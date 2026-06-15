# DEAL DELIVERABLES SPEC — Stage 2 & 3 Sub-Steps

Execution-level companion to `DEAL_WORKFLOW_SPEC.md`. Defines the exact DATA IN → DATA OUT for each sub-step in Stage 2 (Valuation/RFI) and Stage 3 (Indicative Offer). Golden reference extracted from Project Aqua (HEGA-Medical, May 2026).

**Rule**: Every sub-step has a human gate. Claude proposes, Roman confirms. No sub-step output feeds the next without Roman's sign-off.

---

## Stage 2: Valuation and RFI — Sub-Steps

### 2.1 Financial Model Review

**Purpose**: Verify the Excel valuation model is structurally correct — formulas linked, adjustments defensible, no hardcoded values where formulas belong.

| | Detail |
|---|---|
| **DATA IN** | Excel model (`2_Model/<target>_Model_v*.xlsx`): GuV tab (P&L with adjustments), Bilanz tab (balance sheet), Bewertung tab (valuation scenarios), source financials (Saldenliste, BWA, Jahresabschluss) |
| **DATA OUT** | Review memo (inline or .md): list of (1) formula errors / broken links, (2) hardcoded values that should be formulas, (3) missing adjustments (GF salary, one-offs, Bestandsveränderung), (4) scope gaps (entities missing, periods missing). Each finding = cell reference + issue + proposed fix. |
| **QUALITY GATE** | Every finding must reference a specific cell or range. No vague "check the P&L" — cite `GuV!B15` or equivalent. |
| **HUMAN GATE** | Roman reviews findings, confirms which to apply. Model is Roman's tool — Claude flags, Roman decides. |
| **ANTI-PATTERNS** | WRONG-GESAMTLEISTUNG (use Gesamtleistung not Umsatzerlöse), HARDCODED-METRICS, GOLDEN-PL-FORMAT |

### 2.2 Net Debt Bridge

**Purpose**: Compute the cash-free/debt-free adjustment that converts Enterprise Value to Equity Value.

| | Detail |
|---|---|
| **DATA IN** | Bilanz tab from model (latest available balance sheet date), GF-Darlehen details from RFI or Gesellschaftervertrag, Pensionsrückstellungen / Steuerrückstellungen from Bilanz or tax advisor |
| **DATA OUT** | Net debt table with 6 mandatory line items, each explicitly included or excluded with rationale: (1) Verbindlichkeiten ggü. Kreditinstituten, (2) Steuerrückstellungen, (3) Pensionsrückstellungen, (4) sonstige Rückstellungen >€50k, (5) GF-Darlehen / Gesellschafterdarlehen, (6) Leasingverbindlichkeiten. Plus: Kasse/Bank, Wertpapiere des UV. Net result = Net Cash or Net Debt figure. |
| **QUALITY GATE** | All 6 items addressed. GF-Darlehen classified as deal-structure (pre-closing settlement), never as buyer Net Cash. Each line cites Bilanz cell reference or RFI answer. |
| **HUMAN GATE** | Roman confirms net debt figure before it feeds into valuation. This number directly affects offer price. |
| **ANTI-PATTERNS** | GF-LOAN-MISCLASS, NET-DEBT-INCOMPLETE |

### 2.3 Valuation Scenarios

**Purpose**: Generate EV and equity value ranges under multiple scenarios (base, upside, downside) using the reviewed model.

| | Detail |
|---|---|
| **DATA IN** | Reviewed model (post-2.1 fixes applied by Roman), confirmed net debt (2.2), comparable multiples (sector benchmarks from prior deals: CAT, WOLF, HWV), seller expectation (from broker or management call) |
| **DATA OUT** | Scenario table: Base / Upside / Downside × {EBITDA basis, multiple, EV, net debt adjustment, equity value}. Earn-out structure proposal: trigger metric (EBIT or EBITDA), threshold, formula (continuous €X per €1 above threshold, or stepped bands), cap, reference period, payment timing. Sensitivity matrix: equity value at ±0.5x multiple × ±€50k EBITDA. |
| **QUALITY GATE** | EBITDA basis = adjusted (post-GF-salary, post-one-offs). Gesamtleistung used for growth/CAGR metrics. Multiples within sector range (4.0x–7.0x for ambulatory healthcare distribution — flag outliers). Earn-out cap internally consistent with total consideration. |
| **HUMAN GATE** | Roman + Flo alignment on valuation range and earn-out structure before proceeding to offer. This is the critical go/no-go gate. |
| **ANTI-PATTERNS** | WRONG-GESAMTLEISTUNG, CONSERVATIVE-SIGNAL |

### 2.4 Deal Scorecard

**Purpose**: Structured assessment of deal attractiveness across standardized dimensions.

