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
