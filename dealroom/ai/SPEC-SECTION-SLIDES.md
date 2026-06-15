# Section Slides — Implementation Brief

Each analytical section gets a slide header: hero chart (left 55%) + 4 KPI powercards (right 45%). Detail area below keeps existing render function. Exportable as 16:9 slide.

## Scope

| # | Section | sectionId | Hero chart | KPIs (4) | Detail (existing fn) |
|---|---------|-----------|-----------|----------|---------------------|
| 4 | Financials | financials | Revenue/EBITDA grouped bars | ebitda_margin, revenue_cagr, ev_ebitda_mult, adj_ebitda | renderInformation() |
| 5 | Offer | offer | Offer timeline (nodes+arrows) | current_ev, ev_delta, structure_split, implied_multiple | renderOfferNegotiation() |
| 6 | Business Model | business_model | Revenue mix stacked bar | recurring_pct, backlog, avg_order_value, active_contracts | renderBusinessModel() |
| 7 | Customers | customers | Concentration bar | top1_share, top3_share, total_customers, retention | renderCustomersWithSuppliers() |
| 9 | Thesis | thesis | Scorecard traffic-light bars | scorecard_overall, green_count, red_count, strategic_fit | renderThesis() |

## Verified data contract

| Path | Type | Key fields |
|------|------|-----------|
| `DATA.onepager_chart.yearly[yr]` | dict keyed by "YYYY" | revenue_k, ebitda_k, margin_pct, topline_growth_pct |
| `DATA.onepager_chart.bridge` | dict | ev_at_closing, sofortzahlung, earn_out |
| `DATA.onepager_chart.cagr` | float or null | 3-year revenue CAGR |
| `DATA.model_context.offer_history` | array | offer_date, ev_mid, ev_low, ev_high, earnout_max, status |
| `DATA.customers.metrics[yr]` | dict keyed by "YYYY" | num_customers, avg_order_value_k, churn_rate_pct |
| `DATA.customers.top10[yr]` | array keyed by "YYYY" | name, revenue, pct, rank |
| `DATA.customers.service_split` | array | label, pct |
| `DATA.scorecard` | dict | items[] with criterion, score, rating, weight |
| `DATA.commercial` | varies | backlog_value_k, avg_order_value, active_contracts |
| `DATA.financials.cagr` | dict | revenue, ebitda (floats) |

Note: `DATA.commercial` and `DATA.scorecard` may be unpopulated for some deals. Handle null gracefully.

## Shared components (DR-M24a)

```
formatKPI(value, format)           — pct|mult|eur_k|eur_m|ratio|count|score → German locale string
_slide_esc(str)                    — HTML escape for data-driven strings
renderKPIPowercards(kpis[])        — 2×2 grid of {label, value, format, bullet}
renderSlideSection(id, title, heroHtml, kpis[], detailHtml) — full slide assembly
exportSlide(sectionId)             — add .slide-export, window.print(), remove class
```

## KPI bubble-up rule

`getTopKPIs(DATA, 4)` — compute all 20 KPIs, sort by importance desc, apply section diversity (max 1 per section in first pass), backfill. Top 4 feed onepager Q2 strip (DR-M24h).

## Integration pattern

Section JS files live in `src/templates/sections/` — auto-inlined into dashboard.html via `__SECTIONS_JS__`. To wire a slide section:
1. Add slide components + KPI registry as new section JS files (loaded before wireframes)
2. Wrap existing `showSection` case: call `renderXxxSlide()` which uses existing detail fn
3. Server restart rebuilds HTML with new JS files

## Risks

- `DATA.commercial` / `DATA.scorecard` empty for most deals → all business_model + thesis KPIs return null. Wireframes must degrade gracefully with mock fallbacks.
- `offer_history` field names differ from wireframe assumptions (offer_date vs date, ev_mid vs ev). Adapter needed.
- Export hides detail area but doesn't isolate from dashboard chrome. Full export = DR-M24h.

## Milestones

| ID | What | Status |
|----|------|--------|
| DR-M24a | Shared components (slide-components.js) | wireframe done, needs integration |
| DR-M24b | KPI registry (kpi-registry.js) | wireframe done, needs integration |
| DR-M24c | Financials vertical slice | **next — wire into dashboard, render, verify** |
| DR-M24d-g | Remaining 4 sections | after pattern proven on Financials |
| DR-M24h | Export mechanism + onepager KPI strip | last |
