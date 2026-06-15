# Repuro Lead Generation Pipeline — Master Plan

## Vision

A configurable, industry-agnostic lead generation engine. Currently scratching our own itch (German ambulatory medtech M&A targets), but built to be replicable for any industry or client. Core concept: define an **Industry Profile** (area, criteria, examples) → pipeline finds, qualifies, enriches, and exports structured outreach-ready leads.

Long-term trajectory: CLI tool now → Python package → DaaS/SaaS API layer.

## Project Goal

Build a cost-efficient, fully automated lead generation pipeline that:
1. Discovers German ambulatory healthcare distributors (Medizintechnik / Sprechstundenbedarf) via web scraping
2. Classifies them by M&A fit (A/B/C/D/E) using Claude AI
3. Validates ownership structure (private, not subsidiary, not PE-backed) as a hard gate
4. Enriches with contact data
5. Exports Serienbriefe-ready rows for Word mail merge

**Token efficiency is a first-class constraint throughout.** Every Claude API call must justify its cost.

## Industry Profile Concept

All pipeline behavior is driven by a JSON profile file. Swapping the profile changes the industry, the search terms, the classification criteria, and the export format — without touching the pipeline code.

```
profiles/
  medtech_germany.json    ← current Repuro profile
  [future profiles]       ← other industries, other clients
```

The pipeline is invoked with: `python pipeline.py <command> --profile profiles/medtech_germany.json`

## Target Profile (current: medtech_germany)

- **Geography**: Germany (focus), DACH optional
- **Employees**: 20–80 (platform A); 5–20 (add-on B)
- **Business model**: distribution + service mix for ambulatory practices (GP, surgeon, OB-GYN)
- **Ownership**: Privately held GmbH / GmbH & Co. KG, owner-operated — NOT subsidiary, NOT PE-backed
- **Not wanted**: Dental-only, pharmacy, hospital supply only, >100 employees, PE-backed, pure OEM

## Milestone Overview

