"""Tests for DR-M4: Deal Workspace Dashboard.

Updated for Schema v2: deal_data replaced by deal_financials.
"""

import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from src.db import init_db, _migrate_schema_v2
from src.dashboard import build_portfolio_data, build_deal_data


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    init_db(c)
    _migrate_schema_v2(c)

    now = datetime.now(timezone.utc)
    ten_days_ago = (now - timedelta(days=10)).isoformat()
    five_days_ago = (now - timedelta(days=5)).isoformat()

    # Seed deals (using v2 stage names)
    for code, company, domain, stage in [
        ("Alpha", "Alpha GmbH", "alpha.de", "offer"),
        ("Beta", "Beta GmbH", None, "valuation"),
    ]:
        c.execute(
            """INSERT INTO deals (id, code_name, company_name, domain, deal_stage,
               stage_entered_at, last_contact_at, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                code,
                company,
                domain,
                stage,
                ten_days_ago,
                five_days_ago,
                now.isoformat(),
            ),
        )

    # Seed deal_financials for Alpha
    for yr, line_item, val in [
        (2023, "revenue", 5000.0),
        (2023, "ebitda", 500.0),
        (2024, "revenue", 5500.0),
    ]:
        c.execute(
            """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
               period_type, value_k, source, confidence, is_authoritative,
               extracted_at)
               VALUES (?, 'alpha.de', 'pnl', ?, ?, 'annual', ?,
                       'test.xlsx', 'stated', 0, ?)""",
            (str(uuid.uuid4()), line_item, yr, val, now.isoformat()),
        )

    # Add conflicting entries for Alpha revenue 2022
    for val, src in [(5000.0, "guv_a.xlsx"), (5200.0, "guv_b.xlsx")]:
        cid = str(uuid.uuid4())
        c.execute(
            """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
               period_type, value_k, source, confidence, is_authoritative,
               extracted_at)
               VALUES (?, 'alpha.de', 'pnl', 'revenue', 2022, 'annual',
                       ?, ?, 'stated', 0, ?)""",
            (cid, val, src, now.isoformat()),
        )

    # Seed documents
    c.execute(
        """INSERT INTO deal_documents (id, domain, code_name, file_path, doc_type,
           doc_subtype, file_name, registered_at)
           VALUES (?, 'alpha.de', 'Alpha', '/test/guv.xlsx', 'financials_raw', 'guv',
                   'guv_2023.xlsx', ?)""",
        (str(uuid.uuid4()), now.isoformat()),
    )

    # Seed notes
    c.execute(
        """INSERT INTO deal_notes (id, domain, note, author, created_at)
           VALUES (?, 'alpha.de', 'First note', 'Roman', ?)""",
        (str(uuid.uuid4()), ten_days_ago),
    )
    c.execute(
        """INSERT INTO deal_notes (id, domain, note, author, created_at)
           VALUES (?, 'alpha.de', 'Second note', 'Roman', ?)""",
        (str(uuid.uuid4()), five_days_ago),
    )

    c.commit()
    yield c
    c.close()


def test_portfolio_data_has_all_deals(conn):
    data = build_portfolio_data(conn)
    assert data["mode"] == "portfolio"
    codes = [d["code_name"] for d in data["deals"]]
    assert "Alpha" in codes
    assert "Beta" in codes


def test_portfolio_has_financial_fields(conn):
    data = build_portfolio_data(conn)
    alpha = next(d for d in data["deals"] if d["code_name"] == "Alpha")
    # New portfolio schema: financial metrics, status text, no raw stage/conflict counts
    assert "rev_m" in alpha
    assert "ebitda_m" in alpha
    assert "ebitda_pct" in alpha
    assert "employees" in alpha
    assert "ev_m" in alpha
    assert "multiple" in alpha
    assert "status_text" in alpha
    assert "description" in alpha
    assert "strategic_fit" in alpha


def test_deal_data_has_financials(conn):
    data = build_deal_data(conn, "Alpha")
    assert data["mode"] == "deal"
    assert "2023" in data["financials"]["pnl"]
    assert data["financials"]["pnl"]["2023"]["revenue"]["primary"]["value"] == 5000.0


def test_deal_multiple_sources(conn):
    data = build_deal_data(conn, "Alpha")
    pnl_2022 = data["financials"]["pnl"].get("2022", {})
    rev = pnl_2022.get("revenue", {})
    assert len(rev["sources"]) == 2  # two conflicting entries


def test_deal_conflict_flagged(conn):
    data = build_deal_data(conn, "Alpha")
    pnl_2022 = data["financials"]["pnl"].get("2022", {})
    rev = pnl_2022.get("revenue", {})
    assert rev["primary"].get("conflict") is True


def test_documents_present(conn):
    data = build_deal_data(conn, "Alpha")
    assert len(data["documents"]) == 1
    assert data["documents"][0]["doc_type"] == "financials_raw"


def test_notes_newest_first(conn):
    data = build_deal_data(conn, "Alpha")
    assert len(data["notes"]) == 2
    assert data["notes"][0]["note"] == "Second note"
    assert data["notes"][1]["note"] == "First note"


def test_deal_not_found(conn):
    with pytest.raises(ValueError, match="not found"):
        build_deal_data(conn, "NonExistent")


# ─── Overview tests (DR-M8) ─────────────────────────────────────────────────


def test_overview_present(conn):
    """build_deal_data returns an overview dict."""
    data = build_deal_data(conn, "Alpha")
    assert "overview" in data
    ov = data["overview"]
    assert isinstance(ov, dict)


def test_overview_financial_snapshot(conn):
    """Overview populates latest-year revenue/EBITDA from deal_financials."""
    data = build_deal_data(conn, "Alpha")
    ov = data["overview"]
    # Alpha has revenue for 2023 (5000) and 2024 (5500) — latest is 2024
    assert ov.get("revenue_k") == 5500.0
    assert ov.get("revenue_year") == 2024
    # Alpha has EBITDA only for 2023
    assert ov.get("ebitda_k") == 500.0
    assert ov.get("ebitda_year") == 2023


def test_overview_no_allex_no_crash(conn):
    """Overview works without ALLEX data (no pipeline.db attached)."""
    data = build_deal_data(conn, "Beta")
    ov = data["overview"]
    # Should have empty/None ALLEX fields, not crash
    assert ov.get("legal_name") is None
    assert ov.get("employees") is None


def test_overview_ebitda_margin(conn):
    """EBITDA margin computed when both revenue and EBITDA exist for same year."""
    data = build_deal_data(conn, "Alpha")
    ov = data["overview"]
    if ov.get("revenue_k") and ov.get("ebitda_k"):
        assert ov.get("ebitda_margin_pct") is not None


def test_overview_financial_timeline(conn):
    """Financial timeline contains revenue per year from deal_financials."""
    data = build_deal_data(conn, "Alpha")
    tl = data["overview"].get("financial_timeline", {})
    # Alpha has revenue for 2023 and 2024, EBITDA for 2023
    assert "2023" in tl
    assert "2024" in tl
    assert tl["2023"]["revenue"] == 5000.0
    assert tl["2024"]["revenue"] == 5500.0
    # EBITDA 2023 falls back to raw since no adj exists
    assert tl["2023"]["ebitda_adj"] == 500.0


def test_overview_timeline_empty_for_no_data(conn):
    """Beta deal with no financial data has empty timeline."""
    data = build_deal_data(conn, "Beta")
    tl = data["overview"].get("financial_timeline", {})
    assert tl == {}
