# Architecture — Repuro Lead Generation Pipeline

## System Overview

Industry-agnostic lead generation engine. All behavior is driven by a **profile JSON file** that defines the search terms, filter rules, classification criteria, and export format for a given industry/client. The same pipeline code handles any industry.

Linear pipeline: each stage reads from and writes to `data/pipeline.db` (SQLite). Final output goes to `data/output/`. Pipeline state is tracked via `pipeline_stage` column — every command is idempotent and skips already-processed records. Expensive fetches (web scraping, ownership API calls) are cached in a separate **SQLite knowledge base** so they are never repeated.

```
INDUSTRY PROFILE (config)
    profiles/medtech_germany.json       ← drives all pipeline behavior
    profiles/[future_industry].json

    Profile optionally defines supplementary_sources (profile-specific legacy data):
      type: "excel_sheets"
      path: "data/input/260319_Repuro_Medtech_Targets_v3_claude.xlsx"
      ingest_sheets: ["ORBIS_search", "MASTER_Cleaning"]
      dedup_sheets: ["Serienbriefe", "Grande follow-up"]   ← already-approached

KNOWLEDGE BASE (persistent cache)
    data/knowledge_base.db              ← SQLite, never deleted between runs
    Tables: domain_cache, ownership_cache, documents
    → Before any HTTP/API call: check cache first
    → After any HTTP/API call: write result to cache
    → Benefit: scrape once, classify free; never pay OpenRegister twice for same domain

         │
         ▼
    [M2] DISCOVERY SCRAPER
    src/pipeline/wlw_scraper.py
    → Scrapes wer-liefert-was.de with profile.discovery.wlw_search_terms
    → Checks knowledge_base domain_cache before fetching
    → Extracts: name, domain, city, region, phone, description
    → Future sources: Gelbe Seiten, OffeneRegister bulk, Google Maps Places
    → Writes: data/staging/00_discovered.csv

         │
         ▼
    [M3] INGEST (normalize + dedup)
    src/pipeline/ingest.py
    → Loads 00_discovered.csv
    → If profile has supplementary_sources: loads those too
      (medtech: ORBIS_search header=row0, MASTER_Cleaning header=row7)
      ORBIS note: multiple rows per company (merged cells) — dedup by domain col
      ORBIS note: already contains GF birthday (Excel serial), ownership %, CSH data
    → Deduplicates against profile.supplementary_sources.dedup_sheets
      (medtech: Serienbriefe + Grande follow-up = 454 already-approached domains)
    → Normalizes all to CompanyRecord schema
    → Städte-Regionen-Matching sheet (708 cities) loaded for city→region lookup
    → Writes: pipeline.db (pipeline_stage='ingested')

         │
         ▼
    [M4] FILTER (pre-qualification)
    src/pipeline/filter.py
    → Applies profile.filters: dental keywords, NACE exclusions, size bounds, foreign
    → Tags: filter_pass=True/False + filter_reason
    → Writes: pipeline.db (pipeline_stage='filtered')

         │
         ▼
    [M5] SCRAPE
    src/pipeline/scrape.py
    → For each domain: check knowledge_base.domain_cache first (TTL: 90 days)
    → Cache hit → use stored text, no HTTP call
    → Cache miss → fetch homepage + /leistungen + /service + /produkte + /ueber-uns
    → Stores result in knowledge_base.domain_cache
    → Writes scraped_text to pipeline.db (no staging CSV)
    → Also fetches /impressum (M21): stored in knowledge_base.documents (doc_type="impressum")
      Impressum is stored SEPARATELY from scraped_text — never mixed into classification input

         │
         ▼
    [M6] CLASSIFY (AI)
    src/pipeline/classify.py
    → Pre-filter 1 (free): _is_obvious_d() keyword check → auto-D, no Claude call
    → Pre-filter 2 (free): _normalize_company_name() + name index → copy klass from
      already-classified company with same name (different domain/source) → no Claude call
    → Remaining: Claude CLI subprocess (--via-cli, OAuth) or claude-haiku-4-5 API
    → Few-shot examples from profile.classification.examples (2×A, 1×B, 1×D)
    → Output: klass, services_score, ssb_flag, service_flag, distributor_flag,
              leistung_text, reason_code, reasoning
    → Writes result to pipeline.db (pipeline_stage → 'classified')

         │
         ▼
    [M7] ENRICH — Ownership (A/B only)
    src/pipeline/enrich.py
    → CRITICAL: Only called for klass A or B. Never C/D/E. Never realtime=true.
    → Step 0 (free): ORBIS data already in DB (gesellschafter_share_pct not null) — skip API
    → Step 1 (free): OffeneRegister SQL API (db.offeneregister.de)
      → GF name lookup by HRB number — data from 2019, GF name only (no ownership %)
    → Step 2 (paid): OpenRegister.de REST API — 11 credits per company
      → Call 1: GET /v1/autocomplete/company?query={full_name} → 1 credit → company_id
        Match: prefer HRB match, else first active GmbH/UG/AG/KG result
      → Call 2: GET /v1/company/{company_id}/owners → 10 credits → shareholders
        Never use realtime=true (costs extra 10 credits, not needed)
      → Check knowledge_base.ownership_cache first (never pay twice for same domain)
    → Autocomplete waterfall (main targets — has domain, scraped text, impressum):
      W1. full_name as-is
      W2. core name (legal form stripped)
      W3. HRB extracted from scraped text or impressum → retry W1+W2 with HRB filter
      W4. query by HRB number alone
    → Name validation gate: reject autocomplete results where company name doesn't match query
      (prevents false matches, e.g. "Clavaro" returning "DiBuMa Invest GmbH")
    → HRB cross-verification: compare website HRB with OpenRegister company_id register_number
    → Impressum fallback: extract owner/GF from /impressum when API returns no owners (404)
    → UBO resolution for corporate parent owners (_resolve_ubo):
      W1. full holding name as-is
      W2. hyphen/space variant (toggle hyphens↔spaces in compound core)
      W3. core name only (legal form stripped)
      Then: if _parse_owners returns legal entity majority (self-reference, holdco), fallback
      scans raw owners list for largest natural person (handles dispersed ownership)
    → Stage outcomes:
      ownership_enriched      — natural person owner confirmed, OR blocklist-confirmed subsidiary
      ownership_review_needed — legal person owner not on blocklist, or no OpenRegister match
    → Corporate owners blocklist: src/config/corporate_owners_blocklist.json
      Legal person majority owner not on blocklist → manual review, NOT auto-blocked
    → Dashboard Resolve Parent flow:
      POST /api/resolve-parent/{domain} with {"parent_name": "..."} → runs _resolve_ubo
      On success: writes UBO name to record, advances to ownership_enriched
      On failure: returns tried_queries list; UI shows editable field for manual name correction
    → Data completeness on review paths:
      ORBIS corporate-owner unresolved path: writes all_gesellschafter JSON with at least
      the ORBIS owner snapshot (name, type=legal_person, pct) — ensures Investigation column
      is never empty for these records
      OpenRegister no-match path: ownership_reason includes searched company name
      (e.g. "no match for 'AIVIMED GmbH'") for traceability

         │
         ▼
    [M8] OWNERSHIP HARD GATE
    src/pipeline/enrich.py (apply_ownership_gate)
    → Processes pipeline_stage='ownership_enriched' only
    → Skips 'ownership_review_needed' — manual review required first
    → is_subsidiary=True → klass=S, reason="subsidiary — confirmed corporate parent"
    → is_pe_backed=True → klass=S, reason="PE-backed — confirmed fund ownership"
    → is_subsidiary=NULL AND share_pct >= 75% → klass=S (conservative: unknown owner, high %)
    → is_subsidiary=False (natural person confirmed) → always passes regardless of share_pct
    → klass=S NOT klass=D: S is ownership-excluded, D is content no-fit. Roman reviews S manually.
    → Passing records → pipeline_stage='ownership_gated'

         │
         ▼
    [M9] ENRICH — Email (A/B only)
    src/pipeline/enrich.py (enrich_email_batch)
    → Input: pipeline_stage IN ('ownership_gated', 'ownership_enriched', 'classified'),
             klass IN ('A','B'), gf_email IS NULL OR ''
    → SMTP candidate testing from owner name (gesellschafter_name) only
      Build 8 candidates: f.l@, f0.l@, l@, f@, fl@, f0l@, f.l0@, f0.l0@
      Umlaut normalisation before candidate generation (ä→ae, ö→oe, ü→ue, ß→ss)
      SMTP-verify each via DNS MX + RCPT TO port 25 (no API, no cost)
      Catch-all detection: multiple candidates pass → use first (f.l@), log flag
    → ⚠️ KNOWN ISSUE: SMTP port 25 blocked from residential IP (Spamhaus PBL).
      Email enrichment outsourced to freelancer via export list.
    → No impressum scraping — impressum only gives company emails (info@/gf@), not personal
    → If no candidate passes: gf_email=NULL, still advances to email_enriched
    → ⚠️ KNOWN ISSUE: Does NOT pick up 'ownership_review_needed' records — those are stuck
      until manually resolved in dashboard, and even then don't re-enter this stage.
    → owner_name enriched from gesellschafter_name if owner_name currently empty
    → anrede derived from owner first name (German name heuristic, ~85% accuracy)
    → salutation constructed: "Sehr geehrte[r] [Herr/Frau] [Nachname]"
    → ORBIS anrede never overwritten
    → Advances to pipeline_stage='email_enriched'

    [M21] ENRICH — GF from Impressum (A/B only, separate command)
    src/pipeline/enrich.py (enrich_gf_cmd)
    → Command: python pipeline.py enrich-gf [--dry-run] [--limit N]
    → Input: A/B records with already_approached=0 AND (gf_name IS NULL OR gf_name='')
    → Reads /impressum from knowledge_base.documents (doc_type="impressum")
    → Fetches /impressum if not in KB (same HTTP client, polite delay)
    → Regex extraction: Geschäftsführer/Inhaber/Vertreten-durch patterns → gf_name
    → Claude CLI fallback if regex finds nothing (impressum text as stdin)
    → Writes: gf_name, impressum_address (display-only), gf_email (only if currently empty)
    → gf_name is NOT auto-filled into owner_name — surfaced in dashboard for manual decision

         │
         ▼
    [M10] EXPORT → Serienbriefe
    src/pipeline/export.py
    → Generates compliments for A/B records without one (claude CLI via stdin)
    → Maps fields to 36-column schema derived from Word template
      (251111_Repuro_MedTech_Brief_Updated_vF.docx, 19 merge fields confirmed)
      Groups: identity/analytics (9) | Word merge fields (19) | contact (2) | outreach tracking (6)
    → "Region" column uses region_prep (letter form, e.g. "im Allgäu") not bare region name
    → --approved-only flag: only exports records with approved_for_sendout=1 (M17 gate)
    → Never exports: already_approached=True, klass=D/S, filter_pass=False, stage=ingested
    → Runs ensure_schema() to migrate outreach tracking cols if DB is older
    → Writes: data/output/serienbriefe_new_batch_YYYYMMDD.xlsx

         │
         ▼
    [M22] EXPORT → PDF Letters
    src/pipeline/export_pdf.py
    → Reads same records as Excel export via shared _fetch_exportable_records()
    → Parses letter_template.html (BeautifulSoup) into typed LetterBlocks
    → [M23] Completeness gate: check_record_completeness() on 10 REQUIRED_LETTER_FIELDS
      → Incomplete records skipped (not blocked), logged with specific missing fields
    → Pre-render overflow check: estimate_letter_height() → ERROR if any letter > 261mm
    → Renders with fpdf2 (RepuroLetterPDF subclass): logo + sender from sender.json
    → Font: Arial TTF from Windows system fonts (copied to data/fonts/ on first use)
    → One letter per A4 page, single output PDF
    → CLI: python pipeline.py export-pdf [--approved-only] [--dry-run]
    → Dashboard: POST /api/export-pdf → PDF blob download
    → Writes: data/output/serienbriefe_YYYYMMDD.pdf
    
    [M23] AI TEXT POST-PROCESSING (applied at all generation points)
    src/pipeline/normalize.py — restore_umlauts_german(), fix_compliment_text()
    → Umlaut restoration: ~80-word allowlist for common German words (Prüfung, Röntgen, für, etc.)
    → Compliment grammar: strip duplicate prefixes (Besonders/Auch), trailing periods, warn missing verb
    → Applied in: normalize_cmd() step 9b, export._parse_compliment_json(), backfill._parse_json_response()

         │
         ▼
    [M11–M29] DASHBOARD
    src/pipeline/dashboard.py + src/pipeline/templates/dashboard_v2.html
    → Server mode (--serve, default): stdlib HTTP server on localhost:8080
    → Static mode: self-contained HTML with embedded JSON
    → v1 rollback via --v1 flag (frozen 5-tab console)
    → REST endpoints: GET /api/data, PATCH /api/company/{domain}?actor=,
      POST /api/compliment/{domain}, POST /api/ingest-domain, POST /api/export-pdf,
      POST /api/re-enrich/{domain}, POST /api/resolve-parent/{domain},
      GET /api/activity (stub until M27)
    → _WRITEBACK_FIELDS frozenset is the security whitelist — fields not listed are silently
      dropped. Any new editable field MUST be added here.
    → v2 navigation: Review mode (BA-Prep, Lead-Liste, Drop-off, Aenderungslog) +
      Auswertung mode (Funnel, Cohorts, Klassen, Bottlenecks — placeholders until M30)
    → BA-Prep: per-record editor with queue sidebar, filter chips (Fehlend/Pruefen/
      Gesellschafter), "Was fehlt" checklist (4 groups), unified ownership block with
      Resolve/Pass/Exclude, letter preview, website iframe
    → Ownership review integrated into record editor (M28/M29):
      Unified block with status chip, owner chips, Resolve/Pass/Exclude buttons.
      isExportEligible() gate: all required fields filled + approved_for_sendout=1.
      Known limitation: all_gesellschafter stores direct shareholders only. UBO chain
      behind holdings stored in ownership_reason text, not structured field.
    → Writes: data/output/dashboard_{date}.html (static mode)
```

