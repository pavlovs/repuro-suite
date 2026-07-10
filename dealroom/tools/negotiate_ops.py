# -*- coding: utf-8 -*-
"""Operational layer for /repuro:negotiate — SPEC §12 (v4 hardening, 2026-07-10).

Subcommands (all local, stdlib-only, additive writes only):
    migrate                       create §12 tables + columns (WAL-safe backup first)
    watch [--brief] [--days N]    deal-health monitor: milestones, open items,
                                  unlogged interactions, relationship-cold,
                                  stale mirror, missing next steps
    triage <stakeholder> [--mark-read ids --note "..."]   trail skim->read workflow
    trail-add <stakeholder> --source S --date D --subject S [...]
    milestone add|list|set-status
    open-item add|list|resolve
    position add|list|confirm     three-tier terms (preferred/fallback/walk-away)
    round add|review              quick round capture + self-rating review

Morning-brief integration: `watch --brief` prints nothing when all quiet,
pre-formatted alert lines otherwise (same contract as Steuer deadlines.py).
Design rule (codex 2026-07-10): silence must mean VERIFIED-quiet — malformed
dates, unparseable signals, and degraded data sources are ALERTS, not skips.
Companion gate: validate_negotiation.py (per-strategy, blocks delivery).
Regression tests: test_negotiate_ops.py.
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "dealroom.db"
DEFAULT_HUBSPOT = Path(r"C:\Users\X1\Documents\CLAUDE_COWORK\repuro-data\hubspot.db")

MIGRATE_DDL = """
CREATE TABLE IF NOT EXISTS negotiation_milestones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  label TEXT NOT NULL,
  side TEXT DEFAULT 'both' CHECK (side IN ('ours','theirs','both')),
  consequence TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending','met','missed','moved')),
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS negotiation_open_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id INTEGER NOT NULL,
  item TEXT NOT NULL,
  owner TEXT NOT NULL CHECK (owner IN ('us','them')),
  due TEXT,
  status TEXT DEFAULT 'open' CHECK (status IN ('open','resolved')),
  resolution TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS strategy_parties (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id INTEGER NOT NULL,
  stakeholder_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('primary','co_seller','advisor','influencer')),
  notes TEXT,
  UNIQUE (strategy_id, stakeholder_id)
);
CREATE TABLE IF NOT EXISTS negotiation_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy_id INTEGER NOT NULL,
  term TEXT NOT NULL,
  preferred TEXT NOT NULL,
  fallback TEXT,
  walk_away TEXT,
  escalation_required INTEGER DEFAULT 0,
  roman_confirmed INTEGER DEFAULT 0,
  status TEXT DEFAULT 'open' CHECK (status IN ('open','agreed','conceded','escalated')),
  created_at TEXT DEFAULT (datetime('now'))
);
"""
# additive column adds; each guarded because ALTER has no IF NOT EXISTS
MIGRATE_COLUMNS = [
    ("negotiation_rounds", "counterparty_id", "INTEGER"),
    ("negotiation_rounds", "signals", "TEXT"),
    ("negotiation_strategies", "closed_reason", "TEXT"),
    ("communication_trail", "triage_note", "TEXT"),
]
# table -> columns that must exist for the module to work; a PRE-EXISTING
# table with the right name but wrong shape must fail the migration report
# (codex loop-2 #4)
MIGRATE_TABLE_COLUMNS = {
    "negotiation_milestones": {
        "id",
        "strategy_id",
        "date",
        "label",
        "side",
        "consequence",
        "status",
    },
    "negotiation_open_items": {
        "id",
        "strategy_id",
        "item",
        "owner",
        "due",
        "status",
        "resolution",
    },
    "strategy_parties": {"id", "strategy_id", "stakeholder_id", "role"},
    "negotiation_positions": {
        "id",
        "strategy_id",
        "term",
        "preferred",
        "fallback",
        "walk_away",
        "roman_confirmed",
        "status",
    },
}
MIGRATE_TABLES = tuple(MIGRATE_TABLE_COLUMNS)


DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso(d):
    """ISO read of stored TEXT dates: date or None (caller must treat None on a
    REQUIRED date as an alert, never as a silent skip). Accepts YYYY-MM-DD with
    an optional timestamp tail; '2026-07-10garbage' is None (codex loop-2 #5)."""
    if not d:
        return None
    s = str(d)
    if not re.match(r"^\d{4}-\d{2}-\d{2}($|[T ])", s):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _valid_date(s, flag):
    """Strict write-path gate: exactly YYYY-MM-DD or exit — fromisoformat alone
    also accepts '20260710' and ISO week dates (codex loop-2 #7)."""
    if not s or not DATE_RX.match(s):
        sys.exit(f"{flag} must be an ISO date (YYYY-MM-DD), got: {s!r}")
    try:
        date.fromisoformat(s)
    except ValueError:
        sys.exit(f"{flag} is not a real calendar date: {s!r}")
    return s


def _connect(db, readonly=False):
    if readonly:
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    return con


def resolve_stakeholder(con, ident):
    """int id or unique name substring -> (id, name). Ambiguity/miss exits."""
    if str(ident).isdigit():
        row = con.execute(
            "SELECT id, name FROM stakeholders WHERE id=?", (int(ident),)
        ).fetchone()
        if not row:
            sys.exit(f"no stakeholder with id {ident}")
        return row["id"], row["name"]
    hits = con.execute(
        "SELECT id, name FROM stakeholders WHERE name LIKE ?", (f"%{ident}%",)
    ).fetchall()
    if len(hits) == 1:
        return hits[0]["id"], hits[0]["name"]
    if not hits:
        sys.exit(f"no stakeholder matching '{ident}'")
    sys.exit("ambiguous: " + ", ".join(f"{h['id']}={h['name']}" for h in hits))


# --------------------------------------------------------------------------
def _backup_db(db):
    """WAL-safe snapshot via SQLite's backup API into a UNIQUE file (codex
    finding 3: shutil.copy2 can miss WAL pages; same-second reruns must not
    overwrite an earlier backup)."""
    backup_dir = db.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    n, target = 0, backup_dir / f"dealroom_pre_migrate_{stamp}.db"
    while target.exists():
        n += 1
        target = backup_dir / f"dealroom_pre_migrate_{stamp}_{n}.db"
    src = sqlite3.connect(db)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    return target


def _widen_status_check(con):
    """The pre-§12 strategies table CHECKs status IN (active|superseded|closed);
    the phase model adds 'executing'. SQLite cannot ALTER a CHECK — rebuild the
    table (create patched copy, move rows, swap) inside one transaction.
    Found live 2026-07-10: additive column migration alone left the CHECK behind."""
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='negotiation_strategies'"
    ).fetchone()
    if not row or "'executing'" in row[0] or "CHECK" not in row[0].upper():
        return False
    patched = re.sub(
        r"CHECK\s*\(\s*status\s+IN\s*\([^)]*\)\s*\)",
        "CHECK(status IN ('active','executing','superseded','closed'))",
        row[0],
        flags=re.IGNORECASE,
    )
    if patched == row[0]:
        sys.exit(
            "cannot widen status CHECK automatically — negotiation_strategies DDL "
            "has an unexpected shape; widen it manually"
        )
    patched = patched.replace(
        "CREATE TABLE negotiation_strategies",
        "CREATE TABLE negotiation_strategies_new",
        1,
    )
    cols = [r[1] for r in con.execute("PRAGMA table_info(negotiation_strategies)")]
    collist = ", ".join(cols)
    con.execute("BEGIN")
    con.execute(patched)
    con.execute(
        f"INSERT INTO negotiation_strategies_new ({collist}) "
        f"SELECT {collist} FROM negotiation_strategies"
    )
    con.execute("DROP TABLE negotiation_strategies")
    con.execute(
        "ALTER TABLE negotiation_strategies_new RENAME TO negotiation_strategies"
    )
    con.execute("COMMIT")
    return True


