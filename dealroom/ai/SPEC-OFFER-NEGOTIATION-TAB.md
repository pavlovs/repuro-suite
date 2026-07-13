# SPEC — Offer & Negotiation Tab (v2 rework) + Offer-History Data Layer

*2026-07-13. Scope: rebuild of the rejected v2 Negotiation tab as "Offer & Negotiation" (Screen 2 of the v2 UI rebuild, FIRST-SCREEN-SIGNOFF applies), plus the missing bucket-based offer-history layer in the negotiation tool. Absorbs negotiation-tool M3 (SPEC-negotiation-tool.md §9) and SPEC-DEALROOM-V2 §7.*

*STATUS 13.07 evening: BUILT + POPULATED, awaiting Roman sign-off on :8082. Implementation deviates from §5/§6 in ONE structural point: after the 13.07 rejection the rebuild pattern became "v1 visual language, standalone modules, old shell unregistered" (Screen 1 = ui_portfolio). The tab therefore ships as `v2/ui_negotiation.py` — a standalone v1-language page at `/deal/{code}/negotiation` — not as a tab inside the retired v2 shell; §5 layout/content and §2–§4/§6–§7 are implemented as specced (validator chip additionally suppressed for superseded/closed strategies). Population done for Cat, Lion, Fox, Mantis, Mouse + Aqua (§7 table superseded by actual source docs; Fox seed corrected against signed LOI).*

## 1. Problem

- v1 dashboard has an "Offer & Negotiation" section — a **mock-data wireframe** (src/templates/sections/offer-negotiation.js), never wired to real data. Its *shape* is right: offer summary band → offer round ledger with bucket columns → issue list (our vs. their position) → dated counter-notes.
- v2 has a Negotiation tab (ui_workspace.render_negotiation_tab) fed by real DB data, but it is a 10-section wall of prose tiles, mixed DE/EN labels — rejected 13.07 with the rest of the v2 UI.
- **Data gap**: offer history exists only as prose in `negotiation_rounds.we_gave/they_gave`. No table answers "how did Sofort/EO/salary move across rounds?" `deal_terms` (v2) holds *current* terms state only — no side, no event dates, no history rows.

## 2. Data model (negotiation tool fix — master = v1 `data/dealroom.db`, owner = `tools/negotiate_ops.py`)

Additive migration (CREATE TABLE IF NOT EXISTS / ALTER ADD COLUMN, DB backup first — §12.8 conventions):

```sql
CREATE TABLE IF NOT EXISTS negotiation_offers (
  id INTEGER PRIMARY KEY,
  strategy_id INTEGER NOT NULL REFERENCES negotiation_strategies(id),
  round_id INTEGER REFERENCES negotiation_rounds(id),   -- optional link to the round it happened in
  side TEXT NOT NULL CHECK(side IN ('ours','theirs')),
  date TEXT NOT NULL,                                    -- YYYY-MM-DD (strict, existing _valid_date)
  label TEXT NOT NULL,                                   -- 'NBO v1', 'Gegenvorschlag Golland', 'LOI v7', 'Zusage mod. Variante 2'
  status TEXT NOT NULL CHECK(status IN ('sent','received','accepted','signed','superseded','withdrawn')),
  source_doc TEXT,                                       -- citation discipline: file or mail the numbers come from
  note TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS negotiation_offer_terms (
  id INTEGER PRIMARY KEY,
  offer_id INTEGER NOT NULL REFERENCES negotiation_offers(id),
  term_key TEXT NOT NULL,        -- canonical bucket key, see §3
  label TEXT,                    -- display override (else canon label)
  value_num REAL,                -- bare number (unit lives in unit/headers, NEVER in the value)
  unit TEXT,                     -- 'K€' | '%' | 'x' | 'K€ p.a.' | NULL
  value_text TEXT,               -- non-numeric terms ('EBIT > 625 K€/Jahr', 'Variante B')
  note TEXT
);
ALTER TABLE negotiation_positions ADD COLUMN their_position TEXT;  -- seller stance per issue
ALTER TABLE negotiation_positions ADD COLUMN prio TEXT;            -- high|med|low (CLI-validated)
```

