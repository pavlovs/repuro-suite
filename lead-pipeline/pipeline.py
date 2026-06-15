#!/usr/bin/env python3
"""Repuro Lead Generation Pipeline — CLI entry point.

Usage:
    python pipeline.py <command> --profile profiles/medtech_germany.json [options]

Commands:
    scrape-wlw   Scrape wer-liefert-was.de for leads (M2)
    ingest       Normalize and deduplicate all sources (M3)
    filter       Apply pre-qualification filters (M4)
    scrape       Scrape company websites (M5)
    classify     AI classification via Claude API (M6)
    enrich       Ownership + email enrichment (M7/M9)
    export       Generate Serienbriefe Excel output (M10)
    export-briefmarken  Export Briefmarken CSV for Deutsche Post
    dashboard    Generate HTML dashboard (M11)
    run-all      Full pipeline end-to-end
    status       Show pipeline state and record counts

Global options:
    --profile PATH   Industry profile JSON (default: profiles/medtech_germany.json)
    --dry-run        No API calls, no file writes
    --verbose        Debug logging
    --limit N        Process only first N records (for testing)
"""

import argparse
import logging
import sys
from pathlib import Path

from src.config import settings
from src.config.profile import load_profile


def _run_all_stages(profile, args: argparse.Namespace) -> None:
    """Run filter → scrape → classify → enrich → ensure-scrape → ensure-enrich → normalize → backfill."""
    import time

    from src.pipeline.enrich import enrich_cmd
    from src.pipeline.filter import apply_hard_filters
    from src.pipeline.scrape import ensure_scrape_for_briefaktion, scrape_batch_cmd

    def _classify():
        from src.pipeline.classify import classify_cmd

        classify_cmd(profile, dry_run=args.dry_run, limit=args.limit)

    def _normalize():
        from src.pipeline.normalize import normalize_cmd

        normalize_cmd(args)

    def _backfill_leistung():
        from src.pipeline.backfill import backfill_leistung_cmd

        backfill_leistung_cmd(args)

    def _backfill_compliments():
        from src.pipeline.backfill import backfill_compliments_cmd

        backfill_compliments_cmd(args)

    def _ensure_enrich():
        from src.pipeline.enrich import ensure_enrich_for_briefaktion

        ensure_enrich_for_briefaktion(profile, dry_run=args.dry_run)

    def _qa_fix():
        from src.pipeline.qa import qa_fix_batch

        qa_fix_batch(dry_run=args.dry_run)

    all_stages = [
        ("filter", lambda: apply_hard_filters(profile=profile, dry_run=args.dry_run)),
        (
            "scrape",
            lambda: scrape_batch_cmd(
                profile, dry_run=args.dry_run, limit=args.limit, source=None
            ),
        ),
        ("classify", _classify),
        ("enrich", lambda: enrich_cmd(profile, dry_run=args.dry_run)),
        ("ensure-scrape", lambda: ensure_scrape_for_briefaktion()),
        ("ensure-enrich", _ensure_enrich),
        ("normalize", _normalize),
        ("qa-fix", _qa_fix),
        ("backfill-leistung", _backfill_leistung),
        ("backfill-compliments", _backfill_compliments),
    ]

    stage_names = [s[0] for s in all_stages]
    from_stage = getattr(args, "from_stage", None)
    if from_stage:
        if from_stage not in stage_names:
            print(f"Unknown stage '{from_stage}'. Available: {', '.join(stage_names)}")
            return
        idx = stage_names.index(from_stage)
        stages = all_stages[idx:]
    else:
        stages = all_stages

    sep = "=" * 55
    total_start = time.time()
    for name, fn in stages:
        print(f"\n{sep}\n  STAGE: {name.upper()}\n{sep}")
        t0 = time.time()
        fn()
        print(f"  [{name}] done in {time.time() - t0:.0f}s")

    print(
        f"\n{sep}\n  run-all complete ({time.time() - total_start:.0f}s total)\n{sep}"
    )


def _run_dashboard(profile, args: argparse.Namespace) -> None:
    import src.pipeline.dashboard as _dash

    if getattr(args, "v1", False) and getattr(args, "v2", False):
        import sys

        print("error: --v1 and --v2 are mutually exclusive", file=sys.stderr)
        sys.exit(2)

    _dash._USE_V2 = getattr(args, "v2", False)
    _dash._USE_V1 = getattr(args, "v1", False)
    _dash._USE_DEV = getattr(args, "dev", False)
    _dash.dashboard_cmd(
        profile,
        dry_run=args.dry_run,
        serve=getattr(args, "serve", False),
        port=getattr(args, "port", 8080),
        source_filter=getattr(args, "source", None),
        no_open=getattr(args, "no_open", False),
    )


