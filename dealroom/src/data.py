"""
DR-M3: Data Extraction.

extract_deal(conn, code_name) reads registered financial xlsx documents
(GuV, Bilanz, BWA) and extracts P&L + balance-sheet data into deal_financials.
Rule-based parsing of DATEV/HGB format — no external API calls.
Idempotent: re-running re-extracts and replaces rows from the same source file.

All monetary values stored in EUR_K (value_k). Raw EUR preserved in value_raw.
Gesamtleistung and Umsatzerlöse stored as separate line_items.
DATEV account codes (konto_nr) preserved when present.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl

from src.ingest import extract_year

# ─── Constants ────────────────────────────────────────────────────────────────

CONFLICT_THRESHOLD = 0.01  # 1% relative difference triggers a conflict

# ─── Label patterns for DATEV/HGB P&L ─────────────────────────────────────────
# Maps German P&L labels (lowercased substring) → deal_financials line_item.
# Checked in order — first match wins. More specific patterns first.

PNL_LABEL_MAP = [
    # Gesamtleistung — MUST be before Umsatzerlöse (first match wins)
    (["gesamtleistung"], "gesamtleistung"),
    # Revenue (DATEV "1000 Umsatzerlöse")
    (["umsatzerlöse", "umsatzerloese", "umsatzerl"], "revenue"),
    # Other operating income
    (
        [
            "sonstige betriebliche erträge",
            "sonstige betriebliche ertr",
            "sonstige betriebl. ertr",
        ],
        "other_income",
    ),
    # COGS / Material
    (["materialaufwand", "wareneinsatz", "wareneinkauf"], "cogs"),
    # Personnel — match the subtotal, not sublines
    (["personalaufwand", "personalkosten"], "personnel"),
    # D&A
    (["abschreibungen"], "da"),
    # Other operating expenses
    (["sonstige betriebliche aufwendungen", "sonstige betriebl. aufw"], "other_opex"),
    # Interest expense
    (
        [
            "zinsen und ähnliche aufwendungen",
            "zinsen und aehnliche aufwendungen",
            "zinsaufwand",
            "zinsaufwendungen",
        ],
        "interest_expense",
    ),
    # Interest income
    (
        [
            "zinsen und ähnliche erträge",
            "zinserträge",
            "zinsertr",
            "sonstige zinsen und ähnliche ertr",
        ],
        "interest_income",
    ),
    # Tax
    (
        [
            "steuern vom einkommen und vom ertrag",
            "steuern vom einkommen",
            "ertragsteuer",
            "gewerbesteuer",
        ],
        "tax",
    ),
    # Net income — match the final result line
    (
        [
            "jahresüberschuss",
            "jahresueberschuss",
            "jahresfehlbetrag",
            "ergebnis nach steuern",
        ],
        "net_income",
    ),
    # EBT (less common as explicit line in DATEV)
    (["ergebnis der gewöhnlichen geschäftstätigkeit", "ergebnis vor steuern"], "ebt"),
]

BALANCE_LABEL_MAP = [
    (["bilanzsumme", "summe aktiva", "summe passiva"], "total_assets"),
    (["anlagevermögen", "anlagevermoegen"], "fixed_assets"),
    (["umlaufvermögen", "umlaufvermoegen"], "current_assets"),
    (
        [
            "kassenbestand",
            "guthaben bei kreditinstituten",
            "kassenbestand, bundesbankguthaben",
        ],
        "cash",
    ),
    (
        ["forderungen aus lieferungen und leistungen", "forderungen aus lieferungen"],
        "receivables",
    ),
    (["eigenkapital"], "equity"),
    (
        [
            "verbindlichkeiten gegenüber kreditinstituten",
            "verbindlichkeiten gegenueber kreditinstituten",
        ],
        "debt_lt",
    ),
    (
        [
            "verbindlichkeiten aus lieferungen und leistungen",
            "verbindlichkeiten aus lieferungen",
        ],
        "debt_st",
    ),
]

BWA_LABEL_MAP = [
    (["gesamtleistung"], "gesamtleistung"),
    (["umsatzerlöse", "umsatzerloese", "umsatzerl"], "revenue"),
    (["personalaufwand", "personalkosten"], "personnel"),
    (["vorläufiges ergebnis", "betriebsergebnis"], "ebit"),
]


# ─── German number parsing ─────────────────────────────────────────────────────


def _parse_german_number(s: str) -> float | None:
    """Parse German-formatted numbers: '4.240.640,96' → 4240640.96"""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s or s == "0,00" or s == "0":
        return 0.0
    # Remove thousand separators (dots) and replace decimal comma
    cleaned = s.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


# ─── Excel row reader ─────────────────────────────────────────────────────────


def _load_excel_rows(path: Path) -> list[tuple]:
    """Load first sheet of Excel file, return list of row tuples (raw values)."""
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Cannot open {path.name}: {e}") from e

    ws = wb.worksheets[0]
    rows = []
    for row in ws.iter_rows(values_only=True):
        if any(c is not None for c in row):
            rows.append(tuple(row))
    wb.close()
    return rows


def _find_bwa_ytd_column(rows: list[tuple]) -> tuple[int | None, int | None]:
    """
    Detect BWA YTD columns from DATEV BWA header format.

    BWA headers look like: Zeile | Konto | Bezeichnung | Dez/2025 | Dez/2024 |
    Veränderung | % | Jan/2025 - Dez/2025 | Jan/2024 - Dez/2024 | ...

    Returns (ytd_current_col, ytd_prior_col). Either may be None.
    """
    for row in rows[:5]:
        cells = [str(v).strip() if v else "" for v in row]
        ytd_current = None
        ytd_prior = None
        for i, c in enumerate(cells):
            cl = c.lower()
            # YTD range header like "Jan/2025 -\nDez/2025" or "Jan/2025 - Dez/2025"
            if re.search(r"jan/\d{4}\s*-?\s*\n?\s*\w{3}/\d{4}", cl):
                if ytd_current is None:
                    ytd_current = i
                elif ytd_prior is None:
                    ytd_prior = i
        if ytd_current is not None:
            return ytd_current, ytd_prior
    return None, None


def _find_value_columns(
    rows: list[tuple], is_bwa: bool = False
) -> tuple[int | None, int | None]:
    """
    Find the column indices for Geschäftsjahr (current year) and Vorjahr (prior year).

    DATEV GuV format typically has:
    - A header row like: '' | 'EUR' | 'Geschäftsjahr EUR' | 'Vorjahr EUR'
    - Or columns where the first numeric values appear at specific positions.

    For BWA files, looks for YTD range columns (Jan/YYYY - Mon/YYYY) instead.

    Returns (current_col, prior_col). prior_col may be None.
    """
    # BWA-specific: look for YTD range columns first
    if is_bwa:
        ytd_cur, ytd_prior = _find_bwa_ytd_column(rows)
        if ytd_cur is not None:
            return ytd_cur, ytd_prior

    for row in rows[:15]:  # check first 15 rows for header
        cells = [str(v).lower().strip() if v else "" for v in row]
        # Look for "geschäftsjahr" or "EUR" headers
        gy_col = None
        vj_col = None
        for i, c in enumerate(cells):
            if "geschäftsjahr" in c or "geschaeftsjahr" in c:
                gy_col = i
            elif "vorjahr" in c:
                vj_col = i
        if gy_col is not None:
            return gy_col, vj_col

    # Fallback: find the rightmost two numeric columns in the first data row
    # Skip columns 0-1 which are often Zeile/Konto in DATEV files
    start_col = 2 if is_bwa else 0
    for row in rows[3:20]:
        num_cols = []
        for i, v in enumerate(row):
            if i < start_col:
                continue
            if isinstance(v, (int, float)) and v != 0:
                num_cols.append(i)
            # Also detect German-formatted string numbers
            elif isinstance(v, str) and _parse_german_number(v) is not None:
                parsed = _parse_german_number(v)
                if parsed != 0 and abs(parsed) > 10:  # skip small/pct values
                    num_cols.append(i)
        if len(num_cols) >= 2:
            return num_cols[0], num_cols[1]
        if len(num_cols) == 1:
            return num_cols[0], None

    return None, None


def _detect_year_from_rows(rows: list[tuple], file_name: str) -> int | None:
    """Detect fiscal year from file header rows or filename."""
    # Try filename first
    yr = extract_year(file_name)
    if yr:
        return yr
    # Scan first rows for year pattern like "vom 01.01.2022 bis 31.12.2022"
    for row in rows[:5]:
        for v in row:
            if isinstance(v, str):
                m = re.search(r"(?:bis|31\.12\.)\s*(20[1-9]\d)", v)
                if m:
                    return int(m.group(1))
                m = re.search(r"(20[1-9]\d)", v)
                if m:
                    return int(m.group(1))
    return None


def _extract_konto_nr(label: str) -> str | None:
    """Extract leading 4-digit DATEV account code from label, if present."""
    m = re.match(r"^(\d{4})\s+", label.strip())
    return m.group(1) if m else None


def _match_label(label: str, label_map: list) -> str | None:
    """Match a row label against a label map. Returns line_item key or None."""
    label_lower = label.lower().strip()
    if label_lower.startswith("- davon") or label_lower.startswith("davon"):
        return None
    stripped = re.sub(r"^\d{4}\s+", "", label_lower)
    for patterns, key in label_map:
        for pat in patterns:
            if pat in label_lower or pat in stripped:
                return key
    return None


def _get_row_value(row: tuple, col_idx: int) -> float | None:
    """Get numeric value from a specific column. Handles both native numbers
    and German-formatted string numbers ('4.240.640,96')."""
    if col_idx is None or col_idx >= len(row):
        return None
    v = row[col_idx]
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return _parse_german_number(v)
    return None


def _find_subtotal(
    rows: list[tuple], start_idx: int, label_key: str, col_idx: int
) -> float | None:
    """
    For items like Materialaufwand/Personalaufwand that have sub-items (a, b),
    the subtotal is on an unlabeled row with the total in the main value column.

    DATEV pattern:
      3. Materialaufwand          [no value in col_idx]
        a) Aufwendungen für...    [sub-item — skip over]
        b) Aufwendungen für...    [sub-item — skip over]
        [None, None, SUBTOTAL]    ← unlabeled row with value
      4. Personalaufwand          [next section — stop]

    Fallback: if no unlabeled subtotal row exists (e.g. D&A with a single sub-item),
    sum all sub-item values found before the next section header.
    """
    sub_item_sum = 0.0
    sub_item_count = 0

    for offset in range(1, 10):
        idx = start_idx + offset
        if idx >= len(rows):
            break
        row = rows[idx]

        # Check if this is a new numbered section header → stop
        is_new_section = False
        for v in row[:2]:
            if isinstance(v, str) and v.strip():
                lbl = v.strip()
                if re.match(r"^\d+\.\s", lbl):
                    is_new_section = True
                    break
                if re.match(r"^\d{4}\s+\w", lbl):
                    is_new_section = True
                    break
        if is_new_section:
            # No unlabeled subtotal found — return sum of sub-items if any
            return sub_item_sum if sub_item_count > 0 else None

        # Look for unlabeled row or "Summe" row with value in col_idx
        val = _get_row_value(row, col_idx)
        if val is not None and abs(val) > 0:
            has_label = False
            is_summe = False
            for v in row[:2]:
                if isinstance(v, str) and v.strip():
                    cleaned = v.strip().lower()
                    if any(c.isalpha() for c in cleaned) and "eur" not in cleaned:
                        has_label = True
                        # "Summe Eigenkapital", "Summe Anlagevermögen" etc. = explicit subtotal
                        if "summe" in cleaned:
                            is_summe = True
                    break
            if not has_label or is_summe:
                return val  # found the explicit subtotal row
            else:
                # This is a labeled sub-item (a), b), I., II., etc.) with a value — accumulate
                sub_item_sum += val
                sub_item_count += 1

    # Reached end of scan window — return sub-item sum if any
    return sub_item_sum if sub_item_count > 0 else None


# ─── Rule-based extractors ────────────────────────────────────────────────────


def _extract_pnl(path: Path, fiscal_year: int | None) -> dict | None:
    """Extract P&L data from a DATEV/HGB GuV Excel file. Returns dict in EUR."""
    rows = _load_excel_rows(path)
    if not rows:
        return None

    # Sanity-check fiscal_year from deal_documents (may have DATEV regex bug)
    fy = fiscal_year if fiscal_year and 2015 <= fiscal_year <= 2030 else None
    detected_year = fy or _detect_year_from_rows(rows, path.name)
    if not detected_year:
        return None

    gy_col, vj_col = _find_value_columns(rows)
    if gy_col is None:
        return None

    result = {
        "fiscal_year": detected_year,
        "prior_year": detected_year - 1 if vj_col else None,
    }
    prior = {}
    matched_keys = set()

    for i, row in enumerate(rows):
        # Find label in the row
        label = None
        for v in row:
            if isinstance(v, str) and v.strip():
                stripped = v.strip()
                # Skip pure number strings and EUR headers
                if (
                    stripped.replace(".", "")
                    .replace(",", "")
                    .replace("-", "")
                    .isdigit()
                ):
                    continue
                if stripped.lower() in ("eur", "€", "ust"):
                    continue
                label = stripped
                break

        if not label:
            continue

        # Skip detail-only lines (just a 4-digit account code, no label text)
        if re.match(r"^\d{4}$", label.strip()):
            continue

        key = _match_label(label, PNL_LABEL_MAP)
        if not key or key in matched_keys:
            continue

        konto = _extract_konto_nr(label)

        # Get the value — try direct column first
        val = _get_row_value(row, gy_col)

        # For items with sub-items (Materialaufwand, Personalaufwand),
        # if the value is in a sub-column, find the subtotal
        if val is None:
            val = _find_subtotal(rows, i, key, gy_col)

        if val is not None:
            # Store absolute value for cost items
            if key in (
                "cogs",
                "personnel",
                "other_opex",
                "da",
                "interest_expense",
                "tax",
            ):
                val = abs(val)
            result[key] = val
            if konto:
                result[f"konto_nr_{key}"] = konto
            matched_keys.add(key)

        # Prior year
        if vj_col is not None:
            vj_val = _get_row_value(row, vj_col)
            if vj_val is None:
                vj_val = _find_subtotal(rows, i, key, vj_col)
            if vj_val is not None:
                if key in (
                    "cogs",
                    "personnel",
                    "other_opex",
                    "da",
                    "interest_expense",
                    "tax",
                ):
                    vj_val = abs(vj_val)
                prior[key] = vj_val

    if "revenue" not in result and "gesamtleistung" not in result:
        return None

    # Map prior year values
    if prior:
        result["prior_year_revenue"] = prior.get("revenue")
        result["prior_year_gesamtleistung"] = prior.get("gesamtleistung")
        result["prior_year_personnel"] = prior.get("personnel")

    # Compute EBITDA if not directly stated — use gesamtleistung as top line if available
    top_line_key = "gesamtleistung" if "gesamtleistung" in result else "revenue"
    if "ebitda" not in result and top_line_key in result:
        rev = result.get(top_line_key, 0)
        other_inc = result.get("other_income", 0)
        cogs = result.get("cogs", 0)
        pers = result.get("personnel", 0)
        opex = result.get("other_opex", 0)
        da = result.get("da", 0)
        # EBITDA = revenue + other_income - cogs - personnel - other_opex
        ebitda = rev + other_inc - cogs - pers - opex
        result["ebitda"] = ebitda

    # Compute EBIT if not directly stated
    if "ebit" not in result and "ebitda" in result:
        result["ebit"] = result["ebitda"] - result.get("da", 0)

    return result


def _extract_balance(path: Path, fiscal_year: int | None) -> dict | None:
    """Extract balance sheet data from a DATEV/HGB Bilanz Excel file."""
    rows = _load_excel_rows(path)
    if not rows:
        return None

    fy = fiscal_year if fiscal_year and 2015 <= fiscal_year <= 2030 else None
    detected_year = fy or _detect_year_from_rows(rows, path.name)
    if not detected_year:
        return None

    gy_col, _ = _find_value_columns(rows)
    if gy_col is None:
        return None

    result = {"fiscal_year": detected_year}
    matched_keys = set()

    for i, row in enumerate(rows):
        label = None
        for v in row:
            if isinstance(v, str) and v.strip():
                stripped = v.strip()
                if stripped.lower() in ("eur", "€"):
                    continue
                label = stripped
                break
        if not label:
            continue

        key = _match_label(label, BALANCE_LABEL_MAP)
        if not key or key in matched_keys:
            continue

        val = _get_row_value(row, gy_col)
        if val is None:
            val = _find_subtotal(rows, i, key, gy_col)
        if val is not None:
            result[key] = abs(val)
            matched_keys.add(key)

    if len(result) <= 1:  # only fiscal_year
        return None

    # Compute net_debt if we have debt and cash
    if "cash" in result and ("debt_lt" in result or "debt_st" in result):
        total_debt = result.get("debt_lt", 0) + result.get("debt_st", 0)
        result["net_debt"] = total_debt - result["cash"]

    return result


def _extract_bwa(path: Path, fiscal_year: int | None) -> dict | None:
    """Extract BWA data from a BWA Excel file."""
    rows = _load_excel_rows(path)
    if not rows:
        return None

    fy = fiscal_year if fiscal_year and 2015 <= fiscal_year <= 2030 else None
    # For BWA, prefer header-row year detection over filename (avoids DD.MM.YY bugs)
    detected_year = fy or _detect_year_from_rows(rows, path.name)
    # Detect period month from filename (e.g. "BWA 06 2025" → month 6)
    # Validate 1-12 to avoid DD.MM.YY dates like "BWA 31.12.25" → month=31
    m = re.search(r"(?:BWA|bwa)\s*!?\s*-?\s*(\d{1,2})", path.name)
    period_month = int(m.group(1)) if m else None
    if period_month is not None and not (1 <= period_month <= 12):
        period_month = None
    # Also detect month from BWA header row (e.g. "Vorjahresvergleich Dez 2025")
    if period_month is None or detected_year is None:
        _month_map = {
            "jan": 1,
            "feb": 2,
            "mär": 3,
            "mar": 3,
            "apr": 4,
            "mai": 5,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "okt": 10,
            "oct": 10,
            "nov": 11,
            "dez": 12,
            "dec": 12,
        }
        for row in rows[:3]:
            for v in row:
                if isinstance(v, str):
                    hm = re.search(
                        r"(?:vergleich|BWA)[^\d]*(\w{3})\s+(20\d{2})",
                        v,
                        re.IGNORECASE,
                    )
                    if hm:
                        mon_str = hm.group(1).lower()[:3]
                        if mon_str in _month_map:
                            if period_month is None:
                                period_month = _month_map[mon_str]
                            if detected_year is None:
                                detected_year = int(hm.group(2))

    gy_col, _ = _find_value_columns(rows, is_bwa=True)
    if gy_col is None:
        return None

    result = {
        "fiscal_year": detected_year,
        "period_end_month": period_month,
    }
    matched_keys = set()

    for i, row in enumerate(rows):
        label = None
        for v in row:
            if isinstance(v, str) and v.strip():
                stripped = v.strip()
                if stripped.lower() in ("eur", "€"):
                    continue
                label = stripped
                break
        if not label:
            continue

        key = _match_label(label, BWA_LABEL_MAP)
        if not key or key in matched_keys:
            continue

        val = _get_row_value(row, gy_col)
        if val is None:
            val = _find_subtotal(rows, i, key, gy_col)
        if val is not None:
            result[key + "_ytd"] = abs(val) if key == "personnel" else val
            matched_keys.add(key)

    if len(result) <= 2:  # only fiscal_year + period
        return None
    return result


# ─── deal_financials writer ──────────────────────────────────────────────────


def _eur_to_eurk(v: float | None) -> float | None:
    if v is None:
        return None
    return round(v / 1000.0, 2)


def _make_fin_row(
    domain: str,
    statement: str,
    line_item: str,
    fiscal_year: int | None,
    period_type: str,
    value_k: float | None,
    value_raw: float | None,
    source: str,
    source_file_id: str,
    now: str,
    konto_nr: str | None = None,
    is_adjusted: int = 0,
    adjustment_note: str | None = None,
    confidence: str = "stated",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "domain": domain,
        "statement": statement,
        "line_item": line_item,
        "konto_nr": konto_nr,
        "fiscal_year": fiscal_year,
        "period_type": period_type,
        "value_k": value_k,
        "value_raw": value_raw,
        "is_adjusted": is_adjusted,
        "adjustment_note": adjustment_note,
        "source": source,
        "source_file_id": source_file_id,
        "confidence": confidence,
        "is_authoritative": 0,
        "extracted_at": now,
    }


def _pnl_to_entries(
    extracted: dict, domain: str, source: str, source_file_id: str
) -> list[dict]:
    """Convert extracted P&L dict → list of deal_financials row dicts."""
    now = datetime.now(timezone.utc).isoformat()
    fiscal_year = extracted.get("fiscal_year")
    rows = []

    pnl_keys = [
        "gesamtleistung",
        "revenue",
        "cogs",
        "gross_profit",
        "personnel",
        "other_opex",
        "other_income",
        "ebitda",
        "da",
        "ebit",
        "interest_expense",
        "interest_income",
        "ebt",
        "tax",
        "net_income",
    ]
    for key in pnl_keys:
        val_eur = extracted.get(key)
        if val_eur is None:
            continue
        konto = extracted.get(f"konto_nr_{key}")
        rows.append(
            _make_fin_row(
                domain,
                "pnl",
                key,
                fiscal_year,
                "annual",
                _eur_to_eurk(val_eur),
                val_eur,
                source,
                source_file_id,
                now,
                konto_nr=konto,
            )
        )

    # Normalization candidates → adjustments row
    norm = extracted.get("normalization_candidates")
    if norm:
        rows.append(
            _make_fin_row(
                domain,
                "adjustments",
                "normalization_items_json",
                fiscal_year,
                "annual",
                None,
                None,
                source,
                source_file_id,
                now,
                adjustment_note=json.dumps(norm, ensure_ascii=False),
            )
        )

    # Prior year rows
    prior_year = extracted.get("prior_year")
    if prior_year:
        for key, raw_key in [
            ("revenue", "prior_year_revenue"),
            ("gesamtleistung", "prior_year_gesamtleistung"),
            ("ebitda", "prior_year_ebitda"),
            ("personnel", "prior_year_personnel"),
        ]:
            val_eur = extracted.get(raw_key)
            if val_eur is None:
                continue
            rows.append(
                _make_fin_row(
                    domain,
                    "pnl",
                    key,
                    prior_year,
                    "annual",
                    _eur_to_eurk(val_eur),
                    val_eur,
                    source + " [Vorjahr]",
                    source_file_id,
                    now,
                )
            )

    return rows


def _balance_to_entries(
    extracted: dict, domain: str, source: str, source_file_id: str
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    fiscal_year = extracted.get("fiscal_year")
    keys = [
        "total_assets",
        "fixed_assets",
        "current_assets",
        "cash",
        "receivables",
        "equity",
        "debt_lt",
        "debt_st",
        "net_debt",
    ]
    rows = []
    for key in keys:
        val_eur = extracted.get(key)
        if val_eur is None:
            continue
        rows.append(
            _make_fin_row(
                domain,
                "balance",
                key,
                fiscal_year,
                "annual",
                _eur_to_eurk(val_eur),
                val_eur,
                source,
                source_file_id,
                now,
            )
        )
    return rows


def _bwa_to_entries(
    extracted: dict, domain: str, source: str, source_file_id: str
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    fiscal_year = extracted.get("fiscal_year")
    period_month = extracted.get("period_end_month")
    period_label = f"bwa_ytd_m{period_month:02d}" if period_month else "bwa_ytd"
    keys = [
        "gesamtleistung_ytd",
        "revenue_ytd",
        "personnel_ytd",
        "ebitda_ytd",
        "ebit_ytd",
        "net_income_ytd",
    ]
    rows = []
    for key in keys:
        val_eur = extracted.get(key)
        if val_eur is None:
            continue
        rows.append(
            _make_fin_row(
                domain,
                "pnl",
                key.replace("_ytd", ""),
                fiscal_year,
                period_label,
                _eur_to_eurk(val_eur),
                val_eur,
                source,
                source_file_id,
                now,
            )
        )
    return rows


def _write_entries(conn, entries: list[dict], dry_run: bool) -> int:
    if not entries or dry_run:
        return len(entries)
    conn.executemany(
        """INSERT INTO deal_financials
           (id, domain, statement, line_item, konto_nr, fiscal_year, period_type,
            value_k, value_raw, is_adjusted, adjustment_note, source, source_file_id,
            confidence, is_authoritative, extracted_at)
           VALUES
           (:id, :domain, :statement, :line_item, :konto_nr, :fiscal_year, :period_type,
            :value_k, :value_raw, :is_adjusted, :adjustment_note, :source, :source_file_id,
            :confidence, :is_authoritative, :extracted_at)""",
        entries,
    )
    conn.commit()
    return len(entries)


def _clear_source_rows(conn, source_file_id: str) -> int:
    """Delete all deal_financials rows for this source file (idempotent re-extraction)."""
    n = conn.execute(
        "SELECT COUNT(*) FROM deal_financials WHERE source_file_id = ?",
        (source_file_id,),
    ).fetchone()[0]
    conn.execute(
        "DELETE FROM deal_financials WHERE source_file_id = ?", (source_file_id,)
    )
    conn.commit()
    return n


# ─── Conflict detection ───────────────────────────────────────────────────────


def detect_conflicts(conn, domain: str) -> int:
    """Find deal_financials rows with same (statement, line_item, fiscal_year)
    but different value_k (relative diff > 1%). Returns count of conflicts."""
    from collections import defaultdict

    rows = conn.execute(
        """SELECT id, statement, line_item, fiscal_year, value_k
           FROM deal_financials
           WHERE domain = ?
             AND value_k IS NOT NULL
             AND statement != 'adjustments'
           ORDER BY statement, line_item, fiscal_year""",
        (domain,),
    ).fetchall()

    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        gkey = (r["statement"], r["line_item"], r["fiscal_year"])
        groups[gkey].append(r)

    conflict_count = 0
    for gkey, group in groups.items():
        if len(group) < 2:
            continue
        values = [r["value_k"] for r in group]
        max_val = max(abs(v) for v in values)
        if max_val == 0:
            continue
        min_val = min(abs(v) for v in values)
        relative_diff = (max_val - min_val) / max_val
        if relative_diff > CONFLICT_THRESHOLD:
            conflict_count += len(group)
    return conflict_count


# ─── Risk flags ───────────────────────────────────────────────────────────────


def compute_risk_flags(conn, domain: str) -> list[str]:
    """Compute auto risk flags from deal_financials. Returns list of flag descriptions."""
    flags = []

    rows = conn.execute(
        """SELECT fiscal_year, line_item, value_k FROM deal_financials
           WHERE domain = ? AND statement = 'pnl'
             AND period_type = 'annual' AND value_k IS NOT NULL
           ORDER BY fiscal_year, line_item""",
        (domain,),
    ).fetchall()

    data: dict[int, dict[str, float]] = {}
    for r in rows:
        yr = r["fiscal_year"]
        if yr:
            if yr not in data:
                data[yr] = {}
            data[yr][r["line_item"]] = r["value_k"]

    years = sorted(data.keys())

    # Use gesamtleistung for top-line analysis, fall back to revenue
    def _top_line(yr_data: dict) -> float | None:
        return yr_data.get("gesamtleistung") or yr_data.get("revenue")

    for i in range(1, len(years)):
        y0, y1 = years[i - 1], years[i]
        r0 = _top_line(data[y0])
        r1 = _top_line(data[y1])
        if r0 and r1 and r0 > 0 and (r1 - r0) / r0 < -0.05:
            pct = round((r1 - r0) / r0 * 100, 1)
            flags.append(f"Revenue declined {pct}% from {y0} to {y1}")

    for yr in reversed(years):
        rev = _top_line(data[yr])
        ebitda = data[yr].get("ebitda")
        if rev and ebitda and rev > 0:
            margin = ebitda / rev
            if margin < 0.10:
                flags.append(f"EBITDA margin {round(margin * 100, 1)}% in {yr} (< 10%)")
            break

    if len(years) >= 2:
        expected = set(range(min(years), max(years) + 1))
        missing = expected - set(years)
        if missing:
            flags.append(f"Missing fiscal year data: {sorted(missing)}")

    return flags


# ─── Main entry point ─────────────────────────────────────────────────────────


def extract_deal(conn, code_name: str, dry_run: bool = False) -> dict[str, Any]:
    """
    Extract all financial data for a deal. Returns summary dict.

    Steps:
    1. Get domain + registered financial xlsx docs from deal_documents
    2. For each doc: read rows → call Haiku → write to deal_financials
    3. Detect conflicts
    4. Compute risk flags
    """
    deal = conn.execute(
        "SELECT domain, company_name FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if not deal:
        raise ValueError(f"Deal not found: {code_name}")

    domain = deal["domain"] or code_name.lower()
    company = deal["company_name"] or code_name

    # Get extractable docs: guv/bilanz/bwa xlsx (not archive)
    docs = conn.execute(
        """SELECT id, file_path, file_name, doc_type, doc_subtype, fiscal_year
           FROM deal_documents
           WHERE code_name = ?
             AND doc_type = 'financials_raw'
             AND doc_subtype IN ('guv', 'bilanz', 'bwa')
             AND (file_name LIKE '%.xlsx' OR file_name LIKE '%.xlsm')
           ORDER BY doc_subtype, fiscal_year""",
        (code_name,),
    ).fetchall()

    if not docs:
        return {
            "code_name": code_name,
            "files_processed": 0,
            "rows_written": 0,
            "conflicts": 0,
            "flags": [],
            "error": "No extractable financial docs found. Run ingest-docs first.",
        }

    summary = {
        "code_name": code_name,
        "company": company,
        "files_processed": 0,
        "rows_written": 0,
        "conflicts": 0,
        "flags": [],
        "skipped": [],
        "errors": [],
    }

    for doc in docs:
        path = Path(doc["file_path"])
        if not path.exists():
            summary["skipped"].append(f"{doc['file_name']} [file not found]")
            continue

        if dry_run:
            print(
                f"  [dry-run] would extract: {doc['file_name']} ({doc['doc_subtype']})"
            )
            summary["files_processed"] += 1
            continue

        safe_name = doc["file_name"].encode("ascii", "replace").decode("ascii")
        print(
            f"  Extracting {safe_name} ({doc['doc_subtype']}, year={doc['fiscal_year']})..."
        )

        # Clear previous rows for this source (idempotent)
        cleared = _clear_source_rows(conn, doc["id"])
        if cleared:
            print(f"    Cleared {cleared} existing rows for this source")

        extracted = None
        entries = []

        try:
            if doc["doc_subtype"] == "guv":
                extracted = _extract_pnl(path, doc["fiscal_year"])
                if extracted:
                    entries = _pnl_to_entries(
                        extracted, domain, doc["file_name"], doc["id"]
                    )

            elif doc["doc_subtype"] == "bilanz":
                extracted = _extract_balance(path, doc["fiscal_year"])
                if extracted:
                    entries = _balance_to_entries(
                        extracted, domain, doc["file_name"], doc["id"]
                    )

            elif doc["doc_subtype"] == "bwa":
                extracted = _extract_bwa(path, doc["fiscal_year"])
                if extracted:
                    entries = _bwa_to_entries(
                        extracted, domain, doc["file_name"], doc["id"]
                    )
        except ValueError as e:
            summary["errors"].append(str(e))
            continue

        if not extracted:
            summary["errors"].append(
                f"{doc['file_name']}: no data could be extracted (format not recognized or no year detected)"
            )
            continue

        n = _write_entries(conn, entries, dry_run)
        summary["rows_written"] += n
        summary["files_processed"] += 1
        print(f"    -> {n} rows {'(dry-run)' if dry_run else 'written'}")

    if not dry_run:
        summary["conflicts"] = detect_conflicts(conn, domain)
        summary["flags"] = compute_risk_flags(conn, domain)

    return summary
