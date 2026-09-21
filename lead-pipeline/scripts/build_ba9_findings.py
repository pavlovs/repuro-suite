"""Build the 17.09 OpenRegister size-findings payload for BA9 (notes + prio flags) -> data/exports/260917_ba9_findings.json.
Applied with apply_excel_state.py locally and via push_excel_state_to_fly.sh on prod.
"""

import json
import sqlite3
from pathlib import Path

LP = Path(__file__).resolve().parent.parent
DB = LP / "data" / "pipeline.db"
LOG = LP / "data" / "exports" / "260917_ba9_employees_log.json"
OUT = LP / "data" / "exports" / "260917_ba9_findings.json"
TAG = "OpenRegister 17.09:"
SMALL, BIG = "Prio 2 (small)", "Prio 2 (big)"


def meur(v):
    return f"{v:.2f}".replace(".", ",") + " M€"


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
log = json.load(open(LOG, encoding="utf-8"))
rows = []


def add(domain, note, prio=None):
    r = {"domain": domain, "fields": {}, "note": f"{TAG} {note}"}
    if prio:
        r["fields"]["prio"] = prio
    rows.append(r)


for o in log["out"]:
    d, cid = o["domain"], o["cid"]
    if d in ("bergmann-solingen.de", "schupp.shop"):
        add(
            d,
            "keine eindeutige Register-Entität per Name (Namenskollision), Größe offen",
        )
        continue
    level = "KG-Ebene" if "-HRA-" in cid else "GmbH-Ebene"
    if o.get("ma") is not None and o["ma"] > 0:
        fy = o["ma_fy"][:4]
        if o["ma"] <= 5:
            add(d, f"{o['ma']} MA lt. Jahresabschluss {fy} → zu klein", SMALL)
        elif o["ma"] > 100:
            extra = (
                ", Umsatz 40,1 M€, 100 % CENTROTEC SE"
                if d == "moeller-medical.com"
                else ""
            )
            add(
                d,
                f"{o['ma']} MA lt. Jahresabschluss {fy}{extra} → zu groß für BA9",
                BIG,
            )
        else:
            add(d, f"{o['ma']} MA lt. Jahresabschluss {fy}")
        continue
    if o.get("ma") == 0:
        add(
            d,
            f"0 MA auf {level} ausgewiesen ({o['ma_fy'][:7]}), Personal ggf. in anderer Gesellschaft; Größe offen",
        )
        continue
    fin = con.execute(
        "SELECT fy, balance_sheet_total FROM openregister_financials WHERE company_id=? AND balance_sheet_total IS NOT NULL ORDER BY fy DESC LIMIT 1",
        (cid,),
    ).fetchone()
    if not fin:
        if d == "amedes-group.com":
            add(
                d,
                "kein Einzelabschluss unter dieser Entität; amedes-Laborkonzern (Konzernabschluss) → zu groß für BA9",
                BIG,
            )
        else:
            add(d, "kein Jahresabschluss unter dieser Entität gefunden, Größe offen")
        continue
    fy, bst = fin
    b = meur(bst)
    if bst < 0.7:
        add(
            d,
            f"Bilanzsumme {b} ({fy[:4]}), kein MA-Ausweis ({level}) → zu klein",
            SMALL,
        )
    elif bst < 2.5:
        add(d, f"Bilanzsumme {b} ({fy[:4]}), kein MA-Ausweis ({level}) → ca. 10-15 MA")
    else:
        add(
            d,
            f"Bilanzsumme {b} ({fy[:4]}), kein MA-Ausweis (kleine KapG, {level}) → 20-50 MA plausibel, Website/LinkedIn prüfen",
        )
for d, why in log["unresolved"]:
    add(d, "kein Registertreffer per Name, Größe offen")
# the 6 with MA from the first pass (Excel-state payload)
for d, ma, src in [
    ("aescologic.de", 65, "v6 MASTER_Cleaning"),
    ("integromed.de", 26, "Jahresabschluss 2025"),
    ("primus-ultraschall.de", 14, "Jahresabschluss 2025"),
    ("omnilab.de", 137, "Jahresabschluss 2023"),
    ("iriseye.de", 7, "Jahresabschluss 2021"),
    ("lmt-medshop.de", 7, "v6 ORBIS"),
]:
    if ma > 100:
        add(d, f"{ma} MA lt. {src} → zu groß für BA9", BIG)
    else:
        add(d, f"{ma} MA lt. {src}")

json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(
    "rows:",
    len(rows),
    "| prio small:",
    sum(1 for r in rows if r["fields"].get("prio") == SMALL),
    "| prio big:",
    sum(1 for r in rows if r["fields"].get("prio") == BIG),
)
for r in rows:
    if r["fields"].get("prio"):
        print(f"  {r['fields']['prio']:15} {r['domain']:28} {r['note']}")
print("->", OUT)
