# TMDB API Overview

Research basis: fetched directly from `developer.themoviedb.org/docs` and
`/reference` on 2026-07-11. Where the fetched excerpt was incomplete, that
is flagged explicitly rather than filled in from assumption.

## Authentication

TMDB supports two application-level authentication methods, both granting
identical access:

1. **API key as a query parameter** — `?api_key=<key>`. The older method.
2. **API Read Access Token as a Bearer header** — `Authorization: Bearer
   <access_token>`. TMDB's documentation states this is the recommended
   approach, since "using the Bearer token approach offers the added
   benefit of being a single authentication process that you can use across
   both the v3 and v4 methods."

**Decision for this project**: use the Bearer Read Access Token, per
`PROJECT_PLAN.md` Section 5, which already specifies this. The token goes
in `TMDB_API_READ_ACCESS_TOKEN` (see `.env.example` at repo root) and is
sent as `Authorization: Bearer ${TMDB_API_READ_ACCESS_TOKEN}` on every
request — never as a query param, to avoid the token leaking into access
logs.

## Base URL and versioning

- Base URL: `https://api.themoviedb.org/3` (v3 — what this project uses).
- A v4 API also exists (session/list-oriented, different auth flow scope)
  but is out of scope; nothing in this project's endpoint set requires it.

## Rate limits

TMDB's current policy (confirmed from the live rate-limiting doc):

- The old hard limit — **40 requests per 10 seconds** — was explicitly
  **disabled on December 16, 2019**. Any design assuming that number is
  based on stale information.
- The current stated ceiling is informal: "upper limits somewhere in the 40
  requests per second range," and TMDB explicitly warns **this could change
  at any time** — it is not a documented SLA.
- There is no documented burst-limit table. TMDB instead asks clients to be
  "respectful" and to honor HTTP 429 (Too Many Requests) responses.

**Implication for `ingestion/retries/`**: do not hardcode a fixed
requests/sec budget as a correctness guarantee. Implement:
- Exponential backoff keyed off actual `429` responses (and `Retry-After`
  header if TMDB sends one — verify this when the client is built, it
  wasn't confirmed in this research pass).
- A conservative client-side concurrency cap (e.g. 30–35 req/s) as a
  courtesy ceiling, not because it's a documented hard limit.

## Pagination

Standard TMDB list endpoints (e.g. Movie Changes, Person Changes) use:
- `page` query param, default `1`.
- Response includes page metadata — exact field names (`page`,
  `total_pages`, `total_results`) are TMDB's long-standing documented
  convention, but **were not independently re-confirmed against a live
  paginated response body in this research pass** — verify against a real
  response during `ingestion/extractors/` implementation.
- **TODO: verify** whether TMDB still caps `total_pages` at 500 for
  search/discover-style endpoints (a long-standing TMDB limitation) — not
  confirmed from the fetched pages, and none of this project's in-scope
  endpoints are search/discover endpoints, so it's likely not applicable,
  but flag before relying on deep pagination anywhere.

## Daily ID Exports

This is the entity-discovery mechanism for Milestone/Phase 1 scope
filtering (`PROJECT_PLAN.md` Section 9).

- URL pattern: `https://files.tmdb.org/p/exports/movie_ids_MM_DD_YYYY.json.gz`
  (e.g. `movie_ids_10_25_2025.json.gz`).
- Format: gzip-compressed, **JSON Lines** (one JSON object per line, not one
  big JSON array) — this matters operationally: the file can be streamed
  and filtered line-by-line without loading it fully into memory.
- Content per line: "a list of the valid IDs you can find on TMDB and some
  higher level attributes that are helpful for filtering items like the
  `adult`, `video`, and `popularity` values." Exact full field list
  (e.g. whether `original_title` is included) — **TODO: verify** by
  downloading one real file, since the doc excerpt didn't enumerate every
  field.
- Generation schedule: export job runs daily starting ~7:00 AM UTC, all
  files available by ~8:00 AM UTC.
- Retention: files are deleted after 3 months — if a specific date's export
  is needed for reproducibility/replay, it must be captured into this
  project's own `s3://.../raw/` storage promptly, not re-fetched from TMDB
  later.

## Movie Changes (incremental load driver)

Endpoint: `GET /movie/changes` — confirmed via direct fetch of
`developer.themoviedb.org/reference/changes-movie-list` to be a genuine
**bulk discovery feed**: "retrieves all of the movie ids that have been
changed" in the given window, paginated at 100 items/page. This is
distinct from `GET /movie/{movie_id}/changes` (per-movie detail, returns
field-level change entries for one movie) — the incremental DAG only needs
the bulk endpoint to discover *which* movie IDs changed, then re-fetches
full Movie Details for each. `PROJECT_PLAN.md` Section 9's incremental
design ("Call Movie Changes → Collect changed movie IDs") is correct as
written against this endpoint. Key constraints confirmed from the docs:

- **Default window is the last 24 hours.**
- **Maximum queryable range is 14 days** via `start_date`/`end_date`.
- The same shape and 14-day constraint applies to **`GET /person/changes`**
  for Person Changes.

**Implication for watermarking** (`PROJECT_PLAN.md` Section 9): the
incremental DAG's watermark must never fall more than 14 days behind, or a
gap opens that this endpoint cannot backfill in a single query — the
watermark-advance step needs a hard alarm if the previous successful run is
more than ~10-12 days old (safety margin before hitting the 14-day wall),
not just a "best effort" retry. A watermark gap beyond 14 days requires
falling back to a full re-scan via the Daily ID Export instead.

Since this project's SCD2 pattern re-fetches full Movie/Person Details for
any changed ID anyway (`docs/deep-dives/scd2-iceberg-merge-patterns.md`),
the per-entity detail endpoints' exact change-entry shape
(key/action/time/value/original_value) is not actually needed to build the
incremental pipeline — only the bulk endpoint's list of changed IDs is.
Confirming the per-entity shape is therefore lower priority than initially
assessed; left as a TODO only if a future need for field-level change
auditing arises.

## Configuration endpoint

`GET /configuration` returns `images.base_url` / `images.secure_base_url`
and valid `poster_sizes`/`backdrop_sizes`, plus a `change_keys` array (the
valid set of keys the Changes API can report on). This project does not
download images (excluded from MVP per `PROJECT_PLAN.md` Section 4), so
`images.*` is not needed — but `change_keys` is worth fetching once and
storing in `config/` as a reference table, since it defines the full
vocabulary the Changes API can emit.

## Attribution requirement (compliance risk, not just technical)

The Watch Providers data is sourced from **JustWatch**, and TMDB's docs
state explicitly: **"In order to use this data you must attribute the
source of the data as JustWatch."** This is a real legal/compliance
requirement, not a nice-to-have — any dashboard or mart surfacing streaming
availability data (`gold_streaming_catalog` / the Streaming Availability
Mart) must carry a visible JustWatch attribution. Flag this in
`docs/modeling/data-marts.md` and any BI dashboard built in Phase 7.
