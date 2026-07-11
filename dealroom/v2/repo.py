"""DEALROOM v2 — repository / view-model layer.

Every payload is answer-first (spec §2): the decision-relevant statement first,
evidence one click below. Every figure carries source + as-of where known.
Numbers render German (styleguide: NUMBER then UNIT, comma decimal).
"""

from collections import defaultdict

from v2 import freshness

STAGE_LABELS = {
    "meeting_concluded": "Meeting concluded",
    "valuation_rfi": "Valuation / RFI",
    "indicative_offer": "Indicative offer",
    "loi_negotiation": "LOI negotiation",
    "loi_signed": "LOI signed",
    "due_diligence": "Due diligence",
    "contract_negotiation": "Contract negotiation",
    "closed": "Closed",
    "on_hold": "On hold",
    "dead": "Dead",
}

STAGE_ORDER = list(STAGE_LABELS)

TERM_STATUS_ORDER = {
    "locked": 0,
    "agreed": 1,
    "countered": 2,
    "proposed": 3,
    "superseded": 9,
}


# ------------------------------------------------------------- formatting ---


def _de(num_str: str) -> str:
    return num_str.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_keur(value_k):
    """German convention (styleguide + Roman's usage): 79 → '79 K€';
    750 → '0,75 M€'; 1600 → '1,6 M€'; 5957.5 → '5,96 M€'; 12400 → '12,4 M€'.
    Two decimals below 10 M€ (deal terms need the precision — 5.965 K€ must
    not read as 6,0 M€), one above; a single trailing zero is stripped."""
    if value_k is None:
        return "—"
    from decimal import ROUND_HALF_UP, Decimal

    if abs(value_k) < 100:
        return _de(f"{value_k:,.0f}") + " K€"
    m = Decimal(str(value_k)) / 1000
    q = Decimal("0.01") if abs(m) < 10 else Decimal("0.1")
    s = f"{m.quantize(q, rounding=ROUND_HALF_UP):,}"
    if s.endswith("0") and "." in s and not s.endswith(".00"):
        s = s[:-1]
    elif s.endswith(".00"):
        s = s[:-1]
    return _de(s) + " M€"


def fmt_keur_exact(value_k):
    """Ledger-grade exact display: 5965 → '5.965 K€'; 5957.5 → '5.957,5 K€';
    100.05 → '100,05 K€' (two decimals kept when the value carries them)."""
    if value_k is None:
        return "—"
    if value_k == int(value_k):
        return _de(f"{int(value_k):,d}") + " K€"
    if round(value_k, 1) == value_k:
        return _de(f"{value_k:,.1f}") + " K€"
    return _de(f"{value_k:,.2f}") + " K€"


def fmt_mult(value):
    if value is None:
        return "—"
    return f"{value:.1f}".replace(".", ",") + "x"


def fmt_date(iso):
    if not iso:
        return "—"
    s = str(iso)[:10]
    try:
        y, m, d = s.split("-")
        return f"{d}.{m}.{y[2:]}"
    except ValueError:
        return s


def term_display(t, exact: bool = False) -> str:
    if t["value_num"] is not None:
        if t["unit"] == "K€":
            return fmt_keur_exact(t["value_num"]) if exact else fmt_keur(t["value_num"])
        if t["unit"] == "x":
            return fmt_mult(t["value_num"])
        return str(t["value_num"])
    if t["unit"] == "date":
        return fmt_date(t["value_text"])
    return t["value_text"] or "—"


# ------------------------------------------------------------------ deals ---


def get_deal(conn, code):
    return conn.execute(
        "SELECT * FROM deals WHERE lower(code_name)=lower(?)", (code,)
    ).fetchone()


def portfolio(conn):
    """Full portfolio table — one row per deal, stage-ordered."""
    rows = []
    for d in conn.execute("SELECT * FROM deals").fetchall():
        rows.append(
            {
                "code_name": d["code_name"],
                "company_name": d["company_name"],
                "stage": d["deal_stage"],
                "stage_label": STAGE_LABELS.get(d["deal_stage"], d["deal_stage"]),
                "sector": d["sector"],
                "location": d["location"],
                "rev_m": d["rev_m_override"],
                "ebitda_m": d["ebitda_m_override"],
                "ev_m": d["ev_m_override"],
                "multiple": d["multiple_override"],
                "status_note": d["status_note"],
                "stage_entered_at": d["stage_entered_at"],
            }
        )
    rows.sort(
        key=lambda r: (
            STAGE_ORDER.index(r["stage"]) if r["stage"] in STAGE_ORDER else 99,
            r["code_name"],
        )
    )
    return rows


