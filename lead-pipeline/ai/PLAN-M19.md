# M19: Test Coverage Hardening — classify, export, enrich, dashboard

## Summary

Adds unit tests for the four untested core modules: `classify.py`, `export.py`, `enrich.py`, and `dashboard.py`. Focuses on pure-logic functions (no external API calls, no DB) that are most likely to silently break when prompts or schemas change. Does not add integration tests or mock-heavy orchestration tests — those have diminishing returns and high maintenance cost. Done when: 50+ new tests pass, covering all pure-logic functions in the four modules.

---

## HOW TO EXECUTE THIS MILESTONE

Planning: run `/plan-milestone` — full protocol in `~/.claude/commands/plan-milestone.md`.
Execution: run `/execute-milestone` — full protocol in `~/.claude/commands/execute-milestone.md`.

---

## Locked Decisions

- **Scope: pure-logic functions only.** No mocked API calls, no mocked DB connections, no HTTP handler tests. These are brittle, expensive to maintain, and the failure modes they catch (API response format changes) are not the risk here. The risk is prompt/schema changes silently producing wrong output — pure-logic tests catch that.
- **No changes to production code.** This milestone is test-only. No refactoring to make functions "more testable."
- **Test style matches existing conventions:** pytest classes per function group (see `test_normalize.py`), no conftest.py, direct imports of private functions via `from src.pipeline.classify import _is_obvious_d`.
- **One test file per module:** `test_classify.py`, `test_export.py`, `test_enrich.py`, `test_dashboard.py`.
- **No fixtures directory additions.** Tests use inline data, not fixture files.

---

## Plan

### Phase 1 — `tests/test_classify.py`

**Functions to test (all pure logic, no mocks):**

**1.1 `_is_obvious_d(scraped_text, full_name)`**
- Test: keyword in scraped_text → (True, "Unpassende_Branche")
- Test: keyword in full_name → (True, ...)
- Test: "Handwerk" group keyword (maler, dachdecker, sanitär, etc.) → reason_code "Handwerk"
- Test: non-Handwerk keyword (solar, möbel) → reason_code "Unpassende_Branche"
- Test: no keyword match → (False, "")
- Test: case-insensitive matching
- Test: empty strings → (False, "")

**1.2 `_normalize_company_name(name)`**
- Test: basic lowercasing + whitespace collapse
- Test: strips GmbH, KG, AG, GmbH & Co. KG
- Test: strips international forms (Ltd, Inc, BV)
- Test: preserves umlauts (ä, ö, ü, ß)
- Test: removes punctuation (dots, commas, dashes → spaces)
- Test: empty string → ""
- Test: None → "" (if handled — check signature says `str`, so skip None)

**1.3 `_select_examples(examples, n_per_class)`**
- Test: returns correct count per class with default {A:2, B:1, D:1}
- Test: custom n_per_class respected
- Test: handles fewer examples than requested (graceful degradation)
- Test: empty examples list → empty result

**1.4 `_format_example(ex)`**
- Test: includes company name, domain, text, and JSON output block
- Test: includes klass in output JSON

**1.5 `_build_prompt(profile, full_name, domain, city, region, ma_count, scraped_text)`**
- Test: prompt contains company name and domain
- Test: prompt contains class definitions from profile
- Test: prompt contains few-shot examples
- Test: prompt contains reason codes list
- Test: None city/region/ma_count handled (no "None" literal in prompt)

**1.6 `_parse_result(raw)`**
- Test: valid A/B/C/D/E klass passes through
- Test: invalid klass → "C"
- Test: missing klass → "C"
- Test: valid reason_code passes through
- Test: invalid reason_code → "Unklares_Profil"
- Test: known leistung_category resolves to correct dative noun phrases (e.g. "medizintechnik-service" → leistung_text="Medizintechnik-Dienstleistern")
- Test: unknown leistung_category falls back to LEISTUNG_DEFAULT_CATEGORY
- Test: missing leistung_category → default
- Test: mehrwerte truncated at 400 chars
- Test: reasoning truncated at 200 chars
- Test: services_score cast to int, default 0
- Test: boolean flags cast correctly

_Note: leistung_text and leistung_absatz_2 are no longer free-form AI output truncated to N chars — they are resolved from LEISTUNG_CATEGORIES in settings.py (M20). Tests should verify category resolution, not truncation._

### Phase 2 — `tests/test_export.py`

**Functions to test (all pure logic, no mocks):**

**2.1 `_parse_name(full_name)`**
- Test: "Klaus Müller" → ("Klaus", "Müller")
- Test: "Klaus Peter Müller" → ("Klaus", "Peter Müller")
- Test: "Müller" (single name) → ("", "Müller")
- Test: "" → ("", "")
- Test: None → ("", "")
- Test: leading/trailing whitespace stripped

**2.2 `_parse_compliment_json(text)`**
- Test: valid JSON → (k1, k2)
- Test: JSON wrapped in markdown fences → (k1, k2)
- Test: missing k1 key → (None, k2) or (None, None)
- Test: empty string → (None, None)
- Test: invalid JSON → (None, None)

