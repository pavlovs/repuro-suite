# -*- coding: utf-8 -*-
"""Regression tests for negotiate_ops.py (SPEC §12). Codex 2026-07-10 findings
are encoded as named tests — the theme: watch silence must mean VERIFIED-quiet.
Runnable standalone (python test_negotiate_ops.py) or via pytest.
"""

import contextlib
import io
import json
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import negotiate_ops  # noqa: E402
from negotiate_ops import _iso, _valid_date, collect_watch  # noqa: E402

BASE_DDL = """
CREATE TABLE stakeholders (id INTEGER PRIMARY KEY, name TEXT, hubspot_contact_id TEXT);
CREATE TABLE profile_claims (id INTEGER PRIMARY KEY, stakeholder_id INTEGER, field TEXT,
  value TEXT, confidence TEXT, status TEXT DEFAULT 'active');
CREATE TABLE negotiation_strategies (id INTEGER PRIMARY KEY, stakeholder_id INTEGER,
  context_ref TEXT, memo_md TEXT, reservation TEXT, outcome_target TEXT,
  status TEXT DEFAULT 'active');
CREATE TABLE negotiation_rounds (id INTEGER PRIMARY KEY, strategy_id INTEGER,
  stakeholder_id INTEGER, round_no INTEGER, date TEXT, channel TEXT, we_asked TEXT,
  they_asked TEXT, we_gave TEXT, they_gave TEXT, outcome TEXT, next_step TEXT);
CREATE TABLE negotiation_round_reviews (id INTEGER PRIMARY KEY, round_id INTEGER,
  went_well TEXT, went_wrong TEXT, lesson TEXT, self_rating INTEGER);
CREATE TABLE communication_trail (id INTEGER PRIMARY KEY, stakeholder_id INTEGER,
  source TEXT, ref TEXT, date TEXT, direction TEXT, subject TEXT,
  read_status TEXT DEFAULT 'unread');
"""

TODAY = date(2026, 7, 10)


class Args:
    def __init__(self, db, **kw):
        self.db = db
        self.hubspot = kw.pop("hubspot", str(Path(db).parent / "missing_hs.db"))
        for k, v in kw.items():
            setattr(self, k, v)


def make_db(tmp, migrated=True):
    db = str(Path(tmp) / "deal.db")
    con = sqlite3.connect(db)
    con.executescript(BASE_DDL)
    con.commit()
    con.close()
    if migrated:
        negotiate_ops.cmd_migrate(Args(db))
    return db


def seed(db, status="executing", strategy_id=1):
    con = sqlite3.connect(db)
    con.execute("INSERT INTO stakeholders VALUES (1, 'Test Seller', NULL)")
    con.execute(
        "INSERT INTO negotiation_strategies (id, stakeholder_id, context_ref, status) "
        "VALUES (?,1,'Cat',?)",
        (strategy_id, status),
    )
    con.commit()
    con.close()


def _watch(db, **kw):
    return collect_watch(
        db, str(Path(db).parent / "no_hs.db"), days=7, today=TODAY, **kw
    )


def _q(dbfile, sql):
    """One-shot query with a CLOSED handle — Windows keeps open handles alive
    and that breaks TemporaryDirectory cleanup."""
    con = sqlite3.connect(dbfile)
    row = con.execute(sql).fetchone()
    con.close()
    return row


# ---- migrate ----


def test_migrate_idempotent_and_backup_unique():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp, migrated=False)
        negotiate_ops.cmd_migrate(Args(db))
        negotiate_ops.cmd_migrate(Args(db))  # second run must not raise
        backups = list((Path(tmp)).glob("backups/*.db"))
        assert len(backups) == 2, "same-second reruns must produce distinct backups"


def test_migrate_backup_is_valid_sqlite():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp, migrated=False)
        seed_con = sqlite3.connect(db)
        seed_con.execute("INSERT INTO stakeholders VALUES (7, 'Backup Proof', NULL)")
        seed_con.commit()
        seed_con.close()
        negotiate_ops.cmd_migrate(Args(db))
        backup = next((Path(tmp)).glob("backups/*.db"))
        row = _q(backup, "SELECT name FROM stakeholders WHERE id=7")
        assert row and row[0] == "Backup Proof"


