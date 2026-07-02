# Spec: Investor View — Section Split

**Status**: APPROVED (Option B — per-deal split)
**Date**: 2026-07-01
**File**: `boardroom/static/index.html` (1,605 lines)

---

## Problem

Weekly investor-view updates require scrolling through a 1,605-line monolith. ACT 2 (Live Deals) alone is 863 lines — 57% of the file. Editing a single deal valuation or scorecard means navigating past hundreds of unrelated content. Future goal: link deal sections to Dealroom data.

## Current structure

| Block | Lines | Size |
|-------|-------|------|
| CSS (inline `<style>`) | 7–438 | 431 lines |
| Shell (topbar + nav) | 442–464 | 22 lines |
| ACT 1 — This Week | 467–542 | 75 lines |
| ACT 2 — Live Deals | 544–1384 | **840 lines** |
| ACT 3 — Pipeline | 1386–1430 | 44 lines |
| ACT 4 — Timeline | 1432–1488 | 56 lines |
| Footer | 1491–1496 | 5 lines |
| JS (inline `<script>`) | 1498–1603 | 105 lines |

### ACT 2 internal structure (the hard part)

DOM is grouped **by view**, not by deal. Each view-group (`vgroup`) contains all deals:

```
vgroup[onepager]    → deal-panel#deal-fox, #deal-mantis, #deal-mouse, #deal-cat
vgroup[scorecard]   → cdd-deal#cdd-overview, #cdd-fox, #cdd-mantis, #cdd-mouse, #cdd-cat
vgroup[su]          → su-deal#su-overview, #su-fox, #su-mantis, #su-mouse, #su-cat
vgroup[valuation]   → val-deal#val-fox, #val-mantis, #val-mouse, #val-cat
vgroup[dd]          → ddi-deal#ddi-fox, #ddi-mantis, #ddi-mouse, #ddi-cat
```

Per-deal content footprint:
- Fox: ~182 lines (onepager 65 + scorecard 33 + S&U 49 + valuation 30 + DD 5)
- Mantis: ~188 lines
- Mouse: ~171 lines
- Cat: ~174 lines
- Overview (cross-deal comparisons): ~75 lines
- ACT 2 shell (toggle bar + view switch): ~25 lines

## Approach: Python string assembly with per-deal files

### Why not Jinja2

Independent review flagged: the only Jinja2 feature used would be `{% include %}`. Python string assembly achieves the same with zero new dependencies.

### File structure

```
boardroom/
  templates/
    shell-top.html              ← <html><head> CSS, topbar, nav          (~470 lines)
    shell-bottom.html           ← footer + <script>JS</script>           (~115 lines)
    sections/
      act1-thisweek.html        ← weekly updates + decisions               (75 lines)
      act2-shell.html           ← section band + toggle bar + view switch  (25 lines)
      act3-pipeline.html        ← funnel + portfolio table                 (44 lines)
      act4-timeline.html        ← closing milestones                       (56 lines)
    deals/
      _overview.html            ← cross-deal comparison tables             (75 lines)
      fox.html                  ← all Fox content (5 views)              (~182 lines)
      mantis.html               ← all Mantis content                     (~188 lines)
      mouse.html                ← all Mouse content                      (~171 lines)
      cat.html                  ← all Cat content                        (~174 lines)
```

**Total: 11 files**, largest ~188 lines. No file exceeds 200 lines of content (shell-top is mostly CSS).

### Deal file format

Each deal file contains 5 labeled HTML fragments separated by section markers:

```html
<!-- ONEPAGER -->
<div class="deal-panel" id="deal-fox">
  ...
</div>

<!-- SCORECARD -->
<div class="cdd-deal" id="cdd-fox">
  ...
</div>

<!-- SU -->
<div class="su-deal" id="su-fox">
  ...
</div>

<!-- VALUATION -->
<div class="val-deal" id="val-fox">
  ...
</div>

<!-- DD -->
<div class="ddi-deal" id="ddi-fox">
  ...
</div>
```

### Assembly logic (~40 lines in api.py)

The assembly code:
1. Reads each deal file
2. Splits on `<!-- SECTION_NAME -->` markers into a dict `{onepager: ..., scorecard: ..., su: ..., valuation: ..., dd: ...}`
3. Builds ACT 2 by injecting deal fragments into vgroup containers (preserving current DOM structure exactly)
4. Concatenates shell-top + act1 + assembled-act2 + act3 + act4 + shell-bottom

