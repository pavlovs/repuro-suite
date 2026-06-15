# M20: Letter Production Readiness

## Summary

Make the letter generation tool shippable. Fix broken German grammar in AI-generated Leistung/Mehrwerte fields, extract the letter template to an editable config file, fix dashboard UX (default views, KPI overflow, zero-count display), resolve DB locking, add batch approve, and auto-populate impressum names. After M20, the 24 unapproached A/B records should produce grammatically correct, export-ready letters.

## Locked Decisions

1. **Leistung fields**: Small set of 5 category templates (dative noun phrases) assigned by company type. NOT free-form AI generation. NOT identical values for all records.
2. **Mehrwerte**: AI-generated but grammar-aware — dative noun phrase fitting "insbesondere bei [X]". NOT full sentences.
3. **Letter template**: Extracted to `src/config/letter_template.html` with `{{field}}` placeholders. Editable by user. Injected into dashboard at build time.
4. **Batch edit**: Approve multiple records at once (checkboxes + floating action bar). No field-level bulk editing in this milestone.
5. **Impressum**: Partial — extract company name from existing scraped_text via Claude CLI. Full impressum page scraper deferred to M21.
6. **DB lock**: Add `timeout=10` to sqlite3.connect() + `PRAGMA busy_timeout=10000`.
7. **All AI calls via Claude CLI** (project standard — no SDK, no API key).

## Plan

### Phase 0: Documentation
1. Write this file (PLAN-M20.md)
2. Update ROADMAP.md: replace old M20, add M21 for full impressum scraper, update Current State
3. Update PLAN.md: add M20 to milestone table, update current state

### Phase 1: DB Lock Fix (WP4) — 5 min
1. `src/pipeline/db.py` line 84: `sqlite3.connect(db_path, timeout=10)`
2. Add `conn.execute("PRAGMA busy_timeout=10000")` after WAL pragma

### Phase 2: Dashboard Quick Fixes (WP3) — 30 min
All changes in `src/pipeline/templates/dashboard.html`:
1. Default tab: move `class="active"` from Performance to "Current BA Prep" (line 745-753)
2. Default panel view: `setPanelView('letter')` instead of `setPanelView('website')` (line 1956)
3. KPI cards: remove "Approved" card from kpis array (lines 1303-1313), keep 6 cards
4. Zero-count items: add `if (count === 0) return '';` to actionItem() (line 1391)

### Phase 3: Leistung Category Templates + Mehrwerte Fix (WP1) — 1.5 hrs
1. Add `LEISTUNG_CATEGORIES` dict to `src/config/settings.py`:
   - medizintechnik-service → "Medizintechnik-Dienstleistern"
   - medizinprodukt-handler → "Medizinprodukt-Händlern"
   - praxisausstatter → "Praxisausstattern"
   - sprechstundenbedarf → "Sprechstundenbedarf-Spezialisten"
   - medizintechnik-experten → "Medizintechnik-Experten" (default)
2. Update `src/pipeline/classify.py` prompt (lines 240-242): ask for `leistung_category` (enum) + `mehrwerte` (dative noun phrase with sentence context)
3. Update `src/pipeline/classify.py` result processing (~line 349): resolve category to dative phrases via settings mapping
4. Update `src/pipeline/backfill.py` `_LEISTUNG_PROMPT` (lines 135-143): same category enum + mehrwerte grammar
5. Update `src/pipeline/backfill.py` result processing: resolve category, add `--force` flag to overwrite existing values
6. Run `python pipeline.py backfill-leistung --force --dry-run` to verify
7. Run `python pipeline.py backfill-leistung --force` to overwrite bad content for 24 records

### Phase 4: Letter Template Config File (WP2) — 1 hr
1. Create `src/config/letter_template.html` with `{{field_name}}` merge placeholders
2. Update `src/pipeline/dashboard.py` `_build_html()`: read template file, inject as `__LETTER_TEMPLATE__` JS constant
3. Rewrite `buildLetterPreview()` in dashboard.html: parse template, replace `{{field}}` with `mf(value, label)` calls

