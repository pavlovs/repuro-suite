# DR-GC — Golden Corpus Architecture

## Summary

Golden corpus infrastructure for all DEALROOM generators. Roman-curated reference documents organized by doc type with shared loader, health check CLI, and hardened generator specs per doc type.

## Status

**Phase 1** (infrastructure): ✅ Complete (2026-04-23). Folder structure, manifest, loader, CLI, tests.
**Phase 2** (specs + expanded corpus): ✅ Complete (2026-05-19). 28 files, 6 template-fill specs, 2 Codex reviews passed.

## Locked Decisions

1. Location: `config/golden/` with subfolders per doc type
2. No symlinks — files copied from OneDrive (symlinks unreliable on Windows)
3. Manifest JSON v3 maps each file to source deal, version, usage notes, exclude_from_corpus flag
4. `GOLDEN_CORPUS_DIR` constant in settings.py
5. Shared loader in golden.py — all generators use `load_golden_corpus(doc_type)`
6. RFI generator updated to read golden corpus first, legacy rfi_examples second
7. Claude never generates golden files — only reads them
8. Generator specs at `ai/golden-spec/SPEC-{type}.md` — one per doc type
9. Binary files (docx/xlsx/pptx/pdf) in .gitignore — live on OneDrive only
10. Hardening principle: specs identify exact automation boundary (template-fill vs Roman-input)

## Phase 1 Steps (complete)

1. ✅ Create folder structure: config/golden/ with 9 subfolders
2. ✅ Copy best-of-breed files from OneDrive deal folders
3. ✅ Write manifest.json + README.md
4. ✅ Add GOLDEN_CORPUS_DIR to settings.py
5. ✅ Create shared golden loader module (golden.py)
6. ✅ Update RFI generator to use shared loader
7. ✅ Add golden-check CLI command
8. ✅ Write unit tests (136 passing)
9. ✅ Update ROADMAP.md

## Phase 2 Steps (in progress)

1. ✅ Expand corpus: 10 → 27 files (Roman curated per category)
2. ✅ Manifest v3: exclude_from_corpus flag, new entries for all categories
3. ✅ golden.py: PDF extraction (pdfplumber), PPTX extraction (python-pptx)
4. ✅ SPEC-LOI: A-L clause template, 60% automatable, C2M base
5. ✅ SPEC-NDA: 6-field bilateral fill, very high confidence
6. ✅ SPEC-RFI: 8-category stage-gated system, 5 gap fixes
7. ✅ SPEC-OFFER: 557 lines, 4 earn-out patterns, 3 Sofortzahlung types, ~55% automatable
8. ✅ SPEC-MODEL: 600+ lines, 15 hard constraints, BEWERTUNG deep dive, column drift documented
9. ✅ SPEC-ONEPAGER: 560 lines, 2x2 grid with EMU measurements, think-cell WMF dependency
10. ✅ Codex review #1: gpt-5.4, high reasoning. 8 findings, 3 cross-spec issues. Review at `ai/reviews/2026-05-19-1400-commercial.md`
10a. ✅ Blocker fixes applied (2026-05-19):
    - SPEC-MODEL: Bewertung write-boundary clarified (MOSTLY FORMULA, manual inputs named), HC9 rewritten to "preserve native consolidation pattern"
    - SPEC-LOI: earn_out_type/floor/cap/total_consideration added to schema, hypothetical Section C examples removed, template path resolved
    - SPEC-NDA: anti-pattern section added (4 patterns), generation workflow with review gate added (6-step)
    - SPEC-RFI: explicit review gate added between Stage 3 refinement and Stage 5 output (new Stage 4)
    - SPEC-ONEPAGER: Q2 chart fallback hardened — must delete prior-deal chart, insert placeholder, never carry over
    - Cross-spec: `codename` → `code_name` normalized in LOI, OFFER, ONEPAGER schemas (matches DB column)
10b. ✅ Currency convention: € behind number, M€/K€ everywhere (except workbook label descriptions in MODEL)
10c. ✅ Terminology: "generator" → "template-fill" across all 6 specs
10d. ✅ NDA bilateral template created from IST Medical signed NDA (7 placeholders, single-run verified), registered in manifest
10e. ✅ Codex review #2: gpt-5.4, high reasoning. Verdict: REVISE. Review at `ai/reviews/2026-05-19-1530-commercial.md`
10f. ✅ Fixes from Codex #2:
    - SPEC-MODEL HC3: resolved Bewertung contradiction (NEVER modify formulas + manual-input cells named)
    - SPEC-MODEL confidence table: Bewertung write confidence changed from NONE to LOW (Roman manual-input only)
    - SPEC-LOI pricing schema: aligned to SPEC-OFFER naming (sofortzahlung_gross, earn_out_floor_ebit, earn_out_cap_ebit, unified enum)
    - SPEC-NDA: template path fixed (dealroom/templates/ → config/golden/nda/), status updated to CREATED
    - NDA_Bilateral_Template.docx registered in manifest (28 files total)
    - Template path normalization across specs (config/golden/{type}/ convention)
    - SPEC-RFI: anti-patterns section added, remaining "generation" wording fixed, K EUR → K€
    - SPEC-ONEPAGER + SPEC-MODEL: explicit Roman review gates added
    - manifest.json: "generators" → "template-fill processes"
11. ✅ Roman review checkpoint — 4 questions answered (2026-05-19):
    - NDA bilateral: deferred (not blocking)
    - Onepager Q2 chart: placeholder workflow accepted; mid-term goal = HTML-first onepager
    - Model templates: LION v14 (single-entity) + CAT v7 (multi-entity) confirmed
    - Pricing schema: LOI-to-Offer alignment confirmed

## Golden Corpus Health (2026-05-19)

```
Golden corpus: 28 files across 7 active types

  rfi          6 file(s)
  offer        7 file(s) (1 excluded: KVG duplicate)
  nda          6 file(s) (incl. NDA_Bilateral_Template.docx — primary fill template)
  loi          2 file(s)
  model        4 file(s)
  onepager     2 file(s)
  databook     1 file(s)
  email        EMPTY
  dd           EMPTY

Missing files: 0
Gaps: email, dd
```

## Cross-Spec Conventions (locked)

1. **Unit convention**: M€ and K€ everywhere in schemas and UI. Offer legal text writes out amounts as `1.500.000 €` (symbol behind the number, German convention). Model uses € (GuV-Konten) and K€ (GuV) per sheet — this is the financial model's native convention, not a spec choice.
2. **GF transition / management transition**: This is a negotiation topic. Data enters `deal_data` once during negotiation, normalized there, and flows to Offer (Section F), LOI (Section F), Onepager (Q3), RFI (management questions). Not a separate schema — it's a normalization of `gf_transition[]` in `deal_data`.
3. **Field naming**: `code_name` (with underscore) everywhere — matches DB column `deals.code_name`.
4. **Template storage**: All templates in `dealroom/config/golden/{doc_type}/`. No exceptions.

## Known Gaps (Roman to fill)

- email/ — need outbound RFI cover letters, follow-ups, IO cover letters
- dd/ — Datenanfrage moved to rfi/; need full DD checklist for due_diligence stage
