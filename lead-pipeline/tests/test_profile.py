"""Tests for IndustryProfile loading and validation."""
import pytest
from pathlib import Path
from src.config.profile import load_profile, IndustryProfile

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PROFILE = FIXTURES / "sample_profile.json"
MEDTECH_PROFILE = Path(__file__).parent.parent / "profiles" / "medtech_germany.json"


class TestLoadProfile:
    def test_loads_sample_profile(self):
        profile = load_profile(SAMPLE_PROFILE)
        assert isinstance(profile, IndustryProfile)
        assert profile.id == "test_profile"
        assert profile.name == "Test Profile"

    def test_loads_medtech_profile(self):
        profile = load_profile(MEDTECH_PROFILE)
        assert profile.id == "medtech_germany"
        assert len(profile.discovery.wlw_search_terms) > 0

    def test_medtech_has_required_search_terms(self):
        profile = load_profile(MEDTECH_PROFILE)
        terms = profile.discovery.wlw_search_terms
        assert "Sprechstundenbedarf" in terms
        assert "Medizintechnik" in terms

    def test_medtech_filter_defaults(self):
        profile = load_profile(MEDTECH_PROFILE)
        assert profile.filters.ma_min == 5
        assert profile.filters.ma_max == 100
        assert "4774" in profile.filters.nace_exclude

    def test_medtech_dental_keywords_present(self):
        profile = load_profile(MEDTECH_PROFILE)
        keywords = [k.lower() for k in profile.filters.name_exclude_keywords]
        assert "zahn" in keywords
        assert "dental" in keywords

    def test_medtech_classification_has_all_classes(self):
        profile = load_profile(MEDTECH_PROFILE)
        for klass in ("A", "B", "C", "D", "E"):
            assert klass in profile.classification.class_definitions

    def test_medtech_ownership_config(self):
        profile = load_profile(MEDTECH_PROFILE)
        assert profile.ownership.hard_disqualify_subsidiary_threshold_pct == 75.0
        assert profile.ownership.hard_disqualify_pe_backed is True

    def test_medtech_has_region_prepositions(self):
        profile = load_profile(MEDTECH_PROFILE)
        assert "Bayern" in profile.export.region_prepositions
        assert "Saarland" in profile.export.region_prepositions
        assert profile.export.region_prepositions["Saarland"] == "im"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_profile(Path("does_not_exist.json"))

    def test_wlw_base_url_default(self):
        profile = load_profile(SAMPLE_PROFILE)
        assert profile.discovery.wlw_base_url == "https://www.wer-liefert-was.de"

    def test_sample_profile_no_supplementary_sources(self):
        """Profiles without supplementary_sources should default to empty list."""
        profile = load_profile(SAMPLE_PROFILE)
        assert profile.supplementary_sources == []

    def test_medtech_has_supplementary_sources(self):
        profile = load_profile(MEDTECH_PROFILE)
        assert len(profile.supplementary_sources) == 1
        src = profile.supplementary_sources[0]
        assert src.type == "excel_sheets"
        assert "ORBIS_search" in src.ingest_sheets
        assert "MASTER_Cleaning" in src.ingest_sheets
        assert "Serienbriefe" in src.dedup_sheets
        assert "Grande follow-up" in src.dedup_sheets
        assert src.city_region_sheet == "Städte-Regionen-Matching"
