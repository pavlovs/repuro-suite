# M26: MANUAL Records — Briefaktion Readiness

## Summary

71 MANUAL-source A/B records need to be letter-ready for Briefaktion send-out. Target: >90%
fill on anrede, salutation, owner_name (→ Vorname/Nachname at export), street, plz_ort,
region_prep, leistung_text, compliment_draft, compliment_2.

**STATUS: PHASE 1 COMPLETE — Phase 2 (process hardening) pending**

Phase 1 uncovered 8 code bugs and 1 process error (wrong selection cohort). All fixed.
Phase 2 goal: next batch of 100 reaches >90% fill automatically, without manual intervention.
The Phase 1 fixes were mostly narrow/symptom patches. Phase 2 replaces them with general
heuristics that survive future domains.

## Target Cohort

```sql
SELECT * FROM company_records WHERE source='MANUAL' AND filter_pass=1
-- 71 records
```

**Not** `klass IN ('A','B')` — that selects 483 records across all sources and dilutes
MANUAL-specific fill rates.

## Final Fill Rates (2026-04-28, after M26 — extended)

| Field            | Filled | Rate  | Status |
| ---------------- | ------ | ----- | ------ |
| anrede           | 66/71  | 93.0% | OK ✅  |
| salutation       | 66/71  | 93.0% | OK ✅  |
| owner_name       | 66/71  | 93.0% | OK ✅  |
| street           | 70/71  | 98.6% | OK ✅  |
| plz_ort          | 70/71  | 98.6% | OK ✅  |
| region_prep      | 69/71  | 97.2% | OK ✅  |
| leistung_text    | 68/71  | 95.8% | OK ✅  |
| compliment_draft | 69/71  | 97.2% | OK ✅  |
| compliment_2     | 69/71  | 97.2% | OK ✅  |

`Vorname`/`Nachname` in the Serienbriefe template are derived by `export.py:_parse_name(owner_name)`
at export time. Missing owner_name = blank Vorname/Nachname.

## Remaining Hard Blockers (1 domain — manual review only)

| Domain     | Reason                                                                |
| ---------- | --------------------------------------------------------------------- |
| zekamed.de | React SPA — impressum renders no server-side content; address unknown |

All other originally-blocked domains resolved via web search (Northdata, Handelsregister,
business directories). Addresses confirmed by matching `full_name` in pipeline.db.

Also note: `steri24.de` is Austrian (Peintner Straße 10, 4060 Leonding) — letter may need
AT-format handling.

## Code Changes Made in M26

### File: `src/utils/web.py`

#### Change 1 — `clean_html`: preserve `<br>` as newlines before parsing
**Before:** `<br>` tags were discarded → "Musterstraße 1<br>12345 Stadt" → "Musterstraße 112345 Stadt"
**After:**
```python
html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
```
**Why:** German SME footer addresses use `<br>` for line breaks between street and PLZ.
Stripping them collapsed address lines, causing `_PLZ_CITY_RE` to never find a PLZ after
a street.

#### Change 2 — `fetch_impressum_text`: href link-scanning fallback
**Before:** Only tried 4 fixed paths: /impressum, /impressum.html, /impressum.php, /de/impressum
**After:** After path attempts, fetches homepage and scans for `href="...*impressum*..."` links,
deduplicates, and follows each. Fixed domain: `clavaro.de` (path was `/Informationen/Impressum/`
with capital I — not in the fixed list).

#### Change 3 — `extract_jsonld_address`: new function
```python
def extract_jsonld_address(html: str) -> tuple[Optional[str], Optional[str]]:
```
Parses `<script type="application/ld+json">` blocks for `schema.org/PostalAddress`.
Fixed domain: `aplusm-care.de` (address only in JSON-LD structured data, impressum path
returned empty text).
- Handles `"streetAddress": "Fabrikstr. 1, CompanyName"` — strips everything after comma
- Only accepts 5-digit German PLZ (rejects Austrian 4-digit)

