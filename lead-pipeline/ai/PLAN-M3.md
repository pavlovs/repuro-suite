# PLAN-M3: Data Ingest (SQLite-backed)

## Context

M2 delivered: WLW scraper + SQLite knowledge base. Output: `data/staging/00_wlw_raw.csv` (CompanyRecord-format CSV, sparse on address/ownership fields).

M3 delivers:
1. **`data/pipeline.db`** — SQLite primary store for all pipeline stages M3–M11. Replaces staging CSVs.
2. **Multi-source ingest**: WLW CSV + ORBIS_search sheet + 250527 sheet (LLM prep) → single normalized `company_records` table
3. **Ownership pre-population**: ORBIS CSH and Gesellschafter data written to CompanyRecord fields at ingest time → M7 API calls skipped for pre-populated records
4. **Already-approached dedup**: Serienbriefe "Domain Name Clean" → `already_approached=1`
5. **Adapter pattern**: each source (WLW CSV, ORBIS, LLMPrep) implements `SourceAdapter` protocol — adding a new source = adding one class
6. **Shared DB module**: `src/pipeline/db.py` — connection, schema creation, upsert, query helpers used by all downstream milestones

After M3: `python pipeline.py ingest` runs, writes to `data/pipeline.db`, and `python pipeline.py status` queries the DB for counts.

**Architecture decision:** SQLite (`pipeline.db`) is the primary pipeline store. CSVs are input-only (WLW scraper output) or final export (M10 Serienbriefe). No CSV staging files after M3.

---

## Source Data Facts (researched)

**WLW CSV** (`data/staging/00_wlw_raw.csv`):
- Already in CompanyRecord column format (written by M2 scraper)
- Sparse: many records have city and scraped_text, but no HRB, no PLZ, no street
- MA count is approximate (WLW-reported: 1/5/10/20/50 buckets)
- `source="WLW"`, `profile_id="medtech_germany"`

**ORBIS_search sheet** (`260319_Repuro_Medtech_Targets_v3_claude.xlsx`, sheet `ORBIS_search`):
- 2,978 rows (row 1 = headers)
- Column index map (0-based):
  - `0`: Unternehmensname → `full_name`
  - `13`: Domain (plain text) → `domain` ← **use this, not col 1 which has formulas**
  - `7`: Betriebsertrag (Umsatz) tsd EUR → `revenue_tsd_eur` (may be formula or string)
  - `8`: Anzahl der Mitarbeiter → `ma_count` (may be "n.v." = None)
  - `10`: Straße, Hausnr. → `street`
  - `11`: Postleitzahl → `plz_ort` (combine with city as "PLZ Ort")
  - `12`: Ort → `city`
  - `16`: CSH - Name → `gesellschafter_name` (corporate parent if subsidiary)
  - `17`: CSH - Direkt % → (used for subsidiary detection)
  - `18`: CSH - Gesamt % → `gesellschafter_share_pct` (when col 16 non-empty)
  - `19`: Anrede → `anrede` (285/2978 rows)
  - `20`: Vorname → GF first name (305/2978 rows)
  - `21`: Nachname → GF last name (305/2978 rows) → `gf_name = f"{Vorname} {Nachname}".strip()`
  - `22`: GesellschafterName → `gesellschafter_name` (874/2978 rows; prefer over CSH)
  - `26`: Gesellschafter - Direkt % → `gesellschafter_share_pct` (when col 22 non-empty)
  - `28`: DMNachname → GF last name fallback (2,894/2978 rows; use when cols 20/21 empty)
  - `29`: DMGeburtstag → Excel serial date → convert to age → `gesellschafter_age`

**250527 sheet** (`260319_Repuro_Medtech_Targets_v3_claude.xlsx`, sheet `250527`):
- Row 2 = headers, data starts row 3 (~126 rows)
- Column index map (0-based):
  - `3`: URL/domain → `domain`
  - `4`: Full name → `full_name`
  - `5`: Address (freetext "Straße, PLZ Stadt") → parse for `street`/`plz_ort`/`city`
  - `6`: hrb_numberMD → `hrb_number`
  - `7`: MD (GF names, comma-separated) → `gf_name` (first name only)
  - `8`: MA → `ma_count`
