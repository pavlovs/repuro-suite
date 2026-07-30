"""Hard gate: retired claims must never reappear in the investor view.

A claim that has been closed out (a DD finding resolved, a risk that no longer
applies, a dead deal's live-transaction wording) is recorded in
``boardroom/ai/retired-claims.json``. This script fails if any of them is still
rendered in the assembled investor HTML.

Why this exists: the Mantis pre-CDD accounting flags (reported EBIT -55%,
hospital-segment spike, preliminary 2025 P&L) survived multiple weekly updates
into an investor-facing document after the CDD had closed them out. A text rule
did not hold; this check does.

Usage:
    python boardroom/tools/check_retired_claims.py <assembled.html>

Exit 0 = clean, 1 = a retired claim is still present (or the file is unreadable).
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
LEDGER = REPO / "boardroom" / "ai" / "retired-claims.json"

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def rendered_text(raw: str) -> str:
    """Strip markup and entities so matching runs on what the reader sees."""
    text = _TAG.sub(" ", raw)
    text = html.unescape(text)
    # normalise the dash variants and whitespace the templates mix
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    return _WS.sub(" ", text)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_retired_claims.py <assembled.html>", file=sys.stderr)
        return 1

    target = pathlib.Path(argv[1])
    if not target.is_file():
        print(f"FAIL: cannot read {target}", file=sys.stderr)
        return 1

    if not LEDGER.is_file():
        print(f"FAIL: ledger missing at {LEDGER}", file=sys.stderr)
        return 1

    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    text = rendered_text(target.read_text(encoding="utf-8", errors="ignore")).lower()

    hits = []
    for entry in ledger.get("retired", []):
        phrase = entry["phrase"].lower()
        if phrase not in text:
            continue
        # optional second term, so short phrases ("120 K") only fire in context
        requires = entry.get("requires")
        if requires and requires.lower() not in text:
            continue
        hits.append(entry)

    if hits:
        print(f"FAIL: {len(hits)} retired claim(s) still rendered in {target.name}")
        for entry in hits:
            print(
                f"  [{entry['deal']}] {entry['phrase']!r} "
                f"(retired {entry['retired_on']}) - {entry['reason']}"
            )
        return 1

    print(
        f"PASS: no retired claims in {target.name} "
        f"({len(ledger.get('retired', []))} ledger entries checked)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
