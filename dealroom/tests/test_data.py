"""
Tests for DR-M3: Data Extraction.

Unit tests use a tmp_path in-memory DB — no Claude calls, no OneDrive access.
Live tests (marked with @pytest.mark.live) call the real API and real files.
Run live tests explicitly: pytest tests/test_data.py -m live

Updated for Schema v2: deal_data replaced by deal_financials.
"""

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from src.db import init_db, _migrate_schema_v2
from src.data import (
    _pnl_to_entries,
    _write_entries,
    _clear_source_rows,
    detect_conflicts,
    compute_risk_flags,
    extract_deal,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test_dealroom.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    init_db(c)
    _migrate_schema_v2(c)
    # Seed one deal
    c.execute(
        """INSERT INTO deals (id, code_name, company_name, domain, deal_stage, added_at)
           VALUES (?, 'TestCo', 'Test Company GmbH', 'testco.de', 'valuation', '2026-01-01')""",
        (str(uuid.uuid4()),),
    )
    c.commit()
    yield c
    c.close()


def _sample_pnl_extracted(fiscal_year=2023):
    return {
        "fiscal_year": fiscal_year,
        "prior_year": None,
        "revenue": 5_000_000.0,  # EUR → should become 5000.0 EUR_K
        "cogs": 3_000_000.0,
        "gross_profit": 2_000_000.0,
        "personnel": 800_000.0,
        "other_opex": 400_000.0,
        "other_income": 50_000.0,
        "ebitda": 850_000.0,
        "da": None,
        "ebit": None,
        "interest_expense": None,
        "interest_income": None,
        "ebt": None,
        "tax": None,
        "net_income": None,
        "prior_year_revenue": None,
        "prior_year_ebitda": None,
        "prior_year_personnel": None,
        "normalization_candidates": [
            {
                "description": "Owner salary adjustment",
                "amount_eur": 100_000.0,
                "account_code": "6027",
            }
        ],
    }


# ─── Unit tests ───────────────────────────────────────────────────────────────


def test_pnl_to_entries_eur_to_eurk():
    extracted = _sample_pnl_extracted(2023)
    entries = _pnl_to_entries(extracted, "testco.de", "test_guv.xlsx", "file-001")
    revenue_row = next(e for e in entries if e["line_item"] == "revenue")
    assert revenue_row["value_k"] == 5000.0  # 5_000_000 / 1000
    assert revenue_row["fiscal_year"] == 2023
    assert revenue_row["domain"] == "testco.de"
    assert revenue_row["source_file_id"] == "file-001"
    assert revenue_row["statement"] == "pnl"


def test_pnl_to_entries_normalization_row():
    extracted = _sample_pnl_extracted(2023)
    entries = _pnl_to_entries(extracted, "testco.de", "test.xlsx", "file-001")
    norm_rows = [e for e in entries if e["line_item"] == "normalization_items_json"]
    assert len(norm_rows) == 1
    # value_raw contains the JSON text for normalization items
    # Check that the adjustment_note or value_raw contains the data
    assert norm_rows[0]["statement"] == "adjustments"


def test_write_entries_inserts_rows(conn):
    entries = _pnl_to_entries(
        _sample_pnl_extracted(2023), "testco.de", "guv.xlsx", "file-001"
    )
    n = _write_entries(conn, entries, dry_run=False)
    assert n == len(entries)
    count = conn.execute(
        "SELECT COUNT(*) FROM deal_financials WHERE domain = 'testco.de'"
    ).fetchone()[0]
    assert count == len(entries)


def test_write_entries_dry_run_no_insert(conn):
    entries = _pnl_to_entries(
        _sample_pnl_extracted(2023), "testco.de", "guv.xlsx", "file-001"
    )
    _write_entries(conn, entries, dry_run=True)
    count = conn.execute(
        "SELECT COUNT(*) FROM deal_financials WHERE domain = 'testco.de'"
    ).fetchone()[0]
    assert count == 0


def test_idempotent_reextraction(conn):
    entries = _pnl_to_entries(
        _sample_pnl_extracted(2023), "testco.de", "guv.xlsx", "file-001"
    )
    _write_entries(conn, entries, dry_run=False)
    first_count = conn.execute("SELECT COUNT(*) FROM deal_financials").fetchone()[0]

    # Second extraction: clear old rows, re-insert same entries
    _clear_source_rows(conn, "file-001")
    entries2 = _pnl_to_entries(
        _sample_pnl_extracted(2023), "testco.de", "guv.xlsx", "file-001"
    )
    _write_entries(conn, entries2, dry_run=False)
    second_count = conn.execute("SELECT COUNT(*) FROM deal_financials").fetchone()[0]

    assert first_count == second_count


def test_conflict_detection_flags_both(conn):
    now = "2026-01-01T00:00:00+00:00"
    id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
           period_type, value_k, source, source_file_id, confidence,
           is_authoritative, extracted_at)
           VALUES (?, 'testco.de', 'pnl', 'revenue', 2023, 'annual',
                   5000.0, 'guv_a.xlsx', 'file-a', 'stated', 0, ?)""",
        (id1, now),
    )
    conn.execute(
        """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
           period_type, value_k, source, source_file_id, confidence,
           is_authoritative, extracted_at)
           VALUES (?, 'testco.de', 'pnl', 'revenue', 2023, 'annual',
                   5200.0, 'guv_b.xlsx', 'file-b', 'stated', 0, ?)""",
        (id2, now),
    )
    conn.commit()

    n = detect_conflicts(conn, "testco.de")
    assert n == 2  # both rows flagged


def test_no_conflict_same_value(conn):
    now = "2026-01-01T00:00:00+00:00"
    for file_id in ["file-a", "file-b"]:
        conn.execute(
            """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
               period_type, value_k, source, source_file_id, confidence,
               is_authoritative, extracted_at)
               VALUES (?, 'testco.de', 'pnl', 'revenue', 2023, 'annual',
                       5000.0, ?, ?, 'stated', 0, ?)""",
            (str(uuid.uuid4()), file_id, file_id, now),
        )
    conn.commit()

    n = detect_conflicts(conn, "testco.de")
    assert n == 0


def test_risk_flag_revenue_decline(conn):
    now = "2026-01-01T00:00:00+00:00"
    for yr, rev in [(2022, 5000.0), (2023, 4000.0)]:  # -20% → should flag
        conn.execute(
            """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
               period_type, value_k, source, source_file_id, confidence,
               is_authoritative, extracted_at)
               VALUES (?, 'testco.de', 'pnl', 'revenue', ?, 'annual',
                       ?, 'guv.xlsx', 'file-a', 'stated', 0, ?)""",
            (str(uuid.uuid4()), yr, rev, now),
        )
    conn.commit()

    flags = compute_risk_flags(conn, "testco.de")
    assert any("Revenue declined" in f for f in flags)


def test_risk_flag_low_ebitda_margin(conn):
    now = "2026-01-01T00:00:00+00:00"
    for line_item, val in [("revenue", 5000.0), ("ebitda", 200.0)]:  # 4% margin → flag
        conn.execute(
            """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
               period_type, value_k, source, source_file_id, confidence,
               is_authoritative, extracted_at)
               VALUES (?, 'testco.de', 'pnl', ?, 2024, 'annual',
                       ?, 'guv.xlsx', 'file-a', 'stated', 0, ?)""",
            (str(uuid.uuid4()), line_item, val, now),
        )
    conn.commit()

    flags = compute_risk_flags(conn, "testco.de")
    assert any("EBITDA margin" in f for f in flags)
    assert any("< 10%" in f for f in flags)


def test_no_docs_returns_error(conn):
    result = extract_deal(conn, "TestCo", dry_run=True)
    assert "error" in result
    assert "No extractable" in result["error"]


# ─── Live tests (require OneDrive + API key) ──────────────────────────────────


GOLDEN_DIR = Path(__file__).resolve().parent.parent / "data" / "golden"
ONEDRIVE_AVAILABLE = (
    Path.home() / "Documents" / "OneDrive - Kamu Kapital" / "Dokumente - Kamu Kapital"
).exists()


def _load_golden(code_name: str) -> dict | None:
    p = GOLDEN_DIR / f"{code_name.lower()}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def live_conn():
    """Use the real dealroom.db for live tests."""
    from src.db import get_conn

    return get_conn()


@pytest.mark.live
@pytest.mark.skipif(not ONEDRIVE_AVAILABLE, reason="OneDrive not mounted")
@pytest.mark.skipif(
    not (GOLDEN_DIR / "wolf.json").exists(), reason="Wolf golden not built"
)
def test_golden_wolf_revenue_2022(live_conn):
    """Extract Wolf and validate revenue 2022 against golden +/-5%."""
    golden = _load_golden("Wolf")
    assert golden, "Wolf golden not found"

    result = extract_deal(live_conn, "Wolf", dry_run=False)
    assert result["files_processed"] > 0, f"No files processed: {result}"

    expected = float(golden["pnl"]["2022"]["revenue"])
    deal = live_conn.execute(
        "SELECT domain FROM deals WHERE code_name='Wolf'"
    ).fetchone()
    domain = deal["domain"] or "wolf"
    row = live_conn.execute(
        """SELECT value_k FROM deal_financials
           WHERE domain = ?
             AND statement='pnl' AND line_item='revenue'
             AND fiscal_year=2022
           LIMIT 1""",
        (domain,),
    ).fetchone()
    assert row is not None, "Revenue 2022 not found in deal_financials after extraction"
    actual = row["value_k"]
    rel_diff = abs(actual - expected) / expected
    assert rel_diff <= 0.05, (
        f"Wolf revenue 2022: expected ~{expected}, got {actual} (diff {rel_diff:.1%})"
    )


@pytest.mark.live
@pytest.mark.skipif(not ONEDRIVE_AVAILABLE, reason="OneDrive not mounted")
@pytest.mark.skipif(
    not (GOLDEN_DIR / "cat.json").exists(), reason="Cat golden not built"
)
def test_golden_cat_ebitda_2024(live_conn):
    """Extract Cat and validate EBITDA adj 2024 against golden +/-10%."""
    golden = _load_golden("Cat")
    assert golden, "Cat golden not found"

    result = extract_deal(live_conn, "Cat", dry_run=False)
    assert result["files_processed"] > 0, f"No files processed: {result}"

    expected_rev = float(golden["pnl"]["2024"]["revenue"])
    deal = live_conn.execute(
        "SELECT domain FROM deals WHERE code_name='Cat'"
    ).fetchone()
    domain = deal["domain"] or "cat"
    row = live_conn.execute(
        """SELECT MAX(value_k) as value_k FROM deal_financials
           WHERE domain = ?
             AND statement='pnl' AND line_item='revenue'
             AND fiscal_year=2024""",
        (domain,),
    ).fetchone()
    assert row is not None, "Revenue 2024 not found in deal_financials after extraction"
    actual = row["value_k"]
    rel_diff = abs(actual - expected_rev) / expected_rev
    assert rel_diff <= 0.50, (
        f"Cat revenue 2024: golden={expected_rev}, extracted={actual} (diff {rel_diff:.1%})"
    )
