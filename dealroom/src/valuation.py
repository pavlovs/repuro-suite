"""
DR-M7: Interactive Valuation Model — computation engine + DB layer.

Pure functions (no DB) in the first section; DB integration below.
All monetary values in EUR_K unless noted.
"""

import json
import uuid
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════════════════════
# PURE COMPUTATION FUNCTIONS — no DB, no side effects
# ═══════════════════════════════════════════════════════════════════════════════

# P&L category keys used throughout
PNL_CATEGORIES = [
    "revenue",
    "cogs",
    "personnel",
    "other_opex",
    "other_income",
    "da",
    "ebit",
    "ebitda",
    "interest_expense",
    "interest_income",
    "tax",
    "net_income",
]


def compute_adj_pnl(
    raw_pnl_by_year: dict[str, dict],
    adj_items: list[dict],
    gf_salary: dict | None,
    years: list[str],
) -> dict:
    """Compute adjusted P&L from raw category totals + adjustment items.

    GF salary adjustment auto-generates these items in the personnel category:
      + Aktuelles Gehalt GF:  old_monthly * 12 * benefit_factor  (add back)
      - Adj. Gehalt GF (neu): -new_base_k
      - Adj. Tantieme GF:     -tantieme_k
      - Adj. Sozialabgaben:   -(new_base_k + tantieme_k) * sozial_pct

    Returns dict with keys: summary, kpis, cagr, adjustments_detail, adjustments_total
    """
    # Build adjustment totals per category per year
    adj_by_cat: dict[str, dict[str, float]] = {}
    adj_detail: dict[str, list[dict]] = {}

    # Manual adjustment items
    for item in adj_items or []:
        cat = item.get("category", "opex")
        amounts = item.get("amounts", {})
        if cat not in adj_detail:
            adj_detail[cat] = []
        adj_detail[cat].append(
            {
                "description": item.get("description", ""),
                "comment": item.get("comment", ""),
                "amounts_by_year": {y: amounts.get(y, 0) for y in years},
            }
        )
        for y in years:
            adj_by_cat.setdefault(cat, {}).setdefault(y, 0)
            adj_by_cat[cat][y] += amounts.get(y, 0)

    # GF salary auto-items
    if gf_salary:
        old_m = gf_salary.get("old_monthly_k", 0)
        bf = gf_salary.get("benefit_factor", 1.2)
        new_base = gf_salary.get("new_base_k", 0)
        tantieme = gf_salary.get("tantieme_k", 0)
        sozial_pct = gf_salary.get("sozial_pct", 0.18)

        add_back = old_m * 12 * bf  # positive: add back old salary
        new_salary = -new_base  # negative: subtract new salary
        new_tantieme = -tantieme
        new_sozial = -(new_base + tantieme) * sozial_pct

        gf_items = [
            ("Aktuelles Gehalt GF", add_back),
            ("Adj. Gehalt GF (neu)", new_salary),
            ("Adj. Tantieme GF", new_tantieme),
            ("Adj. Sozialabgaben", new_sozial),
        ]

        cat = "personnel"
        if cat not in adj_detail:
            adj_detail[cat] = []
        for desc, val in gf_items:
            adj_detail[cat].append(
                {
                    "description": desc,
                    "amounts_by_year": {y: round(val, 2) for y in years},
                }
            )
            for y in years:
                adj_by_cat.setdefault(cat, {}).setdefault(y, 0)
                adj_by_cat[cat][y] += val

    # Compute adjusted summary
    # DB sign convention: costs (cogs, personnel, opex) stored as POSITIVE values.
    # Adjustments follow: positive = adds cost, negative = removes cost.
    # Revenue and other_income stored as positive (income).
    summary: dict[str, dict] = {}
    for y in years:
        raw = raw_pnl_by_year.get(y, {})
        rev = raw.get("revenue", 0)
        cogs_raw = raw.get("cogs", 0)
        pex_raw = raw.get("personnel", 0)
        opex_raw = raw.get("other_opex", 0)
        opin_raw = raw.get("other_income", 0)
        da_raw = raw.get("da", 0)

        rev_adj = rev + adj_by_cat.get("revenue", {}).get(y, 0)
        cogs_adj = cogs_raw + adj_by_cat.get("cogs", {}).get(y, 0)
        pex_adj = pex_raw + adj_by_cat.get("personnel", {}).get(y, 0)
        opex_adj = opex_raw + adj_by_cat.get("opex", {}).get(y, 0)
        opin_adj = opin_raw + adj_by_cat.get("opin", {}).get(y, 0)

        gross_margin = rev_adj - cogs_adj
        ebitda_adj = gross_margin - pex_adj - opex_adj + opin_adj
        ebit_adj = ebitda_adj - abs(da_raw)

        summary[y] = {
            "total_sales": round(rev_adj, 2),
            "cogs_adj": round(-cogs_adj, 2),  # display as negative
            "gross_margin": round(gross_margin, 2),
            "pex_adj": round(-pex_adj, 2),  # display as negative
            "opex_adj": round(-opex_adj, 2),  # display as negative
            "opin_adj": round(opin_adj, 2),
            "ebitda_adj": round(ebitda_adj, 2),
            "da": round(-abs(da_raw), 2),
            "ebit_adj": round(ebit_adj, 2),
        }

    # Compute adjustments total per category per year
    adj_total: dict[str, dict] = {}
    for y in years:
        row: dict[str, float] = {}
        total = 0.0
        for cat in ["revenue", "cogs", "personnel", "opex", "opin"]:
            val = adj_by_cat.get(cat, {}).get(y, 0)
            row[cat] = round(val, 2)
            total += val
        row["total"] = round(total, 2)
        adj_total[y] = row

    # KPIs
    kpis = compute_pnl_kpis(summary, years)

    # CAGR
    cagr = {}
    if len(years) >= 2:
        n = len(years) - 1
        first, last = years[0], years[-1]
        for metric in ["total_sales", "gross_margin", "ebitda_adj", "ebit_adj"]:
            cagr[metric] = compute_cagr(
                summary.get(first, {}).get(metric, 0),
                summary.get(last, {}).get(metric, 0),
                n,
            )

    return {
        "summary": summary,
        "kpis": kpis,
        "cagr": cagr,
        "adjustments_detail": adj_detail,
        "adjustments_total": adj_total,
    }


