# SPEC-DR-READER -- Financial Document Reader Specification

Engineering spec for the **financial data** intake pipeline. Defines how P&L and Bilanz documents (BWA, SUSA, Jahresabschluss, standalone GuV/Bilanz) are read, parsed, normalized, and stored in `deal_financials`. This is the model builder's upstream dependency -- every value in the Excel financial model originates from data this pipeline extracts.

**Scope boundary:** This spec covers ONLY financial document extraction → `deal_financials`. Commercial/operational data (customers, suppliers, employees, products) is a separate spec (DR-COMMERCIAL). Qualitative data (RFI responses, emails, Granola transcripts) is DR-GATHER. Same read→normalize→store principle, different document types, different target tables.

**Core principle:** Extract once, store persistently, audit always. Every extracted value links back to its source file. Re-extraction is idempotent. Conflicts between sources are detected automatically. Roman reviews before data flows downstream.

**Architecture:** `deal_financials` is the **source of truth** for all GuV and Bilanz data. The Excel financial model (SPEC-MODEL) and future HTML onepager are both **views** of this data -- they read from the DB, they don't define it. This decoupling means: (a) model population is a deterministic DB-to-Excel copy via `susa_to_model.py`, (b) HTML-first onepager becomes possible without Excel dependency, (c) re-extraction never requires re-building downstream artifacts.

**Coverage requirement:** DR-READER must extract and store the **last 3 fiscal years** of account-level data (GuV + Bilanz) for every deal. This is the minimum needed for: financial model population (GuV-Konten + Bilanz-Konten require 3-year history), trend analysis (YoY growth rates, margin trajectories), and valuation (LTM + 2 prior years for multiple basis).

**Status:** Draft -- pending Roman confirmation.
**Owner:** Roman (source document quality + review gate), Claude (extraction logic + storage).
**Last updated:** 2026-05-20.

**Upstream:** `ingest.py` scans deal folders and registers files in `deal_documents` with `doc_type='financials_raw'` and subtypes (`guv`, `bilanz`, `bwa`, `susa`, `ja`). DR-READER picks up from there.

**Downstream:** `deal_financials` feeds into SPEC-MODEL (model population via `susa_to_model.py` → GuV-Konten + Bilanz-Konten), SPEC-RFI (anomaly-driven questions), SPEC-OFFER (valuation basis via net debt), and scorecard computation.

**Sibling specs:**
- **DR-COMMERCIAL** — customer lists, supplier lists, employee data, product splits → `deal_customers`, `deal_suppliers`, `deal_employees`, `deal_commercial`. Same read→normalize→store pattern, different document types. Feeds Onepager, Offer, Scorecard.
- **DR-GATHER** — RFI responses, emails, Granola transcripts, conversation notes → `deal_contacts`, `deal_meetings`, `deal_notes`. Qualitative/unstructured data layer.

---

## 1. Overview

### The Problem

Every deal session today re-reads the same BWA/SUSA/Bilanz files from scratch. Extracted data lives in conversation context and is lost on compaction. The `deal_financials` table exists in the DB schema but is mostly empty because there is no systematic extraction pipeline. This means:

- Duplicate work across sessions (LION SUSA re-read 3 times across sessions)
- No cross-source conflict detection until a human spots a discrepancy
- Model population requires manual transcription (113 SUSA accounts hardcoded by hand in LION session)

### What DR-READER Solves

1. **Systematic extraction**: Every registered financial document gets parsed on `read-docs` invocation
2. **Persistent storage**: Extracted data survives session boundaries in SQLite
3. **Audit trail**: Every row traces back to `source_file_id` in `deal_documents`
4. **Conflict detection**: Same metric from different sources flagged automatically when variance > 1%
5. **Review gate**: Roman confirms extraction before downstream consumption

### Integration Map

```
[OneDrive deal folder]
       |
       v
[ingest.py: scan_deal() -> deal_documents]
       |
       v
[DR-READER: read-docs -> parse + normalize + completeness check]
       |
       v
[deal_financials]  <-- SOURCE OF TRUTH for all GuV + Bilanz data
       |
       |-- VIEW: Excel model (SPEC-MODEL via susa_to_model.py -> GuV-Konten + Bilanz-Konten)
       |-- VIEW: HTML onepager (mid-term, reads DB directly, no Excel dependency)
       |-- VIEW: Offer/LOI pricing (SPEC-OFFER, SPEC-LOI -> net debt, valuation basis)
       |-- QUERY: RFI anomaly questions (SPEC-RFI -> YoY changes, conflicts)
       '-- QUERY: Scorecard (financial metrics only; commercial metrics from DR-COMMERCIAL)
```

**Key implication**: The model builder (SPEC-MODEL) does not extract data -- it reads `deal_financials` and writes the last 3 years into GuV-Konten and Bilanz-Konten sheets. If the DB has complete, verified account-level data, model population is deterministic. Same data feeds the HTML onepager when that path is built.

---

## 2. Document Type Taxonomy

### 2.1 Financial Documents (P&L / Balance Sheet Sources)

| Doc Type | Subtype | Format | Granularity | Typical Source | Target Table |
|---|---|---|---|---|---|
| BWA | `bwa` | PDF, xlsx | ~20 summary lines (PDF) or account-level (xlsx) | Steuerberater monthly | `deal_financials` |
| SUSA | `susa` | xlsx, PDF | Account-level (4-digit DATEV) | Steuerberater cumulative | `deal_financials` |
| Jahresabschluss | `ja` | PDF | Bilanz + GuV for fiscal year | Steuerberater annual | `deal_financials` |
| GuV (standalone) | `guv` | xlsx | Account-level or summary | Steuerberater / target | `deal_financials` |
| Bilanz (standalone) | `bilanz` | xlsx | Line-item level | Steuerberater / target | `deal_financials` |

### 2.2 Format Matrix

