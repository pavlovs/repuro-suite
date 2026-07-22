"""ACT1 slot add/remove tests.

Update tiles and decision rows carry data-slot; spare slots (data-slot-extra)
are hidden until revealed in the admin draft. Visibility state persists as ONE
inline edit under '__slots__' and rides the existing freeze/clear-on-publish
lifecycle — these tests pin that contract.
"""

import json

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# fixtures (same pattern as test_investor_view.py)


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_investor.db"
    monkeypatch.setenv("INVESTOR_DB", str(db_path))

    import src.db as db_mod

    db_mod.close_conn()
    yield str(db_path)
    db_mod.close_conn()


@pytest.fixture()
def client(isolated_db):
    from src import db as db_mod
    from src.api import app

    conn = db_mod.get_conn()
    for uid, name, initials, role in [
        ("rd", "Roman", "RD", "admin"),
        ("strada", "Strada", "ST", "investor"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
            (uid, name, initials, role),
        )
    conn.commit()

    with TestClient(app) as c:
        yield c


def _admin():
    return {"X-Remote-User": "roman"}


def _investor():
    return {"X-Remote-User": "investor"}


# ---------------------------------------------------------------------------
# 1. template carries the slots


def test_draft_has_all_slots(client):
    html = client.get("/", headers=_admin()).text
    assert html.count('data-slot="tile-') == 8
    assert html.count('data-slot="dec-') == 6
    assert html.count(" data-slot-extra>") == 8  # 4 spare tiles + 4 spare rows
    for i in (5, 6, 7, 8):
        assert f'data-edit-id="tile-{i}-title"' in html
    for i in (3, 4, 5, 6):
        assert f'data-edit-id="dec-{i}-title"' in html


def test_spare_slots_hidden_by_default(client):
    html = client.get("/", headers=_admin()).text
    # every spare slot starts with the slot-off class in markup (no-JS safe)
    assert html.count('class="tile changed-tile slot-off"') == 4
    assert html.count('<tr class="slot-off"') == 4


# ---------------------------------------------------------------------------
# 2. slot state persists as a normal inline edit


def test_slot_state_roundtrip(client):
    state = {"tile-5": 1, "tile-2": 0}
    r = client.post(
        "/api/inline-edit",
        json={"edit_id": "__slots__", "content": json.dumps(state)},
        headers=_admin(),
    )
    assert r.status_code == 200
    edits = client.get("/api/inline-edits", headers=_admin()).json()["edits"]
    assert json.loads(edits["__slots__"]) == state


# ---------------------------------------------------------------------------
# 3. publish freezes slot state into the snapshot and KEEPS the draft state
#    (Roman 10-07: publish must never scrub the draft)


def test_publish_freezes_slots_and_keeps_draft(client):
    client.post(
        "/api/inline-edit",
        json={"edit_id": "__slots__", "content": json.dumps({"tile-5": 1})},
        headers=_admin(),
    )
    client.post(
        "/api/inline-edit",
        json={"edit_id": "tile-5-title", "content": "Fifth update"},
        headers=_admin(),
    )
    pub = client.post("/api/investor-view/publish", headers=_admin()).json()
    assert pub["status"] == "published"
    assert pub["inline_edits_kept"] == 2

    # investor's snapshot carries the frozen slot state + content
    html = client.get("/" + pub["url"], headers=_investor()).text
    assert "__slots__" in html
    assert "Fifth update" in html
    assert "__INVESTOR_VIEW_PUBLISHED" in html

    # draft keeps the edits — slot stays revealed, content stays edited
    edits = client.get("/api/inline-edits", headers=_admin()).json()["edits"]
    assert edits["tile-5-title"] == "Fifth update"
    assert json.loads(edits["__slots__"]) == {"tile-5": 1}


# ---------------------------------------------------------------------------
# 4. hidden-slot content never ships to the investor (removed-but-recoverable leak)


def test_publish_strips_hidden_slot_content(client):
    # tile-5 revealed, written, then removed again; dec-1 edited then hidden;
    # dec-3 revealed and visible — only the visible content may publish.
    client.post(
        "/api/inline-edit",
        json={
            "edit_id": "__slots__",
            "content": json.dumps({"tile-5": 0, "dec-1": 0, "dec-3": 1}),
        },
        headers=_admin(),
    )
    for eid, content in [
        ("tile-5-title", "Secret draft note"),
        ("dec-1-title", "Edited then removed"),
        ("dec-3-title", "Visible new decision"),
    ]:
        client.post(
            "/api/inline-edit",
            json={"edit_id": eid, "content": content},
            headers=_admin(),
        )

    pub = client.post("/api/investor-view/publish", headers=_admin()).json()
    html = client.get("/" + pub["url"], headers=_investor()).text
    assert "Secret draft note" not in html
    assert "Edited then removed" not in html
    assert "Visible new decision" in html
    assert "__slots__" in html  # the visibility map itself stays frozen


def test_strip_hides_spare_content_absent_from_map():
    """A spare slot never revealed (absent from __slots__) is hidden by default —
    stray content edits on it must not publish either."""
    from src.api import _strip_hidden_slot_edits

    out = _strip_hidden_slot_edits(
        {"tile-6-title": "orphan", "tile-1-title": "kept", "__slots__": "{}"}
    )
    assert "tile-6-title" not in out
    assert out["tile-1-title"] == "kept"
    assert "__slots__" in out


def test_strip_fails_closed_on_malformed_slot_values():
    """The map is admin-supplied JSON — only an explicit 1/true counts as
    visible. String '1'/'0' or garbage must strip (privacy over display)."""
    from src.api import _strip_hidden_slot_edits

    slots = json.dumps({"tile-5": "1", "tile-6": "0", "tile-7": True, "dec-3": None})
    out = _strip_hidden_slot_edits(
        {
            "__slots__": slots,
            "tile-5-title": "string-one leaks?",
            "tile-6-title": "string-zero leaks?",
            "tile-7-title": "bool-true stays",
            "dec-3-title": "null leaks?",
        }
    )
    assert "tile-5-title" not in out
    assert "tile-6-title" not in out
    assert out["tile-7-title"] == "bool-true stays"
    assert "dec-3-title" not in out


# ---------------------------------------------------------------------------
# 5. hard gate scans content added through a spare slot


def test_denylist_gate_covers_slot_content(client):
    client.post(
        "/api/inline-edit",
        json={"edit_id": "__slots__", "content": json.dumps({"tile-5": 1})},
        headers=_admin(),
    )
    client.post(
        "/api/inline-edit",
        json={
            "edit_id": "tile-5-body",
            "content": "<ul><li>Aurica call notes</li></ul>",
        },
        headers=_admin(),
    )
    r = client.post("/api/investor-view/publish", headers=_admin())
    assert r.status_code == 409
    assert "hard_violations" in json.dumps(r.json())
