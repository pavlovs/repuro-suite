# PLAN-M2: Discovery Scraper + Knowledge Base

## Context

M1 delivered: CLI, IndustryProfile schema, CompanyRecord model, utils, 39 passing tests.

M2 delivers:
1. **SQLite knowledge base** (`data/knowledge_base.db`) — persistent cache for scraped text and ownership data across all runs. Never pay for the same domain twice.
2. **WLW scraper** — scrapes wer-liefert-was.de by profile search terms → `data/staging/00_discovered.csv`

After M2: `python pipeline.py scrape-wlw` runs, produces a discovered CSV, and populates the knowledge base with raw scraped text. `python pipeline.py status` shows M2 Discovered count.

---

## Files to Create / Modify

```
Create:
  src/utils/knowledge_base.py         # SQLite wrapper — all cache access
  src/pipeline/wlw_scraper.py         # REPLACE stub — full implementation
  tests/test_knowledge_base.py
  tests/test_wlw_scraper.py

Modify:
  src/pipeline/models.py              # Add orbis_ownership_source field
  src/config/settings.py             # Add KNOWLEDGE_BASE_PATH, SCRAPE_TTL_DAYS
  pipeline.py                        # scrape-wlw command calls real function
```

---

## Step 1: Update settings.py

Add to `src/config/settings.py`:
```python
KNOWLEDGE_BASE_PATH = DATA_DIR / "knowledge_base.db"
SCRAPE_TTL_DAYS: int = 90          # Re-scrape after 90 days
OWNERSHIP_TTL_DAYS: int = 180      # Re-fetch ownership after 180 days
WLW_DELAY_SEC: float = 1.5         # Polite delay between WLW requests
WLW_MAX_PAGES: int = 20            # Max result pages per search term
```

---

## Step 2: `src/utils/knowledge_base.py`

```python
"""SQLite knowledge base — persistent cache for scraped text and ownership data."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS domain_cache (
    domain          TEXT PRIMARY KEY,
    scraped_text    TEXT,
    scraped_at      TIMESTAMP,
    http_status     INTEGER,
    source_urls     TEXT
);

CREATE TABLE IF NOT EXISTS ownership_cache (
    domain                      TEXT PRIMARY KEY,
    hrb_number                  TEXT,
    gesellschafter_name         TEXT,
    gesellschafter_share_pct    REAL,
    gesellschafter_age          INTEGER,
    is_subsidiary               INTEGER,
    is_pe_backed                INTEGER,
    gf_name                     TEXT,
    source                      TEXT,
    raw_response                TEXT,
    fetched_at                  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    hrb_number  TEXT,
    doc_type    TEXT NOT NULL,
    content     TEXT,
    fetched_at  TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
"""


class KnowledgeBase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- domain_cache ---

    def get_scraped_text(self, domain: str, max_age_days: int = 90) -> Optional[str]:
        """Return cached scraped text if fresh, else None."""
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT scraped_text, scraped_at FROM domain_cache WHERE domain = ?",
                (domain,),
            ).fetchone()
        if row and row["scraped_text"] and row["scraped_at"]:
            scraped_at = datetime.fromisoformat(str(row["scraped_at"]))
            if scraped_at > cutoff:
                return row["scraped_text"]
        return None

    def save_scraped_text(
        self,
        domain: str,
        text: str,
        http_status: int = 200,
        source_urls: Optional[list[str]] = None,
    ) -> None:
        urls_json = json.dumps(source_urls or [])
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO domain_cache (domain, scraped_text, scraped_at, http_status, source_urls)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                     scraped_text=excluded.scraped_text,
                     scraped_at=excluded.scraped_at,
                     http_status=excluded.http_status,
                     source_urls=excluded.source_urls""",
                (domain, text, datetime.utcnow().isoformat(), http_status, urls_json),
            )

    def domain_already_seen(self, domain: str) -> bool:
        """True if domain exists in cache at all (regardless of TTL)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM domain_cache WHERE domain = ?", (domain,)
            ).fetchone()
        return row is not None

    # --- ownership_cache ---

    def get_ownership(self, domain: str, max_age_days: int = 180) -> Optional[dict]:
        """Return cached ownership data if fresh, else None."""
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM ownership_cache WHERE domain = ?", (domain,)
            ).fetchone()
        if row and row["fetched_at"]:
            fetched_at = datetime.fromisoformat(str(row["fetched_at"]))
            if fetched_at > cutoff:
                return dict(row)
        return None

    def save_ownership(self, domain: str, data: dict, source: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO ownership_cache
                   (domain, hrb_number, gesellschafter_name, gesellschafter_share_pct,
                    gesellschafter_age, is_subsidiary, is_pe_backed, gf_name, source,
                    raw_response, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                     hrb_number=excluded.hrb_number,
                     gesellschafter_name=excluded.gesellschafter_name,
                     gesellschafter_share_pct=excluded.gesellschafter_share_pct,
                     gesellschafter_age=excluded.gesellschafter_age,
                     is_subsidiary=excluded.is_subsidiary,
                     is_pe_backed=excluded.is_pe_backed,
                     gf_name=excluded.gf_name,
                     source=excluded.source,
                     raw_response=excluded.raw_response,
                     fetched_at=excluded.fetched_at""",
                (
                    domain,
                    data.get("hrb_number"),
                    data.get("gesellschafter_name"),
                    data.get("gesellschafter_share_pct"),
                    data.get("gesellschafter_age"),
                    int(data["is_subsidiary"]) if data.get("is_subsidiary") is not None else None,
                    int(data["is_pe_backed"]) if data.get("is_pe_backed") is not None else None,
                    data.get("gf_name"),
                    source,
                    json.dumps(data.get("raw_response", {})),
                    datetime.utcnow().isoformat(),
                ),
            )

    # --- documents ---

    def get_document(self, domain: str, doc_type: str) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT content FROM documents WHERE domain = ? AND doc_type = ? ORDER BY fetched_at DESC LIMIT 1",
                (domain, doc_type),
            ).fetchone()
        return row["content"] if row else None

    def save_document(self, domain: str, hrb_number: Optional[str], doc_type: str, content: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO documents (domain, hrb_number, doc_type, content, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (domain, hrb_number, doc_type, content, datetime.utcnow().isoformat()),
            )

    def stats(self) -> dict:
        """Return record counts for status display."""
        with self._conn() as conn:
            domains = conn.execute("SELECT COUNT(*) FROM domain_cache").fetchone()[0]
            with_text = conn.execute(
                "SELECT COUNT(*) FROM domain_cache WHERE scraped_text IS NOT NULL AND scraped_text != ''"
            ).fetchone()[0]
            ownership = conn.execute("SELECT COUNT(*) FROM ownership_cache").fetchone()[0]
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return {"domains_cached": domains, "with_text": with_text, "ownership_cached": ownership, "documents": docs}
```

