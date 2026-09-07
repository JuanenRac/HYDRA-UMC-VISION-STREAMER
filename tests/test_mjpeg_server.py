import sys
import time
import types

import pytest

from hydra_umc_vision_streamer import mjpeg_server
from hydra_umc_vision_streamer.mjpeg_server import MjpegCaptureSource, discover_usb_devices
from hydra_umc_vision_streamer.reconnect import ReconnectPolicy


def _source():
    return MjpegCaptureSource(device="0", width=640, height=480, fps=30, buffer_size=4)


def test_start_raises_clear_error_without_opencv(monkeypatch):
    # opencv-python (cv2) isn't guaranteed to be installed wherever this
    # test runs (it wasn't on the machine this test was first written
    # against; it IS on at least one real dev machine since - forcing
    # the lazy `import cv2` to fail, same as
    # test_discover_usb_devices_raises_clear_error_without_opencv below,
    # keeps this real degradation path covered regardless) - the real,
    # honest state this module must degrade to cleanly either way, same
    # pattern as hailo_runtime.py's own hailort import (test_hailo_runtime.py).
    monkeypatch.setitem(sys.modules, "cv2", None)
    source = _source()
    with pytest.raises(RuntimeError, match="opencv-python"):
        source.start()


def test_wait_for_frame_returns_none_on_timeout_with_no_frames():
    # No capture thread running (start() never called, deliberately) -
    # wait_for_frame must still return cleanly rather than block forever
    # when nothing is ever pushed.
    source = _source()
    assert source.wait_for_frame(last_seen=0, timeout=0.05) is None


def test_wait_for_frame_returns_pushed_frame_without_a_real_camera():
    # Real capture loop bypassed entirely - pushes directly through the
    # same buffer/condition wait_for_frame reads, proving the real
    # producer/consumer handoff works independent of cv2/hardware.
    source = _source()
    frame = b"\xff\xd8fake-jpeg-bytes\xff\xd9"
    with source._new_frame:
        source._buffer.push(frame)
        source.frames_captured += 1
        source._new_frame.notify_all()

    result = source.wait_for_frame(last_seen=0, timeout=1.0)
    assert result == frame


def test_wait_for_frame_returns_latest_of_several_pushed_frames():
    # Real backpressure behaviour (buffer.py's own FrameBuffer, reused
    # here rather than reinvented): a slow consumer that only calls
    # wait_for_frame once after several frames arrived gets the LATEST
    # one, never a stale backlog - the same "freshest frame always wins"
    # policy FrameBuffer's own docstring documents.
    source = _source()
    frames = [b"frame-%d" % i for i in range(3)]
    with source._new_frame:
        for frame in frames:
            source._buffer.push(frame)
        source.frames_captured += len(frames)
        source._new_frame.notify_all()

    result = source.wait_for_frame(last_seen=0, timeout=1.0)
    assert result == frames[-1]


class _FakeFrame:
    """Minimal stand-in for a real numpy frame - discover_usb_devices()
    only ever reads `.shape[:2]`, matching real OpenCV's own
    (height, width, channels) convention."""

    def __init__(self, height: int, width: int):
        self.shape = (height, width, 3)


class _FakeVideoCapture:
    """Fake cv2.VideoCapture standing in for real hardware - a real index
    "opens" (isOpened() True, read() returns a real-shaped frame) only if
    it's in `available_indices`, everything else behaves exactly like a
    real absent/disconnected device (isOpened() False). Tracks release()
    calls so the test can assert every probed device - found or not - is
    actually released, not leaked."""

    released_indices: list[int] = []

    def __init__(self, index, backend, available_indices=frozenset({0}), sizes=None):
        self._index = index
        self._opened = index in available_indices
        self._size = (sizes or {}).get(index, (480, 640))

    def isOpened(self):
        return self._opened

    def read(self):
        if not self._opened:
            return False, None
        height, width = self._size
        return True, _FakeFrame(height, width)

    def release(self):
        _FakeVideoCapture.released_indices.append(self._index)


