# M15: Dashboard Overhaul — Operating Console

## Summary

Redesign the dashboard from a reporting tool into an operating console for moving leads toward meetings. New tab structure separates backward-looking performance reporting (BA cohort results) from forward-looking pipeline preparation (readying the next BA), and centralises all action items into a single prioritised work queue. Decision-useful tables replace descriptive charts wherever possible.

---

## Design Rationale

Roman uses this tool for three distinct jobs:

1. **Pre-BA prep**: How many leads are ready to send? What's blocking them?
2. **Daily ops**: Who replied? What needs action today?
3. **BA retrospective**: How are the cohorts performing? Is the approach working?

The old "Overview" tab tried to do all three simultaneously and ended up doing none well. The new structure assigns one tab to each job, plus a reference tab for lookup.

---

## Tab Structure

### Tab 1 — Performance *(backward-looking)*

**Purpose**: Track outreach effectiveness across BA cohorts. Roman checks this after each send and weekly.

**KPI row** (6 cards, Positive Rate is primary/largest):
| Card | Value | Sub-text |
|------|-------|---------|
| Positive Response Rate | 15.5% | 57 of 367 approached |
| Total Answer Rate | 27.8% | 102 total answers |
| Positive Answers | 57 | Contact + Meeting + More |
| Meetings / Advanced | 29 | Meeting + Financials + Offer |
| Total Approached | 367 | BA1–BA7 |
| Lost | 40 | 10.9% of approached |

**BA Performance table** (main content, full-width):
| Cohort | Sent | No Response | NR% | Contact Made | CM% | Positive Total | Pos% | Negative | Neg% |
|--------|------|-------------|-----|-------------|-----|---------------|------|----------|------|
| BA1 | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| ... | | | | | | | | | |
| **Total** | | | | | | | | | |

- Positive = contact + meeting + financials + offer + deal
- Negative = declined
- No Response = sent + followup1 + followup2

**Response breakdown table** (below BA table, compact):
| Status | Count | % of Approached | Description |
|--------|-------|----------------|-------------|
| Follow-Up 2 Sent | 101 | 27.5% | FU2 sent |
| Follow-Up 1 Sent | 164 | 44.7% | FU1 sent |
| Letter Sent | 0 | 0% | No FU yet |
| Contact Made | 28 | 7.6% | Replied |
| Meeting Done | 26 | 7.1% | Meeting held |
| Financials Received | 3 | 0.8% | Data received |
| Hold | 5 | 1.4% | Timing |
| Lost | 40 | 10.9% | Declined |
| **Total** | **367** | | |

**Source quality table** (collapsed by default, below):
Source | A | B | A+B% | C | D | E | S | Total

No charts on this tab. Dense tables only.

---

### Tab 2 — Current BA Prep *(forward-looking)*

**Purpose**: Assess readiness for the next Briefaktion. Shows only "Current" records (briefaktion IS NULL — companies not yet sent a letter). Answers: how many leads are ready? What's blocking?

**KPI row** (6 cards):
| Card | Value | Sub-text |
|------|-------|---------|
| Current Pipeline | 2,053 | New leads not yet approached |
| A + B Qualified | X | Pipeline-ready targets |
| Ready to Send | X | A/B + email confirmed |
| Missing Email | X | A/B + no email found |
| Unclassified | X | Scraped but no klass yet |
| Unscraped | X | Filter pass, not yet scraped |

**Pipeline funnel table** (left column, 60% width):
```
Stage                   Count    Conv.
────────────────────────────────────
Total ingested          2,053
  Filter pass           X        X%
  Scraped               X        X%
  Classified            X        X%

Classification
  A — Platform          X        X% of classified
  B — Add-on            X        X% of classified
  C — Unclear           X        X%
  D — No-fit            X        X%
  E — Special           X        X%

Outreach Readiness
  A+B with email        X        X% of A+B
  A+B missing email     X        X% of A+B
```

**Blockers / Next Steps** (right column, 40% width — the action queue):
Ordered strictly by what needs to happen before the next BA can be sent:

1. 🔴 X records need scraping → `python pipeline.py scrape`
2. 🟠 X scraped records unclassified → `python pipeline.py classify`
3. 🟠 X C records need review decision → [Requires Attention tab]
4. 🟡 X A/B records missing email → [Requires Attention tab]
5. 🟢 X A/B ready to send now → [Lead Table tab]

Each blocker is a row showing count + description + CLI command or tab link. When count = 0, show green checkmark ("Done") instead.

**Note**: This tab always shows the "Current" view (no BA filter applied). The global BA filter bar is hidden/disabled on this tab.

---

### Tab 3 — Requires Attention *(work queue)*

**Purpose**: Everything Roman needs to actively do, in priority order. Replaces the old C-Review Queue. Interactive — write-back controls visible when server is running.

**Section 1: Positive Replies — Action Needed** *(highest urgency)*
- Companies with `outreach_status IN (contact, meeting, financials, offer)` — need scheduling or advancement
- Table: Name | BA | Status | Owner | Email | Phone
- Action hint per row (e.g. "Schedule meeting", "Request financials")
- Empty state: ✓ All positive replies actioned

**Section 2: Follow-Up Queue** *(medium-high urgency)*
Two sub-sections:
- **FU1 pending** (status = `sent`): sent a letter, no follow-up yet
- **FU2 pending** (status = `followup1`): sent FU1, no FU2 yet
- Each as a compact table: Name | BA | Sent Date | Owner | Email
- Roman decides timing; this surfaces the candidates

