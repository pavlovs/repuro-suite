import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.dealroom_sync import sync_deal_mirror
from tests.conftest import make_fixture_dealroom


def test_sync_upserts(cockpit_db, tmp_path, monkeypatch):
    result = sync_deal_mirror(cockpit_db)
    assert result["ok"] and result["count"] == 3
    rows = {r["codename"]: r for r in cockpit_db.execute("SELECT * FROM deal_mirror")}
    assert rows["Fox"]["stage"] == "loi_signed"
    assert rows["Fox"]["note"] == "DD running"
    assert rows["Octopus"]["owner_mode"] == "legacy"  # default preserved

    # stage change in source -> mirror updates, owner_mode untouched
    cockpit_db.execute(
        "UPDATE deal_mirror SET owner_mode='cockpit-owned' WHERE codename='Fox'"
    )
    cockpit_db.commit()
    dealroom2 = tmp_path / "dealroom2.db"
    make_fixture_dealroom(dealroom2, deals=[("Fox", "dd", "moving")])
    monkeypatch.setenv("COCKPIT_DEALROOM_DB", str(dealroom2))
    result = sync_deal_mirror(cockpit_db)
    assert result["ok"]
    row = cockpit_db.execute(
        "SELECT * FROM deal_mirror WHERE codename='Fox'"
    ).fetchone()
    assert row["stage"] == "dd" and row["owner_mode"] == "cockpit-owned"


def test_sync_missing_file_keeps_stale_mirror(cockpit_db, monkeypatch, tmp_path):
    sync_deal_mirror(cockpit_db)
    monkeypatch.setenv("COCKPIT_DEALROOM_DB", str(tmp_path / "nope.db"))
    result = sync_deal_mirror(cockpit_db)
    assert not result["ok"] and result["error"]
    # stale mirror retained, and no empty db was created at the wrong path
    n = cockpit_db.execute("SELECT COUNT(*) FROM deal_mirror").fetchone()[0]
    assert n == 3
    assert not (tmp_path / "nope.db").exists()


def test_sync_deletes_mirror_rows_absent_upstream(cockpit_db, tmp_path, monkeypatch):
    """Finding 6: a deal removed upstream must be removed from deal_mirror."""
    sync_deal_mirror(cockpit_db)
    n0 = cockpit_db.execute("SELECT COUNT(*) FROM deal_mirror").fetchone()[0]
    assert n0 == 3

    dealroom2 = tmp_path / "dealroom2.db"
    make_fixture_dealroom(dealroom2, deals=[("Fox", "dd", "still here")])
    monkeypatch.setenv("COCKPIT_DEALROOM_DB", str(dealroom2))
    sync_deal_mirror(cockpit_db)

    rows = {r["codename"] for r in cockpit_db.execute("SELECT * FROM deal_mirror")}
    assert rows == {"Fox"}  # Octopus + Cat dropped


def test_sync_preserves_manual_workstream_rename(cockpit_db, tmp_path, monkeypatch):
    """Finding 7: a manually renamed deal-linked workstream must not be clobbered
    back to the codename on the next sync."""
    sync_deal_mirror(cockpit_db)  # auto-creates Fox/Cat workstreams
    cockpit_db.execute(
        "UPDATE workstreams SET name='Project Fox — DD' WHERE deal_codename='Fox'"
    )
    cockpit_db.commit()

    dealroom2 = tmp_path / "dealroom2.db"
    make_fixture_dealroom(dealroom2, deals=[("Fox", "dd", "moving")])
    monkeypatch.setenv("COCKPIT_DEALROOM_DB", str(dealroom2))
    sync_deal_mirror(cockpit_db)

    name = cockpit_db.execute(
        "SELECT name FROM workstreams WHERE deal_codename='Fox'"
    ).fetchone()[0]
    assert name == "Project Fox — DD"  # manual name survived


def test_patch_deal_rejected_mirror_is_readonly(client):
    """Finding 5: deal stage/note are mastered by DEALRoom; cockpit must refuse
    the mirror write (it would be lost on the next sync) with a clear error."""
    r = client.patch(
        "/api/deal/Fox",
        json={"stage": "spa"},
        headers={"Authorization": "Bearer test-token-rd"},
    )
    assert r.status_code == 409, r.text
    # Mirror unchanged (still the synced value).
    row = client.cockpit_conn.execute(
        "SELECT stage FROM deal_mirror WHERE codename='Fox'"
    ).fetchone()
    assert row["stage"] == "loi_signed"


def test_require_db_fails_fast_when_missing(tmp_path, monkeypatch):
    """Finding 8: with COCKPIT_REQUIRE_DB set, a missing DB path must raise
    instead of silently creating a fresh master DB."""
    db.close_conn()
    monkeypatch.setenv("COCKPIT_DB", str(tmp_path / "does-not-exist.db"))
    monkeypatch.setenv("COCKPIT_REQUIRE_DB", "1")
    try:
        raised = False
        try:
            db.get_conn()
        except RuntimeError:
            raised = True
        assert raised, "expected RuntimeError on missing DB with COCKPIT_REQUIRE_DB"
        assert not (tmp_path / "does-not-exist.db").exists()
    finally:
        monkeypatch.delenv("COCKPIT_REQUIRE_DB", raising=False)
        db.close_conn()


def test_open_readonly_rejects_writes(cockpit_db, tmp_path):
    make_fixture_dealroom(tmp_path / "ro.db")
    conn = db.open_readonly(tmp_path / "ro.db")
    import sqlite3

    try:
        conn.execute("INSERT INTO deals (code_name) VALUES ('X')")
        assert False, "write went through on a read-only handle"
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()
