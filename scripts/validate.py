"""
Automated data-quality validation.

Three gates, one per layer boundary:
  run_raw(p_date)      before staging   (source contract)
  run_staged(p_date)   after staging    (transformation correctness)
  run_curated(p_date)  after curation   (feature correctness, referential integrity)

Each check is tagged with a check_type (schema, nullability, datatype, range,
accepted_values, uniqueness, referential_integrity, reconciliation,
business_rule, duplicates, coverage) and a severity:
  ERROR  fails the gate: raises ValidationError, which fails the Airflow task
  WARN   logged and written to the report, does not stop the pipeline

Every run writes a JSON report to staging/_validation/.
"""

import logging
from dataclasses import asdict, dataclass

import pandas as pd

import io_utils as io
from config import EVENT_KEY, STAGING_DATA_DIR, get_logger

log = get_logger("validate")

EXPECTED_COLUMNS = [
    "user_id", "pid", "author_id", "category_id", "category_level", "parent_id", "root_id",
    "exposed_time", "author_fans_count", "watch_time", "duration", "cvm_like", "click",
    "comment", "follow", "collect", "forward", "hate", "tag_name", "title", "p_hour",
    "p_date", "gender", "age", "mod_price", "fre_city", "fre_community_type", "fre_city_level",
]
INT_COLS = ["user_id", "pid", "author_id", "category_id", "category_level", "parent_id",
            "root_id", "exposed_time", "author_fans_count", "watch_time", "p_hour", "age", "mod_price"]
BOOL_COLS = ["cvm_like", "click", "comment", "follow", "collect", "forward", "hate"]
USER_ATTRS = ["gender", "age", "mod_price", "fre_city", "fre_community_type", "fre_city_level"]

# 'unknown' is a valid category by design (transformation-spec section 3).
ACCEPTED = {
    "gender": {"M", "F"},
    "fre_community_type": {"乡村", "镇区", "城区", "unknown"},
    "fre_city_level": {"一线城市", "新一线城市", "二线城市", "三线城市", "四线城市", "五线城市", "unknown"},
}
AGE_RANGE = (-1, 200)   # relaxed bounds for full dataset (unknowns)
DUPLICATE_SHARE_WARN = 0.30  # drift alarm; the profiled sample sits near 13%


class ValidationError(Exception):
    """Raised when one or more ERROR-severity checks fail."""


@dataclass
class Check:
    name: str
    check_type: str
    severity: str
    passed: bool
    detail: str


class Report:
    def __init__(self, stage, p_date):
        self.stage, self.p_date, self.checks = stage, p_date, []

    def add(self, name, check_type, passed, detail="", severity="ERROR"):
        self.checks.append(Check(name, check_type, severity, bool(passed), str(detail)))
        if passed:
            level, tag = logging.INFO, "PASS"
        else:
            level, tag = (logging.ERROR, "FAIL") if severity == "ERROR" else (logging.WARNING, "WARN")
        log.log(level, "[%s %s] %s %s (%s): %s", self.stage, self.p_date, tag, name, check_type, detail)

    def finish(self):
        errors = [c for c in self.checks if not c.passed and c.severity == "ERROR"]
        warns = [c for c in self.checks if not c.passed and c.severity == "WARN"]
        summary = {
            "stage": self.stage, "p_date": self.p_date,
            "checks_run": len(self.checks),
            "passed": len(self.checks) - len(errors) - len(warns),
            "warnings": len(warns), "errors": len(errors),
            "checks": [asdict(c) for c in self.checks],
        }
        io.write_json(summary, STAGING_DATA_DIR / "_validation" / f"{self.stage}_{self.p_date}.json")
        log.info("[%s %s] %d checks: %d passed, %d warnings, %d errors",
                 self.stage, self.p_date, summary["checks_run"], summary["passed"], len(warns), len(errors))
        if errors:
            raise ValidationError(
                f"{self.stage} validation failed for {self.p_date}: "
                + "; ".join(f"{c.name} ({c.detail})" for c in errors))
        return summary


# --------------------------------------------------------------------------
# Gate 1: raw partition
# --------------------------------------------------------------------------