**Section 3: C Records — Classify Now** *(medium urgency)*
- klass=C records not yet approached (or all C, regardless of approach status)
- Cards with: company name, domain, region, MA, services_score, AI reasoning
- Write-back buttons per card: → A | → B | → D | → E
- Progress counter: "X of Y reviewed"
- Sorted by services_score descending (most interesting first)

**Section 4: A/B Missing Email** *(medium urgency)*
- A/B companies, not approached, no gf_email
- Table: Name | Domain | Owner Name | Region | MA Count | [open domain link]
- Purpose: Roman researches emails manually or triggers Hunter

**Section 5: S Records — Confirm Exclusion** *(low urgency)*
- klass=S records pending manual review before final exclusion
- Shows ownership reason that triggered S classification
- Write-back: confirm as S (exclude) or override to B/C
- Usually ≤5 records

Each section shows a count badge in the section header and collapses when count = 0.

---

### Tab 4 — Lead Table *(reference)*

Unchanged from current implementation. Full searchable/sortable table with all records. Filters: search, klass, source, region, outreach status, BA. Shows all 2,420 records.

---

### Tab 5 — Outreach Tracker *(reference)*

Renamed from "Post-Sendout Tracking". Otherwise unchanged — full outreach history table, sortable by any column, with stats pills showing Positive Rate, Answer Rate, Positive count, Lost count.

---

## What stays the same

- Header + ALLEX logo
- Collapsible classification legend
- BA filter bar (shown on Performance + Lead Table + Outreach Tracker; hidden on Current BA Prep)
- `computeView(ba)` filter logic
- Side panel (company card) + iframe
- Write-back API (`/api/patch`, `/api/data`)
- `setBAFilter()`, `destroyChart()`, `outreachHtml()`, `klassHtml()` helpers

## What changes

| Element | Change |
|---------|--------|
| Overview tab | Replaced by Performance tab |
| C Review Queue tab | Replaced by Requires Attention tab (expanded) |
| Tab order | Performance / Current BA Prep / Requires Attention / Lead Table / Outreach Tracker |
| KPI cards | Positive Rate is primary (large), order reflects operating priority |
| Funnel display | Table with rates, split between discovery (Performance) and prep (Current BA Prep) |
| Charts | Klass/D-reason/Size/Age charts moved to secondary position on Performance tab (collapsed section) or removed |
| Action queue | Expanded and split: pipeline prep blockers on Tab 2, post-outreach actions on Tab 3 |
| Source quality | Stays on Performance tab, shows A+B% |

---

## Implementation steps

1. **HTML structure** — rewrite tab bar and all tab content divs
2. **CSS** — add section headers, section collapse, progress counter styles
3. **JS — Performance tab**: `renderPerformanceKPIs()`, `renderBATable()` (already done), `renderResponseBreakdown()`, `renderSourceQuality()` (update)
4. **JS — Current BA Prep tab**: `renderPrepKPIs()`, `renderPrepFunnel()`, `renderBlockers()`
5. **JS — Requires Attention tab**: `renderPositiveReplies()`, `renderFollowUpQueue()`, `renderCQueue()` (refactor existing), `renderMissingEmail()`, `renderSReview()`
6. **JS — `renderAll()`** — orchestrate all new functions, remove obsolete calls
7. **BA filter bar** — hide on Current BA Prep tab (it always shows current records only)

---

## AI validation results

Run 2026-03-28:

- `python -m pytest tests/ -q` → **162 passed** (no regressions)
- `python pipeline.py dashboard --dry-run` → **5,112,077 chars**, 0 errors
- Template: `src/pipeline/templates/dashboard.html` rewritten from 4 tabs to 5 tabs
- Performance tab: KPI row (Positive Rate 15.5%, Total Answer Rate, Positive Answers, Meetings/Advanced, Total Approached, Lost), BA Performance table, Response Breakdown table, Source Quality table
- Current BA Prep tab: 6 KPI cards (Current Pipeline, A+B Qualified, Ready to Send, Missing Email, Unclassified, Unscraped), pipeline funnel table, blockers list with CLI commands
- Requires Attention tab: 5 sections with count badges — Positive Replies, Follow-Up Queue, C Records (with inline → A/B/D/E write-back buttons), A/B Missing Email, S Records (with inline → B/C override)
- Lead Table: unchanged, updated outreach filter options to full granular status list
- Outreach Tracker: renamed from "Post-Sendout Tracking", unchanged content
- BA filter bar: hidden on Prep and Requires Attention tabs via `showTab()` toggle
- Write-back: `inlinePatch()` function for C-card and S-record inline classification (serve mode only)
- Deviations: none. Plan followed exactly.

---

## Definition of done

- `pytest tests/ -q` passes
- `python pipeline.py dashboard --dry-run` builds without error
- `python pipeline.py dashboard --serve` — all 5 tabs render correctly
- Performance tab shows correct Positive Rate (15.5%), BA table, response breakdown
- Current BA Prep tab shows pipeline funnel for briefaktion-IS-NULL records only
- Requires Attention tab shows all 5 sections; empty sections show green checkmark
- Write-back (klass override, outreach status) still works in serve mode
- BA filter bar hidden on Current BA Prep tab, visible on all others
