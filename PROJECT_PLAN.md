# TMDB Data Platform — Initial Project Plan

## 1. Project Context

We want to build an end-to-end data engineering project using the TMDB API as the main data source.

The project is not intended to be generated entirely by AI. We want to work as the primary engineers, make the architectural decisions, implement the solution, review trade-offs, and document the reasoning behind the design.

Claude Code should act as a technical advisor and pair engineer.

Its role is to:

- Help review architecture.
- Review code and documentation.
- Identify risks, inconsistencies, and missing decisions.
- Suggest alternatives and trade-offs.
- Help break work into small milestones.
- Provide objective second opinions.
- Avoid implementing the entire project without discussion.
- Avoid making major architectural decisions without explaining them.
- Prefer guidance, review, and incremental support over large generated solutions.

---

## 2. Main Objective

Design and build an end-to-end data platform on AWS that ingests, processes, historizes, models, validates, and exposes movie-related data from TMDB.

The project should demonstrate practical data engineering skills in:

- REST API ingestion.
- Initial and incremental loads.
- Batch processing.
- PySpark.
- AWS Glue.
- Amazon S3.
- Apache Iceberg.
- Airflow orchestration.
- Slowly Changing Dimensions.
- SCD Type 2.
- Snapshot facts.
- Temporal relationships.
- Dimensional modeling.
- Data quality.
- Observability.
- Data marts.
- SQL consumption through Athena.
- Infrastructure as Code.

The primary goal is not to copy the full TMDB catalog.

The primary goal is to build a maintainable, observable, reproducible, and technically defensible data platform.

---

## 3. Main Business and Analytical Question

The platform should help answer:

> How does a movie evolve from announcement and production to release, popularity growth, and streaming availability?

Additional questions:

- How does the status of a movie change over time?
- How often are release dates modified?
- How does movie metadata become more complete over time?
- How do popularity, vote count, and rating evolve?
- Which actors, directors, and companies collaborate most frequently?
- How does streaming availability change by country and provider?
- Which streaming providers gain or lose catalog over time?
- How healthy and fresh is the data platform?

---

## 4. Initial Scope

### Included in the MVP

- Movies.
- Movie details.
- Movie changes.
- People related to movies.
- Cast and crew.
- Genres.
- Keywords.
- Collections.
- Production companies.
- Regional release dates.
- Popularity and voting metrics.
- Trending movies.
- Streaming providers.
- Streaming availability in one initial region.
- SCD Type 2.
- Daily snapshots.
- Incremental processing.
- Data quality.
- Analytical data marts.

### Excluded from the MVP

- TV shows.
- Seasons.
- Episodes.
- TMDB user authentication.
- Personal watchlists.
- User-created ratings.
- Downloading and storing image files.
- Machine learning recommendations.
- AI-generated content.
- Full multilingual ingestion.
- Full ingestion of the global TMDB catalog.

These can be considered future extensions.

---

## 5. Source System

The primary source is the TMDB API.

Base API:

```text
https://api.themoviedb.org/3
```

Authentication should use a TMDB API Read Access Token as a Bearer token.

### Main source groups

#### Entity discovery

- Daily Movie ID Export.
- Movie Changes.

#### Movie data

- Movie Details.
- Movie Credits.
- Movie Keywords.
- Movie External IDs.
- Movie Release Dates.
- Movie Watch Providers.

#### Person data

- Person Details.
- Person Changes.

#### Reference data

- Genres.
- Countries.
- Languages.
- Watch Providers.
- TMDB Configuration.

#### Time-varying metrics

- Movie popularity.
- Vote average.
- Vote count.
- Trending movies.

---

## 6. Proposed Technology Stack

### Amazon S3

Responsibilities:

- Store immutable raw JSON responses.
- Store manifests and checkpoints.
- Store rejected records.
- Store Parquet and Iceberg data files.
- Act as the physical storage layer for the lakehouse.

Suggested prefixes:

```text
s3://tmdb-data-platform/raw/
s3://tmdb-data-platform/bronze/
s3://tmdb-data-platform/silver/
s3://tmdb-data-platform/gold/
s3://tmdb-data-platform/manifests/
s3://tmdb-data-platform/checkpoints/
s3://tmdb-data-platform/errors/
```