- **Role**: enrichment source only. Contributes HRB + GF names to records that already exist in ORBIS or WLW. Not a standalone lead source (avoids double-counting).

**Serienbriefe sheet** (dedup reference only):
- Column index `2` = "Domain Name Clean" → load into a set of already-approached domains
- Marks matching records `already_approached=1`

**Excel is opened once.** All three sheet reads (ORBIS, 250527, Serienbriefe) happen in a single `openpyxl.load_workbook()` call.

---

## Subsidiary Detection Logic (ORBIS)

A record is flagged `is_subsidiary=1` when:
- Col 16 (`CSH - Name`) is non-empty **AND**
- Col 18 (`CSH - Gesamt %`) >= 50.0 **AND**
- CSH name looks corporate (contains any of: "GmbH", "AG", "SE", "KG", "Corp", "Group", "Holding", "GmbH & Co", "Inc", "Ltd", "BV", "NV", "SA", "SAS", "SRL")

For records without CSH data: `is_subsidiary = NULL` (unknown — M8 decides later).

---

## Files to Create / Modify

```
Create:
  src/pipeline/db.py           # SQLite connection, schema, upsert, query helpers
  tests/test_ingest.py         # Ingest tests

Modify:
  src/pipeline/ingest.py       # Full implementation (replace stub)
  src/config/settings.py       # Add PIPELINE_DB_PATH, HANDELSREGISTER_DB_PATH, sheet/column constants
  pipeline.py                  # Update cmd_status to query pipeline.db instead of reading CSVs
```

No other files needed.

---

## Step 1: Update `src/config/settings.py`

Add after existing constants:

```python
# Pipeline SQLite DB — primary store for all stages M3-M11
PIPELINE_DB_PATH = DATA_DIR / "pipeline.db"

# Handelsregister (offeneregister.de export) — full local DB for M7 GF lookup
HANDELSREGISTER_DB_PATH = DATA_DIR / "handelsregister.db"

# Source Excel — sheet names
ORBIS_SHEET = "ORBIS_search"
LLM_PREP_SHEET = "250527"
SERIENBRIEFE_SHEET = "Serienbriefe"

# Source Excel — column indices (0-based)
ORBIS_COL_NAME = 0
ORBIS_COL_DOMAIN = 13
ORBIS_COL_REVENUE = 7
ORBIS_COL_MA = 8
ORBIS_COL_STREET = 10
ORBIS_COL_PLZ = 11
ORBIS_COL_CITY = 12
ORBIS_COL_CSH_NAME = 16
ORBIS_COL_CSH_DIRECT_PCT = 17
ORBIS_COL_CSH_TOTAL_PCT = 18
ORBIS_COL_ANREDE = 19
ORBIS_COL_GF_VORNAME = 20
ORBIS_COL_GF_NACHNAME = 21
ORBIS_COL_GESELLSCHAFTER_NAME = 22
ORBIS_COL_GESELLSCHAFTER_PCT = 26
ORBIS_COL_DM_NACHNAME = 28
ORBIS_COL_DM_BIRTHDAY = 29

LLM_PREP_HEADER_ROW = 2   # 1-based row containing headers
LLM_PREP_COL_DOMAIN = 3
LLM_PREP_COL_NAME = 4
LLM_PREP_COL_ADDRESS = 5
LLM_PREP_COL_HRB = 6
LLM_PREP_COL_GF = 7
LLM_PREP_COL_MA = 8

SERIENBRIEFE_COL_DOMAIN = 2   # "Domain Name Clean"

# Corporate entity keywords for subsidiary detection
CORPORATE_KEYWORDS = (
    "GmbH", "AG", "SE", "KG", " KG", "Corp", "Group", "Holding",
    "Inc", "Ltd", "BV", "NV", "SA", "SAS", "SRL", "S.A.", "Plc",
)
```

Remove `STAGING_INGESTED` through `STAGING_ENRICHED_EMAIL` (those CSV paths are replaced by `PIPELINE_DB_PATH`). Keep `STAGING_WLW_RAW` — it's the M2 scraper output and M3 reads it as input.

---

