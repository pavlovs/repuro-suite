# Investor Room — deploy artifacts (NOT yet applied)

These are the exact suite-config deltas to wire the Investor Room into the Fly suite. **Not applied** to
`suite/` yet — deploy is gated on Roman because the Caddy `investor`-isolation block is load-bearing and
its 403 matrix must be verified on Fly (suite security-verification rule), and `AUTH_INVESTOR_HASH` +
Strada credentials must be set first.

## Apply order (when Roman approves deploy)
1. **Secret** — generate Strada's bcrypt hash and set as a Fly secret (never in repo):
   `fly secrets set AUTH_INVESTOR_HASH='<bcrypt>' -a repuro-suite`
   (Strada also needs the plaintext password over a secure channel — basic-auth user `investor`.)
2. Apply `caddyfile.delta`, `supervisord.delta`, `fly-env.delta`, `dockerfile.delta` into the matching
   `suite/` files (see each file for the precise insertion point).
3. `fly deploy` from `suite/`.
4. **Verify on Fly (do NOT skip):** as `investor`, GET `/deals/ /allex/ /cockpit/ /` → all 403;
   GET `/investor/` → 200. As `roman`, `/investor/` → 200 admin view. This is the real security gate.

## Local run (no Fly)
`cd boardroom && .venv/Scripts/python.exe boardroom.py init-db && boardroom.py seed && boardroom.py serve --port 8084`
Then hit `localhost:8084/` (admin view locally; behind Caddy the `investor` user is path-isolated).
