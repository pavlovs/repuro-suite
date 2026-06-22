"""Cockpit CLI: serve | token <principal> | init-db | sync | seed | status."""

import argparse
import hashlib
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import db, dealroom_sync  # noqa: E402

PRINCIPALS = {
    "rd": ("Roman", "RD", "human"),
    "ff": ("Florian", "FF", "human"),
    "rc-agent": ("Roman's Claude", "RC", "agent"),
    "fc-agent": ("Florian's Claude", "FC", "agent"),
}


def cmd_token(args):
    if args.principal not in PRINCIPALS:
        sys.exit(
            f"unknown principal {args.principal!r} (M1 allows: {', '.join(PRINCIPALS)})"
        )
    name, initials, role = PRINCIPALS[args.principal]
    token = secrets.token_urlsafe(32)
    conn = db.get_conn()
    with db.WRITE_LOCK:
        conn.execute(
            "INSERT INTO users (id, name, initials, token_hash, role) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash",
            (
                args.principal,
                name,
                initials,
                hashlib.sha256(token.encode()).hexdigest(),
                role,
            ),
        )
        db.audit(conn, "cli", "token_rotate", args.principal)
        conn.commit()
    print(f"{args.principal} token (shown ONCE, store in .env):\n{token}")


def cmd_init_db(_args):
    conn = db.get_conn()  # creates schema if user_version=0
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    print(
        f"db ready at {db.default_db_path()} — schema v"
        f"{conn.execute('PRAGMA user_version').fetchone()[0]}, {n} tables"
    )


def cmd_sync(_args):
    result = dealroom_sync.sync_deal_mirror(db.get_conn())
    if result["ok"]:
        print(
            f"deal_mirror: {result['count']} deals upserted (synced_at {result['synced_at']})"
        )
    else:
        sys.exit(f"sync FAILED: {result['error']}")


def cmd_seed(args):
    from scripts.seed_workplan import seed

    counts = seed(db.get_conn(), args.xlsx)
    print(
        f"seeded (staging): {counts['workstreams']} new workstreams, "
        f"{counts['deliverables']} deliverables, {counts['tasks']} tasks "
        f"({counts['skipped']} empty rows skipped)"
    )


def cmd_status(_args):
    conn = db.get_conn()
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    print(f"db: {db.default_db_path()}")
    print(
        f"deals mirrored: {q('SELECT COUNT(*) FROM deal_mirror')} "
        f"(last sync {dealroom_sync.last_synced_at(conn)})"
    )
    print(f"workstreams:    {q('SELECT COUNT(*) FROM workstreams')}")
    print(f"deliverables:   {q('SELECT COUNT(*) FROM deliverables')}")
    print(
        f"tasks:          {q('SELECT COUNT(*) FROM tasks')} "
        f"({q('SELECT COUNT(*) FROM tasks WHERE staging=1')} staging)"
    )
    print(f"users:          {q('SELECT COUNT(*) FROM users')}")
    print(f"audit entries:  {q('SELECT COUNT(*) FROM audit_log')}")


def cmd_serve(args):
    import uvicorn

    os.environ.setdefault("COCKPIT_SYNC_INTERVAL", "300")
    uvicorn.run("src.api:app", host="127.0.0.1", port=args.port, log_level="info")


def main():
    parser = argparse.ArgumentParser(prog="cockpit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    p_token = sub.add_parser("token")
    p_token.add_argument("principal")
    p_token.set_defaults(fn=cmd_token)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    p_seed = sub.add_parser("seed")
    p_seed.add_argument("xlsx", nargs="?", default=None)
    p_seed.set_defaults(fn=cmd_seed)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument(
        "--port", type=int, default=int(os.environ.get("COCKPIT_PORT", "8099"))
    )
    p_serve.set_defaults(fn=cmd_serve)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
