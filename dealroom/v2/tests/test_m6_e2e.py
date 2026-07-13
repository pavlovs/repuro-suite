"""M6 e2e: scan → push → fresh → UI, against a temp DB copy.

Chains the real pipeline: collect artifacts from the live Fox folder
(read-only), push through the API, assert the freshness engine reacts and the
UI renders the result. Owner-gating asserted end-to-end.
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
    tmp = tmp_path_factory.mktemp("e2e") / "dealroom_v2_e2e.db"
    shutil.copy2(V2, tmp)
    mp.setenv("DEALROOM_V2_DB", str(tmp))
    mp.delenv("DEALROOM_TRUSTED_PROXY", raising=False)
    import v2.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    yield TestClient(server.app)
    mp.undo()


def test_e2e_scan_push_fresh_ui(client):
    from v2.scanner import DEFAULT_TARGETS_ROOT, collect_artifacts

    fox = DEFAULT_TARGETS_ROOT / "250702_Com2Med (Fox)"
    if not fox.exists():
        pytest.skip("Fox deal folder not available")

    # scan (read-only) → push
    artifacts = collect_artifacts(fox)
    assert len(artifacts) > 200
    assert not any("backup" in a["file_name"].lower() for a in artifacts)
    r = client.post(
        "/api/push/artifacts", json={"code_name": "Fox", "artifacts": artifacts}
    )
    assert r.status_code == 200

    # freshness engine runs against the pushed registry (whether Fox carries
    # flags depends on live data state — a fresh model extraction clears
    # extraction_stale, so no specific flag is asserted here)
    fresh = client.get("/api/fresh").json()
    assert "deals" in fresh and "computed_at" in fresh

    # landing (Screen 1: ported v1 Portfolio View) renders the deal
    page = client.get("/").text
    assert "Live Deal Portfolio" in page
    assert '"Fox"' in page  # deal present in DATA payload

    # attention API surfaces Fox in a group (which group depends on live
    # freshness state — a model refresh clears extraction_stale)
    attention = client.get("/api/attention").json()
    assert any(
        e["code_name"] == "Fox" for group in attention["groups"].values() for e in group
    )


def test_e2e_dataroom_delta_flag(client):
    base = {
        "code_name": "Mouse",
        "sections": [
            {
                "section": "04",
                "section_name": "Finanzen",
                "files": [{"name": "susa_2025.xlsx", "mtime": "a"}],
                "newest_file_date": "2026-07-01",
                "newest_file_name": "susa_2025.xlsx",
            },
        ],
    }
    assert client.post("/api/push/dataroom-scan", json=base).status_code == 200
    base["sections"][0]["files"].append({"name": "ja_2025.pdf", "mtime": "b"})
    base["sections"][0]["newest_file_date"] = "2026-07-10"
    assert client.post("/api/push/dataroom-scan", json=base).status_code == 200

    fresh = client.get("/api/fresh").json()
    mouse = next((d for d in fresh["deals"] if d["deal"] == "Mouse"), None)
    assert mouse and any(f["rule"] == "dataroom_delta" for f in mouse["flags"])


@pytest.mark.skip(
    reason="owner-gated surfaces unregistered pending UI rebuild "
    "(13.07 rejection) — re-enable with the negotiation screen"
)
def test_e2e_owner_gating(client):
    headers = {"X-Remote-User": "florian"}
    assert client.get("/deal/Lion/negotiation", headers=headers).status_code == 403
    assert client.get("/stakeholders", headers=headers).status_code == 403
    assert client.get("/deal/Lion", headers=headers).status_code == 200
    # roman (default) passes
    assert client.get("/stakeholders").status_code == 200


def test_e2e_stage_write_shows_in_timeline(client):
    r = client.post(
        "/api/deal/Panda/stage",
        json={"to_stage": "dead", "evidence": "e2e: kein Kontakt seit April"},
    )
    assert r.status_code == 200
    events = client.get("/api/deal/Panda/timeline").json()
    assert any(
        e["kind"] == "stage"
        and "e2e: kein Kontakt seit April" in (e.get("detail") or "")
        for e in events
    )
