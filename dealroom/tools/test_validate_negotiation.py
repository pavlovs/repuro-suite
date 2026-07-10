# -*- coding: utf-8 -*-
"""Regression tests for validate_negotiation.py.

Every test named test_lion_correction_* encodes an ACTUAL correction Roman had
to make during the Lion pilot (2026-07-07/08). If one of these goes red, the
workflow has regressed to a failure mode that already burned trust once.
Runnable standalone (python test_validate_negotiation.py) or via pytest.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_negotiation import validate  # noqa: E402

DDL = """
CREATE TABLE stakeholders (id INTEGER PRIMARY KEY, name TEXT, hubspot_contact_id TEXT);
CREATE TABLE profile_claims (id INTEGER PRIMARY KEY, stakeholder_id INTEGER, field TEXT,
  value TEXT, confidence TEXT, status TEXT DEFAULT 'active');
CREATE TABLE negotiation_strategies (id INTEGER PRIMARY KEY, stakeholder_id INTEGER,
  memo_md TEXT, reservation TEXT, outcome_target TEXT, status TEXT DEFAULT 'active',
  closed_reason TEXT);
CREATE TABLE negotiation_rounds (id INTEGER PRIMARY KEY, strategy_id INTEGER, date TEXT);
CREATE TABLE negotiation_predictions (id INTEGER PRIMARY KEY, strategy_id INTEGER, tag TEXT);
CREATE TABLE communication_trail (id INTEGER PRIMARY KEY, stakeholder_id INTEGER, source TEXT,
  ref TEXT, date TEXT, direction TEXT, subject TEXT, read_status TEXT DEFAULT 'unread');
CREATE TABLE negotiation_milestones (id INTEGER PRIMARY KEY, strategy_id INTEGER,
  date TEXT, label TEXT, side TEXT DEFAULT 'both', consequence TEXT,
  status TEXT DEFAULT 'pending');
CREATE TABLE negotiation_open_items (id INTEGER PRIMARY KEY, strategy_id INTEGER,
  item TEXT, owner TEXT, due TEXT, status TEXT DEFAULT 'open', resolution TEXT);
CREATE TABLE strategy_parties (id INTEGER PRIMARY KEY, strategy_id INTEGER,
  stakeholder_id INTEGER, role TEXT, notes TEXT);
CREATE TABLE negotiation_positions (id INTEGER PRIMARY KEY, strategy_id INTEGER,
  term TEXT, preferred TEXT, fallback TEXT, walk_away TEXT,
  escalation_required INTEGER DEFAULT 0, roman_confirmed INTEGER DEFAULT 0,
  status TEXT DEFAULT 'open');
