"""Force-rescrape impressum for MANUAL records missing street/plz_ort.

Re-fetches even when KB already has an (empty) entry, then runs parse_impressum_address.
Reports which domains got usable address data.
"""

import sys
import time

sys.path.insert(0, "src")

import sqlite3
from config import settings
from pipeline.normalize import parse_impressum_address
from utils.web import fetch_impressum_text

kb_path = settings.PIPELINE_DB_PATH.parent / "knowledge_base.db"

# Find MANUAL records missing street
with sqlite3.connect(settings.PIPELINE_DB_PATH) as db:
    db.row_factory = sqlite3.Row
    missing = db.execute(
        """SELECT domain FROM company_records
           WHERE source='MANUAL' AND filter_pass=1
             AND (street IS NULL OR TRIM(street) = '')"""
    ).fetchall()

domains = [r["domain"] for r in missing]
print(f"Domains to re-scrape: {len(domains)}")
print()

kb = sqlite3.connect(str(kb_path))
kb.row_factory = sqlite3.Row

results = []
for i, domain in enumerate(domains, 1):
    print(f"[{i}/{len(domains)}] {domain} ... ", end="", flush=True)

    # Force fresh fetch (ignore cached empty content)
    imp_text = fetch_impressum_text(domain)

    if imp_text:
        # Upsert into documents table
        existing = kb.execute(
            "SELECT id FROM documents WHERE domain=? AND doc_type='impressum'",
            (domain,),
        ).fetchone()
        if existing:
            kb.execute(
                "UPDATE documents SET content=? WHERE domain=? AND doc_type='impressum'",
                (imp_text, domain),
            )
        else:
            kb.execute(
                "INSERT INTO documents (domain, hrb_number, doc_type, content) VALUES (?,NULL,'impressum',?)",
                (domain, imp_text),
            )
        kb.commit()

        street, plz_ort = parse_impressum_address(imp_text)
        status = (
            f"OK street={street!r} plz_ort={plz_ort!r}"
            if (street or plz_ort)
            else f"scraped {len(imp_text)} chars but no address parsed"
        )
    else:
        status = "EMPTY (fetch returned nothing)"

    print(status)
    results.append((domain, imp_text, status))

    if i < len(domains):
        time.sleep(1.5)

kb.close()

print()
print("=== Summary ===")
got_address = [
    (d, s)
    for d, _, s in results
    if "street=" in s and "None" not in s.split("street=")[1][:10]
]
got_scrape = [(d, s) for d, t, s in results if t and "no address" in s]
empty = [(d, s) for d, t, s in results if not t]
print(f"  Got address:       {len(got_address)}")
print(f"  Scraped, no parse: {len(got_scrape)}")
print(f"  Empty (no fetch):  {len(empty)}")
print()
print("Now run: python pipeline.py normalize")
