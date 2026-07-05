"""FastAPI app: state assembly with computed fields, task/workstream/deliverable
mutations (version-checked, audited), agent queue with leases, MD import/export,
dealroom mirror sync. Single-process; writes serialized via db.WRITE_LOCK."""

import asyncio
import hashlib
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    Body,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse  # noqa: F401

from . import compute, db, dealroom_sync, mdio, models


# --------------------------------------------------------------------------
# SSE broadcast
_sse_clients: set[asyncio.Queue] = set()


def _broadcast(actor: str) -> None:
    """Notify all SSE clients that a change happened. Fire-and-forget."""
    msg = f"data: {json.dumps({'type': 'refresh', 'by': actor})}\n\n"
    dead = set()
    for q in _sse_clients:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.add(q)
    _sse_clients.difference_update(dead)


def _principal_from_token(token: str | None) -> dict | None:
    """Resolve a raw Bearer token string to a principal dict, or return None."""
    if not token:
        return None
    token_hash = hashlib.sha256(token.strip().encode()).hexdigest()
    row = (
        db.get_conn()
        .execute("SELECT id, role FROM users WHERE token_hash = ?", (token_hash,))
        .fetchone()
    )
    return {"id": row["id"], "role": row["role"]} if row else None


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
from starlette.middleware.base import BaseHTTPMiddleware


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.add_middleware(NoCacheStaticMiddleware)
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
            "start_date": r["start_date"] if "start_date" in r.keys() else None,
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
            "objective": r["objective"],
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
    "start_date",
    "preview_url",
    "review_feedback",
    "review_round",
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
    for key in ("deadline", "next_chase_date", "expected_back_by", "start_date"):
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


def _guard_personal(row, principal_id):
    """Personal todos are private to their creator. Any mutation by a non-creator
    is forbidden. Caller passes a task row and the requesting principal id."""
    if row["kind"] == "personal" and row["created_by"] != principal_id:
        raise HTTPException(403, "personal todo belongs to another user")


# Private body fields of a personal todo — never written verbatim into audit_log,
# so deleted personal tasks (unclassifiable at read time) leave no leaked body.
_PERSONAL_PRIVATE_FIELDS = ("text", "detail")


def _redact_personal_audit(payload, kind):
    """Return a copy of an audit before/after dict with personal-todo body fields
    redacted. Pass-through for non-personal tasks and falsy payloads."""
    if kind != "personal" or not payload:
        return payload
    return {
        k: ("[redacted]" if k in _PERSONAL_PRIVATE_FIELDS else v)
        for k, v in payload.items()
    }


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
    db.audit(
        conn,
        actor,
        "task_create",
        models.task_id(cur.lastrowid),
        after=_redact_personal_audit(cols, cols.get("kind")),
    )
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
    eff_kind = (
        "personal" if "personal" in (row["kind"], fields.get("kind")) else row["kind"]
    )
    db.audit(
        conn,
        actor,
        action,
        models.task_id(num),
        before=_redact_personal_audit(before, eff_kind),
        after=_redact_personal_audit(fields, eff_kind),
    )
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


