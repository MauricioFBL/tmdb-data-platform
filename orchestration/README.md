# Orchestration

**Pending [ADR-0001](../docs/architecture/architecture-decisions/adr-0001-orchestrator-choice.md)** —
tool (Airflow vs Dagster) not yet decided. This directory is scaffolded with
Airflow-shaped subfolders (matching `PROJECT_PLAN.md` Section 15) as a
placeholder; if Dagster is chosen instead, this directory gets restructured
around `definitions/`, `assets/`, and `resources/` before Phase 1 starts.
No DAG/asset code should be written here until the ADR is resolved.

- `dags/` — top-level pipeline definitions (Airflow) — *placeholder*.
- `task_groups/` — reusable groupings of tasks (Airflow) — *placeholder*.
- `operators/` — custom operators (Airflow) — *placeholder*.
- `sensors/` — watermark/external-dependency sensors — *placeholder*.
- `tests/` — DAG import tests, task unit tests — *placeholder*.

Orchestration must only coordinate — trigger Glue jobs, manage retries,
advance watermarks. Heavy transformation logic belongs in `glue/`, never
here (see `PROJECT_PLAN.md` Section 22, item 11).
