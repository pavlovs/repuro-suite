"""Fill ma_count (+ revenue_tsd_eur if empty) for BA9 records via OpenRegister: autocomplete (1 cr) -> financials (10 cr).
Usage: python scripts/ba9_fill_employees.py <excel_state_payload.json> [--cap 1300] [--dry-run]
Writes: local pipeline.db (ma_count, revenue_tsd_eur, activity_log), openregister_screen/openregister_financials rows,
        data/exports/<stamp>_ba9_employees.json (payload for push_excel_state_to_fly.sh).
"""

import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

LP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LP / "tools" / "openregister_screen_2026_09"))
import orclient as oc  # noqa: E402  (cache = data/openregister_cache.db, credits logged there)

DB = LP / "data" / "pipeline.db"
PAYLOAD = Path(sys.argv[1])
CAP = int(sys.argv[sys.argv.index("--cap") + 1]) if "--cap" in sys.argv else 1300
DRY = "--dry-run" in sys.argv
STAMP = dt.date.today().strftime("%y%m%d")
KNOWN_CID = {  # matched by name in the Sept screen, financials never fetched
    "myntmedicalsystems.de": "MYNT Medical Systems GmbH",
    "endomed.de": "Endomed Endoskopie + Hygiene GmbH",
    "memax.de": "medimex GmbH",
    "moeller-medical.com": "Möller Medical GmbH",
}
LEGAL = r"(gmbh\s*&\s*co\.?\s*kg|ug\s*\(haftungsbeschr[aä]nkt\)|gmbh|mbh|ag|se|kg|ohg|e\.?\s?k\.?|gesellschaft\s+f[uü]r|gesellschaft\s+mit\s+beschr[aä]nkter\s+haftung)"
GENERIC = {
    "medical",
    "medizintechnik",
    "gmbh",
    "service",
    "systems",
    "solutions",
    "deutschland",
    "germany",
    "group",
    "technik",
    "handel",
    "vertrieb",
}


