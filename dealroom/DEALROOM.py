#!/usr/bin/env python3
"""DEALROOM — M&A execution workspace for Repuro."""

import argparse
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console (avoids UnicodeEncodeError for non-ASCII chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import settings
from src.db import get_conn, resolve_folder


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _col(value: str, width: int) -> str:
    if value is None:
        value = ""
    return str(value)[:width].ljust(width)


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_deals(args) -> None:
    conn = get_conn()
    rows = conn.execute(
        "SELECT code_name, deal_stage, company_name, domain FROM deals ORDER BY deal_stage, code_name"
    ).fetchall()

    if not rows:
        print("No deals found.")
        return

    header = f"{'CODE':<12} {'STAGE':<22} {'COMPANY':<32} {'DOMAIN'}"
    print(header)
    print("-" * len(header))
    for r in rows:
        domain = r["domain"] or "[unlinked]"
        print(
            f"{_col(r['code_name'], 12)} {_col(r['deal_stage'], 22)} {_col(r['company_name'], 32)} {domain}"
        )
    conn.close()


def cmd_status(args) -> None:
    conn = get_conn()

    # DB file size
    db_path = settings.DB_PATH
    size_kb = int(db_path.stat().st_size / 1024) if db_path.exists() else 0
    print(f"dealroom.db: {db_path} ({size_kb} KB)")

    # ALLEX link
    allex_path = settings.ALLEX_PIPELINE_DB
    if allex_path.exists():
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM allex.company_records"
            ).fetchone()[0]
            print(f"ALLEX: {allex_path} OK attached ({count} records)")
        except Exception:
            print(f"ALLEX: {allex_path} OK attached (company_records unavailable)")
    else:
        print(f"ALLEX: {allex_path} [not found]")

    # DEALS_DIR
    deals_dir = settings.DEALS_DIR
    if deals_dir.exists():
        print(f"DEALS_DIR: {deals_dir} OK exists")
    else:
        print(f"DEALS_DIR: {deals_dir} [not found]")

    print()

    # Table row counts
    tables = [
        "deals",
        "deal_documents",
        "deal_financials",
        "deal_commercial",
        "deal_customers",
        "deal_valuations",
        "deal_questions",
        "deal_actions",
        "deal_emails",
        "deal_meetings",
        "deal_notes",
        "deal_model_params",
        "deal_contacts",
        "deal_manual_gates",
        "deal_scorecard_config",
        "deal_scorecard_results",
        "deal_backlog",
        "deal_employees",
        "deal_suppliers",
        "deal_competitors",
        "deal_dd_items",
    ]
    print(f"{'Table':<22} {'Rows':>6}")
    print("-" * 30)
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            n = "?"
        print(f"{t:<22} {str(n):>6}")

    print()

    # Deal folder status
    print("Deal folders (OneDrive):")
    deals = conn.execute(
        "SELECT code_name, folder_path FROM deals ORDER BY code_name"
    ).fetchall()
    for d in deals:
        folder = resolve_folder(d["code_name"])
        if folder:
            status = f"OK  {folder.name}"
        elif d["folder_path"]:
            status = f"MISSING  {d['folder_path']} [not found on disk]"
        else:
            status = "[no folder configured]"
        print(f"  {d['code_name']:<12} {status}")

    conn.close()


def cmd_stage(args) -> None:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, deal_stage FROM deals WHERE code_name = ?", (args.deal,)
    ).fetchone()
    if not row:
        print(f"Deal not found: {args.deal}")
        sys.exit(1)
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE deals SET deal_stage = ?, stage_entered_at = ? WHERE code_name = ?",
        (args.set, now, args.deal),
    )
    conn.commit()
    print(f"{args.deal}: {row['deal_stage']} → {args.set}")
    conn.close()


