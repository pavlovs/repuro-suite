# Lead-Pipeline Dashboard — Frontend Redesign Prompt (v2)

> Feed this prompt to Claude Code with the `frontend-design` skill active.
> Run from: `C:\Users\X1\Documents\OneDrive - Kamu Kapital\Dokumente - Kamu Kapital\CLAUDE_REPURO\lead-pipeline\`

---

## The Prompt

```
Build a complete redesign of the lead-pipeline dashboard at src/pipeline/templates/dashboard.html.

## Step 0 — Read the current implementation FIRST

Before writing any code, read these files to understand the current state:
1. `src/pipeline/templates/dashboard.html` — the full current dashboard (2,600+ lines, single-file HTML/CSS/JS)
2. `src/pipeline/dashboard.py` — the backend server (routes, API endpoints, data injection)
3. `src/pipeline/settings.py` — pipeline constants and config

Understand the existing: tab structure, side panel behavior, write-back fields, Briefaktion filter, PDF export flow, and data shape. The redesign must preserve ALL existing functionality while improving the UX.

## What this is

A deal-sourcing command center for a German healthcare M&A platform (Repuro). One power user (Roman) uses this daily to:
- Monitor a pipeline of 500–2000 companies moving through qualification stages
- Review AI classifications (A/B/C/D/E/S) and override them
- Prepare personalized outreach letters (Serienbriefe) for A/B targets
- Track outreach status: sent → follow-up 1 → follow-up 2 → contact → meeting → deal
- Identify blockers: missing emails, unclassified records, pending approvals

The backend is Python + SQLite. Dashboard receives a single JSON blob with all records. No framework — vanilla HTML/CSS/JS. Keep it that way.

## Aesthetic direction: "Bloomberg Terminal meets Notion"

Dense, data-rich, zero decoration. The feel of a trading terminal — every pixel earns its space — but with Notion's clarity and whitespace discipline. Think: information architecture, not illustration.

**Typography**: JetBrains Mono for data/numbers, Inter for labels and headings (exception to the "no Inter" rule — this IS a data tool, readability > character). Monospace numbers prevent column jitter in tables.

**Color system** (CSS custom properties, dark + light mode):
- Background: `--bg-primary: #0f1117` (dark mode default), `#fafbfc` (light)
- Surface: `--surface: #1a1d27`, `#ffffff`
- Text: `--text-primary: #e4e7eb`, `#1a1a2e`
- Accent (action/CTA): `--accent: #3b82f6` (blue)
- Classification palette (MUST keep — users have muscle memory):
  - A (Platform): `#22c55e` green
  - B (Add-on): `#3b82f6` blue
  - C (Unclear): `#eab308` yellow
  - D (No-fit): `#6b7280` gray (not red — D is passive, not alarming)
  - E (Special): `#a855f7` purple
  - S (Subsidiary/PE): `#f43f5e` rose
- Status colors: sent=#3b82f6, followup=#eab308, contact=#22c55e, meeting=#8b5cf6, deal=#10b981

**Layout**: Sticky left sidebar (48px collapsed / 200px expanded) for navigation instead of horizontal tabs. Main content area with a 12-column CSS Grid. KPI strip always visible at top (horizontal scroll on overflow). No card borders — use background color shifts and spacing to separate sections.

**The ONE thing someone should remember**: The pipeline funnel visualization. Not a boring bar chart — a horizontal Sankey-style flow showing records moving from Ingested → Filtered → Classified → A/B/C/D/E/S → Outreach stages. Animated on load (CSS only, respect prefers-reduced-motion). This replaces the current 6 KPI cards with something that tells a story.

## What to explicitly AVOID
- Purple-on-white gradient backgrounds (AI slop)
- Rounded card grids with even spacing (generic SaaS look)
- Shadows heavier than 0 1px 2px rgba(0,0,0,0.05)
- Any decorative SVG illustrations or icons-for-the-sake-of-icons
- Inline SVG for legends — use CSS border-radius spans
- Stats above tables (put them inline or below)
- Horizontal tabs at the top (use sidebar navigation)

## Technical constraints

