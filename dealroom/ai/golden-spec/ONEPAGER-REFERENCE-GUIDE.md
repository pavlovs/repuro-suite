# Onepager Reference Guide

Practical reference for populating the 4-quadrant deal onepager. Sources: `SPEC-ONEPAGER.md`, the three Q-guides in `config/golden/onepager/`, and DB content for Mantis, Cat, Fox.

---

## 1. Layout and what each quadrant does

```
+-------------------------------------+-------------------------------------+
| Q1: EXECUTIVE SUMMARY               | Q2: FINANCIALS                      |
| 4-6 bullets: company, financials,   | Revenue/EBITDA bar chart (WMF/PNG   |
| revenue quality, valuation, fit     | — not automatable) + optional BP    |
|                                     | scenario and valuation bridge       |
+-------------------------------------+-------------------------------------+
| Q3: PROCESS DETAILS                 | Q4: SERVICE PORTFOLIO & CUSTOMERS   |
| 3-5 bullets: transaction structure, | 3-5 bullets: revenue split, customer|
| transition, status, open items,     | concentration, recurring share,     |
| DD focus                            | supplier info, sector breakdown     |
+-------------------------------------+-------------------------------------+
```

**Q2 is the only quadrant not driven by DB text fields** — it renders from financial data (deal_financials, deal_valuations, deals.bp_2026_*). The bar chart itself is always a manual WMF/PNG from think-cell or a screenshot. Never attempt to auto-generate it.

---

## 2. Q1 — Executive Summary

### Bullet pattern (from guide-q1-exec-summary.md)

1. Company description — what, for whom, geography (1 sentence)
2. Financial headline — revenue + adj. EBITDA + margin + CAGR if meaningful
3. Revenue quality — recurring share %, top-3/top-5 concentration, or cash flow signal
4. Valuation structure — EV at closing (M€, multiple), earn-out if any
5. Strategic fit — anchor vs. add-on, region, product gap, Repuro thesis
6. (Optional) notable differentiator or risk mitigant

**Format rules:** Bold the key metric/claim in each bullet. 1-2 sentences max per bullet. No adjectives without a number. Never blend closing EV and total EV into a single figure without disclosing the earn-out separately. Multiple format: `X.Xx {year}A EBITDA`.

### Real examples

**Mantis:**
> Mantis generated **~3.1 M€ revenue at ~0.8 M€ adj. EBITDA (~25%)** in 2025, with 2023-25 revenue CAGR of ~7%
> EV at closing of **4.3 M€ (5.3x 2025A EBITDA)**, with anticipated earn-out of **0.5 M€** resulting in total **EV of 4.8 M€ (5.9x 2025 EBITDA)**
> Mantis could serve as an **attractive small platform** given its differentiated technical / service capability, scalable model and untapped new-customer acquisition potential

**Cat:**
> Cat generated **~6.2 M€ revenue** at **~0.9 M€ adj. EBITDA (~15% margin)** in 2025 and revenue CAGR 2023-25 of **~15%** and targets **~6.5 M€ revenue** and **0.9 M€ EBITDA in 2026**
> EV at closing of **3.4 M€ (3.6x 2025 EBITDA)**, with anticipated earn-out to **1.8 M€ (5.5x 2025)** and max earn-out incl. super bonus to 1.1 M€ (5.6x at 1.1 M€ EBITDA target)

**Fox:**
> Fox generated **~3.5 M€ revenue** at **0.4 M€ adj. EBITDA (10%)** in 2025, with **consistent growth** since 2021 (~9% CAGR 2021-2025)
> EV at closing of **1.6 M€ (4.5x 2025A EBITDA)**, with further earn-out of **0.3 M€** resulting in total **EV of 1.9 M€ (5.3x 2025 EBITDA or 4.4x** required EBITDA for earn-out**)**

### DB field
`deals.onepager_q1` — one string, bullets prefixed with `- `, `**bold**` for emphasis.

---

## 3. Q2 — Financials (chart-driven)

Q2 is not a text field. The dashboard renders it from DB data. No `onepager_q2` column exists.

### What drives Q2

| Element | Source |
|---------|--------|
| Historical revenue/EBITDA bars (2022-2025) | `deal_financials` — `line_item IN ('revenue','ebitda_adj','ebit_adj')`, `period_type='annual'` |
| 2026 BP scenario | `deals.bp_2026_rev_k`, `deals.bp_2026_ebitda_k` |
| 2026 max earn-out scenario | `deals.maxeo_2026_ebitda_k` |
| EBITDA margin % per year | Computed: `ebitda_k / revenue_k * 100` |
| Valuation bridge (EV at closing / earn-out / total / net cash) | `deal_financials` with `line_item IN ('ev_at_closing','ev_anticipated_earnout','ev_total','net_cash_debt','equity_value')` |
| Valuation widget (ev_mid, earnout_max, multiple) | `deal_valuations` — `ev_mid`, `ev_high`, `earnout_max`, `ebitda_basis`, `ebitda_basis_label`, `multiple_mid` |
| Forward projections | `deals.proj_topline_growth_pct`, `deals.proj_ebitda_margin_pct` |