### File: `src/pipeline/normalize.py`

#### Change 4 — `_LEGAL_ENTITY_RE`: case-sensitivity fix
**Before:** `re.IGNORECASE` flag caused "Ferhat Dag" to match `\bAG\b` at "ag" in "Dag" →
classified as corporate entity → no anrede derived.
**After:** Removed global `re.IGNORECASE`; long words (holding, verwaltung) use inline `(?i:)`.

#### Change 5 — Step 6b: title-skip for Dr./Prof. in gf_name
**Before:** `gf_parts[0]` = "Dr." → `_derive_anrede("Dr.")` → None → no anrede
**After:**
```python
if first_gf.lower().rstrip(".") in ("dr", "prof") and len(gf_parts) >= 3:
    first_gf = gf_parts[1]  # skip title, use actual first name
```
Fixed domain: `xcelsitas.de` (GF = "Dr. Michael Müller")

#### Change 6 — Step 6e: gf_name → owner_name fallback for corporate gesellschafter
When `gesellschafter_name` is a legal entity (GmbH, KG, etc.) or empty, the GF is the
correct letter addressee. New step:
```python
# 6e. gf_name → owner_name when gesellschafter is corporate/missing
if not rec.get("owner_name") and rec.get("gf_name"):
    gf = rec["gf_name"].strip()
    ges = (rec.get("gesellschafter_name") or "").strip()
    ges_is_corporate = bool(ges and _LEGAL_ENTITY_RE.search(ges)) or not ges
    if ges_is_corporate and _is_natural_person_name(gf) and len(gf.split()) >= 2:
        changed["owner_name"] = gf
        rec["owner_name"] = gf
```
**Impact:** +14 owner_name fills in the MANUAL cohort.

#### Change 7 — Step 9 salutation rebuild trigger
**Before:** Salutation only rebuilt when `_is_salutation_broken()` returns True (broken format).
**After:** Also rebuilds when `owner_name` was changed this run:
```python
if (
    (_is_salutation_broken(rec["salutation"]) or changed.get("owner_name"))
    and rec["anrede"]
    and name_for_salutation
):
```
**Why:** After step 6e fills owner_name, salutation still pointed to the old gf_name-based
value. The trigger needed to fire on owner_name change, not just on broken format.

#### Change 8 — `_PLZ_CITY_RE`: word-boundary fix
**Before:** `r"(\d{5})\s+([A-Z...])"` → matched "21702" in "ATU22821702 ARA" (Austrian tax ID).
**After:** `r"(?<!\d)(\d{5})(?!\d)\s+([A-Z...])"` — lookbehind/lookahead prevent matching digits
that are part of a longer number sequence.

#### Change 9 — `_clean_street`: additional separator tokens
Added "& Co.", "Co. KG" to the separator list. Previously "Co. KG Am Schornacker 30" was
returned as a street candidate with the entity prefix still attached.

### File: `scripts/rescrape_impressum_targeted.py` (NEW)
Force-rescrape script for MANUAL records missing street. Re-fetches impressum even when
KB already has an empty entry. Reports domains that got parseable addresses.

### File: `scripts/rescrape_impressum_deep.py` (NEW)
Extended rescraper that adds:
- Sitemap discovery (`/sitemap.xml`, `/sitemap.txt`, `robots.txt → Sitemap:`)
- Contact/about page fallback (`/kontakt`, `/ueber-uns`, etc.)
- Austrian address extraction (4-digit PLZ pattern)

Used to find: `actipart.de` (Hauptstr. 7, 01589 Riesa) and `steri24.de` Austrian address.

## Scraping Techniques Used (priority order for future batches)

1. **Standard paths**: `/impressum`, `/impressum.html`, `/impressum.php`, `/de/impressum`
2. **Homepage href scan**: regex scan for `href="...*impressum*..."` → follow links
   - Critical: case-sensitive paths (clavaro.de: `/Informationen/Impressum/`)
