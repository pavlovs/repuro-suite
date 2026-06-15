# Batch Readiness Specification

## What This Is

The standard a batch of company records must meet before Briefaktion send-out. Applies to
every batch (BA1, BA2, … BA8, BA+1). The batch identifier is the `briefaktion` column in
`company_records`. The pending (not-yet-sent) batch has `briefaktion IS NULL`.

This spec is the acceptance criteria for:
- Milestone completion (M26 and any future data-prep milestone)
- `/batch-control` health checks
- Codex review of normalize.py / enrich.py changes ("does this maintain batch readiness?")

---

## Batch Cohort Query

```sql
-- Pending batch (pre-send):
SELECT * FROM company_records
WHERE briefaktion IS NULL
  AND filter_pass = 1
  AND klass IN ('A', 'B')

-- Specific batch (e.g. BA8):
SELECT * FROM company_records
WHERE briefaktion = 'BA8'
  AND klass IN ('A', 'B')
```

> **Never use `source='MANUAL'` as a batch filter** — `source` is the ingestion method
> (ORBIS, WLW, MANUAL), not the batch. MANUAL is only the ingestion source for BA8.
> Future batches may use ORBIS or WLW source. Use `briefaktion` for batch identity.

---

## Required Fields and Thresholds

All fields below must reach **>90% fill rate** across the batch before send-out approval.

| Field | DB Column | How It's Populated | Blocking If Missing |
|-------|-----------|-------------------|---------------------|
| Company name | `full_name` | Ingestion | Yes — letter header |
| Anrede | `anrede` | normalize step 6/6b/6c | Yes — salutation |
| Salutation | `salutation` | normalize step 9 | Yes — letter greeting |
| Ansprechpartner | `owner_name` | normalize step 6c (from gesellschafter_name) | Yes — Vorname/Nachname at export |
| Street | `street` | normalize step 9a (impressum) | Yes — postal address |
| PLZ + Ort | `plz_ort` | normalize step 9a (impressum) | Yes — postal address |
| Region | `region_prep` | normalize step 8 | Yes — letter body |
| Leistung | `leistung_text` | backfill-leistung | Yes — letter body |
| Kompliment 1 | `compliment_draft` | backfill-compliments | Yes — letter body |
| Kompliment 2 | `compliment_2` | backfill-compliments | Yes — letter body |

**Warning-only (not blocking):**
| Field | DB Column | Notes |
|-------|-----------|-------|
| GF email | `gf_email` | For follow-up — not in letter |
| GF name | `gf_name` | Fallback for anrede; secondary to gesellschafter_name |

---

## Field Derivation Logic (canonical)

### Ansprechperson priority (normalize.py)
```
Step 6:   owner_name already set → derive anrede from owner_name first name
Step 6b:  gf_name set, owner_name missing → derive anrede + set owner_name from gf_name
Step 6c:  gesellschafter_name set, still no anrede → derive anrede + set owner_name
          (ONLY if gesellschafter_name passes _is_natural_person_name()
           AND does NOT match _LEGAL_ENTITY_RE)
```
Rule: **Ansprechperson = highest shareholder** (gesellschafter_name), not the GF.
GF is the legal representative. The letter should reach the owner.

### Address priority (normalize.py step 9a)
```
1. Labeled patterns in impressum: "Straße: ...", "PLZ / Ort: ..."
2. Structural: 5-digit PLZ anchor → city word after → street in preceding 60 chars
```
Prerequisite: impressum text must exist in `knowledge_base.db` for the domain.

### Anrede derivation (_derive_anrede in enrich.py)
```
1. Dr./Prof. prefix → skip (return None — title is not a first name)
2. Accent normalization: René → rene (unicodedata NFD)
3. Name list lookup (accented + ASCII variant)
4. Compound name: Karl-Peter → check Karl
5. Vowel heuristic: endings a/e/i → Frau
6. None if uncertain
```

---

## Known Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| anrede=None for Turkish/Arabic names | Name not in list; no vowel match | Expand `_MALE_NAMES` / `_FEMALE_NAMES` in enrich.py |
| anrede=None for "Dag", "Becker" → misclassified as corporate | `_LEGAL_ENTITY_RE` false positive (case) | Check regex doesn't have `re.IGNORECASE` on abbreviations |
| street empty despite impressum in KB | PLZ-anchor regex misses multi-word cities ("Bad Homburg") | Fix `_PLZ_CITY_RE` to allow 2-word city names |
| street captured company name ("Artikel GmbH Str. 5") | `_clean_street()` didn't strip prefix | Add company name prefix to `_clean_street()` strip list |
| owner_name empty despite gesellschafter_name set | gesellschafter_name is a holding company name | Requires manual UBO resolution or OpenRegister lookup |
| All fields empty for a domain | Impressum content empty in knowledge_base.db | Re-scrape: `python pipeline.py scrape --domains <domain>` |
| region_prep empty | plz_ort empty (dependent field) or region mapping miss | Fix plz_ort first; check region_lookup.py for PLZ range |

---

## Acceptance Criteria for Send-Out

A batch is ready for send-out when ALL of the following are true:

1. **Fill rate**: Every required field above >90% across the batch cohort
2. **No nulls on critical fields**: `full_name`, `anrede`, `street`, `plz_ort` — 0 nulls for `approved_for_sendout=1` records
3. **Codex grammar check passed**: `/codex-review dev` on normalize.py + enrich.py shows no regressions
4. **Letter preview**: at least 5 records spot-checked via `check_letter.py`
5. **`approved_for_sendout` set**: flip to 1 only after all above pass

---

## Batch History

| Batch | Records | Source | Sent |
|-------|---------|--------|------|
| BA1 | 95 | ORBIS + WLW | Yes |
| BA2 | 44 | ORBIS + WLW | Yes |
| BA3 | 45 | ORBIS | Yes |
| BA4 | 23 | WLW | Yes |
| BA5 | 53 | ORBIS | Yes |
| BA6 | 33 | ORBIS + WLW | Yes |
| BA7 | 74 | ORBIS + WLW | Yes |
| BA8 | 71 | MANUAL | In progress (M26) |
| BA9+ | TBD | ORBIS/WLW/new | — |
