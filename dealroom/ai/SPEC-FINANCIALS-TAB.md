# SPEC: Financials Tab Redesign (DR-M9b)

Redesigns the Financials > GuV subtab to match the golden P&L format from the Excel model. Replaces the current `renderUnifiedGuV()` with a compact, structured P&L view with collapsible adjustment bridge, 3-layer drill-down, current trading columns, and CAGR.

**Golden reference**: Screenshot of Cat model P&L (`260505_MundS_v7.xlsx`, Bewertung sheet).

**Upstream**: DR-M3 (extraction), DR-M5 (model reader), DR-SV2 (deal_financials schema).

---

## 1. Column Layout

```
P&L in €K | 2021A | 2022A | 2023A | 2024A | 2025A | [space] | 2026B | [space] | CT | [space] | CAGR 23-25 | Delta CT | [space] | Comment
```

### Year columns (actuals + budget)
- **Source**: `deal_financials WHERE statement='pnl' AND period_type='annual'`
- **Suffix logic**:
  - Years ≤ 2025 → suffix `A` (actual)
  - Years ≥ 2026 → suffix `B` (budget)
  - No `P` suffix exists.
  - The backend returns `years` as a list — the frontend applies the suffix purely based on year value vs. 2025 threshold.
  - Show last 5 actual years + 1 projection year (2026B). If fewer years exist, show all.

### 2026B column
- **2026B is a computed projection column** driven by 3 assumption inputs:
  - **Topline growth %** — applied to last actual year's Total Sales to compute projected Total Sales
  - **Gross Margin %** — applied to projected Total Sales to derive COGS (COGS = Total Sales × (1 - GM%))
  - **EBITDA margin %** — applied to projected Total Sales to derive EBITDA
- **Storage**: These assumptions are stored in the `deals` table as new columns: `proj_topline_growth_pct`, `proj_gm_pct`, `proj_ebitda_margin_pct`. Editable inline in the Comment column area or a small assumptions row above the table.
- **Other line items**: Only Revenue (Total Sales), COGS (from GM%), and EBITDA are populated in 2026B. All other line items (Personnel, OPEX, D&A, EBIT, EBT, Net Income, etc.) show `—` in the 2026B column.
- **Override columns**: `deals.bp_2026_rev_k` and `deals.bp_2026_ebitda_k` remain as override columns. If populated, they take precedence over computed values.
- Separated from actuals by a visual spacer column (thin vertical line or gap).

### CT (Current Trading) column
- **Source**: `deal_financials WHERE period_type IN ('bwa_ytd', 'bwa_ytd_m31')` — the most recent BWA data.
- **Header format**: `MM/YY` — e.g., `03/25`, `09/25`, `04/26`.
- **Derivation**: The backend parses the source filename to extract the month:
  - `"BWA September 25 KVG.xlsx"` → `09/25`
  - `"Kurzfristige Erfolgsrechnung 12.2025 lang.xlsx"` → `12/25`
  - `"BWA Q1 2025.xlsx"` → `03/25` (last month of quarter)
- If month cannot be parsed from the filename, fall back to `CT` as header.
- **Current state**: CT data currently only exists for Wolf. Other deals will show an empty CT column until BWA data is ingested.
- Separated by spacer from 2026B.

### CAGR column
- **Header**: `CAGR 23-25` (dynamically: second-to-last actual year through last actual year, using 3-year window).
- **Formula**: `(value_last / value_first) ^ (1 / n_years) - 1` where `n_years = last_year - first_year`.
- **Applies to**: Revenue, COGS, Personnel, OPEX, EBITDA, EBIT, Net Income. Other rows show `—`.
- **Missing data**: If a line item is missing in the first or last year, or the value is zero/negative making the formula undefined, show `NaN`.
- Separated by spacer from CT.

