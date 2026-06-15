"""Tests for check-letter grammar/consistency validation."""

import pytest

from src.pipeline.check_letter import (
    _check_consistency,
    _check_missing_fields,
    _parse_issues,
)


class TestCheckMissingFields:
    def test_all_filled(self):
        rec = {
            "full_name": "Test GmbH",
            "anrede": "Herr",
            "salutation": "Sehr geehrter Herr Test",
            "owner_name": "Klaus Test",
            "street": "Teststr. 1",
            "plz_ort": "12345 Berlin",
            "region_prep": "in Berlin",
            "leistung_text": "Medizintechnik",
            "compliment_draft": "Ihre Erfahrung",
            "compliment_2": "Ihr Service",
            "mehrwerte": "der Optimierung von Einkaufsprozessen",
            "gf_email": "test@test.de",
        }
        assert _check_missing_fields(rec) == []

    def test_missing_email_is_warning(self):
        rec = {
            "full_name": "Test GmbH",
            "anrede": "Herr",
            "salutation": "Sehr geehrter Herr Test",
            "owner_name": "Klaus Test",
            "street": "Teststr. 1",
            "plz_ort": "12345 Berlin",
            "region_prep": "in Berlin",
            "leistung_text": "Medizintechnik",
            "compliment_draft": "Ihre Erfahrung",
            "compliment_2": "Ihr Service",
            "mehrwerte": "der Optimierung von Einkaufsprozessen",
            "gf_email": None,
        }
        issues = _check_missing_fields(rec)
        assert len(issues) == 1
        assert issues[0]["field"] == "gf_email"
        assert issues[0]["severity"] == "warning"

    def test_empty_string_counts_as_missing(self):
        rec = {
            "full_name": "",
            "anrede": "",
            "salutation": "",
            "owner_name": "",
            "street": "",
            "plz_ort": "",
            "region_prep": "",
            "leistung_text": "",
            "compliment_draft": "",
            "compliment_2": "",
            "mehrwerte": "",
            "gf_email": "",
        }
        issues = _check_missing_fields(rec)
        assert len(issues) == 12


class TestCheckConsistency:
    def test_anrede_salutation_match(self):
        rec = {
            "anrede": "Herr",
            "salutation": "Sehr geehrter Herr Mueller",
            "owner_name": "Klaus Mueller",
            "full_name": "Test GmbH",
        }
        assert _check_consistency(rec) == []

    def test_anrede_salutation_mismatch(self):
        rec = {
            "anrede": "Herr",
            "salutation": "Sehr geehrte Frau Mueller",
            "owner_name": "Klaus Mueller",
            "full_name": "Test GmbH",
        }
        issues = _check_consistency(rec)
        assert any(
            i["field"] == "salutation" and i["severity"] == "error" for i in issues
        )

    def test_salutation_missing_lastname(self):
        rec = {
            "anrede": "Herr",
            "salutation": "Sehr geehrter Herr Schmidt",
            "owner_name": "Klaus Mueller",
            "full_name": "Test GmbH",
        }
        issues = _check_consistency(rec)
        assert any("Mueller" in i["issue"] for i in issues)

    def test_all_caps_name_warning(self):
        rec = {
            "anrede": "",
            "salutation": "",
            "owner_name": "",
            "full_name": "MUELLER MEDIZINTECHNIK GMBH",
        }
        issues = _check_consistency(rec)
        assert any(
            i["severity"] == "warning" and i["field"] == "full_name" for i in issues
        )

    def test_corporate_owner_name_error(self):
        rec = {
            "anrede": "",
            "salutation": "",
            "full_name": "Test",
            "owner_name": "Zuther & Hautmann Verwaltungsgesellschaft mbH",
        }
        issues = _check_consistency(rec)
        assert any(
            i["field"] == "owner_name" and "juristische Person" in i["issue"]
            for i in issues
        )

    def test_clean_record_no_issues(self):
        rec = {
            "anrede": "Frau",
            "salutation": "Sehr geehrte Frau Schmidt",
            "owner_name": "Anna Schmidt",
            "full_name": "Schmidt Medizintechnik GmbH",
        }
        assert _check_consistency(rec) == []


class TestParseIssues:
    def test_valid_array(self):
        text = '[{"field": "salutation", "issue": "test", "severity": "error"}]'
        result = _parse_issues(text)
        assert len(result) == 1

    def test_empty_array(self):
        assert _parse_issues("[]") == []

    def test_markdown_fenced(self):
        text = '```json\n[{"field": "x", "issue": "y", "severity": "warning"}]\n```'
        result = _parse_issues(text)
        assert len(result) == 1

    def test_none_input(self):
        assert _parse_issues(None) == []

    def test_invalid_json(self):
        assert _parse_issues("not json") == []