def consolidate_entities(
    entity_pnl: dict[str, dict[str, dict]],
) -> dict[str, dict]:
    """Sum P&L categories across entities per year."""
    consolidated: dict[str, dict] = {}
    for _entity, year_data in entity_pnl.items():
        for year, cats in year_data.items():
            if year not in consolidated:
                consolidated[year] = {}
            for key, val in cats.items():
                consolidated[year][key] = consolidated[year].get(key, 0) + (val or 0)
    # Round
    for year in consolidated:
        for key in consolidated[year]:
            consolidated[year][key] = round(consolidated[year][key], 2)
    return consolidated


def compute_waterfall(
    ebitda_basis: float,
    ebit_basis: float,
    multiple: float,
    net_debt: float,
    permitted_leakage: float,
    cash_at_closing: float,
    vendor_loan: float,
    earnout_anticipated: float,
    earnout_tiers: list[float],
) -> dict:
    """Compute valuation waterfall from inputs.

    Net debt convention: positive = net cash (adds to equity), negative = net debt.
    """
    net_debt = net_debt or 0
    permitted_leakage = permitted_leakage or 0
    cash_at_closing = cash_at_closing or 0
    vendor_loan = vendor_loan or 0
    earnout_anticipated = earnout_anticipated or 0

    super_earnout = 0.0
    if earnout_tiers:
        max_eo = max(earnout_tiers)
        super_earnout = max(max_eo - earnout_anticipated, 0)

    equity_value = cash_at_closing + vendor_loan + earnout_anticipated + super_earnout
    ev_total = equity_value - net_debt - permitted_leakage
    ev_anticipated = ev_total - super_earnout
    ev_at_closing = ev_anticipated - earnout_anticipated

    eq = equity_value if equity_value else 1
    eb = ebitda_basis if ebitda_basis else 1

    return {
        "ev_at_closing": round(ev_at_closing, 2),
        "ev_anticipated": round(ev_anticipated, 2),
        "ev_total": round(ev_total, 2),
        "equity_value": round(equity_value, 2),
        "super_earnout": round(super_earnout, 2),
        "net_debt": round(net_debt, 2),
        "permitted_leakage": round(permitted_leakage, 2),
        "cash_at_closing": round(cash_at_closing, 2),
        "vendor_loan": round(vendor_loan, 2),
        "earnout_anticipated": round(earnout_anticipated, 2),
        "cash_pct": round(cash_at_closing / eq * 100, 1) if eq else 0,
        "vendor_loan_pct": round(vendor_loan / eq * 100, 1) if eq else 0,
        "earnout_pct": round(earnout_anticipated / eq * 100, 1) if eq else 0,
        "multiple_at_closing": round(ev_at_closing / eb, 2) if eb else 0,
        "multiple_anticipated": round(ev_anticipated / eb, 2) if eb else 0,
        "multiple_total": round(ev_total / eb, 2) if eb else 0,
    }


