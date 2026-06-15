"""Ownership + email enrichment (M7/M8/M9).

M7: Ownership
  Step 0: ORBIS data already in DB (free)
  Step 1: OffeneRegister free SQL API — GF name by HRB (free)
  Step 2: OpenRegister.de REST API — Gesellschafter name + ownership % (paid, A/B only)
          Uses autocomplete waterfall for robust company matching:
            W1: full_name as-is (1 credit)
            W2: core name without legal form suffix (1 credit)
            W3: extract HRB from scraped website text → retry with HRB filter (1-2 credits)
            W4: query by HRB number directly (1 credit)
            W5: impressum owner extraction for non-GmbH / sole proprietors (0 credits)
          Name validation: autocomplete results rejected if result name doesn't contain query core.
          HRB cross-check: if website HRB known, verify against company_id before owners call.

  Stage outcomes:
    ownership_enriched      — ownership data found; natural person owner OR blocklist-confirmed
    ownership_review_needed — A/B company with legal_person majority owner not on blocklist,
                              OR OpenRegister returned no match. Requires manual review.

  UBO resolution for corporate parent owners (_resolve_ubo):
    When _parse_owners finds a legal_person majority owner not on blocklist:
      W1: full holding name as-is (1 credit)
      W2: hyphen/space variant — toggle hyphens↔spaces in compound core (1 credit)
      W3: core name only, legal form stripped (1 credit)
    After autocomplete succeeds → fetch owners → parse:
      Primary: _parse_owners majority check (natural person with highest %)
      Fallback: scan raw owners for natural persons (handles dispersed ownership,
                self-referencing majority, mixed structures)
    On failure: returns tried_queries list for UI feedback + manual correction.

  Dashboard API helpers (single-domain operations):
    re_enrich_single_domain()     — re-run waterfall for one domain (POST /api/re-enrich/{domain})
    resolve_parent_for_domain()   — UBO lookup on corporate parent (POST /api/resolve-parent/{domain})
      On failure: returns {tried_queries: [...]} so dashboard shows editable field for manual name retry.

M8: Ownership gate — confirmed subsidiary/PE → reclassify to S → stage='ownership_gated'

M9: Email — SMTP candidate testing from owner name only. No impressum scraping.
  Build 8 email combinations from gesellschafter_name first+last name + domain.
  SMTP-verify each (DNS MX + RCPT TO, port 25). Store first verified hit.
  Catch-all detection: multiple candidates pass → use first (f.l@domain), log flag.
  If no candidate passes → leave gf_email NULL, advance to email_enriched.
  Impressum scraping is NOT used — it only finds company emails (info@/gf@), not personal.

CRITICAL: OpenRegister.de is ONLY called for klass A or B companies. Never C/D/E.
          Never use realtime=true. Always check knowledge_base cache first.
          Credit cost: 11 per company base (1 autocomplete + 10 owners).
          +11 credits if corporate owner detected → UBO lookup on holding company.
"""

from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from src.config import settings
from src.config.profile import IndustryProfile
from src.pipeline import db as pipeline_db
from src.utils.knowledge_base import KnowledgeBase
from src.utils.web import fetch_impressum_text

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_POLITE_DELAY_S = 0.5
_OPENREGISTER_DELAY_S = 0.3  # polite delay between API calls

# Regex for detecting corporate entity names (word-boundary match to avoid
# false positives like "Seidel" matching "se", "Hagemann" matching "ag")
_CORPORATE_NAME_RE = re.compile(
    r"\b("
    r"gmbh|ag|kg|gbr|ug|ohg|kgaa|se"
    r"|ltd|limited|inc|corp|bv|nv|sa|sas|srl|plc"
    r"|holding|beteiligung|verwaltung|verwaltungs|vermögensverwaltung"
    r"|vermoegensverwaltung|capital|consulting|management"
    r"|stiftung|verein"
    r")\b"
    r"|e\.v\.",
    re.IGNORECASE,
)


def _is_natural_person_name(name: Optional[str]) -> bool:
    """Heuristic: return True if the name looks like a natural person, not a corporate entity.

    Uses word-boundary matching to avoid false positives (e.g. "Seidel" does NOT
    match "se", "Hagemann" does NOT match "ag").
    """
    if not name:
        return False
    return not _CORPORATE_NAME_RE.search(name)


# ---------------------------------------------------------------------------
# Corporate owners blocklist
# ---------------------------------------------------------------------------


def _load_corporate_blocklist() -> list[dict]:
    """Load confirmed non-fit corporate owners from blocklist JSON.

    Returns list of dicts with 'name' and 'type' keys.
    Silently returns empty list if file missing or malformed.
    """
    path = settings.CORPORATE_OWNERS_BLOCKLIST_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Filter out comment entries (those with '_comment' keys)
        return [e for e in data if isinstance(e, dict) and "name" in e]
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load corporate blocklist: %s", e)
        return []


def _is_on_blocklist(owner_name: str, blocklist: list[dict]) -> Optional[dict]:
    """Check if owner_name is a substring match against any blocklist entry.

    Returns the matching entry dict or None.
    """
    name_lower = owner_name.lower()
    for entry in blocklist:
        if entry["name"].lower() in name_lower:
            return entry
    return None


# ---------------------------------------------------------------------------
# M7 Step 1: OffeneRegister (free GF name by HRB)
# ---------------------------------------------------------------------------


def _enrich_ownership_offeneregister(
    hrb_number: Optional[str], domain: str
) -> Optional[dict]:
    """Free GF name lookup via OffeneRegister SQL API (db.offeneregister.de).

    Returns dict with 'gf_name' and 'source'='offeneregister', or None.
    Does NOT return ownership % — that requires OpenRegister Step 2.
    """
    if not hrb_number:
        return None
    try:
        hrb_clean = re.sub(r"[^0-9]", "", hrb_number)
        if not hrb_clean:
            return None
        url = (
            f"https://db.offeneregister.de/openregister-4xqp3gh.db/company_officers"
            f"?_where=(company_number%20like%20%27%25{hrb_clean}%25%27)&_shape=array"
        )
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data:
            return None
        gf_entries = [
            d
            for d in data
            if "geschaeftsfuehrer" in str(d.get("position", "")).lower()
            or "direktor" in str(d.get("position", "")).lower()
        ]
        if not gf_entries:
            gf_entries = data[:1]
        if gf_entries:
            name = gf_entries[0].get("name", "")
            return {"gf_name": name, "source": "offeneregister"}
    except Exception as e:
        logger.debug("OffeneRegister lookup failed for %s: %s", domain, e)
    return None


# ---------------------------------------------------------------------------
# M7 Step 2: OpenRegister.de (paid — A/B only)
# ---------------------------------------------------------------------------


_LEGAL_FORM_SUFFIXES = [
    "gmbh & co. kg",
    "gmbh & co. ohg",
    "gmbh & co.",
    "ug (haftungsbeschränkt)",
    "ug haftungsbeschränkt",
    "gmbh",
    "ug",
    "ag",
    "kg",
    "ohg",
    "e.k.",
    "e.kfm.",
    "gbr",
    "mbh",
    "e.v.",
]


def _strip_legal_form(name: str) -> str:
    """Strip German legal form suffix for fuzzy autocomplete search."""
    lower = name.lower().strip()
    for form in _LEGAL_FORM_SUFFIXES:
        if lower.endswith(form):
            result = name[: len(name) - len(form)].strip().rstrip(",").strip()
            if result:
                return result
    return name


_HRB_RE = re.compile(r"(?:HRB|HR\s*B)\s*(\d{2,6})", re.IGNORECASE)


def _extract_hrb_from_text(text: str) -> Optional[str]:
    """Extract HRB number from website/impressum text."""
    m = _HRB_RE.search(text)
    return m.group(1) if m else None


# Name capture: First + optional middle initial/name + Last (stops before address/legal text)
_PERSON_NAME_RE = (
    r"([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ]\.?[a-zäöüß]*)?\s+[A-ZÄÖÜ][a-zäöüß]+)"
)

_IMPRESSUM_PERSON_PATTERNS = [
    re.compile(r"Inhaber(?:in)?[:\s]+" + _PERSON_NAME_RE),
    re.compile(r"Gesch.ftsfüh?rer(?:in)?[:\s]+" + _PERSON_NAME_RE),
    re.compile(r"Geschaeftsfuehrer(?:in)?[:\s]+" + _PERSON_NAME_RE),
]


def _extract_impressum_owner(text: str) -> Optional[str]:
    """Extract owner or GF name from impressum text.

    Tries patterns in priority order: Inhaber (= owner) → Geschäftsführer (= managing
    director, often the owner in small GmbH). Returns first valid personal name found.
    """
    for pat in _IMPRESSUM_PERSON_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            if not _CORPORATE_NAME_RE.search(name):
                return name
    return None


def _openregister_headers() -> dict:
    return {"Authorization": f"Bearer {settings.OPENREGISTER_API_KEY}"}


def _name_matches_query(result_name: str, query: str) -> bool:
    """Check if an autocomplete result plausibly matches the query company.

    Extracts ALL significant words (>= 3 chars) from the query core (legal
    form stripped) and requires every one to appear in the result name.
    Single-word cores still work but must match; short tokens are skipped.
    """
    if not query or not result_name:
        return False
    q_core = _strip_legal_form(query).lower()
    r_lower = _strip_legal_form(result_name).lower()
    words = [w for w in re.split(r"[\s+&/,.-]+", q_core) if len(w) >= 3]
    if not words:
        return True
    return all(w in r_lower for w in words)


_autocomplete_address_cache: dict[str, str] = {}


