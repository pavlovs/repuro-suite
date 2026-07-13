"""Screen 2 — Offer & Negotiation (v1 visual language over v2 DB).

Guards: owner-gating (403), empty-state without strategy, offer round ledger
with bucket columns (units in headers, bare de-DE numbers in cells), issue
list with their_position/prio, placeholder deep-link for owners only.
"""

import importlib
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

DEALROOM = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(DEALROOM))

V2 = DEALROOM / "data" / "dealroom_v2.db"


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("uineg") / "dr.db"
    shutil.copy2(V2, tmp)
    # seed a deterministic offer history onto Lion's strategy (id from DB)
    c = sqlite3.connect(tmp)
    sid = c.execute(
        "SELECT id FROM negotiation_strategies WHERE deal_domain='golmed.de' "
        "ORDER BY id LIMIT 1"
    ).fetchone()[0]
    c.execute(
        "INSERT INTO negotiation_offers (strategy_id, side, date, label, status,"
        " source_doc) VALUES (?,?,?,?,?,?)",
        (sid, "ours", "2026-06-16", "Angebot 16.06", "superseded", "Mail 16.06.2026"),
    )
    oid1 = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.executemany(
        "INSERT INTO negotiation_offer_terms (offer_id, term_key, value_num, unit)"
        " VALUES (?,?,?,?)",
        [
            (oid1, "purchase_price_upfront", 3425.0, "K€"),
            (oid1, "ev_total_max", 5100.0, "K€"),
        ],
    )
    c.execute(
        "INSERT INTO negotiation_offers (strategy_id, side, date, label, status,"
        " source_doc) VALUES (?,?,?,?,?,?)",
        (
            sid,
            "theirs",
            "2026-07-01",
            "Golland Gegenposition",
            "received",
            "Call 01.07",
        ),
    )
    oid2 = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    c.execute(
        "INSERT INTO negotiation_offer_terms (offer_id, term_key, value_num, unit)"
        " VALUES (?,?,?,?)",
        (oid2, "ev_total_max", 5600.0, "K€"),
    )
    c.execute(
        "UPDATE negotiation_positions SET their_position='150 K EUR fix', prio='high' "
        "WHERE id IN (SELECT id FROM negotiation_positions LIMIT 1)"
    )
    c.commit()
    c.close()
    return tmp


@pytest.fixture(scope="module")
def client(db_path):
    mp = pytest.MonkeyPatch()
    mp.setenv("DEALROOM_V2_DB", str(db_path))
    mp.delenv("DEALROOM_TRUSTED_PROXY", raising=False)
    import v2.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    yield TestClient(server.app)
    mp.undo()


def test_owner_gating(client):
    assert (
        client.get(
            "/deal/Lion/negotiation", headers={"X-Remote-User": "florian"}
        ).status_code
        == 403
    )
    assert client.get("/deal/Lion/negotiation").status_code == 200


def test_unknown_deal_404(client):
    assert client.get("/deal/Nessie/negotiation").status_code == 404


def test_lion_renders_ledger_and_sections(client):
    page = client.get("/deal/Lion/negotiation").text
    assert "Offer &amp; Negotiation" in page
    assert "Offer round ledger" in page
    assert "Negotiation issue list" in page
    # bucket columns: units in headers …
    assert "Sofort (K€)" in page
    assert "Gesamt max (K€)" in page
    # … bare de-DE numbers in ledger CELLS, never unit-suffixed (strategy
    # prose may legitimately carry units — only cells are guarded)
    assert '<td class="r">3.425</td>' in page
    assert '<td class="r">3.425 K€</td>' not in page
    # both sides ledgered with source citation
    assert "Angebot 16.06" in page
    assert "Golland Gegenposition" in page
    assert "Quelle: Mail 16.06.2026" in page
    # seller ask + gap from the theirs-event (5.600 vs our 5.100)
    assert "Seller ask" in page
    # rounds history present (Lion has 13+ rounds)
    assert "Round " in page


def test_issue_list_their_position_and_prio(client):
    page = client.get("/deal/Cat/negotiation").text
    assert "Their position" in page
    # Cat S3 positions exist (LOI-Text v7, Absicherung Erfolgszahlung)
    assert "LOI-Text v7" in page


def test_no_strategy_empty_state(client):
    page = client.get("/deal/Owl/negotiation").text
    assert "No negotiation strategy" in page


def test_negotiation_route_owner_only(client):
    # Entry point changed 13.07: ?deal= serves the full deal workspace, so the
    # owner-only guarantee is asserted at the route itself.
    assert client.get("/deal/Lion/negotiation").status_code == 200
    assert (
        client.get(
            "/deal/Lion/negotiation", headers={"X-Remote-User": "florian"}
        ).status_code
        == 403
    )
