
# Repuro Lead Pipeline — Roadmap

Last updated: 2026-06-29.

---

## Delivered (M1–M23, M28–M29)

All core pipeline stages, outreach data model, Serienbriefe cohort ingest, and dashboard v2 letter review UI implemented. M24–M27 deferred to post-launch.

| Milestone | What it does                                                                                                                                                   | Status |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| M1        | Python env, CLI, profile schema, CompanyRecord model                                                                                                           | ✅      |
| M2        | WLW.de scraper → knowledge_base cache → 00_wlw_raw.csv                                                                                                         | ✅      |
| M3        | Ingest all sources → pipeline.db, dedup vs Serienbriefe (domain + name)                                                                                        | ✅      |
| M4        | Hard filters: dental, pharmacy, size, foreign                                                                                                                  | ✅      |
| M5        | Website scraper → scraped_text in pipeline.db                                                                                                                  | ✅      |
| M6        | AI classifier (Claude CLI + API fallback), keyword pre-filter, name-dupe pre-filter                                                                            | ✅      |
| M7        | Ownership enrichment: OffeneRegister (free) → OpenRegister (paid, A/B only)                                                                                    | ✅      |
| M8        | Ownership hard gate: confirmed subsidiary/PE → klass=S                                                                                                         | ✅      |
| M9        | Email enrichment: SMTP candidate test from owner name                                                                                                          | ✅      |
| M10       | Export: 36-col Serienbriefe Excel, outreach tracking cols in DB — Kompliment 2 fixed in M16                                                                    | ✅      |
| M11       | HTML dashboard: local server, write-back API, funnel, lead table, company card, C-review                                                                       | ✅      |
| M12       | Dedup audit: `audit-dedup` command, cross-check DB vs Serienbriefe, `--fix` mode                                                                               | ✅      |
| M13       | ALLEX branding, collapsible legend, D-reason fix, klass badges, HubSpot forward-compat                                                                         | ✅      |
| M14       | Serienbriefe cohort ingest: 367 BA records, granular outreach statuses, data model fix                                                                         | ✅      |
| M15       | Dashboard overhaul: 5-tab operating console (Performance, BA Prep, Requires Attention, Lead Table, Outreach Tracker)                                           | ✅      |
| M16       | BA Prep editing console: inline lead table, email/compliment edit, blocker run-dialog, manual lead add, compliment_2 DB column                                 | ✅      |
| M17       | BA Prep hardening: approved-for-sendout gate, action queue split, Serienbrief field preview + all fields editable, region mapping                              | ✅      |
| M18       | Data quality hardening: ORBIS title-case, umlaut restoration, anrede/salutation normalization, K1/K2/leistung backfill from Excel                              | ✅      |
| M19       | Test coverage: unit tests for classify, export, enrich, dashboard — 120 pure-logic tests, no API mocks                                                         | ✅      |
| M20       | Letter production readiness: Leistung category templates, editable letter template, dashboard UX fixes, DB lock fix, batch approve, impressum auto-fill        | ✅      |
| M21       | Impressum scraper + GF enrichment: /impressum integrated into scrape pass, enrich-gf command, 17/24 A/B records got gf_name                                    | ✅      |
| M22       | PDF Letter Export: single PDF with all approved letters, overflow detection, configurable sender branding (sender.json)                                        | ✅      |
| M23       | Letter Quality Gate + Text Hardening: PDF completeness gate, German umlaut restoration for AI text, compliment grammar fixes, dashboard/check-letter alignment | ✅      |
| M28       | Dashboard v2 shell + Review mode: sidebar nav, design system, per-record editor with "Was fehlt" checklist, filter chips (Fehlend/Prüfen/Gesellschafter), 33 UX fixes (PLAN-M28-V2-FIXES), QA agent 3-phase validation — 85 letter-ready records | ✅      |
| M29       | Dashboard v2 UX/UI redesign: ownership de-duplication, export gate + approval pessimism, `--v1` rollback flag, salutation auto-compute, single teal subnav bar, German labels. v2 promoted to default. | ✅      |
| M32       | Cloud deployment: Fly.io Dockerfile + fly.toml; GitHub Actions auto-deploy from `main`; push-db/pull-db sync scripts; `_ThreadedHTTPServer` for concurrent requests; empty-DB cold-start handling; `src/data/region_mapping.json` (486 cities extracted from Excel — removes runtime Excel dependency). SDK migration, job runner backend, and Pipeline trigger UI deferred (require Anthropic API key). | ✅      |

---

## Current State (2026-04-30) — ALPHA v2.0-alpha

**ALPHA phase started 2026-04-30.** M32 complete: cloud deployment infrastructure in place. Flo accesses dashboard via Fly.io URL once Roman runs `flyctl deploy` and uploads the DB. Canonical DB on Fly persistent volume; code auto-deploys from GitHub `main`.

