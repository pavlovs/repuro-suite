# SPEC-DR-COMMERCIAL -- Commercial Data Extraction Specification

Engineering spec for the **commercial data** intake pipeline. Defines how customer lists, product breakdowns, backlog, employee registers, and supplier data are read, classified, mapped, and stored in `deal_customers`, `deal_products` (NEW), `deal_backlog`, `deal_employees`, `deal_suppliers`, and derived KPIs in `deal_commercial`. This is the onepager/scorecard's upstream dependency for all non-financial metrics.

**Scope boundary:** This spec covers ONLY structured commercial data extraction from Excel/CSV files to normalized DB tables. It does NOT cover: financial data (DR-READER), qualitative data from emails/Granola/RFI responses (DR-GATHER), or model population (DR-MODEL). Same read-classify-normalize-store principle as DR-READER, but with an AI classification layer because commercial file structures vary wildly per deal.

**Core difference from DR-READER:** Financial data has known structures (SUSA = account + saldo, BWA = 20 summary lines). Commercial data has NO standard format. A customer list from Cat looks nothing like one from Octopus. The LLM layer bridges this gap by classifying file type and proposing column-to-schema mappings. Human confirms before bulk load.

**Core principle:** Extract once, store persistently, derive KPIs. Every extracted row links back to its source file. Re-extraction is idempotent. Entity resolution across years uses LLM-assisted fuzzy matching. Roman reviews before data flows downstream.

**Status:** Draft -- pending Roman confirmation.
**Owner:** Roman (source data quality + review gate), Claude (extraction logic + AI mapping + storage).
**Last updated:** 2026-05-20.

**Upstream:** `ingest.py` scans deal folders and registers files in `deal_documents` with `doc_type='commercial_raw'` and subtypes (`customer_list`, `product_split`, `backlog`, `employee_list`, `supplier_list`). DR-COMMERCIAL picks up from there.

**Downstream:** `deal_customers` + `deal_products` + `deal_backlog` + `deal_employees` + `deal_suppliers` feed into SPEC-ONEPAGER (customer concentration, product mix, headcount), SPEC-OFFER (commercial context), deal scorecard, dashboard commercial tab, IC document, and valuation logic (concentration risk, key person dependency). Derived KPIs stored in `deal_commercial`.

**Sibling specs:**
- **DR-READER** -- financial extraction (SUSA/BWA/JA to `deal_financials`). Same read-normalize-store pattern.
- **DR-GATHER** -- qualitative data (RFI responses, emails, Granola to `deal_notes`, `deal_meetings`).

---

## 1. Pipeline Architecture

```
[1. Source Selection]
    Filter deal_documents: doc_type='commercial_raw', matching subtype
    Skip: already extracted AND source file unchanged (mtime check)
        |
        v
[2. AI Classification]
    LLM reads file header (first 20 rows) + filename
    Outputs: { file_type, target_table, column_mapping, fiscal_year, notes }
    Confidence score per mapping
        |
        v
[3. Human Confirm]
    Print proposed mapping for Roman
    Roman confirms or corrects
    Mapping cached for re-extraction (same file = same mapping)
        |
        v
[4. Bulk Load]
    Parse all rows using confirmed mapping
    German number format handling (_parse_german_number)
    Entity resolution for customer/supplier names across years
    Idempotent write: DELETE WHERE source_file_id = ? then INSERT
        |
        v
[5. KPI Derivation]
    Compute concentration metrics, cohort analysis, product mix KPIs
    FROM raw data in deal_customers / deal_products
    Store derived KPIs in deal_commercial
        |
        v
[6. Review Gate]
    All data loads with is_authoritative = 0
    Roman reviews via review-commercial
    Approves -> is_authoritative = 1
    Downstream consumers query is_authoritative = 1 only
```

**Key architectural decision:** Steps 2-3 (AI classify + human confirm) run once per file. The confirmed mapping is persisted in `deal_documents.extraction_config` (JSON blob). Re-extraction (step 4) replays the confirmed mapping without re-prompting. This means Roman approves the mapping once, not on every re-run.

---

## 2. Source Patterns -- Real Examples