| | Detail |
|---|---|
| **DATA IN** | All Stage 2 outputs (model review, net debt, valuation), RFI answers from `deal_questions`, management call notes, outside-in research (market position, competitive landscape) |
| **DATA OUT** | Scorecard with signal per dimension: 🔴 RED (material concern), 🟢 GREEN (strong), 🟡 YELLOW (genuinely partial info), ❓ OPEN (insufficient data). Dimensions: Revenue quality, Customer concentration, Margin profile, Growth trajectory, Management/team, Market position, Regulatory risk, Integration complexity. Each dimension = signal + 1-sentence rationale + data source. |
| **QUALITY GATE** | No default-yellow hedging. Apply thresholds: concentration >70% single customer = 🔴, margin >40% = 🟢, etc. Every signal must cite a specific data point. |
| **HUMAN GATE** | Roman reviews scorecard before it informs the offer strategy. Scorecard is internal — never shared externally. |
| **ANTI-PATTERNS** | CONSERVATIVE-SIGNAL |
| **REFERENCE** | AQUA benchmark format stored in Claude auto-memory (`reference_aqua_deal_assessment_benchmark.md`) |

---

## Stage 3: Indicative Offer — Sub-Steps

### 3.1 Offer Drafting

**Purpose**: Generate the indicative offer letter from confirmed valuation parameters and the standard Repuro template.

| | Detail |
|---|---|
| **DATA IN** | Confirmed valuation range + earn-out structure (2.3, post-Roman/Flo gate), confirmed net debt (2.2), GF transition terms (from RFI/management call), deal structure (share deal default for GmbH), latest offer template (`3_Indikatives Angebot/` in a prior deal folder — WOLF/KVG is current golden template) |
| **DATA OUT** | `.docx` indicative offer with: Strategie (Repuro platform fit), Kaufgegenstand (share deal, 100% GmbH-Anteile), Stichtag, Kaufpreis (Sofortzahlung + Verkäuferdarlehen + Erfolgszahlung), Nettofinanzstatus (cash-free/debt-free, net debt figure), Rolle des Verkäufers (GF transition), Annahmen (DD, financing, regulatory). |
| **QUALITY GATE** | Document created by copying template and editing in-place (never from scratch — hook-enforced). All numbers consistent with valuation gate output. Earn-out formula matches agreed structure exactly. Net debt figure matches 2.2 output. No confidential cross-deal information leaks. |
| **HUMAN GATE** | Roman reviews and edits the offer before sending. Offer is Roman's document — Claude generates v1, Roman owns final version. Expect 1-2 revision rounds. |
| **ANTI-PATTERNS** | EXCEL-FROM-SCRATCH / OFFICE-FROM-SCRATCH (hook-enforced), CONFIDENTIAL-LEAK, IGNORE-STATED-FORMAT |
| **TEMPLATE** | Copy from: `3_Deals/3_Targets/251125_KVG (Wolf)/3_Indikatives Angebot/260225_Indikatives Angebot KVG_vAktualisiert.docx` |

### 3.2 Offer Review and Iteration

**Purpose**: Incorporate Roman's edits, apply cuts/additions, produce final version for sending.

| | Detail |
|---|---|
| **DATA IN** | Roman's marked-up v1 (or verbal instructions on what to change), any new information from counterparty |
| **DATA OUT** | Final `.docx` ready for Roman to send. Version naming: `YYMMDD_Indikatives Angebot_<LegalName>_v<N>.docx` |
| **QUALITY GATE** | Before any edit: re-read the current file version (Critical 6 #2). Roman may have changed numbers between turns. Never recommend changes based on what Claude wrote — only based on current file state. |
| **HUMAN GATE** | Roman sends the offer. Claude never sends on Roman's behalf. |
| **ANTI-PATTERNS** | READ-BEFORE-ACTING (Critical 6 #2 recurrence in AQUA v2→v3) |

---

## Template Registry

Maps deliverable type to golden template path. Always copy template, never create from scratch.

| Deliverable | Template Path | Notes |
|---|---|---|
| Indicative Offer | `3_Deals/3_Targets/251125_KVG (Wolf)/3_Indikatives Angebot/260225_Indikatives Angebot KVG_vAktualisiert.docx` | 121 paragraphs, List Paragraph style for bullets |
| Databook (legacy) | `dealroom/config/golden/databook/CAT_Databook_v6.xlsx` | Pre-CDD format, multi-tab with INPUT/ANALYSIS separation |
| CDD Databook | `dealroom/config/golden/dd/CDD_Databook_Template.xlsx` | Evolved from Mantis v4. 16 tabs: Summary, Revenue/Customer/Cohort/Churn/Supplier/Personnel/P&L/Charts/Gaps analysis + 5 INPUT tabs. Skill: `/cdd` |
| CDD RFI | `dealroom/config/golden/dd/CDD_RFI_Template.xlsx` | Fragenliste (Nr/Quelle/Frage/Prio/Antwort) + Kundendaten tab. Skill: `/cdd` |
| Valuation Model | `dealroom/config/golden/model/` — select by entity/SKR type | See `/model` skill Phase 1 for template selection matrix |
| RFI (Datenanfrage) | `dealroom/config/golden/rfi/Datenanfrage_Template.xlsx` | Initial DD data request — sent before CDD starts |

---

## Cross-References

- Strategic workflow: `DEAL_WORKFLOW_SPEC.md` (same folder)
- Anti-patterns: `Claude_Context/anti-patterns-deals.md`
- Deal information map: `Claude_Context/deal-information-map.md`
- AQUA benchmark: Claude auto-memory `reference_aqua_deal_assessment_benchmark.md`
- DEALROOM milestones: `dealroom/ai/PLAN.md` (DR-M1–M17)
