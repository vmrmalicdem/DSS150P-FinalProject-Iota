# Data Contract: `daily_user_features`

**Status:** Implemented in `sql/schema.sql` and produced by `scripts/curate.py`. Verified on Day 3 against the
real sample: 25,109 rows across 7 dates, all validation gates passing. The contract is still open to change
if the team revises a feature definition.

- **Producer:** `scripts/curate.py` (staging to curated), loaded by `scripts/load_postgres.py`.
- **Intended consumers:** the future `risk_scores` computation, dashboards, notebooks (Parquet copy in `curated/daily_user_features/`).
- **Grain:** one row per `(user_id, feature_date)`, only for user-days with at least one event.
- **Primary key:** `(user_id, feature_date)`. `user_id` references `users`.
- **Refresh:** one date partition per pipeline run. Rerunning a date replaces that date's rows.

## Fields

| Field | Type | Required | Nullable | Definition |
|---|---|---|---|---|
| `user_id` | bigint | yes | no | User identifier. |
| `feature_date` | date | yes | no | The `p_date` of the events. |
| `n_events` | integer | yes | no | Deduplicated events that day, at least 1. |
| `total_watch_seconds` | bigint | yes | no | Sum of `watch_time`, rewatch time included. |
| `late_night_events` | integer | yes | no | Events with `p_hour` from 2 to 4 inclusive. |
| `late_night_watch_seconds` | bigint | yes | no | `watch_time` summed over those events. |
| `late_night_share` | double | yes | yes | `late_night_watch_seconds / total_watch_seconds`, range 0 to 1. NULL when total watch time is 0. |
| `n_sessions` | integer | yes | no | Sessions that day, at least 1. Gap threshold 900 seconds. |
| `max_session_seconds` | bigint | yes | no | Longest session, as summed `watch_time`. |
| `avg_session_seconds` | double | yes | no | Mean session length. |
| `hate_events` | integer | yes | no | Events with `hate = true`. |
| `hate_rate` | double | yes | no | `hate_events / n_events`, range 0 to 1. Rare-event rate, not a per-session trend. |
| `rewatch_events` | integer | yes | no | Events with `watch_time > duration`. |
| `rewatch_rate` | double | yes | no | `rewatch_events / n_events`, range 0 to 1. |

## Enforced rules

Database `CHECK` constraints mirror the ranges above. `scripts/validate.py` (`run_curated`) additionally checks primary key uniqueness, `hate_events <= n_events`, `max_session_seconds >= avg_session_seconds`, that `sum(n_events)` equals the curated event count and the staged event count, and that every `user_id` exists in `users`.

## Known limitations

- Sessions are split at date boundaries, so a session running past midnight counts as two.
- `p_hour` is the source's own field and can differ from the UTC+8 hour of `exposed_time` by one hour for about 18% of rows.
- The sample logs few events per user-day (5.2 on average), so session lengths are short and long-session signals are weak.
- The transcript feature is not part of this table. It lives on `videos` (`has_transcript`, `transcript_word_count`).
