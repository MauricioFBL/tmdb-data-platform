# ADR-0001: Orchestrator Choice — Airflow vs. Dagster

## Status

**Proposed** — not yet decided. This ADR presents a recommendation, not a
decision. The two engineers must discuss and record the actual choice below
before Phase 1 (first DAG/asset implementation) begins. Milestone 1
(PROJECT_PLAN.md Section 20) does not depend on this decision and can
proceed in parallel.

## Context

PROJECT_PLAN.md originally assumed Airflow throughout (Section 6, 12, 15),
but the team is also considering Dagster and wants cost to be a driver.
Full technical detail backing this ADR is in
[`docs/deep-dives/orchestrator-airflow-vs-dagster.md`](../../deep-dives/orchestrator-airflow-vs-dagster.md) —
read that before deciding. This ADR summarizes the decision drivers and
options; it does not repeat the full analysis.

The orchestrator must: trigger Glue jobs, manage retries, coordinate a
watermark-based incremental load, and (later) run scheduled Iceberg
maintenance jobs (compaction, snapshot expiration — see
`docs/deep-dives/iceberg-internals-and-glue.md`).

## Decision Drivers

1. **Cost** — the original driver named by the team.
2. **Conceptual fit** with this project's Bronze/Silver/Gold table-lineage
   design (Section 8) vs. task-based DAGs.
3. **Two-person operational burden** — who owns this outside working hours.
4. **Portfolio/hiring signal** — which tool is a better demonstration of
   marketable skill for a consultancy.
5. **Glue integration maturity** — how much custom code is needed to
   trigger and monitor Glue jobs.

## Options Considered

### Option A: Amazon MWAA (managed Airflow)

- Verified cost: **~$225–350+/month** minimum for a small always-on
  environment (component-based pricing: scheduler + worker + storage — see
  deep-dive Section 5). This is the most expensive option by a wide margin
  for a project with no production SLA.
- Zero operational burden (AWS manages the control plane, upgrades, HA).
- Mature `GlueJobOperator`, large community, most-common tool in the wild.
- **Rejected primarily on cost** — hard to justify $225+/month recurring
  spend for a portfolio project relative to a ~$20/month self-hosted
  alternative.

### Option B: Self-hosted Airflow (Docker Compose / single EC2)

- Verified cost: **~$15–35/month** raw compute (t3.small/medium, 3
  processes: webserver, scheduler, worker via `LocalExecutor`).
- Task-based DAGs require manually keeping task dependencies in sync with
  actual table lineage — no structural safeguard against a forgotten edge.
- Most mature Glue integration (`GlueJobOperator`), largest community for
  troubleshooting.
- Ops burden: engineer-owned upgrades, Postgres metadata DB, scheduler
  process health — acceptable for a portfolio project without production
  uptime requirements.

### Option C: Self-hosted Dagster OSS

- Verified cost: **~$15–35/month** raw compute — same range as self-hosted
  Airflow, slightly lighter process footprint (2 core services: webserver +
  daemon, vs. Airflow's 3).
- **Asset-based model is a materially better fit** for this project's
  explicit Bronze→Silver→Gold table-lineage design — dependencies are
  declared between tables, not steps, and a missing dependency is visible
  in the lineage graph rather than a silent DAG-authoring bug.
- Built-in "materialize downstream" backfill semantics map directly onto a
  realistic scenario this project will hit (reprocessing Silver after a
  Bronze bug fix) with no Airflow equivalent.
- Weaker Glue integration than Airflow (`boto3`-based op or the newer,
  less-battle-tested `PipesGlueClient`) and a smaller community/fewer
  existing engineers who already know it.

### Option D: Dagster+ (managed)

- Verified cost (post-May-2026 pricing change): Solo tier $10/month + usage
  credits, likely **$30–50/month** for this project's light workload — no
  free tier as of this writing.
- Considered for completeness; not a strong contender given self-hosted
  Dagster OSS costs about the same as self-hosted Airflow and removes the
  managed-service premium entirely.

## Recommendation (not a decision)

Cost turns out **not** to be the deciding driver — MWAA is clearly
disqualified on cost (Option A), but self-hosted Airflow and self-hosted
Dagster cost roughly the same (~$15–35/month). The real trade-off is
**conceptual fit vs. Glue integration maturity / community size**:

- If the priority is demonstrating the *cleanest possible* data-lineage
  story for a portfolio (asset graph that mirrors Section 8's layered
  design) and you're comfortable with a newer, smaller-community tool:
  **Dagster OSS** is the stronger technical fit.
- If the priority is maximizing "the tool most clients/employers already
  run" and minimizing integration risk (mature `GlueJobOperator`, huge
  community for troubleshooting): **self-hosted Airflow** is the safer
  choice.

This document intentionally stops short of picking one. Record the actual
decision below once discussed.

## Decision

*(To be filled in by the two engineers.)*

- Chosen option:
- Date decided:
- Rationale:

## Consequences

- Once decided, `orchestration/` (currently scaffolded with Airflow-shaped
  placeholder subfolders) may need restructuring around Dagster's
  `definitions/`/`assets/`/`resources/` shape if Dagster is chosen.
- `modules/orchestrator/` in the sibling `tmdb-data-platform-infra` repo
  (currently empty) gets built out for whichever option is chosen —
  self-hosted options need EC2/networking Terraform; MWAA would need its
  own VPC/networking shape instead (moot here since Option A is rejected).
- PROJECT_PLAN.md Section 12 (Orchestration Plan) task names stay
  tool-agnostic (already written as generic pipeline steps, not
  Airflow-specific operators) and should not need rewriting regardless of
  outcome.
