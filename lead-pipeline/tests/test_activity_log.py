"""Tests for activity_log table and logging (M27)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.db import ensure_schema, get_connection, log_activity


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test_pipeline.db"
    ensure_schema(p)
    return p


class TestActivityLogSchema:
    def test_table_exists(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "activity_log" in tables

    def test_columns(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            cols = {
                r[1] for r in conn.execute("PRAGMA table_info(activity_log)").fetchall()
            }
        assert {
            "id",
            "domain",
            "actor",
            "field",
            "old_value",
            "new_value",
            "changed_at",
        } <= cols

    def test_indexes_exist(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            indexes = {
                r[1]
                for r in conn.execute(
                    "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='activity_log'"
                ).fetchall()
            }
        assert "idx_activity_domain" in indexes
        assert "idx_activity_changed_at" in indexes

    def test_ensure_schema_idempotent(self, db_path: Path) -> None:
        ensure_schema(db_path)  # second call must not raise
        with get_connection(db_path) as conn:
            conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()


class TestLogActivity:
    def test_logs_single_change(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            log_activity(conn, "example.de", "roman", "klass", "C", "A")
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT * FROM activity_log").fetchall()
        assert len(rows) == 1
        r = rows[0]
        assert r["domain"] == "example.de"
        assert r["actor"] == "roman"
        assert r["field"] == "klass"
        assert r["old_value"] == "C"
        assert r["new_value"] == "A"

    def test_null_old_value(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            log_activity(conn, "example.de", "flo", "owner_name", None, "Schmidt")
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM activity_log").fetchone()
        assert row["old_value"] is None
        assert row["new_value"] == "Schmidt"

    def test_null_actor_defaults_to_unknown(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            log_activity(conn, "example.de", "", "klass", "D", "B")
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT * FROM activity_log").fetchone()
        assert row["actor"] == "unknown"

    def test_multiple_changes_ordered(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            log_activity(conn, "a.de", "roman", "klass", "C", "B")
            log_activity(conn, "a.de", "flo", "owner_name", None, "Müller")
            log_activity(conn, "b.de", "roman", "klass", "D", "A")
        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT domain, field FROM activity_log ORDER BY id"
            ).fetchall()
        assert len(rows) == 3
        assert rows[0]["domain"] == "a.de" and rows[0]["field"] == "klass"
        assert rows[1]["field"] == "owner_name"
        assert rows[2]["domain"] == "b.de"

    def test_domain_filter_query(self, db_path: Path) -> None:
        with get_connection(db_path) as conn:
            log_activity(conn, "target.de", "roman", "klass", "C", "A")
            log_activity(conn, "other.de", "roman", "klass", "D", "B")
        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM activity_log WHERE domain = ?", ("target.de",)
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["domain"] == "target.de"
