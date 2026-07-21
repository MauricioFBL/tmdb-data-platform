"""Tests for ingestion.extractors.movie_ids."""

from __future__ import annotations

import pytest

from ingestion.extractors.movie_ids import DEFAULT_MOVIE_IDS, get_movie_ids


def test_returns_default_when_env_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOVIE_IDS", raising=False)
    assert get_movie_ids() == DEFAULT_MOVIE_IDS


def test_returns_parsed_env_var_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOVIE_IDS", "1, 2,3")
    assert get_movie_ids() == [1, 2, 3]
