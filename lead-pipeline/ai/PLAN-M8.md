# M8: Ownership Hard Gate — Plan

## Context

M7 produces `pipeline_stage='ownership_enriched'` (confirmed ownership) and
`pipeline_stage='ownership_review_needed'` (unknown/ambiguous — awaiting manual input).

M8 applies the hard gate: records confirmed as subsidiaries or PE-backed are reclassified to
the new klass `S`. They do NOT go to D. Roman reviews S manually before any final exclusion.

---

## New Klass: S — Subsidiary / PE-Backed

**Why not D?**
D is for content-based no-fits (dental-only, pharmacy, hospital supply, wrong sector).
S is for ownership-based exclusions — the business model may be fine, but the ownership
structure disqualifies it as an acquisition target. Roman wants to review these manually:
a "subsidiary" might be a management buyout candidate, a spin-off, or a misclassification
in the source data. S keeps them visible and separate.

**Behaviour:**
- NOT exported to Serienbriefe (not in export query's `klass IN ('A','B','C','E')`)
- Visible in dashboard (M11) as a distinct category
- Roman reviews manually → either confirm exclusion or reclassify to A/B/C

---

## Gate Logic

Processes `pipeline_stage='ownership_enriched'` only.
Skips `ownership_review_needed` — those require manual input before gating.

| Condition | Action |
|-----------|--------|
| `is_subsidiary = True` | klass → S, reason: "subsidiary — confirmed corporate parent" |
| `is_pe_backed = True` | klass → S, reason: "PE-backed — confirmed fund ownership" |
| `is_subsidiary IS NULL AND share_pct >= 75%` | klass → S, reason: "unknown owner holds X% — manual verification required" |
| `is_subsidiary = False` (natural person confirmed) | Pass — advance to `ownership_gated` |

---

## Files Modified

| File | Change |
|------|--------|
| `src/pipeline/db.py` | `apply_ownership_gate_db()`: set `klass='S'` (was `'D'`) |
| `ai/DESIGN.md` | Add S definition; remove subsidiary/PE from D criteria |
| `CLAUDE.md` (project) | Update klass system description |
| `ai/ARCHITECTURE.md` | Update M8 gate table |

---

## Validation Steps

```bash
# Run tests
pytest tests/ -q

# Check pipeline status
python pipeline.py status

# Verify no S companies exist yet (current corpus has none confirmed subsidiary)
# Verify current B companies correctly at ownership_gated
```

---

## AI VALIDATION RESULTS

**Run date**: 2026-03-26

**Changes implemented**:
- `db.py`: `apply_ownership_gate_db()` now sets `klass='S'` (was `'D'`)
- `enrich.py`: reclassify reason strings updated to match S semantics
- `DESIGN.md`: S added as new klass; D criteria cleaned (subsidiary/PE removed from D)
- `CLAUDE.md` (project): klass system updated to include S
- `ARCHITECTURE.md`: M8 gate table updated

**Live DB state after M7+M8**:
- 0 S companies in current corpus (correct — no confirmed subsidiaries among current 4 B companies)
- 4 B companies: 1 at email_enriched, 3 at ownership_gated (all natural person owners confirmed)
- 60 D companies: all content no-fits from classifier (dental, wrong sector, etc.)
- S gate is active and will produce S klass on next run with a confirmed subsidiary

**pytest**: 160 passed

**Confirmed**: `klass='S'` is NOT exported (not in export query's `IN ('A','B','C','E')`).
