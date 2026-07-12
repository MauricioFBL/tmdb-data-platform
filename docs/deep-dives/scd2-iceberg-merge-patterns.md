# SCD Type 2 Merge Patterns on Iceberg

> **STALE — pending rewrite (sprint task).** [ADR-0005](../architecture/architecture-decisions/adr-0005-silver-moves-to-dbt.md)
> moved Silver's SCD2 processing from hand-rolled PySpark `MERGE INTO`
> (described below) to dbt snapshots via `dbt-glue`. The conceptual content
> here (hash-diff reasoning, overlap bugs, late-arriving-data risk,
> compaction sequencing) is still valid and directly informs how the dbt
> snapshot's source query must be designed — but the concrete SQL/PySpark
> below no longer reflects the actual implementation. Do not copy the code
> below as-is; treat it as the design rationale a dbt snapshot
> implementation must satisfy.

This doc exists because `dim_movie_scd2` and `dim_person_scd2`
(`docs/modeling/scd-strategy.md`) are the hardest transformation in the
platform: multi-attribute hash-diff change detection, correct
`valid_from`/`valid_to` bounds, exactly one current row per business key, no
overlapping validity periods, and idempotent re-runs — all against an
Iceberg table under the merge-on-read configuration recommended in
`docs/deep-dives/iceberg-internals-and-glue.md`. This is implementation
guidance for the PySpark jobs in `glue/silver/`, not an SCD2 tutorial.

## Why hash-diff, not column-by-column comparison

`dim_movie_scd2` tracks 16 historical attributes (`docs/modeling/scd-strategy.md`).
Comparing each column individually (`old.title <> new.title OR old.status
<> new.status OR ...`) is correct but unreadable, error-prone to extend
(every new attribute requires editing the comparison predicate in two
places), and doesn't handle NULLs consistently unless every comparison is
null-safe (`<=>` in Spark SQL, not `<>`). The standard fix: compute a single
`record_hash` over all historical attributes at write time, on both the
incoming batch and the current dimension state, and compare hashes.

```python
from pyspark.sql import functions as F

HISTORICAL_ATTRS = [
    "title", "original_title", "overview", "tagline", "status",
    "release_date", "runtime", "budget", "revenue", "adult", "video",
    "homepage", "poster_path", "backdrop_path", "original_language",
    "collection_id",
]

def with_record_hash(df):
    # coalesce every attribute to a sentinel before hashing so that
    # NULL vs NULL doesn't silently break equality semantics inside sha2,
    # and casting to string normalizes types (int vs long, etc.) across
    # a batch that may have come through slightly different schema paths.
    concat_expr = F.concat_ws(
        "||", *[F.coalesce(F.col(c).cast("string"), F.lit("¤NULL¤")) for c in HISTORICAL_ATTRS]
    )
    return df.withColumn("record_hash", F.sha2(concat_expr, 256))
```

Apply this to both sides — the incoming, deduplicated batch (`source`) and
the current-state rows of `dim_movie_scd2` (`target`) — before the merge.
A changed record is simply `target.record_hash <> source.record_hash` for
matching business keys; a new record is a business key with no match at
all.

## The two-step merge (why one `MERGE INTO` isn't enough)

A naive single `MERGE INTO` can insert new versions, but it **cannot**
both close an old version (`is_current = false, valid_to = now`) and insert
the new version (`is_current = true, valid_from = now`) for the same
business key in one statement — that would require the merge to both
UPDATE and INSERT against the same matched key, which standard `MERGE INTO`
semantics don't allow in a single `WHEN MATCHED` branch for a changed row.
The reliable pattern is two Iceberg operations against a staged batch:

1. **Stage the batch** as a temp view: only rows that are either brand-new
   business keys or have a changed `record_hash` against the current
   dimension state. Unchanged rows are dropped here — they generate no
   write at all, which matters directly for the merge-on-read cost model in
   `iceberg-internals-and-glue.md` (fewer touched files/positions per run).

```sql
CREATE OR REPLACE TEMP VIEW changed_batch AS
SELECT s.*
FROM source_batch s
LEFT JOIN glue_catalog.silver.dim_movie_scd2 t
  ON s.tmdb_movie_id = t.tmdb_movie_id AND t.is_current = true
WHERE t.tmdb_movie_id IS NULL                      -- brand new key
   OR t.record_hash <> s.record_hash;               -- changed key
```

2. **Close the superseded current version** — an `UPDATE`, not a `MERGE`,
   scoped only to keys present in `changed_batch`:

```sql
MERGE INTO glue_catalog.silver.dim_movie_scd2 t
USING (SELECT DISTINCT tmdb_movie_id FROM changed_batch) c
ON t.tmdb_movie_id = c.tmdb_movie_id AND t.is_current = true
WHEN MATCHED THEN UPDATE SET
  t.is_current = false,
  t.valid_to = current_timestamp(),
  t.updated_at = current_timestamp();
```

