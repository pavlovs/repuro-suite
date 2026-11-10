"""M37 T10: tag OEM D1 + C records as batch BA11 (dry-run by default).

Candidates: klass_oem IN ('D1', 'C') and briefaktion empty. Excluded (plan decision 5), counted
per rule (a record is reported under its first matching rule):
  approached        pipeline_stage = 'approached'
  already_approached already_approached = 1
  live_deal         live deal target (Baaske Medical = deal Rabbit / Projekt CARE)
  contact_note      manual_note shows a letter, LOI, decline, reply or "no reply"
Also reported: D1 / C records that already carry a briefaktion (never re-tagged).

--apply writes briefaktion = 'BA11' only where briefaktion IS NULL or ''. Nothing else is written.

Usage: python scripts/m37_tag_ba11.py [--apply] [--db PATH]
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402

BATCH = "BA11"
LIVE_DEAL_DOMAINS = frozenset({"baaske-medical.de"})
LIVE_DEAL_NAME_RE = re.compile(r"baaske", re.IGNORECASE)
CONTACT_NOTE_RE = re.compile(
    r"\b(letters?|brief|loi|declined?|abgelehnt|no reply|keine antwort|replied|follow-up)\b",
    re.IGNORECASE,
)
RULES = ("approached", "already_approached", "live_deal", "contact_note")


def exclusion_rule(row: sqlite3.Row) -> str | None:
    """First exclusion rule a candidate hits, or None."""
    if (row["pipeline_stage"] or "") == "approached":
        return "approached"
    if (row["already_approached"] or 0) == 1:
        return "already_approached"
    if row["domain"] in LIVE_DEAL_DOMAINS or LIVE_DEAL_NAME_RE.search(row["full_name"] or ""):
        return "live_deal"
    if CONTACT_NOTE_RE.search(row["manual_note"] or ""):
        return "contact_note"
    return None


def plan_tagging(conn: sqlite3.Connection) -> tuple[list[str], dict[str, int], int]:
    """Return (domains to tag, excluded count per rule, D1/C records already batched)."""
    conn.row_factory = sqlite3.Row
    already = conn.execute(
        "SELECT COUNT(*) FROM company_records WHERE klass_oem IN ('D1','C') "
        "AND briefaktion IS NOT NULL AND briefaktion != ''"
    ).fetchone()[0]
    rows = conn.execute(
        """SELECT domain, full_name, pipeline_stage, already_approached, manual_note
           FROM company_records
           WHERE klass_oem IN ('D1', 'C') AND (briefaktion IS NULL OR briefaktion = '')
           ORDER BY domain"""
    ).fetchall()
    excluded = {r: 0 for r in RULES}
    tag: list[str] = []
    for row in rows:
        rule = exclusion_rule(row)
        if rule:
            excluded[rule] += 1
        else:
            tag.append(row["domain"])
    return tag, excluded, already


def apply_tagging(conn: sqlite3.Connection, domains: list[str]) -> int:
    n = 0
    for d in domains:
        n += conn.execute(
            "UPDATE company_records SET briefaktion = ? "
            "WHERE domain = ? AND (briefaktion IS NULL OR briefaktion = '')",
            (BATCH, d),
        ).rowcount
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Tag OEM D1 + C as BA11 (dry-run default)")
    ap.add_argument("--apply", action="store_true", help="write briefaktion='BA11'")
    ap.add_argument("--db", type=Path, default=settings.PIPELINE_DB_PATH)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db, timeout=10)
    conn.execute("PRAGMA journal_mode=DELETE")
    try:
        if args.apply:
            # hold the write lock from planning to commit so no exclusion changes in between
            conn.execute("BEGIN IMMEDIATE")
        used = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE briefaktion = ?", (BATCH,)
        ).fetchone()[0]
        tag, excluded, already = plan_tagging(conn)
        print(f"Batch {BATCH} already holds {used} records")
        print(f"D1/C already in another batch (skipped): {already}")
        for rule in RULES:
            print(f"Excluded {rule:20s} {excluded[rule]}")
        print(f"To tag {BATCH}:                  {len(tag)}")
        if args.apply:
            n = apply_tagging(conn, tag)
            conn.commit()
            print(f"APPLIED: {n} records set to briefaktion='{BATCH}'")
        else:
            print("DRY RUN: nothing written (use --apply)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
