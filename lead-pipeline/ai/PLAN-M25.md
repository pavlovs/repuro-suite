# M25: Scraper Refactor — Subpage Discovery

## Summary

Replace the hardcoded subpage list in `extract_page_text()` (currently: homepage + `/leistungen` + `/service` + `/produkte` + `/ueber-uns`) with dynamic subpage discovery. Two-tier strategy: (1) parse anchor tags from the homepage and score by German keyword relevance, (2) fall back to `sitemap.xml` / `sitemap_index.xml` when homepage yields too few links. Goal: richer text passed to the M24 classifier, especially for sites that don't use the canonical `/leistungen`-style URLs. No behavior change in the HTTP/caching layer — only the URL-discovery step.

## HOW TO EXECUTE THIS MILESTONE

From `ai/PLAN.md` Definition of Done:

1. `PLAN-M25.md` exists with non-empty `## AI VALIDATION RESULTS` section.
2. `pytest tests/` passes — no regressions.
3. `scrape --limit 10` runs live against fresh domains (bypass KB cache with `--force` or pick uncached domains).
4. `python pipeline.py status` shows expected counts.
5. `ARCHITECTURE.md` M5 section + DESIGN.md updated in the same commit.
6. One commit per milestone.

Execution protocol: `/execute-milestone`.

## Locked Decisions

1. **Link-extraction primary, sitemap fallback, hardcoded list as final fallback.** Order: (a) parse homepage links → score → pick top N; if fewer than 3 good links, (b) fetch `/sitemap.xml` → filter by keywords → pick top N; if still fewer than 3, (c) use current hardcoded list.
2. **Cap: 6 subpages max per domain** (homepage + 5 subpages). Current flow fetches up to 5 already; +1 page is acceptable latency cost.
3. **German keyword scoring for link relevance** (case-insensitive substring match on link text AND href):
   - High (+3): `leistungen`, `service`, `produkte`, `ueber-uns`, `über-uns`, `unternehmen`, `kompetenz`, `lösungen`, `loesungen`
   - Medium (+2): `branchen`, `kunden`, `referenzen`, `partner`, `portfolio`, `philosophie`, `tätigkeit`, `taetigkeit`
   - Low (+1): `team`, `firma`, `wir`, `about`
   - Negative (−5): `impressum`, `datenschutz`, `agb`, `karriere`, `jobs`, `kontakt`, `login`, `shop`, `warenkorb`, `cart`, `newsletter`, `blog`, `news`, `presse`, `download`
