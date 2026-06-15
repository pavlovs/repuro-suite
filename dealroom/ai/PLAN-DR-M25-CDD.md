# PLAN DR-M25 — Commercial DD Module

Status: ✅ delivered 2026-06-10 (validated on Mantis databook v4)
Goal: the dealroom — not the databook xlsx or the PPT — is where CDD analysis lives.
Every analysis tab in the Repuro CDD databook is displayable and recomputed live
in the dashboard, tied out 1:1 against the databook before acceptance.

---

## Architecture decision

The databook works because invoice lines are the atomic fact table and every
analysis tab is SUMIFS on top. The dealroom mirrors that:

- **Stored**: raw facts only — `deal_invoices` (3,015 lines, EUR raw) and
  `deal_customers` (customer × year matrix, EUR k) + findings (`deal_dd_items`).
- **Computed**: every analysis (segments, quarterly GM, concentration, type
  split, buckets, new-vs-existing, cohort matrix, retention/NRR, churn, bridge)
  is recomputed at dashboard build time by `src/cdd.py`. No frozen aggregates —
  new invoice data refreshes every chart automatically.

## Components

| File | Role |
|---|---|
| `src/db.py` `_migrate_schema_v5` | `deal_invoices` table; `confidence` on `deal_dd_items`; `churn_reason` on `deal_customers` |
| `src/databook.py` | Deterministic ingest of OUR databook template (no AI classify) + `validate()` tie-out gate |
| `src/cdd.py` | `build_cdd(conn, domain)` — pure compute, databook methodology |
| `src/dashboard.py` | bakes `DATA.cdd` |
| `src/templates/sections/cdd.js` | CDD render helpers + `renderDDSection()` — NO standalone tab; content is distributed into the IC-memo sections |
| `DEALROOM.py ingest-databook <Deal> <xlsx>` | CLI: ingest + tie-out in one shot (exit 1 on any mismatch) |

## Section mapping (correction 2026-06-10)

The dealroom's 14 IC-memo sections ARE the presentation structure — CDD
analyses map into them; there is NO separate "Commercial DD" tab:

| Databook analysis | Dealroom section |
|---|---|
| Revenue split, segment GM, quarterly GM | **Business Model** (replaces wireframe when data present) |
| Concentration, type split, buckets, new-vs-existing, top 20 | **Customers & Suppliers** → Kunden |
| Cohort matrix, retention/NRR | **Customers & Suppliers** → Cohorts & Retention |
| Churn, churn by type, revenue bridge | **Customers & Suppliers** → Churn |
| Red flags, data gaps, confidence | **Due Diligence** (replaces stub) |
| Employee analyses (when ODD data lands) | **Employees** |

## Methodology (mirrors databook exactly)

- active in year = revenue **strictly > 0** (Excel COUNTIFS ">0" — credit-note-only years are NOT active)
- cohort = stored cohort column (first calendar year with revenue in window)
- logo retention = active in both years / active in start year
- NRR = next-year revenue of start-year base / start-year revenue
- churned = active in y, not active in y+1 (invoicing-based)
- buckets = per-customer TOTAL revenue across all years (EUR)
- concentration year = latest FULL year (YTD year excluded)

## Validation results (Mantis databook v4, 2026-06-10)

- Ingest: 3,015 invoices, 185 customers (498 customer-year rows), 7 red flags,
  6 data gaps, 8 confidence items.
- **Tie-out: 106/106 checks passed** — segment revenue & totals per year, GM%
  per segment-year, quarterly revenue, concentration tiers, customer-type split
  per year, buckets, cohort matrix + totals, logo retention + NRR per pair,
  churned logos + churned revenue per pair, churn by type.
- First run failed 9/106 → root cause: active was `!= 0` instead of `> 0`
  (databook COUNTIFS counts only positive years). Fixed in `cdd._active`.
- Visual: all 5 subtabs rendered headless (chrome-headless-shell, 1680px) and
  inspected — charts, tables, badges correct; sidebar item live (no stub badge).

## Codex review (gpt-5.4, 2026-06-10)

4 findings; 2 fixed, 2 rejected as by-design:
- **Fixed**: source isolation — when databook rows exist, `build_cdd` uses them
  exclusively (legacy/manual customer rows no longer mix into the tied-out
  population). Re-validated 106/106.
- **Fixed**: quarterly chart clamps negative-revenue quarters to zero-height bars.
- **Rejected (by design)**: NRR/bridge `rev_start` and concentration denominator
  use the TOTAL population, not the active base — that is exactly what the
  databook does (its Rev(start)/total rows are grand totals incl. credit-note
  customers); changing it would break the 1:1 tie-out contract.

## Known limits / next

- Invoice→customer link not available (databook anonymises customers) → no
  drill-down from customer to invoice lines yet. Ask seller export with
  customer IDs if needed.
- GM is materials-only (Rohertrag) — same caveat as databook red flag #7.
- Churn reasons: schema ready (`deal_customers.churn_reason`), data gap at seller.
- FDD side (EBIT quality, NWC seasonality, current trading) not in scope here —
  `deal_financials` supports monthly periods, ingest TBD.
- Other deals: rerun `ingest-databook` once their databooks exist — ingest is
  template-deterministic, not Mantis-specific.
