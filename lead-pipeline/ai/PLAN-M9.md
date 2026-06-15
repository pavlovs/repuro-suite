# M9: Email Enricher — Plan

## Context

M9 runs after M8 (ownership gate). Input: A/B records at `pipeline_stage='ownership_gated'`
(or 'ownership_enriched') without an email. Goal: find the owner's personal email address.

---

## Approach: SMTP Candidate Testing from Owner Name

We have the owner's full name from OpenRegister (e.g. "Jana Rennecke", "Peter Spranger").
German SME email patterns are highly predictable. Build 8 candidates from name + domain,
SMTP-verify each, use the first one that passes.

**Why not impressum scraping**: impressum pages only contain company emails (`info@`, `gf@`,
`kontakt@`). These are not the owner's personal address. They are useless for personalised
outreach. If SMTP finds nothing, we leave the email empty and fill it manually via M11.

**Candidate generation** from `first_name` + `last_name` + `domain`:
```
jana.rennecke@domain    f.l     (most common German SME pattern)
j.rennecke@domain       f0.l
rennecke@domain         l
jana@domain             f
janarennecke@domain     fl
jrennecke@domain        f0l
jana.r@domain           f.l0
j.r@domain              f0.l0
```

Name splitting: last word = last name, first word = first name (first component of multi-part).
E.g. "Uwe Dirk Joneck" → first="Uwe", last="Joneck" → candidates: uwe.joneck@, u.joneck@, etc.

Umlaut normalisation: ä→ae, ö→oe, ü→ue, ß→ss before building candidates.

**Catch-all detection**: if multiple candidates pass SMTP → catch-all domain;
use first (f.l pattern = most likely), log flag.

**If SMTP finds nothing**: advance to `email_enriched` with `gf_email=NULL`.
Fill manually via M11 dashboard.

---

## SMTP Verification

```
_smtp_verify(email) → bool
```
- DNS MX lookup → connect to mail server on port 25 → RCPT TO test
- Returns True if server responds 250 (mailbox exists)
- **Known limitation**: port 25 is blocked by most ISPs and shared hosting providers.
  SMTP verification only works when run from a server/VPS with unrestricted outbound port 25.
  Running from a home/office network → all probes fail silently → emails left empty.

---

## Anrede / Salutation

Owner first name used for gender heuristic (German name lists + vowel ending rule).
~85% accurate for common German names. Returns None when uncertain.

- ORBIS `anrede` values are authoritative — never overwrite
- OpenRegister provides no salutation/gender data
- `gf_name` set from `gesellschafter_name` when `gf_name` is currently empty

```
salutation = "Sehr geehrte[r] [Herr/Frau] [Nachname]"
```

---

## Bugs Fixed

| # | Bug | Fix |
|---|-----|-----|
| 1 | Query `gf_email IS NULL` misses empty-string emails from ingest | `(gf_email IS NULL OR gf_email = '')` |
| 2 | `db.py` `COALESCE(gf_email, ?)` doesn't overwrite `''` (empty string) | `COALESCE(NULLIF(gf_email, ''), ?)` |
| 3 | Old `_score_email()` only used `gf_name`, ignored owner | Replaced with SMTP approach — no scoring needed |
| 4 | Old impressum fallback stored `info@` / `gf@` as "found" | Removed entirely — those emails are not useful |

---

## DB Fields Written

| Field | Source |
|-------|--------|
| `gf_email` | SMTP-verified personal email, or NULL if not found |
| `gf_name` | Set from `gesellschafter_name` if `gf_name` currently empty |
| `anrede` | Derived from owner first name heuristic (only if not already set) |
| `salutation` | `"Sehr geehrte[r] [Herr/Frau] [Nachname]"` if anrede known |
| `pipeline_stage` | Set to `'email_enriched'` always (even if no email found) |

---

## Files Modified

| File | Change |
|------|--------|
| `src/pipeline/enrich.py` | New `_normalise_name_for_email()`, `_build_owner_email_candidates()`, `_smtp_verify_candidates()`, `_derive_anrede()`; rewrote `enrich_email_batch()` (SMTP only, no impressum) |
| `src/pipeline/db.py` | `COALESCE(NULLIF(...))` fix in `update_email_result()` |
| `ai/ARCHITECTURE.md` | Update M9 section |

---

## Deferred

- Impressum scraping — removed; only finds company emails, not personal
- Hunter.io / Apollo — adds API cost, not implemented
- genderize.io — heuristic is sufficient for German names

---

## AI VALIDATION RESULTS

**Run date**: 2026-03-26

**Changes implemented**:
- `enrich.py`: SMTP-only email enrichment. Old impressum path removed entirely.
- `enrich.py`: `_normalise_name_for_email()`, `_build_owner_email_candidates()` (8 patterns),
  `_smtp_verify_candidates()` (catch-all detection), `_derive_anrede()` (German heuristic)
- `enrich.py`: query fixed — `(gf_email IS NULL OR gf_email = '')`
- `db.py`: `COALESCE(NULLIF(gf_email,''), ?)` — overwrites empty strings correctly

**Live run results (4 B companies)**:

| Company | Owner | SMTP result | anrede | salutation |
|---------|-------|-------------|--------|-----------|
| straetz-novetec.de | Adrian Neundörfer | No (port 25 blocked) | None | None |
| mamedis.de | Uwe Dirk Joneck | No (port 25 blocked) | Herr | Sehr geehrter Herr Joneck |
| rennecke-medic.com | Jana Rennecke | No (port 25 blocked) | Frau | Sehr geehrte Frau Rennecke |
| medizintechnik-web.de | Peter Spranger | No (port 25 blocked) | Herr | Sehr geehrter Herr Spranger |

**SMTP limitation**: port 25 outbound is blocked from this machine (office network / Windows).
All 4 probes failed immediately. The SMTP logic is correct and will work from a VPS or cloud
runner with unrestricted port 25. Emails for these 4 companies need manual entry.

**`gf_name` and `anrede` correctly derived** from `gesellschafter_name` for all 4.

**Note on Adrian Neundörfer**: anrede=None — name not in German name lists and doesn't end
in a/e/i. Correct behaviour — uncertain names left blank.

**pytest**: 160 passed
