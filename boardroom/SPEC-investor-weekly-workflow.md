# Spec: Investor View — Weekly Workflow (Snapshot + Dealroom Linkage)

**Status**: DRAFT v3 2026-07-06 (codex loop 1: 13 findings worked in; loop 2 re-verify: 8/13 confirmed resolved + 5 residual findings worked in after the loop — not re-verified by Codex, loop cap reached) — pending Roman go
**Depends on**: SPEC-investor-split.md (IMPLEMENTED — templates/ + request-time assembly)

---

## DECIDED + IMPLEMENTED 2026-07-08 (Roman — supersedes Phase 1 mechanics below)

Roman's model, verbatim intent: *published weeks are static snapshots at dated
URLs; the current week is dynamic and becomes static on publish.*

| URL | Investor (Strada) | Admin (RD/FF) |
|---|---|---|
| `/investor/` | latest **published static week** (holding page + archive switcher if none) | **dynamic draft** (request-time assembly + live inline edits) + DRAFT toolbar |
| `/investor/<YYMMDD>` (e.g. `/investor/260702`) | that week's frozen snapshot | same |

- **Publish** (toolbar button): freeze draft (templates + inline edits, denylist
  gate) → published row at its dated URL, previous week auto-archived,
  **inline_edits CLEARED** — edits are week-scoped, no cross-week bleed
  (the 02/07-edits-override-07/07 bug class).
- **Week switcher is identical for both roles** on every published/archived/
  holding view (server-rendered options, `(live)` marker, English date labels);
  admin home option = "Current draft", investor = "Latest". Draft toolbar
  shows **"Investors see: <week|NOTHING>"**.
- Navigation is **relative** (`./260702`) — root-absolute URLs broke behind the
  `/investor` Caddy prefix (old `_swWk` bug, fixed).
- Legacy `?week=` links still resolve (ISO or YYMMDD).
- Implemented in `src/api.py` (route `GET /{ref_date}`, publish lifecycle,
  `_week_nav_html` + `_draft_toolbar_html`); tests §13 in
  `tests/test_investor_view.py`. The Phase-1 "snapshots table" design below is
  OBSOLETE (the publications table carries the archive); Phases 2-4
  (dealroom-fed ACT2/3/4) remain the roadmap for making the DRAFT fully
  live-data driven.
**Decisions from Roman (06.07.)**: snapshot is MANUAL (post-meeting, after final inline edits, incl. meeting results); S&U + valuation must be built INTO the dealroom and the investor view linked to dealroom.db — "update the DB, not two workflows"; ACT 2 deals are manually chosen.

---

## Problem

1. No history: the investor page is mutated in place; after each weekly update the prior state is gone. No way to compare against, or reopen, what Strada saw on 03.07.
2. Inline edits never expire: saved per element in investor.db and re-applied on every load, they permanently override template content.
3. ACT 2/3/4 content is forked from the dealroom: identical markup, hand-copied numbers, already diverged in both directions (Fox: investor newer; Mouse: dealroom newer; Cat: both stale vs LOI v7).
4. S&U, DD-cost budget and the OCF-availability logic exist ONLY in the investor HTML — no dealroom structure holds them. `deal_scorecard_results` is empty (scorecards also authored).
5. Dealroom `valuation.py` bridges EV differently than the investor presentation (e.g. no permitted leakage for Fox) — no canonical bridge definition.

## Target workflow (end state)

- **Weekly**: Roman updates dealroom data as deals move (which happens anyway) → investor ACT 2 numerics, ACT 3 funnel/portfolio, ACT 4 milestones are current automatically at render time. Only ACT 1 narrative is authored weekly (inline edits or template).
- **Meeting day (manual)**: Roman makes final inline edits incl. meeting results → clicks **Snapshot** → frozen self-contained HTML is archived (exactly what Strada saw), inline edits are cleared, new week starts clean.
- **Event-driven**: authored prose edited when a deal moves — ONE source of truth per block type: **numerics live in dealroom.db; all prose lives in the per-deal template files** (`templates/deals/*.html`). Dealroom `onepager_q*` fields stay dealroom-internal and do NOT feed the investor view (migration of prose into the dealroom = out of scope, revisit after Phase 4 has run for a few weeks).

---

## Phase 1 — Manual snapshot + archive (boardroom only)

### Data
New investor.db table:
```sql
CREATE TABLE snapshots (
  id INTEGER PRIMARY KEY,
  taken_at TEXT NOT NULL,          -- UTC ISO
  label TEXT NOT NULL,             -- e.g. "Investor Call 03.07."
  html BLOB NOT NULL,              -- fully baked, self-contained page
  edits_json TEXT NOT NULL         -- inline_edits state at snapshot time (audit)
);
```
Stored in investor.db (volume + litestream-replicated) — survives redeploys, no loose files.

