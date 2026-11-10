# M37 — OEM profile (D1 light / D2 heavy), rescan, BA11

**Status:** In progress (10.11.2026)
**Source:** `CLAUDE_COWORK/_drafts/261104_Handover_Target-Search_OEM-light.md` (binding: profile text, few-shot names, sources, build plan)
**Thesis:** OEM-light first. D1 = sells medical products under own brand or private label, production outsourced or limited to assembly/config/labelling/testing (target). D2 = own development and own production (not a target). Bias: when in doubt D1 or C. Roman downgrades D1 to D2 by hand, never the reverse.

---

## Goal

One ALLEX run that finds, scrapes and classifies maker leads into D1 / D2 / C / D under a second profile, shows them in the dashboard for Roman's review, and tags D1 + C as batch BA11. Ownership enrichment (OpenRegister) waits for Roman's review.

## Design Decisions (settled 10.11.2026, do not re-open)

1. **Second column.** New columns `klass_oem` (values `D1`, `D2`, `C`, `D`) and `klass_oem_reason` (text: `<reason_code>: <one sentence>`). The ambulatory `klass` column, `prio`, `leistung_*`, `mehrwerte`, `services_score`, flags and `classified_at` are never written by the OEM path.
2. **No size floor** at classification. Staff stated on the site is one signal, not an input. No revenue-per-head.
3. **Zero OpenRegister credits** in this milestone run. Enrich filter is extended to `klass_oem IN ('D1','C')` but not executed.
4. **Model passthrough.** `classify --model <alias>` passes `--model` to the Claude CLI. Default (no flag) = CLI default, so the ambulatory profile is unchanged. Bulk OEM runs use `--model haiku`.
5. **Exclusions.** Records with `pipeline_stage='approached'`, `already_approached=1`, or `briefaktion` set (BA1..BA10, testbatch) are excluded from the OEM rescan selection and from BA11 tagging. Also excluded from BA11: live deal targets (Baaske Medical = deal Rabbit / Projekt CARE) and source rows whose contact status shows a letter, LOI or decline.
6. **Pipeline stage.** The OEM classify path does not change `pipeline_stage`. OEM scrape writes `scraped_text`/`scraped_at`; a successful retry moves `ingested`/`scrape_failed` to `scraped`, a failure leaves or sets `scrape_failed`.
7. **Leave-one-out few-shot.** A record whose domain equals a few-shot example's domain is never shown its own example (keeps the fixture check honest).

## Profile `profiles/oem_germany.json`

Same structure as `medtech_germany.json` (id `oem_germany`). Class definitions (verbatim from the handover):

- **D1 OEM-light (target):** sells medical products under its own brand or as private label for others; production outsourced or limited to assembly, configuration, labelling, testing; signals: Konfektionierung, Montage, Systemintegration, Lieferanten, Partner, Import, Inverkehrbringer, Eigenmarke, Private Label, OEM for third parties, products built around bought-in components (PCs, displays, power, enclosures, sets).
- **D2 OEM-heavy:** own development and own production; signals: Fertigung, Produktion, Werk, CNC, Spritzguss, Reinraum, Made in Germany as a production claim, Werksverkauf, machine park, Tuttlingen instrument forge, more than roughly 100 staff where stated on the site.
- **C:** medtech maker, text does not show the production model. Treated as D1 for enrichment (bias rule).
- **D:** not a maker or out of market (distributor, service, dental, pharma, software, non-medtech), existing reason codes.

Prompt rule: assign D2 only when the text states own production or a plant; everything else that makes or brands a medical product is D1 or C.

Few-shot examples: D1 Baaske/CARE, UEBE, Hell & Co., Witeg, CIM med, STEMA, Active Key, Fuhrmann; D2 Dr. Mach, Bissinger, Geister, Zepf, ACL, provita, SCHMITZ; C from 28.10 Longlist rows without production evidence; D from the ambulatory profile. Excerpts come from each site's scraped text (production-model sentence where present; the 05.11 workbook column "Production evidence" is the pointer). Per prompt: 2 D1, 2 D2, 1 C, 1 D.

OEM reason codes: `Eigenmarke_Zukauf`, `Private_Label`, `Montage_Konfektion`, `Eigene_Fertigung`, `Werk_Reinraum`, `Produktionsmodell_unklar`, plus the existing D codes (`Unpassende_Branche`, `Dental`, `Apotheke`, `Krankenhaus`, `Kein_Hersteller`, `Pharma`, `Software`, `Ausland`, `Tochtergesellschaft`).

## Scope

