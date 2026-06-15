# PLAN-M1: Infrastructure + Industry Profile Schema

## Context

First milestone. Nothing exists yet. We establish:
- Python project scaffold and directory structure
- CLI skeleton (`pipeline.py`) with `--profile` flag
- `IndustryProfile` dataclass — the config concept that makes this tool industry-agnostic
- `CompanyRecord` dataclass — the universal data model
- Utility modules (Excel, web helpers) with real implementations
- All pipeline modules as stubs
- Seed profile: `profiles/medtech_germany.json`
- Passing test suite

After M1: `python pipeline.py status --profile profiles/medtech_germany.json` runs and returns a clean message. No API calls made.

---

## Files to Create

```
pipeline.py                          # CLI entry point
profiles/
  medtech_germany.json               # Seed industry profile (Repuro medtech)
src/__init__.py
src/config/__init__.py
src/config/profile.py                # IndustryProfile dataclass + load_profile()
src/config/settings.py               # Path constants + global defaults only
src/pipeline/__init__.py
src/pipeline/models.py               # CompanyRecord dataclass
src/pipeline/wlw_scraper.py          # Stub
src/pipeline/ingest.py               # Stub
src/pipeline/filter.py               # Stub
src/pipeline/scrape.py               # Stub
src/pipeline/classify.py             # Stub
src/pipeline/enrich.py               # Stub
src/pipeline/export.py               # Stub
src/pipeline/dashboard.py            # Stub
src/utils/__init__.py
src/utils/excel.py                   # read_sheet, write_dataframe_to_xlsx, validate_no_formula_errors
src/utils/web.py                     # fetch_with_retry, clean_html, extract_page_text
tests/__init__.py
tests/test_models.py
tests/test_profile.py
tests/test_utils.py
tests/fixtures/
  sample_profile.json                # Minimal profile for tests
  sample.html                        # Sample HTML for clean_html tests
data/input/   (directory)
data/staging/ (directory)
data/output/  (directory)
```

---

## Implementation Sequence

### Step 1: Directory scaffold

Create all `__init__.py` files and data directories.

```
src/__init__.py               (empty)
src/config/__init__.py        (empty)
src/pipeline/__init__.py      (empty)
src/utils/__init__.py         (empty)
tests/__init__.py             (empty)
tests/fixtures/               (directory)
data/input/                   (directory)
data/staging/                 (directory)
data/output/                  (directory)
```

### Step 2: `src/config/settings.py`

Global defaults only — no industry-specific criteria.

```python
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_INPUT_DIR = DATA_DIR / "input"
DATA_STAGING_DIR = DATA_DIR / "staging"
DATA_OUTPUT_DIR = DATA_DIR / "output"
PROFILES_DIR = BASE_DIR / "profiles"

# Scraping
SCRAPE_DELAY_SEC: float = 1.0
SCRAPE_MAX_CHARS: int = 2500

# Claude API
DEFAULT_CLAUDE_MODEL: str = "claude-haiku-4-5"
QUALITY_CLAUDE_MODEL: str = "claude-sonnet-4-5"

# OpenRegister
OPENREGISTER_CALLS_PER_COMPANY: int = 3  # search + detail + owners

# Staging file paths
STAGING_WLW_RAW = DATA_STAGING_DIR / "00_wlw_raw.csv"
STAGING_INGESTED = DATA_STAGING_DIR / "01_ingested.csv"
STAGING_FILTERED = DATA_STAGING_DIR / "02_filtered.csv"
STAGING_SCRAPED = DATA_STAGING_DIR / "03_scraped.csv"
STAGING_CLASSIFIED = DATA_STAGING_DIR / "04_classified.csv"
STAGING_ENRICHED_OWNERSHIP = DATA_STAGING_DIR / "05_enriched_ownership.csv"
STAGING_OWNERSHIP_GATED = DATA_STAGING_DIR / "06_ownership_gated.csv"
STAGING_ENRICHED_EMAIL = DATA_STAGING_DIR / "07_enriched_email.csv"

# Source Excel
SOURCE_EXCEL = DATA_INPUT_DIR / "260319_Repuro_Medtech_Targets_v3_claude.xlsx"
```

### Step 3: `src/config/profile.py`