### Baking — `POST /api/snapshot {label}` (server-side admin check, 403 otherwise)
Runs as ONE critical section — a **dedicated SQLite connection with `BEGIN IMMEDIATE`** (acquires the write lock BEFORE the edits read; a deferred transaction would let a concurrent edit land between read and delete and silently vanish). Because the app shares one connection across request handlers, additionally hold an app-level lock (`threading.Lock`) around steps 1–5 so no inline-edit handler interleaves:
1. Read the current `inline_edits` map.
2. Assemble the page exactly as `GET /` does.
3. Bake the edits **server-side into the HTML**: embed the edits map as `<script type="application/json" id="snapshot-edits">…</script>`. Escaping rule: JSON-serialize, then replace `<` with `\u003c`, `>` with `\u003e`, `&` with `\u0026` inside the JSON string (a literal `</script>` in the payload terminates the tag even in `application/json`; HTML-entity escaping is NOT valid inside a script element). NEVER a bare JS object literal. Shell-bottom JS change: if `#snapshot-edits` is present → `JSON.parse(textContent)`, apply to `[data-edit-id]`, and return before any `fetch()` (no whoami, no inline-edits, no EDIT MODE). The archived page must render correctly with the API fully offline.
4. Make it genuinely self-contained: walk the FINAL baked HTML — templates AND inline-edit content — and inline every non-`data:` URL (`<img src>`, CSS `url()`) as `data:` URIs (known set today: `static/img/*` logos). Any URL that cannot be inlined (external host, missing file, asset > 200 KB) → fail the snapshot with an explicit error naming the offending URL; never silently link out. No absolute-path rewriting — the file must open from disk (`file://`) after download.
5. Insert the snapshots row with the HTML and `edits_json`, then `DELETE FROM inline_edits`, commit.

Concurrency: with `BEGIN IMMEDIATE` + the app-level lock, an edit saved during snapshot either lands before (included + cleared) or after (survives as a new-week edit). No 409 handling needed.

### UI + routes
- EDIT MODE toolbar: **"Snapshot & reset"** button (admin only) with confirm dialog stating that inline edits will be archived and cleared. Second click while a snapshot is in flight → button disabled client-side; server side is idempotent-safe anyway (two rows = two snapshots, harmless).
- `GET /api/snapshots` (list), `GET /snapshot/{id}` (serve stored HTML), `GET /archive` (list page with open + download links; download = the self-contained HTML file — this is the "export").
- ALL three routes enforce admin **server-side** (X-Remote-User role check in the route handler, 403 for role `investor`). Caddy's path confinement is NOT sufficient — `/investor/archive` is inside the investor's allowed scope, so without the app-level check Strada could open the archive.

### Edge cases (explicit expected behavior)
- Snapshot with zero inline edits → valid snapshot, `edits_json = "{}"`.
- `GET /snapshot/{id}` for a nonexistent id → 404.
- Snapshot must never 500 the live page: any bake failure → 500 on the POST only, live page and inline_edits untouched (transaction rollback).

### AC (cockpit task)
- Snapshot button admin-only; POST creates row; `inline_edits` empty afterwards; live page shows clean template content after reset.
- Archived page: downloaded file renders visually identical to the pre-snapshot live page (PNG compare), incl. inline-edited content, **opened from `file://` with no server running**.
- investor role gets 403 on `/archive`, `/snapshot/{id}`, `/api/snapshots`, `/api/snapshot`.
- Edits containing quotes and `</script>` survive baking intact (test fixture).
- PDF export: DEFERRED (HTML download covers "export" for now).

## Phase 2 — Dealroom data refresh to signed-LOI state (content, judgment)

NOT a code task — Fable/Roman-verified, sources = signed LOI PDFs. Deliverable = a **per-deal delta table** (every field below: old value → new value → LOI source ref) for Roman's verdict BEFORE any write.

### Canonical bridge — the complete field set Phase 4 reads
Per deal, `deal_financials(statement='bewertung')` MUST contain exactly these line items (K€):
`ebitda_basis, ev_at_closing, earnout_anticipated, ev_anticipated_earnout, super_earnout, ev_total, net_cash_debt, permitted_leakage, equity_value`
plus `deal_model_params`: `cash_at_closing, vendor_loan, ocf_pct, eo_due_years_json, earnout_tiers_json`. Missing line item = Phase 2 not done (Phase 4 renders from these and only these).

`earnout_tiers_json` schema (authoritative for threshold tables, replaces the current bare list):
```json
[{"ebit_k": 225, "earnout_k": 0, "tag": "floor"},
 {"ebit_k": 250, "earnout_k": 225, "tag": ""},
 {"ebit_k": 300, "earnout_k": 500, "tag": "bp"},
 {"ebit_k": 325, "earnout_k": 650, "tag": "max"}]
```

