# SPEC-RFI — Template-Fill Specification for RFI (Datenanfrage) Agent

Engineering spec for `src/generate/rfi.py`. Defines the question bank, stage-gating logic, data dependencies, and architecture for producing deal-specific RFI documents from template.

**Status:** Active. Supersedes implicit behavior in current `rfi.py`.
**Owner:** Roman (content/prioritization), Claude (execution/fill).
**Last updated:** 2026-05-19.

---

## 1. Overview

The RFI template-fill agent produces a German-language Datenanfrage (Request for Information) tailored to a specific deal and its current stage. It combines:

1. A **structured question bank** (58 items across 8 categories, stage-tagged)
2. **Deal-specific anomaly questions** derived from `deal_financials` (YoY changes, margin flags, account-level deviations)
3. **Conflict-resolution questions** from duplicate values in `deal_financials`
4. **Claude refinement** for tone, specificity, and deal-specific phrasing

Output: `deal_questions` rows (DB) + branded PDF (Repuro CI) + optional xlsx tracking sheet.

### Golden File Roles

| File | Path (relative to `config/golden/rfi/`) | Role |
|---|---|---|
| Datenanfrage_Template.xlsx | `Datenanfrage_Template.xlsx` | **PRIMARY**: Structural question bank with stage tags (column D). 8 categories, ~58 items. Source of truth for question selection. |
| CAT_Frageliste.md | `CAT_Frageliste.md` | Tone/format reference. Machine-parseable. Shows deal-specific phrasing with status tracking and priority blocking. |
| CAT_Frageliste_v3.docx | `CAT_Frageliste_v3.docx` | Output format reference. Formal letter structure with section headers. |
| HWV_RFI_vS.docx | `HWV_RFI_vS.docx` | Account-level question reference. References specific SKR account numbers (42100, 42280, 45300, 47700, 49500, 84000). Working-level tone. |
| 260108_Datenanfrage.xlsx | `260108_Datenanfrage.xlsx` | Response tracking reference. Status legend (offen/angefordert/erhalten/nicht relevant). Shows real-world usage of template. |
| AQUA - Summary and Next Steps.md | `AQUA - Summary and Next Steps.md` | Triage/prioritization logic reference. RFI v2 table shows keep/drop decisions with commercial justification per question and scorecard mapping. |

---

## 2. Question Taxonomy

8 top-level categories from `Datenanfrage_Template.xlsx`. Every question item has a category, sub-item identifier, and stage tag.

| # | Category (DE) | Category (EN) | Sub-items | Count | Stage Coverage |
|---|---|---|---|---|---|
| 1 | Kunden | Customers | Revenue by segment, Top 40 customers, competitors, litigation history, material contracts, change-of-control clauses | ~12 | Onepager (3) + DD (9) |
| 2 | Lieferanten | Suppliers | Top 10/20 suppliers, price increase history, litigation | ~6 | Onepager (1) + DD (5) |
| 3 | Personal | Personnel | Org chart, employee list with roles/tenure/comp, employment contracts, hires/departures 3yr, freelancers/temps, GF salary structure, litigation/Arbeitsrecht | ~13 | Onepager (1) + DD (12) |
| 4 | Finanzen | Financials | Jahresabschluss (JA), SuSa/Saldenliste, BWA, one-off/normalization list, business plan, receivables aging, credit agreements, off-balance-sheet items, Pensionsruckstellungen | 9 | Financial Model (5) + DD (4) |
| 5 | Versicherungen | Insurance | Policy register, claims history 5yr | 2 | DD only |
| 6 | Steuern | Tax | Returns 3yr, tax calculations, disputes/audits, advisor opinion letter, last Betriebsprufung date, related-party transactions, KESt/withholding | 7 | DD only |
| 7 | Gesellschaftsverfassung | Corporate | Articles of association (Satzung), shareholder list (Gesellschafterliste), shareholder resolutions 3yr, GF service agreements, Handelsregister excerpt | 5 | DD only |
| 8 | Betriebsausstattung | Operations/Assets | Locations/sites list, lease agreements, IP/trademarks/patents, IT systems inventory | 4 | DD only |

