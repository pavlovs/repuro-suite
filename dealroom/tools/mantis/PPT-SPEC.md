# Mantis CDD Deck — Build Spec (v3, after two failed iterations 2026-06-10)

## Goal (single sentence)
An IC-ready CDD deck where every slide makes one evidence-backed, answer-first claim and is stylistically indistinguishable from the rest of the template.

## Definition of done — per slide, checked on the rendered PNG before delivery
1. **Style match**: fonts, sizes, colors of ALL inserted elements sampled from the deck's own shapes (read Font.Name/Size from an existing comments/body shape on the same slide and clone it). Never default styling.
2. **Language**: investor English only. No German data labels (translate: Vertrieb → Product sales, Endoskop-Reparatur → Endoscope repair, Vertragsrechnung → Service contracts, Other services). Labels must be translated INSIDE the Excel charts before PNG export (English display rows in the chart helper tables, not raw RepArt values).
3. **Voice**: commentary passes the "would an IC member need this sentence?" test. Claims and implications only — no databook mechanics, no file names, no "live formulas", no invoice-count provenance. Sources belong in the footer line, nothing else.
4. **No template remnants**: zero dummy numbers, zero [Octopus/consultation-supplies] content, zero text corruption — re-render and read EVERY touched slide after the LAST patch, not after the first build.
5. **Geometry**: charts keep aspect ratio; elements aligned to the slide grid (header bands at y96, content from y136, footers untouched).

## Known technical traps (all hit on 2026-06-10, fixes proven)
- PowerPoint: first AddPicture per slide gets captured by an empty layout placeholder → always force Left/Top/Width/Height after insert; verify per slide.
- Excel Chart.Export from hidden instance produces broken PNGs unless the chart is `.Activate()`d first.
- PS `-like "[Target]*"` — brackets are wildcard classes; use `.Contains()`.
- German Excel: `NumberFormatLocal` with German codes; en-US thread culture for COM.
- PIA AddPicture needs `[single]` casts on computed coordinates.
- Build scripts: `dealroom/tools/mantis/` (databook v4 builder, RFI builder, chart exporter, PPT builder).

## Working mode (agreed with Roman 2026-06-10)
- 2-slide checkpoint: rebuild S11 + S17 to this bar, show rendered PNGs, get sign-off, then the remaining slides.
- Codex review before delivery; per-slide visual QA is MY job before Codex sees it.
- Financial section (S36–S40): source = financial model in `260112_Endoberatung (Mantis)/4_Model/` — map the model first, slide plan checkpoint, then build.

## Content status (verified, from databook v4)
All analysis content is final and Codex-reviewed: segments/growth (stalled, +11.4%/+2.0%), GM by line (materials-only; Vertrieb 75→47→31%, repair 62→73%, contracts >100% = basis question RFI Q8), quarterly, concentration (Top20 71%), cohorts (94% existing), retention (NRR 90-102%), churn (21-33% logo, bridge +312k→+58k). The remaining work is PRESENTATION quality, not analysis.
