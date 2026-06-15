"""SQLite pipeline database — shared by all pipeline stages M3-M11."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.pipeline.models import CompanyRecord

log = logging.getLogger(__name__)

# Pipeline stage values (set as records progress through the pipeline)
STAGE_INGESTED = "ingested"
STAGE_FILTERED = "filtered"
STAGE_SCRAPED = "scraped"
STAGE_SCRAPE_FAILED = "scrape_failed"
STAGE_CLASSIFIED = "classified"
STAGE_OWNERSHIP_ENRICHED = "ownership_enriched"
STAGE_OWNERSHIP_REVIEW_NEEDED = "ownership_review_needed"
STAGE_OWNERSHIP_GATED = "ownership_gated"
STAGE_EMAIL_ENRICHED = "email_enriched"


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS company_records (
    id                       TEXT PRIMARY KEY,
    domain                   TEXT UNIQUE NOT NULL,
    full_name                TEXT NOT NULL,
    profile_id               TEXT NOT NULL,
    source                   TEXT NOT NULL,
    pipeline_stage           TEXT NOT NULL DEFAULT 'ingested',
    hrb_number               TEXT,
    rechtsform               TEXT,
    street                   TEXT,
    plz_ort                  TEXT,
    city                     TEXT,
    region                   TEXT,
    ma_count                 INTEGER,
    revenue_tsd_eur          REAL,
    klass                    TEXT,
    services_score           INTEGER,
    service_flag             INTEGER,
    distributor_flag         INTEGER,
    ssb_flag                 INTEGER,
    leistung_text            TEXT,
    reasoning                TEXT,
    compliment_draft         TEXT,
    compliment_2             TEXT,
    reclassify_reason        TEXT,
    gesellschafter_name      TEXT,
    gesellschafter_share_pct REAL,
    gesellschafter_age       INTEGER,
    is_subsidiary            INTEGER,
    is_pe_backed             INTEGER,
    owner_name               TEXT,
    gf_name                  TEXT,
    gf_email                 TEXT,
    gf_phone                 TEXT,
    anrede                   TEXT,
    salutation               TEXT,
    already_approached       INTEGER NOT NULL DEFAULT 0,
    filter_pass              INTEGER,
    filter_reason            TEXT,
    ownership_pass           INTEGER,
    ownership_reason         TEXT,
    scraped_text             TEXT,
    scraped_at               TEXT,
    classified_at            TEXT,
    enriched_at              TEXT,
    ingested_at              TEXT NOT NULL,
    outreach_status          TEXT,
    outreach_sent_at         TEXT,
    outreach_comment         TEXT,
    followup1_at             TEXT,
    followup2_at             TEXT,
    followup_comment         TEXT
)
"""


_warned_this_session: set[str] = set()


def _check_other_agent_active(db_path: Path) -> None:
    """Warn once per session if the other agent is active and claims DB-related files."""
    active_dir = db_path.resolve().parent
    for _ in range(4):
        active_dir = active_dir.parent
        candidate = active_dir / ".active"
        if candidate.is_dir():
            break
    else:
        return
    my_user = os.environ.get("USERNAME", os.environ.get("USER", "")).lower()
    db_name = db_path.name
    for md in candidate.glob("*.md"):
        agent_name = md.stem.lower()
        if agent_name == my_user:
            continue
        warn_key = f"{agent_name}:{db_name}"
        if warn_key in _warned_this_session:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        status_m = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
        if not status_m or status_m.group(1) != "active":
            continue
        if db_name in text or "pipeline" in text.lower():
            _warned_this_session.add(warn_key)
            log.warning(
                "OTHER AGENT ACTIVE: %s may be using %s -- coordinate or wait.",
                agent_name.title(),
                db_name,
            )
            print(
                f"WARNING: {agent_name.title()}'s agent is active and may be using {db_name}. "
                f"Risk of OneDrive conflict."
            )


