# SPEC: Multi-User Access Control — v2 (t-403 redo)

**Status:** Draft — awaiting verdict  
**Replaces:** v1 (role_profiles model — dropped per Roman feedback)  
**Date:** 2026-07-07

---

## What is already live (v2.1.23)

The **teams system** was approved and deployed today. It is the access control foundation. This spec does NOT re-specify it — see `SPEC-teams.md` for the authoritative description. Summary:

- Users belong to one or more **teams** (MD, M&A, HR, Accounting, Strada, …)
- Each team carries a **per-module permission map** (`{module_id: "rw"|"ro"}`)
- Effective permission = strongest across all user's teams (rw beats ro beats none)
- MD team = `is_admin`, implicit rw everywhere
- `all_teams=1` (Roman) = god view over all workstreams
- Workstreams can be scoped to specific teams; unscoped = visible to all
- `/api/authz` Caddy forward_auth enforces Dealroom + ALLEX at the gateway layer

---

## What this spec adds (the two gaps Roman flagged)

### 1. Profile view — "see your own team"

A user must be able to open their profile in the Cockpit and see:
- Which teams they belong to
- What those teams give them access to (per-module, rw vs ro)
- Their Cockpit login (the X-Remote-User identity)

**Implementation:**

**Backend:** `GET /api/me` — no new table, reads from existing `principal()` resolver.

```json
{
  "id": "eb01",
  "name": "Heiko Jander",
  "initials": "HJ",
  "login": "heiko",
  "teams": [
    { "id": "advisor", "name": "Advisor", "permissions": {"workstreams":"ro","timeline":"ro"} }
  ],
  "effective_perms": { "workstreams": "ro", "timeline": "ro" },
  "all_teams": false
}
```

**Frontend:** New `#profile` hash route / panel (sidebar avatar → profile). Shows:
- Name + initials avatar
- Teams list: each team as a row with its permission badges
- "Your access" summary table: module → rw / ro / none
- Read-only — no self-edit (admin manages membership)

**Scope:** ~40 lines backend, ~80 lines frontend. No schema changes.

---

### 2. Agent mirroring — "each member gets an agent"

Each team member should have access to a Cockpit agent scoped to their role/permissions. The agent should only see and act on the workstreams/modules the user can access.

**Design decision (spec only — Roman to confirm before build):**

**Option A — Shared runner, per-team lane:** The existing `rc-agent` / `fc-agent` pattern extended. Each team gets a named agent identity in `users` with `role='agent'` and the team's permissions as its effective perms. The agent queue (`/api/agent/queue`) filtered by the team's accessible workstreams.

**Option B — Per-user agent token:** A user generates an agent token from their profile page. The token inherits their effective permissions. They use it to run local Claude Code sessions against the cockpit with their scoped access.

**Recommendation: Option B** — simpler, no new agent processes, aligns with how Roman/Flo already work (local Claude → cockpit token). The profile page gets a "Generate agent token" button. Token = a one-time JWT stored in `agent_tokens` table, valid 30 days, scoped to the user's effective permissions at generation time.

**Schema addition (Option B):**
```sql
CREATE TABLE IF NOT EXISTS agent_tokens (
  id        TEXT PRIMARY KEY,      -- random slug
  user_id   TEXT NOT NULL REFERENCES users(id),
  perms     TEXT NOT NULL,         -- JSON snapshot of effective_perms at creation
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_used  TEXT
);
```

**Backend:** `POST /api/me/agent-token` → generates token, returns once. `GET /api/agent/queue` and all agent endpoints: accept Bearer token from `agent_tokens` in addition to X-Remote-User (same principal resolution, token's `perms` used as effective).

**Frontend:** Profile page → "Agent Token" section: "Generate" button, shows token once, expiry date, revoke button.

---

## Implementation sequence (one-shot)

1. `GET /api/me` endpoint (5 lines — wraps existing `principal()`)
2. `agent_tokens` table + migration (idempotent)
3. `POST /api/me/agent-token` + Bearer auth in agent endpoints
4. Frontend profile panel (avatar click → slide-in panel, 3 sections: identity, teams, agent token)
5. Sidebar avatar/initials button to open profile (currently missing)

**Estimated scope:** ~200 lines total (backend ~80, frontend ~120). One session.

---

## Out of scope (v2)

- Sub-workstream permissions
- Team-level agent queues (Option A — deferred)
- Notification/email on access change
- Self-service team request flow

---

## How this addresses Roman's feedback

| Feedback | Response |
|----------|----------|
| role_profiles do not make sense | Dropped. Teams are the sole permission carrier (already live v2.1.23) |
| Different teams (MD, M&A, HR, etc.) | Supported — admin creates teams with any id/permissions via `/api/admin/team` |
| Member of multiple teams | Supported — strongest permission wins (already live) |
| Investor as a team (Strada) | Supported — create `strada` team with ro workstream access |
| Profile page shows own team | New: `GET /api/me` + profile panel in frontend |
| Agent mirrored to role | New: agent token inheriting user's effective permissions (Option B) |
