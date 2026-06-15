# DX Overhaul — Frontend Module Split + Dev Tooling

**Status:** Codex-reviewed — revised 2026-05-11
**Scope:** Restructure `dashboard_v2.html` (4,100 lines) into modular JS/CSS files with build-time concatenation, add hot reload and dev tooling.

---

## Problem Statement

The ALLEX dashboard is a single-file monolith: 1,284 lines CSS + 2,774 lines JS + HTML in one file. Every edit requires reading the full file (~35k tokens), changes have unbounded blast radius due to shared global state, and every template change requires a full server restart (10s+ DB load + HTML build).

This compounds: every future feature costs more tokens, takes longer to implement, and is harder to review.

## Design Constraints

1. **No external build tools** (webpack, vite, esbuild) — the project uses Python + vanilla JS, no Node.js in the stack.
2. **Single-file deployment** — Fly.io serves a single HTML blob. The split must be invisible to the deployed artifact.
3. **No ES modules** — vanilla JS with globals. The split must preserve this (no import/export), at least in Phase 1.
4. **Backend serves template** — `_build_html()` in `dashboard.py` does string replacements (`__DATA_JSON__`, `__SERVE_MODE_JS__`, etc.). The build step already exists.
5. **Two consumers** — dev server (port 8082, `--serve`) and static HTML export (read-only dashboards). Both must work.

## Architecture: Build-Time Concatenation

### How it works

1. JS and CSS live in separate files under `src/pipeline/templates/`:
   ```
   templates/
     dashboard_v2.html          # Shell: <head>, <body>, <style>/__CSS__</style>, <script>/__JS__</script>
     css/
       tokens.css               # CSS variables, reset
       layout.css               # App grid, sidebar, top bar
       queue.css                # Queue list, search, chips
       record.css               # Record editor, fields, status cards
       preview.css              # Letter/site preview tabs
       analytics.css            # Funnel, cohort, dropoff, activity
       modals.css               # Toast, What's New modal
     js/
       state.js                 # Global state vars, DATA, activeIdx, selectedBA
       helpers.js               # fmt, escapeHtml, formatDateDE, missingFor, isExportEligible
       api.js                   # patchCompany, undoLastChange, postApi, getActor/setActor
       router.js                # Mode/sub switching, renderCurrent, renderSubnav, applyTopTitle
       queue.js                 # renderReviewList, renderQueue, renderQueueChips, matchesQueueFilter
       record-editor.js         # renderRecord HTML generation (~500 lines)
       record-editor-events.js  # event listener bindings and keyboard shortcuts (~400 lines)
       preview.js               # renderLetterPreview, buildFallbackLetter, siteHtml, section review
       leads-table.js           # renderReviewLeads, renderLeadsTable, exportLeadliste
       analytics-dropoff.js     # renderReviewDropoff, _computeDropoff*
       analytics-activity.js    # renderReviewActivity, renderActivityData
       analytics-export.js      # renderExportView
       analytics-followup.js    # renderFollowUpView
       analytics-funnel.js      # renderAnalyzeFunnel
       analytics-cohorts.js     # renderAnalyzeCohorts, renderAnalyzeClasses
       analytics-bottlenecks.js # renderAnalyzeBottlenecks
       init.js                  # DOM refs, event listeners, What's New modal, startup sequence
   ```

2. `_build_html()` reads the shell HTML, concatenates CSS files into `__CSS__` and JS files into `__JS__`, then performs existing replacements (`__DATA_JSON__`, etc.).

3. **Load order matters** (globals must be declared before use):
   ```
   state.js → helpers.js → api.js → router.js → queue.js → record-editor.js →
   record-editor-events.js → preview.js → leads-table.js → analytics-*.js → init.js
   ```
   Defined in a `JS_LOAD_ORDER` list in `dashboard.py`. CSS order: tokens first, then any order.

### Dependency contracts

