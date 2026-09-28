"""
Staging -> curated.

Fact tables are written per date partition:
  interactions_curated   one row per event (user_id, pid, exposed_time)
  daily_user_features    one row per (user_id, feature_date)

Dimensions are rebuilt from every staged partition available, so they are
identical no matter which date triggered the run (rerun safe):
  users, videos (with the transcript feature), categories, video_categories

Feature definitions (docs/transformation-spec.md, section 5):
  late night     p_hour within [LATE_NIGHT_START_HOUR, LATE_NIGHT_END_HOUR], inclusive
  session        consecutive events of one user in one date partition where the gap
                 between the end of the previous view (exposed_time + watch_time)
                 and the next exposure is <= SESSION_GAP_SECONDS
  session length sum of watch_time (seconds) inside the session
  rewatch        watch_time > duration (is_rewatch_flagged); watch_ratio is kept so
                 other thresholds, e.g. 2x, can be applied downstream
"""

import numpy as np
import pandas as pd

import io_utils as io
from config import (EVENT_KEY, LATE_NIGHT_END_HOUR, LATE_NIGHT_START_HOUR, SESSION_GAP_SECONDS,
                    get_logger)

log = get_logger("curate")

EVENT_COLUMNS = ["user_id", "pid", "exposed_time", "p_date", "p_hour", "author_fans_count",
                 "watch_time", "watch_ratio", "is_rewatch_flagged", "tag_count", "cvm_like",
                 "click", "comment", "follow", "collect", "forward", "hate", "ingest_batch_id"]
USER_COLUMNS = ["user_id", "gender", "age", "mod_price", "fre_city", "fre_community_type", "fre_city_level"]


def compute_daily_features(events):
    e = events.sort_values(["user_id", "exposed_time", "pid"]).copy()
    e["end_time"] = e["exposed_time"] + e["watch_time"]

    # Running maximum end time handles overlapping views; shift so each event
    # is compared with everything that ended before it.
    prev_end = e.groupby("user_id")["end_time"].transform(lambda s: s.cummax().shift())
    gap = e["exposed_time"] - prev_end
    e["new_session"] = gap.isna() | (gap > SESSION_GAP_SECONDS)
    e["session_id"] = e.groupby("user_id")["new_session"].cumsum()

    sessions = (e.groupby(["user_id", "session_id"])["watch_time"].sum()
                  .groupby("user_id").agg(n_sessions="size", max_session_seconds="max",
                                          avg_session_seconds="mean"))

    e["is_late_night"] = e["p_hour"].between(LATE_NIGHT_START_HOUR, LATE_NIGHT_END_HOUR)
    e["late_watch"] = np.where(e["is_late_night"], e["watch_time"], 0)

    f = e.groupby("user_id").agg(
        feature_date=("p_date", "first"),
        n_events=("pid", "size"),
        total_watch_seconds=("watch_time", "sum"),
        late_night_events=("is_late_night", "sum"),
        late_night_watch_seconds=("late_watch", "sum"),
        hate_events=("hate", "sum"),
        rewatch_events=("is_rewatch_flagged", "sum"),
    ).join(sessions).reset_index()

    total = f["total_watch_seconds"].where(f["total_watch_seconds"] > 0)
    f["late_night_share"] = f["late_night_watch_seconds"] / total  # NaN when the user-day has no watch time
    f["hate_rate"] = f["hate_events"] / f["n_events"]
    f["rewatch_rate"] = f["rewatch_events"] / f["n_events"]
    for c in ["n_events", "total_watch_seconds", "late_night_events", "late_night_watch_seconds",
              "hate_events", "rewatch_events", "n_sessions", "max_session_seconds"]:
        f[c] = f[c].astype("int64")
    cols = ["user_id", "feature_date", "n_events", "total_watch_seconds", "late_night_events",
            "late_night_watch_seconds", "late_night_share", "n_sessions", "max_session_seconds",
            "avg_session_seconds", "hate_events", "hate_rate", "rewatch_events", "rewatch_rate"]
    return f[cols].sort_values("user_id").reset_index(drop=True)


def build_dimensions():
    dates = io.list_staged_dates()
    if not dates:
        raise FileNotFoundError("no staged partitions found; run staging first")
    events = pd.concat([pd.read_parquet(io.staged_events_path(d)) for d in dates], ignore_index=True)

    # Latest value wins for user attributes (profiling found them stable, so this is a formality).
    users = (events.sort_values("p_date").drop_duplicates("user_id", keep="last")[USER_COLUMNS]
                   .sort_values("user_id").reset_index(drop=True))

    videos = (events.sort_values(["pid", "title"]).drop_duplicates("pid", keep="first")[["pid", "author_id", "title", "duration"]]
                    .sort_values("pid").reset_index(drop=True))
    tr = pd.read_parquet(io.STAGED_TRANSCRIPTS_PATH)
    videos = videos.merge(tr, on="pid", how="left")
    videos["has_transcript"] = videos["has_transcript"].fillna(False).astype(bool)
    videos["transcript_word_count"] = videos["transcript_word_count"].astype("Int64")

    cats = pd.read_parquet(io.STAGED_CATEGORIES_PATH)
    vcat = (pd.concat([pd.read_parquet(io.staged_video_categories_path(d)) for d in dates], ignore_index=True)
              .drop_duplicates().sort_values(["pid", "category_id"]).reset_index(drop=True))

    for name, df in [("users", users), ("videos", videos), ("categories", cats), ("video_categories", vcat)]:
        io.write_parquet(df, io.curated_dim_path(name))
    log.info("dimensions rebuilt from %d staged partitions: users=%d videos=%d categories=%d video_categories=%d",
             len(dates), len(users), len(videos), len(cats), len(vcat))
    n_tr = int(videos["has_transcript"].sum())
    log.info("transcript feature coverage: %d of %d videos have a transcript file", n_tr, len(videos))
    return {"users": len(users), "videos": len(videos), "videos_with_transcript": n_tr}


def curate_partition(p_date):
    p_date = io.check_p_date(p_date)
    events = pd.read_parquet(io.staged_events_path(p_date))
    facts = events[EVENT_COLUMNS].copy()
    features = compute_daily_features(events)
    io.write_parquet(facts, io.curated_fact_path("interactions_curated", p_date))
    io.write_parquet(features, io.curated_fact_path("daily_user_features", p_date))
    stats = {"p_date": p_date, "interactions_curated": len(facts), "daily_user_features": len(features)}
    log.info("curated %s: %s", p_date, stats)
    return stats


def run(p_date):
    stats = curate_partition(p_date)
    stats.update(build_dimensions())
    return stats


if __name__ == "__main__":
    import sys
    run(sys.argv[1])
