"""DEALROOM v2 — one-time migration from v1 (SPEC-DEALROOM-V2.md §3/§8/§10).

Idempotent: rebuilds data/dealroom_v2.db from scratch on every run.
v1 data/dealroom.db is opened READ-ONLY and is never modified — verified by
byte-size + mtime assertion at the end.

Run:  python -m v2.migrate_v1        (from dealroom/)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from v2 import db  # noqa: E402
from v2.naming import artifact_stem, parse_file_date, parse_version  # noqa: E402

# ---------------------------------------------------------------- config ----

# v1 child tables carry placeholder domains for deals whose real domain was
# registered later — remap so the universal FK actually joins.
DOMAIN_REMAP = {
    "cat": "medizinservice-sachsen.de",
    "wolf": "kvg-vertrieb.de",
}

# Tables copied 1:1 (v2 column set ∩ v1 column set; v2-only columns stay NULL).
CARRIED_TABLES = [
    "deal_financials",
    "deal_model_params",
    "deal_valuations",
    "deal_commercial",
    "deal_customers",
    "deal_products",
    "deal_invoices",
    "deal_backlog",
    "deal_suppliers",
    "deal_employees",
    "deal_competitors",
    "deal_dd_items",
    "deal_questions",
    "stakeholders",
    "stakeholder_links",
    "profile_claims",
    "negotiation_strategies",
    "negotiation_rounds",
    "negotiation_round_reviews",
    "negotiation_lessons",
    "negotiation_predictions",
    "communication_trail",
    "portfolio_meta",
]

# v1 doc_type → v2 artifact_type (spec §5 set + granular v1 types kept)
DOC_TYPE_MAP = {
    "offer": "nbo",
    "dd": "dataroom_file",
}

STAGE_CORRECTIONS = [
    # (code_name, to_stage, stage_entered_at, evidence)
    (
        "Fox",
        "due_diligence",
        "2026-06-02",
        "DD läuft: Ebner Stolz LDD/TDD/FDD mandatiert 02.06.2026; Datenanfrage an "
        "Mühlan versandt (Antworten 03.06 fällig). Quelle: deals.md + SPEC v2 §1.",
    ),
    (
        "Mantis",
        "due_diligence",
        "2026-06-02",
        "DD läuft: LOI unterzeichnet 01.06.2026 (AdobeSign); Advisor-Freigabe des "
        "Endoberatung-Ordners; Ebner Stolz mandatiert 02.06; CDD v9 geliefert "
        "10.07. Quelle: deals.md + SPEC v2 §1.",
    ),
    (
        "Lion",
        "indicative_offer",
        "2026-07-08",
        "Aktive Verhandlung, kein Hold: Golland-Absage 03.06 schriftlich, danach "
        "Call + Angebots-Update 260708_v1 erstellt; 23 Verhandlungsrunden im "
        "Negotiation-Modul. Quelle: deals.md + negotiation_rounds.",
    ),
]

AQUA_CORRECTION = {
    "old_code": "Swordfish",
    "new_code": "Aqua",
    "to_stage": "indicative_offer",
    "stage_entered_at": "2026-05-07",
    "evidence": (
        "Swordfish (domain 'aqua', HEGA-Medical GmbH) war fälschlich 'dead' und "
        "unter altem Codenamen geführt. deals.md: Aqua = HEGA-Medical GmbH (Rolf "
        "Hommel), indikatives Angebot eingereicht ~07.05.2026 (Broker Quantum/"
        "Saviello), Management-Meeting 11.06. Umbenennung + Reaktivierung; "
        "bestehende Bewertung (deal_valuations, domain 'aqua') bleibt verknüpft."
    ),
}

TERMS_SEED = [
    # Fox — locked (signed LOI)
    dict(
        code="Fox",
        key="purchase_price_upfront",
        label="Sofortzahlung (EV Closing)",
        num=1600,
        unit="K€",
        status="locked",
        src="Unterzeichnete LOI Com2Med (gegengezeichnet ~26.05.2026)",
        note="4,5x adj. EBITDA",
    ),
    dict(
        code="Fox",
        key="earnout_max",
        label="Earn-Out (max)",
        num=300,
        unit="K€",
        status="locked",
        src="Unterzeichnete LOI Com2Med (gegengezeichnet ~26.05.2026)",
        note=None,
    ),
    dict(
        code="Fox",
        key="ev_total_max",
        label="EV gesamt (max, inkl. EO)",
        num=1900,
        unit="K€",
        status="locked",
        src="Unterzeichnete LOI Com2Med (gegengezeichnet ~26.05.2026)",
        note="5,3x adj. EBITDA",
    ),
    # Mantis — locked (signed LOI)
    dict(
        code="Mantis",
        key="ev_total_max",
        label="EV gesamt (max)",
        num=5965,
        unit="K€",
        status="locked",
        src="Unterzeichnete LOI Endoberatung 01.06.2026 (AdobeSign)",
        note="inkl. Rückbeteiligung",
    ),
    dict(
        code="Mantis",
        key="rueckbeteiligung",
        label="Rückbeteiligung",
        num=500,
        unit="K€",
        status="locked",
        src="Unterzeichnete LOI Endoberatung 01.06.2026 (AdobeSign)",
        note=None,
    ),
    # Cat — agreed 30.06, LOI v7 versandfertig
    dict(
        code="Cat",
        key="purchase_price_upfront",
        label="Brutto-Sofortzahlung",
        num=3400,
        unit="K€",
        status="agreed",
        src="Schröcke-Mail 30.06.2026 (modifizierte Variante 2) + LOI v7 03.07",
        note="abzüglich Nettofinanzverbindlichkeiten per 31.12.2025",
    ),
    dict(
        code="Cat",
        key="earnout_max",
        label="Erfolgszahlung (max)",
        num=2557.5,
        unit="K€",
        status="agreed",
        src="Schröcke-Mail 30.06.2026 (modifizierte Variante 2) + LOI v7 03.07",
        note="je 2026+2027: 2,75 € je 1 € operativer EBIT über 625 K€, "
        "EBIT-Cap 1.090 K€ → max 2 × 1.278,75 K€",
    ),
    dict(
        code="Cat",
        key="ev_total_max",
        label="Gesamtpreis (max)",
        num=5957.5,
        unit="K€",
        status="agreed",
        src="Schröcke-Mail 30.06.2026 (modifizierte Variante 2)",
        note=None,
    ),
    dict(
        code="Cat",
        key="guarantee",
        label="Garantie Erfolgszahlung",
        text="Erfolgszahlung auf Repuro-Ebene garantiert (Variante B)",
        status="agreed",
        src="LOI v7 03.07.2026",
        note=None,
    ),
    dict(
        code="Cat",
        key="earnout_mechanics",
        label="EBIT-Mechanik",
        text="Nachfolge-GF-Kosten mindern EBIT nicht; Budget 2027 gemeinsam; "
        "EBIT-Definition = v6-Wortlaut unverändert (Roman 03.07)",
        status="agreed",
        src="LOI v7 03.07.2026",
        note=None,
    ),
    dict(
        code="Cat",
        key="exclusivity_until",
        label="Exklusivität bis",
        text="2026-10-08",
        unit="date",
        status="agreed",
        src="Zeitplan Schröcke-Mail 30.06.2026",
        note=None,
    ),
    # Mouse — agreed, LOI vS versandfertig (Sign-Ziel 10.07)
    dict(
        code="Mouse",
        key="purchase_price_upfront",
        label="Sofortzahlung",
        num=2000,
        unit="K€",
        status="agreed",
        src="LOI vS 03.07.2026 (Landgraf Laborsysteme)",
        note="Basis 488 K€ EBIT 2025 (535 BWA + 60 GewSt − 107 Tantiemen); "
        "Anpassung ab ±10 K€ Abweichung, 5x vs. festgestellter JA",
    ),
    dict(
        code="Mouse",
        key="earnout_max",
        label="Erfolgszahlung (max)",
        num=750,
        unit="K€",
        status="agreed",
        src="LOI vS 03.07.2026 (Landgraf Laborsysteme)",
        note="3 € je 1 € Ø-EBIT 2026/27 über 450 K€ (nach Tantiemen), "
        "Formel-Cap 700 K€",
    ),
    dict(
        code="Mouse",
        key="seller_commitment",
        label="Verkäufer-Bindung",
        text="Vollzeit bis 31.12.2027, 50–80% als GF bis 31.12.2028; "
        "Nachfolger ab 01.01.2027; 100 K€ + 20 K€ p.P. rückwirkend 01.01.2026",
        status="agreed",
        src="LOI vS 03.07.2026 (Landgraf Laborsysteme)",
        note=None,
    ),
    dict(
        code="Mouse",
        key="exclusivity_until",
        label="Exklusivität bis",
        text="2026-10-30",
        unit="date",
        status="agreed",
        src="LOI vS 03.07.2026 (Landgraf Laborsysteme)",
        note=None,
    ),
    # Lion — round 1 countered, update proposed
    dict(
        code="Lion",
        key="purchase_price_upfront",
        label="Sofortzahlung (Runde 1)",
        num=2500,
        unit="K€",
        status="countered",
        src="Indikatives Angebot 22.05.2026 (deal_valuations R1); "
        "schriftliche Absage Golland 03.06.2026",
        note="EV mid 3.757 K€ lt. Bewertung 22.05",
    ),
    dict(
        code="Lion",
        key="offer_update",
        label="Angebots-Update",
        text="v1 vom 08.07.2026 — offene Punkte: Tantieme 135/140 K€, "
        "EO-Staffelung, Kündigungsschutz +1 Jahr",
        status="proposed",
        src="260708_Golmed_Angebots-Update_v1",
        note=None,
    ),
    # Aqua — proposed (indicative)
    dict(
        code="Aqua",
        key="ev_indicative",
        label="EV indikativ (Range)",
        text="3,0–4,0 M€",
        status="proposed",
        src="Indikatives Angebot ~07.05.2026 (Broker Quantum/Saviello); deals.md",
        note="4,1–5,5x 3-Jahres-Ø adj. EBITDA (~0,7 M€)",
    ),
]

MILESTONES_SEED = [
    # Cat — Zeitplan Schröcke-Mail 30.06 (Quelle: deals.md)
    (
        "Cat",
        "LOI-Unterzeichnung",
        "2026-07-24",
        "Both",
        "Schröcke Urlaub 04.–17.07 — Signatur in Rückkehr-Woche",
    ),
    ("Cat", "Unterlagen + JA 2025", "2026-07-31", "Seller", None),
    ("Cat", "Workshop Chemnitz", None, "Both", "Mitte August (Termin offen)"),
    ("Cat", "CDD/FDD", "2026-08-28", "Repuro", None),
    ("Cat", "Rest-DD", "2026-09-14", "Repuro", None),
    ("Cat", "SPA-Entwurf", "2026-09-18", "Repuro", None),
    ("Cat", "Notartermin Berlin", "2026-10-01", "Both", None),
    ("Cat", "Exklusivität Ende", "2026-10-08", "Both", None),
    # Mouse — Zeitplan LOI vS (Quelle: deals.md)
    (
        "Mouse",
        "LOI-Unterzeichnung",
        "2026-07-10",
        "Both",
        "E-Mail-Draft mit vS-Anhang liegt in Romans Postfach",
    ),
    ("Mouse", "Unterlagen", "2026-07-31", "Seller", None),
    ("Mouse", "JA-Feststellung 2025", "2026-08-31", "Seller", None),
    ("Mouse", "CDD/FDD", "2026-09-11", "Repuro", None),
    ("Mouse", "Rest-DD", "2026-10-02", "Repuro", None),
    ("Mouse", "SPA-Entwurf", "2026-10-09", "Repuro", None),
    ("Mouse", "Notartermin", None, "Both", "Oktober 2026 (Termin offen)"),
    ("Mouse", "Exklusivität Ende", "2026-10-30", "Both", None),
    # Fox — signed LOI timeline
    (
        "Fox",
        "Notartermin",
        "2026-08-21",
        "Both",
        "Quelle: unterzeichnete LOI (Zeitplan)",
    ),
    # Mantis — signed LOI timeline + CDD workshop
    (
        "Mantis",
        "CDD-Workshop (Inputs)",
        "2026-07-14",
        "Repuro",
        "Workshop-Inputs zu CDD v9",
    ),
    (
        "Mantis",
        "Notartermin",
        "2026-08-28",
        "Both",
        "Quelle: unterzeichnete LOI (Zeitplan)",
    ),
]

FRESHNESS_CONFIG = [
    ("activity_decay_days", "14", "Aktive Deals ohne Kontakt > N Tage → flag"),
    ("rfi_high_overdue_days", "10", "Offene HIGH-RFI älter als N Tage → flag"),
    ("milestone_warn_days", "7", "Meilenstein fällig binnen N Tagen → Attention"),
]

# ---------------------------------------------------------------- helpers ---


def table_cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])")]


# ---------------------------------------------------------------- migrate ---


def migrate():
    v1_path = db.v1_db_path()
    v2_path = db.default_db_path()
    if not v1_path.exists():
        sys.exit(f"v1 DB not found: {v1_path}")

    stat_before = (v1_path.stat().st_size, v1_path.stat().st_mtime_ns)
    v1 = db.open_readonly(v1_path)
    report = {"v1": str(v1_path), "v2": str(v2_path), "tables": {}, "diffs": []}

    # 1 — archive export BEFORE anything else (kill list §10: archive-then-drop)
    archive_dir = v1_path.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_file = archive_dir / "deal_data_v1_archive.json"
    rows = [dict(r) for r in v1.execute("SELECT * FROM deal_data_v1_archive")]
    archive_file.write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    report["archive_export"] = {"file": str(archive_file), "rows": len(rows)}

    # 2 — fresh v2 file
    if v2_path.exists():
        v2_path.unlink()
    v2 = db.init_db(v2_path)
    now = db.now_iso()

    # 3 — deals (v1 minus previous_stage/last_contact_at)
    deal_cols = [c for c in table_cols(v2, "deals")]
    v1_deal_cols = set(table_cols(v1, "deals"))
    missing = [c for c in deal_cols if c not in v1_deal_cols]
    if missing:
        sys.exit(f"deals column mismatch — v2 cols absent in v1: {missing}")
    sel = ", ".join(f"[{c}]" for c in deal_cols)
    for row in v1.execute(f"SELECT {sel} FROM deals"):
        v2.execute(
            f"INSERT INTO deals ({', '.join(deal_cols)}) "
            f"VALUES ({', '.join('?' * len(deal_cols))})",
            tuple(row),
        )
    report["tables"]["deals"] = v2.execute("SELECT COUNT(*) FROM deals").fetchone()[0]

    # baseline stage history for every deal (v1 state at migration)
    for r in v2.execute(
        "SELECT domain, code_name, deal_stage, stage_entered_at, added_at FROM deals"
    ).fetchall():
        v2.execute(
            "INSERT INTO deal_stage_history "
            "(domain, code_name, from_stage, to_stage, changed_at, changed_by, evidence) "
            "VALUES (?,?,NULL,?,?,?,?)",
            (
                r["domain"],
                r["code_name"],
                r["deal_stage"],
                r["stage_entered_at"] or r["added_at"],
                "v1-migration",
                "v1-Stand bei Migration (Baseline)",
            ),
        )

    # 4 — stage corrections (spec §8) — each writes history with evidence
    def apply_correction(code, to_stage, entered_at, evidence, rename_to=None):
        row = v2.execute(
            "SELECT domain, code_name, deal_stage FROM deals WHERE code_name=?",
            (code,),
        ).fetchone()
        if not row:
            sys.exit(f"correction target missing: {code}")
        new_code = rename_to or code
        v2.execute(
            "UPDATE deals SET code_name=?, deal_stage=?, stage_entered_at=? "
            "WHERE code_name=?",
            (new_code, to_stage, entered_at, code),
        )
        v2.execute(
            "INSERT INTO deal_stage_history "
            "(domain, code_name, from_stage, to_stage, changed_at, changed_by, evidence) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                row["domain"],
                new_code,
                row["deal_stage"],
                to_stage,
                now,
                "migration (SPEC v2 §8)",
                evidence,
            ),
        )
        report["diffs"].append(
            {
                "deal": new_code,
                "from": row["deal_stage"],
                "to": to_stage,
                "renamed_from": code if rename_to else None,
                "evidence": evidence,
            }
        )

    for code, to_stage, entered_at, evidence in STAGE_CORRECTIONS:
        apply_correction(code, to_stage, entered_at, evidence)

    aq = AQUA_CORRECTION
    sw = v2.execute(
        "SELECT company_name FROM deals WHERE code_name=?", (aq["old_code"],)
    ).fetchone()
    if sw and (sw["company_name"] or "").startswith("HEGA"):
        apply_correction(
            aq["old_code"],
            aq["to_stage"],
            aq["stage_entered_at"],
            aq["evidence"],
            rename_to=aq["new_code"],
        )
    else:
        sys.exit(
            f"Aqua resolution blocked: Swordfish company_name = "
            f"{sw['company_name'] if sw else 'row missing'} — expected HEGA-Medical. "
            "Refusing to guess (NO FABRICATION)."
        )

    # 5 — carried tables (with domain remap on child tables)
    for table in CARRIED_TABLES:
        cols = [c for c in table_cols(v2, table) if c in set(table_cols(v1, table))]
        sel = ", ".join(f"[{c}]" for c in cols)
        rows = v1.execute(f"SELECT {sel} FROM [{table}]").fetchall()
        di = cols.index("domain") if "domain" in cols else None
        ins = (
            f"INSERT INTO [{table}] ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})"
        )
        for row in rows:
            vals = list(row)
            if di is not None and vals[di] in DOMAIN_REMAP:
                vals[di] = DOMAIN_REMAP[vals[di]]
            v2.execute(ins, vals)
        v1_n = v1.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        v2_n = v2.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        report["tables"][table] = v2_n
        assert v1_n == v2_n, f"row count mismatch {table}: {v1_n} != {v2_n}"

    # scorecard_config (renamed from deal_scorecard_config)
    cols = [
        c
        for c in table_cols(v2, "scorecard_config")
        if c in set(table_cols(v1, "deal_scorecard_config"))
    ]
    sel = ", ".join(f"[{c}]" for c in cols)
    for row in v1.execute(f"SELECT {sel} FROM deal_scorecard_config"):
        v2.execute(
            f"INSERT INTO scorecard_config ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            tuple(row),
        )
    report["tables"]["scorecard_config"] = v2.execute(
        "SELECT COUNT(*) FROM scorecard_config"
    ).fetchone()[0]

    # 6 — deal_documents → deal_artifacts (registry with version chains)
    code_by_domain = {
        r["domain"]: r["code_name"]
        for r in v2.execute("SELECT domain, code_name FROM deals")
        if r["domain"]
    }
    docs = [dict(r) for r in v1.execute("SELECT * FROM deal_documents")]
    for d in docs:
        d["domain"] = DOMAIN_REMAP.get(d["domain"], d["domain"])
        d["code_name"] = code_by_domain.get(d["domain"], d["code_name"])
        if d["code_name"] == "Swordfish":
            d["code_name"] = "Aqua"
        d["artifact_type"] = DOC_TYPE_MAP.get(d["doc_type"], d["doc_type"])
        d["version"] = parse_version(d["file_name"])
        d["file_date"] = parse_file_date(d["file_name"])
        d["stem"] = artifact_stem(d["file_name"])

    # v1 ingest-docs double-registered ~98 files (no idempotency on re-run).
    # Registry semantics = one row per file: keep the latest registration.
    by_path: dict[tuple, dict] = {}
    for d in docs:
        key = (d["code_name"], d["file_path"])
        prev = by_path.get(key)
        if prev is None or (d.get("registered_at") or "") > (
            prev.get("registered_at") or ""
        ):
            by_path[key] = d
    deduped = len(docs) - len(by_path)
    docs = list(by_path.values())
    report["deal_documents_deduped"] = deduped

    groups: dict[tuple, list[dict]] = {}
    for d in docs:
        groups.setdefault((d["code_name"], d["artifact_type"], d["stem"]), []).append(d)

    inserted = 0
    for group in groups.values():
        group.sort(
            key=lambda d: (
                d["file_date"] or "0000",
                d["version"] or 0,
                d["registered_at"] or "",
            )
        )
        prev_id = None
        for i, d in enumerate(group):
            status = "current" if i == len(group) - 1 else "superseded"
            cur = v2.execute(
                "INSERT INTO deal_artifacts "
                "(domain, code_name, artifact_type, artifact_subtype, version, "
                " file_name, file_path, file_date, file_size_kb, fiscal_year, "
                " status, supersedes_id, registered_at, note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    d["domain"],
                    d["code_name"],
                    d["artifact_type"],
                    d.get("doc_subtype"),
                    d["version"],
                    d["file_name"],
                    d["file_path"],
                    d["file_date"],
                    d.get("file_size_kb"),
                    d.get("fiscal_year"),
                    status,
                    prev_id,
                    d.get("registered_at") or now,
                    d.get("doc_status_note"),
                ),
            )
            prev_id = cur.lastrowid
            inserted += 1
    report["tables"]["deal_artifacts"] = inserted
    assert inserted == len(docs), "artifact count mismatch"

    # 7 — terms seed (NBO onward, spec §7) — every row cites source_doc
    domain_by_code = {
        r["code_name"]: r["domain"]
        for r in v2.execute("SELECT code_name, domain FROM deals")
    }
    for t in TERMS_SEED:
        v2.execute(
            "INSERT INTO deal_terms "
            "(domain, code_name, term_key, label, value_num, value_text, unit, "
            " status, source_doc, note, changed_at, changed_by) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                domain_by_code.get(t["code"]),
                t["code"],
                t["key"],
                t["label"],
                t.get("num"),
                t.get("text"),
                t.get("unit"),
                t["status"],
                t["src"],
                t.get("note"),
                now,
                "migration (SPEC v2 §7)",
            ),
        )
    report["tables"]["deal_terms"] = len(TERMS_SEED)

    # 8 — milestones seed (LOI Zeitpläne)
    for code, milestone, due, owner, note in MILESTONES_SEED:
        v2.execute(
            "INSERT INTO deal_milestones "
            "(domain, code_name, milestone, due_date, owner, status, source_doc, "
            " note, created_at) VALUES (?,?,?,?,?,'open',?,?,?)",
            (
                domain_by_code.get(code),
                code,
                milestone,
                due,
                owner,
                "deals.md Zeitplan (LOI)",
                note,
                now,
            ),
        )
    report["tables"]["deal_milestones"] = len(MILESTONES_SEED)

    # 9 — freshness config
    for key, value, desc in FRESHNESS_CONFIG:
        v2.execute(
            "INSERT INTO freshness_config (key, value, description) VALUES (?,?,?)",
            (key, value, desc),
        )

    v2.commit()
    v2.close()
    v1.close()

    # 10 — v1 untouched?
    stat_after = (v1_path.stat().st_size, v1_path.stat().st_mtime_ns)
    assert stat_before == stat_after, "v1 DB was modified — INVESTIGATE"
    report["v1_untouched"] = True
    return report


if __name__ == "__main__":
    rep = migrate()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