Each JS file starts with a `// requires: <comma-separated module names>` header. Example:
```js
// requires: state, helpers
```
The Python concatenator reads these headers and verifies that every required module appears earlier in `JS_LOAD_ORDER`. Build fails with a clear error if a dependency is out of order or missing. This is a lightweight guard — not symbol-level validation, just module-order enforcement.

4. The output is still a single HTML blob — no behavioral change for deployment or static export.

### Why not `<script src=>`?

- Would require the HTTP server to handle static file routes
- Breaks the static HTML export (no server = no JS)
- Adds N network requests per page load
- Build-time concat is simpler, preserves existing behavior

### Why not ES modules?

- Requires a transpiler or native `<script type="module">` which changes scoping rules
- All 2,774 lines of JS use globals — converting to modules is a rewrite, not a restructure
- Phase 1 goal is file-level isolation, not architectural modernization

### CSS load order

CSS order is NOT arbitrary — later files can override earlier selectors. Define `CSS_LOAD_ORDER` in `dashboard.py` alongside `JS_LOAD_ORDER`:
```python
CSS_LOAD_ORDER = [
    "tokens.css",    # variables first
    "layout.css",    # grid structure
    "queue.css",
    "record.css",
    "preview.css",
    "analytics.css",
    "modals.css",
]
```

## Module Dependency Graph

```
state.js          ← no dependencies (declares globals)
  ↓
helpers.js        ← reads DATA, state vars
  ↓
api.js            ← reads state, calls helpers
  ↓
router.js         ← calls all render* functions, reads state
  ↓
queue.js          ← calls helpers (sortedRows, getFilteredRows)
record-editor.js        ← calls api, helpers, preview (HTML generation)
record-editor-events.js ← calls api, helpers (event wiring, keyboard shortcuts)
preview.js              ← calls helpers
leads-table.js    ← calls helpers, api
analytics-*.js    ← calls helpers, reads DATA (mostly independent)
  ↓
init.js           ← wires everything: DOM refs, event listeners, startup
```

All modules share globals via the window scope. No import/export. The load order ensures declarations precede usage.

## Implementation Phases

### Phase 1: Build-time concatenation infrastructure (2-3 hours)

0. Create `scripts/dev.ps1` and `scripts/dev.sh` one-liner to start the dev server.

1. Add `_concat_css()` and `_concat_js()` to `dashboard.py`:
   - Read files from `templates/css/` and `templates/js/` in defined order
   - Return concatenated string
   - Error if any file in `JS_LOAD_ORDER` is missing

2. Modify `_build_html()`:
   - Replace `__CSS__` placeholder with concatenated CSS
   - Replace `__JS__` placeholder with concatenated JS
   - Keep all existing `__DATA_JSON__` / `__SERVE_MODE_JS__` replacements (these go into `state.js` as placeholders)

3. Create the shell `dashboard_v2.html`:
   - Just HTML structure + `<style>__CSS__</style>` + `<script>__JS__</script>`
   - ~50 lines

4. **Verification**: functional parity checks — (a) all `__PLACEHOLDER__` tokens resolved (assertion in `_build_html()`), (b) serve mode: all views render without JS console errors, (c) static export: opens in browser and displays data. Byte-identical output is NOT required — whitespace differences from concatenation are expected.

### Phase 2: Extract modules (3-4 hours, incremental)

Extract one module at a time, verify after each:

1. `state.js` — global vars, injected constants (`SERVE_MODE`, `DATA`, `REGION_MAPPING`, etc.)
2. `helpers.js` — pure functions (fmt, escapeHtml, missingFor, etc.)
3. `api.js` — patchCompany, postApi, undoLastChange, getActor/setActor, showToast
4. `router.js` — mode switching, renderCurrent, renderSubnav
5. `queue.js` — renderReviewList, renderQueue, renderQueueChips, populateBaSelect, batchSend
6. `preview.js` — renderLetterPreview, buildFallbackLetter, siteHtml, section review
7. `record-editor.js` — renderRecord HTML generation (~500 lines)
8. `record-editor-events.js` — event listener bindings and keyboard shortcuts extracted from renderRecord (~400 lines). Zero behavior change — just file separation at the natural seam between DOM generation and event wiring.
9. `leads-table.js` — renderReviewLeads, renderLeadsTable, exportLeadliste
10. `analytics-*.js` — one file per view (dropoff, activity, export, followup, funnel, cohorts, bottlenecks)
11. `init.js` — DOM refs, event listener wiring, What's New modal, startup IIFE
12. CSS files — split by section (tokens, layout, queue, record, preview, analytics, modals)

