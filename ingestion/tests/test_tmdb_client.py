"""Tests for ingestion.tmdb_client.client.TMDBClient."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ingestion.tests.conftest import FakeResponse
from ingestion.tmdb_client.client import DEFAULT_BASE_URL, TMDBClient
from ingestion.tmdb_client.exceptions import TMDBConfigError, TMDBRateLimitExceededError


def _make_client(session: MagicMock, **kwargs: object) -> TMDBClient:
    kwargs.setdefault("sleep_fn", lambda _seconds: None)
    return TMDBClient(access_token="test-token", session=session, **kwargs)  # type: ignore[arg-type]


def test_missing_token_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TMDB_API_READ_ACCESS_TOKEN", raising=False)
    with pytest.raises(TMDBConfigError):
        TMDBClient(session=MagicMock())


def test_token_falls_back_to_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMDB_API_READ_ACCESS_TOKEN", "env-token")
    client = TMDBClient(session=MagicMock())
    assert client is not None


def test_get_sends_bearer_header_never_query_param() -> None:
    session = MagicMock()
    session.get.return_value = FakeResponse(status_code=200, text="{}")
    client = _make_client(session)

    client.get("/movie/550")

    _, kwargs = session.get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert "api_key" not in (kwargs.get("params") or {})
    assert kwargs["params"] is None


def test_get_movie_details_builds_correct_path_and_params() -> None:
    session = MagicMock()
    session.get.return_value = FakeResponse(status_code=200, text="{}")
    client = _make_client(session)

    client.get_movie_details(550)

    args, kwargs = session.get.call_args
    assert args[0] == f"{DEFAULT_BASE_URL}/movie/550"
    assert kwargs["params"] == {"language": "en-US"}


def test_get_retries_once_on_429_then_succeeds() -> None:
    session = MagicMock()
    session.get.side_effect = [
        FakeResponse(status_code=429, text="", headers={}),
        FakeResponse(status_code=200, text='{"id": 550}'),
    ]
    from ingestion.retries.backoff import RetryConfig

    client = _make_client(session, retry_config=RetryConfig(base_delay_seconds=0.0, jitter=False))

    response = client.get("/movie/550")

    assert response.status_code == 200
    assert session.get.call_count == 2


def test_get_honors_retry_after_header() -> None:
    session = MagicMock()
    session.get.side_effect = [
        FakeResponse(status_code=429, text="", headers={"Retry-After": "3.5"}),
        FakeResponse(status_code=200, text="{}"),
    ]
    sleeps: list[float] = []
    from ingestion.retries.backoff import RetryConfig

    client = TMDBClient(
        access_token="test-token",
        session=session,
        # base_delay_seconds is deliberately huge — if Retry-After weren't
        # honored, the computed exponential delay would dominate instead.
        retry_config=RetryConfig(base_delay_seconds=99.0, jitter=False),
        sleep_fn=sleeps.append,
    )

    client.get("/movie/550")

    assert sleeps == [3.5]


def test_get_raises_after_retries_exhausted() -> None:
    session = MagicMock()
    session.get.return_value = FakeResponse(status_code=429, text="", headers={})
    from ingestion.retries.backoff import RetryConfig

    client = _make_client(
        session, retry_config=RetryConfig(max_retries=1, base_delay_seconds=0.0, jitter=False)
    )

    with pytest.raises(TMDBRateLimitExceededError):
        client.get("/movie/550")
