"""Backfill commands (M18). Fill missing fields from Serienbriefe Excel or via AI.

Three commands:
- backfill-from-excel: Pull K1/K2/leistung/region from Serienbriefe Excel for matched records
- backfill-leistung: AI-generate leistung fields for records with scraped_text
- backfill-compliments: AI-generate K1/K2 for records with scraped_text
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from typing import Optional

import openpyxl

from src.config import settings
from src.pipeline import db as pipeline_db

logger = logging.getLogger(__name__)

# Serienbriefe Excel column indices (0-based)
_COL_DOMAIN = 2
_COL_LEISTUNG_1 = 15
_COL_LEISTUNG_2 = 16
_COL_MEHRWERTE = 17
_COL_REGION = 21
_COL_K1 = 22
_COL_K2 = 23
_COL_ANREDE = 25
_COL_SALUTATION = 26

# Fields that backfill-from-excel can fill
_BACKFILL_FIELDS = {
    _COL_LEISTUNG_1: "leistung_text",
    _COL_LEISTUNG_2: "leistung_absatz_2",
    _COL_MEHRWERTE: "mehrwerte",
    _COL_REGION: "region_prep",
    _COL_K1: "compliment_draft",
    _COL_K2: "compliment_2",
    _COL_ANREDE: "anrede",
    _COL_SALUTATION: "salutation",
}


def backfill_from_excel_cmd(args) -> None:
    """CLI handler: fill missing fields from Serienbriefe Excel."""
    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)

    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    # Load A/B domains from DB with current field values for ALL backfill-able fields
    db_fields = ", ".join(_BACKFILL_FIELDS.values())
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows = conn.execute(
            f"""SELECT domain, {db_fields}
               FROM company_records
               WHERE prio = 'Prio 1'"""
        ).fetchall()
    db_records = {row["domain"]: dict(row) for row in rows}

    # Load Serienbriefe Excel
    wb = openpyxl.load_workbook(settings.SOURCE_EXCEL, read_only=True, data_only=True)
    ws = wb[settings.SERIENBRIEFE_SHEET]

    matched = 0
    field_fills: dict[str, int] = {f: 0 for f in _BACKFILL_FIELDS.values()}
    updates: list[tuple[str, dict[str, str]]] = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[_COL_DOMAIN]:
            continue
        domain = str(row[_COL_DOMAIN]).strip().lower()
        if domain not in db_records:
            continue

        matched += 1
        rec = db_records[domain]
        fields_to_fill: dict[str, str] = {}

        for col_idx, db_field in _BACKFILL_FIELDS.items():
            # Only fill if DB value is empty/NULL
            current = rec.get(db_field)
            if current and str(current).strip():
                continue
            # Check if Excel has a value
            if col_idx < len(row) and row[col_idx] and str(row[col_idx]).strip():
                fields_to_fill[db_field] = str(row[col_idx]).strip()
                field_fills[db_field] += 1

        if fields_to_fill:
            updates.append((domain, fields_to_fill))
            if verbose:
                logger.info("  %s: filling %s", domain, list(fields_to_fill.keys()))

    wb.close()

    # Print summary
    print(
        f"\nBackfill from Excel — {matched} A/B records matched in Serienbriefe sheet"
    )
    print("-" * 60)
    for field, count in field_fills.items():
        if count:
            print(f"  {field:25s}  {count:>5} fills")
    print(
        f"  {'TOTAL':25s}  {sum(field_fills.values()):>5} field fills across {len(updates)} records"
    )

    if dry_run:
        print("\n  DRY RUN — no changes written")
    else:
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            for domain, fields in updates:
                set_clauses = ", ".join(f"{k} = ?" for k in fields)
                values = list(fields.values()) + [domain]
                conn.execute(
                    f"UPDATE company_records SET {set_clauses} WHERE domain = ?",
                    values,
                )
        print(f"\n  Written: {len(updates)} records updated")

    print("-" * 60)


# ── Leistung backfill (AI path) ──────────────────────────────────────────────

_LEISTUNG_PROMPT = """Analyze this German company's website text and provide two outputs.

--- TASK 1: leistung_category ---
Classify the company into ONE of these categories:
- medizintechnik-service (Wartung, Reparatur, STK, technischer Kundendienst)
- medizinprodukt-handler (Handel/Vertrieb von Medizinprodukten, Verbrauchsmaterial)
- praxisausstatter (Praxiseinrichtung, Praxisbedarf, Gesamtausstattung)
- sprechstundenbedarf (SSB-Abrechnung, Sprechstundenbedarf-Versorgung)
- medizintechnik-experten (Mischform oder allgemeiner Medizintechnik-Anbieter)

