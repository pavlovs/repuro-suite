"""
DR-M5: Excel Model Reader.

Reads finalized Excel models (GuV + Bewertung sheets) for existing deals.
Writes adjusted P&L to deal_financials (is_adjusted=1) and
valuation scenarios to deal_valuations.
Reconciles model EBITDA vs raw extracted EBITDA — flags discrepancies.
"""

import re
import uuid
from datetime import datetime, timezone

import openpyxl

from scripts.build_golden import extract_guv_from_model, get_latest_model

# ─── Bewertung extraction ────────────────────────────────────────────────────

# Row labels in Bewertung sheet → our field names
BEWERTUNG_LABELS = {
    "adj. ebitda": "ebitda_adj",
    "adj. ebit": "ebit_adj",
    "ev at closing": "ev_at_closing",
    "ev @ closing (incl": "ev_at_closing",
    "ev @ closing": "ev_at_closing_multiple",  # multiple, not EUR — skip
    "ev anticipated earn-out": "ev_anticipated_earnout",
    "total ev incl. super-earn-out": "ev_total",
    "total ev incl. super earn-out": "ev_total",
    "ev incl. max": "ev_total",
    "unternehmenswert": "ev_total",
    "ohne super-earn-out": "ev_anticipated_earnout",
    "ohne earn-out": "ev_at_closing",
    "+/- net cash": "net_cash_debt",
    "+ net cash": "net_cash_debt",
    "- permitted leakage": "permitted_leakage",
    "permitted leakage": "permitted_leakage",
    "erlaube auszahlung": "permitted_leakage",
    "erlaubte auszahlung": "permitted_leakage",
    "equity value": "equity_value",
    "cash at closing": "cash_at_closing",
    "at closing": "cash_at_closing",
    "sofortzahlung": "cash_at_closing",
    "vendor loan": "vendor_loan",
    "nachgelagerte zahlung": "vendor_loan",
    "earn-out anticipated": "earnout_anticipated",
    "earn-out at bp": "earnout_at_bp",
    "earn-out": "earnout_anticipated",
    "super earn-out": "super_earnout",
    "re-invest": "rueckbeteiligung",
    "rückbeteiligung": "rueckbeteiligung",
    "ebitda required for max earn-o": "ebitda_max_earnout",
    "max earn-out": "max_earnout",
    "sales": "sales",
    "adj. gesamtleistung": "sales",
    "rep. ebit": "rep_ebit",
}


def _find_valuation_column(header_row: tuple) -> int | None:
    """Find the column index for the main valuation column.

    Models use various headers like 'Bewertung', 'Valuation',
    'FINAL offer...', 'Bewertung (Basis ...)'.
    The valuation column is typically after the year columns
    and before the earn-out scenario table.
    """
    for i, v in enumerate(header_row):
        if not isinstance(v, str):
            continue
        vl = v.strip().lower()
        if any(
            kw in vl for kw in ["bewertung", "valuation", "final offer", "old offer"]
        ):
            return i
    return None


