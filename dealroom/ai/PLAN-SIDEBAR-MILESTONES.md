# PLAN: Sidebar Architecture — Milestone Breakdown

Last updated: 2026-05-21. Covers the restructuring of the deal workspace sidebar into an Interactive IC Memorandum with 14 sections across 3 blocks.

**Constraint**: Financial P&L tab is DONE (SPEC-FINANCIALS-TAB.md). No redesign. Gaps are Bilanz view and Valuation view.

---

## Priority Order

| Milestone | Name | Delivers | Depends On | Priority | Status |
|-----------|------|----------|------------|----------|--------|
| DR-M18 | Bilanz + Valuation Views | Balance sheet tab, dedicated valuation tab (model outputs, EV scenarios, multiples) | DR-M9 (layout) | P0 | ⬜ |
| DR-M19 | Sidebar Reorganization | 3-block sidebar (Deal Economics / Business Fundamentals / Process Artifacts), section separators, 14-item nav | DR-M9 | P1 | ⬜ |
| DR-M20 | Business Model + Investment Thesis | Business Model section view, Investment Thesis & Fit (SWOT, scorecard) | DR-M19 | P1 | ⬜ |
| DR-M8b | Offer & Negotiation (expanded) | Indicative offer generator + issue/negotiation list view | DR-M19, DR-GC | P1 | ⬜ |
| DR-M21 | Employees + Suppliers + Market | Employee view, supplier table, market & competition section | DR-M19 | P2 | ⬜ |
| DR-M13 | Cross-Deal Benchmarking | Portfolio-wide comparison view; feeds scorecard in Investment Thesis | DR-M18 (valuation data) | P2 | ⬜ |
| DR-M22 | Deal History + Stage Tracking | Deal History / Current Status section with timeline, stage log, contact log | DR-M19 | P3 | ⬜ |
| DR-M11 | Granola Sync | Meeting transcripts into deal_meetings; feeds Deal History | DR-M22 | P3 | 🔒 |
| DR-M14 | Due Diligence Package | DD request list generator, gap detection, expanded DD section | DR-M19, DR-GC | P3 | 🔒 |

---

## Milestone Details

### DR-M18 — Bilanz + Valuation Views (P0, ~2 days)

**Why first**: Roman identified these as the two gaps. Both have DB tables with data but no dedicated views.

**Scope**:
1. **Bilanz (Balance Sheet) view** — new subtab under "Valuation & Financials" (section 4)
   - Reads `deal_financials WHERE statement='balance'` — rows exist from DR-M3 extraction
   - Standard structure: Aktiva (assets) / Passiva (liabilities + equity), per fiscal year columns
   - German format (K EUR, dot thousands, parentheses for negatives) — same as P&L
   - Entity toggle (reuse from SPEC-FINANCIALS-TAB.md entity dimension)
   - Drill-down by konto_nr where available (same 3-layer pattern as P&L)
2. **Valuation view** — new subtab under "Valuation & Financials" (section 4)
   - Reads `deal_valuations` — EV scenarios (low/mid/high), implied multiples, deal structure
   - Model output summary: EBITDA basis, normalization bridge (what was adjusted, net effect)
   - EV waterfall: Sofortzahlung + Rückbeteiligung + Earn-out = total EV
   - Multiples comparison: EV/EBITDA, EV/Revenue across scenarios
   - Source model file link (from `deal_valuations.source_model_file`)
   - Not editable — reflects model outputs. "Run `model` to refresh" if stale

**What exists**: Balance sheet data in DB (DR-M3). Valuation data in DB (DR-M5, DR-M7). Model & Valuation tab exists but shows raw adjGuV — this replaces/restructures it.

**AC**: Bilanz tab renders for Cat + Wolf with correct year columns. Valuation tab shows EV scenarios + multiples for any deal with `deal_valuations` rows. Entity toggle works on Bilanz.

---

### DR-M19 — Sidebar Reorganization (P1, ~1 day)

**Why**: Current sidebar is a flat tab list. IC Memo structure requires grouped navigation.

**Scope**:
- Restructure sidebar from flat tabs → 3 blocks with visual separators (thin line + block header):
  - **Block A — Deal Economics**: One-Pager, Overview, Deal History, Valuation & Financials, Offer & Negotiation
  - **Block B — Business Fundamentals**: Business Model, Customers & Suppliers, Employees, Investment Thesis & Fit, Market & Competition
  - **Block C — Process Artifacts**: RFI, Due Diligence, Documents, Notes
- Map existing tabs to new section names (rename only, no content changes):
  - "Overview" = current DR-M8 overview (add shareholder detail placeholder)
  - "Valuation & Financials" = current Financials tab + new Bilanz/Valuation subtabs (DR-M18)
  - "Customers & Suppliers" = current Commercial tab
  - "Documents" = current Documents tab
  - "Notes" = current Notes tab
  - "RFI" = current Open Topics tab