def cmd_note(args) -> None:
    import uuid
    from datetime import datetime, timezone

    conn = get_conn()
    row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (args.deal,)
    ).fetchone()
    if not row:
        print(f"Deal not found: {args.deal}")
        sys.exit(1)
    domain = row["domain"] or args.deal.lower()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO deal_notes (id, domain, note, created_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), domain, args.text, now),
    )
    conn.commit()
    print(f"Note added to {args.deal}.")
    conn.close()


def cmd_ingest_docs(args) -> None:
    from src.ingest import scan_deal

    conn = get_conn()

    if args.deal:
        deals_to_scan = [args.deal]
    elif getattr(args, "all", False):
        rows = conn.execute("SELECT code_name FROM deals ORDER BY code_name").fetchall()
        deals_to_scan = [r["code_name"] for r in rows]
    else:
        print("Provide --deal <CODE> or --all")
        conn.close()
        sys.exit(1)

    for code in deals_to_scan:
        try:
            counts = scan_deal(code, conn)
            _print_ingest_report(code, counts)
        except FileNotFoundError as e:
            print(f"\n  {code}: {e}")
        except ValueError as e:
            print(f"\n  {code}: {e}")
    conn.close()


def _print_ingest_report(code_name: str, counts: dict) -> None:
    print(f"\n{code_name}  ({counts['total']} files total, {counts['new']} new)")
    if not counts["by_type"]:
        print("  (no files found)")
        return
    print(f"  {'Type':<22} {'New':>5}  {'Already reg':>11}")
    print("  " + "-" * 42)
    for doc_type, c in sorted(counts["by_type"].items()):
        print(f"  {doc_type:<22} {c['new']:>5}  {c['skipped']:>11}")


def cmd_extract(args) -> None:
    from src.data import extract_deal

    conn = get_conn()

    if args.deal:
        deals_to_run = [args.deal]
    elif getattr(args, "all", False):
        rows = conn.execute("SELECT code_name FROM deals ORDER BY code_name").fetchall()
        deals_to_run = [r["code_name"] for r in rows]
    else:
        print("Provide --deal <CODE> or --all")
        conn.close()
        sys.exit(1)

    for code in deals_to_run:
        print(f"\n{code}:")
        try:
            result = extract_deal(conn, code, dry_run=getattr(args, "dry_run", False))
            print(
                f"  Files: {result['files_processed']}  Rows: {result['rows_written']}  "
                f"Conflicts: {result['conflicts']}  Flags: {len(result.get('flags', []))}"
            )
            for flag in result.get("flags", []):
                print(f"  [FLAG] {flag}")
            for err in result.get("errors", []):
                print(f"  [ERROR] {err}")
            for skip in result.get("skipped", []):
                print(f"  [SKIP] {skip}")
        except ValueError as e:
            print(f"  {e}")
    conn.close()


def cmd_dashboard(args) -> None:
    from src.dashboard import serve_dashboard

    conn = get_conn()
    serve_dashboard(
        conn,
        code_name=getattr(args, "deal", None),
        port=getattr(args, "port", 8090),
        serve=getattr(args, "serve", False),
    )
    conn.close()


def cmd_model(args) -> None:
    from src.model import read_model

    conn = get_conn()

    if args.deal:
        deals_to_run = [args.deal]
    elif getattr(args, "all", False):
        rows = conn.execute("SELECT code_name FROM deals ORDER BY code_name").fetchall()
        deals_to_run = [r["code_name"] for r in rows]
    else:
        print("Provide --deal <CODE> or --all")
        conn.close()
        sys.exit(1)

    for code in deals_to_run:
        print(f"\n{code}:")
        try:
            result = read_model(conn, code, dry_run=getattr(args, "dry_run", False))
            if result.get("errors"):
                for err in result["errors"]:
                    print(f"  [ERROR] {err}")
            if result.get("model_file"):
                print(f"  Model: {result['model_file']}")
                print(f"  Years: {', '.join(result.get('years', []))}")
                if result.get("dry_run"):
                    print("  [DRY RUN] No data written")
                    if result.get("pnl_data"):
                        for yr, vals in sorted(result["pnl_data"].items()):
                            rev = vals.get("revenue", "?")
                            ebitda = vals.get("ebitda_adj", "?")
                            print(f"    {yr}: revenue={rev}, ebitda_adj={ebitda}")
                    if result.get("bewertung"):
                        bew = result["bewertung"]
                        print(
                            f"    Bewertung: EBITDA basis={bew.get('ebitda_adj', '?')}, "
                            f"EV@closing={bew.get('ev_at_closing', '?')}, "
                            f"Equity={bew.get('equity_value', '?')}"
                        )
                else:
                    print(
                        f"  Rows written: {result['pnl_rows_written']}  "
                        f"Valuation: {'yes' if result['valuation_written'] else 'no'}  "
                        f"Conflicts: {result['conflicts_found']}"
                    )
        except ValueError as e:
            print(f"  {e}")
    conn.close()