### Dev/Prod workflow
- `main` branch = production (what Flo uses via `https://repuro-suite.fly.dev/allex/`). Deploy via `/deploy` skill. Never push breaking changes directly here.
- `dev` branch = active development. All code changes land here first, test locally, then merge to `main`.
- Promote: merge `dev` → `main`, bump `DASHBOARD_VERSION` in `dashboard.py`, GitHub Actions deploys automatically.
- Test locally without disrupting Flo: `python pipeline.py dashboard --serve --dev --port 8081`
- Changes since last deploy tracked in `ai/CHANGELOG.md`.

### DB concurrency
- SQLite DELETE journal mode + `busy_timeout=10000` — intentional, WAL disabled (OneDrive 3-file constraint).
- No undo/rollback yet — M27 (activity log + undo) now higher priority given two users writing.
- DB backup not yet automated — manual copy of `pipeline.db` before sessions recommended.

### Records
- 2,420 records in pipeline.db (ORBIS + WLW + Serienbriefe + 71 MANUAL)
- Classifications: A=101, B=312, C=14, D=513, E=4
- 408 already-approached (BA1–BA7), 367 with rich data (ground truth for backtest)
- 71 MANUAL records (pre-classified B): 57 ownership_gated, 23 review_needed, 2 ownership_enriched
- MANUAL field completeness: full_name/domain/klass 100%, gesellschafter_name 92%, city/region/street/gf_name/email <10%
- 553 scraped WLW records not yet classified (backlog)
- 466 scrape-failed records (mostly WLW dead domains)
- Test suite: 480 tests passing (`pytest tests/`)
- **Dashboard v2 is now default** (`python pipeline.py dashboard` serves v2; `--v1` for rollback). M29 complete.
- **Letter review UI feature-complete** (M28): 93 records with letter fields, 85 letter-ready, 8 salutation mismatches. QA agent validated 15/15 features passing.
- Filter chips in queue sidebar (Fehlend/Prüfen/Gesellschafter) replaced sort chips. Multiple UX fixes: field layout, status cards, queue width, Regen positioning, Leistung fields, Grund chip logic.

### Known Breaking Points (2026-04-27 audit)

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| BP1 | `ownership_review_needed` was a dead end — no recovery path | Fixed: three-column ownership review UI (Owner / Investigation / Action) with Resolve, Pass, Exclude buttons. Visual flash feedback on decisions. Detail panel shows ownership investigation block. Codex-reviewed 2026-04-27. | Fixed |
| BP2 | `enrich_email_batch` WHERE clause skips `ownership_review_needed` | Still open — even after manual resolution via dashboard, records may not re-enter email enrichment | Open |
| BP3 | `run-all` not implemented (prints "not yet implemented") | No single command to run post-classification pipeline end-to-end | Fixed — `_run_all_stages()` in pipeline.py: sequential filter → scrape → classify → enrich with per-stage timing output |
| BP4 | K1/K2 generated at export time, not as pipeline stage; ~30% fail rate on combined prompt, no retry | Silent incomplete exports | Fixed (M34) — compliments generated via `backfill-compliments` stage; export warns on missing K1/K2 instead of silently generating; K2-only retry pass for truncation |
| BP5 | `normalize` / `backfill` don't change pipeline_stage — no way to tell if a record has been through these steps | No readiness tracking | Open |
| BP6 | No completeness gate before approval — only checked at PDF export time | Approval of incomplete records | Mitigated: `isExportEligible()` gate in M29 — requires all fields filled + approved. Confirm dialog when blocking fields missing. |
| BP7 | 27 K2 compliments have structural grammar issues (missing verb) — detected by normalize but not auto-fixed | Broken letter text | Open |
| BP8 | OpenRegister self-referencing owners: company listed as own shareholder (e.g. MED Laborunion 23.6% of itself) — _parse_owners picks this as "majority" | Mitigated: _resolve_ubo natural-person fallback skips self-refs. _parse_owners itself not yet fixed. | Mitigated |
| BP9 | No API call log or UBO cache — every Resolve click fires fresh API calls, no dedup across targets with same parent | Credits wasted on duplicate lookups | Open |
| BP10 | MANUAL records missing address/contact fields — city 11%, street 4%, gf_name 1%, gf_email 1% | Cannot produce letters without address enrichment (normalize step) | Open |

---

## Roadmap — Next Milestones