- Sections without content yet show placeholder: "[Section name] — coming in DR-M{N}" with a muted icon
- Sidebar collapse/expand per block (remember state in localStorage)

**What exists**: Flat sidebar with 9 tabs. All get remapped — no tab is lost.

**AC**: All 14 sections visible in sidebar. 3 blocks visually separated. Existing tabs render under new names. Placeholder sections don't crash. Block collapse persists across page loads.

---

### DR-M20 — Business Model + Investment Thesis (P1, ~1.5 days)

**Why**: Core IC memo chapters. Business model = what the company does. Thesis = why we buy it.

**Scope**:
1. **Business Model view** (section 6)
   - Sources: `deals.investment_thesis`, `allex.company_records` (leistung_text, services), `deal_commercial`
   - Sections: company description, service lines, value chain position, revenue model (recurring vs. project), geographic scope
   - Auto-generated draft from deal data (Claude sonnet), editable inline
   - Stored in `deals.business_model_text` (new column)
2. **Investment Thesis & Fit view** (section 9)
   - SWOT matrix (strengths, weaknesses, opportunities, threats) — editable 4-quadrant grid
   - Scorecard: strategic fit, financial quality, growth profile, customer quality, management — 1-5 scale with notes
   - Sources: `deal_scorecard_results` (existing table from DR-SV2), `deal_commercial`, `deal_financials`
   - Cross-deal percentile rank if DR-M13 is done (graceful fallback if not)

**What exists**: `deal_scorecard_config` + `deal_scorecard_results` tables exist (DR-SV2). Internal Deal Screen has a proto-scorecard. SWOT is new. Business Model is new.

**AC**: Business Model section renders with auto-generated content for any deal with ALLEX data. SWOT grid is editable and persisted. Scorecard shows 5 dimensions with fill from existing `deal_scorecard_results`.

---

### DR-M8b — Offer & Negotiation (P1, ~1.5 days)

**Absorbs existing DR-M8b scope** (offer generator) and adds negotiation tracking.

**Scope**:
1. **Offer generator** (original DR-M8b) — `DEALROOM.py draft-offer --deal Cat`
   - Reads `deal_valuations`, company/seller info, offer template from golden corpus
   - Fills: seller names, company, EV components, economic date, Begründungsabsatz
   - Output: `3_Indikatives Angebot/{date}_{code}_Indikatives_Angebot_v{round}_DRAFT.docx`
   - Offer round ledger: `deal_valuations` rows per round
2. **Negotiation / Issue List view** (new, section 5)
   - Open issues table: issue, owner (buyer/seller), status (open/resolved), priority
   - Stored in `deal_questions` with `category='negotiation'` (reuse existing table)
   - Linked to offer rounds — which issues were raised in which round
   - Summary card: total EV, gap to seller ask, key open points count

**What exists**: Offer round ledger in `deal_valuations`. Offer doc generation spec in ROADMAP (DR-M8b). Issue tracking is new.

**AC**: `draft-offer` generates a Word doc from template + deal data. Offer & Negotiation section shows offer history + issue list. Issues are editable inline.

---

### DR-M21 — Employees + Suppliers + Market (P2, ~1.5 days)

**Why P2**: Tables exist in schema but are mostly empty. Views are straightforward once data exists.

**Scope**:
1. **Employees view** (section 8) — reads `deal_employees`, shows: headcount by role/department, key person flags, FTE trend if multi-year data exists. Compact table.
2. **Suppliers view** (added to section 7 "Customers & Suppliers") — reads `deal_suppliers`. Top supplier concentration, dependency risk flags. Currently empty for all deals.
3. **Market & Competition view** (section 10) — reads `deal_competitors`, shows: competitor list, estimated market share, positioning map (manual 2x2 grid). Data-dependent — mostly empty now.

**What exists**: `deal_employees`, `deal_suppliers`, `deal_competitors` tables (DR-SV2). Customer tab already has `deal_customers` rendering. Employees table has some data for Cat/Wolf.

**AC**: Each section renders its respective table. Empty state shows "No data — add via RFI or manual entry" with a clear CTA. Employees view renders for deals with data.

---

### DR-M13 — Cross-Deal Benchmarking (P2, ~1 day)

**Unchanged from ROADMAP** — absorbs into Investment Thesis section as a data source.

**Scope**: `DEALROOM.py bench` compares all deals on: revenue CAGR, gross margin, EBITDA margin, PEX ratio, recurring %, top-3 concentration, implied EV/EBITDA. Output: ranked table in portfolio view + JSON data that DR-M20 Investment Thesis scorecard consumes for percentile ranking.