--- TASK 2: mehrwerte (CRITICAL — must be company-specific, NOT generic) ---
The mehrwerte fills this sentence: "Wir unterstützen insbesondere bei ___, um Ihr Unternehmen zukunftssicher aufzustellen."

STEP 1 — Find THIS company's GAPS and WEAKNESSES in the website text:
- What are they NOT doing? (e.g. no online shop, no digital ordering, limited geography)
- What pain points are hinted at? (e.g. price pressure, narrow supplier base, single service line)
- What do they lack compared to a well-run, scalable operation?

STEP 2 — Match gaps to Repuro's 5 value creation levers (pick the 1-2 most relevant):
A) Einkauf & Beschaffung — procurement scale, supplier consolidation, better conditions.
   Relevant for: distributors/handlers who lack buying power, face price pressure, have few suppliers.
B) Digitalisierung & Vertriebskanäle — e-commerce, digital ordering, online presence.
   Relevant for: companies with no online shop, outdated website, purely analog order processes.
C) Commercial Excellence / Vertriebswachstum — SoW expansion, new customer acquisition, key account management.
   Relevant for: regional/niche specialists who could grow geographically or expand wallet share.
D) Qualitätsmanagement & Regulatorik — MDR, MPBetreibV compliance, quality management systems.
   Relevant for: service/repair companies handling medical devices.
E) Cross-Selling & Portfolioerweiterung — adding adjacent service or product lines.
   Relevant for: single-focus companies (e.g. only sells but does not service, or vice versa).

STEP 3 — Write a DATIVE noun phrase (NO full sentences, NO periods, max 130 chars) naming those specific needs.
The phrase must reflect THIS company's actual gaps — not a generic Repuro pitch.

GOOD examples (company-specific):
- Small distributor lacking buying power: "dem Ausbau Ihrer Einkaufskonditionen durch Gruppenbündelung und der Erschließung neuer Vertriebskanäle"
- Service company with no digital presence: "der Digitalisierung Ihres Servicemanagements und der Stärkung Ihrer Marktpräsenz"

BAD examples (generic, do NOT produce):
- "neuen Wachstumsinitiativen, der Digitalisierung und beim Qualitätsmanagement"
- "der Optimierung von Prozessen und der Erschließung neuer Märkte"

Return ONLY valid JSON with keys "leistung_category", "mehrwerte".

