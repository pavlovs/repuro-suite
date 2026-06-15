"""Serienbriefe exporter (M10). Maps classified+enriched records to 36-column Excel output."""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import os
import pandas as pd

from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline import db as pipeline_db
from src.utils.excel import validate_no_formula_errors, write_dataframe_to_xlsx

logger = logging.getLogger(__name__)

# Serienbriefe column order (36 columns)
# Group 1: Identity & pipeline analytics (9 cols)
# Group 2: Word mail merge fields from 251111_Repuro_MedTech_Brief_Updated_vF.docx (19 cols)
# Group 3: Contact (2 cols)
# Group 4: Post-sendout outreach tracking (6 cols)
SERIENBRIEFE_COLUMNS = [
    # Group 1: Identity & pipeline analytics
    "Domain Name Clean",  # 0  domain
    "Source",  # 1  WLW / ORBIS
    "Category",  # 2  klass
    "Priority",  # 3  Prio 1 for A/B
    "MA",  # 4  ma_count
    "Owner Age",  # 5  gesellschafter_age
    "Services Score",  # 6  services_score
    "SSB",  # 7  ssb_flag
    "HR-Nummer",  # 8  hrb_number
    # Group 2: Word merge fields (field code → Excel col header)
    # Name_Briefkopf → "Name Briefkopf"
    # Name_Titel → "Name Titel"
    # Name_Absatz_1 → "Name Absatz 1"
    # Name_Absatz_3 → "Name Absatz 3"
    # First_Name_1 → "First Name (1)"
    # Last_Name_1 → "Last Name (1)"
    # Gesellschafter → "Gesellschafter"
    # Anrede → "Anrede"
    # Salutation → "Salutation"
    # Street_Address → "Street Address"
    # PLZ__Stadt → "PLZ + Stadt"
    # Region → "Region"
    # Leistung_Absatz_1 → "Leistung Absatz 1"
    # Leistung_Absatz_2 → "Leistung Absatz 2"
    # Mehrwerte → "Mehrwerte"
    # Kompliment_1 → "Kompliment 1"
    # Kompliment_2 → "Kompliment 2"
    # Verantwortlich → "Verantwortlich"
    # Zweiter → "Zweiter"
    "Name Briefkopf",  # 9
    "Name Titel",  # 10
    "Name Absatz 1",  # 11
    "Name Absatz 3",  # 12
    "First Name (1)",  # 13
    "Last Name (1)",  # 14
    "Gesellschafter",  # 15
    "Anrede",  # 16
    "Salutation",  # 17
    "Street Address",  # 18
    "PLZ + Stadt",  # 19
    "Region",  # 20
    "Leistung Absatz 1",  # 21
    "Leistung Absatz 2",  # 22
    "Mehrwerte",  # 23
    "Kompliment 1",  # 24
    "Kompliment 2",  # 25
    "Gruppe 1",  # 26
    "Gruppe 2",  # 27
    "Verantwortlich",  # 28
    "Zweiter",  # 29
    # Group 3: Contact
    "Email",  # 30
    "Tel",  # 31
    # Group 4: Post-sendout outreach tracking
    "Datum Sent",  # 32  outreach_sent_at
    "Status",  # 33  outreach_status
    "Comment",  # 34  outreach_comment
    "Follow-Up 1",  # 35  followup1_at
    "Follow-Up 2",  # 36  followup2_at
    "Follow-Up Comment",  # 37  followup_comment
]


def _parse_name(full_name: Optional[str]) -> tuple[str, str]:
    """Split 'Vorname Nachname' -> (first, last). Handles multi-part names."""
    if not full_name:
        return "", ""
    parts = full_name.strip().split()
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


_GUIDE_PATH = Path(__file__).parent.parent / "config" / "compliment_guide.md"

