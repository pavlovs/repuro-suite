"""FastAPI app: state assembly with computed fields, task/workstream/deliverable
mutations (version-checked, audited), agent queue with leases, MD import/export,
dealroom mirror sync. Single-process; writes serialized via db.WRITE_LOCK."""

import asyncio
import hashlib
import json
import os
import re
import secrets
import sqlite3
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
from fastapi.responses import (  # noqa: F401
    FileResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)

from . import calendar_graph, compute, db, dealroom_sync, mdio, models


# --------------------------------------------------------------------------
# SSE broadcast
_sse_clients: set[asyncio.Queue] = set()


def _broadcast(actor: str) -> None:
    """Notify all SSE clients that a change happened. Fire-and-forget.
    Iterate a snapshot: _broadcast runs on threadpool workers while the event
    loop thread adds/removes queues in sse_events, so touching the live set here
    would raise 'Set changed size during iteration'."""
    msg = f"data: {json.dumps({'type': 'refresh', 'by': actor})}\n\n"
    dead = set()
    for q in list(_sse_clients):
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
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.exception_handlers import http_exception_handler


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.add_middleware(NoCacheStaticMiddleware)


def _rollback_pending():
    """Discard any transaction left open on the shared connection. Endpoints run
    execute()+commit() under one WRITE_LOCK hold, so a mid-mutation raise (an
    HTTPException in a reorder loop, or a DB error) exits the block with writes
    uncommitted; without this the NEXT request's commit would silently persist
    them. rollback() is a no-op when nothing is pending — safe on every error."""
    try:
        db.get_conn().rollback()
    except Exception:
        pass


@app.exception_handler(StarletteHTTPException)
async def _http_exc_rollback(request, exc):
    _rollback_pending()
    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def _unhandled_exc_rollback(request, exc):
    _rollback_pending()
    raise exc


app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static")),
    name="static",
)


# --------------------------------------------------------------------------
# auth
_CADDY_USER_MAP = {"roman": "rd", "florian": "ff"}


def _build_principal(row):
    """Build full principal dict from users LEFT JOIN role_profiles row."""
    role = row["role"]
    if role == "agent":
        return {
            "id": row["id"],
            "name": row["name"],
            "initials": row["initials"],
            "role": role,
            "profile": None,
            "modules": ["agents"],
            "read_only": False,
        }
    module_access = row["module_access"]
    rp_read_only = row["rp_read_only"]
    profile = row["profile"]
    if module_access is not None:
        modules = json.loads(module_access)
        read_only = bool(rp_read_only)
        effective_profile = profile
    else:
        # NULL profile: treat as owner (fail-open, backward compatible)
        modules = [
            "overview",
            "week",
            "workstreams",
            "timeline",
            "agents",
            "relations",
        ]
        read_only = False
        effective_profile = "owner"
    return {
        "id": row["id"],
        "name": row["name"],
        "initials": row["initials"],
        "role": role,
        "profile": effective_profile,
        "modules": modules,
        "read_only": read_only,
    }


_ALL_COCKPIT_MODS = [
    "overview",
    "week",
    "workstreams",
    "timeline",
    "agents",
    "relations",
    "calendar",
]


def _build_principal_v13(conn, row):
    """Build full principal dict (v13: teams/perms enriched)."""
    role = row["role"]
    if role == "agent":
        return {
            "id": row["id"],
            "name": row["name"],
            "initials": row["initials"],
            "role": role,
            "profile": None,
            "modules": ["agents"],
            "perms": {"agents": "rw"},
            "is_admin": False,
            "all_teams": False,
            "teams": [],
            "read_only": False,
        }

    user_id = row["id"]
    team_rows = conn.execute(
        "SELECT t.id, t.permissions, t.is_admin "
        "FROM teams t JOIN team_members tm ON tm.team_id = t.id "
        "WHERE tm.user_id = ? AND t.status = 'active'",
        (user_id,),
    ).fetchall()

    team_ids = [t["id"] for t in team_rows]
    is_admin = any(bool(t["is_admin"]) for t in team_rows)

    try:
        all_teams = bool(row["all_teams"]) if row["all_teams"] is not None else False
    except (IndexError, KeyError):
        all_teams = False

    # Strongest-wins merge: rw > ro > none
    _RANK = {"rw": 2, "ro": 1}
    merged: dict = {}
    for t in team_rows:
        try:
            t_perms = json.loads(t["permissions"] or "{}")
        except (json.JSONDecodeError, TypeError):
            t_perms = {}
        for mod, lvl in t_perms.items():
            if _RANK.get(lvl, 0) > _RANK.get(merged.get(mod), 0):
                merged[mod] = lvl

    if is_admin:
        perms_out = {m: "rw" for m in _ALL_COCKPIT_MODS}
        modules = _ALL_COCKPIT_MODS[:]
        read_only = False
        profile_val = "owner"
    elif merged:
        perms_out = merged
        modules = list(merged.keys())
        read_only = all(v == "ro" for v in merged.values())
        try:
            profile_val = row["profile"]
        except (IndexError, KeyError):
            profile_val = None
        if profile_val is None:
            profile_val = next(
                (k for k in merged if merged[k] == "rw"), list(merged.keys())[0]
            )
    else:
        # No team memberships. Fail-open as owner-equivalent ONLY for the legacy
        # founders (pre-v13 rows: rd/ff, or the v12 'owner' backfill marker) so a
        # fresh/dev DB can never lock them out. Every other teamless human is
        # fail-CLOSED — otherwise removing a user's last team would escalate
        # them to full access instead of revoking it.
        try:
            legacy_profile = row["profile"]
        except (IndexError, KeyError):
            legacy_profile = None
        if row["id"] in ("rd", "ff") or legacy_profile == "owner":
            perms_out = {m: "rw" for m in _ALL_COCKPIT_MODS}
            modules = _ALL_COCKPIT_MODS[:]
            read_only = False
            profile_val = "owner"
        else:
            perms_out = {}
            modules = []
            read_only = True
            profile_val = None

    return {
        "id": row["id"],
        "name": row["name"],
        "initials": row["initials"],
        "role": role,
        "profile": profile_val,
        "modules": modules,
        "perms": perms_out,
        "is_admin": is_admin,
        "all_teams": all_teams,
        "teams": team_ids,
        "read_only": read_only,
    }


