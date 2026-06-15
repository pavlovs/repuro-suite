# SPEC-DR-GATHER -- Qualitative Data Gathering Specification

Engineering spec for the **qualitative data** intake pipeline. Extracts structured facts from Granola meeting transcripts, RFI responses, Expose PDFs, Rueckfragen, databooks, and presentations into `deal_notes`, `deal_meetings`, `deal_contacts` + enrichment of `deal_commercial`.

**Scope boundary:** Qualitative/unstructured data only. Financial docs → DR-READER. Structured commercial xlsx → DR-COMMERCIAL. DR-GATHER does **fact extraction from natural language**, not column mapping or number parsing.

**Core principle:** Extract discrete, queryable facts with source attribution. "EBIT 2025 = EUR 380k (source: Com2Med Gespraech May 8)" is a fact. "The meeting discussed financials" is useless.

**Status:** Draft. **Owner:** Roman + Claude. **Last updated:** 2026-05-20.

**Sibling specs:** DR-READER (financial), DR-COMMERCIAL (commercial tabular).

---

## 1. Source Types and Routing

Every file in `1_Unternehmensinformationen` is classified into one of three lanes:

| Doc Type | Format | Lane | Target |
|---|---|---|---|
| Granola meeting notes | MCP API | **DR-GATHER** | `deal_meetings` + `deal_notes` |
| RFI response (vAntworten) | docx | **DR-GATHER** | `deal_notes` (Q&A pairs) |
| Rueckfragen follow-up | docx | **DR-GATHER** | `deal_notes` (Q&A pairs) |
| Expose / CIM | PDF | **DR-GATHER** | `deal_notes` (profile facts) |
| Meeting presentations | pptx | **DR-GATHER** | `deal_notes` (presentation facts) |
| Kaufpreismechanismus | xlsx/PDF | **DR-GATHER** | `deal_notes` (pricing structure) |
| Saldenliste Kundenkonten | PDF | **DR-GATHER** | enrich `deal_customers` |
| Saldenliste Lieferantenkonten | PDF | **DR-GATHER** | enrich `deal_suppliers` |
| Databook | xlsx | **DR-GATHER** | cross-check vs DB, flag deltas |
| SUSA / BWA / JA / GuV / Bilanz | xlsx/PDF | DR-READER | `deal_financials` |
| Customer revenue lists / RAB | xlsx | DR-COMMERCIAL | `deal_customers` |
| Product/Warengruppen xlsx | xlsx | DR-COMMERCIAL | `deal_products` |

**Real examples -- Cat:** `250625_MS_RFI_vS.docx` (RFI response), `260421_CAT_Databook_v10.xlsx` (cross-check), `250624_Repuro_Draft_Meeting_v1.pptx` (presentation), `Saldenlisten Kundenkonten.pdf`, `260318_MS_Rueckfragen_vS_Antworten.docx` (follow-up Q&A).

**Real examples -- Octopus:** `250807_HWV_RFI_vAntworten.docx` (RFI response), `HWV_Expose.pdf` (CIM), `Kaufpreismechanismus_2024-2026.xlsx` (pricing mechanism).

---

## 2. Granola Integration

### MCP Tools

| Tool | Purpose |
|---|---|
| `mcp__claude_ai_Granola__query_granola_meetings` | Discovery: find deal-relevant meetings by natural language query |
| `mcp__claude_ai_Granola__list_meetings` | Scan for new meetings since last extraction |
| `mcp__claude_ai_Granola__get_meeting_transcript` | Full transcript for fact extraction |

### Meeting Discovery

Query with codename AND company name AND alternative names. Meetings may reference any of these.

| Deal | Query Pattern |
|---|---|
| Cat | `"Medizin & Service" OR "Cat" OR "M&S"` |
| Fox | `"Com2Med" OR "Fox"` |
| Wolf | `"KVG" OR "Wolf"` |
| Octopus | `"HWV" OR "Octopus"` |

Also query `"Pipeline Review" OR "Deal Review"` -- cross-deal meetings with prioritization context.

### Granola Extraction Flow

```
[1. Query] mcp__claude_ai_Granola__query_granola_meetings(query="{company} OR {code}")
   → meeting IDs + snippet answers
[2. Filter] Check deal_meetings.granola_meeting_id → skip already-extracted
[3. Fetch]  mcp__claude_ai_Granola__get_meeting_transcript(meeting_id=X)
   → full text + metadata (date, participants)
[4. Extract] LLM reads transcript + deal context → discrete facts
[5. Store]  Meeting → deal_meetings | Facts → deal_notes | People → deal_contacts
```

### Real Granola Content Examples

