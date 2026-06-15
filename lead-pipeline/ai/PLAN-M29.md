# M29: Dashboard v2 UX/UI Redesign — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to execute task-by-task. Complete Task 0 first; Tasks 1–5 may then run in order (they have cross-task dependencies noted below — do NOT treat them as fully parallel).

**Goal:** Fix the 8 UX/UI issues identified in the Codex review (`reviews/2026-04-28-1723-frontend-ux.md`). v2 becomes the daily-usable default after this milestone. v1 rollback must work via `--v1` flag.

**Source of truth for all issues:** `reviews/2026-04-28-1723-frontend-ux.md` + `ai/UI-ISSUES.md` (open section).

**Target files:**
- `src/pipeline/templates/dashboard_v2.html` — all frontend changes (Tasks 0b–5)
- `src/pipeline/dashboard.py` — `_template_name()` only (Task 0a)
- `pipeline.py` — CLI flag only (Task 0a)

**No backend API changes. Do not modify `dashboard_v1.html` or `dashboard.html`.**

**Test gate after every task:** `python -m pytest tests/test_dashboard.py -q` — must show 22 passed.

**Cross-task dependency:** Task 2 renames the ownership buttons (`Resolve`→`Eigentümer prüfen`, `Pass`→`Kein Konzern`). Task 5b must NOT re-rename them — just verify they are correct. If Tasks are executed in order 0→1→2→3→4→5 this is handled automatically.

**XSS rule (applies to all tasks):** Any DB-backed value inserted into HTML strings MUST be wrapped in `escapeHtml()`. This includes: `owner_name`, `gesellschafter_name`, `ownership_reason`, `all_gesellschafter` parsed fields, `full_name`. The `escapeHtml` function already exists in the file. Failure to wrap = XSS vulnerability.

---

## Task 0 — `--v1` rollback flag + `patchCompany` ok-check

**Files:** `pipeline.py`, `src/pipeline/dashboard.py`, `src/pipeline/templates/dashboard_v2.html`

### 0a — Wire `--v1` flag (pipeline.py + dashboard.py)

**In `pipeline.py`**, find the `dashboard` subcommand argument parser. It currently has `--v2`. Add `--v1` as mutually exclusive:
```python
# Find the existing: parser_dashboard.add_argument('--v2', ...)
# Add immediately after:
parser_dashboard.add_argument('--v1', action='store_true', default=False,
                               help='Force v1 template (rollback from v2)')
# Also add mutual exclusivity check after parsing:
if getattr(args, 'v1', False) and getattr(args, 'v2', False):
    parser_dashboard.error('--v1 and --v2 are mutually exclusive')
```

**In `src/pipeline/dashboard.py`**:
- Add module-level: `_USE_V1: bool = False`
- Update `_template_name()`:
  ```python
  def _template_name() -> str:
      if _USE_V1:
          return "dashboard_v1.html"
      return "dashboard_v2.html" if _USE_V2 else "dashboard.html"
  ```
- In the `serve()` function (or wherever `_USE_V2` is set from `args.v2`), add:
  ```python
  global _USE_V1
  _USE_V1 = getattr(args, 'v1', False)
  ```
  Both `_USE_V1` and `_USE_V2` must be explicitly set on every invocation (not just when True) to prevent sticky state from prior invocations.

### 0b — `patchCompany()` must check `resp.ok` (dashboard_v2.html)

Find `async function patchCompany(domain, updates)` (~line 1086). Current body:
```js
const actor = getActor();
const resp = await fetch('/api/company/' + encodeURIComponent(domain) + '?actor=' + actor, {
  method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(updates),
});
return resp.json();
```

Replace with (preserve `?actor=` parameter):
```js
const actor = getActor();
const resp = await fetch('/api/company/' + encodeURIComponent(domain) + '?actor=' + actor, {
  method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(updates),
});
if (!resp.ok) {
  const text = await resp.text().catch(() => resp.statusText);
  throw new Error('PATCH ' + domain + ' failed (' + resp.status + '): ' + text);
}
return resp.json();
```

