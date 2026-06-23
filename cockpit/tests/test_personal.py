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