@contextmanager
def get_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a committed-or-rolled-back SQLite connection."""
    _check_other_agent_active(db_path)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "PRAGMA journal_mode=DELETE"
    )  # DELETE not WAL -- OneDrive can't sync WAL's 3-file set safely
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_OUTREACH_COLUMNS: list[tuple[str, str]] = [
    ("outreach_status", "TEXT"),
    ("outreach_sent_at", "TEXT"),
    ("outreach_comment", "TEXT"),
    ("followup1_at", "TEXT"),
    ("followup2_at", "TEXT"),
    ("followup_comment", "TEXT"),
    ("hubspot_company_id", "TEXT"),
    ("hubspot_contact_id", "TEXT"),
    ("briefaktion", "TEXT"),
    ("compliment_2", "TEXT"),
    ("owner_name", "TEXT"),
    ("approved_for_sendout", "INTEGER NOT NULL DEFAULT 0"),
    ("region_prep", "TEXT"),
    ("leistung_absatz_2", "TEXT"),
    ("mehrwerte", "TEXT"),
    ("impressum_name", "TEXT"),
    ("impressum_address", "TEXT"),
    (
        "all_gesellschafter",
        "TEXT",
    ),  # JSON array of all OpenRegister owners, sorted by % desc
    (
        "parent_owners",
        "TEXT",
    ),  # JSON array: holding company's shareholders (from _resolve_ubo)
    ("manual_note", "TEXT"),  # free-text note field for manual review comments
    (
        "sections_reviewed",
        "TEXT",
    ),  # JSON: {"gesellschafter":1,"stammdaten":1,"briefvorbereitung":0,"notizen":0}
    (
        "prio",
        "TEXT",
    ),  # M36: queue priority — 'Prio 1', 'Prio 2 (small/big/intl/other)', 'Duplicate', 'Excluded'
    ("gruppe_1", "TEXT"),  # M36: category-driven letter field
    ("gruppe_2", "TEXT"),  # M36: category-driven letter field
    ("gesellschafter_field", "TEXT"),  # M36: gendered from Anrede for letter merge
    ("gesellschafter_note", "TEXT"),
    ("openregister_address", "TEXT"),
]


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add any missing columns to an existing table (forward-only migration)."""
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info(company_records)").fetchall()
    }
    newly_added: set[str] = set()
    for col_name, col_type in _OUTREACH_COLUMNS:
        if col_name not in existing:
            conn.execute(
                f"ALTER TABLE company_records ADD COLUMN {col_name} {col_type}"
            )
            newly_added.add(col_name)
    # Data migration: backfill owner_name from gf_name for existing records.
    # gf_name previously stored the owner/addressee; owner_name is the correct column going forward.
    if "owner_name" in newly_added and "gf_name" in existing:
        # Copy old owner data to owner_name, then clear gf_name.
        # gf_name previously stored the owner/addressee. After rename it is
        # reserved for impressum GF (M20). Clearing avoids COALESCE blocking M20.
        conn.execute(
            "UPDATE company_records SET owner_name = gf_name WHERE owner_name IS NULL AND gf_name IS NOT NULL"
        )
        conn.execute("UPDATE company_records SET gf_name = NULL")
    # M36: backfill prio from klass — idempotent (WHERE prio IS NULL)
    if "klass" in existing:
        conn.execute(
            "UPDATE company_records SET prio = 'Prio 1' WHERE klass IN ('A', 'B') AND prio IS NULL"
        )
        conn.execute(
            "UPDATE company_records SET prio = 'Prio 2 (other)' WHERE klass IN ('C', 'D', 'E') AND prio IS NULL"
        )
        conn.execute(
            "UPDATE company_records SET prio = 'Excluded' WHERE klass = 'S' AND prio IS NULL"
        )
    # Backfill gesellschafter_field from anrede — idempotent (WHERE ... IS NULL)
    conn.execute("""
        UPDATE company_records
        SET gesellschafter_field = CASE anrede
            WHEN 'Frau' THEN 'Gesellschafterin'
            ELSE 'Gesellschafter'
        END
        WHERE (gesellschafter_field IS NULL OR gesellschafter_field = '')
        AND anrede IS NOT NULL AND anrede != ''
    """)


_CREATE_ACTIVITY_LOG = """
CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'unknown',
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
)
"""


def _ensure_activity_log(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_ACTIVITY_LOG)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_domain ON activity_log (domain)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_changed_at ON activity_log (changed_at)"
    )


