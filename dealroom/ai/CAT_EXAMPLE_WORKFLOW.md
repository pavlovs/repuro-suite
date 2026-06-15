# CAT — Example Deal Workflow

**Purpose:** reusable playbook for the commercial-understanding phase of a Repuro add-on deal. Captured from the CAT (Medizin & Service GmbH / Schröcke) workstream on 2026-04-20.

**When to use:** Indicative offer is out, seller has delivered partial material, you need to (a) map what's still missing, (b) quantify commercial risk, (c) send a targeted follow-up, (d) keep everything auditable for investor DD later.

---

## 1. The deal in one paragraph (write this first)

> CAT (Medizin & Service GmbH, Schröcke) is a ~€6M revenue / 35-employee medtech distributor in the ambulatory hospital segment. Offer submitted 18.03.2026, seller counter-offer received. **Headline risk:** 2025 EBITDA jumped 4x (233 → 938 TEUR) on +36% revenue — concentrated in the Projekte segment (+68%) and in the top 10 customers (50.6% → 66.3% concentration). Without proof that this is structural rather than 3-4 public-sector tender wins, the 2025 valuation multiple is misleading.

Every downstream artifact (databook, RFI, onepager, IC memo) should trace back to this one paragraph. If it doesn't, you're off-thesis.

---

## 2. Process — 5 steps, in order

### Step 1 — Material audit (15 min)
Read **everything** in `3_Targets/<deal>/CLAUDE/` and `3_Targets/<deal>/` root. Do not skim. Specifically:
- Every `.docx` is an RFI or answer — read both sides
- Every `.xlsx` with a date prefix is a deliverable — open it, note what sheet has what
- Email threads on the deal mailbox: `list_emails` filtered by counterparty domain for the last 90 days
- Granola meetings: check local cache `C:\Users\X1\AppData\Roaming\Granola\cache-v6.json` for `state.documents` matching deal keywords

**Output:** one-paragraph material inventory. Example for CAT:
> RFI cycle: 25.06.2025 (answered), 28.07.2025 FU (partial), 18.03.2026 v3 (answered only on segment split 31.03). Emails: 13.03 Bilanz, 16.03 BWA+Auftragsbuch request (open), 07.04 OOO until 13.04. Model: 260313_MundS_v6.xlsx with Bewertung tab. 3x RAB nach Umsatz.xlsx (customer-level invoiced sales 2023-2025). Auftragsübersicht 25.07.2025 (9 months stale).

### Step 2 — Commercial risk framing (30 min)
Do not start drafting. Find the **single sharpest question** the deal hinges on. For CAT it was:
> "How much of the 2025 EBITDA step-up is one-off tender wins vs. structural improvement?"

Techniques that worked:
- **Segment decomposition:** Spartenrechnung showed +68% Projekte vs +46% Service vs -60% FEP vs -81% RV. Growth is concentrated, not broad-based.
- **Customer concentration Δ:** Top 10 went 50.6% → 66.3% in one year. Growth is driven by a small number of large wins.
- **Customer-to-backlog cross-reference:** RAB top names (Staatl. Bauamt Erlangen, Kliniken Südostbayern, BBR, BLB NRW) directly traceable to big tenders in the July 2025 backlog (Erlangen OZ 555K, Traunstein 681K, etc.). Three customers explain most of the jump.

**Principle:** concentration analysis on customer-level data always beats aggregate growth narratives.

### Step 3 — Gap map → targeted RFI
Only after risk framing. The RFI should be ranked by **what would change the valuation if answered**, not alphabetical. Template:

| Prio | Open question | Why it matters | Blocking which deliverable? |
|---|---|---|---|
| P1 | Non-recurring 2025 (Koblenz/Traunstein/Ostfildern?) | Direct EBITDA-quality input | IC memo, LOI, purchase price |
| P2 | Q1-2026 BWA + updated 2026 backlog | Current trading = bridge into 2026 | Earn-out structure, pricing |
| P3 | Consolidated GuV 22-24 w/ D&A | EBITDA bridge auditability | DD prep |
| P4 | 2026 management plan per segment | Forward basis for valuation | Onepager, IC memo |
| P5 | Recurring % from Wartungsverträge | Investor narrative (stable base) | Investor pitch |
| P6 | Reinvestment willingness | Earn-out / retention structure | Offer terms |

### Step 4 — Persist everything (critical)
**The artifact that doesn't exist doesn't count.** Findings in chat get forgotten in the next session. Always write to:

1. **Databook v2** — segment analysis, customer concentration, one-off risk flags on backlog rows, Frageliste with status column, and a new **RFI Log** tab consolidating every question asked across all channels (RFI docs, emails, Granola calls) with:
   - Datum gefragt
   - Gruppe (Financials / Segment / Customers / Service / OEM / Process / Personal / Auftrag / Meta)
   - Frage
   - Status (OFFEN / TEILWEISE / BEANTWORTET / INTERN GELÖST / LÜCKE)
   - Antwort/Befund
   - Quelle Antwort (exact file + date, or Granola meeting)
2. **Thesenaufbereitung.md** — one-page strategic frame (already exists for CAT as template)
3. **Onepager update** — investor-facing artifact stays current
4. **deals.md** — pipeline state (one-line status only)

**File safety rule:** write to `<name>.tmp.xlsx` → validate size → `os.replace` onto final. OneDrive paths have no local git backup. Never `open(path, 'w')` on an original.

