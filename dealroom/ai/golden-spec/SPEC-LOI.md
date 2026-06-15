# SPEC-LOI — Template-Fill Specification

Template-fill spec for the LOI (Kaufabsichtserklärung) agent. Copies the C2M golden file and populates it with structured deal inputs + Roman's guidance on drafted sections to produce a two-column German-language LOI document.

**Template base**: C2M/Fox vS (self-contained, no Anlagen dependency, cleaner structure). HWV/Octopus vFinal used as cross-reference for multi-seller and Anlagen patterns.

**Upstream**: Stage 3 indicative offer accepted. Feeds from `deal_valuations`, `deal_data`, `deal_questions`, and Roman's negotiation notes.

**Downstream**: Signed LOI triggers Stage 5 (DD). Output filed to `3_Deals/3_Targets/<deal>/0_Vertraege und Meetings/`.

---

## 1. Structure Pattern (A-L Skeleton)

Every LOI follows this fixed clause sequence, rendered as a two-column table (label | content):

| Clause | Title | Type |
|--------|-------|------|
| A | Kaufgegenstand | DRAFTED |
| B | Kaufpreiszahlungen | TEMPLATE + SLOTS |
| C | *(wildcard — deal-specific title)* | DRAFTED |
| D | Kaufpreis und Earn-Out | SEMI-TEMPLATE |
| E | Stichtag | TEMPLATE + SLOT |
| F | Taetigkeit Verkaufer | DRAFTED |
| G | Wichtige Annahmen | SEMI-TEMPLATE |
| H | Indikativer Zeitplan | TEMPLATE + SLOTS |
| I | Exklusivitaet | TEMPLATE + SLOTS |
| J | Vertraulichkeit | TEMPLATE + SLOT |
| K | Kostenuebernahme | PURE TEMPLATE |
| L | Bindungswirkung | PURE TEMPLATE |

After L: signature block (pure template), then optional Anlagen.

---

## 2. Template Fill Map

### 2.1 Pure Template (zero variability)

Copy verbatim from C2M golden file:

- **K (Kostenuebernahme)**: Each party bears own costs. No slots.
- **L (Bindungswirkung)**: Non-binding except I, J, K. No slots.
- **Kaeuferin identification**: "Repuro GmbH, Goethestrasse 59, 10625 Berlin" (or successor entity if Repuro restructures -- verify against latest LOI before generating).
- **Signature block**: Roman Dobriakov + Florian Fischer, Repuro GmbH. Layout: two signature lines, place/date, name/role.

### 2.2 Template with Slots (high-confidence fill)

Boilerplate text with variable injection:

| Clause | Slots | Source |
|--------|-------|--------|
| E (Stichtag) | `{effective_date}` | Roman input (typically month-end, 1-3 months out) |
| J (Vertraulichkeit) | `{nda_date}` | `deal_documents` -- NDA signing date |
| I (Exklusivitaet) | `{excl_start}`, `{excl_end}`, `{excl_penalty_eur}` | Roman input. Typical: 8-12 weeks, 25k-50k € penalty |
| H (Zeitplan) | `{dd_start}`, `{dd_end}`, `{spa_target}`, `{closing_target}` | Roman input. Typical: DD 6-10 weeks post-LOI, SPA 4-6 weeks post-DD |
| B (Kaufpreiszahlungen) | `{sofortzahlung_eur}`, `{earn_out_max_eur}`, `{vd_amount_eur}` (if Verkaeuferdarlehen) | `deal_valuations` confirmed scenario |

### 2.3 Semi-Template (template structure, deal-specific content)

| Clause | Templated Part | Deal-Specific Part |
|--------|---------------|-------------------|
| D (Kaufpreis und Earn-Out) | EBIT definition paragraph, earn-out table header/footer, payment timing language | Earn-out bracket table (5-15 rows), base EBIT figure, multiplier, EBIT definition nuances (e.g. "inkl. aller etwaigen Geschaeftsfuehrergehaelter") |
| G (Wichtige Annahmen) | Standard bullets: DD-Vorbehalt, Finanzierungsvorbehalt, keine wesentlichen Veraenderungen, Wettbewerbsverbot | Deal-specific assumptions: entity-specific conditions, regulatory, key-employee retention, real estate, pending litigation |