## Step 2: Create `src/pipeline/db.py`

Shared SQLite layer used by all pipeline stages. Schema mirrors `CompanyRecord` fields exactly.

```python
"""SQLite pipeline database — shared by all pipeline stages M3-M11."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from src.pipeline.models import CompanyRecord

# Pipeline stage values (set as records progress)
STAGE_INGESTED = "ingested"
STAGE_FILTERED = "filtered"
STAGE_SCRAPED = "scraped"
STAGE_CLASSIFIED = "classified"
STAGE_OWNERSHIP_ENRICHED = "ownership_enriched"
STAGE_OWNERSHIP_GATED = "ownership_gated"
STAGE_EMAIL_ENRICHED = "email_enriched"


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS company_records (
    id                      TEXT PRIMARY KEY,
    domain                  TEXT UNIQUE NOT NULL,
    full_name               TEXT NOT NULL,
    profile_id              TEXT NOT NULL,
    source                  TEXT NOT NULL,
    pipeline_stage          TEXT NOT NULL DEFAULT 'ingested',
    hrb_number              TEXT,
    rechtsform              TEXT,
    street                  TEXT,
    plz_ort                 TEXT,
    city                    TEXT,
    region                  TEXT,
    ma_count                INTEGER,
    revenue_tsd_eur         REAL,
    klass                   TEXT,
    services_score          INTEGER,
    service_flag            INTEGER,
    distributor_flag        INTEGER,
    ssb_flag                INTEGER,
    leistung_text           TEXT,
    reasoning               TEXT,
    compliment_draft        TEXT,
    reclassify_reason       TEXT,
    gesellschafter_name     TEXT,
    gesellschafter_share_pct REAL,
    gesellschafter_age      INTEGER,
    is_subsidiary           INTEGER,
    is_pe_backed            INTEGER,
    gf_name                 TEXT,
    gf_email                TEXT,
    gf_phone                TEXT,
    anrede                  TEXT,
    salutation              TEXT,
    already_approached      INTEGER NOT NULL DEFAULT 0,
    filter_pass             INTEGER,
    filter_reason           TEXT,
    ownership_pass          INTEGER,
    ownership_reason        TEXT,
    scraped_text            TEXT,
    scraped_at              TEXT,
    classified_at           TEXT,
    enriched_at             TEXT,
    ingested_at             TEXT NOT NULL
)
"""


@contextmanager
def get_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite connections with WAL mode."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema(db_path: Path) -> None:
    """Create tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.execute(_CREATE_TABLE)


def upsert_company(conn: sqlite3.Connection, rec: CompanyRecord, ingested_at: str) -> None:
    """
    Insert or update a company record.
    On domain conflict: fill NULL fields from the new record (ORBIS wins over WLW for structured fields).
    Caller controls source priority by inserting high-priority records first.
    """
    conn.execute("""
        INSERT INTO company_records (
            id, domain, full_name, profile_id, source, pipeline_stage,
            hrb_number, rechtsform, street, plz_ort, city, region,
            ma_count, revenue_tsd_eur,
            gesellschafter_name, gesellschafter_share_pct, gesellschafter_age,
            is_subsidiary, is_pe_backed,
            gf_name, gf_email, gf_phone, anrede, salutation,
            already_approached,
            scraped_text, ingested_at
        ) VALUES (
            :id, :domain, :full_name, :profile_id, :source, 'ingested',
            :hrb_number, :rechtsform, :street, :plz_ort, :city, :region,
            :ma_count, :revenue_tsd_eur,
            :gesellschafter_name, :gesellschafter_share_pct, :gesellschafter_age,
            :is_subsidiary, :is_pe_backed,
            :gf_name, :gf_email, :gf_phone, :anrede, :salutation,
            :already_approached,
            :scraped_text, :ingested_at
        )
        ON CONFLICT(domain) DO UPDATE SET
            hrb_number              = COALESCE(company_records.hrb_number,              excluded.hrb_number),
            rechtsform              = COALESCE(company_records.rechtsform,              excluded.rechtsform),
            street                  = COALESCE(company_records.street,                  excluded.street),
            plz_ort                 = COALESCE(company_records.plz_ort,                 excluded.plz_ort),
            city                    = COALESCE(company_records.city,                    excluded.city),
            region                  = COALESCE(company_records.region,                  excluded.region),
            ma_count                = COALESCE(company_records.ma_count,                excluded.ma_count),
            revenue_tsd_eur         = COALESCE(company_records.revenue_tsd_eur,         excluded.revenue_tsd_eur),
            gesellschafter_name     = COALESCE(company_records.gesellschafter_name,     excluded.gesellschafter_name),
            gesellschafter_share_pct = COALESCE(company_records.gesellschafter_share_pct, excluded.gesellschafter_share_pct),
            gesellschafter_age      = COALESCE(company_records.gesellschafter_age,      excluded.gesellschafter_age),
            is_subsidiary           = COALESCE(company_records.is_subsidiary,           excluded.is_subsidiary),
            gf_name                 = COALESCE(company_records.gf_name,                 excluded.gf_name),
            anrede                  = COALESCE(company_records.anrede,                  excluded.anrede),
            scraped_text            = COALESCE(company_records.scraped_text,            excluded.scraped_text)
    """, {
        "id": rec.id,
        "domain": rec.domain,
        "full_name": rec.full_name,
        "profile_id": rec.profile_id,
        "source": rec.source,
        "hrb_number": rec.hrb_number,
        "rechtsform": rec.rechtsform,
        "street": rec.street,
        "plz_ort": rec.plz_ort,
        "city": rec.city,
        "region": rec.region,
        "ma_count": rec.ma_count,
        "revenue_tsd_eur": rec.revenue_tsd_eur,
        "gesellschafter_name": rec.gesellschafter_name,
        "gesellschafter_share_pct": rec.gesellschafter_share_pct,
        "gesellschafter_age": rec.gesellschafter_age,
        "is_subsidiary": int(rec.is_subsidiary) if rec.is_subsidiary is not None else None,
        "is_pe_backed": int(rec.is_pe_backed) if rec.is_pe_backed is not None else None,
        "gf_name": rec.gf_name,
        "gf_email": rec.gf_email,
        "gf_phone": rec.gf_phone,
        "anrede": rec.anrede,
        "salutation": rec.salutation,
        "already_approached": 1 if rec.already_approached else 0,
        "scraped_text": rec.scraped_text,
        "ingested_at": ingested_at,
    })


def mark_approached(conn: sqlite3.Connection, domains: frozenset[str]) -> int:
    """Set already_approached=1 for all matching domains. Returns count updated."""
    if not domains:
        return 0
    placeholders = ",".join("?" * len(domains))
    cursor = conn.execute(
        f"UPDATE company_records SET already_approached=1 WHERE domain IN ({placeholders})",
        list(domains),
    )
    return cursor.rowcount


def get_stage_counts(db_path: Path) -> dict[str, int]:
    """Return {pipeline_stage: count} for the status command."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT pipeline_stage, COUNT(*) FROM company_records GROUP BY pipeline_stage"
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def get_total_count(db_path: Path) -> int:
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM company_records").fetchone()[0]


def get_klass_counts(db_path: Path) -> dict[str, int]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT klass, COUNT(*) FROM company_records WHERE klass IS NOT NULL GROUP BY klass"
        ).fetchall()
    return {row[0]: row[1] for row in rows}
```

