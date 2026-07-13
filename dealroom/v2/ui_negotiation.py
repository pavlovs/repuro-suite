"""DEALROOM v2 — Screen 2: Offer & Negotiation (deal page, owner-only).

Rebuild after the 13.07 rejection, in the v1 dashboard visual language
(Screen 1 = v1 Portfolio ported verbatim; this screen follows its DNA:
Inter, #f0f2f5 canvas, teal section titles, teal table-header bars, pill
badges, de-DE numbers). Layout realizes the v1 wireframe
(src/templates/sections/offer-negotiation.js, DR-M8b) with REAL data:

  summary band -> offer round ledger (bucket columns per LOI structure)
  -> issue list (our vs. their position) -> process (milestones/open items)
  -> rounds timeline -> strategy depth (goals, objections, lessons, memo).

Data: workspace.negotiation_payload (negotiation_offers/_offer_terms via
negotiate_ops.py, deal_terms ledger, §12 tables). GDPR: whole page is
owner-gated (negotiation spec §6.9) — profile claims stay off this page.
English chrome (v1 convention); German deal vocabulary (Sofort, EO,
GF-Gehalt) is domain language; units live in headers, never in cells.
"""

from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.responses import HTMLResponse

from v2 import repo, workspace
from v2.uikit import esc

# canonical bucket columns (SPEC-OFFER-NEGOTIATION-TAB §3); a column renders
# only when at least one offer event carries the key
OFFER_BUCKETS = [
    ("purchase_price_upfront", "Sofort", "K€"),
    ("earnout_max", "EO max", "K€"),
    ("earnout_threshold", "EO-Schwelle", "K€"),
    ("earnout_multiple", "EO-Mult.", "x"),
    ("rueckbeteiligung", "RB", "K€"),
    ("gf_salary", "GF-Gehalt", "K€ p.a."),
    ("ev_total_max", "Gesamt max", "K€"),
    ("multiple", "Multiple", "x"),
]

# v1 statusBadge palette (offer-negotiation.js / portfolio.js)
STATUS_BADGE = {
    "sent": "b-blue",
    "received": "b-amber",
    "accepted": "b-green",
    "signed": "b-green",
    "superseded": "b-gray",
    "withdrawn": "b-gray",
}
PRIO_BADGE = {"high": "b-red", "med": "b-amber", "low": "b-gray"}
STAGE_COLORS = {
    "meeting_concluded": ("#f59e0b", "#000"),
    "valuation_rfi": ("#3b82f6", "#fff"),
    "indicative_offer": ("#6366f1", "#fff"),
    "loi_signed": ("#8b5cf6", "#fff"),
    "due_diligence": ("#059669", "#fff"),
    "contract_negotiation": ("#0d9488", "#fff"),
    "closed": ("#065f46", "#fff"),
    "on_hold": ("#6b7280", "#fff"),
    "dead": ("#ef4444", "#fff"),
}

