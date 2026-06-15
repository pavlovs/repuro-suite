# DR-M8: Company Overview

## Summary

Adds an "Overview" section as the default landing view when opening a deal workspace. Shows a company fact sheet with key data pulled from ALLEX `pipeline.db` (via ATTACH) and `dealroom.db`: legal name, address + embedded map, employees, revenue, EBITDA, owner/seller profile, managing director contact, service description, legal entity info, deal stage, and investment thesis. Replaces "Information" as the top sidebar item; the old Information tab (GuV/Bilanz sub-tabs) moves below it.

**Done when**: opening any deal shows a one-page overview card with all available facts filled, map rendered, and empty fields marked as "—".

## HOW TO EXECUTE THIS MILESTONE

Planning: run `/plan-milestone` (reads `ai/ROADMAP.md` for scope)
Execution: run `/execute-milestone`

Full protocols: `~/.claude/commands/plan-milestone.md` and `~/.claude/commands/execute-milestone.md`

## Locked decisions

1. **Data source**: Company identity data from `allex.company_records` via existing ATTACH (read-only). Deal-level data from `dealroom.deals` + `dealroom.deal_data`. No new tables.
2. **Sidebar position**: "Overview" becomes the first sidebar item and the default section shown on deal load. "Information" (GuV/Bilanz) moves to second position, renamed "Financials".
3. **Map**: Leaflet.js (CDN) + OpenStreetMap tiles. Geocode via Nominatim (1 request per deal load — well within usage policy). Circle marker with radius proportional to EBITDA (`radius = Math.max(8, Math.sqrt(ebitda_k / 10))`), teal fill, semi-transparent. Fallback if no PLZ: show "Location not available" text instead of map.
4. **Layout**: Two-column card layout within the main content area. Left column: company identity + map. Right column: financial snapshot + seller/owner profile.
5. **No new CLI commands**: This is purely a dashboard rendering change + a small data-loading addition in `build_deal_data()`.
6. **Financial snapshot**: Latest-year revenue, EBITDA, EBITDA margin, and employee count from `deal_data`. Falls back to `allex.company_records.revenue_tsd_eur` and `ma_count` if no deal_data exists.

## Plan

### Step 1 — Extend `build_deal_data()` in `src/dashboard.py`

Add a new `overview` key to the return dict. Load from both sources:

```python
# In build_deal_data(), after _attach_allex(conn):

# ALLEX company data
allex_row = conn.execute(
    """SELECT full_name, street, plz_ort, city, region, ma_count, revenue_tsd_eur,
              leistung_text, rechtsform, hrb_number,
              gesellschafter_name, gesellschafter_age, gesellschafter_share_pct,
              gf_name, gf_email, gf_phone, owner_name
       FROM allex.company_records WHERE domain = ? LIMIT 1""",
    (domain,),
).fetchone()

overview = {}
if allex_row:
    overview = {
        "legal_name": allex_row["full_name"],
        "street": allex_row["street"],
        "plz_ort": allex_row["plz_ort"],
        "city": allex_row["city"],
        "region": allex_row["region"],
        "employees_allex": allex_row["ma_count"],
        "revenue_allex_k": allex_row["revenue_tsd_eur"],
        "services": allex_row["leistung_text"],
        "rechtsform": allex_row["rechtsform"],
        "hrb": allex_row["hrb_number"],
        "owner_name": allex_row["owner_name"] or allex_row["gesellschafter_name"],
        "owner_age": allex_row["gesellschafter_age"],
        "owner_share_pct": allex_row["gesellschafter_share_pct"],
        "gf_name": allex_row["gf_name"],
        "gf_email": allex_row["gf_email"],
        "gf_phone": allex_row["gf_phone"],
    }

# Enrich with dealroom data
overview["description"] = deal["description"] or ""
overview["investment_thesis"] = deal["investment_thesis"] or ""
overview["seller_motivation"] = deal["seller_motivation"] or ""
overview["seller_age"] = deal["seller_age_approx"]
overview["seller_notes"] = deal["seller_profile_notes"] or ""

# Financial snapshot from deal_data (latest year)
for metric in ["revenue", "ebitda", "ebit"]:
    row = conn.execute(
        """SELECT fiscal_year, value_num FROM deal_data
           WHERE domain = ? AND category = 'financial' AND subcategory = 'pnl'
             AND key = ? AND value_num IS NOT NULL
           ORDER BY fiscal_year DESC LIMIT 1""",
        (domain, metric),
    ).fetchone()
    if row:
        overview[f"{metric}_k"] = row["value_num"]
        overview[f"{metric}_year"] = row["fiscal_year"]

# Employee count from deal_data (operational) — fallback to ALLEX
emp_row = conn.execute(
    """SELECT value_num FROM deal_data
       WHERE domain = ? AND category = 'operational' AND key = 'headcount'
         AND value_num IS NOT NULL
       ORDER BY fiscal_year DESC LIMIT 1""",
    (domain,),
).fetchone()
overview["employees"] = (
    int(emp_row["value_num"]) if emp_row
    else overview.get("employees_allex")
)
```

