"""WLW scraper — scrapes wlw.de by profile search terms.

Produces data/staging/00_wlw_raw.csv. Checks knowledge base before fetching
to avoid re-scraping already-seen domains.

URL structure (as of 2025):
  Search page 1: https://www.wlw.de/de/suche/{term}
  Search page N: https://www.wlw.de/de/suche/{term}/page/{N}
  Company profile: https://www.wlw.de/de/firma/{slug}-{id}

Company homepage URLs are embedded in the page's Nuxt state (window.__NUXT__),
directly adjacent to the WLW slug: '"{slug}","https://company.de/"'.
This is extracted via regex — no extra profile page visits needed.
"""
from __future__ import annotations

import csv
import logging
import re
import time
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline.models import CompanyRecord
from src.utils.knowledge_base import KnowledgeBase
from src.utils.web import fetch_with_retry

logger = logging.getLogger(__name__)

# WLW slug → homepage URL: the slug immediately precedes the URL in Nuxt state
# Pattern: "brune-medizintechnik-1303463","http://www.brune-medizintechnik.de/"
_NUXT_HOMEPAGE_RE = re.compile(r'"([a-z0-9][a-z0-9\-]+-\d+)","(https?://[^"]+)"')


def _parse_domain(url: str) -> Optional[str]:
    """Extract clean domain from a URL string. Returns None if unparseable."""
    if not url:
        return None
    url = url.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if url.startswith(prefix):
            url = url[len(prefix):]
    domain = url.split("/")[0].strip()
    return domain if domain and "." in domain else None


def _parse_employee_range(text: str) -> Optional[int]:
    """Parse WLW employee range string to lower-bound integer.

    "10-19" → 10, "20-49" → 20, "1-4" → 1, "500+" → 500
    Returns None if unparseable.
    """
    if not text:
        return None
    text = text.strip()
    m = re.match(r"(\d+)", text)
    return int(m.group(1)) if m else None


def _extract_nuxt_homepages(html: str) -> dict[str, str]:
    """Extract {wlw_slug: homepage_url} map from page Nuxt state.

    Falls back to empty dict if pattern not found.
    """
    result: dict[str, str] = {}
    for script in BeautifulSoup(html, "lxml").find_all("script"):
        text = script.string or ""
        if "ShallowReactive" not in text:
            continue
        for m in _NUXT_HOMEPAGE_RE.finditer(text):
            slug, url = m.group(1), m.group(2)
            result[slug] = url
        break  # Only the first matching script block
    return result


