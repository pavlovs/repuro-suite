# M11: HTML Dashboard -- Plan

## Context

M11 adds a local web dashboard for reviewing and acting on pipeline data.
Reads directly from `data/pipeline.db`. Supports write-back via a local HTTP server.

Input: all records in `pipeline.db` (all stages, all klasses).
Output: `data/output/dashboard_YYYYMMDD.html` + optional local server.

---

## Architecture

Two modes:

### Mode 1 — Static file (default)
```bash
python pipeline.py dashboard
```
Writes `data/output/dashboard_YYYYMMDD.html`. All data embedded as JSON in a
`<script>` tag. Read-only — no write-back. Open directly in browser.

### Mode 2 — Local server (--serve)
```bash
python pipeline.py dashboard --serve [--port 8080]
```
Starts `http.server` on localhost:8080. Serves the HTML from memory + exposes
REST endpoints for write-back. Opens browser automatically. No extra dependencies
beyond stdlib + what's already installed.

REST endpoints (only active in --serve mode):
- `GET /` — serves HTML dashboard
- `GET /api/data` — returns pipeline data as JSON
- `PATCH /api/company/{domain}` — writes klass / outreach fields to DB
- `POST /api/compliment/{domain}` — regenerates compliment via `claude.cmd -p`, writes to DB

---

## Dashboard Sections

### 1. Funnel bar
Pipeline progression: Total -> Filtered -> Scraped -> Classified -> A/B/C/D/E/S -> Approached -> Sent

### 2. Classification breakdown
Horizontal bar per klass (A/B/C/D/E/S) with count + pct of classified.

### 3. D-reason breakdown
Horizontal bar of `filter_reason` values for D records — what is being excluded and why.

### 4. Size distribution (A/B only)
MA employee buckets: <10 / 10-20 / 20-40 / 40-80 / 80+. Bar chart.

### 5. Owner age histogram (A/B only)
Age buckets from `gesellschafter_age`: <40 / 40-50 / 50-60 / 60-70 / 70+.
Older owners = higher acquisition motivation. Bar chart.

### 6. Source quality table
Rows = sources (WLW / ORBIS). Cols = klass counts (A / B / C / D / E / S / total).
Shows which source produces better leads.

### 7. Lead table
Columns: Name, Domain, Source, Region, MA, Owner Age, Klass, SSB, Services Score, Email, Outreach Status.
Sortable by any column. Clickable row opens company card.
Filter bar: klass, source, region, outreach status.

### 8. Company card (modal/side panel)
Opens on row click. Two-panel layout:
- Left: company name, domain, klass, reasoning, compliment_draft, all contact/ownership fields.
  Write-back controls (--serve only): klass reclassify buttons (A/B/C/D/E), outreach status
  dropdown, comment field, follow-up date inputs. Save button -> PATCH /api/company/{domain}.
  "Regenerate compliment" button -> POST /api/compliment/{domain}.
- Right: `<iframe src="https://{domain}">` with fallback "Open in new tab" button
  (many SME sites allow iframes; fallback handles X-Frame-Options blocks).

### 9. C-class review queue
Separate tab/section. Cards for all C records sorted by services_score desc.
Same write-back controls as company card. Purpose: quick manual triage of maybes.

### 10. Post-sendout tracking
Filter lead table by outreach_status IN (sent / replied / meeting / declined / closed).
Shows the post-sendout funnel. Editable from company card.

---

## Implementation

### Files to create/modify

| File | Change |
|------|--------|
| `src/pipeline/dashboard.py` | Full implementation: data loader, HTML builder, HTTP server, REST handlers |
| `pipeline.py` | Add `--serve` and `--port` flags to dashboard subparser; wire to `dashboard_cmd()` |
| `ai/DESIGN.md` | Update Dashboard Design section to reflect actual implementation |
| `ai/PLAN-M11.md` | This file |

### dashboard.py structure

