"""AI classifier (M6). Classifies company website text via Claude CLI."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import tempfile
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


def _cli_argv(model: Optional[str] = None, extra_args: Optional[list[str]] = None) -> list[str]:
    """Claude CLI argv. No model and no extra args = the pre-M37 argv, byte for byte."""
    argv = [settings.CLAUDE_CMD, "-p", "--output-format", "text"]
    if model:
        argv += ["--model", model]
    if extra_args:
        argv += list(extra_args)
    return argv


def _call_claude_cli(
    prompt: str,
    model: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
    cwd: Optional[str] = None,
    lenient_json: bool = False,
) -> dict:
    """Call Claude via CLI subprocess (OAuth auth, no API key needed).

    M37: model / extra_args / cwd are optional and only change the call when given.
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    for attempt in range(_MAX_RETRIES):
        try:
            result = subprocess.run(
                _cli_argv(model, extra_args),
                cwd=cwd,
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
            if lenient_json:
                # M37 (OEM only): model put prose around the JSON object
                start, end = raw.find("{"), raw.rfind("}")
                if start >= 0 and end > start:
                    raw = raw[start : end + 1]
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
    model: Optional[str] = None,
    workers: int = 1,
    rescan: bool = False,
) -> int:
    """Classify all scraped records. Returns count of successfully classified records.

    Pre-filters obvious non-medtech companies (free, no Claude call).
    Remaining companies sent to Claude CLI.

    M37: a profile with classification.mode == "oem" runs classify_oem_cmd instead (writes
    klass_oem only). model is passed to the CLI only when given; workers / rescan apply to OEM.
    """
    if profile.classification.mode == "oem":
        return classify_oem_cmd(
            profile,
            dry_run=dry_run,
            limit=limit,
            db_path=db_path,
            model=model,
            workers=workers,
            rescan=rescan,
        )
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
                    raw = _call_claude_cli(prompt, model=model)
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


# ---------------------------------------------------------------------------
# M37: OEM profile (D1 light / D2 heavy / C / D) - writes klass_oem only
# ---------------------------------------------------------------------------

_OEM_DEFAULT_REASON_CODES = [
    "Eigenmarke_Zukauf",
    "Private_Label",
    "Montage_Konfektion",
    "Eigene_Fertigung",
    "Werk_Reinraum",
    "Produktionsmodell_unklar",
    "Unpassende_Branche",
    "Dental",
    "Apotheke",
    "Krankenhaus",
    "Kein_Hersteller",
    "Pharma",
    "Software",
    "Ausland",
    "Tochtergesellschaft",
]
_OEM_DEFAULT_PER_CLASS = {"D1": 2, "D2": 2, "C": 1, "D": 1}
_OEM_FALLBACK_KLASS = "C"  # bias rule: unknown or missing class -> C, never D2
_OEM_FALLBACK_REASON = "Produktionsmodell_unklar"
_OEM_EXAMPLE_EXCERPT_CHARS = 400

# CLI overhead flags for OEM mode only (measured 10.11.2026 with --model haiku, see DESIGN.md):
# no MCP servers, no tools, no session file, no user/project settings, neutral cwd (no CLAUDE.md
# auto-discovery). 16.5-18.7 s per call vs 23.4-40.4 s without. Never --bare (needs an API key).
_OEM_CLI_EXTRA_ARGS: list[str] = [
    "--strict-mcp-config",
    "--tools",
    "",
    "--no-session-persistence",
    "--setting-sources",
    "",
]
_OEM_CLI_CWD: str = tempfile.gettempdir()


def _norm_domain(domain: Optional[str]) -> str:
    d = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    if d.startswith("www."):
        d = d[4:]
    return d.split("/")[0]


def _select_oem_examples(
    examples: list[ClassificationExample],
    exclude_domain: Optional[str],
    per_class: Optional[dict[str, int]] = None,
    seed: Optional[str] = None,
) -> list[ClassificationExample]:
    """Few-shot set per OEM class with leave-one-out: never the record's own example.

    Deterministic per seed (the record's domain), so a re-run shows the same examples.
    """
    per_class = per_class or _OEM_DEFAULT_PER_CLASS
    own = _norm_domain(exclude_domain)
    rng = random.Random(seed or own or "oem")
    selected: list[ClassificationExample] = []
    for klass, n in per_class.items():
        pool = [e for e in examples if e.klass == klass and _norm_domain(e.domain) != own]
        if pool:
            selected.extend(rng.sample(pool, min(n, len(pool))))
    return selected


def _format_oem_example(ex: ClassificationExample) -> str:
    excerpt = (ex.scraped_text_excerpt or "")[:_OEM_EXAMPLE_EXCERPT_CHARS]
    text_part = f"\nWebsite: {excerpt}" if excerpt else ""
    out = {
        "klass_oem": ex.klass,
        "reason_code": ex.reason_code or _OEM_FALLBACK_REASON,
        "reasoning": ex.reasoning[:160],
    }
    return (
        f"Company: {ex.full_name} ({ex.domain}){text_part}\n"
        f"Output: {json.dumps(out, ensure_ascii=False)}"
    )


