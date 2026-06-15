import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings


def extract_year(filename: str) -> Optional[int]:
    """Extract fiscal year from filename. Returns None if ambiguous or absent."""
    # Use digit-boundary lookarounds instead of \b — underscore is \w so \b
    # fails on DATEV filenames like "_2024_" (only one of the two years matches).
    years = list(set(re.findall(r"(?<!\d)(20[1-9][0-9])(?!\d)", filename)))
    if len(years) == 1:
        return int(years[0])
    # DATEV-style month.year notation: "12.25" or "9.25" → 2025
    # Require month part is 1-12 (not day-like values like 31) to avoid
    # DD.MM.YY dates like "31.12.25" matching "31.12" → year 2012.
    # Use findall with lookahead to handle overlapping patterns (e.g. "31.12.25"
    # where "31.12" consumes the "12" needed for "12.25").
    if not years:
        for m in re.finditer(r"(?<!\d)(\d{1,2})\.(\d{2})(?!\d)", filename):
            month_part = int(m.group(1))
            year_part = int(m.group(2))
            if 1 <= month_part <= 12 and 20 <= year_part <= 39:
                return 2000 + year_part
        # Handle DD.MM.YY: split on "." and check the last 2-digit segment
        dm = re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2})(?!\d)", filename)
        if dm:
            year_part = int(dm.group(3))
            if 20 <= year_part <= 39:
                return 2000 + year_part
    return None


def classify_file(
    file_path: Path, deal_folder: Path
) -> tuple[str, Optional[str], Optional[int]]:
    """
    Returns (doc_type, doc_subtype, fiscal_year).

    doc_type: 'financials_raw' | 'model' | 'offer' | 'nda' | 'loi' | 'meeting'
              | 'dd' | 'rfi' | 'repuro_internal' | 'other'

    Classification is folder-first, then filename keywords. First match wins.
    """
    try:
        rel = file_path.relative_to(deal_folder)
    except ValueError:
        return "other", None, None

    parts = [p.lower() for p in rel.parts]
    name_lower = file_path.name.lower()
    year = extract_year(file_path.name)

    def _folder_match(keyword: str) -> bool:
        """Match folder by keyword, ignoring numeric prefix (2_Model, 4_Model both match 'model')."""
        return any(keyword in re.sub(r"^\d+_", "", p) for p in parts)

    # Model folder (2_Model, 4_Model, etc.)
    if _folder_match("model"):
        subtype = "archive" if ("_archive" in parts or "_old" in parts) else None
        return "model", subtype, year

    # Indikatives Angebot folder
    if any("angebot" in p for p in parts):
        return "offer", None, year

    # LOI folder
    if _folder_match("loi"):
        subtype = "archive" if ("_old" in parts or "_archive" in parts) else None
        return "loi", subtype, year

    # DD folder
    if _folder_match("dd"):
        return "dd", None, year

    # Repuro documents
    if any("repuro" in p for p in parts) and any(re.match(r"^\d+_", p) for p in parts):
        return "repuro_internal", None, year

    # Verträge und Meetings
    if _folder_match("vertr"):
        if "nda" in parts:
            return "nda", None, year
        if any(kw in name_lower for kw in ("vertraulichkeit", "nda")):
            return "nda", None, year
        return "meeting", None, year

    # Unternehmensinformationen
    if _folder_match("unternehmen"):
        return _classify_financials_raw(name_lower, year)

    # Files at root of deal folder
    if len(parts) == 1:
        return _classify_root_file(name_lower, year)

    return "other", None, year


