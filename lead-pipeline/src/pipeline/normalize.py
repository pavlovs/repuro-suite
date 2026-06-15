"""Data quality normalization (M18). Title-case, umlaut restoration, anrede, salutation rebuild.

Operates on pipeline.db records directly. Does NOT change pipeline_stage — normalization
is orthogonal to pipeline flow. Only processes ORBIS/WLW-source records (not serienbriefe).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from src.config import settings
from src.pipeline import db as pipeline_db
from src.pipeline.region_lookup import load_region_mapping

logger = logging.getLogger(__name__)

# German legal forms that must keep canonical casing after str.title()
_LEGAL_FORMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bGmbh\b", re.IGNORECASE), "GmbH"),
    (re.compile(r"\bKgaa\b", re.IGNORECASE), "KGaA"),
    (re.compile(r"\bE\.k\.\b", re.IGNORECASE), "e.K."),
    (re.compile(r"\bE\.k\b", re.IGNORECASE), "e.K."),
    (re.compile(r"\bMbh\b", re.IGNORECASE), "mbH"),
    (re.compile(r"\bOhg\b", re.IGNORECASE), "OHG"),
    (re.compile(r"\bGbr\b", re.IGNORECASE), "GbR"),
    (re.compile(r"\b(?<!\w)Ug\b", re.IGNORECASE), "UG"),
    (re.compile(r"\b(?<!\w)Ag\b", re.IGNORECASE), "AG"),
    (re.compile(r"\b(?<!\w)Kg\b", re.IGNORECASE), "KG"),
    (re.compile(r"\bCo\.\b", re.IGNORECASE), "Co."),
]

# German prepositions/articles to lowercase (except when first word)
_LOWERCASE_WORDS = {
    "Und",
    "Der",
    "Des",
    "Die",
    "Das",
    "Von",
    "Vom",
    "Am",
    "Im",
    "Für",
    "Fuer",
    "Zur",
    "Zum",
}


def title_case_german(text: str) -> str:
    """Title-case with German legal form preservation and preposition lowering."""
    if not text or not text.strip():
        return text
    result = text.title()
    # Fix legal forms
    for pattern, replacement in _LEGAL_FORMS:
        result = pattern.sub(replacement, result)
    # Lowercase prepositions (but not if first word)
    words = result.split()
    for i in range(1, len(words)):
        if words[i] in _LOWERCASE_WORDS:
            words[i] = words[i].lower()
    result = " ".join(words)
    # Fix "&" contexts: "& co." should stay "& Co."
    result = re.sub(r"& co\.", "& Co.", result, flags=re.IGNORECASE)
    return result


def restore_umlauts_city(text: str, city_lookup: dict[str, str]) -> str:
    """Restore umlauts in city names using the Städte-Regionen-Matching lookup.

    Args:
        text: City name (potentially ALL CAPS with ae/oe/ue substitutions)
        city_lookup: {lowercase_city: canonical_city} from build_city_umlaut_lookup()
    """
    if not text or not text.strip():
        return text
    key = text.strip().lower()
    return city_lookup.get(key, text)


def build_city_umlaut_lookup() -> dict[str, str]:
    """Build {lowercased_city: canonical_city} from the region mapping.

    This also maps ae/oe/ue variants: e.g. "duesseldorf" -> "Düsseldorf"
    by generating the de-umlauted key for each city that contains umlauts.
    """
    mapping = load_region_mapping()
    lookup: dict[str, str] = {}
    for city_lower, (region, region_prep) in mapping.items():
        # Reconstruct the canonical city name from the region mapping
        # The mapping stores lowercase keys, but we need the original casing.
        # Since we only have lowercase, title-case it.
        canonical = title_case_german(city_lower.title())
        # Check if any entry in the original Excel has this city with proper casing
        # For now, use the title-cased version
        lookup[city_lower] = canonical

    # Now load the actual Excel to get proper casing
    try:
        import openpyxl

        wb = openpyxl.load_workbook(
            settings.SOURCE_EXCEL, read_only=True, data_only=True
        )
        ws = wb["Städte-Regionen-Matching"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            city = row[0]
            if city:
                city_str = str(city).strip()
                lookup[city_str.lower()] = city_str
                # Also add de-umlauted variant as key
                deumlauted = _deumlaut(city_str.lower())
                if deumlauted != city_str.lower():
                    lookup[deumlauted] = city_str
        wb.close()
    except Exception as e:
        logger.warning("Could not load Excel for city lookup: %s", e)

    return lookup


def _deumlaut(text: str) -> str:
    """Convert umlauts to ae/oe/ue (for generating lookup keys)."""
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")]:
        text = text.replace(src, dst)
    return text


def restore_umlauts_pattern(text: str) -> str:
    """Restore umlauts using a conservative allowlist of unambiguous patterns."""
    if not text or not text.strip():
        return text
    result = text
    # Handle "strasse" -> "straße" (case-preserving)
    result = re.sub(r"(?i)strasse\b", _replace_strasse, result)
    # Handle "aerzte" -> "ärzte"
    result = re.sub(r"(?i)aerzte", _replace_aerzte, result)
    return result


# Common German names/words with umlauts — maps de-umlauted form to correct spelling.
# Only includes unambiguous cases where the ae/oe/ue form is never a valid standalone word.
_NAME_UMLAUT_MAP: dict[str, str] = {
    # ö first names
    "joerg": "Jörg",
    "goetz": "Götz",
    "soeren": "Sören",
    "joergen": "Jörgen",
    "goertz": "Görtz",
    "koerber": "Körber",
    # ü first names
    "juergen": "Jürgen",
    "guenther": "Günther",
    "guenter": "Günter",
    "ruediger": "Rüdiger",
    "lueder": "Lüder",
    "hueseyin": "Hüseyin",
    # ä first names
    "baerbel": "Bärbel",
    "kaete": "Käte",
    "kaethi": "Käthi",
    # Common surnames (unambiguous: ae/oe/ue form has no other meaning)
    "graef": "Gräf",
    "graefer": "Gräfer",
    "koenig": "König",
    "koenigs": "Königs",
    "mueller": "Müller",
    "schroeder": "Schröder",
    "schroeter": "Schröter",
    "moeller": "Möller",
    "koehler": "Köhler",
    "goebel": "Göbel",
    "boehm": "Böhm",
    "boehme": "Böhme",
    "roemer": "Römer",
    "roeser": "Röser",
    "hoefer": "Höfer",
    "hoeffler": "Höffler",
    "loeffler": "Löffler",
    "groener": "Gröner",
    "kroeger": "Kröger",
    "stoehr": "Stöhr",
    "voelker": "Völker",
    "voelkl": "Völkl",
    "zoeller": "Zöller",
    "schuelke": "Schülke",
    "buehler": "Bühler",
    "huebner": "Hübner",
    "kuehn": "Kühn",
    "kuehne": "Kühne",
    "kuehner": "Kühner",
    "fuehring": "Führing",
    "wuensch": "Wünsch",
    "straetz": "Strätz",
    # Common city/place parts in company names
    "duesseldorf": "Düsseldorf",
    "muenchen": "München",
    "nuernberg": "Nürnberg",
    "muenster": "Münster",
    "wuerzburg": "Würzburg",
    "luebeck": "Lübeck",
    "tuebingen": "Tübingen",
    "goettingen": "Göttingen",
    "saarbruecken": "Saarbrücken",
    "osnabrueck": "Osnabrück",
    "lueneburg": "Lüneburg",
    "bruegel": "Brügel",
    "bruehl": "Brühl",
    "fuerth": "Fürth",
    "gruenwald": "Grünwald",
    "koeln": "Köln",
}


# Common German words with umlauts — for AI-generated text (mehrwerte, compliments).
# Only unambiguous cases where the ASCII de-umlauted form is never a valid German word.
_GERMAN_UMLAUT_WORDS: dict[str, str] = {
    # ü words
    "fuer": "für",
    "ueber": "über",
    "pruefung": "Prüfung",
    "pruefungen": "Prüfungen",
    "fuehrend": "führend",
    "fuehrende": "führende",
    "fuehrenden": "führenden",
    "fuehrung": "Führung",
    "durchfuehrung": "Durchführung",
    "gruendung": "Gründung",
    "gruendlich": "gründlich",
    "unterstuetzen": "unterstützen",
    "unterstuetzung": "Unterstützung",
    "stuetzpunkt": "Stützpunkt",
    "ausruestung": "Ausrüstung",
    "gebuehren": "Gebühren",
    # ö words
    "roentgen": "Röntgen",
    "roentgenanlagen": "Röntgenanlagen",
    "roentgentechnik": "Röntgentechnik",
    "loesungen": "Lösungen",
    "loesung": "Lösung",
    "erloese": "Erlöse",
    "behoerden": "Behörden",
    "foerderung": "Förderung",
    "stoerung": "Störung",
    "stoerungen": "Störungen",
    # ä words
    "geraet": "Gerät",
    "geraete": "Geräte",
    "geraeten": "Geräten",
    "geraetewartung": "Gerätewartung",
    "aerztlich": "ärztlich",
    "aerztliche": "ärztliche",
    "aerztlichen": "ärztlichen",
    "aerzten": "Ärzten",
    "aerzte": "Ärzte",
    "qualitaet": "Qualität",
    "qualitaetssicherung": "Qualitätssicherung",
    "zuverlaessig": "zuverlässig",
    "zuverlaessige": "zuverlässige",
    "zuverlaessigen": "zuverlässigen",
    "zuverlaessigkeit": "Zuverlässigkeit",
    "unabhaengig": "unabhängig",
    "unabhaengige": "unabhängige",
    "unabhaengigen": "unabhängigen",
    "unabhaengigkeit": "Unabhängigkeit",
    "herstellerunabhaengig": "herstellerunabhängig",
    "herstellerunabhaengige": "herstellerunabhängige",
    "herstellerunabhaengigen": "herstellerunabhängigen",
    "herstellerunabhaengiger": "herstellerunabhängiger",
    "herstellerunabhaengiges": "herstellerunabhängiges",
    "herstelleruebergreifend": "herstellerübergreifend",
    "herstelleruebergreifende": "herstellerübergreifende",
    "herstelleruebergreifenden": "herstellerübergreifenden",
    "herstelleruebergreifender": "herstellerübergreifender",
    "verlaesslich": "verlässlich",
    "verlaesslichkeit": "Verlässlichkeit",
    "staerke": "Stärke",
    "staerken": "Stärken",
    "naehe": "Nähe",
    "waehrend": "während",
    "leistungsfaehig": "leistungsfähig",
    "leistungsfaehigkeit": "Leistungsfähigkeit",
    "zukunftsfaehig": "zukunftsfähig",
    "praxisablaeufe": "Praxisabläufe",
    "ablaeufe": "Abläufe",
    "zubehoer": "Zubehör",
    "zubehoervertrieb": "Zubehörvertrieb",
    "aehnlich": "ähnlich",
    "saeule": "Säule",
    "saeulen": "Säulen",
    "ueberzeugung": "Überzeugung",
    "uebergreifend": "übergreifend",
    "beschraenkt": "beschränkt",
    "beschraenkter": "beschränkter",
    "beschraenkung": "Beschränkung",
    "erschliessung": "Erschließung",
    # ß words
    "groesste": "größte",
    "groessten": "größten",
    "massnahmen": "Maßnahmen",
    "massnahme": "Maßnahme",
}


def restore_umlauts_german(text: str) -> str:
    """Restore umlauts in common German words using a conservative allowlist.

    For AI-generated text (mehrwerte, compliments) where Claude sometimes
    produces de-umlauted words when source website uses ASCII encoding.
    Splits on word boundaries, checks each word against the map.
    """
    if not text or not text.strip():
        return text
    words = re.split(r"(\s+)", text)  # keep whitespace tokens
    result = []
    for token in words:
        if not token.strip():
            result.append(token)
            continue
        key = token.lower().rstrip(".,;:!?")
        suffix = token[len(token.rstrip(".,;:!?")) :]
        word_part = token[: len(token) - len(suffix)]
        if key in _GERMAN_UMLAUT_WORDS:
            replacement = _GERMAN_UMLAUT_WORDS[key]
            # Preserve ALL CAPS from original
            if word_part.isupper():
                replacement = replacement.upper()
            result.append(replacement + suffix)
        else:
            result.append(token)
    return "".join(result)


def fix_compliment_text(
    k1: Optional[str], k2: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Rule-based post-processing for compliment K1 and K2 text.

    K1 rules: strip leading "Besonders "/"Auch ", strip trailing period.
    K2 rules: strip leading "Auch ", strip trailing period, warn if missing verb.
    """
    if k1:
        k1 = k1.strip()
        # Strip leading "Besonders " — template already has "Besonders beeindruckt hat uns {k1}"
        if k1.lower().startswith("besonders "):
            k1 = k1[len("besonders ") :].lstrip()
            if k1 and k1[0].isupper():
                k1 = k1[0].lower() + k1[1:]
        # Strip leading "Auch " — wrong slot
        if k1.lower().startswith("auch "):
            k1 = k1[len("auch ") :].lstrip()
            if k1 and k1[0].isupper():
                k1 = k1[0].lower() + k1[1:]
        # Strip trailing punctuation (K1 is mid-sentence; template adds ".")
        k1 = k1.rstrip(".,;")
        k1 = k1.strip() or None

    if k2:
        k2 = k2.strip()
        # Strip leading "Auch " — template already has "Auch {k2} uns davon überzeugt"
        if k2.lower().startswith("auch "):
            k2 = k2[len("auch ") :].lstrip()
        # Strip trailing period
        k2 = k2.rstrip(".")
        k2 = k2.strip()
        # Warn if missing required verb
        if k2 and "hat" not in k2.lower() and "haben" not in k2.lower():
            logger.warning("K2 missing verb 'hat/haben': %r", k2[:80])
        k2 = k2 or None

    return k1, k2


