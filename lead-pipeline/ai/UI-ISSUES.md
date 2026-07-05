# UI Issues — Quick Capture

Drop issues here while looking at the dashboard. Format: `- [ ] description` or just free text.
Claude reads this at the start of any dashboard/dev session and converts open items into tasks.

---
## FF Issues — add new issues below this line

Bug-fixes
- [ ] Website preview does not load: Habys GmbH, wibu.care, Pielmeier Medizintechnik GmbH, Grosspietsch GmbH, CB-MED Planung GmbH
- [ ] Brief-Vorschau: Updates of Geschäftsführer and Name Absatz 1 and Name Absatz 3 in preview of Brief-Vorschau to be updated automatically
- [ ] Dermacom GmbH: Region "Franken" is wrong. Heilbronn is in Baden-Württemberg. Please double check the regions.
- [ ] EHP Hygieneprodukte GmbH: Draft of Straße is also including name of one of the managing directors (also happened with other companies)
- [ ] Reinert & Bläsius: Draft of Straße is also including website adress "reinert-blaesius.de"

Features
- [x] Prio 1: Please add a new field called "Gesellschafter" in the section "Stammdaten" to customize "Gesellschafter" - this should be done by default depending on the gender of Ansprechpartner (Brief) (Gesellschafter or Gesellschafterin depending on the gender of the owner) → **resolved 2026-05-27**: gesellschafter_field added as editable field in Briefvorbereitung; derives from anrede via enrich; reflected in letter template as {{gesellschafter_field}}
- [x] Prio 1: Please add a new field called "Gruppe 1" that allows to customize this section in the current letter draft "Handels- und Servicespezialisten" → **resolved 2026-05-27**: gruppe_1 field added, editable in Briefvorbereitung, reflected in letter template as {{gruppe_1}}, defaults set per category
- [x] Prio 1: Please add a new field called "Gruppe 2" that allows to customize this section in the current letter draft "Komplettangebot mit deutschlandweitem Service-Netzwerk aus einer Hand" → **resolved 2026-05-27**: gruppe_2 field added, editable in Briefvorbereitung, reflected in letter template as {{gruppe_2}}, defaults set per category
- [x] Prio 1: Please implement the new categories as described in: [260515_ALLEX_Category_Ticket.md](https://kamucapital.sharepoint.com/:t:/s/KamuKapital/IQD1gLIaVikpR7NkJAtIA5joAaaZ9p1c6ouM4AirlD5KIC0?e=iilRHw). → **resolved 2026-05-27**: new klass codes (DEA, INT, SER_PLA_1, SER_PLA_2, SER_MAI, SER_ITS) implemented with category_defaults.py; per-category defaults for Leistung 1/2, Mehrwerte, Gruppe 1/2
- [x] Overview about whole batch with each company and current status of Gesellschaft, Stammdaten and Brief. → **resolved 2026-05-27**: Batch-Übersicht tab added with GS/SD/Brief status columns, gap filter, summary stats, click-to-review
- [ ] Website: Preview automatically Impressum (instead of landing page)
- [ ] Briefvorbereitung: Please move Ansprechpartner (Brief), Anrede and Salutation to "Stammdaten"
- [ ] For reference: You can find all classifier context in this folder: @C:\Users\flori\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital\CLAUDE_REPURO\classifier.
- [x] Kategorie: Please categorize every company in the Batch section by default to "Prio 1". Once we change the Priorität to "Prio 2" or "Duplicate" it should automaticelly disappear in the Batch section and be stored in the database → **resolved 2026-05-27**: Prio 2 records hidden from Review queue (already) + Lead-Liste (new toggle "Prio 2 anzeigen", off by default). Prio 2 records remain in DB, visible when filter toggled on.
- [x] Briefvorbereitung Kompliment-Logik + Defaults → **M34 delivered** (incrementally across M16–M32; verified 2026-06-29). Prompt cascade, about-page scraping, category defaults, compliment_guide.md updated with Flo's verbatim cascade.

---

## RD ISSUES — add new issues below this line

Bug-fixes
- [x] **GESELLSCHAFTER lookup bug — root cause found + fixed** (2026-05-11). `_name_matches_query()` only checked FIRST WORD of company name → "alpha" matched wrong Alpha company, "primus" matched wrong Primus, etc. 0/71 BA8 records had HRB cross-check. Fix: (1) match ALL significant words, (2) extract HRB from impressum BEFORE autocomplete calls. Commit `c870164`. 3 records manually corrected by Roman. 9 high-risk re-verified — all correct.

v2.0.4
- [ ] **Enrich logic upgrade** — deploy `c870164` (multi-word `_name_matches_query` + HRB-first waterfall). Then re-enrich all BA8 records without HRB to backfill `hrb_number` from impressum and re-validate existing matches against stricter logic. Scope: `enrich.py` already committed on `dev`; needs deploy + batch re-enrich run.

Pipeline bugs (BA9 retro — prevent recurrence in BA10)
- [ ] **🔴 ROOT CAUSE — MANUAL/dashboard records never get an Impressum-first enrichment pass.** Almost every BA9 gap (missing company name, 0/23 HRB, missing gesellschafter, missing street/PLZ, missing GF) traces to ONE thing: for MANUAL-source / dashboard-added records the Impressum is never reliably fetched, stored, and mined. The German Impressum legally carries the **legal name, HRB+Amtsgericht, GF, and address** — every field we're missing. Proposed hardened flow (new milestone, run BEFORE enrich for any MANUAL cohort): (1) fetch Impressum (homepage→/impressum + /kontakt + sitemap fallback — reuse `rescrape_ba9_addresses.py` link-discovery), store in `knowledge_base.db`; (2) extract **legal name** (line ending in GmbH/AG/KG/e.K./UG) → overwrite `full_name` when current value == domain/brand; (3) extract **HRB + Amtsgericht** → enables exact OpenRegister lookup (no fuzzy name match); (4) extract GF + address. Then `enrich` runs with real inputs. This single upstream step lifts name, gesellschafter, street, AND gf together. Without it **BA10 will reproduce every BA9 gap.** Scope: new `scrape-impressum`/`prepare-manual` stage + `ingest.py`.
- [ ] **GmbH & Co. KG ownership — resolve the top level (Komplementär chain).** 4 BA9 KGs (Mefina Medical, Schupp, iQ-medtec + 1) got no gesellschafter. A GmbH & Co. KG always bottoms out at natural persons: OpenRegister `/owners` on the KG returns Kommanditisten (the capital owners, often the natural persons directly) + the Komplementär (a Verwaltungs-GmbH, ~0% capital). If the top owner is the Verwaltungs-GmbH, recurse into ITS Gesellschafter (the existing `_resolve_ubo` holding-recursion should fire here). Today these KGs fail at step 0 — not found because there's no HRB (see root-cause item). Fix: ensure KG → owners → Komplementär-GmbH → natural-person recursion; gate on HRB-first lookup. Scope: `enrich.py` `_resolve_ubo` / owners waterfall + KG detection.
- [x] **MANUAL import: full_name = domain** — **Fixed (2026-06-14):** new `prepare-manual` CLI command (`qa.py:prepare_manual_names`) scrapes impressum and extracts legal entity name for MANUAL-source records before enrichment. Run `python pipeline.py prepare-manual` after `ingest-manual` and before `enrich`.
- [x] **Scraped text truncated at 2500 chars** — **Fixed (2026-06-14):** `SCRAPE_MAX_CHARS` raised from 2500 to 5000 in `settings.py`. New scrapes will capture full impressum content.
- [ ] **_MALE_NAMES set incomplete** — 8 common German names were missing (dennis, fabian, ibrahim, lutz, marco, mathias, niklas, pascal), causing anrede=NULL for natural person owners. Fix: expand name set systematically — cross-check against a German first name frequency list. Added 8 names in this session but more will surface. Scope: `enrich.py` `_MALE_NAMES`.
- [x] **Impressum address not extracted for records without KB** — `normalize.py` step 9a only read from `knowledge_base.db`. MANUAL imports have no KB entries → addresses not extracted. **Fixed (2026-06-10):** added fallback chain in `normalize.py` step 9a: (1) KB impressum doc → (2) `impressum_address` column → (3) `scraped_text`. Recovered 10/16 missing BA9 addresses via live impressum fetch + impressum_address parsing. 6 domains remain unreachable (defi-esser.de, defistore.de, eye-concept.de, gmd-service.de, keller-medical.de, xcelsitas.com) — sites block scraping, timeout, or have no /impressum page; need Playwright/headless browser or manual entry.
- [x] **No Austrian/non-DE company filter** — **Fixed (2026-06-14):** `_detect_non_de_company()` in `enrich.py` checks TLD (.at/.ch/.nl/etc.) and PLZ digit count (4-digit = AT/CH). Non-DE companies get `ownership_reason='Non-DE company'`, skip OpenRegister, save API credits.
- [x] **OpenRegister autocomplete doesn't extract address** — **Fixed (2026-06-14):** `_openregister_autocomplete()` now caches `registered_address` from API response in `_autocomplete_address_cache`. New `openregister_address` DB column stores it via `update_ownership_result()`. Available for comparison against impressum address.
- [ ] **🔴 ingest-manual / dashboard-add leaves `pipeline_stage='scraped'`** — records added manually (incl. directly on the Fly dashboard) keep `pipeline_stage='scraped'` even after klass+prio are set. `get_records_for_enrich()` requires `stage='classified'`, so ownership/gesellschafter enrichment **silently skips them** (and the `owner_name`→`anrede` chain it feeds), while `prio`-gated backfills (leistung/compliments) still run → a half-enriched batch that looks fine until fill rates are inspected. This was the root cause of the BA9 "drift" (35 added records, gesellschafter 0/35 until stage was manually advanced). Fix: (1) `ingest-manual` + dashboard manual-add must set `pipeline_stage='classified'`; (2) add a batch-readiness check that flags any `briefaktion` cohort record still at `pipeline_stage='scraped'`. Scope: `ingest.py` / dashboard add-record handler + `check_letter.py`/batch-readiness.
- [ ] **🔴 Claude-CLI backfills fail under PowerShell/scheduled spawn (`WinError 2`)** — `backfill-compliments`, `backfill-leistung`, and normalize region-lookup call the Claude CLI via `settings.CLAUDE_CMD = shutil.which('claude')`. Under a `powershell -File` or scheduled-task spawn, `shutil.which('claude')` returns None (npm dir not on that PATH) → falls back to bare `claude` → every call dies `[WinError 2]` and the step silently fills 0 records (exit 0). The same commands work from **bash**. Fix: harden `CLAUDE_CMD` resolution to the npm global `claude.CMD`/`claude.cmd` path (check `%APPDATA%\npm`) instead of relying on PATH; until then, run all AI backfills from bash. Scope: `settings.py` CLAUDE_CMD resolution. (Note: a prior session wrongly concluded "Claude CLI can't run nested" — it can; this is purely PATH resolution.)
- [ ] **`parse_impressum_address` misses street when it's on the line before the PLSZ after a label/names** — e.g. multiclean.de impressum `"...sämtlich geschäftsansässig: General-Bishop-Straße 37, 32339 Espelkamp"` → parser extracted `plz_ort='32339 Espelkamp'` but `street=NULL`. The PLZ-anchor back-search doesn't reach past the `geschäftsansässig:`/names prefix to the street token. Result: records with plz_ort filled but street empty (BA9: 2 such — multiclean fixed manually, defistore impressum unreachable). Fix: widen the street back-search window and strip leading label/name fragments before the street token. Scope: `normalize.py` `parse_impressum_address()`.
- [x] **🔴 Editable company name + "Gesellschafter neu suchen" re-search action** — **Fixed (2026-06-14):** (a) `full_name` was already editable in Stammdaten ("Firmenname Briefkopf" input). (b) "↻ Gesellschafter neu suchen" button now always visible in Gesellschafter section (not just in review mode). Uses existing `re_enrich_single_domain` API endpoint which reads updated `full_name` from DB.
- [ ] **gruppe_1/gruppe_2 + gesellschafter_field not applied to dashboard-added records** — these come from `apply_category_defaults()` (constants per target category) at ingest. Records added directly on the dashboard skip it → gruppe_1/2 empty for all 35 BA9 manual adds (fixed this session by re-running defaults). Fix: dashboard manual-add must call `apply_category_defaults` + `get_gesellschafter_field`. Scope: dashboard add-record handler.
- [ ] **`_MALE_NAMES` gap drops anrede for valid male owners** — consonant-ending / non-German first names not in the list and not matching the a/e/i vowel heuristic → `anrede=NULL` → cascades to salutation + gesellschafter_field + the "Briefform" status all empty. BA9 hits: Marius (Duda), Imad (Kafi), Heinz (Wellmann), Angelo (Berretta), Nurzhan (Tagirov), Alan (Ba). Fix: expand `_MALE_NAMES` (and consider a maintained gender-name dataset) in `enrich.py`; add these 6.
- [ ] **`owner_name` set to a corporate entity instead of a natural person** — koettermann.com owner='KTT Service a. s.', skills-med.de owner='Skills Med Europe B.V.' (foreign parent companies). Ansprechpartner must be a natural person; a corporate gesellschafter should NOT populate owner_name (leave empty → generic salutation). Fix: reject legal-entity strings (a.s., B.V., GmbH, AG, …) in the owner_name derivation. Scope: `normalize.py` owner derivation + `_is_natural_person_name`.
- [ ] **Batch-Übersicht "missing fields" badge undercounts** — IMS shows "2 missing" in the count but the card visibly has Salutation, Anrede, Gruppe 1, Gruppe 2, Gesellschafter-Field all empty (5). The badge doesn't count all blocking fields. Fix: align the missing-count logic with the full BATCH_READINESS_SPEC blocking-field set. Scope: dashboard batch-overview status calc.
- [ ] **GF extraction misses titles and grabs trailing junk** — `_extract_gf_from_impressum` / `_GF_PATTERNS` / `_sanitize_gf_name` in `enrich.py`: (a) misses the GF when a title sits between the marker and the name — `"Geschäftsführer Dipl.-Wirt.-Ing. (FH) Alexander Vollenwyder"` (bemed.com) and `"Geschäftsführer und inhaltliche Verantwortung: Christoph Bartram"` (medizinio.de) → no GF captured; (b) appends trailing non-name junk — mediplan-online.de produced gf/owner `"Ziya Aydinli Zuständiges Gericht"` (the sanitizer didn't stop at the name boundary). Fix: allow academic/professional titles (Dipl.-*, Ing., M.Sc., …) and intervening label text before the name; truncate at trailing label words ("Zuständiges Gericht", "Registergericht", …). Scope: `enrich.py` GF patterns + `_sanitize_gf_name`.
- [x] **`backfill-impressum` / name enrichment only fills empty — never corrects a WRONG name** — **Fixed (2026-06-14):** added `--force` flag to `backfill-impressum` command. `python pipeline.py backfill-impressum --force` overwrites existing `impressum_name` values (default still only fills empty).
- [ ] **Email enrichment is a time-hog for letter prep** — full `enrich` runs email permutation+verify (~8 permutations × ~21s each ≈ 3 min/record via the verify endpoint); `gf_email` is non-blocking (not in the letter). For letter readiness, run ownership-only and skip email (or run email as a separate overnight job). Scope: add `enrich --ownership-only` flag (or `--skip-email`).

Features
- [ ] **Undo button in review pane** — reverts last field change for active record. Requires M27 (activity log backend). Scope: single-record last-change revert; no multi-step history in v1.
- [ ] Company unique identifier: Each company gets a computed incremental identifier (no DB column). Used as Lead-Liste first column and Briefmarken Referenz.
- [ ] We need a legend (clickable or collapsible) explaining field meanings, color codes, and workflow steps.
- [ ] **No grammar/quality check on export** — No validation of AI-generated German letter text before PDF export. Needs spec: full assembled Serienbrief letter text validated via Claude CLI. Scope: when does it run, how are results shown, block export or advisory? Spec in dedicated session.
- [ ] Co-Med Filter: Part of the scraping should be and be updated to a flag 1 or 0 if the company is a Co-Med partner (scraping for Co-Med notes)


---

## Resolved (commit refs for traceability)

### 2026-05-11
- [x] **Freigabe validation** — button disabled when Pflichtfelder missing (detail view + Lead-Liste checkbox); confirm-bypass removed; tooltip shows missing fields. 2026-05-11.

### 2026-05-07
- [x] **Freigabe hard-gate** — block approval when required letter fields missing (was soft confirm). Verified 2026-05-07.
- [x] **Follow-Up view** — inline-editable table for sent letters: status, FU1/FU2 dates, comments, email/phone. Verified 2026-05-07.
- [x] **Cohort tracker BA1-7** — sent count from outreach_sent_at; status columns match actual DB values. Verified 2026-05-07.
- [x] **run-all completion** — 7 stages (was 4) + --from-stage flag. Verified 2026-05-07.

### 2026-05-06
- [x] **Website preview fallback** — `onerror` never fires for X-Frame-Options blocks; replaced with 4s timer-based detection + fallback message. Verified 2026-05-06.
- [x] **Briefmarken CSV export** — wired disabled button to `/api/export-briefmarken?batch=` endpoint; downloads semicolon-delimited CSV (latin-1). Verified 2026-05-06.
- [x] **VS Code-style toggle sidebar** — icon rail + collapsible 180px panel, auto-collapse on section select. Logo bottom-left. Verified 2026-05-06.
- [x] **PDF export logo centered** — was left-aligned, now `(PAGE_W - LOGO_WIDTH_MM) / 2`. Verified 2026-05-06.
- [x] **Alt+E mode switch** — now switches to Review mode before opening Export. Codex-reviewed 2026-05-06.
- [x] **Orphaned CSS cleanup** — `--ink-1` undefined var fixed, dead `.subnav .icon-btn` rules removed. 2026-05-06.

### 2026-05-05
- [x] **Queue hides BA1-BA7** — removed filter_pass constraint from getFilteredRows(); amber 'F' badge on filtered records; 'Ausgefiltert' chip added. 2026-05-05.
- [x] **K1 trailing comma** — fixed in normalize.py rstrip. 2026-05-05.
- [x] **White squares on top left** — transparent logo PNG, updated ALLEX_LOGO_PATH. 2026-05-05.
- [x] **Skip button** — removed btn-skip from actions bar. 2026-05-05.
- [x] **Description truncation** — record-desc flex:1;min-width:0; spacer removed. 2026-05-05.
- [x] **Banner arrows pushed right** — removed max-width:500px cap. Verified 2026-05-05.
- [x] **Approached records badge** — 'Kontaktiert in BA...' badge on approached records. 2026-05-05.
- [x] **Batch abschicken** — mark approved records as sent (outreach_sent_at). 2026-05-05.
- [x] **Excel Serienbrief export** — /api/export-leadliste endpoint, .xlsx download from Lead-Liste view. 2026-05-05.
- [x] **Company unique identifier (#ID)** — computed incremental ref, shown in banner + Lead-Liste. 2026-05-05.

### 2026-05-04
- [x] **Verb field (K2)** — hat/haben select after K2; letter template updated. 2026-05-04.
- [x] **Name fields (Stammdaten)** — Name Überschrift, Absatz 1, Absatz 3 added; defaults to full_name. 2026-05-04.
- [x] **Leistung 2 label** — renamed from "Leistung". 2026-05-04.
- [x] **CHANGELOG.md** — created at `ai/CHANGELOG.md`. 2026-05-04.
- [x] **Kategorie pills** — A/B/C/D/E/S color-coded pills + Prio pills replacing topbar klass select. 2026-05-04.
- [x] **Excel export** — Lead-Liste Excel export added. 2026-05-04.
- [x] **Region mapping** — replaced xlsx with `src/data/region_mapping.json` (commit 88de100). 2026-05-04.
- [x] **Lead-Liste columns** — reordered; filter_reason/ownership_reason/reclassify_reason added. 2026-05-04.
- [x] **Brief-Vorschau/Website tabs** — flex:1, active=light bg+spar border, inactive=surface-2. 2026-05-04.
- [x] **Collapse on Freigabe** — all .fields-section elements collapse after Freigabe PATCH. 2026-05-04.
- [x] **Alt+S/Alt+E shortcuts** — replaced Ctrl+S; fire before INPUT/TEXTAREA/SELECT guard. 2026-05-04.
- [x] **Drop-Off BA8 count** — reverted to global DATA.dropoff. 2026-05-04.
- [x] **Chip order** — reordered: Kontaktierte Ausbln. → Gesellschaft → Fehlend → Prüfen. 2026-05-04.
- [x] **Description position** — moved LEFT of company name (flex sibling). 2026-05-04.
- [x] **Klassifizierung → Kategorie** — moved from top bar to right-side pill section. 2026-05-04.

### 2026-04-30
- [x] **EXPORT Flag** — PDF export scoped to selected Batch only. 2026-04-30.
- [x] **Queue name truncation** — `title` attribute for hover reveal. 2026-04-30.
- [x] **Briefaktionen Filter position** — Batch dropdown moved to queue sidebar header. 2026-04-30.
- [x] **Briefmarken export** — `export-briefmarken --batch` CLI command. 2026-04-30.
- [x] **Rename BA-Prep → Batch** — all user-facing labels renamed. 2026-04-30.
- [x] **Already Approached toggle** — "Kontaktierte ausbln." filter chip. 2026-04-30.
- [x] **Speichern shortcut** — changed from Cmd+S to Ctrl+S. 2026-04-30.
- [x] **Brief-Vorschau/Website shortcut** — Alt+1/Alt+2 tab switching. 2026-04-30.
- [x] **Arrow key navigation** — Left/Up = previous, Right/Down = next. 2026-04-30.
- [x] **Default batch selection** — auto-selects highest BA on load. 2026-04-30.
- [x] **Filter chip tooltips** — German descriptions on hover. 2026-04-30.
- [x] **White square on blue bar** — `.side-brand` background fixed. 2026-04-30.

### Earlier
- [x] **Letter date format** — German format "29. April 2026" via `formatDateDE()`.
- [x] **Panel contrast** — preview panel darkened to #d8d5cc.
- [x] **DAG Holding UG ownership** — resolve did not update UI. `9d067f2`
- [x] **Ausschließen overflow** — button invisible on overflow. `9d067f2`
- [x] **SSB flag** — removed from view. `9d067f2`
- [x] **Sideview redesign** — 4 collapsible sections. `9d067f2`
- [x] **Company owners** — Gesellschafterinformationen section. `9d067f2`
- [x] **Manual attention** — ownership panel always rendered. `9d067f2`
- [x] **Website mock** — iframe with real domain. `3c8211c`
- [x] **Was Fehlt categories** — 4 groups with counts. `9d067f2`
- [x] **Filter by completeness** — BA-Prep filter dropdown. `9d067f2`
- [x] **Failure reasoning** — expandable details. `9d067f2`
- [x] **Lead-Liste tab** — added as 4th subnav tab. `9d067f2`
- [x] **Collapsible sidebar** — Was Fehlt + Gesellschafterinformationen default open. `9d067f2`
- [x] **region_prep empty** — auto-fill on input+blur. `3c8211c`
- [x] **Repuro CI design** — teal primary, logo placeholder. `9d067f2`
- [x] **AX logo** — `__LOGO_IMG__` placeholder. `9d067f2`
- [x] **KPI cards** — removed from BA-Prep. `9d067f2`
- [x] **Ansprechpartner reasoning** — Herkunft block. `9d067f2`
- [x] **Ansprechpartner duplication** — labels clarified. `9d067f2`
- [x] **Klass S** — option added + Ausschließen always visible. `9d067f2`
- [x] **Export PDF** — blob download fix. `9d067f2`
- [x] **PATCH failures** — async + error surfacing. `3c8211c`
