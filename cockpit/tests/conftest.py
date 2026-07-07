import hashlib
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src import db

RD_TOKEN = "test-token-rd"
AGENT_TOKEN = "test-token-agent"


def make_fixture_dealroom(path, deals=None):
    """Minimal dealroom.db lookalike (only the columns the sync reads)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS deals (id TEXT, code_name TEXT, deal_stage TEXT, status_note TEXT)"
    )
    for code, stage, note in (
        deals
        if deals is not None
        else [
            ("Octopus", "dead", None),
            ("Fox", "loi_signed", "DD running"),
            ("Cat", "indicative_offer", "awaiting seller"),
        ]
    ):
        conn.execute(
            "INSERT INTO deals (code_name, deal_stage, status_note) VALUES (?,?,?)",
            (code, stage, note),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def cockpit_db(tmp_path, monkeypatch):
    """Fresh cockpit DB + fixture dealroom DB + fixed today + two principals."""
    monkeypatch.setenv("COCKPIT_DB", str(tmp_path / "cockpit.db"))
    dealroom = tmp_path / "dealroom.db"
    make_fixture_dealroom(dealroom)
    monkeypatch.setenv("COCKPIT_DEALROOM_DB", str(dealroom))
    monkeypatch.setenv("COCKPIT_TODAY", "2026-06-11")
    monkeypatch.delenv("COCKPIT_SYNC_INTERVAL", raising=False)
    db.close_conn()
    conn = db.get_conn()
    for pid, role, token, initials, represents in (
        ("rd", "human", RD_TOKEN, "RD", None),
        ("rc-agent", "agent", AGENT_TOKEN, "RC", "rd"),
    ):
        conn.execute(
            "INSERT INTO users (id, name, role, token_hash, initials, represents) "
            "VALUES (?,?,?,?,?,?)",
            (
                pid,
                pid,
                role,
                hashlib.sha256(token.encode()).hexdigest(),
                initials,
                represents,
            ),
        )
    # v13: add rd to the 'md' team (is_admin=True) — mirrors migration backfill
    conn.execute(
        "INSERT OR IGNORE INTO team_members (team_id, user_id) VALUES (?,?)",
        ("md", "rd"),
    )
    conn.commit()
    yield conn
    db.close_conn()


@pytest.fixture()
def client(cockpit_db):
    from fastapi.testclient import TestClient

    from src.api import app

    with TestClient(app) as c:
        c.cockpit_conn = cockpit_db
        yield c


def auth(token=RD_TOKEN):
    return {"Authorization": f"Bearer {token}"}
