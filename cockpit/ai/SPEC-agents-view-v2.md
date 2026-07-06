# SPEC — Agents view v2: Inbox-first sub-tabs

Status: **REVISED after Opus review (§6) — v2.1 recommendation is the two-tab cut.**
Not built. Author: Claude · Date: 2026-07-06
Trigger: Roman — "with the long queue, Recently completed, Playbook, How-to-set-up
kinda gets lost in the single Agent tab. Rethink how a sensible agent UX/UI would work."
Supersedes: SPEC-agents-view.md (2026-06-23, tabs proposed, stack built instead —
queue volume has since proven the tabs point).

---

## 1. Diagnosis

The tab stacks seven sections in one scroll: Needs your review, Waiting on you,
Running, Queue (11+ cards), Recently completed, Proposed lessons, Playbook, FAQ.
Three different intents compete on one axis:

| Intent | Sections | Frequency |
|---|---|---|
| **Act** — decisions only Roman can make | Needs your review, Waiting on you, Proposed lessons | every visit — THE reason the tab exists |
| **Manage** — order and feed the machine | Queue, Running, Recently completed | occasional |
| **Reference** — rules and docs | Playbook, FAQ | rare |

Two structural faults: the *Act* items sit above a 11-card queue but "Proposed
lessons" sits BELOW it — an action item buried under management noise; and
everything scales linearly with queue length, so the tab gets worse exactly as
the workflow succeeds.

## 2. Recommendation — three sub-tabs, Inbox first

Replace the stack with a segmented sub-nav under the Agents header (same pattern
as the existing Lane filter — no new component language):

```
Agents        [ Inbox (3) | Queue (11) · 2 running | Playbook (5) ]      Lane: All·RC·FC
──────────────────────────────────────────────────────────────────────
INBOX (default when n>0)          QUEUE                    PLAYBOOK
 1. Review cards (full width,      Running strip (top,      Active rules
    evidence + preview + verdict     claimed_by + lease)      (hard/soft chips,
    bar — unchanged)               Ordered queue cards        retire)
 2. Waiting on you (question +       (position #, Round-N,  Recently completed
    inline answer)                   drag-reorder)            (moved here — audit,
 3. Proposed lessons (adopt/       [+ New agent task]         collapsible)
    dismiss — moved UP from                                 How to set up & run
    below the queue)                                          (FAQ, collapsed)
```

