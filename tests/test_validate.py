import json

import pandas as pd
import pytest

import curate
import io_utils as io
import stage
import validate
from conftest import (D1, D2, LAYER_DIRS, RAW_COLUMNS, T0, make_row, raw_frame, write_raw_categories,
                      write_raw_partition, write_raw_transcripts)


def report(stage_name, p_date):
    path = LAYER_DIRS["STAGING_DATA_DIR"] / "_validation" / f"{stage_name}_{p_date}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def checks(stage_name, p_date):
    return {c["name"]: c for c in report(stage_name, p_date)["checks"]}


def rewrite_raw(p_date, fn):
    df = io.read_raw_partition(p_date)
    fn(df)
    df.to_csv(io.raw_partition_path(p_date), index=False, encoding="utf-8")


def assert_gate_fails(check_name, p_date=D1):
    with pytest.raises(validate.ValidationError, match=check_name):
        validate.run_raw(p_date)
    c = checks("raw", p_date)[check_name]
    assert c["passed"] is False and c["severity"] == "ERROR"


# ---------------- raw gate: happy path and reporting ----------------

def test_clean_raw_partition_passes_every_error_check(two_day_raw):
    summary = validate.run_raw(D1)
    assert summary["errors"] == 0
    assert summary["checks_run"] >= 17


def test_at_least_five_distinct_check_types_are_exercised(two_day_raw):
    validate.run_raw(D1)
    types = {c["check_type"] for c in report("raw", D1)["checks"]}
    assert len(types) >= 5
    assert {"schema", "nullability", "datatype", "range", "accepted_values", "referential_integrity"} <= types


def test_validation_report_json_is_written_with_counts(two_day_raw):
    validate.run_raw(D1)
    r = report("raw", D1)
    assert r["stage"] == "raw" and r["p_date"] == D1
    assert r["checks_run"] == len(r["checks"]) == r["passed"] + r["warnings"] + r["errors"]


def test_missing_partition_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        validate.run_raw(D1)


# ---------------- raw gate: schema ----------------

def test_missing_column_fails_schema_check(two_day_raw):
    rewrite_raw(D1, lambda df: df.drop(columns=["hate"], inplace=True))
    assert_gate_fails("schema_columns")


def test_unexpected_extra_column_fails_schema_check(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("surprise", "x"))
    assert_gate_fails("schema_columns")


def test_empty_partition_fails(two_day_raw):
    raw_frame([]).to_csv(io.raw_partition_path(D1), index=False)
    with pytest.raises(validate.ValidationError, match="partition_not_empty"):
        validate.run_raw(D1)


# ---------------- raw gate: nullability, datatypes ----------------

def test_empty_value_fails_nullability(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("age", df["age"].where(df.index != 0, "")))
    assert_gate_fails("required_fields_not_null")


def test_non_numeric_integer_column_fails_datatype(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("watch_time", df["watch_time"].where(df.index != 0, "ten")))
    assert_gate_fails("column_datatypes")


def test_non_boolean_flag_fails_datatype(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("hate", df["hate"].where(df.index != 0, "maybe")))
    assert_gate_fails("column_datatypes")


def test_non_numeric_duration_fails_datatype(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("duration", df["duration"].where(df.index != 0, "long")))
    assert_gate_fails("column_datatypes")


# raw gate: ranges

@pytest.mark.parametrize("col,value,check", [
    ("p_hour", "24", "p_hour_0_23"),
    ("age", "9", "age_in_range"),
    ("age", "101", "age_in_range"),
    ("watch_time", "-1", "watch_time_non_negative"),
    ("duration", "0", "duration_positive"),
    ("mod_price", "-5", "mod_price_non_negative"),
    ("exposed_time", "0", "exposed_time_positive"),
])
def test_out_of_range_values_fail(two_day_raw, col, value, check):
    rewrite_raw(D1, lambda df: df.__setitem__(col, df[col].where(df.index != 0, value)))
    assert_gate_fails(check)


def test_boundary_values_are_accepted(two_day_raw):
    def edit(df):  # user 4 has exactly one row, so no per-user consistency conflict
        df.loc[df["user_id"] == "4", ["p_hour", "age", "watch_time", "mod_price"]] = ["23", "100", "0", "0"]
    rewrite_raw(D1, edit)
    assert validate.run_raw(D1)["errors"] == 0


# raw gate: accepted values, consistency

