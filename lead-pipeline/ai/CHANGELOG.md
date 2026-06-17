# ALLEX Dashboard — Changelog

Format: one entry per prod deploy. Group changes by feature, not individual items. Bump `DASHBOARD_VERSION` in `dashboard.py` on each entry.

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
- `CHANGELOG.md` at repo root (consolidated into `ai/CHANGELOG.md`)
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

See `ROADMAP.md` Delivered section (M11–M23) for full history.
