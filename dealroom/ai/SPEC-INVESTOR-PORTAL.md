# SPEC: Investor Portal (view-only, watermarked)

Serve the existing dealroom **pipeline + one-pager** behind login in a read-only, watermarked **investor mode**. Content is unchanged — the one-pager text is already kept investor-safe by Roman. The build is the *access wrapper*, not a content transform.

**Auth precedent:** ALLEX `lead-pipeline/src/pipeline/dashboard.py` (`_check_auth`, `_send_auth_challenge`, `AUTH_USER`/`AUTH_PASS`). Decision in `.active/roman.md`: HTTP Basic Auth, zero new infra.

**Relationship:** renders the same views as `SPEC-INVESTOR-COCKPIT.md` (DR-M9), gated read-only. Stage-gating, codename sanitizing, and CDD tiering from the prior draft of this spec are **dropped** — out of scope per Roman (2026-06-03).

---

## 1. Scope

**Build (this session, local):**
1. **Login** — HTTP Basic Auth in the dealroom server. The authenticated username is the investor identity.
2. **View-only mode** — investor sessions get a read-only render: no inline editing, no edit/save controls, and the server **rejects all write endpoints** for these sessions (defense in depth — not frontend-only).
3. **Login watermark** — the authenticated username (+ date) tiled diagonally, semi-transparent, fixed above all content, on both the pipeline and the one-pager.
4. **Surface = pipeline + clickable one-pager only.** All other tabs/sections (Documents, Notes, Model, RFI, Financials detail, Internal Deal Screen, etc.) are not exposed in investor mode.

**Explicitly NOT in scope:**
- Stage-driven depth / tiers. (All deals in the pipeline are clickable to their one-pager.)
- CDD section.
- Content sanitizing / codename enforcement — one-pager content is kept safe by Roman; render it as-is.
- Fly.io deployment + credential provisioning → **Phase 2, gated on Roman's explicit go-ahead** (deploy rule).
- Other drill sections in investor mode → later.

---

## 2. Mode detection

Investor mode is a render flag, set by either:
- **Prod:** the request is authenticated via Basic Auth as a user in the configured `INVESTOR_USERS` set → investor mode, watermark = that username.
- **Local dev/testing:** `?view=investor&as=<name>` query flag renders investor mode with `<name>` as the watermark, no auth required. Guarded to localhost.

Internal (non-investor / unauthenticated localhost) sessions render the existing dashboard unchanged.

The render layer does not care how the flag was set — it receives `investor_mode: bool` and `watermark_label: str`.

---

## 3. View-only enforcement (two layers)

1. **Render:** when `investor_mode`, the templates omit every edit affordance — `contenteditable` is not set, edit/save/approve buttons and the stage/override controls are not rendered. Only the pipeline table and the one-pager render; the sidebar/tabs for other sections are suppressed.
2. **Server:** the HTTP handler rejects any mutating endpoint (`/api/update`, `/api/save*`, any POST/PUT) with `403` when the session is investor mode. The frontend hiding is convenience; the server check is the real guard.

---

## 4. Watermark

- A fixed, full-viewport overlay (`position: fixed; inset: 0; pointer-events: none; z-index: high`) with the `watermark_label` repeated in a low-opacity diagonal tile.
- `watermark_label` = `"{username} · {YYYY-MM-DD}"`.
- Present on every investor-mode page (pipeline and one-pager). Does not interfere with clicks (pointer-events: none) so the one-pager stays clickable from the pipeline.
- Purpose: deter and trace screenshot leaks — the viewer's login is burned into anything they capture.

---

## 5. Components

`src/dashboard.py`:
- Port `_check_auth` / `_send_auth_challenge` from ALLEX into the dealroom handler.
- `_investor_context(handler) -> (investor_mode: bool, watermark_label: str | None)` — reads auth user / dev flag.
- Pass `investor_mode` + `watermark_label` into the page data dict.
- Reject mutating endpoints when `investor_mode`.

`src/templates/` (dashboard HTML + sections):
- Accept `investorMode` + `watermarkLabel`.
- When set: render watermark overlay; render pipeline + one-pager only; strip all edit controls; suppress other tabs.

No new content module needed (no sanitizer). Logic is a thin flag threaded through the existing render path.

---

## 6. Testing

- **Server guard:** a mutating request (`/api/update`) in investor mode returns `403`; the same request in internal mode still works.
- **View-only render:** investor-mode HTML contains no `contenteditable` and none of the edit/save control markers; internal-mode HTML still does.
- **Watermark present:** investor-mode HTML for pipeline and one-pager contains the watermark overlay with the supplied label.
- **Surface limited:** investor-mode HTML exposes pipeline + one-pager only; no Documents/Notes/Model/RFI/Internal sections.
- Existing dashboard tests still pass (internal mode unchanged).

---

## 7. Definition of Done (Phase 1)

1. Basic Auth in the dealroom server; authenticated username available to the renderer.
2. Investor mode reachable locally via the dev flag and behind auth.
3. View-only: no edit controls render; mutating endpoints return `403` for investor sessions.
4. Watermark (login + date) overlaid on pipeline and one-pager; one-pager stays clickable.
5. Investor surface limited to pipeline + one-pager.
6. Internal mode unchanged; existing tests pass; new tests above pass.
7. `dealroom/ai/ROADMAP.md` updated; this spec referenced.
8. NO deployment performed.
