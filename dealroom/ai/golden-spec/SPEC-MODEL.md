# SPEC-MODEL -- Financial Model Automation Boundary Specification (Bewertungsmodell)

Engineering spec for the financial model automation boundary. Defines the sheet architecture, formula dependency chain, data input schema, and safety constraints for all automated model operations. The model is the HIGHEST-PRIORITY deliverable in the DEALROOM golden corpus -- it contains formulas, multi-sheet dependencies, and formatting that must be preserved exactly.

**Core principle:** Claude READS these models, NEVER generates from scratch. For writing/updating, Excel COM via PowerShell is mandatory. `susa_to_model.py` is the validated automation tool.

**Status:** Active.
**Owner:** Roman (model design/valuation logic), Claude (data population/automation).
**Last updated:** 2026-05-19.

---

## 1. Overview

The financial model (Bewertungsmodell) is Repuro's core valuation workbook for acquisition targets. Each target gets one model, iteratively refined (version numbers up to v14 observed). The model:

1. Ingests raw accounting data (SUSA/Saldenliste) into **GuV-Konten**
2. Aggregates and transforms via formulas into **GuV** (P&L in K EUR)
3. Feeds the **Bewertung** sheet with adjusted EBITDA/EBIT for enterprise value calculation
4. Maintains a parallel **Bilanz** (balance sheet) for net debt/cash computation
5. Contains deal-specific adjustments (salary normalization, one-offs, entity consolidation)

### Integration with susa_to_model.py

The validated automation pattern lives at:
`CLAUDE_REPURO/dealroom/tools/susa_to_model.py`

It performs exactly ONE operation: write raw SUSA account balances into the **GuV-Konten** sheet. It:
- Reads the model's account map (column B = account numbers, target column = year data)
- Reads SUSA data (xlsx or JSON) with account number, saldo, Soll/Haben flag
- Applies sign convention: Soll (debit) = negative, Haben (credit) = positive
- Generates a PowerShell COM script that writes cell values via Excel COM automation
- Copies model to local temp (OneDrive causes COM RPC errors), writes, copies back

The tool NEVER touches formulas, formatting, or any sheet other than GuV-Konten.

### Golden File Roles

| Deal | File | Type | Key characteristics |
|---|---|---|---|
| FOX (Com2Med) | `260518_Com2Med_v7.xlsx` | 2-entity, consolidated | 7 sheets, 2 legal entities (323 + 441), consolidated GuV-Konten with entity columns O-T. SKR03 (8xxx revenue). 342 rows in GuV-Konten, 0 individually mapped accounts in col B (uses entity sub-columns instead). |
| CAT (M&S) | `260505_MundS_v7.xlsx` | 2-entity, consolidated | 18 sheets, entity raw data sheets (M&S21-25, LIKE21-25), most complex. **SKR04** (4xxx revenue, 5xxx COGS, 6xxx personnel). 394 rows in GuV-Konten, 91 individually mapped accounts. |
| LION (Golmed) | `260514_Golmed_v14.xlsx` | Single-entity | 7 sheets, most iterated (v14), cleanest single-entity reference. SKR03 (8xxx revenue). 497 rows in GuV-Konten, 178 individually mapped accounts. |
| WOLF (KVG) | `260319_KVG_Model_v4.xlsx` | Single-entity | 15 sheets, extra analysis sheets (Seller Vergleich, BWA, Bilanz snapshots). SKR03 (8xxx revenue). 545 rows in GuV-Konten, 188 individually mapped accounts. |

---

## 2. Sheet Architecture

### 2.1 Universal Sheets (present in ALL models)

| Sheet | Purpose | Automation scope |
|---|---|---|
| **Cover** | Title page: B6="Repuro Gruppe", B11="Internes Model fuer", B12=company name, F16/H16=Currency/EUR, F17/H17=Transaction Year, F18/H18=Locked-Box Year | NEVER touch (except company name + years on new deal setup) |
| **Bewertung** | Enterprise value calculation, payment structure, sensitivity | MOSTLY FORMULA -- Roman sets EBITDA targets (I6/J6), multiples, and payment structure; all other cells are formula-driven |
| **GuV** | P&L summary in K EUR (thousands), adjusted + reported views | READ ONLY -- formula-driven from GuV-Konten |
| **Bilanz** | Balance sheet with net debt/cash calculation | MANUAL INPUT for category totals; account-level detail in bottom section |
| **GuV-Konten** | Raw accounting data by SKR03 account | AUTOMATED INPUT TARGET -- susa_to_model.py writes here |
| **INPUT ->** | Separator/divider sheet (1 row, no data) | NEVER touch |

| **Notes (WIP)** | Methodology checklist: (1) SUSA import procedure, (2) GuV-Konten mapping, (3) Bilanz mapping, (4) cross-checks. Contains check result flags (C27-C29): Check Bewertung, CHECK GUV, CHECK BILANZ. Also documents adjustment/net debt methodology. | Template copy, update check flags when model is complete |

### 2.2 Common Optional Sheets

