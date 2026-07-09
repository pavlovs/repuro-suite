"""Calendar module tests — monkeypatched calendar_graph, no live Graph calls."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from tests.conftest import auth

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

FF_TOKEN = "test-token-ff"
VIEWER_TOKEN = "test-token-viewer"
AGENT_TOKEN_CAL = "test-token-agent-cal"


def _ff_auth():
    return {"Authorization": f"Bearer {FF_TOKEN}"}


def _viewer_auth():
    return {"Authorization": f"Bearer {VIEWER_TOKEN}"}


def _agent_auth():
    return {"Authorization": f"Bearer {AGENT_TOKEN_CAL}"}


def _fake_events(upns, start_iso, end_iso):
    """Deterministic stub: one event per UPN."""
    events = []
    for upn in upns:
        events.append(
            {
                "upn": upn,
                "subject": f"Meeting for {upn}",
                "start": start_iso[:10] + "T09:00:00",
                "end": start_iso[:10] + "T10:00:00",
                "all_day": False,
                "location": "Berlin",
                "show_as": "busy",
                "private": False,
                "online_url": None,
            }
        )
    return events


def _private_events(upns, start_iso, end_iso):
    events = []
    for upn in upns:
        events.append(
            {
                "upn": upn,
                "subject": "Secret meeting",
                "start": start_iso[:10] + "T14:00:00",
                "end": start_iso[:10] + "T15:00:00",
                "all_day": False,
                "location": "Home",
                "show_as": "busy",
                "private": True,
                "online_url": "https://teams.example.com/join/secret",
            }
        )
    return events


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cal_db(cockpit_db):
    """Extend base fixture: ff user in md team + calendar UPN; viewer user; agent."""
    cockpit_db.execute(
        "INSERT INTO users (id, name, initials, role, token_hash, login) "
        "VALUES (?,?,?,?,?,?)",
        (
            "ff",
            "Florian",
            "FF",
            "human",
            hashlib.sha256(FF_TOKEN.encode()).hexdigest(),
            "florian",
        ),
    )
    cockpit_db.execute(
        "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
        ("md", "ff"),
    )
    # Give rd a calendar UPN
    cockpit_db.execute(
        "UPDATE users SET calendar_upn=? WHERE id='rd'",
        ("roman@example.com",),
    )
    # Give ff a calendar UPN
    cockpit_db.execute(
        "UPDATE users SET calendar_upn=? WHERE id='ff'",
        ("florian@example.com",),
    )
    # Viewer: no team, no UPN
    cockpit_db.execute(
        "INSERT INTO users (id, name, initials, role, token_hash, login) "
        "VALUES (?,?,?,?,?,?)",
        (
            "viewer1",
            "Viewer One",
            "V1",
            "human",
            hashlib.sha256(VIEWER_TOKEN.encode()).hexdigest(),
            "viewer1",
        ),
    )
    # Agent
    cockpit_db.execute(
        "INSERT INTO users (id, name, initials, role, token_hash) VALUES (?,?,?,?,?)",
        (
            "cal-agent",
            "Cal Agent",
            "CA",
            "agent",
            hashlib.sha256(AGENT_TOKEN_CAL.encode()).hexdigest(),
        ),
    )
    cockpit_db.commit()
    return cockpit_db


@pytest.fixture()
def cal_client(cal_db):
    from fastapi.testclient import TestClient
    from src.api import app

    with TestClient(app) as c:
        c.cockpit_conn = cal_db
        yield c


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


def test_connect_saves_upn(cal_client, monkeypatch):
    monkeypatch.setattr(
        "src.calendar_graph.probe_upn",
        lambda upn: (True, "ok"),
    )
    r = cal_client.post(
        "/api/calendar/connect",
        json={"upn": "roman@example.com"},
        headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    row = cal_client.cockpit_conn.execute(
        "SELECT calendar_upn FROM users WHERE id='rd'"
    ).fetchone()
    assert row["calendar_upn"] == "roman@example.com"


def test_connect_unknown_upn_rejected(cal_client, monkeypatch):
    monkeypatch.setattr(
        "src.calendar_graph.probe_upn",
        lambda upn: (False, "unknown_upn"),
    )
    r = cal_client.post(
        "/api/calendar/connect",
        json={"upn": "nobody@example.com"},
        headers=auth(),
    )
    assert r.status_code == 422
    assert "unknown_upn" in r.text


def test_disconnect_clears_upn(cal_client, monkeypatch):
    monkeypatch.setattr(
        "src.calendar_graph.probe_upn",
        lambda upn: (True, "ok"),
    )
    # First connect
    cal_client.post(
        "/api/calendar/connect",
        json={"upn": "roman@example.com"},
        headers=auth(),
    )
    # Then disconnect (empty upn)
    r = cal_client.post(
        "/api/calendar/connect",
        json={"upn": ""},
        headers=auth(),
    )
    assert r.status_code == 200
    row = cal_client.cockpit_conn.execute(
        "SELECT calendar_upn FROM users WHERE id='rd'"
    ).fetchone()
    assert row["calendar_upn"] is None


def test_connect_not_configured_returns_503(cal_client, monkeypatch):
    monkeypatch.setattr(
        "src.calendar_graph.probe_upn",
        lambda upn: (False, "not_configured"),
    )
    r = cal_client.post(
        "/api/calendar/connect",
        json={"upn": "roman@example.com"},
        headers=auth(),
    )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# events: scope=me
# ---------------------------------------------------------------------------


def test_events_me_returns_own_events(cal_client, monkeypatch):
    monkeypatch.setenv("COCKPIT_CALENDAR_FAKE", "1")
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    r = cal_client.get(
        "/api/calendar/events?scope=me&start=2026-07-09&days=1",
        headers=auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["events"]) == 1
    assert body["events"][0]["user"]["id"] == "rd"
    assert body["events"][0]["subject"] == "Meeting for roman@example.com"


def test_events_me_user_without_upn_returns_empty(cal_client, monkeypatch):
    """FF user has UPN set; test that viewer (no UPN) gets empty events."""
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    # Clear rd UPN temporarily for this test
    cal_client.cockpit_conn.execute("UPDATE users SET calendar_upn=NULL WHERE id='rd'")
    cal_client.cockpit_conn.commit()
    r = cal_client.get(
        "/api/calendar/events?scope=me&start=2026-07-09&days=1",
        headers=auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []


# ---------------------------------------------------------------------------
# events: scope=team
# ---------------------------------------------------------------------------


def test_events_team_includes_shared_team_members(cal_client, monkeypatch):
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    r = cal_client.get(
        "/api/calendar/events?scope=team&start=2026-07-09&days=1",
        headers=auth(),
    )
    assert r.status_code == 200
    body = r.json()
    user_ids = {e["user"]["id"] for e in body["events"]}
    # rd and ff both in md team and both have UPNs
    assert "rd" in user_ids
    assert "ff" in user_ids


def test_events_team_excludes_users_without_upn(cal_client, monkeypatch):
    """viewer1 has no UPN — should not appear in team events."""
    # Add viewer1 to md team
    cal_client.cockpit_conn.execute(
        "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES ('md','viewer1')"
    )
    cal_client.cockpit_conn.commit()
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    r = cal_client.get(
        "/api/calendar/events?scope=team&start=2026-07-09&days=1",
        headers=auth(),
    )
    assert r.status_code == 200
    body = r.json()
    user_ids = {e["user"]["id"] for e in body["events"]}
    assert "viewer1" not in user_ids


# ---------------------------------------------------------------------------
# privacy masking
# ---------------------------------------------------------------------------


def test_private_events_masked_for_non_self(cal_client, monkeypatch):
    """rd fetches team scope — ff's private event must be masked."""
    monkeypatch.setattr("src.calendar_graph.fetch_events", _private_events)
    r = cal_client.get(
        "/api/calendar/events?scope=team&start=2026-07-09&days=1",
        headers=auth(),
    )
    assert r.status_code == 200
    body = r.json()
    ff_events = [e for e in body["events"] if e["user"]["id"] == "ff"]
    assert len(ff_events) >= 1
    for ev in ff_events:
        assert ev["subject"] == "Private"
        assert ev["location"] == ""
        assert ev["online_url"] is None


