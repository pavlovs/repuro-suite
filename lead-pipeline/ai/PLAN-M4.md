# M4: Pre-qualification Filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply profile-driven hard filters to all ingested records in `pipeline.db`, setting `filter_pass`, `filter_reason`, and advancing passing records to `pipeline_stage='filtered'`.

**Architecture:** Read all unfiltered records from `pipeline.db`, evaluate 4 ordered rules against each record, write result back per record. No external APIs. No CSV output — DB is the state store throughout.

**Tech Stack:** Python 3.11+, sqlite3 (stdlib), src.config.profile.IndustryProfile, src.pipeline.db

---

## Context

M3 delivered: `pipeline.db` with `company_records` table. All records have `pipeline_stage='ingested'`. Fields populated at ingest: `already_approached`, `is_subsidiary`, `ma_count`, `full_name`.

M4 delivers:
- `filter_pass` set on every record (1 = pass, 0 = fail)
- `filter_reason` set on failed records (NULL on pass)
- `pipeline_stage='filtered'` set on passing records (failed records stay at `'ingested'`)
- `python pipeline.py filter` runs without error
- `python pipeline.py status` shows M4 filtered count

M5 (website scraper) will query `WHERE pipeline_stage='filtered'` — so only records that pass M4 get scraped.

---

## Hard Filter Rules (ordered cheapest-first)

| # | Rule | Condition | filter_reason |
|---|------|-----------|---------------|
| 1 | Already approached | `already_approached = 1` | `"already approached"` |
| 2 | Confirmed subsidiary | `is_subsidiary = 1` | `"confirmed subsidiary"` |
| 3 | Name keyword exclusion | `full_name.lower()` contains any keyword from `profile.filters.name_exclude_keywords` | `"name contains '{keyword}'"` |
| 4 | Employee size out of range | `ma_count IS NOT NULL AND (ma_count < profile.filters.ma_min OR ma_count > profile.filters.ma_max)` | `"ma_count {n} outside range {ma_min}-{ma_max}"` |

If none of the above match → `filter_pass=1`, `filter_reason=NULL`.

**Important:** records with `ma_count IS NULL` pass rule 4. Size is unknown — M6 classifier handles it later.

---

## Files to Create / Modify

| File | Action | Change |
|------|--------|--------|
| `src/pipeline/db.py` | Modify | Add `get_records_for_filter()`, `update_filter_result()`, `get_filter_counts()`, `_row_to_company_record()` |
| `src/pipeline/filter.py` | Modify | Replace stub with full `apply_hard_filters()` implementation |
| `pipeline.py` | Modify | Add filter breakdown to `cmd_status` |
| `tests/test_filter.py` | Create | Unit tests for all filter rules |

No new files. No changes to `settings.py`, `models.py`, or `profile.py`.

**Notes on intentional deviations from stub:**
- `apply_hard_filters` return type changes from `list[CompanyRecord]` to `int` (count of passing records). The DB is the state store — callers don't need the records list. `pipeline.py` dispatch discards the return value, so no change needed there.
- `nace_exclude` in `FilterConfig` is not implemented in M4 — no `nace_code` field exists in `CompanyRecord` or the DB schema. Deferred to a future milestone if NACE data is added.
- `_row_to_company_record` deserializes datetime fields (`scraped_at`, `classified_at`, `enriched_at`) from ISO strings. At M4 all three are NULL in the DB, but the helper must handle them correctly for reuse in M5+.

---

## Task 1: Add DB helpers to `db.py`

**Files:**
- Modify: `src/pipeline/db.py` (append after `get_klass_counts`)

- [ ] **Step 1.1: Write the failing tests for DB helpers**

Create `tests/test_filter.py`:

