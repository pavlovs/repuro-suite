# M27: Activity Tracker Backend — Implementation Plan

---

## Execution Results — 2026-05-03

**Delivered:**
- `activity_log` table in `db.py` with columns: `id, domain, actor, field, old_value, new_value, changed_at` + two indexes (`idx_activity_domain`, `idx_activity_changed_at`)
- `log_activity(conn, domain, actor, field, old_value, new_value)` — takes an open connection, inserts one row; `actor` defaults to `"unknown"` when blank
- `_patch_company()` in `dashboard.py`: reads old values before UPDATE, logs each changed field via `log_activity()` inside the same `get_connection()` context; actor extracted from `?actor=` query param
- `GET /api/activity` endpoint: replaces stub, supports `?domain=` and `?limit=` filters, returns JSON array
- 9 tests passing in `tests/test_activity_log.py`

**Diverged from spec:**
- No `kind` column — deferred (adds complexity without immediate UI need)
- `log_activity()` signature takes `conn` (not `db_path`) — avoids a second connection open inside the PATCH retry loop
- No `query_activity()` helper — endpoint queries inline
- Undo button: deferred

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Log every manual field change in the dashboard with actor, timestamp, old/new values — enabling accountability and undo. Zero frontend changes.

**Architecture:** New `activity_log` table in pipeline.db created via `ensure_schema()`. PATCH handler reads old values before writing, logs each changed field as a separate row. New `GET /api/activity` endpoint serves log entries with filtering. Actor identity arrives as `?actor=` query param from the client.

**Tech Stack:** Python 3, SQLite, stdlib `http.server` (existing dashboard.py pattern)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/pipeline/db.py` | Modify (lines ~29, ~149-175, ~178-208) | Add `activity_log` DDL + migration |
| `src/pipeline/dashboard.py` | Modify (lines ~26-57, ~363-401, ~433-483, ~544-605) | Hook logging into PATCH/POST handlers, add GET /api/activity route |
| `tests/test_activity_log.py` | Create | All activity log tests |

---

### Task 1: Activity log table DDL and migration

**Files:**
- Modify: `src/pipeline/db.py`
- Test: `tests/test_activity_log.py`

- [ ] **Step 1: Write the failing test — table creation**

```python
"""Tests for activity_log table and logging functions (M27)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.pipeline.db import ensure_schema, get_connection


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_pipeline.db"
    ensure_schema(p)
    return p


class TestActivityLogSchema:
    def test_activity_log_table_exists(self, db_path: Path):
        with get_connection(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "activity_log" in tables

    def test_activity_log_columns(self, db_path: Path):
        with get_connection(db_path) as conn:
            cols = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(activity_log)"
                ).fetchall()
            }
        assert cols == {
            "id", "domain", "field", "old_value", "new_value",
            "actor", "kind", "timestamp",
        }

    def test_activity_log_indexes(self, db_path: Path):
        with get_connection(db_path) as conn:
            indexes = {
                row[1]
                for row in conn.execute(
                    "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='activity_log'"
                ).fetchall()
            }
        assert "idx_activity_domain" in indexes
        assert "idx_activity_timestamp" in indexes
        assert "idx_activity_actor" in indexes

    def test_idempotent_creation(self, db_path: Path):
        ensure_schema(db_path)
        ensure_schema(db_path)
        with get_connection(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "activity_log" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestActivityLogSchema -v`

Expected: FAIL — `activity_log` table does not exist.

- [ ] **Step 3: Add activity_log DDL to db.py**

In `src/pipeline/db.py`, add after the `_CREATE_TABLE` string constant (after the closing `"""`):

```python
_CREATE_ACTIVITY_LOG = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (domain) REFERENCES company_records(domain)
);
CREATE INDEX IF NOT EXISTS idx_activity_domain ON activity_log(domain);
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_actor ON activity_log(actor);
"""
```

Then modify `ensure_schema()` to execute it:

```python
def ensure_schema(db_path: Path) -> None:
    """Create tables if they don't exist and migrate any missing columns. Safe to call repeatedly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.execute(_CREATE_TABLE)
        conn.executescript(_CREATE_ACTIVITY_LOG)
        _migrate_schema(conn)
```

Note: Use `executescript` (not `execute`) because `_CREATE_ACTIVITY_LOG` contains multiple statements separated by `;`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestActivityLogSchema -v`

