# Letter Readiness Session — 2026-03-31

**Goal:** End user generates a fully fledged, ready-to-export letter from this tool.
**Current verdict:** NOT SHIPPABLE. Maximum readiness is 77% (field count), with structural issues preventing letter quality even for "best" records.

---

## PM Assessment — Current State

### What "60–77%" Actually Means

The readiness % was computed against 9 fields. It **did not** penalize:
- `owner_name` with no first name (single-word entries like 'Andersson')
- `full_name` with ORBIS encoding errors ('Zubehoervertrieb' instead of 'Zubehörvertrieb')
- `gesellschafter_name` / `owner_name` mismatch (different people)

True readiness, accounting for letter quality, is lower than displayed.

### Blocking Issues by Category

| Issue | Affects | Type | Fix |
|-------|---------|------|-----|
| `leistung_absatz_2` NULL | 24/24 records | CLI backfill | `backfill-leistung` |
| `mehrwerte` NULL | 24/24 records | CLI backfill | `backfill-leistung` |
| `gf_email` NULL | 24/24 records | SMTP blocked | Known deferred |
| `owner_name` = single word (no Vorname) | 5 records | Data quality | Manual edit in dashboard |
| `owner_name` = EMPTY | 1 record (schmid-medizintechnik.de) | Data quality | Manual entry |
| `owner_name` = legal entity | 3+ records | Manual review | Pick person from shareholder list |
| `anrede`/`salutation` missing | 6 records | Derives from owner_name | Fix owner_name first |
| `full_name` umlaut encoding wrong | 1+ records | Impressum mismatch | `impressum_name` override + M20 |
| `owner_name` ≠ `gesellschafter_name` | Several records | Ambiguity | UI: show both, let user pick |
| `street`/`plz_ort` missing | 3 records | ORBIS gap | Manual entry or M20 impressum |
| Completeness check missing Vorname check | All records | Dashboard bug | Code fix |
| "GF-E-Mail" label wrong | Dashboard | UI bug | Code fix |
| Shareholder % not shown in side panel | Dashboard | UI gap | Code fix |

---

## Per-Record Status (24 unapproached A/B, 2026-03-31 pre-session)

| Domain | Klass | Owner Name | Issue |
|--------|-------|------------|-------|
| praximed.com | A | Katja Nadine Flegel-Wolf ✓ | Missing: email, l2, mehrwerte |
| reintjes.de | A | Achim Graef ✓ | Missing: email, l2, mehrwerte |
| roentgen-bender.de | A | Dirk Bender ✓ | Missing: email, l2, mehrwerte |
| krolicki-med.de | A | Krolicki Verwaltungs GmbH ❌ | Corporate owner — anrede/salutation missing |
| aed-defibrillator.kaufen | B | Holger Koenig ✓ | Missing: email, l2, mehrwerte |
| consu-med.de | B | Matthias Kaiser ✓ | Missing: email, l2, mehrwerte |
| inmedi-service.com | B | Alexander Seidel ✓ | Missing: email, l2, mehrwerte |
| mamedis.de | B | Uwe Dirk Joneck ✓ | Missing: email, l2, mehrwerte, street, plz_ort |
| mediservice-magdeburg.de | B | Patrick Kabelich ✓ | Missing: email, l2, mehrwerte |
| medizintechnik-berlin-gmbh.de | B | **Andersson** ⚠ | Single word; gs=Michael Fratzscher(46%); full_name encoding wrong |
| medizintechnik-puzicha.de | B | **Graef** ⚠ | Single word; gs=Companion Consulting GmbH(50%) — corporate owner |
| medizintechnik-web.de | B | Peter Spranger ✓ | Missing: email, l2, mehrwerte, street, plz_ort |
| medtec-berlin.com | B | Marcus Horn ✓ | Missing: email, l2, mehrwerte |
| meetb.de | B | **Knickenberg** ⚠ | Single word; gs=Asker Germany Holding (PE?); NO compliments at all |
| mtj.de | B | Thomas Haase ✓ | Missing: email, l2, mehrwerte; gs=Haase Beteiligung Holding |
| mtsmedizintechnik.de | B | Michael Schuster ✓ | Missing: email, l2, mehrwerte |
| pxlmd.com | B | Jörg Szymanski ✓ | Missing: email, l2, mehrwerte |
| rennecke-medic.com | B | Jana Rennecke ✓ | Missing: email, l2, mehrwerte, street, plz_ort |
| schmid-medizintechnik.de | B | **EMPTY** ❌ | No owner at all; no anrede/salutation |
| straetz-novetec.de | B | Adrian Neundörfer ✓ | Missing: l2, compliment_2; no scraped text |
| z-h.de | B | Zuther & Hautmann Verwaltungsgesellschaft ❌ | Full legal entity name; corporate |
| distler.de | B | **Distler** ⚠ | Single word; no gs data |
| drepharm.de | B | **Hauptmann** ⚠ | Single word; gs=GKS Management GmbH (corporate) |
| ka-med.de | B | KAMED Verwaltungs GmbH ❌ | Corporate owner |