def cmd_draft_rfi(args) -> None:
    from src.generate.rfi import generate_rfi

    conn = get_conn()
    result = generate_rfi(conn, args.deal, dry_run=getattr(args, "dry_run", False))
    n = len(result["questions"])
    print(
        f"\n{result['code_name']}: {n} questions "
        f"({result['from_corpus']} template, {result['from_data']} data-driven, "
        f"{result['from_conflicts']} conflicts)"
    )
    if result["dry_run"]:
        print("  [DRY RUN]")
        for q in result["questions"]:
            badge = f"[{q['source'].upper()[:18]}]"
            print(f"  {badge} [{q['category']}] {q['question'][:90]}")
    else:
        print(f"  Rows written: {result['rows_written']}")
        if result["doc_path"]:
            print(f"  PDF draft: {result['doc_path']}")
    conn.close()


def cmd_rfi(args) -> None:
    conn = get_conn()
    row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (args.deal,)
    ).fetchone()
    if not row:
        print(f"Deal not found: {args.deal}")
        sys.exit(1)
    domain = row["domain"] or args.deal.lower()

    if getattr(args, "mark_sent", False):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        n = conn.execute(
            "UPDATE deal_questions SET status='sent', sent_at=? WHERE domain=? AND status='draft'",
            (now, domain),
        ).rowcount
        stage_row = conn.execute(
            "SELECT deal_stage FROM deals WHERE code_name=?", (args.deal,)
        ).fetchone()
        conn.commit()
        print(f"{args.deal}: {n} questions marked sent.")

    elif getattr(args, "list", False):
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM deal_questions "
            "WHERE domain=? GROUP BY status ORDER BY status",
            (domain,),
        ).fetchall()
        total = sum(r["n"] for r in rows)
        for r in rows:
            print(f"  {r['status']:<12} {r['n']}")
        print(f"  {'TOTAL':<12} {total}")

    elif getattr(args, "answer_id", None):
        from datetime import datetime, timezone

        q = conn.execute(
            "SELECT id, question, status FROM deal_questions WHERE id = ? AND domain = ?",
            (args.answer_id, domain),
        ).fetchone()
        if not q:
            print(f"Question {args.answer_id!r} not found for {args.deal}")
            sys.exit(1)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """UPDATE deal_questions
               SET answer = ?, answer_source = ?, status = 'answered', answered_at = ?
               WHERE id = ?""",
            (args.text, getattr(args, "source", None), now, args.answer_id),
        )
        conn.commit()
        print(f"Answered: {q['question'][:80]}")
        if getattr(args, "source", None):
            print(f"  Source: {args.source}")
    else:
        print("Provide --mark-sent, --list, or --answer-id <ID> --text <answer>")
    conn.close()


