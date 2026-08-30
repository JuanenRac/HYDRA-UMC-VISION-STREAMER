# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/config.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Per-camera capture configuration: parsing and validation.

This is the "Dynamic Configuration" piece from the README's Key Points -
deciding and validating what each of up to 8 cameras should capture at
(device, resolution, framerate, pixel format) is plain data validation,
independent of the V4L2/GStreamer runtime that would actually open the
device. That runtime, and the physical USB cameras, are what's still
missing to run this for real.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ALLOWED_FORMATS = ("MJPG", "YUYV", "H264")
MAX_CAMERAS = 8

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
    device: str
    width: int
    height: int
    fps: int
    format: str


def _parse_camera(raw: object, index: int) -> CameraConfig:
    if not isinstance(raw, dict):
        raise ConfigError(f"camera {index}: entry must be an object")
    required = ("name", "device", "width", "height", "fps", "format")
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
    if not str(raw["device"]).startswith("/dev/"):
        raise ConfigError(f"camera {index} ({raw['name']}): device must start with /dev/")
    for field in ("width", "height", "fps"):
        if isinstance(raw[field], bool) or not isinstance(raw[field], int) or raw[field] <= 0:
            raise ConfigError(f"camera {index} ({raw['name']}): {field} must be a positive integer")
    if raw["format"] not in ALLOWED_FORMATS:
        raise ConfigError(
            f"camera {index} ({raw['name']}): format {raw['format']!r} not in {ALLOWED_FORMATS}"
        )

    return CameraConfig(
        name=raw["name"], device=raw["device"], width=raw["width"],
        height=raw["height"], fps=raw["fps"], format=raw["format"],
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

    devices = [c.device for c in cameras]
    dup_devices = sorted({d for d in devices if devices.count(d) > 1})
    if dup_devices:
        raise ConfigError(f"duplicate camera device(s): {dup_devices}")

    return cameras
