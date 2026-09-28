# Local Source Data Setup

The pipeline's source files are **not committed to this repository**. The
interaction file alone is ~160MB, over GitHub's 100MB per-file limit, and raw
source data doesn't belong in git regardless of size. Each team member needs
their own local copy before running `scripts/ingest.py`.

## What you need

Per `docs/transformation-spec.md` and earlier project planning, place these
under a local `data_sources/` folder at the repo root (already gitignored):

```
data_sources/
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

This reads from `SOURCE_DATA_DIR` (default `./data_sources`) and writes a
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