def cmd_scenario(args) -> None:
    """Show or save valuation scenario for a deal."""
    from src.valuation import build_model_context, save_model_params

    conn = get_conn()
    deal = conn.execute(
        "SELECT * FROM deals WHERE code_name = ? COLLATE NOCASE", (args.deal,)
    ).fetchone()
    if not deal:
        print(f"Deal not found: {args.deal}")
        sys.exit(1)

    domain = deal["domain"] or deal["code_name"].lower()
    scenario = getattr(args, "scenario", "base") or "base"

    ctx = build_model_context(conn, domain, scenario)

    # Apply CLI overrides
    overrides = {}
    if args.ebitda is not None:
        overrides["ebitda_basis_override"] = args.ebitda
    if args.ebit is not None:
        overrides["ebit_basis_override"] = args.ebit
    if args.multiple is not None:
        overrides["multiple"] = args.multiple
    if args.cash is not None:
        overrides["cash_at_closing"] = args.cash
    if args.vendor_loan is not None:
        overrides["vendor_loan"] = args.vendor_loan
    if args.earnout is not None:
        overrides["earnout_anticipated"] = args.earnout
    if args.net_debt is not None:
        overrides["net_debt"] = args.net_debt

    if overrides:
        from src.valuation import compute_waterfall, compute_earnout_matrix

        p = ctx["params"]
        p.update(overrides)

        ebitda = overrides.get("ebitda_basis_override", ctx["ebitda_basis"])
        ebit = overrides.get("ebit_basis_override", ctx["ebit_basis"])
        da = ctx["da_amount"]
        if ebitda and not ebit:
            ebit = ebitda - abs(da)
        elif ebit and not ebitda:
            ebitda = ebit + abs(da)

        tiers = p.get("earnout_tiers_json", [])
        if isinstance(tiers, str):
            import json

            tiers = json.loads(tiers)
        tiers = tiers or []

        wf = compute_waterfall(
            ebitda_basis=ebitda,
            ebit_basis=ebit,
            multiple=p.get("multiple", 4.0),
            net_debt=p.get("net_debt", 0),
            permitted_leakage=p.get("permitted_leakage", 0),
            cash_at_closing=p.get("cash_at_closing", 0),
            vendor_loan=p.get("vendor_loan", 0),
            earnout_anticipated=p.get("earnout_anticipated", 0),
            earnout_tiers=tiers,
        )
        ctx["waterfall"] = wf
        ctx["ebitda_basis"] = ebitda
        ctx["ebit_basis"] = ebit

        fixed = (p.get("cash_at_closing", 0) or 0) + (p.get("vendor_loan", 0) or 0)
        em = compute_earnout_matrix(
            ebit_anchor=p.get("earnout_ebit_anchor", ebit) or ebit,
            step=p.get("earnout_step", 25) or 25,
            tiers=tiers,
            fixed_payment=fixed,
            net_debt=p.get("net_debt", 0) or 0,
            da_amount=da or 0,
            base_ebitda=ebitda or 0,
        )
        ctx["earnout_matrix"] = em

    # Save if requested
    if getattr(args, "save", None):
        save_name = args.save
        save_params = dict(ctx["params"])
        save_params.update(overrides)
        save_model_params(conn, domain, save_params, save_name)
        print(f"Scenario '{save_name}' saved for {args.deal}.\n")

    # Print waterfall
    wf = ctx["waterfall"]
    eb = ctx["ebitda_basis"]
    ei = ctx["ebit_basis"]
    da = ctx["da_amount"]
    nd = wf["net_debt"]

    def _fmt(v: float) -> str:
        if v < 0:
            return f"({abs(v):,.0f})"
        return f"{v:,.0f}"

    print(f"{args.deal} — {scenario.title()} Scenario")
    print(
        f"EBITDA basis: {_fmt(eb)} | EBIT basis: {_fmt(ei)} | D&A: {_fmt(da)} | Net Debt: {_fmt(nd)}"
    )
    print()
    print(
        f"  EV at closing:    {_fmt(wf['ev_at_closing']):>8}  ({wf['multiple_at_closing']:.1f}x on EBITDA)"
    )
    print(
        f"  EV anticipated:   {_fmt(wf['ev_anticipated']):>8}  ({wf['multiple_anticipated']:.1f}x)"
    )
    print(
        f"  EV total:         {_fmt(wf['ev_total']):>8}  ({wf['multiple_total']:.1f}x)"
    )
    print(f"  +/- Net Debt:     {_fmt(nd):>8}")
    print(f"  Equity Value:     {_fmt(wf['equity_value']):>8}")
    print(f"    At Closing  {wf['cash_pct']:>3.0f}%  {_fmt(wf['cash_at_closing']):>8}")
    print(
        f"    Vendor Loan {wf['vendor_loan_pct']:>3.0f}%  {_fmt(wf['vendor_loan']):>8}"
    )
    print(
        f"    Earn-Out    {wf['earnout_pct']:>3.0f}%  {_fmt(wf['earnout_anticipated']):>8}"
    )
    print(f"    Super EO           {_fmt(wf['super_earnout']):>8}")

    # Print earn-out matrix
    em = ctx.get("earnout_matrix", [])
    if em:
        p = ctx["params"]
        anchor = p.get("earnout_ebit_anchor", ei) or ei
        step = p.get("earnout_step", 25) or 25
        print(
            f"\n  Earn-Out Scenarios (EBIT anchor: {_fmt(anchor)}, step: {_fmt(step)}):"
        )
        # Header
        ebit_vals = [f"{s['ebit']:>7.0f}" for s in em]
        print(f"    {'EBIT':>12}  " + "  ".join(ebit_vals))
        ebitda_vals = [f"{s['ebitda']:>7.0f}" for s in em]
        print(f"    {'EBITDA':>12}  " + "  ".join(ebitda_vals))
        eo_vals = [f"{s['earnout']:>7.0f}" for s in em]
        print(f"    {'Earn-Out':>12}  " + "  ".join(eo_vals))
        total_vals = [f"{s['kaufpreis']:>7.0f}" for s in em]
        print(f"    {'Kaufpreis':>12}  " + "  ".join(total_vals))
        ev_vals = [f"{s['ev']:>7.0f}" for s in em]
        print(f"    {'EV':>12}  " + "  ".join(ev_vals))
        m_vals = [f"{s['multiple']:>6.1f}x" for s in em]
        print(f"    {'EV/EBITDA':>12}  " + "  ".join(m_vals))

    conn.close()