### Cat (Medizin & Service)

**Customer data -- `RAB nach Umsatz 2024.xlsx`:**

| Zeilenbeschriftungen | Summe von Gesamtwarenwert netto in Hauswährung (Rechnung) |
|---|---|
| SLK-Kliniken Heilbronn GmbH (K02699) | 1.234.567,89 |
| Klinikum Stuttgart (K01234) | 987.654,32 |
| ... (300+ rows) | |
| Gesamtergebnis | 12.345.678,90 |

**Characteristics:** Customer name with ID in parens. Single revenue column. German number format. Footer total row. 3 files covering FY2023-2025.

**Backlog -- `Auftragsübersicht 26 05.xlsx`:**

| Ort | Einrichtung | Was | Rohmarge % | Ausführung lt. LV | Auftragssumme | Rest | Angebot Zepter |
|---|---|---|---|---|---|---|---|
| Heilbronn | SLK-Kliniken | Umbau Station 3 | 42% | 2025 Q3 | 450.000 | x | 520.000 |
| Stuttgart | Klinikum | Neubau OP | 38% | 2026 Q1 | 1.200.000 | | 1.350.000 |

**Characteristics:** Project-level granularity. Margin per project. Execution timeline. "Rest" marker = not yet invoiced. 48 projects, 21M EUR total.

### Octopus (HWV)

**Customer data -- `Kundenumsatz_2024_RD.xlsx`:**

| Row Labels | Sum of Umsatz Vorjahr gesamt | Sum of Umsatz lfd Jahr | ... | ABC | Revenue share % |
|---|---|---|---|---|---|
| 100234 | 45.678,90 | 52.345,67 | ... | A | 2.1% |
| 100567 | 12.345,67 | 11.234,56 | ... | B | 0.5% |
| ... (6,750 rows) | | | | | |

**Characteristics:** Numeric IDs only (no names). Pre-computed ABC classification. Revenue share pre-calculated. Two years in one file (Vorjahr + lfd Jahr). 6,750 customers.

**Product data -- `Warengruppen-Rohgewinn_2024_RD.xlsx`:**

Summary sheet:

| Warengruppe | VK (Revenue) | EK (Cost) | Rohertrag | Marge % |
|---|---|---|---|---|
| Medizintechnik (MT) | 8.500.000 | 5.950.000 | 2.550.000 | 30.0% |
| Medizinprodukte (MP) | 4.200.000 | 3.360.000 | 840.000 | 20.0% |
| Service | 1.800.000 | 900.000 | 900.000 | 50.0% |
| SSB | 2.100.000 | 1.680.000 | 420.000 | 20.0% |
| Sonstiges | 400.000 | 320.000 | 80.000 | 20.0% |

Plus 19 detail sheets breaking each category into sub-groups (90+ product lines total).

**Characteristics:** Hierarchy: business line (5) to product group (90+). Revenue, cost, gross profit, margin per group. Summary + detail sheets. Completely different structure from Cat.

### The convergence problem

Same conceptual questions ("who are the top customers?", "what is the product mix?") require reading completely different file formats. The AI layer exists to bridge this gap: detect the file type, propose a column mapping, and normalize into the same target schema.

---

## 3. Target Schema Mapping

### Source type to target table

| Source Type | subtype | Target Table | Key Mapping |
|---|---|---|---|
| Customer revenue list (per year) | `customer_list` | `deal_customers` | Name/ID to customer_name/customer_id, revenue column to revenue_k |
| Customer ABC classification | `customer_list` | `deal_customers` | ABC letter to cohort |
| Product/Warengruppen breakdown | `product_split` | `deal_products` (NEW) | Category/VK/EK/Rohertrag/Marge to schema |
| Project backlog / Auftragsübersicht | `backlog` | `deal_backlog` | Project/client/value/execution_year/margin |
| Employee register | `employee_list` | `deal_employees` | Role/department/hours/salary |
| Supplier cost list | `supplier_list` | `deal_suppliers` | Supplier name/cost/product group |

### Column mapping examples -- AI output format

