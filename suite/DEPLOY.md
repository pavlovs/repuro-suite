# Repuro Suite — Deployment

Single Fly.io app hosting ALLEX + DEALROOM + COCKPIT behind Caddy reverse proxy.

## Architecture

```
repuro-suite.fly.dev
├── /          → landing page
├── /allex/    → ALLEX Pipeline (basic auth)
├── /deals/    → Dealroom (basic auth)
├── /cockpit/  → Cockpit (bearer token auth)
└── /investor/ → Investor Room (basic auth; `investor` user confined to /investor)

/data/ volume: pipeline.db, dealroom.db, cockpit.db, investor.db
```

## First-time setup

### 1. Create the app

```bash
cd CLAUDE_REPURO
flyctl launch --copy-config --config suite/fly.toml --no-deploy
```

### 2. Create the persistent volume

```bash
flyctl volumes create suite_data --region fra --size 1 --app repuro-suite
```

### 3. Generate auth credentials

```bash
# Generate bcrypt hashes for basic auth (ALLEX + DEALROOM)
caddy hash-password  # enter Roman's password, copy the hash
caddy hash-password  # enter Flo's password, copy the hash
```

### 4. Set secrets

```bash
flyctl secrets set \
  AUTH_ROMAN_HASH='$2a$14$...' \
  AUTH_FLORIAN_HASH='$2a$14$...' \
  --app repuro-suite
```

COCKPIT tokens: set in cockpit `.env` or via the API after first deploy.

### 5. Seed databases

Copy existing DBs to the volume on first deploy:

```bash
# SSH into the machine
flyctl ssh console --app repuro-suite

# Inside the machine — DBs will be empty on first run.
# To seed from local, use flyctl sftp:
flyctl sftp shell --app repuro-suite
put pipeline.db /data/pipeline.db
put dealroom.db /data/dealroom.db
put cockpit.db  /data/cockpit.db
```

### 6. Deploy

```bash
cd CLAUDE_REPURO
flyctl deploy --config suite/fly.toml --dockerfile suite/Dockerfile --app repuro-suite
```

The Docker build context is `CLAUDE_REPURO/` (parent of suite/) so it can copy all three apps.

## URLs

- Landing: `https://repuro-suite.fly.dev/`
- ALLEX: `https://repuro-suite.fly.dev/allex/`
- Dealroom: `https://repuro-suite.fly.dev/deals/`
- Cockpit: `https://repuro-suite.fly.dev/cockpit/`
- Investor Room: `https://repuro-suite.fly.dev/investor/`

## Auth

| Tool | Method | Roman | Flo |
|------|--------|-------|-----|
| ALLEX | HTTP Basic (Caddy) | roman / [password] | florian / [password] |
| Dealroom | HTTP Basic (Caddy) | roman / [password] | florian / [password] |
| Cockpit | Bearer token | RD token | FF token |
| Investor Room | HTTP Basic (Caddy) | roman / [password] | `investor` user (Strada; `AUTH_INVESTOR_HASH` secret), confined to `/investor/*` |

## Updating

Redeploy after code changes:

```bash
cd CLAUDE_REPURO
flyctl deploy --config suite/fly.toml --dockerfile suite/Dockerfile --app repuro-suite
```

## Cost

- Compute: shared-cpu-1x, 512MB — ~$3-5/mo
- Volume 1GB: $0.15/mo
- Auto-stop when idle, auto-start on request (~5s cold start)

## Local dev

All apps still work locally unchanged — `BASE_PATH` defaults to empty:

```bash
python pipeline.py dashboard --serve --port 8082
python DEALROOM.py dashboard --serve --port 8090
python cockpit.py serve
```

## Migration from standalone ALLEX (completed 2026-06-15)

Standalone `allex-pipeline.fly.dev` has been shut down (`flyctl scale count 0`).
All traffic now goes to `repuro-suite.fly.dev/allex/`.
The `/deploy` skill deploys the unified suite.