Add `"overview": overview` to the return dict.

### Step 2 — Add `renderOverview()` function in `dashboard.html`

Two-column layout inside the main content area:

**Left column (company identity)**:
- **Company name** (large, bold) — `legal_name` or `deal.company_name`
- **Code name** badge (teal pill) — `deal.code_name`
- **Stage** badge — `deal.deal_stage` with color coding
- **Description** — `description` field (1-2 lines)
- **Services** — `services` / `leistung_text`
- **Address** — `street`, `plz_ort`
- **Region** — `region`
- **Map** — Leaflet.js map (CDN: `unpkg.com/leaflet@1.9/dist/leaflet.{js,css}`). OpenStreetMap tile layer. On render:
  1. Extract PLZ from `plz_ort` (first 5 digits)
  2. Fetch `https://nominatim.openstreetmap.org/search?postalcode={plz}&country=Germany&format=json&limit=1` (with `User-Agent: DEALROOM/1.0` header per Nominatim policy)
  3. On success: center map on lat/lng, zoom 11, add `L.circleMarker` with:
     - Radius: `Math.max(8, Math.sqrt(ebitda_k / 10))` pixels (Fox EBITDA 365 → radius ~6 → clamped to 8; a €2M EBITDA deal → radius ~14)
     - Fill: teal `#1D7080`, opacity 0.5
     - Stroke: teal, weight 2
     - Tooltip: `"{company_name} — EBITDA €{X}K"`
  4. On failure (network error, 429, empty result) or no PLZ: show static text "Location: {plz_ort}" instead of map div. Wrap fetch in `.catch()` — never crash the overview on geocoding failure.
- **Legal entity** — `rechtsform`, HRB `hrb`

**Right column (deal facts)**:

- **Key financials card** (compact table):

  | Metric | Value | Year |
  |--------|-------|------|
  | Revenue | €X.XM | 2024 |
  | EBITDA | €X.XM | 2024 |
  | EBITDA margin | XX.X% | |
  | Employees | XX | |

  Falls back to ALLEX values (italic, labeled "ALLEX") if no deal_data.

- **Commercial KPIs** (from `deal_data commercial.*`, show "—" if not yet populated):
  - Recurring revenue %
  - Top 3 customer concentration %
  - Revenue CAGR (from adj_pnl cagr if available, else compute from deal_data revenue over available years)

- **Owner / Seller profile card**:
  - Name, age, ownership %
  - Motivation (succession / financial / etc.)
  - Profile notes
  - Managing director: name, email (mailto link), phone (tel link)

- **Investment thesis** (if filled) — 3-5 bullet points

- **Deal stage timeline** — simple horizontal: `financials_received → rfi_sent → ... → current` with current stage highlighted

### Step 3 — Update sidebar and default section