From Fox/Com2Med Gespraech:
- `financial_kpi`: "EBIT 2025 revised up to EUR 380k"
- `pricing`: "Roman at EUR 5.2M, owner at EUR 5.7M"
- `management`: "Prokuristen program for new GF to be drafted"
- `risk_flag`: "Philips dependency ~35% gross margin", "devices appearing in Russia"
- `timeline`: "Target close date: August 30"
- `strategy`: "Not standalone -- requires combination with technical expertise partner"

From Cat/M&S call:
- `timeline`: "Notary mid/end August 2026"
- `pricing`: "Sofortzahlung EUR 4.8M + earn-out up to EUR 600k"
- `next_steps`: "Send Rueckfragen by Friday, schedule site visit"

---

## 3. Fact Extraction (AI Layer)

### 3.1 Categories

| Category | Captures | Used By |
|---|---|---|
| `financial_kpi` | Revenue, EBIT, EBITDA figures from meetings/docs | Scorecard cross-check |
| `pricing` | Offer amounts, valuation expectations, negotiations | SPEC-OFFER, LOI |
| `management` | GF info, key persons, succession, Prokuristen | Onepager, DD |
| `risk_flag` | Dependencies, compliance, concentration, litigation | Scorecard, RFI follow-up |
| `timeline` | Close dates, DD timelines, exclusivity periods | Dashboard, tasks |
| `next_steps` | Action items, follow-up tasks with owners | Dashboard, tasks |
| `products` | Product descriptions, service offerings, segments | Onepager, DD |
| `market` | Market size, competition, trends | Onepager, DD |
| `customers` | Relationships, contracts, qualitative context | Onepager, enrich `deal_customers` |
| `employees` | Headcount, key roles, tenure, qualifications | Onepager, enrich `deal_employees` |
| `strategy` | Investment thesis, synergies, platform fit | SPEC-OFFER, IC document |
| `rfi_answer` | Specific Q&A pairs from RFI responses | RFI tracking, gap analysis |

### 3.2 Output Format

```json
{
  "category": "financial_kpi",
  "content": "EBIT 2025 revised up to EUR 380k",
  "confidence": "stated",
  "source_ref": "granola:meeting_abc123:timestamp_14:32",
  "importance": "high",
  "fiscal_year": 2025,
  "value_k": 380,
  "metric": "ebit"
}
```

### 3.3 Source-Specific Rules

**Granola meetings:** Extract figures, decisions, risks, timeline, next steps. Participants → `deal_contacts`. Action items with owners → `next_steps` with owner in content.

**RFI responses (vAntworten):** Extract Q&A pairs as `rfi_answer`. Cross-reference `deal_questions` -- mark matched questions as answered. Double-extract: factual content within answers also gets the appropriate category tag (e.g., litigation answer → `risk_flag`).

**Rueckfragen:** Same as RFI responses. Only extract from latest answer version (vAntworten > vS > v1).

**Expose / CIM PDFs:** Rich source for products, market, management, employees, strategy. Cross-check seller claims against DB data.

**Databooks:** Cross-check mode only, not fact extraction. Compare databook figures vs `deal_financials` and `deal_customers`. Flag deltas > 2% as `risk_flag`. Confirm matches as `financial_kpi`.

**Saldenliste Kunden/Lieferantenkonten:** Extract names + balances. Match to existing `deal_customers`/`deal_suppliers` via entity resolution. NOT Saldenliste Sachkonten (→ DR-READER).

### 3.4 LLM Prompt Design

The extraction prompt contains:
1. **Rules:** Facts not summaries. One category per fact. Include numbers/names/dates. Flag uncertainty.
2. **Deal context:** company name, domain, stage, financial summary from DB
3. **Document text:** full text of the source document
4. **Output schema:** JSON array of `{category, content, confidence, importance, fiscal_year, value_k, metric}`

Key instruction: "Extract FACTS, not summaries. Each fact must contain at least one of: a number, a name, a date, a decision, or a concrete risk."

---

## 4. DB Schema

### deal_notes (exists -- needs migration)

Current schema (v1) has only: `id, domain, note, author, created_at`.

**Required migration (v5):**

```sql
ALTER TABLE deal_notes ADD COLUMN category TEXT;
ALTER TABLE deal_notes ADD COLUMN source TEXT;
ALTER TABLE deal_notes ADD COLUMN source_file_id TEXT;
ALTER TABLE deal_notes ADD COLUMN importance TEXT DEFAULT 'medium';
ALTER TABLE deal_notes ADD COLUMN confidence TEXT DEFAULT 'stated';
ALTER TABLE deal_notes ADD COLUMN fiscal_year INTEGER;
ALTER TABLE deal_notes ADD COLUMN is_authoritative INTEGER DEFAULT 0;
ALTER TABLE deal_notes ADD COLUMN extracted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_dnotes_domain_cat ON deal_notes(domain, category);
```

Existing manual notes (author='Roman') preserved. Extracted notes use author='dr_gather'.

