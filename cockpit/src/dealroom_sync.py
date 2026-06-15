"""deal_mirror sync: read-only pull of (code_name, deal_stage, status_note)
from dealroom.db. Mirror is upserted; cockpit never writes deal stage anywhere
else. Failures keep the stale mirror and report — never raise into the app."""

import logging
import os
from pathlib import Path

from . import db

log = logging.getLogger("cockpit.sync")


def dealroom_db_path():
    env = os.environ.get("COCKPIT_DEALROOM_DB")
    if env:
        return Path(env)
    # cockpit/ and dealroom/ are siblings in CLAUDE_REPURO
    return (
        Path(__file__).resolve().parent.parent.parent
        / "dealroom"
        / "data"
        / "dealroom.db"
    )


def sync_deal_mirror(conn):
    """Returns {'ok': bool, 'count': int, 'error': str|None, 'synced_at': str|None}."""
    src_path = dealroom_db_path()
    try:
        src = db.open_readonly(src_path)
        try:
            rows = src.execute(
                "SELECT code_name, deal_stage, status_note FROM deals"
            ).fetchall()
        finally:
            src.close()
    except Exception as exc:  # missing file, locked, bad schema — keep stale mirror
        log.warning("dealroom sync failed (%s): %s", src_path, exc)
        return {
            "ok": False,
            "count": 0,
            "error": str(exc),
            "synced_at": last_synced_at(conn),
        }

    now = db.now_iso()
    with db.WRITE_LOCK:
        for code_name, stage, note in rows:
            if not code_name:
                continue
            conn.execute(
                """INSERT INTO deal_mirror (codename, stage, note, synced_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(codename) DO UPDATE SET
                     stage=excluded.stage, note=excluded.note, synced_at=excluded.synced_at""",
                (code_name, stage, note, now),
            )
        conn.commit()
    return {"ok": True, "count": len(rows), "error": None, "synced_at": now}


def last_synced_at(conn):
    row = conn.execute("SELECT MAX(synced_at) FROM deal_mirror").fetchone()
    return row[0] if row else None
