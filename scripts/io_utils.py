"""Layer paths and read/write helpers shared by all stages."""

import json
import os
import re

import pandas as pd

from config import CURATED_DATA_DIR, EVENT_KEY, RAW_DATA_DIR, STAGING_DATA_DIR

P_DATE_RE = re.compile(r"^\d{8}$")


def check_p_date(p_date):
    if not P_DATE_RE.match(str(p_date)):
        raise ValueError(f"p_date must look like YYYYMMDD, got {p_date!r}")
    return str(p_date)


# ---------------- raw layer ----------------

def raw_partition_path(p_date):
    return RAW_DATA_DIR / "interactions" / f"p_date={p_date}" / "interactions.csv"


def raw_partition_exists(p_date):
    return raw_partition_path(p_date).exists()


def list_raw_partitions():
    root = RAW_DATA_DIR / "interactions"
    if not root.exists():
        return []
    return sorted(d.name.split("=", 1)[1] for d in root.glob("p_date=*") if d.is_dir())


def read_raw_partition(p_date, usecols=None):
    """Read a raw partition with every field as text. Typing happens in staging."""
    path = raw_partition_path(p_date)
    if not path.exists():
        raise FileNotFoundError(f"raw partition not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8", usecols=usecols)


def read_raw_categories():
    path = RAW_DATA_DIR / "categories" / "categories_cn_en.csv"
    if not path.exists():
        raise FileNotFoundError(f"raw category lookup not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def raw_transcript_files():
    d = RAW_DATA_DIR / "transcripts" / "asr_en"
    return sorted(d.glob("*.txt")) if d.exists() else []


def earlier_event_keys(p_date):
    """
    Event keys present in any raw partition dated before p_date.

    Three events in the source appear in two date partitions. Rule: an event
    belongs to the earliest partition it appears in, so partitions never
    overlap and the event primary key holds across the whole warehouse.
    """
    frames = []
    for other in list_raw_partitions():
        if other < p_date:
            frames.append(read_raw_partition(other, usecols=EVENT_KEY).drop_duplicates())
    if not frames:
        return pd.DataFrame(columns=EVENT_KEY, dtype=str)
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def latest_ingest_batch_id(source="interaction_sampled.csv"):
    """Batch id of the most recent successful ingestion of a source (lineage)."""
    log_file = RAW_DATA_DIR / "_ingestion_log" / "ingestion_log.jsonl"
    if not log_file.exists():
        return None
    batch = None
    for line in log_file.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("source") == source and str(ev.get("status", "")).startswith("OK"):
            batch = ev.get("batch_id")
    return batch


# ---------------- staging layer ----------------

def staged_events_path(p_date):
    return STAGING_DATA_DIR / "events" / f"p_date={p_date}" / "events.parquet"


def staged_video_categories_path(p_date):
    return STAGING_DATA_DIR / "video_categories" / f"p_date={p_date}" / "video_categories.parquet"


STAGED_CATEGORIES_PATH = STAGING_DATA_DIR / "categories" / "categories.parquet"
STAGED_TRANSCRIPTS_PATH = STAGING_DATA_DIR / "transcripts" / "transcripts.parquet"


def list_staged_dates():
    root = STAGING_DATA_DIR / "events"
    if not root.exists():
        return []
    return sorted(d.name.split("=", 1)[1] for d in root.glob("p_date=*") if (d / "events.parquet").exists())


# ---------------- curated layer ----------------

def curated_fact_path(table, p_date):
    return CURATED_DATA_DIR / table / f"p_date={p_date}" / "data.parquet"


def curated_dim_path(name):
    return CURATED_DATA_DIR / "dims" / f"{name}.parquet"


def write_parquet(df, path):
    """Write to a temp file then rename, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False, engine="pyarrow")
    os.replace(tmp, path)


def write_json(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)