---

## HTTP Layer (`src/utils/web.py`)

`fetch_with_retry` and `extract_page_text` — all scraping goes through here.

**Key design decisions (as implemented):**

- **Persistent httpx clients**: Two module-level `httpx.Client` instances reuse TCP connections across multi-page scrapes of the same domain. `_client` (SSL verify on) tried first; `_client_noverify` (SSL verify off) used as fallback for broken/expired certs.
- **Split timeout**: `connect=6s, read=20s` — old Apache servers on German shared hosting (Strato, 1&1) connect fast but are slow to send response body. Flat `timeout=10` was causing false failures.
- **SSL partial chain**: `ssl.VERIFY_X509_PARTIAL_CHAIN` set on the SSL context (Python 3.10+) — resolves `"unable to get local issuer certificate"` errors common on German SME hosts with intermediate CAs.
- **DNS failure fast-exit**: Keywords like `"getaddrinfo"`, `"NXDOMAIN"` detected and treated as permanent failures — no retry, mark as `scrape_failed` immediately.
- **HTTPS-only**: Always tries `https://` — no HTTP fallback (irrelevant for business websites, adds complexity).
- **`extract_page_text(domain)`**: Fetches homepage + `/leistungen` + `/service` + `/produkte` + `/ueber-uns`. Combines and truncates to `max_chars=2500`. Returns empty string on total failure (no exception raised to caller).
- **`fetch_impressum_text(domain)`** (M21): Fetches `/impressum` (+ `.html`, `.php`, `/de/impressum` variants). Returns text or `""`. Stored in `knowledge_base.documents`, never in `scraped_text`.

