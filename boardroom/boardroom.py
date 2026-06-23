"""Boardroom CLI: serve | init-db | token <user> | seed | status."""

import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import db  # noqa: E402

PRINCIPALS = {
    "rd": ("Roman", "RD", "admin"),
    "ff": ("Florian", "FF", "admin"),
    "strada": ("Strada", "ST", "investor"),
}


def cmd_init_db(_args):
    conn = db.get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    print(
        f"db ready at {db.default_db_path()} — schema v"
        f"{conn.execute('PRAGMA user_version').fetchone()[0]}, {n} tables"
    )


def cmd_token(args):
    if args.user not in PRINCIPALS:
        sys.exit(f"unknown user {args.user!r} (allowed: {', '.join(PRINCIPALS)})")
    name, initials, role = PRINCIPALS[args.user]
    token = secrets.token_urlsafe(32)
    conn = db.get_conn()
    with db.WRITE_LOCK:
        conn.execute(
            "INSERT INTO users (id, name, initials, token_hash, role) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash",
            (
                args.user,
                name,
                initials,
                hashlib.sha256(token.encode()).hexdigest(),
                role,
            ),
        )
        conn.execute(
            "INSERT INTO audit_log (at, actor, action, entity) VALUES (?,?,?,?)",
            (db.now_iso(), "cli", "token_rotate", args.user),
        )
        conn.commit()
    print(f"{args.user} token (shown ONCE, store in .env):\n{token}")


SEED_WEEKLY = {
    "pipeline": {
        "funnel": {
            "items": [
                {
                    "codename": "EAGLE",
                    "stage": "valuation_rfi",
                    "sector": "Radiology",
                    "region": "Baden-Württemberg",
                    "size_band": "€1–3M",
                    "strategic_fit": "high",
                },
                {
                    "codename": "OWL",
                    "stage": "nda",
                    "sector": "Lab / Diagnostics",
                    "region": "Bavaria",
                    "size_band": "<€1M",
                    "strategic_fit": "medium",
                },
                {
                    "codename": "PANDA",
                    "stage": "screening",
                    "sector": "Medical Supplies",
                    "region": "NRW",
                    "size_band": "€3–5M",
                    "strategic_fit": "medium",
                },
            ]
        },
        "batches": {
            "rows": [
                {
                    "batch": "BA1",
                    "sent": 240,
                    "replies": 18,
                    "meetings": 6,
                    "conv_pct": 2.5,
                },
                {
                    "batch": "BA2",
                    "sent": 185,
                    "replies": 14,
                    "meetings": 4,
                    "conv_pct": 2.2,
                },
                {
                    "batch": "BA3 (partial)",
                    "sent": 90,
                    "replies": 5,
                    "meetings": 1,
                    "conv_pct": 1.1,
                },
            ]
        },
    },
    "live_deals": [
        {
            "name": "Meditec GmbH",
            "codename": "EAGLE",
            "stage": "due_diligence",
            "rev_m": 8.4,
            "ebitda_m": 1.6,
            "ev_m": 9.6,
            "multiple": 6.0,
            "earnout": "€0.5M over 2 years on EBITDA target",
            "dd_status": "FDD week 3/6, LDD initiated",
            "close_target": "2026-09-30",
            "commentary": "FDD progressing on schedule. Seller aligned on earn-out structure.",
        },
        {
            "name": "RS Radiology Services GmbH",
            "codename": "OWL",
            "stage": "loi_signed",
            "rev_m": 5.1,
            "ebitda_m": 0.9,
            "ev_m": 5.4,
            "multiple": 6.0,
            "earnout": None,
            "dd_status": "DD kick-off scheduled 2026-07-07",
            "close_target": "2026-10-31",
            "commentary": "LOI signed 2026-06-12. Clean books, single owner.",
        },
    ],
    "project_update": {
        "milestones_done": [
            {
                "name": "Lead pipeline M1–M23 complete",
                "date": "2026-05-30",
                "comment": "2,483 records; dashboard v2 live",
            },
            {
                "name": "Cockpit M1 live on :8099",
                "date": "2026-06-10",
                "comment": "Full task/deliverable tracking operational",
            },
        ],
        "milestones_next": [
            {"name": "Investor Room M1 (this build)", "target_date": "2026-06-27"},
            {"name": "Eagle FDD completion", "target_date": "2026-07-15"},
            {"name": "Eagle SPA first draft", "target_date": "2026-08-01"},
        ],
        "narrative": (
            "Build velocity is on track. Two deals in active DD simultaneously "
            "is manageable given current team capacity. Fundraising process "
            "advancing in parallel — no bottleneck identified."
        ),
        "fundraising": {
            "tax_structure": (
                "GmbH & Co. KG holding structure confirmed. Tax opinion from "
                "Ebner Stolz received; no material issues flagged."
            ),
            "sources_uses": [
                {
                    "item": "Equity (Strada + Kamu)",
                    "amount_m": 4.0,
                    "note": "50/50 split per SHA",
                },
                {
                    "item": "Senior debt (local Sparkasse)",
                    "amount_m": 3.5,
                    "note": "indicative term sheet",
                },
                {
                    "item": "Seller loan (Meditec)",
                    "amount_m": 2.1,
                    "note": "5yr, 4% p.a.",
                },
                {
                    "item": "Total EV (Meditec + OWL combined)",
                    "amount_m": 15.0,
                    "note": "",
                },
            ],
            "capital_plan": (
                "First close targeting Q3-2026 simultaneous with Meditec signing. "
                "OWL funded from same vehicle Q4-2026. Reserve facility of €1M "
                "agreed in principle with lender for add-on bolt-ons in 2027."
            ),
        },
    },
    "stamps": {
        "pipeline.funnel": {"source": "authored", "as_of": "2026-06-20"},
        "pipeline.batches": {"source": "pipeline.db", "as_of": "2026-06-19"},
        "live_deals": {"source": "dealroom.db", "as_of": "2026-06-20"},
        "project_update.milestones_done": {
            "source": "cockpit.db",
            "as_of": "2026-06-20",
        },
        "project_update.fundraising": {"source": "authored", "as_of": "2026-06-20"},
    },
}

