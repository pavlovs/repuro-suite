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
    # SPEC §7d: reject pulls the task OFF the agent lane — an unattended loop
    # must never re-execute a rejected task
    assert body["execution"] == "me"
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert q == []


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


def test_agent_queue_lane_and_scope(client):  # SPEC §3a — token-derived lane
    t = agent_task(client)  # created via RD_TOKEN -> created_by="rd" (RC lane)
    # a task in another lane (created_by ff) the caller should NOT see by default
    conn = client.cockpit_conn
    conn.execute(
        "INSERT INTO tasks (text, execution, acceptance_criteria, status, staging, "
        "created_by, created_at, updated_at) "
        "VALUES ('ff job','agent_supervised','ac','open',0,'ff','x','x')"
    )
    conn.commit()

    # default scope=mine -> only the caller's lane (rc-agent represents rd)
    mine = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert [x["id"] for x in mine] == [t["id"]]
    assert mine[0]["created_by"] == "rd" and mine[0]["owner"] == "RC"

    # scope=all -> both lanes
    allq = client.get("/api/agent/queue?scope=all", headers=auth(AGENT_TOKEN)).json()
    assert len(allq["queue"]) == 2

    # bad scope -> 422
    assert (
        client.get("/api/agent/queue?scope=xx", headers=auth(AGENT_TOKEN)).status_code
        == 422
    )


# ---- SPEC §7 review->rework loop -------------------------------------------
def test_queue_carries_review_context_after_request_changes(client):
    """A sent-back task arrives at the runner WITH feedback + evidence trail."""
    t = agent_task(client)
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "k1", "evidence": "round 1 result"},
        headers=auth(AGENT_TOKEN),
    )
    r = client.post(
        f"/api/task/{t['id']}/request-changes",
        json={"feedback": "wrong currency, use EUR"},
        headers=auth(),
    )
    assert r.status_code == 200 and r.json()["review_round"] == 1

    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert len(q) == 1
    task = q[0]
    assert task["review_round"] == 1
    assert task["review_feedback"] == "wrong currency, use EUR"
    assert "round 1 result" in task["evidence"]
    assert "wrong currency" in task["evidence"]
    assert task["ready"] is True and task["blocked_by"] == []


def test_queue_readiness_and_display_order(client):
    gate = make_task(client, text="gate")
    blocked = make_task(
        client,
        text="blocked agent job",
        execution="agent_supervised",
        acceptance_criteria="ac",
        prereqs=[{"ref": gate["id"], "hardness": "hard"}],
    )
    free = agent_task(client)
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    # order = sort_order, id — identical to the Agents view display order
    assert [x["id"] for x in q] == [blocked["id"], free["id"]]
    by_id = {x["id"]: x for x in q}
    assert by_id[blocked["id"]]["ready"] is False
    assert by_id[blocked["id"]]["blocked_by"] == [gate["id"]]
    assert by_id[free["id"]]["ready"] is True

    # gate done -> blocked task becomes ready
    client.patch(
        f"/api/task/{gate['id']}",
        json={"version": 1, "status": "done"},
        headers=auth(),
    )
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert {x["id"]: x["ready"] for x in q} == {blocked["id"]: True, free["id"]: True}


def test_agent_block_and_human_answer_flow(client):
    """in_progress -> blocked (agent question) -> answer -> open with context."""
    t = agent_task(client)
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))

    # question required; must be the claimant
    assert (
        client.post(
            f"/api/agent/block/{t['id']}", json={}, headers=auth(AGENT_TOKEN)
        ).status_code
        == 422
    )
    r = client.post(
        f"/api/agent/block/{t['id']}",
        json={"question": "Which SUSA version — March or April?"},
        headers=auth(AGENT_TOKEN),
    )
    assert r.status_code == 200
    conn = client.cockpit_conn
    row = conn.execute(
        "SELECT status, input_from, input_question, claimed_by FROM tasks WHERE id=1"
    ).fetchone()
    assert row["status"] == "blocked" and row["claimed_by"] is None
    assert row["input_from"] == "RD" and "SUSA" in row["input_question"]

    # blocked task is NOT in the runner queue
    assert (
        client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"] == []
    )

    # agents cannot answer; empty answer rejected; human answer re-opens
    assert (
        client.post(
            f"/api/task/{t['id']}/answer",
            json={"answer": "x"},
            headers=auth(AGENT_TOKEN),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/task/{t['id']}/answer", json={"answer": "  "}, headers=auth()
        ).status_code
        == 422
    )
    r = client.post(
        f"/api/task/{t['id']}/answer", json={"answer": "April"}, headers=auth()
    )
    body = r.json()
    assert body["status"] == "open"
    assert body["input_question"] is None and body["input_from"] is None
    assert "QUESTION:" in body["evidence"] and "ANSWER (rd): April" in body["evidence"]

    # back in the queue, answer rides along in evidence
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert [x["id"] for x in q] == [t["id"]]
    assert "ANSWER (rd): April" in q[0]["evidence"]

    # answer on a non-blocked task -> 409
    assert (
        client.post(
            f"/api/task/{t['id']}/answer", json={"answer": "again"}, headers=auth()
        ).status_code
        == 409
    )


