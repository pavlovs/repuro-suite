# SPEC — Agents view v2: Inbox-first sub-tabs

Status: **SPEC for review** — not built. Author: Claude · Date: 2026-07-06
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
