# M14: Serienbriefe Cohort Full Ingest + Outreach Status Model

## Summary

Ingest all 378 Serienbriefe companies as full pipeline records with Briefaktion cohort tags (BA1–BA7), granular outreach status, and clean data model. This makes post-outreach tracking possible in the dashboard and fixes the data quality issue where Serienbriefe records existed only as a dedup reference.

---

## Scope

1. **`ingest-serienbriefe` command** — new pipeline command reading full Serienbriefe sheet columns, upserting into pipeline.db with: `briefaktion`, `outreach_status`, contact fields, klass (A/B/C/E/S only — not D), MA count, address, owner details.
2. **BA cohort mapping** — 7 distinct send dates → BA1–BA7 labels.
3. **Granular outreach status model** — replaces coarse `sent/replied/meeting/declined` with: `sent / followup1 / followup2 / contact / meeting / financials / offer / deal / hold / declined`.
4. **Data model fix** — `fix_approached_bulk` (audit-dedup) must not set `outreach_status`. Only `ingest_serienbriefe` owns `outreach_status` for BA records. Cleared 39 spurious `outreach_status='sent'` records from name-matched ORBIS records.
5. **D-classification exclusion** — Serienbriefe "D" in Category column = post-outreach response tracking, not pipeline classification. Never imported as klass=D. Set klass=B for 88 BA5–7 records that had been wrongly set to D.
6. **Dashboard updates** — BA filter bar, briefaktion_counts with granular status groups, `outreach_breakdown` in data payload, "approached" now counts `briefaktion IS NOT NULL` (not `outreach_status IS NOT NULL`).

---

## Locked decisions

1. **`_FU_STATUS_MAP`** — explicit mapping of every Serienbriefe FU status string to granular internal value. Unknown strings fall back to `"sent"`.
2. **`upsert_serienbriefe_record`** — `outreach_status = :outreach_status` (always overwrite, not COALESCE) because Serienbriefe sheet is the authoritative source for these records. Klass uses COALESCE (preserve any AI classification done post-ingest).
3. **"Approached" KPI definition** — `briefaktion IS NOT NULL`. Name-matched records with `already_approached=1` but no `briefaktion` are dedup-gated only; they do not count as tracked outreach.
4. **Status groups for KPIs:**
   - No Response: `{sent, followup1, followup2}`
   - Positive: `{contact, meeting, financials, offer, deal}`
   - Neutral: `{hold}`
   - Negative: `{declined}`
   - Positive Response Rate = Positive / Total Approached
   - Total Answer Rate = (Positive + Neutral + Negative) / Total Approached

---

## AI validation results

Run 2026-03-28:

- `python pipeline.py ingest-serienbriefe` → 367 updated, 0 inserted, 11 skipped (no domain)
- Outreach breakdown post-ingest: followup1=164, followup2=101, declined=40, contact=28, meeting=26, hold=5, financials=3 → **Total=367** (matches Serienbriefe)
- Positive Response Rate: 57/367 = **15.5%**
- `python pipeline.py dashboard --dry-run` → 5,100,840 chars, 0 errors
- `fix_approached_bulk` no longer sets `outreach_status` — confirmed by code review
- 39 spurious `outreach_status` records cleared from name-matched ORBIS records
- `python -m pytest tests/ -q` → 162 passed