1. **Single HTML file** — all CSS and JS embedded. No build step. No npm.
2. **Data injection**: Backend replaces `__DATA_JSON__` placeholder with JSON blob. In serve mode, JS fetches `/api/data` on load.
3. **Existing API endpoints** (don't change these):
   - GET `/api/data` — all records
   - PATCH `/api/company/{domain}` — update single record
   - PATCH `/api/batch` — bulk update
   - POST `/api/compliment/{domain}` — regenerate AI greeting
   - POST `/api/export-pdf` — generate Serienbriefe PDF
   - POST `/api/ingest-domain` — add new domain
4. **Side panel**: Keep the right-sliding detail panel. Left sub-panel (company data + edit form), right sub-panel (website iframe / letter preview). But make it feel like a Notion page, not a cramped form.
5. **Write-back fields** (whitelist): klass, outreach_status, outreach_sent_at, approved_for_sendout, region, anrede, owner_name, leistung_text, compliment_draft, gf_email, and others defined in dashboard.py.
6. **Briefaktion filter**: Must persist across all views. Currently a dropdown — could become a persistent chip bar or sidebar filter.
7. **76 database columns**: Not all shown. Key visible columns in lead table: name, domain, klass, services_score, ma_count, gesellschafter_age, region, outreach_status, briefaktion, gf_email, approved_for_sendout.

## Five views (replacing current tabs)

1. **Command Center** (replaces Performance)
   - Sankey funnel (the hero element)
   - Source quality heatmap (source × klass, color intensity = count)
   - Briefaktion cohort comparison (small multiples: one mini-funnel per BA)
   - Response rate trend (if outreach_sent_at timestamps allow)

2. **Prep Queue** (replaces Current BA Prep + Requires Attention — merge them)
   - Three columns, Kanban-style:
     - "Needs Classification" (C records)
     - "Needs Email" (A/B without gf_email)
     - "Needs Approval" (S records pending override)
   - Each card: company name, domain, klass badge, services_score, one-line reasoning
   - Click card → side panel opens
   - Counter badges on each column header

3. **Pipeline** (replaces Lead Table)
   - Dense table, sortable + filterable
   - Inline klass badges (clickable to reclassify)
   - Readiness indicator: horizontal progress bar (fields filled / required fields for that klass)
   - Bulk select (checkbox column) + bulk action bar (change status, assign BA, approve)
   - Keyboard navigation: j/k for row up/down, Enter to open side panel, Esc to close

4. **Outreach** (replaces Outreach Tracker)
   - Timeline view: vertical timeline grouped by week
   - Each entry: company name + status badge + days since last action
   - Filter by status (sent, FU1, FU2, contact, meeting, deal, hold, declined)
   - "Due for follow-up" section at top (records where FU1/FU2 date has passed)

5. **Export** (new — currently a button, deserves its own view)
   - Preview grid of approved records with letter template preview
   - Drag to reorder (print sequence)
   - One-click PDF generation
   - Stats: total approved, by region, by BA

## Responsive behavior
- Primary: desktop (1440px+)
- Sidebar collapses to icon-only at <1200px
- Tables get horizontal scroll at <1024px
- Side panel becomes full-screen modal at <768px

## Accessibility
- All interactive elements keyboard-navigable
- ARIA labels on klass badges and status indicators
- Color is never the ONLY signal — pair with text/icon
- prefers-reduced-motion: skip all animations
- prefers-color-scheme: auto-switch dark/light
```

---

## How to use this prompt

1. Open Claude Code in `lead-pipeline/` directory
2. Ensure `frontend-design` skill is available
3. Paste the prompt above (everything between the triple backticks)
4. Claude will read the existing `dashboard.html`, understand the data model, and produce the redesign
5. Test with `python pipeline.py dashboard --serve` on localhost:8080

## What this prompt does differently from v1

| v1 (implicit/generic) | v2 (this version) |
|---|---|
| No aesthetic direction | "Bloomberg Terminal meets Notion" — specific reference |
| Default colors | CSS custom properties + dark/light mode + preserved classification palette |
| Horizontal tabs | Sidebar navigation |
| 6 KPI cards | Sankey funnel as hero element |
| Separate Prep + Attention tabs | Merged into Kanban-style Prep Queue |
| No bulk actions | Bulk select + action bar in Pipeline view |
| No keyboard navigation | j/k/Enter/Esc shortcuts |
| Button-only export | Dedicated Export view with preview grid |
| No explicit anti-patterns | 7 specific things to avoid |
| No accessibility spec | Keyboard nav, ARIA, motion preference, color pairing |
