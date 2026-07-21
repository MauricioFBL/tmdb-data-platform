"""Tests for glue.bronze.bronze_movie_details."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from pyspark.sql import SparkSession

from glue.bronze.bronze_movie_details import (
    build_bronze_movie_collections,
    build_bronze_movie_details,
    build_bronze_movie_genres,
    build_bronze_movie_production_companies,
    read_raw_movie_details,
    write_bronze_movie_details,
)
from ingestion.schemas.raw_envelope import RawEnvelope

FIXTURE_PATH = (
    Path(__file__).parent.parent.parent / "tests" / "data" / "tmdb_movie_details_sample.json"
)


def test_read_raw_movie_details_parses_with_explicit_schema(
    raw_envelope_dir: str, spark: SparkSession
) -> None:
    df = read_raw_movie_details(spark, raw_envelope_dir)
    assert df.count() == 1
    row = df.collect()[0]
    assert row["source_entity_id"] == "550"
    # PySpark's collect() returns naive datetimes, converted using the JVM's
    # system timezone (pinned to UTC via -Duser.timezone in
    # get_local_test_spark_session) — compare against a naive UTC wall-clock
    # value, not an aware datetime.
    assert row["extraction_timestamp"] == datetime(2026, 7, 16, 12, 0, 0)
    assert row["ingestion_date"] == date(2026, 7, 16)


def test_build_bronze_movie_details_flattens_scalars(
    raw_envelope_dir: str, spark: SparkSession
) -> None:
    raw_df = read_raw_movie_details(spark, raw_envelope_dir)
    details = build_bronze_movie_details(raw_df).collect()[0]

    assert details["tmdb_movie_id"] == 550
    assert details["title"] == "Fight Club"
    assert details["status"] == "Released"
    assert details["budget"] == 63000000
    assert details["revenue"] == 100853753
    assert details["runtime"] == 139
    assert details["release_date"] == "1999-10-15"
    assert details["vote_count"] == 32368
    assert details["origin_country"] == ["US"]
    assert details["softcore"] is False
    assert {c["iso_3166_1"] for c in details["production_countries"]} == {"DE", "US"}


def test_build_bronze_movie_genres_explodes_array(
    raw_envelope_dir: str, spark: SparkSession
) -> None:
    raw_df = read_raw_movie_details(spark, raw_envelope_dir)
    genres = build_bronze_movie_genres(raw_df).collect()

    assert len(genres) == 2
    assert all(g["tmdb_movie_id"] == 550 for g in genres)
    genre_names = {g["genre_name"] for g in genres}
    assert genre_names == {"Drama", "Thriller"}


def test_build_bronze_movie_production_companies_explodes_array(
    raw_envelope_dir: str, spark: SparkSession
) -> None:
    raw_df = read_raw_movie_details(spark, raw_envelope_dir)
    companies = build_bronze_movie_production_companies(raw_df).collect()

    assert len(companies) == 5
    names = {c["company_name"] for c in companies}
    assert names == {
        "Regency Enterprises",
        "Fox 2000 Pictures",
        "Linson Entertainment",
        "20th Century Fox",
        "Taurus Film",
    }


def test_build_bronze_movie_collections_excludes_null_belongs_to_collection(
    raw_envelope_dir: str, spark: SparkSession
) -> None:
    # The Fight Club fixture has belongs_to_collection: null.
    raw_df = read_raw_movie_details(spark, raw_envelope_dir)
    collections = build_bronze_movie_collections(raw_df).collect()

    assert collections == []


def test_build_bronze_movie_collections_includes_present_collection(
    tmp_path: Path, spark: SparkSession
) -> None:
    payload = json.loads(FIXTURE_PATH.read_bytes())
    payload["belongs_to_collection"] = {
        "id": 10,
        "name": "Test Collection",
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
    }
    envelope = RawEnvelope(
        pipeline_run_id="test-run",
        request_id=str(uuid.uuid4()),
        endpoint="/movie/{movie_id}",
        source_entity_id="550",
        http_status=200,
        extraction_timestamp=datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc),
        ingestion_date=date(2026, 7, 16),
        payload=payload,
    )
    partition_dir = tmp_path / "extraction_date=2026-07-16"
    partition_dir.mkdir()
    (partition_dir / "550.json").write_text(envelope.model_dump_json() + "\n")

    raw_df = read_raw_movie_details(spark, str(tmp_path))
    collections = build_bronze_movie_collections(raw_df).collect()

    assert len(collections) == 1
    assert collections[0]["collection_id"] == 10
    assert collections[0]["collection_name"] == "Test Collection"


def test_write_bronze_movie_details_append_doubles_row_count(
    raw_envelope_dir: str, spark: SparkSession
) -> None:
    raw_df = read_raw_movie_details(spark, raw_envelope_dir)
    details_df = build_bronze_movie_details(raw_df)
    genres_df = build_bronze_movie_genres(raw_df)
    companies_df = build_bronze_movie_production_companies(raw_df)
    collections_df = build_bronze_movie_collections(raw_df)

    write_bronze_movie_details(
        spark, "local", "default", details_df, genres_df, companies_df, collections_df
    )
    write_bronze_movie_details(
        spark, "local", "default", details_df, genres_df, companies_df, collections_df
    )

    row_count = spark.sql("SELECT COUNT(*) AS n FROM local.default.bronze_movie_details").collect()[
        0
    ]["n"]
    assert row_count == 2