### deal_meetings (exists -- sufficient)

Has: `id, domain, meeting_type, meeting_date, participants, location, summary, key_topics, action_items, data_points_json, decisions, granola_meeting_id, transcript_url, created_by, created_at`. No migration needed.

### deal_contacts (exists -- sufficient)

Has: `id, domain, contact_name, role, company, email, phone, salutation, is_primary, notes, created_at`. No migration needed.

---

## 5. Pipeline Architecture

```
[1. Source Discovery]
    Scan deal_documents: qualitative files (not financial/commercial)
    Query Granola: codename + company name + alternative names
    Skip: already-extracted (mtime + granola_meeting_id check)
        |
        v
[2. Document Reading]
    docx → python-docx | PDF → pdfplumber | xlsx → openpyxl
    pptx → python-pptx | Granola → MCP API
        |
        v
[3. Fact Extraction (AI)]
    LLM reads text + deal context → discrete facts with category tags
    RFI: Q&A pairs | Granola: figures/decisions/risks | Databook: cross-check mode
        |
        v
[4. Deduplication]
    Same fact from multiple sources → store once, link both sources
    Match: domain + category + content similarity > 0.9
        |
        v
[5. Storage]
    Facts → deal_notes | Meetings → deal_meetings | Contacts → deal_contacts
    Cross-checks → deal_notes (risk_flag for deltas)
        |
        v
[6. Review Gate (light)]
    Print facts by category, new contacts, cross-check results
    Roman confirms → is_authoritative = 1
```

### Idempotency

**Granola:** Check `deal_meetings.granola_meeting_id`. If exists, delete meeting + associated `deal_notes` WHERE source LIKE `granola:{meeting_id}%`, then re-insert.

**Documents:** Delete `deal_notes WHERE source_file_id = ? AND author = 'dr_gather'`, then re-insert. Manual notes (author='Roman') never touched.

---

## 6. CLI Interface

```bash
python DEALROOM.py gather --deal Cat                      # all sources
python DEALROOM.py gather --deal Cat --source granola     # Granola only
python DEALROOM.py gather --deal Cat --source docs        # folder documents only
python DEALROOM.py gather --deal Cat --source rfi         # RFI docs only
python DEALROOM.py gather --deal Cat --dry-run            # preview without storing
python DEALROOM.py gather --deal Cat --force              # re-extract unchanged sources

python DEALROOM.py review-gather --deal Cat               # review facts by category
python DEALROOM.py review-gather --deal Cat --category risk_flag
python DEALROOM.py review-gather --deal Cat --approve
```

**Output summary format:**

```
DEALROOM gather: Cat (Medizin & Service GmbH)
===============================================
Sources processed:   7 (2 Granola + 5 documents)
Facts extracted:     72 (36 rfi_answer, 4 financial_kpi, 4 risk_flag, 4 management, ...)
Q&A pairs:           36 (6 matched to deal_questions → status='answered')
New contacts:        1 (Herr Mueller, GF)
Cross-check deltas:  0 (1 gap: employee headcount not in DB)
Deduplication:       3 facts merged

[!] Run `DEALROOM.py review-gather --deal Cat` to confirm.
```

---

## 7. Anti-Patterns

### AP-0: (Architectural) FACT-NOT-SUMMARY
The entire DR-GATHER pipeline is built on one premise: discrete, category-tagged facts are queryable; paragraph summaries are not. Every design decision -- the 12-category taxonomy, the JSON output format, the deduplication logic -- flows from this. If an extraction produces summaries instead of facts, the entire downstream chain breaks (onepager gets no structured input, scorecard gets no risk flags, RFI gap analysis has nothing to match against). This is not a style preference -- it is a structural requirement.

### AP-1: SUMMARIZE-NOT-EXTRACT
Generating summaries instead of discrete facts. "The meeting covered financials and strategy" is useless. "EBIT 2025 = EUR 380k" is a fact. **Prevention:** Prompt enforces facts-only. Post-filter rejects facts < 15 chars or lacking specificity.

### AP-2: GRANOLA-WITHOUT-CONTEXT
Querying Granola with just the codename ("Fox") misses meetings filed under "Com2Med". **Prevention:** Always query `"{company_name}" OR "{code_name}" OR "{alternatives}"`. Build query from `deals` table.

### AP-3: OVERWRITE-DB-FROM-MEETINGS
Granola says "revenue is EUR 10M" → this must NOT overwrite `deal_financials`. **Prevention:** Meeting figures → `deal_notes` with `category='financial_kpi'`. Only DR-READER writes to `deal_financials`. Cross-check: flag delta > 5% as `risk_flag`.

### AP-4: IGNORE-DOCUMENT-VERSIONS
Extracting from both RFI v1 and vAntworten → duplicates. **Prevention:** Version priority: `vAntworten` > `vS` > `v1`. Only extract from latest answer version per RFI round.

