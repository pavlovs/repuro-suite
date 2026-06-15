"""Tests for M4 pre-qualification filter."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from src.pipeline import db as pipeline_db
from src.pipeline.filter import _evaluate, apply_hard_filters
from src.pipeline.models import CompanyRecord
from src.config.profile import (
    FilterConfig,
    IndustryProfile,
    DiscoveryConfig,
    ClassificationConfig,
    OwnershipConfig,
    ExportConfig,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    pipeline_db.ensure_schema(db_path)
    return db_path


def _make_record(
    domain: str,
    full_name: str = "Test GmbH",
    ma_count: Optional[int] = 30,
    already_approached: bool = False,
    is_subsidiary: Optional[bool] = None,
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
    name_exclude_keywords: Optional[list[str]] = None,
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
        row = conn.execute(
            "SELECT filter_pass, filter_reason, pipeline_stage FROM company_records WHERE domain='a.de'"
        ).fetchone()
    assert row["filter_pass"] == 1
    assert row["filter_reason"] is None
    assert row["pipeline_stage"] == "filtered"


def test_update_filter_result_fail_keeps_stage(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de")])
    with pipeline_db.get_connection(tmp_db) as conn:
        pipeline_db.update_filter_result(conn, "a.de", filter_pass=False, filter_reason="already approached")
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass, filter_reason, pipeline_stage FROM company_records WHERE domain='a.de'"
        ).fetchone()
    assert row["filter_pass"] == 0
    assert row["filter_reason"] == "already approached"
    assert row["pipeline_stage"] == "ingested"


# ---------------------------------------------------------------------------
# Filter rule unit tests (pure function — no I/O)
# ---------------------------------------------------------------------------

def test_evaluate_passes_normal_record() -> None:
    rec = _make_record("normal.de", "Medtech GmbH", ma_count=30)
    passed, reason = _evaluate(rec, _make_profile())
    assert passed is True
    assert reason is None


def test_evaluate_fails_already_approached() -> None:
    rec = _make_record("old.de", already_approached=True)
    passed, reason = _evaluate(rec, _make_profile())
    assert passed is False
    assert reason == "already approached"


def test_evaluate_fails_confirmed_subsidiary() -> None:
    rec = _make_record("sub.de", is_subsidiary=True)
    passed, reason = _evaluate(rec, _make_profile())
    assert passed is False
    assert reason == "confirmed subsidiary"


def test_evaluate_unknown_subsidiary_passes() -> None:
    rec = _make_record("unk.de", is_subsidiary=None)
    passed, reason = _evaluate(rec, _make_profile())
    assert passed is True


def test_evaluate_fails_dental_keyword() -> None:
    rec = _make_record("d.de", "Dental Depot GmbH")
    passed, reason = _evaluate(rec, _make_profile(name_exclude_keywords=["dental", "zahn"]))
    assert passed is False
    assert "dental" in reason


def test_evaluate_keyword_case_insensitive() -> None:
    rec = _make_record("z.de", "ZAHN-DEPOT GmbH")
    passed, reason = _evaluate(rec, _make_profile(name_exclude_keywords=["zahn"]))
    assert passed is False


def test_evaluate_fails_ma_too_small() -> None:
    rec = _make_record("tiny.de", ma_count=2)
    passed, reason = _evaluate(rec, _make_profile(ma_min=5, ma_max=100))
    assert passed is False
    assert "2" in reason and "5" in reason


def test_evaluate_fails_ma_too_large() -> None:
    rec = _make_record("huge.de", ma_count=200)
    passed, reason = _evaluate(rec, _make_profile(ma_min=5, ma_max=100))
    assert passed is False
    assert "200" in reason


def test_evaluate_passes_null_ma_count() -> None:
    rec = _make_record("unk.de", ma_count=None)
    passed, reason = _evaluate(rec, _make_profile(ma_min=5, ma_max=100))
    assert passed is True


# ---------------------------------------------------------------------------
# Integration tests — apply_hard_filters with pipeline.db
# ---------------------------------------------------------------------------

def test_filter_passes_normal_record(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("normal.de", "Medtech GmbH", ma_count=30)])
    count = apply_hard_filters(_make_profile(), db_path=tmp_db)
    assert count == 1
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass, pipeline_stage FROM company_records WHERE domain='normal.de'"
        ).fetchone()
    assert row["filter_pass"] == 1
    assert row["pipeline_stage"] == "filtered"


def test_filter_fails_already_approached(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("old.de", already_approached=True)])
    apply_hard_filters(_make_profile(), db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass, filter_reason FROM company_records WHERE domain='old.de'"
        ).fetchone()
    assert row["filter_pass"] == 0
    assert row["filter_reason"] == "already approached"


def test_filter_fails_confirmed_subsidiary(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("sub.de", is_subsidiary=True)])
    apply_hard_filters(_make_profile(), db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass, filter_reason FROM company_records WHERE domain='sub.de'"
        ).fetchone()
    assert row["filter_pass"] == 0
    assert row["filter_reason"] == "confirmed subsidiary"


def test_filter_fails_dental_keyword(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("dental.de", "Dental Depot GmbH")])
    apply_hard_filters(_make_profile(name_exclude_keywords=["dental"]), db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass, filter_reason FROM company_records WHERE domain='dental.de'"
        ).fetchone()
    assert row["filter_pass"] == 0
    assert "dental" in row["filter_reason"]


def test_filter_fails_ma_out_of_range(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("tiny.de", ma_count=2)])
    apply_hard_filters(_make_profile(ma_min=5, ma_max=100), db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass, filter_reason FROM company_records WHERE domain='tiny.de'"
        ).fetchone()
    assert row["filter_pass"] == 0
    assert "2" in row["filter_reason"]


def test_filter_passes_null_ma_count(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("unk.de", ma_count=None)])
    count = apply_hard_filters(_make_profile(), db_path=tmp_db)
    assert count == 1


def test_filter_idempotent(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de"), _make_record("old.de", already_approached=True)])
    count1 = apply_hard_filters(_make_profile(), db_path=tmp_db)
    count2 = apply_hard_filters(_make_profile(), db_path=tmp_db)
    assert count1 == 1
    assert count2 == 0  # both records already processed


def test_filter_dry_run_writes_nothing(tmp_db: Path) -> None:
    _seed(tmp_db, [_make_record("a.de")])
    apply_hard_filters(_make_profile(), dry_run=True, db_path=tmp_db)
    with pipeline_db.get_connection(tmp_db) as conn:
        row = conn.execute(
            "SELECT filter_pass FROM company_records WHERE domain='a.de'"
        ).fetchone()
    assert row["filter_pass"] is None