# German PLZ pattern: 5-digit zip followed by city name
# Handles "St. Egidien", hyphenated "Moerfelden-Walldorf"
# Negative lookbehind excludes phone numbers like "(05341) 31137"
# Only allows second word after hyphen (compound cities), not after space
_NON_CITY_WORDS = frozenset(
    {
        "handelsregister",
        "registergericht",
        "amtsgericht",
        "telefon",
        "tel",
        "fax",
        "email",
        "vertreten",
        "geschäftsführer",
        "inhaber",
        "kontakt",
        "umsatzsteuer",
        "registernummer",
        "hrb",
        "hra",
    }
)
_LEGAL_SUFFIX_RE_ADDR = re.compile(
    r"(?:GmbH|AG|KG|e\.?\s*K\.|mbH|OHG|UG|eG|e\.?\s*V\.)\s*$", re.IGNORECASE
)

_PLZ_CITY_RE = re.compile(
    r"(?<!\d)(\d{5})(?!\d)\s+([A-ZÄÖÜa-zäöüß\x80-\xff][A-ZÄÖÜa-zäöüß\x80-\xff\-]+)"
)

_LABELED_STREET_RE = re.compile(
    r"(?:Stra(?:ss|ß)e|Anschrift|Adresse)\s*[:/]\s*(.+?\d+[a-zA-Z]?)",
    re.IGNORECASE,
)
_LABELED_PLZ_RE = re.compile(
    r"(?:PLZ\s*(?:/\s*Ort)?|Ort)\s*[:/]\s*(\d{5})\s+(\S+(?:\s+\S+)?)",
    re.IGNORECASE,
)

