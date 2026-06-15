"""Tests for M17b — sideview redesign + new classify fields.

Covers:
- leistung_absatz_2 column created by ensure_schema (default NULL)
- mehrwerte column created by ensure_schema (default NULL)
- update_classify_result writes leistung_absatz_2 + mehrwerte
- PATCH leistung_absatz_2 via dashboard writeback persists
- PATCH mehrwerte via dashboard writeback persists
- _record_to_row maps leistung_absatz_2 to "Leistung Absatz 2" column
- _record_to_row maps mehrwerte to "Mehrwerte" column
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.pipeline.db import ensure_schema, get_connection, update_classify_result
from src.pipeline.export import _record_to_row
from src.pipeline.models import CompanyRecord


# ---------------------------------------------------------------------------
# Helpers (mirror test_m17.py patterns)
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
        "pipeline_stage": "scraped",
        "ingested_at": "2026-01-01T00:00:00",
    }
    defaults.update(kwargs)
    with get_connection(db) as conn:
        placeholders = ", ".join(f":{k}" for k in defaults)
        cols = ", ".join(defaults.keys())
        conn.execute(
            f"INSERT INTO company_records ({cols}) VALUES ({placeholders})", defaults
        )


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
# DB schema tests
# ---------------------------------------------------------------------------


def test_leistung_absatz_2_column_added(tmp_path):
    db = _tmp_db(tmp_path)
    with get_connection(db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
        }
    assert "leistung_absatz_2" in cols


def test_mehrwerte_column_added(tmp_path):
    db = _tmp_db(tmp_path)
    with get_connection(db) as conn:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
        }
    assert "mehrwerte" in cols


def test_leistung_absatz_2_default_null(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "test-la2.de")
    with get_connection(db) as conn:
        val = conn.execute(
            "SELECT leistung_absatz_2 FROM company_records WHERE domain='test-la2.de'"
        ).fetchone()[0]
    assert val is None


def test_mehrwerte_default_null(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "test-mw.de")
    with get_connection(db) as conn:
        val = conn.execute(
            "SELECT mehrwerte FROM company_records WHERE domain='test-mw.de'"
        ).fetchone()[0]
    assert val is None


# ---------------------------------------------------------------------------
# update_classify_result writes new fields
# ---------------------------------------------------------------------------


def test_update_classify_result_new_fields(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "classify-test.de")

    with get_connection(db) as conn:
        rowcount = update_classify_result(
            conn,
            domain="classify-test.de",
            klass="A",
            services_score=75,
            service_flag=True,
            distributor_flag=True,
            ssb_flag=False,
            leistung_text="Medizinprodukte Vertrieb",
            leistung_absatz_2="Medizinprodukt-Händler",
            mehrwerte="Als Plattform bieten wir Synergien im Einkauf und Logistik.",
            reason_code="Passt",
            reasoning="Fits criteria well.",
            classified_at="2026-03-30T10:00:00",
        )

    assert rowcount == 1

    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT leistung_absatz_2, mehrwerte FROM company_records WHERE domain='classify-test.de'"
        ).fetchone()

    assert row["leistung_absatz_2"] == "Medizinprodukt-Händler"
    assert (
        row["mehrwerte"]
        == "Als Plattform bieten wir Synergien im Einkauf und Logistik."
    )


# ---------------------------------------------------------------------------
# PATCH writeback via dashboard _WRITEBACK_FIELDS
# ---------------------------------------------------------------------------


def test_patch_leistung_absatz_2(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "patch-la2.de")

    from src.pipeline.dashboard import _WRITEBACK_FIELDS

    assert "leistung_absatz_2" in _WRITEBACK_FIELDS

    # Simulate PATCH handler: update whitelisted field directly
    with get_connection(db) as conn:
        conn.execute(
            "UPDATE company_records SET leistung_absatz_2 = ? WHERE domain = ?",
            ("Sprechstundenbedarf", "patch-la2.de"),
        )

    with get_connection(db) as conn:
        val = conn.execute(
            "SELECT leistung_absatz_2 FROM company_records WHERE domain='patch-la2.de'"
        ).fetchone()[0]

    assert val == "Sprechstundenbedarf"


def test_patch_mehrwerte(tmp_path):
    db = _tmp_db(tmp_path)
    _insert_record(db, "patch-mw.de")

    from src.pipeline.dashboard import _WRITEBACK_FIELDS

    assert "mehrwerte" in _WRITEBACK_FIELDS

    with get_connection(db) as conn:
        conn.execute(
            "UPDATE company_records SET mehrwerte = ? WHERE domain = ?",
            ("Skalierungspotenzial durch zentrale Einkaufsstruktur.", "patch-mw.de"),
        )

    with get_connection(db) as conn:
        val = conn.execute(
            "SELECT mehrwerte FROM company_records WHERE domain='patch-mw.de'"
        ).fetchone()[0]

    assert val == "Skalierungspotenzial durch zentrale Einkaufsstruktur."


# ---------------------------------------------------------------------------
# Export column mapping
# ---------------------------------------------------------------------------


def test_export_leistung_absatz_2_used():
    rec = _make_rec(leistung_absatz_2="Medizintechnik-Service")
    row = _record_to_row(rec, {})
    assert row["Leistung Absatz 2"] == "Medizintechnik-Service"


def test_export_mehrwerte_used():
    rec = _make_rec(mehrwerte="Wir ermöglichen Wachstum durch Plattformsynergien.")
    row = _record_to_row(rec, {})
    assert row["Mehrwerte"] == "Wir ermöglichen Wachstum durch Plattformsynergien."


def test_export_leistung_absatz_2_empty_fallback():
    rec = _make_rec(leistung_absatz_2=None)
    row = _record_to_row(rec, {})
    assert row["Leistung Absatz 2"] == ""


def test_export_mehrwerte_empty_fallback():
    rec = _make_rec(mehrwerte=None)
    row = _record_to_row(rec, {})
    assert row["Mehrwerte"] == ""
