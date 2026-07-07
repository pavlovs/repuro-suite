# SPEC: Teams — per-module read/write permissions, suite-wide (v2)

**Status:** APPROVED — Roman resolved the open model questions 2026-07-07 (AskUserQuestion, this file supersedes v1)
**Depends on:** migration v12 (deployed 2026-07-07, suite v2.1.22)
**Goal:** Teams (MD, M&A, Marketing, HR, …) are the permission carrier. Each team holds a per-module read/write map. A user belongs to many teams; the strongest membership wins per module (rw > ro > none). Suite-wide: teams gate Dealroom/ALLEX at the Caddy layer, not just cockpit views.

## v1 → v2 decision log (Roman, 2026-07-07)

1. **Teams CARRY permissions** — they replace v12 profiles as the permission carrier. v1's "teams = visibility only, profiles = permissions" model is dead. `role_profiles`/`users.profile`/`workstreams.allowed_profiles` stay in the schema but go dormant (no drop-churn); the profile filter in `assemble_state` is REMOVED. Preset teams `advisor`/`viewer` replicate the old profile function.
2. **Suite-wide now** — `dealroom` and `allex` are modules; Caddy `forward_auth` → cockpit `/api/authz` enforces them (method-aware: ro allows GET/HEAD only). `/investor/` is EXCLUDED from forward_auth v1: the shared `investor` Caddy cred (Strada) is already confined by the Caddy `@investor_outside` block and must not be routed through cockpit's user table.
3. **Both scoping levels** — module permissions (which sections, read vs write) AND workstream-team assignment (which workstreams inside; unassigned = visible to all — opt-in, per v1 spec).

## Model

**Effective permission per module = max over the user's teams** (rw > ro > none).
`is_admin` team (MD) ⇒ implicit **rw on every module, present and future** (no enumeration to maintain — "MD gets ALL permissions") + access to admin endpoints.
`users.all_teams=1` ⇒ bypasses the workstream-team gate (god view over workstreams; RD).

Roman's example: MD = all permissions; HR = write `hr` module (future) only, nothing else — no dealroom; a user in {MD, HR} gets MD's rights (strongest wins).

Module ids: `overview, week, workstreams, timeline, agents, relations` (cockpit, = v12 ids) + `dealroom, allex` (suite, Caddy-enforced) + open-ended for future (`hr`, `investor`, …) — the JSON map accepts any id.

## Data model — migration v13 (all idempotent)

```sql
CREATE TABLE IF NOT EXISTS teams (
  id          TEXT PRIMARY KEY,          -- slug: 'md', 'mna', 'hr'
  name        TEXT NOT NULL,
  color       TEXT,
  permissions TEXT NOT NULL DEFAULT '{}',-- JSON {module_id: "rw"|"ro"}
  is_admin    INTEGER NOT NULL DEFAULT 0,-- 1 => implicit rw everywhere + admin API
  sort_order  INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived'))
);
CREATE TABLE IF NOT EXISTS team_members (
  team_id TEXT NOT NULL REFERENCES teams(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  PRIMARY KEY (team_id, user_id)
);
CREATE TABLE IF NOT EXISTS workstream_teams (
  workstream_id INTEGER NOT NULL REFERENCES workstreams(id),
  team_id       TEXT    NOT NULL REFERENCES teams(id),
  PRIMARY KEY (workstream_id, team_id)
);
-- users: + all_teams INTEGER NOT NULL DEFAULT 0; + login TEXT (Caddy basic-auth username)
```

**Seeds/backfill (behavior-preserving):**
- `md` ("Managing Directors", is_admin=1, permissions '{}' — implicit), members = all existing humans (rd, ff)
- `advisor` ({"workstreams":"ro","timeline":"ro"}), `viewer` ({"workstreams":"ro"}) — presets, no members
- `users.login`: rd→'roman', ff→'florian'; `users.all_teams`: rd→1
- NO workstream_teams rows (unassigned = visible to all ⇒ v13 is a no-op until Roman assigns)
- `mna`/`hr`/`marketing` are NOT seeded — Roman creates them via admin API/UI with the permissions he wants

## Backend (`src/api.py`)