def _scrape_wlw_term(
    term: str,
    base_url: str,
    profile_id: str,
    dry_run: bool,
    max_pages: int,
    delay_sec: float,
) -> list[CompanyRecord]:
    """Scrape one WLW search term across all result pages."""
    records: list[CompanyRecord] = []
    seen_domains: set[str] = set()
    term_slug = term.replace(" ", "-").lower()
    # Page 1: /de/suche/{term}, Page N: /de/suche/{term}/page/{N}
    search_base = f"{base_url}/de/suche/{term_slug}"

    for page in range(1, max_pages + 1):
        url = search_base if page == 1 else f"{search_base}/page/{page}"
        logger.info("WLW [%s] page %d: %s", term, page, url)

        if dry_run:
            logger.info("DRY RUN — skipping HTTP fetch")
            break

        html = fetch_with_retry(url, retries=2, delay=1.0)
        if not html:
            logger.warning("No response for %s — stopping pagination", url)
            break

        soup = BeautifulSoup(html, "lxml")

        # Extract homepage URLs from Nuxt state (slug → URL map)
        slug_to_url = _extract_nuxt_homepages(html)
        if not slug_to_url:
            logger.warning("No Nuxt homepage data on page %d for '%s'", page, term)

        cards = soup.select("div.company-tile")
        if not cards:
            logger.info("No result cards on page %d — end of results for '%s'", page, term)
            break

        page_new = 0
        for card in cards:
            # Company name
            name_el = card.select_one("[data-test='company-name']")
            full_name = name_el.get_text(strip=True) if name_el else None
            if not full_name:
                continue

            # WLW profile path → extract slug (last path segment)
            wlw_href = name_el.get("href", "") if name_el else ""
            # e.g. /de/firma/brune-medizintechnik-1303463
            wlw_slug = wlw_href.rstrip("/").split("/")[-1] if wlw_href else None

            # Homepage URL from Nuxt state
            homepage_url = slug_to_url.get(wlw_slug, "") if wlw_slug else ""
            domain = _parse_domain(homepage_url)

            # Fallback: use WLW slug as synthetic domain placeholder
            if not domain and wlw_slug:
                domain = f"{wlw_slug}.wlw"
                logger.debug("No homepage for '%s' — using placeholder domain %s", full_name, domain)

            if not domain or domain in seen_domains:
                continue
            # Skip WLW's own domain (should not occur, but guard)
            if "wlw.de" in domain and ".wlw" not in domain:
                continue
            seen_domains.add(domain)

            # City
            city_el = card.select_one("span.city")
            city = city_el.get_text(strip=True) if city_el else None

            # Description
            desc_el = card.select_one("[data-test='description']")
            description = desc_el.get_text(strip=True)[:500] if desc_el else None

            # Employee range → lower bound
            emp_el = card.select_one("[data-test='employee-count']")
            emp_text = emp_el.get_text(strip=True) if emp_el else None
            ma_count = _parse_employee_range(emp_text)

            record = CompanyRecord(
                domain=domain,
                full_name=full_name,
                profile_id=profile_id,
                source="WLW",
                city=city,
                ma_count=ma_count,
                scraped_text=description,  # short WLW teaser — not full website scrape
            )
            records.append(record)
            page_new += 1

        logger.info("  Page %d: %d new companies (running total: %d)", page, page_new, len(records))

        if page_new == 0:
            break

        time.sleep(delay_sec)

    return records


def scrape_wlw(
    profile: IndustryProfile,
    kb: Optional[KnowledgeBase] = None,
    dry_run: bool = False,
    verbose: bool = False,
    limit: int = 0,
) -> list[CompanyRecord]:
    """Scrape wlw.de for all profile search terms.

    Deduplicates across search terms. Writes to data/staging/00_wlw_raw.csv.
    Returns list of CompanyRecord (all sources combined, unique by domain).
    """
    if kb is None:
        kb = KnowledgeBase(settings.KNOWLEDGE_BASE_PATH)

    all_records: list[CompanyRecord] = []
    seen_domains: set[str] = set()

    for term in profile.discovery.wlw_search_terms:
        logger.info("Scraping WLW for term: '%s'", term)
        term_records = _scrape_wlw_term(
            term=term,
            base_url=profile.discovery.wlw_base_url,
            profile_id=profile.id,
            dry_run=dry_run,
            max_pages=settings.WLW_MAX_PAGES,
            delay_sec=settings.WLW_DELAY_SEC,
        )
        added = 0
        for r in term_records:
            if limit and len(all_records) >= limit:
                break
            if r.domain not in seen_domains:
                seen_domains.add(r.domain)
                all_records.append(r)
                added += 1
        logger.info("  Term '%s': %d unique new domains", term, added)
        if limit and len(all_records) >= limit:
            logger.info("Reached --limit %d — stopping", limit)
            break

    logger.info("WLW scrape complete: %d unique companies", len(all_records))

    if not dry_run:
        _write_discovered_csv(all_records, settings.STAGING_WLW_RAW)

    return all_records


def _write_discovered_csv(records: list[CompanyRecord], path: Path) -> None:
    if not records:
        logger.warning("No records to write to %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].to_dict().keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(r.to_dict() for r in records)
    logger.info("Wrote %d records to %s", len(records), path)