def principal(
    authorization: str | None = Header(default=None),
    x_remote_user: str | None = Header(default=None),
):
    # X-Remote-User is only trustworthy when a reverse proxy we control set it
    # from basic auth (prod: Caddy overwrites the header on every request).
    # Two gates (codex #5): the deployment must opt in via COCKPIT_TRUSTED_PROXY
    # (set in suite/fly.toml, never on a directly-exposed instance), and a
    # request carrying its own Bearer token is a direct caller — it never ALSO
    # gets to assert a human identity via a client-set header.
    if x_remote_user and os.environ.get("COCKPIT_TRUSTED_PROXY") != "1":
        x_remote_user = None
    # Only a BEARER Authorization marks a direct caller. Browsers behind Caddy
    # necessarily send "Authorization: Basic ..." (the Caddy login itself) and
    # Caddy forwards it upstream alongside the X-Remote-User it sets — nuking
    # the identity on ANY Authorization header rejected all browser traffic
    # through the proxy (login-loop incident 2026-07-05/06).
    if authorization and authorization.startswith("Bearer "):
        x_remote_user = None
    conn = db.get_conn()
    if x_remote_user:
        # v13: resolve by users.login first (replaces _CADDY_USER_MAP as primary path)
        row = conn.execute(
            "SELECT * FROM users WHERE login = ?", (x_remote_user,)
        ).fetchone()
        if row:
            return _build_principal_v13(conn, row)
        # Fallback: legacy _CADDY_USER_MAP (backward compat for unmigrated rows)
        pid = _CADDY_USER_MAP.get(x_remote_user)
        if pid:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (pid,)).fetchone()
            if row:
                return _build_principal_v13(conn, row)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token_hash = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    row = conn.execute(
        "SELECT * FROM users WHERE token_hash = ?", (token_hash,)
    ).fetchone()
    if not row:
        raise HTTPException(401, "unknown token")
    return _build_principal_v13(conn, row)


def human_only(p=Depends(principal)):
    if p["role"] != "human":
        raise HTTPException(403, "requires a human principal")
    return p


def agent_only(p=Depends(principal)):
    if p["role"] != "agent":
        raise HTTPException(403, "requires an agent principal")
    return p


def read_only_guard(p=Depends(principal)):
    if p.get("read_only"):
        raise HTTPException(403, "This account is read-only")
    return p


def _check_write(p: dict, module: str) -> None:
    """Raise 403 if the principal lacks write access to module.
    is_admin bypasses all module checks."""
    if p.get("is_admin"):
        return
    if (p.get("perms") or {}).get(module) != "rw":
        raise HTTPException(403, f"'{module}' write access required")


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
    # One row with malformed JSON here must not 500 the entire /api/state (and
    # thus the whole SPA). Fall back to an empty list — fail visible, not fatal.
    for k in ("prereqs", "tags", "links"):
        try:
            t[k] = json.loads(row[k]) if row[k] else []
        except (json.JSONDecodeError, TypeError):
            t[k] = []
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


def assemble_state(conn, me=None):
    _reap_expired_claims(conn)
    today = _today()
    space_rows = conn.execute("SELECT * FROM spaces ORDER BY sort_order").fetchall()
    ws_rows = conn.execute(
        "SELECT * FROM workstreams ORDER BY sort_order, id"
    ).fetchall()
    # v13 module gate: no 'workstreams' permission at all → no workstream data in
    # the state payload (nav hiding alone is not enforcement — an hr-only or
    # teamless principal must not receive the full task tree). all_teams widens
    # WHICH workstreams you see, not WHETHER the module is yours — no bypass here.
    if (
        me
        and me.get("role") != "agent"
        and "workstreams" not in (me.get("perms") or {})
    ):
        ws_rows = []
    # v13 team gate: workstream visible if (a) no team assignment, or (b) user is
    # in one of the assigned teams, or (c) user has all_teams=1 (god view).
    # Applies to all non-agent principals. Unassigned ws = visible to all (opt-in).
    if me and me.get("role") != "agent" and not me.get("all_teams"):
        principal_teams = set(me.get("teams") or [])
        if principal_teams:
            wt_rows = conn.execute(
                "SELECT workstream_id, team_id FROM workstream_teams"
            ).fetchall()
            ws_team_map: dict = {}
            for wt in wt_rows:
                ws_team_map.setdefault(wt["workstream_id"], set()).add(wt["team_id"])
            ws_rows = [
                ws
                for ws in ws_rows
                if not ws_team_map.get(ws["id"])  # no assignment = visible to all
                or bool(ws_team_map.get(ws["id"]) & principal_teams)
            ]
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


def _guard_foreign_agent(row, p):
    """Agent workflows are lane-private: only the creating human or an admin may
    read or mutate them (codex 2026-07-15 #3 — without this, the /api/state
    scrub is bypassable via direct task routes). Agent principals pass — the
    claim/result/block endpoints govern the runner side."""
    if p.get("role") != "human" or p.get("is_admin"):
        return
    if row["execution"] in models.AGENT_EXECUTIONS and row["created_by"] != p["id"]:
        raise HTTPException(403, "agent task belongs to another user's lane")


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
    # Auth: X-Remote-User (Caddy) or Bearer token via query param.
    # Same trust gate as principal() (codex #5 sweep): header-only identity
    # requires the trusted-proxy env; a token-carrying caller never gets to
    # also assert a header identity.
    if x_remote_user and (os.environ.get("COCKPIT_TRUSTED_PROXY") != "1" or token):
        x_remote_user = None
    p = None
    if x_remote_user:
        _sconn = db.get_conn()
        # v13: login-based resolution first
        row = _sconn.execute(
            "SELECT id, role FROM users WHERE login = ?", (x_remote_user,)
        ).fetchone()
        if not row:
            pid = _CADDY_USER_MAP.get(x_remote_user)
            if pid:
                row = _sconn.execute(
                    "SELECT id, role FROM users WHERE id = ?", (pid,)
                ).fetchone()
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


