"""DEALROOM v2 — CDD workspace (M4) + negotiation/stakeholder payloads (M5).

CDD scope split (spec §6): data-room sections 01–04 = CDD (Repuro/Claude),
05–07 = FDD/TDD/LDD lane (Ebner Stolz), 00 = Datenanfrage/QA, 08 = Betrieb/IT.
"""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from v2 import repo

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"

SECTION_LANES = {
    "00": ("Datenanfrage & QA", "QA"),
    "01": ("Umsatz und Kunden", "CDD"),
    "02": ("Lieferanten", "CDD"),
    "03": ("Personal", "CDD"),
    "04": ("Finanzen", "CDD"),
    "05": ("Versicherungen", "FDD"),
    "06": ("Steuern", "FDD"),
    "07": ("Rechtlich & Gesellschaftsverfassung", "FDD"),
    "08": ("Betriebsausstattung & IT", "TDD"),
}


def _today():
    return datetime.now(timezone.utc).date()


def _days_since(iso):
    try:
        return (_today() - date.fromisoformat(str(iso)[:10])).days
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- M4: CDD ---


def cdd_payload(conn, code):
    d = repo.get_deal(conn, code)
    if not d:
        return None
    code = d["code_name"]
    domain = d["domain"]

    # data-room health: latest scan per section
    dataroom = []
    for r in conn.execute(
        "SELECT s.* FROM dataroom_scans s WHERE s.code_name=? AND s.id = "
        " (SELECT MAX(id) FROM dataroom_scans b WHERE b.code_name=s.code_name "
        "  AND b.section=s.section) ORDER BY s.section",
        (code,),
    ):
        delta = {}
        try:
            delta = json.loads(r["delta_json"] or "{}")
        except json.JSONDecodeError:
            pass
        name, lane = SECTION_LANES.get(
            r["section"], (r["section_name"] or r["section"], "CDD")
        )
        dataroom.append(
            {
                "section": r["section"],
                "name": r["section_name"] or name,
                "lane": lane,
                "scanned_at": r["scanned_at"],
                "file_count": r["file_count"],
                "newest_file_date": r["newest_file_date"],
                "newest_file_name": r["newest_file_name"],
                "delta_added": len(delta.get("added", [])),
                "delta_changed": len(delta.get("changed", [])),
                "delta_removed": len(delta.get("removed", [])),
            }
        )

    # registries: every version of the DD artifact families
    registries = {}
    for atype in ("databook", "rfi", "slides"):
        rows = [
            dict(a)
            for a in conn.execute(
                "SELECT id, file_name, file_date, version, status, checks_json, "
                " registered_at FROM deal_artifacts "
                "WHERE code_name=? AND artifact_type=? "
                "ORDER BY COALESCE(file_date,'0') DESC, COALESCE(version,0) DESC",
                (code, atype),
            )
        ]
        for r in rows:
            try:
                r["checks"] = json.loads(r["checks_json"] or "{}")
            except json.JSONDecodeError:
                r["checks"] = {}
        registries[atype] = rows

    # RFI mirror stats
    rfi_rows = (
        [
            dict(q)
            for q in conn.execute(
                "SELECT question, category, importance, status, sent_at, answered_at "
                "FROM deal_questions WHERE domain=? "
                "ORDER BY CASE importance WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
                "ELSE 2 END, sort_order",
                (domain,),
            )
        ]
        if domain
        else []
    )
    for q in rfi_rows:
        q["days_outstanding"] = (
            _days_since(q["sent_at"])
            if q["status"] == "sent" and q["sent_at"]
            else None
        )
    by_status, by_priority = {}, {}
    for q in rfi_rows:
        by_status[q["status"]] = by_status.get(q["status"], 0) + 1
        by_priority[q["importance"]] = by_priority.get(q["importance"], 0) + 1
    rfi_source = conn.execute(
        "SELECT file_name, file_date FROM deal_artifacts WHERE code_name=? "
        "AND artifact_type='rfi' AND status IN ('current','final') "
        "ORDER BY COALESCE(file_date,'0') DESC LIMIT 1",
        (code,),
    ).fetchone()

    red_flags = (
        [
            dict(r)
            for r in conn.execute(
                "SELECT category, subcategory, description, risk_level, risk_note, "
                " status, advisor, datenanfrage_ref FROM deal_dd_items WHERE domain=? "
                "ORDER BY CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
                "WHEN 'low' THEN 2 ELSE 3 END, category",
                (domain,),
            )
        ]
        if domain
        else []
    )

    milestones = [
        dict(m)
        for m in conn.execute(
            "SELECT * FROM deal_milestones WHERE code_name=? "
            "ORDER BY due_date IS NULL, due_date",
            (code,),
        )
    ]

    return {
        "deal": dict(d),
        "stage_label": repo.STAGE_LABELS.get(d["deal_stage"], d["deal_stage"]),
        "dataroom": dataroom,
        "registries": registries,
        "rfi": {
            "rows": rfi_rows,
            "by_status": by_status,
            "by_priority": by_priority,
            "source": dict(rfi_source) if rfi_source else None,
        },
        "red_flags": red_flags,
        "milestones": milestones,
    }