_COMPLIMENT_PROMPT_BASE = """Generate two German Kompliment sentences for a Serienbrief.

{guide_section}

Analyze the website text below and select the correct tier for each compliment.

## Kompliment 1 (K1) — opening paragraph, references experience/expertise
Check in this order, use the FIRST tier that matches:

Tier 1 — Year of foundation found on website:
  "Ihre umfassende Erfahrung und Expertise, die Sie seit der Gründung im Jahr {{YEAR}} aufgebaut haben"

Tier 2 — Duration of existence found (e.g. "20 Jahren", "zwei Jahrzehnten"):
  "Ihre umfassende Erfahrung und Expertise, die Sie in mehr als {{DURATION}} gesammelt haben"

Tier 3 — Neither found:
  "die hohe Spezialisierung und Expertise im Bereich {{SPECIALIZATION}}"
  Use the company's own wording for their specialization from the website.
  If no specific wording available, use a generic phrase for their product offering.

## Kompliment 2 (K2) — second paragraph, highlights a differentiator
Check in this order, use the FIRST tier that matches:

Tier 1 — Slogan or mission statement found on website:
  "Ihr Leitbild mit den Schwerpunkten \"{{SLOGAN}}\" hat" or
  "Ihr starker Kundenfokus gemäß der Maxime \"{{SLOGAN}}\", hat"

Tier 2 — Quantitative metric found (customer count, product count, manufacturer count):
  e.g. "das breite und hochwertige Sortiment von mehr als {{N}} Produkten hat" or
  "die große Auswahl qualitativ hochwertiger Markenartikel von über {{N}} Herstellern hat"

Tier 3 — Generic portfolio (no slogan, no metric, but product categories identifiable):
  "das breite Leistungsportfolio, von hochwertigen {{CATEGORY_A}} bis zum {{CATEGORY_B}}, hat"
  Replace CATEGORY_A and CATEGORY_B with company-specific product categories from the website.
  Alternative: "das breite Sortiment, von hochwertigen Instrumenten bis zu Praxis- und Sprechstundenbedarf, hat"

Tier 4 — Backup (nothing specific found):
  "der starke Fokus auf hohe Qualität und zuverlässigen Service hat"

## Rules
- Each compliment: exactly one sentence, 15-30 words, German, proper Umlaute (ue->ü, oe->ö, ae->ä, ss->ß where appropriate)
- Specific to THIS company — no generic filler unless forced to Tier 3/4
- No greeting, no sign-off
- Pick the highest applicable tier (lowest number) for each compliment

Company: {full_name}
Website excerpt: {scraped_text}

Return ONLY valid JSON:
{{"k1": "...", "k2": "...", "k1_tier": 1, "k2_tier": 1}}"""

_COMPLIMENT_MAX_TOKENS = 200
_COMPLIMENT_MODEL = "claude-haiku-4-5-20251001"


def _load_compliment_guide() -> str:
    """Load compliment_guide.md as a context block. Returns empty string if missing."""
    if _GUIDE_PATH.exists():
        try:
            guide = _GUIDE_PATH.read_text(encoding="utf-8")
            return f"Style guide (follow these patterns):\n{guide}\n"
        except OSError:
            pass
    logger.warning(
        "compliment_guide.md not found at %s — using base prompt only", _GUIDE_PATH
    )
    return ""


def _extract_value_regex(text: str, key: str) -> Optional[str]:
    """Extract a JSON string value by key using regex — fallback for malformed JSON."""
    import re

    pattern = rf'"{key}"\s*:\s*"(.*?)"(?:\s*[,}}])'
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip().strip('"')
    return None


