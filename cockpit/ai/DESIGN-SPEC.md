# Repuro Cockpit — Hosted PM Tool Design Spec

**Date:** 2026-06-11
**Author:** Roman Dobriakov + Claude
**Status:** v5 — approved by Roman 2026-06-11 with modifications (all folded in: dealroom.db master contract, CMA out of v1, local-first, milestone loop). Codex reviews r1+r2 closed.
**Supersedes scope of:** 2026-05-18-cockpit-design.md (local M1 — parked, not deleted)

---

## 1. Purpose

A hosted internal project-management tool ("Repuro Cockpit") for Roman (RD) and Florian (FF), extensible to future holding employees. It aggregates daily tasks, weekly priorities, and the larger workstream packages (the workplan) in one place, replacing the static workplan xlsx and scattered weekly lists. Core differentiators over off-the-shelf (Trello etc.):

1. **Prerequisite color-coding** — every task/deliverable shows whether its prerequisites are fulfilled, computed live (readiness, separated from schedule risk).
2. **Waiting-on/chase model** — M&A work is dominated by items sitting with counterparties, lawyers, investors. The cockpit tracks who has the ball, since when, and when to chase — not just deadlines.
3. **Auto-generated workstream visualization** — the "Seite 3" deliverable overview is always current, never manually rebuilt.
4. **Agent connection layer** — both Claude instances (RC = Roman's Claude, FC = Flo's Claude) read and write the cockpit via MD/API; `[AGENT]` tasks are claimable and executable with a human approval gate.
5. **Dealroom linkage** — one truth of documentation: the cockpit links into `CLAUDE_REPURO/dealroom/` and deal folders, never duplicates documents.

## 2. Decisions already made (Roman, 2026-06-11)

- Local cockpit M1 is ignored for now; coordination later. Parser code may be reused server-side.
- Server DB is master; MD is the import/export channel. UI edits write to DB.
- v1 scope: workstreams + prereq colors, daily/weekly tasks, MD/agent pipeline. NOT in v1: mail/Granola/calendar feeds.
- Seed content: current workplan xlsx imported as staging (see §7); content curated in the tool afterward.
- Tasks are tied to a **final deadline**; daily/weekly is a **computed recommendation**, not a manual bucket.
- Workstream/deliverable view with upcoming tasks is the most important view — design priority #1.

