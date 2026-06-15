# Repuro Lead Generation Pipeline

Automated lead research and classification pipeline for Repuro GmbH. Identifies and qualifies German ambulatory healthcare distributors (Medizintechnik / Sprechstundenbedarf) as M&A platform or add-on targets. Outputs are Serienbriefe-ready rows for the Word mail merge template. Always respond in English.

## Core Working Principles
1. Invoke multiple independent operations simultaneously where possible.
2. Verify solutions before finishing — run the CLI, check output files.
3. Do exactly what's asked — nothing more, nothing less.
4. Never create unnecessary files.
5. Prefer editing existing files over creating new ones.
6. Project structure is in `./ai/ARCHITECTURE.md`.
7. Master plan and milestones are in `./ai/PLAN.md` and `./ai/PLAN-M{n}.md`.
8. Classification logic and target criteria are in `./ai/DESIGN.md`.

## Project Stack
- **Language**: Python 3.11+
- **Data I/O**: pandas, openpyxl
- **Web scraping**: requests, beautifulsoup4, httpx
- **AI classification**: claude CLI subprocess (`--via-cli`, OAuth) only. No API key, no SDK calls. All Claude calls go through the CLI.
- **CLI**: argparse (stdlib)
- **Testing**: pytest
- **Config**: python-dotenv, .env file

## Architecture — One-Line Summary
Ingest → Filter → Scrape → Classify → Enrich → Export → Dashboard

Full architecture: see `./ai/ARCHITECTURE.md`

## Architecture — Non-Negotiable Decisions
- **Primary state store is SQLite (`pipeline.db`), not CSV files.** M3–M11 all read and write to `pipeline.db` via `src/pipeline/db.py`. Never replace this with CSV staging files. The DB path is configured in `.env` (`PIPELINE_DB_PATH`). On the shared OneDrive workspace, DBs live locally on each machine (see `../CLAUDE.md` Workspace Architecture section).
- **CSV files are input-only or final output only:** `data/staging/00_wlw_raw.csv` (M2 scraper output) and `data/output/` (M10 export). No other CSVs.
- **`settings.py` must always contain `PIPELINE_DB_PATH`.** If you see CSV staging path constants (`STAGING_INGESTED`, `STAGING_FILTERED`, etc.) in `settings.py`, that is an error — remove them.
- **`pipeline.py status` reads from `pipeline.db` via `db.get_stage_counts()`.** Never rewrite it to read CSV files.
- If a stash exists (`git stash list`), check it before implementing anything. It may contain valid in-progress work that supersedes committed stubs.

## Critical Constraints
- **Never call paid APIs in bulk without a dry-run flag first.** Always implement `--dry-run` on any command that hits external APIs.
- **Never write to the source Excel file** (`260319_Repuro_Medtech_Targets_v3_claude.xlsx`). It is read-only input. All output goes to `data/output/`.
- **API keys must come from `.env`** — never hardcoded.
- **Classification must use the few-shot examples** from `profiles/medtech_germany.json` (classification.examples array) — never improvise criteria without checking it first.
- **German company names and text**: handle umlauts (ä/ö/ü/Ä/Ö/Ü/ß) correctly throughout. Use UTF-8 everywhere.
- **Rate limiting**: Northdata free tier = 5,000 calls/month. Build in delays and call counts.
- **Excel formula errors are not acceptable** in output files. Validate with openpyxl after writing.

## Classification System (Klass.)
- **A** = Platform candidate: service + distribution mix, 20-80 employees, privately owned, SSB signals, owner 40-70 years old
- **B** = Add-on: fits criteria but smaller scale or weaker service component
- **C** = Maybe: unclear business model, needs manual review
- **D** = Clear no-fit (content): wrong sector, too large, dental-only, pharmacy, hospital-only
- **E** = Special case: interesting but doesn't fit standard criteria (flag for manual review)
- **S** = Subsidiary / PE-backed: ownership gate disqualified — set by M8, NOT by classifier.
         Do not export. Surface in dashboard for Roman's manual review before final exclusion.

Full classification logic: see `./ai/DESIGN.md`

## CLI Entry Point
All commands run via `python pipeline.py <command> [options]`

```bash
python pipeline.py ingest          # Load all source data, deduplicate, save to data/staging/
python pipeline.py filter          # Apply hard pre-qualification filters
python pipeline.py scrape          # Scrape websites for classified companies
python pipeline.py classify        # Run AI classification via Claude API
python pipeline.py enrich          # Fetch ownership data (Northdata) + email (Hunter)
python pipeline.py export          # Generate Serienbriefe-ready Excel output
python pipeline.py dashboard       # Generate HTML dashboard
python pipeline.py run-all         # Full pipeline end-to-end
python pipeline.py status          # Show current pipeline state and counts
```

All commands support `--dry-run` (no API calls, no writes) and `--verbose`.

## Development Commands
```bash
pip install -r requirements.txt    # Install dependencies
pytest tests/                      # Run test suite
python pipeline.py status          # Check pipeline state
python pipeline.py ingest --dry-run  # Test ingest without writing
```

## Code Quality Standards
- **No hardcoded values** — use `src/config/settings.py` constants
- **No silent failures** — all API errors must be caught, logged, and re-raisable
- **Logging**: use Python `logging` module, not print statements
- **Type hints**: all function signatures must have type hints
- **No `any` type equivalents** — avoid `dict` without TypedDict or dataclass for structured data
- **Encoding**: always specify `encoding="utf-8"` on file operations

