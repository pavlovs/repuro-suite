# M28 v2 Fix Specification

Generated: 2026-04-28
Audited by: Opus

## Summary

`dashboard_v2.html` is functional but ships with several Round 2 issues that block daily use: ownership workflow is hidden behind a collapsed section, several fields are duplicated or wrongly editable, the export button doesn't actually download, and the Repuro CI is only partially applied. About 30 distinct fixes are required across UX, data flow, accessibility-of-actions, and a handful of real JS bugs. None require a rewrite — all are localised inside the existing `dashboard_v2.html` template.

## File under change

All edits in this spec target a single file unless explicitly noted:
`src/pipeline/templates/dashboard_v2.html`

Reference file (for porting only — do not modify):
`src/pipeline/templates/dashboard_v1.html`

## Fix List

---

### F1 — Export PDF button does not download the file
**Type:** Bug
**Severity:** Critical
**Location:** `renderReviewList()`, KPI "ok" click handler (~lines 1332–1343)
**Problem:** The handler calls `fetch('/api/export-pdf', { method: 'POST' })` and reads the response as JSON, then alerts a count. The backend returns the actual PDF as a binary blob with `Content-Disposition` (see v1 line 1538). v2 never reads the blob and never triggers a download — so clicking "Bereit zum Export" appears to do nothing for the user.
**Fix:** Replace the handler body with the v1 pattern (port from `dashboard_v1.html` lines 1530–1559). Concretely:

```js
kpiOk.addEventListener('click', async function() {
  if (!SERVE_MODE) { alert('Export nur im Live-Modus verfügbar (serve-Modus benötigt)'); return; }
  if (!confirm('PDF-Export aller freigegebenen Records starten?')) return;
  const origLabel = kpiOk.querySelector('.kpi-cta');
  const oldText = origLabel ? origLabel.textContent : '';
  if (origLabel) origLabel.textContent = 'Generiert…';
  try {
    const resp = await fetch('/api/export-pdf', { method: 'POST' });
    if (!resp.ok) throw new Error(await resp.text());
    const blob = await resp.blob();
    const disp = resp.headers.get('Content-Disposition') || '';
    const m = disp.match(/filename="(.+?)"/);
    const fname = m ? m[1] : 'serienbriefe.pdf';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = fname; a.click();
    URL.revokeObjectURL(url);
    if (origLabel) origLabel.textContent = 'PDF heruntergeladen ✓';
    setTimeout(() => { if (origLabel) origLabel.textContent = oldText; }, 3000);
  } catch (e) {
    alert('Export fehlgeschlagen: ' + (e.message || e));
    if (origLabel) origLabel.textContent = oldText;
  }
});
```

Also: surface a dedicated **Export PDF** button in the action bar (see F4) — the KPI-card click is a hidden affordance.

---

### F2 — "Resolve" workflow does not refresh state after API success
**Type:** Bug
**Severity:** Critical
**Location:** `btnResolve` handler (~lines 1773–1786)
**Problem:** This is the "DAG Holding UG resolve didn't work" issue. v2 calls `postApi('/api/resolve-parent/...')` then runs `renderRecord()` immediately **without re-fetching `DATA`**. The backend updates `pipeline_stage`, `gesellschafter_name`, `owner_name`, possibly `is_subsidiary`. Local `DATA.records[activeIdx]` is stale, so the UI looks unchanged → user thinks "did not work".
**Fix:** After a successful POST, refresh `DATA` from `/api/data`, then render. Also handle the failure case with a tried-queries hint (port from v1 lines 1822–1835):

```js
btnResolve.addEventListener('click', async function() {
  var rec = DATA.records[activeIdx];
  if (!rec) return;
  var parentName = (document.getElementById('parent-name-input') || {}).value || '';
  if (!SERVE_MODE) {
    rec.gesellschafter_name = parentName;
    renderRecord();
    return;
  }
  btnResolve.disabled = true;
  btnResolve.textContent = 'Resolving…';
  try {
    var data = await postApi('/api/resolve-parent/' + encodeURIComponent(rec.domain), { parent_name: parentName });
    if (data && data.ok) {
      // Re-fetch full DATA so all derived fields update
      var resp = await fetch('/api/data');
      DATA = await resp.json();
      renderQueue();
      renderRecord();
    } else {
      var tried = (data && data.tried_queries) ? data.tried_queries.join(', ') : parentName;
      alert('Resolve fehlgeschlagen. Versucht: ' + tried + '\nNamen anpassen und erneut versuchen.');
      btnResolve.disabled = false;
      btnResolve.textContent = 'Resolve';
    }
  } catch (e) {
    alert('Resolve-Fehler: ' + (e.message || e));
    btnResolve.disabled = false;
    btnResolve.textContent = 'Resolve';
  }
});
```

Depends on F2a below.

---

### F2a — Active record can point outside the filtered queue
**Type:** Bug
**Severity:** High
**Location:** state init (~line 1102), `renderRecord` (line 1380), BA filter change (line 1281)
**Problem:** `activeIdx = 0` indexes `DATA.records[0]` directly, which may be a klass C/D/E record (not in the BA-Prep queue). On first load, the editor shows an irrelevant record. Same after a BA filter change: `activeIdx = 0` is reset on filter change but to absolute index 0, not to the first filtered row.
**Fix:** Replace `activeIdx = 0` resets with `activeIdx = (sortedRows()[0] || {})._idx ?? 0`. In `renderRecord`, if `r` is not in `getFilteredRows()`, fall back to first filtered row:
```js
var queueRows = getFilteredRows();
if (queueRows.length && queueRows.indexOf(r) < 0) {
  activeIdx = (sortedRows()[0] || {})._idx;
  r = (DATA.records || [])[activeIdx];
}
```
Apply at: line 1283 (`sel.onchange`), line 1314 (`renderReviewList`), and at first render after fetch (line 1097).

---

### F3 — "Alle Gesellschafter" rendered as a free-text textarea
**Type:** Bug
**Severity:** High
**Location:** Gesellschafterinformationen section (~lines 1468–1469)
**Problem:** Field shows `<textarea id="field-all-gesellschafter" rows="3" readonly>` containing the raw `r.all_gesellschafter` JSON string. It looks editable (textarea chrome), is not actually editable (`readonly`), and in v1 this was rendered as a structured list with majority badge, type label, and UBO drill-down (v1 lines 2376–2413).
**Fix:** Replace the textarea with a structured read-only block. Port logic from `dashboard_v1.html` lines 2374–2423. Concretely:

```js
function renderAllGesellschafter(r) {
  var allGs = null;
  if (r.all_gesellschafter) {
    try { allGs = JSON.parse(r.all_gesellschafter); } catch(e) {}
  }
  if (!allGs || !allGs.length) {
    if (r.gesellschafter_name) {
      return '<div class="field-readonly">' + escapeHtml(r.gesellschafter_name) +
        (r.gesellschafter_share_pct != null ? ' (' + Number(r.gesellschafter_share_pct).toFixed(1) + '%)' : '') +
        ' <span class="muted" style="font-size:11px">· Gesellschafter</span></div>';
    }
    return '<div class="field-readonly muted" style="font-style:italic">Kein Gesellschafter ermittelt</div>';
  }
  return '<div class="gs-list">' + allGs.map(function(o, i) {
    var pct = (o.pct != null) ? ' (' + Number(o.pct).toFixed(1) + '%)' : '';
    var typeLabel = (o.type === 'natural_person' || o.type === 'person')
      ? 'Person' : (o.type === 'legal_person' ? 'Unternehmen' : (o.type || ''));
    var majority = (i === 0 && allGs.length > 1) ? ' <span class="muted">★</span>' : '';
    return '<div class="gs-row">' +
      '<span>' + escapeHtml(o.name) + escapeHtml(pct) + majority + '</span>' +
      '<span class="muted" style="font-size:11px">' + escapeHtml(typeLabel) + '</span>' +
    '</div>';
  }).join('') + '</div>';
}
```

Add CSS:
```css
.gs-list { border: 1px solid var(--line); border-radius: 5px; background: var(--surface-2); overflow: hidden; }
.gs-row { display: flex; justify-content: space-between; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--line); font-size: 12px; }
.gs-row:last-child { border-bottom: none; }
```

Replace lines 1468–1469 with:
```js
'<div class="field"><div class="field-label">Alle Gesellschafter <span class="src">· Quelle: Enrichment</span></div>' +
renderAllGesellschafter(r) + '</div>' +
```
Remove the now-unused id `field-all-gesellschafter` everywhere.

---

### F4 — Gesellschafterinformationen section is collapsed by default
**Type:** UX
**Severity:** Critical
**Location:** `renderRecord` (line 1463: `class="fields-section collapsible collapsed" id="sec-gesellschafter"`)
**Problem:** Roman runs ownership review every morning — this is the core BA-Prep workflow. Section being collapsed forces a click on every record.
**Fix:**
1. Remove the `collapsed` class from the section root: change to `class="fields-section collapsible" id="sec-gesellschafter"`.
2. Reorder section render order in `record-left` so Gesellschafter is the **second** section (right after "Was fehlt") — its current position. Confirmed already second; no move required.
3. Make Stammdaten and Briefvorbereitung collapsed by default instead — change their `class` to add `collapsed`. This trades attention onto ownership.
4. Add visual distinction: Gesellschafter section uses a light teal accent border-left to mark it as the primary action. Add CSS:
   ```css
   #sec-gesellschafter { border-left: 3px solid var(--spar); padding-left: 12px; margin-left: -12px; }
   ```

---

### F5 — Manual classification to Klasse S not available unless ownership review pending
**Type:** UX
**Severity:** Critical
**Location:** `renderRecord` (~lines 1452–1461) — ownership panel only renders when `r.pipeline_stage === 'ownership_review_needed'`
**Problem:** Roman needs to be able to demote ANY record to klass S (Subsidiary, exclude). Currently the Klass `<select>` (line 1506) does not include S, and the "Ausschließen (S)" button is gated behind `ownership_review_needed`.
**Fix:**
1. Add `S` to the klass `<select>` at line 1511:
   ```html
   <option value="S"' + (r.klass==='S'?' selected':'') + '>S — Subsidiary (excluded)</option>
   ```
2. Move the Resolve / Pass / Ausschließen button row OUT of the conditional — render it permanently inside `sec-gesellschafter`, with the parent-name input still visible. The current `if (r.pipeline_stage === 'ownership_review_needed')` check around `gesellschafterPanel` (line 1453) should be removed; the panel always renders.
3. The "Ausschließen (S)" button must work regardless of pipeline_stage. Its handler (line 1799) already does the correct PATCH; no logic change needed beyond making it always render.
4. When `r.pipeline_stage !== 'ownership_review_needed'`, change panel header text from "Ownership Review benötigt" to "Ownership-Aktionen" and tone the panel down (use `var(--surface-2)` background instead of `var(--warn-soft)`).

---

### F6 — "Ansprechpartner" field appears twice
**Type:** UI
**Severity:** High
**Location:** Gesellschafterinformationen (line 1466–1467, label "Gesellschafter / Ansprechpartner") and Stammdaten (line 1529, label "Ansprechpartner")
**Problem:** The Gesellschafter section labels its input "Gesellschafter / Ansprechpartner" but it writes to `gesellschafter_name` (DB field for the legal owner). The Stammdaten section has "Ansprechpartner" writing to `owner_name` (DB field for the letter addressee). Two visually-identical labels produce two text inputs that both look like "the person to address" — one of them isn't.
**Fix:**
1. In Gesellschafterinformationen, rename the label to **"Gesellschafter (Eigentümer)"** and change the `<span class="src">` to "· DB-Feld gesellschafter_name". The input id stays `field-gesellschafter-name`.
2. In Stammdaten (Postadresse block), keep label **"Ansprechpartner (Brief)"** and add `<span class="src">· DB-Feld owner_name · wird im Serienbrief verwendet</span>`.
3. Add a small inline note under the Gesellschafter input when `r.owner_name && r.gesellschafter_name && r.owner_name !== r.gesellschafter_name`:
   ```html
   <div class="muted" style="font-size:11px;margin-top:4px">⚠ Brief adressiert <code>{owner_name}</code>, nicht den Gesellschafter</div>
   ```

---

