# Cockpit Architecture Rework — Entity Hierarchy

**Status:** Codex-reviewed + iterated with Roman, pending final approval
**Scope:** DB schema, API, sidebar/navigation, table view grouping. Architecture only.
**Trigger:** UX review 2026-06-16 S2.2 — "Workstream conflates thematic grouping with deal container"
**Codex review:** `codex-reviews/2026-06-16-1615-dev.md` — all 6 critical issues addressed.

---

## 1. Problem

The current model is flat: **Workstream -> Deliverable -> Task** (3 levels).

"Fundraising" (thematic, ongoing) and "Fox -- DD" (deal-specific, finite) are both workstreams. This conflation means:
- No organizational structure above work execution
- Can't see "all M&A deal work" vs "all holding company work" in one view
- A Fox admin task under "Admin" workstream disappears from Fox-filtered views unless also tagged `task.deal = fox`
- Sidebar is a flat list that will grow linearly with every new deal

## 2. Target Hierarchy

```
Space                          (organizational division)
 +-- Project                   (functional area or deal)
      +-- Deliverable          (work package / milestone)
           +-- Task            (atomic work item)
```

**Two spaces. Everything below a space is a "project."** No semantic distinction between ongoing functional areas and finite deals — both are projects. The difference is visibility and sort behavior, not entity type.

**Concrete structure:**

```
REPURO (space) — the company
+-- Fundraising (project)              -- manual sort order, drag-and-drop
|   +-- D: "ASF pipeline DD"
|   |   +-- T: "Send updated deck to Laura"
|   +-- D: "Term sheet finalization"
|       +-- T: "Review Strada term sheet"
+-- Operations (project)
|   +-- D: "Cockpit rollout"
|       +-- T: "Deploy to Fly.io"
+-- Investor Reporting (project)
|   +-- D: "Quarterly reporting"
|       +-- T: "Prepare Q2 investor update"
+-- Admin (project)
    +-- D: "(general)"
        +-- T: "Hire allrounder"

M&A (space) — deal execution
+-- Fox (project, deal, stage=dd)       -- auto-sorted by stage, LOI+ visible
|   +-- D: "CDD"
|   |   +-- T: "Review SPA draft"
|   +-- D: "LDD"
|   +-- D: "TDD / FDD"
|   +-- D: "Financial model"
|       +-- T: "Update EBIT bridge"
+-- Octopus (project, deal, stage=loi)
|   +-- D: "Indicative offer"
|       +-- T: "Finalize valuation range"
+-- Lion (project, deal, stage=valuation_rfi)  -- pre-LOI, collapsed in sidebar
+-- Cat (project, deal, stage=screening)       -- early stage, collapsed
+-- Pipeline (project, thematic)               -- always last
    +-- D: "BA9 outreach"
        +-- T: "Send 40 teaser emails"
```

**Every deal is a project. Always.** No entity-type promotion when deals advance. A screening-stage deal with 1 task is just a project with 1 task. What changes is sidebar visibility and sort position, not structure.

**Standalone tasks** (deliverable_id IS NULL) continue to exist. They render in a "(No deliverable)" section at the bottom of their project. No migration into synthetic deliverables.

## 3. Sorting Rules

### 3.1 Repuro space — manual drag-and-drop

Projects under Repuro are ordered by `sort_order` (integer). Users can reorder via drag-and-drop in the sidebar. The API exposes a reorder endpoint.

### 3.2 M&A space — auto-sorted by deal stage

Projects under M&A are sorted by deal stage progression (most advanced first). Pipeline is always last.

```
Stage sort weights (higher = more advanced = sorted first):
  signing       → 100
  spa           → 90
  dd            → 80
  loi_signed    → 70
  indicative_offer → 60
  valuation_rfi → 50
  nda           → 40
  initial_contact → 30
  screening     → 20
  on_hold       → 10
  dead          → 5
  (no deal / Pipeline) → 0   -- always last
```

Within the same stage, secondary sort by `sort_order` (manual tiebreaker).

