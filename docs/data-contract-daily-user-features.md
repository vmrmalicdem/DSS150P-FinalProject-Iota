# Data Contract (Draft) — `daily_user_features`

**Status:** Draft. This table does not exist in any database as of Day 1. Nothing in this
document has been implemented or verified against real data; it describes the intended
target so later-day transformation and load work has something concrete to build toward.

## Grain

One row per `(user_id, feature_date)` — a single user's aggregated behavior for a single
calendar day.

## Candidate key

`(user_id, feature_date)` — proposed primary key, matching the ERD draft in `erd.md`.

## Fields

| Field | Type (proposed) | Required | Nullable | Source / status |
|---|---|---|---|---|
| `user_id` | integer | yes | no | from `users`; confirmed as a join key in prior planning, not yet verified against a real file |
| `feature_date` | date | yes | no | derived from `p_date` in the raw interaction data (raw data not yet ingested) |
| `late_night_share` | numeric (0-1) | proposed | TBD | fraction of watch time in a late-night window; exact window boundaries not yet decided |
| `avg_session_length` | numeric | proposed | TBD | session definition (what counts as one session) not yet decided |
| `hate_rate` | numeric (0-1) | proposed | TBD | per prior profiling discussion, `hate` is sparse; rate should be computed per user per day rather than assumed to have per-session stability |
| `transcript_exists` | boolean | proposed | no | locked scope: file-existence check only, no content analysis |
| `transcript_word_count` | integer | proposed | yes (null if no transcript) | locked scope: word/character count only, no NLP |
| `rewatch_flag_rate` | numeric (0-1) | proposed | TBD | derived from `is_rewatch_flagged` in `interactions_curated`; not yet implemented |

## Producer / consumer

- **Producer (intended):** the staging → curated transformation step (Person B's track),
  not yet built.
- **Consumer (intended):** `risk_scores` table computation, and any downstream
  dashboard/notebook use described in earlier project planning. No consumer currently reads
  this table since it does not exist yet.

## Constraints (proposed, unverified)

- `(user_id, feature_date)` unique.
- `late_night_share` and `hate_rate` bounded to [0, 1] once implemented.
- `transcript_word_count` non-negative when not null.

## Explicitly unresolved / TBD

- Late-night window boundaries (hour range) are not fixed. Earlier profiling discussion
  noted the available raw sample lacked hours 0-1, which bears on how this window should be
  defined, but that has not been resolved here.
- Session definition for `avg_session_length` is not fixed.
- No validation of these fields against real data has occurred — no data exists in this
  repository to validate against as of Day 1.
- This contract will need revision once Person A's raw ingestion output and Person B's
  staging logic exist and the real column set is known.
