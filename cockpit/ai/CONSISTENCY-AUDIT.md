# Cockpit Consistency Audit — 2026-06-18

## Summary
17 inconsistencies found (5 high, 7 medium, 5 low)

Note: `view-meeting.jsx` does not exist as a separate file. MeetingView and WeekView both live in `view-week.jsx`. The audit treats them as distinct views by function.

---

## Findings

### 1. Meeting header is a styled card; Overview hero is plain flex — severity: HIGH
- **Where**: view-week.jsx (MeetingView) vs view-overview.jsx (OverviewView)
- **What**: MeetingView wraps its header in `<div className="mtg-header card">` — a white box with border, shadow, and 18px/22px padding. The Overview's hero (`ov-hero`) is a bare flex row with no card wrapper, no border, no background. Structurally equivalent "page intro" sections look completely different.
- **Fix**: Either wrap `ov-hero` in a `card` div, or strip `card` from `mtg-header` and apply same bare treatment.

### 2. Space bands render differently in Table vs Timeline — severity: HIGH
- **Where**: view-table.jsx vs view-timeline.jsx
- **What**: In both views, `space-band` gets the brand-blue filled pill styling (`.space-band { background: var(--brand); color: #fff; ... }`). Correct and consistent there. But in Timeline (view-timeline.jsx line 111), the space-band also needs `width: LABELW + totalW` inline style because it's inside an absolutely-positioned gantt grid — there is no equivalent constraint in table view. However, in the gantt the `+ Workstream` add-button that exists on every space-band in TableView is entirely missing. Two views of the same structural element have different interactivity.
- **Fix**: Add the `+ Workstream` button to the Timeline's space-band rendering, or accept that Timeline is read-only and add a CSS comment to that effect.

### 3. Edit pencil (✎) visibility trigger is inconsistent — severity: HIGH
- **Where**: cockpit-extras.css, cockpit-views.css, view-week.jsx, view-table.jsx
- **What**: Three different hover-reveal patterns coexist:
  - `.deliv-h:hover .deliv-edit { opacity: 1; }` — triggered by hovering the deliverable row
  - `.trow:hover .tc-edit { opacity: 1; }` — triggered by hovering the task row
  - `.mtg .wk-deliv-head:hover .deliv-edit { opacity: 1; }` — only fires in Meeting mode (`.mtg` scope)
  In WeekView (non-meeting tab), `.wk-deliv-head:hover .deliv-edit` has NO opacity reveal rule — the pencil is hidden at opacity .3 and never appears on hover unless inside `.mtg`. WeekView deliverable rows have non-functional edit buttons.
- **Fix**: Add `.wk-deliv-head:hover .deliv-edit { opacity: 1; }` to cockpit-views.css (outside the `.mtg` scope).

### 4. "Add task" affordance: inline input in Table, modal dispatch in Week/Meeting, ghost button in DeliverableView — severity: HIGH
- **Where**: view-table.jsx (InlineAddTaskTable), view-week.jsx (InlineAddTask + wk-add-task button), view-week.jsx (DeliverableView ghost button)
- **What**: Three different patterns for the same action (create task inside a deliverable):
  1. Table: `InlineAddTaskTable` — a fade-in input row at bottom of deliverable, Enter to submit
  2. Week deliverable expansion: a `wk-add-task` dashed-border button that fires `cockpit:quickadd` event (opens modal)
  3. DeliverableView column: a `btn ghost` styled button that fires `cockpit:quickadd`
  The inline input (Table) requires no context switch. The others open a full modal. The experience for the same action differs by view.
- **Fix**: Standardize on one pattern. Inline is lower friction; extend `InlineAddTask` to Week's deliverable expansion view.

### 5. Click on task name opens drawer in Table/Week, but clicking sub-items in Meeting opens task via openTask — severity: HIGH
- **Where**: view-table.jsx (TRow), view-week.jsx (WeekRow, MeetingView mtg-sub)
- **What**: All views correctly call `openTask(t.id)` on task name click — that part is consistent. However, in MeetingView's "Completed" section (mtg-done-row), clicking a completed task also calls `openTask`, which is correct. But in the "Blockers & decisions" section, the `inputNeededMtg` tasks render a `wkrow` without a `chk` button (unlike WeekRow), creating an asymmetric layout within the same card.
- **Fix**: Render `inputNeededMtg` tasks via `<WeekRow>` component for layout consistency.

---

