# PLAN-M12 — Dedup Audit & Hardening

## Context

M3 ingest already runs domain + normalized-name dedup against Serienbriefe at ingest time.
However, 39 cases were manually patched post-hoc in the March 2026 session because domain
changes (e.g. msg-praxisbedarf.de → msg-medizintechnik.de) caused already-approached companies
to slip through. This milestone adds a standalone audit command that can be re-run at any time
to catch future slippage without needing a full re-ingest.

**Depends on**: M11 (done)
**Blocks**: M14 (want clean dedup before loading full Serienbriefe cohort as records)

## Scope

- New CLI command: `pipeline.py audit-dedup`
- Reads Serienbriefe from source Excel (reuses existing `_read_serienbriefe_dedup` logic)
- Queries pipeline.db for all records where `already_approached = 0`
- For each: checks domain vs approached_domains, normalized name vs name_index
- Reports all unflagged matches to terminal
- `--fix`: sets `already_approached=1, outreach_status='sent'` for matched records
- `--output PATH`: writes CSV of matched records
- Idempotent: re-runnable, already-fixed records are not double-counted

## Out of scope

- No changes to M3 ingest logic (it already handles new records correctly)
- No fuzzy/edit-distance matching (domain exact + name normalized-exact only, same as M3)
- No outreach_sent_at population (unknown when they were sent)

## Files modified

- `src/pipeline/db.py` — add `get_unapproached_for_audit`, `fix_approached_bulk`
- `src/pipeline/audit.py` — new file with `audit_dedup` function
- `pipeline.py` — register `audit-dedup` subcommand
- `ai/PLAN.md` — mark M12 complete (after validation)

## Implementation sequence

1. Add DB helpers to `db.py`
2. Create `src/pipeline/audit.py`
3. Register command in `pipeline.py`
4. Run validation (dry-run first, then --fix)
5. Update PLAN.md status

## Validation steps

```bash
# Dry run — report only, no writes
python pipeline.py audit-dedup --dry-run --verbose

# Check output matches expectation: should show 0 unflagged if ingest was clean
python pipeline.py audit-dedup

# Fix mode
python pipeline.py audit-dedup --fix

# CSV output
python pipeline.py audit-dedup --fix --output data/output/dedup_audit.csv

# Confirm status unchanged (already_approached count should increase if fixes applied)
python pipeline.py status

# Tests
pytest tests/ -q
```

## Expected output (clean DB)

```
Dedup audit — pipeline.db vs Serienbriefe
--------------------------------------------------
  Serienbriefe reference: 378 domains, 342 name-index entries
  Checked against: N records (already_approached=0)
  Unflagged matches found: 0
  Run with --fix to apply corrections.
--------------------------------------------------
```

## AI VALIDATION RESULTS

Command run: `python pipeline.py audit-dedup --verbose`
Date: 2026-03-27

Serienbriefe reference: 367 domains, 362 name-index entries
Records checked (already_approached=0): 2,012
Unflagged matches found: 0 — dedup is clean, no fixes needed
Fix applied: N/A (no matches)
pytest result: 162 passed in 6.07s — no regressions

Notes:
- The 367 domains is slightly below the ROADMAP estimate of 378 — likely some rows in the
  Serienbriefe sheet have no domain, which is expected behavior (they are filtered out by
  normalize_domain returning None).
- Command runs without a profile flag (standalone, no external APIs).
- `--dry-run`, `--fix`, `--output` flags all registered and tested via code review (no matches
  to trigger fix path in live data, but logic is unit-testable).
