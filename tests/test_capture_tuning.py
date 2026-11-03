"""Capture tuning: the file that bounds the RTSP waits and picks the USB format, and how the capture applies it."""
from __future__ import annotations

import json
import sys
import types

import pytest

from hydra_umc_vision_streamer.capture_tuning import CaptureTuning, TuningError, load_capture_tuning, parse_capture_tuning
from hydra_umc_vision_streamer.mjpeg_server import MjpegCaptureSource


def test_defaults_when_the_file_is_an_empty_object():
    assert parse_capture_tuning({}) == CaptureTuning(5000, 5000, "MJPG", 1)


def test_values_are_read():
    tuning = parse_capture_tuning({"rtspOpenTimeoutMs": 2000, "rtspReadTimeoutMs": 3000, "usbFourcc": "YUYV", "usbQueueFrames": 2})
    assert (tuning.rtsp_open_timeout_ms, tuning.rtsp_read_timeout_ms, tuning.usb_fourcc, tuning.usb_queue_frames) == (2000, 3000, "YUYV", 2)


def test_empty_fourcc_leaves_the_driver_format():
    assert parse_capture_tuning({"usbFourcc": ""}).usb_fourcc == ""


@pytest.mark.parametrize("block", [
    [], {"unknown": 1}, {"rtspOpenTimeoutMs": 0}, {"rtspReadTimeoutMs": 10**7}, {"rtspOpenTimeoutMs": True},
    {"usbFourcc": "MJ"}, {"usbFourcc": 5}, {"usbFourcc": "MJ;G"}, {"usbQueueFrames": 0}, {"usbQueueFrames": 99},
])
def test_bad_values_are_refused(block):
    with pytest.raises(TuningError):
        parse_capture_tuning(block)


def test_file_loading(tmp_path):
    good = tmp_path / "t.json"
    good.write_text(json.dumps({"usbQueueFrames": 3}), encoding="utf-8")
    assert load_capture_tuning(good).usb_queue_frames == 3
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(TuningError):
        load_capture_tuning(bad)
    with pytest.raises(TuningError):
        load_capture_tuning(tmp_path / "missing.json")


class _Cap:
    def __init__(self):
        self.set_calls: list[tuple[object, float]] = []

    def isOpened(self):  # noqa: N802 - OpenCV name
        return True

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        return True

    def release(self):
        pass


def _fake_cv2(monkeypatch, caps):
    def factory(target, backend):
        cap = _Cap()
        caps.append(cap)
        return cap

    fake = types.SimpleNamespace(
        VideoCapture=factory, CAP_V4L2=200, CAP_ANY=0, CAP_FFMPEG=1900,
        CAP_PROP_OPEN_TIMEOUT_MSEC="open", CAP_PROP_READ_TIMEOUT_MSEC="read", CAP_PROP_FOURCC="fourcc", CAP_PROP_BUFFERSIZE="queue",
        CAP_PROP_FRAME_WIDTH="w", CAP_PROP_FRAME_HEIGHT="h", CAP_PROP_FPS="fps",
        VideoWriter_fourcc=lambda *chars: "".join(chars),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake)


def test_rtsp_capture_gets_both_timeouts(monkeypatch):
    caps: list[_Cap] = []
    _fake_cv2(monkeypatch, caps)
    source = MjpegCaptureSource("rtsp://cam/1", 640, 480, 30, tuning=CaptureTuning(rtsp_open_timeout_ms=1500, rtsp_read_timeout_ms=2500))
    source._open_capture()
    assert dict(caps[0].set_calls) == {"open": 1500, "read": 2500}


def test_usb_capture_asks_for_mjpg_and_a_queue_of_one(monkeypatch):
    caps: list[_Cap] = []
    _fake_cv2(monkeypatch, caps)
    source = MjpegCaptureSource("0", 640, 480, 30)
    source._open_capture()
    calls = dict(caps[0].set_calls)
    assert calls["fourcc"] == "MJPG" and calls["queue"] == 1 and calls["w"] == 640


def test_usb_capture_without_fourcc_keeps_the_driver_format(monkeypatch):
    caps: list[_Cap] = []
    _fake_cv2(monkeypatch, caps)
    MjpegCaptureSource("0", 640, 480, 30, tuning=CaptureTuning(usb_fourcc="", usb_queue_frames=2))._open_capture()
    calls = dict(caps[0].set_calls)
    assert "fourcc" not in calls and calls["queue"] == 2


def test_a_cv2_without_the_properties_still_opens(monkeypatch):
    fake = types.SimpleNamespace(VideoCapture=lambda t, b: _Cap(), CAP_V4L2=200, CAP_ANY=0, CAP_FFMPEG=1900)
    monkeypatch.setitem(sys.modules, "cv2", fake)
    MjpegCaptureSource("rtsp://cam/1", 640, 480, 30)._open_capture()
