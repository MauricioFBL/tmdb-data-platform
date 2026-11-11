"""Shared Iceberg table helpers for Bronze jobs."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession


def create_table_if_not_exists(
    spark: SparkSession,
    catalog: str,
    database: str,
    table: str,
    schema_ddl: str,
    partition_by: list[str] | None = None,
    table_properties: dict[str, str] | None = None,
) -> None:
    """CREATE TABLE IF NOT EXISTS ... USING iceberg.

    No write.merge.mode / write.update.mode overrides — Bronze tables are
    append-mostly and stay on Iceberg's copy-on-write default; merge-on-read
    is reserved for the Silver/SCD2 tables' scattered-row-update pattern.
    Does not create the database itself — that's the infra repo's job.
    """
    partition_clause = f" PARTITIONED BY ({', '.join(partition_by)})" if partition_by else ""
    properties_clause = ""
    if table_properties:
        pairs = ", ".join(f"'{k}'='{v}'" for k, v in table_properties.items())
        properties_clause = f" TBLPROPERTIES ({pairs})"
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {catalog}.{database}.{table} "
        f"({schema_ddl}) USING iceberg{partition_clause}{properties_clause}"
    )


def write_append(
    spark: SparkSession, df: DataFrame, catalog: str, database: str, table: str
) -> None:
    """Append rows to an existing Iceberg table."""
    df.writeTo(f"{catalog}.{database}.{table}").append()
