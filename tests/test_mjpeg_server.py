import pytest

from hydra_umc_vision_streamer.mjpeg_server import MjpegCaptureSource


def _source():
    return MjpegCaptureSource(device="0", width=640, height=480, fps=30, buffer_size=4)


def test_start_raises_clear_error_without_opencv():
    # opencv-python (cv2) is not installed on this development machine -
    # the real, honest state this module must degrade to cleanly, same
    # pattern as hailo_runtime.py's own hailort import (test_hailo_runtime.py).
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
