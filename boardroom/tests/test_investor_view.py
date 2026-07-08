"""Investor-view draft/publish tests.

Covers: auth-gated / route, publish snapshot, inline-edit freezing, week
switching, denylist gate, unpublish, schema migration v2→v3, draft toolbar,
published flag injection.
"""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# fixtures


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
        ("ff", "Florian", "FF", "admin"),
        ("strada", "Strada", "ST", "investor"),
    ]:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
            (uid, name, initials, role),
        )
    conn.commit()

    with TestClient(app) as c:
        yield c


def _admin(headers=None):
    h = {"X-Remote-User": "roman"}
    if headers:
        h.update(headers)
    return h


def _investor(headers=None):
    h = {"X-Remote-User": "investor"}
    if headers:
        h.update(headers)
    return h


# ---------------------------------------------------------------------------
# 1. GET / — admin sees draft with toolbar, investor sees published or holding


def test_admin_sees_draft_with_toolbar(client):
    r = client.get("/", headers=_admin())
    assert r.status_code == 200
    html = r.text
    assert "draft-toolbar" in html
    assert "DRAFT" in html
    assert "Not visible to investors" in html


def test_investor_sees_holding_page_when_nothing_published(client):
    r = client.get("/", headers=_investor())
    assert r.status_code == 200
    assert "No published content" in r.text
    assert "draft-toolbar" not in r.text


def test_investor_sees_published_snapshot(client):
    client.post("/api/investor-view/publish", headers=_admin())
    r = client.get("/", headers=_investor())
    assert r.status_code == 200
    html = r.text
    assert "__INVESTOR_VIEW_PUBLISHED" in html
    assert "__FROZEN_EDITS" in html
    assert "draft-toolbar" not in html
    assert "Investor View" in html


def test_no_header_gets_draft(client):
    """Local dev (no X-Remote-User header) sees the draft."""
    r = client.get("/")
    assert r.status_code == 200
    assert "draft-toolbar" in r.text


# ---------------------------------------------------------------------------
# 2. POST /api/investor-view/publish


def test_publish_creates_published_row(client):
    r = client.post("/api/investor-view/publish", headers=_admin())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "published"
    assert "id" in data
    assert "ref" in data
    assert "published_at" in data


def test_publish_investor_only_403(client):
    r = client.post("/api/investor-view/publish", headers=_investor())
    assert r.status_code == 403


def test_publish_no_auth_401(client):
    r = client.post("/api/investor-view/publish")
    assert r.status_code == 401


def test_publish_archives_previous(client):
    r1 = client.post("/api/investor-view/publish", headers=_admin())
    id1 = r1.json()["id"]

    r2 = client.post("/api/investor-view/publish", headers=_admin())
    id2 = r2.json()["id"]

    assert id2 != id1

    from src import db as db_mod

    conn = db_mod.get_conn()
    row1 = conn.execute("SELECT status FROM publications WHERE id=?", (id1,)).fetchone()
    row2 = conn.execute("SELECT status FROM publications WHERE id=?", (id2,)).fetchone()
    assert row1["status"] == "archived"
    assert row2["status"] == "published"


def test_publish_stores_html_and_edits(client):
    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "INSERT INTO inline_edits (edit_id, content, updated_by, updated_at) "
        "VALUES ('tile-1-title', 'Edited Title', 'rd', '2026-07-08T00:00:00Z')"
    )
    conn.commit()

    r = client.post("/api/investor-view/publish", headers=_admin())
    pub_id = r.json()["id"]

    row = conn.execute("SELECT body FROM publications WHERE id=?", (pub_id,)).fetchone()
    body = json.loads(row["body"])
    assert "html" in body
    assert isinstance(body["html"], str)
    assert len(body["html"]) > 100
    assert "inline_edits" in body
    assert body["inline_edits"]["tile-1-title"] == "Edited Title"


def test_publish_one_published_per_kind(client):
    """Partial unique index: only one published investor_view at a time."""
    client.post("/api/investor-view/publish", headers=_admin())

    from src import db as db_mod

    conn = db_mod.get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM publications "
        "WHERE kind='investor_view' AND status='published'"
    ).fetchone()[0]
    assert count == 1

    client.post("/api/investor-view/publish", headers=_admin())
    count = conn.execute(
        "SELECT COUNT(*) FROM publications "
        "WHERE kind='investor_view' AND status='published'"
    ).fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# 3. Inline edits frozen at publish time


