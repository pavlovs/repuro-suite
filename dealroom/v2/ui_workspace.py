"""DEALROOM v2 — renderers for CDD workspace (M4) + negotiation/stakeholders (M5).
Pure HTML builders on the shell design system; routes live in ui.py."""

from v2 import repo
from v2.uikit import BASE, CONF_CHIP, LANE_BADGE, SEV_CHIP, esc


# ------------------------------------------------------------------- M4 -----


def render_cdd_tab(payload: dict) -> str:
    parts = []

    # data-room health
    parts.append("<h3>Datenraum (Sorgfaltsprüfung)</h3>")
    if not payload["dataroom"]:
        parts.append(
            '<p class="empty">Noch kein Datenraum-Scan. Lokal ausführen: '
            "<code>python -m v2.scanner dataroom --deal "
            f"{esc(payload['deal']['code_name'])} --path &lt;Datenraum-Root&gt;</code>"
            " (Pfad in data/scanner_paths.json hinterlegen — Lesezugriff only).</p>"
        )
    else:
        rows = []
        for s in payload["dataroom"]:
            delta = []
            if s["delta_added"]:
                delta.append(f"+{s['delta_added']} neu")
            if s["delta_changed"]:
                delta.append(f"{s['delta_changed']} geändert")
            if s["delta_removed"]:
                delta.append(f"−{s['delta_removed']} entfernt")
            delta_txt = (
                f'<span class="chip chip--info">{esc(", ".join(delta))}</span>'
                if delta
                else '<span class="muted">—</span>'
            )
            rows.append(
                "<tr>"
                f'<td class="num">{esc(s["section"])}</td>'
                f"<td>{esc(s['name'])}</td>"
                f'<td><span class="badge {LANE_BADGE.get(s["lane"], "badge--muted")}">'
                f"{esc(s['lane'])}</span></td>"
                f'<td class="r num">{s["file_count"]}</td>'
                f'<td class="r num">{repo.fmt_date(s["newest_file_date"])}</td>'
                f"<td>{delta_txt}</td>"
                f'<td class="r num">{repo.fmt_date(s["scanned_at"])}</td>'
                "</tr>"
            )
        parts.append(
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            "<th>Nr</th><th>Sektion</th><th>Lane</th>"
            '<th class="r">Dateien</th><th class="r">Neueste</th>'
            '<th>Delta (letzter Scan)</th><th class="r">Gescannt</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        )

    # registries
    parts.append('<div class="hr"></div><h3>Registries</h3><div class="grid grid--3">')
    for atype, title in (
        ("databook", "Databook"),
        ("rfi", "RFI / Fragenliste"),
        ("slides", "Slides / Deck"),
    ):
        rows = payload["registries"].get(atype) or []
        inner = []
        for r in rows[:8]:
            checks = r.get("checks") or {}
            marks = []
            if checks.get("sign_off"):
                marks.append('<span class="chip chip--info">Sign-off</span>')
            if checks.get("error_flag"):
                marks.append('<span class="chip chip--alert">Error-Flag</span>')
            if checks.get("tie_out") is False:
                marks.append('<span class="chip chip--warn">Tie-out offen</span>')
            inner.append(
                f'<div class="kv"><span class="k">{esc(r["file_name"])}'
                f"{''.join(marks)}</span>"
                f'<span class="v num">{repo.fmt_date(r["file_date"])} · '
                f"{esc(r['status'])}</span></div>"
            )
        if len(rows) > 8:
            inner.append(f'<p class="empty">+{len(rows) - 8} ältere Versionen</p>')
        if not rows:
            inner.append('<p class="empty">Keine Einträge.</p>')
        parts.append(
            f'<div class="tile"><span class="label">{title} ({len(rows)})</span>'
            f"{''.join(inner)}</div>"
        )
    parts.append("</div>")

    # RFI tracker
    rfi = payload["rfi"]
    parts.append('<div class="hr"></div><h3>RFI-Tracker</h3>')
    if not rfi["rows"]:
        parts.append(
            '<p class="empty">Keine Fragen im Mirror — '
            "<code>python -m v2.scanner rfi --deal "
            f"{esc(payload['deal']['code_name'])}</code> importiert die "
            "aktuelle Fragenliste (xlsx bleibt Master).</p>"
        )
    else:
        src = rfi["source"]
        chip = (
            f'<span class="srcchip">Master: {esc(src["file_name"])} · '
            f"{repo.fmt_date(src['file_date'])}</span>"
            if src
            else ""
        )
        stat = " · ".join(f"{k}: {v}" for k, v in sorted(rfi["by_status"].items()))
        prio = " · ".join(f"{k}: {v}" for k, v in sorted(rfi["by_priority"].items()))
        parts.append(
            f'<div class="rowline"><span class="text-sm">{esc(stat)}</span>'
            f'<span class="text-sm muted">| Priorität — {esc(prio)}</span>{chip}</div>'
        )
        open_rows = [q for q in rfi["rows"] if q["status"] == "sent"][:12]
        rows = []
        for q in open_rows:
            days = (
                f"{q['days_outstanding']} Tage offen"
                if q["days_outstanding"] is not None
                else "—"
            )
            prio_chip = SEV_CHIP.get(
                {"high": "alert", "medium": "warn"}.get(q["importance"], "info"), "chip"
            )
            rows.append(
                "<tr>"
                f'<td class="text-sm">{esc(q["category"])}</td>'
                f"<td>{esc(q['question'][:140])}</td>"
                f'<td><span class="chip {prio_chip}">{esc(q["importance"])}</span></td>'
                f'<td class="r num">{esc(days)}</td>'
                "</tr>"
            )
        if rows:
            parts.append(
                '<div class="card card--flush"><table class="tbl"><thead><tr>'
                "<th>Thema</th><th>Frage</th><th>Prio</th>"
                '<th class="r">Offen seit</th></tr></thead><tbody>'
                + "".join(rows)
                + "</tbody></table></div>"
            )

    # red flags
    parts.append('<div class="hr"></div><h3>Red Flags (DD-Items)</h3>')
    flags = payload["red_flags"]
    if not flags:
        parts.append('<p class="empty">Keine DD-Items erfasst.</p>')
    else:
        rows = []
        for r in flags:
            lvl = r["risk_level"] or "—"
            chip_cls = {"high": "chip--alert", "medium": "chip--warn"}.get(lvl, "chip")
            rows.append(
                "<tr>"
                f'<td><span class="chip {chip_cls}">{esc(lvl)}</span></td>'
                f'<td class="text-sm">{esc(r["category"])}</td>'
                f"<td>{esc(r['description'])}</td>"
                f'<td class="text-sm">{esc(r["risk_note"] or "")}</td>'
                f'<td class="text-sm">{esc(r["status"] or "")}</td>'
                f'<td class="text-sm">{esc(r["advisor"] or "—")}</td>'
                "</tr>"
            )
        parts.append(
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            "<th>Risiko</th><th>Kategorie</th><th>Item</th><th>Notiz</th>"
            "<th>Status</th><th>Advisor</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )

    # DD milestones
    parts.append('<div class="hr"></div><h3>DD-Meilensteine (LOI-Zeitplan)</h3>')
    ms = payload["milestones"]
    if not ms:
        parts.append('<p class="empty">Keine Meilensteine erfasst.</p>')
    else:
        rows = []
        for m in ms:
            due = (
                repo.fmt_date(m["due_date"])
                if m["due_date"]
                else esc(m["note"] or "offen")
            )
            rows.append(
                "<tr>"
                f"<td>{esc(m['milestone'])}</td>"
                f'<td class="r num">{due}</td>'
                f'<td><span class="badge badge--muted">{esc(m["owner"])}</span></td>'
                f"<td>{esc(m['status'])}</td>"
                f'<td class="text-sm">{esc(m["source_doc"] or "")}</td>'
                "</tr>"
            )
        parts.append(
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            '<th>Meilenstein</th><th class="r">Fällig</th><th>Owner</th>'
            "<th>Status</th><th>Quelle</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )
    return "".join(parts)


# ------------------------------------------------------------------- M5 -----


def _md_lite(md: str) -> str:
    """Minimal markdown for strategy memos: headers, bullets, bold, hr.
    Everything else stays verbatim paragraphs — fidelity over polish."""
    out, in_ul = [], False
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
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
        elif stripped.startswith("## "):
            out.append(f"<h3>{_inline(stripped[3:])}</h3>")
        elif stripped.startswith("# "):
            out.append(f"<h3>{_inline(stripped[2:])}</h3>")
        elif stripped in ("---", "***"):
            out.append('<div class="hr"></div>')
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


def render_negotiation_tab(payload: dict) -> str:
    if not payload or not payload.get("strategy"):
        return (
            '<p class="empty">Keine Verhandlungsstrategie für diesen Deal — '
            "Strategien entstehen über /repuro:negotiate.</p>"
        )
    s = payload["strategy"]
    parts = []

    # validation gate + header line
    v = payload["validation"]
    if v["ran"] and v["passed"]:
        gate = '<span class="chip chip--info">Validator: PASS</span>'
    elif v["ran"]:
        gate = (
            f'<span class="chip chip--alert">Validator: FAIL '
            f"({len(v['findings'])} Findings)</span>"
        )
    else:
        gate = '<span class="chip chip--warn">Validator: nicht ausführbar</span>'
    trail = payload["trail"]
    parts.append(
        f'<div class="rowline">'
        f'<span class="badge badge--brand">{esc(s["status"])}</span>'
        f'<span class="text-sm">Gegenüber: <b>{esc(s["stakeholder_name"])}</b> '
        f"({esc(s['stakeholder_company'] or '—')})</span>"
        f"{gate}"
        f'<span class="text-sm muted">Trail: {trail["read"]}/{trail["total"]} gelesen</span>'
        f"</div>"
    )
    if v["ran"] and not v["passed"]:
        items = "".join(f"<li>{esc(f)}</li>" for f in v["findings"][:8])
        parts.append(
            f'<div class="flag flag--alert"><span>Memo nicht deliverable-fähig, '
            f"offene Findings:<ul>{items}</ul></span></div>"
        )

    # position map
    parts.append('<div class="hr"></div><div class="grid grid--3">')
    for label, val in (
        ("Unsere Ziele", s["our_goals"]),
        ("Seine Ziele", s["their_goals"]),
        (
            "Ziel / Reservation / Aspiration",
            " · ".join(
                x for x in (s["outcome_target"], s["reservation"], s["aspiration"]) if x
            ),
        ),
    ):
        parts.append(
            f'<div class="tile"><span class="label">{label}</span>'
            f"<p>{esc(val or '—')}</p></div>"
        )
    parts.append("</div>")

    # locked terms
    if payload["locked_terms"] or s["locked_terms"]:
        parts.append('<div class="hr"></div><h3>Locked / Agreed Terms</h3>')
        rows = []
        for t in payload["locked_terms"]:
            rows.append(
                f'<div class="kv"><span class="k">{esc(t["label"])}</span>'
                f'<span class="v num">{esc(t["display"])}</span></div>'
            )
        if rows:
            parts.append(f'<div class="tile">{"".join(rows)}</div>')
        if s["locked_terms"]:
            parts.append(f'<p class="text-sm">{esc(s["locked_terms"])}</p>')

    # positions (Roman-confirmed walk-away lines)
    if payload.get("positions"):
        rows = []
        for po in payload["positions"]:
            confirm = (
                '<span class="chip chip--info">Roman ✓</span>'
                if po["roman_confirmed"]
                else '<span class="chip chip--warn">unbestätigt</span>'
            )
            rows.append(
                "<tr>"
                f"<td>{esc(po['term'])}</td>"
                f"<td>{esc(po['preferred'])}</td>"
                f'<td class="text-sm">{esc(po["fallback"] or "—")}</td>'
                f'<td class="text-sm">{esc(po["walk_away"] or "—")}</td>'
                f"<td>{esc(po['status'])}</td><td>{confirm}</td></tr>"
            )
        parts.append(
            '<div class="hr"></div><h3>Positionen</h3>'
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            "<th>Term</th><th>Präferenz</th><th>Fallback</th><th>Walk-away</th>"
            "<th>Status</th><th>Freigabe</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )

    # open items + negotiation milestones
    if payload.get("open_items") or payload.get("neg_milestones"):
        parts.append('<div class="hr"></div><div class="grid grid--2">')
        items_rows = []
        for it in payload.get("open_items") or []:
            owner = "Wir" if it["owner"] == "us" else "Verkäufer"
            items_rows.append(
                f'<div class="kv"><span class="k">{esc(it["item"])} '
                f'<span class="badge badge--muted">{owner}</span></span>'
                f'<span class="v num">{repo.fmt_date(it["due"]) if it["due"] else "—"}'
                f" · {esc(it['status'])}</span></div>"
            )
        parts.append(
            '<div class="tile"><span class="label">Offene Punkte</span>'
            + ("".join(items_rows) or '<p class="empty">Keine.</p>')
            + "</div>"
        )
        ms_rows = []
        for m in payload.get("neg_milestones") or []:
            ms_rows.append(
                f'<div class="kv"><span class="k">{esc(m["label"])}'
                + (
                    f' <span class="text-sm muted">{esc(m["consequence"])}</span>'
                    if m["consequence"]
                    else ""
                )
                + f'</span><span class="v num">{repo.fmt_date(m["date"])} · '
                f"{esc(m['status'])}</span></div>"
            )
        parts.append(
            '<div class="tile"><span class="label">Verhandlungs-Meilensteine</span>'
            + ("".join(ms_rows) or '<p class="empty">Keine.</p>')
            + "</div>"
        )
        parts.append("</div>")

    # parties
    if payload.get("parties"):
        chips = "".join(
            f'<a class="chip chip--info" href="{BASE}/stakeholder/'
            f'{p_["stakeholder_id"]}">{esc(p_["name"])} · {esc(p_["role"])}</a>'
            for p_ in payload["parties"]
        )
        parts.append(
            f'<div class="hr"></div><div class="rowline">'
            f'<span class="label">Parteien</span>{chips}</div>'
        )

    # SELBST-CHECK
    if payload["lessons"]:
        parts.append(
            '<div class="hr"></div><h3>SELBST-CHECK (offene Lessons)</h3>'
            '<div class="flaglist">'
        )
        for le in payload["lessons"]:
            cls = "flag--alert" if le["polarity"] == "weakness" else "flag--info"
            drill = f" — <b>Drill:</b> {esc(le['drill'])}" if le["drill"] else ""
            parts.append(
                f'<div class="flag {cls}">'
                f'<span class="label">{esc(le["rule_ref"] or le["polarity"])}</span>'
                f"<span>{esc(le['pattern'])}{drill}</span></div>"
            )
        parts.append("</div>")

    # open predictions / objections
    open_preds = [p for p in payload["predictions"] if p["occurred"] is None]
    if open_preds:
        parts.append('<div class="hr"></div><h3>Objection-Bank (offen)</h3>')
        rows = [
            "<tr>"
            f'<td><span class="badge badge--muted">{esc(p["tag"])}</span></td>'
            f"<td>{esc(p['objection'])}</td>"
            f'<td class="text-sm">{esc(p["counter"] or "—")}</td></tr>'
            for p in open_preds
        ]
        parts.append(
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            "<th>Tag</th><th>Einwand</th><th>Konter</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )

    # rounds timeline
    parts.append('<div class="hr"></div><h3>Runden</h3><ul class="timeline">')
    for r in payload["rounds"]:
        bits = []
        for k, lab in (
            ("we_asked", "Wir fragten"),
            ("they_asked", "Er fragte"),
            ("we_gave", "Wir gaben"),
            ("they_gave", "Er gab"),
        ):
            if r[k]:
                bits.append(f"<b>{lab}:</b> {esc(r[k])}")
        rating = (
            f' <span class="chip">Self-Rating {r["self_rating"]}/5</span>'
            if r["self_rating"]
            else ""
        )
        parts.append(
            f'<li class="k-round"><span class="t-date">{repo.fmt_date(r["date"])} · '
            f"Runde {r['round_no']} ({esc(r['channel'] or '—')})</span>"
            f'<div class="t-title">{esc(r["outcome"] or "—")}{rating}</div>'
            f'<div class="t-detail">{" · ".join(bits)}</div>'
            + (
                f'<div class="t-detail"><b>Next:</b> {esc(r["next_step"])}</div>'
                if r["next_step"]
                else ""
            )
            + "</li>"
        )
    parts.append("</ul>")

    # strategy memo
    if s["memo_md"]:
        parts.append(
            '<div class="hr"></div><h3>Strategie-Memo</h3>'
            f'<div class="card">{_md_lite(s["memo_md"])}</div>'
        )
    return "".join(parts)


def render_stakeholder_page(payload: dict) -> str:
    s = payload["stakeholder"]
    parts = [
        f'<div class="crumbs"><a href="{BASE}/stakeholders">Stakeholders</a> / '
        f"{esc(s['name'])}</div>",
        f'<div class="pagehead"><h1>{esc(s["name"])}</h1>'
        f'<span class="sub">{esc(s["company"] or "")}'
        + (f" · {esc(s['role'])}" if s["role"] else "")
        + "</span></div>",
    ]
    idbits = []
    if s["email"]:
        idbits.append(esc(s["email"]))
    if s["phone"]:
        idbits.append(esc(s["phone"]))
    if s["hubspot_contact_id"]:
        idbits.append(f"HubSpot #{esc(s['hubspot_contact_id'])}")
    ctx = ", ".join(
        f"{esc(li['context_ref'])} ({esc(li['relationship'] or li['context_type'])})"
        for li in payload["links"]
    )
    parts.append(
        f'<div class="rowline"><span class="text-sm">{" · ".join(idbits) or "—"}</span>'
        + (f'<span class="badge badge--brand">{ctx}</span>' if ctx else "")
        + "</div>"
    )

    # claims
    parts.append('<div class="hr"></div><h3>Profil-Claims</h3>')
    if not payload["claims"]:
        parts.append('<p class="empty">Keine Claims erfasst.</p>')
    else:
        rows = []
        for c in payload["claims"]:
            quote = esc(c["evidence_quote"] or "")
            src = " · ".join(
                x for x in (c["source_medium"], repo.fmt_date(c["source_date"])) if x
            )
            rows.append(
                "<tr>"
                f"<td>{esc(c['field'])}</td>"
                f"<td>{esc(c['value'])}</td>"
                f'<td><span class="chip {CONF_CHIP.get(c["confidence"], "chip")}">'
                f"{esc(c['confidence'])}</span></td>"
                f'<td class="text-sm">{quote}</td>'
                f'<td class="text-sm">{esc(src)}</td>'
                f"<td>{esc(c['status'])}</td></tr>"
            )
        parts.append(
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            "<th>Feld</th><th>Wert</th><th>Konfidenz</th><th>Evidenz</th>"
            "<th>Quelle</th><th>Status</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
        )

    # rounds across contexts
    parts.append('<div class="hr"></div><h3>Runden (alle Kontexte)</h3>')
    if not payload["rounds"]:
        parts.append('<p class="empty">Keine Runden.</p>')
    else:
        parts.append('<ul class="timeline">')
        for r in payload["rounds"]:
            parts.append(
                f'<li class="k-round"><span class="t-date">{repo.fmt_date(r["date"])}'
                f" · {esc(r['context_ref'])} · Runde {r['round_no']}</span>"
                f'<div class="t-title">{esc(r["outcome"] or "—")}</div>'
                + (
                    f'<div class="t-detail"><b>Next:</b> {esc(r["next_step"])}</div>'
                    if r["next_step"]
                    else ""
                )
                + "</li>"
            )
        parts.append("</ul>")

    # communication trail
    parts.append('<div class="hr"></div><h3>Kommunikations-Trail</h3>')
    if not payload["trail"]:
        parts.append('<p class="empty">Kein Trail erfasst.</p>')
    else:
        rows = []
        for t in payload["trail"][:40]:
            read_chip = {
                "read": "chip--info",
                "unread": "chip--warn",
                "sealed": "chip",
            }.get(t["read_status"], "chip")
            rows.append(
                "<tr>"
                f'<td class="num">{repo.fmt_date(t["date"])}</td>'
                f"<td>{esc(t['source'])}</td>"
                f"<td>{esc(t['direction'] or '—')}</td>"
                f"<td>{esc(t['subject'] or t['ref'] or '—')}</td>"
                f'<td><span class="chip {read_chip}">{esc(t["read_status"])}</span></td>'
                "</tr>"
            )
        more = (
            f'<p class="empty">+{len(payload["trail"]) - 40} weitere</p>'
            if len(payload["trail"]) > 40
            else ""
        )
        parts.append(
            '<div class="card card--flush"><table class="tbl"><thead><tr>'
            "<th>Datum</th><th>Quelle</th><th>Richtung</th><th>Betreff</th>"
            "<th>Status</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
            + more
        )
    return "".join(parts)