**Cat customer file:**
```json
{
  "file_type": "customer_revenue_list",
  "target_table": "deal_customers",
  "fiscal_year": 2024,
  "column_map": [
    {"col": "A", "target": "customer_name", "transform": "extract_name_before_paren"},
    {"col": "A", "target": "customer_id", "transform": "extract_id_from_paren"},
    {"col": "B", "target": "revenue_k", "transform": "german_number_div_1000"}
  ],
  "skip_rows": ["Gesamtergebnis", "(leer)"],
  "row_count_expected": 300,
  "confidence": 0.95
}
```

**Octopus customer file:**
```json
{
  "file_type": "customer_revenue_list",
  "target_table": "deal_customers",
  "fiscal_year": 2024,
  "column_map": {
    "A": {"target": "customer_id", "transform": "as_string"},
    "C": {"target": "revenue_k", "transform": "german_number_div_1000", "note": "lfd Jahr column"},
    "F": {"target": "cohort", "transform": "abc_letter"}
  },
  "skip_rows": ["Grand Total"],
  "row_count_expected": 6750,
  "confidence": 0.90
}
```

**Octopus product file:**
```json
{
  "file_type": "product_breakdown",
  "target_table": "deal_products",
  "fiscal_year": 2024,
  "sheets": {
    "Summary": {
      "column_map": {
        "A": {"target": "product_name"},
        "B": {"target": "revenue_k", "transform": "german_number_div_1000"},
        "C": {"target": "cost_k", "transform": "german_number_div_1000"},
        "D": {"target": "gross_profit_k", "transform": "german_number_div_1000"},
        "E": {"target": "margin_pct", "transform": "percent"}
      },
      "category_level": "business_line"
    },
    "MT_Detail": {
      "parent_category": "Medizintechnik",
      "category_level": "product_group"
    }
  },
  "confidence": 0.85
}
```

---

## 4. deal_products Schema (NEW)

```sql
CREATE TABLE IF NOT EXISTS deal_products (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    product_name    TEXT NOT NULL,
    category        TEXT,           -- business line (MT, MP, Service, SSB, Sonstiges)
    subcategory     TEXT,           -- product group within business line (90+ for Octopus)
    fiscal_year     INTEGER NOT NULL,
    revenue_k       REAL,           -- VK / Verkaufspreis, in K EUR
    cost_k          REAL,           -- EK / Einkaufspreis, in K EUR
    gross_profit_k  REAL,           -- Rohertrag = VK - EK, in K EUR
    margin_pct      REAL,           -- Rohmarge = Rohertrag / VK * 100
    revenue_share_pct REAL,         -- share of total revenue for that fiscal year
    units_sold      INTEGER,        -- if available (often not)
    is_recurring    INTEGER DEFAULT 0, -- service/maintenance = 1, project/one-off = 0
    notes           TEXT,
    source          TEXT,
    source_file_id  TEXT,
    confidence      TEXT DEFAULT 'stated',
    is_authoritative INTEGER DEFAULT 0,
    extracted_at    TEXT
);
```

**Design rationale:**
- `category` + `subcategory` captures the two-level hierarchy visible in Octopus data (business line to product group). For deals with flat product lists, `subcategory` is NULL.
- `revenue_k` / `cost_k` / `gross_profit_k` stored in K EUR, consistent with `deal_financials.value_k`. Source values divided by 1000 during extraction.
- `margin_pct` stored as-is from source when available; computed as `gross_profit_k / revenue_k * 100` otherwise.
- `revenue_share_pct` computed during KPI derivation, not at extraction time.
- `is_recurring` is a classification flag set during extraction (service contracts = recurring, project sales = one-off). Used by downstream recurring revenue analysis.
- `is_authoritative` follows the same review gate pattern as all other deal tables.

**Index:**
```sql
CREATE INDEX IF NOT EXISTS idx_products_domain_year ON deal_products(domain, fiscal_year);
```

---

## 5. AI Layer

The LLM is used at three points in the pipeline. Each interaction is bounded and verifiable.

### 5.1 File Classification

**When:** Step 2. First time a commercial file is processed.

