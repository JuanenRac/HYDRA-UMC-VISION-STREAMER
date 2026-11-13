# =============================================================================
# HYDRA-UMC-VISION-STREAMER - tests/test_simulation_bench.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Simulation bench: the real capture loop, buffer and frame metadata against a synthetic camera that fails the way cameras fail.

The camera is a stand-in for `cv2.VideoCapture` that follows a script drawn from a fixed seed: frames of synthetic JPEG bytes, bursts of failed reads that are only
jitter, a long silence that is a disconnect, a device that comes back at the first try or only after several, and one that never comes back. The capture loop under
test is the real one, with its real reconnect schedule made fast. Nothing here says how a real camera, a real cable or a real network behave: that needs the camera."""
from __future__ import annotations

import random
import struct
import sys
import time
import types

import pytest

from hydra_umc_vision_streamer import mjpeg_server
from hydra_umc_vision_streamer.buffer import FrameBuffer
from hydra_umc_vision_streamer.frame_meta import frame_meta, jpeg_size
from hydra_umc_vision_streamer.mjpeg_server import Frame, MjpegCaptureSource
from hydra_umc_vision_streamer.reconnect import ConnectionState, ConnectionTracker, ReconnectPolicy

SEED = 20260101


def make_jpeg(width: int, height: int, payload: bytes = b"") -> bytes:
    """The start of a JPEG with a real frame header (SOF0), enough for the size to be read; the rest is whatever the scene carries."""
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof + payload + b"\xff\xd9"


class _Encoded:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def tobytes(self) -> bytes:
        return self._data


class _Scene:
    def __init__(self, seed: int) -> None:
        self.seed = seed


class Script:
    """What the camera does on each read, per device instance: a list of 'ok' / 'fail' decided in advance."""

    def __init__(self, per_instance: list[list[str]], opens: list[bool] | None = None) -> None:
        self.per_instance = per_instance
        self.opens = opens or [True] * len(per_instance)
        self.constructed = 0
        self.released = 0
        self.frames = 0


def install(monkeypatch: pytest.MonkeyPatch, script: Script) -> None:
    class Capture:
        def __init__(self, index, backend) -> None:
            self.number = script.constructed
            script.constructed += 1
            self.reads = 0

        def isOpened(self) -> bool:  # noqa: N802 - the name of the real one
            return script.opens[min(self.number, len(script.opens) - 1)]

        def read(self):
            steps = script.per_instance[min(self.number, len(script.per_instance) - 1)]
            step = steps[min(self.reads, len(steps) - 1)]
            self.reads += 1
            if step == "fail":
                return False, None
            time.sleep(0.002)
            script.frames += 1
            return True, _Scene(script.frames)

        def set(self, prop, value) -> bool:
            return True

        def release(self) -> None:
            script.released += 1

    def imencode(ext, frame, params):
        rng = random.Random(frame.seed)
        return True, _Encoded(make_jpeg(640, 480, bytes(rng.randrange(256) for _ in range(rng.randrange(0, 64)))))

    fake = types.SimpleNamespace(VideoCapture=Capture, CAP_V4L2=200, CAP_ANY=0, CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5, IMWRITE_JPEG_QUALITY=1, imencode=imencode)
    monkeypatch.setitem(sys.modules, "cv2", fake)
    monkeypatch.setattr(mjpeg_server, "default_policy", lambda: ReconnectPolicy(max_attempts=4, base_delay_s=0.01, max_delay_s=0.02))
    monkeypatch.setattr(mjpeg_server, "RECONNECT_AFTER_CONSECUTIVE_FAILURES", 4)
    monkeypatch.setattr(time, "sleep", lambda seconds: _real_sleep(min(seconds, 0.002)))


_real_sleep = time.sleep


def run_source(script: Script, monkeypatch: pytest.MonkeyPatch, *, until, timeout: float = 5.0) -> MjpegCaptureSource:
    install(monkeypatch, script)
    source = MjpegCaptureSource(device="0", width=640, height=480, fps=30, buffer_size=4)
    source.start()
    deadline = time.monotonic() + timeout
    try:
        while not until(source) and time.monotonic() < deadline:
            _real_sleep(0.005)
    finally:
        source.stop()
    return source


def test_a_healthy_camera_streams_numbered_frames_with_the_size_the_scene_has(monkeypatch) -> None:
    source = run_source(Script([["ok"]]), monkeypatch, until=lambda s: s.frames_captured >= 30)
    assert source.frames_captured >= 30 and source.health()["state"] in ("streaming", "stalled")
    frame = source.latest_frame()
    assert frame is not None and jpeg_size(frame.payload) == (640, 480)
    meta = frame_meta(frame, "cam-1")
    assert meta is not None and meta["width"] == 640 and meta["height"] == 480 and meta["source_id"] == "cam-1" and meta["session_id"] == source.session_id


def test_jitter_that_stays_under_the_threshold_never_costs_a_reconnect_or_a_session(monkeypatch) -> None:
    rng = random.Random(SEED)
    steps: list[str] = []
    for _ in range(40):
        steps += ["ok"] * rng.randint(1, 4) + ["fail"] * rng.randint(1, 3)  # at most three bad reads in a row; four are a disconnect
    script = Script([steps + ["ok"] * 200])
    session_at_start = []

    install(monkeypatch, script)
    source = MjpegCaptureSource(device="0", width=640, height=480, fps=30)
    session_at_start.append(source.session_id)
    source.start()
    deadline = time.monotonic() + 5
    while source.frames_captured < 60 and time.monotonic() < deadline:
        _real_sleep(0.005)
    source.stop()
    assert source.frames_captured >= 60 and script.constructed == 1 and source.session_id == session_at_start[0]


def test_a_long_silence_is_a_disconnect_the_device_is_reopened_and_the_session_changes(monkeypatch) -> None:
    script = Script([["ok"] * 5 + ["fail"], ["ok"]])
    seen = []

    install(monkeypatch, script)
    source = MjpegCaptureSource(device="0", width=640, height=480, fps=30)
    first_session = source.session_id
    source.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        frame = source.latest_frame()
        if frame is not None:
            seen.append((frame.session_id, frame.frame_id))
        if script.constructed >= 2 and source.frames_captured > 12:
            break
        _real_sleep(0.005)
    source.stop()
    assert script.constructed >= 2 and script.released >= 1
    assert source.session_id != first_session
    sessions = [s for s, _ in seen]
    assert first_session in sessions and source.session_id in sessions
    ids = [i for _, i in seen]
    assert ids == sorted(ids)  # numbering never goes backwards across the reconnect


def test_a_device_that_needs_several_tries_to_come_back_is_reopened_in_the_end(monkeypatch) -> None:
    script = Script([["fail"], ["ok"], ["ok"], ["ok"]], opens=[True, False, False, True])
    source = run_source(script, monkeypatch, until=lambda s: s.frames_captured >= 5)
    assert source.frames_captured >= 5 and script.constructed >= 4 and not source.gave_up.is_set()
    assert source.health()["last_error"] is None or "consecutive failed reads" in (source.health()["last_error"] or "")


def test_a_device_that_never_comes_back_is_given_up_with_a_reason_and_the_health_says_so(monkeypatch) -> None:
    script = Script([["fail"]], opens=[True, False])
    source = run_source(script, monkeypatch, until=lambda s: s.gave_up.is_set())
    assert source.gave_up.is_set()
    health = source.health()
    assert health == {**health, "state": "given_up", "healthy": False, "frames_captured": 0}
    assert "gave up reconnecting" in (health["last_error"] or "")
    assert source.wait_for_frame(0, timeout=0.2) is None


def test_the_buffer_keeps_only_the_newest_frames_under_a_burst_nobody_reads(monkeypatch) -> None:
    source = run_source(Script([["ok"]]), monkeypatch, until=lambda s: s.frames_captured >= 80)
    assert source.frames_captured >= 80
    latest = source.latest_frame()
    assert latest is not None and latest.frame_id >= source.frames_captured - 1
    assert source._buffer.size <= 4  # noqa: SLF001 - the bound is the point


def test_a_slow_viewer_gets_the_newest_frame_and_never_blocks_the_camera(monkeypatch) -> None:
    script = Script([["ok"]])
    install(monkeypatch, script)
    source = MjpegCaptureSource(device="0", width=640, height=480, fps=30)
    source.start()
    try:
        last = 0
        taken = []
        for _ in range(5):
            frame = source.wait_for_frame(last, timeout=2.0)
            assert frame is not None
            taken.append(frame.frame_id)
            last = frame.frame_id
            _real_sleep(0.05)  # a viewer far slower than the camera
        assert taken == sorted(set(taken)) and taken[-1] > taken[0] + 4  # it skipped frames instead of falling behind
    finally:
        source.stop()


# ----------------------------------------------------------------------------------------------------------------------- the pieces
def test_the_reader_of_jpeg_sizes_never_raises_whatever_it_is_given() -> None:
    rng = random.Random(SEED)
    good = make_jpeg(320, 240, b"scene")
    assert jpeg_size(good) == (320, 240)
    for _ in range(2000):
        kind = rng.randrange(4)
        if kind == 0:
            data = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 80)))
        elif kind == 1:
            cut = rng.randrange(0, len(good))
            data = good[:cut]
        elif kind == 2:
            data = bytearray(good)
            data[rng.randrange(len(data))] = rng.randrange(256)
            data = bytes(data)
        else:
            data = b"\xff\xd8" + bytes(rng.choice([0xFF, 0xC0, 0xE0, 0x00, 0x02, 0x11]) for _ in range(rng.randrange(0, 40)))
        result = jpeg_size(data)
        assert result is None or (isinstance(result, tuple) and len(result) == 2 and all(isinstance(v, int) and v >= 1 for v in result))


def test_a_frame_whose_size_cannot_be_read_has_no_metadata_and_a_hostile_session_is_cleaned() -> None:
    assert frame_meta(Frame(b"not a jpeg", 1, "s", 0.0)) is None
    meta = frame_meta(Frame(make_jpeg(64, 48), 7, "ok.session:1-x", 1_800_000_000.0), "cam 1")
    assert meta is not None and meta["frame_id"] == "7" and meta["session_id"] == "ok.session:1-x" and "source_id" not in meta
    dirty = frame_meta(Frame(make_jpeg(64, 48), 7, "bad session/\n<script>", 1_800_000_000.0), "cam-1")
    assert dirty is not None and "<" not in str(dirty.get("session_id", "")) and "\n" not in str(dirty.get("session_id", ""))


def test_the_reconnect_schedule_doubles_up_to_its_cap_and_ends_in_a_given_up_state() -> None:
    policy = ReconnectPolicy(max_attempts=5, base_delay_s=0.5, max_delay_s=3.0)
    assert [policy.delay_for(n) for n in range(1, 6)] == [0.5, 1.0, 2.0, 3.0, 3.0]
    tracker = ConnectionTracker(policy)
    tracker.on_disconnect()
    delays = []
    while (delay := tracker.on_reconnect_failed()) is not None:
        delays.append(delay)
    assert delays == [0.5, 1.0, 2.0, 3.0] and tracker.state is ConnectionState.GIVEN_UP
    with pytest.raises(RuntimeError):
        tracker.on_reconnect_failed()
    for bad in ((0, 1.0, 2.0), (3, 0.0, 1.0), (3, 2.0, 1.0)):
        with pytest.raises(ValueError):
            ReconnectPolicy(*bad)
    with pytest.raises(ValueError):
        policy.delay_for(0)


def test_the_buffer_drops_the_oldest_when_it_is_full_and_says_so() -> None:
    buffer: FrameBuffer[int] = FrameBuffer(max_size=3)
    results = [buffer.push(n) for n in range(6)]
    assert results == [True, True, True, False, False, False] and buffer.dropped_count == 3
    assert buffer.size == 3 and buffer.is_full and buffer.peek_latest() == 5
    assert buffer.pop() == 3 and buffer.drain() == [4, 5] and buffer.pop() is None and buffer.peek_latest() is None
    with pytest.raises(ValueError):
        FrameBuffer(max_size=0)
