import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.conftest import AGENT_TOKEN, auth


def make_ws(client, name="Octopus", space_id="s-1", **kw):
    r = client.post(
        "/api/workstream",
        json={"name": name, "space_id": space_id, **kw},
        headers=auth(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_deliv(client, ws_id, name="Legal DD", **kw):
    r = client.post(
        "/api/deliverable",
        json={"workstream_id": ws_id, "name": name, **kw},
        headers=auth(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def make_task(client, **kw):
    payload = {"text": "test task", **kw}
    r = client.post("/api/task", json=payload, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()


# ---- SPA shell -------------------------------------------------------------
def test_index_serves_spa(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Repuro Cockpit" in r.text and "boot.js" in r.text
    assert client.get("/static/js/boot.js").status_code == 200
    assert client.get("/static/js/app.jsx").status_code == 200


# ---- auth ----------------------------------------------------------------
def test_auth_required(client):
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers=auth("wrong-token")).status_code == 401
    assert client.get("/api/health").status_code == 200  # health is open


def test_health_reports_mirror(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["mirror_synced_at"]  # startup sync against the fixture ran


# ---- task CRUD + version conflicts ---------------------------------------
def test_task_create_and_patch_version(client):
    t = make_task(client, deadline="2026-06-17", responsible="RD")  # today+6
    assert t["id"] == "t-1" and t["version"] == 1
    assert t["computed"]["recommendation"] == "this_week"

    r = client.patch(
        f"/api/task/{t['id']}",
        json={"version": 1, "status": "in_progress"},
        headers=auth(),
    )
    assert r.status_code == 200 and r.json()["version"] == 2

    stale = client.patch(
        f"/api/task/{t['id']}", json={"version": 1, "status": "done"}, headers=auth()
    )
    assert stale.status_code == 409

    missing = client.patch(
        f"/api/task/{t['id']}", json={"status": "done"}, headers=auth()
    )
    assert missing.status_code == 422  # version required


def test_task_done_sets_done_at_and_audit(client):
    t = make_task(client)
    client.patch(
        f"/api/task/{t['id']}", json={"version": 1, "status": "done"}, headers=auth()
    )
    conn = client.cockpit_conn
    row = conn.execute("SELECT done_at FROM tasks WHERE id=1").fetchone()
    assert row["done_at"]
    actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log")]
    assert "task_create" in actions and "task_update" in actions


def test_task_enum_validation(client):
    r = client.post("/api/task", json={"text": "x", "status": "bogus"}, headers=auth())
    assert r.status_code == 422
    r = client.post(
        "/api/task", json={"text": "x", "execution": "agent_supervised"}, headers=auth()
    )
    assert r.status_code == 422  # AC required for agent execution


def test_prereq_refs_validated(client):
    r = client.post(
        "/api/task", json={"text": "x", "prereqs": [{"ref": "t-99"}]}, headers=auth()
    )
    assert r.status_code == 422


# ---- readiness & waiting flow through the API ----------------------------
def test_readiness_in_state(client):
    ws = make_ws(client)
    d = make_deliv(client, ws, target_date="2026-06-30")
    gate = make_task(client, text="gate", deliverable_id=d)
    dependent = make_task(
        client,
        text="dependent",
        deliverable_id=d,
        prereqs=[{"ref": gate["id"], "hardness": "hard"}],
    )
    assert dependent["computed"]["readiness"] == "red"  # gate open

    client.patch(
        f"/api/task/{gate['id']}", json={"version": 1, "status": "done"}, headers=auth()
    )
    state = client.get("/api/state", headers=auth()).json()
    tasks = {
        t["id"]: t
        for sp in state["spaces"]
        for w in sp["workstreams"]
        for dd in w["deliverables"]
        for t in dd["tasks"]
    }
    assert tasks[dependent["id"]]["computed"]["readiness"] == "green"


def test_waiting_task_surfaces_via_chase_not_deadline(client):
    t = make_task(client, deadline="2026-06-01")  # overdue -> today
    assert t["computed"]["recommendation"] == "today"
    r = client.patch(
        f"/api/task/{t['id']}",
        json={
            "version": 1,
            "status": "waiting",
            "waiting_on_party": "Ebner Stolz",
            "waiting_on_type": "advisor",
            "next_chase_date": "2026-06-20",
        },
        headers=auth(),
    )
    body = r.json()
    assert body["computed"]["recommendation"] == "later"  # own deadline ignored
    # overdue badge stays (risk has no waiting exception — only recommendation does)
    assert body["computed"]["risks"] == ["overdue"]

    r = client.patch(
        f"/api/task/{t['id']}",
        json={"version": 2, "next_chase_date": "2026-06-11"},
        headers=auth(),
    )
    assert r.json()["computed"]["recommendation"] == "today"
    assert "chase" in r.json()["computed"]["risks"]


def test_staging_excluded_from_recommendation(client):
    t = make_task(client, deadline="2026-06-01", staging=1)
    assert t["computed"]["recommendation"] is None
    assert t["computed"]["readiness"] is None


# ---- agent queue ----------------------------------------------------------
def agent_task(client):
    return make_task(
        client,
        text="agent job",
        execution="agent_supervised",
        acceptance_criteria="export contains 3 rows",
        kind="agent_job",
    )


def test_agent_claim_result_approve_flow(client):
    t = agent_task(client)
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert [x["id"] for x in q] == [t["id"]]

    # humans cannot claim; agents can
    assert client.post(f"/api/agent/claim/{t['id']}", headers=auth()).status_code == 403
    r = client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    assert r.status_code == 200 and r.json()["claimed_by"] == "rc-agent"

    # double-claim blocked; queue now empty
    assert (
        client.post(
            f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN)
        ).status_code
        == 409
    )
    assert (
        client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"] == []
    )

    r = client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k1", "evidence": "did it, see X"},
        headers=auth(AGENT_TOKEN),
    )
    assert r.status_code == 200 and r.json()["status"] == "in_review"
    # idempotent replay
    r2 = client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k1", "evidence": "ignored"},
        headers=auth(AGENT_TOKEN),
    )
    assert r2.json() == r.json()

    # agent cannot approve its own result; human can
    assert (
        client.post(
            f"/api/task/{t['id']}/approve", headers=auth(AGENT_TOKEN)
        ).status_code
        == 403
    )
    r = client.post(f"/api/task/{t['id']}/approve", headers=auth())
    assert r.json()["status"] == "done" and r.json()["claimed_by"] is None


def test_agent_reject_reopens(client):
    t = agent_task(client)
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k", "evidence": "weak result"},
        headers=auth(AGENT_TOKEN),
    )
    r = client.post(
        f"/api/task/{t['id']}/reject", json={"comment": "AC not met"}, headers=auth()
    )
    body = r.json()
    assert body["status"] == "open" and "REJECTED" in body["evidence"]


def test_expired_lease_reaped(client):
    t = agent_task(client)
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    conn = client.cockpit_conn
    conn.execute("UPDATE tasks SET claim_expires_at='2020-01-01T00:00:00Z' WHERE id=1")
    conn.commit()
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert [x["id"] for x in q] == [t["id"]]  # back in the queue
    row = conn.execute("SELECT claimed_by, status FROM tasks WHERE id=1").fetchone()
    assert row["claimed_by"] is None and row["status"] == "open"


def test_agent_queue_owner_tag_and_filter(client):  # SPEC-agent-skills-repo §3a
    t = agent_task(client)  # created via RD_TOKEN -> created_by="rd"
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert q[0]["created_by"] == "rd" and q[0]["owner"] == "RC"

    # ?owner=rc keeps Roman's task; ?owner=fc excludes it
    rc = client.get("/api/agent/queue?owner=rc", headers=auth(AGENT_TOKEN)).json()
    assert [x["id"] for x in rc["queue"]] == [t["id"]]
    fc = client.get("/api/agent/queue?owner=fc", headers=auth(AGENT_TOKEN)).json()
    assert fc["queue"] == []

    # bad owner -> 422
    assert (
        client.get("/api/agent/queue?owner=xx", headers=auth(AGENT_TOKEN)).status_code
        == 422
    )


# ---- export / import -------------------------------------------------------
def test_export_scopes_and_agent_restriction(client):
    ws = make_ws(client, name="Fox Legal", deal_codename="Fox", space_id="s-2")
    d = make_deliv(client, ws)
    make_task(client, text="Fox task", deliverable_id=d, responsible="RD", deal="Fox")
    md = client.get("/api/export.md?scope=all", headers=auth()).text
    assert "### Fox Legal" in md and "Fox task" in md and "deal: Fox (loi_signed)" in md

    assert (
        client.get("/api/export.md?scope=all", headers=auth(AGENT_TOKEN)).status_code
        == 403
    )
    md = client.get("/api/export.md?scope=person:RD", headers=auth(AGENT_TOKEN)).text
    assert "Fox task" in md


def test_import_dry_run_and_apply(client):
    ws = make_ws(client, name="Fundraising")
    make_deliv(client, ws)
    t = make_task(client, text="existing")
    push = (
        "# cockpit-push\n"
        "## task-update\n"
        f"- id: {t['id']} | version: 1 | status: in_progress | evidence: started\n"
        "## new-task\n"
        "- workstream: Fundraising | deliverable: Legal DD | text: Review docs"
        " | deadline: 2026-06-20 | priority: high | kind: workplan\n"
    )
    r = client.post(
        "/api/import?dry_run=true",
        content=push,
        headers={**auth(), "Content-Type": "text/markdown"},
    )
    assert r.status_code == 200 and r.json()["dry_run"]
    conn = client.cockpit_conn
    assert (
        conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
    )  # nothing applied

    r = client.post(
        "/api/import", content=push, headers={**auth(), "Content-Type": "text/markdown"}
    )
    assert r.status_code == 200 and r.json()["created_ids"] == ["t-2"]
    assert (
        conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()[0]
        == "in_progress"
    )


def test_import_fail_closed(client):
    make_ws(client)
    t = make_task(client, text="existing")
    push = (
        "# cockpit-push\n"
        "## task-update\n"
        f"- id: {t['id']} | version: 1 | status: done\n"
        "## task-update\n"
        "- id: t-999 | version: 1 | status: done\n"  # unknown id -> whole push rejected
    )
    r = client.post(
        "/api/import", content=push, headers={**auth(), "Content-Type": "text/markdown"}
    )
    assert r.status_code == 422
    conn = client.cockpit_conn
    assert conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()[0] == "open"


def test_import_rejects_unknown_block_and_enum(client):
    r = client.post(
        "/api/import",
        content="## deal-status\n- OCTOPUS | stage: dd\n",
        headers={**auth(), "Content-Type": "text/markdown"},
    )
    assert r.status_code == 422
    make_ws(client, name="Admin")
    r = client.post(
        "/api/import",
        content="## new-task\n- workstream: Admin | text: x | priority: urgent\n",
        headers={**auth(), "Content-Type": "text/markdown"},
    )
    assert r.status_code == 422


# ---- PM amendment regressions (ai/codex-reviews/2026-06-11-PM-M1.md) -------
def test_import_stale_version_conflicts(client):  # PM R1
    t = make_task(client, text="existing")
    client.patch(
        f"/api/task/{t['id']}",
        json={"version": 1, "status": "in_progress"},
        headers=auth(),
    )  # now v2
    stale = f"## task-update\n- id: {t['id']} | version: 1 | status: done\n"
    r = client.post(
        "/api/import",
        content=stale,
        headers={**auth(), "Content-Type": "text/markdown"},
    )
    assert r.status_code == 422 and "version conflict" in r.text
    conn = client.cockpit_conn
    assert (
        conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()[0]
        == "in_progress"
    )
    # update without version at all is rejected outright
    r = client.post(
        "/api/import",
        content=f"## task-update\n- id: {t['id']} | status: done\n",
        headers={**auth(), "Content-Type": "text/markdown"},
    )
    assert r.status_code == 422


def test_export_includes_version_token(client):  # PM R1 (contract)
    make_task(client, text="versioned")
    md = client.get("/api/export.md?scope=all", headers=auth()).text
    assert "| v1" in md


def test_agent_queue_export_includes_deliverable_tasks(client):  # PM R2
    ws = make_ws(client)
    d = make_deliv(client, ws)
    make_task(
        client,
        text="nested agent job",
        deliverable_id=d,
        execution="agent_supervised",
        acceptance_criteria="AC",
        kind="agent_job",
    )
    md = client.get("/api/export.md?scope=agent-queue", headers=auth(AGENT_TOKEN)).text
    assert "nested agent job" in md


def test_deal_scope_keeps_workstream_linked_tasks(client):  # PM R3
    ws = make_ws(client, name="Fox WS", deal_codename="Fox", space_id="s-2")
    d = make_deliv(client, ws)
    make_task(client, text="blank-deal task", deliverable_id=d)  # task.deal is NULL
    md = client.get("/api/export.md?scope=deal:Fox", headers=auth()).text
    assert "blank-deal task" in md


def test_second_result_rejected(client):  # PM R4
    t = agent_task(client)
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    r1 = client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k1", "evidence": "first result"},
        headers=auth(AGENT_TOKEN),
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k2", "evidence": "overwrite attempt"},
        headers=auth(AGENT_TOKEN),
    )
    assert r2.status_code == 409
    conn = client.cockpit_conn
    assert (
        conn.execute("SELECT evidence FROM tasks WHERE id=1").fetchone()[0]
        == "first result"
    )


def test_result_on_expired_lease_rejected(client):  # PM R4 recheck (codex repro)
    t = agent_task(client)
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    conn = client.cockpit_conn
    conn.execute("UPDATE tasks SET claim_expires_at='2020-01-01T00:00:00Z' WHERE id=1")
    conn.commit()
    r = client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k1", "evidence": "too late"},
        headers=auth(AGENT_TOKEN),
    )
    assert r.status_code == 409
    row = conn.execute(
        "SELECT status, claimed_by, evidence FROM tasks WHERE id=1"
    ).fetchone()
    assert (
        row["status"] == "open"
        and row["claimed_by"] is None
        and row["evidence"] is None
    )
    # heartbeat cannot revive a dead lease either
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    conn.execute("UPDATE tasks SET claim_expires_at='2020-01-01T00:00:00Z' WHERE id=1")
    conn.commit()
    assert (
        client.post(
            f"/api/agent/heartbeat/{t['id']}", headers=auth(AGENT_TOKEN)
        ).status_code
        == 409
    )


