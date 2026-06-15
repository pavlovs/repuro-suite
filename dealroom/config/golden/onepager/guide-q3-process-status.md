# Process & Status (Q3) — Generation Guide

## Purpose
Current deal status, timeline, next steps, and key risks. This quadrant tells an investor (or Roman in a review meeting) exactly where the deal stands and what needs to happen next — operational, not narrative.

## Output format
- Bullet count: 3-5
- Length per bullet: 1-2 sentences max
- Language: English (German legal/process terms acceptable: GF, Geschäftsführer, Gesellschafter, Kaufpreisanpassung)
- Tone: Internal/operational, action-oriented. State facts and open items — no diplomatic hedging.
- Formatting: Bold the key status word or metric in each bullet (e.g., stage name, number of open questions, next action).

## Topics to cover
1. **Transaction structure** — acquiring what (100% of shares / majority / minority), from whom (GF-owner, external shareholder), sourcing channel (broker, direct)
2. **Stage + duration** — current deal stage and days/weeks in that stage; key milestone that triggered the stage transition
3. **Open information gaps** — count of open questions (sent, answered, pending); the single most critical missing data item
4. **Last meaningful contact** — date and nature of last substantive interaction (call, email, meeting, data room access)
5. **Key risk or open item** — the one thing that could derail or delay the deal; price expectation gap, DD finding, legal complexity, or seller hesitation
6. *(Optional)* **Next step** — the specific action required to advance, with owner (Roman vs. seller vs. advisor)

## Data sources
The generator will have access to the following fields:

| Field | Source table/column |
|-------|---------------------|
| Deal stage | `deals.deal_stage` |
| Stage entered at (date) | `deals.stage_entered_at` |
| Last contact date | `deals.last_contact_at` |
| Open questions count | `deal_questions` — count where `answered_at IS NULL` |
| Sent questions count | `deal_questions` — count where `sent_at IS NOT NULL` |
| Answered questions count | `deal_questions` — count where `answered_at IS NOT NULL` |
| Key open question text | `deal_questions` — most recent unanswered question with highest priority |
| Recent notes | `deal_notes` — most recent 1-2 notes (date + body) |
| Open actions | `deal_actions` — open items with due date |
| Transaction structure | `deals.transaction_structure` (if field exists) or `deals.description` |
| Investment thesis / sourcing | `deals.investment_thesis` |
| Valuation offer sent | `deal_valuations.offer_sent_at`, `deal_valuations.ev_closing` |

## Example bullets

- **Stage: Indicative Offer (42 days)** — indicative offer submitted 2026-03-15 at €1.4m EV (3.7x 2025A EBITDA); awaiting seller counter or confirmation to advance to exclusivity.
- **3 open questions pending** (7 sent, 4 answered) — key gap: FY2025 full-year P&L and balance sheet not yet received; requested 2026-04-02.
- **Last contact: 2026-04-20** (broker call re: exclusivity timeline) — seller has not engaged since; follow-up scheduled for week of 2026-04-28.
- **Key risk: price expectation gap** — seller indicated 5x EBITDA verbally; our offer implies 3.7x closing / 5.0x incl. earn-out; earn-out structure may not bridge the gap if seller wants cash certainty.
- **Next step**: schedule management meeting upon receipt of FY2025 accounts — Roman to follow up with broker by 2026-04-30.

## Constraints
- Never invent deal milestones or interactions not supported by the DB records (notes, questions, stage log).
- If `last_contact_at` is null or stale (>30 days), flag it explicitly: "Last contact: [DATE] — no response in X days."
- Stage duration must be computed from `stage_entered_at` to today — state as "X days" not "several weeks."
- If fewer than 3 bullets can be generated from available data, mark the missing ones as `[DATA MISSING — Roman to complete]` rather than fabricating content.
- Valuation figures in the process bullet must match `deal_valuations` exactly — do not estimate or round.
- Q3 confidence is LOW (per spec) — this quadrant is the most deal-specific and the most likely to require Roman's direct edit. The draft is a starting point, not a final text.
- Do NOT include financial performance data (revenue, EBITDA) in Q3 — that belongs in Q1. Q3 is about process state only.
- Risk bullet must be concrete: a specific gap, number, or unresolved item — not a generic "execution risk."
