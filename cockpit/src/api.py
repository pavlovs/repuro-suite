"""FastAPI app: state assembly with computed fields, task/workstream/deliverable
mutations (version-checked, audited), agent queue with leases, MD import/export,
dealroom mirror sync. Single-process; writes serialized via db.WRITE_LOCK."""

import asyncio
import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

from . import compute, db, dealroom_sync, mdio, models


# --------------------------------------------------------------------------
# app / lifespan
@asynccontextmanager
async def lifespan(app):
    conn = db.get_conn()  # migration runs inside get_conn on schema_v mismatch
    dealroom_sync.sync_deal_mirror(conn)  # tolerant — logs and keeps stale mirror
    interval = int(os.environ.get("COCKPIT_SYNC_INTERVAL", "0"))
    task = asyncio.create_task(_sync_loop(interval)) if interval > 0 else None
    yield
    if task:
        task.cancel()


async def _sync_loop(interval):
    while True:
        await asyncio.sleep(interval)
        dealroom_sync.sync_deal_mirror(db.get_conn())


app = FastAPI(title="Repuro Cockpit", version="0.1.0", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static")),
    name="static",
)


# --------------------------------------------------------------------------
# auth
_CADDY_USER_MAP = {"roman": "rd", "florian": "ff"}


def principal(
    authorization: str | None = Header(default=None),
    x_remote_user: str | None = Header(default=None),
):
    if x_remote_user and x_remote_user in _CADDY_USER_MAP:
        pid = _CADDY_USER_MAP[x_remote_user]
        row = (
            db.get_conn()
            .execute("SELECT id, role FROM users WHERE id = ?", (pid,))
            .fetchone()
        )
        if row:
            return {"id": row["id"], "role": row["role"]}
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token_hash = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    row = (
        db.get_conn()
        .execute("SELECT id, role FROM users WHERE token_hash = ?", (token_hash,))
        .fetchone()
    )
    if not row:
        raise HTTPException(401, "unknown token")
    return {"id": row["id"], "role": row["role"]}


def human_only(p=Depends(principal)):
    if p["role"] != "human":
        raise HTTPException(403, "requires a human principal")
    return p


def agent_only(p=Depends(principal)):
    if p["role"] != "agent":
        raise HTTPException(403, "requires an agent principal")
    return p


# --------------------------------------------------------------------------
# helpers
def _today():
    return (
        date.fromisoformat(os.environ["COCKPIT_TODAY"])
        if os.environ.get("COCKPIT_TODAY")
        else date.today()
    )


def _task_json(row, computed):
    t = {k: row[k] for k in row.keys()}
    t["id"] = models.task_id(row["id"])
    t["deliverable_id"] = (
        models.deliv_id(row["deliverable_id"]) if row["deliverable_id"] else None
    )
    for k in ("prereqs", "tags", "links"):
        t[k] = json.loads(row[k])
    t["pinned_today"] = bool(row["pinned_today"])
    t["staging"] = bool(row["staging"])
    t["sort_order"] = row["sort_order"] if "sort_order" in row.keys() else 0
    t["computed"] = computed
    return t


def _reap_expired_claims(conn):
    now = db.now_iso()
    with db.WRITE_LOCK:
        rows = conn.execute(
            "SELECT id FROM tasks WHERE claimed_by IS NOT NULL AND claim_expires_at < ? "
            "AND status = 'in_progress'",
            (now,),
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL, status='open', "
                "version=version+1, updated_at=? WHERE id=?",
                (now, r["id"]),
            )
            db.audit(conn, "system", "lease_expired", models.task_id(r["id"]))
        if rows:
            conn.commit()


