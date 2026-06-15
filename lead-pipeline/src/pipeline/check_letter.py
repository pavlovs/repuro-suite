"""Serienbrief grammar/consistency checker (M18 session).

Reads finalized letter fields for A/B records and validates via Claude Sonnet:
- German grammar in K1, K2, salutation, leistung
- Consistency: anrede matches salutation, region preposition correct
- Missing required fields flagged
- Output: structured report with per-record issues
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Optional

from src.config import settings
from src.pipeline import db as pipeline_db

logger = logging.getLogger(__name__)

_CLAUDE_CMD = settings.CLAUDE_CMD

# Fields required for a complete Serienbrief letter.
# Aligned with REQUIRED_LETTER_FIELDS in export_pdf.py (which uses merge field names).
# This list uses DB column names since check_letter queries raw DB rows.
# gf_email is warning-only (not in the letter, but operationally useful).
_REQUIRED_FIELDS = [
    ("full_name", "Name Briefkopf"),
    ("anrede", "Anrede"),
    ("salutation", "Salutation"),
    ("owner_name", "Ansprechpartner"),
    ("street", "Straße"),
    ("plz_ort", "PLZ + Stadt"),
    ("region_prep", "Region"),
    ("leistung_text", "Leistung Absatz 1"),
    ("compliment_draft", "Kompliment 1"),
    ("compliment_2", "Kompliment 2"),
    ("mehrwerte", "Mehrwerte"),
    ("gf_email", "Email"),
]

_CHECK_PROMPT = """Du bist ein deutscher Lektor für formelle Geschäftsbriefe (Serienbriefe).
Prüfe den folgenden assemblierten Briefabsatz auf Fehler. Gib NUR Probleme aus, die korrigiert werden müssen.

ASSEMBLIERTER BRIEFABSATZ:
{salutation},

bei unserer Suche nach erfolgreichen {leistung} {region_prep} sind wir auf {full_name} aufmerksam geworden. Besonders beeindruckt hat uns {k1}. Auch {k2} uns davon überzeugt, dass Ihr Unternehmen zu den führenden Spezialisten zählt.

Prüfe:
1. K1-Satz: "Besonders beeindruckt hat uns {k1}." — ist die Nominalphrase grammatisch korrekt als Objekt von "beeindruckt hat"?
2. K2-Satz: "Auch {k2} uns davon überzeugt" — enthält K2 ein konjugiertes Verb (hat/haben)? Ist Singular/Plural korrekt?
3. Sind K1 und K2 inhaltlich unterschiedlich (kein Thema doppelt)?
4. Anrede passt zur Salutation (Herr → "Sehr geehrter Herr", Frau → "Sehr geehrte Frau")
5. Salutation enthält den korrekten Nachnamen (aus Ansprechpartner)
6. Region-Präposition ist korrekt (z.B. "im Allgäu", "in Hamburg", "in der Oberpfalz")
7. Leistung passt grammatisch als Dativ-Plural ("nach erfolgreichen [Leistung]")
8. Name Briefkopf enthält keine ALL-CAPS-Wörter (außer Abkürzungen wie GmbH, KG)

Briefdaten:
Name Briefkopf: {full_name}
Anrede: {anrede}
Salutation: {salutation}
Ansprechpartner: {owner_name}
Straße: {street}
PLZ + Stadt: {plz_ort}
Region: {region}
Leistung: {leistung}
Region-Präposition: {region_prep}
Kompliment 1 (K1): {k1}
Kompliment 2 (K2): {k2}

Antworte NUR mit einem JSON-Array. Jeder Eintrag hat "field", "issue", "severity" (error/warning).
Wenn alles korrekt ist, antworte mit einem leeren Array: []

Beispiel:
[{{"field": "compliment_2", "issue": "K2 fehlt konjugiertes Verb — 'hat' oder 'haben' erforderlich", "severity": "error"}}]"""


def _call_claude_check(prompt: str) -> Optional[str]:
    """Call Claude CLI for grammar check. Returns raw stdout."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        result = subprocess.run(
            ["claude.cmd", "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=90,
            encoding="utf-8",
            env=env,
        )
        if result.returncode != 0:
            logger.warning("Claude CLI error: %s", result.stderr.strip()[:200])
            return None
        return result.stdout.strip()
    except Exception as e:
        logger.warning("Claude CLI call failed: %s", e)
        return None


def _parse_issues(text: str) -> list[dict]:
    """Parse JSON array of issues from Claude response."""
    if not text:
        return []
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        logger.warning("JSON parse failed for check response: %s", text[:120])
        return []


def _check_missing_fields(rec: dict) -> list[dict]:
    """Check for missing required fields (no AI needed)."""
    issues = []
    for db_field, display_name in _REQUIRED_FIELDS:
        val = rec.get(db_field)
        if not val or not str(val).strip():
            # gf_email is warning-only (useful operationally, not in the letter)
            severity = "warning" if db_field == "gf_email" else "error"
            issues.append(
                {
                    "field": db_field,
                    "issue": f"{display_name} ist leer",
                    "severity": severity,
                }
            )
    return issues


