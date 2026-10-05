import csv
import json
import shutil

import pytest

import ingest
import io_utils as io
from conftest import D1, D2, LAYER_DIRS, RAW_COLUMNS, make_row

SRC = LAYER_DIRS["SOURCE_DATA_DIR"]


def write_source_interactions(rows, bom=True, extra_lines=()):
    path = SRC / "interaction_sampled.csv"
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(RAW_COLUMNS)
        for r in rows:
            w.writerow([r[c] for c in RAW_COLUMNS])
        for line in extra_lines:
            w.writerow(line)


def write_source_categories():
    with open(SRC / "categories_cn_en.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category_level", "category_id", "category_name_cn", "parent_id", "root_id", "category_name_en"])
        w.writerow(["1", "1", "美食", "1", "1", " food"])


def write_source_transcripts(n=2):
    d = SRC / "asr_en"
    d.mkdir(exist_ok=True)
    for i in range(1, n + 1):
        (d / f"{i}.txt").write_text(f"transcript number {i}", encoding="utf-8")


def ingest_log():
    path = LAYER_DIRS["RAW_DATA_DIR"] / "_ingestion_log" / "ingestion_log.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_rows_are_partitioned_by_p_date():
    write_source_interactions([make_row(p_date=D1), make_row(p_date=D1, user_id=2),
                               make_row(p_date=D2, user_id=3)])
    ingest.main()
    assert io.list_raw_partitions() == [D1, D2]
    assert len(io.read_raw_partition(D1)) == 2
    assert len(io.read_raw_partition(D2)) == 1


def test_bom_is_stripped_so_first_column_is_clean():
    write_source_interactions([make_row()], bom=True)
    ingest.main()
    assert io.read_raw_partition(D1).columns[0] == "user_id"


def test_commas_and_embedded_newlines_in_title_survive():
    nasty = 'line one, with comma\nline two "quoted"'
    write_source_interactions([make_row(title=nasty), make_row(title="plain", user_id=2)])
    ingest.main()
    titles = io.read_raw_partition(D1)["title"].tolist()
    assert nasty in titles and "plain" in titles
    assert len(titles) == 2  # the embedded newline did not split the row


def test_raw_values_are_kept_verbatim_as_text():
    write_source_interactions([make_row(duration="14.733", exposed_time="1663322400", fre_community_type="unknown")])
    ingest.main()
    row = io.read_raw_partition(D1).iloc[0]
    assert row["duration"] == "14.733" and row["fre_community_type"] == "unknown"


def test_malformed_rows_are_counted_not_fatal():
    write_source_interactions([make_row()], extra_lines=[["too", "short"]])
    ingest.main()
    events = [e for e in ingest_log() if e["source"] == "interaction_sampled.csv"]
    assert events[-1]["status"] == "OK_WITH_WARNINGS"
    assert json.loads(events[-1]["detail"])["malformed_rows_skipped"] == 1
    assert len(io.read_raw_partition(D1)) == 1


def test_all_five_sources_land_in_raw_and_are_logged():
    write_source_interactions([make_row()])
    write_source_categories()
    write_source_transcripts(3)
    ingest.main()
    raw = LAYER_DIRS["RAW_DATA_DIR"]
    assert (raw / "categories" / "categories_cn_en.csv").exists()
    assert len(io.raw_transcript_files()) == 3
    by_source = {e["source"]: e for e in ingest_log()}
    assert {"interaction_sampled.csv", "categories_cn_en.csv", "asr_en (transcripts)", "REST_API_Risk_Rules", "REST_API_Public_Holidays"}.issubset(set(by_source))
    # Note: we use issubset because network calls in CI might WARN instead of OK, but they shouldn't crash the pipeline.


def test_every_log_event_has_batch_id_and_timestamp_and_one_batch_per_run():
    write_source_interactions([make_row()])
    write_source_categories()
    ingest.main()
    events = ingest_log()
    assert all(e["batch_id"] and e["logged_at"] for e in events)
    assert len({e["batch_id"] for e in events}) == 1


def test_missing_individual_source_is_logged_and_does_not_stop_the_others():
    write_source_interactions([make_row()])  # no categories file, no transcripts
    ingest.main()
    statuses = {e["source"]: e["status"] for e in ingest_log()}
    assert statuses["categories_cn_en.csv"] == "MISSING"
    assert statuses["asr_en (transcripts)"] == "MISSING"
    assert statuses["interaction_sampled.csv"] == "OK"
    assert io.list_raw_partitions() == [D1]


def test_missing_source_directory_exits_non_zero_with_error_logged():
    shutil.rmtree(SRC)
    with pytest.raises(SystemExit) as exc:
        ingest.main()
    assert exc.value.code == 1
    assert ingest_log()[-1]["status"] == "ERROR"


def interaction_status():
    return [e for e in ingest_log() if e["source"] == "interaction_sampled.csv"][-1]["status"]


def test_empty_interaction_file_is_reported_as_error():
    (SRC / "interaction_sampled.csv").write_text("", encoding="utf-8")
    ingest.main()
    assert interaction_status() == "ERROR"
    assert io.list_raw_partitions() == []


def test_interaction_file_without_p_date_column_is_rejected():
    (SRC / "interaction_sampled.csv").write_text("user_id,pid\n1,2\n", encoding="utf-8")
    ingest.main()
    assert interaction_status() == "ERROR"
    assert io.list_raw_partitions() == []


def test_running_ingestion_twice_does_not_duplicate_rows():
    write_source_interactions([make_row(), make_row(user_id=2)])
    ingest.main()
    first = io.read_raw_partition(D1)
    ingest.main()
    second = io.read_raw_partition(D1)
    assert first.equals(second) and len(second) == 2
