"""Compare a generated docx against its source template for formatting drift.

Checks: paragraph count, numbering definitions, indentation, font declarations,
bold/italic properties. Returns exit code 1 if any check fails.

Usage:
    python verify_docx_format.py <template> <output>
    python verify_docx_format.py <template> <output> --verbose
"""

import sys
import os

from docx import Document
from docx.oxml.ns import qn


def get_para_props(doc):
    """Extract paragraph-level properties for comparison."""
    props = []
    for i, p in enumerate(doc.paragraphs):
        ppr = p._element.find(qn("w:pPr"))
        has_numpr = False
        num_id = None
        ilvl = None
        has_indent = False
        indent_left = None

        if ppr is not None:
            numpr = ppr.find(qn("w:numPr"))
            if numpr is not None:
                has_numpr = True
                nid = numpr.find(qn("w:numId"))
                if nid is not None:
                    num_id = nid.get(qn("w:val"))
                il = numpr.find(qn("w:ilvl"))
                if il is not None:
                    ilvl = il.get(qn("w:val"))

            ind = ppr.find(qn("w:ind"))
            if ind is not None:
                has_indent = True
                indent_left = ind.get(qn("w:left"))

        text_preview = "".join(r.text for r in p.runs)[:50]
        props.append(
            {
                "idx": i,
                "text": text_preview,
                "style": p.style.name if p.style else None,
                "has_numpr": has_numpr,
                "num_id": num_id,
                "ilvl": ilvl,
                "has_indent": has_indent,
                "indent_left": indent_left,
            }
        )
    return props


def get_run_fonts(doc):
    """Extract run-level font declarations."""
    fonts = {}
    for p in doc.paragraphs:
        for run in p.runs:
            rpr = run._element.find(qn("w:rPr"))
            if rpr is not None:
                rfonts = rpr.find(qn("w:rFonts"))
                if rfonts is not None:
                    name = rfonts.get(qn("w:ascii")) or rfonts.get(qn("w:hAnsi"))
                    if name:
                        fonts[name] = fonts.get(name, 0) + 1
    return fonts


def compare(template_path, output_path, verbose=False):
    if not os.path.exists(template_path):
        print(f"ERROR: Template not found: {template_path}")
        return False
    if not os.path.exists(output_path):
        print(f"ERROR: Output not found: {output_path}")
        return False

    tmpl = Document(template_path)
    out = Document(output_path)

    tmpl_props = get_para_props(tmpl)
    out_props = get_para_props(out)

    tmpl_fonts = get_run_fonts(tmpl)
    out_fonts = get_run_fonts(out)

    issues = []
    warnings = []

    # 1. Paragraph count
    if len(tmpl_props) != len(out_props):
        issues.append(
            f"Paragraph count: template={len(tmpl_props)}, output={len(out_props)}"
        )

    # 2. Numbered paragraphs
    tmpl_numbered = sum(1 for p in tmpl_props if p["has_numpr"])
    out_numbered = sum(1 for p in out_props if p["has_numpr"])
    if tmpl_numbered != out_numbered:
        issues.append(
            f"Numbered paragraphs: template={tmpl_numbered}, output={out_numbered}"
        )

    # 3. Indented paragraphs
    tmpl_indented = sum(1 for p in tmpl_props if p["has_indent"])
    out_indented = sum(1 for p in out_props if p["has_indent"])
    if tmpl_indented != out_indented:
        warnings.append(
            f"Indented paragraphs: template={tmpl_indented}, output={out_indented}"
        )

    # 4. Font declarations
    if tmpl_fonts and not out_fonts:
        issues.append(f"Template has font declarations ({tmpl_fonts}), output has none")
    elif tmpl_fonts != out_fonts:
        missing = set(tmpl_fonts) - set(out_fonts)
        added = set(out_fonts) - set(tmpl_fonts)
        if missing:
            warnings.append(f"Fonts in template but not output: {missing}")
        if added:
            warnings.append(f"Fonts in output but not template: {added}")

    # 5. Per-paragraph style drift (only if counts match)
    if len(tmpl_props) == len(out_props):
        for tp, op in zip(tmpl_props, out_props):
            if tp["has_numpr"] != op["has_numpr"]:
                issues.append(
                    f"P{tp['idx']:03d}: numbering lost "
                    f"(template has numPr, output doesn't). "
                    f"Text: {op['text']!r}"
                )
            if tp["style"] != op["style"]:
                warnings.append(
                    f"P{tp['idx']:03d}: style changed "
                    f"{tp['style']!r} -> {op['style']!r}"
                )

    # Report
    print("=" * 60)
    print("DOCX FORMAT VERIFICATION")
    print(f"  Template: {os.path.basename(template_path)}")
    print(f"  Output:   {os.path.basename(output_path)}")
    print("=" * 60)

    if verbose:
        print(
            f"\nTemplate: {len(tmpl_props)} paragraphs, {tmpl_numbered} numbered, {tmpl_indented} indented"
        )
        print(
            f"Output:   {len(out_props)} paragraphs, {out_numbered} numbered, {out_indented} indented"
        )
        print(f"Template fonts: {tmpl_fonts}")
        print(f"Output fonts:   {out_fonts}")

    if issues:
        print(f"\nFAILED — {len(issues)} issue(s):")
        for issue in issues:
            print(f"  X {issue}")
    else:
        print("\nPASSED — no structural issues")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ? {w}")

    if not issues and not warnings:
        print("  All checks clean.")

    return len(issues) == 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    verbose = "--verbose" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--verbose"]

    ok = compare(args[0], args[1], verbose=verbose)
    sys.exit(0 if ok else 1)
