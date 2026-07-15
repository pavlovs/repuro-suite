"""
Multi-user access control tests — v13 teams-as-permission-carriers.

Coverage:
- Owner (rd, md team = is_admin=True): full access + admin operations
- Advisor (hj, advisor team = ro on workstreams+timeline): read-only, scoped
- Team gate: workstream_teams drives visibility (opt-in assignment)
- PATCH /api/workstream/{wid}/teams: new v13 team assignment endpoint
- POST /api/admin/user: admin-only provisioning, no profile validation
- /api/authz: Caddy forward_auth module gate
"""

import hashlib

import pytest

from tests.conftest import auth

ADVISOR_TOKEN = "test-token-advisor"


def _advisor_auth():
    return {"Authorization": f"Bearer {ADVISOR_TOKEN}"}


@pytest.fixture()
def advisor_client(cockpit_db, client):
    """Extend the base client fixture with a seeded advisor user in the advisor team."""
    cockpit_db.execute(
        "INSERT INTO users (id, name, initials, role, token_hash, profile, login) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            "hj",
            "Heiko Jander",
            "HJ",
            "human",
            hashlib.sha256(ADVISOR_TOKEN.encode()).hexdigest(),
            "advisor",
            "heiko",
        ),
    )
    cockpit_db.execute(
        "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
        ("advisor", "hj"),
    )
    cockpit_db.commit()
    return client


