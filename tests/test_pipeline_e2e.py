import csv

import pandas as pd
import pytest

import io_utils as io
import run_pipeline
import validate
from conftest import D1, D2, LAYER_DIRS, RAW_COLUMNS, make_row, two_day_rows

SRC = LAYER_DIRS["SOURCE_DATA_DIR"]


def write_sources():
    d1, d2 = two_day_rows()
    with open(SRC / "interaction_sampled.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(RAW_COLUMNS)
        for r in d1 + d2:
            w.writerow([r[c] for c in RAW_COLUMNS])
    with open(SRC / "categories_cn_en.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category_level", "category_id", "category_name_cn", "parent_id", "root_id", "category_name_en"])
        w.writerows([["1", "1", "美食", "1", "1", " food"], ["1", "2", "游戏", "2", "2", " games"],
                     ["2", "3", "做饭", "1", "1", " cooking"]])
    (SRC / "asr_en").mkdir(exist_ok=True)
    (SRC / "asr_en" / "100.txt").write_text("hello brave new world", encoding="utf-8")


def curated_snapshot():
    snap = {}
    for d in (D1, D2):
        for t in ("interactions_curated", "daily_user_features"):
            snap[(t, d)] = pd.read_parquet(io.curated_fact_path(t, d))
    for name in ("users", "videos", "categories", "video_categories"):
        snap[("dim", name)] = pd.read_parquet(io.curated_dim_path(name))
    return snap


@pytest.fixture
def full_run(monkeypatch):
    write_sources()
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--all", "--skip-load"])
    run_pipeline.main()


def test_first_run_ingests_when_raw_is_empty_then_produces_every_layer(full_run):
    assert io.list_raw_partitions() == [D1, D2]
    assert io.list_staged_dates() == [D1, D2]
    for d in (D1, D2):
        assert io.curated_fact_path("interactions_curated", d).exists()
        assert io.curated_fact_path("daily_user_features", d).exists()
    for name in ("users", "videos", "categories", "video_categories"):
        assert io.curated_dim_path(name).exists()


def test_validation_reports_exist_for_all_three_gates_and_both_dates(full_run):
    for gate in ("raw", "staged", "curated"):
        for d in (D1, D2):
            assert (LAYER_DIRS["STAGING_DATA_DIR"] / "_validation" / f"{gate}_{d}.json").exists()


def test_record_can_be_traced_from_raw_row_to_curated_event_and_feature(full_run):
    raw = io.read_raw_partition(D1)
    assert (raw["user_id"] == "1").sum() == 3                         # three tag rows in raw
    staged = pd.read_parquet(io.staged_events_path(D1))
    assert len(staged.query("user_id == 1 and pid == 100")) == 1       # one event in staging
    curated = pd.read_parquet(io.curated_fact_path("interactions_curated", D1))
    assert curated.query("user_id == 1 and pid == 100").iloc[0]["tag_count"] == 3
    feats = pd.read_parquet(io.curated_fact_path("daily_user_features", D1))
    assert feats.query("user_id == 1").iloc[0]["n_events"] == 1


def test_batch_id_links_curated_events_back_to_the_ingestion_log(full_run):
    curated = pd.read_parquet(io.curated_fact_path("interactions_curated", D1))
    log = (LAYER_DIRS["RAW_DATA_DIR"] / "_ingestion_log" / "ingestion_log.jsonl").read_text(encoding="utf-8")
    batch = curated["ingest_batch_id"].iloc[0]
    assert batch and batch in log


def test_events_are_never_double_counted_across_partitions(full_run):
    both = pd.concat([pd.read_parquet(io.curated_fact_path("interactions_curated", d)) for d in (D1, D2)])
    assert not both.duplicated(subset=["user_id", "pid", "exposed_time"]).any()
    assert len(both) == 6  # 4 + 2, the shared event counted once


def test_rerunning_the_whole_pipeline_produces_identical_curated_output(full_run, monkeypatch):
    before = curated_snapshot()
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--all", "--skip-load"])
    run_pipeline.main()
    after = curated_snapshot()
    assert before.keys() == after.keys()
    for key in before:
        pd.testing.assert_frame_equal(before[key], after[key], obj=str(key))


def test_rerunning_a_single_date_leaves_other_dates_untouched(full_run, monkeypatch):
    other = pd.read_parquet(io.curated_fact_path("daily_user_features", D2))
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--date", D1, "--skip-load"])
    run_pipeline.main()
    pd.testing.assert_frame_equal(other, pd.read_parquet(io.curated_fact_path("daily_user_features", D2)))


def test_bad_data_stops_the_pipeline_before_staging(monkeypatch):
    write_sources()
    monkeypatch.setattr("sys.argv", ["run_pipeline.py", "--date", D1, "--skip-load"])
    run_pipeline.ingest.main()
    path = io.raw_partition_path(D1)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.loc[0, "gender"] = "X"
    df.to_csv(path, index=False)
    with pytest.raises(validate.ValidationError, match="gender_accepted_values"):
        run_pipeline.run_date(D1, skip_load=True)
    assert io.list_staged_dates() == []   # nothing bad reached staging


def test_unknown_date_fails_with_a_clear_error(full_run):
    with pytest.raises(FileNotFoundError, match="20991231"):
        run_pipeline.run_date("20991231", skip_load=True)
