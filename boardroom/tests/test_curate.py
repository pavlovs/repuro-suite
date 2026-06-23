"""M3 acceptance tests — curation + publish state machine.

Covers: whoami, PATCH, diff, approve (gates), publish/archive, unpublish, full lifecycle.
"""

import json

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_auth / test_assemble)


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
    """TestClient with admin (roman/rd) and investor (strada) users seeded."""
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


# Minimal valid weekly_update body (matches assemble.py contract)
_VALID_WEEKLY_BODY = {
    "pipeline": {"funnel": {"items": []}, "batches": {"rows": []}},
    "live_deals": [],
    "project_update": {
        "milestones_done": [],
        "milestones_next": [],
        "narrative": "",
        "fundraising": {"tax_structure": "", "sources_uses": [], "capital_plan": ""},
    },
    "stamps": {
        "pipeline.funnel": {"source": "dealroom.db", "as_of": "2026-06-20T10:00:00Z"}
    },
}

_CHECKLIST_ALL_TRUE = {
    "no_pre_loi_names": True,
    "no_other_investors": True,
    "figures_stamped": True,
}


def _seed_draft(client, kind="weekly_update", body=None):
    """Insert a draft publication directly (avoids real DB assembly)."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    now = db_mod.now_iso()
    b = body if body is not None else _VALID_WEEKLY_BODY
    cur = conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, version) "
        "VALUES (?,?,?,?,?,?,?)",
        (kind, "2026-06-20", f"{kind} draft", "draft", json.dumps(b), now, 1),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# 1. whoami


def test_whoami_admin(admin_client):
    r = admin_client.get("/api/whoami", headers={"X-Remote-User": "roman"})
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "rd"
    assert data["role"] == "admin"


def test_whoami_investor(admin_client):
    r = admin_client.get("/api/whoami", headers={"X-Remote-User": "investor"})
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "strada"
    assert data["role"] == "investor"


# ---------------------------------------------------------------------------
# 2. Investor → 403 on all curation endpoints


def test_investor_cannot_patch(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"title": "Hacked"},
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 403


def test_investor_cannot_approve(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 403


def test_investor_cannot_publish(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/publish",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 403


def test_investor_cannot_diff(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.get(
        f"/api/publication/{pub_id}/diff",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 403


def test_investor_cannot_unpublish(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/unpublish",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 3. PATCH behaviour


def test_patch_non_draft_returns_409(admin_client):
    """PATCH on an approved/published row must return 409."""
    from src import db as db_mod

    pub_id = _seed_draft(admin_client)
    conn = db_mod.get_conn()
    conn.execute("UPDATE publications SET status='approved' WHERE id=?", (pub_id,))
    conn.commit()

    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"title": "Changed"},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409


def test_patch_bumps_version(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"title": "New Title"},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2


def test_patch_replaces_body(admin_client):
    pub_id = _seed_draft(admin_client)
    new_body = dict(_VALID_WEEKLY_BODY)
    new_body["project_update"] = dict(new_body["project_update"])
    new_body["project_update"]["narrative"] = "Updated narrative text"

    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"body": new_body},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["body"]["project_update"]["narrative"] == "Updated narrative text"


def test_patch_rejects_unknown_fields(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"status": "published"},  # not in whitelist
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 422


def test_patch_edits_title_and_ref(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"title": "Better Title", "ref": "2026-06-23"},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Better Title"
    assert data["ref"] == "2026-06-23"


# ---------------------------------------------------------------------------
# 4. Approve — gate checks


def test_approve_missing_ack_returns_400(admin_client):
    """Missing or false checklist items must return 400."""
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": {"no_pre_loi_names": True}},  # missing 2 acks
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 400
    data = r.json()
    detail = data["detail"]
    assert "no_other_investors" in detail["missing_acks"]
    assert "figures_stamped" in detail["missing_acks"]


def test_approve_other_investor_in_body_returns_409(admin_client):
    """Injecting 'Aurica' into narrative must trigger the other-investor gate (409)."""
    body = dict(_VALID_WEEKLY_BODY)
    body = json.loads(json.dumps(body))  # deep copy
    body["project_update"]["narrative"] = (
        "We are working with Aurica Capital on the cap table."
    )

    pub_id = _seed_draft(admin_client, body=body)
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409
    violations = r.json()["detail"]["hard_violations"]
    assert any("aurica" in v.lower() for v in violations)


def test_approve_extra_key_in_live_deal_returns_409(admin_client):
    """A live_deal with an extra key violates validate_body → 409."""
    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["live_deals"] = [
        {
            "name": "TestCo",
            "codename": "EAGLE",
            "stage": "due_diligence",
            "rev_m": 10,
            "ebitda_m": 1,
            "ev_m": 5,
            "multiple": 5.0,
            "earnout": "",
            "dd_status": "",
            "close_target": "",
            "commentary": "",
            "FORBIDDEN_INTERNAL_FIELD": "leak",  # not in contract
        }
    ]
    pub_id = _seed_draft(admin_client, body=body)
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409
    violations = r.json()["detail"]["hard_violations"]
    assert any("FORBIDDEN_INTERNAL_FIELD" in v for v in violations)


def test_approve_clean_draft_succeeds(admin_client):
    """A clean draft with full acks and valid body should approve."""
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "approved"
    assert data["approved_by"] == "rd"


def test_force_cannot_override_denylist(admin_client):
    """force=1 must NOT override the other-investor denylist — it is a HARD gate (409 either way)."""
    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["project_update"]["narrative"] = "ASF is our preferred LP."

    pub_id = _seed_draft(admin_client, body=body)
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve?force=1",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409
    assert "hard_violations" in r.json()["detail"]


def _soft_only_body():
    """A body that is structurally valid + denylist-clean but has an unstamped figure (SOFT gate)."""
    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["pipeline"]["funnel"]["items"] = [
        {
            "codename": "EAGLE",
            "stage": "valuation_rfi",
            "sector": "Radiology",
            "region": "Bayern",
            "size_band": "€1–3M",
            "strategic_fit": "high",
        }
    ]
    body["stamps"] = {
        "pipeline.funnel": {"source": "dealroom.db"}
    }  # missing as_of → soft hit
    return body


def test_soft_gate_blocks_without_force(admin_client):
    """An unstamped figure (soft gate) blocks approval unless forced."""
    pub_id = _seed_draft(admin_client, body=_soft_only_body())
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409
    assert "soft_violations" in r.json()["detail"]


def test_force_overrides_only_soft_gate_and_audits(admin_client):
    """force=1 overrides the SOFT figures-stamped gate, recording a body hash in audit_log."""
    from src import db as db_mod

    pub_id = _seed_draft(admin_client, body=_soft_only_body())
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve?force=1",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    conn = db_mod.get_conn()
    override = conn.execute(
        "SELECT * FROM audit_log WHERE action='approve_force_override' AND entity=?",
        (f"pub:{pub_id}",),
    ).fetchone()
    assert override is not None, "force override must be recorded in audit_log"
    after_data = json.loads(override["after"])
    assert "soft_violations" in after_data
    assert "body_sha256" in after_data


# ---------------------------------------------------------------------------
# 5. Publish / archive


def test_publish_non_approved_returns_409(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/publish",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409


def test_publish_archives_prior_and_only_one_published_per_kind(admin_client):
    """Publishing a new row must archive the prior published row of the same kind.
    After publish, exactly one row is 'published' for the kind."""
    from src import db as db_mod

    conn = db_mod.get_conn()
    now = db_mod.now_iso()

    # Seed an existing published row
    conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, published_at, version) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "weekly_update",
            "2026-06-13",
            "Old Update",
            "published",
            json.dumps(_VALID_WEEKLY_BODY),
            now,
            now,
            1,
        ),
    )
    conn.commit()
    old_pub_id = conn.execute(
        "SELECT id FROM publications WHERE status='published' AND kind='weekly_update'"
    ).fetchone()["id"]

    # Seed a new draft and approve it
    new_pub_id = _seed_draft(admin_client)
    admin_client.post(
        f"/api/publication/{new_pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )

    # Publish the new one
    r = admin_client.post(
        f"/api/publication/{new_pub_id}/publish",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "published"

    # Old row must now be 'archived'
    old_row = conn.execute(
        "SELECT status FROM publications WHERE id=?", (old_pub_id,)
    ).fetchone()
    assert old_row["status"] == "archived", "prior published row must be archived"

    # Exactly one published row per kind
    published_count = conn.execute(
        "SELECT COUNT(*) FROM publications WHERE kind='weekly_update' AND status='published'"
    ).fetchone()[0]
    assert published_count == 1


def test_investor_sees_new_published_body(admin_client):
    """After publish, investor GET /api/published returns the new body."""
    new_body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    new_body["project_update"]["narrative"] = "Unique narrative for investor"

    pub_id = _seed_draft(admin_client, body=new_body)
    admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    admin_client.post(
        f"/api/publication/{pub_id}/publish",
        headers={"X-Remote-User": "roman"},
    )

    r = admin_client.get(
        "/api/published?kind=weekly_update",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 200
    data = r.json()
    assert (
        data["body"]["project_update"]["narrative"] == "Unique narrative for investor"
    )


# ---------------------------------------------------------------------------
# 6. Full lifecycle: assemble → patch → approve → publish → investor read


def test_full_lifecycle(admin_client):
    """End-to-end: assemble draft → patch narrative → approve → publish → investor sees it."""
    from src import db as db_mod

    # Step 1: seed a draft (simulate assemble, avoid real DB dependency)
    pub_id = _seed_draft(admin_client)

    # Step 2: patch authored content (narrative + fundraising)
    patched_body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    patched_body["project_update"]["narrative"] = "Strong quarter, pipeline growing."
    patched_body["project_update"]["fundraising"]["tax_structure"] = "GmbH & Co. KG"
    patched_body["project_update"]["fundraising"]["capital_plan"] = "€10M target by Q4."

    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"body": patched_body},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2

    # Step 3: approve with full checklist
    r = admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # Step 4: publish
    r = admin_client.post(
        f"/api/publication/{pub_id}/publish",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "published"

    # Step 5: investor sees the authored content
    r = admin_client.get(
        "/api/published?kind=weekly_update",
        headers={"X-Remote-User": "investor"},
    )
    assert r.status_code == 200
    body = r.json()["body"]
    assert body["project_update"]["narrative"] == "Strong quarter, pipeline growing."
    assert body["project_update"]["fundraising"]["tax_structure"] == "GmbH & Co. KG"
    assert body["project_update"]["fundraising"]["capital_plan"] == "€10M target by Q4."

    # Audit log must have entries for patch, approve, publish
    conn = db_mod.get_conn()
    actions = {
        row["action"] for row in conn.execute("SELECT action FROM audit_log").fetchall()
    }
    assert "patch_publication" in actions
    assert "approve_publication" in actions
    assert "publish_publication" in actions


# ---------------------------------------------------------------------------
# 7. Unpublish


def test_unpublish_moves_to_archived(admin_client):

    pub_id = _seed_draft(admin_client)
    admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    admin_client.post(
        f"/api/publication/{pub_id}/publish",
        headers={"X-Remote-User": "roman"},
    )

    r = admin_client.post(
        f"/api/publication/{pub_id}/unpublish",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    # Investor now sees empty
    r = admin_client.get(
        "/api/published?kind=weekly_update",
        headers={"X-Remote-User": "investor"},
    )
    assert r.json() == {"empty": True}


def test_unpublish_non_published_returns_409(admin_client):
    pub_id = _seed_draft(admin_client)
    r = admin_client.post(
        f"/api/publication/{pub_id}/unpublish",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# 8. Diff endpoint


def test_diff_no_baseline_returns_all_added(admin_client):
    """With no published baseline, diff must return all leaf paths as 'added'."""
    pub_id = _seed_draft(admin_client)
    r = admin_client.get(
        f"/api/publication/{pub_id}/diff",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["added"]) > 0
    assert data["removed"] == []
    assert data["changed"] == []


def test_diff_shows_changed_field(admin_client):
    """After patching a field, diff vs the published baseline must show it as changed."""
    from src import db as db_mod

    # Seed a published baseline
    conn = db_mod.get_conn()
    now = db_mod.now_iso()
    conn.execute(
        "INSERT INTO publications (kind, ref, title, status, body, created_at, published_at, version) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            "weekly_update",
            "2026-06-13",
            "Old",
            "published",
            json.dumps(_VALID_WEEKLY_BODY),
            now,
            now,
            1,
        ),
    )
    conn.commit()

    # New draft with changed narrative
    new_body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    new_body["project_update"]["narrative"] = "New narrative here"
    pub_id = _seed_draft(admin_client, body=new_body)

    r = admin_client.get(
        f"/api/publication/{pub_id}/diff",
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 200
    data = r.json()
    changed_paths = [c["path"] for c in data["changed"]]
    assert any("narrative" in p for p in changed_paths)


# ---------------------------------------------------------------------------
# 9. gates unit tests


def test_gates_scan_other_investors_finds_aurica():
    from src.gates import scan_other_investors

    body = {"project_update": {"narrative": "We spoke with Aurica Capital last week."}}
    findings = scan_other_investors(body)
    assert len(findings) > 0
    assert any("aurica" in f.lower() for f in findings)


def test_gates_scan_other_investors_clean():
    from src.gates import scan_other_investors

    body = {"project_update": {"narrative": "Strada is our co-investor."}}
    assert scan_other_investors(body) == []


def test_gates_check_pre_loi_names_blocked():
    from src.gates import check_pre_loi_names

    body = {
        "pipeline": {
            "funnel": {
                "items": [
                    {
                        "codename": "EAGLE",
                        "company_name": "Meditec GmbH",
                        "stage": "valuation_rfi",
                    }
                ]
            }
        }
    }
    violations = check_pre_loi_names(body)
    assert len(violations) > 0


def test_gates_check_pre_loi_names_clean():
    from src.gates import check_pre_loi_names

    body = {
        "pipeline": {
            "funnel": {
                "items": [
                    {
                        "codename": "EAGLE",
                        "stage": "valuation_rfi",
                        "sector": "healthcare",
                        "region": "Bavaria",
                        "size_band": "€1–3M",
                        "strategic_fit": "high",
                    }
                ]
            }
        }
    }
    assert check_pre_loi_names(body) == []


def test_gates_validate_body_rejects_extra_key():
    from src.gates import validate_body

    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["EXTRA_FORBIDDEN"] = "should not be here"
    violations = validate_body("weekly_update", body)
    assert any("EXTRA_FORBIDDEN" in v for v in violations)


def test_gates_validate_body_clean_weekly():
    from src.gates import validate_body

    violations = validate_body("weekly_update", _VALID_WEEKLY_BODY)
    assert violations == [], f"Expected clean body to pass, got: {violations}"


# ---------------------------------------------------------------------------
# Complete-allowlist + hard-at-publish hardening (M3 Codex review)


def test_validate_body_rejects_extra_key_under_project_update():
    from src.gates import validate_body

    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["project_update"]["internal_note"] = "raw dealroom note"
    v = validate_body("weekly_update", body)
    assert any("internal_note" in x for x in v)


def test_validate_body_rejects_extra_key_under_pipeline():
    from src.gates import validate_body

    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["pipeline"]["private_debug"] = {"raw_row_id": 7}
    v = validate_body("weekly_update", body)
    assert any("private_debug" in x for x in v)


def test_validate_body_rejects_extra_key_in_sources_uses_item():
    from src.gates import validate_body

    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["project_update"]["fundraising"]["sources_uses"] = [
        {"item": "Debt", "amount_m": 5, "note": "", "dealroom_id": 123}
    ]
    v = validate_body("weekly_update", body)
    assert any("dealroom_id" in x for x in v)


def test_validate_body_rejects_extra_key_in_board_sections():
    from src.gates import validate_body

    body = {
        "meeting": {"date": "", "location": "", "attendees": [], "raw_emails": ["x@y"]},
        "agenda": [{"item": "1", "owner": "RD", "minutes": "", "internal": "z"}],
        "decisions": [],
        "pre_read": [],
        "minutes": "",
        "kpis": [],
        "stamps": {},
    }
    v = validate_body("board_pack", body)
    assert any("raw_emails" in x for x in v)
    assert any("internal" in x for x in v)


def test_denylist_catches_key_name():
    """scan_other_investors scans dict KEYS too — a leaked field name must be caught."""
    from src.gates import scan_other_investors

    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["project_update"]["aurica_note"] = "anything"
    findings = scan_other_investors(body)
    assert any("aurica" in f.lower() for f in findings)


def test_denylist_normalizes_zero_width_and_unicode():
    from src.gates import scan_other_investors

    # zero-width space inside the token + fullwidth letters should still be caught
    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["project_update"]["narrative"] = "deal with A​urica is set"
    assert scan_other_investors(body)


def test_publish_is_the_wall_rejects_tampered_approved_body(admin_client):
    """Even if an approved row's body is later tampered to carry a denylist hit (DB-level),
    publish re-runs the HARD gates and refuses (409). Publish is the real wall."""
    from src import db as db_mod

    pub_id = _seed_draft(admin_client)
    admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    # Tamper directly in the DB (simulate a path that bypassed approve)
    tampered = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    tampered["project_update"]["narrative"] = "Co-investing with Aurica."
    conn = db_mod.get_conn()
    conn.execute(
        "UPDATE publications SET body=? WHERE id=?", (json.dumps(tampered), pub_id)
    )
    conn.commit()

    r = admin_client.post(
        f"/api/publication/{pub_id}/publish", headers={"X-Remote-User": "roman"}
    )
    assert r.status_code == 409
    assert "hard_violations" in r.json()["detail"]
    # And it did not become published
    row = conn.execute(
        "SELECT status FROM publications WHERE id=?", (pub_id,)
    ).fetchone()
    assert row["status"] == "approved"


def test_patch_rejects_after_approval(admin_client):
    """PATCH must reject a non-draft row (approved) — content can't change after approval."""
    pub_id = _seed_draft(admin_client)
    admin_client.post(
        f"/api/publication/{pub_id}/approve",
        json={"checklist": _CHECKLIST_ALL_TRUE},
        headers={"X-Remote-User": "roman"},
    )
    r = admin_client.patch(
        f"/api/publication/{pub_id}",
        json={"title": "sneaky edit"},
        headers={"X-Remote-User": "roman"},
    )
    assert r.status_code == 409


def test_validate_body_rejects_unknown_stamp_key():
    """stamp KEYS are an exact allowlist — a surprise key like 'secret_debug' must be rejected,
    since /api/published returns the whole body to the investor."""
    from src.gates import validate_body

    body = json.loads(json.dumps(_VALID_WEEKLY_BODY))
    body["stamps"]["secret_debug"] = {"source": "x", "as_of": "y"}
    v = validate_body("weekly_update", body)
    assert any("secret_debug" in x for x in v)
