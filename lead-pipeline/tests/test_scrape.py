"""Tests for M5 website scraper — DB helpers."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.pipeline import db as pipeline_db
from src.pipeline.models import CompanyRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    return db_path


def _make_filtered_record(domain: str, full_name: str = "Test GmbH") -> CompanyRecord:
    return CompanyRecord(
        domain=domain,
        full_name=full_name,
        profile_id="medtech_germany",
        source="ORBIS",
    )


def _seed_filtered(db_path: Path, records: list[CompanyRecord]) -> None:
    """Seed records and manually set pipeline_stage to 'filtered'."""
    with pipeline_db.get_connection(db_path) as conn:
        for rec in records:
            pipeline_db.upsert_company(conn, rec, "2026-01-01T00:00:00+00:00")
        conn.execute(
            "UPDATE company_records SET pipeline_stage = 'filtered', filter_pass = 1"
        )


# ---------------------------------------------------------------------------
# get_records_for_scrape
# ---------------------------------------------------------------------------

def test_get_records_for_scrape_returns_filtered(tmp_db: Path) -> None:
    _seed_filtered(tmp_db, [_make_filtered_record("a.de"), _make_filtered_record("b.de")])
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 2


def test_get_records_for_scrape_skips_scraped(tmp_db: Path) -> None:
    _seed_filtered(tmp_db, [_make_filtered_record("a.de"), _make_filtered_record("b.de")])
    with pipeline_db.get_connection(tmp_db) as conn:
        conn.execute(
            "UPDATE company_records SET pipeline_stage = 'scraped' WHERE domain = 'a.de'"
        )
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 1
    assert records[0].domain == "b.de"


def test_get_records_for_scrape_skips_scrape_failed(tmp_db: Path) -> None:
    _seed_filtered(tmp_db, [_make_filtered_record("a.de")])
    with pipeline_db.get_connection(tmp_db) as conn:
        conn.execute(
            "UPDATE company_records SET pipeline_stage = 'scrape_failed' WHERE domain = 'a.de'"
        )
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 0


def test_get_records_for_scrape_skips_ingested(tmp_db: Path) -> None:
    """Records that failed filter (stage=ingested) must not be scraped."""
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.upsert_company(conn, _make_filtered_record("a.de"), "2026-01-01T00:00:00+00:00")
    # stage remains 'ingested' (default)
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 0


# ---------------------------------------------------------------------------
# update_scrape_result
# ---------------------------------------------------------------------------

def test_update_scrape_result_with_text_sets_scraped_stage(tmp_db: Path) -> None:
    _seed_filtered(tmp_db, [_make_filtered_record("a.de")])
    ts = datetime.now(timezone.utc).isoformat()
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_scrape_result(conn, "a.de", scraped_text="some text", scraped_at=ts)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT scraped_text, scraped_at, pipeline_stage FROM company_records WHERE domain='a.de'"
        ).fetchone()
    assert row["scraped_text"] == "some text"
    assert row["scraped_at"] == ts
    assert row["pipeline_stage"] == "scraped"


def test_update_scrape_result_empty_text_sets_failed_stage(tmp_db: Path) -> None:
    _seed_filtered(tmp_db, [_make_filtered_record("a.de")])
    ts = datetime.now(timezone.utc).isoformat()
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_scrape_result(conn, "a.de", scraped_text="", scraped_at=ts)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT scraped_text, pipeline_stage FROM company_records WHERE domain='a.de'"
        ).fetchone()
    assert row["scraped_text"] == ""
    assert row["pipeline_stage"] == "scrape_failed"


# ---------------------------------------------------------------------------
# get_scrape_counts
# ---------------------------------------------------------------------------

def test_get_scrape_counts_returns_correct_values(tmp_db: Path) -> None:
    _seed_filtered(tmp_db, [
        _make_filtered_record("a.de"),
        _make_filtered_record("b.de"),
        _make_filtered_record("c.de"),
    ])
    ts = datetime.now(timezone.utc).isoformat()
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_scrape_result(conn, "a.de", scraped_text="text", scraped_at=ts)
        pipeline_db.update_scrape_result(conn, "b.de", scraped_text="", scraped_at=ts)
    counts = pipeline_db.get_scrape_counts(tmp_db)
    assert counts["scraped"] == 1
    assert counts["failed"] == 1
    assert counts["pending"] == 1


# ---------------------------------------------------------------------------
# scrape_batch_cmd tests (mock HTTP, real DB + KB)
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
from src.pipeline.scrape import scrape_batch_cmd
from src.config.profile import (
    IndustryProfile, FilterConfig, DiscoveryConfig,
    ClassificationConfig, OwnershipConfig, ExportConfig,
)


def _make_profile() -> IndustryProfile:
    return IndustryProfile(
        id="test",
        name="Test",
        description="",
        geography={},
        discovery=DiscoveryConfig(wlw_search_terms=[]),
        filters=FilterConfig(ma_min=5, ma_max=100, name_exclude_keywords=[]),
        classification=ClassificationConfig(target_description="", class_definitions={}),
        ownership=OwnershipConfig(),
        export=ExportConfig(),
    )


def test_scrape_dry_run_writes_nothing(tmp_db: Path, tmp_path: Path) -> None:
    """dry_run=True must not write to DB or KB."""
    _seed_filtered(tmp_db, [_make_filtered_record("example.de")])
    kb_path = tmp_path / "kb.db"
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch:
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        mock_fetch.return_value = "some scraped text"
        scrape_batch_cmd(_make_profile(), dry_run=True, limit=0)
        mock_fetch.assert_not_called()
    # DB unchanged — still at filtered
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 1


def test_scrape_uses_cache_when_available(tmp_db: Path, tmp_path: Path) -> None:
    """Cache hit must not call extract_page_text."""
    _seed_filtered(tmp_db, [_make_filtered_record("cached.de")])
    kb_path = tmp_path / "kb.db"
    from src.utils.knowledge_base import KnowledgeBase
    kb = KnowledgeBase(kb_path)
    kb.save_scraped_text("cached.de", "cached text", http_status=200, source_urls=["https://cached.de"])
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch:
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=0)
        mock_fetch.assert_not_called()
    # DB updated from cache — no longer at filtered
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 0


def test_scrape_fetches_on_cache_miss(tmp_db: Path, tmp_path: Path) -> None:
    """Cache miss must call extract_page_text and write result to DB and KB."""
    _seed_filtered(tmp_db, [_make_filtered_record("fresh.de")])
    kb_path = tmp_path / "kb.db"
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch, \
         patch("src.pipeline.scrape.time.sleep"):
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        mock_fetch.return_value = "fresh scraped text"
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=0)
        mock_fetch.assert_called_once_with("fresh.de")
    # Stage advanced to scraped
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT pipeline_stage, scraped_text FROM company_records WHERE domain='fresh.de'"
        ).fetchone()
    assert row["pipeline_stage"] == "scraped"
    assert row["scraped_text"] == "fresh scraped text"
    # Also written to KB
    from src.utils.knowledge_base import KnowledgeBase
    kb = KnowledgeBase(kb_path)
    assert kb.get_scraped_text("fresh.de") == "fresh scraped text"


def test_scrape_failed_domain_sets_scrape_failed_stage(tmp_db: Path, tmp_path: Path) -> None:
    """Domain returning empty text → pipeline_stage='scrape_failed'."""
    _seed_filtered(tmp_db, [_make_filtered_record("dead.de")])
    kb_path = tmp_path / "kb.db"
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch, \
         patch("src.pipeline.scrape.time.sleep"):
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        mock_fetch.return_value = ""
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=0)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT pipeline_stage FROM company_records WHERE domain='dead.de'"
        ).fetchone()
    assert row["pipeline_stage"] == "scrape_failed"


def test_scrape_limit_respected(tmp_db: Path, tmp_path: Path) -> None:
    """--limit N processes at most N records."""
    _seed_filtered(tmp_db, [
        _make_filtered_record("a.de"),
        _make_filtered_record("b.de"),
        _make_filtered_record("c.de"),
    ])
    kb_path = tmp_path / "kb.db"
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch, \
         patch("src.pipeline.scrape.time.sleep"):
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        mock_fetch.return_value = "text"
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=2)
        assert mock_fetch.call_count == 2


def test_scrape_idempotent(tmp_db: Path, tmp_path: Path) -> None:
    """Running scrape twice: second run finds nothing to do."""
    _seed_filtered(tmp_db, [_make_filtered_record("a.de")])
    kb_path = tmp_path / "kb.db"
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch, \
         patch("src.pipeline.scrape.time.sleep"):
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        mock_fetch.return_value = "text"
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=0)
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=0)
        assert mock_fetch.call_count == 1  # second run skipped
