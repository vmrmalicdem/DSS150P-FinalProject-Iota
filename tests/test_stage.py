import pandas as pd
import pytest

import io_utils as io
import stage
from conftest import D1, D2, LAYER_DIRS, T0, make_row, write_raw_categories, write_raw_partition, write_raw_transcripts


def staged(p_date):
    return pd.read_parquet(io.staged_events_path(p_date))


# events

def test_exact_duplicate_rows_are_dropped(two_day_raw):
    stats = stage.stage_partition(D1)
    assert stats["raw_rows"] == 7
    assert stats["exact_duplicate_rows_dropped"] == 1
    ev = staged(D1)
    assert len(ev[ev["user_id"] == 2]) == 1


def test_tag_fan_out_collapses_to_one_event_with_tag_count(two_day_raw):
    stage.stage_partition(D1)
    ev = staged(D1)
    fanned = ev[(ev["user_id"] == 1) & (ev["pid"] == 100)]
    assert len(fanned) == 1
    assert fanned.iloc[0]["tag_count"] == 3


def test_tag_count_is_the_number_of_distinct_tags_not_rows():
    # same tag name under two category ids: 2 raw rows, 1 distinct tag, but both categories are kept
    t = T0
    write_raw_partition([make_row(category_id=1, tag_name="same", exposed_time=t),
                         make_row(category_id=2, tag_name="same", exposed_time=t)], D1)
    stage.stage_partition(D1)
    assert staged(D1).iloc[0]["tag_count"] == 1
    vc = pd.read_parquet(io.staged_video_categories_path(D1))
    assert sorted(vc["category_id"]) == [1, 2]


def test_event_key_is_unique_after_staging(two_day_raw):
    stage.stage_partition(D1)
    assert not staged(D1).duplicated(subset=["user_id", "pid", "exposed_time"]).any()


def test_video_categories_keep_every_tag_as_a_bridge_row(two_day_raw):
    stage.stage_partition(D1)
    vc = pd.read_parquet(io.staged_video_categories_path(D1))
    assert sorted(vc.loc[vc["pid"] == 100, "category_id"]) == [1, 2, 3]
    assert not vc.duplicated().any()


def test_category_columns_are_not_carried_on_the_event_rows(two_day_raw):
    stage.stage_partition(D1)
    assert not {"category_id", "category_level", "parent_id", "root_id", "tag_name"} & set(staged(D1).columns)


def test_cross_partition_event_belongs_only_to_the_earliest_partition(two_day_raw):
    s1 = stage.stage_partition(D1)
    s2 = stage.stage_partition(D2)
    assert s1["events_owned_by_earlier_partition"] == 0
    assert s2["events_owned_by_earlier_partition"] == 1
    day1 = staged(D1)
    day2 = staged(D2)
    shared = day1[(day1["user_id"] == 1) & (day1["pid"] == 100)]
    assert len(shared) == 1
    assert day2[(day2["user_id"] == 1) & (day2["exposed_time"] == T0)].empty
    both = pd.concat([day1, day2])
    assert not both.duplicated(subset=["user_id", "pid", "exposed_time"]).any()


def test_staged_event_counts_match_expectation(two_day_raw):
    assert stage.stage_partition(D1)["staged_events"] == 4
    assert stage.stage_partition(D2)["staged_events"] == 2


def test_columns_are_properly_typed(two_day_raw):
    stage.stage_partition(D1)
    ev = staged(D1)
    for c in ["user_id", "pid", "exposed_time", "watch_time", "p_hour", "age"]:
        assert str(ev[c].dtype) == "int64", c
    assert str(ev["duration"].dtype) == "float64"
    for c in ["cvm_like", "click", "comment", "follow", "collect", "forward", "hate"]:
        assert str(ev[c].dtype) == "bool", c
    assert pd.api.types.is_datetime64_any_dtype(ev["p_date"])


def test_rewatch_is_flagged_and_never_capped_or_dropped(two_day_raw):
    stage.stage_partition(D1)
    ev = staged(D1)
    row = ev[ev["user_id"] == 3].iloc[0]
    assert bool(row["is_rewatch_flagged"]) is True
    assert row["watch_time"] == 40            # not capped to the 20s duration
    assert row["watch_ratio"] == pytest.approx(2.0)
    assert ev["is_rewatch_flagged"].sum() == 1


