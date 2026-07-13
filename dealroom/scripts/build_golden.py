"""
Build golden dataset from finalized Excel models.

Run once: python scripts/build_golden.py
Output: data/golden/{code_name_lower}.json

Reads the GuV sheet from each deal's latest model file (not in _archive/).
Extracts the clean P&L table rows by label matching.
Values are already in EUR_K in the model.
"""

import json
import re
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from config import settings
from src.db import get_conn

# Row labels in the model GuV sheet → our deal_data keys
LABEL_MAP = {
    "revenue": "revenue",
    "cost of sales (adj.)": "cogs_adj",
    "gross margin": "gross_profit",
    "personnel expenses (adj.)": "personnel_adj",
    "opex (adj.)": "other_opex_adj",
    "opin (adj.)": "other_income_adj",
    "ebitda (adj.)": "ebitda_adj",
    "d&a (adj.)": "da_adj",
    "ebit (adj.)": "ebit_adj",
    "zinsaufwand": "interest_expense",
    "zinserträge": "interest_income",
    "ebt (adj.)": "ebt_adj",
    "steuern": "tax",
    "jahresüberschuss (adj.)": "net_income_adj",
}

# CAGR / margin / % rows to skip
SKIP_LABELS = {
    "topline growth",
    "gross margin",
    "pex %",
    "opex %",
    "ebitda margin",
    "ebit margin",
}


def _is_ct_header(val: str) -> bool:
    """Check if a string looks like a CT column header (Q1-2025, 04/25, etc.)."""
    s = val.strip()
    if re.match(r"^Q[1-4][-\s]20\d{2}$", s, re.IGNORECASE):
        return True
    if re.match(r"^\d{2}/\d{2,4}$", s):
        return True
    return False


def _ct_header_year(header: str) -> int:
    """Extract the calendar year from a CT header string."""
    m = re.search(r"20(\d{2})", header)
    if m:
        return 2000 + int(m.group(1))
    m = re.search(r"/(\d{2})$", header)
    if m:
        return 2000 + int(m.group(1))
    return 9999


def extract_guv_from_model(ws) -> tuple[list[int], dict, dict]:
    """
    Parse the GuV sheet. Returns (years, data, ct_data) where
    data[year][key] = float_value_in_eur_k,
    ct_data = {"prior": {"header": str, "values": {key: float}},
               "current": {"header": str, "values": {key: float}}}
    """
    years = []
    data = {}
    year_col_indices = {}  # col_index → year
    ct_col_indices = {}  # col_index → header string
    ct_raw = {}  # header → {key: value}

    for row in ws.iter_rows(values_only=True):
        # Find header row: contains integers that look like fiscal years
        if not years:
            year_candidates = [
                (i, v)
                for i, v in enumerate(row)
                if isinstance(v, (int, float)) and 2015 <= v <= 2030
            ]
            if len(year_candidates) >= 2:
                for col_idx, yr in year_candidates:
                    year = int(yr)
                    years.append(year)
                    year_col_indices[col_idx] = year
                    data[year] = {}

                # Scan remaining columns for CT headers (after year columns)
                max_year_col = max(year_col_indices.keys())
                for i, v in enumerate(row):
                    if i <= max_year_col or i in year_col_indices:
                        continue
                    if isinstance(v, str) and _is_ct_header(v):
                        ct_col_indices[i] = v.strip()
                        ct_raw[v.strip()] = {}
            continue

        if not year_col_indices:
            continue

        # Find label column — typically col index 2
        label_raw = None
        for i, v in enumerate(row):
            if isinstance(v, str) and v.strip() and i < 4:
                label_raw = v.strip().lower()
                break

        if not label_raw:
            continue

        # Skip rows with no data in either annual or CT columns
        has_annual = any(isinstance(row[i], (int, float)) for i in year_col_indices)
        has_ct = ct_col_indices and any(
            isinstance(row[i], (int, float)) for i in ct_col_indices
        )
        if not has_annual and not has_ct:
            continue

        # Check if this is a known key (startswith to avoid substring false matches)
        key = None
        for label_fragment, mapped_key in LABEL_MAP.items():
            if label_raw.startswith(label_fragment):
                key = mapped_key
                break

        if not key:
            continue

        # Skip ratio/margin rows
        if any(label_raw.startswith(skip) for skip in SKIP_LABELS):
            continue

        # Skip rows where all year-column values are zero or tiny (ratio rows)
        year_vals = [
            row[c] for c in year_col_indices if isinstance(row[c], (int, float))
        ]
        if year_vals and all(abs(v) < 5 for v in year_vals):
            continue

        for col_idx, year in year_col_indices.items():
            v = row[col_idx]
            if isinstance(v, (int, float)) and key not in data[year]:
                data[year][key] = round(float(v), 2)

        for col_idx, header in ct_col_indices.items():
            v = row[col_idx]
            if isinstance(v, (int, float)) and key not in ct_raw[header]:
                ct_raw[header][key] = round(float(v), 2)

    # Classify CT columns as prior/current by year
    ct_result = {}
    ct_headers_with_data = {h: vals for h, vals in ct_raw.items() if vals}
    if ct_headers_with_data:
        sorted_headers = sorted(ct_headers_with_data.keys(), key=_ct_header_year)
        if len(sorted_headers) >= 2:
            ct_result["prior"] = {
                "header": sorted_headers[0],
                "values": ct_headers_with_data[sorted_headers[0]],
            }
            ct_result["current"] = {
                "header": sorted_headers[1],
                "values": ct_headers_with_data[sorted_headers[1]],
            }
        elif len(sorted_headers) == 1:
            ct_result["current"] = {
                "header": sorted_headers[0],
                "values": ct_headers_with_data[sorted_headers[0]],
            }

    return years, data, ct_result


