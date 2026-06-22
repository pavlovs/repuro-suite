# CDD Slide Map — Databook to Presentation

Maps CDD Databook findings to a structured presentation for internal decision-making (Investment Committee / partner alignment). Not for external sharing.

## Slide Deck Structure (12–15 slides)

### Slide 1: Cover
- Project {CODENAME} — Commercial Due Diligence
- Date, confidentiality notice
- Source: `Summary` tab title

### Slide 2: Executive Summary (1 slide)
- 4 verdict bullets from `Summary B6:B9`
- Traffic-light signal: proceed / proceed with conditions / walk away
- Source: `Summary` → "Answer first"

### Slide 3: Red Flags (1 slide)
- Table: # | Finding | So What | Severity
- Direct lift from `Summary C14:E20`
- Color-code: HIGH=red, MEDIUM=amber, LOW=grey

### Slide 4: Revenue Overview (1 slide)
- Revenue by segment table (3-year + YTD)
- YoY growth rates and CAGR
- GuV reconciliation delta (one line: "ties within X%")
- Source: `Revenue Analysis` rows 12–29
- Chart: stacked bar from `Charts` tab

### Slide 5: Revenue Deep Dive — Segments (1 slide)
- Top 3 segments: trend, driver, risk
- Key findings 1-5 from `Revenue Analysis B5:B9`
- Chart: segment trend lines from `Charts` tab

### Slide 6: Gross Margin by Segment (1 slide)
- GM% by segment × year table
- Flag: what "Rohertrag" means for this target (materials-only vs full)
- Source: `Revenue Analysis` rows 32–43

### Slide 7: Customer Concentration (1 slide)
- Top 3/5/10/20 concentration table
- Pie chart or bar: Top 20 vs rest
- Source: `Customer Analysis` rows 12–18
- Chart from `Charts` tab

### Slide 8: Customer Type Split (1 slide)
- Revenue by customer type × year
- Highlight volatile channels (e.g., dealer, project business)
- Source: `Customer Analysis` rows 22–29

### Slide 9: Cohort Analysis (1 slide)
- Revenue by first-revenue cohort × year
- Highlight: base cohort dominance, new cohort degradation
- NRR and logo retention metrics
- Source: `Cohort Analysis` rows 16–24, 28–31

### Slide 10: Churn & Revenue Bridge (1 slide)
- Revenue bridge waterfall: Start → Churned → Net retained → New → End
- Churn rate by year (logo and revenue)
- Source: `Churn Analysis` rows 10–15 (churn), 26–30 (bridge)
- Chart: waterfall from `Charts` tab

### Slide 11: Supplier Analysis (1 slide)
- Top supplier concentration
- Single-source dependencies flagged
- Contract terms / switching risk
- Source: `Supplier Analysis` tab

### Slide 12: Personnel Overview (1 slide)
- Headcount trend, cost per FTE
- Key person dependencies
- Turnover / tenure distribution
- Source: `Personnel Overview` tab

### Slide 13: P&L Quality / EBIT Bridge (1–2 slides)
- Reported EBIT → Adjusted EBIT → Pro-forma EBIT
- Each adjustment: amount, direction, verified/unverified
- GF salary normalization detail
- Margin trajectory table
- Source: `P&L Quality` tab

### Slide 14: Data Gaps & Confidence (1 slide)
- Two-column layout: gaps (left) + confidence by analysis (right)
- Direct lift from `Gaps and Confidence` tab
- Color-code confidence: HIGH=green, MEDIUM=amber, LOW=red

### Slide 15: Open Items / RFI Summary (1 slide)
- Top 5 open RFI questions (from `CDD_RFI_Fragenliste`)
- Status: answered / outstanding / partially answered
- Next steps and timeline for management session

## Chart Mapping

| Slide | Chart needed | Source tab | Source range |
|-------|-------------|-----------|-------------|
| 4 | Stacked bar: revenue by segment by year | Charts | Revenue segment chart |
| 5 | Line: top segment trends | Charts | Segment trend lines |
| 7 | Pie/bar: Top 20 vs rest | Charts | Concentration chart |
| 10 | Waterfall: revenue bridge | Charts | Bridge waterfall |

## Production Notes

- **Current constraint**: PPT MCP = M4 (not yet built). Slides are produced manually or via a future PPT automation milestone.
- **Interim workflow**: Export charts from Excel (Charts tab is PowerPoint-ready per Mantis v4 pattern). Paste into slide deck. Fill text from databook findings.
- **House style**: Arial (slides/docs), Aptos Narrow (Excel only). Teal #0891B2 headers, white background, minimal text per slide. Numbers in EUR k, format `#,##0.0` with parens for negatives, dash for zero. Logo: `colorwithname_whitebg.png` on cover slide.
- **Audience**: Internal — Roman + Flo for investment decision. Not shared with sellers or advisors.
