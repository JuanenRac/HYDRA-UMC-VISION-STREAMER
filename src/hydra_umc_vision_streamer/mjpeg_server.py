# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/mjpeg_server.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
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

import io
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .buffer import FrameBuffer

logger = logging.getLogger(__name__)

MJPEG_BOUNDARY = "hydraumcframe"


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
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._buffer: FrameBuffer[bytes] = FrameBuffer(max_size=buffer_size)
        self._lock = threading.Lock()
        self._new_frame = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap = None
        self.frames_captured = 0
        self.last_error: str | None = None

    def start(self) -> None:
        try:
            import cv2  # noqa: PLC0415 - deliberately lazy, see class docstring
        except ImportError as exc:
            raise RuntimeError(
                "opencv-python (cv2) is not installed - install python3-opencv "
                "(Debian/Raspberry Pi OS) to actually capture from a real camera."
            ) from exc

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
            raise CameraUnavailableError(f"Could not open {kind} {self.device!r} - check it is connected/reachable, its credentials are correct, and it is not in use by another process.")
        if not is_ip_camera:
            # A real RTSP camera dictates its own real resolution/fps -
            # cap.set() against an RTSP stream is a real no-op on most
            # camera firmware (silently ignored, sometimes returns False),
            # not a genuine control this source has over that hardware the
            # way it does for a real local V4L2 device.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._cap = cap
        self._thread = threading.Thread(target=self._capture_loop, name=f"mjpeg-capture-{self.device}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap is not None:
            self._cap.release()

    def _capture_loop(self) -> None:
        import cv2  # noqa: PLC0415 - see start()

        consecutive_failures = 0
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                self.last_error = f"{consecutive_failures} consecutive failed reads from {self.device}"
                # Real, bounded backoff on read failure - a camera briefly
                # busy/reconnecting shouldn't spin this thread at 100% CPU.
                time.sleep(min(0.05 * consecutive_failures, 1.0))
                continue
            consecutive_failures = 0
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            if not ok:
                continue
            jpeg_bytes = encoded.tobytes()
            with self._new_frame:
                self._buffer.push(jpeg_bytes)
                self.frames_captured += 1
                self._new_frame.notify_all()

    def wait_for_frame(self, last_seen: int, timeout: float = 5.0) -> bytes | None:
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
            drained = self._buffer.drain()
            return drained[-1] if drained else None


def make_handler(source: MjpegCaptureSource) -> type[BaseHTTPRequestHandler]:
    """Builds a request handler bound to one specific capture source - the
    real HTTP wire format HYDRA-UMC-SERVER's own proxy and every real
    client (MjpegPlayer.kt, CameraPIP) already expect: a `multipart/x-mixed-replace`
    stream of real `Content-Type: image/jpeg` parts."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
            logger.info("%s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            if self.path not in ("/stream", "/"):
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            last_seen = 0
            try:
                while True:
                    frame = source.wait_for_frame(last_seen, timeout=10.0)
                    if frame is None:
                        # A genuinely stalled camera (no new frame in 10s) -
                        # end this connection cleanly rather than hold it
                        # open forever; a real client (MjpegPlayer.kt,
                        # <img>) reconnects on its own.
                        break
                    last_seen = source.frames_captured
                    header = f"--{MJPEG_BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(frame)}\r\n\r\n".encode("ascii")
                    self.wfile.write(header)
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # A client disconnecting mid-stream is normal, not an error
                # to log - ConnectionAbortedError is Windows' own name for
                # the same real condition BrokenPipeError/ConnectionResetError
                # cover on Linux (confirmed live: a curl client
                # cutting a real IP-camera stream short raised exactly this
                # on this Windows dev machine, printing an unhandled
                # traceback to stderr for a perfectly normal disconnect
                # until this was added - ThreadingHTTPServer still isolates
                # it to the one request thread either way, so this was never
                # a crash risk the way HYDRA-UMC-SERVER's own equivalent gap
                # was, just noisy).
                pass

    return Handler


def serve_camera(device: str, addr: str, port: int, width: int, height: int, fps: int) -> None:
    """Real, blocking entry point: opens `device`, starts capturing, and
    serves the real MJPEG stream at http://addr:port/stream until
    interrupted. Raises CameraUnavailableError/RuntimeError immediately
    (before binding a socket) if the device can't be opened at all -
    fails loud, matching this project's own "no guessed process" ethos
    (see HYDRA-UMC-SERVER's own SPI_BRIDGE_URL comment for the same
    reasoning applied there)."""
    source = MjpegCaptureSource(device=device, width=width, height=height, fps=fps)
    source.start()
    try:
        server = ThreadingHTTPServer((addr, port), make_handler(source))
        logger.info("MJPEG stream for %s serving on http://%s:%s/stream", device, addr, port)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    finally:
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