**Verification per step**: restart server, open dashboard, click through all views, verify no JS errors in console.

### Phase 3: Hot reload (1-2 hours)

1. Add `--watch` flag to dashboard serve mode
2. Use `watchdog` library (or `os.stat` polling as zero-dep fallback) to monitor `templates/` directory
3. On file change: rebuild to temp buffer, then atomically swap `_DashboardHandler._html_content`
4. Inject a build timestamp into HTML (`__BUILD_TS__`) so the developer can verify they're seeing fresh content
5. In `--watch` mode, set response headers `Cache-Control: no-store` to prevent browser caching stale builds
6. No browser auto-refresh needed — manual F5 is fine (avoids WebSocket complexity)
7. Server stays running — no restart, no DB reload

### Phase 4: Changelog automation (1 hour)

Add to `/deploy` skill:
1. Parse `git log main..dev --oneline` for conventional commit prefixes
2. Group by `feat:`, `fix:`, `refactor:`, etc.
3. Generate draft CHANGELOG entry
4. Show to Roman for confirmation before writing

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| JS load order breaks silently | `JS_LOAD_ORDER` is explicit; missing file = build error. Console error check in verification. |
| String replacements break when split across files | All `__PLACEHOLDER__` tokens go in `state.js` only — single file to check |
| Concatenation changes whitespace/behavior | Functional parity checks in Phase 1 — placeholder assertion, console error check, static export test. Byte-identical output not required. |
| `record-editor.js` + `record-editor-events.js` combined ~900 lines | Split at the DOM-generation / event-wiring seam. Each file stays under the 500-line ceiling. |
| `watchdog` adds a dependency | Fallback to `os.stat` polling (check mtime every 2s). Zero new deps if needed. |
| Placeholder leak to output | `_build_html()` asserts no `__X__` tokens remain in final HTML. Build fails if any placeholder is unresolved. |
| Static export regression | Phase 1 verification includes opening the exported HTML file in a browser — not just serve mode. |

## Not In Scope

- ES module conversion (import/export)
- Component framework (React, Lit, etc.)
- CSS preprocessor (Sass, PostCSS)
- Splitting `renderRecord()` into sub-functions (future task)
- TypeScript
- Unit tests for JS functions (DX5, depends on this work being done first)

## Module Contracts

Each module file documents what it reads and writes at the top, in a `templates/MODULES.md` file:

| Module | Reads (globals) | Writes (globals) | Calls |
|--------|----------------|------------------|-------|
| state.js | — | DATA, activeIdx, selectedBA, mode, sub, queueSort, queueFilter, ... | — |
| helpers.js | DATA | — | — |
| api.js | state vars | — | helpers |
| router.js | mode, sub | mode, sub | all render* functions |
| queue.js | state vars | activeIdx | helpers, api |
| record-editor.js | DATA, activeIdx | — | api, helpers, preview |
| record-editor-events.js | DATA, activeIdx | activeIdx | api, helpers |
| ... | ... | ... | ... |

New globals require updating this table. This prevents re-sprawl after the split.

## Success Criteria

1. No single JS/CSS source file exceeds 500 lines (record-editor.js is now split into two files)
2. `_build_html()` output is functionally identical to current
3. Template change → visible in browser within 2 seconds (hot reload, no server restart)
4. `scripts/dev.ps1` starts the dev server in one command
5. All dashboard views work: Review (BA Prep, Leads, Drop-off, Activity, Export, Follow-up) + Analyze (Funnel, Cohorts, Classes, Bottlenecks)