def log_activity(
    conn: sqlite3.Connection,
    domain: str,
    actor: str,
    field: str,
    old_value: "str | None",
    new_value: "str | None",
) -> None:
    """Append one field-change row to activity_log. Call inside an open get_connection block."""
    conn.execute(
        "INSERT INTO activity_log (domain, actor, field, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
        (domain, actor or "unknown", field, old_value, new_value),
    )


def ensure_schema(db_path: Path) -> None:
    """Create tables if they don't exist and migrate any missing columns. Safe to call repeatedly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.execute(_CREATE_TABLE)
        _migrate_schema(conn)
        _ensure_activity_log(conn)


def upsert_company(
    conn: sqlite3.Connection, rec: CompanyRecord, ingested_at: str
) -> None:
    """
    Insert or update a company record.
    On domain conflict: fill NULL fields from the new record via COALESCE.
    Caller controls source priority by inserting high-priority records first
    (ORBIS before WLW), so COALESCE keeps the first non-null value.
    """
    conn.execute(
        """
        INSERT INTO company_records (
            id, domain, full_name, profile_id, source, pipeline_stage,
            hrb_number, rechtsform, street, plz_ort, city, region,
            ma_count, revenue_tsd_eur,
            gesellschafter_name, gesellschafter_share_pct, gesellschafter_age,
            is_subsidiary, is_pe_backed,
            owner_name, gf_name, gf_email, gf_phone, anrede, salutation,
            already_approached, scraped_text, ingested_at
        ) VALUES (
            :id, :domain, :full_name, :profile_id, :source, 'ingested',
            :hrb_number, :rechtsform, :street, :plz_ort, :city, :region,
            :ma_count, :revenue_tsd_eur,
            :gesellschafter_name, :gesellschafter_share_pct, :gesellschafter_age,
            :is_subsidiary, :is_pe_backed,
            :owner_name, :gf_name, :gf_email, :gf_phone, :anrede, :salutation,
            :already_approached, :scraped_text, :ingested_at
        )
        ON CONFLICT(domain) DO UPDATE SET
            hrb_number               = COALESCE(company_records.hrb_number,               excluded.hrb_number),
            rechtsform               = COALESCE(company_records.rechtsform,               excluded.rechtsform),
            street                   = COALESCE(company_records.street,                   excluded.street),
            plz_ort                  = COALESCE(company_records.plz_ort,                  excluded.plz_ort),
            city                     = COALESCE(company_records.city,                     excluded.city),
            region                   = COALESCE(company_records.region,                   excluded.region),
            ma_count                 = COALESCE(company_records.ma_count,                 excluded.ma_count),
            revenue_tsd_eur          = COALESCE(company_records.revenue_tsd_eur,          excluded.revenue_tsd_eur),
            gesellschafter_name      = COALESCE(company_records.gesellschafter_name,      excluded.gesellschafter_name),
            gesellschafter_share_pct = COALESCE(company_records.gesellschafter_share_pct, excluded.gesellschafter_share_pct),
            gesellschafter_age       = COALESCE(company_records.gesellschafter_age,       excluded.gesellschafter_age),
            is_subsidiary            = COALESCE(company_records.is_subsidiary,            excluded.is_subsidiary),
            owner_name               = COALESCE(company_records.owner_name,               excluded.owner_name),
            gf_name                  = COALESCE(company_records.gf_name,                  excluded.gf_name),
            anrede                   = COALESCE(company_records.anrede,                   excluded.anrede),
            scraped_text             = COALESCE(company_records.scraped_text,             excluded.scraped_text),
            already_approached       = MAX(company_records.already_approached,            excluded.already_approached)
        """,
        {
            "id": rec.id,
            "domain": rec.domain,
            "full_name": rec.full_name,
            "profile_id": rec.profile_id,
            "source": rec.source,
            "hrb_number": rec.hrb_number,
            "rechtsform": rec.rechtsform,
            "street": rec.street,
            "plz_ort": rec.plz_ort,
            "city": rec.city,
            "region": rec.region,
            "ma_count": rec.ma_count,
            "revenue_tsd_eur": rec.revenue_tsd_eur,
            "gesellschafter_name": rec.gesellschafter_name,
            "gesellschafter_share_pct": rec.gesellschafter_share_pct,
            "gesellschafter_age": rec.gesellschafter_age,
            "is_subsidiary": int(rec.is_subsidiary)
            if rec.is_subsidiary is not None
            else None,
            "is_pe_backed": int(rec.is_pe_backed)
            if rec.is_pe_backed is not None
            else None,
            "owner_name": rec.owner_name,
            "gf_name": rec.gf_name,
            "gf_email": rec.gf_email,
            "gf_phone": rec.gf_phone,
            "anrede": rec.anrede,
            "salutation": rec.salutation,
            "already_approached": 1 if rec.already_approached else 0,
            "scraped_text": rec.scraped_text,
            "ingested_at": ingested_at,
        },
    )


def mark_approached(conn: sqlite3.Connection, domains: frozenset[str]) -> int:
    """Set already_approached=1 for all matching domains. Returns count updated."""
    if not domains:
        return 0
    placeholders = ",".join("?" * len(domains))
    cursor = conn.execute(
        f"UPDATE company_records SET already_approached=1 WHERE domain IN ({placeholders})",
        list(domains),
    )
    return cursor.rowcount


def get_stage_counts(db_path: Path) -> dict[str, int]:
    """Return {pipeline_stage: count} for the status command."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT pipeline_stage, COUNT(*) FROM company_records GROUP BY pipeline_stage"
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def get_total_count(db_path: Path) -> int:
    """Return total number of company records."""
    with get_connection(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM company_records").fetchone()[0]


def get_klass_counts(db_path: Path) -> dict[str, int]:
    """Return {klass: count} for classified records."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT klass, COUNT(*) FROM company_records WHERE klass IS NOT NULL GROUP BY klass"
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def get_records_for_filter(db_path: Path) -> "list[CompanyRecord]":
    """Return all records not yet filtered (filter_pass IS NULL)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM company_records WHERE filter_pass IS NULL"
        ).fetchall()
    return [_row_to_company_record(row) for row in rows]