### Apache Airflow

Responsibilities:

- Orchestrate pipelines.
- Coordinate extraction and transformation.
- Manage dependencies.
- Trigger AWS Glue jobs.
- Manage retries.
- Coordinate watermarks.
- Run validation tasks.
- Publish operational metadata.

Airflow should not perform heavy transformations.

### AWS Glue

Responsibilities:

- Execute PySpark processing.
- Read raw JSON from S3.
- Parse nested structures.
- Build Bronze, Silver, and Gold datasets.
- Apply MERGE operations.
- Apply SCD Type 2 logic.
- Build snapshots and data marts.

### Apache Spark / PySpark

Responsibilities:

- Distributed transformation.
- Schema normalization.
- Array explosion.
- Deduplication.
- Change detection.
- Hash generation.
- SCD Type 2 processing.
- Snapshot construction.
- Data quality validations.

### Apache Iceberg

Responsibilities:

- Transactional tables over S3.
- MERGE, UPDATE, and DELETE.
- Schema evolution.
- Snapshot management.
- Time travel.
- Historical table state.
- Support for incremental and SCD workloads.

### AWS Glue Data Catalog

Responsibilities:

- Register Iceberg tables.
- Centralize metadata.
- Expose databases and tables to query engines.

### Amazon Athena

Responsibilities:

- Query Iceberg tables using SQL.
- Validate results.
- Explore datasets.
- Serve initial analytical data marts.
- Connect to a BI tool.

### Infrastructure as Code

Preferred option:

- Terraform.

Responsibilities:

- S3 buckets.
- IAM roles and policies.
- Glue jobs.
- Glue databases.
- Networking if required.
- Airflow infrastructure.
- Logging and monitoring resources.

### BI and Visualization

Possible options:

- Apache Superset.
- Metabase.
- Amazon QuickSight.

The initial choice can be made later.

---

## 7. High-Level Architecture

```text
TMDB API
   |
   v
Airflow
   |
   +--> API extraction
   +--> batching
   +--> retries
   +--> watermarks
   +--> Glue job orchestration
   |
   v
Amazon S3 Raw
   |
   v
AWS Glue + PySpark
   |
   v
Apache Iceberg
   |
   +--> Bronze
   +--> Silver
   +--> Gold
   |
   v
Glue Data Catalog
   |
   v
Athena / BI
```

---

## 8. Data Layers

## Raw Layer

Purpose:

Preserve the original TMDB response.

Characteristics:

- Immutable.
- JSON format.
- Partitioned by extraction date.
- Organized by endpoint.
- Includes technical ingestion metadata.
- Supports replay and reprocessing.

Suggested raw metadata:

```text
pipeline_run_id
request_id
endpoint
source_entity_id
http_status
extraction_timestamp
ingestion_date
payload
```

Example layout:

```text
raw/tmdb/movie_details/extraction_date=YYYY-MM-DD/
raw/tmdb/movie_credits/extraction_date=YYYY-MM-DD/
raw/tmdb/movie_changes/extraction_date=YYYY-MM-DD/
raw/tmdb/watch_providers/extraction_date=YYYY-MM-DD/
```

## Bronze Layer

Purpose:

Convert raw payloads into typed and structured source-oriented datasets.

Responsibilities:

- Parse JSON.
- Apply explicit schemas.
- Preserve source naming where practical.
- Separate nested arrays and structs.
- Keep technical metadata.
- Avoid complex business logic.

Possible tables:

```text
bronze_movie_details
bronze_movie_credits
bronze_person_details
bronze_release_dates
bronze_watch_providers
bronze_movie_changes
bronze_trending_movies
```

## Silver Layer

Purpose:

Create cleaned, deduplicated, historized, and reusable analytical entities.

Responsibilities:

- Define business keys.
- Generate surrogate keys.
- Apply SCD Type 1 and Type 2.
- Normalize many-to-many relationships.
- Standardize dates, countries, and languages.
- Resolve duplicates.
- Apply integrity validations.

Possible tables:

```text
silver_dim_movie
silver_dim_person
silver_dim_provider
silver_dim_genre
silver_dim_company
silver_dim_collection
silver_dim_keyword
silver_movie_credit
silver_movie_release
silver_movie_provider_availability
silver_movie_metrics_snapshot
```

