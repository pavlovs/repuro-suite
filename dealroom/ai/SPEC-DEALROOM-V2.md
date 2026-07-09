# SPEC — DEALROOM v2

*Draft v1, 2026-07-09 — status: awaiting Roman scope confirmation + build go. Author: RC (Opus xhigh session). Evidence base: live dealroom.db dump 09.07, dealroom/ codebase, CDD skills + Fox/Mantis deal folders, SPEC-negotiation-tool.md v3, suite integration map.*

## 1. Why v2 — diagnosis (evidence, not opinion)

v1 has a strong data layer and a stale process layer. The gap is exactly Roman's four goals: answer-first, freshness, trackability, workflow mapping.

**What the 09.07 DB dump and code audit show:**

| Finding | Evidence |
|---|---|
| Stage data does not match reality | Lion = `on_hold` since 2026-03-28 while negotiation is live (offer update 08.07, negotiation pilot). Cat + Mouse = `indicative_offer` with LOIs versandfertig. Fox/Mantis = `loi_signed` while DD is running (data rooms live, Ebner Stolz engaged 02.06). |
| Status fields are dead | `last_contact_at` = NULL on all 14 deals; `deal_status` = 'on_track' on all deals incl. 4 dead ones. |
| Two DB copies diverge silently | deals.md cockpit block (synced 05.07 from suite prod) shows Lion = `indicative_offer`; local OneDrive dealroom.db shows `on_hold`. No defined sync path between OneDrive master and the Fly copy that cockpit mirrors and boardroom reads. |
| Half the schema was never adopted | 0 rows in deal_contacts, deal_emails, deal_meetings, deal_granola, deal_actions, deal_notes, deal_employees, deal_suppliers, deal_competitors, deal_scorecard_results, deal_manual_gates. |
| 5 of 18 CLI commands are stubs | draft-offer, draft-email, draft-nda, sync-granola, bench — never implemented; their jobs are done today by skills (/deal-doc, /call-prep) + MCP (email, Granola). |
| CDD restructure invisible to the tool | No concept of databook/RFI/slides versions, tie-out status, data-room section health, or the CDD (sections 01–04) vs FDD (05–07, Ebner Stolz) split. `deal_questions` holds 18 rows while the real RFI lives in versioned xlsx. |
| Rich data, no answers | 1.509 financial rows, 3.015 invoices, 1.396 customer-year rows in DB — but the UI opens with a portfolio table; no figure shows its source or as-of date. |
| Negotiation state has no surface | M1+M2 built and live in dealroom.db (2 strategies, 23 rounds, 21 profile claims, 9 lessons, 72 communication-trail rows; `tools/validate_negotiation.py` + tests shipped 08.07). Zero UI. |
| Known data bugs open | DR-BUG-025 (plan columns ingested as actuals — systemic), DR-BUG-020 (subaccounts capped at 10), DR-BUG-022 (Fox service_split missing → onepager charts empty), DR-BUG-026 (3 pre-existing test failures). |

**What v1 got right (keep, do not rebuild):** normalized schema keyed on `domain`, ALLEX read-only ATTACH, DATEV extraction + conflict detection, interactive valuation engine (waterfall, earn-out matrix — 548-line test suite), RFI generator + golden corpus, commercial/databook ingestion with tie-out, per-row `source` + `extracted_at` audit columns.

## 2. Design principles

1. **Answer first.** Every view opens with the decision-relevant statement; evidence is one click below. The landing page answers "what needs me today", the deal page answers "where does this deal stand, what did we agree, what's next, what's stale" — in one screen.
2. **One truth per fact.** Each fact has exactly one master: files = artifact master (databooks, models, LOIs), dealroom.db = state master (stage, terms, rounds, freshness), ALLEX pipeline.db = company identity, HubSpot = contact identity. Everything else is a mirror with a visible as-of.
3. **Freshness is computed, not remembered.** Staleness = deterministic mtime/version comparisons run by the tool. The tool tells Roman what is stale — never the reverse.
4. **Map the real July-2026 workflow.** Stages, artifacts and views mirror the restructured process: CDD = data-room sections 01–04 (Repuro/Claude), FDD/TDD/LDD = 05–07 (Ebner Stolz); versioned artifacts (`YYMMDD_{Codename}_..._vN`); LOI→DD→SPA→Notar timelines as tracked milestones.
5. **Track everything that moves.** Stage transitions, artifact versions, RFI status, terms, negotiation rounds — timestamped, queryable, with history.

## 3. Architecture decision: evolve the data layer, rebuild the workflow layer