def update_filter_result(
    conn: sqlite3.Connection,
    domain: str,
    filter_pass: bool,
    filter_reason: "str | None",
) -> None:
    """Write filter outcome for one record. Advances stage to 'filtered' if passing."""
    new_stage = STAGE_FILTERED if filter_pass else STAGE_INGESTED
    conn.execute(
        """
        UPDATE company_records
        SET filter_pass = ?, filter_reason = ?, pipeline_stage = ?
        WHERE domain = ?
        """,
        (1 if filter_pass else 0, filter_reason, new_stage, domain),
    )


def upsert_serienbriefe_record(
    conn: sqlite3.Connection, rec: dict, ingested_at: str
) -> str:
    """Upsert one Serienbriefe record into company_records.

    - New domain: INSERT with source='serienbriefe', pipeline_stage='approached'.
    - Existing domain: UPDATE briefaktion (always), fill NULL outreach/enrichment fields.

    Returns 'inserted' or 'updated'.
    """
    existing = conn.execute(
        "SELECT domain FROM company_records WHERE domain = ?", (rec["domain"],)
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE company_records SET
                already_approached    = 1,
                briefaktion           = :briefaktion,
                outreach_status       = :outreach_status,
                outreach_sent_at      = COALESCE(outreach_sent_at,      :outreach_sent_at),
                outreach_comment      = COALESCE(outreach_comment,      :outreach_comment),
                klass                 = COALESCE(klass,                 :klass),
                owner_name            = COALESCE(owner_name,            :owner_name),
                gesellschafter_name   = COALESCE(gesellschafter_name,   :gesellschafter_name),
                gf_email              = COALESCE(gf_email,              :gf_email),
                gf_phone              = COALESCE(gf_phone,              :gf_phone),
                gesellschafter_age    = COALESCE(gesellschafter_age,    :gesellschafter_age),
                anrede                = COALESCE(anrede,                :anrede),
                salutation            = COALESCE(salutation,            :salutation),
                hrb_number            = COALESCE(hrb_number,            :hrb_number),
                rechtsform            = COALESCE(rechtsform,            :rechtsform),
                ma_count              = COALESCE(ma_count,              :ma_count),
                city                  = COALESCE(city,                  :city),
                street                = COALESCE(street,                :street),
                plz_ort               = COALESCE(plz_ort,               :plz_ort),
                compliment_draft      = COALESCE(compliment_draft,      :compliment_draft),
                compliment_2          = COALESCE(compliment_2,          :compliment_2)
            WHERE domain = :domain
            """,
            rec,
        )
        return "updated"

    conn.execute(
        """
        INSERT INTO company_records (
            id, domain, full_name, profile_id, source, pipeline_stage,
            already_approached, briefaktion, outreach_status, outreach_sent_at,
            outreach_comment, klass, owner_name, gesellschafter_name, gf_email, gf_phone,
            gesellschafter_age, anrede, salutation, hrb_number, rechtsform,
            ma_count, city, street, plz_ort, compliment_draft, compliment_2, ingested_at
        ) VALUES (
            :id, :domain, :full_name, :profile_id, :source, :pipeline_stage,
            1, :briefaktion, :outreach_status, :outreach_sent_at,
            :outreach_comment, :klass, :owner_name, :gesellschafter_name, :gf_email, :gf_phone,
            :gesellschafter_age, :anrede, :salutation, :hrb_number, :rechtsform,
            :ma_count, :city, :street, :plz_ort, :compliment_draft, :compliment_2, :ingested_at
        )
        """,
        {**rec, "ingested_at": ingested_at},
    )
    return "inserted"


def get_unapproached_for_audit(db_path: Path) -> list[dict]:
    """Return all records with already_approached=0 for dedup audit.

    Returns list of dicts with keys: domain, full_name, klass, pipeline_stage.
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT domain, full_name, klass, pipeline_stage
            FROM company_records
            WHERE already_approached = 0
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fix_approached_bulk(conn: sqlite3.Connection, domains: list[str]) -> int:
    """Set already_approached=1 for given domains (dedup gate only).

    Does NOT set outreach_status — that is managed exclusively by ingest_serienbriefe
    which has the BA assignment and FU status from the sheet.
    Idempotent — records already marked are not affected.
    Returns number of rows actually updated.
    """
    if not domains:
        return 0
    placeholders = ",".join("?" * len(domains))
    cursor = conn.execute(
        f"""
        UPDATE company_records
        SET already_approached = 1
        WHERE domain IN ({placeholders})
          AND already_approached = 0
        """,
        domains,
    )
    return cursor.rowcount


def get_filter_counts(db_path: Path) -> dict[str, int]:
    """Return {pass: N, fail: N, pending: N} for filter status display."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN filter_pass = 1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN filter_pass = 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN filter_pass IS NULL THEN 1 ELSE 0 END)
            FROM company_records
            """
        ).fetchone()
    return {"pass": row[0] or 0, "fail": row[1] or 0, "pending": row[2] or 0}


