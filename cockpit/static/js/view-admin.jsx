/* ===== Admin — user/team management, workstream team assignment ===== */
/* Visible only to is_admin principals (app.jsx gates the tab render). */

function AdminView() {
  var dataState = React.useState(null);
  var data = dataState[0], setData = dataState[1];
  var errState = React.useState(null);
  var err = errState[0], setErr = errState[1];

  function adminFetch(path, opts) {
    var base = window.COCKPIT_BASE || "";
    var token = sessionStorage.getItem("cockpit_token") || "";
    var headers = Object.assign(
      { "Content-Type": "application/json" },
      token ? { Authorization: "Bearer " + token } : {},
      (opts && opts.headers) || {}
    );
    return fetch(base + path, Object.assign({}, opts, { headers: headers }));
  }

  function load() {
    setErr(null);
    adminFetch("/api/admin/overview")
      .then(function(r) {
        if (!r.ok) return r.text().then(function(t) { throw new Error(r.status + " " + t); });
        return r.json();
      })
      .then(function(d) { setData(d); })
      .catch(function(e) { setErr(e.message); });
  }

  React.useEffect(function() { load(); }, []);

  if (err) return (
    <div style={{ padding: "24px", color: "var(--err, #dc2626)", fontSize: 13 }}>
      Failed to load admin data: {err}
    </div>
  );
  if (!data) return (
    <div style={{ padding: "24px", color: "var(--muted)", fontSize: 13 }}>Loading…</div>
  );

  return (
    <div style={{ padding: "20px 24px", maxWidth: 900, display: "flex", flexDirection: "column", gap: 32 }}>
      <AdminUsersSection data={data} reload={load} adminFetch={adminFetch} />
      <AdminTeamsSection data={data} reload={load} adminFetch={adminFetch} />
      <AdminWsSection data={data} reload={load} adminFetch={adminFetch} />
    </div>
  );
}

