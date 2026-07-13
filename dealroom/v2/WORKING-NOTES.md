# DEALROOM v2 build — WORKING NOTES (session 2026-07-10, 6h agentic loop)

**Re-read this file after any compaction. Never re-derive.**

## 13.07 — UI REJECTED, rebuild screen-by-screen (read this first)
Roman rejected the M3–M5 UI wholesale ("v0.2 instead of v2, AI slop"). Data
layer (M1/M2 + tests) stands. Restated goal (confirmed by Roman 13.07):
- DEALROOM = workspace where deal work HAPPENS (CDD review, IC prep, financial
  modelling, negotiation) on the one-truth DB. The deal page IS the IC view:
  answer first, then progressively deeper drill-downs.
- Landing = v1 Portfolio View ported 1:1 (golden reference: src/templates/
  dashboard.html + sections/portfolio.js — served VERBATIM, never reinterpreted).
- NO Attention tab (cockpit owns "what needs me"); freshness = badges later.
- English throughout. Units in column headers/footnotes, NEVER in cells.
  Every visible string is product copy — no builder meta-remarks.
- Terms ledger UI: NOT built here — a separate agent builds it on v1; v2 keeps
  the /api/terms endpoint only.
- Process: ONE screen → Roman sign-off → next (FIRST-SCREEN-SIGNOFF). No
  unattended UI fan-out. validate_ci passing ≠ visual sign-off.
Screen 1 (portfolio port, v2/ui_portfolio.py) built + verified 13.07 — old
v2.ui/v2.ui_workspace/v2.uikit UNREGISTERED (delete when rebuild completes);
their page tests skip-marked. Screen 2 = deal answer card (IC pyramid) — only
after Roman signs off Screen 1.

## Mission
Build SPEC-DEALROOM-V2.md (rev 2, locked) **locally** as a complete-feeling product: data layer v2 + migration + answer-first UI + CDD workspace + negotiation tab + freshness engine. Suite CI tie-in (repuro-ci.css). No Fly deploy this session — local = sandbox, labeled. Roman reviews on local dev URL.

## Scope cut (6h realism, stated in final report)
- IN: M1 data layer+migration, M2 freshness engine + artifact/data-room scanner, M3 answer-first UI, M4 CDD workspace, M5 negotiation tab+stakeholders+terms, M6 e2e+docs.
- OUT (deferred to Fly cutover): COM extraction adapters pushing via HTTP (v1 CLI keeps working locally), Fly deploy itself, supervisord/Dockerfile change, cockpit/boardroom repointing (compat: v2 DB keeps their query contracts working — verified by test).
- Kill list §10: executed as "not carried into v2 DB" — v1 DB NEVER touched (NEVER DESTROY). deal_data_v1_archive (569 rows) exported to JSON before being left behind.

## Fixed facts (verified this session)
- v1 DB: `dealroom/data/dealroom.db` (root dealroom.db = 0-byte stub). Backups exist incl. bak-ddstate-20260710.
- v2 DB: `dealroom/data/dealroom_v2.db` (NEW file; migration re-runnable/idempotent — delete+rebuild).
- pipeline.db (ALLEX, ro ATTACH): `C:\Users\X1\Documents\CLAUDE_COWORK\repuro-data\pipeline.db`
- Prod topology: suite Caddy `/deals/*` → forward_auth cockpit `/api/authz?module=dealroom` (ro users blocked from non-GET at proxy) → reverse_proxy :8082 with X-Remote-User. supervisord runs `DEALROOM.py dashboard --serve --port 8082` today; v2 server = drop-in replacement at cutover.
- fly.toml env already has DEALROOM_DB_PATH=/data/dealroom.db (volume).
- Consumer contracts (regression-tested in v2 tests):
  - cockpit sync: `SELECT code_name, deal_stage, status_note FROM deals`
  - boardroom funnel: `SELECT code_name, deal_stage, sector, location, ebitda_m_override, strategic_fit FROM deals WHERE deal_stage IN ('valuation_rfi','indicative_offer')`
  - boardroom live: `SELECT company_name, code_name, deal_stage, rev_m_override, ebitda_m_override, ev_m_override, multiple_override FROM deals WHERE deal_stage IN ('loi_signed','due_diligence','contract_negotiation','closed')`
  - boardroom KPIs: COUNT/SUM(ev_m_override) over same stage buckets.
- CI: `context/repuro-ci.css` (106 lines) — tokens --ci-*, --stage-*, classes .card/.tile/.btn/.badge/.badge--stage/.section-band/.label/.figure. Boardroom inlines it verbatim in templates/shell-top.html (pattern to follow). Stage colors incl. --stage-loi_negotiation.
- Boardroom = FastAPI + templates/ (shell-top/shell-bottom + sections), trusts X-Remote-User. Cockpit = FastAPI. v2 = FastAPI + uvicorn.
- v1 full DDL: scratchpad/v1_schema.sql (also re-dumpable via dump_v1_schema.py there).