**Decision: v2 is NOT a greenfield rewrite.** Keep dealroom.db (schema v8 → v9), the extraction/valuation/ingestion engine, and the test suite. Rebuild the presentation + process layer (dashboard views, freshness engine, artifact tracking, CDD/negotiation surfaces) and remove dead weight.

Rationale: (a) the hard, proven parts are the data layer — extraction, tie-out, valuation — and they carry 2.555 lines of passing-ish tests; (b) cockpit (`dealroom_sync.py`) and boardroom (`sources.py`, read-only) consume dealroom.db — a schema rewrite breaks two live modules for zero user value; (c) every v1 deficit found is in the workflow/surface layer, none in the data layer. Steelman for rebuild considered (clean answer-first design unconstrained by v1): rejected — the constraint that matters is the DB contract, and it is sound; the UI is self-contained HTML and can be rebuilt freely without a repo reset.

## 4. Keep / Fix / Remove

| Keep | Fix | Remove |
|---|---|---|
| Schema core + domain FK + ALLEX ATTACH | Stage data (integrity migration, §9) | CLI stubs: draft-offer, draft-email, draft-nda, sync-granola, bench |
| Extraction (data.py), model reader, valuation engine | DR-BUG-020/022/025/026 | Dead comms tables: deal_emails, deal_meetings, deal_granola(+archive), deal_actions, deal_notes, deal_manual_gates |
| Commercial + databook ingestion, tie-out | deal_questions ⇄ RFI xlsx sync (xlsx = master) | `src/generate/__init__.py` stub refs; tmp_*.py one-offs |
| RFI generator + golden corpus | DB sync path local ⇄ Fly (§9) | PLAN.md (superseded by ROADMAP) |
| Onepager (boardroom feeds off it) | Dashboard: rebuilt answer-first (§5) | — |
| Negotiation tables + validator | Wire validator into UI deliverable gate | — |
| deal_employees/suppliers/competitors schema (CDD scope — will fill from databooks) | — | — |

## 5. Workstream A — Answer-first surface

**A1. Landing = Attention panel** (replaces portfolio table as default; table stays one click away).
One line per active deal, grouped **Needs Roman / Waiting on seller / On track**:
`Fox — DD running · databook v5 current · 3 HIGH RFI open 12d · next: CDD/FDD 28.08 · 1 stale artifact`
Dead/on-hold deals collapsed at bottom with stage counts (absorbs open feature requests).

**A2. Deal page header = Answer card.** One screen answers: current stage + its evidence (e.g. signed LOI doc link), agreed terms summary (from terms ledger, §8), next milestone + owner + date, top open risks (from deal_dd_items), freshness state of all artifacts. Everything below is drill-down.

**A3. Source + as-of on every figure.** Inline chip on each number: `GuV 2025 · 260610_GuV_Fox.xlsx · extracted 14.06`. The data already exists (`source`, `source_file_id`, `extracted_at` per row) — v2 surfaces it. A figure whose source file is newer than its extraction renders with a stale marker.

**A4. Deal timeline.** Merged chronological view: stage transitions (new history table), artifact versions, negotiation rounds, RFI sent/answered events.

UI constraints: repuro-ci.css only (no bespoke styles), reuse existing component patterns, DEV-FIRST on localhost with Roman sign-off before deploy, validate_ci gate on views.

## 6. Workstream B — Freshness & trackability engine

**New table `deal_artifacts`**: id, domain, artifact_type (databook | rfi | slides | model | loi | offer | spa | fdd_report | nda | other), version, file_path, file_mtime, file_date (from YYMMDD prefix), status (current | superseded | final | stale), checks_json (error flag / tie-out result), registered_at, supersedes_id.
Populated by extending `ingest-docs`: parse the `YYMMDD_{Codename}_..._vN` convention, build supersession chains automatically. Data room (`Sorgfaltsprüfung/…`) is scanned **strictly read-only**.

**Deterministic freshness rules** (run on dashboard load + `DEALROOM.py fresh [--deal X]`):
1. **Extraction stale** — any deal_financials / deal_customers / deal_commercial source file mtime > its extracted_at.
2. **Artifact chain broken** — current RFI version older than current databook version; slides built from a superseded databook.
3. **Model inputs outdated** — newest GuV/BWA/SuSa in data-room section 04 newer than current model file.
4. **Data-room delta** — new/changed files in sections 00–08 since last scan (reuse /check-dataroom scan logic + JSON diffs).
5. **Stage evidence mismatch** — signed LOI registered but stage < loi_signed; DD artifacts exist but stage < due_diligence; strategy/rounds active but deal on_hold.
6. **Contact/activity decay** — derive last_contact_at from communication_trail + deal folder activity; flag active deals silent > N days (config).

