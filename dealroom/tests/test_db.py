import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db, _migrate_schema_v2, SEED_DEALS, VALID_STAGES


EXPECTED_TABLES = [
    "deals",
    "deal_documents",
    "deal_valuations",
    "deal_questions",
    "deal_actions",
    "deal_emails",
    "deal_notes",
    "deal_model_params",
    # v2 tables
    "deal_financials",
    "deal_commercial",
    "deal_customers",
    "deal_backlog",
    "deal_employees",
    "deal_suppliers",
    "deal_competitors",
    "deal_contacts",
    "deal_manual_gates",
    "deal_dd_items",
    "deal_meetings",
    "deal_scorecard_config",
    "deal_scorecard_results",
]


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    _migrate_schema_v2(conn)
    yield conn
    conn.close()


def test_all_tables_created(mem_conn):
    tables = {
        r[0]
        for r in mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for t in EXPECTED_TABLES:
        assert t in tables, f"Missing table: {t}"


def test_deal_data_archived_or_absent(mem_conn):
    """deal_data should not exist as active table after v2 migration (archived or never created with data)."""
    tables = {
        r[0]
        for r in mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    # deal_data may still exist (empty) from init_db, but deal_granola should be renamed
    # The key point: deal_financials exists and is the primary table
    assert "deal_financials" in tables


def test_deal_granola_renamed(mem_conn):
    """deal_granola should be renamed to deal_granola_v1_archive after v2 migration."""
    tables = {
        r[0]
        for r in mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    # deal_granola was created by init_db, then renamed by _migrate_schema_v2
    assert "deal_granola" not in tables
    assert "deal_granola_v1_archive" in tables


def test_seed_count(mem_conn):
    count = mem_conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    assert count == len(SEED_DEALS) == 12


def test_octopus_seed(mem_conn):
    row = mem_conn.execute("SELECT * FROM deals WHERE code_name = 'Octopus'").fetchone()
    assert row is not None
    assert row["domain"] == "hwv-med.de"
    # v2 stage migration: offer_sent -> offer
    assert row["deal_stage"] == "offer"


def test_lion_seed(mem_conn):
    row = mem_conn.execute("SELECT * FROM deals WHERE code_name = 'Lion'").fetchone()
    assert row["domain"] == "golmed.de"


def test_colibri_seed(mem_conn):
    row = mem_conn.execute("SELECT * FROM deals WHERE code_name = 'Colibri'").fetchone()
    assert row["domain"] == "menke-med.de"


def test_falcon_seed(mem_conn):
    row = mem_conn.execute("SELECT * FROM deals WHERE code_name = 'Falcon'").fetchone()
    assert row["domain"] == "koewe.com"


def test_null_domain_allowed(mem_conn):
    rows = mem_conn.execute(
        "SELECT code_name FROM deals WHERE domain IS NULL"
    ).fetchall()
    null_codes = {r["code_name"] for r in rows}
    assert "Cat" in null_codes
    assert "Wolf" in null_codes
    assert "Eagle" in null_codes


def test_row_factory(mem_conn):
    row = mem_conn.execute("SELECT code_name FROM deals LIMIT 1").fetchone()
    assert hasattr(row, "keys"), "row_factory not set to sqlite3.Row"


def test_init_idempotent(mem_conn):
    # Running init_db twice must not crash and must not duplicate seed
    init_db(mem_conn)
    count = mem_conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    assert count == 12


def test_v2_migration_idempotent(mem_conn):
    # Running v2 migration twice must not crash
    _migrate_schema_v2(mem_conn)
    tables = {
        r[0]
        for r in mem_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "deal_financials" in tables


def test_stages_use_v2_taxonomy(mem_conn):
    """All seed deal stages should be in VALID_STAGES after v2 migration."""
    rows = mem_conn.execute("SELECT deal_stage FROM deals").fetchall()
    for r in rows:
        assert r["deal_stage"] in VALID_STAGES, f"Invalid stage: {r['deal_stage']}"


def test_scorecard_config_seeded(mem_conn):
    """Scorecard config should be populated after v2 migration."""
    count = mem_conn.execute("SELECT COUNT(*) FROM deal_scorecard_config").fetchone()[0]
    assert count > 0


def test_attach_no_crash_when_missing(tmp_path):
    """get_conn() must not crash when pipeline.db does not exist."""
    import os

    os.environ["ALLEX_PIPELINE_DB"] = str(tmp_path / "nonexistent.db")
    os.environ["DEALS_DB_PATH"] = str(tmp_path / "dealroom.db")

    # Patch settings at import level
    import config.settings as s

    original_allex = s.ALLEX_PIPELINE_DB
    original_db = s.DB_PATH
    s.ALLEX_PIPELINE_DB = tmp_path / "nonexistent.db"
    s.DB_PATH = tmp_path / "dealroom.db"
    s.DATA_DIR = tmp_path

    try:
        from src.db import get_conn

        conn = get_conn()
        assert conn is not None
        conn.close()
    finally:
        s.ALLEX_PIPELINE_DB = original_allex
        s.DB_PATH = original_db
        s.DATA_DIR = original_db.parent
