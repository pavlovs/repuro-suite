"""DEALROOM v2 — server-rendered UI (spec §4, answer-first).

Boardroom pattern: shell-top/shell-bottom templates + Python renderers.
Styling: repuro-ci.css tokens/classes only (inlined in shell-top) — no inline
styles (NO-INLINE-INVENT). Chrome EN, data values German convention.
"""

from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import HTMLResponse

from v2 import repo, ui_workspace, workspace
from v2.uikit import BASE, SEV_CHIP, SEV_FLAG, TERM_STATUS_BADGE, esc

TPL = Path(__file__).resolve().parent / "templates"

GROUP_META = [
    ("needs_roman", "Needs Roman", "section-band--brand"),
    ("waiting_seller", "Waiting on seller", "section-band--accent"),
    ("on_track", "On track", "section-band--accent"),
]


def _shell_top() -> str:
    return (TPL / "shell-top.html").read_text(encoding="utf-8")


def _shell_bottom() -> str:
    return (TPL / "shell-bottom.html").read_text(encoding="utf-8")


def page(title: str, active: str, body: str, p: dict, foot_note: str = "") -> str:
    top = _shell_top()
    subs = {
        "{{TITLE}}": esc(title),
        "{{BASE}}": BASE,
        "{{USER}}": esc(p["user"]),
        "{{SANDBOX}}": (
            '<span class="room-tag room-tag--sandbox">Sandbox — Fly ist Master</span>'
            if p.get("sandbox")
            else ""
        ),
    }
    for nav in ("attention", "portfolio", "terms", "stakeholders"):
        subs[f"{{{{NAV_{nav.upper()}}}}}"] = "active" if active == nav else ""
    for k, v in subs.items():
        top = top.replace(k, v)
    bottom = _shell_bottom().replace(
        "{{FOOT_NOTE}}", esc(foot_note or "lokale Sandbox · Quelle: dealroom_v2.db")
    )
    return top + body + bottom


def stage_badge(stage: str, label: str) -> str:
    return (
        f'<span class="badge badge--stage" style="--c: var(--stage-{esc(stage)})">'
        f"{esc(label)}</span>"
    )


def flag_chips(flags: list[dict], limit: int = 4) -> str:
    out = []
    for f in flags[:limit]:
        out.append(
            f'<span class="chip {SEV_CHIP.get(f["severity"], "")}">'
            f"{esc(f['message'])}</span>"
        )
    if len(flags) > limit:
        out.append(f'<span class="chip">+{len(flags) - limit} weitere</span>')
    return "".join(out)


# ---------------------------------------------------------------- landing ---


def render_attention(data: dict, p: dict) -> str:
    parts = [
        '<div class="pagehead"><h1>Attention</h1>'
        '<span class="sub">Was heute Aufmerksamkeit braucht — Evidenz je Deal '
        "ein Klick tiefer.</span></div>"
    ]
    for key, label, band in GROUP_META:
        entries = data["groups"][key]
        parts.append(
            f'<section class="group">'
            f'<div class="section-band {band}"><h2>{label}</h2>'
            f'<span class="label">{len(entries)} Deals</span></div>'
            f'<div class="card card--flush"><div class="card">'
        )
        if not entries:
            parts.append('<p class="empty">Keine Deals in dieser Gruppe.</p>')
        for e in entries:
            meta_bits = []
            if e["next_milestone"]:
                meta_bits.append(
                    f'<div class="next">Nächster Meilenstein: '
                    f"{esc(e['next_milestone'])}</div>"
                )
            if e["terms_line"]:
                status = e["terms_status"] or ""
                meta_bits.append(
                    f'<div class="rowline"><span class="badge '
                    f'{TERM_STATUS_BADGE.get(status, "badge--muted")}">'
                    f"{esc(status)}</span>"
                    f'<span class="text-sm num">{esc(e["terms_line"])}</span></div>'
                )
            parts.append(
                f'<a class="deal-row" href="{BASE}/deal/{esc(e["code_name"])}">'
                f'<div class="main">'
                f'<span class="deal-name">{esc(e["code_name"])}</span> '
                f'<span class="company">{esc(e["company_name"] or "")}</span>'
                f'<div class="rowline">'
                f"{stage_badge(e['stage'], e['stage_label'])}</div>"
                f'<div class="chips">{flag_chips(e["flags"])}</div>'
                f"</div>"
                f'<div class="meta">{"".join(meta_bits)}</div>'
                f"</a>"
            )
        parts.append("</div></div></section>")

    parked = data["parked"]
    if parked:
        bits = []
        for stage, codes in parked.items():
            label = repo.STAGE_LABELS.get(stage, stage)
            bits.append(
                f"{stage_badge(stage, label)} "
                f'<span class="codes">{esc(", ".join(codes))}</span>'
            )
        parts.append(
            f'<div class="card"><div class="parked">'
            f'<span class="label">Geparkt</span>{"".join(bits)}</div></div>'
        )
    return "".join(parts)


