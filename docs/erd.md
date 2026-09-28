# Entity-Relationship Diagram

**Status:** Implemented in `sql/schema.sql` and loaded successfully on Day 3 (tested against a local
PostgreSQL 16 with the real data). This replaces the Day 1 draft. Two Day 1 design errors were fixed
after inspecting the real data: `mod_price` is a user attribute (it had been placed on `videos`), and the
transcript fields belong to `videos`, not to the per-user daily features.

```mermaid
erDiagram
    categories ||--o{ video_categories : "labels"
    videos ||--o{ video_categories : "has"
    users ||--o{ interactions_curated : "performs"
    videos ||--o{ interactions_curated : "is viewed in"
    users ||--o{ daily_user_features : "summarized by"
    users ||--o{ risk_scores : "scored in"

    categories {
        int category_id PK
        smallint category_level
        text category_name_cn
        text category_name_en
        int parent_id
        int root_id
        bool en_label_ambiguous
    }
    users {
        bigint user_id PK
        char gender "M or F"
        smallint age
        int mod_price "device price"
        text fre_city
        text fre_community_type "unknown allowed"
        text fre_city_level "unknown allowed"
        int total_events
        bool is_sparse_history
    }
    videos {
        bigint pid PK
        bigint author_id
        text title
        float duration
        bool has_transcript
        int transcript_word_count "null when no transcript"
    }
    video_categories {
        bigint pid PK, FK
        int category_id PK, FK
    }
    interactions_curated {
        bigint user_id PK, FK
        bigint pid PK, FK
        bigint exposed_time PK
        date p_date
        smallint p_hour
        bigint author_fans_count
        int watch_time "rewatch values retained"
        float watch_ratio
        bool is_rewatch_flagged "watch_time > duration"
        int tag_count
        bool cvm_like
        bool click
        bool comment
        bool follow
        bool collect
        bool forward
        bool hate
        text ingest_batch_id "lineage"
    }
    daily_user_features {
        bigint user_id PK, FK
        date feature_date PK
        int n_events
        bigint total_watch_seconds
        int late_night_events
        bigint late_night_watch_seconds
        float late_night_share "null if no watch time"
        int n_sessions
        bigint max_session_seconds
        float avg_session_seconds
        int hate_events
        float hate_rate
        int rewatch_events
        float rewatch_rate
    }
    risk_scores {
        bigint user_id PK, FK
        date score_date PK
        float risk_score "not populated yet"
    }
```

## Keys and rules

- `interactions_curated` primary key `(user_id, pid, exposed_time)` is the deduplication key from `transformation-spec.md`.
- `unknown` values in `fre_community_type` and `fre_city_level` are stored as text, never as NULL.
- Rewatch-inflated `watch_time` is stored as is, with `is_rewatch_flagged` and `watch_ratio` alongside.
- Load strategy: dimensions are upserted, fact tables are replaced per date partition.
- `risk_scores` is a target table only. The scoring method is not designed.