def get_records_for_scrape(db_path: Path) -> list[CompanyRecord]:
    """Return all records at pipeline_stage='filtered' (not yet scraped)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM company_records WHERE pipeline_stage = 'filtered'"
        ).fetchall()
    return [_row_to_company_record(row) for row in rows]


def update_scrape_result(
    conn: sqlite3.Connection,
    domain: str,
    scraped_text: str,
    scraped_at: str,
) -> None:
    """Write scrape result for one record. Advances stage to 'scraped' if text non-empty."""
    new_stage = STAGE_SCRAPED if scraped_text else STAGE_SCRAPE_FAILED
    conn.execute(
        """
        UPDATE company_records
        SET scraped_text = ?, scraped_at = ?, pipeline_stage = ?
        WHERE domain = ?
        """,
        (scraped_text, scraped_at, new_stage, domain),
    )


def get_scrape_counts(db_path: Path) -> dict[str, int]:
    """Return {scraped: N, failed: N, pending: N} for status display."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN pipeline_stage = 'scraped'       THEN 1 ELSE 0 END),
                SUM(CASE WHEN pipeline_stage = 'scrape_failed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN pipeline_stage = 'filtered'      THEN 1 ELSE 0 END)
            FROM company_records
            """
        ).fetchone()
    return {"scraped": row[0] or 0, "failed": row[1] or 0, "pending": row[2] or 0}


def get_records_for_classify(db_path: Path) -> list[CompanyRecord]:
    """Return all records at pipeline_stage='scraped' (not yet classified)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM company_records WHERE pipeline_stage = 'scraped'"
        ).fetchall()
    return [_row_to_company_record(row) for row in rows]