def cmd_draft_onepager(args) -> None:
    from src.generate.onepager import generate_onepager
    from src.dashboard import _ensure_onepager_columns

    conn = get_conn()
    _ensure_onepager_columns(conn)
    quadrants = [args.quadrant] if args.quadrant else None
    deals_to_run = []

    if args.all:
        rows = conn.execute(
            "SELECT code_name FROM deals WHERE deal_stage NOT IN ('dead', 'on_hold', 'closed') ORDER BY code_name"
        ).fetchall()
        deals_to_run = [r["code_name"] for r in rows]
    elif args.deal:
        deals_to_run = [args.deal]
    else:
        print("Specify --deal CODE_NAME or --all")
        conn.close()
        return

    for deal_name in deals_to_run:
        try:
            results = generate_onepager(
                conn, deal_name, quadrants=quadrants, force=args.force
            )
            if results:
                print(f"  {deal_name}: generated {list(results.keys())}")
            else:
                print(f"  {deal_name}: skipped (edited after generation, use --force)")
        except Exception as e:
            print(f"  {deal_name}: ERROR — {e}")

    conn.close()


def cmd_ingest_commercial(args) -> None:
    from src.commercial import ingest_commercial

    conn = get_conn()
    if not args.deal:
        print("Provide --deal <CODE_NAME>")
        sys.exit(1)

    result = ingest_commercial(
        conn,
        args.deal,
        file_path=getattr(args, "file", None),
        auto=getattr(args, "auto", False),
        dry_run=getattr(args, "dry_run", False),
        force=getattr(args, "force", False),
    )
    print(
        f"\n  Files: {result['files_processed']}  "
        f"Rows: {result['rows_written']}  "
        f"KPIs: {result.get('kpis_derived', 0)}"
    )
    for xc in result.get("cross_checks", []):
        status = xc.get("status", "?")
        delta = xc.get("delta_pct")
        year = xc.get("fiscal_year", "?")
        delta_str = f"{delta:+.1f}%" if delta is not None else "n/a"
        print(f"  Cross-check {year}: {status} (delta {delta_str})")
    conn.close()


