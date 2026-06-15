import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db, _migrate_schema_v2, VALID_STAGES, resolve_folder
import config.settings as settings


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    _migrate_schema_v2(conn)
    yield conn
    conn.close()


def test_deals_query_returns_12(mem_conn):
    rows = mem_conn.execute("SELECT * FROM deals").fetchall()
    assert len(rows) == 12


def test_null_domain_no_crash(mem_conn):
    rows = mem_conn.execute(
        "SELECT code_name, domain FROM deals ORDER BY code_name"
    ).fetchall()
    # Must not crash; NULL domain rows must still be present
    domains = {r["code_name"]: r["domain"] for r in rows}
    assert domains["Cat"] is None
    assert domains["Wolf"] is None


def test_all_stages_valid(mem_conn):
    """All deal stages should be in VALID_STAGES after v2 migration."""
    rows = mem_conn.execute("SELECT deal_stage FROM deals").fetchall()
    for r in rows:
        assert r["deal_stage"] in VALID_STAGES, f"Invalid stage: {r['deal_stage']}"


def test_resolve_folder_returns_none_when_deals_dir_missing(tmp_path):
    original = settings.DEALS_DIR
    settings.DEALS_DIR = tmp_path / "nonexistent_deals_dir"
    try:
        result = resolve_folder("Octopus")
        assert result is None
    finally:
        settings.DEALS_DIR = original


def test_resolve_folder_finds_matching_subfolder(tmp_path):
    original = settings.DEALS_DIR
    settings.DEALS_DIR = tmp_path

    # Create a fake deal folder
    folder = tmp_path / "250611_HWV (Octopus)"
    folder.mkdir()

    try:
        result = resolve_folder("Octopus")
        assert result is not None
        assert result.name == "250611_HWV (Octopus)"
    finally:
        settings.DEALS_DIR = original


def test_resolve_folder_no_match_returns_none(tmp_path):
    original = settings.DEALS_DIR
    settings.DEALS_DIR = tmp_path

    # Create folders that don't match
    (tmp_path / "some_other_folder").mkdir()

    try:
        result = resolve_folder("Octopus")
        assert result is None
    finally:
        settings.DEALS_DIR = original


def test_unique_code_names(mem_conn):
    rows = mem_conn.execute("SELECT code_name FROM deals").fetchall()
    names = [r["code_name"] for r in rows]
    assert len(names) == len(set(names)), "Duplicate code_names in seed data"