| Format | Reader | Reliability | Notes |
|---|---|---|---|
| xlsx (financial) | openpyxl `load_workbook(data_only=True, read_only=True)` | High | Proven in `data.py` across LION/AQUA/CAT/FOX |
| xlsx (SUSA) | openpyxl (col A=account, F=saldo, G=S/H) | High | Proven in `susa_to_model.py` |
| PDF (BWA) | pdfplumber table extraction | Medium | ~20 summary lines, tabular layout |
| PDF (SUSA) | pdfplumber table extraction | Medium-Low | ~5 pages, 100+ rows, column alignment varies |
| PDF (Jahresabschluss) | Claude Read tool | Medium | Complex multi-section layout, mixed text + tables |

### 2.4 BWA: What You Get vs. What You Need

**BWA PDF** provides ~20 summary lines:

| Line | line_item key | Notes |
|---|---|---|
| Umsatzerloese | `revenue` | Net revenue |
| Bestandsveraenderung | `inventory_change` | Can be positive or negative |
| Gesamtleistung | `gesamtleistung` | = Revenue + Bestandsveraenderung + aktivierte Eigenleistungen |
| Materialaufwand | `cogs` | Wareneinsatz + Fremdleistungen |
| Rohertrag | `gross_profit` | = Gesamtleistung - Materialaufwand |
| Personalaufwand | `personnel` | Including soziale Abgaben |
| Sonstige betriebliche Aufwendungen | `other_opex` | Rent, insurance, travel, etc. |
| Betriebsergebnis / EBIT | `ebit` | After all operating costs |
| Abschreibungen (AfA) | `da` | Within other_opex or separate |
| Zinsen | `interest_expense` | |
| Vorlaeuiges Ergebnis | `ebt` | Before tax |

**BWA PDF is NOT a substitute for SUSA account-level data.** BWA gives you the headline; SUSA gives you the 100+ account breakdown needed for model population and normalization analysis.

**BWA xlsx** can contain account-level detail (effectively a SUSA formatted as BWA). Detect by checking if rows contain 4-digit DATEV account codes.

### 2.5 SUSA: Sign Convention (Critical)

DATEV SKR03 sign convention:

| Account Range | Normal Side | In Model |
|---|---|---|
| 8xxx (Revenue) | Haben (H) | Positive |
| 3xxx (COGS / Material) | Soll (S) | Negative |
| 4xxx (Personnel / OpEx) | Soll (S) | Negative |
| 6xxx (other costs, SKR04) | Soll (S) | Negative |
| 2xxx (Neutral income/expense) | Varies | Per S/H flag |
| 3960 (Bestandsveraenderung) | **Depends on S/H** | Not hardcodeable |

**Rule**: `model_value = -saldo if is_soll else +saldo`. This is the universal sign convention from `susa_to_model.py`. Do not hardcode sign by account range -- always use the S/H flag from the source document.

**3960 (Bestandsveraenderung)**: This account's sign depends on whether inventory increased (Soll = negative impact on P&L) or decreased (Haben = positive impact). It is the single most common sign error in manual extraction. Always use the S/H flag.

---

## 3. Extraction Pipeline

### 3.0 Source Flexibility — Convergence Principle

Every deal arrives with a different combination of financial documents. The pipeline does not prescribe which documents must exist — it extracts whatever is available and converges toward the same target state: **account-level P&L + Bilanz for the last 3 fiscal years, with completeness checks passing.**

**Real deal examples — what we actually received:**

| Deal | FY-3 Source | FY-2 Source | FY-1 / Current Source | Account-Level? |
|---|---|---|---|---|
| LION | GuV/Bilanz xlsx | GuV/Bilanz xlsx | SUSA xlsx | Yes (all 3 years) |
| FOX | JA PDF | JA PDF | SUSA xlsx | FY-1 yes, FY-2/3 summary only |
| AQUA | — | — | BWA PDF (YTD) | No (summary only) |
| CAT | GuV/Bilanz xlsx (2 entities) | GuV/Bilanz xlsx (2 entities) | SUSA xlsx (2 entities) | Yes (all 3 years) |

**Target state per fiscal year:**

| Level | Source | What You Get |
|---|---|---|
| Account-level (best) | SUSA xlsx, SUSA PDF, detailed GuV xlsx | Every 4-digit account with amount + S/H flag. Completeness check possible. |
| Summary-level (acceptable) | JA PDF, BWA PDF, summary GuV | ~20 line items (Gesamtleistung, COGS, Personnel, EBITDA, etc.). No account breakdown. |
| Missing | No document for that year | Gap flagged in 3-year coverage check. |

**The pipeline is additive**: if a deal starts with only a BWA PDF (summary), then later receives a SUSA xlsx for the same year, re-running `read-docs --force` replaces summary rows with account-level rows. The completeness check flips from N/A to PASS/FAIL. No manual migration needed.

**Minimum viable extraction**: Even a single BWA PDF produces useful output (summary P&L for the covered period). The pipeline doesn't refuse incomplete data — it extracts what's available, flags what's missing, and reports completeness status.

### 3.1 Pipeline Overview

```
[1. Source Selection]
    Filter deal_documents: doc_type='financials_raw', matching subtype
    Skip: already extracted AND source file unchanged (mtime check)
        |
        v
[2. Format Detection]
    xlsx → openpyxl reader (data.py pattern)
    PDF  → pdfplumber table extraction, fallback to Claude Read
        |
        v
[3. Raw Extraction]
    Parse rows → (label, value, optional_konto_nr, optional_period)
    German number format handling
        |
        v
[4. Label Normalization]
    Map German labels → canonical line_item keys (PNL_LABEL_MAP / BALANCE_LABEL_MAP)
    Preserve konto_nr when present
        |
        v
[5. Sign Normalization]
    Apply S/H convention for SUSA data
    Cost items stored as absolute values (sign applied in model, not storage)
        |
        v
[6. Unit Conversion]
    value_raw = original EUR amount
    value_k = value_raw / 1000 (rounded to 2 decimals)
        |
        v
[7. Idempotent Write]
    DELETE FROM deal_financials WHERE source_file_id = ?
    INSERT new rows
        |
        v
[8. Conflict Detection]
    Compare (domain, statement, line_item, fiscal_year) groups
    Flag where relative diff > 1%
        |
        v
[8a. Completeness Checks]
    Jahresergebnis: sum(all P&L accounts) == stated bottom line?
    Gesamtleistung: sum(8xxx) + 3960 == stated Gesamtleistung?
    3-year coverage: data exists for FY-1, FY-2, FY-3?
    FAIL = block model builder, flag for review
        |
        v
[9. Risk Flags]
    Revenue decline > 5% YoY
    EBITDA margin < 10%
    Missing fiscal years in sequence
    Net debt items incomplete (see Section 7)
        |
        v
[10. Summary Report]
    Print: files processed, rows written, conflicts, flags
    Return structured dict for CLI / upstream consumer
```