## Gold Layer

Purpose:

Provide consumption-ready data marts.

Responsibilities:

- Define analytical grains.
- Define reusable business metrics.
- Simplify downstream SQL.
- Support dashboards and analysis.

Possible marts:

```text
gold_movie_lifecycle
gold_movie_performance
gold_talent_collaboration
gold_streaming_catalog
gold_popularity_trends
gold_data_quality
```

---

## 9. Ingestion Strategies

## Initial Load

Purpose:

Create the initial movie catalog.

Suggested flow:

```text
Daily Movie ID Export
        |
        v
Define project scope
        |
        v
Filter movie IDs
        |
        v
Create extraction batches
        |
        v
Extract movie and related data
        |
        v
Store immutable raw data
        |
        v
Build Bronze and Silver tables
```

The first version should not ingest the complete TMDB catalog.

Possible scope filters:

- Movies released after a selected year.
- Minimum vote count.
- Exclude adult content.
- Selected languages.
- Selected countries.
- Fixed maximum number of movie IDs.

The final scope should be documented as an explicit engineering decision.

## Incremental Load

Purpose:

Process only movies that changed.

Suggested flow:

```text
Read previous watermark
        |
        v
Call Movie Changes
        |
        v
Collect changed movie IDs
        |
        v
Extract current movie details
        |
        v
Store new raw responses
        |
        v
Compare with current Silver state
        |
        v
Apply SCD or update relationships
        |
        v
Run quality checks
        |
        v
Advance watermark
```

The watermark must only be updated after a successful pipeline run.

## Periodic Snapshots

Some attributes should not generate new SCD versions.

Daily snapshot candidates:

```text
movie_id
snapshot_date
popularity
vote_average
vote_count
```

Trending should also be stored as a snapshot.

Streaming availability can initially be refreshed weekly.

---

## 10. Historical Modeling Strategy

## SCD Type 2 — Movie

Business key:

```text
tmdb_movie_id
```

Surrogate key:

```text
movie_sk
```

Candidate historical attributes:

```text
title
original_title
overview
tagline
status
release_date
runtime
budget
revenue
adult
video
homepage
poster_path
backdrop_path
original_language
collection_id
```

Technical attributes:

```text
valid_from
valid_to
is_current
version_number
record_hash
created_at
updated_at
pipeline_run_id
```

Do not include rapidly changing metrics such as popularity and vote count in this SCD table.

## SCD Type 2 — Person

Business key:

```text
tmdb_person_id
```

Candidate historical attributes:

```text
name
biography
birthday
deathday
place_of_birth
known_for_department
gender
homepage
profile_path
imdb_id
```

Do not include person popularity in this SCD table.

## SCD Type 2 — Provider

Possible business key:

```text
provider_id + region_code
```

Candidate historical attributes:

```text
provider_name
logo_path
display_priority
region_code
```

## Historical Relationship — Streaming Availability

This should not be modeled as a simple movie attribute.

Grain:

```text
movie
+ provider
+ country
+ availability_type
+ validity period
```

Suggested attributes:

```text
movie_id
provider_id
country_code
availability_type
valid_from
valid_to
is_current
```

Availability types may include:

```text
flatrate
rent
buy
free
ads
```

## Snapshot Fact — Movie Metrics

Grain:

```text
snapshot_date + movie_id
```

Attributes:

```text
popularity
vote_average
vote_count
```

## Type 1 Dimensions

Candidates:

```text
dim_genre
dim_country
dim_language
dim_release_type
dim_credit_department
dim_credit_job
```

---

## 11. Data Marts

## Movie Lifecycle Mart

Purpose:

Reconstruct how a movie changes over time.

Questions:

- How long does a movie remain in each status?
- How often does its release date change?
- When does runtime become available?
- When are budget and revenue added?
- When does the poster change?
- When does it become available on streaming platforms?

Main inputs:

```text
dim_movie_scd2
movie_release_history
movie_provider_availability_history
fact_movie_metrics_daily
```

## Movie Performance Mart

Purpose:

Analyze movie performance.

Metrics:

```text
budget
revenue
estimated_profit
estimated_roi
popularity
vote_average
vote_count
```

Dimensions:

```text
genre
release_year
country
language
company
collection
```

Important rule:

A source value of zero for budget or revenue may represent missing data rather than a true zero.

## Talent Collaboration Mart

Purpose:

Analyze relationships between people and movies.

Questions:

- Which actors collaborate most often?
- Which actor-director pairs collaborate most?
- Which directors have the highest weighted ratings?
- Which people work across multiple departments?
- How does a person's career evolve over time?

## Streaming Availability Mart

Purpose:

Analyze streaming catalog changes.

Questions:

- Which provider has the largest catalog?
- Which movies are exclusive?
- Which provider gains or loses more titles?
- How long does a movie remain on a provider?
- Which genres dominate each provider?

## Popularity Trends Mart

Purpose:

Analyze changing engagement metrics.

Questions:

- Which movies grow fastest in popularity?
- How long do movies remain in trending?
- Which genres appear most often?
- How does rating change as vote count increases?

## Data Quality Mart

Purpose:

Expose the health of the platform.

Metrics:

```text
records_received
records_processed
records_rejected
null_rate
duplicate_rate
invalid_relationship_count
api_error_count
retry_count
freshness_minutes
pipeline_duration
```

---

## 12. Orchestration Plan

## Initial Load DAG

```text
download_daily_movie_ids
        |
        v
filter_movie_scope
        |
        v
create_batches
        |
        v
extract_movie_details
        |
        v
extract_related_entities
        |
        v
validate_raw_data
        |
        v
run_bronze_jobs
        |
        v
run_silver_jobs
        |
        v
run_quality_checks
        |
        v
build_gold_marts
```

## Daily Incremental DAG

```text
read_watermark
        |
        v
extract_movie_changes
        |
        v
extract_changed_movie_ids
        |
        v
extract_current_movie_data
        |
        v
store_raw_data
        |
        v
run_bronze_jobs
        |
        v
apply_scd2
        |
        v
refresh_relationships
        |
        v
capture_daily_metrics
        |
        v
run_quality_checks
        |
        v
update_watermark
```

## Streaming Availability DAG

```text
select_movie_population
        |
        v
extract_watch_providers
        |
        v
compare_current_state
        |
        v
close_removed_relationships
        |
        v
insert_new_relationships
        |
        v
refresh_streaming_mart
```

---

## 13. Data Quality Requirements

### Technical validations

- Valid HTTP status.
- Valid JSON.
- Non-empty payload where expected.
- Required source ID present.
- Valid extraction timestamp.
- No duplicates within the same batch.
- Expected number of records within reasonable thresholds.

### Business validations

- `movie_id` must not be null.
- Only one current SCD version per business key.
- `valid_from` must be before `valid_to`.
- SCD validity periods must not overlap.
- `vote_average` must be within the valid source range.
- `vote_count` must be non-negative.
- `runtime` must be non-negative.
- Credits must reference valid movies and people.
- Streaming availability must reference valid providers and countries.

### Referential integrity validations

- No orphan movie credits.
- No orphan movie-genre relationships.
- No unknown provider references.
- No multiple current records for the same natural key.

---

## 14. Observability Requirements

Minimum metrics:

```text
requests_sent
requests_succeeded
requests_failed
rate_limit_responses
retry_count
average_latency
movie_ids_processed
movie_ids_failed
records_inserted
records_updated
new_scd_versions
unchanged_records
task_duration
pipeline_duration
watermark_processed
table_freshness
```

Suggested log context:

```text
pipeline_run_id
dag_id
task_id
entity_id
endpoint
attempt
status
error_type
timestamp
```

---

## 15. Repository Structure