### F7 — No reasoning shown for why someone is the Ansprechpartner
**Type:** UI
**Severity:** High
**Location:** Gesellschafterinformationen and Stammdaten sections
**Problem:** v1 had a "Herkunft Ansprechpartner" block (v1 lines 2459–2480) with: Gesellschafter name + share, GF name from impressum, percentage note for "owns through" cases, and the raw `ownership_reason` text labelled "Grundlage". v2 only shows `r.ownership_reason` as a single read-only field with no decomposition, and never near the `owner_name` input.
**Fix:** Port the v1 "Herkunft Ansprechpartner" block. Add a new `<div class="herkunft-box">` directly **below the Ansprechpartner input** in Stammdaten (after line 1529):

```js
function renderHerkunft(r) {
  if (!r.ownership_reason && !r.gesellschafter_name && !r.gf_name) return '';
  var gs = r.gesellschafter_name || '';
  var gsPct = r.gesellschafter_share_pct != null ? ' (' + Number(r.gesellschafter_share_pct).toFixed(1) + '%)' : '';
  var isVia = (r.ownership_reason || '').toLowerCase().indexOf('owns through') >= 0;
  var pctNote = (isVia && r.gesellschafter_share_pct != null)
    ? '<div class="hk-row"><span class="muted">Anteil:</span> ' + Number(r.gesellschafter_share_pct).toFixed(1) + '% <em>der Holding</em>, nicht der Zielgesellschaft</div>'
    : '';
  return '<div class="herkunft-box">' +
    '<div class="hk-title">Herkunft Ansprechpartner</div>' +
    (gs ? '<div class="hk-row"><span class="muted">Gesellschafter:</span> <strong>' + escapeHtml(gs) + '</strong>' + escapeHtml(gsPct) + '</div>' : '') +
    (r.gf_name ? '<div class="hk-row"><span class="muted">GF (Impressum):</span> ' + escapeHtml(r.gf_name) + '</div>' : '') +
    pctNote +
    (r.ownership_reason ? '<div class="hk-row"><span class="muted">Grundlage:</span> ' + escapeHtml(r.ownership_reason) + '</div>' : '') +
    '</div>';
}
```

CSS:
```css
.herkunft-box { background: #fefce8; border: 1px solid #fde68a; border-radius: 5px; padding: 8px 10px; margin-top: 6px; font-size: 11px; }
.herkunft-box .hk-title { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ink-3); font-weight: 600; margin-bottom: 4px; }
.herkunft-box .hk-row { padding: 3px 0; border-bottom: 1px solid #fef3c7; }
.herkunft-box .hk-row:last-child { border-bottom: none; }
```

Insert `+ renderHerkunft(r) +` right after the Ansprechpartner field at line 1529.

---

### F8 — "Was fehlt" groups don't match Roman's spec
**Type:** UI / UX
**Severity:** High
**Location:** `MISS_GROUPS` constant (~lines 1141–1146)
**Problem:** Current groups are `Ansprache (anrede, salutation, owner_name)`, `Adresse (street, plz_ort, region_prep)`, `Brieftext (leistung_text, compliment_draft, compliment_2, mehrwerte)`, `Kontakt (gf_email)`. Roman's spec calls for:
- **Ansprache**: `anrede`, `salutation`, `owner_name`
- **Adresse**: `street`, `plz_ort`, `region_prep`
- **Brieftext**: `leistung_text`, `compliment_draft`, `compliment_2`, `mehrwerte`
- **Email**: `gf_email`

Difference: rename "Kontakt" → "Email". Verify all 4 groups, severity rule (green if all filled, amber if any non-blocking missing, red if any blocking missing).
**Fix:**
1. Rename `id: 'kontakt', label: 'Kontakt'` → `id: 'email', label: 'Email'`.
2. Verify `blocking` arrays are correct: in Roman's spec, every missing field in Email/Brieftext should be amber (warn), every missing field in Ansprache/Adresse should be red (block) since these block the letter merge. Update `MISS_GROUPS`:
   ```js
   var MISS_GROUPS = [
     { id: 'ansprache', label: 'Ansprache', fields: ['anrede','salutation','owner_name'], blocking: ['anrede','salutation','owner_name'], scrollTo: 'sec-stammdaten' },
     { id: 'adresse',   label: 'Adresse',   fields: ['street','plz_ort','region_prep'],   blocking: ['street','plz_ort','region_prep'], scrollTo: 'sec-stammdaten' },
     { id: 'brieftext', label: 'Brieftext', fields: ['leistung_text','compliment_draft','compliment_2','mehrwerte'], blocking: [], scrollTo: 'sec-briefvorbereitung' },
     { id: 'email',     label: 'Email',     fields: ['gf_email'], blocking: [], scrollTo: 'sec-stammdaten' },
   ];
   ```
3. The dot-color logic in `groupMissingFor` already supports `ok / warn / block` — no change.

---

### F9 — KPI cards in BA-Prep view are distracting
**Type:** UX
**Severity:** High
**Location:** `renderReviewList` (~lines 1297–1302) — `<div class="kpi-bar">…</div>`
**Problem:** Roman says the 3 cards (Blockiert / In Bearbeitung / Bereit zum Export) at the top of BA-Prep don't add value and clutter the editor.
**Fix:** Remove the `kpi-bar` block from `renderReviewList`. Move the **Export PDF** action (currently triggered by the OK card) to a new dedicated button in the action bar of `record` — see F1. After removal, BA-Prep starts directly with the queue/record split.
- Note: The KPIs may still be useful in **Drop-off** or **Lead-Liste** view; do not delete the `.kpi-bar` CSS (other views may use it later). Just don't render in BA-Prep.

---

### F10 — Static "AX" brand block instead of `__LOGO_IMG__`
**Type:** UI
**Severity:** High
**Location:** `<aside class="side">` (line 984: `<div class="side-brand">AX</div>`) and top bar (line 1004: `<div class="top-logo">__LOGO_IMG__</div>`)
**Problem:** Backend injects the real Repuro logo via `__LOGO_IMG__` into `.top-logo`. The sidebar still shows hardcoded "AX" text. v1 has the same `__LOGO_IMG__` placeholder pattern (v1 line 737).
**Fix:**
1. Replace line 984 `<div class="side-brand">AX</div>` with `<div class="side-brand">__LOGO_IMG__</div>`.
2. Update `.side-brand` CSS so it sizes the injected `<img>` correctly:
   ```css
   .side-brand { width: 36px; height: 36px; background: transparent; padding: 4px; margin-bottom: 18px; display: grid; place-items: center; }
   .side-brand img { width: 100%; height: 100%; object-fit: contain; }
   ```
