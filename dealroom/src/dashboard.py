"""
DR-M4: Deal Workspace Dashboard.

Two views:
- Portfolio: all deals in a summary table
- Deal: single-deal workspace with cockpit strip + tabs (Financials, Documents, Notes)

Hybrid static/serve mode: builds self-contained HTML, optionally serves live on HTTP.
"""

import base64
import http.server
import json
import os
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"
OUTPUT_DIR = settings.DATA_DIR / "output"
DEFAULT_PORT = 8090


# ─── Data builders ────────────────────────────────────────────────────────────


def _days_since(iso_str: str | None) -> int | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).days
    except (ValueError, TypeError):
        return None


def _domain_for(deal_row) -> str:
    return deal_row["domain"] or deal_row["code_name"].lower()


_STAGE_STATUS: dict[str, str] = {
    "meeting_concluded": "Meeting concluded",
    "valuation_rfi": "Valuation & RFI",
    "indicative_offer": "NBO Sent",
    "loi_signed": "LOI signed",
    "due_diligence": "Due Diligence",
    "contract_negotiation": "Contract Negotiation",
    "closed": "Closed",
    "on_hold": "On hold",
    "dead": "Dead",
}


_PORTFOLIO_OVERRIDE_COLS = [
    "description",
    "strategic_fit",
    "rev_m_override",
    "ebitda_m_override",
    "employees_override",
    "ev_m_override",
    "ev_m_note",
    "multiple_override",
    "multiple_note",
    "status_override",
    "deal_stage",
]


def _ensure_portfolio_columns(conn) -> None:
    """Add portfolio override columns to deals table if not present."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(deals)").fetchall()}
    type_map = {
        "description": "TEXT",
        "strategic_fit": "INTEGER",  # 0–4 harvey ball score
        "rev_m_override": "REAL",
        "ebitda_m_override": "REAL",
        "employees_override": "INTEGER",
        "ev_m_override": "REAL",
        "ev_m_note": "TEXT",  # e.g. "(WIP)" or "(11.6 old)"
        "multiple_override": "REAL",
        "multiple_note": "TEXT",
        "status_override": "TEXT",
    }
    for col, dtype in type_map.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {col} {dtype}")
    conn.commit()


_ONEPAGER_COLS = {
    "onepager_title": "TEXT",
    "onepager_headline": "TEXT",
    "onepager_q1": "TEXT",
    "onepager_q3": "TEXT",
    "onepager_q4": "TEXT",
    "onepager_footnote": "TEXT",
    "onepager_generated_at": "TEXT",
    "onepager_edited_at": "TEXT",
    "onepager_q1_approved": "INTEGER DEFAULT 0",
    "onepager_q3_approved": "INTEGER DEFAULT 0",
    "onepager_q4_approved": "INTEGER DEFAULT 0",
    "bp_2026_rev_k": "REAL",
    "bp_2026_ebitda_k": "REAL",
    "maxeo_2026_ebitda_k": "REAL",
}


def _ensure_onepager_columns(conn) -> None:
    """Add onepager columns to deals table if not present (idempotent)."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(deals)").fetchall()}
    for col, dtype in _ONEPAGER_COLS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {col} {dtype}")
    conn.commit()


_DD_CARD_COLS = {
    "bm_segments_comment": "TEXT",
    "bm_margin_comment": "TEXT",
    "bm_revquality_comment": "TEXT",
    "bm_tieout_comment": "TEXT",
    "bm_description": "TEXT",
    "thesis_scorecard_comment": "TEXT",
    "thesis_swot_comment": "TEXT",
    "thesis_rationale": "TEXT",
}


def _ensure_dd_card_columns(conn) -> None:
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(deals)").fetchall()}
    for col, dtype in _DD_CARD_COLS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {col} {dtype}")
    conn.commit()


def _ensure_portfolio_meta(conn) -> None:
    """Create portfolio_meta key-value table if missing (stores portfolio-level settings)."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS portfolio_meta (
            key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)"""
    )
    conn.commit()