### 3.2 BWA Extraction (PDF)

```python
# Pseudocode -- not implementation
def extract_bwa_pdf(pdf_path, fiscal_year):
    tables = pdfplumber.open(pdf_path).pages[0].extract_table()
    # BWA PDFs are typically single-page
    # Columns: Label | Aktueller Monat | Kumuliert | Vorjahr
    # Target: Kumuliert column (YTD) or Vorjahr (annual)
    
    for row in tables:
        label = row[0]
        value_ytd = parse_german_number(row[2])  # Kumuliert
        value_prior = parse_german_number(row[3])  # Vorjahr
        
        line_item = match_label(label, BWA_LABEL_MAP)
        if line_item:
            yield FinRow(line_item, value_ytd, period='bwa_ytd_mXX')
            yield FinRow(line_item, value_prior, period='annual', year=fiscal_year-1)
```

**Period detection**: Extract month from filename ("BWA 4.26" = April 2026 = `bwa_ytd_m04`). If cumulative column detected, period_type = `bwa_ytd_mXX`. If annual/Vorjahr column detected, period_type = `annual`.

**Fallback**: If pdfplumber table extraction fails (non-standard layout), use Claude Read tool to extract the ~20 line items. This is acceptable because BWA PDFs are short and structured.

### 3.3 SUSA Extraction (xlsx)

Already implemented in `susa_to_model.py`. For DR-READER storage:

```python
# Uses read_susa_xlsx() from susa_to_model.py
# Returns: {konto_str: (saldo, is_soll)}
# Storage: one deal_financials row per account

for konto, (saldo, is_soll) in susa_data.items():
    value_eur = model_value(saldo, is_soll)  # -saldo if Soll, +saldo if Haben
    # Store in deal_financials:
    #   statement = 'pnl'
    #   line_item = konto  (e.g., '8400')
    #   konto_nr = konto
    #   value_raw = value_eur
    #   value_k = value_eur / 1000
    #   period_type = 'annual' or 'bwa_ytd_mXX' (from filename)
```

**Account range filtering**: Only store accounts 2000-9999 (P&L range in SKR03). Balance sheet accounts (0xxx-1xxx) are stored with `statement='balance'`.

### 3.4 SUSA Extraction (PDF) -- Automation Target #1

This is the highest-value automation target. LION session required 113 accounts manually transcribed. Pipeline:

1. **pdfplumber table extraction**: SUSA PDFs are tabular (~5 pages). Columns: Konto | Beschriftung | Anfangsbestand EB | Soll-Bewegung | Haben-Bewegung | Saldo | S/H
2. **Column mapping**: Identify Saldo column (usually column 5-6) and S/H column (usually last)
3. **Row filtering**: Skip header rows, page breaks, subtotal rows (look for "Summe", "Kontenklasse")
4. **Account validation**: 4-digit number in first column, 2000-9999 range
5. **Fallback**: If pdfplumber fails on a page, flag for manual review rather than silently skipping

**Known challenges**:
- Column alignment can shift across pages
- Some Steuerberater PDFs use text-based tables (no ruled lines) -- pdfplumber `extract_table()` may fail; use `extract_text()` with regex parsing as fallback
- Account descriptions can wrap to next line -- detect by checking if next row starts with a 4-digit number

**Quality gate**: After extraction, the Gesamtleistung completeness check (Section 5.3, Check 2) runs automatically. sum(8xxx) + model_value(3960) must match stated Gesamtleistung within 2%. FAIL blocks model builder from using this data.

### 3.5 Jahresabschluss Extraction (PDF)

Jahresabschluss PDFs contain both Bilanz and GuV. These are typically multi-page documents with narrative sections.

**Extraction strategy**: Claude Read tool as primary (complex layouts, mixed prose + tables). pdfplumber as secondary for clearly tabular sections.

**Section detection**:
1. Find "Bilanz" or "BILANZ" heading -- extract balance sheet items
2. Find "Gewinn- und Verlustrechnung" or "GuV" heading -- extract P&L items
3. Find "Anhang" heading -- stop extraction (notes section, not structured data)

**Bilanz extraction** (see Section 7 for the mandatory net debt checklist):

| German Label | line_item | statement |
|---|---|---|
| Anlagevermoegen | `fixed_assets` | balance |
| Umlaufvermoegen | `current_assets` | balance |
| Kassenbestand, Bundesbankguthaben, Guthaben bei Kreditinstituten | `cash` | balance |
| Forderungen aus Lieferungen und Leistungen | `receivables` | balance |
| Eigenkapital | `equity` | balance |
| Steuerrueckstellungen | `tax_provisions` | balance |
| Sonstige Rueckstellungen | `other_provisions` | balance |
| Pensionsrueckstellungen | `pension_provisions` | balance |
| Verbindlichkeiten gegenueber Kreditinstituten | `bank_debt` | balance |
| Verbindlichkeiten aus Lieferungen und Leistungen | `trade_payables` | balance |
| Sonstige Verbindlichkeiten | `other_liabilities` | balance |
| GF-Darlehen (Gesellschafterdarlehen) | `shareholder_loan` | balance |

