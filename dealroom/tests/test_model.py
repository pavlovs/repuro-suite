"""
Tests for DR-M5: Excel Model Reader.

Unit tests use a tmp_path in-memory DB — no Excel reads.
Golden validation tests compare read_model output vs golden JSON.

Updated for Schema v2: deal_data replaced by deal_financials.
"""

import json
import sqlite3
import uuid

import pytest

from src.db import init_db, _migrate_schema_v2
from src.model import read_model, _reconcile_ebitda
from config import settings


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test_dealroom.db"
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    init_db(c)
    _migrate_schema_v2(c)
    # Seed one deal (using v2 stage name)
    c.execute(
        """INSERT INTO deals (id, code_name, company_name, domain, deal_stage, added_at)
           VALUES (?, 'TestCo', 'Test Company GmbH', 'testco.de', 'valuation', '2026-01-01')""",
        (str(uuid.uuid4()),),
    )
    c.commit()
    return c


# ─── Unit tests ──────────────────────────────────────────────────────────────


def test_read_model_deal_not_found(conn):
    """read_model raises ValueError for unknown deal."""
    with pytest.raises(ValueError, match="Deal not found"):
        read_model(conn, "NonExistent")


def test_read_model_no_model_file(conn):
    """read_model returns error when no model file registered."""
    result = read_model(conn, "TestCo")
    assert result["model_file"] is None
    assert result["pnl_rows_written"] == 0
    assert len(result["errors"]) == 1
    assert "No model file" in result["errors"][0]


def test_reconcile_no_raw_data(conn):
    """Reconciliation with no raw EBITDA data produces zero conflicts."""
    pnl_data = {"2024": {"ebitda_adj": 500.0}}
    conflicts = _reconcile_ebitda(
        conn, "testco.de", pnl_data, "model.xlsx", "2026-01-01"
    )
    assert conflicts == 0


def test_reconcile_matching_data(conn):
    """Reconciliation with matching EBITDA produces zero conflicts."""
    # Insert raw EBITDA into deal_financials
    conn.execute(
        """INSERT INTO deal_financials
           (id, domain, statement, line_item, fiscal_year, period_type,
            value_k, source, extracted_at)
           VALUES (?, 'testco.de', 'pnl', 'ebitda', 2024, 'annual',
                   500.0, 'guv.xlsx', '2026-01-01')""",
        (str(uuid.uuid4()),),
    )
    # Insert model adjusted row
    model_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO deal_financials
           (id, domain, statement, line_item, fiscal_year, period_type,
            value_k, is_adjusted, source, extracted_at)
           VALUES (?, 'testco.de', 'pnl', 'ebitda_adj', 2024, 'annual',
                   510.0, 1, 'model.xlsx', '2026-01-01')""",
        (model_id,),
    )
    conn.commit()

    # 510 vs 500 = 2% diff < 5% threshold
    pnl_data = {"2024": {"ebitda_adj": 510.0}}
    conflicts = _reconcile_ebitda(
        conn, "testco.de", pnl_data, "model.xlsx", "2026-01-01"
    )
    assert conflicts == 0


def test_reconcile_mismatched_data(conn):
    """Reconciliation with >5% EBITDA difference flags conflict."""
    raw_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO deal_financials
           (id, domain, statement, line_item, fiscal_year, period_type,
            value_k, source, extracted_at)
           VALUES (?, 'testco.de', 'pnl', 'ebitda', 2024, 'annual',
                   500.0, 'guv.xlsx', '2026-01-01')""",
        (raw_id,),
    )
    model_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO deal_financials
           (id, domain, statement, line_item, fiscal_year, period_type,
            value_k, is_adjusted, source, extracted_at)
           VALUES (?, 'testco.de', 'pnl', 'ebitda_adj', 2024, 'annual',
                   700.0, 1, 'model.xlsx', '2026-01-01')""",
        (model_id,),
    )
    conn.commit()

    # 700 vs 500 = 40% diff > 5% threshold
    pnl_data = {"2024": {"ebitda_adj": 700.0}}
    conflicts = _reconcile_ebitda(
        conn, "testco.de", pnl_data, "model.xlsx", "2026-01-01"
    )
    assert conflicts == 1


# ─── Golden validation ───────────────────────────────────────────────────────


@pytest.mark.live
class TestGoldenValidation:
    """Compare read_model output against golden dataset files.

    Only runs with: pytest tests/test_model.py -m live
    """

    @pytest.fixture
    def live_conn(self):
        from src.db import get_conn

        return get_conn()

    @pytest.mark.parametrize("code_name", ["Wolf", "Cat", "Octopus"])
    def test_golden_pnl(self, live_conn, code_name):
        """Model GuV extraction matches golden dataset within 2%."""
        golden_path = settings.GOLDEN_DIR / f"{code_name.lower()}.json"
        if not golden_path.exists():
            pytest.skip(f"Golden file not found: {golden_path}")

        golden = json.loads(golden_path.read_text())
        result = read_model(live_conn, code_name, dry_run=True)

        assert not result["errors"], f"Errors: {result['errors']}"
        assert result["pnl_data"], f"No P&L data extracted for {code_name}"

        for yr, golden_vals in golden["pnl"].items():
            assert yr in result["pnl_data"], f"Year {yr} missing from extraction"
            extracted = result["pnl_data"][yr]

            for key, golden_val in golden_vals.items():
                assert key in extracted, f"{yr}.{key} missing from extraction"
                ext_val = extracted[key]

                if golden_val == 0:
                    assert abs(ext_val) < 1, (
                        f"{yr}.{key}: golden=0, extracted={ext_val}"
                    )
                else:
                    pct_diff = abs(ext_val - golden_val) / abs(golden_val) * 100
                    assert pct_diff < 3, (
                        f"{yr}.{key}: golden={golden_val}, extracted={ext_val} "
                        f"({pct_diff:.1f}% diff)"
                    )
