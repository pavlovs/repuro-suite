# DEAL WORKFLOW SPEC — Repuro (NDA → SPA signing)

Reference workflow for a single deal, NDA through signed purchase contract. Authored by Roman; pre-populated by Claude based on DEALROOM codebase (`PLAN.md`, DR-M1–M8 shipped), prior deal context (CAT, Octopus/HWV), and typical German buy-and-build M&A practice. `[ROMAN: fill in]` = Claude didn't know, needs your input. Replace / rewrite / reorder anything.

---

## Stage 1: NDA and information exchange

- **Trigger**: Initial contact with broker or seller yields willingness to share financials. Teaser / info memo often exchanged first.
- **Duration**: 1–3 weeks (NDA signing often delayed by seller-side legal review)
- **Inputs**:
  - Teaser / info memo (2–5 pages, financial highlights, anonymised customer data)
  - Repuro NDA template `[ROMAN: fill in — German mutual NDA, standard template location?]`
  - Broker contact or direct seller contact
  - Seed row in `deals` table (domain, company name, stage)
- **Activities**:
  - Send Repuro NDA to counterparty
  - Negotiate minor redlines (penalties, duration, carve-outs)
  - Countersign; file in `0_Legal/`
  - Receive data room: GuV, Bilanz, BWA, corporate structure, cap table, customer list (often redacted), material contracts (sometimes)
  - Save into per-deal OneDrive folder `3_Deals/3_Targets/<deal>/`
  - Run `DEALROOM.py ingest-docs --deal <target>` → populates `deal_documents` with auto-classified doc types (DR-M2)
  - Preliminary thesis call internal (Roman + Flo): is this worth Stage 2 effort?
- **Outputs**:
  - Signed NDA (PDF in `0_Legal/`)
  - Raw data room stored per-deal
  - `deal_documents` rows with classified doc types
  - `deals.stage` = `info_exchange`
- **Owner(s)**:
  - Roman: NDA negotiation, counterparty relationship, doc intake
  - Flo: thesis gut-check
  - Counterparty / broker: data room handover
  - System: document registration + classification (DR-M2)
- **Tools today**: Email, OneDrive, Repuro NDA template (Word), DEALROOM CLI (`ingest-docs`), `deals` + `deal_documents` tables
- **Key decisions**:
  - Is the teaser strong enough to justify NDA effort? (first go/no-go)
  - Is the data handed over complete enough to move to Valuation?
- **Failure modes**:
  - Seller sends teaser only, refuses financials without indicative offer (chicken-and-egg)
  - NDA negotiation drags 4–6 weeks
  - Financials arrive as scanned PDFs → OCR / extraction hard
  - Customer list heavily redacted → concentration analysis impossible
  - Piecemeal doc arrival over weeks → triggers repeated re-extraction
- **Done when**:
  - Signed NDA filed
  - ≥2 years GuV + Bilanz + most-recent BWA received and registered
  - `deals.stage` = `info_exchange` or further

---

## Stage 2: Valuation and RFI

> **Sub-steps**: See `DEAL_DELIVERABLES_SPEC.md` §2.1–2.4 for DATA IN / DATA OUT per sub-step (Model Review → Net Debt → Valuation → Scorecard).

- **Trigger**: Core financial docs received (Stage 1 done-when)
- **Duration**: 2–4 weeks (driven by RFI response latency)
- **Inputs**:
  - `deal_documents` financial set
  - `allex.company_records` for the target (company size signals, ownership, employee count)
  - Repuro comparables / multiples for ambulatory healthcare distribution `[ROMAN: fill in — where are these stored / referenced today?]`
  - CAT-comparable historicals if profile matches
- **Activities**:
  - `DEALROOM.py extract --deal <target>` → populates `deal_data` (revenue, EBITDA, margins, concentration, recurring %, employees; DR-M3)
  - Review extraction in dashboard (port 8090, Company Overview tab; DR-M5, DR-M8)
  - Review DR-M3 conflict flags; resolve or queue as RFI question
  - Populate / reconcile Excel valuation model: adjusted P&L (GF salary, one-offs, consolidation), net debt bridge, earn-out matrix (DR-M4, DR-M7)
  - Run live valuation scenarios: `DEALROOM.py scenario` (DR-M7)
  - Draft RFI (`DEALROOM.py draft-rfi` — DR-M6): financial clarifications, customer concentration, contract terms, operational (team, systems), legal (litigation, change-of-control consents)
  - Send RFI to seller/broker; `DEALROOM.py rfi --mark-sent`
  - Receive answers; update `deal_questions`; re-extract if new docs land
  - 1–2 management calls for depth + soft signals (transcripts via Granola → DR-M11 pending)
  - Outside-in market / competition / regulation context (DR-M17 proposed, not built)
  - Internal deal screen review with Flo (Internal Deal Screen tab, DR-M5)
