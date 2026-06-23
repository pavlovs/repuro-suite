# INVESTOR ROOM — Strada

**Design spec v2 — 2026-06-20. Status: approved in principle (Roman), building M1 local.**

Exclusive, authenticated module for **one** co-investor (Strada), served from the
Repuro suite at `/investor/` alongside Allex / Dealroom / Cockpit. Strada logs in and
sees only approved, curated content. The room has **two parts**:

1. **Updates** — the weekly investor update: anonymized pipeline, the live post-LOI
   deals they co-fund (real names + financials), and the project + fundraising update
   (tax structure, Sources & Uses, capital plan).
2. **Board** — board-meeting preparation: agenda, KPI pack, decisions/resolutions,
   pre-read materials, and minutes for each board meeting.

The #1 success criterion is **correctness + permission**: every figure is
source-stamped and verified, and Strada sees *only* what Roman has explicitly
approved — never a raw DB, never a draft, never another investor.

> Module folder is `boardroom/` on disk for now (rename to `investor/` deferred to
> avoid churn mid-build); the **route, auth user, and product name are `investor`**.

---

## 1. Why this is not "just another dashboard"

The suite's only access control today is one `basic_auth` block in
`suite/Caddyfile` (lines 11-14) authenticating `roman` + `florian` for **every** path.
There is no per-user authorization: any authenticated user reaching `/deals/` sees
`dealroom.db` in full — real company names, seller names, exact prices. Allex and
Dealroom run **no auth of their own**; the wall is Caddy alone.

So the primary deliverable is an **authorization boundary**, not a UI. Adding Strada as
a 4th basic-auth user without that boundary hands them the entire deal book. Everything
else serves that boundary.

## 2. Security model — three bright lines

1. **Path isolation.** The `investor` principal gets `403` on everything except
   `/investor/*`. Enforced in Caddy with a CEL matcher (§6), before any `handle_path`.
2. **Content isolation.** The investor view reads *only* approved, published rows from
   `investor.db`. The Investor-Room process is the only thing that opens the sensitive
   DBs, and only the admin (assembly) path does so — read-only. The investor's session
   reaches no live DB and no draft.
3. **Content gates (enforced at the approve step, §5):**
   - Pre-LOI pipeline deals → **codename + anonymized band only**, never real names.
   - Post-LOI deals (`loi_signed` / `due_diligence` / `contract_negotiation` /
     `closed`) → real names + full financials permitted (Strada co-funds these).
   - **Other investors (ASF / Aurica / Arbor / any third party) → never published.**
     Blocking checklist item; an approval cannot complete until acknowledged.

Fail closed: if any line is uncertain for a given item, it does not publish.

## 3. Architecture

Matches the suite pattern: a new Python process behind the suite Caddy.

```
Strada browser ──HTTPS──> Fly Caddy :8080
   (basic_auth: investor)   │  CEL: investor ⇒ 403 unless /investor/*
                            └─/investor/* ──> Investor FastAPI :8084
                                              │  reads  investor.db   (published content)
                                              │  reads  dealroom.db   (ro, ADMIN assembly only)
                                              │  reads  pipeline.db   (ro, ADMIN assembly only)
                                              └  reads  cockpit.db    (ro, ADMIN assembly only)
```

- **Stack:** FastAPI + Uvicorn + SQLite, mirroring Cockpit (`cockpit/src/api.py`).
  React-via-Babel-in-browser frontend, no build step, consistent with Cockpit.
- **Process:** `boardroom/boardroom.py serve --port 8084`, supervised (§6).
- **DB:** `investor.db` on the Fly volume (`/data/investor.db`), `journal_mode=DELETE`
  (OneDrive-safe). Never committed.
- **Source DBs are read-only here.** Open with `file:...?mode=ro` URI always.

### 3.1 Auth principal (reuse Cockpit's pattern)

Port Cockpit's `principal()` dependency: trust `X-Remote-User` injected by Caddy, map
to a role.

| Caddy user | role | Sees |
|------------|------|------|
| `roman`, `florian` | `admin` | drafts, all content, assembly + approve/publish |
| `investor` | `investor` | latest **published** Updates + Board content only |