### Delta CT column
- **Header**: `Δ CT`
- **Shows**: YoY growth of the CT value vs. same period prior year, if available. Uses the same `MM/YY` period reference as the CT column header.
- **Formula**: `(ct_value - ct_prior) / |ct_prior| * 100`, displayed as `+12.3%` or `(5.1%)`.
- If prior period data unavailable → `—`.

### Comment column
- **Editable** (contenteditable in serve mode).
- **Source**: New field `deal_financials.adjustment_note` for adjustment rows; `deals.pnl_row_comments` JSON field mapping `(line_item) → comment`.
- **Format**: JSON in `deals.pnl_row_comments` — `{"revenue": "120k Umsatz von ...", "cogs_adj": "50% Annahme..."}`. Editable inline, saved via existing `/api/update` endpoint.

---

## 2. P&L Section — Row Structure

The main P&L section shows adjusted values (if model exists) with the following rows:

| Row | `line_item` key | Display Label | Style | Sign |
|-----|----------------|---------------|-------|------|
| Total Sales | `revenue` / `gesamtleistung` | Total Sales | normal | +1 |
| Cost of sales (adj.) | `cogs_adj` / `cogs` | Cost of Sales (adj.) | normal | -1 |
| **Gross margin** | *computed* | **Gross Margin** | **bold** | computed |
| Personnel (adj.) | `personnel_adj` / `personnel` | Personnel (adj.) | normal | -1 |
| OPEX (adj.) | `other_opex_adj - other_income_adj` | OPEX (adj.) | normal | -1 |
| **EBITDA (adj.)** | `ebitda_adj` / `ebitda` | **EBITDA (adj.)** | **bold, teal** | +1 |
| D&A (adj.) | `da_adj` / `da` | D&A (adj.) | normal | -1 |
| **EBIT (adj.)** | `ebit_adj` / `ebit` | **EBIT (adj.)** | **bold, teal highlight** | +1 |
| Zinsaufwand | `interest_expense` | Zinsaufwand | normal | -1 |
| Zinserträge | `interest_income` | Zinserträge | normal | +1 |
| **EBT (adj.)** | `ebt_adj` / `ebt` | **EBT (adj.)** | **bold** | +1 |
| Steuern | `tax` | Steuern | normal | -1 |
| **Jahresüberschuss** | `net_income_adj` / `net_income` | **Jahresüberschuss (adj.)** | **bold** | +1 |
| *(spacer)* | | | | |
| Topline growth | *computed* | *Topline growth* | italic, muted | % |
| Gross margin % | *computed: Gross Margin / Total Sales × 100* | *Gross margin* | italic, muted | % |
| PEX % | *computed: Personnel (adj.) / Total Sales × 100* | *PEX %* | italic, muted | % |
| OPEX % | *computed: OPEX (adj.) / Total Sales × 100* | *OPEX %* | italic, muted | % |
| EBITDA margin | *computed: EBITDA (adj.) / Total Sales × 100* | *EBITDA margin* | italic, muted | % |
| EBIT margin | *computed: EBIT (adj.) / Total Sales × 100* | *EBIT margin* | italic, muted | % |

### OPEX includes OPIN
- OPEX (adj.) = `other_opex_adj - other_income_adj` (net OPEX). Other income is netted into OPEX rather than shown as a separate row.
- Display label stays "OPEX (adj.)".
- In the adjustment bridge (Section 3), the OPIN netting is shown as a sub-row for transparency.

### KPI percentages — denominator is always Total Sales
All KPI percentage rows use Total Sales (`gesamtleistung`) as the denominator, never revenue. This is consistent with the golden template and ensures ratios are comparable across deals with different revenue composition (inventory changes, activated own work, etc.).

### "Total Sales" folding
- The golden template shows Revenue, Inventory change, Activated own as sub-rows that sum to Total Sales.
- **In DB**: `gesamtleistung` IS Total Sales. `revenue` is the sub-component.
- **Display**: Show only "Total Sales" using `gesamtleistung` value (preferred) or `revenue` as fallback.
- No expandable sub-rows for Revenue/Inventory/Activated — these are folded into Total Sales.

