"""
Curated -> PostgreSQL.

Rerun strategy (one transaction per run, so a failure leaves the database unchanged):
  dimensions  upsert on primary key (INSERT ... ON CONFLICT DO UPDATE)
  facts       replace-partition: delete the date's rows, then bulk insert them
Running the same date twice therefore yields the same table contents.
"""

import io as stdio

import pandas as pd
import psycopg2

import io_utils as io
from config import MIN_USER_EVENTS, SQL_DIR, get_logger, postgres_settings

log = get_logger("load")


def connect():
    s = postgres_settings()
    try:
        return psycopg2.connect(connect_timeout=10, **s)
    except psycopg2.OperationalError as e:
        raise ConnectionError(
            f"cannot connect to PostgreSQL at {s['host']}:{s['port']}/{s['dbname']} as {s['user']}: {e}") from e


def ensure_schema(cur):
    cur.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))


def _copy(cur, df, table, columns):
    buf = stdio.StringIO()
    df[columns].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cols = ", ".join(columns)
    cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)


def _upsert(cur, df, table, columns, key):
    """Bulk upsert via a temp table; returns rows written."""
    tmp = f"_stg_{table}"
    cur.execute(f"CREATE TEMP TABLE {tmp} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")
    _copy(cur, df, tmp, columns)
    updates = [c for c in columns if c not in key]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)
    conflict = ", ".join(key)
    action = f"DO UPDATE SET {set_clause}" if updates else "DO NOTHING"
    cols = ", ".join(columns)
    cur.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {tmp} ON CONFLICT ({conflict}) {action}")
    return cur.rowcount


def _replace_partition(cur, df, table, date_col, p_date_iso, columns):
    cur.execute(f"DELETE FROM {table} WHERE {date_col} = %s", (p_date_iso,))
    deleted = cur.rowcount
    _copy(cur, df, table, columns)
    return deleted, len(df)


def load(p_date):
    p_date = io.check_p_date(p_date)
    iso = f"{p_date[:4]}-{p_date[4:6]}-{p_date[6:]}"

    users = pd.read_parquet(io.curated_dim_path("users"))
    videos = pd.read_parquet(io.curated_dim_path("videos"))
    cats = pd.read_parquet(io.curated_dim_path("categories"))
    vcat = pd.read_parquet(io.curated_dim_path("video_categories"))
    events = pd.read_parquet(io.curated_fact_path("interactions_curated", p_date))
    feats = pd.read_parquet(io.curated_fact_path("daily_user_features", p_date))

    # users.total_events / is_sparse_history are derived in SQL after the facts load.
    users = users.assign(total_events=0, is_sparse_history=False)
    videos["transcript_word_count"] = videos["transcript_word_count"].astype("Int64")

    conn = connect()
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_schema(cur)
                n_cat = _upsert(cur, cats, "categories", list(cats.columns), ["category_id"])
                user_cols = ["user_id", "gender", "age", "mod_price", "fre_city", "fre_community_type", "fre_city_level"]
                n_usr = _upsert(cur, users, "users", user_cols, ["user_id"])
                n_vid = _upsert(cur, videos, "videos", list(videos.columns), ["pid"])
                n_vc = _upsert(cur, vcat, "video_categories", ["pid", "category_id"], ["pid", "category_id"])

                ev = events.assign(p_date=events["p_date"].dt.strftime("%Y-%m-%d"))
                ft = feats.assign(feature_date=feats["feature_date"].dt.strftime("%Y-%m-%d"))
                del_ev, ins_ev = _replace_partition(cur, ev, "interactions_curated", "p_date", iso, list(ev.columns))
                del_ft, ins_ft = _replace_partition(cur, ft, "daily_user_features", "feature_date", iso, list(ft.columns))

                cur.execute("""
                    UPDATE users u SET total_events =
                        COALESCE((SELECT count(*) FROM interactions_curated i WHERE i.user_id = u.user_id), 0)""")
                cur.execute("UPDATE users SET is_sparse_history = (total_events < %s)", (MIN_USER_EVENTS,))

                cur.execute("SELECT count(*) FROM interactions_curated WHERE p_date = %s", (iso,))
                in_db = cur.fetchone()[0]
                if in_db != len(events):
                    raise RuntimeError(f"row count mismatch after load: db={in_db} expected={len(events)}")
    finally:
        conn.close()

    stats = {"p_date": p_date, "categories_upserted": n_cat, "users_upserted": n_usr, "videos_upserted": n_vid,
             "video_categories_upserted": n_vc, "events_deleted_then_inserted": [del_ev, ins_ev],
             "features_deleted_then_inserted": [del_ft, ins_ft]}
    log.info("loaded %s: %s", p_date, stats)
    return stats


def run(p_date):
    return load(p_date)


if __name__ == "__main__":
    import sys
    run(sys.argv[1])
