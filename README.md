# TMDB Data Platform (Pipeline Repo)

End-to-end data engineering platform built on the [TMDB API](https://developer.themoviedb.org/docs),
demonstrating REST API ingestion, batch processing with PySpark/Glue, SCD Type 2
historization on Apache Iceberg, and analytical data marts via dbt on Athena.

This is the **pipeline repo**: ingestion code, Glue/PySpark jobs, dbt models,
orchestration, and documentation. Infrastructure (Terraform) lives in the
sibling repo [`tmdb-data-platform-infra`](../tmdb-data-platform-infra).

See [`PROJECT_PLAN.md`](./PROJECT_PLAN.md) for the full design and phased
roadmap, and [`docs/architecture/architecture-decisions/`](./docs/architecture/architecture-decisions/)
for the specific technology decisions and their trade-offs.

## Repo layout

| Path                | Purpose |
|---------------------|---------|
| `docs/`             | Architecture, ADRs, TMDB source analysis, data modeling, deep-dive references, operations runbooks |
| `orchestration/`    | Pipeline orchestration (Airflow or Dagster — pending [ADR-0001](./docs/architecture/architecture-decisions/adr-0001-orchestrator-choice.md)) |
| `ingestion/`        | TMDB API client, extractors, pagination, retries, raw-layer schemas |
| `glue/`             | PySpark jobs: Bronze parsing, Silver SCD2/snapshots (no Gold — dbt owns marts, see [ADR-0002](./docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md)) |
| `dbt/`              | dbt project: Gold-layer data marts on top of Silver Iceberg tables via Athena |
| `sql/`              | Ad hoc Athena exploration queries and non-dbt data quality checks |
| `config/`           | Endpoint configs, environment configs, data quality thresholds, table registry |
| `dashboards/`       | Analytical and operational dashboard definitions |
| `tests/`            | Cross-cutting unit, integration, and data tests |

## Status

Phase 0 — Discovery and Design (see `PROJECT_PLAN.md` Section 19).