**Input to LLM:**
- Filename (e.g., "RAB nach Umsatz 2024.xlsx")
- First 20 rows of data (headers + sample rows)
- Sheet names (if multi-sheet xlsx)
- Available target tables and their schemas

**Prompt pattern:**
```
You are classifying a deal data room file for a German ambulatory healthcare
distribution M&A target. Given the filename, headers, and sample data below,
determine:

1. file_type: one of [customer_revenue_list, customer_abc, product_breakdown,
   project_backlog, employee_register, supplier_list, unknown]
2. target_table: which DB table this maps to
3. fiscal_year: extracted from filename or data
4. column_map: for each source column, the target DB column + any transform
5. skip_rows: patterns for footer/total/empty rows to skip
6. confidence: 0.0-1.0

Filename: {filename}
Sheet names: {sheets}
Headers + first 15 data rows:
{sample_data}

Respond in JSON. If uncertain about any mapping, set confidence < 0.7 and
explain in notes.
```

**Output:** JSON mapping (see Section 3 examples). Cached in `deal_documents.extraction_config`.

**What the LLM does NOT do:** It does not extract data. It proposes a mapping. The actual extraction is deterministic Python code using the confirmed mapping.

### 5.2 Entity Resolution

**When:** Step 4, after bulk load. Matching customer/supplier names across fiscal years.

**Problem:** "SLK-Kliniken Heilbronn GmbH (K02699)" in 2024 vs "SLK Kliniken Heilbronn (K02699)" in 2023. Same entity, different string. Customer IDs help but are not always present (Octopus has IDs, Cat has IDs in parens, other deals may have names only).

**Approach:**
1. **ID-based match first:** If customer_id matches across years, entities are the same. No LLM needed.
2. **Name fuzzy match second:** For records without IDs, compute string similarity (Levenshtein / Jaro-Winkler). If similarity > 0.85, auto-match.
3. **LLM disambiguation third:** For similarity between 0.6-0.85, ask LLM to confirm. Present both names + context.

**LLM prompt for disambiguation:**
```
Are these the same entity? Consider that German company names may have
minor variations (GmbH vs. GmbH & Co. KG, abbreviated vs. full city names).

Entity A (FY2024): "SLK-Kliniken Heilbronn GmbH"
Entity B (FY2023): "SLK Kliniken Heilbronn"

Context: Customer of a medical device distributor in southern Germany.

Answer: SAME / DIFFERENT / UNCERTAIN
```

**Result:** Matched entities share the same `customer_id` in the DB. Unmatched entities are flagged for Roman's review.

### 5.3 Anomaly Detection

**When:** Step 5, during KPI derivation. Post-load sanity checks.

**Checks (rule-based, no LLM):**
- Revenue total from `deal_customers` vs `deal_financials` Gesamtleistung: delta > 5% = flag
- Customer count YoY change > 20% = flag
- Top customer revenue drop > 30% YoY = flag
- Product margin outside 5-60% range = flag
- Backlog total exceeding annual revenue by > 2x = flag

**LLM used only for:** Explaining anomalies in narrative form for the review output. Not for detection.

---

## 6. KPI Derivation

After raw data is loaded into entity tables, compute derived KPIs and store in `deal_commercial`. All formulas operate on `deal_customers` / `deal_products` data for a single domain + fiscal_year.

### Customer Concentration

| Metric | Formula | Category | Unit |
|---|---|---|---|
| `top1_customer_pct` | revenue_k[rank=1] / sum(revenue_k) * 100 | customers | % |
| `top5_customer_pct` | sum(revenue_k[rank<=5]) / sum(revenue_k) * 100 | customers | % |
| `top10_customer_pct` | sum(revenue_k[rank<=10]) / sum(revenue_k) * 100 | customers | % |
| `top20_customer_pct` | sum(revenue_k[rank<=20]) / sum(revenue_k) * 100 | customers | % |
| `customer_count` | count(distinct customer_id) | customers | # |
| `herfindahl_index` | sum((revenue_k / total_revenue)^2) | customers | index |
| `revenue_per_customer_k` | sum(revenue_k) / count(distinct customer_id) | customers | K EUR |

### Customer Cohort Analysis

