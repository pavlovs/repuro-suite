# ALLEX QA Agent — Automated Usability Test Spec

## Purpose

An agentic workflow that opens the ALLEX dashboard in `--serve` mode, clicks through all ~70 exportable records like a human reviewer would, tests every feature and interaction, identifies UI bugs and missing functionality, and produces a structured report. Goal: validate that ALLEX is ready for Flo's final review of the send-out batch.

This is NOT data validation (that's a DB query). This is **UI/UX testing** — does the tool work correctly when a human uses it?

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Dashboard      │◄────│  Chrome DevTools MCP  │◄────│  QA Agent       │
│  --serve :8080  │     │  (browser automation) │     │  (Claude Code)  │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                                                            │
                                                            ▼
                                                     ┌─────────────────┐
                                                     │  QA Report      │
                                                     │  (markdown)     │
                                                     └─────────────────┘
```

- Dashboard runs live: `python pipeline.py dashboard --profile profiles/medtech_germany.json --serve --port 8080`
- QA Agent is a Claude Code subagent with Chrome DevTools MCP access
- Agent navigates via `evaluate_script` (fast, JS-level checks) and `click`/`take_screenshot` (visual checks)

## Test Strategy

### Efficiency: JS-batch first, visual-spot-check second

Clicking 70 records × 20 checks = 1400 tool calls = too expensive. Instead:

**Phase 1 — JS sweep (single evaluate_script call):**
Run a JS function that iterates all records in `DATA.records`, checks field completeness, cross-field consistency, and status logic. Returns a structured JSON of per-record issues. This covers ~80% of validation in one tool call.

**Phase 2 — Interactive smoke test (5-8 representative records):**
Pick records that cover each edge case (all-green, missing fields, ownership review, salutation mismatch, etc.). Actually navigate to each, interact with buttons, verify rendering, take screenshots.

**Phase 3 — Feature-level interaction test:**
Test each feature once on an appropriate record: Prüfen button, → Brief button, Anrede change, salutation regen, collapse/expand, Freigabe toggle, export PDF, queue search, queue sort, tab switching.

## Phase 1: JS Sweep — Field & Logic Validation

Single `evaluate_script` call that returns per-record issues:

```js
() => {
  var results = [];
  var exportable = DATA.records.filter(r =>
    ['A','B','C','E'].includes(r.klass) &&
    !r.already_approached &&
    (r.filter_pass === 1 || r.filter_pass === null) &&
    r.pipeline_stage !== 'ingested'
  );

  exportable.forEach(r => {
    var issues = [];

    // --- Required Serienbriefe fields ---
    var required = {
      'owner_name': 'Ansprechpartner',
      'anrede': 'Anrede',
      'salutation': 'Salutation',
      'street': 'Straße',
      'plz_ort': 'PLZ+Stadt',
      'full_name': 'Firmenname',
      'leistung_text': 'Leistung 1',
      'compliment_draft': 'Kompliment 1',
      'compliment_2': 'Kompliment 2',
      'mehrwerte': 'Mehrwerte',
    };
    Object.keys(required).forEach(f => {
      if (!r[f] || !String(r[f]).trim()) issues.push('MISSING: ' + required[f]);
    });

    // --- Cross-field consistency ---
    var ownerSurname = (r.owner_name || '').trim().split(/\s+/).pop();
    if (ownerSurname && r.salutation && !r.salutation.includes(ownerSurname)) {
      issues.push('MISMATCH: Salutation "' + r.salutation + '" vs Ansprechpartner "' + r.owner_name + '"');
    }
    if (r.anrede && r.salutation) {
      var expectedPrefix = r.anrede === 'Herr' ? 'Sehr geehrter Herr' : 'Sehr geehrte Frau';
      if (!r.salutation.startsWith(expectedPrefix)) {
        issues.push('MISMATCH: Salutation prefix should be "' + expectedPrefix + '"');
      }
    }

    // --- Ownership issues ---
    if (r.pipeline_stage === 'ownership_review_needed') {
      var gs = []; try { gs = JSON.parse(r.all_gesellschafter || '[]'); } catch(e) {}
      var hasUnresolved = gs.some(o => o.type === 'legal_person');
      if (hasUnresolved) issues.push('OWNERSHIP: Unresolved legal person in owners');
    }

    // --- Letter preview data ---
    if (!r.region_prep) issues.push('SOFT: Region Brieftext empty (letter will show [region_prep fehlt])');
    if (r.compliment_draft && r.compliment_draft.length < 20) issues.push('QUALITY: Kompliment 1 suspiciously short');
    if (r.compliment_2 && r.compliment_2.length < 20) issues.push('QUALITY: Kompliment 2 suspiciously short');

    // --- Gesellschafter age on legal entity ---
    if (r.gesellschafter_age && r.gesellschafter_age < 1940) {
      var gs2 = []; try { gs2 = JSON.parse(r.all_gesellschafter || '[]'); } catch(e) {}
      if (gs2.length > 0 && gs2[0].type === 'legal_person') {
        issues.push('BUG: gesellschafter_age shown for legal entity');
      }
    }

    var status = issues.length === 0 ? 'READY' :
                 issues.some(i => i.startsWith('MISSING') || i.startsWith('MISMATCH') || i.startsWith('OWNERSHIP')) ? 'BLOCKED' : 'SOFT';

    results.push({
      domain: r.domain,
      full_name: r.full_name,
      klass: r.klass,
      approved: !!r.approved_for_sendout,
      status: status,
      issues: issues
    });
  });

  return {
    total: results.length,
    ready: results.filter(r => r.status === 'READY').length,
    blocked: results.filter(r => r.status === 'BLOCKED').length,
    soft: results.filter(r => r.status === 'SOFT').length,
    records: results
  };
}
```

### Phase 1 output:
```
=== ALLEX QA Sweep: 70 records ===
READY: 45 | BLOCKED: 18 | SOFT ISSUES: 7

BLOCKED records:
  aplusm-care.de (A+M GmbH) — MISSING: E-Mail
  laborunion-shop.de (MED LaborUnion) — MISMATCH: Salutation vs Ansprechpartner
  ...
```

## Phase 2: Interactive Smoke Test

Select 5-8 records covering these categories:

| Category | Selection criteria | What to test |
|----------|-------------------|--------------|
| All-green | approved, no missing fields | Banner shows green cards, Freigegeben ✓ |
| Missing fields | 2+ missing required fields | Red status cards, "fehlt:" in section titles, fields highlighted |
| Salutation mismatch | owner_name surname ≠ salutation | Brief card red, warning shown, Regen button works |
| Ownership review | pipeline_stage = ownership_review_needed | Prüfen button visible, red border on holding, Gesellschafter card red |
| Resolved ownership | has parent_owners | Indented sub-owners shown, no red border, UBO highlighted |
| Legal entity owner | first owner is legal_person | No birthyear shown, "Unternehmen" label |
| Single owner | only 1 gesellschafter | Clean single-row display |
| No gesellschafter | all_gesellschafter empty | Fallback display, no crash |

For each selected record:
1. Navigate via `evaluate_script`: `activeIdx = X; renderRecord();`
2. `take_screenshot` — visual check of full layout
3. Check banner: status cards colors, approve button text, company name
4. Check each section: correct class (has-issues / needs-review / reviewed), title text, collapsed state
5. Check letter preview: click "Brief-Vorschau" tab, verify letter renders, no [fehlt] placeholders

## Phase 3: Feature Interaction Tests

Test each feature ONCE on an appropriate record:

| # | Feature | How to test | Pass criteria |
|---|---------|-------------|---------------|
| 1 | **→ Brief button** | Click on a natural person's → Brief | owner_name updates, salutation regenerates, Grund shows source |
| 2 | **Anrede dropdown** | Change Herr→Frau | Salutation prefix changes to "Sehr geehrte Frau" |
| 3 | **Salutation Regen** | Click ↺ Regen on mismatch record | Salutation rebuilt from current Anrede + owner_name |
| 4 | **Region Auto-fill** | Click ↺ Auto-fill | region_prep populates from region mapping |
| 5 | **Kompliment Regen** | Click ↺ Regen on Kompliment 1 | API call, new text appears (serve mode only) |
| 6 | **Freigabe toggle** | Click Freigeben, then click again to un-approve | Button toggles, section titles update, status cards update |
| 7 | **Prüfen button** | Click on unresolved holding (clavaro.de) | Toast shows, sub-owners appear or error shown |
| 8 | **Eigenständig button** | Click "Eigenständig ✓" | Record moves to ownership_gated, Gesellschafter card updates |
| 9 | **Collapse/expand** | Click section title | Section collapses, collapsed-hint visible, no inner border line |
| 10 | **Section review toggle** | Click ✓ button on section | Section border turns green, status card updates |
| 11 | **Queue search** | Type partial company name | Queue filters correctly |
| 12 | **Queue sort** | Click "Fast fertig" / "Am stärksten blockiert" | Queue reorders |
| 13 | **Tab switch** | Click "Website" tab | Iframe loads or fallback shows |
| 14 | **Prev/Next nav** | Click arrows | Record changes, banner updates, letter preview updates |
| 15 | **Export PDF** | Click Export PDF with eligible records | Download triggers (serve mode) |
| 16 | **Klass change** | Change A→B via dropdown | Queue item updates, record stays selected |
| 17 | **Field save** | Edit a text field, navigate away, come back | Value persisted (serve mode) |

## Report Format

Output: `ai/QA-REPORT-{date}.md`

```markdown
# ALLEX QA Report — {date}

## Summary
- Records tested: 70
- Ready for send-out: 45 (64%)
- Blocked: 18 (26%)
- Soft issues: 7 (10%)
- UI bugs found: X
- Features passing: Y/17

## Blocked Records
| Domain | Company | Issues |
|--------|---------|--------|
| ... | ... | MISSING: Straße, PLZ |

## UI Bugs Found
1. [BUG] Description — screenshot: qa-screenshot-N.png
2. ...

## Feature Test Results
| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | → Brief button | ✅ PASS | |
| 2 | Anrede dropdown | ❌ FAIL | Salutation not updating |
| ... |

## Recommendations
- Feature X needs fix before Flo review
- Y records need manual attention for Z reason
- Consider adding feature W for the send-out workflow
```

## How to Run

```bash
# Terminal 1: Start dashboard
cd lead-pipeline
python pipeline.py dashboard --profile profiles/medtech_germany.json --serve --port 8080

# Terminal 2: Run QA agent (Claude Code)
# Navigate to http://localhost:8080 in Chrome first, then:
claude "Run the ALLEX QA agent per ai/QA-AGENT-SPEC.md"
```

The agent:
1. Opens Chrome to localhost:8080 via `navigate_page`
2. Runs Phase 1 JS sweep via `evaluate_script`
3. Selects Phase 2 records based on sweep results
4. Runs Phase 2 + 3 interactive tests
5. Writes report to `ai/QA-REPORT-{date}.md`
6. Screenshots saved to `ai/qa-screenshots/`

## Scope Boundaries

**In scope:** Testing that existing ALLEX features work correctly for the 70-record send-out workflow.

**Out of scope:**
- Auto-fixing data issues (that's a separate batch-fix script)
- Testing the Lead-Liste tab (not part of BA-Prep workflow)
- Performance testing
- Testing with multiple concurrent users
- Testing the Änderungslog or Drop-off tabs

## Estimated Cost

- Phase 1: 1 evaluate_script call (~2k tokens)
- Phase 2: 8 records × (1 evaluate_script + 1 screenshot) = ~16 tool calls
- Phase 3: 17 feature tests × ~3 tool calls each = ~51 tool calls
- Total: ~70 tool calls, ~15 min runtime, ~100k tokens

## Success Criteria

The QA agent produces a report that answers:
1. How many of the 70 records are letter-ready right now?
2. What specific fields are missing on blocked records?
3. Are there any UI bugs that would prevent Flo from completing a review?
4. Do all interactive features (buttons, toggles, saves) work?
5. What features are missing that would make the workflow smoother?

## Reports

- First run: `ai/QA-REPORT-20260429.md` — 85 letter-ready, 8 sal mismatches, 3 UI bugs (1 medium, 2 low), 1 missing feature, 15/15 features passing
- UI issues logged to: `ai/UI-ISSUES.md` (Open section)
