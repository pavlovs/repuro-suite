"""M37 T8: build data/input/261110_BA11_src.xlsx (sheet BA11_src) from the four OEM sources.

Sources (read-only):
  1. CLAUDE_COWORK/_drafts/261105_Repuro_OEM-light_Targets.xlsx, tab Targets (domain from the
     Source URL when it is the company's own site)
  2. CLAUDE_COWORK/_drafts/261028_Repuro_OEM-light_Longlist.xlsx, tab Longlist (no domain column:
     matched by name to tests/fixtures/oem_fixture.json or source 1, else skipped and counted)
  3. CLAUDE_COWORK/_drafts/260930_Target_Push/L_OEM_targets.csv + S_OEM_candidates.csv (column website)
  4. 260518_Repuro_Medtech_Targets_v6.xlsx (project root), tab AV longlist, Alex AI = 'OEM'

Dedupe on normalized domain against company_records (read-only) and within the sheet (first source
wins, later contact statuses are appended to the note). Layout matches `ingest-manual` defaults:
row 1 title, row 2 header, data from row 3; B source, D domain, E name, H klass (empty), I note.

Usage: python scripts/m37_build_ba11_src.py [--out PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.pipeline.ingest import normalize_domain  # noqa: E402

DRAFTS = Path(r"C:\Users\X1\Documents\CLAUDE_COWORK\_drafts")
SRC_TARGETS = DRAFTS / "261105_Repuro_OEM-light_Targets.xlsx"
SRC_LONGLIST = DRAFTS / "261028_Repuro_OEM-light_Longlist.xlsx"
SRC_PUSH = [
    DRAFTS / "260930_Target_Push" / "L_OEM_targets.csv",
    DRAFTS / "260930_Target_Push" / "S_OEM_candidates.csv",
]
SRC_AV = ROOT / "260518_Repuro_Medtech_Targets_v6.xlsx"
FIXTURE = ROOT / "tests" / "fixtures" / "oem_fixture.json"
DEFAULT_OUT = ROOT / "data" / "input" / "261110_BA11_src.xlsx"

# Source URLs that are not the company's own site
_FOREIGN_HOSTS = ("tga.gov.au", "adlershof.de", "northdata", "openregister", "medicalexpo")

_LEGAL = re.compile(
    r"\b(gmbh\s*&\s*co\.?\s*kg|gmbh\s*u\.?\s*co\.?\s*kg|gmbh\s*\+\s*co\.?\s*kg|gmbh|ag|kg|mbh|co)\b"
)


def name_key(name: str) -> str:
    """Normalized company name for cross-source matching (umlauts folded to ascii forms)."""
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = _LEGAL.sub(" ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def own_site_domain(source: object) -> str | None:
    """Domain from a Source cell when it is a URL of the company's own site."""
    text = str(source or "").strip()
    if not text.lower().startswith("http"):
        return None
    host = (urlparse(text).hostname or "").lower()
    if not host or any(f in host for f in _FOREIGN_HOSTS):
        return None
    host = host.removeprefix("www.")
    labels = host.split(".")
    if len(labels) > 2:  # shop.ossenberg.com -> ossenberg.com
        host = ".".join(labels[-2:])
    return normalize_domain(host)