| Metric | Formula | Category | Unit |
|---|---|---|---|
| `cohort_a_count` | count where cohort = 'A' | customers | # |
| `cohort_a_revenue_pct` | sum(revenue_k where cohort='A') / total * 100 | customers | % |
| `cohort_b_count` | count where cohort = 'B' | customers | # |
| `cohort_b_revenue_pct` | sum(revenue_k where cohort='B') / total * 100 | customers | % |
| `cohort_c_count` | count where cohort = 'C' | customers | # |
| `new_customers_count` | customers in FY not in FY-1 | customers | # |
| `churned_customers_count` | customers in FY-1 not in FY | customers | # |
| `retention_rate_pct` | (FY customers also in FY-1) / FY-1 count * 100 | customers | % |
| `net_revenue_retention_pct` | sum(FY revenue for FY-1 customers) / FY-1 total * 100 | customers | % |

**ABC classification:** If source file provides ABC letters, use them. Otherwise derive: A = top 80% cumulative revenue, B = next 15%, C = remaining 5%.

### Product Mix KPIs

| Metric | Formula | Category | Unit |
|---|---|---|---|
| `product_group_count` | count(distinct product_name) | products | # |
| `top_product_revenue_pct` | max(revenue_share_pct) | products | % |
| `weighted_avg_margin_pct` | sum(gross_profit_k) / sum(revenue_k) * 100 | products | % |
| `recurring_revenue_pct` | sum(revenue_k where is_recurring=1) / total * 100 | products | % |
| `service_revenue_pct` | sum(revenue_k where category='Service') / total * 100 | products | % |
| `highest_margin_category` | category with max margin_pct | products | text |
| `lowest_margin_category` | category with min margin_pct | products | text |

### Backlog KPIs

| Metric | Formula | Category | Unit |
|---|---|---|---|
| `backlog_total_k` | sum(value_k) | backlog | K EUR |
| `backlog_coverage_months` | backlog_total_k / (annual_revenue_k / 12) | backlog | months |
| `avg_project_margin_pct` | avg(margin) across backlog projects | backlog | % |
| `backlog_execution_current_year_k` | sum(value_k where execution_year = current) | backlog | K EUR |

### Employee KPIs

| Metric | Formula | Category | Unit |
|---|---|---|---|
| `headcount` | count(distinct employee_id) | employees | # |
| `fte_count` | sum(hours_per_week / 40) | employees | FTE |
| `avg_tenure_years` | avg(tenure_years) | employees | years |
| `revenue_per_employee_k` | Gesamtleistung / headcount | employees | K EUR |
| `key_person_count` | count where is_key_person = 1 | employees | # |

### Supplier KPIs

| Metric | Formula | Category | Unit |
|---|---|---|---|
| `top1_supplier_pct` | cost_k[rank=1] / sum(cost_k) * 100 | suppliers | % |
| `top5_supplier_pct` | sum(cost_k[rank<=5]) / sum(cost_k) * 100 | suppliers | % |
| `supplier_count` | count(distinct supplier_name) | suppliers | # |
| `exclusive_supplier_count` | count where exclusivity = 1 | suppliers | # |

### Storage in deal_commercial

All derived KPIs are stored as individual rows in `deal_commercial`:

```sql
INSERT INTO deal_commercial (id, domain, category, metric, fiscal_year,
    value_num, value_text, unit, source, confidence, is_authoritative, extracted_at)
VALUES (?, 'golmed.de', 'customers', 'top5_customer_pct', 2024,
    42.3, NULL, '%', 'derived:deal_customers', 'computed', 0, datetime('now'));
```

`source = 'derived:{source_table}'` distinguishes computed KPIs from directly extracted scalar values. `confidence = 'computed'` follows DR-READER convention.

---

## 7. CLI Interface

### 7.1 Command: `ingest-commercial`

```bash
python DEALROOM.py ingest-commercial --deal Cat
python DEALROOM.py ingest-commercial --deal Cat --type customer_list
python DEALROOM.py ingest-commercial --deal Cat --file "RAB nach Umsatz 2024.xlsx"
python DEALROOM.py ingest-commercial --deal Octopus --auto       # skip confirm for cached mappings
python DEALROOM.py ingest-commercial --deal Cat --dry-run
python DEALROOM.py ingest-commercial --deal Cat --force          # re-extract even if unchanged
```

