"""
DR-M25: Commercial DD compute layer.

Computes every analysis in the CDD databook live from the atomic fact
tables (deal_invoices + deal_customers) instead of storing frozen
aggregates. Methodology mirrors the databook exactly:

  - active in year y      = revenue_y != 0 (negatives count as active)
  - cohort                = stored cohort column (first calendar year with revenue)
  - logo retention y->y+1 = retained / active(y); retained = active in both
  - NRR y->y+1            = sum of y+1 revenue of customers active in y / rev(y)
  - churned               = active in y, zero revenue in y+1
  - new/reactivated       = revenue in y+1, zero in y
  - buckets               = per-customer TOTAL revenue (all years, EUR)
  - concentration         = latest FULL year, sorted by that year's revenue

Used by dashboard.py (DATA.cdd) and databook.py (validation gate).
"""

from __future__ import annotations

from typing import Any


def _r(v: float | None, nd: int = 2) -> float | None:
    return round(v, nd) if v is not None else None


def _invoice_years(conn, domain: str) -> tuple[list[int], int | None]:
    """Return (sorted fiscal years with invoices, ytd_year or None).

    A year is YTD when its latest invoice date is before December.
    """
    rows = conn.execute(
        """SELECT fiscal_year, MAX(invoice_date) AS max_dt
           FROM deal_invoices WHERE domain = ? AND fiscal_year IS NOT NULL
           GROUP BY fiscal_year ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    years = [r["fiscal_year"] for r in rows]
    ytd_year = None
    if rows:
        last = rows[-1]
        max_dt = last["max_dt"] or ""
        # ISO date string: YYYY-MM-DD...
        if len(max_dt) >= 7:
            month = int(max_dt[5:7])
            if month < 12:
                ytd_year = last["fiscal_year"]
    return years, ytd_year


def _customer_matrix(conn, domain: str) -> tuple[list[dict], list[int]]:
    """Pivot deal_customers into one dict per customer with rev per year (EUR k).

    When databook-sourced rows exist they take precedence EXCLUSIVELY —
    legacy/manual customer rows from other ingests must not mix into the
    tied-out databook population (Codex review DR-M25, finding 1).
    """
    has_databook = conn.execute(
        """SELECT 1 FROM deal_customers
           WHERE domain = ? AND source LIKE 'databook:%' LIMIT 1""",
        (domain,),
    ).fetchone()
    src_clause = "AND source LIKE 'databook:%'" if has_databook else ""
    rows = conn.execute(
        f"""SELECT customer_name, customer_type, cohort, rank, fiscal_year, revenue_k
           FROM deal_customers WHERE domain = ? AND revenue_k IS NOT NULL {src_clause}""",
        (domain,),
    ).fetchall()
    years = sorted({r["fiscal_year"] for r in rows})
    by_cust: dict[str, dict] = {}
    for r in rows:
        c = by_cust.setdefault(
            r["customer_name"],
            {
                "name": r["customer_name"],
                "type": r["customer_type"],
                "cohort": r["cohort"],
                "rank": r["rank"],
                "rev": {},
            },
        )
        c["rev"][r["fiscal_year"]] = (c["rev"].get(r["fiscal_year"]) or 0) + r[
            "revenue_k"
        ]
        if r["customer_type"] and not c["type"]:
            c["type"] = r["customer_type"]
        if r["cohort"] and not c["cohort"]:
            c["cohort"] = r["cohort"]
    customers = list(by_cust.values())
    for c in customers:
        c["total"] = sum(c["rev"].values())
    return customers, years


def _active(c: dict, year: int) -> bool:
    """Databook methodology: active = revenue strictly > 0 (COUNTIFS ">0").

    A year with only credit notes (net negative) does NOT count as active."""
    v = c["rev"].get(year)
    return v is not None and v > 1e-9


def build_cdd(conn, domain: str) -> dict[str, Any] | None:
    """Build the full CDD data block. Returns None when no CDD data loaded."""
    inv_count = conn.execute(
        "SELECT COUNT(*) FROM deal_invoices WHERE domain = ?", (domain,)
    ).fetchone()[0]
    cust_count = conn.execute(
        "SELECT COUNT(DISTINCT customer_name) FROM deal_customers WHERE domain = ?",
        (domain,),
    ).fetchone()[0]
    if inv_count == 0 and cust_count == 0:
        return None

    out: dict[str, Any] = {
        "meta": {"invoice_count": inv_count, "customer_count": cust_count}
    }

    # ---- Invoice-based: segments + quarterly --------------------------------
    inv_years, ytd_year = _invoice_years(conn, domain)
    full_years = [y for y in inv_years if y != ytd_year]
    out["meta"]["ytd_year"] = ytd_year
    out["meta"]["invoice_years"] = inv_years

    if inv_years:
        seg_rows = conn.execute(
            """SELECT segment, fiscal_year,
                      SUM(COALESCE(net_amount, 0)) / 1000.0 AS rev_k,
                      SUM(COALESCE(gross_profit, 0)) / 1000.0 AS gp_k
               FROM deal_invoices WHERE domain = ?
               GROUP BY segment, fiscal_year""",
            (domain,),
        ).fetchall()
        segs: dict[str, dict] = {}
        for r in seg_rows:
            name = r["segment"] or "(unzugeordnet)"
            s = segs.setdefault(name, {"name": name, "rev": {}, "gp": {}})
            s["rev"][r["fiscal_year"]] = r["rev_k"]
            s["gp"][r["fiscal_year"]] = r["gp_k"]

        seg_list = []
        for s in segs.values():
            gm = {}
            for y, rv in s["rev"].items():
                gm[y] = (s["gp"].get(y) or 0) / rv if abs(rv) > 1e-9 else None
            row: dict[str, Any] = {
                "name": s["name"],
                "rev": {str(y): _r(v) for y, v in s["rev"].items()},
                "gm_pct": {
                    str(y): _r(v * 100, 1) if v is not None else None
                    for y, v in gm.items()
                },
            }
            # YoY between consecutive full years + CAGR first->last full year
            yoy = {}
            for a, b in zip(full_years, full_years[1:]):
                ra, rb = s["rev"].get(a), s["rev"].get(b)
                if ra and abs(ra) > 1e-9 and rb is not None:
                    yoy[f"{a}-{b}"] = _r((rb / ra - 1) * 100, 1)
            row["yoy"] = yoy
            if len(full_years) >= 2:
                ra = s["rev"].get(full_years[0])
                rb = s["rev"].get(full_years[-1])
                n = full_years[-1] - full_years[0]
                if ra and ra > 0 and rb is not None and rb > 0 and n > 0:
                    row["cagr"] = _r(((rb / ra) ** (1 / n) - 1) * 100, 1)
            seg_list.append(row)
        latest_full_inv = full_years[-1] if full_years else inv_years[-1]
        seg_list.sort(key=lambda s: -(float(s["rev"].get(str(latest_full_inv)) or 0)))

        totals = {}
        for y in inv_years:
            totals[str(y)] = _r(
                sum(s["rev"][y] for s in segs.values() if y in s["rev"])
            )
        # share of latest full year
        tot_latest = totals.get(str(latest_full_inv)) or 0
        for s in seg_list:
            rv = float(s["rev"].get(str(latest_full_inv)) or 0)
            s["share_latest"] = _r(rv / tot_latest * 100, 1) if tot_latest else None

        out["segments"] = {
            "years": inv_years,
            "full_years": full_years,
            "latest_full_year": latest_full_inv,
            "rows": seg_list,
            "totals": totals,
        }

        q_rows = conn.execute(
            """SELECT fiscal_year, quarter,
                      SUM(COALESCE(net_amount, 0)) / 1000.0 AS rev_k,
                      SUM(COALESCE(gross_profit, 0)) / 1000.0 AS gp_k
               FROM deal_invoices
               WHERE domain = ? AND quarter IS NOT NULL
               GROUP BY fiscal_year, quarter
               ORDER BY fiscal_year, quarter""",
            (domain,),
        ).fetchall()
        out["quarterly"] = [
            {
                "label": f"{r['fiscal_year']}-Q{r['quarter']}",
                "year": r["fiscal_year"],
                "q": r["quarter"],
                "rev": _r(r["rev_k"]),
                "gp": _r(r["gp_k"]),
                "gm_pct": _r(r["gp_k"] / r["rev_k"] * 100, 1)
                if abs(r["rev_k"]) > 1e-9
                else None,
            }
            for r in q_rows
        ]

    # ---- Customer-based analyses ---------------------------------------------
    customers, cust_years = _customer_matrix(conn, domain)
    if customers:
        # YTD year on the customer side = max year; full years = rest.
        # Mirrors the databook: customer matrix carries one partial year at the end
        # when invoices say the latest year is YTD.
        c_ytd = ytd_year if ytd_year in cust_years else None
        c_full = [y for y in cust_years if y != c_ytd]
        latest_full = c_full[-1] if c_full else cust_years[-1]
        out["meta"]["customer_years"] = cust_years
        out["meta"]["latest_full_year"] = latest_full

        # Concentration (latest full year)
        ranked = sorted(customers, key=lambda c: -(c["rev"].get(latest_full) or 0))
        active_latest = [c for c in customers if _active(c, latest_full)]
        total_latest = sum(c["rev"].get(latest_full) or 0 for c in customers)
        tiers = []
        for n in (3, 5, 10, 20):
            top = ranked[:n]
            rev = sum(c["rev"].get(latest_full) or 0 for c in top)
            tiers.append(
                {
                    "label": f"Top {n}",
                    "n": n,
                    "rev": _r(rev),
                    "pct": _r(rev / total_latest * 100, 1) if total_latest else None,
                }
            )
        out["concentration"] = {
            "year": latest_full,
            "tiers": tiers,
            "active": {"n": len(active_latest), "rev": _r(total_latest)},
        }

        # Type split
        types: dict[str, dict] = {}
        for c in customers:
            t = c["type"] or "(unbekannt)"
            d = types.setdefault(t, {"type": t, "n": 0, "rev": {}, "total": 0.0})
            d["n"] += 1
            for y, v in c["rev"].items():
                d["rev"][y] = (d["rev"].get(y) or 0) + v
            d["total"] += c["total"]
        grand_total = sum(d["total"] for d in types.values())
        type_split = sorted(types.values(), key=lambda d: -d["total"])
        out["type_split"] = [
            {
                "type": d["type"],
                "n": d["n"],
                "rev": {str(y): _r(v) for y, v in sorted(d["rev"].items())},
                "total": _r(d["total"]),
                "share": _r(d["total"] / grand_total * 100, 1) if grand_total else None,
            }
            for d in type_split
        ]

        # Buckets on per-customer total (EUR; revenue_k * 1000)
        bucket_defs = [
            ("> 100k", 100_000, None),
            ("50-100k", 50_000, 100_000),
            ("20-50k", 20_000, 50_000),
            ("10-20k", 10_000, 20_000),
            ("1-10k", 1_000, 10_000),
            ("< 1k", None, 1_000),
        ]
        buckets = []
        for label, lo, hi in bucket_defs:
            members = [
                c
                for c in customers
                if (lo is None or c["total"] * 1000 >= lo)
                and (hi is None or c["total"] * 1000 < hi)
            ]
            rev = sum(c["total"] for c in members)
            buckets.append(
                {
                    "label": label,
                    "n": len(members),
                    "rev": _r(rev),
                    "pct": _r(rev / grand_total * 100, 1) if grand_total else None,
                }
            )
        out["buckets"] = buckets

        # New vs existing (latest full year + YTD year)
        new_existing = {}
        for y in [latest_full] + ([c_ytd] if c_ytd else []):
            active_y = [c for c in customers if _active(c, y)]
            new = [c for c in active_y if str(c["cohort"]) == str(y)]
            existing = [c for c in active_y if str(c["cohort"]) != str(y)]
            tot_y = sum(c["rev"].get(y) or 0 for c in customers)
            new_existing[str(y)] = {
                "existing": {
                    "n": len(existing),
                    "rev": _r(sum(c["rev"].get(y) or 0 for c in existing)),
                    "pct": _r(
                        sum(c["rev"].get(y) or 0 for c in existing) / tot_y * 100, 1
                    )
                    if tot_y
                    else None,
                },
                "new": {
                    "n": len(new),
                    "rev": _r(sum(c["rev"].get(y) or 0 for c in new)),
                    "pct": _r(sum(c["rev"].get(y) or 0 for c in new) / tot_y * 100, 1)
                    if tot_y
                    else None,
                },
            }
        out["new_existing"] = new_existing

        # Cohort matrix
        cohorts: dict[str, dict] = {}
        for c in customers:
            key = str(c["cohort"]) if c["cohort"] else "(ohne)"
            d = cohorts.setdefault(key, {"cohort": key, "n": 0, "rev": {}})
            d["n"] += 1
            for y, v in c["rev"].items():
                d["rev"][y] = (d["rev"].get(y) or 0) + v
        cohort_rows = []
        for key in sorted(cohorts.keys()):
            d = cohorts[key]
            row = {
                "cohort": d["cohort"],
                "n": d["n"],
                "rev": {str(y): _r(d["rev"].get(y)) for y in cust_years},
            }
            try:
                cy = int(key)
                ra = d["rev"].get(cy)
                rb = d["rev"].get(latest_full)
                n_yrs = latest_full - cy
                if ra and ra > 0 and rb is not None and rb > 0 and n_yrs > 0:
                    row["cagr"] = _r(((rb / ra) ** (1 / n_yrs) - 1) * 100, 1)
            except ValueError:
                pass
            cohort_rows.append(row)
        out["cohorts"] = {
            "years": cust_years,
            "rows": cohort_rows,
            "total": {
                "n": len(customers),
                "rev": {
                    str(y): _r(sum(c["rev"].get(y) or 0 for c in customers))
                    for y in cust_years
                },
            },
        }

        # Retention + churn per consecutive year pair
        retention = []
        churn_by_year = []
        bridge = []
        for a, b in zip(cust_years, cust_years[1:]):
            act_a = [c for c in customers if _active(c, a)]
            retained = [c for c in act_a if _active(c, b)]
            churned = [c for c in act_a if not _active(c, b)]
            new_react = [c for c in customers if _active(c, b) and not _active(c, a)]
            rev_a = sum(c["rev"].get(a) or 0 for c in customers)
            rev_b = sum(c["rev"].get(b) or 0 for c in customers)
            rev_retained = sum(c["rev"].get(b) or 0 for c in act_a)
            churned_rev = sum(c["rev"].get(a) or 0 for c in churned)
            partial = " YTD (partial)" if b == c_ytd else ""
            label = f"{a} -> {b}{partial}"
            retention.append(
                {
                    "period": label,
                    "partial": b == c_ytd,
                    "active_start": len(act_a),
                    "retained": len(retained),
                    "logo_pct": _r(len(retained) / len(act_a) * 100, 1)
                    if act_a
                    else None,
                    "rev_start": _r(rev_a),
                    "rev_retained": _r(rev_retained),
                    "nrr_pct": _r(rev_retained / rev_a * 100, 1) if rev_a else None,
                }
            )
            churn_by_year.append(
                {
                    "period": label,
                    "partial": b == c_ytd,
                    "active_start": len(act_a),
                    "churned": len(churned),
                    "logo_churn_pct": _r(len(churned) / len(act_a) * 100, 1)
                    if act_a
                    else None,
                    "churned_rev": _r(churned_rev),
                    "rev_churn_pct": _r(churned_rev / rev_a * 100, 1)
                    if rev_a
                    else None,
                }
            )
            if b != c_ytd:
                net_retained = sum(
                    (c["rev"].get(b) or 0) - (c["rev"].get(a) or 0) for c in retained
                )
                new_rev = sum(c["rev"].get(b) or 0 for c in new_react)
                bridge.append(
                    {
                        "period": label,
                        "start": _r(rev_a),
                        "churned": _r(-churned_rev),
                        "net_retained": _r(net_retained),
                        "new": _r(new_rev),
                        "end": _r(rev_b),
                    }
                )
        out["retention"] = retention
        out["churn"] = {"by_year": churn_by_year, "bridge": bridge}

        # Churn by type for the last full-year pair
        if len(c_full) >= 2:
            a, b = c_full[-2], c_full[-1]
            by_type = []
            for t in sorted({c["type"] or "(unbekannt)" for c in customers}):
                members = [c for c in customers if (c["type"] or "(unbekannt)") == t]
                act_a = [c for c in members if _active(c, a)]
                churned = [c for c in act_a if not _active(c, b)]
                if not act_a:
                    continue
                by_type.append(
                    {
                        "type": t,
                        "active": len(act_a),
                        "churned": len(churned),
                        "logo_churn_pct": _r(len(churned) / len(act_a) * 100, 1),
                        "churned_rev": _r(sum(c["rev"].get(a) or 0 for c in churned)),
                    }
                )
            by_type.sort(key=lambda d: -(d["churned_rev"] or 0))
            out["churn"]["by_type"] = by_type
            out["churn"]["by_type_period"] = f"{a} -> {b}"

        # Top 20 by latest full year
        out["top20"] = [
            {
                "rank": i + 1,
                "name": c["name"],
                "type": c["type"],
                "cohort": c["cohort"],
                "rev": {str(y): _r(c["rev"].get(y)) for y in cust_years},
                "total": _r(c["total"]),
            }
            for i, c in enumerate(ranked[:20])
        ]

    # ---- Findings from deal_dd_items ----------------------------------------
    items = conn.execute(
        """SELECT category, subcategory, description, risk_level, risk_note,
                  confidence, notes
           FROM deal_dd_items WHERE domain = ?
           ORDER BY category,
             CASE risk_level WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END""",
        (domain,),
    ).fetchall()
    findings: dict[str, list] = {"red_flags": [], "gaps": [], "confidence": []}
    for r in items:
        if r["category"] == "red_flag":
            findings["red_flags"].append(
                {
                    "finding": r["description"],
                    "so_what": r["risk_note"],
                    "severity": r["risk_level"],
                }
            )
        elif r["category"] == "data_gap":
            findings["gaps"].append(
                {
                    "item": r["subcategory"],
                    "description": r["description"],
                    "severity": r["risk_level"],
                }
            )
        elif r["category"] == "confidence":
            findings["confidence"].append(
                {
                    "analysis": r["subcategory"],
                    "notes": r["description"],
                    "confidence": r["confidence"],
                }
            )
    out["findings"] = findings
    return out
