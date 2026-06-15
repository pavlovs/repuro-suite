"""DR-M7: Tests for the interactive valuation model engine.

Updated for Schema v2: deal_data replaced by deal_financials.
"""

import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from src.valuation import (
    compute_adj_pnl,
    compute_cagr,
    compute_earnout_matrix,
    compute_pnl_kpis,
    compute_proforma_ebit,
    compute_waterfall,
    consolidate_entities,
    build_model_context,
    load_model_params,
    save_model_params,
)
from src.db import init_db, _migrate_schema_v2


# ═══════════════════════════════════════════════════════════════════════════════
# Pure computation tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestComputeAdjPnl:
    """Tests for compute_adj_pnl — raw P&L + adjustments → adjusted P&L."""

    def test_basic_no_adjustments(self):
        raw = {
            "2022": {
                "revenue": 3400,
                "cogs": 1969,
                "personnel": 776,
                "other_opex": 391,
                "other_income": 37,
                "da": 18,
            },
        }
        result = compute_adj_pnl(raw, [], None, ["2022"])
        s = result["summary"]["2022"]
        assert s["total_sales"] == 3400
        assert s["gross_margin"] == 3400 - 1969  # 1431
        assert s["ebitda_adj"] == 3400 - 1969 - 776 - 391 + 37  # 301
        assert s["ebit_adj"] == 301 - 18  # 283

    def test_with_manual_adjustment(self):
        raw = {
            "2022": {
                "revenue": 1000,
                "cogs": 400,
                "personnel": 200,
                "other_opex": 50,
                "other_income": 10,
                "da": 5,
            }
        }
        adj = [
            {
                "category": "personnel",
                "description": "Add back owner salary",
                "amounts": {"2022": -50},
            }
        ]
        result = compute_adj_pnl(raw, adj, None, ["2022"])
        s = result["summary"]["2022"]
        # personnel raw=200, adj=-50 → adjusted pex = 200+(-50) = 150 (but cost subtracted)
        # EBITDA = 1000 - 400 - 150 - 50 + 10 = 410
        assert s["ebitda_adj"] == 410

    def test_gf_salary_adjustment(self):
        raw = {
            "2022": {
                "revenue": 3000,
                "cogs": 1500,
                "personnel": 800,
                "other_opex": 200,
                "other_income": 0,
                "da": 10,
            }
        }
        gf = {
            "old_monthly_k": 4.5,
            "benefit_factor": 1.2,
            "new_base_k": 60,
            "tantieme_k": 20,
            "sozial_pct": 0.18,
        }
        result = compute_adj_pnl(raw, [], gf, ["2022"])

        s = result["summary"]["2022"]
        assert abs(s["ebitda_adj"] - 529.6) < 0.1

        # Check detail
        detail = result["adjustments_detail"]
        assert "personnel" in detail
        assert len(detail["personnel"]) == 4  # 4 GF salary items

    def test_multi_year(self):
        raw = {
            "2021": {
                "revenue": 2000,
                "cogs": 1000,
                "personnel": 500,
                "other_opex": 100,
                "other_income": 0,
                "da": 5,
            },
            "2022": {
                "revenue": 2500,
                "cogs": 1200,
                "personnel": 600,
                "other_opex": 120,
                "other_income": 10,
                "da": 8,
            },
        }
        result = compute_adj_pnl(raw, [], None, ["2021", "2022"])
        assert "2021" in result["summary"]
        assert "2022" in result["summary"]
        assert result["summary"]["2021"]["ebitda_adj"] == 400  # 2000-1000-500-100+0
        assert result["summary"]["2022"]["ebitda_adj"] == 590  # 2500-1200-600-120+10


class TestConsolidateEntities:
    def test_two_entities(self):
        entity_pnl = {
            "MT_323": {"2022": {"revenue": 1200, "cogs": 800}},
            "Mtec_441": {"2022": {"revenue": 1300, "cogs": 900}},
        }
        result = consolidate_entities(entity_pnl)
        assert result["2022"]["revenue"] == 2500
        assert result["2022"]["cogs"] == 1700

    def test_single_entity_passthrough(self):
        entity_pnl = {"Single": {"2022": {"revenue": 1000, "cogs": 500}}}
        result = consolidate_entities(entity_pnl)
        assert result["2022"]["revenue"] == 1000