def test_malformed_date_rejected(client):  # PM A5 (self-found)
    r = client.post(
        "/api/task", json={"text": "x", "deadline": "next week"}, headers=auth()
    )
    assert r.status_code == 422
    t = make_task(client, text="ok")
    r = client.patch(
        f"/api/task/{t['id']}",
        json={"version": 1, "next_chase_date": "soon"},
        headers=auth(),
    )
    assert r.status_code == 422
    # state still assembles fine afterwards
    assert client.get("/api/state", headers=auth()).status_code == 200


def test_person_scope_token_match(client):  # PM CLARIFY 1
    make_task(client, text="board task", responsible="Board")
    make_task(client, text="rd task", responsible="FF, RD; External Legal")
    md = client.get("/api/export.md?scope=person:RD", headers=auth()).text
    assert "rd task" in md and "board task" not in md


def test_deliverable_gate_clears_when_tasks_done(client):
    ws = make_ws(client, name="GateWS")
    d = make_deliv(client, ws, name="Gate deliverable")
    inner = make_task(client, text="inner work", deliverable_id=d)
    dep = make_task(client, text="gated", prereqs=[{"ref": d, "hardness": "hard"}])
    assert dep["computed"]["readiness"] == "red"
    client.patch(
        f"/api/task/{inner['id']}",
        json={"version": 1, "status": "done"},
        headers=auth(),
    )
    state = client.get("/api/state", headers=auth()).json()
    gated = next(t for t in state["standalone_tasks"] if t["text"] == "gated")
    assert gated["computed"]["readiness"] == "green"  # gate cleared via its tasks


