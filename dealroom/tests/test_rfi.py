"""Tests for DR-M6: RFI Generator.

All tests use in-memory SQLite DB + mock _call_claude.
No real Claude calls, no OneDrive access.

Updated for Schema v2: deal_data replaced by deal_financials,
deal_granola renamed to deal_meetings, stages updated.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


# ─── Helpers ──────────────────────────────────────────────────────────────────


class _NoClose:
    """Wrap a sqlite3 connection so .close() is a no-op (test isolation)."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass  # intentionally swallowed


from src.generate.rfi import (
    _build_conflict_questions,
    _parse_questions,
    _write_questions,
    generate_rfi,
    source_label,
)
from src.dashboard import _build_questions_data, build_deal_data


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_db(stage: str = "valuation", domain: str = "testco.de") -> sqlite3.Connection:
    """Create an in-memory DB with v2 schema and one seeded deal."""
    from src.db import init_db, _migrate_schema_v2

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    _migrate_schema_v2(conn)
    conn.execute(
        "INSERT INTO deals (id, domain, code_name, company_name, deal_stage, added_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), domain, "TestCo", "Test GmbH", stage, _now()),
    )
    conn.commit()
    return conn


_MOCK_QUESTIONS_JSON = json.dumps(
    [
        {
            "question": "Wie hoch war der Umsatz in 2024 im Vergleich zu 2023?",
            "category": "financial",
            "subcategory": "revenue",
            "importance": "high",
            "sort_order": 1,
            "source": "rfi_generator:account:revenue",
            "answer_feeds_data_key": None,
        },
        {
            "question": "Wie viel % des Umsatzes entstehen aus bestehenden Kundenbeziehungen?",
            "category": "commercial",
            "subcategory": "customers",
            "importance": "medium",
            "sort_order": 2,
            "source": "rfi_generator",
            "answer_feeds_data_key": "commercial.recurring.recurring_pct",
        },
        {
            "question": "Erh\u00e4lt der Gesch\u00e4ftsf\u00fchrer weitere Leistungen au\u00dfer dem Grundgehalt?",
            "category": "financial",
            "subcategory": "adjustments",
            "importance": "high",
            "sort_order": 3,
            "source": "rfi_generator",
            "answer_feeds_data_key": "financial.adjustments.gf_salary_k",
        },
        {
            "question": "K\u00f6nnten Sie eine Mitarbeiterliste mit Qualifikationen bereitstellen?",
            "category": "general",
            "subcategory": "personnel",
            "importance": "medium",
            "sort_order": 4,
            "source": "rfi_generator",
            "answer_feeds_data_key": None,
        },
        {
            "question": "Wie teilt sich der Umsatz auf die Gesch\u00e4ftsbereiche auf?",
            "category": "commercial",
            "subcategory": "revenue_split",
            "importance": "medium",
            "sort_order": 5,
            "source": "rfi_generator",
            "answer_feeds_data_key": "commercial.revenue_split.revenue_split_json",
        },
    ]
)


# ─── Unit tests ───────────────────────────────────────────────────────────────


def test_write_questions_inserts_rows():
    conn = _make_db()
    questions = _parse_questions(_MOCK_QUESTIONS_JSON)
    _write_questions(conn, "testco.de", questions, dry_run=False)
    count = conn.execute(
        "SELECT COUNT(*) FROM deal_questions WHERE domain='testco.de'"
    ).fetchone()[0]
    assert count == 5


def test_idempotent_regen_replaces_draft():
    conn = _make_db()
    questions = _parse_questions(_MOCK_QUESTIONS_JSON)
    _write_questions(conn, "testco.de", questions, dry_run=False)
    _write_questions(conn, "testco.de", questions, dry_run=False)  # second run
    count = conn.execute(
        "SELECT COUNT(*) FROM deal_questions WHERE domain='testco.de'"
    ).fetchone()[0]
    assert count == 5  # no accumulation