**Records ready for letter after CLI backfill (needs only email + manual approval):**
praximed.com, reintjes.de, roentgen-bender.de, aed-defibrillator.kaufen, consu-med.de, inmedi-service.com, mediservice-magdeburg.de, medizintechnik-web.de (no address), medtec-berlin.com, mtsmedizintechnik.de, pxlmd.com, rennecke-medic.com (no address)

**Records needing manual owner resolution first:**
krolicki-med.de, medizintechnik-berlin-gmbh.de, medizintechnik-puzicha.de, meetb.de, schmid-medizintechnik.de, z-h.de, distler.de, drepharm.de, ka-med.de

---

## Session Work Plan

### Completed ✅
- [x] PM document (this file)
- [x] Dashboard label fix: "GF-E-Mail" → "E-Mail"
- [x] Dashboard: gesellschafter_share_pct shown in side panel with "≠ Brief" conflict indicator
- [x] Dashboard: owner_name vs gesellschafter_name both visible, user picks manually
- [x] Dashboard: impressum_name field (writeback input + "≠ ORBIS" badge when set)
- [x] Dashboard: completeness check adds Vorname (hasFirstAndLast) check — 10 fields, was 7
- [x] Dashboard: letter preview uses impressum_name override with "(Impressum)" badge
- [x] DB: `impressum_name` column added via forward migration
- [x] Backfill bug fix: CASE WHEN per-field UPDATE (old code blocked all 24 records)
- [x] CLI: backfill-leistung run — 23/24 records now have leistung_absatz_2 + mehrwerte
  - straetz-novetec.de: 0 (no scraped_text, cannot auto-fill)
- [x] CLI: backfill-compliments running for missing K1/K2
- [x] Test script: `scripts/letter_readiness_check.py`
- [x] models.py: impressum_name field added
- [x] export.py: Name Briefkopf uses impressum_name when set

### Post-Session State (2026-03-31, after backfill)
- Tests: **288 passed**
- NEAR-READY (90%+): **12 records**
- IN PROGRESS (60-89%): **11 records**
- BLOCKED (<60%): **1 record** (meetb.de — PE-backed)
- Estimated records meeting all 13 content criteria: **9-10** (pending compliments backfill + impressum_name for 3)
- Remaining manual work: fix owner_name for 9 records in dashboard, impressum_name for 3 records

---

## What "Shippable" Means (Definition of Done for Letter Tool)

A record is **export-ready** when ALL of these are true:
1. `owner_name` has first AND last name (not a legal entity)
2. `anrede` set (Herr/Frau)
3. `salutation` set ("Sehr geehrter/e Herr/Frau [Nachname]")
4. `leistung_text` set (short form)
5. `leistung_absatz_2` set (second paragraph company description)
6. `mehrwerte` set (value proposition for this company)
7. `compliment_draft` (K1) set
8. `compliment_2` (K2) set
9. `region_prep` set ("in Berlin", "im Allgäu" etc.)
10. `street` set
11. `plz_ort` set
12. `full_name` / `impressum_name` correctly spelled
13. `approved_for_sendout` = 1 (Roman manually approves)
14. Email: nice-to-have but NOT a blocker (can send physical letter)

After session: **0/24 fully approved** (no record has approved_for_sendout=1 yet).
Content-complete (criteria 1-12, excl. approval): estimated **9-10** after compliments backfill finishes.
Remaining blockers: 9 records need manual owner_name fix; 3 need impressum_name; straetz-novetec.de needs scraped text.