def test_delete_task_prunes_dangling_prereqs(client):
    gate = make_task(client, text="gate")
    dep = make_task(
        client, text="dependent", prereqs=[{"ref": gate["id"], "hardness": "hard"}]
    )
    assert dep["computed"]["readiness"] == "red"
    # agents cannot delete
    assert (
        client.delete(f"/api/task/{gate['id']}", headers=auth(AGENT_TOKEN)).status_code
        == 403
    )
    r = client.delete(f"/api/task/{gate['id']}", headers=auth())
    assert r.status_code == 200 and r.json()["deleted"] == gate["id"]
    conn = client.cockpit_conn
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
    row = conn.execute("SELECT prereqs FROM tasks").fetchone()
    assert row["prereqs"] == "[]"  # dangling gate stripped, dependent not stuck red
    assert client.delete("/api/task/t-99", headers=auth()).status_code == 404


# ---- spaces ---------------------------------------------------------------
def test_state_has_spaces_structure(client):
    ws = make_ws(client, name="Admin")
    make_task(client, text="admin task", deliverable_id=make_deliv(client, ws))
    state = client.get("/api/state", headers=auth()).json()
    assert "spaces" in state
    space_names = [s["name"] for s in state["spaces"]]
    assert "Holding" in space_names and "M&A" in space_names
    holding = next(s for s in state["spaces"] if s["name"] == "Holding")
    assert any(w["name"] == "Admin" for w in holding["workstreams"])