```text
tmdb-data-platform/
|
├── README.md
├── Makefile
├── pyproject.toml
├── .env.example
├── .gitignore
|
├── docs/
│   ├── architecture/
│   │   ├── architecture-overview.md
│   │   ├── data-flow.md
│   │   └── architecture-decisions/
│   |
│   ├── source-analysis/
│   │   ├── tmdb-api-overview.md
│   │   ├── endpoint-inventory.md
│   │   └── source-to-target.md
│   |
│   ├── modeling/
│   │   ├── conceptual-model.md
│   │   ├── logical-model.md
│   │   ├── scd-strategy.md
│   │   └── data-marts.md
│   |
│   └── operations/
│       ├── runbook.md
│       ├── data-quality.md
│       └── incident-handling.md
|
├── infrastructure/
│   └── terraform/
│       ├── modules/
│       ├── environments/
│       └── main.tf
|
├── airflow/
│   ├── dags/
│   ├── task_groups/
│   ├── operators/
│   ├── sensors/
│   └── tests/
|
├── ingestion/
│   ├── tmdb_client/
│   ├── extractors/
│   ├── pagination/
│   ├── retries/
│   ├── schemas/
│   └── tests/
|
├── glue/
│   ├── bronze/
│   ├── silver/
│   ├── gold/
│   ├── common/
│   └── tests/
|
├── sql/
│   ├── athena/
│   ├── quality/
│   └── marts/
|
├── config/
│   ├── endpoints.yml
│   ├── environments.yml
│   ├── data_quality.yml
│   └── tables.yml
|
├── dashboards/
│   ├── analytics/
│   └── monitoring/
|
└── tests/
    ├── unit/
    ├── integration/
    └── data/
```

---

## 16. Team Structure

There are initially two engineers.

## Engineer 1 — Platform and Ingestion

Responsibilities:

- TMDB API client.
- Authentication.
- Pagination.
- Retry and backoff.
- Raw ingestion.
- Batch management.
- Watermarks.
- Airflow DAGs.
- Infrastructure.
- Technical logging.
- API observability.

## Engineer 2 — Processing and Modeling

Responsibilities:

- Bronze schemas.
- PySpark transformations.
- Silver models.
- SCD Type 2.
- Historical relationships.
- Snapshots.
- Data marts.
- Data quality.
- Model documentation.

## Shared Responsibilities

- Architecture decisions.
- Pull request reviews.
- Contracts between layers.
- Documentation.
- Integration testing.
- Metric definitions.
- Final demonstrations.

Both engineers should review each other's work to avoid knowledge silos.

---

## 17. Working Principles

- Do not build everything at once.
- Prefer small vertical slices.
- Every iteration should produce queryable data.
- Document important decisions.
- Use Architecture Decision Records.
- Every pipeline must be idempotent.
- Every pipeline must be observable.
- Every table must have a documented grain.
- Preserve raw data for replay.
- Separate descriptive history from rapidly changing metrics.
- Separate entity attributes from temporal relationships.
- Avoid introducing technology without a clear need.
- Avoid premature optimization.
- Prefer explicit schemas over uncontrolled schema inference.
- Prefer configuration over hard-coded limits.

---

## 18. Definition of Done

A task is complete when:

- The code works.
- It has tests.
- It is documented.
- It includes data quality checks.
- It is observable.
- It can be rerun safely.
- It does not produce duplicates.
- Its output can be queried.
- It has been reviewed by the other engineer.

---

## 19. Project Phases

## Phase 0 — Discovery and Design

Goal:

Understand TMDB and define the initial architecture.

Deliverables:

- Endpoint inventory.
- Source-to-target document.
- High-level architecture diagram.
- Conceptual data model.
- Initial scope decision.
- Risk register.
- Initial ADRs.

## Phase 1 — Minimal Raw Ingestion

Goal:

Extract movie data and persist original JSON.

Deliverables:

- TMDB client.
- Authentication.
- Extraction by movie ID.
- Retry and error handling.
- S3 raw persistence.
- Technical metadata.
- First Airflow DAG.

## Phase 2 — Bronze Layer

Goal:

Convert raw JSON into typed source-oriented tables.

Deliverables:

- Explicit schemas.
- Bronze tables.
- Nested structure normalization.
- Initial partitioning.
- Catalog registration.
- Technical quality checks.

## Phase 3 — Silver and SCD Type 2

Goal:

Build the first historized analytical entities.

Deliverables:

- `dim_movie_scd2`.
- `dim_person_scd2`.
- Genre relationships.
- Credits.
- Keywords.
- SCD overlap tests.
- Current-record uniqueness tests.

## Phase 4 — Incremental Processing

Goal:

Process only changed entities.

Deliverables:

