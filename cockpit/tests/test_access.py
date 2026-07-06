"""
Multi-user access control tests (SPEC-multi-user-access).

Coverage:
- Owner (rd, NULL profile → owner fallback): full access
- Advisor profile: read-only, module-filtered, workstream-scoped
- POST /api/admin/user: owner-only user provisioning
- PATCH /api/workstream/{wid}/access: owner-only workstream scoping
"""

import hashlib

import pytest

from tests.conftest import auth

ADVISOR_TOKEN = "test-token-advisor"


def _advisor_auth():
    return {"Authorization": f"Bearer {ADVISOR_TOKEN}"}


@pytest.fixture()
def advisor_client(cockpit_db, client):
    """Extend the base client fixture with a seeded advisor user."""
    cockpit_db.execute(
        "INSERT INTO users (id, name, initials, role, token_hash, profile) "
        "VALUES (?,?,?,?,?,?)",
        (
            "hj",
            "Heiko Jander",
            "HJ",
            "human",
            hashlib.sha256(ADVISOR_TOKEN.encode()).hexdigest(),
            "advisor",
        ),
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
    }
    assert p["profile"] == "owner"


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
# Workstream scoping (Option A): null = hidden from advisor
# ---------------------------------------------------------------------------


def _ws_ids_from_state(state):
    """Flatten workstream ids from nested spaces[].workstreams structure."""
    return {w["id"] for s in state.get("spaces", []) for w in s.get("workstreams", [])}


def test_workstream_null_allowed_profiles_hidden_from_advisor(advisor_client):
    """allowed_profiles=NULL → advisor cannot see the workstream."""
    wid = _make_ws(advisor_client, name="Private WS")
    # Confirm workstream exists (owner can see it)
    owner_state = advisor_client.get("/api/state", headers=auth()).json()
    assert wid in _ws_ids_from_state(owner_state)

    # Advisor state should NOT include it (allowed_profiles is NULL)
    advisor_state = advisor_client.get("/api/state", headers=_advisor_auth()).json()
    assert wid not in _ws_ids_from_state(advisor_state)


def test_workstream_whitelisted_visible_to_advisor(advisor_client):
    """allowed_profiles=["owner","advisor"] → advisor can see the workstream."""
    wid = _make_ws(advisor_client, name="Shared WS")

    # Owner grants access
    r = advisor_client.patch(
        f"/api/workstream/{wid}/access",
        json={"allowed_profiles": ["owner", "advisor"]},
        headers=auth(),
    )
    assert r.status_code == 200

    # Advisor state now includes the workstream
    advisor_state = advisor_client.get("/api/state", headers=_advisor_auth()).json()
    assert wid in _ws_ids_from_state(advisor_state)


# ---------------------------------------------------------------------------
# PATCH /api/workstream/{wid}/access — owner-only
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
# POST /api/admin/user — owner-only provisioning
# ---------------------------------------------------------------------------


def test_owner_can_create_user(advisor_client):
    r = advisor_client.post(
        "/api/admin/user",
        json={
            "id": "newuser",
            "name": "New User",
            "initials": "NU",
            "profile": "advisor",
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
        json={"id": "fresh", "name": "Fresh User", "profile": "viewer"},
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
        json={"id": "blocked", "name": "Blocked User", "profile": "viewer"},
        headers=_advisor_auth(),
    )
    assert r.status_code == 403


def test_admin_create_user_duplicate_rejected(advisor_client):
    payload = {"id": "dup", "name": "Dup User", "profile": "advisor"}
    advisor_client.post("/api/admin/user", json=payload, headers=auth())
    r = advisor_client.post("/api/admin/user", json=payload, headers=auth())
    assert r.status_code == 409


def test_admin_create_user_unknown_profile_rejected(advisor_client):
    r = advisor_client.post(
        "/api/admin/user",
        json={"id": "badprof", "name": "Bad Profile", "profile": "superadmin"},
        headers=auth(),
    )
    assert r.status_code == 422


def test_admin_create_user_missing_required_fields(advisor_client):
    r = advisor_client.post(
        "/api/admin/user",
        json={"name": "No ID"},
        headers=auth(),
    )
    assert r.status_code == 422