Company: {full_name}
Website text: {scraped_text}"""


def _call_claude_cli(prompt: str) -> tuple[Optional[str], Optional[str]]:
    """Call claude CLI via subprocess with stdin prompt.

    Returns (stdout, error_type). error_type is None on success,
    or one of 'timeout', 'cli_error', 'exception'.
    """
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
            logger.warning("Claude CLI error: %s", result.stderr.strip()[:200])
            return None, "cli_error"
        return result.stdout.strip(), None
    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI timed out")
        return None, "timeout"
    except Exception as e:
        logger.warning("Claude CLI call failed: %s", e)
        return None, "exception"


def _extract_value_regex(text: str, key: str) -> Optional[str]:
    """Extract a JSON string value by key using regex — fallback for malformed JSON.

    Handles unescaped quotes inside values by matching from '"key": "' to the next
    '", "' or '"}' boundary.
    """
    import re

    pattern = rf'"{key}"\s*:\s*"(.*?)"(?:\s*[,}}])'
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip().strip('"')
    return None


def _parse_json_response(text: str) -> Optional[dict]:
    """Parse JSON from Claude response, stripping markdown fences if present.

    Falls back to regex extraction when JSON is malformed (e.g., unescaped quotes).
    Applies umlaut restoration to string values in the parsed dict.
    """
    from src.pipeline.normalize import restore_umlauts_german

    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(l for l in lines if not l.startswith("```")).strip()
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
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
                            data = json.loads(text[brace_start : i + 1])
                        except json.JSONDecodeError:
                            pass
                        break
    if data is None:
        # Regex fallback for malformed JSON (unescaped quotes in values)
        extracted = {}
        for key in ("k1", "k2", "leistung_category", "mehrwerte", "impressum_name"):
            val = _extract_value_regex(text, key)
            if val:
                extracted[key] = val
        if extracted:
            logger.debug(
                "JSON parse failed, regex extracted: %s", list(extracted.keys())
            )
            data = extracted
        else:
            logger.warning("JSON parse failed (no regex match either) — %s", text[:120])
            return None
    # Post-process: restore umlauts in all string values
    for key, val in data.items():
        if isinstance(val, str):
            data[key] = restore_umlauts_german(val)
    return data


def backfill_leistung_cmd(args) -> None:
    """CLI handler: AI-generate leistung category + mehrwerte for records missing them.

    With --force: overwrite existing values (used after prompt grammar fix).
    Without --force: only fill NULL/empty fields (COALESCE semantics).
    """
    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)
    limit = getattr(args, "limit", 0)
    force = getattr(args, "force", False)

    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    if force:
        # Force mode: all A/B records with scraped_text (overwrite existing)
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            rows = conn.execute(
                """SELECT domain, full_name, scraped_text
                   FROM company_records
                   WHERE prio = 'Prio 1'
                     AND already_approached = 0
                     AND scraped_text IS NOT NULL AND scraped_text != ''"""
            ).fetchall()
    else:
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            rows = conn.execute(
                """SELECT domain, full_name, scraped_text
                   FROM company_records
                   WHERE prio = 'Prio 1'
                     AND ((leistung_text IS NULL OR leistung_text = '')
                       OR (leistung_absatz_2 IS NULL OR leistung_absatz_2 = '')
                       OR (mehrwerte IS NULL OR mehrwerte = ''))
                     AND scraped_text IS NOT NULL AND scraped_text != ''"""
            ).fetchall()

    eligible = [dict(r) for r in rows]
    if limit:
        eligible = eligible[:limit]

    mode_label = "FORCE (overwrite)" if force else "fill empty only"
    print(
        f"\nBackfill leistung ({mode_label}) — {len(rows)} records eligible, processing {len(eligible)}"
    )
    print("-" * 60)

    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "BEFORE backfill-leistung")

    if dry_run:
        print("  DRY RUN — no Claude calls, no DB writes")
        print("-" * 60)
        return

    filled = 0
    errors: dict[str, list[str]] = {
        "timeout": [],
        "cli_error": [],
        "parse_error": [],
        "empty": [],
    }
    for i, rec in enumerate(eligible, 1):
        prompt = _LEISTUNG_PROMPT.format(
            full_name=rec["full_name"] or rec["domain"],
            scraped_text=(rec["scraped_text"] or "")[:2000],
        )
        raw, err_type = _call_claude_cli(prompt)
        if err_type:
            errors[err_type].append(rec["domain"])
            print(f"  [{i}/{len(eligible)}] {rec['domain']}: {err_type}")
            continue
        data = _parse_json_response(raw)
        if not data:
            errors["parse_error"].append(rec["domain"])
            print(f"  [{i}/{len(eligible)}] {rec['domain']}: parse_error")
            continue

        # Resolve category to dative noun phrases
        cat = str(data.get("leistung_category", "")).strip().lower()
        mapping = settings.LEISTUNG_CATEGORIES.get(
            cat, settings.LEISTUNG_CATEGORIES[settings.LEISTUNG_DEFAULT_CATEGORY]
        )
        leistung_text = mapping["leistung_text"]
        leistung_absatz_2 = mapping["leistung_absatz_2"]
        mehrwerte = str(data.get("mehrwerte", ""))[:400]

        if leistung_text or mehrwerte:
            with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
                if force:
                    conn.execute(
                        """UPDATE company_records
                           SET leistung_text = ?, leistung_absatz_2 = ?, mehrwerte = ?
                           WHERE domain = ?""",
                        (leistung_text, leistung_absatz_2, mehrwerte, rec["domain"]),
                    )
                else:
                    conn.execute(
                        """UPDATE company_records
                           SET leistung_text     = CASE WHEN (leistung_text IS NULL OR leistung_text = '')
                                                        THEN ? ELSE leistung_text END,
                               leistung_absatz_2 = CASE WHEN (leistung_absatz_2 IS NULL OR leistung_absatz_2 = '')
                                                        THEN ? ELSE leistung_absatz_2 END,
                               mehrwerte         = CASE WHEN (mehrwerte IS NULL OR mehrwerte = '')
                                                        THEN ? ELSE mehrwerte END
                           WHERE domain = ?""",
                        (leistung_text, leistung_absatz_2, mehrwerte, rec["domain"]),
                    )
            filled += 1
            if verbose:
                logger.info(
                    "[%d/%d] %s: cat=%s → %s",
                    i,
                    len(eligible),
                    rec["domain"],
                    cat,
                    leistung_text,
                )

        if i < len(eligible):
            time.sleep(0.3)

    total_errors = sum(len(v) for v in errors.values())
    print(f"\n  Filled: {filled}/{len(eligible)} records")
    if total_errors:
        print(f"  Errors: {total_errors} — ", end="")
        print(", ".join(f"{len(v)} {k}" for k, v in errors.items() if v))
        for err_type, domains in errors.items():
            if domains:
                print(f"    {err_type}: {', '.join(domains[:10])}")
    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "AFTER backfill-leistung")
    print("-" * 60)


_K2_ONLY_PROMPT = """Generate one German Kompliment sentence (Kompliment 2) for a Serienbrief.

