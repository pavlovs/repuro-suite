"""
DR-M25: CDD databook ingest + validation gate.

Deterministic reader for OUR OWN databook template (Repuro CDD Databook):
fixed tab names, label-scanned tables — no AI classification needed.

Tabs ingested:
  Data Invoices       -> deal_invoices   (atomic fact table, EUR raw)
  Data Customers      -> deal_customers  (customer x year matrix, EUR k)
  Summary red flags   -> deal_dd_items   (category='red_flag')
  Gaps and Confidence -> deal_dd_items   (category='data_gap' / 'confidence')

Analysis tabs (Revenue/Customer/Cohort/Churn Analysis) are NOT copied —
they are recomputed live by cdd.build_cdd() and verified against the
databook's cached formula values by validate() (tie-out gate, delta = 0).

Idempotent: rows carry source='databook:<filename>'; re-ingest deletes all
prior 'databook:%' rows for the domain first.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

from src import cdd as cdd_mod

SHEET_INVOICES = "Data Invoices"
SHEET_CUSTOMERS = "Data Customers"
SHEET_SUMMARY = "Summary"
SHEET_GAPS = "Gaps and Confidence"


def _rows(ws) -> list[tuple]:
    return [tuple(r) for r in ws.iter_rows(values_only=True)]


def _find_row(rows: list[tuple], col_b_value: str) -> int | None:
    """Find 0-based index of the row whose column B equals col_b_value."""
    for i, r in enumerate(rows):
        if len(r) > 1 and isinstance(r[1], str) and r[1].strip() == col_b_value:
            return i
    return None


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _resolve_deal(conn, code_name: str) -> str:
    row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (code_name,)
    ).fetchone()
    if not row or not row["domain"]:
        raise ValueError(f"Deal not found or has no domain: {code_name}")
    return row["domain"]


# ---- Ingest ----------------------------------------------------------------


def ingest(conn, code_name: str, xlsx_path: str) -> dict:
    """Ingest a CDD databook for a deal. Returns counts per table."""
    domain = _resolve_deal(conn, code_name)
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    missing = [s for s in (SHEET_INVOICES, SHEET_CUSTOMERS) if s not in wb.sheetnames]
    if missing:
        raise ValueError(f"Not a CDD databook — missing sheets: {missing}")

    source = f"databook:{path.name}"
    now = datetime.now(timezone.utc).isoformat()
    counts: dict[str, int] = {}

    # Idempotency: this ingest owns all databook rows for the domain
    conn.execute(
        "DELETE FROM deal_invoices WHERE domain = ? AND source LIKE 'databook:%'",
        (domain,),
    )
    conn.execute(
        "DELETE FROM deal_customers WHERE domain = ? AND source LIKE 'databook:%'",
        (domain,),
    )
    conn.execute(
        "DELETE FROM deal_dd_items WHERE domain = ? AND source LIKE 'databook:%'",
        (domain,),
    )

    # ---- Data Invoices -> deal_invoices (EUR raw) ---------------------------
    rows = _rows(wb[SHEET_INVOICES])
    header_idx = next(
        i
        for i, r in enumerate(rows)
        if len(r) > 1 and isinstance(r[1], str) and r[1].strip() == "Rechnungsnummer"
    )
    hdr = {
        (str(v).strip() if v is not None else f"_c{j}"): j
        for j, v in enumerate(rows[header_idx])
    }
    n = 0
    for r in rows[header_idx + 1 :]:
        inv_no = r[hdr["Rechnungsnummer"]] if len(r) > hdr["Rechnungsnummer"] else None
        if inv_no is None or str(inv_no).strip() == "":
            continue
        dt = r[hdr["Datum"]]
        dt_str = (
            dt.strftime("%Y-%m-%d")
            if hasattr(dt, "strftime")
            else (str(dt)[:10] if dt else None)
        )
        conn.execute(
            """INSERT INTO deal_invoices
               (id, domain, invoice_no, status, net_amount, gross_profit,
                segment, model, serial_no, art, invoice_date, fiscal_year,
                quarter, source, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                domain,
                str(inv_no).strip(),
                (str(r[hdr["Status"]]).strip() if r[hdr["Status"]] else None),
                _num(r[hdr["Netto_Gesamt"]]),
                _num(r[hdr["Rohertrag_Sum"]]),
                (str(r[hdr["RepArt"]]).strip() if r[hdr["RepArt"]] else None),
                (str(r[hdr["Modell"]]).strip() if r[hdr["Modell"]] else None),
                (str(r[hdr["SN"]]).strip() if r[hdr["SN"]] else None),
                (str(r[hdr["Art"]]).strip() if r[hdr["Art"]] else None),
                dt_str,
                int(_num(r[hdr["Year"]])) if _num(r[hdr["Year"]]) else None,
                int(_num(r[hdr["Quarter"]])) if _num(r[hdr["Quarter"]]) else None,
                source,
                now,
            ),
        )
        n += 1
    counts["deal_invoices"] = n

    # ---- Data Customers -> deal_customers (EUR k, one row per cust-year) ----
    rows = _rows(wb[SHEET_CUSTOMERS])
    header_idx = next(
        i
        for i, r in enumerate(rows)
        if len(r) > 2 and isinstance(r[2], str) and r[2].strip() == "Kunden"
    )
    hdr_row = rows[header_idx]
    year_cols = {
        int(v): j for j, v in enumerate(hdr_row) if isinstance(v, (int, float))
    }
    col_type = 2  # 'Kunden' column = customer type
    col_rank = next(
        j
        for j, v in enumerate(hdr_row)
        if isinstance(v, str) and v.strip() == "Ranking"
    )
    col_cohort = next(
        j for j, v in enumerate(hdr_row) if isinstance(v, str) and v.strip() == "Cohort"
    )
    col_no = next(
        j for j, v in enumerate(hdr_row) if isinstance(v, str) and v.strip() == "Cust #"
    )
    n = 0
    n_cust = 0
    for r in rows[header_idx + 1 :]:
        ctype = r[col_type] if len(r) > col_type else None
        cust_no = _num(r[col_no]) if len(r) > col_no else None
        if ctype is None or cust_no is None:
            continue
        name = f"Kunde #{int(cust_no):03d}"
        cohort = r[col_cohort]
        rank = _num(r[col_rank])
        n_cust += 1
        for year, j in year_cols.items():
            v = _num(r[j]) if len(r) > j else None
            if v is None or abs(v) < 1e-9:
                continue
            conn.execute(
                """INSERT OR REPLACE INTO deal_customers
                   (id, domain, customer_name, customer_id, fiscal_year,
                    revenue_k, rank, cohort, customer_type, source, extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    domain,
                    name,
                    str(int(cust_no)),
                    year,
                    round(v / 1000.0, 4),
                    int(rank) if rank is not None else None,
                    str(int(cohort))
                    if isinstance(cohort, (int, float))
                    else (str(cohort).strip() if cohort else None),
                    str(ctype).strip(),
                    source,
                    now,
                ),
            )
            n += 1
    counts["deal_customers"] = n
    counts["customers_distinct"] = n_cust

    # ---- Summary red flags -> deal_dd_items ---------------------------------
    n = 0
    if SHEET_SUMMARY in wb.sheetnames:
        rows = _rows(wb[SHEET_SUMMARY])
        i = _find_row(rows, "#")
        if i is not None:
            for r in rows[i + 1 :]:
                num = r[1] if len(r) > 1 else None
                finding = r[2] if len(r) > 2 else None
                if finding is None or str(finding).strip() == "":
                    break
                conn.execute(
                    """INSERT INTO deal_dd_items
                       (id, domain, category, subcategory, description,
                        risk_level, risk_note, source, extracted_at)
                       VALUES (?, ?, 'red_flag', ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        domain,
                        str(num).strip() if num is not None else None,
                        str(finding).strip(),
                        (str(r[4]).strip().upper() if len(r) > 4 and r[4] else None),
                        (str(r[3]).strip() if len(r) > 3 and r[3] else None),
                        source,
                        now,
                    ),
                )
                n += 1
    counts["red_flags"] = n

    # ---- Gaps and Confidence -> deal_dd_items -------------------------------
    n_gaps = n_conf = 0
    if SHEET_GAPS in wb.sheetnames:
        rows = _rows(wb[SHEET_GAPS])
        i = _find_row(rows, "Item")
        if i is not None:
            for r in rows[i + 1 :]:
                item = r[1] if len(r) > 1 else None
                if item is None or str(item).strip() == "":
                    break
                conn.execute(
                    """INSERT INTO deal_dd_items
                       (id, domain, category, subcategory, description,
                        risk_level, source, extracted_at)
                       VALUES (?, ?, 'data_gap', ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        domain,
                        str(item).strip(),
                        (str(r[2]).strip() if len(r) > 2 and r[2] else ""),
                        (str(r[3]).strip().upper() if len(r) > 3 and r[3] else None),
                        source,
                        now,
                    ),
                )
                n_gaps += 1
        i = _find_row(rows, "Analysis")
        if i is not None:
            for r in rows[i + 1 :]:
                analysis = r[1] if len(r) > 1 else None
                if analysis is None or str(analysis).strip() == "":
                    break
                conn.execute(
                    """INSERT INTO deal_dd_items
                       (id, domain, category, subcategory, description,
                        confidence, source, extracted_at)
                       VALUES (?, ?, 'confidence', ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        domain,
                        str(analysis).strip(),
                        (str(r[2]).strip() if len(r) > 2 and r[2] else ""),
                        (str(r[3]).strip() if len(r) > 3 and r[3] else None),
                        source,
                        now,
                    ),
                )
                n_conf += 1
    counts["data_gaps"] = n_gaps
    counts["confidence_items"] = n_conf

    wb.close()
    conn.commit()
    return counts