def cmd_migrate(args):
    db = Path(args.db)
    if not db.exists():
        sys.exit(f"DB not found: {db}")
    backup = _backup_db(db)
    con = _connect(db)
    widened = _widen_status_check(con)
    con.executescript(MIGRATE_DDL)
    added_cols = []
    for table, col, typ in MIGRATE_COLUMNS:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            added_cols.append(f"{table}.{col}")
    con.commit()
    # post-verify: report success ONLY on a complete schema (codex finding 4 —
    # the migration is idempotent, so a partial failure is fixed by re-running,
    # but it must never be REPORTED as ok)
    have = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = [t for t in MIGRATE_TABLES if t not in have]
    for table, need_cols in MIGRATE_TABLE_COLUMNS.items():
        if table not in have:
            continue
        got = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        missing += [f"{table}.{c}" for c in sorted(need_cols - got)]
    for table, col, _ in MIGRATE_COLUMNS:
        if col not in {r[1] for r in con.execute(f"PRAGMA table_info({table})")}:
            missing.append(f"{table}.{col}")
    con.close()
    if missing:
        sys.exit(f"migration INCOMPLETE, re-run: missing {missing} (backup: {backup})")
    print(
        json.dumps(
            {
                "ok": True,
                "backup": str(backup),
                "columns_added": added_cols,
                "status_check_widened": widened,
            },
            ensure_ascii=False,
        )
    )


