# M17: BA Prep Hardening — Approval Gate, All Fields Editable, Region, Letter Preview

## Summary

Closes the BA prep loop: every A/B record gets a % complete score based on 6 required send-out fields, must be manually approved before export, and all 36 Serienbrief merge fields are editable in the side panel. Region is populated from `Städte-Regionen-Matching` (~1,208 / 2,420 records covered by bulk command). The side panel right pane toggles between website and a structured letter preview showing all merge fields with missing-field highlighting. The "Blockers" card becomes a 3-section Action Queue. Final export format is PDF (future milestone) — no Excel export in this milestone.

Done when: `pytest tests/` passes, `enrich-regions --dry-run` shows ~1,208 matchable records, prep table shows % complete per row, letter preview renders with red missing-field markers, save works for all new fields, and `export --approved-only` filters correctly.

---

## Locked Decisions

- `approved_for_sendout` — INTEGER (0/1), not a timestamp. Simple and filterable.
- **% complete** — based on exactly 6 required send-out fields: `gf_email`, `compliment_draft`, `compliment_2`, `region`, `anrede`, `approved_for_sendout`. Shown as "N/6" + colour-coded percentage bar in prep table. 100% = all 6 filled AND approved. Computed client-side from the loaded record data.
- `region_prep` — stores preposition+region ("im Allgäu") for letter merge. `region` stores bare name ("Allgäu") for display/filtering. Both populated together.
- Region mapping: case-insensitive exact city match. ~50% coverage acceptable; rest filled manually via side panel. No fuzzy matching.
- Region mapping embedded as JS constant in the HTML (not a server endpoint) — works in static mode.
- Letter Preview is client-side only — no server call, built from loaded record data.
- **No per-record export** — final export format is PDF (future milestone). This milestone: review + approve only.
- `export --approved-only` flag added to `pipeline.py export` so the approval gate has teeth.
- Export `Region` column updated to use `region_prep` (not bare `region`) — it's what the Word merge template actually uses.
- `enrich-regions` is a standalone CLI command, not merged into `ingest`, so it can be re-run independently.
- No `autoFillRegion()` JS button — users run `enrich-regions` CLI for bulk; manual edit in panel for individual records.
- All new editable fields added to `_WRITEBACK_FIELDS` (silent-drop trap — see LEARNINGS.md).

---

## Plan

### Step 1 — DB schema: `approved_for_sendout` + `region_prep`

**File: `src/pipeline/db.py`**

Add to `_OUTREACH_COLUMNS` (triggers `ALTER TABLE ADD COLUMN` via `_migrate_schema()`):
```python
("approved_for_sendout", "INTEGER NOT NULL DEFAULT 0"),
("region_prep", "TEXT"),
```

### Step 2 — Models

**File: `src/pipeline/models.py`**

Add after `region` field:
```python
region_prep: Optional[str] = None
approved_for_sendout: int = 0
```

### Step 3 — Region mapping module

**New file: `src/pipeline/region_lookup.py`**

```python
"""City → (region, region_prep) lookup from Städte-Regionen-Matching sheet."""
from __future__ import annotations
from functools import lru_cache
from typing import Optional
import openpyxl
from src.config import settings


@lru_cache(maxsize=1)
def load_region_mapping() -> dict[str, tuple[str, str]]:
    """Return {city_lower: (region, region_prep)}. Cached — reads Excel once per process."""
    wb = openpyxl.load_workbook(settings.SOURCE_EXCEL, read_only=True, data_only=True)
    ws = wb["Städte-Regionen-Matching"]
    mapping: dict[str, tuple[str, str]] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        city, region, region_prep = row[0], row[1], row[3]
        if city and region and region_prep:
            mapping[str(city).strip().lower()] = (
                str(region).strip(),
                str(region_prep).strip(),
            )
    wb.close()
    return mapping


def lookup_region(city: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (region, region_prep) or (None, None) if not found."""
    if not city:
        return None, None
    entry = load_region_mapping().get(city.strip().lower())
    return entry if entry else (None, None)
```

### Step 4 — `enrich-regions` command

**File: `src/pipeline/ingest.py`** — add function:

```python
def enrich_regions(dry_run: bool = False) -> dict:
    """Populate region + region_prep for records with missing region, using city lookup."""
    from src.pipeline.region_lookup import load_region_mapping
    mapping = load_region_mapping()

    with get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows = conn.execute(
            "SELECT domain, city FROM company_records "
            "WHERE (region IS NULL OR region = '') AND city IS NOT NULL"
        ).fetchall()

    updates = [
        (region, region_prep, row["domain"])
        for row in rows
        if (entry := mapping.get((row["city"] or "").strip().lower())) is not None
        for region, region_prep in [entry]
    ]

    stats = {"total_checked": len(rows), "matched": len(updates), "updated": 0}
    if dry_run:
        return stats

    with get_connection(settings.PIPELINE_DB_PATH) as conn:
        for region, region_prep, domain in updates:
            conn.execute(
                "UPDATE company_records SET region = ?, region_prep = ? WHERE domain = ?",
                (region, region_prep, domain),
            )
    stats["updated"] = len(updates)
    return stats
```

**File: `pipeline.py`** — add subparser before profile-required dispatch:

```python
subparsers.add_parser(
    "enrich-regions",
    help="Populate region + region_prep from Städte-Regionen-Matching sheet (M17)",
    parents=[base_parser],
)
```

Handler block:
```python
if args.command == "enrich-regions":
    from src.pipeline.ingest import enrich_regions
    result = enrich_regions(dry_run=args.dry_run)
    dry = "(DRY RUN) " if args.dry_run else ""
    print(f"\nRegion enrichment {dry}complete")
    print(f"  Checked (missing region): {result['total_checked']}")
    print(f"  Matched in mapping:       {result['matched']}")
    if not args.dry_run:
        print(f"  Updated in DB:            {result['updated']}")
    return
```

### Step 5 — `_WRITEBACK_FIELDS` expansion

**File: `src/pipeline/dashboard.py`**

Add to `_WRITEBACK_FIELDS` frozenset:
```python
"approved_for_sendout",
"region",
"region_prep",
"anrede",
"salutation",
"gf_name",
"leistung_text",
```

### Step 6 — Embed region mapping in dashboard

**File: `src/pipeline/dashboard.py`**

In `_render_dashboard()`, add template substitution:
```python
from src.pipeline.region_lookup import load_region_mapping
mapping_js = {
    city: {"region": region, "region_prep": region_prep}
    for city, (region, region_prep) in load_region_mapping().items()
}
html = html.replace(
    "__REGION_MAPPING_JSON__",
    json.dumps(mapping_js, ensure_ascii=False)
)
```

**File: `src/pipeline/templates/dashboard.html`**

In bootstrap `<script>` section:
```javascript
const REGION_MAPPING = __REGION_MAPPING_JSON__;
```

### Step 7 — Fix export: use `region_prep`, add `--approved-only`

**File: `src/pipeline/export.py`**

In `_record_to_row()`, change:
```python
"Region": rec.region_prep or rec.region or "",   # was: rec.region or ""
```

In `export_cmd()`, add `--approved-only` logic:
```python
# export_cmd signature already has dry_run, via_cli — add:
def export_cmd(profile, dry_run=False, via_cli=False, approved_only=False):
    ...
    query = "SELECT * FROM company_records WHERE klass IN ('A','B')"
    if approved_only:
        query += " AND approved_for_sendout = 1"
```

**File: `pipeline.py`** — add `--approved-only` flag to export parser:
```python
export_parser.add_argument(
    "--approved-only",
    action="store_true",
    help="Export only records with approved_for_sendout=1",
)
```
And pass to dispatch: `approved_only=getattr(args, "approved_only", False)`.

### Step 8 — `buildWriteBack()` — all Serienbrief fields

**File: `src/pipeline/templates/dashboard.html`**

Restructure writeback into named sections. Add after existing outreach fields and before compliment fields:

```html
<!-- Letter Fields section -->
<div class="writeback-section">
  <h3>Letter Fields</h3>
  <div class="form-row">
    <label>Anrede</label>
    <select id="wb-anrede" ${disabled}>
      <option value="">—</option>
      <option value="Herr" ${rec.anrede==='Herr'?'selected':''}>Herr</option>
      <option value="Frau" ${rec.anrede==='Frau'?'selected':''}>Frau</option>
    </select>
  </div>
  <div class="form-row">
    <label>GF Name</label>
    <input type="text" id="wb-gf-name" value="${escHtml(rec.gf_name||'')}" ${disabled}>
  </div>
  <div class="form-row">
    <label>Salutation</label>
    <input type="text" id="wb-salutation" value="${escHtml(rec.salutation||'')}" ${disabled}
           placeholder="Sehr geehrter Herr Müller">
  </div>
  <div class="form-row">
    <label>Region</label>
    <input type="text" id="wb-region" value="${escHtml(rec.region||'')}" ${disabled}
           placeholder="Allgäu">
    <input type="text" id="wb-region-prep" value="${escHtml(rec.region_prep||'')}" ${disabled}
           placeholder="im Allgäu" style="margin-top:4px;">
    <div style="font-size:10px;color:#9ca3af;margin-top:2px;">
      ${rec.city && REGION_MAPPING[rec.city.toLowerCase()]
        ? `Mapping found: <strong>${REGION_MAPPING[rec.city.toLowerCase()].region_prep}</strong> — edit above to override`
        : (rec.city ? 'City not in mapping — enter manually' : 'No city on record')}
    </div>
  </div>
  <div class="form-row">
    <label>Leistung Absatz 1</label>
    <textarea id="wb-leistung" ${disabled}>${escHtml(rec.leistung_text||'')}</textarea>
  </div>
</div>

<!-- Approval section -->
<div class="writeback-section">
  <h3>Send-out Approval</h3>
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;font-weight:600;">
    <input type="checkbox" id="wb-approved" ${rec.approved_for_sendout?'checked':''} ${disabled}
           style="width:16px;height:16px;">
    Approved for BA send-out
  </label>
  <div style="font-size:11px;color:#6b7280;margin-top:4px;">
    ${completenessHtml(rec)}
  </div>
</div>
```

Add `completenessHtml(rec)` JS helper:
```javascript
function completenessHtml(rec) {
  const fields = [
    { key: 'gf_email',        label: 'Email',    val: rec.gf_email },
    { key: 'compliment_draft',label: 'K1',       val: rec.compliment_draft },
    { key: 'compliment_2',    label: 'K2',       val: rec.compliment_2 },
    { key: 'region',          label: 'Region',   val: rec.region },
    { key: 'anrede',          label: 'Anrede',   val: rec.anrede },
  ];
  const filled = fields.filter(f => f.val).length;
  const pct = Math.round(filled / fields.length * 100);
  const dots = fields.map(f =>
    `<span title="${f.label}" style="color:${f.val?'#16a34a':'#dc2626'};font-size:14px;">●</span>`
  ).join(' ');
  const color = pct === 100 ? '#16a34a' : pct >= 60 ? '#d97706' : '#dc2626';
  return `${dots} &nbsp;<span style="font-weight:700;color:${color}">${filled}/5 fields</span>
          ${rec.approved_for_sendout ? ' <span style="color:#16a34a;font-weight:700;">✓ Approved</span>' : ''}`;
}
```

Note: approval (`approved_for_sendout`) is the 6th gate, shown separately as the checkbox above.

Update `saveWriteback()` to include new fields:
```javascript
anrede: document.getElementById('wb-anrede').value || null,
gf_name: document.getElementById('wb-gf-name').value || null,
salutation: document.getElementById('wb-salutation').value || null,
region: document.getElementById('wb-region').value || null,
region_prep: document.getElementById('wb-region-prep').value || null,
leistung_text: document.getElementById('wb-leistung').value || null,
approved_for_sendout: document.getElementById('wb-approved').checked ? 1 : 0,
```

### Step 9 — % complete in prep table

**File: `src/pipeline/templates/dashboard.html`** — `renderPrepTable()`

Add "% Ready" as first column. Computed from same 6 fields (5 data + 1 approved):

```javascript
function prepCompleteness(r) {
  const fields = [r.gf_email, r.compliment_draft, r.compliment_2, r.region, r.anrede];
  const filled = fields.filter(Boolean).length;
  const approved = r.approved_for_sendout ? 1 : 0;
  const total = filled + approved;
  const pct = Math.round(total / 6 * 100);
  const color = pct === 100 ? '#16a34a' : pct >= 50 ? '#d97706' : '#dc2626';
  return `<span style="font-weight:700;color:${color};font-size:11px;">${pct}%</span>`;
}
```

Sort: 100% approved at bottom (done), then by ascending completion (needs most work first).