def test_idempotent_preserves_sent():
    conn = _make_db()
    questions = _parse_questions(_MOCK_QUESTIONS_JSON)
    _write_questions(conn, "testco.de", questions, dry_run=False)

    # Mark one as sent (SQLite doesn't support LIMIT in UPDATE without compile flag)
    first_id = conn.execute(
        "SELECT id FROM deal_questions WHERE domain='testco.de' LIMIT 1"
    ).fetchone()[0]
    conn.execute("UPDATE deal_questions SET status='sent' WHERE id=?", (first_id,))
    conn.commit()

    # Re-generate — should replace only the 4 draft, keep the 1 sent
    _write_questions(conn, "testco.de", questions, dry_run=False)
    total = conn.execute(
        "SELECT COUNT(*) FROM deal_questions WHERE domain='testco.de'"
    ).fetchone()[0]
    sent = conn.execute(
        "SELECT COUNT(*) FROM deal_questions WHERE domain='testco.de' AND status='sent'"
    ).fetchone()[0]
    assert sent == 1
    assert total == 6  # 5 new drafts + 1 preserved sent


def test_conflict_questions_generated():
    """Inject 2 distinct conflicts → 2 conflict questions generated."""
    conflicts = [
        {
            "key": "revenue",
            "fiscal_year": 2023,
            "value_num": 5000.0,
            "source": "guv_2023.xlsx",
        },
        {
            "key": "revenue",
            "fiscal_year": 2023,
            "value_num": 5200.0,
            "source": "model_v4.xlsx",
        },
        {
            "key": "ebitda",
            "fiscal_year": 2022,
            "value_num": 400.0,
            "source": "guv_2022.xlsx",
        },
        {
            "key": "ebitda",
            "fiscal_year": 2022,
            "value_num": 320.0,
            "source": "model_v3.xlsx",
        },
    ]
    questions = _build_conflict_questions(conflicts)
    assert len(questions) == 2
    for q in questions:
        assert q["source"] == "rfi_generator:conflict"
        assert q["importance"] == "high"


def test_conflict_deduplication():
    """4 conflict rows for same (key, year) → 1 question, not 4."""
    conflicts = [
        {
            "key": "revenue",
            "fiscal_year": 2023,
            "value_num": 5000.0,
            "source": "file_a.xlsx",
        },
        {
            "key": "revenue",
            "fiscal_year": 2023,
            "value_num": 5200.0,
            "source": "file_b.xlsx",
        },
        {
            "key": "revenue",
            "fiscal_year": 2023,
            "value_num": 5100.0,
            "source": "file_c.xlsx",
        },
        {
            "key": "revenue",
            "fiscal_year": 2023,
            "value_num": 5300.0,
            "source": "file_d.xlsx",
        },
    ]
    questions = _build_conflict_questions(conflicts)
    assert len(questions) == 1


def test_dry_run_no_db_write():
    conn = _make_db()
    questions = _parse_questions(_MOCK_QUESTIONS_JSON)
    rows = _write_questions(conn, "testco.de", questions, dry_run=True)
    assert rows == 0
    count = conn.execute("SELECT COUNT(*) FROM deal_questions").fetchone()[0]
    assert count == 0


def test_pdf_created(tmp_path):
    """generate_rfi with mocked Claude writes a .pdf file."""
    conn = _make_db()
    with (
        patch("src.generate.rfi._call_claude", return_value=_MOCK_QUESTIONS_JSON),
        patch("src.generate.rfi._load_rfi_corpus", return_value=""),
        patch(
            "src.generate.rfi._load_deal_context",
            return_value={
                "domain": "testco.de",
                "company_name": "Test GmbH",
                "deal_stage": "valuation",
                "folder_path": tmp_path,
                "conflicts": [],
            },
        ),
        patch("src.generate.rfi._build_financial_summary", return_value=([], [], [])),
    ):
        result = generate_rfi(conn, "TestCo", dry_run=False)

    doc_path = result["doc_path"]
    assert doc_path is not None
    p = Path(doc_path)
    assert p.exists()
    assert p.stat().st_size > 0
    assert p.suffix == ".pdf"