### Gross margin (computed)
- `gross_margin = total_sales + cogs` (COGS stored as negative).
- Not a DB row — computed client-side from `gesamtleistung` and `cogs_adj` values.

### Value display
- All values in K€, German number format (dot thousands, no decimals): `1.168`, `(1.037)`.
- Negative values in parentheses: `(571)` not `-571`.
- This matches the golden template format.

### Consistency with onepager Q2
- The onepager `renderQ2Chart` uses `gesamtleistung` for revenue and `ebitda_adj` for EBITDA — same DB values as this table.
- **Critical**: `gesamtleistung` = Total Sales = the top-line number. Both views must reference the same `line_item`.

---

## 3. Adjustment Section — Collapsible Bridge

Below the main P&L, a collapsible section: **"Adjustments in €K"** (collapsed by default, click to expand).

### Structure
For each adjustable line item (COGS, Personnel, OPEX, D&A):

```
Umsatz                    [raw values per year]
  + adjustment row 1      [values, yellow highlight]     Comment
  + adjustment row 2      [values, yellow highlight]     Comment
Umsatz (adj.)             [adjusted values per year, bold]
```

### OPEX bridge — includes OPIN netting
The OPEX adjustment bridge has 3 sub-rows to show the OPIN merge transparently:

```
Other OPEX (raw)          [raw other_opex values per year]
Other Income (raw)        [raw other_income values, shown with sign]
  Net adjustment delta    [adjustment amount, yellow highlight]
OPEX (adj.)               [adjusted net OPEX total, bold]
```

### Data source
- **Raw value**: `deal_financials WHERE line_item=X AND is_adjusted=0`
- **Adjusted value**: `deal_financials WHERE line_item=X_adj AND is_adjusted=1`
- **Adjustment delta**: `adjusted - raw` (per year)
- **Individual adjustment rows**: Currently NOT stored as separate rows in `deal_financials`. The golden template shows named adjustments (e.g., "Aktuelles Gehalt GF", "Adj. Gehalt (neu)") but these live in the Excel model only.

### Implementation approach
**Option A (recommended — ship now)**: Show 2-row bridge only:
1. Reported (raw) value
2. Adjustment = adjusted - raw (single delta row, yellow highlight)
3. Adjusted total (bold)

For OPEX, bridge may have 3 sub-rows (raw other_opex, raw other_income, net adjustment) to make the OPIN netting visible.

This matches current `_build_unified_financials` output which already provides `raw` and `adjusted` per cell.

**Option B (future — requires model reader enhancement)**: Extract individual named adjustment rows from model. Requires `model.py` to parse the adjustment section of the Excel template and store each adjustment as a separate `deal_financials` row with `statement='adjustments'`. Deferred — implement when model reader is enhanced (DR-M5b).

### Adjustment row comments
- The `adjustment_note` column in `deal_financials` already exists.
- For Option A: show `adjustment_note` from the adjusted row in the Comment column.
- For Option B: each adjustment row carries its own note.

---

## 4. Click-to-Expand: 3-Layer Drill-Down

When the user clicks on a P&L row (e.g., OPEX), the table expands to show detail layers:

### Layer 1: Main P&L row (always visible)
`OPEX (adj.)` → `(263,3)` | `(304,6)` | ...

### Layer 2: Subaccount groups (click to expand)
These are the intermediate groupings from the GuV structure (e.g., Raumkosten, Fahrzeugkosten, Sonstiger Neutraler Aufwand).

**Data source**: `deal_financials WHERE konto_nr IS NOT NULL` — the `konto_nr` field stores the DATEV account number.

