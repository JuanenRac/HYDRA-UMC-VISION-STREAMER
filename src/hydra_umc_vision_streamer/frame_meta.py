# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/frame_meta.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The identity of a streamed frame as the SDK's `FrameMeta` message (JSON Schema v1, closed).

`GET /latest.json` carries it as `frame_meta` next to the fields it always had, so a detection service reads the same message from the vision node and from
the streamer. The size comes from the JPEG header itself (no decoder needed); when the header cannot be read, `frame_meta` is left out rather than invented.
Standard library only.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
MAX_DIMENSION = 8192
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,64}")
# Start-of-frame markers (baseline, extended, progressive, ...): every 0xFFC0-0xFFCF except DHT (C4), JPG (C8) and DAC (CC).
_SOF = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def iso_utc(epoch_seconds: float) -> str:
    """RFC 3339 text (UTC, milliseconds) of an instant given in seconds since the epoch."""
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) read from the start-of-frame segment of a JPEG, or None when there is none or it is malformed."""
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None
    pos, end = 2, len(data)
    while pos + 4 <= end:
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:  # fill byte
            pos += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:  # markers without a length
            pos += 2
            continue
        if marker in (0xD9, 0xDA):  # end of image / start of scan: no frame header after this
            return None
        length = (data[pos + 2] << 8) | data[pos + 3]
        if length < 2:
            return None
        if marker in _SOF:
            if pos + 9 > end:
                return None
            height = (data[pos + 5] << 8) | data[pos + 6]
            width = (data[pos + 7] << 8) | data[pos + 8]
            if 1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION:
                return width, height
            return None
        pos += 2 + length
    return None


def frame_meta(frame: Any, source_id: str | None = None) -> dict[str, Any] | None:
    """The FrameMeta message of `frame` (duck-typed: `payload`, `frame_id`, `session_id`, `capture_ts`), or None when the JPEG size cannot be read."""
    size = jpeg_size(frame.payload)
    if size is None:
        return None
    message: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "frame_id": str(frame.frame_id),
        "capture_ts_utc": iso_utc(frame.capture_ts),
        "width": size[0],
        "height": size[1],
        "pixel_format": "JPEG",
    }
    session = "".join(c for c in str(frame.session_id) if c.isalnum() or c in "._:-")[:64]
    if _IDENTIFIER.fullmatch(session):
        message["session_id"] = session
    if source_id and _IDENTIFIER.fullmatch(source_id):
        message["source_id"] = source_id
    return message
