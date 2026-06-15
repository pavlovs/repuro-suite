# SPEC-DR-MODEL -- Model Builder Pipeline Specification

Engineering spec for the **model builder pipeline**. Defines how account-level financial data flows FROM `deal_financials` (SQLite) INTO the Excel financial model via `susa_to_model.py` and Excel COM. This is the bridge between persistent extracted data (DR-READER) and the live valuation workbook (SPEC-MODEL).

**Scope boundary:** This spec covers ONLY the DB-to-model population pipeline. It does NOT cover data extraction (that is DR-READER), model file structure or formula logic (that is SPEC-MODEL), or manual adjustments/valuation work (that is Roman). DR-MODEL is a deterministic copy operation: verified DB data goes into the correct model cells.

**Core principle:** The database is the input, not raw files. DR-MODEL never reads SUSA xlsx files directly. It queries `deal_financials`, constructs the `susa_data` dict, and feeds it to `susa_to_model.py`. If the DB has complete, verified, account-level data, model population is a mechanical operation.

**Architecture:**

```
deal_financials (SQLite, account-level, 3 years, completeness-checked)
    |
    v
[DR-MODEL: build-model command]
    |
    +-- [1] Completeness gate: DR-READER checks must PASS
    +-- [2] Query deal_financials for account-level P&L data (3 years)
    +-- [3] Format as susa_to_model.py input (dict: {konto: (saldo, is_soll)})
    +-- [4] Determine target columns by reading model R3 headers
    +-- [5] Generate PS1 via susa_to_model.py
    +-- [6] Execute PS1 -> GuV-Konten populated
    +-- [7] Populate Bilanz sheet (Phase 2 -- lower confidence)
    +-- [8] Post-write cross-checks (error flag, revenue match, EBITDA)
    +-- [9] Roman review gate
```

**Status:** Draft -- pending Roman confirmation.
**Owner:** Roman (model review + valuation), Claude (pipeline execution).
**Last updated:** 2026-05-20.

**Upstream:** SPEC-DR-READER (`deal_financials` table with account-level P&L and Bilanz data, completeness-checked).
**Downstream:** SPEC-MODEL (the populated Excel workbook), SPEC-OFFER (valuation outputs from Bewertung), SPEC-LOI (net debt, equity value).

---

## 1. Overview

### The Problem

Today, model population requires manually configuring `susa_to_model.py` with file paths and column numbers for each deal and each fiscal year. The SUSA data source is a raw xlsx or JSON file. This means:

- Each model update requires constructing a JSON config from scratch
- No automated pre-check that the source data is complete and verified
- Column detection is manual (read model headers, count columns, set `target_column`)
- No post-write verification beyond visual inspection
- Bilanz sheet is entirely manual (no automation path exists)

### What DR-MODEL Solves

1. **DB-driven population**: Query `deal_financials` instead of reading raw SUSA files. Data is already extracted, normalized, sign-corrected, and completeness-checked by DR-READER.
2. **3-year batch mode**: Populate all fiscal years in one CLI invocation. No per-year config files.
3. **Automated column detection**: Read model R3 headers to determine which column = which year. Never hardcode.
4. **Completeness gate**: Refuse to populate if DR-READER checks have not passed. `--force` override available.
5. **Post-write cross-checks**: Verify error flag, spot-check revenue and EBITDA against DB values.
6. **Bilanz population path** (Phase 2): Extend automation to balance sheet category totals and net debt detail.

### Integration Map

```
[DR-READER: read-docs -> deal_financials]
       |
       v
[DR-MODEL: build-model]
  (1) Query deal_financials
  (2) Construct susa_data dicts
  (3) Read model R3 headers (openpyxl read-only)
  (4) Configure susa_to_model.py UpdateConfig
  (5) generate_update() -> PS1 script
  (6) Execute PS1 -> GuV-Konten populated via Excel COM
  (7) Post-write cross-checks
       |
       v
[Excel Model: GuV-Konten populated, formulas recalculate]
       |
       +-- GuV (K EUR, formula-driven from GuV-Konten)
       +-- Bewertung (valuation, formula-driven from GuV + Bilanz)
       +-- Bilanz (Phase 2: DR-MODEL writes category totals)
       |
       v
[Roman: manual adjustments, salary normalization, valuation params]
       |
       v
[SPEC-OFFER / SPEC-LOI: downstream deliverables]
```

---

## 2. Pipeline Steps

### Step 1: Completeness Gate

Before any model write, verify that DR-READER extraction is trustworthy.

```python
# Pseudocode
def check_completeness(conn, domain, years):
    """Gate: refuse to populate if extraction checks failed."""
    for year in years:
        # Check Jahresergebnis crossfoot
        check = conn.execute("""
            SELECT adjustment_note FROM deal_financials
            WHERE domain = ? AND line_item = '_check_jahresergebnis'
              AND fiscal_year = ?
        """, (domain, year)).fetchone()
        
        if check is None:
            raise GateError(f"No completeness check for FY{year}. Run read-docs first.")
        if 'FAIL' in check['adjustment_note']:
            raise GateError(f"Jahresergebnis check FAILED for FY{year}. Fix extraction first.")
    
    # Check 3-year coverage
    for year in years:
        has_data = conn.execute("""
            SELECT COUNT(*) FROM deal_financials
            WHERE domain = ? AND statement = 'pnl'
              AND konto_nr IS NOT NULL AND fiscal_year = ?
        """, (domain, year)).fetchone()[0]
        
        if has_data == 0:
            raise GateError(f"No account-level P&L data for FY{year}.")
    
    return True  # All gates pass
```

**Override**: `--force` bypasses the gate. Roman must acknowledge the risk. Use case: partial population when only 2 of 3 years have data.

### Step 2: Query deal_financials

Extract account-level P&L data for the requested years.

