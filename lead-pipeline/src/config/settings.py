"""Global path constants and defaults. No industry-specific criteria — those live in profile JSON."""

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_INPUT_DIR = DATA_DIR / "input"
DATA_STAGING_DIR = DATA_DIR / "staging"
DATA_OUTPUT_DIR = DATA_DIR / "output"
PROFILES_DIR = BASE_DIR / "profiles"

# Scraping
SCRAPE_DELAY_SEC: float = 1.0
SCRAPE_MAX_CHARS: int = 5000

# Claude CLI — all AI calls go through CLI subprocess (OAuth, no API key).
# shutil.which finds "claude" on PATH; no hardcoded user-specific fallback.
import shutil as _shutil

CLAUDE_CMD: str = _shutil.which("claude") or "claude"

# OpenRegister.de — ownership enrichment (M7)
# Credit cost: 1 (autocomplete name search) + 10 (owners) = 11 per company
# CRITICAL: Only call for klass A or B. Never C/D/E. Never realtime=true.
import os as _os
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()
OPENREGISTER_API_KEY: str = _os.getenv("OPENREGISTER_API_KEY", "")
OPENREGISTER_BASE_URL: str = "https://api.openregister.de"

# Email verification — Abstract API (recommended, works from any IP)
# Sign up: https://www.abstractapi.com/api/email-verification-validation-api
# Free: 100/month, $9/month for 5000
ABSTRACT_API_KEY: str = _os.getenv("ABSTRACT_API_KEY", "")

# Email verification Cloud Function URL (fallback if no Abstract API key)
EMAIL_VERIFY_URL: str = _os.getenv("EMAIL_VERIFY_URL", "")
OPENREGISTER_CREDITS_PER_COMPANY: int = 11  # 1 autocomplete + 10 owners

# Corporate owners blocklist — curated list of known non-fit corporate owners
CORPORATE_OWNERS_BLOCKLIST_PATH = (
    Path(__file__).parent / "corporate_owners_blocklist.json"
)

# M2 scraper output (CSV — kept as-is, M3 reads it as input)
STAGING_WLW_RAW = DATA_STAGING_DIR / "00_wlw_raw.csv"

# Source Excel (read-only input — never written to)
SOURCE_EXCEL = DATA_INPUT_DIR / "260319_Repuro_Medtech_Targets_v3_claude.xlsx"

# Pipeline SQLite DB — primary store for all stages M3-M11
# Override via .env PIPELINE_DB_PATH for shared OneDrive setups (DBs stay local)
PIPELINE_DB_PATH = Path(_os.getenv("PIPELINE_DB_PATH", str(DATA_DIR / "pipeline.db")))

# Handelsregister (offeneregister.de export) — full local DB for M7 GF lookup
HANDELSREGISTER_DB_PATH = Path(
    _os.getenv("HANDELSREGISTER_DB_PATH", str(DATA_DIR / "handelsregister.db"))
)

# Knowledge base (WLW scrape cache)
KNOWLEDGE_BASE_PATH = Path(
    _os.getenv("KNOWLEDGE_BASE_PATH", str(DATA_DIR / "knowledge_base.db"))
)
SCRAPE_TTL_DAYS: int = 90
OWNERSHIP_TTL_DAYS: int = 180

# WLW scraper
WLW_DELAY_SEC: float = 1.5
WLW_MAX_PAGES: int = 20

# Source Excel — sheet names
ORBIS_SHEET = "ORBIS_search"
LLM_PREP_SHEET = "250527"
SERIENBRIEFE_SHEET = "Serienbriefe"

# Source Excel — ORBIS_search column indices (0-based)
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

# Source Excel — 250527 sheet column indices (0-based)
LLM_PREP_HEADER_ROW = 2  # 1-based row containing headers
LLM_PREP_COL_DOMAIN = 3
LLM_PREP_COL_NAME = 4
LLM_PREP_COL_ADDRESS = 5
LLM_PREP_COL_HRB = 6
LLM_PREP_COL_GF = 7
LLM_PREP_COL_MA = 8

# Source Excel — Serienbriefe sheet column indices (0-based)
SERIENBRIEFE_COL_DOMAIN = 2  # "Domain Name Clean"

# ALLEX branding
ALLEX_LOGO_PATH: Path = BASE_DIR / "ALLEX_logo_transparent.png"
HUBSPOT_PORTAL_ID: int = 144578192

# Letter export — sender config (client-specific branding)
SENDER_CONFIG_PATH: Path = Path(__file__).parent / "sender.json"

# Leistung category templates — dative noun phrases for letter merge fields.
# Key = category code returned by AI.
# leistung_text fits: "bei unserer Suche nach erfolgreichen [X] in [Region]"
# leistung_absatz_2 fits: "beteiligen wir uns an etablierten [X] in Deutschland"
LEISTUNG_CATEGORIES: dict[str, dict[str, str]] = {
    "medizintechnik-service": {
        "leistung_text": "Medizintechnik-Dienstleistern",
        "leistung_absatz_2": "Medizintechnik-Dienstleistern",
    },
    "medizinprodukt-handler": {
        "leistung_text": "Medizinprodukt-Händlern",
        "leistung_absatz_2": "Medizinprodukt-Händlern",
    },
    "praxisausstatter": {
        "leistung_text": "Praxisausstattern",
        "leistung_absatz_2": "Praxisausstattern",
    },
    "sprechstundenbedarf": {
        "leistung_text": "Sprechstundenbedarf-Spezialisten",
        "leistung_absatz_2": "Sprechstundenbedarf-Anbietern",
    },
    "medizintechnik-experten": {
        "leistung_text": "Medizintechnik-Experten",
        "leistung_absatz_2": "Medizintechnik-Dienstleistern",
    },
}
LEISTUNG_DEFAULT_CATEGORY = "medizintechnik-experten"

# Corporate entity keywords for subsidiary detection
CORPORATE_KEYWORDS = (
    "GmbH",
    "AG",
    "SE",
    "KG",
    " KG",
    "Corp",
    "Group",
    "Holding",
    "Inc",
    "Ltd",
    "BV",
    "NV",
    "SA",
    "SAS",
    "SRL",
    "S.A.",
    "Plc",
)
