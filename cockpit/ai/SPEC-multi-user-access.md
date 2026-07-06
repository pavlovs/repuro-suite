# SPEC: Multi-User Access Control (t-403)

**Status:** Draft — awaiting verdict  
**Goal:** Allow external users (advisors, deal teams) scoped access to specific cockpit modules and workstreams only, without changing existing rd/ff/agent behavior.

---

## Problem

Cockpit currently has 4 fixed principals (rd, ff, rc-agent, fc-agent). To involve external parties (FDD advisors, deal consultants, future team members), Roman needs:
1. Module-level gating — control which sidebar views a user can reach
2. Workstream-level scoping — within accessible views, users see only their deals
3. Read-only mode — external users can view but not mutate

---

## Non-Goals (v1)

- Sub-task-level permissions within a workstream
- Custom per-user module overrides (profiles cover all cases)
- Commenting or partial-edit permissions (read-only is the external mode)
- Notification/email on state changes

---

## Design

### Core concepts

**Role profile** — reusable permission set: which modules can be accessed + read_only flag.  
**Workstream access list** — per-workstream whitelist of profiles that may see it (null = everyone).  

Adding a new user = assign a profile + optionally restrict which workstreams they see. No per-user module config needed.

---

## Data Model Changes

### New table: `role_profiles`

```sql
CREATE TABLE role_profiles (
  id           TEXT PRIMARY KEY,           -- 'owner', 'advisor', 'viewer'
  name         TEXT NOT NULL,              -- display label
  module_access TEXT NOT NULL,             -- JSON array of module ids
  read_only    INTEGER NOT NULL DEFAULT 0, -- 1 = all mutations blocked
  sort_order   INTEGER NOT NULL DEFAULT 0
);
```

Seed rows (inserted in migration):

| id | name | module_access | read_only |
|----|------|--------------|-----------|
| `owner` | Owner | `["overview","week","workstreams","timeline","agents","relations"]` | 0 |
| `advisor` | Advisor | `["workstreams","timeline"]` | 1 |
| `viewer` | Viewer | `["workstreams"]` | 1 |

