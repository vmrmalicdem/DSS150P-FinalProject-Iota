# Short-Video Risk Pipeline

An end-to-end data engineering pipeline that turns raw short-video interaction logs into
daily, per-user behavioral features — things like late-night usage share, session counts,
and rewatch/hate rates — loaded into PostgreSQL for downstream risk scoring.

## 1. Problem statement & objectives

Short-video platforms generate huge volumes of raw interaction events (exposures, watch
time, likes, hates, follows) that are not usable on their own: one CSV row is one *tag* on
one exposure, not one user action, and the file mixes true user behavior with a large
proportion of exact duplicate rows. Before any downstream consumer — a risk model, a
reporting dashboard, an analyst — can ask "which users show risky late-night binge
patterns?", the data needs to be de-duplicated, collapsed into real events, and aggregated
into daily per-user features.

**Objective:** build an automated, rerun-safe pipeline that ingests the raw source files,
validates them, and produces a daily `daily_user_features` table in PostgreSQL suitable as
input to a future user-risk model.

**Target consumer:** a downstream risk-scoring process (the `risk_scores` table exists in
the schema as the intended target; the scoring method itself is out of scope for this
project — see Limitations).

**Why a pipeline and not a one-off analysis:** the source data is inherently structured as
daily partitions and is meant to be processed incrementally, one day at a time, exactly the
way a production system would receive new days of data. A single notebook run once on a
static file would not demonstrate or support that operating model.

## Team Members
- QUERIJERO, ELIJAH BRADLEY
- AGUAVIVA, YUVAL MA. EZEKIEL
- MALICDEM, VINCE MARTIN  


## 2. Data sources

| Source | Format | Rows/files | Role |
| --- | --- | --- | --- |
| `interaction_sampled.csv` | CSV | 794,053 rows / 129,483 real events (7 days: 2022-09-16 → 2022-09-22) | Primary fact source: user–video exposure events |
| `categories_cn_en.csv` | CSV | 826 rows | Category id → Chinese/English label lookup |
| `asr_en/*.txt` | Plain text | 10 files | Sample video transcripts (English), joined onto videos by filename = `pid` |

Full provenance, access notes, and how to place these under `data_sources/` are in
[`docs/data-sources-setup.md`](docs/data-sources-setup.md). Full profiling — nulls, ranges,
duplicates, and every data-quality issue found — is in
[`docs/source-profiling-report.md`](docs/source-profiling-report.md).

## 3. Architecture & technology stack

```
data_sources/ (CSV, CSV, TXT)
        │  scripts/ingest.py
        ▼
raw/  (Parquet, partitioned by p_date, one partition per calendar day, immutable once written)
        │  scripts/validate.py  (schema, type, range, uniqueness, referential, business-rule checks)
        ▼
staging/  (Parquet: dedup'd, standardized, cross-partition ownership resolved)
        │  scripts/stage.py → scripts/curate.py
        ▼
curated/  (Parquet: interactions_curated, daily_user_features, dims/{users,videos,categories,video_categories})
        │  scripts/load_postgres.py  (upsert dimensions, replace-partition facts)
        ▼
PostgreSQL  (sql/schema.sql)
        │
        ▼
Apache Airflow  (dags/short_video_risk_dag.py)  orchestrates ingest → validate → stage → curate → load, per p_date
        │
        ▼
Docker Compose  (docker-compose.yml)  runs Postgres, Airflow metadata DB, webserver, scheduler, and a CLI runner
```

| Layer | Technology | Why |
| --- | --- | --- |
| Ingestion / transformation | Python (pandas) | Row-level and columnar operations needed for dedup, joins, and feature derivation |
| Storage (raw/staging/curated) | Parquet, partitioned by `p_date` | Columnar, compressed, supports reading a single date without a full scan |
| Structured storage | PostgreSQL | Constraints, foreign keys, and SQL querying for the curated output |
| Orchestration | Apache Airflow | Task dependencies, retries, scheduling, and per-partition backfill (`catchup=True`) |
| Containerization | Docker / Docker Compose | Reproducible environment; Postgres, Airflow, and the pipeline code all run the same way on any machine |

## 4. Repository structure

