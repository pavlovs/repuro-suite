# Charge 9 — UI-Issue Prep List
*Generated 2026-06-01 — reviewed against `ai/UI-ISSUES.md` (open items only).*

**Numbering caveat (surface, don't silently resolve):** UI-ISSUES.md treats BA9 as already run (RD pipeline bugs are tagged "BA9 retro — prevent recurrence in BA10"), while project memory records "BA1-8 + testbatch". If "Charge 9" = the next send batch, the 6 enrichment bugs below are the must-fix-before-send items; if it = a retro on BA9, they are the carry-forward fixes for the following batch. Either way the list is the same — confirm which batch number this maps to.

Scope rule applied: only records carrying a briefaktion belong in a charge QA pass (per QA-scope rule), not broader filters.

---

## A. Blockers — must fix + audit before any letters go out
These produce visibly wrong letters. A bad street address or wrong region in an outreach letter is a hard credibility fail.

| # | Item | Source | Action for charge 9 |
|---|------|--------|---------------------|
| A1 | `Straße` draft contains a managing director's **name** (EHP Hygieneprodukte GmbH — "also happened with other companies") | FF Bug-fixes | Systemic Straße-parsing bug. Fix parser, then **audit every charge-9 record's Straße** for stray GF names. |
| A2 | `Straße` draft contains a **website address** (Reinert & Bläsius → "reinert-blaesius.de") | FF Bug-fixes | Same Straße-parsing root cause. Audit all charge-9 Straße values for URLs. |
| A3 | **Region wrong** — Dermacom GmbH tagged "Franken"; Heilbronn is Baden-Württemberg | FF Bug-fixes | Region mapping error → wrong regional framing. Re-validate region for **all charge-9 records**, not just Dermacom. |
| A4 | **Brief-Vorschau not auto-updating** Geschäftsführer / Name Absatz 1 / Name Absatz 3 | FF Bug-fixes | This is the approval surface. Stale preview = risk of approving wrong names. Fix before review of charge 9 begins. |

## B. High — enrichment/pipeline correctness (the 6 BA9-retro bugs)
Determine data completeness and accuracy for a fresh batch. If charge 9 is a new send, deploy + re-enrich first; if a retro, schedule for next batch.

| # | Item | Scope | Action for charge 9 |
|---|------|-------|---------------------|
| B0 | **v2.0.4 enrich upgrade** — deploy `c870164` (multi-word `_name_matches_query` + HRB-first waterfall), then re-enrich BA8 records without HRB | `enrich.py` (on dev) | Gate for B1-B6 to take effect. Deploy before re-enriching charge 9. |
| B1 | MANUAL import: `full_name = domain` → OpenRegister can't search → enrichment misses | `ingest.py` / pre-enrich | Extract legal name from impressum/website before enrichment. |
| B2 | Scraped text truncated at 2500 chars → impressum address/GF/HRB cut off | `scrape.py` | Raise limit or store `impressum_text` separately. |
| B3 | `_MALE_NAMES` incomplete → `anrede=NULL` for natural-person owners | `enrich.py` | Expand against German first-name frequency list (8 added, more will surface). |
| B4 | Impressum address not extracted for records without KB entry | `normalize.py` | Add live impressum fetch fallback when KB has no entry. |
| B5 | No Austrian/non-DE company filter (e.g. bemed.com, Gleisdorf AT) | `enrich.py` / `normalize.py` | Flag non-DE PLZ/TLD as `ownership_reason='non-DE company'`. |
| B6 | OpenRegister autocomplete address discarded (available at 1 credit) | `enrich.py` `_openregister_autocomplete()` | Parse + store `registered_address` from autocomplete result. |

## C. Medium — review-efficiency / UX (not send-blockers)
| # | Item | Source |
|---|------|--------|
| C1 | Website preview fails to load: Habys GmbH, wibu.care, Pielmeier Medizintechnik GmbH, Grosspietsch GmbH, CB-MED Planung GmbH | FF Bug-fixes |
| C2 | Website preview should default to **Impressum** (not landing page) | FF Features |
| C3 | Briefvorbereitung: move Ansprechpartner (Brief), Anrede, Salutation into "Stammdaten" | FF Features |
| C4 | No grammar/quality check on export (full assembled Serienbrief text → Claude CLI validation) — needs spec session | RD Features |
| C5 | Co-Med filter — scraping flag 1/0 if company is a Co-Med partner | RD Features |
| C6 | Legend (clickable/collapsible) for field meanings, colour codes, workflow steps | RD Features |
| C7 | Undo button in review pane (last field change) — requires M27 activity log | RD Features |
| C8 | Company unique identifier (computed incremental ref for Lead-Liste / Briefmarken) | RD Features |

---

## Recommended charge-9 sequence
1. **Fix A1-A4** (letter-correctness blockers) → re-render previews.
2. **Deploy B0**, then run B1-B6 fixes or at minimum re-enrich charge-9 records against the stricter logic.
3. **Audit pass** on charge-9 queue records: Straße (no names/URLs), Region, GF/Name fields in Brief-Vorschau.
4. C-items are backlog — none block the send.

**Open items flagged:** 4 blockers (A1-A4), 7 high (B0-B6), 8 medium (C1-C8). All FF + RD bug-fixes are accounted for; FF reference note (line 24) and resolved/[x] items excluded.