**2.3 `_record_to_row(rec, raw)`**
- Test: A-record maps all 36 columns correctly
- Test: B-record gets "Prio 1" priority
- Test: C-record gets empty priority
- Test: None/empty fields → empty strings (no "None" literals)
- Test: region_prep preferred over region
- Test: outreach tracking fields pulled from raw dict
- Test: owner_name splits into First Name / Last Name columns correctly

### Phase 3 — `tests/test_enrich.py`

**Functions to test (all pure logic, no mocks):**

**3.1 `_is_natural_person_name(name)`**
- Test: "Klaus Müller" → True
- Test: "Müller Medizintechnik GmbH" → False
- Test: "Seidel" → True (word boundary: "se" in "Seidel" must NOT match)
- Test: "Hagemann" → True (word boundary: "ag" in "Hagemann" must NOT match)
- Test: "Deutsche Holding AG" → False
- Test: "" → False
- Test: None → False

**3.2 `_is_on_blocklist(owner_name, blocklist)`**
- Test: exact match → returns entry
- Test: substring match → returns entry
- Test: case-insensitive matching
- Test: no match → None
- Test: empty blocklist → None

**3.3 `_parse_owners(owners, blocklist)`**
- Test: single natural person majority owner → is_subsidiary=False, is_pe_backed=False
- Test: natural person with birth year → gesellschafter_age set
- Test: legal person on blocklist (type=corporate_parent) → is_subsidiary=True
- Test: legal person on blocklist (type=pe_fund) → is_pe_backed=True
- Test: legal person NOT on blocklist → needs_review=True
- Test: 50/50 natural + legal → natural person preferred (key sort logic)
- Test: empty owners list → needs_review=True, review_reason="OpenRegister returned empty owners list"
- Test: unknown owner type → needs_review=True

**3.4 `_derive_anrede(first_name)`**
- Test: "Klaus" → "Herr" (known male name)
- Test: "Sabine" → "Frau" (known female name)
- Test: "Andrea" → "Frau" (ends in 'a' heuristic)
- Test: "" → None
- Test: unknown name not ending in a/e/i → None

**3.5 `_normalise_name_for_email(name)`**
- Test: "Müller" → "mueller"
- Test: "Größe" → "groesse"
- Test: "Straße" → "strasse"
- Test: "Klaus" → "klaus"
- Test: strips non-ascii after umlaut replacement
- Test: preserves hyphens in names (e.g. "Meyer-Schmidt" → "meyer-schmidt")

**3.6 `_build_owner_email_candidates(gesellschafter_name, domain)` — mock only `_scrape_email_pattern`**
- Test: "Klaus Müller" + "example.de" → 8 candidates in correct order
- Test: candidate patterns: klaus.mueller@, k.mueller@, mueller@, klaus@, klausmueller@, kmueller@, klaus.m@, k.m@
- Test: single-word name → empty list
- Test: three-part name "Uwe Dirk Joneck" → uses first="uwe", last="joneck"
- Note: mock `_scrape_email_pattern` to return None (no website pattern) for these tests

### Phase 4 — `tests/test_dashboard.py`

**Functions to test (pure logic only):**

**4.1 `_build_html(data, serve_mode, logo_b64, hubspot_portal_id)`**
- Test: output contains `__DATA_JSON__` replacement (data embedded as JSON string)
- Test: serve_mode=True → `__SERVE_MODE_JS__` = "true"
- Test: serve_mode=False → `__SERVE_MODE_JS__` = "false"
- Test: serve_mode=True → `__LIVE_BADGE__` = "LIVE"; serve_mode=False → "STATIC"
- Test: `__DATE_STR__` replaced with today's date (format YYYY-MM-DD)
- Test: logo_b64 non-empty → output contains `<img class="header-logo"`
- Test: hubspot_portal_id embedded in output
- Test: `__REGION_MAPPING_JSON__` replaced (output does not contain literal `__REGION_MAPPING_JSON__`)
- Note: requires the template file to exist at `src/pipeline/templates/dashboard.html`
- Note: `_build_html` calls `load_region_mapping()` internally — patch it in the test to return `{}`

**4.2 `_load_logo_b64(logo_path)`**
- Test: missing file → ""
- Test: valid PNG file → starts with "data:image/png;base64,"

---

### Phase 0 — Pre-execution doc cleanup (no production code changes)

**Pre-M19 code changes are complete** (commits a37b007, 82cae41):
- ingest.py: `gf_name` → `owner_name` for ORBIS contact person ✅
- check_letter.py: assembled paragraph prompt ✅

**0.1 `ai/ARCHITECTURE.md` — fix stale function names from pre-M19 rename**
- `enrich_gf_name(gf_name, gesellschafter_name)` → `enrich_owner_name(owner_name, gesellschafter_name)`
- `build_salutation(anrede, gf_name)` → `build_salutation(anrede, owner_name)`
- Lines 128, 206 still reference gf_name in the wrong context
- These are in the "Module Responsibilities" section for `normalize.py`

