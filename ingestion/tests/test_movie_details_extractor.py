"""Tests for ingestion.extractors.movie_details.MovieDetailsExtractor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import boto3
import pytest
import requests
from moto import mock_aws

from ingestion.extractors.movie_details import MovieDetailsExtractor
from ingestion.schemas.raw_envelope import RawEnvelope
from ingestion.tests.conftest import FakeResponse
from ingestion.tmdb_client.client import TMDBClient

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "tests" / "data" / "tmdb_movie_details_sample.json"
)
BUCKET = "tmdb-data-platform-test"


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def fixture_payload(fixture_bytes: bytes) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(fixture_bytes))


@mock_aws
def test_extract_movie_writes_expected_key_and_round_trips_payload(
    fixture_bytes: bytes, fixture_payload: dict[str, object]
) -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)

    session_mock = _session_returning(fixture_bytes)
    client = TMDBClient(access_token="test-token", session=session_mock)

    fixed_clock = lambda: datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)
    extractor = MovieDetailsExtractor(
        client=client,
        s3_client=s3,
        bucket=BUCKET,
        raw_prefix="raw/",
        pipeline_run_id="run-1",
        clock=fixed_clock,
    )

    result = extractor.extract_movie(550)

    assert result.s3_key.startswith("raw/tmdb/movie_details/extraction_date=2026-07-16/550_")
    assert result.envelope.http_status == 200
    assert result.envelope.source_entity_id == "550"
    assert result.envelope.extraction_timestamp == fixed_clock()
    assert result.envelope.ingestion_date == fixed_clock().date()
    assert result.envelope.payload == fixture_payload

    stored_body = s3.get_object(Bucket=BUCKET, Key=result.s3_key)["Body"].read()
    restored = RawEnvelope.model_validate_json(stored_body)
    assert restored == result.envelope


@mock_aws
def test_extract_movies_writes_one_object_per_movie(fixture_bytes: bytes) -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=BUCKET)

    session_mock = _session_returning(fixture_bytes)
    client = TMDBClient(access_token="test-token", session=session_mock)
    extractor = MovieDetailsExtractor(client=client, s3_client=s3, bucket=BUCKET, raw_prefix="raw/")

    results = extractor.extract_movies([550, 238])

    assert len(results) == 2
    assert {r.envelope.source_entity_id for r in results} == {"550", "238"}
    listed = s3.list_objects_v2(Bucket=BUCKET, Prefix="raw/tmdb/movie_details/")
    assert listed["KeyCount"] == 2


def _session_returning(body: bytes) -> requests.Session:
    session = MagicMock()
    session.get.return_value = FakeResponse(status_code=200, text=body.decode("utf-8"))
    return cast(requests.Session, session)