def compute_earnout_matrix(
    ebit_anchor: float,
    step: float,
    tiers: list[float],
    fixed_payment: float,
    net_debt: float,
    da_amount: float,
    base_ebitda: float,
) -> list[dict]:
    """Compute N-column earn-out scenario table.

    Returns list of dicts per scenario column, centered on ebit_anchor.
    """
    n = len(tiers)
    if n == 0:
        return []

    half = n // 2
    results = []
    for i in range(n):
        ebit = ebit_anchor + (i - half) * step
        ebitda = ebit + abs(da_amount)
        earnout = tiers[i]
        kaufpreis = fixed_payment + earnout
        ev = kaufpreis - net_debt
        multiple = round(ev / ebitda, 2) if ebitda else 0
        vs_base_pct = round((ebitda / base_ebitda - 1) * 100, 1) if base_ebitda else 0

        results.append(
            {
                "ebit": round(ebit, 2),
                "ebitda": round(ebitda, 2),
                "earnout": round(earnout, 2),
                "kaufpreis": round(kaufpreis, 2),
                "ev": round(ev, 2),
                "multiple": multiple,
                "vs_base_pct": vs_base_pct,
                "fixed_payment": round(fixed_payment, 2),
            }
        )
    return results


def compute_proforma_ebit(
    raw_pnl_by_year: dict[str, dict],
    gf_salary_k: float,
    nebenkosten_pct: float,
    years: list[str],
) -> list[dict]:
    """Compute pro-forma EBIT bridge: Ergebnis → EBIT → minus new salary.

    Uses raw P&L detail keys: net_income, tax, interest_expense, interest_income,
    other_income (neutraler Ertrag), other_opex (neutraler Aufwand).
    """
    rows = []
    for y in years:
        raw = raw_pnl_by_year.get(y, {})
        ergebnis = raw.get("net_income", 0)
        steuern = abs(raw.get("tax", 0))
        zinsaufwand = abs(raw.get("interest_expense", 0))
        zinsertraege = abs(raw.get("interest_income", 0))
        # Neutral items: other_income is typically positive, other_opex negative
        neutraler_ertrag = abs(raw.get("other_income", 0))
        neutraler_aufwand = abs(raw.get("other_opex", 0))

        ebit_reported = (
            ergebnis
            + steuern
            + zinsaufwand
            - zinsertraege
            + neutraler_ertrag
            - neutraler_aufwand
        )
        nebenkosten = gf_salary_k * nebenkosten_pct
        ebit_proforma = ebit_reported + gf_salary_k + nebenkosten

        rows.append(
            {
                "year": y,
                "ergebnis_nach_steuern": round(ergebnis, 2),
                "steuern": round(steuern, 2),
                "zinsaufwand": round(zinsaufwand, 2),
                "zinsertraege": round(zinsertraege, 2),
                "neutraler_ertrag": round(neutraler_ertrag, 2),
                "neutraler_aufwand": round(neutraler_aufwand, 2),
                "ebit": round(ebit_reported, 2),
                "gf_salary": round(gf_salary_k, 2),
                "nebenkosten": round(nebenkosten, 2),
                "ebit_proforma": round(ebit_proforma, 2),
            }
        )
    return rows


def compute_cagr(start_val: float, end_val: float, n_years: int) -> float | None:
    """CAGR = (end/start)^(1/n) - 1. Returns None if not computable."""
    if n_years <= 0 or not start_val or not end_val:
        return None
    if start_val < 0 or end_val < 0:
        return None
    try:
        return round((end_val / start_val) ** (1 / n_years) - 1, 4)
    except (ZeroDivisionError, ValueError):
        return None


