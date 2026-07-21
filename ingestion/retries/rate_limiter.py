"""Client-side request pacing.

This is a courtesy ceiling, not a correctness guarantee: TMDB's rate limit is
informal and undocumented (see docs/source-analysis/tmdb-api-overview.md), so
this only paces the sustained call rate of a single-threaded caller.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    """Sleeps as needed to keep consecutive ``acquire()`` calls spaced apart."""

    def __init__(
        self,
        max_requests_per_second: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval_seconds = 1.0 / max_requests_per_second
        self._clock = clock
        self._sleep_fn = sleep_fn
        self._last_call_time: float | None = None

    def acquire(self) -> None:
        """Block (via ``sleep_fn``) until the minimum interval has elapsed."""
        now = self._clock()
        if self._last_call_time is not None:
            elapsed = now - self._last_call_time
            remaining = self._min_interval_seconds - elapsed
            if remaining > 0:
                self._sleep_fn(remaining)
                now = self._clock()
        self._last_call_time = now
