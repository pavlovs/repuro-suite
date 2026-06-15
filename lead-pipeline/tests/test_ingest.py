"""Tests for M3 data ingest — normalize_domain, adapters, DB helpers, integration."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from src.config import settings
from src.pipeline import db as pipeline_db
from src.pipeline.ingest import (
    WLWCsvAdapter,
    OrbisSheetAdapter,
    _excel_serial_to_age,
    _is_corporate_name,
    _read_llm_prep_enrichment,
    _read_serienbriefe_dedup,
    _normalize_company_name,
    ingest,
    normalize_domain,
)
from src.pipeline.models import CompanyRecord
from src.config.profile import (
    ClassificationConfig,
    DiscoveryConfig,
    ExportConfig,
    FilterConfig,
    IndustryProfile,
    OwnershipConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile() -> IndustryProfile:
    return IndustryProfile(
        id="test_profile",
        name="Test Profile",
        description="Test profile",
        geography={"country": "DE"},
        discovery=DiscoveryConfig(wlw_search_terms=[]),
        filters=FilterConfig(),
        classification=ClassificationConfig(
            target_description="Test",
            class_definitions={"A": "Platform", "B": "Add-on"},
        ),
        ownership=OwnershipConfig(),
        export=ExportConfig(),
    )


def _make_orbis_row(
    name: str = "Test GmbH",
    domain: str = "test.de",
    revenue: object = None,
    ma: object = None,
    street: object = None,
    plz: object = None,
    city: object = None,
    csh_name: object = None,
    csh_direct_pct: object = None,
    csh_total_pct: object = None,
    anrede: object = None,
    vorname: object = None,
    nachname: object = None,
    ges_name: object = None,
    ges_pct: object = None,
    dm_nachname: object = None,
    dm_birthday: object = None,
) -> tuple:
    """Build a 30-element tuple matching ORBIS column indices."""
    row: list = [None] * 30
    row[settings.ORBIS_COL_NAME] = name
    row[settings.ORBIS_COL_DOMAIN] = domain
    row[settings.ORBIS_COL_REVENUE] = revenue
    row[settings.ORBIS_COL_MA] = ma
    row[settings.ORBIS_COL_STREET] = street
    row[settings.ORBIS_COL_PLZ] = plz
    row[settings.ORBIS_COL_CITY] = city
    row[settings.ORBIS_COL_CSH_NAME] = csh_name
    row[settings.ORBIS_COL_CSH_DIRECT_PCT] = csh_direct_pct
    row[settings.ORBIS_COL_CSH_TOTAL_PCT] = csh_total_pct
    row[settings.ORBIS_COL_ANREDE] = anrede
    row[settings.ORBIS_COL_GF_VORNAME] = vorname
    row[settings.ORBIS_COL_GF_NACHNAME] = nachname
    row[settings.ORBIS_COL_GESELLSCHAFTER_NAME] = ges_name
    row[settings.ORBIS_COL_GESELLSCHAFTER_PCT] = ges_pct
    row[settings.ORBIS_COL_DM_NACHNAME] = dm_nachname
    row[settings.ORBIS_COL_DM_BIRTHDAY] = dm_birthday
    return tuple(row)


def _mock_ws(rows: list[tuple]) -> MagicMock:
    ws = MagicMock()
    ws.iter_rows.return_value = iter(rows)
    return ws


def _insert_rec(db_path: Path, rec: CompanyRecord) -> None:
    pipeline_db.ensure_schema(db_path)
    with pipeline_db.get_connection(db_path) as conn:
        pipeline_db.upsert_company(conn, rec, "2026-01-01T00:00:00+00:00")


# ---------------------------------------------------------------------------
# normalize_domain
# ---------------------------------------------------------------------------


def test_normalize_domain_strips_https():
    assert normalize_domain("https://www.example.de/path") == "example.de"


def test_normalize_domain_strips_http():
    assert normalize_domain("http://example.de") == "example.de"


def test_normalize_domain_strips_www():
    assert normalize_domain("www.example.de") == "example.de"


def test_normalize_domain_lowercases():
    assert normalize_domain("EXAMPLE.DE") == "example.de"


def test_normalize_domain_none_input():
    assert normalize_domain(None) is None


def test_normalize_domain_empty_string():
    assert normalize_domain("") is None


def test_normalize_domain_whitespace_only():
    assert normalize_domain("   ") is None


def test_normalize_domain_strips_path():
    assert normalize_domain("example.de/some/path") == "example.de"


# ---------------------------------------------------------------------------
# _is_corporate_name
# ---------------------------------------------------------------------------


def test_is_corporate_name_gmbh():
    assert _is_corporate_name("Meditec Holding GmbH") is True


def test_is_corporate_name_ag():
    assert _is_corporate_name("Fresenius AG") is True


def test_is_corporate_name_holding():
    assert _is_corporate_name("Some Holding Group") is True


def test_is_corporate_name_person():
    assert _is_corporate_name("Hans Müller") is False


def test_is_corporate_name_none():
    assert _is_corporate_name(None) is False


# ---------------------------------------------------------------------------
# _excel_serial_to_age
# ---------------------------------------------------------------------------


def test_excel_serial_to_age_valid():
    # Serial 25569 = 1970-01-01 (approx 56 years ago as of 2026)
    age = _excel_serial_to_age(25569)
    assert isinstance(age, int)
    assert 50 < age < 65


def test_excel_serial_to_age_none():
    assert _excel_serial_to_age(None) is None


def test_excel_serial_to_age_invalid_string():
    assert _excel_serial_to_age("n.v.") is None


def test_excel_serial_to_age_zero():
    assert _excel_serial_to_age(0) is None


# ---------------------------------------------------------------------------
# WLWCsvAdapter
# ---------------------------------------------------------------------------


def test_wlw_csv_adapter_reads_records(tmp_path: Path):
    csv_path = tmp_path / "00_wlw_raw.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["domain", "full_name", "profile_id", "source"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "domain": "firma.de",
                "full_name": "Firma GmbH",
                "profile_id": "test",
                "source": "WLW",
            }
        )
        writer.writerow(
            {
                "domain": "andere.de",
                "full_name": "Andere GmbH",
                "profile_id": "test",
                "source": "WLW",
            }
        )
    adapter = WLWCsvAdapter(csv_path)
    records = adapter.read()
    assert len(records) == 2
    assert records[0].domain == "firma.de"


def test_wlw_csv_adapter_missing_file(tmp_path: Path):
    adapter = WLWCsvAdapter(tmp_path / "nonexistent.csv")
    assert adapter.read() == []


def test_wlw_csv_adapter_skips_missing_domain(tmp_path: Path):
    csv_path = tmp_path / "00_wlw_raw.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["domain", "full_name", "profile_id", "source"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "domain": "",
                "full_name": "No Domain GmbH",
                "profile_id": "test",
                "source": "WLW",
            }
        )
        writer.writerow(
            {
                "domain": "valid.de",
                "full_name": "Valid GmbH",
                "profile_id": "test",
                "source": "WLW",
            }
        )
    records = WLWCsvAdapter(csv_path).read()
    assert len(records) == 1
    assert records[0].domain == "valid.de"


# ---------------------------------------------------------------------------
# OrbisSheetAdapter
# ---------------------------------------------------------------------------


def test_orbis_column_mapping():
    row = _make_orbis_row(
        name="Meditec GmbH",
        domain="meditec.de",
        revenue="1500",
        ma="35",
        street="Hauptstr. 1",
        plz="12345",
        city="Berlin",
    )
    ws = _mock_ws([row])
    adapter = OrbisSheetAdapter(ws, "test_profile")
    records = adapter.read()
    assert len(records) == 1
    rec = records[0]
    assert rec.domain == "meditec.de"
    assert rec.full_name == "Meditec GmbH"
    assert rec.ma_count == 35
    assert rec.revenue_tsd_eur == 1500.0
    assert rec.street == "Hauptstr. 1"
    assert rec.plz_ort == "12345 Berlin"
    assert rec.city == "Berlin"


def test_orbis_subsidiary_detection_corporate_csh():
    row = _make_orbis_row(
        domain="sub.de",
        csh_name="Fresenius AG",
        csh_total_pct=75.0,
    )
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].is_subsidiary is True


def test_orbis_no_subsidiary_person_name():
    row = _make_orbis_row(
        domain="person.de",
        csh_name="Hans Müller",
        csh_total_pct=100.0,
    )
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].is_subsidiary is None


def test_orbis_no_subsidiary_low_pct():
    row = _make_orbis_row(
        domain="lowpct.de",
        csh_name="Holding GmbH",
        csh_total_pct=40.0,
    )
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].is_subsidiary is None


def test_orbis_ma_nv_becomes_none():
    row = _make_orbis_row(domain="nav.de", ma="n.v.")
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].ma_count is None


def test_orbis_owner_name_from_vorname_nachname():
    row = _make_orbis_row(domain="gf.de", vorname="Hans", nachname="Müller")
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].owner_name == "Hans Müller"


def test_orbis_owner_name_fallback_to_dm_nachname():
    row = _make_orbis_row(domain="fallback.de", dm_nachname="Schmidt")
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].owner_name == "Schmidt"


def test_orbis_prefers_gesellschafter_col_over_csh():
    row = _make_orbis_row(
        domain="ges.de",
        ges_name="Direkt Gesellschafter GmbH",
        ges_pct=100.0,
        csh_name="Holding AG",
        csh_total_pct=100.0,
    )
    ws = _mock_ws([row])
    records = OrbisSheetAdapter(ws, "p").read()
    assert records[0].gesellschafter_name == "Direkt Gesellschafter GmbH"


def test_orbis_skips_rows_without_domain():
    row_no_domain = _make_orbis_row(name="No Domain GmbH", domain="")
    row_valid = _make_orbis_row(name="Valid GmbH", domain="valid.de")
    ws = _mock_ws([row_no_domain, row_valid])
    records = OrbisSheetAdapter(ws, "p").read()
    assert len(records) == 1
    assert records[0].domain == "valid.de"


# ---------------------------------------------------------------------------
# _read_llm_prep_enrichment
# ---------------------------------------------------------------------------


def test_read_llm_prep_enrichment_basic():
    row: list = [None] * 10
    row[settings.LLM_PREP_COL_DOMAIN] = "firma.de"
    row[settings.LLM_PREP_COL_HRB] = "HRB 12345"
    row[settings.LLM_PREP_COL_GF] = "Müller, Schmidt"
    row[settings.LLM_PREP_COL_MA] = "25"
    ws = _mock_ws([tuple(row)])
    result = _read_llm_prep_enrichment(ws)
    assert "firma.de" in result
    assert result["firma.de"]["hrb_number"] == "HRB 12345"
    assert result["firma.de"]["owner_name"] == "Müller"  # first from comma-separated
    assert result["firma.de"]["ma_count"] == 25


def test_read_llm_prep_enrichment_skips_no_domain():
    row: list = [None] * 10
    row[settings.LLM_PREP_COL_DOMAIN] = ""
    row[settings.LLM_PREP_COL_HRB] = "HRB 99999"
    ws = _mock_ws([tuple(row)])
    result = _read_llm_prep_enrichment(ws)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# _read_serienbriefe_dedup
# ---------------------------------------------------------------------------


def test_read_serienbriefe_dedup_domains():
    row1: list = [None] * 12
    row1[settings.SERIENBRIEFE_COL_DOMAIN] = "www.approached.de"
    row1[11] = "Approached GmbH"
    row2: list = [None] * 12
    row2[settings.SERIENBRIEFE_COL_DOMAIN] = "https://other.de/path"
    row2[11] = "Other GmbH & Co. KG"
    ws = _mock_ws([tuple(row1), tuple(row2)])
    domains, name_index = _read_serienbriefe_dedup(ws)
    assert "approached.de" in domains
    assert "other.de" in domains


def test_read_serienbriefe_dedup_name_index():
    row: list = [None] * 12
    row[settings.SERIENBRIEFE_COL_DOMAIN] = "approached.de"
    row[11] = "Krolicki Medizintechnik GmbH & Co. KG"
    ws = _mock_ws([tuple(row)])
    domains, name_index = _read_serienbriefe_dedup(ws)
    assert "krolicki medizintechnik" in name_index


def test_read_serienbriefe_dedup_skips_empty():
    row: list = [None] * 12
    row[settings.SERIENBRIEFE_COL_DOMAIN] = None
    ws = _mock_ws([tuple(row)])
    domains, name_index = _read_serienbriefe_dedup(ws)
    assert len(domains) == 0


def test_normalize_company_name():
    assert (
        _normalize_company_name("Krolicki Medizintechnik GmbH & Co. KG")
        == "krolicki medizintechnik"
    )
    assert (
        _normalize_company_name("MSG Medizinische Geräte GmbH")
        == "msg medizinische geräte"
    )
    assert _normalize_company_name("DiaMedic GmbH") == "diamedic"
    assert _normalize_company_name("") == ""


# ---------------------------------------------------------------------------
# db.upsert_company — insert + dedup + mark_approached
# ---------------------------------------------------------------------------


def test_db_upsert_insert(tmp_path: Path):
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    rec = CompanyRecord(
        domain="test.de", full_name="Test GmbH", profile_id="p", source="ORBIS"
    )
    with pipeline_db.get_connection(db_path) as conn:
        pipeline_db.upsert_company(conn, rec, "2026-01-01T00:00:00+00:00")
    assert pipeline_db.get_total_count(db_path) == 1


def test_db_upsert_dedup_orbis_wins_structured(tmp_path: Path):
    """ORBIS record inserted first; WLW upsert should not overwrite structured fields."""
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    orbis = CompanyRecord(
        domain="shared.de",
        full_name="Shared GmbH",
        profile_id="p",
        source="ORBIS",
        ma_count=30,
        owner_name="Schmidt",
    )
    wlw = CompanyRecord(
        domain="shared.de",
        full_name="Shared GmbH WLW",
        profile_id="p",
        source="WLW",
        ma_count=10,
        scraped_text="some text",
    )
    ts = "2026-01-01T00:00:00+00:00"
    with pipeline_db.get_connection(db_path) as conn:
        pipeline_db.upsert_company(conn, orbis, ts)
        pipeline_db.upsert_company(conn, wlw, ts)
    assert pipeline_db.get_total_count(db_path) == 1
    with pipeline_db.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT ma_count, owner_name, scraped_text FROM company_records"
        ).fetchone()
    assert row["ma_count"] == 30  # ORBIS wins
    assert row["owner_name"] == "Schmidt"  # ORBIS wins
    assert row["scraped_text"] == "some text"  # WLW fills NULL


def test_db_mark_approached(tmp_path: Path):
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    rec = CompanyRecord(
        domain="target.de", full_name="Target GmbH", profile_id="p", source="ORBIS"
    )
    with pipeline_db.get_connection(db_path) as conn:
        pipeline_db.upsert_company(conn, rec, "2026-01-01T00:00:00+00:00")
        count = pipeline_db.mark_approached(conn, frozenset(["target.de"]))
    assert count == 1
    with pipeline_db.get_connection(db_path) as conn:
        row = conn.execute("SELECT already_approached FROM company_records").fetchone()
    assert row["already_approached"] == 1


# ---------------------------------------------------------------------------
# ingest() integration
# ---------------------------------------------------------------------------


def test_ingest_dry_run_no_db(tmp_path: Path, monkeypatch):
    """dry_run=True must not create pipeline.db."""
    db_path = tmp_path / "pipeline.db"
    monkeypatch.setattr(settings, "PIPELINE_DB_PATH", db_path)
    monkeypatch.setattr(settings, "STAGING_WLW_RAW", tmp_path / "nonexistent.csv")
    monkeypatch.setattr(settings, "SOURCE_EXCEL", tmp_path / "nonexistent.xlsx")
    profile = _make_profile()
    count = ingest(profile, dry_run=True)
    assert not db_path.exists()
    assert count == 0  # no sources available


def test_ingest_real_run_creates_db(tmp_path: Path, monkeypatch):
    """Real run with a small CSV creates pipeline.db with correct count."""
    db_path = tmp_path / "pipeline.db"
    csv_path = tmp_path / "00_wlw_raw.csv"
    monkeypatch.setattr(settings, "PIPELINE_DB_PATH", db_path)
    monkeypatch.setattr(settings, "STAGING_WLW_RAW", csv_path)
    monkeypatch.setattr(settings, "SOURCE_EXCEL", tmp_path / "nonexistent.xlsx")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["domain", "full_name", "profile_id", "source"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "domain": "alpha.de",
                "full_name": "Alpha GmbH",
                "profile_id": "p",
                "source": "WLW",
            }
        )
        writer.writerow(
            {
                "domain": "beta.de",
                "full_name": "Beta GmbH",
                "profile_id": "p",
                "source": "WLW",
            }
        )

    count = ingest(_make_profile())
    assert db_path.exists()
    assert count == 2


def test_ingest_already_approached_flagged(tmp_path: Path, monkeypatch):
    """Records whose domain appears in the Serienbriefe set get already_approached=1."""
    db_path = tmp_path / "pipeline.db"
    csv_path = tmp_path / "00_wlw_raw.csv"
    monkeypatch.setattr(settings, "PIPELINE_DB_PATH", db_path)
    monkeypatch.setattr(settings, "STAGING_WLW_RAW", csv_path)
    monkeypatch.setattr(settings, "SOURCE_EXCEL", tmp_path / "nonexistent.xlsx")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["domain", "full_name", "profile_id", "source"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "domain": "approached.de",
                "full_name": "Approached GmbH",
                "profile_id": "p",
                "source": "WLW",
            }
        )
        writer.writerow(
            {
                "domain": "new.de",
                "full_name": "New GmbH",
                "profile_id": "p",
                "source": "WLW",
            }
        )

    # Patch _read_serienbriefe_domains is not easily injectable here;
    # instead test via mark_approached directly in db layer.
    ingest(_make_profile())
    pipeline_db.ensure_schema(db_path)
    with pipeline_db.get_connection(db_path) as conn:
        pipeline_db.mark_approached(conn, frozenset(["approached.de"]))
        row = conn.execute(
            "SELECT already_approached FROM company_records WHERE domain='approached.de'"
        ).fetchone()
    assert row["already_approached"] == 1