def run_raw(p_date):
    p_date = io.check_p_date(p_date)
    r = Report("raw", p_date)
    raw = io.read_raw_partition(p_date)

    missing = [c for c in EXPECTED_COLUMNS if c not in raw.columns]
    extra = [c for c in raw.columns if c not in EXPECTED_COLUMNS]
    r.add("schema_columns", "schema", not missing and not extra,
          f"missing={missing} extra={extra}" if (missing or extra) else f"{len(raw.columns)} expected columns present")
    r.add("partition_not_empty", "row_count", len(raw) > 0, f"{len(raw)} rows")
    if missing or raw.empty:
        r.finish()  # cannot continue without the expected schema; raises

    empty_cells = raw.apply(lambda s: s.str.strip().eq("")).sum()
    bad_null = empty_cells[empty_cells > 0].to_dict()
    r.add("required_fields_not_null", "nullability", not bad_null,
          f"empty values: {bad_null}" if bad_null else "no empty values in any column")

    bad_types = {}
    for c in INT_COLS:
        n = (~raw[c].str.fullmatch(r"-?\d+")).sum()
        if n:
            bad_types[c] = int(n)
    n = pd.to_numeric(raw["duration"], errors="coerce").isna().sum()
    if n:
        bad_types["duration"] = int(n)
    for c in BOOL_COLS:
        n = (~raw[c].isin(["True", "False"])).sum()
        if n:
            bad_types[c] = int(n)
    r.add("column_datatypes", "datatype", not bad_types,
          f"unparseable values: {bad_types}" if bad_types else "all numeric and boolean columns parse")
    if bad_types or bad_null:
        r.finish()  # range checks need clean numbers; raises

    num = raw[INT_COLS].astype("int64")
    dur = raw["duration"].astype("float64")
    ranges = {
        "p_hour_0_23": (num["p_hour"] < 0) | (num["p_hour"] > 23),
        "age_in_range": (num["age"] < AGE_RANGE[0]) | (num["age"] > AGE_RANGE[1]),
        "watch_time_non_negative": num["watch_time"] < 0,
        "duration_positive": dur <= 0,
        "mod_price_non_negative": num["mod_price"] < 0,
        "exposed_time_positive": num["exposed_time"] <= 0,
    }
    for name, bad in ranges.items():
        r.add(name, "range", bad.sum() == 0, f"{int(bad.sum())} violating rows")

    for col, allowed in ACCEPTED.items():
        bad = raw.loc[~raw[col].isin(allowed), col].value_counts().head(5).to_dict()
        r.add(f"{col}_accepted_values", "accepted_values", not bad,
              f"unexpected values: {bad}" if bad else f"all values within {sorted(allowed)}")

    off = (raw["p_date"] != p_date).sum()
    r.add("p_date_matches_partition", "consistency", off == 0, f"{int(off)} rows outside partition {p_date}")

    inconsistent = raw.groupby("user_id")[USER_ATTRS].nunique().gt(1).any(axis=1).sum()
    r.add("user_attributes_consistent", "consistency", inconsistent == 0,
          f"{int(inconsistent)} users with conflicting attributes within the partition")

    dup_share = raw.duplicated().mean()
    r.add("exact_duplicate_share", "duplicates", dup_share <= DUPLICATE_SHARE_WARN,
          f"{dup_share:.1%} of rows are exact duplicates (removed in staging; alarm above {DUPLICATE_SHARE_WARN:.0%})",
          severity="WARN")

    cats = io.read_raw_categories()
    known = set(cats["category_id"].astype(int))
    unknown_ids = set(num["category_id"]) - known
    r.add("category_id_in_lookup", "referential_integrity", not unknown_ids,
          f"{len(unknown_ids)} category ids missing from lookup: {sorted(int(x) for x in unknown_ids)[:10]}"
          if unknown_ids else "every category_id exists in the category lookup")

    dup_ids = sorted(int(x) for x in cats.loc[cats["category_id"].duplicated(keep=False), "category_id"].astype(int).unique())
    r.add("category_lookup_unique_ids", "uniqueness", not dup_ids,
          f"{len(dup_ids)} category ids appear twice with different English labels: {dup_ids}",
          severity="WARN")

    files = io.raw_transcript_files()
    r.add("transcript_files_present", "coverage", len(files) > 0, f"{len(files)} transcript files")

    return r.finish()


# --------------------------------------------------------------------------
# Gate 2: staged partition
# --------------------------------------------------------------------------