Output: per-deal freshness report feeding the Attention panel and Answer card. Thresholds live in a config table, start simple.

**New table `deal_stage_history`**: domain, from_stage, to_stage, changed_at, changed_by, evidence_note. v1 only stores `stage_entered_at` — no history. Every stage mutation writes here.

## 7. Workstream C — CDD workspace (Fox + Mantis pilot)

Per-deal **DD tab** rebuilt around the restructured process:

- **Data-room health**: sections 00–08 of `Sorgfaltsprüfung/{company}/` — file count, newest file date, delta since last scan. CDD scope (01_Umsatz und Kunden, 02_Lieferanten, 03_Personal, 04_Finanzen) visually primary; 05–07 shown as FDD lane (Ebner Stolz) with engagement/fieldwork/report status. Read-only scan, hard rule.
- **Databook registry**: all versions from 5_DD with current/superseded status, error-flag + tie-out result per version (from checks_json), Roman sign-off marker.
- **RFI tracker**: **xlsx Fragenliste = master**; `rfi refresh` imports it into deal_questions → counts by priority + status, days outstanding, answered-vs-open per category. The 18-row deal_questions table becomes a live mirror, not a parallel truth.
- **Red flags**: deal_dd_items (21 Mantis rows exist) surfaced on the Answer card: risk level, mitigant, status. Source = databook findings; kept current at each databook version registration.
- **DD milestones**: LOI-defined timeline per deal (Unterlagen, CDD/FDD date, Rest-DD, SPA-Entwurf, Notar, Exklusivität) as dated milestones with owner — powers "next milestone" on the Answer card. Seeded from signed/agreed LOI Zeitplan.

**Pilot AC**: Fox + Mantis fully represented with real data — every artifact version in 5_DD registered, data-room sections live-scanned, Mantis CDD-v7 red flags visible, RFI counts match the live xlsx, a new data-room upload appears as a delta on next scan.

## 8. Workstream D — Negotiation tab + Stakeholders index + terms ledger

This absorbs **SPEC-negotiation-tool.md M3** (M1/M2 already live in dealroom.db).

- **Per-deal Negotiation tab**: current strategy briefing (memo_md rendered), position map (our_goals / their_goals ranked), rounds timeline (asked/given both sides, channel, outcome, self-rating), open objections/predictions with occurred-status, SELBST-CHECK block (open negotiation_lessons relevant to this counterparty), locked terms. All data exists today (2 strategies, 23 rounds, 10 predictions, 9 lessons).
- **Stakeholders index + person page** (the suite CRM view, per negotiation spec §3a): identity + HubSpot key, context links (deal/investor/advisor), profile claims with confidence + evidence quote, rounds across all contexts, communication trail with read-status. HubSpot stays system of record for contact identity.
- **Access gating**: owner-only via the suite TEAMS per-module rights (seller psych profiles must not be readable by advisors/Flo by default). Non-negotiable — GDPR guard from negotiation spec §6.9.
- **Validator wiring**: a strategy that fails `tools/validate_negotiation.py` cannot be marked deliverable in the UI.
- **New table `deal_terms` (terms ledger)**: domain, term_key, value_text/value_num, unit, status (proposed | agreed | locked | superseded), source_doc, agreed_at, note. Seeded from signed LOIs (Fox, Mantis) and agreed-unsigned LOIs (Cat, Mouse — status `agreed`, flips to `locked` at signature). Feeds: Answer card terms summary, negotiation locked-terms guard, and replaces deals.md prose as the queryable terms truth ("what did we agree with Schröcke on the earn-out cap?" = one lookup).

## 9. Workstream E — Data hygiene, stage integrity, DB sync

- **Stage integrity migration**: propose corrections as a diff for Roman's confirmation (never silent): Fox → due_diligence, Mantis → due_diligence, Lion → indicative_offer (from on_hold); verify all 14 against deals.md + folder evidence. Every correction writes deal_stage_history with evidence note.
- **Kill list** (per §4): remove 5 CLI stubs + drop/archive dead comms tables after a repo-wide grep confirms zero consumers. Commercial schema (employees/suppliers/competitors) stays — databooks will fill it.
- **Bug fixes**: DR-BUG-025 (plan columns → own period_type, fix at extraction not read layer), DR-BUG-020 (subaccount cap), DR-BUG-022 (ingest Fox service_split + customer split so onepager charts render), DR-BUG-026 (triage 3 failing tests: fix or delete stale assertions).
- **DB sync (decision needed)**: today local OneDrive dealroom.db is the write master, while the suite image on Fly carries a copy read by boardroom and mirrored by cockpit prod — and they have diverged (Lion). Recommendation: **local stays master** (all ingestion tooling is local: COM, OneDrive files); add (a) a deploy-time DB push, (b) a divergence check comparing row-counts + stage hashes local vs deployed with a visible warning, (c) a "data as of {sync time}" banner in the deployed UI. Promoting Fly to master (cockpit model) rejected for now: writes happen where the files are. Verify mechanics during M5 (open item inherited from negotiation spec §10).
- **deals.md**: stays Roman's narrative file; the cockpit-generated block continues as-is. v2 makes dealroom.db trustworthy enough that the block is correct; terms ledger removes the need to encode terms in prose for retrieval.