### Step 5 — Follow-up email
Only after Steps 1-4 are done. Email should:
- Reference prior RFI by date (do not re-ask answered questions)
- Group by priority (P1 first — the sharpest question)
- Offer an alternative if seller is slow ("updated timeline would help us prioritize")
- Stay under 250 words

---

## 3. Reusable artifacts

### Databook v2 structure (template)
| Tab | Purpose | Fill from |
|---|---|---|
| Cover | Version + changelog | Manual |
| GuV | 3-year P&L | Seller or rebuilt from raw data |
| Revenue Split | Segment decomposition + Δ analysis | Seller Spartenrechnung |
| Customers | Concentration summary + Top 10 + backlog cross-ref | Internal RAB nach Umsatz files |
| Auftragsvolumen | Backlog with one-off risk highlighted | Seller backlog export |
| Personal | Headcount, fluctuation, costs | Seller personnel files |
| Frageliste | Original RFI + Status column | Latest RFI .docx + current state |
| RFI Log | **Consolidated** RFI tracker (new) | Reconcile all channels |
| Customer Development | Cohort / churn / retention | Customer-level history if available |
| CDD Analysis | Commercial DD notes | Claude/manual synthesis |

### RFI Log status colours
- Green (`E2EFDA`) — BEANTWORTET / INTERN GELÖST
- Yellow (`FFF2CC`) — TEILWEISE
- Orange (`FCE4D6`) — OFFEN / LÜCKE

### Auftragsbestand one-off risk flag
Insert 10 rows at top of the backlog tab with a flag box. Row-level fill (`FCE4D6`) on individual candidate-one-off rows. Marker text in a trailing column: `⚠ ONE-OFF RISK`.

---

## 4. Learnings — what to remember for the next deal

**Commercial**
- EBITDA jumps >2x in a single year are almost always driven by 3-5 lumpy wins. Find them before trusting the multiple.
- Customer concentration Δ is the fastest commercial risk signal. Use Top 10 share year-over-year.
- If backlog data is >3 months old, treat headline EBITDA as provisional. Demand a refresh.
- For public-sector-heavy customer bases: map the counterparty (Staatliches Bauamt, BBR, BLB, etc.) to specific named tenders. Public tenders don't repeat.
- RAB (Rechnungsausgangsbuch) totals ≠ Spartenrechnung totals. Delta is WIP / Bestandsveränderung — not a data error. State this explicitly.

**Process**
- Seller-delivered segment data (Spartenrechnung) arrives **after** the offer was already made. Offer price is therefore built on partial info — segment-level risk is priced retroactively.
- Granola local cache (`cache-v6.json`) doesn't always include server-side notes. If a specific number is cited (e.g. "300K€") but not in the local `state.documents` regex search, verify with Roman or fetch server-side. Do not fabricate the source.
- OOO replies from the seller reset your follow-up clock but not your internal deadline. Build the RFI package *during* the OOO window so you can send day-of-return.

**Artifact hygiene**
- Every number in a databook cell needs a source comment or a source row in RFI Log. "Source: Granola 2026-03-17" is sufficient — "Source: unknown" is not.
- A databook without an RFI Log tab is a snapshot. With an RFI Log tab, it becomes an audit trail that investor DD will trust.
- On first session of a deal: check what exists. On every session after: version the databook (`260420_CAT_Databook_v2.xlsx`), do not overwrite v1.

**Anti-pattern (do not repeat)**
- Delivering gap analysis verbally in chat without persisting to the databook — recurring topic, recurring forgetting. The databook is the memory. (Roman feedback, 2026-04-20.)

---

## 5. Entry points in this repo

- **Source materials location (per-deal):** `3_Deals/3_Targets/<YYYYMMDD>_<Name> (<Code>)/CLAUDE/`
- **Deal model Bewertung tab convention:** Avg 24-25P EBITDA drives the headline multiple; 2025-only drives the optimistic multiple. Use Avg for the IC narrative.
- **Offer docs:** `3_Indikatives Angebot/` — structure: `260227_Aktualisiertes Angebot <Name>_vS.docx` (Repuro offer) vs. `Angebot SBAS.docx` (seller counter).
- **Pipeline status:** `CLAUDE_REPURO/deals.md` — one line per deal, no prose.

---

## 6. Hooks into DEALROOM code pipeline

Future state: this workflow should be the reference input/output spec for the DEALROOM pipeline (see `DEAL_WORKFLOW_SPEC.md` in this directory). Specifically:

- Step 1 (material audit) → candidate for an `ingest.scan_deal_folder()` routine that produces the material inventory paragraph automatically
- Step 2 (segment decomposition + customer concentration) → automate as `analytics.growth_quality_report(deal)`
- Step 3 (gap map → RFI) → extend `extract.rfi_tracker()` to cross-reference docs + emails + Granola into the RFI Log tab programmatically
- Step 5 (follow-up email) → draft template already supported by Claude subprocess; feed the RFI Log OPEN+P1 rows

The CAT workstream of 2026-04-20 is the first full manual run-through and should be used as golden output when validating the automated pipeline.

---

*Authored: 2026-04-20 from CAT DEALSUPPORT session. Trigger pattern for update: any new deal requiring the same commercial-understanding phase — append divergences, do not rewrite.*
