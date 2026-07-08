# Repuro Suite — Issues & Requests

Drop issues here. Format: `- [ ] description`.
Claude reads this when `/suite-fix` is invoked.

**Bugs & improvements** → implemented directly.
**Feature requests** → reviewed with Roman first, only built after approval.

> Deployed fixes are removed from this file on each `/suite-fix` run (git history keeps the record). Only OPEN items remain below.

---
## Bugs // Improvements (open)

*(none — all clear as of 2026-07-08)*



---
## Open — architecture / from Codex deep review (needs Roman or deferred)
> Full detail: `suite/ai/codex-reviews/2026-06-23-1758-architecture.md` + `…-frontend.md`

- [ ] [ARCH][high] DEALRoom: child tables keyed by free-text `domain` strand rows on rename — read-only check found REAL orphans in `deal_documents/deal_valuations/deal_questions` (domains `wolf`, `cat`, `blackbird`; Mouse→Everto clean). Migration SQL drafted, NOT executed — **approve cleanup?** (`dealroom/src/db.py`)
- [x] [ARCH][medium] DEALRoom: wrong DB path silently creates+seeds a fresh DB — wired `DEALROOM_REQUIRE_DB=1` in fly.toml 2026-06-26
- [x] [ARCH][medium] Suite: `investor.db` omitted from Litestream — fixed 2026-07-07 (v2.1.22): investor.db added to litestream.yml + entrypoint restore-on-empty guard for all four DBs
- [ ] [ARCH][low] / Infra (deferred — architecture change): `entrypoint.sh` boot-time `sed` injection of `COCKPIT_BASE_PATH` is fragile. Replace with a `/config.js` endpoint that returns `window.COCKPIT_BASE="/cockpit"` so HTML files become immutable. (`suite/entrypoint.sh`)
- [ ] [UX][low] ALLEX: blocking `alert()` fallbacks — no toast system exists; would need a new feedback primitive (`lead-pipeline/src/pipeline/templates/dashboard.html`)

---
## Feature Requests
> NOT auto-implemented. `/suite-fix` presents each with a recommendation and waits for Roman's go/no-go.

- [ ] Unify CSS to repuro-ci — same headers, hero stages, fonts, H1/H2/H3 across all suite modules (the big standardization pass; covers the section-whitespace bug above)
- [x] SPEC: Users belong to a team — SHIPPED 2026-07-07 (v2.1.23/24, `cockpit/ai/SPEC-teams.md` v2): teams carry per-module rw/ro, strongest wins, workstream-team scoping, Admin view. OPEN REMAINDER: "Meetings show the daily todo list of every team member" — per-member meeting rollup not designed yet (flagged to Roman 07-07, needs his input on what a team meeting view shows)
- [ ] SPEC: Integrate office calendar + Granola endpoint for meeting prep in-window
- [ ] SPEC: Add + integrate the HubSpot database (already downloaded once) into the workflow
- [ ] SPEC: Architecture between contact/HubSpot DB + DEALROOM + ALLEX
- [ ] SPEC: Agent integration + handover in Claude CLI via /skill or similar — SPEC written 2026-06-22: `cockpit/ai/SPEC-agent-skills-repo.md` (awaiting Roman's 4 decisions)
- [ ] DEFER: Calendar integration — most important meetings of the week (ignoring the morning daily standup) for Flo and Roman
- [ ] DEFER: Migrate ALLEX + DEALROOM HTTP layer to FastAPI (each ~300 lines of stdlib http.server boilerplate). Effort: L (2–3 days per app)

---
## Resolved
Deployed fixes are pruned on each `/suite-fix` run. See git history of this file for the full log.

- [x] MOUSE onepager into online Dealroom — pushed 2026-07-08 via flyctl SSH (onepager fields + 16 commercial + 40 customer rows + 19 missing financials; prod-only rows preserved; prod DB backed up first). Verified rendering live on /deals/?deal=Mouse. NOTE: flyctl SSH was never broken — the trailing "handle is invalid" is a cosmetic Windows console teardown error AFTER successful output.

Cockpit fix batch — fixed + deployed + click-verified live 2026-07-08 (v2.1.25):

- [x] +1D does nothing — TWO root causes: (1) `addDays()` used `toISOString()` (UTC): in Berlin the +1 day collapsed back to the same date, a deterministic no-op; (2) stale-version 409 after reorders reverted the bump silently — quick actions now retry once with the server's current version (`detail.current.version`, wire shape verified live). Editor saves keep conflict semantics (no blind retry — would clobber Flo/agent edits; Codex HIGH finding).
- [x] Sorting of tasks does not stick — optimistic sortOrder stamping + rerender, rollback on failed PATCH, sortOrder sorts in Table view + deliverable drawer; reorder-persistence pytest added. Verified live: reorder round-trip persisted server-side.
- [x] AGENT tasks in daily meeting / should only be in Cockpit when feedback needed — Meeting + My Week exclude `execution=agent` everywhere (lists, deadline bars, completed-since-Monday, due-today/next-10-days pickers); agent work needing Roman surfaces ONLY in "Agents — waiting on you".
- [x] Agent Queue respec — now "Agents — waiting on you": in_review (Needs review) + blocked (Waiting on your answer), up to 5; Agents nav badge counts both.
- [x] Meeting: earlier dates on top — date-ascending sort in all Meeting/Week lists (verified live: RD + FF daily lists ascending).
- [x] Done/old deliverables lingering ("DD Kick-off" Mantis) — deliverables with status done/dropped OR all tasks done are hidden in Timeline and greyed (`.deliv.done`) but findable in Table view for archiving. Verified live on DD kickoff (d-33).