def cmd_ingest_databook(args) -> None:
    """Ingest a Repuro CDD databook (DR-M25) + run the tie-out validation gate."""
    from src.databook import ingest, validate

    conn = get_conn()
    counts = ingest(conn, args.deal, args.file)
    print(f"Ingested CDD databook for {args.deal}:")
    for k, v in counts.items():
        print(f"  {k}: {v}")

    result = validate(conn, args.deal, args.file)
    print(f"\nTie-out vs databook: {result['passed']}/{result['total']} checks passed")
    if result["failed"]:
        print(f"  FAILED: {result['failed']}")
        for f in result["failures"][:25]:
            print(f"  - {f['check']}: expected={f['expected']} actual={f['actual']}")
        sys.exit(1)
    conn.close()


def cmd_review_commercial(args) -> None:
    from src.commercial import approve_data, review_summary

    conn = get_conn()
    domain_row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (args.deal,)
    ).fetchone()
    if not domain_row:
        print(f"Deal not found: {args.deal}")
        sys.exit(1)
    domain = domain_row["domain"] or args.deal.lower()

    if getattr(args, "approve", False):
        table = getattr(args, "table", None) or "deal_customers"
        n = approve_data(conn, domain, table)
        print(f"Approved {n} rows in {table} for {args.deal}")
    else:
        summary = review_summary(conn, domain)
        for tbl, info in summary.get("tables", {}).items():
            auth = "APPROVED" if info.get("is_authoritative") else "PENDING"
            print(
                f"  {tbl}: {info['count']} rows, years={info.get('fiscal_years')}, {auth}"
            )
        if summary.get("top_customers"):
            print("\n  Top customers (latest year):")
            for c in summary["top_customers"][:10]:
                print(
                    f"    {c['name']:<40} {c['revenue_k'] or 0:>8.1f} K€  ({c['pct']:.1f}%)"
                    if c.get("pct") is not None
                    else f"    {c['name']:<40} {c['revenue_k'] or 0:>8.1f} K€"
                )
        for xc in summary.get("cross_checks", []):
            delta_str = (
                f"{xc['delta_pct']:+.1f}%" if xc.get("delta_pct") is not None else "n/a"
            )
            print(
                f"  Cross-check {xc['fiscal_year']}: {xc['status']} (delta {delta_str})"
            )
        if summary.get("kpis"):
            print("\n  KPIs:")
            for kpi in summary["kpis"]:
                unit = kpi.get("unit", "")
                print(f"    {kpi['metric']:<30} {kpi['value']:>10.1f} {unit}")
    conn.close()


def cmd_derive_kpis(args) -> None:
    from src.commercial import derive_kpis

    conn = get_conn()
    domain_row = conn.execute(
        "SELECT domain FROM deals WHERE code_name = ?", (args.deal,)
    ).fetchone()
    if not domain_row:
        print(f"Deal not found: {args.deal}")
        sys.exit(1)
    domain = domain_row["domain"] or args.deal.lower()

    result = derive_kpis(
        conn,
        domain,
        fiscal_year=getattr(args, "year", None),
        dry_run=getattr(args, "dry_run", False),
    )
    print(
        f"  KPIs written: {result['kpis_written']}  "
        f"Years: {result.get('fiscal_years', [])}"
    )
    conn.close()