### 2.4 Requires Drafting (low-confidence, Roman input required)

| Clause | Why It Cannot Be Templated | Input Required |
|--------|---------------------------|----------------|
| A (Kaufgegenstand) | Entity structure varies: single GmbH vs. GmbH + KGs vs. holding structures. Number of sellers, share percentages, Handelsregister references all differ. Multi-entity targets (C2M: GmbH + 2 KGs) make this clause complex. | `target_entities[]`, `sellers[]`, deal structure (share deal vs. asset deal) |
| C (Wildcard) | Completely different PURPOSE per deal: Rueckbeteiligung (HWV), Co-Med subsidiary handling (C2M), real estate carve-out, or anything else. Title and content are deal-specific. | Roman provides clause title + content brief. Agent drafts from brief. |
| F (Taetigkeit Verkaufer) | Management transition plan unique per deal: GF continues vs. transition period vs. immediate exit. Compensation terms, duration, non-compete scope all negotiated. | GF transition terms from negotiation, compensation range, duration, handover plan |

---

## 3. Data Input Schema

### 3.1 Structured Fields (from DB + deal folder)

```
deal_id:            str           # dealroom deal identifier
code_name:          str           # e.g. "Fox", "Octopus" (DB column: deals.code_name)
legal_name:         str           # e.g. "Com2Med GmbH"

target_entities: [                # 1..N entities being acquired
  {
    name:           str           # legal entity name
    legal_form:     str           # GmbH, KG, GmbH & Co. KG, etc.
    hrb_number:     str           # Handelsregister number
    amtsgericht:    str           # registering court
    registered_seat: str          # Sitz der Gesellschaft
  }
]

sellers: [                        # 1..N sellers
  {
    name:           str           # full legal name
    address:        str           # street, PLZ, city
    share_pct:      float         # percentage of shares held (must sum to 100%)
    entity_ref:     str|null      # which entity if multi-entity deal
  }
]

seller_count:       int           # derived from sellers[]. Drives singular/plural grammar.

pricing: {
  sofortzahlung_gross: int        # €, Brutto-Sofortkaufpreis at closing (same field as SPEC-OFFER)
  earn_out_max:     int           # €, maximum earn-out
  earn_out_type:    str           # "bracket_table" | "formula_cap" | "formula_floor_cap_minimum" | "two_period"
                                  # NOTE: enum values aligned with SPEC-OFFER. "two_period" is LOI-only (M&S pattern).
  earn_out_table: [               # EBIT brackets -> earn-out amounts (used when earn_out_type = "bracket_table")
    { ebit_from: int, ebit_to: int|null, earn_out: int }
  ]
  earn_out_floor_ebit: int|null   # €, EBIT threshold for formula earn-out start (aligned with SPEC-OFFER)
  earn_out_cap_ebit: int|null     # €, EBIT at which max earn-out is reached (aligned with SPEC-OFFER)
  earn_out_multiplier: float      # e.g. 5.5x — € per € above floor
  base_ebit:        int           # €, reference EBIT for earn-out calc
  vd_amount:        int|null      # €, Verkaeuferdarlehen (if applicable)
  ebit_definition:  str           # custom EBIT definition text if deviating from template
  total_consideration: int        # €, sofortzahlung_gross + earn_out_max + rueckbeteiligung (if applicable)
                                  # NOTE: gewinnausschuettung excluded (same convention as SPEC-OFFER)
}

dates: {
  effective_date:   str           # YYYY-MM-DD, Stichtag
  nda_date:         str           # YYYY-MM-DD, from deal_documents
  excl_start:       str           # YYYY-MM-DD
  excl_end:         str           # YYYY-MM-DD
  dd_start:         str|null      # YYYY-MM-DD
  dd_end:           str|null      # YYYY-MM-DD
  spa_target:       str|null      # YYYY-MM-DD
  closing_target:   str|null      # YYYY-MM-DD
}

excl_penalty_eur:   int           # €, exclusivity breach penalty
```

