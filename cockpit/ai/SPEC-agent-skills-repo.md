# SPEC — Repuro Agent-Skills GitHub Repo (`/repuro`)

Status: **SPEC for review** — not built. Decisions 2–4 confirmed by Roman 2026-06-22; one open decision remains (auth path, §2). Resolves ISSUES.md items "AGENT Integration and handover via /skill" + "Agents: Flo will not have this skill / build a custom github repo with cockpit skills".
Author: Claude · Date: 2026-06-22

---

## 1. Goal (Roman's words)

> "Based on the task I just need to put a `/skill XYZ` where XYZ is the queue number in the cockpit or the name of the agent-task."

One slash command, one identifier, the task gets executed and posted back for verdict. Works for **both** Roman and Flo, on their own laptops, without either needing the private `~/.claude/` setup or flyctl.

- **What "done" looks like:** Flo runs `git clone` + one install command + pastes a token. He sees agent task **#3 "Update MOUSE onepager"** in the cockpit, types `/repuro 3` (or `/repuro MOUSE onepager`) in Claude Code, the task is claimed, executed, output posted, and it lands in the cockpit's **"Awaits verdict"** column — where Roman/Flo see the actual result (the produced `.md`, a link, a link back to the task) and either approve (→ done) or send back with feedback.
- **A task is done ONLY after a human verdict.** No auto-close in any version.
- **Ownership:** each agent task is tagged **RC** (Roman) or **FC** (Flo) by **who created it**. Each person's `/repuro` works their own tagged queue by default (see §3a).
- **Out of scope:** building the team/personal-todo features; touching ALLEX/Dealroom.

---

## 2. The one hard decision — how does a remote agent reach the queue?

`suite/Caddyfile:11` applies **site-wide HTTP basic auth** (everything except `/healthz`). `handle_path /cockpit/*` then sets `X-Remote-User` from the basic-auth user id. The cockpit backend (`src/api.py`) treats `X-Remote-User` as a **human** principal, and `agent_claim/heartbeat/result` are gated by `agent_only` (`role='agent'`).

Net: **a remote caller cannot claim an agent task today.** Basic auth forces you to be a human; the agent endpoints reject humans. The only working path is localhost-on-the-box (SSH), which Flo doesn't have.

Three ways to close the gap:

| | Option A — human-as-runner | Option B — agent token bypass *(recommended)* | Option C — flyctl for all |
|---|---|---|---|
| **Mechanism** | Skill authenticates as `florian` via basic auth (human). Reads queue, executes, then PATCHes task → `in_review` + evidence directly (humans can patch). No `agent/*` calls. | Add a Caddy matcher: `/cockpit/api/agent/*` bypasses basic auth **iff** a valid `Authorization: Bearer` is present, forwarded to backend, which validates the agent token. Provision `rd-agent` / `ff-agent` token secrets. | Flo installs flyctl + gets a deploy token; skill SSHes to the box and hits `localhost:8083` like Roman's REMOTE-API. |
| **Infra change** | None — ships on current prod. | Caddyfile edit + 2 secrets + redeploy. | flyctl install + org access for Flo. |
| **Keeps lease/heartbeat (no double-execution)?** | ❌ No — relies on optimistic version check + a soft `claimed` convention. | ✅ Yes — full claim→heartbeat→result lifecycle preserved. | ✅ Yes. |
| **Risk** | Two runners (Roman+Flo) can grab the same task; no 4h lease reaping. | Caddy matcher must be exact (bearer-only bypass, never expose mutating human endpoints unauthenticated). | Flo is not ops; deploy-token sprawl. |

**Recommendation: Option B — and the midterm "two continuous `/loop` sessions" model (§7) makes it close to mandatory.** With Roman and Flo each running a continuous loop against a shared queue, two runners can collide on the same task; only the server-side lease/heartbeat (Option B) prevents double-execution. Option A's convention-only locking is unsafe under continuous loops. Ship Option A only as a stopgap if you need it working **this week** with zero deploy.