def nn(s):
    s = (
        (s or "")
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    s = re.sub(r"\b" + LEGAL + r"\b", " ", s)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def toks(s):
    return {t for t in nn(s).split() if len(t) >= 3}


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
con.execute("PRAGMA journal_mode=DELETE")
domains = [p["domain"] for p in json.load(open(PAYLOAD, encoding="utf-8"))]
recs = [
    dict(r)
    for r in con.execute(
        f"SELECT domain, full_name, impressum_name, plz_ort, city, ma_count, revenue_tsd_eur FROM company_records WHERE domain IN ({','.join('?' * len(domains))}) AND ma_count IS NULL",
        domains,
    )
]
print(
    f"targets without MA: {len(recs)} | credits before: {oc.credits_used()} | cap this run: {CAP}"
)
start_credits = oc.credits_used()
screen_cids = {
    r[1]: r[0] for r in con.execute("SELECT company_id, name FROM openregister_screen")
}


def pick(results, name, plz):
    best, best_s = None, 0
    tn = toks(name)
    for r in results or []:
        rn = r.get("name") or ""
        s = 0
        if nn(rn) == nn(name):
            s = 100
        else:
            shared = tn & toks(rn)
            if shared - GENERIC:
                s = 40 + 10 * len(shared)
        if plz and (r.get("address") or {}).get("postal_code") == plz:
            s += 30
        if r.get("active") is False:
            s -= 25
        if s > best_s:
            best, best_s = r, s
    return (best, best_s) if best_s >= 60 else (None, best_s)


out, unresolved, spent_guard = [], [], False
for r in recs:
    if oc.credits_used() - start_credits > CAP:
        spent_guard = True
        unresolved.append((r["domain"], "cap reached"))
        continue
    name = r["impressum_name"] or r["full_name"]
    plz = (
        (re.match(r"\d{5}", r["plz_ort"] or "") or [None])[0] if r["plz_ort"] else None
    )
    cid, how = None, None
    if r["domain"] in KNOWN_CID and KNOWN_CID[r["domain"]] in screen_cids:
        cid, how = screen_cids[KNOWN_CID[r["domain"]]], "screen"
    else:
        if DRY:
            unresolved.append((r["domain"], "dry-run"))
            continue
        for q in (name, " ".join(nn(name).split()[:3])):
            if not q:
                continue
            ac = oc.autocomplete(q)
            best, s = pick(ac.get("results"), name, plz)
            if best:
                cid, how = best["company_id"], f"ac:{q[:30]} s={s} -> {best['name']}"
                break
    if not cid:
        unresolved.append((r["domain"], f"no autocomplete match for '{name}'"))
        continue
    if DRY:
        out.append({"domain": r["domain"], "cid": cid, "how": how})
        continue
    fin = oc.financials(cid)
    ind = sorted(
        fin.get("indicators") or [], key=lambda x: x.get("date") or "", reverse=True
    )
    emp = next(
        ((x["employees"], x["date"]) for x in ind if x.get("employees") is not None),
        (None, None),
    )
    rev = next(
        ((x["revenue"], x["date"]) for x in ind if x.get("revenue") is not None),
        (None, None),
    )
    row = {
        "domain": r["domain"],
        "cid": cid,
        "how": how,
        "name_or": cid,
        "ma": emp[0],
        "ma_fy": emp[1],
        "rev_tsd": round(rev[0] / 1e5) if rev[0] else None,
        "rev_fy": rev[1],
        "n_fy": len(ind),
    }
    out.append(row)
    for x in ind:  # persist so the next lookup finds it
        keys = [
            "revenue",
            "gross_profit",
            "ebitda",
            "ebit",
            "income_before_tax",
            "net_income",
            "employees",
            "equity",
            "balance_sheet_total",
            "cash",
            "bank_debt",
            "liabilities",
            "salaries",
            "materials",
            "operating_depreciation",
            "taxes",
        ]
        vals = [
            x.get(k) if k == "employees" or x.get(k) is None else x[k] / 1e8
            for k in keys
        ]
        con.execute(
            "INSERT OR REPLACE INTO openregister_financials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, x.get("date"), *vals),
        )
    con.execute(
        "INSERT OR IGNORE INTO openregister_screen (company_id, name, cls_verdict, employees, fy, pipeline_contact, screened_at) VALUES (?,?,?,?,?,?,?)",
        (cid, name, "BA9", emp[0], emp[1], r["domain"], dt.date.today().isoformat()),
    )
    if emp[0] is not None:
        con.execute(
            "UPDATE company_records SET ma_count=? WHERE domain=? AND ma_count IS NULL",
            (emp[0], r["domain"]),
        )
        con.execute(
            "INSERT INTO activity_log (domain, actor, field, old_value, new_value) VALUES (?,?,?,?,?)",
            (r["domain"], "roman", "ma_count", None, str(emp[0])),
        )
    if row["rev_tsd"] and r["revenue_tsd_eur"] in (None, 0):
        con.execute(
            "UPDATE company_records SET revenue_tsd_eur=? WHERE domain=? AND revenue_tsd_eur IS NULL",
            (row["rev_tsd"], r["domain"]),
        )
        con.execute(
            "INSERT INTO activity_log (domain, actor, field, old_value, new_value) VALUES (?,?,?,?,?)",
            (r["domain"], "roman", "revenue_tsd_eur", None, str(row["rev_tsd"])),
        )
    con.commit()
    print(
        f"  {r['domain']:28} MA={emp[0]!s:5} FY={emp[1]} rev_tsd={row['rev_tsd']} via {how}"
    )

found = [o for o in out if o.get("ma") is not None]
print(
    f"\nRESULT: MA found {len(found)} / {len(recs)} | financials without employee figure: {sum(1 for o in out if 'ma' in o and o['ma'] is None)} | unresolved: {len(unresolved)} | credits this run: {oc.credits_used() - start_credits}{' (CAP HIT)' if spent_guard else ''}"
)
for d, why in unresolved:
    print("  UNRESOLVED", d, "|", why)
if not DRY:
    prod = [
        {
            "domain": o["domain"],
            "fields": ({"revenue_tsd_eur": o["rev_tsd"]} if o.get("rev_tsd") else {}),
            **(
                {
                    "ma_count": o["ma"],
                    "ma_source": f"OpenRegister {o['cid']} FY{o['ma_fy']}",
                }
                if o.get("ma") is not None
                else {}
            ),
        }
        for o in out
        if o.get("ma") is not None or o.get("rev_tsd")
    ]
    pp = LP / "data" / "exports" / f"{STAMP}_ba9_employees.json"
    json.dump(prod, open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(
        {"out": out, "unresolved": unresolved},
        open(
            LP / "data" / "exports" / f"{STAMP}_ba9_employees_log.json",
            "w",
            encoding="utf-8",
        ),
        ensure_ascii=False,
        indent=1,
    )
    print("prod payload:", pp, "| rows:", len(prod))
