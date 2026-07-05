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
| M3 | /cockpit-push + /cockpit-pull skills, deals.md generated section, local trial as daily driver, workplan curation pass | ✅ superseded 2026-07-05 by Agentic workflow v2 (skills retired) |
| M4 | Timeline (milestone fidelity) + Agent queue UI | ✅ done 2026-06-11 (PLAN-M2-M4.md) |
| M5 | Fly.io deploy, encrypted backups, token rotation, Flo onboarding | ✅ live — repuro-suite.fly.dev/cockpit/ (suite deploy) |
| Agentic workflow v2 | One queue (cockpit) / one runner (/repuro:loop + RepuroAgentLoop schedule) / one review surface; closed review loop (block/answer, feedback re-queue, loop-safe reject, readiness-enforced claim, agent enqueue) | ✅ **done** 2026-07-05 — validated, see SPEC-agentic-workflow.md §9; deployed v2.1.15; plugin v0.3.0 |
| v1.1 | agent_auto, devbox runner (`runner:any`), CMA integration, deal_actions deprecation w/ dealroom | not started (scheduled poller ✅ delivered 2026-07-05) |

## Current state
Prod on Fly (suite v2.1.15) is the ONLY real DB; local :8099 is a diverged sandbox.
Agentic workflow live end-to-end: enqueue (browser / `/repuro:add`) → scheduled runner
(logon + 13:00) → Needs your review / Waiting on you in the Agents view → verdicts
re-queue with feedback. 102 tests green. Flo: `/plugin install repuro` update to v0.3.0
is the only step. Next: v1.1 automation items when Roman calls for them.