# --------------------------------------------------------------------------
def collect_watch(db, hubspot, days=7, today=None):
    """Pure collection pass -> (alerts, notes). Printing lives in cmd_watch.
    ALERT = needs action / broken data; note = context. Anything malformed on a
    live strategy is an ALERT — a skipped check must never read as quiet."""
    today = today or date.today()
    horizon = today + timedelta(days=days)
    con = _connect(db, readonly=True)
    have = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    alerts, notes = [], []

    strategies = con.execute(
        "SELECT s.id, s.stakeholder_id, s.context_ref, s.status, "
        "st.name AS who FROM negotiation_strategies s "
        "JOIN stakeholders st ON st.id = s.stakeholder_id "
        "WHERE s.status IN ('active','executing')"
    ).fetchall()

    for s in strategies:
        tag = f"{s['context_ref']}/{s['who'].split()[-1]} (S{s['id']}, {s['status']})"

        # milestones — malformed dates are alerts, not skips
        future_pending = 0
        if "negotiation_milestones" in have:
            for m in con.execute(
                "SELECT id, date, label, side, consequence, status "
                "FROM negotiation_milestones WHERE strategy_id=? AND status='pending'",
                (s["id"],),
            ):
                d = _iso(m["date"])
                if d is None:
                    alerts.append(
                        f"{tag}: milestone {m['id']} has unparseable date "
                        f"{m['date']!r} — fix it (watch is blind to it)"
                    )
                    continue
                if d < today:
                    alerts.append(
                        f"{tag}: milestone OVERDUE {m['date']} — {m['label']}"
                        + (
                            f" | consequence: {m['consequence']}"
                            if m["consequence"]
                            else ""
                        )
                    )
                elif d <= horizon:
                    alerts.append(
                        f"{tag}: milestone in {(d - today).days}d ({m['date']}) — {m['label']}"
                    )
                    future_pending += 1
                else:
                    future_pending += 1
        if s["status"] == "executing" and future_pending == 0:
            alerts.append(
                f"{tag}: EXECUTING with no future milestone — deal is in its riskiest "
                f"phase with no deadline map (run milestone add)"
            )

        # open items
        if "negotiation_open_items" in have:
            for o in con.execute(
                "SELECT id, item, owner, due FROM negotiation_open_items "
                "WHERE strategy_id=? AND status='open'",
                (s["id"],),
            ):
                side = "WE owe" if o["owner"] == "us" else "THEY owe"
                if o["due"]:
                    d = _iso(o["due"])
                    if d is None:
                        alerts.append(
                            f"{tag}: open item {o['id']} has unparseable due date "
                            f"{o['due']!r} — fix it"
                        )
                    elif d < today:
                        alerts.append(
                            f"{tag}: open item PAST DUE ({side}): {o['item']}"
                        )
                    elif d <= horizon:
                        notes.append(
                            f"{tag}: open item due {o['due']} ({side}): {o['item']}"
                        )
                else:
                    notes.append(
                        f"{tag}: open item without due date ({side}): {o['item']}"
                    )

        # rounds vs trail: unlogged interactions + cold seller + stuck strategy
        last_round = con.execute(
            "SELECT MAX(date) FROM negotiation_rounds WHERE strategy_id=? OR stakeholder_id=?",
            (s["id"], s["stakeholder_id"]),
        ).fetchone()[0]
        last_trail = con.execute(
            "SELECT MAX(date) FROM communication_trail WHERE stakeholder_id=?",
            (s["stakeholder_id"],),
        ).fetchone()[0]
        lr, lt = _iso(last_round), _iso(last_trail)
        if lr and lt and lt > lr:
            alerts.append(
                f"{tag}: interaction on {last_trail} newer than last logged round "
                f"({last_round}) — ledger stale, run: /repuro:negotiate {s['context_ref']} round"
            )
        if s["status"] == "executing":
            if lt is None:
                alerts.append(
                    f"{tag}: EXECUTING with no dated contact in the trail at all — "
                    f"trail empty or dates unparseable"
                )
            elif (today - lt).days > 7:
                alerts.append(
                    f"{tag}: no contact for {(today - lt).days}d during EXECUTING — "
                    f"relationship-cold risk (seller withdrawal precedes the formal no)"
                )
        if lr and (today - lr).days > 21:
            notes.append(f"{tag}: no round logged in {(today - lr).days}d")

        # signals of the TRUE latest rounds (codex finding 5: stale signals on an
        # older round must not stand in for the latest interaction)
        rows = con.execute(
            "SELECT date, signals FROM negotiation_rounds "
            "WHERE (strategy_id=? OR stakeholder_id=?) AND date IS NOT NULL "
            "ORDER BY date DESC LIMIT 2",
            (s["id"], s["stakeholder_id"]),
        ).fetchall()
        parsed = []
        for r in rows:
            if r["signals"] is None:
                parsed.append(None)  # pre-signals round — legitimate
                continue
            try:
                sig = json.loads(r["signals"])
                if not isinstance(sig, dict):
                    raise ValueError
                parsed.append(sig)
            except (ValueError, TypeError):
                alerts.append(
                    f"{tag}: unparseable signals JSON on round dated {r['date']} — fix it"
                )
                parsed.append(None)
        if parsed and parsed[0] is not None:
            if parsed[0].get("next_step_committed") is not True:
                alerts.append(
                    f"{tag}: last interaction closed WITHOUT a committed next step"
                )
            if (
                len(parsed) == 2
                and parsed[1] is not None
                and parsed[0].get("pricing_deferred")
                and parsed[1].get("pricing_deferred")
            ):
                alerts.append(
                    f"{tag}: pricing deferred 2 rounds in a row — stall pattern"
                )

    # global: hubspot mirror health — degraded source = ALERT while anything is live
    hs = Path(hubspot)
    if strategies:
        if not hs.exists():
            alerts.append(
                f"hubspot mirror MISSING at {hs} — trail/first-contact guarantees "
                f"are degraded for every live strategy"
            )
        else:
            age = (datetime.now() - datetime.fromtimestamp(hs.stat().st_mtime)).days
            if age > 30:
                alerts.append(
                    f"hubspot mirror is {age}d old — refresh it (first-contact and "
                    f"trail-coverage checks degrade silently)"
                )
    con.close()
    return alerts, notes


