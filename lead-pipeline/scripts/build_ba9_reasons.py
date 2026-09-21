"""BA9: derive Filter-Grund (evidence per record) + Reklassifiz. (category) from manual_note/ma_count/prio
so the Lead-Liste and the Drop-Off view explain every non-Prio-1 record. Also prints the batch waterfall
(tab v6 -> ALLEX today) with every count computed from the files, not recalled.
Usage: python scripts/build_ba9_reasons.py <v6.xlsx copy> -> data/exports/260921_ba9_reasons.json
"""

import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

import openpyxl

LP = Path(__file__).resolve().parent.parent
DB = LP / "data" / "pipeline.db"
OUT = LP / "data" / "exports" / "260921_ba9_reasons.json"
SMALL, BIG = "Prio 2 (small)", "Prio 2 (big)"
OUT_LABEL = {
    "Rechtsform": "OUT Rechtsform (BA9-Tab)",
    "OEM": "OUT OEM (BA9-Tab)",
    "intl": "OUT Ausland (BA9-Tab)",
    "already in group": "OUT bereits in Gruppe (BA9-Tab)",
    "duplicate": "Duplikat (BA9-Tab)",
    "400 MA": "Zu groß: >100 MA",
}


def de(n):
    return f"{n:,}".replace(",", ".")


def derive(prio, ma, note, domain):
    """Return (filter_reason, reclassify_reason)."""
    note = note or ""
    m = re.search(r"BA9-Tab v6: OUT \(([^)]+)\)", note)
    if m:
        why = m.group(1)
        ev = f"OUT ({why}) lt. BA9-Tab v6"
        if why == "400 MA":
            ev = "400 MA lt. BA9-Tab v6"
        return ev, OUT_LABEL.get(why, f"OUT {why} (BA9-Tab)")
    if prio == "Duplicate":
        return (
            "Duplikat lt. BA9-Tab v6"
            if "OUT (duplicate)" in note
            else "Duplikat (bereits in ALLEX)",
            "Duplikat",
        )
    # evidence for the headcount
    src = None
    m = re.search(r"(\d+) MA lt\. Jahresabschluss (\d{4})", note)
    if m:
        src = f"Jahresabschluss {m.group(2)}"
    elif re.search(r"MA lt\. v6 MASTER_Cleaning", note):
        src = "v6 MASTER_Cleaning"
    elif re.search(r"MA lt\. v6 ORBIS", note):
        src = "v6 ORBIS"
    elif re.search(r"\d+ MA lt\. http", note):
        src = "Website/Verzeichnis"
    extra = ", 100 % CENTROTEC SE" if "CENTROTEC" in note else ""
    if domain == "amedes-group.com":
        return "4.500 MA (Konzern) lt. Website", "Zu groß: >100 MA"
    if domain == "home.vitamed4u.de":
        return (
            "50+ MA lt. BA9-Tab v6 (Website: 51 Personen auf Teamseite)",
            "Zu groß: 50+ MA lt. BA9-Tab",
        )
    if prio == "Prio 1" and ma is None and not note.strip():
        return "Größe offen: nicht im BA9-Tab v6, nicht geprüft", ""
    if ma is not None and ma > 0 and src:
        ev = f"{de(ma)} MA lt. {src}{extra}"
        if prio == SMALL:
            return ev, "Zu klein: <20 MA lt. Register" if src not in (
                "Website/Verzeichnis",
            ) else "Zu klein: <20 MA lt. Web"
        if prio == BIG:
            return ev, "Zu groß: >100 MA"
        return "", ""  # Prio 1 with a figure: MA column speaks for itself
    m = re.search(r"Größenklasse ([\d\-]+)[^(]*\(([^)]+)\)", note)
    if m:
        ev = f"Größenklasse {m.group(1)} MA lt. {m.group(2).split(',')[0].strip()}"
        if domain == "wesemann.com":
            ev = (
                "Größenklasse 51-200 MA lt. LinkedIn, ca. 200 Beschäftigte lt. odeki.de"
            )
        if prio == SMALL:
            return ev, "Zu klein: <20 MA lt. Verzeichnis"
        if prio == BIG:
            return ev, "Zu groß: >100 MA"
        return f"Größe offen: {ev}", ""
    m = re.search(r"Bilanzsumme ([\d,]+ M€) \((\d{4})\)", note)
    if m and prio == SMALL:
        return (
            f"Bilanzsumme {m.group(1)} ({m.group(2)}), kein MA-Ausweis im Abschluss",
            "Zu klein: Bilanzsumme <0,7 M€",
        )
    if domain == "home.vitamed4u.de":
        return (
            "50+ MA lt. BA9-Tab v6 (Website: 51 Personen auf Teamseite)",
            "Zu groß: 50+ MA lt. BA9-Tab",
        )
    # Prio 1 without a figure
    if "0 MA auf" in note:
        return (
            "Größe offen: 0 MA im Abschluss ausgewiesen, Personal ggf. in Schwestergesellschaft",
            "",
        )
    if "kein Registertreffer" in note or "Namenskollision" in note:
        return "Größe offen: kein Registertreffer per Name, Web ohne MA-Angabe", ""
    if "kein Jahresabschluss unter dieser Entität" in note:
        return (
            "Größe offen: kein Abschluss unter dieser Entität, Web ohne MA-Angabe",
            "",
        )
    if m := re.search(r"(\d+) Personen auf Teamseite", note):
        return f"Größe offen: {m.group(1)} Personen auf Teamseite, keine MA-Angabe", ""
    if "keine MA-Angabe" in note or "Bilanzsumme" in note:
        m2 = re.search(r"Bilanzsumme ([\d,]+ M€) \((\d{4})\)", note)
        return (
            f"Größe offen: Bilanzsumme {m2.group(1)} ({m2.group(2)}), kein MA-Ausweis"
            if m2
            else "Größe offen: keine MA-Angabe in Register/Web"
        ), ""
    return "", ""


