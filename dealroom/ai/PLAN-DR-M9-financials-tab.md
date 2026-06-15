# DR-M9 — Financials Tab Restructure

## Problem

The Financials section is split across two separate sidebar tabs with inconsistent data views:

1. **"Financials" tab** (`renderInformation()` → `renderGuV(pnl)`) — shows raw DATEV P&L only (is_adjusted=0). 15-line structure. Source drill-down per row. No model data.
2. **"Model" tab** (`renderModel()` → `renderAdjGuV()`) — shows adjusted P&L from model (is_adjusted=1). 9-line summary + KPIs + adjustment detail + GF salary panel. No raw data context.

This split makes no sense to Roman: the model IS the financial picture. Raw DATEV data is an input layer, not a separate view. An investor looking at the dashboard sees "Financials" with stale raw numbers and has to know to click "Model" for the real picture.

## Target State

**One "Financials" sidebar tab** that mirrors the Excel model's GuV structure:

1. **Adjusted P&L summary** (top) — the model view, always the primary layer
2. **Adjustment bridge** (below) — raw → adjustments → adjusted, per line item
3. **Subaccount drill-down** (click-to-expand) — konto_nr level detail from SUSA/DATEV
4. **Bilanz subtab** — balance sheet (unchanged)
5. **Bewertung subtab** — valuation summary (moved from Model tab)

The "Model" sidebar item is removed. All financial content lives under "Financials".

## Data Architecture

### deal_financials table — 4-layer authority hierarchy (SPEC-DR-READER §5.1)

| Layer | is_adjusted | konto_nr | Source |
|-------|-------------|----------|--------|
| Model adjusted | 1 | NULL | Excel model GuV sheet |
| Raw aggregate | 0 | NULL | DATEV GuV xlsx (aggregate lines) |
| Subaccount | 0 | 4-digit code | DATEV GuV xlsx (account-level rows) |
| Bewertung | 1 (statement='bewertung') | NULL | Excel model Bewertung sheet |

Current data availability:
- Cat: 43 konto_nr rows, both raw and adjusted P&L
- Fox/Lion/Mantis: 0 konto_nr rows, have raw and adjusted P&L
- When no adjusted data exists, fall back to raw as primary display

### Backend data shape (new unified structure)

Replace the current split (`financials.pnl` + `model.pnl_adj` + `model.ebitda_bridge`) with a single `financials` dict:

```python
"financials": {
    "unified_pnl": {
        # Keyed by fiscal_year (str)
        "2022": {
            "revenue": {"adjusted": 6000.0, "raw": 5823.0, "source_adj": "Model v6", "source_raw": "GuV 2022.xlsx"},
            "cogs_adj": {"adjusted": -2100.0, "raw": -2050.0, ...},
            "personnel_adj": {"adjusted": -1800.0, "raw": -1750.0, ...},
            "other_opex_adj": {"adjusted": -300.0, "raw": -280.0, ...},
            "other_income_adj": {"adjusted": 50.0, "raw": 45.0, ...},
            "ebitda_adj": {"adjusted": 1850.0, "raw": 1788.0, ...},
            "da_adj": {"adjusted": -200.0, "raw": -200.0, ...},
            "ebit_adj": {"adjusted": 1650.0, "raw": 1588.0, ...},
            "interest_income": {"adjusted": 5.0, "raw": 5.0, ...},
            "interest_expense": {"adjusted": -30.0, "raw": -30.0, ...},
            "ebt_adj": {"adjusted": 1625.0, "raw": 1563.0, ...},
            "tax": {"adjusted": -400.0, "raw": -380.0, ...},
            "net_income_adj": {"adjusted": 1225.0, "raw": 1183.0, ...}
        },
        ...
    },
    "subaccounts": {
        # Keyed by parent line_item, then fiscal_year, then list of {konto_nr, label, value_k}
        "revenue": {
            "2022": [
                {"konto_nr": "8000", "value_k": 3200.0, "source": "GuV 2022.xlsx"},
                {"konto_nr": "8100", "value_k": 2623.0, "source": "GuV 2022.xlsx"}
            ]
        },
        ...
    },
    "years": ["2020", "2021", "2022", "2023", "2024"],
    "has_adjusted": true,  # controls whether bridge column shows
    "balance": { ... },  # unchanged from current
    "risk_flags": [ ... ],  # unchanged
    "bewertung": { ... },  # moved from model dict
    "ebitda_bridge": { ... }  # kept for one-pager compatibility
}
```