def _scrub_foreign_agent_tasks(st, viewer):
    """Agent workflows are personal: a non-admin human sees only the agent-execution
    tasks they created themselves. Admins (md team) keep the full agent picture.
    Same in-place shape as _scrub_state_personal — apply to /api/state for
    non-admin humans so foreign 'Waiting on you' items never reach the client."""

    def keep(t):
        return (
            t.get("execution") not in models.AGENT_EXECUTIONS
            or t.get("created_by") == viewer
        )

    st["standalone_tasks"] = [t for t in st.get("standalone_tasks", []) if keep(t)]
    for space in st.get("spaces", []):
        for ws in space.get("workstreams", []):
            for d in ws.get("deliverables", []):
                d["tasks"] = [t for t in d.get("tasks", []) if keep(t)]
    return st


def _recount_progress(st):
    """Re-derive deliverable progress from the tasks that SURVIVED scrubbing —
    otherwise the counts leak how many hidden (foreign agent/personal) tasks
    exist and contradict the visible list (codex 2026-07-15 #5)."""
    for space in st.get("spaces", []):
        for ws in space.get("workstreams", []):
            for d in ws.get("deliverables", []):
                ch = d.get("tasks", [])
                d["computed"]["progress"] = {
                    "done": sum(1 for c in ch if c["status"] == "done"),
                    "total": len(ch),
                }
    return st


@app.get("/api/state")
def state(p=Depends(principal)):
    conn = db.get_conn()
    s = assemble_state(conn, me=p)
    s["principal"] = p
    # The people directory drives every owner picker / person column in the UI —
    # a new team member is a users row, never a frontend change.
    s["users"] = [
        {"id": r["id"], "name": r["name"], "initials": r["initials"]}
        for r in conn.execute(
            "SELECT id, name, initials FROM users WHERE role='human' "
            "ORDER BY CASE id WHEN 'rd' THEN 0 WHEN 'ff' THEN 1 ELSE 2 END, id"
        )
    ]
    s["lanes"] = _owner_tag_map(conn)
    is_admin_human = p["role"] == "human" and p.get("is_admin")
    learn_sql = (
        "SELECT * FROM learnings WHERE status!='dismissed' "
        "ORDER BY status='candidate' DESC, kind='constraint' DESC, id"
    )
    if p["role"] == "human" and not is_admin_human:
        # Non-admin humans get only their own lane's lessons — the founders'
        # playbook (deal context, global rules) is not theirs to curate or read.
        s["learnings"] = [
            _learning_json(r) for r in conn.execute(learn_sql) if r["lane"] == p["id"]
        ]
        _scrub_foreign_agent_tasks(s, p["id"])
    else:
        s["learnings"] = [_learning_json(r) for r in conn.execute(learn_sql)]
    # Server-side privacy: filter personal todos to the authenticated viewer.
    _scrub_state_personal(s, p["id"])
    if p["role"] == "human" and not is_admin_human:
        _recount_progress(s)
    return s


@app.get("/api/authz")
def authz(
    module: str = Query(...),
    x_remote_user: str | None = Header(default=None),
    x_forwarded_method: str | None = Header(default=None),
):
    """Caddy forward_auth endpoint. Resolves X-Remote-User, checks module access.
    Returns 200 (empty) or 403. No Bearer path — agents never hit /deals|/allex."""
    if not x_remote_user:
        raise HTTPException(403, "no user identity")
    conn = db.get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE login = ?", (x_remote_user,)
    ).fetchone()
    if not row:
        pid = _CADDY_USER_MAP.get(x_remote_user)
        if pid:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (pid,)).fetchone()
    if not row:
        raise HTTPException(403, "unknown user")
    p = _build_principal_v13(conn, row)
    if p.get("is_admin"):
        return Response(status_code=200)
    perms = p.get("perms") or {}
    lvl = perms.get(module)
    if lvl is None:
        raise HTTPException(403, "no access to module")
    method = (x_forwarded_method or "GET").upper()
    if lvl == "ro" and method not in {"GET", "HEAD", "OPTIONS"}:
        raise HTTPException(403, "read-only access — write method not allowed")
    return Response(status_code=200)


@app.post("/api/task", status_code=201)
def create_task(payload: dict = Body(...), p=Depends(principal)):
    _check_write(p, "workstreams")
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
    _check_write(p, "workstreams")
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
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        _guard_foreign_agent(row, p)
        _update_task(conn, p["id"], num, payload, expected_version=version)
        conn.commit()
    _broadcast(p["id"])
    return assemble_task(conn, num)


@app.post("/api/workstream", status_code=201)
def create_workstream(payload: dict = Body(...), p=Depends(principal)):
    _check_write(p, "workstreams")
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
        except sqlite3.IntegrityError:
            # Only the (space_id, name) unique index — a real DB error (disk full,
            # corruption) must surface as 500, not a misleading "already exists".
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
    _check_write(p, "workstreams")
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
    _check_write(p, "workstreams")
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
    _check_write(p, "workstreams")
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
    _check_write(p, "workstreams")
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
    me = conn.execute("SELECT represents FROM users WHERE id=?", (p["id"],)).fetchone()
    lane = me["represents"] if me else None
    if scope == "mine":
        if not lane:
            raise HTTPException(
                409,
                f"agent {p['id']!r} has no lane set (represents is empty); "
                "use ?scope=all or ask an admin to link it",
            )
        sql += " AND created_by=?"
        params.append(lane)
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
    # the curated playbook rides with every queue fetch — the runner applies
    # constraints as binding rules and heuristics as defaults (SPEC §learnings)
    return {"queue": out, "playbook": _playbook_for(conn, lane)}


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
def answer_blocker(
    tid: str,
    payload: dict = Body(...),
    p=Depends(human_only),
):
    """Human answers a blocked task's question inline (SPEC §7b): the answer is
    appended to the evidence trail, the question cleared, the task re-opened —
    the next runner pass picks it up with the answer in context."""
    _check_write(p, "agents")
    conn = db.get_conn()
    num = _tid(tid)
    answer = (payload.get("answer") or "").strip()
    if not answer:
        raise HTTPException(422, "answer is required")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        _guard_foreign_agent(row, p)
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


# --------------------------------------------------------------------------
# playbook learnings — candidates from runners, human-curated, hard-capped
_PLAYBOOK_CAP = 40  # active entries per lane — a playbook, not an incident log


def _learning_json(r):
    return {
        "id": r["id"],
        "lane": r["lane"],
        "kind": r["kind"],
        "text": r["text"],
        "source_task": r["source_task"],
        "status": r["status"],
        "created_by": r["created_by"],
        "created_at": r["created_at"],
    }