# -------------------------------------------------------------- portfolio ---


def render_portfolio(rows: list[dict]) -> str:
    body = [
        '<div class="pagehead"><h1>Portfolio</h1>'
        f'<span class="sub">{len(rows)} Deals · Zahlen lt. deals-Registry '
        "(Overrides)</span></div>",
        '<div class="card card--flush"><table class="tbl"><thead><tr>'
        "<th>Deal</th><th>Company</th><th>Stage</th><th>Sektor</th>"
        '<th class="r">Umsatz</th><th class="r">EBITDA</th>'
        '<th class="r">EV</th><th class="r">Multiple</th><th>Note</th>'
        "</tr></thead><tbody>",
    ]
    for r in rows:
        body.append(
            "<tr>"
            f'<td><a href="{BASE}/deal/{esc(r["code_name"])}">{esc(r["code_name"])}</a></td>'
            f"<td>{esc(r['company_name'] or '—')}</td>"
            f"<td>{stage_badge(r['stage'], r['stage_label'])}</td>"
            f"<td>{esc(r['sector'] or '—')}</td>"
            f'<td class="r num">{repo.fmt_keur(r["rev_m"] * 1000) if r["rev_m"] is not None else "—"}</td>'
            f'<td class="r num">{repo.fmt_keur(r["ebitda_m"] * 1000) if r["ebitda_m"] is not None else "—"}</td>'
            f'<td class="r num">{repo.fmt_keur(r["ev_m"] * 1000) if r["ev_m"] is not None else "—"}</td>'
            f'<td class="r num">{repo.fmt_mult(r["multiple"])}</td>'
            f'<td class="text-sm">{esc(r["status_note"] or "")}</td>'
            "</tr>"
        )
    body.append("</tbody></table></div>")
    return "".join(body)


# ---------------------------------------------------------------- deal page -


def _terms_card(terms: list[dict]) -> str:
    if not terms:
        return (
            '<div class="tile"><span class="label">Terms</span>'
            '<p class="empty">Kein Terms-Eintrag — beginnt mit NBO.</p></div>'
        )
    rows = []
    for t in terms:
        rows.append(
            f'<div class="kv"><span class="k">{esc(t["label"])}'
            f' <span class="badge {TERM_STATUS_BADGE.get(t["status"], "badge--muted")}">'
            f"{esc(t['status'])}</span></span>"
            f'<span class="v num">{esc(t["display"])}</span></div>'
        )
    return (
        f'<div class="tile"><span class="label">Terms (Ledger)</span>'
        f"{''.join(rows)}</div>"
    )


def _milestones_card(milestones: list[dict], next_m: dict | None) -> str:
    open_ms = [m for m in milestones if m["status"] == "open"][:6]
    if not open_ms:
        return (
            '<div class="tile"><span class="label">Meilensteine</span>'
            '<p class="empty">Keine offenen Meilensteine.</p></div>'
        )
    rows = []
    for m in open_ms:
        due = (
            repo.fmt_date(m["due_date"]) if m["due_date"] else esc(m["note"] or "offen")
        )
        mark = " ◀" if next_m and m["id"] == next_m.get("id") else ""
        rows.append(
            f'<div class="kv"><span class="k">{esc(m["milestone"])} '
            f'<span class="badge badge--muted">{esc(m["owner"])}</span></span>'
            f'<span class="v num">{due}{mark}</span></div>'
        )
    return (
        f'<div class="tile"><span class="label">Meilensteine (LOI-Zeitplan)</span>'
        f"{''.join(rows)}</div>"
    )


def _risks_card(risks: list[dict]) -> str:
    if not risks:
        return (
            '<div class="tile"><span class="label">Risiken (DD)</span>'
            '<p class="empty">Keine offenen Red Flags erfasst.</p></div>'
        )
    rows = []
    for r in risks:
        sev = "chip--alert" if r["risk_level"] == "high" else "chip--warn"
        note = esc(r["risk_note"] or "")
        rows.append(
            f'<div class="flag {"flag--alert" if r["risk_level"] == "high" else "flag--warn"}">'
            f'<span class="chip {sev}">{esc(r["risk_level"])}</span>'
            f"<span><b>{esc(r['description'])}</b>"
            + (f' — <span class="muted">{note}</span>' if note else "")
            + "</span></div>"
        )
    return (
        f'<div class="tile"><span class="label">Risiken (DD)</span>'
        f'<div class="flaglist">{"".join(rows)}</div></div>'
    )


