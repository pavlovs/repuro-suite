"""Regenerate mehrwerte for MANUAL records only (source='MANUAL' AND filter_pass=1 AND klass IN ('A','B'))."""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from src.pipeline.backfill import (
    _LEISTUNG_PROMPT,
    _call_claude_cli,
    _parse_json_response,
)
from src.config import settings
from src.pipeline import db as pipeline_db


def main():
    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows = conn.execute(
            """SELECT domain, full_name, scraped_text
               FROM company_records
               WHERE source = 'MANUAL'
                 AND filter_pass = 1
                 AND klass IN ('A','B')
                 AND scraped_text IS NOT NULL AND scraped_text != ''"""
        ).fetchall()

    eligible = [dict(r) for r in rows]
    print(f"Regenerating mehrwerte for {len(eligible)} MANUAL records...")

    filled = errors = 0
    for i, rec in enumerate(eligible, 1):
        prompt = _LEISTUNG_PROMPT.format(
            full_name=rec["full_name"] or rec["domain"],
            scraped_text=(rec["scraped_text"] or "")[:2000],
        )
        raw, err_type = _call_claude_cli(prompt)
        if err_type:
            print(f"  [{i}/{len(eligible)}] {rec['domain']}: {err_type}")
            errors += 1
            continue
        data = _parse_json_response(raw)
        if not data:
            print(f"  [{i}/{len(eligible)}] {rec['domain']}: parse_error")
            errors += 1
            continue

        mehrwerte = str(data.get("mehrwerte", ""))[:400]
        if mehrwerte:
            with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
                conn.execute(
                    "UPDATE company_records SET mehrwerte = ? WHERE domain = ?",
                    (mehrwerte, rec["domain"]),
                )
            print(f"  [{i}/{len(eligible)}] {rec['domain']}: OK — {mehrwerte[:60]}")
            filled += 1
        else:
            print(f"  [{i}/{len(eligible)}] {rec['domain']}: empty mehrwerte")
            errors += 1

    print(f"\nDone: {filled} filled, {errors} errors")

    # Verify against MANUAL cohort specifically
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        result = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN mehrwerte IS NOT NULL AND mehrwerte != '' THEN 1 ELSE 0 END) as filled
               FROM company_records
               WHERE source = 'MANUAL' AND filter_pass = 1 AND klass IN ('A','B')"""
        ).fetchone()
    print(
        f"MANUAL cohort mehrwerte: {result['filled']}/{result['total']} filled "
        f"({100 * result['filled'] // result['total'] if result['total'] else 0}%)"
    )

    # Sample 5 values for quality review
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        samples = conn.execute(
            """SELECT domain, full_name, mehrwerte
               FROM company_records
               WHERE source = 'MANUAL' AND filter_pass = 1 AND klass IN ('A','B')
                 AND mehrwerte IS NOT NULL AND mehrwerte != ''
               ORDER BY RANDOM()
               LIMIT 5"""
        ).fetchall()
    print("\nSample mehrwerte (random 5 for quality review):")
    for s in samples:
        print(f"  {s['domain']} ({s['full_name'] or ''}):")
        print(f"    → {s['mehrwerte']}")


if __name__ == "__main__":
    main()