- Movie Changes ingestion.
- Watermark management.
- Re-extraction by changed ID.
- Change detection.
- Idempotent reruns.
- Controlled reprocessing.

## Phase 5 — Snapshots and Temporal Relationships

Goal:

Model rapidly changing values and historical relationships.

Deliverables:

- Daily movie metrics.
- Trending snapshots.
- Streaming availability history.
- Release date history.

## Phase 6 — Data Marts

Goal:

Build consumption-oriented models.

Deliverables:

- Movie Lifecycle Mart.
- Movie Performance Mart.
- Streaming Availability Mart.
- Talent Collaboration Mart.
- Data Quality Mart.

## Phase 7 — BI and Operations

Goal:

Expose analytical and operational results.

Deliverables:

- Analytical dashboard.
- Operational dashboard.
- Alerts.
- Runbook.
- Incident handling documentation.

---

## 20. First Milestone

The first milestone should be a small complete vertical slice.

Scope:

```text
TMDB Movie Details
        |
        v
S3 Raw
        |
        v
Glue Bronze
        |
        v
Iceberg Silver
        |
        v
dim_movie_scd2
        |
        v
Athena historical query
```

Demonstration:

1. Ingest one or more movies.
2. Create the initial SCD version.
3. Simulate or detect a source change.
4. Close the previous version.
5. Insert the new version.
6. Query the entity before and after the change.
7. Verify that only one version is current.
8. Verify that validity periods do not overlap.

This milestone should prove:

- API ingestion.
- S3 raw storage.
- Glue processing.
- Iceberg tables.
- SCD Type 2.
- Airflow orchestration.
- Athena querying.
- Data quality.
- Idempotency.

---

## 21. Initial Documents to Create

Before large-scale implementation, create:

```text
docs/source-analysis/tmdb-api-overview.md
docs/source-analysis/endpoint-inventory.md
docs/source-analysis/source-to-target.md
docs/architecture/architecture-overview.md
docs/architecture/data-flow.md
docs/modeling/conceptual-model.md
docs/modeling/scd-strategy.md
docs/modeling/data-marts.md
```

The source-to-target document should include:

```text
endpoint
source_entity
source_grain
business_key
pagination
load_frequency
load_type
destination_layer
destination_table
nested_structures
historical_strategy
quality_risks
owner
```

---

## 22. Instructions for Claude Code

When helping with this project:

1. Do not generate the entire platform at once.
2. Start by reviewing the current repository and project phase.
3. Identify missing decisions before proposing implementation.
4. Explain trade-offs for architecture recommendations.
5. Prefer small, reviewable changes.
6. Do not introduce new libraries or AWS services without justification.
7. Do not replace engineering decisions with assumptions.
8. Clearly distinguish:
   - recommendation,
   - decision,
   - assumption,
   - unresolved question.
9. Review for:
   - idempotency,
   - observability,
   - testability,
   - data quality,
   - cost,
   - maintainability,
   - security,
   - recoverability.
10. Preserve layer boundaries:
    - Airflow orchestrates.
    - Ingestion extracts.
    - S3 raw preserves.
    - Glue and Spark transform.
    - Iceberg stores analytical state.
    - Athena consumes.
11. Avoid putting heavy transformation logic inside Airflow DAG files.
12. Avoid applying SCD Type 2 to every changing value.
13. Treat popularity and voting metrics as snapshots.
14. Treat streaming availability as a temporal relationship.
15. Ask for or document the grain of every new table.
16. Suggest tests for every transformation.
17. Prefer explicit configuration and schemas.
18. Help update documentation whenever architecture or behavior changes.
19. Challenge decisions objectively when there is a simpler or safer alternative.
20. Keep humans as the owners of final technical decisions.

---

## 23. Recommended First Claude Code Task

Use this prompt after adding this file to the repository:

```text
Review PROJECT_PLAN.md and help us prepare Phase 0.

Do not implement the platform yet.

Create a proposed checklist for the discovery and design phase, including:

- architecture decisions that must be made,
- TMDB endpoints that must be researched,
- source-to-target fields,
- open questions,
- risks,
- acceptance criteria,
- and the minimum documents required before starting ingestion.

Clearly separate recommendations from decisions that still require human approval.
```
