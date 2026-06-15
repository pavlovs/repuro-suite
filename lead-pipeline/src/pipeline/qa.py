"""Post-enrichment QA loop: detect and auto-fix data quality issues.

Runs after enrichment/normalization. For each BA record, checks:
  1. full_name == domain or empty → re-scrape impressum, extract name
  2. Missing street/plz_ort → re-try impressum parse
  3. Missing region_prep → derive from city via region_mapping
  4. No legal form in full_name → try OpenRegister official name

Designed to be idempotent — safe to run multiple times.
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional

from src.config import settings
from src.pipeline import db as pipeline_db
from src.pipeline.normalize import parse_impressum_address
from src.pipeline.region_lookup import lookup_region
from src.utils.knowledge_base import KnowledgeBase
from src.utils.web import fetch_impressum_text

logger = logging.getLogger(__name__)

_LEGAL_FORMS_RE = re.compile(
    r"GmbH|mbH|KGaA|KG|AG|e\.?\s*K\.|OHG|UG|GbR|SE\b|Ltd|Partnerschaft|PartG",
    re.IGNORECASE,
)

_POLITE_DELAY_S = 0.5

_COMPANY_NAME_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"(?:Firma|Firmenname|Anbieter|Betreiber|Diensteanbieter|Verantwortlich"
    r"|Angaben gemäß|Angaben gem(?:aess|äß)|Angaben nach"
    r"|Inhaber|Geschäftsführ)"
    r"[^:\n]{0,20}:\s*(.+?)(?:\n|$)"
    r")",
    re.IGNORECASE,
)

_IMPRESSUM_ENTITY_RE = re.compile(
    r"((?:[A-ZÄÖÜ][\w\-äöüß]*[\s&\.\-]+){0,6}"
    r"(?:GmbH|mbH|KG|AG|e\.?\s*K\.|OHG|UG|GbR|KGaA|SE)\b"
    r"(?:\s*&\s*Co\.?\s*(?:KG|OHG|KGaA))?)",
)

_MAX_NAME_LEN = 120


def _has_legal_form(name: str) -> bool:
    return bool(_LEGAL_FORMS_RE.search(name))


def _extract_company_name_from_text(text: str) -> Optional[str]:
    """Extract legal entity name from impressum text."""
    if not text:
        return None
    chunk = text[:3000]
    for m in _IMPRESSUM_ENTITY_RE.finditer(chunk):
        name = m.group(1).strip()
        if 5 < len(name) <= _MAX_NAME_LEN:
            return name
    m = _COMPANY_NAME_RE.search(chunk)
    if m:
        candidate = m.group(1).strip()
        if _has_legal_form(candidate) and 5 < len(candidate) <= _MAX_NAME_LEN:
            return candidate
    return None


def _try_openregister_name(domain: str, full_name: str) -> Optional[str]:
    """Try OpenRegister autocomplete to get official company name."""
    import httpx

    if not settings.OPENREGISTER_API_KEY:
        return None
    query = full_name if full_name and full_name != domain else domain.split(".")[0]
    url = f"{settings.OPENREGISTER_BASE_URL}/v1/autocomplete/company"
    try:
        resp = httpx.get(
            url,
            params={"query": query},
            headers={"Authorization": f"Bearer {settings.OPENREGISTER_API_KEY}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        results = resp.json().get("results", [])
        if not results:
            return None
        for r in results:
            name = r.get("name", "")
            if r.get("active") and _has_legal_form(name):
                core = query.lower().replace("-", " ").replace(".", "")
                name_lower = name.lower()
                words = [w for w in core.split() if len(w) >= 3]
                if words and all(
                    re.search(r"\b" + re.escape(w) + r"\b", name_lower) for w in words
                ):
                    return name
        return None
    except Exception as e:
        logger.warning("QA: OpenRegister autocomplete error for %r: %s", query, e)
        return None


def qa_fix_batch(
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
    briefaktion: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Auto-fix data quality issues in BA records.

    Returns summary dict with counts of issues found and fixed.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    kb = KnowledgeBase(kb_path)

    with pipeline_db.get_connection(db_path) as conn:
        q = """SELECT domain, full_name, street, plz_ort, city, region_prep,
                      scraped_text, impressum_name, gesellschafter_name, pipeline_stage
               FROM company_records
               WHERE prio = 'Prio 1' AND briefaktion IS NOT NULL"""
        params = []
        if briefaktion:
            q += " AND briefaktion = ?"
            params.append(briefaktion)
        records = conn.execute(q, params).fetchall()

    stats = {
        "total": len(records),
        "name_fixed": 0,
        "street_fixed": 0,
        "plz_fixed": 0,
        "region_fixed": 0,
        "impressum_rescraped": 0,
        "remaining_issues": [],
    }

    all_updates: list[tuple[str, dict]] = []

    for rec in records:
        domain = rec["domain"]
        updates: dict[str, str] = {}
        fn = rec["full_name"] or ""
        issues = []

        name_is_domain = fn == domain or not fn
        has_legal = _has_legal_form(fn) if fn and not name_is_domain else False
        name_needs_fix = name_is_domain or (fn and not has_legal)
        missing_street = not rec["street"]
        missing_plz = not rec["plz_ort"]
        missing_region = not rec["region_prep"]

        needs_work = name_needs_fix or missing_street or missing_plz or missing_region

        if not needs_work:
            continue

        # --- Step 1: Ensure we have impressum text ---
        imp_text = kb.get_document(domain, "impressum")
        if not imp_text and (name_needs_fix or missing_street or missing_plz):
            logger.info("QA: re-scraping impressum for %s", domain)
            imp_text = fetch_impressum_text(domain)
            if imp_text:
                kb.save_document(
                    domain, hrb_number=None, doc_type="impressum", content=imp_text
                )
                stats["impressum_rescraped"] += 1
                logger.info(
                    "QA: impressum re-scraped for %s (%d chars)", domain, len(imp_text)
                )
                time.sleep(_POLITE_DELAY_S)
            else:
                logger.debug("QA: impressum re-scrape failed for %s", domain)
                time.sleep(_POLITE_DELAY_S)

        # Also try scraped_text as fallback
        text_sources = [t for t in [imp_text, rec["scraped_text"]] if t]

        # --- Step 2: Fix company name ---
        if name_needs_fix:
            fixed_name = None
            for text in text_sources:
                fixed_name = _extract_company_name_from_text(text)
                if fixed_name:
                    break
            if not fixed_name:
                fixed_name = _try_openregister_name(domain, fn)
                time.sleep(_POLITE_DELAY_S)
            if fixed_name:
                updates["full_name"] = fixed_name
                stats["name_fixed"] += 1
                logger.info("QA: name fixed for %s: %r → %r", domain, fn, fixed_name)
            else:
                issues.append(
                    "name_no_legal_form"
                    if fn and not name_is_domain
                    else "name_is_domain"
                )

        # --- Step 3: Fix street/plz ---
        if missing_street or missing_plz:
            for text in text_sources:
                street, plz_ort = parse_impressum_address(text)
                if street and missing_street:
                    updates["street"] = street
                    stats["street_fixed"] += 1
                    missing_street = False
                if plz_ort and missing_plz:
                    updates["plz_ort"] = plz_ort
                    stats["plz_fixed"] += 1
                    missing_plz = False
                    parts = plz_ort.split(" ", 1)
                    if len(parts) == 2:
                        updates["city"] = parts[1]
                if not missing_street and not missing_plz:
                    break
            if missing_street:
                issues.append("no_street")
            if missing_plz:
                issues.append("no_plz")

        # --- Step 4: Fix region_prep ---
        city = updates.get("city", rec["city"]) or ""
        if not rec["region_prep"] and city:
            region, region_prep = lookup_region(city)
            if region_prep:
                updates["region"] = region
                updates["region_prep"] = region_prep
                stats["region_fixed"] += 1
            else:
                issues.append("no_region")
        elif not rec["region_prep"] and not city:
            issues.append("no_region")

        if updates:
            all_updates.append((domain, updates))
        if issues:
            stats["remaining_issues"].append(
                {
                    "domain": domain,
                    "full_name": updates.get("full_name", fn),
                    "issues": issues,
                }
            )

    # Apply updates
    if not dry_run and all_updates:
        with pipeline_db.get_connection(db_path) as conn:
            for domain, updates in all_updates:
                set_parts = [f"{k} = ?" for k in updates]
                values = list(updates.values()) + [domain]
                conn.execute(
                    f"UPDATE company_records SET {', '.join(set_parts)} WHERE domain = ?",
                    values,
                )
        logger.info(
            "QA: applied fixes to %d records (name=%d, street=%d, plz=%d, region=%d)",
            len(all_updates),
            stats["name_fixed"],
            stats["street_fixed"],
            stats["plz_fixed"],
            stats["region_fixed"],
        )

    remaining = stats["remaining_issues"]
    if remaining:
        logger.warning(
            "QA: %d records still have issues after auto-fix:", len(remaining)
        )
        for r in remaining:
            logger.warning(
                "  %s (%s): %s", r["domain"], r["full_name"], ", ".join(r["issues"])
            )

    return stats


def prepare_manual_names(
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
    briefaktion: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Pre-enrich step: fix full_name for MANUAL-source records before ownership enrichment.

    Targets records where full_name equals domain (no company name from import)
    or lacks a legal form suffix. Scrapes impressum and extracts legal entity name.

    Run BEFORE `enrich` to ensure OpenRegister gets a searchable company name.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    kb = KnowledgeBase(kb_path)

    with pipeline_db.get_connection(db_path) as conn:
        q = """SELECT domain, full_name, street, plz_ort, city, scraped_text
               FROM company_records
               WHERE source = 'MANUAL'
                 AND pipeline_stage = 'classified'"""
        params = []
        if briefaktion:
            q += " AND briefaktion = ?"
            params.append(briefaktion)
        records = conn.execute(q, params).fetchall()

    stats = {
        "total": len(records),
        "name_fixed": 0,
        "street_fixed": 0,
        "plz_fixed": 0,
        "skipped_ok": 0,
        "still_bad": [],
    }

    all_updates: list[tuple[str, dict]] = []

    for rec in records:
        domain = rec["domain"]
        fn = rec["full_name"] or ""
        name_is_domain = fn == domain or not fn
        has_legal = _has_legal_form(fn) if fn and not name_is_domain else False

        if not name_is_domain and has_legal:
            stats["skipped_ok"] += 1
            continue

        updates: dict[str, str] = {}

        # Fetch impressum
        imp_text = kb.get_document(domain, "impressum")
        if not imp_text:
            imp_text = fetch_impressum_text(domain)
            if imp_text:
                kb.save_document(
                    domain, hrb_number=None, doc_type="impressum", content=imp_text
                )
                logger.info(
                    "prepare-manual: fetched impressum for %s (%d chars)",
                    domain,
                    len(imp_text),
                )
            time.sleep(_POLITE_DELAY_S)

        text_sources = [t for t in [imp_text, rec["scraped_text"]] if t]

        # Extract company name
        fixed_name = None
        for text in text_sources:
            fixed_name = _extract_company_name_from_text(text)
            if fixed_name:
                break

        if not fixed_name:
            fixed_name = _try_openregister_name(domain, fn)
            time.sleep(_POLITE_DELAY_S)

        if fixed_name:
            updates["full_name"] = fixed_name
            stats["name_fixed"] += 1
            logger.info("prepare-manual: %s name %r → %r", domain, fn, fixed_name)
        else:
            stats["still_bad"].append({"domain": domain, "full_name": fn})

        # Also fix street/plz if missing
        missing_street = not rec["street"]
        missing_plz = not rec["plz_ort"]
        if missing_street or missing_plz:
            for text in text_sources:
                street, plz_ort = parse_impressum_address(text)
                if street and missing_street:
                    updates["street"] = street
                    stats["street_fixed"] += 1
                    missing_street = False
                if plz_ort and missing_plz:
                    updates["plz_ort"] = plz_ort
                    stats["plz_fixed"] += 1
                    missing_plz = False
                    parts = plz_ort.split(" ", 1)
                    if len(parts) == 2:
                        updates["city"] = parts[1]
                if not missing_street and not missing_plz:
                    break

        if updates:
            all_updates.append((domain, updates))

    if not dry_run and all_updates:
        with pipeline_db.get_connection(db_path) as conn:
            for domain, updates in all_updates:
                set_parts = [f"{k} = ?" for k in updates]
                values = list(updates.values()) + [domain]
                conn.execute(
                    f"UPDATE company_records SET {', '.join(set_parts)} WHERE domain = ?",
                    values,
                )

    dry = "(DRY RUN) " if dry_run else ""
    logger.info(
        "prepare-manual %scomplete: %d MANUAL records, %d names fixed, "
        "%d streets fixed, %d PLZ fixed, %d already OK, %d still need manual fix",
        dry,
        stats["total"],
        stats["name_fixed"],
        stats["street_fixed"],
        stats["plz_fixed"],
        stats["skipped_ok"],
        len(stats["still_bad"]),
    )
    if stats["still_bad"]:
        logger.warning(
            "prepare-manual: %d records still have bad names:", len(stats["still_bad"])
        )
        for r in stats["still_bad"]:
            logger.warning("  %s (full_name=%r)", r["domain"], r["full_name"])

    return stats
