"""Tests for pure-logic functions in src/pipeline/enrich.py (M19)."""

from __future__ import annotations

from unittest.mock import patch


from src.pipeline.enrich import (
    _build_owner_email_candidates,
    _derive_anrede,
    _is_natural_person_name,
    _is_on_blocklist,
    _normalise_name_for_email,
    _parse_owners,
)


# ---------------------------------------------------------------------------
# _is_natural_person_name
# ---------------------------------------------------------------------------


class TestIsNaturalPersonName:
    def test_natural_person(self):
        assert _is_natural_person_name("Klaus Müller") is True

    def test_corporate_entity_gmbh(self):
        assert _is_natural_person_name("Müller Medizintechnik GmbH") is False

    def test_corporate_entity_ag(self):
        assert _is_natural_person_name("Deutsche Holding AG") is False

    def test_seidel_no_false_positive(self):
        # "se" is in "Seidel" but must NOT match word boundary check
        assert _is_natural_person_name("Seidel") is True

    def test_hagemann_no_false_positive(self):
        # "ag" is in "Hagemann" but must NOT match word boundary check
        assert _is_natural_person_name("Hagemann") is True

    def test_empty_string(self):
        assert _is_natural_person_name("") is False

    def test_none(self):
        assert _is_natural_person_name(None) is False

    def test_holding_in_name(self):
        assert _is_natural_person_name("Familie Holding GmbH") is False


# ---------------------------------------------------------------------------
# _is_on_blocklist
# ---------------------------------------------------------------------------


class TestIsOnBlocklist:
    def _bl(self) -> list[dict]:
        return [
            {"name": "Fresenius", "type": "corporate_parent"},
            {"name": "Blackstone", "type": "pe_fund"},
        ]

    def test_exact_match(self):
        result = _is_on_blocklist("Fresenius SE & Co. KGaA", self._bl())
        assert result is not None
        assert result["type"] == "corporate_parent"

    def test_substring_match(self):
        result = _is_on_blocklist("Fresenius Medical Care GmbH", self._bl())
        assert result is not None

    def test_case_insensitive(self):
        result = _is_on_blocklist("BLACKSTONE Capital Partners", self._bl())
        assert result is not None
        assert result["type"] == "pe_fund"

    def test_no_match(self):
        assert _is_on_blocklist("Unknown Entity GmbH", self._bl()) is None

    def test_empty_blocklist(self):
        assert _is_on_blocklist("Fresenius", []) is None


# ---------------------------------------------------------------------------
# _parse_owners
# ---------------------------------------------------------------------------


def _natural_person(name: str, pct: float, dob: str = "") -> dict:
    return {
        "type": "natural_person",
        "name": name,
        "percentage_share": pct,
        "natural_person": {"date_of_birth": dob, "first_name": "", "last_name": ""},
        "legal_person": {},
    }


def _legal_person(name: str, pct: float) -> dict:
    return {
        "type": "legal_person",
        "name": name,
        "percentage_share": pct,
        "natural_person": {},
        "legal_person": {"name": name},
    }


class TestParseOwners:
    def test_natural_person_majority_owner(self):
        owners = [_natural_person("Klaus Müller", 100.0)]
        result = _parse_owners(owners, [])
        assert result["is_subsidiary"] is False
        assert result["is_pe_backed"] is False
        assert result["needs_review"] is False
        assert result["gesellschafter_name"] == "Klaus Müller"

    def test_natural_person_with_birth_year(self):
        owners = [_natural_person("Jana Rennecke", 100.0, "1975-03-12")]
        result = _parse_owners(owners, [])
        assert result["gesellschafter_age"] == 1975

    def test_legal_person_on_blocklist_corporate(self):
        blocklist = [{"name": "Fresenius", "type": "corporate_parent"}]
        owners = [_legal_person("Fresenius SE", 100.0)]
        result = _parse_owners(owners, blocklist)
        assert result["is_subsidiary"] is True
        assert result["is_pe_backed"] is False
        assert result["needs_review"] is False

    def test_legal_person_on_blocklist_pe_fund(self):
        blocklist = [{"name": "Blackstone", "type": "pe_fund"}]
        owners = [_legal_person("Blackstone Capital Partners", 75.0)]
        result = _parse_owners(owners, blocklist)
        assert result["is_pe_backed"] is True
        assert result["is_subsidiary"] is True

    def test_legal_person_not_on_blocklist(self):
        owners = [_legal_person("Unknown Holding GmbH", 100.0)]
        result = _parse_owners(owners, [])
        assert result["needs_review"] is True
        assert result["is_subsidiary"] is None

    def test_empty_owners_needs_review(self):
        result = _parse_owners([], [])
        assert result["needs_review"] is True
        assert result["review_reason"] == "OpenRegister returned empty owners list"

    def test_50_50_natural_person_preferred(self):
        owners = [
            _natural_person("Klaus Müller", 50.0),
            _legal_person("Holding GmbH", 50.0),
        ]
        result = _parse_owners(owners, [])
        # Natural person preferred in ties (higher secondary sort key)
        assert result["gesellschafter_name"] == "Klaus Müller"
        assert result["is_subsidiary"] is False

    def test_unknown_type_needs_review(self):
        owners = [
            {
                "type": "unknown_type",
                "name": "Entity",
                "percentage_share": 100.0,
                "natural_person": {},
                "legal_person": {},
            }
        ]
        result = _parse_owners(owners, [])
        assert result["needs_review"] is True

    # Bug fix: all_gesellschafter must capture every owner, not just the majority
    def test_all_gesellschafter_single_owner(self):
        """Single-owner case: all_gesellschafter is a JSON list with 1 entry."""
        import json

        owners = [_natural_person("Klaus Müller", 100.0)]
        result = _parse_owners(owners, [])
        assert "all_gesellschafter" in result
        parsed = json.loads(result["all_gesellschafter"])
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Klaus Müller"
        assert parsed[0]["pct"] == 100.0

    def test_all_gesellschafter_multi_owner_all_captured(self):
        """Multi-owner case: both owners stored, not just the majority."""
        import json

        owners = [
            _natural_person("Klaus Müller", 50.0),
            _legal_person("Holding GmbH", 50.0),
        ]
        result = _parse_owners(owners, [])
        assert "all_gesellschafter" in result
        parsed = json.loads(result["all_gesellschafter"])
        assert len(parsed) == 2
        names = {e["name"] for e in parsed}
        assert "Klaus Müller" in names
        assert "Holding GmbH" in names

    def test_all_gesellschafter_empty_owners(self):
        """Empty owners list: all_gesellschafter is an empty JSON array."""
        import json

        result = _parse_owners([], [])
        assert "all_gesellschafter" in result
        assert json.loads(result["all_gesellschafter"]) == []

    def test_all_gesellschafter_sorted_by_pct_desc(self):
        """Owners in all_gesellschafter sorted highest % first."""
        import json

        owners = [
            _natural_person("Minority Person", 25.0),
            _natural_person("Majority Person", 75.0),
        ]
        result = _parse_owners(owners, [])
        parsed = json.loads(result["all_gesellschafter"])
        assert parsed[0]["name"] == "Majority Person"
        assert parsed[1]["name"] == "Minority Person"