Status semantics: one event = one package on the table. `sent`/`received` = live on the table; `accepted` = agreement in principle (Cat 30.06); `signed` = signature-backed (LOIs — immutable like milestone terminal states); `superseded` = replaced by a later package; `withdrawn`. Guard: `signed` rows immutable; new events never UPDATE old ones (append-only ledger).

## 3. Canonical term buckets (fit our LOI structure; keys ALIGN with v2 `deal_terms.term_key`)

| term_key | Label | Unit | Notes |
|---|---|---|---|
| purchase_price_upfront | Sofort | K€ | Brutto-Sofortzahlung / EV closing |
| earnout_max | EO max | K€ | cap over all years |
| earnout_threshold | EO-Schwelle | K€ | EBIT/EBITDA floor p.a. (value_text if formula) |
| earnout_multiple | EO-Multiple | x | €/€ over threshold (2,75x Cat, 3x Mouse) |
| ev_total_max | Gesamt max | K€ | Sofort + EO max (+ RB) |
| rueckbeteiligung | Rückbeteiligung | K€ | |
| gf_salary | GF-Gehalt/Tantieme | K€ p.a. | seller comp post-close (135/140 Lion, 100+20 Mouse) |
| multiple | Multiple | x | implied on adj. EBITDA/EBIT |
| other | — | — | free rows: Kündigungsschutz, Miete, Bürgschaften, Exklusivität … (value_text) |

Everything the offer ledger table renders as columns comes from the first 8; `other` rows render as a note line under the event row. Same keys as deal_terms → render-time consistency check is a dict compare.

## 4. CLI contract (`negotiate_ops.py offer`, same conventions as milestone/open-item)

```
offer add    --strategy S --side ours|theirs --date YYYY-MM-DD --label L
             --status sent|received|accepted|signed [--round R] [--source-doc D] [--note N]
             --term "key=3400|K€"  --term "key=EBIT > 625 K€|note text"   (repeatable;
             value parses float→value_num else →value_text; 3rd pipe segment = note)
             German decimal commas accepted on input ("2,75") → stored as REAL 2.75.
offer list   --strategy S            (chronological, terms inline)
offer set-status --id N --status superseded|accepted|signed|withdrawn
             (signed = terminal/immutable; correcting a signed row = INSERT new event)
position add|list gains --their-position and --prio high|med|low
```

Existing guards apply: strict date validation, backup-before-migrate, idempotent migrate, no destructive updates.

## 5. Tab UX/UI (v2 route `/deal/{code}/negotiation`, label **"Offer & Negotiation"**)