def test_workstream_requires_space_id(client):
    r = client.post("/api/workstream", json={"name": "NoSpace"}, headers=auth())
    assert r.status_code == 422


def test_reorder_blocked_in_deal_stage_space(client):
    ws = make_ws(client, name="Lion", deal_codename="Lion", space_id="s-2")
    r = client.patch(
        "/api/workstreams/reorder",
        json={"order": [ws]},
        headers=auth(),
    )
    assert r.status_code == 422


def test_deliverable_inherits_deal_from_workstream(client):
    ws = make_ws(client, name="Fox DD", deal_codename="Fox", space_id="s-2")
    d = make_deliv(client, ws, name="Financial DD")
    state = client.get("/api/state", headers=auth()).json()
    mna = next(s for s in state["spaces"] if s["name"] == "M&A")
    fox_ws = next(w for w in mna["workstreams"] if w["name"] == "Fox DD")
    dd = next(d for d in fox_ws["deliverables"] if d["name"] == "Financial DD")
    assert dd["deal"] == "Fox"


# ---- sync endpoint ---------------------------------------------------------
def test_sync_endpoint(client):
    r = client.post("/api/sync/dealroom", headers=auth())
    assert r.status_code == 200 and r.json()["ok"] and r.json()["count"] == 3
    state = client.get("/api/state", headers=auth()).json()
    assert len(state["deals"]) == 3


