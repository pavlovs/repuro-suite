# Cockpit Remote API Access

The production cockpit runs on Fly.io at `repuro-suite.fly.dev/cockpit/`. The DB on Fly is the source of truth — never push local DB to Fly.

## How to modify the production DB

**Method: SSH + Python script piped via stdin.**

Caddy handles basic auth on the public URL, so direct HTTP from your machine won't work without Roman's password. Instead, SSH into the Fly machine and hit the backend directly at `localhost:8083`, using the `X-Remote-User: roman` header (which is what Caddy normally sets after basic auth).

### Step-by-step

1. **Wake the machine** (it auto-stops when idle):
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://repuro-suite.fly.dev/healthz
   ```
   Wait for 200.

2. **Write a Python script** to `%TEMP%\cockpit_remote.py` that makes all API calls. Key pattern:
   ```python
   import json, urllib.request, urllib.error, sys

   BASE = "http://localhost:8083/api"
   HDR = {"X-Remote-User": "roman", "Content-Type": "application/json"}

   def api(method, path, body=None):
       data = json.dumps(body).encode() if body else None
       req = urllib.request.Request(f"{BASE}{path}", data=data, headers=HDR, method=method)
       try:
           with urllib.request.urlopen(req) as r:
               return json.loads(r.read())
       except urllib.error.HTTPError as e:
           print(f"ERROR {e.code}: {e.read().decode()}", file=sys.stderr)
           return None
   ```

3. **Pipe the script via SSH** (Bash tool, not PowerShell):
   ```bash
   cat /c/Users/X1/AppData/Local/Temp/cockpit_remote.py | flyctl ssh console --app repuro-suite -C "python3 -" 2>&1
   ```

4. **Ignore the exit code.** flyctl SSH always exits 1 due to handle cleanup on Windows. Check the script output for `=== DONE ===` and valid IDs.

### Auth

- **X-Remote-User: roman** → maps to principal `rd` (human role, full access)
- **X-Remote-User: florian** → maps to principal `ff` (human role, full access)
- Bearer tokens in `.env` work on localhost but the remote DB may have different token hashes — use X-Remote-User instead.

### API reference

All mutations require `version` field (optimistic locking). Fetch current state first via `GET /api/state`.

| Operation | Method | Endpoint | Key fields |
|-----------|--------|----------|------------|
| List everything | GET | `/api/state` | — |
| Create workstream | POST | `/api/workstream` | `name`, `space_id` (e.g. `s-1`), `sort_order`, `status` |
| Patch workstream | PATCH | `/api/workstream/{wid}` | `version` + fields to change |
| Create deliverable | POST | `/api/deliverable` | `name`, `workstream_id` (e.g. `w-5`), `target_date`, `deal`, `sort_order`, `source` |
| Patch deliverable | PATCH | `/api/deliverable/{did}` | `version` + fields to change |
| Create task | POST | `/api/task` | See `mdio.py` NEW_KEYS |
| Patch task | PATCH | `/api/task/{tid}` | `version` + fields to change |
| MD import | POST | `/api/import?dry_run=true` | text/markdown body, see `/cockpit-push` skill |

### Spaces and workstreams (as of 2026-06-17)

- `s-1` Repuro: Fundraising (w-1), Other (w-3), Finance Setup (w-18)
- `s-2` M&A: Fox (w-5), Mantis (w-6), Cat (w-7), Lion (w-8), Wolf (w-9), etc.

### What NOT to do

- Do not use `flyctl proxy` — connection resets on Windows.
- Do not use Bearer token auth against remote — token hashes may differ from local `.env`.
- Do not push local `cockpit.db` to Fly — the remote DB is the source of truth.
- Do not use PowerShell for the `flyctl ssh` command — use the Bash tool (Git Bash).