def test_claim_rejects_unready_task(client):
    """Server enforces readiness at the mutation boundary — an old client or a
    stale queue view must not claim a task behind an unmet hard prereq."""
    gate = make_task(client, text="gate")
    blocked = make_task(
        client,
        text="gated agent job",
        execution="agent_supervised",
        acceptance_criteria="ac",
        prereqs=[{"ref": gate["id"], "hardness": "hard"}],
    )
    r = client.post(f"/api/agent/claim/{blocked['id']}", headers=auth(AGENT_TOKEN))
    assert r.status_code == 409 and gate["id"] in r.json()["detail"]
    # gate done -> claimable
    client.patch(
        f"/api/task/{gate['id']}",
        json={"version": 1, "status": "done"},
        headers=auth(),
    )
    r = client.post(f"/api/agent/claim/{blocked['id']}", headers=auth(AGENT_TOKEN))
    assert r.status_code == 200


def test_dropped_deliverable_prereq_counts_as_cleared(client):
    """assemble_state normalizes deliverable dropped->done; the queue and claim
    readiness must agree, or a task gated on a dropped deliverable is stuck."""
    ws = make_ws(client)
    d = make_deliv(client, ws)
    t = make_task(
        client,
        text="gated on deliverable",
        execution="agent_supervised",
        acceptance_criteria="ac",
        prereqs=[{"ref": d, "hardness": "hard"}],
    )
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert q[0]["id"] == t["id"] and q[0]["ready"] is False
    r = client.patch(
        f"/api/deliverable/{d}",
        json={"version": 1, "status": "dropped"},
        headers=auth(),
    )
    assert r.status_code == 200, r.text
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert q[0]["ready"] is True and q[0]["blocked_by"] == []
    assert (
        client.post(
            f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN)
        ).status_code
        == 200
    )


def test_deliverable_cleared_by_done_children_unblocks_queue(client):
    """An OPEN deliverable whose live child tasks are all done is effectively
    cleared in canonical state — queue/claim readiness must agree."""
    ws = make_ws(client)
    d = make_deliv(client, ws)
    child = make_task(client, text="child work", deliverable_id=d)
    gated = make_task(
        client,
        text="gated on deliverable via children",
        execution="agent_supervised",
        acceptance_criteria="ac",
        prereqs=[{"ref": d, "hardness": "hard"}],
    )
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert q[0]["id"] == gated["id"] and q[0]["ready"] is False
    client.patch(
        f"/api/task/{child['id']}",
        json={"version": 1, "status": "done"},
        headers=auth(),
    )
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert q[0]["ready"] is True and q[0]["blocked_by"] == []
    assert (
        client.post(
            f"/api/agent/claim/{gated['id']}", headers=auth(AGENT_TOKEN)
        ).status_code
        == 200
    )