In `renderSidebar()`:
- Replace `sidebarItem('information','Information',null)` with `sidebarItem('overview','Overview',null)`
- Rename "Information" to `sidebarItem('financials','Financials',null)` (keeps the GuV/Bilanz sub-tabs)

In `showSection()` switch:
- Add `case 'overview': area.innerHTML=bc+renderOverview(); break;`
- Rename `case 'information':` to `case 'financials':`

In `renderDeal()`: change `showSection('information')` to `showSection('overview')`.

### Step 4 — CSS additions

Minimal additions inside the existing `<style>` block:
```css
.overview-grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
.overview-card { background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }
.overview-card h3 { margin:0 0 12px 0; font-size:14px; color:#1D7080; border-bottom:1px solid #e2e8f0; padding-bottom:6px; }
.overview-fact { display:flex; justify-content:space-between; padding:4px 0; font-size:13px; border-bottom:1px solid #f1f5f9; }
.overview-fact .label { color:#64748b; }
.overview-fact .value { font-weight:600; text-align:right; }
.overview-map { width:100%; height:200px; border:1px solid #e2e8f0; border-radius:6px; margin-top:8px; }
.stage-timeline { display:flex; gap:4px; margin-top:12px; flex-wrap:wrap; }
.stage-pill { padding:3px 8px; border-radius:12px; font-size:11px; background:#e2e8f0; color:#475569; }
.stage-pill.active { background:#1D7080; color:#fff; font-weight:700; }
.stage-pill.passed { background:#d1fae5; color:#065f46; }
```

### Step 5 — Tests

Add tests in `tests/test_dashboard_overview.py` (or append to existing test file):

```python
def test_overview_data_present():
    """build_deal_data returns overview dict with expected keys."""

def test_overview_allex_fallback():
    """When deal_data has no employees, falls back to ALLEX ma_count."""

def test_overview_no_allex_record():
    """When domain has no ALLEX match, overview has None values — no crash."""

def test_overview_financial_snapshot():
    """Latest-year revenue/EBITDA populated from deal_data."""
```

## Better engineering notes

- **No new DB tables or schema changes.** All data comes from existing sources. The ALLEX ATTACH is already wired in `_attach_allex()`.
- **Leaflet.js + Nominatim**: One geocoding request per deal page load. Nominatim usage policy requires `User-Agent` header and max 1 req/sec — single-user localhost tool is well within limits. Map tiles load from OSM CDN. No API keys needed.
- **Circle radius formula**: `Math.max(8, Math.sqrt(ebitda_k / 10))` gives visually distinct sizes. Fox (365K) → 8px, a €1M EBITDA deal → 10px, €4M → 20px. The `max(8, ...)` prevents tiny circles for small deals.
- **The `gesellschafter_age` field in pipeline.db is unreliable** (Fox shows 126 — clearly wrong). Use `deals.seller_age_approx` as the primary source; only fall back to ALLEX if value is between 20 and 100. Outside that range: show "—".
- **Revenue from ALLEX (`revenue_tsd_eur`) vs deal_data**: ALLEX revenue is from ORBIS/scraping (often stale). `deal_data` revenue is from actual financials. Always prefer deal_data; only show ALLEX value as fallback, clearly labeled.
- **Static mode**: Leaflet map still works in static HTML (tiles load from CDN on open). Nominatim geocoding also works. No serve-mode dependency.

## AI validation plan

```bash
cd REPURO/dealroom

# Unit tests
python -m pytest tests/ -v
# Expected: 115 existing + 4 new = ~119 passed

# Dashboard (serve mode) — Fox
python DEALROOM.py dashboard --deal Fox --serve
# 1. Opens to Overview section (not Information)
# 2. Left column: "Com 2 Med Medizintechnologien GmbH & Co. KG", address, map, region
# 3. Right column: revenue/EBITDA/margin from deal_data, owner name, contact info
# 4. Click "Financials" sidebar → old GuV/Bilanz tabs still work
# 5. Click "Model" → valuation model still works

# Dashboard — Wolf (has ALLEX data)
python DEALROOM.py dashboard --deal Wolf --serve
# Overview populates from ALLEX + deal_data

# Dashboard — deals without ALLEX link (Cat has no domain)
python DEALROOM.py dashboard --deal Cat --serve
# Overview shows "—" for ALLEX fields, deal_data still shown
```