def test_sync_auto_creates_mna_workstreams(client):
    state = client.get("/api/state", headers=auth()).json()
    mna = next(s for s in state["spaces"] if s["name"] == "M&A")
    ws_names = {w["name"] for w in mna["workstreams"]}
    assert {"Octopus", "Fox", "Cat"} <= ws_names


def test_sync_adopts_existing_ws_by_name(client):
    """If a workstream exists with same name as a deal but no deal_codename,
    sync should adopt it (set deal_codename + move to M&A) rather than crash."""
    conn = client.cockpit_conn
    conn.execute(
        "INSERT INTO workstreams (name, space_id, status) VALUES (?,?,?)",
        ("NewDeal", 1, "active"),
    )
    conn.commit()
    from tests.conftest import make_fixture_dealroom

    dealroom_path = conn.execute("SELECT 1").fetchone()  # just need the env var
    import os

    dr_path = os.environ["COCKPIT_DEALROOM_DB"]
    dr_conn = sqlite3.connect(dr_path)
    dr_conn.execute("DROP TABLE IF EXISTS deals")
    dr_conn.commit()
    dr_conn.close()
    make_fixture_dealroom(dr_path, deals=[("NewDeal", "nda", None)])
    r = client.post("/api/sync/dealroom", headers=auth())
    assert r.status_code == 200
    row = conn.execute(
        "SELECT deal_codename, space_id FROM workstreams WHERE name='NewDeal'"
    ).fetchone()
    mna_id = conn.execute("SELECT id FROM spaces WHERE slug='mna'").fetchone()["id"]
    assert row["deal_codename"] == "NewDeal"
    assert row["space_id"] == mna_id


