"""FastAPI app for the Investor Room (boardroom).
Principal resolution mirrors Cockpit: trust X-Remote-User from Caddy, else Bearer token.
Investor role sees only published rows. Admin sees all.
"""

import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import assemble as _assemble
from . import db
from . import (
    gates,
)  # content gates: scan_other_investors, check_pre_loi_names, validate_body

log = logging.getLogger("investor")

# ---------------------------------------------------------------------------
# Caddy username → internal user id
_CADDY_USER_MAP = {"roman": "rd", "florian": "ff", "investor": "strada"}

_STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    db.get_conn()  # ensure schema exists at startup
    yield


app = FastAPI(title="Repuro Investor Room", version="0.1.0", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=_STATIC),
    name="static",
)


# ---------------------------------------------------------------------------
# auth
def principal(
    authorization: str | None = Header(default=None),
    x_remote_user: str | None = Header(default=None),
):
    """Resolve caller to a users row dict, or raise 401."""
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
        raise HTTPException(401, "missing or invalid token")
    token_hash = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    row = (
        db.get_conn()
        .execute("SELECT id, role FROM users WHERE token_hash = ?", (token_hash,))
        .fetchone()
    )
    if not row:
        raise HTTPException(401, "unknown token")
    return {"id": row["id"], "role": row["role"]}


def admin_only(p=Depends(principal)):
    if p["role"] != "admin":
        raise HTTPException(403, "admin only")
    return p


# ---------------------------------------------------------------------------
# routes
@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/api/published")
def get_published(
    kind: str = Query(..., description="weekly_update or board_pack"),
    p=Depends(principal),
):
    """Latest published row for a given kind. Readable by admin AND investor.
    Returns {"empty": true} when no published row exists — never returns draft/approved/archived.
    The investor-facing payload is allowlisted (kind, ref, title, published_at, body) so
    internal metadata (id, status, approved_by, version, timestamps) never leaks."""
    if kind not in ("weekly_update", "board_pack"):
        raise HTTPException(422, "kind must be weekly_update or board_pack")
    row = (
        db.get_conn()
        .execute(
            "SELECT * FROM publications WHERE kind=? AND status='published' "
            "ORDER BY published_at DESC, id DESC LIMIT 1",
            (kind,),
        )
        .fetchone()
    )
    if not row:
        return {"empty": True}
    return _investor_pub(row)


@app.get("/api/publications")
def list_publications(p=Depends(admin_only)):
    """List all publications (id, kind, ref, title, status). Admin only."""
    rows = (
        db.get_conn()
        .execute(
            "SELECT id, kind, ref, title, status FROM publications ORDER BY id DESC"
        )
        .fetchall()
    )
    return {"publications": [dict(r) for r in rows]}


@app.get("/api/publication/{pub_id}")
def get_publication(pub_id: int, p=Depends(admin_only)):
    """Full publication row by id. Admin only."""
    row = (
        db.get_conn()
        .execute("SELECT * FROM publications WHERE id=?", (pub_id,))
        .fetchone()
    )
    if not row:
        raise HTTPException(404, "publication not found")
    return _pub_row(row)


@app.post("/api/assemble")
def post_assemble(
    kind: str = Query(..., description="weekly_update or board_pack"),
    p=Depends(admin_only),
):
    """Assemble a DRAFT publication from live source DBs. Admin only.
    Creates a new row with status='draft' — does NOT auto-publish.
    Returns {id, kind, status:'draft'}."""
    if kind not in ("weekly_update", "board_pack"):
        raise HTTPException(422, "kind must be weekly_update or board_pack")

    if kind == "weekly_update":
        body = _assemble.assemble_weekly_update()
    else:
        body = _assemble.assemble_board_pack()

    now = db.now_iso()
    ref = now[:10]  # ISO date portion e.g. "2026-06-20"
    title = (
        f"{'Weekly Update' if kind == 'weekly_update' else 'Board Pack'} {ref} (draft)"
    )

    with db.WRITE_LOCK:
        conn = db.get_conn()
        cur = conn.execute(
            "INSERT INTO publications (kind, ref, title, status, body, created_at, version) "
            "VALUES (?, ?, ?, 'draft', ?, ?, 1)",
            (kind, ref, title, json.dumps(body), now),
        )
        conn.commit()
        pub_id = cur.lastrowid

    return {"id": pub_id, "kind": kind, "status": "draft"}


@app.get("/api/config")
def config():
    """Unauthenticated bootstrap flag: tells the SPA whether local dev-auth is on
    (enables the browser-side role switcher). Always false in production."""
    return {"dev_mode": bool(os.environ.get("INVESTOR_DEV_MODE"))}


@app.get("/api/whoami")
def whoami(p=Depends(principal)):
    """Return {id, role} for the calling principal. Readable by admin AND investor."""
    return {"id": p["id"], "role": p["role"]}


