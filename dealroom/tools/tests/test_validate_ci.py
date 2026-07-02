"""
pytest tests for validate_ci.py
Each rule has at least one PASS and one FAIL fixture.
Run: pytest dealroom/tools/tests/test_validate_ci.py -v
"""

import sys
import os

# Allow importing validate_ci from sibling directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validate_ci import (
    check_r1,
    check_r2,
    check_r3,
    check_r4,
    check_r5,
    parse_html,
    _parse_css,
)


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_root(html: str):
    return parse_html(html)


def _style_blocks(html: str):
    import re

    return re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL | re.IGNORECASE)


def _inline_styles(html: str):
    """Return list of (style_text, line) tuples from inline style="" attrs."""
    import re

    results = []
    for i, line in enumerate(html.splitlines(), 1):
        for m in re.finditer(r'style="([^"]*)"', line):
            results.append((m.group(1), i))
    return results


def _findings(html: str, audience: str = "en", rules=None):
    root = _make_root(html)
    sblocks = _style_blocks(html)
    inlines = _inline_styles(html)
    css_rules = _parse_css("\n".join(sblocks))
    findings = []
    if rules is None or "R1" in rules:
        findings += check_r1(root, audience, "test.html")
    if rules is None or "R2" in rules:
        findings += check_r2(sblocks, inlines, "test.html")
    if rules is None or "R3" in rules:
        findings += check_r3(sblocks, inlines, root, css_rules, "test.html")
    if rules is None or "R4" in rules:
        findings += check_r4(root, css_rules, "test.html")
    if rules is None or "R5" in rules:
        findings += check_r5(root, css_rules, "test.html")
    return findings


def _r(findings, rule):
    return [f for f in findings if f.rule == rule]


# ══════════════════════════════════════════════════════════════════════════════
# R1 — Number convention
# ══════════════════════════════════════════════════════════════════════════════


class TestR1:
    # PASS: EN doc with correct dot-decimal numbers
    def test_r1_en_pass_dot_decimal(self):
        html = "<p>Revenue: 44.6 M€, EBITDA margin 10.3%, multiple 4.9x</p>"
        assert _r(_findings(html, "en", ["R1"]), "R1") == []

    # PASS: EN doc — comma as thousands separator (3 digits) is fine
    def test_r1_en_pass_comma_thousands(self):
        html = "<p>Revenue: 3,129 K€ and 1,000 units sold in 2025.</p>"
        assert _r(_findings(html, "en", ["R1"]), "R1") == []

    # FAIL: EN doc has a German-style decimal (comma + 1-2 digits)
    def test_r1_en_fail_de_decimal(self):
        html = "<p>EBITDA margin: 10,3% and revenue 44,6 M€</p>"
        findings = _r(_findings(html, "en", ["R1"]), "R1")
        assert len(findings) >= 1
        found_vals = " ".join(f.found for f in findings)
        assert "10,3" in found_vals or "44,6" in found_vals

    # PASS: EN doc — version strings excluded
    def test_r1_en_pass_version_string(self):
        html = "<p>App v1.2.3 released in 2026-01-15.</p>"
        assert _r(_findings(html, "en", ["R1"]), "R1") == []

    # PASS: CSS content is never scanned for R1
    def test_r1_en_pass_css_skipped(self):
        html = "<style>body { font-size: 14,5px; letter-spacing: 0,07em; }</style><p>Hello</p>"
        # "14,5" and "0,07" inside <style> must not be flagged
        assert _r(_findings(html, "en", ["R1"]), "R1") == []

    # PASS: DE doc with correct comma-decimal
    def test_r1_de_pass_comma_decimal(self):
        html = "<p>Umsatz: 44,6 M€, Marge 10,3%</p>"
        assert _r(_findings(html, "de", ["R1"]), "R1") == []

    # FAIL: DE doc has English dot-decimal
    def test_r1_de_fail_en_decimal(self):
        html = "<p>Umsatz: 44.6 M€</p>"
        findings = _r(_findings(html, "de", ["R1"]), "R1")
        assert len(findings) >= 1
        assert "44.6" in findings[0].found

    # PASS: years (2026) never flagged even though they contain 2 groups of digits
    def test_r1_en_pass_year_not_flagged(self):
        html = "<p>Results for FY 2025 and outlook 2026.</p>"
        assert _r(_findings(html, "en", ["R1"]), "R1") == []

    # PASS: code/pre blocks are skipped
    def test_r1_en_pass_code_skipped(self):
        html = "<pre><code>price = 44,6 * 1,2</code></pre>"
        assert _r(_findings(html, "en", ["R1"]), "R1") == []

    # FAIL: mixing conventions — some dot, some comma decimal in same EN doc
    def test_r1_en_fail_mixed_conventions(self):
        html = "<p>EV: 1.5 M€ (correct) but margin 10,3% (wrong)</p>"
        findings = _r(_findings(html, "en", ["R1"]), "R1")
        assert any("10,3" in f.found for f in findings)


