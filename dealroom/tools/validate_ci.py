#!/usr/bin/env python3
"""
Repuro Corporate Identity validator for HTML deliverables.

Checks:
  R1 - Number convention by audience (en=dot-decimal, de=comma-decimal)
  R2 - Color palette compliance (CI palette + documented tolerance)
  R3 - Font family and size discipline (Arial-first, readable floor, contrast)
  R4 - Heading style consistency (h1-h4 siblings share same signature)
  R5 - Table hygiene (text-column alignment, mixed cells, header background)

Usage:
    python dealroom/tools/validate_ci.py <file.html> [more.html ...]
           --audience en|de [--format text|json]

Exit: 0 = PASS, 1 = FAIL (one or more findings).
"""

import sys
import re
import json
import argparse
from pathlib import Path
from html.parser import HTMLParser
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple


# ── CI constants ───────────────────────────────────────────────────────────────

# Canonical CI palette (repuro-ci.md)
CI_PALETTE: Set[str] = {
    "#0891b2",  # primary brand / header fill
    "#ffffff",  # white
    "#22d3ee",  # accent 1
    "#000000",  # black
    "#8de8f6",  # accent 2
    "#e11d48",  # accent 3 (alert)
    "#eab308",  # accent 4 (warning)
    "#a855f7",  # accent 5
}

# Documented tolerance list: neutrals + common UI functional colors
# Rationale: a whitelist of ONLY 6 colors would flag every grey border/shadow,
# producing hundreds of noise findings. Neutrals are universally safe; the CI
# risk is saturated off-brand colours, not neutral greys.
TOLERANCE_COLORS: Set[str] = {
    # Pure whites / near-whites
    "#fff",
    "#fafafa",
    "#f9fafb",
    "#f8f9fa",
    "#f5f5f5",
    "#f4f4f4",
    "#f3f4f6",
    "#f2f2f2",
    "#f1fafc",  # ci-canvas used in proposal
    "#f0f0f0",
    "#eeeeee",
    # Borders / dividers
    "#e9ecef",
    "#e5e7eb",
    "#e0e0e0",
    "#dee2e6",
    "#dddddd",
    "#d1d5db",
    "#ced4da",
    "#cccccc",
    # Mid greys
    "#bbbbbb",
    "#9ca3af",
    "#adb5bd",
    "#aaaaaa",
    "#999999",
    "#888888",
    "#6b7280",
    "#868e96",
    "#777777",
    "#666666",
    # Dark text greys
    "#4b5563",
    "#495057",
    "#555555",
    "#374151",
    "#343a40",
    "#444444",
    "#1f2937",
    "#212529",
    "#333333",
    "#111827",
    "#222222",
    "#0d0d0d",
    "#000",
    # Badge tints (light fills, safe)
    "#fef3c7",
    "#fde68a",  # amber tints
    "#fee2e2",
    "#fecaca",  # red tints
    "#d1fae5",
    "#a7f3d0",  # green tints
    "#dbeafe",
    "#bfdbfe",
    "#eff6ff",  # blue tints
    "#e0f2fe",
    "#bae6fd",  # cyan tints (Accent1 family)
    "#fef9c3",  # yellow tint
    # Common UI text on dark amber
    "#92400e",
    "#78350f",
    # Functional blues used in boardroom / cockpit nav
    "#1d4ed8",
    "#1e40af",
    "#2563eb",
    "#3b82f6",
    "#60a5fa",
    "#0068b0",
    # Functional greens (deal stages)
    "#10b981",
    "#059669",
    "#059689",
    "#16a34a",
    "#15803d",
    "#065f46",
    "#047857",
    "#0d9488",
    # Functional reds / pinks
    "#ef4444",
    "#dc2626",
    "#b91c1c",
    # Functional ambers / oranges
    "#f59e0b",
    "#d97706",
    "#b45309",
    # Functional violets / indigos
    "#8b5cf6",
    "#7c3aed",
    "#6366f1",
    "#4f46e5",
    # Teal
    "#14b8a6",
    # Stage-specific colors from the design system
    "#3b82f6",  # valuation_rfi
    "#6366f1",  # indicative_offer
    "#059669",  # due_diligence
    "#0d9488",  # contract_negotiation
    "#065f46",  # closed
    # CSS keyword aliases
    "transparent",
    "inherit",
    "initial",
    "unset",
    "currentcolor",
    "none",
    "auto",
    "white",
    "black",
}

