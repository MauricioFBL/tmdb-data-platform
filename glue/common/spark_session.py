"""Shared Iceberg-enabled Spark session builders for Bronze jobs.

Conf per docs/deep-dives/iceberg-internals-and-glue.md.
"""

from __future__ import annotations

import os

from pyspark.sql import SparkSession

_ICEBERG_EXTENSIONS = "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
# Only needed for local/test sessions — a real Glue job gets Iceberg support
# from the `--datalake-formats iceberg` job parameter instead, not this jar.
_ICEBERG_SPARK_RUNTIME_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.5.2"

# spark.sql.session.timeZone only controls SQL-level display/conversion —
# collect() converts internal timestamps to Python datetime using the JVM
# subprocess's *system* default timezone, not this session config (a known
# PySpark quirk, and spark.driver.extraJavaOptions doesn't reach local
# mode's py4j-launched gateway either). Setting TZ in the Python process's
# own environment before the JVM subprocess spawns is what actually works —
# the child JVM inherits it and java.util.TimeZone.getDefault() honors it.
# This keeps collect()-based reads UTC-correct across dev machines and CI.
os.environ.setdefault("TZ", "UTC")

# Belt-and-suspenders for the real Glue/cluster path (spark-submit does
# apply these, unlike local mode's py4j gateway).
_UTC_JVM_OPTS = "-Duser.timezone=UTC"


def get_glue_iceberg_spark_session(
    app_name: str = "tmdb-bronze",
    warehouse_path: str | None = None,
    catalog_name: str = "glue_catalog",
    extra_conf: dict[str, str] | None = None,
) -> SparkSession:
    """Build a Spark session wired to the real Glue Data Catalog via Iceberg.

    ``warehouse_path`` should point at the caller job's own S3 prefix (e.g.
    Bronze's ``s3://{bucket}/{S3_BRONZE_PREFIX}``) — this function stays
    generic so future Bronze jobs can reuse it with their own warehouse path.
    """
    builder = (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.extraJavaOptions", _UTC_JVM_OPTS)
        .config("spark.executor.extraJavaOptions", _UTC_JVM_OPTS)
        .config("spark.sql.extensions", _ICEBERG_EXTENSIONS)
        .config(f"spark.sql.catalog.{catalog_name}", "org.apache.iceberg.spark.SparkCatalog")
        .config(
            f"spark.sql.catalog.{catalog_name}.catalog-impl",
            "org.apache.iceberg.aws.glue.GlueCatalog",
        )
        .config(f"spark.sql.catalog.{catalog_name}.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
    )
    if warehouse_path is not None:
        builder = builder.config(f"spark.sql.catalog.{catalog_name}.warehouse", warehouse_path)
    for key, value in (extra_conf or {}).items():
        builder = builder.config(key, value)
    return builder.getOrCreate()


def get_local_test_spark_session(
    warehouse_dir: str, app_name: str = "tmdb-bronze-tests"
) -> SparkSession:
    """Build a local, file-backed Iceberg session for tests — no AWS access.

    Uses Iceberg's built-in HadoopCatalog rather than GlueCatalog: moto only
    mocks boto3's Python-level HTTP calls, not the JVM's own AWS SDK calls
    that GlueCatalog makes, so tests can't rely on moto for the Iceberg
    catalog layer.
    """
    catalog_name = "local"
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.jars.packages", _ICEBERG_SPARK_RUNTIME_PACKAGE)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.extraJavaOptions", _UTC_JVM_OPTS)
        .config("spark.executor.extraJavaOptions", _UTC_JVM_OPTS)
        .config("spark.sql.extensions", _ICEBERG_EXTENSIONS)
        .config(f"spark.sql.catalog.{catalog_name}", "org.apache.iceberg.spark.SparkCatalog")
        .config(f"spark.sql.catalog.{catalog_name}.type", "hadoop")
        .config(f"spark.sql.catalog.{catalog_name}.warehouse", warehouse_dir)
        .master("local[1]")
        .getOrCreate()
    )
