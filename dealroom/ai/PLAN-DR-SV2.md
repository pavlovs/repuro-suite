# DR-SV2: Schema v2 — Normalized Tables

## Summary

Full schema redesign from EAV (`deal_data`, 569 rows) to 22+ normalized tables. Replaces the single `deal_data` table with purpose-built tables for financials, commercial metrics, customers, backlog, employees, suppliers, competitors, contacts, manual gates, DD items, and deal scorecard. Aligns stage taxonomy to DEAL_STAGE_REDESIGN.md. Adds document status tracking with category-specific progressions. Adds configurable stage gates. All consuming code (data.py, model.py, valuation.py, dashboard.py, rfi.py, DEALROOM.py) rewritten.

**Done when**: all 22+ tables exist, 569 `deal_data` rows migrated, old tables archived, all consumers use new schema, dashboard renders, extraction writes to `deal_financials`.

## Locked decisions

1. **Fully normalized**: no more EAV. Every data category has a typed table with proper columns and indexes.
2. **Gesamtleistung/revenue split**: separate `line_item` values in `deal_financials`. CAGR always on gesamtleistung. Critical fix for accuracy.
3. **DATEV konto_nr preservation**: 4-digit account codes stored in `deal_financials.konto_nr` during extraction.
4. **Stage taxonomy**: `financials_received`→`valuation`, `offer_preparation`→`valuation`, `offer_negotiation`→`offer`, `offer_sent`→`offer`.
5. **Doc status progressions**: Internal (draft→reviewed→approved), Bilateral (draft→sent→negotiation→signed), RFI (draft→sent→partially_answered→answered).
6. **Risk flags computed, not stored**: `compute_risk_flags()` returns a list, no longer writes to DB.
7. **Idempotent migrations**: all CREATE IF NOT EXISTS, ALTER with PRAGMA table_info checks, INSERT OR IGNORE.
8. **Archive, don't delete**: `deal_data` → `deal_data_v1_archive` (569 rows), `deal_granola` → `deal_granola_v1_archive`.

## Plan

### Step 1 — Schema: add new tables + ALTER existing tables in db.py
- 13 new tables: deal_financials, deal_commercial, deal_customers, deal_backlog, deal_employees, deal_suppliers, deal_competitors, deal_contacts, deal_manual_gates, deal_dd_items, deal_meetings, deal_scorecard_config, deal_scorecard_results
- ALTER deals: +deal_status, status_note, previous_stage, sector, location, founded_year, exclusivity_start, exclusivity_end
- ALTER deal_documents: +doc_status, doc_status_note, previous_doc_status
- ALTER deal_emails: +thread_id, contact_id, deal_stage_at_send, account
- Constants: STAGE_MIGRATION_MAP, VALID_STAGES, STAGE_GATES, DOC_CATEGORIES, DEFAULT_SCORECARD

### Step 2 — Stage migration
- Remap deal_stage values per STAGE_MIGRATION_MAP
- Backfill stage_entered_at to added_at where NULL

### Step 3 — Doc status defaults
- Default doc_status to 'draft' for all existing documents

### Step 4 — Data migration: deal_data → normalized tables
- financial/* → deal_financials (statement='pnl'/'balance', period_type based on subcategory)
- valuation_input/* → deal_financials (is_adjusted=1)
- customer_analysis/* → deal_customers (parse key=name, value_num=revenue)
- commercial/* → deal_commercial
- Archive original as deal_data_v1_archive

### Step 5 — Rename deal_granola → deal_granola_v1_archive, create deal_meetings

### Step 6 — Rewrite data.py extraction engine
- Split PNL_LABEL_MAP: gesamtleistung separate from revenue
- Split BWA_LABEL_MAP: same
- Add _extract_konto_nr() function
- Add _make_fin_row() helper
- Rewrite _pnl_to_entries(), _balance_to_entries(), _bwa_to_entries() for deal_financials format
- Rewrite _write_entries(): INSERT INTO deal_financials
- Rewrite _clear_source_rows(): DELETE FROM deal_financials
- Rewrite detect_conflicts(): queries deal_financials
- Rewrite compute_risk_flags(): returns list, no DB writes

### Step 7 — Rewrite model.py Excel reader
- Adjusted P&L: DELETE/INSERT deal_financials with is_adjusted=1
- Bewertung: INSERT deal_financials with statement='bewertung'
- _reconcile_ebitda(): queries deal_financials, returns conflict count

### Step 8 — Add stage gate config + gate-check CLI command
- STAGE_GATES dict in db.py
- gate_check() function: queries deal_documents + deal_manual_gates

### Step 9 — Update dashboard.py queries (~20 queries)
- Pipeline overview: deal_financials with gesamtleistung preference
- build_deal_data(): P&L, balance, model P&L, bewertung from deal_financials
- Risk flags: computed on the fly via compute_risk_flags()
- Customers: deal_commercial + deal_customers
- Overview: financial snapshot from deal_financials + deal_commercial

### Step 10 — Update valuation.py
- load_raw_pnl(), load_raw_pnl_detail(): SELECT from deal_financials with aliases
- _auto_populate_defaults(): reads bewertung from deal_financials
- build_model_context(): reads adjusted P&L from deal_financials

### Step 11 — Update rfi.py + DEALROOM.py
- rfi.py: financial summary from deal_financials, adjustment rows
- DEALROOM.py: status command table list from 10 to 21 tables

### Step 12 — Documentation
- ARCHITECTURE.md: full rewrite for v2 schema
- ROADMAP.md: add DR-SV2 milestone, update all deal_data references

## Validation results (2026-04-22)

- 25 tables in dealroom.db (22 active + 2 archive + allex_deals view)
- deal_data_v1_archive: 569 rows preserved
- deal_financials: 516 rows (migrated from financial + valuation_input categories)
- deal_customers: 30 rows (migrated from customer_analysis)
- deal_commercial: 23 rows (migrated from commercial category)
- deal_granola_v1_archive: exists (0 rows, schema preserved)
- Stage migration: all stages in new taxonomy (valuation, offer)
- Scorecard: 11 default metrics seeded in deal_scorecard_config
- All consumers rewritten and tested against live DB
