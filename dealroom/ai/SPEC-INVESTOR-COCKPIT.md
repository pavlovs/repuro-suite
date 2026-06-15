# SPEC: Investor Cockpit (DR-M9 Redesign)

Replaces the original DR-M9 (Investor One-Pager as standalone HTML export) with an integrated investor cockpit: the one-pager becomes the deal landing page in the dashboard, with drill-down into existing operational tabs.

**Template base**: `260504_Repuro_Deal_Onepagers_v4.pptx` (2x2 quadrant grid). Cross-referenced against `260522_Repuro_Aurica meeting_v1.pptx`. Layout spec in `golden-spec/SPEC-ONEPAGER.md`.

**Upstream**: DR-M4 (dashboard), DR-M5 (model reader), DR-M7 (valuation), DR-M8 (company overview), DR-GC (golden corpus).

**Downstream**: Replaces deal landing page. Portfolio filter enables stage-based pipeline views for investor meetings. PPTX export via `golden-spec/SPEC-ONEPAGER.md` — the Cockpit is the authoring/editing tool, the PPTX onepager is the investor-facing export. Q1/Q3/Q4 text stored in `deals.onepager_q1/q3/q4` flows directly into the PPTX template-fill process. Q2 is the only divergence: HTML renders a live chart from DB, PPTX requires a think-cell WMF or PNG image (manual).

---

## 1. Navigation Architecture

```
Portfolio Table (+ stage filter)
        │
        ▼  click deal code
One-Pager View (deal landing page)
        │
        ▼  click quadrant drill-down
Existing Tabs (Financials, Commercial, Timeline, etc.)
```

- Portfolio table: existing `renderPortfolio()` + new stage filter dropdown
- One-pager: replaces current deal landing page (was: cockpit strip + tabs)
- Drill-down: each quadrant links to the relevant existing tab, rendered below the one-pager (scroll target, not page navigation)
- Sidebar: retains access to all tabs including those not mapped to a quadrant (Documents, Model & Valuation, Open Topics, Internal Deal Screen)

---

## 2. Portfolio Stage Filter

Multi-select dropdown above the portfolio table.

**Options**: All Active (default), NDA, Valuation, Offer, LOI, Due Diligence, Closed, On Hold, Dead.

**Stage-to-filter mapping** (explicit DB enum → UI label):

| DB `deal_stage` | UI label | Included in "All Active" |
|-----------------|----------|--------------------------|
| `nda_exchange` | NDA | Yes |
| `valuation` | Valuation | Yes |
| `offer` | Offer | Yes |
| `loi` | LOI | Yes |
| `due_diligence` | Due Diligence | Yes |
| `closed` | Closed | No |
| `on_hold` | On Hold | No |
| `dead` | Dead | No |

**Rationale**: `nda_exchange` is an active funnel stage — excluding it would hide real pipeline deals from investor views and distort portfolio framing.

**Behavior**:
- "All Active" = nda_exchange + valuation + offer + LOI + DD (excludes dead, on_hold, closed)
- JS-only filtering (show/hide `<tr>` rows) — no server round-trip
- Footer SUM row recalculates based on visible rows
- Filter state persists in URL hash (e.g., `#stage=offer,loi`) for shareability
- No visual redesign of the portfolio table itself — only the filter addition

---

## 3. One-Pager Layout

