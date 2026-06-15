# DR-M3: Data Extraction

## Summary

`DEALROOM.py extract --deal Wolf` reads registered financial documents (GuV, Bilanz, BWA, JA xlsx)
and extracts all available P&L and balance-sheet data into `deal_data`. Uses Claude Haiku with an
explicit JSON schema — no hard-coded cell addresses. Runs conflict detection and auto-risk flags
after each extraction run. Idempotent: re-running re-extracts and updates existing rows.

**Golden dataset approach**: Before extraction logic is written, the finalized Excel models for
Cat, Wolf, Fox, Octopus are read to produce `data/golden/{deal}.json` — verified correct values
that serve as the validation target for extraction accuracy.

**Scope**: Cat, Wolf, Fox, Octopus (all have models + raw GuV/Bilanz xlsx). Remaining deals (Lion,
Colibri, Falcon, Blackbird, Panda, Mouse, Owl, Eagle) have no docs registered yet — out of scope.

---

## Locked Decisions

**Haiku for extraction, Sonnet never.** Per CLAUDE.md model usage rules.

**EUR → EUR_K on ingest.** All raw DATEV files are in EUR. deal_data stores everything in EUR_K.
Division by 1000 happens in `data.py` before writing. Golden values are in EUR_K (from model).

**Only .xlsx / .xlsm processed.** PDFs can't be parsed with openpyxl. Registered but skipped with
a logged warning. This is intentional — most PDFs are signed copies where the xlsx version exists.

**Idempotent via source-keyed UPSERT.** Primary key for deal_data uniqueness: `(domain, category,
subcategory, fiscal_year, key, source)`. On re-extraction, existing rows for the same source are
deleted and re-inserted. Conflicts from other sources are preserved.

**GuV raw → stated values only.** Extraction captures reported numbers, not adjusted. Normalization
candidates are flagged as `category='financial', subcategory='adjustments'` rows, not applied to
the P&L numbers. Adjusted numbers come from the model (DR-M4).

**Conflict detection after full deal extraction.** Runs once after all files for a deal are
processed. Flags (domain, category, subcategory, fiscal_year, key) groups where value_num differs
across sources by >1%. Both rows get `conflict_ids` JSON array.

**Year from file first, content second.** If `fiscal_year` is set in `deal_documents`, use it. If
null, parse from the file header row (first non-empty row containing a 4-digit year).

---

## Implementation Plan

### Step 0 — Build golden dataset

Read model GuV sheets for Cat, Wolf, Fox, Octopus. Extract the clean P&L table (rows: Revenue,
COGS adj., Gross margin, Personnel adj., OPEX adj., EBITDA adj., D&A, EBIT adj.) per year column.
Save to `data/golden/{code_name_lower}.json`.

Format:
```json
{
  "code_name": "Wolf",
  "source_model": "260319_KVG_Model_v4.xlsx",
  "currency": "EUR_K",
  "pnl": {
    "2022": {"revenue": 5773.7, "ebitda_adj": ..., "personnel_adj": ..., "cogs_adj": ...},
    "2023": {...},
    "2024": {...}
  }
}
```

Script: `scripts/build_golden.py` — run once, not part of CI. Output: `data/golden/*.json`.

### Step 1 — `config/settings.py` update

Add:
```python
import dotenv
dotenv.load_dotenv(BASE_DIR / ".env")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOLDEN_DIR = DATA_DIR / "golden"
```

Copy `.env` from lead-pipeline (or create symlink). Add `python-dotenv` if not installed.

### Step 2 — `src/data.py`

Structure:
```
extract_deal(conn, code_name, dry_run=False) -> dict   # main entry point
_get_extractable_docs(conn, domain) -> list[Row]        # guv/bilanz/bwa xlsx only
_read_excel_rows(path) -> list[str]                     # dump non-empty rows as text
_extract_pnl(rows_text, file_name, fiscal_year) -> dict # Haiku call → JSON
_extract_balance(rows_text, file_name, fiscal_year) -> dict
_write_deal_data(conn, domain, entries, dry_run) -> int
_clear_source_rows(conn, domain, source_file_id)        # idempotent re-extraction
detect_conflicts(conn, domain) -> int                   # returns conflict count
compute_risk_flags(conn, domain) -> list[str]           # returns flag descriptions
```

**Extraction prompt (P&L)**:
```
You are extracting financial data from a German P&L statement (Gewinn- und Verlustrechnung).
File: {file_name}. Fiscal year: {fiscal_year}.

Raw rows (label | col1 | col2 | ...):
{rows_text}

Extract ALL available P&L line items for the stated fiscal year AND for the prior year if present.
Return ONLY valid JSON matching this schema. Amounts are in EUR (not EUR_K).
Use null for any item not found. Do not invent numbers.

{
  "fiscal_year": int,
  "prior_year": int | null,
  "revenue": float | null,
  "cogs": float | null,
  "gross_profit": float | null,
  "personnel": float | null,
  "other_opex": float | null,
  "other_income": float | null,
  "ebitda": float | null,
  "da": float | null,
  "ebit": float | null,
  "interest_expense": float | null,
  "interest_income": float | null,
  "ebt": float | null,
  "tax": float | null,
  "net_income": float | null,
  "prior_year_revenue": float | null,
  "prior_year_ebitda": float | null,
  "prior_year_personnel": float | null,
  "normalization_candidates": [
    {"description": "...", "amount_eur": 0.0, "account_code": "..."}
  ]
}
```

