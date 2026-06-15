# M7: Ownership Enricher — Plan

## Context

M6 produces `pipeline_stage='classified'` records. M7 enriches A/B companies only with
ownership data (Gesellschafter name, ownership %, birth year, subsidiary/PE flag) so that M8
can apply the hard gate before outreach.

**Why this matters**: Sending an acquisition letter to a subsidiary or PE-backed company is a
wasted credit and a credibility risk. M7 must confirm or rule out corporate ownership before
any company reaches the Serienbriefe export.

---

## What M7 Delivers

For each `pipeline_stage='classified'` AND `klass IN ('A','B')` record:

1. Check `knowledge_base.ownership_cache` — if hit, use cached data (zero API cost)
2. Check ORBIS data — if `gesellschafter_share_pct IS NOT NULL`, use it (zero API cost)
3. Step 1 (free): OffeneRegister GF name lookup by HRB number (if HRB available)
4. Step 2 (paid): OpenRegister.de — only if Steps 1–2 did not yield ownership %
5. Write ownership fields to DB and advance stage

**CRITICAL constraint**: OpenRegister.de is ONLY called for `klass IN ('A','B')` companies.
Never for C, D, or E. Never with `realtime=true`. Always check cache first.

**Stage outcomes:**
- Data found (ORBIS, OffeneRegister, or OpenRegister): `pipeline_stage = 'ownership_enriched'`
- OpenRegister returns no match for an A/B company: `pipeline_stage = 'ownership_review_needed'`

`ownership_review_needed` records are NOT auto-advanced further. M8 skips them. M11 dashboard
surfaces them for manual review. This is intentional — unknown ownership on an A/B company
cannot be assumed safe.

---

## OpenRegister.de API

**Auth**: `Authorization: Bearer {OPENREGISTER_API_KEY}` (from `.env`)

**Call flow per company (11 credits total):**

| Step | Endpoint | Credits | Purpose |
|------|----------|---------|---------|
| 1 | `GET /v1/autocomplete/company?query={full_name}` | 1 | Resolve company_id from name |
| 2 | `GET /v1/company/{company_id}/owners` | 10 | Get shareholders + ownership % |

**Never use:**
- `GET /v0/search/lookup?url=...` — 10 credits for same company_id we get for 1 credit via name
- `realtime=true` — costs extra 10 credits; cached data is sufficient for ownership checks
- `/company-historical-owners` — 25 credits, not needed
- `/company-ubo` — 25 credits, not needed

**Autocomplete match logic:**
- If HRB number known in DB: match result where `register_number` contains the numeric part
- Else: pick first result where `active=True` and `legal_form in ('gmbh','ug','ag','kg')`
- If no match at all: set `pipeline_stage = 'ownership_review_needed'`

**Owners response parsing:**
```json
{
  "owners": [
    {
      "name": "Max Mustermann",
      "type": "natural_person",
      "percentage_share": 100.0,
      "natural_person": { "date_of_birth": "1965-03-15" }
    }
  ]
}
```

- `gesellschafter_name` = name of owner with highest `percentage_share`
- `gesellschafter_share_pct` = their `percentage_share`
- `gesellschafter_age` = birth year from `natural_person.date_of_birth` (4-digit year)
- `is_subsidiary` determination: see Corporate Owners Blocklist section below
- `is_pe_backed` determination: see Corporate Owners Blocklist section below

---

## Corporate Owners Blocklist