def cmd_watch(args):
    alerts, notes = collect_watch(args.db, args.hubspot, args.days)
    if args.brief:
        for a in alerts:
            print(f"- {a}")
        return  # quiet when nothing burns (brief contract)
    n_live = len(
        _connect(args.db, readonly=True)
        .execute(
            "SELECT id FROM negotiation_strategies WHERE status IN ('active','executing')"
        )
        .fetchall()
    )
    print(f"NEGOTIATION WATCH — {date.today().isoformat()} ({n_live} live strategies)")
    if not n_live:
        print("no active/executing strategies")
    for a in alerts:
        print(f"ALERT  {a}")
    for i in notes:
        print(f"note   {i}")
    if n_live and not alerts and not notes:
        print("all quiet")


# --------------------------------------------------------------------------
def cmd_triage(args):
    con = _connect(args.db)
    sid, name = resolve_stakeholder(con, args.stakeholder)
    if args.mark_read:
        if not args.note:
            sys.exit(
                "--note is mandatory with --mark-read (one line: what the batch was)"
            )
        ids = [int(x) for x in re.split(r"[,\s]+", args.mark_read) if x.strip()]
        q = ",".join("?" * len(ids))
        cur = con.execute(
            f"UPDATE communication_trail SET read_status='read', triage_note=? "
            f"WHERE stakeholder_id=? AND id IN ({q}) AND read_status != 'read'",
            [args.note, sid] + ids,
        )
        con.commit()
        print(f"marked {cur.rowcount} item(s) read for {name} — note: {args.note}")
        remaining = con.execute(
            "SELECT COUNT(*) FROM communication_trail "
            "WHERE stakeholder_id=? AND read_status != 'read'",
            (sid,),
        ).fetchone()[0]
        print(f"remaining non-read: {remaining}")
        con.close()
        return
    rows = con.execute(
        "SELECT id, source, date, direction, subject, read_status "
        "FROM communication_trail WHERE stakeholder_id=? AND read_status != 'read' "
        "ORDER BY source, date",
        (sid,),
    ).fetchall()
    con.close()
    if not rows:
        print(f"trail for {name}: nothing to triage (all read)")
        return
    print(f"TRIAGE {name} — {len(rows)} non-read item(s). Read/skim each, then:")
    print(f'  negotiate_ops.py triage {sid} --mark-read <ids> --note "<what it was>"')
    cur_src = None
    for r in rows:
        if r["source"] != cur_src:
            cur_src = r["source"]
            print(f"[{cur_src}]")
        print(
            f"  {r['id']:>4}  {r['date'] or '?':<12} {r['direction'] or '?':<4} "
            f"{(r['subject'] or '')[:70]}"
        )