| #   | Milestone                | Description                                                                                | Status |
| --- | ------------------------ | ------------------------------------------------------------------------------------------ | ------ |
| M1  | Infrastructure           | Python env, CLI skeleton, Industry Profile schema, CompanyRecord model, tests              | ✅      |
| M2  | WLW Scraper + KB         | SQLite knowledge base cache + WLW scraper → data/staging/00_discovered.csv                 | ✅      |
| M3  | Data Ingest              | Normalize WLW output + existing Excel; dedup against Serienbriefe (already-approached)     | ✅      |
| M4  | Pre-qualification Filter | Profile-driven hard filters: dental, pharmacy, size, subsidiaries                          | ✅      |
| M5  | Website Scraper          | Extract homepage + Leistungen + Produkte text per company                                  | ✅      |
| M6  | AI Classifier            | Claude API classification (haiku bulk, sonnet quality) with few-shot from profile examples | ✅      |
| M7  | Ownership Enricher       | A/B only: OffeneRegister (free, GF name) → OpenRegister.de (paid, Gesellschafter + %)      | ✅      |
| M8  | Ownership Hard Gate      | Confirmed subsidiary or PE-backed → reclassify to S (manual review, not D)                 | ✅      |
| M9  | Email Enricher           | A/B only: SMTP name candidates (8 patterns); anrede heuristic from owner name              | ✅      |
| M10 | Serienbriefe Exporter    | 36-column schema aligned to Word template; outreach tracking cols in DB; --via-cli support  | ✅      |
| M11 | HTML Dashboard           | Local HTTP server + write-back API; funnel, charts, lead table, company card + iframe, C-review | ✅      |
| M12 | Dedup Audit & Hardening  | `audit-dedup` command: cross-check DB vs Serienbriefe, `--fix` mode                            | ✅      |
| M13 | Dashboard UX Polish      | ALLEX branding, collapsible legend, D-reason fix, klass badges, HubSpot forward-compat          | ✅      |
| M14 | Serienbriefe Cohort Ingest | Full ingest of 367 Serienbriefe records with BA tags, granular outreach statuses, data model fix | ✅      |
| M15 | Dashboard Overhaul       | Operating console redesign: Performance / Current BA Prep / Requires Attention tabs             | ✅      |
| M16 | BA Prep Editing Console  | Inline-editable lead table, email/compliment edit, blocker run-dialog, manual lead add          | ✅      |
| M17 | BA Prep Hardening        | Approval gate, % complete, all Serienbrief fields editable, region mapping, Letter Preview      | ✅      |
| M18 | Data Quality Hardening   | ORBIS title-case, umlaut restoration, anrede/salutation, K1/K2/leistung backfill from Excel     | ✅      |
| M19 | Test Coverage Hardening  | Unit tests for classify, export, enrich, dashboard — 425 tests total                           | ✅      |
| M20 | Letter Production Readiness | Fix Leistung grammar, template config file, dashboard UX, batch approve, impressum auto-fill  | ✅      |
| M21 | Impressum + GF Enrichment | /impressum integrated into scrape pass; enrich-gf command; 17/24 A/B got gf_name             | ✅      |
| M22 | PDF Letter Export       | Single PDF with all approved letters, overflow detection, configurable sender branding (ALLEX SaaS)  | ✅      |
| M23 | Letter Quality Gate + Text Hardening | PDF completeness gate (skip incomplete), German umlaut restoration for AI text, compliment grammar fixes | ✅      |
| M24 | Classifier 5-Thesis Refactor | Thesis taxonomy + keyword pre-scan + decision-tree LLM prompt + deterministic guardrails. Spec: `ai/PLAN-M24.md` | 📋      |
| M25 | Scraper Subpage Discovery | Keyword-scored link extraction from homepage + sitemap.xml fallback + hardcoded fallback; `--force-refresh`. Spec: `ai/PLAN-M25.md` | 📋      |
| M26 | Backtest Harness | `--backtest` flag for all pipeline stages. 408 BA records as ground truth. Run stage, compare to known-good data, report match rate + divergences. Stages: scrape, classify, enrich-ownership, enrich-email, normalize, backfill-compliments. | 📋      |

Status: ⬜ = not started, 📋 = planned, 🔄 = in progress, ✅ = complete

---

## Current State (updated 2026-04-27)

- M1–M23 complete. 480 tests passing (`pytest tests/`).
- 2,420 records in pipeline.db (ORBIS + WLW + Serienbriefe + 71 MANUAL)
- Classifications: A=101, B=312, C=14, D=513, E=4
- 408 already-approached (BA1–BA7) with rich data — ground truth for M26 backtest
- 71 MANUAL records (pre-classified B, "Distributor" targets): 57 ownership_gated, 23 review_needed, 2 ownership_enriched
  - MANUAL records are mostly empty beyond identity + ownership: city 11%, street 4%, gf_name 1%, email 1%
  - Ownership review UI: three-column table (Owner / Investigation / Action) with Resolve, Pass, Exclude
  - Codex-reviewed 2026-04-27: 3 critical + 1 secondary fixed (all_gesellschafter on ORBIS path, reclassify_reason on Exclude, dash regex, no-match reason includes company name). 3 deferred (PATCH validation, XSS hardening, majority label).
  - Next steps: Roman reviews 23 pending records in dashboard, then continue pipeline (enrich-gf → normalize → backfill → export)
- 553 scraped records not yet classified (WLW backlog)
- Full roadmap with rationale: `ai/ROADMAP.md`
- **10 breaking points** identified (see ROADMAP.md): BP1 fixed (ownership dead end), BP8 mitigated (self-ref owners), BP9+BP10 new

**Note on legacy milestone docs**: `PLAN-M1.md` through `PLAN-M18.md` (and partially M19–M23) were authored in the pre-OneDrive repo. The `## AI VALIDATION RESULTS` section is empty in early milestone plans (e.g. `PLAN-M4.md`, `PLAN-M5.md`). These are retro imports — the DoD gate in item 1 below applies strictly from M24 forward.

