# SPEC — Admin window rework (2026-07-16)

## Problem (Roman: "very halfbaked, I can't understand anything as a DAU")
The Admin view exposes the storage model instead of answering the admin's questions:
raw permission strings (`overview:ro, week:rw…`), the team indirection is invisible
(nothing answers "what does Anton actually see?"), "Login (Caddy user)" is
infrastructure jargon, workstream assignment is a comma-separated team-ID text
field, and creating a user dead-ends with no credential handoff. (Context-free
review 2026-07-16 rated it 4/10 for the same reasons.)

## Design principle
The admin thinks in PEOPLE and plain language. Teams stay the storage model
(nothing changes server-side) but the UI renders them as "access groups" and
always shows the COMPUTED result per person. Plain words everywhere:
rw → **Edit**, ro → **View**, absent → **No access**; module ids → visible names
(overview → Cockpit, week → Meeting, table → Workstreams, …).

## Screen 1 — Users (the hub; answers "who sees what" at a glance)
- Slim table: Avatar + Name · Suite login · Work email (calendar, keeps the
  two-step confirm) · **Access chip** ("Admin — everything", "Team — 5 modules",
  "View only") computed from memberships · Groups.
- **Click row → drawer** (existing drawer pattern), three blocks:
  1. *Identity*: name, initials, suite login username, work email.
  2. *What {name} can do* — effective-access matrix, one row per module:
     `Meeting  Edit (via Team)` / `Dealroom  View` / `Calendar  No access`.
     Strongest-wins conflicts pre-resolved; source shown small. Below it:
     *Sees workstreams:* computed list, unrestricted ones included.
  3. *Groups*: checkbox list (join/leave = existing team-member endpoints).
     Agent lane shown if linked ("Runner: AC").
- **New user = 3-step flow in the same drawer**:
  1) Identity (name + work email; ID/initials auto-derived, editable).
  2) Access: pick ONE group via radio, each with a one-line plain description
     ("Team — works in Meeting/Workstreams/Agents", "Advisor — view only", …).
  3) Handoff card: suite username, "login password is provisioned separately —
     ask Roman", agent token (shown once) if a runner was created.
  Kills "Login (Caddy user)" — label becomes "Suite login username".

## Screen 2 — Access groups (renamed from Teams)
- Permission MATRIX: rows = groups, columns = modules, cells = Edit/View/—
  as colored chips; admin clicks a cell to cycle (existing PATCH endpoint).
  Raw permission strings disappear. Admin groups render as one line:
  "Full access to everything".

## Screen 3 — Workstream visibility
- Per workstream: group chips (click to toggle) instead of the comma text field.
- Unrestricted state = explicit amber badge **"Visible to EVERYONE incl. future
  users"** + one-click "Restrict to…" (this silent default caused the Holding
  near-miss — it must look like a decision, not a blank).

## Backend
Near-zero: everything renders from `/api/admin/overview` (add `represents` to
its users payload); all mutations use existing admin endpoints. No schema change.

## Order & gates
Screen 1 first → Roman sign-off on :8099 → Screens 2+3 replicate the calibrated
pattern (FIRST-SCREEN-SIGNOFF). Estimate: Screen 1 ≈ half day, 2+3 ≈ 2-3h.
