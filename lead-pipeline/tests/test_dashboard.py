"""Tests for pure-logic functions in src/pipeline/dashboard.py (M19)."""

from __future__ import annotations

import base64
from datetime import date
from unittest.mock import patch

import pytest

import src.pipeline.dashboard as _dash_module
from src.pipeline.dashboard import _build_html, _load_data, _load_logo_b64
from src.pipeline.db import ensure_schema, get_connection


# ---------------------------------------------------------------------------
# _load_logo_b64
# ---------------------------------------------------------------------------


class TestLoadLogoB64:
    def test_missing_file_returns_empty(self, tmp_path):
        result = _load_logo_b64(tmp_path / "nonexistent.png")
        assert result == ""

    def test_valid_png_returns_data_uri(self, tmp_path):
        png_file = tmp_path / "logo.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = _load_logo_b64(png_file)
        assert result.startswith("data:image/png;base64,")
        encoded = result[len("data:image/png;base64,") :]
        assert base64.b64decode(encoded) == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# _build_html
# ---------------------------------------------------------------------------


def _html(
    data=None, serve_mode=False, logo_b64="", hubspot_portal_id=0, v2=False
) -> str:
    orig = _dash_module._USE_V2
    _dash_module._USE_V2 = v2
    try:
        with patch("src.pipeline.region_lookup.load_region_mapping", return_value={}):
            return _build_html(
                data or {},
                serve_mode=serve_mode,
                logo_b64=logo_b64,
                hubspot_portal_id=hubspot_portal_id,
            )
    finally:
        _dash_module._USE_V2 = orig


class TestBuildHtml:
    def test_data_json_embedded(self):
        data = {"companies": [{"domain": "test.de"}]}
        html = _html(data=data)
        assert '"test.de"' in html

    def test_serve_mode_true_replaces_placeholder(self):
        html = _html(serve_mode=True)
        assert "__SERVE_MODE_JS__" not in html

    def test_serve_mode_false_replaces_placeholder(self):
        html = _html(serve_mode=False)
        assert "__SERVE_MODE_JS__" not in html

    def test_live_badge_in_serve_mode(self):
        html = _html(serve_mode=True)
        assert "LIVE" in html
        assert "__LIVE_BADGE__" not in html

    def test_static_badge_not_in_serve_mode(self):
        html = _html(serve_mode=False)
        assert "STATIC" in html
        assert "__LIVE_BADGE__" not in html

    def test_date_str_replaced_with_today(self):
        html = _html()
        assert "__DATE_STR__" not in html
        assert date.today().isoformat() in html

    def test_logo_img_tag_when_logo_provided(self):
        html = _html(logo_b64="data:image/png;base64,abc123")
        assert '<img class="header-logo"' in html

    def test_no_logo_img_tag_when_empty(self):
        html = _html(logo_b64="")
        assert '<img class="header-logo"' not in html

    def test_hubspot_portal_id_embedded(self):
        html = _html(hubspot_portal_id=12345)
        assert "12345" in html
        assert "__HUBSPOT_PORTAL_ID__" not in html

    def test_region_mapping_json_replaced(self):
        html = _html()
        assert "__REGION_MAPPING_JSON__" not in html

    def test_letter_template_replaced(self):
        html = _html()
        assert "__LETTER_TEMPLATE__" not in html

    def test_no_raw_placeholders_remain(self):
        html = _html()
        for placeholder in [
            "__DATA_JSON__",
            "__SERVE_MODE_JS__",
            "__LIVE_BADGE__",
            "__DATE_STR__",
            "__LOGO_IMG__",
            "__HUBSPOT_PORTAL_ID__",
            "__REGION_MAPPING_JSON__",
            "__LETTER_TEMPLATE__",
        ]:
            assert placeholder not in html, f"Placeholder {placeholder!r} not replaced"


# ---------------------------------------------------------------------------
# _load_data: dropoff + required_fields (M28 Task 1)
# ---------------------------------------------------------------------------


@pytest.fixture()
def populated_db(tmp_path):
    db_path = tmp_path / "test.db"
    ensure_schema(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO company_records "
            "(id, domain, full_name, profile_id, source, klass, pipeline_stage, "
            "filter_pass, filter_reason, briefaktion, ingested_at) "
            "VALUES ('a1', 'a.de', 'A GmbH', 'medtech_germany', 'orbis', 'B', "
            "'classified', 1, NULL, 'BA7', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO company_records "
            "(id, domain, full_name, profile_id, source, klass, pipeline_stage, "
            "filter_pass, filter_reason, briefaktion, ingested_at) "
            "VALUES ('a2', 'b.de', 'B GmbH', 'medtech_germany', 'orbis', 'D', "
            "'classified', 1, NULL, 'BA7', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO company_records "
            "(id, domain, full_name, profile_id, source, klass, pipeline_stage, "
            "filter_pass, filter_reason, briefaktion, ingested_at) "
            "VALUES ('a3', 'c.de', 'C GmbH', 'medtech_germany', 'orbis', NULL, "
            "'filtered', 0, 'too_large', 'BA7', '2026-01-01T00:00:00')"
        )
    return db_path