**Total:** ~58 question items.

### Universal Questions (appear in every RFI regardless of deal)

These questions appear across CAT, HWV, and AQUA golden files:

- P&L data by year (minimum 3 years Ist)
- Revenue segmentation (by product/service/geography/customer type)
- Personnel costs and GF compensation detail
- One-off/normalization items
- Customer concentration (Top 10/20 share)
- Management planning / business plan

---

## 3. Stage-Gating Logic

### Template Labels (Column D of Datenanfrage_Template.xlsx)

Three explicit labels in the template:

| Label | Count | Description |
|---|---|---|
| **Onepager** | ~6 | Minimum viable data set for deal screening. Revenue splits, Top 20 customers, Top 10 suppliers, headcount, competitor landscape. |
| **Financial Model** | 5 | Data required to build the valuation model. JA (3yr), SuSa, BWA, one-offs/normalizations, business plan. |
| **Due Diligence** | ~47 | Full disclosure scope. Everything else: insurance, tax, corporate, operations, detailed personnel, contracts, litigation. |

### Derived 4-Stage Logic

The fill agent maps DEALROOM's `deal_stage` to an RFI scope:

| Deal Stage | RFI Scope | Question Selection | Expected Count |
|---|---|---|---|
| `nda_exchange` | **Pre-screening** | No formal RFI produced. Manual questions only. Fill agent returns empty + warning. | 0 |
| `valuation` (early) | **Onepager + Financial Model** | Onepager-tagged items + Financial Model items. Core commercial + financial data to build the model and onepager. | ~11 |
| `valuation` (late) | **Pre-IO / Valuation** | Above + deal-specific anomaly questions from `deal_financials`. Account-level questions for SuSa/BWA anomalies. Triage-filtered by scorecard relevance. | ~16-20 |
| `offer` through `due_diligence` | **Full DD** | All 58+ template items minus already-answered. Expanded operational, legal, tax, insurance, corporate. | 40-58 (minus answered) |

### Early vs. Late Valuation Disambiguation

The fill agent distinguishes early from late valuation using data availability:

```
IF deal_financials has >= 2 years P&L data
   AND deal_financials has at least 1 adjustment row
   THEN late_valuation (include anomaly questions)
ELSE early_valuation (template questions only)
```

---

## 4. Data Input Schema

### Required DB Tables and Fields

| Table | Fields Used | Purpose |
|---|---|---|
| `deals` | `domain`, `code_name`, `company_name`, `deal_stage`, `folder_path` | Deal identification + stage routing |
| `deal_financials` | `line_item`, `fiscal_year`, `value_k`, `statement` (pnl/balance/adjustments), `period_type`, `konto_nr`, `source`, `is_adjusted`, `confidence`, `adjustment_note` | Financial summary, anomaly detection, conflict detection, account-level questions |
| `deal_commercial` | `category`, `metric`, `fiscal_year`, `value_num`, `value_text` | Customer concentration, recurring %, supplier data |
| `deal_customers` | `name`, `revenue`, `rank`, `fiscal_year`, `type`, `contract_type` | Customer-specific questions (Top N analysis) |
| `deal_suppliers` | `name`, `cost_share`, `exclusivity`, `fiscal_year` | Supplier concentration questions |
| `deal_employees` | `role`, `department`, `compensation`, `tenure` | Personnel-specific questions |
| `deal_questions` | `question`, `status`, `source`, `answer`, `answer_feeds_data_key` | Already-answered filter, idempotent insert |
| `deal_documents` | `doc_type='rfi'`, `file_path`, `code_name` | Golden corpus from other deals |

### Anomaly Detection Thresholds

