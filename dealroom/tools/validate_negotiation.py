# -*- coding: utf-8 -*-
"""Deterministic gate for /repuro:negotiate strategy memos (analogous to validate_ci.py).

Usage: python validate_negotiation.py <strategy_id> [--db <path>] [--hubspot <path>]
Exit 0 = PASS, 1 = FAIL. Checks structure + data coverage, not judgment quality.
Importable: validate(strategy_id, db_path, hubspot_path) -> (findings, warnings, info).
Regression tests: test_validate_negotiation.py — every Roman correction from the
Lion pilot (2026-07-07/08) is a named test case there. Extend BOTH when a new
failure class appears.
"""

import argparse
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "dealroom.db"
DEFAULT_HUBSPOT = Path(r"C:\Users\X1\Documents\CLAUDE_COWORK\repuro-data\hubspot.db")

REQUIRED_SECTIONS = [
    "QUELLEN-MANIFEST",
    "VERHANDLUNGSHISTORIE",
    "POSITION",
    "PROFIL",
    "OAR",
    "ASK-DEKODIERUNG",
    "WISSENSLÜCKEN",
    "OPTIONEN",
    "EMPFEHLUNG",
    "OBJECTION-BANK",
    "GUARD-PASS",
]
# Interest layer + per-option response forecasts: presence required, order free
REQUIRED_SUBSECTIONS = [
    "UNSERE ZIELE",
    "SEINE ZIELE",
    "TAUSCHRAUM",
    "REAKTIONS-PROGNOSE",
]
REQUIRED_CLAIM_FIELDS = {
    "MOTIVATOR_STACK",
    "RISK_DISPOSITION",
    "DECISION_STYLE",
    "TRUST_POSTURE",
    "COMM_PREFS",
    "PERSONALITY",
    "NEGOTIATION_PATTERN",
}
# Canonical evidence sources that must appear (GELESEN or NICHT VERFÜGBAR) in the manifest.
MANIFEST_SOURCES = ["deals.md", "model", "angebot", "granola", "mail", "hubspot"]
# Sections in which a bare percentage without calibration marker is a violation.
FORECAST_SECTIONS = ("WISSENSLÜCKEN", "OPTIONEN", "OBJECTION-BANK")
CALIBRATION_MARKERS = ("schätzung", "schaetzung", "n=", "basis:")


def _sec_rx(name):
    # (?!\w) prevents substring spoofing: 'POSITIONIERUNG' must not satisfy 'POSITION'
    return r"^#{1,3}\s+.*" + re.escape(name) + r"(?!\w)"


def _section_span(memo, name, all_names):
    m = re.search(_sec_rx(name), memo, re.MULTILINE | re.IGNORECASE)
    if not m:
        return None
    starts = []
    for other in all_names:
        if other == name:
            continue
        om = re.search(_sec_rx(other), memo, re.MULTILINE | re.IGNORECASE)
        if om and om.start() > m.start():
            starts.append(om.start())
    end = min(starts) if starts else len(memo)
    return memo[m.start() : end]