**Sidebar visibility tiers for M&A:**
- **LOI+** (loi_signed, dd, spa, signing): always visible, expanded
- **Pre-LOI** (valuation_rfi, indicative_offer, nda, initial_contact, screening): collapsed under a "Pre-LOI deals" toggle
- **on_hold / dead**: hidden (visible only in "Show all" mode)
- **Pipeline**: always visible, always last

Deal stage comes from `deal_mirror` (synced from dealroom.db). When a deal advances in dealroom, the cockpit sidebar re-sorts automatically on next sync.

### 3.3 Reorder API

```
PATCH /api/workstreams/reorder
  Payload: {workstream_ids: ["w-3", "w-1", "w-2"]}
  Response: {reordered: 3}
```

Only works for projects in Repuro space (manual sort). M&A projects reject reorder with 422 ("M&A projects are auto-sorted by deal stage").

## 4. Database Changes

### 4.1 New table: `spaces`

```sql
CREATE TABLE spaces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  color TEXT,
  icon TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  sort_mode TEXT NOT NULL DEFAULT 'manual'
    CHECK(sort_mode IN ('manual','deal_stage')),
  status TEXT NOT NULL DEFAULT 'active'
    CHECK(status IN ('active','parked','done')),
  version INTEGER NOT NULL DEFAULT 1
);
```

Pre-seeded (2 spaces):
- `('Repuro', 'repuro', '#0891B2', 'building', 0, 'manual')` — company ops, manual project sort
- `('M&A', 'mna', '#7C3AED', 'handshake', 1, 'deal_stage')` — deals, auto-sorted by stage

`sort_mode` determines whether projects are manually ordered or auto-sorted by deal stage.

Spaces are **seeded in migration only** -- no CRUD endpoints in v1 (see D3).

### 4.2 Alter `workstreams` — conceptually "projects"

Keep `workstreams` table name (see D2). Add `space_id`. Drop global name uniqueness, enforce space-scoped:

```sql
ALTER TABLE workstreams ADD COLUMN space_id INTEGER NOT NULL DEFAULT 1 REFERENCES spaces(id);
CREATE UNIQUE INDEX uq_workstreams_space_name ON workstreams(space_id, name);
```

### 4.3 Add `deal` to deliverables

```sql
ALTER TABLE deliverables ADD COLUMN deal TEXT;
```

Auto-populated from project's `deal_codename` on creation. Makes deal view aggregation structural, not tag-dependent.

### 4.4 Deal stage weight (computed, not stored)

Stage-to-weight mapping lives in Python (compute.py), not in the DB. The `assemble_state()` function sorts M&A projects by weight before returning. No stored `stage_weight` column — it's derived from `deal_mirror.stage` at read time.

### 4.5 Migration (schema version 3 -> 4)

```python
MIGRATIONS[4] = [
    # 1. Create spaces table
    """CREATE TABLE spaces (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      slug TEXT NOT NULL UNIQUE,
      color TEXT,
      icon TEXT,
      sort_order INTEGER NOT NULL DEFAULT 0,
      sort_mode TEXT NOT NULL DEFAULT 'manual'
        CHECK(sort_mode IN ('manual','deal_stage')),
      status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','parked','done')),
      version INTEGER NOT NULL DEFAULT 1
    )""",

    # 2. Seed 2 default spaces
    "INSERT INTO spaces (name, slug, color, icon, sort_order, sort_mode) "
    "VALUES ('Repuro', 'repuro', '#0891B2', 'building', 0, 'manual')",
    "INSERT INTO spaces (name, slug, color, icon, sort_order, sort_mode) "
    "VALUES ('M&A', 'mna', '#7C3AED', 'handshake', 1, 'deal_stage')",

    # 3. Add space_id (default=1 = Repuro for safe migration)
    "ALTER TABLE workstreams ADD COLUMN space_id INTEGER NOT NULL DEFAULT 1 "
    "REFERENCES spaces(id)",

    # 4. deal-linked projects -> M&A
    "UPDATE workstreams SET space_id = (SELECT id FROM spaces WHERE slug = 'mna') "
    "WHERE deal_codename IS NOT NULL",

    # 5. Pipeline -> M&A (no deal_codename but belongs to M&A)
    "UPDATE workstreams SET space_id = (SELECT id FROM spaces WHERE slug = 'mna') "
    "WHERE lower(name) = 'pipeline'",

    # 6. Everything else stays in Repuro (default=1)

    # 7. Drop global uniqueness, add space-scoped
    "DROP INDEX IF EXISTS sqlite_autoindex_workstreams_1",
    "CREATE UNIQUE INDEX uq_workstreams_space_name ON workstreams(space_id, name)",

    # 8. Add deal to deliverables
    "ALTER TABLE deliverables ADD COLUMN deal TEXT",

    # 9. Backfill deliverable.deal from project's deal_codename
    "UPDATE deliverables SET deal = ("
    "  SELECT w.deal_codename FROM workstreams w "
    "  WHERE w.id = deliverables.workstream_id AND w.deal_codename IS NOT NULL"
    ")",
]
```

