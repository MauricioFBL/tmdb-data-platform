# ADR-0002: dbt Owns Gold-Layer Marts Only; PySpark/Glue Owns Bronze, Silver, and Snapshots

## Status

**Superseded by [ADR-0005](./adr-0005-silver-moves-to-dbt.md) — 2026-07-11.**
Silver now moves to dbt as well (via dbt-glue); this ADR's Context section
also overstated why dbt snapshots were rejected — see ADR-0005 for the
corrected reasoning. Kept below, unedited, as the historical record of what
was decided first and why — this is not a live decision anymore.

~~Accepted — 2026-07-11~~

## Context

`PROJECT_PLAN.md`'s original stack (Section 6) had no dbt at all: every
layer (Bronze, Silver, Gold) was PySpark run as AWS Glue jobs. The brief for
this project asked to evaluate dbt as an option, with cost as one driver,
but conflated it with the orchestrator question (dbt is a SQL transformation
tool; Airflow/Dagster are orchestrators — they are not substitutes for each
other and the choice of one doesn't constrain the other). This ADR resolves
dbt's actual scope, independent of ADR-0001 (orchestrator choice).

The project's hardest modeling problem is multi-attribute SCD Type 2 on
`dim_movie_scd2` and `dim_person_scd2` (`PROJECT_PLAN.md` Section 10):
hash-diff change detection across a dozen-plus historical attributes,
correct `valid_from`/`valid_to` bounds, exactly one current record per
business key, no overlapping validity periods, and a MERGE that must be
idempotent under re-runs. dbt does have a built-in `snapshot` feature for
SCD Type 2, but it targets simple check/timestamp-strategy use cases —
tracking many attributes with custom hash-diff logic, non-timestamp change
detection (comparing a computed record hash across a dozen source fields),
and Iceberg-native MERGE semantics is a known rough edge for dbt snapshots.
PySpark gives full control over the hash computation, the MERGE INTO
predicate, and direct access to Iceberg's Spark procedures for the
maintenance operations (compaction, snapshot expiration) the Silver tables
will need under daily writes.

Gold-layer marts (`PROJECT_PLAN.md` Section 11) are a different problem:
they're SQL aggregations and joins over already-historized Silver tables,
with no SCD logic of their own, consumed via Athena. That is squarely
dbt's strength — declarative SQL models, built-in testing
(`unique`, `not_null`, `relationships`), lineage/documentation generation,
and `dbt-athena-community` as a maintained adapter for querying Iceberg
tables through Athena. It's also a distinct, highly marketable skill
(dbt) to demonstrate in a portfolio project, separate from the PySpark/Glue
skill already demonstrated by Bronze/Silver.

## Decision

- **Bronze**: PySpark/Glue only. Parses raw JSON, applies explicit schemas,
  no dbt involvement.
- **Silver**: PySpark/Glue only. SCD Type 2 dimensions, snapshot facts, and
  historized relationships (streaming availability) are all hand-written
  PySpark `MERGE INTO` against Iceberg tables (see
  `docs/deep-dives/scd2-iceberg-merge-patterns.md`). dbt snapshots are
  explicitly rejected for this layer.
- **Gold**: dbt only. The specific adapter (`dbt-athena-community` vs.
  `dbt-glue`) is its own decision — see
  [ADR-0004](./adr-0004-dbt-iceberg-engine-athena-vs-glue.md) — this ADR
  only decides that dbt, in general, owns this layer. The five marts from
  `PROJECT_PLAN.md` Section 11 (`movie_lifecycle`, `movie_performance`,
  `talent_collaboration`, `streaming_availability`, `data_quality`) become
  dbt models under `dbt/models/marts/`, with a thin `dbt/models/staging/`
  layer for naming/typing alignment only (no business logic in staging).
- The `glue/` directory has no `gold/` subfolder. `sql/marts/` (as
  originally sketched in `PROJECT_PLAN.md` Section 15) does not exist —
  mart SQL lives in `dbt/models/marts/` instead.

## Consequences

- Two transformation paradigms in the platform (PySpark for Bronze/Silver,
  SQL/dbt for Gold) instead of one — a deliberate trade-off for skill
  breadth and fit-for-purpose tooling, at the cost of a second toolchain to
  maintain (dbt project setup, `profiles.yml`, a second CI job).
- Query/session cost applies to every `dbt run` against Gold models,
  shaped differently depending on which engine ADR-0004 selects (Athena
  bills per TB scanned; Glue bills per session DPU-hour). Silver tables
  should be well-partitioned
  (by `ingestion_date` / business-relevant date columns) so Gold model
  scans stay cheap; this becomes a concrete requirement for the Silver
  Glue jobs, not just a Gold-side concern.
- Gold-layer data quality tests (uniqueness of mart grain, referential
  integrity to Silver dimensions) are expressed as dbt tests, while
  Bronze/Silver quality checks (`PROJECT_PLAN.md` Section 13) stay as
  PySpark/Glue-invoked checks in `sql/quality/`. Two different test
  frameworks for two different layers — acceptable since the layers
  already have different owners in the team split (Section 16).
- If a future mart needs SCD-2-like historization itself (none currently
  do), that would be a signal the mart boundary is wrong, not a reason to
  reach for dbt snapshots — revisit via a new ADR rather than bending this
  one.
