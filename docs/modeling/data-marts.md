# Data Marts

Formalizes `PROJECT_PLAN.md` Section 11. All five marts below are **dbt
models** under `dbt/models/marts/`, materialized as tables in the Gold
Athena schema, reading from Silver Iceberg tables via
`dbt/models/staging/` — see
`docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md`
for why dbt owns this layer and not PySpark/Glue.

Every mart below must have its dbt `schema.yml` document the grain
explicitly (as a table-level description, not just column tests) — a mart
without a documented grain is not done, per `PROJECT_PLAN.md` Section 18.

## `movie_lifecycle` — `dbt/models/marts/movie_lifecycle/`

**Grain**: one row per `movie_id` (current-state summary) *plus* a
companion event-log model at grain `movie_id + event_type + event_date` for
the underlying transitions — the mart is really two models: a
current-state table and a history table, because "how long did a movie
stay in each status" is a different query shape than "what is a movie's
current lifecycle stage."

Reads from: `dim_movie_scd2` (all versions, not just current — this is why
it can't be a simple `SELECT *` staging view), the release-date historized
relationship, the streaming-availability historized relationship, and
`fact_movie_metrics_daily`.

Answers: how long a movie remains in each status; how often its release
date changes and by how many days; when runtime/budget/revenue first
became non-null (a materiality signal that a zero isn't a true zero, per
the Movie Performance rule below); when it first appeared on any streaming
provider.

## `movie_performance` — `dbt/models/marts/movie_performance/`

**Grain**: one row per `movie_id` (a movie's performance is evaluated once
its metadata has stabilized, not per historical version — performance
analysis is not itself historized in the MVP).

Metrics: `budget`, `revenue`, `estimated_profit` (`revenue - budget`),
`estimated_roi` (`estimated_profit / budget`), `popularity`,
`vote_average`, `vote_count` (latest snapshot values, joined from
`fact_movie_metrics_daily`).

Dimensions: genre, release_year, country, language, company, collection.

**Critical rule carried over from `PROJECT_PLAN.md` Section 11**: a source
value of `0` for `budget` or `revenue` must be treated as missing data, not
a true zero, before computing `estimated_roi` (division by a false zero
would be nonsensical, and a false zero revenue would deflate every
profit/ROI figure). This must be a `case when budget = 0 then null else
budget end`-style guard in the dbt model itself, and a corresponding dbt
test asserting `estimated_roi` is null (not zero or negative-infinity) when
the source budget was zero.

## `talent_collaboration` — `dbt/models/marts/talent_collaboration/`

**Grain**: one row per `person_id_a + person_id_b + collaboration_type`
(e.g. actor-actor, actor-director pairs) — a self-join of the Credit
relationship against itself per movie, aggregated across movies.

Reads from: `dim_person_scd2` (current version only — career-stage
analysis uses `known_for_department` as of now, not historically), the
Credit relationship, `dim_movie_scd2` for vote_average weighting.

Answers: most frequent actor-actor and actor-director pairs; directors with
the highest vote-weighted average rating; people credited across multiple
departments (e.g. actor who also directs); a person's credited-movie count
over time (using `release_date` as the time axis, not the person's SCD2
version history).

## `streaming_availability` — `dbt/models/marts/streaming_availability/`

**Grain**: one row per `provider_id + country_code + snapshot_date` for the
catalog-size time series, plus a companion `movie_id`-grain model for
per-title questions (exclusivity, tenure on a given provider).

Reads from: the streaming-availability historized relationship (Silver),
`dim_provider_scd2`, `dim_movie_scd2` (for genre join).

Answers: which provider has the largest catalog per country/date; which
titles are exclusive to one provider at a point in time; net
adds/drops per provider over a period; how long a title stays on a given
provider before being removed; genre concentration per provider.

## `data_quality` — `dbt/models/marts/data_quality/`

**Grain**: one row per `pipeline_run_id + metric_name` — this is the one
mart that is *not* sourced from Silver business entities; it's sourced from
the technical metadata every Bronze/Silver Glue job already writes
(`PROJECT_PLAN.md` Section 14), surfaced through dbt sources rather than
staging models over business tables.

Metrics (from `PROJECT_PLAN.md` Section 13/14): `records_received`,
`records_processed`, `records_rejected`, `null_rate`, `duplicate_rate`,
`invalid_relationship_count`, `api_error_count`, `retry_count`,
`freshness_minutes`, `pipeline_duration`.

This mart is what any monitoring dashboard (`dashboards/monitoring/`)
queries — it should never itself depend on another mart being fresh, since
its entire purpose is to report on freshness/health even when something
upstream is broken.

## Cross-mart conventions

- Every mart's `is_current`/point-in-time semantics must be stated
  explicitly in its dbt model description — "current state" marts
  (`movie_performance`, `talent_collaboration`) vs. "time series" marts
  (`streaming_availability`, `data_quality`, half of `movie_lifecycle`)
  are answering fundamentally different question shapes and should not be
  joined together carelessly across grains.
- No mart re-implements SCD2 logic or hash-diff change detection — if a
  mart seems to need that, the modeling is wrong at the Silver layer, not
  missing at the Gold layer (see `adr-0002-dbt-for-gold-marts.md`,
  Consequences).