## 10. Schema changes (v8 → v9)

Added: `deal_artifacts`, `deal_terms`, `deal_stage_history`, `freshness_config` (thresholds), `deal_milestones` (DD timeline; or fold into deal_dd_items — build-time call).
Extended: `deal_questions` (+priority normalization, +source_version link to RFI artifact).
Dropped (after consumer grep): `deal_emails`, `deal_meetings`, `deal_granola`, `deal_granola_v1_archive`, `deal_actions`, `deal_notes`, `deal_manual_gates`, `deal_data` (legacy EAV, superseded by v1_archive).
Unchanged: everything cockpit reads (deals: code_name, deal_stage, status_note) and boardroom reads (deals + onepager cols + financials) — **zero breaking change for consumers** (verify with their tests in M1).
Migrations in `src/db.py` as always; `PRAGMA user_version = 9`; backup before migration (NEVER-DESTROY).

## 11. Milestones & test plan

Build execution: Sonnet sessions for the build (mechanical), Opus review at milestone gates. One `ai/PLAN-DR-V2-M{n}.md` per milestone with AC + validation results (v1 definition of done unchanged). Fox/Mantis real data = the test fixture for everything (test-against-real-data rule).

| # | Milestone | Core AC |
|---|---|---|
| **M1** | Truth & freshness foundation — schema v9, artifact registry + scanner, freshness rules 1–6, `fresh` CLI, stage history, stage-integrity diff (Roman confirms), bug fixes, kill list executed | `fresh --deal fox` report matches reality (manually verified); cockpit + boardroom test suites still green; pytest green incl. previously failing 3 |
| **M2** | Answer-first UI — Attention landing, Answer card, source/as-of chips, timeline | Roman sign-off on localhost; validate_ci pass; Fox page answers stage/terms/next/blockers/stale in one screen |
| **M3** | CDD workspace — data-room health (read-only), databook/RFI/slides registry + chain status, RFI xlsx import, red flags, DD milestones | Fox + Mantis pilot AC (§7); RFI counts == live xlsx; new upload appears as delta |
| **M4** | Negotiation tab + Stakeholders index + terms ledger + validator wiring + TEAMS gating | Lion strategy + 23 rounds render; Golland person page complete; terms seeded Fox/Mantis/Cat/Mouse; non-owner token sees no profiles |
| **M5** | Deploy & sync — suite deploy, DB push + divergence check + as-of banner, e2e test (ingest→fresh→UI), docs (ARCHITECTURE, ROADMAP, CLAUDE.md) updated | Deployed /deals == local data post-sync; divergence check fires on induced mismatch; docs current; committed + pushed |

Estimated effort: 5 focused build sessions. Each milestone independently shippable; order fixed (M2–M4 depend on M1 registry; M5 last).

## 12. Out of scope (deliberate)

- Email composer, NDA generation, Granola sync UI — skills + MCP already do this in sessions; a second implementation is drift.
- Cross-deal benchmarking (`bench`) — revisit only when >3 deals in DD simultaneously.
- Natural-language query box — a CLI session over dealroom.db already answers ad-hoc questions.
- Boardroom/investor view changes; new standalone CRM module (Stakeholders index IS the CRM per negotiation spec §3a); rebuilding CDD skills (v2 tracks their outputs, does not replace them).

## 13. Open decisions for Roman (batched)

1. **Evolve-not-rebuild** (§3) — confirm.
2. **Landing default = Attention panel**, portfolio table one click away — confirm.
3. **Kill list** (§4): 5 CLI stubs + comms/notes/gates tables — anything to keep?
4. **DB sync**: local master + deploy-push + divergence check (rec) vs promoting Fly to master — pick.
5. **Terms ledger seeding**: signed LOIs only, or also agreed-unsigned (Cat, Mouse) with status `agreed` (rec: both) — confirm.
6. **Stage corrections diff** (Fox/Mantis → due_diligence, Lion → indicative_offer, full 14-deal verification in M1) — pre-approve approach, individual diffs at M1.
