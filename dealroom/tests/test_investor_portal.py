"""Investor portal (view-only, watermarked) — SPEC-INVESTOR-PORTAL.md.

Pure-unit coverage of the two security-critical pieces: the access decision
(`_compute_investor_ctx`) and the flag/watermark injection in `_build_html`.

The do_GET/do_POST wiring (call `_investor_ctx` → 401 if unauthorized, 403 if the
session is an investor) is a thin branch over the tested decision function; it is
verified by inspection + a manual browser check, not by spawning a live server
here (that thrashes local host processes).
"""

import base64
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sqlite3  # noqa: E402

import dashboard  # noqa: E402


def _basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


# ─────────────────────────── pure access decision ───────────────────────────

INT = ("boss", "x")
INV = ("asf", "y")


def test_investor_credential_maps_to_investor_mode():
    assert dashboard._compute_investor_ctx(_basic("asf", "y"), {}, INT, INV) == (
        True,
        True,
        "asf",
    )


def test_internal_credential_is_full_mode():
    assert dashboard._compute_investor_ctx(_basic("boss", "x"), {}, INT, INV) == (
        True,
        False,
        "",
    )


def test_wrong_password_unauthorized():
    assert dashboard._compute_investor_ctx(_basic("asf", "nope"), {}, INT, INV) == (
        False,
        False,
        "",
    )


def test_missing_auth_when_creds_configured_unauthorized():
    assert dashboard._compute_investor_ctx("", {}, INT, INV)[0] is False


def test_no_creds_configured_is_open_internal():
    assert dashboard._compute_investor_ctx("", {}, ("", ""), ("", "")) == (
        True,
        False,
        "",
    )


def test_dev_view_flag_enables_investor_preview_only_without_creds():
    q = {"view": ["investor"], "as": ["ASF"]}
    assert dashboard._compute_investor_ctx("", q, ("", ""), ("", "")) == (
        True,
        True,
        "ASF",
    )
    # When creds ARE configured, the dev flag must NOT grant investor access.
    assert dashboard._compute_investor_ctx("", q, INT, INV)[0] is False


# ─────────────────────────── flag / watermark injection ─────────────────────


@pytest.fixture(scope="module")
def fox_data():
    con = sqlite3.connect(str(ROOT / "data" / "dealroom.db"))
    con.row_factory = sqlite3.Row
    return dashboard.build_dashboard_data(con, "Fox")


def test_investor_html_sets_flag_and_watermark(fox_data):
    html = dashboard._build_html(
        fox_data, serve_mode=True, investor_mode=True, watermark_label="ASF"
    )
    assert "const INVESTOR_MODE = true;" in html
    assert 'const WATERMARK_LABEL = "ASF";' in html
    assert "function applyInvestorMode()" in html
    assert "SERVE_MODE && !INVESTOR_MODE" in html  # edit gate present
    assert "__INVESTOR_MODE_JS__" not in html and "__WATERMARK_LABEL__" not in html


def test_normal_html_has_investor_mode_false(fox_data):
    html = dashboard._build_html(fox_data, serve_mode=True)
    assert "const INVESTOR_MODE = false;" in html
    assert 'const WATERMARK_LABEL = "";' in html


def test_watermark_label_is_safely_escaped(fox_data):
    # json.dumps must neutralise a label that tries to break out of the JS string.
    html = dashboard._build_html(
        fox_data, serve_mode=True, investor_mode=True, watermark_label='a";alert(1)//'
    )
    assert 'const WATERMARK_LABEL = "a\\";alert(1)//";' in html


# ─────────────────────────── investor data scrub ────────────────────────────


def test_sanitize_investor_deal_mode_allowlist():
    data = {
        "mode": "deal",
        "deal": {
            "code_name": "Fox",
            "company_name": "Com2Med",
            "domain": "com2med.de",
            "investment_thesis": "secret thesis",
            "seller_motivation": "owner retiring",
            "conflict_count": 55,
            "question_count": 3,
            "days_since_contact": 10,
            "deal_stage": "loi_signed",
        },
        "onepager": {"title": "Com2Med", "q1": "keep this bullet text"},
        "onepager_chart": {"yearly": {"2025": {"revenue_k": 3571.85}}},
        "customers": {
            "service_split": [{"label": "Service", "pct": 40}],
            "top10": {
                "2025": [{"name": "Klinikum München GmbH", "rank": 1, "pct": 12}]
            },
        },
        "financials": {"pnl": {"2025": {"revenue": 3571}}},
        "model": {"bewertung": {"sales": 3135}},
        "model_context": {"source_model_file": "Com2Med_v7.xlsx"},
        "overview": {"legal_name": "Com2Med GmbH", "street": "Hauptstr. 1"},
        "documents": [{"filename": "260518_Com2Med_v7.xlsx"}],
    }
    out = dashboard._sanitize_investor(data)
    # Identity -> codename in both leak sites
    assert out["deal"]["company_name"] == "Fox"
    assert out["onepager"]["title"] == "Fox"
    # Identifying deal fields removed
    for k in ("domain", "investment_thesis", "seller_motivation"):
        assert k not in out["deal"]
    assert out["deal"]["conflict_count"] == 0
    # Leaky sections emptied
    assert out["financials"] == {} and out["model"] == {}
    assert out["model_context"] == {} and out["overview"] == {}
    assert out["documents"] == []
    # Author bullet text + name-free chart preserved
    assert out["onepager"]["q1"] == "keep this bullet text"
    assert out["onepager_chart"]["yearly"]["2025"]["revenue_k"] == 3571.85
    # Customer aggregates kept, real customer name scrubbed
    assert out["customers"]["service_split"][0]["pct"] == 40
    assert out["customers"]["top10"]["2025"][0]["name"] == "Customer 1"
    # No real-name / domain token anywhere in the payload
    import json as _json

    blob = _json.dumps(out, ensure_ascii=False)
    assert "Com2Med" not in blob and "com2med" not in blob
    assert "Klinikum" not in blob


def test_sanitize_investor_portfolio_mode_drops_identity():
    data = {
        "mode": "portfolio",
        "deals": [
            {
                "code_name": "Fox",
                "company_name": "Com2Med",
                "domain": "com2med.de",
                "rev_m": 3.6,
            }
        ],
    }
    out = dashboard._sanitize_investor(data)
    row = out["deals"][0]
    assert row["code_name"] == "Fox" and row["rev_m"] == 3.6
    assert "company_name" not in row and "domain" not in row