def load_rows() -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    stats: dict[str, int] = {}
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["companies"]
    by_name: dict[str, str] = {name_key(c["name"]): c["domain"] for c in fixture if c["domain"]}

    # 1. 05.11 Targets
    wb = openpyxl.load_workbook(SRC_TARGETS, read_only=True, data_only=True)
    n_rows = no_dom = 0
    for r in list(wb["Targets"].iter_rows(values_only=True))[1:]:
        if not r[1]:
            continue
        n_rows += 1
        dom = own_site_domain(r[12]) or by_name.get(name_key(r[1]))
        if not dom:
            no_dom += 1
            continue
        by_name.setdefault(name_key(r[1]), dom)
        rows.append({
            "source": "OEM-light Targets 05.11",
            "file": SRC_TARGETS.name,
            "domain": dom,
            "name": str(r[1]).strip(),
            "city": str(r[2] or "").strip(),
            "category": str(r[0] or "").strip(),
            "note": f"05.11 class: {r[0]}; contact: {r[10] or 'none'}",
        })
    wb.close()
    stats["targets_0511_rows"], stats["targets_0511_no_domain"] = n_rows, no_dom

    # 2. 28.10 Longlist (name match only)
    wb = openpyxl.load_workbook(SRC_LONGLIST, read_only=True, data_only=True)
    n_rows = no_dom = 0
    for r in list(wb["Longlist"].iter_rows(values_only=True))[1:]:
        if not r[2]:
            continue
        n_rows += 1
        dom = by_name.get(name_key(r[2]))
        if not dom:
            no_dom += 1
            continue
        rows.append({
            "source": "OEM-light Longlist 28.10",
            "file": SRC_LONGLIST.name,
            "domain": dom,
            "name": str(r[2]).strip(),
            "city": str(r[3] or "").strip(),
            "category": f"Grade {r[1]}",
            "note": f"28.10 grade {r[1]}; contact: {r[13] or 'none'}",
        })
    wb.close()
    stats["longlist_2810_rows"], stats["longlist_2810_no_domain"] = n_rows, no_dom

    # 3. Target Push 30.09 CSVs
    for path in SRC_PUSH:
        n_rows = no_dom = 0
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                n_rows += 1
                dom = normalize_domain(r.get("website"))
                if not dom:
                    no_dom += 1
                    continue
                rows.append({
                    "source": f"Target Push 30.09 {path.stem}",
                    "file": path.name,
                    "domain": dom,
                    "name": (r.get("company") or "").strip(),
                    "city": (r.get("city") or "").strip(),
                    "category": f"market {r.get('market', '')}",
                    "note": f"30.09 prior contact: {(r.get('prior_contact') or 'none').strip()}",
                })
        stats[f"{path.stem}_rows"], stats[f"{path.stem}_no_domain"] = n_rows, no_dom

    # 4. AV longlist, Alex AI = OEM
    wb = openpyxl.load_workbook(SRC_AV, read_only=True, data_only=True)
    all_rows = list(wb["AV longlist"].iter_rows(values_only=True))
    wb.close()
    hdr = {h: i for i, h in enumerate(all_rows[1]) if h}
    n_rows = no_dom = 0
    for r in all_rows[2:]:
        if r[hdr["Alex AI"]] != "OEM":
            continue
        n_rows += 1
        dom = normalize_domain(r[hdr["Domain_clean"]] or r[hdr["Domain"]])
        if not dom:
            no_dom += 1
            continue
        cat = str(r[hdr["Cateogry"]] or "").strip()
        rows.append({
            "source": "AV longlist v6 (Alex AI OEM)",
            "file": SRC_AV.name,
            "domain": dom,
            "name": "",
            "city": "",
            "category": cat,
            "note": f"AV longlist category: {cat or 'none'}",
        })
    stats["av_longlist_oem_rows"], stats["av_longlist_oem_no_domain"] = n_rows, no_dom
    return rows, stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    rows, stats = load_rows()
    con = sqlite3.connect(f"file:{settings.PIPELINE_DB_PATH}?mode=ro", uri=True)
    in_db = {normalize_domain(d) for (d,) in con.execute("SELECT domain FROM company_records")}
    con.close()

    kept: dict[str, dict] = {}
    dup_sheet = dup_db = 0
    per_source_kept: dict[str, int] = {}
    for r in rows:
        if r["domain"] in in_db:
            dup_db += 1
            continue
        if r["domain"] in kept:
            dup_sheet += 1
            k = kept[r["domain"]]
            if r["note"] not in k["note"]:
                k["note"] += " | " + r["note"]
            if not k["name"] and r["name"]:
                k["name"], k["city"] = r["name"], r["city"]
            continue
        kept[r["domain"]] = dict(r)
        per_source_kept[r["source"]] = per_source_kept.get(r["source"], 0) + 1

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BA11_src"
    ws.append(["M37 BA11 source sheet (built by scripts/m37_build_ba11_src.py); new domains only"])
    ws.append(["Nr", "Source", "Source file", "Domain", "Name", "City", "Category", "Klass", "Manual note"])
    for i, r in enumerate(kept.values(), 1):
        ws.append([i, r["source"], r["file"], r["domain"], r["name"], r["city"], r["category"], None, r["note"]])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    check = openpyxl.load_workbook(tmp, read_only=True)
    n_check = check["BA11_src"].max_row - 2
    check.close()
    assert n_check == len(kept), (n_check, len(kept))
    tmp.replace(args.out)

    print("Source rows read:")
    for k, v in stats.items():
        print(f"  {k:32s} {v}")
    print(f"Rows with domain:                 {len(rows)}")
    print(f"Skipped, already in company_records: {dup_db}")
    print(f"Skipped, duplicate within sheet:  {dup_sheet}")
    print(f"Written to BA11_src:              {len(kept)}")
    for s, n in per_source_kept.items():
        print(f"  kept from {s:34s} {n}")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