def _playbook_for(conn, lane):
    """Active entries for one lane (+ lane-agnostic), constraints first."""
    rows = conn.execute(
        "SELECT * FROM learnings WHERE status='active' AND (lane IS NULL OR lane=?) "
        "ORDER BY kind='constraint' DESC, id LIMIT ?",
        (lane, _PLAYBOOK_CAP),
    ).fetchall()
    return [
        {"kind": r["kind"], "text": r["text"], "source_task": r["source_task"]}
        for r in rows
    ]


@app.post("/api/agent/learning", status_code=201)
def agent_submit_learning(payload: dict = Body(...), p=Depends(agent_only)):
    """Runner submits ONE candidate lesson (one line, generalizable). It does
    NOT enter the playbook — a human promotes or dismisses it in the cockpit."""
    conn = db.get_conn()
    text = " ".join((payload.get("text") or "").split())
    if not text:
        raise HTTPException(422, "text is required")
    if len(text) > 300:
        raise HTTPException(422, "lesson too long — one line, max 300 chars")
    kind = payload.get("kind") or "heuristic"
    if kind not in ("constraint", "heuristic"):
        raise HTTPException(422, f"invalid kind: {kind!r}")
    lane = _agent_lane(conn, p)
    dup = conn.execute(
        "SELECT * FROM learnings WHERE status!='dismissed' "
        "AND lower(text)=lower(?) AND (lane IS NULL OR lane=?)",
        (text, lane),
    ).fetchone()
    if dup:
        return _learning_json(dup) | {"duplicate": True}
    with db.WRITE_LOCK:
        cur = conn.execute(
            "INSERT INTO learnings (lane, kind, text, source_task, status, "
            "created_by, created_at) VALUES (?,?,?,?, 'candidate', ?, ?)",
            (lane, kind, text, payload.get("source_task"), p["id"], db.now_iso()),
        )
        db.audit(conn, p["id"], "learning_submit", f"l-{cur.lastrowid}")
        conn.commit()
    _broadcast(p["id"])
    row = conn.execute(
        "SELECT * FROM learnings WHERE id=?", (cur.lastrowid,)
    ).fetchone()
    return _learning_json(row)


@app.post("/api/learning/{lid}/decide")
def decide_learning(
    lid: int,
    payload: dict = Body(...),
    p=Depends(human_only),
):
    """Human curation: promote a candidate into the playbook (optionally edited)
    or dismiss it. Also retires active entries (action=dismiss). The cap is a
    hard gate — a full playbook forces pruning before new promotions."""
    _check_write(p, "agents")
    action = payload.get("action")
    if action not in ("promote", "dismiss"):
        raise HTTPException(422, "action must be promote or dismiss")
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM learnings WHERE id=?", (lid,)).fetchone()
    if not row:
        raise HTTPException(404, f"learning {lid} not found")
    # Lane privacy: non-admins curate only their own lane (codex 2026-07-15 #4).
    # Lane-NULL (global) entries are founders' rules — admin-only to decide.
    if not p.get("is_admin") and row["lane"] != p["id"]:
        raise HTTPException(403, "learning belongs to another lane")
    with db.WRITE_LOCK:
        if action == "promote":
            if row["status"] == "active":
                raise HTTPException(409, "already active")
            lane = row["lane"]
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM learnings "
                "WHERE status='active' AND (lane IS NULL OR lane=?)",
                (lane,),
            ).fetchone()["n"]
            if n >= _PLAYBOOK_CAP:
                raise HTTPException(
                    409,
                    f"playbook full ({_PLAYBOOK_CAP}) — dismiss an active entry first",
                )
            text = " ".join((payload.get("text") or row["text"]).split())[:300]
            kind = payload.get("kind") or row["kind"]
            if kind not in ("constraint", "heuristic"):
                raise HTTPException(422, f"invalid kind: {kind!r}")
            # re-run dedupe on the FINAL text — an edited promotion must not
            # smuggle in a duplicate of an existing rule (codex #6)
            dup = conn.execute(
                "SELECT id FROM learnings WHERE status!='dismissed' AND id!=? "
                "AND lower(text)=lower(?) AND (lane IS NULL OR lane IS ? OR lane=?)",
                (lid, text, row["lane"], row["lane"]),
            ).fetchone()
            if dup:
                raise HTTPException(
                    409, f"duplicate of learning l-{dup['id']} — dismiss one"
                )
            conn.execute(
                "UPDATE learnings SET status='active', text=?, kind=?, "
                "decided_by=?, decided_at=? WHERE id=?",
                (text, kind, p["id"], db.now_iso(), lid),
            )
        else:
            conn.execute(
                "UPDATE learnings SET status='dismissed', decided_by=?, decided_at=? "
                "WHERE id=?",
                (p["id"], db.now_iso(), lid),
            )
        db.audit(conn, p["id"], f"learning_{action}", f"l-{lid}")
        conn.commit()
    _broadcast(p["id"])
    row = conn.execute("SELECT * FROM learnings WHERE id=?", (lid,)).fetchone()
    return _learning_json(row)


@app.delete("/api/task/{tid}")
def delete_task(tid: str, p=Depends(human_only)):
    """Hard delete (undo/cleanup). Strips the ref from other tasks' prereqs so
    dependents don't go red on a dangling gate."""
    _check_write(p, "workstreams")
    conn = db.get_conn()
    num = _tid(tid)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        _guard_foreign_agent(row, p)
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
def reorder_tasks(
    payload: dict = Body(...),
    p=Depends(human_only),
):
    """Bulk-update sort_order for a list of task ids (in new display order).
    Payload: {task_ids: ["t-1", "t-3", "t-2", ...]}"""
    _check_write(p, "workstreams")
    task_ids = payload.get("task_ids")
    if not task_ids or not isinstance(task_ids, list):
        raise HTTPException(422, "task_ids list is required")
    conn = db.get_conn()
    with db.WRITE_LOCK:
        for idx, tid_str in enumerate(task_ids):
            num = _tid(tid_str)
            conn.execute(
                "UPDATE tasks SET sort_order=?, updated_at=?, version=version+1 WHERE id=?",
                (idx, db.now_iso(), num),
            )
        db.audit(conn, p["id"], "tasks_reorder", "bulk", after={"task_ids": task_ids})
        conn.commit()
    _broadcast(p["id"])
    return {"reordered": len(task_ids)}