# ══════════════════════════════════════════════════════════════════════════════
# R2 — Color palette
# ══════════════════════════════════════════════════════════════════════════════


class TestR2:
    # PASS: CI palette colors only
    def test_r2_pass_palette_colors(self):
        html = """
        <style>
        h1 { color: #0891B2; background: #FFFFFF; }
        .alert { color: #E11D48; }
        </style>
        <h1>Title</h1>
        """
        assert _r(_findings(html, rules=["R2"]), "R2") == []

    # PASS: neutral greys (tolerance list)
    def test_r2_pass_neutral_greys(self):
        html = """
        <style>
        td { color: #6b7280; background-color: #f9fafb; border-color: #e5e7eb; }
        </style>
        <table><tr><td>text</td></tr></table>
        """
        assert _r(_findings(html, rules=["R2"]), "R2") == []

    # FAIL: off-brand saturated color
    def test_r2_fail_off_brand_color(self):
        html = """
        <style>
        h1 { color: #FF6600; }
        </style>
        <h1>Off-brand</h1>
        """
        findings = _r(_findings(html, rules=["R2"]), "R2")
        assert any("#ff6600" in f.found for f in findings)

    # PASS: CSS custom property definitions in :root are not flagged
    def test_r2_pass_css_var_definitions_skipped(self):
        html = """
        <style>
        :root { --my-brand: #BADBAD; }
        h1 { color: var(--my-brand); }
        </style>
        <h1>Title</h1>
        """
        # The --my-brand definition is a custom property (skipped); var() usage is unresolvable (skipped)
        assert _r(_findings(html, rules=["R2"]), "R2") == []

    # PASS: inline style using palette color
    def test_r2_pass_inline_palette(self):
        html = '<p style="color: #0891B2;">Brand colored text</p>'
        assert _r(_findings(html, rules=["R2"]), "R2") == []

    # FAIL: inline style with off-brand color
    def test_r2_fail_inline_off_brand(self):
        html = '<p style="color: #BADBAD;">Off-brand inline</p>'
        findings = _r(_findings(html, rules=["R2"]), "R2")
        assert len(findings) >= 1
        assert "#badbad" in findings[0].found

    # PASS: rgba derived from CI palette color is allowed
    def test_r2_pass_rgba_palette_derived(self):
        # rgba(8,145,178,.12) normalizes to #0891b2 — CI brand color
        html = "<style>.badge { background: rgba(8,145,178,.12); }</style>"
        assert _r(_findings(html, rules=["R2"]), "R2") == []

    # PASS: very low alpha rgba is treated as transparent — not flagged
    def test_r2_pass_very_low_alpha_skipped(self):
        html = "<style>.hover { background: rgba(255,0,0,0.04); }</style>"
        assert _r(_findings(html, rules=["R2"]), "R2") == []


# ══════════════════════════════════════════════════════════════════════════════
# R3 — Font discipline
# ══════════════════════════════════════════════════════════════════════════════