class TestComputeWaterfall:
    def test_basic(self):
        wf = compute_waterfall(
            ebitda_basis=365,
            ebit_basis=271,
            multiple=3.8,
            net_debt=-40,
            permitted_leakage=0,
            cash_at_closing=1100,
            vendor_loan=250,
            earnout_anticipated=200,
            earnout_tiers=[0, 50, 100, 200, 250, 300, 300],
        )
        assert wf["ev_at_closing"] == 1390
        assert wf["ev_anticipated"] == 1590
        assert wf["ev_total"] == 1690
        assert wf["equity_value"] == 1650
        assert wf["super_earnout"] == 100

    def test_no_earnout(self):
        wf = compute_waterfall(
            ebitda_basis=300,
            ebit_basis=250,
            multiple=4.0,
            net_debt=0,
            permitted_leakage=0,
            cash_at_closing=800,
            vendor_loan=200,
            earnout_anticipated=0,
            earnout_tiers=[],
        )
        assert wf["equity_value"] == 1000
        assert wf["ev_at_closing"] == 1000
        assert wf["super_earnout"] == 0

    def test_super_earnout(self):
        wf = compute_waterfall(
            ebitda_basis=300,
            ebit_basis=250,
            multiple=4.0,
            net_debt=0,
            permitted_leakage=0,
            cash_at_closing=500,
            vendor_loan=100,
            earnout_anticipated=100,
            earnout_tiers=[0, 100, 200],
        )
        assert wf["super_earnout"] == 100  # max(200) - 100
        assert wf["equity_value"] == 800  # 500+100+100+100

    def test_net_cash_positive(self):
        wf = compute_waterfall(
            ebitda_basis=200,
            ebit_basis=180,
            multiple=4.0,
            net_debt=50,
            permitted_leakage=0,
            cash_at_closing=500,
            vendor_loan=0,
            earnout_anticipated=0,
            earnout_tiers=[],
        )
        # net_debt=50 (net cash) → EV = equity - net_cash = 500 - 50 = 450
        assert wf["ev_at_closing"] == 450
        assert wf["equity_value"] == 500

    def test_percentages(self):
        wf = compute_waterfall(
            ebitda_basis=365,
            ebit_basis=271,
            multiple=3.8,
            net_debt=-40,
            permitted_leakage=0,
            cash_at_closing=1100,
            vendor_loan=250,
            earnout_anticipated=200,
            earnout_tiers=[0, 50, 100, 200, 250, 300, 300],
        )
        assert wf["cash_pct"] == pytest.approx(66.7, abs=0.1)
        assert wf["vendor_loan_pct"] == pytest.approx(15.2, abs=0.1)
        assert wf["earnout_pct"] == pytest.approx(12.1, abs=0.1)


class TestEarnoutMatrix:
    def test_7_scenarios(self):
        em = compute_earnout_matrix(
            ebit_anchor=275,
            step=25,
            tiers=[0, 50, 100, 200, 250, 300, 300],
            fixed_payment=1350,
            net_debt=-40,
            da_amount=94,
            base_ebitda=365,
        )
        assert len(em) == 7
        # First scenario: EBIT = 275 + (0-3)*25 = 200
        assert em[0]["ebit"] == 200
        assert em[0]["ebitda"] == 294  # 200 + 94
        assert em[0]["earnout"] == 0
        assert em[0]["kaufpreis"] == 1350
        # Middle (anchor): EBIT = 275
        assert em[3]["ebit"] == 275
        assert em[3]["earnout"] == 200

    def test_5_scenarios(self):
        em = compute_earnout_matrix(
            ebit_anchor=200,
            step=50,
            tiers=[0, 100, 200, 300, 300],
            fixed_payment=800,
            net_debt=0,
            da_amount=50,
            base_ebitda=250,
        )
        assert len(em) == 5
        assert em[2]["ebit"] == 200  # anchor

    def test_kaufpreis(self):
        em = compute_earnout_matrix(
            ebit_anchor=275,
            step=25,
            tiers=[0, 50, 100, 200, 250, 300, 300],
            fixed_payment=1350,
            net_debt=-40,
            da_amount=94,
            base_ebitda=365,
        )
        for s in em:
            assert s["kaufpreis"] == s["fixed_payment"] + s["earnout"]

    def test_ev_formula(self):
        em = compute_earnout_matrix(
            ebit_anchor=275,
            step=25,
            tiers=[0, 50, 100, 200, 250, 300, 300],
            fixed_payment=1350,
            net_debt=-40,
            da_amount=94,
            base_ebitda=365,
        )
        for s in em:
            assert s["ev"] == s["kaufpreis"] - (-40)  # kaufpreis + 40 (net debt is -40)

    def test_empty_tiers(self):
        em = compute_earnout_matrix(
            ebit_anchor=200,
            step=25,
            tiers=[],
            fixed_payment=500,
            net_debt=0,
            da_amount=50,
            base_ebitda=200,
        )
        assert em == []