def _classify_financials_raw(
    name_lower: str, year: Optional[int]
) -> tuple[str, Optional[str], Optional[int]]:
    """Classify files in 1_Unternehmensinformationen/."""
    if any(kw in name_lower for kw in ("rfi", "fragenliste")):
        return "rfi", None, year
    if any(
        kw in name_lower
        for kw in ("g.u.v", "guv", "gewinn", "erfolgsrechnung", "deckungsbeitrag")
    ):
        return "financials_raw", "guv", year
    if "bilanz" in name_lower:
        return "financials_raw", "bilanz", year
    if "bwa" in name_lower:
        return "financials_raw", "bwa", year
    if any(
        kw in name_lower for kw in ("susa", "summen und salden", "summen-und-salden")
    ):
        return "financials_raw", "susa", year
    if any(
        kw in name_lower for kw in ("ja ", "ja_", "jahresabschluss", "testat", "annual")
    ):
        return "financials_raw", "ja", year
    if "saldenliste" in name_lower:
        if "lieferant" in name_lower:
            return "financials_raw", "saldenliste_lieferanten", year
        return "financials_raw", "saldenliste_kunden", year
    if any(
        kw in name_lower
        for kw in (
            "kundenumsatz",
            "kundengruppen",
            "customer",
            "rab nach umsatz",
            "kundenmatrix",
            "umsatzaufteilung",
        )
    ):
        return "commercial_raw", "customer_list", year
    if any(
        kw in name_lower
        for kw in ("artikelgruppen", "warengruppen", "umsätze nach", "rohgewinn")
    ):
        return "commercial_raw", "product_split", year
    if any(
        kw in name_lower
        for kw in ("auftragsübersicht", "auftragsliste", "backlog", "orderbook")
    ):
        return "commercial_raw", "backlog", year
    if any(
        kw in name_lower
        for kw in ("mitarbeiterliste", "personalliste", "ma-liste", "employee")
    ):
        return "commercial_raw", "employee_list", year
    if any(kw in name_lower for kw in ("lieferant", "supplier")):
        return "commercial_raw", "supplier_list", year
    if any(kw in name_lower for kw in ("planung", "plan", "vorschau", "forecast")):
        return "financials_raw", "planning", year
    if any(kw in name_lower for kw in ("analyse", "analysis", "auswertung")):
        return "financials_raw", "analysis", year
    if "expos" in name_lower:
        return "financials_raw", "expose", year
    return "financials_raw", None, year


def _classify_root_file(
    name_lower: str, year: Optional[int]
) -> tuple[str, Optional[str], Optional[int]]:
    """Classify files at the root of the deal folder (no subfolder)."""
    if any(kw in name_lower for kw in ("rfi", "fragenliste")):
        return "rfi", None, year
    if any(kw in name_lower for kw in ("g.u.v", "guv", "ja ", "ja_", "bilanz", "bwa")):
        return "financials_raw", None, year
    if any(kw in name_lower for kw in ("vertraulichkeit", "nda")):
        return "nda", None, year
    return "other", None, year


_SKIP_PREFIXES = ("~$", ".~")
_SKIP_EXTENSIONS = {".tmp", ".lnk", ".url"}


def scan_deal(code_name: str, conn) -> dict:
    """
    Scan the OneDrive folder for code_name, classify and register all files.

    Returns: {'new': int, 'skipped': int, 'total': int, 'by_type': dict}
    Raises ValueError if deal not in DB. Raises FileNotFoundError if folder missing.
    """
    from src.db import resolve_folder

    row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Deal not found: {code_name}")

    domain = row["domain"] or code_name.lower()
    folder = resolve_folder(code_name)
    if folder is None:
        raise FileNotFoundError(
            f"OneDrive folder for '{code_name}' not found under: {settings.DEALS_DIR}"
        )

    now = datetime.now(timezone.utc).isoformat()
    counts: dict = {"new": 0, "skipped": 0, "total": 0, "by_type": {}}

    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.name.startswith(_SKIP_PREFIXES):
            continue
        if file_path.suffix.lower() in _SKIP_EXTENSIONS:
            continue

        doc_type, doc_subtype, fiscal_year = classify_file(file_path, folder)
        doc_id = hashlib.md5(f"{domain}{file_path}".encode("utf-8")).hexdigest()
        size_kb = int(file_path.stat().st_size / 1024)

        counts["total"] += 1
        counts["by_type"].setdefault(doc_type, {"new": 0, "skipped": 0})

        conn.execute(
            """
            INSERT OR IGNORE INTO deal_documents
            (id, domain, code_name, file_path, doc_type, doc_subtype,
             fiscal_year, file_name, file_size_kb, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                domain,
                code_name,
                str(file_path),
                doc_type,
                doc_subtype,
                fiscal_year,
                file_path.name,
                size_kb,
                now,
            ),
        )
        if conn.execute("SELECT changes()").fetchone()[0] > 0:
            counts["new"] += 1
            counts["by_type"][doc_type]["new"] += 1
        else:
            counts["skipped"] += 1
            counts["by_type"][doc_type]["skipped"] += 1

    conn.commit()
    return counts