| Argument | Required | Default | Description |
|---|---|---|---|
| `--deal` | Yes | -- | Deal code name |
| `--type` | No | all types | Filter: `customer_list`, `product_split`, `backlog`, `employee_list`, `supplier_list` |
| `--file` | No | all files | Process specific file only |
| `--auto` | No | false | Use cached mapping without re-prompting (for re-extraction) |
| `--dry-run` | No | false | Classify + map without writing to DB |
| `--force` | No | false | Re-extract even if source file mtime unchanged |

**Output format:**

```
DEALROOM ingest-commercial: Cat (Medizin & Service GmbH)
=========================================================

Processing 5 commercial documents...

  [1/5] RAB nach Umsatz 2023.xlsx
        AI classification: customer_revenue_list -> deal_customers (FY2023)
        Confidence: 0.95
        Column map:
          A -> customer_name (extract name before parens)
          A -> customer_id (extract ID from parens)
          B -> revenue_k (german_number / 1000)
        Skip: "Gesamtergebnis", "(leer)"
        [?] Confirm mapping? (Y/n/edit): Y
        -> 312 rows written to deal_customers

  [2/5] RAB nach Umsatz 2024.xlsx
        Using cached mapping from [1/5] (same structure detected)
        -> 308 rows written to deal_customers

  [3/5] RAB nach Umsatz 2025.xlsx
        Using cached mapping from [1/5]
        -> 295 rows written to deal_customers

  [4/5] Auftragsübersicht 26 05.xlsx
        AI classification: project_backlog -> deal_backlog
        Confidence: 0.88
        Column map:
          A -> location, B -> client_name, C -> service_type
          D -> margin (percent), E -> execution_year, F -> value_k
        [?] Confirm mapping? (Y/n/edit): Y
        -> 48 rows written to deal_backlog

  [5/5] No product/employee/supplier files registered.

Entity resolution (deal_customers):
  FY2023 vs FY2024: 295/312 matched by ID, 12 fuzzy-matched, 5 new
  FY2024 vs FY2025: 290/308 matched by ID, 10 fuzzy-matched, 8 new, 13 churned

Summary:
  Files processed:  4 / 4
  Rows written:     963 (deal_customers) + 48 (deal_backlog)
  Entity matches:   317 unique customers across 3 years
  Anomalies:        1 (top customer revenue drop 35% FY2023->2024 -- flag)

[!] Review gate: Run `DEALROOM.py review-commercial --deal Cat` to confirm data.
```

### 7.2 Command: `review-commercial`

```bash
python DEALROOM.py review-commercial --deal Cat
python DEALROOM.py review-commercial --deal Cat --table customers
python DEALROOM.py review-commercial --deal Cat --approve
python DEALROOM.py review-commercial --deal Cat --approve --table customers --year 2024
```

Displays:
1. Customer summary: top 10 by revenue, concentration metrics, YoY trends
2. Product summary: business lines with revenue/margin (if data exists)
3. Backlog summary: total value, execution timeline, avg margin
4. Employee summary: headcount, FTE, avg tenure (if data exists)
5. Supplier summary: top 5 by cost, exclusivity flags (if data exists)
6. Anomaly flags
7. Cross-check: customer revenue total vs Gesamtleistung from `deal_financials`

### 7.3 Command: `derive-kpis`

```bash
python DEALROOM.py derive-kpis --deal Cat
python DEALROOM.py derive-kpis --deal Cat --year 2024
python DEALROOM.py derive-kpis --all
```

Computes all KPIs from Section 6 and writes to `deal_commercial`. Idempotent: deletes existing derived KPIs for that domain+year before inserting.

**Output:**
```
DEALROOM derive-kpis: Cat (Medizin & Service GmbH)
====================================================

Customer KPIs (FY2024):
  top1_customer_pct:     18.3%
  top5_customer_pct:     42.1%
  top10_customer_pct:    58.7%
  customer_count:        308
  retention_rate_pct:    94.5%
  net_revenue_retention: 103.2%

Backlog KPIs:
  backlog_total_k:       21,000
  backlog_coverage:      14.2 months
  avg_project_margin:    39.8%

-> 24 KPI rows written to deal_commercial
```