- **Inbox** = everything that waits on a human, one prioritized list: reviews →
  questions → lesson candidates. Empty inbox says so explicitly ("Nothing needs
  you — N queued, M running"). Landing tab whenever it is non-empty, else Queue.
- **Queue** = the machine's side: Running pinned on top (lease freshness), then
  the ordered queue with drag-reorder and inline "+ new agent task". Round-N
  badges stay on redo cards.
- **Playbook** = rules + history + docs: active playbook (retire), Recently
  completed (audit trail, moved out of the main flow), FAQ.
- **Tab counts do the awareness job** — Inbox badge amber when >0 (same
  `ag-count-attn` token), Queue shows `n · k running`. The sidebar "Agents"
  badge keeps showing the in_review count as today.
- Lane filter stays global across tabs (top right), prefiltered to your lane.

## 3. Why this cut (and not the alternatives)

- **Inbox-first matches the §7 cadence**: the design intent is "live in the
  browser, act on what lands". One actionable list beats three sections
  interleaved with management surfaces. Verdict cards keep full width.
- **Sub-tabs, not more collapsibles**: collapsing hides, it doesn't organize —
  the FAQ/Playbook already collapse and still add scroll noise between the
  queue and the lessons.
- **Not a kanban board**: unchanged from the v1 spec — review needs width,
  boards optimize spatial overview at review's expense.
- **Not a separate top-level view**: the Agents tab is already a destination;
  splitting into two sidebar entries would spread one workflow over two places.
- Considered and deferred: an "Awaiting your verdict" tile on the Cockpit
  landing (Overview) deep-linking to Inbox — good complement, separate small
  change, not part of this restructure.

## 4. Scope

- **Frontend only** — zero API changes; all data already in `/api/state`.
  `view-agents.jsx` restructure (sub-tab state, section moves), small CSS.
- Keep: all card components as built (review card, blocked card, queue card,
  lesson row). This is re-homing, not redesign.
- e2e: extend the Agents journey to click through all three sub-tabs.
- Effort: ~1 focused session incl. verification loop.

## 5. Open point (single)

Default tab when Inbox is empty: **Queue** (recommended — next-most-useful) or
always land on Inbox to confirm "nothing needs you"? Recommendation: Queue, with
the Inbox tab still showing its zero state when clicked.

---

## 6. Opus review (2026-07-06) + revised recommendation — v2.1

Opus verdict: **SHIP WITH CHANGES.** Key findings, all adopted:

1. **The real "long queue" fix is density, not location** (MUST): queue items
   become compact single-line rows (`#pos · title · lane · ready/blocked · deal`),
   not 2-col cards with full AC text — ~3-4x height cut. AC/detail show in the
   task drawer on click. Review cards keep full width; queue rows don't need it.
2. **The three-tab cut was one tab too many** (Opus's strongest point, accepted):
   splitting Review from Queue breaks the §7 watch-model — the SSE card motion
   (Queue → Running → Needs your review, live in the open tab) degrades to a
   badge tick on a tab you're not watching. **v2.1 = TWO tabs:**
   - **Work** (default): Needs your review → Waiting on you → Proposed lessons
     (visually subordinate strip, own muted count — never the same amber badge
     as blocking items) → Running (with lease-staleness chip) → compact Queue
     (+ new agent task). One canvas, the live motion preserved, reference noise gone.
   - **Reference**: Playbook (rules) → Recently completed (audit) → nothing else.
   - **Setup FAQ** leaves the stack entirely → persistent "?" help affordance in
     the Agents header (it was the named "gets lost" item; burying it under a
     "Playbook" label would make that worse).
3. **Sticky tabs** (SHOULD, adopted): initial land = Work; never auto-switch after
   an action empties a section — zero states instead.
4. **Counts follow the active lane filter** (ambiguity resolved): all badges and
   section counts reflect the selected lane; switching lane re-counts.
5. **Deal grouping/filter**: deferred — premature at 10-15 tasks; revisit when the
   queue spans 4+ deals regularly.
6. **Mobile**: explicitly desktop-first (existing grid collapses to one column;
   no further responsive work in this scope).

Net effect vs the original stack: same single-canvas workflow, minus the three
reference sections, minus the queue-card bloat, plus correct priority for
lesson candidates. Smaller change than v2.0, closer to the complaint.

---

## 7. FINAL — Roman's call (2026-07-06): THREE views + all orthogonal Opus MUSTs

Roman chose the three-view cut (Opus decision #1 → three). Build target:

| View | Contents (top→bottom) |
|---|---|
| **Inbox** (default when blocking items > 0) | Review cards (full width, unchanged) → Waiting on you (inline answer) → Proposed lessons (SUBORDINATE strip: muted styling + separate muted count — never the amber badge) |
| **Queue** | Running (pinned, claimed_by + lease-staleness chip: amber when lease < 60 min or heartbeat stale) → compact single-line queue rows (`#pos · title · Round-N · lane · deal · ready/blocked`) with drag-unaffected order display + "+ new agent task" → Recently completed (collapsed, tail of the lifecycle) |
| **Playbook** | Active rules only (hard/soft chips, retire) |

Cross-cutting (Opus MUSTs/SHOULDs, all in scope):
- **FAQ → "?" help affordance** in the Agents header (opens the setup guide as an overlay/panel) — not inside any tab.
- **Tab badges**: Inbox badge = reviews + questions ONLY (amber when >0); lessons get their own small muted count on the tab (e.g. `Inbox (2) ·1`) or inside only. Queue tab shows `Queue (n) · k running`.
- **All counts follow the active lane filter**; lane switch re-counts everything.
- **Sticky tabs**: initial land = Inbox if (reviews+questions) > 0 else Queue; NEVER auto-switch after an action; emptied sections show zero states.
- **Zero states** for all three views.
- **Queue rows compact**: no AC text on the row; click opens the task drawer.
- Desktop-first (existing responsive collapse only).

### 7a. Acceptance criteria (verifier checklist — context-free agents get THIS verbatim)

AC1. Agents view shows a 3-segment sub-nav: Inbox, Queue, Playbook. No other
     top-level sections exist on the page outside the active view.
AC2. Inbox contains, in order: in_review verdict cards; blocked-with-question
     cards with a working inline answer input; a visually subordinate
     "Proposed lessons" strip. It contains NO queue cards, NO running cards,
     NO playbook rules, NO FAQ.
AC3. The Inbox tab badge counts ONLY in_review + blocked items and uses the
     attention (amber) style when > 0; lesson candidates are NOT in that number.
AC4. Queue view: running tasks pinned on top showing claimed_by and a lease
     indicator; queue items are single-line rows (< 40px tall) WITHOUT
     acceptance-criteria text; row click opens the task drawer; a
     "+ new agent task" affordance exists; Recently completed appears
     collapsed at the bottom of Queue.
AC5. Playbook view lists active rules with hard/soft kind chips and a retire
     action — and nothing else.
AC6. The setup FAQ is reachable via a "?" affordance in the Agents header and
     is NOT rendered inside any of the three views.
AC7. Switching lane (All/RC/FC) changes tab badge numbers and view contents
     consistently.
AC8. Approving the last review in Inbox does NOT auto-switch the tab; Inbox
     shows a zero state naming the queued/running counts.
AC9. A task with review_round > 0 shows a Round-N badge and the feedback text
     — in Inbox on its review card when in_review, and on its compact queue
     row (badge at minimum) when re-queued.
AC10. All existing flows still work end-to-end: answer→requeue, adopt/dismiss
      lesson, approve/request-changes/reject/escalate, artifact preview pane
      (md rendered, pdf embedded).

### 7b. Verification design — context-free, generator≠reviewer

Deterministic first (all must pass before any agent verdict):
1. JSX bundle babel-compiles.
2. Full pytest (API untouched — must stay green).
3. Seeded e2e (local sandbox): fixtures = 1 in_review with md preview, 1 blocked
   with question, 1 round-2 queued, 6+ plain queued, 1 running (claimed), 2
   lesson candidates, 1 active playbook rule. Script drives: all 3 tabs +
   lane switch + answer flow + adopt flow + "?" help open. Screenshots each
   state. Zero PAGEERROR required.

Then two FRESH-CONTEXT verifier agents (Sonnet; they get ONLY what's listed):
- **V1 code verifier**: inputs = AC checklist verbatim + view-agents.jsx +
  boot.js + cockpit-extras.css paths. Job: for each AC, cite the code that
  satisfies it (file:line) or flag FAIL. No screenshots — code truth only.
- **V2 visual verifier**: inputs = AC checklist verbatim + the e2e screenshots
  ONLY (no code, no spec §1-6). Job: judge each AC as a fresh user looking at
  the pixels; explicitly hunt for Opus's failure modes (queue still noisy?
  lessons visually equal to reviews? FAQ visible in a tab?).
- Verdict rule: every AC needs PASS from BOTH verifiers (V1 code + V2 visual
  where visually observable). Any FAIL → fix → re-run THAT verifier. Max 2
  correction loops, then surface to Roman.

### 7c. Validation results (built + shipped 2026-07-06, suite v2.1.20)

- Deterministic: bundle compile ✓, 108 pytest ✓, seeded e2e all 3 tabs +
  lane switch + answer/adopt flows + help overlay, 0 pageerrors ✓.
- **V2 visual verifier: PASS 10/10 ACs** first pass. Minor findings adopted:
  Playbook count relabeled "N of max 40" (read as pagination); noted ·N lesson
  marker learnability.
- **V1 code verifier: FAIL round 1** — AC7 (lesson/playbook badges not
  lane-filtered) + AC9 (reviewFeedback mapped but never rendered on the review
  card). Both fixed; V1 re-run: **PASS 10/10**. Its "missing CSS" finding was
  withdrawn (classes live in cockpit-views.css).
- Fix round count: 1 of max 2. Orphaned card CSS removed with the restructure.
- Non-blocking observations left open: approve flow also reassigns task owners
  to the reviewer (pre-existing behavior, predates this build — flag to Roman
  whether intended); "Adopt" button label vs API action "promote" naming drift.
