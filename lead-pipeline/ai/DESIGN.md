# Design — Repuro Lead Classification & Targeting

---

## Lead Generation Sources

Sources ranked by priority. Primary is WLW scraper — run first.

### Primary — WLW.de Scraper (M2, automated)
| Source | Method | Est. leads |
|--------|--------|-----------|
| **wer-liefert-was.de** | Profile-driven scraper, search by `profile.discovery.wlw_search_terms` | 200–500 |

Search terms for medtech_germany profile: "Sprechstundenbedarf", "Medizintechnik", "Praxisbedarf", "Medizinischer Bedarf"

### Secondary — Existing Excel (M3, one-time input)
| Source | Content | Use |
|--------|---------|-----|
| `ORBIS_search` sheet | ~498 companies with NACE, revenue, MA, ownership | Ingest + re-classify |
| `MASTER_Cleaning` sheet | ~1,600 pre-ORBIS companies | Ingest + re-classify |
| `LLM_prep1` sheet | 128 pre-classified companies | Few-shot examples source |
| `Serienbriefe` sheet | 378 already-approached companies | Deduplication reference only |

The ~1,600 companies in MASTER_Cleaning and ORBIS should go through the full pipeline again for re-classification validation. The Serienbriefe list is only used for deduplication — never re-process those.

### Deferred — Additional Sources (future milestones)
- Gelbe Seiten: scrape categories "Medizintechnik", "Medizinischer Bedarf"
- OffeneRegister.de bulk download: filter Unternehmensgegenstand for target keywords
- Google Maps Places API: "Medizintechnik Service [Stadt]" across German cities

---

## What We Are Looking For

A Repuro platform/add-on target is a German privately-owned SME that:
1. **Distributes** medical supplies/devices to ambulatory practices (Arztpraxen — GP, Surgeon, OB-GYN, Dermatology). NOT hospital supply. NOT dental only.
2. **Services** those same practices: equipment maintenance, repair, hygiene management (RKI-compliant reprocessing), installation, or managed services. NOT purely logistics.
3. **SSB (Sprechstundenbedarf)** distribution is a strong positive signal — recurring revenue, high customer stickiness, authorized distributor status.
4. **Owner-operated** — GmbH or GmbH & Co. KG, founder or family still runs it. NOT a subsidiary of a large group.
5. **Size**: 20–80 employees for platform (A), 5–20 for add-on (B).

**Not wanted:**
- Dental-only (Zahnarzt supply)
- Pharmacy / Apotheke (NACE 4774)
- Hospital-only (Krankenhaus) supply
- Pure OEM / manufacturer
- IT/software for practices only
- Large group subsidiaries or PE-backed
- >100 employees

---

## Classification System (Klass. A/B/C/D/E/S)

### A — Platform Candidate
**Criteria (all required):**
- Service component: maintenance, hygiene, installation, or managed service
- Distribution: medical supplies/devices to ambulatory practices
- Size: 20–80 employees (or unknown but website suggests medium scale)
- Private ownership signals: independent GmbH, no obvious group parent
- SSB signal preferred but not required
- **Services Score**: 70–100
- **Action**: High priority for outreach. Personalized compliment.

### B — Add-on Candidate
**Criteria:**
- Service OR distribution present (not necessarily both equally strong)
- Size: 5–20, OR 20–80 but weaker service component
- Private ownership likely
- **Services Score**: 20–60
- **Action**: Include in outreach batch. Standard personalization.

### C — Unclear / Manual Review
**Criteria:**
- Website text vague, minimal, or doesn't load
- Business model partially ambulatory but unclear split
- Interesting signals but not enough data
- **Action**: Flag for manual review in dashboard. Do not auto-export.

### D — Clear No-Fit (Content)
**Criteria (any one sufficient):**
- Dental-only
- Pharmacy / Apotheke
- Hospital supply without ambulatory component
- Pure OEM / manufacturer
- >100 employees
- Insolvent / dissolved
- Wrong sector entirely
- **Action**: Exclude from Serienbriefe. Log reason. No manual review needed.

### E — Special Case
**Criteria:**
- Does not fit standard A/B BUT has something unusual worth tracking
- Could be a competitor, or platform in a different niche
- **Action**: Keep in dashboard. Do not add to outreach. Review quarterly.

