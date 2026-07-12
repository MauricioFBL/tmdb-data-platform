# Apache Iceberg Internals and AWS Glue Integration

This doc exists because the platform's Silver layer runs daily `MERGE INTO`
operations for SCD Type 2 (`dim_movie_scd2`, `dim_person_scd2`) against
Iceberg tables in Glue. That workload — high write frequency, row-level
updates, long-lived tables with slowly growing schema — sits exactly on top
of the parts of Iceberg that are easiest to misconfigure. This is a
reference for implementing against it, not an introduction to what Iceberg
is.

## 1. Table format fundamentals

Iceberg tracks table state through four layers, each one immutable once
written:

```
table metadata file (*.metadata.json)
    -> current snapshot
        -> manifest list (avro)
            -> manifest file(s) (avro)
                -> data files (parquet/orc/avro)
```

- **Table metadata file**: the root pointer. Contains the schema history
  (every schema version ever used, each with stable field IDs), the
  partition spec history, table properties, and a pointer to the *current
  snapshot ID*. A new metadata file is written on every commit; the catalog
  (Glue Data Catalog, in this project) just needs to atomically swap which
  metadata file location is "current" for the table.
- **Snapshot**: an immutable, complete view of the table at one point in
  time. A snapshot doesn't store rows — it points to exactly one manifest
  list. Every commit (append, overwrite, delete, `MERGE INTO`) produces a
  new snapshot; old snapshots stay valid and queryable until expired, which
  is what gives you time travel (`VERSION AS OF` / `TIMESTAMP AS OF` in
  Spark SQL).
- **Manifest list**: an index over manifest files for one snapshot. Stores
  per-manifest stats (partition value ranges, row counts) so a query
  planner can prune whole manifests without opening them.
- **Manifest file**: lists actual data files, each with column-level stats
  (min/max, null counts) and the partition values for that file. This is
  what lets Iceberg prune at the file level without a Hive-style
  partition-directory listing on S3.

**Why this matters for concurrent writes**: there is no lock server in the
default configuration. A writer reads the current metadata pointer, builds
new manifests/snapshot, and does an atomic compare-and-swap on the "current
metadata" pointer (optimistic concurrency). If another writer committed
first, the second writer's commit is rejected and must retry against the
new base. This is directly relevant to this project once both the daily
SCD2 merge job and a compaction/maintenance job can touch the same table —
see Section 5.

## 2. Schema and partition evolution