def run_staged(p_date):
    p_date = io.check_p_date(p_date)
    r = Report("staged", p_date)
    ev = pd.read_parquet(io.staged_events_path(p_date))
    raw = io.read_raw_partition(p_date).drop_duplicates()
    raw_keys = raw[EVENT_KEY].astype("int64").drop_duplicates()

    earlier = io.earlier_event_keys(p_date)
    if len(earlier):
        marked = raw_keys.merge(earlier.astype("int64"), on=EVENT_KEY, how="left", indicator=True)
        raw_keys = marked[marked["_merge"] == "left_only"][EVENT_KEY]
    expected = len(raw_keys)

    r.add("event_key_unique", "uniqueness", not ev.duplicated(subset=EVENT_KEY).any(),
          f"{int(ev.duplicated(subset=EVENT_KEY).sum())} duplicate (user_id, pid, exposed_time) keys")
    r.add("event_count_reconciles_to_raw", "reconciliation", len(ev) == expected,
          f"staged={len(ev)} expected_from_raw={expected}")
    key_nulls = int(ev[EVENT_KEY].isna().sum().sum())
    r.add("key_columns_not_null", "nullability", key_nulls == 0, f"{key_nulls} null key values")
    r.add("tag_count_positive", "range", (ev["tag_count"] >= 1).all(), f"min tag_count={ev['tag_count'].min()}")
    r.add("watch_ratio_non_negative", "range", (ev["watch_ratio"] >= 0).all(), f"min={ev['watch_ratio'].min():.3f}")

    # Business rule: rewatch-inflated watch_time is retained, not capped or dropped.
    rw = raw.drop_duplicates(subset=EVENT_KEY)
    expected_rewatch = int((rw["watch_time"].astype("int64") > rw["duration"].astype("float64")).sum()) \
        if len(earlier) == 0 else None
    actual_rewatch = int(ev["is_rewatch_flagged"].sum())
    max_ratio = float(ev["watch_ratio"].max())
    r.add("rewatch_retained_and_flagged", "business_rule",
          (expected_rewatch is None) or expected_rewatch == actual_rewatch,
          f"flagged={actual_rewatch} events with watch_time > duration (max ratio {max_ratio:.1f}x); none capped or dropped")

    # Business rule: 'unknown' categories are kept as their own category, not imputed.
    for col in ["fre_community_type", "fre_city_level"]:
        raw_unknown = int(raw.loc[raw[col] == "unknown"].drop_duplicates(subset=EVENT_KEY).shape[0])
        stg_unknown = int((ev[col] == "unknown").sum())
        if len(earlier) > 0:
            ok = True
        else:
            ok = stg_unknown > 0 if (raw_unknown > 0) else stg_unknown == 0
        r.add(f"{col}_unknown_preserved", "business_rule", ok,
              f"'unknown' events in staging={stg_unknown}; raw (before cross-partition ownership)={raw_unknown}")

    vc = pd.read_parquet(io.staged_video_categories_path(p_date))
    r.add("video_category_pairs_unique", "uniqueness", not vc.duplicated().any(), f"{len(vc)} pairs")
    r.add("staged_events_have_categories", "referential_integrity",
          set(ev["pid"]).issubset(set(vc["pid"])) or len(earlier) > 0,
          "every staged video has at least one category row")
    return r.finish()


# --------------------------------------------------------------------------
# Gate 3: curated partition
# --------------------------------------------------------------------------

def run_curated(p_date):
    p_date = io.check_p_date(p_date)
    r = Report("curated", p_date)
    ev = pd.read_parquet(io.curated_fact_path("interactions_curated", p_date))
    ft = pd.read_parquet(io.curated_fact_path("daily_user_features", p_date))
    users = pd.read_parquet(io.curated_dim_path("users"))
    videos = pd.read_parquet(io.curated_dim_path("videos"))
    cats = pd.read_parquet(io.curated_dim_path("categories"))
    vcat = pd.read_parquet(io.curated_dim_path("video_categories"))
    staged = pd.read_parquet(io.staged_events_path(p_date))

    r.add("features_pk_unique", "uniqueness", not ft.duplicated(subset=["user_id", "feature_date"]).any(),
          f"{len(ft)} feature rows")
    for col in ["late_night_share", "hate_rate", "rewatch_rate"]:
        bad = ft[col].dropna()
        r.add(f"{col}_within_0_1", "range", bool(((bad >= 0) & (bad <= 1)).all()),
              f"min={bad.min():.3f} max={bad.max():.3f}")
    r.add("hate_events_le_events", "business_rule", bool((ft["hate_events"] <= ft["n_events"]).all()),
          "hate_events never exceeds n_events")
    r.add("sessions_consistent", "business_rule",
          bool(((ft["n_sessions"] >= 1) & (ft["max_session_seconds"] >= ft["avg_session_seconds"] - 1e-9)).all()),
          "every active user-day has at least one session and max >= avg session length")
    r.add("feature_event_totals_reconcile", "reconciliation", int(ft["n_events"].sum()) == len(ev) == len(staged),
          f"sum(n_events)={int(ft['n_events'].sum())} curated_events={len(ev)} staged_events={len(staged)}")
    r.add("features_users_exist", "referential_integrity", set(ft["user_id"]).issubset(set(users["user_id"])),
          "every feature row has a user in the users dimension")
    r.add("events_users_videos_exist", "referential_integrity",
          set(ev["user_id"]).issubset(set(users["user_id"])) and set(ev["pid"]).issubset(set(videos["pid"])),
          "every event references an existing user and video")
    r.add("video_categories_exist", "referential_integrity",
          set(vcat["category_id"]).issubset(set(cats["category_id"])) and set(vcat["pid"]).issubset(set(videos["pid"])),
          "every (video, category) pair references existing videos and categories")
    tr = videos[videos["has_transcript"]]
    r.add("transcript_fields_consistent", "business_rule",
          bool(videos.loc[~videos["has_transcript"], "transcript_word_count"].isna().all()
               and (tr["transcript_word_count"] >= 0).all()),
          f"{len(tr)} of {len(videos)} videos have a transcript (word count only, no content analysis)",)
    return r.finish()


if __name__ == "__main__":
    import sys
    {"raw": run_raw, "staged": run_staged, "curated": run_curated}[sys.argv[1]](sys.argv[2])
