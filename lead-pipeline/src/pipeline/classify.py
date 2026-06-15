"""AI classifier (M6). Classifies company website text via Claude CLI."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import settings
from src.config.profile import ClassificationExample, IndustryProfile
from src.pipeline import db as pipeline_db

logger = logging.getLogger(__name__)

_RETRY_DELAY_S = 2.0
_MAX_RETRIES = 3


# Keyword pre-filter — obvious non-medtech sectors that should auto-D without a Claude call.
# Keep this list narrow: only add terms where false-positive risk is essentially zero.
_AUTO_D_KEYWORDS = [
    "solar",
    "photovoltaik",
    "maler",
    "malerbetrieb",
    "lackier",
    "dachdecker",
    "dachdeckerei",
    "sanitär",
    "klempner",
    "heizungsbau",
    "elektroinstallation",
    "elektriker",
    "schlüsseldienst",
    "reinigung",
    "gebäudereinigung",
    "gartenbau",
    "landschaft",
    "autowerkstatt",
    "kfz-werkstatt",
    "fahrzeug",
    "möbel",
    "küchen",
    "inneneinrichtung",
    "coaching",
    "personal training",
    "fitness",
    "yoga",
    "immobilien",
    "versicherung",
    "steuerberater",
    "rechtsanwalt",
    "anwaltskanzlei",
    "werbeagentur",
    "webdesign",
    "druckerei",
    "reisebüro",
]

# Predefined reason codes for D/E classifications — short, structured, token-efficient.
_REASON_CODES = [
    "Unpassende_Branche",  # completely wrong sector
    "Handwerk",  # tradesperson / installer
    "Dental",  # dental-only
    "Apotheke",  # pharmacy
    "Krankenhaus",  # hospital / inpatient only
    "OEM_Hersteller",  # manufacturer, not distributor/service
    "Zu_Gross",  # >100 employees
    "Zu_Klein",  # <5 employees
    "Ausland",  # outside DACH
    "Tochtergesellschaft",  # confirmed subsidiary
    "Kein_Service",  # pure distribution, no service component
    "PE_backed",  # PE-owned
    "Unklares_Profil",  # can't determine from available text
    "Passt",  # used for A/B/C — fits criteria
]


# ---------------------------------------------------------------------------
# Pre-filter
# ---------------------------------------------------------------------------


def _is_obvious_d(scraped_text: str, full_name: str) -> tuple[bool, str]:
    """Return (True, reason_code) if company is obviously non-medtech. Fast, free."""
    combined = (scraped_text + " " + full_name).lower()
    for kw in _AUTO_D_KEYWORDS:
        if kw in combined:
            return True, "Handwerk" if kw in (
                "maler",
                "dachdecker",
                "sanitär",
                "klempner",
                "heizungsbau",
                "elektroinstallation",
                "elektriker",
            ) else "Unpassende_Branche"
    return False, ""


# ---------------------------------------------------------------------------
# Name-based duplicate detection
# ---------------------------------------------------------------------------

_LEGAL_FORMS = re.compile(
    r"\b(gmbh\s*&\s*co\.?\s*kg|gmbh\s*&\s*co|gmbh|ag|se|kg|gbr|ohg|e\.k\.|e\.v\.|ug|inc|ltd|bv|nv|sa|sas|srl|plc|corp|group|holding|gesellschaft|mbh)\b",
    re.IGNORECASE,
)


def _normalize_company_name(name: str) -> str:
    """Normalize company name for duplicate detection.

    Lowercases, strips legal form suffixes, punctuation, and extra whitespace.
    Returns empty string for empty input.
    """
    if not name:
        return ""
    s = name.lower()
    s = _LEGAL_FORMS.sub("", s)
    s = re.sub(r"[^a-z0-9äöüß]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_name_index(db_path: Path) -> dict[str, tuple[str, str]]:
    """Return {normalized_name: (klass, domain)} for all already-classified records."""
    index: dict[str, tuple[str, str]] = {}
    with pipeline_db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT domain, full_name, klass FROM company_records WHERE klass IS NOT NULL"
        ).fetchall()
    for row in rows:
        key = _normalize_company_name(row["full_name"])
        if key and len(key) >= 4:  # ignore very short keys (noise)
            index[key] = (row["klass"], row["domain"])
    return index


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _select_examples(
    examples: list[ClassificationExample],
    n_per_class: dict[str, int] | None = None,
) -> list[ClassificationExample]:
    """Select few-shot examples: 2×A, 1×B, 1×D by default."""
    if n_per_class is None:
        n_per_class = {"A": 2, "B": 1, "D": 1}
    selected: list[ClassificationExample] = []
    by_klass: dict[str, list[ClassificationExample]] = {}
    for ex in examples:
        by_klass.setdefault(ex.klass, []).append(ex)
    for klass, n in n_per_class.items():
        pool = by_klass.get(klass, [])
        if pool:
            selected.extend(random.sample(pool, min(n, len(pool))))
    return selected


def _format_example(ex: ClassificationExample) -> str:
    text_part = (
        f"\nWebsite: {ex.scraped_text_excerpt[:300]}" if ex.scraped_text_excerpt else ""
    )
    return (
        f"Company: {ex.full_name} ({ex.domain}){text_part}\n"
        f'Output: {{"klass": "{ex.klass}", "services_score": {ex.services_score}, '
        f'"service_flag": {str(ex.service_flag).lower()}, '
        f'"distributor_flag": {str(ex.distributor_flag).lower()}, '
        f'"ssb_flag": {str(ex.ssb_flag).lower()}, '
        f'"leistung_text": "{ex.leistung_text}", '
        f'"reason_code": "Passt", '
        f'"reasoning": "{ex.reasoning[:100]}"}}'
    )


def _build_prompt(
    profile: IndustryProfile,
    full_name: str,
    domain: str,
    city: Optional[str],
    region: Optional[str],
    ma_count: Optional[int],
    scraped_text: Optional[str],
) -> str:
    class_defs = "\n".join(
        f"{k} = {v}" for k, v in profile.classification.class_definitions.items()
    )
    examples_selected = _select_examples(profile.classification.examples)
    examples_text = "\n\n".join(_format_example(e) for e in examples_selected)
    text_block = (scraped_text or "")[:2000]
    location = ", ".join(filter(None, [city, region])) or "unbekannt"
    ma_str = str(ma_count) if ma_count is not None else "unbekannt"
    reason_codes = " | ".join(_REASON_CODES)

    return f"""Classify this German company as an M&A target for ambulatory medtech buy-and-build.

