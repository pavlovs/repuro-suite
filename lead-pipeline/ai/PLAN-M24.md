# M24: Classifier Refactor — 5-Thesis Taxonomy

## Summary

Replaces the single-axis ambulatory-distributor classifier with a 5-thesis taxonomy (Full-Service-Partner, Installation-Partner, Specialty-Distributor, Independent-Service, General-Distributor) plus `None`. Each target gets a mutually-exclusive `thesis` label, `specialty_focus` (nullable), `customers`, and `products` — in addition to the existing A/B/C/D/E klass. Classifier logic: free keyword pre-scan → single Claude CLI call with a Q1–Q5 decision-tree prompt and hints from the pre-scan → deterministic post-LLM guardrails. Backlog reprocessing of the 2,420 existing records is explicitly OUT of scope and deferred to a later milestone.

## HOW TO EXECUTE THIS MILESTONE

From `ai/PLAN.md` Definition of Done:

1. `PLAN-M24.md` exists with all sections filled in, including a non-empty `## AI VALIDATION RESULTS` section.
2. `pytest tests/` passes — no regressions.
3. The command runs live — at minimum `classify --limit 5` against real data.
4. `python pipeline.py status` shows expected stage counts.
5. `DESIGN.md` and `ARCHITECTURE.md` updated in the same commit (M24 touches prompt logic, output schema, DB fields).
6. One commit per milestone — implementation + tests + doc updates together.

Execution protocol: `/execute-milestone` (see `~/.claude/commands/execute-milestone.md`).

## Locked Decisions

1. **Five theses, mutually exclusive** — plus `None` for records that fit none. Named: `Full-Service-Partner`, `Installation-Partner`, `Specialty-Distributor`, `Independent-Service`, `General-Distributor`.
2. **Thesis replaces the old flag soup in the core classification schema.** `ssb_flag`, `service_flag`, `distributor_flag` stay as diagnostic signals (reported by the LLM and by the pre-scan) but do NOT drive klass directly — the thesis does. No new `installation_flag` column (redundant with thesis).
3. **New DB columns** (via `ALTER TABLE ADD COLUMN`, forward-only per M4 principle):
   - `thesis TEXT` — one of the 5 labels or NULL
   - `specialty_focus TEXT` — free-text short label (e.g. "Ultraschall", "Endoskopie") when thesis=Specialty-Distributor; else NULL
   - `customers TEXT` — short comma-separated string from controlled vocabulary
   - `products TEXT` — short comma-separated string from controlled vocabulary
   - `thesis_confidence REAL` — 0.0–1.0, from LLM
4. **Single LLM call per target**, not a multi-step chain. Q1→Q5 decision tree is embedded in the prompt; LLM answers all fields in one JSON response. Keeps token cost equivalent to current classifier.
5. **Keyword pre-scan runs first and is injected into the prompt as "hints"**, not as a hard gate (except `_is_obvious_d` which stays auto-D). The LLM still makes the final call — hints just bias it and reduce ambiguity. Pre-scan also emits diagnostic flags (ssb/service/distributor/installation/specialty) for post-LLM guardrails.
6. **Post-LLM deterministic guardrails**:
   - `General-Distributor` → klass cap at B (never A), regardless of LLM-assigned klass.
   - If LLM picks `Installation-Partner` but pre-scan `install_core < 2` OR `install_disq > 0` → flip to best-scoring alternative thesis, lower klass by one step.
   - If LLM picks `Specialty-Distributor` but pre-scan specialty ratio < 0.5 → flip to `None` and set klass=C (Unclear).
   - If `thesis_confidence < 0.5` → klass capped at C regardless of LLM assignment.
7. **A/B/C/D/E klass semantics** unchanged. Thesis orthogonal to klass — klass remains the A-to-E M&A-fit axis. Binding rules:
   - A/B: thesis in {Full-Service-Partner, Specialty-Distributor, Independent-Service, Installation-Partner}, size 5–80 MA, service mix present.
   - B-cap: thesis=General-Distributor (no service → weak add-on).
   - D: thesis=None AND no medtech context (auto-D via `_is_obvious_d` keeps working).
   - Installation-Partner → usually A only if ambulatory/surgery focus present; hospital-only installation → klass B.