def test_edits_frozen_at_publish(client):
    """Edits made AFTER publish must not affect the published snapshot."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "INSERT INTO inline_edits (edit_id, content, updated_by, updated_at) "
        "VALUES ('tile-1-title', 'Before Publish', 'rd', '2026-07-08T00:00:00Z')"
    )
    conn.commit()

    client.post("/api/investor-view/publish", headers=_admin())

    conn.execute(
        "UPDATE inline_edits SET content='After Publish' WHERE edit_id='tile-1-title'"
    )
    conn.commit()

    r = client.get("/", headers=_investor())
    html = r.text
    assert "Before Publish" in html
    assert "After Publish" not in html


# ---------------------------------------------------------------------------
# 4. POST /api/investor-view/unpublish


def test_unpublish_archives_row(client):
    r = client.post("/api/investor-view/publish", headers=_admin())
    pub_id = r.json()["id"]

    r2 = client.post("/api/investor-view/unpublish", headers=_admin())
    assert r2.status_code == 200
    assert r2.json()["status"] == "archived"
    assert r2.json()["id"] == pub_id


def test_unpublish_investor_sees_holding(client):
    client.post("/api/investor-view/publish", headers=_admin())
    client.post("/api/investor-view/unpublish", headers=_admin())

    r = client.get("/", headers=_investor())
    assert "No published content" in r.text


def test_unpublish_when_nothing_published_404(client):
    r = client.post("/api/investor-view/unpublish", headers=_admin())
    assert r.status_code == 404


def test_unpublish_investor_only_403(client):
    r = client.post("/api/investor-view/unpublish", headers=_investor())
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 5. GET /api/investor-view/weeks


def test_weeks_empty_initially(client):
    r = client.get("/api/investor-view/weeks", headers=_admin())
    assert r.status_code == 200
    assert r.json()["weeks"] == []


def test_weeks_lists_published_and_archived(client):
    client.post("/api/investor-view/publish", headers=_admin())
    client.post("/api/investor-view/publish", headers=_admin())

    r = client.get("/api/investor-view/weeks", headers=_admin())
    weeks = r.json()["weeks"]
    assert len(weeks) == 2
    statuses = {w["status"] for w in weeks}
    assert "published" in statuses
    assert "archived" in statuses


def test_weeks_investor_can_access(client):
    client.post("/api/investor-view/publish", headers=_admin())
    r = client.get("/api/investor-view/weeks", headers=_investor())
    assert r.status_code == 200
    assert len(r.json()["weeks"]) == 1


def test_weeks_no_auth_401(client):
    r = client.get("/api/investor-view/weeks")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 6. GET /?week=YYYY-MM-DD — archived week view


def test_week_param_serves_archived(client):
    r1 = client.post("/api/investor-view/publish", headers=_admin())
    ref = r1.json()["ref"]

    client.post("/api/investor-view/publish", headers=_admin())

    r = client.get(f"/?week={ref}", headers=_admin())
    assert r.status_code == 200
    assert "__INVESTOR_VIEW_PUBLISHED" in r.text


def test_week_param_nonexistent_404(client):
    r = client.get("/?week=1999-01-01", headers=_admin())
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 7. Denylist gate at publish


def test_publish_blocked_by_denylist(client):
    """If template HTML contains a denylist term, publish must be rejected."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "INSERT INTO inline_edits (edit_id, content, updated_by, updated_at) "
        "VALUES ('tile-1-body', 'We discussed with Aurica partners', 'rd', '2026-07-08T00:00:00Z')"
    )
    conn.commit()

    r = client.post("/api/investor-view/publish", headers=_admin())
    assert r.status_code == 409
    detail = r.json().get("detail", r.json())
    assert "hard_violations" in detail


# ---------------------------------------------------------------------------
# 8. Schema migration v2 → v3


