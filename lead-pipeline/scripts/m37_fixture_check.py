"""M37 acceptance check (A1, A2): classify the 15 labelled OEM fixture names live.

DB-free: scrapes each fixture domain with the OEM profile into memory (optional --cache-file JSON
to reuse texts across runs), classifies with leave-one-out few-shot (the company never sees its
own example) through the Claude CLI, prints name / label / result / reason.

Exit code 1 on any D2 -> D1 (A1) or D1 -> D2 (A2) miss; C is allowed for both.

Usage:
  python scripts/m37_fixture_check.py [--model haiku] [--workers 4] [--cache-file PATH] [--refresh]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config.profile import load_profile, resolve_profile_path  # noqa: E402
from src.pipeline.classify import classify_oem_one  # noqa: E402
from src.pipeline.scrape import fetch_site_text  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "oem_fixture.json"
_HARD_MISS = {("D2", "D1"), ("D1", "D2")}


def main() -> int:
    ap = argparse.ArgumentParser(description="M37 OEM fixture check (live)")
    ap.add_argument("--model", default="haiku", help="Claude CLI model alias (default haiku)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--profile", default="oem")
    ap.add_argument("--cache-file", type=Path, default=None, help="JSON {domain: text} to reuse scrapes")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache file and scrape again")
    args = ap.parse_args()

    profile = load_profile(resolve_profile_path(args.profile))
    companies = json.loads(FIXTURE.read_text(encoding="utf-8"))["companies"]

    cache: dict[str, str] = {}
    if args.cache_file and args.cache_file.exists() and not args.refresh:
        cache = json.loads(args.cache_file.read_text(encoding="utf-8"))

    todo = [c["domain"] for c in companies if c["domain"] and c["domain"] not in cache]
    with ThreadPoolExecutor(args.workers) as pool:
        for dom, text in zip(todo, pool.map(lambda d: fetch_site_text(d, profile.scrape), todo)):
            cache[dom] = text
    if args.cache_file:
        args.cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    def _classify(c: dict) -> tuple[dict, dict, float]:
        t0 = time.time()
        text = cache.get(c["domain"] or "", "")
        if len(text) < 200:
            return c, {"klass_oem": "-", "klass_oem_reason": "no usable text"}, 0.0
        try:
            res = classify_oem_one(profile, c["name"], c["domain"], c.get("city"), text, args.model)
        except Exception as e:  # noqa: BLE001
            res = {"klass_oem": "ERR", "klass_oem_reason": repr(e)[:120]}
        return c, res, time.time() - t0

    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(_classify, companies))

    misses = 0
    print(f"{'Name':42s} {'Label':5s} {'Result':6s} {'Sec':>5s}  Reason")
    for c, res, secs in results:
        # "-" (no usable text) and "ERR" (CLI failure) are unproven, so they fail the check
        hard = (c["label"], res["klass_oem"]) in _HARD_MISS or res["klass_oem"] in ("-", "ERR")
        misses += hard
        flag = " <-- MISS" if hard else ""
        print(f"{c['name'][:42]:42s} {c['label']:5s} {res['klass_oem']:6s} {secs:5.1f}  {res['klass_oem_reason'][:150]}{flag}")
    d2_ok = sum(1 for c, r, _ in results if c["label"] == "D2" and r["klass_oem"] != "D1")
    d1_ok = sum(1 for c, r, _ in results if c["label"] == "D1" and r["klass_oem"] != "D2")
    n_d2 = sum(1 for c in companies if c["label"] == "D2")
    n_d1 = sum(1 for c in companies if c["label"] == "D1")
    print(f"\nA1 (no D2 -> D1): {d2_ok}/{n_d2}   A2 (no D1 -> D2): {d1_ok}/{n_d1}   hard misses: {misses}")
    print(f"model={args.model}  examples in profile={len(profile.classification.examples)} (leave-one-out)")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
