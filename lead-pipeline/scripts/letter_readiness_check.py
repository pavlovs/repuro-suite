"""Letter Readiness Check — standalone audit script.

Reads all unapproached A/B records from the live DB and produces a
per-record completeness report. Re-run anytime to see current state.

Usage:
    python scripts/letter_readiness_check.py
    python scripts/letter_readiness_check.py --domain praximed.com
    python scripts/letter_readiness_check.py --export-ready-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.pipeline.db import get_connection

# ─── Field definitions ───────────────────────────────────────────────────────

LETTER_FIELDS = [
    # (db_column, display_label, required_for_export, note)
    ("owner_name", "Ansprechpartner", True, "must have first+last"),
    ("anrede", "Anrede", True, None),
    ("salutation", "Briefform", True, None),
    ("leistung_text", "Leistung (kurz)", True, None),
    ("leistung_absatz_2", "Leistung Absatz2", True, "needs backfill-leistung"),
    ("mehrwerte", "Mehrwerte", True, "needs backfill-leistung"),
    ("compliment_draft", "Kompliment 1", True, None),
    ("compliment_2", "Kompliment 2", True, None),
    ("region_prep", "Region (Brief)", True, None),
    ("street", "Straße", True, None),
    ("plz_ort", "PLZ + Stadt", True, None),
    ("gf_email", "E-Mail", False, "nice-to-have, SMTP blocked"),
    ("full_name", "Name (Briefkopf)", True, "check for umlaut/case issues"),
]

# ─── Checks ──────────────────────────────────────────────────────────────────


def check_owner_name(val: str | None) -> tuple[bool, str]:
    """True if owner_name has both first and last name."""
    if not val:
        return False, "EMPTY"
    parts = val.strip().split()
    if len(parts) < 2:
        return False, f"single-word '{val}' — enter first name manually"
    # Check if it's a legal entity (rough heuristic)
    legal_markers = [
        "gmbh",
        "kg",
        "ag",
        "mbh",
        "verwaltungs",
        "holding",
        "management",
        "beteiligung",
    ]
    lower = val.lower()
    if any(m in lower for m in legal_markers):
        return False, f"legal entity '{val}' — pick natural person"
    return True, "OK"


def check_full_name(val: str | None, impressum_name: str | None) -> tuple[bool, str]:
    """Check for encoding issues in full_name."""
    if not val:
        return False, "EMPTY"
    issues = []
    # Detect 'oe/ae/ue' sequences that should be umlauts
    suspicious = ["oe", "ae", "ue", "ss"]
    common_false_positives = [
        "service",
        "steel",
        "green",
        "speed",
        "zubehoer",
        "roentgen",
    ]
    lower = val.lower()
    for seq in suspicious:
        if seq in lower:
            # Check if it's a false positive
            if not any(fp in lower for fp in common_false_positives):
                pass  # could be real umlaut
            else:
                issues.append(f"possible umlaut encoding ('{seq}')")
                break
    # Check for ALL CAPS
    if val == val.upper() and len(val) > 3:
        issues.append("ALL CAPS")
    if impressum_name and impressum_name != val:
        return True, f"Impressum override set: '{impressum_name}'"
    if issues:
        return False, f"encoding issues: {', '.join(issues)} — set impressum_name"
    return True, "OK"


# ─── Main audit ──────────────────────────────────────────────────────────────


def audit_records(
    domain_filter: str | None = None, export_ready_only: bool = False
) -> list[dict]:
    db = settings.PIPELINE_DB_PATH
    results = []

    with get_connection(db) as conn:
        query = """
            SELECT domain, full_name, impressum_name, owner_name, gesellschafter_name,
                   gesellschafter_share_pct, gesellschafter_age,
                   anrede, salutation, gf_email, gf_phone,
                   leistung_text, leistung_absatz_2, mehrwerte,
                   compliment_draft, compliment_2,
                   street, plz_ort, city, region_prep, region,
                   klass, pipeline_stage, approved_for_sendout,
                   scraped_text, source, briefaktion
            FROM company_records
            WHERE already_approached = 0
              AND klass IN ('A','B')
              AND pipeline_stage NOT IN ('ingested')
        """
        if domain_filter:
            query += f" AND domain = '{domain_filter}'"
        query += " ORDER BY klass, domain"
        rows = conn.execute(query).fetchall()

    for row in rows:
        d = dict(row)
        domain = d["domain"]
        issues = []
        field_status = {}

        # Check owner_name (special: first+last required)
        owner_ok, owner_msg = check_owner_name(d.get("owner_name"))
        field_status["owner_name"] = owner_ok
        if not owner_ok:
            issues.append(f"owner_name: {owner_msg}")

        # Check full_name / impressum_name
        fn_ok, fn_msg = check_full_name(d.get("full_name"), d.get("impressum_name"))
        field_status["full_name"] = fn_ok
        if not fn_ok:
            issues.append(f"full_name: {fn_msg}")

        # Check all other letter fields
        for col, label, required, note in LETTER_FIELDS:
            if col in ("owner_name", "full_name"):
                continue  # already handled above
            val = d.get(col)
            ok = bool(val)
            field_status[col] = ok
            if not ok:
                suffix = f" [{note}]" if note else ""
                issues.append(f"missing:{label}{suffix}")

        # Compute % (required fields only, + approved)
        required_cols = [f[0] for f in LETTER_FIELDS if f[2]]
        required_ok = sum(1 for col in required_cols if field_status.get(col, False))
        approved = 1 if d.get("approved_for_sendout") else 0
        pct = round((required_ok + approved) / (len(required_cols) + 1) * 100)

        # Readiness tier
        if pct == 100:
            tier = "READY"
        elif pct >= 80:
            tier = "NEAR-READY"
        elif pct >= 60:
            tier = "IN PROGRESS"
        else:
            tier = "BLOCKED"

        result = {
            "domain": domain,
            "klass": d["klass"],
            "pct": pct,
            "tier": tier,
            "owner_name": d.get("owner_name"),
            "gesellschafter": d.get("gesellschafter_name"),
            "gs_pct": d.get("gesellschafter_share_pct"),
            "impressum_name": d.get("impressum_name"),
            "full_name": d.get("full_name"),
            "has_scraped_text": bool(d.get("scraped_text")),
            "issues": issues,
            "field_status": field_status,
            "approved": bool(d.get("approved_for_sendout")),
        }
        if not export_ready_only or tier == "READY":
            results.append(result)

    return results


def print_report(results: list[dict]) -> None:
    print()
    print("=" * 72)
    print("LETTER READINESS REPORT")
    print("=" * 72)

    tiers = {"READY": [], "NEAR-READY": [], "IN PROGRESS": [], "BLOCKED": []}
    for r in results:
        tiers[r["tier"]].append(r)

    # Summary
    print(f"\nTotal records: {len(results)}")
    for tier, recs in tiers.items():
        if recs:
            avg = round(sum(r["pct"] for r in recs) / len(recs))
            print(f"  {tier}: {len(recs)} records (avg {avg}%)")

    # Per-record detail
    print()
    for tier in ("READY", "NEAR-READY", "IN PROGRESS", "BLOCKED"):
        recs = tiers[tier]
        if not recs:
            continue
        print(f"\n-- {tier} ({len(recs)}) " + "-" * (50 - len(tier)))
        for r in recs:
            gs_info = ""
            if r["gesellschafter"] and r["gesellschafter"] != r["owner_name"]:
                gs_pct = f" ({r['gs_pct']:.1f}%)" if r["gs_pct"] else ""
                gs_info = f"  gs={r['gesellschafter']}{gs_pct}"
            imp_info = (
                f"  impressum='{r['impressum_name']}'" if r["impressum_name"] else ""
            )
            approved_tag = " ✓APPROVED" if r["approved"] else ""

            print(f"\n[{r['klass']}] {r['domain']} — {r['pct']}%{approved_tag}")
            print(f"    owner: {r['owner_name'] or '(empty)'}{gs_info}{imp_info}")
            if r["issues"]:
                for issue in r["issues"]:
                    print(f"    ! {issue}")

    # Action summary
    print()
    print("=" * 72)
    print("ACTIONS NEEDED")
    print("=" * 72)

    needs_backfill = [
        r for r in results if any("backfill-leistung" in i for i in r["issues"])
    ]
    needs_owner_fix = [
        r for r in results if any("owner_name:" in i for i in r["issues"])
    ]
    needs_impressum = [
        r for r in results if any("impressum_name" in i for i in r["issues"])
    ]

    if needs_backfill:
        print(
            f"\n1. Run CLI backfill ({len(needs_backfill)} records need leistung_absatz_2/mehrwerte):"
        )
        print("   python pipeline.py backfill-leistung --via-cli")
        print("   python pipeline.py backfill-compliments --via-cli")

    if needs_owner_fix:
        print(f"\n2. Manual: Fix owner_name for {len(needs_owner_fix)} records:")
        for r in needs_owner_fix:
            owner_issues = [i for i in r["issues"] if "owner_name:" in i]
            print(f"   {r['domain']}: {owner_issues[0] if owner_issues else ''}")

    if needs_impressum:
        print(
            f"\n3. Enter Impressum name for {len(needs_impressum)} records (in dashboard writeback):"
        )
        for r in needs_impressum:
            print(f"   {r['domain']}: current='{r['full_name']}'")

    print()
    print("Fields NOT blocking export (nice-to-have):")
    print(
        "  gf_email — SMTP verification blocked (Spamhaus PBL), physical letter works without it"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Letter readiness audit")
    parser.add_argument("--domain", help="Check single domain only")
    parser.add_argument(
        "--export-ready-only",
        action="store_true",
        help="Show only export-ready records",
    )
    args = parser.parse_args()

    results = audit_records(
        domain_filter=args.domain,
        export_ready_only=args.export_ready_only,
    )
    print_report(results)
