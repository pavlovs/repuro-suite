# M16: Current BA Prep Tab — Lead Editing Console

## Summary

Transform the Current BA Prep tab from a read-only funnel summary into a working console for preparing the next Briefaktion. Add a tailored lead table, click-to-edit in the side panel for email and both compliment columns, a manual lead-add flow, and the `compliment_2` DB column with ingest of existing Serienbriefe values.

---

## Why Now

M15 introduced the tab structure. The BA Prep tab currently shows:
- 6 KPI cards (counts only)
- A pipeline funnel table (read-only)
- A blockers list with CLI commands as plain text

A user cannot act on any of this. To actually prepare a BA, you need to:
1. See the A/B leads and their readiness state
2. Click a record → edit email and both compliments in the side panel
3. Add a lead you found manually
4. See blockers as a clear action queue (no execution trigger needed now)

---

## Why compliment_2 was never a DB column

`export.py` has exported `"Kompliment 2": ""` as a hardcoded empty string since M10. The original design generated one AI compliment (`compliment_draft` = Kompliment 1) and left the second slot for manual entry in Word — explicitly deferred in PLAN-M10.md. The Serienbriefe tab in the source Excel has both `Kompliment 1` and `Kompliment 2` columns populated for the 367 existing approached records. These should be ingested into the DB and used as examples when generating new compliments.

---

## Scope

### 1. DB migration
- Add `compliment_2 TEXT` column to `company_records` via `ALTER TABLE ADD COLUMN` in `db.py:ensure_schema()`
- Update `CompanyRecord` dataclass in `models.py`: add `compliment_2: Optional[str] = None`
- Update `export.py`: `"Kompliment 2": rec.compliment_2 or ""` (replaces hardcoded `""`)

### 2. Ingest existing Serienbriefe Kompliment 1 + 2
- Add column index constants to `ingest.py`: `_C_K1 = 22`, `_C_K2 = 23` (confirmed: "Kompliment 1" at col 22, "Kompliment 2" at col 23)
- Add `"compliment_draft": _s(row[_C_K1])` and `"compliment_2": _s(row[_C_K2])` to the `to_process.append({...})` dict in `ingest_serienbriefe()`
- Update `db.py:upsert_serienbriefe_record` — both the UPDATE block (add `compliment_draft = COALESCE(compliment_draft, :compliment_draft)` and same for `compliment_2`) and the INSERT column list + VALUES. Column lists are explicit/hardcoded in the SQL so must be changed in both branches.
- Do not overwrite if already populated (COALESCE guard in UPDATE; INSERT only for new records)

### 3. Compliment knowledge guide

**Why a guide instead of few-shot examples in the prompt:**
K1 and K2 appear at different positions in the Serienbrief and serve different rhetorical functions. A persistent knowledge file can be updated as we gather more data, weights positive-response examples explicitly, and keeps the generation prompt clean. It is generated once from the full corpus and reused on every export run.

**Data available (confirmed from source Excel):**
- 366 K1 values, 367 K2 values across all 367 Serienbriefe records
- 57 positive-response records (Contact Made: 28, Initial meeting done: 26, Financials Received: 3)
- K1 examples: "Ihre umfassende Erfahrung...", "Ihr langjähriges Know-how..." — typically longevity/experience angle
- K2 examples: "Ihr einzigartiges 360° Servicekonzept...", "die Spezialisierung auf Radiologien..." — specific service/product angle

