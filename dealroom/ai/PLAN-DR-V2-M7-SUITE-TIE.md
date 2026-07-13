# PLAN — DEALROOM v2 M7: Suite tie-in (Cockpit + Investor)

*2026-07-13. Continuation of the v2 local build — closes the "tie to the rest of the suite" goal (Roman: "Cockpit deliverables section tied to it, investor mode, negotiation section"). Negotiation was M5; this adds the Cockpit + Investor ties.*

## Built

- **`v2/db.py`** — `cockpit_db_path()` resolver (env `COCKPIT_DB` / `DEALROOM_COCKPIT_DB`, else sibling `cockpit/data/cockpit.db`). Read-only, present-or-None.
- **`v2/suite.py`** — read-only cross-module layer (mirrors how boardroom reads dealroom; dealroom NEVER writes cockpit):
  - `cockpit_execution(code)` — the deal's Cockpit workstream + open deliverables (name/status/target) + open tasks (waiting-on-party first) + progress (done/total). Cockpit is the PM/execution master; this is the read view. Degrades to `None` if cockpit.db is absent (deal page must never break — boardroom stale-tolerant precedent).
  - `investor_visibility(deal_row)` — how the deal surfaces in the Investor Room, computed with **boardroom's own stage buckets** (`INVESTOR_LIVE_STAGES` / `INVESTOR_FUNNEL_STAGES`) so the two surfaces can never contradict: post-LOI = named live deal, pre-LOI = anonymised funnel, else not visible.
- **`v2/repo.py`** — `deal_answer` now returns `execution` + `investor`.
- **`v2/ui.py`** — deal overview renders an **"Execution — Cockpit"** section (workstream badge, progress, open-deliverables card, waiting/next-tasks card, "Im Cockpit öffnen →" deep-link) and an **Investor Room chip** in the header (named / anonymised / —, links to `/investor/`). New `.rowline--between` utility class (no inline styles).

## Coherence decision

Cockpit deliverables (CDD/FDD/LDD/TDD/Signing) are the **execution lane**; the LOI-Zeitplan `deal_milestones` are the **commercial timeline**. Both are shown, distinctly labelled — not duplicated. Where they agree (Cockpit "Signing/Closing 21.08" == LOI Notartermin 21.08) that agreement is itself the signal that plan and terms are in sync.

## AI VALIDATION RESULTS

2026-07-13:
- Live: Fox deal page shows Cockpit workstream (9 deliverables, dated) + open tasks + "Im Cockpit öffnen" + "Investor Room · Live-Deal" chip (due_diligence → named). Cat/Aqua show "Pipeline (anonymisiert)". Octopus (dead) shows "Investor: —". Visual pass in Chrome — section reads as a coherent, suite-consistent card block.
- `python -m pytest v2/tests/` → **39 passed** (34 + 5 suite-tie: investor buckets == boardroom contract, cockpit_execution Fox, absent-cockpit degradation, deal-page renders execution+investor, dead-deal investor-negative).
- `validate_ci --audience de`: R2/R3/R4 = 0. Remaining R1 = one verbatim date inside a Cockpit task title ("Workshop Com2Med 08.07") — faithfully-rendered upstream content, documented tolerance, not a format defect. No inline styles introduced (stage-badge CSS-var setter is the established design-system pattern).
- Read-only guarantee: suite tie only opens cockpit.db via `open_readonly`; a missing DB yields `None` and the page renders without the section.