Update prep table column headers to include "Ready" as first column.

### Step 10 — Action Queue redesign (`renderBlockers`)

**File: `src/pipeline/templates/dashboard.html`**

Replace flat list with 3 sections. Each section is a `<div>` with a heading:

```
━━ RUN NOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [N]  Records need scraping      python pipeline.py scrape
  [N]  Scraped, unclassified      python pipeline.py classify

━━ MANUAL REVIEW ━━━━━━━━━━━━━━━━━━━━━
  [N]  C records → reclassify      → Requires Attention ›
  [N]  A/B missing email           → Requires Attention ›
  [N]  A/B missing K1 or K2
  [N]  A/B missing region
  [N]  A/B missing anrede

━━ READY TO EXPORT ━━━━━━━━━━━━━━━━━━━
  [N]  A/B: all fields + approved  python pipeline.py export --approved-only
```

A record is "ready" only when all 5 data fields filled AND `approved_for_sendout == 1`.

### Step 11 — KPI: approved + ready count

**File: `src/pipeline/templates/dashboard.html`** — `renderPrepKPIs()`

Add two new KPI cards:
- "Approved" — count of A/B with `approved_for_sendout == 1`
- "Ready to Export" — count of A/B with all 5 fields + approved (the definitive number)

Make "Ready to Export" the visually dominant card (kpi-large or kpi-alert/kpi-good based on count).

### Step 12 — Tests

**File: `tests/test_m17.py`**

```
test_approved_for_sendout_column_added          — ensure_schema adds column, default=0
test_region_prep_column_added                   — ensure_schema adds column
test_enrich_regions_dry_run                     — returns matched/total, no DB writes
test_enrich_regions_updates_db                  — known city → region + region_prep populated
test_enrich_regions_skips_already_filled        — records with existing region not overwritten
test_enrich_regions_unknown_city                — unknown city → no update, no error
test_lookup_region_found                        — lookup_region('Hamburg') returns non-null tuple
test_lookup_region_case_insensitive             — 'HAMBURG' == 'hamburg' result
test_lookup_region_not_found                    — 'Nonexistent City XYZ' → (None, None)
test_patch_approved_for_sendout                 — PATCH approved_for_sendout=1 persists
test_patch_new_letter_fields                    — anrede, salutation, gf_name, leistung_text,
                                                  region, region_prep all accepted via PATCH
test_export_approved_only                       — export_cmd with approved_only=True only
                                                  includes approved records
test_export_region_prep_used                    — _record_to_row uses region_prep for Region col
```

---

## Better Engineering Notes

- The `export_cmd` signature change (adding `approved_only`) requires updating the lambda in `pipeline.py` dispatch dict — easy to miss since it's a keyword arg.
- `region_prep` vs `region` in export: the Word template uses the letter-form. After this milestone `Region` = `region_prep or region`. Note this in ARCHITECTURE.md.
- `completenessHtml()` and `prepCompleteness()` share the same field list — keep them in sync. If a required field changes, update both.
- The 5-field completeness check (email, K1, K2, region, anrede) deliberately excludes `salutation` and `leistung_text` — those are important but not strict blockers. If the definition of "ready" changes, update both JS functions and the `renderBlockers()` ready-count logic.

---

## AI Validation Plan

```bash
# Tests
pytest tests/test_m17.py -v
# Expected: 13 tests pass

pytest tests/ -q
# Expected: 181 + 13 = 194 pass, 0 fail

# Region enrichment
python pipeline.py enrich-regions --dry-run
# Expected:
#   Checked (missing region): 2420
#   Matched in mapping: ~1208

python pipeline.py enrich-regions
# Expected: Updated in DB: ~1208

python -c "
import sqlite3; conn = sqlite3.connect('data/pipeline.db')
print('With region:', conn.execute(\"SELECT COUNT(*) FROM company_records WHERE region != '' AND region IS NOT NULL\").fetchone()[0])
"
# Expected: ~1208

# Export with --approved-only (dry run, should export 0 records initially)
python pipeline.py export --approved-only --dry-run
# Expected: no error, 0 records exported (none approved yet)

# Dashboard
python pipeline.py dashboard --dry-run
# Expected: builds without error, > 5MB

# Manual verification (--serve mode):
# 1. python pipeline.py dashboard --serve
# 2. BA Prep tab → prep table: first column shows "0%" for all rows (none approved)
# 3. Action Queue shows 3 sections; "Ready to Export: 0"
# 4. Click an A/B row → Letter Fields section visible (Anrede, GF Name, Salutation, Region x2, Leistung)
# 5. Region fields: hint shows mapping suggestion if city found
# 6. Toggle "Letter Preview" → all fields shown, missing ones in red
# 7. Fill fields, Save → completeness dots update in panel
# 8. Check "Approved for BA" → Save → row in table shows 100%, Action Queue "Ready to Export: 1"
# 9. KPI "Ready to Export" increments
```

