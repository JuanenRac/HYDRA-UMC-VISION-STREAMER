# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/buffer.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""A real, bounded per-camera frame buffer, independent of the real
GStreamer/V4L2 runtime this project doesn't have in this environment.

The actual gap this closes: a live capture source produces frames at a
fixed rate regardless of whether anything is consuming them - a relay
(MediaMTX) or a slow downstream consumer (a saturated network link, a
Hailo-8 inference stage falling behind) cannot be allowed to make this
process's own memory grow without bound just because it can't keep up.
`FrameBuffer` is the real policy: a fixed-capacity ring buffer that
drops the OLDEST frame once full, not the newest - live video wants the
freshest frame available, never a growing backlog of stale ones. This
is real, deterministic, and fully testable in-process: pushing far more
frames than a "slow consumer" ever pops proves memory stays bounded
without needing an actual camera or network socket to demonstrate it.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class FrameBuffer(Generic[T]):
    """A bounded FIFO queue of at most `max_size` items. `push()` past
    capacity silently drops the OLDEST item (not the newest) and counts
    it - the real, honest behavior of a live video relay under
    backpressure, not a queue that blocks or grows forever.
    """

    max_size: int
    _items: deque[T] = field(init=False, repr=False)
    dropped_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.max_size <= 0:
            raise ValueError(f"max_size must be positive, got {self.max_size}")
        self._items = deque()

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def is_full(self) -> bool:
        return len(self._items) >= self.max_size

    def push(self, item: T) -> bool:
        """Adds `item`. Returns True if it fit without dropping anything,
        False if pushing it forced the oldest item out - the real signal
        a caller uses to know a slow consumer just cost it a frame."""
        dropped = False
        if len(self._items) >= self.max_size:
            self._items.popleft()
            self.dropped_count += 1
            dropped = True
        self._items.append(item)
        return not dropped

    def pop(self) -> T | None:
        """Removes and returns the oldest item, or None if empty - what a
        (possibly slow) consumer calls to drain the buffer."""
        if not self._items:
            return None
        return self._items.popleft()

    def drain(self) -> list[T]:
        """Removes and returns every buffered item, oldest first."""
        items = list(self._items)
        self._items.clear()
        return items