# -------------------------------------------------------- M5: negotiation ---


def negotiation_payload(conn, code):
    """Owner-only. Absorbs negotiation-tool M3 (spec §7)."""
    d = repo.get_deal(conn, code)
    if not d or not d["domain"]:
        return None
    strategy = conn.execute(
        "SELECT s.*, st.name AS stakeholder_name, st.company AS stakeholder_company "
        "FROM negotiation_strategies s JOIN stakeholders st ON st.id=s.stakeholder_id "
        "WHERE s.deal_domain=? ORDER BY CASE s.status WHEN 'active' THEN 0 "
        "WHEN 'executing' THEN 1 ELSE 2 END, s.id DESC LIMIT 1",
        (d["domain"],),
    ).fetchone()
    if not strategy:
        return {
            "deal": dict(d),
            "stage_label": repo.STAGE_LABELS.get(d["deal_stage"], d["deal_stage"]),
            "strategy": None,
        }
    sid = strategy["id"]

    # rounds = the DEAL's full history across memo versions (a new strategy
    # supersedes the memo, not the round record)
    rounds = [
        dict(r)
        for r in conn.execute(
            "SELECT r.*, rv.went_well, rv.went_wrong, rv.lesson, rv.self_rating "
            "FROM negotiation_rounds r "
            "JOIN negotiation_strategies s2 ON s2.id = r.strategy_id "
            "LEFT JOIN negotiation_round_reviews rv ON rv.round_id = r.id "
            "WHERE s2.deal_domain=? ORDER BY r.date DESC, r.round_no DESC",
            (d["domain"],),
        )
    ]
    predictions = [
        dict(p)
        for p in conn.execute(
            "SELECT objection, tag, counter, occurred, resolved_at "
            "FROM negotiation_predictions WHERE strategy_id=? "
            "ORDER BY occurred IS NOT NULL, id",
            (sid,),
        )
    ]
    # SELBST-CHECK: open lessons referencing this deal (weakness drills first)
    lessons = [
        dict(le)
        for le in conn.execute(
            "SELECT polarity, rule_ref, pattern, drill, occurrences, status "
            "FROM negotiation_lessons WHERE status IN ('open','watching','recurred') "
            "AND (deal_refs LIKE ? OR deal_refs IS NULL) "
            "ORDER BY CASE polarity WHEN 'weakness' THEN 0 ELSE 1 END, id",
            (f"%{d['code_name']}%",),
        )
    ]
    locked_terms = [
        {**dict(t), "display": repo.term_display(t, exact=True)}
        for t in conn.execute(
            "SELECT * FROM deal_terms WHERE code_name=? "
            "AND status IN ('locked','agreed') ORDER BY status, id",
            (d["code_name"],),
        )
    ]
    positions = [
        dict(r)
        for r in conn.execute(
            "SELECT term, preferred, fallback, walk_away, escalation_required, "
            " roman_confirmed, status, their_position, prio "
            "FROM negotiation_positions "
            "WHERE strategy_id=? ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, "
            "CASE prio WHEN 'high' THEN 0 WHEN 'med' THEN 1 WHEN 'low' THEN 2 "
            "ELSE 3 END, id",
            (sid,),
        )
    ]
    open_items = [
        dict(r)
        for r in conn.execute(
            "SELECT item, owner, due, status, resolution FROM negotiation_open_items "
            "WHERE strategy_id=? ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, "
            "due IS NULL, due",
            (sid,),
        )
    ]
    neg_milestones = [
        dict(r)
        for r in conn.execute(
            "SELECT date, label, side, consequence, status "
            "FROM negotiation_milestones WHERE strategy_id=? ORDER BY date",
            (sid,),
        )
    ]
    parties = [
        dict(r)
        for r in conn.execute(
            "SELECT p.role, p.notes, st.id AS stakeholder_id, st.name "
            "FROM strategy_parties p JOIN stakeholders st ON st.id=p.stakeholder_id "
            "WHERE p.strategy_id=? ORDER BY CASE p.role WHEN 'primary' THEN 0 "
            "ELSE 1 END",
            (sid,),
        )
    ]
    trail = conn.execute(
        "SELECT COUNT(*) n, SUM(read_status='read') n_read "
        "FROM communication_trail WHERE stakeholder_id=?",
        (strategy["stakeholder_id"],),
    ).fetchone()

    # bucket-based offer history — deal-wide across strategy generations
    # (a superseded strategy keeps its offer events, like rounds)
    offers = []
    for o in conn.execute(
        "SELECT o.* FROM negotiation_offers o "
        "JOIN negotiation_strategies s3 ON s3.id=o.strategy_id "
        "WHERE s3.deal_domain=? ORDER BY o.date, o.id",
        (d["domain"],),
    ):
        terms = [
            dict(t)
            for t in conn.execute(
                "SELECT term_key, label, value_num, unit, value_text, note "
                "FROM negotiation_offer_terms WHERE offer_id=? ORDER BY id",
                (o["id"],),
            )
        ]
        offers.append({**dict(o), "terms": terms})

    # freshness: latest agreement-grade package must match the terms ledger
    latest_pkg = next(
        (o for o in reversed(offers) if o["status"] in ("accepted", "signed")), None
    )
    terms_sync = {"checked": False, "mismatches": []}
    if latest_pkg:
        terms_sync["checked"] = True
        cur = {t["term_key"]: t for t in locked_terms}
        for t in latest_pkg["terms"]:
            ct = cur.get(t["term_key"])
            if (
                t["value_num"] is not None
                and ct is not None
                and ct["value_num"] is not None
                and abs(t["value_num"] - ct["value_num"]) > 0.01
            ):
                terms_sync["mismatches"].append(
                    {
                        "term_key": t["term_key"],
                        "offer": t["value_num"],
                        "ledger": ct["value_num"],
                    }
                )

    today = _today().isoformat()
    for m in neg_milestones:
        m["overdue"] = m["status"] == "pending" and m["date"] < today
    for it in open_items:
        it["overdue"] = it["status"] == "open" and bool(it["due"]) and it["due"] < today
    next_milestone = next(
        (m for m in neg_milestones if m["status"] == "pending" and m["date"] >= today),
        None,
    ) or next((m for m in neg_milestones if m["status"] == "pending"), None)

    return {
        "deal": dict(d),
        "stage_label": repo.STAGE_LABELS.get(d["deal_stage"], d["deal_stage"]),
        "strategy": dict(strategy),
        "rounds": rounds,
        "predictions": predictions,
        "lessons": lessons,
        "locked_terms": locked_terms,
        "positions": positions,
        "open_items": open_items,
        "neg_milestones": neg_milestones,
        "next_milestone": next_milestone,
        "parties": parties,
        "offers": offers,
        "terms_sync": terms_sync,
        "trail": {"total": trail["n"] or 0, "read": trail["n_read"] or 0},
        # validator gates deliverable-grade memos; a seeded strategy without a
        # memo — or a superseded/closed one — is honest state, not a FAIL wall
        "validation": (
            validate_strategy(sid)
            if strategy["memo_md"] and strategy["status"] in ("active", "executing")
            else {"ran": False, "passed": None, "skipped": True}
        ),
    }


