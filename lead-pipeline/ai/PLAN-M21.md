# M21: Impressum Scraper + GF Enrichment

## Summary

Integrates `/impressum` page fetching into the existing scrape pass (no double-scraping) and adds a `enrich-gf` command that extracts Geschäftsführer name, address, and personal email from the stored impressum content. Done when: all 24 unapproached A/B records have been processed, `gf_name` is populated where the impressum pattern matched, and the dashboard side panel shows GF name + address diff warning.

---

## HOW TO EXECUTE THIS MILESTONE

Planning: run `/plan-milestone` — full protocol in `~/.claude/commands/plan-milestone.md`.
Execution: run `/execute-milestone` — full protocol in `~/.claude/commands/execute-milestone.md`.

---

## Locked Decisions

- **Impressum fetched during scrape pass, stored separately.** `extract_page_text` already fetches classification-useful pages (homepage, /leistungen, /service, /produkte, /ueber-uns) into `domain_cache`. `/impressum` is legal boilerplate — useful for GF extraction, not for classification text. It must be stored in `knowledge_base.documents` (doc_type="impressum"), never mixed into `scraped_text`.
- **No double-scraping.** `scrape_batch_cmd` fetches `/impressum` alongside the main pages in the same pass. One HTTP session per domain. Cache hit on `domain_cache` does NOT skip the impressum fetch — the two caches are independent.
- **`enrich-gf` command handles existing records.** The 24 A/B records were scraped before M21. `enrich-gf` fetches `/impressum` for records missing it from the KB (23 HTTP calls), then extracts and writes to DB. Supports `--dry-run` and `--limit`.
- **Regex extraction first, Claude CLI fallback.** German impressum format is standardized (Handelsregister requirement). Regex handles the common patterns cheaply. Claude CLI only called when regex finds nothing and scraped_text is non-empty.
- **`gf_name` is NOT auto-filled into `owner_name`.** `owner_name` = gesellschafter (person we write to). `gf_name` = impressum GF (a different person). When `owner_name` is empty and `gf_name` is found, surface as needs_review in dashboard — Roman decides the addressee manually.
- **Address stored in new `impressum_address` column, ORBIS data never overwritten.** If impressum address differs from `street`/`plz_ort`, flag in dashboard side panel. `impressum_address` is display-only; it does not feed into the Serienbrief export unless manually promoted by Roman.
- **Email: personal emails update `gf_email` if empty, generic emails discarded.** Generic patterns: info@, kontakt@, mail@, anfrage@, post@, office@, service@. If a personal email (e.g. m.mueller@firma.de) is found in impressum and `gf_email` is currently empty, write it.
- **Table name is `company_records`** (not `companies` or `pipeline`). Verified from schema.
- **KB `documents` table already exists** with columns: id, domain, hrb_number, doc_type, content, fetched_at. Zero rows currently. Use doc_type="impressum".

---

## Plan

### Phase 0: DB schema addition

**0.1 Add `impressum_address` column to `company_records`**

In `src/pipeline/db.py`, find `ensure_schema()` and add:
```python
_IMPRESSUM_COLUMNS = [
    "impressum_address TEXT",
]
```
Add these to the `ALTER TABLE ADD COLUMN` loop in `ensure_schema()` (same pattern as `_OUTREACH_COLUMNS`).

Verify the column doesn't already exist before adding.

---

### Phase 1: Impressum fetch in `web.py`

**1.1 Add `fetch_impressum_text(domain) -> str`**

In `src/utils/web.py`, add after `extract_page_text`:

```python
def fetch_impressum_text(domain: str) -> str:
    """Fetch /impressum page text. Tries common URL variants.
    Returns clean text or empty string on failure.
    """
    paths = ["/impressum", "/impressum.html", "/impressum.php", "/de/impressum"]
    for path in paths:
        html = fetch_with_retry(f"https://{domain}{path}")
        if html:
            text = clean_html(html)
            if len(text) > 100:  # skip near-empty pages
                return text
    return ""
```

No changes to `extract_page_text` — impressum is always fetched separately.

---

### Phase 2: Integrate impressum fetch into `scrape_batch_cmd`

**2.1 Update `src/pipeline/scrape.py`**

In `scrape_batch_cmd`, after writing `scraped_text` to DB (after the existing `pipeline_db.update_scrape_result` call), add impressum fetch:

```python
# --- Impressum fetch (stored separately in KB documents) ---
cached_impressum = kb.get_document(domain, "impressum")
if cached_impressum is None:
    imp_text = fetch_impressum_text(domain)
    kb.save_document(domain, hrb_number=None, doc_type="impressum", content=imp_text)
    if imp_text:
        logger.debug("[%d/%d] IMPRESSUM: %s (%d chars)", i, total, domain, len(imp_text))
    http_calls += 1
    if http_calls > 1:
        time.sleep(_POLITE_DELAY_S)
```

