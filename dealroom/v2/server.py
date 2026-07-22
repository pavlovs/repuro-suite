"""DEALROOM v2 — FastAPI app (spec §3): read views + authed write endpoints.

Auth model (cockpit precedent):
- Behind suite Caddy: basic_auth → forward_auth (module=dealroom, TEAMS rights,
  ro users blocked from non-GET at the proxy) → X-Remote-User header. The
  header is trusted ONLY when DEALROOM_TRUSTED_PROXY=1.
- Local dev: no proxy → principal defaults to 'roman', sandbox banner on.
- Negotiation/stakeholder views: owner-only (seller psych profiles, GDPR —
  negotiation spec §6.9). OWNERS below.

Run local:  python -m v2.server --port 8082   (from dealroom/)
"""

import argparse
import json
import os
import sys
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from v2 import db, freshness, repo  # noqa: E402

OWNERS = {"roman"}

app = FastAPI(title="DEALROOM v2", docs_url=None, redoc_url=None)

_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = db.init_db()
        db.attach_pipeline_ro(_conn)
    return _conn


def is_sandbox() -> bool:
    return not db.on_fly()


def principal(x_remote_user: str | None = Header(default=None)) -> dict:
    trusted = os.environ.get("DEALROOM_TRUSTED_PROXY") == "1"
    if trusted:
        if not x_remote_user:
            raise HTTPException(403, "no user identity")
        user = x_remote_user
    else:
        user = x_remote_user or "roman"  # local sandbox default
    return {"user": user, "is_owner": user in OWNERS, "sandbox": is_sandbox()}


def owner_only(p=Depends(principal)) -> dict:
    if not p["is_owner"]:
        raise HTTPException(403, "owner-only view")
    return p


# ---------------------------------------------------------------- reads -----


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/health")
def health(p=Depends(principal)):
    c = conn()
    n = c.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    return {
        "ok": True,
        "deals": n,
        "db": str(db.default_db_path()),
        "sandbox": p["sandbox"],
        "user": p["user"],
    }


@app.get("/api/attention")
def api_attention(p=Depends(principal)):
    return repo.attention(conn())


@app.get("/api/deals")
def api_deals(p=Depends(principal)):
    return repo.portfolio(conn())


@app.get("/api/deal/{code}")
def api_deal(code: str, p=Depends(principal)):
    payload = repo.deal_answer(conn(), code)
    if not payload:
        raise HTTPException(404, f"unknown deal {code!r}")
    return payload


@app.get("/api/deal/{code}/timeline")
def api_timeline(code: str, p=Depends(principal)):
    events = repo.deal_timeline(conn(), code)
    if events is None:
        raise HTTPException(404, f"unknown deal {code!r}")
    return events


@app.get("/api/terms")
def api_terms(deal: str | None = None, p=Depends(principal)):
    return repo.terms_ledger(conn(), deal)


@app.get("/api/fresh")
def api_fresh(p=Depends(principal)):
    c = conn()
    out = []
    for d in c.execute("SELECT * FROM deals").fetchall():
        flags = freshness.all_flags(c, d)
        if flags:
            out.append({"deal": d["code_name"], "flags": flags})
    return {"deals": out, "computed_at": db.now_iso()}


# ---------------------------------------------------------------- writes ----


def _get_deal_or_404(c, code):
    d = repo.get_deal(c, code)
    if not d:
        raise HTTPException(404, f"unknown deal {code!r}")
    return d


@app.post("/api/deal/{code}/stage")
def set_stage(code: str, payload: dict = Body(...), p=Depends(principal)):
    to_stage = payload.get("to_stage")
    evidence = payload.get("evidence")
    if to_stage not in repo.STAGE_LABELS:
        raise HTTPException(422, f"invalid stage {to_stage!r}")
    if not evidence:
        raise HTTPException(422, "evidence is required for stage changes")
    c = conn()
    d = _get_deal_or_404(c, code)
    now = db.now_iso()
    with db.WRITE_LOCK:
        c.execute(
            "UPDATE deals SET deal_stage=?, stage_entered_at=? WHERE code_name=?",
            (to_stage, now[:10], d["code_name"]),
        )
        c.execute(
            "INSERT INTO deal_stage_history "
            "(domain, code_name, from_stage, to_stage, changed_at, changed_by, evidence) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                d["domain"],
                d["code_name"],
                d["deal_stage"],
                to_stage,
                now,
                p["user"],
                evidence,
            ),
        )
        c.commit()
    return {"ok": True, "from": d["deal_stage"], "to": to_stage}