CSS = """
:root{--accent:#0891B2;--accent-bg:#e0f5fa;--accent-border:#b0dff0;
--bg:#f0f2f5;--card:#fff;--border:#e5e7eb;--border-light:#e9ecef;
--text:#111827;--muted:#6b7280;--red:#b91c1c}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
background:var(--bg);color:var(--text);font-size:13px;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 60px}
.strip{background:var(--card);border-bottom:1px solid var(--border);padding:10px 20px;
display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.strip .code{font-size:15px;font-weight:700}
.strip .company{font-size:13px;color:var(--muted)}
.strip .meta{margin-left:auto;font-size:11px;color:var(--muted)}
.stage-badge{padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600}
.badge{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap}
.b-blue{background:#dbeafe;color:#1d4ed8}.b-amber{background:#fef3c7;color:#92400e}
.b-green{background:#d1fae5;color:#065f46}.b-gray{background:#f3f4f6;color:#6b7280}
.b-red{background:#fee2e2;color:#b91c1c}.b-teal{background:#e0f5fa;color:#0891B2}
.secthead{font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;
letter-spacing:.5px;margin:22px 0 8px}
.pagetitle{font-size:13px;font-weight:700;color:var(--accent);text-transform:uppercase;
letter-spacing:.6px;border-bottom:2px solid var(--accent);padding-bottom:6px;margin:18px 0 16px}
.summary{background:var(--accent-bg);border:1px solid var(--accent-border);border-radius:6px;
padding:14px 18px;display:flex;gap:32px;flex-wrap:wrap;align-items:flex-start}
.fig .l{font-size:11px;color:var(--muted);margin-bottom:2px}
.fig .v{font-size:22px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}
.fig .v.plain{color:#374151}.fig .v.alert{color:var(--red)}.fig .v.badge-line{font-size:14px}
.fig .n{font-size:11px;color:var(--muted);margin-top:3px;max-width:260px}
.tblwrap{overflow-x:auto;background:var(--card);border:1px solid var(--border);border-radius:6px}
table{border-collapse:collapse;width:100%}
th{background:var(--accent);color:#fff;padding:6px 10px;font-size:11px;font-weight:700;
text-align:left;white-space:nowrap}
th.r{text-align:right}
td{padding:6px 10px;font-size:12px;border-bottom:1px solid var(--border-light);
vertical-align:top;text-align:left}
td.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr:last-child td{border-bottom:none}
tr.latest td{background:#f0f9ff;font-weight:600}
tr.agreed td{background:#f0fdf4}
tr.resolved td{opacity:.6}
td .strike{text-decoration:line-through;color:var(--muted)}
.subline{display:block;font-size:11px;color:var(--muted);font-weight:400;margin-top:2px}
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:860px){.twocol{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:12px 14px}
.panel .ptitle{font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;
letter-spacing:.5px;margin-bottom:8px}
.kvrow{display:flex;justify-content:space-between;gap:12px;padding:6px 0;
border-bottom:1px solid var(--border-light);align-items:baseline}
.kvrow:last-child{border-bottom:none}
.kvrow .k{font-size:12px}.kvrow .k .subline{margin-top:1px}
.kvrow .v{font-size:12px;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
.kvrow .v.overdue{color:var(--red)}
.rounds{background:var(--card);border:1px solid var(--border);border-radius:6px}
.round{padding:10px 14px;border-top:1px solid var(--border-light)}
.round:first-child{border-top:none}
.round .rdate{font-size:11px;font-weight:700;color:var(--accent);margin-bottom:3px}
.round .rtitle{font-size:12px;font-weight:600;margin-bottom:3px}
.round .rdetail{font-size:12px;color:#374151;line-height:1.5}
.round .rdetail b{color:var(--muted);font-weight:600}
.flagbox{border:1px solid #fde68a;background:#fffbeb;border-radius:4px;padding:8px 12px;
font-size:12px;color:#92400e;margin-top:12px}
.flagbox.alert{border-color:#fecdd3;background:#fff1f4;color:#b91c1c}
.flagbox ul{margin:4px 0 0 18px}
.tiles3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
@media(max-width:860px){.tiles3{grid-template-columns:1fr}}
.panel p,.panel li{font-size:12px;line-height:1.5;color:#374151}
.panel ul{padding-left:18px;margin:2px 0}
.panel h3,.panel h4{font-size:12px;margin:8px 0 3px;color:var(--text)}
.memo{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:14px 18px}
.memo p,.memo li{font-size:12px;line-height:1.55;color:#374151;margin-bottom:4px}
.memo ul{padding-left:18px;margin-bottom:6px}
.memo h3{font-size:13px;margin:12px 0 4px}.memo h4{font-size:12px;margin:10px 0 3px}
.empty{color:var(--muted);font-size:12px;font-style:italic;padding:10px 0}
.lesson{display:flex;gap:10px;padding:8px 12px;border-radius:4px;border:1px solid var(--border);
background:var(--card);margin-bottom:6px;font-size:12px;align-items:baseline}
.lesson.weak{border-left:3px solid #e11d48}.lesson.strong{border-left:3px solid #0891B2}
.lesson .ref{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;white-space:nowrap}
"""


def _md_lite(md: str) -> str:
    out, in_ul = [], False
    for raw in (md or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith(("- ", "* ")):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(stripped[2:])}</li>")
            continue
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if stripped.startswith("### "):
            out.append(f"<h4>{_inline(stripped[4:])}</h4>")
        elif stripped.startswith(("## ", "# ")):
            out.append(f"<h3>{_inline(stripped.lstrip('#').strip())}</h3>")
        elif stripped in ("---", "***"):
            out.append("<hr>")
        elif stripped:
            out.append(f"<p>{_inline(stripped)}</p>")
    if in_ul:
        out.append("</ul>")
    return "".join(out)


