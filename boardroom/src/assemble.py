"""Auto-assembly of draft publication bodies from read-only source DBs.

assemble_weekly_update() → §4.1 body dict
assemble_board_pack()    → §4.2 body dict

ALL foreign DB access goes through db.open_readonly().
SENSITIVE columns (seller_*, investment_thesis, notes, company_name pre-LOI)
are NEVER emitted.
"""

from . import db as _db
from .sources import cockpit_db, dealroom_db, pipeline_db

# ---------------------------------------------------------------------------
# Pre-LOI stages shown in anonymized funnel
_FUNNEL_STAGES = ("valuation_rfi", "indicative_offer")

# Post-LOI stages with real names
_LIVE_STAGES = ("loi_signed", "due_diligence", "contract_negotiation", "closed")

# Pipeline batch exclusions
_BATCH_EXCLUDE = {"testbatch"}

# Reply statuses for batch conversion calc
_REPLY_STATUSES = {
    "contact",
    "financials",
    "meeting",
    "declined",
    "followup1",
    "followup2",
}


# ---------------------------------------------------------------------------
def _size_band(ebitda_m) -> str:
    """Bucket ebitda_m_override into a display band. None → 'n/a'."""
    if ebitda_m is None:
        return "n/a"
    try:
        v = float(ebitda_m)
    except (TypeError, ValueError):
        return "n/a"
    if v < 1.0:
        return "<€1M"
    elif v < 3.0:
        return "€1–3M"
    elif v < 5.0:
        return "€3–5M"
    else:
        return "€5M+"


# ---------------------------------------------------------------------------
def _pull_funnel(conn) -> list[dict]:
    """Anonymized top-of-funnel deals. Never emits company_name or sensitive cols."""
    rows = conn.execute(
        "SELECT code_name, deal_stage, sector, location, ebitda_m_override, strategic_fit "
        "FROM deals "
        "WHERE deal_stage IN ('valuation_rfi','indicative_offer')",
    ).fetchall()
    result = []
    for r in rows:
        result.append(
            {
                "codename": r[0],
                "stage": r[1],
                "sector": r[2],
                "region": r[3],
                "size_band": _size_band(r[4]),
                "strategic_fit": r[5],
            }
        )
    return result


def _pull_batches(conn) -> list[dict]:
    """Per-briefaktion outreach aggregate. Excludes NULL, testbatch, *TEST*."""
    rows = conn.execute(
        "SELECT briefaktion, outreach_sent_at, outreach_status "
        "FROM company_records "
        "WHERE briefaktion IS NOT NULL",
    ).fetchall()

    # Aggregate in Python so we can apply exclusion logic cleanly
    batches: dict[str, dict] = {}
    for ba, sent_at, status in rows:
        if not isinstance(ba, str):  # defend against non-string junk in the column
            continue
        # Exclude testbatch (case-insensitive TEST check)
        if ba in _BATCH_EXCLUDE or "TEST" in ba.upper():
            continue
        if ba not in batches:
            batches[ba] = {"sent": 0, "replies": 0, "meetings": 0}
        if sent_at is not None:
            batches[ba]["sent"] += 1
        if status in _REPLY_STATUSES:
            batches[ba]["replies"] += 1
        if status == "meeting":
            batches[ba]["meetings"] += 1

    result = []
    for ba, counts in sorted(batches.items()):
        sent = counts["sent"]
        meetings = counts["meetings"]
        conv_pct = round(100 * meetings / sent, 1) if sent else 0.0
        result.append(
            {
                # key is "batch" to match the read-view BatchStats component
                "batch": ba,
                "sent": sent,
                "replies": counts["replies"],
                "meetings": meetings,
                "conv_pct": conv_pct,
            }
        )
    return result


def _pull_live_deals(conn) -> list[dict]:
    """Post-LOI deals with real company names allowed."""
    rows = conn.execute(
        "SELECT company_name, code_name, deal_stage, "
        "rev_m_override, ebitda_m_override, ev_m_override, multiple_override "
        "FROM deals "
        "WHERE deal_stage IN ('loi_signed','due_diligence','contract_negotiation','closed')",
    ).fetchall()
    result = []
    for r in rows:
        # EXACTLY the §4.1 live_deals contract — no extra raw DB fields. The body IS the
        # investor allowlist (/api/published returns it whole), so internal columns like
        # status_override / ev_m_note / description must NOT appear here.
        result.append(
            {
                "name": r[0],
                "codename": r[1],
                "stage": r[2],
                "rev_m": r[3],
                "ebitda_m": r[4],
                "ev_m": r[5],
                "multiple": r[6],
                # Authored fields — not in DB; left empty for M3 admin to fill
                "earnout": "",
                "dd_status": "",
                "close_target": "",
                "commentary": "",
            }
        )
    return result


