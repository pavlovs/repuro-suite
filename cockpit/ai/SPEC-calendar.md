# SPEC — Calendar module v1 (2026-07-09)

## Goal
Team calendar visibility in cockpit, tied to teams: each user connects their own calendar; any user sees **Me** or **Team** (everyone sharing an active team with them — for Roman: the `md` team → RD+FF). Two surfaces: a new sidebar view **Calendar** and a 4th right-column tab **Calendar** in the Meeting view (Tomorrow / Personal / Blocked / Calendar).

## Architecture decision — MS Graph application auth (not per-user ICS)
- **Dedicated** Azure app registration "Repuro Cockpit Calendar" with application permission `Calendars.Read` + admin consent (Roman, one-time, ~5 min). Deliberately NOT the existing mail app — the cockpit server must never hold mail scopes.
- Env: `COCKPIT_GRAPH_TENANT`, `COCKPIT_GRAPH_CLIENT_ID`, `COCKPIT_GRAPH_CLIENT_SECRET`. Local: shell env / .env at dev start. Prod: `fly secrets set`. **Secrets never in repo.**
- Probe 2026-07-09: existing mail app token roles = `Mail.Read, Mail.ReadWrite`; `calendarView` → 403 for both roman@kamukapital.de and roman.dobriakov@repuro.de. So an admin-consent step is unavoidable on any Graph path.
- Rejected: per-user published ICS URLs — manual per-user publish (possibly disabled by tenant policy), hours of refresh lag, secret URLs at rest in cockpit.db, RRULE-expansion dependency. The normalize layer keeps a provider seam so an ICS adapter can be added later for non-tenant users (advisors, Google).
- **Opt-in privacy model**: a user appears in team scope only after they connected their own UPN. Events flagged private are masked for teammates (subject "Private", no location/link); own private events render fully. No event content is ever persisted in cockpit.db (real-names rule) — in-memory TTL cache only.

## Backend
1. **Migration 14** (`src/db.py`): `ALTER TABLE users ADD COLUMN calendar_upn TEXT` (NULL = not connected).
2. **New `src/calendar_graph.py`** (~180 lines):
   - Client-credentials token with expiry-aware in-process cache.
   - `fetch_events(upns, start_iso, end_iso)` → httpx GET `/v1.0/users/{upn}/calendarView?startDateTime=..&endDateTime=..&$select=subject,start,end,location,showAs,sensitivity,isAllDay,onlineMeeting,organizer&$orderby=start/dateTime&$top=50`, header `Prefer: outlook.timezone="W. Europe Standard Time"`.
   - Normalized event: `{upn, subject, start, end, all_day, location, show_as, private, online_url}`.
   - In-memory TTL cache 300 s keyed (upn, range). No DB writes.
   - `probe_upn(upn)` → (ok, reason) for the connect flow. Distinguish: `not_configured` (env missing), `consent_missing` (403), `unknown_upn` (404), `ok`.
   - **FAKE mode** `COCKPIT_CALENDAR_FAKE=1`: deterministic demo events (rd + ff, today..+6d, incl. one private + one all-day) so local dev/e2e work before admin consent exists. Probe always ok in fake mode.
3. **`src/api.py`**:
   - `GET /api/calendar/events?scope=me|team&start=YYYY-MM-DD&days=7` — human principal with `calendar` module. `me` → own UPN; `team` → self + users sharing ≥1 active team, only those with `calendar_upn` set. Response `{status, users:[{id,name,initials,connected}], events:[{user:{id,name,initials}, subject, start, end, all_day, location, private, online_url, show_as}]}` sorted by start. Privacy masking for non-self private events. `status`: ok | not_configured | consent_missing.
   - `POST /api/calendar/connect {upn}` — self-service: validate via `probe_upn`, save own `users.calendar_upn` + audit entry. Empty/null upn = disconnect. Returns `{status}` for inline UI feedback.
   - Add `"calendar"` to `_ALL_COCKPIT_MODS` (admins get it automatically; advisor/viewer only if granted).
4. Agents (`role=agent`) never get the module (modules=["agents"]) — no change needed, but the endpoint must still human-gate.