```
.
├── Dockerfile, docker-compose.yml, .dockerignore   containerized environment
├── .env.example                                    configuration template (copy to .env)
├── requirements.txt
├── dags/short_video_risk_dag.py                    Airflow DAG
├── scripts/
│   ├── config.py            environment/config loading
│   ├── io_utils.py           shared path/partition helpers
│   ├── ingest.py             source → raw
│   ├── validate.py           raw partition validation checks
│   ├── stage.py               raw → staging (dedup, standardize, cross-partition ownership)
│   ├── curate.py              staging → curated (feature derivation)
│   ├── load_postgres.py      curated → PostgreSQL (upsert / replace-partition)
│   ├── run_pipeline.py       CLI entrypoint that runs all stages for one or all partitions
│   ├── benchmark_formats.py  CSV vs JSON vs Parquet comparison (size, speed, schema fidelity)
│   ├── partition_demo.py     reading one partition vs scanning everything
│   └── bench_utils.py        timing helpers shared by the two benchmark scripts
├── sql/schema.sql, sql/queries.sql                 DDL and representative queries
├── tests/                                          pytest suite (see section 12)
├── pytest.ini, requirements-dev.txt                test configuration and dev dependencies
├── .github/workflows/tests.yml                     CI: runs the suite against a PostgreSQL service on every push
├── docs/
│   ├── data-sources-setup.md         source provenance & how to place data_sources/
│   ├── source-profiling-report.md    full profiling of the actual source files
│   ├── data-dictionary.md            field-level docs for every curated table
│   ├── data-contract-daily-user-features.md
│   ├── transformation-spec.md        exact cleaning/dedup/feature rules
│   ├── format-comparison-and-partitioning.md   file-format trade-offs and partitioning, with measured results
│   ├── erd.puml / erd.svg / erd.png  ER diagram (PlantUML source and renders)
│   └── erd.md                        ER diagram notes, keys and rules
├── raw/, staging/, curated/                        pipeline data (gitignored contents)
├── outputs/benchmarks/                             committed benchmark results (JSON + Markdown)
└── data_sources/                                    you create this locally, see docs/data-sources-setup.md
```

## 5. Installation & prerequisites

- Docker Desktop (or Docker Engine + Compose v2) — for the full Airflow + Postgres setup
- Python 3.11+ — only needed if running the pipeline scripts directly, outside Docker
- The three source files, placed under `data_sources/` per
  [`docs/data-sources-setup.md`](docs/data-sources-setup.md) (this folder is gitignored and
  not part of the repository, since the interaction file is ~160 MB)

## 6. Configuration

```bash
cp .env.example .env
```
Then edit `.env` and replace every `change_me_*` value — Postgres won't start with a blank
password. Key variables:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | warehouse connection. Compose overrides `POSTGRES_HOST` to `postgres` inside containers — leave it as `localhost` in `.env` for running scripts directly on your own machine |
| `SOURCE_DATA_DIR`, `RAW_DATA_DIR`, `STAGING_DATA_DIR`, `CURATED_DATA_DIR` | pipeline paths, default to `./data_sources`, `./raw`, `./staging`, `./curated`; `OUTPUTS_DIR` (default `./outputs`) receives benchmark results |
| `AIRFLOW_UID` | on Linux, set to your host user id (`id -u`) so files written into the mounted volumes stay owned by you; leave at `50000` on Windows/macOS |
| `AIRFLOW_DB_PASSWORD`, `AIRFLOW_ADMIN_USER`, `AIRFLOW_ADMIN_PASSWORD` | Airflow's own metadata DB and UI login |
| `LATE_NIGHT_START_HOUR`, `LATE_NIGHT_END_HOUR`, `SESSION_GAP_SECONDS`, `MIN_USER_EVENTS` | feature-derivation thresholds, see [`docs/transformation-spec.md`](docs/transformation-spec.md) §5 |

No real secrets are committed; `.env` is gitignored.

## 7. Running everything with Docker

```bash
docker compose up -d --build
docker compose ps       # wait until airflow-webserver and airflow-scheduler are healthy
```

`airflow-init` runs once — migrates Airflow's metadata DB, creates the admin user, fixes
folder permissions — then exits; that's expected, not a failure.

**Start PostgreSQL only** (e.g. to run pipeline scripts directly against it):
```bash
docker compose up -d postgres
```
The schema in `sql/schema.sql` is applied automatically by `scripts/load_postgres.py` on
first load (`CREATE TABLE IF NOT EXISTS`), so no separate init step is needed.

**Run the Airflow DAG:**
```bash
docker compose exec airflow-scheduler airflow dags unpause short_video_risk_pipeline
docker compose exec airflow-scheduler airflow dags trigger short_video_risk_pipeline \
  --conf '{"p_date": "20220918"}'
```
Or leave it unpaused — `catchup=True` with a `@daily` schedule starting 2022-09-16 replays
the whole 7-day source range one partition at a time, `max_active_runs=1`.