**Migration safety:**
- Default `space_id = 1` (Repuro) ensures no NULL rows
- Pipeline explicitly mapped by name
- Fundraising, Operations, Admin stay in Repuro (correct default)
- Existing FKs untouched
- `deliverable.deal` backfill is additive

### 4.6 Auto-create projects from dealroom.db

On deal_mirror sync, for each deal in dealroom.db that has no corresponding project (workstream with `deal_codename`):
- Auto-create a project under M&A space with `deal_codename` set and `staging=1` (hidden until curated)
- Name = deal codename (e.g., "Fox", "Octopus")
- No auto-created deliverables — those are added manually or via playbook template

For LOI+ deals, the agent or user applies the **deal playbook template**: standard deliverables (CDD, LDD, TDD/FDD, IC Document, SPA/Signing) created under the project. Template application is a one-time action, not automatic — different deals need different DD streams.

### 4.7 Updated DDL for new databases

`init_db()` DDL includes `spaces` table with `sort_mode`, `workstreams.space_id NOT NULL`, `UNIQUE(space_id, name)`, `deliverables.deal`, and seeds the two default spaces.

### 4.8 Entity reference format

Existing: `w-1`, `d-1`, `t-1` — unchanged.
New: `s-1` for spaces in API responses.

Ref parser changes:
- `models.py`: add `space_id(n)` and `space_num(ref)` helpers
- `api.py/_safe_ref()`: add `'s'` to valid prefixes
- `api.py` workstream create/update: parse `space_id` field as `s-<n>` ref
- Tests: update ref validation tests

## 5. API Changes

### 5.1 No space CRUD in v1

Spaces are seeded by migration. No `POST /api/space` or `PATCH /api/space`. Third space = new migration.

### 5.2 Modified endpoints

**`GET /api/state`** — v4 response contract:

```json
{
  "spaces": [
    {
      "id": "s-1",
      "name": "Repuro",
      "slug": "repuro",
      "color": "#0891B2",
      "icon": "building",
      "sort_order": 0,
      "sort_mode": "manual",
      "status": "active",
      "version": 1,
      "workstreams": [
        {
          "id": "w-1",
          "name": "Fundraising",
          "space_id": "s-1",
          "color": "#...",
          "deal_codename": null,
          "deal_stage": null,
          "sort_order": 0,
          "status": "active",
          "version": 1,
          "deliverables": [
            {
              "id": "d-1",
              "name": "ASF pipeline DD",
              "target_date": "2026-06-30",
              "deal": null,
              "status": "open",
              "version": 1,
              "computed": {"progress": "2/5", "at_risk": false},
              "tasks": [...]
            }
          ],
          "standalone_tasks": [...]
        }
      ]
    },
    {
      "id": "s-2",
      "name": "M&A",
      "slug": "mna",
      "sort_mode": "deal_stage",
      "workstreams": [
        {
          "id": "w-5",
          "name": "Fox",
          "deal_codename": "fox",
          "deal_stage": "dd",
          "deal_mirror_status": "ok",
          "visibility": "expanded",
          "deliverables": [...]
        },
        {
          "id": "w-8",
          "name": "Lion",
          "deal_codename": "lion",
          "deal_stage": "valuation_rfi",
          "deal_mirror_status": "ok",
          "visibility": "collapsed",
          "deliverables": [...]
        },
        {
          "id": "w-2",
          "name": "Pipeline",
          "deal_codename": null,
          "deal_stage": null,
          "visibility": "expanded",
          "deliverables": [...]
        }
      ]
    }
  ],
  "standalone_tasks": [],
  "deals": [
    {"codename": "fox", "stage": "dd", "note": "...", "synced_at": "..."}
  ],
  "meta": {"task_count": 43, "overdue": 2, "waiting": 5, "today": "2026-06-16"},
  "principal": {"id": "rd", "name": "Roman", "role": "human"}
}
```

