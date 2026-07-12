# Deep Dives

Project-specific technical reference docs — not vendor marketing summaries.
Each one exists because it backs a real decision or a real implementation
risk in this platform.

- `iceberg-internals-and-glue.md` — manifest files, snapshots, partition evolution, `MERGE INTO` mechanics, Glue's Iceberg connector gotchas.
- `orchestrator-airflow-vs-dagster.md` — technical backing for [ADR-0001](../architecture/architecture-decisions/adr-0001-orchestrator-choice.md).
- `scd2-iceberg-merge-patterns.md` — hash-diff change detection and multi-attribute SCD2 `MERGE INTO` patterns in PySpark against Iceberg.
