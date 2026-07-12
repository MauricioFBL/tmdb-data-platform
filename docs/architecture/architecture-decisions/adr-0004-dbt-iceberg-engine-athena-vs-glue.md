# ADR-0004: dbt's Execution Engine for Gold Marts on Iceberg — Athena vs. Glue

## Status

**Proposed** — not yet decided. ADR-0002 named `dbt-athena-community` as the
adapter without weighing it against `dbt-glue`; this ADR closes that gap.
Record the actual choice in the Decision section below.

## Context

ADR-0002 decided dbt owns Gold-layer marts, querying Silver Iceberg tables
"via Athena." It did not evaluate *which engine dbt uses to talk to
Iceberg* as its own decision — Athena and Glue are the two realistic
options, and they differ enough (execution model, locking behavior,
known bugs, cost shape) that this deserves its own record rather than
being folded silently into ADR-0002.

This surfaced because you found real, currently-open bug reports against
`dbt-athena`'s Iceberg support and asked whether `dbt-glue` — running Gold
models as Spark on the same Glue engine Silver already uses — would be the
safer choice.

## Implementation detail: dbt-athena + Iceberg

Materializing a Gold model as an Iceberg table:

```sql
{{ config(
    materialized='incremental',
    table_type='iceberg',
    incremental_strategy='merge',
    unique_key='movie_id',
    format='parquet',
    partitioned_by=['bucket(movie_id, 16)'],
    table_properties={'optimize_rewrite_delete_file_threshold': '2'}
) }}
```

- `table_type='iceberg'` is a per-model config, not a project-wide setting
  — each mart declares it individually. `format` supports parquet/avro/orc.
- `partitioned_by` uses Iceberg's hidden-partitioning transforms
  (`bucket(...)`, `day(...)`, etc.), consistent with the partition-evolution
  behavior already documented in `docs/deep-dives/iceberg-internals-and-glue.md`.
- `incremental_strategy='merge'` requires **Athena engine version 3**
  specifically — the workgroup (`config/environments.yml` /
  `ATHENA_WORKGROUP`) must be pinned to engine v3, not left on whatever
  the default is, or `MERGE INTO` silently isn't available.
- `unique_key` (required for merge), plus optional `incremental_predicates`
  (narrows the match scope, useful for pruning partitions the merge
  touches) and `delete_condition` (row-level deletes as part of the same
  merge) round out the incremental config.
- Execution model: dbt-athena submits SQL to an Athena workgroup and polls
  for completion (`AthenaCursor.execute`) — no persistent compute, no
  session to provision, billed per query.

**The three real, currently-open issues to design around, not ignore:**

1. **[dbt-labs/dbt-adapters #1739](https://github.com/dbt-labs/dbt-adapters/issues/1739)**
   — a failed CTAS (e.g. `TOO_MANY_OPEN_PARTITIONS`) leaves partial data at
   the model's S3 location; the adapter's automatic retry re-runs against
   the same location without cleaning up first, producing a permanent
   `ICEBERG_FILESYSTEM_ERROR` that retries can't self-heal. **Mitigation**:
   a CI/orchestration step that clears the model's S3 target path on
   failure before any retry, or disable automatic retries and let the
   orchestrator's own retry (which can be scoped to `dbt run --full-refresh`
   for the affected model) handle it instead.