---

## AI Validation Results

```
pytest tests/test_m17.py -v
→ 15 passed in 5.26s

pytest tests/ -q
→ 196 passed in 5.91s (0 fail, 0 error)

python pipeline.py enrich-regions --dry-run
→ Checked (missing region): 2420
  Matched in mapping:       940
  (Note: 940 not ~1208 as estimated — mapping covers ~39% of records;
   the Städte-Regionen-Matching sheet has 709 rows but many ORBIS cities don't appear in it)

python pipeline.py enrich-regions
→ Updated in DB: 940

python pipeline.py export --approved-only --dry-run
→ 0 records exported (none approved yet — correct)

python pipeline.py dashboard --dry-run
→ 5,353,260 chars (>5MB, no error)
```

Deviations from plan:
- `enrich_regions` needed `ensure_schema(db_path)` call added — without it the first live run fails with "no such column: region_prep" on the existing DB. Added at function start.
- Coverage was 940 instead of ~1,208 — the source mapping sheet has city names for only a subset of ORBIS records. Acceptable; rest filled manually via side panel.

---

## User Validation Walkthrough

1. `python pipeline.py enrich-regions` — expect ~1,208 records updated
2. `python pipeline.py dashboard --serve`
3. BA Prep tab → all rows show "X%" in first column, most at low %
4. Note KPI cards — "Ready to Export: 0"
5. Action Queue — 3 sections, "Ready to Export: 0" at bottom
6. Click any A/B row → side panel → Letter Fields section with all editable merge fields
7. Fill in missing fields, click Save
8. Toggle right pane to "Letter Preview" — all merge fields visible, filled ones in black, missing in red
9. Check "Approved for BA" → Save → row turns 100%, Action Queue updates
10. `python pipeline.py export --approved-only --dry-run` — confirms N approved records would export

---

## M17 Revision — Sideview Redesign (post-delivery)

**Status: Specified, not yet executed.**

### Problems identified

1. **Duplication.** `buildPanelLeft()` renders Region, Leistung, GF Name, Anrede, Salutation as static info — then `buildWriteBack()` repeats all of them as editable inputs. Same data, two DOM locations, no clear purpose boundary.
2. **Missing letter fields.** `Leistung Absatz 2` and `Mehrwerte` are hardcoded `""` in `export.py`. No DB column, not editable anywhere.
3. **Salutation not gated.** Editable in sideview but excluded from the 5-field completeness check. A letter without a salutation is broken.
4. **Region linkage.** Export uses `region_prep or region`. If user fills `region` but not `region_prep`, export sends bare "Allgäu" instead of "im Allgäu". The hint text exists but no auto-fill on open.
5. **No separation of concerns.** Reclassify (klass buttons), Outreach tracking (dates, status), and Letter prep fields are all in one `buildWriteBack()` block with no logical grouping.

### Letter field audit (against SERIENBRIEFE_COLUMNS in export.py)

| Merge field | DB field | Currently editable? | In completeness? | Gap |
|---|---|---|---|---|
| Name Briefkopf | full_name | read-only | — | none |
| Name Absatz 1 | gf_name | yes | no | — |
| Gesellschafter | gesellschafter_name | **no** | no | not editable |
| Anrede | anrede | yes | yes | — |
| **Salutation** | salutation | yes | **no** | missing from gate |
| Street Address | street | read-only | — | — |
| PLZ + Stadt | plz_ort | read-only | — | — |
| Region | region_prep or region | yes | yes (bare region) | region_prep not auto-synced |
| **Leistung Absatz 1** | leistung_text | yes | no | not in gate |
| **Leistung Absatz 2** | — | **no DB column** | no | **entire gap** |
| **Mehrwerte** | — | **no DB column** | no | **entire gap** |
| Kompliment 1 | compliment_draft | yes | yes | — |
| Kompliment 2 | compliment_2 | yes | yes | — |
| Email | gf_email | yes | yes | — |

