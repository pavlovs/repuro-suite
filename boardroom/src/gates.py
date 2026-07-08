"""Content gates for the Investor Room curation flow.

HARD gates (never overridable, re-run at publish): scan_other_investors, check_pre_loi_names,
validate_body. SOFT gate (force-overridable at approve, a completeness warning): check_figures_stamped.
All functions return a list of violation strings — empty list = clean / passes.

The published body IS the investor allowlist (/api/published returns it whole), so validate_body
is a COMPLETE recursive key allowlist: any key not in the contract, at any nesting level, is rejected.
"""

import unicodedata

# ---------------------------------------------------------------------------
# Denylist: investor names that must NEVER appear in published investor content.
# Strada is the ONLY permitted investor. Case-insensitive word-ish match.
OTHER_INVESTOR_DENYLIST = {"asf", "aurica", "arbor"}


# ---------------------------------------------------------------------------
def _normalize(s: str) -> str:
    """NFKC-normalise and strip zero-width chars so common obfuscations don't evade the scan.
    (Collapses fullwidth/look-alike forms; removes ZWSP/ZWNJ/ZWJ/BOM.)"""
    s = unicodedata.normalize("NFKC", s)
    for zw in ("​", "‌", "‍", "﻿"):
        s = s.replace(zw, "")
    return s


