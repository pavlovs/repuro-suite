# M13: Dashboard UX Polish — ALLEX Branding, Legend, D-Reason Fix

## Summary

Rebrand the dashboard from "Repuro Lead Dashboard" to "ALLEX — Repuro Dashboard" with logo, add a collapsible classification legend (A/B/C/D/E/S), fix the D-reason breakdown query (reads wrong column), add priority badge styling on the lead table, and add a forward-compatible "Open in HubSpot" link in company cards. No new pipeline stages. Dashboard-only changes.

Done when: dashboard renders with ALLEX header + logo, legend toggles, D-reasons show real categories, `pytest tests/` passes.

---

## HOW TO EXECUTE THIS MILESTONE

Planning: run `/plan-milestone` — full protocol in `~/.claude/commands/plan-milestone.md`.
Execution: run `/execute-milestone` — full protocol in `~/.claude/commands/execute-milestone.md`.

---

## Locked decisions

1. **Logo embedding**: Base64-encode `ALLEX_logo.png` and embed as `<img src="data:image/png;base64,...">`. Dashboard works in both static (HTML file) and server mode — no external file reference. Logo path: `settings.ALLEX_LOGO_PATH = BASE_DIR / "ALLEX_logo.png"`.
2. **Logo display size**: 36×36px in header (1024×1024 source → display scaled). Positioned top-right via `margin-left: auto` pushing it to the far right, replacing the current date string (date moves left of logo).
3. **Title**: `<title>ALLEX — Repuro Dashboard</title>` and `<h1>ALLEX <span style="font-weight:400;opacity:0.7;font-size:14px;">— Repuro</span></h1>`.
4. **D-reason fix**: Change query from `COALESCE(filter_reason, 'unknown')` to `COALESCE(reclassify_reason, filter_reason, 'unknown')`. The AI classifier stores reason codes in `reclassify_reason` (set by `update_classify_result`). `filter_reason` is the M4 pre-filter reason — different column. Current state: 57 D records have correct `reclassify_reason`, 60 have NULL (older records with no AI reason), 0 have filter_reason. Fix surfaces 8 real D-reason categories instead of all "unknown".
5. **Legend**: Collapsible `<details><summary>` element injected between the header and tabs. Always visible (not tab-hidden). Toggle is pure CSS/HTML, no JS. Content: all 6 klass definitions (A/B/C/D/E/S) in a two-column grid.
6. **Priority badges on lead table**: A → green badge, B → blue badge, C/D/E/S → grey. Applied in the `renderLeads()` JS function. Same badge style as existing `.badge` class but color-varied.
7. **HubSpot link (forward compat)**: Add `hubspot_company_id TEXT` and `hubspot_contact_id TEXT` columns to `_OUTREACH_COLUMNS` in `db.py` so `_migrate_schema()` adds them on next run. In company card: show "Open in HubSpot" button only if `hubspot_company_id` is not null/empty. URL pattern: `https://app.hubspot.com/contacts/PORTAL/companies/COMPANY_ID` — portal ID hardcoded as a constant `HUBSPOT_PORTAL_ID` in `settings.py` (value: to be confirmed — see open question). If HUBSPOT_PORTAL_ID is 0 or unset, button is hidden.
8. **No new pipeline stages, no new DB queries beyond the D-reason fix and column migration**.

---

## Open question (resolve before executing)

**HubSpot Portal ID**: The "Open in HubSpot" URL requires the portal ID (e.g. `https://app.hubspot.com/contacts/12345678/companies/...`). What is the Repuro HubSpot portal ID? It is visible in any HubSpot URL when logged in. If unknown, set `HUBSPOT_PORTAL_ID = 0` in settings.py and the button will be hidden until populated.

---

## Plan

### Step 1 — Fix D-reason query in `dashboard.py`

In `_load_data()`, line ~97, change:
```python
# BEFORE
d_reason_rows = conn.execute(
    """SELECT COALESCE(filter_reason, 'unknown') as reason, COUNT(*) as cnt
       FROM company_records WHERE klass = 'D'
       GROUP BY reason ORDER BY cnt DESC"""
).fetchall()
```
```python
# AFTER
d_reason_rows = conn.execute(
    """SELECT COALESCE(reclassify_reason, filter_reason, 'unknown') as reason, COUNT(*) as cnt
       FROM company_records WHERE klass = 'D'
       GROUP BY reason ORDER BY cnt DESC"""
).fetchall()
```
Also update the docstring comment from `(filter_reason)` to `(reclassify_reason with filter_reason fallback)`.

### Step 2 — Add HubSpot columns to DB schema in `db.py`