_STREET_NUM_RE = re.compile(
    r"([A-ZÄÖÜa-zäöüß\x80-\xff][A-ZÄÖÜa-zäöüß\x80-\xff.\- ]{1,38}?)\s+(\d+\s*[a-zA-Z]?(?:\s*[-–/]\s*\d+)?)\s*$",
    re.MULTILINE,
)
# Fallback: abbreviated street with number directly attached "Walter-Kühn-Str.1a"
# No space in char class — forces single-word match, preventing "Julian Ponke Str.1a" capture.
_STREET_ABBR_RE = re.compile(
    r"([A-ZÄÖÜa-zäöüß\x80-\xff][A-ZÄÖÜa-zäöüß\x80-\xff.\-]{1,30}?\.)(\d+\s*[a-zA-Z]?(?:\s*[-–/]\s*\d+)?)\s*$",
    re.MULTILINE,
)


_STREET_INDICATOR_SUFFIXES = (
    "straße",
    "strasse",
    "str.",
    "weg",
    "allee",
    "platz",
    "ring",
    "gasse",
    "damm",
    "chaussee",
    "ufer",
    "pfad",
    "steig",
)


_STREET_PREFIXES = {
    "am",
    "an",
    "auf",
    "bei",
    "im",
    "in",
    "ob",
    "vor",
    "zum",
    "zur",
    "von",
    "alte",
    "alter",
    "altes",
    "neue",
    "neuer",
    "neues",
    "obere",
    "untere",
}


def _clean_street(raw: str) -> Optional[str]:
    """Strip company-name junk from a raw street candidate."""
    raw = _LEGAL_SUFFIX_RE_ADDR.sub("", raw).strip()
    for sep in [
        "GmbH",
        "& Co.",
        "Co. KG",
        "TMG",
        "DDG",
        " und ",
        "Postanschrift",
        "Sitz",
        "vertreten durch",
    ]:
        idx = raw.lower().find(sep.lower())
        if idx >= 0:
            raw = raw[idx + len(sep) :].strip()
    raw = re.sub(r"^[^A-ZÄÖÜa-zäöüß]+", "", raw)
    # Strip leading junk before the street name.
    # Rule: if the indicator IS the whole word ("Str.", "Straße", "Weg"), the
    # preceding word is always part of the street name ("Bonner Str.").
    # If the indicator is embedded in a compound word ("Birkenallee"), the
    # preceding word might be a person name — only keep known street prefixes.
    words = raw.split()
    if len(words) >= 3:
        for i, w in enumerate(words):
            wl = w.lower().rstrip(".")
            is_standalone_suffix = wl in {
                "str",
                "straße",
                "strasse",
                "weg",
                "allee",
                "platz",
                "ring",
                "gasse",
                "damm",
                "chaussee",
                "ufer",
                "pfad",
                "steig",
            }
            if any(w.lower().endswith(ind) for ind in _STREET_INDICATOR_SUFFIXES):
                if i == 0:
                    break
                if is_standalone_suffix:
                    raw = " ".join(words[max(0, i - 1) :])
                elif words[i - 1].lower() in _STREET_PREFIXES:
                    raw = " ".join(words[i - 1 :])
                else:
                    raw = " ".join(words[i:])
                break
    if len(raw) < 3 or not re.search(r"\d", raw):
        return None
    return raw


