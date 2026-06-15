# Repuro Suite — Issues & Requests

Drop issues here. Format: `- [ ] description`.
Claude reads this when `/suite-fix` is invoked.

**Bugs & improvements** → implemented directly.
**Feature requests** → reviewed with Roman first, only built after approval.

---
## Bugs // Improvements

Cockpit-Bugs — UX / architecture (needs Roman's input)
- [ ] New Deal wiring: Cockpit “New Deal” should create in Dealroom (cross-app API). Deferred — needs infrastructure investigation next session

Infrastructure — deferred (architecture change)
- [ ] entrypoint.sh sed-injection of COCKPIT_BASE_PATH is fragile (breaks if source strings change or path has special chars). Replace with a /config.js endpoint in FastAPI that returns `window.COCKPIT_BASE="/cockpit"`, loaded via script tag. HTML files become immutable

---
## Feature Requests
> These are NOT auto-implemented. `/suite-fix` presents each one with a recommendation and waits for Roman's go/no-go.

- [ ] Make the suite function, feel and work like a shipped and developed suite. Right now it feels and looks half-baked. Top bar naigation in Dealroom shows LIVE DE (which are unncessary and old). There is blue green yellow, there is the date in the different font on top. ON ALLEX the logo is on the bottom and only by chance i found that clicking the logo gets me back (Cockpit and dealroom are nested somewhere else). Cockpit looks different again. Dealroom looks weird. Let the agent go section by section independently and not try to fix everything at once (reset context after every fix). NOTE: On dev only, the live version is currently getting
- [ ] Integration of calender with most important meetings of the week (ignoring daily standup in the morning) for Flo and Roman
- [ ] Migrate ALLEX and DEALROOM HTTP layer to FastAPI — both use stdlib http.server with manual URL parsing, JSON serialization, auth (~300 lines of boilerplate each). FastAPI gives typed parsing, automatic 422 on bad input, OpenAPI docs. Split dashboard.py into data/routes/html during migration. Effort: L (2-3 days per app)
- [ ] Replace fetch() interceptor with relative URLs — both ALLEX and DEALROOM monkey-patch window.fetch to prepend BASE_PATH. Use relative URLs instead (fetch('api/data') not fetch('/api/data')). Browser resolves against current page URL which already includes the sub-path. Eliminates monkey-patch entirely. Effort: S (needs thorough testing)

---
## Resolved

- [x] Workstreams collapse/expand all — added wsOpen state, toggleAll button in header, chevron + click on ws-band, conditional body render — fixed 2026-06-15
- [x] "Open Dealroom" in Cockpit links to suite dealroom — set `window.DEALROOM_URL='/deals/'` in config script — fixed 2026-06-15
- [x] Cockpit prompt()/alert() replaced — built toast (`showToast`) + modal (`showModal`) system in boot.js + cockpit-extras.css; replaced all 9 alert() in boot.js, 4 in quick-add, prompt() in task-drawer/view-board/view-agents/view-table/view-week with async showModal — fixed 2026-06-15
- [x] Cockpit cold start blank screen — added CSS-only spinner inside #root div, React.render replaces it on boot — fixed 2026-06-15
- [x] Cockpit CDN → local vendor — downloaded React 18.3.1, ReactDOM 18.3.1, Babel 7.29.0 to /cockpit/static/vendor/, updated script tags — fixed 2026-06-15
- [x] Suite nav "return to Suite" — added `<a href="/">Suite</a>` home link to ALLEX, Dealroom, and Cockpit nav bars — fixed 2026-06-15
- [x] Landing page hardcoded name — added `/api/whoami` Caddy endpoint returning auth username as JSON, JS maps to display name/initials — fixed 2026-06-15
- [x] Health check — added `/healthz` unauthenticated handler in Caddyfile + `[[http_service.checks]]` in fly.toml — fixed 2026-06-15
- [x] Container runs as root — added appuser in Dockerfile, chown /data in entrypoint.sh, user=appuser in supervisord — fixed 2026-06-15
- [x] Supervisord start order — set priorities (allex=100, dealroom=200, cockpit=300, caddy=999), startsecs, startretries — fixed 2026-06-15
- [x] SQLite WAL conditional — both cockpit and dealroom db.py check FLY_APP_NAME, use WAL on Fly.io, DELETE locally — fixed 2026-06-15
- [x] busy_timeout — added 5000ms to dealroom and cockpit get_conn() — fixed 2026-06-15
- [x] Dealroom read-only ATTACH — uses URI mode=ro on Linux (os.name != "nt") — fixed 2026-06-15
- [x] Dealroom migration singleton — singleton connection + PRAGMA user_version to skip applied migrations — fixed 2026-06-15
- [x] Dealroom _read_json_body — returns None on parse failure, all 6 callers return 400 JSON error — fixed 2026-06-15
- [x] ALLEX alert() → showToast() — replaced all 11 alert() calls with showToast — fixed 2026-06-15
- [x] Error response consistency — added `_json_error()` helper to ALLEX, replaced all send_error calls; Dealroom's 2 remaining bare send_response calls converted to _json_response; no more str(exc) leaked to client — fixed 2026-06-15
- [x] Remove Cockpit classic.html — deleted classic.html, removed route from api.py, removed test assertion — fixed 2026-06-15
- [x] Consolidate CSS color tokens — canonical --rs-brand tokens in shared.css, cockpit.css aliases via var() fallback — fixed 2026-06-15
- [x] Litestream backup for 3 SQLite DBs — installed in Dockerfile, litestream.yml for 3 DBs, entrypoint.sh wraps supervisord when LITESTREAM_REPLICA_URL set. Needs bucket secrets on Fly to activate — fixed 2026-06-15
- [x] Unified QuickAdd — single modal with Task/Deliverable type toggle, prefill from context (workstream, type). Replaced separate creation flows — fixed 2026-06-15
- [x] My Week deliverable-centric workflow — grouped by workstream→deliverable with edit, progress bar, inline +task, editable focus section — fixed 2026-06-15
- [x] Split requirements.txt into prod/dev — created requirements-prod.txt for all 3 apps, Dockerfile installs only prod deps. Drops ~100-150MB from image — fixed 2026-06-15
- [x] Visual density / separation — increased ws-group margin + border separator, deliverable block spacing, row height padding. Text less cramped — fixed 2026-06-15
- [x] Fox DD / pipeline ownership — deliverables now editable via ✎ button (rename, set target). Content ownership is a data fix, not a UI bug — fixed 2026-06-15
- [x] Smart quote compilation error — replaced Unicode curly quotes in boot.js/view-table.jsx/view-agents.jsx with straight quotes. Babel compiles clean — fixed 2026-06-15