def _mirror_status(deal_codename, mirror):
    if not deal_codename:
        return None
    deal = mirror.get(deal_codename)
    if not deal or not deal["synced_at"]:
        return "missing"
    try:
        synced = datetime.fromisoformat(deal["synced_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - synced).total_seconds() > 86400:
            return "stale"
    except (ValueError, TypeError):
        return "stale"
    return "ok"


def assemble_state(conn):
    _reap_expired_claims(conn)
    today = _today()
    space_rows = conn.execute("SELECT * FROM spaces ORDER BY sort_order").fetchall()
    ws_rows = conn.execute(
        "SELECT * FROM workstreams ORDER BY sort_order, id"
    ).fetchall()
    d_rows = conn.execute(
        "SELECT * FROM deliverables ORDER BY sort_order, id"
    ).fetchall()
    t_rows = conn.execute("SELECT * FROM tasks ORDER BY sort_order, id").fetchall()
    mirror = {r["codename"]: r for r in conn.execute("SELECT * FROM deal_mirror")}

    deliv_by_id = {r["id"]: r for r in d_rows}
    # prereq status resolver — staging entities resolve to None (excluded, fail-visible)
    task_status = {
        models.task_id(r["id"]): (None if r["staging"] else r["status"]) for r in t_rows
    }
    deliv_status = {}
    for r in d_rows:
        st = (
            None
            if r["staging"]
            else ("done" if r["status"] in ("done", "dropped") else "open")
        )
        if st == "open":
            live = [
                t for t in t_rows if t["deliverable_id"] == r["id"] and not t["staging"]
            ]
            if live and all(t["status"] == "done" for t in live):
                st = "done"
        deliv_status[models.deliv_id(r["id"])] = st
    status_of = {**task_status, **deliv_status}.get

    due_soon_prereqs = set()
    horizon = today + timedelta(days=14)
    for r in t_rows:
        if r["staging"] or r["status"] == "done":
            continue
        eff = compute.effective_deadline(
            r["deadline"],
            deliv_by_id[r["deliverable_id"]]["target_date"]
            if r["deliverable_id"]
            else None,
        )
        if eff and date.fromisoformat(eff) <= horizon:
            for p in json.loads(r["prereqs"]):
                due_soon_prereqs.add(p["ref"])

    tasks_json = {}
    for r in t_rows:
        eff = compute.effective_deadline(
            r["deadline"],
            deliv_by_id[r["deliverable_id"]]["target_date"]
            if r["deliverable_id"]
            else None,
        )
        if r["staging"]:
            computed = {
                "effective_deadline": eff,
                "readiness": None,
                "risks": [],
                "recommendation": None,
            }
        else:
            rd = compute.readiness(json.loads(r["prereqs"]), status_of)
            risks = compute.schedule_risk(
                eff, rd, r["status"], r["next_chase_date"], today
            )
            rec = (
                None
                if r["status"] == "done"
                else compute.recommendation(
                    r["status"],
                    eff,
                    bool(r["pinned_today"]),
                    r["next_chase_date"],
                    r["expected_back_by"],
                    models.task_id(r["id"]) in due_soon_prereqs,
                    today,
                )
            )
            computed = {
                "effective_deadline": eff,
                "readiness": rd,
                "risks": risks,
                "recommendation": rec,
            }
        tasks_json[r["id"]] = _task_json(r, computed)

    deliverables_json = {}
    for r in d_rows:
        children = [
            tasks_json[t["id"]] for t in t_rows if t["deliverable_id"] == r["id"]
        ]
        children.sort(
            key=lambda c: (
                c.get("sort_order", 0),
                c["computed"]["effective_deadline"] is None,
                c["computed"]["effective_deadline"] or "",
                c["id"],
            )
        )
        open_rd = [
            c["computed"]["readiness"]
            for c in children
            if c["computed"]["readiness"] and c["status"] != "done"
        ]
        rollup_rd, rollup_risks = compute.deliverable_rollup(
            open_rd, r["target_date"], today
        )
        deliverables_json[r["id"]] = {
            "id": models.deliv_id(r["id"]),
            "workstream_id": models.ws_id(r["workstream_id"]),
            "name": r["name"],
            "target_date": r["target_date"],
            "deal": r["deal"],
            "status": r["status"],
            "comment": r["comment"],
            "staging": bool(r["staging"]),
            "version": r["version"],
            "tasks": children,
            "computed": {
                "readiness": None if r["staging"] else rollup_rd,
                "risks": [] if r["staging"] else rollup_risks,
                "progress": {
                    "done": sum(1 for c in children if c["status"] == "done"),
                    "total": len(children),
                },
            },
        }

    # Build workstreams grouped by space
    ws_by_space = {}
    for r in ws_rows:
        deal = mirror.get(r["deal_codename"]) if r["deal_codename"] else None
        deal_stage = deal["stage"] if deal else None
        ws_json = {
            "id": models.ws_id(r["id"]),
            "name": r["name"],
            "space_id": models.space_id(r["space_id"]),
            "status": r["status"],
            "color": r["color"],
            "sort_order": r["sort_order"],
            "deal_codename": r["deal_codename"],
            "deal_stage": deal_stage,
            "deal_mirror_status": _mirror_status(r["deal_codename"], mirror),
            "version": r["version"],
            "deal": (
                {
                    "codename": deal["codename"],
                    "stage": deal["stage"],
                    "note": deal["note"],
                    "owner_mode": deal["owner_mode"],
                }
                if deal
                else None
            ),
            "deliverables": [
                deliverables_json[d["id"]]
                for d in d_rows
                if d["workstream_id"] == r["id"]
            ],
        }
        ws_by_space.setdefault(r["space_id"], []).append(ws_json)

    spaces_json = []
    for s in space_rows:
        ws_list = ws_by_space.get(s["id"], [])
        if s["sort_mode"] == "deal_stage":
            ws_list.sort(
                key=lambda w: (
                    1 if not w["deal_codename"] else 0,
                    -compute.stage_weight(w["deal_stage"]),
                    w["sort_order"],
                )
            )
            for w in ws_list:
                w["visibility"] = compute.deal_visibility(
                    w["deal_codename"], w["deal_stage"]
                )
        else:
            for w in ws_list:
                w["visibility"] = None

        spaces_json.append(
            {
                "id": models.space_id(s["id"]),
                "name": s["name"],
                "slug": s["slug"],
                "color": s["color"],
                "icon": s["icon"],
                "sort_order": s["sort_order"],
                "sort_mode": s["sort_mode"],
                "status": s["status"],
                "version": s["version"],
                "workstreams": ws_list,
            }
        )

    return {
        "spaces": spaces_json,
        "standalone_tasks": [
            tasks_json[r["id"]] for r in t_rows if not r["deliverable_id"]
        ],
        "deals": [{k: r[k] for k in r.keys()} for r in mirror.values()],
        "meta": {
            "today": today.isoformat(),
            "mirror_synced_at": dealroom_sync.last_synced_at(conn),
            "counts": {
                "workstreams": len(ws_rows),
                "deliverables": len(d_rows),
                "tasks": len(t_rows),
                "staging_tasks": sum(1 for r in t_rows if r["staging"]),
            },
        },
    }


# --------------------------------------------------------------------------
# generic mutation helpers
_TASK_FIELDS = {
    "deliverable_id",
    "kind",
    "text",
    "detail",
    "deadline",
    "responsible",
    "priority",
    "status",
    "waiting_on_party",
    "waiting_on_type",
    "next_chase_date",
    "expected_back_by",
    "execution",
    "runner",
    "acceptance_criteria",
    "prereqs",
    "tags",
    "links",
    "deal",
    "pinned_today",
    "staging",
    "source",
    "evidence",
    "input_from",
    "input_question",
}
_TASK_ENUMS = {
    "kind": models.KINDS,
    "status": models.STATUSES,
    "priority": models.PRIORITIES,
    "execution": models.EXECUTIONS,
    "runner": models.RUNNERS,
    "waiting_on_type": models.WAITING_TYPES,
    "input_from": {"RD", "FF"},
}


def _validate_date(fields, key):
    value = fields.get(key)
    if value is not None:
        try:
            date.fromisoformat(str(value))
        except ValueError:
            # one malformed date stored would 500 every later /api/state call
            raise HTTPException(422, f"{key} must be YYYY-MM-DD, got {value!r}")


def _validate_task_fields(conn, fields):
    for key, allowed in _TASK_ENUMS.items():
        if fields.get(key) is not None and fields[key] not in allowed:
            raise HTTPException(422, f"invalid {key}: {fields[key]!r}")
    for key in ("deadline", "next_chase_date", "expected_back_by"):
        _validate_date(fields, key)
    if "prereqs" in fields:
        for p in fields["prereqs"] or []:
            if p.get("hardness", "hard") not in models.HARDNESS:
                raise HTTPException(422, f"invalid hardness in prereq {p}")
            prefix, num = _safe_ref(p.get("ref", ""))
            table = "tasks" if prefix == "t" else "deliverables"
            if (
                prefix == "w"
                or not conn.execute(
                    f"SELECT 1 FROM {table} WHERE id=?", (num,)
                ).fetchone()
            ):
                raise HTTPException(422, f"prereq ref not found: {p.get('ref')!r}")
    if fields.get("deliverable_id") is not None:
        if not conn.execute(
            "SELECT 1 FROM deliverables WHERE id=?", (fields["deliverable_id"],)
        ).fetchone():
            raise HTTPException(422, "deliverable not found")
    if fields.get("execution") in models.AGENT_EXECUTIONS and not fields.get(
        "acceptance_criteria"
    ):
        raise HTTPException(422, "acceptance_criteria required for agent execution")
    if fields.get("input_from") and not (fields.get("input_question") or "").strip():
        raise HTTPException(422, "input_question required when input_from is set")


def _safe_ref(ref):
    try:
        return models.parse_ref(ref)
    except ValueError:
        raise HTTPException(422, f"bad ref: {ref!r}")


def _tid(tid_str):
    prefix, num = _safe_ref(tid_str)
    if prefix != "t":
        raise HTTPException(422, f"expected task id t-<n>, got {tid_str!r}")
    return num


def _get_task(conn, num):
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (num,)).fetchone()
    if not row:
        raise HTTPException(404, f"task t-{num} not found")
    return row


def _insert_task(conn, actor, fields):
    """Caller validated. Returns new integer id."""
    now = db.now_iso()
    cols = {
        "kind": "workplan",
        "prereqs": "[]",
        "tags": "[]",
        "links": "[]",
        "status": "open",
        "execution": "me",
        "pinned_today": 0,
        "staging": 0,
    }
    cols.update(
        {k: v for k, v in fields.items() if k in _TASK_FIELDS and v is not None}
    )
    for jkey in ("prereqs", "tags", "links"):
        if not isinstance(cols[jkey], str):
            cols[jkey] = json.dumps(cols[jkey])
    cols["pinned_today"] = int(bool(cols["pinned_today"]))
    cols["staging"] = int(bool(cols["staging"]))
    cols.update(
        {
            "created_by": actor,
            "created_at": now,
            "updated_at": now,
            "last_touched_at": now,
        }
    )
    names = ", ".join(cols)
    cur = conn.execute(
        f"INSERT INTO tasks ({names}) VALUES ({','.join('?' * len(cols))})",
        tuple(cols.values()),
    )
    db.audit(conn, actor, "task_create", models.task_id(cur.lastrowid), after=cols)
    return cur.lastrowid


def _update_task(conn, actor, num, fields, expected_version=None, action="task_update"):
    row = _get_task(conn, num)
    if expected_version is not None and row["version"] != expected_version:
        raise HTTPException(
            409, detail={"error": "version conflict", "current": _task_json(row, {})}
        )
    now = db.now_iso()
    updates = {k: v for k, v in fields.items() if k in _TASK_FIELDS}
    for jkey in ("prereqs", "tags", "links"):
        if jkey in updates and not isinstance(updates[jkey], str):
            updates[jkey] = json.dumps(updates[jkey])
    if "pinned_today" in updates:
        updates["pinned_today"] = int(bool(updates["pinned_today"]))
    if updates.get("status") == "done" and row["status"] != "done":
        updates["done_at"] = now
    updates.update({"updated_at": now, "last_touched_at": now})
    setters = ", ".join(f"{k}=?" for k in updates) + ", version=version+1"
    conn.execute(f"UPDATE tasks SET {setters} WHERE id=?", (*updates.values(), num))
    before = {k: row[k] for k in fields if k in row.keys()}
    db.audit(conn, actor, action, models.task_id(num), before=before, after=fields)
    return conn.execute("SELECT * FROM tasks WHERE id=?", (num,)).fetchone()


# --------------------------------------------------------------------------
# routes
_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC, "index.html"), media_type="text/html")


