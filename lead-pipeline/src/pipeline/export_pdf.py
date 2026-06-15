"""PDF Serienbrief generator (M22). Single PDF with all approved letters."""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from fpdf import FPDF

from src.config import settings

logger = logging.getLogger(__name__)

# ── Completeness gate — required fields for a renderable letter ─────────
REQUIRED_LETTER_FIELDS = [
    "name_briefkopf",
    "anrede",
    "salutation",
    "street",
    "plz_ort",
    "leistung_text",
    "region_prep",
    "compliment_draft",
    "compliment_2",
    "mehrwerte",
]


def check_record_completeness(record_data: dict) -> list[str]:
    """Return list of missing field names for a letter record.

    A field is 'missing' if its value is falsy or is a [placeholder].
    """
    missing = []
    for field in REQUIRED_LETTER_FIELDS:
        val = record_data.get(field)
        if not val or not str(val).strip() or str(val).strip().startswith("["):
            missing.append(field)
    return missing


# ── Layout constants (mm), matching Word template on A4 ──────────────────
PAGE_W, PAGE_H = 210, 297
MARGIN_LEFT = 25
MARGIN_RIGHT = 25
MARGIN_TOP = 23
MARGIN_BOTTOM = 13
CONTENT_W = PAGE_W - MARGIN_LEFT - MARGIN_RIGHT  # 160 mm
MAX_CONTENT_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM  # 261 mm

LOGO_WIDTH_MM = 35
HEADER_Y = 8  # mm from page top
BODY_FONT_SIZE = 11
BODY_LINE_H = 5.0  # mm per line
HEADER_FONT_SIZE = 8
HEADER_LINE_H = 3.5
SIGNATURE_TITLE_SIZE = 9

# ── Font paths (Windows system fonts) ────────────────────────────────────
_WIN_FONTS = Path("C:/Windows/Fonts")
_LOCAL_FONTS = settings.BASE_DIR / "data" / "fonts"

# ── Default sender (used when sender.json is missing) ────────────────────
_DEFAULT_SENDER: dict = {
    "company_name": "Repuro GmbH",
    "logo_path": "data/input/_header_logo.png",
    "address_lines": [
        "Repuro GmbH",
        "Goethestraße 59",
        "10625 Berlin",
        "info@repuro.de",
        "www.repuro.de",
    ],
    "signatures": [
        {"name": "Florian Fischer", "title": "Geschäftsführer"},
        {"name": "Roman Dobriakov", "title": "Geschäftsführer"},
    ],
    "city": "Berlin",
}


# ── Sender config ────────────────────────────────────────────────────────
def load_sender_config() -> dict:
    """Load client sender config from sender.json, with defaults fallback."""
    cfg_path = settings.SENDER_CONFIG_PATH
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        # Merge with defaults for any missing keys
        merged = {**_DEFAULT_SENDER, **cfg}
        return merged
    logger.warning("sender.json not found at %s — using defaults", cfg_path)
    return dict(_DEFAULT_SENDER)


# ── Template parsing ─────────────────────────────────────────────────────
@dataclass
class LetterBlock:
    """One logical section of the letter template."""

    block_type: str  # address, date, subject, paragraph, signatures
    text: str


def parse_letter_template(template_path: Path) -> list[LetterBlock]:
    """Parse letter_template.html into ordered LetterBlocks.

    Reads the file fresh each call so edits are reflected immediately.
    Strips HTML tags, decodes entities, preserves {{merge_fields}}.
    """
    raw = template_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")

    blocks: list[LetterBlock] = []
    for div in soup.find_all("div", recursive=False):
        style = div.get("style", "")
        text = html_mod.unescape(div.get_text(separator="\n").strip())

        if not text:
            continue

        # Detect block type from style attributes
        if "display:flex" in style.replace(" ", "") or "display: flex" in style:
            # Signature block — parse child divs
            blocks.append(LetterBlock("signatures", text))
        elif "font-weight:700" in style.replace(" ", "") or "font-weight: 700" in style:
            blocks.append(LetterBlock("subject", text))
        elif (
            "text-align:right" in style.replace(" ", "") or "text-align: right" in style
        ):
            blocks.append(LetterBlock("date", text))
        elif "{{street}}" in text or "{{plz_ort}}" in text:
            blocks.append(LetterBlock("address", text))
        else:
            blocks.append(LetterBlock("paragraph", text))

    return blocks


