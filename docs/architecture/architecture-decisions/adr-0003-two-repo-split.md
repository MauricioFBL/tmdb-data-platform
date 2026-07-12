# ADR-0003: Split Infrastructure (Terraform) from Pipeline Code into Two Repos

## Status

Accepted — 2026-07-11

## Context

`PROJECT_PLAN.md` Section 15 originally sketched a single monorepo
containing `infrastructure/terraform/`, `airflow/`, `ingestion/`, `glue/`,
`sql/`, `docs/`, and everything else under one root. This project is
explicitly meant to be the first of several portfolio pieces supporting a
future data consultancy — how the repos are organized is itself part of
what's being demonstrated to reviewers (hiring managers, prospective
clients), not just an implementation detail.

A single-repo layout is simpler for a two-person team: one PR touches
infra and code together when needed, one CI setup, one place to browse.
A split-repo layout mirrors how many real platform teams separate
infrastructure ownership (often a distinct on-call rotation, distinct
change-approval process, Terraform state/locking concerns) from
application/pipeline code — at the cost of cross-repo coordination
whenever a change spans both (e.g., adding a new Glue job needs a Terraform
change in one repo and a Glue script in the other, coordinated across two
PRs).

## Decision

Two repositories:

- **`tmdb-data-platform`** (this repo) — `docs/`, `orchestration/`,
  `ingestion/`, `glue/`, `dbt/`, `sql/`, `config/`, `dashboards/`, `tests/`,
  its own `.github/workflows/` for Python/PySpark/dbt CI.
- **`tmdb-data-platform-infra`** (sibling repo) — Terraform only:
  `modules/`, `environments/`, its own `.github/workflows/` for
  `terraform fmt`/`validate`/`plan` CI.

`PROJECT_PLAN.md` continues to live in the pipeline repo as the
canonical design document; the infra repo's README links back to it and to
the relevant ADRs for context.

## Consequences

- Every cross-cutting change (new Glue job needing a new IAM policy or S3
  prefix, a new orchestrator needing new networking) requires two PRs
  across two repos, referencing each other. This is real overhead for a
  two-person team, accepted deliberately as a more realistic platform-team
  pattern for the portfolio story.
- Terraform state/backend configuration (`main.tf` in the infra repo)
  currently has no remote backend configured — this is an explicit open
  item, not an oversight; decide before the first `terraform apply` whether
  a local backend is acceptable for this project's scale or whether to set
  up an S3 backend + DynamoDB lock table immediately.
- CI/CD is duplicated across two `.github/workflows/` setups instead of
  one — acceptable since the two repos have genuinely different CI
  concerns (Terraform validate/plan vs Python/PySpark/dbt lint-test).
- If in practice the cross-repo coordination overhead proves too costly for
  a two-person team, revisit via a new ADR rather than silently drifting
  back to a monorepo.