### S — Subsidiary / PE-Backed (Ownership Gate)
**Criteria:**
- Confirmed corporate parent owns ≥75% (blocklist match → `is_subsidiary=True`)
- Confirmed PE fund ownership (`is_pe_backed=True`)
- Unknown owner holds ≥75% with no ownership type confirmed (conservative flag)
- **Set by**: M8 ownership gate, NOT by AI classifier
- **Action**: Do NOT export to Serienbriefe. Surface in dashboard for manual review.
  Roman verifies before final exclusion — could be MBO candidate, spin-off, or misclassification.
  Reclassify to A/B/C if ownership turns out to be private, or confirm exclusion.

---

## Hard Pre-Qualification Filters (M4)

Run BEFORE website scraping. Zero API cost.

| Filter | Rule | Source field |
|--------|------|-------------|
| Already approached | `domain in serienbriefe_domains` | Serienbriefe sheet |
| Too large | `ma_count > profile.filters.ma_max (100)` | ORBIS MA field |
| Too small | `ma_count < profile.filters.ma_min (5)` | ORBIS MA field |
| Pharmacy | `nace_code in profile.filters.nace_exclude` | NACE field |
| Dental signals | company name contains keyword from `profile.filters.name_exclude_keywords` | Full name |
| Foreign | Country != DE | Address field |

**MA Unknown**: Do NOT filter out. ~85% of records have no MA data. These go to scrape → classify.

---

## Ownership Hard Gate (M8)

Runs AFTER OpenRegister.de enrichment. **Critical — this is a reclassification, not a filter.**

| Condition | Action | Reason logged |
|-----------|--------|--------------|
| Corporate entity owns >75% of shares | Set `klass = "S"`, `reclassify_reason = "subsidiary — confirmed corporate parent"` | Acquirable only with group consent |
| PE / financial investor confirmed as majority shareholder | Set `klass = "S"`, `reclassify_reason = "PE-backed — confirmed fund ownership"` | Not a fit for partnership approach |
| Unknown owner holds ≥75%, ownership type unconfirmed | Set `klass = "S"` (conservative) | Manual review required |
| Natural person confirmed as owner | Always passes regardless of share % | Private ownership = target fit |
| No ownership data available | Proceed to export | Unknown is acceptable — discover in conversation |

**Owner age is NOT a hard gate.** Surface in dashboard as a soft signal. Roman decides.

**Credit discipline**: OpenRegister.de costs credits. Only enrich A/B companies. No credits on C/D/E.

---

## AI Classification Prompt Design

### Pre-Filter 1 — Keyword auto-D (free, zero Claude tokens)

Before any Claude call, `_is_obvious_d()` in `classify.py` checks scraped text + company name for keywords that indicate obviously non-medtech companies (Handwerk, Solar, Maler, coaching, furniture, etc.). These are auto-classified D with `reason_code=Handwerk` or `Unpassende_Branche`. No API call made.

This is intentionally narrow — only add keywords where false-positive risk is essentially zero.

### Pre-Filter 2 — Name-based duplicate detection (free, zero Claude tokens)

After the keyword pre-filter, `_normalize_company_name()` strips legal form suffixes (GmbH, AG, GmbH & Co. KG, etc.) and punctuation from the company name to produce a normalized key. Before each Claude call, the key is checked against an in-memory index of all already-classified companies built at the start of the classify run.

If a match is found (same company appearing under a different domain or from a different source), the existing klass is copied without any Claude call. The reasoning field is set to `"Duplicate name: same company as {domain} (klass {klass})"`.

Rules:
- Minimum key length 4 chars (guards against very short names creating false positives)
- Index built once per classify run from all `klass IS NOT NULL` records
- New classifications added to the index within the run (handles batches where dupe appears in same run)
- Logged as `NAME-DUPE` in verbose output; counted separately in the summary line

### Token Efficiency Rules
- **Primary backend**: `claude` CLI subprocess (`--via-cli` flag) — uses Claude Code OAuth, no API key needed
- **Fallback**: `claude-haiku-4-5` API for bulk, `claude-sonnet-4-6` with `--quality` flag
- Scraped text truncated to 2,000 chars
- Select 4 few-shot examples per call: 2×A, 1×B, 1×D
- Output capped at 200 tokens (structured JSON only)
- **No `compliment_draft` in classify step** — generated at export stage only for A/B companies that pass all gates

### Reason Codes (structured, token-efficient)

Instead of prose reasoning, classifier returns one `reason_code` from a fixed list + max 1 sentence:

| Code | When to use |
|------|-------------|
| `Passt` | A/B/C — fits criteria |
| `Unpassende_Branche` | Completely wrong sector |
| `Handwerk` | Tradesperson / installer |
| `Dental` | Dental-only |
| `Apotheke` | Pharmacy |
| `Krankenhaus` | Hospital / inpatient only |
| `OEM_Hersteller` | Manufacturer, not distributor/service |
| `Zu_Gross` | >100 employees |
| `Zu_Klein` | <5 employees |
| `Ausland` | Outside DACH |
| `Tochtergesellschaft` | Confirmed subsidiary |
| `Kein_Service` | Pure distribution, no service component |
| `PE_backed` | PE-owned |
| `Unklares_Profil` | Can't determine from available text |

### Classifier receives
1. Company name + domain
2. City + region
3. Employee count (if known) or "unknown"
4. Scraped website text (≤2,000 chars)
5. `profile.classification.target_description`
6. 4 few-shot examples from `profile.classification.examples`
7. Full reason code list

### Output schema (JSON only, max 200 tokens)
```json
{
  "klass": "A|B|C|D|E",
  "services_score": 0-100,
  "service_flag": true|false,
  "distributor_flag": true|false,
  "ssb_flag": true|false,
  "leistung_text": "2-4 German words describing main service",
  "reason_code": "one code from the list above",
  "reasoning": "max 1 sentence explaining the classification"
}
```

### DB field mapping
- `reclassify_reason` column stores `reason_code` (reused — no schema change needed)
- `reasoning` column stores the 1-sentence reasoning
- `compliment_draft` column written only at export stage

### Few-Shot Example Selection
For each call: 2×A, 1×B, 1×D (random from pool). Skip C unless target has very minimal text.

### Updating examples.json
**Not yet implemented.** Design intent: when Roman reclassifies a company in the dashboard (C→A, B→D, etc.), auto-append that company + reasoning to `profile.classification.examples` as new ground truth. Currently examples are static — dashboard reclassifications don't feed back.

### A/B Double-Check (quality gate)
**Deferred.** Design intent: re-run all A/B companies with a second independent Claude call; flag disagreements for manual review. Not implemented due to token cost. Manual C-review covers the gap partially.

---

## Serienbriefe Column Mapping

Output: 36-column Excel schema derived from the actual Word mail merge template
(`251111_Repuro_MedTech_Brief_Updated_vF.docx`). The 19 Word merge field codes are
mapped to Excel column headers as: spaces -> `_`, `(` -> `_`, `)` dropped, `+` -> `_`.

### Group 1 - Identity & pipeline analytics (9 cols)

| Excel column | Source field | Notes |
|---|---|---|
| Domain Name Clean | `domain` | |
| Source | `source` | WLW / ORBIS |
| Category | `klass` | A/B/C/D/E/S |
| Priority | `klass` | "Prio 1" if A or B, else blank |
| MA | `ma_count` | |
| Owner Age | `gesellschafter_age` | |
| Services Score | `services_score` | |
| SSB | `ssb_flag` | "ja" if flag set, else blank |
| HR-Nummer | `hrb_number` | |

### Group 2 - Word mail merge fields (19 cols, from Word template)

| Excel column | Word field code | Source field |
|---|---|---|
| Name Briefkopf | `Name_Briefkopf` | `full_name` |
| Name Titel | `Name_Titel` | blank |
| Name Absatz 1 | `Name_Absatz_1` | `gf_name` or `full_name` |
| Name Absatz 3 | `Name_Absatz_3` | blank |
| First Name (1) | `First_Name_1` | parsed from `gf_name` |
| Last Name (1) | `Last_Name_1` | parsed from `gf_name` |
| Gesellschafter | `Gesellschafter` | `gesellschafter_name` |
| Anrede | `Anrede` | `anrede` ("Herr" / "Frau") |
| Salutation | `Salutation` | `salutation` |
| Street Address | `Street_Address` | `street` |
| PLZ + Stadt | `PLZ__Stadt` | `plz_ort` |
| Region | `Region` | `region` |
| Leistung Absatz 1 | `Leistung_Absatz_1` | `leistung_text` |
| Leistung Absatz 2 | `Leistung_Absatz_2` | `leistung_absatz_2` (AI-classified or Excel backfill) |
| Mehrwerte | `Mehrwerte` | `mehrwerte` (AI-generated or Excel backfill) |
| Kompliment 1 | `Kompliment_1` | `compliment_draft` (AI-generated or Excel backfill) |
| Kompliment 2 | `Kompliment_2` | `compliment_2` (AI-generated or Excel backfill) |
| Verantwortlich | `Verantwortlich` | blank (filled manually) |
| Zweiter | `Zweiter` | blank (filled manually) |