1. **`principal()`**: resolve X-Remote-User via `users.login` (DB lookup replaces `_CADDY_USER_MAP`; keep the dict only as fallback for unmigrated rows). Attach `teams` (ids), `perms` ({module: "rw"|"ro"} effective), `is_admin`, `all_teams`. Keep `modules` (= keys of perms) and `read_only` (= no rw anywhere) for API-shape compat. Agents unchanged: `modules=["agents"]`, `perms={"agents":"rw"}`, `teams=[]`.
2. **Write guards**: `require_write(module)` dependency factory replaces the global `read_only_guard`. Mapping: task/workstream/deliverable CRUD + reorders → `workstreams`; approve/reject/request-changes/answer, learning decide, human upload-preview → `agents`; patch_deal → `dealroom` (it 422-refuses writes anyway). `is_admin` passes everything.
3. **`assemble_state()` team gate** (replaces the v12 profile gate; applies to ALL non-agent principals incl. admins unless `all_teams`):
   assigned = workstream's team ids; if assigned and no intersection with principal's teams and not all_teams → hidden. Deliverables/tasks cascade via nesting (as v12).
4. **`GET /api/authz?module=<id>`** for Caddy forward_auth. Reads X-Remote-User + X-Forwarded-Method. none→403; ro + write-method→403; else 200 (empty body). Unknown/absent login → 403. No Bearer path (agents never hit /deals|/allex).
5. **Admin endpoints** (guard: `is_admin` member, NOT the old profile=='owner'):
   - `POST /api/admin/user` {id,name,initials?,login?,teams?,all_teams?} → token once (v12 endpoint reworked: `teams` replaces `profile`)
   - `GET /api/admin/overview` → users (+teams, all_teams, login), teams (+permissions, members), workstream assignments — one payload for the admin UI
   - `POST /api/admin/team` {id,name,color?,permissions,is_admin?} / `PATCH /api/admin/team/{tid}` (name/color/permissions/status)
   - `POST /api/admin/team/{tid}/members` {user_id} / `DELETE /api/admin/team/{tid}/members/{uid}`
   - `PATCH /api/admin/user/{uid}` {teams?,all_teams?,login?}
   - `PATCH /api/workstream/{wid}/teams` {team_ids:[…]} → replace assignment, audit + broadcast (v12's `/access` endpoint stays but is deprecated)

## Caddy (`suite/Caddyfile`)

Inside `handle_path /allex/*` and `handle_path /deals/*` (before reverse_proxy):

```
forward_auth localhost:8083 {
    uri /api/authz?module=allex        # resp. module=dealroom
    header_up X-Remote-User {http.auth.user.id}
}
```

`/investor/*` and `/cockpit/*` unchanged (investor = Caddy-confined shared cred; cockpit enforces in-app). Order guarantee: the `@investor_outside` 403 block stays ahead, so the shared investor cred never reaches forward_auth.

## Frontend

- `boot.js`: `window.COCKPIT = {perms, isAdmin, modules, readOnly}` from principal.
- `app.jsx`: NAV filtered by `perms` keys (as v12 via modules); write-controls (`New` button) gated on `perms.workstreams==='rw'`; view-only banner when `readOnly`; NAV gains **Admin** entry (isAdmin only, hash `#admin`).
- `quick-add.jsx` / `view-table/timeline/week` add-buttons: gate on `perms.workstreams==='rw'` (was global readOnly).
- `task-drawer.jsx`: editable iff `perms.workstreams==='rw'`; verdict buttons iff `perms.agents==='rw'`.
- `view-agents.jsx`: verdict/answer/adopt actions iff `perms.agents==='rw'`.
- **`view-admin.jsx` (new, minimal)**: three sections from `/api/admin/overview` — Users (create → token shown once, edit teams/all_teams/login), Teams (create/edit permissions matrix: module × rw/ro/none), Workstream assignment (workstream × team checkboxes). Plain tables, `repuro-ci` tokens, no bespoke styling.
- Team filter chips (v1 spec §frontend): DEFERRED — not in Roman's ask.

## Rollout (zero-downtime, opt-in — unchanged from v1)

1. Ship v13: rd/ff in `md` (admin, all-rw), no workstream assignments → nothing changes.
2. Roman creates `mna`/`hr`/`marketing` teams + members in the Admin view.
3. Assign workstreams to teams area by area; scoping starts per assignment.
4. External users: `POST /api/admin/user` (+ Caddy basic-auth cred + `login` value — still required per user, as v12).

## Test checklist

Regression: rd/ff see all modules + can mutate everything (md implicit rw); agent queue/lane endpoints byte-identical behavior; personal-task privacy unchanged; pre-assignment all workstreams visible to both.
Teams: strongest-wins merge (user in {ro-team, rw-team} → rw); module absent from all teams → hidden from nav + state; ro user → GET ok, mutations 403; workstream assigned to team A hidden from non-member (incl. deliverables/tasks); all_teams=1 sees assigned workstreams regardless; admin endpoints 403 for non-admin; create user → token once; login-based X-Remote-User resolution without _CADDY_USER_MAP entry; /api/authz matrix (none/ro/rw × GET/POST, unknown login → 403).
