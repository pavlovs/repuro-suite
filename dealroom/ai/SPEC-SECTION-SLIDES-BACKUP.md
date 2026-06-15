# SPEC: Section Slides — Exportable Analytical Sections

Makes each analytical sidebar section exportable as a self-contained slide: hero chart on the left, 4 KPI powercards on the right, detailed analysis below. Mirrors the onepager's 4-quadrant visual language but applied per-section. A KPI decision layer ranks all KPIs by importance; the top 4 bubble up to populate the onepager (Section 1).

**Upstream**: SPEC-SIDEBAR-ARCHITECTURE.md (section numbering, block structure), SPEC-INVESTOR-COCKPIT.md (onepager Q1/Q2 layout, quadrant headers), SPEC-ONEPAGER.md (PPTX visual language, Repuro palette).

**Downstream**: Feeds onepager Q1 (executive summary bullets via KPI `bullet` text) and Q2 (headline KPI strip below financial chart) via KPI bubble-up. Export mechanism produces standalone 16:9 slides matching PPTX onepager aesthetics.

---

## 1. Scope — Which Sections Get the Pattern

The hero chart + KPI powercard header applies to **5 analytical sections** across Blocks A and B:

| # | Section | Hero Chart | KPI 1 | KPI 2 | KPI 3 | KPI 4 |
|---|---------|-----------|-------|-------|-------|-------|
| 4 | Valuation & Financials | Revenue/EBITDA trend bar | EBITDA margin % | Revenue CAGR | EV/EBITDA multiple | Adj. EBITDA K |
| 5 | Offer & Negotiation | Offer progression timeline | Current EV M | Delta from last round % | Sofort/EO split | Implied multiple |
| 6 | Business Model | Revenue mix stacked bar | Recurring rev. % | Order backlog M | Avg. order value K | Active contracts |
| 7 | Customers & Suppliers | Concentration curve | Top-1 customer % | Top-3 share % | Total customers | Retention rate |
| 9 | Thesis & Fit | Scorecard radar summary | Overall score | Green signals | Red flags | Strategic fit score |

### NOT in scope

- **Section 1 (One-Pager)**: already has its own 4-quadrant layout per SPEC-INVESTOR-COCKPIT.md.
- **Section 2 (Overview)**: explicitly excluded — company facts don't need this pattern.
- **Section 3 (Deal History)**: process timeline, not analytical.
- **Section 8 (Employees)**: data-thin — `deal_employees` table is empty across all deals.
- **Section 10 (Market & Competition)**: data-thin — `deal_competitors` table is empty.
- **Block C (RFI, DD, Documents, Notes)**: operational/utility views, not exportable.

---

## 2. Layout Pattern — Slide Section Component

```
+----------------------------------------------------------+
| [Section Icon] SECTION TITLE                    [Export]  |  <- teal bar (#0891B2)
+---------------------------+------------------------------+
|                           | +----------+ +----------+    |
|     HERO CHART            | | KPI 1    | | KPI 2    |    |
|     (the one story        | | value    | | value    |    |
|      that matters)        | | bullet   | | bullet   |    |
|                           | +----------+ +----------+    |
|                           | +----------+ +----------+    |
|                           | | KPI 3    | | KPI 4    |    |
|                           | | value    | | value    |    |
|                           | | bullet   | | bullet   |    |
|                           | +----------+ +----------+    |
+---------------------------+------------------------------+
| DETAILED ANALYSIS                                        |
| (existing section content: tables, breakdowns, etc.)     |
+----------------------------------------------------------+
```

### CSS specifications

| Element | Property | Value |
|---------|----------|-------|
| Slide container | max-width | `960px` |
| | aspect-ratio (export mode) | `16/9` |
| | background | `#fff` |
| | border | `1px solid #e2e8f0` |
| | border-radius | `8px` |
| Section header bar | background | `#0891B2` |
| | color | `#fff` |
| | padding | `10px 16px` |
| | font | `16px/1 Arial bold` |
| Hero chart area | flex | `0 0 55%` |
| | min-height | `180px` |
| | padding | `16px` |
| KPI powercard grid | flex | `0 0 45%` |
| | display | `grid` |
| | grid-template-columns | `1fr 1fr` |
| | gap | `10px` |
| | padding | `16px` |
| KPI powercard | background | `#f8fafc` |
| | border | `1px solid #e2e8f0` |
| | border-radius | `6px` |
| | padding | `12px` |
| KPI label | font-size | `11px` |
| | color | `#64748b` |
| | text-transform | `uppercase` |
| | letter-spacing | `0.5px` |
| KPI value | font-size | `22px` |
| | font-weight | `700` |
| | color | `#0f172a` |
| | font-family | `Arial` |
| KPI bullet | font-size | `11px` |
| | color | `#475569` |
| | margin-top | `4px` |
| Export button | position | small icon in header bar, right-aligned |
| Detail area | padding | `20px` |