`@Depends(admin_only)` guards every assembly / draft / approve / publish endpoint.
Defense in depth: the app enforces roles even though Caddy is the outer wall.
Bearer-token fallback for local dev (`X-Remote-User` absent off-Fly).

## 4. Data model (`investor.db`)

One generalized table backs both parts; `kind` distinguishes them.

```sql
publications(
  id           INTEGER PK,
  kind         TEXT NOT NULL CHECK(kind IN ('weekly_update','board_pack')),
  ref          TEXT NOT NULL,         -- weekly_update: ISO Monday; board_pack: meeting date
  title        TEXT,
  status       TEXT NOT NULL CHECK(status IN ('draft','approved','published','archived')),
  body         TEXT NOT NULL DEFAULT '{}',  -- JSON, shape depends on kind (§4.1/§4.2)
  created_at   TEXT NOT NULL,
  approved_at  TEXT, approved_by TEXT,
  published_at TEXT,
  version      INTEGER NOT NULL DEFAULT 1
)
-- per kind, at most one row is 'published' as "current"; superseded → archived
audit_log(id, at, actor, action, entity, before, after)   -- same shape as cockpit
```

Only curated, approved values land here — never raw sensitive source rows.

### 4.1 `weekly_update` body JSON

```jsonc
{
  "pipeline": {
    "funnel":  { "items": [ {codename, stage, sector, region, size_band, strategic_fit} ] },
    "batches": { "rows":  [ {batch, sent, replies, meetings, conv_pct} ] }   // Allex BA1-8, aggregate
  },
  "live_deals": [
    { "name", "codename", "stage", "rev_m", "ebitda_m", "ev_m", "multiple",
      "earnout", "dd_status", "close_target", "commentary" }                  // real names OK post-LOI
  ],
  "project_update": {
    "milestones_done": [ {name, date, comment} ],   // from cockpit deliverables
    "milestones_next": [ {name, target_date} ],
    "narrative": "…",                                // authored
    "fundraising": { "tax_structure":"…", "sources_uses":[…], "capital_plan":"…" }  // authored
  },
  "stamps": { "<field-path>": { "source": "dealroom.db|pipeline.db|cockpit.db|authored", "as_of": "ISO" } }
}
```

### 4.2 `board_pack` body JSON

```jsonc
{
  "meeting": { "date", "location", "attendees": ["…"] },
  "agenda":  [ {item, owner, minutes} ],
  "kpis":    [ {metric, value, prior, as_of} ],          // may reuse stamped figures
  "decisions": [ {topic, proposal, resolution, vote} ],  // resolutions to be passed
  "pre_read":  [ {title, note} ],                         // links/materials list
  "minutes":   "…",                                      // authored, post-meeting
  "stamps":  { "<field-path>": { "source":"…", "as_of":"ISO" } }
}
```

**Data-source split:** pipeline/live-deal/KPI figures are **auto-assembled** (M2) from
the ro DBs with stamps; narrative, fundraising, agenda, decisions, minutes are
**authored** in the curation UI (M3) — never auto-invented (NO_FABRICATION).

## 5. Flow — curate → approve → publish (both kinds)

1. **Assemble (admin, M2).** Pull live data into a `draft` with `{source, as_of}` stamps.
2. **Review (admin, M3).** Draft + **diff vs. last published** (same kind); edit/redact;
   fill authored sections.
3. **Approve (admin, M3).** Blocking checklist must clear:
   - [ ] No pre-LOI real names. [ ] No other-investor references.
   - [ ] Every figure stamped + as-of within freshness window.
   On approve → `approved`, then publish → `published`, prior current → `archived`.
4. **Strada views** the latest published Updates and Board content at `/investor/`.

## 6. Suite integration — exact config deltas

**`suite/Caddyfile`** — add `investor` to `basic_auth`, add the isolation block
*before* the module `handle_path`s, add the `/investor` route:

