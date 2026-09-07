import pytest

from hydra_umc_vision_streamer.reconnect import (
    ConnectionState,
    ConnectionTracker,
    ReconnectPolicy,
    default_policy,
)


def test_delay_for_doubles_each_attempt_until_the_cap():
    policy = ReconnectPolicy(max_attempts=6, base_delay_s=1.0, max_delay_s=10.0)
    assert policy.delay_for(1) == 1.0
    assert policy.delay_for(2) == 2.0
    assert policy.delay_for(3) == 4.0
    assert policy.delay_for(4) == 8.0
    assert policy.delay_for(5) == 10.0  # capped, would otherwise be 16.0
    assert policy.delay_for(6) == 10.0


def test_delay_for_rejects_an_attempt_below_one():
    policy = default_policy()
    with pytest.raises(ValueError):
        policy.delay_for(0)


def test_policy_rejects_nonsensical_bounds():
    with pytest.raises(ValueError):
        ReconnectPolicy(max_attempts=0, base_delay_s=1.0, max_delay_s=10.0)
    with pytest.raises(ValueError):
        ReconnectPolicy(max_attempts=3, base_delay_s=0.0, max_delay_s=10.0)
    with pytest.raises(ValueError):
        ReconnectPolicy(max_attempts=3, base_delay_s=5.0, max_delay_s=1.0)


def test_tracker_starts_connected():
    tracker = ConnectionTracker(policy=default_policy())
    assert tracker.state is ConnectionState.CONNECTED
    assert tracker.attempt == 0


def test_on_disconnect_begins_reconnecting_at_attempt_one():
    tracker = ConnectionTracker(policy=default_policy())
    tracker.on_disconnect()
    assert tracker.state is ConnectionState.RECONNECTING
    assert tracker.attempt == 1


def test_on_reconnect_success_returns_to_connected():
    tracker = ConnectionTracker(policy=default_policy())
    tracker.on_disconnect()
    tracker.on_reconnect_success()
    assert tracker.state is ConnectionState.CONNECTED
    assert tracker.attempt == 0


def test_on_reconnect_failed_returns_the_real_scheduled_delay():
    policy = ReconnectPolicy(max_attempts=3, base_delay_s=1.0, max_delay_s=100.0)
    tracker = ConnectionTracker(policy=policy)
    tracker.on_disconnect()

    delay1 = tracker.on_reconnect_failed()
    assert delay1 == 1.0
    assert tracker.attempt == 2

    delay2 = tracker.on_reconnect_failed()
    assert delay2 == 2.0
    assert tracker.attempt == 3


def test_exhausting_max_attempts_gives_up_honestly_instead_of_retrying_forever():
    policy = ReconnectPolicy(max_attempts=2, base_delay_s=1.0, max_delay_s=100.0)
    tracker = ConnectionTracker(policy=policy)
    tracker.on_disconnect()

    tracker.on_reconnect_failed()  # attempt 1 fails
    result = tracker.on_reconnect_failed()  # attempt 2 (== max_attempts) fails

    assert result is None
    assert tracker.state is ConnectionState.GIVEN_UP


def test_on_reconnect_failed_before_a_disconnect_is_a_real_usage_error():
    tracker = ConnectionTracker(policy=default_policy())
    with pytest.raises(RuntimeError):
        tracker.on_reconnect_failed()


def test_a_full_disconnect_reconnect_cycle_is_deterministic():
    # The end-to-end real scenario: connected -> drops -> two failed
    # attempts with the exact expected backoff -> succeeds - a
    # simulated real link flake, fully reproducible.
    policy = ReconnectPolicy(max_attempts=5, base_delay_s=0.5, max_delay_s=8.0)
    tracker = ConnectionTracker(policy=policy)

    tracker.on_disconnect()
    assert tracker.on_reconnect_failed() == 0.5
    assert tracker.on_reconnect_failed() == 1.0
    tracker.on_reconnect_success()

    assert tracker.state is ConnectionState.CONNECTED
    assert tracker.attempt == 0
