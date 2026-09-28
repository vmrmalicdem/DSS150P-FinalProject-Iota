"""
Run the pipeline without Airflow, using the same stage functions the DAG calls.

    py scripts/run_pipeline.py --date 20220916
    py scripts/run_pipeline.py --all
    py scripts/run_pipeline.py --all --skip-load     (no PostgreSQL needed)
"""

import argparse
import sys

import curate
import ingest
import io_utils as io
import load_postgres
import stage
import validate
from config import get_logger

log = get_logger("run_pipeline")


def run_date(p_date, skip_load=False):
    log.info("=== pipeline start for p_date=%s ===", p_date)
    validate.run_raw(p_date)
    stage.run(p_date)
    validate.run_staged(p_date)
    curate.run(p_date)
    validate.run_curated(p_date)
    if not skip_load:
        load_postgres.run(p_date)
    log.info("=== pipeline done for p_date=%s ===", p_date)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="one partition, YYYYMMDD")
    g.add_argument("--all", action="store_true", help="every raw partition, oldest first")
    ap.add_argument("--skip-load", action="store_true", help="stop after curation")
    args = ap.parse_args()

    if not io.list_raw_partitions():
        log.info("no raw partitions found, running ingestion first")
        ingest.main()

    dates = io.list_raw_partitions() if args.all else [io.check_p_date(args.date)]
    for d in dates:
        run_date(d, skip_load=args.skip_load)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - top-level: log the reason, then exit non-zero
        log.error("pipeline failed: %s: %s", type(e).__name__, e)
        sys.exit(1)