---

## Knowledge Base (SQLite)

`data/knowledge_base.db` — persistent across all pipeline runs and profiles.

```sql
CREATE TABLE domain_cache (
    domain          TEXT PRIMARY KEY,
    scraped_text    TEXT,
    scraped_at      TIMESTAMP,
    http_status     INTEGER,
    source_urls     TEXT    -- JSON array of URLs fetched
);

CREATE TABLE ownership_cache (
    domain                  TEXT PRIMARY KEY,
    hrb_number              TEXT,
    gesellschafter_name     TEXT,
    gesellschafter_share_pct REAL,
    gesellschafter_age      INTEGER,
    is_subsidiary           INTEGER,    -- 0/1/NULL
    is_pe_backed            INTEGER,    -- 0/1/NULL
    gf_name                 TEXT,
    source                  TEXT,       -- "orbis"/"offeneregister"/"openregister"
    raw_response            TEXT,       -- full JSON for future re-parsing
    fetched_at              TIMESTAMP
);

CREATE TABLE documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT,
    hrb_number  TEXT,
    doc_type    TEXT,       -- "impressum", "handelsregister_excerpt"
    content     TEXT,
    fetched_at  TIMESTAMP
);
```

`src/utils/knowledge_base.py` wraps all DB access:
- `get_scraped_text(domain, max_age_days=90) -> Optional[str]`
- `save_scraped_text(domain, text, status, urls)`
- `get_ownership(domain) -> Optional[dict]`
- `save_ownership(domain, data, source)`
- `get_document(domain, doc_type) -> Optional[str]`
- `save_document(domain, hrb, doc_type, content)`