def _build_oem_prompt(
    profile: IndustryProfile,
    full_name: str,
    domain: str,
    city: Optional[str],
    scraped_text: Optional[str],
) -> str:
    """OEM prompt: class definitions, D2 rule, reason codes, leave-one-out few-shot, text cap."""
    cls = profile.classification
    class_defs = "\n".join(f"{k} = {v}" for k, v in cls.class_definitions.items())
    reason_codes = " | ".join(cls.reason_codes or _OEM_DEFAULT_REASON_CODES)
    examples = _select_oem_examples(
        cls.examples,
        exclude_domain=domain,
        per_class=cls.examples_per_class or None,
        seed=domain,
    )
    examples_text = "\n\n".join(_format_oem_example(e) for e in examples)
    text_block = (scraped_text or "")[: cls.max_text_chars]
    location = city or "unbekannt"
    return f"""Classify this German company by its production model (OEM-light vs OEM-heavy).

Target: {cls.target_description}

Classes:
{class_defs}

Rule: {cls.rule}

Reason codes (pick exactly one): {reason_codes}

Examples:
{examples_text}

---
Company: {full_name} ({domain})
Location: {location}
Website:
{text_block}
---

Return JSON only, no prose:
{{"klass_oem": "D1|D2|C|D", "reason_code": "one of the reason codes above", "reasoning": "one sentence citing the production evidence from the text"}}"""


def _parse_oem_result(raw: dict) -> dict[str, str]:
    """Normalize OEM output. Unknown or missing class -> C (bias rule)."""
    klass = str(raw.get("klass_oem") or raw.get("klass") or "").strip().upper()
    if klass not in pipeline_db.OEM_CLASSES:
        klass = _OEM_FALLBACK_KLASS
    reason_code = str(raw.get("reason_code") or "").strip()
    if reason_code not in _OEM_DEFAULT_REASON_CODES:
        reason_code = _OEM_FALLBACK_REASON
    reasoning = " ".join(str(raw.get("reasoning") or "").split())[:240]
    return {
        "klass_oem": klass,
        "reason_code": reason_code,
        "klass_oem_reason": f"{reason_code}: {reasoning}" if reasoning else reason_code,
    }


def classify_oem_one(
    profile: IndustryProfile,
    full_name: str,
    domain: str,
    city: Optional[str],
    scraped_text: Optional[str],
    model: Optional[str] = None,
) -> dict[str, str]:
    """Classify one company under the OEM profile (one CLI call). No DB access."""
    prompt = _build_oem_prompt(profile, full_name, domain, city, scraped_text)
    raw = _call_claude_cli(
        prompt,
        model=model,
        extra_args=_OEM_CLI_EXTRA_ARGS or None,
        cwd=_OEM_CLI_CWD,
        lenient_json=True,
    )
    return _parse_oem_result(raw)


def classify_oem_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Path | None = None,
    model: Optional[str] = None,
    workers: int = 1,
    rescan: bool = False,
) -> int:
    """M37: classify under the OEM profile. Writes klass_oem + klass_oem_reason only.

    No keyword auto-D, no name-dupe copy (both copy the ambulatory klass). pipeline_stage,
    klass, prio and classified_at are never written. CLI calls run in a pool of `workers`;
    DB writes happen on the main thread. Returns count classified.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if not dry_run:
        pipeline_db.ensure_schema(db_path)

    records = pipeline_db.get_records_for_oem_classify(db_path, rescan=rescan)
    if limit > 0:
        records = records[:limit]
    total = len(records)
    logger.info(
        "OEM classify: %d records (rescan=%s, limit=%d, model=%s, workers=%d)",
        total,
        rescan,
        limit,
        model or "CLI default",
        workers,
    )
    if dry_run:
        logger.info("DRY RUN - would classify %d records (no CLI calls, no writes)", total)
        return 0
    if not records:
        return 0
    if not profile.classification.examples:
        logger.warning("OEM profile has no few-shot examples")

    counts: dict[str, int] = {k: 0 for k in pipeline_db.OEM_CLASSES}
    classified = 0
    errors = 0

    def _job(rec: dict) -> dict[str, str]:
        return classify_oem_one(
            profile,
            rec["full_name"],
            rec["domain"],
            rec.get("city"),
            rec["scraped_text"],
            model,
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_job, rec): rec["domain"] for rec in records}
        for i, fut in enumerate(as_completed(futures), 1):
            domain = futures[fut]
            try:
                result = fut.result()
                with pipeline_db.get_connection(db_path) as conn:
                    n = pipeline_db.update_oem_classify_result(
                        conn, domain, result["klass_oem"], result["klass_oem_reason"]
                    )
                if n == 0:
                    errors += 1
                    logger.error("DB WRITE MISS: domain '%s' not found", domain)
                else:
                    classified += 1
                    counts[result["klass_oem"]] += 1
                    logger.debug(
                        "[%d/%d] %s -> %s", i, total, domain, result["klass_oem_reason"]
                    )
            except Exception as e:  # noqa: BLE001 - one failed record never stops the batch
                errors += 1
                logger.error("[%d/%d] FAILED: %s - %s", i, total, domain, e)
            if i % 25 == 0:
                logger.info(
                    "OEM classify progress: %d/%d - %s, %d errors", i, total, counts, errors
                )

    logger.info(
        "OEM classify complete: %d classified %s, %d errors", classified, counts, errors
    )
    return classified
