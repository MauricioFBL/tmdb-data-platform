"""Explicit schemas for the raw Movie Details envelope — no inference.

WARNING: the payload field names below (belongs_to_collection, genres,
production_companies, ...) are sourced from TMDB's publicly documented
response shape, NOT independently verified against a live API response —
this repo doesn't document their internal struct fields anywhere. Verify
against a real `GET /movie/{movie_id}` call before relying on this in
production; see the ingestion team's setup notes for how to get a token.
"""

from __future__ import annotations

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

BELONGS_TO_COLLECTION_SCHEMA = StructType(
    [
        StructField("id", IntegerType(), nullable=True),
        StructField("name", StringType(), nullable=True),
        StructField("poster_path", StringType(), nullable=True),
        StructField("backdrop_path", StringType(), nullable=True),
    ]
)

GENRE_SCHEMA = StructType(
    [
        StructField("id", IntegerType(), nullable=True),
        StructField("name", StringType(), nullable=True),
    ]
)

PRODUCTION_COMPANY_SCHEMA = StructType(
    [
        StructField("id", IntegerType(), nullable=True),
        StructField("logo_path", StringType(), nullable=True),
        StructField("name", StringType(), nullable=True),
        StructField("origin_country", StringType(), nullable=True),
    ]
)

PRODUCTION_COUNTRY_SCHEMA = StructType(
    [
        StructField("iso_3166_1", StringType(), nullable=True),
        StructField("name", StringType(), nullable=True),
    ]
)

SPOKEN_LANGUAGE_SCHEMA = StructType(
    [
        StructField("english_name", StringType(), nullable=True),
        StructField("iso_639_1", StringType(), nullable=True),
        StructField("name", StringType(), nullable=True),
    ]
)

MOVIE_DETAILS_PAYLOAD_SCHEMA = StructType(
    [
        StructField("adult", BooleanType(), nullable=True),
        StructField("backdrop_path", StringType(), nullable=True),
        StructField("belongs_to_collection", BELONGS_TO_COLLECTION_SCHEMA, nullable=True),
        StructField("budget", LongType(), nullable=True),
        StructField("genres", ArrayType(GENRE_SCHEMA), nullable=True),
        StructField("homepage", StringType(), nullable=True),
        StructField("id", IntegerType(), nullable=True),
        StructField("imdb_id", StringType(), nullable=True),
        StructField("original_language", StringType(), nullable=True),
        StructField("original_title", StringType(), nullable=True),
        StructField("overview", StringType(), nullable=True),
        StructField("popularity", DoubleType(), nullable=True),
        StructField("poster_path", StringType(), nullable=True),
        StructField("production_companies", ArrayType(PRODUCTION_COMPANY_SCHEMA), nullable=True),
        StructField("production_countries", ArrayType(PRODUCTION_COUNTRY_SCHEMA), nullable=True),
        # Kept as a string in Bronze — date-typing raw source strings (which
        # can be null/malformed for unreleased movies) is a Silver concern.
        StructField("release_date", StringType(), nullable=True),
        StructField("revenue", LongType(), nullable=True),
        StructField("runtime", IntegerType(), nullable=True),
        StructField("spoken_languages", ArrayType(SPOKEN_LANGUAGE_SCHEMA), nullable=True),
        StructField("status", StringType(), nullable=True),
        StructField("tagline", StringType(), nullable=True),
        StructField("title", StringType(), nullable=True),
        StructField("video", BooleanType(), nullable=True),
        StructField("vote_average", DoubleType(), nullable=True),
        StructField("vote_count", IntegerType(), nullable=True),
    ]
)

# Mirrors ingestion.schemas.raw_envelope.RawEnvelope.
TECHNICAL_METADATA_FIELDS = [
    StructField("pipeline_run_id", StringType(), nullable=False),
    StructField("request_id", StringType(), nullable=False),
    StructField("endpoint", StringType(), nullable=False),
    StructField("source_entity_id", StringType(), nullable=False),
    StructField("http_status", IntegerType(), nullable=False),
    StructField("extraction_timestamp", TimestampType(), nullable=False),
    StructField("ingestion_date", DateType(), nullable=False),
]

RAW_ENVELOPE_SCHEMA = StructType(
    TECHNICAL_METADATA_FIELDS
    + [StructField("payload", MOVIE_DETAILS_PAYLOAD_SCHEMA, nullable=False)]
)