### 3.2 Roman Input (cannot be derived)

| Field | Description | When Needed |
|-------|-------------|-------------|
| `section_c_title` | Clause C heading (e.g. "Rueckbeteiligung", "Co-Med", "Immobilie") | Always |
| `section_c_brief` | 3-10 sentence description of clause C content | Always |
| `section_f_terms` | GF transition: role, duration, compensation, non-compete | Always |
| `deal_specific_assumptions` | Additional G-bullets beyond standard set | If applicable |
| `anlagen_list` | Which appendices to include, if any | If applicable |
| `ebit_definition_override` | Custom EBIT definition text | If deviating from C2M standard |
| `kaufgegenstand_notes` | Special entity structure notes (holding, KG structure, carve-outs) | If multi-entity or non-standard |

---

## 4. Edge Cases and Hardening Rules

### 4.1 Singular/Plural Seller Cascade

**Trigger**: `seller_count == 1` vs `seller_count > 1`

This is NOT a simple find-replace. It cascades through:

| Element | Singular | Plural |
|---------|----------|--------|
| Article | der Verkaufer | die Verkaufer |
| Pronoun | er / ihm / sein | sie / ihnen / ihr |
| Verb agreement | verpflichtet sich | verpflichten sich |
| Possessive | des Verkaufers | der Verkaufer |
| Signature block | 1 seller block | N seller blocks |
| Kaufgegenstand | "Herr X haelt 100% der Anteile" | "Die Verkaufer halten die folgenden Anteile..." + table |

**Rule**: Fill the ENTIRE document in the correct grammatical form from the start. Do NOT fill singular and then find-replace -- German morphology makes this error-prone (articles, case endings, relative clauses).

### 4.2 Section C Wildcard

Section C has NO stable structure across deals. Known variants:

| Deal | C Title | C Content |
|------|---------|-----------|
| HWV/Octopus | Rueckbeteiligung | Seller reinvests X% via Co-Invest vehicle. Detailed vesting, leaver provisions, put/call. Spawns Anlage 1. |
| C2M/Fox | Co-Med | Subsidiary handling: which sub-entity stays/goes, transition of contracts, employee allocation |

*No other Section C variants have been observed in the golden corpus. Future deals may introduce new clause types (e.g., real estate carve-outs, bridge financing) — these will be spec'd when encountered, not predicted.*

**Rule**: Agent MUST receive Roman's brief for Section C before filling. Never infer or template. If brief is missing, block the fill process and request it.

### 4.3 Optional Anlagen (Appendices)

| Trigger | Anlage | Content |
|---------|--------|---------|
| Section C = Rueckbeteiligung | Anlage 1 | Rueckbeteiligungsvereinbarung (term sheet or full agreement) |
| GF continues post-closing | Anlage 2 | GF-Vertrag Wesentliche Eckdaten (key employment terms) |
| Net debt adjustment at closing | Anlage 3 | Nettofinanzstatus Definition (line-item definition of net debt components) |

**Rule**: Anlagen are ONLY included when `anlagen_list` specifies them. C2M golden file has zero Anlagen -- this is the default. HWV pattern (3 Anlagen) is the exception. Each Anlage is a separate drafting task with its own input requirements.

### 4.4 Earn-Out Table Variability

- C2M: 5 EBIT brackets (compact, simple threshold-based)
- HWV: 15 EBIT brackets (granular, continuous adjustment formula)

**Rule**: `earn_out_table[]` array drives row count. No hardcoded table size. Table header/footer text is templated; rows are filled from the array. Verify: last bracket `ebit_to` should be `null` (open-ended "und mehr" row). Sum of earn-out column at max bracket must equal `earn_out_max`.

