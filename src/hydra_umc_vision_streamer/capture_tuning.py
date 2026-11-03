# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/capture_tuning.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""How a camera is opened and read: the timeouts of an RTSP stream and the format and queue of a USB camera.

An RTSP camera that stops answering would block `read()` for as long as the network stack waits, so the capture thread never reconnects; both timeouts
bound that wait so the reconnection policy can act. A USB camera asked for compressed frames (MJPG) and a queue of one frame gives the newest frame
instead of one that sat in a driver queue, at the resolution and rate the bus can carry. Every value can be changed in an optional JSON file
(`--capture-tuning FILE`); without the file the defaults below apply.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_KEYS = {"rtspOpenTimeoutMs", "rtspReadTimeoutMs", "usbFourcc", "usbQueueFrames"}
MAX_TIMEOUT_MS = 120_000
MIN_TIMEOUT_MS = 100


class TuningError(ValueError):
    """The capture tuning file cannot be used."""


@dataclass(frozen=True)
class CaptureTuning:
    rtsp_open_timeout_ms: int = 5000
    rtsp_read_timeout_ms: int = 5000
    usb_fourcc: str = "MJPG"  # "" leaves the format the driver chooses
    usb_queue_frames: int = 1


def _int(block: dict, key: str, default: int, low: int, high: int) -> int:
    value = block.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise TuningError(f"{key} must be an integer from {low} to {high}")
    return value


def parse_capture_tuning(block: object) -> CaptureTuning:
    if not isinstance(block, dict) or set(block) - _KEYS:
        raise TuningError(f"the capture tuning file is an object with the keys {sorted(_KEYS)}")
    fourcc = block.get("usbFourcc", "MJPG")
    if not isinstance(fourcc, str) or (fourcc and (len(fourcc) != 4 or not fourcc.isascii() or not fourcc.isalnum())):
        raise TuningError("usbFourcc must be empty or four letters or digits (for example MJPG or YUYV)")
    return CaptureTuning(
        _int(block, "rtspOpenTimeoutMs", 5000, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS),
        _int(block, "rtspReadTimeoutMs", 5000, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS),
        fourcc,
        _int(block, "usbQueueFrames", 1, 1, 16),
    )


def load_capture_tuning(path: str | Path) -> CaptureTuning:
    file = Path(path)
    try:
        if file.stat().st_size > 16 * 1024:
            raise TuningError("the capture tuning file is larger than 16384 bytes")
        block = json.loads(file.read_text(encoding="utf-8"))
    except OSError as error:
        raise TuningError(f"the capture tuning file cannot be read: {error.strerror}") from None
    except ValueError as error:
        if isinstance(error, TuningError):
            raise
        raise TuningError(f"the capture tuning file is not valid JSON: {error}") from None
    return parse_capture_tuning(block)
