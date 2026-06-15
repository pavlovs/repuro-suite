"""Tests for pure-logic functions in src/pipeline/classify.py (M19)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.pipeline.classify import (
    _build_prompt,
    _format_example,
    _is_obvious_d,
    _normalize_company_name,
    _parse_result,
    _select_examples,
)
from src.config import settings
from src.config.profile import (
    ClassificationConfig,
    ClassificationExample,
    DiscoveryConfig,
    ExportConfig,
    FilterConfig,
    IndustryProfile,
    OwnershipConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    class_defs: dict[str, str] | None = None,
    examples: list[ClassificationExample] | None = None,
) -> IndustryProfile:
    return IndustryProfile(
        id="test",
        name="Test",
        description="desc",
        geography={"country": "DE"},
        discovery=DiscoveryConfig(wlw_search_terms=[]),
        filters=FilterConfig(),
        classification=ClassificationConfig(
            target_description="medtech",
            class_definitions=class_defs
            or {"A": "platform", "B": "addon", "D": "nope"},
            examples=examples or [],
        ),
        ownership=OwnershipConfig(),
        export=ExportConfig(),
    )


def _make_example(klass: str = "A") -> ClassificationExample:
    return ClassificationExample(
        domain="test.de",
        full_name="Test GmbH",
        klass=klass,
        services_score=80,
        service_flag=True,
        distributor_flag=False,
        ssb_flag=False,
        leistung_text="Medizintechnik-Dienstleistern",
        reasoning="Good fit",
        scraped_text_excerpt="medtech service",
    )


# ---------------------------------------------------------------------------
# _is_obvious_d
# ---------------------------------------------------------------------------


class TestIsObviousD:
    def test_handwerk_keyword_in_text(self):
        result, code = _is_obvious_d("maler und lackierer", "")
        assert result is True
        assert code == "Handwerk"

    def test_handwerk_keyword_dachdecker(self):
        result, code = _is_obvious_d("dachdecker in berlin", "")
        assert result is True
        assert code == "Handwerk"

    def test_non_handwerk_keyword_solar(self):
        result, code = _is_obvious_d("solar energy systems", "")
        assert result is True
        assert code == "Unpassende_Branche"

    def test_non_handwerk_keyword_möbel(self):
        result, code = _is_obvious_d("möbel und einrichtung", "")
        assert result is True
        assert code == "Unpassende_Branche"

    def test_keyword_in_full_name(self):
        result, code = _is_obvious_d("", "Solar GmbH & Co. KG")
        assert result is True
        assert code == "Unpassende_Branche"

    def test_no_match(self):
        result, code = _is_obvious_d("medizintechnik service", "Müller GmbH")
        assert result is False
        assert code == ""

    def test_case_insensitive(self):
        result, code = _is_obvious_d("SOLAR panels", "")
        assert result is True

    def test_empty_strings(self):
        result, code = _is_obvious_d("", "")
        assert result is False
        assert code == ""


# ---------------------------------------------------------------------------
# _normalize_company_name
# ---------------------------------------------------------------------------


class TestNormalizeCompanyName:
    def test_strips_gmbh(self):
        assert _normalize_company_name("Müller GmbH") == "müller"

    def test_strips_gmbh_co_kg(self):
        assert _normalize_company_name("Krolicki GmbH & Co. KG") == "krolicki"

    def test_strips_ag(self):
        result = _normalize_company_name("Fresenius AG")
        assert "ag" not in result
        assert "fresenius" in result

    def test_strips_ltd(self):
        result = _normalize_company_name("Acme Ltd")
        assert "ltd" not in result

    def test_preserves_umlauts(self):
        result = _normalize_company_name("Größe GmbH")
        assert "größe" in result

    def test_empty_string(self):
        assert _normalize_company_name("") == ""

    def test_lowercase(self):
        result = _normalize_company_name("ALLEX Medizintechnik")
        assert result == result.lower()

    def test_collapses_whitespace(self):
        result = _normalize_company_name("Meditec   GmbH")
        assert "  " not in result


# ---------------------------------------------------------------------------
# _select_examples
# ---------------------------------------------------------------------------


class TestSelectExamples:
    def test_default_counts(self):
        examples = (
            [_make_example("A")] * 5
            + [_make_example("B")] * 3
            + [_make_example("D")] * 3
        )
        selected = _select_examples(examples)
        klasses = [e.klass for e in selected]
        assert klasses.count("A") == 2
        assert klasses.count("B") == 1
        assert klasses.count("D") == 1

    def test_custom_n_per_class(self):
        examples = [_make_example("A")] * 5 + [_make_example("B")] * 5
        selected = _select_examples(examples, n_per_class={"A": 3, "B": 2})
        klasses = [e.klass for e in selected]
        assert klasses.count("A") == 3
        assert klasses.count("B") == 2

    def test_fewer_examples_than_requested(self):
        examples = [_make_example("A")]  # only 1, requesting 2
        selected = _select_examples(examples, n_per_class={"A": 2})
        assert len(selected) == 1

    def test_empty_examples(self):
        assert _select_examples([]) == []

    def test_missing_class_skipped(self):
        examples = [_make_example("A")] * 3
        selected = _select_examples(examples, n_per_class={"A": 1, "B": 1})
        klasses = [e.klass for e in selected]
        assert "B" not in klasses


# ---------------------------------------------------------------------------
# _format_example
# ---------------------------------------------------------------------------


class TestFormatExample:
    def test_includes_company_name(self):
        ex = _make_example()
        result = _format_example(ex)
        assert "Test GmbH" in result

    def test_includes_domain(self):
        ex = _make_example()
        result = _format_example(ex)
        assert "test.de" in result

    def test_includes_klass_in_output_json(self):
        ex = _make_example("B")
        result = _format_example(ex)
        assert '"klass": "B"' in result

    def test_includes_website_excerpt(self):
        ex = _make_example()
        result = _format_example(ex)
        assert "medtech service" in result


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_contains_company_name(self):
        p = _make_profile()
        result = _build_prompt(p, "Meditec GmbH", "meditec.de", None, None, None, None)
        assert "Meditec GmbH" in result

    def test_contains_domain(self):
        p = _make_profile()
        result = _build_prompt(p, "Meditec GmbH", "meditec.de", None, None, None, None)
        assert "meditec.de" in result

    def test_contains_class_definitions(self):
        p = _make_profile(class_defs={"A": "platform candidate", "B": "addon"})
        result = _build_prompt(p, "X", "x.de", None, None, None, None)
        assert "platform candidate" in result

    def test_contains_reason_codes(self):
        p = _make_profile()
        result = _build_prompt(p, "X", "x.de", None, None, None, None)
        assert "Unpassende_Branche" in result

    def test_no_none_literal_for_optional_fields(self):
        p = _make_profile()
        result = _build_prompt(p, "X", "x.de", None, None, None, None)
        assert "None" not in result

    def test_ma_count_included(self):
        p = _make_profile()
        result = _build_prompt(p, "X", "x.de", "Berlin", None, 35, "medtech text")
        assert "35" in result

    def test_scraped_text_included(self):
        p = _make_profile()
        result = _build_prompt(
            p, "X", "x.de", None, None, None, "medizintechnik service"
        )
        assert "medizintechnik service" in result


# ---------------------------------------------------------------------------
# _parse_result
# ---------------------------------------------------------------------------


class TestParseResult:
    def test_valid_klass_passes_through(self):
        for k in ("A", "B", "C", "D", "E"):
            assert _parse_result({"klass": k})["klass"] == k

    def test_invalid_klass_becomes_c(self):
        assert _parse_result({"klass": "Z"})["klass"] == "C"

    def test_missing_klass_becomes_c(self):
        assert _parse_result({})["klass"] == "C"

    def test_valid_reason_code_passes_through(self):
        result = _parse_result({"klass": "D", "reason_code": "Dental"})
        assert result["reason_code"] == "Dental"

    def test_invalid_reason_code_becomes_unklares_profil(self):
        result = _parse_result({"klass": "D", "reason_code": "InvalidCode"})
        assert result["reason_code"] == "Unklares_Profil"

    def test_known_category_resolves_leistung(self):
        result = _parse_result(
            {"klass": "A", "leistung_category": "medizintechnik-service"}
        )
        assert result["leistung_text"] == "Medizintechnik-Dienstleistern"
        assert result["leistung_absatz_2"] == "Medizintechnik-Dienstleistern"

    def test_medizinprodukt_handler_category(self):
        result = _parse_result(
            {"klass": "B", "leistung_category": "medizinprodukt-handler"}
        )
        assert result["leistung_text"] == "Medizinprodukt-Händlern"

    def test_unknown_category_falls_back_to_default(self):
        result = _parse_result(
            {"klass": "A", "leistung_category": "nonexistent-category"}
        )
        default = settings.LEISTUNG_CATEGORIES[settings.LEISTUNG_DEFAULT_CATEGORY]
        assert result["leistung_text"] == default["leistung_text"]

    def test_missing_category_falls_back_to_default(self):
        result = _parse_result({"klass": "A"})
        default = settings.LEISTUNG_CATEGORIES[settings.LEISTUNG_DEFAULT_CATEGORY]
        assert result["leistung_text"] == default["leistung_text"]

    def test_mehrwerte_truncated_at_400(self):
        long_text = "x" * 500
        result = _parse_result({"klass": "A", "mehrwerte": long_text})
        assert len(result["mehrwerte"]) == 400

    def test_reasoning_truncated_at_200(self):
        long_text = "y" * 300
        result = _parse_result({"klass": "A", "reasoning": long_text})
        assert len(result["reasoning"]) == 200

    def test_services_score_cast_to_int(self):
        result = _parse_result({"klass": "A", "services_score": "75"})
        assert result["services_score"] == 75
        assert isinstance(result["services_score"], int)

    def test_services_score_default_zero(self):
        assert _parse_result({})["services_score"] == 0

    def test_boolean_flags_cast_correctly(self):
        result = _parse_result({"klass": "A", "service_flag": True, "ssb_flag": False})
        assert result["service_flag"] is True
        assert result["ssb_flag"] is False
