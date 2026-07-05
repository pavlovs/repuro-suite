# SPEC — Cockpit Agentic Workflow v2 ("one queue, one runner, one review surface")

Status: **APPROVED 2026-07-02 (Roman, decisions in §8) — in build.** Author: Claude · Date: 2026-07-02
Trigger: Roman — "the agentic view we built is mediocre and not really usable; I want an
agentic workflow in COCKPIT which actually makes sense instead of a mixture between CLI
commands and cockpit commands."

---

## 1. Diagnosis — why the current setup feels mediocre

The Agents *view* has been specced and rebuilt twice (SPEC-agents-view.md, commit
b6c073d). The pixels are not the problem. The *workflow around it* was never designed
as one system, so today Roman is the courier between four half-systems:

| # | Fragment | Problem |
|---|---|---|
| 1 | **Two agent queues** | Cockpit agent tasks (prod, Fly) AND `TASKS.md [AGENT]` (COWORK, consumed by `/agent-loop`). Same concept modeled twice: two backlogs, two blocker conventions (`input_question` vs `loop-state.md`), two run protocols. |
| 2 | **Manual task-by-task execution** | `/repuro:run <id>` runs ONE task and stops. Roman must open a terminal, pick a task, type a command, wait — per task. The §7 end-state of SPEC-agent-skills-repo (continuous loop) was M3 and never built; the plugin has only `setup / queue / run`. |
| 3 | **Send-back goes nowhere** | "Request changes" re-queues in the DB, but nothing picks it up until Roman *again* types `/repuro:run` in a terminal. The review surface writes into a queue no one is draining. |
| 4 | **Dead/dangerous sync skills** | `/cockpit-pull` + `/cockpit-push` still target `localhost:8099` — the diverged local DB that prod rules say must never receive real changes. Any session that follows them reads or mutates the wrong world. |

Net effect: the browser view is a nice dashboard over a queue that only moves when
Roman hand-cranks it from the CLI. That is the "mixture" — and no view redesign fixes it.

## 2. Target model — division of labor, stated once

- **Browser (cockpit) = the ONLY human surface.** Create agent tasks, order the queue,
  answer blockers, give verdicts. Roman never opens a terminal *for the agent workflow*.
- **One unattended runner = the ONLY executor.** A loop (headless Claude) that drains
  the cockpit queue: claim → execute → post evidence → next. Send-backs and answered
  blockers are just re-queued items — the same loop picks them up on its next pass.
- **Cockpit prod DB = the ONLY state.** No `TASKS.md [AGENT]`, no parallel blocker log.
  `loop-state.md` shrinks to a private resume pointer for the runner, nothing Roman reads.
- **Any Claude session can FEED the queue, none needs to WORK it.** While Roman works
  in a normal session: "push that to the agent queue" → one client call. No `/cockpit-push`
  markdown payloads, no version juggling.

The verdict model (done ONLY after human approval, evidence-first review cards,
RC/FC lanes, server leases) is already built and stays unchanged — it was the right part.

## 3. Changes, by component

### 3a. Plugin (`repuro-cockpit-skills`) — the runner + enqueue

1. **`/repuro:loop [--max-tasks N]`** — the missing M3 command. Protocol = merge of
   `run.md` + the good parts of `/agent-loop`:
   - Fresh `queue` fetch → claim next READY task in own lane (skip blocked) → execute →
     verify against AC (max 2 self-correction loops) → `result` with structured evidence
     → next. Stop when queue empty / all blocked / max-tasks hit; then post a 1-block
     run report (done / blocked / skipped) as a cockpit comment or evidence note.
   - **Blocked ≠ ask.** Needs Roman's input → PATCH task to `blocked` +
     `input_from` / `input_question` (fields exist in schema v4) → next task. The
     blocker surfaces in the cockpit "Decisions & waiting" view, NOT in a side file.
   - Model routing per execution.md: loop runs on Sonnet; judgment-heavy task → ONE
     Fable subagent with full context; never split a chain.
   - Honors `runner` field: `local` tasks only when running on the laptop (OneDrive
     files, Office COM, local DBs); `any` runnable anywhere.
2. **`cockpit_client.py add`** — create an agent task from any session
   (`add --text ... --ac ... --deal ... --runner local|any [--deliverable d-n]`).
   AC required — the client refuses agent tasks without acceptance criteria.
3. `run.md` stays for one-off "do exactly this task now" — it's the manual override,
   no longer the primary path.

### 3b. Scheduling — who cranks the loop