def _parse_compliment_json(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (k1, k2) from JSON response. Returns (None, None) on parse failure.

    Falls back to regex extraction when JSON is malformed (unescaped quotes).
    """
    import json as _json

    from src.pipeline.normalize import fix_compliment_text, restore_umlauts_german

    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
    data = None
    try:
        data = _json.loads(text)
    except _json.JSONDecodeError:
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i, ch in enumerate(text[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            data = _json.loads(text[brace_start : i + 1])
                        except _json.JSONDecodeError:
                            pass
                        break
    if data is None:
        k1 = _extract_value_regex(text, "k1")
        k2 = _extract_value_regex(text, "k2")
        if k1 or k2:
            logger.debug(
                "Compliment JSON malformed, regex extracted k1=%s k2=%s",
                bool(k1),
                bool(k2),
            )
            if k1:
                k1 = restore_umlauts_german(k1)
            if k2:
                k2 = restore_umlauts_german(k2)
            k1, k2 = fix_compliment_text(k1, k2)
            return k1, k2
        logger.warning("Failed to parse compliment JSON %r", text[:120])
        return None, None
    try:
        k1 = str(data["k1"]).strip().strip('"') or None
        k2 = str(data["k2"]).strip().strip('"') or None
        if k1:
            k1 = restore_umlauts_german(k1)
        if k2:
            k2 = restore_umlauts_german(k2)
        k1, k2 = fix_compliment_text(k1, k2)
        return k1, k2
    except Exception as e:
        logger.warning("Failed to parse compliment JSON %r: %s", text[:120], e)
        return None, None


def _generate_compliment_cli(
    full_name: str, scraped_text: str
) -> tuple[Optional[str], Optional[str]]:
    """Generate Kompliment 1 and 2 via claude CLI subprocess (OAuth, no API key).

    Prompt passed via stdin (not as CLI arg) to avoid Windows shell issues with
    special characters (&, +, newlines) in company names and scraped text.
    """
    prompt = _COMPLIMENT_PROMPT_BASE.format(
        guide_section=_load_compliment_guide(),
        full_name=full_name,
        scraped_text=(scraped_text or "")[:600],
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        result = subprocess.run(
            [settings.CLAUDE_CMD, "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=90,
            encoding="utf-8",
            env=env,
        )
        if result.returncode != 0:
            logger.warning(
                "Claude CLI error for %r: %s", full_name, result.stderr.strip()
            )
            return None, None
        return _parse_compliment_json(result.stdout)
    except Exception as e:
        logger.warning("Compliment CLI call failed for %r: %s", full_name, e)
        return None, None


def _fill_missing_compliments(
    records: list,
    db_path: Path,
    dry_run: bool = False,
) -> None:
    """Generate compliment_draft + compliment_2 for A/B records missing either.

    Skips records without scraped_text. Only called for records going into the export.
    """
    missing = [
        r
        for r in records
        if (not r.compliment_draft or not r.compliment_2)
        and r.scraped_text
        and r.prio == "Prio 1"
    ]
    if not missing:
        return

    logger.info("Generating compliments for %d records", len(missing))

    if dry_run:
        logger.info("DRY RUN -- skipping compliment generation")
        return

    for i, rec in enumerate(missing, 1):
        k1, k2 = _generate_compliment_cli(rec.full_name or rec.domain, rec.scraped_text)

        if k1 or k2:
            with pipeline_db.get_connection(db_path) as conn:
                pipeline_db.update_compliments(conn, rec.domain, k1, k2)
            rec.compliment_draft = k1 or rec.compliment_draft
            rec.compliment_2 = k2 or rec.compliment_2
            logger.debug(
                "[%d/%d] Compliments: %s -> k1=%r k2=%r",
                i,
                len(missing),
                rec.domain,
                k1,
                k2,
            )
        else:
            logger.warning(
                "[%d/%d] No compliments generated for %s", i, len(missing), rec.domain
            )
        if i < len(missing):
            time.sleep(0.2)


def _record_to_row(rec, raw: dict) -> dict:
    """Map a CompanyRecord + raw DB dict to a Serienbriefe row dict."""
    first_name, last_name = _parse_name(rec.owner_name)
    priority = "Prio 1" if rec.prio == "Prio 1" else ""

    return {
        # Group 1: Identity & analytics
        "Domain Name Clean": rec.domain or "",
        "Source": raw.get("source") or "",
        "Category": rec.klass or "",
        "Priority": priority,
        "MA": rec.ma_count or "",
        "Owner Age": rec.gesellschafter_age or "",
        "Services Score": rec.services_score or "",
        "SSB": "ja" if rec.ssb_flag else "",
        "HR-Nummer": rec.hrb_number or "",
        # Group 2: Word merge fields
        # Use impressum_name if set (manually corrected from Impressum), else ORBIS full_name
        "Name Briefkopf": raw.get("impressum_name") or rec.full_name or "",
        "Name Titel": "",
        "Name Absatz 1": rec.owner_name or rec.full_name or "",
        "Name Absatz 3": "",
        "First Name (1)": first_name,
        "Last Name (1)": last_name,
        "Gesellschafter": raw.get("gesellschafter_field") or "Gesellschafter",
        "Anrede": rec.anrede or "",
        "Salutation": rec.salutation or "",
        "Street Address": rec.street or "",
        "PLZ + Stadt": rec.plz_ort or "",
        "Region": rec.region_prep or rec.region or "",
        "Leistung Absatz 1": rec.leistung_text or "",
        "Leistung Absatz 2": rec.leistung_absatz_2 or "",
        "Mehrwerte": rec.mehrwerte or "",
        "Kompliment 1": rec.compliment_draft or "",
        "Kompliment 2": rec.compliment_2 or "",
        "Gruppe 1": raw.get("gruppe_1") or "",
        "Gruppe 2": raw.get("gruppe_2") or "",
        "Verantwortlich": "",
        "Zweiter": "",
        # Group 3: Contact
        "Email": rec.gf_email or "",
        "Tel": rec.gf_phone or "",
        # Group 4: Outreach tracking (from raw DB row — not in CompanyRecord dataclass)
        "Datum Sent": raw.get("outreach_sent_at") or "",
        "Status": raw.get("outreach_status") or "",
        "Comment": raw.get("outreach_comment") or "",
        "Follow-Up 1": raw.get("followup1_at") or "",
        "Follow-Up 2": raw.get("followup2_at") or "",
        "Follow-Up Comment": raw.get("followup_comment") or "",
    }


def _fetch_exportable_records(
    db_path: Path, approved_only: bool = False
) -> tuple[list, dict]:
    """Fetch records eligible for export (A/B/C/E, not approached, filter_pass).

    Returns (records, raw_rows_dict) where raw_rows_dict maps domain -> dict(row).
    Shared by Excel export and PDF export.
    """
    pipeline_db.ensure_schema(db_path)
    approval_clause = " AND approved_for_sendout = 1" if approved_only else ""
    with pipeline_db.get_connection(db_path) as conn:
        rows = conn.execute(
            f"""SELECT * FROM company_records
               WHERE klass IS NOT NULL AND prio != 'Excluded'
               AND already_approached = 0
               AND (filter_pass = 1 OR filter_pass IS NULL)
               AND pipeline_stage NOT IN ('ingested'){approval_clause}
               ORDER BY
                 CASE prio WHEN 'Prio 1' THEN 1 ELSE 2 END, klass,
                 COALESCE(services_score, 0) DESC""",
        ).fetchall()
    records = [pipeline_db._row_to_company_record(row) for row in rows]
    raw_rows = {dict(row)["domain"]: dict(row) for row in rows}
    return records, raw_rows


def export_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    approved_only: bool = False,
    db_path: Path | None = None,
) -> Optional[Path]:
    """
    Export classified A/B/C/E records to Serienbriefe-ready Excel.
    Excludes: already_approached=True, klass=D/S, filter_pass=False, pipeline_stage=ingested.
    With approved_only=True: only exports records with approved_for_sendout=1.
    Returns output path or None on dry_run.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH

    records, raw_rows = _fetch_exportable_records(db_path, approved_only)

    logger.info(
        "Export: %d exportable records (A/B/C/E, not already approached)", len(records)
    )

    if not records:
        logger.warning("Export: no records to export")
        return None

    # Warn about missing compliments (M34: no silent generation at export time)
    missing_k = [
        r
        for r in records
        if (not r.compliment_draft or not r.compliment_2) and r.prio == "Prio 1"
    ]
    if missing_k:
        logger.warning(
            "Export: %d Prio 1 records missing K1/K2 — run 'backfill-compliments' first: %s",
            len(missing_k),
            ", ".join(r.domain for r in missing_k[:10]),
        )

    if dry_run:
        logger.info(
            "DRY RUN -- would export %d records (no file written)", len(records)
        )
        return None

    rows_data = [_record_to_row(rec, raw_rows.get(rec.domain, {})) for rec in records]
    df = pd.DataFrame(rows_data, columns=SERIENBRIEFE_COLUMNS)

    date_str = datetime.now().strftime("%Y%m%d")
    out_path = settings.DATA_OUTPUT_DIR / f"serienbriefe_new_batch_{date_str}.xlsx"
    settings.DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_dataframe_to_xlsx(df, out_path, sheet_name="Serienbriefe")

    if validate_no_formula_errors(out_path):
        logger.info("Export validated -- no formula errors: %s", out_path)
    else:
        logger.warning("Export validation: formula errors found in %s", out_path)

    logger.info("Export complete: %d rows -> %s", len(records), out_path)
    return out_path