```python
"""Tests for M4 pre-qualification filter."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.pipeline import db as pipeline_db
from src.pipeline.models import CompanyRecord
from src.config.profile import FilterConfig, IndustryProfile, DiscoveryConfig, ClassificationConfig, OwnershipConfig, ExportConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    return db_path


def _make_record(
    domain: str,
    full_name: str = "Test GmbH",
    ma_count: int | None = 30,
    already_approached: bool = False,
    is_subsidiary: bool | None = None,
) -> CompanyRecord:
    return CompanyRecord(
        domain=domain,
        full_name=full_name,
        profile_id="medtech_germany",
        source="ORBIS",
        ma_count=ma_count,
        already_approached=already_approached,
        is_subsidiary=is_subsidiary,
    )


def _seed(db_path: Path, records: list[CompanyRecord]) -> None:
    with pipeline_db.get_connection(db_path) as conn:
        for rec in records:
            pipeline_db.upsert_company(conn, rec, "2026-01-01T00:00:00+00:00")


def _make_profile(
    ma_min: int = 5,
    ma_max: int = 100,
    name_exclude_keywords: list[str] | None = None,
) -> IndustryProfile:
    return IndustryProfile(
        id="test",
        name="Test",
        description="",
        geography={},
        discovery=DiscoveryConfig(wlw_search_terms=[]),
        filters=FilterConfig(
            ma_min=ma_min,
            ma_max=ma_max,
            name_exclude_keywords=name_exclude_keywords or [],
        ),
        classification=ClassificationConfig(
            target_description="",
            class_definitions={},
        ),
        ownership=OwnershipConfig(),
        export=ExportConfig(),
    )


# ---------------------------------------------------------------------------
# DB helper tests
# ---------------------------------------------------------------------------

def test_get_records_for_filter_returns_unfiltered(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de"), _make_record("b.de")])
    records = pipeline_db.get_records_for_filter(tmp_db)
    assert len(records) == 2


def test_get_records_for_filter_skips_already_filtered(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de"), _make_record("b.de")])
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_filter_result(conn, "a.de", filter_pass=True, filter_reason=None)
    records = pipeline_db.get_records_for_filter(tmp_db)
    assert len(records) == 1
    assert records[0].domain == "b.de"


def test_update_filter_result_pass_sets_stage(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de")])
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_filter_result(conn, "a.de", filter_pass=True, filter_reason=None)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason, pipeline_stage FROM company_records WHERE domain='a.de'").fetchone()
    assert row["filter_pass"] == 1
    assert row["filter_reason"] is None
    assert row["pipeline_stage"] == "filtered"


def test_update_filter_result_fail_keeps_stage(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de")])
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_filter_result(conn, "a.de", filter_pass=False, filter_reason="already approached")
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason, pipeline_stage FROM company_records WHERE domain='a.de'").fetchone()
    assert row["filter_pass"] == 0
    assert row["filter_reason"] == "already approached"
    assert row["pipeline_stage"] == "ingested"
```

- [ ] **Step 1.2: Run tests to confirm they fail**

Run from `REPURO/lead-pipeline/`:
```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_filter.py::test_get_records_for_filter_returns_unfiltered tests/test_filter.py::test_update_filter_result_pass_sets_stage -v
```
Expected: `AttributeError: module 'src.pipeline.db' has no attribute 'get_records_for_filter'`

- [ ] **Step 1.3: Implement DB helpers in `db.py`**

Append to the end of `src/pipeline/db.py`:

```python

def get_records_for_filter(db_path: Path) -> list[CompanyRecord]:
    """Return all records not yet filtered (filter_pass IS NULL)."""
    from src.pipeline.models import CompanyRecord
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM company_records WHERE filter_pass IS NULL"
        ).fetchall()
    return [_row_to_company_record(row) for row in rows]


def update_filter_result(
    conn: sqlite3.Connection,
    domain: str,
    filter_pass: bool,
    filter_reason: str | None,
) -> None:
    """Write filter outcome for one record. Advances stage to 'filtered' if passing."""
    new_stage = STAGE_FILTERED if filter_pass else STAGE_INGESTED
    conn.execute(
        """
        UPDATE company_records
        SET filter_pass = ?, filter_reason = ?, pipeline_stage = ?
        WHERE domain = ?
        """,
        (1 if filter_pass else 0, filter_reason, new_stage, domain),
    )


def _row_to_company_record(row: sqlite3.Row) -> CompanyRecord:
    """Convert a sqlite3.Row from company_records to a CompanyRecord dataclass."""
    import dataclasses
    from datetime import datetime
    d = dict(row)
    # Convert INTEGER booleans back to Python bool / None
    for key in ("filter_pass", "is_subsidiary", "is_pe_backed", "service_flag",
                "distributor_flag", "ssb_flag", "ownership_pass"):
        val = d.get(key)
        d[key] = None if val is None else bool(val)
    d["already_approached"] = bool(d.get("already_approached", 0))
    # Deserialize datetime fields stored as ISO strings in the DB
    for key in ("scraped_at", "classified_at", "enriched_at"):
        val = d.get(key)
        if val and str(val) not in ("", "None"):
            try:
                d[key] = datetime.fromisoformat(str(val))
            except ValueError:
                d[key] = None
        else:
            d[key] = None
    # Remove id — recomputed by CompanyRecord.__post_init__
    d.pop("id", None)
    # Remove DB-only field not in CompanyRecord
    d.pop("ingested_at", None)
    valid_fields = {f.name for f in dataclasses.fields(CompanyRecord) if f.name != "id"}
    return CompanyRecord(**{k: d[k] for k in valid_fields if k in d})
```

