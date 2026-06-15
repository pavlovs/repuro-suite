# Deal Stage Redesign — Spec (2026-04-22)

Delta to `DEAL_WORKFLOW_SPEC.md`. Describes what changes and why. The workflow spec's 6-stage structure and activities remain valid — this redesign fixes the data model underneath.

---

## Problem

The current `deals.deal_stage` values in the DB (`financials_received`, `offer_preparation`, `offer_negotiation`, `offer_sent`) don't match the workflow spec's taxonomy (`info_exchange`, `indicative_offer`, `indicative_agreed`, `loi_signed`, `dd_complete`, `closed`). Neither set cleanly separates **where a deal is in the process** from **what's happening right now**. Stage advancement has no defined gate — no checklist, no required deliverables, no audit trail.

## What changes

### 1. New stage taxonomy

Replace all existing `deal_stage` values with:

| # | DB value | What it means | Gate to enter |
|---|----------|---------------|---------------|
| 1 | `nda_exchange` | First contact through data room handover | Deal created |
| 2 | `valuation` | Financial analysis, RFI, thesis building | Signed NDA + raw data room received |
| 3 | `offer` | Indicative offer drafting + negotiation | Financial model approved + onepager approved + IC go decision |
| 4 | `loi` | LOI drafting through signature | Indicative offer sent + terms agreed |
| 5 | `due_diligence` | Full DD workstreams | Signed LOI |
| 6 | `closed` | SPA negotiation through funds flow | DD reports approved + IC go decision |

Out-of-funnel stages (reachable from any funnel stage):
- `on_hold` — paused, preserves position for reactivation
- `dead` — killed, preserves position for post-mortem

### 2. New columns on `deals`

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `deal_status` | TEXT | `'on_track'` | Enum: `on_track`, `waiting_seller`, `waiting_internal` |
| `status_note` | TEXT | NULL | Free-text context for current status |
| `previous_stage` | TEXT | NULL | Last funnel stage before `on_hold`/`dead`. Used for reactivation. |

Existing `stage_entered_at` (currently all NULL) gets populated on every stage transition going forward.

### 3. New columns on `deal_documents`

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `doc_status` | TEXT | `'draft'` | Status within the document's progression |
| `doc_status_note` | TEXT | NULL | Free-text for blockers/context |
| `previous_doc_status` | TEXT | NULL | Stored when entering `blocked`, restored on unblock |

Document types are grouped into three categories, each with its own status progression:

**Internal** (financial_model, onepager, databook, commercial_dd, integration_plan):
`draft → reviewed → approved`

**Bilateral** (nda, loi, spa, indicative_offer, employment_agreement, escrow_agreement):
`draft → sent → negotiation → signed`

**RFI** (rfi):
`draft → sent → partially_answered → answered`

`blocked` is reachable from any state in any progression. When unblocked, returns to previous state. The category-to-type mapping and valid transitions are enforced in application code.

### 4. New table: `deal_manual_gates`

```sql
CREATE TABLE deal_manual_gates (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    gate_type       TEXT NOT NULL,
    stage_transition TEXT NOT NULL,
    decided_by      TEXT,
    decided_at      TEXT,
    decision        TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL
);
```

- `gate_type`: `ic_go_decision` or `terms_agreed`
- `stage_transition`: e.g. `valuation_to_offer`, `due_diligence_to_closed`
- `decision`: `go` or `no_go`

Manual gates capture decisions that can't be derived from document existence (IC approval, verbal agreement on terms).

### 5. Stage gate config (application code)

A Python dict defines what's required to advance between stages:

```python
STAGE_GATES = {
    "nda_exchange_to_valuation": {
        "documents": [("nda", "signed")],
        "manual": [],
    },
    "valuation_to_offer": {
        "documents": [("financial_model", "approved"), ("onepager", "approved")],
        "manual": ["ic_go_decision"],
    },
    "offer_to_loi": {
        "documents": [("indicative_offer", "sent")],
        "manual": ["terms_agreed"],
    },
    "loi_to_due_diligence": {
        "documents": [("loi", "signed")],
        "manual": [],
    },
    "due_diligence_to_closed": {
        "documents": [("dd_report", "approved")],
        "manual": ["ic_go_decision"],
    },
}

DOC_CATEGORIES = {
    "internal": {
        "types": ["financial_model", "onepager", "databook", "commercial_dd", "integration_plan"],
        "progression": ["draft", "reviewed", "approved"],
    },
    "bilateral": {
        "types": ["nda", "loi", "spa", "indicative_offer", "employment_agreement", "escrow_agreement"],
        "progression": ["draft", "sent", "negotiation", "signed"],
    },
    "rfi": {
        "types": ["rfi"],
        "progression": ["draft", "sent", "partially_answered", "answered"],
    },
}
```

### 6. Gate check function

A function (CLI + dashboard) that for a given deal:
1. Reads current `deal_stage`
2. Looks up the next transition in `STAGE_GATES`
3. Queries `deal_documents` for required doc types + statuses
4. Queries `deal_manual_gates` for required manual approvals
5. Returns a gap list: what's missing, what's at wrong status, what manual gates are unsigned

Surfaced as:
- CLI: `DEALROOM.py gate-check --deal <target>`
- Dashboard: gap indicators on the deal view

---

## Migration

Existing `deal_stage` values need mapping to the new taxonomy:

| Old value | New value |
|-----------|-----------|
| `financials_received` | `valuation` |
| `offer_preparation` | `valuation` (offer not yet sent) |
| `offer_negotiation` | `offer` |
| `offer_sent` | `offer` |

All existing `deal_documents` rows get `doc_status = 'draft'` as default — status needs manual review per deal to set correct values (many docs are already signed/approved but not tracked as such).

New doc types to register if not already in the classification list: `indicative_offer`, `dd_report`, `integration_plan`, `employment_agreement`, `escrow_agreement`. Existing types (`nda`, `loi`, `spa`, `financial_model`, `onepager`, `databook`, `rfi`) should already be recognized by DR-M2.

`stage_entered_at` gets backfilled to `added_at` for all deals (best available approximation).

---

## What does NOT change

- The 6-stage workflow structure in `DEAL_WORKFLOW_SPEC.md` (activities, owners, tools, failure modes)
- All other tables (`deal_data`, `deal_valuations`, `deal_questions`, `deal_actions`, `deal_emails`, `deal_granola`, `deal_notes`)
- Dashboard architecture, CLI structure, document ingestion pipeline
- `deal_documents` classification and ingestion logic (DR-M2) — only adds status columns
