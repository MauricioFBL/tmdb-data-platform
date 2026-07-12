# SQL

Non-dbt SQL. Data mart SQL lives in `dbt/models/marts/` instead — see
[ADR-0002](../docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md).

- `athena/` — ad hoc exploration queries against Bronze/Silver Iceberg tables (debugging, manual validation — not run in any pipeline).
- `quality/` — data quality SQL checks that run outside dbt (e.g. Glue-job-invoked checks against Bronze/Silver before Gold is built).