def test_agent_preview_upload_claimant_only_and_md(client):
    """Agent door for artifact previews: claimant-only, .md accepted, URL lands
    on the task for the review card."""
    t = agent_task(client)
    files = {"file": ("result.md", b"# Smoke\n\ndone", "text/markdown")}
    # not claimed yet -> 409
    r = client.post(
        f"/api/agent/upload-preview/{t['id']}", files=files, headers=auth(AGENT_TOKEN)
    )
    assert r.status_code == 409
    client.post(f"/api/agent/claim/{t['id']}", headers=auth(AGENT_TOKEN))
    r = client.post(
        f"/api/agent/upload-preview/{t['id']}", files=files, headers=auth(AGENT_TOKEN)
    )
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert url.endswith(".md")
    # served with markdown media type
    got = client.get(url)
    assert got.status_code == 200 and b"# Smoke" in got.content
    # the human door is human-only — an agent token must not overwrite
    # arbitrary tasks' previews through it (codex #1)
    assert (
        client.post(
            f"/api/task/{t['id']}/upload-preview",
            files=files,
            headers=auth(AGENT_TOKEN),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/task/{t['id']}/upload-preview", files=files, headers=auth()
        ).status_code
        == 201
    )
    # unsupported types rejected — incl. .html (stored-XSS vector, codex #4)
    for bad in (
        {"file": ("x.exe", b"MZ", "application/octet-stream")},
        {"file": ("x.html", b"<script>1</script>", "text/html")},
    ):
        assert (
            client.post(
                f"/api/agent/upload-preview/{t['id']}",
                files=bad,
                headers=auth(AGENT_TOKEN),
            ).status_code
            == 422
        )
    # after result the claim is no longer live — preview locked (codex #2)
    client.post(
        f"/api/agent/result/{t['id']}",
        json={"idempotency_key": "kp", "evidence": "done"},
        headers=auth(AGENT_TOKEN),
    )
    assert (
        client.post(
            f"/api/agent/upload-preview/{t['id']}",
            files=files,
            headers=auth(AGENT_TOKEN),
        ).status_code
        == 409
    )


def test_x_remote_user_not_trusted_by_default(client):
    """X-Remote-User is honored ONLY behind a trusted proxy (env opt-in) and
    NEVER together with a Bearer token (codex #5)."""
    agent_task(client)
    # Bearer + spoofed header -> header ignored, agent stays agent
    r = client.post(
        "/api/task/t-1/approve",
        headers={**auth(AGENT_TOKEN), "X-Remote-User": "roman"},
    )
    assert r.status_code == 403
    # header-only spoof without COCKPIT_TRUSTED_PROXY -> anonymous -> 401
    r = client.post("/api/task/t-1/approve", headers={"X-Remote-User": "roman"})
    assert r.status_code == 401
    # the SSE endpoint has its own auth path — same gate applies
    r = client.get("/api/events", headers={"X-Remote-User": "roman"})
    assert r.status_code == 401


def test_x_remote_user_with_basic_auth_is_honored(client, monkeypatch):
    """The prod browser case: Caddy authenticates via HTTP Basic, sets
    X-Remote-User, AND forwards the browser's `Authorization: Basic ...`
    upstream. Basic must NOT nuke the proxy identity — only Bearer marks a
    direct caller. Regression: 2026-07-05 deploy rejected ALL browser traffic
    through Caddy (login loop)."""
    monkeypatch.setenv("COCKPIT_TRUSTED_PROXY", "1")
    r = client.get(
        "/api/state",
        headers={
            "X-Remote-User": "roman",
            "Authorization": "Basic cm9tYW46aHVudGVyMg==",
        },
    )
    assert r.status_code == 200
    # Bearer still wins over the header (direct caller, codex #5)
    r = client.get(
        "/api/state",
        headers={"X-Remote-User": "roman", "Authorization": "Bearer nonsense"},
    )
    assert r.status_code == 401


def test_promote_with_edited_duplicate_text_rejected(client):
    """Dedupe re-runs on the FINAL promoted text (codex #6)."""
    a = client.post(
        "/api/agent/learning", json={"text": "rule A"}, headers=auth(AGENT_TOKEN)
    ).json()
    b = client.post(
        "/api/agent/learning", json={"text": "rule B"}, headers=auth(AGENT_TOKEN)
    ).json()
    client.post(
        f"/api/learning/{a['id']}/decide", json={"action": "promote"}, headers=auth()
    )
    r = client.post(
        f"/api/learning/{b['id']}/decide",
        json={"action": "promote", "text": "Rule A"},
        headers=auth(),
    )
    assert r.status_code == 409 and "duplicate" in r.json()["detail"]


