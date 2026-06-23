"""M1 acceptance tests — spec §8.
Covers: auth gates, published-only view, admin list, read-only DB guard, unknown principal.
"""

import hashlib
import json
import os
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# fixtures


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Point INVESTOR_DB at a fresh temp file and reset the singleton for every test."""
    db_path = tmp_path / "test_investor.db"
    monkeypatch.setenv("INVESTOR_DB", str(db_path))

    # Reset singleton so get_conn() picks up the new env var
    import src.db as db_mod

    db_mod.close_conn()

    yield str(db_path)

    db_mod.close_conn()


@pytest.fixture()
def seeded_client(isolated_db):
    """TestClient with a fully initialised and seeded DB (users + publications)."""
    from src import db as db_mod
    from src.api import app

    conn = db_mod.get_conn()

    # Insert users
    users = [
        ("rd", "Roman", "RD", "admin"),
        ("ff", "Florian", "FF", "admin"),
        ("strada", "Strada", "ST", "investor"),
    ]
    for uid, name, initials, role in users:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
            (uid, name, initials, role),
        )

    now = db_mod.now_iso()

    # Published weekly_update
    weekly_body = json.dumps(
        {
            "pipeline": {"funnel": {"items": [{"codename": "EAGLE"}]}},
            "live_deals": [],
            "project_update": {},
            "stamps": {},
        }
    )
    conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, published_at, version) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "weekly_update",
            "2026-06-16",
            "Weekly Update",
            "published",
            weekly_body,
            now,
            now,
            1,
        ),
    )

    # Published board_pack
    board_body = json.dumps(
        {
            "meeting": {"date": "2026-06-30"},
            "agenda": [],
            "kpis": [],
            "decisions": [],
            "pre_read": [],
            "minutes": "",
            "stamps": {},
        }
    )
    conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, published_at, version) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "board_pack",
            "2026-06-30",
            "Board Pack",
            "published",
            board_body,
            now,
            now,
            1,
        ),
    )

    # Draft weekly_update (admin must see it; investor must NOT)
    draft_body = json.dumps(
        {"pipeline": {}, "live_deals": [], "project_update": {}, "stamps": {}}
    )
    conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, version) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            "weekly_update",
            "2026-06-23",
            "Weekly Update DRAFT",
            "draft",
            draft_body,
            now,
            1,
        ),
    )

    conn.commit()

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. investor → admin endpoints → 403


def test_investor_cannot_list_publications(seeded_client):
    r = seeded_client.get("/api/publications", headers={"X-Remote-User": "investor"})
    assert r.status_code == 403


def test_investor_cannot_get_publication_by_id(seeded_client):
    r = seeded_client.get("/api/publication/1", headers={"X-Remote-User": "investor"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 2. investor → /api/published returns published row; draft kind → empty; never draft


def test_investor_gets_published_weekly_update(seeded_client):
    r = seeded_client.get(
        "/api/published?kind=weekly_update", headers={"X-Remote-User": "investor"}
    )
    assert r.status_code == 200
    data = r.json()
    assert "empty" not in data
    assert data["kind"] == "weekly_update"
    assert "body" in data


def test_investor_gets_published_board_pack(seeded_client):
    r = seeded_client.get(
        "/api/published?kind=board_pack", headers={"X-Remote-User": "investor"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["kind"] == "board_pack"
    assert "body" in data


# ---------------------------------------------------------------------------
# 2b. investor payload is allowlisted — no internal metadata leaks (Codex blocker #1)

_LEAK_FIELDS = ("id", "status", "created_at", "approved_at", "approved_by", "version")


def test_investor_payload_leaks_no_metadata(seeded_client):
    """The investor must never receive id/status/approved_by/version/timestamps."""
    for kind in ("weekly_update", "board_pack"):
        r = seeded_client.get(
            f"/api/published?kind={kind}", headers={"X-Remote-User": "investor"}
        )
        data = r.json()
        for f in _LEAK_FIELDS:
            assert f not in data, f"leaked field {f!r} in investor payload for {kind}"
        assert set(data.keys()) <= {"kind", "ref", "title", "published_at", "body"}


def test_investor_body_matches_seeded_fixture(seeded_client):
    """The body returned is the actual seeded content, not a placeholder."""
    r = seeded_client.get(
        "/api/published?kind=weekly_update", headers={"X-Remote-User": "investor"}
    )
    payload = r.json()
    assert payload["kind"] == "weekly_update"
    assert payload["ref"] == "2026-06-16"
    body = payload["body"]
    assert body["pipeline"]["funnel"]["items"][0]["codename"] == "EAGLE"
    # body is the seeded structure, fully round-tripped (not truncated/placeholder)
    assert set(body.keys()) == {"pipeline", "live_deals", "project_update", "stamps"}

    # board pack fixture round-trips too
    rb = seeded_client.get(
        "/api/published?kind=board_pack", headers={"X-Remote-User": "investor"}
    )
    bbody = rb.json()["body"]
    assert bbody["meeting"]["date"] == "2026-06-30"


def test_investor_cannot_see_approved_row(seeded_client):
    """An 'approved' (not yet published) row is invisible to the investor."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    # Move the published weekly_update to 'approved' so none is published
    conn.execute(
        "UPDATE publications SET status='approved' WHERE kind='weekly_update' AND status='published'"
    )
    conn.commit()
    r = seeded_client.get(
        "/api/published?kind=weekly_update", headers={"X-Remote-User": "investor"}
    )
    assert r.json() == {"empty": True}