8. **Few-shot examples**: 10 examples in `profiles/medtech_germany.json` — 2 per thesis, each with a "trap pair" sibling (e.g. a General-Distributor that LOOKS like Full-Service) to teach disambiguation. Live-deal domains used: HWV, KVG, Com2Med (Full-Service-Partner); Medizin & Service (Installation-Partner); Sonowied, IST Medical (Specialty-Distributor); Golmed (Independent-Service).
9. **Controlled vocabulary for customers and products** defined in `profiles/medtech_germany.json` under new `classification.vocabulary` key. LLM constrained by prompt + post-LLM validation (drops tokens not in vocab, lowercases, dedups).
   - customers: `hausarzt, facharzt, gynäkologe, chirurg, orthopäde, hno, urologie, kardiologie, augenarzt, dermatologie, zahnarzt, klinik, krankenhaus, pflegeheim, reha, labor, industrie, privat`
   - products: `sprechstundenbedarf, praxisbedarf, hygiene, op-bedarf, verbrauchsmaterial, ultraschall, endoskopie, ekg, beatmung, dialyse, röntgen, sterilisation, labordiagnostik, rehatechnik, möbel, installation, wartung, kalibrierung`
10. **Keyword taxonomy** implemented as a new module `src/pipeline/keyword_scan.py` — exposes `scan(text) -> KeywordHints` dataclass. Taxonomy mirrors the validated v3 taxonomy from `repuro-data/_classify_validate_v3.py` (INSTALL_CORE, INSTALL_DISQ, FS, GD, SERVICE, MEDTECH_CTX, BRANDS, SPECIALTY dict with 14 categories). `_is_obvious_d` stays where it is in `classify.py`.
11. **Backlog reprocessing deferred.** M24 only ships the new classifier + tests + 5-live-domain validation. Re-running classify over the 2,420 existing records is a separate, later milestone (not M25 — M25 is scraping).
12. **No new external dependencies.** Pure-Python keyword scan + existing Claude CLI path.

## Plan

### Step 1 — DB schema migration
`src/pipeline/db.py` (or wherever `ensure_schema` lives in classify.py / models):
- Add to `ensure_schema()`: `ALTER TABLE company_records ADD COLUMN thesis TEXT`, `specialty_focus TEXT`, `customers TEXT`, `products TEXT`, `thesis_confidence REAL`.
- Guard with `try/except sqlite3.OperationalError` (idempotent).
- Verify: open a fresh clone of `pipeline.db`, run any CLI command, confirm columns exist via PRAGMA.

### Step 2 — Keyword pre-scan module
Create `src/pipeline/keyword_scan.py`:
```python
from dataclasses import dataclass

@dataclass
class KeywordHints:
    install_core: int
    install_disq: int
    fs: int
    gd: int
    svc: int
    medtech_ctx: int
    brands: int
    specialty_top: str | None
    specialty_ratio: float
    flags: dict  # {"ssb": bool, "service": bool, "distributor": bool, "installation": bool, "specialty": bool}

INSTALL_CORE = [...]  # from _classify_validate_v3.py
INSTALL_DISQ = [...]
FS = [...]
GD = [...]
SERVICE = [...]
MEDTECH_CTX = [...]
BRANDS = [...]
SPECIALTY = {...}  # 14 categories

def scan(text: str) -> KeywordHints: ...
def hints_for_prompt(h: KeywordHints) -> str: ...  # short human-readable block for LLM
```
Copy keyword lists verbatim from `repuro-data/_classify_validate_v3.py` (they are validated). No behavior change from v3.

### Step 3 — Rewrite `classify.py`
- Keep `_is_obvious_d()` and `_build_name_index()` pre-filters unchanged.
- Replace `_call_claude_cli()` prompt with Q1–Q5 decision tree. Prompt injects:
  - Target description (from profile)
  - 10 few-shot examples (from profile)
  - Controlled vocabulary for customers + products
  - Keyword hints block from `keyword_scan.hints_for_prompt()`
- Replace `_parse_result()` with a parser that extracts JSON keys: `klass`, `thesis`, `specialty_focus`, `customers`, `products`, `thesis_confidence`, `ssb_flag`, `service_flag`, `distributor_flag`, `installation_flag`, `leistung_text`, `mehrwerte`, `reasoning`.
- Add `_apply_guardrails(result, hints)` — implements the 4 deterministic rules from locked decision #6. Returns corrected result + appends to `reasoning` when a guardrail fires.
- Write all new columns plus legacy columns (thesis, specialty_focus, customers, products, thesis_confidence are new; ssb/service/distributor flags preserved).

### Step 4 — Extend `medtech_germany.json`
- Replace `classification.target_description` with a 5-thesis version explaining each thesis in 2 sentences.
- Add `classification.theses` — dict of 5 keys, each with `description`, `a_criteria`, `b_criteria`, `trap_signals`.
- Add `classification.vocabulary` — `customers`, `products` arrays from locked decision #9.
- Replace `classification.examples` — 10 entries, 2 per thesis, each with: `domain`, `scraped_text_snippet` (~300 chars), `klass`, `thesis`, `specialty_focus`, `customers`, `products`, `reasoning`, `trap_note` (optional — what makes this one a teaching case).

### Step 5 — Unit tests
Create `tests/test_keyword_scan.py`:
- One test per thesis: feed a hand-crafted synthetic scraped_text that should score high for that thesis, assert hints come back with correct top signals.
- Edge cases: empty string, no medtech context, ambiguous text.