def cmd_trail_add(args):
    con = _connect(args.db)
    sid, name = resolve_stakeholder(con, args.stakeholder)
    con.execute(
        "INSERT INTO communication_trail "
        "(stakeholder_id, source, ref, date, direction, subject, read_status) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            sid,
            args.source,
            args.ref or "",
            args.date,
            args.direction,
            args.subject,
            "unread" if args.unread else "read",
        ),
    )
    con.commit()
    con.close()
    print(f"trail item added for {name}: {args.source} {args.date} — {args.subject}")


# --------------------------------------------------------------------------
def cmd_milestone(args):
    con = _connect(args.db)
    if args.action == "add":
        con.execute(
            "INSERT INTO negotiation_milestones (strategy_id, date, label, side, consequence) "
            "VALUES (?,?,?,?,?)",
            (args.strategy, args.date, args.label, args.side, args.consequence),
        )
        con.commit()
        print(f"milestone added: S{args.strategy} {args.date} — {args.label}")
    elif args.action == "set-status":
        # transition guard (codex finding 10): only pending milestones move;
        # correcting a wrong terminal state = insert a new milestone row
        cur = con.execute(
            "UPDATE negotiation_milestones SET status=? WHERE id=? AND status='pending'",
            (args.status, args.id),
        )
        con.commit()
        print(
            f"milestone {args.id} -> {args.status}"
            if cur.rowcount
            else f"no-op: milestone {args.id} not found or not pending (terminal "
            f"states are immutable — add a new row to correct)"
        )
    else:  # list
        q = "SELECT * FROM negotiation_milestones"
        rows = (
            con.execute(q + " WHERE strategy_id=? ORDER BY date", (args.strategy,))
            if args.strategy
            else con.execute(q + " ORDER BY strategy_id, date")
        ).fetchall()
        for r in rows:
            print(
                f"{r['id']:>3} S{r['strategy_id']} {r['date']} [{r['status']:<7}] "
                f"({r['side']}) {r['label']}"
                + (f" | {r['consequence']}" if r["consequence"] else "")
            )
    con.close()


def cmd_open_item(args):
    con = _connect(args.db)
    if args.action == "add":
        con.execute(
            "INSERT INTO negotiation_open_items (strategy_id, item, owner, due) "
            "VALUES (?,?,?,?)",
            (args.strategy, args.item, args.owner, args.due),
        )
        con.commit()
        print(f"open item added: S{args.strategy} [{args.owner}] {args.item}")
    elif args.action == "resolve":
        # only open items resolve; a second resolve is a no-op, never an overwrite
        cur = con.execute(
            "UPDATE negotiation_open_items SET status='resolved', resolution=?, "
            "resolved_at=datetime('now') WHERE id=? AND status='open'",
            (args.resolution or "", args.id),
        )
        con.commit()
        print(
            f"item {args.id} resolved"
            if cur.rowcount
            else f"no-op: item {args.id} not found or already resolved"
        )
    else:  # list
        q = (
            "SELECT * FROM negotiation_open_items WHERE status='open'"
            + (" AND strategy_id=?" if args.strategy else "")
            + " ORDER BY owner, due"
        )
        rows = con.execute(q, (args.strategy,) if args.strategy else ()).fetchall()
        for r in rows:
            print(
                f"{r['id']:>3} S{r['strategy_id']} [{'WE owe' if r['owner'] == 'us' else 'THEY owe'}] "
                f"due {r['due'] or '—'}: {r['item']}"
            )
    con.close()


