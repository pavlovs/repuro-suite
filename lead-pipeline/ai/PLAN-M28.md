# M28: Dashboard v2 Shell + Review Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Develop the v2 design as a fork (`dashboard_v2.html`) alongside the untouched v1 (`dashboard.html`). A `--v2` CLI flag switches which template is served. v1 stays the production default until v2 is explicitly promoted. All existing write-back API endpoints preserved.

**Architecture:** Single-file HTML template (same pattern as current — `__PLACEHOLDER__` injection, no build step). CSS custom properties for design system. Vanilla JS with mode/sub-tab routing. Backend `dashboard.py` changes: (1) accept a `v2` parameter in `_build_html()` to pick the template file, (2) add `_compute_dropoff()` for the Drop-off view; all existing routes and `_load_data()` otherwise unchanged.

**Tech Stack:** HTML/CSS/JS (vanilla, no framework), Python stdlib `http.server`, SQLite

**Design Reference:** Prototype at `docs/superpowers/specs/design-prototype/` (index.html, app.js, styles-v3.css, data.js) — match visual output, not internal structure.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/pipeline/templates/dashboard_v1.html` | Create (copy of current) | v1 backup — never modified after Task 0 |
| `src/pipeline/templates/dashboard_v2.html` | Create (new file) | v2 HTML shell + all CSS + all JS |
| `src/pipeline/dashboard.py` | Modify | `--v2` routing in `_build_html()`, add `_compute_dropoff()`, inject dropoff data |
| `tests/test_dashboard.py` | Modify | Add tests for new `_build_html` placeholders, dropoff data |

---

## Important Notes for Implementers

1. **Fork, not replace.** v2 lives in `dashboard_v2.html`. The original `dashboard.html` becomes `dashboard_v1.html` (static copy, never edited after Task 0). Default serving remains v1. Use `--v2` to test v2. Promotion to default is a separate explicit step at the end of this milestone.

2. **This is a single-file HTML template.** All CSS and JS are embedded in `dashboard_v2.html`. The prototype has separate files (app.js, styles-v3.css) for Claude Design's tooling — merge them into the single template file.

3. **Data injection pattern.** The backend replaces `__DATA_JSON__`, `__SERVE_MODE_JS__`, `__LIVE_BADGE__`, `__DATE_STR__`, `__LOGO_IMG__`, `__HUBSPOT_PORTAL_ID__`, `__REGION_MAPPING_JSON__`, `__LETTER_TEMPLATE__` in the HTML string. Add `__DROPOFF_JSON__` and `__ACTIVITY_ENDPOINT__` as new placeholders.

3. **Preserve all existing API endpoints.** Do not modify any route in `dashboard.py` except `_build_html()`. The frontend JS must call the same endpoints:
   - `GET /api/data` — all records
   - `PATCH /api/company/{domain}` — update record
   - `PATCH /api/batch` — bulk update
   - `POST /api/compliment/{domain}` — regen compliment
   - `POST /api/ingest-domain` — add domain
   - `POST /api/export-pdf` — generate PDF
   - `POST /api/re-enrich/{domain}` — re-run enrichment
   - `POST /api/resolve-parent/{domain}` — UBO resolution
   - `GET /api/activity` — activity log (M27)

4. **"Was fehlt" checklist.** Derive from the `_REQUIRED_FIELDS` list in `check_letter.py` (12 fields). The frontend must import this list from the data JSON (add a `required_fields` key to `_load_data()` output), not hardcode field names.

5. **Actor identity.** localStorage stores current user (`roman` or `flo`). Sidebar footer shows initials (RD/FF). All PATCH/POST requests append `?actor=<value>` to the URL.

---

### Pre-flight: Schema / Prototype Reconciliation

**GATE — complete before starting Task 0. Do not write dashboard_v2.html until this checklist is verified.**

The Claude Design prototype (`docs/superpowers/specs/design-prototype/data.js`) uses mock field names. The fields below document the mapping to real DB schema. Type classification: **D** = direct DB column, **C** = composite (maps to 2+ DB fields), **DR** = derived/computed client-side, **M** = mock-only (no DB equivalent — rename or drop).

| Prototype field | Type | Real DB field(s) | Notes |
|---|---|---|---|
| `name` | D | `full_name` | Rename all `r.name` → `r.full_name` in JS |
| `domain` | D | `domain` | Direct match |
| `region` | D | `region` | Direct match |
| `klass` | D | `klass` | Direct match |
| `ready` | DR | computed | Client-side: `missing_count / required_fields.length`. Do NOT map to DB. |
| `address` | C | `street` + `plz_ort` | Split into two fields in editor; combined label in "Was fehlt" |
| `compliment` | C | `compliment_draft` + `compliment_2` | Always two separate fields. Never treat as single. |
| `gf_name` | D | `gf_name` | Direct match |
| `anrede` | D | `anrede` | Direct match |
| `email` | D | `gf_email` | Rename: `r.email` → `r.gf_email` |
| `approve` | D | `approved_for_sendout` | Rename |
| `D.kpis` | DR | computed | Compute from records + required_fields at render time |
| `D.funnel` | DR | `DATA.funnel` (from `_load_data`) | Direct from backend injection |
| `D.cohorts` | DR | `DATA.briefaktion_counts` | Column mapping needed (sent/reply/meeting/deal) |
| `D.classes` | DR | `DATA.klass_counts` | |
| `D.bottlenecks` | DR | computed | Derive from records: missing fields, unclassified, no-email |
| `D.dropoff` | DR | `DATA.dropoff` (M28 Task 1) | Backend computes, injected via `_load_data` |
| `D.activity` | DR | `GET /api/activity` | Fetched live in serve mode |
| `D.missingFor(r)` | DR | computed from `DATA.required_fields` | Replace mock function with real check against `_REQUIRED_FIELDS` (12 fields) |

**Required fields (12) from `check_letter.py:_REQUIRED_FIELDS`:**
`full_name`, `anrede`, `salutation`, `owner_name`, `street`, `plz_ort`, `region_prep`, `leistung_text`, `compliment_draft`, `compliment_2`, `mehrwerte`, `gf_email`

**Writable fields (27) from `dashboard.py:_WRITEBACK_FIELDS`:**
`klass`, `outreach_status`, `outreach_sent_at`, `outreach_comment`, `followup1_at`, `followup2_at`, `followup_comment`, `gf_email`, `compliment_draft`, `compliment_2`, `approved_for_sendout`, `region`, `region_prep`, `anrede`, `salutation`, `owner_name`, `leistung_text`, `leistung_absatz_2`, `mehrwerte`, `gesellschafter_name`, `all_gesellschafter`, `impressum_name`, `gf_name`, `pipeline_stage`, `is_subsidiary`, `is_pe_backed`, `reclassify_reason`

**M28 acceptance check (verify before promoting to default):**
- [ ] Every field in `_REQUIRED_FIELDS` (12) is represented as an editable input in the record editor
- [ ] `compliment_draft` and `compliment_2` are two separate textareas — never merged
- [ ] Every editable field in the editor is in `_WRITEBACK_FIELDS` or marked read-only with justification
- [ ] No mock-only prototype field names (`name`, `ready`, `address`, `compliment`, `email`, `approve`) appear in the shipped JS

---

### Task 0: Backup v1 and wire --v2 flag

**Files:**
- Create: `src/pipeline/templates/dashboard_v1.html` (copy of current `dashboard.html`)
- Create: `src/pipeline/templates/dashboard_v2.html` (empty shell — filled in Task 2)
- Modify: `src/pipeline/dashboard.py` (template selection logic)

- [ ] **Step 1: Copy current dashboard to v1 backup**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
cp src/pipeline/templates/dashboard.html src/pipeline/templates/dashboard_v1.html
```

