# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_frame_meta.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The FrameMeta message of /latest.json: size from the JPEG header, the SDK's rules, and nothing invented when the header is unreadable."""
from __future__ import annotations

import importlib
import struct
import sys
from pathlib import Path

import pytest

from hydra_umc_vision_streamer.frame_meta import frame_meta, iso_utc, jpeg_size
from hydra_umc_vision_streamer.mjpeg_server import Frame, _latest_info


def _jpeg(width: int, height: int, marker: int = 0xC0) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = bytes([0xFF, marker]) + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\xff\xd9"


def test_the_size_is_read_from_the_start_of_frame_segment() -> None:
    assert jpeg_size(_jpeg(640, 480)) == (640, 480)
    assert jpeg_size(_jpeg(1920, 1080, marker=0xC2)) == (1920, 1080)  # progressive


@pytest.mark.parametrize("data", [b"", b"\xff\xd8", b"not a jpeg", b"\xff\xd8fake-jpeg\xff\xd9", _jpeg(0, 10), _jpeg(9000, 10), _jpeg(640, 480)[:12]])
def test_an_unreadable_header_gives_no_size(data: bytes) -> None:
    assert jpeg_size(data) is None


def test_the_message_has_the_fields_of_the_contract() -> None:
    meta = frame_meta(Frame(_jpeg(640, 480), 7, "sess 1\r\n", 1.5), source_id="cam0")
    assert meta == {"schema_version": "1.0", "frame_id": "7", "capture_ts_utc": "1970-01-01T00:00:01.500Z", "width": 640, "height": 480,
                    "pixel_format": "JPEG", "session_id": "sess1", "source_id": "cam0"}
    assert iso_utc(0) == "1970-01-01T00:00:00.000Z"


def test_no_message_is_made_up_when_the_size_is_unknown() -> None:
    assert frame_meta(Frame(b"\xff\xd8fake-jpeg\xff\xd9", 1, "s", 1.0)) is None
    assert "frame_meta" not in _latest_info(Frame(b"\xff\xd8fake-jpeg\xff\xd9", 1, "s", 1.0))


def test_latest_info_carries_the_message_next_to_the_old_fields() -> None:
    info = _latest_info(Frame(_jpeg(320, 240), 3, "s1", 10.0), now=10.5)
    assert info["frame_id"] == 3 and info["data_age_ms"] == 500 and info["frame_meta"]["width"] == 320


def test_the_message_passes_the_sdk_validator() -> None:
    source = Path(__file__).resolve().parents[2] / "HYDRA-UMC-SDK" / "clients" / "python" / "src"
    if not (source / "hydra_umc_sdk" / "vision_pipeline.py").is_file():
        pytest.skip("the SDK checkout is not next to this repository")
    sys.path.insert(0, str(source))
    try:
        sdk = importlib.import_module("hydra_umc_sdk.vision_pipeline")
    finally:
        sys.path.remove(str(source))
    sdk.validate_frame_meta(frame_meta(Frame(_jpeg(640, 480), 7, "sess-1", 1.5), source_id="cam0"))
