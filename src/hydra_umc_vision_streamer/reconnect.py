# =============================================================================
# HYDRA-UMC-VISION-STREAMER - src/hydra_umc_vision_streamer/reconnect.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real, deterministic reconnection policy for a camera capture source
(or a MediaMTX relay link) that drops - independent of the real
V4L2/GStreamer runtime and physical hardware this project doesn't have.

A live capture source WILL disconnect sometimes (a USB camera resets, a
relay link blips) - what matters is that reconnection attempts back off
deterministically instead of hammering a device that just failed, and
that the connection's own state (connected / reconnecting / given up)
is real, inspectable state a caller can act on, not an implicit detail
buried in a retry loop. This mirrors the same real backoff pattern
already used elsewhere in the ecosystem (see
HYDRA-UMC-NODE-HEALING/src/watchdog/retry.go) - no jitter, so the
schedule is exactly reproducible in a test.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


@dataclass(frozen=True)
class ReconnectPolicy:
    max_attempts: int
    base_delay_s: float
    max_delay_s: float

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError(f"max_attempts must be positive, got {self.max_attempts}")
        if self.base_delay_s <= 0:
            raise ValueError(f"base_delay_s must be positive, got {self.base_delay_s}")
        if self.max_delay_s < self.base_delay_s:
            raise ValueError("max_delay_s must be >= base_delay_s")

    def delay_for(self, attempt: int) -> float:
        """The real, deterministic backoff for the Nth reconnect attempt
        (1-indexed): doubles each time, capped at `max_delay_s`. No
        jitter - a caller (or a test) can compute the exact schedule."""
        if attempt < 1:
            raise ValueError(f"attempt must be >= 1, got {attempt}")
        return min(self.base_delay_s * (2 ** (attempt - 1)), self.max_delay_s)


def default_policy() -> ReconnectPolicy:
    return ReconnectPolicy(max_attempts=5, base_delay_s=0.5, max_delay_s=8.0)


class ConnectionState(enum.Enum):
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    GIVEN_UP = "given_up"


@dataclass
class ConnectionTracker:
    """Real, minimal connection-state machine for one camera source.
    Deliberately does not sleep or touch a real socket/device itself -
    it only tracks state and tells a caller how long to wait, which is
    what makes the whole reconnect schedule testable without a real
    camera or a real clock.
    """

    policy: ReconnectPolicy
    state: ConnectionState = ConnectionState.CONNECTED
    attempt: int = 0

    def on_disconnect(self) -> None:
        """A previously-connected source just dropped - the first
        reconnect attempt begins."""
        self.state = ConnectionState.RECONNECTING
        self.attempt = 1

    def on_reconnect_success(self) -> None:
        self.state = ConnectionState.CONNECTED
        self.attempt = 0

    def on_reconnect_failed(self) -> float | None:
        """Records a failed reconnect attempt. Returns the delay before
        the NEXT attempt, or None if `max_attempts` was just exhausted
        (state becomes GIVEN_UP - a real, honest terminal outcome, not
        an infinite retry loop)."""
        if self.state != ConnectionState.RECONNECTING:
            raise RuntimeError(f"on_reconnect_failed() called while state is {self.state}")
        if self.attempt >= self.policy.max_attempts:
            self.state = ConnectionState.GIVEN_UP
            return None
        delay = self.policy.delay_for(self.attempt)
        self.attempt += 1
        return delay
