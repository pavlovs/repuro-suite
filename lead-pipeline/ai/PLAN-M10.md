# M10: Serienbriefe Exporter -- Plan

## Context

M10 is the export stage. It takes all classified + enriched records from `pipeline.db`
and writes a Serienbriefe-ready Excel file aligned with the actual Word mail merge template.

Input: records with `klass IN ('A', 'B', 'C', 'E')`, `already_approached=0`,
`filter_pass=1 OR NULL`, `pipeline_stage NOT IN ('ingested')`.

Word template inspected: `251111_Repuro_MedTech_Brief_Updated_vF.docx`
Extracted 19 actual merge fields: `Anrede`, `First_Name_1`, `Gesellschafter`,
`Kompliment_1`, `Kompliment_2`, `Last_Name_1`, `Leistung_Absatz_1`, `Leistung_Absatz_2`,
`Mehrwerte`, `Name_Absatz_1`, `Name_Absatz_3`, `Name_Briefkopf`, `Name_Titel`,
`PLZ__Stadt`, `Region`, `Salutation`, `Street_Address`, `Verantwortlich`, `Zweiter`

---

## Implementation

### Schema Cleanup (original 61 cols -> 36 cols)

The original 61-column schema was a copy of an internal tracking sheet with many
status/tracking columns not needed at export time. Reduced to 36 columns in 4 groups:

1. **Identity & analytics** (9): Domain, Source, Category, Priority, MA, Owner Age,
   Services Score, SSB, HR-Nummer
2. **Word merge fields** (19): exact mapping from Word template field codes to Excel headers
3. **Contact** (2): Email, Tel
4. **Outreach tracking** (6): Datum Sent, Status, Comment, Follow-Up 1, Follow-Up 2,
   Follow-Up Comment

### Outreach Tracking Columns (DB migration)

6 new columns added to `company_records` in `pipeline.db`:
- `outreach_status TEXT` — new / sent / replied / meeting / declined / closed
- `outreach_sent_at TEXT`
- `outreach_comment TEXT`
- `followup1_at TEXT`
- `followup2_at TEXT`
- `followup_comment TEXT`

Migration: `_migrate_schema()` in `db.py` uses `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`
for each missing column. Called automatically by `ensure_schema()`. Idempotent.

### Compliment Generation

The only Claude call in this stage: one German sentence per A/B company starting with
"Ihre" or "Ihr", based on scraped website text.

Two paths:
- `via_cli=True`: `_generate_compliment_cli()` — subprocess to `claude.cmd -p --output-format text`
- `via_cli=False`: `_generate_compliment_api()` — anthropic SDK (requires ANTHROPIC_API_KEY)

Only generates compliments for A/B records without one. Skips records with no `scraped_text`.
Writes result to `compliment_draft` in DB and uses it in-memory for the same export run.

### Column Mapping Key Points

- `Source` col reads from raw DB dict (not CompanyRecord dataclass) -- already populated as WLW/ORBIS
- Outreach tracking cols read from raw DB dict (not in dataclass)
- `SSB` col: "ja" if `ssb_flag` is truthy, else blank
- `Owner Age` <- `gesellschafter_age`
- `Services Score` <- `services_score`
- `_record_to_row(rec, raw)` takes both CompanyRecord and raw DB row dict

### Output

`data/output/serienbriefe_new_batch_YYYYMMDD.xlsx`
Single sheet named "Serienbriefe". Validated with openpyxl after write (no formula errors).

---

## Files Modified

| File | Change |
|------|--------|
| `src/pipeline/export.py` | Rewritten: 36-col schema, `_generate_compliment_cli()`, `_generate_compliment_api()`, `via_cli` param throughout, `_record_to_row(rec, raw)` takes raw dict for outreach cols |
| `src/pipeline/db.py` | Added 6 outreach cols to `_CREATE_TABLE`; added `_OUTREACH_COLUMNS`, `_migrate_schema()`; `ensure_schema()` now calls `_migrate_schema()` |
| `pipeline.py` | Added `--via-cli` flag to `export` subparser; wired through dispatch |
| `ai/DESIGN.md` | Serienbriefe Column Mapping section rewritten: 4 groups, 36 cols, Word field codes |
| `.gitignore` | Created: excludes `data/handelsregister.db`, `__pycache__/`, `.env`, `data/output/` |

