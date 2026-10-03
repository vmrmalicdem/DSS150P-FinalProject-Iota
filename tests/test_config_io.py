import json
import os

import pandas as pd
import pytest

import config
import io_utils as io
from conftest import LAYER_DIRS, ROOT


# config

def test_relative_paths_resolve_against_repo_root_not_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOME_DIR", "relative/place")
    assert config._path("SOME_DIR", "unused") == (ROOT / "relative/place").resolve()


def test_absolute_paths_are_kept_as_is(monkeypatch, tmp_path):
    monkeypatch.setenv("SOME_DIR", str(tmp_path))
    assert config._path("SOME_DIR", "unused") == tmp_path


def test_dotenv_never_overrides_real_environment(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nFROM_FILE=file_value\nALREADY_SET=file_value\nnot a pair\n", encoding="utf-8")
    monkeypatch.setenv("ALREADY_SET", "env_value")
    monkeypatch.delenv("FROM_FILE", raising=False)
    config._load_dotenv(env_file)
    assert os.environ["FROM_FILE"] == "file_value"
    assert os.environ["ALREADY_SET"] == "env_value"
    monkeypatch.delenv("FROM_FILE", raising=False)


def test_missing_dotenv_is_not_an_error(tmp_path):
    config._load_dotenv(tmp_path / "does-not-exist.env")


def test_feature_thresholds_are_pinned_for_tests():
    assert (config.LATE_NIGHT_START_HOUR, config.LATE_NIGHT_END_HOUR) == (2, 4)
    assert config.SESSION_GAP_SECONDS == 900
    assert config.EVENT_KEY == ["user_id", "pid", "exposed_time"]


def test_postgres_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_HOST", "db.example")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    s = config.postgres_settings()
    assert s["host"] == "db.example" and s["port"] == 6543


# io_utils

@pytest.mark.parametrize("good", ["20220916", 20220916])
def test_check_p_date_accepts_yyyymmdd(good):
    assert io.check_p_date(good) == "20220916"


@pytest.mark.parametrize("bad", ["2022-09-16", "", "2022091", "202209160", "abcdefgh", None])
def test_check_p_date_rejects_everything_else(bad):
    with pytest.raises(ValueError, match="YYYYMMDD"):
        io.check_p_date(bad)


def test_list_raw_partitions_is_sorted_and_empty_safe():
    assert io.list_raw_partitions() == []
    for d in ("20220918", "20220916", "20220917"):
        (LAYER_DIRS["RAW_DATA_DIR"] / "interactions" / f"p_date={d}").mkdir(parents=True)
    assert io.list_raw_partitions() == ["20220916", "20220917", "20220918"]


def test_reading_a_missing_raw_partition_names_the_path():
    with pytest.raises(FileNotFoundError, match="20220916"):
        io.read_raw_partition("20220916")


def test_write_parquet_is_atomic_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "nested" / "out.parquet"
    df = pd.DataFrame({"a": [1, 2, 3]})
    io.write_parquet(df, target)
    assert pd.read_parquet(target).equals(df)
    assert [p.name for p in target.parent.iterdir()] == ["out.parquet"]


def test_write_parquet_overwrite_replaces_content(tmp_path):
    target = tmp_path / "out.parquet"
    io.write_parquet(pd.DataFrame({"a": [1]}), target)
    io.write_parquet(pd.DataFrame({"a": [9, 9]}), target)
    assert len(pd.read_parquet(target)) == 2


def test_write_json_keeps_unicode_readable(tmp_path):
    target = tmp_path / "x.json"
    io.write_json({"label": "美食"}, target)
    assert "美食" in target.read_text(encoding="utf-8")


def test_latest_ingest_batch_id_uses_last_successful_event():
    log = LAYER_DIRS["RAW_DATA_DIR"] / "_ingestion_log" / "ingestion_log.jsonl"
    log.parent.mkdir(parents=True)
    lines = [
        json.dumps({"source": "interaction_sampled.csv", "status": "OK", "batch_id": "first"}),
        "this line is not json",
        json.dumps({"source": "interaction_sampled.csv", "status": "OK_WITH_WARNINGS", "batch_id": "second"}),
        json.dumps({"source": "interaction_sampled.csv", "status": "ERROR", "batch_id": "failed"}),
        json.dumps({"source": "categories_cn_en.csv", "status": "OK", "batch_id": "other-source"}),
    ]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert io.latest_ingest_batch_id() == "second"


def test_latest_ingest_batch_id_is_none_without_a_log():
    assert io.latest_ingest_batch_id() is None
