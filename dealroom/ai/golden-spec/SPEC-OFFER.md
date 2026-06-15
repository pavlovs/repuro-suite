# SPEC-OFFER: Indikatives / Aktualisiertes / Finales Angebot — Template-Fill Specification

Template-fill specification for the Offer (Angebot) agent. Produces German-language acquisition offer letters by copying a golden template and populating it with deal data + Roman's input on deal-specific content. Repuro (buyer) sends these to target companies.

**Template base**: Golmed/Lion vSent (260518) — most recent, clean structure, single entity, standard earn-out, Gewinnausschuettung variant. HWV/Octopus used as cross-reference for Rueckbeteiligung, multi-GF, bracket earn-out, and Auszahlung Liquiditaet patterns. M&S/Cat vS used as cross-reference for Finales Angebot, Nettofinanzstatus, two-year earn-out, and subsidiary EBIT consolidation.

**Upstream**: Stage 2.3 (confirmed valuation scenario + earn-out structure approved by Roman + Flo). Feeds from `deal_valuations`, `deal_data`, `deal_questions`, and Roman's GF transition notes.

**Downstream**: Accepted offer triggers LOI (Stage 4). Output filed to `3_Deals/3_Targets/<deal>/3_Indikatives Angebot/`.

---

## 1. Overview

**What this produces**: A German-language letter-format offer document setting out the commercial terms on which Repuro proposes to acquire 100% of the target entity. Non-binding. Sent by email as PDF; working copy retained as .docx.

### Offer Type Taxonomy

| Type | German Title | When Sent | Stage |
|------|-------------|-----------|-------|
| Indikatives Angebot (IO) | "Indikatives Angebot fuer eine Beteiligung an der [X]" | First offer, terms subject to DD confirmation | Stage 3.1 |
| Aktualisiertes Angebot | "Aktualisiertes Angebot fuer eine Beteiligung an der [X]" | Revised offer after negotiation or new data | Stage 3.2+ |
| Aktualisiertes indikatives Angebot | "Aktualisiertes indikatives Angebot fuer eine Beteiligung an der [X]" | Updated but still indicative — Golmed pattern | Stage 3.2, pre-LOI |
| Finales Angebot | "Finales Angebot fuer eine Beteiligung an der [X]" | Commercial lever: Repuro's best and final position | Stage 3.x, near-LOI |

Note: "Finales Angebot" is commercial signaling, not a legal distinction — M&S Finales golden file is structurally identical to Aktualisiertes. The title changes; sections do not.

**Rule**: The fill process accepts explicit `offer_type` input — never infer from iteration count. Roman decides.

### Upstream / Downstream

```
[Stage 2.3 confirmed valuation scenario (Roman + Flo gate)]
        |
        v
[COLLECT: DB pricing + seller data + Roman input]
        |
        v
[VALIDATE: arithmetic, scope consistency, gating Roman inputs present]
        |
        v
[FILL: copy Golmed golden, populate template sections, draft low-confidence sections]
        |
        v
[REVIEW GATES: arithmetic gate -> intro gate -> drafted sections gate -> full doc]
        |
        v
[OUTPUT: .docx + PDF export + file to deal folder]
        |
        v
[Accepted offer -> LOI (SPEC-LOI.md) at Stage 4]
```

---

## 2. Structure Pattern (Section Skeleton)

Offer is a prose letter — NOT a two-column table (that is the LOI format). Sections are separated by **bold inline labels** in the running text.

| # | Section | Label | Type |
|---|---------|-------|------|
| H | Recipient address block | (no label) | TEMPLATE + SLOTS |
| D | Date | "Berlin, DD.MM.YYYY" | TEMPLATE + SLOT |
| T | Subject line (Betreff) | bold letter heading | SEMI-TEMPLATE |
| A | Salutation | "Sehr geehrter/geehrte..." | SEMI-TEMPLATE |
| I | Intro paragraph(s) | (no label — body text) | DRAFTED |
| L | Lead-in sentence | (no label — last intro line) | SEMI-TEMPLATE (2 variants) |
| S | Strategie | **Strategie:** + 5 bullets | SEMI-TEMPLATE |
| KG | Kaufgegenstand | **Kaufgegenstand:** | TEMPLATE + SLOTS |
| ST | Wirtschaftlicher Stichtag | **Wirtschaftlicher Stichtag:** | TEMPLATE + SLOT |
| KP | Kaufpreis summary | **Kaufpreis:** | SEMI-TEMPLATE |
| RB | *(optional)* Rueckbeteiligung | **Rueckbeteiligung** | DRAFTED |
| LQ | *(optional)* Auszahlung Liquiditaet | **Auszahlung nicht-betriebsnotwendige Liquiditaet** | SEMI-TEMPLATE |
| SK | *(optional)* Sofortkaufpreis detail | **Sofortkaufpreis:** | SEMI-TEMPLATE |
| EZ | Erfolgszahlung | **Erfolgszahlung:** or **Erfolgszahlungen:** | SEMI-TEMPLATE |
| RO | Rolle GF | **Rolle [Name]:** | SEMI-TEMPLATE |
| WA | Wichtige Annahmen | **Wichtige Annahmen:** + bullets | SEMI-TEMPLATE |
| WP | *(conditional)* Weiterer Prozess | **Weiterer Prozess** | TEMPLATE |
| SC | Closing paragraph | (no label) | PURE TEMPLATE |
| FC | Farewell line | (no label) | PURE TEMPLATE |
| SB | Signature block | (no label) | PURE TEMPLATE |
| AN | Anhaenge | **Anhang N:** ... | SEMI-TEMPLATE |

Section 7 (Weiterer Prozess) is absent in earliest IO versions (HWV IO pattern) and present in all updated/final offers. Default for new offers: include it.

---

## 3. Template Fill Map

### 3.1 Pure Template (zero variability — copy verbatim)