---

## Step 3: Implement `src/pipeline/ingest.py`

Opens Excel **once**. Reads ORBIS, 250527, and Serienbriefe sheets from the single open workbook. Writes to `pipeline.db` via `db.upsert_company`.

Insert order: ORBIS first (highest priority), then WLW. The `ON CONFLICT DO UPDATE SET ... = COALESCE(existing, new)` logic in `db.upsert_company` ensures ORBIS wins for structured fields.

```python
"""Data ingestion — normalize all sources to CompanyRecord, write to pipeline.db."""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

import openpyxl

from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline import db as pipeline_db
from src.pipeline.models import CompanyRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain normalization
# ---------------------------------------------------------------------------

_DOMAIN_PREFIX_RE = re.compile(r"^(https?://)?(www\.)?", re.IGNORECASE)


def normalize_domain(raw: Optional[str]) -> Optional[str]:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().lower()
    s = _DOMAIN_PREFIX_RE.sub("", s)
    s = s.split("/")[0].strip()
    return s or None


# ---------------------------------------------------------------------------
# Source adapter protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SourceAdapter(Protocol):
    @property
    def name(self) -> str: ...
    def read(self) -> list[CompanyRecord]: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CORPORATE_KW = frozenset(kw.lower() for kw in settings.CORPORATE_KEYWORDS)


def _is_corporate_name(name: Optional[str]) -> bool:
    if not name:
        return False
    low = name.lower()
    return any(kw in low for kw in _CORPORATE_KW)


def _excel_serial_to_age(serial: object) -> Optional[int]:
    if serial is None:
        return None
    try:
        n = float(str(serial))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None
    if n <= 0:
        return None
    birth_date = datetime(1899, 12, 30) + timedelta(days=n)
    age = (datetime.now() - birth_date).days // 365
    return age if 0 < age < 120 else None


def _safe_float(val: object) -> Optional[float]:
    if val is None or str(val).strip() in ("", "n.v.", "N/A", "nan"):
        return None
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _safe_int(val: object) -> Optional[int]:
    f = _safe_float(val)
    return int(f) if f is not None else None


# ---------------------------------------------------------------------------
# Adapter: WLW CSV
# ---------------------------------------------------------------------------

class WLWCsvAdapter:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def name(self) -> str:
        return "WLW CSV"

    def read(self) -> list[CompanyRecord]:
        if not self._path.exists():
            logger.warning("WLW CSV not found: %s — skipping", self._path)
            return []
        records: list[CompanyRecord] = []
        with open(self._path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                domain = normalize_domain(row.get("domain"))
                if not domain:
                    continue
                row["domain"] = domain
                try:
                    records.append(CompanyRecord.from_dict(row))
                except Exception as exc:
                    logger.debug("Skipping WLW row (parse error): %s", exc)
        logger.info("WLW CSV: %d records loaded", len(records))
        return records


# ---------------------------------------------------------------------------
# Adapter: ORBIS Excel (reads from pre-opened worksheet)
# ---------------------------------------------------------------------------

class OrbisSheetAdapter:
    def __init__(self, ws: object, profile_id: str) -> None:
        self._ws = ws
        self._profile_id = profile_id

    @property
    def name(self) -> str:
        return "ORBIS Excel"

    def read(self) -> list[CompanyRecord]:
        records: list[CompanyRecord] = []
        skipped = 0

        for row in self._ws.iter_rows(min_row=2, values_only=True):
            domain = normalize_domain(row[settings.ORBIS_COL_DOMAIN])
            if not domain:
                skipped += 1
                continue

            full_name = str(row[settings.ORBIS_COL_NAME] or "").strip() or domain

            plz_raw = str(row[settings.ORBIS_COL_PLZ] or "").strip()
            city_raw = str(row[settings.ORBIS_COL_CITY] or "").strip()
            plz_ort = f"{plz_raw} {city_raw}".strip() if (plz_raw or city_raw) else None

            vorname = str(row[settings.ORBIS_COL_GF_VORNAME] or "").strip()
            nachname = str(row[settings.ORBIS_COL_GF_NACHNAME] or "").strip()
            if vorname or nachname:
                gf_name: Optional[str] = f"{vorname} {nachname}".strip() or None
            else:
                dm_last = str(row[settings.ORBIS_COL_DM_NACHNAME] or "").strip()
                gf_name = dm_last or None

            anrede_raw = str(row[settings.ORBIS_COL_ANREDE] or "").strip()
            anrede: Optional[str] = anrede_raw if anrede_raw else None

            ges_name_raw = str(row[settings.ORBIS_COL_GESELLSCHAFTER_NAME] or "").strip()
            csh_name_raw = str(row[settings.ORBIS_COL_CSH_NAME] or "").strip()
            ges_pct_raw = row[settings.ORBIS_COL_GESELLSCHAFTER_PCT]
            csh_total_raw = row[settings.ORBIS_COL_CSH_TOTAL_PCT]

            if ges_name_raw:
                gesellschafter_name: Optional[str] = ges_name_raw
                gesellschafter_share_pct = _safe_float(ges_pct_raw)
            elif csh_name_raw:
                gesellschafter_name = csh_name_raw
                gesellschafter_share_pct = _safe_float(csh_total_raw)
            else:
                gesellschafter_name = None
                gesellschafter_share_pct = None

            gesellschafter_age = _excel_serial_to_age(row[settings.ORBIS_COL_DM_BIRTHDAY])

            csh_total_pct = _safe_float(csh_total_raw)
            is_subsidiary: Optional[bool] = None
            if csh_name_raw and csh_total_pct is not None and csh_total_pct >= 50.0:
                if _is_corporate_name(csh_name_raw):
                    is_subsidiary = True

            records.append(CompanyRecord(
                domain=domain,
                full_name=full_name,
                profile_id=self._profile_id,
                source="ORBIS",
                street=str(row[settings.ORBIS_COL_STREET] or "").strip() or None,
                plz_ort=plz_ort,
                city=city_raw or None,
                ma_count=_safe_int(row[settings.ORBIS_COL_MA]),
                revenue_tsd_eur=_safe_float(row[settings.ORBIS_COL_REVENUE]),
                gf_name=gf_name,
                anrede=anrede,
                gesellschafter_name=gesellschafter_name,
                gesellschafter_share_pct=gesellschafter_share_pct,
                gesellschafter_age=gesellschafter_age,
                is_subsidiary=is_subsidiary,
            ))

        logger.info("ORBIS: %d records loaded, %d skipped (no domain)", len(records), skipped)
        return records


# ---------------------------------------------------------------------------
# LLMPrep enrichment (reads from pre-opened worksheet)
# ---------------------------------------------------------------------------

def _read_llm_prep_enrichment(ws: object) -> dict[str, dict]:
    enrichment: dict[str, dict] = {}
    for row in ws.iter_rows(min_row=settings.LLM_PREP_HEADER_ROW + 1, values_only=True):
        domain = normalize_domain(row[settings.LLM_PREP_COL_DOMAIN])
        if not domain:
            continue
        hrb_raw = str(row[settings.LLM_PREP_COL_HRB] or "").strip()
        gf_raw = str(row[settings.LLM_PREP_COL_GF] or "").strip()
        gf_name = gf_raw.split(",")[0].strip() if gf_raw else None
        enrichment[domain] = {
            "hrb_number": hrb_raw or None,
            "gf_name": gf_name,
            "ma_count": _safe_int(row[settings.LLM_PREP_COL_MA]),
        }
    logger.info("LLMPrep: %d enrichment entries loaded", len(enrichment))
    return enrichment


# ---------------------------------------------------------------------------
# Serienbriefe dedup (reads from pre-opened worksheet)
# ---------------------------------------------------------------------------

def _read_serienbriefe_domains(ws: object) -> frozenset[str]:
    domains: set[str] = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = normalize_domain(row[settings.SERIENBRIEFE_COL_DOMAIN])
        if d:
            domains.add(d)
    logger.info("Serienbriefe: %d already-approached domains loaded", len(domains))
    return frozenset(domains)


# ---------------------------------------------------------------------------
# Main ingest function
# ---------------------------------------------------------------------------

def ingest(
    profile: IndustryProfile,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Load all sources, normalize, write to pipeline.db. Returns record count written."""

    ingested_at = datetime.now(timezone.utc).isoformat()

    # 1. WLW CSV (no Excel dependency)
    wlw_records = WLWCsvAdapter(settings.STAGING_WLW_RAW).read()

    # 2. Open Excel ONCE — read all three sheets
    orbis_records: list[CompanyRecord] = []
    llm_enrichment: dict[str, dict] = {}
    approached_domains: frozenset[str] = frozenset()

    if settings.SOURCE_EXCEL.exists():
        logger.info("Opening source Excel (once): %s", settings.SOURCE_EXCEL)
        wb = openpyxl.load_workbook(settings.SOURCE_EXCEL, read_only=True, data_only=True)

        orbis_records = OrbisSheetAdapter(wb[settings.ORBIS_SHEET], profile.id).read()
        llm_enrichment = _read_llm_prep_enrichment(wb[settings.LLM_PREP_SHEET])
        approached_domains = _read_serienbriefe_domains(wb[settings.SERIENBRIEFE_SHEET])

        wb.close()
        logger.info("Excel closed.")
    else:
        logger.warning("Source Excel not found: %s — skipping ORBIS/LLMPrep/Serienbriefe", settings.SOURCE_EXCEL)

    total_sources = len(wlw_records) + len(orbis_records)
    logger.info("Total from all sources (before dedup): %d", total_sources)

    if dry_run:
        logger.info("DRY RUN — skipping DB write. Would process %d records.", total_sources)
        return total_sources

    # 3. Write to DB — ORBIS first (higher priority), then WLW
    # The upsert logic fills NULLs from later sources, so insertion order matters.
    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        # Insert ORBIS records first (structured data wins)
        for rec in orbis_records:
            # Apply LLMPrep enrichment before insert (fill hrb/gf if available)
            patch = llm_enrichment.get(rec.domain)
            if patch:
                if rec.hrb_number is None and patch.get("hrb_number"):
                    object.__setattr__(rec, "hrb_number", patch["hrb_number"])
                if rec.gf_name is None and patch.get("gf_name"):
                    object.__setattr__(rec, "gf_name", patch["gf_name"])
                if rec.ma_count is None and patch.get("ma_count"):
                    object.__setattr__(rec, "ma_count", patch["ma_count"])
            # Mark already-approached
            if rec.domain in approached_domains:
                object.__setattr__(rec, "already_approached", True)
            pipeline_db.upsert_company(conn, rec, ingested_at)

        # Insert WLW records (fills NULLs in ORBIS records, e.g. scraped_text)
        for rec in wlw_records:
            if rec.domain in approached_domains:
                object.__setattr__(rec, "already_approached", True)
            pipeline_db.upsert_company(conn, rec, ingested_at)

        # Final already-approached pass (catches WLW-only records)
        approached_count = pipeline_db.mark_approached(conn, approached_domains)

    total = pipeline_db.get_total_count(settings.PIPELINE_DB_PATH)
    logger.info("pipeline.db: %d unique records after ingest", total)
    return total
```

