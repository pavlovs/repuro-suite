"""Website scraper (M5). Fetches and caches company homepage text for classification."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import settings
from src.config.profile import IndustryProfile, ScrapeConfig
from src.pipeline import db as pipeline_db
from src.utils.knowledge_base import KnowledgeBase
from src.utils.web import extract_page_text, fetch_about_page_text, fetch_impressum_text

logger = logging.getLogger(__name__)

_POLITE_DELAY_S = 0.5  # seconds between HTTP calls — never between cache hits
_OEM_USABLE_CHARS = 200  # M37: text shorter than this counts as "no usable text"


def _page_kwargs(cfg: ScrapeConfig) -> dict:
    """extract_page_text kwargs for a profile. Ambulatory defaults reproduce the old call."""
    return {
        "extra_paths": cfg.extra_paths,
        "max_chars": cfg.max_chars,
        "homepage_min_chars": cfg.homepage_min_chars,
        "homepage_max_chars": cfg.homepage_max_chars,
        "path_max_chars": cfg.path_max_chars,
        "skip_duplicate_pages": cfg.skip_duplicate_pages,
        "link_keywords": cfg.link_keywords,
        "max_link_pages": cfg.max_link_pages,
    }


def fetch_site_text(domain: str, cfg: ScrapeConfig) -> str:
    """M37: live fetch of homepage + profile paths + about page, capped at cfg.max_chars.

    Used by the OEM target scrape and the fixture check. No cache, no DB.
    """
    text = extract_page_text(domain, **_page_kwargs(cfg))
    if text and len(text) < cfg.max_chars:
        about_text, about_suffix = fetch_about_page_text(domain)
        if about_text and about_text[:200] not in text:
            text = f"{text}\n\n--- ABOUT PAGE ({about_suffix}) ---\n\n{about_text}"
    return text[: cfg.max_chars]


def scrape_batch_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Path | None = None,
    kb_path: Path | None = None,
    source: str | None = None,
) -> int:
    """
    Scrape company websites for records in pipeline.db.

    Default: scrape all pipeline_stage='filtered' records (advances stage).
    With --source: scrape all records matching that source that lack scraped_text
    (updates scraped_text in place, does NOT change pipeline_stage).

    Returns count of successfully scraped records.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    if source:
        with pipeline_db.get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM company_records WHERE source = ? AND scraped_text IS NULL",
                (source,),
            ).fetchall()
        records = [pipeline_db._row_to_company_record(row) for row in rows]
    else:
        records = pipeline_db.get_records_for_scrape(db_path)
    if limit > 0:
        records = records[:limit]

    total = len(records)
    label = f"source={source}" if source else "filtered"
    logger.info("Scrape: %d %s records to process (limit=%d)", total, label, limit)

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

        try:
            # --- Cache check ---
            cached_text = kb.get_scraped_text(domain, max_age_days=90)
            if cached_text is not None:
                text = cached_text
                logger.debug(
                    "[%d/%d] CACHE HIT: %s (%d chars)", i, total, domain, len(text)
                )
            else:
                # --- Live fetch ---
                # ambulatory profile (default ScrapeConfig): the pre-M37 call, unchanged
                text = (
                    extract_page_text(domain)
                    if profile.scrape == ScrapeConfig()
                    else extract_page_text(domain, **_page_kwargs(profile.scrape))
                )
                kb.save_scraped_text(domain, text, http_status=200 if text else 0)
                http_calls += 1
                if http_calls > 1:
                    time.sleep(_POLITE_DELAY_S)
                if text:
                    logger.debug(
                        "[%d/%d] SCRAPED: %s (%d chars)", i, total, domain, len(text)
                    )
                else:
                    logger.debug(
                        "[%d/%d] FAILED: %s (no text returned)", i, total, domain
                    )

                # --- About page discovery (only on live fetch with content) ---
                if text:
                    about_text, about_suffix = fetch_about_page_text(domain)
                    if about_text:
                        text = f"{text}\n\n--- ABOUT PAGE ({about_suffix}) ---\n\n{about_text}"
                        http_calls += 1
                        logger.debug(
                            "[%d/%d] ABOUT: %s matched %s (%d chars)",
                            i,
                            total,
                            domain,
                            about_suffix,
                            len(about_text),
                        )
                    else:
                        http_calls += 1  # attempts were made even if none matched

            # --- Write to DB ---
            with pipeline_db.get_connection(db_path) as conn:
                if source:
                    conn.execute(
                        "UPDATE company_records SET scraped_text = ?, scraped_at = ? WHERE domain = ?",
                        (text, now, domain),
                    )
                else:
                    pipeline_db.update_scrape_result(conn, domain, text, now)

            if text:
                scraped += 1
            else:
                failed += 1

            # --- Impressum fetch (stored separately in KB documents table) ---
            if kb.get_document(domain, "impressum") is None:
                imp_text = fetch_impressum_text(domain)
                kb.save_document(
                    domain, hrb_number=None, doc_type="impressum", content=imp_text
                )
                http_calls += 1
                if http_calls > 1:
                    time.sleep(_POLITE_DELAY_S)
                if imp_text:
                    logger.debug(
                        "[%d/%d] IMPRESSUM: %s (%d chars)",
                        i,
                        total,
                        domain,
                        len(imp_text),
                    )
        except Exception:
            logger.warning(
                "[%d/%d] ERROR scraping %s — skipping", i, total, domain, exc_info=True
            )
            with pipeline_db.get_connection(db_path) as conn:
                if source:
                    conn.execute(
                        "UPDATE company_records SET scraped_text = '', scraped_at = ? WHERE domain = ?",
                        (now, domain),
                    )
                else:
                    pipeline_db.update_scrape_result(conn, domain, "", now)
            failed += 1

        # Progress log every 50
        if i % 50 == 0:
            logger.info(
                "Scrape progress: %d/%d — %d scraped, %d failed, %d HTTP calls",
                i,
                total,
                scraped,
                failed,
                http_calls,
            )

    logger.info(
        "Scrape complete: %d scraped, %d failed, %d HTTP calls made",
        scraped,
        failed,
        http_calls,
    )
    return scraped


