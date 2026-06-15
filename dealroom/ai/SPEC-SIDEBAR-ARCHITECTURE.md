# SPEC: Sidebar Architecture — IC Memorandum Structure

Redesigns the DEALROOM dashboard sidebar from ad-hoc tabs into a structured **Investment Committee (IC) Memorandum**, mapping sections to the standard IC documentation chapters used in German PE deal approvals.

**Upstream**: DR-M4 (dashboard), DR-M8 (overview), DR-M9 (investor cockpit), DR-SV2 (schema v2), DR-GC (golden corpus), SPEC-FINANCIALS-TAB.md (P&L), SPEC-INVESTOR-COCKPIT.md (one-pager).

---

## 1. Navigation Architecture

Three visual blocks separated by `sidebar-divider` elements. Section numbering follows IC memo chapters.

```
SIDEBAR (200px, bg-sidebar)
─────────────────────────────────────
  BLOCK A — Deal Economics
─────────────────────────────────────
  1. One-Pager              [PARTIAL]
  2. Overview               [PARTIAL]
  3. Deal History            [SOON]
  4. Valuation & Financials  [PARTIAL]
  5. Offer & Negotiation     [PARTIAL]
─────────────────────────────────────
  BLOCK B — Business Fundamentals
─────────────────────────────────────
  6. Business Model          [SOON]
  7. Customers & Suppliers   [PARTIAL]
  8. Employees               [SOON]
  9. Thesis & Fit            [SOON]
 10. Market & Competition    [SOON]
─────────────────────────────────────
  BLOCK C — Process Artifacts
─────────────────────────────────────
 11. RFI                     [DONE]
 12. Due Diligence           [PARTIAL]
 13. Documents               [DONE]
 14. Notes                   [DONE]
```

### Block headers
Small caps, `font-size: 10px`, `color: #64748b`, `padding: 6px 16px 2px`, not clickable. Separators above each header.

### Status badges
Replace the current `stub`/count badge logic. Tags render as:
- `[DONE]` — no badge (clean)
- `[PARTIAL]` — teal dot indicator, `background: var(--accent)`
- `[SOON]` — grey italic "soon" badge (existing style)

Count badges (open RFI count, doc count, note count) continue to render alongside status where applicable.

---

## 2. Section-by-Section Wireframe

### 1. One-Pager [PARTIAL]

**IC chapter**: Executive Summary (condensed)
**Spec**: SPEC-INVESTOR-COCKPIT.md (DR-M9)
**Data**: `deals.*`, `deal_financials`, `deal_valuations`, `deal_commercial`, `allex.company_records`

```
+------------------------------------------+
| [Code] One-Pager          [Stage] [Days] |
| [Title — editable]                       |
+--------------------+---------------------+
| Q1: EXEC SUMMARY   | Q2: FINANCIALS      |
| - 5-6 bullets       | Bar chart (rev+     |
|   [editable]        |   EBITDA by year)   |
|             [More]  | Key metrics row     |
+--------------------+---------------------+
| Q3: PROCESS/STATUS  | Q4: SERVICE PORT.   |
| - 5-6 bullets       | - 5-6 bullets       |
|   [editable]        |   [editable]        |
+--------------------+---------------------+
| Footnote: As of... | Financials: FY2024A |
+------------------------------------------+
```

**Exists today**: Q2 chart rendering works. Portfolio stage filter works. Quadrant layout renders.
**Gaps**: Q1/Q3/Q4 auto-generation not built (`draft-onepager` command). Approval gate UI not built. PPTX export separate scope.

---

### 2. Overview [PARTIAL]

**IC chapter**: Organisation (4)
**Spec**: DR-M8
**Data**: `deals.*`, `allex.company_records`, `deal_contacts`

```
+------------------------------------------+
| COMPANY FACTS          | MAP (Leaflet)    |
| Name, sector, location | EBITDA-sized     |
| Founded, employees     | circle marker    |
| Website, domain        |                  |
+------------------------+------------------+
| SHAREHOLDER / SELLER PROFILE              |
| Name, age, role, motivation, profile notes|
+------------------------------------------+
| INVESTMENT THESIS (editable)              |
+------------------------------------------+
| CONTACT REGISTRY (deal_contacts)          |
| Role | Name | Email | Phone              |
+------------------------------------------+
```

**Exists today**: Company facts, map, financial timeline, seller profile (DR-M8). Investment thesis display.
**Gaps**: `deal_contacts` stakeholder registry not rendered (table exists, no view). Contact data sparse across deals.