`dashboard_v1.html` is now a permanent static backup. Never edit it after this point.

- [ ] **Step 2: Create empty dashboard_v2.html placeholder**

Create `src/pipeline/templates/dashboard_v2.html` with a minimal placeholder so the server can start without errors:

```html
<!DOCTYPE html>
<html><head><title>ALLEX v2 — coming soon</title></head>
<body style="font-family:sans-serif;padding:40px">
  <h1>Dashboard v2</h1><p>Implementation in progress (M28).</p>
</body></html>
```

- [ ] **Step 3: Add --v2 flag to dashboard.py**

In `src/pipeline/dashboard.py`, find where the template file is loaded in `_build_html()` (or wherever `dashboard.html` is read). Add a module-level flag and template selection:

```python
# At module level (near existing constants)
_USE_V2 = False  # set to True via --v2 CLI flag

def _template_name() -> str:
    return "dashboard_v2.html" if _USE_V2 else "dashboard.html"
```

Update `_build_html()` to call `_template_name()` instead of hardcoding `"dashboard.html"`.

Then in the CLI entry point (wherever `argparse` or `click` parses `dashboard --serve`), add:

```python
parser.add_argument("--v2", action="store_true", help="Serve dashboard v2 (experimental)")
# ...
if args.v2:
    import src.pipeline.dashboard as _dash
    _dash._USE_V2 = True
```