def _run_scrape_wlw(profile, args: argparse.Namespace) -> None:
    from src.pipeline.wlw_scraper import scrape_wlw
    from src.utils.knowledge_base import KnowledgeBase

    kb = KnowledgeBase(settings.KNOWLEDGE_BASE_PATH)
    records = scrape_wlw(
        profile, kb=kb, dry_run=args.dry_run, verbose=args.verbose, limit=args.limit
    )
    if not args.dry_run:
        print(f"  Discovered: {len(records)} companies -> {settings.STAGING_WLW_RAW}")
    s = kb.stats()
    print(f"  Knowledge base: {s['domains_cached']} domains cached")


def cmd_status(args: argparse.Namespace) -> None:
    """Show pipeline state — queries pipeline.db for record counts per stage."""
    from src.pipeline.db import get_stage_counts, get_total_count, get_klass_counts

    print(f"\nPipeline status — {settings.PIPELINE_DB_PATH.name}")
    print("-" * 60)

    if not settings.PIPELINE_DB_PATH.exists():
        print("  pipeline.db not found. Run 'python pipeline.py ingest' to start.")
    else:
        total = get_total_count(settings.PIPELINE_DB_PATH)
        stage_counts = get_stage_counts(settings.PIPELINE_DB_PATH)
        klass_counts = get_klass_counts(settings.PIPELINE_DB_PATH)

        stage_labels = [
            ("ingested", "M3 Ingested       "),
            ("filtered", "M4 Filtered       "),
            ("scraped", "M5 Scraped        "),
            ("scrape_failed", "M5 Scrape failed  "),
            ("classified", "M6 Classified     "),
            ("ownership_enriched", "M7 Ownership enr. "),
            ("ownership_gated", "M8 Ownership gate "),
            ("email_enriched", "M9 Email enriched "),
        ]

        print(f"  Total unique companies: {total:,}")
        print()
        for stage, label in stage_labels:
            count = stage_counts.get(stage, 0)
            if count:
                print(f"  {label}  {count:>5,}")

        if klass_counts:
            parts = "  ".join(f"{k}:{v}" for k, v in sorted(klass_counts.items()))
            print(f"\n  Classifications -> {parts}")

        from src.pipeline.db import get_filter_counts, get_scrape_counts

        fc = get_filter_counts(settings.PIPELINE_DB_PATH)
        if fc["pass"] or fc["fail"]:
            print(
                f"\n  M4 Filter: {fc['pass']} passed / {fc['fail']} failed / {fc['pending']} pending"
            )
        sc = get_scrape_counts(settings.PIPELINE_DB_PATH)
        if sc["scraped"] or sc["failed"]:
            print(
                f"  M5 Scrape: {sc['scraped']} ok / {sc['failed']} failed / {sc['pending']} pending"
            )

    # WLW raw CSV (M2 scraper output — still a flat file)
    if settings.STAGING_WLW_RAW.exists():
        with open(settings.STAGING_WLW_RAW, encoding="utf-8") as f:
            wlw_count = sum(1 for _ in f) - 1  # subtract header
        print(
            f"\n  M2 WLW raw CSV:    {wlw_count:>5,}  ({settings.STAGING_WLW_RAW.name})"
        )

    # Knowledge base stats
    if settings.KNOWLEDGE_BASE_PATH.exists():
        from src.utils.knowledge_base import KnowledgeBase

        s = KnowledgeBase(settings.KNOWLEDGE_BASE_PATH).stats()
        print(
            f"\n  Knowledge base: {s['domains_cached']} domains | "
            f"{s['with_text']} with text | "
            f"{s['ownership_cached']} ownership records"
        )

    print("-" * 60)


def cmd_export_db(args: argparse.Namespace) -> None:
    """Copy pipeline.db + knowledge_base.db to a destination folder."""
    import os
    import shutil

    dest = args.dest or Path(os.environ.get("DB_EXPORT_DIR", "")) or settings.OUTPUT_DIR
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    db_files = [
        (settings.PIPELINE_DB_PATH, "pipeline.db"),
        (settings.KNOWLEDGE_BASE_PATH, "knowledge_base.db"),
    ]

    for src, name in db_files:
        if not src.exists():
            print(f"  SKIP {name} — not found at {src}")
            continue
        target = dest / name
        shutil.copy2(src, target)
        size_mb = target.stat().st_size / (1024 * 1024)
        print(f"  Copied {name} ({size_mb:.1f} MB) -> {target}")

    print(f"\nDone. Share the files in {dest} with Flo.")


