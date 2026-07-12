# Cross-Cutting Tests

Tests that don't belong to a single module (`ingestion/tests/`,
`glue/tests/`, `dbt/tests/` cover those). Component-level tests live next to
their code; this directory is for tests that span components.

- `unit/` — cross-module unit tests (e.g. config loading, shared utilities).
- `integration/` — end-to-end slice tests (e.g. Milestone 1: TMDB fixture → raw → Bronze → Silver → query), run against local Spark + moto-mocked S3/Glue.
- `data/` — fixture data (recorded TMDB API responses, expected output snapshots) used by both `integration/` and component-level tests.