- [ ] **Step 4: Verify v1 still works**

Run: `python pipeline.py dashboard --serve`

Open http://localhost:8080 — must show the existing v1 dashboard unchanged.

Run: `python pipeline.py dashboard --serve --v2`

Open http://localhost:8080 — must show the "coming soon" placeholder.

- [ ] **Step 5: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass (v1 path unchanged).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/templates/dashboard_v1.html src/pipeline/templates/dashboard_v2.html src/pipeline/dashboard.py
git commit -m "feat(M28): backup dashboard v1, wire --v2 flag for fork development"
```

---

### Task 1: Backend — add dropoff data + required_fields to _load_data

**Files:**
- Modify: `src/pipeline/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing test — dropoff data in _load_data output**

Add to `tests/test_dashboard.py`:

```python
from src.pipeline.dashboard import _load_data
from src.pipeline.db import ensure_schema, get_connection


@pytest.fixture
def populated_db(tmp_path):
    db_path = tmp_path / "test.db"
    ensure_schema(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO company_records (id, domain, full_name, profile_id, source, klass, pipeline_stage, filter_pass, filter_reason, briefaktion) "
            "VALUES ('a1', 'a.de', 'A GmbH', 'medtech_germany', 'orbis', 'B', 'classified', 1, NULL, 'BA7')"
        )
        conn.execute(
            "INSERT INTO company_records (id, domain, full_name, profile_id, source, klass, pipeline_stage, filter_pass, filter_reason, briefaktion) "
            "VALUES ('a2', 'b.de', 'B GmbH', 'medtech_germany', 'orbis', 'D', 'classified', 1, NULL, 'BA7')"
        )
        conn.execute(
            "INSERT INTO company_records (id, domain, full_name, profile_id, source, klass, pipeline_stage, filter_pass, filter_reason, briefaktion) "
            "VALUES ('a3', 'c.de', 'C GmbH', 'medtech_germany', 'orbis', NULL, 'filtered', 0, 'too_large', 'BA7')"
        )
    return db_path


class TestLoadDataDropoff:
    def test_dropoff_key_exists(self, populated_db):
        data = _load_data(populated_db)
        assert "dropoff" in data

    def test_dropoff_has_stages(self, populated_db):
        data = _load_data(populated_db)
        assert "stages" in data["dropoff"]
        assert len(data["dropoff"]["stages"]) >= 1

    def test_required_fields_key_exists(self, populated_db):
        data = _load_data(populated_db)
        assert "required_fields" in data
        assert isinstance(data["required_fields"], list)
        assert len(data["required_fields"]) >= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_dashboard.py::TestLoadDataDropoff -v`

Expected: FAIL — `dropoff` key missing from `_load_data` output.

- [ ] **Step 3: Add dropoff computation + required_fields to _load_data**

In `src/pipeline/dashboard.py`, at the end of the `_load_data` function (before the `return data` line), add:

```python
    # Drop-off data: per-stage counts for drop-off view
    # Stages: ingested → filtered → scraped → classified → ownership → email_enriched → approved
    with get_connection(db_path) as conn:
        all_rows = conn.execute(
            "SELECT pipeline_stage, filter_pass, filter_reason, klass, approved_for_sendout, briefaktion "
            "FROM company_records"
        ).fetchall()

    dropoff_stages = _compute_dropoff(all_rows)
    data["dropoff"] = {"stages": dropoff_stages, "total": len(all_rows)}

    # Required letter fields (from check_letter.py)
    from src.pipeline.check_letter import _REQUIRED_FIELDS
    data["required_fields"] = [
        {"field": f, "label": label} for f, label in _REQUIRED_FIELDS
    ]
```

