"""Bronze Glue job: parse raw Movie Details JSON into typed Iceberg tables.

Per docs/source-analysis/source-to-target.md, belongs_to_collection,
genres[], and production_companies[] must be exploded into their own
relationship tables, not left nested in Bronze.
"""

from __future__ import annotations

import os

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from glue.bronze.schemas import RAW_ENVELOPE_SCHEMA
from glue.common.iceberg_tables import create_table_if_not_exists, write_append
from glue.common.spark_session import get_glue_iceberg_spark_session

_TECHNICAL_METADATA_COLUMNS = [
    "pipeline_run_id",
    "request_id",
    "endpoint",
    "source_entity_id",
    "http_status",
    "extraction_timestamp",
    "ingestion_date",
]

_MOVIE_DETAILS_SCHEMA_DDL = (
    "pipeline_run_id string, request_id string, endpoint string, "
    "source_entity_id string, http_status int, extraction_timestamp timestamp, "
    "ingestion_date date, tmdb_movie_id int, title string, original_title string, "
    "status string, overview string, tagline string, homepage string, "
    "release_date string, runtime int, budget bigint, revenue bigint, "
    "original_language string, adult boolean, video boolean, "
    "popularity double, vote_average double, vote_count int, "
    "poster_path string, backdrop_path string, imdb_id string"
)
_MOVIE_GENRES_SCHEMA_DDL = (
    "pipeline_run_id string, request_id string, extraction_timestamp timestamp, "
    "ingestion_date date, tmdb_movie_id int, genre_id int, genre_name string"
)
_MOVIE_PRODUCTION_COMPANIES_SCHEMA_DDL = (
    "pipeline_run_id string, request_id string, extraction_timestamp timestamp, "
    "ingestion_date date, tmdb_movie_id int, company_id int, company_name string, "
    "logo_path string, origin_country string"
)
_MOVIE_COLLECTIONS_SCHEMA_DDL = (
    "pipeline_run_id string, request_id string, extraction_timestamp timestamp, "
    "ingestion_date date, tmdb_movie_id int, collection_id int, collection_name string, "
    "poster_path string, backdrop_path string"
)


def read_raw_movie_details(spark: SparkSession, raw_path: str) -> DataFrame:
    """Read raw Movie Details envelopes with an explicit schema, no inference.

    Relies on the extractor (ingestion/extractors/movie_details.py) writing
    compact, single-line JSON — default JSON-Lines parsing, no multiLine.
    """
    return spark.read.schema(RAW_ENVELOPE_SCHEMA).json(raw_path)


def build_bronze_movie_details(df: DataFrame) -> DataFrame:
    """Technical metadata + flattened scalar Movie Details fields."""
    return df.select(
        *_TECHNICAL_METADATA_COLUMNS,
        F.col("payload.id").alias("tmdb_movie_id"),
        F.col("payload.title").alias("title"),
        F.col("payload.original_title").alias("original_title"),
        F.col("payload.status").alias("status"),
        F.col("payload.overview").alias("overview"),
        F.col("payload.tagline").alias("tagline"),
        F.col("payload.homepage").alias("homepage"),
        F.col("payload.release_date").alias("release_date"),
        F.col("payload.runtime").alias("runtime"),
        F.col("payload.budget").alias("budget"),
        F.col("payload.revenue").alias("revenue"),
        F.col("payload.original_language").alias("original_language"),
        F.col("payload.adult").alias("adult"),
        F.col("payload.video").alias("video"),
        F.col("payload.popularity").alias("popularity"),
        F.col("payload.vote_average").alias("vote_average"),
        F.col("payload.vote_count").alias("vote_count"),
        F.col("payload.poster_path").alias("poster_path"),
        F.col("payload.backdrop_path").alias("backdrop_path"),
        F.col("payload.imdb_id").alias("imdb_id"),
    )


def build_bronze_movie_genres(df: DataFrame) -> DataFrame:
    """One row per (movie, genre)."""
    exploded = df.select(
        "pipeline_run_id",
        "request_id",
        "extraction_timestamp",
        "ingestion_date",
        F.col("payload.id").alias("tmdb_movie_id"),
        F.explode("payload.genres").alias("genre"),
    )
    return exploded.select(
        "pipeline_run_id",
        "request_id",
        "extraction_timestamp",
        "ingestion_date",
        "tmdb_movie_id",
        F.col("genre.id").alias("genre_id"),
        F.col("genre.name").alias("genre_name"),
    )