class TestProformaEbit:
    def test_basic(self):
        raw = {
            "2022": {
                "net_income": 100,
                "tax": -30,
                "interest_expense": -10,
                "interest_income": 2,
                "other_income": 5,
                "other_opex": -8,
            },
        }
        pf = compute_proforma_ebit(raw, -80, 0.17, ["2022"])
        assert len(pf) == 1
        r = pf[0]
        assert r["ergebnis_nach_steuern"] == 100
        assert r["steuern"] == 30
        assert r["zinsaufwand"] == 10
        assert r["ebit"] == 100 + 30 + 10 - 2 + 5 - 8  # 135 (includes neutral items)
        assert r["gf_salary"] == -80
        assert r["nebenkosten"] == pytest.approx(-13.6, abs=0.01)
        assert r["ebit_proforma"] == pytest.approx(135 - 80 - 13.6, abs=0.1)


class TestCagr:
    def test_positive_growth(self):
        c = compute_cagr(100, 200, 3)
        assert c is not None
        assert abs(c - 0.2599) < 0.01

    def test_negative_start(self):
        assert compute_cagr(-100, 200, 3) is None

    def test_zero_years(self):
        assert compute_cagr(100, 200, 0) is None


class TestPnlKpis:
    def test_margins(self):
        summary = {
            "2022": {
                "total_sales": 1000,
                "gross_margin": 400,
                "pex_adj": -200,
                "opex_adj": -50,
                "ebitda_adj": 150,
                "ebit_adj": 130,
            },
        }
        kpis = compute_pnl_kpis(summary, ["2022"])
        assert kpis["2022"]["gross_margin_pct"] == 40.0
        assert kpis["2022"]["ebitda_margin_pct"] == 15.0


# ═══════════════════════════════════════════════════════════════════════════════
# Fox golden value tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFoxGoldenValues:
    """Validate computation against known Fox Excel model values."""

    def test_fox_waterfall(self):
        wf = compute_waterfall(
            ebitda_basis=365,
            ebit_basis=271,
            multiple=3.8,
            net_debt=-40,
            permitted_leakage=0,
            cash_at_closing=1100,
            vendor_loan=250,
            earnout_anticipated=200,
            earnout_tiers=[0, 50, 100, 200, 250, 300, 300],
        )
        assert wf["ev_at_closing"] == 1390
        assert wf["ev_anticipated"] == 1590
        assert wf["ev_total"] == 1690
        assert wf["equity_value"] == 1650

    def test_fox_earnout_matrix(self):
        em = compute_earnout_matrix(
            ebit_anchor=275,
            step=25,
            tiers=[0, 50, 100, 200, 250, 300, 300],
            fixed_payment=1350,
            net_debt=-40,
            da_amount=94,
            base_ebitda=365,
        )
        # Verify EV values: kaufpreis - net_debt = kaufpreis + 40
        assert em[0]["ev"] == 1390  # 1350+0+40
        assert em[3]["ev"] == 1590  # 1350+200+40
        assert em[6]["ev"] == 1690  # 1350+300+40

    def test_fox_gf_salary_adj(self):
        """GF salary: old=4.5k/month, factor=1.2, new_base=60k, tantieme=20k, sozial=18%."""
        gf = {
            "old_monthly_k": 4.5,
            "benefit_factor": 1.2,
            "new_base_k": 60,
            "tantieme_k": 20,
            "sozial_pct": 0.18,
        }
        raw = {
            "2024": {
                "revenue": 3392,
                "cogs": 1900,
                "personnel": 700,
                "other_opex": 200,
                "other_income": 20,
                "da": 25,
            }
        }
        result = compute_adj_pnl(raw, [], gf, ["2024"])
        detail = result["adjustments_detail"]["personnel"]
        # Old salary add-back: 4.5*12*1.2 = 64.8
        assert abs(detail[0]["amounts_by_year"]["2024"] - 64.8) < 0.01
        # New base: -60
        assert abs(detail[1]["amounts_by_year"]["2024"] - (-60)) < 0.01
        # Tantieme: -20
        assert abs(detail[2]["amounts_by_year"]["2024"] - (-20)) < 0.01
        # Sozial: -(60+20)*0.18 = -14.4
        assert abs(detail[3]["amounts_by_year"]["2024"] - (-14.4)) < 0.01


# ═══════════════════════════════════════════════════════════════════════════════
# DB integration tests
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    _migrate_schema_v2(conn)
    return conn


