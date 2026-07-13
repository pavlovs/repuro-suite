# DEALROOM — Issue List

RD = Roman, FF = Florian. Priority: P0 blocker, P1 high, P2 medium, P3 nice-to-have.
Claude sessions: pick up issues via `/dealroom-bugfix`, log in `.active/dealroom-sessions.md`.

## Bugs

- [ ] DR-BUG-020 — (P2) [RD] Subaccounts only shows a few account numbers — should match GuV-Konten view. **Root cause**: extraction pipeline only captured 10 aggregate konto_nr rows for medizinservice-sachsen.de. Needs re-ingestion from SUSA/BWA source files.
- [ ] DR-BUG-022 — (P2) [RD] FOX: onepager graphs not showing (services, customer distribution). **Root cause**: Fox has 0 customer rows and 0 commercial data in DB. Needs data ingestion from Fox source files. **Confirmed 2026-06-03**: `deal_commercial` has 0 `category='service_split'` rows for com2med.de AND endoberatung.de → service portfolio chart cannot render. Code is correct; needs Sparten/service-split data ingested from Fox + Mantis source files. (Mantis service chart also affected.)
- [x] DR-BUG-023 — (P1) [RD] Fixed 2026-06-03. FOX + Mantis showed blank/0 Rev & EBITDA. **Root cause**: model files carry an empty forward FY2026 plan column; extraction wrote it into `deal_financials` as `period_type='annual'` rows with `value_k=0.0`; the headline logic (`build_portfolio_data` + `_build_onepager_chart_data`) picked the MAX fiscal_year (2026=0.0). The `value_k IS NOT NULL` guard missed it (value is 0, not NULL). **Fix**: both builders now select the latest ACTUAL year (non-zero revenue) and drop zero-revenue plan-year columns; portfolio EBITDA pinned to the headline revenue year. Non-destructive (no DB deletes). Verified live: Fox 3.57M€/0.35M€ (9.9%), Mantis 3.18M€/0.79M€ (24.9%), both FY2025. Systemic note → DR-BUG-025.
- [x] DR-BUG-024 — (P1) [Claude] Fixed 2026-06-03. 12 tests in test_dashboard.py + test_rfi.py failed with `IndexError: deal["onepager_footnote"]`. **Root cause**: in `build_deal_data` the `deal` row was SELECTed before `_ensure_onepager_columns` added the onepager_* columns, so on a fresh test DB the Row lacked them. **Fix**: moved `_ensure_onepager_columns(conn)` above the deal SELECT. Full suite now 133 passed, 3 failed (the 3 are unrelated → DR-BUG-026).
- [ ] DR-BUG-026 — (P2) [Claude] 3 pre-existing test failures unrelated to the dashboard/headline work (surfaced when the suite was run 2026-06-03): (1) `test_db.py::test_octopus_seed` — Octopus seed stage assertion (dead deal / stale seed); (2) `test_ingest.py::test_classify_meeting` — meeting classifier logic; (3) `test_model.py::test_golden_pnl[Cat]` — Cat 2021 ebitda_adj golden=-25.34 vs extracted=-29.12 (14.9% drift). Each is a separate subsystem; needs individual triage.
- [ ] DR-BUG-025 — (P2) [Claude] Systemic: extraction ingests the model's forward plan column (FY+1) as an actual annual P&L year in `deal_financials`. 8 deals have FY2026 rows; where filled (hwv, golmed, medizinservice) a PLAN year can still surface as the headline/actual. Proper fix: don't write the plan column as `period_type='annual'` actuals — route projections to `bp_2026_*` / a projection period_type. DR-BUG-023 fix masks the empty case at the read layer; this is the deeper data-layer fix.


## Feature Requests
- [ ] Add n export to PDF button on the top of the Live Deal Portfolio and the onepager view
- [ ] Show the sum of the total EV of (if possible) and calculate the average multiple (is that possible actually?)
- [ ] also show average EBITDA margin
- [ ] ON Hold / Dead deals should be slightly opaque or grey colored and be sorted obviously on the bottom
- [ ] Could we show a # of deals in the respective stage on top? NDA, Valuation, Offer, LOI, etc.?
- [x] DR-FEAT-007 — (P1) [RD] Fixed 2026-05-22. Financials tab restyle: removed Zinsaufwand–Jahresüberschuss rows, removed inter-row borders, blue fill on EBITDA, indented cost positions (CoS/Personnel/OPEX/D&A), wider Notes column + spacer columns, more padding.
- [ ] DR-FEAT-008 — (P1) [RD] Financials tab: fill CT columns for Cat from model (260505_MundS_v7.xlsx). Cat currently has 0 CT rows in DB.
- [ ] Add the option to enlarge a quadrant and go the next enlarged quadrant if i press left or right arrow key
  
      
      

## Done