```python
def query_pnl_accounts(conn, domain, fiscal_year):
    """Return {konto_str: (saldo_abs, is_soll)} for one fiscal year."""
    rows = conn.execute("""
        SELECT konto_nr, value_raw, adjustment_note
        FROM deal_financials
        WHERE domain = ?
          AND statement = 'pnl'
          AND konto_nr IS NOT NULL
          AND fiscal_year = ?
          AND period_type = 'annual'
          AND is_authoritative = 1
        ORDER BY konto_nr
    """, (domain, fiscal_year)).fetchall()
    
    susa_data = {}
    for row in rows:
        konto = row['konto_nr']
        value_raw = row['value_raw']  # Already sign-corrected by DR-READER
        
        # Reverse the sign convention to get (saldo_abs, is_soll)
        # DR-READER stores: model_value = -saldo if is_soll else +saldo
        # So: negative value_raw = Soll account, positive = Haben account
        is_soll = value_raw < 0
        saldo_abs = abs(value_raw)
        
        susa_data[konto] = (saldo_abs, is_soll)
    
    return susa_data
```

**Key design choice**: DR-READER stores `value_raw` as the signed model value (negative = Soll, positive = Haben). DR-MODEL reverses this to reconstruct the `(saldo_abs, is_soll)` tuple that `susa_to_model.py` expects. This preserves the validated sign convention without introducing a new code path.

**Filter**: `is_authoritative = 1` ensures only Roman-approved data flows to the model. Without approval, the query returns 0 rows and the pipeline halts with an explicit message.

### Step 3: Format as susa_to_model.py Input

Construct the `SourceConfig` objects that `susa_to_model.py` expects.

```python
def build_source_configs(susa_data_by_year, year_to_column):
    """Build SourceConfig list from DB query results + column mapping."""
    sources = []
    for year, susa_data in susa_data_by_year.items():
        col = year_to_column[year]
        sources.append(SourceConfig(
            name=f"fy{year}",
            target_column=col,
            susa_data=susa_data,  # dict passed directly, no file I/O
        ))
    return sources
```

The `susa_data` parameter on `SourceConfig` accepts a dict directly. `resolve_source()` in `susa_to_model.py` calls `normalize_susa_dict()` on it. No file round-trip needed.

### Step 4: Determine Target Columns

Read model R3 (header row) to map fiscal years to Excel column numbers. Never hardcode.

```python
def detect_year_columns(model_path, sheet_name):
    """Read R3 headers -> {year_int: column_number}."""
    import openpyxl
    wb = openpyxl.load_workbook(model_path, read_only=True, data_only=True)
    ws = wb[sheet_name]
    
    year_map = {}
    for col_idx, cell in enumerate(ws[3], start=1):  # Row 3
        val = cell.value
        if val is None:
            continue
        val_str = str(val).strip()
        
        # Match pure year: "2023", "2024", "2025A"
        # Strip trailing letters (A = actual, P = plan, E = estimate)
        year_clean = val_str.rstrip('APEQ ')
        try:
            year_int = int(year_clean)
            if 2015 <= year_int <= 2030:
                year_map[year_int] = col_idx
        except ValueError:
            continue
    
    wb.close()
    return year_map
```

**Known R3 patterns from golden models:**

| Model | R3 Headers | Year-Column Map |
|---|---|---|
| LION | `Konto, KONSOLIDIERT, 2021, 2022, 2023, 2024, 2025, ..., Kommentar` | {2021:4, 2022:5, 2023:6, 2024:7, 2025:8} |
| FOX | `Konto, KONSOLIDIERT, 2021, 2022, 2023, 2024, 2025, ..., Kommentar` | {2021:4, 2022:5, 2023:6, 2024:7, 2025:8} |
| WOLF | `Konto, KONSOLIDIERT, 2022, 2023, 2024, 2025A, ..., Kommentar` | {2022:4, 2023:5, 2024:6, 2025:7} |
| CAT | `Konto, KONSOLIDIERT, 2020, 2021, 2022, 2023, 2024, 2025, ..., Kommentar, Konto, M&S, 2020` | {2020:4, 2021:5, 2022:6, 2023:7, 2024:8, 2025:9} |

**Edge case**: WOLF starts at 2022, not 2021. CAT has entity columns after a separator. The detection function must stop scanning at non-year headers ("Kommentar", "Konto", "Q1-2025") to avoid false matches.

### Step 5: Generate PS1 via susa_to_model.py

Wire everything into `UpdateConfig` and call `generate_update()`.

```python
def build_and_generate(conn, domain, years, model_path, model_filename,
                       deal_folder, model_subfolder, sheet_name='GuV-Konten'):
    """Full pipeline: DB -> susa_to_model.py -> PS1."""
    
    # Step 1: Completeness gate
    check_completeness(conn, domain, years)
    
    # Step 2: Query DB for each year
    susa_data_by_year = {}
    for year in years:
        susa_data_by_year[year] = query_pnl_accounts(conn, domain, year)
    
    # Step 4: Detect columns
    year_to_column = detect_year_columns(model_path, sheet_name)
    
    # Verify requested years exist in model
    for year in years:
        if year not in year_to_column:
            raise ConfigError(
                f"FY{year} not found in model headers. "
                f"Available years: {sorted(year_to_column.keys())}"
            )
    
    # Step 3: Build SourceConfigs
    sources = build_source_configs(susa_data_by_year, year_to_column)
    
    # Step 5: Generate
    config = UpdateConfig(
        deal_folder=deal_folder,
        model_subfolder=model_subfolder,
        model_filename=model_filename,
        guv_sheet_name=sheet_name,
        sources=sources,
    )
    
    result = generate_update(config)
    return result
```

### Step 6: Execute PS1