| Section | Content | Confirmed Verbatim Across |
|---------|---------|--------------------------|
| Closing paragraph | "Wir sind ueberzeugt, dass diese Transaktion erheblichen Mehrwert fuer beide Seiten schafft, und freuen uns, auf dieser Basis gemeinsam die naechsten Schritte gehen zu koennen." | M&S, Golmed, HWV |
| Farewell | "Fuer etwaige Fragen vorab stehen wir selbstverstaendlich gerne zur Verfuegung." | M&S, Golmed, HWV |
| Signature block | Roman Dobriakov + Florian Fischer, Geschaeftsfuehrer, two signature lines with underline dashes | M&S, Golmed, HWV |
| Weiterer Prozess bullets 1-2 | LOI purpose sentence + DD scope sentence (4 areas: Geschaeftsmodell, Finanzen, Recht, Steuern) | M&S, Golmed |
| Weiterer Prozess bullet 3 | "Die Repuro Gruppe arbeitet hier mit externen Beratern zusammen, mit denen sie bereits in der Vergangenheit erfolgreiche Transaktionsabschluesse durchfuehrte." | M&S, Golmed |
| Strategie bullets 3-5 | "Anorganisches Wachstum durch standardisierten M&A-Prozess und Zukaeufe" + "Partnerschaftlicher und vertrauensvoller Ansatz zur gemeinsamen Wertschaffung mit den Geschaeftsfuehrern unserer Partnerunternehmen" + "Nachhaltige Loesungsansaetze als zentrales Element zur langfristigen Kundenbindung und als Basis fuer zukuenftiges Wachstum" | M&S, Golmed |

Note: HWV Strategie bullets 3-5 are functionally identical but with minor wording variation ("fuehrender Unternehmen" vs. "starker Unternehmen"). Golmed/M&S wording is the current standard — use that.

### 3.2 Template with Slots (high-confidence fill)

| Section | Slot(s) | Source |
|---------|---------|--------|
| Recipient header block | `{company_name}`, `{seller_salutation_name(s)}`, `{street}`, `{plz_city}` | `target_entities[0]`, `sellers[]` |
| Date line | `{letter_date}` (DD.MM.YYYY) | Roman input — date letter is sent |
| Salutation | `{gf_salutation(s)}` — see §6.2 for singular/plural cascade | `sellers[]` |
| Kaufgegenstand | `{legal_name}` x2, `{subsidiary_name}` if applicable, `{deal_structure}` (default "Anteilskauf oder 'Share Deal'") | `target_entities[]` |
| Wirtschaftlicher Stichtag | `{effective_date}` (DD.MM.YYYY) | `pricing.effective_date` — always 01.01.YYYY in practice |
| Kaufpreis total line | `{total_consideration_eur}` | Sum: sofortzahlung + earn_out_max + rueckbeteiligung (NOT gewinnausschuettung) |
| Sofortzahlung bullet | `{sofortzahlung_eur}` label line | `pricing.sofortzahlung_gross` |
| Earn-out max bullet | `{earn_out_max_eur}` label line | `pricing.earn_out_max` |
| Earn-out payment trigger | `{payment_trigger_year}` in payment timing sentence | Roman input |

### 3.3 Semi-Template (fixed structure, deal-specific content)

| Section | Templated Part | Deal-Specific Part | Confidence |
|---------|---------------|-------------------|------------|
| Subject line | "[Type] Angebot fuer eine Beteiligung an der [X]" | Offer type word, company name, optional short form in parens | 90% |
| Strategie bullet 1 | "Aufbau einer marktfuehrenden Unternehmensgruppe im Bereich [sector] durch Buendelung [adj] Unternehmen" | Sector phrase and adjective — see §6.11 | 80% |
| Strategie bullet 2 | "Schaffung von [adj] Gruppenvorteilen (z.B. [examples]) und einer konsequenten KI- & Digitalisierungsstrategie" | Adjective (umfangreichen vs. starken) and examples | 75% |
| Lead-in sentence | Two variants: "bitte finden Sie die aktualisierten Eckpunkte..." or "Wir koennen Ihnen / schlagen...folgende Eckpunkte...anbieten/vor" | See §6.3 for intro variant logic | 70% |
| Kaufpreis summary | "Kaufpreis in Hoehe von bis zu [X] €, aufgeteilt in [zwei / folgende] Komponenten:" + component bullets | Component count and amounts; "folgende" replaces "zwei" when 3+ components | 80% |
| Erfolgszahlung (formula type) | EBIT definition sentence; formula sentence structure; payment timing sentence | Floor, multiplier, cap, measurement period (1 yr vs. avg 2 yrs), EBIT scope | 60% |
| Erfolgszahlung (bracket type) | "Das EBIT bezeichnet hierbei..." definition paragraph | EBIT bracket rows (12+ rows for HWV; 5 for C2M) | 65% |
| Sofortkaufpreis detail (Final) | Nettofinanzstatus paragraph structure | Preliminary net price figure, Anhang reference | 55% |
| Rolle GF (simple retention) | "[GF] verbleibt/bleibt nach der Transaktion Geschaeftsfuehrer der [X]" + contract term + salary bullets | Contract end date, FTE%, salary, Tantieme, special terms | 65% |
| Wichtige Annahmen (standard bullets) | Bullet 1 (Finanzzahlen bereinigt), Bullet: Keine Kuendigungen | JA timing wording; whether "mindestens vorlaeufig" or final JA required | 70% |
| Weiterer Prozess (with addon) | Bullets 1-3 verbatim | Bullet 4 (deal-specific JA condition) — present in Golmed, absent in M&S | 80% |

### 3.4 Requires Drafting (low-confidence — Roman input mandatory)

| Section | Why Not Templatable | Input Required |
|---------|--------------------|-|
| Intro paragraph(s) | Tone and framing are fully situation-specific. Wrong tone damages trust with seller. | Roman: 2-5 sentence brief on current situation, relationship, what changed |
| Rueckbeteiligung section | Complex financial instrument — amount, vehicle, vesting, leaver provisions, Wettbewerbsverbot, Anhang reference. Present only in HWV. | Roman provides key commercial terms; spawns Anhang 1 |
| GF transition (complex) | Multi-GF (HWV), phased reduction (Golmed), successor hire with VSOP (C2M) — not templatable. | Per-GF: role, FTE%, salary, Tantieme, contract end, special provisions |
| Wichtige Annahmen (deal-specific bullets) | Every deal has unique operational/legal conditions discovered in RFI or negotiation. Inventing them creates contractual risk. | Roman provides list of conditions to include (property, legacy liabilities, family salaries, pension, factoring, employee protection, etc.) |
| Anhaenge content | Each Anhang is a separate document: Rueckbeteiligung terms, GF-Vertrag key points, Nettofinanzstatus calculation, EBIT calculation. | Roman specifies which Anhaenge needed; provides data for each |

