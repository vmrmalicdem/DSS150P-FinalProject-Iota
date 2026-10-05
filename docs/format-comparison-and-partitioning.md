# File formats and partitioning

Covers project requirements 4.10 (CSV / JSON / Parquet handling) and 4.11 (data partitioning).
Every number below was measured on this project's own data by two scripts in `scripts/`, and the raw
results are committed under `outputs/benchmarks/` as evidence:

| Script | Question it answers | Output |
| --- | --- | --- |
| `scripts/benchmark_formats.py` | How do CSV, JSON and Parquet compare on size, speed and schema preservation? | `outputs/benchmarks/format_comparison.{json,md}` |
| `scripts/partition_demo.py` | What does reading one partition save compared with scanning everything? | `outputs/benchmarks/partition_demo.{json,md}` |

## 1. Where each format is used in the pipeline

The pipeline does not pick one format; each layer uses the one that suits its job. File counts are from
a full run on the real dataset (7 daily partitions).

| Format | Where | Why this format here |
| --- | --- | --- |
| **CSV** | `data_sources/*.csv` (input); `raw/interactions/p_date=*/interactions.csv` (7 files); `raw/categories/categories_cn_en.csv` | The raw layer stays source-faithful: every value is kept as the original text, with no type guessing. Splitting by date (and stripping the file's byte-order mark) are the only changes. |
| **Plain text** | `raw/transcripts/asr_en/<pid>.txt` (10 files) | Kept exactly as delivered. |
| **JSON** | `staging/_validation/{raw,staged,curated}_<date>.json` (21 files); `staging/_stats/stage_<date>.json` (7 files) | Validation reports and run statistics are small, nested and meant to be read by people and by tools. |
| **JSON Lines** | `raw/_ingestion_log/ingestion_log.jsonl` | An append-only lineage log: one event per line, so a new batch is one appended line and never a rewrite. |
| **Parquet** | `staging/events`, `staging/video_categories` (partitioned by `p_date`); `staging/categories`, `staging/transcripts`; `curated/interactions_curated`, `curated/daily_user_features` (partitioned by `p_date`); `curated/dims/*.parquet` (4 files) | Typed, compressed, columnar: the right format for data that is analysed. |

For scale: the raw interaction CSVs are 154 MB (794,053 rows). The same data is 6.8 MB as staged Parquet and
3.5 MB as curated Parquet (129,483 events). That drop is mostly a **row-count** effect (13% exact duplicates
removed and tag fan-out collapsed into one row per event), not a pure format effect, which is why the
benchmark below rewrites the *same* DataFrame in every format.

## 2. Method

- `benchmark_formats.py` loads two real datasets from the pipeline: **curated** (`interactions_curated`,
  129,483 rows x 18 columns, numbers/booleans/timestamps) and **staged** (staged events,
  129,483 rows x 28 columns, the same plus Chinese text columns).
- It writes each DataFrame as CSV, gzip CSV, JSON (array), JSON Lines, and Parquet (snappy and zstd), then measures
  file size, write time, time to read everything, and time to read 3 columns (`user_id`, `p_date`, `watch_time`).
- **Fidelity:** each file is read back with default settings and compared with the original, column by column:
  same dtype and identical values, or not. This measures whether the format *preserves the schema*.
- Each time is the median of 5 runs on a warm file cache. JSON is written with `force_ascii=False` (UTF-8, like
  CSV) and read with `convert_dates=False`; see the gotcha in section 4.
- **Machine:** Linux-6.18.44-fc-v64-x86_64-with-glibc2.39, 1 CPU, Python 3.12.3, pandas 2.1.4, pyarrow 19.0.0.
  Timings depend on the machine, so compare the *ratios*; re-run the scripts on your own machine for your own numbers.

## 3. Format comparison results

### `curated` dataset: 129,483 rows x 18 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 17.9 | 1.00x | 0.500 | 0.142 | 0.091 | 1.0x | 1.0x | 16/18 |
| CSV (gzip) | 3.4 | 0.19x | 1.844 | 0.195 | 0.137 | 0.7x | 0.7x | 16/18 |
| JSON (array) | 45.5 | 2.54x | 0.277 | 0.726 | 0.738 | 0.2x | 0.1x | 16/18 |
| JSON Lines | 45.5 | 2.54x | 0.507 | 0.837 | 0.833 | 0.2x | 0.1x | 16/18 |
| Parquet (snappy) | 3.2 | 0.18x | 0.060 | 0.023 | 0.003 | 6.2x | 27.0x | 18/18 |
| Parquet (zstd) | 2.7 | 0.15x | 0.065 | 0.021 | 0.004 | 6.6x | 25.9x | 18/18 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical

### `staged` dataset: 129,483 rows x 28 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 33.7 | 1.00x | 0.881 | 0.359 | 0.212 | 1.0x | 1.0x | 26/28 |
| CSV (gzip) | 8.3 | 0.25x | 2.497 | 0.465 | 0.328 | 0.8x | 0.6x | 26/28 |
| JSON (array) | 78.1 | 2.32x | 0.592 | 1.605 | 1.579 | 0.2x | 0.1x | 25/28 |
| JSON Lines | 78.1 | 2.32x | 1.155 | 1.894 | 1.877 | 0.2x | 0.1x | 25/28 |
| Parquet (snappy) | 6.1 | 0.18x | 0.161 | 0.070 | 0.004 | 5.1x | 56.1x | 28/28 |
| Parquet (zstd) | 5.0 | 0.15x | 0.166 | 0.071 | 0.004 | 5.1x | 54.0x | 28/28 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `duration` (max abs diff 1.14e-13), `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `duration` (max abs diff 1.14e-13), `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical

## 4. What the results mean

**Size.** Parquet (snappy) is 0.18x the size of CSV on the curated data (3.2 MB vs 17.9 MB) and
0.18x on the text-heavy staged data. zstd shrinks it further (2.7 MB). JSON is the largest, at
2.5x CSV, because every record repeats every field name. Compressing the CSV with gzip closes
almost all of the size gap (3.4 MB), but see the next point.

**Read speed.** Parquet reads the whole table 6.2x faster than CSV, and JSON is
5.1x *slower* than CSV. Gzip CSV also reads more slowly than plain CSV (about
0.7x the speed), so compression buys size but not speed.

**Column pruning.** Reading only 3 columns is 27x faster from Parquet than from CSV on the curated data
and 56x on the staged data, which has more columns (28 vs 18). CSV with `usecols` still has to parse every
line, and JSON has no pruning at all (its 3-column read takes as long as reading everything). Columnar storage is the main reason Parquet
suits analytics queries that touch a few columns.

**Write speed.** Parquet writes 8.4x faster than CSV. Two results are less obvious: JSON (array) writes
*faster* than CSV (0.28s vs 0.50s), so JSON's costs are size and reading, not writing; and gzip CSV is the slowest to write
(1.84s, 3.7x plain CSV) because of compression.

**Schema preservation.** Parquet returned every column with the identical dtype and values. CSV and JSON carry no schema, so a reader must
guess, and on this data both lost the type of `p_date`: it was a timestamp and came back as text from CSV and as an integer from JSON.
Floats also changed slightly: `watch_ratio` differs by up to 7e-15 after a CSV round trip and by up to
5e-11 after JSON (pandas writes JSON floats with 10 decimal digits by default). These differences are tiny, but they
are not zero, so an exact comparison or join on those floats could be affected. All of this can be fixed on the reading side with explicit dtype hints; the point is
that CSV and JSON *need* those hints and Parquet does not.

**A pandas gotcha found while building this.** By default `pandas.read_json` guesses dates from column *names*: a column called `exposed_time`
holding Unix-second integers is silently converted to `datetime64`. The benchmark passes `convert_dates=False` so the comparison measures the format and
not this behaviour, and `tests/test_benchmarks.py` pins it.

### Trade-offs

| | CSV | JSON / JSON Lines | Parquet |
| --- | --- | --- | --- |
| Human-readable, easy to inspect | Yes | Yes | No (needs a tool or pandas) |
| Preserves types and schema | No | Partly (numbers, booleans; not timestamps) | Yes |
| Size | Medium | Largest | Smallest |
| Reads a subset of columns cheaply | No | No | Yes |
| Nested / semi-structured data | No | Yes | Yes, but heavier |
| Append one record without rewriting | Yes | **JSON Lines: yes**; JSON array: no | No (write whole files, which suits partitions) |
| Interoperability | Universal | Universal | Needs a Parquet-aware tool |

**Decision.** Raw layer: CSV, because the requirement is to keep source data close to its original form and CSV is the source format. Staging and
curated layers: Parquet, because they are consumed analytically and need preserved types, small files and column pruning. Reports and logs: JSON and JSON Lines,
because they are small, nested and human-read, and the log is append-only.

## 5. Partitioning

### Strategy

Every fact table is partitioned by **`p_date`** in a Hive-style directory layout, one file per day:

```
raw/interactions/p_date=20220919/interactions.csv
staging/events/p_date=20220919/events.parquet
curated/interactions_curated/p_date=20220919/data.parquet
curated/daily_user_features/p_date=20220919/data.parquet
```

Dimension tables (`users`, `videos`, `categories`, `video_categories`) are small and are rebuilt whole on each run, so they are not partitioned.

### Why `p_date` is the right key

- **It matches how the data arrives and how the pipeline runs.** The source is a daily log. The Airflow DAG's logical date *is* the partition (`p_date = YYYYMMDD`),
  `run_pipeline.py --date` processes one partition, and the PostgreSQL load replaces one date at a time.
- **It matches how the data product is defined.** `daily_user_features` has one row per user per day, computed from that day's events only.
- **It makes reruns safe and cheap.** Rerunning a day rewrites only that day's files, and each write is atomic (temp file then rename), so a failed run cannot leave another
  day half-written.
- **Partition sizes are balanced enough.** The largest partition (20220917, 23,439 events) is 1.87x the smallest (20220922, 12,505). The decline across the week is
  already present in the raw row counts (139,102 rows on 2022-09-16 down to 79,134 on 2022-09-22, from the ingestion log), so it comes from the source sample and not from the pipeline.

Alternatives considered:

| Candidate key | Why not |
| --- | --- |
| `user_id` | 6,654 distinct users would mean thousands of tiny files, and nothing in the pipeline reads by user first. |
| `category_id` | After tag collapse an event belongs to many categories (631 distinct ids), so it is not a property of the event; partitioning on it would duplicate rows. |
| `p_hour` | 22 hours x 7 days = 154 partitions averaging about 840 events each; file overhead would outweigh the data, and no consumer asks for an hour first. |

### Demonstration: reading one partition instead of scanning everything

`partition_demo.py` asks for one day (`p_date=20220919`) four ways. Every strategy must return exactly the same rows or the script fails, so the timings compare like with like.

#### Partition sizes (`interactions_curated`, partition key `p_date`)

| p_date | Rows | Share of rows | Parquet size |
| --- | ---: | ---: | ---: |
| 20220916 | 22,533 | 17.4% | 598 KB |
| 20220917 | 23,439 | 18.1% | 625 KB |
| 20220918 | 22,130 | 17.1% | 598 KB |
| 20220919 | 17,268 | 13.3% | 472 KB |
| 20220920 | 17,739 | 13.7% | 479 KB |
| 20220921 | 13,869 | 10.7% | 389 KB |
| 20220922 | 12,505 | 9.7% | 357 KB |

Largest / smallest partition: 1.87x.

#### Reading one day (`p_date=20220919`), curated Parquet

| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Partition read | 0.005 | 7.7x | 1 | 17,268 | 17,268 | 464 KB |
| Full scan + filter | 0.038 | 1.0x | 7 | 129,483 | 17,268 | 3.46 MB |
| Single file, default row groups | 0.016 | 2.3x | 1 | 129,483 | 17,268 | 3.15 MB |
| Single file, one row group per day | 0.005 | 7.1x | 1 | 17,268 | 17,268 | 464 KB |

#### Reading one day (`p_date=20220919`), raw CSV layer

| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw CSV: one partition | 0.262 | 8.5x | 1 | 106,439 | 106,439 | 21.53 MB |
| Raw CSV: read all, filter | 2.223 | 1.0x | 7 | 794,053 | 106,439 | 160.72 MB |

Bytes read: compressed column data for Parquet, file size for CSV.
All strategies returned identical rows (checked before timing was reported).

**Reading the results**

- **Selected-partition access works.** Reading one partition took 5 ms against 38 ms for scanning everything (7.7x), touching
  1 file instead of 7 and 17,268 rows instead of 129,483 (464 KB instead of 3.46 MB). With 7 partitions
  the ideal saving is about 7x, and the measured speedup is close to it.
- **The raw CSV layer benefits the most in absolute terms:** 0.26s vs 2.22s (8.5x), reading 21.5 MB instead of
  160.7 MB. CSV has no statistics or row groups, so directory partitioning is the *only* way to avoid reading the other days.
- **A single Parquet file with a pushed-down filter is not enough by default.** With default row groups the whole file is one group, so all 129,483 rows are
  read and only 2.3x is saved.
- **An honest caveat: a carefully built single file matches directory partitioning for reads.** Written with one row group per day, a single file reads
  17,268 rows and runs in 5 ms (7.1x), essentially the same as the partition read. So read speed alone does not
  justify directories. What does is the **write and operations side**: rewriting or deleting one day replaces one file instead of rewriting the whole table, a
  failed run cannot touch other days, the raw CSV layer has no alternative, and the layout mirrors the per-date Airflow runs and the per-date PostgreSQL load.

### Limits worth knowing

- **Partitions are not fully independent.** Staging assigns an event to the earliest partition that contains it, so staging a day reads the *earlier* raw partitions' event keys. That is why the DAG runs
  one date at a time (`max_active_runs=1`) and why a late-arriving earlier day would require restaging the later days.
- **The data is small.** The whole curated table is 3.5 MB and fits in memory, so absolute times are milliseconds. The measured ratios hold at 7 partitions; the *reasoning* that a full scan grows with
  every day kept while a partition read stays constant is why this matters as history accumulates, but that growth was not measured here.
- Timings come from one machine (1 CPU) with a warm file cache.

### Selecting a partition in code

```python
import pandas as pd
day = pd.read_parquet("curated/interactions_curated/p_date=20220919/data.parquet")   # one file, one day
```

```bash
python scripts/run_pipeline.py --date 20220919     # process just that partition end to end
```

## 6. Reproduce

```bash
python scripts/run_pipeline.py --all --skip-load          # builds raw, staging and curated first
python scripts/benchmark_formats.py --repeats 5           # -> outputs/benchmarks/format_comparison.{json,md}
python scripts/partition_demo.py --date 20220919 --repeats 15   # -> outputs/benchmarks/partition_demo.{json,md}
```

Both scripts exit with a clear message if the pipeline has not been run yet. Results are written to `OUTPUTS_DIR` (default `./outputs`).
