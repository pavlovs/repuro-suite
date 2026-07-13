"""DEALROOM v2 — deal workspace: the full v1 deal view over the v2 DB.

Same porting rule as the portfolio (Screen 1): the v1 template + section JS
are the golden reference and are served VERBATIM via src.dashboard's own
builders — only the connection changed to the v2 one-truth DB. This brings
the complete IC workspace (answer-first bar, financials, model, CDD, thesis,
customers/suppliers, RFI, deal history, one-pager) onto v2 data.

v2 dropped two v1 tables the deal builder reads; both are bridged with TEMP
views on the server connection:
- deal_documents → view over deal_artifacts (absorbed there at migration)
- deal_notes     → empty view (the v1 table had 0 rows — never adopted)
"""

from fastapi import Body, Depends, HTTPException

from src.dashboard import (  # noqa: F401  (re-exported for ui_portfolio)
    _build_html,
    _build_unified_financials,
    build_deal_data,
)
from v2 import db

# Mirrors of the field sets defined inside src.dashboard.serve_dashboard
# (local scope there — not importable).
ONEPAGER_SAVE_FIELDS = {
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
    "pnl_row_comments",
    "proj_topline_growth_pct",
    "proj_gm_pct",
    "proj_ebitda_margin_pct",
}
DD_CARD_FIELDS = {
    "bm_segments_comment",
    "bm_margin_comment",
    "bm_revquality_comment",
    "bm_tieout_comment",
    "bm_description",
    "thesis_scorecard_comment",
    "thesis_swot_comment",
    "thesis_rationale",
}

_K_NUMBER_FIELDS = {
    "bp_2026_rev_k",
    "bp_2026_ebitda_k",
    "maxeo_2026_ebitda_k",
    "proj_topline_growth_pct",
    "proj_gm_pct",
    "proj_ebitda_margin_pct",
}
_APPROVED_FIELDS = {
    "onepager_q1_approved",
    "onepager_q3_approved",
    "onepager_q4_approved",
}


def ensure_compat_views(conn) -> None:
    """TEMP views bridging the two v1 tables killed in the v2 schema."""
    conn.execute(
        "CREATE TEMP VIEW IF NOT EXISTS deal_documents AS "
        "SELECT code_name, file_name, artifact_type AS doc_type, "
        "       artifact_subtype AS doc_subtype, fiscal_year, registered_at "
        "FROM deal_artifacts"
    )
    conn.execute(
        "CREATE TEMP VIEW IF NOT EXISTS deal_notes "
        "(domain, note, author, created_at) AS "
        "SELECT NULL, NULL, NULL, NULL WHERE 0"
    )
    # v1 build_deal_data reads deals.last_contact_at (dropped in v2 — it was
    # NULL on all 14 v1 deals; the live signal is freshness activity decay).
    # Reintroduced as a NULL read-compat column, never written.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(deals)")}
    if "last_contact_at" not in cols:
        conn.execute("ALTER TABLE deals ADD COLUMN last_contact_at TEXT")
        conn.commit()


def deal_page(conn, code: str, sandbox: bool) -> str | None:
    """Render the v1 deal workspace for one deal; None if the deal is unknown."""
    ensure_compat_views(conn)
    try:
        data = build_deal_data(conn, code)
    except ValueError:
        return None
    return _build_html(data, serve_mode=True)


def deal_data(conn, code: str) -> dict | None:
    ensure_compat_views(conn)
    try:
        return build_deal_data(conn, code)
    except ValueError:
        return None


def cast_update_value(field: str, value):
    """v1 do_POST casts for the deal-view save fields (verbatim semantics)."""
    if field in _K_NUMBER_FIELDS:
        try:
            if value not in (None, "", "—", "-", "–"):
                s = str(value).strip().replace("(", "-").replace(")", "")
                s = s.replace(".", "").replace(",", ".")
                return float(s)
            return None
        except (TypeError, ValueError):
            return None
    if field in _APPROVED_FIELDS:
        return 1 if value else 0
    return value


def register(app, conn_fn, principal_dep) -> None:
    """Deal-view data APIs the v1 section JS fetches (mirror of v1 do_GET/do_POST)."""

    @app.get("/api/financials")
    def api_financials(
        deal: str, entity: str = "consolidated", p=Depends(principal_dep)
    ):
        c = conn_fn()
        row = c.execute(
            "SELECT * FROM deals WHERE code_name = ? COLLATE NOCASE", (deal,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "deal not found")
        domain = row["domain"] or row["code_name"].lower()
        ensure_compat_views(c)
        return _build_unified_financials(c, domain, entity=entity)

    def _model_ctx(c, deal: str, scenario: str):
        from src.valuation import build_model_context

        row = c.execute(
            "SELECT domain, code_name FROM deals WHERE code_name = ? COLLATE NOCASE",
            (deal,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "deal not found")
        domain = row["domain"] or row["code_name"].lower()
        return build_model_context(c, domain, scenario)

    @app.get("/api/model-context")
    def api_model_context_get(
        deal: str, scenario: str = "base", p=Depends(principal_dep)
    ):
        return _model_ctx(conn_fn(), deal, scenario)

    @app.post("/api/model-context")
    def api_model_context_post(payload: dict = Body(...), p=Depends(principal_dep)):
        from src.valuation import build_model_context

        domain = payload.get("domain", "")
        if not domain:
            raise HTTPException(400, "domain required")
        return build_model_context(conn_fn(), domain, payload.get("scenario", "base"))

    @app.post("/api/model-params")
    def api_model_params(payload: dict = Body(...), p=Depends(principal_dep)):
        from src.valuation import build_model_context, save_model_params

        domain = payload.get("domain", "")
        if not domain:
            raise HTTPException(400, "domain required")
        scenario = payload.get("scenario", "base")
        c = conn_fn()
        with db.WRITE_LOCK:
            save_model_params(c, domain, payload.get("params", {}), scenario)
        return build_model_context(c, domain, scenario)

    def _tier_op(payload: dict, remove: bool):
        from src.valuation import (
            build_model_context,
            load_model_params,
            save_model_params,
        )

        domain = payload.get("domain", "")
        if not domain:
            raise HTTPException(400, "domain required")
        scenario = payload.get("scenario", "base")
        c = conn_fn()
        with db.WRITE_LOCK:
            import json as _json

            params = load_model_params(c, domain, scenario) or {}
            tiers = params.get("earnout_tiers_json", [])
            if isinstance(tiers, str):
                tiers = _json.loads(tiers)
            tiers = list(tiers or [])
            if remove:
                index = payload.get("index", -1)
                if tiers and 0 <= index < len(tiers):
                    tiers.pop(index)
                elif tiers:
                    tiers.pop()
            else:
                tiers.append(tiers[-1] if tiers else 0)
            params["earnout_tiers_json"] = tiers
            save_model_params(c, domain, params, scenario)
        return build_model_context(c, domain, scenario)

    @app.post("/api/model-add-tier")
    def api_model_add_tier(payload: dict = Body(...), p=Depends(principal_dep)):
        return _tier_op(payload, remove=False)

    @app.post("/api/model-remove-tier")
    def api_model_remove_tier(payload: dict = Body(...), p=Depends(principal_dep)):
        return _tier_op(payload, remove=True)