Added 2026-06-11 (round 2 feedback):
- §4.2 readiness/schedule-risk split approved.
- **CMA is out of v1 entirely** — only the `runner` schema field ships; all dispatch code, control plane, API key setup are v1.1+.
- **Local-first**: v1 is built and trialled locally (Roman's laptop) before anything moves to Fly.io. Deploy is its own late milestone.
- **Milestone loop**: every milestone runs spec → implement → review-with-separate-agent (existing /plan-milestone → /execute-milestone → /review-milestone methodology).
- **dealroom.db is master for deal stage/facts** (verified: populated DB at `CLAUDE_REPURO/dealroom/data/dealroom.db`, `deals` table, 14 deals, stage enum already live) — the cockpit mirrors, never owns, deal stage. See §4.4.

## 3. Architecture

```
+----------------------+        +---------------------------+
|  Browser (RD / FF)   | HTTPS  |  Fly.io app               |
|  SPA (Alpine.js)     | <----> |  FastAPI + SQLite (volume)|
+----------------------+        +---------------------------+
                                     ^            ^
                              MD/JSON API    MD/JSON API
                                     |            |
                          +----------+--+      +--+-----------+
                          | RC (Roman's |      | FC (Flo's    |
                          | Claude CLI) |      | Claude)      |
                          +-------------+      +--------------+
                                     ^                       |
                                     | poll queue / results   | server-side dispatch (v1.1)
                          +----------+------------------+  +--+------------------------+
                          | Local agent runners:        |  | CMA (Claude Managed       |
                          | - manual /cockpit-pull skill|  | Agents, Anthropic cloud): |
                          | - scheduled poller (v1.1)   |  | runner=cma tasks          |
                          +-----------------------------+  +---------------------------+
```

- **Stack:** Python 3.12, FastAPI, SQLite on a Fly volume, Alpine.js + vanilla CSS frontend. No build step.
- **Hosting:** Fly.io single region (fra), HTTPS only, no public signup.
- **Security posture** (deal-sensitive data on a public endpoint):
  - Per-principal **scoped, rotatable** tokens (RD, FF, rc-agent, fc-agent, runner); rotation = one CLI command.
  - Browser sessions: short-lived cookie (24h), token never stored in localStorage.
  - Exports are least-privilege: agent tokens get scope-filtered slices, not full dumps, unless explicitly granted.
  - **Codenames only** in the cockpit — real company names, financials, and documents stay in the dealroom. The app leaking = codenames + dates, not deal contents.
  - Rate limiting + lockout on auth failures; audit log on every mutation.
  - Backups (SQLite snapshot + MD export) encrypted (age/zip-AES) before landing on OneDrive.
  - Optional hardening later: Tailscale/private network — deferred, adds onboarding friction for FF; revisit when >2 users.

## 4. Data model

### 4.1 Entities

```
users         id, name, initials (RD/FF), token_hash, role (human/agent)
deal_mirror   codename (pk), stage (read-only mirror of dealroom.db deals.deal_stage),
              note (display-only), owner_mode (legacy/cockpit-owned — for execution
              state only, §4.4), synced_at
              -- NEVER mirrored: company_name, financials, or any other dealroom.db field
workstreams   id, name, color, sort_order, status (active/parked/done),
              deal_codename (nullable — deal workstreams link here)
deliverables  id, workstream_id, name, target_date, status, sort_order, comment
tasks         id, deliverable_id (nullable), kind, text, detail (human-only, never exported to CMA),
              deadline (nullable -> inherits deliverable.target_date),
              responsible (RD/FF/external-name), priority (high/med/low),
              status (open/in_progress/waiting/blocked/in_review/done),
              -- waiting-on model --
              waiting_on_party (free text: "Ebner Stolz", "seller", "ASF"),
              waiting_on_type (counterparty/advisor/investor/internal),
              next_chase_date, expected_back_by, last_touched_at,
              -- agent model --
              execution (me/together/agent_supervised/agent_auto),
              runner (local/cma/any — where agent work may execute),
              acceptance_criteria (text, required if execution starts with agent_),
              claimed_by (nullable), claim_expires_at (nullable), evidence,
              -- structure --
              prereqs (JSON array of {ref, hardness: hard|soft}),
              tags (JSON), links (JSON array of {label, path_or_url}),
              deal (codename, nullable), pinned_today (bool),
              version (int, optimistic concurrency),
              created_by, created_at, updated_at, done_at
audit_log     id, at, actor, action, entity, before, after
```

- `kind` enum: `workplan` (workstream activity) / `followup` / `approval` / `agent_job` / `personal`. One table, but filters and reporting never blur deal work with personal one-offs.
- `version` increments on every mutation; writes carry the expected version → 409 on conflict (human edits a claimed task ≠ silent overwrite).
- Status `waiting` is first-class: the item is with an external party — it is NOT actionable and must never appear as "to do today", but its `next_chase_date` IS actionable.

### 4.2 Prerequisite colors — readiness, separated from schedule risk

Codex finding adopted: blending dependency state with deadline proximity produces misleading colors. Two independent signals:

**Readiness (the color dot)** — purely about prereqs:
- **green** — no prereqs, or all `hard` prereqs done (soft prereqs ignored if in progress)
- **amber** — some `hard` prereq in progress, or any `soft` prereq not started
- **red** — any `hard` prereq not started or blocked → this task cannot start

**Schedule risk (a separate badge, not a color blend)**:
- `overdue` — deadline passed
- `at-risk` — deadline within 7 days AND readiness ≠ green
- `chase` — status `waiting` and next_chase_date ≤ today

Prereqs may point at tasks or whole deliverables ("Commercial DD complete" gates "SPA draft"). Hardness defaults to `hard`; `soft` = nice-to-have-first. Deliverable roll-up: red if any open task with red readiness on the critical path to the deliverable target; amber if any amber; else green. Workstream header: count badges (n red / n amber / n chase-due).

### 4.3 Daily/weekly recommendation (computed, override by pin)

- **today** — overdue, due today/tomorrow, `pinned_today`, OR `waiting` with `next_chase_date` ≤ today (shows as "chase X", not as a work task)
- **this_week** — due within 7 days, or prerequisite of anything due within 14 days, or `expected_back_by` within 7 days
- **later** — everything else open

`waiting` items are excluded from work lists by their deadline — only their chase dates surface. This is the fix for "computed deadline lists mis-prioritize event-driven M&A work" (Codex critical #1/#3).

### 4.4 Dealroom & deals.md — ownership contract (one truth)

Roman's requirement 2026-06-11: the data model must tie to the dealroom or we get two versions of reality. Verified state of the dealroom: `CLAUDE_REPURO/dealroom/data/dealroom.db` is a populated SQLite DB — its `deals` table (14 deals) already carries `deal_stage` (live enum: `loi_signed`, `indicative_offer`, `valuation_rfi`, `dead`, …), `stage_entered_at`, status fields, and real company names; its `deal_actions` table (tasks: description/owner/due_date/status/priority) exists but is EMPTY and unused. deals.md mixes facts and execution state and demonstrably goes stale.

The contract — one master per content type, one sync direction, no cycles:

| Content | Master | Cockpit holds |
|---|---|---|
| Deal stage + facts (financials, sellers, real names, documents) | **dealroom.db** (`deals` table) | `deal_mirror`: codename + stage + note, read-only, synced |
| Tasks, next steps, waiting-on, priorities (incl. deal tasks) | **Cockpit** | master; deals.md Next-step/TODO/Priority-Logic content migrates here at curation (§7) |
| deals.md pipeline section | generated | written by cockpit export: mirrored stage + open next steps per deal |

Flow: `dealroom.db → cockpit (stage mirror) → deals.md generated section`. Stage changes happen where they happen today — in the dealroom tooling; the cockpit never writes deal stage.

- **Sync mechanics:** local phase (v1) — the cockpit server reads dealroom.db directly, read-only (same pattern as dealroom's read-only ATTACH of pipeline.db), refreshing the mirror on a timer. Fly phase — the local sync agent / `/cockpit-push` pushes mirror updates; staleness shown in the UI (`synced_at` badge).
- **`deal_actions` deprecation:** to avoid a fourth reality, the dealroom's empty `deal_actions` table is flagged for deprecation in favor of cockpit tasks — decision logged in the dealroom project (`ISSUES.md`), not silently assumed here.

- **Real names never enter the cockpit** — codenames only (also the §3 security rule). The codename→real-name map stays in the dealroom. Enforcement is layered, not claimed absolute: structured fields are enums/IDs; `detail` is human-only and never exported to CMA; the `/cockpit-push` skill lints outgoing text against the dealroom codename map **locally** (where the map lives) before pushing. Residual risk: a human typing a real name into task text — discipline + local lint, no server-side name detection pretended (§10.2c).
- **Per-deal cutover, not big-bang** (Codex r2 C2): each deal carries `owner_mode`. `legacy` = deals.md is master for that deal's execution state; the cockpit renders its tasks greyed like staging. `cockpit-owned` = set at that deal's curation pass (§7); from then on the deal's Next-step/TODO content in deals.md lives only in the generated block. The generated block carries `<!-- cockpit-generated vX @timestamp -->` markers; RC sessions lint manual edits inside markers for cockpit-owned deals and flag them instead of silently keeping both.
- **deals.md generation:** after a deal's cutover, the pipeline-status section of deals.md is auto-generated from `GET /api/export.md?scope=deals` for cockpit-owned deals (RC sessions read deals.md unchanged; it can no longer drift for owned deals). [REPURO] session-tag routing is unaffected.
- **Codified vocabulary** (in-product, not insider convention): deal stage values come from dealroom.db's live `deal_stage` enum — the cockpit adopts, never defines, stage vocabulary; `waiting_on_type` enum above; workstream names free but unique. The MD import rejects unknown enum values (fail closed) rather than guessing. `deal-status` import blocks are dropped — stage comes only from the dealroom.db mirror.

## 5. Views (v1)

### 5.1 Workstreams (default landing view) — THE view
Grouped: workstream → deliverable → open tasks. Each deliverable row: name, target date, readiness dot, schedule-risk badge, responsible, progress (done/total). Expanded: upcoming tasks sorted by deadline with readiness dots, execution badge, waiting-on chip ("@ seller since 02.06 — chase 13.06"), deal links. Filters: responsible, workstream, color, kind. Quick actions inline: done, block, set waiting (party + chase date), claim, edit deadline.

**Blockers & Waiting panel** (top of view, collapsible — Codex critical #3 adopted): the exception list. Three columns: **Red readiness** (what can't start and why — the failing prereq named), **Waiting** (party, since, chase date, sorted by chase date), **Overdue**. This answers "what is blocking the deal, from whom, since when, what's the next push" in one glance.

### 5.2 Today (per person + shared lane)
Needle mover + computed today list + this_week list, RD/FF tabs — **plus a shared coordination lane** (Codex secondary #2): items where I depend on the other person (their task is my prereq), stale handoffs (last_touched > 7 days on together-items), and `together` items awaiting joint action.

### 5.3 Timeline (auto "Seite 3")
Kept in v1 scope but descoped in fidelity (disagreement with Codex logged in §9): FF explicitly asked for the auto-generated Gantt — it is a stakeholder requirement, not a nice-to-have. v1 renders **deliverable windows + milestone diamonds** (target dates) colored by readiness — no task-level bars, no invented start dates (Codex secondary #3: task creation date ≠ plan start). `planned_start` field can be added later if FF wants real bars. Read-only; ships in M4, after the daily-value views.

### 5.4 Agent queue
API ships in M1 (cheap); the **UI view ships in M4** (Codex critical #6 adopted): open agent tasks with AC; claimed tasks with claimant + lease expiry; `in_review` results with evidence. Approve → done; reject → reopen with comment. Until M4, review happens via MD export + CLI.

## 6. MD / Agent connection layer

### 6.1 Endpoints

```
GET  /api/export.md             scope-filtered markdown (full dump only for human tokens)
POST /api/import                MD or JSON patch; dry_run=true returns the diff without applying
GET  /api/agent/queue           claimable agent tasks (execution=agent_*) with AC
POST /api/agent/claim/{id}      claim -> sets claimed_by + claim_expires_at (TTL 4h, renewable)
POST /api/agent/heartbeat/{id}  renew lease
POST /api/agent/result/{id}     evidence + result + idempotency_key; -> in_review (supervised)
                                or done (agent_auto, only if AC self-check passed)
```

Claim semantics (Codex critical #4 adopted): lease with TTL + heartbeat; expired lease → task auto-reverts to open (reclaim allowed, audit-logged). All writes carry `version` → 409 on stale. `result` posts are idempotent by key (agent retries don't double-apply). **The claiming principal cannot approve its own result** — approval requires a human token or a different agent token with reviewer scope.

### 6.2 MD import format (the "inputfile")

```markdown
# cockpit-push
## task-update
- id: t-042 | status: done | evidence: LOI sent 11.06, see dealroom/octopus/loi_v3.pdf
## new-task
- workstream: Octopus | deliverable: Legal DD | text: Review works council docs
  | deadline: 2026-06-20 | responsible: External Legal | prereq: t-031(hard)
  | execution: me | priority: high | kind: workplan
```

(No `deal-status` block: deal stage enters the cockpit exclusively via the dealroom.db mirror, §4.4 — an import channel for stage would reintroduce a second writer.)

Parser is strict where it matters (Codex secondary #4 adopted): updates **require IDs** — no fuzzy text matching; unknown enum values, unknown IDs, ambiguous deliverable names → reject the line, report, apply nothing else from that block (fail closed). `dry_run` preview supported; the `/cockpit-push` skill always dry-runs first and shows the diff in-session before applying. RC/FC get `/cockpit-push` + `/cockpit-pull` skills so any CLI session syncs in one command.

### 6.3 Autonomous execution model

- `execution=me` — humans only, agents never touch.
- `together` — surfaced in the shared coordination lane for both.
- `agent_supervised` — agent claims, executes, posts result + evidence → `in_review`; human approves. Default for all agent work.
- `agent_auto` — agent may complete without review IF acceptance_criteria present and self-check passes. Reserved for low-risk internal work (data pulls, formatting, internal summaries). Never external-facing (emails, investor docs, anything leaving the house) — structurally `agent_supervised` minimum. **Deferred to v1.1** (Codex critical #6): v1 ships supervised only; auto unlocks once the review loop is trusted.

Execution happens where tools live, not on Fly: v1 ships the queue API + manual `/cockpit-pull` (Roman or Flo dispatches a session against a claimed task). v1.1 adds a scheduled poller (laptop cron or Claude scheduled cloud agent) auto-dispatching during work hours. Max 2 self-correction loops per task (existing AC rule), then task flips to blocked with the failure note.

### 6.4 CMA — Claude Managed Agents integration (OUT of v1 — Roman 2026-06-11; spec retained for v1.1)

Nothing in this section ships in v1 except the `runner` schema field. No API key, no dispatch module, no control plane until v1.1 is explicitly started.

CMA = Anthropic's hosted agent harness (beta, `managed-agents-2026-04-01`): agents defined once (model, prompt, tools, MCP servers), sessions run in Anthropic-managed cloud sandboxes with bash/file/web/MCP tools; an application dispatches tasks via API and streams results (SSE). Docs: platform.claude.com/docs/en/managed-agents/overview.

**Why it fits:** the Fly.io server itself can dispatch cloud-executable tasks to CMA — no laptop required. This closes the gap where local runners (RC/FC) must be online. Routing via the task `runner` field:

- `runner=local` — needs OneDrive/dealroom files, email MCP, or local tools → RC/FC only.
- `runner=cma` — executable from web + context supplied in the dispatch (market research, drafting from provided inputs, monitoring/checking public sources, summarization).
- `runner=any` — either.

**Dispatch flow (v1.1):** cockpit server claims the task as the `cma-agent` principal → creates a CMA session with the **dispatch bundle** → streams events → posts result via the same `result` endpoint → `in_review`.

**Dispatch bundle (minimum contract, Codex r2 S1):** task text + AC + parent deliverable & workstream names + one-line summaries of prereq states + prior evidence on the task + required output shape + explicit "no local files are available" statement. Excluded always: `detail`, `links[]` to local paths, financials, anything failing the codename rule. **Preflight blocks dispatch** if AC is missing, if `links[]` reference local-only paths the task plausibly needs, or if the bundle is empty beyond the task text — under-contexted cloud runs produce garbage silently; fail loudly instead.

**Control plane (Codex r2 C4) — server-side, outside task data:** global `cma_enabled` kill switch (one flag blocks all new dispatches immediately, audit-logged); per-dispatch max runtime; concurrency cap (default 1); monthly spend cap with hard stop; per-runner tool allowlist on the CMA agent definition (no email/external-send tools, web read-only).

**Credential separation (Codex r2 S2):** the CMA bridge holds a token scoped to claim/heartbeat/result only — structurally never reviewer scope. All §6.1 semantics apply unchanged (lease, idempotency); a CMA result always requires a human (or distinct reviewer-scoped) approval.

**Constraints (accepted by Roman by requesting CMA, flagged explicitly):**
1. Requires a Claude API key — paid API usage, separate from the Claude subscription. This is a deliberate, scoped exception to the CLI-only rule (`feedback_cli_only_no_api`): CMA dispatch only, from the cockpit server only; RC/FC remain CLI/OAuth.
2. No Zero-Data-Retention for Managed Agents (session state persists at Anthropic until deleted). Mitigation: codenames-only rule is mandatory for CMA payloads; dispatch slices exclude financials by default; sessions deleted after result approval.
3. Beta product — API surface may shift; integration isolated behind a single `cma_dispatch.py` module.

## 7. Seed import — staging, not truth

One-off script parses `260312_Repuro_Workplan_v1.xlsx` → DB with ALL items flagged `staging` (Codex secondary #5 adopted): staging items render greyed, are excluded from readiness colors, recommendations, and the Blockers panel. A curation pass (Roman + Flo, in the tool, with RC assisting) promotes/edits/kills each item and adds prereq links — only promoted items drive colors. The first thing users see is honest: "40 stale items to triage", not false signal.

## 8. Non-goals (v1)

- Mail / Granola / Calendar feeds (needs local sync agent or server-side creds — later milestone)
- Local TASKS.md two-way sync (parked with cockpit M1)
- Mobile app (responsive web is enough), notifications, file uploads (dealroom links instead)
- Multi-tenant features beyond user table supporting >2 users
- `agent_auto` execution + scheduled poller (v1.1)
- Critical-path computation (roll-up uses simple worst-readiness; revisit if deliverables grow >20 tasks)

## 9. Codex review — disposition (2026-06-11-1733-design)

Verdict was **revise**. Adopted: waiting-on/chase model (C1), readiness/schedule-risk separation + hard/soft prereqs (C2), Blockers & Waiting panel (C3 part 1), claim lease/heartbeat/version/idempotency/no-self-approve (C4), tightened security posture (C5), v1 re-cut + agent_auto deferral (C6), kind enum (S1), shared coordination lane (S2), milestone-only Gantt rendering (S3), strict import parser (S4), staging import (S5), codified vocabulary (S6).

**Disagreement (logged per protocol):** Codex suggested deferring the Timeline from v1 entirely. Rejected — the auto-Gantt is FF's explicit core ask ("Seite 3 immer automatisch dabei"); cutting it ships a tool that misses its sponsor's #1 visual. Compromise: milestone-fidelity rendering, last milestone (M4), no invented start dates.

**Round 2 (2026-06-11-1814, delta review of §4.4 + §6.4):** verdict revise; all four critical findings adopted — first-class `deals` entity with stage enum (C1), per-deal `owner_mode` cutover + generated-block markers + edit lint (C2), layered codename enforcement with residual risk stated honestly instead of claimed absolute (C3, adopted proportionately — no server-side name detection for a 2-user tool), CMA control plane: kill switch, spend/runtime/concurrency caps, tool allowlist (C4). Secondary: minimum dispatch bundle + preflight (S1), CMA bridge never holds reviewer scope (S2), deal-status import split into stage enum + display note (S3). Review loop closed at 2 per protocol.

## 10. Risks / open points

1. **CMA cost + data residency** (6.4) — API billing is usage-based and new; start with supervised low-volume tasks and review spend after the first month. No-ZDR means codename discipline in CMA payloads is a hard rule, not a preference.
2. **TASKS.md duality** — until coordination is decided, Roman runs TASKS.md locally AND the cockpit. Mitigation: `/cockpit-push` makes syncing cheap; morning-brief can read the export endpoint.
2b. **deals.md generated-section discipline** — once inverted (post-M3), manual edits to the generated pipeline section get overwritten; facts/narrative sections remain hand-edited. Clear marker comments in the file delimit the generated block; RC-side lint flags edits inside markers.
2c. **Free-text leak surface is mitigated, not eliminated** — `detail` never reaches CMA, push-skill lints against the codename map locally, dispatch bundles exclude links/financials; but a real name typed into task `text` by a human will propagate. Accepted residual risk for a 2-user tool; revisit if users grow.
3. **SQLite on Fly volume** — single-machine constraint, fine for 2-10 users; snapshots + MD export cover data loss.
4. **Curation pass is real work** — the tool is only as good as the triaged workplan; needs a scheduled RD+FF session post-M2.
5. **Gantt fidelity expectations** — FF may expect task-level bars like the xlsx Seite 3; manage expectation: milestones first, bars when planned_start exists.

## 11. Milestones — local-first, loop per milestone

**Methodology (Roman 2026-06-11):** every milestone runs the full loop — spec (`/plan-milestone`), implement (`/execute-milestone`), review with a separate agent (`/review-milestone`). No milestone is marked done without the independent review. ROADMAP.md + PLAN-M{n}.md kept in sync per house rules.

**Deployment phasing:** v1 runs entirely locally on Roman's laptop (server at localhost, SQLite local, direct read-only access to dealroom.db). Fly.io comes only after the local trial proves the operating model.

- **M1** — schema (incl. deal_mirror + dealroom.db read-only sync), API core (agent queue endpoints + lease semantics), MD import/export with dry-run, seed import (staging), auth + audit log. Local. Testable via curl/CLI.
- **M2** — Workstreams view incl. Blockers & Waiting panel + Today view incl. shared lane. Local. The 80% of daily value.
- **M3** — `/cockpit-push` + `/cockpit-pull` skills, deals.md generated section, **local trial: Roman runs it as daily driver for a deal week.** Curation pass on seeded workplan happens here.
- **M4** — Timeline (milestone fidelity) + Agent queue UI. Still local.
- **M5** — Fly.io deploy, encrypted backups, token rotation, Flo onboarding. Only after M3/M4 trial confirms the tool earns its hosting.
- **v1.1** — scheduled agent poller, `agent_auto`, CMA integration (§6.4), `deal_actions` deprecation coordination with dealroom project.
