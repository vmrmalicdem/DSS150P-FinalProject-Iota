import argparse
import sys

import pandas as pd

import io_utils as io
from config import (CURATED_DATA_DIR, LATE_NIGHT_END_HOUR, LATE_NIGHT_START_HOUR, OUTPUTS_DIR,
                    get_logger)

log = get_logger("risk_analytics")

# Rule thresholds for the screening flag.
WATCH_QUANTILE = 0.75   # total_watch_seconds above this quantile
HATE_RATE_MIN = 0.01    # hate_rate above 1%
LATE_NIGHT_MIN = 0.10   # late_night_share above 10%
HEAVY_LATE_NIGHT = 0.50 # "majority of watch time late at night"


def load_features():
    """Concatenate all curated partitions; the date comes from the folder name."""
    root = CURATED_DATA_DIR / "daily_user_features"
    if not root.exists():
        return None, []
    frames, dates = [], []
    for part in sorted(root.glob("p_date=*/*.parquet")):
        d = part.parent.name.split("=", 1)[1]
        df = pd.read_parquet(part)
        df["p_date"] = d
        frames.append(df)
        dates.append(d)
    if not frames:
        return None, []
    return pd.concat(frames, ignore_index=True), dates


def coverage_check(curated_dates):
    """Compare curated partitions with the raw partitions that were ingested."""
    raw_dates = io.list_raw_partitions()
    missing = sorted(set(raw_dates) - set(curated_dates))
    return raw_dates, missing


def md_table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def analyse(df):
    wt = df["total_watch_seconds"]
    watch_cut = float(wt.quantile(WATCH_QUANTILE))

    # NaN (no watch time) compares False, so those user-days never count as late-night.
    f_watch = wt > watch_cut
    f_hate = df["hate_rate"] > HATE_RATE_MIN
    f_late = df["late_night_share"] > LATE_NIGHT_MIN
    n_flags = f_watch.astype(int) + f_hate.astype(int) + f_late.astype(int)
    heavy = df["late_night_share"] > HEAVY_LATE_NIGHT

    per_date = (df.groupby("p_date")
                  .agg(user_days=("user_id", "size"), users=("user_id", "nunique"),
                       avg_watch=("total_watch_seconds", "mean"),
                       late_night_user_days=("late_night_share", lambda s: int((s > HEAVY_LATE_NIGHT).sum())))
                  .reset_index())

    return {
        "user_day_records": int(len(df)),
        "distinct_users": int(df["user_id"].nunique()),
        "dates": sorted(df["p_date"].unique().tolist()),
        "avg_daily_watch_seconds": round(float(wt.mean()), 1),
        "median_daily_watch_seconds": round(float(wt.median()), 1),
        "p90_daily_watch_seconds": round(float(wt.quantile(0.90)), 1),
        "max_session_seconds": round(float(df["max_session_seconds"].max()), 1),
        "no_watch_time_user_days": int(df["late_night_share"].isna().sum()),
        "late_night_heavy_user_days": int(heavy.sum()),
        "late_night_heavy_distinct_users": int(df.loc[heavy, "user_id"].nunique()),
        "watch_cutoff_seconds": round(watch_cut, 1),
        "flag_any_1plus": int((n_flags >= 1).sum()),
        "flag_2plus": int((n_flags >= 2).sum()),
        "flag_all_3": int((n_flags == 3).sum()),
        "flag_counts": {"high_watch": int(f_watch.sum()), "hate_rate": int(f_hate.sum()),
                        "late_night": int(f_late.sum())},
        "per_date": per_date.round(1).to_dict("records"),
    }