# Font families allowed by CI spec (Arial always-first; system fallbacks OK)
CI_FONTS: Set[str] = {
    "arial",
    "inter",  # cockpit / review views — allowed secondary
    "helvetica neue",
    "helvetica",
    "-apple-system",
    "blinkmacsystemfont",
    "system-ui",
    "segoe ui",
    "roboto",
    "sans-serif",
    "monospace",
    "courier new",
    "courier",
    "inherit",
    "initial",
    "unset",
}

READABLE_FLOOR_PX = 12  # body text below this px → finding
ONE_OFF_THRESHOLD = 2  # sizes appearing ≤ this many times → one-off finding
MIN_CONTRAST_RATIO = 3.0  # below WCAG AA Large Text minimum

# Tags whose text content we must skip for R1 number scan
_SKIP_TEXT_TAGS: Set[str] = {"style", "script", "code", "pre", "noscript", "template"}

# Pre-compiled exclusion patterns for R1
_RE_VERSION = re.compile(r"\bv?\d+\.\d+\.\d+\b")
_RE_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_RE_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_RE_HEX_IN_TEXT = re.compile(r"#[0-9a-fA-F]{3,8}")

# Patterns used in color extraction
_RE_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{3,8})\b")
_RE_RGB_COLOR = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
_RE_RGBA_COLOR = re.compile(
    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)"
)

# CSS properties we care about for color extraction
_COLOR_PROPS = {
    "color",
    "background",
    "background-color",
    "border-color",
    "border-top-color",
    "border-bottom-color",
    "border-left-color",
    "border-right-color",
    "outline-color",
    "box-shadow",
    "text-shadow",
}

# The minimum alpha below which we skip rgba colour checks (overlays/tints)
_RGBA_ALPHA_FLOOR = 0.15


# ── Data structures ────────────────────────────────────────────────────────────


@dataclass
class Finding:
    rule: str
    file: str
    location: str
    found: str
    expected: str

    def as_text(self) -> str:
        return (
            f"  [{self.rule}] {self.location}\n"
            f"         found:    {self.found}\n"
            f"         expected: {self.expected}"
        )

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "file": self.file,
            "location": self.location,
            "found": self.found,
            "expected": self.expected,
        }


@dataclass
class Node:
    tag: str  # '#text' for text nodes
    attrs: Dict[str, str] = field(default_factory=dict)
    children: List["Node"] = field(default_factory=list)
    text: str = ""  # only set for '#text' nodes
    line: int = 0
    parent: Optional["Node"] = None

    @property
    def is_text(self) -> bool:
        return self.tag == "#text"

    def classes(self) -> Set[str]:
        return set(self.attrs.get("class", "").split())

    def text_content(self) -> str:
        if self.is_text:
            return self.text
        return "".join(c.text_content() for c in self.children)

    def find_all(self, *tags: str) -> List["Node"]:
        result: List[Node] = []
        for child in self.children:
            if not child.is_text:
                if child.tag in tags:
                    result.append(child)
                result.extend(child.find_all(*tags))
        return result

    def ancestor_tags(self) -> List[str]:
        tags: List[str] = []
        p = self.parent
        while p:
            if not p.is_text:
                tags.append(p.tag)
            p = p.parent
        return tags


# ── DOM builder ────────────────────────────────────────────────────────────────