def cmd_position(args):
    con = _connect(args.db)
    if args.action == "add":
        con.execute(
            "INSERT INTO negotiation_positions "
            "(strategy_id, term, preferred, fallback, walk_away, escalation_required) "
            "VALUES (?,?,?,?,?,?)",
            (
                args.strategy,
                args.term,
                args.preferred,
                args.fallback,
                args.walk_away,
                1 if args.escalation else 0,
            ),
        )
        con.commit()
        print(
            f"position added (UNCONFIRMED — needs Roman): S{args.strategy} {args.term}"
        )
    elif args.action == "confirm":
        # Only on Roman's explicit instruction — the skill enforces this rule.
        cur = con.execute(
            "UPDATE negotiation_positions SET roman_confirmed=1 WHERE id=?", (args.id,)
        )
        con.commit()
        print(f"position {args.id} confirmed" if cur.rowcount else "no such id")
    else:  # list
        q = "SELECT * FROM negotiation_positions" + (
            " WHERE strategy_id=?" if args.strategy else ""
        )
        rows = con.execute(q, (args.strategy,) if args.strategy else ()).fetchall()
        for r in rows:
            conf = "OK Roman" if r["roman_confirmed"] else "UNCONFIRMED"
            print(
                f"{r['id']:>3} S{r['strategy_id']} [{r['status']}, {conf}] {r['term']}"
            )
            print(f"      preferred: {r['preferred']}")
            if r["fallback"]:
                print(f"      fallback:  {r['fallback']}")
            if r["walk_away"]:
                print(f"      walk-away: {r['walk_away']}")
    con.close()


# --------------------------------------------------------------------------
def cmd_round(args):
    con = _connect(args.db)
    if args.action == "add":
        strategy = con.execute(
            "SELECT stakeholder_id FROM negotiation_strategies WHERE id=?",
            (args.strategy,),
        ).fetchone()
        if not strategy:
            sys.exit(f"no strategy {args.strategy}")
        n = con.execute(
            "SELECT COALESCE(MAX(round_no),0)+1 FROM negotiation_rounds WHERE strategy_id=?",
            (args.strategy,),
        ).fetchone()[0]
        signals = None
        if args.signals:
            try:
                parsed = json.loads(args.signals)
                if not isinstance(parsed, dict):
                    raise ValueError
                signals = json.dumps(parsed, ensure_ascii=False)
            except ValueError:
                sys.exit("--signals must be a JSON object")
        cur = con.execute(
            "INSERT INTO negotiation_rounds (strategy_id, stakeholder_id, round_no, date, "
            "channel, we_asked, they_asked, we_gave, they_gave, outcome, next_step, "
            "counterparty_id, signals) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                args.strategy,
                strategy["stakeholder_id"],
                n,
                args.date,
                args.channel,
                args.we_asked or "",
                args.they_asked or "",
                args.we_gave or "",
                args.they_gave or "",
                args.outcome or "",
                args.next_step or "",
                args.counterparty,
                signals,
            ),
        )
        con.commit()
        print(f"round {n} added (id {cur.lastrowid}) for S{args.strategy} {args.date}")
        if args.we_gave and not args.they_gave:
            print(
                "WARNING C1: we gave without logged reciprocity — flag it in the review"
            )
        if not args.next_step:
            print(
                "WARNING: no next step — Gong stall predictor #1; commit one or log why"
            )
    else:  # review
        con.execute(
            "INSERT INTO negotiation_round_reviews (round_id, went_well, went_wrong, "
            "lesson, self_rating) VALUES (?,?,?,?,?)",
            (args.id, args.went_well, args.went_wrong, args.lesson, args.rating),
        )
        con.commit()
        print(f"review saved for round id {args.id} (self-rating {args.rating}/5)")
    con.close()


# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="negotiate_ops")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--hubspot", default=str(DEFAULT_HUBSPOT))
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate")

    pw = sub.add_parser("watch")
    pw.add_argument("--brief", action="store_true")
    pw.add_argument("--days", type=int, default=7)

    pt = sub.add_parser("triage")
    pt.add_argument("stakeholder")
    pt.add_argument("--mark-read")
    pt.add_argument("--note")

    pa = sub.add_parser("trail-add")
    pa.add_argument("stakeholder")
    pa.add_argument(
        "--source", required=True, choices=("email_live", "granola", "hubspot", "other")
    )
    pa.add_argument("--date", required=True)
    pa.add_argument("--subject", required=True)
    pa.add_argument("--direction", default="in", choices=("in", "out"))
    pa.add_argument("--ref")
    pa.add_argument("--unread", action="store_true")

    pm = sub.add_parser("milestone")
    pm.add_argument("action", choices=("add", "list", "set-status"))
    pm.add_argument("--strategy", type=int)
    pm.add_argument("--date")
    pm.add_argument("--label")
    pm.add_argument("--side", default="both", choices=("ours", "theirs", "both"))
    pm.add_argument("--consequence")
    pm.add_argument("--id", type=int)
    pm.add_argument("--status", choices=("pending", "met", "missed", "moved"))

    po = sub.add_parser("open-item")
    po.add_argument("action", choices=("add", "list", "resolve"))
    po.add_argument("--strategy", type=int)
    po.add_argument("--item")
    po.add_argument("--owner", choices=("us", "them"))
    po.add_argument("--due")
    po.add_argument("--id", type=int)
    po.add_argument("--resolution")

    pp = sub.add_parser("position")
    pp.add_argument("action", choices=("add", "list", "confirm"))
    pp.add_argument("--strategy", type=int)
    pp.add_argument("--term")
    pp.add_argument("--preferred")
    pp.add_argument("--fallback")
    pp.add_argument("--walk-away", dest="walk_away")
    pp.add_argument("--escalation", action="store_true")
    pp.add_argument("--id", type=int)

    pr = sub.add_parser("round")
    pr.add_argument("action", choices=("add", "review"))
    pr.add_argument("--strategy", type=int)
    pr.add_argument("--date")
    pr.add_argument("--channel")
    pr.add_argument("--we-asked", dest="we_asked")
    pr.add_argument("--they-asked", dest="they_asked")
    pr.add_argument("--we-gave", dest="we_gave")
    pr.add_argument("--they-gave", dest="they_gave")
    pr.add_argument("--outcome")
    pr.add_argument("--next-step", dest="next_step")
    pr.add_argument("--counterparty", type=int)
    pr.add_argument("--signals")
    pr.add_argument("--id", type=int)
    pr.add_argument("--went-well", dest="went_well")
    pr.add_argument("--went-wrong", dest="went_wrong")
    pr.add_argument("--lesson")
    pr.add_argument("--rating", type=int, choices=range(1, 6))

    args = p.parse_args(argv)
    # minimal required-arg checks per action (argparse subcommand limitation)
    reqs = {
        ("milestone", "add"): ("strategy", "date", "label"),
        ("milestone", "set-status"): ("id", "status"),
        ("open-item", "add"): ("strategy", "item", "owner"),
        ("open-item", "resolve"): ("id",),
        ("position", "add"): ("strategy", "term", "preferred"),
        ("position", "confirm"): ("id",),
        ("round", "add"): ("strategy", "date", "channel"),
        ("round", "review"): ("id", "went_well", "went_wrong", "lesson", "rating"),
    }
    need = reqs.get((args.cmd, getattr(args, "action", None)))
    if need:
        missing = [k for k in need if getattr(args, k, None) in (None, "")]
        if missing:
            sys.exit(
                f"missing required: {', '.join('--' + m.replace('_', '-') for m in missing)}"
            )
    # strict ISO enforcement on every write-path date (codex finding 7)
    if args.cmd == "trail-add":
        _valid_date(args.date, "--date")
    if args.cmd == "milestone" and args.action == "add":
        _valid_date(args.date, "--date")
    if args.cmd == "open-item" and args.action == "add" and args.due:
        _valid_date(args.due, "--due")
    if args.cmd == "round" and args.action == "add":
        _valid_date(args.date, "--date")

    {
        "migrate": cmd_migrate,
        "watch": cmd_watch,
        "triage": cmd_triage,
        "trail-add": cmd_trail_add,
        "milestone": cmd_milestone,
        "open-item": cmd_open_item,
        "position": cmd_position,
        "round": cmd_round,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