| Sheet | Present in | Purpose |
|---|---|---|
| **Vergleich** | FOX, LION | Offer comparison across deal history (Initial/Counter/Final) |
| **Vergleich_Rep** | WOLF | Seller value comparison (Verkauf vs. Fortfuehrung). SENSITIVE -- contains "Sollten wir nicht zeigen!" annotation. |
| **Claude Log** | CAT, WOLF | Audit trail of Claude modifications to the model (Turn#, Date, Request, Action, Details, Outcome) |
| **ND_Positions** | CAT | Net debt position detail for multi-entity (account-level: Konto, Account name, Saldo, S/H, Signed amount, Category, Include?, PDF page) |

### 2.3 Deal-Specific Sheets

**Multi-entity models (CAT, FOX):** Entity raw data sheets contain the original SUSA/BWA imports per legal entity and year. Pattern: `{Entity}{Year}` or `{Entity}{Year}lang` (long version with account-level detail).

CAT entity sheets:
- `M&S25`, `M&S24`, `M&S24lang`, `M&S23`, `M&S21` -- Medizin & Service GmbH
- `LIKE25`, `LIKE24`, `LIKE23`, `LIKE21` -- LIKE Medizintechnik GmbH

FOX has entity columns within GuV-Konten rather than separate sheets (cols O-T for Com2Med Med. Technologien GmbH & Co. KG entity 323).

WOLF extra sheets:
- `Seller Vergleich` -- 4-scenario comparison for seller (Selbstaendig vs. Verkauf, 2J/5J, +5%/+20%). Inputs: Gehalt GF, Tantieme, EBITDA Basis, Earn-Out/Super Earn-Out thresholds, Rueckbeteiligung, Netto-Gewinn, Gewinnvortrag.
- `Vergleich_Rep` -- Repuro vs. Fortfuehrung analysis. Contains sensitive annotation: "Sollten wir nicht zeigen!" (should not be shown to seller).
- `2025_BWA`, `2023_GuV` -- Raw BWA/P&L imports
- `2024_Bilanz`, `2024_Bilanz (2)`, `2025_Bilanz` -- Raw balance sheet imports

LION extra sheets:
- `Vergleich` -- Cross-deal offer comparison (Golmed vs. Cat vs. Fox). Columns: Company Profile (Total Sales, YoY Growth, Adj. EBITDA, Margin, Employees), Valuation (EV at Closing, EV anticipated, Total EV), Multiples, EV-to-Equity Bridge.

FOX extra sheets:
- `Vergleich` -- Offer comparison within deal: Initial Offer vs. Counter Offer vs. Final Offer. Rows: EBITDA 24/25, Avg, EO/Super-EO thresholds, Net Debt, Sofortzahlungen, Earn-Out, Super Earn-Out, Multiples.

### 2.4 Sheet Order

Sheet order varies by model but follows a consistent logical pattern:
1. Cover (always first or near-first)
2. Analysis/comparison sheets (Vergleich, Notes)
3. **Bewertung** (core valuation)
4. **GuV** (P&L output)
5. **Bilanz** (balance sheet)
6. **INPUT ->** (separator)
7. **GuV-Konten** (raw data)
8. Entity/source data sheets (if any)

---

## 3. BEWERTUNG Deep Dive

The Bewertung sheet is the single most critical sheet in the model. It is primarily formula-driven from GuV and Bilanz data, with a small number of manual-input cells where Roman sets valuation parameters (EBITDA targets, multiples, payment structure). It contains three logical sections.

### 3.1 Section A: Valuation (rows 2-19)

Consistent across all four models. All values in K EUR.

| Row | Label | Content | Source |
|---|---|---|---|
| 2 | Error check | `No Errors` or `ERROR FOUND - CHECK` | Formula checking GuV-Konten integrity |
| 3 | Header | `Unternehmensbewertung` or `Valuation` + year headers | Manual labels |
| 4 | Adj. Gesamtleistung | Adjusted total sales per year | Formula from GuV |
| 5 | Adj. EBIT | Adjusted EBIT per year | Formula from GuV |
| 6 | Adj. EBITDA | Adjusted EBITDA per year | Formula from GuV |
| 7 | % growth | YoY EBITDA growth | Formula |
| 8 | Rep. EBIT | Reported (unadjusted) EBIT | Formula from GuV |
| 10 | EV at closing | Enterprise value at closing multiple | Formula: Avg EBITDA x multiple |
| 11 | EV anticipated Earn-Out | EV including anticipated earn-out | Formula |
| 12 | Total EV incl. Super-Earn-Out | Maximum EV scenario | Formula |
| 13 | +/- Net Cash (Net Debt) | Net financial position | Links to Bilanz |
| 14 | - Permitted Leakage | Cash extraction adjustments | Manual or formula |
| 15 | Equity Value | Enterprise value + net cash - leakage | Formula |
| 16 | At Closing | % and amount paid at closing | Formula |
| 17 | Vendor Loan | Deferred payment amount | Manual or formula |
| 18 | Earn-Out anticipated | Expected earn-out payment | Formula |
| 19 | Super Earn-Out | Maximum additional earn-out | Formula |

**Column layout (universal pattern):**

| Column | Content | Notes |
|---|---|---|
| B | Row labels | Always in column B |
| C-F | Historical years (typically 2022-2025) | 4 years standard |
| G-H | Projections (WOLF only: 5yr+ growth) | WOLF has G,H for growth projections |
| H or J | Avg. 2024-25P (average of last 2 years) | Valuation basis |
| I or K | 2026 BP (business plan) | Budget/plan figure |
| J or L | 2026 MAX EO (maximum earn-out scenario) | Stretch target |
| L or N | Valuation (the actual offer) | Key output column |
| N | Multiples column | Implied multiples per year |

**CRITICAL:** Column positions shift between models. FOX/CAT/LION use H for average, I-J for projections, L for valuation, N for multiples. WOLF uses J for average, K-L for projections, N for valuation. Automation must READ column headers (row 3) to determine layout, never hardcode column positions.

### 3.2 Section B: EBIT Reconciliation (rows 22-47, varies by model)

This section shows the bridge from reported net income to adjusted EBIT and pro-forma EBIT. Deal-specific content.

**Universal structure:**
- Ergebnis nach Steuern (net income)
- \+ Steuern (taxes)
- \+ Zinsaufwand (interest expense)
- \- Zinsertraege (interest income)
- +/- Sonstiger neutraler Ertrag/Aufwand (extraordinary items)
- = EBIT (reported)
- Salary adjustments (old GF salary out, new salary in, social charges)
- = EBIT Pro-Forma

**Multi-entity difference (CAT):** Rows 28-29 show separate net income lines per entity (M&S + LIKE), then consolidate. Row 37 adds "Fehlende Abschreibungen" (missing depreciation). Single-entity models have one net income line.

**Deal-specific adjustments (examples):**
- FOX: `- Neues Gehalt Muehlan`, `- Nebenkosten (17%)`
- LION: `+ Weitere Gehaltsanpassung nicht-operative Familie`, `+ Gewinnentnahme / Bilanzgewinn`, `+ Cash 2026 generated (70% EBIT)`
- WOLF: `Rueckbeteiligung (verringert Zahlung @Closing)`, `Wertsteigerung Rueckbeteiligung`
- CAT: `- Fehlende Abschreibungen`, 2-entity consolidation

### 3.3 Section C: Net Debt / Nettofinanzstatus (rows 48-102, varies heavily)

This section computes net cash or net debt by listing individual bank accounts, loans, provisions, and other financial positions with their account numbers and balances.

**Universal pattern:**
1. Header: "(A) Berechnung Netto-Sofortkaufpreis" or "Berechnung Nettofinanzstatus"
2. Cash positions: individual bank accounts by name (Kasse, Nord/LB, Volksbank, Sparkasse, etc.)
3. Working capital adjustment line (if applicable)
4. Non-operative liquid assets subtotal
5. Tax provisions (Gewerbesteuer, Koerperschaftsteuer)
6. Other provisions
7. Bank loans and financing items (individual lines per loan/lease)
8. Non-operative liabilities subtotal
9. **Nettofinanzstatus** = net cash/debt figure that feeds row 13

**Multi-entity difference (CAT/FOX):** Net debt section lists positions by entity (B column shows entity code "323" or "441" in FOX). Separate subtotals per entity, then consolidated total.

**Column layout in this section:**
- Column B: position label
- Column C: account number (Konto)
- Column E: prior year value (EUR, not K EUR -- full euro amounts)
- Column F: current year value (EUR)

**CRITICAL:** Values in this section are in FULL EUROS, not thousands. The Nettofinanzstatus total is converted to K EUR when referenced in row 13. This is a common source of errors.

---

## 4. Formula Dependency Chain

```
SUSA Export (raw trial balance, EUR)
    |
    v
GuV-Konten (EUR, individual accounts)
    |  - Account numbers in column B
    |  - Year data in columns D-H (or further for entity splits)
    |  - Section headers organize accounts by P&L category
    |  - Bottom section: EBIT reconciliation + Pro-Forma calculation
    |
    +---> GuV (K EUR, /1000 transformation)
    |       |  - Row 4-21: Adjusted P&L (Revenue through Net Income)
    |       |  - Row 23-28: Margin percentages
    |       |  - Row 30+: Adjustment detail with account references
    |       |  - Row 62+: Reported (unadjusted) P&L bridge
    |       |  - Row 72+: Check formulas (adjusted vs reported)
    |       |
    |       +---> Bewertung rows 4-8 (valuation inputs)
    |       +---> Bewertung rows 10-12 (EV calculations)
    |       +---> Bewertung EBIT reconciliation section
    |
    +---> Bilanz (EUR, category-level)
            |  - Rows 4-20: Assets (Aktiva)
            |  - Rows 23-39: Liabilities + Equity (Passiva)
            |  - Rows 41-44: Check formulas
            |  - Rows 46+: Net debt detail (account-level)
            |
            +---> Bewertung row 13 (Net Cash/Debt)
            +---> Bewertung Section C (Nettofinanzstatus)
```

### Key formula relationships

1. **GuV-Konten --> GuV:** Each GuV line item (e.g., C4 "Revenue") sums specific account ranges from GuV-Konten, divided by 1000. The KONSOLIDIERT column (C) in GuV-Konten already holds the consolidated value for multi-entity models.

2. **GuV --> Bewertung rows 4-8:** Direct reference. Bewertung!C4 references GuV for Adj. Gesamtleistung. The "Avg" column (H or J) averages the last 2 historical years.

3. **Bewertung rows 10-12 (EV):** These contain valuation outputs. In most models they are formulas (Avg EBITDA x multiple). However, Roman may override specific cells with hardcoded values during negotiation — in that case the cell is no longer formula-driven.
   - EV at closing = Avg EBITDA x closing multiple (or Roman override)
   - EV anticipated = Avg EBITDA x earn-out multiple (using 2026 BP EBITDA)
   - Total EV = Avg EBITDA x max multiple (using 2026 MAX EO EBITDA)
   - The valuation column (L or N) shows the absolute EUR K value
   - **Before writing**: always check whether the cell contains a formula (preserve) or a hardcoded value (safe to update)

4. **Bilanz --> Bewertung row 13:** Net debt figure from Bilanz net cash calculation feeds into equity bridge.

5. **Error check (row 2):** Formula compares reported earnings from GuV-Konten hardcoded section against computed values. Shows "No Errors" or "ERROR FOUND - CHECK".

### GuV-Konten internal structure

Row layout (consistent across models):

| Section | Typical rows | Content |
|---|---|---|
| Headers | 2-3 | Error check, column headers (Konto, KONSOLIDIERT, year labels) |
| Umsatzerlöse | 5-13 | Revenue accounts (8xxx) |
| Bestandsveränderungen | ~14-20 | Inventory changes |
| Aktivierte Eigenleistung | ~18-24 | Capitalized own work |
| Material- und Wareneinkauf | ~21-50 | COGS accounts (3xxx, some 5xxx) |
| Sonstige Erlöse | ~32-65 | Other operating income (2xxx) |
| Betrieblicher Rohertrag | formula row | Gross profit subtotal |
| Personalkosten | ~45-90 | Personnel (4xxx) |
| Raumkosten | ~60-100 | Rent/space costs (4xxx) |
| Versicherungen/Beiträge | varies | Insurance |
| Fahrzeugkosten | varies | Vehicle costs (large section in WOLF: 50+ accounts) |
| Werbe-/Reisekosten | varies | Marketing/travel |
| Kosten Warenabgabe | varies | Distribution costs |
| Reparatur/Instandhaltung | varies | Maintenance |
| Abschreibungen | varies | Depreciation (6xxx) |
| Sonstige Kosten | varies | Other costs |
| Summe der Kosten | formula row | Total costs |
| Betriebsergebnis | formula row | Operating result |
| EBITDA | formula row | EBITDA |
| Zinsaufwand | varies | Interest expense (2xxx) |
| Sonstiger neutraler Aufwand | varies | Extraordinary expenses (2xxx) |
| Zinserträge | varies | Interest income (2xxx) |
| Sonstiger neutraler Ertrag | varies | Extraordinary income (2xxx) |
| Ergebnis vor Steuern | formula row | Pre-tax result |
| Steuern | varies | Tax accounts (7xxx) |
| Ergebnis nach Steuern | formula row | Net income |
| Hardcode check | varies | Manual hardcoded values for validation |
| Ratios | varies | Margins, growth rates |
| EBIT reconciliation | bottom section | Pro-forma EBIT bridge (same as Bewertung section B) |

**Account ranges across models:**
- FOX: **0 accounts individually mapped in column B** -- consolidated view uses category labels (Umsatzerloese, Material, etc.) without individual account numbers. Sub-account detail is in entity columns (O-T) instead. This means susa_to_model.py's `read_model_account_map()` (which scans col B for 2000-9999 numbers) will find 0 matches. FOX requires a different approach: accounts are mapped via the entity sub-columns.
- CAT: 4120-7685, 91 individually mapped accounts (SKR04 range)
- LION: 2000-8935, 178 individually mapped accounts (most granular, best for susa_to_model.py)
- WOLF: 2010-8800, 188 individually mapped accounts

---

## 5. Data Input Schema

### 5.1 Automated Inputs (via susa_to_model.py)

| Input | Source | Target | Format |
|---|---|---|---|
| SUSA trial balance | Steuerberater export (.xlsx or .json) | GuV-Konten, specific year column | Account number + Saldo + S/H flag |

**susa_to_model.py config:**
```json
{
  "deal_folder": "C:\\...\\250724_Golmed (Lion)",
  "model_subfolder": "2_Model",
  "model_filename": "260514_Golmed_v14.xlsx",
  "guv_sheet_name": "GuV-Konten",
  "sources": [
    {
      "name": "fy2025",
      "target_column": 8,
      "susa_xlsx_path": "C:\\...\\SUSA_2025.xlsx"
    }
  ],
  "header_updates": [[3, 11, "Delta 25"]],
  "crosschecks": {"Umsatz_2025": 7821903.47},
  "skip_accounts": ["2870"]
}
```

**Sign convention (universal SKR03):**
- Soll (S/debit) accounts --> negative value in model (costs, expenses)
- Haben (H/credit) accounts --> positive value in model (revenue, income)
- Exceptions flagged by `POSITIVE_IN_MODEL` set in susa_to_model.py (revenue accounts 8xxx that are normally Haben)

### 5.2 Manual Inputs (Roman)

| Input | Location | When |
|---|---|---|
| Bilanz category totals | Bilanz sheet, cols D-H | Per year, from Jahresabschluss |
| Bilanz net debt detail | Bilanz lower section | Per year, account-level from balance sheet |
| EBITDA adjustments | GuV rows 30+ | After initial data load, deal-specific |
| Salary normalization | GuV rows 40-48 | Per deal, based on offer terms |
| Bewertung valuation inputs | Bewertung I-J cells (2026 BP, MAX EO) | Roman's judgment/negotiation position |
| Offer history | Vergleich sheet | Per negotiation round |
| Current trading data | GuV cols M-N (monthly/quarterly) | During active negotiation |

### 5.3 Formula-Derived (never manually entered)

| Output | Location | Derived from |
|---|---|---|
| Adj. EBITDA/EBIT | Bewertung rows 5-6 | GuV formulas |
| Enterprise value | Bewertung rows 10-12 | EBITDA x multiple |
| Equity value | Bewertung row 15 | EV + net cash - leakage |
| Payment split | Bewertung rows 16-19 | Equity value allocation |
| All GuV line items | GuV rows 4-21 | GuV-Konten SUM formulas |
| All margins/ratios | GuV rows 23-28 | Division formulas |
| Bilanz checks | Bilanz rows 41-44 | Aktiva vs Passiva |
| Error flag | Row 2 of GuV/GuV-Konten/Bilanz | Check formulas |

---

## 6. Template Fill Map

### Cells automated by susa_to_model.py

| Sheet | Column | Row range | Content | Write method |
|---|---|---|---|---|
| GuV-Konten | D-H (year cols) | Account rows (varies, 50-500) | Raw SUSA saldo values in EUR | Excel COM via PS1 |
| GuV-Konten | Row 3 headers | Specific cells | Year/period labels | Excel COM via PS1 (header_updates) |

### Cells that are formula-driven (NEVER write)

| Sheet | Scope | Formula type |
|---|---|---|
| GuV | All data cells | SUM/reference from GuV-Konten |
| Bewertung | Rows 4-19 | Reference from GuV + Bilanz + manual multiples |
| Bewertung | EBIT reconciliation | Reference from GuV-Konten |
| GuV-Konten | Subtotal rows (Rohertrag, Betriebsergebnis, EBITDA, etc.) | SUM of account ranges |
| GuV-Konten | Ratio rows (bottom section) | Division formulas |
| Bilanz | Check rows (41-44) | Aktiva - Passiva |

### Cells that need Roman (manual judgment)

| Sheet | Cells | Content |
|---|---|---|
| Bewertung | I6, J6 (or K6, L6 in WOLF) | 2026 BP and MAX EO EBITDA targets |
| Bewertung | L10-L12 (or N10-N12) | Valuation amounts (EV at closing, EO, total) |
| Bewertung | L16-L19 (or N16-N19) | Payment structure (closing, vendor loan, EO, super EO) |
| Bewertung | Net debt detail | Account-level positions and amounts |
| GuV | Adjustment rows 30+ | Deal-specific adjustments and account references |
| GuV | Current trading cols (M-N) | Monthly/quarterly actuals |
| Bilanz | All category totals | From Jahresabschluss (manually entered or referenced) |

---

## 7. Edge Cases and Hardening

### 7.1 Multi-Entity Consolidation (CAT, FOX)

**CAT pattern (separate sheets):**
- Raw SUSA data lives in entity-specific sheets (M&S25, LIKE25, etc.)
- GuV-Konten has a KONSOLIDIERT column (C) that consolidates both entities
- Entity-specific columns exist further right (M-T for M&S, further right for LIKE)
- GuV and Bewertung reference the KONSOLIDIERT column only
- Entity sheets have different formats per year (M&S24lang has 414 rows vs M&S24 with 38)

**FOX pattern (entity columns within GuV-Konten):**
- GuV-Konten cols B-H contain consolidated data
- Cols O-T contain entity-specific data for "Com2Med Med. Technologien GmbH & Co. KG (323)"
- Column P header: "MT" (entity abbreviation)
- Consolidation happens within GuV-Konten formulas, not across sheets

**Automation implication:** When running susa_to_model.py on a multi-entity model, you must specify the correct target columns. For FOX, consolidated data goes to cols D-H, entity data to Q-T. For CAT, the entity sheets are reference-only; consolidated data goes to the standard columns.

### 7.2 SKR03 vs SKR04 Account Mapping

CAT (M&S) uses SKR04. All other models use SKR03. This means the same P&L positions have different account number ranges:

| P&L Line | SKR03 (WOLF, LION, FOX) | SKR04 (CAT) |
|---|---|---|
| Revenue | 8xxx (8400 = Erloese 19% USt) | 4xxx (4400 = Erloese 19%) |
| Cost of Sales | 3xxx (3400 = Wareneingang 19% Vorsteuer) | 5xxx (5400 = WE Service) |
| Personnel | 4xxx (4120 = Gehaelter) | 6xxx (6020 = Gehaelter) |
| GF Salary | 4120 | 6027 (Geschaeftsfuehrergehaelter) |
| Other OpEx | 4xxx-6xxx | 6xxx-7xxx |
| Interest | 2xxx (2650 = Zinsertraege) | 7xxx |
| Skonti (received) | 3730-3760 | 5730-5736 |
| Skonti (granted) | 8730-8743 | 4730-4743 |

**susa_to_model.py handles this transparently** -- it reads the account map from column B of the actual model, matching whatever accounts are present. No hardcoded SKR logic needed. But when manually reviewing cross-checks or spot-checks, be aware that account numbers differ between CAT and the other three.

### 7.3 Column Position Drift

Year columns are NOT fixed across models:

| Model | Historical start | Historical end | CAGR col | Current trading cols |
|---|---|---|---|---|
| FOX | D (2021) | H (2025) | J | L-M (Q1-2025, Q1-2026) |
| CAT | D (2021) | H (2025) | K | O-P (Q1-2025, Q1-2026) |
| LION | D (2021) | H (2025) | K | M-N (04/25, 04/26) |
| WOLF | D (2022) | G (2025) | I | K-L (XX-24, XX-25) |

WOLF starts one year later (2022 not 2021) and has fewer columns. LION and CAT have an extra 2026 column (I). The susa_to_model.py `target_column` parameter handles this -- it takes the Excel column NUMBER (D=4, E=5, etc.).

**GuV-Konten header row (R3) detail from golden models:**

| Model | R3 content |
|---|---|
| WOLF | `B3=Konto, C3=KONSOLIDIERT, D3=2022, E3=2023, F3=2024, G3=2025A, I3=Kommentar / zu hinterfragen` |
| CAT | `B3=Konto, C3=KONSOLIDIERT, D3=2020, E3=2021, F3=2022, G3=2023, H3=2024, I3=2025, K3=Kommentar, M3=Konto, N3=M&S, O3=2020` |
| LION | `B3=Konto, C3=KONSOLIDIERT, D3=2021, E3=2022, F3=2023, G3=2024, H3=2025, J3=04-25, K3=04-26, M3=Kommentar / zu hinterfragen` |
| FOX | `B3=Konto, C3=KONSOLIDIERT, D3=2021, E3=2022, F3=2023, G3=2024, H3=2025, J3=Q1-2025, K3=Q1-2026, M3=Kommentar, O3=Konto, P3=MT` |

### 7.4 Error Flag States

Row 2 across GuV-Konten, GuV, and Bilanz shows either:
- `No Errors` -- all check formulas pass
- `ERROR FOUND - CHECK` -- at least one check failed

The error flag is a formula. After writing SUSA data, the model may temporarily show errors until all years are populated. This is expected during incremental data loading.

### 7.5 Bilanz Structure Variations

- FOX: Bilanz has TWO sections -- rows 3-39 (Bilanz by category) and rows 46-87 (same structure repeated, likely for a different entity or period). Rows 88+ contain net debt detail per entity.
- CAT: Standard single section with net debt detail starting at row 46.
- LION: Additional rows for "Fehlbetrag" (accumulated deficit, row 20) and "Nicht gedeckt" (uncovered equity, row 26). Net debt starts at row 49.
- WOLF: Simplest. Standard structure, net debt at row 46.

### 7.6 GuV Adjustment Section Variations

The adjustment section (GuV rows 30+) is the most deal-specific part. Common patterns:

**Revenue adjustments:**
- Activated own services (Aktivierte Eigenleistung) -- CAT removes this
- Entity intercompany eliminations (Verrechnungen) -- CAT
- Lease reclassification (Mietvertrag) -- CAT, FOX

**Personnel adjustments (universal):**
- Old GF salary added back
- New GF salary deducted (post-acquisition)
- Tantieme (bonus) adjustments
- Social charges at 17% (Nebenkosten)
- Additional family salary adjustments (LION: non-operative family)

**OPEX adjustments:**
- Extraordinary expenses removed (Sonstiger Neutraler Aufwand)
- Vehicle cost reclassification (WOLF)
- One-off legal/consulting costs (CAT)

**D&A adjustments (some models):**
- Vehicle depreciation reclassification (CAT, WOLF)
- Goodwill amortization removal
- Missing depreciation addition (CAT: Fehlende Abschreibungen)

### 7.7 Bewertung Valuation Column Mapping

The "Valuation" column (where the actual offer sits) is at:
- FOX: L (col 12)
- CAT: L (col 12)
- LION: L (col 12)
- WOLF: N (col 14)

WOLF uses N because it has additional growth projection columns (G, H) pushing everything right.

### 7.8 Permitted Leakage Definitions

Row 14 varies significantly:
- FOX: "Permitted Leakage (Gehalt von Muehlan fuer 18 Monate vs. 6 Monate Cashgenerierung)" -- specific to deal timeline
- CAT: "Permitted Leakage" -- generic
- LION: "Permitted Leakage (siehe unten)" -- references rows 22-24 which detail: Gewinnentnahme + Cash 2026 generated (70% EBIT)
- WOLF: "Permitted Leakage" -- generic

### 7.9 Bewertung Szenarioanalyse Variations

The sensitivity analysis section (columns Q-T) varies in structure across models:

| Model | Metric | Scenario Values | Column Layout |
|---|---|---|---|
| WOLF (KVG) | Adj. EBIT | R5=700, S5=750 (implied), T5=800 | Q3: "Szenarioanalyse Earn-out EBIT 26-27". 3 scenarios. Rows: Multiple, Kaufpreis, Enterprise Value, Net Debt, Fixed Payment, Earn-Out. |
| CAT (M&S) | Adj. EBITDA | R6=590, S6=640, T6=690 | Q3: "Szenarioanalyse Earn-out EBITDA 26-27". 3 scenarios. Q4 shows "25-27" reference period with Avg EBITDA. |
| LION (Golmed) | Adj. EBITDA | R6=610, S6=635 (2 scenarios) | Q3: "Szenarioanalyse Earn-out EBITDA 26-27". Includes Q20 "Diff vs. anticipated" delta row. |
| FOX (Com2Med) | EBIT and EBITDA | T5=Adj. EBIT, T6=Adj. EBITDA | T2: "Comment for CLAUDE: THIS IS THE EARN-OUT TABLE". Earn-Out presented as table with Fixed Payment and Earn-Out rows. |

**Key observation:** WOLF uses EBIT-based scenarios; CAT, LION, and FOX use EBITDA-based scenarios. The choice depends on deal structure (whether D&A adjustments are material).

### 7.10 Bewertung EBIT Bridge Start Row Variations

| Model | Nebenrechnung Label | Start Row | GF Salary Rows | Nettofinanzstatus Start |
|---|---|---|---|---|
| WOLF (KVG) | (not labeled as Nebenrechnung) | ~R40 area | R40-R42: Altes/Neues Gehalt Schroecke + Nebenkosten 17% | R48 "(A) Beispielhafte Berechnung Netto-Sofortkaufpreis" |
| CAT (M&S) | "Nebenrechnung fuer EBIT-Bestimmung (K EUR)" | R25 | Not in first 60 rows | In separate ND_Positions sheet |
| LION (Golmed) | "Nebenrechnung fuer EBIT-Bestimmung (K EUR)" | R28 | R43-R45: Altes/Neues Gehalt Golland + Nebenkosten 17%. R41: "Weitere Gehaltsanpassung nicht-operative Familie" | R51 "(A) Berechnung Nettofinanzstatus" |
| FOX (Com2Med) | "Nebenrechnung fuer EBIT-Bestimmung" | R23 | R32-R33: Neues Gehalt Muehlan + Nebenkosten 17% (no old salary line -- was already GF) | Below R34 (within Bewertung) |

### 7.11 Comment Cells

Some models contain Claude comment cells (visible in output):
- FOX Bewertung N1: "Comment Claude: THIS IS OFFER HISTORY"
- FOX Bewertung B22: "Comment CLAUDE: THIS IS WHAT CAN BE SHOWN TO SELLERS AS PRO-FORMA EBIT"
- FOX GuV C1: "Comment CLAUDE: This is the P&L output (comment section is important)"
- FOX GuV C29: "Comment Claude (this is how the adjustment logic should be..."

These are in-model documentation added during previous sessions. They must be preserved.

---

## 8. Hard Constraints

These constraints are absolute. Violation of any one creates model corruption that requires manual repair.

1. **NEVER use openpyxl to WRITE to a financial model** -- Excel COM via PowerShell only. openpyxl destroys conditional formatting, named ranges, chart objects, merged cells, and print areas on write. Reading with `data_only=True, read_only=True` is safe.

2. **NEVER generate a model from scratch** -- always copy an existing golden template or the deal's current model version. The model contains hundreds of formulas, cross-sheet references, and formatting that cannot be reproduced programmatically.

3. **NEVER modify BEWERTUNG formulas** -- only raw data cells in GuV-Konten are writable by automation. Bewertung is MOSTLY FORMULA with a small number of manual-input cells (I6/J6 EBITDA targets, multiples, L10-L12/L16-L19 valuation and payment structure) that Roman sets directly. If a formula-driven Bewertung value is wrong, the fix is in GuV-Konten or GuV adjustment rows.

4. **NEVER delete or rename sheets** -- sheet references are hardcoded in formulas (e.g., `='GuV-Konten'!F47*-1/1000`). Renaming breaks every cross-sheet formula.

5. **NEVER change cell formatting, column widths, or row heights** -- formatting is part of the model's presentation to sellers and investors. Roman sets this manually.

6. **NEVER modify named ranges or print areas** -- these control PDF export layout for deal documents.

7. **NEVER touch chart objects** -- Vergleich sheets may contain charts. Excel COM chart manipulation is fragile and unnecessary.

8. **Formula chain must remain intact** -- if GuV-Konten data changes, GuV and Bewertung must auto-recalculate. Never overwrite a formula cell with a hardcoded value. The only exception: the "Hardcode" check rows (GuV-Konten bottom section) which are intentionally hardcoded for validation.

9. **Preserve the native consolidation pattern per model** -- multi-entity models use EITHER sheet-per-entity (CAT: separate M&S/LIKE sheets) OR column-per-entity within GuV-Konten (FOX: cols O-T for entity 323). Never restructure a model's consolidation approach. The KONSOLIDIERT column (C) handles the consolidated view via formulas in both patterns.

10. **BEWERTUNG view state must be preserved** -- zoom level, frozen panes, selected cell, and scroll position are part of Roman's working environment. Excel COM `$xl.ScreenUpdating = $false` prevents view disruption during writes.

11. **Values in Bilanz net debt section are in FULL EUROS** -- not thousands. Do not divide by 1000 when writing to this section. The K EUR conversion happens in the formula that references these cells from Bewertung row 13.

12. **OneDrive files must be copied to local temp before COM operations** -- OneDrive file locking causes COM RPC errors. Pattern: copy to `C:\Users\X1\Documents\CLAUDE_COWORK\`, write, copy back. susa_to_model.py implements this.

13. **Column positions are model-specific** -- never hardcode column numbers across models. Always read row 3 headers to determine year column positions. The `target_column` in susa_to_model.py config must be set per model.

14. **Sign convention is Soll=negative, Haben=positive** -- this is the SKR03 standard used by all models. susa_to_model.py handles this. If manually entering values, verify the S/H flag from the SUSA source.

15. **Account numbers in column B are the primary key** -- susa_to_model.py matches SUSA accounts to model rows via column B. If an account exists in SUSA but not in the model, it is skipped (logged as "not-in-model"). New accounts require manual row insertion by Roman.

---

## 9. Anti-Patterns

These anti-patterns are derived from actual incidents. They MUST be included verbatim in any agent prompt that touches financial models.

### EXCEL-FROM-SCRATCH
**Never generate a financial model from scratch.** The model contains hundreds of formulas, cross-sheet references, conditional formatting, named ranges, and print areas that cannot be reproduced programmatically. Always start from an existing golden template or the deal's current model version.

### OPENPYXL-CORRUPTION
**openpyxl destroys formatting on write.** Even `Workbook.save()` after only reading + modifying data cells will strip conditional formatting, corrupt chart objects, break named ranges, and scramble merged cells. Use openpyxl ONLY for reading (`read_only=True, data_only=True`). All writes go through Excel COM via PowerShell.
Source: 2026-05-14 GOLMED v11 session -- openpyxl write corrupted the model.

### INVENTED-FORMAT-INSTEAD-OF-COPY
**Never invent a model format.** The model layout (row positions, column arrangement, section structure) has been refined through 14+ iterations across 4 deals. Use the existing model as the template. If a new deal needs a model, copy the closest golden file and modify data only.

### FORMULA-OVERWRITE
**Never overwrite a formula cell with a hardcoded value.** This silently breaks the dependency chain. The next time Roman updates upstream data, the formula-driven values will recalculate but the hardcoded cell will not, creating silent data inconsistency.

### WRONG-UNIT-SCALE
**GuV-Konten stores EUR, GuV stores K EUR, Bilanz net debt section stores EUR.** Mixing scales is the most common manual error. When reading from SUSA (EUR) and writing to GuV-Konten (EUR), no conversion needed. The /1000 transformation happens in GuV formulas.

---

## 10. Confidence Assessment

### Per-Sheet Confidence

| Sheet | Read confidence | Write confidence | Notes |
|---|---|---|---|
| GuV-Konten | HIGH | HIGH (via susa_to_model.py) | Well-understood structure, validated tool |
| GuV | HIGH | NONE (formula-only) | Never write; read for analysis |
| Bewertung | HIGH | LOW (Roman manual-input cells only: I6/J6, multiples, L10-L19) | Automation never writes; Roman sets valuation parameters directly |
| Bilanz | MEDIUM | LOW (manual only) | Category structure consistent, but account-level detail varies per deal |
| Cover | LOW | NONE | Branding only, no data |
| Vergleich | MEDIUM | LOW | Deal-specific negotiation history, format varies |
| Entity sheets | MEDIUM | NONE | Raw SUSA imports, reference only |

### Per-Operation Confidence

| Operation | Confidence | Validated by |
|---|---|---|
| Read SUSA, write to GuV-Konten | HIGH | susa_to_model.py, validated on 4 deals (AQUA, FOX, LION, CAT) |
| Read model for deal analysis | HIGH | openpyxl read-only mode, used in every deal session |
| Update year column headers | HIGH | susa_to_model.py header_updates feature |
| Add new account rows | LOW | Requires manual insertion; formula ranges may need updating |
| Modify adjustment logic | LOW | Deal-specific, requires Roman's commercial judgment |
| Create model for new deal | MEDIUM | Copy golden template + run susa_to_model.py; manual adjustments still needed |

---

## 11. Template-Fill Workflow

### New Deal Model Setup

1. **Copy template:** Copy the closest golden model (single-entity: LION; multi-entity: CAT) to the deal's `2_Model/` subfolder
2. **Rename:** Follow convention `YYMMDD_{DealName}_v1.xlsx`
3. **Clear data:** Roman manually clears old deal data from GuV-Konten (preserving structure and formulas)
4. **Prepare SUSA:** Obtain SUSA exports from Steuerberater (xlsx or convert to JSON)
5. **Configure susa_to_model.py:** Create JSON config specifying deal_folder, model_filename, guv_sheet_name, sources with target columns
6. **Run susa_to_model.py:** Generates PS1 script
7. **Execute PS1:** Run the PowerShell script to populate GuV-Konten
8. **Verify:** Check error flag (row 2), spot-check key accounts, verify GuV totals match SUSA totals
9. **Manual adjustments:** Roman adds deal-specific adjustments in GuV rows 30+
10. **Bilanz:** Roman enters balance sheet data manually
11. **Valuation:** Roman sets EBITDA targets and multiples in Bewertung
12. **REVIEW GATE:** Present model to Roman with: error flag status, spot-check results (revenue, EBITDA, net debt),
    and any skipped accounts. Roman confirms model is ready for valuation work. BLOCK: do not use model outputs
    (Bewertung figures) in downstream specs (Offer, LOI, Onepager) until Roman approves.

### Updating Existing Model with New Period Data

1. **Read current model:** Use openpyxl read-only to understand current column layout
2. **Determine target column:** Read row 3 headers, identify which column to populate
3. **Prepare SUSA:** Obtain new period SUSA data
4. **Configure and run susa_to_model.py:** Set target_column to the appropriate year column
5. **Verify:** Error flag, spot-checks, cross-check totals
6. **Update headers:** If adding new period columns (e.g., current trading), update header labels

### Cross-Check Protocol

After any automated write:
1. Error flag on row 2 of GuV-Konten: must show "No Errors" (or transition from error to no-error)
2. Spot-check accounts 8400 (Umsatz), 3400 (Wareneinkauf), 4120 (Gehaelter), 3960 (Skonti)
3. Compare total Gesamtleistung in GuV row 7 against sum of SUSA revenue accounts
4. Skipped accounts list from susa_to_model.py output -- verify none are material

---

## 12. Dependencies

| Dependency | Path | Role |
|---|---|---|
| susa_to_model.py | `CLAUDE_REPURO/dealroom/tools/susa_to_model.py` | Core automation tool |
| Golden templates | `config/golden/model/` | 4 reference models |
| Deal models | `CLAUDE_REPURO/3_Deals/3_Targets/{deal}/2_Model/` | Live deal files |
| SUSA exports | Deal folder or Steuerberater delivery | Raw accounting data input |
| Excel COM | Local Windows install of Microsoft Excel | Required for all writes |
| PowerShell | Windows PowerShell 5.1+ | Script execution environment |
| openpyxl | Python package | Read-only model analysis |

### Related Specs

| Spec | Relevance |
|---|---|
| SPEC-RFI | RFI questions drive which financial data is requested (Category 4: Finanzen) |
| SPEC-LOI | LOI references valuation figures from Bewertung |
| SPEC-NDA | Precedes model work; no direct data dependency |
| DEAL_DELIVERABLES_SPEC | Stage 2 sub-step: "Build/update financial model" |
| deal-information-map.md | Maps where to find SUSA, JA, BWA in deal folders |
