# INVESTOR ROOM — Build Loop Ledger

Autonomous build loop started 2026-06-20. Local only, no commit, no Fly deploy.
Method: project-methodology (plan → implement → review → codex). Codex review is a hard
gate — on failure, improve and re-review, never skip.

## Status board
| M | State | Notes |
|---|-------|-------|
| M1 — security wall + read view | DONE | Codex SHIP; 21 tests; live matrix verified |
| M2 — auto-assembly | DONE | Codex CONFIRMED; 40 tests; live scan clean |
| M3 — curation + publish | DONE | Codex CONFIRM; 82 tests; hard gates re-run at publish |
| M4 — export/polish | DEFERRED | optional; awaiting Roman steer |

## Iteration log
- **2026-06-20** Spec v2 (rename Boardroom→Investor Room `/investor/`, add Board part). Scaffolding done.
- **2026-06-20** M1 built (Sonnet subagent, mirrors Cockpit): boardroom.py CLI, src/{db,api,models}.py, static/{index.html,app.jsx,investor.css,vendor}, tests. 14 tests pass.
- **2026-06-20** Independent verify: live 403/role matrix passed (investor 403 on list/detail, 401 no-principal, published-only). Fixed seed idempotency (DELETE before insert).
- **2026-06-20** Codex review #1 (gpt-5.4 high): **BLOCK**. 2 blockers: (1) `/api/published` leaked id/status/approved_by/version/timestamps to investor; (2) `open_readonly()` weak Windows/space URI. Fixed both + partial-unique-index, fail-loud body parse, milestones UI render. Tests 14→19. Live re-verify: investor payload now allowlisted (body,kind,published_at,ref,title), zero leak.
- **2026-06-20** Codex review #2 (re-review, gpt-5.4 medium): **REVISE** (up from BLOCK). Both blockers confirmed fixed. One remaining: `_parse_body` leaked row `id` in the 500 `detail` to investor. Fixed (generic message + server-side log). Strengthened 3 tests (corrupt-body asserts no-id; open_readonly missing-path + spaces-path; broader fixture). Tests 19→21. JSX compiles clean (node+babel). Codex review #3 (confirm) running.
- **2026-06-20** M2 recon done: inspected real dealroom/pipeline/cockpit DBs (read-only); PLAN-M2.md written with grounded queries. Live-deal stage = loi_signed (Fox); batch stats real (BA1-9, meeting=26); cockpit deliverables all open + mostly null target_date (timeline data gap flagged).

- **2026-06-20** M2 built (Sonnet subagent): src/sources.py, src/assemble.py, POST /api/assemble (admin-only), tests. Caught + fixed a generator blind spot: assembled body shape diverged from M1 read-view contract — would render blank after publish. Reshaped + added round-trip regression tests. Live security scan: no company_name/seller/thesis in funnel; live_deals post-LOI only.
- **2026-06-20** Codex M2 review #1 (gpt-5.4 medium): **BLOCK**. Funnel anonymization/read-only/auth all confirmed clean. But live_deals leaked ev_m_note/status_override/description and milestones leaked deal/comment into the body (= investor allowlist, since /api/published returns body whole); milestones_done used target_date not date. Fixed: strict contract key sets on live_deals/milestones/batches, done→date, ba.upper() str-guard, strict-key tests. 40 tests pass; live security re-verified. Codex M2 confirm running. Architectural takeaway → M3 gets a publish-time `validate_body()` (reject any non-contract key, fail closed).

- **2026-06-20** M3 built (Sonnet subagent): src/gates.py (denylist scan, pre-LOI name check, validate_body exact key-sets), 6 endpoints (whoami/PATCH/diff/approve/publish/unpublish), CurateTab UI + whoami role-gating. 71 tests. My adversarial live check (12 assertions) ALL PASS: investor 403 on all curation endpoints; validate_body catches injected extra key (409); denylist catches Aurica (409); force=1 overrides denylist (by design) but publish archives prior → exactly 1 published/kind; investor payload allowlisted.
- **2026-06-20** VISUAL verification via Playwright+Edge screenshots (suite UI rule): investor Updates (anonymized funnel EAGLE/OWL/PANDA + batch stats + live-deal cards), investor Board (meeting/KPIs/agenda/APPROVED decisions), admin Curate (admin badge + draft list). Nav gating correct (investor=[Updates,Board], admin=+Curate). Only a harmless favicon 404. Lesson: X-Remote-User carries the CADDY username (investor/roman), not the internal id (strada/rd) — test harness must use the map key.
- **2026-06-20** Codex M3 confirm #2: **REVISE** — 5/5 criticals confirmed fixed; one residual: `stamps` was a free-key map (`_Map` validated values not keys) → `stamps.secret_debug` could reach investor. FIX: removed `_Map`, stamps now an exact key allowlist (weekly: pipeline.funnel/pipeline.batches/live_deals/project_update.milestones; board: kpis). No free-key map remains anywhere. Test added; real assembled data still CLEAN; 82 tests. Codex M3 final confirm running.
- **2026-06-20** Codex M3 review #1 (gpt-5.4 medium): **BLOCK** — 5 criticals (all valid, all fixed): (1) denylist soft+not-re-run-at-publish → other-investor could publish; (2) validate_body partial allowlist → nested extra keys leak; (3) board validation incomplete; (4) TOCTOU on status; (5) denylist false-negatives. Fixes: hardness split (denylist/pre-LOI/validate_body HARD, re-run at publish, no force; only figures_stamped soft-forceable); complete recursive validate_body (WEEKLY/BOARD schema, rejects any non-contract key at every level); status-guarded atomic UPDATEs inside WRITE_LOCK; denylist scans keys+values, NFKC+zero-width normalize, '_'-boundary; audit body_sha256; CurateTab blocks hard (no force btn). 81 tests (added nested-bypass, key-name, zero-width, publish-is-the-wall, patch-after-approval). Codex M3 confirm running.

## Struggles / blockers
- Background servers from prior Bash calls orphan (each Bash call = fresh shell, `kill %1` doesn't carry). Mitigation: kill by port via PowerShell `Get-NetTCPConnection 8084`. Watch for stale servers serving old code during verify.
- Codex sandbox denied pytest temp-dir access → its review is source-inspection only; I run pytest myself for the test gate.

## Open topics for Roman
- Stage threshold for real names = `loi_signed` (confirm vs `due_diligence`).
- Board pack: who chairs / cadence / what KPIs Strada expects (drives M2 board KPI pull).
- `AUTH_INVESTOR_HASH` Fly secret + Strada credentials — needed before any real deploy.
