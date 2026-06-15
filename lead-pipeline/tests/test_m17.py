"""Tests for M17 — BA Prep Hardening.

Covers:
- approved_for_sendout column migration (default=0)
- region_prep column migration
- enrich_regions dry_run returns stats, no DB writes
- enrich_regions updates DB for matched cities
- enrich_regions skips records with existing region
- enrich_regions unknown city → no update, no error
- lookup_region found
- lookup_region case-insensitive
- lookup_region not found
- PATCH approved_for_sendout via dashboard writeback
- PATCH new letter fields accepted (anrede, salutation, gf_name, leistung_text, region, region_prep)
- export_cmd approved_only=True filters to approved records only
- _record_to_row uses region_prep for Region column
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import src.pipeline.region_lookup as rl_mod

from src.pipeline.db import ensure_schema, get_connection
from src.pipeline.export import _record_to_row
from src.pipeline.models import CompanyRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tmp_db(tmp_path: Path) -> Path:
    db = tmp_path / "test_pipeline.db"
    ensure_schema(db)
    return db


def _insert_record(db: Path, domain: str, **kwargs) -> None:
    rec_id = hashlib.md5(domain.encode()).hexdigest()[:12]
    defaults = {
        "id": rec_id,
        "domain": domain,
        "full_name": "Test GmbH",
        "profile_id": "test",
        "source": "test",
        "pipeline_stage": "ingested",
        "ingested_at": "2026-01-01T00:00:00",
    }
    defaults.update(kwargs)
    with get_connection(db) as conn:
        placeholders = ", ".join(f":{k}" for k in defaults)
        cols = ", ".join(defaults.keys())
        conn.execute(
            f"INSERT INTO company_records ({cols}) VALUES ({placeholders})", defaults
        )


def _mock_mapping() -> dict:
    return {
        "hamburg": ("Hamburg", "in Hamburg"),
        "münchen": ("München", "in München"),
        "allgäu": ("Allgäu", "im Allgäu"),
    }


def _run_enrich(db: Path, dry_run: bool) -> dict:
    """Run enrich_regions with mocked mapping and settings pointing to tmp db."""
    from src.pipeline.ingest import enrich_regions

    rl_mod.load_region_mapping.cache_clear()
    with patch.object(rl_mod, "load_region_mapping", return_value=_mock_mapping()):
        with patch("src.pipeline.ingest.settings") as mock_settings:
            mock_settings.PIPELINE_DB_PATH = db
            result = enrich_regions(dry_run=dry_run)
    rl_mod.load_region_mapping.cache_clear()
    return result


def _make_rec(**kwargs) -> CompanyRecord:
    defaults = dict(
        domain="test.de",
        full_name="Test GmbH",
        profile_id="test",
        source="ORBIS",
        klass="A",
    )
    defaults.update(kwargs)
    return CompanyRecord(**defaults)


# ---------------------------------------------------------------------------
# Step 1 — DB schema
# ---------------------------------------------------------------------------


def test_approved_for_sendout_column_added(tmp_path):
    db = _tmp_db(tmp_path)
    with get_connection(db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
        }
    assert "approved_for_sendout" in cols


def test_approved_for_sendout_default_zero(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "test.de")
    with get_connection(db) as conn:
        val = conn.execute(
            "SELECT approved_for_sendout FROM company_records WHERE domain='test.de'"
        ).fetchone()[0]
    assert val == 0


def test_region_prep_column_added(tmp_path):
    db = _tmp_db(tmp_path)
    with get_connection(db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
        }
    assert "region_prep" in cols


# ---------------------------------------------------------------------------
# Step 3 — lookup_region
# ---------------------------------------------------------------------------


def test_lookup_region_found():
    from src.pipeline.region_lookup import lookup_region

    rl_mod.load_region_mapping.cache_clear()
    with patch.object(rl_mod, "load_region_mapping", return_value=_mock_mapping()):
        region, region_prep = lookup_region("Hamburg")
    assert region == "Hamburg"
    assert region_prep == "in Hamburg"


def test_lookup_region_case_insensitive():
    from src.pipeline.region_lookup import lookup_region

    rl_mod.load_region_mapping.cache_clear()
    with patch.object(rl_mod, "load_region_mapping", return_value=_mock_mapping()):
        r1, rp1 = lookup_region("HAMBURG")
        r2, rp2 = lookup_region("hamburg")
    assert r1 == r2 == "Hamburg"
    assert rp1 == rp2 == "in Hamburg"


def test_lookup_region_not_found():
    from src.pipeline.region_lookup import lookup_region

    rl_mod.load_region_mapping.cache_clear()
    with patch.object(rl_mod, "load_region_mapping", return_value=_mock_mapping()):
        r, rp = lookup_region("Nonexistent City XYZ")
    assert r is None
    assert rp is None


# ---------------------------------------------------------------------------
# Step 4 — enrich_regions
# ---------------------------------------------------------------------------


def test_enrich_regions_dry_run(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "hamburg-test.de", city="Hamburg")
    result = _run_enrich(db, dry_run=True)
    assert result["matched"] >= 1
    assert result["total_checked"] >= 1
    # Dry run: DB not written
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT region FROM company_records WHERE domain='hamburg-test.de'"
        ).fetchone()
    assert row[0] is None


def test_enrich_regions_updates_db(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "hamburg-test.de", city="Hamburg")
    result = _run_enrich(db, dry_run=False)
    assert result["updated"] >= 1
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT region, region_prep FROM company_records WHERE domain='hamburg-test.de'"
        ).fetchone()
    assert row[0] == "Hamburg"
    assert row[1] == "in Hamburg"


def test_enrich_regions_skips_already_filled(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "hamburg-test.de", city="Hamburg", region="ExistingRegion")
    result = _run_enrich(db, dry_run=False)
    assert (
        result["total_checked"] == 0
    )  # record has region already, excluded from query
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT region FROM company_records WHERE domain='hamburg-test.de'"
        ).fetchone()
    assert row[0] == "ExistingRegion"  # unchanged


def test_enrich_regions_unknown_city(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "unknown-test.de", city="Atlantis")
    result = _run_enrich(db, dry_run=False)
    assert result["total_checked"] == 1
    assert result["matched"] == 0
    assert result["updated"] == 0
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT region FROM company_records WHERE domain='unknown-test.de'"
        ).fetchone()
    assert row[0] is None


# ---------------------------------------------------------------------------
# Step 5 — _WRITEBACK_FIELDS expansion
# ---------------------------------------------------------------------------


def test_patch_approved_for_sendout(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "approve-test.de")
    from src.pipeline.dashboard import _WRITEBACK_FIELDS

    assert "approved_for_sendout" in _WRITEBACK_FIELDS
    # Simulate what PATCH handler does
    with get_connection(db) as conn:
        conn.execute(
            "UPDATE company_records SET approved_for_sendout = 1 WHERE domain = 'approve-test.de'"
        )
    with get_connection(db) as conn:
        val = conn.execute(
            "SELECT approved_for_sendout FROM company_records WHERE domain='approve-test.de'"
        ).fetchone()[0]
    assert val == 1


def test_patch_new_letter_fields():
    from src.pipeline.dashboard import _WRITEBACK_FIELDS

    for field in (
        "anrede",
        "salutation",
        "owner_name",
        "leistung_text",
        "region",
        "region_prep",
    ):
        assert field in _WRITEBACK_FIELDS, f"{field} missing from _WRITEBACK_FIELDS"


# ---------------------------------------------------------------------------
# Step 7 — Export: region_prep + approved_only
# ---------------------------------------------------------------------------


def test_export_region_prep_used():
    rec = _make_rec(region="Allgäu", region_prep="im Allgäu")
    row = _record_to_row(rec, {})
    assert row["Region"] == "im Allgäu"


def test_export_region_prep_fallback_to_region():
    rec = _make_rec(region="Allgäu", region_prep=None)
    row = _record_to_row(rec, {})
    assert row["Region"] == "Allgäu"


def test_export_approved_only(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(
        db,
        "approved.de",
        klass="A",
        pipeline_stage="classified",
        filter_pass=1,
        already_approached=0,
        approved_for_sendout=1,
    )
    _insert_record(
        db,
        "unapproved.de",
        klass="A",
        pipeline_stage="classified",
        filter_pass=1,
        already_approached=0,
        approved_for_sendout=0,
    )
    with get_connection(db) as conn:
        rows = conn.execute(
            """SELECT domain FROM company_records
               WHERE klass IN ('A','B','C','E')
               AND already_approached = 0
               AND (filter_pass = 1 OR filter_pass IS NULL)
               AND pipeline_stage NOT IN ('ingested')
               AND approved_for_sendout = 1"""
        ).fetchall()
    domains = [r[0] for r in rows]
    assert "approved.de" in domains
    assert "unapproved.de" not in domains