@app.patch("/api/workstreams/reorder")
def reorder_workstreams(
    payload: dict = Body(...),
    p=Depends(human_only),
):
    _check_write(p, "workstreams")
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
def reorder_deliverables(
    payload: dict = Body(...),
    p=Depends(human_only),
):
    _check_write(p, "workstreams")
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
    _check_write(p, "agents")
    conn = db.get_conn()
    num = _tid(tid)
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        _guard_foreign_agent(row, p)
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
def reject(
    tid: str,
    payload: dict = Body(default={}),
    p=Depends(human_only),
):
    _check_write(p, "agents")
    conn = db.get_conn()
    num = _tid(tid)
    comment = payload.get("comment", "")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        _guard_foreign_agent(row, p)
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
def request_changes(
    tid: str,
    payload: dict = Body(...),
    p=Depends(human_only),
):
    """Send task back to agent with structured feedback. Unlike reject (which
    just re-opens), this increments review_round and stores feedback so the
    next agent run gets it as mandatory context."""
    _check_write(p, "agents")
    conn = db.get_conn()
    num = _tid(tid)
    feedback = payload.get("feedback", "")
    if not feedback.strip():
        raise HTTPException(422, "feedback is required for request-changes")
    with db.WRITE_LOCK:
        row = _get_task(conn, num)
        _guard_personal(row, p["id"])
        _guard_foreign_agent(row, p)
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


# no .html: an uploaded HTML file served on the app origin is a stored-XSS
# vector against the reviewer (codex 2026-07-05 #4). md/pdf/png cover the
# real cases — Office artifacts are exported to PDF before upload.
_PREVIEW_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".md")


def _store_preview(conn, actor_id, tid, num, file):
    """Shared by the human and agent upload doors. Returns the preview URL."""
    ext = Path(file.filename or "preview.pdf").suffix.lower()
    if ext not in _PREVIEW_EXTS:
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
            actor_id,
            "preview_upload",
            models.task_id(num),
            after={"preview_url": preview_url, "size": size},
        )
        conn.commit()
    return {"url": preview_url, "size": size}


@app.post("/api/task/{tid}/upload-preview", status_code=201)
def upload_preview(
    tid: str,
    file: UploadFile = File(...),
    p=Depends(human_only),
):
    """Human door for preview files (PDF, PNG, MD). Agents use their own
    claimant-gated door — leaving this open to agent tokens would let any agent
    overwrite any task's preview (codex 2026-07-05 #1)."""
    _check_write(p, "agents")
    conn = db.get_conn()
    num = _tid(tid)
    _get_task(conn, num)
    out = _store_preview(conn, p["id"], tid, num, file)
    _broadcast(p["id"])
    return out


@app.post("/api/agent/upload-preview/{tid}", status_code=201)
def agent_upload_preview(tid: str, file: UploadFile = File(...), p=Depends(agent_only)):
    """Agent door for artifact previews (Caddy exempts /api/agent/* on Bearer).
    Live claimant only, while the task is still in_progress — upload BEFORE
    posting the result; a submitted or lease-expired run cannot rewrite the
    preview under the reviewer (codex 2026-07-05 #2)."""
    conn = db.get_conn()
    num = _tid(tid)
    _reap_expired_claims(conn)
    row = _get_task(conn, num)
    if row["claimed_by"] != p["id"] or row["status"] != "in_progress":
        raise HTTPException(
            409, "not the live claimant — upload previews before result"
        )
    out = _store_preview(conn, p["id"], tid, num, file)
    _broadcast(p["id"])
    return out


@app.get("/api/task/{tid}/preview/{filename}")
def serve_preview(tid: str, filename: str):
    """Serve a stored preview file. No auth — previews are non-sensitive."""
    num = _tid(tid)
    base = (_PREVIEW_DIR / str(num)).resolve()
    path = (base / filename).resolve()
    # Contain the resolved path under the task's preview dir — a filename with
    # '..' (or a backslash segment on Windows dev) must not escape the store.
    if base not in path.parents and path != base:
        raise HTTPException(404, "preview not found")
    if not path.is_file():
        raise HTTPException(404, "preview not found")
    media = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".md": "text/markdown; charset=utf-8",
    }.get(path.suffix.lower(), "application/octet-stream")
    # legacy .html previews (no longer uploadable): force download, never
    # execute on the app origin
    if path.suffix.lower() in (".html", ".htm"):
        return FileResponse(
            path,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
        )
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
    # Same lane-privacy gate as /api/state — the export must never be the side
    # door to foreign agent workflows (codex 2026-07-15 #1).
    if p["role"] == "human" and not p.get("is_admin"):
        _scrub_foreign_agent_tasks(st, p["id"])
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
    # Foreign AGENT tasks go further: for a non-admin human the entry is DROPPED
    # entirely — audit after-fields carry the full task body, and even the
    # entity id enables follow-on reads (codex 2026-07-15 #2).
    task_meta = {}  # entity ref -> live task row (kind, execution, created_by)

    def _task_row(entity):
        if not entity or not entity.startswith("t-"):
            return None
        if entity not in task_meta:
            try:
                _, n = _safe_ref(entity)
                task_meta[entity] = conn.execute(
                    "SELECT kind, execution, created_by FROM tasks WHERE id=?", (n,)
                ).fetchone()
            except Exception:
                task_meta[entity] = None
        return task_meta[entity]

    def _is_other_personal(entity):
        trow = _task_row(entity)
        return bool(
            trow and trow["kind"] == "personal" and trow["created_by"] != p["id"]
        )

    hide_foreign_agent = p["role"] == "human" and not p.get("is_admin")

    def _is_foreign_agent(entity):
        if not hide_foreign_agent:
            return False
        trow = _task_row(entity)
        return bool(
            trow
            and trow["execution"] in models.AGENT_EXECUTIONS
            and trow["created_by"] != p["id"]
        )

    entries = []
    for r in rows:
        if _is_foreign_agent(r["entity"]):
            continue
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
def patch_deal(
    codename: str,
    payload: dict = Body(...),
    p=Depends(human_only),
):
    """Deal stage/note are MASTERED by DEALRoom (dealroom.db) and mirrored
    read-only into cockpit's deal_mirror. Writing them here is silently lost on
    the next sync, so we refuse and point the caller at the source of truth."""
    _check_write(p, "dealroom")
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