3. Title attribute fallback: wrap with `title="Repuro"` for screen readers.
4. The top bar `__LOGO_IMG__` injection (line 1004) already works — leave alone.

---

### F11 — Repuro CI (teal) only used in the sidebar
**Type:** Design
**Severity:** Medium
**Location:** Throughout CSS (`--spar: #0891B2`)
**Problem:** Teal is currently used for: ownership panel inputs focus state, KPI hover, qitem.active border, miss-action links, btn.primary, focus rings. Roman wants it propagated as the primary highlight everywhere — section dividers, active states, current-row highlights, the brand bar.
**Fix:** Apply teal as the recurring accent:
1. **Active subnav**: change `.subnav-item.active { border-bottom-color: var(--ink); }` → `var(--spar)`.
2. **Active sidebar mode**: change `.side-mode.active { background: var(--ink); }` → `background: var(--spar);` (keeping white text).
3. **Section title underline**: add a 2px teal accent under each `.section-title`:
   ```css
   .fields-section .section-title { border-bottom: 1px solid var(--line); padding-bottom: 6px; }
   .fields-section .section-title::after { content: ''; display: block; width: 24px; height: 2px; background: var(--spar); margin-top: -1px; }
   ```
4. **Active record nav buttons**: focus state → `var(--spar)` border instead of default.
5. **Funnel bars**: `.fnl-bar { background: var(--ink); }` → `background: var(--spar);`.
6. **Active leads-table row**: already `var(--spar-soft)` — keep.
7. **Active queue item left rail**: already `var(--spar)` — keep.
8. **Class summary bars** (`.cls-bar > span`): change from `var(--ink)` to `var(--spar)`.
9. **Funnel `.fnl-stage`** active state: not styled, no change.
10. **Approve button**: keep `btn.primary` teal — already correct.

---

### F12 — Lead-Liste table is missing required columns
**Type:** UI
**Severity:** High
**Location:** `renderLeadsTable` `cols` array (~lines 1946–1956)
**Problem:** Currently shows: klass, full_name, domain, region, pipeline_stage, anrede, gf_email, briefaktion, _missing. Missing: `owner_name`, `filter_pass`, `approved_for_sendout`, `briefaktion` already there. Roman explicitly asked for: `full_name, domain, region, klass, anrede, owner_name, gf_email, pipeline_stage, briefaktion, filter_pass, approved_for_sendout, Fehlt`.
**Fix:** Replace `cols` with the full set, in Roman's listed order, and add inline editors where appropriate:

```js
var cols = [
  { id: 'klass',                 label: 'Klass',     sort: 'klass',                 edit: 'select-klass' },
  { id: 'full_name',             label: 'Name',      sort: 'full_name',             edit: 'text' },
  { id: 'domain',                label: 'Domain',    sort: 'domain',                edit: 'readonly' },
  { id: 'region',                label: 'Region',    sort: 'region',                edit: 'text' },
  { id: 'anrede',                label: 'Anrede',    sort: 'anrede',                edit: 'select-anrede' },
  { id: 'owner_name',            label: 'Ansprechp.',sort: 'owner_name',            edit: 'text' },
  { id: 'gf_email',              label: 'GF E-Mail', sort: 'gf_email',              edit: 'email' },
  { id: 'pipeline_stage',        label: 'Stage',     sort: 'pipeline_stage',        edit: 'readonly' },
  { id: 'briefaktion',           label: 'BA',        sort: 'briefaktion',           edit: 'readonly' },
  { id: 'filter_pass',           label: 'Filter',    sort: 'filter_pass',           edit: 'pass-badge' },
  { id: 'approved_for_sendout',  label: 'Approved',  sort: 'approved_for_sendout',  edit: 'checkbox' },
  { id: '_missing',              label: 'Fehlt',     sort: '_missing',              edit: 'readonly' },
];
```

Render rules:
- `select-klass`: `<select>` with options A/B/C/D/E/S, change handler calls `inlineSave(el,'klass')`.
- `select-anrede`: existing behaviour, keep.
- `text`: `<input type="text" class="lt-edit lt-edit-{field}">`, blur → save.
- `email`: `<input type="email">`, blur → save.
- `readonly`: plain text cell, escapeHtml.
- `pass-badge`: render `<span class="lt-pass-{0|1}">✓</span>` or `✗`, click toggles 0/1 and calls `inlineSave`.
- `checkbox`: `<input type="checkbox" class="lt-edit-approved">`, change handler patches `approved_for_sendout` 0/1.

Wire up new handlers analogous to existing `lt-edit-region`/`lt-edit-anrede` (lines 2038–2051). Add CSS for `.lt-pass-1 { color: var(--ok); } .lt-pass-0 { color: var(--block); }`.

---

