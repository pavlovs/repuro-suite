"""DB layer for boardroom/investor.db.
Own DB only via get_conn() (journal DELETE locally, WAL on Fly).
Foreign DBs (dealroom.db, pipeline.db, cockpit.db) ONLY via open_readonly().
open_readonly() uses URI mode=ro so a wrong path raises instead of creating an empty file.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
WRITE_LOCK = threading.RLock()
_conn = None
_conn_path = None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_db_path():
    env = os.environ.get("INVESTOR_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "investor.db"


def get_conn():
    """Singleton connection to investor.db (path from INVESTOR_DB env or default)."""
    global _conn, _conn_path
    with WRITE_LOCK:
        path = default_db_path()
        if _conn is not None and _conn_path == str(path):
            return _conn
        if _conn is not None:
            _conn.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        if os.environ.get("FLY_APP_NAME"):
            conn.execute("PRAGMA journal_mode=WAL")
        else:
            conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=ON")
        schema_v = conn.execute("PRAGMA user_version").fetchone()[0]
        if schema_v == 0:
            init_db(conn)
        _conn, _conn_path = conn, str(path)
        return conn


def close_conn():
    """Tests only — drop the singleton so the next get_conn() re-reads INVESTOR_DB."""
    global _conn, _conn_path
    with WRITE_LOCK:
        if _conn is not None:
            _conn.close()
        _conn, _conn_path = None, None


def open_readonly(path):
    """Read-only URI connect to a foreign DB (dealroom/pipeline/cockpit).
    Fails loudly if the path is missing instead of creating an empty file.
    Uses Path.as_uri() so Windows absolute paths and spaces (OneDrive) are
    escaped correctly — a hand-built 'file:C:/..' URI is malformed for SQLite."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"read-only DB not found: {p}")
    uri = p.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


DDL = """
CREATE TABLE publications (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  kind         TEXT NOT NULL CHECK(kind IN ('weekly_update','board_pack')),
  ref          TEXT NOT NULL,
  title        TEXT,
  status       TEXT NOT NULL CHECK(status IN ('draft','approved','published','archived')),
  body         TEXT NOT NULL DEFAULT '{}',
  created_at   TEXT NOT NULL,
  approved_at  TEXT,
  approved_by  TEXT,
  published_at TEXT,
  version      INTEGER NOT NULL DEFAULT 1
);
-- Invariant: at most one 'published' row per kind (the current one). The publish
-- flow (M3) must archive the prior published row before publishing the next.
CREATE UNIQUE INDEX ux_pub_one_published_per_kind
  ON publications(kind) WHERE status = 'published';
CREATE TABLE audit_log (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  at     TEXT NOT NULL,
  actor  TEXT NOT NULL,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  before TEXT,
  after  TEXT
);
CREATE TABLE users (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  initials   TEXT,
  token_hash TEXT,
  role       TEXT NOT NULL CHECK(role IN ('admin','investor'))
);
"""


def init_db(conn=None):
    """Create schema. Accepts an optional connection (for CLI); otherwise uses get_conn()."""
    if conn is None:
        conn = get_conn()
    conn.executescript(DDL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