| Milestone | Scope | Status |
|-----------|-------|--------|
| M24 | Classifier refactor — 5-thesis taxonomy (Full-Service / Installation / Specialty / Independent-Service / General-Distributor), keyword pre-scan module, decision-tree LLM prompt, deterministic post-LLM guardrails, 10 trap-paired few-shots. Spec: `ai/PLAN-M24.md`. Backlog reprocess deferred. | 📋 Planned |
| M25 | Scraper refactor — subpage discovery (link extraction primary, sitemap.xml fallback, hardcoded fallback); keyword-scored anchor parsing; `--force-refresh` flag. Spec: `ai/PLAN-M25.md`. | 📋 Planned |
| M26 | **MANUAL Briefaktion readiness + process hardening** — Phase 1 ✅: 71 MANUAL records letter-ready (>90% fill, 2026-04-28). Phase 2: 4 general hardening fixes so next batch of 100 reaches >90% without manual work: output shape validation (H1), external lookup match gate (H2), extraction failure reason logging (H3), cohort-scoped CLI defaults (H4). Spec: `ai/PLAN-M26.md`. | 🔄 Phase 2 |
| M27 | **Activity tracker backend** — `activity_log` table in pipeline.db (id/domain/actor/field/old_value/new_value/changed_at + 2 indexes), `log_activity()` in db.py, real `GET /api/activity` endpoint (replaces stub, supports `?domain=` + `?limit=`), PATCH handler logs per-field changes with actor from `?actor=` param. 9 tests passing. Undo button: deferred. Spec: `ai/PLAN-M27.md`. | ✅ |
| M28 | ✅ Delivered — see Delivered table above |  |
| M29 | ✅ Delivered — see Delivered table above |  |
| M30 | **Analyze mode + polish** — Funnel/Classes/Bottlenecks views respond to BA selector via `getFilteredRows()` (server-computed data used only when no BA selected), empty states added, actor selector radio in tweaks panel (Roman/Flo, persists to `allex_actor` in localStorage). Spec: `ai/PLAN-M30.md`. | ✅ |
| M31 | **Backtest harness** — `--backtest` CLI flag for every pipeline stage. Uses 408 already-approached records (BA1–BA7) as ground truth. Runs stage logic on a sample, compares output to existing data, reports match rate + divergences. Covers: scrape, classify, enrich-ownership, enrich-email, normalize, backfill-compliments. No golden dataset to maintain — the BA records ARE the dataset. | 📋 Planned |
| M34 | **Briefvorbereitung Kompliment-Logik & Defaults** — K1/K2 phrasing hierarchy in prompt (3-tier K1, 4-tier K2). About-page URL discovery (30+ suffixes in scraper). Category-driven Leistung/Mehrwerte defaults. Export-time compliment generation removed (warns instead). `compliment_guide.md` updated with Flo's verbatim cascade. Addresses BP4. Spec: `ai/PLAN-M34.md`. | ✅ |

---

## Future Integration (Blocked on Other Projects)

| Feature | Blocked on | Status |
|---------|-----------|--------|
| HubSpot sync — pull deal stage, contact, company into pipeline.db | Dealroom project stable + clear handoff point | Blocked |
| Granola sync — pull meeting summaries into deal view | HubSpot sync done first | Blocked |

## Delivered (Previously Deferred)

| Feature | Delivered in |
|---------|-------------|
| Per-record "Export as Serienbrief" button | M17 |
| Full BA batch review workflow (`--approved-only` export) | M17 |
| Compliment guide v2 — Best Practices Excel → compliment_guide.md | M18-session (pre-migration commit df9abcd) |
| Cloud Function email verification (Spamhaus PBL workaround) | M9 post-session (pre-migration commit 1d791b8) |

---

## DX — Developer Experience

| Item | Scope | Priority |
|------|-------|----------|
| DX1 — Hot reload | File watcher on `dashboard_v2.html` that rebuilds `_html_content` cache without full server restart. Eliminates 10s+ restart cycle per template change. | High |
| DX2 — `make dev` one-liner | Script or Makefile that runs `python pipeline.py dashboard --serve --port 8082 --v2` from the right directory. Removes command discovery friction every session. | High |
| DX3 — Changelog automation | Auto-generate `ai/CHANGELOG.md` entries from conventional commit messages (`feat:`, `fix:`) during `/deploy`. | Medium |
| DX4 — Frontend module split | Break `dashboard_v2.html` (4000+ lines) into separate CSS/JS files concatenated at build time. Enables isolated reasoning, better diffs, future testability. | Medium |
| DX5 — Smoke tests | Automated tests: template renders without JS errors, key DOM elements present, API endpoints respond. Catches 80% of regressions without manual clicking. Depends on DX4. | Low (after DX4) |

## Deferred (Nice-to-Have, Not Confirmed)

| Item | Reason deferred |
|------|----------------|
| Gelbe Seiten scraper | WLW + ORBIS sufficient for current scale |
| Dashboard blocker buttons — execute scrape/classify from browser | Risk of uncontrolled API spend; revisit when test coverage improves |
| OffeneRegister.de bulk download | Complexity vs benefit low at <500 A/B companies |
| Google Maps Places API | Lead quality lower than WLW; cost |
| Hunter.io email enrichment | SMTP pattern matching covers ~40%; Hunter $49/mo only for scale |
| A/B double-check (second Claude call) | Token cost; manual C-review covers gap |
| Multi-profile support | Only one client right now |
| SaaS/API layer | Long-term vision only |