# ── Merge field handling ─────────────────────────────────────────────────
_FIELD_RE = re.compile(r"\{\{(\w+)\}\}")


def _fill_merge_fields(text: str, data: dict) -> str:
    """Replace {{field}} placeholders with values. Missing → [field]."""

    def replacer(m: re.Match) -> str:
        key = m.group(1)
        val = data.get(key)
        return str(val) if val else f"[{key}]"

    return _FIELD_RE.sub(replacer, text)


def _parse_name(full_name: Optional[str]) -> tuple[str, str]:
    """Split 'Vorname Nachname' -> (first, last)."""
    if not full_name:
        return "", ""
    parts = full_name.strip().split()
    if len(parts) == 1:
        return "", parts[0]
    return parts[0], " ".join(parts[1:])


_GERMAN_MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


def _format_date_de(dt: datetime) -> str:
    return f"{dt.day}. {_GERMAN_MONTHS[dt.month - 1]} {dt.year}"


def _build_record_data(raw: dict, sender_config: dict) -> dict:
    """Map a raw DB row dict to the merge field dict used by the template."""
    owner = raw.get("owner_name") or ""
    first, last = _parse_name(owner)
    return {
        "name_briefkopf": raw.get("impressum_name") or raw.get("full_name") or "",
        "anrede": raw.get("anrede") or "",
        "vorname": first,
        "nachname": last,
        "street": raw.get("street") or "",
        "plz_ort": raw.get("plz_ort") or "",
        "datum": _format_date_de(datetime.now()),
        "salutation": raw.get("salutation") or "",
        "leistung_text": raw.get("leistung_text") or "",
        "region_prep": raw.get("region_prep") or "",
        "compliment_draft": raw.get("compliment_draft") or "",
        "compliment_2": raw.get("compliment_2") or "",
        "leistung_absatz_2": raw.get("leistung_absatz_2") or "",
        "mehrwerte": raw.get("mehrwerte") or "",
    }


# ── Height estimation (overflow detection) ───────────────────────────────
def estimate_letter_height(
    pdf: "RepuroLetterPDF",
    blocks: list[LetterBlock],
    record_data: dict,
) -> float:
    """Estimate total height (mm) a letter would occupy, WITHOUT rendering.

    Uses fpdf's get_string_width to compute line wraps for multi_cell blocks.
    """
    total_h = 0.0
    for block in blocks:
        text = _fill_merge_fields(block.text, record_data)
        if block.block_type == "address":
            lines = [l for l in text.split("\n") if l.strip()]
            total_h += len(lines) * BODY_LINE_H + 4
        elif block.block_type == "date":
            total_h += BODY_LINE_H + 8
        elif block.block_type == "subject":
            pdf.set_font("Arial", "B", BODY_FONT_SIZE)
            n_lines = _count_wrapped_lines(pdf, text, CONTENT_W)
            total_h += n_lines * BODY_LINE_H + 3
        elif block.block_type == "signatures":
            total_h += 6 + BODY_LINE_H + 4
        else:  # paragraph
            pdf.set_font("Arial", "", BODY_FONT_SIZE)
            n_lines = _count_wrapped_lines(pdf, text, CONTENT_W)
            total_h += n_lines * BODY_LINE_H + 2.5
    return total_h


def _count_wrapped_lines(pdf: FPDF, text: str, max_w: float) -> int:
    """Count how many lines text will wrap to within max_w mm."""
    words = text.split()
    if not words:
        return 1
    lines = 1
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        if pdf.get_string_width(test) > max_w:
            lines += 1
            current_line = word
        else:
            current_line = test
    return lines


def check_overflow(
    raw_rows: dict[str, dict],
    blocks: list[LetterBlock],
    sender_config: dict,
) -> list[str]:
    """Return list of domains whose letters would overflow one A4 page."""
    pdf = RepuroLetterPDF(sender_config)
    pdf.add_page()  # needed to initialise font metrics

    overflow_domains = []
    for domain, raw in raw_rows.items():
        data = _build_record_data(raw, sender_config)
        h = estimate_letter_height(pdf, blocks, data)
        if h > MAX_CONTENT_H:
            logger.warning(
                "Overflow: %s needs %.0fmm (max %.0fmm)", domain, h, MAX_CONTENT_H
            )
            overflow_domains.append(domain)
    return overflow_domains