def _agreed_terms_line(conn, code):
    """One-line terms summary for cards: headline numeric terms, best status."""
    terms = conn.execute(
        "SELECT * FROM deal_terms WHERE code_name=? AND status != 'superseded' "
        "ORDER BY id",
        (code,),
    ).fetchall()
    if not terms:
        return None, []
    best = min(TERM_STATUS_ORDER.get(t["status"], 9) for t in terms)
    status = [k for k, v in TERM_STATUS_ORDER.items() if v == best][0]
    parts = []
    for key in ("purchase_price_upfront", "earnout_max", "ev_total_max"):
        t = next((x for x in terms if x["term_key"] == key), None)
        if t and t["value_num"] is not None:
            short = {
                "purchase_price_upfront": "Sofort",
                "earnout_max": "EO max",
                "ev_total_max": "Gesamt max",
            }[key]
            parts.append(f"{short} {fmt_keur(t['value_num'])}")
    return status, parts


def _next_milestone(conn, code):
    m = conn.execute(
        "SELECT milestone, due_date, owner, note FROM deal_milestones "
        "WHERE code_name=? AND status='open' AND due_date IS NOT NULL "
        "ORDER BY due_date LIMIT 1",
        (code,),
    ).fetchone()
    return dict(m) if m else None


def attention(conn):
    """Landing payload (spec §4 A1): needs_roman / waiting_seller / on_track,
    dead + on_hold collapsed with counts."""
    groups = {"needs_roman": [], "waiting_seller": [], "on_track": []}
    parked = defaultdict(list)
    for d in conn.execute("SELECT * FROM deals").fetchall():
        stage = d["deal_stage"]
        code = d["code_name"]
        if stage not in freshness.ACTIVE_STAGES:
            parked[stage].append(code)
            continue
        flags = freshness.all_flags(conn, d)
        term_status, term_parts = _agreed_terms_line(conn, code)
        nm = _next_milestone(conn, code)
        entry = {
            "code_name": code,
            "company_name": d["company_name"],
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "terms_status": term_status,
            "terms_line": " · ".join(term_parts) if term_parts else None,
            "next_milestone": (
                f"{nm['milestone']} {fmt_date(nm['due_date'])} ({nm['owner']})"
                if nm
                else None
            ),
            "flags": flags,
            "reasons": [f["message"] for f in flags],
        }
        hints = {f["group_hint"] for f in flags}
        if "roman" in hints:
            groups["needs_roman"].append(entry)
        elif "seller" in hints:
            groups["waiting_seller"].append(entry)
        else:
            groups["on_track"].append(entry)
    for key in groups:
        groups[key].sort(key=lambda e: (STAGE_ORDER.index(e["stage"]), e["code_name"]))
    return {
        "groups": groups,
        "parked": {stage: sorted(codes) for stage, codes in sorted(parked.items())},
    }


# ------------------------------------------------------------ answer card ---


