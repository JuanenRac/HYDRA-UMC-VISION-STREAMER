# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/mjpeg_server.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""A real, working v0 for the actual gap this project's own README/main.py
docstring already named: "Actually running the generated pipeline... against
physical USB cameras... is future work" - this closes exactly that, for the
one thing it needs to do today (get a real USB webcam's picture in front of
an operator), deliberately not the full GStreamer/Hailo-8 tee/inference
pipeline pipeline.py already describes for tomorrow.

Real, not a placeholder: opens a real V4L2 device via OpenCV
(cv2.VideoCapture), JPEG-encodes real captured frames, and serves them as a
real HTTP MJPEG multipart stream (the same wire format HYDRA-UMC-SERVER's
own GET /api/camera/:id/stream already promises and every real client
already expects - HYDRA-UMC-ANDROID-CONTROL's MjpegPlayer.kt, STUDIO's
CameraPIP - see server.ts's own proxy target). Reuses this project's own,
already-real, already-tested FrameBuffer (buffer.py) for the exact same
bounded-backpressure reasoning that module's own docstring explains, with a
lock added here (buffer.py itself is not thread-safe by design, kept that
way so its own tests stay simple) since a real capture thread and one HTTP
handler thread per connected client both touch it concurrently here.

Why OpenCV and not the GStreamer pipeline pipeline.py generates: GStreamer's
own Python bindings (PyGObject/gi) are a real, heavy, awkward-to-install
dependency for a v0 that only needs "decode MJPEG/YUYV frames from a UVC
webcam and re-encode as JPEG" - a job OpenCV's VideoCapture already does in
one call, and python3-opencv is a real Debian package (no source build on
ARM). GStreamer stays the real, correct choice for the actual future job
(hardware-accelerated capture + zero-copy tee into Hailo-8 inference,
matching pipeline.py's own real design) - this module does not replace or
compete with that, it is the simple raw-passthrough path a v0 needs before
that hardware and pipeline exist.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .access import authorized, reject
from .buffer import FrameBuffer
from .config import redact_credentials
from .reconnect import ConnectionState, ConnectionTracker, default_policy
from .snapshot import build_zip, check_max_skew_ms, describe

logger = logging.getLogger(__name__)


class _SecretFilter(logging.Filter):
    """Every line this module logs passes through the shared redaction: a camera address with a
    password, or a token in an error message, never reaches the log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_credentials(record.getMessage())
            record.args = ()
        except Exception:  # noqa: BLE001 - logging must never fail because of the filter
            pass
        return True


logger.addFilter(_SecretFilter())

MJPEG_BOUNDARY = "hydraumcframe"

# Real gap found while auditing the code: nothing capped how many
# clients could open /stream at once - every real client re-encodes
# nothing (the same already-JPEG-encoded frame.payload is written to
# every connection), so this isn't a CPU risk, but each open connection
# is its own real outbound Wi-Fi stream on a CM5 deployment with limited
# uplink - enough simultaneous viewers can genuinely saturate it. Matches
# this project's own bounded-backpressure ethos (buffer.py) applied to
# concurrent clients instead of buffered frames.
DEFAULT_MAX_CLIENTS = 5
SOCKET_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Frame:
    """one real captured JPEG frame, with the identity FrameBuffer's
    own plain-bytes item type discarded before this - which capture
    SESSION produced it (a fresh id assigned every time
    `_reconnect_once` below actually reopens the device, so frames from
    before/after a real reconnect are never conflated as one continuous
    stream), a monotonic `frame_id` distinguishing it from every other
    frame in that same session, and the real wall-clock instant it was
    actually captured (right after `cv2.VideoCapture.read()` returns,
    before JPEG encoding - not when it reached this buffer or a client).
    `payload` is the exact same JPEG bytes `FrameBuffer[bytes]` used to
    carry directly; the wire format `do_GET` below writes to a real HTTP
    client is completely unchanged by this.
    """

    payload: bytes
    frame_id: int
    session_id: str
    capture_ts: float

# How many consecutive failed reads before the capture loop below treats
# the source as really disconnected (releasing and reopening it, via
# reconnect.py's own tested ConnectionTracker) rather than ordinary,
# short-lived jitter on a live UVC/RTSP feed. Found missing while
# auditing the code: ConnectionTracker was real
# and tested but wired only into the `stream simulate` CLI path - this
# live loop just kept re-reading a possibly-dead cv2.VideoCapture with an
# ad-hoc, ever-shorter-relative sleep instead of ever actually releasing
# and reopening it.
RECONNECT_AFTER_CONSECUTIVE_FAILURES = 10


class CameraUnavailableError(RuntimeError):
    """Raised when the requested V4L2 device cannot be opened at all -
    distinct from a transient read failure, which the capture loop below
    retries instead of raising."""


class MjpegCaptureSource:
    """Owns one real capture source - a USB/V4L2 device OR a real RTSP IP
    camera (`device` starting with `rtsp://`, e.g. built from
    CameraConfig.rtsp_url() - see config.py's own header for the real IP
    cameras this was verified against) - and a background thread that
    continuously reads and JPEG-encodes frames into a bounded FrameBuffer
    (buffer.py) - real backpressure: a device producing frames faster
    than any client reads them cannot grow this process's memory without
    bound.

    Lazily imports cv2 (opencv-python / python3-opencv on Debian): this
    module is importable, and every non-capture code path in this project
    stays testable, without the real dependency installed - the same
    lazy-import-degrades-with-a-clear-error pattern this project's own
    hailo_runtime.py already uses for hailort.
    """

    def __init__(self, device: str, width: int, height: int, fps: int, buffer_size: int = 4, jpeg_quality: int = 80) -> None:
        self.device = device
        # What may appear in logs, error messages and thread names: an RTSP
        # URL carries the camera's password.
        self.display_device = redact_credentials(device)
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._buffer: FrameBuffer[Frame] = FrameBuffer(max_size=buffer_size)
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap = None
        self.frames_captured = 0
        self.last_frame_time: float | None = None  # time.monotonic() of the newest frame
        self.gave_up = threading.Event()  # set when every reconnect attempt was used
        self.last_error: str | None = None
        # the initial capture session - a fresh id every time this
        # source (re)starts producing frames, real or reconnected.
        self.session_id = str(uuid.uuid4())

    def start(self) -> None:
        try:
            import cv2  # noqa: PLC0415 - deliberately lazy, see class docstring
        except ImportError as exc:
            raise RuntimeError(
                "opencv-python (cv2) is not installed - install python3-opencv "
                "(Debian/Raspberry Pi OS) to actually capture from a real camera."
            ) from exc

        self._cap = self._open_capture()
        self._thread = threading.Thread(target=self._capture_loop, name=f"mjpeg-capture-{self.display_device}", daemon=True)
        self._thread.start()

    def _open_capture(self):
        """Opens a fresh `cv2.VideoCapture` for `self.device`, exactly the
        way `start()` always has - shared by `start()` and the real
        reconnect path in `_capture_loop()` below, so a reconnect opens
        the device exactly the same way the first connect did."""
        import cv2  # noqa: PLC0415 - see class docstring

        is_ip_camera = self.device.startswith("rtsp://")
        if is_ip_camera:
            # A real RTSP IP camera - cv2.VideoCapture already speaks RTSP
            # through its own bundled FFmpeg backend, no new dependency.
            # CAP_FFMPEG pinned explicitly (not left to auto-detect) so
            # this never silently tries a V4L2/DirectShow backend against
            # a URL string, on any OS. Verified end to end against 2 real
            # RTSP IP cameras (see config.py's own header).
            index_or_path: str | int = self.device
            backend = cv2.CAP_FFMPEG
        else:
            # A bare integer index (e.g. "0") opens /dev/videoN directly via
            # V4L2 - a real /dev/videoN path string works identically, cv2
            # accepts either. CAP_V4L2 pinned explicitly on the real Linux/CM5
            # deployment target this project ships for, so production behavior
            # here is unchanged and never guesses a backend. Off Linux (Mac/
            # Windows dev machines, for local testing against a laptop webcam
            # before real V4L2 hardware exists), cv2.CAP_V4L2 isn't available
            # at all and isOpened() would fail unconditionally even against a
            # real, working camera - CAP_ANY there lets OpenCV pick that
            # platform's own real backend (e.g. DirectShow/MSMF on Windows)
            # instead of silently failing to open a camera that is, in fact,
            # present and working.
            index_or_path = int(self.device) if self.device.isdigit() else self.device
            backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        cap = cv2.VideoCapture(index_or_path, backend)
        if not cap.isOpened():
            cap.release()
            kind = "IP camera" if is_ip_camera else "camera device"
            raise CameraUnavailableError(f"Could not open {kind} {self.display_device!r} - check it is connected/reachable, its credentials are correct, and it is not in use by another process.")
        if not is_ip_camera:
            # A real RTSP camera dictates its own real resolution/fps -
            # cap.set() against an RTSP stream is a real no-op on most
            # camera firmware (silently ignored, sometimes returns False),
            # not a genuine control this source has over that hardware the
            # way it does for a real local V4L2 device.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def _reconnect_once(self, tracker: ConnectionTracker) -> bool:
        """One real release-and-reopen attempt, honoring `tracker`'s own
        deterministic backoff before trying again on failure. Returns
        True with `self._cap` now the new, real, open capture on success;
        False otherwise - check `tracker.state` for `GIVEN_UP`."""
        if self._cap is not None:
            self._cap.release()
        try:
            new_cap = self._open_capture()
        except CameraUnavailableError as exc:
            self.last_error = redact_credentials(str(exc))
            attempts_tried = tracker.attempt
            delay = tracker.on_reconnect_failed()
            if delay is not None:
                logger.warning(
                    "reconnect attempt %d/%d to %s failed: %s - retrying in %.1fs",
                    attempts_tried, tracker.policy.max_attempts, self.display_device, exc, delay,
                )
                self._stop.wait(delay)
            return False
        self._cap = new_cap
        attempts_used = tracker.attempt
        tracker.on_reconnect_success()
        # a real reconnect starts a genuinely new capture session -
        # frames from before and after this point must never be treated
        # as one continuous stream (a gap really happened here).
        self.session_id = str(uuid.uuid4())
        logger.info("reconnected to %s after %d attempt(s)", self.display_device, attempts_used)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()

    def _capture_loop(self) -> None:
        import cv2  # noqa: PLC0415 - see start()

        tracker = ConnectionTracker(default_policy())
        consecutive_failures = 0
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                self.last_error = f"{consecutive_failures} consecutive failed reads from {self.display_device}"
                if consecutive_failures < RECONNECT_AFTER_CONSECUTIVE_FAILURES:
                    # A single/occasional bad read is real, ordinary jitter
                    # on a live feed - a camera briefly busy shouldn't spin
                    # this thread at 100% CPU, but isn't yet a real
                    # disconnect worth releasing and reopening the device
                    # for.
                    time.sleep(min(0.05 * consecutive_failures, 1.0))
                    continue
                # Sustained failure past the threshold above - a real
                # disconnect, not jitter. Actually release and reopen the
                # device (ConnectionTracker's own real, deterministic
                # backoff schedule), rather than continuing to re-read a
                # handle that's most likely dead.
                if tracker.state == ConnectionState.CONNECTED:
                    tracker.on_disconnect()
                if self._reconnect_once(tracker):
                    consecutive_failures = 0
                    continue
                if tracker.state == ConnectionState.GIVEN_UP:
                    self.last_error = (
                        f"gave up reconnecting to {self.display_device} after "
                        f"{tracker.policy.max_attempts} attempts"
                    )
                    logger.error(self.last_error)
                    # A real, permanent outcome, not just this one read
                    # cycle failing - wait_for_frame()'s own callers rely
                    # on `_stop` to mean "no more frames are ever coming",
                    # which is now honestly true.
                    self.gave_up.set()
                    self._stop.set()
                    return
                continue
            consecutive_failures = 0
            # captured right after a real, successful read - before
            # JPEG encoding, which real hardware/frame size makes a
            # variable, non-trivial delay of its own. This is the honest
            # "when did the sensor actually see this" instant, not "when
            # did it finish being processed".
            capture_ts = time.time()
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if not ok:
                continue
            jpeg_bytes = encoded.tobytes()
            with self._new_frame:
                self.frames_captured += 1
                self.last_frame_time = time.monotonic()
                self._buffer.push(Frame(jpeg_bytes, self.frames_captured, self.session_id, capture_ts))
                self._new_frame.notify_all()

    def health(self, max_age_seconds: float = 5.0) -> dict:
        """What GET /health reports: whether frames are arriving right now."""
        with self._lock:
            age = None if self.last_frame_time is None else time.monotonic() - self.last_frame_time
            captured = self.frames_captured
        if self.gave_up.is_set():
            state = "given_up"
        elif age is None:
            state = "connecting"
        elif age <= max_age_seconds:
            state = "streaming"
        else:
            state = "stalled"
        return {
            "state": state,
            "healthy": state == "streaming",
            "last_frame_age_ms": None if age is None else int(age * 1000),
            "frames_captured": captured,
            "session_id": self.session_id,
            "last_error": self.last_error,
        }

    def latest_frame(self) -> Frame | None:
        """The newest frame, or None when none has arrived yet. Does not wait and does not consume it."""
        with self._lock:
            return self._buffer.peek_latest()

    def wait_for_frame(self, last_seen: int, timeout: float = 5.0) -> Frame | None:
        """Blocks until a frame newer than `frames_captured == last_seen`
        is available (or `timeout` elapses), then returns the latest one -
        a real HTTP handler thread's own read loop calls this once per
        multipart part, rather than busy-polling the buffer."""
        with self._new_frame:
            deadline = time.monotonic() + timeout
            while self.frames_captured <= last_seen and not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._new_frame.wait(timeout=remaining)
            # Every viewer shares this one buffer, so reading must not consume
            # the frame: the newest one is returned and left in place.
            return self._buffer.peek_latest()


def _part_header(frame: Frame) -> bytes:
    """The header of one multipart part. Besides the JPEG's type and length it carries the identity of the frame - which capture session
    produced it, its number inside that session and the instant (milliseconds since the epoch) the sensor saw it - so whoever reads the stream
    can tell how old a frame is and whether two frames are the same one. A client that does not know the extra headers ignores them: a browser
    does, and MjpegPlayer.kt looks for the JPEG markers and never reads the part headers."""
    return (
        f"--{MJPEG_BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame.payload)}\r\n"
        f"X-Frame-Id: {frame.frame_id}\r\nX-Session-Id: {_header_safe(frame.session_id)}\r\nX-Capture-Ts: {int(frame.capture_ts * 1000)}\r\n\r\n"
    ).encode("ascii")


def _header_safe(text: str) -> str:
    """The text with anything that could end a header line or is not printable ASCII removed."""
    return "".join(c for c in str(text) if 32 < ord(c) < 127)[:64]


def _latest_info(frame: Frame | None, now: float | None = None) -> dict:
    """What `GET /latest.json` answers: the identity and age of the newest frame, or that there is none."""
    if frame is None:
        return {"available": False}
    seen = time.time() if now is None else now
    return {
        "available": True,
        "frame_id": frame.frame_id,
        "session_id": _header_safe(frame.session_id),
        "capture_ts_ms": int(frame.capture_ts * 1000),
        "data_age_ms": max(0, int((seen - frame.capture_ts) * 1000)),
        "bytes": len(frame.payload),
    }


def make_handler(source: MjpegCaptureSource, max_clients: int = DEFAULT_MAX_CLIENTS, token: str = "") -> type[BaseHTTPRequestHandler]:
    """Builds a request handler bound to one specific capture source - the
    real HTTP wire format HYDRA-UMC-SERVER's own proxy and every real
    client (MjpegPlayer.kt, CameraPIP) already expect: a `multipart/x-mixed-replace`
    stream of real `Content-Type: image/jpeg` parts.

    Routes: `GET /health` (open), `GET /stream` (or `/`), `GET /latest.jpg` (the newest frame as one JPEG) and `GET /latest.json` (its
    identity and age). The last three need the token.

    `max_clients` bounds how many /stream connections can be open at
    once - shared across every request via a class-level counter/lock
    (ThreadingHTTPServer spawns one handler instance per connection, so
    per-instance state can't track this). A request over the limit gets
    a real 503 immediately, before ever touching the capture source.

    `token`, when not empty, is the Bearer token every request but GET /health
    must present (see access.py); empty means no token, which is only allowed
    on loopback."""
    return _build_handler({"": source}, max_clients, token)


def make_multi_handler(cameras: dict[str, MjpegCaptureSource], max_clients: int = DEFAULT_MAX_CLIENTS, token: str = "", snapshot_max_skew_ms: float | None = None) -> type[BaseHTTPRequestHandler]:
    """One handler for several cameras served by this one process: `GET /<name>/stream`, `/<name>/latest.jpg`, `/<name>/latest.json` and
    `/<name>/health`, and `GET /health` for the whole process (healthy only while every camera is). `max_clients` applies to each camera.
    With `snapshot_max_skew_ms` (off by default) `GET /snapshot.json` and `GET /snapshot.zip` answer the newest frame of every camera and how far apart in time they were captured (snapshot.py)."""
    if not cameras:
        raise ValueError("at least one camera is needed")
    for name in cameras:
        if not name or not all(c.isalnum() or c in "-_." for c in name):
            raise ValueError(f"camera name {name!r} cannot be used in an address")
    skew = None if snapshot_max_skew_ms is None else check_max_skew_ms(snapshot_max_skew_ms)
    return _build_handler(dict(cameras), max_clients, token, skew)


def _build_handler(sources: dict[str, MjpegCaptureSource], max_clients: int, token: str, snapshot_max_skew_ms: float | None = None) -> type[BaseHTTPRequestHandler]:
    multi = "" not in sources
    lock = threading.Lock()
    active_by_camera: dict[str, int] = {name: 0 for name in sources}

    # The helpers below are plain functions of the handler instance (not methods), so a test can drive `do_GET` with a stand-in that only has
    # what a request needs (path, wfile and the three send_* calls).
    def reply_json(h, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    def health_of(source) -> dict:
        return source.health() if hasattr(source, "health") else {"state": "unknown", "healthy": True}

    def resolve(path: str):
        """The camera a path is about and what is left of the path, or None for a path that names no camera."""
        if not multi:
            return "", sources[""], path
        parts = path.split("/", 2)  # "", name, rest
        if len(parts) >= 2 and parts[1] in sources:
            return parts[1], sources[parts[1]], "/" + (parts[2] if len(parts) > 2 else "")
        return None

    def serve_latest(h, source, as_json: bool) -> None:
        frame = source.latest_frame() if hasattr(source, "latest_frame") else None
        if as_json:
            reply_json(h, 200 if frame is not None else 503, _latest_info(frame))
            return
        if frame is None:
            h.send_response(503)
            h.send_header("Retry-After", "1")
            h.end_headers()
            return
        h.send_response(200)
        h.send_header("Content-Type", "image/jpeg")
        h.send_header("Content-Length", str(len(frame.payload)))
        h.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        h.send_header("X-Frame-Id", str(frame.frame_id))
        h.send_header("X-Session-Id", _header_safe(frame.session_id))
        h.send_header("X-Capture-Ts", str(int(frame.capture_ts * 1000)))
        h.end_headers()
        h.wfile.write(frame.payload)

    def serve_snapshot(h, as_zip: bool) -> None:
        frames = {name: (src.latest_frame() if hasattr(src, "latest_frame") else None) for name, src in sources.items()}
        manifest = describe(frames, snapshot_max_skew_ms)  # type: ignore[arg-type]
        if not as_zip:
            reply_json(h, 200 if any(c["available"] for c in manifest["cameras"].values()) else 503, manifest)
            return
        if not manifest["complete"]:
            reply_json(h, 503, manifest)
            return
        body = build_zip(frames, manifest)
        h.send_response(200)
        h.send_header("Content-Type", "application/zip")
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        h.send_header("X-Synchronized", "1" if manifest["synchronized"] else "0")
        h.end_headers()
        h.wfile.write(body)

    def take_slot(handler_cls, name: str) -> bool:
        with lock:
            active = active_by_camera[name] if multi else handler_cls._active_clients
            if active >= max_clients:
                return False
            if multi:
                active_by_camera[name] += 1
            else:
                handler_cls._active_clients += 1
            return True

    def release_slot(handler_cls, name: str) -> None:
        with lock:
            if multi:
                active_by_camera[name] -= 1
            else:
                handler_cls._active_clients -= 1

    def serve_stream(h, handler_cls, name: str, source) -> None:
        # Decide inside the lock, answer outside it: a client that does not
        # read its 503 must not hold every other new connection waiting.
        if not take_slot(handler_cls, name):
            h.send_response(503)
            h.send_header("Content-Type", "text/plain")
            h.send_header("Retry-After", "5")
            h.end_headers()
            h.wfile.write(f"stream at its {max_clients}-client limit - retry shortly\n".encode("ascii"))
            return
        try:
            h.send_response(200)
            h.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}")
            h.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            h.send_header("Pragma", "no-cache")
            h.end_headers()
            last_seen = 0
            while True:
                frame = source.wait_for_frame(last_seen, timeout=10.0)
                if frame is None:
                    # A genuinely stalled camera (no new frame in 10s) -
                    # end this connection cleanly rather than hold it
                    # open forever; a real client (MjpegPlayer.kt,
                    # <img>) reconnects on its own.
                    break
                last_seen = frame.frame_id
                # the JPEG itself is what every client reads; the identity of the frame travels in the
                # extra part headers (see _part_header), which a client that does not know them ignores
                h.wfile.write(_part_header(frame))
                h.wfile.write(frame.payload)
                h.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            # A client disconnecting mid-stream is normal, not an error
            # to log - ConnectionAbortedError is Windows' own name for
            # the same real condition BrokenPipeError/ConnectionResetError
            # cover on Linux. ThreadingHTTPServer isolates it to the one
            # request thread either way; this only keeps stderr quiet.
            pass
        finally:
            # Reached only after the slot was taken above (the 503 path
            # returns before this try/finally), so this always has a
            # real slot of its own to release.
            release_slot(handler_cls, name)

    class Handler(BaseHTTPRequestHandler):
        _active_clients = 0  # the one camera of the single-camera handler

        # Seconds any single read or write on a client's socket may block. Without it, a
        # client that opens /stream and then stops reading (or never reads at all) leaves
        # its handler thread stuck in a write once the kernel buffers fill, holding one of
        # the max_clients slots forever: a handful of such clients starve every real viewer.
        # A viewer that is merely slow keeps up with 30 s to spare; a stalled one is dropped.
        timeout = SOCKET_TIMEOUT_SECONDS

        def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
            logger.info("%s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            path = urlparse(self.path).path
            if path == "/health":
                if multi:
                    reports = {name: health_of(src) for name, src in sources.items()}
                    healthy = all(r.get("healthy") for r in reports.values())
                    reply_json(self, 200 if healthy else 503, {"healthy": healthy, "cameras": reports})
                else:
                    report = health_of(sources[""])
                    reply_json(self, 200 if report.get("healthy") else 503, report)
                return
            if not authorized(self, token):
                reject(self)
                return
            if multi and snapshot_max_skew_ms is not None and path in ("/snapshot.json", "/snapshot.zip"):
                serve_snapshot(self, path.endswith(".zip"))
                return
            resolved = resolve(path)
            if resolved is None:
                self.send_response(404)
                self.end_headers()
                return
            name, source, rest = resolved
            if rest == "/health":
                report = health_of(source)
                reply_json(self, 200 if report.get("healthy") else 503, report)
                return
            if rest in ("/latest.jpg", "/latest.json"):
                serve_latest(self, source, rest.endswith(".json"))
                return
            if rest not in ("/stream", "/"):
                self.send_response(404)
                self.end_headers()
                return
            serve_stream(self, Handler, name, source)

    return Handler


def serve_camera(device: str, addr: str, port: int, width: int, height: int, fps: int, max_clients: int = DEFAULT_MAX_CLIENTS, token: str = "") -> None:
    """Real, blocking entry point: opens `device`, starts capturing, and
    serves the real MJPEG stream at http://addr:port/stream until
    interrupted. Raises CameraUnavailableError/RuntimeError immediately
    (before binding a socket) if the device can't be opened at all -
    fails loud, matching this project's own "no guessed process" ethos
    (see HYDRA-UMC-SERVER's own SPI_BRIDGE_URL comment for the same
    reasoning applied there).

    If the camera is lost and every reconnect attempt is used up, the server
    stops and this raises CameraUnavailableError, so the process exits with an
    error and its supervisor restarts it instead of leaving a port open that
    serves nothing."""
    source = MjpegCaptureSource(device=device, width=width, height=height, fps=fps)
    source.start()
    try:
        server = ThreadingHTTPServer((addr, port), make_handler(source, max_clients, token))
        logger.info("MJPEG stream for %s serving on http://%s:%s/stream", source.display_device, addr, port)

        def stop_when_given_up() -> None:
            source.gave_up.wait()
            server.shutdown()

        threading.Thread(target=stop_when_given_up, name="mjpeg-give-up-watch", daemon=True).start()
        try:
            server.serve_forever()
        finally:
            server.server_close()
        if source.gave_up.is_set():
            raise CameraUnavailableError(source.last_error or f"gave up reconnecting to {source.display_device}")
    finally:
        source.stop()
        source.gave_up.set()  # releases the watcher thread on a normal exit


def serve_cameras(
    cameras: dict[str, tuple[str, int, int, int]],
    addr: str,
    port: int,
    max_clients: int = DEFAULT_MAX_CLIENTS,
    token: str = "",
    snapshot_max_skew_ms: float | None = None,
) -> None:
    """All the cameras in one process and one port (`GET /<name>/stream` ...), instead of a process, an interpreter and a copy of OpenCV for
    each camera. `cameras` maps a name to `(device, width, height, fps)`. Every camera is opened before the port is bound, and if one cannot
    be opened none is left running. If any camera is lost for good the whole process stops, so the supervisor restarts it: a half-working
    set of cameras behind one healthy-looking port would hide the lost one."""
    sources: dict[str, MjpegCaptureSource] = {}
    try:
        for name, (device, width, height, fps) in cameras.items():
            source = MjpegCaptureSource(device=device, width=width, height=height, fps=fps)
            source.start()
            sources[name] = source
        server = ThreadingHTTPServer((addr, port), make_multi_handler(sources, max_clients, token, snapshot_max_skew_ms))
        logger.info("MJPEG streams for %d camera(s) serving on http://%s:%s/<name>/stream", len(sources), addr, port)
        stop = threading.Event()

        def stop_when_any_gives_up() -> None:
            while not stop.is_set():
                for source in sources.values():
                    if source.gave_up.is_set():
                        server.shutdown()
                        return
                stop.wait(0.5)

        threading.Thread(target=stop_when_any_gives_up, name="mjpeg-give-up-watch", daemon=True).start()
        try:
            server.serve_forever()
        finally:
            stop.set()
            server.server_close()
        for source in sources.values():
            if source.gave_up.is_set():
                raise CameraUnavailableError(source.last_error or f"gave up reconnecting to {source.display_device}")
    finally:
        for source in sources.values():
            source.stop()


def discover_usb_devices(max_index: int = 10) -> list[dict]:
    """Real USB/V4L2 device enumeration - probes indices `0..max_index-1`
    with the exact same `cv2.VideoCapture`/backend-selection logic
    `MjpegCaptureSource.start()` uses above (CAP_V4L2 on Linux/CM5,
    CAP_ANY elsewhere), so an index this reports as available is
    genuinely the same one `stream serve --device <index>` would open -
    not a separate, possibly-inconsistent enumeration path. Reads one
    real frame per candidate (not just `isOpened()`) since some backends
    report a device as open even when nothing is actually attached and
    the first real read fails - the same false-positive class this
    project's own real hardware testing already ran into elsewhere.
    Releases each device immediately after probing it, real or not, so
    a caller (HYDRA-UMC-SERVER's own `GET /api/camera/discover-usb-
    devices`, which shells out to this via `hydra-umc-vision-streamer
    discover-usb`) never holds a device open longer than the probe
    itself needs."""
    try:
        import cv2  # noqa: PLC0415 - deliberately lazy, see MjpegCaptureSource.start()'s own comment
    except ImportError as exc:
        raise RuntimeError(
            "opencv-python (cv2) is not installed - install python3-opencv "
            "(Debian/Raspberry Pi OS) to discover real cameras."
        ) from exc

    backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    found: list[dict] = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index, backend)
        try:
            if not cap.isOpened():
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            found.append({"index": index, "available": True, "width": int(width), "height": int(height)})
        finally:
            cap.release()
    return found
