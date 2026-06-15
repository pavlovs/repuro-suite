"""Tests for M16 — BA Prep Editing Console.

Covers:
- compliment_2 DB schema migration
- Serienbriefe ingest K1/K2 mapping + upsert guard
- Compliment generation (dual output, fallback on malformed JSON)
- build-compliment-guide --dry-run
- compliment_guide.md loading fallback
- Export: Kompliment 2 from DB (not hardcoded)
- dashboard /api/ingest-domain endpoint
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.pipeline import db as pipeline_db
from src.pipeline.db import ensure_schema, get_connection, upsert_serienbriefe_record
from src.pipeline.export import (
    _generate_compliment_cli,
    _parse_compliment_json,
    _record_to_row,
)
from src.pipeline.models import CompanyRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_pipeline.db"
    ensure_schema(db)
    return db


def _insert_record(db: Path, domain: str, **kwargs) -> None:
    rec_id = hashlib.md5(domain.encode()).hexdigest()[:12]
    defaults = {
        "id": rec_id,
        "domain": domain,
        "full_name": "Test GmbH",
        "profile_id": "test",
        "source": "test",
        "pipeline_stage": "ingested",
        "ingested_at": "2026-01-01T00:00:00",
    }
    defaults.update(kwargs)
    with get_connection(db) as conn:
        placeholders = ", ".join(f":{k}" for k in defaults)
        cols = ", ".join(defaults.keys())
        conn.execute(
            f"INSERT INTO company_records ({cols}) VALUES ({placeholders})", defaults
        )


# ---------------------------------------------------------------------------
# 1. DB migration — compliment_2 column
# ---------------------------------------------------------------------------


def test_compliment_2_column_added(tmp_path):
    db = tmp_path / "fresh.db"
    ensure_schema(db)
    conn = sqlite3.connect(db)
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
    }
    conn.close()
    assert "compliment_2" in cols


def test_compliment_2_column_migration(tmp_path):
    """ensure_schema on a DB that was created without compliment_2 adds the column."""
    db = tmp_path / "old.db"
    # Create table manually without compliment_2
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE company_records (
        id TEXT PRIMARY KEY, domain TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL, profile_id TEXT NOT NULL,
        source TEXT NOT NULL, pipeline_stage TEXT NOT NULL DEFAULT 'ingested',
        already_approached INTEGER NOT NULL DEFAULT 0, ingested_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()
    ensure_schema(db)
    conn = sqlite3.connect(db)
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
    }
    conn.close()
    assert "compliment_2" in cols


# ---------------------------------------------------------------------------
# 2. Serienbriefe ingest — K1/K2 mapping
# ---------------------------------------------------------------------------


def _make_sb_rec(domain: str, k1: str = None, k2: str = None) -> dict:
    rec_id = hashlib.md5(domain.encode()).hexdigest()
    return {
        "id": rec_id,
        "domain": domain,
        "full_name": "Test GmbH",
        "profile_id": "medtech_germany",
        "source": "serienbriefe",
        "pipeline_stage": "approached",
        "briefaktion": "BA1",
        "outreach_status": "sent",
        "outreach_sent_at": "2025-06-10",
        "outreach_comment": None,
        "klass": "B",
        "owner_name": None,
        "gesellschafter_name": None,
        "gf_email": None,
        "gf_phone": None,
        "gesellschafter_age": None,
        "anrede": None,
        "salutation": None,
        "hrb_number": None,
        "rechtsform": None,
        "ma_count": None,
        "city": None,
        "street": None,
        "plz_ort": None,
        "compliment_draft": k1,
        "compliment_2": k2,
    }


def test_serienbriefe_ingest_maps_compliments(tmp_path):
    db = _tmp_db(tmp_path)
    rec = _make_sb_rec(
        "test-k1-k2.de", k1="Ihre Erfahrung...", k2="Ihr Servicekonzept..."
    )
    with get_connection(db) as conn:
        upsert_serienbriefe_record(conn, rec, "2026-01-01T00:00:00")

    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT compliment_draft, compliment_2 FROM company_records WHERE domain = ?",
            ("test-k1-k2.de",),
        ).fetchone()
    assert row["compliment_draft"] == "Ihre Erfahrung..."
    assert row["compliment_2"] == "Ihr Servicekonzept..."


def test_serienbriefe_ingest_does_not_overwrite_existing(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(
        db, "existing.de", compliment_draft="Original K1", compliment_2="Original K2"
    )
    rec = _make_sb_rec("existing.de", k1="New K1", k2="New K2")
    with get_connection(db) as conn:
        upsert_serienbriefe_record(conn, rec, "2026-01-01T00:00:00")

    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT compliment_draft, compliment_2 FROM company_records WHERE domain = ?",
            ("existing.de",),
        ).fetchone()
    assert row["compliment_draft"] == "Original K1"
    assert row["compliment_2"] == "Original K2"


def test_serienbriefe_ingest_fills_null_compliments(tmp_path):
    """Existing record with NULL compliments gets them filled on upsert."""
    db = _tmp_db(tmp_path)
    _insert_record(db, "nullcompliment.de")
    rec = _make_sb_rec(
        "nullcompliment.de", k1="Ihre Expertise...", k2="Ihr Produktsortiment..."
    )
    with get_connection(db) as conn:
        upsert_serienbriefe_record(conn, rec, "2026-01-01T00:00:00")

    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT compliment_draft, compliment_2 FROM company_records WHERE domain = ?",
            ("nullcompliment.de",),
        ).fetchone()
    assert row["compliment_draft"] == "Ihre Expertise..."
    assert row["compliment_2"] == "Ihr Produktsortiment..."


# ---------------------------------------------------------------------------
# 3. Compliment generation — dual output
# ---------------------------------------------------------------------------


def test_parse_compliment_json_valid():
    # Post-processing (M23) strips trailing periods and applies grammar fixes
    k1, k2 = _parse_compliment_json(
        '{"k1": "Ihre Erfahrung", "k2": "hat uns Ihr Konzept beeindruckt"}'
    )
    assert k1 == "Ihre Erfahrung"
    assert k2 == "hat uns Ihr Konzept beeindruckt"


def test_parse_compliment_json_with_fences():
    raw = '```json\n{"k1": "Ihre Erfahrung", "k2": "hat uns Ihr Konzept beeindruckt"}\n```'
    k1, k2 = _parse_compliment_json(raw)
    assert k1 == "Ihre Erfahrung"
    assert k2 == "hat uns Ihr Konzept beeindruckt"


def test_parse_compliment_json_malformed():
    k1, k2 = _parse_compliment_json("Not JSON at all")
    assert k1 is None
    assert k2 is None


def test_generate_compliment_cli_returns_k1_k2():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = (
        '{"k1": "die Erfahrung im Bereich", "k2": "hat uns das Produkt beeindruckt"}'
    )
    with patch("src.pipeline.export.subprocess.run", return_value=mock_result):
        k1, k2 = _generate_compliment_cli("Test GmbH", "website text")
    assert k1 == "die Erfahrung im Bereich"
    assert k2 == "hat uns das Produkt beeindruckt"


def test_generate_compliment_cli_fallback_on_malformed():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Nicht JSON"
    with patch("src.pipeline.export.subprocess.run", return_value=mock_result):
        k1, k2 = _generate_compliment_cli("Test GmbH", "website text")
    assert k1 is None
    assert k2 is None


# ---------------------------------------------------------------------------
# 4. Compliment guide — dry-run and fallback
# ---------------------------------------------------------------------------


def test_build_compliment_guide_dry_run(tmp_path, capsys):
    guide_path = tmp_path / "compliment_guide.md"
    # Should NOT create file in dry-run
    from src.pipeline.compliment_guide import build_guide
    import unittest.mock as _mock

    # Mock the corpus load so test doesn't need source Excel
    with _mock.patch(
        "src.pipeline.compliment_guide._load_corpus",
        return_value=[
            {"domain": "test1.de", "k1": "Ihre Erfahrung...", "k2": "Ihr Konzept..."},
            {"domain": "test2.de", "k1": "Ihre Kompetenz...", "k2": "Ihr Service..."},
        ],
    ):
        stats = build_guide(dry_run=True, output_path=guide_path)

    assert not guide_path.exists(), "dry-run must not create guide file"
    assert stats["k1_count"] == 2
    assert stats["k2_count"] == 2
    assert stats["guide_written"] is False


def test_compliment_prompt_loads_guide(tmp_path, monkeypatch):
    """If compliment_guide.md exists, _load_compliment_guide returns its content."""
    from src.pipeline.export import _load_compliment_guide
    import src.pipeline.export as _export_mod

    fake_guide = tmp_path / "compliment_guide.md"
    fake_guide.write_text("# Test Guide\nSome patterns.", encoding="utf-8")
    monkeypatch.setattr(_export_mod, "_GUIDE_PATH", fake_guide)

    result = _load_compliment_guide()
    assert "Test Guide" in result


def test_compliment_prompt_fallback_if_guide_missing(tmp_path, monkeypatch):
    """If compliment_guide.md is missing, _load_compliment_guide returns empty string."""
    from src.pipeline.export import _load_compliment_guide
    import src.pipeline.export as _export_mod

    monkeypatch.setattr(_export_mod, "_GUIDE_PATH", tmp_path / "nonexistent.md")
    result = _load_compliment_guide()
    assert result == ""


# ---------------------------------------------------------------------------
# 5. Export — Kompliment 2 from DB
# ---------------------------------------------------------------------------


def test_export_kompliment_2_in_output(tmp_path):
    rec = CompanyRecord(
        domain="testexport.de",
        full_name="Test GmbH",
        profile_id="test",
        source="test",
        klass="B",
        compliment_draft="Ihre Erfahrung...",
        compliment_2="Ihr Servicekonzept...",
    )
    raw = {}
    row = _record_to_row(rec, raw)
    assert row["Kompliment 1"] == "Ihre Erfahrung..."
    assert row["Kompliment 2"] == "Ihr Servicekonzept..."


def test_export_kompliment_2_empty_when_null(tmp_path):
    rec = CompanyRecord(
        domain="testexport2.de",
        full_name="Test GmbH",
        profile_id="test",
        source="test",
        klass="B",
    )
    row = _record_to_row(rec, {})
    assert row["Kompliment 2"] == ""


# ---------------------------------------------------------------------------
# 6. db.update_compliments
# ---------------------------------------------------------------------------


def test_update_compliments_fills_both(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "updatetest.de")
    with get_connection(db) as conn:
        pipeline_db.update_compliments(conn, "updatetest.de", "K1 text", "K2 text")
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT compliment_draft, compliment_2 FROM company_records WHERE domain = ?",
            ("updatetest.de",),
        ).fetchone()
    assert row["compliment_draft"] == "K1 text"
    assert row["compliment_2"] == "K2 text"


def test_update_compliments_does_not_overwrite_existing(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(
        db, "updatetest2.de", compliment_draft="Existing K1", compliment_2="Existing K2"
    )
    with get_connection(db) as conn:
        pipeline_db.update_compliments(conn, "updatetest2.de", "New K1", "New K2")
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT compliment_draft, compliment_2 FROM company_records WHERE domain = ?",
            ("updatetest2.de",),
        ).fetchone()
    assert row["compliment_draft"] == "Existing K1"
    assert row["compliment_2"] == "Existing K2"