Add the `_compute_dropoff` helper function above `_load_data`:

```python
def _compute_dropoff(rows: list) -> list[dict]:
    """Compute per-stage pass/drop counts for the drop-off view."""
    total = len(rows)
    stages = []

    # Stage 1: Ingest (all records)
    stages.append({
        "stage": "Ingest",
        "sub": "ORBIS · WLW · Manual",
        "passed": total,
        "dropped": 0,
        "reasons": [],
    })

    # Stage 2: Hard Filter
    filtered_pass = [r for r in rows if r["filter_pass"] == 1 or r["filter_pass"] is None]
    filtered_drop = [r for r in rows if r["filter_pass"] == 0]
    reason_counts: dict[str, int] = {}
    for r in filtered_drop:
        reason = r["filter_reason"] or "Unknown"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    stages.append({
        "stage": "Hard Filter",
        "sub": "Branche · Größe · Land",
        "passed": len(filtered_pass),
        "dropped": len(filtered_drop),
        "reasons": [{"label": k, "n": v} for k, v in sorted(reason_counts.items(), key=lambda x: -x[1])],
    })

    # Stage 3: Scrape
    post_filter = filtered_pass
    scrape_fail = [r for r in post_filter if r["pipeline_stage"] == "scrape_failed"]
    scrape_pass = [r for r in post_filter if r["pipeline_stage"] != "scrape_failed"]
    stages.append({
        "stage": "Scrape",
        "sub": "Website + Impressum",
        "passed": len(scrape_pass),
        "dropped": len(scrape_fail),
        "reasons": [{"label": "Domain nicht erreichbar", "n": len(scrape_fail)}] if scrape_fail else [],
    })

    # Stage 4: Classify
    classified = [r for r in scrape_pass if r["klass"] is not None]
    not_classified = [r for r in scrape_pass if r["klass"] is None]
    klass_d = [r for r in classified if r["klass"] in ("D", "E")]
    klass_pass = [r for r in classified if r["klass"] in ("A", "B", "C", "S")]
    stages.append({
        "stage": "Classify",
        "sub": "AI · A/B/C/D/E",
        "passed": len(klass_pass),
        "dropped": len(klass_d) + len(not_classified),
        "reasons": [
            {"label": f"D/E — No-fit", "n": len(klass_d)},
        ] + ([{"label": "Nicht klassifiziert", "n": len(not_classified)}] if not_classified else []),
    })

    # Stage 5: Ownership Gate
    ownership_excluded = [r for r in klass_pass if r["klass"] == "S"]
    ownership_pass = [r for r in klass_pass if r["klass"] in ("A", "B", "C")]
    stages.append({
        "stage": "Ownership Gate",
        "sub": "OpenRegister · Blocklist",
        "passed": len(ownership_pass),
        "dropped": len(ownership_excluded),
        "reasons": [{"label": "S — Konzerntochter / PE", "n": len(ownership_excluded)}] if ownership_excluded else [],
    })

    # Stage 6: Approval
    ab_records = [r for r in ownership_pass if r["klass"] in ("A", "B")]
    approved = [r for r in ab_records if r["approved_for_sendout"] == 1]
    not_approved = [r for r in ab_records if r["approved_for_sendout"] != 1]
    stages.append({
        "stage": "Approval",
        "sub": "Manueller Review",
        "passed": len(approved),
        "dropped": len(not_approved),
        "reasons": [{"label": "In Bearbeitung / Felder fehlen", "n": len(not_approved)}] if not_approved else [],
    })

    return stages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_dashboard.py::TestLoadDataDropoff -v`

Expected: 3 PASS

