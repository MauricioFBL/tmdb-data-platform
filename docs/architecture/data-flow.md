# Data Flow

Traces how a single movie record actually moves through the platform, for
each of the three flows `PROJECT_PLAN.md` Section 12 defines. This is the
sequential/temporal companion to `architecture-overview.md`'s structural
component view.

## Flow 1 — Initial Load (Milestone 1 scope, `PROJECT_PLAN.md` Section 20)

```text
1. Download Daily Movie ID Export
   (files.tmdb.org/p/exports/movie_ids_MM_DD_YYYY.json.gz — see
   docs/source-analysis/tmdb-api-overview.md)
2. Filter to project scope (release year / vote count / language /
   country / adult-content exclusion / max ID count — PROJECT_PLAN.md
   Section 9's explicit engineering decision, not "ingest everything")
3. Create extraction batches
4. For each movie_id in scope:
   a. GET /movie/{movie_id} (+ append_to_response for credits/keywords/
      release_dates/external_ids where practical, per
      docs/source-analysis/endpoint-inventory.md's note on cutting
      request volume)
   b. Write raw JSON response to S3, verbatim, with technical metadata
      (pipeline_run_id, request_id, endpoint, extraction_timestamp)
5. Bronze Glue job: parse raw JSON -> bronze_movie_details (typed,
   nested arrays separated, no business logic)
6. Silver Glue job:
   a. Compute record_hash over historical attributes
      (docs/deep-dives/scd2-iceberg-merge-patterns.md)
   b. Since this is the first version for every movie_id: insert into
      dim_movie_scd2 with valid_from = extraction_timestamp,
      valid_to = NULL, is_current = true, version_number = 1
7. Quality checks (docs/modeling/scd-strategy.md's invariants: exactly
   one current row per key, no overlapping validity windows)
8. Query dim_movie_scd2 via Athena -> confirms the full path works
```

This flow alone is what Milestone 1 (`PROJECT_PLAN.md` Section 20)
demonstrates end to end, including simulating a source change and
verifying the SCD2 close-and-reopen mechanics — see that section for the
exact acceptance steps.

## Flow 2 — Daily Incremental Load

```text
1. Read previous watermark (last successful run's timestamp)
2. GET /movie/changes?start_date=<watermark>&end_date=<today>
   (bulk discovery endpoint — confirmed in
   docs/source-analysis/tmdb-api-overview.md to return "all movie ids
   that have been changed" in the window; NOT the per-movie
   /movie/{id}/changes endpoint)
   - if watermark is >14 days old, this step cannot succeed as a single
     query (TMDB's 14-day max span) -> fall back to a full re-scan via
     the Daily ID Export instead (Flow 1), and alarm on this condition
     rather than silently degrading
3. Collect the list of changed movie_ids from the (paginated, 100/page)
   response
4. For each changed movie_id: GET /movie/{movie_id} (same as Flow 1
   step 4a) -- the incremental load re-fetches full current state, it
   does not attempt to apply the per-field change deltas
5. Store new raw responses in S3 (same technical metadata pattern)
6. Bronze Glue job: same parsing as Flow 1, scoped to only the changed
   batch
7. Silver Glue job -- the actual SCD2 merge, per
   docs/deep-dives/scd2-iceberg-merge-patterns.md:
   a. Stage changed_batch (new keys + keys whose record_hash differs
      from the current dim_movie_scd2 row)
   b. Close superseded current versions (is_current = false,
      valid_to = run_ts)
   c. Insert new current versions (is_current = true,
      valid_from = run_ts, version_number + 1)
8. Capture the day's movie_metrics_daily snapshot (popularity,
   vote_average, vote_count) for every movie touched -- this happens
   regardless of whether the SCD2 attributes changed, since these
   metrics are snapshotted independently (docs/modeling/scd-strategy.md)
9. Run quality checks (same invariants as Flow 1)
10. Advance the watermark -- ONLY after steps 6-9 succeed
    (PROJECT_PLAN.md Section 9: "The watermark must only be updated
    after a successful pipeline run")
11. Compaction/maintenance job runs -- sequenced strictly AFTER step 7's
    merge commits, never concurrently (see
    docs/deep-dives/iceberg-internals-and-glue.md Section 4/5 and
    docs/deep-dives/scd2-iceberg-merge-patterns.md's closing section --
    this is a real dependency edge in whichever orchestrator ADR-0001
    selects, not an implementation detail)
```

## Flow 3 — Streaming Availability (weekly, historized relationship)

```text
1. Select the movie population to refresh (PROJECT_PLAN.md Section 9:
   weekly refresh is an accepted staleness trade-off for the MVP)
2. GET /movie/{movie_id}/watch/providers for each movie in scope
3. Store raw responses in S3
4. Bronze Glue job: parse into bronze_watch_providers
5. Silver Glue job -- "close removed, insert new" pattern
   (docs/modeling/scd-strategy.md), NOT a hash-diff merge:
   a. Compare the latest extraction against current
      silver_movie_provider_availability rows
      (movie_id + provider_id + country_code + availability_type)
   b. Close any current row not present in the latest extraction
      (is_current = false, valid_to = run_ts)
   c. Insert any newly observed combination
      (is_current = true, valid_from = run_ts)
6. Refresh the streaming_availability Gold mart (dbt) -- this is a
   distinct step from Silver, since Gold marts are dbt models per
   ADR-0002, run on their own schedule against the now-updated Silver
   table
```

## Where Gold fits (all three flows converge here)

None of the three flows above write to Gold directly. Gold refresh
(`dbt run` against `dbt/models/marts/`) is a separate, downstream step that
reads whatever the current state of Silver is at query time -- it is not
triggered per-flow, but on its own schedule (or on-demand), per
`docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md`.
This means Gold marts can lag behind the most recent Silver merge by
however long the orchestrator waits before the next `dbt run` -- an
explicit, acceptable staleness window that should be documented wherever
a mart is consumed (dashboard, ad hoc query), not assumed to be real-time.