def deal_answer(conn, code):
    """Deal page top: stage+evidence, agreed terms, next milestone, risks,
    freshness — one screen (spec §4 A2)."""
    d = get_deal(conn, code)
    if not d:
        return None
    code = d["code_name"]

    last_change = conn.execute(
        "SELECT to_stage, changed_at, evidence FROM deal_stage_history "
        "WHERE code_name=? ORDER BY id DESC LIMIT 1",
        (code,),
    ).fetchone()

    terms = [
        {
            **dict(t),
            "display": term_display(t),
            "display_exact": term_display(t, exact=True),
        }
        for t in conn.execute(
            "SELECT * FROM deal_terms WHERE code_name=? AND status!='superseded' "
            "ORDER BY CASE status WHEN 'locked' THEN 0 WHEN 'agreed' THEN 1 "
            "WHEN 'countered' THEN 2 ELSE 3 END, id",
            (code,),
        )
    ]

    milestones = [
        dict(m)
        for m in conn.execute(
            "SELECT * FROM deal_milestones WHERE code_name=? "
            "ORDER BY status='open' DESC, due_date IS NULL, due_date",
            (code,),
        )
    ]

    risks = (
        [
            dict(r)
            for r in conn.execute(
                "SELECT category, description, risk_level, risk_note, status, advisor "
                "FROM deal_dd_items WHERE domain=? AND risk_level IN ('high','medium') "
                "AND status != 'closed' "
                "ORDER BY CASE risk_level WHEN 'high' THEN 0 ELSE 1 END LIMIT 8",
                (d["domain"],),
            )
        ]
        if d["domain"]
        else []
    )

    # Answer view: ONE row per artifact type — the newest current/final file
    # (several version chains per type exist; the commercial question is
    # "which databook/LOI/RFI is current", not the full registry → M4 CDD tab).
    artifacts_current = [
        dict(a)
        for a in conn.execute(
            "SELECT a.artifact_type, a.file_name, a.file_date, a.version, "
            " a.status, (SELECT COUNT(*) FROM deal_artifacts b "
            "  WHERE b.code_name=a.code_name "
            "  AND b.artifact_type=a.artifact_type) - 1 AS n_others "
            "FROM deal_artifacts a "
            "WHERE a.code_name=? AND a.artifact_type IN "
            "('databook','rfi','slides','model','loi','nbo','spa','fdd_report') "
            "AND a.id = (SELECT b.id FROM deal_artifacts b "
            "  WHERE b.code_name=a.code_name AND b.artifact_type=a.artifact_type "
            "  AND b.status IN ('current','final') "
            "  ORDER BY COALESCE(b.file_date,'0') DESC, COALESCE(b.version,0) DESC, "
            "  b.id DESC LIMIT 1) "
            "ORDER BY COALESCE(a.file_date,'0') DESC",
            (code,),
        )
    ]

    flags = freshness.all_flags(conn, d)

    fin = financial_summary(conn, d)

    return {
        "deal": dict(d),
        "stage_label": STAGE_LABELS.get(d["deal_stage"], d["deal_stage"]),
        "stage_evidence": dict(last_change) if last_change else None,
        "terms": terms,
        "milestones": milestones,
        "next_milestone": _next_milestone(conn, code),
        "risks": risks,
        "artifacts_current": artifacts_current,
        "flags": flags,
        "financials": fin,
    }


def financial_summary(conn, d):
    """Headline figures with source + as-of chips (spec §4 A3).
    Per item: latest ACTUAL-year authoritative extraction (plan years and
    zero/empty rows excluded — DR-BUG-025 class) → deal override fallback."""
    import datetime

    current_year = datetime.date.today().year
    out = []
    domain = d["domain"]
    overrides = {
        "revenue": ("Umsatz", d["rev_m_override"]),
        "ebitda": ("EBITDA (adj.)", d["ebitda_m_override"]),
    }
    for item, label in (("revenue", "Umsatz"), ("ebitda", "EBITDA")):
        row = None
        if domain:
            row = conn.execute(
                "SELECT value_k, fiscal_year, source, extracted_at, is_adjusted "
                "FROM deal_financials WHERE domain=? AND lower(line_item)=? "
                "AND period_type='annual' AND is_authoritative=1 "
                "AND value_k IS NOT NULL AND value_k != 0 AND fiscal_year < ? "
                "ORDER BY fiscal_year DESC, is_adjusted DESC LIMIT 1",
                (domain, item, current_year),
            ).fetchone()
        if row is None and domain:
            # no authoritative row — accept the latest year ONLY if it is a
            # single unambiguous consolidated row (multi-entity years would
            # show a misleading partial figure)
            candidates = conn.execute(
                "SELECT value_k, fiscal_year, source, extracted_at, is_adjusted "
                "FROM deal_financials WHERE domain=? AND lower(line_item)=? "
                "AND period_type='annual' AND value_k IS NOT NULL AND value_k != 0 "
                "AND fiscal_year = (SELECT MAX(fiscal_year) FROM deal_financials "
                " WHERE domain=? AND lower(line_item)=? AND period_type='annual' "
                " AND value_k IS NOT NULL AND value_k != 0 AND fiscal_year < ?) "
                "AND (entity IS NULL OR entity = 'consolidated')",
                (domain, item, domain, item, current_year),
            ).fetchall()
            if len(candidates) == 1:
                row = candidates[0]
        if row:
            out.append(
                {
                    "label": f"{label} {row['fiscal_year']}"
                    + (" (adj.)" if row["is_adjusted"] else ""),
                    "value": fmt_keur(row["value_k"]),
                    "source": row["source"],
                    "as_of": fmt_date(row["extracted_at"]),
                }
            )
        else:
            olabel, oval = overrides[item]
            if oval is not None:
                out.append(
                    {
                        "label": olabel,
                        "value": fmt_keur(oval * 1000),
                        "source": "deals.md (override)",
                        "as_of": None,
                    }
                )
    return out


