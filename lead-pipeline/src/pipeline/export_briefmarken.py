"""Briefmarken (postage stamp) CSV export for Deutsche Post.

Generates semicolon-delimited CSVs matching the Deutsche Post Briefmarken import format.
Each file contains a sender row (Repuro GmbH) followed by recipient rows.

Identifiers are computed at export time from canonical batch ordering — no DB column needed.
Encoding: latin-1 (cp1252) — matches existing Charge 5/6/7 CSVs.
"""

from __future__ import annotations

import csv
import logging
import os
import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.pipeline.db import get_connection

logger = logging.getLogger(__name__)

BRIEFMARKEN_HEADER = [
    "NAME",
    "ZUSATZ",
    "STRASSE",
    "NUMMER",
    "PLZ",
    "STADT",
    "LAND",
    "ADRESS_TYP",
    "Referenz",
]

SENDER_ROW = {
    "NAME": "Repuro GmbH",
    "ZUSATZ": "",
    "STRASSE": "Goethestr.",
    "NUMMER": "59",
    "PLZ": "10625",
    "STADT": "Berlin",
    "LAND": "DEU",
    "ADRESS_TYP": "HOUSE",
    "Referenz": "",
}

FIELD_MAX_LENGTHS = {"NAME": 48, "ZUSATZ": 50, "STRASSE": 40, "STADT": 40}

BATCH_ORDER = ["BA1", "BA2", "BA3", "BA4", "BA5", "BA6", "BA7", "BA8", "testbatch"]

_ACADEMIC_PREFIXES = ("Dr.", "Prof.")


def _compute_batch_offset(conn: sqlite3.Connection, batch: str) -> int:
    """Count records in all batches preceding `batch` in canonical order."""
    if batch not in BATCH_ORDER:
        return conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE briefaktion IS NOT NULL"
        ).fetchone()[0]
    idx = BATCH_ORDER.index(batch)
    preceding = BATCH_ORDER[:idx]
    if not preceding:
        return 0
    placeholders = ",".join("?" for _ in preceding)
    return conn.execute(
        f"SELECT COUNT(*) FROM company_records WHERE briefaktion IN ({placeholders})",
        preceding,
    ).fetchone()[0]


def _build_zusatz(
    anrede: Optional[str], owner_name: Optional[str], gesellschafter_name: Optional[str]
) -> str:
    name = (owner_name or "").strip() or (gesellschafter_name or "").strip()
    if not name:
        return ""
    for prefix in _ACADEMIC_PREFIXES:
        if name.startswith(prefix):
            return name
    anrede_str = (anrede or "").strip()
    return f"{anrede_str} {name}" if anrede_str else name


def _extract_plz(plz_ort: Optional[str]) -> str:
    if not plz_ort:
        return ""
    m = re.match(r"(\d{5})", plz_ort.strip())
    return m.group(1) if m else ""


def _extract_city_from_plz_ort(plz_ort: Optional[str]) -> str:
    if not plz_ort:
        return ""
    m = re.match(r"\d{5}\s+(.*)", plz_ort.strip())
    return m.group(1).strip() if m else ""


def _determine_adress_typ(street: Optional[str]) -> str:
    return "POBOX" if street and "postfach" in street.lower() else "HOUSE"


def _suggest_name_truncation(name: str) -> str:
    replacements = [
        ("GmbH & Co. KG", "GmbH"),
        ("GmbH & Co.KG", "GmbH"),
        ("Gesellschaft mit beschränkter Haftung", "GmbH"),
        ("Gesellschaft", "Ges."),
        ("Medizintechnik", "Med.technik"),
        ("Medizinprodukte", "Med.produkte"),
        (" und ", " u. "),
        (" Handel und Service", " H&S"),
    ]
    result = name
    for old, new in replacements:
        if len(result) <= FIELD_MAX_LENGTHS["NAME"]:
            break
        result = result.replace(old, new)
    return result


def _suggest_strasse_truncation(strasse: str) -> str:
    for old, new in [
        ("Straße", "Str."),
        ("straße", "str."),
        ("Strasse", "Str."),
        ("strasse", "str."),
    ]:
        strasse = strasse.replace(old, new)
    return strasse