### Group 3 - Contact (2 cols)

| Excel column | Source field |
|---|---|
| Email | `gf_email` |
| Tel | `gf_phone` |

### Group 4 - Post-sendout outreach tracking (6 cols)

Populated from outreach tracking columns in `pipeline.db` (added in M10 migration).
All blank on first export; filled manually or via future dashboard write-back.

| Excel column | DB column | Values |
|---|---|---|
| Datum Sent | `outreach_sent_at` | ISO date |
| Status | `outreach_status` | new / sent / replied / meeting / declined / closed |
| Comment | `outreach_comment` | free text |
| Follow-Up 1 | `followup1_at` | ISO date |
| Follow-Up 2 | `followup2_at` | ISO date |
| Follow-Up Comment | `followup_comment` | free text |
---

## Dashboard Design (v2 — M28/M29, two-mode navigation)

### Serving modes

- **Server (default)** (`python pipeline.py dashboard --serve [--port 8080]`): stdlib HTTP server on localhost:8080. Real-time data + write-back API.
- **Static** (`python pipeline.py dashboard`): writes `data/output/dashboard_{date}.html` with all data embedded as JSON. Read-only. Activity Log tab shows static fallback.
- **v1 rollback** (`python pipeline.py dashboard --v1`): serves the pre-M28 5-tab layout for emergency rollback.

### REST endpoints (server mode only)

- `GET /api/data` — all pipeline data as JSON (includes `required_fields`, `dropoff`, `briefaktion_counts`)
- `PATCH /api/company/{domain}?actor=<name>` — update record fields (whitelisted via `_WRITEBACK_FIELDS` frozenset)
- `PATCH /api/batch?actor=<name>` — bulk update multiple records
- `POST /api/compliment/{domain}?actor=<name>` — regenerate K1/K2 via Claude CLI
- `POST /api/ingest-domain` — add new domain via dialog
- `POST /api/export-pdf` — generate + download PDF as blob
- `POST /api/re-enrich/{domain}` — re-run enrichment pipeline for a record
- `POST /api/resolve-parent/{domain}` — UBO resolution (runs `_resolve_ubo` waterfall)
- `GET /api/activity?limit=N&actor=<name>` — activity log entries (stub — returns empty list until M27)

### Navigation architecture

Two modes accessible via sidebar:

**Review mode** (letter preparation workflow):
1. **BA-Prep** — per-record editor with queue sidebar (filter chips: Fehlend/Prüfen/Gesellschafter), "Was fehlt" checklist (4 groups: Ansprache/Adresse/Brieftext/Email), unified ownership block with Resolve/Pass/Exclude, letter preview, website iframe. `isExportEligible()` gate requires all fields filled + approval.
2. **Lead-Liste** — full sortable/filterable tabular view of all records, inline editing, BA-filter toggle.
3. **Drop-off** — per-stage pipeline attrition (Ingest → Filter → Scrape → Classify → Ownership → Approval) with reason buckets.
4. **Änderungslog** — activity feed with actor filter chips (Alle/Claude/manuell). Requires M27 backend.

**Auswertung mode** (analytics — placeholders, implementation in M30):
1. **Funnel** — pipeline stage visualization
2. **Cohorts** — per-Briefaktion sent/reply/meeting/deal metrics
3. **Klassen** — A/B/C/D/E/S distribution
4. **Bottlenecks** — current pipeline blockers

### Design system

- CSS custom properties: `--spar: #0891B2` (teal) as primary accent, warm neutral palette
- Typography: Inter font, 3 sizes (13px body, 11px meta, 22px+ numbers), 3 colors (--ink/--ink-2/--ink-3)
- Single teal subnav bar (M29): logo + tabs + BA selector + live badge
- Sidebar: mode buttons (Review/Auswertung) + actor identity (RD/FF via localStorage)
- Actor identity: `localStorage.getItem('allex_actor')` appended as `?actor=` to all PATCH/POST requests

### Data flow

`_load_data(db_path)` → JSON includes `records`, `required_fields`, `dropoff`, `briefaktion_counts`, `funnel`, `klass_counts`. Injected into HTML template via `__DATA_JSON__` placeholder at build time. In serve mode, live-refreshed via `fetch('/api/data')` every 30s.

### v1 Dashboard (legacy, accessible via --v1)

5-tab layout: Performance | BA Prep | Requires Attention | Lead Table | Outreach Tracker. File: `src/pipeline/templates/dashboard_v1.html`.

Dashboard reads directly from pipeline.db — no CSV staging files.