def test_migration_v2_to_v3(tmp_path):
    """A v2 DB migrates to v3 and accepts investor_view kind."""
    import src.db as db_mod

    db_path = tmp_path / "migrate_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.executescript(
        """
        CREATE TABLE publications (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL CHECK(kind IN ('weekly_update','board_pack')),
          ref TEXT NOT NULL,
          title TEXT,
          status TEXT NOT NULL CHECK(status IN ('draft','approved','published','archived')),
          body TEXT NOT NULL DEFAULT '{}',
          created_at TEXT NOT NULL,
          approved_at TEXT,
          approved_by TEXT,
          published_at TEXT,
          version INTEGER NOT NULL DEFAULT 1
        );
        CREATE UNIQUE INDEX ux_pub_one_published_per_kind
          ON publications(kind) WHERE status = 'published';
        CREATE TABLE inline_edits (
          edit_id TEXT PRIMARY KEY,
          content TEXT NOT NULL,
          updated_by TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          at TEXT NOT NULL,
          actor TEXT NOT NULL,
          action TEXT NOT NULL,
          entity TEXT NOT NULL,
          before TEXT,
          after TEXT
        );
        CREATE TABLE users (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          initials TEXT,
          token_hash TEXT,
          role TEXT NOT NULL CHECK(role IN ('admin','investor'))
        );
        PRAGMA user_version = 2;
    """
    )
    conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, version) "
        "VALUES ('weekly_update', '2026-07-01', 'Test', 'draft', '{}', '2026-07-01T00:00:00Z', 1)"
    )
    conn.commit()
    conn.close()

    db_mod.close_conn()
    import os

    os.environ["INVESTOR_DB"] = str(db_path)
    try:
        migrated = db_mod.get_conn()

        v = migrated.execute("PRAGMA user_version").fetchone()[0]
        assert v == 3

        row = migrated.execute("SELECT * FROM publications WHERE id=1").fetchone()
        assert row["kind"] == "weekly_update"
        assert row["ref"] == "2026-07-01"

        migrated.execute(
            "INSERT INTO publications (kind, ref, status, body, created_at, version) "
            "VALUES ('investor_view', '2026-07-08', 'draft', '{}', '2026-07-08T00:00:00Z', 1)"
        )
        migrated.commit()

        with pytest.raises(sqlite3.IntegrityError):
            migrated.execute(
                "INSERT INTO publications (kind, ref, status, body, created_at, version) "
                "VALUES ('invalid_kind', 'x', 'draft', '{}', 'x', 1)"
            )
    finally:
        db_mod.close_conn()
        del os.environ["INVESTOR_DB"]


# ---------------------------------------------------------------------------
# 9. Published HTML structure


def test_published_html_has_frozen_edits_script(client):
    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "INSERT INTO inline_edits (edit_id, content, updated_by, updated_at) "
        "VALUES ('dec-1-title', 'Custom Decision', 'rd', '2026-07-08T00:00:00Z')"
    )
    conn.commit()

    client.post("/api/investor-view/publish", headers=_admin())

    r = client.get("/", headers=_investor())
    html = r.text
    assert "window.__INVESTOR_VIEW_PUBLISHED=true" in html
    assert '"dec-1-title"' in html
    assert "Custom Decision" in html


def test_draft_html_has_no_published_flag(client):
    """The draft page has the JS check string in shell-bottom but NOT the injected assignment."""
    r = client.get("/", headers=_admin())
    assert "__INVESTOR_VIEW_PUBLISHED=true" not in r.text


# ---------------------------------------------------------------------------
# 10. validate_body for investor_view kind


def test_gates_validate_body_investor_view_valid():
    from src.gates import validate_body

    body = {"html": "<html>test</html>", "inline_edits": {"a": "b"}}
    assert validate_body("investor_view", body) == []


def test_gates_validate_body_investor_view_missing_html():
    from src.gates import validate_body

    assert len(validate_body("investor_view", {"inline_edits": {}})) > 0


def test_gates_validate_body_investor_view_extra_keys():
    from src.gates import validate_body

    body = {"html": "<html/>", "inline_edits": {}, "secret": "data"}
    violations = validate_body("investor_view", body)
    assert any("secret" in v for v in violations)


def test_gates_validate_body_investor_view_no_edits_ok():
    from src.gates import validate_body

    body = {"html": "<html/>"}
    assert validate_body("investor_view", body) == []


# ---------------------------------------------------------------------------
# 11. Audit trail


def test_publish_creates_audit_entry(client):
    client.post("/api/investor-view/publish", headers=_admin())

    from src import db as db_mod

    conn = db_mod.get_conn()
    row = conn.execute(
        "SELECT * FROM audit_log WHERE action='publish_investor_view'"
    ).fetchone()
    assert row is not None
    assert row["actor"] == "rd"


def test_unpublish_creates_audit_entry(client):
    client.post("/api/investor-view/publish", headers=_admin())
    client.post("/api/investor-view/unpublish", headers=_admin())

    from src import db as db_mod

    conn = db_mod.get_conn()
    row = conn.execute(
        "SELECT * FROM audit_log WHERE action='unpublish_investor_view'"
    ).fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# 12. Existing weekly_update/board_pack endpoints unaffected


def test_existing_published_endpoint_still_works(client):
    r = client.get("/api/published?kind=weekly_update", headers=_investor())
    assert r.status_code == 200
    assert r.json() == {"empty": True}


def test_existing_assemble_endpoint_still_works(client):
    r = client.post("/api/assemble?kind=weekly_update", headers=_admin())
    assert r.status_code == 200
    assert r.json()["kind"] == "weekly_update"
