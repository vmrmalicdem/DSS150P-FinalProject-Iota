# Data Dictionary — Curated Layer

Covers every table written to `curated/` and loaded into PostgreSQL. Types, row counts and
sample values below were captured by running the pipeline end to end
(`scripts/run_pipeline.py --all --skip-load`) against the real uploaded
`interaction_sampled.csv` (794,053 rows, 2022-09-16 to 2022-09-22) and reading back the
resulting Parquet files. For the formal schema/quality contract on
`daily_user_features` (types, constraints, producer/consumer), see
`docs/data-contract-daily-user-features.md`; this document covers all curated tables at the
field level.

---

## `interactions_curated` (fact table)

One row per de-duplicated, tag-collapsed event: `(user_id, pid, exposed_time)`.
129,483 rows across all 7 partitions, partitioned by `p_date`.

| Field | Type | Nullable | Description | Example |
| --- | --- | --- | --- | --- |
| `user_id` | integer | No | Viewer id. FK → `users.user_id`. | `1` |
| `pid` | integer | No | Video id. FK → `videos.pid`. | `63980` |
| `exposed_time` | integer (Unix seconds) | No | When the video was exposed to the user. Part of the event's natural key. | `1663598611` |
| `p_date` | date | No | Partition date: the source's own `p_date` label, which is the UTC+8 (Beijing) calendar date of `exposed_time`. An event that appears in several raw partitions is kept in the earliest one (3 events in the real data). See the profiling report, section 1.4. | `2022-09-19` |
| `p_hour` | integer (0–23) | No | Hour of day as given by the source. Equals the UTC+8 hour of `exposed_time` for 81.88% of rows and is one hour later for the rest; not recomputed. See the profiling report, section 1.4. | `22` |
| `author_fans_count` | integer | No | Follower count of the video's author at exposure time. | `29625` |
| `watch_time` | integer (seconds) | No | Seconds watched. | `111` |
| `watch_ratio` | float | No | `watch_time / duration`. Can exceed 1.0 (rewatch); can be `inf`/`NaN` if `duration` is 0, though no zero-duration rows were found in this file. | `0.991` |
| `is_rewatch_flagged` | boolean | No | `True` when `watch_time > duration`. Not dropped or capped — retained as a genuine engagement signal. | `False` |
| `tag_count` | integer | No | Number of raw rows (tags) collapsed into this one event. | `3` |
| `cvm_like`, `click`, `comment`, `follow`, `collect`, `forward`, `hate` | boolean | No | Interaction flags, cast from the source's string `"True"`/`"False"`. | `False` |
| `ingest_batch_id` | string | No | Batch id of the ingestion run that produced the underlying raw partition; supports traceability back to `raw/_ingestion_log/ingestion_log.jsonl`. | `20260929T061212Z-ba1b9b10` |

**Primary key:** `(user_id, pid, exposed_time)`. **Partition key:** `p_date`.

---

## `daily_user_features` (fact table, one row per user per day)

25,109 rows across all 7 partitions. Derived entirely from `interactions_curated` for the
matching `p_date`. See `docs/data-contract-daily-user-features.md` for the formal contract;
definitions below are the exact logic from `scripts/curate.py`.

| Field | Type | Nullable | Description | Example |
| --- | --- | --- | --- | --- |
| `user_id` | integer | No | FK → `users.user_id`. | `1` |
| `feature_date` | date | No | The day these features summarize. Part of the primary key. | `2022-09-19` |
| `n_events` | integer | No | Count of events for this user on this day. | `4` |
| `total_watch_seconds` | integer | No | Sum of `watch_time` for the day. | `620` |
| `late_night_events` | integer | No | Count of events where `p_hour` is in `[2, 4]` inclusive (`LATE_NIGHT_START_HOUR`/`LATE_NIGHT_END_HOUR`, configurable via environment). | `1` |
| `late_night_watch_seconds` | integer | No | `watch_time` summed over late-night events only. | `95` |
| `late_night_share` | float (0–1) | Yes | `late_night_watch_seconds / total_watch_seconds`. **Null when `total_watch_seconds = 0`** (a user-day with only zero-second events) — a genuine, documented edge case, not a bug. | `0.153` |
| `n_sessions` | integer | No | Count of sessions. A session is a run of one user's events, ordered by `exposed_time`, where each gap to the next event is ≤ 900 seconds (`SESSION_GAP_SECONDS`). | `2` |
| `max_session_seconds` | integer | No | Longest session's summed `watch_time`. | `410` |
| `avg_session_seconds` | float | No | Mean session `watch_time` across the day's sessions. | `310.0` |
| `hate_events` | integer | No | Count of events with `hate = True`. | `0` |
| `hate_rate` | float (0–1) | No | `hate_events / n_events`. | `0.0` |
| `rewatch_events` | integer | No | Count of events with `is_rewatch_flagged = True`. | `1` |
| `rewatch_rate` | float (0–1) | No | `rewatch_events / n_events`. | `0.25` |