```python
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DiscoveryConfig:
    wlw_search_terms: list[str]
    wlw_base_url: str = "https://www.wer-liefert-was.de"


@dataclass
class FilterConfig:
    ma_min: int = 5
    ma_max: int = 100
    nace_exclude: list[str] = field(default_factory=list)
    name_exclude_keywords: list[str] = field(default_factory=list)


@dataclass
class ClassificationExample:
    domain: str
    full_name: str
    klass: str
    services_score: int
    service_flag: bool
    distributor_flag: bool
    ssb_flag: bool
    leistung_text: str
    reasoning: str
    scraped_text_excerpt: str = ""


@dataclass
class ClassificationConfig:
    target_description: str
    class_definitions: dict[str, str]
    examples: list[ClassificationExample] = field(default_factory=list)


@dataclass
class OwnershipConfig:
    hard_disqualify_subsidiary_threshold_pct: float = 75.0
    hard_disqualify_pe_backed: bool = True


@dataclass
class ExportConfig:
    format: str = "serienbriefe"
    region_prepositions: dict[str, str] = field(default_factory=dict)


@dataclass
class IndustryProfile:
    id: str
    name: str
    description: str
    geography: dict[str, str]
    discovery: DiscoveryConfig
    filters: FilterConfig
    classification: ClassificationConfig
    ownership: OwnershipConfig
    export: ExportConfig


def load_profile(path: Path) -> IndustryProfile:
    """Load and validate an IndustryProfile from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    discovery = DiscoveryConfig(**data["discovery"])
    filters = FilterConfig(**data["filters"])
    examples = [ClassificationExample(**e) for e in data["classification"].get("examples", [])]
    classification = ClassificationConfig(
        target_description=data["classification"]["target_description"],
        class_definitions=data["classification"]["class_definitions"],
        examples=examples,
    )
    ownership = OwnershipConfig(**data.get("ownership", {}))
    export = ExportConfig(**data.get("export", {}))

    return IndustryProfile(
        id=data["id"],
        name=data["name"],
        description=data["description"],
        geography=data["geography"],
        discovery=discovery,
        filters=filters,
        classification=classification,
        ownership=ownership,
        export=export,
    )
```

### Step 4: `src/pipeline/models.py`

```python
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime
from typing import Optional


@dataclass
class CompanyRecord:
    # Identity
    domain: str
    full_name: str
    profile_id: str
    source: str  # "WLW" / "ORBIS" / "MASTER_CLEANING" / "MANUAL"

    # Computed on creation
    id: str = field(init=False)

    # Location
    hrb_number: Optional[str] = None
    rechtsform: Optional[str] = None
    street: Optional[str] = None
    plz_ort: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None

    # Size
    ma_count: Optional[int] = None
    revenue_tsd_eur: Optional[float] = None

    # Classification
    klass: Optional[str] = None
    services_score: Optional[int] = None
    service_flag: Optional[bool] = None
    distributor_flag: Optional[bool] = None
    ssb_flag: Optional[bool] = None
    leistung_text: Optional[str] = None
    reasoning: Optional[str] = None
    compliment_draft: Optional[str] = None
    reclassify_reason: Optional[str] = None

    # Ownership
    gesellschafter_name: Optional[str] = None
    gesellschafter_share_pct: Optional[float] = None
    gesellschafter_age: Optional[int] = None
    is_subsidiary: Optional[bool] = None
    is_pe_backed: Optional[bool] = None

    # Contact
    gf_name: Optional[str] = None
    gf_email: Optional[str] = None
    gf_phone: Optional[str] = None
    anrede: Optional[str] = None
    salutation: Optional[str] = None

    # Pipeline metadata
    already_approached: bool = False
    filter_pass: Optional[bool] = None
    filter_reason: Optional[str] = None
    ownership_pass: Optional[bool] = None
    ownership_reason: Optional[str] = None
    scraped_text: Optional[str] = None
    scraped_at: Optional[datetime] = None
    classified_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        self.id = hashlib.md5(self.domain.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert datetimes to ISO strings for CSV
        for key in ("scraped_at", "classified_at", "enriched_at"):
            if d[key] is not None:
                d[key] = d[key].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CompanyRecord":
        d = dict(d)
        # Parse ISO datetime strings
        for key in ("scraped_at", "classified_at", "enriched_at"):
            if d.get(key) and d[key] not in ("", "None", None):
                d[key] = datetime.fromisoformat(str(d[key]))
            else:
                d[key] = None
        # Parse booleans stored as strings in CSV
        for key in ("already_approached", "filter_pass", "service_flag",
                    "distributor_flag", "ssb_flag", "is_subsidiary", "is_pe_backed",
                    "ownership_pass"):
            if key in d and d[key] not in (None, "", "None"):
                d[key] = str(d[key]).lower() in ("true", "1", "yes")
            elif key in d:
                d[key] = None if key != "already_approached" else False
        # Parse ints
        for key in ("ma_count", "services_score", "gesellschafter_age"):
            if key in d and d[key] not in (None, "", "None"):
                try:
                    d[key] = int(float(str(d[key])))
                except (ValueError, TypeError):
                    d[key] = None
        # Parse floats
        for key in ("revenue_tsd_eur", "gesellschafter_share_pct"):
            if key in d and d[key] not in (None, "", "None"):
                try:
                    d[key] = float(str(d[key]))
                except (ValueError, TypeError):
                    d[key] = None
        # Remove 'id' — recomputed in __post_init__
        d.pop("id", None)
        return cls(**{k: d.get(k) for k in [f.name for f in fields(cls)] if f.name != "id"})
```