### Frontend rendering

**Subtabs within Financials:**
- **GuV** (default, active) — unified P&L view
- **Bilanz** — balance sheet (existing `renderBilanz`, unchanged)
- **Bewertung** — valuation (moved from Model tab)

**GuV subtab structure:**

```
┌─────────────────────────────────────────────────────────┐
│ P&L in €K              2020   2021   2022   2023   2024 │
├─────────────────────────────────────────────────────────┤
│ Revenue (adj.)         5200   5500   6000   6300   6800 │  ← click expands:
│   ├ Raw (reported)     5100   5400   5823   6100   6500 │     adjustment bridge
│   ├ Adjustment          100    100    177    200    300 │
│   └ Subaccounts:                                        │     konto_nr drill-down
│     8000 Umsatzerlöse  3000   3200   3200   3400   3600 │
│     8100 Erlöse Ware   2100   2200   2623   2700   2900 │
│─────────────────────────────────────────────────────────│
│ COGS (adj.)           -2000  -2050  -2100  -2200  -2400 │
│ Personnel (adj.)      -1600  -1700  -1800  -1900  -2000 │
│ Other OPEX (adj.)      -250   -270   -300   -280   -310 │
│ Other Income (adj.)      40     45     50     55     60 │
│─────────────────────────────────────────────────────────│
│ EBITDA (adj.)          1390   1525   1850   1975   2150 │  ← bold, teal
│ EBITDA margin           ...    ...    ...    ...    ... │  ← italic, muted
│─────────────────────────────────────────────────────────│
│ D&A                    -180   -190   -200   -210   -220 │
│ EBIT (adj.)            1210   1335   1650   1765   1930 │  ← bold, teal
│ Interest income           4      5      5      6      7 │
│ Interest expense        -25    -28    -30    -32    -35 │
│ EBT (adj.)             1189   1312   1625   1739   1902 │
│ Tax                    -300   -330   -400   -435   -475 │
│─────────────────────────────────────────────────────────│
│ Net Income (adj.)       889    982   1225   1304   1427 │  ← bold
└─────────────────────────────────────────────────────────┘

KPI rows (italic, muted — same as current renderAdjGuV):
  Topline growth, Gross margin %, PEX %, OPEX %, EBITDA margin, EBIT margin

GF Salary panel (if model_context has params) — same as current

Adjustment detail table (if model_context has adjustments_detail) — same as current
```

**Fallback when no adjusted data exists:**
- Show raw P&L as primary (current `renderGuV` behavior)
- No bridge column, no "adj." labels
- Badge: "Raw data only — no model extracted"

**Click-to-expand behavior:**
- Click any P&L row → shows 2 detail sections:
  1. **Bridge**: "Reported: X | Adjustment: Y | Adjusted: Z" (only if has_adjusted=true)
  2. **Subaccounts**: konto_nr rows underneath (only if subaccount data exists for that line_item)
- Same expand/collapse pattern as current `renderGuV` source drill-down

## Implementation Scope

### Backend changes (dashboard.py)

1. **New function `_build_unified_financials(conn, domain)`** — replaces the current split queries for pnl (lines 266-293) and model_pnl (lines 353-369):
   - Query all `deal_financials WHERE statement='pnl' AND period_type='annual'`
   - Group by fiscal_year, partition by is_adjusted and konto_nr presence
   - Build the unified_pnl dict with adjusted/raw pairs per line_item per year
   - Build the subaccounts dict from konto_nr rows
   - Map raw line_items to adjusted line_items (revenue→revenue, cogs→cogs_adj, personnel→personnel_adj, etc.)

2. **Move bewertung query into financials dict** — currently at lines 370-378, move into the new function

3. **Update `build_deal_data()` return dict** — replace `financials.pnl` + `model.pnl_adj` + `model.ebitda_bridge` + `model.bewertung` with the new unified structure. Keep `model_context` for the interactive model (GF salary, adjustments detail, net debt).

