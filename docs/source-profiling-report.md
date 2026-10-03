# Source Profiling Report

Profiled directly against the files uploaded to `data_sources/`:
`interaction_sampled.csv`, `categories_cn_en.csv`, and `asr_en/*.txt`. All figures below
were produced by reading these exact files with pandas / the `csv` module and, where noted,
by running the actual pipeline (`scripts/run_pipeline.py --all --skip-load`) end to end.
Full pipeline run against this file: 7/7 partitions succeeded, 0 validation errors, 1
pre-existing warning (duplicate category IDs, documented below), ~35 seconds total.

--- 

## 1. `interaction_sampled.csv`

**Provider / origin:** short-video interaction sample (Kuaishou-style schema), CSV, single
file. Read with `encoding="utf-8-sig"` — the file starts with a UTF-8 BOM.

| Metric | Value |
| --- | --- |
| Rows | 794,053 |
| Columns | 28 |
| File size | ~160 MB |
| p_date range | 2022-09-16 to 2022-09-22 (7 calendar days) |
| p_hour range | 2–23 (no rows for hours 0–1) |

### 1.1 Column inventory

Every column read as `dtype=str` at the source (no column contains an empty-string null in
794,053 rows — nullability is 0% for all 28 fields). Column-by-column:

| Column | Distinct values | Notes |
| --- | --- | --- |
| `user_id` | 6,654 | integer-like string |
| `pid` (video id) | 31,496 | integer-like string |
| `author_id` | 23,242 | integer-like string |
| `category_id` | 631 | all 631 values found in `categories_cn_en.csv` — 0 orphans |
| `category_level` | 3 | `{1: 351925, 2: 258156, 3: 183972}` |
| `parent_id` | 110 | |
| `root_id` | 38 | |
| `exposed_time` | 101,847 | Unix seconds, range 1663263896–1663861929 (spans p_date range exactly) |
| `author_fans_count` | 75,448 | range 1–215,859,160 |
| `watch_time` | 587 | seconds, range 0–922 |
| `duration` | 14,519 | seconds, range 3.958–1734.92 |
| `cvm_like`,`click`,`comment`,`follow`,`collect`,`forward`,`hate` | 2 each | string `"True"`/`"False"`, not native booleans |
| `tag_name` | 26,355 | Chinese text; **one row per tag** — see fan-out, §1.3 |
| `title` | 30,154 | Chinese text; **87 rows have an embedded newline inside the quoted field** — confirmed by parsing with `csv.DictReader`, not naive line-splitting |
| `p_hour` | 22 | 2–23 |
| `p_date` | 7 | 20220916–20220922 |
| `gender` | 2 | `{M: 497010, F: 297043}` |
| `age` | 60 | range 20–79 |
| `mod_price` | 271 | range 399–17,799 |
| `fre_city` | 365 | Chinese city names |
| `fre_community_type` | 4 | `{乡村: 292848, unknown: 256974, 城区: 155864, 镇区: 88367}` — 32.4% are the literal string `"unknown"`, not a missing value |
| `fre_city_level` | 7 | includes `unknown` (7 rows only) alongside 6 tier labels |

### 1.2 Duplicates

- **Exact full-row duplicates: 104,519 rows (13.16% of the file).** These are true byte-for-byte
  duplicate rows, not fan-out. The pipeline drops these in the staging layer and logs the
  count per partition (`exact_duplicate_rows_dropped`, 11.4–14.9% per day).
- **Event fan-out is separate from duplication.** A single (user, video, exposure) can
  legitimately appear once per tag the video carries.

### 1.3 One logical event vs. one CSV row

The file is tag-exploded: each row is one `(user_id, pid, exposed_time, tag_name)`
combination, not one event. Grouping by `(user_id, pid, exposed_time)`:

- **129,483 unique events** across the whole file, vs. **794,053 raw rows** — each event
  appears a median of ~2–3 times, with a long tail up to 675 rows for a single event (a
  heavily multi-tagged video). This is why the curated `interactions_curated` table
  (129,483 rows) is much smaller than the raw row count, and why the pipeline builds a
  separate `video_categories` bridge table instead of carrying `tag_name`/`category_id`
  inline on the event.

### 1.4 Cross-partition events

A small number of events have `exposed_time` values that place them one UTC day before
their stated `p_date`. Staging assigns each event to the partition implied by
`exposed_time`, not the file's own `p_date` label, and logs how many rows this affects per
partition (`events_owned_by_earlier_partition`).