## Key File Paths (relative to project root)
```
pipeline.py                  # CLI entry point
src/pipeline/ingest.py       # Data ingestion and deduplication
src/pipeline/filter.py       # Pre-qualification hard filters
src/pipeline/scrape.py       # Website content extraction
src/pipeline/classify.py     # Claude CLI classification (keyword pre-filter + AI)
src/pipeline/enrich.py       # Ownership (OffeneRegister/OpenRegister) + email (SMTP) + GF enrichment
src/pipeline/export.py       # Serienbriefe Excel output (36-col)
src/pipeline/export_pdf.py   # PDF letter export (M22) + completeness gate (M23)
src/pipeline/dashboard.py    # 5-tab HTML dashboard + HTTP server (M11-M17)
src/pipeline/normalize.py    # Umlaut restoration, title-case, anrede normalization (M18)
src/pipeline/backfill.py     # AI backfill for K1/K2/leistung (M18)
src/pipeline/check_letter.py # Letter quality validation (M23)
src/pipeline/audit.py        # Dedup audit cross-check (M12)
src/pipeline/region_lookup.py # City→region mapping from Excel (M17)
src/config/settings.py       # Constants, thresholds, paths
profiles/medtech_germany.json # Industry profile + few-shot examples + filter rules + classification criteria
src/utils/excel.py           # Excel read/write helpers
src/utils/web.py             # HTTP/retry/scraping helpers
src/utils/knowledge_base.py  # SQLite cache wrapper (scrape + ownership)
data/input/                  # Source files (read-only)
data/staging/                # WLW raw CSV only (00_wlw_raw.csv)
data/output/                 # Final deliverables (Excel, PDF, dashboard HTML)
```

## Source Data
- `data/input/260319_Repuro_Medtech_Targets_v3_claude.xlsx` — master file (read-only)
  - Sheet `ORBIS_search`: ~498 unique companies with NACE, revenue, MA, ownership
  - Sheet `MASTER_Cleaning`: pre-ORBIS company universe (~2,000 total scope)
  - Sheet `LLM_prep1`: 128 already-classified companies (ground truth for few-shot)
  - Sheet `Serienbriefe`: 378 already-approached companies (deduplication reference)
  - Sheet `Städte-Regionen-Matching`: 709-city region lookup (city → region + preposition)
- `data/staging/00_wlw_raw.csv` — WLW scraper output (input to ingest, read-only after)

## External Services
- **Claude CLI** (`claude.cmd --via-cli`): all AI calls (classification, compliments, leistung) go through the Claude CLI subprocess using OAuth. No ANTHROPIC_API_KEY, no SDK. This is a hard rule — never add direct API calls.
- **OpenRegister.de** (`OPENREGISTER_API_KEY`): ownership data for A/B companies only — Gesellschafter, ownership %, birth years. 11 credits per company. Key in `.env`.
- **OffeneRegister.de** (no key): free SQL API at db.offeneregister.de — Geschäftsführer name lookup by HRB. Data from 2019. Use as free pre-step before OpenRegister.de.
- **Email**: SMTP port 25 verification blocked from residential IP. Email enrichment outsourced to freelancer via export list.

## Definition of Done — Hard Gate

A milestone is NOT complete and must NOT be marked ✅ until:
1. `ai/PLAN-M{n}.md` exists with a filled-in `## AI VALIDATION RESULTS` section.
2. `pytest tests/` passes.
3. The CLI command ran live (`--limit 5` minimum) against real data.
4. `python pipeline.py status` shows expected stage counts.
5. `ai/PLAN-M{n}.md` PM Review section shows PASS (run `/review-milestone` after tests pass).
6. If prompt logic, DB schema, output format, or HTTP behaviour changed: `DESIGN.md` / `ARCHITECTURE.md` updated **in the same commit**.
7. `ai/ROADMAP.md` fully updated — not just the current state block. Specifically:
   - Remove completed milestone spec blocks from "Next Milestones"
   - Check "Delivered (Previously Deferred)" — if this milestone delivered any deferred feature, move it there
   - Check "Open Issues" — if this milestone resolved or mitigated any issue, update its status
   - Verify every item in the Open Issues table is still accurate against the code (not just docs)

Batch commits spanning multiple milestones are prohibited. One milestone = one commit set = one plan file.

This rule exists because M6–M10 were implemented in a single commit with no plan files, causing a full documentation recovery session. Do not repeat this.

## ROADMAP Integrity — Non-Negotiable

The ROADMAP drifted badly through M15–M18: delivered features stayed listed as "deferred", resolved issues stayed "open", completed milestone specs stayed in "Next Milestones". Root cause: non-milestone work (session fixes, ad-hoc commits) bypassed `/execute-milestone` and never touched ROADMAP.md.

**Rule 1 — Every commit that changes pipeline behavior must update ROADMAP.md.**
Not just milestone commits. If a session fix resolves an open issue, delivers a deferred feature, or adds a new bug: update the relevant ROADMAP section in the same commit. No exceptions.

**Rule 2 — Session start: verify ROADMAP before planning or executing.**
Before starting any milestone planning or execution, do a quick audit:
- Read `ai/ROADMAP.md` Open Issues and Deferred sections
- Cross-check the top 3 items against the actual codebase (grep, read the file, check git log)
- If anything is stale, fix it before proceeding
This takes 2 minutes and prevents recommending work that's already done.

**Rule 3 — Never recommend next work based on documentation alone.**
Before suggesting what to work on next, verify against the code that the problem still exists. "The ROADMAP says X is open" is not the same as "X is actually still open."

## Problem Solving
1. Stop — don't overcomplicate.
2. Check `./ai/DESIGN.md` before changing classification logic.
3. Check `./ai/PLAN.md` before adding new milestones or features.
4. Check `profiles/medtech_germany.json` before tuning the classifier prompt.
5. When stuck: ask — clarify approach before building.