def validate(strategy_id, db_path=None, hubspot_path=None):
    """Returns (findings, warnings, info). Empty findings == PASS."""
    findings, warn = [], []
    db_path = str(db_path or DEFAULT_DB)
    hubspot_path = str(hubspot_path or DEFAULT_HUBSPOT)

    con = sqlite3.connect(db_path)
    row = con.execute(
        "SELECT stakeholder_id, memo_md, reservation, outcome_target, status "
        "FROM negotiation_strategies WHERE id=?",
        (strategy_id,),
    ).fetchone()
    if row is None:
        con.close()
        return [f"strategy {strategy_id} not found in {db_path}"], warn, {}
    sid, memo, reservation, outcome, status = row
    memo = memo or ""

    # 0. §12 phase model + schema presence (fail closed: missing migration = finding)
    VALID_STATUS = {"active", "executing", "closed", "superseded"}
    if status not in VALID_STATUS:  # NULL/empty is just as invalid (codex 07-10 #9)
        findings.append(
            f"unknown strategy status {status!r} (allowed: {sorted(VALID_STATUS)})"
        )
    tables = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for t in (
        "negotiation_milestones",
        "strategy_parties",
        "negotiation_positions",
        "negotiation_open_items",
    ):
        if t not in tables:
            findings.append(f"§12 migration not run — missing table: {t}")

    # 0b. executing strategies need a future deadline map as ROWS (CAT lesson:
    # agreement != outcome; the signature chase must have an owner)
    if status == "executing" and "negotiation_milestones" in tables:
        # local Berlin wall-clock, parsed in Python — date('now') is UTC and a
        # lexical compare lets '9999-not-a-date' pass (codex 07-10 #7)
        today = date.today()
        future = 0
        for mid, mdate in con.execute(
            "SELECT id, date FROM negotiation_milestones "
            "WHERE strategy_id=? AND status='pending'",
            (strategy_id,),
        ):
            try:
                d = date.fromisoformat(str(mdate))
            except (ValueError, TypeError):
                findings.append(
                    f"milestone {mid} has unparseable date {mdate!r} — fix before delivery"
                )
                continue
            if d >= today:
                future += 1
        if not future:
            findings.append(
                "status=executing but no pending future milestone — "
                "write the deadline map (negotiate_ops.py milestone add)"
            )

    # 0c. multi-party (P5): all parties enumerated; co-sellers need real profiles
    if "strategy_parties" in tables:
        parties = con.execute(
            "SELECT stakeholder_id, role FROM strategy_parties WHERE strategy_id=?",
            (strategy_id,),
        ).fetchall()
        if not parties:
            findings.append(
                "no strategy_parties rows — enumerate ALL parties at intake "
                "(P5: German deals die on the advisor)"
            )
        else:
            # exactly one primary, and it must BE the strategy's stakeholder —
            # a primary mislabeled as co_seller games the coverage (codex 07-10 #8)
            primaries = [pid for pid, role in parties if role == "primary"]
            if primaries != [sid]:
                findings.append(
                    f"strategy_parties must contain exactly one 'primary' matching "
                    f"the strategy stakeholder ({sid}) — found primaries: {primaries}"
                )
        for pid, role in parties:
            # DISTINCT fields: three copies of one claim are one claim (codex #8)
            n_claims = con.execute(
                "SELECT COUNT(DISTINCT field) FROM profile_claims "
                "WHERE stakeholder_id=? AND status='active'",
                (pid,),
            ).fetchone()[0]
            if role == "co_seller" and n_claims < 3:
                findings.append(
                    f"co_seller stakeholder {pid} has only {n_claims} active claim(s) "
                    f"— profile the co-seller before strategizing past them"
                )
            elif role in ("advisor", "influencer") and n_claims == 0:
                warn.append(
                    f"{role} stakeholder {pid} has no profile claims — "
                    f"at least a role/incentive read is expected"
                )

    # 0d. three-tier positions: numbers require Roman confirmation (same
    # laundering guard as the reservation)
    if "negotiation_positions" in tables:
        for pid_, term, pref, fb, wa, confirmed in con.execute(
            "SELECT id, term, preferred, fallback, walk_away, roman_confirmed "
            "FROM negotiation_positions WHERE strategy_id=?",
            (strategy_id,),
        ):
            blob = " ".join(filter(None, (pref, fb, wa)))
            if re.search(r"\d", blob) and not confirmed:
                findings.append(
                    f"position '{term}' (id {pid_}) carries numbers without Roman "
                    f"confirmation — confirm or strip (negotiate_ops.py position confirm)"
                )

    # 1. Section headers, in order, exactly once
    pos = -1
    for sec in REQUIRED_SECTIONS:
        hits = list(re.finditer(_sec_rx(sec), memo, re.MULTILINE | re.IGNORECASE))
        if not hits:
            findings.append(f"missing section: {sec}")
        else:
            if len(hits) > 1:
                findings.append(f"duplicate section header: {sec} ({len(hits)}x)")
            if hits[0].start() < pos:
                findings.append(f"section out of order: {sec}")
            pos = hits[0].start()

    # 1b. Interest-layer subsections
    for sub in REQUIRED_SUBSECTIONS:
        if not re.search(re.escape(sub) + r"(?!\w)", memo, re.IGNORECASE):
            findings.append(f"missing interest-layer subsection: {sub}")

    # 1c. Source manifest must cover the canonical sources (Lion failure: model unread)
    manifest = _section_span(memo, "QUELLEN-MANIFEST", REQUIRED_SECTIONS)
    if manifest:
        for src in MANIFEST_SOURCES:
            if src.lower() not in manifest.lower():
                findings.append(f"manifest does not account for source: {src}")

    # 1d. Communication trail: enumerated in DB, fully read (manifest-overclaim guard, CAT backtest 08.07)
    try:
        trail = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN read_status != 'read' THEN 1 ELSE 0 END),0) "
            "FROM communication_trail WHERE stakeholder_id=?",
            (sid,),
        ).fetchone()
    except sqlite3.OperationalError:
        trail = (0, 0)
    if not trail[0]:
        findings.append(
            "communication_trail empty — trail not enumerated (manifest-overclaim guard)"
        )
    elif trail[1]:
        findings.append(
            f"communication_trail: {trail[1]} non-READ item(s) (unread/sealed) — "
            f"available-but-unread blocks analysis; sealed rows must be unsealed or removed before a live strategy"
        )

    # 2. No email drafts inside a strategy memo
    if re.search(r"^\s*(Betreff|Subject)\s*:", memo, re.MULTILINE):
        findings.append(
            "memo contains an email draft (Betreff:/Subject:) — drafts only on explicit request"
        )

    # 3. Outcome specificity
    if outcome and not re.search(
        r"\d|LOI|SPA|Exklusiv|Notar|Kaufabsicht", outcome, re.IGNORECASE
    ):
        warn.append(f"outcome_target looks vague: '{outcome[:60]}'")

    # 4. Reservation: digits require Roman's marker
    if (
        reservation
        and re.search(r"\d", reservation)
        and not re.search(r"ROMAN\s+(SETZEN|BESTÄTIGT|BESTAETIGT)", reservation.upper())
    ):
        findings.append(
            "reservation contains numbers without 'ROMAN SETZEN'/'ROMAN BESTÄTIGT' marker "
            "— invented or laundered reservation ('Roman said maybe X' does not count)"
        )

    # 4b. Calibration: percentages in forecast sections need Schätzung/n=/Basis marker on the same line
    for sec in FORECAST_SECTIONS:
        span = _section_span(memo, sec, REQUIRED_SECTIONS)
        if not span:
            continue
        for line in span.splitlines():
            if re.search(r"\d{1,3}\s*%", line) and not any(
                k in line.lower() for k in CALIBRATION_MARKERS
            ):
                findings.append(
                    f"uncalibrated probability in {sec}: '{line.strip()[:70]}' "
                    f"(needs Schätzung/n=/Basis on the line)"
                )

    # 5. Rounds coverage back to first contact
    n_rounds, first_round = con.execute(
        "SELECT COUNT(*), MIN(date) FROM negotiation_rounds WHERE strategy_id=?",
        (strategy_id,),
    ).fetchone()
    if n_rounds < 3:
        findings.append(f"only {n_rounds} rounds logged — history incomplete")
    hs = con.execute(
        "SELECT hubspot_contact_id FROM stakeholders WHERE id=?", (sid,)
    ).fetchone()
    hs_id = hs[0] if hs else None
    if hs_id and Path(hubspot_path).exists():
        try:
            h = sqlite3.connect(hubspot_path)
            first_eng = h.execute(
                "SELECT MIN(substr(e.timestamp,1,10)) FROM engagements e "
                "JOIN engagement_contact ec ON ec.engagement_id=e.id WHERE ec.contact_id=?",
                (int(hs_id),),
            ).fetchone()[0]
            mirror_ids = {
                str(r[0])
                for r in h.execute(
                    "SELECT engagement_id FROM engagement_contact WHERE contact_id=?",
                    (int(hs_id),),
                )
            }
            h.close()
            if trail[0]:
                trail_refs = {
                    str(r[0])
                    for r in con.execute(
                        "SELECT ref FROM communication_trail WHERE stakeholder_id=? AND source='hubspot'",
                        (sid,),
                    )
                }
                missing_ids = mirror_ids - trail_refs
                if missing_ids:
                    findings.append(
                        f"trail missing {len(missing_ids)} mirror engagement id(s) "
                        f"(e.g. {sorted(missing_ids)[:3]}) — trail incomplete; "
                        f"fake/duplicate rows cannot mask this (id-set comparison)"
                    )
            if first_eng and first_round:
                fe, fr = (
                    date.fromisoformat(first_eng),
                    date.fromisoformat(first_round[:10]),
                )
                if fr - fe > timedelta(days=45):
                    findings.append(
                        f"rounds start {first_round[:10]} but first HubSpot contact was {first_eng} "
                        f"— history since FIRST CONTACT not covered"
                    )
        except Exception as ex:
            # fail CLOSED: the mirror exists but the cross-check broke — a malformed
            # timestamp must not silently downgrade the first-contact guarantee
            findings.append(f"hubspot cross-check FAILED (fail-closed): {ex}")
    else:
        warn.append(
            "no hubspot_contact_id or mirror missing — first-contact coverage unverified"
        )

    # 6. Profile claims present (active), PERSONALITY may be UNSCORED but must exist
    claims = dict(
        con.execute(
            "SELECT field, confidence FROM profile_claims WHERE stakeholder_id=? AND status='active'",
            (sid,),
        ).fetchall()
    )
    missing = REQUIRED_CLAIM_FIELDS - set(claims)
    if missing:
        findings.append("missing profile claims: " + ", ".join(sorted(missing)))

    # 7. Predictions >=3, tags valid
    n_pred, n_valid = con.execute(
        "SELECT COUNT(*), SUM(CASE WHEN tag IN ('profile','archetype') THEN 1 ELSE 0 END) "
        "FROM negotiation_predictions WHERE strategy_id=?",
        (strategy_id,),
    ).fetchone()
    if (n_pred or 0) < 3:
        findings.append(f"only {n_pred} predictions — premortem incomplete (need >=3)")
    elif n_pred != n_valid:
        findings.append("predictions with invalid tag (must be profile|archetype)")

    # 8. Guard pass must carry evidence, not bare COMPLIED
    gp = _section_span(memo, "GUARD-PASS", REQUIRED_SECTIONS)
    if gp:
        bare = [
            l
            for l in gp.splitlines()
            if re.search(r"COMPLIED", l) and len(l.strip()) < 40
        ]
        if bare:
            findings.append(
                f"guard-pass has {len(bare)} bare COMPLIED line(s) without evidence"
            )

    con.close()
    info = {"rounds": n_rounds, "claims": len(claims), "predictions": n_pred or 0}
    return findings, warn, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("strategy_id", type=int)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--hubspot", default=str(DEFAULT_HUBSPOT))
    args = ap.parse_args()
    findings, warn, info = validate(args.strategy_id, args.db, args.hubspot)
    for w in warn:
        print("WARN:", w)
    if findings:
        print(f"FAIL ({len(findings)} finding(s)) — strategy {args.strategy_id}:")
        for f in findings:
            print("  -", f)
        return 1
    print(
        f"PASS — strategy {args.strategy_id}: {info['rounds']} rounds, "
        f"{info['claims']} claims, {info['predictions']} predictions, all sections present"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
