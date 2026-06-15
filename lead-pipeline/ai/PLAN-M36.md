# M36 — Category Refactor & BA9 Briefvorbereitung Defaults

**Status:** Planned
**Source:** FF Category Ticket (260515_ALLEX_Category_Ticket.md), UI-ISSUES.md Prio 1 items
**Supersedes:** M34 sections 4+5 (Mehrwerte/Leistung defaults — now category-driven, not generic)

---

## Goal

Replace A/B/C/D/E/S classification with functional business-type categories (DEA, INT, SER_PLA_1, SER_PLA_2, SER_MAI, SER_ITS + non-target codes). Formalize the existing `prio` field as a DB column for queue filtering — it already exists in the UI (dashboard_v2.html line 2306) and PATCHABLE_FIELDS. Auto-fill Leistung 1/2, Mehrwerte, Gruppe 1/2 deterministically from category on Briefvorbereitung entry.

## Design Decisions

1. **Keep `klass` column** — new valid values: DEA, INT, SER_PLA_1, SER_PLA_2, SER_MAI, SER_ITS, OEM, HEC, OOS, OTH, B2C, N/A (+ legacy A/B/C/D/E/S for unmigrated BA1-8 records). Column name unchanged — avoids renaming 100+ references.
2. **Formalize existing `prio` field as a DB column** — already exists in UI (dashboard_v2.html line 2306) with values: 'Prio 1', 'Prio 2 (small)', 'Prio 2 (big)', 'Prio 2 (intl)', 'Prio 2 (other)', 'Duplicate'. Add 'Excluded' for ownership gate. Add `prio` to `_OUTREACH_COLUMNS` in db.py so `_migrate_schema()` creates the column.
3. **Category does NOT gate queue access.** Any category can be Prio 1 if manually set. Non-target categories default to 'Prio 2 (other)' on ingest.
4. **Ownership gate** writes `prio = 'Excluded'` instead of `klass = 'S'`. Category stays unchanged.
5. **BA9 data ingested pre-classified** from Flo's xlsx. No classify.py changes this milestone.
6. **BA1-8 keeps old A/B/C/D/E/S values** — no reclassification. Backend handles both old and new values.
7. **Backfill `prio` for existing records**: A/B → 'Prio 1', C → 'Prio 2 (other)', D/E → 'Prio 2 (other)', S → 'Excluded', NULL → NULL.

---

## Category Mapping — Briefvorbereitung Defaults

| Category  | Leistung 1                                 | Leistung 2                                            | Mehrwerte                                                                                      |
|-----------|--------------------------------------------|-------------------------------------------------------|------------------------------------------------------------------------------------------------|
| DEA       | Experten für Medizinprodukte               | Unternehmen im Bereich Medizintechnik und -produkte   | neuen Wachstumsinitiativen, bei der Digitalisierung und im Einkauf durch Volumenbündelung      |
| INT       | Medizintechnik-Experten                    | Unternehmen im Bereich Medizintechnik und -produkte   | neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und im Einkauf                 |
| SER_PLA_1 | Spezialisten für Praxis- und Klinikplanung | Unternehmen im Gesundheitswesen                       | neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Fachkräftemangel      |
| SER_PLA_2 | Medizintechnik-Experten                    | Experten für Medizintechnik und -ausstattung          | neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Qualitätsmanagement   |
| SER_MAI   | Medizintechnik-Experten                    | Medizintechnik-Dienstleistern                         | neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Qualitätsmanagement   |
| SER_ITS   | IT-Experten im Gesundheitswesen            | Medizintechnik- und IT-Experten im Gesundheitswesen   | neuen Wachstumsinitiativen, der Digitalisierung mit KI-Lösungen und beim Fachkräftemangel      |

Gruppe 1 (all categories): "Handels- und Servicespezialisten"
Gruppe 2 (all categories): "Komplettangebot mit deutschlandweitem Service-Netzwerk aus einer Hand"

Gesellschafter: derived from Anrede — Herr → "Gesellschafter", Frau → "Gesellschafterin"

---

## Scope