@app.patch("/api/publication/{pub_id}")
def patch_publication(pub_id: int, payload: dict, p=Depends(admin_only)):
    """Edit title, ref, and/or body of a DRAFT publication. Rejects non-draft (409).
    Full body replacement when body is provided. Bumps version. Audited.
    Read-check-update runs inside WRITE_LOCK with a status-guarded UPDATE so a concurrent
    approve cannot let an edit land after approval (no TOCTOU)."""
    allowed = {"title", "ref", "body"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise HTTPException(422, f"unknown fields: {sorted(unknown)}")
    if not payload:
        raise HTTPException(422, "no fields to update")

    with db.WRITE_LOCK:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM publications WHERE id=?", (pub_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "publication not found")
        if row["status"] != "draft":
            raise HTTPException(
                409, f"can only edit draft publications; status is '{row['status']}'"
            )
        before = _pub_row(row)

        updates = []
        params = []
        if "title" in payload:
            updates.append("title=?")
            params.append(payload["title"])
        if "ref" in payload:
            updates.append("ref=?")
            params.append(payload["ref"])
        if "body" in payload:
            updates.append("body=?")
            params.append(json.dumps(payload["body"]))
        updates.append("version=version+1")
        params.append(pub_id)
        cur = conn.execute(
            f"UPDATE publications SET {', '.join(updates)} WHERE id=? AND status='draft'",
            params,
        )
        conn.commit()
        if cur.rowcount != 1:
            raise HTTPException(409, "publication status changed concurrently")
        updated_row = conn.execute(
            "SELECT * FROM publications WHERE id=?", (pub_id,)
        ).fetchone()

    after = _pub_row(updated_row)
    _audit(p["id"], "patch_publication", f"pub:{pub_id}", before, after)
    return after


@app.get("/api/publication/{pub_id}/diff")
def diff_publication(pub_id: int, p=Depends(admin_only)):
    """Structural diff of this row's body vs the current published row of the same kind.
    Returns {added:[paths], removed:[paths], changed:[{path,from,to}]}.
    If no published baseline exists, returns everything as 'added'."""
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM publications WHERE id=?", (pub_id,)).fetchone()
    if not row:
        raise HTTPException(404, "publication not found")

    body_new = _parse_body(row)

    published = conn.execute(
        "SELECT * FROM publications WHERE kind=? AND status='published' ORDER BY published_at DESC LIMIT 1",
        (row["kind"],),
    ).fetchone()

    if not published:
        # No baseline: everything is 'added'
        added = list(_leaf_paths(body_new))
        return {"added": added, "removed": [], "changed": []}

    body_old = _parse_body(published)
    return _diff_bodies(body_old, body_new)


@app.post("/api/publication/{pub_id}/approve")
def approve_publication(
    pub_id: int,
    payload: dict,
    force: bool = Query(default=False),
    p=Depends(admin_only),
):
    """Approve a draft publication. Requires full human checklist acks + automated gates.

    Gate hardness split:
      HARD (never overridable): scan_other_investors, check_pre_loi_names, validate_body —
        these protect "never published" content classes. A hit is always 409.
      SOFT (force-overridable, audited): check_figures_stamped — a completeness warning.
    Read-check-update runs inside WRITE_LOCK with a status-guarded UPDATE (no TOCTOU)."""
    now = db.now_iso()
    with db.WRITE_LOCK:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM publications WHERE id=?", (pub_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "publication not found")
        if row["status"] != "draft":
            raise HTTPException(
                409, f"can only approve draft publications; status is '{row['status']}'"
            )

        checklist = payload.get("checklist", {})
        required_acks = ["no_pre_loi_names", "no_other_investors", "figures_stamped"]
        missing_acks = [k for k in required_acks if not checklist.get(k)]
        if missing_acks:
            raise HTTPException(400, {"missing_acks": missing_acks})

        body = _parse_body(row)
        # HARD gates — never overridable, even with force.
        hard = (
            gates.check_pre_loi_names(body)
            + gates.scan_other_investors(body)
            + gates.validate_body(row["kind"], body)
        )
        if hard:
            raise HTTPException(409, {"hard_violations": hard})

        # SOFT gate — force-overridable.
        soft = gates.check_figures_stamped(body)
        if soft and not force:
            raise HTTPException(
                409,
                {
                    "soft_violations": soft,
                    "hint": "re-run with ?force=1 to override (audited)",
                },
            )
        body_sha = _body_hash(body)
        if soft and force:
            _audit(
                p["id"],
                "approve_force_override",
                f"pub:{pub_id}",
                None,
                {"soft_violations": soft, "body_sha256": body_sha},
            )

        cur = conn.execute(
            "UPDATE publications SET status='approved', approved_at=?, approved_by=? "
            "WHERE id=? AND status='draft'",
            (now, p["id"], pub_id),
        )
        conn.commit()
        if cur.rowcount != 1:
            raise HTTPException(409, "publication status changed concurrently")

    _audit(
        p["id"],
        "approve_publication",
        f"pub:{pub_id}",
        {"status": "draft"},
        {
            "status": "approved",
            "checklist": checklist,
            "force": force,
            "body_sha256": body_sha,
        },
    )
    return {
        "id": pub_id,
        "status": "approved",
        "approved_at": now,
        "approved_by": p["id"],
        "body_sha256": body_sha,
    }


@app.post("/api/publication/{pub_id}/publish")
def publish_publication(pub_id: int, p=Depends(admin_only)):
    """Publish an approved publication. Re-runs ALL HARD gates (denylist + pre-LOI names +
    validate_body) — no force at publish, this is the real wall. Archives any existing
    published row of the same kind. Read-check-archive-publish is one WRITE_LOCK transaction
    with a status-guarded UPDATE (no TOCTOU, respects the partial unique index)."""
    now = db.now_iso()
    with db.WRITE_LOCK:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT * FROM publications WHERE id=?", (pub_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "publication not found")
        if row["status"] != "approved":
            raise HTTPException(
                409,
                f"can only publish approved publications; status is '{row['status']}'",
            )

        body = _parse_body(row)
        hard = (
            gates.check_pre_loi_names(body)
            + gates.scan_other_investors(body)
            + gates.validate_body(row["kind"], body)
        )
        if hard:
            raise HTTPException(409, {"hard_violations": hard})

        conn.execute(
            "UPDATE publications SET status='archived' WHERE kind=? AND status='published'",
            (row["kind"],),
        )
        cur = conn.execute(
            "UPDATE publications SET status='published', published_at=? "
            "WHERE id=? AND status='approved'",
            (now, pub_id),
        )
        conn.commit()
        if cur.rowcount != 1:
            raise HTTPException(409, "publication status changed concurrently")

    _audit(
        p["id"],
        "publish_publication",
        f"pub:{pub_id}",
        {"status": "approved"},
        {"status": "published", "published_at": now, "body_sha256": _body_hash(body)},
    )
    return {"id": pub_id, "status": "published", "published_at": now}


@app.post("/api/publication/{pub_id}/unpublish")
def unpublish_publication(pub_id: int, p=Depends(admin_only)):
    """Move a published publication to 'archived'. Fast rollback for bad updates."""
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM publications WHERE id=?", (pub_id,)).fetchone()
    if not row:
        raise HTTPException(404, "publication not found")
    if row["status"] != "published":
        raise HTTPException(
            409, f"can only unpublish published rows; status is '{row['status']}'"
        )

    with db.WRITE_LOCK:
        conn.execute(
            "UPDATE publications SET status='archived' WHERE id=?",
            (pub_id,),
        )
        conn.commit()

    _audit(
        p["id"],
        "unpublish_publication",
        f"pub:{pub_id}",
        {"status": "published"},
        {"status": "archived"},
    )
    return {"id": pub_id, "status": "archived"}


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC, "index.html"), media_type="text/html")