---

## 3. KPI Registry

Full registry as a JavaScript object. Each KPI has: id, label, importance (1-10), format type, compute function, and a one-line bullet explaining why it matters.

```javascript
// NOTE: Pseudocode — actual implementation in DR-M24b uses ES5 + _kpi_ helpers.
// Data paths: DATA.onepager_chart.yearly (keyed by year), DATA.onepager_chart.bridge
const KPI_REGISTRY = {
  financials: [
    { id: 'ebitda_margin', label: 'EBITDA Margin', importance: 9, format: 'pct',
      compute: (D) => {
        const yr = latestYear(D.onepager_chart?.yearly);
        return yr?.margin_pct ?? null;
      },
      bullet: 'Profitability benchmark for medtech distribution' },
    { id: 'revenue_cagr', label: 'Revenue CAGR', importance: 8, format: 'pct',
      compute: (D) => {
        const yearly = D.onepager_chart?.yearly;
        // CAGR over all available years (min 3)
        return cagr(yearly) ?? null;
      },
      bullet: 'Organic growth trajectory' },
    { id: 'ev_ebitda_mult', label: 'EV / EBITDA', importance: 9, format: 'mult',
      compute: (D) => {
        const ev = D.onepager_chart?.bridge?.ev_at_closing;
        const ebitda = latestYear(D.onepager_chart?.yearly)?.ebitda_k;
        return ev && ebitda ? ev / ebitda : null;
      },
      bullet: 'Implied valuation at closing' },
    { id: 'adj_ebitda', label: 'Adj. EBITDA', importance: 7, format: 'eur_k',
      compute: (D) => {
        return latestYear(D.onepager_chart?.yearly)?.ebitda_k ?? null;
      },
      bullet: 'Earnings basis for valuation' },
  ],

  offer: [
    { id: 'current_ev', label: 'Current EV', importance: 8, format: 'eur_m',
      compute: (D) => {
        const ev = D.onepager_chart?.bridge?.ev_at_closing;
        return ev ? ev / 1000 : null;
      },
      bullet: 'Enterprise value in current round' },
    { id: 'ev_delta', label: 'Δ from Prior', importance: 6, format: 'pct',
      compute: (D) => {
        const hist = D.model_context?.offer_history;
        if (!hist || hist.length < 2) return null;
        const curr = hist[hist.length - 1].ev;
        const prev = hist[hist.length - 2].ev;
        return prev > 0 ? ((curr - prev) / prev * 100) : null;
      },
      bullet: 'Price movement between rounds' },
    { id: 'structure_split', label: 'Sofort / EO', importance: 7, format: 'ratio',
      compute: (D) => {
        const bridge = D.onepager_chart?.bridge;
        if (!bridge?.sofortzahlung || !bridge?.ev_at_closing) return null;
        const sofort_pct = bridge.sofortzahlung / bridge.ev_at_closing * 100;
        return { sofort: sofort_pct, eo: 100 - sofort_pct };
      },
      bullet: 'Closing payment vs. deferred' },
    { id: 'implied_multiple', label: 'Implied Multiple', importance: 7, format: 'mult',
      compute: (D) => {
        // Same computation as ev_ebitda_mult — contextualised for offer analysis
        const ev = D.onepager_chart?.bridge?.ev_at_closing;
        const ebitda = latestYear(D.onepager_chart?.yearly)?.ebitda_k;
        return ev && ebitda ? ev / ebitda : null;
      },
      bullet: 'Price-to-earnings at current offer' },
  ],

  business_model: [
    { id: 'recurring_pct', label: 'Recurring Rev.', importance: 9, format: 'pct',
      compute: (DATA) => DATA.commercial?.recurring_revenue_pct ?? null,
      bullet: 'Revenue quality — higher = more predictable' },
    { id: 'backlog', label: 'Order Backlog', importance: 7, format: 'eur_m',
      compute: (DATA) => DATA.commercial?.order_backlog_k
        ? DATA.commercial.order_backlog_k / 1000 : null,
      bullet: 'Contracted future revenue' },
    { id: 'avg_order_value', label: 'Avg. Order', importance: 5, format: 'eur_k',
      compute: (DATA) => DATA.commercial?.avg_order_value_k ?? null,
      bullet: 'Ticket size per transaction' },
    { id: 'active_contracts', label: 'Active Contracts', importance: 5, format: 'count',
      compute: (DATA) => DATA.commercial?.active_contracts ?? null,
      bullet: 'Number of running service agreements' },
  ],

  customers: [
    { id: 'top1_share', label: 'Top-1 Customer', importance: 8, format: 'pct',
      compute: (DATA) => {
        const top = DATA.customers?.top10?.[0];
        return top?.revenue_share_pct ?? null;
      },
      bullet: 'Single-customer dependency risk' },
    { id: 'top3_share', label: 'Top-3 Share', importance: 7, format: 'pct',
      compute: (DATA) => {
        const top3 = DATA.customers?.top10?.slice(0, 3);
        if (!top3?.length) return null;
        return top3.reduce((s, c) => s + (c.revenue_share_pct ?? 0), 0);
      },
      bullet: 'Revenue concentration in top accounts' },
    { id: 'total_customers', label: 'Total Customers', importance: 5, format: 'count',
      compute: (DATA) => DATA.customers?.total_count ?? null,
      bullet: 'Breadth of customer base' },
    { id: 'retention', label: 'Retention Rate', importance: 8, format: 'pct',
      compute: (DATA) => DATA.customers?.retention_pct ?? null,
      bullet: 'Customer stickiness — churn inverse' },
  ],

  thesis: [
    { id: 'scorecard_overall', label: 'Overall Score', importance: 9, format: 'score',
      compute: (DATA) => DATA.scorecard?.weighted_average ?? null,
      bullet: 'Composite investment attractiveness' },
    { id: 'green_count', label: 'Green Signals', importance: 6, format: 'count',
      compute: (DATA) => DATA.scorecard?.items
        ?.filter(i => i.rating === 'green').length ?? null,
      bullet: 'Number of strong-performing criteria' },
    { id: 'red_count', label: 'Red Flags', importance: 8, format: 'count',
      compute: (DATA) => DATA.scorecard?.items
        ?.filter(i => i.rating === 'red').length ?? null,
      bullet: 'Material concerns requiring attention' },
    { id: 'strategic_fit', label: 'Strategic Fit', importance: 9, format: 'score',
      compute: (DATA) => DATA.scorecard?.strategic_fit_score ?? null,
      bullet: 'Alignment with Repuro buy-and-build thesis' },
  ],
};
```

