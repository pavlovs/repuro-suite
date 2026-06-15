# DEALROOM — Master Plan (SUPERSEDED)

> **This file is superseded by `ROADMAP.md` as of 2026-05-22.** Milestone overview, detailed specs, and status tracking are all in ROADMAP.md. This file is kept for historical reference only. Do not update.

## Vision

DEALROOM is the M&A execution layer for Repuro. ALLEX finds and qualifies targets. DEALROOM executes on them — financial analysis, valuation, offer generation, and communication — from first financials received through to signed LOI.

Long-term: a reusable execution workspace for any M&A searcher using ALLEX.

## Milestone Overview

| # | Milestone | Description | Status |
|---|-----------|-------------|--------|
| DR-M1 | Foundation | CLI skeleton, dealroom.db, DEALS_DIR → OneDrive, seed deals | ✅ |
| DR-M2 | Document Registry | ingest-docs: scan OneDrive deal folder, classify and register all files | ✅ |
| DR-M3 | Data Extraction | Claude-assisted extraction → deal_data (all categories) + conflict detection | ✅ |
| DR-M4 | Excel Model Builder | Populate template for new deals; read + reconcile existing models → deal_valuations | ✅ |
| DR-M5 | Deal Workspace Dashboard | Cockpit strip (velocity + conflicts), financials, internal deal screen tab | ✅ |
| DR-M6 | RFI Generator | Financial + commercial question list → Word + deal_questions table | ✅ |
| DR-M7 | Interactive Valuation Model | Live valuation engine + earn-out matrix + dashboard model tab | ✅ |
| DR-M8 | Company Overview | Deal overview landing page: company facts, map, financial timeline, owner profile | ✅ |
| DR-M9 | Investor One-Pager | Deal one-pager → PowerPoint, Claude-drafted, open topics flagged | ⬜ |
| DR-M10 | Email Composer | Intent-driven email draft, deal context, history stored | ⬜ |
| DR-M11 | Granola Sync | Pull meeting transcripts per deal → timeline in dashboard | ⬜ |
| DR-M12 | NDA Generator | NDA draft from German template, pre-filled with deal parties | ⬜ |
| DR-M13 | Cross-Deal Benchmarking | Compare all deals via deal_data; recurring %, concentration, margins | ⬜ |
| DR-M17 | Outside-In Canvas + `/deal-update` | Per-target strategic canvas via WebSearch + Opus → HTML; `/deal-update` slash command chains ingest-docs → extract → draft-canvas | ⬜ |

## Current State

**DR-M1 complete (2026-03-28).** `DEALROOM.py` CLI live. `dealroom.db` created with all 9 tables. 10 deals seeded. `deals` + `status` + `stage` + `note` commands functional. All stubs respond correctly. 17 pytest tests passing.

**DR-M2 complete (2026-03-29).** 353 documents registered across 7 deals. Ingest module live. 44 pytest tests passing.

**DR-M3 complete (2026-03-29).** Financial extraction from GuV/Bilanz/BWA/Excel model → deal_data. Conflict detection live. Risk flags. 73 pytest tests passing.

**DR-M4 complete (2026-03-29).** Excel model builder: new-deal template population + existing model reconciliation → deal_valuations. EBITDA bridge.

**DR-M5 complete (2026-03-29).** Deal workspace dashboard: portfolio + deal views. Cockpit strip, P&L tab, balance, model/valuation, documents, notes. Served on port 8090.

**DR-M6 complete (2026-03-30).** RFI Generator: golden corpus from registered RFI files, account-driven anomaly questions, conflict questions. `draft-rfi`, `rfi --mark-sent`, Open Topics dashboard tab. 86 pytest tests passing.

**DR-M7 complete (2026-04-01).** Interactive Valuation Model: live valuation engine replaces read-only Excel snapshot. Adjusted P&L (multi-entity consolidation, GF salary, manual adjustments), net debt, waterfall + earn-out matrix + pro-forma EBIT bridge. `scenario` CLI command. 115 pytest tests passing. DR-M16 (Interactive Model View) effectively delivered by DR-M7.

**DR-M8 complete (2026-04-03).** Company Overview: default deal landing page with company facts from ALLEX, Leaflet map with EBITDA-sized circle, financial timeline (revenue + adj. EBITDA), owner/seller profile, contact, investment thesis. Negative EBITDA risk flag. Offline map fallback. 121 pytest tests passing.

**DR-SV2 complete (2026-04-22).** Schema v2: EAV → 22 normalized tables. Stage taxonomy redesigned. Document status tracking. Scorecard config. Data migration (569 → 516+30+23 rows). All consumers rewritten. 126 pytest tests passing.

**DR-GC complete (2026-04-23).** Golden Corpus: 10 Roman-curated reference docs across 7 types (rfi, offer, nda, loi, dd, model, databook). Shared loader module. CLI health check. RFI generator updated. Gaps identified for Roman: email, onepager. 136 pytest tests passing.

## Process

Planning: run `/plan-milestone` (reads ROADMAP.md for scope)
Execution: run `/execute-milestone`

Full protocols: plan-milestone and execute-milestone slash commands

## Definition of Done (same gates as ALLEX)

1. `ai/PLAN-DR-M{n}.md` exists with non-empty `## AI VALIDATION RESULTS`
2. `pytest tests/` passes
3. CLI command ran live against real data
4. `ARCHITECTURE.md` updated if any design decision changed
5. One commit per milestone