---

## Industry Profile Schema

```json
{
  "id": "medtech_germany",
  "name": "German Ambulatory Medtech Distributors",
  "geography": { "country": "DE" },
  "discovery": {
    "wlw_search_terms": ["Sprechstundenbedarf", "Medizintechnik", "Praxisbedarf", "Medizinischer Bedarf"],
    "wlw_base_url": "https://www.wer-liefert-was.de"
  },
  "supplementary_sources": [
    {
      "type": "excel_sheets",
      "path": "data/input/260319_Repuro_Medtech_Targets_v3_claude.xlsx",
      "ingest_sheets": ["ORBIS_search", "MASTER_Cleaning"],
      "dedup_sheets": ["Serienbriefe", "Grande follow-up"],
      "city_region_sheet": "Städte-Regionen-Matching"
    }
  ],
  "filters": {
    "ma_min": 5,
    "ma_max": 100,
    "nace_exclude": ["4774"],
    "name_exclude_keywords": ["zahn", "dental", "dent", "mund", "apotheke", "krankenhaus", "klinik"]
  },
  "classification": {
    "target_description": "...",
    "class_definitions": { "A": "...", "B": "...", "C": "...", "D": "...", "E": "..." },
    "examples": []
  },
  "ownership": {
    "hard_disqualify_subsidiary_threshold_pct": 75.0,
    "hard_disqualify_pe_backed": true
  },
  "export": {
    "format": "serienbriefe"
    // Note: region_prepositions loaded from city_region_sheet, not hardcoded here
  }
}
```

