"""Deep impressum rescraper — sitemap + contact fallback for domains with empty KB entries.

Strategy per domain:
1. Try standard impressum paths (already done by targeted scraper)
2. Parse /sitemap.xml and /sitemap.txt for impressum URLs
3. Try /robots.txt to find sitemap location
4. Try /kontakt, /kontakt.html, /contact, /ueber-uns as last resort
5. Special: extract Austrian address from steri24.de KB entry (4-digit PLZ)

Run from lead-pipeline root: python scripts/rescrape_impressum_deep.py
"""

import io
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, "src")

import sqlite3
from config import settings
from pipeline.normalize import parse_impressum_address
from utils.web import fetch_with_retry, clean_html

PIPELINE_DB = settings.PIPELINE_DB_PATH
KB_DB = PIPELINE_DB.parent / "knowledge_base.db"

TARGETS = [
    "clavaro.de",
    "pulox.de",
    "steri-shop.com",
    "leitner-service.de",
    "actipart.de",
    "zekamed.de",
    "hestomed-helbig.de",
    "habys.de",
    "eu-medical.de",
    "ana-trade.de",
    "aplusm-care.de",
    "steri24.de",  # Austrian — special handling
]

EXTRA_PATHS = [
    "/kontakt",
    "/kontakt.html",
    "/kontakt.php",
    "/contact",
    "/ueber-uns",
    "/ueber-uns.html",
    "/about",
    "/about-us",
    "/de/kontakt",
]

_XML_URL_RE = re.compile(
    r"<loc>\s*(https?://[^<]+impressum[^<]*)\s*</loc>", re.IGNORECASE
)
_TXT_URL_RE = re.compile(r"https?://\S+impressum\S*", re.IGNORECASE)
_ROBOTS_SITEMAP_RE = re.compile(
    r"^Sitemap:\s*(https?://\S+)", re.IGNORECASE | re.MULTILINE
)

# Austrian 4-digit PLZ pattern (for steri24.de)
_AT_PLZ_RE = re.compile(r"(\d{4})\s+([A-ZÄÖÜa-zäöüß][A-ZÄÖÜa-zäöüß\-]+)")
_AT_STREET_RE = re.compile(
    r"([A-ZÄÖÜa-zäöüß][A-ZÄÖÜa-zäöüß.\- ]{1,38}?)\s+(\d+\s*[a-zA-Z]?)\s*$",
    re.MULTILINE,
)


def find_impressum_via_sitemap(domain: str) -> str | None:
    """Try sitemap.xml + sitemap.txt + robots.txt to discover impressum URL."""
    for sitemap_path in ("/sitemap.xml", "/sitemap.txt"):
        html = fetch_with_retry(f"https://{domain}{sitemap_path}", retries=2)
        if not html:
            continue
        urls = _XML_URL_RE.findall(html) or _TXT_URL_RE.findall(html)
        for url in urls:
            url = url.strip().rstrip("/")
            imp_html = fetch_with_retry(url, retries=2)
            if imp_html:
                text = clean_html(imp_html)
                if len(text) > 100:
                    return text

    # robots.txt sitemap pointer
    robots = fetch_with_retry(f"https://{domain}/robots.txt", retries=1)
    if robots:
        for sitemap_url in _ROBOTS_SITEMAP_RE.findall(robots):
            html = fetch_with_retry(sitemap_url, retries=2)
            if html:
                urls = _XML_URL_RE.findall(html) or _TXT_URL_RE.findall(html)
                for url in urls:
                    url = url.strip().rstrip("/")
                    imp_html = fetch_with_retry(url, retries=2)
                    if imp_html:
                        text = clean_html(imp_html)
                        if len(text) > 100:
                            return text
    return None


def find_address_via_contact_pages(domain: str) -> str | None:
    """Try contact/about pages for address content."""
    for path in EXTRA_PATHS:
        html = fetch_with_retry(f"https://{domain}{path}", retries=2)
        if html:
            text = clean_html(html)
            if len(text) > 100:
                return text
    return None