def test_one_published_per_kind_enforced(seeded_client):
    """Partial unique index: a second 'published' row of the same kind must be rejected."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO publications (kind, ref, title, status, body, created_at, published_at, version) "
            "VALUES ('weekly_update','2026-06-09','dup','published','{}','x','x',1)"
        )


def test_corrupt_published_body_fails_loud(seeded_client):
    """A corrupt body JSON must raise (500), not silently return an empty body."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "UPDATE publications SET body='{not valid json' WHERE kind='board_pack' AND status='published'"
    )
    conn.commit()
    r = seeded_client.get(
        "/api/published?kind=board_pack", headers={"X-Remote-User": "investor"}
    )
    assert r.status_code == 500
    # The error must NOT leak internal metadata (e.g. the row id) to the investor.
    detail = str(r.json().get("detail", ""))
    assert "id=" not in detail
    assert all(ch not in detail for ch in "0123456789"), (
        f"numeric id may have leaked: {detail!r}"
    )


def test_open_readonly_missing_path_raises(tmp_path):
    """A wrong/missing path must raise FileNotFoundError, never silently create an empty DB."""
    from src.db import open_readonly

    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(FileNotFoundError):
        open_readonly(str(missing))
    assert not missing.exists(), "open_readonly must not create the file"


def test_open_readonly_path_with_spaces_is_readonly(tmp_path):
    """OneDrive-style paths contain spaces; the as_uri() URI must still open read-only."""
    import src.db as db_mod

    spaced_dir = tmp_path / "Kamu Kapital Dokumente"
    spaced_dir.mkdir()
    db_path = spaced_dir / "ro spaced.db"

    db_mod.close_conn()
    old = os.environ.get("INVESTOR_DB")
    os.environ["INVESTOR_DB"] = str(db_path)
    db_mod.get_conn()  # create + init at the spaced path
    db_mod.close_conn()
    if old is not None:
        os.environ["INVESTOR_DB"] = old
    else:
        del os.environ["INVESTOR_DB"]

    ro_conn = db_mod.open_readonly(str(db_path))
    # Reads work...
    assert ro_conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 0
    # ...writes do not.
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute(
            "INSERT INTO publications (kind, ref, status, body, created_at, version) "
            "VALUES ('weekly_update','x','draft','{}','2026-01-01T00:00:00Z',1)"
        )


