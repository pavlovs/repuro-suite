# PLAN — DEALROOM v2 M3: Front-end shell, answer-first

*2026-07-10/11. Spec §4 + §11 M3. Local build session.*

## Scope

- `v2/templates/shell-top.html` / `shell-bottom.html` — repuro-ci.css tokens + design-system classes inlined verbatim (boardroom precedent), dealroom page components built ONLY on those tokens (no raw hex outside the canonical block; font sizes = type-scale vars). Suite topbar: brand mark + REPURO wordmark + DEALROOM tag + suite nav (Cockpit/Investor) + SANDBOX badge when local.
- `v2/ui.py` + `v2/uikit.py` — server-rendered pages: Attention landing (A1), Portfolio, Deal page with Answer card (A2: stage+evidence chip, terms ledger card, milestones, risks, freshness flags, headline figures with source/as-of chips A3), Timeline tab (A4: stage/artifacts/rounds/milestones/data-room merged), Terms tab + global Terms ledger.
- Base-path aware (`DEALROOM_BASE_PATH` — behind Caddy handle_path `/deals`).
- German number formatting hardened: `fmt_keur` two decimals < 10 M€ (5.965 K€ → "5,97 M€", NOT "6,0 M€" — contract precision), `fmt_keur_exact` for ledger tables ("5.965 K€"), half-up rounding via Decimal.

## AI VALIDATION RESULTS

2026-07-11:
- All routes 200; visual pass via Chrome on landing/deal/CDD/negotiation pages (screenshots reviewed in-session).
- Defects found by looking and fixed same session: headline figure showed plan-year/zero rows ("Umsatz 2026 (adj.) 0 K€" — DR-BUG-025 class; now completed fiscal years, non-zero, single-consolidated-row fallback); backup files polluted registry (skip markers extended); 7 "current" databooks on overview (now newest per artifact type + "+N weitere"); "spa" substring misclassified Vertriebspartner-PDF (word-bounded markers); milestone dates without year.
- `tools/validate_ci.py --audience de` over rendered landing/portfolio/terms/deal/CDD: **R2 (Farben) = 0, R3 (Fonts) = 0, R4 (Headings) = 0** nach Fixes (raw px → type-scale vars). Rest: R1=0 nach Seed-Datums-Normalisierung; R5 = 35 Findings der Figure-Table-Heuristik auf echten Inhalten (Kategorielabels "1.1 Geschäftsfelder", Quellzitate) — dokumentierte Toleranz, keine Formatdefekte. Multi-Fakten-Notizen in Terms-Tabellen als `<ul>` (SCANNABLE-CELLS).
- 30 Tests grün.