- [x] DR-BUG-021 — (P2) [RD] Fixed 2026-05-22. Customer list capped to actual top 10 per year in backend (_build_customers). Was rendering all 300+ rows per year.
- [x] DR-BUG-004 — (P1) [RD] Fixed 2026-05-22. CAT onepager text and bolding updated to match 260522_Repuro_Aurica meeting_v1.pptx (Slide 5). All 5 fields (q1, q3, q4, title, headline) aligned.
- [x] DR-BUG-001 — (P1) [RD] Fixed 2026-05-21. Harmonize number format — all values in M€, added footnotes explaining EV and Multiple calculation basis.
- [x] DR-BUG-002 — (P1) [RD] Fixed 2026-05-21. Fox EBITDA showed 0.3 due to double-rounding — increased backend precision to 4 decimals, frontend .toFixed(1) now correctly shows 0.4.
- [x] DR-BUG-003 — (P1) [RD] Fixed 2026-05-21. EV reverted from K€ to M€ format.
- [x] DR-FEAT-001 — (P1) [RD] Fixed 2026-05-21. Status column moved between Multiple and Comment.
- [x] DR-FEAT-002 — (P1) [RD] Fixed 2026-05-21. "Updates" renamed to "Comment".
- [x] DR-FEAT-003 — (P1) [RD] Fixed 2026-05-21. EV header → "EV¹ (M€)", Multiple header → "Multiple²" with footnotes.
- [x] DR-FEAT-004 — (P1) [RD] Fixed 2026-05-21. New status levels: NDA signed, Initial meeting, NBO preparation/sent/confirmed, LOI sent/signed. Old values mapped to new labels.
- [x] DR-FEAT-005 — (P2) [RD] Fixed 2026-05-21. Strategic fit column removed.
- [x] DR-FEAT-006 — (P2) [RD] Fixed 2026-05-21. "Other pipeline comments" section added below table; "Other Comments" renamed to "Other updates" and moved below it.
- [x] DR-BUG-005 — (P2) [RD] Fixed 2026-05-21. Added margin-bottom:12px to chart container for spacing below graphs.
- [x] DR-BUG-006 — (P1) [RD] Fixed 2026-05-21. Avg 24-25 EV at closing multiples added to Avg column for all three EV rows.
- [x] DR-BUG-007 — (P1) [RD] Fixed 2026-05-21. BP and Max.EO now show K€ separator (German toLocaleString). Backend parses German-formatted numbers on save.
- [x] DR-BUG-008 — (P1) [RD] Fixed 2026-05-21. EV/EBITDA per-year row removed from onepager Q2 chart.
- [x] DR-BUG-009 — (P1) [RD] Fixed 2026-05-21. One-Pager is now its own sidebar section (first item, starting screen) — no longer sticky/persistent.
- [x] DR-BUG-010 — (P2) [RD] Fixed 2026-05-21. Financials section font size bumped 12px→13px, padding increased for readability.
- [x] DR-BUG-011 — (P1) [RD] Fixed 2026-05-21. Subaccount drill-down hidden by default — CSS selector broadened from .fin-table to generic tr.detail-row.
- [x] DR-BUG-012 — (P1) [RD] Fixed 2026-05-21. Portfolio sorting reversed — furthest along (closed/contract neg.) on top, on_hold/dead at bottom.
- [x] DR-BUG-013 — (P1) [RD] Fixed 2026-05-21. WIP markers removed from table cells, replaced with footnote "All numbers are preliminary."
- [x] DR-BUG-014 — (P1) [RD] Fixed 2026-05-21. All footnotes consolidated into single line with pipe separators.
- [x] DR-BUG-015 — (P1) [RD] Fixed 2026-05-21. CAT Process & Status text updated from Roman's screenshot — 6 bullets with bold labels.
- [x] DR-BUG-016 — (P2) [RD] Fixed 2026-05-21. Portfolio header renamed "Status" → "Stage", stage cell text un-bolded (was font-weight:600).
- [x] DR-BUG-017 — (P2) [RD] Fixed 2026-05-21. EV and Multiple value cells now bold (font-weight:700).
- [x] DR-BUG-018 — (P2) [RD] Fixed 2026-05-21. Footnote 2 text changed to "EV / adj. EBITDA 2025tje."
- [x] DR-BUG-019 — (P2) [RD] Fixed 2026-05-21. Added margin-bottom:12px to service/customer chart in onepager.
- [x] DR-BUG-024 — (P1) [RD] Fixed 2026-05-21. Mouse deal renamed from Coretec-Service GmbH to Everto Laborhandel. DB migration + seed updated, folder_path → 260417_Everto Laborhandel (Mouse).
- [x] DR-BUG-025 — (P2) [RD] Fixed 2026-05-21. Avg. 24-25 and Valuation headers restored to same teal (#0891B2) as year columns (were #1D7080).
- [x] DR-BUG-026 — (P2) [RD] Fixed 2026-05-21. Financial table numbers changed from monospace to Arial for consistency with rest of dashboard. tabular-nums retained for digit alignment.
- [ ] DR-BUG-027 — (P3) [RC 13.07] Flaky e2e: `test_e2e_scan_push_fresh_ui` asserts Fox `extraction_stale`, but the flag depends on extraction recency vs. disk mtimes (failed 12:15 right after a fresh Fox extraction, passed 12:52). Test needs a deterministic fixture (backdate extracted_at in the temp DB) instead of live-folder state.
- [x] DR-BUG-028 — (P1) [RC 13.07] Fox terms: deals.md prose ("EV closing 1.6 (4.5x) + EO 0.3") contradicts the SIGNED LOI (260522_..._signed.pdf: Sofort 1.000 K€ + ca. 150 K€ Co-Med-Anteil + EO gestaffelt max 750 K€ = 1.900 K€; also confirmed by memory reference_fox_mantis_lois). migrate_v1 TERMS_SEED corrected to the signed values 13.07. OPEN for Roman: fix the deals.md Fox row.
