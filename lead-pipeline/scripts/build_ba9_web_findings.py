"""Turn web-check findings (JSON array from the research agents) into an apply_excel_state payload.
Usage: python scripts/build_ba9_web_findings.py <findings.json> -> data/exports/260917_ba9_web_findings.json
Rules: ma_count only from a concrete number with confidence high/medium (never from a range or a team-photo count);
       < 20 MA -> Prio 2 (small); every company gets a one-line note with source.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

LP = Path(__file__).resolve().parent.parent
DB = LP / "data" / "pipeline.db"
OUT = LP / "data" / "exports" / "260917_ba9_web_findings.json"
TAG = "Web 17.09:"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
findings = []
for p in sys.argv[1:]:  # one or more JSON arrays (one per research agent)
    findings += json.load(open(p, encoding="utf-8"))
json.dump(
    findings,
    open(LP / "data" / "exports" / "260917_ba9_web_raw.json", "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=1,
)
rows = []
for f in findings:
    d = f["domain"]
    cur = con.execute(
        "SELECT ma_count, prio FROM company_records WHERE domain=?", (d,)
    ).fetchone()
    if not cur:
        print("not in DB:", d)
        continue
    fields, parts = {}, []
    n, conf = f.get("employees_number"), f.get("confidence")
    rng = f.get("employees_range") or ""
    m = re.match(r"\s*(\d+)\s*-\s*(\d+)", rng)
    hi = int(m.group(2)) if m else None
    if n is not None and conf in ("high", "medium"):
        parts.append(
            f"{n} MA lt. {f.get('source_url')}"
            + (f" ({f['employees_as_of']})" if f.get("employees_as_of") else "")
        )
        if cur[0] in (None, 0):
            fields["ma_count"] = int(n)
        if int(n) < 20:
            fields["prio"] = "Prio 2 (small)"
            parts.append("→ Prio 2 (small), MA < 20")
        elif int(n) > 100:
            fields["prio"] = "Prio 2 (big)"
            parts.append("→ Prio 2 (big)")
        elif cur[1] == "Prio 2 (small)":
            fields["prio"] = "Prio 1"
            parts.append(
                "→ zurück auf Prio 1 (Web-MA ≥ 20 schlägt Bilanzsummen-Schätzung)"
            )
    elif rng:
        parts.append(f"Größenklasse {rng} ({f.get('source_url')})")
        if hi is not None and hi < 20:
            fields["prio"] = "Prio 2 (small)"
            parts.append("→ Prio 2 (small), Größenklasse < 20")
        elif hi is not None and hi >= 150:
            fields["prio"] = "Prio 2 (big)"
            parts.append("→ Prio 2 (big)")
    elif n is not None:
        parts.append(
            f"{n} lt. {f.get('source_url')} (schwache Evidenz, nicht übernommen)"
        )
    elif f.get("team_page_count"):
        parts.append(
            f"{f['team_page_count']} Personen auf Teamseite ({f.get('team_page_url')}), keine MA-Angabe"
        )
    else:
        parts.append("keine MA-Angabe auf Website/Verzeichnissen gefunden")
    if f.get("revenue_stated"):
        parts.append(f"Umsatz lt. Website: {f['revenue_stated']}")
    if f.get("business_note"):
        parts.append(f"Geschäft: {f['business_note']}")
    if f.get("impressum_name"):
        parts.append(f"Impressum: {f['impressum_name']}")
    if f.get("evidence_quote") and n is not None:
        parts.append(f'Zitat: "{f["evidence_quote"][:120]}"')
    rows.append({"domain": d, "fields": fields, "note": f"{TAG} " + "; ".join(parts)})
json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(
    "rows:",
    len(rows),
    "| ma_count set:",
    sum(1 for r in rows if "ma_count" in r["fields"]),
    "| prio small:",
    sum(1 for r in rows if r["fields"].get("prio")),
    "->",
    OUT,
)
for r in rows:
    print(f"  {r['domain']:28} {r['fields']}  {r['note'][:110]}")