Add to `_OUTREACH_COLUMNS` list:
```python
("hubspot_company_id",  "TEXT"),
("hubspot_contact_id",  "TEXT"),
```
`_migrate_schema()` will add them automatically on next `ensure_schema()` call.

### Step 3 — Add `ALLEX_LOGO_PATH` and `HUBSPOT_PORTAL_ID` to `settings.py`

```python
ALLEX_LOGO_PATH: Path = BASE_DIR / "ALLEX_logo.png"
HUBSPOT_PORTAL_ID: int = 0  # set to real portal ID when known
```

### Step 4 — Add logo loader helper in `dashboard.py`

```python
import base64

def _load_logo_b64(logo_path: Path) -> str:
    """Return base64-encoded PNG as data URI, or empty string if file missing."""
    if not logo_path.exists():
        return ""
    data = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"
```

Call at top of `dashboard_cmd()`: `logo_b64 = _load_logo_b64(settings.ALLEX_LOGO_PATH)`.
Pass into `_render_html()` as parameter. Use `{logo_b64}` in the f-string template.

### Step 5 — Update HTML template in `dashboard.py`

**`<title>`** (line ~190):
```html
<title>ALLEX — Repuro Dashboard</title>
```

**Header CSS** — add logo rule:
```css
.header-logo {{
  width: 36px;
  height: 36px;
  object-fit: contain;
  border-radius: 4px;
}}
```

**Legend CSS** — add:
```css
.legend-bar {{
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  padding: 0 20px;
}}
.legend-bar details {{ display: inline-block; width: 100%; }}
.legend-bar summary {{
  padding: 8px 0;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
  list-style: none;
}}
.legend-bar summary::after {{ content: " ▾"; }}
.legend-bar details[open] summary::after {{ content: " ▴"; }}
.legend-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 24px;
  padding: 10px 0 14px;
  font-size: 12px;
}}
.legend-item .klass-badge {{
  display: inline-block;
  font-weight: 700;
  width: 20px;
  text-align: center;
  border-radius: 3px;
  padding: 1px 0;
  margin-right: 6px;
  font-size: 11px;
  color: #fff;
}}
.kb-A {{ background: #16a34a; }}
.kb-B {{ background: #2563eb; }}
.kb-C {{ background: #9333ea; }}
.kb-D {{ background: #6b7280; }}
.kb-E {{ background: #d97706; }}
.kb-S {{ background: #dc2626; }}
```

**Priority klass badges in lead table CSS** — add:
```css
.klass-A {{ background: #16a34a; color: #fff; padding: 1px 6px; border-radius: 3px; font-weight: 700; font-size: 11px; }}
.klass-B {{ background: #2563eb; color: #fff; padding: 1px 6px; border-radius: 3px; font-weight: 700; font-size: 11px; }}
.klass-C, .klass-D, .klass-E, .klass-S {{ background: #e5e7eb; color: #374151; padding: 1px 6px; border-radius: 3px; font-weight: 700; font-size: 11px; }}
```

**Header HTML** (replace existing `<div class="header">` block):
```html
<div class="header">
  <h1>ALLEX <span style="font-weight:400;opacity:0.6;font-size:14px;">— Repuro</span></h1>
  <span class="badge">{'LIVE' if serve_mode else 'STATIC'}</span>
  <span style="margin-left:auto;font-size:11px;opacity:0.7;">{date.today().isoformat()}</span>
  {'<img class="header-logo" src="' + logo_b64 + '" alt="ALLEX">' if logo_b64 else ''}
</div>
```

**Legend HTML** — inject between header div and tabs div:
```html
<div class="legend-bar">
  <details>
    <summary>Classification guide</summary>
    <div class="legend-grid">
      <div class="legend-item"><span class="klass-badge kb-A">A</span><strong>Platform</strong> — service + distribution, 20–80 employees, private, SSB signal</div>
      <div class="legend-item"><span class="klass-badge kb-B">B</span><strong>Add-on</strong> — partial fit, 5–20 employees or weaker service component</div>
      <div class="legend-item"><span class="klass-badge kb-C">C</span><strong>Unclear</strong> — website vague, needs manual review</div>
      <div class="legend-item"><span class="klass-badge kb-D">D</span><strong>No-fit</strong> — dental, pharmacy, hospital, too large, OEM, wrong sector</div>
      <div class="legend-item"><span class="klass-badge kb-E">E</span><strong>Special</strong> — competitor, adjacent niche, review quarterly</div>
      <div class="legend-item"><span class="klass-badge kb-S">S</span><strong>Ownership-gated</strong> — confirmed subsidiary or PE-backed, excluded from export</div>
    </div>
  </details>
</div>
```