**Konto grouping**: Konto grouping is handled by the ingestion/extraction scripts (BWA, SUSA parsers). The scripts assign a `konto_group` label based on the source document's own grouping structure. The P&L drill-down reads whatever grouping the ingestion scripts populated — no hardcoded konto range mapping in the dashboard.

**Current state**: Subaccount infrastructure exists in `dashboard.py` (`_build_unified_financials` collects subaccounts) and `dashboard.html` (`renderUnifiedGuV` renders them). CAT already has 43 `konto_nr`-populated rows from "Kurzfristige Erfolgsrechnung" extraction. These use SKR04 (not SKR03). Wolf has BWA data but without konto_nr detail yet.

### Layer 3: Individual accounts (click subaccount group to expand)
Individual DATEV accounts within a group (e.g., under Fahrzeugkosten: 4510 KFZ-Steuer, 4530 Laufende KFZ-Kosten).

**Data source**: Same `deal_financials` rows with `konto_nr` — Layer 2 groups them, Layer 3 shows individuals.

### Implementation
- **Layer 1**: Already works (current `renderUnifiedGuV`).
- **Layer 2 + 3**: Infrastructure exists; CAT has konto_nr data to test against. The drill-down UI should be built now (click handlers, indentation, expand/collapse icons). Deals without konto_nr data show "No detail available".
- Use CSS classes for indentation: Layer 2 = `padding-left: 24px`, Layer 3 = `padding-left: 48px`.
- Expand/collapse with `▸`/`▾` chevron icons.

---

## 5. Entity Dimension (Multi-Company Consolidation)

### Problem
Some deals consist of multiple legal entities whose financials need consolidation. CAT has 2 entities (from 2024 onward):
- **M&S** (Medizin & Service GmbH) — main entity, ~5.8M revenue
- **LIKE** (subsidiary) — ~328K revenue

Currently all entities' data lands in the same `domain` without distinction, causing duplicate/conflicting rows. Entity is derived from source filename prefix (e.g., `M&S_*.xlsx` → `M&S`, `LIKE_*.xlsx` → `LIKE`).

### Schema change
```sql
ALTER TABLE deal_financials ADD COLUMN entity TEXT DEFAULT 'consolidated';
```

