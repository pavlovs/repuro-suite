# DR-M9: Investor Cockpit

## Summary

Redesigns the deal landing page as a 2x2 one-pager grid (exec summary, financials, process/status, service portfolio) with drill-down into existing tabs. Adds stage filter to portfolio view. Auto-generates narrative bullets from deal data using style guides extracted from golden corpus one-pagers. Full spec: `SPEC-INVESTOR-COCKPIT.md`.

**Done when**: portfolio has working stage filter, clicking a deal shows the one-pager landing page with all 4 quadrants rendering from DB, Q2 shows a financial chart, Q1/Q3/Q4 bullets are auto-generated and editable inline, drill-down links scroll to existing tabs.

## HOW TO EXECUTE THIS MILESTONE

Planning: this file.
Execution: run `/execute-milestone`
Full protocols: `~/.claude/commands/plan-milestone.md` and `~/.claude/commands/execute-milestone.md`

## Locked decisions

1. **One-pager replaces deal landing page** — not a separate view. Existing tabs render below it.
2. **Q2 is data-driven, never stored** — renders live from `deal_financials` + `deal_valuations`. Chart year window is data-driven (not hardcoded).
3. **Q1/Q3/Q4 auto-generated with approval gate** — yellow DRAFT badge until Roman approves. Stored in `deals.onepager_q{1,3,4}`.
4. **Separate style guides per quadrant** — `config/golden/onepager/guide-q{n}.md`. Independent iteration and prompt efficiency.
5. **English output** — matches golden corpus. German domain terms acceptable (Gesamtleistung, Sofortzahlung).
6. **Mandatory footnote** — auto-populated with "as of" date, latest financial period, valuation date.
7. **Stage filter includes `nda_exchange`** in "All Active".
8. **Self-contained HTML** — no external JS/CSS libraries. Same pattern as existing dashboard.
9. **PPTX export NOT in scope** — cockpit is the authoring tool; PPTX export is downstream via SPEC-ONEPAGER.md.

## Plan

### Step 1 — DB migration

Add columns to `deals` table in `src/db.py` migration chain:

```sql
onepager_title, onepager_q1, onepager_q3, onepager_q4, onepager_footnote,
onepager_generated_at, onepager_edited_at,
onepager_q1_approved (INTEGER DEFAULT 0),
onepager_q3_approved (INTEGER DEFAULT 0),
onepager_q4_approved (INTEGER DEFAULT 0)
```

Non-destructive ADD COLUMN. Same pattern as existing `_ensure_portfolio_columns()`.

**Files**: `src/db.py`
**Test**: run migration, verify columns exist via PRAGMA table_info.

---

### Step 2 — Backend: onepager data in `build_deal_data()`

Extend `build_deal_data()` in `src/dashboard.py`:

1. Add `onepager` dict to return value: title, q1, q3, q4, footnote, generated_at, edited_at, q1_approved, q3_approved, q4_approved
2. New function `build_onepager_chart_data(conn, domain)`:
   - Query `deal_financials` WHERE statement='pnl', period_type='annual' → gesamtleistung + ebitda per year
   - Query `deal_financials` WHERE period_type IN ('ltm','ytd') → current trading
   - Query `deal_valuations` → ev_mid, ev_low, ev_high, earnout_max, ebitda_basis
   - Compute implied multiple at render time: `(ev_mid + earnout_max) / ebitda_basis`
   - Return structured dict for JS chart rendering
3. Auto-populate footnote if empty: "As of {today} | Financials: FY{year}A | Valuation: {date}"

**Files**: `src/dashboard.py`
**Test**: `build_deal_data(conn, 'Cat')` returns `onepager` and `chart_data` keys with correct values.

---

### Step 3 — Backend: API update handler for onepager fields

Extend `/api/update` endpoint to handle `onepager_*` fields. Same pattern as existing portfolio override saves. When saving q1/q3/q4 text, set `onepager_edited_at` to now. Reset `*_approved` to 0 on re-generation (handled in Step 5).

**Files**: `src/dashboard.py`
**Test**: POST to `/api/update` with `{code_name: "Cat", field: "onepager_q1", value: "test"}` → verify DB updated.

---

### Step 4 — Golden guide extraction

Read all one-pager slides from `config/golden/onepager/` PPTX files via `golden.py`. For each slide, extract text from Q1, Q3, Q4 text boxes (position-mapped per SPEC-ONEPAGER.md shape inventory). Analyze patterns and write three guide files:

- `config/golden/onepager/guide-q1-exec-summary.md`
- `config/golden/onepager/guide-q3-process-status.md`
- `config/golden/onepager/guide-q4-service-portfolio.md`