### Step 5: `src/utils/excel.py`

```python
import logging
from pathlib import Path
from typing import Optional
import pandas as pd
import openpyxl

logger = logging.getLogger(__name__)

FORMULA_ERROR_STRINGS = ("#REF!", "#DIV/0!", "#NAME?", "#VALUE!", "#NULL!", "#N/A", "#NUM!")


def read_sheet(path: Path, sheet_name: str, header_row: int = 0) -> pd.DataFrame:
    """Read an Excel sheet into a DataFrame."""
    return pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=header_row,
        engine="openpyxl",
    )


def write_dataframe_to_xlsx(df: pd.DataFrame, path: Path, sheet_name: str = "Sheet1") -> None:
    """Write a DataFrame to an Excel file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, sheet_name=sheet_name, engine="openpyxl")
    logger.info("Wrote %d rows to %s", len(df), path)


def validate_no_formula_errors(path: Path) -> bool:
    """Return True if the workbook contains no formula error strings."""
    wb = openpyxl.load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and any(
                    err in cell.value for err in FORMULA_ERROR_STRINGS
                ):
                    logger.warning("Formula error found at %s!%s: %s", ws.title, cell.coordinate, cell.value)
                    return False
    return True
```

### Step 6: `src/utils/web.py`

```python
import logging
import time
from typing import Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def fetch_with_retry(
    url: str,
    retries: int = 3,
    delay: float = 1.0,
    timeout: int = 10,
) -> Optional[str]:
    """Fetch URL with retry. Returns HTML string or None on failure."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RepuroBot/1.0)"}
    for attempt in range(retries):
        try:
            response = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 410):
                logger.debug("404/410 for %s — skipping", url)
                return None
            logger.warning("HTTP %d for %s (attempt %d/%d)", e.response.status_code, url, attempt + 1, retries)
        except (httpx.RequestError, httpx.TimeoutException) as e:
            logger.warning("Request error for %s: %s (attempt %d/%d)", url, e, attempt + 1, retries)
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def clean_html(html: str) -> str:
    """Strip HTML tags, remove nav/footer boilerplate, normalize whitespace."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["nav", "footer", "header", "script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    # Normalize whitespace while preserving umlauts
    lines = [line.strip() for line in text.splitlines()]
    return " ".join(part for line in lines for part in [line] if part)


def extract_page_text(
    domain: str,
    extra_paths: Optional[list[str]] = None,
    max_chars: int = 2500,
) -> str:
    """Fetch text from domain homepage + extra_paths, combined up to max_chars."""
    if extra_paths is None:
        extra_paths = ["/leistungen", "/service", "/produkte", "/ueber-uns"]

    base_url = f"https://{domain}"
    collected: list[str] = []
    total = 0

    for path in [""] + extra_paths:
        if total >= max_chars:
            break
        url = base_url + path
        html = fetch_with_retry(url)
        if html:
            text = clean_html(html)
            remaining = max_chars - total
            collected.append(text[:remaining])
            total += len(text[:remaining])

    return " ".join(collected)[:max_chars]
```

### Step 7: Stub pipeline modules

Each stub raises `NotImplementedError` with a descriptive message so that `--dry-run` works without crashing.

Pattern for all stubs:
```python
# src/pipeline/ingest.py
import logging
from src.config.profile import IndustryProfile
from src.pipeline.models import CompanyRecord

logger = logging.getLogger(__name__)


def ingest(profile: IndustryProfile, dry_run: bool = False, verbose: bool = False) -> int:
    """Load all source data, normalize, deduplicate. Returns record count."""
    raise NotImplementedError("ingest not implemented — M3")
```

Apply same pattern to: `wlw_scraper.py`, `filter.py`, `scrape.py`, `classify.py`, `enrich.py`, `export.py`, `dashboard.py`.

Each stub must import cleanly (no import errors).

