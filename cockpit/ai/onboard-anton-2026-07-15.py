"""Anton onboarding — PROD data flip. Run ONLY AFTER deploying suite v2.1.28
(branch prod/team-login-2026-07-15, commit a4c4e1d): the old frontend would
show Anton the founders' agent queue if perms flip first.

Run (Bash tool, ignore flyctl exit code, check for === DONE ===):
  curl -s https://repuro-suite.fly.dev/healthz   # wake machine, expect 200
  cat "cockpit/ai/onboard-anton-2026-07-15.py" | flyctl ssh console --app repuro-suite -C "python3 -"

What it does (idempotent — safe to re-run; the agent-user POST 409s if it exists):
  1. users.team        -> name Anton, initials AN (login 'team' unchanged; Caddy cred unchanged)
  2. teams.team perms  -> + week:rw + agents:rw (keeps allex:rw / dealroom:ro — Caddy /allex + /deals authz reads these)
  3. users.ac-agent    -> role=agent, represents=team  => Anton's runner lane 'AC'
     TOKEN IS PRINTED ONCE — give it to Anton for /repuro:setup <token>
  4. verifies the team principal: modules, zero foreign agent tasks, scoped learnings
"""

import json
import urllib.request
import urllib.error
import sys

BASE = "http://localhost:8083/api"


def api(method, path, body=None, user="roman"):
    hdr = {"X-Remote-User": user, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(
            f"  {method} {path} -> {e.code}: {e.read().decode()[:200]}", file=sys.stderr
        )
        return None


print("1) rename team user -> Anton (AN)")
print("  ", api("PATCH", "/admin/user/team", {"name": "Anton", "initials": "AN"}))

print("2) team perms += week:rw, agents:rw")
print(
    "  ",
    api(
        "PATCH",
        "/admin/team/team",
        {
            "permissions": {
                "overview": "ro",
                "week": "rw",
                "workstreams": "rw",
                "timeline": "ro",
                "agents": "rw",
                "allex": "rw",
                "dealroom": "ro",
            }
        },
    ),
)

print("3) agent user for Anton's lane")
agent = api(
    "POST",
    "/admin/user",
    {
        "id": "ac-agent",
        "name": "Anton's Claude",
        "initials": "AC",
        "role": "agent",
        "represents": "team",
    },
)
if agent:
    print(
        f"   >>> ANTON RUNNER TOKEN (shown once, for /repuro:setup): {agent['token']}"
    )
else:
    print("   ac-agent already exists (token unchanged)")

print("4) verify as team principal")
st = api("GET", "/state", user="team")
if not st:
    print("   VERIFY FAILED: no state for team")
    sys.exit(1)
p = st["principal"]
tasks = list(st.get("standalone_tasks", []))
for sp in st.get("spaces", []):
    for ws in sp.get("workstreams", []):
        for d in ws.get("deliverables", []):
            tasks.extend(d.get("tasks", []))
foreign = [
    t
    for t in tasks
    if t["execution"] in ("agent_supervised", "agent_auto")
    and t.get("created_by") != "team"
]
checks = {
    "name is Anton": p.get("name") == "Anton",
    "modules incl week+agents": {"week", "agents"} <= set(p.get("modules", [])),
    "not admin": not p.get("is_admin"),
    "zero foreign agent tasks": len(foreign) == 0,
    "learnings scoped": all(l.get("lane") == "team" for l in st.get("learnings", [])),
    "lanes has team->AC": st.get("lanes", {}).get("team") == "AC",
    "users directory present": any(u["id"] == "team" for u in st.get("users", [])),
}
for k, ok in checks.items():
    print(f"   {'PASS' if ok else 'FAIL'} {k}")
print("=== DONE ===" if all(checks.values()) else "=== DONE WITH FAILURES ===")