/* ---- Users ---- */
function AdminUsersSection({ data, reload, adminFetch }) {
  var formState = React.useState(false);
  var showForm = formState[0], setShowForm = formState[1];
  var fieldState = React.useState({ id: "", name: "", initials: "", login: "", calendar_upn: "", teams: [] });
  var f = fieldState[0], setF = fieldState[1];
  var busyState = React.useState(false);
  var busy = busyState[0], setBusy = busyState[1];
  var tokenState = React.useState(null);
  var newToken = tokenState[0], setNewToken = tokenState[1];

  function submit() {
    if (!f.id.trim() || !f.name.trim()) return showToast("id and name required", "err");
    setBusy(true);
    adminFetch("/api/admin/user", {
      method: "POST",
      body: JSON.stringify({
        id: f.id.trim(),
        name: f.name.trim(),
        initials: f.initials.trim() || undefined,
        login: f.login.trim() || undefined,
        calendar_upn: f.calendar_upn.trim() || undefined,
        teams: f.teams,
      }),
    })
      .then(function(r) {
        setBusy(false);
        if (r.status === 409) { showToast("User ID already exists", "err"); return null; }
        if (!r.ok) { r.text().then(function(t) { showToast("Error: " + t.slice(0, 120), "err"); }); return null; }
        return r.json();
      })
      .then(function(d) {
        if (!d) return;
        setNewToken(d.token);
        setF({ id: "", name: "", initials: "", login: "", calendar_upn: "", teams: [] });
        setShowForm(false);
        reload();
      });
  }

  var teamOptions = data.teams.map(function(t) { return t.id; });

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "var(--ink)" }}>Users</h2>
        <button className="btn" style={{ fontSize: 12 }} onClick={function() { setShowForm(!showForm); setNewToken(null); }}>
          {showForm ? "Cancel" : "+ New user"}
        </button>
      </div>
      <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--muted)" }}>
        Work email set = that person's calendar is visible to the whole team in Calendar + Meeting views.
      </p>

      {newToken && (
        <div style={{ marginBottom: 10, padding: "8px 12px", background: "var(--brand-50, #ecfeff)", borderRadius: 7, fontSize: 12 }}>
          Token (copy now — shown once): <code style={{ userSelect: "all", fontFamily: "monospace" }}>{newToken}</code>
        </div>
      )}

      {showForm && (
        <div style={{ marginBottom: 12, padding: "12px 14px", border: "1px solid var(--line)", borderRadius: 8, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          {[["ID", "id", "e.g. hj"], ["Name", "name", "Full name"], ["Initials", "initials", "HJ"], ["Login (Caddy user)", "login", "heiko"], ["Work email (calendar)", "calendar_upn", "name@repuro.de"]].map(function(x) {
            return (
              <label key={x[1]} style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--ink-2)" }}>
                {x[0]}
                <input
                  style={{ padding: "5px 8px", border: "1px solid var(--line)", borderRadius: 5, font: "13px var(--font)", width: 130 }}
                  placeholder={x[2]}
                  value={f[x[1]]}
                  onChange={function(e) { var k = x[1]; setF(function(s) { return Object.assign({}, s, { [k]: e.target.value }); }); }}
                />
              </label>
            );
          })}
          <label style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--ink-2)" }}>
            Teams
            <select
              multiple
              style={{ padding: "4px 6px", border: "1px solid var(--line)", borderRadius: 5, font: "12px var(--font)", minWidth: 110, height: 62 }}
              value={f.teams}
              onChange={function(e) {
                var sel = Array.from(e.target.selectedOptions).map(function(o) { return o.value; });
                setF(function(s) { return Object.assign({}, s, { teams: sel }); });
              }}
            >
              {teamOptions.map(function(tid) { return <option key={tid} value={tid}>{tid}</option>; })}
            </select>
          </label>
          <button className="btn approve" disabled={busy} onClick={submit} style={{ alignSelf: "flex-end" }}>
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--line-2)" }}>
            {["ID", "Name", "Initials", "Role", "Login", "Work email (calendar)", "Teams"].map(function(h) {
              return <th key={h} style={{ textAlign: "left", padding: "4px 8px", color: "var(--muted)", fontWeight: 600 }}>{h}</th>;
            })}
          </tr>
        </thead>
        <tbody>
          {data.users.map(function(u) {
            return (
              <tr key={u.id} style={{ borderBottom: "1px solid var(--line-2)" }}>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11 }}>{u.id}</td>
                <td style={{ padding: "5px 8px" }}>{u.name}</td>
                <td style={{ padding: "5px 8px", color: "var(--muted)" }}>{u.initials || "—"}</td>
                <td style={{ padding: "5px 8px", color: "var(--muted)" }}>{u.role}</td>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11, color: "var(--muted)" }}>{u.login || "—"}</td>
                <td style={{ padding: "4px 8px" }}>
                  <AdminUserEmailCell u={u} adminFetch={adminFetch} reload={reload} />
                </td>
                <td style={{ padding: "5px 8px" }}>
                  {u.teams.length ? u.teams.join(", ") : <span style={{ color: "var(--faint)" }}>none</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

/* Work-email cell — admin sets a user's calendar identity (@repuro.de).
   Having an email set = calendar connected; the user does nothing themselves.
   Save is TWO-STEP: the consequence (team-wide visibility) is stated inline
   and confirmed before anything is written — no silent connect/disconnect. */
function AdminUserEmailCell({ u, adminFetch, reload }) {
  var valState = React.useState(u.calendar_upn || "");
  var val = valState[0], setVal = valState[1];
  var busyState = React.useState(false);
  var busy = busyState[0], setBusy = busyState[1];
  var confirmState = React.useState(null); // null | "connect" | "disconnect"
  var confirming = confirmState[0], setConfirming = confirmState[1];
  React.useEffect(function() { setVal(u.calendar_upn || ""); setConfirming(null); }, [u.calendar_upn]);

  if (u.role !== "human") return <span style={{ color: "var(--faint)" }}>—</span>;

  var dirty = val.trim() !== (u.calendar_upn || "");

  function save() {
    setBusy(true);
    setConfirming(null);
    adminFetch("/api/admin/user/" + u.id, {
      method: "PATCH",
      body: JSON.stringify({ calendar_upn: val.trim() }),
    }).then(function(r) {
      setBusy(false);
      if (!r.ok) {
        r.text().then(function(t) {
          showToast(t.indexOf("unknown_upn") >= 0 ? "Mailbox not found — check the address" : "Error: " + t.slice(0, 120), "err");
        });
        return;
      }
      showToast(val.trim() ? "Calendar connected for " + u.name : "Calendar disconnected for " + u.name);
      reload();
    });
  }

  return (
    <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
      <input
        style={{ padding: "4px 7px", border: "1px solid var(--line)", borderRadius: 5, font: "11px monospace", width: 190 }}
        placeholder="name@repuro.de"
        value={val}
        onChange={function(e) { setVal(e.target.value); setConfirming(null); }}
        onKeyDown={function(e) { if (e.key === "Enter" && dirty && !busy && !confirming) setConfirming(val.trim() ? "connect" : "disconnect"); }}
      />
      {dirty && !confirming && (
        <button className="btn" style={{ fontSize: 11, padding: "3px 10px" }} disabled={busy}
          onClick={function() { setConfirming(val.trim() ? "connect" : "disconnect"); }}>
          {busy ? "…" : "Save"}
        </button>
      )}
      {confirming && (
        <span style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: "var(--ink-2)" }}>
          {confirming === "connect"
            ? "Makes " + u.name + "'s calendar visible to everyone in Calendar + Meeting views."
            : "Removes " + u.name + "'s calendar from the team view."}
          <button className={"btn " + (confirming === "connect" ? "approve" : "reject")} style={{ fontSize: 11, padding: "3px 10px" }} disabled={busy} onClick={save}>
            {confirming === "connect" ? "Connect" : "Disconnect"}
          </button>
          <button className="btn" style={{ fontSize: 11, padding: "3px 10px" }} onClick={function() { setConfirming(null); }}>
            Cancel
          </button>
        </span>
      )}
    </span>
  );
}

