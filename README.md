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
| `glue/`             | PySpark jobs: Bronze parsing only (Silver moved to dbt snapshots, see [ADR-0005](./docs/architecture/architecture-decisions/adr-0005-silver-moves-to-dbt.md); no Gold — dbt owns marts, see [ADR-0002](./docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md)) |
| `dbt/`              | dbt project: Silver SCD2 snapshots and Gold-layer data marts on top of Bronze Iceberg tables via `dbt-glue` (ADR-0004/0005); Athena is the query layer |
| `sql/`              | Ad hoc Athena exploration queries and non-dbt data quality checks |
| `config/`           | Endpoint configs, environment configs, data quality thresholds, table registry |
| `dashboards/`       | Analytical and operational dashboard definitions |
| `tests/`            | Cross-cutting unit, integration, and data tests |

## Pipeline flow

```
TMDB API → ingestion/ → S3 (raw) → glue/ → S3 (bronze, Iceberg) → dbt/ → Athena (Gold) → dashboards/
```

Each top-level directory maps to one stage of that chain.

### `ingestion/` — extraction layer (plain Python, no Spark)

Pulls data out of the TMDB API and lands it, unmodified, in S3. No business
logic or transformation happens here — that starts in `glue/`.

```
ingestion/
├── tmdb_client/     # HTTP client: bearer auth, base URL, request building
├── retries/         # exponential backoff (HTTP 429) + client-side rate limiting
├── extractors/      # one extractor per TMDB endpoint (currently: Movie Details only)
├── schemas/         # RawEnvelope — technical metadata wrapper around each raw payload
├── pagination/       # not yet implemented — for paginated endpoints
└── tests/           # unit tests against recorded/mocked HTTP responses, no live API calls
```

### `glue/` — Bronze layer (PySpark)

The only layer still on PySpark/Glue — Silver and Gold both run on `dbt-glue`
(ADR-0005). Reads raw JSON with an explicit schema (no inference) and
flattens nested structures (`genres`, `production_companies`,
`belongs_to_collection`) into their own Iceberg tables.

```
glue/
├── common/          # shared Spark session builders + Iceberg table helpers
├── bronze/          # Movie Details Bronze job (schemas.py + bronze_movie_details.py)
└── tests/           # PySpark unit tests against a local Iceberg catalog, no AWS access
```

### `dbt/` — Silver and Gold layers (scaffold only)

Owns SCD Type 2 historization and the final analytical data marts. Not yet
implemented.

```
dbt/
├── snapshots/       # planned: dim_movie_scd2
├── models/staging/  # planned: cleanup on top of Bronze
├── models/marts/    # planned: movie_performance, movie_lifecycle, etc.
└── tests/           # planned: current-row uniqueness, no overlapping validity
```

### `orchestration/` — blocked on ADR-0001

Empty until the orchestrator choice (Airflow vs. Dagster) is decided —
no point writing DAGs before the engine is picked.

### `config/`, `sql/`, `dashboards/` — scaffold, not yet used

- `config/` — planned home for `endpoints.yml`, `environments.yml`, etc.
  None exist yet; the current code uses env vars and in-code constants
  instead (see `ingestion/extractors/movie_ids.py`).
- `sql/` — Athena queries and quality checks, planned.
- `dashboards/` — final reporting layer, planned.

### `tests/` — cross-module tests (distinct from `ingestion/tests/` and `glue/tests/`)

```
tests/
├── data/            # shared fixtures (e.g. tmdb_movie_details_sample.json)
├── unit/            # not yet used — for logic that doesn't belong to one module
└── integration/     # not yet used — planned end-to-end slice test (raw → bronze → silver)
```

## Status

Phase 0 (Discovery and Design) is complete. Phases 1–2 are in progress
(see `PROJECT_PLAN.md` Section 19): the `ingestion/` → `glue/` Bronze
vertical slice for Movie Details is implemented and unit-tested, but it has
not yet run against AWS, because the Terraform in `tmdb-data-platform-infra`
is still a scaffold. Silver (dbt snapshots), the Gold marts, and the
orchestrator choice (ADR-0001) are still open.