- **Outputs**:
  - Populated `deal_data`
  - `deal_valuations` with scenario outputs (EV range, equity range, earn-out matrix)
  - RFI Word doc filed + answers logged in `deal_questions`
  - Management call notes in `deal_granola` (once DR-M11 ships; today stored ad-hoc)
  - Outside-in canvas HTML (once DR-M17 ships)
  - Go / no-go decision from Flo alignment
- **Owner(s)**:
  - Roman: valuation judgment, RFI curation, management call lead, thesis
  - Flo: second-pair-of-eyes on valuation + Flo alignment gate
  - System: extraction, model population, RFI draft, conflict detection, dashboard
  - Counterparty: RFI answers, management call availability
- **Tools today**: DEALROOM CLI (`extract`, `draft-rfi`, `scenario`, `rfi --mark-sent`), Dashboard (port 8090), Excel valuation model, Word RFI, Email, Granola, OneDrive deal folder
- **Key decisions**:
  - Indicative EV / equity value range
  - Earn-out structure (fixed vs. EBITDA-linked vs. revenue-linked, split over N years)
  - Go / no-go to Indicative Offer
  - Flo alignment on thesis + price
- **Failure modes**:
  - Extraction conflicts unresolved; seller won't clarify
  - Customer concentration too high (>30% single customer = unfinanceable) `[ROMAN: confirm threshold]`
  - Adjusted EBITDA volatile / negative → thesis collapses
  - RFI ignored / partially answered → signal on seller intent
  - Outside-in reveals regulated moat at risk (procurement reform, reimbursement shift)
  - Valuation gap to seller expectation >30% → uncloseable
- **Done when**:
  - Valuation range locked in `deal_valuations`
  - `deal_questions` ≥80% resolved (or material ones specifically resolved)
  - Internal deal screen reviewed with Flo; go decision made
  - `deals.stage` advanced to `indicative_offer` or deal paused

---

## Stage 3: Indicative Offer and negotiation

> **Sub-steps**: See `DEAL_DELIVERABLES_SPEC.md` §3.1–3.2 for DATA IN / DATA OUT (Offer Drafting → Review/Iteration). Template registry also lives there.

- **Trigger**: Stage 2 go decision from Flo alignment
- **Duration**: 1–3 weeks
- **Inputs**:
  - Valuation range (Stage 2)
  - Earn-out structure options
  - Seller expectation (from Stage 2 calls)
  - Broker guidance (if sell-side broker involved)
  - Financing capacity: Kamu fundraise status + debt appetite
- **Activities**:
  - Draft indicative offer letter: price range, structure (share vs. asset deal), earn-out terms, exclusivity, DD timeline, financing contingency, process steps
  - `[ROMAN: fill in — is there a Repuro indicative offer template today?]`
  - Send to counterparty (often via broker)
  - Receive pushback / counter (price, earn-out split, rollover, timing)
  - Iterate 1–3 rounds; align with Flo each round
  - Log progress in `deal_notes` / `deal_actions` / `deal_emails` (DR-M10 Email Composer pending)
- **Outputs**:
  - Indicative offer letter sent (PDF in `0_Legal/` or `0_Offers/` — `[ROMAN: confirm folder]`)
  - Counter-proposals logged
  - Revised valuation / structure if negotiation changes assumptions
  - Verbal or written agreement on key terms
- **Owner(s)**:
  - Roman: offer authorship, negotiation lead
  - Flo: final-round alignment
  - Counterparty / broker: counter, accept, reject
  - System: offer drafting is **not built today** in DEALROOM — `[ROMAN: should DEALROOM draft indicative offers? Possible DR-M-later milestone.]`