- [ ] **Step 1.4: Run tests to confirm they pass**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_filter.py::test_get_records_for_filter_returns_unfiltered tests/test_filter.py::test_get_records_for_filter_skips_already_filtered tests/test_filter.py::test_update_filter_result_pass_sets_stage tests/test_filter.py::test_update_filter_result_fail_keeps_stage -v
```
Expected: 4 PASS

- [ ] **Step 1.5: Commit**

```bash
cd REPURO/lead-pipeline && git add src/pipeline/db.py tests/test_filter.py && git commit -m "feat(M4): add get_records_for_filter and update_filter_result DB helpers"
```

---

## Task 2: Filter rule unit tests

- [ ] **Step 2.1: Add filter rule tests to `tests/test_filter.py`**

Append to `tests/test_filter.py`:

```python
# ---------------------------------------------------------------------------
# Filter rule tests (test apply_hard_filters logic)
# ---------------------------------------------------------------------------

from src.pipeline.filter import apply_hard_filters


def test_filter_passes_normal_record(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("normal.de", "Medtech GmbH", ma_count=30)])
    profile = _make_profile(ma_min=5, ma_max=100)
    count = apply_hard_filters(profile, db_path=tmp_db)
    assert count == 1
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, pipeline_stage FROM company_records WHERE domain='normal.de'").fetchone()
    assert row["filter_pass"] == 1
    assert row["pipeline_stage"] == "filtered"


def test_filter_fails_already_approached(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("old.de", already_approached=True)])
    profile = _make_profile()
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason FROM company_records WHERE domain='old.de'").fetchone()
    assert row["filter_pass"] == 0
    assert row["filter_reason"] == "already approached"


def test_filter_fails_confirmed_subsidiary(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("sub.de", is_subsidiary=True)])
    profile = _make_profile()
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason FROM company_records WHERE domain='sub.de'").fetchone()
    assert row["filter_pass"] == 0
    assert row["filter_reason"] == "confirmed subsidiary"


def test_filter_fails_dental_keyword(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("dental.de", "Dental Depot GmbH")])
    profile = _make_profile(name_exclude_keywords=["dental", "zahn"])
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason FROM company_records WHERE domain='dental.de'").fetchone()
    assert row["filter_pass"] == 0
    assert "dental" in row["filter_reason"]


def test_filter_keyword_is_case_insensitive(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("z.de", "ZAHN-DEPOT GmbH")])
    profile = _make_profile(name_exclude_keywords=["zahn"])
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass FROM company_records WHERE domain='z.de'").fetchone()
    assert row["filter_pass"] == 0


def test_filter_fails_ma_too_small(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("tiny.de", ma_count=2)])
    profile = _make_profile(ma_min=5, ma_max=100)
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason FROM company_records WHERE domain='tiny.de'").fetchone()
    assert row["filter_pass"] == 0
    assert "2" in row["filter_reason"]
    assert "5" in row["filter_reason"]


def test_filter_fails_ma_too_large(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("huge.de", ma_count=200)])
    profile = _make_profile(ma_min=5, ma_max=100)
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass, filter_reason FROM company_records WHERE domain='huge.de'").fetchone()
    assert row["filter_pass"] == 0
    assert "200" in row["filter_reason"]