## AI validation results

**Date**: 2026-04-03
**Executor**: claude-opus-4-6

### Unit tests
```
python -m pytest tests/ -v
119 passed in 21.88s (115 existing + 4 new overview tests)
```

### Live data verification — Fox
```python
build_deal_data(conn, 'Fox')['overview']
# legal_name: 'Com 2 Med Medizintechnologien GmbH & Co. KG'
# city: 'Braunschweig', plz_ort: '38122 Braunschweig'
# street: 'Frankfurter Str. 3 A', region: 'Lüneburger Heide'
# owner_name: 'Jens-Uwe Muehlan', owner_share_pct: 100.0
# gf_email: 'j.muehlan@com2med.de', gf_phone: '+49 531 2842085'
# revenue_k: 1203.06 (2022), ebitda_k: 138.34 (2022), ebitda_margin_pct: 11.5
# services: 'Medizintechnik-Experten', hrb: 'HRB 9110'
# description: 'Distribution & service of medical products...'
```

### Wolf and Cat (no ALLEX domain match)
Both gracefully return None for ALLEX fields (legal_name, city, plz_ort, owner). Financial snapshot still populated from deal_data. No crashes.

### Deviations from plan
1. `_build_overview` wraps ALLEX ATTACH in try/except (test environment doesn't have pipeline.db)
2. Deal columns accessed via `dict(deal).get()` instead of direct indexing (migration-added columns may not exist in test DB)
3. Fox EBITDA shown is from raw deal_data (2022 only) — 2023-2025 data is in valuation_input.pnl_adj (handled by model context, not overview snapshot)

## User validation walkthrough

1. `python DEALROOM.py dashboard --deal Fox --serve` — opens in browser
2. Default view is now "Overview" — verify company name, address, map visible
3. Check financial snapshot: revenue, EBITDA match your expectations for Fox
4. Check owner/seller: name, contact info visible
5. Click "Financials" in sidebar → GuV/Bilanz sub-tabs still work
6. Click "Model" → valuation model still works
7. Try Wolf, Cat — verify overview populates (or shows "—" gracefully)
8. Close and re-open without `--serve` → static HTML overview renders correctly

## PM Review

**Date**: 2026-04-01
**Reviewer**: claude-opus-4-6 (PM review)

### Correctness vs. spec

The milestone delivers what was promised:
- Overview is the default landing view (sidebar item 1, `showSection('overview')` on load)
- Company facts pulled from ALLEX pipeline.db via ATTACH (legal name, address, region, services, rechtsform, HRB, owner, GF contact)
- Map with Leaflet.js + Nominatim geocoding, circle sized by EBITDA, teal fill, tooltip
- Financial snapshot (revenue, EBITDA, margin, employees, CAGR, commercial KPIs)
- Owner/seller profile with motivation, notes, contact links
- Investment thesis rendering
- Deal stage timeline with progress visualization
- Graceful fallbacks: ALLEX age capped 20-100, ALLEX revenue shown italic when no deal_data, "---" for missing fields, `.catch()` on geocoding

### Required changes

1. **Breadcrumb links to dead section `'information'`** (line 543 of dashboard.html). The breadcrumb code name link calls `showSection('information')` but this case was renamed to `'financials'` in the switch statement. Clicking the deal code name in the breadcrumb does nothing. Should link to `showSection('overview')` instead — that is the new "home" section for a deal.

2. **Breadcrumb suppresses section label for `id === 'information'`** (line 544). The condition `id!=='information'` is stale — it should be `id!=='overview'` so the breadcrumb shows just the deal name when on the Overview tab (the landing view), and appends the section name otherwise.

### Clarify with project owner

1. **EBITDA year mismatch**: Fox shows 2022 financials in the overview snapshot, but the valuation model uses 2023-2025 adjusted P&L. Is it confusing to show 2022 as "latest year" on the landing page when adjusted data exists? Consider whether the overview should pull from `valuation_input.pnl_adj` for deals with a completed model, or at least flag "newer adjusted data available in Model".

2. **Negative EBITDA circle sizing**: The code uses `Math.abs(ebitda)` for circle radius, so a loss-making deal gets the same circle size as a profitable one. Should negative EBITDA deals get a different visual treatment (red circle, or no circle)?

3. **Static mode offline behavior**: Leaflet tiles and Nominatim both require internet. In static mode (no `--serve`), opening the HTML offline will show a broken map div. Acceptable for an internal tool, but worth acknowledging.

### Verdict: CONDITIONAL PASS

Items 1-2 under Required are straightforward fixes (two string replacements in the breadcrumb). Fix those, then this is a clean PASS. The Clarify items are UX polish — none block the commit.

### PM Amendments

1. **Breadcrumb fix**: Changed `showSection('information')` → `showSection('overview')` and `id!=='information'` → `id!=='overview'` in dashboard.html breadcrumb (lines 543-544).
2. **CLARIFY #1 — Financial timeline**: User decided: show Revenue + adj. EBITDA for all years up to 2025. Added `financial_timeline` dict to `_build_overview()` that merges raw revenue + adj. EBITDA (falls back to raw EBITDA). Rendered as a year-column table in the overview.
3. **CLARIFY #2 — Negative EBITDA**: User decided: minimum-size red circle on map + prominent risk flag banner. Implemented in both map circle (red fill, radius=8) and financial table (red text + warning banner).
4. **CLARIFY #3 — Offline map**: User decided: show placeholder message. Added `typeof L === 'undefined'` check + try/catch around map init with "Map requires internet connection" fallback.

### PM Amendment Results
```
python -m pytest tests/ -v
121 passed in 21.33s (119 existing + 2 new timeline tests)
```
All 14 dashboard tests pass including 2 new tests: `test_overview_financial_timeline` and `test_overview_timeline_empty_for_no_data`.

### Verdict (post-amendment): PASS

### Post-commit improvements (user-directed)

**Stage label capitalization**: "loi" → "LOI", "rfi" → "RFI", "dd" → "DD". Used word-boundary regex with acronym correction.

**Cat domain linked**: Set `domain = 'medizinservice-sachsen.de'` for Cat deal (Medizin & Service GmbH, Chemnitz). ALLEX data now links: address (Böttcherstr. 10, 09117 Chemnitz), owner (Andreas Schröcke, age 60), GF contact.

**Cat description**: 5 bullet points sourced from RFI answers, Granola meeting notes, thesis analysis, and financial model. Covers: product/services, entity structure, customer base, order backlog, strategic positioning.

**Frontend design review (Opus)**: Applied 10 improvements:
1. Map hidden when no location data (no more empty 220px box)
2. Single-column layout for no-ALLEX deals
3. Description rendered as bullet list (`<ul>/<li>`)
4. "Operational KPIs" separator between financial table and metrics
5. Empty KPI rows hidden (only show rows with data)
6. Owner card hidden when empty (no more "Name: —")
7. Days-since-contact: amber 14-30d, red 30d+
8. Stage pills horizontal scroll instead of wrapping
9. Investment thesis always shown (empty-state prompt)
10. "GF" → "Managing Director" label

**Cat one-pager**: Static HTML investor one-pager at `data/output/onepager_Cat.html`. Matches reference PDF layout (page 5 of `260318_Repuro_Deal_Onepagers_v1.pdf`). Includes: executive summary, process details, service/customer structure, P&L table (2023A-2026P), customer split chart, KPI boxes, valuation summary.