Module ids map 1:1 to current hash-routing keys: `overview` (#cockpit), `week` (#week), `workstreams` (#workstreams), `timeline` (#timeline), `agents` (#agents), `relations` (#relations).

### New column: `users.profile`

```sql
ALTER TABLE users ADD COLUMN profile TEXT REFERENCES role_profiles(id);
-- Backfill: existing humans → 'owner'; agents keep role='agent', profile stays NULL
UPDATE users SET profile = 'owner' WHERE role = 'human';
```

### New column: `workstreams.allowed_profiles`

```sql
ALTER TABLE workstreams ADD COLUMN allowed_profiles TEXT;
-- NULL = accessible to every profile (default, keeps all existing workstreams open)
-- JSON array e.g. '["owner","advisor"]' = only those profiles can see this workstream
```

---

## Schema Migration v11 → v12

Add to `MIGRATIONS` dict in `src/db.py`:

```python
"12": [
    """CREATE TABLE role_profiles (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        module_access TEXT NOT NULL,
        read_only INTEGER NOT NULL DEFAULT 0,
        sort_order INTEGER NOT NULL DEFAULT 0
    )""",
    """INSERT INTO role_profiles (id, name, module_access, read_only, sort_order) VALUES
        ('owner',   'Owner',   '["overview","week","workstreams","timeline","agents","relations"]', 0, 1),
        ('advisor', 'Advisor', '["workstreams","timeline"]',                                       1, 2),
        ('viewer',  'Viewer',  '["workstreams"]',                                                  1, 3)
    """,
    "ALTER TABLE users ADD COLUMN profile TEXT REFERENCES role_profiles(id)",
    "UPDATE users SET profile = 'owner' WHERE role = 'human'",
    "ALTER TABLE workstreams ADD COLUMN allowed_profiles TEXT",
],
```

---

## Backend Changes (`src/api.py` + `src/db.py`)

### 1. Load profile in `principal()` dependency

When resolving the auth principal, join `role_profiles` to get `module_access` and `read_only`:

```python
row = conn.execute(
    """SELECT u.*, rp.module_access, rp.read_only
       FROM users u
       LEFT JOIN role_profiles rp ON rp.id = u.profile
       WHERE u.token_hash = ?""",
    (token_hash,)
).fetchone()
```

Return dict includes `modules` (parsed JSON list) and `read_only` (bool).  
For `role='agent'` principals (profile=NULL): `modules=["agents"]`, `read_only=False` (agents use existing `agent_only` guard).

### 2. `/api/state` — extend `principal` block

```python
"principal": {
    "id":       me["id"],
    "name":     me["name"],
    "initials": me["initials"],
    "role":     me["role"],
    "profile":  me["profile"],          # NEW
    "modules":  me["modules"],          # NEW — list of accessible module ids
    "read_only": me["read_only"],       # NEW — bool
}
```

### 3. `assemble_state()` — workstream scoping

After fetching all workstreams, filter before assembling deliverables/tasks:

```python
profile = me.get("profile")
if profile and profile != "owner" and me["role"] != "agent":
    workstreams = [
        ws for ws in workstreams
        if ws["allowed_profiles"] is None
        or profile in json.loads(ws["allowed_profiles"] or "null" or "[]")
    ]
# deliverables and tasks are already joined via workstream_id — cascade naturally
```

Owners and agents are not filtered (owner sees all; agent filtering already done via lane).

### 4. New `read_only_guard` dependency

```python
def read_only_guard(p: dict = Depends(principal)) -> dict:
    if p.get("read_only"):
        raise HTTPException(status_code=403, detail="This account is read-only")
    return p
```

Apply `Depends(read_only_guard)` (replacing or stacking with `Depends(human_only)`) to all mutation endpoints:

| Endpoint | Current guard | Add guard |
|----------|--------------|-----------|
| `POST /api/task` | human_only | read_only_guard |
| `PATCH /api/task/{tid}` | human_only | read_only_guard |
| `DELETE /api/task/{tid}` | human_only | read_only_guard |
| `POST /api/workstream` | human_only | read_only_guard |
| `PATCH /api/workstream/{wid}` | human_only | read_only_guard |
| `POST /api/deliverable` | human_only | read_only_guard |
| `PATCH /api/deliverable/{did}` | human_only | read_only_guard |
| `DELETE /api/deliverable/{did}` | human_only | read_only_guard |
| `PATCH /api/tasks/reorder` | human_only | read_only_guard |
| `PATCH /api/workstreams/reorder` | human_only | read_only_guard |
| `PATCH /api/deliverables/reorder` | human_only | read_only_guard |
| `POST /api/task/{tid}/approve` | human_only | read_only_guard |
| `POST /api/task/{tid}/reject` | human_only | read_only_guard |
| `POST /api/task/{tid}/request-changes` | human_only | read_only_guard |
| `POST /api/task/{tid}/answer` | human_only | read_only_guard |
| `POST /api/learning/{lid}/decide` | human_only | read_only_guard |
| `PATCH /api/deal/{codename}` | human_only | read_only_guard |

Agent endpoints (`/api/agent/*`) are unchanged — they use `agent_only` already.

### 5. New endpoint: `POST /api/admin/user` (owner-only)

Creates a new principal and returns their token once. Requires `profile` in body.

```
POST /api/admin/user
Body: {id: str, name: str, initials: str, profile: str}
Response: {id: str, token: str}  ← raw token shown only at creation
Guard: human_only + profile='owner' check (reject if caller's profile != 'owner')
```

Server generates a random token, stores SHA256 hash in users table.

### 6. New endpoint: `PATCH /api/workstream/{wid}/access` (owner-only)

Sets `allowed_profiles` on a workstream.

```
PATCH /api/workstream/{wid}/access
Body: {allowed_profiles: list[str] | null}
Guard: human_only + owner profile check
Side-effect: broadcast state refresh to all connected clients
```

---

## Frontend Changes

### `boot.js` — store modules + read_only on COCKPIT global

After `assemble_state()` response arrives:

```js
window.COCKPIT.modules  = state.principal.modules;    // ['workstreams','timeline']
window.COCKPIT.readOnly = state.principal.read_only;  // true | false
```

### `app.jsx` — filter NAV by allowed modules

```jsx
const NAV_ALL = [
  { id: 'overview',    label: 'Cockpit',     hash: '#cockpit'     },
  { id: 'week',        label: 'Meeting',     hash: '#week'        },
  { id: 'workstreams', label: 'Workstreams', hash: '#workstreams' },
  { id: 'timeline',    label: 'Timeline',    hash: '#timeline'    },
  { id: 'agents',      label: 'Agents',      hash: '#agents'      },
  { id: 'relations',   label: 'Relations',   hash: '#relations'   },
];
const NAV = NAV_ALL.filter(n => window.COCKPIT.modules.includes(n.id));
```

On page load, if current hash is not in allowed modules → redirect to first allowed module.

### `app.jsx` — read-only banner

At the top of the shell render:

```jsx
{window.COCKPIT.readOnly && (
  <div className="read-only-banner">View-only access</div>
)}
```

### `quick-add.jsx` — hide entirely when read-only

```jsx
if (window.COCKPIT.readOnly) return null;
```

### `task-drawer.jsx` — view-only mode when read-only

When `window.COCKPIT.readOnly`:
- Replace all `<input>`, `<textarea>`, `<select>` with `<span>` (display values)
- Hide approve/reject/request-changes buttons
- Hide "Save" button

### `view-table.jsx` — hide creation buttons

```jsx
{!window.COCKPIT.readOnly && <button className="add-workstream">+ Workstream</button>}
{!window.COCKPIT.readOnly && <button className="add-deliverable">+ Deliverable</button>}
```

### `cockpit.css` — read-only banner style

```css
.read-only-banner {
  position: sticky;
  top: 0;
  z-index: 100;
  background: #fef3c7;
  color: #92400e;
  font-size: 11px;
  font-weight: 500;
  text-align: center;
  padding: 4px 16px;
  letter-spacing: 0.02em;
}
```

---

## New Principals (Example: Ebner Stolz)

**`cockpit.py` PRINCIPALS dict — add:**
```python
"ebner-stolz": ("Heiko Jander", "HJ", "human", None),
```

**Users row:**
```sql
INSERT INTO users (id, name, initials, role, profile) VALUES
  ('ebner-stolz', 'Heiko Jander', 'HJ', 'human', 'advisor');
-- token set via: cockpit token ebner-stolz
```

**Workstream access** — grant advisor access to Fox + Mantis:
```
PATCH /api/workstream/<fox-wid>/access    {"allowed_profiles": ["owner", "advisor"]}
PATCH /api/workstream/<mantis-wid>/access {"allowed_profiles": ["owner", "advisor"]}
```
All other workstreams remain `allowed_profiles=null` (owner-only effectively, since advisor profile doesn't grant global access — null means "no restriction" but advisor already can't see non-whitelisted workstreams because of the `assemble_state` filter logic).

**Wait** — null means "no restriction" which would expose all workstreams to advisors. Two options:

- **Option A (recommended):** Default `allowed_profiles=null` means owner-only for non-owner profiles. Explicitly whitelist workstreams for advisors.  
- **Option B:** Default null means all profiles. Advisors see everything unless restricted.

**Recommendation: Option A.** Safer default — new workstreams are private until explicitly shared. Implementation: in `assemble_state()` filter, for non-owner profiles, only show workstreams where `allowed_profiles` contains their profile (null = not accessible to advisors).

```python
# Option A logic:
if profile and profile != "owner" and me["role"] != "agent":
    workstreams = [
        ws for ws in workstreams
        if ws["allowed_profiles"] is not None
        and profile in json.loads(ws["allowed_profiles"])
    ]
```

---

## Caddy / Fly Config (Prod)

For each new human user, add a basic auth credential in Fly secrets:
```
flyctl secrets set COCKPIT_AUTH_HEIKO="hj:$bcrypt_hash"
```

Update Caddy config to include the new username → principal mapping:
```
basicauth {
  roman  <hash>   # → X-Remote-User: roman (maps to rd)
  florian <hash>  # → X-Remote-User: florian (maps to ff)
  hj     <hash>   # → X-Remote-User: hj (maps to ebner-stolz)
}
```

Caddy's `X-Remote-User` passthrough: add mapping `hj` → `ebner-stolz` in the existing principal resolution logic in `api.py` (the dict that maps header values to user IDs).

---

## Implementation Sequence

1. `src/db.py` — add migration v12 (role_profiles table + users.profile + workstreams.allowed_profiles)
2. `src/api.py` — extend `principal()` to load profile/modules/read_only
3. `src/api.py` — extend `assemble_state()` with workstream filter (Option A)
4. `src/api.py` — add `read_only_guard` dependency + apply to mutation endpoints
5. `src/api.py` — add `POST /api/admin/user` and `PATCH /api/workstream/{wid}/access`
6. `static/boot.js` — store modules + read_only on COCKPIT global
7. `static/app.jsx` — filter NAV, add read-only banner, guard creation buttons
8. `static/quick-add.jsx` — hide when read-only
9. `static/task-drawer.jsx` — view-only mode
10. `static/view-table.jsx` — hide creation buttons
11. `static/cockpit.css` — read-only banner style
12. `cockpit.py` — add new principals to PRINCIPALS dict
13. Deploy + run `cockpit token <new-principal>` to issue credentials

---

## Test Checklist

**Regression (existing behavior unchanged):**
- [ ] rd sees all 6 nav modules, can create/edit/delete tasks, workstreams, deliverables
- [ ] ff same as rd
- [ ] rc-agent queue fetch returns only rd-lane tasks (`scope=mine`)
- [ ] fc-agent queue fetch returns only ff-lane tasks
- [ ] Personal task privacy unchanged (kind='personal' scrubbed for non-creators)

**New access control:**
- [ ] New advisor user: login → sees only Workstreams + Timeline in nav
- [ ] Advisor: hash #cockpit in URL → auto-redirect to #workstreams
- [ ] Advisor: GET /api/state → workstreams list contains only explicitly whitelisted workstreams
- [ ] Advisor: deliverables and tasks from non-allowed workstreams absent from state
- [ ] Advisor: POST /api/task → 403
- [ ] Advisor: PATCH /api/task/{tid} → 403
- [ ] Advisor: read-only banner visible in browser
- [ ] Advisor: quick-add modal not rendered
- [ ] Advisor: task-drawer opens in view-only mode (no inputs, no save button)
- [ ] Workstream allowed_profiles=null → not accessible to advisor (Option A)
- [ ] Workstream allowed_profiles=["owner","advisor"] → visible to advisor
- [ ] PATCH /api/workstream/{wid}/access by advisor → 403
- [ ] POST /api/admin/user by owner → creates user, returns token once
- [ ] POST /api/admin/user by advisor → 403

**Edge cases:**
- [ ] New workstream created → allowed_profiles=null → not accessible to existing advisors until explicitly set
- [ ] Advisor token deleted → subsequent requests return 401 (not 403)
- [ ] rd SSE events: state refresh after PATCH /api/workstream/{wid}/access → advisor's next GET /api/state reflects new access
