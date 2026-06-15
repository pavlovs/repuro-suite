import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import init_db, _migrate_schema_v2
from src.ingest import classify_file, extract_year, scan_deal


# ── extract_year ──────────────────────────────────────────────────────────────


def test_year_from_plain_name():
    assert extract_year("JA 2022 Kontennachweis.xlsx") == 2022


def test_year_from_datev_style():
    assert extract_year("BWA 12.25.pdf") == 2025


def test_year_ambiguous_range():
    assert extract_year("hwv bilanz 3jU_2024-2026.pdf") is None


def test_year_none_when_absent():
    assert extract_year("Vertraulichkeitsvereinbarung.docx") is None


def test_year_single_in_complex_name():
    assert extract_year("1213976_1_2024_Kontennachweis zur G.u.V.[34].xlsx") == 2024


# ── classify_file ─────────────────────────────────────────────────────────────


@pytest.fixture
def deal_root(tmp_path):
    (tmp_path / "0_Verträge und Meetings" / "NDA").mkdir(parents=True)
    (tmp_path / "1_Unternehmensinformationen").mkdir()
    (tmp_path / "2_Model" / "_archive").mkdir(parents=True)
    (tmp_path / "3_Indikatives Angebot").mkdir()
    (tmp_path / "4_LOI" / "_old").mkdir(parents=True)
    (tmp_path / "5_DD").mkdir()
    (tmp_path / "7_Repuro documents").mkdir()
    return tmp_path


def _f(deal_root: Path, rel: str) -> Path:
    p = deal_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x")
    return p


def test_classify_nda_in_subfolder(deal_root):
    f = _f(deal_root, "0_Verträge und Meetings/NDA/250724_NDA.docx")
    assert classify_file(f, deal_root)[:2] == ("nda", None)


def test_classify_nda_by_name_in_meetings(deal_root):
    f = _f(
        deal_root, "0_Verträge und Meetings/250612_Vertraulichkeitsvereinbarung.docx"
    )
    assert classify_file(f, deal_root)[:2] == ("nda", None)


def test_classify_meeting(deal_root):
    f = _f(deal_root, "0_Verträge und Meetings/250814_Repuro_vP.pptx")
    assert classify_file(f, deal_root)[:2] == ("meeting", None)


def test_classify_guv(deal_root):
    f = _f(
        deal_root, "1_Unternehmensinformationen/JA 2022 Kontennachweis zur G.u.V..xlsx"
    )
    t, st, _ = classify_file(f, deal_root)
    assert t == "financials_raw" and st == "guv"


def test_classify_bilanz(deal_root):
    f = _f(
        deal_root, "1_Unternehmensinformationen/JA 2022 Kontennachweis zur Bilanz.xlsx"
    )
    t, st, _ = classify_file(f, deal_root)
    assert t == "financials_raw" and st == "bilanz"