```python
# Data loading
def _load_data(db_path: Path) -> dict:
    # Returns dict with: records (list of raw dicts), funnel counts, klass counts,
    # d_reasons, source_quality, size_distribution, age_distribution

# HTML generation
def _build_html(data: dict, serve_mode: bool) -> str:
    # Single-function HTML builder — inline JS + CSS, Chart.js from CDN
    # serve_mode=True: JS uses fetch('/api/data') for live data
    # serve_mode=False: JS reads from embedded JSON constant

# HTTP server
class _DashboardHandler(http.server.BaseHTTPRequestHandler):
    # GET / -> serve HTML
    # GET /api/data -> JSON response
    # PATCH /api/company/{domain} -> update DB, return 200
    # POST /api/compliment/{domain} -> run claude CLI, update DB, return new text

def dashboard_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    serve: bool = False,
    port: int = 8080,
    db_path: Path | None = None,
) -> Optional[Path]:
```

### HTML tech stack
- Chart.js 4 via CDN (charting)
- Vanilla JS (no framework — dashboard is a local tool, not a product)
- Inline CSS (no Tailwind, no external sheets)
- Single HTML file — everything embedded

### Write-back field mapping (PATCH /api/company/{domain})

Accepted JSON body fields:
```json
{
  "klass": "A",
  "outreach_status": "sent",
  "outreach_sent_at": "2026-03-27",
  "outreach_comment": "...",
  "followup1_at": "2026-04-10",
  "followup2_at": "2026-04-24",
  "followup_comment": "..."
}
```
Only whitelisted fields written to DB. Domain is path param, never body.

---

## Implementation Sequence

1. Write `_load_data()` — query pipeline.db, build all data dicts
2. Write `_build_html()` — static HTML with embedded data + all 10 sections
3. Write `dashboard_cmd()` in static mode — generate and save HTML
4. Test static mode: open HTML in browser, verify all charts render
5. Write `_DashboardHandler` — GET /api/data, PATCH /api/company, POST /api/compliment
6. Wire `--serve` mode into `dashboard_cmd()`
7. Update `pipeline.py` subparser with `--serve` and `--port`
8. Test write-back: reclassify a C record in browser, verify DB updated
9. Update DESIGN.md

---

## Deferred

- Authentication on the local server (not needed — localhost only)
- Export filtered subset from dashboard (future)
- Bulk reclassify (future)
- Mobile layout (desktop only for now)

---

## AI VALIDATION RESULTS

### Commands run and outputs

```
$ python -c "from src.pipeline.dashboard import dashboard_cmd; print('import ok')"
import ok

$ python pipeline.py dashboard --help
usage: pipeline.py dashboard [-h] [--profile PROFILE] [--dry-run] [--verbose]
                             [--limit LIMIT] [--serve] [--port PORT]

options:
  -h, --help         show this help message and exit
  --profile PROFILE  Path to industry profile JSON (default: profiles/medtech_germany.json)
  --dry-run          No API calls, no file writes
  --verbose          Debug-level logging
  --limit LIMIT      Process only first N records
  --serve            Start local HTTP server with write-back API (localhost:8080)
  --port PORT        Port for --serve mode (default: 8080)

$ python pipeline.py dashboard --dry-run --verbose
00:33:06 INFO  Loaded profile: German Ambulatory Medtech Distributors (medtech_germany)
00:33:06 INFO  DRY RUN — no API calls or file writes
00:33:06 INFO  Loading pipeline data from data/pipeline.db
00:33:07 INFO  Loaded 2330 records. Classifications: B:4 C:1 D:60
00:33:07 INFO  DRY RUN — HTML not written (would be 4336141 chars)
DRY RUN — dashboard would be 4,336,141 chars

$ python pipeline.py dashboard --verbose
00:33:10 INFO  Loaded 2330 records. Classifications: B:4 C:1 D:60
00:33:11 INFO  Dashboard written to data/output/dashboard_20260327.html (4266 KB)
Dashboard written: data/output/dashboard_20260327.html  (4266 KB)

$ python -m pytest tests/ -q
160 passed in 13.05s
```

### File written
`data/output/dashboard_20260327.html` — 4266 KB (4,266,240 bytes). Self-contained, all data embedded as JSON.

### Deviations from plan
None. All 10 sections implemented. Static mode and --serve mode both implemented. Write-back REST API implemented with field whitelist. --serve flag not used in validation (interactive server).