def write_report(s, raw_dates, missing, min_events, path):
    n = s["user_day_records"]
    pct = lambda k: f"{100 * k / n:.1f}%" if n else "n/a"
    window = f"{LATE_NIGHT_START_HOUR:02d}:00-{LATE_NIGHT_END_HOUR:02d}:59"
    lines = [
        "# Short-Video Usage Pattern Analysis",
        "",
        "Behavioral signals computed from the curated `daily_user_features` layer. "
        "These are descriptive screens, not validated measures of addiction or sleep loss.",
        "",
        "## 0. Data coverage",
        f"- Curated partitions analysed: **{len(s['dates'])}** ({s['dates'][0]} to {s['dates'][-1]})",
        f"- Raw partitions ingested: **{len(raw_dates)}**",
        f"- Minimum events per user-day filter: **{min_events}** "
        + ("(no filter)" if min_events <= 1 else "(sparse user-days excluded)"),
    ]
    if missing:
        lines.append(f"- **WARNING:** raw partitions with no curated output: {', '.join(missing)}. "
                     "Figures below do not cover the full dataset. Run "
                     "`python scripts/run_pipeline.py --all --skip-load`.")
    lines += [
        "",
        "## 1. Exploratory statistics",
        f"- User-day records analysed: **{n:,}** ({s['distinct_users']:,} distinct users)",
        f"- Daily watch time: mean **{s['avg_daily_watch_seconds']} s**, median "
        f"**{s['median_daily_watch_seconds']} s**, 90th percentile **{s['p90_daily_watch_seconds']} s**",
        f"- Longest single session: **{s['max_session_seconds']} s**",
        f"- User-days with no watch time (late-night share undefined): **{s['no_watch_time_user_days']:,}**",
        f"- User-days with >50% of watch time in the late-night window ({window}): "
        f"**{s['late_night_heavy_user_days']:,}** ({pct(s['late_night_heavy_user_days'])}), "
        f"from **{s['late_night_heavy_distinct_users']:,}** distinct users",
        "",
        "### Records per day",
        md_table([(r["p_date"], f"{r['user_days']:,}", f"{r['users']:,}", r["avg_watch"],
                   f"{r['late_night_user_days']:,}") for r in s["per_date"]],
                 ["p_date", "user-days", "users", "avg watch (s)", "late-night heavy user-days"]),
        "",
        "## 2. Late-night usage",
        f"A subset of user-days spends most watch time inside the late-night window ({window}). "
        "This marks a late-night viewing pattern; the data has no sleep or well-being measure, "
        "so it cannot show sleep deprivation.",
        "",
        "## 3. Rule-based screening flag (heuristic, not a risk score)",
        "Three rules, each worth one point per user-day:",
        f"- Watch time above the {int(WATCH_QUANTILE * 100)}th percentile ({s['watch_cutoff_seconds']} s)",
        f"- Hate rate above {HATE_RATE_MIN:.0%}",
        f"- Late-night share above {LATE_NIGHT_MIN:.0%}",
        "",
        md_table([("At least 1 rule", f"{s['flag_any_1plus']:,}", pct(s["flag_any_1plus"])),
                  ("At least 2 rules", f"{s['flag_2plus']:,}", pct(s["flag_2plus"])),
                  ("All 3 rules", f"{s['flag_all_3']:,}", pct(s["flag_all_3"]))],
                 ["Flag level", "user-days", "share of user-days"]),
        "",
        f"Individual rules: high watch time {s['flag_counts']['high_watch']:,}, "
        f"hate rate {s['flag_counts']['hate_rate']:,}, late-night {s['flag_counts']['late_night']:,}.",
        "",
        "The strictest level (all 3 rules) is the most defensible for review. A single rule is common "
        "and not meaningful alone. No outcome data exists to validate any level, so `risk_scores` "
        "remains unpopulated.",
        "",
        "## 4. Visualizations",
        "Not generated here. The columns above can be plotted in a notebook or a BI tool.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-events", type=int, default=1,
                    help="keep only user-days with at least this many events (default 1 = no filter)")
    ap.add_argument("--expected-rows", type=int, default=None,
                    help="exit with an error if the number of user-days analysed differs")
    args = ap.parse_args(argv)

    df, dates = load_features()
    if df is None:
        log.error("No curated daily_user_features found. Run: python scripts/run_pipeline.py --all --skip-load")
        return 1

    raw_dates, missing = coverage_check(dates)
    if missing:
        log.warning("raw partitions without curated output: %s", missing)

    if args.min_events > 1:
        before = len(df)
        df = df[df["n_events"] >= args.min_events]
        log.info("min-events filter %d: kept %d of %d user-days", args.min_events, len(df), before)
    if df.empty:
        log.error("No user-days left to analyse.")
        return 1

    summary = analyse(df)
    summary.update(raw_partitions=raw_dates, missing_curated_partitions=missing, min_events=args.min_events)

    out_dir = OUTPUTS_DIR / "analytics"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_report(summary, raw_dates, missing, args.min_events, out_dir / "risk_analysis_report.md")
    io.write_json(summary, out_dir / "risk_analysis_summary.json")
    log.info("analysed %d user-days across %d partitions -> %s", summary["user_day_records"],
             len(summary["dates"]), out_dir)

    if args.expected_rows is not None and summary["user_day_records"] != args.expected_rows:
        log.error("expected %d user-days but analysed %d", args.expected_rows, summary["user_day_records"])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())