# ---------------------------------------------------------------------------
# _derive_anrede
# ---------------------------------------------------------------------------


class TestDeriveAnrede:
    def test_known_male_name(self):
        assert _derive_anrede("Klaus") == "Herr"

    def test_known_female_name(self):
        assert _derive_anrede("Sabine") == "Frau"

    def test_feminine_ending_a(self):
        assert _derive_anrede("Andrea") == "Frau"

    def test_feminine_ending_e(self):
        assert _derive_anrede("Renate") == "Frau"

    def test_empty_string(self):
        assert _derive_anrede("") is None

    def test_unknown_name_no_vowel_ending(self):
        # "Xylophon" ends in 'n' — not in any list, not feminine ending
        result = _derive_anrede("Xylophon")
        assert result is None


# ---------------------------------------------------------------------------
# _normalise_name_for_email
# ---------------------------------------------------------------------------


class TestNormaliseNameForEmail:
    def test_umlaut_ae(self):
        assert _normalise_name_for_email("Müller") == "mueller"

    def test_umlaut_oe(self):
        assert _normalise_name_for_email("Größe") == "groesse"

    def test_umlaut_ss(self):
        assert _normalise_name_for_email("Straße") == "strasse"

    def test_lowercase(self):
        assert _normalise_name_for_email("Klaus") == "klaus"

    def test_strips_non_ascii_after_umlaut_replacement(self):
        result = _normalise_name_for_email("Ŕęné")
        # After umlaut replacement, remaining non-ascii stripped
        assert result.isascii()

    def test_preserves_hyphens(self):
        assert _normalise_name_for_email("Meyer-Schmidt") == "meyer-schmidt"


# ---------------------------------------------------------------------------
# _build_owner_email_candidates
# ---------------------------------------------------------------------------


class TestBuildOwnerEmailCandidates:
    def _candidates(self, name: str, domain: str) -> list[str]:
        with patch("src.pipeline.enrich._scrape_email_pattern", return_value=None):
            return _build_owner_email_candidates(name, domain)

    def test_two_part_name_8_candidates(self):
        result = self._candidates("Jana Rennecke", "example.de")
        assert len(result) == 8

    def test_correct_patterns_order(self):
        result = self._candidates("Jana Rennecke", "example.de")
        assert result[0] == "jana.rennecke@example.de"
        assert result[1] == "j.rennecke@example.de"
        assert result[2] == "rennecke@example.de"
        assert result[3] == "jana@example.de"

    def test_three_part_name_uses_first_and_last(self):
        result = self._candidates("Uwe Dirk Joneck", "test.de")
        assert "uwe.joneck@test.de" in result
        assert "joneck@test.de" in result

    def test_single_word_returns_empty(self):
        result = self._candidates("Müller", "example.de")
        assert result == []

    def test_umlaut_normalised_in_email(self):
        result = self._candidates("Klaus Müller", "firma.de")
        assert "klaus.mueller@firma.de" in result

    def test_domain_appended_to_all(self):
        result = self._candidates("Jana Rennecke", "mycompany.de")
        assert all(e.endswith("@mycompany.de") for e in result)
