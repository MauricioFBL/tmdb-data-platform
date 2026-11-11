"""Tests for ingestion.retries.backoff."""

from __future__ import annotations

import pytest

from ingestion.retries.backoff import RetryConfig, compute_backoff_delay, retry_with_backoff
from ingestion.tests.conftest import FakeResponse
from ingestion.tmdb_client.exceptions import TMDBRateLimitExceededError


def test_compute_backoff_delay_grows_exponentially_without_jitter() -> None:
    config = RetryConfig(base_delay_seconds=1.0, max_delay_seconds=60.0, jitter=False)
    assert compute_backoff_delay(0, config) == 1.0
    assert compute_backoff_delay(1, config) == 2.0
    assert compute_backoff_delay(2, config) == 4.0


def test_compute_backoff_delay_caps_at_max_delay() -> None:
    config = RetryConfig(base_delay_seconds=1.0, max_delay_seconds=5.0, jitter=False)
    assert compute_backoff_delay(10, config) == 5.0


def test_compute_backoff_delay_retry_after_overrides_computed_delay() -> None:
    config = RetryConfig(base_delay_seconds=1.0, max_delay_seconds=60.0, jitter=False)
    assert compute_backoff_delay(5, config, retry_after=2.5) == 2.5


def test_retry_with_backoff_recovers_after_single_429() -> None:
    responses = [FakeResponse(status_code=429, text=""), FakeResponse(status_code=200, text="ok")]
    calls = iter(responses)
    sleeps: list[float] = []

    result = retry_with_backoff(
        func=lambda: next(calls),
        is_retryable=lambda r: r.status_code == 429,
        get_retry_after=lambda r: None,
        config=RetryConfig(max_retries=3, base_delay_seconds=0.01, jitter=False),
        sleep_fn=sleeps.append,
    )

    assert result.status_code == 200
    assert len(sleeps) == 1


def test_retry_with_backoff_raises_once_retries_exhausted() -> None:
    def always_429() -> FakeResponse:
        return FakeResponse(status_code=429, text="rate limited")

    with pytest.raises(TMDBRateLimitExceededError):
        retry_with_backoff(
            func=always_429,
            is_retryable=lambda r: r.status_code == 429,
            get_retry_after=lambda r: None,
            config=RetryConfig(max_retries=2, base_delay_seconds=0.01, jitter=False),
            sleep_fn=lambda _seconds: None,
        )


def test_retry_with_backoff_returns_non_retryable_response_immediately() -> None:
    response = FakeResponse(status_code=404, text="not found")
    result = retry_with_backoff(
        func=lambda: response,
        is_retryable=lambda r: r.status_code == 429,
        get_retry_after=lambda r: None,
        sleep_fn=lambda _seconds: None,
    )
    assert result is response
