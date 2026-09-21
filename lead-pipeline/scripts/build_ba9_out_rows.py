"""BA9 tab rows marked OUT (Priorität column) -> ALLEX prio + note, so the Prio 1 queue equals the 70 real targets.
Also notes BA9 records that are not in the tab at all. Payload for apply_excel_state.py.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

import openpyxl

LP = Path(__file__).resolve().parent.parent
XLSX = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else LP / "260518_Repuro_Medtech_Targets_v6.xlsx"
)  # pass a copy when Excel holds the lock
DB = LP / "data" / "pipeline.db"
OUT = LP / "data" / "exports" / "260917_ba9_out_rows.json"
MAP = {  # Excel OUT reason -> ALLEX prio
    "OUT (Rechtsform)": "Prio 2 (other)",
    "OUT (OEM)": "Prio 2 (other)",
    "OUT (duplicate)": "Duplicate",
    "OUT (400 MA)": "Prio 2 (big)",
    "OUT (intl)": "Prio 2 (intl)",
    "OUT (already in group)": "Excluded",
}


def norm_dom(d):
    s = str(d or "").strip().lower()
    s = re.sub(r"^https?://(www\.)?", "", s)
    return s.split("/")[0].strip() or None


wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
rows = list(wb["BA9"].iter_rows(values_only=True))
hdr = list(rows[0])
tab = [dict(zip(hdr, r)) for r in rows[1:] if any(c is not None for c in r)]
payload, tab_doms = [], set()
for r in tab:
    d = norm_dom(r["Domain"])
    tab_doms.add(d)
    p = str(r["Priorität"] or "").strip()
    if p.startswith("OUT"):
        prio = MAP.get(p)
        if not prio:
            print("unmapped OUT reason:", p, d)
            continue
        payload.append(
            {"domain": d, "fields": {"prio": prio}, "note": f"BA9-Tab v6: {p} → {prio}"}
        )
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
for d, name, prio in con.execute(
    "SELECT domain, full_name, prio FROM company_records WHERE briefaktion='BA9'"
):
    if d not in tab_doms:
        payload.append(
            {
                "domain": d,
                "fields": {},
                "note": "BA9-Tab v6: nicht im Tab enthalten (Status offen, prio unverändert)",
            }
        )
        print("not in tab:", d, name, prio)
json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(
    "rows:",
    len(payload),
    "| prio set:",
    sum(1 for x in payload if x["fields"]),
    "->",
    OUT,
)
for x in payload:
    if x["fields"]:
        print(f"  {x['domain']:28} {x['fields']['prio']:16} {x['note']}")