**Primary key:** `(user_id, feature_date)`. **Partition key:** `feature_date` (`p_date` on disk).

---

## `dims/users` (dimension)

6,654 rows, one per distinct `user_id` seen anywhere in the source file. Rebuilt from all
staged partitions on every run (not incremental) — the safest option given `user_id` is the
whole dimension's key and attributes are static per user.

| Field | Type | Nullable | Description | Example |
| --- | --- | --- | --- | --- |
| `user_id` | integer | No | Primary key. | `1` |
| `gender` | string (`M`/`F`) | No | | `M` |
| `age` | integer (20–79 observed) | No | | `61` |
| `mod_price` | integer | No | Modal device/spending price bucket reported by the source. | `1999` |
| `fre_city` | string | No | Most frequent city (Chinese name, not translated). | `开封` |
| `fre_community_type` | string (`乡村`/`城区`/`镇区`/`unknown`) | No | `"unknown"` is a legitimate reported value, not a missing value. | `乡村` |
| `fre_city_level` | string (6 tier labels or `unknown`) | No | | `四线城市` |

**Primary key:** `user_id`.

---

## `dims/videos` (dimension)

31,496 rows, one per distinct `pid`.

| Field | Type | Nullable | Description | Example |
| --- | --- | --- | --- | --- |
| `pid` | integer | No | Primary key. | `1` |
| `author_id` | integer | No | | `520560003` |
| `title` | string (Chinese, may contain commas/newlines) | No | Parsed with a real CSV parser to preserve embedded newlines correctly (87 such rows in the source). | `站住!打劫手机` |
| `duration` | float (seconds) | No | | `14.733` |
| `has_transcript` | boolean | No | `True` for the 9 of 31,496 videos whose `pid` matches a file in `asr_en/`. | `True` |
| `transcript_word_count` | nullable integer | Yes | Null when `has_transcript = False`. | `45` |

**Primary key:** `pid`.

---

## `dims/categories` (dimension)

820 rows, one per distinct `category_id` (826 source rows minus 6 duplicates). Six ids carry
two different English labels in `categories_cn_en.csv`; staging keeps the **first occurrence
in file order** (a deterministic rule, so reruns always give the same result) and sets
`en_label_ambiguous = True` on those ids so the conflict stays visible downstream.

| Field | Type | Nullable | Description | Example |
| --- | --- | --- | --- | --- |
| `category_level` | integer (1–3) | No | | `1` |
| `category_id` | integer | No | Primary key. Unique after staging (the source file has 6 ids that appear twice). | `1` |
| `category_name_cn` | string | No | Whitespace-stripped. | `舞蹈` |
| `parent_id` | integer | No | | `1` |
| `root_id` | integer | No | | `1` |
| `category_name_en` | string | Yes (4 rows blank) | Whitespace-stripped (the source had a leading space on 786 of 826 values). | `dance` |
| `en_label_ambiguous` | boolean | No | `True` for the 6 `category_id` values that had two conflicting `category_name_en` rows in the source (ids 233, 239, 338, 350, 354, 368). The kept English label is the first one in file order. | `False` |

**Primary key:** `category_id`.

**Caveat for consumers:** first-occurrence is deterministic but not always *correct*. For two
of the six ambiguous ids the kept English label is visibly wrong against the Chinese name:
id 239 (舞蹈教学, "dance teaching") keeps "Ace warrior", and id 354 (仿妆, "imitation makeup")
keeps "action movies". Rely on `category_name_cn` for these, or treat `en_label_ambiguous`
rows as unreliable English labels. Four rows also have a blank `category_name_en`.

---

## `dims/video_categories` (bridge table)

67,311 rows. One row per distinct `(pid, category_id)` pair — this is what the raw file's
tag fan-out becomes once collapsed: a video keeps all of its tags/categories here instead of
duplicating the fact row per tag.

| Field | Type | Nullable | Description | Example |
| --- | --- | --- | --- | --- |
| `pid` | integer | No | FK → `videos.pid`. | `1` |
| `category_id` | integer | No | FK → `categories.category_id`. | `6` |

**Primary key:** `(pid, category_id)`.

---

## Notes applying across all tables

- All tables are written as **Parquet**, partitioned by date where the table is a fact
  table (`interactions_curated`, `daily_user_features`); dimensions are rebuilt whole on
  every run from all staged partitions, so they are not partitioned by date.
- Booleans are native `bool` in the curated layer; the raw source stores them as the
  strings `"True"`/`"False"`.
- No field in the curated layer is silently coerced from the source's `"unknown"` string to
  a null — `"unknown"` is preserved as a value wherever the source uses it.
- Chinese text fields (`title`, `fre_city`, `category_name_cn`, `tag_name` pre-collapse) are
  kept in the original language; no translation is performed by the pipeline itself.