All existing callers that use `.catch(function(){})` (silent swallow) — replace with `.catch(function(e){ console.warn('patchCompany silent fail:', e); })`. Do NOT add modal alerts to these callers — only the ownership/approval callers (Tasks 1–2) get that.

**AC:**
- `python pipeline.py dashboard --v1` serves `dashboard_v1.html` (verify via page title or HTML comment)
- `python pipeline.py dashboard` serves current default (unchanged for now — promotion happens at end of milestone)
- `python pipeline.py dashboard --v2` still serves `dashboard_v2.html`
- `python pipeline.py dashboard --v1 --v2` prints an error and exits
- Failed PATCH logs to console.warn in devtools
- 22 tests pass

---

## Task 1 — Export gate: `isExportEligible()` + approval pessimism

**Files:** `src/pipeline/templates/dashboard_v2.html` only

### 1a — `isExportEligible(r)` helper

**Important:** `missingFor(r)` returns ALL required fields with severity info. The pre-computed `r._missing` field (set in `sortedRows()` and `renderLeadsTable()`) counts how many fields have `severity !== 'done'`. For records from `sortedRows()`, use `r._missing`. For raw `DATA.records` (which don't have `_missing`), compute it inline.

Add at module scope near `missingFor`:
```js
function isExportEligible(r) {
  var missing = (r._missing !== undefined)
    ? r._missing
    : missingFor(r).filter(function(m){ return m.severity !== 'done'; }).length;
  return missing === 0 && r.approved_for_sendout == 1;
}
```

Replace ALL "Bereit" / "exportbereit" UI logic that currently only checks `_missing === 0` or `blockingCount === 0`:

1. **Queue row badge** (~line 1426): change `if (miss === 0) { sev = 'ok'; stat = 'Bereit'; }` to `if (isExportEligible(r)) { sev = 'ok'; stat = 'Bereit'; } else if (miss === 0) { sev = 'warn'; stat = 'Freigabe fehlt'; }`
2. **Record editor Was-fehlt "Bereit zum Export" message** (~line 1523): change `if (allDone)` to `if (isExportEligible(r))`. The `allDone = blockingCount === 0` case where approval is missing should instead show: "Alle Felder gefüllt — Freigabe noch ausstehend" in warn color.
3. **Export KPI card** (~lines 1510–1530): change the ready count from `allDone` to `DATA.records.filter(isExportEligible).length`. Show that count as the headline number.
4. **Export preview in confirm** — before the `exportPdf()` POST, build a preview list: `var eligible = DATA.records.filter(isExportEligible); var names = eligible.slice(0,8).map(function(r){ return r.full_name || r.domain; }).join('\n'); if (!confirm(eligible.length + ' Records werden exportiert:\n' + names + (eligible.length > 8 ? '\n…und ' + (eligible.length - 8) + ' weitere' : '') + '\n\nFortfahren?')) return;`

### 1b — Pessimistic approval toggle (BA-Prep editor)

Find the approval toggle handler (~line 1976). Replace with this pattern that correctly separates PATCH failure from refresh failure:
```js
var prev = rec.approved_for_sendout;
rec.approved_for_sendout = newVal;  // optimistic for immediate UI feedback
el.disabled = true;
try {
  await patchCompany(rec.domain, { approved_for_sendout: newVal });
  // PATCH succeeded — now refresh DATA (failure here is non-fatal since DB is already correct)
  try {
    var resp = await fetch('/api/data');
    DATA = await resp.json();
  } catch (refreshErr) {
    console.warn('DATA refresh failed after approval PATCH; UI may be stale', refreshErr);
  }
  renderQueue();
  renderRecord();
} catch (patchErr) {
  // PATCH failed — DB unchanged, revert optimistic update
  rec.approved_for_sendout = prev;
  alert('Freigabe konnte nicht gespeichert werden: ' + (patchErr.message || patchErr));
  renderRecord();
} finally {
  el.disabled = false;
}
```

Apply the same pessimistic pattern to the Lead-Liste approved checkbox handler (~line 2442).

**AC:**
- Record with `approved_for_sendout = 0` (even if all fields filled) shows "Freigabe fehlt" in warn color, NOT green "Bereit"
- Record with `approved_for_sendout = 1` AND all fields filled shows green "Bereit"
- Export confirm shows "N Records werden exportiert: [names]…"
- Failed approval PATCH shows alert and reverts checkbox
- Successful PATCH but failed refresh logs warning (does NOT revert checkbox)
- 22 tests pass

---

## Task 2 — Ownership section redesign (de-duplication)

**Files:** `src/pipeline/templates/dashboard_v2.html` only
**Dependency:** Must complete before Task 5 (Task 5 skips the button renames handled here).

### Problem
Owner name shown in 4 places; `pipeline_stage` shown as raw text; Resolve/Pass/Exclude buttons have English labels.

### Surviving element IDs (must keep these exact IDs for existing handlers to work)
- `#parent-name-input` — the ownership name text input (keep this ID; the Resolve handler depends on it)
- `#btn-resolve` (`btnResolve` in JS) — Resolve button
- `#btn-pass` (`btnPass` in JS) — Pass button (will be relabeled "Kein Konzern")
- `#btn-exclude` (`btnExclude` in JS) — Exclude button (will be relabeled "Ausschließen")

### Remove these:
- `renderHerkunft(r)` call from `renderRecord()` — delete both the call and the function definition
- Standalone `gesellschafter_name` editable field from Stammdaten section (the `wb('field-gesellschafter-name', ...)` writeback binding in `setupEditorPanel()` should also be removed)
- Raw `pipeline_stage` field display (wherever it appears as a visible label+value pair)

### Unified ownership block (replaces `sec-gesellschafter` interior)

```
┌─ Gesellschafter ─────────────────── [status chip] ─┐
│  [Name, Age J. · Share% · Type]                      │
│  Grundlage: [ownership_reason, max 80 chars]          │
│  ─────────────────────────────────────────────────    │
│  [chip: Person A 80%]  [chip: Person B 20%]  [▼ N]  │
│  ─────────────────────────────────────────────────    │
│  [input#parent-name-input placeholder="Eigentümer…"] │
│  [#btn-resolve: Eigentümer prüfen ▶]                 │
│  [#btn-pass: Kein Konzern ✓]  [#btn-exclude: Ausschließen ✗] │
└──────────────────────────────────────────────────────┘
```

**Null/empty rules for new block:**
- Primary owner row: if `r.gesellschafter_name` is null/empty → show `'—'`; no age/share if those fields are null
- Rationale row: if `r.ownership_reason` is null/empty → omit the row entirely
- Chips row: parse `r.all_gesellschafter` as JSON; if parse fails or empty → omit chips row; if 1 entry → show inline, no collapse; if 2 → show both; if 3+ → show first 2 + `▼ N weitere` toggle
- Status chip: `r.pipeline_stage === 'ownership_review_needed'` → orange "Prüfung ausstehend"; `r.pipeline_stage === 'ownership_gated'` → green "Kein Konzern"; `r.klass === 'S'` → grey "Ausgeschlossen"; else → no chip

**`ownerAge()` helper** (add at module scope):
```js
function ownerAge(r) {
  return r.gesellschafter_age ? ', ' + r.gesellschafter_age + ' J.' : '';
}
```

**All new owner name/reason strings MUST use `escapeHtml()`.**

**Confirm dialog** (add at top of `btnExclude` click handler):
```js
if (!confirm('Diesen Eintrag als Tochtergesellschaft ausschließen (Klass S)?')) return;
```

**Confirm dialog for Pass/Kein Konzern** (add at top of `btnPass` handler):
```js
if (!confirm('Diesen Eintrag als "Kein Konzern" markieren und in Briefvorbereitung weiterleiten?')) return;
```

**New CSS** (add to `<style>` block):
```css
.owner-primary { font-size: 13px; font-weight: 500; }
.owner-rationale { font-size: 11px; color: var(--ink-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 3px 0; }
.owner-chips { display: flex; flex-wrap: wrap; gap: 5px; padding: 6px 0; }
.owner-chip { font-size: 11px; padding: 2px 8px; border-radius: 20px; background: var(--surface-2); border: 1px solid var(--line); }
.ownership-status-chip { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 20px; letter-spacing: 0.04em; }
.ownership-status-chip.pending  { background: var(--warn-soft); color: var(--warn); }
.ownership-status-chip.passed   { background: var(--ok-soft); color: var(--ok); }
.ownership-status-chip.excluded { background: var(--surface-2); color: var(--ink-3); }
```

**AC:**
- Owner name appears exactly once in the main display row
- `renderHerkunft` not called anywhere in render path (grep confirms)
- Standalone `gesellschafter_name` field NOT in Stammdaten
- `pipeline_stage` raw text NOT shown
- Age shown when `gesellschafter_age` is set (e.g. "Max Mustermann, 54 J. · 100% · Person")
- Ownership chips shown for multi-shareholder records; "▼ N weitere" for 3+
- "Eigentümer prüfen", "Kein Konzern", "Ausschließen" visible as button labels
- Both buttons show confirm dialog before executing
- `#parent-name-input`, `#btn-resolve`, `#btn-pass`, `#btn-exclude` IDs still present in rendered HTML
- 22 tests pass

---

## Task 3 — Salutation auto-compute (`autoSalutation`)

**Files:** `src/pipeline/templates/dashboard_v2.html` only

### Module-scope helpers

```js
function buildSalutation(anrede, ownerName) {
  if (!ownerName) return '';
  var parts = ownerName.trim().split(/\s+/);
  var nachname = parts[parts.length - 1] || '';
  var a = (anrede || '').trim();
  if (!a || a === 'Herr') return 'Sehr geehrter Herr ' + nachname;
  if (a === 'Frau') return 'Sehr geehrte Frau ' + nachname;
  return 'Sehr geehrte Damen und Herren';
}

function applyAutoSalutation(rec) {
  if (!rec.owner_name) return;  // no-op when owner_name is cleared — avoid overwriting with empty
  var newSal = buildSalutation(rec.anrede, rec.owner_name);
  if (!newSal) return;
  rec.salutation = newSal;
  var salEl = document.getElementById('field-salutation');
  if (salEl) salEl.value = newSal;
  if (SERVE_MODE) patchCompany(rec.domain, { salutation: newSal })
    .catch(function(e){ console.warn('salutation PATCH failed:', e); });
    // salutation PATCH failure is non-fatal — owner PATCH already succeeded
}
```

### Trigger inside `setupEditorPanel()`

Find the `field-owner-name` blur handler and the `field-anrede` change handler. In both, call `applyAutoSalutation(rec)` AFTER the existing `patchCompany` call (not before — so owner_name is already persisted first):

```js
// Inside field-owner-name blur handler, after existing patchCompany line:
applyAutoSalutation(rec);

// Inside field-anrede change handler, after existing patchCompany line:
applyAutoSalutation(rec);
```

### Consistency warning in `renderRecord()`

Locate the salutation field rendering in `renderRecord()` (the line that renders `r.salutation` as a form field, in the Stammdaten/Ansprechpartner area). Immediately AFTER that field's closing HTML, append:

```js
var ownerSurname = (r.owner_name || '').trim().split(/\s+/).pop() || '';
var salMismatch = ownerSurname && (r.salutation || '') && !(r.salutation || '').includes(ownerSurname);
if (salMismatch) {
  html += '<div class="field-warn">⚠ Anrede stimmt möglicherweise nicht mit Ansprechpartner überein — Ansprechpartner erneut speichern um zu aktualisieren</div>';
}
```

CSS (add to `<style>`):
```css
.field-warn { font-size: 11px; color: var(--warn); background: var(--warn-soft); padding: 4px 8px; border-radius: 4px; margin-top: 4px; }
```

**AC:**
- Changing `owner_name` and tabbing out updates `salutation` field value in UI and PATCHes DB
- Changing `anrede` dropdown updates `salutation`
- Warning chip renders below salutation field when surname doesn't match
- Clearing `owner_name` does NOT wipe the existing salutation
- 22 tests pass

---

## Task 4 — Chrome consolidation (single teal subnav bar)

**Files:** `src/pipeline/templates/dashboard_v2.html` only
**Complexity:** High — grid layout, DOM restructure, JS handler updates.

### Grid change

Find in CSS (currently ~line 63):
```css
grid-template-rows: var(--top-h) 40px 1fr;
grid-template-areas: "side top" "side subnav" "side main";
```
Replace with:
```css
grid-template-rows: var(--top-h) 1fr;
grid-template-areas: "side subnav" "side main";
```
Remove `grid-area: top` CSS rule for `.top`. Remove `.top` CSS class entirely.

### Remove `.top` HTML block

The `.top` HTML block contains: logo, title (`#top-title`), subtitle (`#top-sub`), live badge, BA select, tweaks button (`#toggle-tweaks`). Before removing, migrate content:
- Logo → move as `<div class="subnav-logo">__LOGO_IMG__</div>` at the START of `.subnav`, before the first `.subnav-item`
- Live badge → move to `.subnav-right` div (create this if not present) at END of `.subnav`
- BA select + label → move to `.subnav-right`
- `#toggle-tweaks` button → move to `.subnav-right`
- `#top-title` and `#top-sub` → delete; these are decorative only

After moving content, delete the entire `.top` HTML block.

**JS handler updates** — search `dashboard_v2.html` for these references and update:
- Any JS that reads `document.getElementById('top-title')` or `document.getElementById('top-sub')` → remove those lines (they were decorative updates)
- Any JS that references the BA select by its old `.top-ba select` or `#ba-sel` selector → verify it still works with the element now in `.subnav-right`. The select element ID (`#ba-sel` or similar) must be preserved.
- `#toggle-tweaks` → still functions identically, now in `.subnav-right`

### Teal subnav CSS

Add/replace `.subnav` and related rules:
```css
.subnav {
  background: var(--spar);
  border-bottom: none;
  height: var(--top-h);
}
.subnav-item { color: rgba(255,255,255,0.7); }
.subnav-item:hover { color: white; background: rgba(255,255,255,0.12); }
.subnav-item.active { color: white; border-bottom-color: white; background: transparent; }
.subnav-item.active .subnav-hint { color: rgba(255,255,255,0.7); }
.subnav-hint { color: rgba(255,255,255,0.55); }
.subnav-logo { height: var(--top-h); padding: 0 10px 0 4px; display: flex; align-items: center; }
.subnav-logo img { height: 22px; filter: brightness(0) invert(1); }
.subnav-right { display: flex; align-items: center; gap: 10px; margin-left: auto; padding-right: 14px; }
.subnav-ba-label { font-size: 11px; color: rgba(255,255,255,0.7); white-space: nowrap; }
.subnav-ba select {
  background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.3);
  color: white; border-radius: 4px; padding: 4px 24px 4px 8px; font-size: 12px;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
}
.subnav-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; padding: 2px 7px; border-radius: 3px; background: rgba(255,255,255,0.2); color: white; }
.subnav-badge.static { background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.6); }
```

**AC:**
- Only one horizontal bar visible above main content (sidebar nav + single subnav)
- Subnav background is `#0891B2` teal
- Logo visible (white-inverted) at left of subnav
- Live badge and BA select visible at right
- `#toggle-tweaks` accessible
- All 4 tab switches work (renderSubnav still activates correct `.subnav-item.active`)
- No JS errors on load (`console.error` clean)
- 22 tests pass

---

## Task 5 — Was-fehlt styling + language polish

**Files:** `src/pipeline/templates/dashboard_v2.html` only
**Note:** Button renames (Eigentümer prüfen / Kein Konzern) are handled by Task 2 — DO NOT re-rename here. Only verify they are correct.

### 5a — Was-fehlt group styling

Find `.miss-group` CSS (~line 540). Replace/extend with:
```css
.miss-group {
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: 6px;
  margin-bottom: 6px;
  overflow: hidden;
  cursor: pointer;
}
.miss-group:last-child { margin-bottom: 0; }
```

In the JS that renders each miss group (find `'<div class="miss-group"'`), verify the group HTML uses this structure:
```html
<div class="miss-group" data-scroll="...">
  <div class="miss-group-header">
    <div class="mg-dot ..."></div>
    <div class="mg-label">...</div>
    <div class="mg-count ...">...</div>
    <div class="mg-action">...</div>
  </div>
</div>
```

Add CSS for header:
```css
.miss-group-header { display: flex; align-items: center; gap: 10px; padding: 8px 12px; font-weight: 500; font-size: 12px; }
.miss-group-header:hover { background: var(--surface-3); }
```

### 5b — Language polish (verify + remaining labels)

Verify from Task 2 (these should already be done):
- `Eigentümer prüfen` ✓
- `Kein Konzern` ✓

Additionally replace in `dashboard_v2.html` (UI strings only, not JS variable names or API endpoints):

| Find (exact label text in HTML/JS string) | Replace with |
|---|---|
| `>Auswertung<` OR `>Analyze<` in subnav label | `>Auswertung<` |
| `>Änderungslog<` OR `>Activity Log<` in subnav label | `>Änderungslog<` |

Move all `· DB-Feld …` `<span class="src">` annotations: set their CSS to `display:none` (do not delete — they are useful for debugging). Example:
```html
<!-- Before: -->
<span class="src">· DB-Feld gesellschafter_name</span>
<!-- After: -->
<span class="src" style="display:none">· DB-Feld gesellschafter_name</span>
```

**AC:**
- Was-fehlt groups have `--surface-2` background + border
- Subnav tabs show "Auswertung" and "Änderungslog"
- `DB-Feld` text not visible (display:none)
- "Eigentümer prüfen" and "Kein Konzern" confirmed correct (from Task 2)
- 22 tests pass

---

## Promotion gate (run after all Tasks 0–5 complete)

1. In `dashboard.py` `_template_name()`: change the no-flag default from `"dashboard.html"` to `"dashboard_v2.html"`:
   ```python
   def _template_name() -> str:
       if _USE_V1:
           return "dashboard_v1.html"
       if _USE_V2:
           return "dashboard_v2.html"
       return "dashboard_v2.html"  # v2 is now default
   ```
2. Update `ROADMAP.md`: mark M29 ✅, update Current State block with v2 as default
3. Update this file with `## Validation Results` section per task

**After this commit: `python pipeline.py dashboard` serves v2. `python pipeline.py dashboard --v1` serves v1.**

---

## Validation Results

Executed 2026-04-29 via subagent-driven development. All tasks complete, 22 tests pass after each.

### Task 0 — `--v1` rollback flag + `patchCompany` ok-check
**AC outcome: ✅ PASS**
- `_USE_V1` module variable added to dashboard.py; `_template_name()` returns v1/v2/default correctly
- `--v1` flag added to dashboard parser; `--v1 --v2` mutual exclusivity error on stderr + exit(2)
- `_run_dashboard()` sets both flags on every invocation (not just when True)
- `patchCompany()` throws on `!resp.ok`; all `.catch(function(){})` patterns replaced with `console.warn`
- Fix applied: misleading "patchCompany silent fail" label on `/api/data` fetch corrected
- Commits: cf46db2, bed0b66, 9e43815

### Task 1 — Export gate: `isExportEligible()` + approval pessimism
**AC outcome: ✅ PASS**
- `isExportEligible(r)` at module scope: checks `_missing === 0 && approved_for_sendout == 1`
- Queue badge: "Bereit" only when eligible; "Freigabe fehlt" (warn) when fields filled but not approved
- Was-fehlt: 3-way branch (eligible / fields-done-no-approval / missing fields)
- exportPdf(): zero-eligible early-return + "N Records werden exportiert" confirm
- Pessimistic BA-Prep approve toggle: PATCH first, revert + alert on failure
- Pessimistic Lead-Liste approved checkbox: same pattern, `renderLeadsTable()` after refresh
- Commits: 75666ab, 01fd848

### Task 2 — Ownership section redesign
**AC outcome: ✅ PASS**
- Unified ownership block: status chip + primary owner row (name/age/share/type) + rationale + chips
- `ownerAge()` helper added; all owner strings use `escapeHtml()`
- `renderHerkunft()` no longer called; `field-gesellschafter-name` standalone input removed
- `pipeline_stage` raw text not shown; `all_gesellschafter` chips with correct `g.pct` field
- Button labels: "Eigentümer prüfen ▶", "Kein Konzern ✓", "Ausschließen ✗"
- Confirm dialogs on btn-pass and btn-exclude
- `#parent-name-input`, `#btn-resolve`, `#btn-pass`, `#btn-exclude` IDs preserved
- Fix applied: `g.share_pct` → `g.pct`; allGsArr parsed before primary row build
- Commits: 6a601f3, 57ac2e3

### Task 3 — Salutation auto-compute
**AC outcome: ✅ PASS**
- `buildSalutation()` and `applyAutoSalutation()` at module scope
- `owner_name` blur → auto-updates salutation field + PATCHes DB
- `anrede` change → auto-updates salutation
- Clearing `owner_name` does NOT wipe existing salutation (early-return guard)
- Mismatch warning renders below salutation when surname doesn't match
- `.field-warn` CSS class added
- Fix applied: letter preview re-renders after auto-salutation update
- Commits: ff84685, d55d606

### Task 4 — Chrome consolidation (single teal subnav bar)
**AC outcome: ✅ PASS**
- Grid changed from 3 rows to 2 rows; `.top` area removed
- `<header class="top">` removed; logo/badge/BA-select/tweaks moved to `.subnav-right`
- `.subnav` CSS: `background: var(--spar)`, no border-bottom, teal single bar
- `renderSubnav()` writes into `#subnav-tabs` (not whole subnav innerHTML)
- `applyTopTitle()` null-guarded (top-title/top-sub elements removed)
- Fixes applied: `.subnav-ba` base CSS rule; `.subnav .icon-btn` white on teal
- Commits: task-4 feat, 3835887, 90383f7

### Task 5 — Was-fehlt styling + language polish
**AC outcome: ✅ PASS**
- `.miss-group`: card style with `var(--surface-2)` background + border + border-radius
- `.miss-group-header` wrapper div in each group row; hover uses `var(--surface-3)`
- "Analyze" → "Auswertung" in 2 locations (TITLES + sidebar tooltip)
- "Activity Log" → "Änderungslog" in 5 locations (SUBNAV_TITLES, SUBNAV items, h2 headings, error text)
- `.src { display: none; }` CSS rule added (debug annotations hidden, not deleted)
- "Eigentümer prüfen" / "Kein Konzern" confirmed from Task 2
- Commits: 4401b30, 53ea04e

### Promotion gate
- `_template_name()` default changed to `dashboard_v2.html`
- ROADMAP.md: M29 marked ✅, Current State block updated
- 22 tests pass on final state
