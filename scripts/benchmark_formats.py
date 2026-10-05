import argparse
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import pandas as pd

import io_utils as io
from bench_utils import machine_info, median_seconds
from config import OUTPUTS_DIR, get_logger

log = get_logger("benchmark_formats")

SUBSET_COLUMNS = ["user_id", "p_date", "watch_time"]


@dataclass(frozen=True)
class Format:
    name: str
    ext: str
    write: Callable      # (df, path) -> None
    read: Callable       # (path, columns or None) -> DataFrame


def _read_json(path, columns, lines):
    # convert_dates=False: by default pandas guesses dates from column NAMES (e.g. anything ending in
    # "_time") and silently turns plausible-looking integers into datetimes. exposed_time, a Unix
    # timestamp stored as an integer, is converted that way. Switching it off keeps the comparison honest.
    df = pd.read_json(str(path), orient="records", lines=lines, convert_dates=False)
    return df[columns] if columns else df


FORMATS = [
    Format("CSV", "csv",
           lambda df, p: df.to_csv(p, index=False),
           lambda p, cols: pd.read_csv(p, usecols=cols)),
    Format("CSV (gzip)", "csv.gz",
           lambda df, p: df.to_csv(p, index=False),
           lambda p, cols: pd.read_csv(p, usecols=cols)),
    Format("JSON (array)", "json",
           lambda df, p: df.to_json(p, orient="records", force_ascii=False),
           lambda p, cols: _read_json(p, cols, lines=False)),
    Format("JSON Lines", "jsonl",
           lambda df, p: df.to_json(p, orient="records", lines=True, force_ascii=False),
           lambda p, cols: _read_json(p, cols, lines=True)),
    Format("Parquet (snappy)", "snappy.parquet",
           lambda df, p: df.to_parquet(p, index=False, engine="pyarrow", compression="snappy"),
           lambda p, cols: pd.read_parquet(p, columns=cols)),
    Format("Parquet (zstd)", "zstd.parquet",
           lambda df, p: df.to_parquet(p, index=False, engine="pyarrow", compression="zstd"),
           lambda p, cols: pd.read_parquet(p, columns=cols)),
]


def fidelity(original, loaded):
    out = {"exact": [], "dtype_changed": {}, "value_changed": {}, "missing": []}
    for col in original.columns:
        if col not in loaded.columns:
            out["missing"].append(col)
        elif str(original[col].dtype) != str(loaded[col].dtype):
            out["dtype_changed"][col] = f"{original[col].dtype} -> {loaded[col].dtype}"
        elif original[col].equals(loaded[col]):
            out["exact"].append(col)
        else:
            diff = None
            if pd.api.types.is_numeric_dtype(original[col]):
                diff = float((original[col].astype("float64") - loaded[col].astype("float64")).abs().max())
            out["value_changed"][col] = diff
    return out


def benchmark_dataframe(name, df, workdir, repeats=3, columns=None):
    df = df.reset_index(drop=True)
    columns = columns or [c for c in SUBSET_COLUMNS if c in df.columns]
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for fmt in FORMATS:
        path = workdir / f"{name}.{fmt.ext}"
        write_s, _ = median_seconds(lambda: fmt.write(df, path), repeats)
        size = path.stat().st_size
        read_s, loaded = median_seconds(lambda: fmt.read(path, None), repeats)
        cols_s, _ = median_seconds(lambda: fmt.read(path, columns), repeats)
        fid = fidelity(df, loaded)
        rows.append({
            "format": fmt.name, "size_bytes": size,
            "write_seconds": write_s, "read_all_seconds": read_s, "read_columns_seconds": cols_s,
            "columns_exact": len(fid["exact"]), "columns_total": len(df.columns),
            "dtype_changed": fid["dtype_changed"], "value_changed": fid["value_changed"],
            "missing": fid["missing"],
        })
        log.info("%s / %s: %.1f MB, write %.2fs, read %.2fs, 3-col read %.2fs, %d/%d columns exact",
                 name, fmt.name, size / 1e6, write_s, read_s, cols_s, len(fid["exact"]), len(df.columns))
        path.unlink(missing_ok=True)
    return {"dataset": name, "rows": len(df), "columns": len(df.columns),
            "subset_columns": columns, "formats": rows}