def _check_consistency(rec: dict) -> list[dict]:
    """Rule-based consistency checks (no AI needed)."""
    issues = []
    anrede = (rec.get("anrede") or "").strip()
    salutation = (rec.get("salutation") or "").strip()
    owner_name = (rec.get("owner_name") or "").strip()

    # Anrede ↔ Salutation consistency
    if anrede == "Herr" and salutation and "Herr" not in salutation:
        issues.append(
            {
                "field": "salutation",
                "issue": f"Anrede ist 'Herr' aber Salutation enthält nicht 'Herr': '{salutation}'",
                "severity": "error",
            }
        )
    if anrede == "Frau" and salutation and "Frau" not in salutation:
        issues.append(
            {
                "field": "salutation",
                "issue": f"Anrede ist 'Frau' aber Salutation enthält nicht 'Frau': '{salutation}'",
                "severity": "error",
            }
        )

    # Salutation should contain last name from owner_name
    if salutation and owner_name and " " in owner_name:
        last_name = owner_name.split()[-1]
        if last_name not in salutation:
            issues.append(
                {
                    "field": "salutation",
                    "issue": f"Nachname '{last_name}' fehlt in Salutation: '{salutation}'",
                    "severity": "error",
                }
            )

    # ALL CAPS check on full_name
    full_name = (rec.get("full_name") or "").strip()
    if full_name and full_name == full_name.upper():
        issues.append(
            {
                "field": "full_name",
                "issue": "Name Briefkopf ist komplett in Großbuchstaben",
                "severity": "warning",
            }
        )

    # owner_name is a corporate entity (should be a person)
    owner_lower = owner_name.lower()
    if any(kw in owner_lower for kw in ("gmbh", "gbr", "verwaltung", "holding")):
        issues.append(
            {
                "field": "owner_name",
                "issue": f"Ansprechpartner scheint eine juristische Person zu sein: '{owner_name}'",
                "severity": "error",
            }
        )

    return issues


def check_letter_cmd(args) -> None:
    """CLI handler for 'python pipeline.py check-letter'."""
    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)
    limit = getattr(args, "limit", 0)
    ai_check = not getattr(args, "rules_only", False)

    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows = conn.execute(
            """SELECT domain, full_name, anrede, salutation, owner_name,
                      gesellschafter_name, street, plz_ort, city,
                      region, region_prep, leistung_text, leistung_absatz_2,
                      mehrwerte, compliment_draft, compliment_2, gf_email,
                      already_approached, approved_for_sendout
               FROM company_records
               WHERE prio = 'Prio 1' AND already_approached = 0"""
        ).fetchall()

    records = [dict(r) for r in rows]
    if limit:
        records = records[:limit]

    print(
        f"\nCheck letter — {len(rows)} unapproached A/B records, checking {len(records)}"
    )
    print("-" * 70)

    total_errors = 0
    total_warnings = 0
    records_with_issues = 0

    for i, rec in enumerate(records, 1):
        all_issues: list[dict] = []

        # Phase 1: Missing fields (always)
        all_issues.extend(_check_missing_fields(rec))

        # Phase 2: Rule-based consistency (always)
        all_issues.extend(_check_consistency(rec))

        # Phase 3: AI grammar check (optional, only for records with enough data)
        if ai_check and not dry_run:
            has_enough = (
                rec.get("salutation")
                and rec.get("compliment_draft")
                and rec.get("leistung_text")
            )
            if has_enough:
                prompt = _CHECK_PROMPT.format(
                    full_name=rec.get("full_name") or "",
                    anrede=rec.get("anrede") or "",
                    salutation=rec.get("salutation") or "",
                    owner_name=rec.get("owner_name") or "",
                    street=rec.get("street") or "",
                    plz_ort=rec.get("plz_ort") or "",
                    region=rec.get("region") or "",
                    region_prep=rec.get("region_prep") or rec.get("region") or "",
                    leistung=rec.get("leistung_text") or "",
                    k1=rec.get("compliment_draft") or "",
                    k2=rec.get("compliment_2") or "",
                )
                raw = _call_claude_check(prompt)
                ai_issues = _parse_issues(raw)
                all_issues.extend(ai_issues)

        errors = [x for x in all_issues if x.get("severity") == "error"]
        warnings = [x for x in all_issues if x.get("severity") == "warning"]
        total_errors += len(errors)
        total_warnings += len(warnings)

        if all_issues:
            records_with_issues += 1
            if verbose or errors:
                print(
                    f"\n  [{i}] {rec['domain']} — {len(errors)} errors, {len(warnings)} warnings"
                )
                for issue in all_issues:
                    marker = "E" if issue.get("severity") == "error" else "W"
                    print(
                        f"      [{marker}] {issue.get('field', '?')}: {issue.get('issue', '?')}"
                    )

    print(f"\n{'=' * 70}")
    print(f"  Records checked:       {len(records)}")
    print(f"  Records with issues:   {records_with_issues}")
    print(f"  Total errors:          {total_errors}")
    print(f"  Total warnings:        {total_warnings}")
    if dry_run:
        print("  (DRY RUN — rule-based checks only, no AI grammar check)")
    elif not ai_check:
        print("  (--rules-only — no AI grammar check)")
    print("=" * 70)