def cmd_golden_check(args) -> None:
    """Validate golden corpus health (DR-GC)."""
    from src.golden import check_golden_health

    health = check_golden_health()
    print(
        f"Golden corpus: {health['total']} files across {sum(1 for v in health['by_type'].values() if v)} types\n"
    )

    for dt, count in sorted(health["by_type"].items()):
        status = f"{count} file(s)" if count else "EMPTY"
        print(f"  {dt:<12} {status}")

    if health["missing"]:
        print(f"\nMissing files ({len(health['missing'])}):")
        for p in health["missing"]:
            print(f"  - {p}")

    if health["gaps"]:
        print(f"\nGaps (no files): {', '.join(health['gaps'])}")

    if health["manifest_gaps"]:
        print("\nKnown gaps (from manifest):")
        for g in health["manifest_gaps"]:
            print(f"  - [{g['doc_type']}] {g['note']}")


def _stub(milestone: str, name: str):
    def handler(args):
        print(f"[{milestone}] {name} not implemented yet.")

    return handler


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="DEALROOM",
        description="M&A execution workspace for Repuro",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # deals
    p_deals = sub.add_parser("deals", help="List all active deals")
    p_deals.set_defaults(func=cmd_deals)

    # status
    p_status = sub.add_parser("status", help="DB state and folder inventory")
    p_status.set_defaults(func=cmd_status)

    # stage
    p_stage = sub.add_parser("stage", help="Update deal stage")
    p_stage.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_stage.add_argument("--set", required=True, metavar="STAGE", dest="set")
    p_stage.set_defaults(func=cmd_stage)

    # note
    p_note = sub.add_parser("note", help="Add a note to a deal")
    p_note.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_note.add_argument("--text", required=True, metavar="TEXT")
    p_note.set_defaults(func=cmd_note)

    # ingest-docs (DR-M2)
    p_ingest = sub.add_parser(
        "ingest-docs", help="Register documents from OneDrive deal folder"
    )
    p_ingest.add_argument("--deal", metavar="CODE_NAME")
    p_ingest.add_argument("--all", action="store_true", help="Scan all deals")
    p_ingest.set_defaults(func=cmd_ingest_docs)

    # extract (DR-M3)
    p_extract = sub.add_parser(
        "extract", help="Extract financial data from registered documents"
    )
    p_extract.add_argument("--deal", metavar="CODE_NAME")
    p_extract.add_argument("--all", action="store_true", help="Extract all deals")
    p_extract.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_extract.set_defaults(func=cmd_extract)

    # model (DR-M5)
    p_model = sub.add_parser(
        "model", help="Read Excel model — adjusted P&L + valuation"
    )
    p_model.add_argument("--deal", metavar="CODE_NAME")
    p_model.add_argument(
        "--all", action="store_true", help="Read all deals with models"
    )
    p_model.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_model.set_defaults(func=cmd_model)

    # dashboard (DR-M4)
    p_dash = sub.add_parser("dashboard", help="Open deal workspace dashboard")
    p_dash.add_argument("--deal", metavar="CODE_NAME")
    p_dash.add_argument("--serve", action="store_true", help="Start live HTTP server")
    p_dash.add_argument("--port", type=int, default=8090)
    p_dash.set_defaults(func=cmd_dashboard)

    # draft-rfi (DR-M6)
    p_draft_rfi = sub.add_parser("draft-rfi", help="Generate RFI question list")
    p_draft_rfi.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_draft_rfi.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_draft_rfi.set_defaults(func=cmd_draft_rfi)

    # rfi — status management (DR-M6)
    p_rfi = sub.add_parser("rfi", help="RFI status: list questions, mark-sent")
    p_rfi.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_rfi.add_argument("--mark-sent", action="store_true", dest="mark_sent")
    p_rfi.add_argument("--list", action="store_true")
    p_rfi.add_argument("--answer-id", dest="answer_id", metavar="ID")
    p_rfi.add_argument("--text", metavar="ANSWER_TEXT")
    p_rfi.add_argument(
        "--source",
        metavar="SOURCE",
        help="e.g. 'RFI_vAntworten.docx' or 'call 2026-03-30'",
    )
    p_rfi.set_defaults(func=cmd_rfi)

    # scenario (DR-M7)
    p_scenario = sub.add_parser("scenario", help="Show/save valuation scenario")
    p_scenario.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_scenario.add_argument("--scenario", default="base", metavar="NAME")
    p_scenario.add_argument("--ebitda", type=float, metavar="EUR_K")
    p_scenario.add_argument("--ebit", type=float, metavar="EUR_K")
    p_scenario.add_argument("--multiple", type=float)
    p_scenario.add_argument("--cash", type=float, metavar="EUR_K")
    p_scenario.add_argument(
        "--vendor-loan", type=float, dest="vendor_loan", metavar="EUR_K"
    )
    p_scenario.add_argument("--earnout", type=float, metavar="EUR_K")
    p_scenario.add_argument("--net-debt", type=float, dest="net_debt", metavar="EUR_K")
    p_scenario.add_argument(
        "--save", metavar="SCENARIO_NAME", help="Save scenario with this name"
    )
    p_scenario.set_defaults(func=cmd_scenario)

    # draft-onepager (DR-M9)
    p_onepager = sub.add_parser(
        "draft-onepager", help="Generate one-pager quadrant bullets"
    )
    p_onepager.add_argument("--deal", metavar="CODE_NAME")
    p_onepager.add_argument(
        "--all", action="store_true", help="Generate for all active deals"
    )
    p_onepager.add_argument("--force", action="store_true", help="Override edit guard")
    p_onepager.add_argument("--quadrant", choices=["q1", "q3", "q4"], metavar="Q")
    p_onepager.set_defaults(func=cmd_draft_onepager)

    # ingest-commercial (DR-COMMERCIAL)
    p_icom = sub.add_parser(
        "ingest-commercial", help="Extract commercial data (customers, products)"
    )
    p_icom.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_icom.add_argument("--file", metavar="PATH", help="Specific file to process")
    p_icom.add_argument("--auto", action="store_true", help="Skip confirmation")
    p_icom.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_icom.add_argument(
        "--force", action="store_true", help="Re-classify even if cached"
    )
    p_icom.set_defaults(func=cmd_ingest_commercial)

    # review-commercial (DR-COMMERCIAL)
    p_idbk = sub.add_parser(
        "ingest-databook",
        help="Ingest a Repuro CDD databook (invoices, customers, findings) + tie-out",
    )
    p_idbk.add_argument("deal", help="Deal code name, e.g. Mantis")
    p_idbk.add_argument("file", help="Path to the CDD databook xlsx")
    p_idbk.set_defaults(func=cmd_ingest_databook)

    p_rcom = sub.add_parser(
        "review-commercial", help="Review commercial data + approve"
    )
    p_rcom.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_rcom.add_argument("--table", metavar="TABLE", help="e.g. deal_customers")
    p_rcom.add_argument("--approve", action="store_true", help="Set is_authoritative=1")
    p_rcom.set_defaults(func=cmd_review_commercial)

    # derive-kpis (DR-COMMERCIAL)
    p_kpi = sub.add_parser("derive-kpis", help="Compute commercial KPIs")
    p_kpi.add_argument("--deal", required=True, metavar="CODE_NAME")
    p_kpi.add_argument("--year", type=int, metavar="YEAR")
    p_kpi.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_kpi.set_defaults(func=cmd_derive_kpis)

    # golden-check (DR-GC)
    p_golden = sub.add_parser("golden-check", help="Validate golden corpus health")
    p_golden.set_defaults(func=cmd_golden_check)

    # stubs
    stub_commands = [
        ("bench", None, "DR-M7"),
        ("draft-offer", "--deal", "DR-M8"),
        ("draft-email", "--deal", "DR-M10"),
        ("draft-nda", "--deal", "DR-M12"),
        ("sync-granola", "--deal", "DR-M11"),
    ]
    for name, deal_arg, milestone in stub_commands:
        p = sub.add_parser(name)
        if deal_arg:
            p.add_argument(deal_arg, required=False, metavar="CODE_NAME")
        p.set_defaults(func=_stub(milestone, name))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