**Inspect runs / logs:**
```bash
docker compose exec airflow-scheduler airflow dags list-runs -d short_video_risk_pipeline
```
or open http://localhost:8080 (login from `.env`).

**Check the curated warehouse:**
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT p_date, count(*) FROM interactions_curated GROUP BY 1 ORDER BY 1;"
```

**Stop:**
```bash
docker compose down       # keep data
docker compose down -v    # also delete both databases
```

## 8. Running without Docker/Airflow

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d postgres                          # or point POSTGRES_HOST at your own instance
python scripts/run_pipeline.py --all                    # every raw partition, oldest first
python scripts/run_pipeline.py --date 20220918          # a single partition
python scripts/run_pipeline.py --all --skip-load        # stop after curation, don't touch Postgres
```
The first run against an empty `raw/` ingests from `data_sources/`; on later runs the raw
layer is treated as immutable and ingestion is skipped if the partition already exists.

## 9. Data quality & validation

`scripts/validate.py` runs automated checks on every raw partition before it's allowed into
staging — schema/column presence, data types, nullability, accepted-value sets (e.g.
`gender ∈ {M, F}`), numeric ranges, referential integrity of `category_id` against the
category lookup, and row-count sanity. A failure raises `AirflowFailException` in the DAG so
the task shows red in the Airflow UI with the specific check that failed in the task log,
rather than continuing on bad data. Known non-fatal data-quality findings (e.g. the 6
`category_id`s with conflicting English labels) are logged as warnings, not failures — see
[`docs/source-profiling-report.md`](docs/source-profiling-report.md) for the full list.

## 10. Expected outputs

| Output | Location |
| --- | --- |
| Raw Parquet, one partition per `p_date` | `raw/interactions/p_date=YYYYMMDD/` |
| Staging Parquet (deduplicated, standardized) | `staging/interactions/p_date=YYYYMMDD/` |
| Curated fact tables | `curated/interactions_curated/p_date=.../`, `curated/daily_user_features/p_date=.../` |
| Curated dimensions (rebuilt whole each run) | `curated/dims/{users,videos,categories,video_categories}.parquet` |
| PostgreSQL warehouse | tables defined in `sql/schema.sql`; representative queries in `sql/queries.sql` |
| Ingestion lineage log | `raw/_ingestion_log/ingestion_log.jsonl` |
| Validation reports / run statistics | `staging/_validation/*.json`, `staging/_stats/*.json` |
| Format and partition benchmark results | `outputs/benchmarks/` |

Full field-level documentation for every curated table is in
[`docs/data-dictionary.md`](docs/data-dictionary.md).

## 11. File formats & partitioning

The pipeline uses each format where it fits: **CSV** for the source-faithful raw layer, **Parquet** for staging
and curated data, **JSON** for validation reports and run statistics, and **JSON Lines** for the append-only
ingestion log. Fact tables are partitioned by `p_date`, one file per day.

```bash
python scripts/run_pipeline.py --all --skip-load            # build the layers first
python scripts/benchmark_formats.py --repeats 5             # CSV vs JSON vs Parquet
python scripts/partition_demo.py --date 20220919 --repeats 15   # one partition vs full scan
```

Headline results on the real data (129,483 curated events; timings are machine-dependent, compare the ratios):

| Measure | Result |
| --- | --- |
| Parquet size vs CSV | 0.18x (3.2 MB vs 17.9 MB); JSON is 2.5x CSV |
| Parquet full read vs CSV | 6.2x faster; JSON is 5.1x slower than CSV |
| Parquet 3-column read vs CSV | 27x faster |
| Schema preserved on round trip | Parquet: 18/18 columns identical; CSV: 16/18 (the `p_date` timestamp comes back as text) |
| Read one day, partitioned Parquet vs full scan | 7.7x faster (17,268 rows read instead of 129,483) |
| Read one day, raw CSV partition vs all CSVs | 8.5x faster (21.5 MB instead of 160.7 MB) |

The full analysis (trade-offs, why `p_date` is the partition key, and an honest comparison with a single
well-built Parquet file) is in [`docs/format-comparison-and-partitioning.md`](docs/format-comparison-and-partitioning.md).

## 12. Automated tests

```bash
pip install -r requirements-dev.txt
python -m pytest                      # everything; PostgreSQL tests skip if no database is reachable
docker compose up -d postgres         # start the database, then re-run to include the PostgreSQL tests
python -m pytest tests/test_validate.py -k raw     # a subset
```