def _install_fake_cv2(monkeypatch, available_indices=frozenset({0}), sizes=None):
    _FakeVideoCapture.released_indices = []

    def factory(index, backend):
        return _FakeVideoCapture(index, backend, available_indices=available_indices, sizes=sizes)

    fake_cv2 = types.SimpleNamespace(VideoCapture=factory, CAP_V4L2=200, CAP_ANY=0)
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)


def test_discover_usb_devices_finds_only_real_working_indices(monkeypatch):
    # Indices 0 and 2 "have" a real camera (isOpened + a real frame read
    # succeeds); 1, 3, 4 don't - same false-positive class real hardware
    # testing already ran into elsewhere in this project (isOpened() can
    # lie on some backends; a real frame read is the honest check).
    _install_fake_cv2(monkeypatch, available_indices=frozenset({0, 2}), sizes={0: (720, 1280), 2: (1080, 1920)})

    devices = discover_usb_devices(max_index=5)

    assert devices == [
        {"index": 0, "available": True, "width": 1280, "height": 720},
        {"index": 2, "available": True, "width": 1920, "height": 1080},
    ]
    # Every probed index (0-4, found or not) gets released - no held-open
    # device left behind after a discovery scan.
    assert _FakeVideoCapture.released_indices == [0, 1, 2, 3, 4]


def test_discover_usb_devices_returns_empty_list_when_none_available(monkeypatch):
    # No real camera anywhere in the probed range - a real, honest empty
    # list, not an error (the caller - HYDRA-UMC-SERVER's own "Discover
    # USB Devices" button - shows "none found", not a failure).
    _install_fake_cv2(monkeypatch, available_indices=frozenset())

    devices = discover_usb_devices(max_index=3)

    assert devices == []
    assert _FakeVideoCapture.released_indices == [0, 1, 2]


def test_discover_usb_devices_raises_clear_error_without_opencv(monkeypatch):
    # Real cv2 IS installed in this dev environment (unlike
    # test_start_raises_clear_error_without_opencv's own assumption
    # above) - force the lazy `import cv2` to fail so the clean-
    # degradation path itself stays covered regardless of what's
    # actually installed on whichever machine runs this test.
    monkeypatch.setitem(sys.modules, "cv2", None)
    with pytest.raises(RuntimeError, match="opencv-python"):
        discover_usb_devices()


# ---------------------------------------------------------------------------
# Real reconnect wiring in _capture_loop() - found in an ecosystem-wide
# software-improvements audit: reconnect.py's own tested ConnectionTracker
# was wired only into the `stream simulate` CLI path, never into this
# live capture loop.
# ---------------------------------------------------------------------------


class _FakeEncodedFrame:
    def tobytes(self) -> bytes:
        return b"\xff\xd8fake-jpeg-bytes\xff\xd9"


class _FlakyFakeVideoCapture:
    """A fake `cv2.VideoCapture` that starts healthy, then goes fully dead
    (`isOpened()` stays True but `read()` always fails) - the same real
    "device silently stopped producing frames" failure a live UVC/RTSP
    source can hit - until a real NEW instance has been constructed (a
    real reconnect calls `cv2.VideoCapture(...)` again, exactly like
    `_open_capture()` does), at which point reads succeed again. Tracks
    every constructed instance and every `release()` call, so the test
    can assert a real release-and-reopen cycle happened, not just a
    longer sleep on the same dead handle."""

    instances: list["_FlakyFakeVideoCapture"] = []
    released_count = 0

    def __init__(self, index, backend):
        self._my_index = len(_FlakyFakeVideoCapture.instances)
        _FlakyFakeVideoCapture.instances.append(self)

    def isOpened(self):
        return True

    def read(self):
        if self._my_index > 0:  # the very first instance is already dead
            return True, _FakeFrame(480, 640)
        return False, None

    def set(self, prop, value):
        return True

    def release(self):
        _FlakyFakeVideoCapture.released_count += 1


