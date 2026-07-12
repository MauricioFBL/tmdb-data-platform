# Data Modeling

- `conceptual-model.md` — entities, relationships, and grains before physical design (Section 8 of `PROJECT_PLAN.md`).
- `scd-strategy.md` — which entities get SCD Type 2, which attributes are excluded and why, snapshot vs. historized-relationship rules (Section 10).
- `data-marts.md` — Gold-layer mart definitions, now implemented as dbt models on Athena (see [ADR-0002](../architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md)).
