import os
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = Path(tempfile.mkdtemp(prefix="pipeline_tests_"))

LAYER_DIRS = {
    "SOURCE_DATA_DIR": TMP_ROOT / "source",
    "RAW_DATA_DIR": TMP_ROOT / "raw",
    "STAGING_DATA_DIR": TMP_ROOT / "staging",
    "CURATED_DATA_DIR": TMP_ROOT / "curated",
    "LOG_DIR": TMP_ROOT / "logs",
}
for _name, _path in LAYER_DIRS.items():
    os.environ[_name] = str(_path)
os.environ.update({
    "LATE_NIGHT_START_HOUR": "2",
    "LATE_NIGHT_END_HOUR": "4",
    "SESSION_GAP_SECONDS": "900",
    "MIN_USER_EVENTS": "5",
})
sys.path.insert(0, str(ROOT / "scripts"))

# Imported only after the environment above is in place.
import validate  # noqa: E402  (EXPECTED_COLUMNS is the single source of the raw schema)

RAW_COLUMNS = list(validate.EXPECTED_COLUMNS)
D1, D2, D3 = "20220916", "20220917", "20220918"
T0 = 1663322400  # 2022-09-16 10:00:00 UTC


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_layers():
    """Start every test from empty layers."""
    for path in LAYER_DIRS.values():
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
    yield


# Synthetic data builders (same schema as interaction_sampled.csv, all text)

def make_row(**over):
    row = {
        "user_id": "1", "pid": "100", "author_id": "900", "category_id": "1",
        "category_level": "1", "parent_id": "1", "root_id": "1",
        "exposed_time": str(T0), "author_fans_count": "500", "watch_time": "10",
        "duration": "20.0", "cvm_like": "False", "click": "False", "comment": "False",
        "follow": "False", "collect": "False", "forward": "False", "hate": "False",
        "tag_name": "tag-a", "title": "a title", "p_hour": "10", "p_date": D1,
        "gender": "M", "age": "30", "mod_price": "1999", "fre_city": "Beijing",
        "fre_community_type": "城区", "fre_city_level": "一线城市",
    }
    row.update({k: str(v) for k, v in over.items()})
    return row


def raw_frame(rows):
    return pd.DataFrame(rows, columns=RAW_COLUMNS, dtype=str)


def write_raw_partition(rows, p_date):
    path = LAYER_DIRS["RAW_DATA_DIR"] / "interactions" / f"p_date={p_date}" / "interactions.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_frame(rows).to_csv(path, index=False, encoding="utf-8")
    return path


DEFAULT_CATEGORIES = [
    # level, id, cn, parent, root, en  (en labels carry the leading space seen in the real file)
    ("1", "1", "美食", "1", "1", " food"),
    ("1", "2", "游戏", "2", "2", " games"),
    ("2", "3", "做饭", "1", "1", " cooking"),
]


def write_raw_categories(rows=None):
    rows = DEFAULT_CATEGORIES if rows is None else rows
    path = LAYER_DIRS["RAW_DATA_DIR"] / "categories" / "categories_cn_en.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["category_level", "category_id", "category_name_cn",
                                "parent_id", "root_id", "category_name_en"]).to_csv(path, index=False)
    return path


def write_raw_transcripts(texts=None):
    texts = {"100": "hello brave new world"} if texts is None else texts
    d = LAYER_DIRS["RAW_DATA_DIR"] / "transcripts" / "asr_en"
    d.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (d / f"{name}.txt").write_text(text, encoding="utf-8")


def two_day_rows():
    t = T0
    d1 = [
        make_row(user_id=1, pid=100, category_id=1, tag_name="a", exposed_time=t),
        make_row(user_id=1, pid=100, category_id=2, tag_name="b", exposed_time=t),
        make_row(user_id=1, pid=100, category_id=3, tag_name="c", exposed_time=t),
        make_row(user_id=2, pid=101, exposed_time=t + 100, gender="F", age=25),
        make_row(user_id=2, pid=101, exposed_time=t + 100, gender="F", age=25),
        make_row(user_id=3, pid=102, exposed_time=t + 200, watch_time=40, duration=20.0,
                 hate="True", age=41),
        make_row(user_id=4, pid=103, exposed_time=t + 300, fre_community_type="unknown",
                 fre_city_level="unknown", age=52),
    ]
    day2 = 86400
    d2 = [
        make_row(user_id=1, pid=100, category_id=1, tag_name="a", exposed_time=t,
                 p_date=D2),  # same event as day 1
        make_row(user_id=1, pid=104, exposed_time=t + day2, p_date=D2, p_hour=10),
        make_row(user_id=2, pid=101, exposed_time=t + day2 + 50, p_date=D2, gender="F", age=25),
    ]
    return d1, d2


@pytest.fixture
def two_day_raw():
    d1, d2 = two_day_rows()
    write_raw_partition(d1, D1)
    write_raw_partition(d2, D2)
    write_raw_categories()
    write_raw_transcripts()
    return d1, d2