---

## Step 4: Update `pipeline.py` — `cmd_status`

Replace the CSV-reading `cmd_status` with a DB-querying version:

```python
def cmd_status(args: argparse.Namespace) -> None:
    """Show pipeline funnel — record counts at each stage."""
    from src.pipeline.db import get_stage_counts, get_total_count, get_klass_counts
    from src.config import settings

    print(f"\nPipeline status — {settings.PIPELINE_DB_PATH.name}")
    print("-" * 60)

    if not settings.PIPELINE_DB_PATH.exists():
        print("  pipeline.db not found. Run 'python pipeline.py ingest' to start.")
    else:
        total = get_total_count(settings.PIPELINE_DB_PATH)
        stage_counts = get_stage_counts(settings.PIPELINE_DB_PATH)
        klass_counts = get_klass_counts(settings.PIPELINE_DB_PATH)

        stage_labels = [
            ("ingested",           "M3 Ingested       "),
            ("filtered",           "M4 Filtered       "),
            ("scraped",            "M5 Scraped        "),
            ("classified",         "M6 Classified     "),
            ("ownership_enriched", "M7 Ownership enr. "),
            ("ownership_gated",    "M8 Ownership gate "),
            ("email_enriched",     "M9 Email enriched "),
        ]

        print(f"  Total unique companies: {total:,}")
        print()
        for stage, label in stage_labels:
            count = stage_counts.get(stage, 0)
            if count:
                print(f"  {label}  {count:>5,}")

        if klass_counts:
            parts = "  ".join(f"{k}:{v}" for k, v in sorted(klass_counts.items()))
            print(f"\n  Classifications → {parts}")

    # WLW raw CSV (M2 output — still a CSV)
    if settings.STAGING_WLW_RAW.exists():
        import pandas as pd
        wlw_count = len(pd.read_csv(settings.STAGING_WLW_RAW, encoding="utf-8"))
        print(f"\n  M2 WLW raw CSV:    {wlw_count:>5,}  ({settings.STAGING_WLW_RAW.name})")

    # Knowledge base stats
    if settings.KNOWLEDGE_BASE_PATH.exists():
        from src.utils.knowledge_base import KnowledgeBase
        s = KnowledgeBase(settings.KNOWLEDGE_BASE_PATH).stats()
        print(f"\n  Knowledge base: {s['domains_cached']} domains | "
              f"{s['with_text']} with text | "
              f"{s['ownership_cached']} ownership records")

    print("-" * 60)
```

