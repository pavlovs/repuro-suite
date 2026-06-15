# DR-M5 — Excel Model Builder (Reader)

## Scope

Read finalized Excel models for existing deals (Wolf, Cat, Octopus; Fox locked). Extract:
1. Adjusted P&L from GuV sheet (reusing `build_golden.py` extraction logic)
2. Valuation data from Bewertung sheet (EV scenarios, deal structure)
3. Write to `deal_data` (category=valuation_input) and `deal_valuations`
4. Reconcile model EBITDA adj vs raw extracted EBITDA — flag >5% discrepancies
5. Dashboard Model section: GuV (adjusted), Bewertung, EBITDA Bridge

New deal model population (writing to Excel template) deferred — only the READ path implemented.

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `src/model.py` | NEW | `read_model()`, `extract_bewertung()`, `_reconcile_ebitda()` |
| `DEALROOM.py` | EDIT | Added `model` command, removed `value` stub |
| `src/dashboard.py` | EDIT | `build_deal_data()` now includes model_pnl, bewertung, valuation, ebitda_bridge |
| `src/templates/dashboard.html` | EDIT | Model section: GuV (adj), Bewertung, EBITDA Bridge tabs |
| `tests/test_model.py` | NEW | 5 unit tests + 3 golden validation tests |
| `ai/ROADMAP.md` | EDIT | DR-M5 marked complete |
| `ai/ARCHITECTURE.md` | EDIT | Module map updated |

## CLI

```
python DEALROOM.py model --deal Wolf [--dry-run]
python DEALROOM.py model --all [--dry-run]
```

## AI Validation Results

### Unit tests (5/5 pass)
- `test_read_model_deal_not_found` — ValueError for unknown deal
- `test_read_model_no_model_file` — graceful error when no model registered
- `test_reconcile_no_raw_data` — 0 conflicts when no raw data exists
- `test_reconcile_matching_data` — 0 conflicts when diff < 5%
- `test_reconcile_mismatched_data` — 1 conflict flagged when diff = 40%

### Golden validation (3/3 pass)
- Wolf: 4 years, all keys within 2% of golden
- Cat: 6 years, all keys within 2% of golden
- Octopus: 6 years, all keys within 2% of golden

### Live execution
```
Wolf:     52 P&L rows + 12 bewertung rows, valuation written, 3 EBITDA conflicts
Cat:      72 P&L rows + 15 bewertung rows, valuation written, 6 EBITDA conflicts
Octopus:  72 P&L rows + 12 bewertung rows, valuation written, 2 EBITDA conflicts
Fox:      LOCKED (PermissionError — graceful skip)
```

### Full test suite
73/73 tests pass (all existing + new).

### Dashboard
Model section renders three sub-tabs:
- **GuV (adjusted)**: full adjusted P&L table per year with source attribution
- **Bewertung**: EV scenarios (low/mid/high), EBITDA basis, deal structure (cash, Rueckbeteiligung, earn-out)
- **EBITDA Bridge**: raw vs adjusted per year with delta

## Design Decisions

1. **Bewertung column detection**: models use varied headers (Bewertung, Valuation, FINAL offer). Parser skips first 5 columns (labels + years) and searches for keywords. Sorts label matches by length descending to prefer specific matches.
2. **Cat EBITDA basis**: Cat model puts EBITDA basis in the Avg column, not the Valuation column. The basis is missing for Cat — acceptable, EV values still extracted.
3. **Idempotent writes**: `DELETE FROM deal_data WHERE source = model_name` before re-inserting. Same for `deal_valuations`.
4. **Conflict threshold**: 5% EBITDA difference triggers conflict flag on both raw and model rows.

## PM Review
Reviewed: 2026-03-30
Model: Claude Sonnet 4.6 (inline — Opus unavailable due to token budget)

### Required changes (high conviction — autonomous)
1. **Model values missing `is_authoritative=1`.** Model data comes from Roman's finalized work — should be marked authoritative per ARCHITECTURE.md definition. Fixed: added `is_authoritative` column + value=1 to both pnl_adj and bewertung INSERT statements.

### Clarify with project owner (low conviction)
None — all design decisions align with Roman's stated preferences from this session.

### Verdict
PASS (after amendment)
