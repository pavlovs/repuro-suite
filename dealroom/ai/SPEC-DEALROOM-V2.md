# SPEC — DEALROOM v2

*Rev 2, 2026-07-10 — Roman's decisions of 10.07 locked in (§0). Status: kill list (§10) awaiting Roman confirm; everything else approved for build. Author: RC. Evidence base: live dealroom.db dump 09.07, dealroom/ codebase, CDD skills + Fox/Mantis deal folders, SPEC-negotiation-tool.md v3, suite integration map.*

## 0. Locked decisions (Roman, 10.07)

1. **Rebuild both layers, separately.** Data layer rebuilt (clean schema, not v1-preserving); front-end rebuilt with full visual tie-in to the Repuro suite (repuro-ci.css design system, suite navigation, same look as cockpit/boardroom). Data layer first, front-end second.
2. **Landing default = Attention panel**; portfolio table one click away.
3. **Kill list** — detailed enumeration in §10, awaiting confirm.
4. **Fly is master.** dealroom.db lives on the Fly volume (cockpit model). Prod is the only DB Roman sees; all writes via authenticated API; local = dev sandbox only.
5. **Terms ledger starts at NBO sent** — negotiation begins there. Lifecycle: proposed → countered → agreed → locked (signature) → superseded.
6. **Stage corrections**: approach approved; individual diffs presented at M1.

## 1. Why v2 — diagnosis (evidence, 09.07)

| Finding | Evidence |
|---|---|
| Stage data does not match reality | Lion = `on_hold` since 2026-03-28 during live negotiation; Cat + Mouse = `indicative_offer` with LOIs versandfertig; Fox/Mantis = `loi_signed` while DD runs (Ebner Stolz engaged 02.06). |
| Status fields dead | `last_contact_at` NULL on all 14 deals; `deal_status`='on_track' on all, incl. 4 dead deals. Aqua (NBO submitted ~07.05) missing from dealroom.db entirely. |
| Two DB copies diverged silently | deals.md cockpit block (synced from Fly copy 05.07): Lion=`indicative_offer`; local OneDrive DB: `on_hold`. No defined sync path. **Resolved structurally by decision #4 — one DB, on Fly.** |
| Half the schema never adopted | 0 rows in 11 tables (contacts, emails, meetings, granola, actions, notes, manual_gates, employees, suppliers, competitors, scorecard_results). |
| 5 of 18 CLI commands are stubs | draft-offer/-email/-nda, sync-granola, bench — jobs done today by skills (/deal-doc, /call-prep) + MCP (email, Granola). |
| CDD restructure invisible | No databook/RFI/slides versioning, no tie-out status, no data-room section health, no CDD (01–04) vs FDD (05–07, Ebner Stolz) split. deal_questions: 18 rows while the real RFI lives in versioned xlsx. |
| Rich data, no answers | 1.509 financial rows, 3.015 invoices, 1.396 customer-years — UI opens with a table; no figure shows source or as-of. |
| Negotiation state has no surface | M1+M2 live in DB (2 strategies, 23 rounds, 21 claims, 9 lessons, 72 trail rows; validator + tests shipped 08.07). Zero UI. |
| Open data bugs | DR-BUG-025 (plan columns as actuals), DR-BUG-020 (subaccount cap), DR-BUG-022 (Fox service_split missing), DR-BUG-026 (3 failing tests). |

**Carried forward as code, not as schema:** extraction logic (DATEV mapping, conflict detection), valuation engine (waterfall, earn-out matrix), commercial/databook ingestion + tie-out, RFI generator + golden corpus, onepager generator. The algorithms are proven; they get a new storage backend.

## 2. Design principles