def update_classify_result(
    conn: sqlite3.Connection,
    domain: str,
    klass: str,
    services_score: int,
    service_flag: bool,
    distributor_flag: bool,
    ssb_flag: bool,
    leistung_text: str,
    leistung_absatz_2: str,
    mehrwerte: str,
    reason_code: str,
    reasoning: str,
    classified_at: str,
) -> int:
    """Write classification result. Advances stage to 'classified'.

    Returns rowcount (0 = domain not found — caller must log error).
    compliment_draft excluded — generated at export stage only.
    """
    # Derive prio from klass so prio-based queries find newly classified records
    if klass in ("A", "B"):
        prio = "Prio 1"
    elif klass == "S":
        prio = "Excluded"
    elif klass in ("C", "D", "E"):
        prio = "Prio 2 (other)"
    else:
        prio = None

    from src.pipeline.category_defaults import TARGET_CATEGORIES, _SHARED_DEFAULTS

    # Set gruppe_1/gruppe_2 for target-quality records (A/B or new category codes)
    is_target = klass in ("A", "B") or klass in TARGET_CATEGORIES
    gruppe_1 = _SHARED_DEFAULTS["gruppe_1"] if is_target else None
    gruppe_2 = _SHARED_DEFAULTS["gruppe_2"] if is_target else None

    cursor = conn.execute(
        """
        UPDATE company_records
        SET klass=?, services_score=?, service_flag=?, distributor_flag=?,
            ssb_flag=?, leistung_text=?, leistung_absatz_2=?, mehrwerte=?,
            reclassify_reason=?, reasoning=?, classified_at=?,
            prio=COALESCE(prio, ?),
            gruppe_1=COALESCE(gruppe_1, ?),
            gruppe_2=COALESCE(gruppe_2, ?),
            gesellschafter_field=COALESCE(gesellschafter_field,
                CASE anrede WHEN 'Frau' THEN 'Gesellschafterin' ELSE 'Gesellschafter' END),
            pipeline_stage='classified'
        WHERE domain=?
        """,
        (
            klass,
            services_score,
            1 if service_flag else 0,
            1 if distributor_flag else 0,
            1 if ssb_flag else 0,
            leistung_text,
            leistung_absatz_2,
            mehrwerte,
            reason_code,
            reasoning,
            classified_at,
            prio,
            gruppe_1,
            gruppe_2,
            domain,
        ),
    )
    return cursor.rowcount


def get_classify_counts(db_path: Path) -> dict[str, int]:
    """Return {classified: N, pending: N} + per-klass counts."""
    with get_connection(db_path) as conn:
        total_row = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE pipeline_stage = 'classified'"
        ).fetchone()
        pending_row = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE pipeline_stage = 'scraped'"
        ).fetchone()
        klass_rows = conn.execute(
            "SELECT klass, COUNT(*) FROM company_records WHERE klass IS NOT NULL GROUP BY klass"
        ).fetchall()
    result = {
        "classified": total_row[0] or 0,
        "pending": pending_row[0] or 0,
    }
    for row in klass_rows:
        result[row[0]] = row[1]
    return result


def get_records_for_enrich(db_path: Path) -> list[CompanyRecord]:
    """Return A/B classified records not yet ownership-enriched."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT * FROM company_records
               WHERE pipeline_stage = 'classified'
               AND prio = 'Prio 1'"""
        ).fetchall()
    return [_row_to_company_record(row) for row in rows]


