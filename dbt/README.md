# dbt Project — Silver and Gold

Per [ADR-0005](../docs/architecture/architecture-decisions/adr-0005-silver-moves-to-dbt.md)
(superseding [ADR-0002](../docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md)),
dbt now owns **both** Silver (SCD Type 2, historized relationships, the
daily metrics snapshot fact) and Gold (the five data marts). Bronze stays
PySpark/Glue — see `glue/README.md` — since dbt can't usefully parse
TMDB's raw nested JSON.

**Adapter**: `dbt-glue`, decided in
[ADR-0004](../docs/architecture/architecture-decisions/adr-0004-dbt-iceberg-engine-athena-vs-glue.md).
`profiles.yml.example` below reflects this.

- `snapshots/` — SCD Type 2 for `dim_movie_scd2`, `dim_person_scd2`,
  `dim_provider_scd2` (dbt `snapshot` materialization, `strategy='check'`)
  and the historized relationships (streaming availability, release
  dates). **Not** the same thing as this project's "snapshot fact"
  vocabulary (`movie_metrics_daily`) — see the disambiguation note in
  ADR-0005; that one is a plain incremental model, not a dbt snapshot.
- `models/staging/` — thin, non-materialized views over Bronze/snapshot
  output (naming/typing alignment only — no business logic).
- `models/marts/` — the five Gold marts (`movie_lifecycle`,
  `movie_performance`, `talent_collaboration`, `streaming_availability`,
  `data_quality`), per `docs/modeling/data-marts.md`.
- `tests/` — dbt tests (uniqueness, not-null, relationships, SCD-overlap
  checks) for both snapshots and marts.
- `macros/` — shared SQL macros.

**Open design item, not yet solved** (tracked as a sprint task): whether
the historized relationships' "close removed, insert new" pattern maps
cleanly onto a dbt snapshot's `invalidate_hard_deletes`, or needs a custom
source-query shape. See ADR-0005's Decision section.

**Open infra item**: dbt-glue's reference config auto-creates a DynamoDB
commit-lock table for Iceberg snapshots/incrementals. AWS's own guidance
recommends enabling this for production — treat as needed by default
pending verification against a real Glue 4.0+ session (ADR-0004/ADR-0005).