**In:**
- DB: add `prio`, `gruppe_1`, `gruppe_2`, `gesellschafter_field` columns via `_OUTREACH_COLUMNS`
- DB: backfill `prio` from existing klass values (A/B → 'Prio 1', C/D/E → 'Prio 2 (other)', S → 'Excluded')
- DB: expand valid klass values to new category codes
- Backend: replace all `klass IN ('A','B')` filters with `prio = 'Prio 1'`
- Backend: replace all `klass = 'S'` logic with `prio = 'Excluded'`
- UI: new category pills, prio selector (using existing prio UI field), Gesellschafter field, Gruppe 1/2 fields
- Briefvorbereitung: deterministic default fill from category mapping (Leistung 1/2, Mehrwerte, Gruppe 1/2)
- Letter template: wire Gruppe 1/2 + Gesellschafter into letter merge
- Backwards compat: BA1-8 keeps old A/B/C/D/E/S values, must still work

**Out:**
- classify.py prompt changes (future milestone)
- M34 K1/K2 compliment logic (remains valid, independent)
- About-page discovery (M34 T3, independent)
- BA1-8 reclassification — no migration of old records to new category codes

---

## Tasks

### T1: Schema + Prio Backfill

Add columns to `_OUTREACH_COLUMNS` in db.py:
- `prio TEXT`
- `gruppe_1 TEXT`
- `gruppe_2 TEXT`
- `gesellschafter_field TEXT`

`_migrate_schema()` handles column creation automatically.

Backfill script (run once at end of migration):
```sql
UPDATE company_records SET prio = 'Prio 1' WHERE klass IN ('A', 'B') AND prio IS NULL;
UPDATE company_records SET prio = 'Prio 2 (other)' WHERE klass IN ('C', 'D', 'E') AND prio IS NULL;
UPDATE company_records SET prio = 'Excluded' WHERE klass = 'S' AND prio IS NULL;
```

No rename of `klass` column. Valid values expand from A/B/C/D/E/S to: DEA, INT, SER_PLA_1, SER_PLA_2, SER_MAI, SER_ITS, OEM, HEC, OOS, OTH, B2C, N/A (+ legacy A/B/C/D/E/S for unmigrated records).

### T2: Backend Filter Refactor

Replace all query patterns:

| Old pattern | New pattern | Files |
|---|---|---|
| `klass IN ('A','B')` | `prio = 'Prio 1'` | backfill.py (6), enrich.py (2), normalize.py (3), check_letter.py (1), export.py (3), dashboard.py (6), db.py (2) |
| `klass = 'S'` / `klass='S'` | `prio = 'Excluded'` | db.py (1), dashboard.py (2) |
| `r.klass in ("A","B")` (Python) | `r.prio == 'Prio 1'` | export.py (2) |
| `r["klass"] == "S"` (Python) | `r.get("prio") == 'Excluded'` | dashboard.py (1) |
| JS `r.klass === 'A' \|\| r.klass === 'B'` | `r.prio === 'Prio 1'` | dashboard_v2.html (multiple) |
| JS `r.klass === 'S'` | `r.prio === 'Excluded'` | dashboard_v2.html (multiple) |

### T3: Category Defaults Engine

New file: `src/pipeline/category_defaults.py`

```python
CATEGORY_DEFAULTS = {
    "DEA": {"leistung_text": "...", "leistung_absatz_2": "...", "mehrwerte": "...", "gruppe_1": "...", "gruppe_2": "..."},
    "INT": {...},
    ...
}

def apply_category_defaults(record, category):
    """Fill Leistung 1/2, Mehrwerte, Gruppe 1/2 from category if empty."""
```

Called during:
- Ingest (when category is known from xlsx)
- Briefvorbereitung entry (dashboard PATCH that starts brief prep)

Replaces: `settings.LEISTUNG_CATEGORIES` mapping + AI-generated mehrwerte for new records.

### T4: Gesellschafter Field

- Derive default from Anrede: "Herr" → "Gesellschafter", "Frau" → "Gesellschafterin"
- Add to Stammdaten section in UI (per FF request: move Ansprechpartner/Anrede/Salutation there too)
- Wire into letter template merge
- Add to PATCHABLE_FIELDS in dashboard.py

### T5: UI — Templates Refactor

**dashboard_v2.html** (primary):
- Replace klass pill options: `['A','B','C','D','E']` → `['DEA','INT','SER_PLA_1','SER_PLA_2','SER_MAI','SER_ITS','OEM','HEC','OOS','OTH','B2C']`
- Prio selector already exists (line 2306) — update allowed values to include 'Excluded'
- Add Gruppe 1, Gruppe 2, Gesellschafter fields to detail view
- Update queue filter: use `prio` not `klass` for show/hide
- Update funnel rendering: stages reference prio-based logic
- Update Lead-Liste: klass select dropdown → new category options
- CSS: new color scheme for category pills (6 target + 5 non-target + N/A)