class TestR3:
    # PASS: Arial primary font
    def test_r3_pass_arial(self):
        html = "<style>body { font-family: Arial, Helvetica, sans-serif; }</style>"
        findings = _r(_findings(html, rules=["R3"]), "R3")
        font_findings = [f for f in findings if "font" in f.found.lower()]
        assert font_findings == []

    # FAIL: non-CI primary font
    def test_r3_fail_off_font(self):
        html = '<style>body { font-family: "Times New Roman", serif; font-size: 14px; }</style>'
        findings = _r(_findings(html, rules=["R3"]), "R3")
        assert any("times new roman" in f.found.lower() for f in findings)

    # FAIL: font size below readable floor (e.g. 8px)
    def test_r3_fail_too_small(self):
        html = "<style>.footnote { font-size: 8px; font-family: Arial; }</style>"
        findings = _r(_findings(html, rules=["R3"]), "R3")
        small = [f for f in findings if "8px" in f.found and "R3" == f.rule]
        assert small

    # PASS: font-family via var() — not checked for family name
    def test_r3_pass_var_font_family(self):
        html = "<style>body { font-family: var(--ci-font); font-size: 14px; }</style>"
        findings = _r(_findings(html, rules=["R3"]), "R3")
        assert not any("primary font" in f.found for f in findings)

    # FAIL: low contrast pair (grey text on grey background in same rule)
    def test_r3_fail_low_contrast(self):
        # #aaaaaa on #dddddd: both mid-grey, very low contrast
        html = (
            "<style>.muted-box { color: #aaaaaa; background-color: #dddddd; }</style>"
        )
        findings = _r(_findings(html, rules=["R3"]), "R3")
        contrast_finds = [f for f in findings if "contrast" in f.found]
        assert contrast_finds, f"expected contrast finding, got: {findings}"

    # PASS: good contrast pair (white on brand color)
    def test_r3_pass_good_contrast(self):
        html = "<style>.header { color: #ffffff; background-color: #0891B2; }</style>"
        findings = _r(_findings(html, rules=["R3"]), "R3")
        contrast_finds = [f for f in findings if "contrast" in f.found]
        assert contrast_finds == []


# ══════════════════════════════════════════════════════════════════════════════
# R4 — Heading consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestR4:
    # PASS: all h2s share the same style
    def test_r4_pass_consistent_headings(self):
        html = """
        <style>
        h2 { font-size: 22px; font-weight: 700; color: #000000; }
        </style>
        <h2>Section A</h2>
        <h2>Section B</h2>
        <h2>Section C</h2>
        """
        assert _r(_findings(html, rules=["R4"]), "R4") == []

    # FAIL: one h2 has a diverging inline style
    def test_r4_fail_divergent_inline(self):
        html = """
        <style>
        h2 { font-size: 22px; font-weight: 700; color: #000000; }
        </style>
        <h2>Normal heading</h2>
        <h2>Normal heading 2</h2>
        <h2 style="font-size: 30px; color: #FF0000;">Rogue heading</h2>
        """
        findings = _r(_findings(html, rules=["R4"]), "R4")
        assert findings, "expected divergent heading to be flagged"
        # The rogue heading should be flagged, not the majority
        assert any("30px" in f.found or "#ff0000" in f.found.lower() for f in findings)

    # PASS: only one h1 — nothing to compare
    def test_r4_pass_single_heading(self):
        html = """
        <style>h1 { font-size: 30px; }</style>
        <h1>Only heading</h1>
        """
        assert _r(_findings(html, rules=["R4"]), "R4") == []

    # FAIL: h3 elements have two different class-driven sizes (via inline)
    def test_r4_fail_two_distinct_styles(self):
        html = """
        <style>h3 { font-size: 17px; color: #000; }</style>
        <h3>First</h3>
        <h3 style="font-size: 20px;">Second — bigger</h3>
        <h3>Third</h3>
        """
        findings = _r(_findings(html, rules=["R4"]), "R4")
        assert findings, "h3 with diverging inline size should be flagged"


# ══════════════════════════════════════════════════════════════════════════════
# R5 — Table hygiene
# ══════════════════════════════════════════════════════════════════════════════


