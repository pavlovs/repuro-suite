# -*- coding: utf-8 -*-
"""Regression tests for negotiate_ops.py (SPEC §12). Codex 2026-07-10 findings
are encoded as named tests — the theme: watch silence must mean VERIFIED-quiet.
Runnable standalone (python test_negotiate_ops.py) or via pytest.
"""

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
