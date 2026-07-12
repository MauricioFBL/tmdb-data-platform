# Config

Explicit, version-controlled configuration — preferred over hard-coded
limits per `PROJECT_PLAN.md` Section 17.

- `endpoints.yml` — TMDB endpoint registry (path, method, pagination type, rate-limit class) — generated from `docs/source-analysis/endpoint-inventory.md`.
- `environments.yml` — per-environment settings (dev/prod S3 buckets, Glue database names, Athena workgroup).
- `data_quality.yml` — thresholds for the checks in `PROJECT_PLAN.md` Section 13 (null rates, duplicate rates, valid ranges).
- `tables.yml` — table registry: layer, grain, business key, partitioning, owner — one entry per Bronze/Silver/Gold table.