### Required changes

#### A. Backend (db.py, models.py, classify.py, export.py, dashboard.py)

Both `leistung_absatz_2` and `mehrwerte` are **classify-step generated**, not manually filled. Pattern mirrors `leistung_text`: pipeline generates the default, sideview allows manual override. Auto-D records and name-dupes get empty string (no Claude call).

**File: `src/pipeline/db.py`** — add to `_OUTREACH_COLUMNS`:
```python
("leistung_absatz_2", "TEXT"),
("mehrwerte", "TEXT"),
```

**File: `src/pipeline/models.py`** — add fields:
```python
leistung_absatz_2: Optional[str] = None
mehrwerte: Optional[str] = None
```

**File: `src/pipeline/classify.py`**

1. `_build_prompt()` — extend JSON output template (increase max_tokens from 200 → 350):
```
"leistung_absatz_2": "one of: Medizinprodukt-Händler | Sprechstundenbedarf | Medizintechnik-Service | Mixed",
"mehrwerte": "1-2 German sentences: specific ways a healthcare distribution buy-and-build platform can benefit this company"
```

2. `_parse_result()` — add:
```python
"leistung_absatz_2": str(raw.get("leistung_absatz_2", ""))[:80],
"mehrwerte": str(raw.get("mehrwerte", ""))[:400],
```

3. Auto-D / name-dupe result dicts — add `"leistung_absatz_2": ""` and `"mehrwerte": ""`.

4. `update_classify_result()` call in `classify_cmd()` — pass new fields through.

**File: `src/pipeline/db.py` — `update_classify_result()`** — add parameters and update SET clause:
```python
def update_classify_result(conn, domain, klass, services_score, service_flag,
    distributor_flag, ssb_flag, leistung_text, leistung_absatz_2, mehrwerte,
    reason_code, reasoning, classified_at) -> int:
    cursor = conn.execute("""
        UPDATE company_records
        SET klass=?, services_score=?, service_flag=?, distributor_flag=?,
            ssb_flag=?, leistung_text=?, leistung_absatz_2=?, mehrwerte=?,
            reclassify_reason=?, reasoning=?, classified_at=?,
            pipeline_stage='classified'
        WHERE domain=?
    """, (klass, services_score, 1 if service_flag else 0,
          1 if distributor_flag else 0, 1 if ssb_flag else 0,
          leistung_text, leistung_absatz_2, mehrwerte,
          reason_code, reasoning, classified_at, domain))
    return cursor.rowcount
```

**File: `src/pipeline/export.py`** — update `_record_to_row()`:
```python
"Leistung Absatz 2": rec.leistung_absatz_2 or "",
"Mehrwerte": rec.mehrwerte or "",
```

**File: `src/pipeline/dashboard.py`** — add to `_WRITEBACK_FIELDS`:
```python
"leistung_absatz_2",
"mehrwerte",
"gesellschafter_name",  # editable for corrections
```

Upstream steps unaffected: ingest, filter, scrape, enrich all unchanged.

#### B. Frontend (dashboard.html)

**Redesign `buildPanelLeft()` and `buildWriteBack()` into a two-tab left panel:**

**Tab 1 — Overview (read-only):**
- Company name (large) + Klass badge + SSB badge
- Domain (clickable)
- MA | Revenue (Tsd EUR) | Owner Age
- City + Region (display)
- GF Name + GF Email (read-only)
- Reasoning (scrollable block)
- HubSpot link if exists

**Tab 2 — Letter Prep (all editable, in letter flow order):**

Section "Address Block":
1. GF Name → text input (fills Name Absatz 1, First/Last Name in export)
2. Gesellschafter → text input (NEW — currently not editable)
3. Anrede → Herr/Frau dropdown
4. Salutation → text input + **Generate button** (builds "Sehr geehrter/e [Anrede] [Last Name]" from fields above)
5. Street Address → read-only display
6. PLZ + Stadt → read-only display
7. Region (display name) → text input with mapping hint
8. Region Prep (letter form) → text input, auto-filled on panel open from city mapping if empty