| Metric | Threshold | Question Trigger |
|---|---|---|
| Revenue YoY change | > +20% or < -10% | "Treiber fragen" / "Grunde fragen" |
| EBITDA margin | < 10% | "Normalisierungsanpassungen fragen" |
| Personnel / Revenue | > 20% | "GF-Gehalt und Einmalkosten fragen" |
| Receivables YoY | > +25% | "Uberfalligkeit und Kundenkonzentration fragen" |
| Bank debt / EBITDA | > 3.0x | "Finanzierungsstruktur und Tilgungsplan fragen" |
| Net debt / EBITDA | > 2.0x | "Finanzierungsstruktur fragen" |

### Account-Level Data (SuSa/BWA)

When `konto_nr` is populated in `deal_financials`, the fill agent can produce account-level questions referencing specific DATEV/SKR codes. Pattern from HWV golden file:

- `42100` (Wareneinsatz) -- COGS main account
- `42280` (Fremdleistungen) -- outsourced services
- `45300` (Kfz-Kosten) -- vehicle costs (GF adjustment candidate)
- `47700` (Reisekosten) -- travel costs
- `49500` (sonstige Aufwendungen) -- other expenses (one-off screening)
- `84000` (außerordentliche Ertrage) -- extraordinary income

**Gap (current):** `rfi.py` does not query `konto_nr`. Fix: add account-level anomaly detection in `_build_financial_summary()`.

---

## 5. Fill Agent Architecture

### 4-Stage Pipeline

```
Stage 1: Template Selection
  INPUT:  deal_stage, deal_financials row count
  ACTION: Parse Datenanfrage_Template.xlsx programmatically
          Filter questions by stage tag matching deal_stage
          Remove already-answered questions (status='answered'|'waived')
  OUTPUT: List of template questions with category + subcategory + stage_tag

Stage 2: Deal-Specific Questions
  INPUT:  deal_financials (all statements), deal_commercial, deal_customers
  ACTION: Run anomaly detection (YoY thresholds, margin flags)
          Run conflict detection (same key+year, different values)
          Run account-level SuSa/BWA analysis (if konto_nr populated)
          Generate German-language questions per anomaly/conflict
  OUTPUT: List of anomaly + conflict + account-level questions

Stage 3: Claude Refinement
  INPUT:  Template questions (Stage 1) + deal-specific questions (Stage 2)
          + golden corpus text (tone reference)
          + company_name, deal_stage, financial summary
  ACTION: Claude prompt with structured instructions:
          - Merge template + deal-specific questions
          - Refine phrasing for deal context (reference specific numbers)
          - Deduplicate semantically similar questions
          - Assign importance (high/medium) and sort_order
          - Output JSON array
  OUTPUT: Final question list as validated JSON

Stage 4: Review Gate
  INPUT:  Final question list from Stage 3
  ACTION: Write to deal_questions with status='draft' (idempotent: delete prior draft rfi_generator rows, insert new)
          Produce PDF with _DRAFT suffix from Repuro-branded template
          Present to Roman: question count per section, flagged anomalies, DRAFT PDF path
          Roman reviews: approves, edits, or removes individual questions
          BLOCK: Do not proceed to send/finalize until Roman explicitly approves
  OUTPUT: Reviewed question list with status='draft' (approved) or status='removed'

Stage 5: Output
  INPUT:  Approved question list + financial summary + deal metadata
  ACTION: Produce final PDF from template without _DRAFT suffix
          Update deal_questions status from 'draft' to 'ready'
          Optionally produce xlsx tracking sheet (status legend from 260108_Datenanfrage.xlsx)
  OUTPUT: deal_questions rows (status='ready') + final PDF + optional xlsx
  NOTE:   Status changes to 'sent' only when Roman actually sends the RFI to the target
```

### Claude Prompt Structure

The prompt to Claude contains (in order):