@pytest.mark.parametrize("col,value,check", [
    ("gender", "X", "gender_accepted_values"),
    ("fre_community_type", "suburb", "fre_community_type_accepted_values"),
    ("fre_city_level", "六线城市", "fre_city_level_accepted_values"),
])
def test_unexpected_category_values_fail(two_day_raw, col, value, check):
    rewrite_raw(D1, lambda df: df.__setitem__(col, df[col].where(df.index != 0, value)))
    assert_gate_fails(check)


def test_unknown_is_an_accepted_value_not_a_failure(two_day_raw):
    # user 4 in the fixture already carries 'unknown' for both fields
    assert validate.run_raw(D1)["errors"] == 0


def test_rows_outside_the_partition_date_fail(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("p_date", df["p_date"].where(df.index != 0, D2)))
    assert_gate_fails("p_date_matches_partition")


def test_conflicting_user_attributes_fail(two_day_raw):
    # make user 1's rows disagree on gender inside one partition
    def edit(df):
        df.loc[df.index[df["user_id"] == "1"][0], "gender"] = "F"
    rewrite_raw(D1, edit)
    assert_gate_fails("user_attributes_consistent")


# raw gate: referential integrity, uniqueness, duplicates, warnings

def test_category_id_missing_from_lookup_fails_referential_integrity(two_day_raw):
    rewrite_raw(D1, lambda df: df.__setitem__("category_id", df["category_id"].where(df.index != 0, "999")))
    assert_gate_fails("category_id_in_lookup")


def test_duplicate_category_lookup_ids_warn_but_do_not_fail(two_day_raw):
    write_raw_categories([("1", "1", "美食", "1", "1", " food"), ("1", "1", "美食", "1", "1", " cuisine"),
                          ("1", "2", "游戏", "2", "2", " games"), ("2", "3", "做饭", "1", "1", " cooking")])
    summary = validate.run_raw(D1)
    assert summary["errors"] == 0 and summary["warnings"] == 1
    c = checks("raw", D1)["category_lookup_unique_ids"]
    assert c["passed"] is False and c["severity"] == "WARN"


def test_high_exact_duplicate_share_warns_but_does_not_fail():
    rows = [make_row()] * 8 + [make_row(user_id=2, exposed_time=1)] * 2
    write_raw_partition(rows, D1)
    write_raw_categories()
    write_raw_transcripts()
    summary = validate.run_raw(D1)
    assert summary["errors"] == 0
    assert checks("raw", D1)["exact_duplicate_share"]["passed"] is False


def test_no_transcript_files_fails_coverage(two_day_raw):
    for f in io.raw_transcript_files():
        f.unlink()
    assert_gate_fails("transcript_files_present")


def test_multiple_failures_are_all_reported_in_one_exception(two_day_raw):
    def edit(df):
        df.loc[0, "p_hour"] = "30"
        df.loc[0, "gender"] = "X"
    rewrite_raw(D1, edit)
    with pytest.raises(validate.ValidationError) as exc:
        validate.run_raw(D1)
    assert "p_hour_0_23" in str(exc.value) and "gender_accepted_values" in str(exc.value)


# staged gate

def staged_rewatch_total(p_date):
    return int(pd.read_parquet(io.staged_events_path(p_date))["is_rewatch_flagged"].sum())


def stage_clean():
    stage.run(D1)
    return D1


def test_clean_staged_partition_passes(two_day_raw):
    stage_clean()
    assert validate.run_staged(D1)["errors"] == 0


def test_staged_gate_covers_reconciliation_and_business_rules(two_day_raw):
    stage_clean()
    validate.run_staged(D1)
    types = {c["check_type"] for c in report("staged", D1)["checks"]}
    assert {"uniqueness", "reconciliation", "nullability", "range", "business_rule", "referential_integrity"} <= types


def test_staged_gate_for_a_later_partition_accounts_for_cross_partition_ownership(two_day_raw):
    stage.run(D1)
    stage.run(D2)
    assert validate.run_staged(D2)["errors"] == 0


def test_partition_with_zero_rewatch_events_passes_the_gate(two_day_raw):
    """Regression: a quiet later partition (no rewatch events) used to fail spuriously."""
    stage.run(D1)
    stage.run(D2)
    assert staged_rewatch_total(D2) == 0
    assert validate.run_staged(D2)["errors"] == 0


