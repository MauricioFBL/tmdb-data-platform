# Source-to-Target Mapping

Per `PROJECT_PLAN.md` Section 21. One entry per endpoint, with the required
fields: `endpoint | source_entity | source_grain | business_key | pagination
| load_frequency | load_type | destination_layer | destination_table |
nested_structures | historical_strategy | quality_risks | owner`.

Table names reuse exactly what `PROJECT_PLAN.md` Sections 8/10 already
named (`bronze_movie_details`, `silver_dim_movie`, etc.) — no new names
invented here. Rendered as a field list per endpoint rather than one giant
13-column table, since a table that wide stops being readable.

---

### Movie Details
- **endpoint**: `GET /movie/{movie_id}`
- **source_entity**: Movie
- **source_grain**: one row per movie_id per extraction
- **business_key**: `tmdb_movie_id`
- **pagination**: none (single-entity fetch)
- **load_frequency**: initial load once per movie; incremental on Movie Changes signal
- **load_type**: full-row upsert (whole object replaced each fetch, not partial)
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_movie_details` → `silver_dim_movie`
- **nested_structures**: `belongs_to_collection` (struct), `genres[]`, `production_companies[]` — must be exploded into their own relationship tables, not left nested in Bronze
- **historical_strategy**: SCD Type 2 for descriptive attributes (title, status, release_date, runtime, budget, revenue, etc. — full list in `PROJECT_PLAN.md` Section 10); popularity/vote_average/vote_count split out to the snapshot fact, **not** part of the SCD2 row
- **quality_risks**: `budget`/`revenue` of `0` commonly means "unknown," not a true zero — must not be treated as a real financial value downstream (flag explicitly in `movie_performance` mart logic); `release_date` can be null for unreleased/announced movies; `status` transitions (Rumored → Planned → In Production → Post Production → Released) are the core lifecycle-mart signal and must not be lost between SCD2 versions
- **owner**: Engineer 1 (extraction) / Engineer 2 (Silver SCD2 modeling)

### Movie Changes
- **endpoint**: `GET /movie/changes` (bulk discovery — confirmed to exist and return "all movie ids changed" in the window; distinct from the per-movie `GET /movie/{movie_id}/changes` detail endpoint, which this project does not need to call)
- **source_entity**: Movie Change Log
- **source_grain**: one row per changed `movie_id` per extraction window
- **business_key**: `tmdb_movie_id` + extraction window (`start_date`/`end_date`)
- **pagination**: `page` (default 1, 100 items/page)
- **load_frequency**: daily (incremental DAG watermark driver)
- **load_type**: append-only, insert new change signals since last watermark
- **destination_layer**: Bronze only (this is a discovery/trigger signal, not a modeled dimension)
- **destination_table**: `bronze_movie_changes`
- **nested_structures**: none — a flat list of movie IDs
- **historical_strategy**: N/A — this is the *trigger* for re-extracting Movie Details, not itself historized
- **quality_risks**: 14-day max query span means a stalled watermark for >14 days creates an unrecoverable gap without a full re-scan against the Daily ID Export instead; this is a real operational constraint on how long the incremental DAG can be down before a full backfill is required, not just a theoretical edge case
- **owner**: Engineer 1

### Movie Credits
- **endpoint**: `GET /movie/{movie_id}/credits`
- **source_entity**: Cast & Crew
- **source_grain**: one row per (movie_id, person_id, credit_id)
- **business_key**: `credit_id`
- **pagination**: none
- **load_frequency**: same cadence as Movie Details
- **load_type**: full replace per movie (TMDB returns the complete current cast/crew list each call, not a delta)
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_movie_credits` → `silver_movie_credit`
- **nested_structures**: `cast[]`, `crew[]` — two arrays with different schemas, must be normalized separately (crew has `department`/`job`, cast has `character`/`order`)
- **historical_strategy**: historized relationship (credits added/removed over time as TMDB corrects data) — not SCD2 on a single business key, since the grain is the movie-person relationship itself
- **quality_risks**: duplicate person entries across departments (a person can appear in `crew[]` multiple times for different jobs on the same movie) — dedup logic must key on `credit_id`, not `person_id` alone; `character` field can be empty string for uncredited/background roles
- **owner**: Engineer 2

