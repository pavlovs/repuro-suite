"""SQLite knowledge base — persistent cache for scraped text and ownership data.

All expensive external fetches (website scraping, ownership API calls) are cached here.
Cache is never deleted between pipeline runs — only TTL-expired entries are re-fetched.
This prevents paying for the same domain twice across runs or across profiles.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS domain_cache (
    domain          TEXT PRIMARY KEY,
    scraped_text    TEXT,
    scraped_at      TIMESTAMP,
    http_status     INTEGER,
    source_urls     TEXT
);

CREATE TABLE IF NOT EXISTS ownership_cache (
    domain                      TEXT PRIMARY KEY,
    hrb_number                  TEXT,
    gesellschafter_name         TEXT,
    gesellschafter_share_pct    REAL,
    gesellschafter_age          INTEGER,
    is_subsidiary               INTEGER,
    is_pe_backed                INTEGER,
    gf_name                     TEXT,
    source                      TEXT,
    raw_response                TEXT,
    all_gesellschafter          TEXT,
    fetched_at                  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    domain      TEXT NOT NULL,
    hrb_number  TEXT,
    doc_type    TEXT NOT NULL,
    content     TEXT,
    fetched_at  TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(domain, doc_type);
"""


class KnowledgeBase:
    """Thread-safe SQLite wrapper for all cached pipeline data."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns that may be missing from older DBs."""
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(ownership_cache)").fetchall()
        }
        if "all_gesellschafter" not in existing:
            conn.execute(
                "ALTER TABLE ownership_cache ADD COLUMN all_gesellschafter TEXT"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # domain_cache
    # -------------------------------------------------------------------------

    def get_scraped_text(self, domain: str, max_age_days: int = 90) -> Optional[str]:
        """Return cached scraped text if younger than max_age_days, else None."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT scraped_text, scraped_at FROM domain_cache WHERE domain = ?",
                (domain,),
            ).fetchone()
        if not row or not row[0]:
            return None
        if row[1]:
            try:
                scraped_at = datetime.fromisoformat(str(row[1]))
                if scraped_at.tzinfo is None:
                    scraped_at = scraped_at.replace(tzinfo=timezone.utc)
                if scraped_at <= cutoff:
                    return None
            except ValueError:
                pass
        return row[0]

    def save_scraped_text(
        self,
        domain: str,
        text: str,
        http_status: int = 200,
        source_urls: Optional[list[str]] = None,
    ) -> None:
        urls_json = json.dumps(source_urls or [])
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO domain_cache (domain, scraped_text, scraped_at, http_status, source_urls)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                     scraped_text = excluded.scraped_text,
                     scraped_at   = excluded.scraped_at,
                     http_status  = excluded.http_status,
                     source_urls  = excluded.source_urls""",
                (domain, text, self._now(), http_status, urls_json),
            )

    def domain_already_seen(self, domain: str) -> bool:
        """True if domain exists in cache at all (regardless of TTL)."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM domain_cache WHERE domain = ?", (domain,)
            ).fetchone()
        return row is not None

    # -------------------------------------------------------------------------
    # ownership_cache
    # -------------------------------------------------------------------------

    def get_ownership(self, domain: str, max_age_days: int = 180) -> Optional[dict]:
        """Return cached ownership data if younger than max_age_days, else None."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with self._conn() as conn:
            # all_gesellschafter added in bug-fix (previously only majority owner was stored).
            # Old KB rows won't have it — SELECT returns None for missing column values,
            # which the enrich pipeline handles gracefully via result.get("all_gesellschafter").
            cur = conn.execute(
                "SELECT domain, hrb_number, gesellschafter_name, gesellschafter_share_pct, "
                "gesellschafter_age, is_subsidiary, is_pe_backed, gf_name, source, "
                "raw_response, all_gesellschafter, fetched_at "
                "FROM ownership_cache WHERE domain = ?",
                (domain,),
            )
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        if d.get("fetched_at"):
            try:
                fetched_at = datetime.fromisoformat(str(d["fetched_at"]))
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                if fetched_at <= cutoff:
                    return None
            except ValueError:
                pass
        return d

    def save_ownership(self, domain: str, data: dict, source: str) -> None:
        """Cache ownership data. Upserts on domain."""
        is_sub = data.get("is_subsidiary")
        is_pe = data.get("is_pe_backed")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO ownership_cache
                   (domain, hrb_number, gesellschafter_name, gesellschafter_share_pct,
                    gesellschafter_age, is_subsidiary, is_pe_backed, gf_name,
                    source, raw_response, all_gesellschafter, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(domain) DO UPDATE SET
                     hrb_number               = excluded.hrb_number,
                     gesellschafter_name      = excluded.gesellschafter_name,
                     gesellschafter_share_pct = excluded.gesellschafter_share_pct,
                     gesellschafter_age       = excluded.gesellschafter_age,
                     is_subsidiary            = excluded.is_subsidiary,
                     is_pe_backed             = excluded.is_pe_backed,
                     gf_name                  = excluded.gf_name,
                     source                   = excluded.source,
                     raw_response             = excluded.raw_response,
                     all_gesellschafter       = excluded.all_gesellschafter,
                     fetched_at               = excluded.fetched_at""",
                (
                    domain,
                    data.get("hrb_number"),
                    data.get("gesellschafter_name"),
                    data.get("gesellschafter_share_pct"),
                    data.get("gesellschafter_age"),
                    int(is_sub) if is_sub is not None else None,
                    int(is_pe) if is_pe is not None else None,
                    data.get("gf_name"),
                    source,
                    json.dumps(data.get("raw_response", {})),
                    data.get("all_gesellschafter"),
                    self._now(),
                ),
            )

    # -------------------------------------------------------------------------
    # documents
    # -------------------------------------------------------------------------

    def get_document(self, domain: str, doc_type: str) -> Optional[str]:
        """Return most recent document of given type for domain."""
        with self._conn() as conn:
            row = conn.execute(
                """SELECT content FROM documents
                   WHERE domain = ? AND doc_type = ?
                   ORDER BY fetched_at DESC LIMIT 1""",
                (domain, doc_type),
            ).fetchone()
        return row[0] if row else None

    def save_document(
        self,
        domain: str,
        hrb_number: Optional[str],
        doc_type: str,
        content: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO documents (domain, hrb_number, doc_type, content, fetched_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (domain, hrb_number, doc_type, content, self._now()),
            )

    # -------------------------------------------------------------------------
    # stats
    # -------------------------------------------------------------------------

    def stats(self) -> dict:
        """Return record counts for status display."""
        with self._conn() as conn:
            domains = conn.execute("SELECT COUNT(*) FROM domain_cache").fetchone()[0]
            with_text = conn.execute(
                "SELECT COUNT(*) FROM domain_cache WHERE scraped_text IS NOT NULL AND scraped_text != ''"
            ).fetchone()[0]
            ownership = conn.execute("SELECT COUNT(*) FROM ownership_cache").fetchone()[
                0
            ]
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return {
            "domains_cached": domains,
            "with_text": with_text,
            "ownership_cached": ownership,
            "documents": docs,
        }