### 4.5 EBIT Definition Nuances

C2M adds "inklusive aller etwaigen Geschaeftsfuehrergehaelter" to EBIT definition. This is deal-specific -- depends on whether GF salary is already normalized in the model or needs explicit LOI-level definition.

**Rule**: Use `ebit_definition_override` if provided. Otherwise, use C2M standard definition. Always flag to Roman: "EBIT definition includes/excludes GF salary normalization -- confirm."

### 4.6 Multi-Entity Kaufgegenstand

C2M pattern: GmbH + 2 KGs with different ownership structures per entity. Kaufgegenstand becomes a table within the clause, not a single paragraph.

**Rule**: If `target_entities.length > 1`, generate entity table (Name, Rechtsform, HRB, AG, Anteil) within clause A. If `target_entities.length == 1`, single-paragraph form.

### 4.7 Document Production

**HARD RULE (from anti-patterns-deals.md)**: Never produce a LOI from scratch programmatically. Always:
1. Copy C2M golden file as template
2. Modify text in-place using Word COM or careful docx manipulation
3. Preserve formatting, styles, page layout, headers/footers
4. Output as `.docx` with naming: `YYMMDD_LOI_<LegalName>_v<N>.docx`

Anti-patterns that apply: EXCEL-FROM-SCRATCH, DOCX-FROM-TEMPLATE, INVENTED-FORMAT-INSTEAD-OF-COPY, OPENPYXL-CORRUPTION (for any xlsx Anlagen).

---

## 5. Confidence Assessment

### HIGH confidence -- automate fully

| Section | Confidence | Rationale |
|---------|------------|-----------|
| K (Kostenuebernahme) | 100% | Verbatim copy. Zero variability across deals. |
| L (Bindungswirkung) | 100% | Verbatim copy. Zero variability across deals. |
| Signature block | 95% | Fixed layout. Only edge case: Repuro entity name changes. |
| E (Stichtag) | 95% | Single date slot in stable boilerplate. |
| J (Vertraulichkeit) | 95% | Single NDA-date slot in stable boilerplate. |
| I (Exklusivitaet) | 90% | 3 slots (dates + penalty) in stable boilerplate. |
| B (Kaufpreiszahlungen) | 85% | Number slots in stable structure. Complexity: Verkaeuferdarlehen is optional, changes paragraph structure. |
| H (Zeitplan) | 85% | 4 date slots in stable structure. Complexity: milestone count may vary. |

### MEDIUM confidence -- produce draft, Roman reviews

| Section | Confidence | Rationale |
|---------|------------|-----------|
| D (Kaufpreis und Earn-Out) | 60% | Table generation is mechanical, but EBIT definition and bracket logic need verification. Earn-out formula language is semi-standard but has deal-specific tweaks. |
| G (Wichtige Annahmen) | 55% | Standard bullets are known, but deal-specific additions are open-ended. Risk of missing a critical assumption. |
| Singular/plural cascade | 50% | Mechanical but high surface area for German grammar errors. Requires careful proofreading pass. |

### LOW confidence -- Roman must provide input, review closely

| Section | Confidence | Rationale |
|---------|------------|-----------|
| A (Kaufgegenstand) | 25% | Entity structure varies too much. Multi-entity deals require legal precision Claude cannot guarantee. |
| C (Wildcard) | 10% | No stable template. Content is negotiation-outcome-dependent. |
| F (Taetigkeit Verkaufer) | 20% | Transition plans are unique. Compensation terms are negotiated. Non-compete scope varies. |
| Anlagen | 15% | Each Anlage is essentially a separate document with its own complexity. |

### Overall automation estimate

~60% of the LOI by character count can be filled from template + structured data with high confidence. ~25% can be drafted for review. ~15% requires Roman's substantive input before the fill process runs.

---

## 6. Template-Fill Workflow