@dataclass
class _OemFetchResult:
    domain: str
    text: str
    impressum: Optional[str]  # None = not fetched (already in KB)
    error: Optional[str] = None


def _oem_fetch_job(domain: str, cfg: ScrapeConfig, need_impressum: bool) -> _OemFetchResult:
    """Worker thread: HTTP only, no DB or KB writes. Polite delay per worker after the job."""
    try:
        text = fetch_site_text(domain, cfg)
        imp = fetch_impressum_text(domain) if need_impressum else None
        return _OemFetchResult(domain=domain, text=text, impressum=imp)
    except Exception as e:  # noqa: BLE001 — reported per domain, never fatal for the batch
        return _OemFetchResult(domain=domain, text="", impressum=None, error=repr(e)[:200])
    finally:
        time.sleep(_POLITE_DELAY_S)


def scrape_oem_targets_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Path | None = None,
    kb_path: Path | None = None,
    workers: int = 1,
) -> dict[str, int]:
    """M37: scrape OEM target records (no usable text, stage ingested/scrape_failed or BA11_src).

    HTTP runs in a thread pool of `workers`; every DB and KB write happens on the main thread.
    A cached text shorter than 200 chars is bypassed once (live retry). Writes only
    scraped_text, scraped_at and (ingested/scrape_failed only) pipeline_stage.
    Returns {"selected", "cache_hits", "scraped", "failed"}.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    records = pipeline_db.get_records_for_oem_scrape(db_path)
    if limit > 0:
        records = records[:limit]
    stats = {"selected": len(records), "cache_hits": 0, "scraped": 0, "failed": 0}
    logger.info(
        "OEM scrape: %d target records (limit=%d, workers=%d, paths=%s, cap=%d)",
        len(records),
        limit,
        workers,
        profile.scrape.extra_paths,
        profile.scrape.max_chars,
    )
    if dry_run:
        logger.info("DRY RUN — would scrape %d records (no HTTP, no writes)", len(records))
        return stats
    if not records:
        return stats

    kb = KnowledgeBase(kb_path)
    cfg = profile.scrape

    def _write(domain: str, text: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with pipeline_db.get_connection(db_path) as conn:
            pipeline_db.update_oem_scrape_result(conn, domain, text, now)
        if len(text) >= _OEM_USABLE_CHARS:
            stats["scraped"] += 1
        else:
            stats["failed"] += 1

    jobs: list[tuple[str, bool]] = []
    for rec in records:
        domain = rec["domain"]
        cached = kb.get_scraped_text(domain, max_age_days=90)
        if cached is not None and len(cached) >= _OEM_USABLE_CHARS:
            stats["cache_hits"] += 1
            _write(domain, cached)
            continue
        # cache empty or too short: one live retry (cache bypass)
        jobs.append((domain, kb.get_document(domain, "impressum") is None))

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_oem_fetch_job, d, cfg, need_imp) for d, need_imp in jobs]
        for fut in as_completed(futures):
            res = fut.result()
            done += 1
            if res.error:
                logger.warning("OEM scrape error %s: %s", res.domain, res.error)
            if res.text:
                kb.save_scraped_text(res.domain, res.text, http_status=200)
            if res.impressum is not None:
                kb.save_document(
                    res.domain, hrb_number=None, doc_type="impressum", content=res.impressum
                )
            _write(res.domain, res.text)
            if done % 25 == 0:
                logger.info(
                    "OEM scrape progress: %d/%d live — %d ok, %d failed",
                    done,
                    len(jobs),
                    stats["scraped"],
                    stats["failed"],
                )

    logger.info(
        "OEM scrape complete: %d selected, %d cache hits, %d usable, %d failed",
        stats["selected"],
        stats["cache_hits"],
        stats["scraped"],
        stats["failed"],
    )
    return stats


def ensure_scrape_for_briefaktion(
    db_path: Path | None = None,
    kb_path: Path | None = None,
    briefaktion: str | None = None,
) -> int:
    """Ensure every BA-assigned record has scraped_text + impressum in KB.

    Records entering via serienbriefe import or dashboard skip the normal
    scrape step. This function catches those gaps: any Prio 1 record with a
    briefaktion that is missing scraped_text or a KB impressum doc gets
    scraped and its impressum fetched.

    Returns count of records that were scraped/updated.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    with pipeline_db.get_connection(db_path) as conn:
        query = """
            SELECT domain FROM company_records
            WHERE briefaktion IS NOT NULL
              AND prio = 'Prio 1'
              AND (scraped_text IS NULL OR scraped_text = '')
        """
        params: list[str] = []
        if briefaktion:
            query += " AND briefaktion = ?"
            params.append(briefaktion)
        missing_scrape = {r["domain"] for r in conn.execute(query, params).fetchall()}

    kb = KnowledgeBase(kb_path)
    missing_impressum: set[str] = set()
    with pipeline_db.get_connection(db_path) as conn:
        query = """
            SELECT domain FROM company_records
            WHERE briefaktion IS NOT NULL
              AND prio = 'Prio 1'
        """
        params = []
        if briefaktion:
            query += " AND briefaktion = ?"
            params.append(briefaktion)
        all_ba = conn.execute(query, params).fetchall()
    for r in all_ba:
        if kb.get_document(r["domain"], "impressum") is None:
            missing_impressum.add(r["domain"])

    domains_to_process = missing_scrape | missing_impressum
    if not domains_to_process:
        logger.info("ensure_scrape: all BA records have scraped_text + impressum")
        return 0

    logger.info(
        "ensure_scrape: %d records need work (%d missing scrape, %d missing impressum)",
        len(domains_to_process),
        len(missing_scrape),
        len(missing_impressum),
    )

    updated = 0
    http_calls = 0
    now = datetime.now(timezone.utc).isoformat()

    for domain in sorted(domains_to_process):
        try:
            if domain in missing_scrape:
                cached_text = kb.get_scraped_text(domain, max_age_days=90)
                if cached_text is not None:
                    text = cached_text
                else:
                    text = extract_page_text(domain)
                    kb.save_scraped_text(domain, text, http_status=200 if text else 0)
                    http_calls += 1
                    if http_calls > 1:
                        time.sleep(_POLITE_DELAY_S)

                    if text:
                        about_text, about_suffix = fetch_about_page_text(domain)
                        if about_text:
                            text = f"{text}\n\n--- ABOUT PAGE ({about_suffix}) ---\n\n{about_text}"
                            http_calls += 1

                with pipeline_db.get_connection(db_path) as conn:
                    conn.execute(
                        "UPDATE company_records SET scraped_text = ?, scraped_at = ? WHERE domain = ?",
                        (text, now, domain),
                    )

            if domain in missing_impressum:
                imp_text = fetch_impressum_text(domain)
                kb.save_document(
                    domain, hrb_number=None, doc_type="impressum", content=imp_text
                )
                http_calls += 1
                if http_calls > 1:
                    time.sleep(_POLITE_DELAY_S)
                if imp_text:
                    logger.debug(
                        "ensure_scrape: IMPRESSUM %s (%d chars)", domain, len(imp_text)
                    )

            updated += 1
        except Exception:
            logger.warning(
                "ensure_scrape: error processing %s — skipping", domain, exc_info=True
            )

    logger.info(
        "ensure_scrape: %d/%d records updated, %d HTTP calls",
        updated,
        len(domains_to_process),
        http_calls,
    )
    return updated
