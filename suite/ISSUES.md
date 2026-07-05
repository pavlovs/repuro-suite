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


- [ ] AGents: How to setup & run is hidden beneath, same as recently updated. if there is a long queue, those section are difficult to see. Maybe separate Agents into Agents Workflow and Agents Review and have its own section? Something like this?

Investor Mode
- [ ] LOI Scorecard comparison Add Total (out of 40) and in the score column just keep the number (29, 34, etc.). Also call it Total Score instead of Total only, so that one understands what the coefficient leads to. 
- [ ] Add comment below. Higher Score / Multiple equals more "value for money" acquisitoin - change as how you see fit
- [ ] I find Sources & Uses, espeically in the comparison hard to read, there is a lot of numbers - leave maybe morewhite space in between or change to illions instead of K€? What do you think is better? there is inconsistency between using "-" as 0 and 0 as 0.
- [ ] Custmer Interviews Provider is still WIP
- [ ] Structuring Tax KG is Ebner Stolz, YPOG is only our own 
- [ ] Operative Cash Flow: Maybe instead of a complex comment, add a small table on the right of sources and souces to show calculation and vailability of "operating cash flow"
- [ ] add that the sources & uses are preliminary as a comment below
- [ ] change position of mouse and cat
- [ ] Sources and Uses for Mouse and Cat should not be streatched out but have same format as Fox and Mantis
- [ ] Formatting of the individual scorecards looks bad, they are creating stupdi white space (e. g. value creation potential is only one category, no need to have 3/4 on the left in vertical writing which no one can read)
- [ ] FOX EBITDA is 0,36 - why is the scorecard saying 432k and eBITDA margin of 12% - this is invented - please make sure and check that the scorecard bvlaues are correct for the 4 companies, especially the historical growth as well. Fox shows 432k, Mantis shows 0,8 M€, inconsistent - fix this


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
- [x] Cockpit blank white page (all modules) — fixed 2026-06-29 (v76). Root causes across v71-v75: (1) Caddy crash from invalid Caddyfile syntax in /diag handler, (2) machine auto_stop with min=0 causing 503, (3) Cache-Control headers inside handle_path blocks (reverted v75). **Actual root cause of persistent blank pages (v75 still broken):** Caddy `handle /` is a catch-all prefix matcher that swallows ALL paths including `/cockpit`, `/allex`, `/deals` before their `handle /xxx { redir }` blocks fire. Fix: replaced `handle /xxx { redir }` with top-level `redir /xxx /xxx/ permanent` directives (run before handle blocks) + changed landing page links to use trailing slashes (`/cockpit/` not `/cockpit`).
