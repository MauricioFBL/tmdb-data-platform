# TMDB Endpoint Inventory

All paths confirmed against `developer.themoviedb.org/reference` on
2026-07-11 (base URL `https://api.themoviedb.org/3`, omitted below for
brevity). Auth for every endpoint below: `Authorization: Bearer
<TMDB_API_READ_ACCESS_TOKEN>` (see `tmdb-api-overview.md`).

## Entity discovery

| Endpoint | Method + Path | Params (this project uses) | Notes |
|---|---|---|---|
| Daily Movie ID Export | `GET https://files.tmdb.org/p/exports/movie_ids_MM_DD_YYYY.json.gz` | date in URL path, not a query param | Not part of the `/3` API — separate static file host. gzip JSON-Lines. Available ~8:00 AM UTC daily, 3-month retention. |
| Movie Changes (bulk discovery) | `GET /movie/changes` | `start_date`, `end_date` (max 14-day span), `page` (default 1, 100 items/page) | **This is the endpoint the incremental DAG actually calls.** Confirmed via direct fetch of `developer.themoviedb.org/reference/changes-movie-list`: returns "all of the movie ids that have been changed" in the given window — a genuine bulk discovery feed, not per-movie. Distinct from the per-movie endpoint below. |
| Movie Changes (per-movie detail) | `GET /movie/{movie_id}/changes` | `start_date`, `end_date` (max 14-day span), `page` | Returns the actual field-level change entries (`key`/`action`/`time`/`value`) for one movie. Used *after* the bulk endpoint above identifies a changed `movie_id`, if the change detail itself (not just "this movie changed") is ever needed — for this project's SCD2 pattern, re-fetching full Movie Details for the changed ID is simpler than parsing per-field change entries, so this endpoint is likely unused in practice; kept here for completeness. |

## Movie data

| Endpoint | Method + Path | Params (this project uses) | Notes |
|---|---|---|---|
| Movie Details | `GET /movie/{movie_id}` | `language` (default en-US), `append_to_response` (max 20 comma-separated) | Core SCD2 source. `append_to_response` could fold credits/keywords/release_dates/external_ids into one call — evaluate in Phase 1 to cut request volume, at the cost of a larger nested payload to parse in Bronze. |
| Movie Credits | `GET /movie/{movie_id}/credits` | `language` | Returns `cast[]` (id, name, character, credit_id, order) and `crew[]` (department, job, + person id/name). |
| Movie Keywords | `GET /movie/{movie_id}/keywords` | none | Returns `keywords[]` (id, name). No language param — keywords are not localized. |
| Movie External IDs | `GET /movie/{movie_id}/external_ids` | none | Returns `imdb_id`, `wikidata_id`, `facebook_id`, `instagram_id`, `twitter_id`. |
| Movie Release Dates | `GET /movie/{movie_id}/release_dates` | none | Returns `results[]` grouped by `iso_3166_1`, each with `release_dates[]` (certification, release_date, type, note). `type` codes: 1=Premiere, 2=Theatrical (limited), 3=Theatrical, 4=Digital, 5=Physical, 6=TV. |
| Movie Watch Providers | `GET /movie/{movie_id}/watch/providers` | none | Returns `results` keyed by country code, each with `link` + `flatrate`/`rent`/`buy`/`free`/`ads` arrays (`provider_id`, `provider_name`, `logo_path`, `display_priority`). **Attribution to JustWatch is contractually required** — see `tmdb-api-overview.md`. |

## Person data

| Endpoint | Method + Path | Params | Notes |
|---|---|---|---|
| Person Details | `GET /person/{person_id}` | `language`, `append_to_response` (max 20) | Fields: name, biography, birthday, deathday, place_of_birth, known_for_department, gender (0=Not set, 1=Female, 2=Male, 3=Non-binary), homepage, profile_path, imdb_id. |
| Person Changes (bulk discovery) | `GET /person/changes` | `start_date`, `end_date` (max 14-day span), `page` | Confirmed via direct fetch of `developer.themoviedb.org/reference/changes-people-list`: bulk list of changed person IDs, same shape as the movie equivalent above. |
| Person Changes (per-person detail) | `GET /person/{person_id}/changes` | `start_date`, `end_date` (max 14-day span), `page` | Same relationship to the bulk endpoint as the movie pair above. |

## Reference data

| Endpoint | Method + Path | Params | Notes |
|---|---|---|---|
| Genres | `GET /genre/movie/list` | `language` (default en) | Returns `genres[]` (id, name). Small, stable — Type 1 dimension, safe to refresh fully on every run. |
| Countries | `GET /configuration/countries` | `language` (default en-US) | Returns `iso_3166_1`, `english_name`, `native_name`. |
| Languages | `GET /configuration/languages` | none | Returns `iso_639_1`, `english_name`, `name`. |
| Watch Providers (reference list) | `GET /watch/providers/movie` | `language`, `watch_region` (optional filter) | The full provider catalog (provider_id, provider_name, logo_path, per-country display_priorities) — distinct from the per-movie availability endpoint above; this is the Type 1 `silver_dim_provider` source, the per-movie endpoint is the historized-relationship source. |
| TMDB Configuration | `GET /configuration` | none | Returns `images.base_url`/`images.secure_base_url`/size arrays (not needed — no image storage in MVP) and `change_keys[]` (the valid vocabulary for Changes API `key` fields — worth capturing once as reference data). |

## Time-varying metrics

| Endpoint | Method + Path | Params | Notes |
|---|---|---|---|
| Movie popularity / vote_average / vote_count | (from Movie Details response, not a separate endpoint) | — | Snapshot-fact source per day, per `PROJECT_PLAN.md` Section 10 — do not treat as SCD2 attributes. |
| Trending Movies | `GET /trending/movie/{time_window}` | `time_window` path param (`day` or `week`), `language` | **TODO: verify** exact response shape — the fetched excerpt confirmed the path and params but the response body schema wasn't returned; likely a paginated `results[]` of movie-summary objects similar to Discover, but confirm before building the extractor. |

## Open items flagged during this research pass

1. Exact Daily Export per-line field list — confirm by downloading a real
   file rather than relying on the docs' prose description.
2. Trending Movies response shape — confirm via a live call.
3. Movie/Person Changes individual change-entry shape (key/action/time/
   value/original_value) — confirm via a live call before writing the
   Bronze parser for `bronze_movie_changes`. This only matters if the
   per-entity change-detail endpoints end up being used (see note above —
   likely unnecessary, since re-fetching full Movie/Person Details for a
   changed ID from the bulk discovery endpoint is simpler than parsing
   field-level change entries).

**Resolved during this pass** (was initially flagged as the top design
risk, then corrected after a follow-up fetch): TMDB does have bulk
discovery endpoints — `GET /movie/changes` and `GET /person/changes` —
distinct from the per-entity `/movie/{id}/changes` and
`/person/{id}/changes` detail endpoints. `PROJECT_PLAN.md` Section 9's
incremental DAG design ("Call Movie Changes → Collect changed movie IDs")
is correct as written; it should reference the bulk endpoint explicitly.