def extract_austrian_address(text: str) -> tuple[str, str]:
    """Extract Austrian 4-digit PLZ address from text."""
    plz_match = _AT_PLZ_RE.search(text)
    if not plz_match:
        return "", ""
    plz = plz_match.group(1)
    city = plz_match.group(2)
    # Search 60 chars before PLZ for street+number
    start = max(0, plz_match.start() - 60)
    snippet = text[start : plz_match.start()]
    street_match = _AT_STREET_RE.search(snippet)
    if street_match:
        return (
            f"{street_match.group(1)} {street_match.group(2)}".strip(),
            f"{plz} {city}",
        )
    return "", f"{plz} {city}"


def upsert_kb(kb: sqlite3.Connection, domain: str, text: str) -> None:
    existing = kb.execute(
        "SELECT id FROM documents WHERE domain=? AND doc_type='impressum'", (domain,)
    ).fetchone()
    if existing:
        kb.execute(
            "UPDATE documents SET content=? WHERE domain=? AND doc_type='impressum'",
            (text, domain),
        )
    else:
        kb.execute(
            "INSERT INTO documents (domain, hrb_number, doc_type, content) VALUES (?,NULL,'impressum',?)",
            (domain, text),
        )
    kb.commit()


def main() -> None:
    pipeline = sqlite3.connect(str(PIPELINE_DB))
    kb = sqlite3.connect(str(KB_DB))
    kb.row_factory = sqlite3.Row

    results: list[tuple[str, str, str]] = []

    for i, domain in enumerate(TARGETS, 1):
        print(f"[{i}/{len(TARGETS)}] {domain} ... ", end="", flush=True)

        # Special case: steri24.de — Austrian address already in KB
        if domain == "steri24.de":
            row = kb.execute(
                "SELECT content FROM documents WHERE domain=? AND doc_type='impressum'",
                (domain,),
            ).fetchone()
            if row and row["content"]:
                street, plz_ort = extract_austrian_address(row["content"])
                if street or plz_ort:
                    print(f"AT address: street={street!r} plz_ort={plz_ort!r}")
                    results.append((domain, street, plz_ort))
                    if i < len(TARGETS):
                        time.sleep(0.5)
                    continue
            print("no AT address found in KB")
            results.append((domain, "", ""))
            continue

        # Try sitemap discovery
        text = find_impressum_via_sitemap(domain)
        if text:
            print(f"sitemap hit ({len(text)} chars)", end=" ")
            upsert_kb(kb, domain, text)
            street, plz_ort = parse_impressum_address(text)
            print(f"→ street={street!r} plz_ort={plz_ort!r}")
            results.append((domain, street or "", plz_ort or ""))
            if i < len(TARGETS):
                time.sleep(1.0)
            continue

        # Try contact/about pages
        text = find_address_via_contact_pages(domain)
        if text:
            street, plz_ort = parse_impressum_address(text)
            if street or plz_ort:
                print(f"contact page hit → street={street!r} plz_ort={plz_ort!r}")
                upsert_kb(kb, domain, text)
                results.append((domain, street or "", plz_ort or ""))
                if i < len(TARGETS):
                    time.sleep(1.0)
                continue

        print("no result — manual required")
        results.append((domain, "", ""))
        if i < len(TARGETS):
            time.sleep(1.0)

    kb.close()

    # Write found addresses back to pipeline.db
    updated = 0
    for domain, street, plz_ort in results:
        if street or plz_ort:
            pipeline.execute(
                "UPDATE company_records SET street=?, plz_ort=? WHERE domain=? AND source='MANUAL'",
                (street or None, plz_ort or None, domain),
            )
            updated += 1
    pipeline.commit()
    pipeline.close()

    print()
    print("=== Summary ===")
    got = [(d, s, p) for d, s, p in results if s or p]
    manual = [d for d, s, p in results if not s and not p]
    print(f"  Got address:    {len(got)}")
    print(f"  Manual needed:  {len(manual)}")
    if manual:
        print(f"  Manual domains: {', '.join(manual)}")
    print(f"  DB updated:     {updated} records")
    print()
    print("Run: python pipeline.py normalize")


if __name__ == "__main__":
    main()
