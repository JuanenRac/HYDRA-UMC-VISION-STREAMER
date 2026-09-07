# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/config.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Per-camera capture configuration: parsing and validation.

This is the "Dynamic Configuration" piece from the README's Key Points -
deciding and validating what each of up to 8 cameras should capture at
(source type, device/host, resolution, framerate, pixel format) is plain
data validation, independent of the V4L2/RTSP/GStreamer runtime that
would actually open the device.

Two real source types, verified end to end against real hardware:
`usb` (a real V4L2 device via OpenCV, mjpeg_server.py's
original v0 - see that module's own header) and `ip` (a real RTSP camera,
also via OpenCV - `cv2.VideoCapture()` already speaks RTSP through its
own FFmpeg backend with no new dependency, confirmed against 2 real
IP cameras on the local network: real H.264 frames pulled from
`rtsp://user:pass@host:554/11` main-stream and `/12` sub-stream paths -
see mjpeg_server.py's own `_open_capture()` for where that URL gets
built and opened). The exact RTSP path a given camera answers on is
real, camera-firmware-specific data (`rtsp_path` below), not something
this module can guess - two of the four real cameras this was tested
against use `Hipcam RealServer` firmware (`/11`/`/12`); a third
(`H264DVR` firmware) rejected the same credential shape entirely (401
on every path tried) and needs its own real credentials/RTSP-enable
step verified against that camera's own admin UI before it can be
configured here, not invented.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

ALLOWED_FORMATS = ("MJPG", "YUYV", "H264")
ALLOWED_SOURCE_TYPES = ("usb", "ip")
MAX_CAMERAS = 8
DEFAULT_RTSP_PORT = 554

# camera.name is interpolated unescaped into a hand-built YAML file
# (mediamtx_config.build_mediamtx_paths_yaml) and into a gst-launch-1.0
# pipeline string (pipeline.build_capture_pipeline) - both generators
# trust it as a bare token, not a quoted/escaped one. Restricting it to
# this safe set up front is what keeps a stray `:`, space, or newline
# from corrupting either generator's output.
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfigError(ValueError):
    """Raised for a malformed camera configuration file or entry."""


@dataclass(frozen=True)
class CameraConfig:
    name: str
    width: int
    height: int
    fps: int
    format: str
    source_type: str = "usb"
    # USB (source_type == "usb"): a real V4L2 device path, e.g. /dev/video0.
    device: str = ""
    # IP (source_type == "ip"): a real RTSP camera's own connection details.
    # Kept as separate fields rather than one pre-built rtsp:// string so a
    # password containing `@`/`:`/`/` can be embedded safely (see
    # rtsp_url() below) and so this config file never has to duplicate a
    # credential inside an otherwise-opaque URL string.
    host: str = ""
    rtsp_port: int = DEFAULT_RTSP_PORT
    rtsp_path: str = ""
    username: str = ""
    password: str = ""

    def rtsp_url(self) -> str:
        """The real, connectable RTSP URL for this camera - user/password
        percent-encoded (urllib.parse.quote) so a real special character in
        either (this ecosystem has already hit passwords containing `@`)
        can never be misparsed as a second `@`/`:` delimiter in the URL."""
        if self.source_type != "ip":
            raise ValueError(f"rtsp_url() called on a non-ip camera ({self.source_type!r})")
        path = self.rtsp_path if self.rtsp_path.startswith("/") else f"/{self.rtsp_path}"
        if self.username or self.password:
            user = quote(self.username, safe="")
            pw = quote(self.password, safe="")
            return f"rtsp://{user}:{pw}@{self.host}:{self.rtsp_port}{path}"
        return f"rtsp://{self.host}:{self.rtsp_port}{path}"