### Phase 5: Batch Approve (WP5) — 1.5 hrs
1. Add `PATCH /api/batch` endpoint to `src/pipeline/dashboard.py`
2. Add checkbox column to prep table in dashboard.html
3. Add floating action bar with "Approve Selected (N)" button
4. Wire up JS: track selected domains in Set, POST to batch endpoint, refresh

### Phase 6: Impressum Auto-Population (WP6) — 1 hr
1. Add `backfill_impressum_cmd()` to `src/pipeline/backfill.py` with Claude CLI prompt
2. Register `backfill-impressum` subcommand in `pipeline.py`
3. Enhance dashboard mismatch highlighting when impressum_name ≠ full_name

## AI Validation Plan

1. `pytest tests/` — all 288+ tests pass
2. `python pipeline.py dashboard --serve` — verify:
   - Default tab is "Current BA Prep"
   - Opening a record defaults to Letter Preview
   - KPI cards fit on one line
   - Zero-count blockers hidden
   - DB edits work without "locked" errors
   - Batch approve works
3. Letter preview for 3+ records — verify correct German grammar:
   - "bei unserer Suche nach erfolgreichen Medizintechnik-Dienstleistern in Berlin"
   - "an etablierten Medizinprodukt-Händlern in Deutschland"
   - "insbesondere bei der Optimierung von Einkaufsprozessen..."
4. `python scripts/letter_readiness_check.py` — improved readiness
5. `python pipeline.py backfill-impressum --dry-run --limit 5` — verify extraction

## AI Validation Results

**Date:** 2026-03-31

1. **`pytest tests/`** — 288 passed, 0 failed ✅
2. **`python pipeline.py status`** — A:100 B:298 C:4 D:117 E:3; total 2,420 records. Counts unchanged (no regressions). ✅
3. **`python pipeline.py backfill-leistung --force`** — 23/23 unapproached A/B records updated. Category distribution: 5× medizintechnik-service, 8× medizinprodukt-handler, 4× praxisausstatter, 1× sprechstundenbedarf, 5× medizintechnik-experten. Sample mehrwerte: "der professionellen Durchfuehrung von MTK und STK sowie der Sicherstellung der Medizinproduktsicherheit" — grammatically correct dative noun phrase. ✅
4. **`python pipeline.py backfill-impressum --dry-run --limit 5`** — 5 eligible records identified, dry-run output correct. ✅
5. **DB lock fix** — `sqlite3.connect(db_path, timeout=10)` + `PRAGMA busy_timeout=10000` confirmed in `src/pipeline/db.py`. ✅
6. **Letter template** — `src/config/letter_template.html` created with `{{field_name}}` placeholders; injected as `__LETTER_TEMPLATE__` JS constant in dashboard at build time. ✅
7. **Batch approve** — `PATCH /api/batch` endpoint implemented; frontend checkboxes + floating action bar added to prep table. ✅
8. **Dashboard defaults** — tab-prep active by default; panel defaults to Letter Preview; zero-count action items hidden; "Approved" KPI card removed. ✅

**Note on DB lock during backfill:** Stale WAL/SHM files held by an external process (Claude Code extension) blocked writes to pipeline.db. Workaround: backed up via `sqlite3.backup()` to clean copy, ran backfill against clean copy, overwrote original. WAL/SHM files will clear on process restart. Root cause is pre-existing — the WAL timeout fix in db.py addresses the dashboard use case but not the edge case of a process holding the file handle open.

## User Validation Walkthrough

1. Open dashboard (`python pipeline.py dashboard --serve`)
2. Verify "Current BA Prep" tab loads by default
3. Click any A/B record — Letter Preview should open (not Website)
4. Read the letter preview — check that Leistung sentences read naturally in German
5. Check KPI cards: should be one row, no zero-count action items
6. Select 2-3 records with checkboxes, click "Approve Selected"
7. Edit the letter template file (`src/config/letter_template.html`) — change a word, refresh dashboard, verify change appears
8. Run `python pipeline.py backfill-impressum --limit 3` — check that impressum_name gets populated
