"""DB layer. Own DB only via get_conn() (journal DELETE, validated path).
Foreign DBs (dealroom.db) ONLY via open_readonly() — plain sqlite3.connect()
on a wrong path silently creates an empty file (see ai/LEARNINGS.md)."""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 8
WRITE_LOCK = threading.RLock()
_conn = None
_conn_path = None


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_db_path():
    env = os.environ.get("COCKPIT_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "data" / "cockpit.db"


def get_conn():
    """Singleton connection to the cockpit DB (path from COCKPIT_DB env or default)."""
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
        elif schema_v < SCHEMA_VERSION:
            migrate_db(conn, schema_v)
        _conn, _conn_path = conn, str(path)
        return conn


def close_conn():
    """Tests only — drop the singleton so the next get_conn() re-reads COCKPIT_DB."""
    global _conn, _conn_path
    with WRITE_LOCK:
        if _conn is not None:
            _conn.close()
        _conn, _conn_path = None, None


def open_readonly(path):
    """Read-only URI connect to a foreign DB. Fails loudly if the path is wrong
    instead of creating an empty file."""
    uri = "file:" + str(Path(path)).replace("\\", "/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


DDL = """
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  initials TEXT,
  token_hash TEXT,
  role TEXT NOT NULL CHECK(role IN ('human','agent'))
);
CREATE TABLE deal_mirror (
  codename TEXT PRIMARY KEY,
  stage TEXT,
  note TEXT,
  owner_mode TEXT NOT NULL DEFAULT 'legacy' CHECK(owner_mode IN ('legacy','cockpit-owned')),
  synced_at TEXT
);
CREATE TABLE spaces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  color TEXT,
  icon TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  sort_mode TEXT NOT NULL DEFAULT 'manual'
    CHECK(sort_mode IN ('manual','deal_stage')),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active','parked','done')),
  version INTEGER NOT NULL DEFAULT 1
);
INSERT INTO spaces (name, slug, color, icon, sort_order, sort_mode)
  VALUES ('Holding', 'holding', '#0891B2', 'building', 0, 'manual');
INSERT INTO spaces (name, slug, color, icon, sort_order, sort_mode)
  VALUES ('M&A', 'mna', '#7C3AED', 'handshake', 1, 'deal_stage');
CREATE TABLE workstreams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  space_id INTEGER NOT NULL DEFAULT 1 REFERENCES spaces(id),
  color TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','parked','done')),
  deal_codename TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  objective TEXT
);
CREATE UNIQUE INDEX uq_workstreams_space_name ON workstreams(space_id, name);
CREATE TABLE deliverables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workstream_id INTEGER NOT NULL REFERENCES workstreams(id),
  name TEXT NOT NULL,
  target_date TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done','dropped')),
  sort_order INTEGER NOT NULL DEFAULT 0,
  comment TEXT,
  staging INTEGER NOT NULL DEFAULT 0,
  source TEXT,
  deal TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  start_date TEXT
);
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  deliverable_id INTEGER REFERENCES deliverables(id),
  kind TEXT NOT NULL DEFAULT 'workplan'
    CHECK(kind IN ('workplan','followup','approval','agent_job','personal')),
  text TEXT NOT NULL,
  detail TEXT,
  deadline TEXT,
  responsible TEXT,
  priority TEXT CHECK(priority IS NULL OR priority IN ('high','med','low')),
  status TEXT NOT NULL DEFAULT 'open'
    CHECK(status IN ('open','in_progress','waiting','blocked','in_review','done')),
  waiting_on_party TEXT,
  waiting_on_type TEXT CHECK(waiting_on_type IS NULL OR
    waiting_on_type IN ('counterparty','advisor','investor','internal')),
  next_chase_date TEXT,
  expected_back_by TEXT,
  last_touched_at TEXT,
  execution TEXT NOT NULL DEFAULT 'me'
    CHECK(execution IN ('me','together','agent_supervised','agent_auto')),
  runner TEXT CHECK(runner IS NULL OR runner IN ('local','cma','any')),
  acceptance_criteria TEXT,
  claimed_by TEXT,
  claim_expires_at TEXT,
  evidence TEXT,
  prereqs TEXT NOT NULL DEFAULT '[]',
  tags TEXT NOT NULL DEFAULT '[]',
  links TEXT NOT NULL DEFAULT '[]',
  deal TEXT,
  pinned_today INTEGER NOT NULL DEFAULT 0,
  staging INTEGER NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  source TEXT,
  input_from TEXT CHECK(input_from IS NULL OR input_from IN ('RD','FF')),
  input_question TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  done_at TEXT,
  start_date TEXT
);
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity TEXT NOT NULL,
  before TEXT,
  after TEXT
);
CREATE TABLE idempotency (
  task_id INTEGER NOT NULL,
  key TEXT NOT NULL,
  response TEXT NOT NULL,
  at TEXT NOT NULL,
  PRIMARY KEY (task_id, key)
);
CREATE INDEX idx_tasks_deliverable ON tasks(deliverable_id);
CREATE INDEX idx_tasks_status ON tasks(status);
"""


MIGRATIONS = {
    2: ["ALTER TABLE tasks ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"],
    3: [
        "ALTER TABLE tasks ADD COLUMN input_from TEXT CHECK(input_from IS NULL OR input_from IN ('RD','FF'))",
        "ALTER TABLE tasks ADD COLUMN input_question TEXT",
    ],
    4: [
        """CREATE TABLE IF NOT EXISTS spaces (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          slug TEXT NOT NULL UNIQUE,
          color TEXT,
          icon TEXT,
          sort_order INTEGER NOT NULL DEFAULT 0,
          sort_mode TEXT NOT NULL DEFAULT 'manual'
            CHECK(sort_mode IN ('manual','deal_stage')),
          status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active','parked','done')),
          version INTEGER NOT NULL DEFAULT 1
        )""",
        "INSERT OR IGNORE INTO spaces (name, slug, color, icon, sort_order, sort_mode) "
        "VALUES ('Repuro', 'repuro', '#0891B2', 'building', 0, 'manual')",
        "INSERT OR IGNORE INTO spaces (name, slug, color, icon, sort_order, sort_mode) "
        "VALUES ('M&A', 'mna', '#7C3AED', 'handshake', 1, 'deal_stage')",
        lambda c: _add_column_if_missing(
            c, "workstreams", "space_id", "INTEGER NOT NULL DEFAULT 1"
        ),
        "UPDATE workstreams SET space_id = (SELECT id FROM spaces WHERE slug = 'mna') "
        "WHERE deal_codename IS NOT NULL",
        "UPDATE workstreams SET space_id = (SELECT id FROM spaces WHERE slug = 'mna') "
        "WHERE lower(name) = 'pipeline'",
        # sqlite_autoindex_workstreams_1 (global UNIQUE on name) can't be dropped —
        # it's tied to the table definition. Harmless: stricter than space-scoped.
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_workstreams_space_name "
        "ON workstreams(space_id, name)",
        lambda c: _add_column_if_missing(c, "deliverables", "deal", "TEXT"),
        "UPDATE deliverables SET deal = ("
        "  SELECT w.deal_codename FROM workstreams w "
        "  WHERE w.id = deliverables.workstream_id AND w.deal_codename IS NOT NULL"
        ") WHERE deal IS NULL",
    ],
    5: [
        "UPDATE spaces SET name = 'Holding', slug = 'holding' WHERE slug = 'repuro'",
    ],
    6: [
        lambda c: _add_column_if_missing(c, "workstreams", "objective", "TEXT"),
    ],
    7: [
        lambda c: _add_column_if_missing(c, "deliverables", "start_date", "TEXT"),
    ],
    8: [
        lambda c: _add_column_if_missing(c, "tasks", "start_date", "TEXT"),
    ],
}


def _add_column_if_missing(conn, table, column, typedef):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")


def init_db(conn):
    conn.executescript(DDL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def migrate_db(conn, from_version):
    """Apply all pending migrations starting from from_version.
    Called by get_conn() when schema_v < SCHEMA_VERSION."""
    current = from_version
    for version in sorted(MIGRATIONS):
        if current < version:
            stmts = MIGRATIONS[version]
            for step in stmts:
                if callable(step):
                    step(conn)
                else:
                    conn.execute(step)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
            current = version


# Backwards-compat alias used by api.py lifespan (no-op — migration runs in get_conn now)
def migrate(conn):
    pass


def audit(conn, actor, action, entity, before=None, after=None):
    """Caller holds WRITE_LOCK and commits."""
    conn.execute(
        "INSERT INTO audit_log (at, actor, action, entity, before, after) VALUES (?,?,?,?,?,?)",
        (
            now_iso(),
            actor,
            action,
            entity,
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
        ),
    )