# ---- watch: codex findings 5/6 — degraded data must ALERT, not skip ----


def test_watch_overdue_milestone_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_milestones (strategy_id, date, label) "
            "VALUES (1,'2026-07-01','Sign LOI')"
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert any("OVERDUE" in a for a in alerts)


def test_watch_invalid_milestone_date_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_milestones (strategy_id, date, label) "
            "VALUES (1,'sometime soon','Sign')"
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert any("unparseable date" in a for a in alerts)


def test_watch_executing_without_milestone_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        alerts, _ = _watch(db)
        assert any("no future milestone" in a for a in alerts)


def test_watch_unlogged_interaction_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, stakeholder_id, date) "
            "VALUES (1,1,'2026-07-01')"
        )
        con.execute(
            "INSERT INTO communication_trail (stakeholder_id, source, date, read_status) "
            "VALUES (1,'email_live','2026-07-09','read')"
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert any("ledger stale" in a for a in alerts)


def test_watch_executing_empty_trail_alerts():
    # codex #6: no trail must not read as "not cold"
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        alerts, _ = _watch(db)
        assert any("no dated contact" in a for a in alerts)


def test_watch_cold_contact_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO communication_trail (stakeholder_id, source, date, read_status) "
            "VALUES (1,'email_live','2026-06-20','read')"
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert any("relationship-cold" in a for a in alerts)


def test_watch_missing_hubspot_mirror_alerts_when_live():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        alerts, _ = _watch(db)  # helper points hubspot at a missing file
        assert any("hubspot mirror MISSING" in a for a in alerts)


def test_watch_quiet_db_no_mirror_alert():
    # no live strategies -> mirror state is irrelevant, watch stays quiet
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        alerts, notes = _watch(db)
        assert alerts == [] and notes == []


def test_watch_stale_signals_not_treated_as_latest():
    # codex #5: an older round WITH signals must not stand in for the latest round
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        old_sig = json.dumps({"next_step_committed": False})
        con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, stakeholder_id, date, signals) "
            "VALUES (1,1,'2026-06-01',?)",
            (old_sig,),
        )
        con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, stakeholder_id, date, signals) "
            "VALUES (1,1,'2026-07-09',NULL)"
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert not any("WITHOUT a committed next step" in a for a in alerts)


def test_watch_missing_next_step_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, stakeholder_id, date, signals) "
            "VALUES (1,1,'2026-07-09',?)",
            (json.dumps({"next_step_committed": False}),),
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert any("WITHOUT a committed next step" in a for a in alerts)


def test_watch_unparseable_signals_alerts():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, stakeholder_id, date, signals) "
            "VALUES (1,1,'2026-07-09','not json')"
        )
        con.commit()
        con.close()
        alerts, _ = _watch(db)
        assert any("unparseable signals" in a for a in alerts)


# ---- transition guards (codex finding 10) ----


def test_open_item_double_resolve_is_noop():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_open_items (strategy_id, item, owner) "
            "VALUES (1,'JA 2025','them')"
        )
        con.commit()
        con.close()
        negotiate_ops.cmd_open_item(
            Args(db, action="resolve", id=1, resolution="done", strategy=None)
        )
        negotiate_ops.cmd_open_item(
            Args(db, action="resolve", id=1, resolution="OVERWRITE", strategy=None)
        )
        row = _q(db, "SELECT resolution FROM negotiation_open_items WHERE id=1")
        assert row[0] == "done", "second resolve must not overwrite the first"


def test_milestone_terminal_state_immutable():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_milestones (strategy_id, date, label, status) "
            "VALUES (1,'2026-07-24','Sign','met')"
        )
        con.commit()
        con.close()
        negotiate_ops.cmd_milestone(
            Args(db, action="set-status", id=1, status="missed", strategy=None)
        )
        row = _q(db, "SELECT status FROM negotiation_milestones WHERE id=1")
        assert row[0] == "met", "terminal milestone states must be immutable"