**Key additions:**
- `sort_mode` on space — tells frontend whether to allow drag-drop or show auto-sorted
- `deal_stage` on project — denormalized from deal_mirror for sorting + badge
- `deal_mirror_status` on deal projects — "ok", "stale" (>24h), "missing"
- `visibility` on M&A projects — "expanded" (LOI+), "collapsed" (pre-LOI), "hidden" (dead/hold). Computed from stage.
- M&A workstreams array is **pre-sorted by stage weight** (server-side). Frontend renders in order received.
- Repuro workstreams array is sorted by `sort_order`. Frontend allows drag-drop reorder.

**`POST /api/workstream`** — required: `space_id` (ref `s-<n>`).

**`PATCH /api/workstream/{wid}`** — optional: `space_id` (move between spaces).

**`PATCH /api/workstreams/reorder`** — manual sort (Repuro only). 422 for M&A projects.

**`POST /api/deliverable`** — `deal` auto-populated from project's `deal_codename`.

### 5.3 MD export/import

**Export** gains space grouping:
```markdown
## Repuro

### Fundraising
#### ASF pipeline DD
- [ ] Send updated deck to Laura @RD !high due:2026-06-20

## M&A

### Fox [DD]
#### CDD
- [ ] Review commercial data room @RD due:2026-07-01
#### LDD
- [ ] Review SPA draft @FF due:2026-06-25
```

**Import:** space headers must match existing space name exactly (no auto-create). Unknown = 422.

### 5.4 Deal mirror degraded behavior

- Codename comparison always **lowercase**
- Missing mirror: stage = "unknown" (grey badge), note = "Mirror not synced"
- Stale mirror (>24h): warning icon on badge
- `deal_mirror_status` in API per deal project

## 6. Frontend Changes

### 6.1 Sidebar navigation

```
[Cockpit]       — overview (unchanged)
[My Week]       — personal focus (unchanged)

REPURO          — collapsible section header
  Fundraising     — project (drag-drop reorderable)
  Operations
  Investor Reporting
  Admin

M&A             — collapsible section header
  Fox [DD]        — deal project (auto-sorted, stage badge)
  Octopus [LOI]
  v Pre-LOI deals — collapsible toggle
    Lion [VAL]
    Cat [SCR]
  Pipeline        — always last

[Timeline]      — cross-cutting (unchanged)
[Agents]        — agent queue (unchanged)
[Relations]     — dependency graph (unchanged)
```

Repuro projects: drag handle on hover for reordering.
M&A projects: auto-sorted, no drag. Stage badge from deal_mirror.

### 6.2 Table view (All Projects tab)

```
+-- REPURO ---------------------------------------------------+
|  v Fundraising                                              |
|    v ASF pipeline DD                        due 2026-06-30  |
|      [ ] Send updated deck to Laura  RD high  green         |
|  v Operations                                               |
|    ...                                                      |
+-- M&A ------------------------------------------------------+
|  v Fox  [DD]                                                |
|    v CDD                                    due 2026-07-01  |
|      [ ] Review commercial data room RD high  green         |
|    v LDD                                    due 2026-07-15  |
|      [ ] Review SPA draft            FF high  red           |
|    v TDD / FDD                              due 2026-07-20  |
|    v IC Document                            due 2026-08-01  |
|  v Octopus  [LOI]                                           |
|    ...                                                      |
|  v Pipeline                                                 |
|    ...                                                      |
+-------------------------------------------------------------+
```