### F13 — Region-prep auto-fill fails when REGION_MAPPING is empty
**Type:** Bug
**Severity:** High
**Location:** `wb()` function inside `renderRecord` (~lines 1606–1621)
**Problem:** Roman typed `Test123` into the Region field at zekamed.de. The Brief still showed `[region_prep fehlt]`. Two bugs:
1. The auto-fill only fires on `blur` (the input's writeback event). If the user tabs away into the Brieftext or the next-record nav before blurring, the save never happens.
2. The fallback (`'in ' + val`) only fires when `!rec.region_prep`. If `rec.region_prep` was previously `''` (empty string) it works, but if it's `null` it works too — so this isn't the bug. The bug is in REGION_MAPPING access: the lookup uses `val.toLowerCase()` (the city/region the user typed) which is never a key in `REGION_MAPPING` because `REGION_MAPPING` is keyed by city, but the user types a region label like "Test123". When `mapped` is undefined AND `rec.region_prep` is already non-empty stale value, no overwrite happens.
3. Also in static export mode `REGION_MAPPING` is `{}` — same outcome.

**Fix:**
1. Always overwrite `region_prep` when the user changes `region` (don't gate on `!rec.region_prep`):
   ```js
   if (field === 'region' && val) {
     var cityLower = val.toLowerCase().trim();
     var mapped = REGION_MAPPING && REGION_MAPPING[cityLower];
     var newRp = (mapped && mapped.region_prep) ? mapped.region_prep : ('in ' + val);
     rec.region_prep = newRp;
     var rpInput = document.getElementById('field-region-prep');
     if (rpInput) rpInput.value = newRp;
     if (SERVE_MODE) patchCompany(rec.domain, { region_prep: newRp }).catch(function(){});
   }
   ```
2. Fire the writeback on `input` (live) for the `region` field, not only `blur`. Modify `wb` to accept an event override or special-case region to add an `input` listener as well.
3. After update, **re-render the letter preview** (already partially done — verify it runs).
4. Add a tiny "↺ Auto-fill" button next to the Region Brieftext field so the user can manually re-run the mapping if region was already set.

---

### F14 — Field writeback only fires on blur — letter preview can show stale state
**Type:** Bug
**Severity:** Medium
**Location:** `wb()` function (~lines 1595–1629)
**Problem:** The `blur` listener doesn't fire if the user clicks Save or Approve (the click captures focus before blur events flush in some browsers — race). Symptoms: clicked Save, field value not in DB.
**Fix:** Inside `Save` button handler (line 1734), call `document.activeElement.blur()` first to force any pending writeback:
```js
saveBtn.addEventListener('click', function() {
  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }
  // existing save logic
});
```
Apply the same blur-first guard to `approveBtn`, `skipBtn`, `rec-prev`, `rec-next`.

---

### F15 — Letter preview doesn't update after Gesellschafter section saves
**Type:** Bug
**Severity:** Medium
**Location:** `wb('field-gesellschafter-name', 'gesellschafter_name')` (line 1646), `wbCheckbox` (lines 1649–1660)
**Problem:** After the user edits `gesellschafter_name` or toggles `is_subsidiary`, the letter preview is **not** re-rendered. Although the letter template doesn't currently use `gesellschafter_name`, the `owner_name` derivation downstream and the Was-fehlt bar do. When the user toggles `is_subsidiary = 1`, the record may now be classified as ownership_excluded but the UI doesn't reflect it.
**Fix:** Inside `wb()` and `wbCheckbox()`, always trigger a `renderRecord()` after save (since the Was-fehlt bar / Herkunft block / mismatch warning all depend on the updated state). Cheaper: re-render only the letter preview AND the "Was fehlt" bar:
```js
// After rec[field] = val:
var groups = groupMissingFor(rec);
// ... update miss-group dots in DOM, OR just call renderRecord() for simplicity
renderRecord();
```
Calling `renderRecord()` is acceptable here — one full re-render per field edit on blur is fine.

---

### F16 — Activity Log fails silently when SERVE_MODE=false
**Type:** UX
**Severity:** Medium
**Location:** `renderReviewActivity` (~lines 2095–2106)
**Problem:** When the dashboard is opened in static-export mode (no backend), `/api/activity` 404s and the lead text becomes "Fehler beim Laden (serve-Modus benötigt)". Roman wants a clear message, not an error.
**Fix:** Guard the fetch on `SERVE_MODE`:
```js
function renderReviewActivity() {
  var root = document.getElementById('view-review');
  if (!SERVE_MODE) {
    root.innerHTML = '<div class="page"><div class="page-head"><div><h2>Activity Log</h2>' +
      '<p class="lead">Activity Log ist nur im Live-Modus verfügbar (serve-Modus).</p></div></div></div>';
    return;
  }
  root.innerHTML = '<div class="page"><div class="page-head"><div><h2>Activity Log</h2><p class="lead">Lädt…</p></div></div></div>';
  fetch('/api/activity?limit=100')
    .then(function(r){ if (!r.ok) throw new Error('http_'+r.status); return r.json(); })
    .then(function(data){ renderActivityData(root, data); })
    .catch(function(){
      var lead = root.querySelector('.lead');
      if (lead) lead.textContent = 'Fehler beim Laden des Activity Logs';
    });
}
```

---

### F17 — Website preview iframe collapses to zero height
**Type:** Bug
**Severity:** Medium
**Location:** `siteHtml(r)` (~lines 1875–1886) and CSS `.site` / `.site iframe` (~lines 700–712)
**Problem:** v1 had the iframe-fallback pattern working. v2's `<div class="site">` uses `height: 100%; min-height: 480px` with `display: flex; flex-direction: column` — but its parent `.preview-body` is `overflow-y: auto` (not a flex column). When the parent isn't constrained, `height: 100%` resolves against an auto-height container = collapses. The iframe then takes 0 px.
**Fix:**
1. Make `.preview-body` a flex column itself so children can `flex: 1`:
   ```css
   .preview-body { flex: 1; overflow-y: auto; min-height: 0; display: flex; flex-direction: column; }
   ```
2. Ensure `.site` fills its parent:
   ```css
   .site { flex: 1; min-height: 480px; background: var(--surface-2); display: flex; flex-direction: column; }
   .site iframe { flex: 1; border: none; width: 100%; height: 100%; min-height: 400px; background: white; }
   ```
3. Remove the unused `.site-frame` CSS block (lines 713–721) — it's not referenced.
4. Inline `style="flex:1;border:none;width:100%;height:100%;"` on the iframe is fine; keep.
5. The `onerror` handler on `<iframe>` does **not** fire for X-Frame-Options blocks. Replace with the v1 pattern (port from v1 lines 2300–2314): show a "cannot embed" notice with an "open in new tab" link as a default visible affordance, since most German company sites set `X-Frame-Options: SAMEORIGIN`. Render both side by side OR add a 3-second timeout that swaps to fallback if the iframe stays blank:
   ```js
   // After inserting the iframe, set a timer:
   setTimeout(function() {
     try {
       var ifr = pb.querySelector('iframe');
       if (ifr && (!ifr.contentDocument || !ifr.contentDocument.body || !ifr.contentDocument.body.innerHTML)) {
         ifr.style.display = 'none';
         ifr.nextElementSibling.style.display = 'flex';
       }
     } catch(e) {
       // cross-origin — assume blocked and show fallback
       var ifr = pb.querySelector('iframe');
       if (ifr) { ifr.style.display = 'none'; if (ifr.nextElementSibling) ifr.nextElementSibling.style.display = 'flex'; }
     }
   }, 2500);
   ```
   (Cross-origin throws — caught and shows fallback. Acceptable trade-off.)

---

### F18 — Collapsible sections lose their collapsed state on re-render
**Type:** Bug
**Severity:** Medium
**Location:** `renderRecord` — every call rebuilds `record-left` from scratch (line 1497)
**Problem:** Every Save / field blur triggers `renderRecord()`. The DOM is rebuilt → all collapsed sections snap back to their default state (open or closed per F4). A user who opened Briefvorbereitung mid-edit will see it close every time they edit a field.
**Fix:** Track collapsed state in JS, not DOM:
1. Add module state: `var collapsedSections = { 'sec-was-fehlt': false, 'sec-gesellschafter': false, 'sec-stammdaten': true, 'sec-briefvorbereitung': true };`
2. In `renderRecord`, when building each section, read from `collapsedSections[id]` and add `collapsed` class accordingly.
3. In the toggle click handler (line 1665), update `collapsedSections[id]`:
   ```js
   document.querySelectorAll('.fields-section.collapsible .collapse-toggle').forEach(function(t) {
     t.addEventListener('click', function() {
       var parent = t.closest('.fields-section');
       if (!parent || !parent.id) return;
       parent.classList.toggle('collapsed');
       collapsedSections[parent.id] = parent.classList.contains('collapsed');
     });
   });
   ```

---

### F19 — `document.onkeydown` rebound on every render destroys other listeners
**Type:** Bug
**Severity:** Low
**Location:** End of `renderRecord` (~lines 1813–1817)
**Problem:** `document.onkeydown = function(e) {…}` overwrites the property; only one handler can be active. If a future feature adds another keyboard hook, it'll be silently replaced.
**Fix:** Switch to `addEventListener` once at the top of the script, not inside `renderRecord`. Move the handler to module scope:
```js
// Module scope, runs once at page load
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  var skipBtn = document.getElementById('btn-skip');
  var saveBtn = document.getElementById('btn-save');
  if (e.key === 'ArrowRight' && skipBtn) skipBtn.click();
  if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); if (saveBtn) saveBtn.click(); }
});
```
Remove lines 1813–1817 from `renderRecord`.

---

### F20 — Typography inconsistency
**Type:** Design
**Severity:** Medium
**Location:** Across all CSS rules
**Problem:** Roman wants max 3 text sizes (13px body, 11px meta, 22px+ numbers) and 3 colors (--ink, --ink-2, --ink-3). Audit shows many one-off sizes: 9px (sort-arrow), 10px (kbd, ps-lbl, kpi-sub uses 11px, side-mode-label 11px), 14px (record-name uses 18px, dfstage-title), 16px (fnl-n), 12px (top-title, queue-title, lots), 11px, 13px. Color: `--ink-4` is used heavily in addition to the 3 official.
**Fix:** Define a typography scale in `:root` and apply:
```css
:root {
  --t-num: 22px;     /* primary numerics: kpi, ps-num, bottle-card-num — currently 24/28/32, normalise to 22 (or keep 28 for hero KPIs) */
  --t-body: 13px;    /* default body */
  --t-meta: 11px;    /* labels, hints, meta */
}
```
Concrete consolidations:
- All elements currently using 9px or 10px → 11px (`--t-meta`). This includes `sort-arrow`, `kbd`, `dfc-lbl`, `ps-lbl`, `cls-letter` (currently 13px), `fnl-stage-sub`, `act-kind`.
- Numbers larger than 22 keep their hero weight (kpi-num 28, bottle-card-num 32, record-name 18) — acceptable hero-scale exceptions, document them in a CSS comment.
- All elements currently using 12px → 13px (`--t-body`) or 11px (`--t-meta`) based on hierarchy. E.g. `top-title 14 → 13`, `subnav-label 12 → 13`.
- Replace `var(--ink-4)` usages with `var(--ink-3)`. `--ink-4` may still be used for very-disabled placeholder text but flag every instance for review (~12 occurrences).
- Add a CSS comment block at top documenting the rule:
  ```css
  /* TYPOGRAPHY: only 3 sizes (13/11/22+) and 3 colors (--ink/--ink-2/--ink-3). Hero numbers may exceed 22px and are documented inline. */
  ```

---

### F21 — `top-title` shows "Review" — Roman wants subnav rename
**Type:** UX
**Severity:** Medium
**Location:** `TITLES` map (line 1200), `SUBNAV` (line 1204)
**Problem:** Roman explicitly asked for tabs **BA-Prep / Lead-Liste / Drop-off / Activity Log**. Already correct in v2 (line 1206). Top title still says "Review" generically. Roman wants each view to "have one purpose" — top title should reflect the current sub-tab.
**Fix:** Update `top-sub` per-subnav. Add a per-subnav title map and call it from `renderSubnav`:
```js
var SUBNAV_TITLES = {
  baprep:   ['BA-Prep',      'Briefe vorbereiten · ein Record nach dem anderen'],
  leads:    ['Lead-Liste',   'Alle Records · Tabelle · direkt editierbar'],
  dropoff:  ['Drop-off',     'Wo Records aus der Pipeline herausfallen'],
  activity: ['Activity Log', 'Wer hat was geändert'],
  funnel:   ['Funnel',       'Pipeline-Stadien'],
  cohorts:  ['Cohorts',      'Sent → Reply → Deal pro Briefaktion'],
  classes:  ['Klassen',      'A/B/C/D/E/S Verteilung'],
  bottlenecks:['Bottlenecks','Aktuelle Blocker'],
};
function applyTopTitle() {
  var cur = sub[mode];
  var t = SUBNAV_TITLES[cur];
  if (t) { titleEl.textContent = t[0]; subEl.textContent = t[1]; }
}
```
Call `applyTopTitle()` at the end of `renderSubnav()` and on subnav-item click.

---

### F22 — BA filter doesn't apply to Lead-Liste consistently
**Type:** Bug
**Severity:** Medium
**Location:** `renderLeadsTable` (~lines 1912–2052) and `getFilteredRows` (~line 1172)
**Problem:** `getFilteredRows()` filters by `selectedBA` and by `klass A/B`. `renderLeadsTable` deliberately shows **all** records without filter. The BA select in the top bar therefore appears to filter BA-Prep but does nothing in Lead-Liste — inconsistent.
**Fix:** Add an explicit BA filter chip inside the leads-toolbar that mirrors `selectedBA` and lets the user choose: "Folge BA-Filter (oben)" vs. "Alle anzeigen". Default = follow top-bar filter.
```js
// Inside renderLeadsTable, before iterating rows:
var followGlobalBA = (typeof leadsFollowBA === 'undefined' ? true : leadsFollowBA);
if (followGlobalBA && selectedBA) {
  rows = rows.filter(function(r){ return r.briefaktion === selectedBA; });
}
```
Add toggle UI in the toolbar:
```html
<label style="font-size:12px;color:var(--ink-3);display:flex;align-items:center;gap:4px">
  <input type="checkbox" id="leads-follow-ba" checked> BA-Filter folgen
</label>
```
Wire change handler to set `leadsFollowBA` and re-render.

---

### F23 — Subsidiary checkbox in Gesellschafter section conflicts with Klasse S
**Type:** UX
**Severity:** Low
**Location:** `field-is-subsidiary` checkbox (line 1471–1472) + Klass select (line 1506)
**Problem:** Two ways to mark a subsidiary: the `is_subsidiary` checkbox sets the flag, and Klasse S (after F5) sets klass='S'. They can drift (`is_subsidiary=1, klass='B'`). Backend treats them differently.
**Fix:** Make the `is_subsidiary` checkbox auto-cascade to klass='S' when checked (and warn when unchecking would leave klass='S'):
```js
wbCheckbox('field-is-subsidiary', 'is_subsidiary');
// Override: when checked, also set klass='S' as a UX shortcut
var subsBox = document.getElementById('field-is-subsidiary');
if (subsBox) {
  subsBox.addEventListener('change', function() {
    var rec = DATA.records[activeIdx];
    if (!rec) return;
    if (subsBox.checked && rec.klass !== 'S') {
      rec.klass = 'S';
      rec.reclassify_reason = 'ownership_excluded';
      if (SERVE_MODE) patchCompany(rec.domain, { klass: 'S', reclassify_reason: 'ownership_excluded' }).catch(function(){});
      var sel = document.getElementById('field-klass'); if (sel) sel.value = 'S';
    }
  });
}
```
Note: this is additive to F5's klass='S' option in the dropdown — the two paths converge.

---

### F24 — Approve button enables export even with blocking fields
**Type:** UX
**Severity:** Low
**Location:** `renderRecord` action bar (~line 1560)
**Problem:** Label reads "5 Felder offen · Trotzdem freigeben" → click sets `approved_for_sendout=1`. No friction. A typo or missing street will silently approve.
**Fix:** When `blockingCount > 0` AND user clicks Approve, show a confirm:
```js
approveBtn.addEventListener('click', function() {
  var rec = DATA.records[activeIdx];
  if (!rec) return;
  var newVal = rec.approved_for_sendout ? 0 : 1;
  if (newVal === 1 && blockingCount > 0) {
    if (!confirm(blockingCount + ' Pflichtfelder fehlen noch. Trotzdem freigeben?')) return;
  }
  rec.approved_for_sendout = newVal;
  if (SERVE_MODE) patchCompany(rec.domain, { approved_for_sendout: newVal }).catch(function(){});
  renderQueue();
  renderRecord();
});
```

---

### F25 — Lead-Liste row click hijacks editable cell clicks
**Type:** Bug
**Severity:** Low
**Location:** Row click handler (~lines 2008–2020)
**Problem:** The TR-level click handler navigates to BA-Prep when the click target is not a `.lt-edit`. Works for inputs/selects but fails when clicking inside the `lt-name` cell — that cell is not a `.lt-edit` so click navigates away. Acceptable but counter-intuitive: a small click on a domain like `klinik-medizin.de` sends the user to a detail view they may not want.
**Fix:** Add an explicit "Open" affordance per row instead of whole-row click. Add a leftmost cell with an arrow icon; bind click only to that:
```js
// Insert at start of bodyHtml each row:
'<td style="width:24px;text-align:center"><button class="btn-row-open">→</button></td>'
```
Or: keep row click but only when target is `<td class="lt-name">` or domain cell. Prefer the explicit button approach for clarity.

---

### F26 — `siteHtml` builds onclick from raw domain (parse-time risk)
**Type:** Bug
**Severity:** Low
**Location:** `siteHtml(r)` (line 1879)
**Problem:** `onclick="window.open('https://' + domain + '','_blank')"` — `domain` is `escapeHtml`'d so HTML-safe, but if a domain ever contains `'` or `\`, JS string parsing fails. Domains can't legally contain these, but defensive programming.
**Fix:** Replace inline `onclick` with a JS-attached listener:
```js
function siteHtml(r) {
  var domain = r.domain || '';
  var safe = escapeHtml(domain);
  return '<div class="site">' +
    '<div class="site-bar"><span class="muted">https://</span><span style="color:var(--ink);font-weight:500">' + safe + '</span>' +
    '<div style="flex:1"></div><button class="btn sm ghost" id="btn-open-site">Neu öffnen ↗</button></div>' +
    '<iframe src="https://' + safe + '" id="site-iframe"></iframe>' +
    '<div class="site-fallback" style="display:none">' +
    '<div>Website kann nicht eingebettet werden</div>' +
    '<a href="https://' + safe + '" target="_blank" rel="noopener" class="site-open-link">In neuem Tab öffnen ↗</a>' +
    '</div></div>';
}
// After inserting:
var btn = document.getElementById('btn-open-site');
if (btn) btn.addEventListener('click', function(){ window.open('https://' + (r.domain || ''), '_blank', 'noopener'); });
```

---

### F27 — `qitem` grid template assumes 2 columns, content has 4 children
**Type:** Bug
**Severity:** Low
**Location:** CSS `.qitem` (line 318) and JS render (line 1363–1368)
**Problem:** CSS declares `grid-template-columns: 1fr auto;` but the rendered children are 4 elements: name, stat, domain, cls. They auto-flow into rows 1 + 2. Visually fine because CSS grid handles overflow, but the row-2 `qitem-cls` is right-aligned by `auto` column — sometimes overlaps domain on narrow widths.
**Fix:** Set explicit grid-template-areas:
```css
.qitem {
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  grid-template-areas:
    "name stat"
    "domain cls";
}
.qitem-name   { grid-area: name; }
.qitem-stat   { grid-area: stat; }
.qitem-domain { grid-area: domain; }
.qitem-cls    { grid-area: cls; text-align: right; }
```

---

### F28 — `record-meta` not declared in CSS — falls back to default block
**Type:** Bug
**Severity:** Low
**Location:** record-head HTML (line 1486), CSS rules — only `.record-meta { display: flex; flex-direction: column; }` at line 371 (verified) — exists. No bug. **Skip.**

(Removing this entry — false positive on initial pass, kept here for audit transparency.)

---

### F29 — Approve button label includes raw HTML SVG inside `+` concat with truthy interpolation
**Type:** Bug
**Severity:** Low
**Location:** action bar (line 1558–1560)
**Problem:** Ternary returns either `'Freigegeben ✓</button>'` or a longer string with embedded SVG. Concatenation is correct, but the inner SVG `<path>` uses unescaped `>` characters. In v2 these are template strings so OK. Confirmed correct. **Skip.**

(Verified — no bug; left for audit transparency.)

---

### F30 — XSS audit: confirm all dynamic text is escaped
**Type:** Security
**Severity:** Low
**Location:** All `.innerHTML` assignments
**Problem:** Surveyed all `escapeHtml` usage. Concerning sites:
- `LETTER_TEMPLATE.replace(...)` — values escaped in callback. Safe.
- `siteHtml` — domain escaped. After F26 fix, also safe.
- `kindLabel(kind)` returns either a known label or the raw `k` — `k` is `a.kind` from the activity API, which is server-controlled but not raw user input. Low risk.
- `escapeHtml(a.field || a.field_name || '')` etc. in activity row — escaped. Safe.
- `r.full_name` via `escapeHtml` — safe.
**Fix:** No code change required. Add a code comment at the top of the script block: `// All user-visible string output MUST go through escapeHtml(). Treat any new innerHTML without it as a bug.` Document this in `LEARNINGS.md`.

---

### F31 — `populateBaSelect` rebuilds entire `<select>` losing focus when opened
**Type:** Bug
**Severity:** Low
**Location:** `populateBaSelect` (~lines 1269–1286)
**Problem:** Called from the live-refresh `.then()` chain (line 1097). Each refresh wipes and rebuilds the dropdown — if the user had it open, it snaps shut.
**Fix:** Only rebuild if the option set changed. Cache the join of BA names; only rebuild when changed:
```js
var _lastBas = '';
function populateBaSelect() {
  var sel = document.getElementById('ba-select');
  if (!sel) return;
  var bas = (DATA.briefaktion_counts || []).map(function(b){ return b.briefaktion; }).filter(Boolean).sort();
  var sig = bas.join('|');
  if (sig === _lastBas) return;
  _lastBas = sig;
  // existing rebuild logic
  ...
}
```

---

### F32 — Live refresh fetches `/api/data` but doesn't repopulate REGION_MAPPING
**Type:** Bug
**Severity:** Low
**Location:** Live refresh block (~lines 1094–1099)
**Problem:** `REGION_MAPPING` is injected at template render time. If the backend updates region mappings while the dashboard is open, the auto-fill will use stale data.
**Fix:** Either fetch `/api/region-mapping` alongside `/api/data`, or accept staleness for now and document. Lower priority — recommend deferring unless backend already exposes the endpoint.

---

### F33 — Top "AX" sidebar brand has no semantics (after F10)
**Type:** Accessibility
**Severity:** Low
**Location:** F10 fix
**Problem:** After F10, the brand cell holds an `<img>`. Need `alt="Repuro"` for screen readers.
**Fix:** Backend-injected `__LOGO_IMG__` should already include `alt`. If not, wrap server-side. As a JS-side guard, after init add:
```js
var brandImg = document.querySelector('.side-brand img');
if (brandImg && !brandImg.alt) brandImg.alt = 'Repuro';
var topImg = document.querySelector('.top-logo img');
if (topImg && !topImg.alt) topImg.alt = 'Repuro';
```

---

## Implementation order

Critical first (do not commit until F1–F5, F7, F8 are all in):

1. F1 — Export PDF (download blob)
2. F2 — Resolve refresh + F2a active-idx fix
3. F3 — Alle Gesellschafter rendered as list
4. F4 — Gesellschafter section open by default
5. F5 — Klass S in dropdown + permanent ownership panel
6. F6 — Ansprechpartner labels disambiguated
7. F7 — Herkunft Ansprechpartner block ported from v1
8. F8 — Was-fehlt groups (rename Kontakt → Email)
9. F9 — Remove KPI bar from BA-Prep
10. F10 — `__LOGO_IMG__` in sidebar
11. F11 — Repuro CI propagation
12. F12 — Lead-Liste full column set
13. F13 — Region-prep auto-fill robustness
14. F14, F15, F18 — Save/blur/preview/collapsed-state robustness
15. F16, F17 — Activity log + iframe height
16. F19, F20, F21 — keyboard handler, typography, top title
17. F22, F23, F24, F25 — BA filter consistency, subsidiary cascade, approve confirm, row-click cell
18. F26, F27, F31, F33 — minor hardening
19. F30 — security audit comment + LEARNINGS.md note

## Out of scope

- M28-Round-1 issues (Export button hidden at top → addressed by F1+F9; ownership section hidden → F4; website static mock → F17)
- Backend changes to `/api/resolve-parent`, `/api/export-pdf`, `/api/data` — assumed correct; verify if F2 reveals server bugs.
- Migration of any v1-only feature not explicitly listed (e.g. Drop-Off graph variants, blocker tabs).

## Notes for implementer

- All edits in one file: `src/pipeline/templates/dashboard_v2.html`. No backend/Python changes required.
- After implementing, run the dashboard against a live SQLite (`SERVE_MODE=true`) AND in static export mode to verify both code paths.
- Specifically test: DAG Holding UG resolve (F2), zekamed.de region-prep auto-fill (F13), Lead-Liste with BA filter active (F22).
- Consider running `/codex-review` on the final diff — generator-reviewer blind spot warning per CLAUDE.md Critical 10 rule 6.
