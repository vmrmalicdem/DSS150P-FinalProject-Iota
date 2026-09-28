# Transformation Specification (Staging → Curated)

**Status:** Updated Day 2. Person A's raw ingestion now exists and has been run against the
real source files, so §4 below is updated from "proposed" to confirmed real column names -
this still describes intended staging/curated logic only. No staging or curated
transformation **code** has been written; that remains Day 3 scope.

## 1. Deduplication key

Deduplication is keyed on:

```
(user_id, pid, exposed_time)
```

This recovers the true interaction-event grain from the raw interaction file, where each
event is legitimately duplicated once per tag attached to its video (tag-level fan-out).
Rows that are exact duplicates of another row (identical across all columns) are dropped
outright before this keying is applied.

**Unresolved as of Day 1:** the exact deduplication *procedure* (e.g., which duplicate row
is kept when multiple rows share the key but differ only in tag-related columns) is not yet
decided. This will be finalized once Person A's raw output exists and its actual column
layout can be inspected.

## 2. Rewatch-inflated `watch_time`

Rows where `watch_time` exceeds `duration` (and especially where it exceeds `duration` by
2x or more) are **retained**, not discarded or capped. This pattern is treated as a genuine
behavioral signal (repeated/looped viewing) rather than a data error, since discarding it
would remove exactly the compulsive-usage signal the project is meant to detect.

These rows are flagged with a derived boolean feature (working name: `is_rewatch_flagged`,
TBD in the eventual curated schema) rather than silently left indistinguishable from
single-pass views. The exact threshold for flagging (any `watch_time > duration`, or only
`watch_time > 2 * duration`) is **not yet decided** - this is an open decision for Day 3
when the curated feature transformation is implemented.

## 3. `unknown` categorical values

Fields carrying an explicit `unknown` value (e.g., community type, city level, as noted in
prior profiling discussion) are treated as their **own valid category**, not imputed, not
dropped, and not merged into another category. Any validation check on accepted values for
these fields must include `unknown` in the accepted set.

## 4. Raw interaction table - confirmed real column list (Day 2)

Confirmed by running `scripts/ingest.py` against the real `interaction_sampled.csv`
(794,053 data rows, matches earlier profiling exactly). This is the actual header row, not
a proposal:

```
user_id, pid, author_id, category_id, category_level, parent_id, root_id, exposed_time,
author_fans_count, watch_time, duration, cvm_like, click, comment, follow, collect,
forward, hate, tag_name, title, p_hour, p_date, gender, age, mod_price, fre_city,
fre_community_type, fre_city_level
```

Notes on fields relevant to staging/curated logic:

| Field | Type (observed) | Notes |
|---|---|---|
| `user_id` | integer | part of dedup key |
| `pid` | integer | video id; part of dedup key |
| `exposed_time` | integer (unix timestamp) | part of dedup key |
| `watch_time` | integer (seconds) | retained even when > duration; see §2 |
| `duration` | float (seconds) | video duration |
| `hate` | boolean (`True`/`False` strings) | sparse - 431 of 794,053 rows (0.05%); treat as rare-event rate downstream, not per-session trend |
| `p_date` | integer, `YYYYMMDD` | 7 distinct values, 20220916–20220922; used as the raw-layer partition key |
| `p_hour` | integer | present per row |
| `gender`, `age`, `mod_price`, `fre_city`, `fre_community_type`, `fre_city_level` | mixed | `unknown` retained per §3 where present |
| `category_id`, `category_level`, `parent_id`, `root_id` | integer | join against `categories_cn_en.csv` |
| `tag_name`, `title` | text (Chinese) | **`title` can contain commas and embedded newlines inside quoted CSV values** - confirmed in 87 of 794,053 rows for embedded newlines. Any staging code must use a real CSV parser (e.g. Python's `csv` module or pandas), never naive comma/line splitting, or these rows will be silently corrupted. |
| `cvm_like`, `click`, `comment`, `follow`, `collect`, `forward` | boolean | other interaction flags, not yet assigned a specific curated use beyond what's noted in `data-contract-daily-user-features.md` |

`is_rewatch_flagged` is not a raw column - it remains a **derived** field planned for the
staging/curated step (§2), not present in the source data.

## 5. Decisions settled on Day 3 (previously TBD)

Each decision was made against the real data. The evidence is noted so the team can defend it.

| Decision | Rule | Evidence |
|---|---|---|
| Event grain | One event = `(user_id, pid, exposed_time)`. Fan-out rows are categories x tags, not tags alone. | 794,053 rows collapse to 129,483 events (matches the profiling report). |
| Exact duplicates | Dropped first. | 104,519 exact duplicate rows in the sample. |
| Event tie-break | Within an event, keep the smallest `p_hour`, then smallest `title`. | Only 3 events disagree on `p_hour` and 15 on `title`. |
| Events in two partitions | An event belongs to the earliest date partition it appears in. | 3 events appear in two partitions. Without this rule the per-partition counts sum to 129,486, and the event primary key would fail on load. |
| Rewatch flag | `is_rewatch_flagged = watch_time > duration`. `watch_ratio` is kept so any other threshold (e.g. 2x) can be applied later. | 29% of events exceed 1x and 5.7% exceed 2x. Nothing is capped or dropped. |
| Late-night window | `p_hour` 2 to 4 inclusive, configurable (`LATE_NIGHT_START_HOUR`, `LATE_NIGHT_END_HOUR`). | Taken from the project brief. Hours 0 and 1 do not exist in this sample. |
| `p_hour` source | Use `p_hour` as provided. | It equals the UTC+8 hour of `exposed_time` for 82% of rows and is one hour later for the other 18%, so the late-night boundary is fuzzy by up to an hour. Report as a limitation. |
| Session | Consecutive events of one user within one date partition, where the gap between the end of the previous view and the next exposure is at most 900 seconds (`SESSION_GAP_SECONDS`). Session length = sum of `watch_time`. | Median gap between logged events is about 8 minutes. A 300s gap fragmented most usage into single-event sessions. Sessions are split at the date boundary, which is a known limitation. |
| Sparse users | Flag `is_sparse_history` when a user has fewer than 5 events (`MIN_USER_EVENTS`). Flagged, not excluded. | 1,752 of 6,654 users (26%) at event grain. The profiling report's 217 users counted rows, not events. |
| Category lookup | Keep the first row per `category_id`, flag `en_label_ambiguous`. English labels are trimmed. | 6 category ids appear twice with conflicting English labels (233, 239, 338, 350, 354, 368). Chinese names agree. |
| Transcript feature | Lives on `videos`: `has_transcript`, `transcript_word_count` (whitespace word count). Filename number is treated as `pid`. | Only 9 of 31,496 videos have a transcript file. Coverage is intentionally tiny (locked scope). |

## 6. Known limits of the data (state these in the report)

- **Long unbroken sessions are barely observable.** With a 900s gap the longest session in the sample is 1,323 seconds and only a handful of user-days pass 10 minutes. Absolute thresholds such as 30 minutes match nothing, so risk logic should use relative thresholds (for example the top decile).
- **`hate` is very rare:** 431 flagged rows, which is 87 events across 7 days. Use it as a per-user-per-day rate.
- **Only 7 days:** no claim about long-term trends is supportable.
- **Sample, not the full release:** 6,654 of 10,000 users.

## 7. Out of scope so far

- The `risk_scores` table exists but nothing loads into it. The scoring method is not designed.
- Format comparison (CSV vs JSON vs Parquet benchmarks) is not done yet. Staging and curated data are written as Parquet.