_VALIDATION_CACHE: dict[int, dict] = {}


def validate_strategy(strategy_id: int) -> dict:
    """Run tools/validate_negotiation.py in-process against the v2 DB.
    FAIL ⇒ the memo is not deliverable-grade (spec §7). Cached per process —
    the validator reads hubspot.db and costs seconds; sandbox data only
    changes on re-migration, which restarts the server anyway."""
    if strategy_id in _VALIDATION_CACHE:
        return _VALIDATION_CACHE[strategy_id]
    try:
        sys.path.insert(0, str(TOOLS_DIR))
        from validate_negotiation import validate  # noqa: PLC0415

        from v2 import db as v2db  # noqa: PLC0415

        findings, warnings, info = validate(strategy_id, str(v2db.default_db_path()))
        result = {
            "ran": True,
            "passed": not findings,
            "findings": findings,
            "warnings": warnings,
        }
    except Exception as exc:  # validator missing/incompatible — degrade honestly
        result = {"ran": False, "passed": None, "error": str(exc)[:300]}
    _VALIDATION_CACHE[strategy_id] = result
    return result


# -------------------------------------------------------- M5: stakeholder ---


def stakeholders_index(conn):
    return [
        dict(r)
        for r in conn.execute(
            "SELECT s.id, s.name, s.company, s.role, "
            " (SELECT GROUP_CONCAT(context_ref, ', ') FROM stakeholder_links l "
            "  WHERE l.stakeholder_id = s.id) AS contexts, "
            " (SELECT COUNT(*) FROM profile_claims pc "
            "  WHERE pc.stakeholder_id = s.id AND pc.status='active') AS n_claims, "
            " (SELECT COUNT(*) FROM negotiation_rounds nr "
            "  WHERE nr.stakeholder_id = s.id) AS n_rounds "
            "FROM stakeholders s ORDER BY s.name"
        )
    ]


