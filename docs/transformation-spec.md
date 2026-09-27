# Transformation Specification (Staging → Curated)

**Status:** Day 1 specification only. No transformation code exists yet — it depends on
Person A's ingestion/raw layer, which is not built as of Day 1. This document exists so
Person A's ingestion output has a target shape to match, and so Person C's ERD/contract
can be checked against it.

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

## 4. Expected staging output shape

This section is necessarily incomplete as of Day 1: no raw data has been ingested yet in
this repository, and no source file is present to inspect directly. The fields listed below
reflect the columns discussed in prior project planning (user, video, interaction, and
attribute fields), **not a confirmed schema read from an actual file**. Person A's ingestion
step should be treated as the authority on the real column names, types, and completeness
once it exists.

| Field (proposed) | Type (proposed) | Notes |
|---|---|---|
| `user_id` | integer | part of dedup key |
| `pid` (video id) | integer | part of dedup key |
| `exposed_time` | timestamp/int | part of dedup key |
| `watch_time` | numeric | retained even when > duration; see §2 |
| `duration` | numeric | video duration |
| `is_rewatch_flagged` | boolean | derived; threshold TBD |
| `hate` | boolean | sparse; treat as rare-event rate downstream, not per-session trend |
| `p_date`, `p_hour` | date/int | hour range and date coverage depend on the actual raw file; not assumed here |
| gender, age, city/community/city-level fields | mixed | `unknown` retained per §3 |
| category/tag fields | string/id | subject to the category lookup table, not yet ingested |

**Explicitly unresolved / TBD:**
- Full, confirmed column list and types (depends on Person A's actual raw ingestion output).
- Final dedup tie-breaking procedure.
- Rewatch-flag threshold.
- Whether `hate` and other interaction flags need any additional handling beyond what's
  noted here, once real data volumes are visible in this repository's raw layer.

## 5. Explicitly out of scope for Day 1

- No staging code, no curated feature code, no validation checks are implemented as part of
  this document. This is a specification only.
- No claim is made that any of the figures referenced in earlier project discussion (row
  counts, duplicate percentages, etc.) have been verified against data in this repository —
  no source data is present here as of Day 1.
