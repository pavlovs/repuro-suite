"""DEALROOM v2 — DB connection + schema init.

Local sandbox: data/dealroom_v2.db (journal=DELETE — OneDrive rules).
Fly (cutover): DEALROOM_DB_PATH=/data/dealroom.db on the volume (WAL allowed).
v1 data/dealroom.db is NEVER opened read-write by v2 code.
"""

import os
import sqlite3
import threading
from pathlib import Path

V2_DIR = Path(__file__).resolve().parent
DEALROOM_DIR = V2_DIR.parent

WRITE_LOCK = threading.Lock()

SCHEMA_FILE = V2_DIR / "schema.sql"


def default_db_path() -> Path:
    env = os.environ.get("DEALROOM_V2_DB") or os.environ.get("DEALROOM_DB_PATH")
    if env:
        return Path(env)
    return DEALROOM_DIR / "data" / "dealroom_v2.db"


def v1_db_path() -> Path:
    env = os.environ.get("DEALROOM_V1_DB")
    if env:
        return Path(env)
    return DEALROOM_DIR / "data" / "dealroom.db"


def pipeline_db_path() -> Path | None:
    env = os.environ.get("ALLEX_PIPELINE_DB")
    if env:
        return Path(env)
    default = Path(r"C:\Users\X1\Documents\CLAUDE_COWORK\repuro-data\pipeline.db")
    return default if default.exists() else None


def on_fly() -> bool:
    return bool(os.environ.get("FLY_APP_NAME"))


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else default_db_path()
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # OneDrive-synced local sandbox: journal must stay DELETE (no -wal siblings).
    conn.execute("PRAGMA journal_mode = " + ("WAL" if on_fly() else "DELETE"))
    return conn


def open_readonly(path: Path) -> sqlite3.Connection:
    """Read-only URI connect for foreign DBs (v1 dealroom.db, pipeline.db)."""
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def attach_pipeline_ro(conn: sqlite3.Connection) -> bool:
    """ATTACH ALLEX pipeline.db read-only as `allex`. Returns False if absent."""
    path = pipeline_db_path()
    if not path or not Path(path).exists():
        return False
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    try:
        conn.execute("ATTACH DATABASE ? AS allex", (uri,))
        return True
    except sqlite3.Error:
        return False


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Create the v2 schema in a fresh or existing-empty DB file."""
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn(path)
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    if n == 0:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    return conn


def now_iso() -> str:
    import datetime

    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
