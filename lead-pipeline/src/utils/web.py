"""HTTP fetch and HTML cleaning utilities."""

import json
import logging
import re
import ssl
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RepuroBot/1.0; +https://repuro.de)"}
_BOILERPLATE_TAGS = [
    "nav",
    "footer",
    "header",
    "script",
    "style",
    "noscript",
    "aside",
    "iframe",
]

# Split connect vs read timeout — old Apache servers on shared hosting (Strato, 1&1) are either
# up or not (short connect), but slow to send response body (longer read).
_TIMEOUT = httpx.Timeout(connect=6.0, read=20.0, write=10.0, pool=5.0)

# SSL context: VERIFY_X509_PARTIAL_CHAIN lets OpenSSL accept intermediate CAs in the trust store
# as full anchors — resolves "unable to get local issuer certificate" on most German SME hosts.
_ssl_ctx = ssl.create_default_context()
if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
    _ssl_ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN  # Python 3.10+

# Persistent clients — reuse TCP connections for multi-page scrapes of the same domain.
_client = httpx.Client(
    headers=_HEADERS,
    timeout=_TIMEOUT,
    follow_redirects=True,
    verify=_ssl_ctx,
)
# Fallback client for domains with completely broken/expired certs.
_client_noverify = httpx.Client(
    headers=_HEADERS,
    timeout=_TIMEOUT,
    follow_redirects=True,
    verify=False,  # noqa: S501 — intentional fallback for public business sites
)

# DNS failure keywords — no retry will fix these.
_DNS_ERRORS = (
    "getaddrinfo",
    "Name or service not known",
    "nodename nor servname",
    "NXDOMAIN",
)

# Domain-level dead cache — skip all subsequent requests for domains that are
# unreachable (DNS failure, connect refused, persistent timeout). Prevents
# burning 36+ seconds per unreachable domain across impressum/about-page probes.
_dead_domains: set[str] = set()

_CONNECT_REFUSED = ("ConnectionRefusedError", "10061", "Connection refused")


def _extract_domain(url: str) -> str:
    """Extract domain from URL for dead-domain tracking."""
    try:
        from urllib.parse import urlparse

        return urlparse(url).hostname or ""
    except Exception:
        return ""


def fetch_with_retry(
    url: str,
    retries: int = 3,
    delay: float = 1.0,
) -> Optional[str]:
    """Fetch URL with retry. Returns HTML string or None on failure.

    Error handling:
    - Dead domain (in _dead_domains cache) → skip immediately.
    - DNS failures (dead domain) → mark dead, skip immediately, no retry.
    - Connect refused → mark dead, skip immediately, no retry.
    - SSL cert errors → single retry with verify=False before giving up.
    - HTTP 403/404/410 → skip immediately.
    - Other errors → retry up to `retries` times with `delay` seconds between.
    - All retries exhausted on connect/timeout → mark domain dead.
    """
    domain = _extract_domain(url)
    if domain in _dead_domains:
        logger.debug("Dead domain cache hit for %s — skipping", url)
        return None

    for attempt in range(retries):
        try:
            response = _client.get(url)
            response.raise_for_status()
            return response.text

        except httpx.InvalidURL as e:
            logger.debug("Invalid URL %s — skipping: %s", url, e)
            return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 404, 410):
                logger.debug("HTTP %d for %s — skipping", e.response.status_code, url)
                return None
            logger.warning(
                "HTTP %d for %s (attempt %d/%d)",
                e.response.status_code,
                url,
                attempt + 1,
                retries,
            )

        except httpx.ConnectError as e:
            err_str = str(e)

            if any(kw in err_str for kw in _DNS_ERRORS):
                logger.debug("DNS failure for %s — marking dead, skipping", url)
                _dead_domains.add(domain)
                return None

            if any(kw in err_str for kw in _CONNECT_REFUSED):
                logger.debug("Connect refused for %s — marking dead, skipping", url)
                _dead_domains.add(domain)
                return None

            if "SSL" in err_str or "certificate" in err_str.lower():
                logger.debug("SSL failure for %s — retrying with verify=False", url)
                try:
                    response = _client_noverify.get(url)
                    response.raise_for_status()
                    return response.text
                except Exception:
                    pass
                return None

            logger.warning(
                "Connect error for %s: %s (attempt %d/%d)", url, e, attempt + 1, retries
            )

        except httpx.TimeoutException as e:
            logger.warning(
                "Timeout for %s (attempt %d/%d): %s", url, attempt + 1, retries, e
            )

        except httpx.RequestError as e:
            logger.warning(
                "Request error for %s: %s (attempt %d/%d)", url, e, attempt + 1, retries
            )

        if attempt < retries - 1:
            time.sleep(delay)

    # All retries exhausted — mark domain dead for remaining calls in this batch
    if domain:
        _dead_domains.add(domain)
        logger.debug("All retries exhausted for %s — marking domain dead", domain)
    return None


def clean_html(html: str) -> str:
    """Strip HTML tags, remove nav/footer boilerplate, normalize whitespace.

    Preserves German umlauts (ä/ö/ü/Ä/Ö/Ü/ß) — always parsed as UTF-8.
    Converts <br> tags to newlines before stripping so address lines in footer
    HTML (e.g. GmbH<br>Musterstraße 1<br>12345 Stadt) remain parseable.
    """
    if not html:
        return ""
    # Replace <br> variants with newline before parsing — preserves address structure
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_BOILERPLATE_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ")
    lines = (line.strip() for line in text.splitlines())
    joined = " ".join(part for line in lines for part in [line] if part)
    return re.sub(r" {2,}", " ", joined)


