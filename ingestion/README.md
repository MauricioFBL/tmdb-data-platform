# Ingestion

Everything needed to pull data out of the TMDB API and land it, unmodified,
as raw JSON in S3. No business logic or transformation lives here — that
starts in `glue/`.

- `tmdb_client/` — thin HTTP client: bearer-token auth, base URL, request building. See `docs/source-analysis/tmdb-api-overview.md`.
- `extractors/` — one extractor per source group from `PROJECT_PLAN.md` Section 5 (entity discovery, movie data, person data, reference data, time-varying metrics).
- `pagination/` — TMDB pagination handling (page-based, `total_pages`/`total_results`).
- `retries/` — backoff and retry policy for rate limits (HTTP 429) and transient failures.
- `schemas/` — raw-layer technical metadata schema (`pipeline_run_id`, `request_id`, `endpoint`, `extraction_timestamp`, etc. — see `PROJECT_PLAN.md` Section 8).
- `tests/` — unit tests per extractor, using recorded/mocked TMDB responses (no live API calls in CI).
