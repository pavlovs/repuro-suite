# DEALROOM — Roadmap

Last updated: 2026-07-11 (v2 local build).
Scope: NDA exchange → closing (full deal lifecycle since Schema v2).
ALLEX has authority over pipeline stage — DEALROOM reads, does not write back (for now).

---

## v2 REBUILD (SPEC-DEALROOM-V2.md) — built locally 2026-07-10/13

All six milestones + suite tie-in built + tested in `v2/` (39 tests green; plans
`ai/PLAN-DR-V2-M1.md` / `-M2` / `-M3` / `-M4-M5` / `-M7-SUITE-TIE`). Local sandbox
on :8082 (`python -m v2.server --port 8082`), DB `data/dealroom_v2.db` (rebuildable
via `python -m v2.migrate_v1`; v1 read-only). v1 code untouched and still serving prod.

**UI rebuild after 13.07 rejection** (screens ship one at a time, sign-off each;
old M3–M5 surfaces unregistered): Screen 1 = Portfolio (v1 port, e69bbe6).
**Screen 2 = Offer & Negotiation (13.07, this block)**: standalone v1-language
page `/deal/{code}/negotiation` (owner-only), spec `ai/SPEC-OFFER-NEGOTIATION-TAB.md`.
Data layer: `negotiation_offers` + `negotiation_offer_terms` (bucket-based offer
history per LOI structure) + `negotiation_positions.their_position/prio` — added
to v1 via `negotiate_ops.py migrate` (new `offer` subcommand, 31 tool tests),
carried by migrate_v1. Populated for Cat/Lion/Fox/Mantis/Mouse/Aqua from source
docs (signed LOI PDFs, offer PDFs, negotiation rounds, deals.md; every event
source-cited). NOTE: Fox deal_terms seed corrected against the signed LOI
(1.000 Sofort + ca. 150 Co-Med + 750 EO gestaffelt = 1.900; deals.md prose
"1.6 + 0.3 EO" contradicts the signed doc — Roman to update deals.md).
Screen-2 tests: `v2/tests/test_ui_negotiation.py` (6).

**Suite tie (M7, 13.07)**: deal page reads Cockpit (read-only) for the deal's
open deliverables + tasks ("Execution — Cockpit" section, deep-linked) and shows
Investor-Room visibility (named live-deal vs anonymised funnel) computed with
boardroom's own stage buckets. Negotiation tie = M5. `cockpit.db` path is
`COCKPIT_DB` on Fly / sibling locally; absent DB degrades cleanly.

