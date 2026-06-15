"""Tests for pure-logic functions in src/pipeline/export_pdf.py (M22)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from src.pipeline.export_pdf import (
    REQUIRED_LETTER_FIELDS,
    LetterBlock,
    _build_record_data,
    _count_wrapped_lines,
    _fill_merge_fields,
    _parse_name,
    check_overflow,
    check_record_completeness,
    estimate_letter_height,
    load_sender_config,
    parse_letter_template,
)


# ---------------------------------------------------------------------------
# _parse_name
# ---------------------------------------------------------------------------


class TestParseName:
    def test_two_part(self):
        assert _parse_name("Klaus Müller") == ("Klaus", "Müller")

    def test_single(self):
        assert _parse_name("Müller") == ("", "Müller")

    def test_none(self):
        assert _parse_name(None) == ("", "")

    def test_empty(self):
        assert _parse_name("") == ("", "")

    def test_three_parts(self):
        assert _parse_name("Karl Peter Schmidt") == ("Karl", "Peter Schmidt")


# ---------------------------------------------------------------------------
# _fill_merge_fields
# ---------------------------------------------------------------------------


class TestFillMergeFields:
    def test_all_fields_replaced(self):
        text = "Hallo {{vorname}} {{nachname}}"
        data = {"vorname": "Klaus", "nachname": "Müller"}
        assert _fill_merge_fields(text, data) == "Hallo Klaus Müller"

    def test_missing_field_bracketed(self):
        text = "{{company}} in {{city}}"
        data = {"company": "Repuro"}
        assert _fill_merge_fields(text, data) == "Repuro in [city]"

    def test_no_fields(self):
        assert _fill_merge_fields("plain text", {}) == "plain text"

    def test_empty_value_shows_bracket(self):
        text = "{{name}}"
        data = {"name": ""}
        assert _fill_merge_fields(text, data) == "[name]"


# ---------------------------------------------------------------------------
# _build_record_data
# ---------------------------------------------------------------------------


class TestBuildRecordData:
    def test_basic_mapping(self):
        raw = {
            "impressum_name": "Test GmbH",
            "full_name": "Test",
            "owner_name": "Hans Meier",
            "street": "Musterstr. 1",
            "plz_ort": "10115 Berlin",
            "anrede": "Herr",
            "salutation": "Sehr geehrter Herr Meier",
            "leistung_text": "Medizintechnik-Dienstleistern",
            "region_prep": "in Berlin",
            "compliment_draft": "K1 text",
            "compliment_2": "K2 text",
            "leistung_absatz_2": "Medizintechnik-Dienstleistern",
            "mehrwerte": "bullet points",
        }
        sender = {"city": "München"}
        result = _build_record_data(raw, sender)

        assert result["name_briefkopf"] == "Test GmbH"
        assert result["vorname"] == "Hans"
        assert result["nachname"] == "Meier"
        assert result["street"] == "Musterstr. 1"
        assert "München" in result["datum"]
        assert result["salutation"] == "Sehr geehrter Herr Meier"

    def test_fallback_to_full_name(self):
        raw = {"full_name": "Fallback GmbH"}
        result = _build_record_data(raw, {"city": "Berlin"})
        assert result["name_briefkopf"] == "Fallback GmbH"

    def test_missing_fields_empty_string(self):
        result = _build_record_data({}, {"city": "Berlin"})
        assert result["street"] == ""
        assert result["anrede"] == ""


# ---------------------------------------------------------------------------
# load_sender_config
# ---------------------------------------------------------------------------


class TestLoadSenderConfig:
    def test_loads_real_sender_json(self):
        """Reads the actual sender.json from config dir."""
        cfg = load_sender_config()
        assert cfg["company_name"] == "Repuro GmbH"
        assert len(cfg["signatures"]) == 2
        assert cfg["city"] == "Berlin"

    def test_fallback_when_missing(self, tmp_path):
        """Returns defaults when config path doesn't exist."""
        with patch("src.pipeline.export_pdf.settings") as mock_settings:
            mock_settings.SENDER_CONFIG_PATH = tmp_path / "nonexistent.json"
            mock_settings.BASE_DIR = tmp_path
            cfg = load_sender_config()
        assert cfg["company_name"] == "Repuro GmbH"
        assert "address_lines" in cfg


# ---------------------------------------------------------------------------
# parse_letter_template
# ---------------------------------------------------------------------------


class TestParseLetterTemplate:
    def test_parses_blocks(self, tmp_path):
        html = textwrap.dedent("""\
            <div style="text-align: right;">{{datum}}</div>
            <div>{{street}}\n{{plz_ort}}</div>
            <div style="font-weight: 700;">Betreff</div>
            <div>Paragraph text here.</div>
            <div style="display: flex;">Sig1 Sig2</div>
        """)
        p = tmp_path / "template.html"
        p.write_text(html, encoding="utf-8")

        blocks = parse_letter_template(p)
        types = [b.block_type for b in blocks]

        assert "date" in types
        assert "address" in types
        assert "subject" in types
        assert "paragraph" in types
        assert "signatures" in types

    def test_empty_divs_skipped(self, tmp_path):
        html = '<div style="margin:10px;"></div><div>Content</div>'
        p = tmp_path / "template.html"
        p.write_text(html, encoding="utf-8")
        blocks = parse_letter_template(p)
        assert len(blocks) == 1


