# Repuro Suite — Module Registry

Suite version: `suite/VERSION`. Changelog: `suite/CHANGELOG.md`.
Deploy: `suite/Dockerfile` + `suite/fly.toml` via `/deploy` skill. All modules ship as one Fly.io app (`repuro-suite`).

## Modules

| Module | Path | Port | Entrypoint | Route | DB |
|--------|------|------|------------|-------|----|
| ALLEX | `lead-pipeline/` | 8081 | `pipeline.py dashboard --serve` | `/allex/` | pipeline.db |
| DEALRoom | `dealroom/` | 8082 | `DEALROOM.py dashboard --serve` | `/deals/` | dealroom.db |
| Cockpit | `cockpit/` | 8083 | `cockpit.py serve` | `/cockpit/` | cockpit.db |
| Investor Room | `boardroom/` | 8084 | `boardroom.py serve` | `/investor/` | investor.db (+ read-only: dealroom/pipeline/cockpit) |

Investor Room deviates from the convention: investor-view HTML is assembled at
request time from `boardroom/templates/` (see `boardroom/SPEC-investor-split.md`);
`investor` Caddy user is confined to `/investor/*` (403 elsewhere).

## Module Structure Convention

Each module follows this layout:

```
<module>/
  <entrypoint>.py        # CLI with serve/dashboard subcommand
  src/                   # Source code
    db.py                # SQLite connection + schema migrations
    dashboard.py         # HTTP handler (or equivalent)
    ...
  static/                # Frontend (HTML/CSS/JS)
  tests/                 # pytest suite
  requirements.txt       # Dev dependencies (full)
  requirements-prod.txt  # Prod dependencies (minimal, no test/dev packages)
  ai/                    # Planning docs (ROADMAP.md, PLAN.md, PLAN-M*.md)
```

No per-module Dockerfile or fly.toml. Production deployment is always via `suite/`.
Local development: `python <entrypoint>.py dashboard --serve --port <port>` from the module directory.

## Adding a Module

1. Create `<module>/` at repo root following the convention above.

2. Update suite infrastructure (all files in `suite/`):
   - **Dockerfile** — add `COPY <module>/requirements-prod.txt` + `pip install` + `COPY <module>/ /app/<module>/`
   - **supervisord.conf** — add `[program:<module>]` block (next available port, priority)
   - **Caddyfile** — add `handle` redirect + `handle_path` reverse_proxy for the route
   - **fly.toml** — add env vars for DB paths
   - **entrypoint.sh** — add data dir creation if needed
   - **static/index.html** — add module card to the landing page

3. Update this file with the new row.

4. Update `.gitignore` — add `!/<module>/` to the whitelist.

5. Update `CLAUDE_REPURO/CLAUDE.md` — add the module to the Sub-projects section.

## Architecture

```
Internet → Fly.io (repuro-suite.fly.dev)
  → Caddy (:8080) — TLS termination, basic auth, routing
    → /allex/*    → ALLEX    (localhost:8081)
    → /deals/*    → DEALRoom (localhost:8082)
    → /cockpit/*  → Cockpit  (localhost:8083)
    → /           → Suite landing page (static)

Supervisor manages all processes. Litestream replicates SQLite DBs (when configured).
Persistent volume at /data holds all .db files.
```