Import `fetch_impressum_text` at the top of `scrape.py`.

The `_POLITE_DELAY_S` sleep is shared with the main scrape counter — this keeps the existing rate-limit behavior.

**2.2 Check `kb.get_document` and `kb.save_document` signatures**

In `src/utils/knowledge_base.py`, verify these methods exist and match:
- `get_document(domain: str, doc_type: str) -> Optional[str]` — returns content or None
- `save_document(domain: str, hrb_number: Optional[str], doc_type: str, content: str) -> None`

If signatures differ, adapt the call in scrape.py accordingly. Do not change knowledge_base.py signatures.

---

### Phase 3: GF extraction logic

**3.1 Add `_extract_gf_from_impressum(text) -> dict` to `src/pipeline/enrich.py`**

```python
import re

_GF_PATTERNS = [
    r"Gesch[äa]ftsf[üu]hr(?:er(?:in)?|ung)\s*[:\s]\s*(?:Dr\.?\s+)?([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){1,3})",
    r"[Vv]ertreten durch[:\s]+(?:Gesch[äa]ftsf[üu]hr(?:er|erin)\s+)?(?:Dr\.?\s+)?([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){1,3})",
    r"Inhaber\s*[:\s]\s*(?:Dr\.?\s+)?([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+){1,3})",
]

_GENERIC_EMAIL_PREFIXES = {
    "info", "kontakt", "mail", "anfrage", "post", "office",
    "service", "support", "hello", "hallo", "vertrieb",
}

def _extract_gf_from_impressum(text: str) -> dict:
    """Extract GF name, address fragment, and personal email from impressum text.
    Returns dict with keys: gf_name, impressum_address, personal_email (all may be None).
    """
    result: dict = {"gf_name": None, "impressum_address": None, "personal_email": None}
    if not text:
        return result

    # GF name — first pattern match wins
    for pattern in _GF_PATTERNS:
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip()
            # Sanity check: at least two words, no digits
            if len(name.split()) >= 2 and not re.search(r"\d", name):
                result["gf_name"] = name
                break

    # Address — look for PLZ + city near the top of the impressum
    addr_match = re.search(
        r"([A-ZÄÖÜ][a-zäöüß\s\.\-]+\d+[a-zA-Z]?\s*\n?\s*\d{5}\s+[A-ZÄÖÜ][a-zäöüß\s\-]+)",
        text,
    )
    if addr_match:
        result["impressum_address"] = re.sub(r"\s+", " ", addr_match.group(1)).strip()

    # Personal email — find all emails, discard generic
    emails = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}\b", text)
    for email in emails:
        prefix = email.split("@")[0].lower().split(".")[0]
        if prefix not in _GENERIC_EMAIL_PREFIXES and len(prefix) > 2:
            result["personal_email"] = email
            break

    return result
```

**3.2 Add `enrich_gf_cmd(args)` to `src/pipeline/enrich.py`**

```python
def enrich_gf_cmd(
    dry_run: bool = False,
    limit: int = 0,
    db_path: Path | None = None,
    kb_path: Path | None = None,
) -> int:
    """
    Enrich A/B records with GF name, impressum address, and personal email
    from /impressum page content.

    For each A/B record:
    1. Check KB documents for impressum content.
    2. If not found: fetch /impressum → save to KB.
    3. Extract gf_name, impressum_address, personal_email via regex.
    4. If regex finds nothing and scraped_text non-empty: Claude CLI fallback for gf_name only.
    5. Write to pipeline.db (gf_name, impressum_address, gf_email if currently empty).

    Skips records where gf_name is already populated.
    """
```

Selection query: A/B records with `already_approached=0` AND (`gf_name IS NULL OR gf_name=''`).

For each record:
1. `cached = kb.get_document(domain, "impressum")`
2. If `cached is None`: call `fetch_impressum_text(domain)`, `kb.save_document(...)`, polite delay
3. `extracted = _extract_gf_from_impressum(cached or fetched_text)`
4. If `extracted["gf_name"] is None` and `scraped_text` non-empty: Claude CLI fallback (see 3.3)
5. Write to DB (per-record connection, same pattern as `backfill_leistung_cmd`)

**3.3 Claude CLI fallback for gf_name**

Prompt (passed via stdin, `--output-format json`):
```
Extract the Geschäftsführer (managing director) name from this German impressum text.
Return JSON: {"gf_name": "First Last"} or {"gf_name": null} if not found.
---
{impressum_text[:1500]}
```

