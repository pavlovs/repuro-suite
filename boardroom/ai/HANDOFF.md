# Investor Room — session handoff (2026-06-23)

Resume the **Strada × Repuro weekly co-investor-call view** (`/investor`, on disk `boardroom/`).
Goal: a deck-style web view to structure a 15–60 min investor call, REUSING the suite formats
(Dealroom table/one-pager, Cockpit timeline, Allex funnel) filtered for the investor — only the
summary/Sankey visuals are new. CI-compliant, answer-first.

## Where things stand
- **Backend M1–M3 built + Codex-passed** (`boardroom/src/` api/db/gates/assemble, ~82 tests): security
  wall, curate→approve→publish, hard content gates, read-only assembly from the 3 DBs. Still valid as
  the **data/permission layer** the final UI wires into. NOT deployed.
- **The visual is being designed as static mockups** in `boardroom/review/proposal-fresh-v*.html`.
  **Latest = `proposal-fresh-v7.html`** (open via file://). v1→v7 = many aesthetic iterations.
  The mockup is NOT yet wired into the live app — it's the design we'll port once locked.
- **Design system = `context/repuro-ci.css`** (single source of truth): CI tokens (`var(--ci-*)`
  palette + `--ci-font`) + type scale (`h1`–`h4`, `.label`, `.figure`) + components (`.card`, `.btn`,
  `.badge`, `.section-band`, spacing/radius). Enforced by a rule in `CLAUDE_REPURO/CLAUDE.md`
  (import it, use only these classes/vars — never raw hex/fonts/bespoke sizes). No enforcement script
  (Roman rejected a .py hook as over-engineered — the tokens + rule ARE the enforcement).

## v7 structure (the approved direction)
- Top bar: **white Repuro logo × STRADA** (STRADA = text placeholder — NEED the real Strada logo file).
- Agenda nav: This week · Live deals · Pipeline · Decisions. **Timeline = sticky collapsible
  "PATH TO SIGNING" strip** under the nav (always-on, Expand toggle).
- **01 This week:** 3 **vertical** boxed updates (number-left) + 2 decision previews. (Roman wants these
  VERTICAL — agents keep defaulting to horizontal; do not revert.)
- **02 Live deals:** Fox/Mantis toggle → Dealroom one-pager 2×2 quadrants + financials/EV-bridge/red-flags.
- **03 Pipeline:** batch filter + **Sankey** + verbatim Dealroom "Live Deal Portfolio" table + stage spread.
- **04 Decisions:** 2 boxed cards — category header / LEFT chart-or-KPIs (skippable) / RIGHT 3–5 bullets /
  footer concrete ask + Approve·Hold·Discuss buttons. NO inline "curated/placeholder" commentary.
- Bottom: **Data provenance** (REAL / CURATED / MISSING) — Roman's exact wording; keep provenance ONLY here.

## OPEN ITEMS to fix next session (Roman's outstanding feedback)
1. **Sankey must be 100% real, redone to the true structure.** Allex funnel (Sent 411 / Replies 362 /
   Meetings 26) is real per briefaktion. The right side: join Allex→Dealroom by `domain` (script:
   `C:\Users\X1\AppData\Local\Temp\join_check.py`). Findings: **9/12 deals match Allex; 3 sourced outside
   Allex (Wolf, Mouse, Swordfish); only 5/26 meetings became tracked deals; and Allex `outreach_status`
   FREEZES once a lead graduates to the Dealroom** (e.g. Mantis = loi_signed but Allex still says
   followup1) — so you CANNOT read deal stage from Allex status. Real Sankey = Sent→Replies→Meetings →
   {entered Dealroom (domain-matched → real CURRENT dealroom stage) vs no-deal drop-off} + small
   separate inflow for the 3 non-Allex deals. Annotate stage nodes with real €EV. The current v7 Sankey
   was built on the vaguer earlier spec — **rebuild it to this.**
2. **Decision boxes** — verify v7 matches Roman's spec (header=category only; left KPIs/chart skippable;
   right 3–5 bullets; footer ask + 3 buttons; zero noise). Roman will spec the 6–7-flag table separately.
3. **Strada logo** — need the real asset (white/transparent ideal). Placeholder text in place.
4. **Font decision** — CI doc says **Arial** (v7 uses it) but suite web tools use **Inter**. Roman to pick
   the canonical web font → flip the single `--ci-font` line in `repuro-ci.css`.
5. **Pipeline boundary calls (still open)** — the verbatim Dealroom table shows competitive Comment text
   ("Lost on price — strategic buyer bid 1M€ more", junk "xz/xyz") and **exact pre-LOI financials**.
   Roman to decide: strip/keep the comments, band/keep the pre-LOI figures.
6. **Design-system sizes** — confirm H1 30 / H2 22 / H3 17 / body 14.5 etc. or go bigger on headers.
7. **Eventually:** port the locked mockup into the live `/investor` app (replace the M1 frontend, keep the
   M1–M3 backend as filtering/permission layer), then deploy (needs `AUTH_INVESTOR_HASH` + Strada creds +
   on-Fly 403-matrix verify). Suite deltas staged in `boardroom/deploy/`.

## Real data sources
- `dealroom/data/dealroom.db`: `deals` (codename/stage/onepager_q1/q3/q4/headline/footnote; rev/ebitda/ev
  overrides mostly NULL), `deal_financials` (real Fox/Mantis figures, value_k in K€), `deal_dd_items`
  (Mantis 21 risk items; Fox 0 — pre-DD), `deal_valuations`.
- `lead-pipeline/data/pipeline.db`: `company_records` (briefaktion, outreach_status, domain).
- `cockpit/data/cockpit.db`: `deliverables` (most target_date NULL → timeline sparse).
- Fox=Com2Med(com2med.de), Mantis=Endoberatung(endoberatung.de); both loi_signed (post-LOI = real names).

## Render / verify
- Playwright (Edge) via `C:/Users/X1/Documents/CLAUDE_COWORK/cockpit-e2e/node_modules/playwright-core`;
  screenshot scripts in `C:\Users\X1\AppData\Local\Temp\shot_v*.js` (point FILE at the v#).
- The REAL Dealroom dashboard renders on :8092 via the boardroom venv python (its own .venv is macOS):
  `cd dealroom && DEALROOM_DB_PATH=$PWD/data/dealroom.db <boardroom/.venv python> DEALROOM.py dashboard --serve --port 8092`.
  Captured verbatim table HTML/CSS at `C:\Users\X1\AppData\Local\Temp\investor-shots\dealroom-table.html` + `dealroom-styles.css`.

## Process learnings (do NOT repeat)
- Roman wants the 3 updates **VERTICAL**, and **no inline provenance/disclaimer commentary** in the UI
  (provenance only in the bottom block). Agents drift on both — instruct explicitly + verify by screenshot
  BEFORE showing Roman.
- **Copy suite formats exactly; never invent a new visual.** Reuse Dealroom/Cockpit/Allex markup verbatim.
- All numbers must be real (no-fabrication); null → "—" or honest empty state.
- Verify every UI change by rendering + reading the screenshot before claiming done.