@app.post("/api/deal/{code}/term")
def add_term(code: str, payload: dict = Body(...), p=Depends(principal)):
    required = ("term_key", "status", "source_doc")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise HTTPException(422, f"missing: {missing}")
    if payload["status"] not in ("proposed", "countered", "agreed", "locked"):
        raise HTTPException(422, "invalid status")
    c = conn()
    d = _get_deal_or_404(c, code)
    now = db.now_iso()
    with db.WRITE_LOCK:
        cur = c.execute(
            "INSERT INTO deal_terms "
            "(domain, code_name, term_key, label, value_num, value_text, unit, "
            " status, source_doc, note, changed_at, changed_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                d["domain"],
                d["code_name"],
                payload["term_key"],
                payload.get("label") or payload["term_key"],
                payload.get("value_num"),
                payload.get("value_text"),
                payload.get("unit"),
                payload["status"],
                payload["source_doc"],
                payload.get("note"),
                now,
                p["user"],
            ),
        )
        new_id = cur.lastrowid
        c.execute(
            "UPDATE deal_terms SET status='superseded', superseded_by_id=? "
            "WHERE code_name=? AND term_key=? AND id != ? AND status != 'superseded'",
            (new_id, d["code_name"], payload["term_key"], new_id),
        )
        c.commit()
    return {"ok": True, "id": new_id}


@app.post("/api/deal/{code}/milestone")
def add_milestone(code: str, payload: dict = Body(...), p=Depends(principal)):
    if not payload.get("milestone"):
        raise HTTPException(422, "milestone is required")
    c = conn()
    d = _get_deal_or_404(c, code)
    with db.WRITE_LOCK:
        cur = c.execute(
            "INSERT INTO deal_milestones "
            "(domain, code_name, milestone, due_date, owner, status, source_doc, "
            " note, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                d["domain"],
                d["code_name"],
                payload["milestone"],
                payload.get("due_date"),
                payload.get("owner") or "Repuro",
                payload.get("status") or "open",
                payload.get("source_doc"),
                payload.get("note"),
                db.now_iso(),
            ),
        )
        c.commit()
    return {"ok": True, "id": cur.lastrowid}


@app.post("/api/milestone/{mid}/status")
def set_milestone_status(mid: int, payload: dict = Body(...), p=Depends(principal)):
    status = payload.get("status")
    if status not in ("open", "done", "missed", "dropped"):
        raise HTTPException(422, "invalid status")
    c = conn()
    with db.WRITE_LOCK:
        n = c.execute(
            "UPDATE deal_milestones SET status=?, done_at=? WHERE id=?",
            (status, db.now_iso() if status == "done" else None, mid),
        ).rowcount
        c.commit()
    if not n:
        raise HTTPException(404, "milestone not found")
    return {"ok": True}


@app.post("/api/push/artifacts")
def push_artifacts(payload: dict = Body(...), p=Depends(principal)):
    """Scanner upsert: one row per (code_name, file_path); version chains are
    recomputed per (code, type, stem) group after the batch."""
    code = payload.get("code_name")
    artifacts = payload.get("artifacts") or []
    c = conn()
    d = _get_deal_or_404(c, code)
    now = db.now_iso()
    seen_groups = set()
    with db.WRITE_LOCK:
        for a in artifacts:
            if not a.get("file_path") or not a.get("file_name"):
                raise HTTPException(422, "artifact needs file_path + file_name")
            c.execute(
                "INSERT INTO deal_artifacts "
                "(domain, code_name, artifact_type, artifact_subtype, version, "
                " file_name, file_path, file_mtime, file_date, file_size_kb, "
                " fiscal_year, dataroom_section, status, registered_at, "
                " last_seen_at, note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(code_name, file_path) DO UPDATE SET "
                " artifact_type=excluded.artifact_type, "
                " version=excluded.version, file_mtime=excluded.file_mtime, "
                " file_date=excluded.file_date, "
                " file_size_kb=excluded.file_size_kb, "
                " dataroom_section=excluded.dataroom_section, "
                " last_seen_at=excluded.last_seen_at",
                (
                    d["domain"],
                    d["code_name"],
                    a.get("artifact_type") or "other",
                    a.get("artifact_subtype"),
                    a.get("version"),
                    a["file_name"],
                    a["file_path"],
                    a.get("file_mtime"),
                    a.get("file_date"),
                    a.get("file_size_kb"),
                    a.get("fiscal_year"),
                    a.get("dataroom_section"),
                    "current",
                    now,
                    now,
                    a.get("note"),
                ),
            )
            seen_groups.add(a.get("artifact_type") or "other")
        # recompute current/superseded within each touched type group
        for atype in seen_groups:
            _recompute_chains(c, d["code_name"], atype)
        c.commit()
    return {"ok": True, "count": len(artifacts)}


def _recompute_chains(c, code, atype):
    from v2.naming import artifact_stem

    rows = c.execute(
        "SELECT id, file_name, file_date, version, registered_at, status "
        "FROM deal_artifacts WHERE code_name=? AND artifact_type=?",
        (code, atype),
    ).fetchall()
    groups = {}
    for r in rows:
        groups.setdefault(artifact_stem(r["file_name"]), []).append(r)
    for group in groups.values():
        group.sort(
            key=lambda r: (
                r["file_date"] or "0000",
                r["version"] or 0,
                r["registered_at"] or "",
            )
        )
        for i, r in enumerate(group):
            if r["status"] == "final":
                continue  # sign-off is sticky
            status = "current" if i == len(group) - 1 else "superseded"
            supersedes = group[i - 1]["id"] if i > 0 else None
            c.execute(
                "UPDATE deal_artifacts SET status=?, supersedes_id=? WHERE id=?",
                (status, supersedes, r["id"]),
            )