**Problem**: Keywords like "holding" or "beteiligungen" are unreliable — they appear in both
personal holdcos (e.g. "Mustermann Verwaltungs-GmbH" = owner's own vehicle) and genuine
corporate parents. Auto-classifying by name keywords produces false positives.

**Solution**: Maintain a curated blocklist of confirmed non-fit corporate owners at:
`src/config/corporate_owners_blocklist.json`

**Logic when a `legal_person` is found as majority owner (>= 75%):**
1. Check if the owner name appears in `corporate_owners_blocklist.json`
   - Match: `is_subsidiary = True` (and `is_pe_backed = True` if entry is tagged as PE)
   - No match: flag for manual review — do NOT auto-decide
2. Set `pipeline_stage = 'ownership_review_needed'` with reason:
   `"Legal entity majority owner ({name}, {pct}%) — not on blocklist, manual review required"`

**When a `natural_person` is the majority owner:**
- `is_subsidiary = False`, `is_pe_backed = False` — proceed normally to `ownership_enriched`

**Blocklist format** (`src/config/corporate_owners_blocklist.json`):
```json
[
  {
    "name": "Siemens Healthineers AG",
    "type": "corporate_parent",
    "notes": "Siemens subsidiary"
  },
  {
    "name": "3i Group",
    "type": "pe_fund",
    "notes": "UK PE fund"
  }
]
```
Matching: case-insensitive substring match on owner name. Grows over time as new cases are confirmed.

---

## Pipeline Stages After M7

| Stage | Meaning |
|-------|---------|
| `ownership_enriched` | Ownership data found; natural person owner confirmed OR blocklist confirmed subsidiary/PE |
| `ownership_review_needed` | A/B company where OpenRegister found no match, OR legal_person majority owner not on blocklist |

---

## DB Fields Written

| Field | Type | Source |
|-------|------|--------|
| `gesellschafter_name` | TEXT | Largest shareholder name |
| `gesellschafter_share_pct` | REAL | Ownership % |
| `gesellschafter_age` | INT | Birth year from date_of_birth |
| `is_subsidiary` | INT (0/1/NULL) | NULL = unknown |
| `is_pe_backed` | INT (0/1/NULL) | NULL = unknown |
| `gf_name` | TEXT | From OffeneRegister (if not already set) |
| `enriched_at` | TEXT | ISO timestamp |
| `pipeline_stage` | TEXT | `'ownership_enriched'` or `'ownership_review_needed'` |
| `ownership_reason` | TEXT | Reason if review_needed |

---

## Files to Create or Modify

| File | Action |
|------|--------|
| `src/pipeline/enrich.py` | Rewrite `enrich_ownership_batch()` — add OpenRegister Step 2, new stage logic |
| `src/config/settings.py` | Add `OPENREGISTER_API_KEY = os.getenv("OPENREGISTER_API_KEY")` |
| `src/config/corporate_owners_blocklist.json` | Create — initially empty list `[]` |
| `ai/ARCHITECTURE.md` | Update M7 section: correct credit costs, new stage names, blocklist |
| `CLAUDE.md` (project-level) | Update External APIs section with correct credit cost (11/company) |

---

## Implementation Sequence

1. Add `OPENREGISTER_API_KEY` to `settings.py`
2. Create `src/config/corporate_owners_blocklist.json` with empty list
3. Implement `_load_corporate_blocklist()` helper
4. Implement `_enrich_ownership_openregister(full_name, hrb_number, domain)`:
   - Autocomplete call → resolve company_id
   - Owners call → parse shareholders
   - Apply blocklist logic
   - Cache result to `knowledge_base.ownership_cache`
5. Rewrite `enrich_ownership_batch()`:
   - Guard: only process `klass IN ('A','B')`
   - Check cache → check ORBIS → check OffeneRegister → call OpenRegister
   - Write stage `'ownership_enriched'` or `'ownership_review_needed'`
6. Write `tests/test_enrich.py` — mock both API calls, cover: natural person owner,
   legal person on blocklist, legal person not on blocklist, API no-result
7. Run live: `python pipeline.py enrich --limit 3 --verbose`
8. Verify DB: stage counts, ownership fields populated
9. Update ARCHITECTURE.md

---

## Validation Steps

```bash
# 1. Dry run — confirm count, zero API calls
python pipeline.py enrich --dry-run --verbose

# 2. Live run on 3 companies
python pipeline.py enrich --limit 3 --verbose

# 3. Pipeline status
python pipeline.py status

# 4. Tests
pytest tests/test_enrich.py -v
```

Expected after live run on current 4 B companies:
- `straetz-novetec.de`: ORBIS data used — 0 credits, stage = `ownership_enriched`
- 3 others: OpenRegister called — 11 credits each = 33 credits, stage depends on result

---

## Credit Budget

| Scenario | Credits |
|----------|---------|
| Current 4 B companies | max 33 (3 × 11) |
| Future run, 50 A/B companies | 550 |
| Future run, 100 A/B companies | 1,100 |
| Monthly plan allowance | 5,000 |

Well within plan for expected A/B volumes.

---

## Deferred

- `realtime=true` — never needed; cached data sufficient
- UBO / beneficial owner chain — not needed for gate logic
- Historical owners — not needed
- Blocklist pre-population — starts empty, grows as cases are confirmed in production

---

## AI VALIDATION RESULTS

**Run date**: 2026-03-26

**Input**: 4 B companies at `pipeline_stage='classified'`

**Results**:
| Company | Source | Owner | Share% | is_subsidiary | Stage |
|---------|--------|-------|--------|---------------|-------|
| straetz-novetec.de | ORBIS (0 credits) | STÜTZ FN GMBH | 50% | NULL | ownership_enriched → email_enriched |
| mamedis.de | OpenRegister (11 credits) | Uwe Dirk Joneck | 33% | False | ownership_gated |
| rennecke-medic.com | OpenRegister (11 credits) | Jana Rennecke | 100% | False | ownership_gated |
| medizintechnik-web.de | OpenRegister (11 credits) | Peter Spranger | 100% | False | ownership_gated |

**Credits used**: 33 (3 × 11 — 1 ORBIS skip)

**Bug found and fixed during validation**:
The M8 gate logic `share_pct >= threshold` triggered on natural person owners (Jana Rennecke
100%, Peter Spranger 100%) — incorrectly reclassifying them to D as "corporate entity owns X%".
Fix: gate's share_pct check now only fires when `is_subsidiary IS NULL` (unknown owner type).
When `is_subsidiary = False` (confirmed natural person), record passes regardless of %.

**dotenv loading fix**: `settings.py` was reading `OPENREGISTER_API_KEY` before dotenv was
loaded. Fixed by calling `load_dotenv()` in `settings.py` before the `os.getenv` call.

**pytest**: 160 passed

**pipeline.py status**: classified=65 (unchanged), ownership_enriched, ownership_gated, email_enriched stages all present.
