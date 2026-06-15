# SPEC-ONEPAGER: Deal Onepager — Template-Fill Specification

Template-fill spec for the Deal Onepager slide type. Produces a single-slide deal summary within a multi-deal PowerPoint deck. Used for investor meetings (AURICA, Strada, ASF) and internal deal tracking.

**Template base**: `260504_Repuro_Deal_Onepagers_v4.pptx` (multi-deal deck, primary slide structure). Cross-referenced against `260522_Repuro_Aurica meeting_v1.pptx` (investor-meeting variant with identical onepager layout).

**Upstream**: Stage 2+ deal assessment. Feeds from `deal_valuations`, `deal_data`, financial model outputs, and the Investor Cockpit (`ai/SPEC-INVESTOR-COCKPIT.md`) which is the HTML authoring/editing surface for Q1/Q3/Q4 bullet content.

**Downstream**: Included in investor update decks and deal pipeline presentations. Filed to `3_Deals/0_Pipeline/` or the specific investor meeting folder.

**HEGA PRINCIPLE (HARD CONSTRAINT)**: NEVER create PPTX from scratch. ALWAYS copy an existing onepager slide from the template deck and populate it with data. Layouts built without the template look wrong and damage credibility with investors.

**Anti-patterns enforced**: EXCEL-FROM-SCRATCH (applies to PPTX equally), INVENTED-FORMAT-INSTEAD-OF-COPY, OPENPYXL-CORRUPTION (by analogy: never python-pptx-write on think-cell OLE objects), CONFIDENTIAL-LEAK (offscreen shapes may contain real names).

---

## 1. Slide Dimensions and Deck Context

| Property | Value |
|----------|-------|
| Slide width | 12,192,000 EMU (13.33 in) |
| Slide height | 6,858,000 EMU (7.50 in) |
| Aspect ratio | 16:9 widescreen |
| Layout name | `Title and Content` |
| Template deck | v4 has 10 slides; Aurica has 14 slides |

Onepager slides sit within a larger deck that includes: title slide (slide 1), pipeline funnel (slide 2), pipeline table (slide 3), then individual deal onepager slides.

---

## 2. Slide Layout Map

The onepager uses a **2x2 quadrant grid** with a header bar, four section header bars, and a footer.

```
+-----------------------------------------------------------------------+
| [Section Label]               [Status Badge]                          |  <- Row 0: top bar
| [Slide Title - key message about the deal]                            |  <- Row 1: title
+-----------------------------------+-----------------------------------+
| [Q1: EXECUTIVE SUMMARY header]    | [Q2: FINANCIALS header]           |  <- Section headers
| [Q1: Exec summary text box]       | [Q2: Financial chart (WMF/Chart)] |  <- Content area
|                                   |                                   |
+-----------------------------------+-----------------------------------+
| [Q3: PROCESS DETAILS header]      | [Q4: SVC PORTFOLIO header]        |  <- Section headers
| [Q3: Process details text box]    | [Q4: Portfolio/customer text+chart]|  <- Content area
|                                   |                                   |
+-----------------------------------+-----------------------------------+
| [Footnote]                                              [Slide #]     |  <- Footer
+-----------------------------------------------------------------------+
```

### Grid anchor points (EMU)

| Grid element | Left | Top | Width | Height |
|-------------|------|-----|-------|--------|
| LEFT column origin | 328,613 | - | ~5,432,107 | - |
| RIGHT column origin | 6,440,130 | - | ~5,416,590 | - |
| Column gap | ~679,410 EMU (~0.74 in) between left column right edge and right column left edge |
| TOP content row | - | 1,137,603 | - | ~2,692,236 |
| BOTTOM content row | - | 3,829,839 | - | ~2,670,564 |

---

## 3. Element Inventory

### 3.1 Fixed Infrastructure (IDENTICAL across all 9 analyzed onepager slides)

These elements are pixel-identical in position across every onepager in both decks. **Confidence: 100% — never modify position or size.**