Create `tests/test_classify_m24.py`:
- Mock `_call_claude_cli` to return canned JSON for 7 live-deal fixtures (scraped_text snippets captured at planning time from HWV, KVG, Com2Med, Medizin & Service, Sonowied, IST Medical, Golmed).
- Assert each returns the expected thesis + klass.
- Guardrail tests:
  - LLM says `Installation-Partner` + hints `install_core=0` → flipped
  - LLM says `Specialty-Distributor` + hints `specialty_ratio=0.3` → flipped to None
  - LLM says `General-Distributor` + klass=A → klass capped at B
  - LLM `thesis_confidence=0.3` + klass=A → klass capped at C
- Parser robustness: malformed JSON, missing fields, unknown vocabulary tokens.

### Step 6 — Live CLI run (`--limit 5`)
- Select 5 unclassified records from pipeline.db via `classify --limit 5`.
- Verify DB columns populated; verify `python pipeline.py status` shows counts.
- Record the 5 outputs in AI Validation Results.

### Step 7 — Update DESIGN.md + ARCHITECTURE.md
- `ARCHITECTURE.md` M6 section: add pre-scan step + thesis columns + guardrail step.
- `DESIGN.md`: add "Classifier — 5-Thesis Taxonomy" section documenting prompt structure, guardrails, and trap-pair rationale.
- Update `ai/ROADMAP.md` Foundation table: add M24 row ✅. Update Current State block.
- Update `ai/PLAN.md` Milestone Overview: add M24 row ✅.

### Step 8 — Commit
One commit: "feat(M24): 5-thesis classifier taxonomy with keyword pre-scan and decision-tree prompt"

## Better Engineering Notes

- **Few-shot staleness**: the "Classifier examples static — dashboard reclassifications don't feed back into few-shot" Open Issue in ROADMAP.md remains open after M24. Worth a follow-up milestone (M26 candidate): auto-harvest high-confidence dashboard reclassifications into a versioned examples file.
- **Vocabulary drift**: controlled vocab for customers/products is intentionally small (~18 each). Grow it only when a real gap appears, not speculatively — dashboard UI can display the raw LLM output alongside the normalized vocab for visibility.
- **`_apply_guardrails` is the correct place for ALL deterministic rules**. Resist the temptation to push business logic into the prompt — anything a Python rule can enforce cheaply should live in the rule, not burn tokens on every call.
- **Backlog reprocess (~2,420 records) will cost real tokens.** When that milestone runs, use `--via-cli` (already default per memory), batch, and checkpoint to tolerate interruption. Estimate: ~€0 direct cost (OAuth subscription covers it), ~2–3 hours wall time.

## AI Validation Plan

Commands the executor will run:
```
pytest tests/ -x -q                    # expect: all green, 490+ passing (was 467 after M23)
pytest tests/test_keyword_scan.py -v   # expect: all thesis fixtures pass
pytest tests/test_classify_m24.py -v   # expect: 7 live-deal + 4 guardrail cases pass
python pipeline.py classify --limit 5  # expect: 5 records written with thesis populated
python pipeline.py status              # expect: classified count +5, other stages unchanged
sqlite3 data/pipeline.db "SELECT domain, klass, thesis, specialty_focus, customers, products, thesis_confidence FROM company_records WHERE thesis IS NOT NULL LIMIT 10"
```

Expected completion signal: 5 new classifications with non-null thesis in pipeline.db, zero pytest regressions, ARCHITECTURE.md + DESIGN.md updated in the same commit as code.

## AI Validation Results

_To be filled by the executor._

## User Validation Walkthrough

1. Pull the M24 commit. Run `pytest tests/ -x -q` → expect all green.
2. `python pipeline.py classify --limit 5` on a fresh set of unclassified records.
3. Open the dashboard → Lead Table tab. Confirm new `thesis` column renders (dashboard column add is NOT part of M24 — will appear as raw in company card panel).
4. Spot-check one record per live deal in pipeline.db:
   - HWV → thesis=Full-Service-Partner, klass=A
   - Medizin & Service → thesis=Installation-Partner, klass=A
   - Sonowied → thesis=Specialty-Distributor, specialty_focus≈"Ultraschall", klass=A
   - Golmed → thesis=Independent-Service, klass=A or B
5. Review `_classify_validate_v3.py` output on the same 170 sent-letter sample — expect thesis distribution to roughly match (Independent-Service ~25–30%, Full-Service ~20–25%, Specialty ~10%, Installation small, GD ~10%, None/Unclear ≤15%).
6. If any live deal comes back with wrong thesis: add it as a new trap-pair example in `medtech_germany.json` and re-run classify on that domain. Do NOT adjust guardrails for a single bad case.
