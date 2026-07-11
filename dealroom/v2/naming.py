"""DEALROOM v2 — filename convention parsing + artifact classification.

Convention (spec §5): YYMMDD_{Codename}_..._vN.ext
Non-numeric version markers (vS = versandt, vP = print, vFC, vWIP) are real
document states but not numeric versions — version stays NULL for those.
"""

import re

VERSION_RE = re.compile(r"_v(\d+)(?:[._]|$)", re.IGNORECASE)
DATE_PREFIX_RE = re.compile(r"^(\d{6})[_ ]")

SKIP_DIRS = {"_old", "_archive", "archive"}
SKIP_FILE_MARKERS = (".bak", "~$", ".tmp", ".lnk", "_backup_", "_backup.", "backup_20")

# filename markers → artifact_type (checked in order, first hit wins)
NAME_RULES = [
    (("databook",), "databook"),
    (("fragenliste", "datenanfrage", "rfi"), "rfi"),
    (("kaufabsichtserkl", "loi"), "loi"),
    (("vertraulichkeit", "nda"), "nda"),
    (("_spa_", "_spa.", "kaufvertrag"), "spa"),  # bare 'spa' hits Vertriebspartner etc.
    (("angebots-update", "indikatives angebot", "angebot", "nbo", "offer"), "nbo"),
    (("cdd", "chancen_risiken", "dd structure", "dd_v", " dd_"), "slides"),
    (("bewertung", "model", "susa"), "model"),
    (
        ("briefing", "workshop_prep", "slides_plan", "protokoll", "intern"),
        "repuro_internal",
    ),
]

# folder → artifact_type fallback (matched on any path segment prefix)
FOLDER_RULES = [
    ("0_vertr", "meeting"),
    ("0_meetings", "meeting"),
    ("1_unternehmens", "commercial_raw"),
    ("1_financials", "financials_raw"),
    ("2_model", "model"),
    ("3_indikatives", "nbo"),
    ("3_offer", "nbo"),
    ("4_loi", "loi"),
    ("4_nda", "nda"),
    ("5_dd", "dataroom_file"),
    ("6_spa", "spa"),
]

SLIDE_EXT = {".pptx", ".pdf", ".key"}


def parse_version(name: str):
    m = VERSION_RE.search(name)
    return int(m.group(1)) if m else None


def parse_file_date(name: str):
    m = DATE_PREFIX_RE.match(name)
    if not m:
        return None
    yy, mm, dd = m.group(1)[0:2], m.group(1)[2:4], m.group(1)[4:6]
    if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
        return None
    return f"20{yy}-{mm}-{dd}"


def artifact_stem(name: str):
    stem = name.rsplit(".", 1)[0].lower()
    stem = DATE_PREFIX_RE.sub("", stem)
    stem = VERSION_RE.sub("", stem)
    return stem.strip(" _-")


def skip_file(name: str) -> bool:
    low = name.lower()
    return any(m in low for m in SKIP_FILE_MARKERS)


def classify(file_name: str, rel_path: str = "") -> str:
    """artifact_type from filename markers, then folder fallback."""
    low = file_name.lower()
    ext = "." + low.rsplit(".", 1)[-1] if "." in low else ""
    for markers, atype in NAME_RULES:
        if any(m in low for m in markers):
            # decks named *_CDD_* are slides only when they are deck formats
            if atype == "slides" and ext not in SLIDE_EXT:
                continue
            return atype
    rel_low = rel_path.lower()
    for prefix, atype in FOLDER_RULES:
        if any(seg.startswith(prefix) for seg in rel_low.split("/")):
            return atype
    return "other"