def _openregister_autocomplete(
    full_name: str, hrb_number: Optional[str]
) -> Optional[str]:
    """Resolve company_id from company name via autocomplete (1 credit).

    Match logic (in priority order):
    1. HRB match: prefer result where register_number matches known HRB
    2. Name-verified active GmbH/UG/AG/KG: result name must contain query core
    3. Name-verified first result: last resort, still requires name match

    Rejects results where the company name doesn't match the query to prevent
    false matches (e.g., "Clavaro" returning "DiBuMa Invest GmbH").
    Returns company_id string or None.
    Side effect: caches registered_address in _autocomplete_address_cache[company_id].
    """
    url = f"{settings.OPENREGISTER_BASE_URL}/v1/autocomplete/company"
    try:
        resp = httpx.get(
            url,
            params={"query": full_name},
            headers=_openregister_headers(),
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(
                "OpenRegister autocomplete HTTP %d for %r", resp.status_code, full_name
            )
            return None
        results = resp.json().get("results", [])
        if not results:
            return None

        def _match_and_cache(r: dict) -> str:
            cid = r["company_id"]
            addr = r.get("registered_address") or r.get("address") or ""
            if addr and cid:
                _autocomplete_address_cache[cid] = addr
            return cid

        # Priority 1: match by HRB number (most reliable — bypasses name check)
        if hrb_number:
            hrb_digits = re.sub(r"[^0-9]", "", hrb_number)
            for r in results:
                reg_num = re.sub(r"[^0-9]", "", r.get("register_number", ""))
                if hrb_digits and hrb_digits == reg_num:
                    return _match_and_cache(r)

        # Priority 2: first active GmbH/UG/AG/KG whose name matches query
        preferred_forms = {"gmbh", "ug", "ag", "kg"}
        for r in results:
            if (
                r.get("active")
                and r.get("legal_form", "").lower() in preferred_forms
                and _name_matches_query(r.get("name", ""), full_name)
            ):
                return _match_and_cache(r)

        # Priority 3: first result with name match
        for r in results:
            if _name_matches_query(r.get("name", ""), full_name):
                return _match_and_cache(r)

        logger.info(
            "OpenRegister: %d results for %r but none matched by name",
            len(results),
            full_name,
        )
        return None

    except Exception as e:
        logger.warning("OpenRegister autocomplete error for %r: %s", full_name, e)
        return None


def _openregister_owners(company_id: str) -> Optional[list[dict]]:
    """Fetch owner list for a company_id (10 credits). Never uses realtime=true.

    Returns list of owner dicts or None on error.
    """
    url = f"{settings.OPENREGISTER_BASE_URL}/v1/company/{company_id}/owners"
    try:
        resp = httpx.get(
            url,
            headers=_openregister_headers(),
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(
                "OpenRegister owners HTTP %d for company_id=%s",
                resp.status_code,
                company_id,
            )
            return None
        return resp.json().get("owners", [])
    except Exception as e:
        logger.warning("OpenRegister owners error for company_id=%s: %s", company_id, e)
        return None


def _parse_owners(owners: list[dict], blocklist: list[dict]) -> dict:
    """Parse OpenRegister owners list into ownership fields.

    Returns dict with:
      gesellschafter_name, gesellschafter_share_pct, gesellschafter_age,
      is_subsidiary (True/False/None), is_pe_backed (True/False/None),
      needs_review (bool), review_reason (str|None),
      all_gesellschafter (str) — JSON array of ALL owners sorted by % desc.
        Each entry: {"name": str, "type": str, "pct": float|None}
        Previously only the majority owner was stored; minority owners were silently dropped.
    """
    # Build the full owner list before selecting the majority — captures all shareholders.
    all_gs = sorted(
        [
            {
                "name": o.get("name") or "",
                "type": o.get("type") or "unknown",
                "pct": o.get("percentage_share"),
            }
            for o in owners
        ],
        key=lambda e: e["pct"] or 0,
        reverse=True,
    )
    all_gs_json = json.dumps(all_gs, ensure_ascii=False)

    if not owners:
        return {
            "gesellschafter_name": None,
            "gesellschafter_share_pct": None,
            "gesellschafter_age": None,
            "is_subsidiary": None,
            "is_pe_backed": None,
            "needs_review": True,
            "review_reason": "OpenRegister returned empty owners list",
            "all_gesellschafter": all_gs_json,
        }

    # Find controlling owner: highest %, natural persons preferred in ties
    # (50/50 structures common in German SMEs — natural person side is what we care about)
    majority = max(
        owners,
        key=lambda o: (
            o.get("percentage_share") or 0,
            1 if o.get("type") == "natural_person" else 0,
        ),
    )
    pct = majority.get("percentage_share")
    owner_type = majority.get("type", "")

    # Name + birth year extraction — OpenRegister stores person data in nested sub-object
    np_obj = majority.get("natural_person") or {}
    lp_obj = majority.get("legal_person") or {}
    age: Optional[int] = None

    if owner_type == "natural_person":
        # Name: top-level "name" field preferred; fall back to first_name + last_name
        top_name = majority.get("name", "")
        first = np_obj.get("first_name", "")
        last = np_obj.get("last_name", "")
        owner_name = top_name or f"{first} {last}".strip()

        dob = np_obj.get("date_of_birth", "")
        if dob and len(dob) >= 4:
            try:
                age = int(dob[:4])
            except ValueError:
                pass
    else:
        top_name = majority.get("name", "")
        owner_name = top_name or lp_obj.get("name", "")

    # Natural person majority owner — confirmed private ownership
    if owner_type == "natural_person":
        return {
            "gesellschafter_name": owner_name,
            "gesellschafter_share_pct": pct,
            "gesellschafter_age": age,
            "is_subsidiary": False,
            "is_pe_backed": False,
            "needs_review": False,
            "review_reason": None,
            "all_gesellschafter": all_gs_json,
        }

    # Legal person majority owner — check blocklist
    if owner_type == "legal_person":
        match = _is_on_blocklist(owner_name, blocklist)
        if match:
            entry_type = match.get("type", "corporate_parent")
            is_sub = True
            is_pe = entry_type == "pe_fund"
            return {
                "gesellschafter_name": owner_name,
                "gesellschafter_share_pct": pct,
                "gesellschafter_age": None,
                "is_subsidiary": is_sub,
                "is_pe_backed": is_pe,
                "needs_review": False,
                "review_reason": None,
                "all_gesellschafter": all_gs_json,
            }
        # Legal person not on blocklist — cannot auto-decide (could be personal holdco)
        return {
            "gesellschafter_name": owner_name,
            "gesellschafter_share_pct": pct,
            "gesellschafter_age": None,
            "is_subsidiary": None,
            "is_pe_backed": None,
            "needs_review": True,
            "review_reason": (
                f"Legal entity majority owner ({owner_name}, {pct or 0:.0f}%) — "
                f"not on blocklist, manual review required"
            ),
            "all_gesellschafter": all_gs_json,
        }

    # Unknown type
    return {
        "gesellschafter_name": owner_name,
        "gesellschafter_share_pct": pct,
        "gesellschafter_age": age,
        "is_subsidiary": None,
        "is_pe_backed": None,
        "needs_review": True,
        "review_reason": f"Unknown owner type '{owner_type}' — manual review required",
        "all_gesellschafter": all_gs_json,
    }


def _resolve_ubo(holding_company_name: str, blocklist: list[dict]) -> Optional[dict]:
    """One-level UBO lookup: find the natural person behind a corporate majority owner.

    Called when _parse_owners() finds a legal_person owner not on the blocklist.
    Costs up to 13 credits (1-3 autocomplete attempts + 10 owners).

    Autocomplete waterfall (stops on first match):
      W1. full holding name as-is
      W2. hyphen/space variant (toggle hyphens↔spaces in compound core)
      W3. core name only (legal form stripped)

    Owner resolution (after autocomplete + owners call succeed):
      1. _parse_owners majority check (natural person with >50%)
      2. Fallback: scan raw owners for natural persons (handles dispersed ownership,
         self-referencing majority, mixed natural/legal structures)

    Returns result dict with owner data on success, or {"tried_queries": [...]} on failure.
    """
    if not settings.OPENREGISTER_API_KEY:
        return None

    logger.info("UBO lookup: resolving ownership of %r", holding_company_name)

    tried: list[str] = []
    company_id = None
    core = _strip_legal_form(holding_company_name)
    suffix = holding_company_name[len(core) :].strip()

    # W1: full name as-is
    tried.append(holding_company_name)
    company_id = _openregister_autocomplete(holding_company_name, None)

    # W2: toggle hyphens/spaces in core
    if not company_id:
        if " " in core:
            variant_core = core.replace(" ", "-")
        elif "-" in core:
            variant_core = core.replace("-", " ")
        else:
            variant_core = None
        if variant_core:
            variant = f"{variant_core} {suffix}".strip() if suffix else variant_core
            tried.append(variant)
            time.sleep(_OPENREGISTER_DELAY_S)
            company_id = _openregister_autocomplete(variant, None)

    # W3: core name without legal form
    if not company_id and core.lower() != holding_company_name.lower().strip():
        tried.append(core)
        time.sleep(_OPENREGISTER_DELAY_S)
        company_id = _openregister_autocomplete(core, None)

    if not company_id:
        logger.info(
            "UBO: no OpenRegister match for %r (tried: %s)",
            holding_company_name,
            tried,
        )
        return {"tried_queries": tried}

    time.sleep(_OPENREGISTER_DELAY_S)

    owners = _openregister_owners(company_id)
    if not owners:
        return {"tried_queries": tried}

    result = _parse_owners(owners, blocklist)

    if result.get("is_subsidiary") is False and result.get("gesellschafter_name"):
        result["review_reason"] = f"owns through {holding_company_name}"
        result["parent_owners"] = result.pop("all_gesellschafter", None)
        return result

    # Fallback: _parse_owners picked a legal entity (self-reference, holdco, etc.)
    # Scan raw owners for natural persons directly, skipping self-references.
    natural_persons = sorted(
        [
            o
            for o in owners
            if o.get("type") == "natural_person"
            and o.get("name")
            and o.get("name", "").lower() != holding_company_name.lower()
        ],
        key=lambda o: o.get("percentage_share") or 0,
        reverse=True,
    )
    if natural_persons:
        top = natural_persons[0]
        np_obj = top.get("natural_person") or {}
        age = None
        dob = np_obj.get("date_of_birth", "")
        if dob and len(dob) >= 4:
            try:
                age = int(dob[:4])
            except ValueError:
                pass
        all_gs = sorted(
            [
                {
                    "name": o.get("name", ""),
                    "type": o.get("type", "unknown"),
                    "pct": o.get("percentage_share"),
                }
                for o in owners
            ],
            key=lambda e: e["pct"] or 0,
            reverse=True,
        )
        return {
            "gesellschafter_name": top.get("name"),
            "gesellschafter_share_pct": top.get("percentage_share"),
            "gesellschafter_age": age,
            "is_subsidiary": False,
            "is_pe_backed": False,
            "review_reason": (
                f"owns through {holding_company_name} — "
                f"dispersed ownership, largest natural person"
            ),
            "parent_owners": json.dumps(all_gs, ensure_ascii=False),
        }

    return {"tried_queries": tried}


def _autocomplete_waterfall(
    full_name: str,
    hrb_number: Optional[str],
    domain: str,
    kb: Optional[KnowledgeBase] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Try progressively looser queries to resolve a company_id.

    Waterfall (HRB extracted early so every autocomplete call can use it):
      0. Extract HRB from scraped text / impressum (free, no API credit)
      1. full_name + HRB filter (if available)
      2. core name (legal form stripped) + HRB filter
      3. query by HRB number alone
      4. full_name without HRB (name-match only, lower confidence)
      5. core name without HRB (name-match only, lowest confidence)

    Returns (company_id, hrb_number) — hrb_number may be newly extracted.
    Each autocomplete step costs 1 credit (only if previous step failed).
    """
    core = _strip_legal_form(full_name)
    has_core_variant = core.lower() != full_name.lower().strip()

    # Step 0: extract HRB from website before any API call (free)
    if not hrb_number:
        text_sources = []
        if kb:
            scraped = kb.get_scraped_text(domain)
            if scraped:
                text_sources.append(scraped)
        impressum = fetch_impressum_text(domain)
        if impressum:
            text_sources.append(impressum)
        for src_text in text_sources:
            extracted = _extract_hrb_from_text(src_text)
            if extracted:
                hrb_number = f"HRB {extracted}"
                logger.info("Waterfall: extracted %s from %s", hrb_number, domain)
                break

    # Step 1: full name (with HRB filter when available)
    cid = _openregister_autocomplete(full_name, hrb_number)
    if cid:
        return cid, hrb_number

    # Step 2: core name without legal form
    if has_core_variant:
        time.sleep(_OPENREGISTER_DELAY_S)
        cid = _openregister_autocomplete(core, hrb_number)
        if cid:
            return cid, hrb_number

    # Step 3: query by HRB number directly
    if hrb_number:
        time.sleep(_OPENREGISTER_DELAY_S)
        cid = _openregister_autocomplete(hrb_number, hrb_number)
        if cid:
            return cid, hrb_number

    # Steps 4-5: retry WITHOUT HRB filter (name-match only) — only if HRB
    # was present but didn't help, because steps 1-2 already tried name-match
    # when hrb_number was None.
    if hrb_number:
        time.sleep(_OPENREGISTER_DELAY_S)
        cid = _openregister_autocomplete(full_name, None)
        if cid:
            return cid, hrb_number
        if has_core_variant:
            time.sleep(_OPENREGISTER_DELAY_S)
            cid = _openregister_autocomplete(core, None)
            if cid:
                return cid, hrb_number

    return None, hrb_number


def _enrich_ownership_openregister(
    full_name: str,
    hrb_number: Optional[str],
    domain: str,
    blocklist: list[dict],
    kb: Optional[KnowledgeBase] = None,
) -> Optional[dict]:
    """Full OpenRegister.de ownership lookup (11 credits base, +11 for UBO).

    Uses autocomplete waterfall: full name → core name → HRB extraction → HRB query.
    Returns parsed ownership dict or None if company not found.
    """
    if not settings.OPENREGISTER_API_KEY:
        logger.error("OPENREGISTER_API_KEY not set — cannot call OpenRegister.de")
        return None

    # Step 1: resolve company_id via waterfall (1-5 credits)
    company_id, hrb_number = _autocomplete_waterfall(full_name, hrb_number, domain, kb)

    # HRB cross-verification: if we have an HRB (from DB or extracted from website),
    # check that the company_id contains the same HRB digits. Prevents spending 10
    # credits on owners for the wrong company.
    if company_id and hrb_number:
        hrb_digits = re.sub(r"[^0-9]", "", hrb_number)
        cid_digits = re.sub(r"[^0-9]", "", company_id)
        if hrb_digits and hrb_digits not in cid_digits:
            logger.warning(
                "HRB cross-check FAILED for %s: website HRB=%s vs company_id=%s — rejecting match",
                domain,
                hrb_number,
                company_id,
            )
            company_id = None

    def _try_impressum_fallback() -> Optional[dict]:
        """Try extracting owner from impressum page (0 API credits)."""
        for text in [
            kb.get_scraped_text(domain) if kb else None,
            fetch_impressum_text(domain),
        ]:
            if not text:
                continue
            owner_name = _extract_impressum_owner(text)
            if owner_name:
                logger.info("Impressum fallback: owner for %s: %s", domain, owner_name)
                return {
                    "gesellschafter_name": owner_name,
                    "gesellschafter_share_pct": 100.0,
                    "gesellschafter_age": None,
                    "is_subsidiary": False,
                    "is_pe_backed": False,
                    "needs_review": False,
                    "gf_name": None,
                    "hrb_number": None,
                    "source": "impressum",
                    "all_gesellschafter": json.dumps(
                        [{"name": owner_name, "type": "person", "pct": 100.0}],
                        ensure_ascii=False,
                    ),
                }
        return None

    if not company_id:
        result = _try_impressum_fallback()
        if result:
            return result
        logger.info(
            "OpenRegister: no company_id after waterfall for %r (%s)",
            full_name,
            domain,
        )
        return None

    time.sleep(_OPENREGISTER_DELAY_S)

    # Step 2: get owners (10 credits)
    owners = _openregister_owners(company_id)
    if owners is None:
        logger.warning(
            "OpenRegister: owners call failed for %s (company_id=%s) — trying impressum",
            domain,
            company_id,
        )
        result = _try_impressum_fallback()
        if result:
            return result
        return None

    result = _parse_owners(owners, blocklist)
    result["company_id"] = company_id
    result["source"] = "openregister"

    # Step 3: UBO lookup — corporate owner not on blocklist → try one level up (+11 credits)
    if result.get("needs_review") and result.get("gesellschafter_name"):
        holding_name = result["gesellschafter_name"]
        logger.info(
            "OpenRegister: %s — corporate owner %r, attempting UBO lookup",
            domain,
            holding_name,
        )
        ubo = _resolve_ubo(holding_name, blocklist)
        if ubo and ubo.get("gesellschafter_name"):
            ubo["gesellschafter_share_pct"] = result.get("gesellschafter_share_pct")
            ubo["source"] = "openregister_ubo"
            ubo["all_gesellschafter"] = result.get("all_gesellschafter")
            logger.info(
                "UBO resolved: %s -> %s (via %s)",
                domain,
                ubo.get("gesellschafter_name"),
                holding_name,
            )
            return ubo
        logger.info(
            "UBO: could not resolve %r — flagging for manual review", holding_name
        )

    return result


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Ensure enrichment for briefaktion records (workflow hardening)
# ---------------------------------------------------------------------------


def ensure_enrich_for_briefaktion(
    profile: IndustryProfile,
    db_path: "Path | None" = None,
    kb_path: "Path | None" = None,
    briefaktion: "str | None" = None,
    dry_run: bool = False,
) -> int:
    """Ensure every BA-assigned Prio 1 record progresses through enrichment.

    Records imported via serienbriefe/dashboard may have klass set but
    pipeline_stage stuck at 'scraped' (skipped formal classify step).
    This function:
    1. Advances BA records from 'scraped' to 'classified' if klass is already set
    2. Runs enrichment on all newly classified BA records

    Returns count of records enriched.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    ba_filter = ""
    params: list[str] = []
    if briefaktion:
        ba_filter = " AND briefaktion = ?"
        params.append(briefaktion)

    # Step 1: advance scraped→classified for records that already have klass
    with pipeline_db.get_connection(db_path) as conn:
        rows = conn.execute(
            f"""SELECT domain, klass FROM company_records
                WHERE briefaktion IS NOT NULL
                  AND prio = 'Prio 1'
                  AND pipeline_stage = 'scraped'
                  AND klass IS NOT NULL AND klass != ''
                  {ba_filter}""",
            params,
        ).fetchall()

        if rows and not dry_run:
            domains = [r["domain"] for r in rows]
            placeholders = ",".join(["?"] * len(domains))
            conn.execute(
                f"UPDATE company_records SET pipeline_stage = 'classified' "
                f"WHERE domain IN ({placeholders})",
                domains,
            )
            conn.commit()
            logger.info(
                "ensure_enrich: advanced %d BA records from scraped→classified",
                len(domains),
            )
        elif rows:
            logger.info("ensure_enrich: DRY RUN — would advance %d records", len(rows))

    # Step 2: run normal enrichment (picks up newly classified records)
    count = enrich_ownership_batch(
        profile, dry_run=dry_run, db_path=db_path, kb_path=kb_path
    )

    if rows:
        logger.info(
            "ensure_enrich: %d records advanced + %d enriched", len(rows), count
        )
    return count


_NON_DE_TLDS = {
    ".at",
    ".ch",
    ".nl",
    ".fr",
    ".it",
    ".pl",
    ".cz",
    ".be",
    ".lu",
    ".dk",
    ".se",
    ".uk",
    ".co.uk",
}


def _detect_non_de_company(domain: str, plz_ort: Optional[str] = None) -> Optional[str]:
    """Return reason string if company is non-German, None if it looks DE."""
    d = domain.lower()
    for tld in _NON_DE_TLDS:
        if d.endswith(tld):
            country = tld.lstrip(".").upper()
            return f"Non-DE company (TLD: {tld}) — OpenRegister skipped"

    if plz_ort:
        plz = re.match(r"^(\d+)", plz_ort.strip())
        if plz:
            digits = len(plz.group(1))
            if digits == 4:
                return f"Non-DE company (4-digit PLZ: {plz.group(1)}) — likely AT/CH"
            if digits < 4 or digits > 5:
                return f"Non-DE company (PLZ {plz.group(1)} not 5-digit DE format)"

    return None


# M7: Ownership enrichment batch
# ---------------------------------------------------------------------------


def enrich_ownership_batch(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
) -> int:
    """Enrich A/B records with ownership data. Returns count processed.

    Stage outcomes per record:
      ownership_enriched      — data found, natural person confirmed OR blocklist match
      ownership_review_needed — legal person not on blocklist, or no OpenRegister match
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    records = pipeline_db.get_records_for_enrich(db_path)
    if limit > 0:
        records = records[:limit]

    total = len(records)
    logger.info("Enrich ownership: %d A/B records to process", total)

    if dry_run:
        logger.info("DRY RUN — would enrich %d records (0 API calls)", total)
        return 0

    if not records:
        logger.info("Enrich ownership: nothing to do")
        return 0

    kb = KnowledgeBase(kb_path)
    blocklist = _load_corporate_blocklist()
    logger.debug("Loaded %d corporate blocklist entries", len(blocklist))

    processed = 0
    api_calls = 0

    non_de_skipped = 0

    for i, rec in enumerate(records, 1):
        now = datetime.now(timezone.utc).isoformat()
        result: Optional[dict] = None
        stage = pipeline_db.STAGE_OWNERSHIP_ENRICHED
        ownership_reason: Optional[str] = None

        # Step -1: Non-DE company detection — skip OpenRegister (Germany-only API)
        non_de_reason = _detect_non_de_company(rec.domain, rec.plz_ort)
        if non_de_reason:
            stage = pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED
            ownership_reason = non_de_reason
            result = {
                "gf_name": rec.gf_name,
                "source": "non_de_skipped",
            }
            non_de_skipped += 1
            logger.info(
                "[%d/%d] NON-DE SKIP: %s — %s", i, total, rec.domain, non_de_reason
            )
            with pipeline_db.get_connection(db_path) as conn:
                pipeline_db.update_ownership_result(
                    conn,
                    rec.domain,
                    gesellschafter_name=rec.gesellschafter_name,
                    gesellschafter_share_pct=rec.gesellschafter_share_pct,
                    gesellschafter_age=rec.gesellschafter_age,
                    is_subsidiary=None,
                    is_pe_backed=None,
                    gf_name=rec.gf_name,
                    hrb_number=rec.hrb_number,
                    enriched_at=now,
                    stage=stage,
                    ownership_reason=ownership_reason,
                )
            processed += 1
            continue

        # Step 0: ORBIS data already in DB — determine if owner is natural person
        if rec.gesellschafter_share_pct is not None:
            orbis_name = rec.gesellschafter_name or ""
            if rec.is_subsidiary is not None:
                # Already resolved (prior OpenRegister call or manual review)
                logger.debug(
                    "[%d/%d] ORBIS+resolved for %s (%.0f%%)",
                    i,
                    total,
                    rec.domain,
                    rec.gesellschafter_share_pct,
                )
                result = {
                    "gesellschafter_name": rec.gesellschafter_name,
                    "gesellschafter_share_pct": rec.gesellschafter_share_pct,
                    "gesellschafter_age": rec.gesellschafter_age,
                    "is_subsidiary": rec.is_subsidiary,
                    "is_pe_backed": rec.is_pe_backed,
                    "gf_name": rec.gf_name,
                    "source": "orbis",
                }
            elif _is_natural_person_name(orbis_name):
                # ORBIS name is a natural person — confirmed private ownership
                logger.debug(
                    "[%d/%d] ORBIS natural person for %s: %s (%.0f%%)",
                    i,
                    total,
                    rec.domain,
                    orbis_name,
                    rec.gesellschafter_share_pct,
                )
                result = {
                    "gesellschafter_name": rec.gesellschafter_name,
                    "gesellschafter_share_pct": rec.gesellschafter_share_pct,
                    "gesellschafter_age": rec.gesellschafter_age,
                    "is_subsidiary": False,
                    "is_pe_backed": False,
                    "gf_name": rec.gf_name,
                    "source": "orbis",
                }
            else:
                # ORBIS name looks corporate — try OpenRegister UBO resolution
                logger.debug(
                    "[%d/%d] ORBIS corporate owner for %s: %s — attempting UBO lookup",
                    i,
                    total,
                    rec.domain,
                    orbis_name,
                )
                ubo = _resolve_ubo(orbis_name, blocklist)
                if (
                    ubo
                    and ubo.get("gesellschafter_name")
                    and ubo.get("is_subsidiary") is False
                ):
                    # UBO resolved to natural person behind the holding
                    logger.info(
                        "[%d/%d] UBO resolved for %s: %s behind %s",
                        i,
                        total,
                        rec.domain,
                        ubo.get("gesellschafter_name"),
                        orbis_name,
                    )
                    result = ubo
                    result["gesellschafter_share_pct"] = rec.gesellschafter_share_pct
                    result["gf_name"] = rec.gf_name
                    result["all_gesellschafter"] = json.dumps(
                        [
                            {
                                "name": orbis_name,
                                "type": "legal_person",
                                "pct": rec.gesellschafter_share_pct,
                            }
                        ],
                        ensure_ascii=False,
                    )
                    api_calls += 1
                else:
                    # UBO not resolved — keep ORBIS data, flag for review (NOT auto-S)
                    logger.info(
                        "[%d/%d] UBO unresolved for %s: %s — flagging for review",
                        i,
                        total,
                        rec.domain,
                        orbis_name,
                    )
                    stage = pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED
                    ownership_reason = f"Corporate owner ({orbis_name}, {rec.gesellschafter_share_pct:.0f}%) — UBO not resolved, manual review required"
                    tried = (
                        ubo.get("tried_queries", [orbis_name]) if ubo else [orbis_name]
                    )
                    result = {
                        "gesellschafter_name": rec.gesellschafter_name,
                        "gesellschafter_share_pct": rec.gesellschafter_share_pct,
                        "gesellschafter_age": rec.gesellschafter_age,
                        "is_subsidiary": None,
                        "is_pe_backed": None,
                        "gf_name": rec.gf_name,
                        "source": "orbis",
                        "all_gesellschafter": json.dumps(
                            [
                                {
                                    "name": orbis_name,
                                    "type": "legal_person",
                                    "pct": rec.gesellschafter_share_pct,
                                }
                            ],
                            ensure_ascii=False,
                        ),
                    }
                    if ubo:
                        api_calls += 1
        else:
            # Check KB cache
            cached = kb.get_ownership(rec.domain)
            if cached:
                result = cached
                logger.debug("[%d/%d] KB CACHE hit for %s", i, total, rec.domain)
            else:
                # Step 1: OffeneRegister free GF name lookup
                or_result = _enrich_ownership_offeneregister(rec.hrb_number, rec.domain)
                if or_result:
                    logger.debug(
                        "[%d/%d] OffeneRegister GF for %s: %s",
                        i,
                        total,
                        rec.domain,
                        or_result.get("gf_name"),
                    )
                    time.sleep(_POLITE_DELAY_S)

                # Step 2: OpenRegister.de — 11 credits base; +11 if UBO lookup triggered
                or2_result = _enrich_ownership_openregister(
                    rec.full_name, rec.hrb_number, rec.domain, blocklist, kb=kb
                )
                ubo_resolved = (
                    or2_result and or2_result.get("source") == "openregister_ubo"
                )
                api_calls += 2 if ubo_resolved else 1

                if or2_result is None:
                    stage = pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED
                    ownership_reason = f"OpenRegister: no match for '{rec.full_name}' — manual review required"
                    result = {
                        "gf_name": or_result.get("gf_name") if or_result else None,
                        "source": "not_found",
                    }
                    logger.info(
                        "[%d/%d] REVIEW NEEDED: %s — not found in OpenRegister",
                        i,
                        total,
                        rec.domain,
                    )
                else:
                    if or2_result.get("needs_review"):
                        stage = pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED
                        ownership_reason = or2_result.get("review_reason")
                        logger.info(
                            "[%d/%d] REVIEW NEEDED: %s — %s",
                            i,
                            total,
                            rec.domain,
                            ownership_reason,
                        )
                    else:
                        stage = pipeline_db.STAGE_OWNERSHIP_ENRICHED
                        # Preserve UBO note even for non-review cases
                        ownership_reason = or2_result.get("review_reason")
                        ubo_note = f" [{ownership_reason}]" if ownership_reason else ""
                        logger.info(
                            "[%d/%d] ENRICHED: %s — owner=%s pct=%.0f%% subsidiary=%s%s",
                            i,
                            total,
                            rec.domain,
                            or2_result.get("gesellschafter_name", "?"),
                            or2_result.get("gesellschafter_share_pct") or 0,
                            or2_result.get("is_subsidiary"),
                            ubo_note,
                        )
                    result = or2_result
                    if or_result and not result.get("gf_name"):
                        result["gf_name"] = or_result.get("gf_name")

                    # Cache to knowledge base (only if we got real ownership data)
                    if or2_result and or2_result.get("gesellschafter_name"):
                        kb.save_ownership(
                            rec.domain, result, result.get("source", "openregister")
                        )

                time.sleep(_POLITE_DELAY_S)

        or_addr = _autocomplete_address_cache.get(result.get("company_id", ""))
        if or_addr:
            logger.debug(
                "[%d/%d] OpenRegister address for %s: %s",
                i,
                total,
                rec.domain,
                or_addr,
            )

        with pipeline_db.get_connection(db_path) as conn:
            pipeline_db.update_ownership_result(
                conn,
                domain=rec.domain,
                gesellschafter_name=result.get("gesellschafter_name"),
                gesellschafter_share_pct=result.get("gesellschafter_share_pct"),
                gesellschafter_age=result.get("gesellschafter_age"),
                is_subsidiary=result.get("is_subsidiary"),
                is_pe_backed=result.get("is_pe_backed"),
                gf_name=result.get("gf_name"),
                hrb_number=result.get("hrb_number"),
                enriched_at=now,
                stage=stage,
                ownership_reason=ownership_reason,
                all_gesellschafter=result.get("all_gesellschafter"),
                parent_owners=result.get("parent_owners"),
                openregister_address=or_addr,
            )
        processed += 1

    if non_de_skipped:
        logger.info("Ownership enrichment: %d non-DE companies skipped", non_de_skipped)
    logger.info(
        "Ownership enrichment complete: %d processed, %d API calls (~%d credits used)",
        processed,
        api_calls,
        api_calls * settings.OPENREGISTER_CREDITS_PER_COMPANY,
    )
    return processed


# ---------------------------------------------------------------------------
# Dashboard API helpers: single-domain re-enrich & resolve parent
# ---------------------------------------------------------------------------


def re_enrich_single_domain(
    domain: str,
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
) -> dict:
    """Re-run ownership enrichment for one domain using the autocomplete waterfall.

    Bypasses KB ownership cache (the old lookup failed — cache holds nothing useful).
    Returns {"ok": bool, "stage": str, "detail": str}.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    if not settings.OPENREGISTER_API_KEY:
        return {"ok": False, "stage": "", "detail": "OPENREGISTER_API_KEY not set"}

    with pipeline_db.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT full_name, hrb_number FROM company_records WHERE domain = ?",
            (domain,),
        ).fetchone()
    if not row:
        return {"ok": False, "stage": "", "detail": f"Domain {domain} not found"}

    full_name = row["full_name"] or domain
    hrb_number = row["hrb_number"]
    kb = KnowledgeBase(kb_path)
    blocklist = _load_corporate_blocklist()
    now = datetime.now(timezone.utc).isoformat()

    result = _enrich_ownership_openregister(
        full_name, hrb_number, domain, blocklist, kb=kb
    )

    if result is None:
        return {
            "ok": False,
            "stage": pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED,
            "detail": "Waterfall exhausted — no match found",
        }

    if result.get("needs_review"):
        stage = pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED
        reason = result.get("review_reason", "needs review")
    else:
        stage = pipeline_db.STAGE_OWNERSHIP_ENRICHED
        reason = result.get("review_reason")

    with pipeline_db.get_connection(db_path) as conn:
        pipeline_db.update_ownership_result(
            conn,
            domain=domain,
            gesellschafter_name=result.get("gesellschafter_name"),
            gesellschafter_share_pct=result.get("gesellschafter_share_pct"),
            gesellschafter_age=result.get("gesellschafter_age"),
            is_subsidiary=result.get("is_subsidiary"),
            is_pe_backed=result.get("is_pe_backed"),
            gf_name=result.get("gf_name"),
            hrb_number=result.get("hrb_number"),
            enriched_at=now,
            stage=stage,
            ownership_reason=reason,
            all_gesellschafter=result.get("all_gesellschafter"),
            parent_owners=result.get("parent_owners"),
        )
        if result.get("gesellschafter_name"):
            kb.save_ownership(domain, result, result.get("source", "openregister"))

    owner = result.get("gesellschafter_name") or "unknown"
    return {
        "ok": True,
        "stage": stage,
        "detail": f"{owner} — {result.get('source', '?')}",
    }


def resolve_parent_for_domain(
    domain: str,
    parent_name: str,
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
) -> dict:
    """Run UBO lookup on a corporate parent entity, update the child record.

    Called from the dashboard "Resolve Parent" button.
    Costs 11 credits (autocomplete + owners on the parent entity).
    Returns {"ok": bool, "stage": str, "detail": str}.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    if not settings.OPENREGISTER_API_KEY:
        return {"ok": False, "stage": "", "detail": "OPENREGISTER_API_KEY not set"}

    blocklist = _load_corporate_blocklist()
    now = datetime.now(timezone.utc).isoformat()

    ubo = _resolve_ubo(parent_name, blocklist)

    if not ubo or not ubo.get("gesellschafter_name"):
        tried = ubo.get("tried_queries", [parent_name]) if ubo else [parent_name]
        return {
            "ok": False,
            "stage": pipeline_db.STAGE_OWNERSHIP_REVIEW_NEEDED,
            "detail": f"No match for: {', '.join(tried)}",
            "tried_queries": tried,
        }

    stage = pipeline_db.STAGE_OWNERSHIP_ENRICHED
    ubo["review_reason"] = f"owns through {parent_name}"

    with pipeline_db.get_connection(db_path) as conn:
        # Read current share_pct from the child record (parent's share in the target)
        row = conn.execute(
            "SELECT gesellschafter_share_pct FROM company_records WHERE domain = ?",
            (domain,),
        ).fetchone()
        share_pct = row["gesellschafter_share_pct"] if row else None

        pipeline_db.update_ownership_result(
            conn,
            domain=domain,
            gesellschafter_name=ubo.get("gesellschafter_name"),
            gesellschafter_share_pct=share_pct,
            gesellschafter_age=ubo.get("gesellschafter_age"),
            is_subsidiary=ubo.get("is_subsidiary"),
            is_pe_backed=ubo.get("is_pe_backed"),
            gf_name=ubo.get("gf_name"),
            hrb_number=None,
            enriched_at=now,
            stage=stage,
            ownership_reason=ubo.get("review_reason"),
            parent_owners=ubo.get("parent_owners"),
        )

    owner = ubo.get("gesellschafter_name", "unknown")
    return {"ok": True, "stage": stage, "detail": f"UBO: {owner} (via {parent_name})"}


# ---------------------------------------------------------------------------
# M8: Ownership hard gate
# ---------------------------------------------------------------------------


def apply_ownership_gate(
    profile: IndustryProfile,
    dry_run: bool = False,
    db_path: Optional[Path] = None,
) -> int:
    """Reclassify confirmed subsidiaries/PE-backed records to D.

    Processes pipeline_stage='ownership_enriched' only.
    Skips 'ownership_review_needed' — those require manual intervention first.
    Returns count reclassified to D.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH

    threshold = profile.ownership.hard_disqualify_subsidiary_threshold_pct

    with pipeline_db.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT domain, gesellschafter_share_pct, is_subsidiary, is_pe_backed "
            "FROM company_records WHERE pipeline_stage = 'ownership_enriched'"
        ).fetchall()

    if not rows:
        logger.info("Ownership gate: nothing to process")
        return 0

    reclassified = 0
    passed = 0

    with pipeline_db.get_connection(db_path) as conn:
        for row in rows:
            domain = row["domain"]
            share_pct = row["gesellschafter_share_pct"]
            is_sub = row["is_subsidiary"]
            is_pe = row["is_pe_backed"]

            reason: Optional[str] = None
            if is_sub:
                reason = "subsidiary — confirmed corporate parent"
            elif is_pe:
                reason = "PE-backed — confirmed fund ownership"
            elif is_sub is None and share_pct is not None and share_pct >= threshold:
                # is_subsidiary unknown + high share % → conservative S classification
                reason = f"unknown owner holds {share_pct:.0f}% — manual verification required"

            if reason:
                if not dry_run:
                    pipeline_db.apply_ownership_gate_db(conn, domain, reason)
                reclassified += 1
                logger.debug("GATE FAIL: %s — %s", domain, reason)
            else:
                if not dry_run:
                    pipeline_db.advance_ownership_gate(conn, domain)
                passed += 1

    logger.info("Ownership gate: %d reclassified to S, %d passed", reclassified, passed)
    return reclassified


# ---------------------------------------------------------------------------
# M9: Email enrichment — SMTP candidate testing from owner name only
# ---------------------------------------------------------------------------

# Known masculine first names / endings to help anrede heuristic
_MALE_NAMES = {
    "peter",
    "hans",
    "michael",
    "thomas",
    "stefan",
    "andreas",
    "christian",
    "martin",
    "frank",
    "markus",
    "jens",
    "uwe",
    "ralf",
    "klaus",
    "bernd",
    "dirk",
    "jochen",
    "holger",
    "rainer",
    "volker",
    "oliver",
    "alexander",
    "sebastian",
    "tobias",
    "daniel",
    "philipp",
    "simon",
    "felix",
    "florian",
    "jan",
    "tim",
    "paul",
    "max",
    "moritz",
    "lukas",
    "leon",
    "nico",
    "marc",
    "björn",
    "sven",
    "carsten",
    "torsten",
    "gerhard",
    "walter",
    "werner",
    "helmut",
    "günter",
    "dieter",
    "manfred",
    "horst",
    # Added — common German male names missing from original list
    "achim",
    "adrian",
    "arno",
    "axel",
    "benjamin",
    "bernhard",
    "bruno",
    "christoph",
    "detlef",
    "dietmar",
    "dietrich",
    "eberhard",
    "eckhard",
    "edgar",
    "edmund",
    "egon",
    "erich",
    "ernst",
    "erwin",
    "eugen",
    "friedhelm",
    "friedrich",
    "georg",
    "gerd",
    "gregor",
    "günther",
    "guenter",
    "harald",
    "hartmut",
    "heinrich",
    "hendrik",
    "henning",
    "herbert",
    "hermann",
    "hubert",
    "ingo",
    "joachim",
    "joerg",
    "jörg",
    "josef",
    "jürgen",
    "juergen",
    "karl",
    "konrad",
    "kurt",
    "lars",
    "lothar",
    "ludger",
    "ludwig",
    "manfred",
    "marcel",
    "marcus",
    "mario",
    "matthias",
    "maximilian",
    "norbert",
    "olaf",
    "otto",
    "patrick",
    "rainer",
    "reinhard",
    "reinhold",
    "richard",
    "robert",
    "roland",
    "ronald",
    "rolf",
    "rüdiger",
    "ruediger",
    "rudolf",
    "siegfried",
    "steffen",
    "stephan",
    "timo",
    "tino",
    "ulrich",
    "volker",
    "wilfried",
    "wilhelm",
    "winfried",
    "wolfgang",
    # Names found missing during BA9 enrichment
    "dennis",
    "fabian",
    "ibrahim",
    "lutz",
    "marco",
    "mathias",
    "niklas",
    "pascal",
    # International / less common male names
    "artur",
    "arthur",
    "emil",
    "johann",
    "yannik",
    "jannik",
    "tuncay",
    "ferhat",
    "karlheinz",
    "hans-peter",
    "karl-peter",
    "karl-heinz",
    "hans-jürgen",
    "hans-georg",
    "hans-dieter",
    # Male names ending in vowels (would otherwise trigger -e/-a/-i heuristic)
    "pierre",
    "boris",
    "johannes",
    "stephen",
    "andre",
    "arne",
    "bodo",
    "enno",
    "fiete",
    "giulio",
    "hajo",
    "heiko",
    "helge",
    "henrike",
    "hugo",
    "ivo",
    "janne",
    "jesse",
    "joe",
    "jonte",
    "kai",
    "malte",
    "manne",
    "mike",
    "niko",
    "ole",
    "owe",
    "rene",
    "robby",
    "rocco",
    "sascha",
    "serge",
    "sönke",
    "thore",
    "torge",
    "udo",
    "ugo",
    "ulf",
}
_FEMALE_NAMES = {
    "jana",
    "maria",
    "anna",
    "julia",
    "sarah",
    "lisa",
    "laura",
    "katharina",
    "sabine",
    "sandra",
    "monika",
    "petra",
    "claudia",
    "andrea",
    "christine",
    "susanne",
    "nicole",
    "karin",
    "angelika",
    "birgit",
    "martina",
    "silke",
    "anja",
    "melanie",
    "stephanie",
    "jessica",
    "jennifer",
    "michelle",
    "hannah",
    "lena",
    "lea",
    "emma",
    "sophie",
    "marie",
    "charlotte",
    "franziska",
    "nadine",
    "tanja",
    "eva",
    "britta",
    "heike",
    # International / less common female names
    "annegret",
    "yasemin",
    "snezana",
    "beatrice",
    "elvira",
    "jacqueline",
    # Added — common German female names missing from original list
    "annette",
    "bärbel",
    "barbara",
    "beate",
    "bettina",
    "brigitte",
    "carina",
    "cornelia",
    "dagmar",
    "doris",
    "dorothea",
    "edith",
    "elke",
    "elisabeth",
    "gabriele",
    "gisela",
    "gudrun",
    "hannelore",
    "helga",
    "hildegard",
    "ilse",
    "ines",
    "ingrid",
    "irene",
    "iris",
    "isabell",
    "jutta",
    "karen",
    "katja",
    "katrin",
    "kirsten",
    "kristin",
    "margit",
    "margret",
    "marianne",
    "marion",
    "marlene",
    "meike",
    "michaela",
    "natascha",
    "petra",
    "regina",
    "renate",
    "rita",
    "roswitha",
    "ruth",
    "sigrid",
    "simone",
    "sonja",
    "stefanie",
    "ulrike",
    "ursula",
    "ute",
    "vera",
    "waltraud",
}


def _derive_anrede(first_name: str) -> Optional[str]:
    """Simple German first-name gender heuristic. Returns 'Herr', 'Frau', or None.

    Priority: known name lists → vowel ending heuristic.
    ~85% accurate for common German names. Returns None when uncertain.
    ORBIS anrede is authoritative — never overwrite existing values.
    """
    if not first_name:
        return None
    name = first_name.lower().strip()
    if name in ("dr.", "prof.", "dr", "prof"):
        return None
    # Strip accents for lookup: René→rene, Günter→guenter handled by list
    import unicodedata

    normalized = unicodedata.normalize("NFD", name)
    ascii_name = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    for candidate in (name, ascii_name):
        if candidate in _MALE_NAMES:
            return "Herr"
        if candidate in _FEMALE_NAMES:
            return "Frau"
    # Compound names: Karl-Peter → check Karl
    if "-" in name:
        first_part = name.split("-")[0]
        if first_part in _MALE_NAMES:
            return "Herr"
        if first_part in _FEMALE_NAMES:
            return "Frau"
    # Heuristic: names ending in 'a', 'e', 'i' tend to be feminine in German
    if name.endswith(("a", "e", "i")):
        return "Frau"
    return None


def _normalise_name_for_email(name: str) -> str:
    """Lowercase + umlaut normalisation for email local-part generation.

    ä→ae, ö→oe, ü→ue, ß→ss. Remaining non-ascii stripped.
    """
    s = name.lower()
    for src, dst in [
        ("ä", "ae"),
        ("ö", "oe"),
        ("ü", "ue"),
        ("ß", "ss"),
        ("Ä", "ae"),
        ("Ö", "oe"),
        ("Ü", "ue"),
    ]:
        s = s.replace(src, dst)
    return re.sub(r"[^a-z0-9\-]", "", s)


def _scrape_email_pattern(domain: str) -> Optional[str]:
    """Scrape company website for personal emails to discover the email pattern.

    Checks /impressum, /team, /kontakt, /ueber-uns for non-generic emails.
    If found, extracts the local-part pattern (e.g. "firstname.lastname").
    Returns the pattern string or None.
    """
    generic_prefixes = frozenset(
        {
            "info",
            "kontakt",
            "office",
            "mail",
            "post",
            "service",
            "support",
            "verwaltung",
            "buchhaltung",
            "empfang",
            "zentrale",
            "bewerbung",
            "jobs",
            "career",
            "presse",
            "marketing",
            "datenschutz",
            "webmaster",
            "admin",
            "sales",
            "vertrieb",
            "bestellung",
            "anfrage",
            "technik",
        }
    )
    personal_emails: list[str] = []

    for path in (
        "/impressum",
        "/team",
        "/kontakt",
        "/ueber-uns",
        "/about",
        "/about-us",
    ):
        url = f"https://{domain}{path}"
        try:
            resp = httpx.get(url, timeout=8, follow_redirects=True, verify=False)
            if resp.status_code != 200:
                continue
            found = _EMAIL_RE.findall(resp.text)
            for email in found:
                local = email.split("@")[0].lower()
                email_domain = email.split("@")[1].lower()
                # Only consider emails from the company's own domain
                if domain.lower() not in email_domain:
                    continue
                if local not in generic_prefixes:
                    personal_emails.append(local)
        except Exception:
            continue

    if not personal_emails:
        return None

    # Analyze the pattern: how is the local part structured?
    local = personal_emails[0]
    if "." in local:
        parts = local.split(".")
        if len(parts) == 2:
            if len(parts[0]) == 1:
                return "f0.l"  # j.rennecke
            return "f.l"  # jana.rennecke
    return None  # can't determine pattern reliably


def _build_owner_email_candidates(gesellschafter_name: str, domain: str) -> list[str]:
    """Build 8 email candidates from owner name + domain.

    Name splitting: last word = last name, first word = first name.
    E.g. "Uwe Dirk Joneck" -> first="uwe", last="joneck"

    Patterns (f=first, l=last, 0=initial):
      f.l     jana.rennecke  (most common German SME pattern)
      f0.l    j.rennecke
      l       rennecke
      f       jana
      fl      janarennecke
      f0l     jrennecke
      f.l0    jana.r
      f0.l0   j.r

    If a pattern was discovered via website scraping, that pattern is tested first.
    """
    parts = gesellschafter_name.strip().split()
    if len(parts) < 2:
        return []

    f = _normalise_name_for_email(parts[0])
    l = _normalise_name_for_email(parts[-1])
    if not f or not l:
        return []

    f0 = f[0]
    l0 = l[0]

    # Check if we can discover the pattern from the website
    discovered = _scrape_email_pattern(domain)
    if discovered:
        logger.debug("Email pattern discovered for %s: %s", domain, discovered)

    all_patterns = [
        ("f.l", f"{f}.{l}"),
        ("f0.l", f"{f0}.{l}"),
        ("l", l),
        ("f", f),
        ("fl", f"{f}{l}"),
        ("f0l", f"{f0}{l}"),
        ("f.l0", f"{f}.{l0}"),
        ("f0.l0", f"{f0}.{l0}"),
    ]

    # If we discovered the pattern, put it first
    if discovered:
        all_patterns.sort(key=lambda p: 0 if p[0] == discovered else 1)

    return [f"{pat}@{domain}" for _, pat in all_patterns]


def _smtp_verify(email: str) -> bool:
    """Verify email deliverability.

    Priority: Abstract API (works from any IP) > Cloud Function > direct SMTP.
    Abstract API recommended — residential IPs are Spamhaus PBL-listed,
    and GCP Cloud Functions block outbound port 25.
    """
    if settings.ABSTRACT_API_KEY:
        return _verify_via_abstract_api(email)
    verify_url = settings.EMAIL_VERIFY_URL
    if verify_url:
        return _verify_via_cloud_function(email, verify_url)
    return _verify_via_local_smtp(email)


def _verify_via_abstract_api(email: str) -> bool:
    """Verify email via Abstract API (SMTP check from their servers)."""
    try:
        resp = httpx.get(
            "https://emailvalidation.abstractapi.com/v1/",
            params={"api_key": settings.ABSTRACT_API_KEY, "email": email},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            deliverable = data.get("deliverability") == "DELIVERABLE"
            smtp_info = data.get("is_smtp_valid", {})
            smtp_valid = (
                smtp_info.get("value", False)
                if isinstance(smtp_info, dict)
                else bool(smtp_info)
            )
            return deliverable and smtp_valid
        if resp.status_code == 429:
            logger.warning(
                "Abstract API rate limited for %s — treating as unverified", email
            )
        else:
            logger.warning("Abstract API error for %s: %d", email, resp.status_code)
        return False
    except Exception as e:
        logger.warning("Abstract API call failed for %s: %s", email, e)
        return False


def _verify_via_cloud_function(email: str, verify_url: str) -> bool:
    """Call the email verification Cloud Function."""
    try:
        resp = httpx.get(verify_url, params={"email": email}, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("valid", False)
        return False
    except Exception as e:
        logger.warning("Cloud email verify failed for %s: %s", email, e)
        return False


def _verify_via_local_smtp(email: str) -> bool:
    """Direct SMTP RCPT TO probe (only works from non-PBL IPs)."""
    try:
        domain = email.split("@")[1]
        import dns.resolver  # type: ignore

        mx_records = dns.resolver.resolve(domain, "MX")
        mx_host = str(
            sorted(mx_records, key=lambda r: r.preference)[0].exchange
        ).rstrip(".")
        with smtplib.SMTP(mx_host, 25, timeout=5) as smtp:
            smtp.helo("repuro.de")
            smtp.mail("verify@repuro.de")
            code, _ = smtp.rcpt(email)
            return code == 250
    except Exception:
        return False


def _smtp_verify_candidates(candidates: list[str]) -> tuple[Optional[str], bool]:
    """Verify a list of candidates via SMTP. Returns (email, is_catch_all).

    Exactly 1 passes → real email, is_catch_all=False.
    Multiple pass → catch-all domain; return first (most common pattern), is_catch_all=True.
    None pass → (None, False).
    """
    passing = [c for c in candidates if _smtp_verify(c)]
    if not passing:
        return None, False
    if len(passing) == 1:
        return passing[0], False
    logger.info(
        "Catch-all detected (%d/%d passed) — using first: %s",
        len(passing),
        len(candidates),
        candidates[0],
    )
    return candidates[0], True


def enrich_email_batch(
    profile: IndustryProfile,
    dry_run: bool = False,
    limit: int = 0,
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
) -> int:
    """Enrich A/B records with owner personal email via SMTP candidate testing.

    Builds 8 email combinations from owner name (gesellschafter_name) + domain and
    SMTP-verifies each. No impressum scraping — impressum only gives company emails
    (info@, gf@) which are not personal addresses and not what we need.

    If SMTP finds nothing: advances stage to email_enriched with gf_email=NULL.
    The email will be filled manually via M11 dashboard.

    Returns count of records where a verified email was found.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    with pipeline_db.get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM company_records
               WHERE pipeline_stage IN ('ownership_gated', 'ownership_enriched', 'classified')
               AND prio = 'Prio 1'
               AND (gf_email IS NULL OR gf_email = '')""",
        ).fetchall()
    records = [pipeline_db._row_to_company_record(row) for row in rows]

    if limit > 0:
        records = records[:limit]

    total = len(records)
    logger.info("Enrich email: %d A/B records to process", total)

    if dry_run:
        logger.info("DRY RUN — would process %d records (no SMTP calls)", total)
        return 0

    if not records:
        logger.info("Enrich email: nothing to do")
        return 0

    found = 0

    for i, rec in enumerate(records, 1):
        domain = rec.domain
        best_email: Optional[str] = None

        owner_name = rec.gesellschafter_name if rec.gesellschafter_name else None

        if owner_name and rec.is_subsidiary is False:
            candidates = _build_owner_email_candidates(owner_name, domain)
            if candidates:
                logger.debug(
                    "[%d/%d] %s — testing %d SMTP candidates for %r",
                    i,
                    total,
                    domain,
                    len(candidates),
                    owner_name,
                )
                best_email, is_catch_all = _smtp_verify_candidates(candidates)
                if best_email:
                    found += 1
                    source = "smtp_catchall" if is_catch_all else "smtp_verified"
                    logger.info(
                        "[%d/%d] FOUND (%s): %s -> %s",
                        i,
                        total,
                        source,
                        domain,
                        best_email,
                    )
                else:
                    logger.info(
                        "[%d/%d] NO EMAIL (SMTP): %s — port 25 blocked or no match",
                        i,
                        total,
                        domain,
                    )
            else:
                logger.info(
                    "[%d/%d] NO EMAIL: %s — cannot build candidates from name %r",
                    i,
                    total,
                    domain,
                    owner_name,
                )
        else:
            logger.info(
                "[%d/%d] SKIP: %s — no owner name or not natural person",
                i,
                total,
                domain,
            )

        # Derive owner_name: prefer existing DB value, fall back to gesellschafter_name
        owner_name_db = rec.owner_name if rec.owner_name else None
        if not owner_name_db and owner_name and rec.is_subsidiary is False:
            owner_name_db = owner_name

        # Derive anrede from owner first name (only if not already set in DB)
        anrede = rec.anrede if rec.anrede else None
        if not anrede and owner_name:
            first = owner_name.strip().split()[0]
            anrede = _derive_anrede(first)

        # Build salutation
        salutation = rec.salutation if rec.salutation else None
        if not salutation and anrede and owner_name_db:
            last = owner_name_db.strip().split()[-1]
            suffix = "r" if anrede == "Herr" else ""
            salutation = f"Sehr geehrte{suffix} {anrede} {last}"

        with pipeline_db.get_connection(db_path) as conn:
            pipeline_db.update_email_result(
                conn,
                domain=domain,
                gf_email=best_email,
                owner_name=owner_name_db,
                anrede=anrede,
                salutation=salutation,
            )

    logger.info("Email enrichment complete: %d/%d verified emails found", found, total)
    return found


# ---------------------------------------------------------------------------
# Combined enrich command (M7 + M8 + M9)
# ---------------------------------------------------------------------------


def enrich_cmd(
    profile: IndustryProfile,
    dry_run: bool = False,
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
) -> None:
    """Run full enrichment pipeline: ownership (M7) -> gate (M8) -> email (M9)."""
    enrich_ownership_batch(profile, dry_run=dry_run, db_path=db_path, kb_path=kb_path)
    apply_ownership_gate(profile, dry_run=dry_run, db_path=db_path)
    enrich_email_batch(profile, dry_run=dry_run, db_path=db_path, kb_path=kb_path)


# ---------------------------------------------------------------------------
# GF enrichment (M21) — impressum scrape + extraction
# ---------------------------------------------------------------------------

# Name: 2–4 words (First [Initial./Middle] Last [Suffix]).
# Allows single-letter initials with period (e.g., "T.") and hyphenated names.
_NAME_WORD = r"[A-ZÄÖÜ](?:[a-zäöüß\-]+|\.)"
_NAME_PART = r"(" + _NAME_WORD + r"(?:\s+" + _NAME_WORD + r"){1,3})"
_GF_CONJUNCTION = (
    r"Gesch[äa]ftsf[üu]hr(?:er(?:in)?|ung)\s*[:\s]\s*"
    r"(?:Dr\.?\s+)?" + _NAME_WORD + r"+\s+(?:&|und)\s+"
    r"(?:Dr\.?\s+)?" + _NAME_PART
)
_GF_PATTERNS = [
    re.compile(_GF_CONJUNCTION),
    re.compile(
        r"Gesch[äa]ftsf[üu]hr(?:er(?:in(?:nen)?)?|ung|er/(?:in(?:nen)?))\s*[:\s]\s*(?:Dr\.?\s+)?"
        + _NAME_PART
    ),
    re.compile(
        r"[Vv]ertreten durch[:\s]+(?:Gesch[äa]ftsf[üu]hr(?:er|erin)\s+)?"
        r"(?:Dr\.?\s+)?" + _NAME_PART
    ),
    re.compile(r"Inhaber\s*[:\s]\s*(?:Dr\.?\s+)?" + _NAME_PART),
    re.compile(r"Gesch[äa]ftsleitung\s*[:\s]\s*(?:Dr\.?\s+)?" + _NAME_PART),
    re.compile(
        r"[Vv]erantwortlich(?:\s+(?:i\.\s*S\.\s*d\.\s*§?\s*\d+\s*\w*))?\s*[:\s]\s*(?:Dr\.?\s+)?"
        + _NAME_PART
    ),
]

# Words that follow GF names in impressum but are not part of the name.
_NON_NAME_SUFFIXES = re.compile(
    r"\s+(Umsatzsteuer|Steuer|HRB|Amtsgericht|Registergericht|Tel|Fax|E-Mail|"
    r"Ust|USt|GmbH|AG|KG|Gesellschaft|Straße|Str\.|Kontakt|Aufsichtsbeh|"
    r"Handelsregister|Kammer|Haftung|Vertretung|Anschrift|Adresse|"
    r"Impressum|Datenschutz|Telefon|Mobile|Mobil).*$",
    re.IGNORECASE,
)

_GENERIC_EMAIL_PREFIXES = frozenset(
    {
        "info",
        "kontakt",
        "mail",
        "anfrage",
        "post",
        "office",
        "service",
        "support",
        "hello",
        "hallo",
        "vertrieb",
        "sales",
        "verwaltung",
        "buchhaltung",
        "bestellung",
        "anfragen",
    }
)


_GF_JUNK_WORDS = frozenset(
    {
        "eingetragen",
        "handelsgericht",
        "handelsregister",
        "amtsgericht",
        "registergericht",
        "verantwortlich",
        "technische",
        "verwaltungs",
        "geschäftsführer",
        "geschaeftsfuehrer",
        "vertretungsberechtigter",
        "umsatzsteuer",
        "steuernummer",
        "haftung",
        "kontakt",
        "impressum",
        "datenschutz",
        "telefon",
        "mobil",
        "fax",
    }
)

_GF_STREET_RE = re.compile(
    r"\b\w{4,}(straße|strasse|weg|gasse|platz|allee|damm|ufer|chaussee|pfad|steig)\b"
    r"|\b(str\.|ring)\s*\d",
    re.IGNORECASE,
)

_GF_NAME_PARTICLES = frozenset(
    {"von", "zu", "van", "de", "der", "den", "ten", "ter", "vom", "zum", "zur"}
)

_GF_PREFIX_RE = re.compile(
    r"^(Herr|Frau|Mr\.?|Mrs\.?|Ms\.?|Dr\.?\s*med\.?|Dr\.?|Prof\.?|Dipl\.\s*\S+)\s+",
    re.IGNORECASE,
)
_GF_SUFFIX_RE = re.compile(
    r"\s+(Dr\.?\s*med\.?|Dr\.?|Prof\.?|Dipl\.\s*\S+)$", re.IGNORECASE
)


def _sanitize_gf_name(raw: str) -> "str | None":
    """Clean extracted GF name: strip prefixes/suffixes, junk words, street names.
    Returns cleaned name or None if invalid."""
    if not raw or not raw.strip():
        return None
    name = raw.strip()
    prev = None
    while prev != name:
        prev = name
        name = _GF_PREFIX_RE.sub("", name).strip()
    name = _GF_SUFFIX_RE.sub("", name).strip()
    parts = re.split(r"[,;/&]|\bund\b", name)
    name = parts[0].strip()
    words_for_street = name.split()
    if len(words_for_street) > 2 and _GF_STREET_RE.search(name):
        cleaned = []
        for i, w in enumerate(words_for_street):
            if i >= 2 and _GF_STREET_RE.search(w):
                break
            cleaned.append(w)
        name = " ".join(cleaned)
    words = name.split()
    cleaned = []
    for w in words:
        if w.lower() in _GF_JUNK_WORDS:
            break
        cleaned.append(w)
    name = " ".join(cleaned)
    if _CORPORATE_NAME_RE.search(name):
        return None
    words = name.split()
    if len(words) < 2:
        return None
    if re.search(r"\d", name):
        return None
    if not all(
        w[0].isupper() or w[0] in "äöüÄÖÜ" or w.lower() in _GF_NAME_PARTICLES
        for w in words
        if len(w) > 1
    ):
        return None
    return name


def _extract_gf_from_impressum(text: str) -> dict:
    """Extract GF name, address fragment, and personal email from impressum text.

    Returns dict with keys: gf_name, impressum_address, personal_email (all may be None).
    """
    result: dict = {"gf_name": None, "impressum_address": None, "personal_email": None}
    if not text:
        return result

    # GF name — first pattern match wins
    for pattern in _GF_PATTERNS:
        m = pattern.search(text)
        if m:
            name = _NON_NAME_SUFFIXES.sub("", m.group(1)).strip().rstrip("-")
            # Sanity check: 2–3 words, no digits
            words = name.split()
            if 2 <= len(words) <= 4 and not re.search(r"\d", name):
                result["gf_name"] = name
                break

    # Address — street + PLZ/city block
    addr_match = re.search(
        r"([A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\s\.\-]+\d+[a-zA-Z]?\s*[\n,]\s*\d{5}\s+[A-ZÄÖÜ][a-zäöüß\s\-]+)",
        text,
    )
    if addr_match:
        result["impressum_address"] = re.sub(r"\s+", " ", addr_match.group(1)).strip()

    # Personal email — find all emails, discard generic
    for email in _EMAIL_RE.findall(text):
        local = email.split("@")[0].lower()
        first_segment = local.split(".")[0]
        if first_segment not in _GENERIC_EMAIL_PREFIXES and len(local) > 2:
            result["personal_email"] = email
            break

    return result


def _enrich_gf_via_claude(impressum_text: str) -> Optional[str]:
    """Claude CLI fallback: extract GF name from impressum text when regex finds nothing.
    Returns gf_name string or None.
    """
    import subprocess

    prompt = (
        "Extract the Geschäftsführer (managing director) name from this German impressum text.\n"
        'Return JSON only: {"gf_name": "First Last"} or {"gf_name": null} if not found.\n'
        "---\n" + impressum_text[:1500]
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        result = subprocess.run(
            [settings.CLAUDE_CMD, "--output-format", "json", "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            raw = result.stdout.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)
            gf = data.get("gf_name")
            if gf and len(str(gf).split()) >= 2:
                return str(gf).strip()
    except Exception as exc:
        logger.debug("Claude GF fallback failed: %s", exc)
    return None


def enrich_gf_cmd(
    dry_run: bool = False,
    limit: int = 0,
    db_path: Optional[Path] = None,
    kb_path: Optional[Path] = None,
) -> int:
    """Enrich A/B records with GF name, impressum address, and personal email (M21).

    For each unapproached A/B record missing gf_name:
    1. Check KB documents for impressum content.
    2. If not found: fetch /impressum → save to KB.
    3. Regex extraction. Claude CLI fallback if regex finds nothing.
    4. Write gf_name, impressum_address, gf_email (only if currently empty) to pipeline.db.
    """
    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH
    if kb_path is None:
        kb_path = settings.KNOWLEDGE_BASE_PATH

    pipeline_db.ensure_schema(db_path)

    with pipeline_db.get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT domain, scraped_text FROM company_records
               WHERE prio = 'Prio 1'
               AND already_approached = 0
               AND (gf_name IS NULL OR gf_name = '')
               ORDER BY domain"""
        ).fetchall()

    records = [{"domain": r[0], "scraped_text": r[1]} for r in rows]
    if limit > 0:
        records = records[:limit]

    total = len(records)
    logger.info("enrich-gf: %d A/B records to process (limit=%d)", total, limit)

    if dry_run:
        kb = KnowledgeBase(kb_path)
        fetch_needed = sum(
            1 for r in records if kb.get_document(r["domain"], "impressum") is None
        )
        logger.info(
            "DRY RUN — %d records, %d impressum fetches needed", total, fetch_needed
        )
        return 0

    if not records:
        logger.info("enrich-gf: nothing to do")
        return 0

    kb = KnowledgeBase(kb_path)
    found = 0
    http_calls = 0

    for i, rec in enumerate(records, 1):
        domain = rec["domain"]

        # Step 1: check KB cache
        imp_text = kb.get_document(domain, "impressum")

        # Step 2: fetch if not cached
        if imp_text is None:
            if http_calls > 0:
                time.sleep(_POLITE_DELAY_S)
            imp_text = fetch_impressum_text(domain)
            kb.save_document(
                domain, hrb_number=None, doc_type="impressum", content=imp_text
            )
            http_calls += 1
            logger.debug(
                "[%d/%d] IMPRESSUM FETCH: %s (%d chars)",
                i,
                total,
                domain,
                len(imp_text or ""),
            )

        # Step 3: regex extraction
        extracted = _extract_gf_from_impressum(imp_text or "")

        # Step 4: Claude CLI fallback when regex finds no GF name
        if extracted["gf_name"] is None:
            fallback_text = imp_text or rec.get("scraped_text") or ""
            if fallback_text:
                extracted["gf_name"] = _enrich_gf_via_claude(fallback_text)
                if extracted["gf_name"]:
                    logger.debug(
                        "[%d/%d] GF via Claude: %s → %s",
                        i,
                        total,
                        domain,
                        extracted["gf_name"],
                    )

        # Step 5: sanitize + write to DB
        gf_name = (
            _sanitize_gf_name(extracted["gf_name"]) if extracted["gf_name"] else None
        )
        impressum_addr = extracted["impressum_address"]
        personal_email = extracted["personal_email"]

        with pipeline_db.get_connection(db_path) as conn:
            pipeline_db.update_gf_enrichment(
                conn, domain, gf_name, impressum_addr, personal_email
            )

        if gf_name:
            found += 1
            logger.info("[%d/%d] GF found: %s → %s", i, total, domain, gf_name)
        else:
            logger.debug("[%d/%d] GF not found: %s", i, total, domain)

    logger.info(
        "enrich-gf complete: %d/%d records got gf_name, %d HTTP calls",
        found,
        total,
        http_calls,
    )
    return found