---

## 8. Anti-Patterns

### AP-1: ASSUME-COLUMN-POSITIONS

**What happens:** Hardcoding "col A = customer name, col B = revenue" across all deals. Octopus has revenue in col C, ABC in col F.

**Prevention:** AI classification proposes column mapping per file. Never assume. Always confirm. Cache confirmed mappings for re-extraction.

### AP-2: IGNORE-GERMAN-NUMBERS

**What happens:** Parsing "1.234.567,89" as 1.234 (treating first dot as decimal). Or failing on negative values in parentheses.

**Prevention:** All numeric parsing routes through `_parse_german_number()` from `data.py`. No `float()` or `int()` on raw cell values. Unit test coverage for: "1.234,56", "-1.234,56", "(1.234,56)", "0,00", "1.234.567,89".

### AP-3: CUSTOMER-NAME-WITHOUT-ID-TRACKING

**What happens:** Loading customer names as-is across years without entity resolution. "SLK-Kliniken Heilbronn GmbH" in 2024 and "SLK Kliniken" in 2023 appear as two different customers. Concentration metrics are wrong, cohort analysis is wrong.

**Prevention:** Entity resolution pipeline (Section 5.2). ID-based matching first, fuzzy matching second, LLM disambiguation third. All matched entities share the same `customer_id`. Unmatched entities flagged for review.

### AP-4: SKIP-REVIEW-FOR-LARGE-DATASETS

**What happens:** Loading 6,750 Octopus customer rows without review because "too many to check." Then discovering the revenue total doesn't match Gesamtleistung because a header row was included or footer rows were not skipped.

**Prevention:** Post-load cross-check: sum(deal_customers.revenue_k) vs deal_financials Gesamtleistung. Delta > 5% = block. Always verify row count against expected range. Review gate is non-negotiable regardless of dataset size.

### AP-5: DERIVE-KPIS-BEFORE-APPROVAL

**What happens:** Computing concentration metrics from unapproved raw data, then presenting them in onepager or scorecard. Roman later corrects the raw data, but derived KPIs are stale.

**Prevention:** `derive-kpis` checks `is_authoritative = 1` on source rows. If raw data is unapproved, KPIs are computed but marked `is_authoritative = 0` and flagged as preliminary. Downstream consumers (onepager, scorecard) filter on `is_authoritative = 1`.

### AP-6: PRODUCT-DATA-WITHOUT-HIERARCHY

**What happens:** Loading 90+ Octopus product lines as flat list without capturing the business line grouping. Product mix analysis becomes meaningless because you cannot say "MT is 50% of revenue."

**Prevention:** `deal_products.category` captures the business line level, `subcategory` captures the product group level. AI classification detects hierarchy from sheet structure (summary sheet = business lines, detail sheets = product groups under each business line).

### AP-7: BACKLOG-DOUBLE-COUNTING

**What happens:** Loading the same backlog project from two overlapping files (e.g., monthly export snapshots) without deduplication. Total backlog is overstated.

**Prevention:** Idempotent extraction per source_file_id. If multiple files cover the same backlog, only the most recent file is loaded (or Roman chooses which file to use). Cross-check: backlog total should be plausible relative to annual revenue (1-2x range for project-based business).

---

## 9. Review Gate

**Hard rule:** Extracted commercial data does NOT flow to downstream consumers (onepager, scorecard, offer, dashboard) until Roman confirms.

### Review flow

```
[ingest-commercial completes]
       |
       v
[Extraction summary printed]
[Anomalies + cross-checks highlighted]
       |
       v
[Roman runs: review-commercial --deal X]
[Sees: top customers, product mix, backlog, cross-checks]
       |
       v
[Roman confirms: review-commercial --deal X --approve]
[OR: Roman flags issues -> re-extract / correct mapping]
       |
       v
[Approved data marked: is_authoritative = 1]
[derive-kpis runs on approved data]
[Downstream consumers can now query authoritative data]
```

