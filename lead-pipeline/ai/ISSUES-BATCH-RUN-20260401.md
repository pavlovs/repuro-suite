# Issues Found During Batch Run (2026-04-01)

Tracking bugs and quality issues discovered during the 50-target letter production run.

---

## Code Fixes — RESOLVED

| # | Issue | Severity | Where | Fix | Resolved |
|---|-------|----------|-------|-----|---------|
| 1 | **Scraper crashes on httpx.InvalidURL** — bad redirect URL (absolute path in Location header) killed entire batch. `httpx.InvalidURL` inherits from `Exception` directly, not from `httpx.RequestError`, so it was uncaught in `fetch_with_retry` and propagated up to `scrape_batch_cmd`. | Medium | `src/utils/web.py` → `fetch_with_retry` | Added explicit `except httpx.InvalidURL` handler as the first catch clause — returns `None` immediately, no retry (URL won't fix itself). Workaround `except Exception` in `scrape.py` remains as safety net. | ✅ 2026-04-10 |
| 2 | **Only 1 Gesellschafter stored** — `_parse_owners` ran `max()` to find the majority owner then discarded all other shareholders. Multi-owner companies (50/50 splits, holding structures) silently lost minority owners. `gesellschafter_name` only ever held the top owner. | Medium | `src/pipeline/enrich.py` → `_parse_owners`; `src/pipeline/db.py`; `src/pipeline/models.py`; `src/utils/knowledge_base.py`; dashboard | Added `all_gesellschafter` TEXT column (JSON array, sorted by % desc). `_parse_owners` now builds the full list before the `max()` selection and includes it in every return path. Threaded through `update_ownership_result`, KB `save_ownership`/`get_ownership`, `CompanyRecord`, dashboard data columns, and side panel display. | ✅ 2026-04-10 |

---

## Tests Added

| Test file | Test names | Covers |
|-----------|-----------|--------|
| `tests/test_utils.py` | `TestFetchWithRetryInvalidUrl` (3 tests) | Bug 1: InvalidURL returns None, no retry, extract_page_text survives |
| `tests/test_enrich.py` | `TestParseOwners::test_all_gesellschafter_*` (4 tests) | Bug 2: single owner, multi owner, empty list, sort order |

Suite: **480 passed, 0 failures** (was 475 before fixes + 5 new tests passing).

---

## Important: Backfill Required for Existing Records

`all_gesellschafter` will be **NULL for all records enriched before 2026-04-10**. The raw OpenRegister owners list was never cached — only the parsed single-owner result was stored. To populate existing records, re-run `enrich` (costs ~11 OpenRegister credits per A/B company). KB cache entries from before the fix will also be missing `all_gesellschafter`; they must expire (180-day TTL) or be manually cleared before a re-run will repopulate them.

The dashboard side panel gracefully falls back to `gesellschafter_name` (single field) for records that have not been re-enriched.

---

## Quality Issues (Per-Letter)

Format: domain | error count | issues found

| Domain | Errors | Issues |
|--------|--------|--------|
| | | |

## Metrics

- Total A/B classified this run: _
- A/B after S-gating: _
- Letter-ready (all 10 fields): _
- PDF-rendered: _
- Error-free letters: _ / _ (_%)
- 1-error letters: _ / _ (_%)
- 2+ error letters: _ / _ (_%)