- **Tools today**: Email, Word (offer drafting), `deal_notes` / `deal_actions`, Excel (sensitivity on counter-proposals). **No DEALROOM automation today.**
- **Key decisions**:
  - Opening price vs. walk-away price
  - Share deal vs. asset deal
  - Earn-out split (e.g., 70% close / 30% over 2–3 yrs, EBITDA-linked — `[ROMAN: Repuro standard?]`)
  - Exclusivity duration (8–12 weeks market typical — `[ROMAN: confirm Repuro standard]`)
  - Rollover equity for seller/GF if applicable
- **Failure modes**:
  - Seller rejects price → deal dies or reset to Stage 2 with new model
  - Competing bidder emerges (rare in proprietary deals, real in broker-led processes)
  - Financing contingency tight → Kamu close not done yet
  - Seller verbal-agrees then retreats on written version
- **Done when**:
  - Verbal or written agreement on key terms (price, structure, exclusivity)
  - Both sides committed to moving to LOI drafting
  - `deals.stage` = `indicative_agreed` (or equivalent — `[ROMAN: confirm stage taxonomy]`)

---

## Stage 4: LOI signed

- **Trigger**: Stage 3 verbal/written agreement
- **Duration**: 1–2 weeks
- **Inputs**:
  - Agreed key terms (Stage 3)
  - Repuro LOI template `[ROMAN: fill in — template, or drafted fresh by external lawyer each time?]`
  - External M&A lawyer `[ROMAN: fill in — which firm?]`
- **Activities**:
  - External lawyer drafts LOI from agreed terms
  - Internal review (Roman + Flo)
  - Send to counterparty; counterparty's legal reviews
  - Final redlines: exclusivity clause wording, break fee (if any), confidentiality extension, DD scope boilerplate, LOI-to-SPA timeline, long-stop
  - Both sides countersign
  - Optional internal announcement (Repuro team; investors in deal-update if material)
  - DD workstream kickoff scheduled
- **Outputs**:
  - Signed LOI (PDF in `0_Legal/`)
  - Exclusivity clock started (dated)
  - DD checklist prepared
  - `deal_documents` updated; `deals.stage` = `loi_signed`
- **Owner(s)**:
  - Roman: final negotiation, signature
  - Flo: co-signature if applicable
  - External lawyer: drafting + redlines
  - Counterparty + their lawyer: review, redlines
  - System: `DEALROOM.py ingest-docs` to register the signed LOI
- **Tools today**: Email, external lawyer, Word, DocuSign or wet-sign scan, DEALROOM (`ingest-docs`)
- **Key decisions**:
  - Exclusivity duration (8–12 weeks typical)
  - DD scope and timeline
  - Break fee and triggers (if any)
  - Public disclosure — confidential until SPA by default
- **Failure modes**:
  - Counterparty legal adds onerous conditions post-verbal agreement
  - LOI language ambiguous → disputes during DD
  - Exclusivity too short for realistic DD scope
  - Internal legal review on counterparty side drags
- **Done when**:
  - Countersigned LOI filed
  - `deals.stage` = `loi_signed`
  - DD team kickoff scheduled

---

## Stage 5: Due Diligence

- **Trigger**: LOI signed
- **Duration**: 4–12 weeks (scope and target size dependent)
- **Inputs**:
  - LOI with agreed DD scope
  - DD checklist across: financial, tax, legal, commercial, operational, IT, HR, ESG/regulatory
  - External advisors (legal always; financial/tax usually; operational for larger targets)
  - Full data room access (expanded from Stage 1)
- **Activities**:
  - **Financial DD** — Quality of Earnings, working capital mechanics, detailed net debt bridge. `[ROMAN: fill in — external (BDO/Mazars/etc.) or in-house?]`
  - **Tax DD** — historical tax risks, VAT, payroll, open audits. `[ROMAN: fill in — advisor?]`
  - **Legal DD** — contracts, litigation, IP, employment, compliance, corporate records. External law firm.
  - **Commercial DD** — customer reference calls, market validation, competitor positioning. `[ROMAN: fill in — in-house or external?]`
  - **Operational DD** — ops walkthroughs, site visits, systems review, supplier review
  - **IT / Data DD** — systems inventory, DSGVO compliance, cybersecurity posture
  - **HR DD** — key-employee retention, compensation, Betriebsrat if applicable
  - DD-scoped Q&A cycle (expanded RFI)
  - Red-flag log: each finding with materiality + recommended action (price chip / specific indemnity / walk)
  - Integration planning (parallel): 100-day plan, add-on thesis, team / brand integration