### 6.3 Board view

- "Group by Status" — columns: Open | In Progress | Waiting | Done (cards show project badge)
- "Group by Project" — swimlanes per project, under space headers
- "Group by Space" — two swimlanes: Repuro | M&A

### 6.4 Deal view

Clicking a deal project under M&A opens the **Deal view**: single-deal focus.

Content:
- Stage badge + note from deal_mirror
- All deliverables under this project (CDD, LDD, TDD, etc.) with progress
- **Cross-project section:** deliverables with `deliverable.deal = <codename>` from other projects + tasks with `task.deal = <codename>` in non-deal deliverables
- Waiting items + chase dates
- Blockers (readiness = red)
- Timeline strip

### 6.5 boot.js data transformation

```javascript
COCKPIT_DATA = {
  TODAY: "2026-06-16",
  PEOPLE: {RD: {...}, FF: {...}},
  SPACES: [
    {id: "s-1", name: "Repuro", slug: "repuro", sortMode: "manual"},
    {id: "s-2", name: "M&A", slug: "mna", sortMode: "deal_stage"}
  ],
  PROJECTS: [
    {id: "w-1", name: "Fundraising", space: "s-1", deal: null, dealStage: null, sortOrder: 0},
    {id: "w-5", name: "Fox", space: "s-2", deal: "fox", dealStage: "dd", visibility: "expanded"}
  ],
  DELIVERABLES: [{id: "d-1", project: "w-1", deal: null, ...}],
  TASKS: [{id: "t-1", d: "d-1", deal: null, ...}],
  STANDALONE: [{id: "t-99", project: "w-1", deal: null, ...}]
}
```

## 7. Migration of Existing Data

| Current workstream | deal_codename | -> Space | Rule |
|---|---|---|---|
| Fundraising | null | Repuro | default |
| Admin | null | Repuro | default |
| Operations | null | Repuro | default |
| Pipeline | null | M&A | explicit name match |
| Fox -- DD | fox | M&A | deal_codename present |
| Octopus -- IO | octopus | M&A | deal_codename present |
| (any with deal_codename) | * | M&A | deal_codename present |
| (any without) | null | Repuro | default fallback |

**Existing deliverables, tasks, and their content are untouched.** Only the project's `space_id` and `deliverable.deal` backfill change. No renames, no deletions, no restructuring of existing items.

## 8. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Spaces are a real DB entity, not UI-only | API-level filtering, sort_mode, future permissions |
| D2 | Keep `workstreams` table name, "project" in UI/API | 66 tests + seeds reference workstreams; DB name is implementation detail |
| D3 | No space CRUD in v1, seeded only | Two spaces cover the use case. No taxonomy drift. |
| D4 | `space_id NOT NULL` default=1, required on new creates | Safe migration + explicit choice going forward |
| D5 | `deliverable.deal` auto-set from project's deal_codename | Structural deal association, not tag-fragile |
| D6 | Two flat spaces: Repuro + M&A | Fundraising is a project under Repuro, not its own space |
| D7 | `UNIQUE(space_id, name)`, not global | Space-scoped project names |
| D8 | Standalone tasks preserved | "(No deliverable)" sub-section per project |
| D9 | Repuro: manual sort (drag-drop). M&A: auto-sort by deal stage. | `sort_mode` on space controls behavior. Pipeline always last. |
| D10 | Every deal is a project regardless of stage | No entity promotion. Visibility and sort position change, not structure. |
| D11 | Deal playbook template applied manually on LOI+ | Standard deliverables (CDD, LDD, TDD, IC Doc, SPA) — not auto-created |

## 9. Risks

1. **4-level depth** — mitigated by thin space dividers, collapsible projects
2. **Auto-sort vs manual expectations** — M&A users can't reorder deals. Acceptable because stage progression IS the natural order.
3. **Pre-LOI deal clutter** — mitigated by "Pre-LOI deals" collapsible toggle in sidebar