1. **System instruction**: Language=German, tone=professional, no generic questions without numbers
2. **Buyer-perspective guard**: "We build the model ourselves. Only ask what the seller must provide."
3. **Company context**: name, deal_stage
4. **Financial summary**: P&L by year, LTM/BWA, balance sheet, YoY changes, net debt, known adjustments
5. **Anomaly flags**: German-readable strings from threshold detection
6. **Pre-formed conflict questions**: Exact text, source='rfi_generator:conflict'
7. **Already-answered exclusion list**: Up to 20 most recent answered questions
8. **Golden corpus**: Tone reference from CAT/HWV/AQUA (max 6000 chars)
9. **Stage-specific section structure**: Which sections to include based on deal_stage
10. **Output format**: JSON array schema with required fields

### Section Mapping

Questions are routed to PDF sections via `_SECTION_MAP`:

| Subcategory | PDF Section |
|---|---|
| adjustments, legal, process | Allgemeine Fragen / Adjustments |
| revenue, costs | GuV |
| balance | Bilanz |
| customers, revenue_split, contracts, recurring | Kunden |
| personnel, succession | Mitarbeiter |
| insurance | Versicherungen |
| tax | Steuern |
| corporate | Gesellschaftsverfassung |
| operations, assets, leases, ip | Betriebsausstattung |

---

## 6. Current Gaps and Fixes

### Gap 1: No Stage-Gating

**Current behavior:** Fill agent always produces 12-18 questions regardless of `deal_stage`. The prompt hardcodes "Erstelle 12-18 Fragen".

**Fix:** Parse `Datenanfrage_Template.xlsx` programmatically at startup. Build a `QUESTION_BANK` dict indexed by `(category, stage_tag)`. The prompt instruction changes per stage:

```python
STAGE_QUESTION_COUNTS = {
    "nda_exchange": 0,           # No RFI
    "valuation_early": (8, 12),  # Onepager + Financial Model items
    "valuation_late": (14, 20),  # Above + anomaly questions
    "offer": (30, 50),           # Full DD minus answered
    "due_diligence": (40, 58),   # Everything
}
```

**Implementation:** New function `_select_template_questions(deal_stage, answered_set) -> list[dict]` that reads from parsed template and filters by stage scope.

### Gap 2: Template Questions Not Structured

**Current behavior:** Golden corpus text extraction (`_load_rfi_corpus`) reads the template xlsx as flat text, losing numbering, category structure, and stage tags.

**Fix:** Create `_parse_datenanfrage_template() -> list[dict]` that reads `Datenanfrage_Template.xlsx` with openpyxl (read-only mode), extracts:
- Column A: category number
- Column B: question text
- Column C: sub-item detail
- Column D: stage tag (Onepager / Financial Model / Due Diligence)

Cache result in module-level variable (parsed once per process). Return structured dicts, not flat text.

### Gap 3: No Account-Level Questions

**Current behavior:** Anomaly detection operates on aggregate line_items (revenue, ebitda, personnel). Does not reference `konto_nr` from SuSa/BWA.

**Fix:** Add `_build_account_anomalies(conn, domain) -> list[str]` that:
1. Queries `deal_financials WHERE konto_nr IS NOT NULL`
2. Groups by `konto_nr + fiscal_year`
3. Detects YoY changes > 25% for material accounts (value_k > 20)
4. Generates questions like: "Konto 42280 (Fremdleistungen) ist von 45 K€ (2023) auf 72 K€ (2024) gestiegen (+60%). Bitte erlautern Sie die Ursache."

Reference: HWV_RFI_vS.docx pattern.

### Gap 4: Missing Categories

**Current behavior:** Fill agent covers 5 sections: Adjustments, GuV, Bilanz, Kunden, Mitarbeiter. Template has 8 categories (missing: Insurance, Tax, Corporate, Operations/Assets).

**Fix:** Extend `_SECTION_MAP` with new subcategory keys. Extend the Claude prompt section structure to include all 8 categories when `deal_stage` is `offer` or later. For `valuation` stage, keep current 5 sections (Insurance/Tax/Corporate/Operations are DD-scope).