**GuV extraction**: Uses same PNL_LABEL_MAP as xlsx GuV extraction in `data.py`.

---

## 4. Data Mapping: Source Fields to DB Columns

### 4.1 deal_financials

| Source Field | DB Column | Rules |
|---|---|---|
| P&L line item label | `line_item` | Normalized via PNL_LABEL_MAP (e.g., "Umsatzerloese" -> `revenue`) |
| Balance sheet label | `line_item` | Normalized via BALANCE_LABEL_MAP |
| SUSA 4-digit account | `konto_nr` + `line_item` | konto_nr = account code; line_item = account code (for SUSA) or mapped label |
| Statement type | `statement` | `pnl` / `balance` / `adjustments` / `bewertung` |
| Fiscal year | `fiscal_year` | From filename or document header. Range: 2015-2030 |
| Period | `period_type` | `annual` / `bwa_ytd_m04` / `ltm` / `forecast` |
| Value in EUR | `value_raw` | Original EUR amount, no rounding |
| Value in K EUR | `value_k` | `value_raw / 1000`, rounded to 2 decimals |
| Source filename | `source` | Filename of the originating document |
| Document ID | `source_file_id` | `deal_documents.id` -- the audit trail link |
| Extraction confidence | `confidence` | `stated` (read directly) / `computed` (derived by formula) / `estimated` (Claude inference) |
| Is adjusted | `is_adjusted` | 0 = raw reported, 1 = normalized/adjusted |

---

## 5. Conflict Detection and Risk Flags

### 5.1 Conflict Detection

Runs automatically after every extraction batch. Already implemented in `data.py:detect_conflicts()`.

**Conflict definition**: Two or more rows with identical `(domain, statement, line_item, fiscal_year)` where `value_k` differs by more than 1% relative.

**Common conflict sources**:
- BWA Gesamtleistung vs. GuV Gesamtleistung (rounding differences)
- SUSA-derived revenue total vs. GuV reported revenue (timing differences)
- Jahresabschluss P&L vs. standalone GuV (one is audited, one preliminary)
- Prior-year column in current-year BWA vs. standalone prior-year file

**Resolution hierarchy** (which source wins):
1. Jahresabschluss (audited / testiert) -- highest authority
2. SUSA (account-level detail, cumulative year-end)
3. GuV xlsx (Steuerberater-prepared)
4. BWA (management reporting, may be preliminary)

**Storage**: Conflict flags stored as `is_authoritative` on the winning row. All conflicting rows kept for audit trail. Conflict count reported in extraction summary.

### 5.2 Risk Flags

Already implemented in `data.py:compute_risk_flags()`. Extended for DR-READER:

| Flag | Condition | Severity |
|---|---|---|
| Revenue decline | Gesamtleistung YoY < -5% | High |
| Low EBITDA margin | EBITDA / Gesamtleistung < 10% | High |
| Missing fiscal years | Gap in annual data sequence | Medium |
| Net debt incomplete | Bilanz data exists but mandatory items missing (see Section 7) | High |
| SUSA vs BWA mismatch | Gesamtleistung differs > 2% between sources | Medium |
| Bestandsveraenderung material | abs(Bestandsveraenderung) > 5% of Gesamtleistung | Medium |
| Personnel cost jump | Personnel YoY change > 15% without revenue change > 10% | Medium |

### 5.3 Completeness Checks (Post-Extraction Verification)

After extracting SUSA or account-level data, DR-READER runs two mandatory completeness checks per fiscal year. These verify that **no accounts were forgotten** during extraction. This is the core quality gate -- if these pass, the extraction is trustworthy.

**Check 1: Jahresergebnis (bottom line)**

```
sum_all_pnl = sum(value_raw for all P&L accounts in fiscal_year)
jahresergebnis_stated = stated Jahresergebnis from BWA, GuV, or JA

delta = abs(sum_all_pnl - jahresergebnis_stated)
PASS if delta / abs(jahresergebnis_stated) < 0.01  (1% tolerance)
```

If PASS: all P&L accounts are accounted for. The SUSA extraction is complete.
If FAIL: accounts are missing or sign convention is wrong. Flag for review -- do NOT proceed to model builder.

**Check 2: Gesamtleistung (revenue crossfoot)**

```
sum_revenue = sum(value_raw for 8xxx accounts)       # SKR03; 4xxx for SKR04
            + model_value(3960)                       # Bestandsveraenderung, if present
gesamtleistung_stated = stated Gesamtleistung from BWA or GuV

delta = abs(sum_revenue - gesamtleistung_stated)
PASS if delta / abs(gesamtleistung_stated) < 0.02  (2% tolerance)
```

2% tolerance because Gesamtleistung may include aktivierte Eigenleistungen not always broken out as a separate SUSA account.

**When checks run**: After every SUSA extraction AND after every GuV/JA extraction that contains account-level data. BWA-only extractions are exempt (BWA provides summary lines, not individual accounts).

**Check results stored**: In `deal_financials` as synthetic rows:

| line_item | value_raw | confidence | Notes |
|---|---|---|---|
| `_check_jahresergebnis` | delta amount | `computed` | PASS/FAIL in `adjustment_note` |
| `_check_gesamtleistung` | delta amount | `computed` | PASS/FAIL in `adjustment_note` |

**Blocking behavior**: If Check 1 fails, the extraction is flagged `completeness='incomplete'`. Downstream model builder (SPEC-MODEL) refuses to populate GuV-Konten from an incomplete extraction. Roman can override with `--approve --force`, but must acknowledge the gap.

### 5.4 3-Year Coverage Check

DR-READER verifies that extracted data covers the required 3 fiscal years per deal.