- **Schema evolution** is safe by construction: every column has a
  permanent field ID, independent of its name or position. Renaming a
  column, adding a column, widening a type (int → long), or dropping a
  column are all metadata-only operations — no data files are rewritten.
  Old data files are read using the schema they were written with, mapped
  onto the current schema by field ID. This matters directly for
  `dim_movie_scd2`: attributes can be added later (the project explicitly
  expects this — see `PROJECT_PLAN.md` Section 10's "candidate historical
  attributes" list, which is not meant to be exhaustive on day one) without
  a backfill/rewrite of existing SCD2 history.
- **Partition evolution**: Iceberg decouples the logical partition columns
  from physical file layout ("hidden partitioning" — you don't need a
  `WHERE extraction_date = '...'` filter matching a literal directory path;
  Iceberg derives partition values from real columns via transforms like
  `day(extraction_date)`, `bucket(16, movie_id)`). Changing the partition
  spec (e.g., going from daily to monthly partitioning as a table grows)
  only affects files written after the change — old files keep their
  original spec ID, and Iceberg's planner mixes specs transparently at read
  time. There is no partition-migration job to run. The practical
  implication: don't over-design the initial partition spec for Bronze/
  Silver tables; it can change later without a rewrite.

## 3. How `MERGE INTO` actually executes

Iceberg supports two execution strategies for `MERGE INTO` / `UPDATE` /
`DELETE`, controlled by table properties (`write.merge.mode`,
`write.update.mode`, `write.delete.mode`), each independently settable:

- **Copy-on-write (CoW)** — the default for all three operations as of
  current Iceberg releases. Any data file containing at least one row that
  matches the operation gets fully rewritten (unaffected rows in that file
  are copied through unchanged). Reads afterward see a normal table with no
  extra work. Write cost scales with *how many files contain a matched
  row*, not with how many rows changed — a `MERGE` that touches one row in
  each of 500 files rewrites all 500 files.
- **Merge-on-read (MoR)** — set `write.merge.mode=merge-on-read` (and the
  update/delete equivalents) to instead write small **delete files**
  (position deletes or equality deletes) that mark old rows as removed,
  plus new data files for inserted/updated rows. Commits are cheap and
  fast. The cost moves to read time: every read has to reconcile data files
  against their delete files, and this reconciliation cost grows until a
  compaction job rewrites the delete files away.

**For this project's daily SCD2 merge**: the incoming batch from `Movie
Changes` is typically a small fraction of the table (only changed movie
IDs, per `PROJECT_PLAN.md` Section 9's incremental load flow), so the
matched rows are scattered across many files in a table that grows over
time — the worst case for copy-on-write's "rewrite every touched file"
cost. Merge-on-read keeps the daily job fast and bounded by the size of the
day's change set, at the cost of needing a real compaction schedule (see
Section 5) — without one, query latency on `dim_movie_scd2` degrades
silently as unmerged delete files accumulate. Recommendation: start with
`write.merge.mode=merge-on-read` on the SCD2 tables specifically, paired
with a non-optional weekly compaction job — treat compaction as part of the
SCD2 pipeline's definition of done, not an optional extra.

## 4. AWS Glue + Iceberg integration specifics

Glue version determines the bundled Iceberg version — this is not
independently upgradable without supplying your own JARs:

| Glue version | Bundled Iceberg version |
|---|---|
| 3.0 | 0.13.1 |
| 4.0 | 1.0.0 |
| 5.0 | 1.7.1 |
| 5.1 | 1.10.0 |

Concrete implication: **target Glue 4.0 or later.** Glue 3.0's Iceberg
0.13.1 does not support `ALTER TABLE ... RENAME TO`, and — more importantly
for this project — Glue 3.0 requires manually wiring a DynamoDB-backed lock
manager (`DynamoLockManager`) for safe concurrent commits, because
optimistic locking via the Glue Data Catalog isn't the default until Glue
4.0+. Since this project already plans a `glue-catalog` module and no
DynamoDB table, staying on 4.0+ avoids that extra piece of infrastructure
entirely.

Enabling Iceberg on a Glue job requires both a job parameter and Spark
config, not just adding a JAR:

```
--datalake-formats iceberg

--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
--conf spark.sql.catalog.glue_catalog=org.apache.iceberg.spark.SparkCatalog
--conf spark.sql.catalog.glue_catalog.warehouse=s3://<bucket>/silver/
--conf spark.sql.catalog.glue_catalog.catalog-impl=org.apache.iceberg.aws.glue.GlueCatalog
--conf spark.sql.catalog.glue_catalog.io-impl=org.apache.iceberg.aws.s3.S3FileIO
```

Known rough edges to plan around, not theoretical risks:

- **Concurrent write conflicts** are the most commonly reported real-world
  issue: if the SCD2 merge job and a compaction/maintenance job (Section 5)
  run against the same table concurrently, one of them gets a commit
  conflict and must retry. AWS's own guidance is to **schedule merges and
  compaction sequentially, never in parallel**, on the same table — this
  becomes an orchestrator-level constraint (a real dependency edge in the
  DAG/asset graph), not just a Spark-level concern.
- Lake Formation fine-grained access control on Iceberg tables changed
  materially between Glue 4.0 and 5.0 (different configuration paths) — if
  Lake Formation permissions are ever introduced, re-check the version-
  specific docs rather than assuming the Glue 4.0 pattern still applies.

## 5. Maintenance operations

Under daily `MERGE INTO` writes (especially in merge-on-read mode), an
Iceberg table accumulates small data files and delete files. This is not
optional cleanup — an un-compacted table degrades in query latency over
weeks, silently, with no error until someone notices Athena queries got
slow.

- **Compaction (`rewrite_data_files`)**: AWS Glue's managed Data Catalog
  compaction kicks in automatically once a table or partition exceeds 100
  files where files are smaller than 75% of the target file size — this can
  be enabled per-table as a Glue "table optimizer" instead of a hand-rolled
  Glue job, which is the simpler starting point for a two-person team.
  If running compaction as an explicit Spark job instead: narrow the scope
  with a `WHERE` clause (e.g., only recent partitions) to reduce the chance
  of conflicting with the concurrently-running merge job, and expect
  occasional `partial-progress.enabled` commit failures under load — the
  documented fix is raising `partial-progress.max-commits` so the rewrite
  splits into more, smaller commits instead of one large one.
- **Snapshot expiration**: without it, every daily commit's snapshot (and
  the manifests/data files it uniquely references) is retained forever,
  which is both an S3 cost problem and, eventually, a metadata-size problem
  for the table metadata JSON itself. Needs a retention policy (e.g., expire
  snapshots older than 7-14 days) from the start, not deferred — this
  project's daily incremental load (`PROJECT_PLAN.md` Section 9) guarantees
  daily snapshot growth from day one.
- **Orphan file cleanup**: removes data/manifest files that exist in S3 but
  are no longer referenced by any live snapshot (left behind by failed or
  superseded commits). Lower urgency than the two above; safe to defer to
  Phase 5+ but should not be forgotten entirely.

## Implications for this project

- Target **AWS Glue 4.0 or later** for the Silver/SCD2 jobs — avoids the
  DynamoDB lock manager requirement and gets optimistic-locking-by-default
  concurrency control.
- Set `write.merge.mode=merge-on-read` (and `write.update.mode`,
  `write.delete.mode` to match) on `dim_movie_scd2` and `dim_person_scd2`
  specifically, given the daily-batch-touches-scattered-files access
  pattern described in Section 3. Bronze tables, which are append-mostly,
  can stay on the copy-on-write default.
- Compaction is not a "nice to have" backlog item — it needs to exist
  before Phase 3 (Silver and SCD2) is considered done, either as AWS Glue's
  managed table-optimizer or a scheduled Glue job, and it must be
  **sequenced strictly after** the daily merge job in whichever orchestrator
  is chosen (see [ADR-0001](../architecture/architecture-decisions/adr-0001-orchestrator-choice.md)),
  never run in parallel with it.
- Snapshot expiration needs a retention policy decision (suggest starting
  at 14 days, enough to cover `PROJECT_PLAN.md`'s replay/reprocessing
  requirement in Section 8 without unbounded growth) — this should be
  written down as a config value in `config/tables.yml`, not hard-coded in
  a job script.
- Orphan file cleanup can be deferred to Phase 5 or later without risk.

## Sources

- [Apache Iceberg Table Spec](https://iceberg.apache.org/spec/)
- [AWS Glue: Using the Iceberg framework in AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html)
- [Apache Iceberg: Spark Writes](https://iceberg.apache.org/docs/latest/spark-writes/)
- [AWS: Manage concurrent write conflicts in Apache Iceberg on the AWS Glue Data Catalog](https://aws.amazon.com/blogs/big-data/manage-concurrent-write-conflicts-in-apache-iceberg-on-the-aws-glue-data-catalog/)
- [AWS Glue: Optimizing Iceberg tables (table optimizers, compaction thresholds)](https://docs.aws.amazon.com/glue/latest/dg/table-optimizers.html)