Kompliment 2 appears in the second paragraph. It highlights a specific service concept,
product specialisation, or differentiator. NOT company history (that's K1).

Analyze the website text and select the correct tier. Check in this order, use the FIRST that matches:

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

One sentence, 15-30 words, German, proper Umlaute. Pick the highest applicable tier.
Specific to THIS company — no generic filler unless forced to Tier 3/4.

Company: {full_name}
Website excerpt: {scraped_text}

Return ONLY valid JSON: {{"k2": "...", "k2_tier": 1}}"""


def _generate_k2_only_cli(full_name: str, scraped_text: str) -> Optional[str]:
    """Generate K2 only via Claude CLI (shorter prompt, avoids truncation)."""
    from src.pipeline.normalize import fix_compliment_text

    prompt = _K2_ONLY_PROMPT.format(
        full_name=full_name,
        scraped_text=(scraped_text or "")[:600],
    )
    raw, _ = _call_claude_cli(prompt)
    data = _parse_json_response(raw)  # already applies umlaut restoration
    if data and data.get("k2"):
        k2 = str(data["k2"]).strip()
        _, k2 = fix_compliment_text(None, k2)
        return k2
    return None


def backfill_compliments_cmd(args) -> None:
    """CLI handler: AI-generate K1/K2 for records missing them.

    Two passes:
    1. Records missing K1 → generate both K1+K2 together
    2. Records with K1 but missing K2 → K2-only prompt (shorter, avoids CLI truncation)
    """
    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)
    limit = getattr(args, "limit", 0)

    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    from src.pipeline.export import _generate_compliment_cli

    # Pass 1: Records missing K1
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows_k1 = conn.execute(
            """SELECT domain, full_name, scraped_text
               FROM company_records
               WHERE prio = 'Prio 1'
                 AND (compliment_draft IS NULL OR compliment_draft = '')
                 AND scraped_text IS NOT NULL AND scraped_text != ''"""
        ).fetchall()

    # Pass 2: Records with K1 but missing K2
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows_k2 = conn.execute(
            """SELECT domain, full_name, scraped_text
               FROM company_records
               WHERE prio = 'Prio 1'
                 AND compliment_draft IS NOT NULL AND compliment_draft != ''
                 AND (compliment_2 IS NULL OR compliment_2 = '')
                 AND scraped_text IS NOT NULL AND scraped_text != ''"""
        ).fetchall()

    eligible_k1 = [dict(r) for r in rows_k1]
    eligible_k2 = [dict(r) for r in rows_k2]
    if limit:
        eligible_k1 = eligible_k1[:limit]
        eligible_k2 = eligible_k2[:limit]

    print(
        f"\nBackfill compliments — {len(rows_k1)} need K1+K2, {len(rows_k2)} need K2 only"
    )
    print("-" * 60)

    pipeline_db.print_fill_rates(
        settings.PIPELINE_DB_PATH, "BEFORE backfill-compliments"
    )

    if dry_run:
        print("  DRY RUN — no Claude calls, no DB writes")
        print("-" * 60)
        return

    filled = 0
    errors: dict[str, list[str]] = {
        "timeout": [],
        "parse_error": [],
        "empty_response": [],
    }

    # Pass 1: K1+K2
    if eligible_k1:
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            for i, rec in enumerate(eligible_k1, 1):
                k1, k2 = _generate_compliment_cli(
                    rec["full_name"] or rec["domain"], rec["scraped_text"]
                )
                if k1 or k2:
                    pipeline_db.update_compliments(conn, rec["domain"], k1, k2)
                    filled += 1
                else:
                    errors["empty_response"].append(rec["domain"])
                    print(
                        f"  [K1+K2 {i}/{len(eligible_k1)}] {rec['domain']}: no result"
                    )
                if verbose:
                    logger.info(
                        "[K1+K2 %d/%d] %s: k1=%r",
                        i,
                        len(eligible_k1),
                        rec["domain"],
                        (k1 or "")[:40],
                    )
                if i < len(eligible_k1):
                    time.sleep(0.3)

    # Pass 2: K2-only (shorter prompt avoids CLI truncation)
    if eligible_k2:
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            for i, rec in enumerate(eligible_k2, 1):
                k2 = _generate_k2_only_cli(
                    rec["full_name"] or rec["domain"], rec["scraped_text"]
                )
                if k2:
                    conn.execute(
                        """UPDATE company_records SET compliment_2 = ?
                           WHERE domain = ? AND (compliment_2 IS NULL OR compliment_2 = '')""",
                        (k2, rec["domain"]),
                    )
                    filled += 1
                else:
                    errors["empty_response"].append(rec["domain"])
                    print(f"  [K2 {i}/{len(eligible_k2)}] {rec['domain']}: no result")
                if verbose:
                    logger.info(
                        "[K2 %d/%d] %s: k2=%r",
                        i,
                        len(eligible_k2),
                        rec["domain"],
                        (k2 or "")[:50],
                    )
                if i < len(eligible_k2):
                    time.sleep(0.3)

    total_errors = sum(len(v) for v in errors.values())
    print(
        f"\n  Filled: {filled} records ({len(eligible_k1)} K1+K2, {len(eligible_k2)} K2-only)"
    )
    if total_errors:
        print(f"  Errors: {total_errors} — ", end="")
        print(", ".join(f"{len(v)} {k}" for k, v in errors.items() if v))
        for err_type, domains in errors.items():
            if domains:
                print(f"    {err_type}: {', '.join(domains[:10])}")
    pipeline_db.print_fill_rates(
        settings.PIPELINE_DB_PATH, "AFTER backfill-compliments"
    )
    print("-" * 60)


# ── Impressum Name Extraction ──────────────────────────────────────────

_IMPRESSUM_PROMPT = """Extract the exact legal company name (Firmenname laut Impressum/Handelsregister) from this German website text. Return ONLY valid JSON: {{"impressum_name": "..."}}.
If the impressum name cannot be determined, return: {{"impressum_name": null}}.

Website text:
{scraped_text}"""


def backfill_impressum_cmd(args) -> None:
    """CLI handler: extract impressum_name from scraped_text via AI."""
    dry_run: bool = getattr(args, "dry_run", False)
    limit: int = getattr(args, "limit", 0)
    verbose: bool = getattr(args, "verbose", False)
    force: bool = getattr(args, "force", False)

    print("=" * 60)
    print("BACKFILL: Impressum Name Extraction" + (" (FORCE)" if force else ""))
    print("=" * 60)

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        if force:
            query = """
                SELECT domain, full_name, scraped_text FROM company_records
                WHERE prio = 'Prio 1'
                  AND scraped_text IS NOT NULL AND scraped_text != ''
            """
        else:
            query = """
                SELECT domain, full_name, scraped_text FROM company_records
                WHERE prio = 'Prio 1'
                  AND (impressum_name IS NULL OR impressum_name = '')
                  AND scraped_text IS NOT NULL AND scraped_text != ''
            """
        rows = conn.execute(query).fetchall()

    if limit > 0:
        rows = rows[:limit]

    mode = "all" if force else "empty impressum_name only"
    print(f"  Eligible: {len(rows)} A/B records ({mode})")
    if not rows:
        print("  Nothing to do.")
        print("-" * 60)
        return

    if dry_run:
        for r in rows:
            print(f"  [DRY-RUN] Would extract impressum for: {r['domain']}")
        print("-" * 60)
        return

    filled = 0
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        for i, rec in enumerate(rows, 1):
            # Truncate scraped text to avoid overly long prompts
            text = (rec["scraped_text"] or "")[:6000]
            prompt = _IMPRESSUM_PROMPT.format(scraped_text=text)
            raw, _ = _call_claude_cli(prompt)
            data = _parse_json_response(raw)

            impressum = None
            if data and data.get("impressum_name"):
                impressum = str(data["impressum_name"]).strip()[:200]

            if impressum:
                conn.execute(
                    "UPDATE company_records SET impressum_name = ? WHERE domain = ?",
                    (impressum, rec["domain"]),
                )
                filled += 1

            if verbose:
                logger.info(
                    "[%d/%d] %s: impressum=%r",
                    i,
                    len(rows),
                    rec["domain"],
                    (impressum or "")[:60],
                )
            if i < len(rows):
                time.sleep(0.3)

    print(f"  Filled: {filled}/{len(rows)} records")
    print("-" * 60)
