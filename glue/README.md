# Glue / PySpark Jobs

**Bronze only** — per [ADR-0005](../docs/architecture/architecture-decisions/adr-0005-silver-moves-to-dbt.md),
Silver's SCD Type 2 processing moved to dbt snapshots (via `dbt-glue`, see
`dbt/snapshots/`). This directory no longer has a `silver/` subfolder.

- `bronze/` — parse raw JSON into typed, source-oriented tables with
  explicit schemas (`PROJECT_PLAN.md` Section 8). The only transformation
  layer PySpark still owns — dbt cannot usefully explode TMDB's nested
  array payloads, so this stays here regardless of the Silver/Gold engine
  decisions above it.
- `common/` — shared Spark session setup, Iceberg table helpers, technical
  metadata helpers used by Bronze jobs.
- `tests/` — PySpark unit tests using local Spark sessions (no cluster
  required).