## Frontend
1. `boot.js`: add `view-calendar.jsx` to `JSX_FILES`; add `"calendar"` to the modules fallback list (line ~716).
2. `app.jsx`: NAV_ALL entry `{id:"calendar", module:"calendar", label:"Calendar", icon:"calendar", crumb:"Your and your team's meetings"}` after `week`; extend TAB_TO_HASH/HASH_TO_TAB with `#calendar`.
3. `components.jsx`: new `calendar` Icon glyph (distinct from `week`).
4. **New `static/js/view-calendar.jsx`**:
   - Toolbar: seg **Me | Team** + week nav (‹ Today ›) + user legend chips (initials avatar per connected user) in team scope.
   - Week grid: 7 day-columns Mon–Sun, header = weekday + date (today highlighted), events stacked chronologically as cards (time range, subject, owner avatar in team scope, location / online-meeting icon). All-day events pinned at column top. Masked private events show a lock + "Private".
   - Not connected → **connect card**: short guide ("enter your Kamu/Repuro work email — the cockpit reads your calendar via the company Microsoft account; you appear in Team view only after connecting") + input + validate on submit, inline error on 404.
   - `consent_missing` + isAdmin → setup card with the Azure steps (see guide below). Non-admin: "Calendar backend not enabled yet — ping Roman."
   - Styling: reuse existing css vars + card/seg/wk patterns; new classes in `cockpit-views.css`. NO inline style inventions.
5. `view-week.jsx`: 4th right-column seg option `["calendar","Calendar",n]` → compact agenda (scope=team, today + tomorrow, grouped day headers, rows: time · subject · initials avatar). Lazy fetch on first tab select, kept in component state.
6. **Cache-bump** (`index.html`): `boot.js?v=17`, `cockpit-views.css?v=9`.

## Admin one-time setup guide (also → ai/CALENDAR-SETUP.md)
portal.azure.com → Microsoft Entra ID → App registrations → New registration "Repuro Cockpit Calendar" (single tenant, no redirect URI) → API permissions → Add → Microsoft Graph → **Application permissions** → `Calendars.Read` → **Grant admin consent** → Certificates & secrets → New client secret (24 mo) → then:
`fly secrets set COCKPIT_GRAPH_TENANT=kamucapital.onmicrosoft.com COCKPIT_GRAPH_CLIENT_ID=<app id> COCKPIT_GRAPH_CLIENT_SECRET=<secret> -a repuro-suite`
Optional hardening later: Exchange ApplicationAccessPolicy restricting the app to MD mailboxes.

## Tests (`tests/test_calendar.py`)
Monkeypatch `calendar_graph.fetch_events`/`probe_upn` — no live Graph in tests. Cover: connect validate+save+disconnect, events scope=me vs team (team-membership math incl. user without UPN excluded), private masking for non-self, module gating (teamless viewer → no access), not_configured/consent_missing statuses, agent principal → 403.

## Non-goals v1
No event create/edit, no free-slot search, no ICS adapter (seam only), no Google/external tenants, no per-user busy-only mode (whole-team full detail, private-flag masking only).

## Build addendum (2026-07-09, post-verification)
- The "Meeting view right column" from §Frontend.5 actually lives in `WeekView` (view-week.jsx), which the **Cockpit overview** embeds — so the Calendar tab appears on the Cockpit tab's right column, matching Roman's original wording. The Meeting tab (MeetingView) is a separate daily/weekly layout and was not touched.
- JSX views must NOT call `authedFetch` (closure-private in boot.js — referencing it from the bundle throws and unmounts the app). The sanctioned seam is `window.api.calendarEvents(scope, startIso, days)` / `api.calendarConnect(upn)`.
- Masking is server-side only (`is_self` aware); the client renders `ev.subject` as delivered. `private` flag drives styling only.
- Hardening: UPN regex (`calendar_graph.UPN_RE`) enforced on connect + URL-quoted in every Graph path; `days` clamped 1..31; invalid `start` → 422; events endpoint probes on empty result so `consent_missing` surfaces post-deploy.
- FAKE mode assigns demo profiles by upn char-sum so me/team scopes stay consistent for the same user.

## Verification gate (before "done")
Babel-compile full JSX bundle → pytest → restart :8099 with `COCKPIT_CALENDAR_FAKE=1` → e2e screenshots → READ screenshots as a fresh user → fix → repeat until a round is clean. Live Graph path is **not verifiable** until admin consent — state this explicitly at handoff.