**Priority logic in `_build_onepager_chart_data`:** For revenue: adjusted revenue (`is_adjusted=1`) > gesamtleistung > raw. For EBITDA: `ebitda_adj` (`is_adjusted=1`) > `ebitda` (`is_adjusted=0`). For EBIT: `ebit_adj` or `ebit` with `is_adjusted=1` > raw. Uses MAX per year when multiple rows exist for same year/entity.

The bar chart visual (WMF/PNG in the PPTX) is a separate manual artifact — it does not come from the DB. The HTML dashboard renders native bars from the DB data.

---

## 4. Q3 — Process & Status

### Bullet pattern (from guide-q3-process-status.md)

1. Transaction structure — acquiring what, from whom, sourcing channel (broker/direct)
2. Transition — GF/owner stay-on duration and role
3. Reinvestment — if applicable (pari passu reinvestment amount/%)
4. Status — current stage + last meaningful action + next step
5. DD focus — the 3-5 specific items that need verification

**Format rules:** Bold the stage name or key status word. No financial performance data in Q3 (that belongs in Q1). Risk bullet must name a specific gap, not generic "execution risk". State open questions concretely.

### Real examples

**Mantis:**
> **Transaction background:** Acquiring 100% of shares (two managing shareholders: senior owner + son); proprietary sourcing, owner re-contacted Repuro after exclusive process was terminated due to personal fit with strategic buyer
> **Reinvestment:** 0.5 M€ (~10%) of cash purchase price to be reinvested pari passu with investors in Repuro group
> **Due diligence:** Specific focus on recurring vs. demand-driven revenue, OEM/Olympus dependency, adjustments, inventory valuation, customer churn, revenue visibility

**Cat:**
> **Status:** After final offer send-out, we focus now on progressing to LOI and diving into deeper commercial and financial DD
> **Real estate:** Office building and land is owned by Cat and will be sold to a separate investor with a long-term rental contract as a condition for the successful closing of the transaction
> **Due diligence:** Cat appears as an attractive investment opportunity, key DD items will be: sustainability of 2025 EBITDA (4x step-up, project-driven), customer churn rate, quality of projects and outlooks, further add-ons in this space as well as the high debt of the company

**Fox:**
> - **Status:** Q1 in-line with 2025 numbers, preparing updated indicative offer (initial offer sent last year, now updated with full-year 2025 view that outperformed, seller price expectations in line with updated offer)
> - **Transaction:** Acquiring 100% of shares; Fox approached through proprietary sourcing in 2025; Fox owns 2 Co-Med shares, mid-term dependency to be analyzed

Note: Cat/Mantis use bold-prefixed labels (`**Label:**`); Fox uses `- ` bullet prefix. Either style works; pick one per deal and be consistent.

### DB field
`deals.onepager_q3`

---

## 5. Q4 — Service Portfolio & Customer Structure

### Bullet pattern (from guide-q4-service-portfolio.md)

1. Core product/service offering — revenue split by type with percentages
2. Customer structure — concentration (top-1/3/5/10 %), sector breakdown, framework vs. spot
3. Recurring revenue — share %, contract types, repeat-purchase dynamics
4. (Optional) Geographic footprint — specific region/city, not just "Germany"
5. (Optional) Regulatory/certification differentiator — only if commercially meaningful

**Format rules:** Bold the key commercial metric or category label. Percentages must match the service_split and deal_commercial data — no contradictions with Q2. Max 5 bullets. Do not include valuation or process info here.

### Real examples

**Mantis:**
> Manufacturer-independent **endoscopy distribution and service** partner for gastroenterology practices, MVZs and hospital endoscopy departments
> **Fragmented customer base** (>100 customers make up 80% of sales); long-standing, trust-based relationships; growth inbound / word-of-mouth with no active sales to date
> Sales largely driven by **existing customers (~80%)** with limited sales efforts; however, contractual recurring share is thin (~14 service contracts) — recurring vs. churn to be verified in DD

**Cat:**
> **~70% of revenue with projects, ~24% recurring service** (70-75% GM) and ~6% other. Growing share of service (up from ~20% in 2023)
> Customer base is **~95% hospitals** and ambulatory surgery centers; Top 10 concentration **~50% in 2025** (down from ~70% in 2023, diversifying)
> **Order backlog ~10.5 M€ (~1.5x revenue)** across ~40 projects, with the largest project ~1.8 M€ over 3 years