---

## 4. KPI Bubble-Up to Onepager

The onepager (Section 1) automatically references the most important KPIs from across all sections.

### Logic

1. Collect all KPIs where `compute(DATA)` returns a non-null value (data available for this deal).
2. Sort by `importance` descending.
3. Take top 4 — these become the headline KPIs in the onepager's Q2 area as a compact KPI strip below the financial chart.
4. The same KPIs inform auto-generation of Q1 executive summary bullets (`bullet` text feeds into the `draft-onepager` prompt).

### Implementation

```javascript
function getTopKPIs(DATA, n = 4) {
  const all = [];
  for (const [section, kpis] of Object.entries(KPI_REGISTRY)) {
    for (const kpi of kpis) {
      const value = kpi.compute(DATA);
      if (value != null) all.push({ ...kpi, section, value });
    }
  }
  all.sort((a, b) => b.importance - a.importance);
  return all.slice(0, n);
}
```

**Tie-breaking**: when multiple KPIs share the same importance score, prefer diversity across sections (no two from the same section in the top 4 unless no alternatives exist). Implementation: after sorting by importance, apply a secondary pass that deduplicates by section, backfilling from the remaining pool.

### Onepager integration points

| Onepager area | What it receives | How |
|---------------|-----------------|-----|
| Q2 KPI strip | Top 4 KPI labels + formatted values | `getTopKPIs(DATA, 4)` rendered as a compact row below the Q2 chart |
| Q1 bullets | KPI `bullet` text + formatted values | Fed into `draft-onepager` prompt as context; not rendered directly |

---

## 5. Hero Chart Specifications

### Section 4 — Valuation & Financials

