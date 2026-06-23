"""M2 acceptance tests — assemble.py + POST /api/assemble.

Tests run against the REAL read-only source DBs (dealroom/pipeline/cockpit).
investor.db is isolated via the existing isolated_db fixture pattern.
Foreign DBs are never written.
"""

import json

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Re-use the isolated_db fixture from test_auth (same pattern, local copy here
# so this file is self-contained and doesn't depend on import order).


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Point INVESTOR_DB at a fresh temp file; reset singleton for every test."""
    db_path = tmp_path / "test_investor.db"
    monkeypatch.setenv("INVESTOR_DB", str(db_path))

    import src.db as db_mod

    db_mod.close_conn()
    yield str(db_path)
    db_mod.close_conn()


@pytest.fixture()
def admin_client(isolated_db):
    """TestClient seeded with an admin user (roman/rd)."""
    from src import db as db_mod
    from src.api import app

    conn = db_mod.get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
        ("rd", "Roman", "RD", "admin"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
        ("strada", "Strada", "ST", "investor"),
    )
    conn.commit()

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. funnel — no company_name, only allowed pre-LOI stages


def test_funnel_no_company_name():
    """Funnel rows must never contain 'name' or 'company_name' keys."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    items = result["pipeline"]["funnel"]["items"]
    assert isinstance(items, list)
    for row in items:
        assert "name" not in row, f"'name' leaked in funnel row: {row}"
        assert "company_name" not in row, f"'company_name' leaked in funnel row: {row}"


def test_funnel_only_pre_loi_stages():
    """Every funnel item must be valuation_rfi or indicative_offer — never dead/on_hold/loi_signed+."""
    from src.assemble import _FUNNEL_STAGES, assemble_weekly_update

    result = assemble_weekly_update()
    items = result["pipeline"]["funnel"]["items"]
    forbidden = {
        "dead",
        "on_hold",
        "loi_signed",
        "due_diligence",
        "contract_negotiation",
        "closed",
    }
    for row in items:
        assert row["stage"] in _FUNNEL_STAGES, (
            f"unexpected stage in funnel: {row['stage']}"
        )
        assert row["stage"] not in forbidden, (
            f"forbidden stage in funnel: {row['stage']}"
        )


def test_funnel_row_fields():
    """Each funnel item has the expected anonymized fields."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    items = result["pipeline"]["funnel"]["items"]
    expected_keys = {
        "codename",
        "stage",
        "sector",
        "region",
        "size_band",
        "strategic_fit",
    }
    for row in items:
        assert set(row.keys()) == expected_keys, (
            f"unexpected funnel row shape: {row.keys()}"
        )


# ---------------------------------------------------------------------------
# 2. live_deals — only post-LOI, real names present


def test_live_deals_only_post_loi():
    """live_deals must only contain post-LOI stages."""
    from src.assemble import _LIVE_STAGES, assemble_weekly_update

    result = assemble_weekly_update()
    items = result["live_deals"]  # bare array per the read-view contract
    pre_loi = {"valuation_rfi", "indicative_offer", "dead", "on_hold"}
    for row in items:
        assert row["stage"] in _LIVE_STAGES, (
            f"pre-LOI stage in live_deals: {row['stage']}"
        )
        assert row["stage"] not in pre_loi


def test_live_deals_has_company_name():
    """live_deals items must include the real company name."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    items = result["live_deals"]  # bare array
    # If there are live deals, they must have 'name'
    for row in items:
        assert "name" in row, f"missing 'name' in live_deals row: {row}"


# ---------------------------------------------------------------------------
# 3. batches — exclusions correct, numbers match direct SQL


def test_batches_exclude_null_and_test():
    """Batch rows must exclude NULL briefaktion, 'testbatch', and any value containing 'TEST'."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    rows = result["pipeline"]["batches"]["rows"]
    for row in rows:
        ba = row["batch"]
        assert ba is not None, "NULL batch in output"
        assert ba != "testbatch", "'testbatch' must be excluded"
        assert "TEST" not in ba.upper(), f"TEST batch leaked: {ba}"


def test_batches_numeric_types():
    """sent/replies/meetings must be ints; conv_pct must be a number."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    rows = result["pipeline"]["batches"]["rows"]
    assert len(rows) > 0, (
        "Expected at least one batch row (BA1..BA8 exist in live data)"
    )
    for row in rows:
        assert isinstance(row["sent"], int), f"sent not int: {row}"
        assert isinstance(row["replies"], int), f"replies not int: {row}"
        assert isinstance(row["meetings"], int), f"meetings not int: {row}"
        assert isinstance(row["conv_pct"], (int, float)), f"conv_pct not numeric: {row}"


def test_batches_ba1_matches_direct_sql():
    """For BA1: verify assemble numbers match a direct SQL COUNT — proves correctness."""
    from src.assemble import _REPLY_STATUSES, assemble_weekly_update
    from src.sources import pipeline_db
    from src import db as db_mod

    # Direct SQL counts from the real pipeline DB
    pl_path = pipeline_db()
    pl_conn = db_mod.open_readonly(pl_path)
    try:
        direct_sent = pl_conn.execute(
            "SELECT COUNT(*) FROM company_records "
            "WHERE briefaktion='BA1' AND outreach_sent_at IS NOT NULL"
        ).fetchone()[0]

        # Build the reply IN clause dynamically to match assemble.py logic exactly
        placeholders = ",".join("?" * len(_REPLY_STATUSES))
        direct_replies = pl_conn.execute(
            f"SELECT COUNT(*) FROM company_records "
            f"WHERE briefaktion='BA1' AND outreach_status IN ({placeholders})",
            tuple(_REPLY_STATUSES),
        ).fetchone()[0]

        direct_meetings = pl_conn.execute(
            "SELECT COUNT(*) FROM company_records "
            "WHERE briefaktion='BA1' AND outreach_status='meeting'"
        ).fetchone()[0]
    finally:
        pl_conn.close()

    # Get assembled numbers
    result = assemble_weekly_update()
    ba1 = next(
        (r for r in result["pipeline"]["batches"]["rows"] if r["batch"] == "BA1"),
        None,
    )
    assert ba1 is not None, "BA1 missing from assembled batches"

    assert ba1["sent"] == direct_sent, (
        f"BA1 sent mismatch: assembled={ba1['sent']}, direct={direct_sent}"
    )
    assert ba1["replies"] == direct_replies, (
        f"BA1 replies mismatch: assembled={ba1['replies']}, direct={direct_replies}"
    )
    assert ba1["meetings"] == direct_meetings, (
        f"BA1 meetings mismatch: assembled={ba1['meetings']}, direct={direct_meetings}"
    )

    # Report the numbers (visible with pytest -s)
    print(
        f"\nBA1 verified: sent={ba1['sent']}, replies={ba1['replies']}, "
        f"meetings={ba1['meetings']}, conv_pct={ba1['conv_pct']}%"
    )


# ---------------------------------------------------------------------------
# 4. assemble functions never raise; cockpit tolerates NULL target_date


def test_assemble_weekly_update_does_not_raise():
    """Full weekly_update assembly on real data must not raise."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    assert isinstance(result, dict)
    assert "pipeline" in result
    assert "live_deals" in result
    assert "project_update" in result
    assert "stamps" in result


def test_assemble_board_pack_does_not_raise():
    """Full board_pack assembly on real data must not raise."""
    from src.assemble import assemble_board_pack

    result = assemble_board_pack()
    assert isinstance(result, dict)
    assert "kpis" in result
    assert len(result["kpis"]) == 4


def test_cockpit_null_target_date_tolerated():
    """Cockpit has deliverables with NULL target_date — milestones_next must skip them cleanly."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    next_items = result["project_update"]["milestones_next"]
    # All returned items must have a non-None target_date (NULLs were filtered by SQL)
    for item in next_items:
        assert item["target_date"] is not None, (
            f"NULL target_date leaked into milestones_next: {item}"
        )


def test_cockpit_done_milestones_empty():
    """Live cockpit has 0 done deliverables — milestones_done must be an empty list."""
    from src.assemble import assemble_weekly_update

    result = assemble_weekly_update()
    done = result["project_update"]["milestones_done"]
    assert done == [], f"Expected empty milestones_done, got: {done}"


# ---------------------------------------------------------------------------
# 5. POST /api/assemble auth gates + draft creation


def test_assemble_endpoint_investor_gets_403(admin_client):
    """Investor must not be able to trigger assembly — admin only."""
    r = admin_client.post(
        "/api/assemble?kind=weekly_update",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 403


def test_assemble_endpoint_admin_creates_draft_weekly_update(admin_client):
    """Admin POST /api/assemble?kind=weekly_update creates a draft row."""
    r = admin_client.post(
        "/api/assemble?kind=weekly_update",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["kind"] == "weekly_update"
    assert data["status"] == "draft"
    assert "id" in data
    pub_id = data["id"]

    # Verify the row is actually in the DB with status='draft' and not published
    from src import db as db_mod

    conn = db_mod.get_conn()
    row = conn.execute("SELECT * FROM publications WHERE id=?", (pub_id,)).fetchone()
    assert row is not None
    assert row["status"] == "draft"
    assert row["kind"] == "weekly_update"
    # Body must be valid JSON with expected shape
    body = json.loads(row["body"])
    assert "pipeline" in body
    assert "live_deals" in body


def test_assemble_endpoint_admin_creates_draft_board_pack(admin_client):
    """Admin POST /api/assemble?kind=board_pack creates a draft row."""
    r = admin_client.post(
        "/api/assemble?kind=board_pack",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["kind"] == "board_pack"
    assert data["status"] == "draft"

    from src import db as db_mod

    conn = db_mod.get_conn()
    row = conn.execute(
        "SELECT * FROM publications WHERE id=?", (data["id"],)
    ).fetchone()
    assert row["status"] == "draft"
    body = json.loads(row["body"])
    assert "kpis" in body
    assert len(body["kpis"]) == 4


def test_assemble_draft_not_visible_to_investor(admin_client):
    """A freshly assembled draft must not appear at /api/published for the investor."""
    # Assemble a draft
    admin_client.post(
        "/api/assemble?kind=weekly_update",
        headers={"X-Remote-User": "roman"},
    )
    # Investor should still see empty (no published row)
    r = admin_client.get(
        "/api/published?kind=weekly_update",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 200
    assert r.json() == {"empty": True}


def test_assemble_invalid_kind_returns_422(admin_client):
    """An unrecognised kind must return 422."""
    r = admin_client.post(
        "/api/assemble?kind=invalid",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 6. Shape contract — an assembled draft, once published, must match what the
#    M1 read view (app.jsx) consumes. This is the regression guard for the
#    generator/read-view shape divergence found in M2 review.


def test_assembled_weekly_body_matches_readview_contract(admin_client):
    """assemble → publish → investor read: body must use the exact keys app.jsx reads."""
    r = admin_client.post(
        "/api/assemble?kind=weekly_update", headers={"X-Remote-User": "roman"}
    )
    pub_id = r.json()["id"]

    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "UPDATE publications SET status='published', published_at=? WHERE id=?",
        (db_mod.now_iso(), pub_id),
    )
    conn.commit()

    body = admin_client.get(
        "/api/published?kind=weekly_update", headers={"X-Remote-User": "investor"}
    ).json()["body"]

    # Exact keys consumed by app.jsx UpdatesTab
    assert isinstance(body["pipeline"]["funnel"]["items"], list)
    assert isinstance(body["pipeline"]["batches"]["rows"], list)  # NOT 'items'
    assert isinstance(body["live_deals"], list)  # bare array, NOT {items:...}
    pu = body["project_update"]
    assert isinstance(pu["milestones_done"], list)
    assert isinstance(pu["milestones_next"], list)
    assert isinstance(pu["fundraising"], dict)  # object, NOT ""
    assert set(pu["fundraising"].keys()) == {
        "tax_structure",
        "sources_uses",
        "capital_plan",
    }

    # STRICT key sets — body is the investor allowlist; no extra raw DB field may ride along.
    live_contract = {
        "name",
        "codename",
        "stage",
        "rev_m",
        "ebitda_m",
        "ev_m",
        "multiple",
        "earnout",
        "dd_status",
        "close_target",
        "commentary",
    }
    for d in body["live_deals"]:
        assert set(d.keys()) == live_contract, (
            f"live_deal leaks extra keys: {set(d.keys()) - live_contract}"
        )
    for m in pu["milestones_next"]:
        assert set(m.keys()) == {"name", "target_date"}, f"next extra: {m.keys()}"
    for m in pu["milestones_done"]:
        assert set(m.keys()) == {"name", "date", "comment"}, f"done extra: {m.keys()}"
    batch_contract = {"batch", "sent", "replies", "meetings", "conv_pct"}
    for b in body["pipeline"]["batches"]["rows"]:
        assert set(b.keys()) == batch_contract, (
            f"batch row extra: {set(b.keys()) - batch_contract}"
        )


def test_assembled_board_body_matches_readview_contract(admin_client):
    """Board KPIs must use metric/value/prior keys (what BoardTab renders)."""
    r = admin_client.post(
        "/api/assemble?kind=board_pack", headers={"X-Remote-User": "roman"}
    )
    pub_id = r.json()["id"]

    from src import db as db_mod

    conn = db_mod.get_conn()
    conn.execute(
        "UPDATE publications SET status='published', published_at=? WHERE id=?",
        (db_mod.now_iso(), pub_id),
    )
    conn.commit()

    body = admin_client.get(
        "/api/published?kind=board_pack", headers={"X-Remote-User": "investor"}
    ).json()["body"]

    assert isinstance(body["meeting"].get("attendees"), list)
    for k in body["kpis"]:
        assert "metric" in k and "value" in k and "prior" in k
