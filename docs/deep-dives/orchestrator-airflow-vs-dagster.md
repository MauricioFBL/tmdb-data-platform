# Orchestrator Deep-Dive: Airflow vs. Dagster for the TMDB Data Platform

This doc backs [ADR-0001](../architecture/architecture-decisions/adr-0001-orchestrator-choice.md).
It is scoped specifically to this project's three DAGs (PROJECT_PLAN.md
Section 12: Initial Load, Daily Incremental, Streaming Availability), not a
general Airflow-vs-Dagster listicle.

## 1. How each tool models this project's pipelines

### Airflow: explicit task graphs

The three DAGs in Section 12 map directly onto Airflow's mental model — a
DAG *is* a directed graph of tasks:

```python
download_daily_movie_ids >> filter_movie_scope >> create_batches \
    >> extract_movie_details >> extract_related_entities \
    >> validate_raw_data >> run_bronze_jobs >> run_silver_jobs \
    >> run_quality_checks >> build_gold_marts
```

Each box in the plan's ASCII diagrams becomes a task (usually a
`PythonOperator` calling into `ingestion/` or a `GlueJobOperator` calling
into `glue/`). Airflow does not know or care *what data* flows between
tasks — dependencies are declared by the engineer, not inferred. If someone
adds a new Silver table that depends on a Bronze table, they must remember
to add the edge; Airflow won't catch a missing dependency.

### Dagster: asset graphs inferred from data, not steps

Dagster's core abstraction is the **software-defined asset** — you declare
"here is how `bronze_movie_details` is built, and it depends on
`raw_movie_details`", and Dagster derives the DAG from those declarations:

```python
@asset(deps=[raw_movie_details])
def bronze_movie_details(context) -> None:
    trigger_glue_job("bronze_movie_details_job")

@asset(deps=[bronze_movie_details])
def silver_dim_movie_scd2(context) -> None:
    trigger_glue_job("silver_dim_movie_scd2_job")
```

This is a materially better fit for this project's actual shape: Section 8
already defines the platform as a chain of *tables* (raw → bronze → silver
→ gold), not a chain of *steps*. Adding a new Silver table that reads two
Bronze tables is just declaring two `deps` — Dagster's asset graph (and its
UI's lineage view) updates automatically, and a missing dependency is a
visible gap in the graph rather than a silent bug. Airflow requires the
engineer to keep the DAG and the table-dependency reality in sync by hand.

The trade-off: Dagster's asset model adds a layer of abstraction (ops,
assets, jobs, resources, IO managers) that has a steeper initial learning
curve than Airflow's "just write a DAG file" model, and most real-world
production Dagster usage is younger/smaller than Airflow's — fewer
StackOverflow answers, fewer engineers who already know it if you ever hire.

## 2. Watermark management

This project's incremental DAG is explicitly watermark-driven (Section 9):
read previous watermark → call Movie Changes → extract changed IDs →
process → **advance watermark only after success**.

