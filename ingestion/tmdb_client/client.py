"""Thin HTTP client for the TMDB API (v3 base URL, v4 bearer-token auth)."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, Final

import requests

from ingestion.retries.backoff import RetryConfig, retry_with_backoff
from ingestion.retries.rate_limiter import RateLimiter
from ingestion.tmdb_client.exceptions import TMDBConfigError

DEFAULT_BASE_URL: Final[str] = "https://api.themoviedb.org/3"
_ACCESS_TOKEN_ENV_VAR: Final[str] = "TMDB_API_READ_ACCESS_TOKEN"


class TMDBClient:
    """Base HTTP client: bearer-token auth, retry/backoff, rate limiting."""

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        retry_config: RetryConfig | None = None,
        rate_limiter: RateLimiter | None = None,
        timeout_seconds: float = 10.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        token = access_token or os.environ.get(_ACCESS_TOKEN_ENV_VAR)
        if not token:
            raise TMDBConfigError(
                f"TMDB access token not set — pass access_token or set {_ACCESS_TOKEN_ENV_VAR}"
            )
        self._access_token = token
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._retry_config = retry_config or RetryConfig()
        self._rate_limiter = rate_limiter or RateLimiter()
        self._timeout_seconds = timeout_seconds
        self._sleep_fn = sleep_fn

    def get(self, path: str, params: dict[str, Any] | None = None) -> requests.Response:
        """Issue a GET request with bearer auth, retry/backoff, and rate limiting.

        Returns the raw ``requests.Response`` untouched — callers that need
        the parsed body call ``.json()`` themselves; this lets callers that
        need the raw bytes (e.g. a raw-layer writer) persist them unmodified.
        """
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._access_token}"}

        def do_request() -> requests.Response:
            self._rate_limiter.acquire()
            return self._session.get(
                url, headers=headers, params=params, timeout=self._timeout_seconds
            )

        def is_retryable(response: requests.Response) -> bool:
            return response.status_code == 429

        def get_retry_after(response: requests.Response) -> float | None:
            value = response.headers.get("Retry-After")
            if value is None:
                return None
            try:
                return float(value)
            except ValueError:
                return None

        return retry_with_backoff(
            do_request,
            is_retryable,
            get_retry_after,
            config=self._retry_config,
            sleep_fn=self._sleep_fn,
        )

    def get_movie_details(self, movie_id: int, language: str = "en-US") -> requests.Response:
        """GET /movie/{movie_id} — Movie Details endpoint."""
        return self.get(f"/movie/{movie_id}", params={"language": language})