**0.2 `ai/ROADMAP.md` — mark pre-M19 Open Issues resolved**
- `gf_name column misnamed` → ✅ resolved (commits a37b007)
- `check-letter checks K1/K2 in isolation` → ✅ resolved (commit 82cae41)

---

## Better Engineering Notes

- **Why no integration tests**: The orchestration functions (`classify_cmd`, `export_cmd`, `enrich_cmd`) are wrappers that call DB + external APIs + pure logic. Testing them requires extensive mocking of DB connections, API responses, and file I/O — these tests are brittle (break when implementation changes even if behavior is correct) and rarely catch real bugs. The pure-logic functions are where silent breakage actually happens (prompt output parsing, field mapping, name normalization).
- **Future M20 candidate**: If integration tests are ever needed, consider a `tests/fixtures/test.db` with a known set of ~10 records and run `classify_cmd(dry_run=True)` against it. But that's separate scope.
- **`_build_owner_email_candidates` is the only test that needs a mock** — `_scrape_email_pattern` makes HTTP calls. Use `unittest.mock.patch` on the function, return None. This is one mock per test function, not a complex mock setup.
- **Dashboard `_build_html` requires the template file** — this is a real file dependency, not a mock. The test verifies the template rendering, so it must read the actual template. This is an intentional design choice.

---

## AI Validation Plan

**Commands:**
```bash
pytest tests/test_classify.py tests/test_export.py tests/test_enrich.py tests/test_dashboard.py -v
pytest tests/ -q  # full suite — no regressions
python pipeline.py status  # confirm no side effects
```

**Expected outputs:**
- `test_classify.py`: ~25 tests pass
- `test_export.py`: ~15 tests pass
- `test_enrich.py`: ~25 tests pass
- `test_dashboard.py`: ~8 tests pass
- Total new tests: ~73
- Full suite: 288 existing + ~73 new = ~361 tests, all green
- `pipeline.py status`: unchanged from pre-milestone (no data changes)

**Failure definition:**
- Any test failure
- Any existing test regression
- `pipeline.py status` shows different counts than before

---

## AI Validation Results

**Commands run:**
```bash
pytest tests/test_classify.py tests/test_export.py tests/test_enrich.py tests/test_dashboard.py -v
pytest tests/ -q
python pipeline.py status
```

**Results (2026-03-31):**
- `test_classify.py`: 46 tests — all pass
- `test_export.py`: 21 tests — all pass
- `test_enrich.py`: 39 tests — all pass
- `test_dashboard.py`: 14 tests — all pass
- Total new tests: **120** (plan estimated ~73; actual higher due to broader `_parse_result` category coverage and fuller `_record_to_row` coverage)
- Full suite: **408 passed** in 3.58s — zero regressions
- `pipeline.py status`: 2,420 records, A=100, B=298, C=4, D=117, E=3 — unchanged

**Deviations from plan:**
- `_parse_result` truncation tests replaced with category resolution tests (plan was updated after M20 changed leistung_text from free-form to LEISTUNG_CATEGORIES lookup)
- `_build_html` requires patching `src.pipeline.region_lookup.load_region_mapping` (local import inside function) — patch target is the module, not `dashboard.load_region_mapping`
- `_make_profile()` test helper required `ownership=OwnershipConfig()` and `export=ExportConfig()` (IndustryProfile has required fields not reflected in plan spec)
- `test_dashboard.py` uses real template file (no mock) — design choice confirmed by plan's Better Engineering Notes

**PM Review verdict:** PASS

**PM Review notes:**
- 120 tests delivered vs ~73 estimated — higher coverage is positive; no scope creep (tests only)
- Highest-value tests: `_parse_owners` ownership gate logic, `_parse_result` category resolution, `_record_to_row` None-literal prevention — these protect against silent letter output corruption
- No integration tests (intentional, per locked decisions) — pure-logic coverage is the right call at this scale
- No production code changes

---

## User Validation Walkthrough

1. Run `pytest tests/test_classify.py -v` — all green, covers `_is_obvious_d`, `_normalize_company_name`, `_parse_result`, etc.
2. Run `pytest tests/test_export.py -v` — all green, covers `_parse_name`, `_parse_compliment_json`, `_record_to_row`
3. Run `pytest tests/test_enrich.py -v` — all green, covers `_is_natural_person_name`, `_parse_owners`, `_derive_anrede`, `_normalise_name_for_email`, `_build_owner_email_candidates`
4. Run `pytest tests/test_dashboard.py -v` — all green, covers `_build_html`, `_load_logo_b64`
5. Run `pytest tests/ -q` — full suite passes, no regressions
6. Run `python pipeline.py status` — same counts as before (no side effects)
7. Spot-check: open `test_enrich.py`, verify `_parse_owners` tests cover the natural-person vs legal-person vs blocklist paths — these are the most business-critical assertions (ownership gate correctness)