### Per-deal targets (headline mechanics; full values come from the LOI PDFs in the delta table)
- **Fox**: rows are 22.05. indicative state (EV@closing 893 K€, tiers anchor 275 K€, VL 250 K€ / ant. EO 200 K€ in params). Target: signed-LOI bridge — EV@closing 1.253 K€, ant. EO 500 K€, super EO 150 K€, VL 100 K€, net cash 137 K€, leakage −290 K€, equity value 1.750 K€, tiers per schema above (225/250/300/325 K€ EBIT).
- **Mouse**: headline current (2.000 K€ + 750 K€ = 2.750 K€); refresh mechanics to LOI v2 03.07. — 3x über 450 K€ Ø-EBIT nach Tantiemen, Sofort-Basis 488 K€, EBIT-Cap 700 K€ → max EO 750 K€.
- **Cat**: fully stale (22.05. round-2: ant. EO 1.800 K€ / super 1.050 K€ / EV total 6.209 K€). Target: LOI v7 — Sofort 3,4 M€ abzgl. NFV per 31.12.25 (NFV-Stichtag ins delta table aufnehmen), EO 2,75x über 625 K€ EBIT, Cap 1.090 K€ → max total 5.957,5 K€.
- **Mantis**: verify 18.06. rows vs signed LOI (≤ 5.965 K€ incl. 500 K€ Rückbeteiligung); correct if needed.
- Align `valuation.py` output labels to the canonical line-item set (rename, don't recompute — computation change only where a value is wrong vs LOI).

### AC
- All canonical fields present for all 4 deals; dealroom deal view shows LOI-consistent bridge + tiers; delta table signed off by Roman before write; investor-view figures (post Phase 4) reproduce the LOI numbers exactly.

## Phase 3 — S&U + DD costs as dealroom structures

### Data (dealroom.db)
```sql
CREATE TABLE deal_su_items (
  id INTEGER PRIMARY KEY,
  domain TEXT NOT NULL,
  phase TEXT NOT NULL CHECK(phase IN ('closing','post_closing')),
  side  TEXT NOT NULL CHECK(side  IN ('source','use')),
  label TEXT NOT NULL,
  value_k REAL NOT NULL,
  note TEXT,
  sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE(domain, phase, side, sort)
);
CREATE INDEX idx_su_domain ON deal_su_items(domain);

CREATE TABLE deal_dd_costs (
  id INTEGER PRIMARY KEY,
  domain TEXT NOT NULL,
  category TEXT NOT NULL,
  item TEXT NOT NULL,
  provider TEXT,
  value_k REAL NOT NULL,
  sort INTEGER NOT NULL DEFAULT 0,
  UNIQUE(domain, sort)
);
CREATE INDEX idx_ddc_domain ON deal_dd_costs(domain);
```
- Render order = `sort` ascending (uniqueness enforced above).
- `deal_dd_costs` is **display-only**: it feeds the DD-cost table; the OCF-availability panel is computed from `deal_model_params` (`ocf_pct`, `eo_due_years_json`, EBITDA basis) + S&U uses. DD costs enter S&U only via an explicit `deal_su_items` row (e.g. "Transaction Costs"), never implicitly.

### Seed + UI
- Seed all 4 deals from the current investor v16 tables (freshest S&U anywhere) — AFTER Phase 2 corrects the underlying terms.
- Dealroom dashboard: extend the offer-negotiation section (or new "S&U" section) to display + edit S&U, DD costs, OCF assumptions per deal. Sources/uses totals must balance per phase; UI shows the imbalance amount if not.

### AC
- S&U renders in dealroom for Fox/Mantis/Mouse/Cat, totals balance, DD-cost sums match proposed budgets, imbalance warning verified with a deliberately broken fixture.

## Phase 4 — Investor view live-linked to the DBs

### Mechanism
Extend the existing request-time assembly (`api.py`): before concatenation, substitute **placeholder blocks** from read-only DB reads (`sources.py` resolves paths; Fly container has all three DBs).

Placeholder grammar: `{{NAME}}` (section-level) and `{{NAME:codename}}` (per-deal), matched literally. Unknown placeholder in a template → render error at startup smoke test, not silently empty.

Per-deal templates keep ALL authored prose; numeric blocks become placeholders:
- `{{KEYSTRIP:fox}}` — EV/EBITDA/multiple strip (all views)
- `{{VAL_TABLE:fox}}` — P&L header rows + valuation bridge
- `{{EO_TIERS:fox}}` — threshold table from `earnout_tiers_json`
- `{{SU_TABLE:fox}}`, `{{OCF_PANEL:fox}}`, `{{DD_COSTS:fox}}` — from Phase 3 structures
- `{{STAGE:fox}}`, `{{DAYS_IN_STAGE:fox}}` — from deals (kills the stale-days defect class)

Sections:
- ACT 3: `{{FUNNEL}}` (counts from dealroom stages + pipeline batches — reuse assemble.py pull logic), `{{PORTFOLIO_TABLE}}` (deals incl. on_hold/dead rows).
- ACT 4: `{{MILESTONES}}` from cockpit deliverables + dealroom notary/exclusivity dates.
- ACT 1 + all prose: untouched (authored).

### Deal selection (manual, Roman's rule) — the WHOLE ACT 2 shell is data-driven
- `deals.investor_display INTEGER NOT NULL DEFAULT 0` + `deals.investor_order INTEGER NOT NULL DEFAULT 99` in dealroom.db; toggle in dealroom UI.
- The assembly renders **from the flag, not from hardcoded markup**: deal tab bar, per-deal fragment inclusion, `_overview` comparison rows, and per-deal headers (`dname`) are all generated. `act2-shell.html` loses its hardcoded tabs.
- Naming rule, two layers BECAUSE prose is authored and the renderer cannot rewrite it: (a) **renderer-owned chrome** (tab, `dname` header, overview row, keystrip): `loi_signed`+ renders "RealName (Codename)", below `loi_signed` renders codename only — enforced in code; (b) **authoring gate for prose**: the assembly runs a name-scan — for every flagged deal below `loi_signed`, the deal's `company_name` (from dealroom.db) must not appear anywhere in the assembled output; a hit fails the startup smoke test / renders the deal omitted with an error log. Same scan runs over ACT 1 content (inline edits + template) since it is also authored.
- Flag on but no `templates/deals/<codename>.html` → deal omitted + startup warning logged (never a broken page). Deal file exists but flag off → not rendered anywhere (tab, fragments, overview). Zero flagged deals → ACT 2 renders the section header + "No live transactions." line (defined empty state).

### Guardrails
- Read-only connections only (`db.open_readonly`). **Explicit per-placeholder field allowlist** (a dict in code: placeholder → exact columns read); the renderer can only access listed columns. `seller_*`, `notes`, `investment_thesis`, `seller_profile_notes` are not in any allowlist — enforced by construction, verified by a test that greps rendered output for known-sensitive fixture values.
- Number formatting: renderer emits ENGLISH convention (dot decimals, comma thousands) — investor-view rule; `validate_ci.py --audience en` runs on the assembled output in codex-review before deploy.
- Render failure handling — **fragment cache**: every successful render of a placeholder writes the fragment to investor.db `fragment_cache(placeholder TEXT, template_hash TEXT, html TEXT, rendered_at TEXT, PRIMARY KEY(placeholder, template_hash))`. `template_hash` = hash of the shipped templates/ tree (computed once at startup) — a deploy that changes templates invalidates the old cache by key, so a stale fragment can never be spliced into a newer shell contract. On DB-read failure → serve cached fragment for the CURRENT template_hash + log warning. No cache for current hash (cold start after deploy, DB unreachable) → fragment renders as `<div class="frag-unavailable">Data temporarily unavailable</div>` + error log; the page itself always serves 200. Cache is a fallback, NOT a freshness layer — a healthy render always reads live.
- Placeholder with DB reachable but required row/value missing (e.g. deal flagged, no bewertung rows yet) → same `frag-unavailable` block + error log naming placeholder and missing field; NEVER a partially-filled table with blank numbers, and never a cached fragment (the cache is for read FAILURES, not for missing data — serving cached data here would mask a Phase 2 gap as fresh).

### AC
- Every number on the assembled page that has a DB source equals the DB value (scripted check over all placeholders).
- Toggling `investor_display` adds/removes a deal everywhere (tab, fragments, overview) without deploy.
- Pre-LOI fixture deal with flag on → real name appears NOWHERE in output (scripted grep).
- Sensitive-column fixture test passes; kill-DB test serves cached fragments; `validate_ci --audience en`: no new findings vs baseline.

## Out of scope (explicit)
- Scorecard values/comments from DB (`deal_scorecard_results` empty — scorecards stay authored; candidate for later).
- Migrating investor prose into dealroom fields (single prose source for now = per-deal templates).
- PDF export of snapshots.
- Retiring the M2/M3 publish-flow machinery (assemble.py pulls get reused; the JSON publish path stays dormant — decide separately).
- Strada login enablement (AUTH_INVESTOR_HASH — separate, unchanged).

## Sequencing + execution
1 → 2 → 3 → 4 strictly (linking before the data refresh would publish stale numbers to Strada).
- Phases 1, 3, 4: mechanical builds → cockpit queue tasks (Sonnet runner) with the ACs above; artifact previews (PNG of rendered page) mandatory before verdict.
- Phase 2: judgment (LOI terms) → Fable session with LOI PDFs pre-loaded; Roman verdict on the delta table before write.