**dashboard.html + dashboard_v1.html** — mark as DEPRECATED. Same changes as v2 IF still served, otherwise skip with deprecation notice.

### T6: BA9 Ingest

- Read Flo's xlsx (`260518_Repuro_Medtech_Targets_v5.xlsx`, tab `Serienbriefe`, column F)
- Map column F values to `klass` field (new category codes)
- Set `prio` based on target/non-target category (target → 'Prio 1', non-target → 'Prio 2 (other)')
- Apply category defaults (T3) during ingest
- Standard BA9 ingest flow (same pattern as BA8)

---

## Exhaustive Refactoring Checklist

### Python files — klass references

**src/config/settings.py**
- Line 24: comment `# CRITICAL: Only call for klass A or B...` → update comment to reference `prio = 'Prio 1'`

**src/config/profile.py**
- Line 39: `klass: str` → keep (column name unchanged)

**src/pipeline/models.py**
- Line 36: `klass: Optional[str] = None` → keep (column name unchanged)
- ADD: `prio: Optional[str] = None`
- ADD: `gruppe_1: Optional[str] = None`
- ADD: `gruppe_2: Optional[str] = None`
- ADD: `gesellschafter_field: Optional[str] = None`

**src/pipeline/db.py**
- Line 45: `klass TEXT` → keep (column stays)
- ADD to `_OUTREACH_COLUMNS`: `prio`, `gruppe_1`, `gruppe_2`, `gesellschafter_field`
- Line 364-368: `get_klass_counts()` → rename to `get_category_counts()`, keep query logic (GROUP BY klass)
- Line 423: `klass = COALESCE(klass, :klass)` → keep (upsert logic unchanged)
- Line 450-456: INSERT column list includes klass → keep
- Line 469-474: SELECT includes klass → keep
- Line 574-601: `update_classify_result()` → keep (classify.py out of scope, still writes A/B/C/D/E)
- Line 619-634: classify stats → keep (still counts klass values)
- Line 645: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 730-736: ownership gate sets `klass='S'` → change to `prio='Excluded'`, keep klass unchanged
- Line 853: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 858: `klass IN ('A','B')` → `prio = 'Prio 1'`

**src/pipeline/dashboard.py**
- Line 50: `"klass"` in column list → keep
- ADD `"prio"` to column list if not present
- Line 86: `"prio"` in PATCHABLE_FIELDS → keep (already there)
- Line 145: `r["klass"] is not None` → keep (classified = has klass)
- Line 146: `r["klass"] is None` → keep
- Line 147: `r["klass"] in ("D", "E")` → keep for legacy funnel (after backfill, prio handles filtering)
- Line 148: `r["klass"] in ("A","B","C","S")` → replace with `r.get("prio") in ('Prio 1', 'Excluded')`
- Line 153-155: funnel counts → keep labels, update logic to use prio
- Line 164: `r["klass"] == "S"` → `r.get("prio") == 'Excluded'`
- Line 165: `r["klass"] in ("A","B","C")` → `r.get("prio") not in ('Excluded', None) and r["klass"] not in ("D","E")`
- Line 180: `r["klass"] in ("A","B")` → `r.get("prio") == 'Prio 1'`
- Line 264: `klass IS NOT NULL` → keep (classified check)
- Line 274-281: klass GROUP BY → keep (for category distribution chart)
- Line 290: `klass_counts.get(k, 0)` → keep
- Line 304: `klass = 'D'` → keep (D-count for funnel)
- Line 326: `klass = ?` → keep (per-source klass breakdown)
- Line 344: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 350: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 368: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 374: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 407: SELECT includes klass → keep (add prio to SELECT)
- Line 430: `klass_counts` → keep key name
- Line 748: `("Klass", "klass")` → keep (export column)
- Line 749: `("Priorität", "prio")` → keep
- Line 1327: `klass_counts: {}` → keep
- Line 1341-1347: klass_summary display → keep

**src/pipeline/backfill.py**
- Line 62: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 297: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 306: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 460: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 470: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 595: `klass = 'A' OR klass = 'B'` → `prio = 'Prio 1'`

**src/pipeline/enrich.py**
- Line 46: comment about klass A/B → update to reference `prio = 'Prio 1'`
- Line 1906: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 2279: `klass IN ('A','B')` → `prio = 'Prio 1'`