class TestR5:
    # PASS: text column explicitly left-aligned, header has bg
    def test_r5_pass_clean_table(self):
        html = """
        <style>
        th { background-color: #0891B2; color: #fff; }
        td.label { text-align: left; }
        td.value { text-align: right; }
        </style>
        <table>
          <thead><tr><th>Label</th><th>Value</th></tr></thead>
          <tbody>
            <tr>
              <td class="label">Revenue</td>
              <td class="value">3,129</td>
            </tr>
            <tr>
              <td class="label">EBITDA</td>
              <td class="value">359</td>
            </tr>
          </tbody>
        </table>
        """
        assert _r(_findings(html, rules=["R5"]), "R5") == []

    # FAIL: text cell has explicit inline text-align:center (wrong for text content)
    def test_r5_fail_explicit_wrong_align_on_text_cell(self):
        html = """
        <style>th { background: #0891B2; }</style>
        <table>
          <thead><tr><th>Label</th><th>Value</th></tr></thead>
          <tbody>
            <tr>
              <td style="text-align:center">Revenue description text here</td>
              <td>1000</td>
            </tr>
          </tbody>
        </table>
        """
        findings = _r(_findings(html, rules=["R5"]), "R5")
        alignment_finds = [f for f in findings if "text-align" in f.found]
        assert alignment_finds, "explicit inline center on text cell should be flagged"

    # FAIL: header row has no background color
    def test_r5_fail_no_header_background(self):
        html = """
        <table>
          <thead><tr><th>Col A</th><th>Col B</th></tr></thead>
          <tbody><tr><td>a</td><td>b</td></tr></tbody>
        </table>
        """
        findings = _r(_findings(html, rules=["R5"]), "R5")
        bg_finds = [
            f
            for f in findings
            if "background" in f.found.lower() or "background" in f.expected.lower()
        ]
        assert bg_finds

    # FAIL: mixed number+word in cell
    def test_r5_fail_mixed_cell(self):
        html = """
        <style>th { background: #0891B2; } td { text-align: left; }</style>
        <table>
          <thead><tr><th>Metric</th><th>Value</th></tr></thead>
          <tbody>
            <tr><td>Revenue</td><td>44.6 avg</td></tr>
          </tbody>
        </table>
        """
        findings = _r(_findings(html, rules=["R5"]), "R5")
        mixed = [f for f in findings if "mixed" in f.found.lower()]
        assert mixed

    # PASS: numeric columns need not be left-aligned
    def test_r5_pass_numeric_col_right_aligned(self):
        html = """
        <style>
        th { background: #0891B2; color: #fff; }
        td { text-align: right; }
        td:first-child { text-align: left; }
        </style>
        <table>
          <thead><tr><th>Label</th><th>2023</th><th>2024</th></tr></thead>
          <tbody>
            <tr>
              <td style="text-align:left;">Revenue</td>
              <td>3129</td>
              <td>3392</td>
            </tr>
          </tbody>
        </table>
        """
        findings = _r(_findings(html, rules=["R5"]), "R5")
        # Numeric columns right-aligned should NOT be flagged
        numeric_align = [
            f for f in findings if "text-align" in f.found and "3129" in f.location
        ]
        assert numeric_align == []


# ══════════════════════════════════════════════════════════════════════════════
# Integration: normalize_color edge cases
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizeColor:
    def test_hex3_expanded(self):
        from validate_ci import normalize_color

        assert normalize_color("#fff") == "#ffffff"

    def test_hex6_lowered(self):
        from validate_ci import normalize_color

        assert normalize_color("#0891B2") == "#0891b2"

    def test_rgb_tuple(self):
        from validate_ci import normalize_color

        # rgb(8,145,178) = #0891b2
        assert normalize_color("rgb(8,145,178)") == "#0891b2"

    def test_rgba_above_threshold(self):
        from validate_ci import normalize_color

        # alpha 0.5 — above floor — should normalize
        assert normalize_color("rgba(8,145,178,0.5)") == "#0891b2"

    def test_rgba_below_threshold(self):
        from validate_ci import normalize_color

        # alpha 0.04 — below floor — treated as transparent
        assert normalize_color("rgba(255,0,0,0.04)") == "transparent"

    def test_keyword_transparent(self):
        from validate_ci import normalize_color

        assert normalize_color("transparent") == "transparent"
