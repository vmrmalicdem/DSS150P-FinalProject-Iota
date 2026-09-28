"""
short_video_risk_pipeline

One DAG run processes one date partition. The source is a static 7-day sample
(2022-09-16 to 2022-09-22), so the schedule is simulated: the run's logical date
selects the partition (p_date = YYYYMMDD of the logical date), and catchup
replays the week one day at a time. Trigger a single date manually with the
run config {"p_date": "20220918"}.

    ingest_raw -> validate_raw -> stage -> validate_staged
               -> curate -> validate_curated -> load_postgres

Failure handling
  - transient errors (I/O, database connection): retried 2 times, 1 minute apart
  - data-quality failures (ValidationError): fail immediately, no retry, because
    rerunning the same bad data cannot fix it
  - every failure is logged with the task, the run and the reason
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:  # Airflow 3
    from airflow.sdk import DAG
    from airflow.sdk.exceptions import AirflowFailException
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:  # Airflow 2
    from airflow import DAG
    from airflow.exceptions import AirflowFailException
    from airflow.operators.python import PythonOperator

SCRIPTS_DIR = os.environ.get("PIPELINE_SCRIPTS_DIR", str(Path(__file__).resolve().parents[1] / "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

log = logging.getLogger(__name__)


def _modules():
    """Import pipeline code lazily so DAG parsing stays fast and never touches data."""
    import curate, ingest, io_utils, load_postgres, stage, validate  # noqa: E401
    return curate, ingest, io_utils, load_postgres, stage, validate


def _guard(fn, p_date):
    """Run a stage; turn data-quality failures into non-retryable task failures."""
    validate = _modules()[5]
    try:
        return fn(p_date)
    except validate.ValidationError as e:
        raise AirflowFailException(str(e)) from e


def ingest_raw(p_date):
    _, ingest, io_utils, *_ = _modules()
    if io_utils.raw_partition_exists(p_date):
        log.info("raw partition %s already exists; raw data is immutable, skipping ingestion", p_date)
        return
    log.info("raw partition %s missing; running ingestion of the source files", p_date)
    ingest.main()
    if not io_utils.raw_partition_exists(p_date):
        raise AirflowFailException(f"ingestion finished but raw partition {p_date} does not exist "
                                   f"(is it outside the source file's date range?)")


def validate_raw(p_date):
    _guard(_modules()[5].run_raw, p_date)


def stage_task(p_date):
    _modules()[4].run(p_date)


def validate_staged(p_date):
    _guard(_modules()[5].run_staged, p_date)


def curate_task(p_date):
    _modules()[0].run(p_date)


def validate_curated(p_date):
    _guard(_modules()[5].run_curated, p_date)


def load_postgres(p_date):
    _modules()[3].run(p_date)


def _on_failure(context):
    ti = context.get("task_instance")
    log.error("TASK FAILED dag=%s task=%s run=%s reason=%r", getattr(ti, "dag_id", "?"),
              getattr(ti, "task_id", "?"), context.get("run_id"), context.get("exception"))


default_args = {
    "owner": "data-eng-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": _on_failure,
}

P_DATE = "{{ dag_run.conf.get('p_date') or ds_nodash }}"

with DAG(
    dag_id="short_video_risk_pipeline",
    description="Raw -> staging -> curated -> PostgreSQL for one date partition of the short-video sample",
    start_date=datetime(2022, 9, 16),
    end_date=datetime(2022, 9, 22),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    default_args=default_args,
    tags=["data-engineering", "short-video", "well-being-risk"],
    doc_md=__doc__,
) as dag:
    tasks = []
    for task_id, fn in [
        ("ingest_raw", ingest_raw),
        ("validate_raw", validate_raw),
        ("stage", stage_task),
        ("validate_staged", validate_staged),
        ("curate", curate_task),
        ("validate_curated", validate_curated),
        ("load_postgres", load_postgres),
    ]:
        tasks.append(PythonOperator(task_id=task_id, python_callable=fn, op_kwargs={"p_date": P_DATE}))

    for upstream, downstream in zip(tasks, tasks[1:]):
        upstream >> downstream