---

### 3. Current Status / Deal History [SOON]

**IC chapter**: Prozess und Zeitleiste (10)
**Data**: `deal_notes`, `deal_meetings`, `deal_emails`, `deals.deal_stage`, `deals.stage_entered_at`

```
+------------------------------------------+
| STAGE TIMELINE                            |
| nda ──► valuation ──► offer ──► ...       |
|    12d      45d        ●23d               |
+------------------------------------------+
| RECENT ACTIVITY (reverse chron)           |
| [date] [type-icon] Meeting: ...           |
| [date] [type-icon] Email sent: ...        |
| [date] [type-icon] Note: ...              |
| [date] [type-icon] Stage change: ...      |
+------------------------------------------+
| OPEN ACTIONS / BLOCKERS                   |
| - [ ] RFI answer pending (14d)            |
| - [ ] Seller callback scheduled           |
+------------------------------------------+
```

**Exists today**: Nothing rendered. `deal_notes` and stage data exist in DB.
**Gaps**: Stage history not tracked (only current stage + `stage_entered_at`). Granola/HubSpot sync not built (DR-M11 deferred). `deal_meetings` empty for most deals. Unified activity feed requires merging `deal_notes` + `deal_meetings` + `deal_emails`. Need `deal_stage_history` table or log.

---

### 4. Valuation & Financials [PARTIAL]

**IC chapter**: Finanzen (8)
**Spec**: SPEC-FINANCIALS-TAB.md (DR-M9b)
**Data**: `deal_financials`, `deal_valuations`, `deal_model_params`

```
+------------------------------------------+
| [GuV] [Bilanz] [Bewertung]   subtab bar  |
+------------------------------------------+
| GuV subtab (P&L) — SPEC-FINANCIALS-TAB   |
| Compact P&L with A/B suffixes, CT, CAGR, |
| comment column, 3-layer drill-down,       |
| collapsible adjustment bridge, entity     |
| toggle for multi-company deals            |
+------------------------------------------+
| Bilanz subtab (balance sheet)             |
| Aktiva / Passiva table by year            |
| Key ratios: EK-Quote, Working Capital     |
+------------------------------------------+
| Bewertung subtab (valuation)              |
| EV waterfall: EBITDA basis → adj → mult   |
| Scenario table: low / mid / high          |
| Deal structure: Sofort / RB / EO split    |
| Earn-out matrix (from DR-M7)              |
+------------------------------------------+
```

**Exists today**: GuV (P&L) subtab is [DONE] per SPEC-FINANCIALS-TAB.md. Offer round ledger exists. DR-M7 valuation engine works.
**Gaps**: Bilanz view [SOON] — `deal_financials WHERE statement='balance'` has data but no dedicated rendering. Bewertung view [SOON] — `deal_valuations` + `deal_model_params` have data, DR-M7 model tab exists but not integrated into this subtab structure.

**Note**: P&L is feature-complete and must not be redesigned. Only Bilanz and Bewertung subtabs need building.

---

### 5. Offer & Negotiation History [PARTIAL]

**IC chapter**: Prozess und Zeitleiste (10) — offer subset
**Data**: `deal_valuations`, `deal_questions WHERE category='negotiation'`, `deal_notes`

```
+------------------------------------------+
| OFFER ROUND LEDGER                        |
| Rnd | Date  | EV   | Sofort | RB  | EO  |
|  1  | 03/26 | 4.2M | 2.8M   | 15% | 0.6M|
|  2  | 04/26 | 4.5M | 3.0M   | 15% | 0.7M|
+------------------------------------------+
| NEGOTIATION POINTS / ISSUE LIST           |
| # | Topic          | Repuro | Seller | Δ |
| 1 | GF salary adj. | 120K   | 150K   |30K|
| 2 | EO trigger     | EBITDA | Rev    | — |
+------------------------------------------+
| SELLER COUNTER-POSITIONS (from Granola)   |
| [reverse chron notes from meetings]       |
+------------------------------------------+
```

**Exists today**: Offer round ledger renders from `deal_valuations` (offer tab, marked 'stub' but data flows). EV waterfall in DR-M7.
**Gaps**: Issue list / negotiation points [SOON] — no structured storage. Would need `deal_negotiation_items` table or repurpose `deal_questions` with `category='negotiation'`. Seller counter-positions depend on DR-M11 (Granola sync, deferred).