def _pull_milestones(conn) -> dict:
    """Cockpit deliverables: done + upcoming (open with date). NULL target_date is safe."""
    done_rows = conn.execute(
        "SELECT name, target_date, comment FROM deliverables WHERE status='done'",
    ).fetchall()
    next_rows = conn.execute(
        "SELECT name, target_date FROM deliverables "
        "WHERE status='open' AND target_date IS NOT NULL "
        "ORDER BY target_date",
    ).fetchall()

    # Exact read-view contract: done = {name, date, comment} (UI reads m.date), next = {name, target_date}.
    # No extra keys (e.g. cockpit 'deal') — the published body is the investor allowlist.
    done = [{"name": r[0], "date": r[1], "comment": r[2]} for r in done_rows]
    nxt = [{"name": r[0], "target_date": r[1]} for r in next_rows]

    return {
        "milestones_done": done,
        "milestones_next": nxt,
        # Authored fields — left empty for M3 admin (fundraising is an OBJECT, per §4.1 + read view)
        "narrative": "",
        "fundraising": {"tax_structure": "", "sources_uses": [], "capital_plan": ""},
    }


# ---------------------------------------------------------------------------
def assemble_weekly_update() -> dict:
    """Build a §4.1 weekly-update draft body from the live read-only source DBs.

    Every data block is stamped with its source filename and the UTC time of pull.
    Authored sections are left as empty strings for the admin to fill (M3).
    """
    now = _db.now_iso()

    dr_path = dealroom_db()
    pl_path = pipeline_db()
    ck_path = cockpit_db()

    dr_conn = _db.open_readonly(dr_path)
    pl_conn = _db.open_readonly(pl_path)
    ck_conn = _db.open_readonly(ck_path)

    try:
        funnel = _pull_funnel(dr_conn)
        batches = _pull_batches(pl_conn)
        live_deals = _pull_live_deals(dr_conn)
        project_update = _pull_milestones(ck_conn)
    finally:
        dr_conn.close()
        pl_conn.close()
        ck_conn.close()

    # Shape matches DESIGN-SPEC §4.1 AND the M1 read view (app.jsx): funnel.items,
    # batches.rows, live_deals as a bare array, fundraising as an object, top-level
    # stamps keyed by field-path. Do not diverge — a published draft must render.
    return {
        "pipeline": {
            "funnel": {"items": funnel},
            "batches": {"rows": batches},
        },
        "live_deals": live_deals,
        "project_update": project_update,
        "stamps": {
            "pipeline.funnel": {"source": dr_path.name, "as_of": now},
            "pipeline.batches": {"source": pl_path.name, "as_of": now},
            "live_deals": {"source": dr_path.name, "as_of": now},
            "project_update.milestones": {"source": ck_path.name, "as_of": now},
        },
    }


def assemble_board_pack() -> dict:
    """Build a §4.2 board-pack draft body.

    Authored sections (meeting, agenda, decisions, pre_read, minutes) are left empty.
    KPIs are computed from live DBs and stamped.
    """
    now = _db.now_iso()

    dr_path = dealroom_db()
    pl_path = pipeline_db()

    dr_conn = _db.open_readonly(dr_path)
    pl_conn = _db.open_readonly(pl_path)

    try:
        # KPI: active pipeline count (pre-LOI)
        active_pipeline = dr_conn.execute(
            "SELECT COUNT(*) FROM deals WHERE deal_stage IN ('valuation_rfi','indicative_offer')"
        ).fetchone()[0]

        # KPI: live deals (post-LOI)
        live_deal_count = dr_conn.execute(
            "SELECT COUNT(*) FROM deals WHERE deal_stage IN ('loi_signed','due_diligence','contract_negotiation','closed')"
        ).fetchone()[0]

        # KPI: combined EV in DD (post-LOI)
        ev_row = dr_conn.execute(
            "SELECT SUM(ev_m_override) FROM deals WHERE deal_stage IN ('loi_signed','due_diligence','contract_negotiation','closed')"
        ).fetchone()
        combined_ev_m = ev_row[0]  # may be None if no rows or all NULL

        # KPI: batch outreach total sent
        total_sent_row = pl_conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE outreach_sent_at IS NOT NULL"
        ).fetchone()
        total_sent = total_sent_row[0]

    finally:
        dr_conn.close()
        pl_conn.close()

    # KPI keys (metric/value/prior/as_of) match the read-view BoardTab. prior is None
    # until we have prior-week data to diff against (M3+).
    kpis = [
        {
            "metric": "Active pipeline (deals)",
            "value": active_pipeline,
            "prior": None,
            "as_of": now,
        },
        {
            "metric": "Live deals (post-LOI)",
            "value": live_deal_count,
            "prior": None,
            "as_of": now,
        },
        {
            "metric": "Combined EV in DD (€M)",
            "value": combined_ev_m,
            "prior": None,
            "as_of": now,
        },
        {
            "metric": "Batch outreach (total sent)",
            "value": total_sent,
            "prior": None,
            "as_of": now,
        },
    ]

    return {
        # Authored sections — empty for M3 admin to fill
        "meeting": {"date": "", "location": "", "attendees": []},
        "agenda": [],
        "decisions": [],
        "pre_read": [],
        "minutes": "",
        # Computed
        "kpis": kpis,
        "stamps": {
            "kpis": {"source": f"{dr_path.name}+{pl_path.name}", "as_of": now},
        },
    }
