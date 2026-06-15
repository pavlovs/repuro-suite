# COCKPIT — Master Plan

## Vision
One tool for RD + FF that aggregates daily tasks, weekly priorities, and workstream packages —
replacing the static workplan xlsx. Differentiators: prereq readiness colors, waiting-on/chase
model for counterparty-driven M&A work, auto-generated workstream visualization, agent task queue
(RC/FC, later CMA). Full design: `DESIGN-SPEC.md` (v5, approved by Roman 2026-06-11).

## Execution protocol (every milestone)
1. Read `PLAN-M{n}.md` fully before touching code. Locked decisions are locked.
2. Implement steps in order. Commit per logical unit (workspace git = backup repo, push after milestone).
3. Write tests alongside code; run the full suite before claiming any step done.
4. Run the AI validation plan exactly; paste real outputs into "AI validation results" in PLAN-M{n}.md. No results = milestone incomplete.
5. Update ROADMAP.md + PLAN.md status blocks + CLAUDE.md Status line before the milestone commit.
6. Run `/review-milestone` with a separate agent. Address findings (max 2 loops). Only then mark done.
7. Present the user validation walkthrough to Roman.

## Milestones
| M | Scope | Status |
|---|---|---|
| M1 | Backend core: schema, deal_mirror sync (dealroom.db ro), API + auth + audit, MD import/export, agent queue endpoints, seed import (staging) | ✅ **done** 2026-06-11 — validated, see PLAN-M1.md |
| M2 | Workstreams view (Blockers & Waiting panel) + Today view (shared lane) | ✅ done 2026-06-11 (PLAN-M2-M4.md) |
| M3 | /cockpit-push + /cockpit-pull skills, deals.md generated section, local trial as daily driver, workplan curation pass | ✅ built 2026-06-11 — trial + curation = Roman's part (PLAN-M3.md) |
| M4 | Timeline (milestone fidelity) + Agent queue UI | ✅ done 2026-06-11 (PLAN-M2-M4.md) |
| M5 | Fly.io deploy, encrypted backups, token rotation, Flo onboarding | prepared (Dockerfile + fly.toml) — deploy gated on trial |
| v1.1 | Scheduled agent poller, agent_auto, CMA integration, deal_actions deprecation w/ dealroom | not started |

## Current state
M1 backend live: API on localhost:8099 (66 tests green), 14 deals mirrored from dealroom.db,
workplan seeded as 43 staging tasks across 4 workstreams. Tokens for rd/rc-agent in `.env`.
Next: M2 (Workstreams + Today views).
