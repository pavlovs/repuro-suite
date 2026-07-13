"""DEALROOM v2 — Screen 1: Portfolio View, ported 1:1 from v1.

The v1 dashboard (src/templates/dashboard.html + sections/*.js) is the
approved golden reference; v2's reinterpretation was rejected 13.07.
This module serves the v1 template VERBATIM (read from src/templates/ —
single source, no copy drift) fed from the v2 DB. Data shape and API
contract mirror src/dashboard.py exactly so the template works unchanged.

Deal pages are rebuilt screen-by-screen with sign-off per screen; until
Screen 2 ships, deal links land on a minimal placeholder page.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, HTTPException
from fastapi.responses import HTMLResponse

from v2 import db, repo

V1_TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "templates"

# Mirror of src/dashboard.py — fields the portfolio UI may write via api/update.
PORTFOLIO_SAVE_FIELDS = {
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
}

_FLOAT_FIELDS = {
    "rev_m_override",
    "ebitda_m_override",
    "ev_m_override",
    "multiple_override",
}

# Mirror of src/dashboard.py _STAGE_STATUS (default status_text per stage).
STAGE_STATUS = {
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


def _domain_for(deal_row) -> str:
    return deal_row["domain"] or deal_row["code_name"].lower()


def _portfolio_meta(conn, key: str) -> str:
    row = conn.execute(
        "SELECT value FROM portfolio_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row and row["value"] else ""


def _save_portfolio_meta(conn, key: str, text: str) -> None:
    with db.WRITE_LOCK:
        conn.execute(
            "INSERT INTO portfolio_meta (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at",
            (key, text, db.now_iso()),
        )
        conn.commit()


def build_portfolio_data(conn) -> dict[str, Any]:
    """Port of src/dashboard.py build_portfolio_data against the v2 DB."""
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

        # Revenue + EBITDA — prefer model (adjusted) data; headline year =
        # latest ACTUAL year (non-zero revenue) so an empty forward plan
        # column cannot blank out the headline.
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
        # EBITDA must match the headline revenue year so the margin is coherent.
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

        # Valuation: EV incl. EO + multiple — deal_valuations, then bewertung.
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

        # Employees from ALLEX (attached as 'allex'; absent in some sandboxes).
        employees_allex = None
        try:
            allex_row = conn.execute(
                "SELECT ma_count FROM allex.company_records WHERE domain = ? LIMIT 1",
                (domain,),
            ).fetchone()
            employees_allex = allex_row["ma_count"] if allex_row else None
        except Exception:
            pass

        # Manual overrides win over computed values.
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
            else STAGE_STATUS.get(d["deal_stage"], d["deal_stage"])
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
        "portfolio_pipeline_comments": _portfolio_meta(
            conn, "portfolio_pipeline_comments"
        ),
        "portfolio_comments": _portfolio_meta(conn, "portfolio_comments"),
    }


def _build_html(data: dict, sandbox: bool) -> str:
    """Mirror of src/dashboard.py _build_html — v1 template served verbatim."""
    template = (V1_TEMPLATES / "dashboard.html").read_text(encoding="utf-8")
    html = template.replace(
        "__DATA_JSON__", json.dumps(data, ensure_ascii=False, default=str)
    )
    html = html.replace("__SERVE_MODE_JS__", "true")
    html = html.replace("__INVESTOR_MODE_JS__", "false")
    html = html.replace("__WATERMARK_LABEL__", json.dumps(""))
    html = html.replace("__LIVE_BADGE__", "LIVE")
    date_str = datetime.now().strftime("%Y-%m-%d") + (" · Sandbox" if sandbox else "")
    html = html.replace("__DATE_STR__", date_str)
    sections_js = ""
    sections_dir = V1_TEMPLATES / "sections"
    for js_file in sorted(sections_dir.glob("*.js")):
        sections_js += js_file.read_text(encoding="utf-8") + "\n"
    return html.replace("__SECTIONS_JS__", sections_js)


_DEAL_PLACEHOLDER = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Dealroom — Repuro</title>
<style>body{{font-family:'Inter',-apple-system,'Segoe UI',sans-serif;background:#f0f2f5;
color:#111827;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:28px 36px;max-width:420px}}
h1{{font-size:16px;margin:0 0 8px}} p{{font-size:13px;color:#6b7280;margin:0 0 16px}}
a{{color:#0891B2;font-size:13px;text-decoration:none}} a:hover{{text-decoration:underline}}</style>
</head><body><div class="card"><h1>{code}</h1>
<p>The deal workspace is being rebuilt and will be back shortly.</p>
<a href="./">&larr; Back to portfolio</a></div></body></html>"""


def register(app, conn_fn, principal_dep) -> None:
    @app.get("/", response_class=HTMLResponse)
    def index(deal: str | None = None, p=Depends(principal_dep)):
        if deal:
            return HTMLResponse(_DEAL_PLACEHOLDER.format(code=deal))
        data = build_portfolio_data(conn_fn())
        return HTMLResponse(_build_html(data, sandbox=p.get("sandbox", True)))

    @app.get("/api/data")
    def api_data(deal: str | None = None, p=Depends(principal_dep)):
        # Template refetches on load; portfolio payload regardless of ?deal=.
        return build_portfolio_data(conn_fn())

    @app.post("/api/update")
    def api_update(payload: dict = Body(...), p=Depends(principal_dep)):
        code = (payload.get("code_name") or "").strip()
        field = (payload.get("field") or "").strip()
        value = payload.get("value")
        if not code or field not in PORTFOLIO_SAVE_FIELDS:
            raise HTTPException(400, "invalid code_name or field")
        c = conn_fn()
        d = repo.get_deal(c, code)
        if not d:
            raise HTTPException(404, f"unknown deal {code!r}")

        if field in _FLOAT_FIELDS:
            try:
                value = float(value) if value not in (None, "", "—", "-") else None
            except (TypeError, ValueError):
                value = None
        elif field == "employees_override":
            try:
                value = int(value) if value not in (None, "", "—", "-") else None
            except (TypeError, ValueError):
                value = None

        if field == "deal_stage":
            if value not in repo.STAGE_LABELS:
                raise HTTPException(422, f"invalid stage {value!r}")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with db.WRITE_LOCK:
                c.execute(
                    "UPDATE deals SET deal_stage = ?, stage_entered_at = ? "
                    "WHERE code_name = ?",
                    (value, now, d["code_name"]),
                )
                c.execute(
                    "INSERT INTO deal_stage_history "
                    "(domain, code_name, from_stage, to_stage, changed_at, "
                    " changed_by, evidence) VALUES (?,?,?,?,?,?,?)",
                    (
                        d["domain"],
                        d["code_name"],
                        d["deal_stage"],
                        value,
                        db.now_iso(),
                        p["user"],
                        "portfolio stage dropdown",
                    ),
                )
                c.commit()
            return {"ok": True}

        with db.WRITE_LOCK:
            c.execute(
                f"UPDATE deals SET {field} = ? WHERE code_name = ?",
                (value, d["code_name"]),
            )
            c.commit()
        return {"ok": True}

    @app.post("/api/portfolio-comments")
    def api_portfolio_comments(payload: dict = Body(...), p=Depends(principal_dep)):
        key = payload.get("key", "portfolio_comments")
        if key in ("portfolio_comments", "portfolio_pipeline_comments"):
            _save_portfolio_meta(conn_fn(), key, payload.get("value", ""))
        return {"ok": True}