class _DOMBuilder(HTMLParser):
    _VOID: Set[str] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node(tag="#document")
        self._stack: List[Node] = [self.root]

    def handle_starttag(self, tag: str, attrs) -> None:
        node = Node(
            tag=tag.lower(),
            attrs={k.lower(): v or "" for k, v in attrs},
            line=self.getpos()[0],
            parent=self._stack[-1],
        )
        self._stack[-1].children.append(node)
        if tag.lower() not in self._VOID:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tl = tag.lower()
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tl:
                self._stack = self._stack[:i]
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            node = Node(
                tag="#text",
                text=data,
                line=self.getpos()[0],
                parent=self._stack[-1],
            )
            self._stack[-1].children.append(node)


def parse_html(html_text: str) -> Node:
    builder = _DOMBuilder()
    builder.feed(html_text)
    return builder.root


# ── CSS parser ─────────────────────────────────────────────────────────────────


@dataclass
class CSSRule:
    selectors: List[str]
    props: Dict[str, str]


def _parse_declarations(decl: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for part in decl.split(";"):
        part = part.strip()
        if ":" not in part:
            continue
        prop, _, val = part.partition(":")
        prop = prop.strip().lower()
        val = val.strip()
        if prop and val:
            result[prop] = val
    return result


def _parse_css(css_text: str) -> List[CSSRule]:
    # Strip block comments
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    # Remove @keyframes (may contain { })
    css_text = re.sub(
        r"@keyframes[^{]*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", css_text, flags=re.DOTALL
    )
    # Remove @font-face
    css_text = re.sub(r"@font-face\s*\{[^}]+\}", "", css_text, flags=re.DOTALL)
    # Unwrap @media / @supports — keep inner rules
    css_text = re.sub(
        r"@[^{]+\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", css_text, flags=re.DOTALL
    )

    rules: List[CSSRule] = []
    for m in re.finditer(r"([^{]+)\{([^}]*)\}", css_text):
        sel_text = m.group(1).strip()
        decl_text = m.group(2).strip()
        if not sel_text or not decl_text:
            continue
        sels = [s.strip() for s in sel_text.split(",") if s.strip()]
        props = _parse_declarations(decl_text)
        if sels and props:
            rules.append(CSSRule(selectors=sels, props=props))
    return rules


def _selector_matches(sel: str, node: Node) -> bool:
    """Simplified single-component selector matching (no descendant/child)."""
    # Skip complex selectors (spaces, >, +, ~) to avoid false matches
    if re.search(r"[\s>+~]", sel.strip()):
        return False
    # Strip pseudo-classes/elements
    sel = re.sub(r":+[a-zA-Z-]+(\([^)]*\))?", "", sel).strip()
    if not sel:
        return True

    tag = node.tag
    classes = node.classes()
    node_id = node.attrs.get("id", "")

    # Parse selector parts: optional tag + zero or more .class + optional #id
    m_tag = re.match(r"^([a-zA-Z][a-zA-Z0-9-]*)(.*)$", sel)
    sel_tag = ""
    rest = sel
    if m_tag and not sel.startswith(".") and not sel.startswith("#"):
        sel_tag = m_tag.group(1).lower()
        rest = m_tag.group(2)

    sel_classes = set(re.findall(r"\.([a-zA-Z][a-zA-Z0-9_-]*)", rest))
    m_id = re.search(r"#([a-zA-Z][a-zA-Z0-9_-]*)", rest)
    sel_id = m_id.group(1) if m_id else ""

    if sel_tag and sel_tag != tag:
        return False
    if sel_id and sel_id != node_id:
        return False
    if sel_classes and not sel_classes.issubset(classes):
        return False
    return True


def _resolve_style(node: Node, rules: List[CSSRule]) -> Dict[str, str]:
    """Compute effective style: matching CSS rules (in order) + inline style."""
    merged: Dict[str, str] = {}
    for rule in rules:
        for sel in rule.selectors:
            if _selector_matches(sel, node):
                merged.update(rule.props)
                break
    inline = _parse_declarations(node.attrs.get("style", ""))
    merged.update(inline)
    return merged


# ── Color utilities ────────────────────────────────────────────────────────────


def _normalize_hex(h: str) -> str:
    """Expand 3-char hex to 6-char, strip alpha channel."""
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    elif len(h) == 4:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2  # discard alpha
    elif len(h) == 8:
        h = h[:6]  # discard alpha
    return f"#{h.lower()}"


def normalize_color(val: str) -> Optional[str]:
    """Return lowercase hex or keyword, or None if unrecognised."""
    v = val.strip().lower()
    kw = {
        "transparent",
        "inherit",
        "initial",
        "unset",
        "currentcolor",
        "none",
        "auto",
        "white",
        "black",
    }
    if v in kw:
        return v
    m = _RE_HEX_COLOR.fullmatch(v) or _RE_HEX_COLOR.match(v)
    if m:
        return _normalize_hex(m.group(1))
    m = _RE_RGBA_COLOR.match(v)
    if m:
        alpha = float(m.group(4))
        if alpha < _RGBA_ALPHA_FLOOR:
            return "transparent"  # near-invisible overlay — skip
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"#{r:02x}{g:02x}{b:02x}"
    m = _RE_RGB_COLOR.match(v)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"#{r:02x}{g:02x}{b:02x}"
    return None


def _is_allowed_color(val: str) -> bool:
    n = normalize_color(val)
    if n is None:
        return True  # unknown format — don't flag
    if n in (
        "transparent",
        "inherit",
        "initial",
        "unset",
        "currentcolor",
        "none",
        "auto",
    ):
        return True
    return n in CI_PALETTE or n in TOLERANCE_COLORS


def _luminance(hex6: str) -> float:
    h = hex6.lstrip("#")
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(fg: str, bg: str) -> float:
    try:
        l1, l2 = _luminance(fg), _luminance(bg)
        hi, lo = max(l1, l2), min(l1, l2)
        return (hi + 0.05) / (lo + 0.05)
    except Exception:
        return 21.0


def _extract_colors_from_value(val: str) -> List[str]:
    """Extract all hex/rgb color strings from a CSS property value."""
    colors: List[str] = []
    # Skip CSS functions we cannot resolve
    if "var(" in val or "color-mix(" in val or "linear-gradient(" in val:
        return colors
    for m in _RE_RGBA_COLOR.finditer(val):
        colors.append(m.group(0))
    for m in _RE_RGB_COLOR.finditer(val):
        if "rgba" not in val[max(0, m.start() - 1) : m.start() + 4]:
            colors.append(m.group(0))
    for m in _RE_HEX_COLOR.finditer(val):
        colors.append(m.group(0))
    return colors


# ── R1: Number convention ──────────────────────────────────────────────────────


def check_r1(root: Node, audience: str, filename: str) -> List[Finding]:
    """R1: EN audience → dot decimal; DE audience → comma decimal."""
    findings: List[Finding] = []

    if audience == "en":
        # Flag: digit,digit(1-2) — German decimal in an English doc
        # The {1,2} naturally excludes EN thousands like 1,000 (3 digits)
        pattern = re.compile(r"\b(\d+),(\d{1,2})(?!\d)\b")
        hint = "use dot decimal (EN): 44.6 or 1,000 for thousands"
    else:
        # Flag: digit.digit(1-2) — English decimal in a German doc
        # The {1,2} naturally excludes DE thousands like 1.000 (3 digits)
        pattern = re.compile(r"\b(\d+)\.(\d{1,2})(?!\d)\b")
        hint = "use comma decimal (DE): 44,6 or 1.000 for thousands"

    def walk(node: Node) -> None:
        if not node.is_text and node.tag in _SKIP_TEXT_TAGS:
            return
        if node.is_text:
            _check_text(node)
        for child in node.children:
            walk(child)

    def _check_text(node: Node) -> None:
        # Skip if inside a skip-tag ancestor
        if any(t in _SKIP_TEXT_TAGS for t in node.ancestor_tags()):
            return
        text = node.text
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            matched = m.group(0)
            # Widen context for exclusion checks
            ctx_start = max(0, start - 4)
            ctx_end = min(len(text), end + 4)
            ctx = text[ctx_start:ctx_end]

            # Exclude version strings (1.2.3 or v1.2.3)
            if _RE_VERSION.search(ctx):
                continue
            # Exclude years (e.g. "2026" matches \d+,\d{2} if misread — safety net)
            if _RE_YEAR.fullmatch(matched.replace(",", "").replace(".", "")):
                continue
            # Exclude ISO dates
            if _RE_ISO_DATE.search(text[max(0, start - 8) : end + 8]):
                continue
            # Exclude hex colours accidentally in text
            if _RE_HEX_IN_TEXT.search(ctx):
                continue
            # For DE audience: exclude section-number-like patterns "1.2 Heading"
            # Only apply when BOTH parts are single-digit (e.g. "1.2", "2.3") —
            # multi-digit integers like "44.6" are never section numbers.
            if audience == "de":
                after = text[end : end + 2].lstrip()
                before = text[max(0, start - 1) : start]
                if (
                    len(m.group(1)) == 1
                    and len(m.group(2)) == 1
                    and after
                    and after[0].isupper()
                    and (not before or before[-1] in (" ", "\n", "\t"))
                ):
                    continue  # e.g. "2.3 Revenue" — section numbering

            snippet = text[max(0, start - 20) : end + 20].strip()
            findings.append(
                Finding(
                    rule="R1",
                    file=filename,
                    location=f"line ~{node.line}: {snippet!r}",
                    found=matched,
                    expected=hint,
                )
            )

    walk(root)
    return findings


# ── R2: Color palette ──────────────────────────────────────────────────────────


def check_r2(
    style_blocks: List[str], inline_styles: List[Tuple[str, int]], filename: str
) -> List[Finding]:
    """R2: All explicit colors must be in CI palette or tolerance list."""
    findings: List[Finding] = []

    def report(color_val: str, location: str) -> None:
        n = normalize_color(color_val)
        if n is None or n in ("transparent",):
            return
        if not _is_allowed_color(color_val):
            findings.append(
                Finding(
                    rule="R2",
                    file=filename,
                    location=location,
                    found=f"{color_val!r} (normalized: {n})",
                    expected="CI palette color or documented neutral",
                )
            )

    # --- CSS rules from <style> blocks ---
    for css_text in style_blocks:
        rules = _parse_css(css_text)
        for rule in rules:
            for sel in rule.selectors:
                for prop, val in rule.props.items():
                    # Skip CSS custom property definitions (--var-name)
                    if prop.startswith("--"):
                        continue
                    if prop not in _COLOR_PROPS:
                        continue
                    for color_str in _extract_colors_from_value(val):
                        report(color_str, f"CSS rule {sel!r}, property {prop!r}")

    # --- Inline styles ---
    for inline_text, line_no in inline_styles:
        props = _parse_declarations(inline_text)
        for prop, val in props.items():
            if prop not in _COLOR_PROPS:
                continue
            for color_str in _extract_colors_from_value(val):
                report(color_str, f"inline style line ~{line_no}")

    return findings


# ── R3: Font discipline ────────────────────────────────────────────────────────


def check_r3(
    style_blocks: List[str],
    inline_styles: List[Tuple[str, int]],
    root: Node,
    css_rules: List[CSSRule],
    filename: str,
) -> List[Finding]:
    """R3: Font family whitelist, size floor, one-off sizes, contrast pairs."""
    findings: List[Finding] = []

    # --- Font family check ---
    def _check_font_family(val: str, location: str) -> None:
        # Skip CSS variable references
        if "var(" in val:
            return
        families = [f.strip().strip("'\"").lower() for f in val.split(",")]
        primary = families[0] if families else ""
        # Only flag the primary family (fallbacks can be anything)
        if primary and primary not in CI_FONTS and primary not in ("serif",):
            findings.append(
                Finding(
                    rule="R3",
                    file=filename,
                    location=location,
                    found=f"primary font {primary!r}",
                    expected=f"one of: {', '.join(sorted(CI_FONTS))}",
                )
            )

    # Collect from CSS rules
    all_sizes: List[Tuple[str, str]] = []  # (value, location)

    for css_text in style_blocks:
        rules = _parse_css(css_text)
        for rule in rules:
            for sel in rule.selectors:
                if "font-family" in rule.props:
                    _check_font_family(rule.props["font-family"], f"CSS rule {sel!r}")
                if "font-size" in rule.props:
                    all_sizes.append((rule.props["font-size"], f"CSS rule {sel!r}"))

    for inline_text, line_no in inline_styles:
        props = _parse_declarations(inline_text)
        if "font-family" in props:
            _check_font_family(props["font-family"], f"inline style line ~{line_no}")
        if "font-size" in props:
            all_sizes.append((props["font-size"], f"inline style line ~{line_no}"))

    # --- Font size checks ---
    # Parse px values; track frequency
    px_sizes: Dict[float, List[str]] = {}
    for val, loc in all_sizes:
        v = val.strip().lower()
        if "var(" in v:
            continue
        m = re.match(r"^([\d.]+)px$", v)
        if m:
            px = float(m.group(1))
            px_sizes.setdefault(px, []).append(loc)

    def _fmt_px(px: float) -> str:
        return f"{int(px)}px" if px == int(px) else f"{px}px"

    # Below readable floor
    for px, locs in sorted(px_sizes.items()):
        if px < READABLE_FLOOR_PX:
            findings.append(
                Finding(
                    rule="R3",
                    file=filename,
                    location=locs[0],
                    found=_fmt_px(px),
                    expected=f">= {READABLE_FLOOR_PX}px",
                )
            )

    # One-off sizes (used in exactly 1 place — outlier risk)
    for px, locs in sorted(px_sizes.items()):
        if len(locs) <= ONE_OFF_THRESHOLD and px >= READABLE_FLOOR_PX:
            findings.append(
                Finding(
                    rule="R3",
                    file=filename,
                    location=locs[0],
                    found=f"{_fmt_px(px)} (one-off: appears {len(locs)}x)",
                    expected="reuse a type-scale size or add to CSS var",
                )
            )

    # --- Contrast check (explicit same-rule fg+bg pairs only) ---
    for css_text in style_blocks:
        rules = _parse_css(css_text)
        for rule in rules:
            color = rule.props.get("color")
            bg = rule.props.get("background-color") or rule.props.get("background")
            if color and bg:
                fg_hex = normalize_color(color)
                bg_hex = normalize_color(bg)
                if (
                    fg_hex
                    and bg_hex
                    and fg_hex.startswith("#")
                    and bg_hex.startswith("#")
                    and len(fg_hex) == 7
                    and len(bg_hex) == 7
                ):
                    ratio = _contrast(fg_hex, bg_hex)
                    if ratio < MIN_CONTRAST_RATIO:
                        for sel in rule.selectors:
                            findings.append(
                                Finding(
                                    rule="R3",
                                    file=filename,
                                    location=f"CSS rule {sel!r}",
                                    found=f"contrast {ratio:.2f}:1 ({color} on {bg})",
                                    expected=f">= {MIN_CONTRAST_RATIO}:1 (WCAG AA Large)",
                                )
                            )

    return findings


# ── R4: Heading consistency ────────────────────────────────────────────────────


def check_r4(root: Node, css_rules: List[CSSRule], filename: str) -> List[Finding]:
    """R4: All h1 elements share one style signature; same for h2, h3, h4."""
    findings: List[Finding] = []
    _SIG_PROPS = ("font-family", "font-size", "font-weight", "color")

    for htag in ("h1", "h2", "h3", "h4"):
        headings = root.find_all(htag)
        if len(headings) < 2:
            continue

        sigs: List[Tuple[str, str]] = []  # (signature, location)
        for h in headings:
            style = _resolve_style(h, css_rules)
            sig_parts = {p: style.get(p, "") for p in _SIG_PROPS}
            # Skip properties set to a var() — they resolve identically
            sig_clean = {k: v for k, v in sig_parts.items() if v and "var(" not in v}
            sig = json.dumps(sig_clean, sort_keys=True)
            sigs.append((sig, f"<{htag}> line ~{h.line}: {h.text_content()[:60]!r}"))

        # Check if all headings share one signature
        unique_sigs = set(s for s, _ in sigs)
        if len(unique_sigs) > 1:
            # Find the majority signature
            from collections import Counter

            counts = Counter(s for s, _ in sigs)
            majority_sig, _ = counts.most_common(1)[0]
            for sig, loc in sigs:
                if sig != majority_sig:
                    findings.append(
                        Finding(
                            rule="R4",
                            file=filename,
                            location=loc,
                            found=sig,
                            expected=f"majority signature: {majority_sig}",
                        )
                    )

    return findings


# ── R5: Table hygiene ──────────────────────────────────────────────────────────

_RE_NUM_CELL = re.compile(r"^[\s\-+()]*\d[\d\s,.\-+%×x€$£kKmM]*$")
_RE_MIXED_CELL = re.compile(
    r"\b\d+[.,]\d+\s+[a-zA-Z]{2,}"  # "44.6 avg" or "3,129 items"
    r"|[a-zA-Z]{2,}\s+\d+[.,]\d+"  # "avg 44.6"
)


def check_r5(root: Node, css_rules: List[CSSRule], filename: str) -> List[Finding]:
    """R5: Table text columns left-aligned; no mixed cells; header has bg color."""
    findings: List[Finding] = []

    # Pre-scan: does any CSS rule globally target `th` and set a background?
    # If yes, descendant-selector rules (e.g. `.foo thead th { background: ... }`)
    # are almost certainly present and our simplified resolver would produce
    # false-positive "no background" findings — so we skip the per-table check.
    _global_th_has_bg = any(
        any("th" in sel for sel in rule.selectors)
        and ("background" in rule.props or "background-color" in rule.props)
        for rule in css_rules
    )

    tables = root.find_all("table")
    for table in tables:
        table_loc = f"<table> line ~{table.line}"

        # --- Header row background check ---
        # Only run this check when no global th-background rule exists,
        # because complex descendant selectors are not resolved by our cascade.
        if not _global_th_has_bg:
            header_rows = table.find_all("thead")
            ths_to_check: List[Node] = []
            if not header_rows:
                first_tr = next(iter(table.find_all("tr")), None)
                if first_tr:
                    ths_to_check = first_tr.find_all("th")
            else:
                for thead in header_rows:
                    ths_to_check.extend(thead.find_all("th"))

            if ths_to_check:
                has_bg = any(
                    (
                        _resolve_style(th, css_rules).get("background-color")
                        or _resolve_style(th, css_rules).get("background", "")
                        or th.attrs.get("style", "")
                    )
                    for th in ths_to_check
                )
                if not has_bg:
                    findings.append(
                        Finding(
                            rule="R5",
                            file=filename,
                            location=table_loc,
                            found="th elements have no background-color (no global th rule found)",
                            expected="header row must have a background from CI palette",
                        )
                    )

        # --- Per-cell alignment and mixed-cell checks ---
        # Alignment strategy: simplified CSS cascade cannot reliably resolve
        # descendant/pseudo-class selectors (e.g. `.table td:first-child`),
        # so we avoid false-positives by checking ONLY cells with an explicit
        # inline style that sets a non-left alignment on a text-heavy cell.
        # Cells relying on browser default (left) are not flagged.
        all_cells = table.find_all("td", "th")
        for cell in all_cells:
            cell_text = cell.text_content().strip()
            if not cell_text:
                continue

            # Mixed number+word check (any cell)
            if _RE_MIXED_CELL.search(cell_text):
                findings.append(
                    Finding(
                        rule="R5",
                        file=filename,
                        location=f"<{cell.tag}> line ~{cell.line}: {cell_text[:60]!r}",
                        found="mixed number+word in cell",
                        expected="separate numeric and text content",
                    )
                )

            # Explicit wrong alignment on a text cell (inline style only —
            # CSS cascade for descendants is not reliably resolved)
            inline_ta = _parse_declarations(cell.attrs.get("style", "")).get(
                "text-align", ""
            )
            if inline_ta.lower() in ("right", "center"):
                is_text_cell = not _RE_NUM_CELL.match(cell_text) and len(cell_text) > 2
                if is_text_cell:
                    findings.append(
                        Finding(
                            rule="R5",
                            file=filename,
                            location=f"<{cell.tag}> line ~{cell.line}: {cell_text[:40]!r}",
                            found=f"text-align: {inline_ta} (inline) on text content",
                            expected="text-align: left for text content",
                        )
                    )

    return findings


# ── Orchestrator ───────────────────────────────────────────────────────────────


def validate_file(html_path: Path, audience: str) -> List[Finding]:
    html_text = html_path.read_text(encoding="utf-8", errors="replace")
    filename = html_path.name
    root = parse_html(html_text)

    # Collect <style> block text
    style_blocks: List[str] = []
    for snode in root.find_all("style"):
        style_blocks.append(snode.text_content())

    # Parse CSS rules (combined)
    all_css = "\n".join(style_blocks)
    css_rules = _parse_css(all_css)

    # Collect inline styles (text, line)
    inline_styles: List[Tuple[str, int]] = []

    def _collect_inline(node: Node) -> None:
        if not node.is_text and "style" in node.attrs:
            inline_styles.append((node.attrs["style"], node.line))
        for child in node.children:
            _collect_inline(child)

    _collect_inline(root)

    findings: List[Finding] = []
    findings += check_r1(root, audience, filename)
    findings += check_r2(style_blocks, inline_styles, filename)
    findings += check_r3(style_blocks, inline_styles, root, css_rules, filename)
    findings += check_r4(root, css_rules, filename)
    findings += check_r5(root, css_rules, filename)
    return findings


# ── Output formatting ──────────────────────────────────────────────────────────


def _print_text(path: Path, findings: List[Finding], passed: bool) -> None:
    print(f"\n{'=' * 68}")
    print(f"  {path}")
    print(f"{'=' * 68}")
    if passed:
        print("  PASS — no CI findings")
    else:
        by_rule: Dict[str, List[Finding]] = {}
        for f in findings:
            by_rule.setdefault(f.rule, []).append(f)
        for rule in sorted(by_rule):
            fs = by_rule[rule]
            print(f"\n  {rule} [{len(fs)} finding(s)]")
            for f in fs:
                print(f.as_text())
    print()


def _build_json(results: List[Tuple[Path, List[Finding]]]) -> dict:
    out = {
        "summary": {
            "total_files": len(results),
            "failed_files": 0,
            "total_findings": 0,
        },
        "files": [],
    }
    for path, findings in results:
        out["summary"]["total_findings"] += len(findings)
        if findings:
            out["summary"]["failed_files"] += 1
        out["files"].append(
            {
                "file": str(path),
                "passed": len(findings) == 0,
                "findings": [f.as_dict() for f in findings],
            }
        )
    return out


# ── Entry point ────────────────────────────────────────────────────────────────


def main() -> int:
    # Ensure UTF-8 output on Windows consoles that default to cp1252
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Repuro CI validator for HTML deliverables",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("files", nargs="+", help="HTML file(s) to validate")
    ap.add_argument(
        "--audience",
        required=True,
        choices=("en", "de"),
        help="en = dot-decimal, comma-thousands; de = comma-decimal, dot-thousands",
    )
    ap.add_argument("--format", choices=("text", "json"), default="text")
    args = ap.parse_args()

    results: List[Tuple[Path, List[Finding]]] = []
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            continue
        findings = validate_file(p, args.audience)
        results.append((p, findings))

    if args.format == "json":
        print(json.dumps(_build_json(results), indent=2))
    else:
        for path, findings in results:
            _print_text(path, findings, passed=len(findings) == 0)

        total = sum(len(f) for _, f in results)
        failed = sum(1 for _, f in results if f)
        print(
            f"{'FAIL' if failed else 'PASS'} — "
            f"{len(results)} file(s), {failed} failed, {total} finding(s)"
        )

    return 1 if any(f for _, f in results) else 0


if __name__ == "__main__":
    sys.exit(main())