3. **Sitemap discovery**: `/sitemap.xml` → `<loc>` entries matching "impressum"
4. **Contact/about pages**: `/kontakt`, `/ueber-uns`, etc. → `parse_impressum_address`
5. **JSON-LD structured data**: `extract_jsonld_address(html)` on homepage
   - Catches: sites with empty impressum pages but SEO-structured data
6. **Footer div extraction**: `BeautifulSoup.find_all(['footer','div'], class_=re.compile('foot|contact|address'))`
   - Catches: habys.de (address in footer div), ana-trade.de (in `<address>` tag)
7. **Manual lookup**: for sites returning 4xx/connection refused/Flash

## Process Failures This Session

### Failure 1 — Wrong cohort for validation
**Anti-pattern (WRONG-COHORT-VALIDATION):** Ran fill-rate checks on all 483 A/B records
rather than the 71 MANUAL target. Global fill rates looked fine; MANUAL-specific rates
(street 66%, owner_name 44%) were never surfaced until caught.

**Fix:** Before reporting any sub-cohort task as done:
```sql
SELECT field, COUNT(*) FILTER (WHERE field IS NOT NULL AND TRIM(field) != '')
FROM company_records WHERE source='MANUAL' AND filter_pass=1
```

### Failure 2 — Enrichment script found wrong company names
**What happened:** An enrichment script matched `eu-medical.de` to "Eunaxis-Medical GmbH"
and `ana-trade.de` to "Manasseri Sales & Trade GmbH" — both are different companies.
The addresses were not written to the pipeline but the intermediate output was misleading.

**Root cause:** Company-name fuzzy matching in Handelsregister lookup is unreliable for
short domain prefixes. The LIKE search found the nearest text match regardless of domain.

### Failure 3 — Ansprechperson design wrong from M18
**What happened:** Steps 6/6b derived anrede/owner_name from `gf_name`. Roman clarified:
Ansprechperson = highest shareholder = `gesellschafter_name`.
GF = legal representative (may be employee/external). Gesellschafter = owner.

**Fix:** Priority order enforced in normalize: gesellschafter_name > gf_name for owner_name.
Step 6c (gesellschafter fallback) and 6e (gf_name fallback for corporate gesellschafter)
implement this correctly.

## AI VALIDATION RESULTS

Final normalize run (2026-04-28, after all M26 changes):
```
FILL RATES — 482 A/B records (all):
  anrede      :  465/482 ( 96.5%)
  salutation  :  469/482 ( 97.3%)
  street      :  461/482 ( 95.6%)
  plz_ort     :  462/482 ( 95.9%)
  region_prep :  476/482 ( 98.8%)
  leistung    :  479/482 ( 99.4%)
  K1          :  463/482 ( 96.1%)
  K2          :  463/482 ( 96.1%)

FILL RATES — 71 MANUAL filter_pass=1 records (M26 target):
  anrede           :  66/71 (93.0%) ✅
  salutation       :  66/71 (93.0%) ✅
  owner_name       :  66/71 (93.0%) ✅
  street           :  70/71 (98.6%) ✅  ← extended via web search
  plz_ort          :  70/71 (98.6%) ✅
  region_prep      :  69/71 (97.2%) ✅
  leistung_text    :  68/71 (95.8%) ✅
  compliment_draft :  69/71 (97.2%) ✅
  compliment_2     :  69/71 (97.2%) ✅
```

All 9 letter-relevant fields ≥90%. Phase 1 complete.
Only zekamed.de (React SPA, no server-side impressum) remains unresolved — manual lookup needed.

---

## Phase 2: Process Hardening — General Fixes

**Goal:** Next batch of 100 reaches >90% fill in a single automated run. No per-domain manual work.

The Phase 1 fixes were narrow patches (add one word to a blocklist, fix one regex flag, strip
one company name prefix). Phase 2 replaces those with 4 general heuristics that handle the
class of problem, not individual instances.

---

### H1 — Output Shape Validation