---

## 4. Intro Paragraph Variants

Three distinct intro patterns found in corpus. The fill process must route to the correct variant by `offer_type` + Roman's context:

**Variant A — Indikativ, warm first approach** (Golmed pattern):
```
"im Folgenden moechten wir Ihnen unser ausdrueckliches Interesse an einer Beteiligung
an der [X] darstellen.

Wir sehen enormes Potential mit unserem Ansatz im dynamischen Gesundheitsmarkt. [X] waere
dabei fuer uns ein wichtiger Eckpfeiler, um eine fuehrende Gruppe aufzubauen. Als Teil der
Repuro Gruppe wird [X] [Roman provides 1-2 sentence value prop / partnership angle].
Wir koennen Ihnen folgende Eckpunkte fuer eine gemeinsame Transaktion anbieten:"
```

**Variant B — Aktualisiert, specific issue addressed** (HWV pattern):
```
"wie besprochen, moechten wir Ihnen unser aktualisiertes Angebot senden mit einigen
ergaenzten Formulierungen, um die von Ihnen genannten Punkte klarer darzustellen.

Wir schlagen daher die folgenden Eckpunkte fuer eine gemeinsame Transaktion vor:"
```

**Variant C — Aktualisiert/Final, neutral update** (M&S pattern):
```
"bitte finden Sie die aktualisierten Eckpunkte fuer eine gemeinsame Transaktion anbei:"
```
(Single sentence, no preceding paragraph — appropriate when update is minor or relationship is advanced)

**Rule**: Never auto-select Variant A without Roman providing the value-prop sentences. The company-specific partnership angle in Variant A cannot be templated. Block the fill process and request brief if Variant A is selected and no intro_brief provided.

---

## 5. Data Input Schema

### 5.1 Structured Fields (from DB + deal folder)

```
deal_id:              str           # dealroom deal identifier
code_name:            str           # e.g. "Lion", "Octopus" (DB column: deals.code_name)
legal_name:           str           # e.g. "GOLMED GmbH"
shortname:            str|null      # abbreviated name for Betreff e.g. "M&S", null = use full name

offer_type:           enum          # "IO" | "Aktualisiertes" | "Aktualisiertes_Indikatives" | "Finales"
letter_date:          str           # DD.MM.YYYY — date letter is sent

target_entities: [                  # 1..N entities
  {
    name:             str           # legal entity name
    legal_form:       str           # GmbH, KG, GmbH & Co. KG
    role:             str           # "primary" | "subsidiary" | "co_entity"
  }
]
# Offer does NOT need HRB/Amtsgericht — those are LOI-level details

sellers: [                          # 1..N sellers / GFs receiving the letter
  {
    salutation:       str           # "Herr" | "Frau"
    last_name:        str
    first_name:       str
    address:          str           # street + number
    plz:              str
    city:             str
    role:             str           # "GF" | "Gesellschafter" | "GF_and_Gesellschafter"
  }
]

pricing: {
  effective_date:     str           # DD.MM.YYYY — Wirtschaftlicher Stichtag
  total_consideration: int          # € — sum of sofortzahlung + earn_out_max + rueckbeteiligung
                                    # NOTE: gewinnausschuettung is NOT in total_consideration
  sofortzahlung_gross: int          # € — Brutto-Sofortkaufpreis
  sofortzahlung_type: enum          # "fixed" | "formula_adjusted" | "nettofinanzstatus_adjusted"
  nettofinanzstatus_preliminary: int|null  # € — preliminary net price (Final offer only)
  adjustment_base_ebit: int|null    # € — reference EBIT for formula adjustment (HWV/C2M)
  adjustment_multiplier: float|null # e.g. 5.0 (€ per € deviation)
  adjustment_tolerance: int|null    # € — tolerance band before adjustment triggers (e.g. 10000)
  earn_out_max:       int           # € — maximum earn-out
  earn_out_type:      enum          # "bracket_table" | "formula_cap" | "formula_floor_cap_minimum"
  earn_out_periods:   int           # 1 = single year; 2 = avg of 2 years or two separate earn-outs
  earn_out_year_1:    int           # YYYY
  earn_out_year_2:    int|null      # YYYY — only if earn_out_periods >= 2
  earn_out_payment_year: int        # YYYY of Jahresabschluss that triggers payment
  earn_out_table: [                 # earn_out_type == "bracket_table" only
    { ebit_from: int, ebit_to: int|null, earn_out: int }
    # last row: ebit_to must be null ("oder mehr")
  ]
  earn_out_floor_ebit: int|null     # € — EBIT threshold for formula earn-out start
  earn_out_multiplier: float|null   # € per € above floor (formula types)
  earn_out_cap_ebit:  int|null      # € — EBIT at which max earn-out is reached
  earn_out_minimum:   int|null      # € — minimum earn-out if EBIT >= floor (Golmed pattern)
  rueckbeteiligung:   int|null      # € — seller reinvestment amount (HWV pattern)
  gewinnausschuettung: int|null     # € — pre-closing dividend (Golmed pattern)
                                    # NOT in total_consideration; handled separately in body
  vd_amount:          int|null      # € — Verkaeuferdarlehen (rarely in Angebot; more common in LOI)
  ebit_scope:         str           # "single_entity" | "konsolidiert" (multi-entity)
  ebit_definition_addons: [str]     # default: ["management_fees", "einmaleffekte", "synergien"]
                                    # optional: "gf_gehaelter" (C2M pattern)
}

gf_transition: [                    # per GF/seller — 1..N entries
  {
    name:             str           # full name (for section label "Rolle Herr X:")
    salutation:       str           # "Herr" | "Frau"
    last_name:        str
    continues_as_gf:  bool
    contract_end:     str           # YYYY-MM-DD
    fte_pct_initial:  int           # e.g. 100
    fte_pct_after:    int|null      # if FTE reduces (Golmed: 60-80%)
    fte_reduction_date: str|null    # YYYY-MM-DD (Golmed: 01.01.2027)
    salary_fixed:     int           # € annual
    salary_tantieme:  int           # € approx
    special_terms:    str|null      # e.g. "Beraterrolle auf Repuro-Ebene", "VSOP"
  }
]
```