Revenue + EBITDA grouped bar chart (3-4 years). Revenue bars in light cyan (`#67e8f9`), EBITDA bars in teal (`#0891B2`). Year labels below x-axis. Same pattern as onepager Q2 but rendered at larger size (fills 55% of the slide header).

**Data source**: `DATA.onepager_chart.yearly` (array of `{ year, revenue, ebitda }`).

### Section 5 — Offer & Negotiation

Offer progression timeline. Horizontal timeline showing each offer round as a labeled node with EV amount (M). Current/latest round highlighted with teal fill; prior rounds in light gray. Connecting line between nodes shows price trajectory.

**Data source**: `DATA.model_context.offer_history` or `deal_valuations` ordered by date.

### Section 6 — Business Model

Revenue mix stacked bar chart. Shows service lines as segments of a horizontal stacked bar. Colors from Repuro palette: `#0891B2` (primary), `#22D3EE` (secondary), `#67e8f9` (tertiary), `#8DE8F6` (quaternary), `#e2e8f0` (other). Reuses the `renderServicePortfolioChart()` pattern from onepager Q4.

**Data source**: `DATA.customers.service_split` or `DATA.commercial`.

### Section 7 — Customers & Suppliers

Customer concentration horizontal stacked bar. Segments: Top-1 (`#0891B2`), Top 2-3 (`#22D3EE`), Top 4-10 (`#67e8f9`), Rest (`#e2e8f0`). Each segment labeled with percentage. Alternative: Lorenz-style area chart showing cumulative revenue share vs. cumulative customer count.

**Data source**: `DATA.customers.top10`.

### Section 9 — Thesis & Fit

Scorecard summary — compact horizontal bar chart. One bar per scorecard metric, colored green/yellow/red based on rating. Metric label on the left, score value on the right. Sorted by importance or grouped by category.

**Data source**: `DATA.scorecard` or `deal_scorecard_results`.

---

## 6. Export Mechanism

Each slide section has an export button (small icon in the header bar, right-aligned) that produces a 16:9 image or print-ready view.

### Export flow

1. Add `.slide-export` class to the container.
2. `.slide-export` constrains to exact 16:9 ratio (`960px x 540px`) and hides the detail area.
3. Capture via `html2canvas` or native `window.print()` with a print stylesheet.
4. Remove `.slide-export` class after capture.

### Print CSS

```css
@media print {
  .slide-section.exporting .slide-detail {
    display: none;
  }
  .slide-section.exporting {
    width: 960px;
    height: 540px; /* 16:9 */
    page-break-inside: avoid;
    border: none;
    box-shadow: none;
  }
}
```

### Visual requirements

Exported slides must match the PPTX onepager visual language:
- Repuro teal (`#0891B2`) header bars
- Arial font throughout
- White background
- No dashboard chrome (sidebar, nav, scroll indicators) in the export

---

## 7. Component API

```javascript
/**
 * Renders a complete slide section: header bar + hero chart + KPI powercards + detail area.
 * @param {string} sectionId - Registry key (e.g. 'financials', 'offer')
 * @param {string} title - Section display title
 * @param {Function} heroChartFn - (container, DATA) => void; renders hero chart into container
 * @param {Array} kpis - Array of { id, label, value, format, bullet }
 * @param {Function} detailFn - (container, DATA) => void; renders detail content
 * @returns {HTMLElement}
 */
function renderSlideSection(sectionId, title, heroChartFn, kpis, detailFn) { ... }

/**
 * Renders the 2x2 KPI powercard grid.
 * @param {Array} kpis - Array of 4 KPIs with computed values
 * @returns {HTMLElement}
 */
function renderKPIPowercards(kpis) { ... }

/**
 * Formats a KPI value based on its format type.
 * @param {number|object} value - Raw KPI value
 * @param {string} format - One of: 'pct', 'mult', 'eur_k', 'eur_m', 'ratio', 'count', 'score'
 * @returns {string} Formatted display string
 *
 * Format rules:
 *   pct    -> '14.1%'          (1 decimal)
 *   mult   -> '5.2x'           (1 decimal + x suffix)
 *   eur_k  -> '842 K€'         (integer, dot thousands, de-DE)
 *   eur_m  -> '3.2 M€'         (1 decimal)
 *   ratio  -> '72 / 28'        (integer percentages)
 *   count  -> '127'            (integer)
 *   score  -> '7.4 / 10'       (1 decimal)
 */
function formatKPI(value, format) { ... }

/**
 * Returns the top N KPIs across all sections, sorted by importance.
 * Prefers section diversity when importance scores tie.
 * @param {Object} DATA - Deal data object
 * @param {number} n - Number of KPIs to return (default 4)
 * @returns {Array} Top KPIs with section, value, label, format, bullet
 */
function getTopKPIs(DATA, n = 4) { ... }

/**
 * Triggers export of a single section as a 16:9 slide.
 * Adds .slide-export class, captures via html2canvas, removes class.
 * @param {string} sectionId - Section to export
 */
function exportSlide(sectionId) { ... }
```