**src/pipeline/normalize.py**
- Line 768: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 1070: `klass IN ('A','B')` → `prio = 'Prio 1'`
- Line 1141: `klass IN ('A','B')` → `prio = 'Prio 1'`

**src/pipeline/export.py**
- Line 31: `"Category",  # 2  klass` → keep (klass now holds category code)
- Line 261: `r.klass in ("A","B")` → `r.prio == 'Prio 1'`
- Line 299: `rec.klass in ("A","B")` → `rec.prio == 'Prio 1'`
- Line 305: `"Category": rec.klass or ""` → keep (klass = category)
- Line 359: `klass IN ('A','B','C','E')` → `klass IS NOT NULL AND prio != 'Excluded'`
- Line 364: `CASE klass WHEN 'A' THEN 1...` → sort by `prio` then `klass` (Prio 1 first, then alphabetical category)
- Line 380: comment about klass=D/S → update to reference `prio='Excluded'`

**src/pipeline/check_letter.py**
- Line 221: `klass IN ('A','B')` → `prio = 'Prio 1'`

**src/pipeline/ingest.py**
- Line 566: `"klass": _s(row[_C_KLASS])` → keep for serienbriefe parsing, must accept new category codes
- Line 662-663: comments about klass='B' → update comments
- Line 691-692: `klass_new` from xlsx → accept new category codes, not just "Distributor" check
- Line 711: `"klass": "B"` → set to proper category from xlsx column F
- Line 747: `klass = 'B'` → set to proper category from xlsx
- Line 766-769: INSERT includes klass → keep, add prio to INSERT

**src/pipeline/audit.py**
- Line 29: comment mentions klass → keep
- Line 99: `"klass": rec.get("klass") or ""` → keep
- Line 116: `"klass"` in column list → keep

**classify.py** — OUT OF SCOPE, do not touch

### HTML/JS templates — klass references

**dashboard_v2.html** (PRIMARY — all changes go here first):

CSS changes:
- Lines 690-695: `.lt-klass` styles for A/B/C/D/E/S → add styles for new category codes (DEA, INT, SER_PLA_1, etc.)
- Lines 918-930: `.klass-pill` and `.prio-pill` styles → update klass-pill active styles for new codes

JS logic changes:
- Line 1585: `r.klass === 'A' || r.klass === 'B'` → `r.prio === 'Prio 1'`
- Line 2116: `r.klass === 'S'` → `r.prio === 'Excluded'`
- Lines 2311-2313: klass-pills `['A','B','C','D','E']` → `['DEA','INT','SER_PLA_1','SER_PLA_2','SER_MAI','SER_ITS','OEM','HEC','OOS','OTH','B2C']`
- Line 2692: save fields list includes klass+prio → keep, add gruppe_1, gruppe_2, gesellschafter_field
- Lines 2762-2770: klass-pill click handler → update to use new category codes
- Lines 2870, 2881: ownership exclusion sets `klass='S'` → change to `prio='Excluded'`, keep klass unchanged
- Line 2903: reclassify to E → keep klass='E' for legacy, but also set `prio='Prio 2 (other)'`
- Lines 3222-3252: Lead-Liste klass column + select dropdown → update options to new category codes
- Lines 3345-3346: klass select change handler → keep (patches klass field)
- Lines 3443-3451: funnel logic using klass values → rewrite to use prio for queue filtering
- Lines 3454, 3465-3469: batch filtering `klass === 'A' || klass === 'B'` and `prio !== 'Duplicate'` → `r.prio === 'Prio 1'`
- Line 3655: `klass: r.klass` in export → keep
- Line 3714: klass badge display → update CSS classes for new codes
- Lines 4028-4029: overview funnel klass counts → update to use prio for A/B equivalent
- Lines 4121-4132: klass distribution chart → update labels for new codes
- Line 4150: "klassifizierte Records" label → keep or rename to "kategorisierte Records"
- Line 4159: `r.klass === 'A' || r.klass === 'B'` → `r.prio === 'Prio 1'`

**dashboard.html + dashboard_v1.html** — DEPRECATED:
- ~72 klass references each, nearly identical to each other
- Do NOT have prio pills at all
- Decision: mark deprecated with comment banner. Apply same changes ONLY if still served via dashboard.py routes. Otherwise skip.

---

## Execution Order