_IMPRESSUM_ANCHOR_RE = re.compile(
    r"(?:Angaben\s+gem[äa](?:ß|ss)\s+§\s*5\s+TMG|"
    r"Angaben\s+gem[äa](?:ß|ss)\s+§\s*5\s+DDG|"
    r"Impressum\s+Angaben|"
    r"Inhaltlich\s+verantwortlich|"
    r"Anbieterkennzeichnung)",
    re.IGNORECASE,
)

_THIRD_PARTY_CONTEXT_RE = re.compile(
    r"(?:Hoster|Hosting|Host\s+Europe|Auftragsverarbeitung|"
    r"Auftragsverarbeiter|Server\s*-?\s*Standort|"
    r"im\s+Folgenden|nachfolgend|Drittanbieter|"
    r"Borlabs|Google\s+Analytics|Cloudflare)",
    re.IGNORECASE,
)


def _extract_street_from_before(before: str) -> Optional[str]:
    """Try to extract street+number from the text preceding a PLZ match."""
    before = re.sub(r"\s+[A-Z]{1,2}-\s*$", "", before)
    before = re.sub(r"[,;.\s]+$", "", before)
    sm = _STREET_NUM_RE.search(before)
    if sm:
        candidate = _clean_street(f"{sm.group(1).strip()} {sm.group(2).strip()}")
        if candidate:
            return candidate
    sm2 = _STREET_ABBR_RE.search(before)
    if sm2:
        candidate = _clean_street(f"{sm2.group(1).strip()}{sm2.group(2).strip()}")
        if candidate:
            return candidate
    return None


def parse_impressum_address(
    impressum_text: str,
) -> tuple[Optional[str], Optional[str]]:
    """Extract street and PLZ+Ort from German impressum text.

    Strategy: find PLZ+city first (most reliable anchor), then look for the
    street in the preceding context. Falls back to labeled patterns.

    On pages with multiple addresses (datenschutz pages list hosting provider
    before company address), prioritize PLZ matches near "§ 5 TMG" / "Impressum"
    anchors and skip matches in third-party contexts.
    """
    if not impressum_text:
        return None, None

    street = None
    plz_ort = None

    # 1. Labeled patterns (explicit "Straße:", "PLZ / Ort:" labels)
    m = _LABELED_PLZ_RE.search(impressum_text)
    if m:
        plz_ort = f"{m.group(1)} {m.group(2)}"
    m = _LABELED_STREET_RE.search(impressum_text)
    if m:
        candidate = _clean_street(m.group(1).strip())
        if candidate:
            street = candidate

    if street and plz_ort:
        return street, plz_ort

    # 2. Structural: find PLZ+City, then grab street from preceding context.
    #    Two passes: first try PLZ matches near an impressum anchor ("§ 5 TMG"),
    #    then fall back to any PLZ match (skipping third-party contexts).
    all_plz = []
    for m in _PLZ_CITY_RE.finditer(impressum_text):
        plz = m.group(1)
        city = m.group(2).strip()
        if len(city) < 2 or city[0].isdigit():
            continue
        if city.lower().split("-")[0] in _NON_CITY_WORDS:
            continue
        all_plz.append((m, plz, city))

    # Pass 1: PLZ near an impressum anchor (within ~300 chars after anchor)
    anchor = _IMPRESSUM_ANCHOR_RE.search(impressum_text)
    if anchor:
        anchor_pos = anchor.start()
        for m, plz, city in all_plz:
            if anchor_pos <= m.start() <= anchor_pos + 300:
                before = impressum_text[max(0, m.start() - 60) : m.start()]
                s = _extract_street_from_before(before)
                if s:
                    return s, f"{plz} {city}"
                if not plz_ort:
                    plz_ort = f"{plz} {city}"

    # Pass 2: any PLZ match, skipping third-party contexts
    for m, plz, city in all_plz:
        context = impressum_text[max(0, m.start() - 120) : m.start()]
        if _THIRD_PARTY_CONTEXT_RE.search(context):
            continue
        if not plz_ort:
            plz_ort = f"{plz} {city}"
        if not street:
            before = impressum_text[max(0, m.start() - 60) : m.start()]
            street = _extract_street_from_before(before)
        if street and plz_ort:
            break

    return street, plz_ort


def restore_umlauts_name(text: str) -> str:
    """Restore umlauts in person/company names using a dictionary of known mappings.

    Handles individual words within the text: "Joerg Mueller" → "Jörg Mueller".
    Only replaces when the lowercase word is an unambiguous match.
    """
    if not text or not text.strip():
        return text
    words = text.split()
    result = []
    for word in words:
        key = word.lower()
        if key in _NAME_UMLAUT_MAP:
            # Preserve the original casing pattern
            replacement = _NAME_UMLAUT_MAP[key]
            result.append(replacement)
        else:
            result.append(word)
    return " ".join(result)


def _replace_strasse(match: re.Match) -> str:
    """Case-preserving replacement for strasse -> straße.

    Called after title_case_german(), so input is always title-cased (never ALL CAPS).
    """
    s = match.group()
    if s[0].isupper():
        return "Straße"
    return "straße"


def _replace_aerzte(match: re.Match) -> str:
    """Case-preserving replacement for aerzte -> ärzte."""
    s = match.group()
    if s[0].isupper():
        return "Ärzte"
    return "ärzte"


_LEGAL_ENTITY_RE = re.compile(
    r"\b(GmbH|GbR|KG|OHG|UG|AG|(?i:holding|capital|consulting|verwaltung|beteiligungs))\b"
)

_ANREDE_MAP = {
    "MR": "Herr",
    "MR.": "Herr",
    "MRS": "Frau",
    "MRS.": "Frau",
    "MS": "Frau",
    "MS.": "Frau",
    "HERR": "Herr",
    "FRAU": "Frau",
}


def normalize_anrede(raw: Optional[str]) -> Optional[str]:
    """Normalize MR/MRS/MS to Herr/Frau. Returns None if blank or unknown."""
    if not raw or not raw.strip():
        return None
    key = raw.strip().upper()
    return _ANREDE_MAP.get(
        key, raw.strip() if raw.strip() in ("Herr", "Frau") else None
    )


_GS_PREFIX_RE = re.compile(r"^(MR|MRS|MS)\.?\s+", re.IGNORECASE)


