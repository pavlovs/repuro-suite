# M6: AI Classifier — Implementation Record

> This document records what was built and the design decisions made. M6 code is complete.
> For classifier design details see `DESIGN.md § AI Classification Prompt Design`.

---

## What M6 Delivers

For each `pipeline_stage='scraped'` record in `pipeline.db`:
1. Run keyword pre-filter — obvious non-medtech → auto-D, no Claude call
2. Build prompt with few-shot examples from profile
3. Call Claude (CLI subprocess or API) → parse JSON response
4. Write `klass`, `services_score`, flags, `leistung_text`, `reason_code`, `reasoning` to DB
5. Advance `pipeline_stage` to `'classified'`

Output: `pipeline_stage='classified'` records ready for M7 (ownership enrichment, A/B only).

---

## Implementation: `src/pipeline/classify.py`

### Key functions

| Function | Purpose |
|---|---|
| `_is_obvious_d(text, name)` | Keyword pre-filter — returns `(True, reason_code)` for obvious non-medtech |
| `_select_examples(examples, n_per_class)` | Picks 2×A, 1×B, 1×D few-shot examples |
| `_build_prompt(profile, ...)` | Constructs full classification prompt |
| `_call_claude(client, prompt, model)` | Anthropic SDK call with retry |
| `_call_claude_cli(prompt)` | `claude` CLI subprocess call (OAuth, no API key) |
| `_parse_result(raw)` | Validates and normalizes JSON response |
| `classify_cmd(profile, ...)` | Main entry point — orchestrates full batch |

### CLI subprocess approach (`--via-cli`)

Uses `claude -p --output-format text` as a subprocess. Key details:
- `_CLAUDE_CMD = shutil.which("claude") or r"C:\Users\X1\AppData\Roaming\npm\claude.cmd"` — resolves full path at import time to avoid Windows PATH failures in subprocess env
- `env = os.environ.copy(); env.pop("ANTHROPIC_API_KEY", None)` — preserves full PATH, only strips API key so OAuth is used
- List args (not shell string) + `timeout=90` with proper `subprocess.TimeoutExpired` handling
- `shell=False` — avoids `.cmd` resolution issues

### DB write verification

`update_classify_result()` in `db.py` returns `cursor.rowcount`. Caller logs an explicit error on `rowcount == 0` (domain not found — previously a silent failure).

### What is NOT in classify

- **No `compliment_draft`** — generated at export step only, for A/B companies that pass all gates. Saves ~50 tokens per call.
- **No batching yet** — currently 1 company per Claude call. Batching (5 per call) is a planned optimization but not yet implemented.
- **No A/B double-check yet** — planned: re-run all A/B with a second independent call, flag disagreements for manual review.

---

## DB Schema Fields Written

| Field | Type | Notes |
|---|---|---|
| `klass` | TEXT | A/B/C/D/E |
| `services_score` | INT | 0–100 |
| `service_flag` | INT | 0/1 |
| `distributor_flag` | INT | 0/1 |
| `ssb_flag` | INT | 0/1 |
| `leistung_text` | TEXT | 2–4 German words |
| `reclassify_reason` | TEXT | stores `reason_code` (column reused) |
| `reasoning` | TEXT | max 1 sentence |
| `classified_at` | TEXT | ISO timestamp |
| `pipeline_stage` | TEXT | set to `'classified'` |

`compliment_draft` column exists in schema but is written at export stage only.

---

## CLI Commands

```bash
python pipeline.py classify --via-cli --verbose        # use Claude Code OAuth
python pipeline.py classify --via-cli --limit 10       # test on 10 companies
python pipeline.py classify --dry-run                  # count without calling
python pipeline.py classify --quality --via-cli        # sonnet instead of haiku (API only)
```

---

## Known Issues / Planned Improvements

| Issue | Status | Fix |
|---|---|---|
| 1-per-call → rate limit at scale | Open | Batch 5 companies per call |
| No A/B double-check | Open | Second independent call for A/B, flag disagreements |
| Pre-filter keyword list narrow | Open | Expand after reviewing misclassifications |
| Scrape text quality (BeautifulSoup) | Open | Replace `clean_html()` with Trafilatura |
| DB write miss (domain mismatch) | Fixed | `rowcount` check + explicit error log |
| CLI PATH failure on session resume | Fixed | Full path resolution + `os.environ.copy()` |

---

## Validation Results (first real run, March 2026)

- **Input**: 204 companies at `pipeline_stage='scraped'`
- **Output**: 161 classified (57 initial ok + 104 after session resume), 43 CLI errors (PATH failures during session suspend)
- **Grade distribution**: B: 4, C: 1, D: 60, rest not saved due to DB write bug (pre-fix)
- **A/B companies**: 4 × B — straetz-novetec.de, medizintechnik-web.de, mamedis.de, rennecke-medic.com
- **DB write bug**: ~96 "ok" results not saved — root cause: session suspend caused connection state issues; fixed with rowcount check
- **Observation**: 204 companies >> expected 34 — ORBIS/MASTER_Cleaning data contains many non-medtech companies; pre-filter addresses this going forward
