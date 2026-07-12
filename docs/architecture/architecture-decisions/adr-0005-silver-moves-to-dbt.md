# ADR-0005: Silver Moves to dbt (via dbt-glue); Bronze Stays PySpark

## Status

Accepted — 2026-07-11. Supersedes
[ADR-0002](./adr-0002-dbt-for-gold-marts.md).

## Context

ADR-0002 kept Silver's SCD Type 2 processing as hand-rolled PySpark,
reasoning that "dbt snapshots... tracking many attributes with custom
hash-diff logic... is a known rough edge." That claim was overstated — it
was corrected in conversation before this ADR was written: dbt-athena and
dbt-glue both support the `snapshot` materialization on Iceberg tables with
a `check` strategy and `check_cols` accepting an arbitrary column list
(including `'all'`), so 16 tracked attributes on `dim_movie_scd2` is not
mechanically a problem for either adapter.

After discussion, the decision is to move Silver to dbt as well, running
through `dbt-glue` (same engine as Bronze), rather than keep the
hand-rolled PySpark `MERGE INTO` approach designed in
`docs/deep-dives/scd2-iceberg-merge-patterns.md`. The corrected reasoning
below is what should have been in ADR-0002 from the start — verified
against independent sources, not asserted from memory:

**dbt snapshots' real limitation is out-of-order/backdated records, not
column count.** An independent write-up on building a custom SCD2
materialization for dbt ([Kateryna, "Enhancing SCD2 in dbt"](https://drogaieva.medium.com/enhancing-scd2-in-dbt-custom-materialization-for-creating-complex-slowly-changing-dimensions-type-2ef998bbc660))
states plainly that standard dbt snapshots "fail to address nuanced
scenarios where mixed strategies, out of order and duplicate records are
involved" — backdated/late-arriving updates are exactly the failure mode
`scd2-iceberg-merge-patterns.md` already identified as a real risk (TMDB's
`Movie Changes` bulk feed reprocessed out of order after a newer batch
already landed). This is a genuine, independently-confirmed limitation of
the built-in `snapshot` feature, and it does not disappear by moving
engines — it has to be designed around explicitly, in the snapshot's
source-query definition, regardless of adapter.

**A separate, real-world data point worth knowing before scaling up**: a
production team ([Ministry of Justice Data Engineering](https://ministryofjustice.github.io/data-and-analytics-engineering/blog/posts/building-a-transaction-data-lake-using-amazon-athena-apache-iceberg-and-dbt/))
compared Glue Spark against Athena specifically for SCD2-on-Iceberg and
found "Glue Spark encountered out-of-memory issues at the higher end of
our volume range" (tables up to ~200GB), which led them to migrate that
workload to Athena. This project's TMDB movie catalog at portfolio scale
is far below that volume range, so this is **not a blocker** — but it's a
real signal to revisit if the project ever scales toward a fuller TMDB
catalog ingestion, and it should be written down now rather than
discovered the hard way later.

**dbt-glue does support Iceberg snapshots** — confirmed via the adapter's
own source (`aws-samples/dbt-glue`, `snapshot.sql` materialization macro):
both `timestamp` and `check_cols` strategies, same shape as dbt-athena's.
AWS's own guidance for this feature recommends enabling **commit locking**
on Iceberg tables "to prevent concurrent execution conflicts" in
production — this is a point in favor of treating the DynamoDB lock table
ADR-0004 flagged as an open question as **needed by default**, not legacy
cruft to strip out, pending final verification against a real session.

## Decision

- **Bronze**: unchanged — PySpark/Glue, raw JSON parsing, no dbt
  involvement (dbt cannot do nested-array explosion of TMDB's raw payloads
  usefully; this was never in question).
- **Silver**: dbt, via `dbt-glue`, specifically:
  - `dim_movie_scd2`, `dim_person_scd2`, `dim_provider_scd2` → dbt
    **snapshots**, `strategy='check'`, `check_cols` set to each
    dimension's historical attribute list from
    `docs/modeling/scd-strategy.md`, `file_format='iceberg'`.
  - Historized relationships (streaming availability, release dates) →
    also modeled as dbt snapshots; the "close removed, insert new"
    semantics need to be mapped onto dbt's snapshot mechanics explicitly
    (verify whether `invalidate_hard_deletes` fits this cleanly or whether
    it needs a custom source-query shape) — **not yet a solved design**,
    tracked as an explicit sprint task rather than assumed.
  - **Disambiguation, since the vocabulary now collides**: `movie_metrics_daily`
    (the append-only popularity/vote-count time series) is a "snapshot
    fact" in the data-warehouse sense (`docs/modeling/scd-strategy.md`),
    **not** a dbt `snapshot` — it should be a plain dbt **incremental
    model** (`incremental_strategy='append'`), never the `snapshot`
    materialization. Keep this distinction explicit in code review; the
    naming collision is a real source of confusion between the two
    engineers going forward.
  - **The out-of-order guard is not free** — per the Context section
    above, it must be hand-designed into each snapshot's source-query
    definition (e.g., excluding any incoming row whose TMDB `time` field
    is older than what's already recorded), not assumed to come from the
    `snapshot` feature itself.
- **Gold**: unchanged in scope (the five marts, per ADR-0002/
  `docs/modeling/data-marts.md`), now running on the same `dbt-glue`
  engine as Silver (see [ADR-0004](./adr-0004-dbt-iceberg-engine-athena-vs-glue.md),
  which this decision resolves in Glue's favor).

## Consequences

- **Repo restructuring** (tracked as sprint tasks, not done speculatively
  in this ADR): `glue/silver/` is removed — Bronze is PySpark's only
  remaining layer. A new `dbt/snapshots/` directory holds the SCD2 and
  historized-relationship definitions. `dbt/profiles.yml.example` needs a
  full rewrite to the `type: glue` shape from ADR-0004.
- **Documentation debt, acknowledged explicitly rather than silently
  left stale**: `docs/deep-dives/scd2-iceberg-merge-patterns.md`,
  `docs/modeling/scd-strategy.md`, `docs/architecture/architecture-overview.md`,
  `docs/architecture/data-flow.md`, and `PROJECT_PLAN.md` Sections 6/10/12/15
  all still describe hand-rolled PySpark `MERGE INTO` for Silver. They are
  now inaccurate and need rewriting for dbt-snapshot-based Silver. This is
  real, non-trivial writing (not a find-and-replace) and is deliberately
  **not** done inline in this ADR — it's the first sprint ticket, so it
  gets done carefully rather than rushed.
- **Terraform**: a Glue interactive-session IAM role is needed for
  dbt-glue (distinct from a classic Glue ETL job role). If commit locking
  is confirmed necessary, `tmdb-data-platform-infra` needs a DynamoDB
  table module that doesn't exist today.
- **Portfolio-signal trade-off, stated honestly**: this swaps "we
  hand-wrote a distributed SCD2 merge engine in PySpark against Iceberg"
  for "we identified dbt snapshot's real out-of-order limitation, designed
  around it, and ran SCD2 at scale through Glue-backed dbt." Both are
  legitimate, demonstrable modeling work — this is a different story, not
  a lesser one, but it is a real change from what ADR-0002 originally
  intended to showcase, and should be described accurately in any
  portfolio write-up rather than glossed over.
- **Scale risk to monitor, not act on now**: the MoJ Glue-Spark-OOM finding
  above. Revisit the Silver engine choice if TMDB ingestion volume ever
  grows toward a large fraction of the full catalog.

## Sources

- [Kateryna — "Enhancing SCD2 in dbt: Custom Materialization for Complex SCD2"](https://drogaieva.medium.com/enhancing-scd2-in-dbt-custom-materialization-for-creating-complex-slowly-changing-dimensions-type-2ef998bbc660)
- [Ministry of Justice — Building a transaction data lake using Athena, Iceberg and dbt](https://ministryofjustice.github.io/data-and-analytics-engineering/blog/posts/building-a-transaction-data-lake-using-amazon-athena-apache-iceberg-and-dbt/)
- [aws-samples/dbt-glue (adapter source, incl. snapshot materialization)](https://github.com/aws-samples/dbt-glue)
- [dbt-athena known issues (snapshot support confirmation)](https://dbt-athena.github.io/docs/configuration/snapshots)