def _get_portfolio_meta(conn, key: str) -> str:
    _ensure_portfolio_meta(conn)
    row = conn.execute(
        "SELECT value FROM portfolio_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else ""


def _get_portfolio_comments(conn) -> str:
    return _get_portfolio_meta(conn, "portfolio_comments")


def _save_portfolio_meta(conn, key: str, text: str) -> None:
    _ensure_portfolio_meta(conn)
    conn.execute(
        """INSERT INTO portfolio_meta (key, value, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, text, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()


def _save_portfolio_comments(conn, text: str) -> None:
    _save_portfolio_meta(conn, "portfolio_comments", text)


def _attach_allex(conn) -> None:
    """Attach ALLEX pipeline.db as 'allex' if not already attached."""
    try:
        conn.execute("SELECT 1 FROM allex.company_records LIMIT 1")
    except Exception:
        conn.execute(f"ATTACH DATABASE '{settings.ALLEX_PIPELINE_DB}' AS allex")


def build_portfolio_data(conn) -> dict[str, Any]:
    _ensure_portfolio_columns(conn)
    _attach_allex(conn)
    deals = conn.execute(
        """SELECT * FROM deals ORDER BY
           CASE deal_stage
             WHEN 'closed' THEN 1
             WHEN 'contract_negotiation' THEN 2
             WHEN 'due_diligence' THEN 3
             WHEN 'loi_signed' THEN 4
             WHEN 'indicative_offer' THEN 5
             WHEN 'valuation_rfi' THEN 6
             WHEN 'meeting_concluded' THEN 7
             WHEN 'on_hold' THEN 50
             WHEN 'dead' THEN 51
             ELSE 40
           END, code_name"""
    ).fetchall()
    result = []
    for d in deals:
        domain = _domain_for(d)

        # Revenue + EBITDA — prefer model (adjusted) data, fall back to raw.
        # Headline year = latest ACTUAL year (non-zero revenue). Excluding zero
        # revenue skips an empty forward FY+1 model plan column that would
        # otherwise be picked as the latest year and blank out the headline.
        rev_row = conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl'
                 AND line_item IN ('gesamtleistung', 'revenue')
                 AND period_type = 'annual'
                 AND value_k IS NOT NULL AND value_k != 0
               ORDER BY is_adjusted DESC, fiscal_year DESC,
                 CASE line_item WHEN 'gesamtleistung' THEN 0 ELSE 1 END
               LIMIT 1""",
            (domain,),
        ).fetchone()
        revenue_k = rev_row["value_k"] if rev_row else None
        rev_year = rev_row["fiscal_year"] if rev_row else None
        # EBITDA must match the headline revenue year so the margin is coherent
        # and a stray non-zero plan-year EBITDA cannot leak in.
        ebitda_row = None
        if rev_year is not None:
            ebitda_row = conn.execute(
                """SELECT value_k FROM deal_financials
                   WHERE domain = ? AND statement = 'pnl'
                     AND line_item IN ('ebitda_adj', 'ebitda')
                     AND period_type = 'annual'
                     AND fiscal_year = ? AND value_k IS NOT NULL
                   ORDER BY is_adjusted DESC LIMIT 1""",
                (domain, rev_year),
            ).fetchone()
        if ebitda_row is None:
            ebitda_row = conn.execute(
                """SELECT value_k FROM deal_financials
                   WHERE domain = ? AND statement = 'pnl'
                     AND line_item IN ('ebitda_adj', 'ebitda')
                     AND period_type = 'annual'
                     AND value_k IS NOT NULL AND value_k != 0
                   ORDER BY is_adjusted DESC, fiscal_year DESC LIMIT 1""",
                (domain,),
            ).fetchone()
        ebitda_k = ebitda_row["value_k"] if ebitda_row else None
        ebitda_pct = (
            round(ebitda_k / revenue_k * 100, 1)
            if (revenue_k and ebitda_k and revenue_k != 0)
            else None
        )

        # Valuation: EV incl. EO + Multiple — prefer deal_valuations, fall back to bewertung
        val_row = conn.execute(
            """SELECT ev_mid, earnout_max, ebitda_basis FROM deal_valuations
               WHERE domain = ? ORDER BY created_at DESC LIMIT 1""",
            (domain,),
        ).fetchone()
        ev_m_computed = None
        multiple_computed = None
        ev_total_k = 0
        if val_row:
            ev_mid = val_row["ev_mid"] or 0
            earnout = val_row["earnout_max"] or 0
            basis = val_row["ebitda_basis"]
            ev_total_k = ev_mid + earnout
            ev_m_computed = round(ev_total_k / 1000, 2) if ev_total_k else None
            if ev_m_computed and basis and basis > 0:
                multiple_computed = round(ev_total_k / basis, 2)
        if ev_m_computed is None:
            bew = conn.execute(
                """SELECT line_item, value_k FROM deal_financials
                   WHERE domain = ? AND statement = 'bewertung' AND is_adjusted = 1
                     AND line_item IN ('ev_anticipated_earnout', 'ev_total')""",
                (domain,),
            ).fetchall()
            bew_map = {r["line_item"]: r["value_k"] for r in bew}
            ev_k = bew_map.get("ev_anticipated_earnout") or bew_map.get("ev_total")
            if not ev_k or ev_k <= 0:
                bew2 = conn.execute(
                    """SELECT line_item, value_k FROM deal_financials
                       WHERE domain = ? AND statement = 'bewertung' AND is_adjusted = 1
                         AND line_item IN ('equity_value', 'net_cash_debt')""",
                    (domain,),
                ).fetchall()
                bew2_map = {r["line_item"]: r["value_k"] for r in bew2}
                eq = bew2_map.get("equity_value")
                ncd = bew2_map.get("net_cash_debt", 0)
                if eq and eq > 0:
                    ev_k = eq - ncd
            if ev_k and ev_k > 0:
                ev_total_k = ev_k
                ev_m_computed = round(ev_k / 1000, 2)
        if multiple_computed is None and ev_total_k and ebitda_k and ebitda_k > 0:
            multiple_computed = round(ev_total_k / ebitda_k, 2)

        # Employees from ALLEX (fall back to override)
        allex_row = conn.execute(
            "SELECT ma_count FROM allex.company_records WHERE domain = ? LIMIT 1",
            (domain,),
        ).fetchone()
        employees_allex = allex_row["ma_count"] if allex_row else None

        # Apply manual overrides (override wins over computed)
        rev_m = (
            d["rev_m_override"]
            if d["rev_m_override"] is not None
            else (round(revenue_k / 1000, 4) if revenue_k is not None else None)
        )
        ebitda_m = (
            d["ebitda_m_override"]
            if d["ebitda_m_override"] is not None
            else (round(ebitda_k / 1000, 4) if ebitda_k is not None else None)
        )
        ebitda_pct_val = (
            round(ebitda_m / rev_m * 100, 1)
            if (rev_m and ebitda_m and rev_m != 0)
            else None
        )
        employees = (
            d["employees_override"]
            if d["employees_override"] is not None
            else employees_allex
        )
        ev_m = d["ev_m_override"] if d["ev_m_override"] is not None else ev_m_computed
        multiple = (
            d["multiple_override"]
            if d["multiple_override"] is not None
            else multiple_computed
        )
        status_text = (
            d["status_override"]
            if d["status_override"]
            else _STAGE_STATUS.get(d["deal_stage"], d["deal_stage"])
        )

        result.append(
            {
                "code_name": d["code_name"],
                "company_name": d["company_name"],
                "deal_stage": d["deal_stage"],
                "description": d["description"] or "",
                "strategic_fit": d["strategic_fit"]
                if d["strategic_fit"] is not None
                else 0,
                "status_text": status_text,
                "rev_m": rev_m,
                "ebitda_m": ebitda_m,
                "ebitda_pct": ebitda_pct_val,
                "employees": employees,
                "ev_m": ev_m,
                "ev_m_note": d["ev_m_note"] or "",
                "multiple": multiple,
                "multiple_note": d["multiple_note"] or "",
            }
        )
    return {
        "mode": "portfolio",
        "deals": result,
        "portfolio_pipeline_comments": _get_portfolio_meta(
            conn, "portfolio_pipeline_comments"
        ),
        "portfolio_comments": _get_portfolio_comments(conn),
    }


def _parse_ct_header(source: str | None) -> str:
    """Parse source filename to derive CT column header in MM/YY format.

    Examples:
      'BWA September 25 KVG.xlsx'           → '09/25'
      'Kurzfristige Erfolgsrechnung 12.2025' → '12/25'
      'BWA Q1 2025.xlsx'                    → '03/25'
    Returns 'CT' if month cannot be parsed.
    """
    import re

    if not source:
        return "CT"

    MONTH_DE = {
        "januar": "01",
        "february": "02",
        "februar": "02",  # noqa
        "march": "03",
        "märz": "03",
        "april": "04",
        "may": "05",
        "mai": "05",
        "june": "06",
        "juni": "06",
        "july": "07",
        "juli": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "oktober": "10",
        "november": "11",
        "december": "12",
        "dezember": "12",
    }
    QUARTER_LAST = {"q1": "03", "q2": "06", "q3": "09", "q4": "12"}

    src_lower = source.lower()
    fn = Path(source).name.lower()

    # Pattern: MM.YYYY or MM.YY  e.g. "12.2025"
    m = re.search(r"\b(0?[1-9]|1[0-2])\.(20\d{2}|\d{2})\b", fn)
    if m:
        mm = m.group(1).zfill(2)
        yr_raw = m.group(2)
        yy = yr_raw[-2:]
        return f"{mm}/{yy}"

    # Pattern: German month name + 2-digit year
    for name, mm in MONTH_DE.items():
        m2 = re.search(rf"\b{name}\s+(20\d{{2}}|\d{{2}})\b", src_lower)
        if m2:
            yr_raw = m2.group(1)
            yy = yr_raw[-2:]
            return f"{mm}/{yy}"

    # Pattern: Q1/Q2/Q3/Q4 + year
    for q, mm in QUARTER_LAST.items():
        m3 = re.search(rf"\b{q}\s+(20\d{{2}}|\d{{2}})\b", src_lower)
        if m3:
            yr_raw = m3.group(1)
            yy = yr_raw[-2:]
            return f"{mm}/{yy}"

    return "CT"


def _build_unified_financials(conn, domain: str, entity: str = "consolidated") -> dict:
    """Build unified P&L dict combining raw (is_adjusted=0) and adjusted (is_adjusted=1).

    DR-M9b: Added entity filter, CT data with filename-parsed header, CAGR computation,
    2026B projection, OPEX netting, pnl_row_comments, entities list.
    """

    # Mapping: raw line_item → unified display key
    RAW_TO_KEY = {
        "revenue": "revenue",
        "gesamtleistung": "revenue",
        "cogs": "cogs_adj",
        "personnel": "personnel_adj",
        "other_opex": "other_opex_adj",
        "other_income": "other_income_adj",
        "ebitda": "ebitda_adj",
        "da": "da_adj",
        "ebit": "ebit_adj",
        "interest_income": "interest_income",
        "interest_expense": "interest_expense",
        "ebt": "ebt_adj",
        "tax": "tax",
        "net_income": "net_income_adj",
    }

    # Detect whether entity column exists (schema v4 may not be applied yet on old DBs)
    df_cols = {
        r[1] for r in conn.execute("PRAGMA table_info(deal_financials)").fetchall()
    }
    has_entity_col = "entity" in df_cols

    # Build entity filter clause
    if has_entity_col:
        entity_clause = "AND entity = ?"
        base_params: tuple = (domain, entity)
    else:
        entity_clause = ""
        base_params = (domain,)

    # Query ALL pnl rows (both adjusted and raw, no konto_nr filter)
    all_rows = conn.execute(
        f"""SELECT fiscal_year, line_item, value_k, source, is_adjusted, konto_nr
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND period_type = 'annual'
             AND value_k IS NOT NULL {entity_clause}
           ORDER BY fiscal_year, is_adjusted, line_item""",
        base_params,
    ).fetchall()

    unified_pnl: dict[str, dict] = {}
    subaccounts: dict[str, dict] = {}

    for r in all_rows:
        yr = str(r["fiscal_year"]) if r["fiscal_year"] else "unknown"
        li = r["line_item"]
        val = r["value_k"]
        src = r["source"] or ""
        is_adj = r["is_adjusted"]
        konto = r["konto_nr"]

        # Subaccount row (konto_nr present) — store under parent line_item
        # Only return subaccounts for entity-level views, not consolidated
        if konto is not None:
            if entity != "consolidated":
                parent_key = RAW_TO_KEY.get(li, li)
                if parent_key not in subaccounts:
                    subaccounts[parent_key] = {}
                if yr not in subaccounts[parent_key]:
                    subaccounts[parent_key][yr] = []
                subaccounts[parent_key][yr].append(
                    {"konto_nr": str(konto), "value_k": val, "source": src}
                )
            continue

        # Aggregate row — map to display key
        if is_adj == 1:
            display_key = li
        else:
            display_key = RAW_TO_KEY.get(li, li)

        if display_key not in unified_pnl:
            unified_pnl[display_key] = {}

        if yr not in unified_pnl[display_key]:
            unified_pnl[display_key][yr] = {}

        if is_adj == 1:
            unified_pnl[display_key][yr]["adjusted"] = val
            unified_pnl[display_key][yr]["source_adj"] = src
        else:
            unified_pnl[display_key][yr]["raw"] = val
            unified_pnl[display_key][yr]["source_raw"] = src

    # Determine years list and has_adjusted
    all_years: set[str] = set()
    has_adjusted = False
    for key_data in unified_pnl.values():
        for yr_key, cell in key_data.items():
            if yr_key != "unknown":
                all_years.add(yr_key)
            if "adjusted" in cell:
                has_adjusted = True
    years = sorted(all_years)

    # ── CT (Current Trading) data ──────────────────────────────────────────────
    ct_params_base = [domain]
    if has_entity_col:
        ct_entity_clause = "AND entity = ?"
        ct_params_base.append(entity)
    else:
        ct_entity_clause = ""

    # CT current year YTD (bwa_ytd)
    ct_cur_rows = conn.execute(
        f"""SELECT line_item, value_k, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND period_type = 'bwa_ytd'
             AND value_k IS NOT NULL {ct_entity_clause}
           ORDER BY extracted_at DESC""",
        ct_params_base,
    ).fetchall()
    ct_current: dict[str, float | None] = {}
    ct_cur_source: str | None = None
    for r in ct_cur_rows:
        li = r["line_item"]
        display_key = RAW_TO_KEY.get(li, li)
        if display_key not in ct_current:
            ct_current[display_key] = r["value_k"]
            if ct_cur_source is None:
                ct_cur_source = r["source"]

    # CT prior year full-year (bwa_ytd_m31)
    ct_prior_rows = conn.execute(
        f"""SELECT line_item, value_k, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND period_type = 'bwa_ytd_m31'
             AND value_k IS NOT NULL {ct_entity_clause}
           ORDER BY extracted_at DESC""",
        ct_params_base,
    ).fetchall()
    ct_prior: dict[str, float | None] = {}
    ct_prior_source: str | None = None
    for r in ct_prior_rows:
        li = r["line_item"]
        display_key = RAW_TO_KEY.get(li, li)
        if display_key not in ct_prior:
            ct_prior[display_key] = r["value_k"]
            if ct_prior_source is None:
                ct_prior_source = r["source"]

    # Merged ct_data for backward compat (uses current if available, else prior)
    ct_data: dict[str, float | None] = {}
    for k in set(list(ct_current.keys()) + list(ct_prior.keys())):
        ct_data[k] = ct_current.get(k, ct_prior.get(k))

    ct_header_current = _parse_ct_header(ct_cur_source) if ct_cur_source else "CT (CY)"
    ct_header_prior = (
        _parse_ct_header(ct_prior_source) if ct_prior_source else "CT (PY)"
    )

    # ── OPEX netting: net_opex = other_opex_adj - other_income_adj ────────────
    # Compute per year and store under key 'opex_net_adj'
    for yr in years:
        opex_cell = unified_pnl.get("other_opex_adj", {}).get(yr, {})
        opin_cell = unified_pnl.get("other_income_adj", {}).get(yr, {})
        opex_val = (
            opex_cell.get("adjusted")
            if opex_cell.get("adjusted") is not None
            else opex_cell.get("raw")
        )
        opin_val = (
            opin_cell.get("adjusted")
            if opin_cell.get("adjusted") is not None
            else opin_cell.get("raw")
        )
        if opex_val is not None or opin_val is not None:
            net = (opex_val or 0.0) - (opin_val or 0.0)
            unified_pnl.setdefault("opex_net_adj", {})[yr] = {
                "raw": net,
                "adjusted": net,
                "source_raw": "computed",
                "source_adj": "computed",
            }

    # CT OPEX netting — current
    ct_opex_cur = ct_current.get("other_opex_adj")
    ct_opin_cur = ct_current.get("other_income_adj")
    if ct_opex_cur is not None or ct_opin_cur is not None:
        ct_current["opex_net_adj"] = (ct_opex_cur or 0.0) - (ct_opin_cur or 0.0)
    # CT OPEX netting — prior
    ct_opex_pr = ct_prior.get("other_opex_adj")
    ct_opin_pr = ct_prior.get("other_income_adj")
    if ct_opex_pr is not None or ct_opin_pr is not None:
        ct_prior["opex_net_adj"] = (ct_opex_pr or 0.0) - (ct_opin_pr or 0.0)
    # Merged ct_data opex netting
    ct_opex = ct_data.get("other_opex_adj")
    ct_opin = ct_data.get("other_income_adj")
    if ct_opex is not None or ct_opin is not None:
        ct_data["opex_net_adj"] = (ct_opex or 0.0) - (ct_opin or 0.0)

    # ── CAGR (3-year window) ───────────────────────────────────────────────────
    # Use last 3 actual years (≤ 2025)
    actual_years = [y for y in years if int(y) <= 2025]
    cagr: dict[str, float | None] = {}
    CAGR_KEYS = [
        "revenue",
        "cogs_adj",
        "personnel_adj",
        "opex_net_adj",
        "ebitda_adj",
        "ebit_adj",
        "net_income_adj",
    ]
    cagr_label = "CAGR"
    if len(actual_years) >= 2:
        cagr_first = actual_years[max(0, len(actual_years) - 3)]
        cagr_last = actual_years[-1]
        n_yrs = int(cagr_last) - int(cagr_first)
        cagr_label = f"CAGR {cagr_first[-2:]}-{cagr_last[-2:]}"
        for k in CAGR_KEYS:
            first_cell = unified_pnl.get(k, {}).get(cagr_first, {})
            last_cell = unified_pnl.get(k, {}).get(cagr_last, {})
            first_val = (
                first_cell.get("adjusted")
                if first_cell.get("adjusted") is not None
                else first_cell.get("raw")
            )
            last_val = (
                last_cell.get("adjusted")
                if last_cell.get("adjusted") is not None
                else last_cell.get("raw")
            )
            if (
                first_val is None
                or last_val is None
                or first_val == 0
                or n_yrs == 0
                or first_val < 0
                or last_val < 0
            ):
                cagr[k] = None  # NaN indicator — frontend shows 'NaN'
            else:
                try:
                    cagr[k] = round((last_val / first_val) ** (1 / n_yrs) - 1, 4)
                except (ZeroDivisionError, ValueError):
                    cagr[k] = None

    # ── 2026B projection ───────────────────────────────────────────────────────
    proj_2026: dict[str, float | None] = {}
    try:
        deal_cols = {r[1] for r in conn.execute("PRAGMA table_info(deals)").fetchall()}
        proj_fields = [
            "proj_topline_growth_pct",
            "proj_gm_pct",
            "proj_ebitda_margin_pct",
            "bp_2026_rev_k",
            "bp_2026_ebitda_k",
        ]
        select_fields = [f for f in proj_fields if f in deal_cols]
        if select_fields:
            proj_row = conn.execute(
                f"SELECT {', '.join(select_fields)} FROM deals WHERE domain = ?",
                (domain,),
            ).fetchone()
            if proj_row:
                # Last actual year total sales
                last_actual = actual_years[-1] if actual_years else None
                rev_cell_last = (
                    unified_pnl.get("revenue", {}).get(last_actual, {})
                    if last_actual
                    else {}
                )
                last_rev = (
                    rev_cell_last.get("adjusted")
                    if rev_cell_last.get("adjusted") is not None
                    else rev_cell_last.get("raw")
                )

                growth_pct = (
                    proj_row["proj_topline_growth_pct"]
                    if "proj_topline_growth_pct" in select_fields
                    else None
                )
                gm_pct = (
                    proj_row["proj_gm_pct"] if "proj_gm_pct" in select_fields else None
                )
                ebitda_m_pct = (
                    proj_row["proj_ebitda_margin_pct"]
                    if "proj_ebitda_margin_pct" in select_fields
                    else None
                )
                bp_rev = (
                    proj_row["bp_2026_rev_k"]
                    if "bp_2026_rev_k" in select_fields
                    else None
                )
                bp_ebitda = (
                    proj_row["bp_2026_ebitda_k"]
                    if "bp_2026_ebitda_k" in select_fields
                    else None
                )

                # Compute projected revenue
                proj_rev = None
                if bp_rev is not None:
                    proj_rev = bp_rev
                elif last_rev is not None and growth_pct is not None:
                    proj_rev = last_rev * (1 + growth_pct / 100)

                # Compute projected COGS from GM%
                proj_cogs = None
                if proj_rev is not None and gm_pct is not None:
                    proj_cogs = -proj_rev * (1 - gm_pct / 100)  # COGS stored negative

                # Compute projected EBITDA
                proj_ebitda = None
                if bp_ebitda is not None:
                    proj_ebitda = bp_ebitda
                elif proj_rev is not None and ebitda_m_pct is not None:
                    proj_ebitda = proj_rev * ebitda_m_pct / 100

                if proj_rev is not None:
                    proj_2026["revenue"] = proj_rev
                if proj_cogs is not None:
                    proj_2026["cogs_adj"] = proj_cogs
                if proj_ebitda is not None:
                    proj_2026["ebitda_adj"] = proj_ebitda

                # Store projection assumptions for frontend
                proj_2026["_assumptions"] = {
                    "topline_growth_pct": growth_pct,
                    "gm_pct": gm_pct,
                    "ebitda_margin_pct": ebitda_m_pct,
                }
    except Exception:
        pass  # schema v4 not yet applied — projection unavailable

    # ── Available entities list ────────────────────────────────────────────────
    entities = ["consolidated"]
    if has_entity_col:
        try:
            ent_rows = conn.execute(
                "SELECT DISTINCT entity FROM deal_financials WHERE domain = ? AND entity IS NOT NULL",
                (domain,),
            ).fetchall()
            ent_set = {r[0] for r in ent_rows if r[0] and r[0] != "consolidated"}
            entities = ["consolidated"] + sorted(ent_set)
        except Exception:
            pass

    # ── pnl_row_comments ──────────────────────────────────────────────────────
    pnl_row_comments: dict = {}
    try:
        deals_cols = {r[1] for r in conn.execute("PRAGMA table_info(deals)").fetchall()}
        if "pnl_row_comments" in deals_cols:
            row = conn.execute(
                "SELECT pnl_row_comments FROM deals WHERE domain = ?", (domain,)
            ).fetchone()
            if row and row["pnl_row_comments"]:
                import json as _json

                try:
                    pnl_row_comments = _json.loads(row["pnl_row_comments"])
                except Exception:
                    pnl_row_comments = {}
    except Exception:
        pass

    # Bewertung data
    bewertung_rows = conn.execute(
        """SELECT line_item AS key, value_k AS value_num, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'bewertung' AND is_adjusted = 1
             AND value_k IS NOT NULL""",
        (domain,),
    ).fetchall()
    bewertung = {r["key"]: r["value_num"] for r in bewertung_rows}

    return {
        "unified_pnl": unified_pnl,
        "subaccounts": subaccounts,
        "years": years,
        "has_adjusted": has_adjusted,
        "bewertung": bewertung,
        "ct_data": ct_data,
        "ct_current": ct_current,
        "ct_prior": ct_prior,
        "ct_header": ct_header_current,
        "ct_header_current": ct_header_current,
        "ct_header_prior": ct_header_prior,
        "cagr": cagr,
        "cagr_label": cagr_label,
        "proj_2026": proj_2026,
        "entities": entities,
        "pnl_row_comments": pnl_row_comments,
        "current_entity": entity,
    }


def build_deal_data(conn, code_name: str) -> dict[str, Any]:
    # Ensure onepager columns exist BEFORE fetching the deal row. Otherwise on a
    # fresh DB the Row is captured without the onepager_* columns and downstream
    # access (e.g. deal["onepager_footnote"]) raises IndexError. (DR-BUG-024)
    _ensure_onepager_columns(conn)
    _ensure_dd_card_columns(conn)
    deal = conn.execute(
        "SELECT * FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if not deal:
        raise ValueError(f"Deal not found: {code_name}")

    domain = _domain_for(deal)

    # Conflict count (approximate — count rows with duplicate statement+line_item+year)
    conflict_count = 0

    # P&L data grouped by year
    pnl_rows = conn.execute(
        """SELECT fiscal_year, line_item, value_k, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND period_type = 'annual' AND value_k IS NOT NULL AND is_adjusted = 0
           ORDER BY fiscal_year, line_item, source""",
        (domain,),
    ).fetchall()

    pnl: dict[str, dict] = {}
    for r in pnl_rows:
        yr = str(r["fiscal_year"]) if r["fiscal_year"] else "unknown"
        if yr not in pnl:
            pnl[yr] = {}
        key = r["line_item"]
        entry = {
            "value": r["value_k"],
            "source": r["source"],
            "conflict": False,
            "conflict_note": None,
        }
        if key not in pnl[yr]:
            pnl[yr][key] = {"primary": entry, "sources": [entry]}
        else:
            pnl[yr][key]["sources"].append(entry)
            if abs(pnl[yr][key]["primary"]["value"] - entry["value"]) > 0.5:
                pnl[yr][key]["primary"]["conflict"] = True
                conflict_count += 1

    # Balance data grouped by year
    balance_rows = conn.execute(
        """SELECT fiscal_year, line_item, value_k, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'balance'
             AND period_type = 'annual' AND value_k IS NOT NULL
           ORDER BY fiscal_year, line_item""",
        (domain,),
    ).fetchall()

    balance: dict[str, dict] = {}
    for r in balance_rows:
        yr = str(r["fiscal_year"]) if r["fiscal_year"] else "unknown"
        if yr not in balance:
            balance[yr] = {}
        key = r["line_item"]
        entry = {
            "value": r["value_k"],
            "source": r["source"],
            "conflict": False,
        }
        if key not in balance[yr]:
            balance[yr][key] = entry

    # Risk flags — computed on the fly
    from src.data import compute_risk_flags

    risk_flags = compute_risk_flags(conn, domain)

    # Documents
    docs = conn.execute(
        """SELECT file_name, doc_type, doc_subtype, fiscal_year, registered_at
           FROM deal_documents WHERE code_name = ?
           ORDER BY doc_type, fiscal_year, file_name""",
        (code_name,),
    ).fetchall()
    documents = [
        {
            "file_name": d["file_name"],
            "doc_type": d["doc_type"],
            "doc_subtype": d["doc_subtype"],
            "fiscal_year": d["fiscal_year"],
            "registered_at": d["registered_at"],
        }
        for d in docs
    ]

    # Notes
    notes_rows = conn.execute(
        """SELECT note, author, created_at FROM deal_notes
           WHERE domain = ? ORDER BY created_at DESC""",
        (domain,),
    ).fetchall()
    notes = [
        {"note": n["note"], "author": n["author"], "created_at": n["created_at"]}
        for n in notes_rows
    ]

    # Model adjusted P&L from deal_financials (is_adjusted=1)
    model_pnl_rows = conn.execute(
        """SELECT fiscal_year, line_item AS key, value_k AS value_num, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 1
             AND period_type = 'annual' AND value_k IS NOT NULL
           ORDER BY fiscal_year, line_item""",
        (domain,),
    ).fetchall()

    model_pnl: dict[str, dict] = {}
    for r in model_pnl_rows:
        yr = str(r["fiscal_year"]) if r["fiscal_year"] else "unknown"
        if yr not in model_pnl:
            model_pnl[yr] = {}
        model_pnl[yr][r["key"]] = {"value": r["value_num"], "source": r["source"]}

    # Bewertung data from deal_financials (statement='bewertung')
    bewertung_rows = conn.execute(
        """SELECT line_item AS key, value_k AS value_num, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'bewertung' AND is_adjusted = 1
             AND value_k IS NOT NULL""",
        (domain,),
    ).fetchall()
    bewertung = {r["key"]: r["value_num"] for r in bewertung_rows}

    # Model valuations from deal_valuations
    val_row = conn.execute(
        """SELECT * FROM deal_valuations
           WHERE domain = ? ORDER BY created_at DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    model_valuation = None
    if val_row:
        model_valuation = {
            "ebitda_basis": val_row["ebitda_basis"],
            "ebitda_basis_label": val_row["ebitda_basis_label"],
            "source_model_file": val_row["source_model_file"],
            "ev_low": val_row["ev_low"],
            "ev_mid": val_row["ev_mid"],
            "ev_high": val_row["ev_high"],
            "cash_at_closing": val_row["cash_at_closing"],
            "rueckbeteiligung": val_row["rueckbeteiligung"],
            "earnout_max": val_row["earnout_max"],
        }

    # EBITDA bridge: raw EBITDA vs adjusted EBITDA per year
    ebitda_bridge: dict[str, dict] = {}
    for yr_str in sorted(set(list(pnl.keys()) + list(model_pnl.keys()))):
        if yr_str == "unknown":
            continue
        raw_ebitda = None
        if yr_str in pnl and "ebitda" in pnl[yr_str]:
            raw_ebitda = pnl[yr_str]["ebitda"]["primary"]["value"]
        adj_ebitda = None
        if yr_str in model_pnl and "ebitda_adj" in model_pnl[yr_str]:
            adj_ebitda = model_pnl[yr_str]["ebitda_adj"]["value"]
        if raw_ebitda is not None or adj_ebitda is not None:
            ebitda_bridge[yr_str] = {
                "raw": raw_ebitda,
                "adjusted": adj_ebitda,
                "delta": round(adj_ebitda - raw_ebitda, 2)
                if (raw_ebitda is not None and adj_ebitda is not None)
                else None,
            }

    # Questions / RFI
    questions_data = _build_questions_data(conn, domain)

    q_counts = questions_data["counts"]
    question_count = q_counts.get("draft", 0) + q_counts.get("sent", 0)

    # Overview data (DR-M8)
    overview = _build_overview(conn, deal, domain)

    # Customer analysis
    customers = _build_customers(conn, domain)

    # Commercial DD (DR-M25) — computed live from deal_invoices + deal_customers
    from src.cdd import build_cdd

    try:
        cdd = build_cdd(conn, domain)
    except Exception as e:
        print(f"WARN: CDD build failed for {domain}: {e}")
        cdd = None

    # Onepager data (DR-M9)
    onepager_chart = _build_onepager_chart_data(conn, domain)

    # Auto-populate footnote if empty
    footnote = deal["onepager_footnote"]
    if not footnote:
        # Build from latest financial year + valuation date
        latest_fy = (
            max(onepager_chart["yearly"].keys()) if onepager_chart["yearly"] else None
        )
        val_date = (
            onepager_chart["valuation"]["valuation_date"]
            if onepager_chart["valuation"]
            else None
        )
        parts = [f"As of {datetime.now(timezone.utc).strftime('%d %b %Y')}"]
        if latest_fy:
            parts.append(f"Financials: FY{latest_fy}A")
        if val_date:
            parts.append(f"Valuation: {val_date}")
        footnote = " | ".join(parts)

    return {
        "mode": "deal",
        "deal": {
            "code_name": deal["code_name"],
            "company_name": deal["company_name"],
            "deal_stage": deal["deal_stage"],
            "stage_entered_at": deal["stage_entered_at"],
            "last_contact_at": deal["last_contact_at"],
            "days_in_stage": _days_since(deal["stage_entered_at"]),
            "days_since_contact": _days_since(deal["last_contact_at"]),
            "investment_thesis": deal["investment_thesis"],
            "seller_motivation": deal["seller_motivation"],
            "conflict_count": conflict_count,
            "question_count": question_count,
            "notes_field": deal["notes"],
            "folder_path": deal["folder_path"],
        },
        "financials": {
            "pnl": pnl,
            "balance": balance,
            "risk_flags": risk_flags,
            "ebitda_bridge": ebitda_bridge,
            **_build_unified_financials(conn, domain),
        },
        "model": {
            "pnl_adj": model_pnl,
            "bewertung": bewertung,
            "valuation": model_valuation,
            "ebitda_bridge": ebitda_bridge,
        },
        "model_context": _build_model_context(conn, domain),
        "overview": overview,
        "customers": customers,
        "cdd": cdd,
        "documents": documents,
        "notes": notes,
        "questions": questions_data,
        "onepager": {
            "title": deal["onepager_title"] or deal["company_name"],
            "headline": deal["onepager_headline"],
            "q1": deal["onepager_q1"],
            "q3": deal["onepager_q3"],
            "q4": deal["onepager_q4"],
            "footnote": footnote,
            "generated_at": deal["onepager_generated_at"],
            "edited_at": deal["onepager_edited_at"],
            "q1_approved": bool(deal["onepager_q1_approved"]),
            "q3_approved": bool(deal["onepager_q3_approved"]),
            "q4_approved": bool(deal["onepager_q4_approved"]),
        },
        "onepager_chart": onepager_chart,
        "dd_commentary": {col: deal[col] for col in _DD_CARD_COLS if deal[col]},
    }


def _build_customers(conn, domain: str) -> dict[str, Any]:
    """Build customer analysis data from deal_commercial + deal_customers."""
    # Metrics per year from deal_commercial
    metrics_rows = conn.execute(
        """SELECT fiscal_year, metric AS key, value_num FROM deal_commercial
           WHERE domain = ? AND category = 'customers'
             AND value_num IS NOT NULL
           ORDER BY fiscal_year, metric""",
        (domain,),
    ).fetchall()
    metrics: dict[str, dict] = {}
    for r in metrics_rows:
        yr = str(r["fiscal_year"])
        metrics.setdefault(yr, {})[r["key"]] = r["value_num"]

    # Top-10 per year from deal_customers
    top10_rows = conn.execute(
        """SELECT fiscal_year, customer_name AS name, revenue_k AS revenue,
                  revenue_pct AS pct, rank
           FROM deal_customers
           WHERE domain = ? AND revenue_k IS NOT NULL
           ORDER BY fiscal_year, rank, revenue_k DESC""",
        (domain,),
    ).fetchall()
    top10: dict[str, list] = {}
    for r in top10_rows:
        yr = str(r["fiscal_year"])
        top10.setdefault(yr, []).append(
            {
                "name": r["name"],
                "revenue": r["revenue"],
                "pct": r["pct"],
                "rank": r["rank"],
            }
        )
    for yr in top10:
        top10[yr].sort(key=lambda x: (x["rank"] or 99, -(x["revenue"] or 0)))
        top10[yr] = top10[yr][:10]

    # Service split from deal_commercial (category='service_split')
    svc_rows = conn.execute(
        """SELECT metric, value_num FROM deal_commercial
           WHERE domain = ? AND category = 'service_split' AND value_num IS NOT NULL
           ORDER BY value_num DESC""",
        (domain,),
    ).fetchall()
    service_split = [
        {"label": r["metric"], "pct": float(r["value_num"])} for r in svc_rows
    ]

    return {"metrics": metrics, "top10": top10, "service_split": service_split}


def _build_overview(conn, deal, domain: str) -> dict[str, Any]:
    """Build company overview data from ALLEX + dealroom sources (DR-M8)."""
    overview: dict[str, Any] = {}

    # ALLEX company data (may not be available in test environment)
    allex_row = None
    try:
        _attach_allex(conn)
        allex_row = conn.execute(
            """SELECT full_name, street, plz_ort, city, region, ma_count, revenue_tsd_eur,
                      leistung_text, rechtsform, hrb_number,
                      gesellschafter_name, gesellschafter_age, gesellschafter_share_pct,
                      gf_name, gf_email, gf_phone, owner_name
               FROM allex.company_records WHERE domain = ? LIMIT 1""",
            (domain,),
        ).fetchone()
    except Exception:
        pass

    if allex_row:
        age = allex_row["gesellschafter_age"]
        overview.update(
            {
                "legal_name": allex_row["full_name"],
                "street": allex_row["street"],
                "plz_ort": allex_row["plz_ort"],
                "city": allex_row["city"],
                "region": allex_row["region"],
                "employees_allex": allex_row["ma_count"],
                "revenue_allex_k": allex_row["revenue_tsd_eur"],
                "services": allex_row["leistung_text"],
                "rechtsform": allex_row["rechtsform"],
                "hrb": allex_row["hrb_number"],
                "owner_name": allex_row["owner_name"]
                or allex_row["gesellschafter_name"],
                "owner_age_allex": age if age and 20 <= age <= 100 else None,
                "owner_share_pct": allex_row["gesellschafter_share_pct"],
                "gf_name": allex_row["gf_name"],
                "gf_email": allex_row["gf_email"],
                "gf_phone": allex_row["gf_phone"],
            }
        )

    # Deal-level data (some columns added by migration — access safely)
    deal_dict = dict(deal)
    overview["description"] = deal_dict.get("description") or ""
    overview["investment_thesis"] = deal_dict.get("investment_thesis") or ""
    overview["seller_motivation"] = deal_dict.get("seller_motivation") or ""
    overview["seller_age"] = deal_dict.get("seller_age_approx")
    overview["seller_notes"] = deal_dict.get("seller_profile_notes") or ""

    # Financial snapshot — prefer adjusted, combine gesamtleistung+revenue
    rev_row = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND line_item IN ('gesamtleistung', 'revenue')
             AND period_type = 'annual' AND value_k IS NOT NULL
           ORDER BY is_adjusted DESC, fiscal_year DESC,
             CASE line_item WHEN 'gesamtleistung' THEN 0 ELSE 1 END
           LIMIT 1""",
        (domain,),
    ).fetchone()
    if rev_row:
        overview["revenue_k"] = rev_row["value_k"]
        overview["revenue_year"] = rev_row["fiscal_year"]
    for metric, items in [
        ("ebitda", ("ebitda_adj", "ebitda")),
        ("ebit", ("ebit_adj", "ebit")),
    ]:
        placeholders = ",".join("?" * len(items))
        row = conn.execute(
            f"""SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl'
                 AND line_item IN ({placeholders})
                 AND period_type = 'annual' AND value_k IS NOT NULL
               ORDER BY is_adjusted DESC, fiscal_year DESC LIMIT 1""",
            (domain, *items),
        ).fetchone()
        if row:
            overview[f"{metric}_k"] = row["value_k"]
            overview[f"{metric}_year"] = row["fiscal_year"]

    # EBITDA margin
    rev_k = overview.get("revenue_k")
    ebitda_k = overview.get("ebitda_k")
    if rev_k and ebitda_k and rev_k != 0:
        overview["ebitda_margin_pct"] = round(ebitda_k / rev_k * 100, 1)

    # Employee count: deal_commercial > ALLEX
    emp_row = conn.execute(
        """SELECT value_num FROM deal_commercial
           WHERE domain = ? AND metric = 'headcount'
             AND value_num IS NOT NULL
           ORDER BY fiscal_year DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    overview["employees"] = (
        int(emp_row["value_num"]) if emp_row else overview.get("employees_allex")
    )

    # Commercial KPIs
    for key in ["recurring_pct", "top3_share_pct"]:
        kpi_row = conn.execute(
            """SELECT value_num FROM deal_commercial
               WHERE domain = ? AND metric = ?
                 AND value_num IS NOT NULL
               ORDER BY fiscal_year DESC LIMIT 1""",
            (domain, key),
        ).fetchone()
        if kpi_row:
            overview[key] = kpi_row["value_num"]

    # Revenue CAGR — prefer adjusted, MAX per year to avoid subsidiary contamination
    rev_rows = conn.execute(
        """SELECT fiscal_year, MAX(value_k) AS value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND line_item IN ('gesamtleistung', 'revenue')
             AND is_adjusted = 1 AND period_type = 'annual' AND value_k IS NOT NULL
           GROUP BY fiscal_year ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    if len(rev_rows) < 2:
        rev_rows = conn.execute(
            """SELECT fiscal_year, MAX(value_k) AS value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl'
                 AND line_item IN ('gesamtleistung', 'revenue')
                 AND period_type = 'annual' AND value_k IS NOT NULL
               GROUP BY fiscal_year ORDER BY fiscal_year""",
            (domain,),
        ).fetchall()
    if len(rev_rows) >= 2:
        first_rev = rev_rows[0]["value_k"]
        last_rev = rev_rows[-1]["value_k"]
        n = rev_rows[-1]["fiscal_year"] - rev_rows[0]["fiscal_year"]
        if n > 0 and first_rev > 0 and last_rev > 0:
            overview["revenue_cagr"] = round((last_rev / first_rev) ** (1 / n) - 1, 4)
            overview["revenue_cagr_period"] = (
                f"{rev_rows[0]['fiscal_year']}-{rev_rows[-1]['fiscal_year']}"
            )

    # Financial timeline: revenue + adj. EBITDA per year
    timeline: dict[str, dict[str, float | None]] = {}
    for r in rev_rows:
        yr = str(r["fiscal_year"])
        timeline.setdefault(yr, {})["revenue"] = r["value_k"]
    # Adj. EBITDA from deal_financials (is_adjusted=1)
    adj_ebitda_rows = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 1
             AND line_item = 'ebitda_adj' AND period_type = 'annual'
             AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    for r in adj_ebitda_rows:
        yr = str(r["fiscal_year"])
        timeline.setdefault(yr, {})["ebitda_adj"] = r["value_k"]
    # Raw EBITDA fallback
    raw_ebitda_rows = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 0
             AND line_item = 'ebitda' AND period_type = 'annual'
             AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    for r in raw_ebitda_rows:
        yr = str(r["fiscal_year"])
        if yr not in timeline or "ebitda_adj" not in timeline[yr]:
            timeline.setdefault(yr, {})["ebitda_adj"] = r["value_k"]
    overview["financial_timeline"] = dict(sorted(timeline.items()))

    return overview


def _build_questions_data(conn, domain: str) -> dict[str, Any]:
    """Build questions payload for dashboard Open Topics tab."""
    from src.generate.rfi import source_label as _source_label

    rows = conn.execute(
        """SELECT id, question, category, subcategory, importance, source, status, answer, answer_source
           FROM deal_questions WHERE domain = ? ORDER BY sort_order, category, created_at""",
        (domain,),
    ).fetchall()

    counts: dict[str, int] = {
        "draft": 0,
        "sent": 0,
        "answered": 0,
        "waived": 0,
        "total": 0,
    }
    by_section: dict[str, list] = {"financial": [], "commercial": [], "general": []}

    for q in rows:
        status = q["status"] or "draft"
        counts["total"] += 1
        if status in counts:
            counts[status] += 1

        cat = q["category"] if q["category"] in by_section else "general"
        src = q["source"] or "manual"
        by_section[cat].append(
            {
                "id": q["id"],
                "question": q["question"],
                "subcategory": q["subcategory"] or "",
                "importance": q["importance"] or "medium",
                "source": src,
                "source_label": _source_label(src),
                "status": status,
                "answer": q["answer"],
                "answer_source": q["answer_source"],
            }
        )

    return {"counts": counts, "by_section": by_section}


def _build_model_context(conn, domain: str) -> dict | None:
    """Build valuation model context for a deal. Returns None on error."""
    try:
        from src.valuation import build_model_context

        return build_model_context(conn, domain)
    except Exception:
        import traceback

        traceback.print_exc()
        return None


def _build_onepager_chart_data(conn, domain: str) -> dict[str, Any]:
    """Build Q2 P&L table data: revenue, EBITDA, EBIT per year + CT + CAGR + valuation."""

    def _max_per_year(rows, key="value_k"):
        """Pick the MAX value per fiscal_year to handle multi-entity duplicates."""
        best: dict[int, float] = {}
        for r in rows:
            yr = r["fiscal_year"]
            v = r[key]
            if yr not in best or (v is not None and v > best.get(yr, float("-inf"))):
                best[yr] = v
        return best

    # Revenue priority: model-adjusted revenue (from GuV) > BWA gesamtleistung > raw revenue.
    # Model is the valuation basis — one-pager must match model numbers.
    gl_rows = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND line_item = 'gesamtleistung'
             AND period_type = 'annual' AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    adj_rev_rows = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND line_item = 'revenue'
             AND period_type = 'annual' AND is_adjusted = 1 AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    raw_rev_rows = conn.execute(
        """SELECT fiscal_year, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND line_item = 'revenue'
             AND period_type = 'annual' AND is_adjusted = 0 AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    gl_by_yr = _max_per_year(gl_rows)
    adj_rev_by_yr = _max_per_year(adj_rev_rows)
    raw_rev_by_yr = _max_per_year(raw_rev_rows)

    yearly: dict[str, dict] = {}
    for yr in sorted(set(gl_by_yr) | set(adj_rev_by_yr) | set(raw_rev_by_yr)):
        adj = adj_rev_by_yr.get(yr)
        gl = gl_by_yr.get(yr)
        raw = raw_rev_by_yr.get(yr)
        rev = adj if adj is not None else (gl if gl is not None else raw)
        # Skip empty/zero-revenue plan-year columns (e.g. an unfilled FY2026
        # column carried in from the model). The explicit BP/plan column is
        # rendered separately from deals.bp_2026_* fields.
        if not rev:
            continue
        yearly[str(yr)] = {"revenue_k": rev}
    all_years = sorted(int(y) for y in yearly)

    # EBITDA: prefer adjusted, fall back to raw — pick MAX per year
    adj_ebitda = _max_per_year(
        conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 1
                 AND line_item = 'ebitda_adj' AND period_type = 'annual' AND value_k IS NOT NULL""",
            (domain,),
        ).fetchall()
    )
    raw_ebitda = _max_per_year(
        conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 0
                 AND line_item = 'ebitda' AND period_type = 'annual' AND value_k IS NOT NULL""",
            (domain,),
        ).fetchall()
    )
    for yr in all_years:
        s = str(yr)
        if yr in adj_ebitda:
            yearly.setdefault(s, {})["ebitda_k"] = adj_ebitda[yr]
            yearly[s]["ebitda_is_adj"] = True
        elif yr in raw_ebitda:
            yearly.setdefault(s, {})["ebitda_k"] = raw_ebitda[yr]
            yearly[s]["ebitda_is_adj"] = False

    # EBIT: prefer adjusted (model stores ebit_adj)
    adj_ebit = _max_per_year(
        conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 1
                 AND line_item IN ('ebit_adj', 'ebit') AND period_type = 'annual' AND value_k IS NOT NULL""",
            (domain,),
        ).fetchall()
    )
    raw_ebit = _max_per_year(
        conn.execute(
            """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 0
                 AND line_item = 'ebit' AND period_type = 'annual' AND value_k IS NOT NULL""",
            (domain,),
        ).fetchall()
    )
    for yr in all_years:
        s = str(yr)
        v = adj_ebit.get(yr) or raw_ebit.get(yr)
        if v is not None:
            yearly.setdefault(s, {})["ebit_k"] = v

    # Cost of sales (adj preferred)
    def _fetch_adj_line(line_adj, line_raw):
        adj = _max_per_year(
            conn.execute(
                """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND line_item = ?
                 AND period_type = 'annual' AND value_k IS NOT NULL""",
                (domain, line_adj),
            ).fetchall()
        )
        raw = _max_per_year(
            conn.execute(
                """SELECT fiscal_year, value_k FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND line_item = ?
                 AND period_type = 'annual' AND value_k IS NOT NULL""",
                (domain, line_raw),
            ).fetchall()
        )
        return {
            yr: adj.get(yr) or raw.get(yr)
            for yr in set(adj) | set(raw)
            if adj.get(yr) or raw.get(yr)
        }

    cogs_by_yr = _fetch_adj_line("cogs_adj", "cogs")
    personnel_by_yr = _fetch_adj_line("personnel_adj", "personnel")
    opex_by_yr = _fetch_adj_line("other_opex_adj", "other_opex")
    opin_by_yr = _fetch_adj_line("other_income_adj", "other_income")

    for yr in all_years:
        s = str(yr)
        if yr in cogs_by_yr:
            yearly.setdefault(s, {})["cogs_k"] = cogs_by_yr[yr]
        if yr in personnel_by_yr:
            yearly.setdefault(s, {})["personnel_k"] = personnel_by_yr[yr]
        opex_val = opex_by_yr.get(yr, 0) or 0
        opin_val = opin_by_yr.get(yr, 0) or 0
        if opex_val or opin_val:
            yearly.setdefault(s, {})["opex_net_k"] = opex_val - opin_val
        rev = yearly.get(s, {}).get("revenue_k")
        cogs = yearly.get(s, {}).get("cogs_k")
        if rev is not None and cogs is not None:
            yearly.setdefault(s, {})["gross_margin_k"] = rev - cogs

    # Compute margins and KPI percentages
    for yr, vals in yearly.items():
        rev = vals.get("revenue_k")
        if not rev or rev == 0:
            continue
        ebitda = vals.get("ebitda_k")
        if ebitda is not None:
            vals["margin_pct"] = round(ebitda / rev * 100, 1)
        ebit = vals.get("ebit_k")
        if ebit is not None:
            vals["ebit_margin_pct"] = round(ebit / rev * 100, 1)
        gm = vals.get("gross_margin_k")
        if gm is not None:
            vals["gross_margin_pct"] = round(gm / rev * 100, 1)
        pex = vals.get("personnel_k")
        if pex is not None:
            vals["pex_pct"] = round(pex / rev * 100, 1)
        opex_net = vals.get("opex_net_k")
        if opex_net is not None:
            vals["opex_net_pct"] = round(opex_net / rev * 100, 1)

    # Topline growth YoY
    sorted_years = sorted(yearly.keys())
    for i in range(1, len(sorted_years)):
        prev_rev = yearly[sorted_years[i - 1]].get("revenue_k")
        cur_rev = yearly[sorted_years[i]].get("revenue_k")
        if prev_rev and cur_rev and prev_rev > 0:
            yearly[sorted_years[i]]["topline_growth_pct"] = round(
                (cur_rev / prev_rev - 1) * 100, 1
            )

    # Current trading (LTM/YTD)
    current_trading = {}
    for pt in ("ltm", "ytd"):
        for li in ("gesamtleistung", "revenue", "ebitda", "ebitda_adj"):
            row = conn.execute(
                """SELECT value_k, period FROM deal_financials
                   WHERE domain = ? AND statement = 'pnl' AND line_item = ?
                     AND period_type = ? AND value_k IS NOT NULL
                   ORDER BY extracted_at DESC LIMIT 1""",
                (domain, li, pt),
            ).fetchone()
            if row:
                key = "revenue" if li in ("gesamtleistung", "revenue") else "ebitda"
                ct_key = f"{key}_{pt}_k"
                if ct_key not in current_trading:
                    current_trading[ct_key] = row["value_k"]
                    if row["period"]:
                        current_trading[f"{key}_{pt}_period"] = row["period"]

    # Valuation metrics
    val_row = conn.execute(
        """SELECT ev_mid, ev_low, ev_high, earnout_max, ebitda_basis, valuation_date
           FROM deal_valuations WHERE domain = ? ORDER BY created_at DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    valuation = None
    if val_row:
        ev_mid = val_row["ev_mid"] or 0
        earnout = val_row["earnout_max"] or 0
        basis = val_row["ebitda_basis"]
        implied_multiple = None
        if basis and basis > 0 and (ev_mid + earnout) > 0:
            implied_multiple = round((ev_mid + earnout) / basis, 1)
        valuation = {
            "ev_low": val_row["ev_low"],
            "ev_mid": val_row["ev_mid"],
            "ev_high": val_row["ev_high"],
            "earnout_max": val_row["earnout_max"],
            "ebitda_basis": val_row["ebitda_basis"],
            "implied_multiple": implied_multiple,
            "valuation_date": val_row["valuation_date"],
        }

    # CAGR (revenue + EBITDA)
    cagr = None
    ebitda_cagr = None
    if len(sorted_years) >= 2:
        first_rev = yearly[sorted_years[0]].get("revenue_k")
        last_rev = yearly[sorted_years[-1]].get("revenue_k")
        n = int(sorted_years[-1]) - int(sorted_years[0])
        if n > 0 and first_rev and first_rev > 0 and last_rev and last_rev > 0:
            cagr = round((last_rev / first_rev) ** (1 / n) - 1, 4)
        first_eb = yearly[sorted_years[0]].get("ebitda_k")
        last_eb = yearly[sorted_years[-1]].get("ebitda_k")
        if n > 0 and first_eb and first_eb > 0 and last_eb and last_eb > 0:
            ebitda_cagr = round((last_eb / first_eb) ** (1 / n) - 1, 4)

    # Valuation bridge items from deal_financials
    bridge = {}
    for li in (
        "ev_at_closing",
        "ev_anticipated_earnout",
        "ev_total",
        "net_cash_debt",
        "equity_value",
    ):
        row = conn.execute(
            """SELECT value_k FROM deal_financials
               WHERE domain = ? AND line_item = ? AND value_k IS NOT NULL
               ORDER BY extracted_at DESC LIMIT 1""",
            (domain, li),
        ).fetchone()
        if row:
            bridge[li] = row["value_k"]

    # Permitted leakage (if stored)
    leak_row = conn.execute(
        """SELECT value_k FROM deal_financials
           WHERE domain = ? AND line_item = 'permitted_leakage' AND value_k IS NOT NULL
           ORDER BY extracted_at DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    if leak_row:
        bridge["permitted_leakage"] = leak_row["value_k"]

    # 2026 Business Plan scenario (fiscal_year=2026, period_type='budget' or 'annual')
    bp_2026: dict[str, Any] = {}
    for li, key in [
        ("gesamtleistung", "revenue_k"),
        ("revenue", "revenue_k"),
        ("ebitda_adj", "ebitda_k"),
        ("ebitda", "ebitda_k"),
    ]:
        if key not in bp_2026:
            row = conn.execute(
                """SELECT value_k FROM deal_financials
                   WHERE domain = ? AND statement = 'pnl' AND line_item = ?
                     AND fiscal_year = 2026
                     AND period_type IN ('annual', 'budget')
                     AND value_k IS NOT NULL
                   ORDER BY is_adjusted DESC, extracted_at DESC LIMIT 1""",
                (domain, li),
            ).fetchone()
            if row:
                bp_2026[key] = row["value_k"]

    # 2026 MAX Earn-Out scenario — stored from Bewertung as ebitda_max_earnout
    maxeo_2026: dict[str, Any] = {}
    row = conn.execute(
        """SELECT value_k FROM deal_financials
           WHERE domain = ? AND line_item = 'ebitda_max_earnout' AND value_k IS NOT NULL
           ORDER BY extracted_at DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    if row:
        maxeo_2026["ebitda_k"] = row["value_k"]

    # Apply user overrides (takes precedence over model-extracted values)
    try:
        ov = conn.execute(
            "SELECT bp_2026_rev_k, bp_2026_ebitda_k, maxeo_2026_ebitda_k FROM deals WHERE domain = ?",
            (domain,),
        ).fetchone()
        if ov:
            if ov["bp_2026_rev_k"] is not None:
                bp_2026["revenue_k"] = ov["bp_2026_rev_k"]
            if ov["bp_2026_ebitda_k"] is not None:
                bp_2026["ebitda_k"] = ov["bp_2026_ebitda_k"]
            if ov["maxeo_2026_ebitda_k"] is not None:
                maxeo_2026["ebitda_k"] = ov["maxeo_2026_ebitda_k"]
    except Exception:
        pass

    return {
        "yearly": dict(sorted(yearly.items())),
        "current_trading": current_trading,
        "valuation": valuation,
        "bridge": bridge,
        "bp_2026": bp_2026,
        "maxeo_2026": maxeo_2026,
        "cagr": cagr,
        "ebitda_cagr": ebitda_cagr,
    }


def build_dashboard_data(conn, code_name: str | None = None) -> dict[str, Any]:
    if code_name:
        return build_deal_data(conn, code_name)
    return build_portfolio_data(conn)


# ─── HTML builder + HTTP server ───────────────────────────────────────────────


def _compute_investor_ctx(auth_header, query, internal, investor):
    """Pure access decision for the investor portal.

    `internal` / `investor` are (user, pass) tuples ("" when unset). `query` is a
    parse_qs dict. Returns (authorized: bool, is_investor: bool, watermark_label: str).

    - No credentials configured anywhere => open (internal) access, with investor
      preview available via the `?view=investor&as=NAME` flag (intended for localhost).
    - Credentials configured => Basic Auth required. The investor credential maps to
      investor mode (watermark = its username); the internal credential to full mode;
      anything else is unauthorized.
    """
    req_user = req_pass = None
    if auth_header.startswith("Basic "):
        try:
            req_user, req_pass = (
                base64.b64decode(auth_header[6:]).decode("utf-8").split(":", 1)
            )
        except Exception:
            req_user = req_pass = None
    iu, ip = investor
    nu, np_ = internal
    if not (iu or nu):  # no creds configured
        if query.get("view", [None])[0] == "investor":
            return True, True, (query.get("as", ["investor"])[0] or "investor")[:60]
        return True, False, ""
    if iu and req_user == iu and req_pass == ip:
        return True, True, iu
    if nu and req_user == nu and req_pass == np_:
        return True, False, ""
    return False, False, ""


def _sanitize_investor(data):
    """Allow-list scrub of a dashboard payload for an investor session.

    Investors see only the pipeline and the one-pager, so everything else is emptied
    server-side: no real name / domain / owner / address / document filename / customer
    name can be recovered from the embedded page JSON or /api/data. Preserved: codename
    identity, one-pager bullet text + chart (name-free), and customer AGGREGATES.
    """
    # Portfolio mode: drop identifying columns from each row.
    if data.get("mode") == "portfolio":
        for row in data.get("deals", []) or []:
            if isinstance(row, dict):
                row.pop("company_name", None)
                row.pop("domain", None)
        return data

    # Deal mode: scrub the deal record down to safe fields.
    deal = data.get("deal") or {}
    code = deal.get("code_name")
    if code:
        deal["company_name"] = code
    for k in (
        "domain",
        "folder_path",
        "investment_thesis",
        "seller_motivation",
        "seller_profile_notes",
        "seller_age_approx",
        "notes_field",
        "last_contact_at",
        "stage_entered_at",
    ):
        deal.pop(k, None)
    deal["conflict_count"] = 0
    deal["question_count"] = 0
    deal["days_since_contact"] = None

    op = data.get("onepager")
    if isinstance(op, dict) and code:
        op["title"] = code

    # Customers: keep service_split + aggregate concentration; blank real names.
    cust = data.get("customers")
    if isinstance(cust, dict) and isinstance(cust.get("top10"), dict):
        for rows in cust["top10"].values():
            for i, r in enumerate(rows or []):
                if isinstance(r, dict):
                    r["name"] = "Customer %d" % (r.get("rank") or i + 1)

    # Empty every section the investor UI never renders but that carries identity.
    for k in ("financials", "model", "model_context", "overview", "ebitda_bridge"):
        if k in data:
            data[k] = {}
    for k in ("documents", "notes"):
        if k in data:
            data[k] = []
    if "questions" in data:
        data["questions"] = {"counts": {}, "questions": []}

    return data


def _build_html(
    data: dict,
    serve_mode: bool = False,
    investor_mode: bool = False,
    watermark_label: str = "",
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    data_json = json.dumps(data, ensure_ascii=False, default=str)
    html = template.replace("__DATA_JSON__", data_json)
    html = html.replace("__SERVE_MODE_JS__", "true" if serve_mode else "false")
    html = html.replace("__INVESTOR_MODE_JS__", "true" if investor_mode else "false")
    # json.dumps yields a safely-quoted JS string literal for the watermark.
    html = html.replace("__WATERMARK_LABEL__", json.dumps(watermark_label))
    html = html.replace("__LIVE_BADGE__", "LIVE" if serve_mode else "STATIC")
    html = html.replace("__DATE_STR__", datetime.now().strftime("%Y-%m-%d"))
    sections_dir = TEMPLATE_PATH.parent / "sections"
    sections_js = ""
    if sections_dir.exists():
        for js_file in sorted(sections_dir.glob("*.js")):
            sections_js += js_file.read_text(encoding="utf-8") + "\n"
    html = html.replace("__SECTIONS_JS__", sections_js)
    return html


def serve_dashboard(
    conn,
    code_name: str | None = None,
    port: int = DEFAULT_PORT,
    serve: bool = False,
) -> None:
    data = build_dashboard_data(conn, code_name)

    if serve:
        html = _build_html(data, serve_mode=True)
        _start_server(html, conn, code_name, port)
    else:
        html = _build_html(data, serve_mode=False)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        suffix = f"_{code_name}" if code_name else ""
        out_path = OUTPUT_DIR / f"dashboard{suffix}_{datetime.now():%Y%m%d}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"Dashboard written to {out_path}")
        webbrowser.open(str(out_path))


def _start_server(html: str, conn, code_name: str | None, port: int) -> None:
    import sqlite3 as _sqlite3
    from urllib.parse import urlparse, parse_qs

    # Re-open a thread-safe connection for ThreadingHTTPServer.
    # Replicate attached databases (allex) from the original connection.
    dbs = conn.execute("PRAGMA database_list").fetchall()
    db_path = dbs[0][2]
    conn = _sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = _sqlite3.Row
    for row in dbs:
        if row[1] != "main" and row[2]:
            try:
                conn.execute(f"ATTACH DATABASE ? AS {row[1]}", (row[2],))
            except Exception:
                pass

    # Single lock guards all access to the shared conn across threads.
    _conn_lock = threading.Lock()

    _ONEPAGER_SAVE_FIELDS = {
        "onepager_title",
        "onepager_headline",
        "onepager_q1",
        "onepager_q3",
        "onepager_q4",
        "onepager_footnote",
        "onepager_q1_approved",
        "onepager_q3_approved",
        "onepager_q4_approved",
        "bp_2026_rev_k",
        "bp_2026_ebitda_k",
        "maxeo_2026_ebitda_k",
        # DR-M9b: financials tab projection assumptions + comments
        "pnl_row_comments",
        "proj_topline_growth_pct",
        "proj_gm_pct",
        "proj_ebitda_margin_pct",
    }
    _DD_CARD_FIELDS = {
        "bm_segments_comment",
        "bm_margin_comment",
        "bm_revquality_comment",
        "bm_tieout_comment",
        "bm_description",
        "thesis_scorecard_comment",
        "thesis_swot_comment",
        "thesis_rationale",
    }
    _ALLOWED_SAVE_FIELDS = (
        set(_PORTFOLIO_OVERRIDE_COLS) | _ONEPAGER_SAVE_FIELDS | _DD_CARD_FIELDS
    )

    # Investor portal auth (Basic Auth). All optional — if no creds are set in the
    # environment, the server stays open (local dev / internal) and investor mode
    # is reachable only via the localhost ?view=investor preview flag.
    _INTERNAL = (
        os.environ.get("DEALROOM_AUTH_USER", ""),
        os.environ.get("DEALROOM_AUTH_PASS", ""),
    )
    _INVESTOR = (
        os.environ.get("DEALROOM_INVESTOR_USER", ""),
        os.environ.get("DEALROOM_INVESTOR_PASS", ""),
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        def _parse_deal(self) -> str | None:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            return qs.get("deal", [None])[0] or code_name

        def _investor_ctx(self):
            """(authorized, is_investor, watermark_label) for this request."""
            qs = parse_qs(urlparse(self.path).query)
            return _compute_investor_ctx(
                self.headers.get("Authorization", ""), qs, _INTERNAL, _INVESTOR
            )

        def _send_auth_challenge(self) -> None:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="DEALROOM"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            ok, investor, wm_label = self._investor_ctx()
            if not ok:
                self._send_auth_challenge()
                return
            if investor and parsed.path in ("/api/model-context", "/api/financials"):
                # These expose model internals + source filenames — not for investors.
                self._json_response({"error": "not available in investor view"}, 403)
                return

            with _conn_lock:
                if parsed.path == "/api/model-context":
                    from src.valuation import build_model_context

                    deal_code = qs.get("deal", [None])[0] or code_name
                    scenario = qs.get("scenario", ["base"])[0]
                    if deal_code:
                        deal_row = conn.execute(
                            "SELECT domain, code_name FROM deals WHERE code_name = ? COLLATE NOCASE",
                            (deal_code,),
                        ).fetchone()
                        if deal_row:
                            domain = deal_row["domain"] or deal_row["code_name"].lower()
                            ctx = build_model_context(conn, domain, scenario)
                            self._json_response(ctx)
                            return
                    self._json_response({"error": "deal not found"}, 404)
                    return

            if parsed.path == "/api/data":
                deal = self._parse_deal()
                with _conn_lock:
                    fresh = build_dashboard_data(conn, deal)
                if investor:
                    fresh = _sanitize_investor(fresh)
                body = json.dumps(fresh, ensure_ascii=False, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            elif parsed.path == "/api/financials":
                deal = self._parse_deal()
                with _conn_lock:
                    deal_row = conn.execute(
                        "SELECT * FROM deals WHERE code_name = ?", (deal,)
                    ).fetchone()
                    if not deal_row:
                        self._json_response({"error": "deal not found"}, 404)
                        return
                    entity = qs.get("entity", ["consolidated"])[0]
                    domain = _domain_for(deal_row)
                    fin = _build_unified_financials(conn, domain, entity=entity)
                self._json_response(fin)

            else:
                deal = self._parse_deal()
                with _conn_lock:
                    data = build_dashboard_data(conn, deal)
                if investor:
                    data = _sanitize_investor(data)
                page = _build_html(
                    data,
                    serve_mode=True,
                    investor_mode=investor,
                    watermark_label=wm_label,
                )
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def _json_response(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                return json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, TypeError, ValueError):
                return None

        def do_POST(self) -> None:
            parsed = urlparse(self.path)

            ok, investor, _ = self._investor_ctx()
            if not ok:
                self._send_auth_challenge()
                return
            if investor:
                # Investor sessions are strictly read-only — reject every mutation
                # server-side, independent of the frontend hiding edit controls.
                self._json_response({"error": "read-only investor session"}, 403)
                return

            # ── Model param endpoints (DR-M7) ───────────────────────────
            if parsed.path == "/api/model-params":
                from src.valuation import save_model_params, build_model_context

                body = self._read_json_body()
                if body is None:
                    self._json_response({"error": "invalid JSON body"}, 400)
                    return
                domain = body.get("domain", "")
                scenario = body.get("scenario", "base")
                params = body.get("params", {})
                if not domain:
                    self._json_response({"error": "domain required"}, 400)
                    return
                with _conn_lock:
                    save_model_params(conn, domain, params, scenario)
                    ctx = build_model_context(conn, domain, scenario)
                self._json_response(ctx)
                return

            if parsed.path == "/api/model-add-tier":
                from src.valuation import (
                    load_model_params,
                    save_model_params,
                    build_model_context,
                )

                body = self._read_json_body()
                if body is None:
                    self._json_response({"error": "invalid JSON body"}, 400)
                    return
                domain = body.get("domain", "")
                scenario = body.get("scenario", "base")
                if not domain:
                    self._json_response({"error": "domain required"}, 400)
                    return
                with _conn_lock:
                    params = load_model_params(conn, domain, scenario) or {}
                    tiers = params.get("earnout_tiers_json", [])
                    if isinstance(tiers, str):
                        tiers = json.loads(tiers)
                    tiers = list(tiers or [])
                    tiers.append(tiers[-1] if tiers else 0)
                    params["earnout_tiers_json"] = tiers
                    save_model_params(conn, domain, params, scenario)
                    ctx = build_model_context(conn, domain, scenario)
                self._json_response(ctx)
                return

            if parsed.path == "/api/model-remove-tier":
                from src.valuation import (
                    load_model_params,
                    save_model_params,
                    build_model_context,
                )

                body = self._read_json_body()
                if body is None:
                    self._json_response({"error": "invalid JSON body"}, 400)
                    return
                domain = body.get("domain", "")
                scenario = body.get("scenario", "base")
                index = body.get("index", -1)
                if not domain:
                    self._json_response({"error": "domain required"}, 400)
                    return
                with _conn_lock:
                    params = load_model_params(conn, domain, scenario) or {}
                    tiers = params.get("earnout_tiers_json", [])
                    if isinstance(tiers, str):
                        tiers = json.loads(tiers)
                    tiers = list(tiers or [])
                    if tiers and 0 <= index < len(tiers):
                        tiers.pop(index)
                    elif tiers:
                        tiers.pop()
                    params["earnout_tiers_json"] = tiers
                    save_model_params(conn, domain, params, scenario)
                    ctx = build_model_context(conn, domain, scenario)
                self._json_response(ctx)
                return

            if parsed.path == "/api/model-context":
                from src.valuation import build_model_context

                body = self._read_json_body()
                if body is None:
                    self._json_response({"error": "invalid JSON body"}, 400)
                    return
                domain = body.get("domain", "")
                scenario = body.get("scenario", "base")
                if not domain:
                    self._json_response({"error": "domain required"}, 400)
                    return
                with _conn_lock:
                    ctx = build_model_context(conn, domain, scenario)
                self._json_response(ctx)
                return

            if parsed.path == "/api/portfolio-comments":
                body = self._read_json_body()
                if body is None:
                    self._json_response({"error": "invalid JSON body"}, 400)
                    return
                key = body.get("key", "portfolio_comments")
                text = body.get("value", "")
                if key in ("portfolio_comments", "portfolio_pipeline_comments"):
                    with _conn_lock:
                        _save_portfolio_meta(conn, key, text)
                self._json_response({"ok": True})
                return

            if parsed.path != "/api/update":
                self._json_response({"error": "not found"}, 404)
                return
            body = self._read_json_body()
            if body is None:
                self._json_response({"error": "invalid JSON body"}, 400)
                return
            code = body.get("code_name", "").strip()
            field = body.get("field", "").strip()
            value = body.get("value")
            if not code or field not in _ALLOWED_SAVE_FIELDS:
                self._json_response({"error": "invalid code_name or field"}, 400)
                return
            # Cast numeric fields
            if field in (
                "rev_m_override",
                "ebitda_m_override",
                "ev_m_override",
                "multiple_override",
            ):
                try:
                    value = float(value) if value not in (None, "", "—", "-") else None
                except (TypeError, ValueError):
                    value = None
            elif field == "employees_override":
                try:
                    value = int(value) if value not in (None, "", "—", "-") else None
                except (TypeError, ValueError):
                    value = None
            elif field in (
                "bp_2026_rev_k",
                "bp_2026_ebitda_k",
                "maxeo_2026_ebitda_k",
                "proj_topline_growth_pct",
                "proj_gm_pct",
                "proj_ebitda_margin_pct",
            ):
                try:
                    if value not in (None, "", "—", "-", "–"):
                        s = str(value).strip().replace("(", "-").replace(")", "")
                        s = s.replace(".", "").replace(",", ".")
                        value = float(s)
                    else:
                        value = None
                except (TypeError, ValueError):
                    value = None
            elif field in (
                "onepager_q1_approved",
                "onepager_q3_approved",
                "onepager_q4_approved",
            ):
                value = 1 if value else 0
            # Special handling: deal_stage also updates stage_entered_at
            if field == "deal_stage":
                with _conn_lock:
                    conn.execute(
                        "UPDATE deals SET deal_stage = ?, stage_entered_at = ? WHERE code_name = ?",
                        (
                            value,
                            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            code,
                        ),
                    )
                    conn.commit()
                self._json_response({"ok": True})
                return
            with _conn_lock:
                conn.execute(
                    f"UPDATE deals SET {field} = ? WHERE code_name = ?", (value, code)
                )
                if field in ("onepager_q1", "onepager_q3", "onepager_q4"):
                    conn.execute(
                        "UPDATE deals SET onepager_edited_at = ? WHERE code_name = ?",
                        (datetime.now(timezone.utc).isoformat(), code),
                    )
                conn.commit()
            resp = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        def log_message(self, fmt, *args) -> None:
            pass  # suppress noisy logs

    server = http.server.ThreadingHTTPServer(("localhost", port), Handler)
    url = f"http://localhost:{port}"
    print(f"DEALROOM dashboard at {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
