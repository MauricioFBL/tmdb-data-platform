# Conceptual Model

This is the entity/relationship model before physical design (before
deciding table names, SCD mechanics, or file formats — see
`scd-strategy.md` and `data-marts.md` for those). It formalizes
`PROJECT_PLAN.md` Sections 5, 8, and 10.

## Core entities

| Entity | Business key | Nature | Notes |
|---|---|---|---|
| **Movie** | `tmdb_movie_id` | Slowly changing | Title, overview, status, release_date, runtime, budget, revenue, etc. — see `scd-strategy.md` for the full attribute list. |
| **Person** | `tmdb_person_id` | Slowly changing | Actors, directors, crew. Biography/name/birthday change rarely but do change (corrections, deaths). |
| **Provider** | `provider_id + region_code` | Slowly changing | A streaming provider *as it exists in a specific region* — the same TMDB provider_id can have a different name/logo/priority per region. |
| **Genre / Country / Language / Credit Department / Credit Job** | source id | Reference (Type 1) | Low cardinality, effectively static vocabularies. Overwritten in place, no history needed. |
| **Collection** | `tmdb_collection_id` | Reference-like | Franchise groupings (e.g. "James Bond Collection"). Treated as Type 1 for the MVP — a collection's own metadata changing is out of scope; only its membership (which movies belong to it) matters, captured as an attribute on Movie. |

## Relationships

- **Movie ↔ Person** (many-to-many, via **Credit**): a person appears on a
  movie in a specific department/job (e.g., "Directing / Director",
  "Acting / Actor"), and cast credits carry a `character` and `order`
  (billing position). This is not a plain junction table — the credit
  itself is a fact with attributes (department, job, character, order),
  not just a relationship.
- **Movie ↔ Genre** (many-to-many): a movie has zero or more genres, flat,
  no attributes on the relationship itself.
- **Movie ↔ Keyword** (many-to-many): same shape as Movie ↔ Genre.
- **Movie ↔ Production Company** (many-to-many): a movie has one or more
  producing companies; the relationship carries no time-varying attributes
  in the MVP.
- **Movie ↔ Provider** (many-to-many, **time-varying**, via **Availability**):
  a movie is available through a provider, in a country, under an
  `availability_type` (flatrate/rent/buy/free/ads), and this fact has a
  validity period — it is fundamentally different from the relationships
  above because it changes on its own schedule, independent of any change
  to the Movie or Provider entities themselves. See "Attributes vs.
  relationships vs. metrics" below.
- **Movie ↔ Release Date** (one-to-many, **time-varying**): a movie has a
  release date per country/release-type combination (theatrical, digital,
  physical, premiere), and these dates are themselves subject to change
  (a release getting pushed back is a first-class event this platform
  should be able to answer questions about — see `PROJECT_PLAN.md`
  Section 3).
- **Movie ↔ Collection** (many-to-one, optional): a movie may belong to at
  most one collection.

## Attributes vs. relationships vs. metrics — the modeling rule that drives everything else

Three different things change about a Movie, and conflating them is the
single biggest risk in this data model (this is why `PROJECT_PLAN.md`
Section 22 explicitly calls out "avoid applying SCD Type 2 to every
changing value" and "treat streaming availability as a temporal
relationship" as standing review criteria):

1. **Descriptive attributes** of the movie itself (title, status, runtime,
   budget...) — these change *rarely* and *meaningfully*. → SCD Type 2 on
   the dimension (`scd-strategy.md`).
2. **Rapidly changing engagement metrics** (popularity, vote_average,
   vote_count) — these change on *every* API call, often trivially (a
   popularity score drifting by 0.001). Modeling this as SCD2 would create
   a new dimension version on almost every incremental run, destroying the
   signal-to-noise ratio of the movie's actual history. → Daily snapshot
   fact, not a dimension attribute.
3. **Temporal relationships to other entities** (streaming availability,
   release dates) — these aren't attributes of the movie at all; they're
   facts about a *relationship* that has its own validity period,
   independent of whether the movie's own descriptive attributes changed.
   → Historized relationship/bridge table with `valid_from`/`valid_to`,
   not a movie attribute and not a plain SCD2 dimension.

## Conceptual diagram

```text
                         +-------------------+
                         |     Collection    |  (Type 1)
                         +-------------------+
                                   ^
                                   | (0..1)
+------------+   (M:N via         |
|   Genre    |<--- flat) ---+     |
| (Type 1)   |               \    |
+------------+                v   v
                         +-------------------+          +----------------+
+------------+           |       Movie       |--------->|  Release Date  |
|  Keyword   |<--(M:N)-->|  (SCD Type 2)     |  (1:N,   |  (time-varying)|
| (Type 1)   |           +-------------------+   temporal)+----------------+
+------------+                 ^   ^  ^
                                |   |  |
              +-----------------+  |  +------------------+
              |                    |                     |
     (M:N via Credit,     (daily snapshot)      (M:N via Availability,
      fact w/ attrs)              |                time-varying)
              |                    v                     |
      +--------------+   +-------------------+   +----------------+
      |    Person    |   | Movie Metrics     |   |    Provider    |
      | (SCD Type 2) |   | Snapshot (fact)   |   | (SCD Type 2,   |
      +--------------+   +-------------------+   |  key: id+region)|
                                                   +----------------+
```

## Grain statements (formal — every table must have one)

| Conceptual entity | Grain |
|---|---|
| Movie (dimension) | One row per `tmdb_movie_id` per historical version |
| Person (dimension) | One row per `tmdb_person_id` per historical version |
| Provider (dimension) | One row per `provider_id + region_code` per historical version |
| Credit | One row per `movie_id + person_id + department + job` (a person can hold multiple jobs on the same movie, e.g. director *and* writer) |
| Availability | One row per `movie_id + provider_id + country_code + availability_type` per validity period |
| Release Date | One row per `movie_id + country_code + release_type` per validity period |
| Movie Metrics Snapshot | One row per `movie_id + snapshot_date` |

See `scd-strategy.md` for how "per historical version" and "per validity
period" are physically implemented, and `data-marts.md` for how these
conceptual entities get reassembled into consumption-grain marts.
