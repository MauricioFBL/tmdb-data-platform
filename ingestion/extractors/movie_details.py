"""Movie Details extractor: fetch GET /movie/{movie_id}, write raw JSON to S3."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Final

from ingestion.extractors.movie_ids import get_movie_ids
from ingestion.extractors.raw_writer import write_raw_json
from ingestion.schemas.raw_envelope import RawEnvelope
from ingestion.tmdb_client.client import TMDBClient

# Endpoint template, not a resolved path — kept unparameterized so all
# extractions of this endpoint group under one value for observability.
MOVIE_DETAILS_ENDPOINT: Final[str] = "/movie/{movie_id}"

_S3_BUCKET_ENV_VAR: Final[str] = "S3_BUCKET"
_S3_RAW_PREFIX_ENV_VAR: Final[str] = "S3_RAW_PREFIX"


@dataclass(frozen=True)
class ExtractionResult:
    """The envelope written for one movie, and where it landed in S3."""

    envelope: RawEnvelope
    s3_key: str


class MovieDetailsExtractor:
    """Fetches Movie Details for a set of movie IDs and writes raw JSON to S3."""

    def __init__(
        self,
        client: TMDBClient,
        s3_client: Any,
        bucket: str | None = None,
        raw_prefix: str | None = None,
        pipeline_run_id: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._client = client
        self._s3_client = s3_client
        self._bucket = bucket or os.environ[_S3_BUCKET_ENV_VAR]
        self._raw_prefix = raw_prefix or os.environ[_S3_RAW_PREFIX_ENV_VAR]
        self._pipeline_run_id = pipeline_run_id or str(uuid.uuid4())
        self._clock = clock

    def extract_movie(self, movie_id: int) -> ExtractionResult:
        """Fetch one movie's details and write it as raw JSON to S3."""
        response = self._client.get_movie_details(movie_id)
        request_id = str(uuid.uuid4())
        extraction_timestamp = self._clock()
        envelope = RawEnvelope(
            pipeline_run_id=self._pipeline_run_id,
            request_id=request_id,
            endpoint=MOVIE_DETAILS_ENDPOINT,
            source_entity_id=str(movie_id),
            http_status=response.status_code,
            extraction_timestamp=extraction_timestamp,
            ingestion_date=extraction_timestamp.date(),
            payload=json.loads(response.content),
        )
        key = self._build_s3_key(movie_id, request_id, envelope.ingestion_date)
        # Compact, single-line JSON — Bronze's Spark reader (issue #5) relies
        # on default JSON-Lines parsing, one record per line.
        write_raw_json(
            self._s3_client, self._bucket, key, envelope.model_dump_json().encode("utf-8")
        )
        return ExtractionResult(envelope=envelope, s3_key=key)

    def extract_movies(self, movie_ids: Iterable[int] | None = None) -> list[ExtractionResult]:
        """Extract a batch of movies, fail-fast on the first error.

        Milestone 1 is a small fixed batch proving the pipeline end-to-end,
        not production incremental-load partial-failure handling.
        """
        ids = list(movie_ids) if movie_ids is not None else get_movie_ids()
        return [self.extract_movie(movie_id) for movie_id in ids]

    def _build_s3_key(self, movie_id: int, request_id: str, extraction_date: date) -> str:
        return (
            f"{self._raw_prefix}tmdb/movie_details/"
            f"extraction_date={extraction_date.isoformat()}/{movie_id}_{request_id}.json"
        )
