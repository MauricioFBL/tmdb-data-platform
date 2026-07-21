"""Tests for ingestion.retries.rate_limiter."""

from __future__ import annotations

from ingestion.retries.rate_limiter import RateLimiter


def test_acquire_sleeps_remaining_interval_when_called_too_fast() -> None:
    clock_values = iter([0.0, 0.0, 0.05])
    sleeps: list[float] = []

    limiter = RateLimiter(
        max_requests_per_second=10.0,  # min interval = 0.1s
        clock=lambda: next(clock_values),
        sleep_fn=sleeps.append,
    )

    limiter.acquire()  # first call: no prior call, no sleep
    limiter.acquire()  # second call: 0.0s elapsed, needs to sleep ~0.1s

    assert sleeps == [0.1]


def test_acquire_does_not_sleep_when_called_slower_than_rate() -> None:
    clock_values = iter([0.0, 1.0])
    sleeps: list[float] = []

    limiter = RateLimiter(
        max_requests_per_second=10.0,  # min interval = 0.1s
        clock=lambda: next(clock_values),
        sleep_fn=sleeps.append,
    )

    limiter.acquire()
    limiter.acquire()  # 1.0s elapsed, well over the 0.1s min interval

    assert sleeps == []