def compute_pnl_kpis(summary: dict[str, dict], years: list[str]) -> dict[str, dict]:
    """Compute topline growth, margins per year."""
    kpis: dict[str, dict] = {}
    prev_rev = None
    for y in years:
        s = summary.get(y, {})
        rev = s.get("total_sales", 0)
        growth = None
        if prev_rev and prev_rev != 0:
            growth = round((rev / prev_rev - 1) * 100, 1)
        prev_rev = rev

        rev_safe = rev if rev else 1
        kpis[y] = {
            "topline_growth": growth,
            "gross_margin_pct": round(s.get("gross_margin", 0) / rev_safe * 100, 1)
            if rev
            else None,
            "pex_pct": round(s.get("pex_adj", 0) / rev_safe * 100, 1) if rev else None,
            "opex_pct": round(s.get("opex_adj", 0) / rev_safe * 100, 1)
            if rev
            else None,
            "ebitda_margin_pct": round(s.get("ebitda_adj", 0) / rev_safe * 100, 1)
            if rev
            else None,
            "ebit_margin_pct": round(s.get("ebit_adj", 0) / rev_safe * 100, 1)
            if rev
            else None,
        }
    return kpis


# ═══════════════════════════════════════════════════════════════════════════════
# DB INTEGRATION LAYER
# ═══════════════════════════════════════════════════════════════════════════════