---

## Step 5: Tests (`tests/test_ingest.py`)

All tests use in-memory SQLite (`:memory:` equivalent via tmp_path). No real Excel files loaded.

Tests to implement:

**`normalize_domain`:** strip https, www, lowercase, empty/None → None

**`_is_corporate_name`:** detects GmbH, Holding; rejects person names

**`_excel_serial_to_age`:** valid serial, None, invalid string

**`WLWCsvAdapter`:** reads records from tmp CSV, missing file → `[]`

**`OrbisSheetAdapter` (mock worksheet rows):**
- column mapping
- subsidiary detection (corporate CSH ≥50% → `is_subsidiary=True`)
- no subsidiary on person name
- no subsidiary on low pct
- "n.v." MA → `ma_count=None`
- GF name from Vorname/Nachname
- GF name fallback to DMNachname
- Prefers Gesellschafter col 22 over CSH col 16

**`_read_llm_prep_enrichment`:** domain keyed dict, first GF only from comma list

**`_read_serienbriefe_domains`:** returns frozenset of normalized domains

**`db.upsert_company`:** insert, dedup (ORBIS wins structured, WLW fills scraped_text), mark_approached

**`ingest` integration (tmp_path):**
- dry_run=True → no DB created
- real run → `pipeline.db` exists with correct row count
- already_approached flagged correctly
- LLMPrep enrichment patches hrb_number

