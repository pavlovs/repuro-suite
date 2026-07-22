# Calendar Module — Azure Admin Setup

One-time setup to grant the Cockpit app access to read Microsoft 365 calendars.

## Prerequisites
- Tenant admin access (kamucapital.onmicrosoft.com)

## Steps

### 1. Create a NEW dedicated App Registration
In **Azure Portal → Microsoft Entra ID → App registrations → New registration**: name it **"Repuro Cockpit Calendar"**, single tenant, no redirect URI.

**Do NOT reuse the existing mail app** (the one the email proxy uses) — it holds `Mail.Read/ReadWrite`, and its secret must never land on Fly. The cockpit app gets `Calendars.Read` only; a leak of the Fly secret then exposes calendars, not mailboxes.

### 2. Add API permissions
- Under **API permissions → Add a permission → Microsoft Graph → Application permissions**
- Add: `Calendars.Read`
- Click **Grant admin consent for [your tenant]**

### 3. Create a client secret
- Under **Certificates & secrets → New client secret**
- Copy the value immediately — it is not shown again

### 4. Note the IDs
- **Tenant ID**: Azure AD → Overview → Tenant ID
- **Client ID**: App registration → Overview → Application (client) ID
- **Client Secret**: value from step 3

### 5. Set environment variables on Fly
```
flyctl secrets set -a repuro-suite \
  COCKPIT_GRAPH_TENANT=kamucapital.onmicrosoft.com \
  COCKPIT_GRAPH_CLIENT_ID=<client-id> \
  COCKPIT_GRAPH_CLIENT_SECRET=<client-secret>
```
(Setting secrets restarts the app — data is safe, it lives on the volume.)

### 6. Each user connects their own UPN
In the Calendar view, each user enters their Microsoft 365 email (UPN) and clicks Connect. The backend validates via a probe call before saving.

## Fake/demo mode
Set `COCKPIT_CALENDAR_FAKE=1` to enable deterministic demo events (no Azure credentials needed). Useful for local dev and testing.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `consent_missing` in UI | App lacks `Calendars.Read` grant | Repeat step 2 |
| `unknown_upn` on connect | UPN not found in tenant | Check spelling; user must be in the same tenant |
| No events shown | UPN not connected | Each user must connect individually |
| Events stale | In-memory cache (5 min TTL) | Reload or wait |