**In:**
- T1 Schema: `klass_oem TEXT`, `klass_oem_reason TEXT` via the existing migration list in `db.py`.
- T2 Profile file + loader: `--profile oem` alias resolves to `profiles/oem_germany.json` (path form keeps working); profile carries `scrape.extra_paths` and `scrape.max_chars`, `classification.max_text_chars`.
- T3 Scrape: per-profile `extra_paths` (OEM adds `/produktion /fertigung /unternehmen /qualitaet /partner /oem /private-label` to the four defaults) and 4,000-char cap for OEM; ambulatory default unchanged (2,500 / four paths). OEM target selection: records with a domain, no usable text (<200 chars), stage `ingested` or `scrape_failed` or source `BA11_src`, minus exclusions; retry of `scrape_failed` bypasses an empty cache entry once. Concurrency `--workers N` (default 1) across domains; DB writes on the main thread.
- T4 Classify: OEM prompt builder (class defs, rule, leave-one-out few-shot, text cap 4,000), parser accepting only D1/D2/C/D (anything else → C, bias), writer touching only `klass_oem` + `klass_oem_reason`. `--model` passthrough. `--workers N` thread pool around the CLI subprocess. Ambulatory keyword auto-D and name-dupe copy are NOT applied in OEM mode (they copy ambulatory klass).
- T5 Rescan: `classify --profile oem --rescan` selects `klass_oem IS NULL AND length(scraped_text) > 200 AND (klass IS NULL OR klass = 'D' OR source = 'BA11_src')` minus exclusions; `--limit`, `--dry-run` supported.
- T6 Dashboard: `klass_oem` + `klass_oem_reason` in the Lead-Liste payload and as a column; filter D1 / D2 / C / D / empty; `klass_oem` editable (whitelist in `_WRITEBACK_FIELDS`, values validated to the four codes or empty) so Roman can downgrade D1 to D2.
- T7 Enrich filter: OpenRegister selection also accepts `klass_oem IN ('D1','C')` (S ownership gate unchanged). Not run in M37.
- T8 Ingest: build `data/input/261110_BA11_src.xlsx`, sheet `BA11_src`, from (a) `260518_Repuro_Medtech_Targets_v6.xlsx` tab `AV longlist` rows with `Alex AI = 'OEM'` (the handover's "102 own-brand and manufacturer rows" does not reproduce from the tab; `Alex AI = 'OEM'` is the reproducible maker filter, 604 rows), (b) `_drafts/260930_Target_Push/L_OEM_targets.csv` + `S_OEM_candidates.csv` (semicolon, column `website`), (c) `_drafts/261028_Repuro_OEM-light_Longlist.xlsx` tab `Longlist` and `_drafts/261105_Repuro_OEM-light_Targets.xlsx` tab `Targets` (domain from the Source URL where present, else from the fixture domain list). Dedupe on normalized domain against `company_records` and within the sheet. Source contact status goes to `manual_note`. Then `pipeline.py ingest-manual --file ... --sheet BA11_src` with `source='BA11_src'`, `klass` empty.
- T9 Fixture: `tests/fixtures/oem_fixture.json` = the 15 labelled names with verified domains (source column: where the domain came from). Live check script `scripts/m37_fixture_check.py` (scrape fixture domains with the OEM profile, classify with `--model haiku`, leave-one-out, print name / label / result / reason, exit non-zero on a D2→D1 or D1→D2).
- T10 BA11 tag + docs: `briefaktion='BA11'` on every record with `klass_oem IN ('D1','C')` from this run and `briefaktion IS NULL`, minus exclusions (script `scripts/m37_tag_ba11.py`, dry-run default, prints N per rule).

**Out:** MEDICA and EUDAMED name lists (no domains), OpenRegister spend, Fly sync (flyctl not authenticated on 10.11), any change to the ambulatory prompt or `klass`.

## Acceptance Items

| # | Item | Check |
|---|---|---|
| A1 | No D2-labelled fixture name (Dr. Mach, Bissinger, Geister, Zepf, ACL, provita, SCHMITZ) classified D1 | `scripts/m37_fixture_check.py` live, haiku |
| A2 | No D1-labelled fixture name (Baaske, UEBE, Hell & Co., Witeg, CIM med, STEMA, Active Key, Fuhrmann) classified D2; C allowed | same |
| A3 | Ambulatory `klass` unchanged for every record | checksum of `(domain, klass, prio, classified_at)` before vs after run, identical |
| A4 | OEM path writes only `klass_oem`, `klass_oem_reason` (classify) and `scraped_text`, `scraped_at`, stage (scrape), `briefaktion` (tag) | pytest + before/after column diff |
| A5 | Zero OpenRegister calls | run with `OPENREGISTER_API_KEY` empty in the process env; `openregister_cache.db` row count unchanged |
| A6 | Contacted / batched / live-deal records not in BA11 | SQL: BA11 ∩ (approached ∪ already_approached ∪ prior BA ∪ Baaske) = 0 |
| A7 | `--profile` default stays `medtech_germany`; no `--model` = no `--model` in the CLI argv | pytest |
| A8 | Dashboard shows `klass_oem` column + filter; PATCH accepts only D1/D2/C/D/empty | pytest + local `dashboard --serve` load |
| A9 | `pytest tests/` passes | run |

No recall threshold (bias rule).

## Test Plan

- Unit (mocked CLI): OEM prompt contains the four class definitions and the D2 rule; leave-one-out drops the own-domain example; parser maps unknown/missing klass to C; writer leaves `klass` untouched; rescan selection honours every exclusion; `--model haiku` lands in argv, absent flag adds nothing; scrape picks OEM paths and the 4,000 cap only for the OEM profile; dashboard whitelist rejects `klass_oem='A'`.
- Live: fixture script on 15 names; `classify --profile oem --model haiku --limit 5` before the bulk run; `python pipeline.py status`.
- Run report: N/M/K per step from DB queries (scrape ok / failed, classify D1 / D2 / C / D / error, BA11 size, excluded per rule).

## Definition of Done

1. This file has a filled `## AI VALIDATION RESULTS` section.
2. `pytest tests/` passes.
3. CLI ran live against real data (fixture + bulk).
4. `python pipeline.py status` shows expected counts.
5. `code-reviewer` verdict on the diff recorded below; every H finding applied.
6. `DESIGN.md` (OEM profile section) and `ARCHITECTURE.md` (columns, flags) updated in the same commit.
7. `ai/ROADMAP.md` updated (M37 delivered, open issues, next: MEDICA/EUDAMED slices, D1 enrichment after review).

## AI VALIDATION RESULTS

Run 10.11.2026, local `data/pipeline.db` (backup `data/pipeline-backup-2026-11-10-preM37.db`), every command with `OPENREGISTER_API_KEY` empty.

| Step | Result (DB query or command log) |
|---|---|
| Ingest `BA11_src` | 575 new records (05.11 Targets 32, L_OEM 2, S_OEM 2, AV longlist `Alex AI = OEM` 539); 77 skipped as already in DB, 45 in-sheet duplicates |
| OEM scrape | 1,478 selected, 1,183 usable, 295 failed (BA11_src 482 / 93; base 701 / 202) |
| OEM classify (4 runs, haiku, 8 workers) | 2,152 classified, 0 errors: D1 196, C 179, D2 152, D 1,625 (BA11_src 107 / 115 / 106 / 154; base klass NULL 48 / 38 / 29 / 1,119; base klass D 41 / 26 / 17 / 352) |
| BA11 tag | 374 (D1 195, C 179; BA11_src 221, base 153); excluded: live deal 1 (Baaske), approached / contacted / prior batch 0 |
| A1 / A2 fixture (live, haiku, leave-one-out, final code) | A1 7/7, A2 8/8, 0 hard misses; UEBE, Witeg C; Zepf D (dental); SCHMITZ C |
| A3 ambulatory checksum (domain, klass, prio, classified_at) | `7f4a89aa411ce059` before and after |
| A5 OpenRegister | cache 1,876 rows, credits 1,877 before and after |
| A6 BA11 ∩ contacted / batched / live deal | 0 |
| A8 dashboard | local `dashboard --serve --dev`: `/api/data` returns 374 BA11 with `klass_oem`; OEM + OEM-Grund columns present; PATCH `klass_oem='A'` → 400 (dev-worker check) |
| A9 pytest | 530 passed, 6 failed (pre-existing, confirmed on `git archive HEAD`) |
| Readiness (BATCH_READINESS_SPEC) | not send-ready by design: anrede 3 %, owner 7 %, street 7 %, region 14 %, leistung 11 %, compliments 0 % (enrichment waits for review) |

Note: `normalize --dry-run` is not dry: it calls `ensure_scrape_for_briefaktion` and fetched live (12 batched records re-scraped before it was stopped). Normalize does not apply to BA11 (no `Prio 1` records) and was not run.

## Code Review

- `code-reviewer` (context-free): REVISE. H applied (`enrich` OEM selection behind `--include-oem`, never from run-all / ensure-enrich). M applied: OEM flags without `--profile oem` exit 2; fixture check fails on `-` / `ERR`; ambulatory classify skips `BA11_src`. L applied: `>= 200` in both selections, lenient JSON always trims. L residual: shared scrape cache (L6), contact status of rows already in DB (L8, checked: no leak). ROADMAP open issues.
- Codex (gpt-5.6-terra, standard): BLOCK, 4 findings, all applied: default enrich excludes `klass_oem` D1 / C even on the Prio 1 path (default selection 46, same as pre-M37; `--include-oem` 152 before BA11); `filter` skips `BA11_src`; OEM writer only writes where `klass_oem IS NULL` (no overwrite of a hand edit); tag script holds `BEGIN IMMEDIATE` from plan to commit.
