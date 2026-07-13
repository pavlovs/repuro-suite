"""M7 suite-tie tests: Cockpit execution read + Investor visibility, wired
into the deal page. Degrades cleanly when cockpit.db is absent."""

import importlib
import shutil
import sys
from pathlib import Path

import pytest

DEALROOM = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(DEALROOM))

from v2 import suite  # noqa: E402

V2 = DEALROOM / "data" / "dealroom_v2.db"
COCKPIT = DEALROOM.parent / "cockpit" / "data" / "cockpit.db"


def test_investor_visibility_buckets():
    class Row(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    assert suite.investor_visibility(Row(deal_stage="due_diligence"))["mode"] == "named"
    assert suite.investor_visibility(Row(deal_stage="loi_signed"))["visible"]
    assert (
        suite.investor_visibility(Row(deal_stage="indicative_offer"))["mode"]
        == "anonymised"
    )
    dead = suite.investor_visibility(Row(deal_stage="dead"))
    assert dead["visible"] is False and dead["url"] is None
    # buckets must match boardroom's exactly (contract)
    assert suite.INVESTOR_LIVE_STAGES == {
        "loi_signed",
        "due_diligence",
        "contract_negotiation",
        "closed",
    }


@pytest.mark.skipif(not COCKPIT.exists(), reason="cockpit.db not available")
def test_cockpit_execution_fox():
    ex = suite.cockpit_execution("Fox")
    assert ex and ex["linked"]
    assert ex["deliverables_total"] >= 5
    assert any("CDD" in d["name"] or "DD" in d["name"] for d in ex["deliverables_open"])
    assert ex["url"].startswith("/cockpit")


def test_cockpit_execution_absent_degrades(monkeypatch):
    monkeypatch.setenv("DEALROOM_COCKPIT_DB", str(DEALROOM / "no" / "such.db"))
    # env points at a missing file → path resolver returns None → tie skipped
    assert suite.cockpit_execution("Fox") is None


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("m7") / "dr.db"
    shutil.copy2(V2, tmp)
    mp.setenv("DEALROOM_V2_DB", str(tmp))
    mp.delenv("DEALROOM_TRUSTED_PROXY", raising=False)
    import v2.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    yield TestClient(server.app)
    mp.undo()


_DEAL_PAGE_SKIP = pytest.mark.skip(
    reason="deal page unregistered pending UI rebuild (13.07 rejection) — "
    "re-enable with Screen 2"
)


@_DEAL_PAGE_SKIP
@pytest.mark.skipif(not COCKPIT.exists(), reason="cockpit.db not available")
def test_deal_page_shows_execution_and_investor(client):
    page = client.get("/deal/Fox").text
    assert "Execution — Cockpit" in page
    assert "Im Cockpit" in page
    assert "Investor Room" in page  # due_diligence → named live deal


@_DEAL_PAGE_SKIP
def test_deal_page_investor_negative(client):
    # a dead deal must not claim investor visibility
    page = client.get("/deal/Octopus").text
    assert "Investor: —" in page or "Nicht im Investor" in page