con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
recs = [
    dict(r)
    for r in con.execute(
        "SELECT domain, full_name, prio, ma_count, manual_note, filter_reason, reclassify_reason FROM company_records WHERE briefaktion='BA9'"
    )
]
rows, missing = [], []
for r in recs:
    fr, rr = derive(r["prio"], r["ma_count"], r["manual_note"], r["domain"])
    if not fr and not rr and r["prio"] != "Prio 1":
        missing.append((r["domain"], r["prio"], (r["manual_note"] or "")[:100]))
    fields = {}
    if fr:
        fields["filter_reason"] = fr
    if rr:
        fields["reclassify_reason"] = rr
    if fields:
        rows.append({"domain": r["domain"], "fields": fields})
    r["_fr"], r["_rr"] = fr, rr
json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("payload rows:", len(rows), "->", OUT)
print("non-Prio-1 without derived reason:", missing)

# ---- waterfall, computed
wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
tab = list(wb["BA9"].iter_rows(values_only=True))
hdr = list(tab[0])
tab_rows = [dict(zip(hdr, r)) for r in tab[1:] if any(c is not None for c in r)]
tab_out = collections.Counter(
    (str(r["Priorität"]).strip() if r["Priorität"] else "") for r in tab_rows
)
print("\n== BA9-Tab v6:", len(tab_rows), "rows |", dict(tab_out))
by_prio = collections.Counter(r["prio"] for r in recs)
print("== ALLEX BA9:", len(recs), dict(by_prio))
cat = collections.Counter(r["_rr"] for r in recs if r["_rr"])
print("== Reklassifiz. categories:")
for k, n in cat.most_common():
    print(f"   {n:3}  {k}")
p1 = [r for r in recs if r["prio"] == "Prio 1"]
print(
    "== Prio 1:",
    len(p1),
    "| with MA:",
    sum(1 for r in p1 if r["ma_count"]),
    "| Größe offen:",
    sum(1 for r in p1 if not r["ma_count"]),
)
print("   Größe offen:", [r["domain"] for r in p1 if not r["ma_count"]])
print(
    "   not in tab:",
    [
        r["domain"]
        for r in recs
        if r["domain"] not in {str(x["Domain"]).strip().lower() for x in tab_rows}
    ],
)
