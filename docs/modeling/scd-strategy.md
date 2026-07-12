# SCD Strategy

Formalizes `PROJECT_PLAN.md` Section 10. All SCD Type 2 and snapshot logic
is implemented as PySpark `MERGE INTO` against Iceberg tables in
`glue/silver/` — see `docs/deep-dives/scd2-iceberg-merge-patterns.md` for
the actual merge mechanics, and `docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md`
for why this is PySpark and not dbt snapshots.

## Decision rule: which strategy for which attribute

Before adding a new attribute anywhere in this platform, classify it using
this rule (from `conceptual-model.md`'s "Attributes vs. relationships vs.
metrics" section):

1. Does it change on almost every extraction, with low business
   significance per individual change? → **Snapshot fact**, not SCD2.
2. Is it a fact about a relationship between two entities, with its own
   independent validity period? → **Historized relationship**, not an SCD2
   attribute on either entity.
3. Otherwise, if it's a descriptive attribute of a single entity that
   changes rarely and each change is meaningful? → **SCD Type 2** on that
   entity's dimension.
4. Is it a low-cardinality reference value with no meaningful history
   (genre names, country codes)? → **Type 1**, overwrite in place.

## SCD Type 2 — `dim_movie_scd2`

- Business key: `tmdb_movie_id`. Surrogate key: `movie_sk`.
- Historical attributes: `title`, `original_title`, `overview`, `tagline`,
  `status`, `release_date`, `runtime`, `budget`, `revenue`, `adult`,
  `video`, `homepage`, `poster_path`, `backdrop_path`, `original_language`,
  `collection_id`.
- Technical attributes: `valid_from`, `valid_to`, `is_current`,
  `version_number`, `record_hash`, `created_at`, `updated_at`,
  `pipeline_run_id`.
- **Explicitly excluded**: `popularity`, `vote_average`, `vote_count` — see
  Movie Metrics Snapshot below. Including these here would generate a new
  dimension version on nearly every incremental run.
- Change detection: compute `record_hash` as a hash over all historical
  attributes (order-stable, null-safe concatenation); a new version is only
  created when `record_hash` differs from the current row's hash for that
  `tmdb_movie_id`.
- Invariants that must hold after every merge (see corresponding dbt/Glue
  tests): exactly one `is_current = true` row per `tmdb_movie_id`; no two
  versions for the same key have overlapping `[valid_from, valid_to)`
  ranges; `valid_from < valid_to` for closed versions.

## SCD Type 2 — `dim_person_scd2`

- Business key: `tmdb_person_id`.
- Historical attributes: `name`, `biography`, `birthday`, `deathday`,
  `place_of_birth`, `known_for_department`, `gender`, `homepage`,
  `profile_path`, `imdb_id`.
- **Explicitly excluded**: person popularity — same rapidly-changing-metric
  reasoning as Movie.
- Same technical attributes and invariants as `dim_movie_scd2`.

## SCD Type 2 — `dim_provider_scd2`

- Business key: `provider_id + region_code` (composite — the same
  `provider_id` can have different names/priority per region, so region is
  part of identity, not a separate dimension).
- Historical attributes: `provider_name`, `logo_path`, `display_priority`,
  `region_code`.
- Lower change frequency and lower row count than the other two SCD2
  dimensions — worth noting because it means simpler backfill/reprocessing
  risk if the merge logic needs to change later.

## Historized relationship — Streaming Availability

Not a dimension attribute on Movie or Provider. Grain:
`movie_id + provider_id + country_code + availability_type`, with its own
validity period.

- Attributes: `movie_id`, `provider_id`, `country_code`,
  `availability_type` (`flatrate` / `rent` / `buy` / `free` / `ads`),
  `valid_from`, `valid_to`, `is_current`.
- Refresh cadence: weekly is acceptable for the MVP (`PROJECT_PLAN.md`
  Section 9) — this is a business decision about acceptable staleness, not
  a technical constraint; revisit if a mart needs finer granularity.
- Merge pattern: on each refresh, close (`valid_to = now`, `is_current =
  false`) any current row not present in the latest extraction for that
  `movie_id + provider_id + country_code`, then insert new rows for newly
  observed combinations. This is a "close removed, insert new" pattern, not
  a hash-diff pattern, because there's no descriptive attribute to diff —
  the row's mere presence/absence *is* the fact.

## Historized relationship — Release Dates

Same shape as Streaming Availability: grain `movie_id + country_code +
release_type`, with `release_date` as the tracked value and its own
validity period. A release date changing (a delay, a moved premiere) is a
first-class historical event this platform must be able to answer
questions about (`PROJECT_PLAN.md` Section 3) — which is exactly why this
is a historized relationship and not just an overwritten field on
`dim_movie_scd2`.

## Snapshot fact — Movie Metrics

Grain: `movie_id + snapshot_date`. Attributes: `popularity`,
`vote_average`, `vote_count`. Append-only — no merge/close logic, no
`is_current` flag, no validity period. Every extraction run that observes a
movie writes one new row for that day; trend analysis is done by querying
across `snapshot_date`, not by tracking "current vs. historical" state.

Trending movies are stored the same way: a snapshot fact keyed by
`snapshot_date + movie_id`, sourced from the Trending endpoint rather than
Movie Details.

## Type 1 dimensions

`dim_genre`, `dim_country`, `dim_language`, `dim_release_type`,
`dim_credit_department`, `dim_credit_job` — overwrite in place on change,
no `valid_from`/`valid_to`, no versioning. These are reference vocabularies
where the *current* mapping is all that's ever needed; TMDB does not
meaningfully "change history" for a genre name.

## Testing every SCD2 table must have

- Uniqueness of `(business_key, valid_from)` and of `is_current = true` per
  business key.
- No overlapping validity windows per business key (a self-join check:
  no two current-or-historical rows for the same key where one's
  `[valid_from, valid_to)` intersects another's).
- Every closed version (`is_current = false`) has a non-null `valid_to`.
- `record_hash` uniqueness is *not* required across different business
  keys (two different movies can coincidentally hash the same only if the
  hash function is broken — worth a canary test, not a hard constraint).