Section "Letter Body":
9. Leistung Absatz 1 → textarea
10. Leistung Absatz 2 → textarea (NEW)
11. Mehrwerte → textarea (NEW)
12. Kompliment 1 → textarea
13. Kompliment 2 → textarea

Section "Contact":
14. GF Email → email input

Section "Outreach" (collapsible, collapsed by default):
- Outreach Status, Sent At, FU1, FU2, Comment, FU Comment

Section "Classification":
- Klass buttons [A/B/C/D/E]

Section "Approval":
- Completeness dots (updated — see below)
- Approved checkbox
- Save button

**Update `completenessHtml()` and `prepCompletenessPct()`:**

Add `salutation` to required fields. New 6-field gate:
```javascript
const fields = [
  { label: 'Email',      val: rec.gf_email },
  { label: 'Anrede',     val: rec.anrede },
  { label: 'Salutation', val: rec.salutation },   // ← add
  { label: 'Region',     val: rec.region },
  { label: 'K1',         val: rec.compliment_draft },
  { label: 'K2',         val: rec.compliment_2 },
];
```
Update all references from "5 fields" → "6 fields", denominator 5 → 6.

**Region auto-fill on panel open:**
In `openPanel(rec)`, after loading: if `rec.region_prep` is empty and `rec.city` is in `REGION_MAPPING`, populate `#wb-region-prep` input with the mapped value immediately (without saving — user must Save to persist).

**Salutation auto-generate button:**
```javascript
function autoSalutation() {
  const anrede = document.getElementById('wb-anrede').value;
  const name = document.getElementById('wb-gf-name').value.trim();
  if (!anrede || !name) return;
  const parts = name.split(' ');
  const last = parts[parts.length - 1];
  const prefix = anrede === 'Herr' ? 'Sehr geehrter Herr' : 'Sehr geehrte Frau';
  document.getElementById('wb-salutation').value = `${prefix} ${last}`;
}
```

**Update `saveWriteback()` payload:**
Add: `leistung_absatz_2`, `mehrwerte`, `gesellschafter_name`

### Tests to add (tests/test_m17b.py)

```
test_leistung_absatz_2_column_added     — ensure_schema adds column, default NULL
test_mehrwerte_column_added             — ensure_schema adds column, default NULL
test_patch_leistung_absatz_2            — PATCH leistung_absatz_2 persists
test_patch_mehrwerte                    — PATCH mehrwerte persists
test_export_leistung_absatz_2_used      — _record_to_row maps leistung_absatz_2 → "Leistung Absatz 2"
test_export_mehrwerte_used              — _record_to_row maps mehrwerte → "Mehrwerte"
```

### Parallel execution split

Two agents can work simultaneously with zero file overlap:

**Agent A — Backend:**
- `src/pipeline/db.py`
- `src/pipeline/models.py`
- `src/pipeline/export.py`
- `src/pipeline/dashboard.py`
- `tests/test_m17b.py` (new file)

**Agent B — Frontend:**
- `src/pipeline/templates/dashboard.html` (only)

Shared contract (Agent A writes to DB, Agent B reads via JSON): field names are `leistung_absatz_2`, `mehrwerte`, `gesellschafter_name` — both agents use these exact strings.

### Done when
- `pytest tests/` passes (196 + 6 = 202)
- Dashboard serves with two-tab left panel
- Salutation auto-generate works
- Region Prep auto-fills on open when city is in mapping
- Leistung Absatz 2 + Mehrwerte editable and save correctly
- Completeness gate shows 6 fields including salutation
- Export test confirms `Leistung Absatz 2` and `Mehrwerte` columns populated from DB

---

### Revision AI Validation Results

**Backend agent (db.py, models.py, classify.py, export.py, dashboard.py, tests/test_m17b.py):**

```
pytest tests/test_m17b.py -v
→ 11 passed

pytest tests/ -q
→ 207 passed (0 fail, 0 error)

python pipeline.py classify --dry-run
→ no error

python pipeline.py dashboard --dry-run
→ 5,360,000+ chars (> 5MB, no error)
```

