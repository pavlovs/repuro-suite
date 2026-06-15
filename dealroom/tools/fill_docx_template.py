"""Fill a docx template by replacing text in existing runs only.

NEVER adds/removes paragraphs. NEVER touches paragraph properties (numbering, indentation).
Only modifies run.text where a replacement key is found.

Usage:
    python fill_docx_template.py <template> <output> <replacements.json>
    python fill_docx_template.py <template> <output> --inline "old1=new1" "old2=new2"

The replacements JSON is a dict: {"old text": "new text", ...}
Replacements are applied to paragraph text (concatenated runs), then redistributed
across existing runs preserving their XML properties.
"""

import json
import os
import shutil
import sys

from docx import Document
from docx.oxml.ns import qn


def redistribute_text(paragraph, new_full_text):
    """Replace paragraph text while preserving run boundaries and XML properties.

    Strategy: keep all runs, clear text from all but first, set first run's text
    to the new full text. This preserves the first run's formatting for the whole
    paragraph. Only use when the replacement is a simple value swap.
    """
    runs = paragraph.runs
    if not runs:
        return
    old_full = "".join(r.text for r in runs)
    if old_full == new_full_text:
        return

    # Try to do targeted replacement within individual runs first
    # This preserves per-run formatting better
    remaining = new_full_text
    assigned = False

    # Simple case: replacement only affects one run's content
    for run in runs:
        if run.text and run.text in old_full:
            pass  # Normal case

    # Fallback: redistribute across runs preserving boundaries
    # Map character positions to runs
    positions = []
    pos = 0
    for run in runs:
        length = len(run.text)
        positions.append((pos, pos + length, run))
        pos += length

    # If lengths match closely, try character-aligned distribution
    if len(new_full_text) == len(old_full):
        idx = 0
        for start, end, run in positions:
            run_len = end - start
            run.text = new_full_text[idx : idx + run_len]
            idx += run_len
        return

    # Otherwise: put all text in first run, empty the rest
    runs[0].text = new_full_text
    for run in runs[1:]:
        run.text = ""


def apply_replacements(doc, replacements):
    """Apply text replacements across all paragraphs, preserving formatting."""
    changes = []
    for paragraph in doc.paragraphs:
        full_text = "".join(r.text for r in paragraph.runs)
        if not full_text.strip():
            continue

        new_text = full_text
        for old, new in replacements.items():
            if old in new_text:
                new_text = new_text.replace(old, new)

        if new_text != full_text:
            changes.append(f"  [{full_text[:60]!r}] -> [{new_text[:60]!r}]")
            redistribute_text(paragraph, new_text)

    # Also check tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    full_text = "".join(r.text for r in paragraph.runs)
                    if not full_text.strip():
                        continue
                    new_text = full_text
                    for old, new in replacements.items():
                        if old in new_text:
                            new_text = new_text.replace(old, new)
                    if new_text != full_text:
                        changes.append(
                            f"  [table] [{full_text[:60]!r}] -> [{new_text[:60]!r}]"
                        )
                        redistribute_text(paragraph, new_text)

    return changes


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    template_path = sys.argv[1]
    output_path = sys.argv[2]

    if not os.path.exists(template_path):
        print(f"ERROR: Template not found: {template_path}")
        sys.exit(1)

    # Parse replacements
    if sys.argv[3] == "--inline":
        replacements = {}
        for pair in sys.argv[4:]:
            if "=" not in pair:
                print(f"ERROR: Invalid inline replacement (need old=new): {pair}")
                sys.exit(1)
            old, new = pair.split("=", 1)
            replacements[old] = new
    else:
        json_path = sys.argv[3]
        if not os.path.exists(json_path):
            print(f"ERROR: Replacements JSON not found: {json_path}")
            sys.exit(1)
        with open(json_path, encoding="utf-8") as f:
            replacements = json.load(f)

    # Step 1: FILE COPY template (preserves all Word XML)
    shutil.copy2(template_path, output_path)
    print(f"Copied template -> {output_path}")

    # Step 2: Open copy, apply text-only replacements
    doc = Document(output_path)
    changes = apply_replacements(doc, replacements)
    doc.save(output_path)

    print(f"Applied {len(changes)} replacements:")
    for c in changes:
        print(c)

    # Step 3: Integrity check
    print("\n--- Integrity check ---")
    original = Document(template_path)
    result = Document(output_path)

    orig_num = sum(
        1
        for p in original.paragraphs
        if p._element.find(qn("w:pPr")) is not None
        and p._element.find(qn("w:pPr")).find(qn("w:numPr")) is not None
    )
    result_num = sum(
        1
        for p in result.paragraphs
        if p._element.find(qn("w:pPr")) is not None
        and p._element.find(qn("w:pPr")).find(qn("w:numPr")) is not None
    )

    orig_paras = len(original.paragraphs)
    result_paras = len(result.paragraphs)

    issues = []
    if orig_paras != result_paras:
        issues.append(f"Paragraph count changed: {orig_paras} -> {result_paras}")
    if orig_num != result_num:
        issues.append(f"Numbered paragraphs changed: {orig_num} -> {result_num}")

    if issues:
        print("WARNINGS:")
        for issue in issues:
            print(f"  ! {issue}")
    else:
        print("OK: paragraph count and numbering preserved")


if __name__ == "__main__":
    main()