# ---- Validation gate --------------------------------------------------------


def _check(checks: list, label: str, expected, actual, tol: float = 0.02) -> None:
    """Numeric comparison with tolerance (EUR k values cached at full precision)."""
    if expected is None and actual is None:
        checks.append((label, expected, actual, True))
        return
    if expected is None or actual is None:
        checks.append((label, expected, actual, False))
        return
    ok = abs(float(expected) - float(actual)) <= tol
    checks.append((label, round(float(expected), 2), round(float(actual), 2), ok))


def validate(conn, code_name: str, xlsx_path: str) -> dict:
    """Tie-out: every recomputed figure must match the databook's cached values.

    Compares cdd.build_cdd() output against the analysis tabs of the
    databook (cached formula results). Returns {passed, failed, failures}.
    """
    domain = _resolve_deal(conn, code_name)
    data = cdd_mod.build_cdd(conn, domain)
    if not data:
        raise ValueError("No CDD data in DB — run ingest first.")

    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True, read_only=True)
    checks: list = []

    # ---- Revenue Analysis: segment revenue + totals + quarterly -------------
    if "Revenue Analysis" in wb.sheetnames:
        rows = _rows(wb["Revenue Analysis"])
        i = _find_row(rows, "Segment")
        if i is not None:
            hdr = rows[i]
            year_cols = {}
            for j, v in enumerate(hdr):
                if isinstance(v, (int, float)):
                    year_cols[int(v)] = j
                elif isinstance(v, str) and v.strip().endswith("YTD"):
                    year_cols[int(v.strip().split()[0])] = j
            seg_by_name = {
                s["name"]: s for s in data.get("segments", {}).get("rows", [])
            }
            for r in rows[i + 1 :]:
                name = r[1] if len(r) > 1 else None
                if name is None or str(name).strip() == "":
                    continue
                name = str(name).strip()
                if name.startswith("Check") or name.startswith("Delta"):
                    break
                if name == "Other services":
                    continue
                if name == "Total":
                    for y, j in year_cols.items():
                        _check(
                            checks,
                            f"RevAnalysis Total {y}",
                            _num(r[j]),
                            data["segments"]["totals"].get(str(y)),
                        )
                    break
                ours = seg_by_name.get(name)
                for y, j in year_cols.items():
                    exp = _num(r[j])
                    act = ours["rev"].get(str(y)) if ours else None
                    if exp is None and act is None:
                        continue
                    _check(checks, f"Segment {name} {y}", exp or 0, act or 0)

        # GM by segment (header 'Segment' + '2023 Rev'/'2023 GM%' columns)
        gm_i = None
        for k, r in enumerate(rows):
            if (
                len(r) > 2
                and isinstance(r[1], str)
                and r[1].strip() == "Segment"
                and isinstance(r[2], str)
                and "Rev" in str(r[2])
            ):
                gm_i = k
                break
        if gm_i is not None:
            hdr = rows[gm_i]
            gm_cols = {}
            for j, v in enumerate(hdr):
                if isinstance(v, str) and v.strip().endswith("GM%"):
                    gm_cols[int(v.strip().split()[0])] = j
            seg_by_name = {
                s["name"]: s for s in data.get("segments", {}).get("rows", [])
            }
            for r in rows[gm_i + 1 :]:
                name = r[1] if len(r) > 1 else None
                if name is None or str(name).strip() == "":
                    break
                name = str(name).strip()
                ours = seg_by_name.get(name)
                for y, j in gm_cols.items():
                    exp = _num(r[j])
                    act = ours["gm_pct"].get(str(y)) if ours else None
                    if exp is None:
                        continue
                    _check(
                        checks,
                        f"GM% {name} {y}",
                        exp * 100,
                        act,
                        tol=0.1,
                    )

        # Quarterly
        qi = _find_row(rows, "Quarter")
        if qi is not None:
            q_ours = {q["label"]: q for q in data.get("quarterly", [])}
            for r in rows[qi + 1 :]:
                label = r[1] if len(r) > 1 else None
                if label is None or str(label).strip() == "":
                    break
                label = str(label).strip()
                ours = q_ours.get(label)
                _check(
                    checks,
                    f"Quarterly {label} rev",
                    _num(r[4]),
                    ours["rev"] if ours else None,
                )

    # ---- Customer Analysis: concentration + types + buckets -----------------
    if "Customer Analysis" in wb.sheetnames:
        rows = _rows(wb["Customer Analysis"])
        tiers = {t["label"]: t for t in data.get("concentration", {}).get("tiers", [])}
        for r in rows:
            label = r[1] if len(r) > 1 else None
            if isinstance(label, str) and label.strip() in (
                "Top 3",
                "Top 5",
                "Top 10",
                "Top 20",
            ):
                t = tiers.get(label.strip())
                _check(
                    checks,
                    f"Concentration {label.strip()} rev",
                    _num(r[3]),
                    t["rev"] if t else None,
                )
            if isinstance(label, str) and label.strip().startswith("All active"):
                _check(
                    checks,
                    "Active customers n",
                    _num(r[2]),
                    data.get("concentration", {}).get("active", {}).get("n"),
                    tol=0.5,
                )

        ti = _find_row(rows, "Customer type")
        if ti is not None:
            hdr = rows[ti]
            year_cols = {
                int(v): j for j, v in enumerate(hdr) if isinstance(v, (int, float))
            }
            ours_types = {d["type"]: d for d in data.get("type_split", [])}
            for r in rows[ti + 1 :]:
                name = r[1] if len(r) > 1 else None
                if name is None or str(name).strip() == "":
                    break
                name = str(name).strip()
                if name == "Total":
                    break
                ours = ours_types.get(name)
                _check(
                    checks,
                    f"Type {name} n",
                    _num(r[2]),
                    ours["n"] if ours else None,
                    tol=0.5,
                )
                for y, j in year_cols.items():
                    act = ours["rev"].get(str(y)) if ours else None
                    exp = _num(r[j])
                    if exp is None and act is None:
                        continue
                    _check(checks, f"Type {name} {y}", exp or 0, act or 0)

        bi = _find_row(rows, "Bucket")
        if bi is not None:
            ours_buckets = {b["label"]: b for b in data.get("buckets", [])}
            for r in rows[bi + 1 :]:
                label = r[1] if len(r) > 1 else None
                if label is None or str(label).strip() == "":
                    break
                b = ours_buckets.get(str(label).strip())
                _check(
                    checks,
                    f"Bucket {label} n",
                    _num(r[4]),
                    b["n"] if b else None,
                    tol=0.5,
                )
                _check(
                    checks,
                    f"Bucket {label} rev",
                    _num(r[5]),
                    b["rev"] if b else None,
                )

    # ---- Cohort Analysis: matrix + retention --------------------------------
    if "Cohort Analysis" in wb.sheetnames:
        rows = _rows(wb["Cohort Analysis"])
        ci = _find_row(rows, "Cohort")
        if ci is not None:
            hdr = rows[ci]
            year_cols = {}
            for j, v in enumerate(hdr):
                if isinstance(v, (int, float)):
                    year_cols[int(v)] = j
                elif isinstance(v, str) and v.strip().endswith("YTD"):
                    year_cols[int(v.strip().split()[0])] = j
            ours_cohorts = {
                c["cohort"]: c for c in data.get("cohorts", {}).get("rows", [])
            }
            for r in rows[ci + 1 :]:
                label = r[1] if len(r) > 1 else None
                if label is None or str(label).strip() == "":
                    break
                label = str(label).strip()
                if label == "Total":
                    for y, j in year_cols.items():
                        _check(
                            checks,
                            f"Cohort Total {y}",
                            _num(r[j]),
                            data["cohorts"]["total"]["rev"].get(str(y)),
                        )
                    break
                key = label.replace(" cohort", "")
                ours = ours_cohorts.get(key)
                _check(
                    checks,
                    f"Cohort {key} n",
                    _num(r[2]),
                    ours["n"] if ours else None,
                    tol=0.5,
                )
                for y, j in year_cols.items():
                    exp = _num(r[j])
                    act = ours["rev"].get(str(y)) if ours else None
                    if exp is None and act is None:
                        continue
                    _check(checks, f"Cohort {key} {y}", exp or 0, act or 0)

        ri = _find_row(rows, "Period")
        if ri is not None:
            ours_ret = {
                x["period"].split(" YTD")[0]: x for x in data.get("retention", [])
            }
            for r in rows[ri + 1 :]:
                label = r[1] if len(r) > 1 else None
                if label is None or str(label).strip() == "":
                    break
                key = str(label).strip().split(" YTD")[0]
                ours = ours_ret.get(key)
                _check(
                    checks,
                    f"Retention {key} logo%",
                    (_num(r[4]) or 0) * 100,
                    ours["logo_pct"] if ours else None,
                    tol=0.5,
                )
                _check(
                    checks,
                    f"Retention {key} NRR%",
                    (_num(r[7]) or 0) * 100,
                    ours["nrr_pct"] if ours else None,
                    tol=0.5,
                )

    # ---- Churn Analysis ------------------------------------------------------
    if "Churn Analysis" in wb.sheetnames:
        rows = _rows(wb["Churn Analysis"])
        pi = _find_row(rows, "Period")
        if pi is not None:
            ours_churn = {}
            for x in data.get("churn", {}).get("by_year", []):
                ours_churn[x["period"].split(" YTD")[0]] = x
            for r in rows[pi + 1 :]:
                label = r[1] if len(r) > 1 else None
                if label is None or str(label).strip() == "":
                    break
                key = str(label).strip()
                # databook last row label: '2025 -> no invoices 2026 YTD...'
                key2 = key.split(" YTD")[0]
                ours = None
                for k, v in ours_churn.items():
                    if (
                        key2.startswith(k.split(" -> ")[0])
                        and k.split(" -> ")[0] in key2
                    ):
                        a = k.split(" -> ")[0]
                        if key2.startswith(a):
                            ours = (
                                v if key2.startswith(k.split(" YTD")[0][:12]) else ours
                            )
                ours = ours_churn.get(key2, ours)
                if ours is None:
                    # fuzzy: match on start year
                    start = key2.split(" ")[0]
                    for k, v in ours_churn.items():
                        if k.startswith(start):
                            ours = v
                            break
                _check(
                    checks,
                    f"Churn {key2} logos",
                    _num(r[3]),
                    ours["churned"] if ours else None,
                    tol=0.5,
                )
                _check(
                    checks,
                    f"Churn {key2} rev",
                    _num(r[5]),
                    ours["churned_rev"] if ours else None,
                )

        ti = _find_row(rows, "Customer type")
        if ti is not None:
            ours_bt = {x["type"]: x for x in data.get("churn", {}).get("by_type", [])}
            for r in rows[ti + 1 :]:
                name = r[1] if len(r) > 1 else None
                if name is None or str(name).strip() == "":
                    break
                ours = ours_bt.get(str(name).strip())
                _check(
                    checks,
                    f"ChurnType {name} churned",
                    _num(r[3]),
                    ours["churned"] if ours else None,
                    tol=0.5,
                )
                _check(
                    checks,
                    f"ChurnType {name} rev",
                    _num(r[5]),
                    ours["churned_rev"] if ours else None,
                )

    wb.close()
    failures = [c for c in checks if not c[3]]
    return {
        "passed": len(checks) - len(failures),
        "failed": len(failures),
        "total": len(checks),
        "failures": [
            {"check": c[0], "expected": c[1], "actual": c[2]} for c in failures
        ],
    }
