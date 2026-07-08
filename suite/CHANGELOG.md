# Repuro Suite — Changelog

Format: one entry per prod deploy. Group changes by module, then by feature. Bump `suite/VERSION` on each entry.

---

## v2.1.27 — 2026-07-08

### Investor Room — week lifecycle v2 (Roman's model: static dated weeks + dynamic draft)
- **Dated snapshot URLs**: published weeks live at `/investor/<YYMMDD>`
  (`/investor/260702`); `GET /{ref_date}` route, legacy `?week=` still works.
- **Universal week switcher** — SAME control for investor and admin on all
  published/archived/holding views (server-rendered, English date labels,
  `(live)` marker); investors self-serve navigate the archive. Holding page
  now carries the switcher instead of dead-ending.
- **Week-scoped inline edits**: publish freezes edits into the snapshot and
  CLEARS the live table — next week's draft starts clean from templates
  (kills the 02/07-edits-override-07/07 bug class).
- **Draft toolbar**: shows "Investors see: <week|NOTHING (holding page)>";
  switcher options server-rendered; navigation made RELATIVE (`./260702`) —
  the old `location='/?week='` landed on the suite landing page behind the
  `/investor` Caddy prefix.
- Tests: +8 lifecycle tests (40 green in test_investor_view.py).
- Prod data: cleared the 4 stale 02-Jul inline edits from the live draft
  (preserved inside the 2026-07-02 publication).

## v2.1.26 — 2026-07-08

### Investor Room — draft/publish workflow + 07-Jul weekly content (aef2c61)
- Auth-aware `GET /`: admin sees the live draft with a toolbar
  (publish/unpublish/week selector); the investor user sees the published
  snapshot or a holding page. Publish snapshots templates + inline edits
  into a publication row (denylist scan, auto-archive of the previous week);
  frozen edits injected as `__FROZEN_EDITS` — published pages make no live
  API calls. Schema v3 migration; 33 new tests.
- Weekly content 07 Jul 2026 (Fox/Mantis DD status, Mouse LOI, decisions).
- Volume check before this deploy: `/data/investor.db` live with data
  (WAL-persisted inline edits), served by prod, litestream-replicated since
  v2.1.22 — investor mode needed no infra change, code ships with the image.

### Suite — Research module (static)
- `/research/` static route (Caddy `file_server`, no-cache) serving
  `suite/static/research/` — first artifact: Com2Med ownership map.
  Behind suite basic auth; investor user remains confined to `/investor/*`.
- Landing page card added.

## v2.1.25 — 2026-07-08

### Cockpit — meeting/overview content rules + interaction bug fixes (suite-fix batch)
- **Meeting/Week views exclude agent tasks** (`execution === "agent"`): agent
  work lives in the Agents view; Meeting daily/weekly and My Week person lists
  show human tasks only.
- **Agent Queue respec** → "Agents — waiting on you": shows only agent tasks
  in review or blocked with a question (up to 5), instead of suggested queue
  candidates. Blocked = amber "Waiting on your answer", in review = red
  "Needs review".
- **Date-ascending sort** in Meeting + My Week lists (decisions, waiting,
  due-today, per-deliverable and standalone tasks): earlier dates on top,
  undated last.
- **+1d silent failure fixed — two root causes**: (1) `addDays()` formatted
  via `toISOString()` (UTC): east of UTC the +1 day collapsed back to the
  same date — a deterministic no-op in Berlin; now formats local
  (`localISO`, also applied to the last-Monday cutoff in Meeting).
  (2) Stale-version 409 after reorders (reorder bumps every task's version
  server-side) reverted the bump silently; quick actions (due bump,
  checkmark, waiting chips) now retry once with the server's current version
  read from the 409 body (`detail.current.version` — wire shape verified
  live). Rich editor saves deliberately do NOT auto-retry: that would
  silently clobber a concurrent edit (Flo/agent) — they keep the conflict
  toast + reload.
- **Task reorder sticks**: optimistic `sortOrder` stamping + immediate
  rerender (no snap-back), rollback to server truth if the reorder PATCH
  fails, and Table view + deliverable drawer sort all task lists by
  `sortOrder`. New pytest: reorder persists through `/api/state`.