Expected: 4 PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All 480+ tests pass.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/db.py tests/test_activity_log.py
git commit -m "feat(M27): activity_log table DDL + migration in ensure_schema"
```

---

### Task 2: log_activity helper function

**Files:**
- Modify: `src/pipeline/db.py`
- Test: `tests/test_activity_log.py`

- [ ] **Step 1: Write the failing test — log_activity insert**

Append to `tests/test_activity_log.py`:

```python
from src.pipeline.db import log_activity


class TestLogActivity:
    def test_inserts_single_entry(self, db_path: Path):
        log_activity(
            db_path,
            domain="test.de",
            field="klass",
            old_value="C",
            new_value="B",
            actor="roman",
            kind="edit",
        )
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT * FROM activity_log").fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["domain"] == "test.de"
        assert row["field"] == "klass"
        assert row["old_value"] == "C"
        assert row["new_value"] == "B"
        assert row["actor"] == "roman"
        assert row["kind"] == "edit"
        assert row["timestamp"]  # non-empty ISO string

    def test_null_old_value(self, db_path: Path):
        log_activity(
            db_path,
            domain="test.de",
            field="compliment_draft",
            old_value=None,
            new_value="Beeindruckend…",
            actor="claude",
            kind="gen",
        )
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM activity_log").fetchone()
        assert row["old_value"] is None
        assert row["new_value"] == "Beeindruckend…"

    def test_multiple_entries_same_domain(self, db_path: Path):
        for field in ["klass", "region", "anrede"]:
            log_activity(
                db_path,
                domain="test.de",
                field=field,
                old_value="old",
                new_value="new",
                actor="roman",
                kind="edit",
            )
        with get_connection(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM activity_log WHERE domain = 'test.de'"
            ).fetchone()[0]
        assert count == 3

    def test_timestamp_is_iso_format(self, db_path: Path):
        log_activity(
            db_path,
            domain="test.de",
            field="klass",
            old_value="A",
            new_value="B",
            actor="flo",
            kind="edit",
        )
        with get_connection(db_path) as conn:
            ts = conn.execute(
                "SELECT timestamp FROM activity_log"
            ).fetchone()[0]
        # ISO 8601: YYYY-MM-DDTHH:MM:SS
        assert "T" in ts
        assert len(ts) >= 19
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestLogActivity -v`

Expected: FAIL — `log_activity` not found.

- [ ] **Step 3: Implement log_activity in db.py**

Add to `src/pipeline/db.py`, after `ensure_schema`:

```python
def log_activity(
    db_path: Path,
    *,
    domain: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
    actor: str,
    kind: str,
) -> None:
    """Insert one activity log entry. Called per-field, not per-request."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO activity_log (domain, field, old_value, new_value, actor, kind, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (domain, field, old_value, new_value, actor, kind, ts),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestLogActivity -v`

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/db.py tests/test_activity_log.py
git commit -m "feat(M27): log_activity helper — inserts per-field change entries"
```

---

### Task 3: Hook activity logging into PATCH handler

**Files:**
- Modify: `src/pipeline/dashboard.py` (lines ~433-483)
- Test: `tests/test_activity_log.py`

- [ ] **Step 1: Write the failing test — PATCH logs changes**

Append to `tests/test_activity_log.py`:

```python
import json
from unittest.mock import patch as mock_patch, MagicMock
from src.pipeline.db import log_activity


class TestPatchLogging:
    def _seed_record(self, db_path: Path):
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO company_records (id, domain, full_name, profile_id, source, klass, pipeline_stage) "
                "VALUES ('abc123', 'test.de', 'Test GmbH', 'medtech_germany', 'manual', 'C', 'classified')"
            )

    def test_patch_logs_changed_fields(self, db_path: Path):
        self._seed_record(db_path)
        # Simulate what the PATCH handler does: read old, write new, log
        domain = "test.de"
        updates = {"klass": "B", "region": "Bayern"}

        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT klass, region FROM company_records WHERE domain = ?",
                (domain,),
            ).fetchone()
            old_values = {k: row[k] for k in updates}

        # Write the update
        with get_connection(db_path) as conn:
            for k, v in updates.items():
                conn.execute(
                    f"UPDATE company_records SET {k} = ? WHERE domain = ?",
                    (v, domain),
                )

        # Log each changed field
        for field, new_val in updates.items():
            old_val = old_values.get(field)
            if str(old_val) != str(new_val):
                log_activity(
                    db_path,
                    domain=domain,
                    field=field,
                    old_value=str(old_val) if old_val is not None else None,
                    new_value=str(new_val) if new_val is not None else None,
                    actor="roman",
                    kind="edit",
                )

        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT field, old_value, new_value, actor FROM activity_log ORDER BY field"
            ).fetchall()
        assert len(rows) == 2
        assert rows[0]["field"] == "klass"
        assert rows[0]["old_value"] == "C"
        assert rows[0]["new_value"] == "B"
        assert rows[1]["field"] == "region"
        assert rows[1]["old_value"] is None
        assert rows[1]["new_value"] == "Bayern"

    def test_unchanged_fields_not_logged(self, db_path: Path):
        self._seed_record(db_path)
        domain = "test.de"
        updates = {"klass": "C"}  # same as current value

        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT klass FROM company_records WHERE domain = ?",
                (domain,),
            ).fetchone()
            old_klass = row["klass"]

        # klass is already "C", sending "C" again → no log
        if str(old_klass) != str(updates["klass"]):
            log_activity(
                db_path,
                domain=domain,
                field="klass",
                old_value=old_klass,
                new_value=updates["klass"],
                actor="roman",
                kind="edit",
            )

        with get_connection(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
        assert count == 0
```

- [ ] **Step 2: Run test to verify it passes (these test the pattern, not the handler)**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestPatchLogging -v`

Expected: 2 PASS (these test the logging pattern we'll embed in the handler)

- [ ] **Step 3: Modify the PATCH handler in dashboard.py**

In `src/pipeline/dashboard.py`, add import at the top:

```python
from src.pipeline.db import log_activity
```

Then modify `_patch_company` (around line 433). The key change: before the UPDATE, read old values; after successful UPDATE, log each changed field. Replace the body of `_patch_company`:

```python
def _patch_company(self, domain: str) -> None:
    try:
        payload = self._read_body()
    except (json.JSONDecodeError, ValueError) as exc:
        self.send_error(400, f"Invalid JSON: {exc}")
        return

    updates = {k: v for k, v in payload.items() if k in _WRITEBACK_FIELDS}
    if not updates:
        self.send_error(400, "No writable fields in payload")
        return

    # Detect actor from query param (?actor=roman), default to 'roman'
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(self.path).query)
    actor = qs.get("actor", ["roman"])[0]

    db_path = self.__class__._db_path

    # Read old values before update
    old_values: dict[str, str | None] = {}
    try:
        with get_connection(db_path) as conn:
            cols = ", ".join(updates.keys())
            row = conn.execute(
                f"SELECT {cols} FROM company_records WHERE domain = ?",
                (domain,),
            ).fetchone()
            if row:
                old_values = {k: (str(row[k]) if row[k] is not None else None) for k in updates}
            else:
                self.send_error(404, f"Domain not found: {domain}")
                return
    except Exception as exc:
        logger.exception("DB read error: %s", exc)
        self.send_error(500, str(exc))
        return

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [domain]
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(5):
        try:
            with get_connection(db_path) as conn:
                cursor = conn.execute(
                    f"UPDATE company_records SET {set_clause} WHERE domain = ?",
                    values,
                )
                if cursor.rowcount == 0:
                    self.send_error(404, f"Domain not found: {domain}")
                    return

            # Log each changed field
            # Determine kind based on field name
            for field, new_val in updates.items():
                new_str = str(new_val) if new_val is not None else None
                old_str = old_values.get(field)
                if old_str == new_str:
                    continue
                kind = "edit"
                if field == "approved_for_sendout" and str(new_val) == "1":
                    kind = "approve"
                log_activity(
                    db_path,
                    domain=domain,
                    field=field,
                    old_value=old_str,
                    new_value=new_str,
                    actor=actor,
                    kind=kind,
                )

            logger.info(
                "PATCH /api/company/%s: updated %s", domain, list(updates.keys())
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "locked" in str(exc).lower() and attempt < 4:
                logger.warning(
                    "DB locked on attempt %d, retrying in %ds…",
                    attempt + 1,
                    attempt + 1,
                )
                time.sleep(attempt + 1)
            else:
                break
        except Exception as exc:
            last_exc = exc
            break
    logger.exception("DB write error: %s", last_exc)
    self.send_error(500, str(last_exc))
```

- [ ] **Step 4: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/dashboard.py tests/test_activity_log.py
git commit -m "feat(M27): PATCH handler logs field changes to activity_log"
```

---

### Task 4: Hook activity logging into compliment regeneration

**Files:**
- Modify: `src/pipeline/dashboard.py` (lines ~544-605)
- Test: `tests/test_activity_log.py`

- [ ] **Step 1: Write the failing test — compliment regen logs**

Append to `tests/test_activity_log.py`:

```python
class TestComplimentLogging:
    def test_compliment_regen_logged_as_regen(self, db_path: Path):
        # Seed a record with existing compliment
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO company_records (id, domain, full_name, profile_id, source, klass, pipeline_stage, compliment_draft) "
                "VALUES ('abc123', 'test.de', 'Test GmbH', 'medtech_germany', 'manual', 'B', 'classified', 'Old compliment')"
            )

        # Simulate what the POST handler does after generating new compliment
        old_compliment = "Old compliment"
        new_compliment = "Beeindruckend ist die Sortimentstiefe…"

        log_activity(
            db_path,
            domain="test.de",
            field="compliment_draft",
            old_value=old_compliment,
            new_value=new_compliment,
            actor="claude",
            kind="regen",
        )

        with get_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM activity_log").fetchone()
        assert row["actor"] == "claude"
        assert row["kind"] == "regen"
        assert row["old_value"] == "Old compliment"
        assert row["new_value"] == "Beeindruckend ist die Sortimentstiefe…"

    def test_first_compliment_logged_as_gen(self, db_path: Path):
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO company_records (id, domain, full_name, profile_id, source, klass, pipeline_stage) "
                "VALUES ('abc123', 'test.de', 'Test GmbH', 'medtech_germany', 'manual', 'B', 'classified')"
            )

        log_activity(
            db_path,
            domain="test.de",
            field="compliment_draft",
            old_value=None,
            new_value="Neues Kompliment…",
            actor="claude",
            kind="gen",
        )

        with get_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM activity_log").fetchone()
        assert row["kind"] == "gen"
        assert row["old_value"] is None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestComplimentLogging -v`

Expected: 2 PASS (these test the pattern)

- [ ] **Step 3: Modify _post_compliment in dashboard.py**

In the `_post_compliment` method, after the successful Claude CLI call and before the DB write, read the old compliment. After the write, log the change:

Find the block (around line 590-600):

```python
        with get_connection(db_path) as conn:
            conn.execute(
                "UPDATE company_records SET compliment_draft = ? WHERE domain = ?",
                (compliment, domain),
            )
```

Replace with:

```python
        # Read old compliment for activity log
        with get_connection(db_path) as conn:
            old_row = conn.execute(
                "SELECT compliment_draft FROM company_records WHERE domain = ?",
                (domain,),
            ).fetchone()
            old_compliment = old_row["compliment_draft"] if old_row else None

        with get_connection(db_path) as conn:
            conn.execute(
                "UPDATE company_records SET compliment_draft = ? WHERE domain = ?",
                (compliment, domain),
            )

        # Log compliment generation
        kind = "gen" if not old_compliment else "regen"
        log_activity(
            db_path,
            domain=domain,
            field="compliment_draft",
            old_value=old_compliment,
            new_value=compliment,
            actor="claude",
            kind=kind,
        )
```

- [ ] **Step 4: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/dashboard.py tests/test_activity_log.py
git commit -m "feat(M27): compliment regen logs to activity_log (gen/regen kind)"
```

---

### Task 5: GET /api/activity endpoint

**Files:**
- Modify: `src/pipeline/dashboard.py`
- Test: `tests/test_activity_log.py`

- [ ] **Step 1: Write the failing test — query_activity helper**

Append to `tests/test_activity_log.py`:

```python
from src.pipeline.db import query_activity


class TestQueryActivity:
    def _seed_logs(self, db_path: Path):
        entries = [
            ("a.de", "klass", "C", "B", "roman", "edit"),
            ("a.de", "region", None, "Bayern", "roman", "edit"),
            ("b.de", "compliment_draft", None, "Toll…", "claude", "gen"),
            ("a.de", "approved_for_sendout", "0", "1", "flo", "approve"),
            ("c.de", "klass", None, "B", "claude", "gen"),
        ]
        for domain, field, old, new, actor, kind in entries:
            log_activity(
                db_path,
                domain=domain,
                field=field,
                old_value=old,
                new_value=new,
                actor=actor,
                kind=kind,
            )

    def test_returns_all_entries_desc(self, db_path: Path):
        self._seed_logs(db_path)
        rows = query_activity(db_path)
        assert len(rows) == 5
        # Newest first (last inserted = newest timestamp)
        assert rows[0]["domain"] == "c.de"

    def test_filter_by_actor(self, db_path: Path):
        self._seed_logs(db_path)
        rows = query_activity(db_path, actor="claude")
        assert len(rows) == 2
        assert all(r["actor"] == "claude" for r in rows)

    def test_filter_by_domain(self, db_path: Path):
        self._seed_logs(db_path)
        rows = query_activity(db_path, domain="a.de")
        assert len(rows) == 3

    def test_limit(self, db_path: Path):
        self._seed_logs(db_path)
        rows = query_activity(db_path, limit=2)
        assert len(rows) == 2

    def test_empty_db(self, db_path: Path):
        rows = query_activity(db_path)
        assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestQueryActivity -v`

Expected: FAIL — `query_activity` not found.

- [ ] **Step 3: Implement query_activity in db.py**

Add to `src/pipeline/db.py`, after `log_activity`:

```python
def query_activity(
    db_path: Path,
    *,
    limit: int = 100,
    actor: str | None = None,
    domain: str | None = None,
) -> list[dict]:
    """Return activity log entries, newest first. Optional filters."""
    clauses: list[str] = []
    params: list[str] = []
    if actor:
        clauses.append("actor = ?")
        params.append(actor)
    if domain:
        clauses.append("domain = ?")
        params.append(domain)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM activity_log {where} ORDER BY timestamp DESC, id DESC LIMIT ?"
    params.append(str(limit))

    with get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_activity_log.py::TestQueryActivity -v`

Expected: 5 PASS

- [ ] **Step 5: Add GET /api/activity route to dashboard.py**

In `src/pipeline/dashboard.py`, add import:

```python
from src.pipeline.db import query_activity
```

Add the handler method in the handler class (after `_serve_data`):

```python
def _serve_activity(self) -> None:
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(self.path).query)
    limit = int(qs.get("limit", ["100"])[0])
    actor = qs.get("actor", [None])[0]
    domain = qs.get("domain", [None])[0]

    db_path = self.__class__._db_path
    rows = query_activity(db_path, limit=limit, actor=actor, domain=domain)

    content = json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(content)))
    self.end_headers()
    self.wfile.write(content)
```

Add the route registration in `do_GET` (where GET routes are matched):

```python
elif self.path.startswith("/api/activity"):
    self._serve_activity()
```

- [ ] **Step 6: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/db.py src/pipeline/dashboard.py tests/test_activity_log.py
git commit -m "feat(M27): GET /api/activity endpoint + query_activity helper"
```

---

### Task 6: Update docs — ROADMAP, ARCHITECTURE, PLAN validation

**Files:**
- Modify: `ai/ROADMAP.md`
- Modify: `ai/ARCHITECTURE.md`

- [ ] **Step 1: Update ROADMAP.md**

In the "Roadmap — Next Milestones" table, add M27 as delivered and renumber backtest harness:

Change M27 row from backtest harness to:
```
| M27 | **Activity tracker backend** — `activity_log` table in pipeline.db, PATCH/POST handlers log per-field changes with actor/kind/timestamp, `GET /api/activity` endpoint with filter/pagination. Spec: `ai/PLAN-M27.md`. | ✅ |
```

Add new row for backtest harness at the end:
```
| M30 | **Backtest harness** — `--backtest` CLI flag for every pipeline stage. Uses 408 BA records as ground truth. | 📋 Planned |
```

- [ ] **Step 2: Update ARCHITECTURE.md**

Add a section for the activity log under the database schema section:

```markdown
### Activity Log (M27)

`activity_log` table tracks per-field changes made through the dashboard API. Each row records: domain, field name, old/new values, actor (claude/roman/flo), kind (edit/gen/regen/enrich/approve/system), and ISO 8601 timestamp. Queried via `GET /api/activity?limit=N&actor=X&domain=Y`.
```

- [ ] **Step 3: Commit docs + final milestone commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add ai/ROADMAP.md ai/ARCHITECTURE.md ai/PLAN-M27.md
git commit -m "docs(M27): activity tracker backend — ROADMAP + ARCHITECTURE updated"
```

- [ ] **Step 4: Push**

```bash
git push
```