@app.get("/api/events")
async def sse_events(
    token: str | None = Query(default=None),
    x_remote_user: str | None = Header(default=None),
) -> StreamingResponse:
    """Server-Sent Events stream. Broadcasts a refresh event on any mutation.
    Clients that cannot set custom headers (EventSource) pass token as ?token=."""
    # Auth: X-Remote-User (Caddy) or Bearer token via query param
    p = None
    if x_remote_user and x_remote_user in _CADDY_USER_MAP:
        pid = _CADDY_USER_MAP[x_remote_user]
        row = (
            db.get_conn()
            .execute("SELECT id, role FROM users WHERE id = ?", (pid,))
            .fetchone()
        )
        if row:
            p = {"id": row["id"], "role": row["role"]}
    if p is None:
        p = _principal_from_token(token)
    if p is None:
        raise HTTPException(401, "missing or invalid token")

    q: asyncio.Queue = asyncio.Queue(maxsize=32)
    _sse_clients.add(q)

    async def event_stream():
        try:
            yield "retry: 3000\n\n"  # tell browser to reconnect after 3 s
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield msg
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # SSE comment — prevents proxy timeout
        finally:
            _sse_clients.discard(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _scrub_personal(tasks, viewer):
    """Personal todos (kind='personal') are private to their creator. Drop any
    that this viewer did not create so one human never receives the other's."""
    return [
        t
        for t in tasks
        if not (t.get("kind") == "personal" and t.get("created_by") != viewer)
    ]


def _scrub_state_personal(st, viewer):
    """Strip personal tasks not owned by `viewer` from an assembled-state dict,
    in place, across standalone tasks and every deliverable. Apply before any
    rendering (export, etc.) so private todos never leak to another principal."""
    st["standalone_tasks"] = _scrub_personal(st.get("standalone_tasks", []), viewer)
    for space in st.get("spaces", []):
        for ws in space.get("workstreams", []):
            for d in ws.get("deliverables", []):
                d["tasks"] = _scrub_personal(d.get("tasks", []), viewer)
    return st


@app.get("/api/state")
def state(p=Depends(principal)):
    s = assemble_state(db.get_conn())
    s["principal"] = p
    # Server-side privacy: filter personal todos to the authenticated viewer.
    _scrub_state_personal(s, p["id"])
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
    _broadcast(p["id"])
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
        _guard_personal(_get_task(conn, num), p["id"])
        _update_task(conn, p["id"], num, payload, expected_version=version)
        conn.commit()
    _broadcast(p["id"])
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
    _broadcast(p["id"])
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
        {
            "name",
            "color",
            "sort_order",
            "status",
            "deal_codename",
            "space_id",
            "objective",
        },
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
    _validate_date(payload, "start_date")
    deal = payload.get("deal") or ws_row["deal_codename"]
    with db.WRITE_LOCK:
        cur = conn.execute(
            "INSERT INTO deliverables (workstream_id, name, target_date, start_date, status, sort_order,"
            " comment, staging, source, deal) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                wnum,
                payload["name"],
                payload.get("target_date"),
                payload.get("start_date"),
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
    _broadcast(p["id"])
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
    _validate_date(payload, "start_date")
    return _patch_simple(
        did,
        "d",
        "deliverables",
        payload,
        p,
        {
            "name",
            "target_date",
            "start_date",
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
    _broadcast(p["id"])
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
    _broadcast(p["id"])
    return {"id": id_str, "version": version + 1}


# --------------------------------------------------------------------------
# agent queue
# Ownership lanes (SPEC-agent-skills-repo §3a) are token-derived and data-driven:
# each agent's `represents` column links it to the human whose lane it works, and
# the agent's initials label that lane. Onboarding a new agent (id, initials,
# represents) needs no code change here.
def _owner_tag_map(conn):
    """{human_id -> lane label}, e.g. {'rd': 'RC', 'ff': 'FC'} — built from the
    agent rows so a new person never touches this file."""
    return {
        r["represents"]: r["initials"]
        for r in conn.execute(
            "SELECT initials, represents FROM users "
            "WHERE role='agent' AND represents IS NOT NULL"
        )
    }


def _task_readiness(conn, row):
    """(ready, blocked_by_hard_refs) for one task row — shared by queue (display)
    and claim (enforcement). Mirrors assemble_state's prereq resolver exactly:
    staging -> None; deliverable done/dropped -> done; an open deliverable whose
    live child tasks are all done -> done."""

    def _status_of(ref):
        try:
            prefix, num = models.parse_ref(ref)
        except ValueError:
            return None
        if prefix == "t":
            hit = conn.execute(
                "SELECT status, staging FROM tasks WHERE id=?", (num,)
            ).fetchone()
            return None if not hit or hit["staging"] else hit["status"]
        hit = conn.execute(
            "SELECT status, staging FROM deliverables WHERE id=?", (num,)
        ).fetchone()
        if not hit or hit["staging"]:
            return None
        if hit["status"] in ("done", "dropped"):
            return "done"
        live = conn.execute(
            "SELECT COUNT(*) AS n, SUM(status='done') AS d FROM tasks "
            "WHERE deliverable_id=? AND staging=0",
            (num,),
        ).fetchone()
        return "done" if live["n"] and live["n"] == live["d"] else "open"

    prereqs = json.loads(row["prereqs"] or "[]")
    color = compute.readiness(prereqs, _status_of)
    blocked_by = [
        p_["ref"]
        for p_ in prereqs
        if p_.get("hardness", "hard") == "hard" and _status_of(p_["ref"]) != "done"
    ]
    return color != compute.RED, blocked_by


@app.get("/api/agent/queue")
def agent_queue(scope: str = Query(default="mine"), p=Depends(agent_only)):
    """scope=mine (default) → only the caller's own lane, derived from the token;
    scope=all → every open agent task across all lanes."""
    if scope not in ("mine", "all"):
        raise HTTPException(422, f"scope must be 'mine' or 'all', got {scope!r}")
    conn = db.get_conn()
    _reap_expired_claims(conn)
    sql = (
        "SELECT * FROM tasks WHERE execution IN ('agent_supervised','agent_auto') "
        "AND staging=0 AND status='open'"
    )
    params: list = []
    if scope == "mine":
        me = conn.execute(
            "SELECT represents FROM users WHERE id=?", (p["id"],)
        ).fetchone()
        creator = me["represents"] if me else None
        if not creator:
            raise HTTPException(
                409,
                f"agent {p['id']!r} has no lane set (represents is empty); "
                "use ?scope=all or ask an admin to link it",
            )
        sql += " AND created_by=?"
        params.append(creator)
    # queue order must equal the Agents-view display order — "next task the
    # runner picks" is always the top card on screen
    sql += " ORDER BY sort_order, id"
    rows = conn.execute(sql, params).fetchall()
    owner_of = _owner_tag_map(conn)

    out = []
    for r in rows:
        ready, blocked_by = _task_readiness(conn, r)
        out.append(
            {
                "id": models.task_id(r["id"]),
                "text": r["text"],
                "detail": r["detail"],
                "acceptance_criteria": r["acceptance_criteria"],
                "deadline": r["deadline"],
                "execution": r["execution"],
                "runner": r["runner"],
                "deal": r["deal"],
                "created_by": r["created_by"],
                "owner": owner_of.get(r["created_by"]),
                "version": r["version"],
                # review-loop context: a sent-back task arrives WITH the human
                # feedback and the prior evidence trail (SPEC §7b)
                "review_round": r["review_round"] or 0,
                "review_feedback": r["review_feedback"],
                "evidence": r["evidence"],
                "ready": ready,
                "blocked_by": blocked_by,
            }
        )
    return {"queue": out}


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
        # enforce the readiness invariant at the mutation boundary — a runner
        # (old client, stale queue view) must not start work behind a hard gate
        ready, blocked_by = _task_readiness(conn, row)
        if not ready:
            raise HTTPException(
                409, f"task is blocked by unmet prereqs: {', '.join(blocked_by)}"
            )
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
    _broadcast(p["id"])  # card moves Queue -> Running live in the open browser
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
    _broadcast(p["id"])  # card moves Running -> Needs your review live
    return response


def _agent_lane(conn, p):
    """The human a caller-agent represents ('rd'/'ff'). 409 if unlinked."""
    me = conn.execute("SELECT represents FROM users WHERE id=?", (p["id"],)).fetchone()
    if not me or not me["represents"]:
        raise HTTPException(
            409, f"agent {p['id']!r} has no lane set (represents is empty)"
        )
    return me["represents"]


@app.post("/api/agent/task", status_code=201)
def agent_create_task(payload: dict = Body(...), p=Depends(agent_only)):
    """Enqueue an agent task from any Claude session (client `add`, SPEC §3a-2).
    The task is created in the caller's lane: created_by = the represented human,
    so RC-enqueued work shows lane RC and is drained by Roman's runner."""
    conn = db.get_conn()
    if not payload.get("text"):
        raise HTTPException(422, "text is required")
    lane = _agent_lane(conn, p)
    fields = {
        k: payload.get(k)
        for k in (
            "text",
            "detail",
            "acceptance_criteria",
            "deadline",
            "priority",
            "deal",
            "runner",
        )
        if payload.get(k) is not None
    }
    fields["execution"] = payload.get("execution") or "agent_supervised"
    if fields["execution"] not in models.AGENT_EXECUTIONS:
        raise HTTPException(422, "execution must be agent_supervised or agent_auto")
    fields["kind"] = "agent_job"
    fields.setdefault("runner", "local")
    if payload.get("deliverable_id"):
        prefix, dnum = _safe_ref(payload["deliverable_id"])
        if prefix != "d":
            raise HTTPException(422, "deliverable_id must be d-<n>")
        fields["deliverable_id"] = dnum
    _validate_task_fields(conn, fields)  # enforces AC for agent execution
    with db.WRITE_LOCK:
        new_id = _insert_task(conn, lane, fields)
        db.audit(conn, p["id"], "agent_enqueue", models.task_id(new_id))
        conn.commit()
    _broadcast(p["id"])
    return assemble_task(conn, new_id)


@app.post("/api/agent/block/{tid}")
def agent_block(tid: str, payload: dict = Body(...), p=Depends(agent_only)):
    """Claimant parks a task on a question for its human (SPEC §7b): status ->
    blocked, question stored, claim released. The browser shows it under
    'Waiting on you'; answering re-opens it for the next runner pass."""
    conn = db.get_conn()
    num = _tid(tid)
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(422, "question is required")
    lane = _agent_lane(conn, p)
    input_from = payload.get("input_from") or lane.upper()
    if input_from not in _TASK_ENUMS["input_from"]:
        raise HTTPException(422, f"invalid input_from: {input_from!r}")
    _reap_expired_claims(conn)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        if row["claimed_by"] != p["id"]:
            raise HTTPException(409, "not the claimant")
        if row["status"] != "in_progress":
            raise HTTPException(409, f"task is {row['status']}, not in_progress")
        _update_task(
            conn,
            p["id"],
            num,
            {
                "status": "blocked",
                "input_from": input_from,
                "input_question": question,
            },
            action="agent_block",
        )
        conn.execute(
            "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL WHERE id=?", (num,)
        )
        conn.commit()
    _broadcast(p["id"])  # card moves Running -> Waiting on you live
    return {"id": tid, "status": "blocked", "input_from": input_from}


@app.post("/api/task/{tid}/answer")
def answer_blocker(tid: str, payload: dict = Body(...), p=Depends(human_only)):
    """Human answers a blocked task's question inline (SPEC §7b): the answer is
    appended to the evidence trail, the question cleared, the task re-opened —
    the next runner pass picks it up with the answer in context."""
    conn = db.get_conn()
    num = _tid(tid)
    answer = (payload.get("answer") or "").strip()
    if not answer:
        raise HTTPException(422, "answer is required")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        if row["status"] != "blocked" or not row["input_question"]:
            raise HTTPException(
                409, f"task is {row['status']} and/or has no open question"
            )
        evidence = (row["evidence"] or "") + (
            f"\n\n---\nQUESTION: {row['input_question']}\nANSWER ({p['id']}): {answer}"
        )
        _update_task(
            conn,
            p["id"],
            num,
            {
                "status": "open",
                "evidence": evidence,
                "input_from": None,
                "input_question": None,
            },
            action="task_answer",
        )
        conn.commit()
    _broadcast(p["id"])
    return assemble_task(conn, num)


@app.delete("/api/task/{tid}")
def delete_task(tid: str, p=Depends(human_only)):
    """Hard delete (undo/cleanup). Strips the ref from other tasks' prereqs so
    dependents don't go red on a dangling gate."""
    conn = db.get_conn()
    num = _tid(tid)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
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
            conn,
            p["id"],
            "task_delete",
            ref,
            before=_redact_personal_audit({k: row[k] for k in row.keys()}, row["kind"]),
        )
        conn.commit()
    _broadcast(p["id"])
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
    _broadcast(p["id"])
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
    _broadcast(p["id"])
    return {"reordered": len(ws_ids)}


@app.patch("/api/deliverables/reorder")
def reorder_deliverables(payload: dict = Body(...), p=Depends(human_only)):
    deliv_ids = payload.get("deliverable_ids")
    if not deliv_ids or not isinstance(deliv_ids, list):
        raise HTTPException(422, "deliverable_ids list is required")
    conn = db.get_conn()
    with db.WRITE_LOCK:
        for idx, did_str in enumerate(deliv_ids):
            prefix, num = _safe_ref(did_str)
            if prefix != "d":
                raise HTTPException(422, f"expected d-<n>, got {did_str!r}")
            conn.execute(
                "UPDATE deliverables SET sort_order=?, version=version+1 WHERE id=?",
                (idx, num),
            )
        db.audit(
            conn,
            p["id"],
            "deliverables_reorder",
            "bulk",
            after={"deliverable_ids": deliv_ids},
        )
        conn.commit()
    _broadcast(p["id"])
    return {"reordered": len(deliv_ids)}


@app.post("/api/task/{tid}/approve")
def approve(tid: str, p=Depends(human_only)):
    conn = db.get_conn()
    num = _tid(tid)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        if row["status"] != "in_review":
            raise HTTPException(409, f"task is {row['status']}, not in_review")
        _update_task(conn, p["id"], num, {"status": "done"}, action="task_approve")
        conn.execute(
            "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL WHERE id=?", (num,)
        )
        conn.commit()
    _broadcast(p["id"])
    return assemble_task(conn, num)


@app.post("/api/task/{tid}/reject")
def reject(tid: str, payload: dict = Body(default={}), p=Depends(human_only)):
    conn = db.get_conn()
    num = _tid(tid)
    comment = payload.get("comment", "")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        if row["status"] != "in_review":
            raise HTTPException(409, f"task is {row['status']}, not in_review")
        evidence = (row["evidence"] or "") + f"\nREJECTED ({p['id']}): {comment}"
        # Reject = "this result is unusable / never agent work" — flip execution
        # to 'me' so the task LEAVES the agent lane. Otherwise an unattended
        # runner re-executes the identical failure forever (SPEC §7d).
        # Redo-with-guidance is exclusively request-changes.
        _update_task(
            conn,
            p["id"],
            num,
            {"status": "open", "evidence": evidence, "execution": "me"},
            action="task_reject",
        )
        conn.execute(
            "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL WHERE id=?", (num,)
        )
        conn.commit()
    _broadcast(p["id"])
    return assemble_task(conn, num)


@app.post("/api/task/{tid}/request-changes")
def request_changes(tid: str, payload: dict = Body(...), p=Depends(human_only)):
    """Send task back to agent with structured feedback. Unlike reject (which
    just re-opens), this increments review_round and stores feedback so the
    next agent run gets it as mandatory context."""
    conn = db.get_conn()
    num = _tid(tid)
    feedback = payload.get("feedback", "")
    if not feedback.strip():
        raise HTTPException(422, "feedback is required for request-changes")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        if row["status"] != "in_review":
            raise HTTPException(409, f"task is {row['status']}, not in_review")
        new_round = (row["review_round"] or 0) + 1
        evidence = (
            row["evidence"] or ""
        ) + f"\n\n---\nFEEDBACK R{new_round} ({p['id']}): {feedback}"
        _update_task(
            conn,
            p["id"],
            num,
            {
                "status": "open",
                "evidence": evidence,
                "review_feedback": feedback,
                "review_round": new_round,
            },
            action="task_request_changes",
        )
        conn.execute(
            "UPDATE tasks SET claimed_by=NULL, claim_expires_at=NULL WHERE id=?", (num,)
        )
        conn.commit()
    _broadcast(p["id"])
    return assemble_task(conn, num)


# --------------------------------------------------------------------------
# preview file storage
_PREVIEW_DIR = (
    Path(os.environ.get("COCKPIT_DB", "")).parent / "previews"
    if os.environ.get("COCKPIT_DB")
    else Path(__file__).resolve().parent.parent / "data" / "previews"
)
_MAX_PREVIEW_MB = 50


@app.post("/api/task/{tid}/upload-preview", status_code=201)
def upload_preview(tid: str, file: UploadFile = File(...), p=Depends(principal)):
    """Store a preview file (PDF, PNG, HTML) for the review UI."""
    conn = db.get_conn()
    num = _tid(tid)
    row = _get_task(conn, num)
    if not row:
        raise HTTPException(404, "task not found")
    ext = Path(file.filename or "preview.pdf").suffix.lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".html"):
        raise HTTPException(422, f"unsupported preview type: {ext}")
    task_dir = _PREVIEW_DIR / str(num)
    task_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{uuid.uuid4().hex[:12]}{ext}"
    dest = task_dir / fname
    size = 0
    with open(dest, "wb") as f:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > _MAX_PREVIEW_MB * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"file exceeds {_MAX_PREVIEW_MB}MB limit")
            f.write(chunk)
    preview_url = f"/api/task/{tid}/preview/{fname}"
    with db.WRITE_LOCK:
        conn.execute(
            "UPDATE tasks SET preview_url=?, updated_at=?, version=version+1 WHERE id=?",
            (preview_url, db.now_iso(), num),
        )
        db.audit(
            conn,
            p["id"],
            "preview_upload",
            models.task_id(num),
            after={"preview_url": preview_url, "size": size},
        )
        conn.commit()
    return {"url": preview_url, "size": size}


@app.get("/api/task/{tid}/preview/{filename}")
def serve_preview(tid: str, filename: str):
    """Serve a stored preview file. No auth — previews are non-sensitive."""
    num = _tid(tid)
    path = _PREVIEW_DIR / str(num) / filename
    if not path.is_file():
        raise HTTPException(404, "preview not found")
    media = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".html": "text/html",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media)


