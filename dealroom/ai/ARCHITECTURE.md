# DEALROOM — Architecture

Last updated: 2026-04-22. Schema v2 (normalized tables).

## System Overview

DEALROOM is a Python CLI + dashboard alongside ALLEX. Manages the full deal lifecycle from NDA exchange through closing.

```
ALLEX (pipeline.db)                    DEALROOM (dealroom.db)
─────────────────────                  ──────────────────────
company_records  ── READ-ONLY ──►      deals
                                       deal_financials     ← P&L, balance sheet, adjustments, bewertung
                                       deal_commercial     ← scalar commercial/operational metrics
                                       deal_customers      ← per-customer per-year entity data
                                       deal_backlog        ← project backlog / Auftragsvolumen
                                       deal_employees      ← personnel register
                                       deal_suppliers      ← supplier concentration
                                       deal_competitors    ← competitive landscape
                                       deal_valuations     ← computed scenarios + offer history
                                       deal_documents      ← file registry with doc_status tracking
                                       deal_questions      ← RFI + DD questions
                                       deal_contacts       ← stakeholder registry per deal
                                       deal_manual_gates   ← IC decisions, terms-agreed gates
                                       deal_dd_items       ← DD checklist + risk flags
                                       deal_meetings       ← all meeting types (replaces deal_granola)
                                       deal_emails         ← threaded email tracking
                                       deal_actions        ← blockers, action items
                                       deal_notes          ← timestamped free-text
                                       deal_model_params   ← interactive valuation assumptions
                                       deal_scorecard_config   ← configurable quality thresholds
                                       deal_scorecard_results  ← computed per-deal ratings
```

**The rule**: DEALROOM never writes to `pipeline.db`. The `domain` field is the universal FK.

---

## Deal Stage Model

```
nda_exchange → valuation → offer → loi → due_diligence → closed
                                                          ↓
                                                   on_hold | dead
```

| # | Stage | Meaning | Gate to enter |
|---|-------|---------|---------------|
| 1 | `nda_exchange` | First contact through data room handover | Deal created |
| 2 | `valuation` | Financial analysis, RFI, thesis building | NDA signed + raw data room received |
| 3 | `offer` | Indicative offer drafting + negotiation | Financial model approved + onepager approved + IC go |
| 4 | `loi` | LOI drafting through signature | Indicative offer sent + terms agreed |
| 5 | `due_diligence` | Full DD workstreams | Signed LOI |
| 6 | `closed` | SPA negotiation through funds flow | DD reports approved + IC go |

Out-of-funnel: `on_hold` (paused, preserves position), `dead` (killed, preserves position for post-mortem).

Additional deal columns: `deal_status` (on_track/waiting_seller/waiting_internal), `status_note`, `previous_stage`.

---

## Database Schema (`dealroom.db`) — 22+ tables

### Core: `deals`

12 active deals. Columns: id, domain, code_name, company_name, deal_stage, folder_path, investment_thesis, seller_motivation, seller_age_approx, seller_profile_notes, stage_entered_at, last_contact_at, added_at, notes, deal_status, status_note, previous_stage, sector, location, founded_year, exclusivity_start, exclusivity_end, plus portfolio view override columns.

### Financial data: `deal_financials`

Replaces the old `deal_data` EAV table. Fully normalized P&L, balance sheet, and valuation data.

Key columns: domain, statement (pnl/balance/adjustments/bewertung), line_item, konto_nr (DATEV account code), fiscal_year, period_type, value_k (EUR thousands), value_raw (original EUR), is_adjusted, source, confidence.

Critical: `gesamtleistung` and `revenue` are separate line_items. CAGR always computed on `gesamtleistung`.

### Commercial metrics: `deal_commercial`

Scalar commercial/operational KPIs. Key columns: domain, category (revenue/customers/suppliers/recurring/backlog/market/operational), metric, fiscal_year, value_num, value_text, unit.

### Entity tables: `deal_customers`, `deal_backlog`, `deal_employees`, `deal_suppliers`, `deal_competitors`

Tabular entity data that cannot fit in scalar metrics. Each table has domain as FK.

- `deal_customers`: per-customer per-year revenue, rank, cohort, type, contract info
- `deal_backlog`: project-level backlog with value, execution year, risk flags
- `deal_employees`: anonymized personnel register with roles, departments, compensation
- `deal_suppliers`: supplier concentration with cost share, exclusivity, relationship data
- `deal_competitors`: competitive landscape with estimated revenue, segment overlap

### Process: `deal_contacts`, `deal_manual_gates`, `deal_dd_items`

- `deal_contacts`: stakeholder registry (seller, broker, lawyers, advisors) with role, email, phone
- `deal_manual_gates`: IC decisions, terms-agreed gates. gate_type + stage_transition + decision (go/no_go)
- `deal_dd_items`: DD checklist items with category, status, risk_level, datenanfrage_ref

