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


- [ ] AGents: How to setup & run is hidden beneath, same as recently updated. if there is a long queue, those section are difficult to see. Maybe separate Agents into Agents Workflow and Agents Review and have its own section? Something like this? *(flagged 2026-07-06: UX restructure — Claude recommends splitting the Agents view into "Queue & Review" [default] and "Setup & Playbook" [collapsed second section]; needs Roman's go before building)*


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

- [x] Login loop on all modules ("stuck at auth", roman locked out since 05.07 deploy) — fixed 2026-07-06 (v2.1.17). Root cause: floating `caddy:2-alpine` tag pulled Caddy 2.11.4 in the 05.07 image build; 2.11.4 no longer injects `header_up X-Remote-User {http.auth.user.id}` after basic_auth (placeholder resolves in `respond` but not in reverse_proxy upstream headers) → backends saw authed users as anonymous. Diagnosed live with a temporary debug basic-auth user; @needsAuth matcher and route-based config variants ruled out (version-bound, not config-bound). Fix: pin `caddy:2.10-alpine` in suite/Dockerfile.
- [x] Investor portfolio table Lion/Wolf EV+multiple stale vs latest models — fixed 2026-07-06: Lion 4.8/5.9x → 3.7/5.6x (Golmed v15, 26.06), Wolf 5.2/5.1x → 4.3/5.4x (KVG v5, 12.06); matches dealroom.db overrides synced 05.07 (handoff item the v16 port session skipped).

All Investor Mode items — fixed 2026-07-06 by applying the pending `boardroom/review/proposal-fresh-v16.html` through `boardroom/templates/` (reverse-split, byte-verified) + deploying the template split (92f0bba) and scorecard re-source (8251375) that were committed but never shipped:

- [x] LOI Scorecard comparison: "Total Score (out of 40)" row label, score column plain numbers — fixed 2026-07-06 (v16)
- [x] Comment below comparison: Score/Multiple = value-for-money explainer — fixed 2026-07-06 (v16)
- [x] Sources & Uses readability: more cell padding (9px/16px), kept K€; "—" = n/a vs 0 = true zero — fixed 2026-07-06 (v16)
- [x] Customer Interviews provider → TBD — fixed 2026-07-06 (v16)
- [x] Structuring/Tax KG → Ebner Stolz only (YPOG removed) — fixed 2026-07-06 (v16)
- [x] Operating cash flow: side table (eo-panel) right of S&U instead of prose comment — fixed 2026-07-06 (v16)
- [x] "Preliminary" note below all S&U views — fixed 2026-07-06 (v16)
- [x] Mouse and Cat positions swapped (tabs, panels, all comparison columns) — fixed 2026-07-06 (v16 + `_PAGE_DEALS` order in boardroom/src/api.py)
- [x] Mouse + Cat S&U same layout as Fox/Mantis (su-layout grid, no stretch) — fixed 2026-07-06 (v16)
- [x] Individual scorecard formatting: horizontal category rows, no vertical labels — fixed 2026-07-06 (was committed 8251375, undeployed)
- [x] Fox scorecard 432k/12% invented values — re-sourced from in-doc P&Ls, all 4 deals cross-checked (Fox 0.36 M€/10.3%, Mantis 0.81, Mouse 0.65, Cat 0.93; CAGRs match deals.md) — fixed 2026-07-06 (was committed 8251375, undeployed)
- [x] Fox valuation earn-out table EVs inconsistent with EV 1,753 (963/1,463 → 1,253/1,753/1,903) — fixed 2026-07-06 (v16)