Target: {profile.classification.target_description}

Classes:
{class_defs}

Reason codes (pick exactly one): {reason_codes}

Examples:
{examples_text}

---
Company: {full_name} ({domain})
Location: {location} | Employees: {ma_str}
Website:
{text_block}
---

Return JSON only:
{{
  "klass": "A|B|C|D|E",
  "services_score": 0-100,
  "service_flag": true|false,
  "distributor_flag": true|false,
  "ssb_flag": true|false,
  "leistung_category": "one of: medizintechnik-service | medizinprodukt-handler | praxisausstatter | sprechstundenbedarf | medizintechnik-experten",
  "mehrwerte": "German dative noun phrase (NO full sentences) that completes: 'Wir unterstuetzen insbesondere bei ___'. Example: 'der Optimierung von Einkaufsprozessen und der Erschliessung neuer Vertriebswege'. Max 120 chars.",
  "reason_code": "one of the reason codes above",
  "reasoning": "max 1 sentence explaining the classification"
}}"""


# ---------------------------------------------------------------------------
# API / CLI calls
# ---------------------------------------------------------------------------


def _call_claude_cli(prompt: str) -> dict:
    """Call Claude via CLI subprocess (OAuth auth, no API key needed)."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    for attempt in range(_MAX_RETRIES):
        try:
            result = subprocess.run(
                [settings.CLAUDE_CMD, "-p", "--output-format", "text"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
                env=env,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"claude CLI exited {result.returncode}: {result.stderr[:200]}"
                )
            raw = result.stdout.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(
                "CLI JSON parse error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, e
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)
        except subprocess.TimeoutExpired:
            logger.warning("CLI timeout (attempt %d/%d)", attempt + 1, _MAX_RETRIES)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)
        except Exception as e:
            logger.warning(
                "CLI error (attempt %d/%d): %s", attempt + 1, _MAX_RETRIES, e
            )
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_S)
    raise RuntimeError(f"claude CLI failed after {_MAX_RETRIES} attempts")


def _parse_result(raw: dict) -> dict:
    """Normalize and validate classifier JSON output."""
    klass = str(raw.get("klass", "C")).upper()
    if klass not in ("A", "B", "C", "D", "E"):
        klass = "C"
    reason_code = str(raw.get("reason_code", "Unklares_Profil"))
    if reason_code not in _REASON_CODES:
        reason_code = "Unklares_Profil"
    # Resolve leistung_category to dative noun phrases for letter merge fields
    cat = str(raw.get("leistung_category", "")).strip().lower()
    mapping = settings.LEISTUNG_CATEGORIES.get(
        cat, settings.LEISTUNG_CATEGORIES[settings.LEISTUNG_DEFAULT_CATEGORY]
    )

    return {
        "klass": klass,
        "services_score": int(raw.get("services_score", 0)),
        "service_flag": bool(raw.get("service_flag", False)),
        "distributor_flag": bool(raw.get("distributor_flag", False)),
        "ssb_flag": bool(raw.get("ssb_flag", False)),
        "leistung_text": mapping["leistung_text"],
        "leistung_absatz_2": mapping["leistung_absatz_2"],
        "mehrwerte": str(raw.get("mehrwerte", ""))[:400],
        "reason_code": reason_code,
        "reasoning": str(raw.get("reasoning", ""))[:200],
    }


# ---------------------------------------------------------------------------
# Main classify command
# ---------------------------------------------------------------------------