HTML rendering of the PPTX 2x2 quadrant grid. Repuro CI colors (teal #0891B2 section headers, white backgrounds).

```
+-----------------------------------------------------------------------+
| [Codename] one-pager                    [Stage badge] [Days in stage] |
| [Title — key positioning message about the deal]               [edit] |
+-----------------------------------+-----------------------------------+
| Q1: EXECUTIVE SUMMARY             | Q2: FINANCIALS                    |
|                                   |                                   |
| • 5-6 bullets                     | Bar chart: Gesamtleistung + adj.  |
|   - Investment thesis             |   EBITDA by year (2022-2025P)     |
|   - Company size (rev, employees) | Margin % line overlay             |
|   - Strategic fit to Repuro       | Current trading box (LTM/YTD)     |
|   - Seller context / motivation   | Key metrics row                   |
|   - Key differentiator            |                                   |
|   - Deal attractiveness summary   |                                   |
|                          [▼ More] |                          [▼ More] |
+-----------------------------------+-----------------------------------+
| Q3: PROCESS / STATUS              | Q4: SERVICE PORTFOLIO             |
|                                   |                                   |
| • 5-6 bullets                     | • 5-6 bullets                     |
|   - Current deal stage + timing   |   - Core service lines / products |
|   - Next steps / open actions     |   - Revenue split by segment      |
|   - Key blockers / risks          |   - Customer split (B2B/B2C,      |
|   - Valuation: EV range           |     public/private, segments)     |
|   - Valuation: implied multiple   |   - Top customer concentration    |
|   - Deal structure (if offer+)    |   - Recurring revenue %           |
|                          [▼ More] |   - Geographic scope              |
|                                   |                          [▼ More] |
+-----------------------------------+-----------------------------------+
| [Footnote: "As of DD.MM.YYYY | Financials: FY2024A | Val: dd.mm.yy"] |
+-----------------------------------------------------------------------+
```

**[▼ More]** = drill-down link. Scrolls to the corresponding tab section below the one-pager.

**Footnote** (mandatory — auto-populated, editable):
- Default text: `"As of {today} | Financials: {latest_fiscal_year}A | Valuation: {valuation_date}"`
- `latest_fiscal_year`: max fiscal_year from `deal_financials` WHERE period_type='annual'
- `valuation_date`: `deal_valuations.created_at` of latest row
- If LTM/YTD data exists, append: `" | Current trading: {period_label}"`
- Stored in `deals.onepager_footnote`. Editable inline — Roman can override with custom caveats.
- Purpose: investors will immediately ask whether numbers are FY2024A, 2025P, or stale. This answers it.

---

## 4. Quadrant Specifications

### Q1: Executive Summary

**Data sources**:
- `deals.investment_thesis` (primary narrative source)
- `deal_financials` → latest annual gesamtleistung, adj. EBITDA, margin
- `deal_commercial` → recurring_pct
- `allex.company_records` → ma_count (employees), location
- `deals` → company_name, sector

**Content guide** (derived from golden corpus analysis):
- 5-6 bullets
- Bullet 1: what the company does + size (revenue, employees)
- Bullet 2: strategic fit to Repuro thesis (why this target)
- Bullet 3: financial attractiveness (margin, growth, adj. EBITDA level)
- Bullet 4: seller context / motivation for transaction
- Bullet 5: key differentiator or competitive position
- Bullet 6: overall deal attractiveness / recommendation

**Generation**: Claude (sonnet) with style guide prompt + deal data → draft bullets. Stored in `deals.onepager_q1`. Editable inline in dashboard (contenteditable, saved via API like existing overrides).

**Approval gate**: Generated bullets render with a yellow "DRAFT" badge. Roman marks as approved via a toggle button per quadrant (sets `onepager_q1_approved = 1`). Unapproved quadrants show the badge as a visual reminder that content has not been fact-checked. This is a soft gate — it does not block rendering, but prevents accidental investor exposure of unverified claims.

**Drill-down target**: Overview tab (company facts, investment thesis, key metrics, map).

---

### Q2: Financials

**Data sources**:
- `deal_financials` WHERE statement='pnl', period_type='annual' → gesamtleistung, ebitda (adj. preferred, raw fallback) per fiscal_year
- `deal_financials` WHERE period_type IN ('ltm', 'ytd') → current trading update
- `deal_valuations` → ev_mid, ev_low, ev_high, earnout_max, ebitda_basis. Implied multiple is computed at render time: `(ev_mid + earnout_max) / ebitda_basis` (NOT a stored field)
- `deal_financials` WHERE is_adjusted=1 → normalization items for adj. EBITDA

**Rendering** (self-contained HTML/CSS/JS, no external chart libs):

1. **Grouped bar chart**: Gesamtleistung (light teal) + adj. EBITDA (dark teal) per year. Year window is **data-driven** — shows all available annual fiscal years from `deal_financials`, not hardcoded. Y-axis in M€.
   - **Fallback for partial data**: if only 1-2 years available, render as a simple table instead of chart. If no projection year exists, omit "P" suffix. Label each year as "A" (actual) or "P" (projection) based on `deal_financials.is_projection` flag or fiscal_year > current year heuristic.
2. **Line overlay**: EBITDA margin % (right y-axis, dotted line with data points). Omitted if fewer than 2 data points.
3. **Current trading box** (conditional — only shown if LTM or YTD data exists):
   - Label: "Current Trading (LTM)" or "Current Trading (YTD MM/YYYY)"
   - Revenue, EBITDA, margin for the period
   - Styled as an inset card below or beside the chart
4. **Key metrics row** below chart:
   - Revenue CAGR (earliest to latest annual)
   - Latest adj. EBITDA (M€)
   - EBITDA margin %
   - EV range (low–high, M€)
   - Implied multiple (computed: EV incl. EO / adj. EBITDA)

**Not editable** — always reflects live DB state. If data is missing, show "—" with tooltip "No data — run `extract` or `model`".

**Drill-down target**: Financials tab (full P&L table, balance sheet, source badges, conflict indicators).

---

### Q3: Process / Status

**Data sources** (all existing fields):
- `deals.deal_stage`, `deals.stage_entered_at` → current stage + days in stage
- `deal_notes` → most recent 2-3 notes for context
- `deal_questions` WHERE status='open' → open blockers/risks (existing table, uses `importance` column)
- `deal_valuations` → ev_mid, ev_low, ev_high, earnout_max, ebitda_basis. Implied multiple computed at render time: `(ev_mid + earnout_max) / ebitda_basis`
- `deal_valuations` → cash_at_closing, rueckbeteiligung, earnout_structure (existing fields) → deal structure components

**Note**: `deal_actions` table does not exist — use `deal_questions` with category filtering. `deals.deal_structure_json` does not exist — deal structure is derived from `deal_valuations` fields.

**Content guide**:
- 5-6 bullets
- Bullet 1: current stage + how long in this stage
- Bullet 2: next concrete step / action required
- Bullet 3: key blockers or open risks
- Bullet 4: valuation — EV range and basis EBITDA
- Bullet 5: implied multiple (computed: EV incl. EO / adj. EBITDA)
- Bullet 6: deal structure overview (if offer stage+): Sofortzahlung / Rückbeteiligung / Earn-out split

**Audience note**: This quadrant contains internal deal-control content (blockers, valuation, deal structure). The dashboard is Roman's working tool — investors see the PPTX deck, not this dashboard. However, if screensharing during investor calls, review Q3 content beforehand to avoid exposing negotiation posture or unfinished thinking.

**Generation**: Claude (sonnet) with style guide + deal data → draft bullets. Stored in `deals.onepager_q3`. Editable inline. Same approval gate as Q1.

**Drill-down target**: Timeline tab (chronological events) + Notes tab.

---

### Q4: Service Portfolio

**Data sources**:
- `deal_commercial` → recurring_pct, key scalar KPIs (existing table — note: `service_lines` and `customer_segments` are not typed columns; data is stored as individual key/value rows or in free-text fields. Generation prompt must query available rows and interpret.)
- `deal_customers` → customer_name, revenue_share, rank (existing table — top customer concentration derived from top-N rows)
- `deal_financials` WHERE line_item LIKE 'revenue_%' → revenue by segment if available
- `allex.company_records` → business_description, sector (existing ALLEX fields)

**Content guide**:
- 5-6 bullets
- Bullet 1: core service lines / products offered
- Bullet 2: revenue split by service segment (% breakdown)
- Bullet 3: customer split — B2B vs. B2C, public vs. private, by segment
- Bullet 4: top customer concentration (top 1 / top 3 / top 10 as % of revenue)
- Bullet 5: recurring revenue % (contracts, framework agreements, repeat business)
- Bullet 6: geographic scope (local, regional, national, export)

**Generation**: Claude (sonnet) with style guide + deal data → draft bullets. Stored in `deals.onepager_q4`. Editable inline. Same approval gate as Q1.

**Drill-down target**: Commercial tab (full recurring %, customer detail, service line breakdown).

---

## 5. Generation Guide Architecture

The style guide for Q1/Q3/Q4 auto-generation is derived from the golden corpus one-pagers.

**Output language**: English. The existing golden one-pagers are in English. All generated bullets must be in English. German terms are acceptable only for domain-specific concepts (Gesamtleistung, Sofortzahlung, Rückbeteiligung, Gesellschafter).

**Source material**: All one-pager slides in `config/golden/onepager/` (v4 deck: ~8 deal slides, Aurica deck: investor-meeting variants).

**Extraction process** (one-time, during implementation):
1. Read all one-pager slides via `golden.py` PPTX loader
2. For each slide, extract text from Q1, Q3, Q4 text boxes (shape positions map to quadrants per SPEC-ONEPAGER.md)
3. Analyze across all slides:
   - Bullet count per quadrant (range + median)
   - Topics covered per quadrant (consistent vs. deal-specific)
   - Bullet length: word count range
   - Tone: formal/informal, assertive/hedged
4. Produce a structured prompt template per quadrant

**Output**: Three separate guide files (NEW — created by this milestone):
- `config/golden/onepager/guide-q1-exec-summary.md` — thesis, sizing, strategic fit patterns
- `config/golden/onepager/guide-q3-process-status.md` — stage, valuation, deal structure patterns
- `config/golden/onepager/guide-q4-service-portfolio.md` — commercial, customer, recurring patterns

**Rationale for separate files**: Each quadrant has different data sources, content rules, and tone. Separate guides allow independent iteration (Roman can refine Q4 customer phrasing without touching Q1) and prompt efficiency (generation loads only the relevant guide).

**Generation flow**:
```
guide-q{n}.md + deal data (quadrant-specific subset)
        │
        ▼  Claude sonnet (one call per quadrant)
Draft bullets for that quadrant
        │
        ▼  stored in deals.onepager_q{n}
Rendered in dashboard (editable inline)
```

**Re-generation**: `DEALROOM.py draft-onepager --deal Cat [--force]` regenerates bullets. Without `--force`, skips quadrants that have been manually edited (checks `onepager_edited_at > onepager_generated_at`). Can target a single quadrant: `--quadrant q1`.

---

## 6. DB Schema Changes

New columns on `deals` table (ALTERed, same pattern as existing `description`, `status_override`):

```sql
ALTER TABLE deals ADD COLUMN onepager_title TEXT;
ALTER TABLE deals ADD COLUMN onepager_q1 TEXT;
ALTER TABLE deals ADD COLUMN onepager_q3 TEXT;
ALTER TABLE deals ADD COLUMN onepager_q4 TEXT;
ALTER TABLE deals ADD COLUMN onepager_footnote TEXT;
ALTER TABLE deals ADD COLUMN onepager_generated_at TEXT;   -- ISO timestamp
ALTER TABLE deals ADD COLUMN onepager_edited_at TEXT;      -- ISO timestamp, set on manual edit
ALTER TABLE deals ADD COLUMN onepager_q1_approved INTEGER DEFAULT 0;
ALTER TABLE deals ADD COLUMN onepager_q3_approved INTEGER DEFAULT 0;
ALTER TABLE deals ADD COLUMN onepager_q4_approved INTEGER DEFAULT 0;
```

Re-generation (`draft-onepager`) resets `*_approved` to 0 — forces re-review after content changes.

Q2 has no stored text — always rendered live from `deal_financials` + `deal_valuations`.

Migration: added to `db.py` migration chain. Non-destructive (ADD COLUMN only).

---

## 7. Dashboard Code Changes

**`src/dashboard.py`**:
- `build_deal_data()` → add one-pager fields to the deal data dict
- New function `build_onepager_chart_data(conn, domain)` → extracts annual P&L + LTM/YTD for Q2 chart
- API endpoint `/api/update` → handle new `onepager_*` fields (same pattern as existing overrides)

**`src/templates/dashboard.html`**:
- New `renderOnepager()` function — renders the 2x2 grid as the first thing in deal view
- Existing tabs render below the one-pager (scroll targets)
- `renderPortfolio()` → add stage filter dropdown + filter logic
- Q2 chart: pure CSS/JS bar chart (no external dependencies — self-contained HTML constraint)
- Inline editing: `contenteditable` on Q1/Q3/Q4 text areas, blur → save via `/api/update`

**`DEALROOM.py`**:
- `draft-onepager` command: triggers generation for a deal (or `--all` for all deals)
- Reads golden generation guide, assembles deal data, calls Claude sonnet, stores results

**New file: `src/generate/onepager.py`** (CREATED BY THIS MILESTONE — does not exist yet):
- Generation logic: load guide + deal data → Claude prompt → parse response → store in DB
- Re-generation guard: skip if `onepager_edited_at > onepager_generated_at` unless `--force`

---

## 8. Drill-Down UX

When user clicks [▼ More] on a quadrant:
1. Smooth-scroll to the corresponding tab section below the one-pager
2. Tab is auto-activated (if using tab UI)
3. One-pager stays visible above (user can scroll back up)

Sidebar navigation retains all tabs:
- Overview (Q1 drill target)
- Financials (Q2 drill target)
- Commercial (Q4 drill target)
- Timeline (Q3 drill target)
- Model & Valuation
- Documents
- Notes
- Open Topics
- Internal Deal Screen

---

## 9. Constraints

- Self-contained HTML (no external JS/CSS libraries) — matches existing dashboard pattern
- PPTX export is NOT in scope for this milestone — see `golden-spec/SPEC-ONEPAGER.md` for the PPTX template-fill workflow that consumes the DB fields authored here
- Chart rendering: pure CSS/JS, no D3/Chart.js. Acceptable: `<canvas>` with inline JS or CSS grid bars
- Inline editing only in serve mode (same as existing portfolio overrides)
- Dead deal anti-pattern: Octopus is DEAD — exclude from default "All Active" filter
- Stage filter default: show active deals only (nda_exchange + valuation + offer + LOI + DD)

---

## 10. Definition of Done

1. Portfolio view has working stage filter (multi-select, JS-only)
2. Clicking a deal code shows the one-pager as landing page
3. All 4 quadrants render with correct data from DB
4. Q2 shows grouped bar chart + current trading box (when data exists)
5. Q1/Q3/Q4 bullets are auto-generated via `draft-onepager` command
6. Generated bullets match golden corpus style (validated against generation guide)
7. Inline editing works in serve mode for Q1/Q3/Q4 + title + footnote
8. Drill-down links scroll to correct tab sections
9. All existing tabs still accessible and functional
10. `pytest tests/` passes
11. Visually reviewed in browser on at least 2 deals with financial data
