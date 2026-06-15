# Pipeline Learnings — Pre-Execution Checklist

Read at milestone start. Only non-obvious traps not visible from reading the code.

---

**`upsert_serienbriefe_record` has hardcoded column lists in both UPDATE and INSERT.**
Adding a column → update both branches. Forgetting the INSERT silently drops data.

**`_WRITEBACK_FIELDS` frozenset in dashboard.py is a security whitelist.**
Fields not listed are silently dropped on PATCH. Always add new editable fields here.

**`region` requires explicit population via region_lookup.py.**
ORBIS has no region column. Mapping is in source Excel sheet `Städte-Regionen-Matching` (709 rows: Stadt → Region Neu + Präposition). Region ≠ Bundesland — it's a curated marketing region for the letter sentence. Fixed in M17 for existing records, but new ingested records still need `normalize` or `enrich_regions` run.

**Source Excel sheets that matter:**
- `Serienbriefe` — 367 approached records, cols 22/23 = K1/K2
- `Städte-Regionen-Matching` — city → region + preposition (letter merge)
- `LLM_prep1` — 128 classified ground truth (few-shot examples)
- `Target_Overview` / `Tracker` — deal pipeline (Dealroom project, not ALLEX)
- `Komplimente Best Practices` — manually curated K1/K2 examples (not yet used)

**Any function that writes new DB columns must call `ensure_schema()` first.**
New columns exist in `_OUTREACH_COLUMNS` but the live DB doesn't get them until `ensure_schema()` is called. Functions that run standalone (like `enrich_regions`) must call it; don't assume it was called elsewhere.

**When fixing an open issue from a prior milestone, update that milestone's status in both PLAN.md and ROADMAP.md before committing.**

**`backfill-from-excel` SELECT query must include ALL fields in `_BACKFILL_FIELDS`.**
If you add a new field to `_BACKFILL_FIELDS`, the SELECT query must also include it. Otherwise `rec.get(field)` returns None and the backfill overwrites existing data. Bug found and fixed in M18.

**Legal entity substring detection needs word boundaries.**
`"kg" in name.lower()` matches "Wagner", "Spiegelberg". Use `re.search(r"\b(kg|ag)\b", ...)` instead.

**Before adding M{n} to ROADMAP or creating PLAN-M{n}.md: glob for existing PLAN-M{n}.md files first.**
Number collisions cause ROADMAP drift. Always run `Glob("ai/PLAN-M*.md")` before assigning a milestone number.

**DB column renames: after backfilling the new column, immediately NULL the old column.**
The rename pattern is: (1) add new column, (2) copy old→new via UPDATE, (3) NULL the old column.
Skipping step 3 leaves stale data that blocks future writes using COALESCE semantics (as happened with gf_name→owner_name).

**Patching a locally-imported function: patch at the source module, not the caller.**
`_build_html` does `from src.pipeline.region_lookup import load_region_mapping` inside the function body. Patch `src.pipeline.region_lookup.load_region_mapping`, not `src.pipeline.dashboard.load_region_mapping`. The local import re-looks up the name at call time.

**Impressum text must never be mixed into scraped_text.**
`scraped_text` feeds the classifier. Impressum is legal boilerplate (GF name, address, tax IDs). Storing them together pollutes classification signal. Always use `knowledge_base.documents` (doc_type="impressum") for impressum content.

**Address extraction technique stack — use in this order (fast→expensive):**
1. Standard URL suffixes: `impressum`, `impressum.html`, `impressum.php`, `de/impressum`
2. Homepage href scan: regex `href="...*impressum*..."` → follow deduped links. Case-sensitive paths are common (e.g. `Informationen/Impressum/` with capital I).
3. Sitemap discovery: `sitemap.xml` → `<loc>` matching "impressum"; also `sitemap.txt` and `robots.txt → Sitemap:`.
4. Contact/about pages: `/kontakt`, `/ueber-uns`, etc. — addresses often here too.
5. JSON-LD structured data: `extract_jsonld_address(html)` on homepage — `schema.org/PostalAddress` blocks are used by SEO-conscious SMEs and bypass blocked impressum pages.
6. Footer div extraction: `BeautifulSoup.find_all(['footer','div'], class_=re.compile('foot|contact|address'))` — many sites put address in `<footer>` (stripped by clean_html, so must query raw HTML).
7. Web search agent (Northdata, Handelsregister, business directories) — for completely blocked/down sites. Always verify: found company name must match `full_name` in pipeline.db before writing.

**Per-domain retry cap: max 3 distinct approaches before declaring manual.**
Don't count path variants (10 impressum variants = 1 approach). After 3 methods fail → manual review task.

**`_PLZ_CITY_RE` false positives on Handelsregister numbers.**
"HRB 99315 Umsatzsteuer-ID" → "99315" matches as PLZ, "Umsatzsteuer-ID" as city. Fixed by `city.lower().split('-')[0] in _NON_CITY_WORDS`. The hyphen suffix must be stripped before the non-city check.

**Handelsregister company name matching requires exact-name validation.**
LIKE-based lookups return nearest text match regardless of relevance — can return hotels for medtech domains. Always cross-check: extracted company name root should appear in domain name or industry must match. Reject mismatches rather than writing wrong data.