def test_classify_bwa(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/BWA 12.25.pdf")
    t, st, _ = classify_file(f, deal_root)
    assert t == "financials_raw" and st == "bwa"


def test_classify_ja(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/JA 31.12.2023_HWV.pdf")
    t, st, _ = classify_file(f, deal_root)
    assert t == "financials_raw" and st == "ja"


def test_classify_model_active(deal_root):
    f = _f(deal_root, "2_Model/260119_Golmed_v8.xlsx")
    assert classify_file(f, deal_root)[:2] == ("model", None)


def test_classify_model_archive(deal_root):
    f = _f(deal_root, "2_Model/_archive/250629_HWV_v1.xlsx")
    assert classify_file(f, deal_root)[:2] == ("model", "archive")


def test_classify_offer(deal_root):
    f = _f(deal_root, "3_Indikatives Angebot/250908_Angebot_v1.docx")
    assert classify_file(f, deal_root)[:2] == ("offer", None)


def test_classify_loi(deal_root):
    f = _f(deal_root, "4_LOI/260210_LOI_v1.docx")
    assert classify_file(f, deal_root)[:2] == ("loi", None)


def test_classify_loi_old(deal_root):
    f = _f(deal_root, "4_LOI/_old/251202_LOI_v1.docx")
    assert classify_file(f, deal_root)[:2] == ("loi", "archive")


def test_classify_dd(deal_root):
    f = _f(deal_root, "5_DD/260108_Datenanfrage.xlsx")
    assert classify_file(f, deal_root)[:2] == ("dd", None)


def test_classify_repuro_internal(deal_root):
    f = _f(deal_root, "7_Repuro documents/260309_overview_vS.pdf")
    assert classify_file(f, deal_root)[:2] == ("repuro_internal", None)


def test_classify_rfi_in_financials(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/250807_HWV_RFI_vS.docx")
    assert classify_file(f, deal_root)[:2] == ("rfi", None)


def test_classify_rfi_at_root(deal_root):
    f = _f(deal_root, "250831_Golmed_RFI_vS.docx")
    assert classify_file(f, deal_root)[:2] == ("rfi", None)


def test_classify_year_extracted(deal_root):
    f = _f(deal_root, "1_Unternehmensinformationen/JA 2022 Kontennachweis.xlsx")
    _, _, year = classify_file(f, deal_root)
    assert year == 2022


# ── scan_deal ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mem_conn(tmp_path):
    import config.settings as s

    original_deals_dir = s.DEALS_DIR
    s.DEALS_DIR = tmp_path

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    _migrate_schema_v2(conn)

    yield conn, tmp_path

    conn.close()
    s.DEALS_DIR = original_deals_dir


def _insert_deal(conn, code: str, domain: str | None, folder: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO deals "
        "(id, code_name, company_name, domain, deal_stage, folder_path, added_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            code,
            f"Test {code}",
            domain,
            "valuation",
            folder,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def _build_fake_folder(base: Path, code: str) -> Path:
    folder = base / f"250101_TestCo ({code})"
    (folder / "1_Unternehmensinformationen").mkdir(parents=True)
    (folder / "2_Model").mkdir()
    (folder / "0_Verträge und Meetings" / "NDA").mkdir(parents=True)
    (folder / "1_Unternehmensinformationen" / "GuV_2023.xlsx").write_text("x")
    (folder / "1_Unternehmensinformationen" / "Bilanz_2023.xlsx").write_text("x")
    (folder / "2_Model" / "250101_v1.xlsx").write_text("x")
    (folder / "0_Verträge und Meetings" / "NDA" / "250101_NDA.docx").write_text("x")
    return folder


def test_scan_registers_files(mem_conn):
    conn, tmp_path = mem_conn
    _insert_deal(conn, "Alpha", "alpha.de", "250101_TestCo (Alpha)")
    _build_fake_folder(tmp_path, "Alpha")

    counts = scan_deal("Alpha", conn)

    assert counts["total"] == 4
    assert counts["new"] == 4
    assert counts["skipped"] == 0
    n = conn.execute(
        "SELECT COUNT(*) FROM deal_documents WHERE code_name='Alpha'"
    ).fetchone()[0]
    assert n == 4


def test_scan_idempotent(mem_conn):
    conn, tmp_path = mem_conn
    _insert_deal(conn, "Beta", "beta.de", "250101_TestCo (Beta)")
    folder = _build_fake_folder(tmp_path, "Beta")

    scan_deal("Beta", conn)
    counts2 = scan_deal("Beta", conn)

    assert counts2["new"] == 0
    assert counts2["skipped"] == 4
    n = conn.execute(
        "SELECT COUNT(*) FROM deal_documents WHERE code_name='Beta'"
    ).fetchone()[0]
    assert n == 4


def test_scan_null_domain_uses_codename(mem_conn):
    conn, tmp_path = mem_conn
    _insert_deal(conn, "Gamma", None, "250101_TestCo (Gamma)")
    _build_fake_folder(tmp_path, "Gamma")

    scan_deal("Gamma", conn)

    row = conn.execute(
        "SELECT domain FROM deal_documents WHERE code_name='Gamma' LIMIT 1"
    ).fetchone()
    assert row["domain"] == "gamma"


def test_scan_skips_temp_files(mem_conn):
    conn, tmp_path = mem_conn
    _insert_deal(conn, "Delta", "delta.de", "250101_TestCo (Delta)")
    folder = tmp_path / "250101_TestCo (Delta)"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "~$locked.xlsx").write_text("x")  # OneDrive lock file
    (folder / "real.xlsx").write_text("x")

    counts = scan_deal("Delta", conn)
    assert counts["total"] == 1  # lock file skipped


def test_scan_unknown_deal_raises(mem_conn):
    conn, _ = mem_conn
    with pytest.raises(ValueError, match="Deal not found"):
        scan_deal("NoSuchDeal", conn)
