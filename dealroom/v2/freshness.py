"""DEALROOM v2 — freshness engine (SPEC-DEALROOM-V2.md §5, rules 1–6).

Deterministic, server-side, computed from DB state on demand. The tool tells
Roman what is stale — never the reverse. Every flag carries the evidence in
its message.

Flag shape:
    {"deal": code_name, "rule": str, "severity": "alert"|"warn"|"info",
     "message": str, "group_hint": "roman"|"seller"|None}
"""

import json
from datetime import date, datetime, timedelta, timezone

ACTIVE_STAGES = {
    "meeting_concluded",
    "valuation_rfi",
    "indicative_offer",
    "loi_negotiation",
    "loi_signed",
    "due_diligence",
    "contract_negotiation",
}

DD_EVIDENCE_TYPES = ("databook", "fdd_report", "dataroom_file")
SIGNED_MARKERS = ("signed", "unterschrieben", "gegengezeichnet", "countersign")
PRE_LOI_STAGES = {
    "meeting_concluded",
    "valuation_rfi",
    "indicative_offer",
    "loi_negotiation",
}


def _cfg(conn, key, default):
    row = conn.execute(
        "SELECT value FROM freshness_config WHERE key=?", (key,)
    ).fetchone()
    try:
        return int(row["value"]) if row else default
    except (TypeError, ValueError):
        return default


def _today():
    return datetime.now(timezone.utc).date()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def deal_flags(conn, deal) -> list[dict]:
    """All freshness flags for one deal row (sqlite3.Row from deals)."""
    code = deal["code_name"]
    domain = deal["domain"]
    stage = deal["deal_stage"]
    flags = []

    def flag(rule, severity, message, group_hint=None):
        flags.append(
            {
                "deal": code,
                "rule": rule,
                "severity": severity,
                "message": message,
                "group_hint": group_hint,
            }
        )

    # -- rule 1: extraction stale — source artifact newer than extracted rows
    if domain:
        newest_fin_src = conn.execute(
            "SELECT MAX(COALESCE(file_mtime, file_date)) d FROM deal_artifacts "
            "WHERE code_name=? AND artifact_type IN "
            "('financials_raw','model','commercial_raw')",
            (code,),
        ).fetchone()["d"]
        newest_extract = conn.execute(
            "SELECT MAX(extracted_at) d FROM ("
            " SELECT extracted_at FROM deal_financials WHERE domain=?"
            " UNION ALL SELECT extracted_at FROM deal_commercial WHERE domain=?)",
            (domain, domain),
        ).fetchone()["d"]
        if (
            newest_fin_src
            and newest_extract
            and newest_fin_src[:10] > newest_extract[:10]
        ):
            flag(
                "extraction_stale",
                "warn",
                f"Quelle neuer als Extraktion: Datei vom {newest_fin_src[:10]}, "
                f"letzte Extraktion {newest_extract[:10]}",
                "roman",
            )

    # -- rule 2: artifact chain broken (rfi/slides older than current databook)
    cur = {
        r["artifact_type"]: r
        for r in conn.execute(
            "SELECT artifact_type, file_date, file_name FROM deal_artifacts "
            "WHERE code_name=? AND status='current' "
            "AND artifact_type IN ('databook','rfi','slides')",
            (code,),
        )
    }
    db_art = cur.get("databook")
    if db_art and db_art["file_date"]:
        for dep, label in (("rfi", "RFI"), ("slides", "Slides")):
            d = cur.get(dep)
            if d and d["file_date"] and d["file_date"] < db_art["file_date"]:
                flag(
                    "chain_broken",
                    "warn",
                    f"{label} ({d['file_date']}) älter als aktuelles Databook "
                    f"({db_art['file_date']})",
                    "roman",
                )

    # -- rule 3: model inputs outdated — section 04 newer than current model
    newest_04 = conn.execute(
        "SELECT MAX(newest_file_date) d FROM dataroom_scans "
        "WHERE code_name=? AND section='04'",
        (code,),
    ).fetchone()["d"]
    model = conn.execute(
        "SELECT MAX(COALESCE(file_mtime, file_date)) d FROM deal_artifacts "
        "WHERE code_name=? AND artifact_type='model' AND status IN "
        "('current','final')",
        (code,),
    ).fetchone()["d"]
    if newest_04 and model and newest_04[:10] > model[:10]:
        flag(
            "model_outdated",
            "warn",
            f"Neue Finanzdaten im Datenraum (04: {newest_04[:10]}) nach letztem "
            f"Modellstand ({model[:10]})",
            "roman",
        )

    # -- rule 4: data-room delta since last scan
    added_total, changed_total = 0, 0
    for r in conn.execute(
        "SELECT section, delta_json FROM dataroom_scans WHERE code_name=? "
        "AND scanned_at = (SELECT MAX(scanned_at) FROM dataroom_scans s2 "
        "WHERE s2.code_name = dataroom_scans.code_name)",
        (code,),
    ):
        try:
            delta = json.loads(r["delta_json"] or "{}")
        except json.JSONDecodeError:
            delta = {}
        added_total += len(delta.get("added", []))
        changed_total += len(delta.get("changed", []))
    if added_total or changed_total:
        flag(
            "dataroom_delta",
            "info",
            f"Datenraum: {added_total} neue, {changed_total} geänderte Dateien "
            "seit letztem Scan",
            "roman",
        )

    # -- rule 5: stage-evidence mismatch
    signed_loi = conn.execute(
        "SELECT file_name FROM deal_artifacts WHERE code_name=? "
        "AND artifact_type IN ('loi','nbo') AND ("
        + " OR ".join("lower(file_name) LIKE ?" for _ in SIGNED_MARKERS)
        + ") LIMIT 1",
        (code, *[f"%{m}%" for m in SIGNED_MARKERS]),
    ).fetchone()
    if signed_loi and stage in PRE_LOI_STAGES:
        flag(
            "stage_mismatch",
            "alert",
            f"Unterzeichnete LOI registriert ({signed_loi['file_name']}), "
            f"Stage ist aber '{stage}'",
            "roman",
        )
    if stage in PRE_LOI_STAGES - {"loi_negotiation"}:
        dd_evidence = conn.execute(
            "SELECT COUNT(*) n FROM deal_artifacts WHERE code_name=? "
            "AND artifact_type IN (?,?,?)",
            (code, *DD_EVIDENCE_TYPES),
        ).fetchone()["n"]
        if dd_evidence:
            flag(
                "stage_mismatch",
                "warn",
                f"{dd_evidence} DD-Artefakte registriert, Stage ist '{stage}'",
                "roman",
            )
    if stage in ("on_hold", "dead") and domain:
        recent_round = conn.execute(
            "SELECT MAX(r.date) d FROM negotiation_rounds r "
            "JOIN negotiation_strategies s ON s.id = r.strategy_id "
            "WHERE s.deal_domain=? AND s.status='active'",
            (domain,),
        ).fetchone()["d"]
        if recent_round:
            flag(
                "stage_mismatch",
                "alert",
                f"Aktive Verhandlungsrunden (zuletzt {recent_round}) bei Stage "
                f"'{stage}'",
                "roman",
            )

    # -- rule 6: activity decay (only when the deal has a communication trail)
    if stage in ACTIVE_STAGES and domain:
        last_contact = conn.execute(
            "SELECT MAX(t.date) d FROM communication_trail t "
            "JOIN stakeholder_links l ON l.stakeholder_id = t.stakeholder_id "
            "WHERE l.deal_domain=?",
            (domain,),
        ).fetchone()["d"]
        if last_contact:
            decay_days = _cfg(conn, "activity_decay_days", 14)
            d = _parse_date(last_contact)
            if d and (_today() - d).days > decay_days:
                flag(
                    "activity_decay",
                    "warn",
                    f"Kein erfasster Kontakt seit {last_contact} (> {decay_days} Tage)",
                    "roman",
                )

    return flags