# --------------------------------------------------------------------------
# admin: user provisioning, team management, workstream assignment
# Guard: is_admin membership (replaces old profile=='owner' check)


def _require_admin(p: dict) -> None:
    if not p.get("is_admin"):
        raise HTTPException(403, "admin access required")


@app.post("/api/admin/user", status_code=201)
def admin_create_user(payload: dict = Body(...), p=Depends(human_only)):
    _require_admin(p)
    uid = (payload.get("id") or "").strip()
    name = (payload.get("name") or "").strip()
    if not uid or not name:
        raise HTTPException(422, "id and name are required")
    initials = (payload.get("initials") or "").strip() or None
    login_val = (payload.get("login") or "").strip() or None
    all_teams_val = 1 if payload.get("all_teams") else 0
    teams = payload.get("teams") or []
    role = payload.get("role") or "human"
    if role not in ("human", "agent"):
        raise HTTPException(422, "role must be 'human' or 'agent'")
    represents = (payload.get("represents") or "").strip() or None
    conn = db.get_conn()
    if (
        represents
        and not conn.execute(
            "SELECT 1 FROM users WHERE id=? AND role='human'", (represents,)
        ).fetchone()
    ):
        raise HTTPException(
            422, f"represents must be an existing human: {represents!r}"
        )
    if conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        raise HTTPException(409, f"user {uid!r} already exists")
    for tid in teams:
        if not conn.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone():
            raise HTTPException(422, f"unknown team: {tid!r}")
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db.WRITE_LOCK:
        conn.execute(
            "INSERT INTO users (id, name, initials, role, token_hash, login, all_teams, represents) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                uid,
                name,
                initials,
                role,
                token_hash,
                login_val,
                all_teams_val,
                represents,
            ),
        )
        for tid in teams:
            conn.execute(
                "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
                (tid, uid),
            )
        db.audit(conn, p["id"], "user_create", uid, after={"teams": teams})
        conn.commit()
    return {"id": uid, "token": token}


@app.get("/api/admin/overview")
def admin_overview(p=Depends(human_only)):
    _require_admin(p)
    conn = db.get_conn()
    users_rows = conn.execute(
        "SELECT id, name, initials, role, login, all_teams, profile FROM users ORDER BY id"
    ).fetchall()
    members_rows = conn.execute("SELECT team_id, user_id FROM team_members").fetchall()
    teams_rows = conn.execute(
        "SELECT id, name, color, permissions, is_admin, sort_order, status FROM teams ORDER BY sort_order, id"
    ).fetchall()
    wt_rows = conn.execute(
        "SELECT wt.workstream_id, wt.team_id, w.name AS ws_name "
        "FROM workstream_teams wt JOIN workstreams w ON w.id = wt.workstream_id"
    ).fetchall()
    # Build user→teams map
    user_teams: dict = {}
    for m in members_rows:
        user_teams.setdefault(m["user_id"], []).append(m["team_id"])
    users_out = [
        {
            "id": r["id"],
            "name": r["name"],
            "initials": r["initials"],
            "role": r["role"],
            "login": r["login"],
            "all_teams": bool(r["all_teams"]),
            "teams": user_teams.get(r["id"], []),
        }
        for r in users_rows
    ]
    # Build team→members map
    team_members_map: dict = {}
    for m in members_rows:
        team_members_map.setdefault(m["team_id"], []).append(m["user_id"])
    teams_out = [
        {
            "id": r["id"],
            "name": r["name"],
            "color": r["color"],
            "permissions": json.loads(r["permissions"] or "{}"),
            "is_admin": bool(r["is_admin"]),
            "sort_order": r["sort_order"],
            "status": r["status"],
            "members": team_members_map.get(r["id"], []),
        }
        for r in teams_rows
    ]
    # Workstream assignments
    ws_assignments: dict = {}
    for wt in wt_rows:
        ws_assignments.setdefault(
            wt["workstream_id"], {"ws_name": wt["ws_name"], "teams": []}
        )["teams"].append(wt["team_id"])
    return {
        "users": users_out,
        "teams": teams_out,
        "workstream_assignments": ws_assignments,
    }


@app.post("/api/admin/team", status_code=201)
def admin_create_team(payload: dict = Body(...), p=Depends(human_only)):
    _require_admin(p)
    tid = (payload.get("id") or "").strip()
    name = (payload.get("name") or "").strip()
    if not tid or not name:
        raise HTTPException(422, "id and name are required")
    color = payload.get("color") or None
    perms = payload.get("permissions") or {}
    is_admin_val = 1 if payload.get("is_admin") else 0
    conn = db.get_conn()
    if conn.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone():
        raise HTTPException(409, f"team {tid!r} already exists")
    with db.WRITE_LOCK:
        conn.execute(
            "INSERT INTO teams (id, name, color, permissions, is_admin) VALUES (?,?,?,?,?)",
            (tid, name, color, json.dumps(perms), is_admin_val),
        )
        db.audit(
            conn,
            p["id"],
            "team_create",
            tid,
            after={"name": name, "permissions": perms},
        )
        conn.commit()
    return {"id": tid, "name": name}


@app.patch("/api/admin/team/{tid}")
def admin_patch_team(tid: str, payload: dict = Body(...), p=Depends(human_only)):
    _require_admin(p)
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone():
        raise HTTPException(404, f"team {tid!r} not found")
    updates = {}
    if "name" in payload:
        updates["name"] = payload["name"]
    if "color" in payload:
        updates["color"] = payload["color"]
    if "permissions" in payload:
        updates["permissions"] = json.dumps(payload["permissions"])
    if "status" in payload:
        if payload["status"] not in ("active", "archived"):
            raise HTTPException(422, "status must be active or archived")
        updates["status"] = payload["status"]
    if not updates:
        raise HTTPException(422, "no updatable fields provided")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with db.WRITE_LOCK:
        conn.execute(
            f"UPDATE teams SET {set_clause} WHERE id=?",
            (*updates.values(), tid),
        )
        db.audit(conn, p["id"], "team_update", tid, after=updates)
        conn.commit()
    _broadcast(p["id"])
    return {"id": tid, **{k: v for k, v in updates.items()}}