- [ ] **Step 5: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/dashboard.py tests/test_dashboard.py
git commit -m "feat(M28): add dropoff data + required_fields to _load_data"
```

---

### Task 2: Dashboard v2 HTML template — shell + CSS design system

This is the largest task. Write `dashboard_v2.html` with the v2 structure. This task covers the HTML skeleton, all CSS, and the navigation JS. Content rendering (views) follows in subsequent tasks.

**Files:**
- Write: `src/pipeline/templates/dashboard_v2.html`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing test — new placeholders in v2 template**

Note: the `_html()` test helper must be called with `v2=True` so it loads `dashboard_v2.html`. Update `_html()` or add a `_html_v2()` variant that sets `_USE_V2 = True` before calling `_build_html()`.

Add to `tests/test_dashboard.py`:

```python
class TestBuildHtmlV2:
    def test_v2_no_raw_placeholders_remain(self):
        html = _html(v2=True)
        for placeholder in [
            "__DATA_JSON__",
            "__SERVE_MODE_JS__",
            "__LIVE_BADGE__",
            "__DATE_STR__",
            "__LOGO_IMG__",
            "__HUBSPOT_PORTAL_ID__",
            "__REGION_MAPPING_JSON__",
            "__LETTER_TEMPLATE__",
        ]:
            assert placeholder not in html, f"Placeholder {placeholder!r} not replaced"

    def test_v2_contains_sidebar(self):
        html = _html(v2=True)
        assert 'class="side"' in html or 'class="side-mode"' in html

    def test_v2_contains_subnav(self):
        html = _html(v2=True)
        assert "subnav" in html

    def test_v2_contains_review_mode(self):
        html = _html(v2=True)
        assert "review" in html.lower()

    def test_v2_contains_analyze_mode(self):
        html = _html(v2=True)
        assert "analyze" in html.lower()
```

- [ ] **Step 2: Run test to verify some fail (old template won't have sidebar)**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_dashboard.py::TestBuildHtmlV2 -v`

Expected: Some tests FAIL (old template has no sidebar).

- [ ] **Step 3: Write dashboard_v2.html**

Write `src/pipeline/templates/dashboard_v2.html`. The new template must:

1. **HTML shell**: Match the prototype's `index.html` structure — `<div class="app">` with grid layout (sidebar + top + subnav + main)
2. **CSS**: Port the full `styles-v3.css` content into a `<style>` block. Use all the CSS custom properties exactly as defined in the design spec (colors, spacing, typography)
3. **JS**: Port `app.js` routing logic (mode switching, sub-nav rendering) but replace mock `data.js` with the injected `__DATA_JSON__`
4. **Placeholders**: Keep all existing `__PLACEHOLDER__` strings exactly as they are — the backend replaces them

The template should contain these sections in order:
- `<!DOCTYPE html>` + `<head>` with Inter font link + `<style>` block
- `<body>` with `.app` grid container
- Sidebar (`.side`) with Review/Analyze mode buttons + user avatar
- Top bar (`.top`) with title, BA selector, tweaks toggle
- Sub-nav strip (`.subnav`, populated by JS)
- Main area (`.main`) with view containers
- Tweaks panel
- `<script>` block with:
  - Data initialization from `__DATA_JSON__`
  - Routing (mode/sub-tab switching)
  - View renderers (Review: Lead-Liste, Drop-off, Activity Log; Analyze: placeholder "Coming in M29")
  - PATCH/POST API helpers with `?actor=` param
  - Actor identity from localStorage

**Key implementation details:**

The JS data initialization:
```javascript
const SERVE_MODE = __SERVE_MODE_JS__;
const REGION_MAPPING = __REGION_MAPPING_JSON__;
const LETTER_TEMPLATE = __LETTER_TEMPLATE__;
let DATA = __DATA_JSON__;

if (SERVE_MODE) {
  fetch('/api/data')
    .then(r => r.json())
    .then(d => { DATA = d; renderCurrent(); });
}
```

The actor identity:
```javascript
function getActor() {
  return localStorage.getItem('allex_actor') || 'roman';
}
function setActor(a) {
  localStorage.setItem('allex_actor', a);
  document.getElementById('side-avatar').textContent = a === 'flo' ? 'FF' : 'RD';
}
```

API helper with actor param:
```javascript
async function patchCompany(domain, updates) {
  const actor = getActor();
  const resp = await fetch(`/api/company/${encodeURIComponent(domain)}?actor=${actor}`, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(updates),
  });
  return resp.json();
}
```