```
required_years = [current_year - 1, current_year - 2, current_year - 3]
# e.g., for FY2026: [2025, 2024, 2023]

for year in required_years:
    has_pnl = exists(deal_financials WHERE statement='pnl' AND fiscal_year=year)
    has_balance = exists(deal_financials WHERE statement='balance' AND fiscal_year=year)
    if not has_pnl: warn(f"Missing P&L data for FY{year}")
    if not has_balance: warn(f"Missing Bilanz data for FY{year}")
```

Missing years are reported in the extraction summary but do not block extraction of available years. The model builder (SPEC-MODEL) can populate partially, but warns on gaps.

---

## 6. Multi-Entity Handling

Some deals involve multiple legal entities that consolidate into one acquisition target.

**Known multi-entity deals**:
- FOX (Com2Med): Com2Med MT GmbH + Com2Med MTec GmbH (2 entities)
- CAT (M&S): Medizin & Service GmbH + LIKE GmbH (2 entities, different SKR schemes)

### 6.1 Entity Model

Each entity is a separate extraction scope. The `domain` column in `deal_financials` tracks the deal-level domain (e.g., `com2med.de`), while a separate column or naming convention tracks the entity:

```
line_item naming for multi-entity:
  revenue              -- consolidated (sum of entities)
  revenue__entity_mt   -- Com2Med MT only
  revenue__entity_mtec -- Com2Med MTec only
```

Alternative approach (preferred -- uses existing schema without new columns):

```sql
-- Store entity-level data with entity prefix in source field
INSERT INTO deal_financials (domain, statement, line_item, ..., source)
VALUES ('com2med.de', 'pnl', 'revenue', ..., 'Com2Med_MT_GuV_2024.xlsx');

-- Entity identification is implicit from source_file_id linkage
-- Consolidation logic queries by domain and aggregates
```

### 6.2 Consolidation Rules

- **Revenue**: Sum of entities (no intercompany elimination assumed for ambulatory healthcare distributors)
- **Personnel**: Sum of entities
- **COGS/Material**: Sum of entities
- **Other OpEx**: Sum of entities, but flag intercompany charges if detected
- **Bilanz**: Not consolidated -- each entity's balance sheet reviewed separately for net debt

### 6.3 SKR Scheme Detection

| Deal | Entity | SKR Scheme | Revenue Accounts | COGS Accounts |
|---|---|---|---|---|
| LION | Golmed | SKR03 | 8xxx | 3xxx |
| FOX | Com2Med MT / MTec | SKR03 | 8xxx | 3xxx |
| CAT | M&S | SKR04 | 4xxx | 5xxx |
| CAT | LIKE | SKR04 | 4xxx | 5xxx |
| WOLF | KVG | SKR03 | 8xxx | 3xxx |

**Detection**: Check the first revenue account in SUSA data. If 8xxx = SKR03, if 4xxx = SKR04. `susa_to_model.py` already handles both via S/H flag convention (accounts 2000-9999 range).

---

## 7. Net Debt Checklist (Mandatory 6-Item Bilanz Review)

Every Bilanz extraction MUST check for all 6 net debt components. Missing items are flagged as `net_debt_incomplete` risk.

| # | Item | line_item | Debt-Like? | Notes |
|---|---|---|---|---|
| 1 | Kassenbestand / Bankguthaben | `cash` | No (reduces net debt) | Cash at bank. Primary offset. |
| 2 | Verbindlichkeiten gg. Kreditinstituten | `bank_debt` | Yes | Bank loans -- short and long term. |
| 3 | Steuerrueckstellungen | `tax_provisions` | **Yes** | Tax provisions are debt-like. Missed in AQUA session -- NOT operating provisions. |
| 4 | Pensionsrueckstellungen | `pension_provisions` | Yes | Pension obligations. Often material in older companies. |
| 5 | Sonstige Rueckstellungen | `other_provisions` | Partial | Split needed: warranty/litigation = operating; restructuring = debt-like. Flag for Roman review. |
| 6 | Leasing-Verbindlichkeiten | `leasing_liabilities` | Yes | May be inside sonstige Verbindlichkeiten or disclosed separately in Anhang. |

**NOT net debt (common errors)**:
- **GF-Darlehen (Gesellschafterdarlehen)**: This is a deal structure item (seller loan to company). It is eliminated at closing, not operating net debt. Store as `shareholder_loan` with `statement='balance'` but do NOT include in net debt calculation.
- **Verbindlichkeiten aus Lieferungen und Leistungen**: Trade payables are working capital, not net debt.
- **Sonstige Verbindlichkeiten (operating)**: Depends on nature. Tax liabilities (Steuerschulden) = debt-like. Social security = operating.

**Auto-computation**: If all mandatory items are present:
```
net_debt = bank_debt + tax_provisions + pension_provisions + leasing_liabilities
           + debt_like_portion_of_other_provisions
           - cash
```

Store as `line_item='net_debt_computed'`, `confidence='computed'`, `is_adjusted=0`.

Roman must confirm the net debt figure before it flows to SPEC-OFFER or SPEC-MODEL. The computed value is a starting point, not authoritative.

---

## 8. Implementation Approach

### 8.1 Technology Stack

| Component | Tool | Rationale |
|---|---|---|
| xlsx financial reading | openpyxl `load_workbook(data_only=True, read_only=True)` | Already proven in `data.py`. read_only=True prevents memory issues on large files. |
| xlsx SUSA reading | openpyxl (same as above) | Already proven in `susa_to_model.py`. Column mapping: A=account, F=saldo, G=S/H. |
| PDF table extraction | pdfplumber | Already in requirements (used by `golden.py`). Best Python library for tabular PDF extraction. |
| PDF complex layouts | Claude Read tool (via CLI) | For Jahresabschluss PDFs with mixed prose + tables. Claude handles these natively. |
| German number parsing | `_parse_german_number()` from `data.py` | Already handles "4.240.640,96" format. |
| Database | SQLite via `db.py:get_conn()` | Existing infrastructure. Tables already created in schema v2 migration. |

### 8.2 Module Structure

