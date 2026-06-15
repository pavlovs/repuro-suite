"""Tests for WLW scraper."""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from src.config.profile import load_profile
from src.pipeline.wlw_scraper import (
    _parse_domain,
    _parse_employee_range,
    _extract_nuxt_homepages,
    scrape_wlw,
    _write_discovered_csv,
)
from src.pipeline.models import CompanyRecord
from src.utils.knowledge_base import KnowledgeBase

PROFILE_PATH = Path(__file__).parent.parent / "profiles" / "medtech_germany.json"


@pytest.fixture
def profile():
    return load_profile(PROFILE_PATH)


@pytest.fixture
def kb(tmp_path: Path) -> KnowledgeBase:
    return KnowledgeBase(tmp_path / "test_kb.db")


class TestParseDomain:
    def test_strips_https(self):
        assert _parse_domain("https://example.de/path") == "example.de"

    def test_strips_http(self):
        assert _parse_domain("http://example.de") == "example.de"

    def test_strips_www(self):
        assert _parse_domain("www.example.de") == "example.de"

    def test_strips_https_and_www(self):
        assert _parse_domain("https://www.example.de/page") == "example.de"

    def test_empty_string_returns_none(self):
        assert _parse_domain("") is None

    def test_none_returns_none(self):
        assert _parse_domain(None) is None

    def test_no_dot_returns_none(self):
        assert _parse_domain("nodot") is None

    def test_preserves_subdomain(self):
        assert _parse_domain("https://shop.example.de") == "shop.example.de"

    def test_lowercases(self):
        assert _parse_domain("https://EXAMPLE.DE") == "example.de"


class TestParseEmployeeRange:
    def test_range_returns_lower_bound(self):
        assert _parse_employee_range("10-19") == 10

    def test_range_20_49(self):
        assert _parse_employee_range("20-49") == 20

    def test_single_digit_range(self):
        assert _parse_employee_range("1-4") == 1

    def test_plus_notation(self):
        assert _parse_employee_range("500+") == 500

    def test_empty_returns_none(self):
        assert _parse_employee_range("") is None

    def test_none_returns_none(self):
        assert _parse_employee_range(None) is None


class TestExtractNuxtHomepages:
    def test_extracts_slug_url_pairs(self):
        html = """<script>["ShallowReactive",1],"some-company-1234567","http://example.de/"</script>"""
        result = _extract_nuxt_homepages(html)
        assert result.get("some-company-1234567") == "http://example.de/"

    def test_returns_empty_dict_when_no_nuxt(self):
        html = "<html><body>no nuxt state here</body></html>"
        assert _extract_nuxt_homepages(html) == {}

    def test_extracts_multiple_companies(self):
        html = """<script>["ShallowReactive",1]
        "alpha-gmbh-111","http://alpha.de/"
        "beta-kg-222","https://www.beta.de/"
        </script>"""
        result = _extract_nuxt_homepages(html)
        assert result.get("alpha-gmbh-111") == "http://alpha.de/"
        assert result.get("beta-kg-222") == "https://www.beta.de/"

    def test_ignores_slugs_without_numeric_id(self):
        html = """<script>["ShallowReactive",1],"no-numbers","http://example.de/"</script>"""
        result = _extract_nuxt_homepages(html)
        assert "no-numbers" not in result


class TestScrapeWlwDryRun:
    def test_dry_run_returns_empty_list(self, profile, kb):
        records = scrape_wlw(profile, kb=kb, dry_run=True)
        assert records == []

    def test_dry_run_makes_no_http_calls(self, profile, kb):
        with patch("src.pipeline.wlw_scraper.fetch_with_retry") as mock_fetch:
            scrape_wlw(profile, kb=kb, dry_run=True)
            mock_fetch.assert_not_called()

    def test_dry_run_writes_no_files(self, profile, kb, tmp_path):
        from src.config import settings
        with patch.object(settings, "STAGING_WLW_RAW", tmp_path / "00_discovered.csv"):
            scrape_wlw(profile, kb=kb, dry_run=True)
            assert not (tmp_path / "00_discovered.csv").exists()


class TestWriteDiscoveredCsv:
    def test_creates_csv_file(self, tmp_path: Path):
        records = [
            CompanyRecord(domain="a.de", full_name="A GmbH", profile_id="test", source="WLW"),
            CompanyRecord(domain="b.de", full_name="B GmbH", profile_id="test", source="WLW"),
        ]
        path = tmp_path / "discovered.csv"
        _write_discovered_csv(records, path)
        assert path.exists()

    def test_csv_has_correct_row_count(self, tmp_path: Path):
        import csv
        records = [
            CompanyRecord(domain="a.de", full_name="A GmbH", profile_id="test", source="WLW"),
            CompanyRecord(domain="b.de", full_name="B GmbH", profile_id="test", source="WLW"),
        ]
        path = tmp_path / "discovered.csv"
        _write_discovered_csv(records, path)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2

    def test_csv_preserves_umlauts(self, tmp_path: Path):
        import csv
        records = [
            CompanyRecord(
                domain="mueller.de",
                full_name="Müller Medizintechnik GmbH",
                profile_id="test",
                source="WLW",
                city="Köln",
            )
        ]
        path = tmp_path / "discovered.csv"
        _write_discovered_csv(records, path)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["full_name"] == "Müller Medizintechnik GmbH"
        assert rows[0]["city"] == "Köln"

    def test_empty_records_writes_no_file(self, tmp_path: Path):
        path = tmp_path / "empty.csv"
        _write_discovered_csv([], path)
        assert not path.exists()