def classify_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Path | None = None,
) -> int:
    """Classify all scraped records. Returns count of successfully classified records.

    Pre-filters obvious non-medtech companies (free, no Claude call).
    Remaining companies sent to Claude CLI.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH

    records = pipeline_db.get_records_for_classify(db_path)
    if limit > 0:
        records = records[:limit]

    total = len(records)
    logger.info("Classify: %d scraped records to process (limit=%d)", total, limit)

    if dry_run:
        logger.info("DRY RUN — would classify %d records (no API calls)", total)
        return 0

    if not records:
        logger.info("Classify: nothing to do (no scraped records)")
        return 0

    if not profile.classification.examples:
        logger.warning(
            "Profile has no few-shot examples — classification quality will be lower"
        )

    logger.info("Using claude CLI at: %s", settings.CLAUDE_CMD)

    classified = 0
    pre_filtered = 0
    name_dupes = 0
    errors = 0

    # Build name index from already-classified records for duplicate detection
    name_index = _build_name_index(db_path)
    logger.debug(
        "Name index: %d classified companies for duplicate check", len(name_index)
    )

    for i, rec in enumerate(records, 1):
        now = datetime.now(timezone.utc).isoformat()
        try:
            # --- Pre-filter: obvious non-medtech → auto-D, no Claude call ---
            is_d, auto_reason = _is_obvious_d(rec.scraped_text or "", rec.full_name)
            if is_d:
                result = {
                    "klass": "D",
                    "services_score": 0,
                    "service_flag": False,
                    "distributor_flag": False,
                    "ssb_flag": False,
                    "leistung_text": "",
                    "leistung_absatz_2": "",
                    "mehrwerte": "",
                    "reason_code": auto_reason,
                    "reasoning": "Auto-D: keyword match, clearly non-medtech.",
                }
                pre_filtered += 1
                logger.debug(
                    "[%d/%d] AUTO-D: %s (%s)", i, total, rec.domain, auto_reason
                )
            else:
                # --- Name-based duplicate check → copy klass, no Claude call ---
                name_key = _normalize_company_name(rec.full_name)
                dupe_match = name_index.get(name_key) if name_key else None
                if dupe_match:
                    dupe_klass, dupe_domain = dupe_match
                    result = {
                        "klass": dupe_klass,
                        "services_score": 0,
                        "service_flag": False,
                        "distributor_flag": False,
                        "ssb_flag": False,
                        "leistung_text": "",
                        "leistung_absatz_2": "",
                        "mehrwerte": "",
                        "reason_code": "Passt"
                        if dupe_klass in ("A", "B", "C", "E")
                        else "Unklares_Profil",
                        "reasoning": f"Duplicate name: same company as {dupe_domain} (klass {dupe_klass}).",
                    }
                    name_dupes += 1
                    logger.debug(
                        "[%d/%d] NAME-DUPE: %s -> %s (same as %s)",
                        i,
                        total,
                        rec.domain,
                        dupe_klass,
                        dupe_domain,
                    )
                else:
                    # --- Claude classification ---
                    prompt = _build_prompt(
                        profile=profile,
                        full_name=rec.full_name,
                        domain=rec.domain,
                        city=rec.city,
                        region=rec.region,
                        ma_count=rec.ma_count,
                        scraped_text=rec.scraped_text,
                    )
                    raw = _call_claude_cli(prompt)
                    result = _parse_result(raw)

            with pipeline_db.get_connection(db_path) as conn:
                rows_updated = pipeline_db.update_classify_result(
                    conn,
                    domain=rec.domain,
                    klass=result["klass"],
                    services_score=result["services_score"],
                    service_flag=result["service_flag"],
                    distributor_flag=result["distributor_flag"],
                    ssb_flag=result["ssb_flag"],
                    leistung_text=result["leistung_text"],
                    leistung_absatz_2=result["leistung_absatz_2"],
                    mehrwerte=result["mehrwerte"],
                    reason_code=result["reason_code"],
                    reasoning=result["reasoning"],
                    classified_at=now,
                )
            if rows_updated == 0:
                logger.error(
                    "DB WRITE MISS: domain '%s' not found in company_records",
                    rec.domain,
                )
                errors += 1
            else:
                classified += 1
                logger.debug(
                    "[%d/%d] %s → %s (%s)",
                    i,
                    total,
                    rec.domain,
                    result["klass"],
                    result["reason_code"],
                )

        except Exception as e:
            errors += 1
            logger.error("[%d/%d] FAILED: %s — %s", i, total, rec.domain, e)

        if i % 50 == 0:
            logger.info(
                "Classify progress: %d/%d — %d classified (%d auto-D, %d name-dupe), %d errors",
                i,
                total,
                classified,
                pre_filtered,
                name_dupes,
                errors,
            )

    claude_calls = classified - pre_filtered - name_dupes
    logger.info(
        "Classify complete: %d classified (%d auto-D, %d name-dupe, %d Claude calls), %d errors",
        classified,
        pre_filtered,
        name_dupes,
        claude_calls,
        errors,
    )
    return classified