/* ---- Teams ---- */
function AdminTeamsSection({ data, reload, adminFetch }) {
  var formState = React.useState(false);
  var showForm = formState[0], setShowForm = formState[1];
  var fieldState = React.useState({ id: "", name: "", is_admin: false, perms: {} });
  var f = fieldState[0], setF = fieldState[1];
  var busyState = React.useState(false);
  var busy = busyState[0], setBusy = busyState[1];

  var ALL_MODS = ["overview", "week", "workstreams", "timeline", "agents", "relations", "dealroom", "allex"];

  function submit() {
    if (!f.id.trim() || !f.name.trim()) return showToast("id and name required", "err");
    setBusy(true);
    adminFetch("/api/admin/team", {
      method: "POST",
      body: JSON.stringify({ id: f.id.trim(), name: f.name.trim(), is_admin: f.is_admin, permissions: f.perms }),
    })
      .then(function(r) {
        setBusy(false);
        if (r.status === 409) { showToast("Team ID already exists", "err"); return null; }
        if (!r.ok) { r.text().then(function(t) { showToast("Error: " + t.slice(0, 120), "err"); }); return null; }
        return r.json();
      })
      .then(function(d) {
        if (!d) return;
        setF({ id: "", name: "", is_admin: false, perms: {} });
        setShowForm(false);
        reload();
      });
  }

  function setModPerm(mod, val) {
    setF(function(s) {
      var p = Object.assign({}, s.perms);
      if (!val) { delete p[mod]; } else { p[mod] = val; }
      return Object.assign({}, s, { perms: p });
    });
  }

  return (
    <section>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "var(--ink)" }}>Teams</h2>
        <button className="btn" style={{ fontSize: 12 }} onClick={function() { setShowForm(!showForm); }}>
          {showForm ? "Cancel" : "+ New team"}
        </button>
      </div>

      {showForm && (
        <div style={{ marginBottom: 12, padding: "12px 14px", border: "1px solid var(--line)", borderRadius: 8 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
            {[["ID", "id", "e.g. viewer"], ["Name", "name", "Display name"]].map(function(x) {
              return (
                <label key={x[1]} style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11, color: "var(--ink-2)" }}>
                  {x[0]}
                  <input
                    style={{ padding: "5px 8px", border: "1px solid var(--line)", borderRadius: 5, font: "13px var(--font)", width: 160 }}
                    placeholder={x[2]}
                    value={f[x[1]]}
                    onChange={function(e) { var k = x[1]; setF(function(s) { return Object.assign({}, s, { [k]: e.target.value }); }); }}
                  />
                </label>
              );
            })}
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--ink-2)", alignSelf: "flex-end", marginBottom: 1 }}>
              <input type="checkbox" checked={f.is_admin} onChange={function(e) { setF(function(s) { return Object.assign({}, s, { is_admin: e.target.checked }); }); }} />
              Admin (all modules rw)
            </label>
          </div>
          {!f.is_admin && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, color: "var(--ink-2)", marginBottom: 4 }}>Module permissions</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {ALL_MODS.map(function(mod) {
                  return (
                    <label key={mod} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, background: "var(--surface, #f8fafc)", border: "1px solid var(--line)", borderRadius: 5, padding: "3px 8px" }}>
                      {mod}
                      <select
                        style={{ border: "none", background: "transparent", font: "11px var(--font)", cursor: "pointer" }}
                        value={f.perms[mod] || ""}
                        onChange={function(e) { setModPerm(mod, e.target.value); }}
                      >
                        <option value="">—</option>
                        <option value="ro">ro</option>
                        <option value="rw">rw</option>
                      </select>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
          <button className="btn approve" disabled={busy} onClick={submit}>
            {busy ? "Creating…" : "Create team"}
          </button>
        </div>
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--line-2)" }}>
            {["ID", "Name", "Admin", "Permissions", "Members"].map(function(h) {
              return <th key={h} style={{ textAlign: "left", padding: "4px 8px", color: "var(--muted)", fontWeight: 600 }}>{h}</th>;
            })}
          </tr>
        </thead>
        <tbody>
          {data.teams.map(function(t) {
            var permStr = t.is_admin ? "all rw" : Object.entries(t.permissions).map(function(kv) { return kv[0] + ":" + kv[1]; }).join(", ") || "—";
            return (
              <tr key={t.id} style={{ borderBottom: "1px solid var(--line-2)" }}>
                <td style={{ padding: "5px 8px", fontFamily: "monospace", fontSize: 11 }}>{t.id}</td>
                <td style={{ padding: "5px 8px" }}>{t.name}</td>
                <td style={{ padding: "5px 8px", color: t.is_admin ? "var(--brand)" : "var(--faint)" }}>{t.is_admin ? "yes" : "no"}</td>
                <td style={{ padding: "5px 8px", color: "var(--muted)", fontFamily: "monospace", fontSize: 11 }}>{permStr}</td>
                <td style={{ padding: "5px 8px" }}>
                  {t.members.length ? t.members.join(", ") : <span style={{ color: "var(--faint)" }}>none</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

/* ---- Workstream assignments ---- */
function AdminWsSection({ data, reload, adminFetch }) {
  var allWs = [];
  (window.WORKSTREAMS || []).forEach(function(w) { allWs.push(w); });

  var teamIds = data.teams.map(function(t) { return t.id; });

  function assign(wid, teamIdsCsv) {
    var teams = teamIdsCsv ? teamIdsCsv.split(",").map(function(s) { return s.trim(); }).filter(Boolean) : [];
    adminFetch("/api/workstream/" + wid + "/teams", {
      method: "PATCH",
      body: JSON.stringify({ team_ids: teams }),
    })
      .then(function(r) {
        if (!r.ok) { r.text().then(function(t) { showToast("Error: " + t.slice(0, 120), "err"); }); return; }
        reload();
      });
  }

  return (
    <section>
      <h2 style={{ margin: "0 0 10px", fontSize: 15, fontWeight: 700, color: "var(--ink)" }}>Workstream Team Assignments</h2>
      <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--muted)" }}>
        No assignment = visible to all. Assign to one or more teams to restrict visibility.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--line-2)" }}>
            {["Workstream", "Assigned teams", "Assign to (team ID, comma-sep)"].map(function(h) {
              return <th key={h} style={{ textAlign: "left", padding: "4px 8px", color: "var(--muted)", fontWeight: 600 }}>{h}</th>;
            })}
          </tr>
        </thead>
        <tbody>
          {allWs.map(function(w) {
            var asgn = data.workstream_assignments[w.id];
            var current = asgn ? asgn.teams.join(", ") : "";
            return (
              <AdminWsRow key={w.id} w={w} current={current} teamIds={teamIds} onAssign={assign} />
            );
          })}
          {allWs.length === 0 && (
            <tr><td colSpan={3} style={{ padding: "10px 8px", color: "var(--faint)", fontStyle: "italic" }}>No workstreams yet.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

function AdminWsRow({ w, current, teamIds, onAssign }) {
  var valState = React.useState(current);
  var val = valState[0], setVal = valState[1];
  React.useEffect(function() { setVal(current); }, [current]);

  return (
    <tr style={{ borderBottom: "1px solid var(--line-2)" }}>
      <td style={{ padding: "5px 8px" }}>{w.name}</td>
      <td style={{ padding: "5px 8px", color: current ? "var(--ink)" : "var(--faint)", fontStyle: current ? "normal" : "italic" }}>
        {current || "all (unrestricted)"}
      </td>
      <td style={{ padding: "4px 8px", display: "flex", gap: 6, alignItems: "center" }}>
        <input
          style={{ padding: "4px 7px", border: "1px solid var(--line)", borderRadius: 5, font: "12px var(--font)", width: 180 }}
          placeholder={teamIds.join(", ")}
          value={val}
          onChange={function(e) { setVal(e.target.value); }}
        />
        <button className="btn" style={{ fontSize: 11, padding: "3px 10px" }} onClick={function() { onAssign(w.id, val); }}>
          Save
        </button>
        {val && (
          <button className="btn" style={{ fontSize: 11, padding: "3px 10px" }} onClick={function() { setVal(""); onAssign(w.id, ""); }}>
            Clear
          </button>
        )}
      </td>
    </tr>
  );
}