@app.post("/api/artifact/{aid}/status")
def set_artifact_status(aid: int, payload: dict = Body(...), p=Depends(principal)):
    status = payload.get("status")
    if status not in ("current", "superseded", "final", "stale", "draft"):
        raise HTTPException(422, "invalid status")
    c = conn()
    with db.WRITE_LOCK:
        n = c.execute(
            "UPDATE deal_artifacts SET status=?, checks_json=COALESCE(?, checks_json) "
            "WHERE id=?",
            (
                status,
                json.dumps(payload["checks"]) if payload.get("checks") else None,
                aid,
            ),
        ).rowcount
        c.commit()
    if not n:
        raise HTTPException(404, "artifact not found")
    return {"ok": True}


@app.post("/api/push/dataroom-scan")
def push_dataroom_scan(payload: dict = Body(...), p=Depends(principal)):
    """Scanner pushes full file lists per section; server computes the delta
    vs the previous scan of the same section."""
    code = payload.get("code_name")
    sections = payload.get("sections") or []
    c = conn()
    d = _get_deal_or_404(c, code)
    now = db.now_iso()
    deltas = {}
    with db.WRITE_LOCK:
        for s in sections:
            section = s.get("section")
            if section is None:
                raise HTTPException(422, "section is required")
            prev = c.execute(
                "SELECT files_json FROM dataroom_scans WHERE code_name=? "
                "AND section=? ORDER BY scanned_at DESC, id DESC LIMIT 1",
                (d["code_name"], section),
            ).fetchone()
            prev_files = {}
            if prev and prev["files_json"]:
                prev_files = json.loads(prev["files_json"])
            files = {f["name"]: f.get("mtime") for f in (s.get("files") or [])}
            delta = {
                "added": sorted(set(files) - set(prev_files)),
                "removed": sorted(set(prev_files) - set(files)),
                "changed": sorted(
                    n for n in set(files) & set(prev_files) if files[n] != prev_files[n]
                ),
            }
            if prev is None:
                delta = {"added": [], "removed": [], "changed": []}  # baseline
            deltas[section] = delta
            c.execute(
                "INSERT INTO dataroom_scans "
                "(domain, code_name, section, section_name, scanned_at, "
                " file_count, newest_file_date, newest_file_name, files_json, "
                " delta_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    d["domain"],
                    d["code_name"],
                    section,
                    s.get("section_name"),
                    now,
                    len(files),
                    s.get("newest_file_date"),
                    s.get("newest_file_name"),
                    json.dumps(files, ensure_ascii=False),
                    json.dumps(delta, ensure_ascii=False),
                ),
            )
        c.commit()
    return {"ok": True, "sections": len(sections), "deltas": deltas}


@app.post("/api/push/rfi")
def push_rfi(payload: dict = Body(...), p=Depends(principal)):
    """RFI xlsx is master (spec §6): mirror refresh replaces the deal's rows."""
    code = payload.get("code_name")
    questions = payload.get("questions") or []
    c = conn()
    d = _get_deal_or_404(c, code)
    if not d["domain"]:
        raise HTTPException(422, f"deal {code!r} has no domain — cannot mirror RFI")
    now = db.now_iso()
    with db.WRITE_LOCK:
        c.execute("DELETE FROM deal_questions WHERE domain=?", (d["domain"],))
        for i, q in enumerate(questions):
            if not q.get("question"):
                raise HTTPException(422, "question text required")
            c.execute(
                "INSERT INTO deal_questions "
                "(id, domain, question, category, subcategory, importance, "
                " source, sort_order, status, answer, sent_at, answered_at, "
                " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    q.get("id") or f"rfi-{d['domain']}-{i}",
                    d["domain"],
                    q["question"],
                    q.get("category") or "RFI",
                    q.get("subcategory"),
                    q.get("importance") or "medium",
                    q.get("source") or "rfi-xlsx",
                    q.get("sort_order", i),
                    q.get("status") or "open",
                    q.get("answer"),
                    q.get("sent_at"),
                    q.get("answered_at"),
                    now,
                ),
            )
        c.commit()
    return {"ok": True, "count": len(questions)}


# ------------------------------------------------------------------- UI -----
# Rebuild after 13.07 rejection: screens ship one at a time with sign-off.
# Screen 1 = Portfolio View (v1 golden reference, ported 1:1). Screen 2 =
# Offer & Negotiation (v1 visual language, owner-only). The old M3-M5
# surfaces (v2.ui / v2.ui_workspace) are unregistered pending their rebuild.

from v2 import ui_dealview, ui_negotiation, ui_portfolio  # noqa: E402

ui_portfolio.register(app, conn, principal)
ui_dealview.register(app, conn, principal)
ui_negotiation.register(app, conn, owner_only)


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


# ------------------------------------------------------------------ main ----

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
