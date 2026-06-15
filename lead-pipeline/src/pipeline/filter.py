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
    db_path: Optional[Path] = None,
) -> int:
    """
    Apply profile-driven hard filters to all unfiltered records in pipeline.db.
    Sets filter_pass + filter_reason. Advances passing records to pipeline_stage='filtered'.
    Returns count of records that passed.

    Note: return type is int (pass count), not list[CompanyRecord] — the DB is the state
    store. pipeline.py dispatch discards the return value so this is backward-compatible.
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