```python
import re, os
from fastapi.responses import HTMLResponse

_TPL = os.path.join(os.path.dirname(__file__), "..", "templates")
_SECTIONS = ("ONEPAGER", "SCORECARD", "SU", "VALUATION", "DD")
_VGROUP_MAP = {
    "ONEPAGER": "onepager", "SCORECARD": "scorecard",
    "SU": "su", "VALUATION": "valuation", "DD": "dd",
}
_DEALS = ["_overview", "fox", "mantis", "mouse", "cat"]

def _read(path):
    return open(os.path.join(_TPL, path), encoding="utf-8").read()

def _parse_deal(filename):
    raw = _read(f"deals/{filename}.html")
    parts = {}
    current = None
    buf = []
    for line in raw.splitlines(True):
        m = re.match(r"^<!--\s*(ONEPAGER|SCORECARD|SU|VALUATION|DD)\s*-->", line)
        if m:
            if current:
                parts[current] = "".join(buf)
            current = m.group(1)
            buf = []
        else:
            buf.append(line)
    if current:
        parts[current] = "".join(buf)
    return parts

def _assemble_act2():
    shell = _read("sections/act2-shell.html")
    deals = {name: _parse_deal(name) for name in _DEALS}
    vgroups = []
    for sec in _SECTIONS:
        vg = _VGROUP_MAP[sec]
        active = ' active' if sec == "SCORECARD" else ''
        cls = ' cdd-wrap' if sec == "SCORECARD" else ''
        content = "".join(d.get(sec, "") for d in deals.values())
        vgroups.append(
            f'<div class="{cls} vgroup{active}" data-vg="{vg}">\n{content}</div>'
        )
    return shell + "\n".join(vgroups) + "\n</div>\n</section>"

def _assemble_investor():
    act2 = _assemble_act2()
    parts = [_read("shell-top.html"), _read("sections/act1-thisweek.html"),
             act2, _read("sections/act3-pipeline.html"),
             _read("sections/act4-timeline.html"), _read("shell-bottom.html")]
    return HTMLResponse("".join(parts))

@app.get("/")
def index():
    return _assemble_investor()
```

### Weekly edit map

| Weekly task | File to edit | Size |
|-------------|-------------|------|
| Update tiles (what happened this week) | `sections/act1-thisweek.html` | 75 lines |
| Update decision table | `sections/act1-thisweek.html` | 75 lines |
| Update Fox financials/scorecard/S&U/DD | `deals/fox.html` | 182 lines |
| Update Mantis data | `deals/mantis.html` | 188 lines |
| Update Mouse data | `deals/mouse.html` | 171 lines |
| Update Cat data | `deals/cat.html` | 174 lines |
| Update cross-deal comparison tables | `deals/_overview.html` | 75 lines |
| Add/remove a deal tab | `sections/act2-shell.html` + new deal file | 25 lines |
| Update funnel numbers | `sections/act3-pipeline.html` | 44 lines |
| Update portfolio table | `sections/act3-pipeline.html` | 44 lines |
| Move/add timeline milestones | `sections/act4-timeline.html` | 56 lines |
| Change call date in header | `shell-top.html` | line 1 |

### Adding a new deal

1. Create `deals/newdeal.html` using any existing deal file as template
2. Add deal to `_DEALS` list in api.py
3. Add tab button in `act2-shell.html`
4. Add rows to `_overview.html` comparison tables

### Cross-references

- ACT 1 decision links (`#cdd-mouse`, `#su-fox`) → work unchanged (assembled DOM has all IDs)
- JS deal/view toggle → works unchanged (DOM structure is identical after assembly)
- Portfolio table in ACT 3 → independent, no code link to ACT 2

### Dealroom linkage (future)

Per-deal files map 1:1 to Dealroom deal records. Future path:
- `assemble.py` generates deal HTML fragments from Dealroom/Cockpit DB data
- Writes to `deals/{codename}.html`
- Weekly update = run `assemble.py`, review output, commit
- Eventually: serve directly from DB without intermediate files

## Independent review notes (Sonnet)

Accepted:
- Jinja2 unnecessary → using Python string assembly
- Migration needs diff check → added
- Need rollback plan → keeping .bak

Rejected:
- "Comment markers solve it" → doesn't reduce cognitive load, user wants a real split
- "AI editor experience is worse" → 170-line deal files are far better than scrolling 1,600

Acknowledged:
- Long-term fix is data-driven assembly via `assemble.py` → noted as future direction

## Migration checklist

1. [ ] Git-tag current working state
2. [ ] Create `templates/` directory structure (sections/ + deals/)
3. [ ] Extract shell-top and shell-bottom from index.html
4. [ ] Extract ACT 1, ACT 3, ACT 4 into section files
5. [ ] Extract ACT 2 shell (toggle + view switch)
6. [ ] Extract each deal's content across all 5 views into per-deal files with section markers
7. [ ] Extract overview comparison content into `_overview.html`
8. [ ] Write assembly code in api.py
9. [ ] **Diff check**: assembled HTML output vs original index.html — must produce identical DOM
10. [ ] Keep `static/index.html` as `.bak` for one weekly cycle
11. [ ] Browser verification: all 4 acts render, agenda nav, deal tabs, view switch, decision links, portfolio sum
12. [ ] First weekly update using new structure — confirm editing workflow
