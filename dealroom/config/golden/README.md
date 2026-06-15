# Golden Corpus

Roman-curated reference documents for DEALROOM generators.

**Rule: Claude reads these files. Claude never generates or modifies them.**

## Structure

Each subfolder maps to a document type that a generator produces:

- `rfi/` — RFI question lists (Word, Markdown)
- `offer/` — Indicative offer letters (Word)
- `onepager/` — One-pager slides/structure (PPTX)
- `email/` — Email templates/examples (Markdown)
- `nda/` — NDA template (Word)
- `model/` — Financial model template (Excel)
- `databook/` — Databook template (Excel)
- `loi/` — LOI template (Word)
- `dd/` — DD checklist / Datenanfrage (Excel)

## Adding files

1. Copy the file into the appropriate subfolder
2. Add an entry to `manifest.json` with source deal, version, and usage notes
3. Run `python DEALROOM.py golden-check` to verify

## How generators use this

Each generator calls `load_golden_corpus(doc_type)` which:
- Reads the manifest for files matching the requested doc_type
- Extracts text content (docx → paragraphs, md → raw, xlsx → sheet dump)
- Returns concatenated text within a token budget
- Excludes files from the current deal (avoids self-reference)