Changes delivered:
- `db.py`: `leistung_absatz_2` + `mehrwerte` added to `_OUTREACH_COLUMNS`; `update_classify_result()` extended with both fields
- `models.py`: both fields added as `Optional[str] = None` after `leistung_text`
- `classify.py`: prompt extended with `leistung_absatz_2` (constrained vocab) + `mehrwerte` (1-2 sentence German); max_tokens 200 → 350; `_parse_result()` extended; auto-D and name-dupe result dicts include empty strings for both fields
- `export.py`: `_record_to_row()` now maps `rec.leistung_absatz_2` → "Leistung Absatz 2", `rec.mehrwerte` → "Mehrwerte"
- `dashboard.py`: `_WRITEBACK_FIELDS` extended with `leistung_absatz_2`, `mehrwerte`, `gesellschafter_name`
- `tests/test_m17b.py`: 11 new tests (schema migration, PATCH endpoints, export mapping)

**Frontend agent (dashboard.html):**

```
python pipeline.py dashboard --dry-run
→ 5,362,012 chars (> 5MB, no error)
```

Changes delivered:
- CSS: `.panel-tabs`, `.panel-tab-btn`, `.panel-tab-content` tab styles; `.collapsible-header`, `.collapsible-body` collapsible styles
- `buildPanelLeft()`: rewritten to render two-tab shell (Overview + Letter Prep)
- New `buildOverviewTab()`: read-only company card (name, klass/SSB badges, domain link, MA/Revenue/Owner Age, city, GF, reasoning, K1/K2, HubSpot link)
- `buildWriteBack()`: redesigned into Letter Prep tab — Address Block (GF Name, Gesellschafter, Anrede, Salutation + Generate button, Street/PLZ read-only, Region, Region Prep) → Letter Body (Leistung 1, Leistung 2 new, Mehrwerte new, K1, K2) → Contact → Outreach (collapsed) → Classification → Approval
- `saveWriteback()`: `leistung_absatz_2`, `mehrwerte`, `gesellschafter_name` added to payload
- `completenessHtml()`: 6 fields now (Salutation added), threshold updated to `/6 fields`
- `prepCompletenessPct()`: denominator updated to 7 (6 fields + approved)
- `renderPrepKPIs()` + `renderBlockers()`: ready-count filter includes `r.salutation`
- `openPanel()`: region_prep auto-fills from REGION_MAPPING on open if empty
- New JS functions: `switchPanelTab()`, `toggleCollapsible()`, `autoSalutation()`

Deviations from plan:
- None. All spec items delivered as written.

---

## M17 Post-Delivery Fix: Letter Preview & Form Audit (2026-03-30)

**Trigger**: User review identified 8 issues in letter preview, form labels, and completeness gate.

### Fixes applied (all in `dashboard.html`)

| # | Issue | Fix |
|---|---|---|
| 1 | "Leistung Absatz 1" label misleading — not a standalone letter field | Renamed to "Leistung (Kurzform)" with placeholder "Medizinprodukt-Händlern" |
| 2 | English field labels in German-language Letter Prep form | Renamed: GF Name→GF-Name, Salutation→Anrede (Briefform), Street Address→Straße, GF Email→GF-E-Mail |
| 3 | Region / Region Prep dual inputs had unclear English labels | Renamed: "Region (display name)"→"Region" + hint "Anzeigename", "Region Prep (letter form)"→"Region (Briefform)" |
| 4 | Letter preview showed internal underscore codes (Name_Briefkopf, First_Name_1, etc.) as missing-field labels | Replaced all with German labels: Name Briefkopf, Vorname, Nachname, Straße, PLZ + Stadt, Leistung, Name, Kompliment 1/2 |
| 5 | `leistung_absatz_2` + `mehrwerte` shown as grey template text despite now being DB fields | Switched from `ft()` to `mf()` — now render as yellow (filled) or red (missing) merge fields; removed stale "not yet a per-record DB field" comments |
| 6 | Action Queue showed "Region" twice (RUN NOW + MANUAL REVIEW) | Removed duplicate "A/B missing region" line from MANUAL REVIEW section |
| 7 | Completeness gate missing `leistung_text` | Added to `completenessHtml()`, `prepCompletenessPct()`, `renderPrepKPIs()`, `renderBlockers()` — gate now 7 fields + approved (was 6+approved) |
| 8 | Completeness gate checked bare `region` instead of `region_prep` | Changed to `region_prep` in all gate functions — matches what the letter actually uses |

### Validation

```
python pipeline.py dashboard --dry-run → 5,362,033 chars (no error)
pytest tests/ -q → 207 passed in 6.60s (0 fail)
```
