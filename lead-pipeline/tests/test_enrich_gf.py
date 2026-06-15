"""Tests for _extract_gf_from_impressum (M21)."""

from __future__ import annotations

import pytest

from src.pipeline.enrich import _extract_gf_from_impressum


class TestExtractGfFromImpressum:
    def test_geschaeftsfuehrer_pattern(self):
        text = "Muster GmbH Geschäftsführer: Klaus Müller USt-IdNr. DE123"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Klaus Müller"

    def test_vertreten_durch_pattern(self):
        text = "vertreten durch den Geschäftsführer Jana Rennecke, Straße 1"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Jana Rennecke"

    def test_inhaber_pattern(self):
        text = "Inhaber: Thomas Weber Kontakt E-Mail"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Thomas Weber"

    def test_dr_prefix_stripped_from_match(self):
        text = "Geschäftsführer: Dr. Peter Schäfer HRB 12345"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Peter Schäfer"

    def test_trailing_non_name_words_stripped(self):
        text = "Geschäftsführer: Martin Helbig Kontakt Telefon"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Martin Helbig"

    def test_trailing_umsatzsteuer_stripped(self):
        text = "Geschäftsführer: Holger König Umsatzsteuer-ID DE987"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Holger König"

    def test_trailing_handelsregister_stripped(self):
        text = "Geschäftsführer: Timo Bender Handelsregister HRB 1234"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Timo Bender"

    def test_three_word_name_accepted(self):
        text = "Geschäftsführer: Lukas Peter Distler"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Lukas Peter Distler"

    def test_single_word_name_rejected(self):
        text = "Geschäftsführer: Müller"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] is None

    def test_empty_text(self):
        result = _extract_gf_from_impressum("")
        assert result["gf_name"] is None
        assert result["impressum_address"] is None
        assert result["personal_email"] is None

    def test_no_gf_pattern_returns_none(self):
        text = "Keine Angabe zum Geschäftsführer hier."
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] is None

    def test_name_with_digits_rejected(self):
        text = "Geschäftsführer: Max1 Mustermann"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] is None

    def test_personal_email_extracted(self):
        text = "Kontakt: m.mueller@firma.de\nGeschäftsführer: Max Müller"
        result = _extract_gf_from_impressum(text)
        assert result["personal_email"] == "m.mueller@firma.de"

    def test_generic_email_discarded(self):
        text = "Kontakt: info@firma.de\nGeschäftsführer: Max Müller"
        result = _extract_gf_from_impressum(text)
        assert result["personal_email"] is None

    def test_address_extracted(self):
        text = "Muster GmbH\nHauptstraße 12,\n12345 Berlin\nGeschäftsführer: Max Müller"
        result = _extract_gf_from_impressum(text)
        assert result["impressum_address"] is not None
        assert "12345" in result["impressum_address"]

    def test_trailing_hyphen_stripped(self):
        # "Flegel-" with trailing hyphen stripped → "Flegel", giving "Nadine Flegel" (valid 2-word name)
        text = "Geschäftsführer: Nadine Flegel-"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Nadine Flegel"

    def test_vertreten_durch_without_gf_keyword(self):
        text = "vertreten durch Max Mustermann"
        result = _extract_gf_from_impressum(text)
        assert result["gf_name"] == "Max Mustermann"