### 5.2 Roman Input Fields (cannot be derived from DB)

| Field | Description | When Needed |
|-------|-------------|-------------|
| `intro_brief` | Current situation: tone, references to prior discussions, what changed, seller concerns | Always |
| `strategie_sector_phrase` | Sector description for bullet 1 (e.g. "Medizintechnik-Service und -Handel") | Always — check prior offer for continuity |
| `strategie_bullet2_variant` | "umfangreichen" (Golmed/M&S) vs. "starken" (HWV) Gruppenvorteile | Always |
| `deal_specific_annahmen` | List of special conditions: property, legacy liabilities, family salaries, pension, factoring, employee protection | If applicable — BLOCK fill process if omitted and deal is past IO stage |
| `anhaenge_list` | Which appendices to include and their content | If applicable |
| `rueckbeteiligung_terms` | Key commercial terms for Rueckbeteiligung and Anhang 1 | If pricing.rueckbeteiligung non-null |
| `weiterer_prozess_addons` | Additional bullets beyond standard 3 (e.g. JA-condition for Sofortkaufpreis) | If applicable |

---

## 6. Edge Cases and Hardening Rules

### 6.1 Kaufpreis Component Count and "folgende" Rule

Standard = 2 components: Sofortzahlung + Erfolgszahlung.
Third component when any of these are non-null: `rueckbeteiligung`, `gewinnausschuettung`, `vd_amount`.

| Count | Summary line phrasing |
|-------|----------------------|
| 2 | "aufgeteilt in zwei Komponenten:" |
| 3+ | "aufgeteilt in folgende Komponenten:" |

**Gewinnausschuettung rule** (Golmed): The Gewinnausschuettung (425k €) is listed as a SEPARATE bullet below the standard two components, with the phrase "Zusaetzlich zu dem Sofortkaufpreis und der Erfolgszahlung erhaelt [GF] eine Gewinnausschuettung in Hoehe von [X] €...". It is NOT included in `total_consideration` on the main Kaufpreis line. The Ausschuettungsverbot Annahme must reference this amount as an explicit exception.

**Rueckbeteiligung rule** (HWV): The Rueckbeteiligung IS included in `total_consideration` and is shown as a third component bullet "[X] € Rueckbeteiligung in die Repuro GmbH". A dedicated Rueckbeteiligung section immediately follows the Kaufpreis summary block.

**Rule**: Never include a component in the summary bullet list without a corresponding detail section below. And never include a detail section without the corresponding bullet in the summary.

### 6.2 Singular vs. Plural Seller (GF Cascade)

**Trigger**: `sellers.length > 1` (only HWV in corpus has 2 sellers)

| Element | Single (M&S, Golmed) | Plural (HWV) |
|---------|---------------------|-------------|
| Address block | "Herr [Name]" | "Frau [Name1] und Herr [Name2]" |
| Salutation | "Sehr geehrter Herr X," | "Sehr geehrte Frau X, sehr geehrter Herr Y," |
| Rolle label | "Rolle Herr X:" | Per person: "Rolle Herr X:" THEN "Rolle Frau Y:" (separate sections) |
| Kaufpreis body (Rueckbeteiligung) | "[GF] investiert" | "Herr und Frau X investieren in Summe" |
| Annahmen references | "Herr X" | "Herr und Frau X" |

**Rule**: Multi-GF deals require SEPARATE Rolle sub-sections per person with individual terms. Do NOT merge into a single section. Draft each Rolle section independently then assemble.

**Rule**: Offer does NOT have a seller signature block — unlike the LOI. Repuro signs unilaterally. Never add seller signature lines.

### 6.3 Intro Lead-In Sentence Variants

| Variant | Used With |
|---------|-----------|
| "bitte finden Sie die aktualisierten Eckpunkte fuer eine gemeinsame Transaktion anbei:" | Variant C (M&S — terse update, no preceding paragraph) |
| "Wir koennen Ihnen folgende Eckpunkte fuer eine gemeinsame Transaktion anbieten:" | Variant A (Golmed — first approach with positive framing) |
| "Wir schlagen daher die folgenden Eckpunkte fuer eine gemeinsame Transaktion vor:" | Variant B (HWV — follow-up to prior discussion) |

**Rule**: These are the only confirmed lead-in sentences in corpus. Do not invent alternatives.

### 6.4 Earn-Out Structure Variants

Four distinct patterns across corpus. The fill process must route correctly via `earn_out_type`:

**Pattern A — Bracket Table** (HWV: 12 rows single year; C2M: 5 rows avg 2 years):
```
"[X] €, wenn das EBIT zwischen [Y] € und [Z] € liegt"  [per bracket row]
"[X_max] €, wenn das EBIT [Y_last] € oder mehr betraegt"  [final row]
```
Validation: last `ebit_to` must be null. Max bracket earn-out must equal `earn_out_max`. HWV pattern uses single-year; C2M uses average of 2 years in bracket head sentence.

**Pattern B — Formula with Floor and Cap** (M&S):
```
"Die Erfolgszahlungen betragen [X] € fuer jeden 1,00 €, der den Betrag des EBITs von
[floor] € uebersteigt, bis zu einem maximalen Betrag des jaehrlichen EBITs von [cap] €.
Die maximale jaehrliche Erfolgszahlung betraegt somit [max_annual] €."
"Die maximale gesamte Summe der Erfolgszahlungen [year1] und [year2] betraegt somit
[earn_out_max] €."
```
M&S: two SEPARATE earn-outs (one per year), each with own floor/cap/max, total stated separately.
Validation: multiplier * (cap_ebit - floor_ebit) = max_annual. 2 * max_annual = earn_out_max.

**Pattern C — Formula with Floor, Cap, and Minimum** (Golmed):
```
"Die Erfolgszahlung betraegt mindestens [minimum] €, wenn das durchschnittliche EBIT
mindestens [floor_trigger] € betraegt."
"Die Erfolgszahlung betraegt zusaetzlich [multiplier],00 € fuer jeden 1,00 €, der den
Betrag des durchschnittlichen EBITs von [floor] € uebersteigt, bis zu einem maximalen
EBIT von [cap] €. Die maximale Erfolgszahlung betraegt [earn_out_max] €."
```
Single earn-out on average of 2 years; paid after JA year 2 ("Feststellung des Jahresabschlusses [year2]").
Validation: minimum + multiplier * (cap_ebit - floor_ebit) = earn_out_max.