4. **Link filtering rules**:
   - Only same-origin links (drop external, drop `tel:`, `mailto:`, anchors, `javascript:`).
   - Drop query strings and fragments before dedup.
   - Dedup by normalized path.
   - Drop links whose path depth > 3 (avoid deep product catalog pages).
   - Drop paths matching negative-score terms outright (don't just downscore).
5. **Sitemap parser** — minimal: try `/sitemap.xml` then `/sitemap_index.xml`. Parse all `<loc>` entries (follow one level of sitemap-index if encountered). Apply same keyword scoring + path filtering as homepage links.
6. **Impressum fetch unchanged.** `fetch_impressum_text()` stays separate — no pollution of scraped_text per LEARNINGS.md.
7. **Cache invalidation**: existing `knowledge_base.domain_cache` entries stay valid. M25 only affects new scrapes and TTL-expired re-scrapes. No bulk refresh in this milestone — the M24 backlog reprocess milestone (later) can force refresh if needed.
8. **New `--force-refresh` flag on `scrape` command** — bypass KB cache for a specific record set. Useful for testing M25 against live deals.
9. **No subdirectory crawling.** Only links present on the homepage or in sitemap. No recursive crawling of selected subpages.
10. **Text truncation stays `max_chars=2500`.** Subpage discovery gives better signal, not more tokens — richer ≠ longer.

## Plan

### Step 1 — New module `src/utils/link_discovery.py`
```python
from dataclasses import dataclass

KEYWORDS_HIGH = [...]
KEYWORDS_MED = [...]
KEYWORDS_LOW = [...]
KEYWORDS_NEG = [...]

@dataclass
class ScoredLink:
    url: str
    score: int
    source: str  # "homepage" | "sitemap" | "fallback"

def extract_links_from_html(html: str, base_url: str) -> list[str]: ...
def score_link(url: str, anchor_text: str) -> int: ...
def discover_subpages(domain: str, homepage_html: str, client, max_pages: int = 5) -> list[ScoredLink]:
    """Homepage links → sitemap fallback → hardcoded fallback."""
```

### Step 2 — Modify `src/utils/web.py`
- `extract_page_text(domain, max_chars=2500)`:
  1. Fetch homepage → get HTML text + raw html for link parsing.
  2. Call `discover_subpages(domain, homepage_html, client)` → list of up to 5 URLs.
  3. Fetch each, concatenate text.
  4. Truncate to `max_chars`.
- Replace hardcoded `["/leistungen", "/service", "/produkte", "/ueber-uns"]` loop with the discovery call. Hardcoded list moves into `link_discovery.FALLBACK_PATHS`.

### Step 3 — Sitemap parser
In `link_discovery.py`:
- `fetch_sitemap(domain, client) -> list[str]` — tries `/sitemap.xml` then `/sitemap_index.xml`. Returns list of URLs. Handles sitemap-index one level deep. Returns `[]` on any failure.
- Minimal XML parsing with `xml.etree.ElementTree` — no new dependency.

### Step 4 — Add `--force-refresh` to scrape command
`src/pipeline/scrape.py`:
- Add CLI flag.
- When set: skip `kb.get_scraped_text()` check, always fetch.
- Still writes result back to KB (overwrite).

### Step 5 — Persist discovery metadata
Store discovered URLs in existing `knowledge_base.domain_cache.source_urls` (JSON array). No schema change needed — column exists per ARCHITECTURE.md. Confirms which strategy (homepage/sitemap/fallback) produced the pages for debugging.

### Step 6 — Unit tests
Create `tests/test_link_discovery.py`:
- `score_link()`: hand-crafted URLs against expected scores (leistungen/impressum/shop/etc.).
- `extract_links_from_html()`: fixture HTML with mixed internal/external/mailto/anchor links.
- `discover_subpages()`: mocked homepage HTML → correct top-N; empty homepage → sitemap fallback mocked; both fail → fallback paths returned.
- Path-depth filter: `/a/b/c/d` dropped, `/a/b/c` kept.
- Same-origin filter: external domains dropped.

Extend `tests/test_web.py` or create `tests/test_extract_page_text.py`:
- Integration test with mocked httpx client returning canned HTML for homepage + 3 subpages → verify final text contains content from all pages, truncated to 2500.

### Step 7 — Live validation
Run `scrape --force-refresh` on the 7 live deal domains (HWV, KVG, Com2Med, Medizin & Service, Sonowied, IST Medical, Golmed). Inspect `source_urls` in KB — verify non-canonical sites get useful subpages that the old hardcoded list would have missed.

### Step 8 — Docs + commit
- Update `ARCHITECTURE.md` M5 section + HTTP Layer section.
- Update `DESIGN.md` with subpage discovery rationale.
- Update `ai/ROADMAP.md` Foundation table: add M25 row ✅. Update Current State.
- Update `ai/PLAN.md` Milestone Overview: M25 ✅.
- One commit: `feat(M25): subpage discovery with keyword-scored link extraction + sitemap fallback`

## Better Engineering Notes

- **Link-discovery quality depends on keyword list.** Monitor `source_urls` in KB after rollout — if live deals keep missing obvious pages, extend `KEYWORDS_MED/LOW`, don't lower thresholds.
- **Shopware/WordPress sites often use non-German slugs** (`/solutions`, `/products`). Current keyword list is German-first; add English equivalents if live deals show this pattern.
- **Sitemap.xml is often massive** on e-commerce sites. Cap parse to first 1000 entries to avoid memory spikes on catalog-heavy domains.
- **Robots.txt is ignored** (same as current behavior — public pages, polite rate). Revisit if a host complains.
- **Backlog re-scrape decision stays with user** — M25 does not force a refresh of the 2,420 existing records. A separate milestone can do that after validating M25 on live deals.

## AI Validation Plan

```
pytest tests/ -x -q                                       # expect all green
pytest tests/test_link_discovery.py -v                    # expect ~8 tests pass
python pipeline.py scrape --limit 10 --force-refresh      # expect fresh fetches, source_urls populated
python pipeline.py status                                  # expect scrape counts +10
sqlite3 data/knowledge_base.db "SELECT domain, source_urls FROM domain_cache ORDER BY scraped_at DESC LIMIT 10"
```

For live-deal spot check:
```
python pipeline.py scrape --domain <hwv.de>  --force-refresh   # repeat for 7 live deals
```
Inspect `source_urls` — expect a mix of `/leistungen`, `/unternehmen`, `/philosophie`, `/lösungen`, `/branchen` — NOT just the old 4.

## AI Validation Results

_To be filled by the executor._

## User Validation Walkthrough

1. `pytest tests/ -x -q` → green.
2. Pick one live deal whose site uses non-canonical URLs (e.g. Medizin & Service if it uses `/kompetenz`). Run `scrape --domain <domain> --force-refresh`.
3. Query `source_urls` in knowledge_base.db — confirm the new URLs were discovered (not just the old hardcoded 4).
4. Re-run `classify --domain <same> --force` (if supported, else manually flush classify stage and re-classify). Compare new `scraped_text` vs old — expect more company-specific content.
5. After M24 is also deployed: re-classify the 7 live deals and verify the thesis assignment matches expectation (see M24 walkthrough).