SEED_BOARD = {
    "meeting": {
        "date": "2026-06-30",
        "location": "Berlin / Video call",
        "attendees": [
            "Roman Dobriakov (MD)",
            "Florian (Co-Founder)",
            "Strada Representative",
        ],
    },
    "agenda": [
        {
            "item": "1. Deal pipeline update — Eagle & OWL status",
            "owner": "Roman",
            "minutes": "",
        },
        {
            "item": "2. Fundraising & cap table — sources/uses approval",
            "owner": "Roman / Florian",
            "minutes": "",
        },
        {
            "item": "3. Q3 milestones & resolutions",
            "owner": "All",
            "minutes": "",
        },
    ],
    "kpis": [
        {
            "metric": "Pipeline (active leads)",
            "value": "3",
            "prior": "2",
            "as_of": "2026-06-20",
        },
        {
            "metric": "Live deals (post-LOI)",
            "value": "2",
            "prior": "1",
            "as_of": "2026-06-20",
        },
        {
            "metric": "Combined EV in DD (€M)",
            "value": "15.0",
            "prior": "9.6",
            "as_of": "2026-06-20",
        },
        {
            "metric": "Batch outreach (total sent)",
            "value": "515",
            "prior": "425",
            "as_of": "2026-06-19",
        },
    ],
    "decisions": [
        {
            "topic": "Eagle acquisition — EV and earn-out",
            "proposal": "Approve EV of €9.6M with €0.5M earn-out over 2 years",
            "resolution": "APPROVED",
            "vote": "Unanimous",
        },
        {
            "topic": "OWL acquisition — LOI ratification",
            "proposal": "Ratify LOI signed 2026-06-12 at EV €5.4M",
            "resolution": "APPROVED",
            "vote": "Unanimous",
        },
    ],
    "pre_read": [
        {
            "title": "Eagle FDD interim report (week 3)",
            "note": "Shared via secure data room",
        },
        {"title": "OWL LOI + NDA", "note": "Executed copies in data room"},
        {"title": "Capital structure memo v2", "note": "Ebner Stolz, dated 2026-06-15"},
    ],
    "minutes": "",
    "stamps": {
        "kpis": {"source": "authored", "as_of": "2026-06-20"},
        "decisions": {"source": "authored", "as_of": "2026-06-20"},
    },
}