@app.get("/api/health")
def health():
    conn = db.get_conn()
    return {
        "status": "ok",
        "db": str(db.default_db_path().name),
        "mirror_synced_at": dealroom_sync.last_synced_at(conn),
    }


@app.get("/api/state")
def state(p=Depends(principal)):
    s = assemble_state(db.get_conn())
    s["principal"] = p
    return s


@app.post("/api/task", status_code=201)
def create_task(payload: dict = Body(...), p=Depends(principal)):
    conn = db.get_conn()
    if not payload.get("text"):
        raise HTTPException(422, "text is required")
    if payload.get("deliverable_id"):
        prefix, num = _safe_ref(payload["deliverable_id"])
        if prefix != "d":
            raise HTTPException(422, "deliverable_id must be d-<n>")
        payload["deliverable_id"] = num
    _validate_task_fields(conn, payload)
    with db.WRITE_LOCK:
        new_id = _insert_task(conn, p["id"], payload)
        conn.commit()
    return assemble_task(conn, new_id)


def assemble_task(conn, num):
    """Single-task view with computed fields, via full state (simple > clever at this scale)."""
    st = assemble_state(conn)
    wanted = models.task_id(num)
    for t in st["standalone_tasks"]:
        if t["id"] == wanted:
            return t
    for space in st["spaces"]:
        for ws in space["workstreams"]:
            for d in ws["deliverables"]:
                for t in d["tasks"]:
                    if t["id"] == wanted:
                        return t
    raise HTTPException(404, f"{wanted} not found")