def milestone_flags(conn, deal) -> list[dict]:
    """Milestones due within warn window or overdue — feeds Attention groups."""
    code = deal["code_name"]
    if deal["deal_stage"] not in ACTIVE_STAGES:
        return []
    warn_days = _cfg(conn, "milestone_warn_days", 7)
    today = _today()
    horizon = today + timedelta(days=warn_days)
    flags = []
    for m in conn.execute(
        "SELECT milestone, due_date, owner FROM deal_milestones "
        "WHERE code_name=? AND status='open' AND due_date IS NOT NULL "
        "ORDER BY due_date",
        (code,),
    ):
        due = _parse_date(m["due_date"])
        if not due or due > horizon:
            continue
        overdue = due < today
        group = "seller" if m["owner"] == "Seller" else "roman"
        flags.append(
            {
                "deal": code,
                "rule": "milestone_overdue" if overdue else "milestone_due",
                "severity": "alert" if overdue else "warn",
                "message": (
                    f"Meilenstein {'überfällig' if overdue else 'fällig'}: "
                    f"{m['milestone']} ({due.strftime('%d.%m.')}, {m['owner']})"
                ),
                "group_hint": group,
            }
        )
    return flags


def rfi_flags(conn, deal) -> list[dict]:
    """Open sent RFI questions overdue → waiting on seller."""
    domain = deal["domain"]
    if not domain or deal["deal_stage"] not in ACTIVE_STAGES:
        return []
    overdue_days = _cfg(conn, "rfi_high_overdue_days", 10)
    cutoff = (_today() - timedelta(days=overdue_days)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) n, MIN(sent_at) oldest FROM deal_questions "
        "WHERE domain=? AND sent_at IS NOT NULL AND answered_at IS NULL "
        "AND importance='high' AND sent_at <= ?",
        (domain, cutoff),
    ).fetchone()
    if row["n"]:
        days = (
            (_today() - _parse_date(row["oldest"])).days
            if _parse_date(row["oldest"])
            else "?"
        )
        return [
            {
                "deal": deal["code_name"],
                "rule": "rfi_overdue",
                "severity": "warn",
                "message": f"{row['n']} offene HIGH-RFI, älteste seit {days} Tagen",
                "group_hint": "seller",
            }
        ]
    return []


def all_flags(conn, deal) -> list[dict]:
    return deal_flags(conn, deal) + milestone_flags(conn, deal) + rfi_flags(conn, deal)