- **Phase 2 (recommended default): laptop, scheduled.** Windows Task Scheduler runs
  `claude --model sonnet -p "/repuro:loop --max-tasks 3"` at logon + 13:00 (cockpit
  server already auto-starts at logon the same way). Zero new infra; covers `runner:
  local` tasks, which is most Repuro work (OneDrive + COM).
- **Phase 3 (optional): cloud devbox** (Hetzner box, pi harness — already provisioned)
  runs the same loop always-on for `runner: any` tasks only. Two runners can't collide —
  server leases + lane + runner filter already prevent double-execution.
- Until Phase 2 ships, Roman types exactly ONE command a day: `/repuro:loop`. That is
  the whole CLI surface.

### 3c. Queue unification — kill the second queue

- Migrate open `TASKS.md [AGENT]` items → cockpit agent tasks (one-time, with AC).
- `TASKS.md` keeps [ME]/[TOGETHER]/[WIP] only; new rule: agent work goes to the
  cockpit, not TASKS.md.
- `/agent-loop` retired → thin alias that says "use /repuro:loop" (grace period), then deleted.
- Update `execution.md` / routing rules accordingly (COWORK side, Roman's `~/.claude`).

### 3d. Retire / retarget the sync skills

- `/cockpit-push` for agent work → replaced by `cockpit_client.py add`.
- `/cockpit-pull` for context → replaced by `queue` (already prod-targeted via plugin).
- If a general MD export/import path is still wanted for non-agent tasks, retarget the
  skills to prod (REMOTE-API or an authenticated prod endpoint) — but they must stop
  pointing at :8099 either way. Recommendation: retire; the plugin client is the one door.

### 3e. Cockpit UI — only two surgical deltas (no third redesign)

1. **Blocked-with-question cards get an inline answer box**: Roman types the answer →
   task flips `blocked → open` with the answer appended to `detail`. Closes the
   blocker loop entirely in the browser. (Also render these in Agents view Queue
   section, badge "Waiting on you", not only in Decisions & waiting.)
2. **Quick-add with execution=agent requires AC + runner** (local/any picker,
   default local). A task an agent can't verify shouldn't be enqueuable.

Everything else in the Agents view stays as built (review cards, lanes, verdict bar).

## 4. The day-in-the-life after this ships

1. Anytime (browser or any Claude session): Roman enqueues agent tasks with AC.
2. Runner drains the queue on schedule; results land in **Needs your review**;
   blockers land as **Waiting on you** questions.
3. Roman, in the browser only: approves / requests changes / answers questions.
   Send-backs and answers are picked up on the runner's next pass automatically.
4. Morning brief reports: N awaiting verdict, N waiting on you, N done since yesterday.

Zero terminal involvement in steady state. Flo gets the identical flow via his token.

## 5. Phasing

- **Phase 1 — unify (1 session):** `/repuro:loop` + `client add` + blocker→cockpit
  protocol; migrate TASKS.md [AGENT]; retire/redirect `/agent-loop`, `/cockpit-pull`,
  `/cockpit-push`. Manual daily `/repuro:loop` kick.
- **Phase 2 — unattended (small):** Task Scheduler job (logon + 13:00). UI delta 3e-1/2.
- **Phase 3 — optional:** devbox always-on runner for `runner:any`; notification digest.

## 6. Decisions for Roman (batched)

| # | Decision | Recommendation |
|---|---|---|
| 1 | Kill `TASKS.md [AGENT]` queue in favor of cockpit-only? | **Yes** — one queue or the mixture persists |
| 2 | Runner home | **Laptop scheduled** (Phase 2); devbox later only for `any` tasks |
| 3 | Retire `/cockpit-pull` + `/cockpit-push`? | **Retire** — plugin client is the one door; they point at a dead DB today |
| 4 | AC mandatory on agent-task creation? | **Yes** — unverifiable tasks are the #1 cause of mediocre agent output |
| 5 | Scope now | **Phase 1 + 2 together** — Phase 1 alone still leaves Roman hand-cranking |

## 7. The review → back-to-work loop — visual + technical (added on Roman's request)

The heart of the workflow: what happens after the agent posts a result, in the UI and
on the wire. One state machine, every edge is one API call, every transition pushes an
SSE event so the card physically moves between sections in the open browser tab —
no reload, no terminal.

### 7a. State machine

```
        create (quick-add / client `add`)
              │
              ▼
   ┌───────► open ───────── claim ─────────► in_progress
   │          ▲            (runner)               │
   │   answer │                       ┌───────────┼───────────────┐
   │ (browser)│                       │           │               │
   │          │                    block        result       4h lease expiry
   │       blocked ◄──────────────────┘           │          (auto-reaped → open)
   │    (question for you)                        ▼               │
   │                                          in_review ◄─────────┘
   │  Request changes (feedback, round+1) ────────┤
   └──────────────────────────────────────────────┤
      Reject → open + execution flips to "me"     │ Approve
      (leaves the agent queue — see 7d)           ▼
                                                done
```

### 7b. Each edge on the wire

| Transition | Actor | Call | What gets stored |
|---|---|---|---|
| open → in_progress | runner | `POST /api/agent/claim/{t}` | `claimed_by`, 4h lease |
| in_progress → in_review | runner | `POST /api/agent/result/{t}` | `evidence` (markdown: summary + artifact links), idempotency-keyed |
| in_progress → blocked | runner | `POST /api/agent/block/{t}` **(new)** | `input_from` + `input_question`, claim released |
| blocked → open | human, browser | `POST /api/task/{t}/answer` **(new)** | answer appended to evidence (`ANSWER (rd): …`), question cleared |
| in_review → done | human, browser | `POST /api/task/{t}/approve` | `done_at` |
| in_review → open (redo) | human, browser | `POST /api/task/{t}/request-changes` | `review_feedback`, `review_round`+1, feedback appended to evidence |
| in_review → open + `execution=me` | human, browser | `POST /api/task/{t}/reject` | rejection note; task LEAVES the agent queue (7d) |

Two server gaps close to make the loop lossless:
1. **`/api/agent/queue` now returns `review_round`, `review_feedback`, `evidence` and
   readiness** — a sent-back task arrives at the runner WITH the feedback and the full
   round-1 evidence trail. Today the queue omits them, so round 2 would start blind.
2. **SSE `_broadcast` fires on claim / result / block** (today only on human actions) —
   the browser's `refreshFromServer()` runs and the card moves live: Queue → Running →
   Needs your review, or Running → Waiting on you.

Queue order = what you see: the endpoint orders by `sort_order, id` — identical to the
Agents view — so "next task the runner picks" is always the top card on screen.

### 7c. What Roman sees (per section of the Agents view)

- **Needs your review** (`in_review`) — full-width card, unchanged layout: AC
  checklist, evidence rendered as markdown with links, artifact preview pane,
  feedback box + Approve / Request Changes / Reject / Escalate. On *Request
  changes* the card visibly re-enters Queue with a **Round N** badge and the
  feedback line shown on the queue card — you can see your own instruction riding
  with the task.
- **Waiting on you** (**new section**, `blocked` + `input_question`, placed directly
  under Needs your review) — the agent's question, an inline answer box, one
  **Answer & requeue** button. Submitting flips it back to Queue as ready; the runner
  picks it up next pass with your answer in the evidence trail.
- **Running** (`in_progress`) — claimed_by + lease freshness, as built.
- **Queue** (`open`) — position #, ready/blocked-by-prereq, Round-N badge on redos.

The full circle, zero terminal: agent posts → card slides into *Needs your review* →
you type feedback → *Request changes* → card slides into *Queue* with Round 2 badge →
scheduled runner claims it → *Running* → posts → back in *Needs your review*. Same
for questions: *Waiting on you* → you answer inline → *Queue* → next pass.

### 7d. Reject semantics fix (found during build-spec)

Today Reject re-opens the task **still on the agent queue** with no new guidance — an
unattended loop would re-execute the identical failure forever. Fix: Reject now also
flips `execution → me`, i.e. "this result is unusable / this was never agent work —
take it off the lane." Redo-with-guidance is exclusively *Request changes*; Escalate
(→ `together`) already leaves the lane. Every in_review exit is now loop-safe.

### 7e. Runner cycle (the other half of the loop)

`/repuro:loop` each pass: fetch queue (own lane) → take top **ready** task (skips
unmet hard prereqs — readiness now included in the queue payload) → claim → if
`review_round > 0`, read `review_feedback` + prior evidence FIRST and address the
feedback explicitly → execute → verify against AC (max 2 self-correction loops) →
post result (or `block` with a precise question) → next. Stops when no ready tasks
remain or `--max-tasks` hit; ends with a one-block run report. Scheduled at logon +
13:00 → send-backs from the morning get picked up midday, midday answers by next
logon; ad-hoc `/repuro:loop` anytime for an immediate drain.

## 8. Decisions — FINAL (Roman, 2026-07-02)

| # | Decision | Verdict |
|---|---|---|
| 1 | Kill `TASKS.md [AGENT]` queue | **YES** — migrate to cockpit, retire `/agent-loop` |
| 2 | Runner home | **Laptop scheduled now**; devbox later (not now) → `runner` picker in UI deferred, everything defaults `local` |
| 3 | Retire `/cockpit-pull` + `/cockpit-push` | **YES** (Claude's call, approved) |
| 4 | AC mandatory | **YES** (already enforced in quick-add + server; client `add` enforces too) |
| 5 | Scope | **Phase 1 + 2 together** — build until Roman AND Flo can start the loop |

AC for the build: the loop works end-to-end and Roman can start the agentic workflow
after the build — and Flo can too (plugin update via GitHub, no new setup beyond his
existing token).

## 9. Validation results (built 2026-07-05, same session)

- **Shipped**: suite v2.1.15 on Fly (commits c7f2d58 + 3acdd0f + 1c490b7); plugin
  v0.3.0 pushed (eb040e0). All 4 backends 200 post-deploy; all routes 401 unauth.
- **Tests**: 102 pytest (was 99 pre-existing +13 new for the loop endpoints/readiness);
  JSX bundle babel-compiles; e2e 0 pageerrors.
- **Codex review**: 3 rounds → PASS. R1 found 2 real defects (claim didn't enforce
  readiness server-side; dropped-deliverable prereqs never cleared), R2 found the
  resolver still diverged from canonical state (children-done deliverables). All
  fixed with regression tests.
- **Latent bug fixed en passant**: DDL lacked migration-10 columns — fresh DBs
  (tests, new installs) broke on preview/review fields.
- **Live UI verification (screenshots read)**: review card with evidence+verdict bar;
  Waiting-on-you card with inline answer → live requeue (toast, SSE refresh);
  Round-2 badge + feedback line on send-back card; blocked tasks no longer hide in Queue.
- **Prod smoke**: `queue` returns new fields against live Fly (7 real RC tasks);
  t-424 executed by a headless Sonnet run (`claude -p "/repuro:run t-424"`, the exact
  scheduler path) → artifact created → in_review on prod.
- **Phase 2 live**: scheduled task `RepuroAgentLoop` (logon+5min, daily 13:00) →
  `CLAUDE_COWORK/scripts/run-repuro-loop.ps1`, logs to Claude_Context/runner-logs/,
  runs `--permission-mode bypassPermissions` (nobody watching; hard boundaries live
  in the loop skill — flag to Roman if he wants it tighter).
- **Queue unification done**: TASKS.md [AGENT] items migrated → t-420..t-423 (ASF
  business case NOT migrated — ASF dead 01.07, flagged for drop-confirmation);
  /agent-loop, /cockpit-pull, /cockpit-push retired to pointer stubs; execution.md +
  routing.md updated.
- **Open (deferred by decision)**: devbox runner for `runner:any` (Phase 3);
  `runner` picker in quick-add (everything defaults `local` until devbox exists).

## 10. Round 2 (2026-07-05, same day) — artifact previews + curated playbook

Trigger: Roman — "why is the .md not directly loaded in the review? how do I review
a PDF/Excel/LOI?" + go on the learning loop ("must not blow up into unusable feedback").

- **Artifact previews**: the reviewer sees the ACTUAL output in the review card —
  `.md` rendered inline, `.pdf` embedded, images direct; Office artifacts exported
  to PDF by the runner before upload (`preview` client cmd → agent door
  `POST /api/agent/upload-preview/{id}`, live-claimant-gated). Mandatory runner
  step before `result`.
- **Curated playbook** (ACE-style generate→reflect→curate, human as curator):
  runners submit ≤1 one-line candidate lesson per run (only from redo rounds /
  answered questions, general rules only); Roman adopts/edits/dismisses in the
  Agents view; active rules (constraints binding, heuristics defaults, HARD CAP
  40) ride with every queue fetch. Anti-blow-up guards: cap, dedupe (submission
  AND promotion), one-line limit, human gate, "if in doubt submit nothing".
- **Codex 4 rounds → PASS**; fixed en route: agent-writable human preview door,
  post-result preview overwrite, markdown href XSS, stored-XSS via .html previews
  (support removed), X-Remote-User header spoof (COCKPIT_TRUSTED_PROXY opt-in on
  principal + SSE), promote-dedupe gap, LessonRow SSE staleness.
- **Deployed**: suite v2.1.16; plugin v0.4.0. 107 pytest, bundle compile, e2e
  0 pageerrors, screenshots read (md preview card, lessons strip, playbook).
- **First candidates seeded on prod** (l-1 adjusted-EBITDA, l-2 audience number
  format) — awaiting Roman's Adopt as the first curation act.