# ---------------------------------------------------------------- datasets

def load_curated():
    dates = io.list_curated_dates("interactions_curated")
    if not dates:
        raise FileNotFoundError("no curated data found; run the pipeline first: "
                                "python scripts/run_pipeline.py --all --skip-load")
    return pd.concat([pd.read_parquet(io.curated_fact_path("interactions_curated", d)) for d in dates],
                     ignore_index=True)


def load_staged():
    dates = io.list_staged_dates()
    if not dates:
        raise FileNotFoundError("no staged data found; run the pipeline first: "
                                "python scripts/run_pipeline.py --all --skip-load")
    return pd.concat([pd.read_parquet(io.staged_events_path(d)) for d in dates], ignore_index=True)


DATASETS = {"curated": load_curated, "staged": load_staged}


# ---------------------------------------------------------------- reporting

def render_markdown(result):
    lines = []
    for ds in result["datasets"]:
        csv_row = next(r for r in ds["formats"] if r["format"] == "CSV")
        lines += [f"### `{ds['dataset']}` dataset: {ds['rows']:,} rows x {ds['columns']} columns", "",
                  "| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for r in ds["formats"]:
            lines.append(
                f"| {r['format']} | {r['size_bytes'] / 1e6:.1f} | {r['size_bytes'] / csv_row['size_bytes']:.2f}x "
                f"| {r['write_seconds']:.3f} | {r['read_all_seconds']:.3f} | {r['read_columns_seconds']:.3f} "
                f"| {csv_row['read_all_seconds'] / r['read_all_seconds']:.1f}x "
                f"| {csv_row['read_columns_seconds'] / r['read_columns_seconds']:.1f}x "
                f"| {r['columns_exact']}/{r['columns_total']} |")
        lines.append("")
        lines += ["Round-trip differences (read back with default settings):", ""]
        for r in ds["formats"]:
            parts = []
            if r["dtype_changed"]:
                parts.append("dtype changed: " + ", ".join(f"`{c}` ({v})" for c, v in r["dtype_changed"].items()))
            if r["value_changed"]:
                parts.append("values changed: " + ", ".join(
                    f"`{c}`" + (f" (max abs diff {d:.2e})" if d is not None else "")
                    for c, d in r["value_changed"].items()))
            if r["missing"]:
                parts.append("missing: " + ", ".join(f"`{c}`" for c in r["missing"]))
            lines.append(f"- **{r['format']}**: " + ("; ".join(parts) if parts else "all columns identical"))
        lines.append("")
    return "\n".join(lines)


def run(datasets=("curated", "staged"), repeats=3, out_dir=None, workdir=None):
    out_dir = Path(out_dir) if out_dir else OUTPUTS_DIR / "benchmarks"
    own_workdir = workdir is None
    workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="format_benchmark_"))
    try:
        results = []
        for name in datasets:
            log.info("loading dataset %s", name)
            results.append(benchmark_dataframe(name, DATASETS[name](), workdir, repeats))
    finally:
        if own_workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "repeats": repeats,
              "machine": machine_info(), "datasets": results}
    io.write_json(result, out_dir / "format_comparison.json")
    (out_dir / "format_comparison.md").write_text(render_markdown(result), encoding="utf-8")
    log.info("wrote %s", out_dir / "format_comparison.json")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare CSV, JSON and Parquet on the pipeline's own data.")
    ap.add_argument("--dataset", choices=[*DATASETS, "both"], default="both")
    ap.add_argument("--repeats", type=int, default=3, help="runs per measurement; the median is reported")
    ap.add_argument("--out", help="output directory (default: OUTPUTS_DIR/benchmarks)")
    args = ap.parse_args(argv)
    names = tuple(DATASETS) if args.dataset == "both" else (args.dataset,)
    try:
        result = run(names, args.repeats, args.out)
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1
    print(render_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