### 6. Workstream band font sizes differ between views — severity: MEDIUM
- **Where**: cockpit-views.css (.ws-name), view-timeline.jsx (.gantt-band-name)
- **What**: In Table view, workstream name uses `.ws-name { font-size: 18px; font-weight: 800 }`. In Timeline, the gantt-band renders the workstream name with `.gantt-band-name { font-size: 14px; font-weight: 800 }`. The gantt band is visually the same structural element — a full-width workstream separator — but 4px smaller.
- **Fix**: Either use `.ws-name` class inside `gantt-band`, or align `gantt-band-name` to 18px.

### 7. Section label styling: mtg-sec-label vs sec-head vs wk-grp — severity: MEDIUM
- **Where**: cockpit.css (.sec-head), cockpit-views.css (.wk-grp, .mtg-sec-label)
- **What**: Three separate section-label patterns serve the same semantic purpose (label a group of items):
  - `.sec-head h2`: 16px, font-weight 700, margin 8px 0 14px — used in Overview
  - `.wk-grp`: 10px, uppercase, letter-spacing .8px, color faint/purple/rose — used in Week card columns
  - `.mtg-sec-label`: 12px, uppercase, letter-spacing .5px, color ink-2 — used in Meeting between-section labels
  Same concept, three different visual weights. Meeting section labels look like table headers, not section titles.
- **Fix**: Consolidate `mtg-sec-label` to reuse `.sec-head` or a new shared `.view-sec-label` class.

### 8. Card column header (.wk-h) includes person name in Week/Meeting but plain text in standalone cards — severity: MEDIUM
- **Where**: view-week.jsx (WeekView cards, MeetingView person columns), view-week.jsx (AgentQueue, standalone deliverable cards)
- **What**: Person column cards use `.wk-h` with `<Avatar> {name}` pattern. But AgentQueue (line 491), the "Deliverables Due Today" card (line 154), and the WeekView "Deliverables Due Next 10 Days" card (line 592) all use `.wk-h` with plain text — no avatar, no consistent icon treatment. The class name suggests it's the "week column header" but it's being reused as a generic card header, causing visual inconsistency.
- **Fix**: Create `.card-h` (already defined in cockpit-views.css) usage for non-person cards, and reserve `.wk-h` for person columns.

### 9. Filter bars: topbar toggle controls Table filters, inline FilterBar controls Timeline filters — severity: MEDIUM
- **Where**: app.jsx (topbar Filter button), view-timeline.jsx (FilterBar inside view)
- **What**: Workstreams/Table filters are controlled by a topbar button (`tb-filter`) that toggles `wsFiltersOpen`. Timeline uses `FilterBar` component rendered inside the view itself at line 66, with its own `filtersOpen` state. Functionally equivalent controls live in different places. A user looking for filters in Timeline would check the topbar first and find nothing.
- **Fix**: Move Timeline's FilterBar into the topbar or add a topbar passthrough for timeline filter state (same pattern as Table).

### 10. Deliverable due date display: fdate vs fdateShort mixed in same view — severity: MEDIUM
- **Where**: view-week.jsx (WeekView, MeetingView), view-table.jsx
- **What**: `fdate()` returns `DD/MM` format. `fdateShort()` returns `DD.MM.` format. Both are used in the same context (deliverable due date next to a deliverable name):
  - `wk-deliv-head`: uses `fdate(d.target)` (view-week.jsx line 202, 606)
  - `mtg-deliv`: uses `fdateShort` for the loi-item (line 132)
  - `deliv-h` in Table: uses `fdate(d.target)` (view-table.jsx line 407)
  Within Meeting, `fdate` is used for deliverable blocks but `fdateShort` for the LOI bar — the slash vs dot format switches within the same page.
- **Fix**: Pick one format for due dates across the whole app. `DD/MM` (`fdate`) is used more consistently; swap LOI bar to `fdate`.

### 11. "Add deliverable" button has inline hardcoded styles — severity: MEDIUM
- **Where**: view-table.jsx lines 292-294, 331-332
- **What**: The `+ Workstream` button and the `+ deliverable` button on ws-band both use `style={{ ... }}` inline with hardcoded `border: "1px dashed var(--line)"`, `color: "var(--brand)"`, `fontSize: 12`, etc. The `.ws-band-target` class in cockpit-extras.css already defines exactly these styles. The inline styles partially duplicate and in one case override the class (`color: "var(--muted)"` on the `+ deliverable` button vs. `color: #475569` in the class).
- **Fix**: Remove inline styles from both buttons; rely on `.ws-band-target`. For the `+ deliverable` muted variant, add a `.ws-band-target.muted` modifier class.

