"""Exponential backoff/retry policy for TMDB HTTP 429 responses."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from ingestion.tmdb_client.exceptions import TMDBRateLimitExceededError


class _RetryableResponse(Protocol):
    """The subset of requests.Response this retry loop actually touches.

    Declared as read-only properties, not plain attributes: requests.Response
    exposes ``text`` as a read-only @property, and a plain attribute
    declaration here would require read-write access, which Response can't
    structurally satisfy.
    """

    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...


ResponseT = TypeVar("ResponseT", bound=_RetryableResponse)


@dataclass(frozen=True)
class RetryConfig:
    """Tunables for :func:`retry_with_backoff`."""

    max_retries: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter: bool = True


def compute_backoff_delay(
    attempt: int, config: RetryConfig, retry_after: float | None = None
) -> float:
    """Compute the delay before the next retry attempt.

    A server-supplied ``Retry-After`` value always takes precedence over the
    computed exponential delay, since TMDB (if it sends the header) knows its
    own rate-limit window better than a client-side guess.
    """
    if retry_after is not None:
        return retry_after

    delay: float = min(config.base_delay_seconds * (2**attempt), config.max_delay_seconds)
    if config.jitter:
        delay *= random.uniform(0.8, 1.2)
    return delay


def retry_with_backoff(
    func: Callable[[], ResponseT],
    is_retryable: Callable[[ResponseT], bool],
    get_retry_after: Callable[[ResponseT], float | None],
    config: RetryConfig = RetryConfig(),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ResponseT:
    """Call ``func`` and retry while ``is_retryable`` reports 429s.

    Returns the response as-is once it is no longer retryable, whatever its
    status code — interpreting non-429 4xx/5xx responses is the caller's
    responsibility, not this loop's.
    """
    attempt = 0
    response = func()
    while is_retryable(response):
        if attempt >= config.max_retries:
            retry_after = get_retry_after(response)
            raise TMDBRateLimitExceededError(
                status_code=response.status_code,
                message=f"Rate limit retries exhausted after {config.max_retries} attempts",
                retry_after=retry_after,
                response_body=response.text,
            )
        delay = compute_backoff_delay(attempt, config, get_retry_after(response))
        sleep_fn(delay)
        attempt += 1
        response = func()
    return response