SEED_DRAFT_WEEKLY = {
    "pipeline": {
        "funnel": {"items": []},
        "batches": {"rows": []},
    },
    "live_deals": [],
    "project_update": {
        "milestones_done": [],
        "milestones_next": [],
        "narrative": "DRAFT — not yet authored.",
        "fundraising": {"tax_structure": "", "sources_uses": [], "capital_plan": ""},
    },
    "stamps": {},
}


def cmd_seed(_args):
    conn = db.get_conn()
    now = db.now_iso()
    with db.WRITE_LOCK:
        # Idempotent: seed is demo data, so reset publications before re-inserting.
        conn.execute("DELETE FROM publications")
        # Ensure principal users exist (needed for token command but seed should work standalone)
        for uid, (name, initials, role) in PRINCIPALS.items():
            conn.execute(
                "INSERT OR IGNORE INTO users (id, name, initials, role) VALUES (?,?,?,?)",
                (uid, name, initials, role),
            )

        conn.execute(
            "INSERT INTO publications (kind, ref, title, status, body, created_at, approved_at, "
            "approved_by, published_at, version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "weekly_update",
                "2026-06-16",
                "Weekly Update — w/c 16 Jun 2026",
                "published",
                json.dumps(SEED_WEEKLY),
                now,
                now,
                "rd",
                now,
                1,
            ),
        )
        conn.execute(
            "INSERT INTO publications (kind, ref, title, status, body, created_at, approved_at, "
            "approved_by, published_at, version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "board_pack",
                "2026-06-30",
                "Board Meeting — 30 Jun 2026",
                "published",
                json.dumps(SEED_BOARD),
                now,
                now,
                "rd",
                now,
                1,
            ),
        )
        conn.execute(
            "INSERT INTO publications (kind, ref, title, status, body, created_at, version) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                "weekly_update",
                "2026-06-23",
                "Weekly Update — w/c 23 Jun 2026 [DRAFT]",
                "draft",
                json.dumps(SEED_DRAFT_WEEKLY),
                now,
                1,
            ),
        )
        conn.commit()
    print(
        "seeded: 1 published weekly_update, 1 published board_pack, 1 draft weekly_update"
    )


def cmd_status(_args):
    conn = db.get_conn()
    q = lambda sql, *p: conn.execute(sql, p).fetchone()[0]  # noqa: E731
    print(f"db: {db.default_db_path()}")
    print(f"users:        {q('SELECT COUNT(*) FROM users')}")
    print(f"publications: {q('SELECT COUNT(*) FROM publications')}")
    for status in ("draft", "approved", "published", "archived"):
        n = q("SELECT COUNT(*) FROM publications WHERE status=?", status)
        print(f"  {status}: {n}")
    print(f"audit log:    {q('SELECT COUNT(*) FROM audit_log')}")


def cmd_serve(args):
    import uvicorn

    if getattr(args, "dev", False):
        # Local review only: enables the browser role switcher (no Caddy locally).
        # Bind stays loopback; production is unaffected (Caddy overwrites X-Remote-User).
        os.environ["INVESTOR_DEV_MODE"] = "1"
        print("DEV MODE — role switcher enabled (Strada / Admin). Loopback only.")
    uvicorn.run("src.api:app", host="127.0.0.1", port=args.port, log_level="info")


def main():
    parser = argparse.ArgumentParser(prog="boardroom")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)

    p_token = sub.add_parser("token")
    p_token.add_argument("user", choices=list(PRINCIPALS))
    p_token.set_defaults(fn=cmd_token)

    sub.add_parser("seed").set_defaults(fn=cmd_seed)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    p_serve = sub.add_parser("serve")
    p_serve.add_argument(
        "--port", type=int, default=int(os.environ.get("INVESTOR_PORT", "8084"))
    )
    p_serve.add_argument(
        "--dev", action="store_true", help="local review: enable browser role switcher"
    )
    p_serve.set_defaults(fn=cmd_serve)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