# --------------------------------------------------------------------------
# MD export / import
@app.get("/api/export.md", response_class=PlainTextResponse)
def export_md(scope: str = Query(default="all"), p=Depends(principal)):
    if scope == "all" and p["role"] != "human":
        raise HTTPException(403, "scope=all requires a human principal")
    conn = db.get_conn()
    st = assemble_state(conn)
    # Privacy: drop personal todos not owned by the requester, for ALL scopes
    # (incl. scope=all) before scope filtering and rendering.
    _scrub_state_personal(st, p["id"])
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

    # Privacy: an audit entry whose entity is a personal todo not created by the
    # viewer must not expose its body. Classify each task-entity row against the
    # live task; entries we can identify as another user's personal todo are
    # redacted. Rows whose task no longer exists can't be classified — but
    # personal-task bodies are no longer written into audit_log (see _audit_task),
    # so those legacy rows carry no private body for new personal todos.
    personal_owner = {}  # entity ref -> created_by, for kind='personal' tasks

    def _is_other_personal(entity):
        if not entity or not entity.startswith("t-"):
            return False
        if entity not in personal_owner:
            try:
                _, n = _safe_ref(entity)
                trow = conn.execute(
                    "SELECT kind, created_by FROM tasks WHERE id=?", (n,)
                ).fetchone()
            except Exception:
                trow = None
            personal_owner[entity] = (
                trow["created_by"] if trow and trow["kind"] == "personal" else False
            )
        owner = personal_owner[entity]
        return owner is not False and owner != p["id"]

    entries = []
    for r in rows:
        redacted = _is_other_personal(r["entity"])
        entries.append(
            {
                "id": r["id"],
                "timestamp": r["at"],
                "actor": r["actor"],
                "action": r["action"],
                "entity": r["entity"],
                "before": None
                if redacted
                else (json.loads(r["before"]) if r["before"] else None),
                "after": None
                if redacted
                else (json.loads(r["after"]) if r["after"] else None),
                **({"redacted": True} if redacted else {}),
            }
        )
    return {"entries": entries}


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
    """Deal stage/note are MASTERED by DEALRoom (dealroom.db) and mirrored
    read-only into cockpit's deal_mirror. Writing them here is silently lost on
    the next sync, so we refuse and point the caller at the source of truth."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM deal_mirror WHERE codename=?", (codename,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "deal not found")
    raise HTTPException(
        409,
        "deal stage/note are mastered by DEALRoom and mirrored read-only here; "
        "edit them in DEALRoom (dealroom.db) — cockpit mirror edits are "
        "overwritten on the next sync",
    )