@app.patch("/api/task/{tid}")
def patch_task(tid: str, payload: dict = Body(...), p=Depends(principal)):
    conn = db.get_conn()
    num = _tid(tid)
    if "version" not in payload:
        raise HTTPException(422, "version is required on updates")
    version = payload.pop("version")
    if payload.get("deliverable_id"):
        prefix, dnum = _safe_ref(payload["deliverable_id"])
        if prefix != "d":
            raise HTTPException(422, "deliverable_id must be d-<n>")
        payload["deliverable_id"] = dnum
    _validate_task_fields(conn, payload)
    with db.WRITE_LOCK:
        _update_task(conn, p["id"], num, payload, expected_version=version)
        conn.commit()
    return assemble_task(conn, num)


@app.post("/api/workstream", status_code=201)
def create_workstream(payload: dict = Body(...), p=Depends(principal)):
    conn = db.get_conn()
    if not payload.get("name"):
        raise HTTPException(422, "name is required")
    if not payload.get("space_id"):
        raise HTTPException(422, "space_id is required")
    prefix, snum = _safe_ref(payload["space_id"])
    if prefix != "s":
        raise HTTPException(422, "space_id must be s-<n>")
    if not conn.execute("SELECT 1 FROM spaces WHERE id=?", (snum,)).fetchone():
        raise HTTPException(422, "space not found")
    if payload.get("status") and payload["status"] not in models.WS_STATUSES:
        raise HTTPException(422, "invalid status")
    with db.WRITE_LOCK:
        try:
            cur = conn.execute(
                "INSERT INTO workstreams (name, space_id, color, sort_order, status, deal_codename) "
                "VALUES (?,?,?,?,?,?)",
                (
                    payload["name"],
                    snum,
                    payload.get("color"),
                    payload.get("sort_order", 0),
                    payload.get("status", "active"),
                    payload.get("deal_codename"),
                ),
            )
        except Exception:
            raise HTTPException(
                422, f"workstream {payload['name']!r} already exists in this space"
            )
        db.audit(
            conn,
            p["id"],
            "workstream_create",
            models.ws_id(cur.lastrowid),
            after=payload,
        )
        conn.commit()
    return {"id": models.ws_id(cur.lastrowid), "version": 1}


@app.patch("/api/workstream/{wid}")
def patch_workstream(wid: str, payload: dict = Body(...), p=Depends(principal)):
    conn = db.get_conn()
    if "space_id" in payload:
        prefix, snum = _safe_ref(payload["space_id"])
        if prefix != "s":
            raise HTTPException(422, "space_id must be s-<n>")
        if not conn.execute("SELECT 1 FROM spaces WHERE id=?", (snum,)).fetchone():
            raise HTTPException(422, "space not found")
        payload["space_id"] = snum
    return _patch_simple(
        wid,
        "w",
        "workstreams",
        payload,
        p,
        {"name", "color", "sort_order", "status", "deal_codename", "space_id"},
        {"status": models.WS_STATUSES},
    )