> **This is the one open decision** (it displaced the original "auth path" question when the RC/FC tagging requirement came in). Everything else in this spec is confirmed.

---

## 3. Command surface

`/repuro` is the entry command (distinct, agentic, unmistakably Repuro). Three commands:

| Command | Purpose |
|---|---|
| `/repuro <selector>` | Claim + execute **one** agent task, post output, leave for verdict. |
| `/repuro-queue` | Print the live queue: position, **stable id**, owner (RC/FC), title, deal, readiness. |
| `/repuro-loop` | Work the **whole** queue in order continuously (Flo-facing equivalent of the private `/agent-loop`; the §7 midterm model). |

### Selector resolution (the `XYZ`)

Queue position `#N` is **computed client-side and unstable** — it shifts as tasks complete or reprioritize. So `XYZ` resolves in this order, always against a **freshly fetched** `/api/agent/queue` (never cached):

1. `t-<n>` → exact task id (stable, unambiguous).
2. bare integer `N` → queue **position** #N at invocation time.
3. otherwise → case-insensitive substring match on task `text`. 1 hit → proceed; >1 → list and ask; 0 → error.

**Safety net for the unstable `#N`:** always echo `Resolved "<selector>" → t-123 [RC]: "<title>"` before claiming, so a stale-position mismatch is caught by eye. Companion UI change (small): render the stable `t-<id>` + owner badge on each agent card in `view-agents.jsx` so the human can pass the unambiguous id.

## 3a. Ownership tagging (RC / FC)

Each agent task carries an owner derived from **`created_by`**: `rd → RC`, `ff → FC`. (The `view-agents.jsx` `HANDOVER_INITIALS` map already encodes this; today it keys off `responsible` — switch it to `created_by` so the tag means "whose agent created it".)

- `/repuro <selector>` and `/repuro-loop` default to the **caller's own** tag — Roman's session works RC tasks, Flo's works FC tasks. The caller's identity comes from the configured token/user in `.env`.
- `/repuro <selector> --any` (or an explicit `t-<n>`) overrides to work across both owners.
- Server change: `/api/agent/queue` must return `created_by` (it does not today) and accept an optional `?owner=rc|fc` filter. The owner badge then renders on each card.

This keeps two parallel loops out of each other's lane by default, on top of the §2 lease.

---

## 4. Execution contract (`/rep <selector>`)

Mirrors `/agent-loop`, scoped to one task:

1. Load config (`COCKPIT_BASE_URL`, auth per §2).
2. `GET /api/agent/queue` → resolve selector → task; echo resolution.
3. **Claim** — `POST /api/agent/claim/{id}` (Option B, agent token). Heartbeat is optional for short tasks (4h lease); long tasks `POST /api/agent/heartbeat/{id}` periodically.
4. **Execute** — read `text` / `detail` / `acceptance_criteria` / `deal` / `runner`; do the work. The skill body is general-purpose and may dispatch subagents (per Agent Discipline). Honor `runner` (`local` / `cma` / `any`).
5. **Verify** against `acceptance_criteria`. Max 2 self-correction loops, then report.
6. **Post** — `POST /api/agent/result/{id}` with `idempotency_key` + **structured `evidence`** (see §4a) → task → `in_review`.
7. **Report locally** — task, what was done, output links, "awaiting your verdict in /cockpit".

v1: **supervised only** — a task is **done only after a human verdict**. Every result routes to `in_review`. (Matches current M1 server behavior.) No auto-close in any version.

## 4a. "Awaits verdict" — the review surface (decision 4)

Goal: the reviewer sees the **actual output** in the cockpit and can approve or correct without leaving the browser. Today `AgentsView` already shows an `in_review` "Needs verdict" card with raw `evidence` text + Approve / Send-back. Two changes make it the review surface Roman described:

- **Structured evidence.** The agent posts `evidence` as a small block, not free text: a one-line **result summary**, plus **links** — produced artifact(s) (`.md`/file path or URL), a link back to the task (`t-<id>`), and any relevant deal/deliverable. The verdict card renders these as clickable rows ("Review t-123 result → result.md, task, deal Mouse").
- **Verdict actions unchanged:** **Approve** → `done`; **Send back** → re-queue with feedback (already wired via `/api/task/{id}/approve|reject`). Feedback is appended to evidence so the next loop sees what to fix.

No separate "Review t-123" task entity — that would duplicate the record. The `in_review` state **is** the review item, surfaced prominently in the "Awaits verdict" column. (Alternative — minting a sibling review task — is available if you'd rather see it in the main task list, but it doubles bookkeeping; not recommended.)

---

## 5. Repo

`github.com/pavlovs/repuro-cockpit-skills` — **private, shared by link only** (decision 3): not public, not org-listed. GitHub has no "unlisted" repo, so "sharable via link" = keep it private and add Flo as a **collaborator via invite link** (he gets a link to accept; no one else can discover or clone it). Layout:

```
repuro-cockpit-skills/
  README.md            # 3-step install + auth setup
  install.ps1          # copy/symlink commands/*.md into ~/.claude/commands/
  install.sh           #   (mac/linux equivalent)
  .env.example         # COCKPIT_BASE_URL=https://repuro-suite.fly.dev/cockpit
                       # COCKPIT_AUTH=...  (token or basic creds per chosen option)
  commands/
    repuro.md          # /repuro <selector>
    repuro-queue.md    # /repuro-queue
    repuro-loop.md     # /repuro-loop
  lib/
    cockpit_client.py  # queue / claim / heartbeat / result / patch — single thin client
```

- **Distribution to Flo:** accept collaborator invite link → `git clone` → `./install.ps1` → paste token into `.env`. Updates via `git pull`.
- **Security:** token never in the repo. `.env` gitignored; only `.env.example` is tracked. Token is a per-user secret (revocable independently) — and it identifies the owner (RC vs FC) for §3a.
- **Versioning:** repo `VERSION` + README changelog; skills are forward-compatible with the cockpit API (all mutations already version-checked).

---

## 6. Decisions

| # | Decision | Status |
|---|---|---|
| Command name | `/repuro` entry + `/repuro-queue` + `/repuro-loop` | ✅ confirmed |
| Repo | private, shared by collaborator invite link only | ✅ confirmed |
| v1 scope | done only after human verdict; "Awaits verdict" review surface with output links | ✅ confirmed |
| Ownership | tasks tagged RC/FC by `created_by`; per-owner queues | ✅ confirmed (new requirement) |
| **Auth path** | **Option B** — agent-token Caddy bypass + server lease (no UX difference vs A; B prevents double-execution under continuous loops) | ✅ confirmed 2026-06-22 |

Build plan:
- **M1** — `/repuro` + `/repuro-queue` + `cockpit_client.py` + install script; server: `created_by` + `?owner` on `/api/agent/queue`; Caddy matcher letting `/cockpit/api/agent/*` through on a valid agent Bearer token + `rd-agent`/`ff-agent` token secrets + redeploy.
- **M2** — structured evidence + "Awaits verdict" card rendering (§4a); owner badge + `t-id` on cards (§3a UI).
- **M3** — `/repuro-loop` continuous mode (§7).

## 7. Midterm model — continuous loop + browser review

The end state Roman described: each of Roman and Flo keeps **one Claude session open running `/repuro-loop`** (or the generic `/loop /repuro`), which continuously pulls their RC/FC queue, executes, and posts each result to "Awaits verdict." They never touch the terminal to review — they sit in the **cockpit browser**, watch tasks land in "Awaits verdict," and approve or send-back inline. This is why §2 Option B (server-side leases) and §3a (per-owner queues) matter: two always-on loops sharing one DB must not double-execute or cross lanes. The loop cadence and the cockpit's existing SSE refresh (`/api/events`) already give near-real-time updates in the browser.