# ---- date helpers (codex finding 7) ----


def test_iso_lenient_read():
    assert _iso("2026-07-10") == date(2026, 7, 10)
    assert _iso("2026-07-10T12:00:00") == date(2026, 7, 10)
    assert _iso("2026-07-10 12:00") == date(2026, 7, 10)
    assert _iso("sometime") is None
    assert _iso(None) is None
    # codex loop-2 #5: a valid 10-char prefix on garbage must NOT parse
    assert _iso("2026-07-10garbage") is None


def test_valid_date_strict():
    assert _valid_date("2026-07-10", "--date") == "2026-07-10"
    # codex loop-2 #7: fromisoformat alone accepts 20260710 / week dates
    for bad in (
        "9999-not-a-date",
        "2026-7-1x",
        "morgen",
        "",
        "20260710",
        "2026-W28-1",
        "2026-02-30",
    ):
        try:
            _valid_date(bad, "--date")
            raise AssertionError(f"accepted {bad!r}")
        except SystemExit:
            pass


def test_migrate_widens_status_check():
    # live finding 2026-07-10: original table CHECKed status IN
    # (active|superseded|closed) — 'executing' INSERTs failed
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "deal.db")
        con = sqlite3.connect(db)
        con.executescript(
            BASE_DDL.replace(
                "status TEXT DEFAULT 'active'",
                "status TEXT DEFAULT 'active' "
                "CHECK(status IN ('active','superseded','closed'))",
            )
        )
        con.execute("INSERT INTO stakeholders VALUES (1,'T',NULL)")
        con.execute(
            "INSERT INTO negotiation_strategies (id, stakeholder_id, context_ref, status) "
            "VALUES (1,1,'X','closed')"
        )
        con.commit()
        con.close()
        negotiate_ops.cmd_migrate(Args(db))
        con = sqlite3.connect(db)
        con.execute(
            "INSERT INTO negotiation_strategies (id, stakeholder_id, context_ref, status) "
            "VALUES (2,1,'Y','executing')"
        )
        kept = con.execute(
            "SELECT status FROM negotiation_strategies WHERE id=1"
        ).fetchone()[0]
        con.close()
        assert kept == "closed", "rebuild must preserve existing rows"


def test_migrate_detects_malformed_preexisting_table():
    # codex loop-2 #4: right table name, wrong shape -> INCOMPLETE, not ok
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "deal.db")
        con = sqlite3.connect(db)
        con.executescript(BASE_DDL)
        con.execute(
            "CREATE TABLE strategy_parties (id INTEGER PRIMARY KEY, wrong TEXT)"
        )
        con.commit()
        con.close()
        try:
            negotiate_ops.cmd_migrate(Args(db))
            raise AssertionError("migration reported ok on malformed table")
        except SystemExit as e:
            assert "INCOMPLETE" in str(e)


# ---- offer ledger (SPEC-OFFER-NEGOTIATION-TAB §2-§4) ----


def _offer_args(db, **kw):
    kw.setdefault("action", "add")
    kw.setdefault("strategy", 1)
    kw.setdefault("side", "ours")
    kw.setdefault("date", "2026-07-01")
    kw.setdefault("label", "NBO v1")
    kw.setdefault("status", "sent")
    kw.setdefault("round_id", None)
    kw.setdefault("source_doc", "test.docx")
    kw.setdefault("note", None)
    kw.setdefault("term", [])
    kw.setdefault("id", None)
    return Args(db, **kw)