**This is a large file (~2000-2500 lines).** Build it section by section, starting with the shell, then CSS, then each view renderer. Use the prototype files as the pixel-perfect reference for styling. Use `dashboard_v1.html` (the v1 backup) as the reference for API integration patterns (PATCH whitelist, save feedback, compliment regen, etc.) — do not touch `dashboard_v1.html` itself.

- [ ] **Step 4: Update _build_html in dashboard.py if any new placeholders needed**

If you added any new placeholders (e.g., `__DROPOFF_JSON__`), update the `_build_html` function's `.replace()` chain to include them.

- [ ] **Step 5: Run tests**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/test_dashboard.py -v`

Expected: All tests pass (both old and new).

- [ ] **Step 6: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/templates/dashboard_v2.html src/pipeline/dashboard.py tests/test_dashboard.py
git commit -m "feat(M28): dashboard v2 shell — sidebar, subnav, design system, Review mode"
```

---

### Task 3: Review > Lead-Liste — queue + record editor

This task implements the core Review workflow: the left-panel queue with missing-field counts, the right-panel record editor with "Was fehlt" checklist, and the letter preview / website preview tabs.

**Files:**
- Modify: `src/pipeline/templates/dashboard_v2.html` (JS section)

- [ ] **Step 1: Implement renderReviewList()**

The function must:

1. **KPI bar** (3 cards): count records by missing-field severity
   - Blockiert (red): records with 4+ missing required fields
   - In Bearbeitung (amber): records with 1-3 missing fields
   - Bereit zum Export (green): 0 missing + approved_for_sendout=1

2. **Queue** (left 360px):
   - Filter records: klass IN ('A','B'), filter_pass=1, already_approached=0
   - Further filter by selected Briefaktion if not "Alle"
   - Compute missing count per record using `DATA.required_fields` list
   - Sort by `queueSort`: 'ready' (fewest missing first) or 'block' (most missing first)
   - Search filter by name/domain
   - Render each item with company name, domain, klass letter, missing count + severity color
   - Active item highlight: left blue bar + soft blue bg

3. **Record editor** (right):
   - Header: klass badge, company name, domain · region, counter "N / total", prev/next buttons
   - **"Was fehlt" checklist** (TOP — before all sections): iterate `DATA.required_fields`, check if field is filled on the active record
     - done (green check): field has a non-empty value
     - block (red): field is one of (street, plz_ort, full_name) and empty
     - warn (amber): field is empty but not critical
   - Field editor: single unified scroll (no Overview tab vs Letter Prep tab split), structured in three sections:

   **Section 1 — Overview**
   - Domain
   - Key Metrics (klass, pipeline_stage, filter_reason)
   - Classification + Reasoning (klass badge + target_description / classification notes)
   - Gesellschafter der Zielgesellschaft + reasoning (source of contact — Herkunft Ansprechpartner)
   - Kontakt (gf_email)

   **Section 2 — Address Block** (red border on missing blocking fields)
   - Ansprechpartner + Reasoning (how the contact was identified)
   - Anrede (select: Herr/Frau)
   - Vorname + Nachname (gf_name split)
   - Straße
   - PLZ + Stadt (plz_ort)
   - Region (select from REGION_MAPPING)

   **Section 3 — Letter Body** (all fields write-back to DB via PATCH)
   - Name/Firmenname (`full_name` — for letter heading)
   - Leistung Absatz 1 (`leistung_text`)
   - Leistung Absatz 2 (`leistung_absatz_2`)
   - Kompliment 1 (`compliment_draft`)
   - Kompliment 2 (`compliment_2`)
   - Mehrwerte (`mehrwerte`)

   > **Note:** Cross-check all Section 3 fields against `_REQUIRED_FIELDS` in `check_letter.py` — the Letter Body section must cover every required field not already in Overview or Address Block. Add any missing fields.

   - Each field: label + source hint, input/select/textarea, write via `patchCompany()`
   - Right preview panel: Brief-Vorschau tab (rendered letter with field highlights) and Website tab

4. **Bottom action bar**: Save, Skip, dynamic approval/warning button

Use the prototype `app.js` lines 84-414 as the visual reference. Replace mock data references with `DATA.records[activeIdx]` and `DATA.required_fields`.

- [ ] **Step 2: Wire up write-back**

