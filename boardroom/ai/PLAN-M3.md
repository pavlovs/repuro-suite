# PLAN-M3 — Curation + publish state machine

Build after M2 ships. Adds the admin workflow: edit a draft, see a diff vs last published, clear a
blocking approval checklist, publish (archiving the prior). The two content gates (§2 of DESIGN-SPEC)
are enforced here — this is where "the investor only sees what is permitted" is operationally guaranteed.

## State machine
`draft → approved → published`, with `published → archived` when a newer one of the same kind publishes.
- Only `published` is investor-visible (M1 already enforces).
- Partial unique index `ux_pub_one_published_per_kind` already guarantees ≤1 published/kind — publish
  must archive the prior in the SAME transaction (WRITE_LOCK) before flipping the new one.

## Backend endpoints (all admin_only; all audited to audit_log)
- `PATCH /api/publication/{id}` — edit `title`, `ref`, and authored `body` fields only. Reject if status
  != 'draft' (can't edit an approved/published row; clone-to-new-draft instead). Bumps `version`.
- `GET  /api/publication/{id}/diff` — structural diff of this row's body vs the current published row of
  the same kind (added/removed/changed leaf paths). Powers the review screen.
- `POST /api/publication/{id}/approve` — body: `{checklist: {no_pre_loi_names: true, no_other_investors:
  true, figures_stamped: true}}`. ALL must be true or 400 with the missing acks. Also runs an automated
  pre-check (below); if it finds a violation, 409 with the offending paths — approval cannot proceed.
  On success: status='approved', approved_at/approved_by set, acks written to audit_log.
- `POST /api/publication/{id}/publish` — requires status='approved'. Transaction: archive prior published
  of same kind → set this published + published_at. 409 if not approved.
- `POST /api/publication/{id}/unpublish` (optional) — published → archived (pull a bad update fast).

## Body schema validation at publish (belt-and-suspenders — from M2 review)
Because `/api/published` returns the whole `body`, the body IS the investor allowlist. Add
`src/gates.py: validate_body(kind, body)` enforcing the exact key sets per §4.1/§4.2 (funnel item keys,
batch row keys, live_deal keys, milestone keys, fundraising keys, board kpi keys). `publish` calls it and
**refuses (409) any body containing a key outside the contract** — so even a hand-edited M3 draft can't
introduce a stray DB/internal field. Strip-or-reject: reject (fail closed), report the offending paths.

## Automated pre-checks at approve (defense in depth, not a replacement for human acks)
- **no_pre_loi_names:** assert no funnel item contains a `name`/`company_name` key (structural).
- **no_other_investors:** scan all string values in body for a denylist {ASF, Aurica, Arbor, and any
  configured competitor-investor tokens}; flag matches. Denylist in `src/gates.py`, case-insensitive.
- **figures_stamped:** every numeric block referenced in `stamps` has a source + as_of; flag unstamped.
These are advisory-blocking: a hit returns 409 so the admin must fix or consciously override (override
requires an explicit `?force=1` that is itself audited — never silent).

## Frontend (minimal admin curation view)
- Admin-only screen (gated by role from a new `GET /api/whoami`): list drafts, open one, edit authored
  fields (narrative, fundraising.{tax_structure,sources_uses,capital_plan}, per-live-deal commentary/
  earnout/dd_status/close_target, board agenda/decisions/pre_read/minutes/meeting), show the diff, run
  approve (checklist modal) → publish. Keep it functional, not pretty (polish = M4).
- Investor view unchanged.

## Tests
- PATCH rejects edits to non-draft; edits only whitelisted fields; bumps version.
- approve: missing ack → 400; denylist hit (inject "Aurica" into narrative) → 409; clean → approved.
- publish: non-approved → 409; publishing archives the prior published of same kind (assert exactly one
  published per kind after); investor sees the new one.
- whoami returns role; investor → 403 on all curation endpoints.
- full lifecycle: assemble → patch authored → approve → publish → investor read shows authored content.

## Open for Roman
- Final denylist of competitor-investor tokens (ASF, Aurica, Arbor + others?).
- `?force=1` decision RESOLVED in build: force overrides ONLY the soft figures-stamped gate; the
  denylist + pre-LOI-names + validate_body are HARD (never forceable) and re-run at publish. Confirm.

---

## VALIDATION RESULTS (2026-06-20)
Built: `src/gates.py` (denylist scan, pre-LOI check, complete recursive `validate_body`), 6 endpoints
(whoami/PATCH/diff/approve/publish/unpublish), CurateTab UI + role-gating. **81 tests pass.**
- Adversarial live check (12 assertions) + visual screenshots (investor Updates/Board, admin Curate) all good.
- **Codex M3 review #1: BLOCK** — 5 criticals, all fixed:
  1. Denylist was soft (forceable) + not re-run at publish → other-investor content could publish.
     FIX: hardness split — denylist/pre-LOI/validate_body HARD (no force), re-run at publish.
  2. `validate_body` was a partial allowlist (nested keys unchecked) → extra raw-DB keys could leak.
     FIX: complete recursive schema allowlist, rejects any non-contract key at every level.
  3. board_pack validation incomplete. FIX: BOARD_SCHEMA covers meeting/agenda/decisions/pre_read/kpis.
  4. TOCTOU (status checked outside lock). FIX: read-check-update inside WRITE_LOCK, status-guarded
     `UPDATE ... WHERE id=? AND status=?` + rowcount==1.
  5. Denylist false-negatives (values-only, ASCII-only). FIX: scan keys+values, NFKC + zero-width
     normalize, boundary excludes '_' (catches `aurica_note`).
  Plus: audit records `body_sha256`; CurateTab blocks hard violations (no force button), force only for soft.
- New regression tests added: nested-extra-key bypasses (project_update/pipeline/sources_uses/board),
  key-name denylist, zero-width/unicode, publish-is-the-wall (DB-tampered approved body → 409), patch-
  after-approval 409, force-can't-override-denylist, force-overrides-only-soft.
