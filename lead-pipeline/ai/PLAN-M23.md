# M23: Letter Quality Gate + Text Hardening

## Summary

Adds a completeness gate to PDF export (skips records with missing fields instead of rendering broken letters), German umlaut restoration for AI-generated text, and rule-based compliment grammar fixes. Dashboard and check-letter completeness definitions aligned with PDF gate.

## Locked Decisions

1. Skip incomplete records (don't block entire export) — log which domains were skipped and why
2. Conservative umlaut allowlist (~80 entries) — only unambiguous ae/oe/ue→ä/ö/ü substitutions
3. Rule-based compliment fixes — strip known bad prefixes, flag missing verbs. No AI validation in export path
4. No address auto-fill — flag as incomplete; manual entry via dashboard
5. Excel export unchanged — quality gate only on PDF export

## Plan

### Step 1: German umlaut restoration for AI text
- Added `_GERMAN_UMLAUT_WORDS` dict (~80 entries) in `normalize.py`
- Added `restore_umlauts_german(text)` function — splits on whitespace, checks against map
- Integration: `normalize_cmd()` step 9b, `export.py` `_parse_compliment_json()`, `backfill.py` `_parse_json_response()`

### Step 2: Compliment grammar post-processing
- Added `fix_compliment_text(k1, k2)` in `normalize.py`
- K1: strips "Besonders "/"Auch " prefix, trailing period, lowercases after strip
- K2: strips "Auch " prefix, trailing period, warns if missing "hat"/"haben"
- Integration: same three points as Step 1

### Step 3: PDF export completeness gate
- Added `REQUIRED_LETTER_FIELDS` constant (10 fields) in `export_pdf.py`
- Added `check_record_completeness(data)` — returns list of missing field names
- Modified `export_pdf_cmd()`: check each record, skip incomplete, log reasons, only render complete

### Step 4: Dashboard completeness alignment
- Added `street` and `plz_ort` to `completenessHtml()` and `prepCompletenessPct()`
- Denominator updated from 11 to 13

### Step 5: check_letter.py alignment
- Added `mehrwerte` to `_REQUIRED_FIELDS` (was missing)
- Changed `gf_email` severity from error to warning (not in letter)

### Step 6: Normalize + re-export
- `python pipeline.py normalize` → 25 AI text fixes (8 K1, 7 K2, 10 mehrwerte)
- `python pipeline.py export-pdf` → 14 complete letters, 20 skipped

### Step 7: Tests
- 20 new tests across test_normalize.py, test_export_pdf.py, test_check_letter.py
- Updated 4 existing tests in test_m16.py to reflect post-processing behavior

## AI Validation Results

### Commands run
```
pytest tests/ -x -q → 467 passed in 8.56s
python pipeline.py normalize --dry-run → 25 AI text fixes (8 K1, 7 K2, 10 mehrwerte)
python pipeline.py normalize → Written: 13 records (AI fixes) + 7 records (name/address)
python pipeline.py export-pdf --dry-run → 14 records would render, 20 skipped with reasons
python pipeline.py export-pdf → 14 letters → serienbriefe_20260401.pdf (20 skipped)
```

### Observations
- K2 verb warnings correctly flagging 9 records missing "hat"/"haben"
- Most common missing fields: anrede/salutation (14), street/plz_ort (10), compliment_draft/2 (8)
- Umlaut fixes hit: Prüfung, Röntgen, für, über, Geräte, Qualität, etc.

## Files Modified

| File | Change |
|------|--------|
| `src/pipeline/normalize.py` | `_GERMAN_UMLAUT_WORDS`, `restore_umlauts_german()`, `fix_compliment_text()`, step 9b in `normalize_cmd()` |
| `src/pipeline/export_pdf.py` | `REQUIRED_LETTER_FIELDS`, `check_record_completeness()`, completeness gate in `export_pdf_cmd()` |
| `src/pipeline/export.py` | `_parse_compliment_json()` calls umlaut+grammar post-processing |
| `src/pipeline/backfill.py` | `_parse_json_response()` applies umlaut restoration; `_generate_k2_only_cli()` applies grammar fix |
| `src/pipeline/check_letter.py` | Added `mehrwerte` to required fields, `gf_email` → warning severity |
| `src/pipeline/templates/dashboard.html` | Added street/plz_ort to completeness checks, denominator 11→13 |
| `tests/test_normalize.py` | 12 new tests for umlaut + compliment functions |
| `tests/test_export_pdf.py` | 4 new tests for completeness gate |
| `tests/test_check_letter.py` | Updated 2 existing tests for new field + severity |
| `tests/test_m16.py` | Updated 4 tests for post-processing behavior |
