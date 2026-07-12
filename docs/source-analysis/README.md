# Source Analysis

Research on the TMDB API as the platform's only source system.

- `tmdb-api-overview.md` — authentication, rate limits, pagination model, versioning, general API shape.
- `endpoint-inventory.md` — every endpoint the platform consumes (Section 5 of `PROJECT_PLAN.md`), with method, path, auth, rate limit class, and pagination behavior.
- `source-to-target.md` — field-level mapping per endpoint: source grain, business key, load type, destination layer/table, historical strategy, quality risks, owner.