**Open before Fly cutover (needs Roman):**
1. Confirm stage-correction diffs (Fox/Mantis→due_diligence, Lion→indicative_offer, Swordfish→Aqua revived) — applied in the local sandbox only.
2. Confirm kill list §10 (v2 DB simply doesn't carry the dead tables; v1 untouched; deal_data_v1_archive exported to `data/archive/`).
3. Sign-off on the sandbox UI (DEV-FIRST), then cutover: one-time migration against Fly volume, supervisord command → `python -m v2.server --port 8082`, `DEALROOM_TRUSTED_PROXY=1`, boardroom/cockpit repointed (their queries already pass against v2 — tested), retire deploy-time DB snapshot.
4. Deferred to cutover phase: COM/xlsx extraction adapters push via HTTP (v1 `extract` keeps working locally until then; DR-BUG-020/022/025 move with that work); data-room scanner paths for live seller shares (`data/scanner_paths.json`); scheduled scan via RepuroAgentLoop.

---

## Milestone Overview

| # | Name | Delivers | Status |
|---|------|---------|--------|
| DR-M1 | Foundation | CLI, dealroom.db (all tables), seed deals, velocity fields, quick note | ✅ |
| DR-M2 | Document Registry | ingest-docs: scan OneDrive folder, classify, populate deal_documents | ✅ |
| DR-M3 | Data Extraction | Rule-based extraction → deal_financials (P&L, balance, BWA) + conflict detection + risk flags | ✅ |
| DR-M4 | Deal Workspace Dashboard | Portfolio view + deal workspace (cockpit, P&L, balance, docs, notes) on port 8090 | ✅ |
| DR-M5 | Excel Model Builder | Populate model template for new deals; read + reconcile existing models | ✅ |
| DR-M6 | RFI Generator | Question list → Word + deal_questions; answers feed deal_financials | ✅ |
| DR-M7 | Interactive Valuation Model | Live valuation engine + earn-out matrix + dashboard model tab | ✅ |
| DR-M8 | Company Overview | Deal overview landing page: company facts, map, financial timeline, owner profile | ✅ |
| DR-SV2 | Schema v2 — Normalized Tables | EAV → 22 normalized tables, stage redesign, doc status, scorecard, gate config | ✅ |
| DR-GC | Golden Corpus | Roman-curated reference docs (28 files), shared loader, 6 template-fill specs, health check CLI | ✅ |
| DR-M9 | Investor Cockpit | One-pager as deal landing page (2x2 grid), stage filter on portfolio, drill-down to tabs. Spec: `SPEC-INVESTOR-COCKPIT.md` | 🔄 |
| DR-M16 | Interactive Model View | ~~Deferred~~ — delivered by DR-M7 | ✅ |
| DR-M18 | Bilanz + Valuation Views | Balance sheet tab + dedicated valuation view (EV scenarios, multiples, deal structure) | ⬜ |
| DR-M19 | Sidebar Reorganization | 3-block sidebar (Deal Economics / Business Fundamentals / Process Artifacts), 14-section IC memo nav | ⬜ |
| DR-M20 | Business Model + Investment Thesis | Business model view + SWOT matrix + scorecard + strategic rationale | ⬜ |
| DR-M8b | Offer & Negotiation (expanded) | Offer generator + negotiation issue list + seller counter-positions | ⬜ |
| DR-M21 | Employees + Suppliers + Market | Employee view, supplier table, market & competition section | ⬜ |
| DR-M13 | Cross-Deal Benchmarking | Compare all deals via deal_financials + deal_commercial; flag outliers | ⬜ |
| DR-M22 | Deal History + Stage Tracking | Stage timeline, unified activity feed, open actions, contact log | ⬜ |
| DR-M10 | Email Composer | Intent-driven email draft; updates last_contact_at | 🔒 Deferred |
| DR-M11 | Granola Sync | Meeting transcripts → deal_meetings; data_points cross-check vs deal_financials | 🔒 Deferred |
| DR-M12 | NDA Generator | NDA draft → Word from template | 🔒 Deferred |
| DR-M14 | Due Diligence Package | DD request list → Word; gap detection vs. received docs; deal_dd_items tracking | 🔒 Deferred |
| DR-M15 | Investor Report | Export cockpit data as shareable investor update (recipient-aware filtering). Thin layer on DR-M9 | ⬜ |
| DR-M17 | Outside-In Canvas + `/deal-update` | Per-target strategic canvas via WebSearch + Opus → static HTML | 🔒 Deferred |
| DR-M25 | Commercial DD Module | `deal_invoices` fact table, databook ingest + 106-check tie-out gate; analyses rendered INSIDE the IC-memo sections (segments→Business Model, cohorts/churn→Customers & Suppliers, findings→DD). Spec: `PLAN-DR-M25-CDD.md` | ✅ |
| DR-M26 | Deal State Pack (session entry) | `tools/deal_state_pack.py` + `tools/dd_item.py` + `state/<codename>-pack.md`; `deal_dd_items` ledger + `last_verified_at`; `[CODENAME]` prompt-hook injection + `/deal-brief` skill. Interim pre-v2 — generator becomes the v2 M2 scanner; ledger migrates as-is; write path re-points to Fly API at v2 M1 (2026-07-10) | ✅ |

Status: ⬜ = not started, 🔄 = in progress, ✅ = complete

---

## Detailed Milestone Specs

### DR-M1 — Foundation
**Delivers**: Working CLI. `DEALROOM.py deals` lists all active deals. `DEALROOM.py status` shows DB state + OneDrive folder + velocity indicators. Quick note entry. All other commands stubbed.

**DB**: 22+ tables since DR-SV2 (see ARCHITECTURE.md). Critical columns:
- `deals.stage_entered_at` — auto-set when stage changes
- `deals.last_contact_at` — updated by email composer + Granola sync
- `deal_financials` — normalized P&L, balance, adjustments, bewertung (replaced EAV `deal_data` in DR-SV2)

**Seed data** (10 active deals):

| Code | Company | Domain | Stage | OneDrive folder |
|------|---------|--------|-------|-----------------|
| Octopus | HWV Hanseatische... | hwv-med.de | offer_sent | `250611_HWV (Octopus)` |
| Cat | Medizin & Service GmbH | — | offer_negotiation | `250612_Medizin & Service (Cat)` |
| Lion | Golmed GmbH | golmed.de | offer_negotiation | `250724_Golmed (Lion)` |
| Fox | Com2Med | com2med.de | offer_preparation | `250702_Com2Med (Fox)` |
| Wolf | KVG Vertriebs GmbH | — | offer_negotiation | `251125_KVG (Wolf)` |
| Colibri | Menke-Med GmbH | menke-med.de | offer_preparation | `250828_Menke (Colibri)` |
| Falcon | KoeWe Medizinbedarf | koewe.com | offer_preparation | `260225_KoeWe (Falcon)` |
| Owl | RS Radiology Support | radiology-support.de | financials_received | `251126_RS Radiology (Owl)` |
| Eagle | Meditec Source | — | financials_received | `251002_Meditec Source (Eagle)` |
| Mouse | Everto Laborhandel | everto-laborhandel.de | financials_received | `260417_Everto Laborhandel (Mouse)` |

**`DEALROOM.py deals` output** includes: code name, company, stage, days-in-stage, last contact.

**`DEALROOM.py status`** shows: DB table counts, OneDrive link status, conflict count per deal.

**`DEALROOM.py note --deal Cat "..."` ** writes timestamped note to `deal_notes`.

**`DEALROOM.py stage --deal Cat --set offer_negotiation`** — moves deal to new stage, sets `stage_entered_at`.

**Depends on**: nothing
**Estimated scope**: 0.5 days

---

### DR-M2 — Document Registry
**Delivers**: `DEALROOM.py ingest-docs --deal Cat` scans OneDrive deal folder, classifies and registers all files in `deal_documents`. Idempotent. Reports new vs. already-registered.

**Classification logic** (real OneDrive folder structure):
- `0_Verträge und Meetings/` + `.pptx`/`.pdf` → `doc_type='meeting'`
- `0_Verträge und Meetings/NDA/` → `doc_type='nda'`
- `1_Unternehmensinformationen/` + `.xlsx` with "GuV" in name → `doc_subtype='guv'`
- `1_Unternehmensinformationen/` + `.xlsx` with "Bilanz" → `doc_subtype='bilanz'`
- `1_Unternehmensinformationen/` + `.xlsx` with "BWA" → `doc_subtype='bwa'`
- `1_Unternehmensinformationen/` + `.pdf` with "JA" or "Bericht" → `doc_subtype='ja_bericht'`
- `2_Model/` + `.xlsx` NOT in `_archive/` → `doc_type='model'`
- `3_Indikatives Angebot/` → `doc_type='offer'`
- `4_LOI/` → `doc_type='loi'`
- `5_DD/` → `doc_type='dd'`
- Year extracted from filename where present

**Depends on**: DR-M1
**Estimated scope**: 0.5 days

---

### DR-M3 — Data Extraction
**Delivers**: `DEALROOM.py extract --deal Cat` reads registered financial documents and extracts all available data into `deal_financials`. Runs conflict detection. Covers P&L, balance sheet, BWA.

**Sources read** (in extraction order):
1. GuV files → `financial.pnl` entries per fiscal year
2. Bilanz files → `financial.balance` entries per fiscal year
3. BWA files → `financial.ltm` (annualized)
4. JA-Berichte → secondary confirmation of P&L numbers
5. `deal_questions` with status='answered' → commercial KPIs (if structured answers exist)

**Method**:
- Read Excel with openpyxl → dump relevant rows as plain text
- Claude (haiku) with explicit JSON schema: `{"revenue": float|null, "cogs": float|null, ...}`
- Claude identifies normalization candidates (owner salary, non-recurring items) → stored in `financial.adjustments.normalization_items_json`
- Each extracted value stored as a `deal_financials` row with `source=filename`, `confidence='stated'`

**Auto risk flags** (computed on the fly, not stored — returned as list):
- Revenue declining >5% YoY
- EBITDA margin < 10%
- Normalization > 20% of reported EBITDA
- Missing year in expected range

**Conflict detection** runs after extraction:
- Query: same (domain, category, subcategory, fiscal_year, key) with different value_num across sources
- Both records flagged with `conflict_ids` pointing to each other
- `DEALROOM.py status` shows conflict count; dashboard shows badge

**`--dry-run`**: prints extracted JSON without writing.

**Depends on**: DR-M2
**Estimated scope**: 2 days (format variance is the hard part)

---

### DR-M4 — Deal Workspace Dashboard
**Delivers**: `DEALROOM.py dashboard --deal Cat` opens the full deal workspace in browser. Visual feedback loop for extraction debugging and deal review.

**Cockpit strip** (always visible at top):
- Code | Company | Stage badge | `X days in stage` | `Last contact Y days ago` (red if >14d in offer stages)
- Conflict badge (if any unresolved conflicts in deal_financials)
- Open topics count (questions unanswered + actions open)

**Tabs**:

**Overview** — deal summary:
- Key metrics from `deal_financials`: revenue (LTM), EBITDA (adj.), margin, CAGR
- Valuation: latest `deal_valuations` row — EV range, deal structure
- Stage timeline (visual): financials received → [stage dates] → current stage

**Financials** — P&L table:
- Rows: revenue, gross profit, gross margin %, personnel, EBITDA, EBITDA adj., EBITDA margin, EBIT
- Columns: each fiscal year + LTM
- Source badges per cell: which file the number came from
- Conflict indicators inline (red with tooltip)

**Commercial** — from `deal_commercial`:
- Recurring revenue %, top customer concentration, revenue split by segment
- Populated from RFI answers or manual entry; empty cells shown with "ask in RFI" prompt

**Model & Valuation** — from `deal_valuations`:
- Latest model file link
- EV scenario table (low/mid/high)
- Offer round ledger: table of rounds with Repuro bid, seller counter, gap, movement
- Earn-out structure

**Internal Deal Screen** (decision support — internal only, NOT the investor one-pager):
- Investment rationale: 3 bullets (Claude-drafted from deal_financials + deal_commercial, editable inline)
- Top 3 risks / open DD topics (populated from high-importance deal_questions + deal_actions)
- Scorecard with directional arrows:
  - Strategic fit to thesis (based on deal investment_thesis + sector context)
  - Recurring revenue % (vs. portfolio target)
  - Customer concentration (top3 share)
- Anything in this tab is internal — separate from the investor one-pager

**Documents** — all registered files by type, sorted by date, with links

**Timeline** — chronological: outreach → NDA → first meeting → financials → RFI sent → offer rounds → current

**Notes** — timestamped `deal_notes`, newest first

**Open Topics** — all `deal_questions` (open + sent), grouped by category/subcategory

**Depends on**: DR-M3
**Estimated scope**: 2 days

---

### DR-M5 — Excel Model Builder
**Delivers**: Populates the standard Excel model template for new deals. Reads and reconciles existing models. Replaces the planned Python valuation engine.

**Rationale**: valuation logic lives in the Excel model (Repuro's own template, versioned per deal). DEALROOM does not recompute EV independently — it reads the model's outputs and stores them in `deal_financials` and `deal_valuations`. For new deals without a model, it creates one.

**New deal flow** (Owl, Eagle, Mouse — no `2_Model/` file):
1. Load model template (planned, not yet created)
2. Populate GuV sheet with `deal_financials` WHERE statement='pnl' entries by year
3. Populate Bilanz sheet with `financial.balance` entries
4. Add validation: revenue - COGS must equal gross_profit within rounding; EBITDA must reconcile
5. Highlight cells in yellow where underlying data has `is_authoritative=0` or `confidence='estimated'`
6. Mark cells with open `deal_questions` -> add comment "Open: [question text]"
7. Save to `2_Model/{date}_{code}_Model_v1_vCLAUDE.xlsx` — `_vCLAUDE` suffix marks DEALROOM-generated files; never overwrite existing Roman-built models
8. Register in `deal_documents`

**Existing deal flow** (Octopus, Cat, Wolf etc. — model already exists):
1. Identify latest model (highest date, not in `_archive/`)
2. Read key output cells: EBITDA basis, EV range, deal structure components
3. Store as `deal_financials` with `is_adjusted=1`, `source=model_filename`, `confidence='confirmed'`
4. Reconcile: compare model EBITDA vs. extracted `financial.pnl.ebitda` — flag discrepancies as conflicts
5. Populate `deal_valuations` row: `ebitda_basis`, `ev_low/mid/high`, `cash_at_closing`, `rueckbeteiligung`, `earnout_structure`, `source_model_file`

**`--dry-run`**: prints what would be written without saving.

**Long-term (DR-M16)**: Replace Excel model with interactive dashboard model view. This milestone is the bridge — it keeps the Excel workflow for now while building the data layer that will eventually replace it.

**Depends on**: DR-M3
**Estimated scope**: 2 days

---

### DR-M6 — RFI Generator
**Delivers**: `DEALROOM.py draft-rfi --deal Cat` generates a structured question list and email draft.

**Input sources** (Claude reads all):
1. `config/rfi_examples/` — Roman's example question lists (any format)
2. `1_Unternehmensinformationen/` files for this deal
3. Unresolved conflicts in `deal_financials` (automatic questions for each conflict)
4. Granola meeting transcripts (if DR-M11 done)

**Generation logic** (Claude sonnet):
- Draft 10–15 questions across three categories with subcategories:
  - **Financial**: revenue drivers, cost structure, normalization items, working capital, net debt
  - **Commercial**: top 10 customer split, recurring revenue %, revenue by service line, contract durations, key account risk, pipeline
  - **General**: personnel/key persons, regulatory, legal
- Each question tagged with `category`, `subcategory`, `importance`, `sort_order`
- Conflict-driven questions auto-added: "Your GuV shows revenue €6.2M but the model shows €6.4M — please clarify"
- `answer_feeds_data_key` pre-filled for commercial questions (e.g. `commercial.recurring.recurring_pct`)

**Output**:
- Word doc: `1_Unternehmensinformationen/{date}_{code}_Fragenliste_DRAFT.docx`
- All questions stored in `deal_questions` with status='draft'

**Manual edit**: edit questions in dashboard Open Topics tab. Bulk "Mark as Sent" → sets status='sent', updates `deals.stage_entered_at` if stage is `financials_received`.

**Answer flow**: when answers arrive, record in `deal_questions.answer`. For questions with `answer_feeds_data_key`, system prompts: "Update deal_financials/deal_commercial with this answer?" — Roman confirms, record updates accordingly.

**`config/rfi_examples/`**: drop your example question lists here before using this command.

**Depends on**: DR-M3
**Estimated scope**: 1 day

---

---

### DR-M8 — Company Overview
**Delivers**: Default deal landing page with company facts (ALLEX), Leaflet map with EBITDA-sized circle marker, financial timeline table (revenue + adj. EBITDA up to 2025), owner/seller profile, contact info, investment thesis, deal stage timeline. Negative EBITDA risk flag. Offline map fallback.
**Status**: ✅ Complete (2026-04-03). 121 tests passing.

---

### DR-SV2 — Schema v2: Normalized Tables
**Delivers**: Full schema redesign from EAV (`deal_data`, 569 rows) to 22 normalized tables. Stage taxonomy aligned to DEAL_STAGE_REDESIGN.md. Document status tracking. Configurable deal scorecard. Stage gate config.
**Status**: ✅ Complete (2026-04-22).

**What changed**:
- **10 new tables**: `deal_financials`, `deal_commercial`, `deal_customers`, `deal_backlog`, `deal_employees`, `deal_suppliers`, `deal_competitors`, `deal_contacts`, `deal_manual_gates`, `deal_dd_items`, `deal_scorecard_config`, `deal_scorecard_results`, `deal_meetings`
- **3 ALTERed tables**: `deals` (+deal_status, status_note, previous_stage, sector, location, founded_year, exclusivity_start/end), `deal_documents` (+doc_status, doc_status_note, previous_doc_status), `deal_emails` (full redesign with thread_id, contact_id, deal_stage_at_send)
- **Data migration**: 569 `deal_data` rows → 516 `deal_financials` + 30 `deal_customers` + 23 `deal_commercial`. Originals archived as `deal_data_v1_archive`
- **Stage migration**: `financials_received`→`valuation`, `offer_preparation`→`valuation`, `offer_negotiation`→`offer`, `offer_sent`→`offer`
- **Gesamtleistung/revenue split**: separate line_items; CAGR always on gesamtleistung
- **DATEV konto_nr**: preserved during extraction via `_extract_konto_nr()`
- **All consumers rewritten**: data.py, model.py, valuation.py, dashboard.py, rfi.py, DEALROOM.py

**Files changed**: db.py (schema + migrations), data.py (extraction engine), model.py (Excel reader), valuation.py (model context builder), dashboard.py (~20 queries), rfi.py (financial summary), DEALROOM.py (status table list), ARCHITECTURE.md (full rewrite)

---

### DR-GC — Golden Corpus
**Delivers**: Roman-curated reference document infrastructure for all DEALROOM template-fill processes. Shared golden corpus loader module. CLI health check. Hardened specs per doc type.
**Status**: ✅ Complete (2026-05-19). Phase 1 (infrastructure) + Phase 2 (specs + expanded corpus) both done. 2 Codex reviews passed.

**What it provides**:
- Golden folder at `config/golden/` with subfolders per doc type
- `manifest.json` v3 registry: 28 files across 7 active types (rfi:6, offer:7, nda:6, loi:2, model:4, onepager:2, databook:1)
- Shared golden loader (`golden.py`): docx, md, xlsx, pdf, pptx extraction; `exclude_from_corpus` flag; token budget
- `DEALROOM.py golden-check` — validates corpus health, reports gaps
- Template-fill specs at `ai/golden-spec/SPEC-{type}.md` — hardened fill maps, edge cases, confidence assessments

**Template-fill specs** (all complete):
- SPEC-NDA: 6-field bilateral fill, very high confidence, ~50 lines implementation
- SPEC-RFI: 8-category stage-gated question bank, anti-patterns, review gate
- SPEC-LOI: A-L clause template, ~60% automatable, C2M as template base, cross-spec pricing schema
- SPEC-OFFER: 4 earn-out patterns, 3 Sofortzahlung types, ~55% automatable
- SPEC-MODEL: 15 hard constraints, BEWERTUNG deep dive, Excel COM only, LION/CAT confirmed templates
- SPEC-ONEPAGER: 2x2 grid with EMU measurements, think-cell WMF dependency, placeholder workflow for Q2

**Known gaps** (deferred): email examples, full DD checklist

**Depends on**: DR-SV2
**Required by**: DR-M8b, DR-M9, DR-M10, DR-M12, DR-M14

---

### DR-M8b — Offer Generator
**Delivers**: `DEALROOM.py draft-offer --deal Cat` generates a German indicative offer draft.

**Process**:
1. Read latest `deal_valuations` row for this deal
2. Read company + seller info from `dealroom.deals` + `allex.company_records`
3. Load offer template (to be created with DR-M8b)
4. Fill: seller names, company, EV components (cash, Rückbeteiligung, earn-out), economic date
5. Claude (sonnet): write the Begründungsabsatz (2–3 sentences, deal rationale from investment thesis)
6. Determine `offer_round` = max existing round + 1
7. Output: `3_Indikatives Angebot/{date}_{code}_Indikatives_Angebot_v{round}_DRAFT.docx`
8. Register in `deal_documents`, link `deal_valuations.offer_doc_id`

**Review gate**: `_DRAFT` until Roman renames. Never overwrites existing non-draft.

**Soft gate**: warns if pre-offer checklist < 7/9 complete. Does not block.

**Depends on**: DR-M5, DR-M7
**Estimated scope**: 1 day

---

### DR-M9 — Investor One-Pager
**Delivers**: `DEALROOM.py draft-onepager --deal Cat` generates a deal one-pager as a static HTML file.

**Content** (reads from `deal_financials` + `deal_commercial` + `deal_valuations` + `dealroom.deals`):
- Header: company name, sector, location, employees
- Investment thesis: 3–5 bullets (from `deals.investment_thesis`)
- Key financials table: revenue, EBITDA, margin, CAGR (from `deal_financials`)
- Commercial profile: recurring %, service split, customer base (from `deal_commercial`) — shown as "TBD" if empty with open topics flagged
- Valuation: EV range, deal structure (from `deal_valuations`)
- **Open topics section**: lists all `deal_questions` with status='open' and importance='high'

**Interactive refinement**: Claude responds to follow-up prompts ("make thesis sharper", "update EBITDA to €1.9M"). Each refinement re-generates the HTML.

**Output**: `7_Repuro documents/{date}_{code}_Onepager_DRAFT.html` (falls back to `3_Indikatives Angebot/` if folder doesn't exist)

**PDF**: user opens HTML in browser → Ctrl+P → Save as PDF. No new dependencies.

**Depends on**: DR-M5
**Estimated scope**: 1 day

---

### DR-M10 — Email Composer
**Delivers**: `DEALROOM.py draft-email --deal Cat --intent "..."` drafts a German email.

**Context loaded**: company, seller, salutation, outreach history, last Granola summary (if available), current stage, open question count, days since last contact.

**On send** (status → 'sent'): updates `deals.last_contact_at`.

**History**: all draft + sent emails visible in dashboard Timeline tab.

**Depends on**: DR-M4
**Estimated scope**: 1 day

---

### DR-M11 — Granola Sync
**Delivers**: `DEALROOM.py sync-granola --deal Cat` pulls meeting transcripts. `--all` syncs all active deals.

**Process**:
1. Search Granola MCP with company name + code name
2. Pull transcript → Claude (haiku) extracts: summary, action items, key topics, **data_points** (any numbers or facts stated: "our revenue was €6.2M", "top customer is about 30%")
3. Store in `deal_meetings` (meeting_type='management_call', created_by='granola_sync') with `data_points_json`
4. For each data point: compare against `deal_financials`/`deal_commercial` — if different value → create conflict entry
5. Updates `deals.last_contact_at` to meeting date if more recent than current value

**Append-only**: never overwrite existing synced meetings. Old `deal_granola` archived as `deal_granola_v1_archive` (DR-SV2).

**Depends on**: DR-M4
**Estimated scope**: 1 day

---

### DR-M12 — NDA Generator
**Note**: NDA is typically signed *before* financials are shared, so before DEALROOM activates. This milestone serves re-generation, new counterparties, or deals where NDA needs refreshing.

**Delivers**: `DEALROOM.py draft-nda --deal Cat` fills NDA template (to be created with DR-M12) with company + seller data.

**Output**: `0_Verträge und Meetings/NDA/{date}_NDA_{code}_DRAFT.docx`

**Depends on**: DR-M1
**Estimated scope**: 0.5 days

---

### DR-M13 — Cross-Deal Benchmarking
**Delivers**: `DEALROOM.py bench` compares all deals with extracted data in `deal_financials` + `deal_commercial`.

**Metrics** (all read from `deal_financials` + `deal_commercial`, authoritative values only):
- Revenue CAGR (2022–2025)
- Gross margin LTM
- EBITDA margin LTM vs. adj.
- Personnel cost as % revenue
- Recurring revenue % (commercial.recurring)
- Top 3 customer concentration
- Implied EV/EBITDA (from deal_valuations)

**Output**: ranked table in `DEALROOM.py dashboard` portfolio view (all deals on one page) + optional CSV.

**Use case**: before submitting an offer, compare vs. live portfolio to calibrate the multiple.

**Depends on**: DR-M5 + >=2 deals with data
**Estimated scope**: 1 day

---

### DR-M14 — Due Diligence Package
**Delivers**: `DEALROOM.py draft-dd --deal Cat` generates a structured DD request list as a Word document. Gap detection against already-registered `deal_documents`.

**Golden dataset approach**: Before building, read existing DD checklists and Datenanfragen from the 7 live deals. Extract the standard question categories, item structure, and phrasing. Use these as the reference corpus for generation — output should match Roman's established DD style, not a generic template.

**Process**:
1. Load `config/rfi_examples/` + existing DD docs from `deal_documents` (doc_type='dd')
2. Claude (sonnet): generate categorized request list from golden corpus + deal-specific gaps
3. Gap detection: cross-reference requested items against `deal_documents` already registered → flag what's missing
4. Output: `5_DD/{date}_{code}_DD_Anforderungsliste_DRAFT.docx`
5. Store items in `deal_questions` with category='dd', status='draft'

**Depends on**: DR-M4
**Estimated scope**: 1 day

---

### DR-M15 — Investor Report
**Delivers**: `DEALROOM.py draft-investor-report --deal Cat --recipient ASF` drafts a periodic deal update for a named investor.

**Golden dataset approach**: Before building, read existing investor update emails/reports (ASF weekly updates, etc.) from Outlook or stored files. Extract: structure, tone, level of detail, what gets included vs. omitted per recipient type. Critical: enforce the existing feedback rule — never include competing investor or deal info.

**Process**:
1. Read `deal_financials` + `deal_valuations` + recent `deal_meetings` summaries + `deal_notes`
2. Claude (sonnet): draft update in established tone and structure from golden corpus
3. Recipient-aware: each investor gets a version that contains only info appropriate for that party
4. Output: draft email body (stored in `deal_emails`) + optional Word attachment

**Standing rule**: never reference competing investors, competing targets, or deal-sensitive third-party info in any investor report. Each report written as if recipient is the only investor.

**Depends on**: DR-M11 (Granola Sync), DR-M4
**Estimated scope**: 1 day

---

### DR-M18 — Bilanz + Valuation Views (P0)
**Delivers**: Two new subtabs under "Valuation & Financials". Bilanz (balance sheet): Aktiva/Passiva by year, key ratios (EK-Quote, Working Capital, Net Debt, Current Ratio), entity toggle. Valuation: EBITDA basis + adjustment bridge, EV scenarios (low/mid/high), deal structure waterfall (Sofortzahlung/RB/Earn-out), multiples comparison, source model link.
**Data**: `deal_financials WHERE statement='balance'` (has data), `deal_valuations` (has data), `deal_model_params`.
**Note**: P&L (GuV subtab) is [DONE] per SPEC-FINANCIALS-TAB.md — not in scope.
**Spec**: SPEC-SIDEBAR-ARCHITECTURE.md §4
**Depends on**: DR-M9
**Estimated scope**: 2 days

---

### DR-M19 — Sidebar Reorganization (P1)
**Delivers**: 3-block sidebar (Deal Economics / Business Fundamentals / Process Artifacts) with 14 sections. Block headers, visual separators. Existing tabs remapped, new sections show [SOON] placeholder.
**Spec**: SPEC-SIDEBAR-ARCHITECTURE.md §1
**Depends on**: DR-M9
**Estimated scope**: 1 day

---

### DR-M20 — Business Model + Investment Thesis (P1)
**Delivers**: Business Model section (company description, service portfolio, key KPIs, revenue model type) + Investment Thesis & Fit (SWOT matrix, scorecard, strategic rationale). Auto-generated drafts from deal data, editable inline.
**Data**: `deals.investment_thesis`, `deal_commercial`, `deal_scorecard_config`, `deal_scorecard_results`, `allex.company_records`.
**New columns**: `deals.swot_json`, `deals.business_model_text`.
**Spec**: SPEC-SIDEBAR-ARCHITECTURE.md §6, §9
**Depends on**: DR-M19
**Estimated scope**: 1.5 days

---

### DR-M8b — Offer & Negotiation (P1, expanded)
**Delivers**: Original offer generator scope + negotiation issue list view. Offer summary card, offer round ledger with deal structure columns, negotiation issue tracker (topic, buyer/seller positions, delta, status, priority), seller counter-positions feed.
**Data**: `deal_valuations`, `deal_questions WHERE category='negotiation'` (repurposed), `deal_notes`.
**Spec**: SPEC-SIDEBAR-ARCHITECTURE.md §5, golden-spec/SPEC-OFFER.md
**Depends on**: DR-M19, DR-GC
**Estimated scope**: 1.5 days

---

### DR-M21 — Employees + Suppliers + Market (P2)
**Delivers**: Employee view (headcount by department, key person risk), Supplier table (concentration, dependency risk), Market & Competition (competitor landscape, positioning, market context).
**Data**: `deal_employees`, `deal_suppliers`, `deal_competitors` — tables exist but mostly empty.
**Spec**: SPEC-SIDEBAR-ARCHITECTURE.md §7, §8, §10
**Depends on**: DR-M19
**Estimated scope**: 1.5 days

---

### DR-M22 — Deal History + Stage Tracking (P3)
**Delivers**: Stage timeline (visual), key dates, unified activity feed (notes + meetings + emails + stage changes), open actions/blockers, contact log.
**New table**: `deal_stage_history` (from, to, timestamp, trigger).
**Data**: `deal_notes`, `deal_meetings` (empty until DR-M11), `deals.stage_entered_at`.
**Spec**: SPEC-SIDEBAR-ARCHITECTURE.md §3
**Depends on**: DR-M19
**Estimated scope**: 1 day

---

## Sidebar Architecture

All new sections (DR-M18–DR-M22) follow the IC Memorandum structure defined in `SPEC-SIDEBAR-ARCHITECTURE.md`. Execution sequence: DR-M9 (finish) → DR-M18 → DR-M19 → DR-M20 → DR-M8b → DR-M21/M13/M22. See `PLAN-SIDEBAR-MILESTONES.md` for detailed milestone dependencies and priority rationale.

---

## Deferred

| Item | Reason |
|------|--------|
| ~~Interactive model view~~ | Delivered by DR-M7 |
| DR-M10 Email Composer | MCP email tools work; manual drafting is fast enough. Revisit if email volume increases |
| DR-M11 Granola Sync | Manual Granola reference sufficient; meeting data not a bottleneck |
| DR-M12 NDA Generator | Pre-DEALROOM stage, low frequency, 5-min manual fill |
| DR-M14 DD Package | No deal in DD yet; build when first deal reaches LOI |
| DR-M17 Outside-In Canvas | Research tool, doesn't move deals; expensive per run |
| ~~Negotiation tracker (formal)~~ | Delivered by DR-M8b (expanded) — offer round ledger + issue list |
| DEALROOM writes stage back to ALLEX | ALLEX has stage authority now; revisit post-first-close |
| Financial model auto-write (Excel formulas) | openpyxl write to formula cells is fragile; DR-M4 populates data cells only |
| Legal review (LOI, SPA) | Needs lawyer |
| Multi-user access | Read-only dashboard sharing — deferred post-first-close |
| Portfolio deal list — link cells to live DB | Serve mode already handles this via `loadDeal()`. Static mode deferred |
| ~~Portfolio deal list — P&L section redesign~~ | Delivered by SPEC-FINANCIALS-TAB.md (DR-M9b) |

---

## Key Invariants

1. `deal_financials` is the normalized source of truth for all financial/valuation data. `deal_commercial` for scalar KPIs. `deal_valuations` stores computed outputs only.
2. `gesamtleistung` and `revenue` are always separate line_items in `deal_financials`. CAGR always computed on `gesamtleistung`.
3. DATEV account codes (`konto_nr`) preserved during extraction.
4. Conflict detection runs on every extraction.
5. `pipeline.db` is read-only. Never write to it.
6. All generated documents end in `_DRAFT` until Roman renames.
7. `offer_round` increments with every new offer iteration — never reset.
8. `last_contact_at` is updated by the email composer (on send) and meeting sync (on meeting date). Never updated manually.
9. Meeting sync is append-only (via `deal_meetings`).
10. Excel model template is read-only input.
11. Stage advancement requires passing gate checks (documents at required statuses + manual gates).
12. SQLite journal_mode=DELETE (not WAL) due to OneDrive sync.
13. One milestone = one commit = one `PLAN-DR-M{n}.md`.