Visual language = **approved v1 look** (portfolio/onepager): teal section titles (#0891B2), teal table header bars (white text), 12px cells, de-DE numbers, pill badges — implemented as CSS classes in shell-top.html (extend; NO inline styles). English UI chrome; German deal vocabulary (Sofort, EO-Schwelle) is domain language, allowed; no sentence-level DE/EN mixing. Units in headers, bare numbers in cells.

Layout top→down (answer-first):

1. **Summary band** (teal-tinted card): Current package total (`ev_total_max` from deal_terms agreed/locked) + structure one-liner (Sofort + EO max); strategy status badge (active/executing/closed); next milestone (date+label); open issues count; counterparty chip(s) → stakeholder pages. Validator chip ONLY if strategy has memo_md (no FAIL-wall for seeded deals without memo).
2. **Offer history** (the centerpiece): one row per offer event, chronological. Columns: Date | Side (Us/Seller badge) | Package (label) | Sofort (K€) | EO max (K€) | EO-Schwelle | EO-Mult (x) | GF-Gehalt (K€) | Gesamt (K€) | Status | Source. `other` terms + note render as a muted sub-line. Latest row bold; `signed`/`accepted` rows tinted. Empty bucket = "—". Consistency flag: if latest accepted/signed event's terms ≠ deal_terms current values → amber "terms ledger out of sync" chip (freshness principle).
3. **Issue list**: negotiation_positions as table: Issue | Our position (preferred, walk-away as tooltip-ish sub-line) | Their position | Prio | Status | Roman-confirm chip. Open first, resolved struck-through.
4. **Process row** (2-col grid): Milestones (deadline map, side + consequence) | Open items (Us/Seller, due, overdue in red).
5. **Rounds timeline** (compact): date, round no, channel, outcome headline; asked/gave pairs as sub-lines; self-rating chip. Collapsed styling, no wall of text.
6. **Strategy depth** (bottom, owner-only content anyway): goals/reservation/aspiration tiles, open objection bank, SELBST-CHECK lessons, memo (md-lite) — unchanged data, tightened rendering.

Tab visibility: owner-only (unchanged 403 gate); shown when strategy OR offer rows exist for the deal. Per-deal `terms` tab is absorbed into this tab (global /terms untouched).

## 6. v2 plumbing

- `v2/migrate_v1.py`: copy `negotiation_offers`, `negotiation_offer_terms`, new position columns (negotiation tables copy "as-is" per SPEC v2 §9).
- `v2/workspace.negotiation_payload`: + offers (with terms dict), + deal_terms current-state, + consistency flag, + next milestone; strategy selection: prefer `executing` > `active` > latest.
- `v2/ui_workspace.render_negotiation_tab`: full rewrite per §5.
- Tests: extend `v2/tests` (payload shape, route 200 with/without strategy, gating unchanged, consistency flag); extend `tools/tests/test_negotiate_ops.py` (offer add/list/set-status, signed immutability, comma-decimal parse, migrate idempotence with new tables).

## 7. Population (NBO+ deals) — every number source-cited or omitted

| Deal | Strategy | Offer events to ledger (source) |
|---|---|---|
| Cat | S3 executing (exists) | NBO → 07.05 full-acceptance package (R17 mail) → 09.06 3-variant MESO → 30.06 Zusage mod. Var 2 (Schröcke-Mail, accepted) → LOI v7 03.07 (ours, sent) |
| Lion | S1 superseded + rounds 1–13 exist; new active strategy for the 08.07 offer update | Angebot v1/v2 (2025) → 16.06 package (R9: 2.500→3.425 K€, +300 aus EO) → Golland decline 03.06 → offer update 260708_v1 (sent/prepared) |
| Mouse | new (executing — LOI versandfertig) | LOI vS 03.07: 2.000 Sofort + EO ≤750 (3x >450 Ø-EBIT 26/27, Cap 700), GF 100+20 p.P. (LOI docx) |
| Fox | new (executing — DD running) | NBO (folder) → signed LOI ~26.05: 1.600 + 300 EO (signed) |
| Mantis | new (executing — DD running) | NBO (folder) → signed LOI 01.06: ≤5.965 incl. 500 RB (signed) |
| Aqua | new (active) | NBO ~07.05 via Quantum (only if offer doc found in folder; else skip + flag) |

Strategies created for Mouse/Fox/Mantis get: parties (primary seller), LOI-Zeitplan milestones, open items, goals; NO fabricated profile claims/predictions (validator findings are honest state). Rounds: seed at minimum the offer-event rounds. deal_valuations offer_round rows cross-checked where present.

## 8. AC

1. Migration runs idempotently on v1 DB (backup created); 19 existing + new tool tests green.
2. `python -m v2.migrate_v1` carries offers; v2 tests green.
3. Tab on :8082 renders for all populated deals in the v1 visual language; no inline styles; units in headers; validator chip only with memo; non-owner gets 403 + no tab.
4. Offer history per deal matches source docs (spot-check vs LOI PDFs/mails); consistency flag green for Cat/Mouse/Fox/Mantis (deal_terms == latest event).
5. Screenshots + live server for Roman's sign-off (screen 1 of the v2 rebuild).
