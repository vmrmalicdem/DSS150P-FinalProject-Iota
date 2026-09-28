-- Curated warehouse schema. Idempotent: safe to run on every load.
-- Load strategy: dimensions are upserted, fact tables are replaced per date partition.

CREATE TABLE IF NOT EXISTS categories (
    category_id         integer  PRIMARY KEY,
    category_level      smallint NOT NULL CHECK (category_level BETWEEN 1 AND 3),
    category_name_cn    text     NOT NULL,
    category_name_en    text,
    parent_id           integer  NOT NULL,
    root_id             integer  NOT NULL,
    en_label_ambiguous  boolean  NOT NULL DEFAULT false  -- source lookup had conflicting English labels for this id
);

CREATE TABLE IF NOT EXISTS users (
    user_id             bigint   PRIMARY KEY,
    gender              char(1)  NOT NULL CHECK (gender IN ('M', 'F')),
    age                 smallint NOT NULL CHECK (age BETWEEN 10 AND 100),
    mod_price           integer  NOT NULL CHECK (mod_price >= 0),   -- user's device price, a user attribute
    fre_city            text     NOT NULL,
    fre_community_type  text     NOT NULL,   -- 'unknown' is a valid category, not a null
    fre_city_level      text     NOT NULL,   -- 'unknown' is a valid category, not a null
    total_events        integer  NOT NULL DEFAULT 0,
    is_sparse_history   boolean  NOT NULL DEFAULT false  -- fewer than MIN_USER_EVENTS events; flagged, not excluded
);

CREATE TABLE IF NOT EXISTS videos (
    pid                    bigint   PRIMARY KEY,
    author_id              bigint   NOT NULL,
    title                  text     NOT NULL,
    duration               double precision NOT NULL CHECK (duration > 0),
    has_transcript         boolean  NOT NULL DEFAULT false,
    transcript_word_count  integer  CHECK (transcript_word_count >= 0),
    CHECK ((has_transcript AND transcript_word_count IS NOT NULL)
        OR (NOT has_transcript AND transcript_word_count IS NULL))
);

CREATE TABLE IF NOT EXISTS video_categories (
    pid          bigint  NOT NULL REFERENCES videos (pid),
    category_id  integer NOT NULL REFERENCES categories (category_id),
    PRIMARY KEY (pid, category_id)
);

CREATE TABLE IF NOT EXISTS interactions_curated (
    user_id             bigint   NOT NULL REFERENCES users (user_id),
    pid                 bigint   NOT NULL REFERENCES videos (pid),
    exposed_time        bigint   NOT NULL,     -- unix seconds; with user_id and pid this is the event key
    p_date              date     NOT NULL,
    p_hour              smallint NOT NULL CHECK (p_hour BETWEEN 0 AND 23),
    author_fans_count   bigint   NOT NULL,
    watch_time          integer  NOT NULL CHECK (watch_time >= 0),   -- rewatch-inflated values retained
    watch_ratio         double precision NOT NULL CHECK (watch_ratio >= 0),
    is_rewatch_flagged  boolean  NOT NULL,     -- watch_time > duration
    tag_count           integer  NOT NULL CHECK (tag_count >= 1),
    cvm_like            boolean  NOT NULL,
    click               boolean  NOT NULL,
    comment             boolean  NOT NULL,
    follow              boolean  NOT NULL,
    collect             boolean  NOT NULL,
    forward             boolean  NOT NULL,
    hate                boolean  NOT NULL,
    ingest_batch_id     text,                  -- lineage back to raw/_ingestion_log
    PRIMARY KEY (user_id, pid, exposed_time)
);
CREATE INDEX IF NOT EXISTS idx_interactions_p_date ON interactions_curated (p_date);

CREATE TABLE IF NOT EXISTS daily_user_features (
    user_id                   bigint  NOT NULL REFERENCES users (user_id),
    feature_date              date    NOT NULL,
    n_events                  integer NOT NULL CHECK (n_events >= 1),
    total_watch_seconds       bigint  NOT NULL CHECK (total_watch_seconds >= 0),
    late_night_events         integer NOT NULL CHECK (late_night_events >= 0),
    late_night_watch_seconds  bigint  NOT NULL CHECK (late_night_watch_seconds >= 0),
    late_night_share          double precision CHECK (late_night_share BETWEEN 0 AND 1),  -- NULL when no watch time
    n_sessions                integer NOT NULL CHECK (n_sessions >= 1),
    max_session_seconds       bigint  NOT NULL CHECK (max_session_seconds >= 0),
    avg_session_seconds       double precision NOT NULL CHECK (avg_session_seconds >= 0),
    hate_events               integer NOT NULL CHECK (hate_events >= 0),
    hate_rate                 double precision NOT NULL CHECK (hate_rate BETWEEN 0 AND 1),
    rewatch_events            integer NOT NULL CHECK (rewatch_events >= 0),
    rewatch_rate              double precision NOT NULL CHECK (rewatch_rate BETWEEN 0 AND 1),
    PRIMARY KEY (user_id, feature_date)
);

-- Target table only. The risk score method is not designed yet, so nothing loads into it.
CREATE TABLE IF NOT EXISTS risk_scores (
    user_id     bigint NOT NULL REFERENCES users (user_id),
    score_date  date   NOT NULL,
    risk_score  double precision,
    PRIMARY KEY (user_id, score_date)
);