**Lead table JS** — in `renderLeads()`, replace plain klass text `r.klass` with:
```js
`<span class="klass-${r.klass||'?'}">${r.klass||'?'}</span>`
```
Apply same in the C-review queue table.

**Company card HubSpot link** — in company card JS, after existing fields, add:
```js
${r.hubspot_company_id && HUBSPOT_PORTAL_ID
  ? `<a href="https://app.hubspot.com/contacts/${HUBSPOT_PORTAL_ID}/companies/${r.hubspot_company_id}"
       target="_blank" class="btn-hubspot">Open in HubSpot</a>`
  : ''}
```
Add `HUBSPOT_PORTAL_ID` as a JS constant from the Python template: `const HUBSPOT_PORTAL_ID = {hubspot_portal_id};`

Add CSS:
```css
.btn-hubspot {{
  display: inline-block;
  margin-top: 8px;
  padding: 4px 12px;
  background: #ff7a59;
  color: #fff;
  border-radius: 4px;
  font-size: 12px;
  text-decoration: none;
  font-weight: 600;
}}
```

### Step 6 — Update `_render_html()` signature

Add `logo_b64: str` and `hubspot_portal_id: int` parameters. Thread them into the f-string template.

### Step 7 — Validate

```bash
python pipeline.py dashboard                        # static mode, check HTML
python pipeline.py dashboard --serve                # server mode, open localhost:8080
python pipeline.py status                           # confirm no regressions
python -m pytest tests/ -q                          # full test suite
```

Manual checks:
- Title tab shows "ALLEX — Repuro Dashboard"
- Logo appears top-right in header
- Legend toggles open/closed
- Lead table shows colored klass badges
- D-reasons panel shows: Unpassende_Branche (28), OEM_Hersteller (8), Zu_Klein (5), etc.

---

## Better engineering notes

- The 60 D records with NULL reclassify_reason likely pre-date the reason_code column being populated. Not a bug to fix — `COALESCE` handles them correctly as 'unknown'. If we ever re-classify them, reason codes will populate.
- Logo is 1024×1024 PNG. Base64 size will be ~200KB embedded in the HTML. Acceptable for a local tool. If it becomes a concern, compress to 64×64 before embedding.
- The `<details><summary>` approach for the legend requires no JS — CSS-only collapse. Reliable across all modern browsers.
- HubSpot portal ID lives in settings.py, not hardcoded. When Roman sets the real ID, it propagates to every new dashboard generated.

---

## AI validation plan

```bash
# 1. Regenerate dashboard
python pipeline.py dashboard

# 2. Check D-reasons in generated HTML
grep -o '"reason":"[^"]*"' data/output/dashboard_*.html | sort | uniq -c

# 3. Full test suite
python -m pytest tests/ -q

# 4. Confirm schema migration ran (new columns exist)
python -c "
import sqlite3
conn = sqlite3.connect('data/pipeline.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(company_records)').fetchall()]
print('hubspot_company_id:', 'hubspot_company_id' in cols)
print('hubspot_contact_id:', 'hubspot_contact_id' in cols)
conn.close()
"
```

Expected:
- D-reasons show real categories (Unpassende_Branche, OEM_Hersteller, etc.), not all "unknown"
- `hubspot_company_id: True`, `hubspot_contact_id: True`
- 162 tests pass (or more if new tests added)

---

## AI validation results

Run 2026-03-27:

- `python pipeline.py dashboard` → Dashboard written (4683 KB), 0 errors
- `python -m pytest tests/ -q` → **162 passed**
- `hubspot_company_id: True`, `hubspot_contact_id: True` (schema migration ran)
- D-reasons query verified live against DB:
  - 60 unknown (old records without reclassify_reason, handled by COALESCE)
  - 28 Unpassende_Branche, 8 OEM_Hersteller, 5 Zu_Klein, 3 Krankenhaus, 3 Kein_Service, 3 Handwerk, 2 Dental, 2 Ausland, 2 Apotheke
- HTML checks: title "ALLEX — Repuro Dashboard" ✓, header-logo ✓, Classification guide legend ✓, HUBSPOT_PORTAL_ID = 144578192 ✓

---

## User validation walkthrough

1. `python pipeline.py dashboard --serve` → opens localhost:8080
2. Verify title tab reads "ALLEX — Repuro Dashboard"
3. Verify ALLEX logo appears top-right in dark header bar
4. Click "Classification guide" — legend expands with 6 rows, color-coded badges
5. Go to Lead Table tab — klass column shows colored badges (A=green, B=blue, grey for rest)
6. Go to Overview tab — D-Reasons chart should show named categories, not all "unknown"