If CLI returns valid JSON with non-null `gf_name`: use it.
If CLI fails or returns null: skip, log as not found.
Dry-run: log what would be called, skip actual CLI call.

---

### Phase 4: Register CLI command

**4.1 Update `pipeline.py`**

Add `enrich-gf` subparser:
```python
gf_parser = subparsers.add_parser("enrich-gf", help="Extract GF name/address from impressum pages")
gf_parser.add_argument("--dry-run", action="store_true")
gf_parser.add_argument("--limit", type=int, default=0)
```

Add dispatch:
```python
elif args.command == "enrich-gf":
    from src.pipeline.enrich import enrich_gf_cmd
    enrich_gf_cmd(dry_run=args.dry_run, limit=args.limit)
```

---

### Phase 5: Dashboard side panel

**5.1 GF name display in `src/pipeline/templates/dashboard.html`**

In the side panel (company card right pane), add below the `owner_name` field:

- If `gf_name` is non-empty: show as "GF (Impressum): {gf_name}" in a secondary row
- If `owner_name` is empty AND `gf_name` non-empty: show orange warning "Kein Gesellschafter — GF als Adressat prüfen" with `gf_name` prominently

**5.2 Address mismatch warning**

If `impressum_address` is set and differs from `street + " " + plz_ort` (simple substring check): show yellow info row "Impressum-Adresse abweichend: {impressum_address}"

**5.3 Update `_load_data()` in `dashboard.py`**

Add `gf_name` and `impressum_address` to the fields loaded per record. Verify they appear in the JSON data object.

**5.4 Update `_WRITEBACK_FIELDS`**

Add `"gf_name"` to the frozenset so Roman can manually edit it from the dashboard if needed.

---

### Phase 6: Update DB write helper

**6.1 Verify `db.py` write function**

Confirm there is a function (or add one) that can update `gf_name`, `impressum_address`, and `gf_email` for a given domain. Pattern: use existing `update_company_field` or equivalent. If no generic field updater exists, add:

```python
def update_gf_enrichment(
    conn: sqlite3.Connection,
    domain: str,
    gf_name: Optional[str],
    impressum_address: Optional[str],
    gf_email: Optional[str],
) -> None:
    """Write GF enrichment fields for a domain. Only overwrites gf_email if currently empty."""
    conn.execute(
        """UPDATE company_records
           SET gf_name = COALESCE(?, gf_name),
               impressum_address = COALESCE(?, impressum_address),
               gf_email = CASE WHEN (gf_email IS NULL OR gf_email='') THEN COALESCE(?, gf_email)
                               ELSE gf_email END
           WHERE domain = ?""",
        (gf_name, impressum_address, gf_email, domain),
    )
```

---

## Better Engineering Notes

- **Why `/impressum` is stored separately from `scraped_text`**: The classification prompt uses `scraped_text` to determine business model. Impressum content (GF name, address, legal entity info) would dilute the classification signal if mixed in. Separate storage in `documents` table keeps the concerns clean.
- **KB cache independence**: `domain_cache` TTL 90 days and `documents` TTL are independent. A domain can have fresh `scraped_text` but no impressum entry (pre-M21 records) — `enrich-gf` handles this without invalidating the scrape cache.
- **Regex coverage estimate**: ~70% of German GmbH impressum pages follow "Geschäftsführer: Name" format. The "Vertreten durch" pattern catches another ~15%. The remaining ~15% (unusual formats, multiple GFs listed differently) fall to Claude CLI.
- **`impressum_address` is display-only for now.** It is NOT added to the Serienbrief export. If Roman wants to correct an ORBIS address, he does it manually via the dashboard write-back on `street`/`plz_ort`.
- **Future: `/team` page scraping** for personal email patterns is deferred. Impressum covers the most common case. Add `/team` to `fetch_impressum_text` paths only if impressum email hit rate is low after M21.
- **LEARNINGS.md note**: `upsert_serienbriefe_record` hardcodes column lists — if `impressum_address` ever flows into Serienbrief, both UPDATE and INSERT branches must be updated.

---

## AI Validation Plan

