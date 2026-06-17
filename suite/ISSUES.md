# Repuro Suite — Issues & Requests

Drop issues here. Format: `- [ ] description`.
Claude reads this when `/suite-fix` is invoked.

**Bugs & improvements** → implemented directly.
**Feature requests** → reviewed with Roman first, only built after approval.

---
## Bugs // Improvements

- [ ] DEFER - New Deal wiring: Cockpit "New Deal" should create in Dealroom (cross-app API). Deferred — needs infrastructure investigation next session
- [x] Agent Jobs should just be shown in Agent Queue — filtered execution="agent" tasks out of Workstreams table + WeekView Due Today/Tomorrow/focus; only show in AgentsView + AgentQueue widget — fixed 2026-06-17
- [x] Weekly Meeting should be called "Meeting" — nav label + meeting title renamed — fixed 2026-06-17
- [x] Weekly Meeting: "Daily/Weekly" switch jumps — removed all three stat badges (completed/need attention/deal deadlines) from meeting header — fixed 2026-06-17
- [x] Where does Flo see that I need input from him — added "Needs your input" card in WeekView (personal); added "Input needed" subsection in Meeting blockers — fixed 2026-06-17
- [x] Adding a Deliverable in Workstreams does not show in the pipeline — filter guard now skips deliverables with 0 tasks (empty deliverables always visible); also default to expanded — fixed 2026-06-17

Infrastructure — deferred (architecture change)
- [ ] DEFER - entrypoint.sh sed-injection of COCKPIT_BASE_PATH is fragile (breaks if source strings change or path has special chars). Replace with a /config.js endpoint in FastAPI that returns `window.COCKPIT_BASE="/cockpit"`, loaded via script tag. HTML files become immutable

---
## Feature Requests
> These are NOT auto-implemented. `/suite-fix` presents each one with a recommendation and waits for Roman's go/no-go.

- [ ] DEFER - Agents: "- **Start a session:** Open Claude Code in the `CLAUDE_REPURO` workspace and run `/agent-loop`. Claude picks up queued tasks in order, executes them, and reports results." --> Flo or other uses will not have this skill. Should we provide a build a custom github repo or something similar with cockpit skills required to use it.
- [ ] DEFER — Integration of calender with most important meetings of the week (ignoring daily standup in the morning) for Flo and Roman
- [ ] DEFER — Migrate ALLEX and DEALROOM HTTP layer to FastAPI — both use stdlib http.server with manual URL parsing, JSON serialization, auth (~300 lines of boilerplate each). FastAPI gives typed parsing, automatic 422 on bad input, OpenAPI docs. Split dashboard.py into data/routes/html during migration. Effort: L (2-3 days per app)

---
## Resolved