1. **Answer first.** Every view opens with the decision-relevant statement; evidence one click below. Landing answers "what needs me today"; deal page answers "where does this stand, what did we agree, what's next, what's stale" in one screen.
2. **One truth per fact.** Fly dealroom DB = state master (stage, terms, rounds, freshness, artifact registry). OneDrive files = artifact master (databooks, models, LOIs). ALLEX pipeline.db = company identity. HubSpot = contact identity. Every display shows source + as-of.
3. **Freshness is computed, not remembered.** Deterministic mtime/version comparisons; the tool tells Roman what is stale, never the reverse.
4. **Map the real July-2026 workflow.** CDD = data-room sections 01–04 (Repuro/Claude); FDD/TDD/LDD = 05–07 (Ebner Stolz); versioned artifacts (`YYMMDD_{Codename}_..._vN`); LOI→DD→SPA→Notar timelines as dated milestones; negotiation begins at NBO sent.
5. **Track everything that moves.** Stage transitions, artifact versions, RFI status, terms, rounds — timestamped, queryable, with history.
6. **Visually part of the suite.** repuro-ci.css tokens/components only; suite nav; no bespoke styling (v1's self-contained HTML style is retired).

## 3. Architecture (decision #1 + #4)

```
┌────────────── Fly (repuro-suite app) ──────────────┐
│  /deals  DEALROOM v2 module                        │
│    ├─ dealroom DB (volume, MASTER)                 │
│    ├─ API: read views + authed write endpoints     │
│    ├─ freshness engine (computes from DB state)    │
│    └─ TEAMS-gated negotiation/stakeholder views    │
│  cockpit ──reads──> volume DB (deal_mirror sync)   │
│  boardroom ──ro──> volume DB (investor view)       │
│  ALLEX pipeline.db (volume) <──ro ATTACH── /deals  │
└────────────────────────────────────────────────────┘
              ▲ authenticated HTTPS push
┌─────────────┴──────────────── local (Roman's machine) ─┐
│  DEALROOM CLI: extraction (COM/xlsx), folder scans,     │
│  data-room scans (read-only), RFI import                │
│  → parses OneDrive files locally, PUSHES payloads to    │
│    prod API. Local dealroom.db = dev sandbox ONLY,      │
│    labeled as such (cockpit precedent).                 │
└─────────────────────────────────────────────────────────┘
```

Consequences of **Fly-master**:
- **Writes via API only** (existing rule NO-DB-WRITE-WHILE-SERVED becomes structural). UI edits and CLI pushes share the same endpoints. Auth = existing suite mechanism (Caddy forward_auth + tokens), TEAMS per-module rights for gated views.
- **Ingestion stays local, storage goes remote.** Files and COM live on Roman's machine; every ingest command keeps its CLI UX (`DEALROOM.py extract --deal fox`) but the write backend becomes HTTP push. Repository-layer swap in code.
- **Scheduled freshness**: the local scan+push can ride the existing RepuroAgentLoop schedule (logon + 13:00) so prod freshness is current without anyone doing anything.
- **OneDrive-SQLite constraints disappear** for the master DB (no journal=DELETE requirement, no sync-corruption class, no conflict copies). Local sandbox keeps the old rules.
- **Divergence class eliminated**: cockpit block in deals.md and boardroom read the same live DB. deploys no longer snapshot data into the image (today boardroom reads a deploy-time copy — that path is retired).
- **Migration**: one-time lift of good v1 data (financials, invoices, customers, commercial, documents, valuations, model params, dd_items, questions, scorecard config, portfolio meta, ALL negotiation tables incl. Lion pilot) local → Fly at M1 cutover, with stage-correction diffs applied on the way (decision #6). Aqua added as a deal (currently missing).
- Accepted trade-off: no Fly = no deal data UI (same as cockpit today). CLI can pull a read-only local mirror on demand for offline analysis.

**Schema v2** — clean design, `domain` stays the universal FK, table set in §9. v1 schema is not preserved for its own sake; good data migrates, dead weight does not (§10).

## 4. Workstream A — Answer-first surface (front-end rebuild)

- **A1 Landing = Attention panel**, grouped **Needs Roman / Waiting on seller / On track**; one line per active deal: `Fox — DD running · databook v5 current · 3 HIGH RFI open 12d · next: CDD/FDD 28.08 · 1 stale artifact`. Dead/on-hold collapsed at bottom with stage counts. Portfolio table one click away.
- **A2 Deal page = Answer card**: stage + evidence link, agreed terms summary (ledger §7), next milestone + owner + date, top open risks, artifact freshness state. Everything else is drill-down tabs.
- **A3 Source + as-of chip on every figure**: `GuV 2025 · 260610_GuV_Fox.xlsx · extracted 14.06`; stale figures render marked.
- **A4 Deal timeline**: stage history + artifact versions + rounds + RFI events, merged chronologically.
- **A5 Suite tie-in**: repuro-ci.css only, suite nav/header, component reuse from cockpit/boardroom (REUSE-EXISTING-FORMATS). DEV-FIRST on dev URL with Roman sign-off before deploy; validate_ci gate.

## 5. Workstream B — Freshness & trackability engine

- **`deal_artifacts`** (absorbs v1 deal_documents into one registry): domain, artifact_type (databook | rfi | slides | model | loi | nbo | spa | fdd_report | nda | dataroom_file | other), version, file_path, file_mtime, file_date (YYMMDD prefix), status (current | superseded | final | stale), checks_json (error flag / tie-out), supersedes_id, registered_at. Local scanner parses the `YYMMDD_{Codename}_..._vN` convention and pushes; Sorgfaltsprüfung scanned **strictly read-only**.
- **Freshness rules** (server-side, deterministic; run on view load + scheduled push):
  1. Extraction stale — source file mtime > extracted_at of its rows.
  2. Artifact chain broken — current RFI older than current databook; slides from superseded databook.
  3. Model inputs outdated — newest GuV/BWA/SuSa in data-room section 04 newer than current model.
  4. Data-room delta — new/changed files in 00–08 since last scan (reuse /check-dataroom scan logic).
  5. Stage-evidence mismatch — signed LOI registered but stage < loi_signed; DD artifacts but stage < due_diligence; active rounds but deal on_hold.
  6. Activity decay — last_contact derived from communication_trail; active deals silent > N days flagged.
- **`deal_stage_history`**: every stage mutation logged (from, to, at, by, evidence). Thresholds in `freshness_config`.

## 6. Workstream C — CDD workspace (Fox + Mantis pilot)

- **Data-room health**: sections 00–08 per deal — file count, newest date, delta since last scan; CDD scope 01–04 visually primary; 05–07 as FDD lane (Ebner Stolz: engaged/fieldwork/report status).
- **Databook registry**: all versions with current/superseded, error-flag + tie-out per version, Roman sign-off marker.
- **RFI tracker**: xlsx Fragenliste = master; `rfi refresh` imports → counts by priority/status, days outstanding. DB is a mirror, not a parallel truth.
- **Red flags**: deal_dd_items surfaced on the Answer card (risk level, mitigant, status), refreshed at each databook registration.
- **DD milestones**: LOI Zeitplan as dated milestones (Unterlagen, CDD/FDD, Rest-DD, SPA-Entwurf, Notar, Exklusivität) — powers "next milestone".
- **Pilot AC**: Fox + Mantis complete with real data — every 5_DD artifact version registered, data rooms live-scanned, Mantis v8 red flags visible, RFI counts match live xlsx, new upload appears as delta on next scan.

## 7. Workstream D — Negotiation tab + Stakeholders index + terms ledger

Absorbs SPEC-negotiation-tool.md **M3** (M1/M2 already live in DB).

- **Per-deal Negotiation tab**: strategy briefing (memo_md), position map (our_goals/their_goals), rounds timeline (asked/given both sides + self-rating), open objections/predictions, SELBST-CHECK (open lessons for this counterparty), locked terms. `validate_negotiation.py` wired: FAIL ⇒ not markable as deliverable.
- **Stakeholders index + person page** (suite CRM view per negotiation spec §3a): identity + HubSpot key, context links, claims with confidence + evidence, rounds across contexts, communication trail with read-status.
- **Access**: owner-only via TEAMS per-module rights — on Fly-master this is non-negotiable before the tab ships (seller psych profiles, GDPR guard §6.9 of negotiation spec).
- **`deal_terms` ledger — from NBO onward (decision #5)**: domain, term_key, value, unit, status (proposed | countered | agreed | locked | superseded), source_doc, changed_at, note. Seeded for every deal with an NBO out: **Fox, Mantis (locked from signed LOIs), Cat, Mouse (agreed, flip to locked at signature), Lion (live proposed/countered history), Aqua (proposed)**. Feeds Answer card, negotiation locked-terms guard, and replaces deals.md prose as the queryable terms truth.

## 8. Workstream E — data hygiene & stage integrity

- **Stage corrections at M1 migration** (approach approved): Fox → due_diligence, Mantis → due_diligence, Lion → indicative_offer; all 14 verified against deals.md + folder evidence; Aqua inserted. Each as an individual diff for confirm; each writes stage history with evidence note.
- **Bug fixes carried into the rebuild**: plan columns get their own period_type (DR-BUG-025 fixed at extraction), subaccount cap removed (DR-BUG-020), Fox service_split + customer split ingested (DR-BUG-022), failing tests triaged (DR-BUG-026).
- **deals.md**: stays Roman's narrative file; the cockpit-generated block keeps working (same DB, now guaranteed fresh). Terms ledger removes the need to encode terms in prose for retrieval.

## 9. Schema v2 table set

Core: `deals` (slim: domain, code_name, company ref, stage, status, folder_path, thesis), `deal_stage_history`, `deal_terms`, `deal_milestones`, `deal_artifacts`, `freshness_config`, `dataroom_scans`
Financial: `deal_financials`, `deal_model_params`, `deal_valuations`
Commercial (CDD): `deal_commercial`, `deal_customers`, `deal_products`, `deal_invoices`, `deal_backlog`, `deal_suppliers`, `deal_employees`, `deal_competitors`
DD: `deal_dd_items`, `deal_questions`
Negotiation/CRM (unchanged, migrated as-is): `stakeholders`, `stakeholder_links`, `profile_claims`, `negotiation_strategies`, `negotiation_rounds`, `negotiation_round_reviews`, `negotiation_lessons`, `negotiation_predictions`, `communication_trail`
Meta: `scorecard_config`, `portfolio_meta`
Detailed DDL at M1 plan (`PLAN-DR-V2-M1.md`). Consumer contract: cockpit sync (code_name, stage, note) and boardroom reads (deals + onepager cols + financials) re-pointed to the volume DB with unchanged field semantics — their test suites are the regression gate.

## 10. Kill list — detailed (decision #3, awaiting confirm)

**CLI stubs removed (never implemented, print "not implemented"):**

| Command | Was meant to do | Why dead | What does the job today |
|---|---|---|---|
| `draft-offer` (DR-M8) | Generate indicative offer .docx | Never built; offers are template-copied + edited | `/deal-doc` skill + golden templates + Codex gate |
| `draft-email` (DR-M10) | Intent-driven email drafts | Never built; drafting needs voice + thread context | Email MCP in sessions + Roman voice template |
| `draft-nda` (DR-M12) | NDA from template | Never built | `/deal-doc` + NDA template |
| `sync-granola` (DR-M11) | Pull meeting transcripts into DB | Never built; 0 meetings stored ever | Granola MCP live in sessions (/call-prep, CDD) |
| `bench` (DR-M13) | Cross-deal benchmark report | Never built | Portfolio view; revisit if >3 deals in DD at once |

**Tables NOT carried into schema v2 (all 0 rows unless noted):**

| Table | Why dead | Replacement |
|---|---|---|
| `deal_emails` | Email never stored here | Outlook/MCP; communication_trail tracks negotiation-relevant items |
| `deal_meetings`, `deal_granola`, `deal_granola_v1_archive` | Meeting intelligence never landed in DB | Granola MCP session-side; key outcomes → rounds/notes in negotiation tables |
| `deal_actions` | Task tracking never adopted | Cockpit is the execution master — duplicating it here = drift |
| `deal_notes` | Never used | deals.md narrative + cockpit |
| `deal_manual_gates` | IC gates never used | deal_stage_history + cockpit verdicts |
| `deal_contacts` | Never populated | `stakeholders` + `stakeholder_links` (CRM spine) + HubSpot as identity master |
| `deal_data` (legacy EAV, 0 rows) | Superseded by normalized tables in v1 already | — |
| `deal_data_v1_archive` (**569 rows**) | Frozen migration archive | **Export to JSON in the deal folder archive before drop** (no data loss, just not in the live DB) |
| `deal_scorecard_results` | Never persisted (0 rows) | Scorecards compute live from deal_commercial/financials; `scorecard_config` (11 metrics) IS carried |

**Kept despite 0 rows**: `deal_employees`, `deal_suppliers`, `deal_competitors` — CDD databook outputs (Personnel/Supplier tabs exist in the databooks); the CDD workspace will fill them.

**Files removed**: `tmp_*.py` one-offs (7), `src/generate/__init__.py` stub refs, `ai/PLAN.md` (superseded by ROADMAP).

**The confirm needed from Roman**: (a) the two replacement calls — contacts→stakeholders and cockpit-owns-actions; (b) archive-then-drop for deal_data_v1_archive; (c) anything on the lists above he wants kept.

## 11. Milestones & test plan

Data layer first, front-end second (decision #1 "separately"). Sonnet builds, Opus gates. One `ai/PLAN-DR-V2-M{n}.md` per milestone (v1 definition of done unchanged). Fox/Mantis real data = the fixture throughout.

| # | Milestone | Core AC |
|---|---|---|
| **M1** | **Data layer v2 on Fly** — schema v2 DDL, volume DB, authed read/write API, one-time migration (incl. negotiation pilot data + stage-correction diffs + Aqua), consumers repointed (cockpit sync, boardroom), kill list executed, ALLEX ATTACH verified on Fly | Prod API serves migrated data; cockpit block + boardroom output unchanged (their tests green); stage diffs confirmed by Roman; local labeled sandbox |
| **M2** | **Ingestion + freshness pipeline** — local CLI adapters (extract, ingest-docs→artifact scanner, ingest-databook, rfi refresh, data-room scan) push via API; freshness rules 1–6 server-side; `fresh` report + API; optional scheduled scan via RepuroAgentLoop | Fox end-to-end: local scan → prod freshness report manually verified correct; DR-BUG-020/022/025 fixed in new pipeline |
| **M3** | **Front-end shell, answer-first** — repuro-ci.css + suite nav, Attention landing, Answer card, source/as-of chips, timeline | Roman sign-off on dev URL (DEV-FIRST); validate_ci pass; Fox page answers stage/terms/next/blockers/stale in one screen |
| **M4** | **CDD workspace** — data-room health, databook/RFI/slides registries + chain status, RFI import, red flags, DD milestones | Fox + Mantis pilot AC (§6); RFI counts == live xlsx; new upload shows as delta |
| **M5** | **Negotiation tab + Stakeholders index + terms ledger** — negotiation M3, deal_terms seeded NBO-onward (Fox/Mantis/Cat/Mouse/Lion/Aqua), validator wiring, TEAMS gating | Lion strategy + 23 rounds render; Golland person page complete; non-owner token sees no profiles; terms queryable |
| **M6** | **Hardening & cutover** — e2e (scan→push→fresh→UI), decommission v1 dashboard + deploy-time DB snapshot path, docs (ARCHITECTURE, ROADMAP, CLAUDE.md, suite/MODULES.md, CHANGELOG) | e2e green; old paths removed; docs current; committed + pushed + deployed |

Estimated effort: 6 build sessions. Order fixed; M3–M5 depend on M1/M2.

## 12. Out of scope (deliberate)

Email composer, NDA generation, Granola sync UI (skills + MCP do this); cross-deal benchmarking (revisit >3 simultaneous DDs); NL query box (CLI session over the API covers ad-hoc questions); boardroom changes; separate CRM module (Stakeholders index IS the CRM); rebuilding CDD skills (v2 tracks their outputs).

## 13. Open items

1. **Kill list confirm** (§10) — the last gate before M1 build.
2. M1 build-time calls: exact DDL, API endpoint shapes, volume sizing — in PLAN-DR-V2-M1.md.
