"""Tests for CompanyRecord data model."""
import pytest
from src.pipeline.models import CompanyRecord


def make_record(**kwargs) -> CompanyRecord:
    defaults = dict(domain="example.de", full_name="Example GmbH", profile_id="test", source="WLW")
    defaults.update(kwargs)
    return CompanyRecord(**defaults)


class TestCompanyRecordCreation:
    def test_required_fields(self):
        r = make_record()
        assert r.domain == "example.de"
        assert r.full_name == "Example GmbH"
        assert r.profile_id == "test"
        assert r.source == "WLW"

    def test_id_computed_from_domain(self):
        import hashlib
        r = make_record(domain="test.de")
        expected = hashlib.md5("test.de".encode()).hexdigest()[:12]
        assert r.id == expected

    def test_id_stable_for_same_domain(self):
        r1 = make_record(domain="stable.de")
        r2 = make_record(domain="stable.de")
        assert r1.id == r2.id

    def test_id_differs_for_different_domains(self):
        r1 = make_record(domain="a.de")
        r2 = make_record(domain="b.de")
        assert r1.id != r2.id

    def test_all_optional_fields_default_none(self):
        r = make_record()
        optional_fields = [
            "hrb_number", "rechtsform", "street", "plz_ort", "city", "region",
            "ma_count", "revenue_tsd_eur",
            "klass", "services_score", "service_flag", "distributor_flag",
            "ssb_flag", "leistung_text", "reasoning", "compliment_draft", "reclassify_reason",
            "gesellschafter_name", "gesellschafter_share_pct", "gesellschafter_age",
            "is_subsidiary", "is_pe_backed",
            "gf_name", "gf_email", "gf_phone", "anrede", "salutation",
            "filter_pass", "filter_reason", "ownership_pass", "ownership_reason",
            "scraped_text", "scraped_at", "classified_at", "enriched_at",
        ]
        for field_name in optional_fields:
            assert getattr(r, field_name) is None, f"{field_name} should default to None"

    def test_already_approached_defaults_false(self):
        r = make_record()
        assert r.already_approached is False


class TestCompanyRecordSerialization:
    def test_to_dict_round_trip(self):
        from datetime import datetime
        r = make_record(
            domain="medtec.de",
            full_name="MedTec GmbH",
            klass="A",
            ma_count=45,
            city="München",
            region="Bayern",
            scraped_at=datetime(2026, 3, 24, 10, 0, 0),
        )
        d = r.to_dict()
        r2 = CompanyRecord.from_dict(d)

        assert r2.domain == r.domain
        assert r2.full_name == r.full_name
        assert r2.klass == r.klass
        assert r2.ma_count == r.ma_count
        assert r2.city == r.city
        assert r2.region == r.region
        assert r2.scraped_at == r.scraped_at
        assert r2.id == r.id  # recomputed from domain

    def test_to_dict_has_id(self):
        r = make_record()
        d = r.to_dict()
        assert "id" in d

    def test_to_dict_datetime_as_isostring(self):
        from datetime import datetime
        r = make_record(scraped_at=datetime(2026, 1, 1, 12, 0, 0))
        d = r.to_dict()
        assert isinstance(d["scraped_at"], str)
        assert "2026-01-01" in d["scraped_at"]

    def test_from_dict_handles_empty_strings(self):
        d = dict(
            domain="x.de",
            full_name="X GmbH",
            profile_id="test",
            source="WLW",
            ma_count="",
            scraped_at="",
            filter_pass="",
            already_approached="",
        )
        r = CompanyRecord.from_dict(d)
        assert r.ma_count is None
        assert r.scraped_at is None
        assert r.filter_pass is None
        assert r.already_approached is False

    def test_from_dict_parses_booleans(self):
        d = dict(
            domain="x.de",
            full_name="X GmbH",
            profile_id="test",
            source="WLW",
            already_approached="True",
            filter_pass="False",
            service_flag="true",
        )
        r = CompanyRecord.from_dict(d)
        assert r.already_approached is True
        assert r.filter_pass is False
        assert r.service_flag is True

    def test_from_dict_parses_integers(self):
        d = dict(
            domain="x.de",
            full_name="X GmbH",
            profile_id="test",
            source="WLW",
            ma_count="42",
            services_score="75",
        )
        r = CompanyRecord.from_dict(d)
        assert r.ma_count == 42
        assert r.services_score == 75

    def test_umlauts_preserved(self):
        r = make_record(full_name="Müller Medizintechnik GmbH", city="Köln")
        d = r.to_dict()
        r2 = CompanyRecord.from_dict(d)
        assert r2.full_name == "Müller Medizintechnik GmbH"
        assert r2.city == "Köln"
