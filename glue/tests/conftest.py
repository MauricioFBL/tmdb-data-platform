"""Shared fixtures for glue/tests — local Iceberg session + raw fixture data."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

from glue.common.spark_session import get_local_test_spark_session
from ingestion.schemas.raw_envelope import RawEnvelope

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "tests" / "data" / "tmdb_movie_details_sample.json"
)


@pytest.fixture(scope="session")
def spark(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SparkSession]:
    warehouse_dir = str(tmp_path_factory.mktemp("iceberg_warehouse"))
    session = get_local_test_spark_session(warehouse_dir)
    yield session
    session.stop()


def _write_envelope_line(path: Path, movie_id: int, payload: dict[str, object]) -> None:
    envelope = RawEnvelope(
        pipeline_run_id="test-run",
        request_id=str(uuid.uuid4()),
        endpoint="/movie/{movie_id}",
        source_entity_id=str(movie_id),
        http_status=200,
        extraction_timestamp=datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc),
        ingestion_date=date(2026, 7, 16),
        payload=payload,
    )
    with path.open("a") as f:
        f.write(envelope.model_dump_json())
        f.write("\n")


@pytest.fixture
def raw_envelope_dir(tmp_path: Path) -> str:
    """One compact-JSON raw file, built the same way the extractor (#4) does."""
    payload = json.loads(FIXTURE_PATH.read_bytes())
    partition_dir = tmp_path / "extraction_date=2026-07-16"
    partition_dir.mkdir()
    _write_envelope_line(partition_dir / "550.json", 550, payload)
    return str(tmp_path)