# ---------------------------------------------------------------------------
# Helpers


def _body_hash(body) -> str:
    """Stable sha256 of a body — lets the audit log answer 'what exact JSON was approved?'."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _audit(actor: str, action: str, entity: str, before, after):
    """Write one row to audit_log. before/after are JSON-serialisable or None."""
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO audit_log (at, actor, action, entity, before, after) VALUES (?,?,?,?,?,?)",
        (
            db.now_iso(),
            actor,
            action,
            entity,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
        ),
    )
    conn.commit()


def _leaf_paths(obj, prefix=""):
    """Yield dot-bracket paths for every leaf value in obj."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaf_paths(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaf_paths(v, f"{prefix}[{i}]")
    else:
        yield prefix


def _diff_bodies(old: dict, new: dict) -> dict:
    """Leaf-path diff between two body dicts.
    Returns {added:[...], removed:[...], changed:[{path, from, to}]}."""
    old_leaves = dict(_leaf_pairs(old))
    new_leaves = dict(_leaf_pairs(new))

    old_paths = set(old_leaves)
    new_paths = set(new_leaves)

    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    changed = []
    for path in sorted(old_paths & new_paths):
        if old_leaves[path] != new_leaves[path]:
            changed.append(
                {"path": path, "from": old_leaves[path], "to": new_leaves[path]}
            )

    return {"added": added, "removed": removed, "changed": changed}


def _leaf_pairs(obj, prefix=""):
    """Yield (path, value) for every leaf in obj."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaf_pairs(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaf_pairs(v, f"{prefix}[{i}]")
    else:
        yield prefix, obj


def _parse_body(row):
    """Parse a publication body JSON. Fail loud on corruption rather than silently
    returning {} — a broken published record must not look like a valid empty one."""
    try:
        return json.loads(row["body"])
    except (TypeError, ValueError) as e:
        # Log the id server-side; never expose internal metadata to the caller.
        log.error("corrupt publication body (id=%s): %s", row["id"], e)
        raise HTTPException(500, "corrupt publication body") from e


def _pub_row(row):
    """Full row for ADMIN routes only — includes all metadata."""
    d = dict(row)
    d["body"] = _parse_body(row)
    return d


# Investor-facing allowlist — only these fields ever reach the investor principal.
_INVESTOR_FIELDS = ("kind", "ref", "title", "published_at")


def _investor_pub(row):
    """Allowlisted payload for the investor. No id/status/approved_by/version/timestamps
    beyond published_at; only curated published content."""
    out = {k: row[k] for k in _INVESTOR_FIELDS}
    out["body"] = _parse_body(row)
    return out