def _flags_block(flags: list[dict]) -> str:
    if not flags:
        return ""
    rows = [
        f'<div class="flag {SEV_FLAG.get(f["severity"], "")}">'
        f'<span class="label">{esc(f["rule"])}</span>'
        f"<span>{esc(f['message'])}</span></div>"
        for f in flags
    ]
    return f'<div class="flaglist">{"".join(rows)}</div>'


def _figures_block(figures: list[dict]) -> str:
    if not figures:
        return ""
    tiles = []
    for f in figures:
        chip = (
            f'<span class="srcchip">{esc(f["source"])}'
            + (f" · Stand {esc(f['as_of'])}" if f["as_of"] else "")
            + "</span>"
        )
        tiles.append(
            f'<div class="tile figblock"><span class="label">{esc(f["label"])}</span>'
            f'<span class="figure">{esc(f["value"])}</span>{chip}</div>'
        )
    return f'<div class="grid grid--4">{"".join(tiles)}</div>'


def render_deal(
    answer: dict,
    timeline: list[dict],
    active_tab: str = "overview",
    extra_tabs: dict | None = None,
    tab_body: str | None = None,
) -> str:
    d = answer["deal"]
    code = d["code_name"]
    ev = answer["stage_evidence"]
    parts = [
        f'<div class="crumbs"><a href="{BASE}/">Attention</a> / '
        f'<a href="{BASE}/portfolio">Portfolio</a> / {esc(code)}</div>',
        f'<div class="pagehead"><h1>{esc(code)}</h1>'
        f'<span class="sub">{esc(d["company_name"] or "")}'
        + (f" · {esc(d['sector'])}" if d["sector"] else "")
        + (f" · {esc(d['location'])}" if d["location"] else "")
        + "</span></div>",
        '<div class="rowline">'
        + stage_badge(d["deal_stage"], answer["stage_label"])
        + (
            f'<span class="text-sm">seit {repo.fmt_date(d["stage_entered_at"])}</span>'
            if d["stage_entered_at"]
            else ""
        )
        + (
            f'<span class="srcchip" title="{esc(ev["evidence"])}">Evidenz: '
            f"{esc((ev['evidence'] or '')[:90])}…</span>"
            if ev and ev["evidence"]
            else ""
        )
        + "</div>",
    ]
    if answer["flags"]:
        parts.append('<div class="hr"></div>')
        parts.append(_flags_block(answer["flags"]))

    tabs = {"overview": "Overview", "timeline": "Timeline"}
    if extra_tabs:
        tabs.update(extra_tabs)
    tabs["terms"] = "Terms"
    nav = "".join(
        f'<a href="{BASE}/deal/{esc(code)}{"" if k == "overview" else "/" + k}" '
        f'class="{"active" if k == active_tab else ""}">{v}</a>'
        for k, v in tabs.items()
    )
    parts.append(f'<div class="tabnav">{nav}</div>')

    if tab_body is not None:
        parts.append(tab_body)
        return "".join(parts)

    # overview tab
    parts.append(_figures_block(answer["financials"]))
    parts.append('<div class="hr"></div>')
    parts.append(
        '<div class="answer-grid">'
        + _terms_card(answer["terms"])
        + _milestones_card(answer["milestones"], answer["next_milestone"])
        + _risks_card(answer["risks"])
        + "</div>"
    )

    if answer["artifacts_current"]:
        rows = []
        for a in answer["artifacts_current"]:
            others = (
                f'<span class="text-sm muted"> +{a["n_others"]} weitere</span>'
                if a.get("n_others")
                else ""
            )
            rows.append(
                "<tr>"
                f'<td><span class="badge badge--muted">{esc(a["artifact_type"])}</span></td>'
                f"<td>{esc(a['file_name'])}{others}</td>"
                f'<td class="r num">{esc(a["version"] or "—")}</td>'
                f'<td class="r num">{repo.fmt_date(a["file_date"])}</td>'
                f"<td>{esc(a['status'])}</td></tr>"
            )
        parts.append(
            '<div class="hr"></div><h3>Aktuelle Artefakte</h3>'
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            '<th>Typ</th><th>Datei</th><th class="r">v</th>'
            '<th class="r">Datum</th><th>Status</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    return "".join(parts)


def render_timeline_tab(events: list[dict]) -> str:
    if not events:
        return '<p class="empty">Keine Ereignisse.</p>'
    items = []
    for e in events:
        detail = (
            f'<div class="t-detail">{esc(e["detail"])}</div>' if e["detail"] else ""
        )
        items.append(
            f'<li class="k-{esc(e["kind"])}">'
            f'<span class="t-date">{repo.fmt_date(e["date"])}</span>'
            f'<div class="t-title">{esc(e["title"])}</div>{detail}</li>'
        )
    return f'<ul class="timeline">{"".join(items)}</ul>'


def render_terms_tab(terms: list[dict]) -> str:
    if not terms:
        return (
            '<p class="empty">Kein Terms-Eintrag für diesen Deal — '
            "Ledger beginnt mit NBO-Versand.</p>"
        )
    rows = []
    for t in terms:
        # SCANNABLE-CELLS: multi-fact notes become one fact per bullet
        note = t["note"] or ""
        note_parts = [x.strip() for x in note.split(";") if x.strip()]
        if len(note_parts) > 1:
            note_html = (
                "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in note_parts) + "</ul>"
            )
        else:
            note_html = esc(note)
        rows.append(
            "<tr>"
            f"<td>{esc(t['label'])}</td>"
            f'<td class="r num">{esc(t.get("display_exact") or t["display"])}</td>'
            f'<td><span class="badge {TERM_STATUS_BADGE.get(t["status"], "badge--muted")}">'
            f"{esc(t['status'])}</span></td>"
            f'<td class="text-sm">{esc(t["source_doc"])}</td>'
            f'<td class="text-sm">{note_html}</td>'
            f'<td class="r num">{repo.fmt_date(t["changed_at"])}</td>'
            "</tr>"
        )
    return (
        '<div class="card card--flush"><table class="tbl"><thead><tr>'
        '<th>Term</th><th class="r">Wert</th><th>Status</th><th>Quelle</th>'
        '<th>Notiz</th><th class="r">Stand</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_terms_global(terms: list[dict]) -> str:
    by_deal: dict[str, list] = {}
    for t in terms:
        if t["status"] == "superseded":
            continue
        by_deal.setdefault(t["code_name"], []).append(t)
    parts = [
        '<div class="pagehead"><h1>Terms-Ledger</h1>'
        '<span class="sub">Verhandelte Konditionen ab NBO — Quelle je Zeile. '
        "Historie auf der Deal-Seite.</span></div>"
    ]
    if not by_deal:
        parts.append('<p class="empty">Noch keine Terms erfasst.</p>')
    for code, ts in by_deal.items():
        parts.append(
            f'<h3><a href="{BASE}/deal/{esc(code)}">{esc(code)}</a></h3>'
            + render_terms_tab(ts)
            + '<div class="hr"></div>'
        )
    return "".join(parts)


def render_stakeholders(rows: list[dict]) -> str:
    parts = [
        '<div class="pagehead"><h1>Stakeholders</h1>'
        '<span class="sub">CRM-Spine der Verhandlungen — Personen, Kontexte, '
        "Claims.</span></div>"
    ]
    if not rows:
        return parts[0] + '<p class="empty">Keine Stakeholder erfasst.</p>'
    body = [
        '<div class="card card--flush"><table class="tbl"><thead><tr>'
        "<th>Name</th><th>Firma</th><th>Rolle</th><th>Kontexte</th>"
        '<th class="r">Claims</th><th class="r">Runden</th></tr></thead><tbody>'
    ]
    for s in rows:
        body.append(
            "<tr>"
            f'<td><a href="{BASE}/stakeholder/{s["id"]}">{esc(s["name"])}</a></td>'
            f"<td>{esc(s['company'] or '—')}</td>"
            f"<td>{esc(s['role'] or '—')}</td>"
            f'<td class="text-sm">{esc(s["contexts"] or "—")}</td>'
            f'<td class="r num">{s["n_claims"]}</td>'
            f'<td class="r num">{s["n_rounds"]}</td>'
            "</tr>"
        )
    body.append("</tbody></table></div>")
    return parts[0] + "".join(body)


# ---------------------------------------------------------------- routes ----


def _deal_tabs(conn, code, p) -> dict:
    """CDD is always a tab; Negotiation only for owners on deals that have a
    strategy — no dead tabs, no placeholder sections."""
    tabs = {"cdd": "CDD"}
    if p.get("is_owner"):
        d = repo.get_deal(conn, code)
        if d and d["domain"]:
            has_strategy = conn.execute(
                "SELECT 1 FROM negotiation_strategies WHERE deal_domain=? LIMIT 1",
                (d["domain"],),
            ).fetchone()
            if has_strategy:
                tabs["negotiation"] = "Negotiation"
    return tabs


def register(app, conn_fn, principal_dep, owner_dep):

    @app.get("/", response_class=HTMLResponse)
    def ui_index(p=Depends(principal_dep)):
        data = repo.attention(conn_fn())
        return page("Dealroom — Attention", "attention", render_attention(data, p), p)

    @app.get("/portfolio", response_class=HTMLResponse)
    def ui_portfolio(p=Depends(principal_dep)):
        rows = repo.portfolio(conn_fn())
        return page("Dealroom — Portfolio", "portfolio", render_portfolio(rows), p)

    @app.get("/terms", response_class=HTMLResponse)
    def ui_terms(p=Depends(principal_dep)):
        terms = repo.terms_ledger(conn_fn())
        return page("Dealroom — Terms", "terms", render_terms_global(terms), p)

    @app.get("/deal/{code}", response_class=HTMLResponse)
    def ui_deal(code: str, p=Depends(principal_dep)):
        c = conn_fn()
        answer = repo.deal_answer(c, code)
        if not answer:
            raise HTTPException(404, f"unknown deal {code!r}")
        timeline = repo.deal_timeline(c, code)
        return page(
            f"{answer['deal']['code_name']} — Dealroom",
            "attention",
            render_deal(answer, timeline, extra_tabs=_deal_tabs(c, code, p)),
            p,
        )

    @app.get("/deal/{code}/timeline", response_class=HTMLResponse)
    def ui_deal_timeline(code: str, p=Depends(principal_dep)):
        c = conn_fn()
        answer = repo.deal_answer(c, code)
        if not answer:
            raise HTTPException(404, f"unknown deal {code!r}")
        events = repo.deal_timeline(c, code)
        return page(
            f"{answer['deal']['code_name']} — Timeline",
            "attention",
            render_deal(
                answer,
                events,
                active_tab="timeline",
                extra_tabs=_deal_tabs(c, code, p),
                tab_body=render_timeline_tab(events),
            ),
            p,
        )

    @app.get("/deal/{code}/terms", response_class=HTMLResponse)
    def ui_deal_terms(code: str, p=Depends(principal_dep)):
        c = conn_fn()
        answer = repo.deal_answer(c, code)
        if not answer:
            raise HTTPException(404, f"unknown deal {code!r}")
        terms = repo.terms_ledger(c, code)
        return page(
            f"{answer['deal']['code_name']} — Terms",
            "attention",
            render_deal(
                answer,
                [],
                active_tab="terms",
                extra_tabs=_deal_tabs(c, code, p),
                tab_body=render_terms_tab(terms),
            ),
            p,
        )

    @app.get("/deal/{code}/cdd", response_class=HTMLResponse)
    def ui_deal_cdd(code: str, p=Depends(principal_dep)):
        c = conn_fn()
        answer = repo.deal_answer(c, code)
        if not answer:
            raise HTTPException(404, f"unknown deal {code!r}")
        payload = workspace.cdd_payload(c, code)
        return page(
            f"{answer['deal']['code_name']} — CDD",
            "attention",
            render_deal(
                answer,
                [],
                active_tab="cdd",
                extra_tabs=_deal_tabs(c, code, p),
                tab_body=ui_workspace.render_cdd_tab(payload),
            ),
            p,
        )

    @app.get("/deal/{code}/negotiation", response_class=HTMLResponse)
    def ui_deal_negotiation(code: str, p=Depends(owner_dep)):
        c = conn_fn()
        answer = repo.deal_answer(c, code)
        if not answer:
            raise HTTPException(404, f"unknown deal {code!r}")
        payload = workspace.negotiation_payload(c, code)
        return page(
            f"{answer['deal']['code_name']} — Negotiation",
            "attention",
            render_deal(
                answer,
                [],
                active_tab="negotiation",
                extra_tabs=_deal_tabs(c, code, p),
                tab_body=ui_workspace.render_negotiation_tab(payload),
            ),
            p,
        )

    @app.get("/stakeholders", response_class=HTMLResponse)
    def ui_stakeholders(p=Depends(owner_dep)):
        rows = workspace.stakeholders_index(conn_fn())
        return page(
            "Dealroom — Stakeholders", "stakeholders", render_stakeholders(rows), p
        )

    @app.get("/stakeholder/{sid}", response_class=HTMLResponse)
    def ui_stakeholder(sid: int, p=Depends(owner_dep)):
        payload = workspace.stakeholder_payload(conn_fn(), sid)
        if not payload:
            raise HTTPException(404, "unknown stakeholder")
        return page(
            f"{payload['stakeholder']['name']} — Stakeholder",
            "stakeholders",
            ui_workspace.render_stakeholder_page(payload),
            p,
        )