def _parse_camera(raw: object, index: int) -> CameraConfig:
    if not isinstance(raw, dict):
        raise ConfigError(f"camera {index}: entry must be an object")
    required = ("name", "width", "height", "fps", "format")
    missing = [field for field in required if field not in raw]
    if missing:
        raise ConfigError(f"camera {index}: missing field(s) {missing}")

    if not raw["name"]:
        raise ConfigError(f"camera {index}: name must not be empty")
    if not _NAME_RE.fullmatch(str(raw["name"])):
        raise ConfigError(
            f"camera {index}: name {raw['name']!r} must match {_NAME_RE.pattern} "
            f"(it is written unescaped into generated YAML and gst-launch pipelines)"
        )

    # source_type defaults to "usb" so every camera-list JSON file written
    # before this field existed keeps parsing exactly as before - a real
    # backward-compatibility case, not a hypothetical one, since VISION-
    # STREAMER already had a real v0 (device-only) shape in production.
    source_type = raw.get("source_type", "usb")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ConfigError(f"camera {index} ({raw['name']}): source_type {source_type!r} not in {ALLOWED_SOURCE_TYPES}")

    device = ""
    host = ""
    rtsp_port = DEFAULT_RTSP_PORT
    rtsp_path = ""
    username = ""
    password = ""

    if source_type == "usb":
        device = raw.get("device", "")
        if not str(device).startswith("/dev/"):
            raise ConfigError(f"camera {index} ({raw['name']}): device must start with /dev/ for source_type \"usb\"")
    else:
        host = str(raw.get("host", ""))
        if not host:
            raise ConfigError(f"camera {index} ({raw['name']}): host is required for source_type \"ip\"")
        rtsp_path = str(raw.get("rtsp_path", ""))
        if not rtsp_path:
            raise ConfigError(f"camera {index} ({raw['name']}): rtsp_path is required for source_type \"ip\" (e.g. \"/11\" - real per-camera-firmware value, see this file's own header)")
        rtsp_port = raw.get("rtsp_port", DEFAULT_RTSP_PORT)
        if isinstance(rtsp_port, bool) or not isinstance(rtsp_port, int) or not (0 < rtsp_port < 65536):
            raise ConfigError(f"camera {index} ({raw['name']}): rtsp_port must be a valid port number")
        username = str(raw.get("username", ""))
        password = str(raw.get("password", ""))

    for field in ("width", "height", "fps"):
        if isinstance(raw[field], bool) or not isinstance(raw[field], int) or raw[field] <= 0:
            raise ConfigError(f"camera {index} ({raw['name']}): {field} must be a positive integer")
    if raw["format"] not in ALLOWED_FORMATS:
        raise ConfigError(
            f"camera {index} ({raw['name']}): format {raw['format']!r} not in {ALLOWED_FORMATS}"
        )

    return CameraConfig(
        name=raw["name"], width=raw["width"], height=raw["height"], fps=raw["fps"], format=raw["format"],
        source_type=source_type, device=device,
        host=host, rtsp_port=rtsp_port, rtsp_path=rtsp_path, username=username, password=password,
    )


def load_cameras(path: Path) -> list[CameraConfig]:
    """Parse a camera list JSON file: a top-level array of camera entries."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"could not read config {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigError(f"config {path} must be a JSON array of camera entries")
    if len(raw) > MAX_CAMERAS:
        raise ConfigError(f"config {path} declares {len(raw)} cameras; maximum is {MAX_CAMERAS}")

    cameras = [_parse_camera(item, i) for i, item in enumerate(raw)]

    names = [c.name for c in cameras]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ConfigError(f"duplicate camera name(s): {duplicates}")

    # Real connection identity: for "usb" that's the /dev/ path; for "ip"
    # a device string is always "" (see CameraConfig above), so comparing
    # raw .device values would falsely flag every 2nd+ IP camera as a
    # duplicate of the first. host+rtsp_path (not the full rtsp_url(),
    # which would bury a real duplicate host/path behind two different
    # credentials) is the real identity check for that source type.
    connections = [c.device if c.source_type == "usb" else f"{c.host}:{c.rtsp_port}{c.rtsp_path}" for c in cameras]
    dup_connections = sorted({d for d in connections if connections.count(d) > 1})
    if dup_connections:
        raise ConfigError(f"duplicate camera connection(s): {dup_connections}")

    return cameras