class TestModelParamsDB:
    def test_save_load_roundtrip(self, tmp_conn):
        params = {
            "multiple": 4.0,
            "net_debt": -40,
            "cash_at_closing": 1100,
            "earnout_tiers_json": [0, 50, 100],
            "entities_json": [{"name": "MT", "label": "Main", "source_pattern": "323"}],
        }
        save_model_params(tmp_conn, "com2med.de", params, "base")
        loaded = load_model_params(tmp_conn, "com2med.de", "base")
        assert loaded is not None
        assert loaded["multiple"] == 4.0
        assert loaded["net_debt"] == -40
        assert loaded["earnout_tiers_json"] == [0, 50, 100]
        assert loaded["entities_json"][0]["name"] == "MT"

    def test_update_existing(self, tmp_conn):
        save_model_params(tmp_conn, "test.de", {"multiple": 3.0}, "base")
        save_model_params(tmp_conn, "test.de", {"multiple": 5.0}, "base")
        loaded = load_model_params(tmp_conn, "test.de", "base")
        assert loaded["multiple"] == 5.0

    def test_load_nonexistent(self, tmp_conn):
        assert load_model_params(tmp_conn, "nope.de") is None


class TestBuildModelContext:
    def _seed_pnl(self, conn, domain: str):
        """Insert test P&L data into deal_financials."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (2022, "revenue", 3400, "test_source"),
            (2022, "cogs", 1969, "test_source"),
            (2022, "personnel", 776, "test_source"),
            (2022, "other_opex", 391, "test_source"),
            (2022, "other_income", 37, "test_source"),
            (2022, "da", 18, "test_source"),
            (2022, "ebit", 301, "test_source"),
            (2022, "ebitda", 301, "test_source"),
        ]
        for yr, line_item, val, src in rows:
            conn.execute(
                """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
                   period_type, value_k, source, confidence, is_authoritative, extracted_at)
                   VALUES (?, ?, 'pnl', ?, ?, 'annual', ?, ?, 'stated', 0, ?)""",
                (str(uuid.uuid4()), domain, line_item, yr, val, src, now),
            )
        conn.commit()

    def test_defaults_auto_populate(self, tmp_conn):
        self._seed_pnl(tmp_conn, "com2med.de")
        ctx = build_model_context(tmp_conn, "com2med.de")
        assert ctx["years"] == ["2022"]
        assert ctx["ebitda_basis"] > 0
        assert ctx["waterfall"] is not None

    def test_with_saved_params(self, tmp_conn):
        self._seed_pnl(tmp_conn, "com2med.de")
        save_model_params(
            tmp_conn,
            "com2med.de",
            {
                "multiple": 3.8,
                "net_debt": -40,
                "cash_at_closing": 1100,
                "vendor_loan": 250,
                "earnout_anticipated": 200,
                "earnout_tiers_json": [0, 50, 100, 200, 250, 300, 300],
                "earnout_ebit_anchor": 275,
                "earnout_step": 25,
                "ebitda_basis_override": 365,
                "ebit_basis_override": 271,
                "da_amount": 94,
            },
        )
        ctx = build_model_context(tmp_conn, "com2med.de")
        assert ctx["waterfall"]["ev_at_closing"] == 1390
        assert len(ctx["earnout_matrix"]) == 7

    def test_multi_entity(self, tmp_conn):
        now = datetime.now(timezone.utc).isoformat()
        for ent, rev in [("323", 1200), ("441", 1300)]:
            tmp_conn.execute(
                """INSERT INTO deal_financials (id, domain, statement, line_item, fiscal_year,
                   period_type, value_k, source, confidence, is_authoritative, extracted_at)
                   VALUES (?, 'test.de', 'pnl', 'revenue', 2022, 'annual', ?, ?, 'stated', 0, ?)""",
                (str(uuid.uuid4()), rev, f"file_{ent}_2022.xlsx", now),
            )
        tmp_conn.commit()

        save_model_params(
            tmp_conn,
            "test.de",
            {
                "entities_json": [
                    {"name": "MT_323", "label": "Main", "source_pattern": "323"},
                    {"name": "Mtec_441", "label": "Handel", "source_pattern": "441"},
                ],
                "multiple": 4.0,
            },
        )
        ctx = build_model_context(tmp_conn, "test.de")
        assert ctx["entities"] is not None
        assert ctx["entity_pnl"] is not None
        # Consolidated revenue = 1200 + 1300 = 2500
        assert ctx["raw_pnl"]["2022"]["revenue"] == 2500