def test_filter_passes_null_ma_count(tmp_db: Path) -> None:
    """Records without ma_count must still pass the size filter."""
    _seed(tmp_db, [_make_record("unknown.de", ma_count=None)])
    profile = _make_profile(ma_min=5, ma_max=100)
    apply_hard_filters(profile, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass FROM company_records WHERE domain='unknown.de'").fetchone()
    assert row["filter_pass"] == 1


def test_filter_idempotent_pass(tmp_db: Path) -> None:
    """Running filter twice: passing record not re-processed on second run."""
    _seed(tmp_db, [_make_record("a.de")])
    profile = _make_profile()
    count1 = apply_hard_filters(profile, db_path=tmp_db)
    count2 = apply_hard_filters(profile, db_path=tmp_db)
    assert count1 == 1
    assert count2 == 0  # no unfiltered records remain


def test_filter_idempotent_fail(tmp_db: Path) -> None:
    """Running filter twice: failed record not re-processed on second run."""
    _seed(tmp_db, [_make_record("old.de", already_approached=True)])
    profile = _make_profile()
    count1 = apply_hard_filters(profile, db_path=tmp_db)
    count2 = apply_hard_filters(profile, db_path=tmp_db)
    assert count1 == 0
    assert count2 == 0  # failed record also skipped on re-run


def test_filter_dry_run_writes_nothing(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de")])
    profile = _make_profile()
    apply_hard_filters(profile, db_path=tmp_db, dry_run=True)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute("SELECT filter_pass FROM company_records WHERE domain='a.de'").fetchone()
    assert row["filter_pass"] is None  # not written
```

- [ ] **Step 2.2: Run to confirm they fail**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_filter.py -v 2>&1 | tail -20
```
Expected: `NotImplementedError` from the stub in `filter.py`

---

## Task 3: Implement `apply_hard_filters` in `filter.py`

**Files:**
- Modify: `src/pipeline/filter.py` (full replacement)

- [ ] **Step 3.1: Replace stub with full implementation**

Replace the entire contents of `src/pipeline/filter.py`:

```python
"""Pre-qualification filter (M4). Applies profile-driven hard filters to ingested records."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline import db as pipeline_db
from src.pipeline.models import CompanyRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filter rules — ordered cheapest first
# ---------------------------------------------------------------------------

def _check_already_approached(rec: CompanyRecord) -> Optional[str]:
    if rec.already_approached:
        return "already approached"
    return None


def _check_subsidiary(rec: CompanyRecord) -> Optional[str]:
    if rec.is_subsidiary is True:
        return "confirmed subsidiary"
    return None


def _check_name_keywords(rec: CompanyRecord, keywords: list[str]) -> Optional[str]:
    name_lower = rec.full_name.lower()
    for kw in keywords:
        if kw.lower() in name_lower:
            return f"name contains '{kw.lower()}'"
    return None


def _check_ma_count(rec: CompanyRecord, ma_min: int, ma_max: int) -> Optional[str]:
    if rec.ma_count is None:
        return None  # unknown size → pass
    if rec.ma_count < ma_min or rec.ma_count > ma_max:
        return f"ma_count {rec.ma_count} outside range {ma_min}-{ma_max}"
    return None


def _evaluate(rec: CompanyRecord, profile: IndustryProfile) -> tuple[bool, Optional[str]]:
    """Return (filter_pass, filter_reason) for a single record."""
    checks = [
        _check_already_approached(rec),
        _check_subsidiary(rec),
        _check_name_keywords(rec, profile.filters.name_exclude_keywords),
        _check_ma_count(rec, profile.filters.ma_min, profile.filters.ma_max),
    ]
    for reason in checks:
        if reason is not None:
            return False, reason
    return True, None


# ---------------------------------------------------------------------------
# Main filter command
# ---------------------------------------------------------------------------

def apply_hard_filters(
    profile: IndustryProfile,
    dry_run: bool = False,
    db_path: Path | None = None,
) -> int:
    """
    Apply profile-driven hard filters to all unfiltered records in pipeline.db.
    Sets filter_pass + filter_reason. Advances passing records to pipeline_stage='filtered'.
    Returns count of records that passed.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH

    records = pipeline_db.get_records_for_filter(db_path)
    logger.info("Filter: %d unfiltered records to process", len(records))

    if not records:
        logger.info("Filter: nothing to do (all records already filtered)")
        return 0

    pass_count = 0
    fail_count = 0

    if dry_run:
        for rec in records:
            passed, reason = _evaluate(rec, profile)
            if passed:
                pass_count += 1
            else:
                fail_count += 1
                logger.debug("DRY RUN — would fail: %s (%s)", rec.domain, reason)
        logger.info(
            "DRY RUN — would pass: %d, would fail: %d (no writes)",
            pass_count, fail_count,
        )
        return pass_count

    with pipeline_db.get_connection(db_path) as conn:
        for rec in records:
            passed, reason = _evaluate(rec, profile)
            pipeline_db.update_filter_result(conn, rec.domain, passed, reason)
            if passed:
                pass_count += 1
            else:
                fail_count += 1
                logger.debug("FAIL: %s — %s", rec.domain, reason)

    logger.info("Filter complete: %d passed, %d failed", pass_count, fail_count)
    return pass_count


def apply_ownership_gate(
    profile: IndustryProfile,
    dry_run: bool = False,
) -> list[CompanyRecord]:
    """Reclassify confirmed subsidiaries/PE-backed companies to D. Sets reclassify_reason."""
    raise NotImplementedError("apply_ownership_gate not implemented — M8")
```

- [ ] **Step 3.2: Run all filter tests**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/test_filter.py -v
```
Expected: all PASS

- [ ] **Step 3.3: Run full test suite**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/ -v
```
Expected: all PASS (no regressions)

- [ ] **Step 3.4: Commit**

```bash
cd REPURO/lead-pipeline && git add src/pipeline/filter.py tests/test_filter.py && git commit -m "feat(M4): implement apply_hard_filters — profile-driven pre-qualification filter"
```

---

## Task 4: Wire `pipeline.py status` counts + validate end-to-end

- [ ] **Step 4.1: Add `get_filter_counts` helper to `db.py`**

Append to `src/pipeline/db.py`:

```python

def get_filter_counts(db_path: Path) -> dict[str, int]:
    """Return {pass: N, fail: N, pending: N} for filter status display."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                SUM(CASE WHEN filter_pass = 1 THEN 1 ELSE 0 END) AS pass,
                SUM(CASE WHEN filter_pass = 0 THEN 1 ELSE 0 END) AS fail,
                SUM(CASE WHEN filter_pass IS NULL THEN 1 ELSE 0 END) AS pending
            FROM company_records
            """
        ).fetchone()
    return {"pass": rows[0] or 0, "fail": rows[1] or 0, "pending": rows[2] or 0}
```

- [ ] **Step 4.2: Update `cmd_status` in `pipeline.py` to show filter breakdown**

In `pipeline.py`, update `cmd_status` to show filter pass/fail after stage counts. Find this block:

```python
        if klass_counts:
            parts = "  ".join(f"{k}:{v}" for k, v in sorted(klass_counts.items()))
            print(f"\n  Classifications → {parts}")
```

Replace with:

```python
        if klass_counts:
            parts = "  ".join(f"{k}:{v}" for k, v in sorted(klass_counts.items()))
            print(f"\n  Classifications → {parts}")

        from src.pipeline.db import get_filter_counts
        fc = get_filter_counts(settings.PIPELINE_DB_PATH)
        if fc["pass"] or fc["fail"]:
            print(f"\n  M4 Filter results: {fc['pass']} passed / {fc['fail']} failed / {fc['pending']} pending")
```

- [ ] **Step 4.3: Run `python pipeline.py filter` (dry-run first)**

```bash
cd REPURO/lead-pipeline && python pipeline.py filter --dry-run
```
Expected: log output like `DRY RUN — would pass: N, would fail: N (no writes)`

- [ ] **Step 4.4: Run `python pipeline.py filter` (live)**

```bash
cd REPURO/lead-pipeline && python pipeline.py filter
```
Expected: log output like `Filter complete: N passed, N failed`

- [ ] **Step 4.5: Verify with status**

```bash
cd REPURO/lead-pipeline && python pipeline.py status
```
Expected output includes:
```
  M4 Filtered         N
  M4 Filter results: N passed / N failed / 0 pending
```

- [ ] **Step 4.6: Run full test suite**

```bash
cd REPURO/lead-pipeline && python -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 4.7: Final commit**

```bash
cd REPURO/lead-pipeline && git add src/pipeline/db.py pipeline.py && git commit -m "feat(M4): add filter status display and get_filter_counts helper"
```

---

## Validation Checklist

Before marking M4 complete:

- [ ] `pytest tests/` — all green
- [ ] `python pipeline.py filter --dry-run` — no error, shows would-pass/would-fail counts
- [ ] `python pipeline.py filter` — runs, shows passed/failed counts
- [ ] `python pipeline.py filter` (second run) — shows `nothing to do` (idempotent)
- [ ] `python pipeline.py status` — shows M4 stage count and filter breakdown
- [ ] No hardcoded filter values — all thresholds come from `profile.filters.*`
- [ ] `is_subsidiary=NULL` records pass rule 2 (unknown ≠ confirmed)
- [ ] `ma_count=NULL` records pass rule 4 (unknown size → pass)

---

## AI VALIDATION RESULTS

_To be filled in after execution._

```
pytest tests/ →
python pipeline.py filter --dry-run →
python pipeline.py filter →
python pipeline.py filter (2nd run) →
python pipeline.py status →
```