def test_own_private_events_not_masked(cal_client, monkeypatch):
    """rd fetching scope=me sees own private events unmasked."""
    monkeypatch.setattr("src.calendar_graph.fetch_events", _private_events)
    r = cal_client.get(
        "/api/calendar/events?scope=me&start=2026-07-09&days=1",
        headers=auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["subject"] == "Secret meeting"
    assert body["events"][0]["location"] == "Home"
    assert body["events"][0]["online_url"] is not None


# ---------------------------------------------------------------------------
# module gating
# ---------------------------------------------------------------------------


def test_agent_cannot_access_calendar(cal_client):
    r = cal_client.get(
        "/api/calendar/events",
        headers=_agent_auth(),
    )
    assert r.status_code == 403
    assert "agents" in r.text.lower() or "calendar" in r.text.lower()


def test_viewer_without_calendar_module_gets_403(cal_client, monkeypatch):
    """viewer1 has no team membership — calendar not in modules → 403."""
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    r = cal_client.get(
        "/api/calendar/events",
        headers=_viewer_auth(),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# not_configured / consent_missing status passthrough
# ---------------------------------------------------------------------------


def test_not_configured_status_when_env_missing(cal_client, monkeypatch):
    """When graph env vars absent and not fake mode, status=not_configured."""
    monkeypatch.setattr("src.calendar_graph.fetch_events", lambda *a: [])
    monkeypatch.delenv("COCKPIT_GRAPH_TENANT", raising=False)
    monkeypatch.delenv("COCKPIT_GRAPH_CLIENT_ID", raising=False)
    monkeypatch.delenv("COCKPIT_CALENDAR_FAKE", raising=False)
    r = cal_client.get(
        "/api/calendar/events?scope=me",
        headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "not_configured"


def test_ok_status_in_fake_mode(cal_client, monkeypatch):
    monkeypatch.setenv("COCKPIT_CALENDAR_FAKE", "1")
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    r = cal_client.get(
        "/api/calendar/events?scope=me",
        headers=auth(),
    )
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# real Graph path (mocked httpx) — every other test runs fake/monkeypatched
# mode, so a broken import or error path in calendar_graph is invisible to them
# ---------------------------------------------------------------------------


def test_real_graph_path_url_and_error_handling(monkeypatch):
    """Guards the urllib `quote` import (a formatter once stripped it as unused —
    NameError on every non-fake Graph call, caught only by fresh-context review)
    and the httpx error nets (ConnectError must not 500 to the browser)."""
    import httpx

    import src.calendar_graph as cg

    monkeypatch.delenv("COCKPIT_CALENDAR_FAKE", raising=False)
    monkeypatch.setenv("COCKPIT_GRAPH_TENANT", "t")
    monkeypatch.setenv("COCKPIT_GRAPH_CLIENT_ID", "c")
    monkeypatch.setenv("COCKPIT_GRAPH_CLIENT_SECRET", "s")
    monkeypatch.setattr(cg, "_get_token", lambda: "tok")

    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"value": []}

    monkeypatch.setattr(
        cg.httpx,
        "get",
        lambda url, headers=None, timeout=None: seen.update(url=url) or _Resp(),
    )
    assert cg.probe_upn("quote.test@example.com") == (True, "ok")
    assert "/users/quote.test@example.com/calendarView" in seen["url"]
    assert (
        cg._fetch_upn_events(
            "quote.test@example.com",
            "2099-01-01T00:00:00",
            "2099-01-08T00:00:00",
            "tok",
        )
        == []
    )

    def _boom(url, headers=None, timeout=None):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(cg.httpx, "get", _boom)
    assert cg.probe_upn("quote.test2@example.com") == (False, "error_network")
    assert (
        cg._fetch_upn_events(
            "quote.test2@example.com",
            "2099-02-01T00:00:00",
            "2099-02-08T00:00:00",
            "tok",
        )
        == []
    )


def test_events_rejects_datetime_start(cal_client, monkeypatch):
    """start must be a bare date — a datetime would corrupt start_iso for Graph."""
    monkeypatch.setenv("COCKPIT_CALENDAR_FAKE", "1")
    monkeypatch.setattr("src.calendar_graph.fetch_events", _fake_events)
    r = cal_client.get(
        "/api/calendar/events?scope=me&start=2026-07-09T12:00:00",
        headers=auth(),
    )
    assert r.status_code == 422
