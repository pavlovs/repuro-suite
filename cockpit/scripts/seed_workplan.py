"""Seed the cockpit from the workplan xlsx — ALL rows land as staging=1 /
source='seed-v1' (greyed in UI, excluded from colors and recommendations until
curated, DESIGN-SPEC §7). Idempotent: re-run deletes prior seed-v1 rows first.
openpyxl is read-only here (house rule: never write xlsx with it)."""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db  # noqa: E402

SOURCE_TAG = "seed-v1"
DEFAULT_XLSX = (
    Path.home()
    / "Documents"
    / "OneDrive - Kamu Kapital"
    / "Dokumente - Kamu Kapital"
    / "General"
    / "01_Workplan"
    / "260312_Repuro_Workplan_v1.xlsx"
)
GENERAL_DELIVERABLE = "(general)"


def _iso(value):
    if value is None or value == "":
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None  # unparseable deadline -> keep task, drop date


def _priority(value):
    return {"high": "high", "medium": "med", "low": "low"}.get(
        str(value or "").strip().lower()
    )


def seed(conn, xlsx_path=None):
    import openpyxl  # local import: only this script needs it

    path = Path(xlsx_path or os.environ.get("COCKPIT_WORKPLAN_XLSX") or DEFAULT_XLSX)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Workplan"]

    rows = []
    header_seen = False
    for row in ws.iter_rows(min_col=2, max_col=8, values_only=True):
        workstream, deliverable, activity, deadline, responsible, priority, comment = (
            row
        )
        if not header_seen:
            if workstream == "Workstream":
                header_seen = True
            continue
        if not workstream or not str(workstream).strip():
            continue
        rows.append(
            {
                "workstream": str(workstream).strip(),
                "deliverable": str(deliverable).strip() if deliverable else None,
                "activity": str(activity).strip() if activity else None,
                "deadline": _iso(deadline),
                "responsible": str(responsible).strip() if responsible else None,
                "priority": _priority(priority),
                "comment": str(comment).strip() if comment else None,
            }
        )
    wb.close()
    if not header_seen:
        raise SystemExit("header row ('Workstream'...) not found in sheet 'Workplan'")

    now = db.now_iso()
    counts = {"workstreams": 0, "deliverables": 0, "tasks": 0, "skipped": 0}
    with db.WRITE_LOCK:
        # idempotency: wipe previous seed
        conn.execute("DELETE FROM tasks WHERE source=?", (SOURCE_TAG,))
        conn.execute(
            "DELETE FROM deliverables WHERE source=? AND id NOT IN "
            "(SELECT DISTINCT deliverable_id FROM tasks WHERE deliverable_id IS NOT NULL)",
            (SOURCE_TAG,),
        )

        ws_ids, deliv_ids = {}, {}
        for r in rows:
            ws_name = r["workstream"]
            if ws_name not in ws_ids:
                row_db = conn.execute(
                    "SELECT id FROM workstreams WHERE name=?", (ws_name,)
                ).fetchone()
                if row_db:
                    ws_ids[ws_name] = row_db["id"]
                else:
                    cur = conn.execute(
                        "INSERT INTO workstreams (name, sort_order) VALUES (?, ?)",
                        (ws_name, len(ws_ids)),
                    )
                    ws_ids[ws_name] = cur.lastrowid
                    counts["workstreams"] += 1
            if not r["activity"]:  # workstream registered, but no task/deliverable
                counts["skipped"] += 1
                continue
            d_name = r["deliverable"] or GENERAL_DELIVERABLE
            d_key = (ws_name, d_name)
            if d_key not in deliv_ids:
                row_db = conn.execute(
                    "SELECT id FROM deliverables WHERE workstream_id=? AND name=?",
                    (ws_ids[ws_name], d_name),
                ).fetchone()
                if row_db:
                    deliv_ids[d_key] = row_db["id"]
                else:
                    cur = conn.execute(
                        "INSERT INTO deliverables (workstream_id, name, staging, source,"
                        " sort_order) VALUES (?,?,1,?,?)",
                        (ws_ids[ws_name], d_name, SOURCE_TAG, len(deliv_ids)),
                    )
                    deliv_ids[d_key] = cur.lastrowid
                    counts["deliverables"] += 1
            conn.execute(
                "INSERT INTO tasks (deliverable_id, kind, text, deadline, responsible,"
                " priority, detail, staging, source, prereqs, tags, links, created_by,"
                " created_at, updated_at, last_touched_at)"
                " VALUES (?,?,?,?,?,?,?,1,?,'[]','[]','[]','seed',?,?,?)",
                (
                    deliv_ids[d_key],
                    "workplan",
                    r["activity"],
                    r["deadline"],
                    r["responsible"],
                    r["priority"],
                    r["comment"],
                    SOURCE_TAG,
                    now,
                    now,
                    now,
                ),
            )
            counts["tasks"] += 1
        db.audit(conn, "seed", "seed_workplan", SOURCE_TAG, after=counts)
        conn.commit()
    return counts


if __name__ == "__main__":
    counts = seed(db.get_conn(), sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(counts))