---

## 8. Integration with Existing Sections

Each section that receives the slide pattern keeps its existing render function for the detail area. The slide header (hero + powercards) wraps on top.

### Wiring pattern

1. Existing `render*()` function becomes the `detailFn` argument.
2. `renderSlideSection()` adds the hero + powercard header above.
3. Hero chart is a NEW function specific to each section.
4. KPIs are pulled from `KPI_REGISTRY[sectionId]` and computed at render time.

### Example — Financials

```javascript
function renderFinancialsSlide() {
  const kpis = KPI_REGISTRY.financials.map(k => ({
    ...k,
    value: k.compute(DATA)
  }));
  return renderSlideSection(
    'financials',
    'Valuation & Financials',
    renderFinancialsHero,
    kpis,
    renderUnifiedGuV
  );
}
```

### Section-to-function mapping

| Section | sectionId | heroChartFn | detailFn |
|---------|-----------|-------------|----------|
| 4. Valuation & Financials | `financials` | `renderFinancialsHero` | `renderUnifiedGuV` |
| 5. Offer & Negotiation | `offer` | `renderOfferTimeline` | `renderOfferSection` |
| 6. Business Model | `business_model` | `renderRevenueMixChart` | `renderBusinessModel` |
| 7. Customers & Suppliers | `customers` | `renderConcentrationChart` | `renderCustomers` |
| 9. Thesis & Fit | `thesis` | `renderScorecardSummary` | `renderThesisFit` |

---

## 9. Visual Consistency Rules

| Rule | Value |
|------|-------|
| Section header bars | `#0891B2` (Repuro teal), Arial 16px bold, white text — identical to onepager quadrant headers |
| KPI values | `font-variant-numeric: tabular-nums`, Arial |
| Chart palette | `#0891B2`, `#22D3EE`, `#67e8f9`, `#8DE8F6`, `#e2e8f0` only |
| Number formatting | German locale (`de-DE`), dot thousands separators |
| Currency | K with euro sign for thousands, M with euro sign for millions |
| Percentages | One decimal, e.g. `14.1%` |
| Multiples | One decimal with x suffix, e.g. `5.2x` |
| Scores | One decimal out of 10, e.g. `7.4 / 10` |

---

## 10. Implementation Milestones

| Milestone | Scope | Dependencies |
|-----------|-------|-------------|
| DR-M24a | Shared slide-section component: CSS + `renderSlideSection` + `renderKPIPowercards` + `formatKPI` | None |
| DR-M24b | KPI registry + bubble-up logic: `KPI_REGISTRY` object + `getTopKPIs` + onepager Q2 KPI strip integration | DR-M24a |
| DR-M24c | Financials slide wireframe: `renderFinancialsHero` + KPIs + existing `renderUnifiedGuV` as detail | DR-M24a, DR-M24b |
| DR-M24d | Business Model slide wireframe: `renderRevenueMixChart` + KPIs + detail | DR-M24a, DR-M24b |
| DR-M24e | Customers slide wireframe: `renderConcentrationChart` + KPIs + detail | DR-M24a, DR-M24b |
| DR-M24f | Thesis & Fit slide wireframe: `renderScorecardSummary` + KPIs + detail | DR-M24a, DR-M24b |
| DR-M24g | Offer & Negotiation slide wireframe: `renderOfferTimeline` + KPIs + detail | DR-M24a, DR-M24b |
| DR-M24h | Export mechanism: print CSS + `exportSlide` + html2canvas integration | DR-M24a through DR-M24g |

### Suggested execution order

DR-M24a → DR-M24b → DR-M24c (proves the pattern on the data-richest section) → DR-M24d/e/f/g (parallel, independent) → DR-M24h (export last, needs all sections).