def test_migrate_creates_offer_tables_and_position_columns():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)  # migrated once by the helper
        negotiate_ops.cmd_migrate(Args(db))  # re-run must stay idempotent
        con = sqlite3.connect(db)
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        pos = {r[1] for r in con.execute("PRAGMA table_info(negotiation_positions)")}
        offers = {r[1] for r in con.execute("PRAGMA table_info(negotiation_offers)")}
        terms = {
            r[1] for r in con.execute("PRAGMA table_info(negotiation_offer_terms)")
        }
        con.close()
        assert {"negotiation_offers", "negotiation_offer_terms"} <= tables
        assert {"their_position", "prio"} <= pos
        assert {
            "strategy_id",
            "round_id",
            "side",
            "date",
            "label",
            "status",
            "source_doc",
            "note",
        } <= offers
        assert {
            "offer_id",
            "term_key",
            "label",
            "value_num",
            "unit",
            "value_text",
            "note",
        } <= terms


def test_offer_add_numeric_text_comma_thousands_terms():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        negotiate_ops.cmd_offer(
            _offer_args(
                db,
                term=[
                    "purchase_price_upfront=3.400|K",  # German thousands -> 3400
                    "earnout_multiple=2,75|x",  # comma decimal -> 2.75
                    "ev_total_max=5.957.500",  # multi-group thousands
                    "gf_salary=135|K p.a.|Tantieme offen",  # note segment
                    "earnout_threshold=EBIT > 625 p.a.",  # non-numeric -> text
                    "multiple=4.9",  # dot decimal -> 4.9
                ],
            )
        )
        con = sqlite3.connect(db)
        rows = {
            r[0]: r
            for r in con.execute(
                "SELECT term_key, value_num, value_text, unit, note "
                "FROM negotiation_offer_terms"
            )
        }
        con.close()
        assert rows["purchase_price_upfront"][1] == 3400.0
        assert rows["earnout_multiple"][1] == 2.75
        assert rows["ev_total_max"][1] == 5957500.0
        assert rows["gf_salary"][1] == 135.0
        assert rows["gf_salary"][3] == "K p.a."
        assert rows["gf_salary"][4] == "Tantieme offen"
        assert rows["earnout_threshold"][1] is None
        assert rows["earnout_threshold"][2] == "EBIT > 625 p.a."
        assert rows["multiple"][1] == 4.9


def test_offer_unknown_term_key_hard_error_no_partial_write():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        try:
            negotiate_ops.cmd_offer(_offer_args(db, term=["sofort=3400"]))
            raise AssertionError("unknown term_key was accepted")
        except SystemExit as e:
            assert "purchase_price_upfront" in str(e), "error must list valid keys"
        row = _q(db, "SELECT COUNT(*) FROM negotiation_offers")
        assert row[0] == 0, "a bad term must not leave a partial offer row"


def test_offer_other_requires_label():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        try:
            negotiate_ops.cmd_offer(_offer_args(db, term=["other=+1 MA"]))
            raise AssertionError("'other' without a label was accepted")
        except SystemExit as e:
            assert "label" in str(e)
        negotiate_ops.cmd_offer(_offer_args(db, term=["other:Kuendigungsschutz=+1 MA"]))
        row = _q(
            db,
            "SELECT label, value_text, value_num FROM negotiation_offer_terms "
            "WHERE term_key='other'",
        )
        assert row[0] == "Kuendigungsschutz"
        assert row[1] == "+1 MA" and row[2] is None


