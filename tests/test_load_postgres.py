import pandas as pd
import pytest

import curate
import io_utils as io
import stage
from conftest import D1, D2

pytestmark = pytest.mark.postgres
TEST_SCHEMA = "pipeline_test"


@pytest.fixture
def pg(monkeypatch):
    import load_postgres
    try:
        admin = load_postgres.connect()
    except ConnectionError:
        s = load_postgres.postgres_settings()
        pytest.skip(f"no PostgreSQL reachable at {s['host']}:{s['port']} (start it with: docker compose up -d postgres)")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {TEST_SCHEMA}")
    monkeypatch.setenv("PGOPTIONS", f"-c search_path={TEST_SCHEMA}")
    yield load_postgres
    with admin.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
    admin.close()


def prepare(dates):
    for d in dates:
        stage.run(d)
        curate.run(d)


def query(pg, sql, params=None):
    conn = pg.connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def counts(pg):
    return {t: query(pg, f"SELECT count(*) FROM {t}")[0][0]
            for t in ("categories", "users", "videos", "video_categories",
                      "interactions_curated", "daily_user_features")}


def test_schema_is_created_with_all_tables(two_day_raw, pg):
    prepare([D1])
    pg.load(D1)
    tables = {r[0] for r in query(pg, "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                                  (TEST_SCHEMA,))}
    assert {"categories", "users", "videos", "video_categories", "interactions_curated",
            "daily_user_features", "risk_scores"} <= tables


def test_loaded_rows_match_the_curated_parquet(two_day_raw, pg):
    prepare([D1])
    pg.load(D1)
    c = counts(pg)
    assert c["interactions_curated"] == len(pd.read_parquet(io.curated_fact_path("interactions_curated", D1)))
    assert c["daily_user_features"] == len(pd.read_parquet(io.curated_fact_path("daily_user_features", D1)))
    assert c["users"] == len(pd.read_parquet(io.curated_dim_path("users")))
    assert c["categories"] == len(pd.read_parquet(io.curated_dim_path("categories")))


def test_reloading_the_same_date_does_not_duplicate_anything(two_day_raw, pg):
    prepare([D1])
    pg.load(D1)
    first = counts(pg)
    second_stats = pg.load(D1)
    assert counts(pg) == first
    assert second_stats["events_deleted_then_inserted"] == [first["interactions_curated"]] * 2


def test_loading_a_second_date_adds_only_that_dates_facts(two_day_raw, pg):
    prepare([D1, D2])
    pg.load(D1)
    after_one = counts(pg)
    pg.load(D2)
    after_two = counts(pg)
    assert after_two["interactions_curated"] == after_one["interactions_curated"] + 2
    dates = [str(r[0]) for r in query(pg, "SELECT DISTINCT p_date FROM interactions_curated ORDER BY 1")]
    assert dates == ["2022-09-16", "2022-09-17"]


def test_reloading_an_earlier_date_leaves_later_dates_alone(two_day_raw, pg):
    prepare([D1, D2])
    pg.load(D1)
    pg.load(D2)
    before = counts(pg)
    pg.load(D1)
    assert counts(pg) == before


def test_changed_dimension_values_are_updated_on_reload(two_day_raw, pg):
    prepare([D1])
    pg.load(D1)
    assert query(pg, "SELECT fre_city FROM users WHERE user_id = 1")[0][0] == "Beijing"
    users = pd.read_parquet(io.curated_dim_path("users"))
    users.loc[users["user_id"] == 1, "fre_city"] = "Shenzhen"
    io.write_parquet(users, io.curated_dim_path("users"))
    cats = pd.read_parquet(io.curated_dim_path("categories"))
    cats.loc[cats["category_id"] == 1, "category_name_en"] = "food (renamed)"
    io.write_parquet(cats, io.curated_dim_path("categories"))
    counts_before = counts(pg)
    pg.load(D1)
    assert query(pg, "SELECT fre_city FROM users WHERE user_id = 1")[0][0] == "Shenzhen"
    assert query(pg, "SELECT category_name_en FROM categories WHERE category_id = 1")[0][0] == "food (renamed)"
    assert counts(pg) == counts_before          # updated in place, not duplicated


def test_user_event_totals_and_sparse_flag_are_derived(two_day_raw, pg):
    prepare([D1, D2])
    pg.load(D1)
    pg.load(D2)
    rows = {r[0]: r[1:] for r in query(pg, "SELECT user_id, total_events, is_sparse_history FROM users")}
    assert rows[1][0] == 2 and rows[2][0] == 2          # user 1: pid100 + pid104; user 2: two days
    assert all(sparse for _, sparse in rows.values())    # every fixture user has < 5 events


def test_primary_key_blocks_a_duplicate_event(two_day_raw, pg):
    import psycopg2
    prepare([D1])
    pg.load(D1)
    conn = pg.connect()
    try:
        with pytest.raises(psycopg2.errors.UniqueViolation):
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO interactions_curated SELECT * FROM interactions_curated LIMIT 1")
    finally:
        conn.close()


def test_foreign_key_blocks_an_event_for_an_unknown_user(two_day_raw, pg):
    import psycopg2
    prepare([D1])
    pg.load(D1)
    conn = pg.connect()
    try:
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            with conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO daily_user_features
                    (user_id, feature_date, n_events, total_watch_seconds, late_night_events,
                     late_night_watch_seconds, n_sessions, max_session_seconds, avg_session_seconds,
                     hate_events, hate_rate, rewatch_events, rewatch_rate)
                    VALUES (999999, '2022-09-16', 1, 1, 0, 0, 1, 1, 1, 0, 0, 0, 0)""")
    finally:
        conn.close()


def test_failed_load_leaves_the_database_unchanged(two_day_raw, pg):
    prepare([D1, D2])
    pg.load(D1)
    before = counts(pg)
    # break the day-2 curated facts so the load raises mid-transaction
    path = io.curated_fact_path("interactions_curated", D2)
    df = pd.read_parquet(path)
    df.loc[0, "user_id"] = 424242            # not in the users dimension -> FK violation
    io.write_parquet(df, path)
    with pytest.raises(Exception):
        pg.load(D2)
    assert counts(pg) == before


def test_unreachable_database_raises_a_clear_connection_error(monkeypatch):
    import load_postgres
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "1")   # nothing listens here
    with pytest.raises(ConnectionError, match="cannot connect to PostgreSQL"):
        load_postgres.connect()