```
dealroom/
  src/
    data.py          -- EXISTS: xlsx GuV/Bilanz/BWA extraction (expand)
    reader.py        -- NEW: orchestrator for DR-READER pipeline
    reader_pdf.py    -- NEW: PDF extraction (BWA, SUSA, JA)
    reader_susa.py   -- NEW: SUSA-specific extraction (xlsx + PDF), reuses susa_to_model.py logic
  tools/
    susa_to_model.py -- EXISTS: SUSA reader + PS1 generator (DO NOT modify)
```

### 8.3 Idempotency Contract

Every extraction function follows this pattern:

```python
def extract_and_store(conn, doc_row, domain):
    """
    1. Delete all rows with source_file_id = doc_row['id']
    2. Parse document
    3. Insert new rows
    4. Commit
    """
    source_file_id = doc_row['id']
    
    # Clear previous extraction (idempotent)
    conn.execute(
        "DELETE FROM deal_financials WHERE source_file_id = ?",
        (source_file_id,)
    )
    
    # Parse + insert
    rows = parse_document(doc_row)
    write_rows(conn, rows)
    conn.commit()
```

Re-running on the same file replaces all previously extracted rows from that file. No duplicates. No orphans.

### 8.4 File Safety

- NEVER use `open(path, 'w')` on source documents. DR-READER is read-only.
- Temporary files for PDF processing go to `CLAUDE_COWORK/tmp/` and are cleaned up.
- openpyxl `read_only=True` prevents accidental modification.
- Source files on OneDrive are never modified by the pipeline.

---

## 9. CLI Interface

### 9.1 Command: `read-docs`

```bash
python DEALROOM.py read-docs --deal Lion
python DEALROOM.py read-docs --deal Lion --type susa
python DEALROOM.py read-docs --deal Lion --type bwa --year 2025
python DEALROOM.py read-docs --deal Lion --dry-run
python DEALROOM.py read-docs --deal Lion --force  # re-extract even if unchanged
python DEALROOM.py read-docs --all                 # all deals with registered docs
```

**Arguments**:

| Argument | Required | Default | Description |
|---|---|---|---|
| `--deal` | Yes (unless `--all`) | -- | Deal code name (Lion, Fox, Cat, etc.) |
| `--type` | No | all types | Filter: `bwa`, `susa`, `guv`, `bilanz`, `ja` |
| `--year` | No | all years | Filter by fiscal year |
| `--dry-run` | No | false | Parse and report without writing to DB |
| `--force` | No | false | Re-extract even if source file mtime unchanged |
| `--all` | No | false | Process all deals with registered financial docs |

### 9.2 Output Format

```
DEALROOM read-docs: Lion (Golmed GmbH)
=========================================

Processing 7 documents...

  [1/7] Golmed_GuV_2023.xlsx (guv, FY2023)
        -> 15 rows written to deal_financials
  [2/7] Golmed_GuV_2024.xlsx (guv, FY2024)
        -> 15 rows written to deal_financials
  [3/7] Golmed_Bilanz_2024.xlsx (bilanz, FY2024)
        -> 9 rows written to deal_financials
  [4/7] SUSA_Golmed_2025.xlsx (susa, FY2025)
        -> 178 rows written to deal_financials
  [5/7] BWA_04_2026.pdf (bwa, FY2026 YTD M04)
        -> 8 rows written to deal_financials
  [6/7] SUSA_Golmed_2024.pdf (susa, FY2024)
        -> EXTRACTION FAILED: pdfplumber table detection failed on page 3
        -> Partial: 87/113 accounts extracted. Flagged for manual review.
  [7/7] Golmed_Bilanz_2023.pdf (ja, FY2023)
        -> 12 rows written to deal_financials (balance sheet)
        -> Completeness check: Jahresergebnis PASS (delta 0.02%)

Summary:
  Files processed:  6 / 7
  Rows written:     237 (deal_financials)
  Completeness:     FY2024 Jahresergebnis PASS | FY2023 PASS | FY2025 PASS
                    FY2024 Gesamtleistung PASS (delta 0.07%)
  3-year coverage:  FY2023 OK | FY2024 OK | FY2025 OK
  Conflicts:        2 (Gesamtleistung 2024: GuV=4,241K€ vs SUSA-derived=4,238K€)
  Risk flags:       1 (EBITDA margin 8.2% in 2023, below 10% threshold)
  Pending review:   1 file (SUSA PDF partial extraction)

[!] Review gate: Run `DEALROOM.py review-extraction --deal Lion` to confirm data.
```

### 9.3 Command: `review-extraction`

```bash
python DEALROOM.py review-extraction --deal Lion
python DEALROOM.py review-extraction --deal Lion --year 2024
```

Displays extracted data in a summary table for Roman's review. Shows:
1. P&L summary by year (Gesamtleistung, COGS, Gross Profit, Personnel, EBITDA, EBIT)
2. Balance sheet summary (Cash, Bank Debt, Net Debt components)
3. Completeness check results (Jahresergebnis + Gesamtleistung per year)
4. 3-year coverage status
5. Conflicts with source details
6. Risk flags

Roman confirms with `--approve` flag or flags issues for re-extraction.

---

## 10. Anti-Patterns

These are specific failure modes observed in real deal sessions. The extraction pipeline MUST handle them.

### AP-1: SUSA PDF Manual Transcription

**What happened**: LION session required 113 SUSA accounts manually read from PDF and typed into JSON. 90 minutes of session time.

**Prevention**: pdfplumber table extraction with per-page validation. Quality gate compares extracted account count against expected range (80-200 for a typical ambulatory healthcare distributor). Partial extraction flagged, not silently accepted.

### AP-2: BWA PDF Treated as SUSA Substitute

**What happened**: BWA PDF used as sole P&L source, missing account-level detail needed for normalization analysis.

**Prevention**: If only BWA PDF exists for a fiscal year, flag as `data_completeness='summary_only'`. Extraction proceeds but downstream model builder warns that account-level data is unavailable for that year.

### AP-3: German Number Format Errors

