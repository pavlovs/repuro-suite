# M5: Website Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For each `pipeline_stage='filtered'` record in `pipeline.db`, fetch and store the company website text. Cache results in `knowledge_base.db` (TTL 90 days). Advance passing records to `pipeline_stage='scraped'`.

**Architecture:** All scraping infrastructure already exists in `src/utils/`. M5 wires it to the pipeline DB — no new HTTP logic needed. No staging CSV — `pipeline.db` is the state store throughout.

**Tech Stack:** Python 3.11+, sqlite3 (stdlib), `src.utils.web.extract_page_text`, `src.utils.knowledge_base.KnowledgeBase`, `src.pipeline.db`

---

## Context

M4 delivered: `pipeline.db` with 1,596 records at `pipeline_stage='filtered'` — these passed all hard filters and are ready to scrape.

M5 delivers:
- `scraped_text` populated for all filtered records (empty string if domain unreachable)
- `scraped_at` timestamp set for every processed record
- `pipeline_stage='scraped'` set on records with non-empty scraped text
- `pipeline_stage='scrape_failed'` set on records where domain returned no text
- `python pipeline.py scrape --dry-run --limit 5` runs without error
- `python pipeline.py scrape --limit 10` hits 10 live domains and populates DB
- `python pipeline.py status` shows M5 scraped count

M6 (AI classifier) will query `WHERE pipeline_stage='scraped'` — only successfully scraped records get classified.

**No staging CSV.** `pipeline.db` is the sole state store. `knowledge_base.db` is the persistent HTTP cache.

---

## Key Design Decisions

1. **Cache-first**: Always check `knowledge_base.get_scraped_text(domain)` before any HTTP call. Cache hit → write to DB, advance stage, no HTTP.
2. **Polite delay**: 0.5s between HTTP calls. Never between cache hits (no network cost).
3. **Empty text = scrape_failed**: If `extract_page_text` returns empty string (domain unreachable, all pages 404/timeout), record `scraped_at` but set `pipeline_stage='scrape_failed'`. M6 can optionally retry or classify with empty input.
4. **Idempotent**: Query `WHERE pipeline_stage='filtered'` — already-scraped records (stage='scraped' or 'scrape_failed') are never re-processed.
5. **`--limit N`**: Always test with `--limit 5` or `--limit 10` against live sites before full run (~1,596 domains).

---

## New DB stage constant

Add to `src/pipeline/db.py` constants block:

```python
STAGE_SCRAPE_FAILED = "scrape_failed"
```

---

## Files to Create / Modify

| File | Action | Change |
|------|--------|--------|
| `src/pipeline/db.py` | Modify | Add `STAGE_SCRAPE_FAILED` constant, `get_records_for_scrape()`, `update_scrape_result()`, `get_scrape_counts()` |
| `src/pipeline/scrape.py` | Modify | Replace stub with full `scrape_batch_cmd()` |
| `tests/test_scrape.py` | Create | Unit tests for DB helpers and scrape logic |

No changes to `pipeline.py`, `settings.py`, `models.py`, or `profile.py` — the `scrape` command dispatch already exists.

---

## Task 1: Add DB helpers to `db.py`

- [ ] **Step 1.1: Write failing tests for DB helpers**

Create `tests/test_scrape.py`:

```python
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
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_scrape.py -v 2>&1 | tail -15
```
Expected: `AttributeError: module 'src.pipeline.db' has no attribute 'get_records_for_scrape'`

- [ ] **Step 1.3: Add `STAGE_SCRAPE_FAILED` constant and DB helpers to `db.py`**

Add `STAGE_SCRAPE_FAILED = "scrape_failed"` to the constants block after `STAGE_SCRAPED`.

Append to end of `src/pipeline/db.py`:

```python

def get_records_for_scrape(db_path: Path) -> list[CompanyRecord]:
    """Return all records at pipeline_stage='filtered' (not yet scraped)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM company_records WHERE pipeline_stage = 'filtered'"
        ).fetchall()
    return [_row_to_company_record(row) for row in rows]


def update_scrape_result(
    conn: sqlite3.Connection,
    domain: str,
    scraped_text: str,
    scraped_at: str,
) -> None:
    """Write scrape result for one record. Advances stage to 'scraped' if text non-empty."""
    new_stage = STAGE_SCRAPED if scraped_text else STAGE_SCRAPE_FAILED
    conn.execute(
        """
        UPDATE company_records
        SET scraped_text = ?, scraped_at = ?, pipeline_stage = ?
        WHERE domain = ?
        """,
        (scraped_text, scraped_at, new_stage, domain),
    )


def get_scrape_counts(db_path: Path) -> dict[str, int]:
    """Return {scraped: N, failed: N, pending: N} for status display."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN pipeline_stage = 'scraped'       THEN 1 ELSE 0 END),
                SUM(CASE WHEN pipeline_stage = 'scrape_failed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN pipeline_stage = 'filtered'      THEN 1 ELSE 0 END)
            FROM company_records
            """
        ).fetchone()
    return {"scraped": row[0] or 0, "failed": row[1] or 0, "pending": row[2] or 0}
```

- [ ] **Step 1.4: Run tests to confirm they pass**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_scrape.py -v
```
Expected: all PASS

- [ ] **Step 1.5: Run full suite — no regressions**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all PASS

- [ ] **Step 1.6: Commit**

```bash
cd REPURO/lead-pipeline && git add src/pipeline/db.py tests/test_scrape.py && git commit -m "feat(M5): add get_records_for_scrape, update_scrape_result, get_scrape_counts DB helpers"
```

---

## Task 2: Add scrape_batch_cmd tests

- [ ] **Step 2.1: Append scrape logic tests to `tests/test_scrape.py`**

Append to `tests/test_scrape.py`:

```python
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
    # DB unchanged
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 1  # still at filtered, nothing written


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
    # DB updated from cache
    records = pipeline_db.get_records_for_scrape(tmp_db)
    assert len(records) == 0  # consumed from filtered


def test_scrape_fetches_on_cache_miss(tmp_db: Path, tmp_path: Path) -> None:
    """Cache miss must call extract_page_text and write result to DB and KB."""
    _seed_filtered(tmp_db, [_make_filtered_record("fresh.de")])
    kb_path = tmp_path / "kb.db"
    with patch("src.pipeline.scrape.settings") as mock_settings, \
         patch("src.pipeline.scrape.extract_page_text") as mock_fetch, \
         patch("src.pipeline.scrape.time.sleep"):  # suppress delay in tests
        mock_settings.PIPELINE_DB_PATH = tmp_db
        mock_settings.KNOWLEDGE_BASE_PATH = kb_path
        mock_fetch.return_value = "fresh scraped text"
        scrape_batch_cmd(_make_profile(), dry_run=False, limit=0)
        mock_fetch.assert_called_once_with("fresh.de")
    # Stage advanced
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
```

- [ ] **Step 2.2: Run to confirm they fail**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_scrape.py -v 2>&1 | tail -15
```
Expected: `NotImplementedError` from the stub in `scrape.py`

---

## Task 3: Implement `scrape_batch_cmd` in `scrape.py`

- [ ] **Step 3.1: Replace stub with full implementation**

Replace entire contents of `src/pipeline/scrape.py`:

```python
"""Website scraper (M5). Fetches and caches company homepage text for classification."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline import db as pipeline_db
from src.utils.knowledge_base import KnowledgeBase
from src.utils.web import extract_page_text

logger = logging.getLogger(__name__)

_POLITE_DELAY_S = 0.5  # seconds between HTTP calls — never between cache hits


def scrape_batch_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Path | None = None,
    kb_path: Path | None = None,
) -> int:
    """
    Scrape company websites for all filtered records in pipeline.db.
    - Cache hit (knowledge_base TTL 90 days) → write to DB, no HTTP call.
    - Cache miss → fetch with extract_page_text → save to KB → write to DB.
    - Empty text → pipeline_stage='scrape_failed'.
    - Non-empty text → pipeline_stage='scraped'.
    Returns count of successfully scraped records.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    records = pipeline_db.get_records_for_scrape(db_path)
    if limit > 0:
        records = records[:limit]

    total = len(records)
    logger.info("Scrape: %d filtered records to process (limit=%d)", total, limit)

    if dry_run:
        logger.info("DRY RUN — would scrape %d records (no HTTP, no writes)", total)
        return 0

    if not records:
        logger.info("Scrape: nothing to do (no filtered records remaining)")
        return 0

    kb = KnowledgeBase(kb_path)
    scraped = 0
    failed = 0
    http_calls = 0

    for i, rec in enumerate(records, 1):
        domain = rec.domain
        now = datetime.now(timezone.utc).isoformat()

        # --- Cache check ---
        cached_text = kb.get_scraped_text(domain, max_age_days=90)
        if cached_text is not None:
            text = cached_text
            logger.debug("[%d/%d] CACHE HIT: %s (%d chars)", i, total, domain, len(text))
        else:
            # --- Live fetch ---
            text = extract_page_text(domain)
            kb.save_scraped_text(domain, text, http_status=200 if text else 0)
            http_calls += 1
            if http_calls > 1:
                time.sleep(_POLITE_DELAY_S)
            if text:
                logger.debug("[%d/%d] SCRAPED: %s (%d chars)", i, total, domain, len(text))
            else:
                logger.debug("[%d/%d] FAILED: %s (no text returned)", i, total, domain)

        # --- Write to DB ---
        with pipeline_db.get_connection(db_path) as conn:
            pipeline_db.update_scrape_result(conn, domain, text, now)

        if text:
            scraped += 1
        else:
            failed += 1

        # Progress log every 50
        if i % 50 == 0:
            logger.info(
                "Scrape progress: %d/%d — %d scraped, %d failed, %d HTTP calls",
                i, total, scraped, failed, http_calls,
            )

    logger.info(
        "Scrape complete: %d scraped, %d failed, %d HTTP calls made",
        scraped, failed, http_calls,
    )
    return scraped
```