# ---- migration v3→v4 -------------------------------------------------------
def test_migration_v3_to_v4(tmp_path):
    """Simulate a v3 DB and verify migration to v4 creates spaces + moves deal ws."""
    from src import db as dbmod

    path = tmp_path / "mig.db"
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys=ON")
    v3_ddl = """
    CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, initials TEXT,
      token_hash TEXT, role TEXT NOT NULL CHECK(role IN ('human','agent')));
    CREATE TABLE deal_mirror (codename TEXT PRIMARY KEY, stage TEXT, note TEXT,
      owner_mode TEXT NOT NULL DEFAULT 'legacy', synced_at TEXT);
    CREATE TABLE workstreams (id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE, color TEXT, sort_order INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'active', deal_codename TEXT,
      version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE deliverables (id INTEGER PRIMARY KEY AUTOINCREMENT,
      workstream_id INTEGER NOT NULL REFERENCES workstreams(id),
      name TEXT NOT NULL, target_date TEXT,
      status TEXT NOT NULL DEFAULT 'open', sort_order INTEGER NOT NULL DEFAULT 0,
      comment TEXT, staging INTEGER NOT NULL DEFAULT 0, source TEXT,
      version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,
      deliverable_id INTEGER REFERENCES deliverables(id),
      kind TEXT NOT NULL DEFAULT 'workplan', text TEXT NOT NULL, detail TEXT,
      deadline TEXT, responsible TEXT, priority TEXT, status TEXT NOT NULL DEFAULT 'open',
      waiting_on_party TEXT, waiting_on_type TEXT, next_chase_date TEXT,
      expected_back_by TEXT, last_touched_at TEXT,
      execution TEXT NOT NULL DEFAULT 'me', runner TEXT, acceptance_criteria TEXT,
      claimed_by TEXT, claim_expires_at TEXT, evidence TEXT,
      prereqs TEXT NOT NULL DEFAULT '[]', tags TEXT NOT NULL DEFAULT '[]',
      links TEXT NOT NULL DEFAULT '[]', deal TEXT, pinned_today INTEGER NOT NULL DEFAULT 0,
      staging INTEGER NOT NULL DEFAULT 0, sort_order INTEGER NOT NULL DEFAULT 0,
      source TEXT, input_from TEXT, input_question TEXT,
      version INTEGER NOT NULL DEFAULT 1, created_by TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, done_at TEXT);
    CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT,
      at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL,
      before TEXT, after TEXT);
    CREATE TABLE idempotency (task_id INTEGER NOT NULL, key TEXT NOT NULL,
      response TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (task_id, key));
    """
    conn.executescript(v3_ddl)
    conn.execute("PRAGMA user_version = 3")
    conn.execute(
        "INSERT INTO workstreams (name, deal_codename) VALUES (?,?)",
        ("Fox DD", "Fox"),
    )
    conn.execute("INSERT INTO workstreams (name) VALUES (?)", ("Admin",))
    conn.execute(
        "INSERT INTO deliverables (workstream_id, name, created_at, updated_at) "
        "VALUES (1, 'LDD', '', '')"
    ) if False else conn.execute(
        "INSERT INTO deliverables (workstream_id, name) VALUES (1, 'LDD')"
    )
    conn.commit()
    conn.close()

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    dbmod.migrate_db(conn, 3)

    # migrate_db runs forward to the latest migration, not just v4; the holding
    # space was 'repuro' until migration 5 renamed it.
    assert conn.execute("PRAGMA user_version").fetchone()[0] == dbmod.SCHEMA_VERSION
    spaces = {r["slug"]: r["id"] for r in conn.execute("SELECT slug, id FROM spaces")}
    assert "holding" in spaces and "mna" in spaces
    fox = conn.execute(
        "SELECT space_id FROM workstreams WHERE name='Fox DD'"
    ).fetchone()
    assert fox["space_id"] == spaces["mna"]
    admin = conn.execute(
        "SELECT space_id FROM workstreams WHERE name='Admin'"
    ).fetchone()
    assert admin["space_id"] == spaces["holding"]
    deal_col = conn.execute("SELECT deal FROM deliverables WHERE name='LDD'").fetchone()
    assert deal_col["deal"] == "Fox"
    conn.close()
