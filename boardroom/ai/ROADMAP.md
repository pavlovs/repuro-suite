# INVESTOR ROOM — Roadmap

Spec: `ai/DESIGN-SPEC.md` (v2). Single-tenant **Strada** investor room at `/investor/`.
Two parts: **Updates** (weekly investor update) + **Board** (board-meeting prep).
Module folder is `boardroom/` on disk; product/route/auth-user = `investor`.

## Milestones

- ✅ **M1 — Security wall + read view** (2026-06-20) — Investor process on :8084,
  `investor.db` (`publications` table), principal/roles, read-only Updates + Board view of
  hand-seeded published rows, admin index. 21 tests; live 403/role matrix verified;
  investor payload allowlisted (no metadata leak); `open_readonly` robust. Codex: SHIP
  (BLOCK→REVISE→SHIP). Caddy/supervisord/fly deltas specced (§6), not yet deployed.
- ✅ **M2 — Auto-assembly** (2026-06-20) — `src/sources.py` + `src/assemble.py` +
  `POST /api/assemble` (admin-only draft). Pulls funnel/batches/live-deals/milestones/board-KPIs
  from the 3 ro DBs with stamps. Strict contract key sets (body = investor allowlist). 40 tests;
  live security scan clean (no funnel name/seller leak; post-LOI only). Codex: CONFIRMED
  (BLOCK→CONFIRMED). Data gaps surfaced in PLAN-M2 (dealroom sector/EV nulls, thin cockpit timeline).
- ✅ **M3 — Curation + publish** (2026-06-20) — `src/gates.py` (denylist + pre-LOI + complete
  recursive `validate_body` allowlist), 6 admin endpoints (whoami/PATCH/diff/approve/publish/unpublish),
  CurateTab UI + role-gating. Hard/soft gate split (denylist/pre-LOI/validate_body never forceable,
  re-run at publish; only figures-stamped soft-forceable). Atomic status-guarded transitions, audit
  body-hash. 82 tests + adversarial live check + screenshots. Codex: CONFIRM (BLOCK→REVISE→CONFIRM).
- ⬜ **M4 — Polish + PDF/email export** (deferred).

## Current state
Spec v2 written 2026-06-20. Building M1 locally (autonomous loop). Ledger: `ai/loop-state.md`.