**Problem:** Bad extraction results were written silently. "Umsatzsteuer-ID" as a city,
"ATU22821702" as a PLZ, company name prefixes in street — all passed into the DB because
there was no gate between extraction and write.

**Fix:** `validate_address_fields(street, plz, city) -> bool` — one function, called
before any address write. Rules:
- PLZ: exactly 5 digits, no adjacent digits (not part of a registration number)
- City: only letters, hyphens, spaces — no digits, no tokens from a non-city blocklist
- Street: must contain at least one digit (house number)

If any rule fails → write NULL + log reason. Never write a malformed field.

**Scope:** `normalize.py:parse_impressum_address` + any new scraping function.
**Benefit:** Every future edge case (new legal ID format, new country, new website structure)
that produces a malformed result gets rejected automatically.

---

### H2 — External Lookup Match Gate

**Problem:** Handelsregister/OpenRegister returned wrong companies (Megro Hotel for a
medtech domain) because the LIKE search returns nearest text match regardless of relevance.

**Fix:** `validate_company_match(extracted_name, domain, db_full_name) -> bool` — one function,
called after any external lookup. Rule: at least one word from `extracted_name` (>4 chars)
must appear in either `domain` or `db_full_name`. If not → return False, write NULL, log mismatch.

**Scope:** Any function that queries Handelsregister, OpenRegister, or web search for company data.
**Benefit:** Catches any future case where a lookup returns an unrelated company, regardless of
which database or which domain.

---

### H3 — Extraction Failure Reasons

**Problem:** When extraction failed, the record showed empty fields with no explanation.
Debugging required re-running the same scraping logic manually. 24 hours spent on ~15 domains
that failed silently.

**Fix:** Add `scrape_failure_reason` column to `company_records`. Every scraping attempt
that fails writes a short reason: `"impressum_403"`, `"no_impressum_link_found"`,
`"address_shape_invalid"`, `"company_match_rejected"`, `"react_spa_no_ssr"`.

Dashboard surfaces this in the MANUAL REVIEW section per record. Next batch review = scan
the failure reasons, not re-debug from scratch.

**Scope:** `web.py:fetch_impressum_text` + `normalize.py:parse_impressum_address` + H1/H2.
**Benefit:** The failure reason is written once at extraction time. All future batches benefit.

---

### H4 — Cohort-Scoped CLI Defaults

**Problem:** `backfill-leistung`, `backfill-compliments`, `normalize` all default to all A/B
records. WRONG-RECORD-SET fired 3+ times in Phase 1 because the wrong default is easy to
trigger and the feedback (global fill rates) doesn't make the error obvious.

**Fix:** Add `--source` flag to all data-writing pipeline commands. When a new batch is
ingested with a distinct source tag, all commands for that batch use `--source <tag>`.
Default behavior unchanged for existing runs; `--source` adds a WHERE clause.

Also: after every data-writing command, auto-print fill rates for the target cohort only
(not global A/B). If no `--source` given, warn but still run global.

**Scope:** `backfill.py`, `normalize.py` CLI entry points, `pipeline_db.print_fill_rates`.
**Benefit:** WRONG-RECORD-SET becomes structurally impossible when the flag is used.
Auto-verify eliminates BLIND-EXECUTION without needing a separate check step.

---

### Phase 2 Acceptance Criteria

- [ ] H1: `validate_address_fields` implemented + called in `parse_impressum_address` + one new scraping path
- [ ] H2: `validate_company_match` implemented + called in any Handelsregister/web lookup
- [ ] H3: `scrape_failure_reason` column exists + written by scraping + visible in dashboard MANUAL REVIEW
- [ ] H4: `--source` flag on `backfill-leistung`, `backfill-compliments`, `normalize` + auto-verify prints cohort rates

Validation: run full pipeline on a 20-record test cohort. All 4 heuristics fire at least once
(introduce one malformed address, one bad lookup, one cohort filter). Confirm correct behavior.