def export_briefmarken(db_path: Path, batch: str, output_path: Path) -> dict:
    """Export Briefmarken CSV for a given batch.

    Identifiers (Referenz) are computed from canonical batch ordering:
    BA1 → BA2 → ... → BA8 → testbatch, alphabetical within each batch.
    """
    with get_connection(db_path) as conn:
        offset = _compute_batch_offset(conn, batch)

        all_in_batch = conn.execute(
            """SELECT full_name, owner_name, gesellschafter_name, anrede,
                      street, plz_ort, city, domain, approved_for_sendout
               FROM company_records
               WHERE briefaktion = ?
               ORDER BY full_name COLLATE NOCASE""",
            (batch,),
        ).fetchall()

    if not all_in_batch:
        logger.warning("No records found for batch %s", batch)
        return {
            "exported": 0,
            "truncation_warnings": 0,
            "incomplete_skipped": 0,
            "output_path": output_path,
            "warnings_path": None,
        }

    recipients: list[dict] = []
    incomplete: list[dict] = []
    truncation_violations: list[dict] = []
    skipped_not_approved = 0

    for i, row in enumerate(all_in_batch):
        rec = dict(row)
        referenz = offset + i + 1

        if not rec["approved_for_sendout"]:
            skipped_not_approved += 1
            continue

        full_name = rec["full_name"] or ""
        street = rec["street"] or ""
        plz_ort = rec["plz_ort"] or ""
        city = rec["city"] or ""

        missing_fields: list[str] = []
        if not street:
            missing_fields.append("street")
        if not plz_ort and not city:
            missing_fields.append("plz_ort/city")
        owner = (rec["owner_name"] or "").strip() or (
            rec["gesellschafter_name"] or ""
        ).strip()
        if not owner:
            missing_fields.append("owner_name/gesellschafter_name")

        if missing_fields:
            incomplete.append(
                {
                    "referenz": referenz,
                    "domain": rec["domain"],
                    "full_name": full_name,
                    "missing": ", ".join(missing_fields),
                }
            )
            continue

        zusatz = _build_zusatz(
            rec["anrede"], rec["owner_name"], rec["gesellschafter_name"]
        )
        plz = _extract_plz(plz_ort)
        stadt = city if city else _extract_city_from_plz_ort(plz_ort)

        csv_row = {
            "NAME": full_name,
            "ZUSATZ": zusatz,
            "STRASSE": street,
            "NUMMER": "",
            "PLZ": plz,
            "STADT": stadt,
            "LAND": "DEU",
            "ADRESS_TYP": _determine_adress_typ(street),
            "Referenz": str(referenz),
        }

        for field, max_len in FIELD_MAX_LENGTHS.items():
            value = csv_row.get(field, "")
            if len(value) > max_len:
                if field == "NAME":
                    suggested = _suggest_name_truncation(value)
                elif field == "STRASSE":
                    suggested = _suggest_strasse_truncation(value)
                else:
                    suggested = value[:max_len]
                truncation_violations.append(
                    {
                        "Referenz": csv_row["Referenz"],
                        "Field": field,
                        "Current Value": value,
                        "Length": len(value),
                        "Max": max_len,
                        "Suggested Truncation": suggested,
                    }
                )

        recipients.append(csv_row)

    if truncation_violations:
        print(f"\nWARNING: {len(truncation_violations)} field length violation(s):")
        print(f"  {'Ref':>5}  {'Field':<8}  {'Len':>3}/{'Max':<4}  Value")
        print(f"  {'-' * 5}  {'-' * 8}  {'-' * 3} {'-' * 4}  {'-' * 40}")
        for v in truncation_violations:
            print(
                f"  {v['Referenz']:>5}  {v['Field']:<8}  {v['Length']:>3}/{v['Max']:<4}  {v['Current Value'][:50]}"
            )
            print(
                f"  {'':>5}  {'':>8}  {'':>3} {'':>4}  -> {v['Suggested Truncation'][:50]}"
            )

    if incomplete:
        print(
            f"\nINCOMPLETE: {len(incomplete)} record(s) skipped (missing required fields):"
        )
        for inc in incomplete:
            print(
                f"  #{inc['referenz']}: {inc['full_name'][:40]} — missing: {inc['missing']}"
            )

    if skipped_not_approved:
        print(
            f"\nNOT APPROVED: {skipped_not_approved} record(s) in batch not yet approved"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".csv", dir=str(output_path.parent), prefix=".briefmarken_"
    )
    try:
        with os.fdopen(
            tmp_fd, "w", newline="", encoding="latin-1", errors="replace"
        ) as f:
            writer = csv.DictWriter(f, fieldnames=BRIEFMARKEN_HEADER, delimiter=";")
            writer.writeheader()
            writer.writerow(SENDER_ROW)
            for rec in recipients:
                writer.writerow(rec)
        if os.path.getsize(tmp_path) == 0:
            raise RuntimeError("Temp CSV file is empty — aborting")
        os.replace(tmp_path, str(output_path))
        logger.info("Wrote %d recipients to %s", len(recipients), output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    warnings_path = None
    if truncation_violations or incomplete:
        warnings_path = output_path.with_name(output_path.stem + "_WARNINGS.txt")
        tmp_fd2, tmp_path2 = tempfile.mkstemp(
            suffix=".txt", dir=str(warnings_path.parent), prefix=".warnings_"
        )
        try:
            with os.fdopen(tmp_fd2, "w", encoding="utf-8") as f:
                f.write(f"Briefmarken Export Warnings — {batch}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
                f.write("=" * 60 + "\n\n")
                if truncation_violations:
                    f.write(f"TRUNCATION WARNINGS ({len(truncation_violations)}):\n")
                    f.write("-" * 60 + "\n")
                    for v in truncation_violations:
                        f.write(
                            f"  Ref {v['Referenz']}, {v['Field']}: {v['Current Value']} ({v['Length']} chars, max {v['Max']})\n"
                        )
                        f.write(f"    Suggested: {v['Suggested Truncation']}\n")
                    f.write("\n")
                if incomplete:
                    f.write(f"INCOMPLETE RECORDS ({len(incomplete)}):\n")
                    f.write("-" * 60 + "\n")
                    for inc in incomplete:
                        f.write(f"  Ref {inc['referenz']}: {inc['full_name']}\n")
                        f.write(f"    Domain: {inc['domain']}\n")
                        f.write(f"    Missing: {inc['missing']}\n")
            os.replace(tmp_path2, str(warnings_path))
        except Exception:
            try:
                os.unlink(tmp_path2)
            except OSError:
                pass
            raise

    return {
        "exported": len(recipients),
        "truncation_warnings": len(truncation_violations),
        "incomplete_skipped": len(incomplete),
        "output_path": output_path,
        "warnings_path": warnings_path,
    }