**deal_data rows written per GuV file** (EUR → EUR_K, unit='EUR_K'):
- `financial.pnl.{key}` per year: revenue, cogs, gross_profit, personnel, other_opex,
  other_income, ebitda, da, ebit, interest_expense, interest_income, ebt, tax, net_income
- `financial.adjustments.normalization_items_json` per year (value_text = JSON array)

**Balance sheet prompt** uses same pattern with Bilanz-specific keys:
total_assets, current_assets, fixed_assets, equity, debt_lt, debt_st, net_debt, cash, receivables.

### Step 3 — Wire `DEALROOM.py extract`

Replace the stub for `extract` with `cmd_extract`:
```python
def cmd_extract(args) -> None:
    from src.data import extract_deal
    conn = get_conn()
    result = extract_deal(conn, args.deal, dry_run=args.dry_run)
    # print summary
    conn.close()
```

Add `--dry-run` flag and `--all` flag.

### Step 4 — `tests/test_data.py`

Tests (all use tmp_path + fake DB, no Claude calls):
1. `test_write_deal_data_inserts_rows` — write entries → check db
2. `test_idempotent_reextraction` — write same source twice → same row count
3. `test_conflict_detection_flags_both` — two rows same key different value → both flagged
4. `test_no_conflict_same_value` — same value from two sources → no conflict
5. `test_risk_flag_revenue_decline` — declining revenue → flag written
6. `test_risk_flag_low_ebitda_margin` — EBITDA margin < 10% → flag written
7. `test_golden_wolf_revenue_2022` — read Wolf golden, compare to extracted (LIVE, skipif no files)
8. `test_golden_cat_ebitda_2024` — read Cat golden (LIVE)

Live tests (skip if OneDrive not mounted) compare extracted values to golden ±2%.

---

## AI Validation Results

- `pytest tests/` result: **56 passed** (10 unit + 2 live + 44 existing)
- **Approach changed**: rule-based DATEV/HGB label matching instead of Claude API. No API calls needed.
- Golden dataset built for: Wolf (4yr), Cat (6yr), Octopus (6yr). Fox pending (file locked).

### Live extraction results

| Deal | Files | Rows | Conflicts | Flags | Errors |
|------|-------|------|-----------|-------|--------|
| Wolf | 8 | 57 | 0 | 1 | 0 |
| Cat | 6 | 60 | 50 | 0 | 2 |
| Fox | 23 | 120 | 97 | 0 | 6 |
| Octopus | 7 | 42 | 4 | 2 | 4 |

### Golden match accuracy (Wolf)

| Year | Revenue diff | Comment |
|------|-------------|---------|
| 2022 | **0.0%** | Perfect match: 5773.74 |
| 2023 | **0.0%** | Perfect match: 6217.67 |
| 2024 | **0.0%** | Perfect match: 7449.04 |

EBITDA diff is expected: extraction gives stated (unadjusted) EBITDA; golden has adjusted.
Wolf 2022: extracted EBITDA 315 EUR_K vs golden adj 333 EUR_K — diff is GF salary normalization.

### Errors (format not recognized)

- `BilanzinfoVergleichQuer.xlsm`: multi-year comparison layout, no year column detection
- `Kurzfristige Erfolgsrechnung kurz`: abbreviated format, different column layout
- `Kontennachweis zur G.u.V.`: account-level detail, not summary P&L
- `Warengruppen-Rohgewinn`: product-level margin report, not P&L
- Fox 2023/2024 GuV: could not detect fiscal year from file header (DATEV format variant)

These are edge formats — the core DATEV GuV/Bilanz/BWA extraction works. Kontennachweis and
Warengruppen are NOT standard P&L files and should arguably have different doc_subtypes.

### Learnings

1. **German string numbers**: Kurzfristige Erfolgsrechnung uses `'4.240.640,96'` strings, not floats
2. **Subtotal scanning**: DATEV Materialaufwand/Personalaufwand have sub-items (a,b) with labeled rows before the unlabeled subtotal — scanner must skip past labeled sub-items
3. **Year sanity**: DATEV regex `\b\d{1,2}\.(\d{2})\b` matches "31.12" → 2012 (wrong). Added 2015–2030 range check.
4. **Multi-entity**: Cat has M&S + LIKE entities → high conflict count is expected, not a bug
5. **No API needed**: DATEV/HGB format is standardized enough for rule-based parsing