- [x] ?deal=Mantis routing — suite landing JS detects ?deal= param and redirects to /deals/?deal=X — fixed 2026-06-17
- [x] Input Required opens new window — removed showModal popup, inputFrom dropdown saves inline and question field appears immediately in drawer — fixed 2026-06-17
- [x] Weekly Meeting DAILY/WEEKLY toggle — Daily shows due-today per person + deliverables due today + shared blockers; Weekly unchanged — fixed 2026-06-17
- [x] Adding a Deliverable default date — default target date set to TODAY in QuickAdd — fixed 2026-06-17
- [x] Side drawer: can't edit task's deliverable or deliverable's workstream — added Deliverable dropdown to TaskDrawer; workstream dropdown already existed in DelivDrawer — fixed 2026-06-17
- [x] Cockpit/My Week merge — OverviewView embeds WeekView (hero + Due Today/Tomorrow/Deliverables/AgentQueue); KPI cards removed; "My Week" renamed to "Weekly Meeting" (renders MeetingView directly); dead meetingMode toggle cleaned up — fixed 2026-06-16
- [x] Version history + activity log — GET /api/activity endpoint, ActivityPanel slide-out in app header, TaskHistory section in task drawer — fixed 2026-06-16
- [x] Nested "blocked by" font style — prereq-name changed from 11.5px italic to 12px normal, slightly greyed out (#94a3b8) — fixed 2026-06-16
- [x] Remove "New deal (playbook)" button from Workstreams — removed button + onNewDeal prop + NewDeal state/render from app.jsx — fixed 2026-06-16
- [x] "Shared Blockers" / Relations view removed — nav entry, hash routing, badge, view rendering all cleaned up; Blockers card on Cockpit covers the use case — fixed 2026-06-16
- [x] Deliverable's relation to Workstreams is not editable yet — added workstream dropdown to editDeliv() modal, PATCH endpoint accepts workstream_id — fixed 2026-06-16
- [x] Adding a deliverable in Workstreams did not work — fixed deliverable creation flow, validated POST /api/deliverable endpoint + quick-add dispatch — fixed 2026-06-16
- [x] Blocked tasks grouped/nested in workstreams — "↳ blocked by: [task]" rows nested underneath in workstreams table — fixed 2026-06-16
- [x] Filter placement standardized + collapsible — shared FilterBar component in components.jsx, migrated workstreams + timeline — fixed 2026-06-16
- [x] URL routing per view — hash routing (#cockpit, #week, #workstreams, #timeline, #agents), browser back/forward works — fixed 2026-06-16
- [x] Agent task suggestions in My Week — AgentQueue component shows top 2 ready agent tasks sorted by priority+due — fixed 2026-06-16
- [x] Input Required From feature — input_from/input_question columns, quick-add toggle, task-drawer editing, overview Blockers section, WeekRow badge — fixed 2026-06-16
- [x] Replace fetch() interceptor with relative URLs — removed monkey-patch from both dashboard.py files, converted 28+ fetch calls — fixed 2026-06-16
- [x] Move all the resolved bugs down — reorganized ISSUES.md — fixed 2026-06-16
- [x] Drag and drop in My Week — DragList component with HTML5 native drag, sort_order column + /api/tasks/reorder endpoint — fixed 2026-06-16
- [x] My Week: Tomorrow next to Due Today — 2-column top layout — fixed 2026-06-16
- [x] "This week" renamed to "Deliverables Due next 10 Days" — full-width below Due Today/Tomorrow — fixed 2026-06-16
- [x] Drag & drop in Workstreams — added to TRow in table view — fixed 2026-06-16
- [x] Search bar ⌘K → Ctrl+K on Windows — fixed 2026-06-16
- [x] Focus today checkmark — added done toggle on overview focus items — fixed 2026-06-16
- [x] Red dot → "blocked" text label — ReadinessDot changed, removed from board view, moved after text in palette — fixed 2026-06-16
- [x] Task editing unified with deliverable editing — ✎ pencil button on task rows — fixed 2026-06-16
- [x] Deliverable due date column alignment — CSS margin-right on .wk-deliv-head .deliv-due — fixed 2026-06-16
- [x] Incomplete issue removed (Roman confirmed) — 2026-06-16
- [x] Slow checkmark in My Week — optimisticDone state with async rollback — fixed 2026-06-16
- [x] Overdue section removed — rolls into Due Today with red badge — fixed 2026-06-16
- [x] Filters collapsible in Workstreams + Timeline — Filter toggle with active count badge — fixed 2026-06-16
- [x] 0/3 counter removed from deliverables — fixed 2026-06-16
- [x] Agents view bigger cards + RC/FC handover — grid layout 480px min, HANDOVER_INITIALS map — fixed 2026-06-16
- [x] Agents how-to panel + queue position — collapsible instructions, position badges — fixed 2026-06-16
- [x] Login with Florian defaults to Florian's tasks — fixed 2026-06-16
- [x] Workstream name editable — ✎ button on ws-band — fixed 2026-06-16
- [x] Workstreams default to Table view — fixed 2026-06-16
- [x] All headers increased — fixed 2026-06-16
- [x] Workstream view defaults to "workstream" grouping — fixed 2026-06-16
- [x] Workstream counter removed — fixed 2026-06-16
- [x] Badge clutter reduced — TRow stripped to dot + text + owner + due — fixed 2026-06-16
- [x] Due date warning on deliverable creation — fixed 2026-06-16
- [x] Relations moved to bottom of nav — fixed 2026-06-16
- [x] Timeline filters sticky — fixed 2026-06-16
- [x] Agent View redesigned — independent cards with state badges — fixed 2026-06-16
- [x] Deliverable editing combined — single modal — fixed 2026-06-16
- [x] Deliverable task counter removed — fixed 2026-06-16
- [x] Status column removed from table view — fixed 2026-06-16
- [x] Priority filter added — fixed 2026-06-16
- [x] Workstreams collapse/expand all — fixed 2026-06-15
- [x] "Open Dealroom" links to suite dealroom — fixed 2026-06-15
- [x] Cockpit prompt()/alert() replaced with toast + modal — fixed 2026-06-15
- [x] Cockpit cold start blank screen — CSS spinner — fixed 2026-06-15
- [x] Cockpit CDN → local vendor — fixed 2026-06-15
- [x] Suite nav "return to Suite" — fixed 2026-06-15
- [x] Landing page hardcoded name — /api/whoami — fixed 2026-06-15
- [x] Health check — /healthz — fixed 2026-06-15
- [x] Container runs as root — appuser — fixed 2026-06-15
- [x] Supervisord start order — priorities — fixed 2026-06-15
- [x] SQLite WAL conditional — fixed 2026-06-15
- [x] busy_timeout 5000ms — fixed 2026-06-15
- [x] Dealroom read-only ATTACH — fixed 2026-06-15
- [x] Dealroom migration singleton — fixed 2026-06-15
- [x] Dealroom _read_json_body — fixed 2026-06-15
- [x] ALLEX alert() → showToast() — fixed 2026-06-15
- [x] Error response consistency — fixed 2026-06-15
- [x] Remove Cockpit classic.html — fixed 2026-06-15
- [x] Consolidate CSS color tokens — fixed 2026-06-15
- [x] Litestream backup for 3 SQLite DBs — fixed 2026-06-15
- [x] Unified QuickAdd — fixed 2026-06-15
- [x] My Week deliverable-centric workflow — fixed 2026-06-15
- [x] Split requirements.txt into prod/dev — fixed 2026-06-15
- [x] Visual density / separation — fixed 2026-06-15
- [x] Fox DD / pipeline ownership — fixed 2026-06-15
- [x] Smart quote compilation error — fixed 2026-06-15
- [x] Removed LIVE badge + DE language toggle from Dealroom — fixed 2026-06-15
- [x] Removed LIVE badge from ALLEX — fixed 2026-06-15
- [x] Removed CLI command references from Dealroom empty states — fixed 2026-06-15
- [x] Fixed "DEALRoom" → "Dealroom" casing — fixed 2026-06-15
- [x] Cleaned dev-facing cockpit login message — fixed 2026-06-15
- [x] Removed legacy suite files — fixed 2026-06-15
- [x] Fixed Florian name inconsistency — fixed 2026-06-15