The suite builds small synthetic datasets with the same schema as the real files, in a
throwaway temp directory, so it never touches `raw/`, `staging/`, `curated/`, your `.env`, or
the real warehouse tables (the PostgreSQL tests work inside a temporary `pipeline_test` schema
that is dropped afterwards). It runs in about 8 seconds and needs no source data.

| File | What it pins down |
| --- | --- |
| `test_config_io.py` | env-driven config, repo-root path resolution, partition helpers, atomic writes, lineage lookup |
| `test_ingest.py` | partitioning by `p_date`, BOM, commas/newlines inside titles, malformed rows, missing sources, rerun safety |
| `test_stage.py` | exact-duplicate removal, tag fan-out collapse, cross-partition ownership, typing, rewatch kept and flagged, `unknown` preserved, category and transcript staging |
| `test_curate.py` | session boundaries (including overlapping views), late-night window, rates, null `late_night_share`, dimensions |
| `test_validate.py` | every validation gate: each check type passes on clean data and fails (or warns) on the matching defect |
| `test_benchmarks.py` | benchmark correctness: format fidelity classification, row-group pruning, and that every partition strategy returns identical rows |
| `test_erd.py` | the ER diagrams (PlantUML and Mermaid) match `sql/schema.sql`: tables, columns, types, NOT NULL, keys, defaults, CHECKs, relationships |
| `test_pipeline_e2e.py` | full run without PostgreSQL, record tracing across layers, identical output on rerun |
| `test_load_postgres.py` | table creation, reload without duplicates, per-date replace, dimension updates, PK/FK enforcement, rollback on failure |

GitHub Actions (`.github/workflows/tests.yml`) runs the same suite on every push against a
PostgreSQL service container.

## 13. Rerun safety

- **Raw layer:** immutable once written; `ingest_raw` skips re-ingesting a partition that
  already exists rather than overwriting it.
- **Curated facts** (`interactions_curated`, `daily_user_features`): loaded via
  delete-then-insert for that partition's date, so retriggering the same `p_date` produces
  identical row counts, not duplicates.
- **Curated dimensions** (`users`, `videos`, `categories`, `video_categories`): loaded via
  `INSERT ... ON CONFLICT DO UPDATE` (upsert) keyed on the primary key, so reruns update
  rather than duplicate.

## 14. Known limitations & assumptions

- **6 category ids have two conflicting English labels in the source lookup file.** Staging
  keeps the first occurrence in file order (deterministic, so reruns are stable) and flags
  those ids with `en_label_ambiguous = True`, so `category_id` is a clean primary key in both
  Parquet and PostgreSQL. First-occurrence is not always correct: id 239 (舞蹈教学, "dance
  teaching") keeps the label "Ace warrior" and id 354 (仿妆, "imitation makeup") keeps
  "action movies". `category_name_cn` is reliable; treat English labels on flagged ids as
  unreliable.
- **The transcript sample is very small** — 10 files against 31,496 distinct videos (0.03%
  coverage) — included to demonstrate multi-format ingestion, not to support any real
  transcript-based analysis.
- **`late_night_share` is null**, by design, for a user-day where `total_watch_seconds = 0`
  (division by zero avoided rather than coerced to 0).
- **The `risk_scores` table exists in the schema as the intended downstream target but is
  not populated** — the risk-scoring method itself is out of scope for this project.
- **13.16% of raw rows are exact duplicates** and are dropped in staging; see the profiling
  report for the per-partition breakdown.

## 15. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `docker compose` warns a variable "is not set. Defaulting to a blank string" | `.env` doesn't exist yet, or you're running the command from a different directory than `docker-compose.yml`. Run `cp .env.example .env` from the repo root and re-run. |
| Postgres container won't start | a blank/default password in `.env` — edit the `change_me_*` values |
| `ingest_raw` task fails immediately, no retries | `SOURCE_DATA_DIR` doesn't exist or the three source files aren't there — see §5 |
| `airflow dags trigger ... --conf {"p_date": ...}` fails for a date | that date has no raw partition and none exists yet; the task lists the available dates in its failure message |
| Task retried and still failed | check the task log in the Airflow UI — validation failures name the specific check that failed |

## 16. Future improvements

- Replace the first-occurrence rule for the 6 ambiguous category labels with a reviewed mapping
- Implement the actual risk-scoring logic that populates `risk_scores`
- Develop real-time streaming ingestion for immediate well-being nudges