---

## Excel Sheet Reference (medtech_germany only)

These details are medtech-specific and only relevant for M3 ingest.

| Sheet | Header row | Key columns | Use |
|-------|-----------|-------------|-----|
| ORBIS_search | 0 | col1=domain, Unternehmensname, NACE, Postleitzahl, Ort, Anzahl der Mitarbeiter, GesellschafterName, Gesellschafter-Direkt%, DMNachname, DMGeburtstag (Excel serial) | Primary ingest source |
| MASTER_Cleaning | 7 | Domain Name Clean, Name Briefkopf, Street Address, PLZ+Ort, Stadt | Secondary ingest |
| LLM_prep1 | 2 | URL clean (domain), Full_name, Klass., MA, Services Score, Service, Leistung, Reasoning, Compl. 3 | Few-shot examples for classifier |
| Serienbriefe | 0 | Domain Name Clean | Dedup reference (378 rows) |
| Grande follow-up | 0 | Domain Name Clean | Dedup reference (76 rows) |
| Städte-Regionen-Matching | 0 | Stadt (col0), Region Neu (col1), Präposition (col2), Region mit Präp (col3) | 709-city region lookup — `region_lookup.py` reads this, maps city→(region, region_prep) |

---

## Core Data Model

`src/pipeline/models.py` — `CompanyRecord` dataclass. All sources normalize to this.

Key fields added vs original design:
- `orbis_ownership_source: bool` — True if ownership data came from ORBIS (no API call needed)
- `email_source: str` — "impressum_scrape" / "smtp_pattern" / "manual"

---

## Module Responsibilities

### `src/utils/knowledge_base.py` (new in M2)
- SQLite wrapper — all cached data access
- `KnowledgeBase` class, context manager, thread-safe writes

### `src/pipeline/wlw_scraper.py`
- `scrape_wlw(profile, kb, dry_run) -> list[CompanyRecord]`
- Uses `kb` (KnowledgeBase) for domain dedup check before fetching

### `src/pipeline/ingest.py`
- `load_discovered(path) -> list[CompanyRecord]`
- `load_orbis(path) -> list[CompanyRecord]` — handles merged cells, Excel serial dates
- `load_master_cleaning(path) -> list[CompanyRecord]` — header at row 7
- `deduplicate(records, dedup_domains) -> list[CompanyRecord]`
- `enrich_regions(dry_run) -> dict` — bulk-populate region + region_prep from Städte-Regionen-Matching

