# SPEC-NDA — Template-Fill Specification

Template-fill spec for NDA (Vertraulichkeitsvereinbarung) document production. Copies a cleaned bilateral template and populates it with 6 variable fields. Extracted from golden corpus: signed IST Medical (23.03.2026) + Sonowied (15.04.2026) NDAs, cross-referenced against NDA_Template.docx.

---

## 1. Overview

Simplest template-fill process in the dealroom pipeline. Pure template fill — 6 variable fields, identical body text across all signed instances. No conditional logic, no computed fields, no financial data.

**Trigger**: Stage 1 (Initial Contact) — after target agrees to enter mutual due diligence. Typically sent before any financials are exchanged.

**Output**: `.docx` bilateral NDA ready for Roman's review and dual signature.

---

## 2. Variant Selection

The golden corpus contains two distinct NDA variants. They are NOT interchangeable.

| Variant | Use Case | Parties | Source |
|---|---|---|---|
| **Bilateral (mutual)** | M&A targets — standard for all deal targets | "Vertragsparteien" (equal) | Signed IST Medical / Sonowied |
| **Unilateral (one-way)** | Advisors / consultants | "Offenlegende Partei" + "Berater" | NDA_Template.docx |

**Default**: Bilateral. This is what Repuro sends to deal targets. The unilateral template is a separate document with different structure, obligations, and liability scope — it must NOT be used as the source for target NDAs.

**Decision needed from Roman**: Confirm bilateral is the standard for all targets. If unilateral is also needed for advisors, that becomes a second template-fill process (separate spec).

### Key Structural Differences

| Aspect | Bilateral (Signed) | Unilateral (Template) |
|---|---|---|
| S2 heading | "Verpflichtungen der Parteien" | "Verpflichtungen des Beraters" |
| S2 content | 5 sub-paragraphs | 7 sub-paragraphs (incl. purpose limitation + cloud security) |
| S6 liability | Both parties liable | Only Berater liable |
| S7 governing law | Gerichtsstand Berlin only | Explicit German law clause + Gerichtsstand |
| Affiliated companies | NOT third parties | ARE third parties |
| Return/destroy deadline | No deadline specified | 14-day deadline |

---

## 3. Document Structure — Bilateral Version

7 sections, fixed text. Paragraph numbers reference the signed IST Medical version.

| Section | Paragraphs | Content |
|---|---|---|
| Title | P[0] | "VERTRAULICHKEITSVEREINBARUNG" — centered, bold, 14pt Arial |
| Parties block | P[4–14] | Repuro GmbH (fixed) + Target (variable fields) + "Vertragsparteien" designation |
| Praambel | P[15–18] | Mutual disclosure purpose: potential Beteiligung |
| S 1 — Vertrauliche Informationen | P[19–30] | Scope of confidential info, enumeration (7 categories), 4 exclusions |
| S 2 — Verpflichtungen der Parteien | P[31–47] | Secrecy obligation, permitted disclosure, forced disclosure, return/destroy |
| S 3 — Umfang der Vereinbarung | P[48–51] | No additional rights granted |
| S 4 — Haftungsausschluss | P[52–55] | No liability for accuracy/completeness of disclosed information |
| S 5 — Dauer | P[56–59] | 3-year duration from signing |
| S 6 — Rechtsfolgen | P[60–67] | Both parties liable for breach, UWG reference |
| S 7 — Schlussbestimmungen | P[68–77] | Schriftform, Salvatorische Klausel, Gerichtsstand Berlin |
| Signature block | P[78–89] | Berlin + target city, date, signature lines for both parties |

**Body text (P[15–77]) is identical across all signed versions.** Zero variation. Only the parties block and signature block contain variable fields.

---

## 4. Data Input Schema

6 variable fields. All string type.

```
# Target side (variable per deal)
target_company_name: str       # e.g. "IST Medical GmbH"
target_street: str             # e.g. "Robert-Bosch-Strasse 10"
target_plz_city: str           # e.g. "89191 Nellingen/Alb"
target_representative: str     # e.g. "Konrad Loosl"
target_representative_role: str  # e.g. "Geschaftsfuhrer" (always so far)
signing_date: str              # DD.MM.YYYY format, e.g. "23.03.2026"

# Repuro side (fixed — but configurable for entity changes)
repuro_entity: str = "Repuro GmbH"
repuro_address: str = "Goethestrasse 59, 10625 Berlin"
repuro_representative: str = "Florian Fischer"
repuro_representative_role: str = "Geschaftsfuhrer"
```

**Source**: Target fields come from dealroom record (HubSpot CRM or manual input). Signing date set at fill time or left as placeholder for Roman to fill.