# --------------------------------------------------------------- timeline ---


def deal_timeline(conn, code):
    """Merged chronology (spec §4 A4): stage changes, artifact versions,
    negotiation rounds, milestones done, data-room scans."""
    d = get_deal(conn, code)
    if not d:
        return []
    code = d["code_name"]
    events = []

    for r in conn.execute(
        "SELECT from_stage, to_stage, changed_at, changed_by, evidence "
        "FROM deal_stage_history WHERE code_name=?",
        (code,),
    ):
        events.append(
            {
                "date": (r["changed_at"] or "")[:10],
                "kind": "stage",
                "title": (
                    f"Stage: {STAGE_LABELS.get(r['from_stage'], r['from_stage'] or 'neu')}"
                    f" → {STAGE_LABELS.get(r['to_stage'], r['to_stage'])}"
                ),
                "detail": r["evidence"],
            }
        )

    for r in conn.execute(
        "SELECT artifact_type, file_name, file_date, registered_at, version "
        "FROM deal_artifacts WHERE code_name=? AND artifact_type IN "
        "('databook','rfi','slides','model','loi','nbo','spa','fdd_report')",
        (code,),
    ):
        events.append(
            {
                "date": (r["file_date"] or r["registered_at"] or "")[:10],
                "kind": "artifact",
                "title": f"{r['artifact_type'].upper()}"
                + (f" v{r['version']}" if r["version"] else ""),
                "detail": r["file_name"],
            }
        )

    if d["domain"]:
        for r in conn.execute(
            "SELECT r.round_no, r.date, r.channel, r.outcome "
            "FROM negotiation_rounds r JOIN negotiation_strategies s "
            "ON s.id=r.strategy_id WHERE s.deal_domain=?",
            (d["domain"],),
        ):
            events.append(
                {
                    "date": (r["date"] or "")[:10],
                    "kind": "round",
                    "title": f"Runde {r['round_no']} ({r['channel'] or '—'})",
                    "detail": r["outcome"],
                }
            )

    for r in conn.execute(
        "SELECT milestone, done_at FROM deal_milestones "
        "WHERE code_name=? AND status='done' AND done_at IS NOT NULL",
        (code,),
    ):
        events.append(
            {
                "date": r["done_at"][:10],
                "kind": "milestone",
                "title": f"Meilenstein erledigt: {r['milestone']}",
                "detail": None,
            }
        )

    for r in conn.execute(
        "SELECT section, scanned_at, delta_json FROM dataroom_scans "
        "WHERE code_name=? AND delta_json IS NOT NULL AND delta_json != '{}'",
        (code,),
    ):
        events.append(
            {
                "date": (r["scanned_at"] or "")[:10],
                "kind": "dataroom",
                "title": f"Datenraum-Delta (Sektion {r['section']})",
                "detail": r["delta_json"],
            }
        )

    events.sort(key=lambda e: e["date"] or "0000", reverse=True)
    return events


# -------------------------------------------------------------- terms API ---


TERM_KEY_ORDER = (
    "purchase_price_upfront",
    "ausschuettung_closing",
    "closing_total",
    "earnout_max",
    "rueckbeteiligung",
    "ev_total_max",
    "ev_indicative",
    "multiple",
    "earnout_mechanics",
    "guarantee",
    "seller_commitment",
    "exclusivity_until",
    "offer_update",
)


def terms_ledger(conn, code=None):
    # commercial reading order: upfront → earn-out → total → mechanics → rest
    order_case = (
        "CASE term_key "
        + " ".join(f"WHEN '{k}' THEN {i}" for i, k in enumerate(TERM_KEY_ORDER))
        + " ELSE 99 END"
    )
    q = (
        "SELECT * FROM deal_terms "
        + ("WHERE lower(code_name)=lower(?) " if code else "")
        + f"ORDER BY code_name, {order_case}, id"
    )
    rows = conn.execute(q, (code,) if code else ()).fetchall()
    return [
        {
            **dict(t),
            "display": term_display(t),
            "display_exact": term_display(t, exact=True),
        }
        for t in rows
    ]