- **Outputs**:
  - DD report per workstream
  - Consolidated red-flag log
  - Price / structure adjustment recommendations (→ Stage 6 input)
  - Integration plan draft
  - `deal_documents` heavily expanded (contracts, DD reports, legal files)
- **Owner(s)**:
  - Roman: overall DD program manager, commercial DD, red-flag decisions
  - Flo: operational / integration angles
  - External advisors: financial / tax / legal / ops DD workstreams
  - Counterparty: data room expansion, management availability
  - System: **not covered by DEALROOM today**. DEALROOM charter per `PLAN.md` stops at LOI. `[ROMAN: should DEALROOM extend to DD workstream tracking?]`
- **Tools today**: External advisors (primary), dedicated DD data room (possibly separate from Stage 1 room), Excel for red-flag tracking, Email, OneDrive. No DEALROOM tooling.
- **Key decisions**:
  - Which workstreams in scope (size-dependent)
  - Red-flag materiality: price chip vs. specific indemnity vs. walk vs. absorb
  - Integration thesis: standalone entity vs. carve-in to existing Repuro entity
  - Closing conditions (regulatory, key customer consents, financing, employment retention)
- **Failure modes**:
  - Material undisclosed liability found → price chip or walk
  - Customer reference calls reveal concentration / churn risk
  - Seller slow on data room expansion → exclusivity burns
  - Regulated relationships non-transferable
  - Betriebsrat / key-employee pushback
  - Key employee departures during DD
  - Tax audit surfaces mid-DD
- **Done when**:
  - All DD workstreams closed
  - Red-flag log consolidated, each item priced or dismissed
  - Go / no-go SPA decision made with Flo
  - `deals.stage` = `dd_complete` `[ROMAN: confirm stage value exists in taxonomy]`

---

## Stage 6: Contract Negotiation

- **Trigger**: DD complete; go decision on SPA
- **Duration**: 4–10 weeks
- **Inputs**:
  - LOI terms (price, earn-out, closing conditions)
  - DD findings (price chips, specific indemnities)
  - External M&A lawyer drafting SPA
  - Financing fully committed (Kamu equity closed + any debt signed)
- **Activities**:
  - External lawyer drafts SPA from LOI + DD findings
  - Iterate on: purchase price mechanism (locked box vs. closing accounts), working capital peg, reps and warranties, indemnity cap and basket, specific indemnities (DD-driven), non-compete, earn-out mechanics + dispute resolution, closing conditions, long-stop date
  - Ancillary docs: shareholders' agreement (if rollover), key-employee employment agreements, escrow agreement, management incentive plan
  - Signing prep: funds flow memo, closing mechanics, signing-meeting logistics
  - Post-sign / pre-close: satisfy closing conditions (regulatory approvals, key-customer consents, financing drawdown, W&I insurance if used)
  - Closing: funds flow executed, shares transfer, optional public announcement
- **Outputs**:
  - Signed SPA (PDF in `0_Legal/`)
  - Shareholders' agreement, employment agreements, escrow, MIP docs
  - Closing memo
  - `deal_documents` fully expanded
  - `deals.stage` → `signed` then `closed`
- **Owner(s)**:
  - Roman: commercial negotiation on SPA points, final sign-off
  - Flo: co-sign if applicable
  - External M&A lawyer: primary drafter, negotiation tactics
  - Counterparty + their lawyer: redlines
  - Tax + financing advisors: structure, funds flow
  - System: **not covered by DEALROOM today**
- **Tools today**: External lawyer (primary), Email, Word (SPA drafts), DocuSign / wet-sign, OneDrive. No DEALROOM tooling.
- **Key decisions**:
  - Purchase price mechanism: locked box vs. closing accounts
  - Working capital peg level
  - R&W cap (10–25% of EV typical `[ROMAN: confirm Repuro range]`) and basket
  - Earn-out final mechanics + dispute resolution
  - Specific indemnities for DD-identified risks
  - Management rollover terms (if applicable)
  - W&I insurance used or not
- **Failure modes**:
  - SPA negotiation breaks on price chip
  - Seller's lawyer slow-walks drafts → exclusivity burns
  - Financing falls through (Kamu or debt)
  - Regulatory / consent conditions un-satisfiable by long-stop
  - R&W gap too wide
  - Earn-out accounting disagreement blocks signing
- **Done when**:
  - SPA signed
  - Closing conditions satisfied
  - Funds flow executed; shares transferred
  - `deals.stage` = `closed`