def _walk_keys_and_strings(obj, path=""):
    """Yield (path, text) for every string VALUE and every dict KEY reachable in obj.
    Keys are scanned too — a leaked field name like 'aurica_note' must be caught."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kp = f"{path}.{k}" if path else k
            if isinstance(k, str):
                yield f"{kp} (key)", k
            yield from _walk_keys_and_strings(v, kp)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys_and_strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


def scan_other_investors(body) -> list[str]:
    """Scan every string value AND every dict key in body for denylist tokens.

    Returns findings like 'project_update.narrative: contains "aurica"'. Empty = clean.
    Word-ish match on NFKC-normalised, zero-width-stripped text so 'arbitrage' is not flagged
    but 'Aurіca' (Cyrillic і) / fullwidth forms are. HARD gate — never overridable.
    """
    import re

    findings = []
    # Boundary excludes '_' so underscore-joined identifiers like 'aurica_note' are caught,
    # while 'arbitrage'/'harbor' are not (token must be bounded by non-alphanumerics).
    pattern = re.compile(
        r"(?<![a-zA-Z0-9])("
        + "|".join(re.escape(t) for t in OTHER_INVESTOR_DENYLIST)
        + r")(?![a-zA-Z0-9])",
        re.IGNORECASE,
    )
    for path, text in _walk_keys_and_strings(body):
        if pattern.search(_normalize(text)):
            snippet = text[:120].replace("\n", " ")
            findings.append(f'{path}: matches investor denylist — "{snippet}"')
    return findings


def check_pre_loi_names(body) -> list[str]:
    """Assert no funnel item carries a 'name'/'company_name' key (pre-LOI = codename only).
    HARD gate. Returns offending paths. Empty = clean."""
    violations = []
    items = body.get("pipeline", {}).get("funnel", {}).get("items", [])
    if isinstance(items, list):
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            for forbidden in ("name", "company_name"):
                if forbidden in item:
                    violations.append(
                        f"pipeline.funnel.items[{i}].{forbidden}: real company name in pre-LOI funnel"
                    )
    return violations


def check_figures_stamped(body) -> list[str]:
    """SOFT gate (force-overridable): warn if pulled data is present but unstamped.
    Returns notes. Empty = clean."""
    if not isinstance(body, dict):
        return ["body: not an object"]
    stamps = body.get("stamps")
    if not isinstance(stamps, dict):
        return ["stamps: missing or not an object"]
    has_pulled = any(
        [
            bool(body.get("pipeline", {}).get("funnel", {}).get("items")),
            bool(body.get("pipeline", {}).get("batches", {}).get("rows")),
            bool(body.get("live_deals")),
            bool(body.get("kpis")),
        ]
    )
    if has_pulled and not stamps:
        return [
            "stamps: empty but body contains pulled data — every data block must be stamped"
        ]
    missing = []
    for key, stamp in stamps.items():
        if not isinstance(stamp, dict):
            missing.append(f"stamps.{key}: not an object")
            continue
        if not stamp.get("source"):
            missing.append(f"stamps.{key}.source: missing")
        if not stamp.get("as_of"):
            missing.append(f"stamps.{key}.as_of: missing")
    return missing


# ---------------------------------------------------------------------------
# Complete body schema — the investor allowlist. Any key not present here, at any
# nesting level, is rejected. Schema grammar:
#   ANY              → leaf; accepts any scalar (str/num/bool/None). No nested keys allowed.
#   {k: subschema}   → dict; keys MUST be a subset of these (extra key = violation). Recurse each.
#   [item_schema]    → list; every item validated against item_schema.
# There are NO free-key maps — every key at every level is an explicit allowlist (incl. stamp keys).
ANY = object()

_STAMP = {"source": ANY, "as_of": ANY}

WEEKLY_SCHEMA = {
    "pipeline": {
        "funnel": {
            "items": [
                {
                    "codename": ANY,
                    "stage": ANY,
                    "sector": ANY,
                    "region": ANY,
                    "size_band": ANY,
                    "strategic_fit": ANY,
                }
            ]
        },
        "batches": {
            "rows": [
                {
                    "batch": ANY,
                    "sent": ANY,
                    "replies": ANY,
                    "meetings": ANY,
                    "conv_pct": ANY,
                }
            ]
        },
    },
    "live_deals": [
        {
            "name": ANY,
            "codename": ANY,
            "stage": ANY,
            "rev_m": ANY,
            "ebitda_m": ANY,
            "ev_m": ANY,
            "multiple": ANY,
            "earnout": ANY,
            "dd_status": ANY,
            "close_target": ANY,
            "commentary": ANY,
        }
    ],
    "project_update": {
        "milestones_done": [{"name": ANY, "date": ANY, "comment": ANY}],
        "milestones_next": [{"name": ANY, "target_date": ANY}],
        "narrative": ANY,
        "fundraising": {
            "tax_structure": ANY,
            "sources_uses": [{"item": ANY, "amount_m": ANY, "note": ANY}],
            "capital_plan": ANY,
        },
    },
    # stamp KEYS are an exact allowlist of field-paths the assembler stamps — not free-form,
    # so no surprise key (e.g. 'stamps.secret_debug') can ride along to the investor.
    "stamps": {
        "pipeline.funnel": _STAMP,
        "pipeline.batches": _STAMP,
        "live_deals": _STAMP,
        "project_update.milestones": _STAMP,
    },
}

BOARD_SCHEMA = {
    "meeting": {"date": ANY, "location": ANY, "attendees": [ANY]},
    "agenda": [{"item": ANY, "owner": ANY, "minutes": ANY}],
    "decisions": [{"topic": ANY, "proposal": ANY, "resolution": ANY, "vote": ANY}],
    "pre_read": [{"title": ANY, "note": ANY}],
    "minutes": ANY,
    "kpis": [{"metric": ANY, "value": ANY, "prior": ANY, "as_of": ANY}],
    "stamps": {"kpis": _STAMP},
}


def _check(path, node, schema, out):
    """Recursively assert node contains no key outside schema. Appends violations to out."""
    if schema is ANY:
        return  # leaf — any scalar; we do not police leaf contents here (denylist does that)
    if isinstance(schema, dict):
        if not isinstance(node, dict):
            out.append(f"{path or '<root>'}: expected an object")
            return
        for k, v in node.items():
            kp = f"{path}.{k}" if path else str(k)
            if k not in schema:
                out.append(f"{kp}: key not permitted in published body")
                continue
            _check(kp, v, schema[k], out)
        return
    if isinstance(schema, list):
        if node is None:
            return
        if not isinstance(node, list):
            out.append(f"{path or '<root>'}: expected a list")
            return
        item_schema = schema[0]
        for i, item in enumerate(node):
            _check(f"{path}[{i}]", item, item_schema, out)
        return


def validate_body(kind: str, body) -> list[str]:
    """Complete recursive allowlist. Returns violations for ANY key outside the contract,
    at any nesting level. Empty = valid. HARD gate (re-run at publish, no force)."""
    if not isinstance(body, dict):
        return ["body: not an object"]
    if kind == "weekly_update":
        schema = WEEKLY_SCHEMA
    elif kind == "board_pack":
        schema = BOARD_SCHEMA
    elif kind == "investor_view":
        if not isinstance(body.get("html"), str):
            return ["html: must be a string"]
        if body.get("inline_edits") is not None and not isinstance(
            body.get("inline_edits"), dict
        ):
            return ["inline_edits: must be an object or null"]
        extra = set(body.keys()) - {"html", "inline_edits"}
        if extra:
            return [f"{k}: key not permitted in investor_view body" for k in sorted(extra)]
        return []
    else:
        return [f"unknown kind: {kind}"]
    out = []
    _check("", body, schema, out)
    return out