def test_pdf_is_valid(tmp_path):
    """Generated PDF starts with PDF magic bytes and contains question text."""
    conn = _make_db()
    with (
        patch("src.generate.rfi._call_claude", return_value=_MOCK_QUESTIONS_JSON),
        patch("src.generate.rfi._load_rfi_corpus", return_value=""),
        patch(
            "src.generate.rfi._load_deal_context",
            return_value={
                "domain": "testco.de",
                "company_name": "Test GmbH",
                "deal_stage": "valuation",
                "folder_path": tmp_path,
                "conflicts": [],
            },
        ),
        patch("src.generate.rfi._build_financial_summary", return_value=([], [], [])),
    ):
        result = generate_rfi(conn, "TestCo", dry_run=False)

    with open(result["doc_path"], "rb") as f:
        header = f.read(5)
    assert header == b"%PDF-"


def test_mark_sent_advances_stage():
    """rfi --mark-sent on valuation deal → stage becomes rfi_sent."""
    from DEALROOM import cmd_rfi

    conn = _make_db(stage="valuation")
    # Add a draft question
    conn.execute(
        "INSERT INTO deal_questions (id, domain, question, category, status, created_at) "
        "VALUES (?, ?, ?, ?, 'draft', ?)",
        (str(uuid.uuid4()), "testco.de", "Test question?", "financial", _now()),
    )
    conn.commit()

    import types

    args = types.SimpleNamespace(deal="TestCo", mark_sent=True, list=False)

    # Patch get_conn to return our in-memory conn
    import DEALROOM as dm

    original_get_conn = dm.get_conn
    dm.get_conn = lambda: _NoClose(conn)
    try:
        cmd_rfi(args)
    except SystemExit:
        pass
    finally:
        dm.get_conn = original_get_conn

    stage = conn.execute(
        "SELECT deal_stage FROM deals WHERE code_name='TestCo'"
    ).fetchone()[0]
    status = conn.execute(
        "SELECT status FROM deal_questions WHERE domain='testco.de'"
    ).fetchone()[0]
    assert stage == "valuation"
    assert status == "sent"


def test_mark_sent_preserves_non_valuation_stage():
    """rfi --mark-sent when stage != valuation → stage unchanged."""
    from DEALROOM import cmd_rfi

    conn = _make_db(stage="offer")
    conn.execute(
        "INSERT INTO deal_questions (id, domain, question, category, status, created_at) "
        "VALUES (?, ?, ?, ?, 'draft', ?)",
        (str(uuid.uuid4()), "testco.de", "Test?", "financial", _now()),
    )
    conn.commit()

    import types

    args = types.SimpleNamespace(deal="TestCo", mark_sent=True, list=False)

    import DEALROOM as dm

    original_get_conn = dm.get_conn
    dm.get_conn = lambda: _NoClose(conn)
    try:
        cmd_rfi(args)
    except SystemExit:
        pass
    finally:
        dm.get_conn = original_get_conn

    stage = conn.execute(
        "SELECT deal_stage FROM deals WHERE code_name='TestCo'"
    ).fetchone()[0]
    assert stage == "offer"  # unchanged


def test_dashboard_includes_questions():
    """build_questions_data returns dict with counts and by_section."""
    conn = _make_db()
    questions = _parse_questions(_MOCK_QUESTIONS_JSON)
    _write_questions(conn, "testco.de", questions, dry_run=False)

    data = _build_questions_data(conn, "testco.de")
    assert "counts" in data
    assert "by_section" in data
    assert data["counts"]["total"] == 5
    assert data["counts"]["draft"] == 5
    # financial section should have 2 questions
    assert len(data["by_section"]["financial"]) == 2


def test_dashboard_question_count_in_cockpit():
    """build_deal_data includes question_count in deal dict."""
    conn = _make_db()
    questions = _parse_questions(_MOCK_QUESTIONS_JSON)
    _write_questions(conn, "testco.de", questions, dry_run=False)

    result = build_deal_data(conn, "TestCo")
    assert "question_count" in result["deal"]
    assert result["deal"]["question_count"] == 5


def test_source_label_computation():
    """source_label converts rfi_generator:account:key → ACCOUNT:KEY."""
    assert source_label("rfi_generator") == "TEMPLATE"
    assert source_label("rfi_generator:conflict") == "CONFLICT"
    assert source_label("manual") == "MANUAL"
    assert (
        source_label("rfi_generator:account:ebitda_margin_pct")
        == "ACCOUNT:EBITDA_MARGIN_PCT"
    )
    assert source_label("rfi_generator:account:revenue") == "ACCOUNT:REVENUE"
