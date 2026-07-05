# M34 — Briefvorbereitung Kompliment-Logik & Defaults

**Status:** ✅ Delivered (incrementally across M16–M32 sessions; verified 2026-06-29)
**Source:** FF feature request (UI-ISSUES.md, 2026-05-06)
**Scope:** Automate compliment generation logic and set field defaults for the letter preparation workflow.

---

## Overview

K1/K2 compliment generation already exists as a pipeline stage (`backfill-compliments` in `backfill.py`, prompt in `export.py:_COMPLIMENT_PROMPT_BASE`). Leistung/Mehrwerte generation also exists (`backfill-leistung`). However, the current prompts are generic — they don't enforce Flo's specific phrasing hierarchy or default values.

This milestone replaces the generic prompts with rule-based phrasing logic, adds about-page discovery for richer source data, and sets deterministic defaults for Leistung/Mehrwerte fields.

---

## 1. Kompliment 1 — Phrasing Hierarchy

Generate K1 by checking the company website (landing page or about section) in this priority order:

1. **Year of foundation found** → `"Ihre umfassende Erfahrung und Expertise, die Sie seit der Gründung im Jahr {YEAR} aufgebaut haben"`
2. **Duration of existence found** (e.g. "20 Jahren", "zwei Jahrzehnten") → `"Ihre umfassende Erfahrung und Expertise, die Sie in mehr als {DURATION} gesammelt haben"`
3. **Neither found** → `"die hohe Spezialisierung und Expertise im Bereich {SPECIALIZATION}"` — use the company's own wording for their specialization from the website. If no specific wording available, use a generic phrase for their product offering.

## 2. Kompliment 2 — Phrasing Hierarchy

Generate K2 by checking the company website in this priority order:

1. **Slogan found** → `"Ihr Leitbild mit den Schwerpunkten "{SLOGAN}" hat"` or `"Ihr starker Kundenfokus gemäß der Maxime "{SLOGAN}", hat"`
2. **Quantitative metric found** (customer count, product count, manufacturer count) → e.g. `"das breite und hochwertige Sortiment von mehr als {N} Produkten hat"` or `"die große Auswahl qualitativ hochwertiger Markenartikel von über {N} Herstellern hat"`
3. **Generic portfolio** → `"das breite Leistungsportfolio, von hochwertigen Geräten bis zum technischen Service, hat"` — replace "Geräte" and "technischen Service" with company-specific product categories if available. Alternative: `"das breite Sortiment, von hochwertigen Instrumenten bis zu Praxis- und Sprechstundenbedarf, hat"`
4. **Backup** → `"der starke Fokus auf hohe Qualität und zuverlässigen Service hat"`

## 3. About-Page Discovery

The pipeline must check these URL suffixes when looking for company information:

```
/ueber-uns, /ueberuns, /über-uns, /überuns, /unternehmen, /das-unternehmen,
/dasunternehmen, /mein-unternehmen, /meinunternehmen, /unser-unternehmen,
/mein-betrieb, /meinbetrieb, /wir-ueber-uns, /wirueberuns, /wer-wir-sind,
/das-sind-wir, /about, /aboutus, /about-us, /profile, /profil, /firma,
/meine-firma, /firmenprofil, /firmenportrait, /firmengeschichte,
/unternehmensgeschichte, /philosophie, /unsere-philosophie, /leitbild,
/portrait, /porträt, /historie, /geschichte, /unsere-geschichte, /team,
/unser-team, /das-team, /mein-team, /kompetenz, /kompetenzen, /wir, /uns,
/company, /company-profile, /mission, /vision, /leitidee
```

## 4. Mehrwerte — Conditional Phrasing

Depends on Leistung 1 value:
- If Leistung 1 = "Medizintechnik-Experten" → Mehrwerte: `"neuen Wachstumsinitiativen, der Digitalisierung und beim Qualitätsmanagement"`
- If Leistung 1 = "Medizinprodukt-Händler" → Mehrwerte: `"neuen Wachstumsinitiativen, bei der Digitalisierung, im Einkauf und der Logistik"`

## 5. Field Defaults

- **Leistung 1** default for every company: `"Experten für Medizinprodukte"`
- **Leistung 2** default for every company: `"Unternehmen im Bereich Medizintechnik & -produkte"`

---

## What already exists (do not rebuild)

- `backfill-compliments` CLI command (`backfill.py:440`) — two-pass: K1+K2 together, then K2-only retry
- `_generate_compliment_cli` (`export.py:211`) — Claude CLI subprocess, JSON output, umlaut restoration
- `_fill_missing_compliments` (`export.py:247`) — export-time safety net (BP4 source — 30% fail rate here)
- `backfill-leistung` CLI command (`backfill.py:278`) — AI-generates leistung_text, leistung_absatz_2, mehrwerte
- `compliment_guide.md` style guide loaded into prompt context

## What changed (delivered incrementally)

1. **`_COMPLIMENT_PROMPT_BASE` replaced** — `export.py:104-153` encodes the 3-tier K1 + 4-tier K2 cascades with Flo's exact template strings. `_K2_ONLY_PROMPT` in `backfill.py:409-438` mirrors the K2 cascade for pass-2 retries.
2. **About-page scraping added** — `fetch_about_page_text` in `web.py:335` checks 30+ URL suffixes (`_ABOUT_SUFFIXES`). Called during scrape pass, appended to `scraped_text` as `--- ABOUT PAGE ({suffix}) ---`.
3. **Deterministic defaults in `category_defaults.py`** — per-category `leistung_text`, `leistung_absatz_2`, and `mehrwerte` for all 6 category codes (DEA/INT/SER_PLA_1/SER_PLA_2/SER_MAI/SER_ITS). Applied at ingest via `apply_category_defaults()`.
4. **Export-time compliment generation removed** — `_fill_missing_compliments` is dead code (defined but never called). Export flow warns and tells user to run `backfill-compliments` first (export.py:434-445).
5. **`compliment_guide.md` updated (2026-06-29)** — Flo's verbatim cascade added as Section 0 ("MANDATORY") at the top. This file is loaded into the AI prompt as context via `_load_compliment_guide()`.

## Acceptance Criteria — Verification (2026-06-29)

- ✅ K1 generated using the 3-tier hierarchy; prompt encodes exact template strings
- ✅ K2 generated using the 4-tier hierarchy; prompt encodes exact template strings
- ✅ Leistung 1/2 pre-filled with defaults when empty (via `apply_category_defaults`)
- ✅ Mehrwerte auto-filled based on category (via `category_defaults.py`)
- ✅ About-page URLs checked during scrape pass (30+ suffixes in `_ABOUT_SUFFIXES`)
- ✅ All generated text uses proper German umlauts (umlaut restoration in `normalize.py`)
- ✅ `_fill_missing_compliments` dead — export warns on missing K1/K2 instead of silently generating
