# COCKPIT — Repuro PM Tool

Hosted (eventually) internal project-management tool for RD + FF: workstreams with prerequisite
readiness colors, waiting-on/chase model, computed daily/weekly recommendations, agent task queue.
Design spec: `ai/DESIGN-SPEC.md` (v5, approved 2026-06-11). Milestones: `ai/PLAN.md` + `ai/ROADMAP.md`.

## Architecture (one line)
FastAPI + SQLite (`data/cockpit.db`, journal DELETE) → JSON/MD API on localhost:8099 → Alpine.js SPA (M2+). Local-first; Fly.io at M5. **Remote API access: see `REMOTE-API.md`** — SSH + Python via flyctl, X-Remote-User auth.

## Hard rules (inherit workspace CLAUDE.md, plus)
- **PROD IS ON FLY, NOT LOCAL — verify before mutating.** `repuro-suite.fly.dev/cockpit/` (Fly DB) is the ONLY source of truth Roman sees. The local `:8099` DB is a **diverged, stale copy** — workstream names/IDs differ (local `Fundraising`/`w-1` = prod `Equity Partner`/`w-1`; the IDs collide but mean different things). **Never make real data changes via `:8099`.** ALL mutations go to prod via `REMOTE-API.md` (flyctl SSH → `localhost:8083`, `X-Remote-User: roman`). Before any mutation, `GET /api/state` and confirm a known deliverable name matches what Roman sees. Data changes are **live on HTTP 200 — no deploy needed**; only code changes (`.py`/`.js`/`.css`) require `fly deploy`. *(2026-06-24: a full update round was applied to local by mistake, invisible to Roman, and a local-ID delete plan would have destroyed real prod rows. Don't repeat.)*
- **cockpit.db**: journal_mode=DELETE (OneDrive safety). Never commit. Mutations only through the API/db module — never raw writes from scripts.
- **dealroom.db is read-only here.** Open with `file:...?mode=ro` URI ALWAYS (plain connect() on a wrong path silently creates an empty db — a stray 0-byte `dealroom/dealroom.db` exists from exactly this mistake). Deal stage is mastered in dealroom.db; cockpit mirrors it.
- **Real names never enter cockpit.db** — codenames only. The codename→name map stays in the dealroom.
- **Code ownership**: FC does not edit `.py`/`.html`/`.js`/`.css` here — tickets to `TICKETS.md`, RC implements.
- **Milestone loop**: /plan-milestone → /execute-milestone → /review-milestone (separate agent) for every milestone. No milestone done without independent review.
- Port 8099 (Roman 2026-06-11). Python 3.12, venv at `.venv/`.
- **UI verification loop — MANDATORY after ANY frontend change** (Roman 2026-06-12: "I shouldn't have to find the bugs"). Loop until a round finds nothing new:
  1. Compile: node + babel.min.js transform of the full JSX bundle (catches bundle-scope errors curl can't).
  2. `pytest` (API contract).
  3. Restart server, run `CLAUDE_COWORK/cockpit-e2e/run.js` — drives real Edge, screenshots all views + journeys, collects console errors. Zero PAGEERROR required.
  4. READ the screenshots (vision) as a fresh user; fix what you see; re-run.
  5. Codex usability review only at milestone boundaries (screenshots referenced in prompt).
  Never claim a UI change done from code reading alone — the 2026-06-12 session found a server bug (deliverable gates), an invisible button, and a false-blocked display ONLY via screenshots.

## DB Schema (v4, 7 tables)

Schema version tracked in `PRAGMA user_version`. Migrations in `src/db.py`.

**users** — id, name, initials, token_hash, role (human/agent), calendar_upn (TEXT, NULL = not connected)

**spaces** — id, name, slug, color, icon, sort_order, sort_mode (manual/deal_stage), status (active/parked/done), version
- Seeded: Repuro (s-1), M&A (s-2)

**workstreams** — id, name, space_id→spaces, color, sort_order, status (active/parked/done), deal_codename, version
- Unique index on (space_id, name)

**deliverables** — id, workstream_id→workstreams, name, target_date, status (open/done/dropped), sort_order, comment, staging, source, deal, version

**tasks** — id, deliverable_id→deliverables, kind (workplan/followup/approval/agent_job/personal), text, detail, deadline, responsible, priority (high/med/low), status (open/in_progress/waiting/blocked/in_review/done), waiting_on_party, waiting_on_type (counterparty/advisor/investor/internal), next_chase_date, expected_back_by, last_touched_at, execution (me/together/agent_supervised/agent_auto), runner (local/cma/any), acceptance_criteria, claimed_by, claim_expires_at, evidence, prereqs(JSON), tags(JSON), links(JSON), deal, pinned_today, staging, sort_order, source, input_from (RD/FF), input_question, version, created_by, created_at, updated_at, done_at

**deal_mirror** — codename, stage, note, owner_mode (legacy/cockpit-owned), synced_at
- Read-only mirror from dealroom.db via `dealroom_sync.py`. Do not write directly.

**audit_log** — id, at, actor, action, entity, before(JSON), after(JSON)

**idempotency** — task_id+key (composite PK), response, at

## File Map

| Backend | Role |
|---------|------|
| `cockpit.py` | CLI: serve, init-db, token, sync, seed, status |
| `src/api.py` | FastAPI app — all CRUD endpoints, agent queue, MD import/export |
| `src/compute.py` | Pure logic — readiness, schedule risk, roll-ups. No DB imports. |
| `src/db.py` | SQLite layer — singleton conn, schema migrations, audit helper |
| `src/dealroom_sync.py` | Read-only pull from dealroom.db into deal_mirror |
| `src/mdio.py` | MD import/export (task-update, new-task blocks) |
| `src/models.py` | Enums (STATUSES, KINDS, PRIORITIES, RUNNERS) + ID helpers |

| Frontend (`static/`) | Role |
|-----------------------|------|
| `js/boot.js` | Bootloader — fetches state, mounts app |
| `js/app.jsx` | Main app, routing, sidebar, space/workstream rendering |
| `js/components.jsx` | Shared UI: FilterBar, TaskRow, DeliverableCard |
| `js/task-drawer.jsx` | Task detail side panel |
| `js/quick-add.jsx` | Quick-add modal |
| `js/activity.jsx` | Activity feed panel |
| `js/view-week.jsx` | Weekly meeting / My Week view |
| `js/view-overview.jsx` | Overview + hero dashboard |
| `js/view-board.jsx` | Kanban board |
| `js/view-table.jsx` | Table view with workstream grouping |
| `js/view-timeline.jsx` | Timeline / Gantt |
| `js/view-agents.jsx` | Agent queue view |
| `js/view-calendar.jsx` | Calendar week-grid view + connect flow |
| `src/calendar_graph.py` | MS Graph client — token cache, fetch_events, probe_upn, fake mode |
| `css/cockpit.css` | Main styles |
| `css/cockpit-views.css` | Per-view styles |
| `css/cockpit-extras.css` | Drawer, modal, palette styles |

React via Babel in-browser (no build step). Vendor libs in `static/vendor/`.

## Status
- M1 backend: ✅ 2026-06-11 — API on :8099, 75 tests, 14 deals mirrored, workplan seeded (staging)
- M2+M4 frontend: ✅ 2026-06-11 — SPA at `/` (Workstreams+Blockers, Today, Timeline, Agent Queue)
- M3 agent layer: ✅ superseded by **Agentic workflow v2** (below). /cockpit-pull + /cockpit-push RETIRED 2026-07-05 (targeted the diverged :8099).
- M5 hosting: live on Fly.io via suite/Dockerfile — served at `/cockpit/`
- **Agentic workflow v2.1: ✅ 2026-07-05, deployed v2.1.16** — adds inline artifact previews (md/pdf/png in the review card; Office → PDF; `POST /api/agent/upload-preview`, live-claimant-gated) and the **curated playbook** (learnings table: runner candidates → human adopt/dismiss in Agents view, cap 40, rides with every queue fetch; `POST /api/agent/learning` + `/api/learning/{id}/decide`). X-Remote-User trust is opt-in via `COCKPIT_TRUSTED_PROXY` (set in suite/fly.toml). Spec §10.
- **Agentic workflow v2: ✅ 2026-07-05, deployed v2.1.15** — spec `ai/SPEC-agentic-workflow.md`. One queue (cockpit prod), one runner (`/repuro:loop`, plugin v0.3.0, scheduled task `RepuroAgentLoop` logon+13:00 → `CLAUDE_COWORK/scripts/run-repuro-loop.ps1`), one review surface (Agents view: Needs your review / Waiting on you / Running / Queue). Closed loop: request-changes re-queues WITH feedback (`review_round`/`review_feedback` in `/api/agent/queue`); agent questions → `POST /api/agent/block` → inline answer (`POST /api/task/{id}/answer`) → re-queue; reject flips `execution→me` (loop-safe); claim enforces prereq readiness server-side; agents enqueue via `POST /api/agent/task` (AC mandatory). TASKS.md [AGENT] queue killed — cockpit is the only agent queue.
- Server: auto-starts at logon (Startup `RepuroCockpit.cmd` → `start_cockpit.ps1`); manual: run the ps1
- **Multi-user personal cockpit: ✅ 2026-07-15** — the two-founder hardcode is gone. `/api/state` carries `users` (humans directory) + `lanes` (`users.represents`-derived, e.g. `rd→RC`); every owner picker / person column / meeting column renders from it (me-first). Identity = login: sidebar shows the principal, non-admins are always themselves, the person switch is admin-only. **Server-enforced agent scoping**: non-admin humans receive ONLY agent-execution tasks they created + learnings of their own lane (`_scrub_foreign_agent_tasks`); admins (md) see all. Lane bar in Agents view is admin-only and data-driven. `POST /api/admin/user` accepts `role: agent` + `represents` (new runner lanes = data, no code); `PATCH /api/admin/user/{uid}` supports `name`/`initials`. Onboarding a member: create user (login = Caddy basic-auth user, team with module perms) + optional agent user for their lane. Meeting view (`week` module) renders N person columns from the team-visible scope.
- **Calendar module v1: 🔄 in-progress 2026-07-09** — `src/calendar_graph.py` (MS Graph client-credentials, in-memory cache, fake mode), `GET /api/calendar/events`, `POST /api/calendar/connect`, week-grid UI (`view-calendar.jsx`), Calendar tab in the Cockpit-overview right column (WeekView, embedded via view-overview). Migration 14: `users.calendar_upn`. Azure setup: `ai/CALENDAR-SETUP.md`.