def main() -> None:
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        "--profile",
        type=Path,
        default=Path("profiles/medtech_germany.json"),
        help="Path to industry profile JSON (default: profiles/medtech_germany.json)",
    )
    base_parser.add_argument(
        "--dry-run", action="store_true", help="No API calls, no file writes"
    )
    base_parser.add_argument(
        "--verbose", action="store_true", help="Debug-level logging"
    )
    base_parser.add_argument(
        "--limit", type=int, default=0, help="Process only first N records"
    )

    parser = argparse.ArgumentParser(
        description="Repuro Lead Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
        parents=[base_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "scrape-wlw",
        help="Scrape wer-liefert-was.de for leads (M2)",
        parents=[base_parser],
    )
    subparsers.add_parser(
        "ingest",
        help="Normalize and deduplicate all sources (M3)",
        parents=[base_parser],
    )
    subparsers.add_parser(
        "filter",
        help="Apply pre-qualification hard filters (M4)",
        parents=[base_parser],
    )
    scrape_parser = subparsers.add_parser(
        "scrape", help="Scrape company websites for text (M5)", parents=[base_parser]
    )
    scrape_parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Filter by source (e.g. MANUAL) — scrapes records without scraped_text, keeps pipeline_stage unchanged",
    )
    subparsers.add_parser(
        "classify",
        help="AI classification via Claude CLI (M6)",
        parents=[base_parser],
    )
    subparsers.add_parser(
        "enrich", help="Ownership + email enrichment (M7/M9)", parents=[base_parser]
    )
    export_parser = subparsers.add_parser(
        "export", help="Generate Serienbriefe Excel output (M10)", parents=[base_parser]
    )
    export_parser.add_argument(
        "--approved-only",
        action="store_true",
        help="Export only records with approved_for_sendout=1 (M17)",
    )
    export_pdf_parser = subparsers.add_parser(
        "export-pdf",
        help="Generate Serienbriefe PDF letters (one letter per page, M22)",
        parents=[base_parser],
    )
    export_pdf_parser.add_argument(
        "--approved-only",
        action="store_true",
        help="Export only records with approved_for_sendout=1",
    )
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Generate HTML dashboard (M11)", parents=[base_parser]
    )
    dashboard_parser.add_argument(
        "--serve",
        action="store_true",
        help="Start local HTTP server with write-back API (localhost:8080)",
    )
    dashboard_parser.add_argument(
        "--port", type=int, default=8080, help="Port for --serve mode (default: 8080)"
    )
    dashboard_parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Filter dashboard to only show records from this source (e.g. MANUAL)",
    )
    dashboard_parser.add_argument(
        "--v2",
        action="store_true",
        help="Serve dashboard v2 (experimental — M28)",
    )
    dashboard_parser.add_argument(
        "--v1",
        action="store_true",
        default=False,
        help="Force v1 template (rollback from v2)",
    )
    dashboard_parser.add_argument(
        "--dev",
        action="store_true",
        default=False,
        help="Dev mode: shows [DEV] version badge. Use port 8081 to test without disrupting Flo on 8080.",
    )
    dashboard_parser.add_argument(
        "--no-open",
        action="store_true",
        default=False,
        help="Suppress auto-opening browser tab on --serve start.",
    )
    audit_parser = subparsers.add_parser(
        "audit-dedup",
        help="Audit and fix already-approached companies that slipped dedup (M12)",
        parents=[base_parser],
    )
    audit_parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply fixes: mark matched records as already_approached=1",
    )
    audit_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="PATH",
        help="Write matched records to CSV at PATH",
    )
    subparsers.add_parser(
        "ingest-serienbriefe",
        help="Ingest Serienbriefe sheet as full approached records with briefaktion tags (M14)",
        parents=[base_parser],
    )
    guide_parser = subparsers.add_parser(
        "build-compliment-guide",
        help="Build compliment style guide from Serienbriefe corpus (M16)",
        parents=[base_parser],
    )
    subparsers.add_parser(
        "enrich-regions",
        help="Populate region + region_prep from Städte-Regionen-Matching sheet (M17)",
        parents=[base_parser],
    )
    subparsers.add_parser(
        "normalize",
        help="Title-case, umlaut, anrede, salutation normalization for A/B records (M18)",
        parents=[base_parser],
    )
    subparsers.add_parser(
        "backfill-from-excel",
        help="Fill missing K1/K2/leistung/region from Serienbriefe Excel (M18)",
        parents=[base_parser],
    )
    bl_parser = subparsers.add_parser(
        "backfill-leistung",
        help="AI-generate leistung fields for records with scraped_text (M18)",
        parents=[base_parser],
    )
    bl_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing leistung/mehrwerte values (use after prompt fix)",
    )
    bc_parser = subparsers.add_parser(
        "backfill-compliments",
        help="AI-generate K1/K2 for records with scraped_text (M18)",
        parents=[base_parser],
    )
    cl_parser = subparsers.add_parser(
        "check-letter",
        help="Validate Serienbrief fields for grammar/consistency (M18)",
        parents=[base_parser],
    )
    cl_parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Skip AI grammar check, only run rule-based validation",
    )
    subparsers.add_parser(
        "prepare-manual",
        help="Pre-enrich: fix full_name for MANUAL-source records (scrape impressum, extract legal name)",
        parents=[base_parser],
    )
    bf_imp_parser = subparsers.add_parser(
        "backfill-impressum",
        help="Extract impressum_name from scraped_text via AI (M20)",
        parents=[base_parser],
    )
    bf_imp_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing impressum_name (default: only fill empty)",
    )
    subparsers.add_parser(
        "enrich-gf",
        help="Extract GF name/address/email from impressum pages for A/B records (M21)",
        parents=[base_parser],
    )
    ingest_manual_parser = subparsers.add_parser(
        "ingest-manual",
        help="Ingest pre-classified companies from manual Excel input (source=MANUAL)",
        parents=[base_parser],
    )
    ingest_manual_parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to Excel file with ALLEX input sheet",
    )
    ingest_manual_parser.add_argument(
        "--sheet",
        type=str,
        default="ALLEX input",
        help="Sheet name (default: 'ALLEX input')",
    )
    ingest_manual_parser.add_argument(
        "--col-domain",
        type=int,
        default=3,
        help="0-based column index for domain (default: 3 = col D)",
    )
    ingest_manual_parser.add_argument(
        "--col-name",
        type=int,
        default=4,
        help="0-based column index for company name (default: 4 = col E)",
    )
    ingest_manual_parser.add_argument(
        "--col-klass",
        type=int,
        default=7,
        help="0-based column index for classification (default: 7 = col H)",
    )
    ingest_manual_parser.add_argument(
        "--col-source",
        type=int,
        default=1,
        help="0-based column index for source (default: 1 = col B)",
    )
    run_all_parser = subparsers.add_parser(
        "run-all", help="Full pipeline end-to-end", parents=[base_parser]
    )
    run_all_parser.add_argument(
        "--from-stage",
        choices=[
            "filter",
            "scrape",
            "classify",
            "enrich",
            "normalize",
            "backfill-leistung",
            "backfill-compliments",
        ],
        default=None,
        help="Start from this stage (skip earlier stages)",
    )
    subparsers.add_parser(
        "status", help="Show pipeline state and record counts", parents=[base_parser]
    )
    briefmarken_parser = subparsers.add_parser(
        "export-briefmarken",
        help="Export Briefmarken (postage stamp) CSV for Deutsche Post",
        parents=[base_parser],
    )
    briefmarken_parser.add_argument(
        "--batch",
        type=str,
        required=True,
        help="Briefaktion batch label (e.g. BA8, testbatch)",
    )
    briefmarken_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: data/exports/{date}_Briefmarken_{batch}.csv)",
    )
    export_db_parser = subparsers.add_parser(
        "export-db",
        help="Copy pipeline.db + knowledge_base.db to a destination folder",
        parents=[base_parser],
    )
    export_db_parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Destination folder (default: DB_EXPORT_DIR from .env, or data/output/)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger(__name__)

    if args.command == "status":
        cmd_status(args)
        return

    if args.command == "export-db":
        cmd_export_db(args)
        return

    if args.command == "export-briefmarken":
        from datetime import datetime as _dt

        from src.pipeline.export_briefmarken import export_briefmarken

        db_path = settings.PIPELINE_DB_PATH
        batch = args.batch

        output = args.output
        if output is None:
            exports_dir = settings.DATA_DIR / "exports"
            exports_dir.mkdir(parents=True, exist_ok=True)
            date_str = _dt.now().strftime("%y%m%d")
            output = exports_dir / f"{date_str}_Briefmarken_{batch}.csv"

        result = export_briefmarken(db_path, batch, output)
        print(f"\nBriefmarken export complete — {batch}")
        print("-" * 50)
        print(f"  Records exported:       {result['exported']}")
        print(f"  Truncation warnings:    {result['truncation_warnings']}")
        print(f"  Incomplete skipped:     {result['incomplete_skipped']}")
        print(f"  Output: {result['output_path']}")
        if result["warnings_path"]:
            print(f"  Warnings: {result['warnings_path']}")
        print("-" * 50)
        return

    if args.command == "build-compliment-guide":
        from src.pipeline.compliment_guide import build_guide

        stats = build_guide(
            dry_run=args.dry_run,
        )
        print("\nCompliment guide build complete")
        print("-" * 50)
        print(f"  Corpus entries:    {stats['total_count']}")
        print(f"  K1 filled:         {stats['k1_count']}")
        print(f"  K2 filled:         {stats['k2_count']}")
        print(f"  Positive-response: {stats['positive_count']}")
        if stats["guide_written"]:
            print("  Guide written:     src/config/compliment_guide.md")
        elif args.dry_run:
            print("  DRY RUN — guide not written")
        else:
            print("  ERROR — guide not written (check logs)")
        print("-" * 50)
        return

    if args.command == "ingest-serienbriefe":
        from src.pipeline.ingest import ingest_serienbriefe

        result = ingest_serienbriefe(dry_run=args.dry_run)
        print("\nSerienbriefe ingest complete")
        print("-" * 50)
        print(f"  Total rows in sheet:  {result['total']}")
        print(f"  Inserted (new):       {result['inserted_new']}")
        print(f"  Updated (existing):   {result['updated_existing']}")
        print(f"  Skipped (no domain):  {result['skipped_no_domain']}")
        print(f"  Skipped (no date):    {result['skipped_no_date']}")
        print(f"  Skipped (unknown BA): {result['skipped_unknown_ba']}")
        print("-" * 50)
        return

    if args.command == "ingest-manual":
        from src.pipeline.ingest import ingest_manual

        result = ingest_manual(
            excel_path=args.file,
            sheet_name=args.sheet,
            dry_run=args.dry_run,
            col_domain=args.col_domain,
            col_name=args.col_name,
            col_klass=args.col_klass,
            col_source=args.col_source,
        )
        dry = "(DRY RUN) " if args.dry_run else ""
        print(f"\nManual ingest {dry}complete")
        print("-" * 50)
        print(f"  Total rows in sheet:  {result['total_rows']}")
        print(f"  Accepted:             {result['accepted']}")
        print(f"  Inserted (new):       {result['inserted']}")
        print(f"  Updated (existing):   {result['updated']}")
        print(f"  Skipped (no domain):  {result['skipped_no_domain']}")
        print("-" * 50)
        return

    if args.command == "enrich-regions":
        from src.pipeline.ingest import enrich_regions

        result = enrich_regions(dry_run=args.dry_run)
        dry = "(DRY RUN) " if args.dry_run else ""
        print(f"\nRegion enrichment {dry}complete")
        print(f"  Checked (missing region): {result['total_checked']}")
        print(f"  Matched in mapping:       {result['matched']}")
        if not args.dry_run:
            print(f"  Updated in DB:            {result['updated']}")
        return

    if args.command == "normalize":
        from src.pipeline.normalize import normalize_cmd

        normalize_cmd(args)
        return

    if args.command == "backfill-from-excel":
        from src.pipeline.backfill import backfill_from_excel_cmd

        backfill_from_excel_cmd(args)
        return

    if args.command == "backfill-leistung":
        from src.pipeline.backfill import backfill_leistung_cmd

        backfill_leistung_cmd(args)
        return

    if args.command == "backfill-compliments":
        from src.pipeline.backfill import backfill_compliments_cmd

        backfill_compliments_cmd(args)
        return

    if args.command == "prepare-manual":
        from src.pipeline.qa import prepare_manual_names

        result = prepare_manual_names(dry_run=args.dry_run)
        dry = "(DRY RUN) " if args.dry_run else ""
        print(f"\nPrepare-manual {dry}complete")
        print("-" * 50)
        print(f"  MANUAL records scanned:  {result['total']}")
        print(f"  Names fixed:             {result['name_fixed']}")
        print(f"  Streets fixed:           {result['street_fixed']}")
        print(f"  PLZ fixed:               {result['plz_fixed']}")
        print(f"  Already OK:              {result['skipped_ok']}")
        print(f"  Still need manual fix:   {len(result['still_bad'])}")
        if result["still_bad"]:
            print("\n  Records needing manual name correction:")
            for r in result["still_bad"]:
                print(f"    {r['domain']} (current: {r['full_name']})")
        print("-" * 50)
        return

    if args.command == "backfill-impressum":
        from src.pipeline.backfill import backfill_impressum_cmd

        backfill_impressum_cmd(args)
        return

    if args.command == "enrich-gf":
        from src.pipeline.enrich import enrich_gf_cmd

        enrich_gf_cmd(dry_run=args.dry_run, limit=args.limit)
        return

    if args.command == "check-letter":
        from src.pipeline.check_letter import check_letter_cmd

        check_letter_cmd(args)
        return

    if args.command == "audit-dedup":
        from src.pipeline.audit import audit_dedup

        result = audit_dedup(
            dry_run=args.dry_run,
            fix=getattr(args, "fix", False),
            output_path=getattr(args, "output", None),
        )
        print("\nDedup audit — pipeline.db vs Serienbriefe")
        print("-" * 50)
        print(
            f"  Serienbriefe reference: {result.serienbriefe_domains} domains, "
            f"{result.serienbriefe_names} name-index entries"
        )
        print(
            f"  Checked against: {result.records_checked} records (already_approached=0)"
        )
        print(f"  Unflagged matches found: {len(result.matched)}")
        if result.matched:
            print()
            for m in result.matched:
                klass = f"[{m['klass']}] " if m["klass"] else ""
                print(f"    {klass}{m['domain']} — {m['match_reason']}")
        if result.fixed:
            print(
                f"\n  Fixed: {result.fixed} records marked already_approached=1, outreach_status='sent'"
            )
        elif getattr(args, "fix", False) and result.matched and not args.dry_run:
            print("\n  (No new fixes — records may already be flagged)")
        elif result.matched and not getattr(args, "fix", False):
            print("\n  Run with --fix to apply corrections.")
        print("-" * 50)
        return

    # All other commands require a valid profile
    profile = load_profile(args.profile)
    log.info("Loaded profile: %s (%s)", profile.name, profile.id)
    log.info("Search terms: %s", profile.discovery.wlw_search_terms)

    if args.dry_run:
        log.info("DRY RUN — no API calls or file writes")

    dispatch = {
        "scrape-wlw": lambda: _run_scrape_wlw(profile, args),
        "ingest": lambda: __import__("src.pipeline.ingest", fromlist=["ingest"]).ingest(
            profile, dry_run=args.dry_run, verbose=args.verbose
        ),
        "filter": lambda: __import__(
            "src.pipeline.filter", fromlist=["apply_hard_filters"]
        ).apply_hard_filters(profile=profile, dry_run=args.dry_run),
        "scrape": lambda: __import__(
            "src.pipeline.scrape", fromlist=["scrape_batch_cmd"]
        ).scrape_batch_cmd(
            profile,
            dry_run=args.dry_run,
            limit=args.limit,
            source=getattr(args, "source", None),
        ),
        "classify": lambda: __import__(
            "src.pipeline.classify", fromlist=["classify_cmd"]
        ).classify_cmd(
            profile,
            dry_run=args.dry_run,
            limit=args.limit,
        ),
        "enrich": lambda: __import__(
            "src.pipeline.enrich", fromlist=["enrich_cmd"]
        ).enrich_cmd(profile, dry_run=args.dry_run),
        "export": lambda: __import__(
            "src.pipeline.export", fromlist=["export_cmd"]
        ).export_cmd(
            profile,
            dry_run=args.dry_run,
            approved_only=getattr(args, "approved_only", False),
        ),
        "export-pdf": lambda: __import__(
            "src.pipeline.export_pdf", fromlist=["export_pdf_cmd"]
        ).export_pdf_cmd(
            dry_run=args.dry_run,
            approved_only=getattr(args, "approved_only", False),
        ),
        "dashboard": lambda: _run_dashboard(profile, args),
        "run-all": lambda: _run_all_stages(profile, args),
    }

    try:
        dispatch[args.command]()
    except NotImplementedError as e:
        log.error("Not yet implemented: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
