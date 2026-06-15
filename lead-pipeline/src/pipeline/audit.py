"""M12 — Dedup audit: detect and optionally fix already-approached companies that slipped
through ingest dedup (e.g. due to domain changes).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import openpyxl

from src.config import settings
from src.pipeline import db as pipeline_db
from src.pipeline.ingest import _normalize_company_name, _read_serienbriefe_dedup

logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    serienbriefe_domains: int
    serienbriefe_names: int
    records_checked: int
    matched: list[
        dict
    ]  # each: {domain, full_name, klass, pipeline_stage, match_reason}
    fixed: int  # 0 if dry_run or --fix not passed


def audit_dedup(
    dry_run: bool = False,
    fix: bool = False,
    output_path: Optional[Path] = None,
) -> AuditResult:
    """Cross-check pipeline.db unapproached records against Serienbriefe reference.

    Args:
        dry_run: If True, do not apply any DB writes even if fix=True.
        fix:     If True (and not dry_run), update matched records in pipeline.db.
        output_path: If given, write matched records to this CSV path.

    Returns:
        AuditResult with counts and matched records list.
    """
    # 1. Load Serienbriefe reference
    if not settings.SOURCE_EXCEL.exists():
        raise FileNotFoundError(
            f"Source Excel not found: {settings.SOURCE_EXCEL}. "
            "Cannot run dedup audit without Serienbriefe reference."
        )

    logger.info("Loading Serienbriefe reference from %s …", settings.SOURCE_EXCEL.name)
    wb = openpyxl.load_workbook(settings.SOURCE_EXCEL, read_only=True, data_only=True)
    try:
        approached_domains, name_index = _read_serienbriefe_dedup(
            wb[settings.SERIENBRIEFE_SHEET]
        )
    finally:
        wb.close()

    logger.info(
        "Serienbriefe: %d domains, %d name-index entries",
        len(approached_domains),
        len(name_index),
    )

    # 2. Load all unapproached records from pipeline.db
    if not settings.PIPELINE_DB_PATH.exists():
        raise FileNotFoundError(
            f"pipeline.db not found: {settings.PIPELINE_DB_PATH}. Run ingest first."
        )

    unapproached = pipeline_db.get_unapproached_for_audit(settings.PIPELINE_DB_PATH)
    logger.info("Records to check (already_approached=0): %d", len(unapproached))

    # 3. Check each record
    matched: list[dict] = []
    for rec in unapproached:
        domain: str = rec["domain"]
        full_name: str = rec["full_name"] or ""
        match_reason: Optional[str] = None

        if domain in approached_domains:
            match_reason = f"domain match: {domain}"
        else:
            name_key = _normalize_company_name(full_name)
            if name_key and len(name_key) >= 4 and name_key in name_index:
                sb_domain = name_index[name_key]
                match_reason = f"name match: '{full_name}' → {sb_domain}"

        if match_reason:
            matched.append(
                {
                    "domain": domain,
                    "full_name": full_name,
                    "klass": rec.get("klass") or "",
                    "pipeline_stage": rec.get("pipeline_stage") or "",
                    "match_reason": match_reason,
                }
            )

    logger.info("Unflagged matches found: %d", len(matched))

    # 4. Optional CSV output
    if output_path and matched:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "domain",
                    "full_name",
                    "klass",
                    "pipeline_stage",
                    "match_reason",
                ],
            )
            writer.writeheader()
            writer.writerows(matched)
        logger.info("Audit CSV written: %s (%d rows)", output_path, len(matched))

    # 5. Fix mode
    fixed = 0
    if fix and not dry_run and matched:
        domains_to_fix = [m["domain"] for m in matched]
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            fixed = pipeline_db.fix_approached_bulk(conn, domains_to_fix)
        logger.info(
            "Fixed: %d records marked already_approached=1, outreach_status='sent'",
            fixed,
        )
    elif fix and dry_run:
        logger.info("DRY RUN — would fix %d records (skipping DB write)", len(matched))

    return AuditResult(
        serienbriefe_domains=len(approached_domains),
        serienbriefe_names=len(name_index),
        records_checked=len(unapproached),
        matched=matched,
        fixed=fixed,
    )
