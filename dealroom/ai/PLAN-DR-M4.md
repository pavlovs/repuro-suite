# DR-M4: Deal Workspace Dashboard

## Summary

`DEALROOM.py dashboard` opens an all-deals overview. `DEALROOM.py dashboard --deal Wolf` opens the single-deal workspace. Same pattern as ALLEX: stdlib HTTP server on port 8090, self-contained HTML, hybrid static/serve mode. This milestone delivers the Financials tab (P&L + balance with source/conflict badges), Documents tab, Notes tab, and the cockpit strip. Other tabs (Commercial, Model & Valuation, Internal Deal Screen, Timeline, Open Topics) are stubbed with headers — they depend on data from later milestones.

Done when: `pytest tests/` passes, `DEALROOM.py dashboard --deal Wolf` opens in browser with real extracted data visible in the Financials table, conflicts highlighted, cockpit strip shows stage + days-in-stage + conflict count.

---

## HOW TO EXECUTE THIS MILESTONE

1. Read `PLAN-DR-M4.md` (this file) fully before writing any code.
2. Implement in the sequence listed in the Plan section. Do not skip steps.
3. After implementation: run `pytest tests/` (must pass), then run live against real data.
4. Update `PLAN-DR-M4.md ## AI Validation Results` before committing.
5. One commit: `feat(DR-M4): Deal Workspace Dashboard — cockpit, financials, docs, notes`

---

## Locked Decisions

**Port 8090** (ALLEX uses 8080 — avoid collision).

**Same hybrid pattern as ALLEX**: `dashboard.py` builds self-contained HTML, optionally serves it live with `--serve`. Data injected via `__DATA_JSON__` placeholder. In serve mode, `/api/data` returns fresh JSON.

**Two views**:
- **Portfolio view** (no `--deal`): all deals in a table — code, company, stage, days-in-stage, last-contact, conflict count, doc count, data row count. Click a row → opens single-deal view.
- **Deal view** (`--deal Wolf`): full workspace with cockpit strip + tabs.

**Tabs delivered in M4** (with real data):
1. **Financials** — P&L table from `deal_data financial.pnl` by year. Balance sheet summary below. Source badges. Conflict markers.
2. **Documents** — grouped by doc_type, sorted by date.
3. **Notes** — timestamped, newest first.

**Tabs stubbed in M4** (header + "Coming in M{n}" placeholder):
- Overview (needs deal_valuations → M5)
- Commercial (needs deal_data commercial.* → M6 RFI)
- Model & Valuation (needs deal_valuations → M5)
- Internal Deal Screen (needs deal_questions + deal_actions → M6/M7)
- Timeline (needs deal_emails + deal_granola → M10/M11)
- Open Topics (needs deal_questions → M6)

**No external CSS/JS frameworks.** Vanilla CSS + JS, same as ALLEX. Single HTML file, no build step.

**Template file**: `src/templates/dashboard.html`. Single file for both portfolio and deal views — JS toggles which section is shown based on data.

**domain fallback**: deals with NULL domain use `code_name.lower()` as the join key, matching `data.py` behavior.

---

## Plan

### Step 1 — `src/dashboard.py`

Create `src/dashboard.py` with:

```python
def build_dashboard_data(conn, code_name=None) -> dict:
    """Build the JSON payload for the dashboard.

    If code_name is None: returns portfolio-level data for all deals.
    If code_name is set: returns full deal data for the single-deal view.
    """

def serve_dashboard(conn, code_name=None, port=8090, serve=False) -> None:
    """Build HTML, optionally start HTTP server."""
```

**Portfolio data shape** (`code_name=None`):
```json
{
  "mode": "portfolio",
  "deals": [
    {
      "code_name": "Wolf",
      "company_name": "KVG Vertriebs GmbH",
      "deal_stage": "offer_negotiation",
      "stage_entered_at": "...",
      "last_contact_at": "...",
      "days_in_stage": 42,
      "days_since_contact": 15,
      "data_rows": 58,
      "doc_count": 26,
      "conflict_count": 0,
      "note_count": 0
    },
    ...
  ]
}
```

