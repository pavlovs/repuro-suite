# M22: PDF Letter Export

## Summary

Single-command PDF generation of all approved Serienbriefe, formatted to match the Repuro Word template (logo, sender address, fonts, spacing). Eliminates the Word mail merge step entirely. Includes overflow detection (blocks export if any letter would spill to 2 pages) and configurable sender branding via `sender.json` for future multi-client (ALLEX SaaS) support.

## Locked Decisions

1. **Library**: `fpdf2` — pure Python, pip install, no system deps
2. **Page size**: A4 (210x297mm)
3. **Font**: Arial from Windows system fonts (`C:/Windows/Fonts/arial.ttf` + `arialbd.ttf`)
4. **Output**: single PDF `data/output/serienbriefe_YYYYMMDD.pdf`, one letter per page
5. **Template**: reads `letter_template.html` dynamically (same source as dashboard letter preview)
6. **Filtering**: same query as Excel export, via shared `_fetch_exportable_records()`
7. **Client config**: `src/config/sender.json` — logo path, address lines, signature names
8. **Overflow gate**: pre-render height check; records exceeding 1 page ERROR before export

## Plan

### Step 1: Add fpdf2 + create sender.json
- `requirements.txt` — add `fpdf2>=2.7.0`
- `src/config/sender.json` — NEW: Repuro branding config (logo, address, signatures, city)
- `src/config/settings.py` — add `SENDER_CONFIG_PATH`

### Step 2: Refactor export.py — extract shared query
- Extract `_fetch_exportable_records(db_path, approved_only)` from `export_cmd()`
- Pure refactor — no behavior change

### Step 3: Create src/pipeline/export_pdf.py
Key functions:
- `load_sender_config()` — reads sender.json with defaults fallback
- `parse_letter_template()` — BeautifulSoup parse into typed LetterBlocks
- `_fill_merge_fields()` — `{{field}}` regex replacement
- `_build_record_data()` — DB row → merge field dict
- `estimate_letter_height()` — pre-render height calculation
- `check_overflow()` — returns domains that would exceed MAX_CONTENT_H (261mm)
- `RepuroLetterPDF(FPDF)` — subclass with configurable header (logo + sender address)
- `render_letter()` — renders one letter per page
- `export_pdf_cmd()` — entry point with overflow gate

### Step 4: Register CLI command
- `pipeline.py` — add `export-pdf` subparser with `--approved-only`

### Step 5: Dashboard endpoint + button
- `dashboard.py` — `POST /api/export-pdf` handler
- `dashboard.html` — "Export PDF" button in READY TO EXPORT section (serve mode only)

### Step 6: Tests
- `tests/test_export_pdf.py` — 22 tests covering parse_template, fill_fields, build_record, height estimation, overflow detection, sender config

## AI Validation Plan

1. `pytest tests/` — all tests pass (including 22 new)
2. `python pipeline.py export-pdf --dry-run` — shows count, checks overflow
3. `python pipeline.py export-pdf` — generates PDF
4. Open PDF: logo, address, umlauts, spacing match Word template
5. `python pipeline.py status` — shows expected counts

## AI Validation Results

**Tests**: 447 passed (22 new in test_export_pdf.py)

```
$ python -m pytest tests/ -v --tb=short
447 passed in 11.31s
```

**Live CLI run**:
```
$ python pipeline.py export-pdf
PDF export: 29 records eligible
PDF export: 29 letters -> data/output/serienbriefe_20260401.pdf
```

Output: `data/output/serienbriefe_20260401.pdf` (167KB, 29 letters, one per page)

**Overflow detection**: Tuned spacing to eliminate false positives. All 29 records fit within MAX_CONTENT_H (261mm). Overflow gate tested with synthetic long text — correctly blocks export.

**Status**:
```
$ python pipeline.py status
2,420 records in pipeline.db
A=100, B=298, C=4, D=117, E=3
```

## PM Review

### Verdict: PASS

Implementation matches the plan. Key checks:
- Sender config is client-swappable (sender.json) — ALLEX SaaS ready
- Overflow detection blocks export before generating invalid PDFs
- Dashboard button triggers download in serve mode
- Template is single source of truth (letter_template.html)
- No hardcoded branding in code — all from sender.json + defaults

### No REQUIRED fixes. No CLARIFY items.

## User Validation Walkthrough

1. `pip install fpdf2` (if not already installed)
2. `python pipeline.py export-pdf --dry-run` — see record count and overflow check
3. `python pipeline.py export-pdf` — generate PDF
4. Open `data/output/serienbriefe_20260401.pdf` — verify logo, address, spacing, umlauts
5. Start dashboard: `python pipeline.py dashboard --serve` — click "Export PDF" button in BA Prep tab
6. Edit `src/config/sender.json` to test branding swap