Each editable field must:
- Listen for `change` or `blur` events
- Call `patchCompany(domain, {fieldName: newValue})`
- Show save feedback (brief green flash or checkmark)
- Re-compute "Was fehlt" after save

The compliment regeneration button must:
- Call `POST /api/compliment/${domain}?actor=claude`
- Update the textarea with the response
- Show feedback

The "Bereit · Zum Export hinzufügen" button must:
- Call `patchCompany(domain, {approved_for_sendout: 1})`
- Update KPI counts
- Move to next record

- [ ] **Step 3: Test in browser**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python pipeline.py dashboard --serve`

Open http://localhost:8080 and verify:
- Sidebar shows Review/Analyze modes
- Sub-nav shows Lead-Liste / Drop-off / Activity Log
- Queue populates with A/B records
- Clicking a record shows the editor with "Was fehlt"
- Editing a field and blurring saves (check terminal for PATCH log)
- Letter preview renders with real data
- KPI counts are accurate

- [ ] **Step 4: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/templates/dashboard_v2.html
git commit -m "feat(M28): Review > Lead-Liste — queue, record editor, Was fehlt, letter preview"
```

---

### Task 4: Review > Drop-off view

**Files:**
- Modify: `src/pipeline/templates/dashboard_v2.html` (JS section)

- [ ] **Step 1: Implement renderReviewDropoff()**

Use the prototype `app.js` lines 417-497 as the visual reference. Replace `D.dropoff` with `DATA.dropoff`.

The function must:
1. Page header: "Drop-off · BA #N Name" (from selected Briefaktion)
2. Stats strip: total ingested, total dropped (amber), approved (green)
3. Stage cards: iterate `DATA.dropoff.stages`, for each:
   - Step number badge (dark bg, white text)
   - Stage name + subtitle
   - Passed count (green) + percentage, dropped count (red) + percentage
   - Progress bar: width = passed/total ratio
   - Reason buckets: dot + label + mini proportion bar + count

- [ ] **Step 2: Test in browser**

Open http://localhost:8080, navigate to Review > Drop-off. Verify:
- All stages render with real data
- Reason buckets show actual filter_reason values from DB
- Counts are accurate

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/templates/dashboard_v2.html
git commit -m "feat(M28): Review > Drop-off — per-BA stage attrition view"
```

---

### Task 5: Review > Activity Log view

**Files:**
- Modify: `src/pipeline/templates/dashboard_v2.html` (JS section)

- [ ] **Step 1: Implement renderReviewActivity()**

Use the prototype `app.js` lines 499-576 as the visual reference. Replace `D.activity` with a live API call to `GET /api/activity`.

The function must:
1. Fetch activity data: `fetch('/api/activity?limit=100')`
2. Page header: "Activity Log" + stats (total today, Claude count, manual count)
3. Actor filter chips: Alle / Nur Claude / Nur manuell — filter the fetched data client-side or re-fetch with `?actor=claude`
4. Activity table: each row shows timestamp, actor dot + name, kind badge, company name, field (monospace), old→new diff
5. Kind badge colors from prototype CSS:
   - gen/regen: warm gold bg
   - enrich: sage green bg
   - edit: blue bg
   - approve: green bg
   - system: gray bg

- [ ] **Step 2: Test in browser**

Open http://localhost:8080, navigate to Review > Activity Log. Verify:
- Activity entries appear (requires M27 backend to have logged some changes)
- Actor filter works
- Kind badges render with correct colors
- Old→new diff shows with strikethrough old and bold new

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/templates/dashboard_v2.html
git commit -m "feat(M28): Review > Activity Log — field change feed with actor filters"
```

---

### Task 6: Ownership review workflow in record editor

Port the existing Requires Attention functionality (Resolve/Pass/Exclude) into the record editor's "Was fehlt" section.

**Files:**
- Modify: `src/pipeline/templates/dashboard_v2.html` (JS section)

- [ ] **Step 1: Add ownership review actions to "Was fehlt" checklist**

When a record has `pipeline_stage === 'ownership_review_needed'`, add a special checklist item:
- Label: "Eigentümer prüfen"
- Hint: shows `ownership_reason` text
- Action: opens an inline panel with three buttons:
  - **Resolve**: POST `/api/resolve-parent/${domain}` with editable parent name input
  - **Pass**: PATCH `{is_subsidiary: 0, pipeline_stage: 'ownership_gated'}` + flash green
  - **Exclude (S)**: PATCH `{klass: 'S', is_subsidiary: 1, reclassify_reason: 'ownership_excluded'}` + flash red