def update_ownership_result(
    conn: sqlite3.Connection,
    domain: str,
    gesellschafter_name: "str | None",
    gesellschafter_share_pct: "float | None",
    gesellschafter_age: "int | None",
    is_subsidiary: "bool | None",
    is_pe_backed: "bool | None",
    gf_name: "str | None",
    hrb_number: "str | None",
    enriched_at: str,
    stage: str = STAGE_OWNERSHIP_ENRICHED,
    ownership_reason: "str | None" = None,
    all_gesellschafter: "str | None" = None,
    parent_owners: "str | None" = None,
    openregister_address: "str | None" = None,
) -> None:
    """Write ownership enrichment result. Advances stage to given stage (default: ownership_enriched)."""
    conn.execute(
        """
        UPDATE company_records
        SET gesellschafter_name = COALESCE(gesellschafter_name, ?),
            gesellschafter_share_pct = COALESCE(gesellschafter_share_pct, ?),
            gesellschafter_age = COALESCE(gesellschafter_age, ?),
            is_subsidiary = COALESCE(is_subsidiary, ?),
            is_pe_backed = COALESCE(is_pe_backed, ?),
            gf_name = COALESCE(gf_name, ?),
            hrb_number = COALESCE(hrb_number, ?),
            ownership_reason = COALESCE(ownership_reason, ?),
            all_gesellschafter = COALESCE(all_gesellschafter, ?),
            parent_owners = COALESCE(?, parent_owners),
            openregister_address = COALESCE(?, openregister_address),
            enriched_at = ?,
            pipeline_stage = ?
        WHERE domain = ?
        """,
        (
            gesellschafter_name,
            gesellschafter_share_pct,
            gesellschafter_age,
            int(is_subsidiary) if is_subsidiary is not None else None,
            int(is_pe_backed) if is_pe_backed is not None else None,
            gf_name,
            hrb_number,
            ownership_reason,
            all_gesellschafter,
            parent_owners,
            openregister_address,
            enriched_at,
            stage,
            domain,
        ),
    )


def update_gf_enrichment(
    conn: sqlite3.Connection,
    domain: str,
    gf_name: "str | None",
    impressum_address: "str | None",
    gf_email: "str | None",
) -> None:
    """Write GF enrichment fields. Only overwrites gf_email if currently empty."""
    conn.execute(
        """
        UPDATE company_records
        SET gf_name = COALESCE(?, gf_name),
            impressum_address = COALESCE(?, impressum_address),
            gf_email = CASE WHEN (gf_email IS NULL OR gf_email = '') THEN COALESCE(?, gf_email)
                            ELSE gf_email END
        WHERE domain = ?
        """,
        (gf_name, impressum_address, gf_email, domain),
    )


def apply_ownership_gate_db(
    conn: sqlite3.Connection,
    domain: str,
    reclassify_reason: str,
) -> None:
    """Set prio='Excluded' for subsidiary/PE-backed records. Category (klass) stays unchanged."""
    conn.execute(
        """
        UPDATE company_records
        SET prio = 'Excluded', reclassify_reason = ?, pipeline_stage = 'ownership_gated'
        WHERE domain = ?
        """,
        (reclassify_reason, domain),
    )


def advance_ownership_gate(conn: sqlite3.Connection, domain: str) -> None:
    """Advance record that passed ownership gate to 'ownership_gated' stage."""
    conn.execute(
        "UPDATE company_records SET pipeline_stage = 'ownership_gated' WHERE domain = ?",
        (domain,),
    )


def update_compliment_draft(
    conn: sqlite3.Connection, domain: str, compliment: str
) -> None:
    """Write generated compliment_draft. Only sets if currently NULL or empty."""
    conn.execute(
        "UPDATE company_records SET compliment_draft = ? WHERE domain = ? AND (compliment_draft IS NULL OR compliment_draft = '')",
        (compliment, domain),
    )


def update_compliments(
    conn: sqlite3.Connection,
    domain: str,
    k1: "str | None",
    k2: "str | None",
) -> None:
    """Write both compliment slots. Only fills NULL/empty slots (COALESCE semantics)."""
    conn.execute(
        """UPDATE company_records
           SET compliment_draft = CASE WHEN compliment_draft IS NULL OR compliment_draft = '' THEN ? ELSE compliment_draft END,
               compliment_2     = CASE WHEN compliment_2     IS NULL OR compliment_2     = '' THEN ? ELSE compliment_2     END
           WHERE domain = ?""",
        (k1, k2, domain),
    )


