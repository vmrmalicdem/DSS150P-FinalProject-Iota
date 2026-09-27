# Entity-Relationship Diagram — Draft (Day 1)

**Status:** Draft sketch only. No Postgres schema has been implemented in this repository as
of Day 1 — there is no DDL, no running database load, and this diagram is not to be read as
confirmation that any of the below exists in a live database. It is a design target for
later days, checked against `transformation-spec.md` so the two stay consistent.

## Entities and relationships (proposed)

```
users
  user_id (PK)
  gender
  age
  fre_city
  fre_community_type      -- 'unknown' is a valid value, not imputed (see transformation-spec.md §3)
  fre_city_level           -- 'unknown' is a valid value, not imputed

videos
  pid (PK)                 -- video id
  duration
  author_id
  mod_price

interactions_curated
  user_id (FK -> users.user_id)
  pid (FK -> videos.pid)
  exposed_time
  watch_time
  is_rewatch_flagged        -- boolean, derived; see transformation-spec.md §2
  hate
  click, comment, forward, cvm_like, follow, collect   -- confirmed present in real raw data (see transformation-spec.md §4)
  p_date
  p_hour
  PRIMARY KEY (user_id, pid, exposed_time)   -- matches the dedup key in transformation-spec.md §1

daily_user_features
  user_id (FK -> users.user_id)
  feature_date
  late_night_share           -- proposed
  avg_session_length          -- proposed
  hate_rate                   -- proposed
  transcript_word_count       -- proposed, tied to the (locked) narrow transcript scope
  transcript_exists           -- proposed, boolean
  PRIMARY KEY (user_id, feature_date)

risk_scores
  user_id (FK -> users.user_id)
  score_date
  risk_score                  -- proposed; scoring method not yet designed
  PRIMARY KEY (user_id, score_date)
```

## Relationships

- `interactions_curated.user_id` → `users.user_id` (many-to-one)
- `interactions_curated.pid` → `videos.pid` (many-to-one)
- `daily_user_features.user_id` → `users.user_id` (many-to-one)
- `risk_scores.user_id` → `users.user_id` (many-to-one)

## Explicitly unresolved / TBD

- `interactions_curated`'s full column list is proposed, not confirmed — it depends on
  Person A's actual raw ingestion output, which does not exist in this repository yet.
- `risk_scores.risk_score` has no defined calculation method yet; this table exists here as
  a placeholder target, not a designed feature.
- Foreign key types (integer vs. string ids) are assumed consistent with `users.user_id` /
  `videos.pid` but not verified against any real source file.
- This diagram has not been translated into DDL or validated against a running Postgres
  instance in this repository.