def test_learning_candidate_promote_dismiss_flow(client):
    """Runner submits a candidate; it does NOT reach the playbook until a human
    promotes it; dedupe by text; dismiss retires it."""
    # submit
    r = client.post(
        "/api/agent/learning",
        json={
            "text": "Models default to adjusted EBITDA",
            "kind": "constraint",
            "source_task": "t-1",
        },
        headers=auth(AGENT_TOKEN),
    )
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert r.json()["status"] == "candidate" and r.json()["lane"] == "rd"
    # humans cannot submit via the agent door
    assert (
        client.post(
            "/api/agent/learning", json={"text": "x"}, headers=auth()
        ).status_code
        == 403
    )
    # duplicate (case-insensitive) returns the existing row, no second insert
    dup = client.post(
        "/api/agent/learning",
        json={"text": "models default to ADJUSTED ebitda"},
        headers=auth(AGENT_TOKEN),
    ).json()
    assert dup.get("duplicate") is True and dup["id"] == lid
    # candidate is NOT in the queue playbook yet
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()
    assert q["playbook"] == []
    # agent cannot decide; human promotes (with an edit)
    assert (
        client.post(
            f"/api/learning/{lid}/decide",
            json={"action": "promote"},
            headers=auth(AGENT_TOKEN),
        ).status_code
        == 403
    )
    r = client.post(
        f"/api/learning/{lid}/decide",
        json={
            "action": "promote",
            "text": "Always use adjusted EBITDA, never reported",
        },
        headers=auth(),
    )
    assert r.status_code == 200 and r.json()["status"] == "active"
    # now it rides with the queue fetch
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()
    assert q["playbook"] == [
        {
            "kind": "constraint",
            "text": "Always use adjusted EBITDA, never reported",
            "source_task": "t-1",
        }
    ]
    # visible in state for the UI strip
    st = client.get("/api/state", headers=auth()).json()
    assert any(x["id"] == lid and x["status"] == "active" for x in st["learnings"])
    # dismiss retires it from the playbook
    client.post(
        f"/api/learning/{lid}/decide", json={"action": "dismiss"}, headers=auth()
    )
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()
    assert q["playbook"] == []


def test_learning_playbook_cap(client):
    """The playbook is hard-capped — promotion into a full playbook 409s."""
    conn = client.cockpit_conn
    for i in range(40):
        conn.execute(
            "INSERT INTO learnings (lane, kind, text, status, created_at) "
            "VALUES ('rd','heuristic',?, 'active','x')",
            (f"rule {i}",),
        )
    conn.commit()
    r = client.post(
        "/api/agent/learning", json={"text": "one more"}, headers=auth(AGENT_TOKEN)
    )
    lid = r.json()["id"]
    r = client.post(
        f"/api/learning/{lid}/decide", json={"action": "promote"}, headers=auth()
    )
    assert r.status_code == 409 and "playbook full" in r.json()["detail"]
    # validation: garbage rejected
    assert (
        client.post(
            "/api/agent/learning", json={"text": "  "}, headers=auth(AGENT_TOKEN)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/agent/learning",
            json={"text": "x" * 301},
            headers=auth(AGENT_TOKEN),
        ).status_code
        == 422
    )


def test_agent_block_requires_claim(client):
    t = agent_task(client)
    assert (
        client.post(
            f"/api/agent/block/{t['id']}",
            json={"question": "q?"},
            headers=auth(AGENT_TOKEN),
        ).status_code
        == 409
    )


def test_agent_create_task(client):
    """client `add` — agent enqueues into its human's lane, AC enforced."""
    # no AC -> 422 (unverifiable tasks are not enqueuable)
    r = client.post(
        "/api/agent/task", json={"text": "no ac"}, headers=auth(AGENT_TOKEN)
    )
    assert r.status_code == 422
    # humans use /api/task, not the agent door
    assert (
        client.post(
            "/api/agent/task",
            json={"text": "x", "acceptance_criteria": "y"},
            headers=auth(),
        ).status_code
        == 403
    )
    r = client.post(
        "/api/agent/task",
        json={
            "text": "Update MOUSE onepager",
            "acceptance_criteria": "onepager reflects 2025 SUSA",
            "deal": "Mouse",
            "priority": "high",
        },
        headers=auth(AGENT_TOKEN),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # created in the REPRESENTED human's lane -> shows as RC, drained by RD's runner
    assert body["created_by"] == "rd"
    assert body["execution"] == "agent_supervised" and body["kind"] == "agent_job"
    assert body["runner"] == "local"
    q = client.get("/api/agent/queue", headers=auth(AGENT_TOKEN)).json()["queue"]
    assert body["id"] in [x["id"] for x in q]


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
