# PLAN — DEALROOM v2 M4+M5: CDD workspace + Negotiation/Stakeholders/Terms

*2026-07-11. Spec §6/§7 + §11 M4/M5. Local build session (one pass — shared payload layer).*

## M4 — CDD workspace (`/deal/{code}/cdd`)

- Data-room health: latest scan per section 00–08, lanes CDD (01–04, Repuro) / FDD (05–07, Ebner Stolz) / QA / TDD; delta since last scan; honest empty state with scanner command when no scan exists (live seller-share paths pending in `data/scanner_paths.json`).
- Registries: databook / RFI / slides — all versions, current/superseded, checks (sign-off, error-flag, tie-out) from `checks_json`.
- RFI tracker: mirror stats by status/priority, open questions with days outstanding, master-xlsx chip (xlsx bleibt Master).
- Red flags: deal_dd_items full table (risk/category/note/advisor). DD milestones table.

## M5 — Negotiation tab + Stakeholders + Terms ledger

- `/deal/{code}/negotiation` (owner-only via 403): strategy header (status, Gegenüber, Trail read-stats), **validate_negotiation.py wired in-process** (PASS/FAIL chip + findings; FAIL ⇒ nicht deliverable; per-process cache — Validator liest hubspot.db, Sekunden), position map (unsere/seine Ziele, Ziel/Reservation/Aspiration), Locked/Agreed Terms, §12-Tabellen: Positionen (preferred/fallback/walk-away + Roman-Freigabe-Chip), offene Punkte, Verhandlungs-Meilensteine, Parteien (verlinkt auf Personenseiten), SELBST-CHECK (offene Lessons mit Drill), Objection-Bank, Runden = volle Deal-Historie über Memo-Versionen hinweg, Strategie-Memo (md-lite Rendering).
- `/stakeholders` + `/stakeholder/{id}` (owner-only): Identität + HubSpot-Key, Kontexte, Claims mit Konfidenz + Evidenzzitat + Quelle, Runden über alle Kontexte, Kommunikations-Trail mit Read-Status.
- Terms ledger: global `/terms` + Deal-Tab; exakte K€-Darstellung; Lifecycle proposed→countered→agreed→locked→superseded; jede Zeile mit source_doc.

## Build-time data findings (v1 changed under the session — other sessions active)

1. v1 gained §12 negotiation tables on 10/11.07 (negotiation_milestones, negotiation_open_items, strategy_parties, negotiation_positions) + `negotiation_strategies.closed_reason` + Status 'executing' → v2 Schema/Migration nachgezogen, Tabellen carried (6/3/2/2 Zeilen).
2. Lion-Terms-Seed korrigiert: Verhandlungsstand aus negotiation locked_terms (Runden-Record 16.06/26.06) — Sofort 3.000 K€ + Ausschüttung 425 K€ = Closing 3.425 K€ agreed; R1-Angebot (2.500 K€, 22.05) als superseded-Historie; offene Punkte (Tantieme 135/140, EO-Staffelung, +1J Kündigungsschutz) proposed per 260708-Update.
3. Cat executing-Strategie S3 (Signatur-Phase) rendert vollständig inkl. Objection-Bank + Meilensteine.

## AI VALIDATION RESULTS

2026-07-11:
- Routes 200 (CDD Fox/Mantis, Negotiation Lion/Cat, Stakeholder 1/2, Terms). Owner-Gating verifiziert: X-Remote-User=florian → 403 auf Negotiation/Stakeholders, Tab wird nicht gerendert; Deal/CDD bleiben zugänglich.
- Visual pass (Chrome): Cat-Negotiation zeigt echte offene Punkte/Meilensteine/Parteien/Objection-Bank/Memo; Lion zeigt 13, Cat 11 Runden (24 gesamt = v1-Stand); Fehler "Runden leer bei Memo-Versionierung" gefunden + gefixt (Runden = Deal-Historie, nicht Memo-Version).
- Validator-Gate: Lion FAIL (17 Findings — Memo-Struktur der superseded-Strategie) sichtbar mit Findings-Liste; §12-"migration not run"-Findings verschwanden nach Schema-Nachzug.
- 30 Tests grün.
