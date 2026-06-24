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
    upstream_codes = {code_name for code_name, _, _ in rows if code_name}
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
        # Drop mirror rows for deals no longer present upstream — same transaction
        # as the upserts so the mirror exactly reflects the source set.
        existing_mirror = [
            r[0] for r in conn.execute("SELECT codename FROM deal_mirror").fetchall()
        ]
        for codename in existing_mirror:
            if codename not in upstream_codes:
                conn.execute("DELETE FROM deal_mirror WHERE codename=?", (codename,))
        # Auto-create M&A projects for deals without a matching workstream (§4.6)
        mna = conn.execute("SELECT id FROM spaces WHERE slug='mna'").fetchone()
        if mna:
            existing_deals = {
                r[0].lower()
                for r in conn.execute(
                    "SELECT deal_codename FROM workstreams WHERE deal_codename IS NOT NULL"
                ).fetchall()
            }
            existing_names = {
                r[0].lower()
                for r in conn.execute("SELECT name FROM workstreams").fetchall()
            }
            for code_name, stage, note in rows:
                if not code_name or code_name.lower() in existing_deals:
                    continue
                if code_name.lower() in existing_names:
                    conn.execute(
                        "UPDATE workstreams SET deal_codename=?, space_id=? "
                        "WHERE lower(name)=? AND deal_codename IS NULL",
                        (code_name, mna["id"], code_name.lower()),
                    )
                else:
                    conn.execute(
                        "INSERT INTO workstreams (name, space_id, deal_codename, status) "
                        "VALUES (?,?,?,?)",
                        (code_name, mna["id"], code_name, "active"),
                    )
                existing_deals.add(code_name.lower())
                existing_names.add(code_name.lower())
            # Linkage is via deal_codename; the workstream name is set only at
            # creation/linking above. Do NOT normalize names on every sync —
            # that clobbered manual renames.
        conn.commit()
    return {"ok": True, "count": len(rows), "error": None, "synced_at": now}


def last_synced_at(conn):
    row = conn.execute("SELECT MAX(synced_at) FROM deal_mirror").fetchone()
    return row[0] if row else None
