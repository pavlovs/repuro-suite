"""Roman's rule 17.09: BA9 records with a register headcount below 20 -> 'Prio 2 (small)'. Payload for apply_excel_state.py."""

import json
import sqlite3
from pathlib import Path

LP = Path(__file__).resolve().parent.parent
DB = LP / "data" / "pipeline.db"
OUT = LP / "data" / "exports" / "260917_ba9_small_rule.json"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = []
for dom, ma, prio in con.execute(
    "SELECT domain, ma_count, prio FROM company_records WHERE briefaktion='BA9' AND ma_count IS NOT NULL AND ma_count > 0 AND ma_count < 20"
):
    rows.append(
        {
            "domain": dom,
            "fields": {"prio": "Prio 2 (small)"},
            "note": f"Regel RD 17.09: {ma} MA < 20 → Prio 2 (small)",
        }
    )
json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("rows:", len(rows), "->", OUT)