This replaces the old 3-column "Requires Attention" table. The UX is now: see ownership issue in the "Was fehlt" list → click "Bearbeiten" → resolve inline → move to next record.

- [ ] **Step 2: Test in browser**

Find a record with `ownership_review_needed` status. Verify the Resolve/Pass/Exclude actions work and the record updates correctly.

- [ ] **Step 3: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/templates/dashboard_v2.html
git commit -m "feat(M28): ownership review actions in record editor Was fehlt section"
```

---

### Task 7: Analyze mode placeholder + docs

**Files:**
- Modify: `src/pipeline/templates/dashboard_v2.html`
- Modify: `ai/ROADMAP.md`
- Modify: `ai/ARCHITECTURE.md`

- [ ] **Step 1: Add Analyze placeholder views**

For each Analyze sub-tab (Funnel, Cohorts, Klassen, Bottlenecks), render a simple placeholder:

```html
<div class="analyze">
  <h2>Funnel</h2>
  <p class="lead">Kommt in M29.</p>
</div>
```

This ensures the navigation works end-to-end without blocking M28 on the Analyze implementation.

- [ ] **Step 2: Update ROADMAP.md**

Mark M28 as delivered in the "Next Milestones" table.

- [ ] **Step 3: Update ARCHITECTURE.md**

Add a section describing the v2 dashboard architecture:
- Two-mode navigation (Review/Analyze) with sub-tabs
- Design system (CSS custom properties)
- Data flow: `_load_data()` → `__DATA_JSON__` → JS routing → view renderers
- Activity log integration: `GET /api/activity` fetched client-side

- [ ] **Step 4: Run full test suite**

Run: `cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline" && python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 5: Final visual check**

Run the dashboard in serve mode. Walk through:
- [ ] Review > Lead-Liste: queue loads, records editable, letter preview works
- [ ] Review > Drop-off: stages render with real data
- [ ] Review > Activity Log: entries appear, filters work
- [ ] Analyze > all 4 tabs: show placeholder text
- [ ] Sidebar mode switching works
- [ ] Sub-nav tab switching works
- [ ] BA selector filters correctly
- [ ] Actor toggle in sidebar footer works
- [ ] Save/Skip/Approve buttons work
- [ ] Compliment regeneration works

- [ ] **Step 6: Commit + push**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add ai/ROADMAP.md ai/ARCHITECTURE.md ai/PLAN-M28.md src/pipeline/templates/dashboard_v2.html
git commit -m "docs(M28): dashboard v2 shell + Review mode — ROADMAP + ARCHITECTURE updated"
git push
```

---

### Task 8: Promote v2 to default (explicit gate)

**Do not execute this task until all of Tasks 0–7 pass the visual checklist and full test suite.**

This task is deliberately separate so promotion is a conscious decision, not an accidental side-effect of implementation.

**Files:**
- Modify: `src/pipeline/dashboard.py`

- [ ] **Step 1: Change the default template to v2**

In `src/pipeline/dashboard.py`, update `_template_name()`:

```python
def _template_name() -> str:
    # v1 still accessible via --v1 flag for emergency rollback
    return "dashboard_v1.html" if _USE_V1 else "dashboard_v2.html"
```

Rename the flag from `--v2` to `--v1` in the CLI argument parser (v2 is now the default; `--v1` is the rollback escape hatch).

- [ ] **Step 2: Verify v2 serves by default**

Run: `python pipeline.py dashboard --serve`

Opens http://localhost:8080 — must show v2.

Run: `python pipeline.py dashboard --serve --v1`

Opens http://localhost:8080 — must show v1 (rollback confirmed working).

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
cd "C:/Users/X1/Documents/OneDrive - Kamu Kapital/Dokumente - Kamu Kapital/CLAUDE_REPURO/lead-pipeline"
git add src/pipeline/dashboard.py
git commit -m "feat(M28): promote dashboard v2 to default — v1 accessible via --v1 flag"
git push
```
