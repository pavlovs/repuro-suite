# Dashboard v2 — Design Spec

> Source: Claude Design handoff bundle (2026-04-27), chat1 + chat2 transcripts, FRONTEND_REDESIGN_PROMPT_v2.md
> Prototype files: `docs/superpowers/specs/design-prototype/` (index.html, app.js, data.js, styles-v3.css)

## Problem

The current dashboard (2,946-line single-file `dashboard.html`) works but feels like a dev draft — not a tool a power user wants to live in daily. Four gaps:

1. **No product feel** — raw layout, mixed typography, no visual hierarchy
2. **Letter production invisible** — the journey from raw data → PDF export isn't visible or reviewable
3. **Flat attention model** — one "Requires Attention" list instead of per-record checklists showing exactly what blocks export
4. **No audit trail** — field changes aren't logged; no way to know who changed what, or to undo

## Design Direction

**"Command center, assembly line."** Two modes: Review (work) and Analyze (measure). Neutral palette, signal-only color (red = critical, amber = needs action, green = done). Single typeface (Inter). Maximum density. Every pixel earns its space.

### Design System (from prototype)

```
Background:    #f7f6f3 (warm off-white)
Surface:       #ffffff
Surface-2:     #f1efea (subtle bg for inputs, cards)
Surface-3:     #e8e6e0
Line:          #e5e3dd (hairline dividers)

Ink:           #14131a (primary text)
Ink-2:         #4a4750 (secondary)
Ink-3:         #807d86 (tertiary/labels)
Ink-4:         #b0acb3 (disabled/placeholder)

Accent:        #1f3a5f (deep calm blue — sidebar active, CTA, focus rings)
Accent-soft:   #e6ecf3

Signal-block:  #c43a3a / #fbe9e9 (critical missing — address)
Signal-warn:   #c08a00 / #fbf3dc (needs action — 1-3 fields missing)
Signal-ok:     #2f7a4f / #e7f1ea (ready / done)

Font:          Inter (all UI), tabular-nums for figures
Sizes:         10/11/12/13/14/18/22/28 (tight scale)
```

### Layout

- **Sidebar**: 56px icon-only, two modes (Review checkmark, Analyze chart), brand badge (AX), user avatar (RD)
- **Top bar**: 48px, mode title + subtitle, Briefaktion selector (persistent), tweaks toggle
- **Sub-nav**: 40px strip below top bar, mode-specific tabs
- **Main**: fills remaining viewport, no scroll on container (scroll inside views)

### Navigation Structure

```
Review (Assembly Line)
├── Lead-Liste       — queue (360px left) + record editor (right) + letter preview
├── Drop-off         — per-BA stage-by-stage attrition with reason buckets
└── Activity Log     — chronological field-change feed with actor + kind filters

Analyze (Performance)
├── Funnel           — Ingest → Export bar chart (animated)
├── Cohorts          — Sent → Reply → Meeting → Deal per BA
├── Klassen          — A/B/C/D/E distribution
└── Bottlenecks      — top 3 action-prompting blockers
```

## Milestone Decomposition

### M27: Activity Tracker Backend

**Goal:** Start logging every manual field change with actor, timestamp, old/new values. Zero frontend changes.

**Scope:**
- New `activity_log` table in pipeline.db:
  ```sql
  CREATE TABLE IF NOT EXISTS activity_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      domain TEXT NOT NULL,
      field TEXT NOT NULL,
      old_value TEXT,
      new_value TEXT,
      actor TEXT NOT NULL,         -- 'claude' | 'roman' | 'flo'
      kind TEXT NOT NULL,          -- 'edit' | 'gen' | 'regen' | 'enrich' | 'approve' | 'system'
      timestamp TEXT NOT NULL,     -- ISO 8601
      FOREIGN KEY (domain) REFERENCES company_records(domain)
  );
  CREATE INDEX IF NOT EXISTS idx_activity_domain ON activity_log(domain);
  CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_log(timestamp DESC);
  CREATE INDEX IF NOT EXISTS idx_activity_actor ON activity_log(actor);
  ```
- Hook into `dashboard.py` PATCH handler: before writing each field, read old value, write log row after successful update
- Actor detection: dashboard API receives actor from client (header or query param `?actor=roman`); pipeline CLI stages use `actor='claude'`
- New API endpoint: `GET /api/activity?limit=100&actor=&domain=` — returns activity log entries, paginated
- Migration: add table via `ensure_schema()` (forward-only, idempotent)

