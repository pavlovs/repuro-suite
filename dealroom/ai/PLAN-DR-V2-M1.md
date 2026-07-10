# PLAN — DEALROOM v2 M1: Data layer v2 (local build)

*2026-07-10. Spec: SPEC-DEALROOM-V2.md rev 2 §3/§8/§9/§10/§11. Build mode: local sandbox (Roman 10.07: "build the dealroom v2 spec locally"); Fly cutover is a later, separate step with Roman.*

## Scope

1. **Schema v2** — `v2/schema.sql`, new DB file `data/dealroom_v2.db`. v1 `data/dealroom.db` is never written (NEVER DESTROY).
2. **Migration** — `v2/migrate_v1.py`: idempotent (drop+rebuild v2 file), copies good v1 data, applies stage corrections with `deal_stage_history` evidence rows, resolves Aqua, seeds `deal_terms` (NBO onward) + `deal_milestones` from deals.md-cited sources, absorbs `deal_documents` → `deal_artifacts`, exports `deal_data_v1_archive` → JSON archive.
3. **API server** — `v2/server.py` (FastAPI, port 8082 local): read views + authed write endpoints; X-Remote-User trust behind proxy (cockpit pattern); local dev = sandbox-labeled, default user roman.
4. **Consumer contract** — cockpit sync + boardroom queries run unchanged against v2 DB (regression test in `v2/tests/test_consumers.py`).

## Schema v2 (table set per spec §9)

- **New**: `deal_stage_history`, `deal_terms`, `deal_milestones`, `deal_artifacts` (absorbs deal_documents), `freshness_config`, `dataroom_scans`.
- **`deals`**: v1 columns minus `previous_stage` (→ stage_history) and `last_contact_at` (→ computed from communication_trail). All consumer/onepager/commentary columns unchanged.
- **Carried DDL as-is**: deal_financials, deal_model_params, deal_valuations, deal_commercial, deal_customers, deal_products, deal_invoices, deal_backlog, deal_suppliers, deal_employees, deal_competitors, deal_dd_items, deal_questions, stakeholders, stakeholder_links, profile_claims, negotiation_strategies, negotiation_rounds, negotiation_round_reviews, negotiation_lessons, negotiation_predictions, communication_trail, portfolio_meta; `deal_scorecard_config` → `scorecard_config`.
- **Not carried (kill list §10)**: deal_emails, deal_meetings, deal_granola(+archive), deal_actions, deal_notes, deal_manual_gates, deal_contacts, deal_data, deal_data_v1_archive (JSON export first), deal_scorecard_results. All 0 rows except v1_archive (569 → JSON).

## Stage corrections (individual diffs — Roman confirm in final report)

| Deal | v1 | v2 | Evidence |
|---|---|---|---|
| Fox | loi_signed | due_diligence | Ebner Stolz LDD/TDD/FDD engaged 02.06; data request out (deals.md) |
| Mantis | loi_signed | due_diligence | LOI signed 01.06; CDD v9 delivered 10.07 |
| Lion | on_hold | indicative_offer | Angebots-Update 260708_v1; 23 negotiation rounds live |
| Aqua | (missing/Swordfish-dead) | indicative_offer | Ind. offer ~07.05 (broker Quantum); resolve Swordfish domain='aqua' collision by company_name evidence |

## API endpoints (M1 set; M2+ extend)

Read: `/api/health`, `/api/attention`, `/api/deals`, `/api/deal/{code}`, `/api/deal/{code}/timeline`, `/api/terms`, `/api/fresh` (stub until M2).
Write (authed): `POST /api/deal/{code}/stage` (writes stage_history), `POST /api/deal/{code}/term`, `POST /api/deal/{code}/milestone`, `POST /api/push/artifacts`, `POST /api/push/dataroom-scan`, `POST /api/push/rfi`.
Auth: X-Remote-User honored only with `DEALROOM_TRUSTED_PROXY=1`; otherwise dev-sandbox default `roman`. Owner-only (negotiation/stakeholder data): `roman`.

## AC / verify

- [ ] migrate_v1.py runs green; row counts of carried tables == v1 counts; v1 file byte-identical after run
- [ ] stage corrections present with history evidence; Aqua resolved with evidence
- [ ] deal_terms seeded for Fox/Mantis (locked), Cat/Mouse (agreed), Lion/Aqua (proposed) — every row has source_doc
- [ ] consumer contract queries return expected shapes/rows (pytest)
- [ ] server starts; endpoints return migrated data (pytest via TestClient)

## AI VALIDATION RESULTS

2026-07-10 — build session (local, 6h loop):
- `python -m v2.migrate_v1` green. Carried counts == v1 (deal_financials 1509, invoices 3015, customers 1396, negotiation tables complete). deal_documents 782 → 684 artifacts (98 v1 double-registrations deduped, reported). deal_data_v1_archive → `data/archive/deal_data_v1_archive.json` (569 rows). v1 byte-untouched (stat assertion).
- Stage corrections applied with evidence rows: Fox/Mantis → due_diligence, Lion → indicative_offer, **Swordfish → Aqua** (company_name = HEGA-Medical GmbH verified in-DB; rename + revive to indicative_offer; valuation row domain='aqua' stays linked). Diffs for Roman confirm in final session report.
- deal_terms: 18 rows seeded, every row with source_doc. deal_milestones: 19 rows from LOI Zeitpläne.
- `pytest v2/tests/test_m1.py` → **23 passed** (migration integrity, kill-list absence, consumer contracts cockpit/boardroom, API round-trips incl. term supersede, artifact chain recompute, data-room delta, RFI mirror).
- Placeholder domains 'cat'/'wolf' remapped to real domains in child tables.
- NOTE: v1 DB received writes today from another session (deal_dd_items 21→29); migration is idempotent and will re-run at M6 for the freshest snapshot.