**Fox:**
> - **Distribution and service partner** to ambulatory care providers (doctors, medical facilities, practice founders, health centers, MVZs, ambulant surgery settings)
> - Revenue from **distributing medical products** and devices (ultrasound) with additional service offering (practice planning, IT, technical service, STK/MTK inspections)
> - Customer concentration and recurring revenue share remain to be verified in due diligence

### DB field
`deals.onepager_q4`

### Data that drives the Q4 charts in the dashboard

| Chart | Source |
|-------|--------|
| Revenue split pie (Handel/Service/Eigenprodukte) | `deal_commercial WHERE category='service_split'` — `metric`=label, `value_num`=pct, `fiscal_year`=2025 |
| Customer concentration bar (top-1/5/10 per year) | `deal_commercial WHERE category='customers'` — `metric` IN ('top1_share','top5_share','top10_share'), `value_num`=pct |
| Recurring rev share | `deal_commercial WHERE category='customers' AND metric='recurring_rev_share'` |
| Top-10 customer table | `deal_customers` — `revenue_k`, `revenue_pct`, `rank`, `customer_name`, `fiscal_year` |

`_build_customers` in `src/dashboard.py` reads all three and returns `{metrics, top10, service_split}`.

---

## 6. Other DB fields on the `deals` table

| Column | Purpose |
|--------|---------|
| `onepager_title` | Short slide title shown in header (e.g. "Mouse (Landgraf Laborsysteme HLL)") |
| `onepager_headline` | 1-line deal thesis shown below the title |
| `onepager_footnote` | Footer caveat text (data sources, open items, caveats) |
| `onepager_generated_at` | UTC ISO timestamp; set when content is written |
| `onepager_q1_approved` / `onepager_q3_approved` / `onepager_q4_approved` | 0=draft (shown with DRAFT badge in cockpit), 1=approved for PPTX fill |

---

## 7. How to generate and render

### Draft text content
```bash
python DEALROOM.py draft-onepager --deal <Codename>
```
Uses Claude sonnet to draft Q1/Q3/Q4 from deal data. Writes to `deals.onepager_q1/q3/q4`. Review and edit in the Cockpit HTML, then set `*_approved=1` per quadrant when ready.

### Render HTML dashboard
```bash
python DEALROOM.py dashboard --deal <Codename>
```
Writes to `data/output/dashboard_<Codename>_<date>.html`. No server needed. Opens browser automatically. The HTML renders all four quadrants plus the financial chart from DB data.

### Populate financial/commercial data first
Before rendering, ensure these tables are populated for the deal:
- `deal_financials`: `revenue` + `ebitda_adj` (is_adjusted=1) for each historical year (period_type='annual')
- `deal_financials`: `ev_at_closing`, `ev_anticipated_earnout`, `ev_total`, `net_cash_debt`, `equity_value` (period_type='point_in_time', fiscal_year=NULL)
- `deal_valuations`: `ev_mid`, `ev_high`, `earnout_max`, `ebitda_basis`, `ebitda_basis_label`, `multiple_mid`, `earnout_structure`
- `deals`: `bp_2026_rev_k`, `bp_2026_ebitda_k`, `maxeo_2026_ebitda_k`, `proj_topline_growth_pct`, `proj_ebitda_margin_pct`
- `deal_commercial`: `category='service_split'` + `category='customers'` rows
- `deal_customers`: top-10 rows per year with `rank`, `revenue_k`, `revenue_pct`

### Re-populate safely
Use the idempotent pattern: DELETE the specific (line_item, fiscal_year) rows you are replacing, then INSERT. Never DELETE all rows for a domain — only target the specific items being updated. See `tmp_build_mouse_onepager.py` (Mouse, 2026-06-18) as a working example.

---

## 8. PPTX template fill (when producing slides)

- Always copy from template `config/golden/onepager/260504_Repuro_Deal_Onepagers_v4.pptx` — never create from scratch
- Preferred source slides: Wolf (v4 slide 7) for simple onepager; Octopus (slide 10) if pie charts needed
- Match shapes by position, not by name — names are inconsistent across slides
- Scan for offscreen shapes (Left < 0) before external distribution — the pipeline table on slide 3 contains real company names
- Scan for yellow (#FFFF00) shapes before external distribution — these are editorial WIP markers
- The Q2 bar chart (WMF/PNG) cannot be auto-generated — it is a think-cell export; accept image file path as input
- Set `onepager_*_approved=1` per quadrant in the DB before including in an investor deck

Full PPTX spec: `ai/golden-spec/SPEC-ONEPAGER.md`