---

### 6. Business Model [SOON]

**IC chapter**: Geschaeftsmodell (3)
**Data**: `deal_commercial`, `deal_backlog`, `deals.investment_thesis`

```
+------------------------------------------+
| SERVICE PORTFOLIO                         |
| - Service line 1: description, rev share  |
| - Service line 2: description, rev share  |
+------------------------------------------+
| KEY KPIs                                  |
| Recurring rev %  | 45%                   |
| Avg order value  | 12K                   |
| Order backlog    | 2.1M (from backlog)   |
+------------------------------------------+
| BUSINESS MODEL NARRATIVE                  |
| [from deals.investment_thesis or          |
|  deal_commercial free text]               |
+------------------------------------------+
```

**Exists today**: `deal_commercial` has some KPIs (category: revenue, customers, recurring, backlog). `deal_backlog` table exists with data for some deals.
**Gaps**: No dedicated view. Service line breakdown not structured in DB — lives in free text or `deal_commercial` rows. Need to aggregate existing `deal_commercial` rows by category and render.

---

### 7. Customers & Suppliers [PARTIAL]

**IC chapter**: Kunden (6)
**Data**: `deal_customers`, `deal_suppliers`, `deal_commercial`

```
+------------------------------------------+
| [Customers] [Suppliers]       subtab bar  |
+------------------------------------------+
| CUSTOMER CONCENTRATION (top 10)           |
| Rank | Name     | Rev K | Share | Cohort  |
| 1    | Klinikum | 890   | 15.3% | 2018   |
| ...                                       |
| Top 3: 38% | Top 10: 62%    [computed]    |
+------------------------------------------+
| SUPPLIER CONCENTRATION                    |
| Rank | Name     | Cost K | Share | Excl.  |
| 1    | Medline  | 1.200  | 22%   | No     |
+------------------------------------------+
```

**Exists today**: `deal_customers` table rendered with per-customer per-year data (current Customers tab).
**Gaps**: Suppliers subtab [SOON] — `deal_suppliers` table exists in schema but empty across all deals. Concentration metrics (top 3/10 share) not computed in current view.

---

### 8. Employees [SOON]

**IC chapter**: Organisation (4) — personnel subset
**Data**: `deal_employees`, `deal_commercial WHERE category='operational'`

```
+------------------------------------------+
| HEADCOUNT SUMMARY                         |
| Total: 45 | FTE: 42.5 | Avg tenure: 6.2y|
+------------------------------------------+
| PERSONNEL REGISTER (anonymized)           |
| # | Dept       | Role    | FTE | Tenure  |
| 1 | Vertrieb   | Sales   | 1.0 | 8y      |
| 2 | Lager      | Ops     | 1.0 | 3y      |
+------------------------------------------+
| KEY PERSON RISK                           |
| [Flag if GF/owner is >60 or single dep.] |
+------------------------------------------+
```

**Exists today**: `deal_employees` table in schema with columns for role, department, compensation.
**Gaps**: No data populated for any deal. No view. Employee data typically arrives via RFI answer or management presentation — ingestion path not built.

---

### 9. Investment Thesis & Fit [SOON]

**IC chapter**: SWOT-Analyse (1) + Kriterienkatalog (2) + Rational fuer Transaktion (9)
**Data**: `deals.investment_thesis`, `deal_scorecard_config`, `deal_scorecard_results`, `deal_commercial`

```
+------------------------------------------+
| SWOT MATRIX                              |
| Strengths        | Weaknesses            |
| - High recurring | - Owner dependency    |
| Opportunities    | Threats               |
| - Cross-sell     | - Reimbursement cuts  |
+------------------------------------------+
| SCORECARD (11 metrics)                   |
| Metric          | Value | G/Y/R | Trend  |
| Rev CAGR        | 8.2%  |  G    |  ↑     |
| EBITDA margin   | 14.1% |  Y    |  →     |
| Recurring %     | 45%   |  Y    |  ↑     |
| Cust. conc.     | 38%   |  R    |  →     |
| ...                                      |
+------------------------------------------+
| STRATEGIC RATIONALE                      |
| [from deals.investment_thesis, editable] |
+------------------------------------------+
```

**Exists today**: `deals.investment_thesis` stores free text. `deal_scorecard_config` has 11 default metrics with green/yellow/red thresholds. `deal_scorecard_results` table exists.
**Gaps**: No view for scorecard. SWOT not stored — would need `deals.swot_json` or similar. Scorecard computation logic exists in `db.py` but results not rendered in dashboard. Strategic rationale overlaps with Overview — may consolidate.