New subcategories to add:
```python
_SECTION_MAP_EXTENDED = {
    **_SECTION_MAP,
    "insurance": "Versicherungen",
    "tax": "Steuern",
    "corporate": "Gesellschaftsverfassung",
    "operations": "Betriebsausstattung",
    "assets": "Betriebsausstattung",
    "leases": "Betriebsausstattung",
    "ip": "Betriebsausstattung",
}
```

### Gap 5: No Triage/Priority Logic

**Current behavior:** All generated questions have equal weight. No keep/drop decision logic. No scorecard mapping.

**Fix:** Implement triage based on AQUA pattern:

1. Each question gets a `scorecard_dimension` field (maps to deal_scorecard_config dimensions)
2. After fill, run `_triage_questions(questions, deal_data) -> list[dict]`:
   - **Keep**: Question addresses a scorecard RED or YELLOW dimension
   - **Keep**: Question addresses a financial anomaly
   - **Drop**: Question asks for data already available in deal_financials with confidence='high'
   - **Drop**: Question is immaterial (references amounts < 10 K€)
   - **Deprioritize**: Question is standard DD boilerplate and deal is pre-offer
3. Add `triage_status` field: keep/drop/deprioritize with `triage_reason`
4. Dropped questions still written to DB with `status='deprioritized'` for audit trail

---

## 7. Edge Cases and Hardening Rules

### Data Quality

- **No financial data available:** Fill agent produces template-only questions (no anomaly section). Warn in output: "Keine Finanzdaten verfuegbar -- nur Template-Fragen generiert."
- **Single year of data:** Skip YoY anomaly detection. Still produce margin and ratio checks for the available year.
- **Mixed period types:** LTM/BWA rows labeled separately in prompt (current behavior, correct). Never mix annual JA with partial-year BWA in same YoY comparison.
- **German number format in source data:** `deal_financials.value_k` is always stored as float (thousands). No format conversion needed at fill time. But display in PDF uses German format for recipient.

### Deduplication

- Before writing to DB, check semantic similarity between new questions and existing `status='sent'` questions. If a new question covers the same topic as a sent question, skip it.
- Conflict questions (`source='rfi_generator:conflict'`) are always included -- they represent real data inconsistencies.

### Idempotency

- Current behavior (correct): Delete all `source LIKE 'rfi_generator%' AND status='draft'` rows before inserting new batch. Never touch `status='sent'|'answered'|'waived'` or `source='manual'`.
- **Hard rule:** The fill agent never modifies questions that have been sent or answered. Once a question leaves draft status, it is immutable.

### Answer Feedback Loop

- `answer_feeds_data_key` maps answered questions back to `deal_financials` / `deal_commercial` fields. When an answer is recorded, the pipeline can auto-populate the corresponding data field.
- Current keyword-based inference (`_infer_feeds_key`) covers 11 patterns. Extend as new question types are added.

### Output Path

- Default: `{deal_folder}/1_Unternehmensinformationen/{YYMMDD}_{code_name}_Fragenliste_DRAFT.pdf`
- Fallback: `data/output/{YYMMDD}_{code_name}_Fragenliste_DRAFT.pdf`
- **Never overwrite a non-DRAFT file.** If a file without `_DRAFT` exists at the target path, write to a new versioned path.

### Multi-Entity Deals

- CAT pattern: M&S GmbH + LIKE GmbH consolidated. RFI must specify which entity's data is requested when questions reference financials.
- If `deal_financials` has multiple `source` values indicating separate entities, the fill agent should add an entity qualifier to relevant questions.

---

## 8. Confidence Assessment

