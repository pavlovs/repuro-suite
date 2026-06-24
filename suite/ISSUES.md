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
- [ ] Cockpit Workstreams: "Blocked By" (the tasks that must finish first) should only unravel when you hover over the respective task
- [ ] UX: sections in Cockpit still not unified — whitespace between the side-drawer and section content differs (Workstreams starts flush, Weekly Meeting sits further right, etc.). Part of the CSS-unification FR below.
- [ ] Dealroom resolves to 502

---
## Open — architecture / from Codex deep review (needs Roman or deferred)
> Full detail: `suite/ai/codex-reviews/2026-06-23-1758-architecture.md` + `…-frontend.md`

- [ ] [ARCH][high] DEALRoom: child tables keyed by free-text `domain` strand rows on rename — read-only check found REAL orphans in `deal_documents/deal_valuations/deal_questions` (domains `wolf`, `cat`, `blackbird`; Mouse→Everto clean). Migration SQL drafted, NOT executed — **approve cleanup?** (`dealroom/src/db.py`)
- [ ] [ARCH][medium] DEALRoom: wrong DB path silently creates+seeds a fresh DB — one-line fail-closed guard assessed safe, not implemented — **approve?** (`dealroom/src/db.py:1342`)
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
