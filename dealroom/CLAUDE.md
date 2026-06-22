# DEALROOM — Project Instructions

## Identity

**DEALROOM** is the M&A execution workspace for Repuro. It activates when a target in ALLEX reaches `deal_stage = 'financials_received'` and handles everything that follows: financial analysis, valuation, benchmarking, document generation, communication, and Granola meeting intelligence.

ALLEX finds and qualifies targets. DEALROOM executes on them.

**Working language**: English and German (documents are in German; code and logs in English).

## Session start — always do this

Read in this order:
1. `ai/ARCHITECTURE.md` — system design, DB link, module map
2. `ai/ROADMAP.md` — milestone status and what's next
3. `ai/LEARNINGS.md` — hard-won lessons; apply silently, do not comment unless relevant
4. `context/glossary.md` (repo root) — deal code names, people, investors

## Architecture in one line

`dealroom.db` (read-write) + ALLEX `pipeline.db` (read-only ATTACH) → CLI → Dashboard

Never write to `pipeline.db`. Never duplicate ALLEX data into `dealroom.db`. Read it live.

## Non-negotiable decisions

- **Single source of truth**: Company identity, basic financials, outreach history, contact data live in ALLEX `pipeline.db`. DEALROOM reads them via `ATTACH DATABASE`. No copy, no sync job, no duplication.
- **`domain` is the universal foreign key** that links DEALROOM records to ALLEX records.
- **`dealroom.db` only** stores data that ALLEX doesn't have: uploaded documents, extracted financials, valuations, offer drafts, email drafts, Granola summaries.
- **File storage** follows the standard deal folder: `data/deals/{code_name}/0_Meetings/`, `1_Financials/`, `2_Model/`, `3_Offer/`, `4_NDA/`, `5_DD/`.
- **Never write to source files** — Excel financials, NDA templates, offer templates are read-only inputs.
- **Claude API for extraction and generation** — financial extraction uses Claude (haiku bulk, sonnet for complex), offer/email generation uses sonnet. Always `--dry-run` on generation commands.
- **All commands idempotent** — re-running any command produces the same result.

## CLI entry point

```bash
python DEALROOM.py <command> --deal <code_name> [options]

Commands:
  deals          List all active deals (status, stage, key metrics)
  ingest-docs    Register documents from OneDrive deal folder
  extract        Parse financial documents → deal_financials table
  value          Compute valuation scenarios → deal_valuations table
  bench          Cross-deal benchmarking report (all live deals)
  draft-offer    Generate indicative offer draft (Word)
  draft-email    Draft email for specified intent (--intent "follow up on NDA")
  draft-nda      Generate NDA from template
  sync-granola   Pull meeting transcripts for the deal from Granola
  dashboard      Open deal workspace in browser
  status         Show dealroom.db state and per-deal progress
```

## Project stack

- **Language**: Python 3.11+
- **DB**: SQLite (`data/dealroom.db`) + ATTACH to ALLEX `pipeline.db`
- **Excel parsing**: openpyxl + pandas
- **Document generation**: python-docx (Word output)
- **AI**: `claude --via-cli` subprocess (OAuth, no API key) — consistent with ALLEX lead-pipeline. `haiku` for extraction, `sonnet` for generation.
- **Granola**: MCP tool `mcp__claude_ai_Granola__*` (already connected)
- **Dashboard**: same HTML + stdlib HTTP server pattern as ALLEX M11

## Definition of done (same as ALLEX)

A milestone is NOT complete until:
1. `ai/PLAN-DR-M{n}.md` exists with filled `## AI VALIDATION RESULTS`
2. `pytest tests/` passes
3. CLI command ran live against real data (--limit where applicable)
4. `ai/PLAN-DR-M{n}.md` PM Review section shows PASS (run `/review-milestone` after tests pass)
5. `ARCHITECTURE.md` updated if any design decision changed
6. `ai/ROADMAP.md` current state block updated
7. One commit per milestone

## DB Schema (v8, 22 tables)

Schema version in `PRAGMA user_version`. Migrations in `src/db.py`. All tables keyed on `domain`.

### Core
- **deals** — id, domain, code_name, company_name, deal_stage, folder_path, investment_thesis, seller_motivation, seller_age_approx, deal_status, sector, location, exclusivity_start/end, proj_topline_growth_pct, proj_gm_pct, proj_ebitda_margin_pct, stage_entered_at, last_contact_at
- **deal_documents** — id, domain, code_name, file_path, doc_type, doc_subtype, fiscal_year, file_name, file_size_kb, doc_status, extraction_config
- **deal_notes** — id, domain, note, author, category, source, importance, confidence, fiscal_year
- **deal_contacts** — id, domain, contact_name, role, company, email, phone, salutation, is_primary