# ── PDF class ────────────────────────────────────────────────────────────
def _resolve_font_path(name: str) -> Path:
    """Find a font file, preferring local copy over Windows system."""
    local = _LOCAL_FONTS / name
    if local.exists():
        return local
    system = _WIN_FONTS / name
    if system.exists():
        # Copy to local dir to avoid permission issues with font cache
        _LOCAL_FONTS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(system, local)
        return local
    raise FileNotFoundError(f"Font not found: {name} (checked {local}, {system})")


class RepuroLetterPDF(FPDF):
    """FPDF subclass with configurable letter header (logo + sender address)."""

    def __init__(self, sender_config: dict):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._sender = sender_config
        self._logo_path = self._resolve_logo()
        self._in_letter = False
        self.set_auto_page_break(auto=False)  # we manage page breaks ourselves

        # Register Arial as Unicode font
        regular = _resolve_font_path("arial.ttf")
        bold = _resolve_font_path("arialbd.ttf")
        self.add_font("Arial", "", str(regular))
        self.add_font("Arial", "B", str(bold))

    def _resolve_logo(self) -> Optional[Path]:
        logo_rel = self._sender.get("logo_path", "")
        if not logo_rel:
            return None
        p = settings.BASE_DIR / logo_rel
        if p.exists():
            return p
        logger.warning("Letter logo not found at %s", p)
        return None

    def header(self) -> None:
        """Draw logo top-left + sender address top-right."""
        if not self._in_letter:
            return
        # Logo
        if self._logo_path:
            self.image(
                str(self._logo_path),
                x=(PAGE_W - LOGO_WIDTH_MM) / 2,
                y=HEADER_Y,
                w=LOGO_WIDTH_MM,
            )
        # Sender address (right-aligned)
        self.set_font("Arial", "", HEADER_FONT_SIZE)
        addr = self._sender.get("address_lines", [])
        addr_w = 50
        x_right = PAGE_W - MARGIN_RIGHT - addr_w
        for i, line in enumerate(addr):
            self.set_xy(x_right, HEADER_Y + i * HEADER_LINE_H)
            self.cell(addr_w, HEADER_LINE_H, line, align="R")


# ── Letter rendering ─────────────────────────────────────────────────────
def render_letter(
    pdf: RepuroLetterPDF,
    blocks: list[LetterBlock],
    record_data: dict,
    sender_config: dict,
) -> None:
    """Render one complete letter onto the PDF."""
    pdf._in_letter = True
    pdf.add_page()
    pdf.set_left_margin(MARGIN_LEFT)
    pdf.set_right_margin(MARGIN_RIGHT)
    pdf.set_y(MARGIN_TOP)

    for block in blocks:
        text = _fill_merge_fields(block.text, record_data)

        if block.block_type == "address":
            pdf.set_font("Arial", "", BODY_FONT_SIZE)
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped:
                    pdf.set_x(MARGIN_LEFT)
                    pdf.cell(CONTENT_W, BODY_LINE_H, stripped)
                    pdf.ln(BODY_LINE_H)
            pdf.ln(4)

        elif block.block_type == "date":
            pdf.set_font("Arial", "", BODY_FONT_SIZE)
            pdf.set_x(MARGIN_LEFT)
            pdf.cell(CONTENT_W, BODY_LINE_H, text.strip(), align="R")
            pdf.ln(8)

        elif block.block_type == "subject":
            pdf.set_font("Arial", "B", BODY_FONT_SIZE)
            pdf.set_x(MARGIN_LEFT)
            pdf.multi_cell(CONTENT_W, BODY_LINE_H, text.strip())
            pdf.ln(3)

        elif block.block_type == "signatures":
            sigs = sender_config.get("signatures", [])
            pdf.ln(6)
            pdf.set_font("Arial", "", BODY_FONT_SIZE)
            pdf.set_x(MARGIN_LEFT)
            if len(sigs) >= 2:
                pdf.cell(CONTENT_W / 2, BODY_LINE_H, sigs[0]["name"])
                pdf.cell(CONTENT_W / 2, BODY_LINE_H, sigs[1]["name"], align="R")
                pdf.ln(BODY_LINE_H)
                pdf.set_font("Arial", "", SIGNATURE_TITLE_SIZE)
                pdf.set_x(MARGIN_LEFT)
                pdf.cell(CONTENT_W / 2, 4, sigs[0]["title"])
                pdf.cell(CONTENT_W / 2, 4, sigs[1]["title"], align="R")
            elif len(sigs) == 1:
                pdf.cell(CONTENT_W, BODY_LINE_H, sigs[0]["name"])
                pdf.ln(BODY_LINE_H)
                pdf.set_font("Arial", "", SIGNATURE_TITLE_SIZE)
                pdf.set_x(MARGIN_LEFT)
                pdf.cell(CONTENT_W, 4, sigs[0]["title"])

        else:  # paragraph / opening / closing
            pdf.set_font("Arial", "", BODY_FONT_SIZE)
            pdf.set_x(MARGIN_LEFT)
            pdf.multi_cell(CONTENT_W, BODY_LINE_H, text.strip())
            pdf.ln(2.5)