---

### 10. Market & Competition [SOON]

**IC chapter**: Markt (5)
**Data**: `deal_competitors`, `deal_commercial WHERE category='market'`

```
+------------------------------------------+
| COMPETITIVE LANDSCAPE                     |
| Company     | Est Rev | Segment | Overlap |
| Competitor1 | 12M     | Distrib | High    |
| Competitor2 | 8M      | Direct  | Low     |
+------------------------------------------+
| MARKET CONTEXT                            |
| TAM / SAM estimate (if available)        |
| Regulatory environment notes             |
| Growth drivers / headwinds               |
+------------------------------------------+
```

**Exists today**: `deal_competitors` table in schema.
**Gaps**: Table empty across all deals. No view. Market context data (`deal_commercial WHERE category='market'`) sparse. DR-M17 (outside-in canvas) was designed to populate this but is deferred.

---

### 11. RFI [DONE]

**IC chapter**: n/a (process artifact)
**Spec**: DR-M6
**Data**: `deal_questions`

```
+------------------------------------------+
| RFI QUESTIONS                             |
| Category | Question        | Status | Imp |
| Fin      | Revenue split?  | open   | H   |
| Comm     | Top 10 cust.?   | sent   | H   |
| ...                                       |
| Open: 3 | Sent: 5 | Answered: 12         |
+------------------------------------------+
```

**Exists today**: Full rendering. Questions grouped by category/subcategory. Status badges. Open count in sidebar.
**Gaps**: None — feature-complete.

---

### 12. Due Diligence [PARTIAL]

**IC chapter**: n/a (process artifact)
**Spec**: DR-M14 (deferred)
**Data**: `deal_dd_items`

```
+------------------------------------------+
| DD CHECKLIST                              |
| Category | Item           | Status | Risk |
| FDD      | P&L audit      | open   | med  |
| TDD      | IT assessment  | n/a    | low  |
| ...                                       |
| Gap analysis vs. deal_documents           |
+------------------------------------------+
```

**Exists today**: `deal_dd_items` table exists with category, status, risk_level columns. Basic stub view.
**Gaps**: No data populated — no deal has reached DD stage. DR-M14 (DD Package generator) deferred. View is a stub that shows "coming soon".

---

### 13. Documents [DONE]

**IC chapter**: n/a (process artifact)
**Spec**: DR-M2
**Data**: `deal_documents`

```
+------------------------------------------+
| DOCUMENT REGISTRY                         |
| Type    | Name           | Status | Date  |
| model   | 260505_v7.xlsx | draft  | 05/26 |
| nda     | NDA_signed.pdf | signed | 01/26 |
| ...                                       |
| Grouped by doc_type, sorted by date       |
+------------------------------------------+
```

**Exists today**: Full rendering. Documents grouped by type, status badges, file links.
**Gaps**: None — feature-complete.

---

### 14. Notes [DONE]

**IC chapter**: n/a (process artifact)
**Data**: `deal_notes`

```
+------------------------------------------+
| NOTES (reverse chronological)             |
| [2026-05-20] Roman: Called seller...      |
| [2026-05-18] System: Stage → offer        |
| ...                                       |
| [+ Add note] input                        |
+------------------------------------------+
```

**Exists today**: Full rendering. Timestamped notes, newest first. Add note input in serve mode.
**Gaps**: None — feature-complete.

---

## 3. DB Schema Implications

### New tables needed

| Table | Purpose | Milestone |
|-------|---------|-----------|
| `deal_stage_history` | Track stage transitions (from, to, timestamp, trigger) for Section 3 timeline | Section 3 build |
| `deal_negotiation_items` | Structured issue list for Section 5 (topic, repuro_position, seller_position, delta, status) | Section 5 build |

### New columns needed

| Table | Column | Type | Purpose |
|-------|--------|------|---------|
| `deals` | `swot_json` | TEXT | JSON `{strengths:[], weaknesses:[], opportunities:[], threats:[]}` for Section 9 |

### Existing tables — sufficient but empty