def extract_bewertung(ws) -> dict:
    """Parse the Bewertung sheet to extract valuation data.

    Returns dict with: ebitda_basis, ebitda_basis_label,
    ev_at_closing, ev_anticipated_earnout, ev_total, equity_value,
    cash_at_closing, rueckbeteiligung, earnout_anticipated,
    super_earnout, net_cash_debt, max_earnout,
    bp_2026 (dict), maxeo_2026 (dict).
    """
    result = {}
    header_row = None
    val_col = None
    avg_col = None
    bp_col = None
    maxeo_col = None
    basis_label = None

    for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
        # Find header row with year columns and valuation column
        if header_row is None:
            # Check for Unternehmensbewertung / Valuation header
            row_strs = [str(v).lower().strip() if v else "" for v in row]
            if any("unternehmensbewertung" in s or "valuation" in s for s in row_strs):
                header_row = row
                for i, v in enumerate(row):
                    if not isinstance(v, str):
                        continue
                    vl = v.strip().lower()
                    if (
                        i >= 5
                        and val_col is None
                        and any(
                            kw in vl for kw in ["bewertung", "valuation", "final offer"]
                        )
                    ):
                        val_col = i
                        basis_label = v.strip()
                    if "bp" in vl and "2026" in vl:
                        bp_col = i
                    if "max" in vl and ("eo" in vl or "earn" in vl):
                        maxeo_col = i
                # Record avg column for EBITDA fallback
                for i, v in enumerate(row):
                    if i >= 5 and isinstance(v, str) and "avg" in v.lower():
                        avg_col = i
                        break
                # If no explicit valuation column, use avg as primary
                if val_col is None and avg_col is not None:
                    val_col = avg_col
                    basis_label = (
                        row[avg_col].strip() if isinstance(row[avg_col], str) else None
                    )
                continue

            continue

        if val_col is None:
            continue

        # Find label
        label_raw = None
        for i, v in enumerate(row):
            if isinstance(v, str) and v.strip() and i < 4:
                label_raw = v.strip().lower()
                break

        if not label_raw:
            continue

        # Match label — sort by length desc to prefer longer/more specific matches
        key = None
        for label_fragment, mapped_key in sorted(
            BEWERTUNG_LABELS.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if label_raw.startswith(label_fragment):
                key = mapped_key
                break

        if not key:
            continue

        # Skip multiple-only rows (not EUR values)
        if key == "ev_at_closing_multiple":
            continue

        # Get value from valuation column (fall back to avg column for EBITDA/EBIT)
        val = row[val_col] if val_col < len(row) else None
        if isinstance(val, (int, float)):
            result[key] = round(float(val), 2)
        elif (
            key in ("ebitda_adj", "ebit_adj")
            and avg_col is not None
            and avg_col != val_col
        ):
            avg_val = row[avg_col] if avg_col < len(row) else None
            if isinstance(avg_val, (int, float)):
                result[key] = round(float(avg_val), 2)

        # Extract BP 2026 and Max EO columns for EBITDA/revenue rows
        if key in ("ebitda_adj", "sales") and bp_col is not None:
            bp_val = row[bp_col] if bp_col < len(row) else None
            if isinstance(bp_val, (int, float)):
                bp_key = "ebitda_k" if key == "ebitda_adj" else "revenue_k"
                result.setdefault("bp_2026", {})[bp_key] = round(float(bp_val), 2)

        if key == "ebitda_adj" and maxeo_col is not None:
            maxeo_val = row[maxeo_col] if maxeo_col < len(row) else None
            if isinstance(maxeo_val, (int, float)):
                result["maxeo_2026_ebitda"] = round(float(maxeo_val), 2)

        # EV rows at BP / Max EO scenarios
        if key == "ev_anticipated_earnout" and bp_col is not None:
            ev_bp = row[bp_col] if bp_col < len(row) else None
            if isinstance(ev_bp, (int, float)) and ev_bp > 100:
                result.setdefault("bp_2026", {})["ev_anticipated_k"] = round(
                    float(ev_bp), 2
                )

        if key == "ev_total" and maxeo_col is not None:
            ev_maxeo = row[maxeo_col] if maxeo_col < len(row) else None
            if isinstance(ev_maxeo, (int, float)) and ev_maxeo > 100:
                result.setdefault("maxeo_2026", {})["ev_total_k"] = round(
                    float(ev_maxeo), 2
                )

    result["_basis_label"] = basis_label
    return result


# ─── Main read_model function ────────────────────────────────────────────────


def read_model(conn, code_name: str, dry_run: bool = False) -> dict:
    """Read a deal's Excel model and extract adjusted P&L + valuation data.

    Returns summary dict with keys:
      model_file, years, pnl_rows_written, valuation_written,
      conflicts_found, errors
    """
    deal = conn.execute(
        "SELECT * FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if not deal:
        raise ValueError(f"Deal not found: {code_name}")

    domain = deal["domain"] or code_name.lower()

    # Find latest model
    model_path = get_latest_model(code_name, conn)
    if not model_path:
        return {
            "model_file": None,
            "years": [],
            "pnl_rows_written": 0,
            "valuation_written": False,
            "conflicts_found": 0,
            "errors": [f"No model file found for {code_name}"],
        }

    # Try to open
    try:
        wb = openpyxl.load_workbook(model_path, data_only=True, read_only=True)
    except PermissionError:
        return {
            "model_file": model_path.name,
            "years": [],
            "pnl_rows_written": 0,
            "valuation_written": False,
            "conflicts_found": 0,
            "errors": [f"File locked: {model_path.name}"],
        }
    except Exception as e:
        return {
            "model_file": model_path.name,
            "years": [],
            "pnl_rows_written": 0,
            "valuation_written": False,
            "conflicts_found": 0,
            "errors": [f"Cannot open {model_path.name}: {e}"],
        }

    errors = []
    model_name = model_path.name
    now = datetime.now(timezone.utc).isoformat()

    # ── GuV sheet: extract adjusted P&L ──────────────────────────────────

    pnl_data = {}
    ct_data = {}
    years = []
    if "GuV" in wb.sheetnames:
        ws = wb["GuV"]
        years, pnl_data, ct_data = extract_guv_from_model(ws)
        pnl_data = {str(y): v for y, v in pnl_data.items() if v}
    else:
        errors.append(f"No GuV sheet in {model_name}")

    # ── Bewertung sheet: extract valuation data ──────────────────────────

    bewertung = {}
    if "Bewertung" in wb.sheetnames:
        ws = wb["Bewertung"]
        bewertung = extract_bewertung(ws)
    else:
        errors.append(f"No Bewertung sheet in {model_name}")

    wb.close()

    if dry_run:
        return {
            "model_file": model_name,
            "years": sorted(pnl_data.keys()),
            "pnl_data": pnl_data,
            "bewertung": bewertung,
            "pnl_rows_written": 0,
            "valuation_written": False,
            "conflicts_found": 0,
            "errors": errors,
            "dry_run": True,
        }

    # ── Write adjusted P&L to deal_financials ─────────────────────────────

    # Clear previous model-sourced adjusted rows (annual + CT) for this deal
    conn.execute(
        "DELETE FROM deal_financials WHERE domain = ? AND is_adjusted = 1 AND source LIKE ?",
        (domain, f"{model_name}%"),
    )

    pnl_rows_written = 0
    for yr_str, entries in pnl_data.items():
        yr = int(yr_str)
        for key, value in entries.items():
            conn.execute(
                """INSERT INTO deal_financials
                   (id, domain, statement, line_item, fiscal_year, period_type,
                    value_k, is_adjusted, source, confidence, is_authoritative, extracted_at)
                   VALUES (?, ?, 'pnl', ?, ?, 'annual',
                           ?, 1, ?, 'confirmed', 1, ?)""",
                (
                    str(uuid.uuid4()),
                    domain,
                    key,
                    yr,
                    value,
                    model_name,
                    now,
                ),
            )
            pnl_rows_written += 1

    # ── Write CT (Current Trading) data from model GuV ────────────────────

    ct_rows_written = 0
    for period_key in ("prior", "current"):
        if period_key not in ct_data:
            continue
        ct_info = ct_data[period_key]
        header = ct_info["header"]
        values = ct_info["values"]
        period_type = "bwa_ytd" if period_key == "current" else "bwa_ytd_m31"

        # Normalize header for _parse_ct_header: Q1-2025→Q1 2025, 04/25→04.25
        norm = re.sub(r"(Q\d)[-](\d+)", r"\1 \2", header, flags=re.IGNORECASE)
        norm = norm.replace("/", ".")
        ct_source = f"{model_name} ({norm})"

        from scripts.build_golden import _ct_header_year

        fiscal_year = _ct_header_year(header)

        for key, value in values.items():
            conn.execute(
                """INSERT INTO deal_financials
                   (id, domain, statement, line_item, fiscal_year, period_type,
                    value_k, is_adjusted, source, confidence, is_authoritative, extracted_at)
                   VALUES (?, ?, 'pnl', ?, ?, ?,
                           ?, 1, ?, 'confirmed', 1, ?)""",
                (
                    str(uuid.uuid4()),
                    domain,
                    key,
                    fiscal_year,
                    period_type,
                    value,
                    ct_source,
                    now,
                ),
            )
            ct_rows_written += 1

    # ── Write Bewertung data to deal_financials ─────────────────────────

    bewertung_keys_to_store = [
        "ebitda_adj",
        "ebit_adj",
        "ev_at_closing",
        "ev_anticipated_earnout",
        "ev_total",
        "equity_value",
        "cash_at_closing",
        "rueckbeteiligung",
        "earnout_anticipated",
        "super_earnout",
        "net_cash_debt",
        "max_earnout",
        "sales",
        "rep_ebit",
    ]
    for key in bewertung_keys_to_store:
        if key in bewertung and bewertung[key] is not None:
            conn.execute(
                """INSERT INTO deal_financials
                   (id, domain, statement, line_item, fiscal_year, period_type,
                    value_k, is_adjusted, source, confidence, is_authoritative, extracted_at)
                   VALUES (?, ?, 'bewertung', ?, NULL, NULL,
                           ?, 1, ?, 'confirmed', 1, ?)""",
                (
                    str(uuid.uuid4()),
                    domain,
                    key,
                    bewertung[key],
                    model_name,
                    now,
                ),
            )
            pnl_rows_written += 1

    # ── Write 2026 BP scenario from Bewertung columns ────────────────────

    # Clear previous BP/MaxEO rows from this model source
    conn.execute(
        "DELETE FROM deal_financials WHERE domain = ? AND source = ? AND line_item = 'ebitda_max_earnout'",
        (domain, f"model:{model_name}"),
    )
    conn.execute(
        "DELETE FROM deal_financials WHERE domain = ? AND source = ? AND fiscal_year = 2026 AND statement = 'pnl'",
        (domain, f"model:{model_name}"),
    )

    bp_2026 = bewertung.get("bp_2026", {})
    if bp_2026.get("ebitda_k") is not None:
        conn.execute(
            """INSERT INTO deal_financials
               (id, domain, statement, line_item, fiscal_year, period_type,
                value_k, is_adjusted, source, confidence, is_authoritative, extracted_at)
               VALUES (?, ?, 'pnl', 'ebitda_adj', 2026, 'budget',
                       ?, 1, ?, 'confirmed', 1, ?)""",
            (
                str(uuid.uuid4()),
                domain,
                bp_2026["ebitda_k"],
                f"model:{model_name}",
                now,
            ),
        )
        pnl_rows_written += 1
    if bp_2026.get("revenue_k") is not None:
        conn.execute(
            """INSERT INTO deal_financials
               (id, domain, statement, line_item, fiscal_year, period_type,
                value_k, is_adjusted, source, confidence, is_authoritative, extracted_at)
               VALUES (?, ?, 'pnl', 'gesamtleistung', 2026, 'budget',
                       ?, 1, ?, 'confirmed', 1, ?)""",
            (
                str(uuid.uuid4()),
                domain,
                bp_2026["revenue_k"],
                f"model:{model_name}",
                now,
            ),
        )
        pnl_rows_written += 1

    # Max Earn-Out EBITDA threshold
    maxeo_ebitda = bewertung.get("maxeo_2026_ebitda")
    if maxeo_ebitda is not None:
        conn.execute(
            """INSERT INTO deal_financials
               (id, domain, statement, line_item, fiscal_year, period_type,
                value_k, is_adjusted, source, confidence, is_authoritative, extracted_at)
               VALUES (?, ?, 'bewertung', 'ebitda_max_earnout', NULL, NULL,
                       ?, 1, ?, 'confirmed', 1, ?)""",
            (str(uuid.uuid4()), domain, maxeo_ebitda, f"model:{model_name}", now),
        )
        pnl_rows_written += 1

    # ── Write deal_valuations row ────────────────────────────────────────

    valuation_written = False
    ebitda_basis = bewertung.get("ebitda_adj")
    ev_closing = bewertung.get("ev_at_closing")

    if ebitda_basis or ev_closing:
        # Delete previous valuation from same model
        conn.execute(
            "DELETE FROM deal_valuations WHERE domain = ? AND source_model_file = ?",
            (domain, model_name),
        )

        conn.execute(
            """INSERT INTO deal_valuations
               (id, domain, valuation_date, ebitda_basis, ebitda_basis_label,
                source_model_file, ev_low, ev_mid, ev_high,
                cash_at_closing, rueckbeteiligung, earnout_max,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                domain,
                now[:10],
                ebitda_basis,
                bewertung.get("_basis_label"),
                model_name,
                ev_closing,  # ev_low = at closing (conservative)
                bewertung.get("ev_anticipated_earnout"),  # ev_mid
                bewertung.get("ev_total"),  # ev_high = total incl super earn-out
                bewertung.get("cash_at_closing"),
                bewertung.get("rueckbeteiligung"),
                bewertung.get("max_earnout"),
                now,
            ),
        )
        valuation_written = True

    # ── Reconcile: model EBITDA adj vs raw extracted EBITDA ──────────────

    conflicts_found = _reconcile_ebitda(conn, domain, pnl_data, model_name, now)

    conn.commit()

    return {
        "model_file": model_name,
        "years": sorted(pnl_data.keys()),
        "pnl_rows_written": pnl_rows_written,
        "valuation_written": valuation_written,
        "conflicts_found": conflicts_found,
        "errors": errors,
    }


def _reconcile_ebitda(
    conn, domain: str, pnl_data: dict, model_name: str, now: str
) -> int:
    """Compare model adjusted EBITDA vs raw extracted EBITDA per year.
    Returns count of discrepancies > 5%.
    """
    conflicts = 0

    for yr_str, entries in pnl_data.items():
        model_ebitda = entries.get("ebitda_adj")
        if model_ebitda is None:
            continue

        yr = int(yr_str)

        raw_rows = conn.execute(
            """SELECT id, value_k, source FROM deal_financials
               WHERE domain = ? AND statement = 'pnl'
                 AND fiscal_year = ? AND line_item = 'ebitda'
                 AND is_adjusted = 0 AND value_k IS NOT NULL""",
            (domain, yr),
        ).fetchall()

        for raw in raw_rows:
            raw_val = raw["value_k"]
            if raw_val is None or raw_val == 0:
                continue
            diff_pct = abs(model_ebitda - raw_val) / abs(raw_val) * 100
            if diff_pct > 5:
                conflicts += 1

    return conflicts