def load_model_params(conn, domain: str, scenario: str = "base") -> dict | None:
    """Load deal_model_params row as dict. Returns None if not found."""
    row = conn.execute(
        "SELECT * FROM deal_model_params WHERE domain = ? AND scenario_name = ?",
        (domain, scenario),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    # Parse JSON fields
    for jf in [
        "entities_json",
        "adj_items_json",
        "earnout_tiers_json",
        "net_debt_items_json",
        "comments_json",
    ]:
        if d.get(jf):
            try:
                d[jf] = json.loads(d[jf])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def save_model_params(conn, domain: str, params: dict, scenario: str = "base") -> None:
    """Upsert deal_model_params row."""
    now = datetime.now(timezone.utc).isoformat()

    # Serialize JSON fields
    save_params = dict(params)
    for jf in [
        "entities_json",
        "adj_items_json",
        "earnout_tiers_json",
        "net_debt_items_json",
        "comments_json",
    ]:
        if jf in save_params and not isinstance(save_params[jf], str):
            save_params[jf] = json.dumps(save_params[jf], ensure_ascii=False)

    # Check if exists
    existing = conn.execute(
        "SELECT id FROM deal_model_params WHERE domain = ? AND scenario_name = ?",
        (domain, scenario),
    ).fetchone()

    columns = [
        "entities_json",
        "adj_items_json",
        "gf_old_salary_monthly_k",
        "gf_new_base_k",
        "gf_tantieme_k",
        "gf_sozialabgaben_pct",
        "gf_benefit_factor",
        "ebitda_basis_override",
        "ebit_basis_override",
        "ebitda_basis_label",
        "da_amount",
        "multiple",
        "net_debt",
        "permitted_leakage",
        "cash_at_closing",
        "vendor_loan",
        "earnout_anticipated",
        "earnout_ebit_anchor",
        "earnout_step",
        "earnout_tiers_json",
        "proforma_gf_salary_k",
        "proforma_nebenkosten_pct",
        "net_debt_items_json",
        "projection_revenue",
        "projection_growth",
        "comments_json",
    ]

    if existing:
        sets = ", ".join(f"{c} = ?" for c in columns)
        vals = [save_params.get(c) for c in columns]
        vals.append(now)
        vals.append(domain)
        vals.append(scenario)
        conn.execute(
            f"UPDATE deal_model_params SET {sets}, updated_at = ? WHERE domain = ? AND scenario_name = ?",
            vals,
        )
    else:
        row_id = str(uuid.uuid4())
        all_cols = ["id", "domain", "scenario_name"] + columns + ["created_at"]
        placeholders = ", ".join(["?"] * len(all_cols))
        vals = (
            [row_id, domain, scenario] + [save_params.get(c) for c in columns] + [now]
        )
        conn.execute(
            f"INSERT INTO deal_model_params ({', '.join(all_cols)}) VALUES ({placeholders})",
            vals,
        )
    conn.commit()


def _dedup_pnl_rows(rows: list) -> list:
    """Deduplicate P&L rows: keep one value per (fiscal_year, key, source_entity).

    Source entity = unique source prefix pattern. When multiple source files
    cover the same entity/year/key (e.g., Gewinn-und-Verlustrechnung AND
    Kontennachweis), keep only the first one encountered.
    """
    seen: set[tuple] = set()
    deduped = []
    for r in rows:
        yr = r["fiscal_year"]
        key = r["key"]
        src = r["source"] or ""
        # Extract entity identifier: e.g., "67858_323_2022" from source filename
        # Take first 3 underscore-separated parts as entity signature
        parts = src.split("_")
        entity_sig = "_".join(parts[:3]) if len(parts) >= 3 else src[:20]
        dedup_key = (yr, key, entity_sig)
        if dedup_key not in seen:
            seen.add(dedup_key)
            deduped.append(r)
    return deduped


def load_raw_pnl(conn, domain: str, entities: list[dict] | None = None) -> dict:
    """Load raw P&L data from deal_financials (statement='pnl', is_adjusted=0).

    If entities is None: returns {year_str: {key: value}}
    If entities provided: returns {entity_name: {year_str: {key: value}}}
    Entity matching: source filename contains entity's source_pattern.
    Deduplicates across source file types (GuV vs Kontennachweis).
    """
    rows = conn.execute(
        """SELECT fiscal_year, line_item AS key, value_k AS value_num, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 0
             AND period_type = 'annual'
             AND value_k IS NOT NULL AND is_authoritative = 1
           ORDER BY fiscal_year, line_item, source""",
        (domain,),
    ).fetchall()

    if not rows:
        rows = conn.execute(
            """SELECT fiscal_year, line_item AS key, value_k AS value_num, source
               FROM deal_financials
               WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 0
                 AND period_type = 'annual'
                 AND value_k IS NOT NULL
               ORDER BY fiscal_year, line_item, source""",
            (domain,),
        ).fetchall()

    rows = _dedup_pnl_rows(rows)

    if entities:
        result: dict[str, dict[str, dict]] = {}
        for ent in entities:
            result[ent["name"]] = {}

        for r in rows:
            yr = str(r["fiscal_year"])
            key = r["key"]
            val = r["value_num"]
            src = r["source"] or ""

            assigned = False
            for ent in entities:
                pat = ent.get("source_pattern", "")
                if pat and pat in src:
                    result[ent["name"]].setdefault(yr, {})[key] = val
                    assigned = True
                    break
            if not assigned:
                result[entities[0]["name"]].setdefault(yr, {})[key] = val
        return result
    else:
        # Single entity: aggregate by summing across entities per year/key
        agg: dict[str, dict[str, float]] = {}
        for r in rows:
            yr = str(r["fiscal_year"])
            key = r["key"]
            val = r["value_num"]
            agg.setdefault(yr, {}).setdefault(key, 0)
            agg[yr][key] += val
        for yr in agg:
            for key in agg[yr]:
                agg[yr][key] = round(agg[yr][key], 2)
        return agg


def load_raw_pnl_detail(conn, domain: str) -> dict[str, dict]:
    """Load raw P&L data needed for pro-forma EBIT bridge.

    Returns {year_str: {key: value}} with all raw P&L keys summed across entities
    (deduplicated across source file types).
    """
    rows = conn.execute(
        """SELECT fiscal_year, line_item AS key, value_k AS value_num, source
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 0
             AND period_type = 'annual'
             AND value_k IS NOT NULL
           ORDER BY fiscal_year, line_item, source""",
        (domain,),
    ).fetchall()

    rows = _dedup_pnl_rows(rows)

    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        yr = str(r["fiscal_year"])
        key = r["key"]
        val = r["value_num"]
        agg.setdefault(yr, {}).setdefault(key, 0)
        agg[yr][key] += val
    for yr in agg:
        for key in agg[yr]:
            agg[yr][key] = round(agg[yr][key], 2)
    return agg


def _auto_populate_defaults(conn, domain: str) -> dict:
    """Build default model params from existing deal_financials and deal_valuations."""
    params: dict = {}

    # Valuation input from model (DR-M5) — bewertung statement, adjusted
    vi_rows = conn.execute(
        """SELECT line_item AS key, value_k AS value_num FROM deal_financials
           WHERE domain = ? AND statement = 'bewertung' AND is_adjusted = 1
             AND value_k IS NOT NULL""",
        (domain,),
    ).fetchall()
    vi = {r["key"]: r["value_num"] for r in vi_rows}

    if vi.get("ebitda_adj"):
        params["ebitda_basis_override"] = vi["ebitda_adj"]
    if vi.get("ebit_adj"):
        params["ebit_basis_override"] = vi["ebit_adj"]
    if vi.get("net_cash_debt"):
        params["net_debt"] = vi["net_cash_debt"]

    # From deal_valuations
    val_row = conn.execute(
        """SELECT * FROM deal_valuations WHERE domain = ?
           ORDER BY valuation_date DESC LIMIT 1""",
        (domain,),
    ).fetchone()
    if val_row:
        vr = dict(val_row)
        if vr.get("ebitda_basis"):
            params.setdefault("ebitda_basis_override", vr["ebitda_basis"])
        if vr.get("ebitda_basis_label"):
            params["ebitda_basis_label"] = vr["ebitda_basis_label"]
        if vr.get("multiple_mid"):
            params["multiple"] = vr["multiple_mid"]
        if vr.get("cash_at_closing"):
            params["cash_at_closing"] = vr["cash_at_closing"]
        if vr.get("rueckbeteiligung"):
            params["vendor_loan"] = vr["rueckbeteiligung"]
        if vr.get("earnout_max"):
            params["earnout_anticipated"] = vr["earnout_max"]

    # Fallback defaults
    params.setdefault("multiple", 4.0)
    params.setdefault("net_debt", 0)
    params.setdefault("cash_at_closing", 0)
    params.setdefault("vendor_loan", 0)
    params.setdefault("earnout_anticipated", 0)
    params.setdefault("earnout_step", 25)
    params.setdefault("gf_sozialabgaben_pct", 0.18)
    params.setdefault("gf_benefit_factor", 1.2)
    params.setdefault("proforma_nebenkosten_pct", 0.17)

    return params


def build_model_context(conn, domain: str, scenario: str = "base") -> dict:
    """Master function: assemble all data, run all computations, return complete context.

    Returns dict with: params, years, raw_pnl, adj_pnl, waterfall, earnout_matrix,
    proforma, offer_history, entities, entity_pnl
    """
    # 1. Load or auto-populate params
    params = load_model_params(conn, domain, scenario)
    if not params:
        params = _auto_populate_defaults(conn, domain)
        params["domain"] = domain
        params["scenario_name"] = scenario

    # 2. Load raw P&L
    entities = params.get("entities_json")
    if isinstance(entities, str):
        try:
            entities = json.loads(entities)
        except (json.JSONDecodeError, TypeError):
            entities = None

    entity_pnl = None
    if entities:
        entity_pnl = load_raw_pnl(conn, domain, entities)
        raw_pnl = consolidate_entities(entity_pnl)
    else:
        raw_pnl = load_raw_pnl(conn, domain)

    # Also try adjusted P&L from deal_financials as fallback/override
    vi_pnl_rows = conn.execute(
        """SELECT fiscal_year, line_item AS key, value_k AS value_num
           FROM deal_financials
           WHERE domain = ? AND statement = 'pnl' AND is_adjusted = 1
             AND period_type = 'annual' AND value_k IS NOT NULL
           ORDER BY fiscal_year""",
        (domain,),
    ).fetchall()
    vi_pnl: dict[str, dict] = {}
    for r in vi_pnl_rows:
        yr = str(r["fiscal_year"])
        vi_pnl.setdefault(yr, {})[r["key"]] = r["value_num"]

    # Merge vi_pnl into raw_pnl — model data OVERRIDES BWA sums.
    # vi_pnl comes from DR-M5 Excel model (is_adjusted=1) and is the valuation
    # basis. BWA sums can be inflated by multi-entity duplicates, so model wins.
    _VI_KEY_MAP = {
        "ebitda_adj": "ebitda",
        "ebit_adj": "ebit",
        "da_adj": "da",
        "cogs_adj": "cogs",
        "personnel_adj": "personnel",
        "other_opex_adj": "other_opex",
        "other_income_adj": "other_income",
        "net_income_adj": "net_income",
    }
    for yr, vi_data in vi_pnl.items():
        if yr not in raw_pnl:
            raw_pnl[yr] = {}
        for k, v in vi_data.items():
            mapped = _VI_KEY_MAP.get(k, k)
            raw_pnl[yr][mapped] = v

    # Determine years — union of raw and valuation_input years
    all_years = sorted(set(list(raw_pnl.keys()) + list(vi_pnl.keys())))
    if not all_years:
        all_years = []

    # 3. Build GF salary dict
    gf_salary = None
    if params.get("gf_old_salary_monthly_k"):
        gf_salary = {
            "old_monthly_k": params["gf_old_salary_monthly_k"],
            "benefit_factor": params.get("gf_benefit_factor", 1.2),
            "new_base_k": params.get("gf_new_base_k", 0),
            "tantieme_k": params.get("gf_tantieme_k", 0),
            "sozial_pct": params.get("gf_sozialabgaben_pct", 0.18),
        }

    # Parse adj_items
    adj_items = params.get("adj_items_json")
    if isinstance(adj_items, str):
        try:
            adj_items = json.loads(adj_items)
        except (json.JSONDecodeError, TypeError):
            adj_items = []
    adj_items = adj_items or []

    # 4. Compute adjusted P&L
    adj_pnl = compute_adj_pnl(raw_pnl, adj_items, gf_salary, all_years)

    # 5. Determine EBITDA/EBIT basis for valuation
    ebitda_basis = params.get("ebitda_basis_override", 0)
    ebit_basis = params.get("ebit_basis_override", 0)
    da_amount = params.get("da_amount", 0)

    # If no override, use latest year adjusted values
    if not ebitda_basis and all_years:
        latest = all_years[-1]
        s = adj_pnl["summary"].get(latest, {})
        ebitda_basis = s.get("ebitda_adj", 0)
        ebit_basis = s.get("ebit_adj", 0)
        if not da_amount:
            da_amount = (
                abs(ebitda_basis - ebit_basis) if ebitda_basis and ebit_basis else 0
            )

    if not ebit_basis and ebitda_basis and da_amount:
        ebit_basis = ebitda_basis - abs(da_amount)

    # 6. Compute waterfall
    earnout_tiers = params.get("earnout_tiers_json")
    if isinstance(earnout_tiers, str):
        try:
            earnout_tiers = json.loads(earnout_tiers)
        except (json.JSONDecodeError, TypeError):
            earnout_tiers = []
    earnout_tiers = earnout_tiers or []

    waterfall = compute_waterfall(
        ebitda_basis=ebitda_basis,
        ebit_basis=ebit_basis,
        multiple=params.get("multiple", 4.0),
        net_debt=params.get("net_debt", 0),
        permitted_leakage=params.get("permitted_leakage", 0),
        cash_at_closing=params.get("cash_at_closing", 0),
        vendor_loan=params.get("vendor_loan", 0),
        earnout_anticipated=params.get("earnout_anticipated", 0),
        earnout_tiers=earnout_tiers,
    )

    # 7. Compute earn-out matrix
    ebit_anchor = params.get("earnout_ebit_anchor", ebit_basis)
    fixed_payment = (params.get("cash_at_closing", 0) or 0) + (
        params.get("vendor_loan", 0) or 0
    )

    earnout_matrix = compute_earnout_matrix(
        ebit_anchor=ebit_anchor or 0,
        step=params.get("earnout_step", 25) or 25,
        tiers=earnout_tiers,
        fixed_payment=fixed_payment,
        net_debt=params.get("net_debt", 0) or 0,
        da_amount=da_amount or 0,
        base_ebitda=ebitda_basis or 0,
    )

    # 8. Compute pro-forma EBIT bridge
    raw_detail = load_raw_pnl_detail(conn, domain)
    proforma_salary = params.get("proforma_gf_salary_k", 0) or 0
    proforma_nk = params.get("proforma_nebenkosten_pct") or 0.17
    proforma = compute_proforma_ebit(
        raw_detail, proforma_salary, proforma_nk, all_years
    )

    # 9. Offer history from deal_valuations
    offer_rows = conn.execute(
        """SELECT * FROM deal_valuations WHERE domain = ?
           ORDER BY valuation_date DESC""",
        (domain,),
    ).fetchall()
    offer_history = [dict(r) for r in offer_rows]

    # 10. Build context
    # Serialize params for JSON output — keep parsed versions
    params_clean = {k: v for k, v in params.items() if k != "id"}

    return {
        "params": params_clean,
        "years": all_years,
        "raw_pnl": raw_pnl,
        "adj_pnl": adj_pnl,
        "waterfall": waterfall,
        "earnout_matrix": earnout_matrix,
        "proforma": proforma,
        "offer_history": offer_history,
        "entities": entities,
        "entity_pnl": entity_pnl,
        "ebitda_basis": ebitda_basis,
        "ebit_basis": ebit_basis,
        "da_amount": da_amount,
    }