def _make_ws(client, name="Test WS", space_id="s-1", **kw):
    r = client.post(
        "/api/workstream",
        json={"name": name, "space_id": space_id, **kw},
        headers=auth(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_task(client, **kw):
    r = client.post("/api/task", json={"text": "test task", **kw}, headers=auth())
    assert r.status_code == 201, r.text
    return r.json()


def _ws_ids_from_state(state):
    """Flatten workstream ids from nested spaces[].workstreams structure."""
    return {w["id"] for s in state.get("spaces", []) for w in s.get("workstreams", [])}


# ---------------------------------------------------------------------------
# Owner (rd) — regression: existing behavior unchanged
# ---------------------------------------------------------------------------


def test_owner_state_all_modules_not_read_only(client):
    r = client.get("/api/state", headers=auth())
    assert r.status_code == 200
    p = r.json()["principal"]
    assert p["read_only"] is False
    assert set(p["modules"]) == {
        "overview",
        "week",
        "workstreams",
        "timeline",
        "agents",
        "relations",
        "calendar",
    }
    assert p["profile"] == "owner"
    assert p["is_admin"] is True


def test_owner_can_create_task(client):
    r = client.post("/api/task", json={"text": "owner task"}, headers=auth())
    assert r.status_code == 201


def test_owner_can_create_workstream(client):
    r = client.post(
        "/api/workstream",
        json={"name": "Owner WS", "space_id": "s-1"},
        headers=auth(),
    )
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Advisor — state: read_only=True, module-filtered
# ---------------------------------------------------------------------------


def test_advisor_state_read_only_and_restricted_modules(advisor_client):
    r = advisor_client.get("/api/state", headers=_advisor_auth())
    assert r.status_code == 200
    p = r.json()["principal"]
    assert p["read_only"] is True
    assert set(p["modules"]) == {"workstreams", "timeline"}
    assert p["profile"] == "advisor"
    assert p["is_admin"] is False


# ---------------------------------------------------------------------------
# Advisor — mutation endpoints return 403
# ---------------------------------------------------------------------------


def test_advisor_task_create_blocked(advisor_client):
    r = advisor_client.post(
        "/api/task", json={"text": "should fail"}, headers=_advisor_auth()
    )
    assert r.status_code == 403


def test_advisor_task_patch_blocked(advisor_client):
    t = _make_task(advisor_client)
    r = advisor_client.patch(
        f"/api/task/{t['id']}",
        json={"version": t["version"], "status": "in_progress"},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


def test_advisor_task_delete_blocked(advisor_client):
    t = _make_task(advisor_client)
    r = advisor_client.delete(f"/api/task/{t['id']}", headers=_advisor_auth())
    assert r.status_code == 403


def test_advisor_workstream_create_blocked(advisor_client):
    r = advisor_client.post(
        "/api/workstream",
        json={"name": "Blocked WS"},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


def test_advisor_workstream_patch_blocked(advisor_client):
    wid = _make_ws(advisor_client)
    r = advisor_client.patch(
        f"/api/workstream/{wid}",
        json={"version": 1, "name": "Renamed"},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


def test_advisor_deliverable_create_blocked(advisor_client):
    wid = _make_ws(advisor_client)
    r = advisor_client.post(
        "/api/deliverable",
        json={"workstream_id": wid, "name": "Blocked deliv"},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Workstream team gate — workstream_teams drives visibility (v13)
# Semantics: no assignment = visible to all (opt-in); assignment = team-gated.
# ---------------------------------------------------------------------------


def test_workstream_no_team_assignment_visible_to_advisor(advisor_client):
    """workstream_teams empty for a WS → visible to everyone."""
    wid = _make_ws(advisor_client, name="Open WS")
    advisor_state = advisor_client.get("/api/state", headers=_advisor_auth()).json()
    assert wid in _ws_ids_from_state(advisor_state)


def test_workstream_assigned_to_other_team_hidden_from_advisor(advisor_client):
    """WS assigned to md team only → advisor (not in md) cannot see it."""
    wid = _make_ws(advisor_client, name="Admin-only WS")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/teams",
        json={"team_ids": ["md"]},
        headers=auth(),
    )
    assert r.status_code == 200

    advisor_state = advisor_client.get("/api/state", headers=_advisor_auth()).json()
    assert wid not in _ws_ids_from_state(advisor_state)

    owner_state = advisor_client.get("/api/state", headers=auth()).json()
    assert wid in _ws_ids_from_state(owner_state)


def test_workstream_assigned_to_advisor_team_visible(advisor_client):
    """WS assigned to advisor team → advisor can see it."""
    wid = _make_ws(advisor_client, name="Shared WS")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/teams",
        json={"team_ids": ["advisor"]},
        headers=auth(),
    )
    assert r.status_code == 200

    advisor_state = advisor_client.get("/api/state", headers=_advisor_auth()).json()
    assert wid in _ws_ids_from_state(advisor_state)


# ---------------------------------------------------------------------------
# PATCH /api/workstream/{wid}/access — admin-only (deprecated v12 endpoint)
# ---------------------------------------------------------------------------


def test_advisor_cannot_update_workstream_access(advisor_client):
    wid = _make_ws(advisor_client, name="WS for access test")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/access",
        json={"allowed_profiles": ["owner", "advisor"]},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


def test_owner_can_update_workstream_access(advisor_client):
    wid = _make_ws(advisor_client, name="WS access by owner")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/access",
        json={"allowed_profiles": ["owner"]},
        headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["allowed_profiles"] == ["owner"]


def test_patch_workstream_access_unknown_profile_rejected(advisor_client):
    wid = _make_ws(advisor_client, name="WS for bad profile")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/access",
        json={"allowed_profiles": ["nonexistent"]},
        headers=auth(),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/workstream/{wid}/teams — admin-only, v13 primary assignment path
# ---------------------------------------------------------------------------


def test_patch_workstream_teams_clears_on_empty(advisor_client):
    """team_ids=[] clears all assignments → WS becomes visible to all."""
    wid = _make_ws(advisor_client, name="WS to clear")
    advisor_client.patch(
        f"/api/workstream/{wid}/teams",
        json={"team_ids": ["md"]},
        headers=auth(),
    )
    r = advisor_client.patch(
        f"/api/workstream/{wid}/teams",
        json={"team_ids": []},
        headers=auth(),
    )
    assert r.status_code == 200
    advisor_state = advisor_client.get("/api/state", headers=_advisor_auth()).json()
    assert wid in _ws_ids_from_state(advisor_state)


def test_patch_workstream_teams_unknown_team_rejected(advisor_client):
    wid = _make_ws(advisor_client, name="WS for bad team")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/teams",
        json={"team_ids": ["nonexistent"]},
        headers=auth(),
    )
    assert r.status_code == 422


def test_advisor_cannot_update_workstream_teams(advisor_client):
    wid = _make_ws(advisor_client, name="WS teams blocked")
    r = advisor_client.patch(
        f"/api/workstream/{wid}/teams",
        json={"team_ids": ["advisor"]},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/user — admin-only, v13: no profile validation
# ---------------------------------------------------------------------------


def test_owner_can_create_user(advisor_client):
    r = advisor_client.post(
        "/api/admin/user",
        json={
            "id": "newuser",
            "name": "New User",
            "initials": "NU",
        },
        headers=auth(),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "newuser"
    assert len(body["token"]) >= 32  # secrets.token_urlsafe(32) → 43 chars


def test_admin_create_user_returns_token_once(advisor_client):
    """Token is returned in response; subsequent state calls with that token work."""
    r = advisor_client.post(
        "/api/admin/user",
        json={"id": "fresh", "name": "Fresh User"},
        headers=auth(),
    )
    assert r.status_code == 201
    token = r.json()["token"]
    state = advisor_client.get(
        "/api/state", headers={"Authorization": f"Bearer {token}"}
    )
    assert state.status_code == 200
    assert state.json()["principal"]["id"] == "fresh"


def test_advisor_cannot_create_user(advisor_client):
    r = advisor_client.post(
        "/api/admin/user",
        json={"id": "blocked", "name": "Blocked User"},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


def test_admin_create_user_duplicate_rejected(advisor_client):
    payload = {"id": "dup", "name": "Dup User"}
    advisor_client.post("/api/admin/user", json=payload, headers=auth())
    r = advisor_client.post("/api/admin/user", json=payload, headers=auth())
    assert r.status_code == 409


def test_admin_create_user_missing_required_fields(advisor_client):
    r = advisor_client.post(
        "/api/admin/user",
        json={"name": "No ID"},
        headers=auth(),
    )
    assert r.status_code == 422


def test_admin_create_user_with_teams(advisor_client):
    """User created with teams list gets correct team membership."""
    r = advisor_client.post(
        "/api/admin/user",
        json={"id": "newadv", "name": "New Advisor", "teams": ["advisor"]},
        headers=auth(),
    )
    assert r.status_code == 201
    token = r.json()["token"]
    state = advisor_client.get(
        "/api/state", headers={"Authorization": f"Bearer {token}"}
    )
    p = state.json()["principal"]
    assert "workstreams" in p["modules"]
    assert p["read_only"] is True


# ---------------------------------------------------------------------------
# /api/authz — Caddy forward_auth gate (v13)
# Uses X-Remote-User: "roman" → _CADDY_USER_MAP → rd (admin)
#       X-Remote-User: "heiko" → users.login=heiko → hj (advisor)
# ---------------------------------------------------------------------------


def test_authz_admin_always_allowed_get(client):
    """is_admin → 200 for any module regardless of method."""
    r = client.get(
        "/api/authz",
        params={"module": "dealroom"},
        headers={"X-Remote-User": "roman", "X-Forwarded-Method": "GET"},
    )
    assert r.status_code == 200


def test_authz_admin_always_allowed_post(client):
    """is_admin → 200 even for write methods."""
    r = client.get(
        "/api/authz",
        params={"module": "allex"},
        headers={"X-Remote-User": "roman", "X-Forwarded-Method": "POST"},
    )
    assert r.status_code == 200


def test_authz_ro_read_allowed(advisor_client):
    """advisor has workstreams=ro; GET → 200."""
    r = advisor_client.get(
        "/api/authz",
        params={"module": "workstreams"},
        headers={"X-Remote-User": "heiko", "X-Forwarded-Method": "GET"},
    )
    assert r.status_code == 200


def test_authz_ro_write_blocked(advisor_client):
    """advisor has workstreams=ro; POST → 403."""
    r = advisor_client.get(
        "/api/authz",
        params={"module": "workstreams"},
        headers={"X-Remote-User": "heiko", "X-Forwarded-Method": "POST"},
    )
    assert r.status_code == 403


def test_authz_no_module_access_blocked(advisor_client):
    """advisor has no agents perm → 403 regardless of method."""
    r = advisor_client.get(
        "/api/authz",
        params={"module": "agents"},
        headers={"X-Remote-User": "heiko", "X-Forwarded-Method": "GET"},
    )
    assert r.status_code == 403


def test_authz_no_user_identity_blocked(client):
    """Missing X-Remote-User → 403."""
    r = client.get("/api/authz", params={"module": "dealroom"})
    assert r.status_code == 403


def test_authz_unknown_user_blocked(client):
    """X-Remote-User not in login or CADDY_USER_MAP → 403."""
    r = client.get(
        "/api/authz",
        params={"module": "dealroom"},
        headers={"X-Remote-User": "nobody"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Fail-closed hardening (review fixes on top of the v13 build)
# ---------------------------------------------------------------------------

TEAMLESS_TOKEN = "test-token-teamless"
HRONLY_TOKEN = "test-token-hronly"


def _seed_user(cockpit_db, uid, token, profile=None, login=None, teams=()):
    cockpit_db.execute(
        "INSERT INTO users (id, name, initials, role, token_hash, profile, login) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            uid,
            uid.upper(),
            uid[:2].upper(),
            "human",
            hashlib.sha256(token.encode()).hexdigest(),
            profile,
            login,
        ),
    )
    for tid in teams:
        cockpit_db.execute(
            "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
            (tid, uid),
        )
    cockpit_db.commit()


def test_teamless_new_user_fail_closed(cockpit_db, client):
    """A non-legacy user with zero teams gets NOTHING — removing someone's
    last team must revoke access, not escalate to owner-equivalent."""
    _seed_user(cockpit_db, "ext1", TEAMLESS_TOKEN)
    _make_ws(client, name="Visible WS")
    hdrs = {"Authorization": f"Bearer {TEAMLESS_TOKEN}"}
    state = client.get("/api/state", headers=hdrs).json()
    assert state["principal"]["modules"] == []
    assert state["principal"]["perms"] == {}
    assert state["principal"]["read_only"] is True
    assert _ws_ids_from_state(state) == set()
    r = client.post("/api/task", json={"text": "nope"}, headers=hdrs)
    assert r.status_code == 403


def test_teamless_legacy_owner_still_fail_open(cockpit_db, client):
    """Legacy marker (profile='owner' from the v12 backfill) keeps full access
    even with zero team rows — rd/ff can never be locked out."""
    _seed_user(cockpit_db, "legacy1", "test-token-legacy", profile="owner")
    hdrs = {"Authorization": "Bearer test-token-legacy"}
    state = client.get("/api/state", headers=hdrs).json()
    assert state["principal"]["read_only"] is False
    assert "workstreams" in state["principal"]["perms"]


# ---------------------------------------------------------------------------
# Multi-user personal cockpit (2026-07-15): users/lanes payload, per-user agent
# scoping, lane-scoped learnings, agent-user provisioning
# ---------------------------------------------------------------------------

TEAMMEMBER_TOKEN = "test-token-anton"


def _team_auth():
    return {"Authorization": f"Bearer {TEAMMEMBER_TOKEN}"}


@pytest.fixture()
def team_member_client(cockpit_db, client):
    """Non-admin team member (anton) in a crew team with workstreams+agents rw."""
    cockpit_db.execute(
        "INSERT INTO teams (id, name, permissions) VALUES ('crew','Crew',"
        '\'{"overview":"ro","week":"rw","workstreams":"rw","agents":"rw"}\')'
    )
    cockpit_db.commit()
    _seed_user(cockpit_db, "anton", TEAMMEMBER_TOKEN, login="anton", teams=("crew",))
    return client


def _agent_task(client, headers, text="agent job"):
    r = client.post(
        "/api/task",
        json={
            "text": text,
            "execution": "agent_supervised",
            "acceptance_criteria": "done when done",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _all_task_ids(state):
    ids = {t["id"] for t in state.get("standalone_tasks", [])}
    for s in state.get("spaces", []):
        for w in s.get("workstreams", []):
            for d in w.get("deliverables", []):
                ids |= {t["id"] for t in d.get("tasks", [])}
    return ids


def test_state_contains_users_and_lanes(client):
    state = client.get("/api/state", headers=auth()).json()
    users = {u["id"]: u for u in state["users"]}
    assert "rd" in users and users["rd"]["initials"] == "RD"
    assert all(u["id"] != "rc-agent" for u in state["users"])  # humans only
    assert state["lanes"] == {"rd": "RC"}


def test_non_admin_sees_only_own_agent_tasks(team_member_client):
    c = team_member_client
    foreign = _agent_task(c, auth(), "rd's agent job")
    own = _agent_task(c, _team_auth(), "anton's agent job")
    plain = c.post("/api/task", json={"text": "shared plain"}, headers=auth())
    assert plain.status_code == 201

    member_ids = _all_task_ids(c.get("/api/state", headers=_team_auth()).json())
    assert own["id"] in member_ids
    assert foreign["id"] not in member_ids
    assert plain.json()["id"] in member_ids  # non-agent tasks stay shared

    admin_ids = _all_task_ids(c.get("/api/state", headers=auth()).json())
    assert foreign["id"] in admin_ids and own["id"] in admin_ids


def test_non_admin_learnings_scoped_to_own_lane(cockpit_db, team_member_client):
    c = team_member_client
    for lane in ("rd", "anton", None):
        cockpit_db.execute(
            "INSERT INTO learnings (lane, text, status, created_at) "
            "VALUES (?,?, 'candidate', '2026-07-15T00:00:00Z')",
            (lane, f"lesson for {lane or 'all'}"),
        )
    cockpit_db.commit()
    member = c.get("/api/state", headers=_team_auth()).json()
    assert {l["lane"] for l in member["learnings"]} == {"anton"}
    admin = c.get("/api/state", headers=auth()).json()
    assert {l["lane"] for l in admin["learnings"]} == {"rd", "anton", None}


def test_admin_can_create_agent_user_with_lane(team_member_client):
    c = team_member_client
    r = c.post(
        "/api/admin/user",
        json={
            "id": "ac-agent",
            "name": "Anton's Claude",
            "initials": "AC",
            "role": "agent",
            "represents": "anton",
        },
        headers=auth(),
    )
    assert r.status_code == 201, r.text
    state = c.get("/api/state", headers=auth()).json()
    assert state["lanes"]["anton"] == "AC"
    # the new agent token drains anton's lane
    own = _agent_task(c, _team_auth(), "anton lane job")
    q = c.get(
        "/api/agent/queue",
        headers={"Authorization": f"Bearer {r.json()['token']}"},
    ).json()
    assert [t["id"] for t in q["queue"]] == [own["id"]]


def test_admin_create_user_rejects_unknown_represents(client):
    r = client.post(
        "/api/admin/user",
        json={"id": "x-agent", "name": "X", "role": "agent", "represents": "ghost"},
        headers=auth(),
    )
    assert r.status_code == 422


def test_admin_patch_user_name_initials(team_member_client):
    c = team_member_client
    r = c.patch(
        "/api/admin/user/anton",
        json={"name": "Anton Neu", "initials": "AN"},
        headers=auth(),
    )
    assert r.status_code == 200
    ov = c.get("/api/admin/overview", headers=auth()).json()
    anton = next(u for u in ov["users"] if u["id"] == "anton")
    assert anton["name"] == "Anton Neu" and anton["initials"] == "AN"


def test_non_admin_cannot_patch_users(team_member_client):
    r = team_member_client.patch(
        "/api/admin/user/anton", json={"name": "Hax"}, headers=_team_auth()
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Side-door privacy (codex 2026-07-15): export, activity, per-task routes,
# learning decide — every path must enforce the same lane privacy as /api/state
# ---------------------------------------------------------------------------


def test_export_md_scrubs_foreign_agent_tasks(team_member_client):
    c = team_member_client
    _agent_task(c, auth(), "SECRET rd agent job")
    own = _agent_task(c, _team_auth(), "anton export job")
    md = c.get("/api/export.md?scope=all", headers=_team_auth()).text
    assert "SECRET rd agent job" not in md
    assert "anton export job" in md
    admin_md = c.get("/api/export.md?scope=all", headers=auth()).text
    assert "SECRET rd agent job" in admin_md and own["id"] in admin_md


def test_activity_hides_foreign_agent_entries(team_member_client):
    c = team_member_client
    foreign = _agent_task(c, auth(), "SECRET rd activity job")
    own = _agent_task(c, _team_auth(), "anton activity job")
    entries = c.get("/api/activity", headers=_team_auth()).json()["entries"]
    assert all(e["entity"] != foreign["id"] for e in entries)
    assert any(e["entity"] == own["id"] for e in entries)
    admin_entries = c.get("/api/activity", headers=auth()).json()["entries"]
    assert any(e["entity"] == foreign["id"] for e in admin_entries)


def test_non_admin_cannot_touch_foreign_agent_task(team_member_client):
    c = team_member_client
    foreign = _agent_task(c, auth(), "rd guarded job")
    # PATCH
    r = c.patch(
        f"/api/task/{foreign['id']}",
        json={"version": foreign["version"], "text": "hax"},
        headers=_team_auth(),
    )
    assert r.status_code == 403
    # DELETE
    assert (
        c.delete(f"/api/task/{foreign['id']}", headers=_team_auth()).status_code == 403
    )
    # verdicts on an in-review foreign task
    r = c.patch(
        f"/api/task/{foreign['id']}",
        json={"version": foreign["version"], "status": "in_review"},
        headers=auth(),
    )
    assert r.status_code == 200
    for action, body in (
        ("approve", {}),
        ("reject", {}),
        ("request-changes", {"feedback": "nope"}),
    ):
        r = c.post(
            f"/api/task/{foreign['id']}/{action}", json=body, headers=_team_auth()
        )
        assert r.status_code == 403, action
    # own agent task stays fully workable
    own = _agent_task(c, _team_auth(), "anton workable job")
    r = c.patch(
        f"/api/task/{own['id']}",
        json={"version": own["version"], "text": "anton edited"},
        headers=_team_auth(),
    )
    assert r.status_code == 200


def test_non_admin_learning_decide_lane_gated(cockpit_db, team_member_client):
    c = team_member_client
    for lane in ("rd", "anton", None):
        cockpit_db.execute(
            "INSERT INTO learnings (lane, text, status, created_at) "
            "VALUES (?,?, 'candidate', '2026-07-15T00:00:00Z')",
            (lane, f"decide test {lane or 'global'}"),
        )
    cockpit_db.commit()
    ids = {
        r["lane"]: r["id"]
        for r in cockpit_db.execute(
            "SELECT id, lane FROM learnings WHERE text LIKE 'decide test %'"
        )
    }
    deny_rd = c.post(
        f"/api/learning/{ids['rd']}/decide",
        json={"action": "dismiss"},
        headers=_team_auth(),
    )
    assert deny_rd.status_code == 403
    deny_global = c.post(
        f"/api/learning/{ids[None]}/decide",
        json={"action": "dismiss"},
        headers=_team_auth(),
    )
    assert deny_global.status_code == 403
    own = c.post(
        f"/api/learning/{ids['anton']}/decide",
        json={"action": "promote"},
        headers=_team_auth(),
    )
    assert own.status_code == 200
    admin = c.post(
        f"/api/learning/{ids['rd']}/decide",
        json={"action": "dismiss"},
        headers=auth(),
    )
    assert admin.status_code == 200


def test_non_admin_reorder_and_import_cannot_touch_foreign_agent(team_member_client):
    c = team_member_client
    foreign = _agent_task(c, auth(), "rd reorder/import guard")
    own = c.post("/api/task", json={"text": "anton plain"}, headers=_team_auth()).json()
    # reorder including a foreign agent task -> 403
    r = c.patch(
        "/api/tasks/reorder",
        json={"task_ids": [own["id"], foreign["id"]]},
        headers=_team_auth(),
    )
    assert r.status_code == 403
    # reorder of only own tasks -> ok
    r = c.patch(
        "/api/tasks/reorder", json={"task_ids": [own["id"]]}, headers=_team_auth()
    )
    assert r.status_code == 200
    # md import targeting the foreign task -> 403
    md = f"## task-update\n- id: {foreign['id']} | version: {foreign['version']} | text: hax\n"
    r = c.post(
        "/api/import",
        content=md,
        headers={**_team_auth(), "Content-Type": "text/markdown"},
    )
    assert r.status_code == 403


def test_non_admin_cannot_upload_preview_to_foreign_agent(team_member_client):
    c = team_member_client
    foreign = _agent_task(c, auth(), "rd preview guard")
    r = c.post(
        f"/api/task/{foreign['id']}/upload-preview",
        files={"file": ("x.md", b"secret", "text/markdown")},
        headers=_team_auth(),
    )
    assert r.status_code == 403


def test_activity_redacts_deleted_task_body_for_non_admin(team_member_client):
    c = team_member_client
    foreign = _agent_task(c, auth(), "SECRET deleted agent body")
    assert c.delete(f"/api/task/{foreign['id']}", headers=auth()).status_code == 200
    # non-admin: EVERY audit entry for the deleted foreign task carries no body
    entries = c.get("/api/activity", headers=_team_auth()).json()["entries"]
    mine = [e for e in entries if e["entity"] == foreign["id"]]
    for e in mine:
        assert e.get("before") is None and e.get("after") is None
    # admin: the body survives somewhere (create.after or delete.before)
    admin_entries = c.get("/api/activity", headers=auth()).json()["entries"]
    admin_mine = [e for e in admin_entries if e["entity"] == foreign["id"]]
    assert any(e.get("before") or e.get("after") for e in admin_mine)


def test_non_admin_delete_cannot_sideeffect_foreign_agent(team_member_client):
    c = team_member_client
    # (1) deleting an own task that a foreign agent task depends on -> blocked
    gate = c.post("/api/task", json={"text": "anton gate"}, headers=_team_auth()).json()
    dep = c.post(
        "/api/task",
        json={
            "text": "rd agent depends on anton",
            "execution": "agent_supervised",
            "acceptance_criteria": "x",
            "prereqs": [{"ref": gate["id"], "hardness": "hard"}],
        },
        headers=auth(),
    )
    assert dep.status_code == 201
    assert c.delete(f"/api/task/{gate['id']}", headers=_team_auth()).status_code == 403
    # admin can (strips the ref)
    assert c.delete(f"/api/task/{gate['id']}", headers=auth()).status_code == 200

    # (2) deleting a shared deliverable that holds a foreign agent task -> blocked
    wid = _make_ws(c, name="Shared deliv WS")
    did = c.post(
        "/api/deliverable",
        json={"workstream_id": wid, "name": "shared deliv"},
        headers=_team_auth(),
    ).json()["id"]
    c.post(
        "/api/task",
        json={
            "text": "rd agent under shared deliv",
            "deliverable_id": did,
            "execution": "agent_supervised",
            "acceptance_criteria": "x",
        },
        headers=auth(),
    )
    assert c.delete(f"/api/deliverable/{did}", headers=_team_auth()).status_code == 403
    assert c.delete(f"/api/deliverable/{did}", headers=auth()).status_code == 200


def test_non_admin_progress_counts_match_visible_tasks(team_member_client):
    c = team_member_client
    wid = _make_ws(c, name="Progress WS")
    r = c.post(
        "/api/deliverable",
        json={"workstream_id": wid, "name": "Progress deliv"},
        headers=auth(),
    )
    did = r.json()["id"]
    c.post(
        "/api/task", json={"text": "plain child", "deliverable_id": did}, headers=auth()
    )
    r = c.post(
        "/api/task",
        json={
            "text": "rd agent child",
            "deliverable_id": did,
            "execution": "agent_supervised",
            "acceptance_criteria": "x",
        },
        headers=auth(),
    )
    assert r.status_code == 201
    st = c.get("/api/state", headers=_team_auth()).json()
    deliv = next(
        d
        for s in st["spaces"]
        for w in s["workstreams"]
        for d in w["deliverables"]
        if d["id"] == did
    )
    assert deliv["computed"]["progress"]["total"] == len(deliv["tasks"]) == 1


def test_module_gate_bounds_state_payload(cockpit_db, client):
    """A team WITHOUT the workstreams module must not receive workstream/task
    data in /api/state, even for unassigned (visible-to-all) workstreams."""
    cockpit_db.execute(
        "INSERT INTO teams (id, name, permissions) VALUES ('hr','HR','{\"relations\":\"rw\"}')"
    )
    cockpit_db.commit()
    _seed_user(cockpit_db, "hruser", HRONLY_TOKEN, teams=("hr",))
    _make_ws(client, name="Unassigned WS")
    hdrs = {"Authorization": f"Bearer {HRONLY_TOKEN}"}
    state = client.get("/api/state", headers=hdrs).json()
    assert state["principal"]["perms"] == {"relations": "rw"}
    assert _ws_ids_from_state(state) == set()
    r = client.post("/api/task", json={"text": "nope"}, headers=hdrs)
    assert r.status_code == 403