def clean_gesellschafter_name(name: Optional[str]) -> Optional[str]:
    """Strip MR/MRS/MS prefix, then title-case. Preserves DR. prefix."""
    if not name or not name.strip():
        return name
    cleaned = _GS_PREFIX_RE.sub("", name.strip())
    if not cleaned:
        return name
    # Preserve "DR." or "Dr." prefix
    dr_match = re.match(r"^(DR\.?\s+)", cleaned, re.IGNORECASE)
    if dr_match:
        prefix = "Dr. "
        rest = cleaned[dr_match.end() :]
        return prefix + title_case_german(rest)
    return title_case_german(cleaned)


def enrich_owner_name(
    owner_name: Optional[str], gesellschafter_name: Optional[str]
) -> Optional[str]:
    """If owner_name is last-name-only, enrich from gesellschafter_name (cleaned).

    Pattern: owner_name="Mueller", gesellschafter_name="Klaus Mueller" -> "Klaus Mueller"
    """
    if not owner_name or not gesellschafter_name:
        return owner_name
    parts = owner_name.strip().split()
    if len(parts) != 1:
        return owner_name  # already has first + last
    last_name = parts[0].lower()
    # Clean gesellschafter_name first (strip MR/MRS prefix)
    cleaned_gs = _GS_PREFIX_RE.sub("", gesellschafter_name.strip())
    if not cleaned_gs:
        return owner_name
    gs_parts = cleaned_gs.strip().split()
    if len(gs_parts) < 2:
        return owner_name
    # Check if last token of gesellschafter matches owner_name
    if gs_parts[-1].lower() == last_name:
        return cleaned_gs.strip()
    return owner_name


def build_salutation(anrede: Optional[str], owner_name: Optional[str]) -> Optional[str]:
    """Build 'Sehr geehrter Herr Mueller' or 'Sehr geehrte Frau Schmidt'.

    Returns None if anrede or owner_name is missing.
    """
    if not anrede or not owner_name or anrede not in ("Herr", "Frau"):
        return None
    last_name = owner_name.strip().split()[-1]
    suffix = "r" if anrede == "Herr" else ""
    return f"Sehr geehrte{suffix} {anrede} {last_name}"


def normalize_plz_ort(plz_ort: Optional[str]) -> Optional[str]:
    """Title-case the city portion of PLZ+Ort. '12345 BERLIN' -> '12345 Berlin'."""
    if not plz_ort or not plz_ort.strip():
        return plz_ort
    parts = plz_ort.strip().split(None, 1)
    if len(parts) < 2:
        return plz_ort  # just PLZ, no city
    plz = parts[0]
    city = title_case_german(parts[1])
    return f"{plz} {city}"


def _is_all_caps(text: Optional[str]) -> bool:
    """Check if text is ALL CAPS (ignoring non-alpha characters)."""
    if not text:
        return False
    alpha = "".join(c for c in text if c.isalpha())
    return bool(alpha) and alpha == alpha.upper()


def _is_salutation_broken(salutation: Optional[str]) -> bool:
    """Check if salutation is incomplete (prefix without proper name)."""
    if not salutation:
        return True
    s = salutation.strip()
    # A proper salutation should be "Sehr geehrter Herr X" or "Sehr geehrte Frau X"
    if s in (
        "Sehr geehrter",
        "Sehr geehrte",
        "Sehr geehrter Herr",
        "Sehr geehrte Frau",
    ):
        return True
    if re.match(r"^Sehr geehrte[r]?\s+(Herr|Frau)\s+\S+", s):
        return False  # proper salutation
    return True