### Movie Keywords
- **endpoint**: `GET /movie/{movie_id}/keywords`
- **source_entity**: Keyword tags
- **source_grain**: one row per (movie_id, keyword_id)
- **business_key**: `movie_id` + `keyword_id`
- **pagination**: none
- **load_frequency**: same cadence as Movie Details
- **load_type**: full replace per movie
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_movie_details` (nested extraction) → `silver_dim_keyword` + a movie-keyword bridge table
- **nested_structures**: `keywords[]` (id, name) — no language param, not localized
- **historical_strategy**: Type 1 for `silver_dim_keyword` itself; the movie-keyword relationship can be full-replace per movie (low value in historizing keyword additions/removals for this MVP)
- **quality_risks**: low risk — small, stable vocabulary; watch for keyword_id reuse/rename over time (rare but possible)
- **owner**: Engineer 2

### Movie External IDs
- **endpoint**: `GET /movie/{movie_id}/external_ids`
- **source_entity**: Cross-reference IDs
- **source_grain**: one row per movie_id
- **business_key**: `tmdb_movie_id`
- **pagination**: none
- **load_frequency**: same cadence as Movie Details
- **load_type**: full replace
- **destination_layer**: Bronze → Silver (folded into `silver_dim_movie` as Type 1 attributes, not SCD2 — these rarely change and aren't analytically interesting to historize)
- **destination_table**: `bronze_movie_details` (nested or `append_to_response`) → `silver_dim_movie`
- **nested_structures**: none — flat object
- **historical_strategy**: Type 1 (overwrite)
- **quality_risks**: fields are frequently null (not every movie has a Wikidata/Facebook/Instagram/Twitter presence) — null here means "not linked," not missing data
- **owner**: Engineer 1

### Movie Release Dates
- **endpoint**: `GET /movie/{movie_id}/release_dates`
- **source_entity**: Regional release dates & certifications
- **source_grain**: one row per (movie_id, country, release type)
- **business_key**: `movie_id` + `iso_3166_1` + `type`
- **pagination**: none
- **load_frequency**: same cadence as Movie Details
- **load_type**: full replace per movie
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_release_dates` → `silver_movie_release`
- **nested_structures**: `results[]` grouped by `iso_3166_1`, each containing `release_dates[]`
- **historical_strategy**: historized relationship — release dates are explicitly called out in `PROJECT_PLAN.md` Section 3 as something that changes over time ("how often are release dates modified") and must be tracked as valid_from/valid_to, not overwritten
- **quality_risks**: `type` numeric codes (1=Premiere, 2=Theatrical limited, 3=Theatrical, 4=Digital, 5=Physical, 6=TV) must be mapped to a `dim_release_type` lookup, not left as magic numbers in Silver; `certification` varies by country's own rating system (not comparable across countries without a country-aware lookup)
- **owner**: Engineer 2

### Movie Watch Providers
- **endpoint**: `GET /movie/{movie_id}/watch/providers`
- **source_entity**: Streaming availability
- **source_grain**: one row per (movie_id, country, provider_id, availability_type)
- **business_key**: `movie_id` + `iso_3166_1` (country) + `provider_id` + `availability_type`
- **pagination**: none
- **load_frequency**: weekly per `PROJECT_PLAN.md` Section 9 ("Streaming availability can initially be refreshed weekly")
- **load_type**: full snapshot per movie, diffed against current Silver state to detect additions/removals
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_watch_providers` → `silver_movie_provider_availability`
- **nested_structures**: `results` keyed by country code, each with `flatrate[]`/`rent[]`/`buy[]`/`free[]`/`ads[]`
- **historical_strategy**: historized relationship, per `PROJECT_PLAN.md` Section 10 (Streaming Availability DAG: compare current state → close removed relationships → insert new ones)
- **quality_risks**: **JustWatch attribution is contractually required** wherever this data is displayed (confirmed from TMDB docs — see `tmdb-api-overview.md`); a country with zero providers listed means "no known availability," not necessarily "unavailable" (JustWatch coverage gaps exist)
- **owner**: Engineer 2

### Person Details
- **endpoint**: `GET /person/{person_id}`
- **source_entity**: Person
- **source_grain**: one row per person_id per extraction
- **business_key**: `tmdb_person_id`
- **pagination**: none
- **load_frequency**: initial load once per person referenced by a credit; incremental on Person Changes signal
- **load_type**: full replace
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_person_details` → `silver_dim_person`
- **nested_structures**: none — flat object
- **historical_strategy**: SCD Type 2 (full attribute list in `PROJECT_PLAN.md` Section 10); person popularity explicitly excluded from the SCD2 table
- **quality_risks**: `deathday` null vs. populated is itself a meaningful state change worth capturing in SCD2; `gender` uses TMDB's 4-value enum (0=Not set,1=Female,2=Male,3=Non-binary) — must be mapped, not left as raw int, to avoid silently treating "Not set" as a real category in analysis
- **owner**: Engineer 1 (extraction) / Engineer 2 (Silver SCD2 modeling)

