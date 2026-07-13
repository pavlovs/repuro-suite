"""DEALROOM v2 — suite tie-in (read-only): Cockpit execution + Investor visibility.

The deal page is the single answer surface, so it must show where the deal
stands in the OTHER suite modules too:
- Cockpit (PM master): open deliverables + tasks for this deal, and what's
  waiting on whom. dealroom NEVER writes cockpit — read-only, like boardroom.
- Investor Room (boardroom): whether this deal surfaces to Strada, and how
  (named live deal post-LOI vs anonymised funnel pre-LOI) — computed with the
  SAME stage buckets boardroom uses, so the two never disagree.

All failures degrade to "tie unavailable" — a missing cockpit.db must never
break the deal page (boardroom precedent: stale-tolerant foreign reads).
"""

from datetime import date, datetime, timezone

from v2 import db

# boardroom stage buckets (boardroom/src/assemble.py) — keep in lockstep
INVESTOR_LIVE_STAGES = {"loi_signed", "due_diligence", "contract_negotiation", "closed"}
INVESTOR_FUNNEL_STAGES = {"valuation_rfi", "indicative_offer"}

COCKPIT_BASE = "/cockpit"
INVESTOR_BASE = "/investor"


def _days_until(iso):
    try:
        return (
            date.fromisoformat(str(iso)[:10]) - datetime.now(timezone.utc).date()
        ).days
    except (ValueError, TypeError):
        return None


def cockpit_execution(code: str) -> dict | None:
    """Open deliverables + tasks for a deal from cockpit.db (read-only).
    Returns None when cockpit is unreachable (tie simply not shown)."""
    path = db.cockpit_db_path()
    if not path:
        return None
    try:
        conn = db.open_readonly(path)
    except Exception:
        return None
    try:
        ws = conn.execute(
            "SELECT id, name, status, objective FROM workstreams "
            "WHERE lower(deal_codename)=lower(?) LIMIT 1",
            (code,),
        ).fetchone()
        if not ws:
            return {"linked": False}

        deliverables = [
            dict(r)
            for r in conn.execute(
                "SELECT name, status, target_date, comment FROM deliverables "
                "WHERE workstream_id=? ORDER BY status='done', "
                "target_date IS NULL, target_date",
                (ws["id"],),
            )
        ]
        open_delivs = [d for d in deliverables if d["status"] == "open"]
        done_delivs = [d for d in deliverables if d["status"] == "done"]
        next_deliv = next((d for d in open_delivs if d["target_date"]), None)

        # open tasks, waiting-on flagged first
        tasks = [
            dict(r)
            for r in conn.execute(
                "SELECT t.text, t.status, t.deadline, t.waiting_on_party, "
                " t.waiting_on_type, t.responsible, t.pinned_today "
                "FROM tasks t JOIN deliverables d ON d.id=t.deliverable_id "
                "WHERE d.workstream_id=? AND t.status NOT IN ('done','cancelled') "
                "ORDER BY t.waiting_on_party IS NULL, t.pinned_today DESC, "
                "t.deadline IS NULL, t.deadline",
                (ws["id"],),
            )
        ]
        waiting = [t for t in tasks if t["waiting_on_party"]]
        for t in tasks:
            t["days_to_deadline"] = _days_until(t["deadline"])

        return {
            "linked": True,
            "workstream": dict(ws),
            "url": f"{COCKPIT_BASE}/",
            "deliverables_open": open_delivs,
            "deliverables_done": len(done_delivs),
            "deliverables_total": len(deliverables),
            "next_deliverable": next_deliv,
            "tasks_open": tasks,
            "waiting": waiting,
        }
    finally:
        conn.close()


def investor_visibility(deal_row) -> dict:
    """How this deal appears in the Investor Room — computed with boardroom's
    own stage buckets so the surfaces never contradict each other."""
    stage = deal_row["deal_stage"]
    if stage in INVESTOR_LIVE_STAGES:
        return {
            "visible": True,
            "mode": "named",
            "label": "Live-Deal (namentlich im Board-Pack)",
            "detail": "Post-LOI — erscheint mit Firmennamen in Weekly-Update + "
            "Board-Pack des Investor Room.",
            "url": f"{INVESTOR_BASE}/",
        }
    if stage in INVESTOR_FUNNEL_STAGES:
        return {
            "visible": True,
            "mode": "anonymised",
            "label": "Pipeline (anonymisiert)",
            "detail": "Pre-LOI — nur anonymisiert im Funnel (Sektor/Region/"
            "Größenband), kein Firmenname.",
            "url": f"{INVESTOR_BASE}/",
        }
    return {
        "visible": False,
        "mode": "none",
        "label": "Nicht im Investor Room",
        "detail": f"Stage '{stage}' — weder Live-Deal noch aktiver Funnel.",
        "url": None,
    }
