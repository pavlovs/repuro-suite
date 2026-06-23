# PLAN-M2 — Auto-assembly from read-only source DBs

Grounded in live DB inspection 2026-06-20 (read-only). Build after M1 passes Codex re-review.

## Module: `src/assemble.py` (admin-only path; opens foreign DBs via `db.open_readonly`)

Local DB paths (env-overridable): `INVESTOR_DEALROOM_DB`, `INVESTOR_PIPELINE_DB`, `INVESTOR_COCKPIT_DB`.
Local defaults point at `<module>/data/<db>.db` (the root-level `*.db` are 0-byte strays — ignore).
Prod = `/data/*.db` per supervisord env.

## `assemble_weekly_update() -> dict` (a draft body, §4.1 shape, every figure stamped)

### pipeline.funnel  (source: dealroom.db, anonymized — NO company_name)
- `SELECT code_name, deal_stage, sector, location, ebitda_m_override, strategic_fit FROM deals`
  `WHERE deal_stage IN ('valuation_rfi','indicative_offer')` — active top-of-funnel only.
- **Exclude** `dead`, `on_hold`, and `loi_signed`+ (latter shown as live deals). Exclude company_name,
  seller_*, investment_thesis, notes (sensitive).
- size_band: derive a band from `ebitda_m_override` (e.g. <1 / 1–3 / 3–5 / 5+ €M), never the exact figure pre-LOI.
- region: map `location` → German state/region.

### pipeline.batches  (source: pipeline.db, aggregate)
- Per `briefaktion` (exclude NULL + 'testbatch' + '*TEST*'):
  - sent = COUNT(WHERE outreach_sent_at IS NOT NULL) — fallback COUNT(*) in cohort
  - replies = COUNT(WHERE outreach_status IN ('contact','financials','meeting','declined','followup1','followup2'))
  - meetings = COUNT(WHERE outreach_status='meeting')
  - conv_pct = meetings / sent
- Confirm "reply" definition with Roman; default above. Report aggregate only — no company names.

### live_deals  (source: dealroom.db, real names allowed post-LOI)
- `WHERE deal_stage IN ('loi_signed','due_diligence','contract_negotiation','closed')`.
- Fields: company_name, code_name, deal_stage, rev_m_override, ebitda_m_override, ev_m_override,
  multiple_override, ev_m_note, status_override, description. earnout/dd_status/close_target/commentary
  are authored if not in a structured column (flag which are DB vs authored).

### project_update.milestones  (source: cockpit.db)
- milestones_done = deliverables WHERE status='done' (currently 0 — section will be empty).
- milestones_next = deliverables WHERE status='open' AND target_date IS NOT NULL ORDER BY target_date.
- **DATA GAP:** 62 deliverables, all open, target_date mostly NULL → thin timeline. Flag to Roman:
  cockpit deliverables need dates/done-status for this to be useful; until then narrative carries it.
- narrative + fundraising = authored (left empty; M3 admin fills).

## stamps
Every pulled block records `{source: '<db>', as_of: '<ISO now or source timestamp>'}`. Authored → 'authored'.

## Tests
- assemble against the REAL dbs (read-only): assert funnel excludes dead/on_hold and has no company_name
  key; live_deals only post-LOI; batch numbers match a direct SQL count (report N/M); cockpit pull tolerant
  of NULL target_date. Use a copy or the live ro DBs; never write them.

## Open for Roman
- "Reply" definition for batch conv (above default).
- size_band thresholds.
- Whether `indicative_offer` deals appear in pipeline (anonymized) or are held back entirely.

---

## VALIDATION RESULTS (2026-06-20, against live read-only DBs)
Built: `src/sources.py`, `src/assemble.py`, `POST /api/assemble` (admin-only), `tests/test_assemble.py`.
- **40 tests pass** (21 M1 + 19 M2). Includes round-trip shape guards (assemble→publish→investor read).
- **Live numbers:** funnel 5 (Cat, Lion, Wolf, Mouse, Swordfish — anonymized, codename-only); batches 8
  (BA1–BA8); live_deals 2 (Fox=Com2Med, Mantis — loi_signed, real names); milestones_next 20; done 0.
- **Security gate PASS (live scan):** no company_name / seller_motivation / seller_profile_notes /
  investment_thesis value appears anywhere in the funnel JSON. live_deals = post-LOI stages only.
- **Integration bug found + fixed:** assembler initially emitted a body shape (`batches.items`,
  `live_deals.{items}`, `fundraising:""`, KPI `label/unit`) that diverged from the M1 read view
  (`batches.rows`, bare `live_deals` array, `fundraising` object, KPI `metric/value/prior`). A published
  draft would have rendered blank. Reshaped assembler to the read-view contract + added two round-trip
  regression tests.

## DATA GAPS surfaced (dealroom completeness, not code bugs — flag to Roman)
- `indicative_offer` deals (Cat/Lion/Mouse) have NULL `sector`, `location`, `ebitda_m_override` →
  funnel shows null sector/region and size_band 'n/a'. Needs dealroom enrichment to be presentable.
- `ev_m_override` NULL for Fox/Mantis → live-deal EV and board "Combined EV in DD" KPI are null.
- Cockpit deliverables: 0 done, target_dates mostly NULL → milestones thin; project narrative carries it.
- BA8: 44 sent, 0 replies under current reply definition — verify outreach_status tracking for BA8.