**What exists**: All data sources exist (`deal_financials`, `deal_commercial`, `deal_valuations`). No view.

**AC**: Benchmark table renders in portfolio view with 7 metrics across all deals with data. Percentile data available for scorecard consumption.

---

### DR-M22 — Deal History + Stage Tracking (P3, ~1 day)

**Why P3**: Depends on DR-M11 (Granola) for full value. Partial version works with stage log alone.

**Scope**:
- Deal History / Current Status section (section 3):
  - Stage log: when deal entered/exited each stage (from `deals.stage_entered_at` + new `deal_stage_log` table)
  - Contact log: last contact date, source (email/meeting/note), days since
  - Meeting summaries: from `deal_meetings` (populated by DR-M11 when ready)
  - HubSpot deal activity link (if HubSpot ID exists)
  - Visual timeline: horizontal stage progression with dates

**What exists**: `deals.stage_entered_at`, `deals.last_contact_at`. `deal_meetings` table (empty until DR-M11). No stage history log.

**AC**: Stage timeline renders with current stage highlighted. Contact log shows last contact. Meeting section shows placeholder until DR-M11. New `deal_stage_log` table tracks stage transitions.

---

### DR-M11 — Granola Sync (P3, unchanged)

Scope unchanged from ROADMAP. Feeds DR-M22 Deal History section with meeting transcripts, data points, and cross-check against `deal_financials`.

---

### DR-M14 — Due Diligence Package (P3, unchanged)

Scope unchanged from ROADMAP. Expands the Due Diligence section (12) with generated DD request lists, gap detection, and `deal_dd_items` tracking.

---

## Integration with Existing Milestones

| Existing | Maps To | Integration |
|----------|---------|-------------|
| DR-M8b (Offer Generator) | DR-M8b (expanded) | Original scope preserved. Added: negotiation issue list view (section 5). Uses same `deal_valuations` + golden corpus offer template. |
| DR-M11 (Granola Sync) | DR-M11 (unchanged) | Remains 🔒 deferred. DR-M22 (Deal History) provides the section it feeds into. DR-M22 works without DR-M11 (stage log + contact log are standalone). |
| DR-M13 (Cross-Deal Benchmarking) | DR-M13 (unchanged scope, new consumer) | Benchmark output feeds DR-M20 Investment Thesis scorecard as percentile data. Standalone portfolio view also retained. |
| DR-M14 (DD Package) | DR-M14 (unchanged) | Remains 🔒 deferred. DR-M19 creates the Due Diligence section placeholder it will fill. |
| DR-M9 (Investor Cockpit) | Prerequisite | Must complete first. One-pager becomes section 1. Sidebar reorg (DR-M19) restructures around it. |
| DR-M15 (Investor Report) | No change | Thin layer on DR-M9. Not part of sidebar architecture. |
| DR-M10 (Email Composer) | No change | Remains 🔒 deferred. Not mapped to sidebar. |
| DR-M12 (NDA Generator) | No change | Remains 🔒 deferred. Not mapped to sidebar. |
| DR-M17 (Outside-In Canvas) | No change | Remains 🔒 deferred. Could feed Market & Competition section (DR-M21) if undeferred. |

---

## Suggested Execution Sequence

1. **DR-M9** (in progress) — finish the one-pager landing page. Everything below depends on this.
2. **DR-M18** — Bilanz + Valuation views. Roman's stated priority. Pure backend + frontend, no structural changes.
3. **DR-M19** — Sidebar reorganization. Renames tabs, adds block structure. Quick win that makes all subsequent sections land in the right place.
4. **DR-M20** — Business Model + Investment Thesis. Core IC memo chapters. Scorecard infrastructure already exists.
5. **DR-M8b** — Offer & Negotiation. Deal-moving: generates offer docs, tracks negotiation issues.
6. **DR-M21** — Employees + Suppliers + Market. Data-dependent — build views, populate as RFI answers come in.
7. **DR-M13** — Cross-Deal Benchmarking. Valuable once 3+ deals have complete financials.
8. **DR-M22** — Deal History + Stage Tracking. Useful but not blocking deals.
9. **DR-M11** — Granola Sync. Feeds DR-M22 with meeting data. Defer until meeting volume justifies automation.
10. **DR-M14** — DD Package. Build when first deal reaches LOI/DD stage.

**Rationale**: Sequence optimizes for (a) unblocking Roman's stated gaps first (Bilanz, Valuation), (b) establishing navigation structure early so milestones land cleanly, (c) prioritizing deal-moving tools (offer, thesis) over data-display views, (d) deferring data-dependent sections until data exists.

**Estimated total**: ~11.5 days of execution across all milestones (excluding DR-M9 which is already in progress, DR-M11 and DR-M14 which remain deferred).