Each guide contains: bullet count range, topic list, example bullets from corpus, tone/length constraints, language rules.

**Files**: one-time extraction script (can run inline or as agent task), 3 output guide files
**Test**: each guide file exists, contains at least 3 example bullets from real slides.

---

### Step 5 — Generation module: `src/generate/onepager.py`

New module. Core function: `generate_onepager(conn, code_name, quadrants=['q1','q3','q4'], force=False)`.

1. Load the relevant guide file(s)
2. Assemble deal data per quadrant (from deal_financials, deal_commercial, deal_customers, deal_valuations, deals, allex.company_records)
3. Call Claude sonnet with guide + data → structured JSON response with bullet list
4. Store in `deals.onepager_q{n}`, set `onepager_generated_at`, reset `*_approved` to 0
5. Re-generation guard: skip if `onepager_edited_at > onepager_generated_at` unless `force=True`

**Files**: `src/generate/onepager.py`
**Test**: generate for Cat, verify bullets stored in DB, verify re-generation guard works.

---

### Step 6 — CLI command: `draft-onepager`

Wire `draft-onepager` in `DEALROOM.py`:
- `--deal Cat` → generate for one deal
- `--all` → generate for all active deals
- `--force` → override edit guard
- `--quadrant q1` → single quadrant only

**Files**: `DEALROOM.py`
**Test**: `python DEALROOM.py draft-onepager --deal Cat` produces stored bullets.

---

### Step 7 — Frontend: stage filter on portfolio

In `dashboard.html`, add to `renderPortfolio()`:
1. Multi-select dropdown above table with stage options
2. JS filter: show/hide `<tr>` rows based on `deal_stage` data attribute
3. Recalculate footer SUM on filter change
4. Hash-based state persistence (`#stage=offer,loi`)
5. Default: "All Active" (nda_exchange + valuation + offer + loi + due_diligence)

**Files**: `src/templates/dashboard.html`
**Test**: open portfolio → filter by "Offer" → only offer-stage deals visible, SUM recalculated.

---

### Step 8 — Frontend: one-pager landing page

New `renderOnepager(data)` function in `dashboard.html`:
1. 2x2 CSS grid with teal (#0891B2) section headers matching Repuro CI
2. Header bar: codename, stage badge, days in stage
3. Title line (editable in serve mode)
4. Q1/Q3/Q4: render stored markdown bullets, DRAFT badge if not approved, approve toggle button
5. Q2: render chart (Step 9) + current trading box + metrics row
6. Footnote (editable)
7. [▼ More] links per quadrant → smooth-scroll to tab section below
8. Called as first thing in `renderDeal()` — existing tabs render below

**Files**: `src/templates/dashboard.html`
**Test**: open Cat deal → one-pager grid renders with correct data, drill-down links work.

---

### Step 9 — Frontend: Q2 financial chart

Pure CSS/JS grouped bar chart inside Q2 quadrant:
1. Bars: Gesamtleistung (light teal) + adj. EBITDA (dark teal) per fiscal year
2. Line overlay: EBITDA margin % (right y-axis, dotted)
3. Year window: data-driven from available fiscal years. Table fallback if <3 years.
4. Current trading inset card (conditional on LTM/YTD data)
5. Key metrics row: CAGR, adj. EBITDA, margin, EV range, implied multiple

**Files**: `src/templates/dashboard.html`
**Test**: Cat Q2 shows bar chart with correct years and values from deal_financials.

---

### Step 10 — Frontend: inline editing + approval

1. `contenteditable` on Q1/Q3/Q4 text areas + title + footnote (serve mode only)
2. Blur → POST to `/api/update` (same pattern as portfolio overrides)
3. Approve button per quadrant: toggles `onepager_q{n}_approved`, removes DRAFT badge
4. Save indicator ("Saved ✓" / "Error")

**Files**: `src/templates/dashboard.html`
**Test**: edit Q1 text → blur → verify saved in DB. Toggle approve → badge disappears.

---

### Step 11 — Integration test + visual review

1. Run `pytest tests/`
2. Start dashboard: `python DEALROOM.py dashboard --serve --port 8090`
3. Visual check on Cat + at least one other deal with financial data:
   - Portfolio filter works
   - One-pager renders all 4 quadrants
   - Q2 chart shows correct data
   - Drill-down scrolls to tabs
   - Inline editing saves
   - Approval toggle works
4. Check edge cases: deal with no financials, deal with no valuation, deal with no commercial data

---

## AI VALIDATION RESULTS

*To be filled after implementation.*
