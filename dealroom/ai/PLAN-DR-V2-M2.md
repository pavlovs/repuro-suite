# PLAN — DEALROOM v2 M2: Ingestion + freshness pipeline

*2026-07-10. Spec §5 + §11 M2. Local build session (continues PLAN-DR-V2-M1.md).*

## Scope

1. **`v2/naming.py`** — shared filename convention parsing (`YYMMDD_..._vN`), artifact classification (name markers → folder fallback). Non-numeric markers (vS/vP/vFC/vWIP) = document states, not versions.
2. **`v2/scanner.py`** — local CLI, pushes via API (spec: ingestion local, storage remote):
   - `artifacts --deal X` — walks the deal folder (skips `_old`/`_archive`/`.bak`/`~$`), classifies, pushes with mtime+size → registry upsert + version-chain recompute.
   - `rfi --deal X` — picks newest Fragenliste/Datenanfrage xlsx in 5_DD (vS preferred on date tie), parses the Repuro header convention (Priorität/Status/Antwort optional), pushes mirror (xlsx = master).
   - `dataroom --deal X --path <root>` — sections 00–08 read-only, full file list push; server computes delta. Per-deal roots in `data/scanner_paths.json` (live seller shares are not under 3_Targets).
3. **Freshness rules 1–6** (`v2/freshness.py`, built in M1, hardened here): chain rule now compares newest current per artifact type (multiple version chains per type exist in reality).
4. **Scope cut (6h session)**: COM/xlsx financial-extraction adapters (v1 `extract`) stay on the v1 CLI until Fly cutover; DR-BUG-020/022/025 are extraction-pipeline bugs and move with that work. Documented in ROADMAP at M6.

## AC / verify — AI VALIDATION RESULTS

2026-07-10:
- Fox live end-to-end: `artifacts --deal Fox` → 291 files pushed (databook 13, rfi 11, loi 12, …); `rfi --deal Fox` → 28 Fragen (11 HIGH) from `260708_Repuro_C2M_Fragenliste_vS.xlsx` (vS correctly preferred over vP after fix).
- Mantis live: 61 artifacts; Fragenliste vS (20 Fragen — header without Priorität parsed after fix).
- `/api/fresh` (manually verified against folder reality):
  - Fox: extraction_stale (Quelle 2026-07-06 > letzte Extraktion 2026-05-22) — correct.
  - Fox chain_broken false positive fixed (newest-current-per-type); flag dropped.
  - Mantis: chain_broken RFI 06.07 < Databook v8 10.07 — verified real (260710_Mantis_CDD_Databook_v8.xlsx exists); extraction_stale correct; milestone CDD-Workshop 14.07 surfaced.
  - Mouse: LOI-Unterzeichnung 10.07 fällig — correct (Sign-Ziel heute).
- `pytest v2/tests/` → 30 passed (M1 23 + M2 7: classification, version/date parsing, real-file Fragenliste parse read-only, vS preference).
- Data-room scan: section discovery validated against `0_Template/_Dataroom_Struktur` (00–08); delta logic covered by API test (M1). Live seller-share paths pending Roman (scanner_paths.json).