def test_watch_equal_to_duration_is_not_a_rewatch():
    write_raw_partition([make_row(watch_time=20, duration=20.0)], D1)
    write_raw_categories()
    stage.stage_partition(D1)
    row = staged(D1).iloc[0]
    assert bool(row["is_rewatch_flagged"]) is False and row["watch_ratio"] == pytest.approx(1.0)


def test_unknown_is_preserved_as_a_value_not_imputed(two_day_raw):
    stage.stage_partition(D1)
    row = staged(D1).query("user_id == 4").iloc[0]
    assert row["fre_community_type"] == "unknown" and row["fre_city_level"] == "unknown"


def test_conflicting_rows_for_one_event_resolve_deterministically():
    t = T0
    rows = [make_row(category_id=1, tag_name="a", p_hour=11, title="zeta", exposed_time=t),
            make_row(category_id=2, tag_name="b", p_hour=9, title="alpha", exposed_time=t)]
    write_raw_partition(rows, D1)
    stage.stage_partition(D1)
    first = staged(D1).iloc[0]
    write_raw_partition(list(reversed(rows)), D1)
    stage.stage_partition(D1)
    second = staged(D1).iloc[0]
    assert (first["p_hour"], first["title"]) == (second["p_hour"], second["title"]) == (9, "alpha")


def test_restaging_the_same_partition_is_idempotent(two_day_raw):
    stage.stage_partition(D1)
    a = staged(D1).drop(columns="staged_at")
    stage.stage_partition(D1)
    b = staged(D1).drop(columns="staged_at")
    pd.testing.assert_frame_equal(a, b)


def test_staging_a_partition_that_was_never_ingested_fails_clearly():
    with pytest.raises(FileNotFoundError, match="20220916"):
        stage.stage_partition(D1)


def test_staging_rejects_a_malformed_date():
    with pytest.raises(ValueError):
        stage.stage_partition("2022-09-16")


def test_stats_file_is_written(two_day_raw):
    stage.stage_partition(D1)
    assert (LAYER_DIRS["STAGING_DATA_DIR"] / "_stats" / f"stage_{D1}.json").exists()


# ---------------- category lookup ----------------

def test_category_labels_are_stripped_of_the_leading_space():
    write_raw_categories()
    stage.stage_categories()
    cats = pd.read_parquet(io.STAGED_CATEGORIES_PATH)
    assert "food" in cats["category_name_en"].tolist()
    assert not cats["category_name_en"].str.startswith(" ").any()


def test_duplicate_category_ids_keep_first_row_and_are_flagged():
    write_raw_categories([
        ("1", "7", "舞蹈", "1", "1", " dance"),
        ("1", "7", "舞蹈", "1", "1", " dancing"),
        ("1", "8", "音乐", "2", "2", " music"),
    ])
    stage.stage_categories()
    cats = pd.read_parquet(io.STAGED_CATEGORIES_PATH).set_index("category_id")
    assert cats.index.is_unique and len(cats) == 2
    assert cats.loc[7, "category_name_en"] == "dance"          # first occurrence in file order
    assert bool(cats.loc[7, "en_label_ambiguous"]) is True
    assert bool(cats.loc[8, "en_label_ambiguous"]) is False


def test_category_ids_are_integers():
    write_raw_categories()
    stage.stage_categories()
    assert str(pd.read_parquet(io.STAGED_CATEGORIES_PATH)["category_id"].dtype) == "int64"


# transcripts

def test_transcript_word_count_and_pid_from_filename():
    write_raw_transcripts({"100": "one two three", "101": "single"})
    stage.stage_transcripts()
    t = pd.read_parquet(io.STAGED_TRANSCRIPTS_PATH).set_index("pid")
    assert t.loc[100, "transcript_word_count"] == 3
    assert t.loc[101, "transcript_word_count"] == 1
    assert t["has_transcript"].all()


def test_transcripts_with_non_numeric_names_are_skipped():
    write_raw_transcripts({"100": "ok", "notes": "ignore me"})
    stage.stage_transcripts()
    assert pd.read_parquet(io.STAGED_TRANSCRIPTS_PATH)["pid"].tolist() == [100]


def test_no_transcripts_yields_an_empty_typed_table():
    stage.stage_transcripts()
    t = pd.read_parquet(io.STAGED_TRANSCRIPTS_PATH)
    assert t.empty and str(t["pid"].dtype) == "int64"