"""
HS_DDL = """
CREATE TABLE engagements (id INTEGER PRIMARY KEY, timestamp TEXT);
CREATE TABLE engagement_contact (engagement_id INTEGER, contact_id INTEGER);
"""
ALL_CLAIMS = [
    "MOTIVATOR_STACK",
    "RISK_DISPOSITION",
    "DECISION_STYLE",
    "TRUST_POSTURE",
    "COMM_PREFS",
    "PERSONALITY",
    "NEGOTIATION_PATTERN",
]

GOOD_MEMO = """# Strategie X
## QUELLEN-MANIFEST
deals.md GELESEN | Deal-Model (golden/model/x.xlsx, Sheet Bewertung) GELESEN | Angebot v3 PDF GELESEN | Mail-Thread seit 08/2025 GELESEN | Granola alle Meetings GELESEN | hubspot.db Engagements GELESEN
## VERHANDLUNGSHISTORIE
Tabelle: 13 Runden. Bilanz 9:1.
## POSITION (UNSERE)
Multiple 5,6x vs Fox 5,3x.
### UNSERE ZIELE (Rangfolge)
1. Kapitaldisziplin.
## PROFIL
Claims-Tabelle.
## OAR
Utility, BATNA.
### SEINE ZIELE (Rangfolge)
1. Sicherheit.
### TAUSCHRAUM
Integrativ: Sicherheit x Disziplin.
## ASK-DEKODIERUNG
Lesarten gerankt.
## WISSENSLÜCKEN & INVESTIGATION
KNOWN/ASSUMED (n=3)/UNKNOWN + Discovery.
## OPTIONEN & REAKTIONS-PROGNOSE
Option A. REAKTIONS-PROGNOSE: Slide kommt erneut, 60-80% (Schätzung, n=3), Falsifier: schriftliche Wiederholung.
## EMPFEHLUNG
Option B, begründet gegen Ziele.
## OBJECTION-BANK
1. Einwand [profile] 60-70% (Schätzung, n=3) Konter/Fallback/Falsifier.
## GUARD-PASS
- C4 Concession-Scoring: kein einseitiges Geben, Tausch benannt in EMPFEHLUNG Z.2. COMPLIED mit Evidenz.
"""


def make_dbs(
    tmp,
    memo=GOOD_MEMO,
    reservation="[ROMAN SETZEN]",
    rounds_start="2025-09-10",
    n_rounds=5,
    claims=ALL_CLAIMS,
    n_pred=3,
    hs_first="2025-08-12",
    trail_rows=1,
    trail_unread=0,
    trail_sealed=0,
    trail_source="hubspot",
    trail_ref=None,
    status="active",
    parties=((1, "primary"),),
    milestones=(),
    positions=(),
    extra_stakeholders=(),
    drop_tables=(),
    sql=(),
):
    db = str(Path(tmp) / "deal.db")
    con = sqlite3.connect(db)
    con.executescript(DDL)
    con.execute("INSERT INTO stakeholders VALUES (1,'Test','42')")
    for f in claims:
        con.execute(
            "INSERT INTO profile_claims (stakeholder_id, field, value, confidence) "
            "VALUES (1,?,?, 'LOW')",
            (f, "v"),
        )
    con.execute(
        "INSERT INTO negotiation_strategies "
        "(id, stakeholder_id, memo_md, reservation, outcome_target, status) "
        "VALUES (1,1,?,?,'LOI bis 07.08',?)",
        (memo, reservation, status),
    )
    for n, (psid, role) in enumerate(parties):
        con.execute(
            "INSERT INTO strategy_parties (strategy_id, stakeholder_id, role) "
            "VALUES (1,?,?)",
            (psid, role),
        )
    for sid_, name_, n_claims in extra_stakeholders:
        con.execute("INSERT INTO stakeholders VALUES (?,?,NULL)", (sid_, name_))
        for i in range(n_claims):
            con.execute(
                "INSERT INTO profile_claims (stakeholder_id, field, value, confidence) "
                "VALUES (?,?,?, 'LOW')",
                (sid_, f"F{i}", "v"),
            )
    for m_date, m_status in milestones:
        con.execute(
            "INSERT INTO negotiation_milestones (strategy_id, date, label, status) "
            "VALUES (1,?,'test',?)",
            (m_date, m_status),
        )
    for term, pref, confirmed in positions:
        con.execute(
            "INSERT INTO negotiation_positions "
            "(strategy_id, term, preferred, roman_confirmed) VALUES (1,?,?,?)",
            (term, pref, confirmed),
        )
    for stmt, params in sql:
        con.execute(stmt, params)
    for t in drop_tables:
        con.execute(f"DROP TABLE {t}")
    for i in range(trail_rows):
        status = (
            "unread"
            if i < trail_unread
            else "sealed"
            if i < trail_unread + trail_sealed
            else "read"
        )
        con.execute(
            "INSERT INTO communication_trail (stakeholder_id, source, ref, read_status) VALUES (1,?,?,?)",
            (trail_source, trail_ref if trail_ref else str(i + 1), status),
        )
    for i in range(n_rounds):
        y, m = (rounds_start[:4], int(rounds_start[5:7]) + i)
        con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, date) VALUES (1,?)",
            (f"{int(y) + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}-15",),
        )
    con.execute("UPDATE negotiation_rounds SET date=? WHERE id=1", (rounds_start,))
    for _ in range(n_pred):
        con.execute(
            "INSERT INTO negotiation_predictions (strategy_id, tag) VALUES (1,'profile')"
        )
    con.commit()
    con.close()
    hs = str(Path(tmp) / "hs.db")
    h = sqlite3.connect(hs)
    h.executescript(HS_DDL)
    h.execute("INSERT INTO engagements VALUES (1, ?)", (hs_first + "T10:00:00Z",))
    h.execute("INSERT INTO engagement_contact VALUES (1, 42)")
    h.commit()
    h.close()
    return db, hs


def _run(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        db, hs = make_dbs(tmp, **kw)
        return validate(1, db, hs)[0]


def test_compliant_memo_passes():
    assert _run() == []


def test_lion_correction_1_missing_position_and_ledger():
    # Roman correction #1: recommendation without own economics/ledger -> structural sections missing
    memo = GOOD_MEMO.replace("## POSITION (UNSERE)", "## IRRELEVANT").replace(
        "## VERHANDLUNGSHISTORIE", "## AUCH-IRRELEVANT"
    )
    f = _run(memo=memo)
    assert any("VERHANDLUNGSHISTORIE" in x for x in f) and any(
        "POSITION" in x for x in f
    )


def test_lion_correction_2_history_not_since_first_contact():
    # Roman correction #2: ledger started May 2026, first contact Aug 2025
    f = _run(rounds_start="2026-05-19", hs_first="2025-08-12")
    assert any("FIRST CONTACT" in x for x in f)


def test_lion_correction_3_uncalibrated_probability():
    # Roman correction #3: overconfident point estimates without evidence base
    memo = GOOD_MEMO.replace(
        "60-80% (Schätzung, n=3), Falsifier: schriftliche Wiederholung", "70% sicher"
    )
    f = _run(memo=memo)
    assert any("uncalibrated probability" in x for x in f)


def test_lion_inference_failure_model_not_in_manifest():
    # Roman 08.07: "It is in the Lion model and available to you" — unread available source
    memo = GOOD_MEMO.replace(
        "Deal-Model (golden/model/x.xlsx, Sheet Bewertung) GELESEN | ", ""
    )
    f = _run(memo=memo)
    assert any("source: model" in x for x in f)


def test_email_draft_blocked():
    f = _run(memo=GOOD_MEMO + "\nBetreff: AW Angebot\n")
    assert any("email draft" in x for x in f)


def test_invented_reservation():
    f = _run(reservation="Floor 90%, Cap 4.465")
    assert any("invented" in x and "reservation" in x for x in f)


def test_missing_claims():
    f = _run(claims=[c for c in ALL_CLAIMS if c != "NEGOTIATION_PATTERN"])
    assert any("NEGOTIATION_PATTERN" in x for x in f)


def test_too_few_predictions():
    f = _run(n_pred=1)
    assert any("premortem incomplete" in x for x in f)


def test_bare_complied_guard():
    memo = GOOD_MEMO.replace(
        "- C4 Concession-Scoring: kein einseitiges Geben, Tausch benannt in EMPFEHLUNG Z.2. COMPLIED mit Evidenz.",
        "- C4: COMPLIED.",
    )
    f = _run(memo=memo)
    assert any("bare COMPLIED" in x for x in f)


def test_trail_missing_blocks():
    # CAT backtest 08.07: GELESEN claimed without enumeration
    f = _run(trail_rows=0)
    assert any("trail not enumerated" in x for x in f)


def test_trail_unread_blocks():
    f = _run(trail_rows=3, trail_unread=1)
    assert any("non-READ" in x for x in f)


def test_trail_hubspot_undercount():
    # mirror has 1 engagement; trail exists but covers 0 hubspot items
    f = _run(trail_source="email_live")
    assert any("trail incomplete" in x for x in f)


def test_codex_header_spoof_blocks():
    # Codex finding 1: 'POSITIONIERUNG' must not satisfy 'POSITION'
    memo = GOOD_MEMO.replace("## POSITION (UNSERE)", "## POSITIONIERUNG (UNSERE)")
    f = _run(memo=memo)
    assert any("missing section: POSITION" in x for x in f)


def test_codex_duplicate_header_blocks():
    memo = GOOD_MEMO + "\n## GUARD-PASS\nnachtrag"
    f = _run(memo=memo)
    assert any("duplicate section header: GUARD-PASS" in x for x in f)


def test_codex_sealed_trail_blocks():
    # Codex finding 2: sealed rows must not launder unread items
    f = _run(trail_rows=3, trail_sealed=1)
    assert any("non-READ" in x for x in f)


def test_codex_fake_hubspot_row_blocks():
    # Codex finding 3: a fake row can't mask a missing mirror engagement (id-set check)
    f = _run(trail_ref="999")
    assert any("trail incomplete" in x for x in f)


def test_codex_reservation_laundering_blocks():
    # Codex finding 5: 'Roman said maybe X' is not a confirmation
    f = _run(reservation="Roman said maybe 4.465 floor")
    assert any("laundered reservation" in x or "invented" in x for x in f)


def test_codex_hubspot_failclosed():
    # Codex finding 8: malformed mirror data must FAIL, not warn
    f = _run(hs_first="garbage")
    assert any("fail-closed" in x for x in f)


def test_missing_interest_subsections():
    memo = GOOD_MEMO.replace("### TAUSCHRAUM", "### SONSTIGES")
    f = _run(memo=memo)
    assert any("TAUSCHRAUM" in x for x in f)


# ---- §12 hardening (2026-07-10) — CAT stress-test failure classes ----


def test_v12_executing_without_milestone_blocks():
    # CAT lesson: strategy closed/idle while the signature chase had no deadline map
    f = _run(status="executing", milestones=())
    assert any("no pending future milestone" in x for x in f)


def test_v12_executing_with_future_milestone_passes():
    f = _run(status="executing", milestones=[("2099-01-01", "pending")])
    assert f == []


def test_v12_past_milestone_does_not_satisfy():
    f = _run(status="executing", milestones=[("2020-01-01", "pending")])
    assert any("no pending future milestone" in x for x in f)


def test_v12_missing_parties_blocks():
    # Boyens gap: multi-party must be enumerated, not prose
    f = _run(parties=())
    assert any("strategy_parties" in x for x in f)


def test_v12_co_seller_thin_profile_blocks():
    # Boyens: 45,8% co-seller with 1 claim must block, not warn
    f = _run(
        parties=((1, "primary"), (2, "co_seller")),
        extra_stakeholders=((2, "Co", 1),),
    )
    assert any("co_seller" in x and "claim" in x for x in f)


def test_v12_co_seller_with_profile_passes():
    f = _run(
        parties=((1, "primary"), (2, "co_seller")),
        extra_stakeholders=((2, "Co", 3),),
    )
    assert f == []


def test_v12_unconfirmed_position_numbers_blocks():
    # three-tier positions: numbers without Roman = laundering guard
    f = _run(positions=[("EBIT-Floor", "625 K EUR", 0)])
    assert any("position" in x and "Roman" in x for x in f)


def test_v12_confirmed_position_passes():
    f = _run(positions=[("EBIT-Floor", "625 K EUR", 1)])
    assert f == []


def test_v12_missing_migration_blocks():
    f = _run(drop_tables=("negotiation_positions",))
    assert any("migration not run" in x for x in f)


def test_v12_unknown_status_blocks():
    f = _run(status="done")
    assert any("unknown strategy status" in x for x in f)


def test_v12_null_status_blocks():
    # codex 07-10 #9: NULL must not evade the phase-model check
    f = _run(status=None)
    assert any("unknown strategy status" in x for x in f)


def test_v12_malformed_future_milestone_blocks():
    # codex 07-10 #7: '9999-not-a-date' must not satisfy the future check
    f = _run(status="executing", milestones=[("9999-not-a-date", "pending")])
    assert any("unparseable date" in x for x in f)
    assert any("no pending future milestone" in x for x in f)


def test_v12_primary_party_must_match_strategy_stakeholder():
    # codex 07-10 #8: a primary mislabeled as co_seller games the coverage
    f = _run(parties=((1, "co_seller"),))
    assert any("exactly one 'primary'" in x for x in f)


def test_v12_wrong_primary_blocks():
    f = _run(
        parties=((2, "primary"), (1, "co_seller")),
        extra_stakeholders=((2, "Other", 3),),
    )
    assert any("exactly one 'primary'" in x for x in f)


def test_v12_duplicate_co_seller_claims_block():
    # codex 07-10 #8: 3 copies of ONE claim field are 1 claim, not 3
    f = _run(
        parties=((1, "primary"), (2, "co_seller")),
        extra_stakeholders=((2, "Co", 0),),
        sql=[
            (
                "INSERT INTO profile_claims (stakeholder_id, field, value, confidence) "
                "VALUES (2,'MOTIVATOR_STACK','v','LOW')",
                (),
            )
        ]
        * 3,
    )
    assert any("co_seller" in x and "claim" in x for x in f)


if __name__ == "__main__":
    tests = [(n, fn) for n, fn in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError:
            failed += 1
            print(f"FAIL {name}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