### Ingestion rules
- Extraction scripts derive entity name from source filename (e.g., `M&S_*.xlsx` → entity `M&S`, `LIKE_*.xlsx` → entity `LIKE`).
- After writing entity-level rows, scripts compute `consolidated` rows by summing across entities per `(statement, line_item, fiscal_year, period_type, is_adjusted)`.
- Consolidation is a straight sum — no intercompany eliminations (distribution companies don't have interco revenue).
- Consolidated rows do NOT include konto_nr-level detail — subaccount drill-down is only available at entity level, not consolidated level.
- `entity='consolidated'` is the default and what the main P&L view shows.

### Backend
- `_build_unified_financials()` gets an `entity` filter parameter, defaulting to `consolidated`.
- Returns list of available entities for the deal alongside P&L data: `entities: ['consolidated', 'M&S', 'LIKE']`. Subaccount drill-down data only returned for entity-level views, not consolidated.

### Frontend
- Small dropdown/toggle above the P&L table: `[Consolidated ▾]` with entity options.
- Switching entity re-renders the same P&L structure with that entity's data.
- Default view = consolidated.

### Single-entity deals
- Deals with only one company have all rows with `entity='consolidated'` (the default).
- No dropdown shown when only one entity exists.

---

## 6. Layout Constraints

### Width
- **Do NOT stretch full width**. The table should be compact — use `width: auto` or `max-width: fit-content`.
- Year columns: `min-width: 75px`, right-aligned.
- Label column: `min-width: 200px`, left-aligned.
- Comment column: `min-width: 150px`, `max-width: 250px`, left-aligned, truncate with ellipsis.
- Spacer columns: `width: 8px`, no border.

### Typography
- Match golden template: Arial/sans-serif, 12-13px for data, 11px for headers.
- Bold rows: 700 weight.
- KPI rows: italic, muted color (#888).
- EBITDA/EBIT: teal color (#1D7080).
- EBIT row: teal background highlight (matching golden template).

### Number format
- All values in K€ (already the DB unit).
- German locale: dot as thousands separator, no decimals.
- Negatives in parentheses: `(1.037)`.
- Percentages: one decimal, e.g., `13.6%`, `(25.3%)`.

---

## 7. DB Changes

### New columns on `deals`
```sql
ALTER TABLE deals ADD COLUMN proj_topline_growth_pct REAL;
ALTER TABLE deals ADD COLUMN proj_gm_pct REAL;
ALTER TABLE deals ADD COLUMN proj_ebitda_margin_pct REAL;
ALTER TABLE deals ADD COLUMN pnl_row_comments TEXT;  -- JSON: {"line_item": "comment text"}
```

### New column on `deal_financials`
```sql
ALTER TABLE deal_financials ADD COLUMN entity TEXT DEFAULT 'consolidated';
```

### Existing columns (no changes needed)
- `deal_financials.adjustment_note` — already exists.
- `deal_financials.konto_nr` — already exists.
- `period_type` values `bwa_ytd` / `bwa_ytd_m31` — already stored.
- `deals.bp_2026_rev_k` / `deals.bp_2026_ebitda_k` — already exist, used as override columns.

### Backend function changes (`dashboard.py`)
1. **`_build_unified_financials()`**: Add `entity` filter parameter (default `consolidated`). Return available entities list alongside P&L data.
2. **CT data**: Query `WHERE period_type IN ('bwa_ytd', 'bwa_ytd_m31')`. Parse source filename to extract month for `MM/YY` header.
3. **2026B data**: Compute projection from `proj_topline_growth_pct`, `proj_gm_pct`, `proj_ebitda_margin_pct` applied to last actual year. Fall back to `deals.bp_2026_rev_k` / `deals.bp_2026_ebitda_k` if those override columns are populated.
4. **CAGR**: Compute server-side for each line item across the 3-year window. Return as `cagr: {line_item: pct}`. Return `NaN` for missing/invalid data.
5. **OPEX netting**: Compute `other_opex_adj - other_income_adj` as the OPEX (adj.) value.
6. **Comments**: Read/write `deals.pnl_row_comments` JSON field.
7. **Subaccount grouping**: Read konto_group labels from ingestion-populated data. Return as `subaccount_groups: {parent_key: {group_label: {year: value}}}`.

### Frontend changes (`dashboard.html`)
1. Replace `renderUnifiedGuV()` entirely.
2. New column layout with spacers, CT (MM/YY header), CAGR, Delta CT, Comment.
3. Year suffix logic (A/B based on ≤2025 / ≥2026).
4. 2026B column rendering from computed projections + assumption inputs.
5. Entity dropdown (hidden for single-entity deals).
6. Collapsible adjustment section with OPEX bridge showing OPIN netting.
7. 3-layer expand/collapse on P&L rows.
8. Comment inline editing + save via `/api/update`.

---

## 8. Files to Modify

| File | Changes |
|---|---|
| `src/dashboard.py` | `_build_unified_financials()` — add entity filter, CT query with filename month parsing, CAGR computation, 2026B projection, OPEX netting, comment field, subaccount grouping |
| `src/dashboard.py` | `/api/update` handler — support `pnl_row_comments` and projection assumption saves |
| `src/templates/dashboard.html` | Replace `renderUnifiedGuV()` — new column layout, entity dropdown, adjustment section, 3-layer drill-down, CT/CAGR/Delta columns, 2026B projection display |
| `src/db.py` | `_migrate_schema_v2()` — add `proj_topline_growth_pct REAL`, `proj_gm_pct REAL`, `proj_ebitda_margin_pct REAL`, `pnl_row_comments TEXT` to deals; add `entity TEXT DEFAULT 'consolidated'` to deal_financials |
| Extraction scripts | Add entity-awareness: derive entity name from source filename, compute consolidated rows after entity-level ingestion |

---

## 9. What This Does NOT Change

- **Onepager Q2 chart**: Unchanged — still uses `gesamtleistung` for revenue, `ebitda_adj` for EBITDA from `_build_onepager_chart_data()`. Same DB values, different view.
- **Bewertung subtab**: Unchanged.
- **Bilanz subtab**: Unchanged.
- **Model & Valuation tab** (`renderAdjGuV`): Unchanged — that's the valuation model view, separate from this operational P&L.
- **Portfolio table**: Unchanged.

**Note**: The extraction pipeline DOES need changes for the entity dimension (Section 5). Extraction scripts must be updated to parse entity names from filenames and produce consolidated rows.

---

## 10. Implementation Order

1. **DB migration**: Add new columns to `deals` (projection assumptions, pnl_row_comments) and `deal_financials` (entity). Run migration first — all subsequent work depends on schema.
2. **Entity ingestion**: Update extraction scripts with entity-awareness. Re-ingest CAT data to populate entity-level + consolidated rows.
3. **Backend P&L**: Rebuild `_build_unified_financials()` with entity filter, OPEX netting, CT month parsing, CAGR computation, 2026B projection logic.
4. **Frontend P&L**: Rebuild `renderUnifiedGuV()` with new column layout, year suffixes (A/B), computed rows (Gross Margin, KPIs with Total Sales denominator), entity dropdown.
5. **2026B projection**: Wire up assumption inputs (topline growth, GM%, EBITDA margin%) with inline editing and computed column rendering.
6. **Adjustment section**: Collapsible bridge below P&L, including OPEX bridge with OPIN netting sub-rows.
7. **3-layer drill-down**: Expand/collapse handlers for subaccount groups + individual accounts. Test against CAT's existing konto_nr data.
8. **Comment column**: Inline editing + save.
9. **CT + CAGR + Delta**: Wire up the new columns with data from backend.

---

## 11. Acceptance Criteria

- [ ] P&L table shows columns: years (with A/B suffix, no P suffix) | spacer | 2026B | spacer | CT (MM/YY header) | spacer | CAGR 23-25 | Delta CT | spacer | Comment
- [ ] "Total Sales" shown instead of separate Revenue/Inventory/Activated rows
- [ ] Gross Margin row computed and displayed between COGS and Personnel
- [ ] OPIN merged into OPEX — no separate OPIN row; OPEX (adj.) = other_opex_adj - other_income_adj
- [ ] All KPI percentage rows use Total Sales (gesamtleistung) as denominator
- [ ] 2026B column shows projected values computed from 3 assumption inputs (topline growth %, GM%, EBITDA margin%)
- [ ] 2026B shows only Revenue, COGS (from GM%), and EBITDA; all other line items show `—`
- [ ] 2026B override columns (bp_2026_rev_k, bp_2026_ebitda_k) take precedence when populated
- [ ] CT column header shows MM/YY format parsed from source filename (falls back to "CT")
- [ ] CAGR shows NaN for missing/invalid data (zero, negative, or absent values)
- [ ] Entity toggle works for CAT (shows M&S, LIKE, consolidated); hidden for single-entity deals
- [ ] Adjustment section collapsed by default, expandable; OPEX bridge shows OPIN netting
- [ ] Click on P&L row expands subaccount groups (Layer 2), click group expands accounts (Layer 3) — drill-down only available at entity level, not consolidated
- [ ] Table is compact (not full-width stretched)
- [ ] Numbers in K€, German format, negatives in parentheses
- [ ] EBITDA/EBIT values match onepager Q2 chart values exactly (same DB source)
- [ ] Comment column editable and persisted
- [ ] Server restart shows all data correctly for Cat (medizinservice-sachsen.de)