---

## Definition of Done — A milestone is NOT complete until ALL of the following are true

This is a hard gate. Marking ✅ in the status table without satisfying every item is a process failure.

1. **`PLAN-M{n}.md` exists** in `./ai/` with all sections filled in, including a non-empty `## AI VALIDATION RESULTS` section.
2. **`pytest tests/` passes** — no regressions.
3. **The command runs live** — at minimum `--limit 5` against real data (not just mocked tests).
4. **`python pipeline.py status` shows the expected stage counts.**
5. **Design documents updated** — if the milestone changed prompt logic, output schema, DB fields, or API behaviour: `DESIGN.md` and/or `ARCHITECTURE.md` must be updated in the same commit. Not later.
6. **One commit per milestone** — implementation + tests + doc updates together. Batch commits across multiple milestones are a red flag that planning was skipped.

**Why this exists**: In March 2026 a session implemented M6–M10 in a single commit, ticked all checkboxes, and created zero plan files. DESIGN.md went stale. The downstream cost was a full documentation recovery session. This rule prevents recurrence.

---

## Process

Planning: run `/plan-milestone` — full protocol in `~/.claude/commands/plan-milestone.md`.
Execution: run `/execute-milestone` — full protocol in `~/.claude/commands/execute-milestone.md`.

---

## Cost Budget (per full pipeline run of ~500 companies)

- **Claude CLI** (classification, compliments, leistung): all AI calls via `claude.cmd --via-cli` (OAuth, no API key). Cost covered by Claude subscription, not per-token billing.
- **OpenRegister.de** (ownership): ~11 credits/company (1 autocomplete + 10 owners). A/B only. Cache: 180-day TTL — never pay twice.
- **OffeneRegister.de**: Free. Always use first before OpenRegister.
- **WLW scraper**: Free (public scraping with polite delays).
- **Email**: outsourced to freelancer (not automated). SMTP port 25 blocked from residential IP.
- **Total target**: <€50/month for full pipeline operation.

---

## Key Design Decisions

1. **Industry Profile drives everything**: Target criteria, search terms, classification examples, filter rules, export schema — all in `profiles/{name}.json`. Changing profile = changing industry.
2. **WLW.de is the primary discovery source**: Public search results scraped by profile-defined search terms. Existing Excel is secondary input + deduplication reference.
3. **Standard schema**: All source data normalizes to `CompanyRecord` dataclass before any processing.
4. **Pipeline state persisted in SQLite**: All stage data lives in `data/pipeline.db`. CSV files are input-only (`data/input/`) or final output only (`data/output/`). No intermediate CSV staging.
5. **Token efficiency**: Haiku for bulk classification. Batch and checkpoint. Skip already-processed records. Short, structured prompts.
6. **Few-shot examples drive classification**: `profiles/{name}.json` contains the examples array. Update it to retrain the classifier.
7. **Ownership is a hard gate, not a soft signal**: A/B company confirmed as subsidiary (>75% corporate ownership) or PE-backed → reclassify to S (not D). S = ownership-excluded, surfaced in dashboard for manual review. Never auto-export.
8. **Two-tier ownership enrichment**: OffeneRegister SQL API (free, GF names) first, then OpenRegister.de (paid, ownership %) only for A/B companies. No credits wasted on C/D/E.
9. **Idempotent commands**: Running any command twice produces the same result. Skip already-processed records.
10. **Output is Excel-compatible**: Final output matches the exact column structure of the `Serienbriefe` sheet.

---

## Files / Credentials Status

- [x] `OPENREGISTER_API_KEY` — configured in `.env`
- [x] Word template merge fields — confirmed and mapped to 36-col export schema (M10)
- [ ] Email enrichment solution — SMTP blocked from residential IP; decision: outsource to freelancer via export list