**New command: `pipeline.py build-compliment-guide`**
- Reads K1/K2 corpus directly from source Excel Serienbriefe sheet (columns 22 and 23: "Kompliment 1", "Kompliment 2"). Reason: `compliment_draft` in pipeline.db is only populated for 25 records (M10 export runs) — pipeline.db is not the right source for this. The Excel has all 366/367 K1/K2 values.
- Cross-references domain column (col 2) with pipeline.db `outreach_status` to identify positive-response records (contact/meeting/financials/offer/deal) — these are weighted higher in the guide
- Passes corpus to Claude (both groups clearly labelled) with prompt: analyse K1 and K2 patterns separately; K1 opens with the company's history/experience (position: opening paragraph of letter); K2 highlights a specific service or product differentiator (position: second paragraph); prioritize patterns from positive-response records; output a structured .md guide with: position in letter, grammatical pattern, typical length, opening word distribution, 5 best examples per slot (positive-response ones first), 3 patterns to avoid
- Saves result to `src/config/compliment_guide.md` — committed to git (it's a knowledge/config file, not generated output; equivalent to `examples.json`)
- One-time operation, but re-runnable as data grows
- `--dry-run` shows corpus stats (K1/K2 count, positive-response count) without calling Claude
- `--via-cli` flag: uses Claude CLI subprocess (OAuth); default uses Anthropic API (same pattern as `export` and `classify`)

**Updated compliment generation in export.py:**
- `_COMPLIMENT_PROMPT` loads `src/config/compliment_guide.md` as context (prepended to the company-specific prompt)
- Single Claude call generates both K1 and K2, returns JSON `{"k1": "...", "k2": "..."}`
- Response parsed: `compliment_draft` ← k1, `compliment_2` ← k2
- If guide file does not exist: warn and fall back to single-sentence prompt (no crash)
- `_generate_compliment_cli()` and `_generate_compliment_api()` both updated to return `tuple[Optional[str], Optional[str]]` (k1, k2) instead of `Optional[str]`
- New `db.update_compliments(conn, domain, k1, k2)` function to write both fields; existing `update_compliment_draft` kept but no longer called by generation path
- `_fill_missing_compliments` updated to call `update_compliments` and set both `rec.compliment_draft` and `rec.compliment_2`

### 4. PATCH whitelist — add new editable fields

`dashboard.py:_WRITEBACK_FIELDS` currently only allows: `klass`, `outreach_status`, `outreach_sent_at`, `outreach_comment`, `followup1_at`, `followup2_at`, `followup_comment`. The side panel save calls `PATCH /api/company/{domain}` — any field not in the whitelist is silently dropped.

Must add: `gf_email`, `compliment_draft`, `compliment_2` to `_WRITEBACK_FIELDS`.

### 5. New server endpoint (dashboard.py)

**`POST /api/ingest-domain`** — add lead manually
- Body: `{"domains": ["example.de", "other.de"]}`
- For each domain: check if already in DB; if not, create a minimal `company_records` row with `domain`, `ingested_at`, `pipeline_stage='ingested'`, `source='manual'`, all other fields NULL
- Record starts at the very beginning of the funnel — still needs filtering, scraping, classifying
- Response: `{"added": 2, "skipped": 1, "details": [...]}`
- Serve mode only

### 6. Prep lead table (dashboard.html)
- New section at the bottom of the BA Prep tab, below funnel + blockers
- Title: "A/B Targets — Prep View"
- Default filter: `klass IN ('A','B')` and `briefaktion IS NULL`
- "Show all current" toggle to include C/D/E records
- Columns (in order): Name | Domain | Region | MA | Owner Age | Klass | SSB | Svc Score | Email | Kompliment 1 | Kompliment 2 | (open icon)
  - No Source column. No Outreach column. No BA column.
  - Email and Kompliment columns show truncated preview text (not editable in the table itself)
  - Klass shows the badge (read-only in table)
  - Open icon (↗) → calls `openPanel(record)` to open the side panel
- Sortable headers (reuse existing `sortBy` pattern, separate sort state from Lead Table)
- Row count shown below table
- Table is **read-only** — all editing happens in the side panel after clicking a row

### 7. Side panel — edit mode for Prep tab records
- Existing panel already shows email, klass dropdown, outreach controls
- Add to panel for `compliment_draft` field: **editable `<textarea>`** (3 rows) with a "Save" button → PATCHes `/api/company/{domain}` with `{compliment_draft: value}`
- Add same for `compliment_2`: editable textarea + Save button
- Email field (`gf_email`): change from read-only display to an `<input type="text">` with Save button → PATCHes `{gf_email: value}`
- Remove the "Regenerate compliment" button entirely (was in existing panel — not needed)
- All edit controls visible only in serve mode (show read-only text in dry-run mode)
- Save confirmation: brief "Saved ✓" inline text that fades after 2s

### 8. "Add lead manually" button
- Position: aligned right, next to the KPI card row header
- In serve mode only (hidden otherwise)
- Click → modal overlay:
  - Title: "Add leads by domain"
  - Textarea: one domain per line (or comma-separated)
  - Submit → POST `/api/ingest-domain` → shows result: "Added 2, skipped 1 (already in DB)"
  - Close button. On success: calls `renderAll()` to refresh counts.

### 9. Blockers section — no execution trigger
- Blocker items remain as display-only (count + label + CLI command as plain text)
- No run-button or execution from browser — deferred to long-term roadmap
- This is already the current behavior, no change needed here

---

---

## Tests

All new tests go in `tests/test_m16.py`.

### DB migration
- `test_compliment_2_column_added`: call `ensure_schema()` on a fresh in-memory DB → assert `compliment_2` column exists in `PRAGMA table_info(company_records)`

### Serienbriefe ingest — K1/K2 mapping
- `test_serienbriefe_ingest_maps_compliments`: construct a minimal mock Serienbriefe row with "Kompliment 1" = "Test K1" and "Kompliment 2" = "Test K2", run through the ingest path → assert `compliment_draft = "Test K1"` and `compliment_2 = "Test K2"` in pipeline.db
- `test_serienbriefe_ingest_does_not_overwrite_existing`: if `compliment_draft` already populated for a domain, ingest must not overwrite it (upsert guard)

### Compliment generation — dual output
- `test_generate_compliment_returns_k1_k2`: mock the Claude CLI subprocess response as JSON `{"k1": "Ihre Erfahrung...", "k2": "Ihr Servicekonzept..."}` → assert function returns `("Ihre Erfahrung...", "Ihr Servicekonzept...")`
- `test_generate_compliment_api_returns_k1_k2`: same for the API path using `unittest.mock.patch` on the Anthropic client
- `test_generate_compliment_fallback_on_malformed_json`: if Claude returns non-JSON, function logs a warning and returns `(None, None)` — no crash

### Compliment guide
- `test_build_compliment_guide_dry_run`: run `python pipeline.py build-compliment-guide --dry-run` → exits 0, prints example count, does NOT create or modify `compliment_guide.md`
- `test_compliment_prompt_loads_guide`: if `compliment_guide.md` exists, `_COMPLIMENT_PROMPT` includes its contents; if file is missing, prompt still runs (no FileNotFoundError)

### Export — Kompliment 2 in output
- `test_export_kompliment_2_in_output`: create a test record with `compliment_2 = "Test K2"` → run export → assert "Kompliment 2" column in output Excel contains "Test K2", not `""`

### Dashboard — ingest-domain endpoint
- `test_ingest_domain_adds_record`: POST `{"domains": ["newdomain.de"]}` to `/api/ingest-domain` → assert record appears in pipeline.db with `source='manual'`, `pipeline_stage='ingested'`, all classification fields NULL
- `test_ingest_domain_skips_duplicate`: POST with a domain already in DB → response shows `skipped: 1`, DB unchanged

---

## What stays the same

- `computeView()`, `renderAll()`, `renderPrepKPIs()`, `renderPrepFunnel()`, `renderBlockers()` — minor extension only
- `/api/patch` and `/api/company/{domain}` PATCH endpoints — reused for panel saves
- All other tabs unchanged

---

## Files changed

| File | Change |
|------|--------|
| `src/pipeline/db.py` | `ensure_schema()`: add `compliment_2` via `ALTER TABLE ADD COLUMN` |
| `src/pipeline/models.py` | Add `compliment_2: Optional[str] = None` to `CompanyRecord` |
| `src/pipeline/export.py` | `"Kompliment 2": rec.compliment_2 or ""`; generation functions updated to return `tuple[str, str]` (k1, k2); prompt loads `compliment_guide.md` as context |
| `src/pipeline/ingest.py` | Map "Kompliment 1"→`compliment_draft`, "Kompliment 2"→`compliment_2` in Serienbriefe ingest path |
| `src/pipeline/compliment_guide.py` | New module: `build_guide(db_path, output_path, dry_run)` — reads corpus, calls Claude once, saves `compliment_guide.md` |
| `src/config/compliment_guide.md` | Knowledge/config file — committed to git (equivalent to `examples.json`); regenerate with `build-compliment-guide` when corpus grows |
| `pipeline.py` | Add `build-compliment-guide` subcommand with `--dry-run` |
| `src/pipeline/dashboard.py` | Add `/api/ingest-domain` POST handler |
| `src/pipeline/templates/dashboard.html` | Prep lead table, panel edit fields, "Add lead manually" modal, remove regenerate button |
| `tests/test_m16.py` | All new tests (see Tests section) |
| `ai/PLAN-M16.md` | This file |
| `ai/PLAN.md` | M16 row; M10 marked 🔄 (open fix for compliment generation) |
| `ai/ROADMAP.md` | M16 scope updated; open issues updated |

---

## Implementation steps

1. **DB + model** — `db.py` ensure_schema + `models.py` + `export.py` K2 output fix
2. **Ingest Serienbriefe K1+K2** — update `ingest.py` Serienbriefe path to map both columns
3. **`compliment_guide.py`** — new module + `pipeline.py build-compliment-guide` command
4. **Export generation** — update `_generate_compliment_cli/api` to return `(k1, k2)`, load guide as context, parse JSON response
5. **Tests** — `tests/test_m16.py` covering all cases in Tests section
6. **dashboard.py** — add `/api/ingest-domain` handler
7. **Prep lead table HTML + CSS** — new section, tailored columns, click opens panel
8. **Side panel edit fields** — email, compliment_1, compliment_2 as editable textareas with Save; remove regenerate button
9. **"Add lead manually" modal** — button + modal HTML/JS + API call
10. **Run `build-compliment-guide`** — execute once against source Excel to generate `src/config/compliment_guide.md`; commit the file
11. **Verification** — pytest + dry-run + live serve test

---

## Verification

```
pytest tests/ -q                                    → all pass, no regressions
python pipeline.py dashboard --dry-run              → builds without error, > 4MB
python pipeline.py dashboard --serve                → serve starts on port 8765
```

Manual checks in browser:
- Current BA Prep tab shows KPI cards + funnel + blockers + prep lead table
- Lead table defaults to A/B only; "show all current" toggle works
- Click a row → side panel opens with editable email, K1, K2 fields
- Email edit: type → Save → confirm via DB query that value persisted
- K1/K2 edit: type → Save → persisted
- Klass change in panel → row in table updates after `renderAll()`
- "Add lead manually" → type `test-domain.de` → "Added 1" message → funnel count increments
- No "Regenerate" button visible anywhere in panel

---

## Definition of done

- [x] `pytest tests/ -q` passes (includes all `test_m16.py` tests)
- [x] `python pipeline.py dashboard --dry-run` builds without error
- [x] `compliment_2` column exists in `pipeline.db`
- [x] `compliment_2` populated from Serienbriefe ingest for existing approached records
- [x] Kompliment 2 in export output comes from DB, not hardcoded `""`
- [x] `python pipeline.py build-compliment-guide --dry-run` exits 0, prints corpus stats
- [x] `src/config/compliment_guide.md` generated, contains K1 and K2 sections, committed to git
- [x] Compliment generation produces both K1 and K2 in a single call; fallback works if guide missing
- [x] Side panel: email, K1, K2 all editable + save works
- [x] "Add lead manually" writes to DB, record appears in funnel
- [x] No "Regenerate" button anywhere in panel
- [x] PLAN.md, ROADMAP.md updated

---

## AI validation results

**Date**: 2026-03-28

**Commands run:**
```
pytest tests/ -q
→ 181 passed in 4.18s

python pipeline.py build-compliment-guide --dry-run
→ Corpus entries: 367, K1=366, K2=367, Positive-response=57, DRY RUN — guide not written

python pipeline.py build-compliment-guide --via-cli
→ Guide written to src/config/compliment_guide.md (7010 chars)

python pipeline.py dashboard --dry-run
→ Loaded 2420 records. A:100 B:296 C:4 D:117 E:3 S:2
→ DRY RUN — HTML not written (would be 5,117,333 chars)
```

**Deviations from plan:**
- None. All 11 implementation steps executed as planned.
- Browser execution (scrape/classify buttons in BA Prep tab) moved to ROADMAP.md Deferred per user instruction.
