# COCKPIT — Roadmap

Spec references: `DESIGN-SPEC.md` §-numbers. Status table lives in `PLAN.md` — keep both in sync at milestone completion.

## M1 — Backend core (✅ done 2026-06-11, PLAN-M1.md has validation results)
Schema (§4.1), dealroom.db read-only mirror sync (§4.4), computed fields (readiness §4.2, schedule risk, recommendation §4.3), REST API + bearer auth + audit log, MD export/import with dry-run (§6.1–6.2), agent queue endpoints with lease semantics (§6.1), workplan xlsx seed import as staging (§7). No UI.

## M2 — Core views (✅ done 2026-06-11, with M4 — PLAN-M2-M4.md)
Workstreams view: workstream → deliverable → tasks, readiness dots, risk badges, waiting chips, filters, inline actions; Blockers & Waiting panel (§5.1). Today view: needle, computed today/this_week, RD/FF tabs + shared coordination lane (§5.2). Alpine.js SPA served by the FastAPI app, no build step.

## M3 — Agent skills + local trial (✅ built 2026-06-11 — trial open, Roman)
`/cockpit-push` (dry-run first, local codename lint) + `/cockpit-pull` skills for RC/FC sessions (§6.2). deals.md generated pipeline section for cockpit-owned deals (§4.4). Roman runs cockpit as daily driver for one deal week. Workplan curation pass (staging → promoted) with Flo. Exit criteria: Roman stops opening TASKS.md for workstream items.

## M4 — Timeline + Agent queue UI (✅ done 2026-06-11, with M2)
Timeline: deliverable windows + milestone diamonds, readiness colors, no invented start dates (§5.3). Agent queue UI: claims, leases, in_review approvals with evidence (§5.4).

## M5 — Hosting + Flo
Fly.io (fra), HTTPS, per-principal rotatable tokens for FF/fc-agent, encrypted backups to OneDrive, mirror sync switches from direct dealroom.db read to push-based (§3, §4.4). Flo onboarding.

## v1.1 — Automation (not before trial verdict)
Scheduled agent poller; `agent_auto` execution; CMA integration incl. control plane (§6.4); `deal_actions` deprecation coordinated with dealroom project.