def test_investor_gets_empty_when_no_published_row(seeded_client):
    """There is no published row for board_pack kind = 'weekly_update' with ref 2026-06-23
    (that one is a draft). Confirm /api/published never leaks it."""
    from src import db as db_mod

    # Archive the existing published weekly_update so none is published
    conn = db_mod.get_conn()
    conn.execute(
        "UPDATE publications SET status='archived' WHERE kind='weekly_update' AND status='published'"
    )
    conn.commit()

    r = seeded_client.get(
        "/api/published?kind=weekly_update", headers={"X-Remote-User": "investor"}
    )
    assert r.status_code == 200
    data = r.json()
    assert data == {"empty": True}


def test_published_endpoint_never_returns_draft(seeded_client):
    """Even if a draft exists, /api/published must not return it."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    # Archive published so only draft remains
    conn.execute(
        "UPDATE publications SET status='archived' WHERE kind='weekly_update' AND status='published'"
    )
    conn.commit()

    r = seeded_client.get(
        "/api/published?kind=weekly_update", headers={"X-Remote-User": "investor"}
    )
    data = r.json()
    assert data.get("status") != "draft"
    assert data == {"empty": True}


# ---------------------------------------------------------------------------
# 3. admin → sees list including drafts


def test_admin_can_list_publications(seeded_client):
    r = seeded_client.get("/api/publications", headers={"X-Remote-User": "roman"})
    assert r.status_code == 200
    pubs = r.json()["publications"]
    statuses = {p["status"] for p in pubs}
    assert "draft" in statuses, "admin list must include drafts"
    assert len(pubs) >= 3


def test_admin_can_get_publication_by_id(seeded_client):
    r = seeded_client.get("/api/publication/1", headers={"X-Remote-User": "roman"})
    assert r.status_code == 200
    assert "id" in r.json()


# ---------------------------------------------------------------------------
# 4. open_readonly raises on write attempt


def test_open_readonly_raises_on_write(tmp_path):
    """open_readonly() must prevent writes — confirms mode=ro URI is enforced."""
    from src.db import open_readonly
    import src.db as db_mod

    # Bootstrap a real DB at tmp_path so the file exists
    db_path = tmp_path / "ro_test.db"
    db_mod.close_conn()
    old_env = os.environ.get("INVESTOR_DB")
    os.environ["INVESTOR_DB"] = str(db_path)
    db_mod.get_conn()  # creates + initialises
    db_mod.close_conn()
    if old_env is not None:
        os.environ["INVESTOR_DB"] = old_env
    else:
        del os.environ["INVESTOR_DB"]

    ro_conn = open_readonly(str(db_path))
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute(
            "INSERT INTO publications (kind, ref, status, body, created_at, version) "
            "VALUES ('weekly_update','x','draft','{}','2026-01-01T00:00:00Z',1)"
        )


# ---------------------------------------------------------------------------
# 5. unknown / no principal → 401


def test_no_principal_returns_401(seeded_client):
    r = seeded_client.get("/api/publications")
    assert r.status_code == 401


def test_unknown_bearer_returns_401(seeded_client):
    r = seeded_client.get(
        "/api/publications", headers={"Authorization": "Bearer notarealtoken"}
    )
    assert r.status_code == 401


def test_unknown_x_remote_user_falls_through_to_401(seeded_client):
    """X-Remote-User with an unknown value (not in _CADDY_USER_MAP) → 401."""
    r = seeded_client.get("/api/publications", headers={"X-Remote-User": "hacker"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Bearer token path (local dev fallback)


def test_bearer_token_auth_admin(seeded_client):
    """Admin can authenticate via Bearer token (local dev path)."""
    from src import db as db_mod

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = db_mod.get_conn()
    conn.execute("UPDATE users SET token_hash=? WHERE id='rd'", (token_hash,))
    conn.commit()

    r = seeded_client.get(
        "/api/publications", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200


def test_bearer_token_auth_investor(seeded_client):
    """Investor authenticating via Bearer token sees published content."""
    from src import db as db_mod

    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = db_mod.get_conn()
    conn.execute("UPDATE users SET token_hash=? WHERE id='strada'", (token_hash,))
    conn.commit()

    r = seeded_client.get(
        "/api/published?kind=weekly_update",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "weekly_update"