```
1. COLLECT
   - Read deal_valuations (confirmed scenario) for pricing
   - Read deal_data for entity details, seller info
   - Read deal_documents for NDA date
   - Request Roman input: Section C brief, Section F terms, deal-specific assumptions

2. VALIDATE
   - seller_count matches sellers[] length
   - earn_out_table max equals earn_out_max
   - all dates are future (warn if not)
   - target_entities all have HRB + Amtsgericht
   - pricing.sofortzahlung + pricing.earn_out_max == pricing.total_consideration (hard check — fail if mismatch)

3. FILL
   - Copy C2M golden file
   - Fill pure-template sections (K, L, sig block)
   - Fill slot-template sections (E, J, I, H, B) with validated data
   - Populate earn-out table for D from earn_out_table[]
   - Draft A from target_entities[] + sellers[] (present to Roman)
   - Draft C from section_c_brief (present to Roman)
   - Draft F from section_f_terms (present to Roman)
   - Apply singular/plural cascade based on seller_count
   - Add Anlagen if anlagen_list is non-empty

4. REVIEW GATES
   - Gate 1: Roman reviews A, C, F drafts before they're inserted
   - Gate 2: Roman reviews complete document (all sections assembled)
   - Gate 3: Proofread pass -- singular/plural consistency, number formatting,
     entity names exact match to Handelsregister, dates internally consistent

5. OUTPUT
   - Save as YYMMDD_LOI_<LegalName>_v1.docx
   - File to 3_Deals/3_Targets/<deal>/0_Vertraege und Meetings/
   - Update deal_documents with doc type = 'loi_draft'
```

---

## 7. Dependencies

### DB Tables

| Table | Fields Used | Purpose |
|-------|-------------|---------|
| `deals` | deal_id, code_name, legal_name, stage | Deal identification, stage validation (must be post-Stage 3) |
| `deal_valuations` | scenario rows (sofortzahlung, earn_out, multiplier, base_ebit) | Pricing data for B, D |
| `deal_data` | entity info, seller info, financials | Entity details for A, financial refs for D/G |
| `deal_documents` | NDA record (signing date) | NDA date for J |
| `deal_questions` | GF transition answers | Input for F drafting |

### Prior Stage Outputs

| Output | From Stage | Used In |
|--------|-----------|---------|
| Confirmed valuation scenario | Stage 2.3 (post-Roman/Flo gate) | Pricing: B, D |
| Net debt bridge | Stage 2.2 | May appear in Anlagen (Nettofinanzstatus) |
| GF transition terms | Stage 2 RFI / management calls | Section F |
| Indicative offer (accepted) | Stage 3.1 | Cross-check: LOI pricing must match accepted offer |
| Negotiation notes | Stage 3 iteration | Section C content, deal-specific assumptions |

### Golden Files

| File | Role |
|------|------|
| C2M/Fox vS LOI | PRIMARY template -- copy for every new LOI |
| HWV/Octopus vFinal LOI | REFERENCE for multi-seller patterns, Anlagen structure, 15-bracket earn-out |

### Anti-Patterns (must be loaded by agent)

From `anti-patterns-deals.md`: EXCEL-FROM-SCRATCH, DOCX-FROM-TEMPLATE, OPENPYXL-CORRUPTION, INVENTED-FORMAT-INSTEAD-OF-COPY, CONFIDENTIAL-LEAK, SUBSTANCE-ONLY-REVIEW, IGNORE-STATED-FORMAT.

From `anti-patterns.md` (global): READ-BEFORE-ACTING, VERIFY-BEFORE-DONE.

---

## 8. Template Registry Entry

Add to `DEAL_DELIVERABLES_SPEC.md` Template Registry:

| Deliverable | Template Path | Notes |
|---|---|---|
| LOI (Kaufabsichtserklaerung) | `config/golden/loi/` (C2M vS = primary template) | Two-column table format, A-L clauses. C2M = base (no Anlagen). HWV = reference for Anlagen pattern. |