### Approval scope

Approval is per-deal, per-table, per-fiscal-year. Approving Cat customer data for FY2024 does not approve FY2023 or backlog data.

### What triggers re-review

1. Source file updated (new export from target) -> `--force` re-extract clears `is_authoritative`
2. Entity resolution changed (new matching rules) -> KPIs recalculated, flagged for review
3. New commercial file added for same deal
4. Column mapping corrected by Roman

---

## 10. Cross-References

| Spec | Relationship | Shared Data |
|---|---|---|
| **SPEC-DR-READER** | Sibling. Same read-normalize-store pattern. DR-READER handles financials, DR-COMMERCIAL handles commercial. Cross-check: customer revenue total vs Gesamtleistung from `deal_financials`. | `deal_financials` (read for cross-check) |
| **SPEC-DR-MODEL** | No direct interface. DR-MODEL reads `deal_financials` only. Commercial data does not flow into the Excel financial model. | None |
| **SPEC-ONEPAGER** | Downstream consumer. Reads `deal_customers` (concentration, top customers), `deal_products` (product mix chart), `deal_commercial` (derived KPIs for snapshot). | `deal_customers`, `deal_products`, `deal_commercial` |
| **SPEC-OFFER** | Downstream consumer. Reads `deal_commercial` for commercial context in offer letter (customer base description, market position). | `deal_commercial` (KPIs) |
| **SPEC-RFI** | Sibling. Gaps in commercial data (missing supplier info, no employee register) may trigger RFI questions. Anomalies (customer concentration > 70%) inform RFI priorities. | Gap analysis from `deal_commercial` |
| **DEAL_DELIVERABLES_SPEC** | Process reference. Stage 2 scorecard (sub-step 2.4) consumes concentration metrics, product mix, employee data from `deal_commercial`. | Scorecard dimensions |
| **DR-GATHER** | Sibling. Qualitative commercial context (management call notes about customer relationships, market position) stored separately in `deal_notes`/`deal_meetings`. DR-COMMERCIAL handles structured tabular data only. | Separate tables |
| **Dashboard** | Consumer. Customer tab and commercial tab in HTML dashboard read from `deal_customers` and `deal_commercial`. | Direct DB queries |

### Downstream consumers summary

| Consumer | Data Read | What It Uses It For |
|---|---|---|
| Onepager | `deal_customers` top 10, `deal_commercial` concentration KPIs, `deal_products` category split | Customer concentration chart, product mix, revenue by segment |
| Commercial DD | `deal_customers` full, `deal_products` full, `deal_suppliers`, `deal_employees` | Deep analysis: customer dependency, supplier risk, margin by product, key person assessment |
| Offer letter | `deal_commercial` KPIs | Narrative: "~300 customers, top 5 represent 42% of revenue" |
| Dashboard | `deal_customers`, `deal_commercial` | Customer tab, commercial tab |
| IC Document | All commercial tables | Superset containing all commercial analysis sections |
| Valuation Logic | `deal_commercial` KPIs | Concentration risk discount, key person dependency adjustment |

---

## 11. Implementation Priority

**Phase 1 -- Customer data (highest value, most complete data available):**
- AI classification for customer list files
- Bulk load to `deal_customers`
- Entity resolution (ID-based + fuzzy)
- Concentration KPI derivation
- Cross-check against `deal_financials`
- Test on Cat (3 years, 300 rows/year) + Octopus (1 year, 6,750 rows)

**Phase 2 -- Product data + backlog:**
- `deal_products` schema migration (CREATE TABLE)
- Multi-sheet product file handling (Octopus Warengruppen)
- Backlog extraction (Cat Auftragsübersicht)
- Product mix + backlog KPI derivation

**Phase 3 -- Employee + supplier data:**
- Employee register extraction (when data becomes available)
- Supplier list extraction
- Employee + supplier KPI derivation
- Full scorecard integration

**Phase 4 -- Entity resolution refinement:**
- Cross-deal entity matching (same customer appears in Cat and Octopus)
- Historical trend analysis across 3+ years
- Automated anomaly narrative generation