2. **[dbt-labs/dbt-adapters #1813](https://github.com/dbt-labs/dbt-adapters/issues/1813)**
   — the adapter retries a query that hit Athena's 60-minute DML timeout up
   to `num_retries` times (default 5), even though a timeout won't resolve
   itself. **Mitigation**: set `num_retries: 0` (or 1) in `profiles.yml`
   for this project's scale, and rely on the orchestrator's retry/alerting
   instead of the adapter's — this project's marts are small enough that a
   60-minute timeout indicates a real problem (missing partition pruning,
   an accidental full scan), not a transient blip worth silently retrying.
3. **[Known issue](https://dbt-athena.github.io/docs/known-issues)** —
   an incremental Iceberg model can't drop a column that's also a
   partition key via `on_schema_change: sync_all_columns`; it needs a
   `--full-refresh` instead. **Mitigation**: treat any partition-key change
   to a mart as a deliberate, documented full-refresh operation (already
   consistent with `docs/modeling/data-marts.md`'s point that Silver
   partitioning choices should be stable — this is a Gold-layer echo of
   the same discipline).

None of these are "Iceberg doesn't work on Athena" — they're specific,
narrow failure-handling gaps with known workarounds.

## Implementation detail: dbt-glue + Iceberg

Connection profile (from dbt-glue's own reference example):

```yaml
tmdb_gold:
  target: dev
  outputs:
    dev:
      type: glue
      role_arn: arn:aws:iam::<account>:role/GlueInteractiveSessionRole
      region: us-east-1
      glue_version: "4.0"
      workers: 2
      worker_type: G.1X
      schema: tmdb_gold
      session_provisioning_timeout_in_seconds: 120
      location: "s3://tmdb-data-platform/gold/"
      datalake_formats: iceberg
      conf: >-
        --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
        --conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog
        --conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog
        --conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO
        --conf spark.sql.catalog.glue_catalog.lock-impl=org.apache.iceberg.aws.dynamodb.DynamoDbLockManager
        --conf spark.sql.catalog.glue_catalog.lock.table=tmdb_gold_lock
```

Model config:

```sql
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['movie_id'],
    file_format='iceberg',
    partition_by=['release_year'],
    table_properties={'write.target-file-size-bytes': '268435456'},
    iceberg_expire_snapshots='False'
) }}
```

- Execution model: dbt compiles models to Spark SQL and runs them through a
  **Glue interactive session** — the same underlying engine (Spark +
  Iceberg + Glue Data Catalog) that `glue/silver/` jobs already use, so
  version compatibility follows the same Glue-version-to-Iceberg-version
  table already established in `docs/deep-dives/iceberg-internals-and-glue.md`.
- Incremental strategies: `merge` (recommended, needs `unique_key`),
  `append`, `insert_overwrite` — a superset of what dbt-athena offers,
  since it isn't constrained to whatever `MERGE INTO` Athena's engine
  supports.
- **A real wrinkle worth flagging before assuming Glue is the "simpler"
  option**: dbt-glue's reference config wires up
  `lock-impl=DynamoDbLockManager` and, per its own docs, **automatically
  creates a DynamoDB table** (`myGlueLockTable` by default) on first run of
  an incremental Iceberg model. This directly reintroduces the exact
  DynamoDB lock-manager infrastructure that
  `docs/deep-dives/iceberg-internals-and-glue.md` Section 4 said Glue
  4.0+/Iceberg 1.0+ lets you **avoid**, because the Glue Data Catalog does
  optimistic locking natively as of that version. **Open question, not yet
  verified**: is dbt-glue's DynamoDB lock config still necessary on
  Glue 4.0+, or is it legacy guidance from before Glue Catalog had native
  optimistic locking, carried over in dbt-glue's docs/defaults without
  being revisited? If it's still required, that's a real infra cost this
  ADR needs to weigh (a `dynamodb` module would need adding to
  `tmdb-data-platform-infra/modules/`, which doesn't exist today). If it's
  legacy/optional, it can likely be omitted from the `conf` block entirely
  — confirm against a real Glue 4.0 session before committing either way.
- Session lifecycle: sessions cold-start (~120s provisioning per the
  example config) and idle-timeout after inactivity — a `dbt run` against
  five marts back-to-back reuses one warm session, but a scheduled job that
  starts a fresh session per run pays that ~2-minute provisioning cost
  every time, pure overhead with no query work done in it.

## Cost model — worked comparison for this project's actual scale

- **Athena on-demand**: $5.00 per TB scanned, 10 MB minimum per query
  (verified current AWS pricing). Five well-partitioned Gold marts each
  scanning a few hundred MB to a few GB of Silver data (a portfolio-scale
  movie catalog, not a real streaming platform's data volume) totals well
  under 10 GB scanned per full refresh — **under $0.05/run** even
  generously estimated. Cost scales with bytes scanned, so it's punished
  hard by poor partitioning/pruning, but rewarded proportionally for doing
  partitioning right (which `docs/modeling/scd-strategy.md` and
  `data-marts.md` already require).
- **Glue interactive session**: $0.44/DPU-hour, 2 DPU minimum, 1-minute
  minimum billing (verified current AWS pricing). A 2-worker G.1X session
  (2 DPU workers + implicit driver overhead) running for, say, 10 minutes
  of actual dbt work costs roughly `3 DPU x (10/60) hr x $0.44 ≈ $0.22`,
  plus the ~2-minute cold-start is billed time with no query progress if a
  fresh session is provisioned per scheduled run.
- **At this project's scale, Athena is very likely cheaper per run** —
  Glue's cost floor is time-based (you pay for the session however little
  data it touches), while Athena's is bytes-based (you pay for exactly
  what you scan, and a small portfolio dataset scans small). This cost gap
  would only close if data volumes grew enough that Athena's per-TB cost
  started dominating, which is not this project's near-term shape.

## Decision Drivers

1. **Reliability** — the concrete, currently-open bugs above vs. Glue's
   different (Spark-session) failure surface.
2. **Consistency of engine** — Glue means one execution model (Spark)
   end-to-end; Athena means a genuinely different engine for Gold than for
   Bronze/Silver.
3. **Cost**, worked out concretely above — favors Athena at this project's
   scale.
4. **Operational simplicity** — Athena has no session/cluster to manage;
   Glue's DynamoDB-lock-table question (open, above) could reintroduce
   infra Athena avoids entirely.
5. **Skill-diversity story for the portfolio** (from ADR-0002) — Athena
   keeps Gold as a genuinely separate, serverless-SQL skill from the
   PySpark skill Silver already demonstrates; Glue would make dbt "just
   another way to submit Spark," diluting that distinction.

## Recommendation (not a decision)

Keep **dbt-athena**, hardened against the three known issues (explicit
`num_retries` cap, engine-v3-pinned workgroup, full-refresh discipline on
partition-key changes) — do not switch to dbt-glue by default. The known
dbt-athena bugs are narrow and workaround-able; dbt-glue's session-based
cost model is very likely more expensive at this project's scale, and its
DynamoDB-lock-table behavior is an unresolved question that could
reintroduce exactly the extra infrastructure the Glue-version choice in
`docs/deep-dives/iceberg-internals-and-glue.md` was meant to avoid. Revisit
this recommendation if, in practice, the Athena adapter bugs prove more
disruptive than expected, or if Gold-layer data volume grows enough that
Athena's per-TB cost stops being trivially cheap.

This is a closer call than ADR-0001, and reasonable engineers could land on
Glue for the single-engine consistency argument alone — record whichever
way you two land on below.

## Decision

*(To be filled in by the two engineers.)*

- Chosen option:
- Date decided:
- Rationale:

## Consequences

- If Athena is confirmed: harden `dbt/profiles.yml.example` with
  `num_retries` capped and a note pinning the Athena workgroup to engine
  v3; no infra changes needed.
- If Glue is chosen instead: `dbt/profiles.yml.example` needs a full
  rewrite to the `type: glue` shape above; verify the DynamoDB lock
  question first (may require a new `modules/dynamodb/` or extending
  `modules/orchestrator/` in `tmdb-data-platform-infra`); and
  `docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md`'s
  "distinct, hireable skill" rationale should be revisited/amended since it
  assumed Athena specifically.
- Either way, the three concrete bug workarounds (or the Glue equivalent
  hardening once evaluated) should be captured as a runbook item once
  `docs/operations/runbook.md` is written (currently deferred to Phase 7).

## Sources

- [dbt-adapters #1739 — ICEBERG_FILESYSTEM_ERROR retry bug](https://github.com/dbt-labs/dbt-adapters/issues/1739)
- [dbt-adapters #1813 — Athena query timeout retry bug](https://github.com/dbt-labs/dbt-adapters/issues/1813)
- [dbt-athena known issues](https://dbt-athena.github.io/docs/known-issues)
- [dbt-athena Iceberg materialization config](https://dbt-athena.github.io/docs/configuration/materializations/iceberg)
- [dbt-glue setup docs (dbt Developer Hub)](https://docs.getdbt.com/docs/local/connect-data-platform/glue-setup)
- [AWS: dbt-glue as a "trusted" dbt adapter](https://aws.amazon.com/blogs/big-data/build-and-manage-your-modern-data-stack-using-dbt-and-aws-glue-through-dbt-glue-the-new-trusted-dbt-adapter/)
- [AWS Glue interactive session pricing](https://docs.aws.amazon.com/glue/latest/dg/interactive-sessions-session-pricing.html)
- [Amazon Athena pricing](https://aws.amazon.com/athena/pricing/)
