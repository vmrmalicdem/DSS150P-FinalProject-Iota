"""
Shared configuration for the pipeline.

All paths and tunable parameters come from environment variables (or a local
.env file), never hard-coded machine paths. Relative paths are resolved
against the repository root, so scripts behave the same no matter which
directory they are launched from (host shell, Docker, Airflow).
"""

import logging
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path):
    """Minimal .env reader (KEY=VALUE, # comments). Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")


def _path(name, default):
    p = Path(os.environ.get(name, default))
    return p if p.is_absolute() else (ROOT / p).resolve()


SOURCE_DATA_DIR = _path("SOURCE_DATA_DIR", "data_sources")
RAW_DATA_DIR = _path("RAW_DATA_DIR", "raw")
STAGING_DATA_DIR = _path("STAGING_DATA_DIR", "staging")
CURATED_DATA_DIR = _path("CURATED_DATA_DIR", "curated")
LOG_DIR = _path("LOG_DIR", "logs")
SQL_DIR = ROOT / "sql"

# Feature definitions (see docs/transformation-spec.md, section 5).
LATE_NIGHT_START_HOUR = int(os.environ.get("LATE_NIGHT_START_HOUR", 2))
LATE_NIGHT_END_HOUR = int(os.environ.get("LATE_NIGHT_END_HOUR", 4))  # inclusive
SESSION_GAP_SECONDS = int(os.environ.get("SESSION_GAP_SECONDS", 900))
MIN_USER_EVENTS = int(os.environ.get("MIN_USER_EVENTS", 5))

# Event grain: one interaction event = one (user, video, exposure time).
EVENT_KEY = ["user_id", "pid", "exposed_time"]


def postgres_settings():
    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", 5432)),
        "dbname": os.environ.get("POSTGRES_DB", "shortvideo_risk"),
        "user": os.environ.get("POSTGRES_USER", "pipeline_user"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
    }


def get_logger(name):
    logger = logging.getLogger(f"pipeline.{name}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # file logging is best-effort; stdout logging always works
    logger.propagate = False
    return logger