### `src/pipeline/region_lookup.py` (new in M17, updated M32)
- `load_region_mapping() -> dict[str, tuple[str, str]]` — lru_cache(1), reads `src/data/region_mapping.json` (486 cities, extracted from Excel once at M32 — no runtime Excel dependency)
- `lookup_region(city) -> tuple[str|None, str|None]` — city → (region, region_prep)

### `src/pipeline/enrich.py`
- `enrich_ownership_batch(profile, dry_run, limit, db_path, kb_path) -> int`
  - Step 0: use ORBIS data if gesellschafter_share_pct not null
  - Step 1: OffeneRegister free SQL API (GF name by HRB)
  - Step 2: OpenRegister.de paid API (A/B only, 11 credits, cache-first)
  - Outcomes: ownership_enriched / ownership_review_needed
- `apply_ownership_gate(profile, db_path) -> int` — M8 hard reclassification to klass=S
- `enrich_email_batch(profile, dry_run, limit, db_path, kb_path) -> int`
  - SMTP candidate testing from gesellschafter_name (8 patterns, umlaut-normalized)
  - No impressum scraping, no paid API
  - Also fills: owner_name, anrede, salutation
- `enrich_gf_cmd(args)` — M21: extract GF name from /impressum (regex + Claude CLI fallback)

### `src/pipeline/normalize.py` (new in M18)
- `title_case_german(text) -> str` — title-case with German legal form preservation (GmbH, KG, etc.)
- `restore_umlauts_city(text, lookup) -> str` — city umlaut restoration from Städte-Regionen-Matching
- `restore_umlauts_pattern(text) -> str` — conservative allowlist (straße, ärzte)
- `normalize_anrede(raw) -> str|None` — MR→Herr, MRS→Frau
- `clean_gesellschafter_name(name) -> str` — strip MR/MRS prefix, preserve DR., title-case
- `enrich_owner_name(owner_name, gesellschafter_name) -> str` — single-word owner_name → full name from gesellschafter
- `build_salutation(anrede, owner_name) -> str|None` — "Sehr geehrte[r] {Herr/Frau} {Nachname}"
- `parse_impressum_address(impressum_text) -> (street|None, plz_ort|None)` — regex extraction of street + PLZ+Stadt from impressum text
- `normalize_cmd(args)` — CLI handler: applies all normalizations to A/B non-serienbriefe records
    - Step 6b: gf_name fallback — only for lastname-only case (owner = single surname matching gf_name). Missing/corporate owner_name flagged for manual review, not auto-replaced.
    - Step 9a: impressum address fill — queries knowledge_base.db for impressum text, extracts street/PLZ+Ort into pipeline.db when fields are empty

### `src/pipeline/backfill.py` (new in M18)
- `backfill_from_excel_cmd(args)` — fill K1/K2/leistung/region from Serienbriefe Excel for matched records
- `backfill_leistung_cmd(args)` — AI-generate leistung fields via Claude CLI for records with scraped_text
- `backfill_compliments_cmd(args)` — AI-generate K1/K2 via Claude CLI, reuses export.py compliment logic

### `src/pipeline/export_pdf.py` (new in M22)
- `export_pdf_cmd(profile, dry_run, approved_only, db_path) -> Optional[Path]`
- `check_record_completeness(rec) -> list[str]` — M23 completeness gate (10 required fields)
- `estimate_letter_height(blocks) -> float` — overflow detection (max 261mm)
- Shares `_fetch_exportable_records()` with export.py

### `src/pipeline/check_letter.py` (new in M23)
- `check_letter_cmd(args)` — standalone letter quality validation
- Assembles full letter text before checking (not fragment-based)

### `src/pipeline/audit.py` (new in M12)
- `audit_dedup_cmd(args)` — cross-check DB vs Serienbriefe Excel, `--fix` mode

---

## Data Files