### Step 8: `pipeline.py` (CLI)

```python
#!/usr/bin/env python3
"""Repuro Lead Generation Pipeline — CLI entry point."""
import argparse
import logging
import sys
from pathlib import Path

from src.config.profile import load_profile
from src.config import settings


def cmd_status(args: argparse.Namespace) -> None:
    """Show current pipeline state."""
    staging_files = [
        (settings.STAGING_WLW_RAW, "00 WLW raw"),
        (settings.STAGING_INGESTED, "01 Ingested"),
        (settings.STAGING_FILTERED, "02 Filtered"),
        (settings.STAGING_SCRAPED, "03 Scraped"),
        (settings.STAGING_CLASSIFIED, "04 Classified"),
        (settings.STAGING_ENRICHED_OWNERSHIP, "05 Ownership enriched"),
        (settings.STAGING_OWNERSHIP_GATED, "06 Ownership gated"),
        (settings.STAGING_ENRICHED_EMAIL, "07 Email enriched"),
    ]
    found = False
    for path, label in staging_files:
        if path.exists():
            import pandas as pd
            df = pd.read_csv(path, encoding="utf-8")
            print(f"  {label}: {len(df)} records")
            if "klass" in df.columns:
                breakdown = df["klass"].value_counts().to_dict()
                print(f"    Klass breakdown: {breakdown}")
            found = True
    if not found:
        print("No staging files found. Run 'python pipeline.py scrape-wlw' to start.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repuro Lead Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("profiles/medtech_germany.json"),
        help="Path to industry profile JSON (default: profiles/medtech_germany.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="No API calls, no writes")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N records")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("scrape-wlw", help="Scrape wer-liefert-was.de for leads")
    subparsers.add_parser("ingest", help="Normalize and deduplicate all sources")
    subparsers.add_parser("filter", help="Apply pre-qualification filters")
    subparsers.add_parser("scrape", help="Scrape company websites")
    subparsers.add_parser("classify", help="AI classification via Claude API")
    subparsers.add_parser("enrich", help="Ownership + email enrichment")
    subparsers.add_parser("export", help="Generate Serienbriefe Excel output")
    subparsers.add_parser("dashboard", help="Generate HTML dashboard")
    subparsers.add_parser("run-all", help="Full pipeline end-to-end")
    subparsers.add_parser("status", help="Show pipeline state and counts")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "status":
        cmd_status(args)
        return

    # Load and validate profile for all other commands
    profile = load_profile(args.profile)
    logging.getLogger(__name__).info("Profile: %s", profile.name)

    if args.command == "scrape-wlw":
        from src.pipeline.wlw_scraper import scrape_wlw
        scrape_wlw(profile, dry_run=args.dry_run)
    elif args.command == "ingest":
        from src.pipeline.ingest import ingest
        ingest(profile, dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == "filter":
        from src.pipeline.filter import apply_hard_filters
        apply_hard_filters(profile=profile, dry_run=args.dry_run)
    elif args.command == "scrape":
        from src.pipeline.scrape import scrape_batch_cmd
        scrape_batch_cmd(profile, dry_run=args.dry_run, limit=args.limit)
    elif args.command == "classify":
        from src.pipeline.classify import classify_cmd
        classify_cmd(profile, dry_run=args.dry_run, limit=args.limit)
    elif args.command == "enrich":
        from src.pipeline.enrich import enrich_cmd
        enrich_cmd(profile, dry_run=args.dry_run)
    elif args.command == "export":
        from src.pipeline.export import export_cmd
        export_cmd(profile, dry_run=args.dry_run)
    elif args.command == "dashboard":
        from src.pipeline.dashboard import dashboard_cmd
        dashboard_cmd(profile, dry_run=args.dry_run)
    elif args.command == "run-all":
        print("run-all not yet implemented — run stages individually.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Step 9: `profiles/medtech_germany.json`

Seed profile for Repuro medtech use case. Examples to be populated from LLM_prep1 sheet in M3.

```json
{
  "id": "medtech_germany",
  "name": "German Ambulatory Medtech Distributors",
  "description": "M&A targets: Medizintechnik/Sprechstundenbedarf distributors for German ambulatory care (GP, surgeon, OB-GYN). Service + distribution mix, 20-80 employees, private ownership.",
  "geography": {
    "country": "DE"
  },
  "discovery": {
    "wlw_search_terms": [
      "Sprechstundenbedarf",
      "Medizintechnik",
      "Praxisbedarf",
      "Medizinischer Bedarf"
    ],
    "wlw_base_url": "https://www.wer-liefert-was.de"
  },
  "filters": {
    "ma_min": 5,
    "ma_max": 100,
    "nace_exclude": ["4774"],
    "name_exclude_keywords": [
      "zahn", "dental", "dent", "mund", "kieferorthop",
      "apotheke", "pharma",
      "krankenhaus", "klinik", "hospital"
    ]
  },
  "classification": {
    "target_description": "Distributes medical supplies/devices to ambulatory practices (GP, surgeon, OB-GYN, Dermatology) AND provides service (equipment maintenance, hygiene management, installation, Sprechstundenbedarf supply). SSB distribution is a strong positive signal — recurring revenue, high customer stickiness. Target: 20-80 employees, privately owned GmbH, not hospital-only, not dental-only.",
    "class_definitions": {
      "A": "Platform candidate: clear service + distribution mix, 20-80 employees, private ownership, regional or multi-regional footprint",
      "B": "Add-on: fits criteria but smaller scale (5-20 MA) or weaker service component",
      "C": "Unclear: vague website, ambiguous customer base, or insufficient data to classify",
      "D": "No-fit: dental-only, pharmacy, hospital-only, pure OEM, subsidiary of large group, PE-backed, >100 employees, dissolved",
      "E": "Special case: interesting but outside standard criteria — flag for manual review"
    },
    "examples": []
  },
  "ownership": {
    "hard_disqualify_subsidiary_threshold_pct": 75.0,
    "hard_disqualify_pe_backed": true
  },
  "export": {
    "format": "serienbriefe",
    "region_prepositions": {
      "Bayern": "in",
      "Nordrhein-Westfalen": "in",
      "Baden-Württemberg": "in",
      "Berlin": "in",
      "Hamburg": "in",
      "Bremen": "in",
      "Sachsen": "in",
      "Thüringen": "in",
      "Hessen": "in",
      "Niedersachsen": "in",
      "Rheinland-Pfalz": "in",
      "Saarland": "im",
      "Schleswig-Holstein": "in",
      "Mecklenburg-Vorpommern": "in",
      "Brandenburg": "in",
      "Sachsen-Anhalt": "in",
      "Sachsen-Anhalt": "in",
      "Oberpfalz": "in der",
      "Mittelrhein": "am"
    }
  }
}
```

### Step 10: Test files

**`tests/fixtures/sample_profile.json`**: minimal valid profile for tests.

**`tests/test_models.py`**:
- `CompanyRecord` creation with required fields
- `to_dict()` → `from_dict()` round-trip preserves all fields
- All Optional fields default to None
- `id` is correctly computed from domain
- `already_approached` defaults to False

**`tests/test_profile.py`**:
- `load_profile()` loads `profiles/medtech_germany.json` without error
- Profile has correct `id`, non-empty `discovery.wlw_search_terms`
- `FilterConfig` has correct defaults
- `load_profile()` raises on missing file (FileNotFoundError)

**`tests/test_utils.py`**:
- `clean_html()` strips `<nav>`, `<footer>`, `<script>` tags
- `clean_html()` preserves umlauts (ä, ö, ü, Ä, Ö, Ü, ß)
- `clean_html()` handles empty string
- `read_sheet()` with a small test Excel fixture

---

## Validation

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests — must pass with 0 failures
pytest tests/ -v

# CLI help
python pipeline.py --help

# Status (no staging files yet)
python pipeline.py status
# Expected: "No staging files found. Run 'python pipeline.py scrape-wlw' to start."

# Profile loads cleanly
python pipeline.py status --profile profiles/medtech_germany.json

# Dry-run on all commands that would hit APIs
python pipeline.py scrape-wlw --dry-run
python pipeline.py classify --dry-run
python pipeline.py enrich --dry-run
```

Expected: 0 test failures, no import errors, `status` returns clean message.

---

## AI VALIDATION RESULTS

- `pytest tests/ -v` → **37 passed, 0 failed** (0.87s)
- `python pipeline.py status` → "No staging files found. Run 'python pipeline.py scrape-wlw' to start."
- `python pipeline.py --help` → all 10 subcommands listed correctly
- `python pipeline.py --dry-run classify` → profile loads, DRY RUN logged, NotImplementedError returned (expected)
- All imports clean — no import errors across any module
- Python 3.13.1, pytest 9.0.2

---

## Not Included (Deferred to M2+)

- WLW scraper implementation (M2)
- Data ingestion from Excel (M3)
- Real API calls (M6+)
- Few-shot examples population — done in M3 from LLM_prep1 sheet
- Web scraping implementation (M5)
- Dashboard HTML (M11)