**Deal data shape** (`code_name="Wolf"`):
```json
{
  "mode": "deal",
  "deal": {
    "code_name": "Wolf",
    "company_name": "KVG Vertriebs GmbH",
    "deal_stage": "offer_negotiation",
    "stage_entered_at": "...",
    "last_contact_at": "...",
    "days_in_stage": 42,
    "days_since_contact": 15,
    "investment_thesis": null,
    "seller_motivation": null,
    "conflict_count": 0,
    "notes": "..."
  },
  "financials": {
    "pnl": {
      "2022": {"revenue": {"value": 5773.74, "source": "guv_2022.xlsx", "conflict": false}, ...},
      "2023": {...},
      "2024": {...}
    },
    "balance": {
      "2022": {"total_assets": {...}, "equity": {...}, ...},
      ...
    },
    "risk_flags": ["EBITDA margin 4.4% in 2024 (< 10%)"]
  },
  "documents": [
    {"file_name": "...", "doc_type": "financials_raw", "doc_subtype": "guv", "fiscal_year": 2022, "registered_at": "..."},
    ...
  ],
  "notes": [
    {"note": "...", "author": "Roman", "created_at": "..."},
    ...
  ]
}
```

**`build_dashboard_data`** queries:
- `deals` table for deal metadata
- `deal_data` for financials (grouped by fiscal_year, key)
- `deal_documents` for document list
- `deal_notes` for notes
- Computes `days_in_stage` and `days_since_contact` from timestamps

**HTTP server** (same pattern as ALLEX):
- `_DashboardHandler(BaseHTTPRequestHandler)`
- `GET /` → serve HTML
- `GET /api/data` → serve JSON (live refresh in serve mode)
- Port 8090

### Step 2 — `src/templates/dashboard.html`

Single self-contained HTML file. Structure:

**Header** (sticky):
- "DEALROOM" title + LIVE/STATIC badge

**Portfolio view** (shown when `mode == "portfolio"`):
- Table: Code | Company | Stage | Days in Stage | Last Contact | Data | Docs | Conflicts
- Stage badges with color coding (green=financials_received, blue=offer_*, yellow=loi_*, gray=paused/declined)
- Row click → navigates to `?deal={code_name}` (serve mode) or shows deal view inline (static mode)

**Deal view** (shown when `mode == "deal"`):
- **Cockpit strip**: code_name | company | stage badge | "X days in stage" | "Last contact Y days ago" | conflict count badge
- **Tab bar**: Financials | Documents | Notes | Overview* | Commercial* | Model* | Internal* | Timeline* | Topics*
  (*stubbed tabs show placeholder)

**Financials tab**:
- **P&L table**: columns = fiscal years (sorted). Rows = revenue, cogs, gross_profit, personnel, other_opex, other_income, ebitda, da, ebit, interest_expense, interest_income, ebt, tax, net_income. Values in EUR_K formatted with thousand separators. Source tooltip on hover. Conflict cells highlighted red with tooltip showing conflicting values.
- **Balance sheet summary** below P&L: total_assets, equity, cash, net_debt per year.
- **Risk flags** section: list of auto-detected flags from deal_data.

**Documents tab**:
- Grouped by `doc_type` (financials_raw, model, offer, nda, etc.)
- Each row: file_name, doc_subtype, fiscal_year, registered_at
- File names are plain text (no links — files are on OneDrive, not served)

**Notes tab**:
- Chronological list, newest first
- Each note: text, author, timestamp

**Styling**:
- Dark header, light body (same visual language as ALLEX)
- Monospace numbers in financial tables
- Stage badge colors: `financials_received`=amber, `offer_preparation`=blue, `offer_sent`=indigo, `offer_negotiation`=purple, `loi_*`=green, `paused`=gray, `declined`=red
- Conflict cells: light red background, red border
- Responsive: works at 1200px+ width

### Step 3 — Wire `DEALROOM.py dashboard` command

Replace the `dashboard` stub with:

```python
def cmd_dashboard(args) -> None:
    from src.dashboard import serve_dashboard
    conn = get_conn()
    serve_dashboard(conn, code_name=args.deal, port=8090, serve=getattr(args, 'serve', False))
    conn.close()
```

Add `--deal`, `--serve`, `--port` arguments.

### Step 4 — Tests (`tests/test_dashboard.py`)

Unit tests (no HTTP server, no browser):
1. `test_portfolio_data_has_all_deals` — `build_dashboard_data(conn)` returns all seeded deals
2. `test_deal_data_has_financials` — `build_dashboard_data(conn, "TestCo")` includes pnl dict
3. `test_days_in_stage_computed` — deal with `stage_entered_at` set → `days_in_stage` is positive int
4. `test_conflict_count_matches` — deal with known conflicts → `conflict_count` matches
5. `test_documents_grouped` — documents returned with correct fields
6. `test_notes_newest_first` — notes ordered by created_at desc

All tests use tmp_path + in-memory DB with seeded data. No HTTP calls.

---

## Better Engineering Notes

- The ALLEX dashboard builds a single massive HTML with all data embedded. For DEALROOM, the data is much smaller (12 deals, ~300 deal_data rows) so the same approach works fine.
- The portfolio view is new (ALLEX only has single-view). Keep it simple — a table, not a kanban board. Kanban would be nice but is scope creep for M4.
- Conflict visualization is the key debugging feature Roman asked for. Make it visually obvious: red background + tooltip with the conflicting value and source.
- Stubbed tabs should look intentional, not broken. Use a muted style with the milestone reference.