def _inline(text: str) -> str:
    s = esc(text)
    while "**" in s:
        i = s.find("**")
        j = s.find("**", i + 2)
        if j < 0:
            break
        s = s[:i] + "<b>" + s[i + 2 : j] + "</b>" + s[j + 2 :]
    return s


def _badge(text: str, cls: str) -> str:
    return f'<span class="badge {cls}">{esc(text)}</span>'


def _num_cell(term: dict | None) -> str:
    if term is None:
        return '<td class="r">—</td>'
    if term["value_num"] is not None:
        return f'<td class="r">{esc(repo.fmt_num_bare(term["value_num"]))}</td>'
    return f"<td>{esc(term['value_text'] or '—')}</td>"


def _offer_total(offer: dict) -> float | None:
    t = next(
        (t for t in offer["terms"] if t["term_key"] == "ev_total_max"),
        None,
    )
    return t["value_num"] if t else None


def _summary(payload: dict) -> str:
    s = payload["strategy"]
    terms_by_key = {t["term_key"]: t for t in payload["locked_terms"]}
    offers = payload["offers"]

    total_t = terms_by_key.get("ev_total_max")
    total = total_t["value_num"] if total_t else None
    pkg_label = "Current package"
    struct_bits = []
    if total_t:
        pkg_label = (
            "Locked package" if total_t["status"] == "locked" else "Agreed package"
        )
        for key, word in (
            ("purchase_price_upfront", "Sofort"),
            ("earnout_max", "EO max"),
        ):
            t = terms_by_key.get(key)
            if t and t["value_num"] is not None:
                struct_bits.append(f"{repo.fmt_keur(t['value_num'])} {word}")
    elif offers:
        # no agreement-grade ledger entry yet — figure AND structure both come
        # from our latest package (never mix sources in one block)
        ours = [o for o in offers if o["side"] == "ours"]
        if ours:
            o_terms = {t["term_key"]: t for t in ours[-1]["terms"]}
            pkg_label = f"Our last offer ({repo.fmt_date(ours[-1]['date'])})"
            total = _offer_total(ours[-1])
            if total is None:
                pp = o_terms.get("purchase_price_upfront")
                if pp and pp["value_num"] is not None:
                    total = pp["value_num"]
                    pkg_label += " — Sofort"
            for key, word in (
                ("purchase_price_upfront", "Sofort"),
                ("earnout_max", "EO max"),
            ):
                t = o_terms.get(key)
                if t and t["value_num"] is not None:
                    struct_bits.append(f"{repo.fmt_keur(t['value_num'])} {word}")

    figs = [
        f'<div class="fig"><div class="l">{esc(pkg_label)}</div>'
        f'<div class="v">{esc(repo.fmt_keur(total)) if total is not None else "—"}</div>'
        f'<div class="n">{esc(" + ".join(struct_bits))}</div></div>'
    ]

    # seller ask + gap — only for a LIVE counter on the table (an accepted
    # theirs-event IS the package, not an ask)
    theirs = [o for o in offers if o["side"] == "theirs" and o["status"] == "received"]
    ask = _offer_total(theirs[-1]) if theirs else None
    if ask is not None and total is not None:
        gap = ask - total
        gap_pct = f" ({gap / total * 100:,.0f}%)".replace(",", ".") if total else ""
        figs.append(
            f'<div class="fig"><div class="l">Seller ask '
            f"({repo.fmt_date(theirs[-1]['date'])})</div>"
            f'<div class="v plain">{esc(repo.fmt_keur(ask))}</div></div>'
        )
        if abs(gap) > 0.01:
            figs.append(
                f'<div class="fig"><div class="l">Gap</div>'
                f'<div class="v alert">{esc(repo.fmt_keur(gap))}{esc(gap_pct)}</div>'
                "</div>"
            )

    n_issues = sum(1 for p in payload["positions"] if p["status"] == "open")
    n_items = sum(1 for i in payload["open_items"] if i["status"] == "open")
    status_note = (
        "new strategy pending (/repuro:negotiate) · "
        if s["status"] == "superseded"
        else ""
    )
    figs.append(
        f'<div class="fig"><div class="l">Status</div>'
        f'<div class="v badge-line">{_badge(s["status"], "b-teal")}</div>'
        f'<div class="n">{status_note}{n_issues} open issues · {n_items} open items · '
        f"Trail {payload['trail']['read']}/{payload['trail']['total']} read</div></div>"
    )

    nm = payload.get("next_milestone")
    if nm:
        figs.append(
            f'<div class="fig"><div class="l">Next milestone</div>'
            f'<div class="v plain">{repo.fmt_date(nm["date"])}</div>'
            f'<div class="n">{esc(nm["label"])}</div></div>'
        )

    v = payload["validation"]
    gate = ""
    if v["ran"] and v["passed"]:
        gate = _badge("Validator PASS", "b-green")
    elif v["ran"]:
        gate = _badge(f"Validator FAIL ({len(v['findings'])})", "b-red")
    counter = ", ".join(
        f"{esc(p['name'])} ({esc(p['role'])})" for p in payload["parties"]
    ) or (
        f"{esc(s['stakeholder_name'])}"
        + (f" ({esc(s['stakeholder_company'])})" if s["stakeholder_company"] else "")
    )
    figs.append(
        f'<div class="fig"><div class="l">Counterparty</div>'
        f'<div class="v badge-line plain" style="font-size:13px">{counter}</div>'
        f'<div class="n">{gate}</div></div>'
    )
    return f'<div class="summary">{"".join(figs)}</div>'


