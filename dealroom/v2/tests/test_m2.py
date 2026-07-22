"""M2 tests: naming/classification, Fragenliste parsing (real files, read-only),
RFI candidate preference."""

import sys
from pathlib import Path

import pytest

DEALROOM = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(DEALROOM))

from v2 import naming  # noqa: E402
from v2.scanner import DEFAULT_TARGETS_ROOT, find_rfi_file, parse_fragenliste  # noqa: E402

FOX = DEFAULT_TARGETS_ROOT / "250702_Com2Med (Fox)"


def test_parse_version():
    assert naming.parse_version("260702_Fox_CDD_Databook_FC_v5.xlsx") == 5
    assert naming.parse_version("260708_Fragenliste_vS.xlsx") is None
    assert naming.parse_version("no_version.pdf") is None


def test_parse_file_date():
    assert naming.parse_file_date("260710_Mantis_CDD_v9.pptx") == "2026-07-10"
    assert naming.parse_file_date("991301_bad_month.xlsx") is None
    assert naming.parse_file_date("Fragenliste.xlsx") is None


def test_classify_by_name():
    assert naming.classify("260622_Fox_CDD_Databook_FC_v1.xlsx") == "databook"
    assert naming.classify("260708_Repuro_C2M_Fragenliste_vS.xlsx") == "rfi"
    assert naming.classify("260601_Repuro_C2M_DD Datenanfrage_vS.xlsx") == "rfi"
    assert naming.classify("260710_Mantis_CDD_v9.pptx") == "slides"
    assert naming.classify("260703_Kaufabsichtserklärung M&S_v7.docx") == "loi"
    assert naming.classify("260708_Golmed_Angebots-Update_v1.docx") == "nbo"
    # CDD marker on an xlsx must NOT become slides (databook wins by order)
    assert naming.classify("260710_Mantis_CDD_Databook_v8.xlsx") == "databook"


def test_classify_by_folder_fallback():
    assert naming.classify("irgendwas.pdf", "4_LOI/irgendwas.pdf") == "loi"
    assert naming.classify("plain.xlsx", "2_Model/plain.xlsx") == "model"
    assert naming.classify("x.pdf", "5_DD/x.pdf") == "dataroom_file"


def test_skip_markers():
    assert naming.skip_file("260617_Datei.xlsx.bak_260624")
    assert naming.skip_file("~$tempfile.xlsx")
    assert not naming.skip_file("260617_Datei.xlsx")


@pytest.mark.skipif(not FOX.exists(), reason="Fox deal folder not available")
def test_find_rfi_prefers_vs():
    picked = find_rfi_file(FOX)
    assert picked is not None
    assert picked.name == "260708_Repuro_C2M_Fragenliste_vS.xlsx"


@pytest.mark.skipif(not FOX.exists(), reason="Fox deal folder not available")
def test_parse_fragenliste_fox_real():
    qs = parse_fragenliste(FOX / "5_DD" / "260708_Repuro_C2M_Fragenliste_vS.xlsx")
    assert len(qs) >= 25
    assert all(q["question"] for q in qs)
    assert any(q["importance"] == "high" for q in qs)
    assert all(q["sent_at"] == "2026-07-08" for q in qs)
    # category comes from the Thema column, not the generic default
    assert any("Geschäftsfelder" in q["category"] for q in qs)
