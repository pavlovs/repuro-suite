"""Apply Excel BA9 state (payload.json) to a pipeline.db: Excel wins where non-empty; empty Excel never blanks DB.
Usage: python apply_excel_state.py <db_path> <payload.json> [--apply] [--diff out.json]
Runs identically on the local OneDrive DB and on the Fly machine (stdlib only).
"""

import json
import sqlite3
import sys

db_path, payload_path = sys.argv[1], sys.argv[2]
APPLY = "--apply" in sys.argv
diff_out = sys.argv[sys.argv.index("--diff") + 1] if "--diff" in sys.argv else None
ACTOR = "roman"

payload = json.load(open(payload_path, encoding="utf-8"))
con = sqlite3.connect(db_path, timeout=10)
con.row_factory = sqlite3.Row
con.execute("PRAGMA journal_mode=DELETE")
con.execute("PRAGMA busy_timeout=10000")


def norm(v):
    if v is None:
        return ""
    return " ".join(str(v).split())


changes = []  # (domain, field, old, new)
missing = []
for p in payload:
    dom = p["domain"]
    row = con.execute("SELECT * FROM company_records WHERE domain=?", (dom,)).fetchone()
    if row is None and p.get("old_domain"):
        row = con.execute(
            "SELECT * FROM company_records WHERE domain=?", (p["old_domain"],)
        ).fetchone()
        if row is not None:
            changes.append((p["old_domain"], "domain", p["old_domain"], dom))
            if APPLY:
                con.execute(
                    "UPDATE company_records SET domain=? WHERE domain=?",
                    (dom, p["old_domain"]),
                )
    if row is None:
        missing.append(dom)
        continue
    cur = dict(row)
    sets = {}
    for f, new in p["fields"].items():
        if norm(new) and norm(new) != norm(cur.get(f)):
            sets[f] = new
    bk = p.get("briefkopf")
    if (
        bk
        and norm(bk) != norm(cur.get("impressum_name") or cur.get("full_name"))
        and norm(bk) != norm(p["fields"].get("full_name"))
    ):
        sets["impressum_name"] = bk
    if "ma_count" in p and cur.get("ma_count") in (None, "", 0):
        sets["ma_count"] = p["ma_count"]
    av = p.get("av_comment")
    note = (
        f"AV: {av}" if av else p.get("note")
    )  # av_comment gets the AV prefix; note is appended verbatim
    if note:
        existing = cur.get("manual_note") or ""
        if note not in existing:
            sets["manual_note"] = (
                f"{existing} | {note}".strip(" |") if existing else note
            )
    for f, new in sets.items():
        changes.append((dom, f, cur.get(f), new))
    if sets and APPLY:
        cols = ", ".join(f"{f}=?" for f in sets)
        con.execute(
            f"UPDATE company_records SET {cols} WHERE domain=?", [*sets.values(), dom]
        )
        for f, new in sets.items():
            con.execute(
                "INSERT INTO activity_log (domain, actor, field, old_value, new_value) VALUES (?,?,?,?,?)",
                (
                    dom,
                    ACTOR,
                    f,
                    None if cur.get(f) is None else str(cur.get(f)),
                    str(new),
                ),
            )

if APPLY:
    con.commit()
con.close()

by_field = {}
for _, f, _, _ in changes:
    by_field[f] = by_field.get(f, 0) + 1
print(
    f"{'APPLIED' if APPLY else 'DRY-RUN'} {db_path}: {len(changes)} field changes on {len({c[0] for c in changes})} records; missing={missing}"
)
for f, n in sorted(by_field.items(), key=lambda x: -x[1]):
    print(f"  {f:22} {n}")
if diff_out:
    json.dump(
        [{"domain": d, "field": f, "old": o, "new": n} for d, f, o, n in changes],
        open(diff_out, "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