- **Agents badge** counts blocked ("waiting on you") agent tasks, not just
  in_review — matches the new AgentQueue card.
- **Agent exclusion completed across Meeting/Week internals**: deal deadline
  bars, "completed since Monday", due-today/next-10-days deliverable pickers
  no longer count agent-only work (Codex sweep findings).
- **Done/old deliverables no longer linger**: Timeline hides done/dropped
  (and all-tasks-done) deliverables; Table view greys them out but keeps them
  findable for archiving (fixes "DD Kick-off looks weird" class).

### Dealroom — Next (Cockpit) sidebar section
- New "Next (Cockpit)" section under Process Artifacts surfacing upcoming
  cockpit deliverables per deal (`sections/next-deliverables.js`); degrades
  to a quiet note when no same-origin Cockpit API exists (static export).

## v2.1.24 — 2026-07-07

### Cockpit — Admin tab fix + frontend contract tests
- Admin nav click bounced back to Cockpit: hash validator rejected tabs not
  in NAV; `_isValidTab()` now accepts `admin` for admins. Missing `settings`
  icon glyph → `ops` gear; breadcrumb fixed.
- New `tests/test_frontend_contracts.py` (runs in pytest): routable-tab vs
  validator consistency (fails on the pre-fix code), tab/hash map symmetry,
  Icon-glyph existence, bundle registration order, full Babel bundle compile.

## v2.1.23 — 2026-07-07

### Cockpit + Suite — Teams with per-module read/write permissions (SPEC-teams v2)
- **Teams carry permissions** (supersedes v2.1.22 profiles as the carrier):
  per-module rw/ro map per team, strongest membership wins; MD = admin team
  with implicit full rights on all modules; user can be in many teams.
- **Suite-wide enforcement**: Caddy `forward_auth` gates `/allex/` and
  `/deals/` against cockpit team permissions, method-aware (read-only teams
  can GET, not POST). `/investor/` deliberately excluded (Strada shared cred
  stays Caddy-confined).
- **Workstream-team assignment**: workstream visible only to its assigned
  teams' members (unassigned = visible to all — opt-in scoping);
  `all_teams` god-view override (RD).
- **Admin view** (new, admin-only): manage users (create → token shown once),
  teams (module permission matrix), memberships, workstream assignments.
- Fail-closed hardening: teamless non-legacy users get nothing; state payload
  bounded by module perms (no workstreams perm = no task tree).
- Migration v13 (behavior-preserving: rd/ff seeded into MD, no workstream
  assignments). 143 pytest green (35 access tests), JSX bundle compile-checked.

---

## v2.1.22 — 2026-07-07

### Cockpit — Multi-user access control (t-403)
- **Role profiles** (`owner` / `advisor` / `viewer`): module-level nav gating +
  read-only mode, per SPEC-multi-user-access. rd/ff backfilled as `owner` —
  behavior unchanged; agents untouched.
- **Per-workstream access whitelists** (Option A, private-by-default): non-owner
  humans see only explicitly shared workstreams; deliverables/tasks cascade.
- Server-side enforcement: `read_only_guard` 403s all mutation endpoints; new
  owner-only `POST /api/admin/user` (token shown once) and
  `PATCH /api/workstream/{wid}/access`.
- UI: nav filtered by profile, disallowed-hash redirect, view-only banner,
  quick-add/task-drawer/add-buttons in read-only mode.
- DB migration v11→v12 (additive). 129 pytest green (21 new in test_access.py),
  JSX bundle compile-checked.