@app.post("/api/deliverable", status_code=201)
def create_deliverable(payload: dict = Body(...), p=Depends(principal)):
    conn = db.get_conn()
    if not payload.get("name") or not payload.get("workstream_id"):
        raise HTTPException(422, "name and workstream_id are required")
    prefix, wnum = _safe_ref(payload["workstream_id"])
    if prefix != "w":
        raise HTTPException(422, "workstream_id must be w-<n>")
    ws_row = conn.execute("SELECT * FROM workstreams WHERE id=?", (wnum,)).fetchone()
    if not ws_row:
        raise HTTPException(422, "workstream not found")
    if payload.get("status") and payload["status"] not in models.DELIV_STATUSES:
        raise HTTPException(422, "invalid status")
    _validate_date(payload, "target_date")
    deal = payload.get("deal") or ws_row["deal_codename"]
    with db.WRITE_LOCK:
        cur = conn.execute(
            "INSERT INTO deliverables (workstream_id, name, target_date, status, sort_order,"
            " comment, staging, source, deal) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                wnum,
                payload["name"],
                payload.get("target_date"),
                payload.get("status", "open"),
                payload.get("sort_order", 0),
                payload.get("comment"),
                int(bool(payload.get("staging", 0))),
                payload.get("source"),
                deal,
            ),
        )
        db.audit(
            conn,
            p["id"],
            "deliverable_create",
            models.deliv_id(cur.lastrowid),
            after=payload,
        )
        conn.commit()
    return {"id": models.deliv_id(cur.lastrowid), "version": 1}


@app.patch("/api/deliverable/{did}")
def patch_deliverable(did: str, payload: dict = Body(...), p=Depends(principal)):
    conn = db.get_conn()
    # workstream_id needs FK validation before the generic patch path
    if "workstream_id" in payload:
        ws_raw = payload["workstream_id"]
        try:
            prefix, wnum = models.parse_ref(ws_raw)
        except ValueError:
            raise HTTPException(422, f"bad workstream_id: {ws_raw!r}")
        if (
            prefix != "w"
            or not conn.execute(
                "SELECT 1 FROM workstreams WHERE id=?", (wnum,)
            ).fetchone()
        ):
            raise HTTPException(422, "workstream not found")
        payload["workstream_id"] = wnum
    return _patch_simple(
        did,
        "d",
        "deliverables",
        payload,
        p,
        {
            "name",
            "target_date",
            "status",
            "sort_order",
            "comment",
            "staging",
            "workstream_id",
        },
        {"status": models.DELIV_STATUSES},
    )


@app.delete("/api/deliverable/{did}")
def delete_deliverable(did: str, p=Depends(human_only)):
    conn = db.get_conn()
    prefix, num = _safe_ref(did)
    if prefix != "d":
        raise HTTPException(422, "expected d-<n>")
    row = conn.execute("SELECT * FROM deliverables WHERE id=?", (num,)).fetchone()
    if not row:
        raise HTTPException(404, f"{did} not found")
    ref = models.deliv_id(num)
    with db.WRITE_LOCK:
        conn.execute(
            "UPDATE tasks SET deliverable_id=NULL, updated_at=? WHERE deliverable_id=?",
            (db.now_iso(), num),
        )
        conn.execute("DELETE FROM deliverables WHERE id=?", (num,))
        db.audit(
            conn,
            p["id"],
            "deliverable_delete",
            ref,
            before={k: row[k] for k in row.keys()},
        )
        conn.commit()
    return {"deleted": ref}


def _patch_simple(id_str, want_prefix, table, payload, p, allowed, enums):
    conn = db.get_conn()
    prefix, num = _safe_ref(id_str)
    if prefix != want_prefix:
        raise HTTPException(422, f"expected {want_prefix}-<n>")
    if "version" not in payload:
        raise HTTPException(422, "version is required on updates")
    version = payload.pop("version")
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (num,)).fetchone()
    if not row:
        raise HTTPException(404, f"{id_str} not found")
    if row["version"] != version:
        raise HTTPException(
            409, detail={"error": "version conflict", "current_version": row["version"]}
        )
    updates = {k: v for k, v in payload.items() if k in allowed}
    for key, allowed_vals in enums.items():
        if updates.get(key) is not None and updates[key] not in allowed_vals:
            raise HTTPException(422, f"invalid {key}")
    if "staging" in updates:
        updates["staging"] = int(bool(updates["staging"]))
    _validate_date(updates, "target_date")
    if not updates:
        raise HTTPException(422, "no recognized fields")
    with db.WRITE_LOCK:
        setters = ", ".join(f"{k}=?" for k in updates) + ", version=version+1"
        conn.execute(
            f"UPDATE {table} SET {setters} WHERE id=?", (*updates.values(), num)
        )
        db.audit(
            conn,
            p["id"],
            f"{table[:-1]}_update",
            id_str,
            before={k: row[k] for k in updates},
            after=updates,
        )
        conn.commit()
    return {"id": id_str, "version": version + 1}


# --------------------------------------------------------------------------
# agent queue
@app.get("/api/agent/queue")
def agent_queue(p=Depends(principal)):
    conn = db.get_conn()
    _reap_expired_claims(conn)
    rows = conn.execute(
        "SELECT * FROM tasks WHERE execution IN ('agent_supervised','agent_auto') "
        "AND staging=0 AND status='open' ORDER BY priority='high' DESC, deadline"
    ).fetchall()
    return {
        "queue": [
            {
                "id": models.task_id(r["id"]),
                "text": r["text"],
                "detail": r["detail"],
                "acceptance_criteria": r["acceptance_criteria"],
                "deadline": r["deadline"],
                "execution": r["execution"],
                "runner": r["runner"],
                "deal": r["deal"],
                "version": r["version"],
            }
            for r in rows
        ]
    }


