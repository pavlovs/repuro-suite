# Repuro Suite — Issues & Requests

Drop issues here. Format: `- [ ] description`.
Claude reads this when `/suite-fix` is invoked.

**Bugs & improvements** → implemented directly.
**Feature requests** → reviewed with Roman first, only built after approval.

---
## Bugs // Improvements

- [x] The numbering is neither the same font nor the same size nor the same color, neither in Workstreams nor timeline — fixed 2026-06-19
- [x] Fix the Formatting issues that exist in Workstreams and timeline (empty box under due, + button, due date alignment) — fixed 2026-06-19
- [x] One should see where 1. the deliverable is being dragged to (like with tasks) — fixed 2026-06-19
- [x] Somehow, not shown "done tasks" are still being counted wrongly — fixed 2026-06-19
- [x] Dealroom: Valuation & Financials does not show the correct details of the adjustments (commentary and positions adjusted) — fixed 2026-06-19
- [x] Dropdown list of "deliverbles" on a task still shows deals as spaces and then deals as todos under pipeline — fixed 2026-06-21 (grouped by SPACES not WORKSTREAMS; task-drawer.jsx + quick-add.jsx)
- [ ] Is the latest version live on /cockpit a regression? It shows again: Daily Weekly with 3 badges on top "need attention / deal deadline / completed " that nobody asked for — fixed 2026-06-21 (removed 3 mtg-stat badges from view-week.jsx; toggle kept)
- [x] Cockpit error: Uncaught TypeError: id.startsWith is not a function (react-dom.production.min.js:63) — fixed 2026-06-22 (QuickAdd onClose got a React event from the scrim onClick; added `typeof id === "string"` guard in app.jsx:234). Deploy pending.
- [ ] REMOVE the badges from the Daily Weekly again!! The completed, need attention, deal deadlines is so stupid
- [ ] Deliverable Drop Down Menu: Still shows the deals in a double format (very annoying)
- [ ] update of the updates local MOUSE onepager into the online dealroom
- [ ] Add a personal todo list (only seen by the one who logged in: roman just sees his personal with his crednetials, Flo just sees his)
- [ ] Deliverable can have an earlier deadline that the tasks beneath it. There should either be a warning on the task beneath the deliverable or some other way to showcase this
- [ ] WEEKLY Meeting: Only show the deliverables, if they are relevant subtasks due in the coming 7 days
- [ ] Blockers / Decision seems a very useless view currently, it is just a stack of 100 todos 
- [ ] Filter: Should be in the top row next to ACTIVITY
- [ ] EDIT and ADD button should be next ot the text on the deliverable (like with the EQUITY PARTNER space) - why is it now on the right?



Infrastructure — deferred (architecture change)
- [ ] DEFER - entrypoint.sh sed-injection of COCKPIT_BASE_PATH is fragile (breaks if source strings change or path has special chars). Replace with a /config.js endpoint in FastAPI that returns `window.COCKPIT_BASE="/cockpit"`, loaded via script tag. HTML files become immutable

---
## Feature Requests
> These are NOT auto-implemented. `/suite-fix` presents each one with a recommendation and waits for Roman's go/no-go.

- [ ] SPEC: User should be part of a team (e. g. Roman / Flo = Founder). Teams only see specific spaces and dont have access to other spaces. Also Meetings should then show the daily todo list of every member of that team
- [ ] SPEC: Integration of office calender + granola endpoint to have something like meeting prep in the window
- [ ] SPEC: Add and integrate the hubspot database (which we downloaded once) into the workflow
- [ ] SPEC: Architecture between contact/hubspot database + DEALROOM + ALLEX 
- [ ] SPEC: AGENT Integration and handover in claude cli thorugh /skill or similar (see next DEFER point) — SPEC WRITTEN 2026-06-22: cockpit/ai/SPEC-agent-skills-repo.md (awaiting Roman's 4 decisions)
- [ ] DEFER - Agents: "- **Start a session:** Open Claude Code in the `CLAUDE_REPURO` workspace and run `/rep-loop` (or some other command that makes sense). Claude picks up queued tasks in order, executes them, and reports results." --> Flo or other uses will not have this skill. Should we provide a build a custom github repo or something similar with cockpit skills required to use it. — covered by SPEC-agent-skills-repo.md (private repo + install script)
- [ ] DEFER — Integration of calender with most important meetings of the week (ignoring daily standup in the morning) for Flo and Roman
- [ ] DEFER — Migrate ALLEX and DEALROOM HTTP layer to FastAPI — both use stdlib http.server with manual URL parsing, JSON serialization, auth (~300 lines of boilerplate each). FastAPI gives typed parsing, automatic 422 on bad input, OpenAPI docs. Split dashboard.py into data/routes/html during migration. Effort: L (2-3 days per app)

---
## Resolved

