"""Tests for utility modules — HTML cleaning and Excel helpers."""

from pathlib import Path
from unittest.mock import patch

import httpx

from src.utils.web import clean_html, fetch_with_retry


class TestCleanHtml:
    def test_strips_html_tags(self):
        html = "<p>Hello <b>World</b></p>"
        result = clean_html(html)
        assert "<p>" not in result
        assert "<b>" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_nav_tag(self):
        html = "<nav>Menu Item</nav><main>Content</main>"
        result = clean_html(html)
        assert "Menu Item" not in result
        assert "Content" in result

    def test_removes_footer_tag(self):
        html = "<footer>Copyright 2026</footer><p>Real content</p>"
        result = clean_html(html)
        assert "Copyright" not in result
        assert "Real content" in result

    def test_removes_script_tag(self):
        html = "<script>var x = 1;</script><p>Text</p>"
        result = clean_html(html)
        assert "var x" not in result
        assert "Text" in result

    def test_removes_style_tag(self):
        html = "<style>body { color: red; }</style><p>Text</p>"
        result = clean_html(html)
        assert "color: red" not in result
        assert "Text" in result

    def test_preserves_german_umlauts(self):
        html = (
            "<p>Wir liefern Sprechstundenbedarf für Arztpraxen in ganz Österreich.</p>"
        )
        result = clean_html(html)
        assert "Sprechstundenbedarf" in result
        assert "für" in result
        assert "Österreich" in result

    def test_preserves_eszett(self):
        html = "<p>Medizinische Geräte und Zubehör — Qualität aus Deutschland.</p>"
        result = clean_html(html)
        assert "Qualität" in result

    def test_empty_string_returns_empty(self):
        result = clean_html("")
        assert result == ""

    def test_normalizes_whitespace(self):
        html = "<p>  Too   much   space  </p>"
        result = clean_html(html)
        assert "  " not in result.strip()

    def test_handles_special_characters(self):
        html = "<p>Ärzte &amp; Praxen: Medizintechnik GmbH &amp; Co. KG</p>"
        result = clean_html(html)
        assert "Ärzte" in result
        assert "GmbH" in result

    def test_real_world_like_content(self):
        html = """
        <html>
          <head><title>Medizintechnik GmbH</title></head>
          <body>
            <nav><a href="/">Home</a><a href="/kontakt">Kontakt</a></nav>
            <main>
              <h1>Ihr Partner für Medizintechnik</h1>
              <p>Wir bieten Wartung, Reparatur und Lieferung von Medizinprodukten für
              niedergelassene Ärzte in Bayern und Umgebung.</p>
            </main>
            <footer>Impressum | Datenschutz</footer>
          </body>
        </html>
        """
        result = clean_html(html)
        assert "Wartung" in result
        assert "Reparatur" in result
        assert "Medizinprodukten" in result
        assert "Impressum" not in result
        assert "Home" not in result


class TestExcelHelpers:
    def test_write_and_read_roundtrip(self, tmp_path: Path):
        import pandas as pd
        from src.utils.excel import write_dataframe_to_xlsx, read_sheet

        df = pd.DataFrame(
            {
                "Name": ["Müller GmbH", "Schmidt AG"],
                "Stadt": ["München", "Berlin"],
                "MA": [45, 12],
            }
        )
        output_path = tmp_path / "test.xlsx"
        write_dataframe_to_xlsx(df, output_path)

        df2 = read_sheet(output_path, "Sheet1")
        assert list(df2.columns) == list(df.columns)
        assert len(df2) == 2
        assert df2["Name"].iloc[0] == "Müller GmbH"
        assert df2["Stadt"].iloc[1] == "Berlin"

    def test_validate_no_formula_errors_clean_file(self, tmp_path: Path):
        import pandas as pd
        from src.utils.excel import write_dataframe_to_xlsx, validate_no_formula_errors

        df = pd.DataFrame({"col": ["value1", "value2"]})
        path = tmp_path / "clean.xlsx"
        write_dataframe_to_xlsx(df, path)
        assert validate_no_formula_errors(path) is True

    def test_creates_parent_directory(self, tmp_path: Path):
        import pandas as pd
        from src.utils.excel import write_dataframe_to_xlsx

        nested_path = tmp_path / "subdir" / "output.xlsx"
        df = pd.DataFrame({"col": [1, 2]})
        write_dataframe_to_xlsx(df, nested_path)
        assert nested_path.exists()


# ---------------------------------------------------------------------------
# fetch_with_retry — InvalidURL handling (Bug fix: batch killer)
# ---------------------------------------------------------------------------


class TestFetchWithRetryInvalidUrl:
    def test_invalid_url_returns_none_not_raises(self):
        """httpx.InvalidURL must not propagate — fetch_with_retry must return None."""
        with patch("src.utils.web._client") as mock_client:
            mock_client.get.side_effect = httpx.InvalidURL(
                "bad redirect: absolute path in Location"
            )
            result = fetch_with_retry("https://broken-redirect.example.com")
        assert result is None

    def test_invalid_url_does_not_retry(self):
        """InvalidURL is terminal — no retries should be attempted (URL won't fix itself)."""
        with patch("src.utils.web._client") as mock_client:
            mock_client.get.side_effect = httpx.InvalidURL("bad url")
            fetch_with_retry("https://example.com", retries=3)
        # Must have tried only once — retrying an invalid URL wastes time and clogs the pool
        mock_client.get.assert_called_once()

    def test_extract_page_text_survives_invalid_url(self):
        """extract_page_text must return empty string, not crash, when all fetches hit InvalidURL."""
        from src.utils.web import extract_page_text

        with patch("src.utils.web._client") as mock_client:
            mock_client.get.side_effect = httpx.InvalidURL("bad redirect")
            result = extract_page_text("broken-redirect.example.com")
        assert isinstance(result, str)