def update_email_result(
    conn: sqlite3.Connection,
    domain: str,
    gf_email: "str | None",
    owner_name: "str | None",
    anrede: "str | None",
    salutation: "str | None",
) -> None:
    """Write email enrichment result. Advances stage to 'email_enriched'."""
    conn.execute(
        """
        UPDATE company_records
        SET gf_email = COALESCE(NULLIF(gf_email, ''), ?),
            owner_name = COALESCE(NULLIF(owner_name, ''), ?),
            anrede = COALESCE(NULLIF(anrede, ''), ?),
            salutation = COALESCE(NULLIF(salutation, ''), ?),
            pipeline_stage = 'email_enriched'
        WHERE domain = ?
        """,
        (gf_email, owner_name, anrede, salutation, domain),
    )


def _row_to_company_record(row: sqlite3.Row) -> "CompanyRecord":
    """Convert a sqlite3.Row from company_records to a CompanyRecord dataclass."""
    import dataclasses
    from datetime import datetime

    d = dict(row)
    # Convert INTEGER booleans back to Python bool / None
    for key in (
        "filter_pass",
        "is_subsidiary",
        "is_pe_backed",
        "service_flag",
        "distributor_flag",
        "ssb_flag",
        "ownership_pass",
    ):
        val = d.get(key)
        d[key] = None if val is None else bool(val)
    d["already_approached"] = bool(d.get("already_approached", 0))
    # Deserialize datetime fields stored as ISO strings in the DB
    for key in ("scraped_at", "classified_at", "enriched_at"):
        val = d.get(key)
        if val and str(val) not in ("", "None"):
            try:
                d[key] = datetime.fromisoformat(str(val))
            except ValueError:
                d[key] = None
        else:
            d[key] = None
    # Remove id — recomputed by CompanyRecord.__post_init__
    d.pop("id", None)
    # Remove DB-only field not in CompanyRecord
    d.pop("ingested_at", None)
    valid_fields = {f.name for f in dataclasses.fields(CompanyRecord) if f.name != "id"}
    return CompanyRecord(**{k: d[k] for k in valid_fields if k in d})


_BRIEFAKTION_FIELDS = [
    ("anrede", "anrede IN ('Herr','Frau')"),
    ("salutation", "salutation IS NOT NULL AND salutation != ''"),
    ("street", "street IS NOT NULL AND street != ''"),
    ("plz_ort", "plz_ort IS NOT NULL AND plz_ort != ''"),
    ("region_prep", "region_prep IS NOT NULL AND region_prep != ''"),
    ("leistung", "leistung_text IS NOT NULL AND leistung_text != ''"),
    ("K1", "compliment_draft IS NOT NULL AND compliment_draft != ''"),
    ("K2", "compliment_2 IS NOT NULL AND compliment_2 != ''"),
]


def briefaktion_fill_rates(db_path: Path) -> dict[str, tuple[int, int]]:
    """Return {field_label: (filled_count, total_count)} for A/B records."""
    with get_connection(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM company_records WHERE prio = 'Prio 1'"
        ).fetchone()[0]
        rates = {}
        for label, condition in _BRIEFAKTION_FIELDS:
            filled = conn.execute(
                f"SELECT COUNT(*) FROM company_records WHERE prio = 'Prio 1' AND ({condition})"
            ).fetchone()[0]
            rates[label] = (filled, total)
    return rates


def print_fill_rates(db_path: Path, label: str = "") -> dict[str, tuple[int, int]]:
    """Print Briefaktion fill rates and return the dict."""
    rates = briefaktion_fill_rates(db_path)
    total = next(iter(rates.values()))[1] if rates else 0
    header = f"  FILL RATES ({label})" if label else "  FILL RATES"
    print(f"\n{header} — {total} A/B records")
    for field, (filled, tot) in rates.items():
        pct = (filled / tot * 100) if tot else 0
        bar = "OK" if pct >= 90 else "LOW" if pct >= 50 else "GAP"
        print(f"    {field:12s}: {filled:4d}/{tot} ({pct:5.1f}%) [{bar}]")
    print()
    return rates