3. **Insert the new current version** for every row in `changed_batch`
   (both brand-new keys and changed keys get a fresh row here):

```sql
INSERT INTO glue_catalog.silver.dim_movie_scd2
SELECT
  monotonically_increasing_id() AS movie_sk,   -- see surrogate-key note below
  tmdb_movie_id, title, original_title, overview, tagline, status,
  release_date, runtime, budget, revenue, adult, video, homepage,
  poster_path, backdrop_path, original_language, collection_id,
  current_timestamp() AS valid_from,
  CAST(NULL AS timestamp) AS valid_to,
  true AS is_current,
  version_number + 1 AS version_number,          -- 1 if brand new (coalesce upstream)
  record_hash,
  current_timestamp() AS created_at,
  current_timestamp() AS updated_at,
  '{{ pipeline_run_id }}' AS pipeline_run_id
FROM changed_batch;
```

Both statements run inside the **same Spark job invocation**, back to back
— this is what makes the pair idempotent as a unit: if the job fails
between step 2 and step 3, the next run's `changed_batch` computation
(step 1) will still detect the closed-but-not-reopened key as "changed"
(its `is_current = true` row no longer exists, so the `LEFT JOIN` in step 1
sees it as a brand-new key) and re-insert it, self-healing the gap. This is
why `version_number + 1` must be computed defensively (`coalesce` against
the closed row's version if present, else `1`), not assumed monotonic
across a clean run.

`monotonically_increasing_id()` is fine for a portfolio project's scale but
is not globally unique across separate Spark applications — if the daily
job and a backfill job ever run concurrently, switch to a hash-based
surrogate key (`sha2(concat(tmdb_movie_id, valid_from), 256)`) instead.
Note this as an explicit, deferred decision rather than silently shipping
a key scheme that only works by accident of single-writer scheduling.

## Overlapping-validity-period bugs — the two ways this actually breaks

1. **Clock skew between step 2 and step 3.** If `current_timestamp()` is
   evaluated separately for the UPDATE and the INSERT (which it is, as two
   statements), there is a small but real gap where a query between the two
   statements sees **zero** current rows for a just-changed key, not an
   overlap — but if the job is ever restructured to compute `valid_from` for
   the new row *before* `valid_to` for the old row using an earlier
   timestamp, that ordering bug produces a real overlap. Guard against this
   with a single captured timestamp variable in the job (`run_ts =
   current_timestamp()` computed once in Python, passed as a literal into
   both SQL statements), not two independent `current_timestamp()` calls.
2. **Late-arriving data / out-of-order reprocessing.** If a backfill job
   reprocesses an older `Movie Changes` batch after a newer one has already
   been applied (e.g., replaying a failed day after today's run already
   succeeded), inserting the "late" version with `valid_from = run_ts` would
   place it *after* a version that's chronologically newer, corrupting the
   validity sequence. The batch's own source timestamp (TMDB's change
   `time`, not the pipeline's wall-clock `run_ts`) should drive
   `valid_from`, and any batch whose source timestamp is older than the
   current version's `valid_from` must be routed to a manual-review/
   reprocessing path instead of being merged automatically — this is a
   real gap in the naive pattern above and should be an explicit data
   quality check (`docs/modeling/scd-strategy.md`'s overlap test), not
   assumed away.

## Tests that must exist (mirrors `scd-strategy.md`, made concrete here)

```sql
-- exactly one current row per key
SELECT tmdb_movie_id, count(*) FROM dim_movie_scd2
WHERE is_current = true GROUP BY tmdb_movie_id HAVING count(*) > 1;
-- expect 0 rows

-- no overlapping validity windows per key
SELECT a.tmdb_movie_id FROM dim_movie_scd2 a
JOIN dim_movie_scd2 b
  ON a.tmdb_movie_id = b.tmdb_movie_id AND a.movie_sk <> b.movie_sk
WHERE a.valid_from < coalesce(b.valid_to, timestamp'9999-12-31')
  AND coalesce(a.valid_to, timestamp'9999-12-31') > b.valid_from;
-- expect 0 rows

-- every closed version has a non-null valid_to
SELECT * FROM dim_movie_scd2 WHERE is_current = false AND valid_to IS NULL;
-- expect 0 rows
```

Run these as Glue-invoked checks in `sql/quality/` after every Silver merge
— per `docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md`,
this is Silver-layer quality, not a dbt test, since dbt has no visibility
into this layer.

## Interaction with compaction (do not skip this)

`docs/deep-dives/iceberg-internals-and-glue.md` Section 4/5 documents that
Glue's own guidance is to never run compaction concurrently with a merge
against the same table. For this job specifically: the three-statement
pattern above (stage, close, insert) must complete and commit fully before
any scheduled compaction job for `dim_movie_scd2` is allowed to start — a
real dependency edge in the orchestrator's DAG/asset graph
(`docs/architecture/architecture-decisions/adr-0001-orchestrator-choice.md`),
not just an implementation detail of this job.