def stakeholder_payload(conn, sid: int):
    s = conn.execute("SELECT * FROM stakeholders WHERE id=?", (sid,)).fetchone()
    if not s:
        return None
    links = [
        dict(r)
        for r in conn.execute(
            "SELECT context_type, context_ref, deal_domain, relationship "
            "FROM stakeholder_links WHERE stakeholder_id=?",
            (sid,),
        )
    ]
    claims = [
        dict(r)
        for r in conn.execute(
            "SELECT field, value, confidence, evidence_quote, source_medium, "
            " source_date, status FROM profile_claims WHERE stakeholder_id=? "
            "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, "
            "CASE confidence WHEN 'HIGH' THEN 0 WHEN 'MED' THEN 1 "
            "WHEN 'LOW' THEN 2 ELSE 3 END",
            (sid,),
        )
    ]
    rounds = [
        dict(r)
        for r in conn.execute(
            "SELECT r.round_no, r.date, r.channel, r.outcome, r.next_step, "
            " s.context_ref FROM negotiation_rounds r "
            "JOIN negotiation_strategies s ON s.id=r.strategy_id "
            "WHERE r.stakeholder_id=? ORDER BY r.date DESC",
            (sid,),
        )
    ]
    trail = [
        dict(r)
        for r in conn.execute(
            "SELECT source, ref, date, direction, subject, read_status "
            "FROM communication_trail WHERE stakeholder_id=? ORDER BY date DESC",
            (sid,),
        )
    ]
    return {
        "stakeholder": dict(s),
        "links": links,
        "claims": claims,
        "rounds": rounds,
        "trail": trail,
    }