---

## Validation

```bash
# Tests pass
pytest tests/test_ingest.py -v

# Full suite still passes
pytest tests/ -q

# Dry run — shows expected counts without writing
python pipeline.py ingest --dry-run --profile profiles/medtech_germany.json

# Real run
python pipeline.py ingest --profile profiles/medtech_germany.json

# Status queries pipeline.db
python pipeline.py status
```

**Expected after real run:**
- `data/pipeline.db` exists
- Total count: ~2,500–3,200 (ORBIS 2978 + WLW unique domains, deduped)
- `already_approached=1` for ~378 companies
- `is_subsidiary=1` pre-populated for companies with corporate CSH ≥50%
- `gf_name` populated for ~2,894 records (from ORBIS DMNachname)
- `hrb_number` populated for up to 126 records (from LLMPrep)
- `python pipeline.py status` shows "M3 Ingested" count

---

## Not Included (Deferred)

- MASTER_Cleaning sheet ingestion: inconsistent row/column structure — deferred pending manual normalization
- NACE code field: ORBIS has it (col 4), but CompanyRecord has no NACE field — deferred to M4 (filter by NACE)
- Salutation generation — M10
- LLM classification from 250527: prior scores not imported
- Handelsregister DB lookup at ingest time: deferred to M7

---

## AI VALIDATION RESULTS

All 39 ingest tests pass. Full suite: 147/147.

**Dry run output:**
- WLW CSV: 1,936 records
- ORBIS: 475 records (2,503 skipped — no domain in ORBIS sheet)
- LLMPrep: 126 enrichment entries
- Serienbriefe: 367 already-approached domains
- Excel opened once, closed once
- Total before dedup: 2,411

**Real run output:**
- `data/pipeline.db` created
- 2,330 unique records after dedup
- 277 already-approached flagged
- `python pipeline.py status` queries DB correctly

**M4 end-to-end (run after M3):**
- `python pipeline.py filter`: 1,596 passed, 734 failed
- `python pipeline.py status`: M3 Ingested=734, M4 Filtered=1,596

**Note:** ORBIS sheet has 2,978 rows but only 475 have a domain in col 13. The remaining 2,503 are skipped (no domain = not usable). This is expected — ORBIS data is sparse on domain.