### 1.5 Data quality issues found

| Issue | Scope | How the pipeline handles it |
| --- | --- | --- |
| 13.16% exact duplicate rows | whole file | Dropped in staging; count logged per partition |
| Tag fan-out (rows ≠ events) | whole file | Collapsed to one row per event in `interactions_curated`; tags become `video_categories` rows |
| `watch_time > duration` ("rewatch") | up to ~28% of events in some partitions (e.g. 3,465/12,505 on 09-22) | Retained, not dropped or capped; flagged via `is_rewatch_flagged`, ratio kept in `watch_ratio` |
| `fre_community_type` / `fre_city_level` literal `"unknown"` | 32.4% / 0.1% of rows | Preserved as-is (not treated as null); validated as an accepted value, not a missing value |
| Embedded newlines inside `title` | 87 rows | Requires a real CSV parser; naive line-splitting would corrupt these rows |
| No rows for `p_hour` 0–1 | whole file | Confirmed absent, not a bug in ingestion |

---

## 2. `categories_cn_en.csv`

| Metric | Value |
| --- | --- |
| Rows | 826 |
| Columns | 6: `category_level, category_id, category_name_cn, parent_id, root_id, category_name_en` |
| File size | ~31 KB |

- **Referential integrity: clean.** All 631 distinct `category_id` values used in
  `interaction_sampled.csv` are present in this file — 0 orphaned category references.
- **Duplicate `category_id` values: 6** (`233, 239, 338, 350, 354, 368`) — each appears twice
  with a different `category_name_en` label. The pipeline keeps both rows in staging, flags
  each affected id with `en_label_ambiguous = True` in the curated `categories` dimension,
  and surfaces the conflict as a validation **warning** (not a failure) per raw partition.
- **4 rows have a blank `category_name_en`** after stripping whitespace.
- **Every `category_name_en` value has a leading space** in the raw file (e.g. `" beauty"`,
  `" folk dance"`). Confirmed formatting artifact of the source file, not a parsing bug.
  Staging strips both `category_name_cn` and `category_name_en`.
- `category_level` distribution: `{1: 36, 2: 307, 3: 483}` — a 3-level taxonomy.

---

## 3. `asr_en/*.txt` (video transcripts)

| Metric | Value |
| --- | --- |
| Files | 10 (`1.txt`–`10.txt`) |
| File size range | 102–578 bytes |
| Encoding | plain UTF-8 English text (already translated / summarized, not raw ASR output) |

- Filenames are the video's `pid`. 9 of the 10 filenames (`1,2,3,4,5,6,8,9,10`) match an
  actual `pid` present in `interaction_sampled.csv`; `7.txt` does not correspond to any pid
  in the interaction file.
- This is a tiny, non-representative sample: 10 transcripts against 31,496 distinct videos
  (0.03% coverage). The curated `videos` dimension records `has_transcript` and
  `transcript_word_count` for the 9 that match; the other 31,487 videos have
  `has_transcript = False`.
- Content check: transcripts are short marketing/vlog-style narration (skincare, winter
  jackets, hair dye, a writing guide, a Chinese liquor ad, a "don't touch my peach tree"
  rant, a mock-robbery bit). No embedded delimiters, HTML, or control characters found —
  safe to read as plain text with no special parsing.

---

## 4. Summary of source limitations and risks

- **Tag fan-out means "row count" is not "event count."** Any headline number
  (10,000+ minimum row requirement, etc.) should be reported at both the raw-row level
  (794,053) and the deduplicated-event level (129,483) to avoid overstating volume.
- **13% exact duplication** is high enough that skipping the staging dedup step would
  materially inflate every downstream count and feature.
- **`unknown` is a real category, not a null**, for two location fields — must not be
  coerced to NaN/None anywhere in transformation or the accepted-values checks would need
  to be rewritten.
- **The transcript sample (10 files) is too small to support any transcript-based feature
  or analysis with statistical confidence** — it exists to demonstrate the CSV/JSON/text
  multi-format ingestion requirement, not to drive real content-based insights.
- **The 6 duplicate category IDs with conflicting English labels** are a genuine upstream
  data-quality defect in `categories_cn_en.csv`, not an ingestion bug; documented and
  flagged rather than silently resolved by picking one label.