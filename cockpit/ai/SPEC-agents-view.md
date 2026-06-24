# SPEC — Cockpit Agents View redesign

Status: **SPEC for review** — not built. Author: Claude · Date: 2026-06-23
Question from Roman: should the Agents view be one bulk list, or sections/tabs?

---

## 1. The agentic workflow (what the view must serve)

- **Lifecycle:** `open` (queued) → `in_progress` (agent claimed via `/repuro:run`,
  holds a 4h lease + heartbeats) → `in_review` (awaits human verdict) → `done`
  (approved) **or** back to `open` (sent back with feedback). `blocked` = open with
  an unmet prereq (red).
- **Actors / lanes:** human authors tasks + gives verdicts; agent
  (`rc-agent`/`fc-agent`) claims, executes, posts evidence. Lane = RC / FC by
  `created_by` (now token-derived end to end).
- **Cadence (the §7 end-state):** Roman and Flo each run a continuous loop and live
  in the browser, watching tasks land in **Awaits verdict** and approving / sending
  back inline. **→ Verdict review is the primary, highest-frequency action.**

## 2. Why the current single view stops scaling

Today: one flat card stack (verdict → running → queued, done collapsed) + the FAQ
panel. Fine at low volume. As loops + two people raise volume it breaks down:

- The **verdict items** (the thing needing a human) get diluted in one long scroll.
- **No focused review surface** — evidence is raw text, not the rich review the
  original agent-skills spec §4a intended (summary + clickable artifact links).
- **Lane (RC/FC) isn't surfaced**, and there's no Mine/All filter.
- It conflates **three different intents** — review, monitor, triage — in one column.

## 3. The three+ distinct modes (different intent, cadence, layout needs)

| Mode | Intent | Layout need |
|---|---|---|
| **Review** (in_review) | Approve / send back — the money action | **Full width**: title, AC, rendered evidence + links, Approve / Send-back+feedback |
| **Monitor** (in_progress) | Who's running what, is it alive | Compact: claimed_by (RC/FC), started, lease/heartbeat freshness, cancel |
| **Triage** (open/blocked) | What's next, what's stuck | List: position #, priority, readiness (ready/blocked + missing prereq), deal, +new |
| **History** (done) | Audit last N | Collapsed list: outcome + evidence |

## 4. Recommendation — status tabs, verdict-first (not one bulk list, not a kanban board)

Replace the single stack with a tabbed Agents section:

- **Tab bar = the count strip** already at the top:
  `Needs verdict (n) · Running (n) · Queue (n) · Done`.
- **Default tab** = *Needs verdict* when n>0, else *Queue*. (You land on the action.)
- **Lane filter** (segmented): `Mine · All`, default **Mine** (your own lane via the
  token/owner). RC/FC badge on every card so All stays legible.
- **Per tab:**
  - **Needs verdict** — full-width review cards: title, deal, AC, **rendered evidence**
    (one-line summary + clickable artifact / task / deal links per §4a), **Approve** →
    done, **Send back** → feedback modal → re-queue. This is the surface you live in.
  - **Running** — card per claimed task: claimed_by (RC/FC agent), started, lease
    expiry / heartbeat age (stale-warning if the heartbeat is old), cancel/reclaim.
  - **Queue** — ordered list: position #, priority, readiness (ready / blocked +
    which prereq), deal, deadline; inline "+ new agent task".
  - **Done** — recent N with outcome + collapsible evidence.

**Why tabs, not a kanban board:** the review action needs *width* — rendered evidence,
links, and a feedback box don't fit a narrow board column. Tabs give the verdict queue
full-width review ergonomics and keep each mode focused; the count badges preserve
at-a-glance awareness. A board optimises *spatial overview* at the cost of review
comfort — available as a variant if you'd rather watch flow than review fast.

**Why not keep one bulk list:** it can't make the verdict queue both prominent *and*
spacious once running/queued items pile up; the modes have genuinely different layouts.

## 5. Data / API touchpoints

The browser reads `/api/state` (already includes agent tasks with status, evidence,
`claimed_by`, `claim_expires_at`, owner/created_by). So most of this is a **frontend
restructure**. Backend deltas, by phase:

- **Structured evidence** (original M2): agent posts evidence as
  `{summary, links:[{label, href}]}` (or markdown the card renders). Today it's free
  text → at minimum render it as markdown + autolink. Best: a light schema the
  `/repuro:run` skill fills.
- **Running freshness:** expose heartbeat age (have `claim_expires_at`; add
  `last_heartbeat_at` or derive) so a stalled agent is visible.
- Lane/owner + Mine/All: already supported.

## 6. Phasing (ship value early, low risk)

- **Phase 1 — UI only, no backend:** tabs + Mine/All filter + verdict-first default +
  RC/FC badges + render evidence as markdown/links. Biggest UX win, zero API risk.
- **Phase 2 — small backend:** structured-evidence schema; Running heartbeat freshness;
  inline "+ new agent task".
- **Phase 3:** per-lane continuous-loop status; SSE live-refresh polish for the watch model.

## 7. Open questions for Roman

1. **Tabs vs kanban board** — confirm tabs (review ergonomics) over board (overview)?
2. **Default lane** — Mine or All?
3. **Create agent tasks from this view**, or keep creation in the normal task flow?
4. **Evidence** — enforce structured (summary + links), or keep free markdown the card autolinks?
5. **Scope now** — build Phase 1 only, or 1+2 together?