**Validation rules**:
- `target_company_name`: required, non-empty
- `target_street`: required, non-empty
- `target_plz_city`: required, must match pattern `\d{5}\s+.+` (German PLZ + city)
- `target_representative`: required, non-empty
- `signing_date`: required, must match `DD.MM.YYYY` or literal placeholder `"[DATUM]"`

---

## 5. Template Fill Map

Paragraph-level locations in the signed IST Medical source document. Body text paragraphs are untouched — only these locations receive variable content.

| Paragraph | Current Content (IST Medical) | Replacement |
|---|---|---|
| P[10] | `IST Medical GmbH` | `{target_company_name}` |
| P[11] | `Robert-Bosch-Strasse 10, 89191 Nellingen/Alb` | `{target_street}, {target_plz_city}` |
| P[12] | `vertreten durch den Geschaftsfuhrer Konrad Loosl` | `vertreten durch den {target_representative_role} {target_representative}` |
| P[82] | Date/location line (example: IST Medical reads "Berlin / Nellingen/Alb, den 23.03.2026") | `Berlin / {target_city}, den {signing_date}` — extract city from `target_plz_city` |
| P[88] | `Konrad Loosl` (target signature name) | `{target_representative}` |

**Note on P[82]**: The city in the date line is extracted from `target_plz_city` (everything after the PLZ). E.g., `"89191 Nellingen/Alb"` → city = `"Nellingen/Alb"`.

**Repuro-side fields** (P[4–8], P[84–85]) are already correct in the template and should NOT be modified unless the Repuro entity changes. Keep them configurable but default to current values.

---

## 6. Implementation Approach

### 6.1 Template Source

Use a **cleaned copy of a signed version** (IST Medical or Sonowied) as the base template. NOT the NDA_Template.docx (that is the unilateral variant).

**Cleaning steps** (one-time, manual):
1. Strip scanned signature images from P[84] area
2. Replace target-specific text with placeholder markers (e.g., `{{target_company_name}}`)
3. Fix footer page number if hardcoded (see Edge Cases)
4. Save as `NDA_Bilateral_Template.docx` in `dealroom/config/golden/nda/`

### 6.2 Fill Method

**python-docx run-level text replacement** within existing runs. This preserves all formatting (font, size, alignment, bold) because formatting lives on runs, not on the text content.

```python
# Pseudocode — actual implementation in fill script
from docx import Document

def fill_nda(template_path: str, output_path: str, fields: dict) -> str:
    doc = Document(template_path)
    
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            for placeholder, value in fields.items():
                if placeholder in run.text:
                    run.text = run.text.replace(placeholder, value)
    
    doc.save(output_path)
    return output_path
```

**Critical constraint**: Placeholders must fall within a SINGLE run. If python-docx splits a placeholder across multiple runs (common with formatting changes mid-word), the replacement silently fails. 

**Mitigation**: After creating the template, verify each placeholder is in exactly one run:
```python
for p in doc.paragraphs:
    for run in p.runs:
        if '{{' in run.text:
            print(f"P[{doc.paragraphs.index(p)}]: {run.text}")
```

If a placeholder is split across runs, consolidate the runs in the template (re-type the placeholder without interrupting formatting).

### 6.3 Output

- Filename convention: `YYMMDD_Vertraulichkeitsvereinbarung_{target_short_name}.docx`
- Save to: deal folder `3_Deals/3_Targets/{deal_folder}/1_NDA/`
- Target short name = company name without legal suffix (e.g., "IST Medical" not "IST Medical GmbH")

---

## 7. Edge Cases & Hardening

| # | Issue | Mitigation |
|---|---|---|
| 1 | **Long company names** (Sonowied = 67 chars) wrapping in signature block | Template signature block uses small enough font + wide enough column. Test with 80-char name. If wrapping breaks layout, reduce font size in signature line run to 9pt. |
| 2 | **Scanned signature image** in source template | Strip during template cleaning (6.1). Generated drafts must never contain prior signatures. |
| 3 | **Footer page number hardcoded "2"** | Remove hardcoded footer or make dynamic. Check `doc.sections[0].footer` during template cleaning. |
| 4 | **Repuro entity name change** (was "i.Gr." → now "GmbH") | Entity name is a configurable field, not hardcoded in the fill script. Future change = update default value. |
| 5 | **Target city extraction from PLZ string** | Regex: `re.match(r'\d{5}\s+(.+)', target_plz_city).group(1)`. Fail loudly if pattern doesn't match. |
| 6 | **Umlaute in company names** (e.g., Vertriebs- und Beratungsgesellschaft fur Sonographische Systeme) | python-docx handles Unicode natively. No special handling needed. Ensure template file is saved as .docx (not .doc). |
| 7 | **Multiple representatives** | Current schema assumes single representative per side. If a target has co-GFs, extend `target_representative` to accept list. Not seen in corpus yet — defer until needed. |
| 8 | **Placeholder not found** (typo or run-split) | Fill script must raise explicit error if any placeholder remains in output document. Post-fill scan: search all runs for `{{` and fail if found. |