## Migration decisions (evidence in deals.md read 2026-07-10)
- Stage corrections (each → deal_stage_history row with evidence; diffs listed in final report for Roman confirm):
  - Fox loi_signed→due_diligence (Ebner Stolz engaged 02.06)
  - Mantis loi_signed→due_diligence (LOI 01.06, CDD v9 delivered 10.07)
  - Lion on_hold→indicative_offer (updated offer 260708_v1; 23 live rounds)
  - Cat/Mouse stay indicative_offer (LOIs versandfertig, not signed) — per spec §8 only 3 corrections.
- Aqua: deals.md = HEGA-Medical GmbH (Rolf Hommel), ind. offer ~07.05 broker Quantum, mgmt meeting 11.06. DB has domain='aqua' code_name='Swordfish' stage=dead — CHECK Swordfish company_name before insert: same company → rename+revive with evidence; different → insert Aqua (domain NULL if unknown, never fabricate).
- deals v2 columns: v1 minus previous_stage (→stage_history) + last_contact_at (→computed). Keep ALL consumer/onepager/bm_/thesis_ cols unchanged.
- deal_documents (782 rows) → absorbed into deal_artifacts.
- deal_terms seed (status per spec §7; German values; source_doc cited):
  - Fox locked: upfront 1.600 K€ (4,5x), EO 300 K€, total ≤1.900 K€ (5,3x) — src signed LOI ~26.05 (deals.md)
  - Mantis locked: total ≤5.965 K€ incl. Rückbeteiligung 500 K€ — src signed LOI 01.06
  - Cat agreed: Sofort brutto 3.400 K€ abzgl. NFV 31.12.25; EO je 26+27: 2,75€/1€ op. EBIT >625 K€, Cap 1.090 K€ → max 2.557,5 K€; total max 5.957,5 K€; EO auf Repuro-Ebene garantiert (Var. B) — src Schröcke-Mail 30.06 + LOI v7 03.07
  - Mouse agreed: Sofort 2.000 K€ (Basis 488 K€ EBIT 2025, ±10 K€/5x vs JA); EO bis 750 K€ (3x über 450 K€ Ø-EBIT 26/27 nach Tantiemen, Cap 700 K€) — src LOI vS 03.07
  - Lion proposed: from latest deal_valuations row + note re open points (135/140 Tantieme, Staffelung, +1 Kündigungsschutz) — src 260708 Angebots-Update v1
  - Aqua proposed: EV-Range 3,0–4,0 M€ (4,1–5,5x 3J-Ø adj. EBITDA) — src deals.md/ind. offer ~07.05
- Milestones seed: Cat (Sign 24.07, Unterlagen 31.07, Workshop Chemnitz Mitte Aug, CDD/FDD 28.08, Rest-DD 14.09, SPA 18.09, Notar 01.10, Exkl. 08.10); Mouse (Sign 10.07, Unterlagen 31.07, JA 31.08, CDD/FDD 11.09, DD 02.10, SPA 09.10, Notar Okt=NULL date note, Exkl. 30.10); Fox (Notar 21.08); Mantis (CDD-Workshop 14.07, Notar 28.08). NEVER cross-contaminate deals (Mouse v1 had Cat contamination).

## Access rules
- Owner-only (negotiation/stakeholders): user=="roman" (+"florian"? NO — seller psych profiles = Roman only per negotiation spec §6.9; OWNERS={"roman"}).
- Local dev: no proxy → default user "roman", sandbox banner shown.
- Sorgfaltsprüfung folders: STRICTLY read-only (scanner never writes there).

## Layout
- dealroom/v2/: schema.sql, db.py, repo.py, freshness.py, server.py, migrate_v1.py, scanner.py, templates/, tests/
- Plans: ai/PLAN-DR-V2-M1.md (+M2..M6 as built). Run server: `python -m v2.server --port 8082` from dealroom/ (or v2/server.py path exec).
- Tests: dealroom/v2/tests/ — run `python -m pytest v2/tests/` from dealroom/ with venv? v1 uses .venv — check `python` works with fastapi; else pip install fastapi uvicorn httpx into .venv.

## Progress log (append per milestone)
- [x] Recon + M1 plan
- [x] M1 data layer + migration (23 tests) — commit 6f5c5de
- [x] M2 scanner + freshness (30 tests) — verified live on Fox/Mantis
- [x] M3 answer-first UI — visual pass, validate_ci R2/R3/R4=0
- [x] M4 CDD tab + M5 negotiation/stakeholders/terms — owner-gating verified
- [x] M6 e2e (34 tests), docs (ROADMAP v2 block, CLAUDE.md v2 section), final rebuild
- Mid-session v1 drift handled: §12 negotiation tables + 'executing' status + closed_reason (other sessions were writing v1 concurrently — counts in plans reflect final snapshot)
- Lion terms reseeded from negotiation locked_terms (3.425 K€ Closing agreed 16.06; R1 2.500 K€ superseded)
- FOUND (report to Roman): Mantis workshop file sits in Fox folder root (260714_Endoberatung_Workshop_vS.xlsx) — cross-deal contamination in OneDrive, not fixed (not my file to move)