```
Phase 1: T1 — Schema + backfill prio
  - Add prio, gruppe_1, gruppe_2, gesellschafter_field to _OUTREACH_COLUMNS
  - _migrate_schema() creates columns automatically
  - Backfill prio from klass: A/B→'Prio 1', C/D/E→'Prio 2 (other)', S→'Excluded'

Phase 2 (parallel, after Phase 1):
  - T2: Backend filter refactor — all klass IN ('A','B') → prio = 'Prio 1' across Python files
  - T3: Category defaults engine — new function/file for deterministic Leistung/Mehrwerte fill
  - T4: Gesellschafter field — derive from Anrede, add to UI

Phase 3 (after T2):
  - T5: UI templates — update dashboard_v2.html klass pills, prio logic, funnel, Lead-Liste

Phase 4 (after T3):
  - T6: BA9 ingest — read xlsx, map category codes, set prio defaults, apply category defaults
```

---

## Review Agent — CRITICAL EMPHASIS

The `/review-milestone` agent MUST put **heavy emphasis** on the following during review:

1. **SQL query completeness** — every `klass IN ('A','B')` pattern across all .py files must be converted to `prio = 'Prio 1'`. A single missed query means records silently drop out of enrichment/export. Grep for `klass.*IN.*'A'` across all .py files and verify ZERO legacy filter patterns remain (except in classify.py which is out of scope).

2. **JavaScript filter logic** — the templates have ~80 JS references to klass values. Every `r.klass === 'A'`, `'ABCS'.indexOf(r.klass)`, and hardcoded array `['A','B','C','D','E','S']` must be updated. A missed JS filter means the queue or funnel renders incorrectly.

3. **Template consistency** — three templates exist (dashboard.html, dashboard_v1.html, dashboard_v2.html). All three must be updated consistently or deprecated with banner. Partial updates = one view works, another breaks.

4. **Ownership gate path** — verify the full flow: ownership check → set `prio='Excluded'` (NOT klass='S') → UI renders correctly → "Revert to Prio 1" button works → record re-enters queue. Category must remain unchanged throughout.

5. **Export integrity** — Serienbrief export, Lead-Liste export, Briefmarken export all reference klass for filtering and column output. Verify exports produce correct records with new prio-based logic.

6. **Backwards compatibility** — existing records with old A/B/C/D/E/S klass values must still render and be queryable. After backfill, `prio` is the authoritative queue filter. The `klass` field for old records is display-only (shows legacy letter grade). New records get proper category codes in klass.

---

## Acceptance Criteria

1. All BA9 records ingested with correct category codes in `klass` from xlsx
2. `prio` column exists and backfilled for all existing records (A/B → 'Prio 1', C/D/E → 'Prio 2 (other)', S → 'Excluded')
3. Briefvorbereitung auto-fills Leistung 1/2, Mehrwerte, Gruppe 1/2 based on category
4. Gesellschafter field visible and gendered from Anrede
5. Queue shows records based on `prio`, not category/klass
6. Ownership exclusion writes `prio='Excluded'`, preserves klass/category unchanged
7. Funnel/stats render correctly with new categories
8. All exports produce correct output with prio-based filtering
9. Zero Python files contain `klass IN ('A','B')` filter pattern (except classify.py)
10. Zero JS files contain hardcoded `['A','B','C','D','E','S']` arrays for queue logic
11. BA1-8 records with old A/B/C/D/E/S klass values still render and filter correctly via their backfilled prio

## Dependencies

- Flo's xlsx must be accessible on shared OneDrive (currently on his personal path)
- M34 K1/K2 logic remains independent — no conflict
- classify.py untouched — future milestone will align prompt with new codes
- T1 backfill must run before T2 filter changes go live (otherwise records with prio=NULL drop out of queue)

## Resolved Questions

- xlsx location: `260518_Repuro_Medtech_Targets_v5.xlsx` in lead-pipeline folder (shared OneDrive)
- Gesellschafter gender: Herr → "Gesellschafter", Frau → "Gesellschafterin" (from Anrede field) — confirmed
- `prio` vs `prioritaet`: use `prio` — field already exists in UI and PATCHABLE_FIELDS (dashboard_v2.html line 2306, dashboard.py line 86). No new column name needed.
- Prio values: 'Prio 1', 'Prio 2 (small)', 'Prio 2 (big)', 'Prio 2 (intl)', 'Prio 2 (other)', 'Duplicate', 'Excluded' — matches existing UI dropdown options plus new Excluded value.
- Legacy A/B/C/D/E/S: kept in klass column indefinitely. No reclassification. Prio backfill handles queue logic.
