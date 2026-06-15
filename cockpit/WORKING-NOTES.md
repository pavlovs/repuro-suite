# Cockpit UX Redesign — Working Notes

## Spec
- Default view = judgment/action. Detailed view = admin.
- Surface what needs attention. Push metadata into drilldowns.
- Color = meaning only: red=blocked, amber=soon, green=on-track, purple=waiting, teal=accent.
- Calmer, more whitespace, fewer competing elements.

## File map
- `static/css/cockpit.css` — design system, shell, atoms
- `static/css/cockpit-views.css` — per-view styles (overview, board, week, table, relations, timeline)
- `static/css/cockpit-extras.css` — palette, quick-add, agents, drawer, toast, modal
- `static/js/components.jsx` — shared helpers, icons, model functions
- `static/js/view-week.jsx` — My Week + Meeting mode
- `static/js/view-overview.jsx` — Overview (Cockpit landing)
- `static/js/view-table.jsx` — Workstreams (table + deliverables view)
- `static/js/view-board.jsx` — Board (kanban) + TaskCard
- `static/js/view-timeline.jsx` — Timeline (gantt)
- `static/js/view-relations.jsx` — Relations (dependency graph)
- `static/js/view-agents.jsx` — Agents queue
- `static/js/app.jsx` — App shell, nav, routing
- `static/js/boot.js` — login, API, state mapping

## Priority order
1. My Week — main execution surface
2. Overview — morning operating view
3. Workstreams — execution tracking
4. Timeline — planning view
5. Relations — dependency resolution
6. Agents — agent task management

## Strategy
CSS-first approach: global calming (whitespace, reduced color weight, softer shadows) then per-view JSX restructuring.

## Current state
- [x] Backup created at static_backup/
- [x] All files read
- [x] CSS foundation changes — spacing, shadows, deal chips, section heads, progress bars
- [x] View 1: My Week — collapsible done, "Up next" rename, "Chase" trim, date label
- [x] View 2: Overview — greeting removed, KPI labels shortened, "Focus today" card added
- [x] View 3: Workstreams — "New deliverable" → subtle dashed button
- [x] View 4: Timeline — default filter changed to "dated"
- [x] View 5: Relations — waiting context box in side panel
- [x] View 6: Agents — hint bar simplified
- [x] Browser verification — 0 JS errors, all views render correctly (2026-06-15)
- [ ] Deploy