---

## AI Validation Plan

```bash
# Unit tests
cd REPURO/dealroom && python -m pytest tests/ -v

# Portfolio view (static)
python DEALROOM.py dashboard

# Deal view (static, opens browser)
python DEALROOM.py dashboard --deal Wolf

# Live serve mode
python DEALROOM.py dashboard --deal Wolf --serve
```

Expected:
- `pytest tests/` → all pass (existing 56 + new ~6 = ~62)
- Portfolio view: HTML opens in browser, shows 12 deals with stage badges
- Wolf deal view: cockpit strip shows "Wolf | KVG Vertriebs GmbH | offer_negotiation"
- Financials tab: P&L table with 2022/2023/2024 columns, revenue=5773.74 for 2022
- Documents tab: 26 documents grouped by type
- Risk flags: "EBITDA margin 4.4% in 2024 (< 10%)" visible

---

## AI Validation Results

- `pytest tests/ -v -m "not live"`: **62 passed**, 2 deselected (live tests)
- New tests: 8 in `test_dashboard.py` (portfolio, deal, financials, conflicts, docs, notes)
- Portfolio static: `dashboard_20260330.html` generated, opens in browser, 12 deals visible
- Wolf deal static: `dashboard_Wolf_20260330.html` generated
  - Cockpit: Wolf | KVG Vertriebs GmbH | offer_negotiation
  - P&L: 4 years (2021-2024), revenue 2022 = 5,773.74
  - Balance: 3 years (2022-2024)
  - Risk flag: "EBITDA margin 4.4% in 2024 (< 10%)"
  - Documents: 26 files grouped by type
  - Notes: 0 (empty state with CLI hint)
  - Stubbed tabs show placeholder text with milestone reference

---

## User Validation Walkthrough

1. Run `python DEALROOM.py dashboard --deal Wolf --serve`
2. Browser opens at `localhost:8090`
3. **Cockpit strip**: verify code name, company, stage, days-in-stage
4. **Financials tab**: check revenue 2022 = 5,773.74. Check EBITDA values look reasonable. Hover over a cell → see source file tooltip.
5. **Documents tab**: verify doc list matches what `ingest-docs` registered
6. **Notes tab**: empty (no notes added yet). Add one via `python DEALROOM.py note --deal Wolf --text "test note"`, then refresh dashboard.
7. Navigate to portfolio view (click "DEALROOM" header or visit `localhost:8090`)
8. Verify all 12 deals listed with correct stages and counts.

---

## PM Review
Reviewed: 2026-03-30
Model: Claude Opus 4.6

### Required changes (high conviction — autonomous)

1. **Serve mode ignores `?deal=` query parameter — portfolio-to-deal navigation broken.** Server always returns pre-built HTML regardless of URL. Fix: parse `?deal=` from URL, build deal-specific data dynamically. `/api/data` must also honor `?deal=`.

2. **Static mode portfolio click shows developer-facing alert.** Change alert text to clear, actionable instruction.

3. **Sign inversion on cost lines could mask conflicts.** `Math.abs()` hides sign discrepancies between sources. Validate against actual Cat data; store and display values with consistent sign convention.

### Clarify with project owner (low conviction)

1. German vs English financial labels (Umsatzerloese vs Revenue)
2. Open Topics count missing from cockpit strip (deferred to M6/M7)
3. No breadcrumb / back arrow in deal view
4. Balance sheet not expandable like P&L
5. Risk flags in sidebar vs inline in financials

### Verdict
CONDITIONAL PASS

### PM Amendments

1. **Fixed: serve mode `?deal=` routing.** Server now parses `?deal=Wolf` from URL query string, builds deal-specific data dynamically for both HTML and `/api/data`. Portfolio → deal click navigation works in serve mode.
2. **Fixed: static mode alert text.** Changed from developer-facing "Run: python..." to "Static mode — to browse deals interactively, restart with: python DEALROOM.py dashboard --serve".
3. **Verified: sign convention is clean.** All cost items stored as positive absolute values in deal_data. `Math.abs()` in JS is redundant but safe. Checked Cat's 50 conflicts — all are real value differences between entity files, no sign-flip masking.

### PM Amendment Results

- `pytest tests/ -m "not live"`: 63 passed
- Serve mode routing: verified `/?deal=Wolf` loads deal view, `/` loads portfolio
- Static mode alert: shows actionable message

### Verdict (updated)
PASS — all REQUIRED items resolved