```caddyfile
basic_auth @needsAuth {
    roman    {$AUTH_ROMAN_HASH}
    florian  {$AUTH_FLORIAN_HASH}
    investor {$AUTH_INVESTOR_HASH}
}

# Strada is confined to /investor — 403 on everything else.
@investor_outside {
    expression {http.auth.user.id} == "investor"
    not path /investor /investor/*
}
respond @investor_outside 403

handle /investor {
    redir /investor/ permanent
}
handle_path /investor/* {
    reverse_proxy localhost:8084 {
        header_up X-Remote-User {http.auth.user.id}
    }
}
```

**`suite/supervisord.conf`** — new program (priority 400):

```ini
[program:investor]
command=python /app/boardroom/boardroom.py serve --port 8084
directory=/app/boardroom
environment=INVESTOR_DB="/data/investor.db",INVESTOR_DEALROOM_DB="/data/dealroom.db",INVESTOR_PIPELINE_DB="/data/pipeline.db",INVESTOR_COCKPIT_DB="/data/cockpit.db"
user=appuser
priority=400
autostart=true
autorestart=true
```

**`suite/fly.toml`** `[env]` — add `INVESTOR_DB="/data/investor.db"` (+ the three
`INVESTOR_*_DB` read paths). **`AUTH_INVESTOR_HASH`** is a **Fly secret**
(`fly secrets set`), never in the repo or this file.

**`suite/Dockerfile`** — `COPY boardroom/ /app/boardroom/` + install its
`requirements-prod.txt` (fastapi, uvicorn).

**Landing page** — investor hitting `/` already gets `403` via `@investor_outside`;
cosmetic `/` → `/investor/` redirect is a later refinement, not a security item.

## 7. Milestones

| M | Scope | Done = |
|---|-------|--------|
| **M1** | **Security wall + read view.** Caddy isolation block; Investor process; `investor.db` schema; principal/roles; read-only view with **Updates + Board** nav, each rendering a **hand-seeded** published row; admin index. | Local: investor token → 403 on admin/draft/list endpoints, 200 on published; ro-DB test; app renders seeded Updates + Board. Caddy 403 matrix validated on deploy. |
| **M2** | **Auto-assembly.** Pull pipeline funnel + Allex batch stats + live-deal financials (+ board KPIs) from ro DBs into a draft with stamps. | Draft body matches live DB values (verified vs real rows, N/M reported); authored sections empty. |
| **M3** | **Curation + publish.** Admin edit UI, diff-vs-last, blocking approval checklist, publish/archive state machine — for both kinds. | Gates block on unmet checklist; publish flips visibility; prior current archived. |
| **M4** | **Polish + PDF/email export** (deferred). | Offline export of an update / board pack; styling pass. |

## 8. Acceptance tests (security-first, M1, local)

- `investor` → `GET /investor/api/publications` (list) and any draft endpoint ⇒ **403**.
- `investor` → `GET /investor/api/published?kind=weekly_update` and `?kind=board_pack`
  ⇒ latest published only; with **no** published row ⇒ empty placeholder, never a draft.
- `admin` → sees drafts + list; published views match seeded fixtures.
- Investor-Room opens dealroom/pipeline/cockpit DBs only via `?mode=ro`; a write attempt
  raises — unit test asserts the connection is read-only.
- **Deploy-time:** `investor` → `GET /deals/ /allex/ /cockpit/` ⇒ **403** (Caddy CEL).
  Validate `caddy validate` locally; run the full path matrix on Fly before M1 done.

## 9. Risks / open

- **CEL matcher is load-bearing.** A wrong matcher = full leak. Validate config locally;
  run the 403 matrix on deploy — never mark done on code reading alone.
- **Stale data as current** — mitigated by `stamps` + freshness check at approve.
- **Authored fundraising/board accuracy** — `/codex-review` gate on any item before its
  first real publish, same as any external investor doc.

---

## Build process

Suite-module convention (Cockpit): this DESIGN-SPEC + per-milestone `ai/PLAN-M{n}.md`,
milestone loop with independent review and the suite UI/security-verification loop. RC
implements; tickets to suite `TICKETS.md`.