**Pattern D — Two Separate Annual Earn-Outs** (M&S extended variant):
```
"Es sollen zwei Erfolgszahlungen erfolgen, jeweils basierend auf dem EBIT der
Geschaeftsjahre [year1] und [year2]."
```
Then Pattern B formula applied to each year individually. Payment for each year: "faellig mit der Feststellung der Jahresabschluesse [year1] und [year2]."

**Rule**: `earn_out_periods == 2` with separate payments = Pattern D framing. `earn_out_periods == 2` with single payment on average = Pattern C framing. Verify arithmetic before inserting any earn-out section.

### 6.5 Sofortzahlung Section Variants

| Type | Section | Content | When |
|------|---------|---------|------|
| Fixed (no adjustment) | No explicit Sofortkaufpreis section needed | Amount stated only in Kaufpreis summary bullet | Golmed, most IOs |
| Formula-adjusted | No explicit Sofortkaufpreis section | Adjustment formula goes in Wichtige Annahmen (Assumption bullet, not price section) | HWV, C2M |
| Nettofinanzstatus-adjusted | Explicit **Sofortkaufpreis:** section | Brutto/Netto adjustment explanation + preliminary net figure + Anhang reference | M&S Final |

**Nettofinanzstatus section** (M&S pattern — 2 paragraphs):
1. "Der Brutto-Sofortkaufpreis wird um nicht-operative Kassenbestaende und Verbindlichkeiten aller Gesellschaften angepasst ('Nettofinanzstatus'), um den Netto-Sofortkaufpreis zu errechnen. Eine beispielhafte Berechnung findet sich in Anhang [N]."
2. "Der vorlaeufige Netto-Sofortkaufpreis entspricht [nettofinanzstatus_preliminary] € auf Grundlage des derzeit vorliegenden Nettofinanzstatus."

**Auszahlung nicht-betriebsnotwendige Liquiditaet** (HWV pattern — separate section, distinct from Sofortkaufpreis):
- Balance sheet stability statement (Bilanzpositionen in Groessenordnung der letzten 2 Jahre)
- Exception: non-operating cash to be distributed before closing
- Net financial status procedure (Anhang reference)
- Calculation confirmed during financial DD

**Rule**: These two sections are mutually exclusive in current corpus. HWV uses the Auszahlung section; M&S uses the Sofortkaufpreis detail section. Never include both.

### 6.6 Wichtige Annahmen — Standard vs. Deal-Specific

**Standard bullets** (present in ALL offers — order matters):

| Order | Bullet | Exact wording pattern | In all 3? |
|-------|--------|----------------------|-----------|
| 1 | Finanzzahlen bereinigt | "Die zur Verfuegung bereitgestellten Finanzzahlen sind um alle Einmal- oder Sondereffekte bereinigt und stellen die Finanzlage des Unternehmens realistisch dar." | Yes |
| 2 | Jahresabschluss timing | "Bis zum Abschluss der Transaktion liegt [mindestens der vorlaeufige] Jahresabschluss [YYYY] vor." ("mindestens" = safer; creates wiggle room if JA is delayed) | Yes |
| 3 | Keine Kuendigungen | "Es sind keine Kuendigungen von Kunden- oder Mitarbeitervertraegen bekannt oder absehbar." | Yes |

**Standard-conditional bullets** (include when applicable):

| Bullet | When to Include | Wording Pattern |
|--------|----------------|----------------|
| Bilanzstabilitaet | Golmed, HWV (formula-adjusted sofortzahlung) | "Die wesentlichen Bilanzpositionen (insb. Liquiditaet, Vorraete, Forderungen, Verbindlichkeiten, Darlehen) liegen zum Stichtag in einer Groessenordnung des Vorjahres..." |
| Keine Ausschuettungen / Schuldenaufnahmen | Golmed, HWV — NOT M&S (M&S uses Nettofinanzstatus instead) | "Es erfolgen bis zum Vollzug keine Ausschuettungen und keine neuen Schuldenaufnahmen ausserhalb des ueblichen Geschaeftsbetriebs[und der Gewinnausschuettung von [X] €]. Diese reduzieren ansonsten den Sofortkaufpreis in gleicher Hoehe." |
| Sofortzahlung adjustment formula | HWV, C2M (formula_adjusted sofortzahlung) | "Die Sofortzahlung basiert auf einem durchschnittlichen EBIT der Jahre [Y1] und [Y2] von [X] €. Ab einer Abweichung von [tolerance] € (mehr oder weniger) wird die Sofortzahlung um [multiplier],00 € pro 1,00 € Abweichung angepasst." |
| Budget/plan achievability | HWV only | "Das Finanz-Budget fuer [Y] und der Finanzplan fuer [Y+1] sind realistisch erreichbar und werden laut Aussage der Geschaeftsfuehrer erreicht oder uebertroffen." |

**Deal-specific bullets** (Roman must provide — never invent):

Examples observed in corpus:

