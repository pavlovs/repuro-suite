# Service Portfolio & Customer Structure (Q4) — Generation Guide

## Purpose
What the company sells, to whom, and where. Investors use this quadrant to assess revenue quality, customer base diversity, and business model defensibility. It complements the financial headline in Q1 with the underlying commercial logic.

## Output format
- Bullet count: 3-5
- Length per bullet: 1-2 sentences max
- Language: English (German product/regulatory terms acceptable: Medizinprodukte, MDR, Hilfsmittel, Verbrauchsmaterialien, Sprechstundenbedarf)
- Tone: Descriptive and factual. Quantify wherever data supports it. No marketing language.
- Formatting: Bold the key commercial metric or category label in each bullet.

## Topics to cover
1. **Core product/service offering** — what the company distributes or provides; product categories by revenue weight if known (e.g., consumables vs. capital equipment, distribution vs. service/repair)
2. **Customer structure** — customer count, customer type breakdown (hospital, ambulatory practice, pharmacy, care home, etc.), and concentration metrics (top-3 or top-5 %)
3. **Recurring revenue** — recurring share (%), contract types if known (framework agreements, Sprechstundenbedarf contracts), or repeat-purchase dynamics
4. **Geographic footprint** — region(s) served, logistics hub location if relevant, any national vs. regional positioning
5. *(Optional)* **Regulatory or certification differentiator** — MDR Class I/II/III authorization, quality certifications, specialist accreditations that create a barrier to entry or switching cost

## Data sources
The generator will have access to the following fields:

| Field | Source table/column |
|-------|---------------------|
| Services / product text | ALLEX `leistung_text` |
| Region | ALLEX `region` |
| Legal form | ALLEX `rechtsform` |
| Product mix / revenue split | `deal_commercial.product_mix` (JSON: label + pct) |
| Customer segments | `deal_commercial.customer_segments` (JSON: type + pct) |
| Customer concentration | `deal_commercial.customer_concentration` (top-N %) |
| Active customer count | `deal_commercial.active_customers` |
| Recurring revenue % | `deal_commercial.recurring_pct` |
| Top supplier concentration | `deal_commercial.supplier_concentration` |
| Geography / logistics hub | `deals.description`, `deal_data.geography` |
| Certifications / accreditations | `deal_commercial.certifications` |
| Revenue split (for pie chart) | `deal_data.revenue_split` (JSON: label + pct) — same data as Q2 pie chart |

## Example bullets

- **Core offering: distribution of medical consumables** (wound care, hygiene, disposables) and capital equipment (OR instruments, sterilization systems), with consumables representing ~65% of Gesamtleistung.
- **~180 active accounts** across hospitals (45%), ambulatory practices (35%), and pharmacies (20%); **top-3 customers account for 8%** of revenue — low concentration relative to sector peers.
- **62% recurring revenue share** driven by framework agreements with hospital procurement and Sprechstundenbedarf contracts with ambulatory practices; low churn historically.
- **Geographic focus: Lower Saxony and Hamburg**, with logistics operations from Hanover; no current presence in southern Germany — adjacent market expansion opportunity.
- **MDR 2017/745 authorized distributor** for Class I–III medical devices; regulatory approval is a meaningful barrier for new entrants in the hospital supply segment.

## Constraints
- Never describe product categories not supported by the available data (leistung_text, product_mix, or description). If product mix is unknown, describe the general category only.
- Customer segment percentages must come from `deal_commercial.customer_segments` — do not estimate splits from the business description alone.
- If `customer_concentration` data is missing, omit the concentration metric — do not estimate "low" or "high" without a number.
- Revenue split percentages in Q4 bullets must be consistent with the pie chart data in Q2 (same `revenue_split` source) — never generate contradictory numbers across quadrants.
- Do NOT include valuation or deal process information in Q4 — that belongs in Q1 (valuation) and Q3 (process).
- Geographic footprint must be specific (state, region, or city level) — "Germany" alone is not acceptable unless the business genuinely has national coverage.
- Regulatory bullet is optional — only include if certification data is available and the certification is commercially meaningful (creates switching cost or market access barrier). Do not add MDR boilerplate for all deals.
- Maximum 5 bullets. If content overflows, prioritize: product offering > customer structure > recurring revenue > geography > certifications.
