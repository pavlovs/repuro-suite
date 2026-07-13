"""Screen 1 — Portfolio View port (v1 golden reference over v2 DB).

Guards the v1 template/API contract: landing serves the v1 dashboard with
mode=portfolio, api/data refreshes it, api/update accepts exactly the
portfolio fields (stage changes write history), portfolio comments persist.
"""

import importlib
import shutil
import sys
from pathlib import Path

import pytest

DEALROOM = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(DEALROOM))

V2 = DEALROOM / "data" / "dealroom_v2.db"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("uip") / "dr.db"
    shutil.copy2(V2, tmp)
    mp.setenv("DEALROOM_V2_DB", str(tmp))
    mp.delenv("DEALROOM_TRUSTED_PROXY", raising=False)
    import v2.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    yield TestClient(server.app)
    mp.undo()


def test_landing_serves_v1_portfolio(client):
    page = client.get("/").text
    # v1 template markers — the approved view, not a reinterpretation
    assert "renderPortfolio" in page
    assert '"mode": "portfolio"' in page or '"mode":"portfolio"' in page
    assert "All financial figures in M€" in page  # unit note in footer, not cells
    # no builder meta-remarks as UI copy
    assert "deals-Registry" not in page
    assert "overrides)" not in page


def test_api_data_matches_v1_shape(client):
    data = client.get("/api/data").json()
    assert data["mode"] == "portfolio"
    assert data["deals"], "no deals in payload"
    d = data["deals"][0]
    for key in (
        "code_name",
        "deal_stage",
        "rev_m",
        "ebitda_m",
        "ebitda_pct",
        "employees",
        "ev_m",
        "multiple",
        "status_text",
        "description",
    ):
        assert key in d
    # cells get bare numbers — the payload must not pre-format units
    for deal in data["deals"]:
        for k in ("rev_m", "ebitda_m", "ev_m", "multiple"):
            assert deal[k] is None or isinstance(deal[k], (int, float))


def test_deal_link_placeholder(client):
    page = client.get("/", params={"deal": "Fox"}).text
    assert "Fox" in page
    assert "Back to portfolio" in page


def test_api_update_status_and_stage_history(client):
    code = client.get("/api/data").json()["deals"][0]["code_name"]
    r = client.post(
        "/api/update",
        json={"code_name": code, "field": "status_override", "value": "test note"},
    )
    assert r.status_code == 200
    assert any(
        d["status_text"] == "test note" for d in client.get("/api/data").json()["deals"]
    )

    r = client.post(
        "/api/update",
        json={"code_name": code, "field": "deal_stage", "value": "on_hold"},
    )
    assert r.status_code == 200
    events = client.get(f"/api/deal/{code}/timeline").json()
    assert any(
        e["kind"] == "stage" and "portfolio stage dropdown" in (e.get("detail") or "")
        for e in events
    )


def test_api_update_rejects_non_portfolio_fields(client):
    code = client.get("/api/data").json()["deals"][0]["code_name"]
    r = client.post(
        "/api/update",
        json={"code_name": code, "field": "seller_profile_notes", "value": "x"},
    )
    assert r.status_code == 400


def test_portfolio_comments_persist(client):
    r = client.post(
        "/api/portfolio-comments",
        json={"key": "portfolio_pipeline_comments", "value": "Panda: awaiting JA"},
    )
    assert r.status_code == 200
    data = client.get("/api/data").json()
    assert data["portfolio_pipeline_comments"] == "Panda: awaiting JA"