# ---------------------------------------------------------------------------
# estimate_letter_height / _count_wrapped_lines
# ---------------------------------------------------------------------------


class TestHeightEstimation:
    @pytest.fixture
    def pdf_instance(self):
        """Create a minimal RepuroLetterPDF for font metric tests."""
        from src.pipeline.export_pdf import RepuroLetterPDF

        sender = load_sender_config()
        pdf = RepuroLetterPDF(sender)
        pdf.add_page()
        return pdf

    def test_count_wrapped_lines_short(self, pdf_instance):
        pdf_instance.set_font("Arial", "", 11)
        lines = _count_wrapped_lines(pdf_instance, "Hello world", 160)
        assert lines == 1

    def test_count_wrapped_lines_long(self, pdf_instance):
        pdf_instance.set_font("Arial", "", 11)
        long_text = "Wort " * 100
        lines = _count_wrapped_lines(pdf_instance, long_text, 160)
        assert lines > 5

    def test_estimate_returns_positive(self, pdf_instance):
        blocks = [
            LetterBlock("date", "Berlin, 31.03.2026"),
            LetterBlock("address", "Test GmbH\nMusterstr. 1\n10115 Berlin"),
            LetterBlock("subject", "Betreff"),
            LetterBlock("paragraph", "Short paragraph."),
            LetterBlock("signatures", "Sig1 Sig2"),
        ]
        data = {"datum": "Berlin, 31.03.2026"}
        h = estimate_letter_height(pdf_instance, blocks, data)
        assert h > 0
        assert h < 300  # should fit on one page

    def test_overflow_detected(self, pdf_instance):
        """A letter with extremely long text should exceed MAX_CONTENT_H."""
        blocks = [
            LetterBlock("paragraph", "Wort " * 500),
            LetterBlock("paragraph", "Wort " * 500),
        ]
        h = estimate_letter_height(pdf_instance, blocks, {})
        assert h > 261  # MAX_CONTENT_H


# ---------------------------------------------------------------------------
# check_overflow
# ---------------------------------------------------------------------------


class TestCheckOverflow:
    def test_no_overflow_on_normal_data(self):
        sender = load_sender_config()
        raw_rows = {
            "example.de": {
                "impressum_name": "Example GmbH",
                "owner_name": "Hans Test",
                "street": "Teststr. 1",
                "plz_ort": "10115 Berlin",
                "anrede": "Herr",
                "salutation": "Sehr geehrter Herr Test",
                "leistung_text": "Medizintechnik-Dienstleistern",
                "region_prep": "in Berlin",
                "compliment_draft": "Ein Kompliment.",
                "compliment_2": "Noch ein Kompliment.",
                "leistung_absatz_2": "Medizintechnik-Dienstleistern",
                "mehrwerte": "Bullet points.",
            }
        }
        blocks = [
            LetterBlock("date", "{{datum}}"),
            LetterBlock("address", "{{name_briefkopf}}\n{{street}}\n{{plz_ort}}"),
            LetterBlock("subject", "Betreff"),
            LetterBlock("paragraph", "Short text."),
            LetterBlock("signatures", "Sig"),
        ]
        overflow = check_overflow(raw_rows, blocks, sender)
        assert overflow == []

    def test_overflow_flagged(self):
        sender = load_sender_config()
        raw_rows = {
            "overflow.de": {
                "compliment_draft": "Wort " * 500,
                "compliment_2": "Wort " * 500,
            }
        }
        blocks = [
            LetterBlock("paragraph", "{{compliment_draft}}"),
            LetterBlock("paragraph", "{{compliment_2}}"),
        ]
        overflow = check_overflow(raw_rows, blocks, sender)
        assert "overflow.de" in overflow


# ---------------------------------------------------------------------------
# check_record_completeness (M23)
# ---------------------------------------------------------------------------


class TestCheckRecordCompleteness:
    def _full_record(self) -> dict:
        return {
            "name_briefkopf": "Test GmbH",
            "anrede": "Herr",
            "salutation": "Sehr geehrter Herr Test",
            "street": "Teststr. 1",
            "plz_ort": "12345 Berlin",
            "leistung_text": "Medizintechnik-Experten",
            "region_prep": "in Berlin",
            "compliment_draft": "die langjährige Erfahrung",
            "compliment_2": "hat uns der Service überzeugt",
            "mehrwerte": "der Optimierung von Einkaufsprozessen",
        }

    def test_all_filled_returns_empty(self):
        assert check_record_completeness(self._full_record()) == []

    def test_missing_fields_returned(self):
        rec = self._full_record()
        del rec["street"]
        del rec["compliment_2"]
        missing = check_record_completeness(rec)
        assert "street" in missing
        assert "compliment_2" in missing
        assert len(missing) == 2

    def test_placeholder_counts_as_missing(self):
        rec = self._full_record()
        rec["anrede"] = "[anrede]"
        missing = check_record_completeness(rec)
        assert "anrede" in missing

    def test_empty_string_counts_as_missing(self):
        rec = self._full_record()
        rec["mehrwerte"] = ""
        missing = check_record_completeness(rec)
        assert "mehrwerte" in missing
