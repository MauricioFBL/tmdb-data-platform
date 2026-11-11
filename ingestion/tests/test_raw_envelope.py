"""Tests for ingestion.schemas.raw_envelope.RawEnvelope."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from ingestion.schemas.raw_envelope import RawEnvelope


def _valid_kwargs() -> dict[str, object]:
    return {
        "pipeline_run_id": "run-1",
        "request_id": "req-1",
        "endpoint": "/movie/{movie_id}",
        "source_entity_id": "550",
        "http_status": 200,
        "extraction_timestamp": datetime(2026, 7, 16, tzinfo=timezone.utc),
        "ingestion_date": date(2026, 7, 16),
        "payload": {"id": 550},
    }


def test_valid_envelope_constructs() -> None:
    envelope = RawEnvelope(**_valid_kwargs())  # type: ignore[arg-type]
    assert envelope.payload == {"id": 550}


@pytest.mark.parametrize("missing_field", list(_valid_kwargs().keys()))
def test_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        RawEnvelope(**kwargs)  # type: ignore[arg-type]


def test_envelope_round_trips_through_json() -> None:
    envelope = RawEnvelope(**_valid_kwargs())  # type: ignore[arg-type]
    restored = RawEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored == envelope