---

## Step 3: `src/pipeline/wlw_scraper.py` — full implementation

WLW search URL pattern: `https://www.wer-liefert-was.de/suche/{term}/` with pagination `?page=N`.

Each result card contains: company name, website link, city, description snippet.

```python
"""WLW scraper — scrapes wer-liefert-was.de by profile search terms."""
from __future__ import annotations

import csv
import logging
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


def _parse_domain(url: str) -> Optional[str]:
    """Extract clean domain from a URL string."""
    if not url:
        return None
    url = url.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if url.startswith(prefix):
            url = url[len(prefix):]
    return url.split("/")[0].strip() or None


def _scrape_wlw_term(
    term: str,
    base_url: str,
    kb: KnowledgeBase,
    profile_id: str,
    dry_run: bool = False,
    max_pages: int = 20,
    delay_sec: float = 1.5,
) -> list[CompanyRecord]:
    """Scrape one WLW search term, all pages."""
    records: list[CompanyRecord] = []
    seen_domains: set[str] = set()

    # URL-encode the search term (spaces → -)
    term_slug = term.replace(" ", "-").lower()
    search_url = f"{base_url}/suche/{term_slug}/"

    for page in range(1, max_pages + 1):
        url = search_url if page == 1 else f"{search_url}?page={page}"
        logger.info("WLW [%s] page %d: %s", term, page, url)

        if dry_run:
            logger.info("DRY RUN — skipping fetch")
            break

        html = fetch_with_retry(url, retries=2, delay=1.0)
        if not html:
            logger.warning("No response from %s — stopping pagination", url)
            break

        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("[data-testid='result-item'], .result-item, article.company-item")

        # Fallback: try common WLW result card selectors
        if not cards:
            cards = soup.select("div.company-result, li.result-entry, div[class*='CompanyCard']")

        if not cards:
            logger.info("No result cards found on page %d — end of results", page)
            break

        page_new = 0
        for card in cards:
            # Extract company name
            name_el = card.select_one("h2, h3, [class*='company-name'], [class*='CompanyName']")
            full_name = name_el.get_text(strip=True) if name_el else None
            if not full_name:
                continue

            # Extract website link
            link_el = card.select_one("a[href*='://'], a[class*='website'], a[class*='url']")
            raw_url = link_el.get("href", "") if link_el else ""
            domain = _parse_domain(raw_url)

            # Skip if no domain or already seen this run
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)

            # Extract city
            city_el = card.select_one("[class*='city'], [class*='location'], [class*='address']")
            city = city_el.get_text(strip=True) if city_el else None

            # Extract description
            desc_el = card.select_one("[class*='description'], [class*='teaser'], p")
            description = desc_el.get_text(strip=True)[:500] if desc_el else None

            record = CompanyRecord(
                domain=domain,
                full_name=full_name,
                profile_id=profile_id,
                source="WLW",
                city=city,
                scraped_text=description,
            )
            records.append(record)
            page_new += 1

        logger.info("  Page %d: %d new companies (total: %d)", page, page_new, len(records))

        if page_new == 0:
            break

        time.sleep(delay_sec)

    return records


def scrape_wlw(
    profile: IndustryProfile,
    kb: Optional[KnowledgeBase] = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[CompanyRecord]:
    """Scrape wer-liefert-was.de for all profile search terms. Writes 00_discovered.csv."""
    if kb is None:
        kb = KnowledgeBase(settings.KNOWLEDGE_BASE_PATH)

    all_records: list[CompanyRecord] = []
    seen_domains: set[str] = set()

    for term in profile.discovery.wlw_search_terms:
        logger.info("Scraping WLW for: %s", term)
        term_records = _scrape_wlw_term(
            term=term,
            base_url=profile.discovery.wlw_base_url,
            kb=kb,
            profile_id=profile.id,
            dry_run=dry_run,
            max_pages=settings.WLW_MAX_PAGES,
            delay_sec=settings.WLW_DELAY_SEC,
        )
        # Dedup across search terms
        for r in term_records:
            if r.domain not in seen_domains:
                seen_domains.add(r.domain)
                all_records.append(r)

    logger.info("WLW scrape complete: %d unique companies found", len(all_records))

    if not dry_run:
        _write_discovered_csv(all_records, settings.STAGING_WLW_RAW)

    return all_records


def _write_discovered_csv(records: list[CompanyRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        logger.warning("No records to write")
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].to_dict().keys())
        writer.writeheader()
        writer.writerows(r.to_dict() for r in records)
    logger.info("Wrote %d records to %s", len(records), path)
```