# ── CLI entry point ──────────────────────────────────────────────────────
def export_pdf_cmd(
    dry_run: bool = False,
    approved_only: bool = False,
    db_path: Optional[Path] = None,
    domain_filter: Optional[list[str]] = None,
) -> Optional[Path]:
    """Generate a single PDF with all exportable letters.

    Returns the output path, or None on dry-run / no records / overflow error.
    """
    from src.pipeline.export import _fetch_exportable_records

    if db_path is None:
        db_path = settings.PIPELINE_DB_PATH

    records, raw_rows = _fetch_exportable_records(db_path, approved_only)
    if domain_filter:
        domain_set = set(domain_filter)
        records = [r for r in records if r.domain in domain_set]
        raw_rows = {k: v for k, v in raw_rows.items() if k in domain_set}

    if not records:
        logger.warning("PDF export: no records to export")
        return None

    logger.info("PDF export: %d records eligible", len(records))

    sender = load_sender_config()
    template_path = Path(__file__).parent.parent / "config" / "letter_template.html"
    blocks = parse_letter_template(template_path)

    # ── Completeness gate ───────────────────────────────────────────
    skipped: dict[str, list[str]] = {}
    complete_records = []
    for rec in records:
        raw = raw_rows.get(rec.domain, {})
        data = _build_record_data(raw, sender)
        missing = check_record_completeness(data)
        if missing:
            skipped[rec.domain] = missing
            logger.info("PDF skip: %s — missing: %s", rec.domain, ", ".join(missing))
        else:
            complete_records.append(rec)

    if skipped:
        logger.warning(
            "PDF export: skipped %d/%d records (incomplete fields)",
            len(skipped),
            len(records),
        )
        for domain, fields in skipped.items():
            logger.info("  %s: %s", domain, ", ".join(fields))

    if not complete_records:
        logger.warning("PDF export: ALL records skipped — no complete letters")
        return None

    # ── Overflow pre-check (only on complete records) ────────────────
    complete_raw = {
        rec.domain: raw_rows.get(rec.domain, {}) for rec in complete_records
    }
    overflow = check_overflow(complete_raw, blocks, sender)
    if overflow:
        logger.error(
            "PDF export BLOCKED — %d letter(s) overflow one page: %s",
            len(overflow),
            ", ".join(overflow),
        )
        return None

    if dry_run:
        logger.info(
            "DRY RUN — would generate PDF for %d records (%d skipped)",
            len(complete_records),
            len(skipped),
        )
        return None

    # ── Render ────────────────────────────────────────────────────────
    pdf = RepuroLetterPDF(sender)
    for rec in complete_records:
        raw = raw_rows.get(rec.domain, {})
        data = _build_record_data(raw, sender)
        render_letter(pdf, blocks, data, sender)

    date_str = datetime.now().strftime("%Y%m%d")
    out_path = settings.DATA_OUTPUT_DIR / f"serienbriefe_{date_str}.pdf"
    settings.DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))

    logger.info(
        "PDF export: %d letters → %s (%d skipped)",
        len(complete_records),
        out_path,
        len(skipped),
    )
    return out_path
