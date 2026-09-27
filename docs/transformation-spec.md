# Transformation Specification (Staging → Curated)

**Status:** Updated Day 2. Person A's raw ingestion now exists and has been run against the
real source files, so §4 below is updated from "proposed" to confirmed real column names —
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
`watch_time > 2 * duration`) is **not yet decided** — this is an open decision for Day 3
when the curated feature transformation is implemented.

## 3. `unknown` categorical values

Fields carrying an explicit `unknown` value (e.g., community type, city level, as noted in
prior profiling discussion) are treated as their **own valid category**, not imputed, not
dropped, and not merged into another category. Any validation check on accepted values for
these fields must include `unknown` in the accepted set.

## 4. Raw interaction table — confirmed real column list (Day 2)

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
| `hate` | boolean (`True`/`False` strings) | sparse — 431 of 794,053 rows (0.05%); treat as rare-event rate downstream, not per-session trend |
| `p_date` | integer, `YYYYMMDD` | 7 distinct values, 20220916–20220922; used as the raw-layer partition key |
| `p_hour` | integer | present per row |
| `gender`, `age`, `mod_price`, `fre_city`, `fre_community_type`, `fre_city_level` | mixed | `unknown` retained per §3 where present |
| `category_id`, `category_level`, `parent_id`, `root_id` | integer | join against `categories_cn_en.csv` |
| `tag_name`, `title` | text (Chinese) | **`title` can contain commas and embedded newlines inside quoted CSV values** — confirmed in 87 of 794,053 rows for embedded newlines. Any staging code must use a real CSV parser (e.g. Python's `csv` module or pandas), never naive comma/line splitting, or these rows will be silently corrupted. |
| `cvm_like`, `click`, `comment`, `follow`, `collect`, `forward` | boolean | other interaction flags, not yet assigned a specific curated use beyond what's noted in `data-contract-daily-user-features.md` |

`is_rewatch_flagged` is not a raw column — it remains a **derived** field planned for the
staging/curated step (§2), not present in the source data.

## 5. Still unresolved / TBD (Day 3 scope)

- Final dedup tie-breaking procedure when rows share the `(user_id, pid, exposed_time)` key
  but differ only in tag-related columns.
- Rewatch-flag threshold (`watch_time > duration` vs. `watch_time > 2 * duration`).
- Late-night window boundaries and session definition (see also
  `data-contract-daily-user-features.md`).

## 6. Explicitly out of scope for Day 2

- No staging code, no curated feature code, no validation-check code exist yet. This remains
  a specification, now updated with confirmed real column data. Staging code is Day 3 scope.
- The `categories_cn_en.csv` join and the transcript word-count feature are not yet
  implemented in code — only ingested as raw files (see `data-sources-setup.md`).
