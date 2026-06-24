"""Personal todos (kind='personal') must be private to their creator — one human
must never receive the other's. Verifies the /api/state server-side scrub."""

import hashlib

RD_TOKEN = "test-token-rd"
FF_TOKEN = "test-token-ff"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _add_ff(conn):
    conn.execute(
        "INSERT INTO users (id, name, role, token_hash, initials, represents) "
        "VALUES (?,?,?,?,?,?)",
        (
            "ff",
            "ff",
            "human",
            hashlib.sha256(FF_TOKEN.encode()).hexdigest(),
            "FF",
            None,
        ),
    )
    conn.commit()


def _personal_texts(state):
    out = []
    for t in state.get("standalone_tasks", []):
        if t.get("kind") == "personal":
            out.append(t["text"])
    for sp in state.get("spaces", []):
        for ws in sp.get("workstreams", []):
            for d in ws.get("deliverables", []):
                for t in d.get("tasks", []):
                    if t.get("kind") == "personal":
                        out.append(t["text"])
    return out


def test_personal_todos_are_private_per_creator(client):
    _add_ff(client.cockpit_conn)

    r1 = client.post(
        "/api/task",
        json={"text": "rd-private", "kind": "personal", "owners": ["RD"]},
        headers=_auth(RD_TOKEN),
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        "/api/task",
        json={"text": "ff-private", "kind": "personal", "owners": ["FF"]},
        headers=_auth(FF_TOKEN),
    )
    assert r2.status_code == 201, r2.text

    rd_state = client.get("/api/state", headers=_auth(RD_TOKEN)).json()
    ff_state = client.get("/api/state", headers=_auth(FF_TOKEN)).json()

    rd_seen = _personal_texts(rd_state)
    ff_seen = _personal_texts(ff_state)

    assert "rd-private" in rd_seen
    assert "ff-private" not in rd_seen  # Roman must NOT see Flo's private todo
    assert "ff-private" in ff_seen
    assert "rd-private" not in ff_seen  # Flo must NOT see Roman's private todo


def _make_two_personal(client):
    """Returns (rd_task, ff_task) JSON for one personal todo per human."""
    _add_ff(client.cockpit_conn)
    rd = client.post(
        "/api/task",
        json={"text": "rd-secret", "kind": "personal"},
        headers=_auth(RD_TOKEN),
    )
    ff = client.post(
        "/api/task",
        json={"text": "ff-secret", "kind": "personal"},
        headers=_auth(FF_TOKEN),
    )
    assert rd.status_code == 201 and ff.status_code == 201
    return rd.json(), ff.json()


def test_export_md_does_not_leak_other_users_personal(client):
    """Finding 1: /api/export.md must scrub personal todos not owned by caller,
    for ALL scopes including scope=all."""
    _make_two_personal(client)

    rd_md = client.get("/api/export.md?scope=all", headers=_auth(RD_TOKEN)).text
    ff_md = client.get("/api/export.md?scope=all", headers=_auth(FF_TOKEN)).text

    assert "rd-secret" in rd_md
    assert "ff-secret" not in rd_md  # Roman's export must not contain Flo's body
    assert "ff-secret" in ff_md
    assert "rd-secret" not in ff_md


def test_activity_does_not_leak_other_users_personal_body(client):
    """Finding 2: /api/activity must not expose another user's personal task body."""
    rd_task, ff_task = _make_two_personal(client)

    # Roman views the activity log; NO personal task body leaks (bodies are not
    # written verbatim into audit_log, and another user's entry is redacted).
    rd_activity = client.get("/api/activity", headers=_auth(RD_TOKEN)).json()
    blob = repr(rd_activity)
    assert "ff-secret" not in blob
    assert "rd-secret" not in blob  # personal bodies never stored in audit

    by_entity = {e["entity"]: e for e in rd_activity["entries"]}
    # Flo's task entry is redacted for Roman.
    assert by_entity[ff_task["id"]].get("redacted") is True
    # Roman's own personal task entry is NOT flagged redacted (it is his).
    assert by_entity[rd_task["id"]].get("redacted") is not True

    # A targeted ?entity= lookup of Flo's task exposes no body to Roman.
    scoped = client.get(
        f"/api/activity?entity={ff_task['id']}", headers=_auth(RD_TOKEN)
    ).json()
    assert "ff-secret" not in repr(scoped)
    for e in scoped["entries"]:
        assert e["before"] is None and e["after"] is None


def test_non_creator_cannot_patch_personal(client):
    """Finding 3: a non-creator gets 403 on PATCH of a personal todo."""
    rd_task, _ = _make_two_personal(client)
    r = client.patch(
        rf"/api/task/{rd_task['id']}",
        json={"version": rd_task["version"], "text": "hijacked"},
        headers=_auth(FF_TOKEN),
    )
    assert r.status_code == 403, r.text
    # Creator can still patch their own.
    ok = client.patch(
        rf"/api/task/{rd_task['id']}",
        json={"version": rd_task["version"], "text": "rd-secret-edited"},
        headers=_auth(RD_TOKEN),
    )
    assert ok.status_code == 200, ok.text


def test_non_creator_cannot_delete_personal(client):
    """Finding 3: a non-creator gets 403 on DELETE of a personal todo."""
    rd_task, _ = _make_two_personal(client)
    r = client.delete(rf"/api/task/{rd_task['id']}", headers=_auth(FF_TOKEN))
    assert r.status_code == 403, r.text
    ok = client.delete(rf"/api/task/{rd_task['id']}", headers=_auth(RD_TOKEN))
    assert ok.status_code == 200, ok.text
