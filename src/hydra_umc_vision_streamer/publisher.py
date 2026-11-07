# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/publisher.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Publishing the frames of a camera to a MediaMTX server over RTSP, by running GStreamer for real.

The camera is opened once, by the capture of this process (OpenCV). To publish what it sees, this module starts `gst-launch-1.0` as a child process (no
shell, an argument list built from validated pieces) whose input is the standard input: the JPEG frames of the capture are written to it one after the
other, `jpegparse` cuts them apart again, and the rest of the pipeline either encodes them to H.264 (`codec: h264`, what WebRTC and most players want) or
sends them on as they are (`codec: mjpeg`) to `rtspclientsink`, which pushes them to `rtsp://<host>:<port>/<camera>` where MediaMTX waits for a publisher
(`source: publisher`, see `config mediamtx`). Feeding the pipeline from the capture instead of letting GStreamer open the device means that the camera
is never opened twice, and that an IP camera's password never appears in an argument list.

If the child ends, it is started again after the deterministic delays of `reconnect.py`; after the last attempt the state is `given_up` and stays so. A
machine without `gst-launch-1.0` ends in `unavailable` at once (a missing program is not a failure that waiting cures). With `mediamtxApi` the status
also asks MediaMTX whether the path is ready. All of this is off unless the publishing file says `"enabled": true` and the server is started with
`--publish`. It was tried against a stand-in program and, in a manual workflow, against a real GStreamer and a real MediaMTX. `codec: mjpeg` only carries 4:2:0 or
4:2:2 JPEG frames (the RTP payloader of GStreamer refuses the rest); frames of another layout are not fed and the status says why.
"""
from __future__ import annotations

import http.client
import json
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .log_redaction import redact_secrets
from .reconnect import ReconnectPolicy

CODECS = ("h264", "mjpeg")
_KEYS = {"enabled", "gstLaunch", "rtspBase", "codec", "bitrateKbps", "mediamtxApi", "allowRemote", "restart"}
_RESTART_KEYS = {"maxAttempts", "baseDelaySeconds", "maxDelaySeconds"}
_PART = re.compile(r"!|[A-Za-z0-9._/:=+,-]{1,200}")
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
STABLE_SECONDS = 10.0
STDERR_TAIL_BYTES = 2048
PROBE_LIMIT_BYTES = 16 * 1024


class PublishError(ValueError):
    """The publishing file cannot be used."""


class FrameSource(Protocol):
    fps: int

    def wait_for_frame(self, last_seen: int, timeout: float = 5.0) -> Any: ...


@dataclass(frozen=True)
class Address:
    scheme: str
    host: str
    port: int
    path: str


@dataclass(frozen=True)
class PublishConfig:
    enabled: bool
    gst_launch: tuple[str, ...]
    rtsp: Address
    codec: str
    bitrate_kbps: int
    api: Address | None
    policy: ReconnectPolicy

    def describe(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "gstLaunch": self.gst_launch[0], "rtspBase": f"rtsp://{self.rtsp.host}:{self.rtsp.port}{self.rtsp.path}",
                "codec": self.codec, "bitrateKbps": self.bitrate_kbps, "mediamtxApi": f"http://{self.api.host}:{self.api.port}" if self.api else None,
                "restart": {"maxAttempts": self.policy.max_attempts, "baseDelaySeconds": self.policy.base_delay_s, "maxDelaySeconds": self.policy.max_delay_s}}


def _address(url: object, scheme: str, default_port: int, allow_remote: bool, what: str) -> Address:
    if not isinstance(url, str) or len(url) > 300:
        raise PublishError(f"{what} must be a {scheme} URL")
    parts = urlparse(url)
    if parts.scheme != scheme or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise PublishError(f"{what} must be a plain {scheme}://host[:port][/path] URL without credentials")
    try:
        port = parts.port or default_port
    except ValueError:
        raise PublishError(f"{what} has an invalid port") from None
    host = parts.hostname
    if not allow_remote and host not in ("localhost", "127.0.0.1", "::1"):
        raise PublishError(f"{what} points away from this machine: set allowRemote to true to allow it")
    path = parts.path.rstrip("/")
    if path and (not re.fullmatch(r"(/[A-Za-z0-9._~-]+)+", path) or any(set(part) == {"."} for part in path.split("/")[1:])):
        raise PublishError(f"{what} has a path with characters that are not allowed")
    return Address(scheme, host, port, path)


def parse_publish_config(block: object) -> PublishConfig:
    if not isinstance(block, dict) or set(block) - _KEYS:
        raise PublishError(f"the publishing file is an object with the keys {sorted(_KEYS)}")
    enabled = block.get("enabled", False)
    allow_remote = block.get("allowRemote", False)
    if not isinstance(enabled, bool) or not isinstance(allow_remote, bool):
        raise PublishError("enabled and allowRemote must be true or false")
    command = block.get("gstLaunch", ["gst-launch-1.0"])
    if not isinstance(command, list) or not 1 <= len(command) <= 4 or not all(isinstance(c, str) and c and len(c) <= 300 and "\x00" not in c for c in command):
        raise PublishError("gstLaunch is the program (and at most 3 leading arguments) that runs a GStreamer pipeline, as a list of texts")
    codec = block.get("codec", "h264")
    if codec not in CODECS:
        raise PublishError(f"codec must be one of {list(CODECS)}")
    bitrate = block.get("bitrateKbps", 2000)
    if isinstance(bitrate, bool) or not isinstance(bitrate, int) or not 100 <= bitrate <= 20000:
        raise PublishError("bitrateKbps must be an integer from 100 to 20000")
    restart = block.get("restart", {})
    if not isinstance(restart, dict) or set(restart) - _RESTART_KEYS:
        raise PublishError(f"restart is an object with the keys {sorted(_RESTART_KEYS)}")
    try:
        policy = ReconnectPolicy(restart.get("maxAttempts", 5), restart.get("baseDelaySeconds", 1.0), restart.get("maxDelaySeconds", 30.0))
    except (TypeError, ValueError) as error:
        raise PublishError(f"restart: {error}") from None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (policy.max_attempts, policy.base_delay_s, policy.max_delay_s)) or policy.max_attempts > 100 or policy.max_delay_s > 3600:
        raise PublishError("restart: maxAttempts is an integer up to 100 and the delays are numbers up to 3600 seconds")
    api = block.get("mediamtxApi")
    return PublishConfig(
        enabled, tuple(command), _address(block.get("rtspBase", "rtsp://127.0.0.1:8554"), "rtsp", 8554, allow_remote, "rtspBase"), codec, bitrate,
        _address(api, "http", 9997, allow_remote, "mediamtxApi") if api is not None else None, policy,
    )


def load_publish_config(path: str | Path) -> PublishConfig:
    file = Path(path)
    try:
        if file.stat().st_size > 64 * 1024:
            raise PublishError("the publishing file is larger than 65536 bytes")
        block = json.loads(file.read_text(encoding="utf-8"), parse_constant=lambda name: (_ for _ in ()).throw(ValueError(f"{name} is not a valid JSON number")))
    except OSError as error:
        raise PublishError(f"the publishing file cannot be read: {error.strerror}") from None
    except ValueError as error:
        if isinstance(error, PublishError):
            raise
        raise PublishError(f"the publishing file is not valid JSON: {error}") from None
    return parse_publish_config(block)


def rtsp_location(config: PublishConfig, camera: str) -> str:
    if not _NAME.fullmatch(camera):
        raise PublishError(f"camera name {camera!r} cannot be used in an address")
    return f"rtsp://{config.rtsp.host}:{config.rtsp.port}{config.rtsp.path}/{camera}"


def build_feed_command(config: PublishConfig, camera: str, fps: int) -> list[str]:
    """The program and arguments of the child process: JPEG frames in on the standard input, RTSP out. Every piece is a plain token."""
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240:
        raise PublishError("fps must be an integer from 1 to 240")
    head = ["-q", "-e", "fdsrc", "fd=0", "do-timestamp=true", "!", f"image/jpeg,framerate={fps}/1", "!", "jpegparse", "!"]
    body: list[str]
    if config.codec == "h264":
        body = ["jpegdec", "!", "videoconvert", "!", "x264enc", "tune=zerolatency", "speed-preset=ultrafast", f"bitrate={config.bitrate_kbps}", "key-int-max=30", "!", "h264parse", "!"]
    else:
        # rtspclientsink payloads by itself (its pads take the encoded media, not RTP): a payloader in front of it does not link
        body = []
    command = [*config.gst_launch, *head, *body, "rtspclientsink", f"location={rtsp_location(config, camera)}"]
    bad = [c for c in command[len(config.gst_launch):] if not _PART.fullmatch(c)]
    if bad:
        raise PublishError(f"the pipeline would carry a token that is not plain: {bad[0]!r}")
    return command


def jpeg_subsampling(payload: bytes) -> str | None:
    """The chroma layout a baseline JPEG declares in its frame header ("4:2:0", "4:2:2", "4:4:4", "gray" or "other"), or None when no frame header is found.

    The RTP payloader of GStreamer (`rtpjpegpay`, behind `codec: mjpeg`) only accepts 4:2:0 and 4:2:2: it rejects every frame of anything else with
    "Invalid component" and nothing ever reaches MediaMTX, so the feeder asks first and says why instead of publishing silence.
    """
    index = 2
    size = len(payload)
    while index + 4 <= size and payload[index] == 0xFF:
        marker = payload[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in (0xC0, 0xC1, 0xC2):
            head = payload[index + 4 : index + 10]
            if len(head) < 6:
                return None
            count = head[5]
            table = payload[index + 10 : index + 10 + 3 * count]
            if count == 1:
                return "gray"
            if count != 3 or len(table) < 9:
                return "other"
            first, second, third = table[1], table[4], table[7]
            if second != 0x11 or third != 0x11:
                return "other"
            return {0x11: "4:4:4", 0x21: "4:2:2", 0x22: "4:2:0"}.get(first, "other")
        if marker == 0xDA or marker == 0xD9:
            return None
        index += 2 + (payload[index + 2] << 8 | payload[index + 3])
    return None


def probe_ready(api: Address, camera: str, timeout: float = 2.0) -> bool | None:
    """Whether MediaMTX says the path of `camera` has a publisher (`GET /v3/paths/get/<name>`, field `ready`). None when it cannot be asked or does not say."""
    connection = http.client.HTTPConnection(api.host, api.port, timeout=timeout)
    try:
        connection.request("GET", f"{api.path}/v3/paths/get/{camera}", headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read(PROBE_LIMIT_BYTES)
        if response.status == 404:
            return False
        if response.status != 200:
            return None
        ready = json.loads(body.decode("utf-8")).get("ready")
        return ready if isinstance(ready, bool) else None
    except (OSError, http.client.HTTPException, ValueError, AttributeError):
        return None
    finally:
        connection.close()


Spawn = Callable[..., Any]


class FeedPublisher:
    """Runs and watches the child process of one camera."""

    def __init__(self, camera: str, source: FrameSource, config: PublishConfig, spawn: Spawn = subprocess.Popen, clock: Callable[[], float] = time.monotonic) -> None:
        self.camera = camera
        self.source = source
        self.config = config
        self._spawn = spawn
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._state = "stopped"
        self._restarts = 0
        self._frames_sent = 0
        self._last_error: str | None = None
        self._tail: deque[int] = deque(maxlen=STDERR_TAIL_BYTES)
        self._proc: Any = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=f"publish-{self.camera}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is not None:
            self._end(proc)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        with self._lock:
            self._state = "stopped"

    def _set(self, state: str, error: str | None = None) -> None:
        with self._lock:
            self._state = state
            if error is not None:
                self._last_error = redact_secrets(error)[:300]

    def status(self) -> dict[str, Any]:
        with self._lock:
            state, restarts, sent, error = self._state, self._restarts, self._frames_sent, self._last_error
        ready = probe_ready(self.config.api, self.camera) if self.config.api and state == "publishing" else None
        return {"camera": self.camera, "state": state, "codec": self.config.codec, "url": rtsp_location(self.config, self.camera), "restarts": restarts,
                "framesSent": sent, "ready": ready, "lastError": error}

    @staticmethod
    def _end(proc: Any) -> None:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=3.0)
        except Exception:  # noqa: BLE001 - it did not leave by itself: ask, then insist (this is our own child)
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except Exception:  # noqa: BLE001
                proc.kill()

    def _drain_stderr(self, proc: Any) -> None:
        stream = getattr(proc, "stderr", None)
        if stream is None:
            return
        try:
            for chunk in iter(lambda: stream.read(256), b""):
                self._tail.extend(chunk)
        except (OSError, ValueError):
            pass

    def _run(self) -> None:
        program = self.config.gst_launch[0]
        if shutil.which(program) is None and not Path(program).is_file():
            self._set("unavailable", f"{program} is not installed: install GStreamer (gst-launch-1.0, the good, bad and ugly plugin sets and rtspclientsink)")
            return
        command = build_feed_command(self.config, self.camera, int(getattr(self.source, "fps", 30)))
        failures = 0
        while not self._stop.is_set():
            self._set("starting")
            try:
                proc = self._spawn(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, shell=False)
            except OSError as error:
                self._set("unavailable", f"cannot start {program}: {error.strerror or type(error).__name__}")
                return
            self._proc = proc
            threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True, name=f"publish-{self.camera}-stderr").start()
            started = self._clock()
            self._set("publishing")
            self._feed(proc)
            self._end(proc)
            code = proc.poll()
            self._proc = None
            if self._stop.is_set():
                return
            tail = bytes(self._tail).decode("utf-8", errors="replace").strip().splitlines()[-1:] or [""]
            self._set("restarting", f"the pipeline ended (exit code {code}): {tail[0]}")
            if self._clock() - started >= STABLE_SECONDS:
                failures = 0  # it ran for a while: the next end is a new trouble, not one more of the same
            failures += 1
            if failures > self.config.policy.max_attempts:
                self._set("given_up")
                return
            delay = self.config.policy.delay_for(failures)
            with self._lock:
                self._restarts += 1
            self._stop.wait(delay)

    def _feed(self, proc: Any) -> None:
        last_seen = 0
        while not self._stop.is_set() and proc.poll() is None:
            frame = self.source.wait_for_frame(last_seen, timeout=2.0)
            if frame is None:
                continue
            last_seen = frame.frame_id
            if self.config.codec == "mjpeg":
                layout = jpeg_subsampling(frame.payload)
                if layout not in (None, "4:2:0", "4:2:2"):
                    self._set("publishing", f"the camera sends {layout} JPEG frames and codec mjpeg can only carry 4:2:0 or 4:2:2: use codec h264")
                    continue
            try:
                proc.stdin.write(frame.payload)
                proc.stdin.flush()
            except (OSError, ValueError):
                return
            with self._lock:
                self._frames_sent += 1