### AP-5: EXTRACT-FROM-FINANCIAL-DOCS
DR-GATHER parsing Saldenliste Sachkonten, JA, BWA -- these belong to DR-READER. **Prevention:** Filename pattern check routes financial docs away. DR-GATHER handles only Saldenliste Kundenkonten/Lieferantenkonten + qualitative docs.

### AP-6: DUPLICATE-FACTS-ACROSS-SOURCES
Same EBIT from meeting AND RFI stored twice. **Prevention:** Deduplication step matches on `domain + category + content_similarity > 0.9`. Merge into single fact with both source_refs. If values differ, keep both and flag delta.

---

## 8. Review Gate

Lighter than DR-READER/DR-COMMERCIAL. Facts are additive context, not replacing structured data. But review is required because: wrong category breaks downstream routing, inferred facts may misrepresent source, contacts may be duplicated.

```
[gather] → [summary printed] → [review-gather --deal X] → [--approve] → [is_authoritative = 1]
```

**Re-review triggers:** New Granola meeting, updated RFI response, new databook with cross-check deltas, `--force` re-extraction.

---

## 9. Cross-References

| Spec | Relationship |
|---|---|
| **DR-READER** | Sibling. DR-GATHER defers financial docs. Cross-check: meeting figures vs `deal_financials`. |
| **DR-COMMERCIAL** | Sibling. DR-GATHER defers structured xlsx. Enriches `deal_customers`/`deal_suppliers` with qualitative context. |
| **SPEC-ONEPAGER** | Downstream. Reads `deal_notes`: products, market, management, customers, employees. |
| **SPEC-OFFER** | Downstream. Reads `deal_notes`: pricing, strategy. |
| **SPEC-RFI** | Sibling + downstream. RFI answers are a DR-GATHER source. Gap analysis feeds RFI follow-up. |
| **Dashboard** | Consumer. Notes tab reads `deal_notes`. Timeline reads `deal_meetings`. |
| **IC Document** | Consumer. All fact categories feed IC sections. |
| **Scorecard** | Consumer. `risk_flag` facts feed qualitative risk assessment. |

---

## 10. Implementation Priority

**Phase 1 -- Granola + RFI responses (highest value):**
Granola meeting discovery + transcript extraction via MCP. RFI response docx parsing. Storage in `deal_notes` + `deal_meetings`. `deal_questions` status update. Test on Fox (Granola), Cat (RFI).

**Phase 2 -- Expose/CIM + Rueckfragen:**
PDF extraction for Expose. Rueckfragen follow-up parsing. Presentation (pptx) extraction. Test on Octopus (HWV_Expose.pdf).

**Phase 3 -- Databook cross-check + Saldenliste:**
Databook reading + cross-check against `deal_financials`/`deal_customers`. Saldenliste Kunden/Lieferanten PDF parsing with entity resolution. Test on Cat (databook v10 + Saldenlisten).

**Phase 4 -- Full automation:**
Automated folder scan + classification. Content similarity deduplication. Scheduled re-scan for new/updated files.

### Confidence Assessment

| Component | Confidence | Notes |
|---|---|---|
| Granola meeting discovery + transcript fetch | HIGH | MCP tools are connected, query patterns proven |
| RFI response docx parsing (Q&A pairs) | HIGH | python-docx proven, document structure is consistent |
| Fact extraction from structured Q&A | HIGH | Category assignment from Q&A pairs is deterministic |
| Fact extraction from meeting transcripts | MEDIUM | LLM-dependent, needs prompt tuning per deal type |
| Expose/CIM fact extraction | MEDIUM | PDFs vary in structure; pdfplumber handles most |
| Databook cross-check | HIGH | Mechanical comparison against DB values |
| Deduplication across sources | MEDIUM | Content similarity threshold needs calibration |
| Entity resolution for Saldenliste | MEDIUM | Depends on name overlap with existing DB records |

---

## 11. Dependencies

| Dependency | Status | Notes |
|---|---|---|
| `deal_notes` table | EXISTS (needs v5 migration) | Add category, source, source_file_id, importance, confidence, fiscal_year, is_authoritative |
| `deal_meetings` table | EXISTS | Schema v4, has `granola_meeting_id`. Sufficient. |
| `deal_contacts` table | EXISTS | Schema v4. Sufficient. |
| `deal_documents` table | EXISTS | `ingest.py` populates. DR-GATHER reads doc_type for routing. |
| Granola MCP tools | AVAILABLE | 3 tools connected. Requires active MCP session. |
| pdfplumber | EXISTS | In requirements. |
| python-docx | EXISTS | In requirements. |
| python-pptx | EXISTS | In requirements. |
| Claude CLI | EXISTS | LLM fact extraction via subprocess (OAuth). |
