import pytest

from hydra_umc_vision_streamer.buffer import FrameBuffer


def test_push_below_capacity_never_drops():
    buf: FrameBuffer[int] = FrameBuffer(max_size=4)
    for i in range(4):
        assert buf.push(i) is True
    assert buf.size == 4
    assert buf.dropped_count == 0


def test_push_past_capacity_drops_the_oldest_not_the_newest():
    buf: FrameBuffer[int] = FrameBuffer(max_size=3)
    for i in range(3):
        buf.push(i)
    result = buf.push(99)  # forces out item 0
    assert result is False
    assert buf.dropped_count == 1
    assert buf.drain() == [1, 2, 99]


def test_memory_never_grows_past_max_size_no_matter_how_many_pushes():
    # The real property this gate exists to prove: an arbitrarily slow
    # (or entirely absent) consumer must never let the buffer's real
    # size grow past its declared bound - simulating thousands of real
    # frames arriving with zero pops in between.
    buf: FrameBuffer[bytes] = FrameBuffer(max_size=8)
    fake_frame = b"x" * 1024
    for _ in range(50_000):
        buf.push(fake_frame)
        assert buf.size <= 8
    assert buf.size == 8
    assert buf.dropped_count == 50_000 - 8


def test_a_slow_consumer_popping_occasionally_still_stays_bounded():
    buf: FrameBuffer[int] = FrameBuffer(max_size=5)
    popped = []
    for i in range(1000):
        buf.push(i)
        assert buf.size <= 5
        if i % 97 == 0:  # a "slow consumer" popping much less often than pushes arrive
            item = buf.pop()
            if item is not None:
                popped.append(item)
    assert buf.size <= 5
    assert buf.dropped_count > 0  # a real slow consumer really did lose frames


def test_pop_on_empty_buffer_returns_none_not_an_exception():
    buf: FrameBuffer[int] = FrameBuffer(max_size=2)
    assert buf.pop() is None


def test_is_full_reflects_real_state():
    buf: FrameBuffer[int] = FrameBuffer(max_size=2)
    assert buf.is_full is False
    buf.push(1)
    assert buf.is_full is False
    buf.push(2)
    assert buf.is_full is True


def test_drain_empties_the_buffer_and_returns_fifo_order():
    buf: FrameBuffer[int] = FrameBuffer(max_size=3)
    buf.push(1)
    buf.push(2)
    assert buf.drain() == [1, 2]
    assert buf.size == 0
    assert buf.drain() == []


def test_max_size_must_be_positive():
    with pytest.raises(ValueError):
        FrameBuffer(max_size=0)
    with pytest.raises(ValueError):
        FrameBuffer(max_size=-1)
