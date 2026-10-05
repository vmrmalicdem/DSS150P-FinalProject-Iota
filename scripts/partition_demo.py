# Partition demonstration (project requirement 4.11).

import argparse
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import io_utils as io
from bench_utils import machine_info, median_seconds
from config import EVENT_KEY, OUTPUTS_DIR, get_logger

log = get_logger("partition_demo")

TABLE = "interactions_curated"
KEY = "p_date"


def to_timestamp(p_date):
    p_date = io.check_p_date(p_date)
    return pd.Timestamp(f"{p_date[:4]}-{p_date[4:6]}-{p_date[6:]}")


# ---------------------------------------------------------------- parquet metadata helpers

def _matching_groups(meta, ts):
    """Row groups whose min/max statistics could contain ts (all of them if statistics are unusable)."""
    idx = meta.schema.names.index(KEY)
    groups = []
    for g in range(meta.num_row_groups):
        stats = meta.row_group(g).column(idx).statistics
        try:
            if stats is None or not stats.has_min_max or stats.min <= ts <= stats.max:
                groups.append(g)
        except TypeError:        # statistics in an unexpected type: be conservative and read the group
            groups.append(g)
    return groups


def _group_cost(meta, groups):
    """(rows, compressed bytes) held by the given row groups."""
    rows = sum(meta.row_group(g).num_rows for g in groups)
    size = sum(meta.row_group(g).column(c).total_compressed_size
               for g in groups for c in range(meta.num_columns))
    return rows, size


# ---------------------------------------------------------------- strategies (curated Parquet)

def read_one_partition(p_date):
    path = io.curated_fact_path(TABLE, p_date)
    df = pd.read_parquet(path)
    meta = pq.ParquetFile(path).metadata
    rows, size = _group_cost(meta, range(meta.num_row_groups))
    return df, {"files_read": 1, "rows_read": rows, "bytes_read": size}


def read_all_then_filter(p_date):
    paths = [io.curated_fact_path(TABLE, d) for d in io.list_curated_dates(TABLE)]
    df = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    rows = size = 0
    for p in paths:
        meta = pq.ParquetFile(p).metadata
        r, s = _group_cost(meta, range(meta.num_row_groups))
        rows, size = rows + r, size + s
    return df[df[KEY] == to_timestamp(p_date)], {"files_read": len(paths), "rows_read": rows, "bytes_read": size}


def read_single_file(p_date, single_path):
    ts = to_timestamp(p_date)
    df = pd.read_parquet(single_path, filters=[(KEY, "==", ts)])
    meta = pq.ParquetFile(single_path).metadata
    rows, size = _group_cost(meta, _matching_groups(meta, ts))
    return df, {"files_read": 1, "rows_read": rows, "bytes_read": size}


def write_single_files(workdir):
    """The same data as one file: with Parquet's default row groups, and with one row group per day."""
    dates = io.list_curated_dates(TABLE)
    frames = [pd.read_parquet(io.curated_fact_path(TABLE, d)) for d in dates]
    default_path = Path(workdir) / "all_default.parquet"
    pd.concat(frames, ignore_index=True).to_parquet(default_path, index=False, engine="pyarrow")
    tuned_path = Path(workdir) / "all_row_group_per_day.parquet"
    tables = [pa.Table.from_pandas(f, preserve_index=False) for f in frames]
    with pq.ParquetWriter(tuned_path, tables[0].schema) as writer:
        for t in tables:
            writer.write_table(t)          # one call = one row group = one day
    return default_path, tuned_path


# ---------------------------------------------------------------- strategies (raw CSV)

def raw_one_partition(p_date):
    path = io.raw_partition_path(p_date)
    df = io.read_raw_partition(p_date)
    return df, {"files_read": 1, "rows_read": len(df), "bytes_read": path.stat().st_size}


def raw_all_then_filter(p_date):
    dates = io.list_raw_partitions()
    df = pd.concat([io.read_raw_partition(d) for d in dates], ignore_index=True)
    size = sum(io.raw_partition_path(d).stat().st_size for d in dates)
    return df[df[KEY] == p_date], {"files_read": len(dates), "rows_read": len(df), "bytes_read": size}


# ---------------------------------------------------------------- measurement

def _canonical(df, key):
    return df.sort_values(key).reset_index(drop=True)


def measure(strategies, baseline, repeats, key):
    """
    strategies: list of (name, description, callable) -> (DataFrame, info).
    Raises AssertionError unless every strategy returns exactly the same rows.
    """
    records, reference = [], None
    for name, description, fn in strategies:
        seconds, (df, info) = median_seconds(fn, repeats)
        frame = _canonical(df, key)
        if reference is None:
            reference = frame
        else:
            pd.testing.assert_frame_equal(reference, frame, obj=f"result of '{name}'")
        records.append({"strategy": name, "description": description, "seconds": seconds,
                        "rows_returned": len(df), **info})
        log.info("%s: %.3fs, %d rows read from disk, %d returned", name, seconds, info["rows_read"], len(df))
    base = next(r for r in records if r["strategy"] == baseline)["seconds"]
    for r in records:
        r["speedup_vs_full_scan"] = base / r["seconds"] if r["seconds"] else None
    return records