def test_unknown_only_owned_by_an_earlier_partition_does_not_fail_a_later_one():
    """Regression: the cross-partition 'unknown' event must not be expected in the later partition."""
    unknown = dict(fre_community_type="unknown", fre_city_level="unknown")
    write_raw_partition([make_row(user_id=4, pid=103, exposed_time=T0, **unknown)], D1)
    write_raw_partition([make_row(user_id=4, pid=103, exposed_time=T0, p_date=D2, **unknown),
                         make_row(user_id=5, pid=104, exposed_time=T0 + 86400, p_date=D2)], D2)
    write_raw_categories()
    write_raw_transcripts()
    stage.run(D1)
    stage.run(D2)
    assert validate.run_staged(D2)["errors"] == 0


def test_duplicate_event_key_in_staging_fails(two_day_raw):
    stage_clean()
    ev = pd.read_parquet(io.staged_events_path(D1))
    io.write_parquet(pd.concat([ev, ev.iloc[[0]]], ignore_index=True), io.staged_events_path(D1))
    with pytest.raises(validate.ValidationError, match="event_key_unique"):
        validate.run_staged(D1)


def test_dropped_event_breaks_reconciliation_to_raw(two_day_raw):
    stage_clean()
    ev = pd.read_parquet(io.staged_events_path(D1))
    io.write_parquet(ev.iloc[1:], io.staged_events_path(D1))
    with pytest.raises(validate.ValidationError, match="event_count_reconciles_to_raw"):
        validate.run_staged(D1)


def test_capping_rewatch_values_breaks_the_business_rule(two_day_raw):
    stage_clean()
    ev = pd.read_parquet(io.staged_events_path(D1))
    ev["is_rewatch_flagged"] = False
    io.write_parquet(ev, io.staged_events_path(D1))
    with pytest.raises(validate.ValidationError, match="rewatch_retained_and_flagged"):
        validate.run_staged(D1)


def test_imputing_unknown_breaks_the_business_rule(two_day_raw):
    stage_clean()
    ev = pd.read_parquet(io.staged_events_path(D1))
    ev["fre_community_type"] = ev["fre_community_type"].replace("unknown", "乡村")
    io.write_parquet(ev, io.staged_events_path(D1))
    with pytest.raises(validate.ValidationError, match="fre_community_type_unknown_preserved"):
        validate.run_staged(D1)


# curated gate

def curate_clean():
    stage.run(D1)
    curate.run(D1)


def test_clean_curated_partition_passes(two_day_raw):
    curate_clean()
    assert validate.run_curated(D1)["errors"] == 0


def test_curated_gate_reconciles_features_to_events(two_day_raw):
    curate_clean()
    validate.run_curated(D1)
    assert checks("curated", D1)["feature_event_totals_reconcile"]["passed"] is True


def test_rate_outside_zero_one_fails(two_day_raw):
    curate_clean()
    ft = pd.read_parquet(io.curated_fact_path("daily_user_features", D1))
    ft.loc[0, "hate_rate"] = 1.5
    io.write_parquet(ft, io.curated_fact_path("daily_user_features", D1))
    with pytest.raises(validate.ValidationError, match="hate_rate_within_0_1"):
        validate.run_curated(D1)


def test_duplicate_feature_key_fails(two_day_raw):
    curate_clean()
    ft = pd.read_parquet(io.curated_fact_path("daily_user_features", D1))
    io.write_parquet(pd.concat([ft, ft.iloc[[0]]], ignore_index=True), io.curated_fact_path("daily_user_features", D1))
    with pytest.raises(validate.ValidationError, match="features_pk_unique"):
        validate.run_curated(D1)


def test_event_for_unknown_user_fails_referential_integrity(two_day_raw):
    curate_clean()
    users = pd.read_parquet(io.curated_dim_path("users"))
    io.write_parquet(users[users["user_id"] != 1], io.curated_dim_path("users"))
    with pytest.raises(validate.ValidationError, match="events_users_videos_exist"):
        validate.run_curated(D1)


def test_feature_totals_that_do_not_match_events_fail(two_day_raw):
    curate_clean()
    ft = pd.read_parquet(io.curated_fact_path("daily_user_features", D1))
    ft.loc[0, "n_events"] += 5
    io.write_parquet(ft, io.curated_fact_path("daily_user_features", D1))
    with pytest.raises(validate.ValidationError, match="feature_event_totals_reconcile"):
        validate.run_curated(D1)
