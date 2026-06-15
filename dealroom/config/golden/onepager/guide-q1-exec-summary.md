# Executive Summary (Q1) — Generation Guide

## Purpose
Brief company overview and investment highlights for investor meetings. This is the first quadrant investors read — it must deliver the deal thesis in 4-6 scannable bullets without requiring them to ask follow-up questions.

## Output format
- Bullet count: 4-6
- Length per bullet: 1-2 sentences max
- Language: English (German domain terms acceptable: Gesamtleistung, Sofortzahlung, Medizinprodukte, GmbH, GmbH & Co. KG)
- Tone: Factual, investor-ready, no marketing language. State numbers, not adjectives.
- Formatting: Bold the key claim/metric in each bullet. Supporting detail in regular weight.

## Topics to cover
1. **Company description** — what it does, for whom, in which geography (1 sentence, grounded in actual business)
2. **Financial headline** — revenue (Gesamtleistung) + adj. EBITDA + margin for most recent full year; revenue CAGR if meaningful
3. **Revenue quality** — recurring revenue share, customer concentration (top-3 or top-5 %), or other cash flow quality signal
4. **Valuation structure** — EV at closing (M€, EBITDA multiple), earn-out if applicable
5. **Strategic fit** — how it fits Repuro's buy-and-build thesis: anchor vs. add-on, region, product adjacency, or capability being acquired
6. *(Optional)* Notable differentiator or risk mitigant not captured above (e.g., owner staying on, no customer cliff, MDR certification)

## Data sources
The generator will have access to the following fields:

| Field | Source table/column |
|-------|---------------------|
| Company name (legal + codename) | `deals.legal_name`, `deals.code_name` |
| Business description | `deals.description`, `deals.investment_thesis` |
| Revenue (Gesamtleistung) | `deal_data.revenue_latest`, `deal_valuations.revenue` |
| Adj. EBITDA | `deal_data.ebitda_latest`, `deal_valuations.ebitda` |
| EBITDA margin % | Computed: ebitda / revenue |
| Revenue CAGR | `deal_data.revenue_cagr` or computed from historicals |
| Revenue year | `deal_data.revenue_year` |
| EV at closing (M€) | `deal_valuations.ev_closing` |
| EV multiple | `deal_valuations.ev_closing_mult` |
| Earn-out (max, M€) | `deal_valuations.earn_out_max` |
| EV incl. earn-out + multiple | `deal_valuations.ev_incl_eo`, `deal_valuations.ev_incl_eo_mult` |
| Employees | `deal_data.employees` |
| Customer concentration | `deal_commercial.customer_concentration` |
| Recurring revenue % | `deal_commercial.recurring_pct` |
| Services / product lines | ALLEX `leistung_text`, `deal_commercial.product_mix` |
| Region / geography | ALLEX `region`, `deal_data.geography` |
| Strategic fit narrative | `deals.strategic_fit` |

## Example bullets

- **Fox is a regional distributor of medical devices and surgical instruments** in Lower Saxony, generating €3.2m Gesamtleistung (FY2025A) with a lean two-person sales structure and owner-operated since 2009.
- **Adj. EBITDA of €380k (11.9% margin)** with 4.2% revenue CAGR (2023–2025), demonstrating stable organic growth in a non-cyclical niche.
- **Low customer concentration** (top-3: 8%) and 62% recurring revenue share indicate predictable cash flow with no single-customer cliff.
- **EV at closing: €1.4m (3.7x 2025A EBITDA)**, with a further earn-out of up to €0.5m tied to FY2026 EBITDA — total EV €1.9m (5.0x).
- **Strategic fit**: add-on acquisition for Repuro's Northern Germany hub; adds hospital channel access and OR instrument portfolio not currently covered by the platform.

## Constraints
- Never use adjectives without a number to back them up: "strong growth" is not acceptable; "4.2% CAGR" is.
- Never include the real company legal name if the slide uses a codename — use the codename in the company description bullet.
- Never fabricate financials — if a field is null or missing, omit the bullet or mark it `[DATA MISSING]`.
- Valuation bullet must reflect the actual deal_valuations DB record, not an estimate.
- Strategic fit must reference Repuro's thesis specifically (anchor vs. add-on, regional logic, product gap being filled) — generic "fits our strategy" is not acceptable.
- EBITDA multiple format: always `X.Xx {year}A/P EBITDA` (e.g., "3.7x 2025A EBITDA").
- Revenue format: `€X.Xm` (one decimal, lowercase m for million).
- If earn-out exists: state Sofortzahlung (closing payment) and max EO separately. Never blend them into a single EV without disclosure.
- Maximum 6 bullets. If content overflows, cut — do not expand bullet length.