- [ ] **Step 3.2: Run all scrape tests**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_scrape.py -v
```
Expected: all PASS

- [ ] **Step 3.3: Run full test suite**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all PASS

- [ ] **Step 3.4: Commit**

```bash
cd REPURO/lead-pipeline && git add src/pipeline/scrape.py tests/test_scrape.py && git commit -m "feat(M5): implement scrape_batch_cmd — KB-cached website scraper"
```

---

## Task 4: End-to-end validation

- [ ] **Step 4.1: Dry-run — no writes, no HTTP**

```bash
cd REPURO/lead-pipeline && python pipeline.py scrape --dry-run
```
Expected: `DRY RUN — would scrape 1596 records (no HTTP, no writes)`

- [ ] **Step 4.2: Live run — 5 companies**

```bash
cd REPURO/lead-pipeline && python pipeline.py scrape --limit 5 --verbose
```
Expected: 5 HTTP calls, log shows scraped/failed counts, no errors.

- [ ] **Step 4.3: Verify DB updated**

```bash
cd REPURO/lead-pipeline && python pipeline.py status
```
Expected output includes `M5 Scraped` with count ≥ 1 (and possibly `scrape_failed` entries).

**Note:** `pipeline.py status` does not show `scrape_failed` in the label list — but `get_stage_counts` will capture it as a separate stage. Add it to the `stage_labels` in `cmd_status`:

```python
("scrape_failed",      "M5 Scrape failed  "),
```

after the `("scraped", ...)` entry.

- [ ] **Step 4.4: Check idempotency — run again with --limit 5**

```bash
cd REPURO/lead-pipeline && python pipeline.py scrape --limit 5 --verbose
```
Expected: `nothing to do` for those 5 domains (already scraped or failed). If any were `scrape_failed`, they are also skipped (by design — re-run not attempted automatically).

- [ ] **Step 4.5: Full test suite — final check**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all PASS

- [ ] **Step 4.6: Final commit**

```bash
cd REPURO/lead-pipeline && git add pipeline.py && git commit -m "feat(M5): show scrape_failed in pipeline status display"
```

---

## Validation Checklist

Before marking M5 complete:

- [ ] `pytest tests/` — all green
- [ ] `python pipeline.py scrape --dry-run` — no error, shows count
- [ ] `python pipeline.py scrape --limit 5 --verbose` — 5 real domains scraped/attempted
- [ ] `python pipeline.py scrape --limit 5` (second run) — idempotent, nothing re-processed
- [ ] `python pipeline.py status` — shows M5 Scraped and M5 Scrape failed counts
- [ ] 0.5s polite delay between HTTP calls (never between cache hits)
- [ ] Knowledge base has new entries after live run
- [ ] No hardcoded values — delay constant in `scrape.py`, TTL default in `knowledge_base.py`

---

## AI VALIDATION RESULTS

_To be filled in after execution._

```
pytest tests/ →
python pipeline.py scrape --dry-run →
python pipeline.py scrape --limit 5 --verbose →
python pipeline.py scrape --limit 5 (2nd run) →
python pipeline.py status →
Knowledge base entries after run →
```