The generated PS1 script handles:
1. Kill lingering Excel processes
2. Copy model from OneDrive to local temp (`C:\Users\X1\Documents\CLAUDE_COWORK\`)
3. Open via Excel COM (`$xl = New-Object -ComObject Excel.Application`)
4. Write cell values to GuV-Konten sheet
5. Save, close, release COM objects
6. Copy back to OneDrive
7. Clean up temp file

Execution is a PowerShell subprocess call. DR-MODEL does not modify the PS1 execution pattern -- `susa_to_model.py` owns that.

### Step 7: Bilanz Population (Phase 2)

See Section 6 below. This is new scope not covered by `susa_to_model.py`. Lower confidence.

### Step 8: Post-Write Cross-Checks

See Section 9 below. Read the model after COM write to verify data integrity.

### Step 9: Roman Review Gate

See Section 13 below. Model output is not used in downstream deliverables until Roman confirms.

---

## 3. Data Mapping: deal_financials to susa_to_model.py

### 3.1 Source Query

The fundamental query extracts account-level P&L rows from `deal_financials`:

```sql
SELECT konto_nr, value_raw
FROM deal_financials
WHERE domain = :domain
  AND statement = 'pnl'
  AND konto_nr IS NOT NULL
  AND fiscal_year = :year
  AND period_type = 'annual'
  AND is_authoritative = 1
ORDER BY CAST(konto_nr AS INTEGER)
```

**Columns used:**

| DB Column | Role in Pipeline |
|---|---|
| `domain` | Deal identifier (e.g., `golmed.de`, `com2med.de`) |
| `statement` | Filter: `'pnl'` for GuV-Konten, `'balance'` for Bilanz |
| `konto_nr` | Account number -- matches model column B |
| `fiscal_year` | Determines which model column to write to |
| `value_raw` | EUR amount, sign-corrected (negative=Soll, positive=Haben) |
| `period_type` | Filter: `'annual'` for fiscal year totals |
| `is_authoritative` | Gate: only approved data flows to model |

### 3.2 Sign Convention Roundtrip

The sign convention passes through three stages:

```
[1] SUSA source:      saldo = 125,000.00   S/H = "S"
[2] DR-READER stores: value_raw = -125,000.00   (model_value = -saldo if is_soll)
[3] DR-MODEL extracts: saldo_abs = 125,000.00  is_soll = True  (reverse of step 2)
[4] susa_to_model.py:  model_value(-125,000.00) = writes -125,000.00 to cell
```

Stage [3] is the reconstruction:
- `value_raw < 0` implies `is_soll = True`, `saldo_abs = abs(value_raw)`
- `value_raw >= 0` implies `is_soll = False`, `saldo_abs = value_raw`

This roundtrip is lossless. The same sign convention from DR-READER (`model_value = -saldo if is_soll else +saldo`) is preserved through to the model cell.

### 3.3 Account Filtering

`susa_to_model.py` already handles accounts that exist in SUSA but not in the model -- they are logged as "not-in-model" and skipped. DR-MODEL passes the full account set from `deal_financials`; filtering happens inside `generate_ps1()` via the `account_map`.

Accounts in `DEFAULT_SKIP_ACCOUNTS` (currently `{"2870"}` -- Vorabausschuettung) are also skipped.

### 3.4 What DR-MODEL Does NOT Transform

DR-MODEL is a pass-through. It does NOT:
- Aggregate accounts (GuV-Konten formulas do that)
- Convert EUR to K EUR (GuV formulas do that via `/1000`)
- Apply adjustments (Roman does that in GuV rows 30+)
- Compute EBITDA, EBIT, or any derived metric (model formulas do that)
- Modify model structure, formulas, formatting, or layout (SPEC-MODEL hard constraints)

---

## 4. Multi-Entity Handling

### 4.1 Single-Entity (LION, WOLF)

Standard path. One `susa_data` dict per fiscal year. All accounts write to the consolidated columns (D-H range).

```python
# LION example
year_to_column = {2021: 4, 2022: 5, 2023: 6, 2024: 7, 2025: 8}
# One susa_data dict per year, all from domain='golmed.de'
```

### 4.2 Multi-Entity with Entity Columns (FOX)

FOX has two entities within the same GuV-Konten sheet:
- Consolidated columns: D-H (year data)
- Entity 323 columns: O-T (Com2Med Med. Technologien GmbH & Co. KG)

**Challenge**: FOX has 0 individually mapped accounts in column B for the consolidated view. Account numbers appear in the entity sub-columns (col O = Konto for entity 323). The standard `read_model_account_map()` returns 0 matches.

**Approach for FOX:**

1. Query `deal_financials` per entity (using `source_file_id` linkage to identify entity)
2. For each entity, detect entity account columns in the model (scan R3 for entity headers)
3. Build a separate `account_map` per entity by reading the entity Konto column (e.g., col O)
4. Generate separate PS1 write blocks: one per entity, targeting entity-specific columns
5. Consolidated columns are formula-driven -- they sum entity columns automatically

```python
# FOX entity handling pseudocode
entity_configs = {
    'consolidated': {'konto_col': 2, 'year_cols': {2021:4, 2022:5, ...}},  # IF accounts exist
    'entity_323':   {'konto_col': 15, 'year_cols': {2021:17, 2022:18, ...}},  # cols O-T
}
```

**Status**: FOX entity handling requires extending `susa_to_model.py` to accept a custom `account_col` parameter for `read_model_account_map()`. This is a minor change (the function already reads from a fixed col B; parameterize it).

### 4.3 Multi-Entity with Separate Sheets (CAT)

CAT has entity raw data in separate sheets: M&S25, M&S24, LIKE25, LIKE24, etc. The GuV-Konten sheet has both individual accounts (col B, 91 mapped) and entity sub-columns further right.

**Approach for CAT:**

1. For consolidated GuV-Konten population: query `deal_financials` for the consolidated/combined entity data per year. Write to standard columns (D-I).
2. For entity sheets (M&S25, LIKE25, etc.): these are raw SUSA imports used as reference. DR-MODEL can populate them if entity-level data exists in `deal_financials`, but this is lower priority since the entity sheets feed into GuV-Konten via formulas.

**Practical recommendation**: Focus on consolidated column population first. Entity sheet population is a nice-to-have -- the model formulas handle consolidation from those sheets.

### 4.4 SKR03 vs SKR04

CAT uses SKR04 (revenue = 4xxx, COGS = 5xxx, personnel = 6xxx). All others use SKR03 (revenue = 8xxx, COGS = 3xxx, personnel = 4xxx).

DR-MODEL does not need to handle this explicitly. The account numbers in `deal_financials.konto_nr` match the account numbers in the model's column B. The mapping is deal-specific and already encoded in the model template. `susa_to_model.py` matches by account number, not by account range.

---

## 5. Bilanz Population (Phase 2)

**Confidence: LOW. This section is a design proposal, not a validated pipeline.**

The Bilanz sheet requires different handling than GuV-Konten because:
- Bilanz uses category totals (Anlagevermoegen, Umlaufvermoegen, Eigenkapital), not individual accounts
- The lower section (net debt detail) uses account-level positions
- Values are in FULL EUROS (not K EUR)
- Bilanz structure varies significantly across models (see SPEC-MODEL Section 7.5)
- No existing tool (`susa_to_model.py` only handles GuV-Konten)

### 5.1 Bilanz Data in deal_financials

DR-READER stores balance sheet data with `statement = 'balance'`:

```sql
SELECT line_item, konto_nr, value_raw, fiscal_year
FROM deal_financials
WHERE domain = :domain
  AND statement = 'balance'
  AND fiscal_year = :year
  AND is_authoritative = 1
```

**Expected line_items:**

| line_item | Bilanz Section | Model Row Pattern |
|---|---|---|
| `fixed_assets` | Aktiva: Anlagevermoegen | Category total row |
| `current_assets` | Aktiva: Umlaufvermoegen | Category total row |
| `cash` | Aktiva: Kassenbestand/Bankguthaben | Category subtotal |
| `receivables` | Aktiva: Forderungen aus LuL | Category subtotal |
| `equity` | Passiva: Eigenkapital | Category total row |
| `tax_provisions` | Passiva: Steuerrueckstellungen | Net debt component |
| `pension_provisions` | Passiva: Pensionsrueckstellungen | Net debt component |
| `other_provisions` | Passiva: Sonstige Rueckstellungen | Partially net debt |
| `bank_debt` | Passiva: Verbindlichkeiten gg. KI | Net debt component |
| `trade_payables` | Passiva: Verbindlichkeiten aus LuL | Working capital (not net debt) |
| `other_liabilities` | Passiva: Sonstige Verbindlichkeiten | Review needed |
| `shareholder_loan` | Passiva: GF-Darlehen | Deal structure, NOT net debt |

### 5.2 Bilanz Row Detection

Unlike GuV-Konten (where col B has account numbers), Bilanz uses text labels. Row detection requires label matching:

```python
def detect_bilanz_rows(model_path, sheet_name='Bilanz'):
    """Scan Bilanz sheet col B for category labels -> {label_key: row_number}."""
    import openpyxl
    wb = openpyxl.load_workbook(model_path, read_only=True, data_only=True)
    ws = wb[sheet_name]
    
    BILANZ_LABEL_MAP = {
        'Anlagevermoegen': 'fixed_assets',
        'Anlagevermögen': 'fixed_assets',
        'Umlaufvermoegen': 'current_assets',
        'Umlaufvermögen': 'current_assets',
        'Eigenkapital': 'equity',
        'Steuerrueckstellungen': 'tax_provisions',
        'Steuerrückstellungen': 'tax_provisions',
        'Kassenbestand': 'cash',
        # ... extend as models are analyzed
    }
    
    row_map = {}
    for row_idx, row in enumerate(ws.iter_rows(min_col=2, max_col=2, values_only=True), start=1):
        label = row[0]
        if label and str(label).strip() in BILANZ_LABEL_MAP:
            key = BILANZ_LABEL_MAP[str(label).strip()]
            row_map[key] = row_idx
    
    wb.close()
    return row_map
```

**Risk**: Label matching is fragile. Labels differ across models (abbreviations, Umlaute, spacing). This needs validation against all 4 golden models before implementation.

### 5.3 Bilanz Column Detection

Bilanz year columns follow a similar pattern to GuV-Konten R3 headers, but the header row may differ:
- Most models: row 3 contains year headers
- Some models: row 2 contains years

Detection approach: scan rows 2-4 for year-like values (2015-2030) in columns D-H.

### 5.4 Net Debt Detail Section

The lower Bilanz section contains account-level net debt positions. These are individual bank accounts, loans, and provisions with their balances.

**Structure varies heavily by model** (SPEC-MODEL Section 7.5):
- LION: Net debt starts at row 49
- WOLF: Net debt at row 46
- CAT: Row 46 or in separate ND_Positions sheet
- FOX: Rows 88+ (after duplicated Bilanz structure)

Standard net debt positions (Bankdarlehen, Kontokorrent, Gesellschafterdarlehen, Rückstellungen, Verbindlichkeiten aus L+L) are typical across all models and can be automated in a first pass. Deal-specific or unusual positions may need manual adjustment by Roman.

**Approach: Automate standard positions, flag non-standard for review.**

### 5.5 Bilanz Implementation Plan

1. **Phase 2a**: Category totals (Anlagevermoegen, Umlaufvermoegen, Eigenkapital, etc.)
   - Detect rows via label matching
   - Write values in FULL EUROS via Excel COM
   - Verify Aktiva = Passiva check formulas pass

2. **Phase 2b**: Net debt standard positions (first-pass automation)
   - Standard positions written automatically: Bankdarlehen, Kontokorrent/KK, Gesellschafterdarlehen, Rückstellungen (Pension, sonstige), Verbindlichkeiten aus Lieferungen und Leistungen, Kasse/Bank (asset side)
   - Label matching against known variants per position type
   - Row positions detected per model (LION row 49+, WOLF row 46+, CAT row 46+, FOX row 88+)
   - Non-matched positions flagged in output: "3 net debt rows not auto-filled — review needed"
   - Roman adjusts: adds missing positions, corrects values, adds deal-specific items (earn-out liabilities, Mezzanine, etc.)
   - After Roman's adjustments: `verify-model` checks net debt total matches Bilanz Fremdkapital

### 5.6 Unit Scale

**Bilanz values are in FULL EUROS, not K EUR.** This is a critical difference from the DB storage:

```python
# deal_financials stores value_raw (EUR) and value_k (K EUR)
# Bilanz sheet expects FULL EUROS
# Use value_raw directly -- DO NOT divide by 1000
bilanz_cell_value = row['value_raw']  # EUR, not K EUR
```

The K EUR conversion happens in Bewertung row 13 formula, which references the Bilanz net debt total and divides by 1000. Writing K EUR to Bilanz cells would double the division.

---

## 6. CLI Interface

### 6.1 Command: `build-model`

```bash
python DEALROOM.py build-model --deal Lion
python DEALROOM.py build-model --deal Lion --year 2025
python DEALROOM.py build-model --deal Fox --entity mt --year 2024
python DEALROOM.py build-model --deal Lion --dry-run
python DEALROOM.py build-model --deal Lion --force
python DEALROOM.py build-model --deal Lion --bilanz          # Phase 2
python DEALROOM.py build-model --deal Lion --execute          # Generate + run PS1
```

**Arguments:**

| Argument | Required | Default | Description |
|---|---|---|---|
| `--deal` | Yes | -- | Deal code name (Lion, Fox, Cat, Wolf, etc.) |
| `--year` | No | all available | Populate specific fiscal year(s) only |
| `--entity` | No | consolidated | Entity code for multi-entity deals (FOX: `mt`, `mtec`) |
| `--dry-run` | No | false | Build config and report what would be written, without generating PS1 |
| `--force` | No | false | Bypass completeness gate (Roman override) |
| `--bilanz` | No | false | Include Bilanz population (Phase 2) |
| `--execute` | No | false | Generate PS1 AND execute it. Default = generate only. |
| `--sheet` | No | `GuV-Konten` | Target sheet name (override for non-standard models) |

### 6.2 Output Format

```
DEALROOM build-model: Lion (Golmed GmbH)
==========================================

Completeness gate:
  FY2023: Jahresergebnis PASS (delta 0.01%)  |  178 accounts
  FY2024: Jahresergebnis PASS (delta 0.02%)  |  175 accounts
  FY2025: Jahresergebnis PASS (delta 0.00%)  |  178 accounts
  3-year coverage: OK

Model: 260514_Golmed_v14.xlsx
Sheet: GuV-Konten
Column detection (R3 headers):
  2021 -> col D (4)
  2022 -> col E (5)
  2023 -> col F (6)   <-- will populate
  2024 -> col G (7)   <-- will populate
  2025 -> col H (8)   <-- will populate

Account map: 178 accounts in model col B
  FY2023: 175 matched, 3 not-in-model (2870, 3111, 4995)
  FY2024: 172 matched, 3 not-in-model
  FY2025: 178 matched, 0 not-in-model

Generated: C:\Users\X1\Documents\CLAUDE_COWORK\update_model.ps1
  Total cell writes: 525
  Skipped: 9 (3 per year, see log)

Spot-check values:
  [fy2023] col 6:
    8400 -> row 7:  5,432,100.00  (raw: 5,432,100.00 H)
    3400 -> row 28: -3,210,500.00 (raw: 3,210,500.00 S)
    4120 -> row 65: -  485,000.00 (raw: 485,000.00 S)

[!] Review: Execute PS1 with `--execute` or run manually in PowerShell.
[!] After execution: verify error flag (R2) and spot-check GuV totals.
```

### 6.3 Command: `verify-model`

Post-write verification (runs after PS1 execution):

```bash
python DEALROOM.py verify-model --deal Lion
```

Opens model with openpyxl (read-only, data_only=True) and checks:
1. Error flag (R2): "No Errors" expected
2. Revenue spot-check: model GuV Gesamtleistung vs `deal_financials` sum
3. EBITDA spot-check: model GuV EBITDA vs `deal_financials` derived EBITDA
4. Reports deltas

See Section 9 for details.

---

## 7. New Deal Setup Workflow

Complete workflow for creating a model for a new deal, from template to populated workbook.

### 7.1 Prerequisites

- Deal registered in DEALROOM with `domain` identifier
- Financial documents extracted via DR-READER (`read-docs` complete)
- Completeness checks passing for at least 2 of 3 fiscal years
- Roman confirms deal is ready for model work

### 7.2 Steps

```
[1] Select template:
    Single-entity -> LION v14: 260514_Golmed_v14.xlsx
    Multi-entity  -> CAT v7:  260505_MundS_v7.xlsx

[2] Copy template to deal folder:
    Source: CLAUDE_REPURO/dealroom/config/golden/model/{template}
    Target: CLAUDE_REPURO/3_Deals/3_Targets/{deal_folder}/2_Model/YYMMDD_{DealName}_v1.xlsx

[3] Clear old deal data from GuV-Konten:
    Roman manually clears data columns (D-H) while preserving:
    - Account numbers in col B
    - Section headers and labels
    - All formulas (subtotals, ratios, EBIT reconciliation)
    - Column structure and formatting

[4] Run DR-MODEL to populate GuV-Konten:
    python DEALROOM.py build-model --deal NewDeal --execute

[5] Verify:
    python DEALROOM.py verify-model --deal NewDeal

[6] Roman manual work:
    - Review populated data for plausibility
    - Add deal-specific adjustments in GuV rows 30+
    - Salary normalization (old GF salary, new GF salary, Nebenkosten 17%)
    - Enter Bilanz category totals
    - Enter net debt detail positions
    - Set valuation parameters in Bewertung (EBITDA targets, multiples)
    - Populate Vergleich sheet with offer history

[7] REVIEW GATE:
    Roman confirms model is ready for valuation work.
    BLOCK: do not use Bewertung outputs in SPEC-OFFER or SPEC-LOI until approved.
```

### 7.3 Template Selection Logic

| Criterion | Template | Rationale |
|---|---|---|
| Single legal entity, SKR03 | LION v14 | Most iterated, cleanest structure, 178 mapped accounts |
| Multiple entities, separate sheets | CAT v7 | Entity sheet pattern, handles SKR04 |
| Multiple entities, column pattern | FOX v7 | Entity columns within GuV-Konten |
| Single entity, SKR04 | CAT v7 (stripped) | Start from CAT, remove second entity sheets |

**Template naming convention**: `YYMMDD_{DealName}_v1.xlsx`
- `YYMMDD` = date of model creation
- `{DealName}` = company name (not code name)
- `v1` = first version, incremented on each major revision

---

## 8. Incremental Update Workflow

Workflow for adding new fiscal year data to an existing model.

### 8.1 New Annual Data

```
Trigger: New SUSA arrives for FY2026 (from Steuerberater)

[1] DR-READER extracts new SUSA:
    python DEALROOM.py read-docs --deal Lion --type susa

[2] Verify extraction:
    python DEALROOM.py review-extraction --deal Lion --year 2026

[3] Roman approves:
    python DEALROOM.py review-extraction --deal Lion --year 2026 --approve

[4] DR-MODEL populates single column:
    python DEALROOM.py build-model --deal Lion --year 2026 --execute
```

### 8.2 Column Addition

If the new fiscal year does not yet exist in the model headers (no column for 2026):

```
[1] Detect: build-model reports "FY2026 not found in model headers"
[2] Roman manually:
    - Insert new column in model (after last year column)
    - Add year header in R3
    - Extend formula ranges in GuV, Bewertung, Bilanz (if any reference ranges)
[3] Re-run: build-model --deal Lion --year 2026 --execute
    (Column detection now finds the new year)
```

**DR-MODEL does NOT insert columns.** Column insertion affects formulas across every sheet and is Roman-manual. DR-MODEL only writes to existing columns.

### 8.3 Data Correction

If DR-READER re-extracts corrected data (updated SUSA from Steuerberater):

```
[1] Re-extract: read-docs --deal Lion --type susa --force
[2] Re-approve: review-extraction --deal Lion --year 2025 --approve
[3] Re-populate: build-model --deal Lion --year 2025 --execute
    (Overwrites previous values in the same column)
[4] Verify: verify-model --deal Lion
```

The model's Excel COM write is idempotent -- writing the same cell twice replaces the value.

---

## 9. Cross-Checks and Verification

### 9.1 Post-Write Checks (verify-model)

After PS1 execution, read the model (openpyxl, read-only, data_only=True) and verify:

| Check | Source | Expected | Tolerance | Severity |
|---|---|---|---|---|
| Error flag (R2) | GuV-Konten cell R2 (or B2) | "No Errors" | Exact match | BLOCK |
| Revenue match | Model GuV Gesamtleistung row vs `deal_financials` sum(8xxx + 3960) | Equal within rounding | 2% | WARN |
| EBITDA match | Model GuV EBITDA row vs `deal_financials` derived EBITDA | Equal within rounding | 5% | WARN |
| Account count | Number of non-zero cells in populated column | >= 80% of DB account count | -- | WARN |

**Note on data_only=True**: openpyxl `data_only=True` returns the LAST CACHED formula result, not the live recalculated value. After a COM write, the cached values reflect the new data only if Excel recalculated before saving. The PS1 script calls `$wb.Save()` after writing, which triggers Excel's recalculation engine. So data_only=True should return updated values for the cells written, and recalculated values for formula cells.

**Edge case**: If the model shows "ERROR FOUND - CHECK" after population, this may be expected during partial population (e.g., only 2 of 3 years filled). The error flag is a formula checking multiple years. Flag for review but do not block.

### 9.2 Revenue Spot-Check Detail

```python
def check_revenue(conn, model_path, domain, year, year_column, sheet='GuV'):
    """Compare model GuV revenue vs DB revenue."""
    import openpyxl
    wb = openpyxl.load_workbook(model_path, read_only=True, data_only=True)
    
    # Read Gesamtleistung from GuV (typically row 7, but detect by label)
    ws_guv = wb[sheet]
    model_revenue_k = None
    for row in ws_guv.iter_rows(min_row=3, max_row=30, min_col=2, max_col=year_column):
        label_cell = row[0]  # col B
        if label_cell.value and 'Gesamtleistung' in str(label_cell.value):
            model_revenue_k = row[year_column - 2].value  # col offset
            break
    
    # Query DB
    db_revenue = conn.execute("""
        SELECT SUM(value_raw) FROM deal_financials
        WHERE domain = ? AND statement = 'pnl'
          AND (konto_nr LIKE '8%' OR konto_nr = '3960')
          AND fiscal_year = ? AND is_authoritative = 1
    """, (domain, year)).fetchone()[0]
    
    db_revenue_k = db_revenue / 1000 if db_revenue else 0
    
    if model_revenue_k and db_revenue_k:
        delta_pct = abs(model_revenue_k - db_revenue_k) / abs(db_revenue_k) * 100
        return {
            'model_k': model_revenue_k,
            'db_k': db_revenue_k,
            'delta_pct': delta_pct,
            'pass': delta_pct < 2.0
        }
    
    wb.close()
    return {'pass': False, 'error': 'Could not read values'}
```

### 9.3 Cross-Check Failure Handling

| Failure | Action |
|---|---|
| Error flag shows "ERROR FOUND - CHECK" | If all years populated: investigate. If partial: expected, proceed. |
| Revenue delta > 2% | Do NOT proceed to downstream deliverables. Investigate: missing accounts? Wrong column? Sign error? |
| EBITDA delta > 5% | Likely due to adjustment rows or missing accounts in one of the cost categories. Review skipped accounts. |
| Account count < 80% of DB | Model template may need new account rows. Roman adds manually, then re-run. |

---

## 10. Anti-Patterns

These anti-patterns MUST be included verbatim in any agent prompt that executes model population. They are sourced from SPEC-MODEL plus DR-MODEL-specific failure modes.

### EXCEL-FROM-SCRATCH
**Never generate a financial model from scratch.** The model contains hundreds of formulas, cross-sheet references, conditional formatting, named ranges, and print areas that cannot be reproduced programmatically. Always start from an existing golden template or the deal's current model version.

### OPENPYXL-CORRUPTION
**openpyxl destroys formatting on write.** Even `Workbook.save()` after only reading + modifying data cells will strip conditional formatting, corrupt chart objects, break named ranges, and scramble merged cells. Use openpyxl ONLY for reading (`read_only=True, data_only=True`). All writes go through Excel COM via PowerShell.
Source: 2026-05-14 GOLMED v11 session -- openpyxl write corrupted the model.

### FORMULA-OVERWRITE
**Never overwrite a formula cell with a hardcoded value.** This silently breaks the dependency chain. `susa_to_model.py` only writes to cells where column B has a 2000-9999 account number -- these are always data cells, never formula cells. Do not write to subtotal rows (Rohertrag, Betriebsergebnis, EBITDA, etc.).

### WRONG-UNIT-SCALE
**GuV-Konten stores EUR, GuV stores K EUR, Bilanz net debt section stores EUR.** Mixing scales is the most common manual error. `deal_financials.value_raw` is EUR. Write `value_raw` directly to GuV-Konten cells (EUR). Never divide by 1000 before writing to GuV-Konten. Never divide Bilanz values by 1000 either. The K EUR conversion happens in GuV formulas (`/1000`).

### INVENTED-FORMAT-INSTEAD-OF-COPY
**Never invent a model format.** The model layout has been refined through 14+ iterations across 4 deals. For new deals, copy the closest golden template and populate data only. Do not create new sheets, restructure rows, or redesign the layout.

### DB-BYPASS
**Never read SUSA xlsx files directly in DR-MODEL.** The pipeline is: DR-READER extracts to `deal_financials`, DR-MODEL reads from `deal_financials`. Bypassing the DB skips completeness checks, sign normalization, conflict detection, and the approval gate. If the DB data looks wrong, fix it in DR-READER, not by reading raw files.

### HARDCODED-COLUMNS
**Never hardcode column numbers across models.** WOLF starts at col D=2022; LION starts at col D=2021; CAT extends to col I=2025. Always read R3 headers to determine `year -> column` mapping. The `detect_year_columns()` function handles this.

### UNAPPROVED-DATA-TO-MODEL
**Never populate a model from unapproved data.** The `is_authoritative = 1` filter exists for a reason. Roman reviews extraction results before they flow to the model. Bypassing this with `WHERE is_authoritative IN (0, 1)` defeats the review gate. Use `--force` only with Roman's explicit acknowledgment.

### ONEDRIVE-COM-CONFLICT
**Never run Excel COM on OneDrive-synced files directly.** OneDrive file locking causes COM RPC errors and potential data corruption. Always: copy to local temp -> COM write -> copy back. `susa_to_model.py` implements this pattern in the generated PS1 script.

---

## 11. Dependencies and Pre-Implementation Checklist

### 11.1 Dependencies

| Dependency | Status | Path | Role |
|---|---|---|---|
| `deal_financials` table | EXISTS | SQLite via `db.py` | Source of truth for account-level data |
| `susa_to_model.py` | EXISTS | `dealroom/tools/susa_to_model.py` | PS1 generator for GuV-Konten writes |
| DR-READER pipeline | SPEC DONE | SPEC-DR-READER | Extraction + completeness checks |
| Model golden files | EXISTS | `config/golden/model/` | 4 reference templates |
| Deal models | EXISTS | `3_Deals/3_Targets/{deal}/2_Model/` | Live deal workbooks |
| openpyxl | EXISTS | Python package | Read-only model analysis |
| Excel COM | EXISTS | Windows Excel install | PS1 execution |
| PowerShell | EXISTS | Windows PowerShell 5.1+ | Script runtime |

### 11.2 Code Changes Required

| Component | Change | Scope |
|---|---|---|
| `DEALROOM.py` | Add `build-model` and `verify-model` CLI commands | New command handlers |
| `src/model.py` (new or extend existing) | Pipeline orchestration: gate -> query -> config -> generate | Core logic |
| `susa_to_model.py` | No changes for Phase 1. Phase 2 (Bilanz): add Bilanz sheet support | Minimal extension |
| `src/data.py` | Add helper to reconstruct susa_data dict from deal_financials | Small utility |
| `dealroom/config/` | Deal-to-domain mapping, model paths per deal | Config registry |

### 11.3 Pre-Implementation Checklist

- [ ] Verify `deal_financials` has account-level data (konto_nr IS NOT NULL) for at least one deal (LION preferred)
- [ ] Verify `is_authoritative` flag is set for approved data (run review-extraction --approve)
- [ ] Test `detect_year_columns()` against all 4 golden models -- confirm year-column mapping matches SPEC-MODEL Section 7.3
- [ ] Test sign convention roundtrip: DB value_raw -> (saldo_abs, is_soll) -> model_value -> verify matches original
- [ ] Verify `susa_to_model.py` accepts `susa_data` dict parameter (already supported via `SourceConfig.susa_data`)
- [ ] Confirm PS1 execution works from Python subprocess on current system
- [ ] Test openpyxl `data_only=True` reading of model after COM write -- verify formula results are cached
- [ ] Document deal-to-domain mapping for all active deals
- [ ] Verify completeness check rows (`_check_jahresergebnis`) exist in deal_financials for test deals

### 11.4 Implementation Priority

**Phase 1 -- GuV-Konten Population (HIGH confidence)**:
- `build-model` command: gate -> query -> susa_to_model.py -> PS1
- `verify-model` command: read model, check error flag + spot-checks
- Single-entity support (LION, WOLF)
- 3-year batch mode
- Estimated scope: ~300 lines of orchestration code

**Phase 2 -- Bilanz Population (MEDIUM confidence)**:
- Category totals via label matching + Excel COM
- Net debt standard positions: automated first pass (Bankdarlehen, KK, Gesellschafterdarlehen, Rückstellungen, VLL, Kasse/Bank)
- Non-standard positions flagged for Roman adjustment
- Estimated scope: ~250 lines + standard position registry

**Phase 3 -- Multi-Entity (MEDIUM confidence)**:
- FOX entity column handling (extend account_map to non-standard columns)
- CAT entity sheet population
- Consolidated + entity-level population in one invocation
- Estimated scope: ~150 lines + model-specific config

---

## 12. Review Gate

**Hard rule**: Model output (Bewertung figures: EV, equity value, payment structure) is not used in SPEC-OFFER, SPEC-LOI, or any external document until Roman confirms the model.

### 12.1 Review Flow

```
[build-model completes]
       |
       v
[PS1 generated (or executed with --execute)]
       |
       v
[verify-model reports: error flag, spot-checks, account coverage]
       |
       v
[Roman opens model in Excel]
[Reviews: GuV-Konten data, GuV summary, Bewertung outputs]
[Checks: plausibility of revenue, EBITDA, key accounts]
       |
       v
[Roman confirms: "model is good" or flags issues]
       |
       v
[If confirmed: model is ready for adjustments + valuation work]
[If issues: fix extraction (DR-READER) or re-run (DR-MODEL)]
```

### 12.2 What Roman Reviews

| Item | Where | What to Check |
|---|---|---|
| Error flag | GuV-Konten R2 / Bewertung R2 | "No Errors" |
| Revenue trend | GuV row 4-7 (Gesamtleistung) | Plausible YoY trend, matches known deal profile |
| EBITDA level | GuV EBITDA row | Within expected range for deal |
| Key accounts | GuV-Konten: 8400 (Umsatz), 4120 (Gehaelter) | Match SUSA / mental model |
| Skipped accounts | build-model output log | No material accounts skipped |
| Bilanz (if populated) | Bilanz sheet | Aktiva = Passiva, net debt plausible |

### 12.3 Blocking Downstream

Until Roman confirms the model:
- SPEC-OFFER must not reference Bewertung values
- SPEC-LOI must not reference net debt or equity value
- Onepager financial snapshot must use `deal_financials` directly (DB values), not model outputs
- Scorecard financial metrics use `deal_financials`, not model

After confirmation:
- Model becomes the authoritative view for valuation-dependent deliverables
- Adjustments in the model (salary normalization, one-offs) feed into offer pricing

---

## 13. Cross-Reference to Other Specs

| Spec | Relationship | Interface |
|---|---|---|
| **SPEC-DR-READER** | Upstream. Provides `deal_financials` with account-level data, completeness checks, approval status. DR-MODEL's `check_completeness()` reads DR-READER check rows (`_check_jahresergebnis`). | `deal_financials` table (read) |
| **SPEC-MODEL** | Defines the target. Sheet architecture, formula chains, hard constraints, anti-patterns. DR-MODEL writes to GuV-Konten data cells only. SPEC-MODEL Section 7.3 (column positions) and Section 4 (formula chain) are the authoritative references. | Excel model file (write via COM) |
| **susa_to_model.py** | The execution tool. DR-MODEL constructs `UpdateConfig` + `SourceConfig` objects and calls `generate_update()`. The tool is not modified -- its `susa_data` dict parameter is the interface. | `generate_update()` function |
| **SPEC-OFFER** | Downstream consumer. Uses Bewertung EV, equity value, payment structure -- all of which depend on correct model population. Blocked until Roman review gate passes. | Bewertung sheet values |
| **SPEC-LOI** | Downstream consumer. References net debt (Bewertung row 13) and equity value for LOI drafting. | Bewertung + Bilanz values |
| **SPEC-RFI** | Sibling. DR-READER risk flags may trigger RFI questions. Model population may surface additional anomalies (error flag, EBITDA mismatch) that feed back into RFI. | `deal_financials` risk flags |
| **SPEC-ONEPAGER** | Downstream consumer. Financial snapshot uses `deal_financials` directly (not model) for the HTML path. Model is the Excel path. Both should show the same numbers. | `deal_financials` (DB) |
| **DEAL_DELIVERABLES_SPEC** | Process reference. Stage 2 sub-step "Build/update financial model" is what DR-MODEL implements. | Workflow trigger |

---

## Appendix A: Deal Registry

Active deals and their model characteristics. Used by `build-model` for deal-to-config resolution.

| Code | Domain | Model Type | SKR | Template Basis | Golden Model |
|---|---|---|---|---|---|
| LION | golmed.de | Single-entity | SKR03 | LION v14 (self) | `260514_Golmed_v14.xlsx` |
| FOX | com2med.de | Multi-entity (col) | SKR03 | FOX v7 (self) | `260518_Com2Med_v7.xlsx` |
| CAT | ms-medical.de | Multi-entity (sheet) | SKR04 | CAT v7 (self) | `260505_MundS_v7.xlsx` |
| WOLF | kvg.de | Single-entity | SKR03 | WOLF v4 (self) | `260319_KVG_Model_v4.xlsx` |

**New deal resolution**: Look up domain in deal registry -> determine model type + SKR -> select template -> copy + rename -> run `build-model`.

## Appendix B: susa_to_model.py Interface Reference

Key functions and data structures DR-MODEL interacts with:

| Function / Class | Signature | DR-MODEL Usage |
|---|---|---|
| `SourceConfig` | `dataclass(name, target_column, susa_data=None, ...)` | Constructed per fiscal year with `susa_data` dict from DB |
| `UpdateConfig` | `dataclass(deal_folder, model_subfolder, model_filename, guv_sheet_name, sources, ...)` | Constructed once per `build-model` invocation |
| `generate_update(config)` | `UpdateConfig -> UpdateResult` | Main entry point. Returns PS1 path, write count, skipped accounts, warnings. |
| `model_value(saldo, is_soll)` | `(float, bool) -> float` | Sign convention: `-saldo if is_soll else saldo`. Used in roundtrip verification. |
| `read_model_account_map(path, sheet)` | `(str, str) -> dict[str, int]` | Reads col B account numbers. DR-MODEL uses this for account coverage reporting. |
| `validate_signs(susa_data, name)` | `(dict, str) -> list[str]` | Sign validation warnings. DR-MODEL includes these in output. |

**Contract**: DR-MODEL constructs `UpdateConfig` with `SourceConfig.susa_data` populated from DB queries. `susa_to_model.py` handles everything else: account matching, PS1 generation, OneDrive copy, COM script structure.