def get_latest_model(code_name: str, conn) -> Path | None:
    """Get path of the latest non-archive model for a deal.

    Prefers date-prefixed files (YYMMDD_...) over generic names like Bilanz.xlsx.
    A candidate must actually contain the model sheets (GuV + Bewertung) —
    exports like 260706_Fox_vInvestor.xlsx live in 2_Model but carry neither,
    and picking one silently freezes the valuation at the previous model.
    """
    rows = conn.execute(
        """SELECT file_path, file_name FROM deal_documents
           WHERE code_name = ? AND doc_type = 'model' AND (doc_subtype IS NULL OR doc_subtype != 'archive')
           ORDER BY file_name DESC""",
        (code_name,),
    ).fetchall()
    # Prefer versioned files (date prefix like 260313_...) over generic names
    dated = [r for r in rows if r["file_name"][:6].isdigit()]
    candidates = dated if dated else rows
    for r in candidates:
        p = Path(r["file_path"])
        if not p.exists():
            continue
        try:
            wb = openpyxl.load_workbook(p, read_only=True)
            sheets = set(wb.sheetnames)
            wb.close()
        except Exception:
            continue
        if "GuV" in sheets and "Bewertung" in sheets:
            return p
    return None


def build_golden_for_deal(code_name: str, conn) -> dict | None:
    model_path = get_latest_model(code_name, conn)
    if not model_path:
        print(f"  {code_name}: no model file found")
        return None

    try:
        wb = openpyxl.load_workbook(model_path, data_only=True, read_only=True)
    except PermissionError:
        print(f"  {code_name}: file locked — {model_path.name}")
        return None
    except Exception as e:
        print(f"  {code_name}: could not open {model_path.name} — {e}")
        return None

    if "GuV" not in wb.sheetnames:
        print(f"  {code_name}: no GuV sheet in {model_path.name}")
        return None

    ws = wb["GuV"]
    years, pnl_data, _ct_data = extract_guv_from_model(ws)

    if not years:
        print(f"  {code_name}: no year columns found in GuV sheet")
        return None

    # Filter out years with no data
    pnl_data = {str(y): v for y, v in pnl_data.items() if v}

    golden = {
        "code_name": code_name,
        "source_model": model_path.name,
        "currency": "EUR_K",
        "pnl": pnl_data,
    }
    print(f"  {code_name}: extracted {len(pnl_data)} years from {model_path.name}")
    for yr, vals in sorted(pnl_data.items()):
        rev = vals.get("revenue", "?")
        ebitda = vals.get("ebitda_adj", "?")
        print(f"    {yr}: revenue={rev}, ebitda_adj={ebitda}")
    return golden


def main():
    conn = get_conn()
    golden_dir = settings.GOLDEN_DIR
    golden_dir.mkdir(parents=True, exist_ok=True)

    # Deals with registered model docs
    deals_with_models = conn.execute(
        """SELECT DISTINCT code_name FROM deal_documents WHERE doc_type = 'model'"""
    ).fetchall()
    codes = [r["code_name"] for r in deals_with_models]

    print(f"Building golden dataset for: {codes}")
    built = 0
    for code in codes:
        print(f"\n{code}:")
        golden = build_golden_for_deal(code, conn)
        if golden:
            out_path = golden_dir / f"{code.lower()}.json"
            out_path.write_text(json.dumps(golden, indent=2, ensure_ascii=False))
            built += 1
            print(f"  -> saved to {out_path.name}")

    conn.close()
    print(f"\nDone. {built}/{len(codes)} golden files written to {golden_dir}")


if __name__ == "__main__":
    main()