def build_bronze_movie_production_companies(df: DataFrame) -> DataFrame:
    """One row per (movie, production company)."""
    exploded = df.select(
        "pipeline_run_id",
        "request_id",
        "extraction_timestamp",
        "ingestion_date",
        F.col("payload.id").alias("tmdb_movie_id"),
        F.explode("payload.production_companies").alias("company"),
    )
    return exploded.select(
        "pipeline_run_id",
        "request_id",
        "extraction_timestamp",
        "ingestion_date",
        "tmdb_movie_id",
        F.col("company.id").alias("company_id"),
        F.col("company.name").alias("company_name"),
        F.col("company.logo_path").alias("logo_path"),
        F.col("company.origin_country").alias("origin_country"),
    )


def build_bronze_movie_collections(df: DataFrame) -> DataFrame:
    """0 or 1 row per movie — belongs_to_collection is a nullable struct, not an array."""
    return df.filter(F.col("payload.belongs_to_collection").isNotNull()).select(
        "pipeline_run_id",
        "request_id",
        "extraction_timestamp",
        "ingestion_date",
        F.col("payload.id").alias("tmdb_movie_id"),
        F.col("payload.belongs_to_collection.id").alias("collection_id"),
        F.col("payload.belongs_to_collection.name").alias("collection_name"),
        F.col("payload.belongs_to_collection.poster_path").alias("poster_path"),
        F.col("payload.belongs_to_collection.backdrop_path").alias("backdrop_path"),
    )


def write_bronze_movie_details(
    spark: SparkSession,
    catalog: str,
    database: str,
    details_df: DataFrame,
    genres_df: DataFrame,
    companies_df: DataFrame,
    collections_df: DataFrame,
) -> None:
    """Create (if needed) and append to all four Bronze Movie Details tables."""
    create_table_if_not_exists(
        spark, catalog, database, "bronze_movie_details", _MOVIE_DETAILS_SCHEMA_DDL
    )
    create_table_if_not_exists(
        spark, catalog, database, "bronze_movie_genres", _MOVIE_GENRES_SCHEMA_DDL
    )
    create_table_if_not_exists(
        spark,
        catalog,
        database,
        "bronze_movie_production_companies",
        _MOVIE_PRODUCTION_COMPANIES_SCHEMA_DDL,
    )
    create_table_if_not_exists(
        spark, catalog, database, "bronze_movie_collections", _MOVIE_COLLECTIONS_SCHEMA_DDL
    )
    write_append(spark, details_df, catalog, database, "bronze_movie_details")
    write_append(spark, genres_df, catalog, database, "bronze_movie_genres")
    write_append(spark, companies_df, catalog, database, "bronze_movie_production_companies")
    write_append(spark, collections_df, catalog, database, "bronze_movie_collections")


def main() -> None:
    """Job entrypoint. Assumes the Glue Catalog database already exists (infra repo's job)."""
    bucket = os.environ["S3_BUCKET"]
    raw_prefix = os.environ["S3_RAW_PREFIX"]
    bronze_prefix = os.environ["S3_BRONZE_PREFIX"]
    database = os.environ["GLUE_DATABASE_BRONZE"]
    catalog = "glue_catalog"

    spark = get_glue_iceberg_spark_session(
        app_name="tmdb-bronze-movie-details",
        warehouse_path=f"s3://{bucket}/{bronze_prefix}",
        catalog_name=catalog,
    )
    raw_path = f"s3://{bucket}/{raw_prefix}tmdb/movie_details/"
    raw_df = read_raw_movie_details(spark, raw_path)

    write_bronze_movie_details(
        spark,
        catalog,
        database,
        build_bronze_movie_details(raw_df),
        build_bronze_movie_genres(raw_df),
        build_bronze_movie_production_companies(raw_df),
        build_bronze_movie_collections(raw_df),
    )


if __name__ == "__main__":
    main()