@app.post("/api/admin/team/{tid}/members", status_code=201)
def admin_add_member(tid: str, payload: dict = Body(...), p=Depends(human_only)):
    _require_admin(p)
    uid = (payload.get("user_id") or "").strip()
    if not uid:
        raise HTTPException(422, "user_id is required")
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone():
        raise HTTPException(404, f"team {tid!r} not found")
    if not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        raise HTTPException(404, f"user {uid!r} not found")
    with db.WRITE_LOCK:
        conn.execute(
            "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
            (tid, uid),
        )
        db.audit(conn, p["id"], "team_member_add", f"{tid}/{uid}")
        conn.commit()
    _broadcast(p["id"])
    return {"team_id": tid, "user_id": uid}


@app.delete("/api/admin/team/{tid}/members/{uid}", status_code=200)
def admin_remove_member(tid: str, uid: str, p=Depends(human_only)):
    _require_admin(p)
    conn = db.get_conn()
    with db.WRITE_LOCK:
        conn.execute(
            "DELETE FROM team_members WHERE team_id=? AND user_id=?", (tid, uid)
        )
        db.audit(conn, p["id"], "team_member_remove", f"{tid}/{uid}")
        conn.commit()
    _broadcast(p["id"])
    return {"team_id": tid, "user_id": uid, "removed": True}


@app.patch("/api/admin/user/{uid}")
def admin_patch_user(uid: str, payload: dict = Body(...), p=Depends(human_only)):
    _require_admin(p)
    conn = db.get_conn()
    if not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        raise HTTPException(404, f"user {uid!r} not found")
    with db.WRITE_LOCK:
        if "name" in payload:
            if not (payload["name"] or "").strip():
                raise HTTPException(422, "name must not be empty")
            conn.execute(
                "UPDATE users SET name=? WHERE id=?", (payload["name"].strip(), uid)
            )
        if "initials" in payload:
            conn.execute(
                "UPDATE users SET initials=? WHERE id=?",
                ((payload["initials"] or "").strip() or None, uid),
            )
        if "login" in payload:
            conn.execute(
                "UPDATE users SET login=? WHERE id=?", (payload["login"] or None, uid)
            )
        if "all_teams" in payload:
            conn.execute(
                "UPDATE users SET all_teams=? WHERE id=?",
                (1 if payload["all_teams"] else 0, uid),
            )
        if "teams" in payload:
            teams = payload["teams"] or []
            for tid in teams:
                if not conn.execute(
                    "SELECT 1 FROM teams WHERE id=?", (tid,)
                ).fetchone():
                    raise HTTPException(422, f"unknown team: {tid!r}")
            conn.execute("DELETE FROM team_members WHERE user_id=?", (uid,))
            for tid in teams:
                conn.execute(
                    "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
                    (tid, uid),
                )
        db.audit(
            conn,
            p["id"],
            "user_update",
            uid,
            after={
                k: payload[k]
                for k in ("name", "initials", "login", "all_teams", "teams")
                if k in payload
            },
        )
        conn.commit()
    _broadcast(p["id"])
    return {"id": uid, "updated": True}


@app.patch("/api/workstream/{wid}/teams")
def patch_workstream_teams(wid: str, payload: dict = Body(...), p=Depends(human_only)):
    """Replace workstream team assignment. team_ids=[] clears assignment (visible to all)."""
    _require_admin(p)
    conn = db.get_conn()
    prefix, num = _safe_ref(wid)
    if prefix != "w":
        raise HTTPException(422, "expected w-<n>")
    row = conn.execute("SELECT id FROM workstreams WHERE id=?", (num,)).fetchone()
    if not row:
        raise HTTPException(404, f"{wid} not found")
    team_ids = payload.get("team_ids") or []
    for tid in team_ids:
        if not conn.execute("SELECT 1 FROM teams WHERE id=?", (tid,)).fetchone():
            raise HTTPException(422, f"unknown team: {tid!r}")
    with db.WRITE_LOCK:
        conn.execute("DELETE FROM workstream_teams WHERE workstream_id=?", (num,))
        for tid in team_ids:
            conn.execute(
                "INSERT OR IGNORE INTO workstream_teams (workstream_id, team_id) VALUES (?,?)",
                (num, tid),
            )
        db.audit(
            conn, p["id"], "workstream_teams_update", wid, after={"team_ids": team_ids}
        )
        conn.commit()
    _broadcast(p["id"])
    return {"id": wid, "team_ids": team_ids}


@app.patch("/api/workstream/{wid}/access")
def patch_workstream_access(wid: str, payload: dict = Body(...), p=Depends(human_only)):
    """Deprecated v12 workstream scoping endpoint. Kept for backward compat."""
    _require_admin(p)
    conn = db.get_conn()
    prefix, num = _safe_ref(wid)
    if prefix != "w":
        raise HTTPException(422, "expected w-<n>")
    row = conn.execute("SELECT * FROM workstreams WHERE id=?", (num,)).fetchone()
    if not row:
        raise HTTPException(404, f"{wid} not found")
    allowed_profiles = payload.get("allowed_profiles")
    if allowed_profiles is not None:
        for ap in allowed_profiles:
            if not conn.execute(
                "SELECT 1 FROM role_profiles WHERE id=?", (ap,)
            ).fetchone():
                raise HTTPException(422, f"unknown profile: {ap!r}")
        allowed_profiles_json = json.dumps(allowed_profiles)
    else:
        allowed_profiles_json = None
    with db.WRITE_LOCK:
        conn.execute(
            "UPDATE workstreams SET allowed_profiles=? WHERE id=?",
            (allowed_profiles_json, num),
        )
        db.audit(
            conn,
            p["id"],
            "workstream_access_update",
            wid,
            after={"allowed_profiles": allowed_profiles},
        )
        conn.commit()
    _broadcast(p["id"])
    return {"id": wid, "allowed_profiles": allowed_profiles}