---

## CLI Usage

```bash
python pipeline.py export --via-cli          # compliments via Claude CLI (OAuth)
python pipeline.py export                    # compliments via API (requires ANTHROPIC_API_KEY)
python pipeline.py export --dry-run          # validate without writing
python pipeline.py export --via-cli --dry-run
```

---

## Deferred

- Leistung Absatz 2 -- left empty; not enough data for two distinct lines
- Kompliment 2 -- left empty at M10; single compliment sufficient for initial outreach
- Mehrwerte -- left empty; requires profile-level configuration not yet defined
- Dashboard write-back for outreach tracking cols -- deferred to M11

---

## Open Issues (added 2026-03-28, to be fixed in M16)

**Kompliment 2 has no DB column.**
`export.py` exports `"Kompliment 2": ""` as a hardcoded empty string. The Word template field `Kompliment_2` is never populated. The Serienbriefe source Excel has both columns filled for the 367 existing approached records — this data has never been ingested into `pipeline.db`.

**Fix (M16):**
1. Add `compliment_2 TEXT` column to `company_records` in `db.py:ensure_schema()`
2. Add `compliment_2: Optional[str] = None` to `CompanyRecord` in `models.py`
3. Update `export.py`: `"Kompliment 2": rec.compliment_2 or ""`
4. Update `ingest.py` Serienbriefe path: map "Kompliment 2" → `compliment_2` (upsert, do not overwrite)
5. Build `src/config/compliment_guide.md` via `pipeline.py build-compliment-guide`: reads full K1+K2 corpus from pipeline.db (after Serienbriefe ingest), separates positive-response records (contact/meeting/financials/offer/deal) from rest, passes to Claude once to synthesize a style guide for K1 and K2 separately. This guide is loaded as context by `_COMPLIMENT_PROMPT` instead of inline few-shot examples. Generation produces both K1 and K2 in a single call returning JSON `{"k1": "...", "k2": "..."}`.

---

## AI VALIDATION RESULTS

**Run date**: 2026-03-26

### Pass 1: --via-cli support + unicode fix

**Bug fixed**: `pipeline.py status` crashed with `UnicodeEncodeError` on Windows (cp1252)
due to `->` arrow character in `cmd_status()`. Fixed to `->`.

**Export added**: `--via-cli` flag for compliment generation via Claude Code CLI subprocess.
Matches the pattern established in `classify.py` `_call_claude_cli()`.

**Live run**:
```
python pipeline.py export --via-cli --verbose
```
Output:
- 5 exportable records (4 B + 1 C)
- All 4 B records already had `compliment_draft` -- no new Claude calls needed
- C record (metpon.de) correctly skipped (compliments only for A/B)
- `validate_no_formula_errors()` passed

### Pass 2: 36-column schema cleanup + outreach tracking

**Changes**:
- 61 cols -> 36 cols (removed internal tracking noise, aligned to Word template)
- Added 6 outreach tracking columns to DB via `_migrate_schema()`
- Added `Source` and `Owner Age` and `Services Score` and `SSB` to analytics group
- `_record_to_row` now takes raw DB dict alongside CompanyRecord for outreach cols + Source

**Validation**:
```
python -c "from src.pipeline.export import SERIENBRIEFE_COLUMNS; print(len(SERIENBRIEFE_COLUMNS))"
# 36

python -c "from src.pipeline.db import _OUTREACH_COLUMNS; print(len(_OUTREACH_COLUMNS))"
# 6

python pipeline.py export --help
# shows --via-cli flag

python pipeline.py export --dry-run --verbose
# 5 exportable records, schema migration ran, DRY RUN -- would export 5 records

pytest tests/ -q
# 160 passed
```
