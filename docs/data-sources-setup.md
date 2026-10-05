# Local Source Data Setup

The pipeline's source files are **not committed to this repository**. The
interaction file alone is ~160MB, over GitHub's 100MB per-file limit, and raw
source data doesn't belong in git regardless of size. Each team member needs
their own local copy before running `scripts/ingest.py`.

## What you need

Per `docs/transformation-spec.md` and earlier project planning, place these
under a local `data/` folder at the repo root (already gitignored):

```
data/
├── interaction_sampled.csv
├── categories_cn_en.csv
└── asr_en/
    ├── 1.txt
    ├── 2.txt
    └── ... (10 files total in the current sample)
```

- `interaction_sampled.csv` - the behavior/attribute table already profiled in
  earlier project planning (794,053 rows, confirmed again when this ingestion
  script was built and tested).
- `categories_cn_en.csv` - the category lookup table.
- `asr_en/*.txt` - a small sample of English ASR transcript files. Locked
  scope: only file-existence and word/character count are ever computed from
  these. English was chosen specifically to avoid word-tokenization ambiguity
  that Chinese (`asr_zn`) text would introduce.

Source: [tsinghua-fib-lab/ShortVideo_dataset](https://github.com/tsinghua-fib-lab/ShortVideo_dataset).
The tiny sample (no credentials required) is linked from that repo's README.

## Running ingestion

```bash
cp .env.example .env   # if you haven't already
python scripts/ingest.py
```

This reads from `SOURCE_DATA_DIR` (default `./data`) and writes a
partitioned raw layer into `RAW_DATA_DIR` (default `./raw`, also gitignored).
Ingestion metadata (batch id, timestamp, row/file counts, any errors) is
logged to `raw/_ingestion_log/ingestion_log.jsonl`.

Confirmed by test run: 794,053 interaction rows partitioned cleanly across 7
`p_date=` folders (2022-09-16 through 2022-09-22), 826 category rows copied,
10 transcript files copied, zero malformed rows. Rerunning the script
overwrites each partition file rather than duplicating rows - this is
file-level overwrite behavior for Day 2 only, not the UPSERT-based rerun
safety planned for the Postgres load step later.

## Running the full pipeline (Day 3)

Install dependencies once, and start PostgreSQL (`docker compose up -d postgres`):

```powershell
py -m pip install -r requirements.txt
copy .env.example .env      # keep POSTGRES_HOST=localhost when running scripts on your own machine
```

Run without a database (validate, stage, curate only):

```powershell
py scripts\run_pipeline.py --all --skip-load
```

Run everything including the PostgreSQL load, for one date or all seven:

```powershell
py scripts\run_pipeline.py --date 20220918
py scripts\run_pipeline.py --all
```

Outputs: `staging/` and `curated/` (Parquet, partitioned by `p_date`), validation reports in
`staging/_validation/`, and the warehouse tables described in `docs/erd.md`. Example queries are in
`sql/queries.sql`. A failed validation gate stops the run with a nonzero exit code and names the check.
The Airflow DAG (`dags/short_video_risk_dag.py`) calls the same functions, one date partition per run.

## Running the pipeline under Airflow in Docker (Day 4)

Prerequisites: Docker with Compose v2, and the source files in `data/` (see above).

```bash
cp .env.example .env        # then set the three change_me_* passwords; on Linux set AIRFLOW_UID=$(id -u)
docker compose up -d --build
docker compose ps           # wait until airflow-webserver and airflow-scheduler are healthy
```

`airflow-init` runs once (migrates Airflow's metadata DB, creates the admin user, fixes folder
permissions) and then exits; that is expected. The UI is at http://localhost:8080 (login from
`AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` in `.env`).

Run the DAG `short_video_risk_pipeline`:

```bash
# one partition
docker compose exec airflow-scheduler airflow dags unpause short_video_risk_pipeline
docker compose exec airflow-scheduler airflow dags trigger short_video_risk_pipeline --conf '{"p_date": "20220918"}'

# or unpause it and let catchup replay 2022-09-16 .. 2022-09-22, one run per day (max_active_runs=1)
```

Check results:

```bash
docker compose exec airflow-scheduler airflow dags list-runs -d short_video_risk_pipeline
docker compose exec postgres psql -U pipeline_user -d shortvideo_risk -c "SELECT p_date, count(*) FROM interactions_curated GROUP BY 1 ORDER BY 1;"
```

Demonstrate rerun safety: trigger the same `p_date` twice; the row counts above do not change.
Demonstrate failure diagnosis: temporarily rename a column in `raw/interactions/p_date=.../interactions.csv`,
trigger that date, and open the `validate_raw` task log in the UI: it fails immediately (no retries) and names the check.

Without Airflow, the same stage functions run through the CLI container:

```bash
docker compose --profile cli run --rm pipeline python scripts/run_pipeline.py --all
```

Stop with `docker compose down`; add `-v` to also delete the warehouse and Airflow databases.

Notes
- The DAG reads `POSTGRES_HOST=postgres` from Compose; do not change it to `localhost` inside containers.
- Only `raw/`, `staging/`, `curated/`, `logs/` and `data/` hold data, and all are gitignored.
- Database passwords in `.env.example` are placeholders for local development only.