**Does NOT include:**
- Frontend activity log view (that's M28 — Review > Activity Log sub-tab)
- Undo/revert functionality (log-only for now; revert = manual PATCH with old_value from log)
- Logging pipeline CLI bulk operations (only dashboard manual edits + compliment regen)

**Definition of Done:**
- `activity_log` table created on startup
- Every PATCH /api/company/{domain} write logs old→new per changed field
- POST /api/compliment/{domain} logs compliment regeneration
- GET /api/activity returns log entries with filters
- Tests: log creation, actor detection, filter queries
- No existing functionality broken

---

### M28: Dashboard v2 Shell + Review Mode

**Goal:** Replace `dashboard.html` with the v2 design. Port the entire Review mode (Lead-Liste, Drop-off, Activity Log views). Preserve all existing write-back functionality.

**Scope:**

#### Shell (layout + navigation)
- Replace 5-tab horizontal nav with sidebar (2 modes) + sub-nav strip
- Design system CSS (custom properties, typography, all component styles from prototype)
- Briefaktion selector in top bar (persistent across views, replaces current dropdown)
- Tweaks panel (queue sort, funnel style)
- All existing API endpoints preserved — no backend route changes

#### Review > Lead-Liste
- **Queue (360px left panel):**
  - Shows A/B records for selected Briefaktion
  - Each item: company name, domain, klass badge, missing-field count with severity color
  - Sort: "closest to ready" (fewest missing first) / "most blocked" (most missing first)
  - Search: filter by name/domain
  - Active item: left blue bar indicator + soft blue bg

- **Record editor (right panel):**
  - Header: klass badge, company name, domain, region, record counter, prev/next nav
  - "Was fehlt" hero section: checklist derived from REQUIRED_LETTER_FIELDS in check_letter.py (currently 10 fields — do not hardcode count, read from source)
    - Each item: icon (done=green check, block=red exclamation, warn=amber dot), label, hint, "Bearbeiten →" action
    - When all done: green "Bereit zum Export" banner
  - Stammdaten section: Firma, Klasse (select), Region, Anrede (select), Geschäftsführer
  - Postadresse section: Straße, PLZ, Stadt — red border on missing when blocking
  - Brief-Inhalt section: Compliment textarea (AI-generiert tag), GF E-Mail
  - All fields write-back via existing PATCH API
  - Source hints on fields (· Impressum, · ORBIS, · AI-generiert)

- **Right preview panel (split with record editor):**
  - Tab bar: Brief-Vorschau / Website
  - Brief-Vorschau: rendered letter template with field substitution
    - Missing fields highlighted red: `[Straße fehlt]`
    - Filled fields highlighted green
    - Full Serienbrief layout: sender, recipient, date, subject, body with compliment, signature block
  - Website: mock preview with company initials, domain bar, "Neu öffnen ↗" button
    - Real iframe where X-Frame-Options allows; static mock otherwise

- **KPI bar (3 cards above queue):**
  - Blockiert (red): records with 4+ missing fields
  - In Bearbeitung (amber): records with 1-3 missing fields
  - Bereit zum Export (green): records with 0 missing fields + approved

- **Bottom action bar:**
  - Save (⌘S), Skip (→)
  - Dynamic: "X offene Felder bearbeiten" (warn) or "Bereit · Zum Export hinzufügen" (primary)

#### Review > Drop-off
- Per-BA stage-by-stage attrition view
- 7 stages: Ingest → Hard Filter → Scrape → Classify → Ownership Gate → Enrichment → Approval
- Each stage card: step number, stage name, subtitle, passed/dropped counts with percentages
- Progress bar: width = passed/total ratio
- Reason buckets below each stage with dot + label + mini-bar + count
- Top stats: total ingested, total dropped (amber), approved (green)
- **Data source:** computed from pipeline.db — group by pipeline_stage + filter_reason + klass for the selected BA

#### Review > Activity Log
- Chronological feed of field changes (newest first)
- Each row: timestamp, actor (dot + name), kind badge, company name, field (monospace code), old→new diff
- Actor filter: Alle / Nur Claude / Nur manuell
- Top stats: total changes today, Claude count, manual count
- **Data source:** GET /api/activity (from M27)
- Kind badge colors: gen/regen = warm gold, enrich = sage green, edit = blue, approve = green, system = gray

#### Ported existing functionality (must not regress)
- Compliment regeneration (POST /api/compliment/{domain})
- Ownership review workflow (Resolve/Pass/Exclude) — move to record editor "Was fehlt" item
- Batch approve (approved_for_sendout toggle)
- Domain ingest (POST /api/ingest-domain)
- PDF export trigger (POST /api/export-pdf)
- Region mapping (embedded at build time via __REGION_MAPPING_JSON__)

**Does NOT include:**
- Analyze mode views (M29)
- Export view (deferred — current button-based export preserved)
- Outreach timeline view (deferred)
- Dark mode (deferred)
- Keyboard navigation j/k/Enter/Esc (deferred)

**Definition of Done:**
- dashboard.html fully replaced with v2 layout
- All Review sub-tabs render correctly with real pipeline.db data
- All existing PATCH/POST endpoints work from the new UI
- Letter preview renders with real field values and missing-field highlights
- Drop-off computed from real DB data per BA
- Activity Log displays from M27's API
- Ownership review actions accessible from record editor
- 480 existing tests still pass
- Visual check: matches prototype design system (colors, spacing, typography)

---

### M29: Analyze Mode + Polish

**Goal:** Port all Analyze views, wire up real data computation, polish edge cases.

**Scope:**

#### Analyze > Funnel
- Horizontal bar chart: Ingested → Filter pass → Scraped → Classified → A+B qualified → Ready to export
- Each row: stage label + subtitle, bar (width = percentage), count, percentage
- Animated bar growth on load (CSS `scaleX`, `animation-delay` staggered)
- Data: computed from pipeline.db stage counts across all BAs (or filtered by selected BA)

#### Analyze > Cohorts
- Table: Briefaktion | Sent | Reply (+ %) | Meeting (+ %) | Deal (+ %)
- Data: computed from outreach_status + outreach_sent_at + followup fields
- One row per BA cohort

#### Analyze > Klassen
- 5-cell grid: A/B/C/D/E, each showing letter, count, description, proportion bar
- Data: `SELECT klass, COUNT(*) FROM company_records GROUP BY klass`

#### Analyze > Bottlenecks
- 3 action-prompting cards: Unklassifiziert (count), Fehlende E-Mail (count), Fehlende Adresse (count)
- Each card: count (with severity color), label, action link text
- Data: computed from field NULL checks on A/B records

#### Polish
- Responsive: sidebar collapse at <1200px, horizontal scroll on tables at <1024px
- Tweaks panel: queue sort wired to real sort, funnel style toggle (bar/stepped)
- Briefaktion selector: populated from real BA values in DB, filters all views
- Edge cases: empty states (no records for BA, no activity yet), long company names, missing fields
- prefers-reduced-motion: disable all animations

**Does NOT include:**
- Dark mode
- Keyboard navigation
- Export view (separate future milestone)
- Outreach timeline view (separate future milestone)

**Definition of Done:**
- All 4 Analyze sub-tabs render with real DB data
- Funnel animation works, respects prefers-reduced-motion
- Cohort data computed correctly from outreach fields
- Bottleneck counts match pipeline.db state
- Briefaktion filter works across all views in both modes
- Responsive behavior at 3 breakpoints
- Full visual match with prototype design system

## Resolved Questions

1. **Undo via activity log** — deferred. M27 is log-only. Revert UX in a future milestone.
2. **Actor identity** — localStorage toggle in sidebar footer (click avatar → Roman / Flo). Sent as `?actor=` param on PATCH requests.
3. **Export view** — deferred to M30. Button-based export preserved in M28.
4. **Outreach timeline** — deferred to M31. Cohort table in M29 covers analytical need.

## Reference Files

Lead-pipeline project root: `CLAUDE_REPURO/lead-pipeline/`

Design prototype (from Claude Design handoff): `lead-pipeline/docs/superpowers/specs/design-prototype/` — contains index.html, app.js, styles-v3.css, data.js

Current implementation (to be replaced): dashboard.html template in src/pipeline/templates/, backend server dashboard.py and letter validation check_letter.py in src/pipeline/, config settings.py in src/config/ — all under the lead-pipeline project root.
