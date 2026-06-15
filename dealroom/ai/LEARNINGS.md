# DEALROOM — Learnings

Only things not derivable from reading the code. If a lesson is already in CLAUDE.md, ARCHITECTURE.md, or obvious from the implementation, delete it here. Keep this under 25 lines.

---

**`\b` word-boundary fails on filenames with underscore separators.**
Python's `\b` treats `_` as `\w`. Use `(?<!\d)(20[1-9][0-9])(?!\d)` for year extraction from DATEV filenames.

**SQLite ATTACH URI mode fails on Windows with drive-letter paths.**
Use plain `ATTACH DATABASE ? AS allex` with the path string. Read-only enforced by application invariant.

**Never hard-code Excel cell addresses for financial extraction.**
GuV/Bilanz layouts vary per target. Dump raw row text, pass to Claude with explicit JSON schema.

**Claude needs an explicit JSON schema in the extraction prompt.**
Without it, Claude invents field names. Schema in prompt → structured output every time.

**Prompts to Claude subprocess via stdin, not CLI args.**
Company names contain `&`, `+`, `"`, newlines — these break Windows shell quoting. Always `input=`.

**Claude CLI may return valid JSON wrapped in markdown fences or prefixed with prose.**
`_parse_questions` strips fences and leading non-JSON text. Wrap in try/except and retry once.

**DATEV source deduplication: Gewinn-und-Verlustrechnung + Kontennachweis overlap.**
Both files contain the same P&L data per entity. Extract entity signature from filename (first 3 underscore parts like `67858_323_2022`) and deduplicate by (year, key, entity_sig) to avoid doubling.

**DB stores costs (cogs, personnel, opex) as POSITIVE values.**
Computation must subtract them from revenue: `gross_margin = rev - cogs`, not `rev + cogs`. Display values negate for presentation.
