# INVESTOR ROOM — Strada

Single-tenant, authenticated investor module for the co-investor **Strada**. Served from
the suite at `/investor/`. Two parts: **Updates** (weekly investor update) + **Board**
(board-meeting prep). Spec: `ai/DESIGN-SPEC.md`. Roadmap: `ai/ROADMAP.md`.
Module folder is `boardroom/` on disk; product/route/auth-user = `investor`.

## Architecture (one line)
FastAPI + SQLite (`/data/investor.db`, journal DELETE) on :8084 → suite Caddy `/investor/*`
with X-Remote-User auth. Investor sees only approved, published `publications`; never a live DB.

## Investor view HTML — edit templates/, never a monolith
`GET /` is assembled at request time from `templates/` (shell + `sections/act*.html` +
`deals/{fox,mantis,mouse,cat,_overview}.html`) by `_assemble_page()` in `src/api.py`.
Weekly edits go into the small per-deal/per-act files — see the edit map in
`SPEC-investor-split.md`. Deal files hold one fragment per view behind
`<!-- ONEPAGER/SCORECARD/SU/VALUATION -->` markers. The old monolith
(`static/index.html.pre-split.bak`) is rollback-only — do NOT edit it.

## Hard rules (inherit suite + cockpit CLAUDE.md, plus)
- **Permission is the product.** `investor` principal: 403 outside `/investor/*` (Caddy CEL),
  and reads only `status='published'` publications — never drafts, never live DBs.
- **Source DBs are read-only here.** Open dealroom/pipeline/cockpit with `file:...?mode=ro`
  ALWAYS. Boardroom never writes them.
- **Two content gates, enforced at approve, fail-closed:** (1) no pre-LOI real names —
  pipeline is codename + band only; post-LOI deals may use real names. (2) no other
  investors (ASF/Aurica/Arbor/any third party) ever published.
- **Every figure carries `{source, as_of}`.** No unstamped numbers publish. NO_FABRICATION:
  authored sections (tax structure, S&U, narrative) are written, never auto-invented.
- **`investor.db` never committed.** `AUTH_INVESTOR_HASH` is a Fly secret, never in repo.
- **Milestone loop + suite UI-verification** apply (independent review; 403 matrix verified
  by running it, not by reading code).
- **English number convention throughout** — dot decimals (`4.9x`, `0.36 M€`), comma thousands (`5,433`), dates as `02 Jul`. Strada reads English. No German formatting anywhere in this document. Do NOT "fix" dot decimals to commas, and do NOT invent per-section format zones.