# --------------------------------------------------------------------------
# Calendar
@app.get("/api/calendar/events")
def calendar_events(
    scope: str = Query("me"),
    start: str = Query(None),
    days: int = Query(7),
    p=Depends(principal),
):
    if p["role"] == "agent":
        raise HTTPException(403, "agents cannot access calendar")
    if "calendar" not in p.get("modules", []):
        raise HTTPException(403, "calendar module not enabled")
    conn = db.get_conn()
    today = _today().isoformat()
    days = max(1, min(days, 31))
    try:
        # date (not datetime) — a datetime string would corrupt start_iso below
        start_d = date.fromisoformat(start or today)
    except ValueError:
        raise HTTPException(422, "invalid start date (expect YYYY-MM-DD)")
    start_iso = start_d.isoformat() + "T00:00:00"
    end_iso = (start_d + timedelta(days=days)).isoformat() + "T00:00:00"

    my_id = p["id"]
    my_row = conn.execute("SELECT * FROM users WHERE id=?", (my_id,)).fetchone()
    my_upn = my_row["calendar_upn"] if my_row else None

    if scope == "me":
        upn_map = {my_id: my_upn} if my_upn else {}
    else:
        # team scope: self + users sharing >=1 active team
        my_teams = set(
            r["team_id"]
            for r in conn.execute(
                "SELECT team_id FROM team_members WHERE user_id=?", (my_id,)
            ).fetchall()
        )
        if not my_teams and not p.get("all_teams"):
            upn_map = {my_id: my_upn} if my_upn else {}
        else:
            if p.get("all_teams"):
                rows = conn.execute(
                    "SELECT id, name, initials, calendar_upn FROM users WHERE role='human'"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT u.id, u.name, u.initials, u.calendar_upn "
                    "FROM users u JOIN team_members tm ON tm.user_id = u.id "
                    "WHERE tm.team_id IN ({}) AND u.role='human'".format(
                        ",".join("?" * len(my_teams))
                    ),
                    tuple(my_teams),
                ).fetchall()
            upn_map = {r["id"]: r["calendar_upn"] for r in rows if r["calendar_upn"]}
            if my_upn:
                upn_map[my_id] = my_upn

    # Build users list (all team members, mark connected)
    if scope == "me":
        user_rows = [my_row] if my_row else []
    else:
        if p.get("all_teams"):
            user_rows = conn.execute(
                "SELECT id, name, initials, calendar_upn FROM users WHERE role='human'"
            ).fetchall()
        else:
            if my_teams:
                user_rows = conn.execute(
                    "SELECT DISTINCT u.id, u.name, u.initials, u.calendar_upn "
                    "FROM users u JOIN team_members tm ON tm.user_id = u.id "
                    "WHERE tm.team_id IN ({}) AND u.role='human'".format(
                        ",".join("?" * len(my_teams))
                    ),
                    tuple(my_teams),
                ).fetchall()
            else:
                user_rows = [my_row] if my_row else []

    users_out = [
        {
            "id": r["id"],
            "name": r["name"],
            "initials": r["initials"],
            "connected": bool(r["calendar_upn"]),
        }
        for r in user_rows
    ]

    # Fetch events
    upns_to_fetch = list(upn_map.values())
    upn_to_uid = {v: k for k, v in upn_map.items()}
    uid_to_row = {
        r["id"]: r for r in (user_rows if user_rows else [my_row] if my_row else [])
    }

    raw_events = (
        calendar_graph.fetch_events(upns_to_fetch, start_iso, end_iso)
        if upns_to_fetch
        else []
    )

    # Determine status
    fake = os.environ.get("COCKPIT_CALENDAR_FAKE") == "1"
    if fake or (
        os.environ.get("COCKPIT_GRAPH_TENANT")
        and os.environ.get("COCKPIT_GRAPH_CLIENT_ID")
    ):
        status = "ok"
    else:
        status = "not_configured"

    # Configured but zero events came back for connected users: distinguish a
    # genuinely empty week from a silent Graph auth failure (fetch swallows
    # per-upn errors), so the admin consent card can actually surface.
    if status == "ok" and not fake and upns_to_fetch and not raw_events:
        # probe the caller's own upn when connected — per-mailbox access policies
        # could 403 a teammate while the caller's calendar works fine
        probe_target = my_upn if my_upn in upns_to_fetch else upns_to_fetch[0]
        probe_ok, probe_reason = calendar_graph.probe_upn(probe_target)
        if not probe_ok and probe_reason in ("consent_missing", "not_configured"):
            status = probe_reason

    events_out = []
    for ev in raw_events:
        upn = ev["upn"]
        uid = upn_to_uid.get(upn)
        if not uid:
            continue
        urow = uid_to_row.get(uid)
        is_self = uid == my_id
        private = ev.get("private", False)
        subject = ev["subject"] if (not private or is_self) else "Private"
        location = ev.get("location", "") if (not private or is_self) else ""
        online_url = ev.get("online_url") if (not private or is_self) else None
        events_out.append(
            {
                "user": {
                    "id": uid,
                    "name": urow["name"] if urow else uid,
                    "initials": urow["initials"] if urow else uid[:2].upper(),
                },
                "subject": subject,
                "start": ev["start"],
                "end": ev["end"],
                "all_day": ev.get("all_day", False),
                "location": location,
                "private": private,
                "online_url": online_url,
                "show_as": ev.get("show_as", "busy"),
            }
        )

    events_out.sort(key=lambda e: e["start"])
    return {"status": status, "users": users_out, "events": events_out}


@app.post("/api/calendar/connect")
def calendar_connect(payload: dict = Body(...), p=Depends(human_only)):
    upn = (payload.get("upn") or "").strip()
    conn = db.get_conn()
    if upn:
        # format gate before any Graph call — a stored upn feeds URL paths
        if not calendar_graph.UPN_RE.match(upn):
            raise HTTPException(422, "unknown_upn")
        ok, reason = calendar_graph.probe_upn(upn)
        if not ok:
            if reason == "not_configured":
                raise HTTPException(503, "Calendar backend not configured")
            if reason == "consent_missing":
                raise HTTPException(422, "consent_missing")
            if reason == "unknown_upn":
                raise HTTPException(422, "unknown_upn")
            # don't echo raw Graph status codes to the browser
            raise HTTPException(422, "probe_failed")
    with db.WRITE_LOCK:
        conn.execute(
            "UPDATE users SET calendar_upn=? WHERE id=?",
            (upn or None, p["id"]),
        )
        db.audit(conn, p["id"], "calendar_connect", p["id"], after={"upn": upn or None})
        conn.commit()
    return {"status": "ok", "upn": upn or None}
