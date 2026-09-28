"""
Raw -> staging.

Per date partition:
  1. drop exact duplicate rows
  2. drop events already owned by an earlier partition (cross-partition rule)
  3. collapse the category/tag fan-out to one row per event
     (user_id, pid, exposed_time), keeping tag_count
  4. type the columns, derive watch_ratio and is_rewatch_flagged
  5. write the (video, category) pairs separately, since categories are a
     property of the video and not of the event

Retained on purpose (docs/transformation-spec.md):
  - rewatch-inflated watch_time is kept and flagged, never capped or dropped
  - 'unknown' categorical values stay as their own category, never imputed

Also stages the reference sources once per run: the category lookup and the
transcript files (file exists + word count only, nothing else).
"""

import re
from datetime import datetime, timezone

import pandas as pd

import io_utils as io
from config import EVENT_KEY, STAGING_DATA_DIR, get_logger

log = get_logger("stage")

INT_COLS = ["user_id", "pid", "author_id", "category_id", "category_level", "parent_id",
            "root_id", "exposed_time", "author_fans_count", "watch_time", "p_hour", "age",
            "mod_price"]
BOOL_COLS = ["cvm_like", "click", "comment", "follow", "collect", "forward", "hate"]
CATEGORY_COLS = ["category_id", "category_level", "parent_id", "root_id", "tag_name"]


def _type_columns(df):
    for c in INT_COLS:
        df[c] = df[c].astype("int64")
    df["duration"] = df["duration"].astype("float64")
    for c in BOOL_COLS:
        df[c] = df[c].map({"True": True, "False": False}).astype(bool)
    return df


def stage_partition(p_date):
    p_date = io.check_p_date(p_date)
    raw = io.read_raw_partition(p_date)
    n_raw = len(raw)

    raw = raw.drop_duplicates()
    n_after_exact = len(raw)

    raw = _type_columns(raw)

    # Cross-partition rule: an event belongs to the earliest partition it appears in.
    earlier = io.earlier_event_keys(p_date)
    n_events_before_ownership = raw.groupby(EVENT_KEY).ngroups
    if len(earlier):
        earlier = earlier.astype({c: "int64" for c in EVENT_KEY})
        marked = raw.merge(earlier, on=EVENT_KEY, how="left", indicator=True)
        raw = marked[marked["_merge"] == "left_only"].drop(columns="_merge")
    n_events_owned = raw.groupby(EVENT_KEY).ngroups

    # Fan-out collapse. Tie-break for the few events whose rows disagree on
    # p_hour or title: keep the smallest p_hour, then the smallest title.
    tag_count = raw.groupby(EVENT_KEY)["tag_name"].nunique().rename("tag_count").reset_index()
    video_categories = raw[["pid", "category_id"]].drop_duplicates().sort_values(["pid", "category_id"])

    events = (raw.sort_values(EVENT_KEY + ["p_hour", "title"], kind="mergesort")
                 .drop_duplicates(subset=EVENT_KEY, keep="first")
                 .drop(columns=CATEGORY_COLS))
    events = events.merge(tag_count, on=EVENT_KEY, how="left")

    events["p_date"] = pd.to_datetime(events["p_date"], format="%Y%m%d")
    events["watch_ratio"] = events["watch_time"] / events["duration"]
    events["is_rewatch_flagged"] = events["watch_time"] > events["duration"]
    events["ingest_batch_id"] = io.latest_ingest_batch_id()
    events["staged_at"] = datetime.now(timezone.utc).isoformat()
    events = events.sort_values(EVENT_KEY).reset_index(drop=True)

    io.write_parquet(events, io.staged_events_path(p_date))
    io.write_parquet(video_categories.reset_index(drop=True), io.staged_video_categories_path(p_date))

    stats = {
        "p_date": p_date,
        "raw_rows": n_raw,
        "exact_duplicate_rows_dropped": n_raw - n_after_exact,
        "events_in_partition": n_events_before_ownership,
        "events_owned_by_earlier_partition": n_events_before_ownership - n_events_owned,
        "staged_events": len(events),
        "video_category_pairs": len(video_categories),
        "rewatch_flagged_events": int(events["is_rewatch_flagged"].sum()),
        "hate_events": int(events["hate"].sum()),
    }
    io.write_json(stats, STAGING_DATA_DIR / "_stats" / f"stage_{p_date}.json")
    log.info("staged %s: %s", p_date, stats)
    return stats


def stage_categories():
    """Category lookup: strip labels, flag ids that carry conflicting English labels."""
    cats = io.read_raw_categories()
    for c in ["category_name_cn", "category_name_en"]:
        cats[c] = cats[c].str.strip()
    for c in ["category_level", "category_id", "parent_id", "root_id"]:
        cats[c] = cats[c].astype("int64")
    ambiguous = cats["category_id"].duplicated(keep=False)
    cats["en_label_ambiguous"] = ambiguous
    # Deterministic rule: keep the first occurrence in file order.
    cats = cats.drop_duplicates(subset="category_id", keep="first").sort_values("category_id")
    io.write_parquet(cats.reset_index(drop=True), io.STAGED_CATEGORIES_PATH)
    n_amb = int(cats["en_label_ambiguous"].sum())
    log.info("staged categories: %d rows, %d ids with conflicting English labels", len(cats), n_amb)
    return {"categories": len(cats), "ambiguous_ids": n_amb}


def stage_transcripts():
    """Transcript feature, locked scope: file exists + word count. Nothing else."""
    rows = []
    for f in io.raw_transcript_files():
        m = re.fullmatch(r"(\d+)\.txt", f.name)
        if not m:
            log.warning("skipping transcript with non-numeric name: %s", f.name)
            continue
        text = f.read_text(encoding="utf-8")
        rows.append({"pid": int(m.group(1)), "has_transcript": True,
                     "transcript_word_count": len(text.split())})
    df = pd.DataFrame(rows, columns=["pid", "has_transcript", "transcript_word_count"])
    df = df.astype({"pid": "int64", "has_transcript": "bool", "transcript_word_count": "int64"})
    io.write_parquet(df, io.STAGED_TRANSCRIPTS_PATH)
    log.info("staged transcripts: %d files", len(df))
    return {"transcripts": len(df)}


def run(p_date):
    stage_categories()
    stage_transcripts()
    return stage_partition(p_date)


if __name__ == "__main__":
    import sys
    run(sys.argv[1])