@app.post("/api/agent/claim/{tid}")
def agent_claim(tid: str, p=Depends(agent_only)):
    conn = db.get_conn()
    num = _tid(tid)
    _reap_expired_claims(conn)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        if row["execution"] not in models.AGENT_EXECUTIONS or row["staging"]:
            raise HTTPException(409, "task is not agent-executable")
        if row["status"] != "open" or row["claimed_by"]:
            raise HTTPException(409, f"task not claimable (status={row['status']})")
        expires = (datetime.now(timezone.utc) + timedelta(hours=4)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        _update_task(
            conn, p["id"], num, {"status": "in_progress"}, action="agent_claim"
        )
        conn.execute(
            "UPDATE tasks SET claimed_by=?, claim_expires_at=? WHERE id=?",
            (p["id"], expires, num),
        )
        conn.commit()
    return {"id": tid, "claimed_by": p["id"], "claim_expires_at": expires}


@app.post("/api/agent/heartbeat/{tid}")
def agent_heartbeat(tid: str, p=Depends(agent_only)):
    conn = db.get_conn()
    num = _tid(tid)
    _reap_expired_claims(conn)  # heartbeat cannot revive a dead lease (PM R4 recheck)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        if row["claimed_by"] != p["id"]:
            raise HTTPException(409, "not the claimant")
        expires = (datetime.now(timezone.utc) + timedelta(hours=4)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        conn.execute("UPDATE tasks SET claim_expires_at=? WHERE id=?", (expires, num))
        db.audit(conn, p["id"], "agent_heartbeat", tid)
        conn.commit()
    return {"id": tid, "claim_expires_at": expires}


@app.post("/api/agent/result/{tid}")
def agent_result(tid: str, payload: dict = Body(...), p=Depends(agent_only)):
    conn = db.get_conn()
    num = _tid(tid)
    key = payload.get("idempotency_key")
    evidence = payload.get("evidence")
    if not key or not evidence:
        raise HTTPException(422, "idempotency_key and evidence are required")
    _reap_expired_claims(conn)  # a dead lease must not accept results (PM R4 recheck)
    with db.WRITE_LOCK:
        prior = conn.execute(
            "SELECT response FROM idempotency WHERE task_id=? AND key=?", (num, key)
        ).fetchone()
        if prior:
            return json.loads(prior["response"])
        row = _get_task(conn, num)
        if row["claimed_by"] != p["id"]:
            raise HTTPException(409, "not the claimant")
        if row["status"] != "in_progress":
            # first accepted result locks the task (in_review) — no evidence overwrite
            raise HTTPException(
                409,
                f"task is {row['status']}; result already submitted "
                "or claim not active",
            )
        # M1: ALL agent results route to in_review — agent_auto unlocks in v1.1
        _update_task(
            conn,
            p["id"],
            num,
            {"status": "in_review", "evidence": evidence},
            action="agent_result",
        )
        response = {"id": tid, "status": "in_review"}
        conn.execute(
            "INSERT INTO idempotency (task_id, key, response, at) VALUES (?,?,?,?)",
            (num, key, json.dumps(response), db.now_iso()),
        )
        conn.commit()
    return response


@app.delete("/api/task/{tid}")
def delete_task(tid: str, p=Depends(human_only)):
    """Hard delete (undo/cleanup). Strips the ref from other tasks' prereqs so
    dependents don't go red on a dangling gate."""
    conn = db.get_conn()
    num = _tid(tid)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        ref = models.task_id(num)
        for other in conn.execute(
            "SELECT id, prereqs, version FROM tasks WHERE prereqs LIKE ?",
            (f'%"{ref}"%',),
        ).fetchall():
            pruned = [p_ for p_ in json.loads(other["prereqs"]) if p_.get("ref") != ref]
            conn.execute(
                "UPDATE tasks SET prereqs=?, version=version+1, updated_at=? WHERE id=?",
                (json.dumps(pruned), db.now_iso(), other["id"]),
            )
        conn.execute("DELETE FROM idempotency WHERE task_id=?", (num,))
        conn.execute("DELETE FROM tasks WHERE id=?", (num,))
        db.audit(
            conn, p["id"], "task_delete", ref, before={k: row[k] for k in row.keys()}
        )
        conn.commit()
    return {"deleted": ref}


@app.patch("/api/tasks/reorder")
def reorder_tasks(payload: dict = Body(...), p=Depends(human_only)):
    """Bulk-update sort_order for a list of task ids (in new display order).
    Payload: {task_ids: ["t-1", "t-3", "t-2", ...]}"""
    task_ids = payload.get("task_ids")
    if not task_ids or not isinstance(task_ids, list):
        raise HTTPException(422, "task_ids list is required")
    conn = db.get_conn()
    with db.WRITE_LOCK:
        for idx, tid_str in enumerate(task_ids):
            num = _tid(tid_str)
            conn.execute(
                "UPDATE tasks SET sort_order=?, updated_at=? WHERE id=?",
                (idx, db.now_iso(), num),
            )
        db.audit(conn, p["id"], "tasks_reorder", "bulk", after={"task_ids": task_ids})
        conn.commit()
    return {"reordered": len(task_ids)}


@app.patch("/api/workstreams/reorder")
def reorder_workstreams(payload: dict = Body(...), p=Depends(human_only)):
    ws_ids = payload.get("workstream_ids")
    if not ws_ids or not isinstance(ws_ids, list):
        raise HTTPException(422, "workstream_ids list is required")
    conn = db.get_conn()
    with db.WRITE_LOCK:
        for idx, wid_str in enumerate(ws_ids):
            prefix, num = _safe_ref(wid_str)
            if prefix != "w":
                raise HTTPException(422, f"expected w-<n>, got {wid_str!r}")
            row = conn.execute(
                "SELECT w.id, s.sort_mode FROM workstreams w "
                "JOIN spaces s ON s.id = w.space_id WHERE w.id=?",
                (num,),
            ).fetchone()
            if not row:
                raise HTTPException(404, f"{wid_str} not found")
            if row["sort_mode"] != "manual":
                raise HTTPException(422, "M&A projects are auto-sorted by deal stage")
            conn.execute(
                "UPDATE workstreams SET sort_order=?, version=version+1 WHERE id=?",
                (idx, num),
            )
        db.audit(
            conn,
            p["id"],
            "workstreams_reorder",
            "bulk",
            after={"workstream_ids": ws_ids},
        )
        conn.commit()
    return {"reordered": len(ws_ids)}


@app.post("/api/task/{tid}/approve")
def approve(tid: str, p=Depends(human_only)):
    conn = db.get_conn()
    num = _tid(tid)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        if row["status"] != "in_review":
            raise HTTPException(409, f"task is {row['status']}, not in_review")
        _update_task(conn, p["id"], num, {"status": "done"}, action="task_approve")
        conn.execute(
            "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL WHERE id=?", (num,)
        )
        conn.commit()
    return assemble_task(conn, num)


@app.post("/api/task/{tid}/reject")
def reject(tid: str, payload: dict = Body(default={}), p=Depends(human_only)):
    conn = db.get_conn()
    num = _tid(tid)
    comment = payload.get("comment", "")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        if row["status"] != "in_review":
            raise HTTPException(409, f"task is {row['status']}, not in_review")
        evidence = (row["evidence"] or "") + f"\nREJECTED ({p['id']}): {comment}"
        _update_task(
            conn,
            p["id"],
            num,
            {"status": "open", "evidence": evidence},
            action="task_reject",
        )
        conn.execute(
            "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL WHERE id=?", (num,)
        )
        conn.commit()
    return assemble_task(conn, num)


# --------------------------------------------------------------------------
# MD export / import
@app.get("/api/export.md", response_class=PlainTextResponse)
def export_md(scope: str = Query(default="all"), p=Depends(principal)):
    if scope == "all" and p["role"] != "human":
        raise HTTPException(403, "scope=all requires a human principal")
    conn = db.get_conn()
    st = assemble_state(conn)
    st = _filter_scope(st, scope)
    return mdio.render_export(st, scope)


def _all_ws(st):
    return [w for s in st["spaces"] for w in s["workstreams"]]


def _filter_scope(st, scope):
    if scope == "all":
        return st
    if scope == "agent-queue":
        # ALL agent-executable tasks — deliverable-linked ones included (PM R2)
        agent_tasks = [
            t
            for s in st["spaces"]
            for w in s["workstreams"]
            for d in w["deliverables"]
            for t in d["tasks"]
            if t["execution"] in models.AGENT_EXECUTIONS
        ]
        agent_tasks += [
            t
            for t in st["standalone_tasks"]
            if t["execution"] in models.AGENT_EXECUTIONS
        ]
        for s in st["spaces"]:
            s["workstreams"] = []
        st["standalone_tasks"] = agent_tasks
        return st
    kind, _, value = scope.partition(":")
    if kind == "person":

        def keep(t):
            tokens = re.split(r"[,;/\s]+", (t["responsible"] or ""))
            return value.lower() in (tok.lower() for tok in tokens if tok)
    elif kind == "workstream":
        for s in st["spaces"]:
            s["workstreams"] = [
                w for w in s["workstreams"] if w["id"] == value or w["name"] == value
            ]
        st["standalone_tasks"] = []
        return st
    elif kind == "deal":
        ws_matched = {
            w["id"]
            for w in _all_ws(st)
            if ((w["deal"] or {}).get("codename") or "").lower() == value.lower()
        }

        def keep(t):
            return (t["deal"] or "").lower() == value.lower()

        for s in st["spaces"]:
            s["workstreams"] = [
                w
                for w in s["workstreams"]
                if w["id"] in ws_matched
                or any(keep(t) for d in w["deliverables"] for t in d["tasks"])
            ]
            # PM R3: deal-linked workstream exports ALL its tasks
            for w in s["workstreams"]:
                if w["id"] not in ws_matched:
                    for d in w["deliverables"]:
                        d["tasks"] = [t for t in d["tasks"] if keep(t)]
                    w["deliverables"] = [d for d in w["deliverables"] if d["tasks"]]
        st["standalone_tasks"] = [t for t in st["standalone_tasks"] if keep(t)]
        return st
    else:
        raise HTTPException(422, f"unknown scope {scope!r}")
    # person scope: task-level filter everywhere
    for s in st["spaces"]:
        for w in s["workstreams"]:
            for d in w["deliverables"]:
                d["tasks"] = [t for t in d["tasks"] if keep(t)]
            w["deliverables"] = [d for d in w["deliverables"] if d["tasks"]]
        s["workstreams"] = [w for w in s["workstreams"] if w["deliverables"]]
    st["standalone_tasks"] = [t for t in st["standalone_tasks"] if keep(t)]
    return st


@app.post("/api/import")
def import_md(
    body: str = Body(..., media_type="text/markdown"),
    dry_run: bool = Query(default=False),
    p=Depends(principal),
):
    conn = db.get_conn()
    updates, creates, errors = mdio.parse_push(body)

    # resolve against DB (still fail-closed)
    resolved_creates = []
    for c in creates:
        if c.get("space"):
            space_row = conn.execute(
                "SELECT id FROM spaces WHERE name=?", (c["space"],)
            ).fetchone()
            if not space_row:
                errors.append(f"line {c['_line']}: space {c['space']!r} not found")
                continue
            ws = conn.execute(
                "SELECT id FROM workstreams WHERE name=? AND space_id=?",
                (c["workstream"], space_row["id"]),
            ).fetchall()
        else:
            ws = conn.execute(
                "SELECT id FROM workstreams WHERE name=?", (c["workstream"],)
            ).fetchall()
        if len(ws) != 1:
            errors.append(
                f"line {c['_line']}: workstream {c['workstream']!r} "
                f"{'not found' if not ws else 'ambiguous'}"
            )
            continue
        deliverable_id = None
        if c.get("deliverable"):
            ds = conn.execute(
                "SELECT id FROM deliverables WHERE workstream_id=? AND name=?",
                (ws[0]["id"], c["deliverable"]),
            ).fetchall()
            if len(ds) != 1:
                errors.append(
                    f"line {c['_line']}: deliverable {c['deliverable']!r} "
                    f"{'not found' if not ds else 'ambiguous'} in {c['workstream']!r}"
                )
                continue
            deliverable_id = ds[0]["id"]
        fields = {
            k: v
            for k, v in c.items()
            if k not in ("_line", "space", "workstream", "deliverable")
        }
        fields["deliverable_id"] = deliverable_id
        try:
            _validate_task_fields(conn, fields)
        except HTTPException as exc:
            errors.append(f"line {c['_line']}: {exc.detail}")
            continue
        resolved_creates.append(fields)

    resolved_updates = []
    for u in updates:
        num = models.parse_ref(u["id"])[1]
        row = conn.execute("SELECT version FROM tasks WHERE id=?", (num,)).fetchone()
        if not row:
            errors.append(f"line {u['_line']}: {u['id']} not found")
            continue
        if row["version"] != u["version"]:
            # stale markdown push must conflict, not silently overwrite (PM R1)
            errors.append(
                f"line {u['_line']}: {u['id']} version conflict — push has v{u['version']}, "
                f"current is v{row['version']}; re-export and retry"
            )
            continue
        fields = {k: v for k, v in u.items() if k not in ("_line", "id", "version")}
        try:
            _validate_task_fields(conn, fields)
        except HTTPException as exc:
            errors.append(f"line {u['_line']}: {exc.detail}")
            continue
        resolved_updates.append((num, fields))

    if errors:
        raise HTTPException(422, detail={"errors": errors})
    summary = {
        "updates": [
            {"id": models.task_id(n), "fields": f} for n, f in resolved_updates
        ],
        "creates": resolved_creates,
        "dry_run": dry_run,
    }
    if dry_run:
        return summary
    with db.WRITE_LOCK:
        for num, fields in resolved_updates:
            _update_task(conn, p["id"], num, fields, action="import_update")
        created_ids = [
            models.task_id(_insert_task(conn, p["id"], f)) for f in resolved_creates
        ]
        conn.commit()
    summary["created_ids"] = created_ids
    return summary


# --------------------------------------------------------------------------
# activity log
@app.get("/api/activity")
def activity_log(entity: str | None = Query(default=None), p=Depends(principal)):
    """Last 50 audit entries, newest first. Optional ?entity=t-123 filter."""
    conn = db.get_conn()
    if entity:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE entity=? ORDER BY at DESC LIMIT 50",
            (entity,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY at DESC LIMIT 50"
        ).fetchall()
    return {
        "entries": [
            {
                "id": r["id"],
                "timestamp": r["at"],
                "actor": r["actor"],
                "action": r["action"],
                "entity": r["entity"],
                "before": json.loads(r["before"]) if r["before"] else None,
                "after": json.loads(r["after"]) if r["after"] else None,
            }
            for r in rows
        ]
    }


# --------------------------------------------------------------------------
@app.post("/api/sync/dealroom")
def sync_now(p=Depends(principal)):
    return dealroom_sync.sync_deal_mirror(db.get_conn())


VALID_DEAL_STAGES = {
    "initial_contact",
    "screening",
    "nda",
    "valuation_rfi",
    "indicative_offer",
    "loi_signed",
    "dd",
    "spa",
    "signing",
    "on_hold",
    "dead",
}


@app.patch("/api/deal/{codename}")
def patch_deal(codename: str, payload: dict = Body(...), p=Depends(human_only)):
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM deal_mirror WHERE codename=?", (codename,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "deal not found")
    allowed = {"stage", "note"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(422, "nothing to update")
    if "stage" in updates and updates["stage"] not in VALID_DEAL_STAGES:
        raise HTTPException(422, f"invalid stage: {updates['stage']}")
    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [codename]
    with db.WRITE_LOCK:
        conn.execute(f"UPDATE deal_mirror SET {sets} WHERE codename=?", vals)
        conn.commit()
    return {"ok": True, "codename": codename, "updated": updates}