### Communication: `deal_meetings`, `deal_emails`

- `deal_meetings`: all meeting types (management_call, ic_meeting, site_visit, etc.) with summary, action items, data points. Replaces old `deal_granola` (archived as `deal_granola_v1_archive`).
- `deal_emails`: enhanced with thread_id, contact_id FK, deal_stage_at_send, account tracking.

### Quality: `deal_scorecard_config`, `deal_scorecard_results`

Configurable green/yellow/red thresholds for 11 default metrics: revenue CAGR, EBITDA margin, recurring %, customer concentration, supplier concentration, EV/EBITDA multiple, headcount, backlog coverage, customer churn.

### Kept unchanged: `deal_valuations`, `deal_questions`, `deal_actions`, `deal_notes`, `deal_model_params`

### Archived: `deal_data_v1_archive` (569 rows), `deal_granola_v1_archive` (0 rows)

---

## Document Status Tracking

`deal_documents` now includes `doc_status`, `doc_status_note`, `previous_doc_status`.

Status progressions by category (enforced in application code):

| Category | Doc types | Progression |
|----------|-----------|-------------|
| Internal | financial_model, onepager, databook, commercial_dd, integration_plan | draft → reviewed → approved |
| Bilateral | nda, loi, spa, indicative_offer, employment_agreement, escrow_agreement | draft → sent → negotiation → signed |
| RFI | rfi | draft → sent → partially_answered → answered |

`blocked` is reachable from any state; stores `previous_doc_status` for unblocking.

---

## Stage Gate Configuration

```python
STAGE_GATES = {
    "nda_exchange_to_valuation": {"documents": [("nda", "signed")], "manual": []},
    "valuation_to_offer": {"documents": [("financial_model", "approved"), ("onepager", "approved")], "manual": ["ic_go_decision"]},
    "offer_to_loi": {"documents": [("indicative_offer", "sent")], "manual": ["terms_agreed"]},
    "loi_to_due_diligence": {"documents": [("loi", "signed")], "manual": []},
    "due_diligence_to_closed": {"documents": [("dd_report", "approved")], "manual": ["ic_go_decision"]},
}
```

Gate check: queries deal_documents for required doc types + statuses, deal_manual_gates for manual approvals, returns gap list.

---

## Module Map

```
DEALROOM.py              CLI entry point
src/
  db.py                  schema (22 tables), migrations, ALLEX ATTACH, stage gates, scorecard config
  ingest.py              folder scan → deal_documents (DR-M2)
  data.py                rule-based extraction → deal_financials + conflict detection + risk flags (DR-M3)
  model.py               Excel model reader: GuV adj. P&L + Bewertung → deal_financials + deal_valuations (DR-M5)
  valuation.py           Live valuation engine: adj P&L, waterfall, earn-out matrix, pro-forma EBIT (DR-M7)
  bench.py               cross-deal benchmarking from deal_financials (DR-M13)
  generate/
    rfi.py               RFI question list → Word + deal_questions (DR-M6)
    offer.py             indicative offer → Word from template (DR-M8b)
    onepager.py          investor one-pager → HTML (DR-M9)
    email.py             email draft → Claude (DR-M10)
    nda.py               NDA → Word from template (DR-M12)
  dashboard.py           HTTP server + HTML, port 8090 (DR-M4, DR-M8)
  templates/
    dashboard.html       Self-contained HTML template with embedded JS/CSS
config/
  settings.py            paths, DEALS_DIR, ALLEX_PIPELINE_DB
  templates/
  rfi_examples/
tests/
```

---

## Standard Deal Folder Structure

```
{DEALS_DIR}/{date}_{CompanyName} ({CodeName})/
  0_Verträge und Meetings/     ← NDAs, contracts, meeting decks
    NDA/
  1_Unternehmensinformationen/ ← raw financials from target (READ-ONLY)
    {year}/
  2_Model/                     ← financial models (versioned)
    _archive/
  3_Indikatives Angebot/       ← offer drafts
  4_LOI/
  5_DD/
  6_SPA/
  CLAUDE/                      ← RFI docs, RAB data, deal-specific analysis
```

---

## Key Invariants

- `pipeline.db` opened read-only via ATTACH. Never write to it.
- All generated documents end in `_DRAFT` until Roman renames.
- `deal_financials` is the normalized source of truth for all financial/valuation data.
- `gesamtleistung` and `revenue` are always separate line_items. CAGR on gesamtleistung.
- DATEV account codes (konto_nr) preserved during extraction.
- Stage advancement requires passing gate checks (documents at required statuses + manual gates).
- Granola sync is append-only (via deal_meetings).
- Excel model template is read-only input — never overwrite it.
- `offer_round` in `deal_valuations` increments with every new offer iteration.
- SQLite journal_mode=DELETE (not WAL) due to OneDrive sync.