def _lookup_region_claude(city: str) -> Optional[tuple[str, str]]:
    """Use Claude CLI to determine region + preposition for a city not in the lookup.

    Returns (region, region_prep) e.g. ("Schleswig-Holstein", "in Schleswig-Holstein")
    or None on failure.
    """
    import json as _json
    import os
    import subprocess

    prompt = (
        f"Für den deutschen Ort '{city}': In welcher Region liegt dieser Ort? "
        f"Antworte NUR mit JSON: "
        f'{{"region": "Regionname", "region_prep": "Präposition + Region"}}\n'
        f"Beispiele:\n"
        f'  Hamburg → {{"region": "Hamburg", "region_prep": "in Hamburg"}}\n'
        f'  Stockelsdorf → {{"region": "Ostholstein", "region_prep": "in Ostholstein"}}\n'
        f'  Estenfeld → {{"region": "Unterfranken", "region_prep": "in Unterfranken"}}\n'
        f"Verwende die Marketing-Region (z.B. 'im Allgäu', 'am Niederrhein'), "
        f"nicht das Bundesland, wenn es eine geläufigere Bezeichnung gibt."
    )
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        result = subprocess.run(
            [settings.CLAUDE_CMD, "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
            encoding="utf-8",
            env=env,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not l.startswith("```")).strip()
        data = _json.loads(text)
        region = data.get("region", "").strip()
        region_prep = data.get("region_prep", "").strip()
        if region and region_prep:
            return region, region_prep
    except Exception as e:
        logger.warning("Claude region lookup failed for %s: %s", city, e)
    return None


def normalize_cmd(args) -> None:
    """CLI handler for 'python pipeline.py normalize'."""
    dry_run = getattr(args, "dry_run", False)
    verbose = getattr(args, "verbose", False)

    pipeline_db.ensure_schema(settings.PIPELINE_DB_PATH)

    # Build city umlaut lookup
    city_lookup = build_city_umlaut_lookup()
    logger.info("City umlaut lookup: %d entries", len(city_lookup))

    # Load A/B records (exclude serienbriefe source)
    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        rows = conn.execute(
            """SELECT domain, full_name, city, street, plz_ort,
                      gesellschafter_name, anrede, owner_name, salutation, source,
                      region, region_prep, gf_name
               FROM company_records
               WHERE prio = 'Prio 1' AND source != 'serienbriefe'"""
        ).fetchall()

    pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "BEFORE normalize")

    # Load existing region mapping for Claude fallback
    region_mapping = load_region_mapping()

    changes: dict[str, int] = {
        "full_name": 0,
        "city": 0,
        "street": 0,
        "plz_ort": 0,
        "gesellschafter_name": 0,
        "anrede": 0,
        "owner_name": 0,
        "salutation": 0,
        "region": 0,
        "region_prep": 0,
    }
    updates: list[dict] = []
    legal_entities: list[dict] = []

    from src.pipeline.enrich import _derive_anrede, _is_natural_person_name

    for row in rows:
        domain = row["domain"]
        rec = dict(row)
        changed = {}

        # 1. Title-case full_name + name umlaut restoration
        if rec["full_name"]:
            new_val = rec["full_name"]
            if _is_all_caps(new_val):
                new_val = title_case_german(new_val)
            new_val = restore_umlauts_name(new_val)
            if new_val != rec["full_name"]:
                changed["full_name"] = new_val
                rec["full_name"] = new_val

        # 2. City: umlaut restoration + title-case
        if rec["city"] and _is_all_caps(rec["city"]):
            new_val = restore_umlauts_city(rec["city"], city_lookup)
            if _is_all_caps(new_val):
                new_val = title_case_german(new_val)
            if new_val != rec["city"]:
                changed["city"] = new_val
                rec["city"] = new_val

        # 3. Street: title-case + umlaut patterns
        if rec["street"] and _is_all_caps(rec["street"]):
            new_val = title_case_german(rec["street"])
            new_val = restore_umlauts_pattern(new_val)
            if new_val != rec["street"]:
                changed["street"] = new_val
                rec["street"] = new_val

        # 4. PLZ+Ort
        if rec["plz_ort"] and _is_all_caps(
            rec["plz_ort"].split(None, 1)[-1] if " " in (rec["plz_ort"] or "") else ""
        ):
            new_val = normalize_plz_ort(rec["plz_ort"])
            if new_val != rec["plz_ort"]:
                changed["plz_ort"] = new_val
                rec["plz_ort"] = new_val

        # 5. Gesellschafter cleanup (strip MR/MRS, title-case)
        if rec["gesellschafter_name"] and _GS_PREFIX_RE.search(
            rec["gesellschafter_name"]
        ):
            new_val = clean_gesellschafter_name(rec["gesellschafter_name"])
            if new_val != rec["gesellschafter_name"]:
                changed["gesellschafter_name"] = new_val
                rec["gesellschafter_name"] = new_val
        elif rec["gesellschafter_name"] and _is_all_caps(rec["gesellschafter_name"]):
            new_val = clean_gesellschafter_name(rec["gesellschafter_name"])
            if new_val != rec["gesellschafter_name"]:
                changed["gesellschafter_name"] = new_val
                rec["gesellschafter_name"] = new_val

        # 6. Anrede normalization (MR→Herr) + derivation from first name if missing
        if rec["anrede"] and rec["anrede"].strip().upper() in _ANREDE_MAP:
            new_val = normalize_anrede(rec["anrede"])
            if new_val and new_val != rec["anrede"]:
                changed["anrede"] = new_val
                rec["anrede"] = new_val
        elif (not rec["anrede"] or rec["anrede"] not in ("Herr", "Frau")) and rec[
            "owner_name"
        ]:
            # Derive anrede from first name using gender heuristic
            owner_parts = rec["owner_name"].strip().split()
            if len(owner_parts) >= 2 and _is_natural_person_name(rec["owner_name"]):
                derived = _derive_anrede(owner_parts[0])
                if derived and derived != rec["anrede"]:
                    changed["anrede"] = derived
                    rec["anrede"] = derived

        # 6b. gf_name fallback: only for last-name-only case (owner = surname,
        #     gf_name has matching full name). Missing/corporate owner_name
        #     requires manual investigation — flag but don't auto-replace.
        gf = rec.get("gf_name") or ""
        owner = rec["owner_name"] or ""
        owner_is_corporate = bool(
            owner and (_LEGAL_ENTITY_RE.search(owner) or "verwaltung" in owner.lower())
        )
        owner_is_missing = not owner.strip()
        # Last-name-only: single word, and gf_name shares the same last name
        owner_is_lastname_only = (
            bool(owner.strip())
            and len(owner.strip().split()) == 1
            and gf.strip()
            and gf.strip().split()[-1].lower() == owner.strip().lower()
        )

        # Flag missing/corporate for manual review (don't auto-replace)
        if gf.strip() and (owner_is_missing or owner_is_corporate):
            if verbose:
                reason = "corporate" if owner_is_corporate else "missing"
                logger.info(
                    "  %s: owner_name %s, gf_name=%r → needs manual review",
                    domain,
                    reason,
                    gf.strip(),
                )
            # Still derive anrede from gf_name even without owner_name
            if not rec["anrede"] or rec["anrede"] not in ("Herr", "Frau"):
                gf_parts = gf.strip().split()
                if len(gf_parts) >= 2 and _is_natural_person_name(gf.strip()):
                    first_gf = gf_parts[0]
                    if (
                        first_gf.lower().rstrip(".") in ("dr", "prof")
                        and len(gf_parts) >= 3
                    ):
                        first_gf = gf_parts[1]
                    derived = _derive_anrede(first_gf)
                    if derived and derived != rec["anrede"]:
                        changed["anrede"] = derived
                        rec["anrede"] = derived

        # Auto-replace only for last-name-only match
        if gf.strip() and owner_is_lastname_only:
            new_owner = gf.strip()
            if new_owner != rec["owner_name"]:
                changed["owner_name"] = new_owner
                rec["owner_name"] = new_owner
                if verbose:
                    logger.info(
                        "  %s: owner_name last-name-only → gf fallback %r",
                        domain,
                        new_owner,
                    )
            # Derive anrede from gf_name's first name
            gf_parts = new_owner.split()
            if len(gf_parts) >= 2 and _is_natural_person_name(new_owner):
                derived = _derive_anrede(gf_parts[0])
                if derived and derived != rec["anrede"]:
                    changed["anrede"] = derived
                    rec["anrede"] = derived

        # 6c. gesellschafter_name fallback for anrede + owner_name
        if (not rec["anrede"] or rec["anrede"] not in ("Herr", "Frau")) and rec.get(
            "gesellschafter_name"
        ):
            ges = rec["gesellschafter_name"].strip()
            if _is_natural_person_name(ges) and not _LEGAL_ENTITY_RE.search(ges):
                ges_parts = ges.split()
                if len(ges_parts) >= 2:
                    first = ges_parts[0]
                    if (
                        first.lower() in ("dr.", "prof.", "dr", "prof")
                        and len(ges_parts) >= 3
                    ):
                        first = ges_parts[1]
                    derived = _derive_anrede(first)
                    if derived:
                        changed["anrede"] = derived
                        rec["anrede"] = derived
                        if not rec["owner_name"]:
                            changed["owner_name"] = ges
                            rec["owner_name"] = ges

        # 6d. Fill owner_name from gesellschafter_name when still empty, regardless of
        #     whether anrede is already set (step 6c only runs when anrede is missing).
        #     Priority: owner_name > gesellschafter_name — never overwrite existing owner_name.
        if not rec.get("owner_name") and rec.get("gesellschafter_name"):
            ges = rec["gesellschafter_name"].strip()
            if _is_natural_person_name(ges) and not _LEGAL_ENTITY_RE.search(ges):
                ges_parts = ges.split()
                if len(ges_parts) >= 2:
                    changed["owner_name"] = ges
                    rec["owner_name"] = ges

        # 6e. gf_name → owner_name fallback when gesellschafter is corporate/missing
        #     and owner_name is still empty. Subsidiary case: the GF is the right
        #     letter addressee when there is no natural-person shareholder.
        if not rec.get("owner_name") and rec.get("gf_name"):
            gf = rec["gf_name"].strip()
            ges = (rec.get("gesellschafter_name") or "").strip()
            ges_is_corporate = bool(ges and _LEGAL_ENTITY_RE.search(ges)) or not ges
            if (
                ges_is_corporate
                and _is_natural_person_name(gf)
                and len(gf.split()) >= 2
            ):
                changed["owner_name"] = gf
                rec["owner_name"] = gf

        # 7. owner_name enrichment (single word -> pull from gesellschafter)
        if rec["owner_name"]:
            new_val = enrich_owner_name(rec["owner_name"], rec["gesellschafter_name"])
            if new_val != rec["owner_name"]:
                changed["owner_name"] = new_val
                rec["owner_name"] = new_val

        # 8. owner_name title-case + name umlaut restoration
        if rec["owner_name"]:
            new_val = rec["owner_name"]
            if _is_all_caps(new_val):
                new_val = title_case_german(new_val)
            new_val = restore_umlauts_name(new_val)
            if new_val != rec["owner_name"]:
                changed["owner_name"] = new_val
                rec["owner_name"] = new_val

        # 8b. plz_ort name umlaut restoration (city part)
        if rec["plz_ort"]:
            new_val = restore_umlauts_name(rec["plz_ort"])
            if new_val != rec["plz_ort"]:
                changed["plz_ort"] = new_val
                rec["plz_ort"] = new_val

        # 8c. Region fill — lookup from mapping, fall back to Claude CLI
        # Extract city from plz_ort if city field is empty
        city_for_region = (rec["city"] or "").strip()
        if not city_for_region and rec["plz_ort"]:
            parts = rec["plz_ort"].strip().split(None, 1)
            if len(parts) == 2:
                city_for_region = parts[1].strip()

        if not rec.get("region_prep") and city_for_region and not dry_run:
            city_lower = city_for_region.lower()
            entry = region_mapping.get(city_lower)
            if not entry and "-" in city_lower:
                entry = region_mapping.get(city_lower.split("-")[0])
            if entry:
                changed["region"] = entry[0]
                changed["region_prep"] = entry[1]
                rec["region_prep"] = entry[1]
            else:
                claude_result = _lookup_region_claude(city_for_region)
                if claude_result:
                    changed["region"] = claude_result[0]
                    changed["region_prep"] = claude_result[1]
                    rec["region_prep"] = claude_result[1]
                    logger.info(
                        "  Claude region for %s: %s",
                        city_for_region,
                        claude_result[1],
                    )

        # 9. Salutation rebuild (prefer owner_name, fall back to gf_name)
        _owner_for_sal = (
            rec["owner_name"]
            if (rec["owner_name"] and not owner_is_corporate)
            else None
        )
        name_for_salutation = (
            _owner_for_sal or (rec.get("gf_name") or "").strip() or None
        )
        if (
            (_is_salutation_broken(rec["salutation"]) or changed.get("owner_name"))
            and rec["anrede"]
            and name_for_salutation
        ):
            new_val = build_salutation(rec["anrede"], name_for_salutation)
            if new_val and new_val != rec["salutation"]:
                changed["salutation"] = new_val

        if changed:
            for field in changed:
                changes[field] += 1
            updates.append({"domain": domain, **changed})
            if verbose:
                logger.info("  %s: %s", domain, changed)

        # Track legal entity gesellschafter (word-boundary match to avoid
        # false positives like "Wagner" matching "ag", "Spiegelberg" matching "kg")
        gs = rec["gesellschafter_name"] or ""
        if _LEGAL_ENTITY_RE.search(gs):
            legal_entities.append(
                {
                    "domain": domain,
                    "full_name": rec["full_name"],
                    "gesellschafter_name": gs,
                }
            )

    # ── Step 9a: Fill street/plz_ort from impressum text ──
    # First ensure all BA records have scraped_text + KB impressum doc
    # (records entering via serienbriefe/dashboard skip the normal scrape step)
    from src.pipeline.scrape import ensure_scrape_for_briefaktion

    ensure_scrape_for_briefaktion()

    # Fallback chain: KB impressum doc → impressum_address column → scraped_text
    imp_fills = {"street": 0, "plz_ort": 0}
    imp_updates: list[dict] = []

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        missing_addr = conn.execute(
            """SELECT domain, impressum_address, scraped_text FROM company_records
               WHERE prio = 'Prio 1' AND source != 'serienbriefe'
                 AND (street IS NULL OR street = '' OR plz_ort IS NULL OR plz_ort = '')"""
        ).fetchall()
    missing_records = {r["domain"]: dict(r) for r in missing_addr}

    if missing_records:
        import sqlite3 as _sqlite3

        kb_path = settings.PIPELINE_DB_PATH.parent / "knowledge_base.db"
        kb_conn = None
        if kb_path.exists():
            kb_conn = _sqlite3.connect(str(kb_path))
            kb_conn.row_factory = _sqlite3.Row

        for d, rec_data in missing_records.items():
            street, plz_ort = None, None

            # Source 1: KB impressum doc
            if kb_conn is not None:
                imp_row = kb_conn.execute(
                    "SELECT content FROM documents WHERE domain = ? AND doc_type = 'impressum'",
                    (d,),
                ).fetchone()
                if imp_row and imp_row["content"]:
                    street, plz_ort = parse_impressum_address(imp_row["content"])

            # Source 2: impressum_address column (already extracted, just needs parsing)
            if (not street or not plz_ort) and rec_data.get("impressum_address"):
                s2, p2 = parse_impressum_address(rec_data["impressum_address"])
                if not street and s2:
                    street = s2
                if not plz_ort and p2:
                    plz_ort = p2

            # Source 3: scraped_text (full homepage text, may contain impressum section)
            if (not street or not plz_ort) and rec_data.get("scraped_text"):
                s3, p3 = parse_impressum_address(rec_data["scraped_text"])
                if not street and s3:
                    street = s3
                if not plz_ort and p3:
                    plz_ort = p3

            imp_changed: dict[str, str] = {}
            already_has_street = any(
                u.get("domain") == d and "street" in u for u in updates
            )
            already_has_plz = any(
                u.get("domain") == d and "plz_ort" in u for u in updates
            )
            if street and not already_has_street:
                imp_changed["street"] = street
                imp_fills["street"] += 1
            if plz_ort and not already_has_plz:
                imp_changed["plz_ort"] = plz_ort
                imp_fills["plz_ort"] += 1
            if imp_changed:
                imp_updates.append({"domain": d, **imp_changed})
                if verbose:
                    logger.info("  %s: impressum address → %s", d, imp_changed)

        if kb_conn is not None:
            kb_conn.close()

    if sum(imp_fills.values()):
        print("\n  Impressum address fills:")
        for field, count in imp_fills.items():
            if count:
                print(f"    {field:25s}  {count:>5} fills")

    if not dry_run and imp_updates:
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            for upd in imp_updates:
                domain = upd.pop("domain")
                # Only fill empty fields (COALESCE semantics)
                set_clauses = ", ".join(
                    f"{k} = CASE WHEN ({k} IS NULL OR {k} = '') THEN ? ELSE {k} END"
                    for k in upd
                )
                values = list(upd.values()) + [domain]
                conn.execute(
                    f"UPDATE company_records SET {set_clauses} WHERE domain = ?",
                    values,
                )
        print(f"    Written: {len(imp_updates)} records updated")

    # ── Step 9b: Umlaut restoration + compliment fixes for AI-generated text ──
    ai_text_changes = {"compliment_draft": 0, "compliment_2": 0, "mehrwerte": 0}
    ai_updates: list[dict] = []

    with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
        ai_rows = conn.execute(
            """SELECT domain, compliment_draft, compliment_2, mehrwerte
               FROM company_records
               WHERE prio = 'Prio 1' AND source != 'serienbriefe'"""
        ).fetchall()

    for row in ai_rows:
        domain = row["domain"]
        ai_changed: dict[str, str] = {}

        # Umlaut restoration on all three fields
        for field in ("compliment_draft", "compliment_2", "mehrwerte"):
            val = row[field]
            if val and val.strip():
                new_val = restore_umlauts_german(val)
                if new_val != val:
                    ai_changed[field] = new_val

        # Compliment grammar fixes (after umlaut restoration)
        k1 = ai_changed.get("compliment_draft", row["compliment_draft"])
        k2 = ai_changed.get("compliment_2", row["compliment_2"])
        fixed_k1, fixed_k2 = fix_compliment_text(k1, k2)
        if fixed_k1 and fixed_k1 != (
            ai_changed.get("compliment_draft") or row["compliment_draft"]
        ):
            ai_changed["compliment_draft"] = fixed_k1
        if fixed_k2 and fixed_k2 != (
            ai_changed.get("compliment_2") or row["compliment_2"]
        ):
            ai_changed["compliment_2"] = fixed_k2

        if ai_changed:
            for field in ai_changed:
                ai_text_changes[field] += 1
            ai_updates.append({"domain": domain, **ai_changed})

    # Print AI text fix summary
    ai_total = sum(ai_text_changes.values())
    if ai_total:
        print("\n  AI text fixes (umlauts + compliment grammar):")
        for field, count in ai_text_changes.items():
            if count:
                print(f"    {field:25s}  {count:>5} fixes")

    if not dry_run and ai_updates:
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            for upd in ai_updates:
                domain = upd.pop("domain")
                set_clauses = ", ".join(f"{k} = ?" for k in upd)
                values = list(upd.values()) + [domain]
                conn.execute(
                    f"UPDATE company_records SET {set_clauses} WHERE domain = ?",
                    values,
                )
        print(f"    Written: {len(ai_updates)} records updated")

    # Print summary
    print(f"\nNormalize — {len(rows)} A/B records checked (excl. serienbriefe)")
    print("-" * 60)
    for field, count in changes.items():
        if count:
            print(f"  {field:25s}  {count:>5} changes")
    print(
        f"  {'TOTAL':25s}  {sum(changes.values()):>5} field changes across {len(updates)} records"
    )
    if legal_entities:
        print(
            f"\n  Legal entity gesellschafter: {len(legal_entities)} records (review needed)"
        )

    if dry_run:
        print("\n  DRY RUN — no changes written")
    else:
        # Write changes to DB
        with pipeline_db.get_connection(settings.PIPELINE_DB_PATH) as conn:
            for upd in updates:
                domain = upd.pop("domain")
                set_clauses = ", ".join(f"{k} = ?" for k in upd)
                values = list(upd.values()) + [domain]
                conn.execute(
                    f"UPDATE company_records SET {set_clauses} WHERE domain = ?",
                    values,
                )
        print(f"\n  Written: {len(updates)} records updated")

    # Generate legal entity review report
    if legal_entities:
        today = datetime.now().strftime("%Y%m%d")
        report_path = settings.DATA_OUTPUT_DIR / f"legal_entity_review_{today}.txt"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(
                f"Legal Entity Gesellschafter Review — {len(legal_entities)} records\n"
            )
            f.write("=" * 70 + "\n\n")
            for le in legal_entities:
                f.write(f"Domain:          {le['domain']}\n")
                f.write(f"Company:         {le['full_name']}\n")
                f.write(f"Gesellschafter:  {le['gesellschafter_name']}\n")
                f.write("-" * 40 + "\n")
        print(f"  Legal entity report: {report_path}")

    if not dry_run:
        pipeline_db.print_fill_rates(settings.PIPELINE_DB_PATH, "AFTER normalize")
    print("-" * 60)