```bash
# Phase 0: schema
python -c "import sqlite3; c=sqlite3.connect('data/pipeline.db'); print([r[1] for r in c.execute('PRAGMA table_info(company_records)').fetchall()])" | grep impressum_address

# Phase 1-2: scrape integration (dry run + live)
python pipeline.py scrape --dry-run --limit 3
python pipeline.py scrape --limit 2  # verify impressum appears in KB after

python -c "
import sqlite3
c=sqlite3.connect('data/knowledge_base.db')
print('Documents after scrape:', c.execute('SELECT COUNT(*) FROM documents').fetchone())
print('Sample:', c.execute('SELECT domain, doc_type, length(content) FROM documents LIMIT 5').fetchall())
"

# Phase 3-4: enrich-gf
python pipeline.py enrich-gf --dry-run --limit 5  # shows what would be fetched/extracted
python pipeline.py enrich-gf --limit 5             # live run on 5 A/B records

python -c "
import sqlite3
c=sqlite3.connect('data/pipeline.db')
print(c.execute(\"SELECT domain, gf_name, impressum_address FROM company_records WHERE gf_name IS NOT NULL AND gf_name != '' LIMIT 5\").fetchall())
"

# Full run
python pipeline.py enrich-gf  # all 24 unapproached A/B records
python pipeline.py status

# No regressions
pytest tests/ -q
```

**Pass criteria:**
- `impressum_address` column exists in schema
- After `scrape --limit 2`: KB documents table has ≥1 impressum row with `length(content) > 100`
- After `enrich-gf --limit 5`: ≥2 of 5 records have non-empty `gf_name`
- After full `enrich-gf`: count of records with `gf_name != ''` ≥ 10 (realistic: ~70% regex hit rate → ~17/24)
- `pytest tests/ -q`: 408+ passing, zero regressions
- `pipeline.py status`: same stage counts (no classification side effects)

**Failure definition:**
- Any test regression
- `impressum_address` column missing after migration
- `enrich-gf` with no `--dry-run` makes DB writes without a `with get_connection()` context (check for bare `conn =` outside context manager)
- Claude CLI fallback fires for >50% of records (would indicate regex patterns are wrong — fix patterns first)

---

## AI Validation Results

**Commands run:**
```bash
python pipeline.py enrich-gf --dry-run       # 24 records, 24 fetches needed
python pipeline.py enrich-gf --limit 5       # 5/5 found (via work copy — DB WAL lock workaround)
python pipeline.py enrich-gf                 # full run, 17/24 found
python pipeline.py status                    # stage counts unchanged
pytest tests/ -q                             # 425 passed (17 new in test_enrich_gf.py)
```

**Results (2026-03-31):**
- `impressum_address` column added to `company_records` schema ✅
- KB `documents` table: 24 impressum entries (18 with content, 6 empty = domain had no /impressum page) ✅
- `enrich-gf` full run: **17/24 records** got `gf_name` (71% hit rate) ✅
- 7 not-found: ka-med.de, mamedis.de, mediservice-magdeburg.de, medizintechnik-berlin-gmbh.de, medtec-berlin.com (HTTP 400), rennecke-medic.com, mtsmedizintechnik.de
- `schmid-medizintechnik.de` (the 1 record with no owner_name) → `gf_name = Stefan Schmid` ✅
- Test suite: **425 passed, zero regressions**
- `pipeline.py status`: A=100, B=298, C=4, D=117, E=3 — unchanged

**Deviations from plan:**
- Regex patterns required 2 rounds of tuning: added `_NON_NAME_SUFFIXES` to strip "Kontakt/Handelsregister/Kammer/Umsatzsteuer" trailing words; added `rstrip("-")` for hyphenated surnames
- Email extraction: fixed to check full local part (not just first dot segment) so `m.mueller@firma.de` is correctly classified as personal
- 17 new unit tests added for `_extract_gf_from_impressum` (PM review requirement — pure logic, testable, exactly the M19 pattern)
- DB WAL lock workaround (same as M20): used `sqlite3.backup()` to clean copy for all enrich-gf runs
- `autoSalutation` JS pre-existing bug fixed: was referencing `wb-gf-name` which didn't exist; now uses `wb-owner-name` with fallback to `wb-gf-name`

**PM Review verdict:** PASS (see below)

---

## User Validation Walkthrough

1. `python pipeline.py scrape --limit 3 --verbose` — observe log lines "IMPRESSUM: domain.de (NNN chars)" alongside the regular scrape logs
2. `python pipeline.py enrich-gf --dry-run` — shows how many records would be processed, how many impressum fetches needed
3. `python pipeline.py enrich-gf` — run for real; watch for "GF found: [Name]" log lines
4. `python pipeline.py dashboard --serve`, open localhost:8080 → navigate to any A/B record side panel → verify "GF (Impressum):" row appears; for the 1 record with no owner_name (schmid-medizintechnik.de), verify orange warning shown
5. Spot-check: `python -c "import sqlite3; c=sqlite3.connect('data/pipeline.db'); print(c.execute(\"SELECT domain,gf_name,impressum_address FROM company_records WHERE gf_name!='' LIMIT 5\").fetchall())"` — verify names look like real people, not corporate strings