| Table | Has schema | Has data | Needs ingestion path |
|-------|-----------|----------|---------------------|
| `deal_employees` | Yes | No | RFI answers, management presentations |
| `deal_suppliers` | Yes | No | RFI answers |
| `deal_competitors` | Yes | No | DR-M17 (deferred) or manual entry |
| `deal_scorecard_results` | Yes | Partial | Scorecard computation in `db.py`, needs dashboard trigger |
| `deal_backlog` | Yes | Partial | Commercial extraction (DR-GC Phase 2) |

### Existing tables — sufficient, data present

| Table | Used by section |
|-------|----------------|
| `deal_financials` | 4 (P&L [DONE], Bilanz, Bewertung) |
| `deal_valuations` | 4, 5 |
| `deal_customers` | 7 |
| `deal_commercial` | 6, 7, 9, 10 |
| `deal_questions` | 11 |
| `deal_dd_items` | 12 |
| `deal_documents` | 13 |
| `deal_notes` | 14, 3 |
| `deal_contacts` | 2 |
| `deal_scorecard_config` | 9 |
| `deal_model_params` | 4 |

---

## 4. Cross-References

| Spec | Sections affected | Relationship |
|------|-------------------|-------------|
| SPEC-INVESTOR-COCKPIT.md | 1 (One-Pager) | Governs Q1-Q4 layout, stage filter, drill-down. This spec inherits, does not override. |
| SPEC-FINANCIALS-TAB.md | 4 (GuV subtab) | Governs P&L rendering. [DONE] — do not touch. Bilanz + Bewertung subtabs are new scope. |
| ARCHITECTURE.md | All | Schema reference for all 22+ tables. |
| DEAL_WORKFLOW_SPEC.md | 3, 5 | Stage transitions and gate checks inform Deal History and Offer sections. |
| DEAL_DELIVERABLES_SPEC.md | 4, 5, 9 | Stage 2-3 deliverable definitions overlap with Valuation, Offer, Thesis sections. |
| golden-spec/SPEC-MODEL.md | 4 (Bewertung) | Model reader constraints apply to valuation data display. |
| golden-spec/SPEC-OFFER.md | 5 | Offer generation patterns inform negotiation history structure. |

### Migration from current sidebar

| Current tab | Maps to new section | Changes |
|-------------|-------------------|---------|
| One-Pager | 1. One-Pager | No change |
| Overview | 2. Overview | Add `deal_contacts` rendering |
| Financials | 4. Valuation & Financials | Add Bilanz + Bewertung subtabs |
| Customers | 7. Customers & Suppliers | Add Suppliers subtab |
| Offer | 5. Offer & Negotiation | Expand from stub to negotiation tracker |
| RFI | 11. RFI | No change |
| Due Diligence | 12. Due Diligence | No change (remains stub until DR-M14) |
| Documents | 13. Documents | No change |
| Notes | 14. Notes | No change |
| Risk Flags | Removed as standalone | Flags integrated into relevant sections (Financials, Thesis) |
| *(new)* | 3. Deal History | New section |
| *(new)* | 6. Business Model | New section |
| *(new)* | 8. Employees | New section |
| *(new)* | 9. Thesis & Fit | New section |
| *(new)* | 10. Market & Competition | New section |

---

## 5. Implementation Priority

Sections ranked by value-to-effort for milestone planning:

| Priority | Section | Rationale |
|----------|---------|-----------|
| P0 | Sidebar restructure (navigation only) | Zero data work — just rearrange `renderSidebar()` with block headers and dividers. Ships the IC structure immediately. |
| P0 | 4. Bilanz subtab | `deal_financials WHERE statement='balance'` has data. Rendering only. |
| P0 | 4. Bewertung subtab | `deal_valuations` + `deal_model_params` have data. DR-M7 model tab logic can be reused. |
| P1 | 9. Thesis & Fit — scorecard only | `deal_scorecard_config` + computation already in `db.py`. Render green/yellow/red table. |
| P1 | 5. Offer — expand from stub | Offer round ledger data exists. Issue list is new scope. |
| P1 | 2. Overview — add contacts | `deal_contacts` table exists, just needs rendering. |
| P2 | 3. Deal History | Requires `deal_stage_history` table + unified activity feed. Medium scope. |
| P2 | 6. Business Model | Requires aggregating `deal_commercial` by category. Low data density currently. |
| P3 | 7. Suppliers subtab | Table empty — needs data first. |
| P3 | 8. Employees | Table empty — needs data first. |
| P3 | 10. Market & Competition | Table empty — needs DR-M17 or manual entry. |
| P3 | 9. SWOT matrix | Needs `swot_json` column + manual entry UI. Low urgency. |
