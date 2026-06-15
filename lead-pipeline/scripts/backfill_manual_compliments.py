"""Backfill K1/K2 for MANUAL source records only."""

import sys
import time
import logging

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from src.config import settings
from src.pipeline import db as pipeline_db
from src.pipeline.export import _generate_compliment_cli

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)
    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "BEFORE manual-compliments")

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows_k1 = conn.execute(
            """SELECT domain, full_name, scraped_text
               FROM company_records
               WHERE source = 'MANUAL' AND klass IN ('A','B')
                 AND (compliment_draft IS NULL OR compliment_draft = '')
                 AND scraped_text IS NOT NULL AND scraped_text != ''"""
        ).fetchall()
        rows_k2 = conn.execute(
            """SELECT domain, full_name, scraped_text
               FROM company_records
               WHERE source = 'MANUAL' AND klass IN ('A','B')
                 AND compliment_draft IS NOT NULL AND compliment_draft != ''
                 AND (compliment_2 IS NULL OR compliment_2 = '')
                 AND scraped_text IS NOT NULL AND scraped_text != ''"""
        ).fetchall()

    print(
        f"\nMANUAL compliments — {len(rows_k1)} need K1+K2, {len(rows_k2)} need K2 only"
    )
    print("-" * 60)

    filled = 0
    errors = {"timeout": [], "parse_error": [], "empty": []}

    for i, row in enumerate(rows_k1, 1):
        rec = dict(row)
        k1, k2 = _generate_compliment_cli(
            rec["full_name"] or rec["domain"], rec["scraped_text"]
        )
        if k1 or k2:
            with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
                pipeline_db.update_compliments(conn, rec["domain"], k1, k2)
            filled += 1
            print(f"  [{i}/{len(rows_k1)}] {rec['domain']}: OK")
        else:
            errors["empty"].append(rec["domain"])
            print(f"  [{i}/{len(rows_k1)}] {rec['domain']}: FAILED")
        if i < len(rows_k1):
            time.sleep(0.5)

    for i, row in enumerate(rows_k2, 1):
        rec = dict(row)
        from src.pipeline.backfill import _generate_k2_only_cli

        k2 = _generate_k2_only_cli(
            rec["full_name"] or rec["domain"], rec["scraped_text"]
        )
        if k2:
            with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
                conn.execute(
                    """UPDATE company_records SET compliment_2 = ?
                       WHERE domain = ? AND (compliment_2 IS NULL OR compliment_2 = '')""",
                    (k2, rec["domain"]),
                )
            filled += 1
            print(f"  [K2 {i}/{len(rows_k2)}] {rec['domain']}: OK")
        else:
            errors["empty"].append(rec["domain"])
            print(f"  [K2 {i}/{len(rows_k2)}] {rec['domain']}: FAILED")
        if i < len(rows_k2):
            time.sleep(0.5)

    total_errors = sum(len(v) for v in errors.values())
    print(f"\n  Filled: {filled}/{len(rows_k1) + len(rows_k2)} MANUAL records")
    if total_errors:
        print(f"  Failed: {total_errors}")
        for etype, domains in errors.items():
            if domains:
                print(f"    {etype}: {', '.join(domains)}")

    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "AFTER manual-compliments")


if __name__ == "__main__":
    main()