| Component | Confidence | Notes |
|---|---|---|
| Template question selection by stage | **HIGH** | Direct mapping from xlsx column D. Mechanical. |
| Formal letter output format (PDF) | **HIGH** | Already implemented, Repuro-branded. |
| Section routing via subcategory | **HIGH** | Extend existing `_SECTION_MAP`. Mechanical. |
| Anomaly detection (P&L-level) | **HIGH** | Already implemented. Thresholds validated across deals. |
| Account-level anomaly questions | **MEDIUM** | Requires `konto_nr` to be populated. Depends on SuSa parsing quality (DR-M3). Works for HWV/FOX where SuSa was ingested; untested for deals without SuSa. |
| Triage/keep-drop logic | **MEDIUM** | AQUA pattern is clear but has one golden example. Needs validation on 2-3 more deals before hardcoding thresholds. |
| Stage disambiguation (early vs late valuation) | **MEDIUM** | Heuristic based on data availability. May need Roman override for edge cases. |
| Deal-specific creative questions | **LOW** | Questions about management transition, strategy, regulatory -- these require domain judgment. Claude generates reasonable drafts but Roman reviews every RFI before sending. |
| xlsx tracking sheet output | **LOW** | Not implemented. Nice-to-have. 260108_Datenanfrage.xlsx format exists as reference. |

---

## 9. Dependencies

### Upstream (required before fill agent runs)

| Dependency | Source | Notes |
|---|---|---|
| Deal created in DB | `deals` table | `code_name` must exist |
| Documents ingested | DR-M2 (`ingest.py`) | Needed for `deal_documents` golden corpus lookup |
| Financial data extracted | DR-M3 (`data.py`) | `deal_financials` must have >= 1 year of P&L for meaningful output |
| Golden corpus populated | `config/golden/rfi/` | 6 files currently registered. Fill agent degrades gracefully if corpus empty. |
| `Datenanfrage_Template.xlsx` | `config/golden/rfi/` | **Critical for Gap 1/2 fix.** Must be parseable. |

### Downstream (consumes RFI output)

| Consumer | How it uses RFI output |
|---|---|
| Dashboard (port 8090) | Displays `deal_questions` with status badges, source labels, filters |
| `deal_questions.answer_feeds_data_key` | Routes answers back to `deal_financials` / `deal_commercial` for auto-population |
| Valuation model review (2.1) | RFI answers may trigger model adjustments |
| Deal scorecard (2.4) | Unanswered RFI questions → OPEN signals in scorecard |
| Offer drafting (3.1) | RFI answers inform offer structure (GF transition, net debt, earn-out) |

### Tool Dependencies

| Tool | Version | Purpose |
|---|---|---|
| `claude` CLI | Latest (OAuth) | LLM refinement of question list |
| `reportlab` | >= 4.0 | PDF generation with Repuro branding |
| `python-docx` | >= 0.8 | Golden corpus text extraction from .docx |
| `openpyxl` | >= 3.1 | Template xlsx parsing (read-only mode) |

---

## Anti-Patterns

### DOCX-FROM-TEMPLATE (critical)
**Never produce an RFI document from scratch.** Always use the Repuro-branded template for PDF output. Copy golden file structure for xlsx tracking sheets.

### INVENTED-FORMAT-INSTEAD-OF-COPY (critical)
**Never invent question categories or restructure the section order.** Follow the Datenanfrage_Template.xlsx 8-category structure exactly.

### CONFIDENTIAL-LEAK (critical)
**Never include pricing, valuation, or internal deal assessment data in an RFI.** The RFI is sent to the target company — it asks for data, it does not reveal Repuro's analysis. If deal_financials data appears in question text, it must be limited to what the target already knows (their own reported figures).

### QUESTION-FABRICATION (medium)
**Never invent questions that sound specific but have no data backing.** If anomaly detection did not flag a metric, do not generate a question about it just to fill the question count. Template questions are pre-vetted; anomaly questions are data-driven. Filler questions waste seller goodwill.

---

## Cross-References

- Deal workflow: `DEAL_WORKFLOW_SPEC.md` (Stage 2: Valuation and RFI)
- Deliverables spec: `DEAL_DELIVERABLES_SPEC.md` (Template Registry -- RFI row)
- Architecture: `ARCHITECTURE.md` (Module Map: `src/generate/rfi.py`)
- Anti-patterns: `Claude_Context/anti-patterns-deals.md`
- Golden corpus: `config/golden/README.md` + `config/golden/manifest.json`
- Current implementation: `src/generate/rfi.py` (DR-M6)
