"""Exception types raised by the TMDB API client."""

from __future__ import annotations


class TMDBError(Exception):
    """Base class for all TMDB client errors."""


class TMDBConfigError(TMDBError):
    """Raised when the client is misconfigured (e.g. missing access token)."""


class TMDBHTTPError(TMDBError):
    """Raised for a non-retryable HTTP error response from the TMDB API."""

    def __init__(self, status_code: int, message: str, response_body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class TMDBRateLimitExceededError(TMDBHTTPError):
    """Raised when retries on HTTP 429 are exhausted without success."""

    def __init__(
        self,
        status_code: int,
        message: str,
        retry_after: float | None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(status_code, message, response_body)
        self.retry_after = retry_after
