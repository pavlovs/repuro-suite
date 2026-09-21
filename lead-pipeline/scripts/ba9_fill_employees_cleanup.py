"""Post-run cleanup for ba9_fill_employees.py (2026-09-17): filed 0 employees -> no figure; unlink wrong-entity matches."""

import json
import sqlite3
from pathlib import Path

LP = Path(__file__).resolve().parent.parent
DB = LP / "data" / "pipeline.db"
PAYLOAD = LP / "data" / "exports" / "260917_ba9_employees.json"
ZERO = ["iq-medtec.de", "memax.de"]
WRONG = [
    "bergmann-solingen.de",
    "schupp.shop",
    "memax.de",  # screen matched medimex GmbH Limburg; web check 17.09: different company
]  # autocomplete/screen picked a different legal entity

con = sqlite3.connect(DB)
con.execute("PRAGMA journal_mode=DELETE")
for d in ZERO:
    cur = con.execute(
        "SELECT ma_count FROM company_records WHERE domain=?", (d,)
    ).fetchone()
    if cur and cur[0] == 0:
        con.execute("UPDATE company_records SET ma_count=NULL WHERE domain=?", (d,))
        con.execute(
            "INSERT INTO activity_log (domain, actor, field, old_value, new_value) VALUES (?,?,?,?,?)",
            (d, "roman", "ma_count", "0", None),
        )
        con.execute(
            "UPDATE openregister_screen SET employees=NULL WHERE pipeline_contact=?",
            (d,),
        )
        print("ma_count 0 -> NULL:", d)
for d in WRONG:
    n = con.execute(
        "DELETE FROM openregister_screen WHERE pipeline_contact=? AND cls_verdict='BA9'",
        (d,),
    ).rowcount
    print("unlinked screen row:", d, n)
con.commit()
p = [
    r
    for r in json.load(open(PAYLOAD, encoding="utf-8"))
    if not (r["domain"] in ZERO and r.get("ma_count") == 0)
]
json.dump(p, open(PAYLOAD, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(
    "prod payload rows:",
    len(p),
    "| local ma_count BA9:",
    con.execute(
        "SELECT COUNT(*) FROM company_records WHERE briefaktion='BA9' AND ma_count IS NOT NULL"
    ).fetchone()[0],
)
con.close()