### 12. DeliverableDropdown uses fully inline styles, not CSS classes — severity: MEDIUM
- **Where**: task-drawer.jsx (DeliverableDropdown component, lines 40-107)
- **What**: The dropdown is built entirely with JS style objects (`triggerStyle`, `dropdownStyle`, `groupHeaderStyle`, `delivRowStyle`). These hardcode colors (`#0891B2`), font strings, and spacing values that exist as CSS variables. The rest of the drawer uses CSS classes. The dropdown is also written in `React.createElement` rather than JSX, making it inconsistent with every other component.
- **Fix**: Convert to JSX with CSS classes. Add `.dd-trigger`, `.dd-menu`, `.dd-group-h`, `.dd-option` classes to cockpit-extras.css using CSS variable tokens.

---

### 13. `.tb-undo` class used for both Undo, Filter, and Activity buttons — severity: LOW
- **Where**: app.jsx (topbar), cockpit-extras.css
- **What**: Three semantically different buttons — Undo, Activity log, and Filter — all share the `tb-undo` class. The Filter button then adds `tb-filter` to override. `.tb-undo` as a name implies a single purpose. If styles diverge further the class will need splitting anyway.
- **Fix**: Rename to `.tb-btn` as the base class; keep `.tb-filter` and `.tb-undo` as modifier classes.

### 14. Hardcoded hex colors in cockpit-extras.css where CSS variables exist — severity: LOW
- **Where**: cockpit-extras.css (multiple locations)
- **What**: The following hardcoded values appear in cockpit-extras.css despite equivalent CSS variables being defined in cockpit.css:
  - `#0891B2` (17 occurrences) → should be `var(--brand)`
  - `#E11D48` (9 occurrences) → should be `var(--rose)`
  - `#64748b`, `#94a3b8`, `#475569` → should be `var(--muted)` or `var(--ink-2)` or `var(--faint)`
  - `'Inter', system-ui, sans-serif` repeated inline → should be `var(--font)`
  The design system in cockpit.css defines tokens specifically to avoid this. cockpit-extras.css was written after and bypasses them.
- **Fix**: Global find-replace in cockpit-extras.css for the listed hex values → CSS variables. Medium effort, zero behavioral change.

### 15. Caret/expand icon inconsistency: CSS class vs inline SVG — severity: LOW
- **Where**: view-timeline.jsx vs view-table.jsx, view-week.jsx
- **What**: Expand/collapse carets all use `<Icon name="chevron" size={N} />` inside a `<span className="caret [open]">`. The CSS rotates the span 90deg when `.open`. This is consistent across Table, Week, and Timeline. However, the Timeline's gantt-label caret uses the same pattern but adds `.gantt-label .caret` scoped CSS that re-declares `margin-right: -2px` — a layout tweak that is gantt-specific but leaks into the shared `.caret` class scope.
- **Fix**: Move the gantt-specific caret margin to `.gantt-label > .caret` (add `>` direct child combinator).

### 16. Missing icon for "alert" name in Icon component — severity: LOW
- **Where**: components.jsx (Icon function, line 154-176), view-week.jsx (WeekView line 638, MeetingView line 266)
- **What**: `<Icon name="alert" size={14} />` is used in WeekView's "Needs your input" section header and in MeetingView's "Input needed" group label. The Icon component does not have an `"alert"` key in its path map — it falls through to `p = ""`, rendering an empty SVG. The icon silently disappears.
- **Fix**: Add `alert: "M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"` to the Icon path map.

### 17. WeekView "Deliverables Due Next 10 Days" card has inconsistent inner padding vs other wk-col cards — severity: LOW
- **Where**: view-week.jsx (WeekView, lines 591-630)
- **What**: Person column cards (`wk-col`) get padding from `.wk-col { padding-bottom: 12px }` and inner rows via `.wkrow`. The standalone "Deliverables Due Next 10 Days" card uses `wk-deliv-block` with `padding: 8px 10px` (from CSS). But `.wkrow` uses `padding: 11px var(--card-pad)` where `--card-pad` defaults to 16px. The deliverable block rows are 6px narrower horizontally than task rows in the person columns, creating a visible left-edge misalignment when both card types appear on screen.
- **Fix**: Change `wk-deliv-block` padding to `8px var(--card-pad)` or add a modifier to match the card-pad value.