### Financial
- **deal_financials** — id, domain, statement, line_item, konto_nr, fiscal_year, period_type, period, value_k, value_raw, is_adjusted, adjustment_note, source, confidence, is_authoritative, entity
- **deal_data** — legacy EAV (category/subcategory/key/value). Migrated to deal_financials/deal_commercial.
- **deal_model_params** — id, domain, scenario_name, entities_json, adj_items_json, gf_old/new_salary, ebitda/ebit_basis_override, multiple, net_debt, cash_at_closing, vendor_loan, earnout fields, proforma fields
- **deal_valuations** — id, domain, valuation_date, offer_round, ebitda_basis, multiple_low/mid/high, ev_low/mid/high, cash_at_closing, rueckbeteiligung, earnout_max, earnout_structure, seller_counter_ev

### Commercial (CDD)
- **deal_commercial** — id, domain, category, metric, fiscal_year, value_num, value_text, unit, source
- **deal_customers** — id, domain, customer_name, customer_id, fiscal_year, revenue_k, revenue_pct, rank, cohort, customer_type, specialty, relationship_start_year, has_contract, contract_end, change_of_control, churn_reason
- **deal_products** — id, domain, product_name, category, subcategory, fiscal_year, revenue_k, cost_k, gross_profit_k, margin_pct, revenue_share_pct, units_sold
- **deal_invoices** — id, domain, invoice_no, status, net_amount, gross_profit, segment, model, serial_no, art, invoice_date, fiscal_year, quarter, customer_ref
- **deal_backlog** — id, domain, customer_name, project_description, location, execution_year, order_value_k, margin_pct, status
- **deal_suppliers** — id, domain, supplier_name, fiscal_year, cost_k, cost_pct, rank, product_group, exclusivity
- **deal_competitors** — id, domain, competitor_name, rank, estimated_revenue_k, region, segment_overlap
- **deal_employees** — id, domain, employee_id, role, department, qualification, employment_type, hours_per_week, salary_monthly/annual_k, age_bucket, tenure_years, is_key_person

### Process
- **deal_questions** — id, domain, question, category, subcategory, importance, source, status, answer, sent_at, answered_at
- **deal_actions** — id, domain, description, category, owner, due_date, status, priority
- **deal_emails** — id, domain, intent, direction, recipient_name/email, subject, body_draft/final, status, thread_id, account
- **deal_meetings** — id, domain, meeting_type, meeting_date, participants, summary, key_topics, action_items, decisions
- **deal_granola** — id, domain, granola_meeting_id, meeting_title/date, participants, summary, data_points_json
- **deal_dd_items** — id, domain, category, subcategory, description, datenanfrage_ref, status, risk_level, risk_note
- **deal_manual_gates** — id, domain, gate_type, stage_transition, decided_by, decided_at, decision
- **deal_scorecard_config** — metric_key, label, category, threshold_green/yellow, direction, unit
- **deal_scorecard_results** — id, domain, metric_key, value, rating, fiscal_year

## Model usage

- **Extraction** (financial docs, meeting transcripts): `claude-haiku-4-5` — bulk, fast, cheap
- **Generation** (offers, emails, one-pagers, RFI): `claude-sonnet-4-6` — quality matters
- Never use sonnet for bulk extraction. Never use haiku for final-output generation.

## Multi-agent session protocol

Multiple Claude sessions may work on dealroom in parallel. Coordination is file-based.

**On session start (log on):**
1. Read `CLAUDE_REPURO/.active/dealroom-sessions.md` — check for active sessions
2. Register your session: add a block with name, timestamp, issue IDs, and file locks
3. If a file you need is exclusively locked by another session, work on something else

**On session end (log off):**
1. Remove your session block from `dealroom-sessions.md` entirely
2. Update `ISSUES.md` status for any issues you completed

**During work:**
- Before editing any file, check the lock list. If locked → skip.
- `ISSUES.md` is shared-append (multiple sessions can add entries). Don't rewrite other sessions' entries.
- `dealroom.db` is shared-read by default. Schema migrations require an exclusive lock.
- Dashboard templates (`src/dealroom/templates/`) require an exclusive lock — only one session touches UI at a time.
- If you need a locked file: add a `WAITING:` line under the blocking session's entry.

**Issue tracker:** `dealroom/ISSUES.md` — all bugs and feature requests go here. Use `DR-BUG-NNN` / `DR-FEAT-NNN` IDs.

## Standing rules

- Ask before building anything that touches ALLEX files or `pipeline.db`
- Never modify the KVG example folder or any source financial documents
- All offer/NDA generation produces a draft for Roman's review — never a final document
- Granola sync is read-only — never create or modify Granola meetings
- Batch all clarifying questions into one ask per session