---

## Step 4: Update `pipeline.py` scrape-wlw command

Replace the dynamic import dispatch for `scrape-wlw` to pass the KB:

```python
if args.command == "scrape-wlw":
    from src.pipeline.wlw_scraper import scrape_wlw
    from src.utils.knowledge_base import KnowledgeBase
    kb = KnowledgeBase(settings.KNOWLEDGE_BASE_PATH)
    records = scrape_wlw(profile, kb=kb, dry_run=args.dry_run, verbose=args.verbose)
    if not args.dry_run:
        print(f"  Discovered: {len(records)} companies → {settings.STAGING_WLW_RAW}")
    kb_stats = kb.stats()
    print(f"  Knowledge base: {kb_stats['domains_cached']} domains cached")
```

Also add KB stats to `cmd_status`:
```python
kb_path = settings.KNOWLEDGE_BASE_PATH
if kb_path.exists():
    from src.utils.knowledge_base import KnowledgeBase
    kb = KnowledgeBase(kb_path)
    s = kb.stats()
    print(f"\n  Knowledge base: {s['domains_cached']} domains | {s['with_text']} with text | {s['ownership_cached']} ownership records")
```

---

## Step 5: Tests

**`tests/test_knowledge_base.py`**:
- `test_init_creates_db`: KnowledgeBase(tmp_path) creates file + tables
- `test_save_and_get_scraped_text`: save → get returns same text
- `test_get_scraped_text_respects_ttl`: stale entry returns None
- `test_domain_already_seen`: True after save, False before
- `test_save_and_get_ownership`: round-trip ownership data
- `test_get_ownership_respects_ttl`: stale returns None
- `test_save_and_get_document`: round-trip document
- `test_upsert_scraped_text`: saving twice updates, doesn't duplicate
- `test_stats_returns_counts`: stats() returns dict with correct keys

**`tests/test_wlw_scraper.py`**:
- `test_parse_domain_strips_https`: `"https://example.de/path"` → `"example.de"`
- `test_parse_domain_strips_www`: `"www.example.de"` → `"example.de"`
- `test_parse_domain_none_on_empty`: `""` → `None`
- `test_scrape_wlw_dry_run`: dry_run=True returns [] without HTTP calls
- `test_scrape_wlw_deduplicates_across_terms`: same domain from two terms appears once
- `test_write_discovered_csv_creates_file`: valid CSV written to tmp_path

---

## Validation

```bash
# Tests pass
pytest tests/test_knowledge_base.py tests/test_wlw_scraper.py -v

# Full suite still passes
pytest tests/ -q

# Dry run works
python pipeline.py --dry-run scrape-wlw --profile profiles/medtech_germany.json

# Real run (needs internet)
python pipeline.py scrape-wlw --profile profiles/medtech_germany.json --limit 10

# Status shows KB stats
python pipeline.py status
```

Expected after real run:
- `data/staging/00_discovered.csv` exists with N rows
- `data/knowledge_base.db` exists
- `status` shows "M2 Discovered: N companies"

---

## AI VALIDATION RESULTS

- `pytest tests/ -q` → **77 passed, 0 failed, 0 warnings** (2.58s)
- Knowledge base: SQLite with 3 tables (domain_cache, ownership_cache, documents), TTL-aware reads, upsert writes
- WLW scraper: dry_run works, _parse_domain handles all URL formats, CSV writer preserves umlauts
- `python pipeline.py status` shows KB stats when DB exists
- Python 3.13 compatibility confirmed (removed deprecated `detect_types=PARSE_DECLTYPES`)

---

## Not Included (Deferred)
- Additional scrapers (Gelbe Seiten, Google Maps) — future milestones
- WLW login / authenticated scraping — public results are sufficient
- Proxy rotation — not needed at this scale
