"""M1 tests: migration integrity, consumer contracts, API round-trips.

Read-only tests hit data/dealroom_v2.db directly; write tests run against a
temp copy so the sandbox DB stays clean.
"""

import importlib
import shutil
import sys
from pathlib import Path

import pytest

DEALROOM = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(DEALROOM))

from v2 import db as v2db  # noqa: E402

V1 = DEALROOM / "data" / "dealroom.db"
V2 = DEALROOM / "data" / "dealroom_v2.db"

KILLED_TABLES = [
    "deal_emails",
    "deal_meetings",
    "deal_granola",
    "deal_granola_v1_archive",
    "deal_actions",
    "deal_notes",
    "deal_manual_gates",
    "deal_contacts",
    "deal_data",
    "deal_data_v1_archive",
    "deal_scorecard_results",
]

CARRIED_SAME_COUNT = [
    "deal_financials",
    "deal_valuations",
    "deal_commercial",
    "deal_customers",
    "deal_products",
    "deal_invoices",
    "deal_backlog",
    "deal_model_params",
    "stakeholders",
    "stakeholder_links",
    "profile_claims",
    "negotiation_strategies",
    "negotiation_rounds",
    "negotiation_round_reviews",
    "negotiation_lessons",
    "negotiation_predictions",
    "communication_trail",
]


@pytest.fixture(scope="module")
def v2conn():
    conn = v2db.open_readonly(V2)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def v1conn():
    conn = v2db.open_readonly(V1)
    yield conn
    conn.close()


# ------------------------------------------------------------- migration ----


def test_v2_db_exists():
    assert V2.exists(), "run python -m v2.migrate_v1 first"


def test_killed_tables_absent(v2conn):
    tables = {
        r[0]
        for r in v2conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for t in KILLED_TABLES:
        assert t not in tables, f"kill-list table {t} leaked into v2"


def test_archive_export_exists():
    f = DEALROOM / "data" / "archive" / "deal_data_v1_archive.json"
    assert f.exists() and f.stat().st_size > 10_000


def test_carried_row_counts(v1conn, v2conn):
    for t in CARRIED_SAME_COUNT:
        n1 = v1conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        n2 = v2conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        assert n1 == n2, f"{t}: v1={n1} v2={n2}"


def test_stage_corrections(v2conn):
    stages = {
        r[0]: r[1] for r in v2conn.execute("SELECT code_name, deal_stage FROM deals")
    }
    assert stages["Fox"] == "due_diligence"
    assert stages["Mantis"] == "due_diligence"
    assert stages["Lion"] == "indicative_offer"
    assert stages["Aqua"] == "indicative_offer"
    assert "Swordfish" not in stages
    # every correction carries evidence
    for code in ("Fox", "Mantis", "Lion", "Aqua"):
        row = v2conn.execute(
            "SELECT evidence FROM deal_stage_history WHERE code_name=? "
            "AND changed_by LIKE 'migration%' ORDER BY id DESC LIMIT 1",
            (code,),
        ).fetchone()
        assert row and len(row[0]) > 40, f"{code}: missing evidence"


def test_aqua_keeps_valuation_link(v2conn):
    row = v2conn.execute(
        "SELECT d.domain FROM deals d WHERE d.code_name='Aqua'"
    ).fetchone()
    assert row[0] == "aqua"
    n = v2conn.execute(
        "SELECT COUNT(*) FROM deal_valuations WHERE domain='aqua'"
    ).fetchone()[0]
    assert n >= 1


def test_domain_remap_applied(v2conn):
    for placeholder in ("cat", "wolf"):
        n = v2conn.execute(
            "SELECT COUNT(*) FROM deal_valuations WHERE domain=?", (placeholder,)
        ).fetchone()[0]
        assert n == 0, f"placeholder domain {placeholder!r} survived in valuations"


def test_terms_seeded_with_sources(v2conn):
    rows = v2conn.execute("SELECT * FROM deal_terms").fetchall()
    assert len(rows) >= 18
    for r in rows:
        assert r["source_doc"], f"term {r['code_name']}/{r['term_key']} has no source"
    status = {
        r["code_name"]: r["status"]
        for r in v2conn.execute(
            "SELECT code_name, status FROM deal_terms "
            "WHERE term_key IN ('ev_total_max','ev_indicative','offer_update')"
        )
    }
    assert status["Fox"] == "locked"
    assert status["Mantis"] == "locked"
    assert status["Cat"] == "agreed"
    assert status["Lion"] == "proposed"
    assert status["Aqua"] == "proposed"


def test_artifacts_registry(v2conn):
    n = v2conn.execute("SELECT COUNT(*) FROM deal_artifacts").fetchone()[0]
    assert n > 600
    # exactly one non-superseded head per (code, type, stem)-chain is enforced
    # indirectly: no two 'current' rows share the same file_path
    dup = v2conn.execute(
        "SELECT code_name, file_path, COUNT(*) c FROM deal_artifacts "
        "GROUP BY code_name, file_path HAVING c > 1"
    ).fetchall()
    assert not dup
    # version parsing worked on the standard convention
    versioned = v2conn.execute(
        "SELECT COUNT(*) FROM deal_artifacts WHERE version IS NOT NULL"
    ).fetchone()[0]
    assert versioned > 100


# ------------------------------------------------------ consumer contract ---


def test_cockpit_sync_contract(v2conn):
    rows = v2conn.execute(
        "SELECT code_name, deal_stage, status_note FROM deals"
    ).fetchall()
    assert len(rows) == 14
    assert all(r[0] and r[1] for r in rows)


def test_boardroom_funnel_contract(v2conn):
    rows = v2conn.execute(
        "SELECT code_name, deal_stage, sector, location, ebitda_m_override, "
        "strategic_fit FROM deals "
        "WHERE deal_stage IN ('valuation_rfi','indicative_offer')"
    ).fetchall()
    codes = {r[0] for r in rows}
    assert {"Cat", "Mouse", "Lion", "Aqua"} <= codes


def test_boardroom_live_deals_contract(v2conn):
    rows = v2conn.execute(
        "SELECT company_name, code_name, deal_stage, rev_m_override, "
        "ebitda_m_override, ev_m_override, multiple_override FROM deals "
        "WHERE deal_stage IN "
        "('loi_signed','due_diligence','contract_negotiation','closed')"
    ).fetchall()
    codes = {r[1] for r in rows}
    assert codes == {"Fox", "Mantis"}


# ------------------------------------------------------------------- API ----


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_module):
    tmp = tmp_path_factory.mktemp("dbcopy") / "dealroom_v2_test.db"
    shutil.copy2(V2, tmp)
    monkeypatch_module.setenv("DEALROOM_V2_DB", str(tmp))
    monkeypatch_module.delenv("DEALROOM_TRUSTED_PROXY", raising=False)
    import v2.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    return TestClient(server.app)


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_api_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["deals"] == 14 and body["sandbox"] is True


