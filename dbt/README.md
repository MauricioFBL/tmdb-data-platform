# dbt Project — Gold Marts

Scope is deliberately narrow: **dbt only builds the five Gold-layer data
marts** (`PROJECT_PLAN.md` Section 11) as SQL models reading Silver Iceberg
tables. Bronze parsing and Silver SCD2/snapshot logic stay in PySpark/Glue
— see [ADR-0002](../docs/architecture/architecture-decisions/adr-0002-dbt-for-gold-marts.md)
for why.

**Adapter: pending [ADR-0004](../docs/architecture/architecture-decisions/adr-0004-dbt-iceberg-engine-athena-vs-glue.md)**
(`dbt-athena-community` vs. `dbt-glue`) — currently Proposed, leaning
Athena. `profiles.yml.example` below assumes Athena; if ADR-0004 resolves
to Glue instead, that file needs a full rewrite to the `type: glue` shape
documented in ADR-0004, not just a tweak.

- `models/staging/` — thin, non-materialized views over Silver Iceberg tables (naming/typing alignment only — no business logic).
- `models/marts/movie_lifecycle/` — status/date/completeness history over time.
- `models/marts/movie_performance/` — budget, revenue, ROI, popularity by genre/year/country/company.
- `models/marts/talent_collaboration/` — actor/director collaboration patterns.
- `models/marts/streaming_availability/` — provider catalog changes over time.
- `models/marts/data_quality/` — platform health metrics mart.
- `tests/` — dbt tests (uniqueness, not-null, relationships, custom SCD-overlap checks) per mart.
- `macros/` — shared SQL macros (e.g. is_current-record filters, standard date-spine generation).

`profiles.yml` is intentionally **not** committed (see root `.gitignore`) —
copy `profiles.yml.example` locally and point at your Athena workgroup.