class _DisconnectsForeverVideoCapture:
    """A fake `cv2.VideoCapture` for the real "gives up" case: the
    initial open succeeds but never produces a frame, and every
    subsequent real reopen attempt genuinely fails (`isOpened()` False,
    e.g. a real hardware disconnect) - the actual persisted-disconnect
    case `ConnectionTracker`'s own `GIVEN_UP` terminal state exists for."""

    instances: list["_DisconnectsForeverVideoCapture"] = []

    def __init__(self, index, backend):
        self._my_index = len(_DisconnectsForeverVideoCapture.instances)
        _DisconnectsForeverVideoCapture.instances.append(self)

    def isOpened(self):
        return self._my_index == 0

    def read(self):
        return False, None

    def set(self, prop, value):
        return True

    def release(self):
        pass


def test_capture_loop_reconnects_after_sustained_read_failures(monkeypatch):
    _FlakyFakeVideoCapture.instances = []
    _FlakyFakeVideoCapture.released_count = 0
    fake_cv2 = types.SimpleNamespace(
        VideoCapture=lambda index, backend: _FlakyFakeVideoCapture(index, backend),
        CAP_V4L2=200, CAP_ANY=0,
        CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5,
        IMWRITE_JPEG_QUALITY=1,
        imencode=lambda ext, frame, params: (True, _FakeEncodedFrame()),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    # Real backoff schedule (ConnectionTracker), just fast enough this
    # test doesn't spend real wall-clock time on it.
    monkeypatch.setattr(
        mjpeg_server, "default_policy",
        lambda: ReconnectPolicy(max_attempts=5, base_delay_s=0.01, max_delay_s=0.02),
    )
    # A couple of failed reads is "ordinary jitter" here, not a real
    # disconnect yet - keeps the test from needing many read cycles
    # before the real reconnect path even engages.
    monkeypatch.setattr(mjpeg_server, "RECONNECT_AFTER_CONSECUTIVE_FAILURES", 2)

    source = _source()
    source.start()
    try:
        deadline = time.monotonic() + 5.0
        while source.frames_captured == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert source.frames_captured > 0, f"never recovered a real frame - last_error={source.last_error!r}"
    finally:
        source.stop()

    # A real release-and-reopen cycle happened - not just a longer sleep
    # on the same dead handle. At least the first (dead) instance and one
    # real reconnect attempt were both constructed and released.
    assert len(_FlakyFakeVideoCapture.instances) >= 2
    assert _FlakyFakeVideoCapture.released_count >= 1


def test_capture_loop_gives_up_and_stops_after_max_reconnect_attempts(monkeypatch):
    _DisconnectsForeverVideoCapture.instances = []
    fake_cv2 = types.SimpleNamespace(
        VideoCapture=lambda index, backend: _DisconnectsForeverVideoCapture(index, backend),
        CAP_V4L2=200, CAP_ANY=0,
        CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5,
        IMWRITE_JPEG_QUALITY=1,
        imencode=lambda ext, frame, params: (True, _FakeEncodedFrame()),
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)
    monkeypatch.setattr(
        mjpeg_server, "default_policy",
        lambda: ReconnectPolicy(max_attempts=2, base_delay_s=0.01, max_delay_s=0.02),
    )
    monkeypatch.setattr(mjpeg_server, "RECONNECT_AFTER_CONSECUTIVE_FAILURES", 2)

    source = _source()
    source.start()
    try:
        deadline = time.monotonic() + 5.0
        while source._thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not source._thread.is_alive(), "capture thread never gave up and stopped"
        assert source.frames_captured == 0
        assert source.last_error is not None and "gave up" in source.last_error
        assert source._stop.is_set()
        # A real reopen was actually attempted (not just one giant sleep) -
        # the first instance (initial open) plus at least one real
        # reconnect attempt.
        assert len(_DisconnectsForeverVideoCapture.instances) >= 2
    finally:
        source.stop()
