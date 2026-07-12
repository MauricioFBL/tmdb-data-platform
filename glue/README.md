# Glue / PySpark Jobs

PySpark transformation logic run as AWS Glue jobs. Owns Bronze and Silver —
**no `gold/` here**: Gold-layer marts are dbt models (see
[ADR-0002](../docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md)),
because dbt snapshots are a poor fit for this project's multi-attribute
SCD Type 2 requirements, but SQL-on-Athena is a good fit for the
consumption-layer marts themselves.

- `bronze/` — parse raw JSON into typed, source-oriented tables with explicit schemas (`PROJECT_PLAN.md` Section 8).
- `silver/` — business keys, surrogate keys, SCD Type 2 merge logic (see `docs/deep-dives/scd2-iceberg-merge-patterns.md`), snapshot fact construction, historized relationships (e.g. streaming availability).
- `common/` — shared Spark session setup, Iceberg table helpers, hashing/change-detection utilities, technical metadata helpers.
- `tests/` — PySpark unit tests using local Spark sessions (no cluster required).