def _offer_ledger(offers: list[dict]) -> str:
    if not offers:
        return (
            '<p class="empty">No offer events recorded yet — '
            "<code>negotiate_ops.py offer add</code> logs them.</p>"
        )
    present = [
        (k, lab, unit)
        for k, lab, unit in OFFER_BUCKETS
        if any(t["term_key"] == k for o in offers for t in o["terms"])
    ]
    head = "".join(
        f'<th class="r">{esc(lab)} ({esc(unit)})</th>' for _, lab, unit in present
    )
    live_ids = [o["id"] for o in offers if o["status"] in ("sent", "received")]
    latest_live = live_ids[-1] if live_ids else None
    rows = []
    for o in offers:
        terms = {t["term_key"]: t for t in o["terms"]}
        cells = "".join(_num_cell(terms.get(k)) for k, _, _ in present)
        sub_bits = []
        others = [t for t in o["terms"] if t["term_key"] == "other"]
        if others:
            sub_bits.append(
                " · ".join(
                    f"{esc(t['label'] or 'Weitere')}: "
                    f"{esc(t['value_text'] or repo.fmt_num_bare(t['value_num']))}"
                    for t in others
                )
            )
        if o["note"]:
            sub_bits.append(esc(o["note"]))
        if o["source_doc"]:
            sub_bits.append(f"Quelle: {esc(o['source_doc'])}")
        sub = f'<span class="subline">{" — ".join(sub_bits)}</span>' if sub_bits else ""
        cls = []
        if o["status"] in ("accepted", "signed"):
            cls.append("agreed")
        if o["id"] == latest_live:
            cls.append("latest")
        side = (
            _badge("Us", "b-teal")
            if o["side"] == "ours"
            else _badge("Seller", "b-gray")
        )
        rows.append(
            f'<tr class="{" ".join(cls)}">'
            f"<td>{repo.fmt_date(o['date'])}</td>"
            f"<td>{side}</td>"
            f"<td>{esc(o['label'])}{sub}</td>"
            f"{cells}"
            f"<td>{_badge(o['status'], STATUS_BADGE.get(o['status'], 'b-gray'))}</td>"
            "</tr>"
        )
    return (
        '<div class="tblwrap"><table><thead><tr>'
        "<th>Date</th><th>Side</th><th>Package</th>" + head + "<th>Status</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _issue_list(positions: list[dict]) -> str:
    if not positions:
        return '<p class="empty">No positions recorded.</p>'
    rows = []
    for n, po in enumerate(positions, 1):
        resolved = po["status"] not in ("open", "escalated")
        walk = (
            f'<span class="subline">Walk-away: {esc(po["walk_away"])}</span>'
            if po["walk_away"]
            else ""
        )
        esc_flag = _badge("escalation", "b-red") if po["escalation_required"] else ""
        confirm = (
            _badge("Roman ✓", "b-green")
            if po["roman_confirmed"]
            else _badge("unconfirmed", "b-amber")
        )
        prio = po.get("prio")
        rows.append(
            f'<tr class="{"resolved" if resolved else ""}">'
            f'<td style="color:var(--muted)">{n}</td>'
            f'<td><span class="{"strike" if resolved else ""}">{esc(po["term"])}'
            f"</span> {esc_flag}</td>"
            f"<td>{esc(po['preferred'])}{walk}</td>"
            f"<td>{esc(po.get('their_position') or '—')}</td>"
            f"<td>{_badge(prio, PRIO_BADGE.get(prio, 'b-gray')) if prio else '—'}</td>"
            f"<td>{_badge(po['status'], 'b-blue' if po['status'] == 'open' else 'b-green')}</td>"
            f"<td>{confirm}</td></tr>"
        )
    return (
        '<div class="tblwrap"><table><thead><tr>'
        "<th>#</th><th>Issue</th><th>Our position</th><th>Their position</th>"
        "<th>Prio</th><th>Status</th><th>Sign-off</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _process(payload: dict) -> str:
    ms_rows = []
    for m in payload["neg_milestones"]:
        side = {"ours": "Us", "theirs": "Seller", "both": "Both"}.get(
            m["side"], m["side"]
        )
        cons = (
            f'<span class="subline">{esc(m["consequence"])}</span>'
            if m["consequence"]
            else ""
        )
        ms_rows.append(
            f'<div class="kvrow"><span class="k">{esc(m["label"])} '
            f"{_badge(side, 'b-gray')}{cons}</span>"
            f'<span class="v{" overdue" if m.get("overdue") else ""}">'
            f"{repo.fmt_date(m['date'])} · {esc(m['status'])}</span></div>"
        )
    it_rows = []
    for it in payload["open_items"]:
        owner = "Us" if it["owner"] == "us" else "Seller"
        it_rows.append(
            f'<div class="kvrow"><span class="k">{esc(it["item"])} '
            f"{_badge(owner, 'b-gray')}</span>"
            f'<span class="v{" overdue" if it.get("overdue") else ""}">'
            f"{repo.fmt_date(it['due']) if it['due'] else '—'} · "
            f"{esc(it['status'])}</span></div>"
        )
    return (
        '<div class="twocol">'
        '<div class="panel"><div class="ptitle">Milestones</div>'
        + ("".join(ms_rows) or '<p class="empty">None recorded.</p>')
        + '</div><div class="panel"><div class="ptitle">Open items</div>'
        + ("".join(it_rows) or '<p class="empty">None open.</p>')
        + "</div></div>"
    )


def _rounds(rounds: list[dict]) -> str:
    if not rounds:
        return '<p class="empty">No rounds logged.</p>'
    items = []
    for r in rounds:
        bits = []
        for k, lab in (
            ("we_asked", "We asked"),
            ("they_asked", "They asked"),
            ("we_gave", "We gave"),
            ("they_gave", "They gave"),
        ):
            if r[k]:
                bits.append(f"<b>{lab}:</b> {esc(r[k])}")
        rating = (
            f" · {_badge(f'self-rating {r['self_rating']}/5', 'b-gray')}"
            if r["self_rating"]
            else ""
        )
        nxt = (
            f'<div class="rdetail"><b>Next:</b> {esc(r["next_step"])}</div>'
            if r["next_step"]
            else ""
        )
        items.append(
            f'<div class="round"><div class="rdate">{repo.fmt_date(r["date"])} · '
            f"Round {r['round_no']} ({esc(r['channel'] or '—')})</div>"
            f'<div class="rtitle">{esc(r["outcome"] or "—")}{rating}</div>'
            f'<div class="rdetail">{" · ".join(bits)}</div>{nxt}</div>'
        )
    return f'<div class="rounds">{"".join(items)}</div>'


def _strategy_depth(payload: dict) -> str:
    s = payload["strategy"]
    parts = ['<div class="tiles3">']
    for label, val in (
        ("Our goals", s["our_goals"]),
        ("Their goals", s["their_goals"]),
        (
            "Target / Reservation / Aspiration",
            " · ".join(
                x for x in (s["outcome_target"], s["reservation"], s["aspiration"]) if x
            ),
        ),
    ):
        body = _md_lite(val) if val else '<p class="empty">—</p>'
        parts.append(
            f'<div class="panel"><div class="ptitle">{label}</div>{body}</div>'
        )
    parts.append("</div>")
    if s["locked_terms"]:
        parts.append(
            f'<p style="font-size:12px;color:#6b7280;margin-top:8px">'
            f"Locked terms (strategy): {esc(s['locked_terms'])}</p>"
        )

    open_preds = [p for p in payload["predictions"] if p["occurred"] is None]
    if open_preds:
        rows = "".join(
            "<tr>"
            f"<td>{_badge(p['tag'], 'b-gray')}</td>"
            f"<td>{esc(p['objection'])}</td>"
            f"<td>{esc(p['counter'] or '—')}</td></tr>"
            for p in open_preds
        )
        parts.append(
            '<div class="secthead">Objection bank (open)</div>'
            '<div class="tblwrap"><table><thead><tr>'
            "<th>Tag</th><th>Objection</th><th>Counter</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )

    if payload["lessons"]:
        parts.append('<div class="secthead">Self-check (open lessons)</div><div>')
        for le in payload["lessons"]:
            cls = "weak" if le["polarity"] == "weakness" else "strong"
            drill = f" — <b>Drill:</b> {esc(le['drill'])}" if le["drill"] else ""
            parts.append(
                f'<div class="lesson {cls}">'
                f'<span class="ref">{esc(le["rule_ref"] or le["polarity"])}</span>'
                f"<span>{esc(le['pattern'])}{drill}</span></div>"
            )
        parts.append("</div>")

    if s["memo_md"]:
        parts.append(
            '<div class="secthead">Strategy memo</div>'
            f'<div class="memo">{_md_lite(s["memo_md"])}</div>'
        )
    return "".join(parts)


def render(payload: dict, sandbox: bool) -> str:
    d = payload["deal"]
    s = payload.get("strategy")
    bg, fg = STAGE_COLORS.get(d["deal_stage"], ("#e2e8f0", "#000"))
    date_str = datetime.now().strftime("%Y-%m-%d") + (" · Sandbox" if sandbox else "")
    body = [
        f'<div class="strip"><a href="../../">&larr; Portfolio</a>'
        f'<span class="code">{esc(d["code_name"])}</span>'
        f'<span class="company">{esc(d["company_name"] or "")}</span>'
        f'<span class="stage-badge" style="background:{bg};color:{fg}">'
        f"{esc(payload['stage_label'])}</span>"
        f'<span class="meta">{date_str}</span></div>',
        '<div class="wrap">',
        '<div class="pagetitle">Offer &amp; Negotiation</div>',
    ]
    if not s:
        body.append(
            '<p class="empty">No negotiation strategy for this deal yet — '
            "strategies are created via /repuro:negotiate.</p></div>"
        )
        return _page(d["code_name"], "".join(body))

    body.append(_summary(payload))

    sync = payload["terms_sync"]
    if sync["mismatches"]:
        rows = "".join(
            f"<li>{esc(m['term_key'])}: offer "
            f"{esc(repo.fmt_num_bare(m['offer']))} ≠ terms ledger "
            f"{esc(repo.fmt_num_bare(m['ledger']))}</li>"
            for m in sync["mismatches"]
        )
        body.append(
            '<div class="flagbox">Latest agreed package differs from the '
            f"terms ledger:<ul>{rows}</ul></div>"
        )
    v = payload["validation"]
    if v["ran"] and not v["passed"]:
        items = "".join(f"<li>{esc(f)}</li>" for f in v["findings"][:8])
        body.append(
            '<div class="flagbox alert">Strategy memo not deliverable-grade, '
            f"open findings:<ul>{items}</ul></div>"
        )

    body.append('<div class="secthead">Offer round ledger</div>')
    body.append(_offer_ledger(payload["offers"]))
    body.append('<div class="secthead">Negotiation issue list</div>')
    body.append(_issue_list(payload["positions"]))
    body.append('<div class="secthead">Process</div>')
    body.append(_process(payload))
    body.append('<div class="secthead">Rounds</div>')
    body.append(_rounds(payload["rounds"]))
    body.append('<div class="secthead">Strategy</div>')
    body.append(_strategy_depth(payload))
    body.append("</div>")
    return _page(d["code_name"], "".join(body))


def _page(code: str, body: str) -> str:
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(code)} — Offer &amp; Negotiation</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )


def register(app, conn_fn, owner_dep) -> None:
    @app.get("/deal/{code}/negotiation", response_class=HTMLResponse)
    def ui_deal_negotiation(code: str, p=Depends(owner_dep)):
        payload = workspace.negotiation_payload(conn_fn(), code)
        if payload is None:
            raise HTTPException(404, f"unknown deal {code!r}")
        return HTMLResponse(render(payload, sandbox=p.get("sandbox", True)))