def extract_page_text(
    domain: str,
    extra_paths: Optional[list[str]] = None,
    max_chars: int = 2500,
    homepage_min_chars: int = 800,
) -> str:
    """Fetch and combine text from domain homepage + extra_paths, up to max_chars.

    Strategy:
    1. Try HTTPS homepage. If empty, fall back to HTTP homepage.
    2. If homepage already yields >= homepage_min_chars, skip extra paths.
    3. Fetch extra paths only until max_chars is reached.
    """
    if extra_paths is None:
        extra_paths = ["/leistungen", "/service", "/produkte", "/ueber-uns"]

    collected: list[str] = []
    total_chars = 0

    # Homepage — HTTPS first, HTTP fallback.
    for scheme in ("https", "http"):
        html = fetch_with_retry(f"{scheme}://{domain}")
        if html:
            text = clean_html(html)
            chunk = text[:max_chars]
            if chunk:
                collected.append(chunk)
                total_chars += len(chunk)
            break  # stop trying schemes once we got a response

    # If homepage alone is sufficient, skip extra paths.
    if total_chars >= homepage_min_chars:
        return " ".join(collected)[:max_chars]

    # Fetch extra paths for more content.
    for path in extra_paths:
        if total_chars >= max_chars:
            break
        html = fetch_with_retry(f"https://{domain}{path}")
        if html:
            text = clean_html(html)
            remaining = max_chars - total_chars
            chunk = text[:remaining]
            if chunk:
                collected.append(chunk)
                total_chars += len(chunk)

    return " ".join(collected)[:max_chars]


_BOILERPLATE_MARKERS = [
    "impressum generator",
    "erecht24",
    "janolaw",
    "datenschutz-generator",
    "kostenlos & rechtssicher",
]


def _is_boilerplate(text: str) -> bool:
    """Detect third-party legal generator pages (eRecht24, janolaw, etc.)."""
    lower = text[:500].lower()
    return any(m in lower for m in _BOILERPLATE_MARKERS)


def fetch_impressum_text(domain: str) -> str:
    """Fetch /impressum page text. Tries common URL variants, then link-scans homepage.
    Returns clean text or empty string on failure. Stored separately from scraped_text.
    """
    paths = [
        "/impressum",
        "/impressum.html",
        "/impressum.php",
        "/de/impressum",
        "/datenschutz",
        "/datenschutzerklaerung",
        "/privacy-policy",
    ]
    for path in paths:
        html = fetch_with_retry(f"https://{domain}{path}")
        if html:
            text = clean_html(html)
            if len(text) > 100 and not _is_boilerplate(text):
                return text

    # Fallback: scan main page for an impressum href link
    main_html = fetch_with_retry(f"https://{domain}")
    if main_html:
        links = re.findall(
            r'href=["\']([^"\']*(?:impressum|datenschutz|privacy.policy)[^"\']*)["\']',
            main_html,
            re.IGNORECASE,
        )
        seen: set[str] = set()
        for link in links:
            if link.startswith("http"):
                url = link
            elif link.startswith("/"):
                url = f"https://{domain}{link}"
            else:
                continue
            url = url.split("?")[0].rstrip("/")
            if url in seen:
                continue
            seen.add(url)
            html = fetch_with_retry(url)
            if html:
                text = clean_html(html)
                if len(text) > 100 and not _is_boilerplate(text):
                    return text

    return ""


_ABOUT_SUFFIXES = [
    "/ueber-uns",
    "/ueberuns",
    "/über-uns",
    "/unternehmen",
    "/das-unternehmen",
    "/wir-ueber-uns",
    "/wer-wir-sind",
    "/about",
    "/about-us",
    "/profil",
    "/firma",
    "/firmenprofil",
    "/firmenportrait",
    "/firmengeschichte",
    "/unternehmensgeschichte",
    "/philosophie",
    "/unsere-philosophie",
    "/leitbild",
    "/portrait",
    "/historie",
    "/geschichte",
    "/unsere-geschichte",
    "/team",
    "/unser-team",
    "/kompetenz",
    "/company",
    "/company-profile",
    "/mission",
    "/vision",
]


def fetch_about_page_text(domain: str) -> tuple[Optional[str], Optional[str]]:
    """Fetch about/company page text. Tries common URL suffixes, stops at first hit.

    Returns (cleaned_text, matched_suffix) on success, (None, None) if none match.
    Only accepts pages with >100 chars of cleaned text to filter out error/redirect stubs.
    """
    for i, suffix in enumerate(_ABOUT_SUFFIXES):
        if i > 0:
            time.sleep(0.3)  # polite delay between attempts
        html = fetch_with_retry(f"https://{domain}{suffix}", retries=1)
        if html:
            text = clean_html(html)
            if len(text) > 100:
                logger.debug(
                    "About page hit for %s at %s (%d chars)", domain, suffix, len(text)
                )
                return text, suffix
    return None, None


_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def extract_jsonld_address(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extract street and PLZ+city from JSON-LD structured data in raw HTML.

    Many German SME sites embed schema.org/LocalBusiness or Organization with
    a PostalAddress block for SEO. This catches addresses that never appear in
    /impressum paths (e.g. aplusm-care.de).

    Returns (street, plz_ort) or (None, None) if no usable address found.
    """
    for m in _JSON_LD_RE.finditer(html):
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            addr = item.get("address") or {}
            street_raw = addr.get("streetAddress", "").strip()
            city = addr.get("addressLocality", "").strip()
            plz = addr.get("postalCode", "").strip()
            # streetAddress sometimes contains "Street, CompanyName" — take part before comma
            if "," in street_raw:
                street_raw = street_raw.split(",")[0].strip()
            if street_raw and plz and len(plz) == 5 and plz.isdigit():
                return street_raw, f"{plz} {city}" if city else plz
    return None, None