def test_api_attention_groups(client):
    r = client.get("/api/attention")
    assert r.status_code == 200
    body = r.json()
    active = sum(len(v) for v in body["groups"].values())
    parked = sum(len(v) for v in body["parked"].values())
    assert active + parked == 14
    assert parked >= 7  # dead + on_hold collapsed


def test_api_deal_answer(client):
    r = client.get("/api/deal/Fox")
    assert r.status_code == 200
    body = r.json()
    assert body["stage_label"] == "Due diligence"
    assert body["stage_evidence"]["evidence"]
    assert any(t["term_key"] == "ev_total_max" for t in body["terms"])
    assert body["next_milestone"]


def test_api_deal_404(client):
    assert client.get("/api/deal/Nope").status_code == 404


def test_api_timeline(client):
    r = client.get("/api/deal/Lion/timeline")
    assert r.status_code == 200
    events = r.json()
    kinds = {e["kind"] for e in events}
    assert "stage" in kinds and "round" in kinds


def test_write_stage_requires_evidence(client):
    r = client.post("/api/deal/Owl/stage", json={"to_stage": "dead"})
    assert r.status_code == 422


def test_write_stage_roundtrip(client):
    r = client.post(
        "/api/deal/Owl/stage",
        json={"to_stage": "dead", "evidence": "test: no response since April"},
    )
    assert r.status_code == 200
    hist = client.get("/api/deal/Owl/timeline").json()
    assert any("Dead" in e["title"] for e in hist if e["kind"] == "stage")


def test_write_term_supersedes(client):
    r1 = client.post(
        "/api/deal/Fox/term",
        json={
            "term_key": "test_term",
            "status": "proposed",
            "source_doc": "test-1",
            "value_num": 100,
            "unit": "K€",
        },
    )
    r2 = client.post(
        "/api/deal/Fox/term",
        json={
            "term_key": "test_term",
            "status": "agreed",
            "source_doc": "test-2",
            "value_num": 120,
            "unit": "K€",
        },
    )
    assert r1.status_code == r2.status_code == 200
    terms = client.get("/api/terms", params={"deal": "Fox"}).json()
    test_terms = [t for t in terms if t["term_key"] == "test_term"]
    assert len(test_terms) == 2
    by_status = {t["status"]: t for t in test_terms}
    assert by_status["superseded"]["superseded_by_id"] == by_status["agreed"]["id"]


def test_push_artifacts_and_chain(client):
    payload = {
        "code_name": "Fox",
        "artifacts": [
            {
                "file_path": "X:/test/260701_Fox_Databook_v1.xlsx",
                "file_name": "260701_Fox_Databook_v1.xlsx",
                "artifact_type": "databook",
                "version": 1,
                "file_date": "2026-07-01",
            },
            {
                "file_path": "X:/test/260709_Fox_Databook_v2.xlsx",
                "file_name": "260709_Fox_Databook_v2.xlsx",
                "artifact_type": "databook",
                "version": 2,
                "file_date": "2026-07-09",
            },
        ],
    }
    r = client.post("/api/push/artifacts", json=payload)
    assert r.status_code == 200
    answer = client.get("/api/deal/Fox").json()
    dbs = [a for a in answer["artifacts_current"] if a["artifact_type"] == "databook"]
    assert any(a["file_name"].endswith("_v2.xlsx") for a in dbs)
    assert not any(a["file_name"].endswith("_v1.xlsx") for a in dbs)


def test_push_dataroom_scan_delta(client):
    base = {
        "code_name": "Fox",
        "sections": [
            {
                "section": "04",
                "section_name": "Finanzen",
                "files": [{"name": "a.xlsx", "mtime": "1"}],
                "newest_file_date": "2026-07-01",
                "newest_file_name": "a.xlsx",
            },
        ],
    }
    r1 = client.post("/api/push/dataroom-scan", json=base)
    assert r1.status_code == 200
    base["sections"][0]["files"].append({"name": "b.xlsx", "mtime": "2"})
    r2 = client.post("/api/push/dataroom-scan", json=base)
    assert r2.json()["deltas"]["04"]["added"] == ["b.xlsx"]


def test_push_rfi_mirror(client):
    payload = {
        "code_name": "Fox",
        "questions": [
            {
                "question": "Kundenverträge Top 10?",
                "importance": "high",
                "status": "sent",
                "sent_at": "2026-06-20",
            },
            {
                "question": "OEM-Autorisierung Nachweis?",
                "importance": "high",
                "status": "open",
            },
        ],
    }
    r = client.post("/api/push/rfi", json=payload)
    assert r.status_code == 200 and r.json()["count"] == 2