class TestLoadDataDropoff:
    def test_dropoff_key_exists(self, populated_db):
        data = _load_data(populated_db)
        assert "dropoff" in data

    def test_dropoff_has_stages(self, populated_db):
        data = _load_data(populated_db)
        assert "stages" in data["dropoff"]
        assert len(data["dropoff"]["stages"]) >= 1

    def test_required_fields_key_exists(self, populated_db):
        data = _load_data(populated_db)
        assert "required_fields" in data
        assert isinstance(data["required_fields"], list)
        assert len(data["required_fields"]) >= 10


# ---------------------------------------------------------------------------
# TestBuildHtmlV2 (M28 Task 2)
# ---------------------------------------------------------------------------


class TestBuildHtmlV2:
    def test_v2_no_raw_placeholders_remain(self):
        html = _html(v2=True)
        for placeholder in [
            "__DATA_JSON__",
            "__SERVE_MODE_JS__",
            "__LIVE_BADGE__",
            "__DATE_STR__",
            "__LOGO_IMG__",
            "__HUBSPOT_PORTAL_ID__",
            "__REGION_MAPPING_JSON__",
            "__LETTER_TEMPLATE__",
        ]:
            assert placeholder not in html, f"Placeholder {placeholder!r} not replaced"

    def test_v2_contains_sidebar(self):
        html = _html(v2=True)
        assert 'class="side"' in html or 'class="side-mode"' in html

    def test_v2_contains_subnav(self):
        html = _html(v2=True)
        assert "subnav" in html

    def test_v2_contains_review_mode(self):
        html = _html(v2=True)
        assert "review" in html.lower()

    def test_v2_contains_analyze_mode(self):
        html = _html(v2=True)
        assert "analyze" in html.lower()


# ---------------------------------------------------------------------------
# M29 regression tests: --v1/--v2 flag routing + default promotion
# ---------------------------------------------------------------------------


class TestTemplateName:
    """Verify _template_name() returns the correct template for each flag state.

    Tests the M29 promotion gate: default (no flags) must serve v2, not v1 or
    the old dashboard.html.  Also verifies the --v1 rollback path and the
    explicit --v2 path.
    """

    def test_v1_flag_returns_v1_template(self):
        orig_v1, orig_v2 = _dash_module._USE_V1, _dash_module._USE_V2
        try:
            _dash_module._USE_V1 = True
            _dash_module._USE_V2 = False
            assert _dash_module._template_name() == "dashboard_v1.html"
        finally:
            _dash_module._USE_V1 = orig_v1
            _dash_module._USE_V2 = orig_v2

    def test_v2_flag_returns_v2_template(self):
        orig_v1, orig_v2 = _dash_module._USE_V1, _dash_module._USE_V2
        try:
            _dash_module._USE_V1 = False
            _dash_module._USE_V2 = True
            assert _dash_module._template_name() == "dashboard_v2.html"
        finally:
            _dash_module._USE_V1 = orig_v1
            _dash_module._USE_V2 = orig_v2

    def test_default_no_flags_returns_v2_template(self):
        """M29 promotion gate: default must be v2, not the old dashboard.html."""
        orig_v1, orig_v2 = _dash_module._USE_V1, _dash_module._USE_V2
        try:
            _dash_module._USE_V1 = False
            _dash_module._USE_V2 = False
            assert _dash_module._template_name() == "dashboard_v2.html"
        finally:
            _dash_module._USE_V1 = orig_v1
            _dash_module._USE_V2 = orig_v2


def _html_default_flags() -> str:
    """Build HTML with both _USE_V1 and _USE_V2 False (production default)."""
    orig_v1, orig_v2 = _dash_module._USE_V1, _dash_module._USE_V2
    _dash_module._USE_V1 = False
    _dash_module._USE_V2 = False
    try:
        with patch("src.pipeline.region_lookup.load_region_mapping", return_value={}):
            return _build_html({}, serve_mode=False)
    finally:
        _dash_module._USE_V1 = orig_v1
        _dash_module._USE_V2 = orig_v2


class TestDefaultPromotion:
    """Verify that running with no flags produces v2 HTML (M29 promotion gate)."""

    def test_default_build_contains_subnav(self):
        """v2-specific marker: subnav bar is not present in v1 / dashboard.html."""
        html = _html_default_flags()
        assert "subnav" in html

    def test_default_build_contains_v2_sidebar(self):
        html = _html_default_flags()
        assert 'class="side"' in html or 'class="side-mode"' in html

    def test_default_build_no_raw_placeholders(self):
        html = _html_default_flags()
        for placeholder in [
            "__DATA_JSON__",
            "__SERVE_MODE_JS__",
            "__LIVE_BADGE__",
            "__DATE_STR__",
            "__LOGO_IMG__",
            "__HUBSPOT_PORTAL_ID__",
            "__REGION_MAPPING_JSON__",
            "__LETTER_TEMPLATE__",
        ]:
            assert placeholder not in html, f"Placeholder {placeholder!r} not replaced"


class TestRequiredFieldsCount:
    """Verify _load_data() includes exactly 12 required_fields (M29 AC #4)."""

    def test_required_fields_exact_count(self, populated_db):
        data = _load_data(populated_db)
        assert len(data["required_fields"]) == 12
