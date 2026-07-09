# COCKPIT — Roadmap

Spec references: `DESIGN-SPEC.md` §-numbers. Status table lives in `PLAN.md` — keep both in sync at milestone completion.

## M1 — Backend core (✅ done 2026-06-11, PLAN-M1.md has validation results)
Schema (§4.1), dealroom.db read-only mirror sync (§4.4), computed fields (readiness §4.2, schedule risk, recommendation §4.3), REST API + bearer auth + audit log, MD export/import with dry-run (§6.1–6.2), agent queue endpoints with lease semantics (§6.1), workplan xlsx seed import as staging (§7). No UI.

## M2 — Core views (✅ done 2026-06-11, with M4 — PLAN-M2-M4.md)
Workstreams view: workstream → deliverable → tasks, readiness dots, risk badges, waiting chips, filters, inline actions; Blockers & Waiting panel (§5.1). Today view: needle, computed today/this_week, RD/FF tabs + shared coordination lane (§5.2). Alpine.js SPA served by the FastAPI app, no build step.

## M3 — Agent skills + local trial (✅ superseded 2026-07-05 by Agentic workflow v2)
Original `/cockpit-push`/`/cockpit-pull` skills RETIRED (targeted diverged :8099). Replaced by the plugin flow — see "Agentic workflow v2" below.

## M4 — Timeline + Agent queue UI (✅ done 2026-06-11, with M2)
Timeline: deliverable windows + milestone diamonds, readiness colors, no invented start dates (§5.3). Agent queue UI: claims, leases, in_review approvals with evidence (§5.4).

## M5 — Hosting + Flo
Fly.io (fra), HTTPS, per-principal rotatable tokens for FF/fc-agent, encrypted backups to OneDrive, mirror sync switches from direct dealroom.db read to push-based (§3, §4.4). Flo onboarding.

## Agentic workflow v2 (✅ done 2026-07-05 — SPEC-agentic-workflow.md §9 has validation results)
One queue (cockpit prod) / one runner (`/repuro:loop` plugin v0.3.0, scheduled `RepuroAgentLoop` logon+13:00) / one review surface (Agents view). Closed review loop: request-changes re-queues with feedback context; agent questions → "Waiting on you" inline answer; reject loop-safe (`execution→me`); claim enforces readiness; `POST /api/agent/task` enqueue from any session. TASKS.md [AGENT] queue killed; /agent-loop + cockpit-pull/push retired. Deployed suite v2.1.15.

## Calendar v1 (🔄 in-progress 2026-07-09)
MS Graph client-credentials integration for team calendar visibility. `src/calendar_graph.py`: token cache, `fetch_events`, `probe_upn`, FAKE mode. API: `GET /api/calendar/events?scope=me|team`, `POST /api/calendar/connect`. Frontend: `view-calendar.jsx` (week-grid, connect flow, privacy masking), Calendar tab in the Cockpit-overview right column (WeekView). DB migration 14: `users.calendar_upn`. Azure setup guide: `ai/CALENDAR-SETUP.md`.

## v1.1 — Automation (remaining)
`agent_auto` execution; devbox always-on runner for `runner:any` tasks (Phase 3 — Roman: devbox later, not now); CMA integration incl. control plane (§6.4); `deal_actions` deprecation coordinated with dealroom project. ~~Scheduled agent poller~~ ✅ delivered as `RepuroAgentLoop` 2026-07-05.
