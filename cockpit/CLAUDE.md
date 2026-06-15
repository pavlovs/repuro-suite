# COCKPIT — Repuro PM Tool

Hosted (eventually) internal project-management tool for RD + FF: workstreams with prerequisite
readiness colors, waiting-on/chase model, computed daily/weekly recommendations, agent task queue.
Design spec: `ai/DESIGN-SPEC.md` (v5, approved 2026-06-11). Milestones: `ai/PLAN.md` + `ai/ROADMAP.md`.

## Architecture (one line)
FastAPI + SQLite (`data/cockpit.db`, journal DELETE) → JSON/MD API on localhost:8099 → Alpine.js SPA (M2+). Local-first; Fly.io at M5.

## Hard rules (inherit workspace CLAUDE.md, plus)
- **cockpit.db**: journal_mode=DELETE (OneDrive safety). Never commit. Mutations only through the API/db module — never raw writes from scripts.
- **dealroom.db is read-only here.** Open with `file:...?mode=ro` URI ALWAYS (plain connect() on a wrong path silently creates an empty db — a stray 0-byte `dealroom/dealroom.db` exists from exactly this mistake). Deal stage is mastered in dealroom.db; cockpit mirrors it.
- **Real names never enter cockpit.db** — codenames only. The codename→name map stays in the dealroom.
- **Code ownership**: FC does not edit `.py`/`.html`/`.js`/`.css` here — tickets to `TICKETS.md`, RC implements.
- **Milestone loop**: /plan-milestone → /execute-milestone → /review-milestone (separate agent) for every milestone. No milestone done without independent review.
- Port 8099 (Roman 2026-06-11). Python 3.12, venv at `.venv/`.
- **UI verification loop — MANDATORY after ANY frontend change** (Roman 2026-06-12: "I shouldn't have to find the bugs"). Loop until a round finds nothing new:
  1. Compile: node + babel.min.js transform of the full JSX bundle (catches bundle-scope errors curl can't).
  2. `pytest` (API contract).
  3. Restart server, run `CLAUDE_COWORK/cockpit-e2e/run.js` — drives real Edge, screenshots all views + journeys, collects console errors. Zero PAGEERROR required.
  4. READ the screenshots (vision) as a fresh user; fix what you see; re-run.
  5. Codex usability review only at milestone boundaries (screenshots referenced in prompt).
  Never claim a UI change done from code reading alone — the 2026-06-12 session found a server bug (deliverable gates), an invisible button, and a false-blocked display ONLY via screenshots.

## Status
- M1 backend: ✅ 2026-06-11 — API on :8099, 75 tests, 14 deals mirrored, workplan seeded (staging)
- M2+M4 frontend: ✅ 2026-06-11 — SPA at `/` (Workstreams+Blockers, Today, Timeline, Agent Queue)
- M3 agent layer: ✅ built — /cockpit-pull + /cockpit-push skills, deals.md generated block. **Trial + curation pass = Roman's part, open.**
- M5 hosting: prepared (Dockerfile, fly.toml) — deploy gated on trial verdict
- Server: auto-starts at logon (Startup `RepuroCockpit.cmd` → `start_cockpit.ps1`); manual: run the ps1