---

## 8. Confidence Assessment

**VERY HIGH** — simplest template-fill process in the pipeline.

| Dimension | Assessment |
|---|---|
| Template stability | Identical body text across 2 signed versions spanning 3 weeks. No variation. |
| Field count | 6 variable fields. No computed values, no conditionals. |
| Formatting risk | Low — replacement within existing runs preserves all formatting. |
| Implementation complexity | ~50 lines of Python. Single function, no dependencies beyond python-docx. |

**Only risk**: python-docx run splitting. Mitigated by template verification step (6.2). If a placeholder is split, it is detectable and fixable in the template — not a runtime issue.

**Open decision**: Roman to confirm bilateral is the only variant needed for targets. If unilateral is also needed, it is a separate template-fill process with a separate spec (different structure, different fields, different obligations).

---

## 9. Anti-Patterns

### DOCX-FROM-TEMPLATE (critical)
**Never produce an NDA from scratch.** Always use the cleaned bilateral template as source. The formatting (font sizes, paragraph spacing, header alignment, signature block layout) has been refined across multiple signed versions. Producing from scratch programmatically will produce visually different output.

### INVENTED-FORMAT-INSTEAD-OF-COPY (critical)
**Never invent NDA clause language.** The body text is legally reviewed and identical across all signed versions. Copy verbatim — do not paraphrase, reorder, or "improve" any clause.

### CONFIDENTIAL-LEAK (critical)
**Never include deal-specific financial data in an NDA.** The NDA is a standalone confidentiality agreement with zero deal content. If target information beyond the 6 variable fields somehow enters the document, the fill script has a bug.

### PLACEHOLDER-SPLIT (medium — specific to python-docx)
**python-docx may split placeholder text across multiple runs.** A `{{target_company_name}}` placeholder that looks like one string in Word may be stored as `{{target_` + `company_name}}` internally. The fill script must verify each placeholder is in a single run after template creation. See Section 6.2 for the verification procedure.

---

## 10. Template-Fill Workflow

```
1. COLLECT
   - Read deal record for: company name, address, representative, representative role
   - Determine signing date (Roman input or "[DATUM]" placeholder)
   - Confirm variant = bilateral (default for all targets)

2. VALIDATE
   - target_company_name: non-empty
   - target_plz_city: matches \d{5}\s+.+ pattern
   - signing_date: DD.MM.YYYY or "[DATUM]"
   - All 6 fields present and non-null

3. FILL
   - Copy NDA_Bilateral_Template.docx to temp file
   - Replace all {{placeholder}} markers with validated field values
   - Extract city from target_plz_city for date line

4. VERIFY (automated)
   - Scan all runs for remaining {{ markers — fail if any found
   - Verify output file size > 10KB (catch empty/corrupt output)
   - Verify paragraph count matches template (no paragraphs added/removed)

5. REVIEW GATE
   - Present filled NDA to Roman for review before filing
   - Roman confirms: correct target details, correct variant, no placeholder remnants
   - Only after Roman confirmation: save to deal folder

6. OUTPUT
   - Save as YYMMDD_Vertraulichkeitsvereinbarung_{target_short_name}.docx
   - File to 3_Deals/3_Targets/{deal_folder}/1_NDA/
   - Update deal_documents with doc type = 'nda_bilateral'
```

---

## 11. Dependencies

| Dependency | Status | Notes |
|---|---|---|
| `python-docx` | Available | Already used in dealroom pipeline |
| Cleaned bilateral template | **CREATED** (config/golden/nda/NDA_Bilateral_Template.docx) | Created from signed IST Medical .docx: signatures stripped, 7 placeholders inserted, single-run verified |
| Deal folder structure | Exists | `1_NDA/` subfolder standard in all target folders |
| Dealroom record fields | Exists | Company name, address, representative available from HubSpot or manual entry |

### Pre-implementation checklist

- [ ] Roman confirms bilateral = standard for all targets
- [ ] Select source signed NDA (IST Medical recommended — shorter company name, cleaner)
- [ ] Clean template: strip signatures, insert `{{placeholders}}`, fix footer
- [ ] Verify all placeholders are single-run in cleaned template
- [x] Save as `NDA_Bilateral_Template.docx` in `dealroom/config/golden/nda/`