def partition_stats():
    stats = []
    for d in io.list_curated_dates(TABLE):
        path = io.curated_fact_path(TABLE, d)
        stats.append({"p_date": d, "rows": pq.ParquetFile(path).metadata.num_rows, "bytes": path.stat().st_size})
    total = sum(s["rows"] for s in stats)
    for s in stats:
        s["share_of_rows"] = s["rows"] / total if total else 0.0
    return stats


def run(p_date=None, repeats=5, out_dir=None, workdir=None):
    dates = io.list_curated_dates(TABLE)
    if not dates:
        raise FileNotFoundError("no curated data found; run the pipeline first: "
                                "python scripts/run_pipeline.py --all --skip-load")
    p_date = io.check_p_date(p_date) if p_date else dates[len(dates) // 2]
    if p_date not in dates:
        raise ValueError(f"no curated partition for {p_date}; available: {dates}")

    out_dir = Path(out_dir) if out_dir else OUTPUTS_DIR / "benchmarks"
    own_workdir = workdir is None
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="partition_demo_"))
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        default_path, tuned_path = write_single_files(workdir)
        curated = measure([
            ("Partition read", "read only this day's file", lambda: read_one_partition(p_date)),
            ("Full scan + filter", "read every day's file, then filter", lambda: read_all_then_filter(p_date)),
            ("Single file, default row groups", "one Parquet file, pushed-down filter",
             lambda: read_single_file(p_date, default_path)),
            ("Single file, one row group per day", "one Parquet file, pushed-down filter",
             lambda: read_single_file(p_date, tuned_path)),
        ], baseline="Full scan + filter", repeats=repeats, key=EVENT_KEY)
        raw = None
        if p_date in io.list_raw_partitions():
            raw = measure([
                ("Raw CSV: one partition", "read only this day's CSV", lambda: raw_one_partition(p_date)),
                ("Raw CSV: read all, filter", "read every day's CSV, then filter", lambda: raw_all_then_filter(p_date)),
            ], baseline="Raw CSV: read all, filter", repeats=repeats, key=list(io.read_raw_partition(p_date).columns))
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    stats = partition_stats()
    sizes = [s["rows"] for s in stats]
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "p_date": p_date, "repeats": repeats,
              "machine": machine_info(), "identical_results": True,
              "partition_stats": stats, "skew_ratio": max(sizes) / min(sizes),
              "curated_parquet": curated, "raw_csv": raw}
    io.write_json(result, out_dir / "partition_demo.json")
    (out_dir / "partition_demo.md").write_text(render_markdown(result), encoding="utf-8")
    log.info("wrote %s", out_dir / "partition_demo.json")
    return result


# ---------------------------------------------------------------- reporting

def _strategy_table(records):
    lines = ["| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in records:
        lines.append(f"| {r['strategy']} | {r['seconds']:.3f} | {r['speedup_vs_full_scan']:.1f}x | {r['files_read']} "
                     f"| {r['rows_read']:,} | {r['rows_returned']:,} | {r['bytes_read'] / 1e6:.2f} MB |"
                     if r["bytes_read"] >= 1e6 else
                     f"| {r['strategy']} | {r['seconds']:.3f} | {r['speedup_vs_full_scan']:.1f}x | {r['files_read']} "
                     f"| {r['rows_read']:,} | {r['rows_returned']:,} | {r['bytes_read'] / 1e3:.0f} KB |")
    return lines


def render_markdown(result):
    lines = [f"### Partition sizes (`{TABLE}`, partition key `{KEY}`)", "",
             "| p_date | Rows | Share of rows | Parquet size |", "| --- | ---: | ---: | ---: |"]
    for s in result["partition_stats"]:
        lines.append(f"| {s['p_date']} | {s['rows']:,} | {s['share_of_rows']:.1%} | {s['bytes'] / 1e3:.0f} KB |")
    lines += ["", f"Largest / smallest partition: {result['skew_ratio']:.2f}x.", "",
              f"### Reading one day (`p_date={result['p_date']}`), curated Parquet", ""]
    lines += _strategy_table(result["curated_parquet"])
    if result["raw_csv"]:
        lines += ["", f"### Reading one day (`p_date={result['p_date']}`), raw CSV layer", ""]
        lines += _strategy_table(result["raw_csv"])
    lines += ["", "Bytes read: compressed column data for Parquet, file size for CSV.",
              "All strategies returned identical rows (checked before timing was reported).", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Show what reading one partition saves over scanning everything.")
    ap.add_argument("--date", help="partition to read, YYYYMMDD (default: the middle date)")
    ap.add_argument("--repeats", type=int, default=5, help="runs per measurement; the median is reported")
    ap.add_argument("--out", help="output directory (default: OUTPUTS_DIR/benchmarks)")
    args = ap.parse_args(argv)
    try:
        result = run(args.date, args.repeats, args.out)
    except (FileNotFoundError, ValueError) as e:
        log.error("%s", e)
        return 1
    print(render_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
