# Architecture Overview

Updates `PROJECT_PLAN.md` Sections 6/7 for the decisions recorded in
`architecture-decisions/`: dbt owns Gold marts
([ADR-0002](./architecture-decisions/adr-0002-dbt-for-gold-marts.md)),
the orchestrator is not yet chosen
([ADR-0001](./architecture-decisions/adr-0001-orchestrator-choice.md)),
and infrastructure lives in a separate repo
([ADR-0003](./architecture-decisions/adr-0003-two-repo-split.md)).

## Components and responsibilities

| Component | Responsibility | Does NOT do |
|---|---|---|
| **TMDB API** | Source of truth for all movie/person/reference data. | Nothing under this project's control — external dependency with its own rate limits and availability. |
| **Ingestion** (`ingestion/`) | Auth, pagination, retry/backoff, writing immutable raw JSON to S3 with technical metadata. | Any parsing, typing, or business logic — a raw payload is stored byte-for-byte as returned. |
| **Orchestrator** (`orchestration/` — tool pending ADR-0001) | Coordinates extraction batches, triggers Glue jobs, manages watermarks, sequences merge-then-compact (see `docs/deep-dives/scd2-iceberg-merge-patterns.md`'s compaction note), retries failed tasks. | Heavy transformation — no PySpark or business logic runs inside orchestrator task/asset code itself (`PROJECT_PLAN.md` Section 22, item 11). |
| **Glue/PySpark — Bronze** (`glue/bronze/`) | Parses raw JSON into typed, explicit-schema, source-oriented tables. | Business keys, surrogate keys, deduplication across extractions, SCD logic — that starts in Silver. |
| **Glue/PySpark — Silver** (`glue/silver/`) | SCD Type 2 merge (hash-diff, `MERGE INTO` against Iceberg), snapshot facts, historized relationships. Owns the platform's single hardest problem. | Gold-layer aggregation/business metrics — those are dbt's job. |
| **Iceberg + Glue Data Catalog** | Transactional table storage over S3 (MERGE/UPDATE/DELETE, schema/partition evolution, time travel, snapshot-based concurrency). | Query serving on its own — always accessed through Spark (Glue jobs) or Athena. |
| **dbt** (`dbt/`) | Gold-layer marts: SQL models over Silver Iceberg tables via Athena, with built-in testing and documentation. | Anything SCD2-shaped — rejected explicitly in ADR-0002. |
| **Athena** | Query engine for dbt's Gold models and ad hoc exploration (`sql/athena/`). | Write path for Bronze/Silver — those are Spark-only. |
| **Terraform** (sibling repo) | All AWS resource provisioning: S3, IAM, Glue, Glue Catalog, orchestrator infra, networking, monitoring. | Application code deployment logic beyond provisioning the resources it runs on. |
| **GitHub Actions** (per-repo `.github/workflows/`) | CI: lint/test on PR for pipeline code, `terraform fmt`/`validate`/`plan` for infra. | `terraform apply` / production deploys — not yet wired (no AWS account/CI role exists yet; see `tmdb-data-platform-infra/.github/workflows/terraform-ci.yml`'s commented-out plan step). |

## High-level diagram

```text
TMDB API
   |
   v
ingestion/ (auth, pagination, retry)
   |
   v
S3 raw/  (immutable JSON + technical metadata)
   |
   v
orchestration/  <-- triggers, never transforms -->  Glue jobs
   |                                                     |
   |                                                     v
   |                                          glue/bronze/ (typed, source-shaped)
   |                                                     |
   |                                                     v
   +---------------------------------------->  glue/silver/ (SCD2, snapshots,
   |    (watermark advance only after            historized relationships)
   |     successful merge + quality checks)             |
   |                                                     v
   |                                          Apache Iceberg tables (S3 + Glue Catalog)
   |                                                     |
   +-----------------(sequenced strictly after merge)--> compaction / maintenance jobs
                                                          |
                                                          v
                                                    Athena (query layer)
                                                          |
                                                          v
                                              dbt/models/marts/  (Gold)
                                                          |
                                                          v
                                              dashboards/ (Phase 7, deferred)
```

## Layer boundaries (enforced, not just documented)

These are review criteria — a PR that violates them should be flagged
regardless of whether the code otherwise "works" (`PROJECT_PLAN.md`
Section 22):

1. Raw JSON is never mutated after landing in S3 — reprocessing means
   re-reading the same raw file, never patching it.
2. Bronze never writes a business key or surrogate key — those are Silver
   concepts.
3. Silver never computes a business metric that spans multiple entities
   (e.g. "estimated ROI") — that's a Gold/dbt concern.
4. dbt never writes SCD Type 2 logic — if a Gold model seems to need it,
   the Silver model underneath is incomplete, not the Gold model.
5. The orchestrator never contains a PySpark transformation inline — it
   triggers a Glue job and waits/retries, nothing else.

## What's still open

- **Orchestrator tool** — ADR-0001 is Proposed, not Accepted. This diagram
  uses `orchestration/` generically; once decided, update this doc's
  component table and diagram labels to name the actual tool.
- **Terraform remote state backend** — noted as open in ADR-0003's
  Consequences; decide before the first `terraform apply`.
- **BI tool** (Superset/Metabase/QuickSight) — explicitly deferred to
  Phase 7 per `PROJECT_PLAN.md` Section 6; not part of this diagram yet.
