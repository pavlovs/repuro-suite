"""Tests for pure-logic functions in src/pipeline/export.py (M19)."""

from __future__ import annotations

import pytest

from src.pipeline.export import _parse_compliment_json, _parse_name, _record_to_row
from src.pipeline.models import CompanyRecord


# ---------------------------------------------------------------------------
# _parse_name
# ---------------------------------------------------------------------------


class TestParseName:
    def test_two_part_name(self):
        assert _parse_name("Klaus Müller") == ("Klaus", "Müller")

    def test_three_part_name_first_only_split(self):
        first, last = _parse_name("Klaus Peter Müller")
        assert first == "Klaus"
        assert last == "Peter Müller"

    def test_single_name_no_first(self):
        assert _parse_name("Müller") == ("", "Müller")

    def test_empty_string(self):
        assert _parse_name("") == ("", "")

    def test_none(self):
        assert _parse_name(None) == ("", "")

    def test_strips_whitespace(self):
        first, last = _parse_name("  Klaus   Müller  ")
        assert first == "Klaus"
        assert last == "Müller"


# ---------------------------------------------------------------------------
# _parse_compliment_json
# ---------------------------------------------------------------------------


class TestParseComplimentJson:
    def test_valid_json(self):
        k1, k2 = _parse_compliment_json('{"k1": "K1 text", "k2": "K2 text"}')
        assert k1 == "K1 text"
        assert k2 == "K2 text"

    def test_markdown_fences_stripped(self):
        text = '```json\n{"k1": "val1", "k2": "val2"}\n```'
        k1, k2 = _parse_compliment_json(text)
        assert k1 == "val1"
        assert k2 == "val2"

    def test_empty_string(self):
        assert _parse_compliment_json("") == (None, None)

    def test_invalid_json(self):
        assert _parse_compliment_json("not json at all") == (None, None)

    def test_empty_values_become_none(self):
        k1, k2 = _parse_compliment_json('{"k1": "", "k2": "val"}')
        assert k1 is None
        assert k2 == "val"


# ---------------------------------------------------------------------------
# _record_to_row
# ---------------------------------------------------------------------------


def _make_record(**kwargs) -> CompanyRecord:
    defaults = dict(
        domain="test.de",
        full_name="Test GmbH",
        profile_id="p",
        source="ORBIS",
        klass="A",
        owner_name="Klaus Müller",
        anrede="Herr",
        salutation="Sehr geehrter Herr Müller",
        street="Hauptstr. 1",
        plz_ort="12345 Berlin",
        region="Berlin",
        region_prep="in Berlin",
        leistung_text="Medizintechnik-Dienstleistern",
        leistung_absatz_2="Medizintechnik-Dienstleistern",
        mehrwerte="der Optimierung von Prozessen",
        compliment_draft="K1 text",
        compliment_2="K2 text hat",
        gf_email="k.mueller@test.de",
    )
    defaults.update(kwargs)
    return CompanyRecord(**defaults)


class TestRecordToRow:
    def test_a_record_all_columns_present(self):
        rec = _make_record()
        row = _record_to_row(rec, {"source": "ORBIS"})
        assert row["Domain Name Clean"] == "test.de"
        assert row["Category"] == "A"
        assert row["Anrede"] == "Herr"
        assert row["Salutation"] == "Sehr geehrter Herr Müller"
        assert row["Leistung Absatz 1"] == "Medizintechnik-Dienstleistern"
        assert row["Email"] == "k.mueller@test.de"

    def test_a_record_priority_prio_1(self):
        row = _record_to_row(_make_record(klass="A"), {})
        assert row["Priority"] == "Prio 1"

    def test_b_record_priority_prio_1(self):
        row = _record_to_row(_make_record(klass="B"), {})
        assert row["Priority"] == "Prio 1"

    def test_c_record_empty_priority(self):
        row = _record_to_row(_make_record(klass="C"), {})
        assert row["Priority"] == ""

    def test_no_none_literals(self):
        rec = _make_record(street=None, region=None, mehrwerte=None)
        row = _record_to_row(rec, {})
        for val in row.values():
            assert val != "None", f"Found 'None' literal in row"

    def test_region_prep_preferred_over_region(self):
        rec = _make_record(region="Bayern", region_prep="in Bayern")
        row = _record_to_row(rec, {})
        assert row["Region"] == "in Bayern"

    def test_outreach_fields_from_raw(self):
        rec = _make_record()
        raw = {
            "outreach_sent_at": "2026-01-01",
            "outreach_status": "sent",
            "outreach_comment": "done",
            "followup1_at": "2026-01-15",
            "followup2_at": None,
            "followup_comment": None,
        }
        row = _record_to_row(rec, raw)
        assert row["Datum Sent"] == "2026-01-01"
        assert row["Status"] == "sent"
        assert row["Comment"] == "done"

    def test_owner_name_splits_into_first_last(self):
        rec = _make_record(owner_name="Jana Rennecke")
        row = _record_to_row(rec, {})
        assert row["First Name (1)"] == "Jana"
        assert row["Last Name (1)"] == "Rennecke"

    def test_impressum_name_preferred_over_full_name(self):
        rec = _make_record()
        raw = {"impressum_name": "Test GmbH & Co. KG Impressum"}
        row = _record_to_row(rec, raw)
        assert row["Name Briefkopf"] == "Test GmbH & Co. KG Impressum"

    def test_full_name_fallback_when_no_impressum(self):
        rec = _make_record()
        row = _record_to_row(rec, {})
        assert row["Name Briefkopf"] == "Test GmbH"