---

## Open Issues (Known Bugs / Tech Debt)

Verified against codebase 2026-04-29.

| Issue | Severity | Status |
|-------|----------|--------|
| **Email SMTP verification blocked** — Spamhaus PBL (residential IP), port 25 blocked. Decision: export missing-email list for freelancer instead. | High | Deferred — email outsourced |
| **K1+K2 CLI truncation** — combined prompt too long, ~30% fail rate. K2-only retry works. | Medium | Mitigated (K2-only prompt) |
| **Classifier non-discriminating on thesis** — single-axis target_description, no way to distinguish Installation-Partner vs. Full-Service vs. Specialty. | High | 📋 Addressed by M24 |
| Classifier examples static — dashboard reclassifications don't feed back into few-shot | High | Partially addressed by M24; auto-harvest still open |
| Dedup: approached companies may slip through on domain change | Medium | Mitigated (M12 audit command) |
| No persistent API usage counters / call log | Medium | Open (BP9) |
| Knowledge base TTL (90d scrape, 180d ownership) not tested in production | Low | Open |
| Dashboard iframe: many German SME sites block framing (X-Frame-Options) | Low | Fixed — 4s timer-based fallback + "open in new tab" link (v2.0.2) |
| **`ownership_review_needed` dead end** — 23 records pending review, now actionable via dashboard | High | Fixed (BP1) — three-column review UI, Resolve/Pass/Exclude, Codex-reviewed |
| **`run-all` not implemented** — post-classification pipeline requires 5+ manual commands in sequence | High | Fixed (BP3) — `_run_all_stages()` wired |
| **No readiness stage** — normalize/backfill don't update pipeline_stage, no way to track completion | Medium | Open (BP5) |
| **27 K2 grammar issues** — missing verb detected by normalize but not auto-fixed | Medium | Open (BP7) |
| **PATCH whitelist too broad** — `pipeline_stage`, `is_subsidiary`, `is_pe_backed` writable without server-side transition checks | Medium | Open (Codex C4) |
| **Inline onclick XSS** — `escHtml` doesn't escape single quotes; parent names in `onclick` handlers could break JS or inject | Low | Open (Codex C6, localhost-only) |
| **"majority owner" label misleading** — `_parse_owners` selects largest share, not necessarily >50%; label should say "largest owner" when <50% | Low | Open (Codex C3) |
| **No parent_owners storage** — `_resolve_ubo` finds UBO behind holding company but doesn't store the holding's shareholder list; detail panel can't show multi-level drill-down | Medium | Open (Codex finding 3) |
| **Ownership provenance not tracked** — no DB column distinguishes whether gesellschafter_name came from ORBIS, OpenRegister, impressum, or manual entry | Low | Open (Codex finding 1) |

---

## Shared Access (Co-founder Dashboard)

**Implemented in M32: Fly.io cloud deployment.**

- Dashboard hosted at `https://repuro-suite.fly.dev/allex/` (unified Repuro Suite, Fly.io `fra` region)
- SQLite `pipeline.db` lives on a Fly persistent volume mounted at `/data` inside the container
- Auto-deploys from GitHub `main` branch via `FLY_API_TOKEN` secret
- Sync scripts: `scripts/push-db.sh` (upload local → Fly), `scripts/pull-db.sh` (download Fly → local)
- No LAN requirement — Flo accesses via URL from anywhere
- Pipeline jobs (classify/enrich/backfill) still triggered locally by Roman — cloud is view/edit only until Anthropic API key is available

**Revisit if**: co-founder needs to run pipeline commands or write back to DB. At that point, consider Turso (hosted SQLite, free tier, HTTP API) — but adds infrastructure overhead.

**Setup time**: ~30 minutes. Path change in settings.py + move files.

---

## Principles for Future Milestones

1. **One milestone = one commit set = one PLAN-M{n}.md**. No batch commits.
2. **DB-first**: all new data goes to pipeline.db. No intermediate CSVs.
3. **Dry-run always**: any command hitting external APIs needs `--dry-run`.
4. **Migration forward-only**: new DB columns via `ALTER TABLE ADD COLUMN` in `ensure_schema()`. Never drop or rename columns.
5. **Deal tracking lives in the Dealroom project** — ALLEX pipeline tracks the approach funnel (sourcing → export → outreach status). Post-send deal stage, financials, and meeting notes are the Dealroom's domain. HubSpot/Granola sync will bridge the two when ready.
6. **MCP tools for HubSpot/Granola** already connected in Claude Code — no new API libraries needed when that sync is scheduled.