| Deal | Specific Bullets |
|------|-----------------|
| M&S | Immobilie carve-out (transfer to Schroecke personally or GbR, arm's-length lease-back); MedServ GmbH insolvency complete (keine Nachforderungen); specific balance sheet positions listed in Anhang 1 to be settled/carved out by Stichtag |
| Golmed | Family member salaries (ca. 40k € brutto, end post-2026 or 2027); pension obligation to seller's mother (steueroptimale Herauslosung; Steuerrisiken geteilt); two successor management employees to be onboarded; 4 employees with Kuendigungs- und Standortschutz; factoring continuity at same terms |
| HWV | Sofortzahlung adjustment formula (see conditional above); budget/plan achievability |

**Rule**: Bullets 1, 2, and the Keine-Kuendigungen bullet are always included. All others: conditional or deal-specific. Missing a property carve-out or pension obligation in the Annahmen is a commercial and legal risk — the fill process is BLOCKED if `deal_specific_annahmen` is not provided for Aktualisiert and Final offers.

### 6.7 Anhaenge Variability

| Anhang | Content | Trigger | Numbering Priority |
|--------|---------|---------|------------------|
| Beispielhafte Berechnung des vorlaeufigen Nettofinanzstatus [YYYY] | Line-item net debt table | `sofortzahlung_type == "nettofinanzstatus_adjusted"` | Gets Anhang 1 if no Rueckbeteiligung |
| Berechnung des EBIT | EBIT bridge: Jahresueberschuss -> adjusted EBIT | Almost always (M&S Anhang 2, Golmed Anhang 1) | Default Anhang 1; shifts to 2 if Nettofinanzstatus is Anhang 1 |
| Eckpunkte zur Rueckbeteiligung | Key commercial terms for seller reinvestment | `pricing.rueckbeteiligung` non-null | Always Anhang 1 (precedes other Anhaenge) |
| Wichtigste Eckpunkte des Geschaeftsfuehrervertrages | GF contract: compensation, benefits, work conditions, Beraterrolle | When GF-Vertrag terms are detailed (HWV Anhang 3) | Last Anhang in sequence |
| Hinweis / Anmerkungen | Notes on EBIT projections (e.g. "Fuer 2026 und 2027 10% Wachstum angenommen") | When forward-looking assumptions need explicit disclosure | Within Anhang EBIT section, as footnote |

**Rule**: Anhang numbering must be sequential and every body reference ("Anhang [N]") must match a listed Anhang. Cross-validate before finalizing output.

**EBIT Berechnung table structure** (from Golmed golden — confirmed columns):
- Column 1: Position name
- Column 2: € amount
- Rows: Jahresueberschuss | + Steuern | + Zinsen | (+/- adjustments per EBIT definition) | = EBIT
- Source: Stage 2.1 model review output. Never fabricate EBIT figures.

### 6.8 Multi-Entity Kaufgegenstand

| Target Structure | Kaufgegenstand Formulation |
|-----------------|---------------------------|
| Single GmbH (Golmed, HWV) | "Erwerb von 100% der Anteile an der [Name] durch die Repuro GmbH (Anteilskauf oder 'Share Deal')" |
| GmbH + Tochter GmbH (M&S + Like Medizintechnik) | "Erwerb von 100% der Anteile an der [Name] mitsamt der Tochtergesellschaft [Sub Name] durch die Repuro GmbH (Anteilskauf oder 'Share Deal')" |
| GmbH + 2 KGs (C2M pattern) | Full entity list with combined designation; entity names as comma-separated list | 

**Rule**: When `ebit_scope == "konsolidiert"`, the Erfolgszahlung EBIT definition must explicitly state "konsolidierten Jahresueberschuss der [Parent] inkl. der [Sub]". Missing this creates legal ambiguity on earn-out measurement.

**Rule**: Offer does NOT require HRB or Amtsgericht — those are LOI-level details. Do not include them in the offer body.

### 6.9 EBIT Definition Variants

Core EBIT definition (present across all deals — always present):
> "Jahresueberschuss der [X] zzgl. Steuern, Zinsen"

Add-backs by deal:

| Add-back | In Corpus | Rule |
|----------|-----------|------|
| etwaigen Management Fees | HWV, M&S, Golmed | Always include — protects seller from group charges |
| Einmaleffekte | HWV, M&S, Golmed | Always include |
| Synergien durch die Repuro GmbH | M&S, Golmed | Include by default — seller protection from Repuro-imposed cost synergies |
| (keine Zusatzbelastungen durch die Repuro Gruppe) | HWV — bracketed parenthetical variant | Use when Roman wants to explicitly state Repuro charges don't affect earn-out (instead of "Synergien" phrasing) |
| inkl. aller etwaigen Geschaeftsfuehrergehaelter | C2M only | Only if `ebit_definition_addons` includes "gf_gehaelter" |

For multi-entity deals (`ebit_scope == "konsolidiert"`), prepend: "konsolidierten Jahresueberschuss der [X] inkl. der [Y], zzgl. Steuern..."

**Rule**: Confirm EBIT definition with Roman before finalizing any Erfolgszahlung section. The definition is a legal and commercial commitment.

### 6.10 Weiterer Prozess — Inclusion Logic

| Offer version | Include Weiterer Prozess? |
|---------------|--------------------------|
| Very first IO (early-stage, relationship-building) | Optional — absent in HWV original IO |
| IO with engaged seller | Yes — include |
| Aktualisiertes Angebot | Always include |
| Finales Angebot | Always include |

Default = include. Omit only on Roman's explicit instruction.

Golmed Weiterer Prozess has an extra 4th bullet absent from M&S: "Fuer die finale Freigabe der Transaktion und die Festlegung des Sofortkaufpreises wird mindestens der vorlaeufige Jahresabschluss [YYYY] benoetigt. Dieser wird ebenfalls Teil der Finanzpruefung werden." — include when `weiterer_prozess_addons` specifies it.

### 6.11 Strategie Sector Phrase Variants

Two confirmed variants in corpus:

| Phrase | Used In | When to Use |
|--------|---------|-------------|
| "Medizintechnik-Service und -Handel durch Buendelung starker Unternehmen" | M&S, Golmed (current standard) | Default for all new offers |
| "Medizintechnik-Handel und Service durch Buendelung fuehrender Unternehmen" | HWV (older version) | Only if prior HWV-pattern offers used this; maintain consistency within a deal |

**Rule**: Check prior offer versions for the deal before selecting. Never switch sector phrase between iterations — it signals inconsistency.

### 6.12 Document Production — HARD RULE

**NEVER generate an Offer from scratch programmatically.** Always:
1. Copy the appropriate golden .docx to a temp file (never modify originals)
2. Modify text in-place: python-docx paragraph-level replacement or Word COM (PowerShell)
3. Preserve all formatting: bold labels, bullet styles, font, spacing, page layout, header/footer
4. Verify: run paragraph count check, spot-check 3 key € amounts match input schema
5. Output naming: `YYMMDD_[OfferType] Angebot [ShortName/LegalName]_v[N].docx`
   Example: `260519_Aktualisiertes Angebot Golmed_v2.docx`

**Template selection rule**:
- Single seller, no special components: GOLMED vSent (primary template)
- Multi-seller or Rueckbeteiligung: HWV vAktualisiert (reference)
- Final offer with Nettofinanzstatus, multi-entity EBIT: M&S vS (reference)
- KVG_IO_vAktualisiert.docx: EXCLUDED — byte-for-byte duplicate of HWV; never use

Anti-patterns: DOCX-FROM-TEMPLATE (copy + modify, never create), INVENTED-FORMAT-INSTEAD-OF-COPY (no structural deviations), CONFIDENTIAL-LEAK (purge all prior-deal data before filling — check every paragraph), READ-BEFORE-ACTING (re-read current DOCX state before any edit).

---

## 7. Confidence Assessment

### HIGH confidence — automate fully

| Section | Confidence | Rationale |
|---------|-----------|-----------|
| Closing paragraph | 100% | Verbatim across HWV, M&S, Golmed |
| Farewell line | 100% | Verbatim across all deals |
| Signature block | 98% | Fixed. Edge case: Repuro entity name change — verify before each use |
| Wirtschaftlicher Stichtag | 98% | Single date slot, 1-line template |
| Kaufgegenstand (single entity) | 92% | Stable formula; only slot is entity name |
| Strategie bullets 3-5 | 90% | Verbatim across M&S, Golmed (confirmed identical) |
| Weiterer Prozess (standard 3 bullets) | 90% | Verbatim across M&S, Golmed |
| Header block | 88% | Slots only; edge case: multi-seller address formatting |

### MEDIUM confidence — generate draft, Roman reviews

| Section | Confidence | Rationale |
|---------|-----------|-----------|
| Strategie bullets 1-2 | 65% | Sector phrase and Gruppenvorteile adjective vary; 2 confirmed variants each |
| Kaufgegenstand (multi-entity) | 60% | Multi-entity pattern known; KG structures need legal precision |
| Erfolgszahlung (bracket table) | 65% | Table generation mechanical; arithmetic verification is critical; band count varies 5-12 |
| Erfolgszahlung (formula type B/C) | 60% | Formula template known; Golmed 3-part formula adds complexity; earn_out_periods branching |
| Wichtige Annahmen (standard bullets) | 72% | 3 always-present bullets; conditional bullets require correct routing |
| Rolle GF (simple single-GF retention) | 65% | 3-4 bullet structure known; deal-specific: FTE%, salary, contract term |
| Sofortzahlung (Nettofinanzstatus) | 55% | Structure known; preliminary figure requires live net debt data |
| Kaufpreis summary (3 components) | 70% | 3-component routing logic; Gewinnausschuettung exclusion rule adds complexity |

### LOW confidence — Roman must provide, review closely

| Section | Confidence | Rationale |
|---------|-----------|-----------|
| Intro paragraph | 15% | Fully situation-dependent; wrong tone is commercially costly |
| Wichtige Annahmen (deal-specific bullets) | 20% | Open-ended; missing a critical assumption creates contractual risk |
| Rolle GF (multi-GF / phased / successor) | 20% | HWV dual-GF with Beraterrolle; C2M successor with VSOP — neither templatable |
| Rueckbeteiligung section | 10% | Complex financial instrument; leaver provisions, Tag/Drag, valuation mechanics all negotiated |
| Anhaenge content | 15% | Each Anlage is effectively a separate document; GF-Vertrag Eckpunkte alone has 8+ sub-items |

### Overall automation estimate

~55% of the offer by character count can be generated from template + structured data with high confidence. ~20% can be drafted for review (Rolle GF, Erfolgszahlung, standard Annahmen). ~25% requires Roman's substantive input. The 25% (intro, deal-specific Annahmen, GF complex cases, Anhaenge) is disproportionately high commercial and legal risk — errors affect negotiating position and deal terms.

---

## 8. Template-Fill Workflow

```
1. COLLECT
   From DB:
   - deal_valuations: confirmed scenario (sofortzahlung, earn-out structure)
   - deal_data: entity structure, seller/GF details, addresses
   - deal_questions: GF transition answers from RFI / management call notes
   - deal_documents: prior offer versions (version numbering + continuity check)

   From Roman (mandatory before starting — BLOCK if missing):
   - offer_type
   - intro_brief (situation, tone, what changed)
   - deal_specific_annahmen (list — required for Aktualisiert/Final; optional for IO)
   - gf_transition per GF (salary, FTE%, contract end, special terms)
   - anhaenge_list (which Anhaenge to include + content data)
   - weiterer_prozess_addons (if any)
   - strategie_sector_phrase (confirm with prior offer for continuity)

2. VALIDATE (hard stops — do NOT generate with failures)
   - earn_out arithmetic: bracket sum OR formula * (cap - floor) + minimum = earn_out_max
   - two-period formula: 2 * single_period_max = earn_out_max
   - total_consideration = sofortzahlung + earn_out_max + rueckbeteiligung (confirm gewinnausschuettung excluded)
   - Kaufpreis summary "bis zu [X] €" matches total_consideration
   - Anhang body references match anhaenge_list entries (cross-reference check)
   - earn_out_periods matches earn-out payment framing (one vs. two Erfolgszahlungen)
   - ebit_scope consistency: if multi-entity, EBIT definition includes all entities
   - All € amounts will be formatted: German number format (1.234.567 €, symbol behind number)
   - gf_transition data complete per GF (salary, contract end, FTE%)

3. FILL (copy golden template + populate)
   a. Present arithmetic gate to Roman: pricing table (Sofortzahlung, Earn-Out max,
      optional components, total). Wait for confirmation before proceeding.
   b. Present intro draft (from intro_brief). Wait for Roman approval.
   c. Copy golden template to temp file. Verify copy is non-empty.
   d. Fill pure-template sections (closing, farewell, signature, Weiterer Prozess bullets 1-3)
   e. Fill slot-template sections (header, date, Betreff, salutation, Kaufgegenstand, Stichtag)
   f. Fill Kaufpreis summary (component count logic, total, component bullets)
   g. Fill optional sections if triggered: Rueckbeteiligung (drafted), Auszahlung Liquiditaet
   h. Fill Sofortkaufpreis detail section if sofortzahlung_type == "nettofinanzstatus_adjusted"
   i. Fill Erfolgszahlung (route by earn_out_type: bracket_table / formula_cap /
      formula_floor_cap_minimum; route by earn_out_periods: 1 / 2)
   j. Fill Rolle GF sections (route by complexity: simple / phased / multi-GF)
   k. Fill Wichtige Annahmen: standard bullets auto-filled, conditional bullets routed,
      deal-specific from roman_input appended
   l. Fill Weiterer Prozess if included (3 standard + any addons)
   m. Add Anhaenge stubs from anhaenge_list; each complex Anhang is a sub-task
   n. Apply singular/plural cascade if seller_count > 1
   o. Replace temp file as output (os.replace — never open(w) on golden or working file)

4. REVIEW GATES
   Gate 1 (arithmetic): Before fill — confirmed by Roman in COLLECT step
   Gate 2 (intro): Intro draft confirmed by Roman before inserting
   Gate 3 (drafted sections): Rueckbeteiligung, complex GF sections, deal-specific Annahmen —
     present to Roman before final assembly
   Gate 4 (full document): Roman reviews assembled .docx.
     For Aktualisiert/Final: present delta summary vs. prior version:
     "Changed: Sofortzahlung [old] -> [new], Earn-out [old] -> [new], Annahmen: added [X], removed [Y]"
   Gate 5 (proofread): € formatting (symbol behind number), seller name consistency throughout, Anhang numbering,
     entity name consistency (no abbreviation drift), no prior-deal data residual

5. OUTPUT
   - Save as YYMMDD_[OfferType] Angebot [ShortName]_v[N].docx
   - PDF export (Word -> Export as PDF) — PDF is the version sent
   - File to 3_Deals/3_Targets/<deal>/3_Indikatives Angebot/
   - Update deal_documents: doc_type = 'offer_IO' | 'offer_aktualisiert' | 'offer_final'
   - Email draft created via mcp__email__create_draft (roman.dobriakov@repuro.de) — NOT saved
     as .docx or .md file
   - Update deal stage in deals table if Finales Angebot sent and accepted
```

---

## 9. Dependencies

### DB Tables

| Table | Fields Used | Purpose |
|-------|------------|---------|
| `deals` | deal_id, code_name, legal_name, stage | Deal identification; stage must be >= 2.3 complete |
| `deal_valuations` | sofortzahlung, earn_out_max, earn_out_table, multiplier, base_ebit | All pricing fields for Kaufpreis and Erfolgszahlung |
| `deal_data` | target_entities, seller/GF details, addresses, entity structure | Kaufgegenstand, header, salutation, Rolle section |
| `deal_questions` | GF transition RFI answers, salary info | Rolle section data |
| `deal_documents` | Prior offer versions | Version numbering; delta check for Aktualisiert/Final |

### Prior Stage Outputs Required

| Output | From Stage | Used In |
|--------|-----------|---------|
| Confirmed valuation scenario | Stage 2.3 (post Roman + Flo gate) | All pricing sections |
| Net debt bridge | Stage 2.2 | Nettofinanzstatus section (M&S pattern), Anhang |
| EBIT bridge | Stage 2.1 model review | Anhang: EBIT Berechnung |
| GF transition terms | RFI / management call notes | Rolle section |
| Scorecard | Stage 2.4 | Not in offer body; informs framing of deal-specific Annahmen |

### Golden Files

| File | Role | Use For |
|------|------|---------|
| `260518_Aktualisiertes Angebot Golmed_vSent.docx` | PRIMARY template | Single seller, standard earn-out, Gewinnausschuettung variant reference |
| `HWV_IO_vAktualisiert.docx` | REFERENCE | Multi-seller, Rueckbeteiligung, bracket earn-out, Auszahlung Liquiditaet, GF-Vertrag Eckpunkte Anhang |
| `260507_Finales Angebot M&S_vS.docx` | REFERENCE | Final offer, Brutto/Netto Sofortkaufpreis, subsidiary in Kaufgegenstand, two-year earn-out (separate annual payments), M&S-specific Annahmen |
| `KVG_IO_vAktualisiert.docx` | EXCLUDED | Byte-for-byte duplicate of HWV_IO_vAktualisiert.docx — do not use |
| `251002_Indikatives Angebot C2M_vAktualisiert.pdf` | READ-ONLY REFERENCE | PDF only; not editable. C2M/Fox: multi-entity KG structure, EBIT incl. GF Gehaelter, 5-bracket table, formula adjustment in Annahmen |

### Anti-Patterns (must be loaded by agent executing the fill process)

From `anti-patterns-deals.md`:
- **DOCX-FROM-TEMPLATE**: Never regenerate from scratch. Copy golden + modify in-place. Creating from python-docx Document() destroys all formatting.
- **INVENTED-FORMAT-INSTEAD-OF-COPY**: Do not restructure sections or change section order. Follow golden file structure exactly unless Roman explicitly instructs deviation.
- **CONFIDENTIAL-LEAK**: Offers contain deal-sensitive pricing. Verify all amounts come from the specific `deal_id` being processed. Check every paragraph for residual prior-deal text before finalizing.
- **EXCEL-FROM-SCRATCH**: Applies to Anhang tables (EBIT Berechnung, Nettofinanzstatus). Derive from Stage 2 model data. Never fabricate financial tables.
- **OPENPYXL-CORRUPTION**: If any Anhang is delivered as .xlsx with styling, use Excel COM not openpyxl for modifications.

From `anti-patterns.md` (global):
- **READ-BEFORE-ACTING**: Re-read current DOCX file state before any paragraph replacement. Roman may have edited the document between turns. Do not assume paragraph indices are stable.
- **VERIFY-BEFORE-DONE**: Run arithmetic verification and paragraph/section count before claiming output is ready. Show results.
- **NO-FABRICATION**: All € figures must come from `deal_valuations` or Roman's explicit input. No inferred or estimated pricing figures.

---

## 10. Template Registry Entry

Update `DEAL_DELIVERABLES_SPEC.md` Template Registry:

| Deliverable | Template Path | Notes |
|-------------|--------------|-------|
| Indikatives / Aktualisiertes / Finales Angebot (standard) | `dealroom/config/golden/offer/260518_Aktualisiertes Angebot Golmed_vSent.docx` | Primary template. Single seller, formula earn-out with minimum, Gewinnausschuettung variant. |
| Angebot (multi-seller / Rueckbeteiligung) | `dealroom/config/golden/offer/HWV_IO_vAktualisiert.docx` | Reference. Multi-GF, bracket earn-out, Auszahlung Liquiditaet, GF-Vertrag Anhang. |
| Finales Angebot (Nettofinanzstatus / multi-entity EBIT) | `dealroom/config/golden/offer/260507_Finales Angebot M&S_vS.docx` | Reference. Brutto/Netto split, subsidiary EBIT consolidation, two-year separate earn-outs. |
