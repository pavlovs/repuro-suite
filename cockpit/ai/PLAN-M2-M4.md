# M2 + M4: Frontend — Workstreams, Today, Timeline, Agent Queue

Executed together (one SPA file serves all four views; separate builds would re-touch the same
artifact twice). M3 runs separately after. Loop preserved: this plan → implement → external review.

## Summary
`static/cockpit.html` (Alpine.js CDN + vanilla CSS, no build step) served at `GET /` by the
existing FastAPI app. Done = all four views render real data on :8099, inline mutations work
version-safely, Repuro CI applied, external review PASS.

## Locked decisions
- **CI (context/repuro-ci.md):** Arial; header band #0891B2 white; section bands #8DE8F6;
  readiness dots green #16A34A / amber #EAB308 (Accent 4) / red #E11D48 (Accent 3); staging grey;
  accent links #0891B2. Light theme (CI is white-surface oriented). CSS dots, not SVG (house rule).
  No logo files (Corporate Identity folder was removed from CLAUDE_COWORK) — text wordmark.
- **Auth:** login overlay → token kept in sessionStorage (localhost phase; cookie auth is M5).
- **Data flow:** GET /api/state once + after every mutation; no client-side caching cleverness.
  409 → toast + refresh. All computed fields come from the server — the UI never re-computes
  readiness/risk/recommendation.
- **Views:**
  1. *Workstreams* (default): Blockers & Waiting panel (3 columns: Red readiness / Waiting by
     chase date / Overdue) on top, collapsible. Workstream groups with deal chip (codename+stage),
     deliverable rows (dot, name, target, risk badges, progress n/m), expandable tasks with inline
     actions: done, start, block, wait (party+type+chase), pin, promote (staging→live), edit deadline.
     Filters: responsible (RD/FF/ext), readiness color, kind, show/hide staging (default ON while
     curation pending), show/hide done.
  2. *Today*: three lanes RD / FF / Shared. RD+FF lanes: needle (pinned) → today → this_week,
     from server recommendation. Shared lane: execution=together + in_progress tasks untouched
     >7 days (stale handoffs). Person match = token match on responsible (server rule mirrored
     for display only).
  3. *Timeline* (M4, "Seite 3"): inline SVG per workstream — time axis (month gridlines, today
     line), deliverable diamonds at target_date colored by readiness, label + target. No invented
     start dates (milestone fidelity per spec §5.3). Deliverables without target_date listed
     beside the chart, not invented onto it.
  4. *Agent Queue* (M4): open (with AC), claimed (claimant + lease expiry), in_review (evidence,
     Approve/Reject buttons — human token).
- **API change:** only `GET /` → FileResponse(static/cockpit.html). No new data endpoints.
- **Out of scope:** drag-reorder, edit-in-place text, mobile layout polish (responsive enough),
  charts beyond the milestone SVG.

## Validation
- pytest (adds: GET / returns 200 text/html containing 'Repuro Cockpit').
- Live: all four tabs against the real seeded DB on :8099; mutation round-trip (create task in UI
  → appears; check done → state refresh); 409 path (stale version) shows toast.
- UI self-check (house rules): column counts per view, CSS display block checks, JS scope (no
  undeclared x-data refs), staging greyed everywhere, no SVG legend dots.
- External review (codex): correctness vs this plan + spec §5; visual/structural critique of the
  HTML; verdict gate as in M1.

## Validation results
Executed 2026-06-11/12 (RC, Fable 5):
```
pytest: 75 passed (incl. GET / SPA test)
live:   SPA at localhost:8099/ — login overlay, 4 tabs, real seeded data
        server detached via start_cockpit.ps1 + Startup RepuroCockpit.cmd (schtasks denied)
structural checks: braces balanced, x-cloak CSS present, chase lane, deps lane, ws filter — all true
```
PM review (ai/codex-reviews/2026-06-11-PM-M2-M4.md): CONDITIONAL PASS, 5 REQUIRED + 5 CLARIFY.
All REQUIRED fixed: waiting→chase cards in Today (R1), dependency-based shared lane (R2),
server-side deadline sort (R3), generator fail-closed on marker drift — verified live, exit 1 on
dup/missing markers (R4), pipe-escaping (R5). CLARIFY decided autonomously per Roman's
instruction: ws filter + chase counts (C1), waiting modal (C2), skill wording (C3), x-cloak (C4),
legacy on deal chip instead of double-greying (C5 — all deals legacy today, staging already greys).
Re-review (…-recheck.md): **PASS — all 10 verified with code-level evidence.**

### Verdict
PASS