def test_offer_list_chronological_terms_inline():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        negotiate_ops.cmd_offer(
            _offer_args(
                db,
                date="2026-07-03",
                label="LOI v7",
                term=["purchase_price_upfront=3.400|K"],
            )
        )
        negotiate_ops.cmd_offer(
            _offer_args(
                db, date="2026-05-07", label="NBO", side="theirs", status="received"
            )
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            negotiate_ops.cmd_offer(_offer_args(db, action="list", strategy=1))
        text = out.getvalue()
        assert text.index("NBO") < text.index("LOI v7"), "list must be chronological"
        assert "purchase_price_upfront = 3400 K" in text, "terms must print inline"


def test_offer_signed_immutable():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        negotiate_ops.cmd_offer(_offer_args(db, status="signed", label="LOI signed"))
        negotiate_ops.cmd_offer(
            _offer_args(db, action="set-status", id=1, status="withdrawn")
        )
        row = _q(db, "SELECT status FROM negotiation_offers WHERE id=1")
        assert row[0] == "signed", "signed offers must be immutable"


def test_offer_set_status_transition_and_double_noop():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        negotiate_ops.cmd_offer(_offer_args(db))  # status=sent
        negotiate_ops.cmd_offer(
            _offer_args(db, action="set-status", id=1, status="superseded")
        )
        assert _q(db, "SELECT status FROM negotiation_offers WHERE id=1")[0] == (
            "superseded"
        )
        # superseded is terminal: a second transition must be a no-op
        negotiate_ops.cmd_offer(
            _offer_args(db, action="set-status", id=1, status="signed")
        )
        assert _q(db, "SELECT status FROM negotiation_offers WHERE id=1")[0] == (
            "superseded"
        )
        # and set-status must reject back-transitions to sent/received
        try:
            negotiate_ops.cmd_offer(
                _offer_args(db, action="set-status", id=1, status="sent")
            )
            raise AssertionError("set-status accepted 'sent'")
        except SystemExit:
            pass


def test_offer_add_rejects_lifecycle_status():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        try:
            negotiate_ops.cmd_offer(_offer_args(db, status="superseded"))
            raise AssertionError("offer add accepted a lifecycle-only status")
        except SystemExit:
            pass
        assert _q(db, "SELECT COUNT(*) FROM negotiation_offers")[0] == 0


def test_offer_add_via_main_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        negotiate_ops.main(
            [
                "--db",
                db,
                "offer",
                "add",
                "--strategy",
                "1",
                "--side",
                "ours",
                "--date",
                "2026-07-03",
                "--label",
                "LOI v7",
                "--status",
                "sent",
                "--term",
                "purchase_price_upfront=3.400|K",
                "--source-doc",
                "LOI_v7.docx",
            ]
        )
        row = _q(
            db,
            "SELECT value_num FROM negotiation_offer_terms "
            "WHERE term_key='purchase_price_upfront'",
        )
        assert row[0] == 3400.0


def test_offer_add_date_strict_via_main():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        try:
            negotiate_ops.main(
                [
                    "--db",
                    db,
                    "offer",
                    "add",
                    "--strategy",
                    "1",
                    "--side",
                    "ours",
                    "--date",
                    "07.05.2026",
                    "--label",
                    "NBO",
                    "--status",
                    "sent",
                ]
            )
            raise AssertionError("non-ISO offer date was accepted")
        except SystemExit:
            pass
        assert _q(db, "SELECT COUNT(*) FROM negotiation_offers")[0] == 0


# ---- position their_position / prio (SPEC-OFFER §4) ----


def test_position_their_position_prio_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        negotiate_ops.cmd_position(
            Args(
                db,
                action="add",
                strategy=1,
                term="Kaufpreis",
                preferred="3.400 K",
                fallback=None,
                walk_away=None,
                escalation=False,
                their_position="3.200 K fix",
                prio="high",
                id=None,
            )
        )
        row = _q(
            db, "SELECT their_position, prio FROM negotiation_positions WHERE id=1"
        )
        assert row[0] == "3.200 K fix" and row[1] == "high"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            negotiate_ops.cmd_position(Args(db, action="list", strategy=1))
        text = out.getvalue()
        assert "their pos: 3.200 K fix" in text
        assert "prio high" in text


def test_position_prio_validated_via_main():
    with tempfile.TemporaryDirectory() as tmp:
        db = make_db(tmp)
        seed(db)
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                negotiate_ops.main(
                    [
                        "--db",
                        db,
                        "position",
                        "add",
                        "--strategy",
                        "1",
                        "--term",
                        "T",
                        "--preferred",
                        "P",
                        "--prio",
                        "urgent",
                    ]
                )
            raise AssertionError("--prio urgent was accepted")
        except SystemExit:
            pass
        assert _q(db, "SELECT COUNT(*) FROM negotiation_positions")[0] == 0


if __name__ == "__main__":
    tests = [(n, fn) for n, fn in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