| File | Stage | Contents |
|------|-------|----------|
| `data/staging/00_wlw_raw.csv` | M2 | Raw WLW scraper output (input-only after ingest) — gitignored |
| `data/pipeline.db` | M3–M10 | Primary state store — all pipeline stages live here — gitignored |
| `data/knowledge_base.db` | persistent | HTTP cache (scraped text + ownership) — never deleted — gitignored |
| `data/output/serienbriefe_new_batch_{date}.xlsx` | M10 | Final export — only A/B, not already approached, not D |
| `data/output/serienbriefe_{date}.pdf` | M22 | PDF letters — one per page, all approved records |
| `src/config/sender.json` | M22 | Client branding: logo path, address lines, signatures, city |
| `src/data/region_mapping.json` | M32 | 486-city region lookup (extracted once from Excel) — committed, no runtime Excel dependency |

**No CSV staging files for M3–M10.** `pipeline.db` is the sole state store. `pipeline_stage` column tracks each record's position in the pipeline.

---

## Dashboard Template Architecture

### Template files

| Template | Purpose | Served when |
|----------|---------|-------------|
| `src/pipeline/templates/dashboard_v2.html` | v2 dashboard (default since M29) — sidebar nav, two-mode layout | Default (`python pipeline.py dashboard`) |
| `src/pipeline/templates/dashboard_v1.html` | v1 backup (5-tab console, frozen at M27) | `--v1` flag |
| `src/pipeline/templates/dashboard.html` | Original pre-fork file (kept for compatibility) | Never (legacy) |

Template selection: `_template_name()` in `dashboard.py` checks `_USE_V1` / `_USE_V2` module flags set by CLI args.

### Placeholder injection

Python reads the template and does string replacements at build time:

| Placeholder | Value |
|-------------|-------|
| `__DATA_JSON__` | JSON-serialised pipeline data (records, required_fields, dropoff, briefaktion_counts) |
| `__SERVE_MODE_JS__` | `true` / `false` for JavaScript |
| `__LIVE_BADGE__` | `LIVE` / `STATIC` header badge |
| `__DATE_STR__` | today's date (`YYYY-MM-DD`) |
| `__LOGO_IMG__` | `<img>` tag with base64 PNG, or empty string |
| `__REGION_MAPPING_JSON__` | JSON city-to-region lookup from Stadte-Regionen-Matching (M17) |
| `__LETTER_TEMPLATE__` | HTML letter template string for Brief-Vorschau rendering |
| `__HUBSPOT_PORTAL_ID__` | HubSpot portal ID (forward-compat) |

### v2 architecture (M28/M29)

- **Two modes**: Review (BA-Prep, Lead-Liste, Drop-off, Aenderungslog) and Auswertung (Funnel, Cohorts, Klassen, Bottlenecks — placeholders until M30)
- **Design system**: CSS custom properties, Inter font, teal accent (`--spar: #0891B2`), single teal subnav bar
- **Data flow**: `_load_data()` computes `required_fields` (from `check_letter.py`) and `dropoff` (per-stage pipeline attrition), injected via `__DATA_JSON__`. Live-refreshed via `fetch('/api/data')` in serve mode.
- **Actor identity**: `localStorage.getItem('allex_actor')` (roman/flo) appended as `?actor=` to all PATCH/POST requests
- **Filter chips**: BA-Prep queue sidebar uses Fehlend/Pruefen/Gesellschafter filter chips (replaced sort chips in M28)

**Design rules for future dashboard work:**
1. New views in v2 only. v1 is frozen. Edit `dashboard_v2.html` for all UI changes.
2. New data fields: add to `_load_data()` in `dashboard.py`, reference in template.
3. `--serve` is the primary mode. Design all new views assuming `fetch('/api/data')` is available.
4. Static mode kept for one-off HTML snapshots but is secondary to serve mode.

---

## Key Invariants

- `id = hashlib.md5(domain.encode()).hexdigest()[:12]` — stable across runs
- `already_approached = True` → never export
- `filter_pass = False` → never scrape/classify
- `klass = D` → never export (content no-fit)
- `klass = S` → never export (ownership-gated: confirmed subsidiary or PE-backed)
- `ownership_pass = None` → proceed to export
- Knowledge base is append-only — never delete cached entries, just check TTL on read
- Master Excel is NEVER modified
- All API-touching commands support `--dry-run`
- All output files are dated (e.g. `serienbriefe_new_batch_{date}.xlsx`, `dashboard_{date}.html`)
- Compliment prompts passed via stdin to claude CLI (not as CLI arg) — avoids Windows shell issues with `&`, `+`, newlines in German company names