**What happened**: Dot-comma confusion when parsing financial data ("4.240.640,96" = 4,240,640.96 EUR, not 4.240640 etc.).

**Prevention**: `_parse_german_number()` is the single parser. All extraction paths route through it. Unit test coverage for edge cases: negative values ("-1.234,56"), zero ("0,00"), large values ("12.345.678,90"), small values ("0,12").

### AP-4: Soll/Haben Sign Inversion

**What happened**: Revenue account stored as negative (Soll convention applied to Haben account).

**Prevention**: Sign convention is `model_value = -saldo if is_soll else +saldo`. Universal rule from `susa_to_model.py`. Validation warnings for accounts with unusual S/H direction (see `validate_signs()`).

### AP-5: Bestandsveraenderung (3960) Sign Hardcoded

**What happened**: Account 3960 sign assumed based on account range instead of S/H flag, producing wrong Gesamtleistung.

**Prevention**: 3960 is explicitly NOT in POSITIVE_IN_MODEL set. Its sign is determined solely by the S/H flag from the source document. Cross-check: Gesamtleistung = sum(8xxx) + model_value(3960) should match stated Gesamtleistung from BWA/GuV.

### AP-6: Steuerrueckstellungen Classified as Operating

**What happened**: AQUA session treated Steuerrueckstellungen as operating provisions, excluding from net debt. This understated net debt.

**Prevention**: Net debt checklist (Section 7) explicitly includes Steuerrueckstellungen. `tax_provisions` is a mandatory net debt component. Extraction flags if Bilanz data exists but `tax_provisions` is not extracted.

### AP-7: GF-Darlehen in Net Debt

**What happened**: Gesellschafterdarlehen (shareholder loan) included in net debt calculation, overstating debt.

**Prevention**: `shareholder_loan` is stored in `deal_financials` with `statement='balance'` but is explicitly excluded from the net debt computation formula. Comment in code explains: "GF-Darlehen is eliminated at closing -- deal structure item, not operating net debt."

### AP-8: Multi-Entity Data Mixed Without Entity Tracking

**What happened**: FOX data from two entities (MT + MTec) loaded without distinguishing which rows came from which entity, making entity-level analysis impossible.

**Prevention**: Source file linkage via `source_file_id` preserves entity provenance. Each entity's files are registered separately in `deal_documents`. Consolidation is an explicit aggregation step, not an implicit merge.

### AP-9: SUSA Column Mapping Assumed Instead of Detected

**What happened**: SUSA xlsx assumed col A=account, col F=saldo, col G=S/H, but a different Steuerberater used different column positions.

**Prevention**: Column detection in `read_susa_xlsx()` already parameterizable (`account_col`, `saldo_col`, `sh_col`). DR-READER adds auto-detection: scan header row for "Konto", "Saldo", "S/H" labels. Fall back to default positions (A/F/G) only if no headers found.

### AP-10: Extraction Without Source File Registration

**What happened**: Extraction attempted on a file not registered in `deal_documents`, losing the audit trail.

**Prevention**: `read-docs` only processes files already in `deal_documents`. If a file is not registered, it is not extracted -- the user must run `ingest-docs` first. Error message: "No registered documents found. Run `DEALROOM.py ingest-docs --deal X` first."

---

## 11. Confidence Assessment

Every extracted value receives a `confidence` tag:

| Level | Meaning | When Applied |
|---|---|---|
| `stated` | Value read directly from source document | Direct cell value from xlsx, clear table cell from PDF |
| `computed` | Derived by formula from stated values | EBITDA = Gesamtleistung - COGS - Personnel - OpEx; net_debt_computed |
| `estimated` | Inferred by Claude or heuristic | Claude Read extraction from complex PDF layout; interpolated values |
| `manual` | Entered by Roman directly | Review gate overrides, manual corrections |

**Rules**:
- `stated` values are never overwritten by `computed` or `estimated` values
- `computed` values include the formula in `adjustment_note` for audit
- `estimated` values are always flagged in extraction summary for Roman's review
- `manual` values take precedence over all other confidence levels

**Conflict resolution by confidence**: When two sources conflict, higher confidence wins. If same confidence, the authority hierarchy from Section 5.1 applies (Jahresabschluss > SUSA > GuV > BWA).

---

## 12. Dependencies and Pre-Implementation Checklist

### 12.1 Dependencies

| Dependency | Status | Notes |
|---|---|---|
| `deal_financials` table | EXISTS | Created in `_migrate_schema_v2()` |
| `deal_documents` table | EXISTS | Populated by `ingest.py:scan_deal()` |
| `data.py` extraction functions | EXISTS | `_extract_pnl`, `_extract_balance`, `_extract_bwa` |
| `susa_to_model.py` SUSA reader | EXISTS | `read_susa_xlsx()`, `model_value()` |
| `_parse_german_number()` | EXISTS | In `data.py` |
| `PNL_LABEL_MAP` / `BALANCE_LABEL_MAP` | EXISTS | In `data.py` |
| `detect_conflicts()` | EXISTS | In `data.py` |
| `compute_risk_flags()` | EXISTS | In `data.py` |
| pdfplumber | EXISTS | In requirements (used by `golden.py`) |
| openpyxl | EXISTS | In requirements |

### 12.2 Pre-Implementation Checklist

- [ ] Verify pdfplumber version supports `extract_table()` on SUSA-style PDFs (test with real LION SUSA PDF)
- [ ] Collect sample SUSA PDFs from at least 2 different Steuerberater to validate column detection
- [ ] Confirm `deal_documents` has correct `doc_subtype` for SUSA files (`susa`, not `guv` or blank)
- [ ] Verify `ingest.py` classification catches SUSA filenames: "SUSA", "Summen und Salden", "Summen-und-Salden", "Saldenliste"
- [ ] Add `period` column to `deal_financials` if not present (for BWA month tracking -- check schema)
- [ ] Test `_parse_german_number()` edge cases: negative values, parenthetical negatives "(1.234,56)", zero variants
- [ ] Confirm Jahresabschluss PDFs are readable by Claude Read tool (test with LION/AQUA JA files)
- [ ] Create `reader.py` as orchestrator that ties together existing `data.py` functions + new PDF extractors
- [ ] Add `--type susa` filter to CLI argument parser
- [ ] Implement completeness checks (Section 5.3): Jahresergebnis crossfoot + Gesamtleistung crossfoot
- [ ] Verify 3-year coverage check works across all active deals

