# M30: Analyze Mode + Polish — Implementation Plan

---

## Execution Results — 2026-05-03

**Delivered:**
- `renderAnalyzeFunnel()`: when `selectedBA` is set, uses `getFilteredRows()` for client-side computation instead of server-injected `DATA.funnel`; adds empty state message
- `renderAnalyzeClasses()`: when `selectedBA` is set, computes counts from `getFilteredRows()`; adds empty state message
- `renderAnalyzeBottlenecks()`: uses `getFilteredRows()` instead of `DATA.records` when `selectedBA` is set; `outreach` breakdown remains global (server-computed, no per-BA split)
- Tweaks panel — actor selector: Roman/Flo radio buttons added to `<div class="tweaks-body">`; clicking calls `setActor()` which persists to `allex_actor` in localStorage and updates sidebar avatar; active state initialized from localStorage on page load

**Diverged from spec:**
- Cohorts view: not implemented (no `outreach_cohort` field in current DB; deferred)
- `prefers-reduced-motion` CSS block: deferred (low priority, no user-facing animation issues reported)
- Debug mode toggle in tweaks: deferred

---

> **For agentic workers:** Use superpowers:subagent-driven-development to execute task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Analyze mode placeholders added in M28 with fully functional views backed by real pipeline.db data. Polish the full dashboard: BA selector filters all views, tweaks panel, empty states, prefers-reduced-motion.

**Prerequisite:** M29 (UX redesign) must be complete and v2 must be the default template.

**Target files:**
- `src/pipeline/templates/dashboard_v2.html` — all frontend changes
- `src/pipeline/dashboard.py` — add data computation helpers for Analyze views

**Test gate:** `python -m pytest tests/test_dashboard.py -q` must pass after every task.

---

## Scope (from ROADMAP.md)

| Area | What's needed |
|------|--------------|
| Funnel view | Per-stage pass/drop counts wired to real `_compute_dropoff()` data (already injected via `__DROPOFF_JSON__`) |
| Cohorts view | BA1–BA7 cohort pass/response rates from DB |
| Klassen view | A/B/C/D/E distribution chart from real `DATA.records` |
| Bottlenecks view | Which required fields are most commonly missing across the queue |
| BA selector | Filter switch in subnav applies to ALL views (Analyze + BA-Prep), not just BA-Prep |
| Tweaks panel | `#toggle-tweaks` opens a slide-in panel with: actor selector (Roman/Flo), sort order, debug mode toggle |
| Empty states | Every view/tab must show a helpful empty state when no records match the current filter |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` for all CSS transitions/animations |

---

## Tasks

### Task 0 — Funnel + Klassen views from real data

**Problem:** The Analyze tab currently shows placeholder content.

Wire `__DROPOFF_JSON__` (already injected) to the Funnel view bars. Each stage shows: stage name, passed count, dropped count, drop reasons (expandable).

Wire `DATA.records` to the Klassen distribution: count A/B/C/D/E/S, render as horizontal bar segments with counts.

**AC:**
- Funnel view renders real stage data (not mock numbers)
- Klassen bar shows real distribution
- 22 tests pass

### Task 1 — Bottlenecks + Cohorts views

**Bottlenecks:** For all records with `klass IN ('A','B')`, compute per-field missing frequency. Show top 8 most-missing fields as a ranked list with count + percentage.

**Cohorts:** Group records by `outreach_cohort` (BA1–BA7). For each cohort: total, sent, replied, in-progress. Show as a simple table. If `outreach_cohort` field is absent, show "Kohorten-Daten nicht verfügbar".

**AC:**
- Bottlenecks list shows real field-miss frequency
- Cohorts table shows per-BA cohort data or graceful empty state
- 22 tests pass

### Task 2 — BA selector wired to all views + tweaks panel

**BA selector:** The BA briefaktion select (now in subnav from M29 Task 4) must filter BOTH BA-Prep records AND Analyze metrics. Currently it only filters the BA-Prep queue.

When BA select changes, re-run all Analyze view computations against the filtered record set.

**Tweaks panel:** `#toggle-tweaks` opens a right-side slide-in `<div class="tweaks-panel">` with:
- Actor selector: Radio buttons for Roman/Flo (persisted in localStorage as `allex_actor`)
- Sort direction toggle: "Vollständigste zuerst" / "Unvollständigste zuerst"
- Debug mode toggle: shows/hides `DB-Feld` annotations (currently always hidden via display:none from M29)

**AC:**
- BA select change re-renders Analyze views with filtered data
- Tweaks panel opens/closes
- Actor selection persists across page reloads
- 22 tests pass

### Task 3 — Empty states + prefers-reduced-motion

**Empty states:** Every view must show a message when no records match:
- BA-Prep queue: "Keine Records in dieser Briefaktion" with a reset link
- Lead-Liste: "Keine Records — Suche anpassen"
- Analyze views: "Keine Daten für diese Auswahl"
- Drop-off: "Keine Daten verfügbar"

**Reduced motion:** Add to CSS:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

**AC:**
- Each view shows appropriate empty state when filtered to 0 records
- CSS has `prefers-reduced-motion` block
- 22 tests pass