| Element | Shape Name | Type | Left | Top | Width | Height | Notes |
|---------|-----------|------|------|-----|-------|--------|-------|
| think-cell OLE | `think-cell data - do not delete` | EMBEDDED_OLE_OBJECT | 1,588 | 1,588 | 1,588 | 1,588 | DO NOT TOUCH. Required by think-cell. Invisible. |
| Slide title | `Title 1` | PLACEHOLDER | 333,375 | 452,406 | 11,498,166 | 628,315 | Deal headline message |
| Slide number | `Slide Number Placeholder 3` | PLACEHOLDER | 11,060,264 | 6,500,403 | 445,273 | 322,004 | Auto-incremented |
| Section label | `Content Placeholder 4` | PLACEHOLDER | 333,375 | 119,090 | 11,498,166 | 270,524 | "{Codename} one-pager" |
| Footnote | `Content Placeholder 5` | PLACEHOLDER | 328,613 | 6,500,403 | 10,653,712 | 322,004 | Optional notes/caveats |
| Q1 header bar | `Rectangle 8` | AUTO_SHAPE | 328,613 | 1,137,603 | 5,432,107 | 214,947 | Fill: scheme:tx2 (#0891B2) |
| Q2 header bar | `Rectangle 9` | AUTO_SHAPE | 6,440,130 | 1,137,603 | 5,416,590 | 214,947 | Fill: scheme:tx2 (#0891B2) |
| Q3 header bar | `Rectangle 13` | AUTO_SHAPE | 328,613 | 3,829,839 | 5,432,107 | 214,947 | Fill: scheme:tx2 (#0891B2) |
| Q4 header bar | `Rectangle 14` | AUTO_SHAPE | 6,440,130 | 3,829,839 | 5,416,590 | 214,947 | Fill: scheme:tx2 (#0891B2) |

**Outlier**: Aurica Slide 7 (Lion) has `Title 1` width at 11,784,561 instead of 11,498,166 -- treat as a manual edit artifact; use the standard width.

### 3.1a Offscreen Shapes (CONFIDENTIALITY RISK)

The pipeline table slide (slide 3 in both decks) contains a **hidden real-name table** positioned offscreen:

| Shape | Type | Position | Content |
|-------|------|----------|---------|
| `Table 9` | TABLE | L=-1,639,093 (offscreen left) | 11r x 1c, contains REAL company names mapped to codenames (HWV Blome, Medizin & Service GmbH, GOLMED, MenkeMED GmbH, Com2Med, KVG GmbH, KoeWe GmbH, RS Radiology, Meditec Source GmbH & Co. KG, Coretec-Service GmbH) |

**HARD RULE**: When copying slides or producing decks for external distribution, scan for shapes with `Left < 0` (offscreen) and either delete them or flag them. This table maps codenames to legal names and MUST NOT appear in investor-facing materials.

### 3.1b Cover Slide (Slide 1 -- deck context)

The deck opens with a full-bleed cover slide (layout `1_Blank`):

| Element | Shape | Position | Content |
|---------|-------|----------|---------|
| Background photo | `Picture 2` / `Picture 15` | Full-bleed (extends past slide edges) | JPEG/PNG, 1.3-8.5 MB |
| Overlay rectangle | `Rectangle 12` / `Rectangle 16` | Full-bleed | Fill #B4B4B4 with transparency |
| Title text | `Title 1` | L=0 T=1,268,413 W=~6,700,000 H=3,416,875 | "Repuro Group" (bold 40pt) + "Deal Updates" / "AURICA Update" (regular 40pt) |
| Logo | `Picture 14` | L=~4,150,000-4,640,000 T=~3,720,000-3,860,000 W=~1,830,000-2,210,000 | Repuro logo PNG, ~16KB |
| Date | `Text Placeholder 2` | L=0 T=~3,880,000-3,900,000 W=6,969,125 H=900,177 | "24 March 2026" / "May 22, 2026" -- Arial ~24pt |

**Rule**: Cover slide date and subtitle change per meeting. Logo and background are fixed chrome.

### 3.2 Status Badge (per-slide, optional)

| Element | Shape Name (varies) | Type | Left | Top | Width | Height | Notes |
|---------|-----------|------|------|-----|-------|--------|-------|
| Status badge | `Rectangle 15` / `Rectangle 21` / `Rectangle 4` | AUTO_SHAPE | 5,045,166 | 0 | 2,101,669 | 184,286 | Fill: scheme:accent3 (v4, #E11D48 red) or scheme:accent6 (Aurica, #8C6AD8 purple). Text: "WIP", "OLD", "TO BE UPDATED" |

**Rule**: Badge name varies. Position is stable at (5,045,166, 0). Badge is absent on final/clean slides. Use accent3 for internal WIP flagging; accent6 appears in Aurica deck (different theme override — irrelevant for the fill process).

### 3.3 Content Text Boxes (variable height, stable anchor points)

All content text boxes are named `Google Shape;99;p3` (legacy Google Slides naming). The LEFT and TOP anchors are stable; HEIGHT varies per deal based on content length.

| Quadrant | Role | Left (stable) | Top (stable) | Width (stable range) | Height (varies) |
|----------|------|------|-----|-------|--------|
| Q1 (top-left) | Executive summary | 328,613 | 1,381,137 | 5,567,841 (+/-68,510) | 2,150,195 — 2,842,692 |
| Q2 (top-right) | Financial visual + commentary | varies by visual type | varies | varies | varies |
| Q3 (bottom-left) | Process details | 328,613 | 4,101,303 | 5,519,926 | 1,688,530 — 2,304,083 |
| Q4 (bottom-right) | Portfolio/customer commentary | varies (7,934,632 — 8,436,779) | 4,096,540 — 4,340,380 | 3,397,755 — 3,896,909 | 1,919,363 — 2,919,636 |

**Key finding**: Q1 and Q3 LEFT positions are pixel-stable. Q4 LEFT position varies because it shares horizontal space with a native chart object of variable width.

### 3.4 Financial Visuals (Q2 top-right area)

**CRITICAL**: Financial visuals in Q2 use THREE different rendering approaches across slides:

| Approach | Example slides | Format | Automatable? |
|----------|---------------|--------|-------------|
| WMF image (think-cell export) | Cat 1/2, Cat 2/2, Fox (both decks), Octopus | `image/x-wmf`, 12-17KB | NO — opaque image |
| Native PPTX Chart | Cat 1/2 (Chart 26), Fox (Content Placeholder 32), Wolf, Octopus | CHART object | PARTIALLY — python-pptx can update chart data but not create from scratch |
| PNG image | Wolf (both decks), Mantis | `image/png`, 38-39KB | NO — opaque image |

**Position envelope for financial visuals in Q2**:

| Property | Min | Max | Typical |
|----------|-----|-----|---------|
| Left | 6,357,938 | 6,442,459 | ~6,440,130 |
| Top | 1,372,080 | 1,413,307 | ~1,400,000 |
| Width | 5,410,369 | 5,434,441 | ~5,420,000 |
| Height | 1,845,474 | 2,438,602 | ~2,350,000 |

### 3.5 Pie Charts with Labels (Q4 bottom-right)

Some onepagers include native PPTX pie charts for revenue split and customer concentration. These appear alongside the Q4 commentary text box, pushing it rightward.

| Chart type | Example slides | Position |
|-----------|---------------|----------|
| Revenue split pie | Cat (Chart 26), Fox (Content Placeholder 32), Octopus (Chart 81) | L~6,358,000 T~4,045,000 W~2,040,000 H~2,375,000 |
| Customer concentration pie | Wolf (Content Placeholder 38) | L~6,416,000 T~4,004,000 W~1,732,000 H~2,402,000 |

Pie chart labels are individual AUTO_SHAPE elements named `Text Placeholder 2` positioned absolutely around the chart. Font: Arial 8pt (88,900 EMU) or 10pt (101,600 EMU).

### 3.5a think-cell Infrastructure (DO NOT TOUCH)

Every content slide contains think-cell infrastructure shapes that must be preserved intact:

| Shape Name Pattern | Type | Count per slide | Purpose |
|--------------------|------|-----------------|---------|
| `think-cell data - do not delete` | EMBEDDED_OLE_OBJECT | 1 | think-cell data store at (1588, 1588, 1588, 1588) |
| `btfpColumnIndicatorGroup*` | GROUP (4 sub-shapes each) | 2 | Column alignment guides at top/bottom of slide |
| `btfpColumnGapBlocker*` | AUTO_SHAPE (within groups) | 4 | Column gap boundary markers |
| `btfpColumnIndicator*` | LINE (within groups) | 4 | Column indicator lines |
| `btfpTable*` | TABLE | 0-1 | Pipeline summary table (slide 3 only) |
| `btfpHBCheckCross*` | AUTO_SHAPE | 0-11 | Strategic fit check/cross markers (pipeline table only) |
| `Google Shape;4*` | GROUP (4 sub-shapes each) | 2 | Duplicate column guides (Google Slides artifact) |

**HARD RULE**: Never modify, move, or delete any shape whose name starts with `btfp` or `Google Shape;4`. Never touch shapes named containing "think-cell". Corrupting any of these breaks think-cell charts across the entire deck.

### 3.6 Revenue Split Sub-header (optional)

| Element | Shape Name | Position | Notes |
|---------|-----------|----------|-------|
| Revenue split label | `Rectangle 18` | L=6,440,130 T=4,063,203-4,101,303 W=1,750,559 H=214,947 | "Revenue split 2024" / "Revenue split 2025". Only present on slides with pie chart. |

---

## 4. Section Header Text Variations

The four section headers use scheme:tx2 fill (#0891B2 teal) with **Arial 12pt (152,400 EMU) Bold White**.

### Standard onepager (1/1 or 1/2)

| Position | Standard text | Observed variations |
|----------|--------------|-------------------|
| Q1 header (Rectangle 8) | `Executive summary` | Stable across all primary onepagers |
| Q2 header (Rectangle 9) | `Financials` | Sometimes `Financials1` (with footnote ref) |
| Q3 header (Rectangle 13) | `Process details` | Stable |
| Q4 header (Rectangle 14) | `Service portfolio & customer structure` | Stable |

### Extension slide (2/2 — used for Cat)

| Position | Text |
|----------|------|
| Q1 header | `Current Trading1` |
| Q2 header | `Order book` / `Order book (M€)2` |
| Q3 header | `Process details` / `Comments` |
| Q4 header | `Service portfolio & customer structure` / `Comments` |

**Rule**: The 2/2 extension slide is NOT a separate template — it reuses the same grid but with different section headers and content. Only Cat has used this pattern so far.

---

## 5. Template Fill Map

### 5.1 Fixed Chrome (zero variability — copy verbatim)

- think-cell OLE object (position, content)
- Four section header bars (position, size, fill color)
- Slide number placeholder (position, auto-increment)
- Grid structure and column gap

### 5.2 Variable Text — High Confidence Fill

| Shape | Content source | Type |
|-------|---------------|------|
| `Content Placeholder 4` (section label) | `"{Codename} one-pager"` or `"{Codename} one-pager (1/2)"` | Simple slot fill |
| `Title 1` (slide title) | Roman provides — deal headline, e.g. "Cat shows a strong orderbook and highly profitable projects" | Roman input |
| Status badge text | "WIP" / blank / "TO BE UPDATED" | Roman decision |
| Section header texts | Standard set unless 2/2 extension | Template |
| `Content Placeholder 5` (footnote) | Deal-specific notes/caveats, optional | Roman input |

### 5.3 Variable Text — Requires Drafting

| Shape | Content type | Source | Confidence |
|-------|-------------|--------|-----------|
| Q1 exec summary | 4-6 bullet points: company description, financials summary, key metrics, valuation, strategic fit | Deal model + deal_data + Roman narrative | MEDIUM — can draft from data, Roman reviews |
| Q3 process details | 3-5 bullet points: transaction structure, transition plan, reinvestment, status, DD focus | Negotiation state + Roman input | LOW — deal-specific, Roman must provide or heavily review |
| Q4 portfolio commentary | 3-5 bullet points: revenue split description, customer structure, recurring revenue, supplier info | Deal data + management info | MEDIUM — can draft from data |

### 5.4 Financial Visuals — CANNOT Be Produced Programmatically

| Visual type | Automation status | Required action |
|-------------|------------------|-----------------|
| Revenue/EBITDA bar chart (WMF) | NOT automatable | Roman creates in think-cell or provides WMF export |
| Revenue/EBITDA bar chart (PNG) | NOT automatable | Roman provides PNG image |
| Revenue split pie chart | PARTIALLY automatable | python-pptx can update chart data series if native PPTX chart |
| Customer concentration pie chart | PARTIALLY automatable | Same as above |
| Pie chart labels | Manually positioned | Must be created per deal |

---

## 5a. Pipeline Table Structure (slide 3 -- reference)

The pipeline overview table defines the standard metrics displayed per deal. This table is NOT part of individual onepager slides but provides the data backbone.

### Column structure (v4: 12r x 10c, Aurica: 11r x 10c)

| Column | Header | Width (EMU) | Content Type | Font |
|--------|--------|-------------|-------------|------|
| 0 | (codename, in M€) | 761,670-854,741 | Codename | Arial 10.5pt (133,350) bold |
| 1 | Rev. 2025P | 738,688-781,234 | Revenue | Arial 11pt (139,700) |
| 2 | EBITDA 2025P | 738,688-781,234 | EBITDA | Arial 11pt |
| 3 | EBITDA(%) | 738,688-781,234 | Margin % | Arial 11pt |
| 4 | # empl. | 721,404-738,688 | Headcount | Arial 11pt |
| 5 | Strategic fit | 721,404-738,688 | Check/cross icon (btfpHBCheckCross shapes overlay this column) | think-cell generated |
| 6 | Description | 2,943,687 | 1-line business description | Arial 11pt |
| 7 | Status | 2,428,124 | Current deal status | Arial 11pt |
| 8 | EV incl. EO | 769,122 | Total EV | Arial 11pt |
| 9 | Multiple incl. EO | 826,613 | EBITDA multiple | Arial 11pt |

### Row heights

| Row Type | Height (EMU) | Notes |
|----------|-------------|-------|
| Header row | 571,505-612,328 | Bold, 12pt |
| Deal row | 422,604-452,791 | Regular data |
| Sum row | 394,874-423,080 | Bold totals |

**Rule**: This table is think-cell managed. The strategic fit column (5) uses overlaid btfpHBCheckCross shapes to render check/cross/tilde icons. Do NOT attempt to modify this table programmatically.

---

## 6. Data Input Schema

### 6.1 Structured Fields (from DB + deal folder + model)

```
deal_id:            str           # dealroom deal identifier
code_name:          str           # e.g. "Fox", "Octopus", "Cat" (DB column: deals.code_name)
legal_name:         str           # e.g. "Com2Med GmbH"

financials: {
  revenue_latest:   float         # M€, most recent full year
  ebitda_latest:    float         # M€, adjusted EBITDA
  ebitda_margin:    float         # %, e.g. 15.0
  revenue_year:     int           # year of latest figures, e.g. 2025
  employees:        int           # headcount
  revenue_cagr:     str|null      # e.g. "CAGR 2023-25 of 4%"
}

valuation: {
  ev_closing:       float         # M€, EV at closing
  ev_closing_mult:  str           # e.g. "3.6x 2025 EBITDA"
  earn_out_max:     float|null    # M€, max earn-out
  ev_incl_eo:       float|null    # M€, total EV including earn-out
  ev_incl_eo_mult:  str|null      # e.g. "5.5x 2025"
  super_eo:         float|null    # M€, super earn-out if applicable
}

deal_stage:         str           # "LOI preparation", "Indicative offer sent", etc.
strategic_fit:      str           # brief description of fit to Repuro thesis
```

### 6.2 Roman Input (cannot be derived — MUST be provided)

**Authoring tool**: The Investor Cockpit (HTML dashboard, spec at `ai/SPEC-INVESTOR-COCKPIT.md`) is the primary authoring surface for Q1/Q3/Q4 text content and the slide title. Content is auto-generated via `draft-onepager` (Claude sonnet), stored in DB columns (`deals.onepager_q1/q3/q4`, `deals.onepager_title`, `deals.onepager_footnote`), and editable inline in the dashboard. The PPTX template-fill process reads these DB fields — Roman does not re-enter content for the PPTX.

**Approval gate**: Each quadrant has an approval flag in the DB (`onepager_q1_approved`, `onepager_q3_approved`, `onepager_q4_approved`). The PPTX fill process should only proceed on quadrants where `*_approved = 1`. Unapproved quadrants render with a "DRAFT" badge in the HTML cockpit.

| Field | Description | DB source (Cockpit) | When needed |
|-------|-------------|---------------------|-------------|
| `slide_title` | 1-line headline message for the deal | `deals.onepager_title` | Always |
| `exec_summary_bullets` | 4-6 bullet points for Q1 exec summary. Roman either writes or heavily edits draft. | `deals.onepager_q1` | Always |
| `process_bullets` | 3-5 bullet points for Q3 process details (transaction structure, transition, reinvestment, status, DD focus) | `deals.onepager_q3` | Always |
| `portfolio_bullets` | 3-5 bullet points for Q4 service portfolio & customer structure | `deals.onepager_q4` | Always |
| `financial_chart` | WMF/PNG image file OR instruction to reuse/update existing chart | N/A — manual, not in Cockpit | Always |
| `footnote_text` | Optional footnote for bottom of slide | `deals.onepager_footnote` | If applicable |
| `is_extension` | Whether this is a 1/1 slide or needs a 2/2 extension | N/A — Roman decision | If complex deal |
| `status_badge` | "WIP" / "TO BE UPDATED" / none | N/A — Roman decision | If applicable |

### 6.3 Chart Data (only if native PPTX pie chart is used)

```
revenue_split: [                  # for revenue breakdown pie
  { label: str, pct: float }     # e.g. {"label": "Consultation supplies", "pct": 47.0}
]

customer_concentration: [         # for customer pie
  { label: str, pct: float }     # e.g. {"label": "Top 3", "pct": 8.0}
]
```

---

## 7. Text Formatting Rules

All onepager text uses consistent formatting. Preserve exactly.

### 7.1 Content text boxes

| Property | Value |
|----------|-------|
| Font family | Arial |
| Font size | 10pt (127,000 EMU) |
| Color | #000000 (black) |
| Bold | Used for emphasis on key metrics and Roman's highlighted points |
| Line spacing | Default (single) |
| Bullet style | En-dash or bullet point prefix in text, NOT PowerPoint native bullets |
| Text box fill | #000000 with 0% opacity (transparent fill — legacy artifact, do not remove) |

### 7.2 Section headers

| Property | Value |
|----------|-------|
| Font family | Arial |
| Font size | 12pt (152,400 EMU) |
| Bold | True |
| Color | White |
| Bar fill | scheme:tx2 = #0891B2 (Repuro teal from "Medtech 2" theme) |
| Bar height | 214,947 EMU (0.235 in) |

### 7.3 Slide title

| Property | Value |
|----------|-------|
| Font | Inherited from slide master (typically Arial) |
| Size | Inherited (typically 24-28pt) |
| Style | Bold implied by placeholder styling |

### 7.4 Footnote

| Property | Value |
|----------|-------|
| Font | Inherited from placeholder |
| Size | ~8pt (small) |
| Style | Regular |

### 7.5 Pie chart labels

| Property | Value |
|----------|-------|
| Font family | Arial |
| Size | 8pt (88,900 EMU) for Top N labels, 10pt (101,600 EMU) for category labels |
| Bold | None/False |
| Positioning | Absolute — manually placed around pie chart perimeter |

---

## 8. Brand Color Palette

Theme: "Medtech 2 (chosen so far)" — consistent across all theme files in both decks.

| Scheme name | Role in onepager | Hex value |
|-------------|-----------------|-----------|
| dk1 | Text default | #000000 (windowText) |
| dk2 / tx2 | Section header fill, primary brand teal | #0891B2 |
| lt2 / bg2 | Muted gray (used in some chart labels) | #6B7280 |
| accent1 | Chart accent, cyan highlight | #22D3EE |
| accent2 | Chart accent, light cyan | #8DE8F6 |
| accent3 | WIP badge fill (red) | #E11D48 |
| accent4 | Warning/info badge (yellow) | #EAB308 |
| accent5 | Reserved | #A855F7 |
| accent6 | Alternative badge fill (purple, Aurica deck) | #8C6AD8 |
| hlink | Repuro green | #1A7C65 |

**Note**: A secondary "Repuro" theme exists in `themeOverride2.xml` with dk2=#1A7C65 and accent1=#26B492. This is NOT used for onepager section headers — the "Medtech 2" theme governs.

---

## 9. Edge Cases and Hardening

### 9.1 Multi-slide Onepagers (e.g., Cat 1/2 + 2/2)

Cat is the only deal with a two-slide onepager. The extension slide (2/2) uses different section headers but the same grid structure. When a deal has significant current trading data or order book detail, Roman may request a 2/2 extension.

**Rule**: Default to 1/1. Only create 2/2 if Roman explicitly requests it. The 2/2 slide is a duplicate of the template with different section header text and content.

### 9.2 Financial Chart Type Varies Per Deal

| Deal | Chart approach in Q2 top-right |
|------|-------------------------------|
| Cat | WMF image (think-cell revenue/EBITDA waterfall) |
| Fox | WMF image (think-cell) |
| Wolf | PNG image (screenshot/export) |
| Octopus | WMF image (think-cell) |
| Lion | PNG image |
| Mantis | No distinct chart — reuses Wolf structure |

**Rule**: The fill process MUST NOT attempt to create financial charts. Accept image file path as input and place at the standard Q2 position. If no image is provided:
1. DELETE any existing chart/image in Q2 from the copied template slide (do NOT leave the previous deal's chart)
2. Insert a placeholder text box at the Q2 position with text "FINANCIAL CHART — TO BE ADDED" in gray
3. Flag to Roman that Q2 is empty

**HARD RULE**: A prior deal's financial chart MUST NEVER carry over to a new deal's onepager. This is a confidentiality and accuracy risk — it shows wrong numbers for the wrong company. Empty is always safer than stale.

### 9.3 Pie Chart Presence is Optional

Not all onepagers include pie charts. When present, they push the Q4 text box rightward. When absent, the Q4 text box can extend leftward to L=6,440,130.

**Rule**: If `revenue_split` or `customer_concentration` data is provided AND a native chart exists in the template to clone, update the chart data. Otherwise, leave pie charts to Roman.

### 9.4 Missing "Executive Summary" Header on Lion Slide

The Aurica Lion onepager (slide 7) uses `Rectangle 32` instead of `Rectangle 8` for the Q1 header. This is a naming anomaly — the position is identical. Shape names are unreliable for identification; use position matching instead.

**Rule**: When locating shapes for text fill, match by position (Left, Top within 10,000 EMU tolerance) rather than by shape name.

### 9.5 Content Text Box Heights

Text box heights vary significantly based on content length (1,688,530 to 2,919,636 EMU observed). PowerPoint auto-resizes text boxes when text overflows.

**Rule**: Set text box height to accommodate expected content. If text overflows, reduce font size is NOT acceptable — instead, reduce content (fewer bullets, tighter wording). The 7.50-inch slide height is the hard constraint.

### 9.6 Bold Formatting Pattern in Bullet Points

Analysis shows a consistent pattern: key metrics and emphasis points are bold, while supporting detail is regular weight. This is NOT random — it follows Roman's editorial judgment about what investors should see first when scanning.

**Rule**: In draft mode, bold the first sentence of each bullet (which contains the key claim). Roman will adjust during review.

### 9.7 Yellow Editorial Markers (MUST REMOVE)

Both decks contain yellow (#FFFF00) filled rectangles used as internal editorial comments:

| Shape | Position | Content | Found In |
|-------|----------|---------|----------|
| `Rectangle 5` | L=9,307,782 T=228,164 W=2,523,759 H=749,113 | "Comment about Q1 Update" | v4 Cat slide 4 |
| `Rectangle 17` | L=8,750,711 T=0 W=3,441,290 H=943,834 | "WIP" (large variant) | v4 Fox slide 6 |
| `Rectangle 2` | L=8,267,701 T=219,187 W=3,590,922 H=628,315 | "Mantis to be added / Status to be updated" | Aurica slide 3 (yellow fill) |
| Large overlay | L=2,489,850 T=2,344,860 W=7,611,396 H=2,562,977 | "To be updated" (covers content) | Aurica Mantis slide 8 (yellow fill) |

**HARD RULE**: Scan for all shapes with fill color #FFFF00 before producing external-facing output. Delete or flag every one. These are internal editorial markers that MUST NOT appear in investor presentations.

### 9.8 Pipeline Table Evolution Between Decks

The v4 pipeline table (slide 3) has 12 rows x 10 columns with 10 deals. The Aurica table has 11 rows x 10 columns with 9 deals (different set: Cat, Fox, Lion promoted to top; Swordfish, Bat, Blackbird added; Octopus and Eagle removed).

**Rule**: Pipeline table updates are a SEPARATE workflow. The table uses think-cell formatting (btfpHBCheckCross shapes for strategic fit indicators, btfpTable for the table itself). Do not attempt to modify the pipeline table programmatically.

### 9.9 Special Characters

German text uses: €, ü, ö, ä, ß, – (en-dash), ~ (tilde for approximation). EMU size notation uses \x0b (vertical tab) for line breaks within table cells in the pipeline table — NOT relevant for onepager text boxes.

---

## 10. Think-Cell Dependency

### 10.1 OLE Object

Every onepager slide contains `think-cell data - do not delete` as an EMBEDDED_OLE_OBJECT at position (1588, 1588, 1588, 1588). This is a think-cell data store. **It MUST be preserved when copying slides.** Deleting it may break think-cell charts on other slides in the same deck.

### 10.2 WMF Images

WMF (Windows Metafile) images in Q2 are think-cell chart exports. They are static raster/vector images — the underlying chart data lives in the think-cell OLE object or in a separate think-cell data source. python-pptx can:
- Read WMF image position and size
- Replace a WMF image with another WMF/PNG image
- NOT modify the chart content within the WMF

**Implication**: Revenue/EBITDA bar charts cannot be auto-generated. Roman must either:
1. Create them in think-cell and export as WMF
2. Provide a PNG screenshot
3. Accept the previous deal's chart as a placeholder marked "TO BE UPDATED"

### 10.3 Native PPTX Charts

Some slides contain native PPTX Chart objects (pie charts). python-pptx can:
- Read chart data series
- Update chart data values
- NOT reliably change chart type or add/remove series

**Implication**: If a template slide already has a pie chart, the template-fill agent can update its data series. If no pie chart exists, one cannot be safely added programmatically.

---

## 11. Confidence Assessment

| Element | Confidence | Automatable | Notes |
|---------|-----------|-------------|-------|
| Slide copy from template | HIGH | YES | python-pptx slide duplication |
| Section label fill ("{Codename} one-pager") | HIGH | YES | Simple text replacement |
| Section header text | HIGH | YES | Standard set known |
| Status badge | HIGH | YES | Text replacement + show/hide |
| Q1 exec summary text | MEDIUM | DRAFT + REVIEW | Can draft from deal data; Roman reviews |
| Q3 process details text | LOW | ROMAN INPUT | Too deal-specific to draft reliably |
| Q4 portfolio commentary text | MEDIUM | DRAFT + REVIEW | Can draft from deal data |
| Slide title | LOW | ROMAN INPUT | Requires editorial judgment |
| Q2 financial bar chart (WMF/PNG) | NONE | MANUAL | Cannot be produced programmatically |
| Q2 financial bar chart (native) | LOW | PARTIAL | Can update data if chart exists |
| Pie chart data update | MEDIUM | YES | If native chart exists in template |
| Pie chart label positioning | LOW | MANUAL | Absolute positioning per chart |
| Footnote | LOW | ROMAN INPUT | Deal-specific caveats |

---

## 12. Template-Fill Workflow

### Phase 1: Copy Template Slide

1. Open the template deck (`260504_Repuro_Deal_Onepagers_v4.pptx`)
2. Identify a clean onepager slide to use as source (prefer Wolf or Octopus — most complete)
3. Duplicate the slide using python-pptx `add_slide()` with the same layout
4. Position the new slide at the correct index in the target deck

**CRITICAL**: Copy the ENTIRE slide including all shapes. Do not reconstruct shape-by-shape.

### Phase 2: Fill Text Fields

1. **Section label**: Set `Content Placeholder 4` text to `"{Codename} one-pager"`
2. **Slide title**: Set `Title 1` text to Roman's provided headline
3. **Section headers**: Verify standard text is correct (or update for 2/2 extension)
4. **Q1 exec summary**: Replace text in the top-left `Google Shape;99;p3` (matched by position: Left < 6M, Top ~1,381,137)
5. **Q3 process details**: Replace text in the bottom-left `Google Shape;99;p3` (matched by position: Left < 6M, Top ~4,101,303)
6. **Q4 portfolio commentary**: Replace text in the bottom-right `Google Shape;99;p3` (matched by position: Left > 6M, Top > 4M)
7. **Footnote**: Set `Content Placeholder 5` text if footnote provided
8. **Status badge**: Set text to "WIP" or hide shape

### Phase 3: Handle Financial Visuals

1. If Roman provides a chart image file (WMF/PNG):
   - Locate the existing Q2 image shape (Picture in top-right, Top < 2M)
   - Replace image blob with new file
   - Preserve position and size from template
2. If updating pie chart data:
   - Locate CHART object by position (Left ~6,358,000-6,440,000, Top > 4M)
   - Update data series values from `revenue_split` / `customer_concentration`
3. If no financial visual provided:
   - Leave existing placeholder or clear text to "TO BE UPDATED"
   - Flag to Roman

### Phase 4: Verify and Output

1. Verify all text boxes have content (no empty quadrants)
2. Verify slide dimensions match deck (13.33 x 7.50 in)
3. Verify section header positions match spec (within 10,000 EMU tolerance)
4. Save to temp file first, then verify file is valid and non-empty, then move to target
5. Report which elements need Roman's review
6. REVIEW GATE: Present completed slide to Roman. Roman confirms: correct data, correct formatting,
   no prior-deal residual, financial chart acceptable. BLOCK: do not include slide in external deck
   until Roman explicitly approves.

---

## 13. Anti-Patterns

### PPTX-FROM-SCRATCH (critical)
**Never create a PPTX slide from scratch.** Always copy from an existing template. Layouts created without a template have wrong spacing, wrong fonts, missing theme inheritance, and look obviously machine-generated. This is an investor-facing document — visual quality is non-negotiable.

### INVENTED-FORMAT-INSTEAD-OF-COPY (critical)
**Never invent a new onepager layout.** The 2x2 quadrant grid with specific section headers is Roman's design. Respect it. If the content doesn't fit, reduce the content — do not restructure the slide.

### THINK-CELL-CHART-GENERATION (critical)
**Never attempt to programmatically generate think-cell charts or create bar charts from scratch.** The financial charts are think-cell exports (WMF images) or Roman-created native charts. Accept image inputs; never fabricate chart visuals.

### CONFIDENTIAL-LEAK (critical)
Onepagers contain deal-sensitive information: company codenames, valuations, EBITDA figures, transaction structures. Never include real company names in codename-stage documents. Never share onepager content outside the intended recipient context.

### PIE-CHART-LABEL-DRIFT (medium)
Pie chart labels are absolutely positioned AUTO_SHAPE elements. If chart data changes (e.g., new revenue split percentages), label positions must be manually adjusted. Do not assume labels will auto-reposition — they will overlap or point to wrong slices.

### TEXT-OVERFLOW-FONT-SHRINK (medium)
PowerPoint may auto-shrink text to fit a box. This creates inconsistent font sizes across slides and looks unprofessional. If text overflows, CUT the text — do not let PowerPoint shrink it. Each bullet should be 1-2 lines maximum.

### SHAPE-NAME-MATCHING (medium)
Shape names are inconsistent across slides (Rectangle 15 vs Rectangle 21 vs Rectangle 4 for the same status badge). Always match shapes by POSITION, not by name. Position tolerance: 10,000 EMU (0.01 inches).

---

## 14. Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| python-pptx | 1.0.2+ | Slide manipulation, text replacement, chart data update |
| Template deck | `260504_Repuro_Deal_Onepagers_v4.pptx` | Source for slide copy |
| think-cell | External (PowerPoint add-in) | Financial chart creation — Roman's tool |
| Deal model outputs | From `susa_to_model.py` pipeline | Revenue, EBITDA, valuation data |
| Roman's narrative | Manual input | Slide title, process bullets, editorial emphasis |

### Template file location

```
Primary:   config/golden/onepager/260504_Repuro_Deal_Onepagers_v4.pptx
Reference: config/golden/onepager/260522_Repuro_Aurica meeting_v1.pptx
```

### Deck structure comparison

**v4 (260504, 10 slides)**:
1. Cover (Repuro Group / Deal Updates / 24 March 2026)
2. Pipeline funnel
3. Pipeline table (12r: Octopus, Wolf, Cat, Colibri, Fox, Falcon, Owl, Eagle, Mouse, Lion + SUM)
4. Cat one-pager (1/2)
5. Cat one-pager (2/2)
6. Fox one-pager
7. Wolf one-pager
8. Cat OLD (archived version)
9. Blank divider
10. Octopus one-pager

**Aurica (260522, 14 slides)**:
1. Cover (Repuro Group / AURICA Update / May 22, 2026)
2. Intro (Goals of today's meeting)
3. Pipeline table (11r: Cat, Fox, Lion, Wolf, Mouse, Swordfish, Bat, Falcon, Blackbird + SUM)
4. Fox one-pager (updated)
5. Cat two-pager (1/2)
6. Cat two-pager (2/2) -- Current Trading + Order book
7. Lion one-pager (NEW)
8. Mantis one-pager (reusing Wolf template, "To be updated")
9. Next steps
10. Blank divider
11. Fundraising comparison table (AURICA vs Offer 2 vs Offer 3)
12. Wolf one-pager (unchanged from v4)
13. AI workflow (FROM manual)
14. AI workflow (TO dashboard)

### Source slide selection for copying

| Source slide | Codename | Recommended for | Reason |
|-------------|----------|-----------------|--------|
| v4 Slide 7 | Wolf | Simple onepagers | Clean 1/1 layout, no extra chart labels |
| v4 Slide 10 | Octopus | Onepagers with pie charts | Has revenue split pie + customer pie |
| v4 Slide 4 | Cat | Onepagers needing detailed financials | Has WMF chart + native pie chart |

---

## Appendix A: Observed Bullet Content Patterns

### Q1 Executive Summary — typical bullet structure

1. **Company description**: "{Codename} is a [type] for [customers] with [differentiator]"
2. **Financial headline**: "{Codename} generated ~X M€ revenue at Y M€ adj. EBITDA (Z% margin) in {year} and revenue CAGR..."
3. **Key differentiator** (bold): Revenue quality, recurring share, customer concentration
4. **Valuation**: "EV at closing of X M€ (Yx {year} EBITDA), with further earn-out of Z M€..."
5. **Strategic fit**: "Could serve as [anchor/add-on] for Repuro with [reason]"

### Q3 Process Details — typical bullet structure

1. **Transaction background**: "Acquiring 100% of shares; [sourcing channel]"
2. **Transition**: "Current owner/GF to stay on as MD [duration] and [role]"
3. **Reinvestment** (if applicable): "X M€ (~Y%) to be reinvested pari passu..."
4. **Status**: "Current status: [stage]"
5. **DD focus**: "Key items: [sustainability, customer churn, margin drivers, ...]"

### Q2 Financial Chart — observed chart data patterns

Revenue/EBITDA bridge charts show 3-4 years of historical + projected data:

| Deal | Years Shown | Revenue Range | EBITDA Range | Chart Source |
|------|-------------|---------------|-------------|-------------|
| Cat | 2022-2026B | 2.5-6.5 M€ | 0.2-0.9 M€ | WMF (think-cell) |
| Fox | 2021-2025A | 2.0-3.5 M€ | 0.2-0.4 M€ | WMF (think-cell) |
| Wolf | 2022-2025A | 5.0-8.3 M€ | 0.4-0.8 M€ | PNG (screenshot) |
| Octopus | 2023-2025P | 7.0-11.0 M€ | 1.0-2.0 M€ | WMF (think-cell) |
| Lion | 2022-2025P | 4.0-7.8 M€ | 0.4-0.7 M€ | PNG (screenshot) |

### Q4 Portfolio/Customer — typical bullet structure

1. **Business model**: Revenue split by type (distribution, service, projects, consumables)
2. **Customer structure**: Concentration, recurring share, hospital vs. ambulatory
3. **Key metric** (bold): Recurring revenue share, backlog, top customer %
4. **Supplier info**: Top supplier concentration
5. **Growth indicator**: New customer generation, churn rates

### Supplementary Slide Types (Aurica deck only)

**Next Steps slide** (Aurica slide 9): Left side has a process/timeline image (PNG), right side has 3-4 numbered action items. Font: Arial 20pt (254,000 EMU), key item in teal (#0891B2) + bold. Separated by vertical line at L=4,502,716.

**Fundraising Comparison table** (Aurica slide 11): 15r x 15c table comparing investor term sheets (AURICA vs Offer 2 vs Offer 3). Covers: equity commitment, co-investors, MOIC hurdles, MIP structure, free equity, management salary. Font: +mj-lt/+mn-lt (theme fonts) 11pt (139,700 EMU). Column structure uses blank columns (width ~265,000-295,000) as visual separators between offers.

**AI Workflow slides** (Aurica slides 13-14): Before/after comparison showing manual target search workflow vs. Claude Code dashboard. Layout `1_Title and Content`. Contains screenshots (PNG) and labeled description boxes. These are Repuro capability slides, not deal-specific.