4. **Keep backward compatibility for one-pager** — `_build_onepager_chart_data()` reads from `deal_financials` directly, doesn't depend on the `financials` dict. No changes needed there.

### Frontend changes (dashboard.html)

1. **Remove "Model" sidebar tab** — delete `sidebarItem('model', ...)` from `renderSidebar()` (line 918) and `case 'model'` from `showSection()` (line 954)

2. **Rewrite `renderInformation()`** — new subtabs: GuV (default), Bilanz, Bewertung

3. **New `renderUnifiedGuV()`** — replaces both `renderGuV()` and `renderAdjGuV()`:
   - Reads `DATA.financials.unified_pnl`
   - Primary display: adjusted values (or raw fallback)
   - Click-to-expand: bridge row + subaccount rows
   - KPI rows below (same as current `renderAdjGuV` KPIs)
   - Source badge on hover (tooltip)

4. **Move Bewertung rendering** — `renderBewertungTab()` stays as-is, just called from the new Financials subtab structure instead of Model subtab

5. **Keep `renderModel()` functions** — `renderAdjGuV()`, `renderNetDebt()`, GF salary panel, adjustment detail — these stay alive because the interactive model (live recalculation via `/api/model-params`) still needs them. But they're accessed via the Bewertung subtab or kept internal to the model_context flow. The PRIMARY financial view is the unified one.

6. **Keep one-pager Q2 drill-down link** — line 640: `showSection('financials')` already points to the right tab

### Line-item mapping (raw → adjusted)

| Raw line_item | Adjusted line_item | Display label |
|---|---|---|
| revenue | revenue | Revenue |
| gesamtleistung | revenue | Revenue (Gesamtleistung) |
| cogs | cogs_adj | COGS |
| personnel | personnel_adj | Personnel |
| other_opex | other_opex_adj | Other OPEX |
| other_income | other_income_adj | Other Income |
| ebitda | ebitda_adj | EBITDA |
| da | da_adj | D&A |
| ebit | ebit_adj | EBIT |
| interest_income | interest_income | Interest Income |
| interest_expense | interest_expense | Interest Expense |
| ebt | ebt_adj | EBT |
| tax | tax | Tax |
| net_income | net_income_adj | Net Income |

### Subaccount → parent mapping

konto_nr ranges (DATEV SKR03):
- 8000-8999 → revenue
- 3000-3999 → cogs
- 4000-4999 → personnel (4xxx with Lohn/Gehalt) OR other_opex (4xxx with Miete/Versicherung etc.)
- 2000-2999 → other_income (partial)

For now: subaccounts are shown under the parent line_item they were extracted with (the extraction stores both konto_nr and line_item). No re-mapping needed.

## Files Changed

| File | Action | Lines affected |
|---|---|---|
| `src/dashboard.py` | Modify | ~266-420 (build_deal_data financials section), ~460-480 (return dict) |
| `src/templates/dashboard.html` | Modify | ~910-920 (sidebar), ~950-955 (showSection), ~1444-1574 (renderInformation + renderGuV), ~1658 (renderModel entry) |
| `ai/ROADMAP.md` | Update | DR-M9 status → 🔄 |

## NOT in scope

- Interactive model recalculation (GF salary panel, live params) — stays in model_context flow
- Net Debt tab — stays in model section, accessible from Bewertung subtab
- BWA/YTD data — no LTM/YTD data exists yet
- Current trading box — deferred until BWA extraction
- One-pager changes — Q2 renders independently from deal_financials
- New data extraction — uses existing deal_financials rows

## Verification

1. Dashboard server restart → Financials tab loads with unified view for Cat
2. Cat shows adjusted P&L as primary, with bridge on expand (both raw and adjusted exist)
3. Cat shows 43 konto_nr rows in subaccount drill-down under appropriate parent line items
4. Fox/Lion show adjusted P&L as primary (0 subaccount rows, no drill-down)
5. Mantis shows adjusted P&L (no raw P&L data at all — model only)
6. "Model" sidebar tab no longer exists
7. Bewertung accessible via Financials → Bewertung subtab
8. One-pager Q2 drill-down link still works
9. No regressions in portfolio cockpit financial data
