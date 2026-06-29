# Repuro Suite — Issues & Requests

Drop issues here. Format: `- [ ] description`.
Claude reads this when `/suite-fix` is invoked.

**Bugs & improvements** → implemented directly.
**Feature requests** → reviewed with Roman first, only built after approval.

> Deployed fixes are removed from this file on each `/suite-fix` run (git history keeps the record). Only OPEN items remain below.

---
## Bugs // Improvements (open)

- [ ] Dealroom onepager MOUSE: add the content — still not in (content/data sync, Roman handling separately)
- [ ] Update the local MOUSE onepager into the online Dealroom (content/data sync)
- [x] UX: sections in Cockpit still not unified — fixed 2026-06-26. Meeting view now uses `view-wide` (no max-width centering), content left-edge matches Workstreams/Timeline
- [x] [UX decision] Cockpit Board view: hover-gated prereqs — fixed 2026-06-26. `.tcard-need` hidden by default, revealed on card hover (matches Workstreams table pattern)
- [ ] AGents: How to setup & run is hidden beneath, same as recently updated. if there is a long queue, those section are difficult to see. Maybe separate Agents into Agents Workflow and Agents Review and have its own section? Something like this?
- [x] When you add a task make the deliverable only show the workstreams and then when you click on the wokrstream show the deliverables underneath — fixed 2026-06-26. Custom two-level picker: workstreams → click to expand → deliverables
- [x] Instead of Weekly Meeting call it Meeting — fixed 2026-06-26. NAV + palette updated

---
## Open — architecture / from Codex deep review (needs Roman or deferred)
> Full detail: `suite/ai/codex-reviews/2026-06-23-1758-architecture.md` + `…-frontend.md`

- [ ] [ARCH][high] DEALRoom: child tables keyed by free-text `domain` strand rows on rename — read-only check found REAL orphans in `deal_documents/deal_valuations/deal_questions` (domains `wolf`, `cat`, `blackbird`; Mouse→Everto clean). Migration SQL drafted, NOT executed — **approve cleanup?** (`dealroom/src/db.py`)
- [x] [ARCH][medium] DEALRoom: wrong DB path silently creates+seeds a fresh DB — wired `DEALROOM_REQUIRE_DB=1` in fly.toml 2026-06-26
- [ ] [ARCH][medium] Suite: `investor.db` started by supervisord but omitted from Litestream — moot until the investor/boardroom module ships to prod; decide when provisioning Strada access (`suite/litestream.yml`)
- [ ] [ARCH][low] / Infra (deferred — architecture change): `entrypoint.sh` boot-time `sed` injection of `COCKPIT_BASE_PATH` is fragile. Replace with a `/config.js` endpoint that returns `window.COCKPIT_BASE="/cockpit"` so HTML files become immutable. (`suite/entrypoint.sh`)
- [ ] [UX][low] ALLEX: blocking `alert()` fallbacks — no toast system exists; would need a new feedback primitive (`lead-pipeline/src/pipeline/templates/dashboard.html`)

---
## Feature Requests
> NOT auto-implemented. `/suite-fix` presents each with a recommendation and waits for Roman's go/no-go.

- [ ] Unify CSS to repuro-ci — same headers, hero stages, fonts, H1/H2/H3 across all suite modules (the big standardization pass; covers the section-whitespace bug above)
- [ ] SPEC: Users belong to a team (e.g. Roman / Flo = Founder). Teams see only their spaces; Meetings show the daily todo list of every team member
- [ ] SPEC: Integrate office calendar + Granola endpoint for meeting prep in-window
- [ ] SPEC: Add + integrate the HubSpot database (already downloaded once) into the workflow
- [ ] SPEC: Architecture between contact/HubSpot DB + DEALROOM + ALLEX
- [ ] SPEC: Agent integration + handover in Claude CLI via /skill or similar — SPEC written 2026-06-22: `cockpit/ai/SPEC-agent-skills-repo.md` (awaiting Roman's 4 decisions)
- [ ] DEFER: Calendar integration — most important meetings of the week (ignoring the morning daily standup) for Flo and Roman
- [ ] DEFER: Migrate ALLEX + DEALROOM HTTP layer to FastAPI (each ~300 lines of stdlib http.server boilerplate). Effort: L (2–3 days per app)

---
## Resolved
Deployed fixes are pruned on each `/suite-fix` run. See git history of this file for the full log.

- [x] Dealroom resolves to 502 — fixed 2026-06-24 (missing `import threading` in `dealroom/src/dashboard.py`; backend was crash-looping on `NameError`. Verified live: `localhost:8082 -> 200` post-deploy). a4f1815
- [x] Cockpit Workstreams "Blocked By" reveals only on hover — fixed 2026-06-24 (`TRow` wrapped in `.trow-hovergroup`; prereq rows `display:none` until parent task hovered; per-row separators preserved). a4f1815
- [x] +1d slow/broken — fixed 2026-06-26. Added `api.bumpDue` fast path: parses PATCH response, updates version in-place, fires `refreshFromServer` in background. Rapid clicks now work.
- [x] Dead `view-relations.jsx` removed — 2026-06-26 (10.6KB, not in JSX_FILES, CSS already cleaned in prior session)
- [x] DEALROOM_REQUIRE_DB wired in fly.toml — 2026-06-26 (env guard was implemented but inert; now active in prod)
- [x] Cockpit blank white page (all modules) — fixed 2026-06-29. Vendor scripts (React/ReactDOM/Babel) had no cache-bust params; browser cached broken responses from prior cold starts. Added `?v=1` to vendor tags, bumped boot.js to `?v=5`, added `NoCacheStaticMiddleware` setting `Cache-Control: no-cache` on `/static/`. 4e68197
