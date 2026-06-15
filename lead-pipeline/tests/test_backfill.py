"""Tests for M18 backfill functions."""

import pytest

from src.pipeline.backfill import _parse_json_response


class TestParseJsonResponse:
    def test_valid_json(self):
        result = _parse_json_response(
            '{"leistung_text": "test", "leistung_absatz_2": "Mixed"}'
        )
        assert result["leistung_text"] == "test"

    def test_markdown_fenced_json(self):
        text = '```json\n{"leistung_text": "test"}\n```'
        result = _parse_json_response(text)
        assert result["leistung_text"] == "test"

    def test_none_input(self):
        assert _parse_json_response(None) is None

    def test_empty_input(self):
        assert _parse_json_response("") is None

    def test_invalid_json(self):
        assert _parse_json_response("not json") is None

    def test_compliment_json(self):
        result = _parse_json_response('{"k1": "Ihre Erfahrung", "k2": "Ihr Service"}')
        assert result["k1"] == "Ihre Erfahrung"
        assert result["k2"] == "Ihr Service"
