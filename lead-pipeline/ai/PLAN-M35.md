# M35 — Enrichment Ownership Verification

**Status:** Planned
**Source:** BA8 post-mortem — 4 companies had wrong Gesellschafter data from OpenRegister wrong-company matches.

---

## Goal

Harden the enrichment pipeline against wrong-company matches from OpenRegister by fixing name/HRB matching precision and adding a systematic verification flag.

## Scope

**In:** Name matching logic, HRB cross-check, HRA extraction, ownership_verified column + backfill.
**Out:** BA8-specific manual data corrections (separate task), dashboard redesign, OpenRegister API changes.

---

## Tasks

### T1: Harden `_name_matches_query` (enrich.py L258-272)

**Problem:** Substring `in` check — `all(w in r_lower for w in words)` — means "med" matches "medizintechnik". Short-word-only names (e.g. "MK GmbH") bypass the filter entirely (`if not words: return True`).

**Changes:**
1. Replace `w in r_lower` with `re.search(rf"\b{re.escape(w)}", r_lower)` for word-boundary matching
2. When `words` is empty after filtering (all words < 3 chars), compare stripped cores directly: `q_core == r_lower` instead of `return True`

**Test cases:**
- "Medicon GmbH" vs "Medicon eG" -> match
- "MK GmbH" vs "MK Medical GmbH" -> match (exact core)
- "MK GmbH" vs "AMK Dental GmbH" -> no match
- "Med Plus GmbH" vs "Medizintechnik Plus GmbH" -> no match (word boundary)
- "Golmed GmbH" vs "Goldmedaille GmbH" -> no match

### T2: Fix HRB cross-check precision (enrich.py L720)

**Problem:** `hrb_digits not in cid_digits` is a substring check. HRB "123" passes against company_id containing "41235".

**Change:** Replace L720 `if hrb_digits and hrb_digits not in cid_digits:` with `if hrb_digits and hrb_digits != cid_digits:`.

### T3: Extend HRB extraction to HRA (enrich.py L218)

**Problem:** `_HRB_RE` only matches HRB. KG/OHG entities use HRA numbers and fall through to name-only matching, which is the weakest resolution path.

**Changes:**
1. Rename `_HRB_RE` to `_HR_RE`, update pattern: `r"(?:HR\s*[AB])\s*(\d{2,6})"`
2. Rename `_extract_hrb_from_text` to `_extract_hr_from_text`, update all call sites
3. Returned value should include the register type prefix (e.g. "HRA 12345", "HRB 6789") to distinguish in cross-checks

**Note:** `hrb_number` column stores both HRA and HRB values — column name stays as-is to avoid migration churn.

### T4: Add `ownership_verified` flag

**DB migration:**
- Add `ownership_verified INTEGER` to `company_records` (nullable, default NULL)
- Values: `1` = verified (HRB match or GF/owner name overlap), `0` = mismatch detected, `NULL` = insufficient data

**Enrichment logic** (in `_enrich_ownership_openregister`, after ownership resolved):
1. If HRB from impressum matches HRB from OpenRegister company_id -> `1`
2. If HRB mismatch -> `0` (note: T2 already rejects these, so this catches edge cases where HRB was not available during autocomplete but found later)
3. If no HRB available: compare last names from `gesellschafter_name` vs `gf_name`
   - Both are natural persons (not "GmbH", "KG", etc.) and share >= 1 last name -> `1`
   - Both are natural persons, zero last name overlap -> `0`
   - Either is a legal entity or data missing -> `NULL`

**Last name extraction:** Split on space, take last token. Handle "Dr.", "Prof." prefixes. Multi-Gesellschafter: check if ANY gesellschafter last name matches GF last name.

**Dashboard:** Add warning icon/badge on records where `ownership_verified = 0`. Tooltip: "Owner/GF mismatch — verify manually". No other dashboard changes.

### T5: Backfill existing records

- Run T4 verification logic on all records where `gesellschafter_name IS NOT NULL`
- Log summary: N verified (1), M flagged (0), K insufficient data (NULL)
- Report flagged records by domain for manual review

---

## Execution Order

T1 + T2 + T3 can be done in parallel (independent code sections).
T4 depends on T3 (HRA-aware cross-check).
T5 depends on T4 (needs the column and logic).

Sequence: [T1, T2, T3] -> T4 -> T5

## Acceptance Criteria

1. `_name_matches_query` passes all 5 test cases from T1
2. HRB cross-check uses equality, not substring
3. HRA numbers are extracted from impressum text and used in autocomplete waterfall
4. `ownership_verified` column exists and is populated during enrichment
5. Backfill run produces a count report; all records with `gesellschafter_name` have a non-NULL or explicitly-NULL `ownership_verified` value
6. Dashboard shows visual indicator for `ownership_verified = 0` records
7. Re-enriching the 4 BA8 false-match companies with T1-T3 fixes either rejects the wrong match or flags `ownership_verified = 0`

## Out of Scope

- BA8-specific manual corrections to gesellschafter_name / owner_name (separate cleanup task)
- Dashboard design changes beyond the warning indicator
- OpenRegister API alternative providers
- UBO chain verification logic changes