### 12.3 Implementation Priority (Phased)

**Phase 1 -- Foundation (re-wire existing code)**:
- Create `reader.py` orchestrator
- Wire `data.py:extract_deal()` into new CLI `read-docs` command
- Add `review-extraction` command (display only, no new extraction logic)
- Conflict detection + risk flags already work

**Phase 2 -- SUSA PDF (highest value)**:
- Implement `reader_pdf.py` with pdfplumber SUSA table extraction
- Quality gate: compare extracted totals against known figures
- Test on LION, AQUA, FOX SUSA PDFs

**Phase 3 -- Jahresabschluss + BWA PDF**:
- Jahresabschluss extraction via Claude Read tool
- BWA PDF extraction via pdfplumber
- Net debt checklist enforcement

**Phase 4 -- Handoff to DR-COMMERCIAL**:
- Once deal_financials pipeline is stable, apply same read→normalize→store pattern
- DR-COMMERCIAL spec covers: customer lists, supplier lists, employee data, product splits
- Separate spec, separate implementation, same architectural principles

---

## 13. Review Gate

**Hard rule**: Extracted data does NOT flow to downstream processes (model builder, template-fill, scorecard) until Roman confirms.

### 13.1 Review Flow

```
[read-docs completes]
       |
       v
[Extraction summary printed]
[Conflicts + risk flags highlighted]
       |
       v
[Roman runs: review-extraction --deal X]
[Sees: P&L summary, Bilanz summary, completeness checks, conflicts]
       |
       v
[Roman confirms: review-extraction --deal X --approve]
[OR: Roman flags issues -> re-extract specific files]
       |
       v
[Approved data marked: is_authoritative = 1]
[Downstream processes can now query authoritative data]
```

### 13.2 Approval Scope

Approval is per-deal, per-fiscal-year. Approving Lion FY2024 data does not approve Lion FY2023.

When Roman approves:
- All `deal_financials` rows for that (domain, fiscal_year) get `is_authoritative = 1`
- Conflicts are resolved: Roman picks which source is correct
- Risk flags are acknowledged (not necessarily resolved -- some are inherent to the deal)

### 13.3 Re-Extraction After Approval

If a source file is updated after approval (new BWA version, corrected SUSA):
- `read-docs` with `--force` re-extracts, which clears `is_authoritative` for affected rows
- Roman must re-approve
- Previous approved values are logged (not deleted) for audit trail

### 13.4 What Triggers Review

The following changes require Roman's review before downstream consumption:
1. First extraction for a deal (no prior data)
2. Re-extraction that changes any `is_authoritative` row by more than 1%
3. New conflicts detected
4. New risk flags triggered
5. Net debt components changed
6. Completeness check status changed (PASS → FAIL or vice versa)

---

## Appendix A: DATEV Account Reference (SKR03 Subset)

Common accounts encountered in ambulatory healthcare distribution targets:

| Range | Category | Examples |
|---|---|---|
| 2xxx | Neutral / financial | 2650 Zinsertraege, 2100 Zinsaufwand |
| 3xxx | COGS / Material | 3400 Wareneinsatz, 3730 Skonti, 3960 Bestandsveraenderung |
| 4xxx | Personnel | 4120 Gehaelter, 4130 Sozialabgaben, 4190 Aushilfsloehne |
| 6xxx | Other OpEx | 6300 sonstige Aufwendungen, 6800 Reisekosten |
| 7xxx | D&A / Extraordinary | 7000 Abschreibungen |
| 8xxx | Revenue | 8400 Umsatzerloese, 8120 steuerfreie Umsaetze |

**SKR04 differences** (CAT/M&S deal):
- Revenue: 4xxx (not 8xxx)
- COGS: 5xxx (not 3xxx)
- Personnel: 6xxx (not 4xxx)
- Other OpEx: 6xxx-7xxx

Detection: first revenue account in SUSA. If starts with 8 = SKR03, if starts with 4 = SKR04.

## Appendix B: Cross-Reference to Other Specs

| Spec | Relationship | Shared Data |
|---|---|---|
| SPEC-MODEL | **DB is source of truth.** DR-READER stores 3 years of account-level data. Model builder reads `deal_financials` and writes into GuV-Konten + Bilanz-Konten sheets via Excel COM. Completeness check (Section 5.3) must PASS before model builder runs. | `deal_financials` (konto_nr level, 3 years) |
| SPEC-RFI | DR-READER flags -> RFI anomaly questions | `deal_financials` (YoY changes, conflicts) |
| SPEC-OFFER | DR-READER Bilanz -> net debt for offer pricing | `deal_financials` (statement='balance') |
| SPEC-ONEPAGER | DR-READER summaries -> onepager financial snapshot. Mid-term: HTML onepager reads DB directly (no Excel dependency). Commercial data from DR-COMMERCIAL. | `deal_financials` (P&L summary) |
| SPEC-LOI | DR-READER net debt -> LOI Nettofinanzstatus section | `deal_financials` (net_debt_computed) |
| **DR-COMMERCIAL** | Sibling spec. Same read→normalize→store pattern for customer/supplier/employee/product data → `deal_customers`, `deal_suppliers`, `deal_employees`, `deal_commercial`. | Separate tables, separate spec |
| **DR-GATHER** | Sibling spec. Qualitative/unstructured data from RFI responses, emails, Granola → `deal_contacts`, `deal_meetings`, `deal_notes`. | Separate tables, separate spec |