- **Airflow**: no built-in "watermark" concept. The idiomatic pattern is an
  Airflow `Variable` (or a row in a Postgres table) read at the start of the
  DAG run and written at the end, inside a task that only runs if every
  upstream task succeeded (`trigger_rule="all_success"`). This is exactly
  what Section 9 already describes — Airflow doesn't add anything beyond
  "store the watermark somewhere and gate the write". XCom is the wrong
  tool here (it's per-DAG-run, not persistent across runs); a Variable or an
  external table is correct and this is a common Airflow footgun for
  newcomers who reach for XCom first.
- **Dagster**: has first-class support for this pattern via **partitions**.
  A daily-partitioned asset carries its own "last successfully materialized
  partition" state in Dagster's metadata store, so "what's the watermark"
  is answered by the framework instead of hand-rolled state. Dynamic
  partitions (partitions created at runtime, e.g. one partition per changed
  `movie_id` from the Movie Changes response) map cleanly onto Section 9's
  "collect changed movie IDs → extract current movie details" step in a way
  Airflow has no native equivalent for (Airflow's dynamic task mapping,
  added in 2.3+, is close but is a per-DAG-run fan-out, not a persistent
  partition registry with materialization history).

## 3. Triggering Glue jobs

- **Airflow**: `airflow.providers.amazon.aws.operators.glue.GlueJobOperator`,
  mature, widely used, directly maps to "run this Glue job and wait/poll for
  completion" — very little custom code needed.
- **Dagster**: no first-party Glue operator as polished as Airflow's. The
  practical pattern is an op/asset that calls `boto3` directly
  (`start_job_run` + poll `get_job_run`), or Dagster's `PipesGlueClient`
  (part of the `dagster-aws` package) which additionally streams Glue job
  logs/metadata back into the Dagster UI via the Pipes protocol — a nicer
  observability story than Airflow's "check CloudWatch separately", but it
  is a newer, less battle-tested integration than `GlueJobOperator`.

## 4. Backfill and replay

PROJECT_PLAN.md is explicit that raw data must "support replay and
reprocessing" (Section 8). Both tools support this, differently:

- **Airflow**: backfill via `airflow dags backfill` or manually clearing
  task instances for a date range; this re-runs the *tasks* for those
  logical dates. Because Airflow doesn't track data lineage, "replay
  Bronze for movie X because Silver had a bug" means manually targeting the
  right tasks/dates — there's no built-in way to ask "what needs to
  re-run because this asset changed."
- **Dagster**: because dependencies are between *assets*, Dagster can
  compute "materialize this asset and everything downstream of it" — a
  built-in operation ("Materialize Downstream") that has no direct Airflow
  equivalent. This maps well onto a real scenario this project will
  actually hit: reprocessing Silver after fixing a Bronze parsing bug,
  without needing to hand-enumerate which DAG runs to clear.

## 5. Cost — real figures (verified July 2026)

### Amazon MWAA (managed)

AWS switched MWAA to **component-based pricing** (environment instance +
scheduler(s) + worker(s) + web server + metadata storage), not a single
flat per-environment rate. Representative small-class rates:

| Component | Small class rate |
|---|---|
| Scheduler | ~$0.25/hr (~$180/mo always-on) |
| Worker (1x) | ~$0.24/hr (~$175/mo always-on) |
| Metadata storage | ~$0.10/GB-month |

A minimal always-on small MWAA environment (1 scheduler + 1 worker) lands
around **$225–350/month** for a light workload like this project's three
DAGs — this is the number that should anchor ADR-0001's cost comparison,
not the often-quoted "$0.49/hr small environment" figure from AWS's
marketing page, which describes an older single-rate pricing model AWS has
since replaced with the per-component model above.
[AWS MWAA pricing](https://aws.amazon.com/managed-workflows-for-apache-airflow/pricing/)

### Self-hosted Airflow (Docker Compose or single EC2)

Three long-running processes minimum: webserver, scheduler, worker
(`LocalExecutor` can merge scheduler+worker onto one process for a
low-volume project like this one). A `t3.small` or `t3.medium` running
Airflow via Docker Compose with a local Postgres metadata DB realistically
costs **$15–35/month** in raw EC2 spend for this project's DAG volume (3
DAGs, daily/weekly cadence, non-production SLA). The real cost is
operational: patching Airflow versions, managing the Postgres metadata DB,
and being the one who gets paged if the scheduler process dies at 2am —
independent benchmarking of light MWAA workloads vs. self-hosted puts the
*total* (compute + ops labor) self-hosted cost at roughly **$400+/month**
once ~10 hours/week of DevOps time is priced in, which can exceed MWAA's
light-workload cost once labor is counted, not just compute.
[Cost comparison writeup](https://www.d23.io/blog/aws-mwaa-vs-self-hosted-airflow-cost-comparison)

For a portfolio project specifically (not a business with real uptime
requirements), the labor-cost framing above matters less — an occasional
scheduler restart is an acceptable trade for near-zero compute cost — so
raw EC2 spend (**$15–35/month**) is the more relevant number here than the
"fully loaded" $400+/month figure.

### Dagster OSS (self-hosted)

Minimum architecture is **two** long-running processes (webserver + daemon)
plus a code location server per code repo, vs. Airflow's three
(webserver + scheduler + worker). Dagster defaults to SQLite for run
storage in dev, and Postgres in production — for a project this size, a
single `t3.small` running all of webserver + daemon + code server + a local
Postgres container is realistic, putting self-hosted Dagster in the same
**$15–35/month** raw-compute range as self-hosted Airflow, with a slightly
lighter process footprint (2 core services vs. 3).
[Dagster OSS deployment architecture](https://docs.dagster.io/deployment/oss/oss-deployment-architecture)

### Dagster+ (managed, mentioned for completeness)

As of the May 2026 pricing change, Dagster+ no longer has a free tier — Solo
is $10/month **plus** $0.04/credit with no included credits, and Serverless
compute is $0.01/minute. For a project running 3 lightweight daily/weekly
DAGs, this would likely land under $30–50/month, but it's a newer pricing
model (credits replaced a previous included-quota Solo tier) and is worth
re-checking at decision time rather than trusting this document's snapshot.
[Dagster+ pricing update](https://support.dagster.io/articles/3171123463-dagster-solo-and-starter-pricing-updates-may-2026)

## 6. Local dev experience

- **Airflow**: `docker-compose up` (the official Airflow quick-start
  compose file) brings up Postgres + webserver + scheduler + worker; iterate
  by editing DAG files, which Airflow's file-watcher picks up. Startup is
  slower (multiple containers) and the feedback loop is coarser (wait for
  the scheduler to notice the DAG file, then trigger a run from the UI).
- **Dagster**: `dagster dev` runs webserver + daemon in a single local
  process against SQLite, no Docker required. Materializing a single asset
  from the UI (or CLI) for fast iteration is a noticeably tighter loop than
  triggering an Airflow DAG run and waiting on the scheduler.

## 7. Two-person operational burden

Both tools require *someone* to own upgrades and handle a stuck
scheduler/daemon. Airflow's operational surface is larger (3 processes,
a more complex upgrade path historically, e.g. the 1.x→2.x migration was
notoriously painful) and better-documented for troubleshooting (much larger
community). Dagster's smaller process count and newer, cleaner codebase
mean less to keep running, but a two-person team hits problems with less
existing Stack Overflow/blog coverage when something breaks.

## Implications for this project

- Cost is roughly a wash for a **self-hosted** deployment of either tool at
  this project's scale (~$15–35/month raw compute) — cost alone does not
  settle this decision, contrary to the original brief's framing.
- MWAA is the clear cost outlier: **$225-350+/month** minimum, hard to
  justify for a portfolio project with no real production SLA.
- The asset-based model is a **materially better conceptual fit** for this
  project's Bronze→Silver→Gold table-lineage design (Section 8) than
  Airflow's task-based model — this is the strongest technical argument in
  ADR-0001, independent of cost.
- Airflow remains the safer choice if the goal is maximizing "have I used
  the tool most consultancy clients already run" — it is still the more
  common tool in the wild.
