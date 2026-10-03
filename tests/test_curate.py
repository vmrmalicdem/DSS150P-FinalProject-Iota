import numpy as np
import pandas as pd
import pytest

import curate
import io_utils as io
import stage
from conftest import D1, D2, T0, write_raw_categories


def events(*rows):
    out = []
    for i, r in enumerate(rows):
        user, t, w, hour = r[:4]
        out.append({"user_id": user, "pid": 1000 + i, "exposed_time": t, "watch_time": w, "p_hour": hour,
                    "p_date": pd.Timestamp("2022-09-16"), "hate": r[4] if len(r) > 4 else False,
                    "is_rewatch_flagged": r[5] if len(r) > 5 else False})
    return pd.DataFrame(out)


def features(df, user=1):
    f = curate.compute_daily_features(df)
    return f[f["user_id"] == user].iloc[0]


# sessions

def test_two_sessions_when_the_gap_is_large():
    f = features(events((1, 1000, 100, 10), (1, 1500, 50, 10), (1, 5000, 30, 10)))
    assert f["n_sessions"] == 2
    assert f["max_session_seconds"] == 150      # 100 + 50
    assert f["avg_session_seconds"] == pytest.approx(90.0)   # (150 + 30) / 2


def test_gap_of_exactly_the_threshold_stays_in_one_session():
    # first view ends at 1100; next exposure at 2000 -> gap 900
    assert features(events((1, 1000, 100, 10), (1, 2000, 10, 10)))["n_sessions"] == 1


def test_gap_one_second_over_the_threshold_starts_a_new_session():
    assert features(events((1, 1000, 100, 10), (1, 2001, 10, 10)))["n_sessions"] == 2


def test_overlapping_views_use_the_running_maximum_end_time():
    # a long view (ends 6000) contains a short one; the 3rd event is only 500s after 6000
    f = features(events((1, 1000, 5000, 10), (1, 2000, 10, 10), (1, 6500, 5, 10)))
    assert f["n_sessions"] == 1


def test_sessions_are_computed_per_user():
    df = events((1, 1000, 10, 10), (2, 1001, 10, 10), (1, 1100, 10, 10), (2, 90000, 10, 10))
    f = curate.compute_daily_features(df).set_index("user_id")
    assert f.loc[1, "n_sessions"] == 1 and f.loc[2, "n_sessions"] == 2


# late night

@pytest.mark.parametrize("hour,late", [(1, False), (2, True), (3, True), (4, True), (5, False), (23, False)])
def test_late_night_window_is_inclusive_on_both_ends(hour, late):
    f = features(events((1, 1000, 60, hour)))
    assert f["late_night_events"] == (1 if late else 0)
    assert f["late_night_watch_seconds"] == (60 if late else 0)


def test_late_night_share_is_late_watch_over_total_watch():
    f = features(events((1, 1000, 30, 3), (1, 90000, 70, 12)))
    assert f["total_watch_seconds"] == 100
    assert f["late_night_share"] == pytest.approx(0.3)


def test_late_night_share_is_null_when_the_day_has_no_watch_time():
    f = features(events((1, 1000, 0, 3), (1, 90000, 0, 12)))
    assert np.isnan(f["late_night_share"])


# rates and counts

def test_hate_and_rewatch_rates():
    f = features(events((1, 1000, 10, 10, True, False), (1, 90000, 10, 10, False, True),
                        (1, 180000, 10, 10, False, True), (1, 270000, 10, 10, False, False)))
    assert f["n_events"] == 4
    assert f["hate_events"] == 1 and f["hate_rate"] == pytest.approx(0.25)
    assert f["rewatch_events"] == 2 and f["rewatch_rate"] == pytest.approx(0.5)


def test_one_row_per_user_with_expected_columns_and_types():
    f = curate.compute_daily_features(events((1, 1000, 10, 10), (2, 1000, 10, 10), (1, 1100, 10, 10)))
    assert len(f) == 2 and f["user_id"].is_unique
    assert list(f.columns)[:3] == ["user_id", "feature_date", "n_events"]
    assert str(f["n_events"].dtype) == "int64"
    assert (f["n_sessions"] >= 1).all()


def test_rates_stay_within_zero_and_one():
    f = curate.compute_daily_features(events((1, 1000, 10, 3, True, True), (2, 1000, 5, 10)))
    for c in ["hate_rate", "rewatch_rate", "late_night_share"]:
        assert f[c].dropna().between(0, 1).all()


# partitions and dimensions

def test_curate_requires_staged_data():
    with pytest.raises(FileNotFoundError):
        curate.build_dimensions()


def test_curated_partition_row_counts_reconcile(two_day_raw):
    stage.run(D1)
    stats = curate.curate_partition(D1)
    assert stats["interactions_curated"] == 4          # events, not raw rows
    assert stats["daily_user_features"] == 4           # users 1-4 each active once
    facts = pd.read_parquet(io.curated_fact_path("interactions_curated", D1))
    feats = pd.read_parquet(io.curated_fact_path("daily_user_features", D1))
    assert feats["n_events"].sum() == len(facts)


def test_dimensions_are_unique_and_cover_every_event(two_day_raw):
    stage.run(D1)
    stage.run(D2)
    curate.run(D1)
    curate.run(D2)
    users = pd.read_parquet(io.curated_dim_path("users"))
    videos = pd.read_parquet(io.curated_dim_path("videos"))
    cats = pd.read_parquet(io.curated_dim_path("categories"))
    vcat = pd.read_parquet(io.curated_dim_path("video_categories"))
    assert users["user_id"].is_unique and videos["pid"].is_unique and cats["category_id"].is_unique
    all_events = pd.concat([pd.read_parquet(io.staged_events_path(d)) for d in (D1, D2)])
    assert set(all_events["user_id"]) <= set(users["user_id"])
    assert set(all_events["pid"]) <= set(videos["pid"])
    assert set(vcat["category_id"]) <= set(cats["category_id"])


def test_transcript_flags_land_on_the_videos_dimension(two_day_raw):
    stage.run(D1)
    curate.run(D1)
    videos = pd.read_parquet(io.curated_dim_path("videos")).set_index("pid")
    assert bool(videos.loc[100, "has_transcript"]) is True
    assert videos.loc[100, "transcript_word_count"] == 4
    assert bool(videos.loc[101, "has_transcript"]) is False
    assert pd.isna(videos.loc[101, "transcript_word_count"])


def test_dimensions_do_not_depend_on_which_date_triggered_the_run(two_day_raw):
    stage.run(D1)
    stage.run(D2)
    curate.run(D1)
    curate.run(D2)
    after_both = pd.read_parquet(io.curated_dim_path("users"))
    curate.run(D1)  # rerun the earlier date
    pd.testing.assert_frame_equal(after_both, pd.read_parquet(io.curated_dim_path("users")))


def test_curating_twice_gives_identical_output(two_day_raw):
    stage.run(D1)
    curate.run(D1)
    a = pd.read_parquet(io.curated_fact_path("daily_user_features", D1))
    curate.run(D1)
    pd.testing.assert_frame_equal(a, pd.read_parquet(io.curated_fact_path("daily_user_features", D1)))
