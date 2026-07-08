"""FastAPI app for the Investor Room (boardroom).
Principal resolution mirrors Cockpit: trust X-Remote-User from Caddy, else Bearer token.
Investor role sees only published rows. Admin sees all.
"""

import hashlib
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
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
_BOOTSTRAP_USERS = [
    ("rd", "Roman", "RD", "admin"),
    ("ff", "Florian", "FF", "admin"),
    ("strada", "Strada", "ST", "investor"),
]


@asynccontextmanager
async def lifespan(app):
    conn = db.get_conn()
    with db.WRITE_LOCK:
        for uid, name, initials, role in _BOOTSTRAP_USERS:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
                (uid, name, initials, role),
            )
        conn.commit()
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


@app.get("/api/inline-edits")
def get_inline_edits(p=Depends(principal)):
    """All inline overrides. Both admin and investor see saved edits."""
    rows = db.get_conn().execute("SELECT edit_id, content FROM inline_edits").fetchall()
    return {"edits": {r["edit_id"]: r["content"] for r in rows}}


@app.post("/api/inline-edit")
def post_inline_edit(payload: dict, p=Depends(admin_only)):
    """Upsert a single inline edit. Admin only. Audited."""
    edit_id = payload.get("edit_id")
    content = payload.get("content")
    if not edit_id or not isinstance(edit_id, str) or len(edit_id) > 64:
        raise HTTPException(422, "edit_id required (string, max 64 chars)")
    if content is None or not isinstance(content, str):
        raise HTTPException(422, "content required (string)")
    now = db.now_iso()
    with db.WRITE_LOCK:
        conn = db.get_conn()
        old = conn.execute(
            "SELECT content FROM inline_edits WHERE edit_id=?", (edit_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO inline_edits (edit_id, content, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(edit_id) DO UPDATE SET "
            "content=excluded.content, updated_by=excluded.updated_by, "
            "updated_at=excluded.updated_at",
            (edit_id, content, p["id"], now),
        )
        conn.commit()
    _audit(
        p["id"],
        "inline_edit",
        f"edit:{edit_id}",
        {"content": old["content"]} if old else None,
        {"content": content},
    )
    return {"ok": True, "edit_id": edit_id}


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


# ---------------------------------------------------------------------------
# Investor-view page assembly (SPEC-investor-split.md)
# static/index.html was split into templates/ (shell + per-act sections + per-deal
# files). Deal files hold one fragment per view behind <!-- ONEPAGER --> etc.
# markers; act2-shell.html carries {{ONEPAGER}}-style placeholders. Assembly is
# pure concatenation — output is byte-identical to the pre-split monolith
# (static/index.html.pre-split.bak).

_TPL = os.path.join(os.path.dirname(__file__), "..", "templates")
_PAGE_SECTIONS = ("ONEPAGER", "SCORECARD", "SU", "VALUATION")
_PAGE_DEALS = ("_overview", "fox", "mantis", "cat", "mouse")
_MARKER_RE = re.compile(r"^<!--\s*(ONEPAGER|SCORECARD|SU|VALUATION)\s*-->\s*$")


def _tpl(rel: str) -> str:
    # newline="" — templates are CRLF; keep bytes exact, no translation
    with open(os.path.join(_TPL, rel), encoding="utf-8", newline="") as f:
        return f.read()


def _parse_deal(name: str) -> dict:
    """Split deals/<name>.html on section markers → {SECTION: fragment}."""
    parts, current, buf = {}, None, []
    for line in _tpl(f"deals/{name}.html").splitlines(keepends=True):
        m = _MARKER_RE.match(line)
        if m:
            if current:
                parts[current] = "".join(buf)
            current, buf = m.group(1), []
        else:
            buf.append(line)
    if current:
        parts[current] = "".join(buf)
    return parts


def _assemble_page() -> str:
    deals = [_parse_deal(n) for n in _PAGE_DEALS]
    act2 = _tpl("sections/act2-shell.html")
    for sec in _PAGE_SECTIONS:
        act2 = act2.replace("{{%s}}\r\n" % sec, "".join(d.get(sec, "") for d in deals))
    return "".join(
        [
            _tpl("shell-top.html"),
            _tpl("sections/act1-thisweek.html"),
            act2,
            _tpl("sections/act3-pipeline.html"),
            _tpl("sections/act4-timeline.html"),
            _tpl("shell-bottom.html"),
        ]
    )


@app.get("/")
def index(
    week: str | None = Query(default=None),
    x_remote_user: str | None = Header(default=None),
):
    is_investor = x_remote_user == "investor"

    if week:  # legacy ?week= links; dated path URLs are canonical
        iso = _iso_from_ref(week)
        if not iso:
            raise HTTPException(404, "no investor view for that week")
        return _serve_archived_week(iso, is_investor)

    if is_investor:
        return _serve_published_view(True)

    return HTMLResponse(_inject_draft_toolbar(_assemble_page()))


@app.get("/{ref_date}")
def week_page(ref_date: str, x_remote_user: str | None = Header(default=None)):
    """Dated static snapshot URL: /260702 (external: /investor/260702).
    Published weeks live here forever; only 6-digit refs match."""
    if not re.fullmatch(r"\d{6}", ref_date):
        raise HTTPException(404, "not found")
    iso = _iso_from_ref(ref_date)
    return _serve_archived_week(iso, x_remote_user == "investor")


@app.post("/api/investor-view/publish")
def publish_investor_view(p=Depends(admin_only)):
    """Freeze the current draft as this week's static snapshot: templates +
    inline edits → published investor_view at its dated URL. Archives the
    previous published week, runs the denylist scan, then CLEARS inline_edits —
    edits are week-scoped (frozen into the snapshot; the next draft starts
    clean from templates, no cross-week bleed)."""
    html = _assemble_page()

    rows = db.get_conn().execute("SELECT edit_id, content FROM inline_edits").fetchall()
    inline_edits = {r["edit_id"]: r["content"] for r in rows}

    body = {"html": html, "inline_edits": inline_edits}

    hard = gates.scan_other_investors(body)
    if hard:
        raise HTTPException(409, {"hard_violations": hard})

    now = db.now_iso()
    ref = now[:10]

    with db.WRITE_LOCK:
        conn = db.get_conn()
        conn.execute(
            "UPDATE publications SET status='archived' "
            "WHERE kind='investor_view' AND status='published'"
        )
        cur = conn.execute(
            "INSERT INTO publications "
            "(kind, ref, title, status, body, created_at, published_at, version) "
            "VALUES ('investor_view', ?, 'Investor View', 'published', ?, ?, ?, 1)",
            (ref, json.dumps(body), now, now),
        )
        cleared = conn.execute("DELETE FROM inline_edits").rowcount
        conn.commit()
        pub_id = cur.lastrowid

    _audit(
        p["id"],
        "publish_investor_view",
        f"pub:{pub_id}",
        None,
        {"ref": ref, "status": "published", "inline_edits_cleared": cleared},
    )
    return {
        "id": pub_id,
        "status": "published",
        "ref": ref,
        "url": _yymmdd(ref),
        "published_at": now,
        "inline_edits_cleared": cleared,
    }


@app.post("/api/investor-view/unpublish")
def unpublish_investor_view(p=Depends(admin_only)):
    """Archive the published investor_view. Investor sees holding page."""
    with db.WRITE_LOCK:
        conn = db.get_conn()
        row = conn.execute(
            "SELECT id FROM publications "
            "WHERE kind='investor_view' AND status='published'"
        ).fetchone()
        if not row:
            raise HTTPException(404, "no published investor view")
        conn.execute(
            "UPDATE publications SET status='archived' WHERE id=?",
            (row["id"],),
        )
        conn.commit()
    _audit(
        p["id"],
        "unpublish_investor_view",
        f"pub:{row['id']}",
        {"status": "published"},
        {"status": "archived"},
    )
    return {"ok": True, "id": row["id"], "status": "archived"}


@app.get("/api/investor-view/weeks")
def investor_view_weeks(p=Depends(principal)):
    """Published/archived investor_view history for week switching."""
    rows = (
        db.get_conn()
        .execute(
            "SELECT id, ref, status, published_at FROM publications "
            "WHERE kind='investor_view' AND status IN ('published','archived') "
            "ORDER BY published_at DESC"
        )
        .fetchall()
    )
    return {"weeks": [dict(r) for r in rows]}


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


# ---------------------------------------------------------------------------
# Investor-view draft/publish helpers
#
# URL model (Roman, 08-07): published weeks are STATIC snapshots at dated URLs
# (/investor/260702); the draft at / is DYNAMIC (assembled per request) and
# becomes the next dated snapshot on publish. The week switcher is the SAME
# for admin and investor — only the "home" option differs (draft vs latest).

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _iso_from_ref(ref: str) -> str | None:
    """Accept '260702' (URL form) or '2026-07-02' (DB form) → ISO, else None.
    Calendar-validated so a malformed ref fails closed (404) instead of
    crashing label rendering downstream."""
    if re.fullmatch(r"\d{6}", ref):
        iso = "20%s-%s-%s" % (ref[:2], ref[2:4], ref[4:6])
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", ref):
        iso = ref
    else:
        return None
    try:
        datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return None
    return iso


def _yymmdd(iso: str) -> str:
    return iso[2:4] + iso[5:7] + iso[8:10]


def _ref_label(iso: str) -> str:
    """Investor-facing label: '2026-07-02' → '02 Jul 2026'. Falls back to the
    raw ref if a stored value is not a valid date (manual DB writes) — a bad
    row must never 500 the page."""
    try:
        y, m, d = iso.split("-")
        return "%s %s %s" % (d, _MONTHS[int(m) - 1], y)
    except (ValueError, IndexError):
        return iso


# Relative targets: './260702' resolves under /investor/ behind Caddy; a
# root-absolute '/?week=' would land on the suite landing page.
_ARCHIVE_JS = (
    "if(!this.value)return;"
    "if(this.value==='__home'){location='./'}else{location='./'+this.value}"
)


def _archive_select_html(is_investor: bool, light_bg: bool = False) -> str:
    """Compact 'Archive' dropdown that lives INSIDE the existing blue topline —
    NEVER an additional bar (Roman 08-07: the page already has a topline; the
    current week is labelled by the topline date itself, so no duplication).
    Same control for both roles; only the home option differs."""
    home = "Latest published" if is_investor else "Current draft"
    opts = [
        '<option value="" disabled selected hidden>Archive</option>',
        '<option value="__home" style="color:#111">%s</option>' % home,
    ]
    rows = (
        db.get_conn()
        .execute(
            "SELECT ref, status FROM publications "
            "WHERE kind='investor_view' AND status IN ('published','archived') "
            "ORDER BY published_at DESC"
        )
        .fetchall()
    )
    seen = set()
    for r in rows:
        if r["ref"] in seen:
            continue
        seen.add(r["ref"])
        live = " (live)" if r["status"] == "published" else ""
        opts.append(
            '<option value="%s" style="color:#111">%s%s</option>'
            % (_yymmdd(r["ref"]), _ref_label(r["ref"]), live)
        )
    style = (
        "color:#0f172a;background:#f8fafc;border:1px solid #cbd5e1;"
        if light_bg
        else "color:#fff;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.35);"
    )
    return (
        '<select id="wk-archive" onchange="' + _ARCHIVE_JS + '" '
        'style="' + style + "border-radius:6px;padding:4px 10px;"
        'font-size:12px;cursor:pointer;font-family:inherit">'
        + "".join(opts)
        + "</select>"
    )


def _draft_controls_html() -> str:
    """Admin draft chrome = ONE Publish button, nothing else (Roman 08-07:
    no chips, no extra buttons — EDIT MODE badge already marks the draft and
    the Archive '(live)' option already shows what investors see). Unpublish
    stays API-only: POST /api/investor-view/unpublish."""
    return (
        '<div id="iv-draft" style="display:flex;align-items:center">'
        '<button onclick="_pubIV()" style="background:#fff;color:#0891B2;border:none;'
        'padding:5px 14px;border-radius:6px;font-weight:700;font-size:12px;cursor:pointer">Publish</button>'
        "</div>"
        "<script>"
        "function _pubIV(){if(!confirm('Publish to investors? Inline edits are frozen into this week and cleared for the next.'))return;"
        "fetch('api/investor-view/publish',{method:'POST',credentials:'include'})"
        ".then(function(r){return r.json()}).then(function(d){"
        "if(d.status==='published'){alert('Published');location.reload()}"
        "else alert('Error: '+(d.detail||JSON.stringify(d)))"
        "}).catch(function(e){alert('Error: '+e)})}"
        "</script>"
    )


def _inject_topline(html: str, controls: str) -> str:
    """Insert controls INTO the existing blue topline, LEFT of the .meta block.
    The meta ('Investor View / Weekly call · date') keeps its far-right anchor
    (Roman 08-07 review 2: date stays right, Archive sits left of it); the
    controls wrapper takes over meta's auto left-margin."""
    wrapper = (
        '<div id="iv-controls" style="margin-left:auto;display:flex;'
        'align-items:center;gap:8px">' + controls + "</div>"
        "<style>.topbar .meta{margin-left:0}</style>"
    )
    out, n = re.subn(
        r'<div class="meta">',
        lambda m: wrapper + m.group(0),
        html,
        count=1,
    )
    return out if n else html


def _holding_page(is_investor: bool) -> str:
    """No published week: message + the standard Archive control (no topline
    exists on this minimal page, so the select sits under the message)."""
    return (
        "<!DOCTYPE html><html><head><title>Investor View</title></head>"
        '<body style="font-family:system-ui;display:flex;flex-direction:column;'
        'align-items:center;justify-content:center;height:100vh;margin:0;color:#64748b">'
        "<h2>No published content available</h2>"
        '<div style="margin-top:12px">'
        + _archive_select_html(is_investor, light_bg=True)
        + "</div></body></html>"
    )


def _serve_published_view(is_investor: bool = True):
    """Serve the latest published week (static snapshot) with the week switcher."""
    row = (
        db.get_conn()
        .execute(
            "SELECT ref, body FROM publications "
            "WHERE kind='investor_view' AND status='published' "
            "ORDER BY published_at DESC LIMIT 1"
        )
        .fetchone()
    )
    if not row:
        return HTMLResponse(_holding_page(is_investor))
    body = json.loads(row["body"])
    html = _inject_published_script(body["html"], body.get("inline_edits", {}))
    return HTMLResponse(_inject_topline(html, _archive_select_html(is_investor)))


def _serve_archived_week(week_iso: str, is_investor: bool = True):
    """Serve a specific week's static snapshot (published or archived)."""
    row = (
        db.get_conn()
        .execute(
            "SELECT body FROM publications "
            "WHERE kind='investor_view' AND ref=? "
            "AND status IN ('published','archived') "
            "ORDER BY published_at DESC LIMIT 1",
            (week_iso,),
        )
        .fetchone()
    )
    if not row:
        raise HTTPException(404, "no investor view for that week")
    body = json.loads(row["body"])
    html = _inject_published_script(body["html"], body.get("inline_edits", {}))
    return HTMLResponse(_inject_topline(html, _archive_select_html(is_investor)))


def _inject_published_script(html: str, edits: dict) -> str:
    """Inject frozen-edit globals before </head> so shell-bottom.html JS uses them."""
    script = (
        "<script>window.__INVESTOR_VIEW_PUBLISHED=true;"
        "window.__FROZEN_EDITS="
        + json.dumps(edits, ensure_ascii=False)
        + ";</script>\n"
    )
    return html.replace("</head>", script + "</head>", 1)


def _inject_draft_toolbar(html: str) -> str:
    """Admin draft chrome: DRAFT chip + Publish/Unpublish + Archive select,
    all INSIDE the existing blue topline (no injected bars)."""
    return _inject_topline(html, _draft_controls_html() + _archive_select_html(False))