### Cockpit — contract-audit hardening (2026-07-06 review)
- SSE broadcast snapshot iteration; rollback-on-error handlers (no half-written
  transactions leaking into the next request's commit); preview path traversal
  containment; reorder version bump; tolerant task JSON fields; atomic init_db.
- SSE client in boot.js: live cross-user/agent refresh without reload.
- dealroom_sync never drops cockpit-owned mirror rows; prod deps pinned (~=).

### Suite — backup hardening
- litestream replicates investor.db; entrypoint restores missing DBs from S3
  before replication starts (fresh volume can no longer overwrite backups
  with empty DBs).

---

## v2.1.20 — 2026-07-06

### Cockpit — Agents view v2 (three views)
- **Inbox / Queue / Playbook sub-navigation** replaces the single scroll
  (SPEC-agents-view-v2, Opus-reviewed): Inbox = reviews → agent questions →
  subordinate lessons strip; Queue = running (lease-staleness chip) + compact
  single-line rows + "+ new agent task" + recently-completed tail; Playbook =
  rules only. Setup FAQ moved to a "?" header overlay.
- Sticky tabs (land on Inbox only when something blocks; never auto-switch);
  all badges follow the lane filter (incl. learnings); redo review cards show
  the Round-N badge AND the sent-back feedback text.
- Verified per spec §7b: 108 pytest, bundle compile, seeded e2e 0 pageerrors,
  two context-free verifier agents (code + visual) PASS on all 10 ACs after
  2 fix rounds (lane-filtered learnings, feedback render).

---

## v2.1.19 — 2026-07-06

### Investor Room — codex-gate fixes on the v16 port (/suite-fix run)
- 4 individual deal scorecards: total row now "Total Score (out of 40)" with a
  plain number (29/34/31/27), matching the overview comparison table
- ACT 1 Decision 2 cost bullet: "Notary, structuring = 23 K€" → 15 K€
  (reconciles with the dd-costs detail table: notary 11 + structuring 4)
- Codex commercial review on the assembled page: revise → ship
  (`boardroom/ai/codex-reviews/2026-07-06-investor-v16-*`, untracked)

---

## v2.1.18 — 2026-07-06

### Login-loop incident — ACTUAL root causes (supersedes the v2.1.17 analysis)
Two independent bugs, both shipped/exposed by the 05.07 deploy:

1. **Cockpit principal rejected all browser traffic through Caddy**
   (`cockpit/src/api.py`): the agentic-v2 rewrite nuked `X-Remote-User` on ANY
   `Authorization` header — but browsers behind Caddy necessarily send
   `Authorization: Basic ...` (the Caddy login itself) and Caddy forwards it
   upstream alongside the `X-Remote-User` it sets. Every `/api/state` via the
   proxy → 401 → the UI fell back to its token prompt (a dead end on prod) and
   trapped the user. Fix: only a **Bearer** Authorization marks a direct
   caller. Regression tests added (Basic+header → 200, Bearer+header → 401).
2. **UI fetch() calls relied on Chrome replaying basic-auth credentials**,
   which current Chrome no longer does for background fetches (navigations
   still carry them). Fix: `window.fetch` wrapper forcing
   `credentials:'include'` in cockpit boot.js, investor shell-bottom.html,
   allex dashboard.html (dealroom has no fetch sites). Cockpit boot.js also
   now re-tries the basic-auth path every login-loop round and clears stale
   tokens — a bad token can never permanently trap a user again.

The v2.1.17 "Caddy 2.11.4 placeholder regression" analysis was **wrong** — an
artifact of testing with a debug user that existed only in Caddy, so backends
correctly rejected it as unknown. Verified via echo-backend probe: Caddy header
injection works on both 2.10 and 2.11. The `caddy:2.10-alpine` pin stays
(pinning > floating tag), but it fixed nothing.

## v2.1.17 — 2026-07-06

### Suite — Caddy version pin (analysis superseded by v2.1.18)
- Pin `caddy:2.10-alpine` instead of floating `caddy:2-alpine`. Shipped under a
  wrong root-cause theory for the login loop — see v2.1.18. Pin kept for
  build reproducibility.

### Investor Room — v16 content + model-corrected Lion/Wolf
- Ships the v16 template port (done 05.07 evening session: Cat/Mouse reorder,
  scorecard re-source, S&U layout, provider fixes — see ISSUES.md Resolved).
- Portfolio table Lion EV/multiple 4.8/5.9x → **3.7/5.6x** (Golmed model v15),
  Wolf 5.2/5.1x → **4.3/5.4x** (KVG model v5) — aligned with dealroom.db
  overrides synced from the 05.07 model sweep.

### Investor Room — v16 content + model-corrected Lion/Wolf
- Ships the v16 template port (done 05.07 evening session: Cat/Mouse reorder,
  scorecard re-source, S&U layout, provider fixes — see ISSUES.md Resolved).
- Portfolio table Lion EV/multiple 4.8/5.9x → **3.7/5.6x** (Golmed model v15),
  Wolf 5.2/5.1x → **4.3/5.4x** (KVG model v5) — aligned with dealroom.db
  overrides synced from the 05.07 model sweep.

---

## v2.1.16 — 2026-07-05

### Cockpit — Artifact previews + curated agent playbook
- **Inline artifact review**: agents upload the produced artifact as a preview
  (`POST /api/agent/upload-preview/{id}`, live-claimant-gated); the review card
  renders `.md` inline, `.pdf` embedded, images directly — the reviewer sees the
  actual output, never just a file path. Office artifacts are exported to PDF
  before upload (runner rule). `previewUrl` now respects the `/cockpit` mount
  (was silently broken on prod).
- **Curated playbook (learning loop)**: runners submit one-line candidate lessons
  (`POST /api/agent/learning`, deduped, ≤300 chars); humans adopt/edit/dismiss in
  the Agents view ("Proposed lessons" / "Playbook"); active rules (hard cap 40)
  ride with every `/api/agent/queue` fetch. Nothing enters the playbook without
  a human click.
- **Security hardening (Codex, 4 rounds → PASS)**: human preview door human-only;
  agent door requires live claim; `.html` previews removed (stored-XSS), legacy
  served as download; markdown renderer escapes quotes (href breakout);
  `X-Remote-User` trust opt-in via `COCKPIT_TRUSTED_PROXY` on both `principal()`
  and the SSE endpoint; promote re-runs dedupe on final text.
- 107 pytest; plugin v0.4.0 (`preview` + `lesson` commands, playbook-aware loop).

---

## v2.1.15 — 2026-07-05

### Cockpit — Agentic workflow v2 (closed review loop, SPEC-agentic-workflow)
- **Review→rework loop closed end-to-end**: agent queue returns `review_round`/`review_feedback`/`evidence` + prereq readiness (send-backs arrive WITH the feedback); SSE broadcast on claim/result/block so cards move live in the browser
- **New agent endpoints**: `POST /api/agent/task` (enqueue from any Claude session, AC enforced), `POST /api/agent/block/{id}` (park on a question for the human)
- **New human endpoint**: `POST /api/task/{id}/answer` — inline answer re-opens a blocked task for the next runner pass
- **Reject is loop-safe**: flips `execution → me` so an unattended runner never re-executes a rejected task
- **Claim enforces readiness** server-side (409 on unmet hard prereqs); readiness resolver mirrors canonical state exactly (dropped deliverables + children-done deliverables count as cleared)
- **UI**: "Waiting on you" section with inline answer box; Round-N badge + feedback line on send-back queue cards; FAQ updated to `/repuro:loop` flow
- **DDL fix**: fresh DBs were created without migration-10 columns (`preview_url`, `review_feedback`, `review_round`)
- 102 pytest passing; Codex review PASS (r3) after 2 fix rounds
- Plugin v0.3.0 (`pavlovs/repuro-cockpit-skills`): `/repuro:loop`, `/repuro:add`, block support, feedback-aware `/repuro:run`

### Cockpit — earlier this cycle
- CSS unification (design-system variables, button consolidation); `+1d` fast path; cache-bust vendor scripts + no-cache middleware (blank-page fix)

### Boardroom — Investor view v15
- English number convention throughout; S&U rebuilt; funnel/timeline updates; scorecard horizontal rows; monolith split into `templates/` (per-deal + per-act, assembled in api.py)

### Infrastructure
- Caddy no-cache headers + `/diag`; fly.toml: `auto_stop_machines=suspend`, `min_machines_running=1` (always-on — prevents blank-page on cold start); `DEALROOM_REQUIRE_DB=1`

---

## v2.1.11 — 2026-06-17

### Infrastructure — Deploy consolidation
- **Per-module Dockerfiles/fly.tomls removed** — `cockpit/Dockerfile`, `cockpit/fly.toml`, `lead-pipeline/Dockerfile`, `lead-pipeline/fly.toml` deleted; `suite/` is now the single deploy artefact
- **MODULES.md** — module registry added to `suite/` documenting ports, routes, DB paths, and adding-a-module convention
- **Suite landing page** — `suite/static/index.html` replaced with `Repuro Suite.html` (renamed)
- **lead-pipeline/ai/CHANGELOG.md removed** — changelog consolidated into `suite/CHANGELOG.md`

### Cockpit — UI fixes
- Static index.html, app.jsx, boot.js, quick-add.jsx, task-drawer.jsx, view-week.jsx updated (follow-on fixes from v2.1.9 space architecture)

---

## v2.1.10 — 2026-06-17

### Cockpit — Prod crash fixes
- **FileResponse import restored** — missing import caused 500 on first load after v2.1.9 deploy
- **Relative paths + cache-bust on boot.js** — absolute `/static/` paths broke under `/cockpit/` prefix; cache-bust param added to force reload

---

## v2.1.9 — 2026-06-17

### Cockpit — Space architecture + UX polish
- **Spaces entity** — new `spaces` table with two seeded spaces (Repuro, M&A). Workstreams grouped under spaces with `space_id` FK. Schema v3→v4 migration with deal-linked projects auto-assigned to M&A
- **Visual hierarchy** — teal space banners as top-level separators, elevated workstream bands (card-style, colored left border), toned-down deliverable cards (indented, no shadow). Consistent across Table, Timeline, Board views
- **Deal filtering** — dead/on_hold deals hidden by default, "+N inactive" toggle to reveal. Pre-LOI deals collapsed, LOI+ expanded. Computed visibility from deal_mirror stage
- **Deal stage editing** — clickable stage chips on M&A workstreams open modal to change deal stage. `PATCH /api/deal/{codename}` endpoint
- **Deliverable drawer** — side panel (like task drawer) with inline editing for name, target, status, workstream, task list, delete button. Replaces modal popup
- **Deal name normalization** — dealroom_sync strips legacy suffixes (e.g., "Fox — DD" → "Fox"), auto-aligns workstream names with codenames
- **Delete deliverable** — `DELETE /api/deliverable/{did}` endpoint; tasks become standalone

---

## v2.1.8 — 2026-06-16

### Cockpit — suite-fix session (30+ issues)
- **Cockpit/My Week merge** — Cockpit landing shows hero + WeekView (Due Today, Tomorrow, Deliverables Due 10 Days, Agent Queue); KPI cards removed. "My Week" renamed to "Weekly Meeting" and renders MeetingView (agenda-structured meeting prep)
- **Activity log** — ActivityPanel slide-out with grouped-by-date entries, TaskHistory in task drawer, /api/activity endpoint
- **UX overhaul** — hash-based URL routing, HTML5 drag-and-drop on WeekView + Workstreams, shared FilterBar component, collapsible filters, blocked task nesting, Agent view redesign with larger cards
- **Input Required From** — input_from/input_question columns, quick-add toggle, task-drawer editing, overview Blockers section
- **Cleanup** — dead meetingMode toggle removed, Relations view unloaded, stale suite files deleted

### Dealroom
- Removed LIVE badge, CLI references, DEALRoom casing fixed, fetch() interceptor replaced with relative URLs

### ALLEX
- Removed LIVE badge, fetch() interceptor replaced with relative URLs

---

## v2.1.7 — 2026-06-15

### Cockpit
- **Meeting view rewrite** — reordered sections (Focus → Blockers & decisions → Completed), all deliverables and tasks editable inline via WeekRow, hover ✎ edit and + task buttons, completed section collapsed by default, larger fonts for meeting readability
- **Deliverables layout** — new default Workstreams tab with RD/FF two-column split, progress bars per deliverable, expandable task lists, inline editing

### Infrastructure
- **Suite DB path env vars** — explicit `PIPELINE_DB_PATH`, `DEALROOM_DB_PATH`, `COCKPIT_DB` environment variables in supervisord.conf so Fly volume mount works correctly
- **Entrypoint permissions** — create + chown app-local data dirs (`allex/data/output`, `dealroom/data`) in addition to `/data` volume

### Fixed
- **Smart-quote compilation errors** — Unicode curly quotes in boot.js/view-agents.jsx replaced with straight quotes; Babel compiles clean

---

## v2.1.5 — 2026-06-15

### Changed
- **Suite navigation fix** — removed separate topbar (double-header). App-switcher links now embedded in each component's existing chrome (Cockpit sidebar, ALLEX side-panel, DEALRoom header bar)
- **DEALRoom light theme** — dark sidebar/header converted to white/Inter design matching Cockpit and ALLEX
- **Unified design tokens** — Inter font, #0891B2 accent, consistent border-radius and spacing across all 3 apps

---

## v2.1.4 — 2026-06-15

### Infrastructure
- **Repuro Suite migration** — ALLEX now served at `/allex/` under the unified `repuro-suite` Fly.io app. Suite topbar with navigation to Cockpit, ALLEX, and DEALRoom. fly.toml, pull-db.sh, push-db.sh updated.
- **BASE_PATH routing** — dashboard.py injects `window.BASE_PATH` for sub-path fetch interception

### Pipeline hardening (BA9 retro)
- **`prepare-manual` CLI command** — new pre-enrich step scrapes impressum and extracts legal entity name for MANUAL-source records (`qa.py`). Run before `enrich` for any MANUAL cohort.
- **Non-DE company filter** — `.at`/`.ch`/`.nl`/etc TLD and 4-digit PLZ detection skips OpenRegister (DE-only API), saves credits
- **OpenRegister address caching** — `_openregister_autocomplete()` now stores `registered_address` from API response → new `openregister_address` DB column
- **SCRAPE_MAX_CHARS 2500 → 5000** — impressum content (addresses, GF, HRB) at page bottom no longer truncated
- **`backfill-impressum --force`** — overwrites existing `impressum_name` values (default still fills empty only)

### Dashboard
- **"Gesellschafter neu suchen" always visible** — re-search button shown in all records, not just review mode
- **QA name fix expanded** — now fixes names missing legal form suffix, not just domain-as-name
- **Design refresh** — neutral grays, larger radii, shared.css integration

---

## v2.1.2 — 2026-05-29

### Added
- **Gesellschafter Notiz** — Freitext-Feld unter Gesellschaft-Sektion für manuelle Anmerkungen
- **Favicon** — ALLEX-Logo im Browser-Tab
- **gesellschafter_field Auto-Derive** — wird automatisch aus Anrede abgeleitet beim Setzen von Ansprechpartner

### Fixed
- **gesellschafter_field zählt als Pflichtfeld** — leeres Feld wird jetzt in "Fehlende Felder" und Brief-Status angezeigt
- **DB-Migration Backfill** — gesellschafter_field wird beim Start aus Anrede befüllt (582 Bestandsrecords)
- **8 fehlende Vornamen** in Gender-Erkennung ergänzt (dennis, fabian, ibrahim, lutz, marco, mathias, niklas, pascal)

---

## v2.1.0 — 2026-05-28

### Kategorisierung
- Neue Kategorie-Codes: DEA, INT, SER_PLA_1, SER_PLA_2, SER_MAI, SER_ITS
- Per-Kategorie Defaults für Leistung 1/2, Mehrwerte, Gruppe 1/2
- Neue editierbare Felder: **gesellschafter_field**, **gruppe_1**, **gruppe_2** (Template-Variablen)
- Ingest unterstützt erweiterte Spalten aus Quell-Excel

### Lead-Liste
- Editierbare **Prio-Spalte** (Prio 1 / Prio 2 Varianten / Excluded)
- Eigener **Batch-Dropdown-Filter**
- Toggle **"Prio 2 anzeigen"** (localStorage-persistent)
- **Pagination** mit 100 Records pro Seite

### Batch-Übersicht
- Neuer Tab: Status von Gesellschaft / Stammdaten / Briefvorbereitung als Ampel-Pills
- Lücken-Filter und Summary-Statistiken
- Klick navigiert direkt zum Review

### BA9
- 51 neue Records hinzugefügt, BATCH_ORDER aktualisiert

---

## v2.0.3 — 2026-05-11

### Added
- **Druckfreigabe** — "Freigeben" heißt jetzt "Druckfreigabe". Einmal freigegeben, kann die Freigabe per Klick wieder zurückgenommen werden
- **Neue Filter** — drei neue Filter-Optionen: Gesellschaft / Stammdaten / Briefvorbereitung Freigabe ausstehend
- **Automatischer Wiedereinstieg** — Dashboard merkt sich den zuletzt bearbeiteten Datensatz und Batch, springt beim Neuladen automatisch zurück
- **Was ist neu** — Popup zeigt Änderungen bei jeder neuen Version

### Changed
- **Tab-Reihenfolge & Umbenennung** — Sidebar jetzt: Lead-Liste → Review (war "Batch") → Export → Follow-Up → Drop-Off → Änderungslog
- **Export-Ansicht vereinfacht** — bereits versendete Records ausgeblendet; nur 3 Buttons: Export PDF / Export Excel / Export Briefmarken (Abschicken + Checkboxen entfernt)
- **Feld-Zuordnung überarbeitet** — Ansprechpartner, Anrede und Salutation von Briefvorbereitung nach Stammdaten verschoben; Geschäftsführer → Brief von Stammdaten nach Gesellschaft verschoben
- **Fehlende-Felder-Validierung** — Stammdaten/Briefvorbereitung-Status-Karten spiegeln die neue Feldzuordnung korrekt wider (inkl. Anrede-Mismatch-Prüfung in Stammdaten)

### Fixed
- Druckfreigabe über Lead-Liste aktualisiert jetzt auch den Prüfstatus aller Sektionen
- #ID bleibt nach Änderungen an Datensätzen stabil (wurde vorher nach Speichern zurückgesetzt)
- Drop-off Ansicht: Statistiken jetzt batch-bezogen, Duplicate-Handling korrigiert
- Herzkönig Medizintechnik GmbH (Klass D) Druckfreigabe zurückgesetzt — Klass D darf nicht freigegeben sein

### Other
- Worktree-Konsolidierung: Entwicklung läuft jetzt in einem einzelnen Ordner
- Dev-Version wird nach Deploy automatisch hochgezählt

---

## v2.0.2 — 2026-05-06

### Added
- VS Code-style toggle sidebar navigation: icon rail + collapsible 180px panel, auto-collapse on section select
- 'Batch abschicken' button — mark approved records as sent (`outreach_sent_at`)
- Excel Serienbrief export (`/api/export-leadliste`) in Lead-Liste view
- 'Kontaktiert in BA...' badge on approached records in queue
- Company unique identifier (#ID) for cross-reference
- Undo button for field edits (M27 follow-on)
- Follow-Up view: inline-editable table for sent letters — status, FU1/FU2 dates, comments, email/phone per record
- Freigabe hard-gate: block approval when required letter fields are missing (was soft confirm dialog)
- `run-all` now runs 7 stages (filter→scrape→classify→enrich→normalize→backfill-leistung→backfill-compliments) with `--from-stage` flag

### Fixed
- Freigabe button disabled when Pflichtfelder missing (detail view + Lead-Liste checkbox); confirm-bypass removed; tooltip shows which fields are incomplete
- PDF export logo centered (was left-aligned)
- Banner: description moved right of name; arrow alignment fixed
- Queue: show all klass A/B records regardless of filter_pass; grey out approached records
- White squares, skip button removal, description truncation
- K1 trailing punctuation stripped (comma, semicolon)
- Activity log + collapse bugs
- Alt+E shortcut: now switches to Review mode before opening Export
- Orphaned CSS cleanup (`--ink-1` undefined var, dead `.subnav .icon-btn` rules)
- Cohort tracker BA1-7: sent count now from `outreach_sent_at` (was looking for non-existent "sent" status); columns match actual outreach statuses
- Cohorts subnav hint text updated to match actual columns

### Changed
- Logo switched to transparent version (`ALLEX_logo_transparent.png`)
- Auth removed from dev (prod auth restored on merge)
- Fly.io: `auto_stop_machines=true`, `min_machines_running=0` (cost optimization)

### Removed
- `CHANGELOG.md` at repo root (consolidated into `suite/CHANGELOG.md`)
- M33 plan file (completed)

---

## v2.0-alpha.3 — 2026-05-03

**M27 + M30 complete.**

### Added (M27 — Activity Tracker)
- `activity_log` table in `pipeline.db` (id/domain/actor/field/old_value/new_value/changed_at + 2 indexes)
- `log_activity()` in `db.py`: per-field change logging; called from PATCH handler
- PATCH handler: reads old values before UPDATE, logs each changed field with actor identity
- `GET /api/activity`: real endpoint (replaces stub), supports `?domain=` and `?limit=` filters

### Added (M30 — Analyze Mode)
- Funnel/Classes/Bottlenecks views now respond to BA selector: when a BA is selected, views compute from `getFilteredRows()` instead of server-injected global data
- Empty states added to Funnel and Classes views when filtered set is empty
- Tweaks panel: actor selector (Roman / Flo) — persists to `allex_actor` in localStorage, updates sidebar avatar

### Backend (BP3)
- `pipeline.py run-all`: sequential filter → scrape → classify → enrich with per-stage timing output (was "not yet implemented")

---

## v2.0-alpha.1 — 2026-05-03 (Cloud)

**M32 complete: dashboard now live at `https://repuro-suite.fly.dev/allex/`** (migrated from standalone `allex-pipeline.fly.dev` on 2026-06-15).

### Infrastructure (M32)
- Fly.io deployment: Dockerfile, `fly.toml` (fra region, 512MB, persistent volume at `/data`)
- GitHub Actions auto-deploy: push to `main` → `flyctl deploy --remote-only` via `FLY_API_TOKEN`
- `scripts/push-db.sh` / `scripts/pull-db.sh`: sync `pipeline.db` between local and Fly volume
- `_ThreadedHTTPServer`: concurrent request handling (replaces single-threaded stdlib server)
- Empty-DB cold-start: server starts cleanly on Fly before DB is uploaded (creates empty SQLite, serves empty dashboard)
- `src/data/region_mapping.json`: 486 cities extracted from Excel — no runtime Excel dependency in container

### Not in this release (deferred, require Anthropic API key)
- SDK migration (classify/backfill/enrich via `anthropic` SDK)
- Job runner backend (`POST /api/run-job`, `GET /api/job-status`)
- Pipeline trigger UI panel in dashboard

---

## v2.0-alpha — 2026-04-30

**ALPHA phase started. Flo (co-founder) now actively editing DB via dashboard.**

### Added
- Version string in LIVE badge: badge now shows `LIVE · v2.0-alpha` (single badge, version always visible)
- `--dev` CLI flag: runs on separate port with `[DEV] LIVE · v2.0-alpha` badge, safe to test without disrupting Flo
- `dev` git branch: all development work happens here; merge to `main` for prod deploy

### Fixed
- `full_name` (Firmenname Briefkopf) added to `_WRITEBACK_FIELDS` — Flo's edits now save
- Export PDF scoped to currently selected Batch only (`r.briefaktion === selectedBA`)
- Navigation counter mismatch: rec-prev / rec-next / btn-skip now use `.filter(matchesQueueFilter)`
- Chip click handler now calls `renderRecord()` and auto-selects first in-filter record
- Server bind changed from `localhost` → `0.0.0.0` for LAN access (Flo on `http://10.70.102.138:8080`)

### Infrastructure
- SQLite stays on DELETE journal mode (not WAL) — OneDrive cannot sync WAL's 3-file set safely
- Concurrent write safety: `PRAGMA busy_timeout=10000` (10s) handles overlapping saves
- No auth layer yet — LAN-only deployment is the security boundary for now

---

## v2.0 — 2026-04-29

Dashboard v2 promoted to default (M29). Letter review UI feature-complete (M28). 85 letter-ready records in BA8.

---

## v1.x (pre-v2)

See `lead-pipeline/ai/ROADMAP.md` Delivered section (M11–M23) for full history.