### Person Changes
- **endpoint**: `GET /person/changes` (bulk discovery, confirmed — same shape as `GET /movie/changes`; the per-person `GET /person/{person_id}/changes` detail endpoint is not needed for the same reason noted under Movie Changes)
- **source_entity**: Person Change Log
- **source_grain**: one row per changed `person_id` per extraction window
- **business_key**: `tmdb_person_id` + extraction window
- **pagination**: `page` (100 items/page)
- **load_frequency**: daily
- **load_type**: append-only
- **destination_layer**: Bronze only
- **destination_table**: `bronze_person_changes` — **note**: not explicitly named in `PROJECT_PLAN.md` Section 8's table list; needs to be added there
- **nested_structures**: none — flat list of person IDs
- **historical_strategy**: N/A — trigger signal only
- **quality_risks**: same 14-day max query span constraint as Movie Changes
- **owner**: Engineer 1

### Genres
- **endpoint**: `GET /genre/movie/list`
- **source_entity**: Genre reference list
- **source_grain**: one row per genre_id
- **business_key**: `genre_id`
- **pagination**: none
- **load_frequency**: weekly or on-demand (near-static reference data)
- **load_type**: full replace
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_movie_details` (nested) → `silver_dim_genre`
- **nested_structures**: `genres[]` (id, name)
- **historical_strategy**: Type 1
- **quality_risks**: minimal — small, stable, TMDB-curated vocabulary
- **owner**: Engineer 2

### Countries / Languages / Watch Provider list / TMDB Configuration
- **endpoint**: `GET /configuration/countries`, `GET /configuration/languages`, `GET /watch/providers/movie`, `GET /configuration`
- **source_entity**: Reference/lookup data
- **source_grain**: one row per code (country/language/provider) or singleton (configuration)
- **business_key**: `iso_3166_1` / `iso_639_1` / `provider_id` / N/A
- **pagination**: none
- **load_frequency**: weekly or on-demand
- **load_type**: full replace
- **destination_layer**: Bronze → Silver
- **destination_table**: `silver_dim_provider`, plus new `dim_country`/`dim_language` (named in `PROJECT_PLAN.md` Section 10's Type 1 dimension list but not yet given Bronze/Silver table names — gap to close before Phase 2)
- **nested_structures**: none, except Watch Provider list (per-country `display_priorities`)
- **historical_strategy**: Type 1 for all
- **quality_risks**: `change_keys` from `/configuration` should be captured once as a reference table so the Changes API's `key` values are validated against a known vocabulary, catching unexpected/new change types early
- **owner**: Engineer 2

### Trending Movies
- **endpoint**: `GET /trending/movie/{time_window}`
- **source_entity**: Trending snapshot
- **source_grain**: one row per (movie_id, time_window, snapshot_date)
- **business_key**: `movie_id` + `time_window` + `snapshot_date`
- **pagination**: **TODO: verify** — likely paginated `results[]` like Discover-family endpoints, not confirmed in this pass
- **load_frequency**: daily
- **load_type**: append-only snapshot
- **destination_layer**: Bronze → Silver
- **destination_table**: `bronze_trending_movies` → folds into `silver_movie_metrics_snapshot` or a dedicated trending snapshot table (open modeling question — see `docs/modeling/data-marts.md`)
- **nested_structures**: **TODO: verify** exact response shape — not confirmed
- **historical_strategy**: snapshot fact
- **quality_risks**: `day` vs `week` windows measure different things and must not be blended in the same mart metric without a `time_window` dimension
- **owner**: Engineer 2

---

## Gaps this pass surfaced in `PROJECT_PLAN.md` itself

1. Section 8's Bronze table list does not include a `bronze_person_changes`
   equivalent — only `bronze_movie_changes` is named. Needs adding before
   Phase 2.
2. `dim_country` and `dim_language` are named as Type 1 dimension
   candidates in Section 10 but have no corresponding Bronze/Silver table
   names assigned yet, unlike every other dimension.
3. Trending movies' destination table is ambiguous between the snapshot
   fact and a standalone table — needs an explicit decision in
   `docs/modeling/data-marts.md`.
