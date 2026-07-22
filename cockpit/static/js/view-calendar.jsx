/* ===== Calendar — week-grid view with team scope + connect flow ===== */

function CalendarView() {
  const [scope, setScope] = React.useState("me");
  const [weekStart, setWeekStart] = React.useState(() => {
    // Monday of current week
    const d = new Date(todayDate);
    const dow = d.getDay();
    d.setDate(d.getDate() - (dow === 0 ? 6 : dow - 1));
    return localISO(d);
  });
  const [data, setData] = React.useState(null); // {status, users, events}
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState(null);
  // connect flow
  const [upnInput, setUpnInput] = React.useState("");
  const [connectErr, setConnectErr] = React.useState(null);
  const [connecting, setConnecting] = React.useState(false);

  const isAdmin = !!(window.COCKPIT && window.COCKPIT.isAdmin);

  function weekDays() {
    const days = [];
    for (let i = 0; i < 7; i++) days.push(addDays(weekStart, i));
    return days;
  }

  function prevWeek() { setWeekStart(addDays(weekStart, -7)); }
  function nextWeek() { setWeekStart(addDays(weekStart, 7)); }
  function goToday() {
    const d = new Date(todayDate);
    const dow = d.getDay();
    d.setDate(d.getDate() - (dow === 0 ? 6 : dow - 1));
    setWeekStart(localISO(d));
  }

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    api.calendarEvents(scope, weekStart, 7)
      .then((d) => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch((e) => { if (!cancelled) { setErr(e.message || "fetch error"); setLoading(false); } });
    return () => { cancelled = true; };
  }, [scope, weekStart]);

  async function handleConnect(e) {
    e.preventDefault();
    setConnecting(true);
    setConnectErr(null);
    try {
      const r = await api.calendarConnect(upnInput.trim());
      if (r.ok) {
        setUpnInput("");
        try {
          setData(await api.calendarEvents(scope, weekStart, 7));
        } catch (e3) {
          setConnectErr("Connected — refresh failed, reload the page.");
        }
      } else {
        if (r.text.includes("unknown_upn")) setConnectErr("Address not found in Azure — check spelling.");
        else if (r.text.includes("consent_missing")) setConnectErr("Admin consent not configured. Ask Roman to complete Azure setup.");
        else setConnectErr("Error: " + r.text.slice(0, 120));
      }
    } catch (e2) {
      setConnectErr(e2.message || "network error");
    }
    setConnecting(false);
  }

  // two-step: first click arms the inline confirm, only the confirm writes
  const [disconnectArmed, setDisconnectArmed] = React.useState(false);
  async function handleDisconnect() {
    setDisconnectArmed(false);
    try {
      await api.calendarConnect("");
      setData(await api.calendarEvents(scope, weekStart, 7));
    } catch (e2) {
      setConnectErr(e2.message || "network error");
    }
  }

  // Inline avatar for calendar (server-supplied, not PEOPLE map)
  function CalAvatar({ user, size = 22 }) {
    const colors = ["#0891B2", "#7C3AED", "#DC2626", "#059669", "#D97706"];
    const color = colors[(user.id || "").charCodeAt(0) % colors.length];
    return (
      <span className="avatar" title={user.name} style={{ width: size, height: size, background: color, fontSize: size * 0.42 }}>
        {user.initials || (user.name || "?")[0]}
      </span>
    );
  }

  const days = weekDays();
  const today = localISO(todayDate);

  // Render the not-configured card
  function renderSetupCard() {
    const status = data && data.status;
    if (status === "consent_missing") {
      if (isAdmin) {
        return (
          <div className="card cal-setup-card">
            <div className="cal-setup-title"><Icon name="calendar" size={18} /> Azure Admin Setup Required</div>
            <p className="cal-setup-body">One-time step — full click-path in <code>cockpit/ai/CALENDAR-SETUP.md</code>:</p>
            <ol className="cal-setup-steps">
              <li>Azure Portal → Entra ID → App registrations → <strong>New registration</strong> "Repuro Cockpit Calendar" (single tenant, no redirect URI)</li>
              <li>API permissions → Microsoft Graph → <strong>Application</strong> → <code>Calendars.Read</code> → <strong>Grant admin consent</strong></li>
              <li>Certificates &amp; secrets → new client secret</li>
              <li><code>fly secrets set COCKPIT_GRAPH_TENANT=… COCKPIT_GRAPH_CLIENT_ID=… COCKPIT_GRAPH_CLIENT_SECRET=…</code></li>
            </ol>
          </div>
        );
      }
      return (
        <div className="card cal-setup-card">
          <Icon name="calendar" size={18} />
          <div className="cal-setup-title">Calendar backend not enabled yet — ping Roman</div>
        </div>
      );
    }
    if (status === "not_configured") {
      return (
        <div className="card cal-setup-card">
          <div className="cal-setup-title"><Icon name="calendar" size={18} /> Connect your calendar</div>
          <p className="cal-setup-body">Enter your work email (@repuro.de) to link your calendar. Your events become visible to your team in Calendar + Meeting views — events marked private stay masked.</p>
          <form className="cal-connect-form" onSubmit={handleConnect}>
            <input
              className="cal-connect-input"
              type="email"
              placeholder="you@company.com"
              value={upnInput}
              onChange={(e) => setUpnInput(e.target.value)}
              required
            />
            <button className="btn primary" type="submit" disabled={connecting}>
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </form>
          {connectErr && <div className="cal-connect-err">{connectErr}</div>}
        </div>
      );
    }
    return null;
  }

  // Check if the current user is connected
  const myConnected = data && data.users && data.users.find((u) => {
    const pid = PRINCIPAL && PRINCIPAL.id;
    return u.id === pid;
  });
  const showConnectForm = data && data.status === "ok" && myConnected && !myConnected.connected;

  // Group events by date for the grid
  function eventsOnDay(iso) {
    if (!data || !data.events) return [];
    return data.events.filter((ev) => {
      if (!ev.all_day) return (ev.start || "").startsWith(iso);
      // all-day spans render on EVERY covered day; Graph end date is exclusive
      const s = (ev.start || "").slice(0, 10);
      const e = (ev.end || "").slice(0, 10);
      return e > s ? (iso >= s && iso < e) : iso === s;
    });
  }

  function fmtTime(iso) {
    if (!iso) return "";
    const m = iso.match(/T(\d{2}):(\d{2})/);
    if (!m) return "";
    return m[1] + ":" + m[2];
  }

  const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  return (
    <div className="cal-root">
      {/* Toolbar */}
      <div className="cal-toolbar">
        <div className="seg">
          <button className={scope === "me" ? "on" : ""} onClick={() => setScope("me")}>Me</button>
          <button className={scope === "team" ? "on" : ""} onClick={() => setScope("team")}>Team</button>
        </div>
        <div className="cal-week-nav">
          <button className="cal-nav-btn" onClick={prevWeek} title="Previous week">‹</button>
          <button className="cal-nav-btn cal-today-btn" onClick={goToday}>Today</button>
          <button className="cal-nav-btn" onClick={nextWeek} title="Next week">›</button>
        </div>
        <div className="cal-week-label">
          {days[0].replace(/-/g, "/")} – {days[6].replace(/-/g, "/")}
        </div>
        {/* User legend chips — team scope only */}
        {scope === "team" && data && data.users && (
          <div className="cal-legend">
            {data.users.filter((u) => u.connected).map((u) => (
              <span key={u.id} className="cal-legend-chip">
                <CalAvatar user={u} size={18} />
                <span>{u.name}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Setup / consent cards */}
      {data && renderSetupCard()}

      {/* Connect own calendar inline nudge */}
      {showConnectForm && (
        <div className="card cal-connect-nudge">
          <span className="cal-setup-title">Connect your calendar to see your events</span>
          <p className="cal-setup-body" style={{margin: "4px 0 0"}}>Your events become visible to your team in Calendar + Meeting views — events marked private stay masked.</p>
          <form className="cal-connect-form" onSubmit={handleConnect} style={{marginTop: 8}}>
            <input
              className="cal-connect-input"
              type="email"
              placeholder="you@company.com"
              value={upnInput}
              onChange={(e) => setUpnInput(e.target.value)}
              required
            />
            <button className="btn primary" type="submit" disabled={connecting}>
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </form>
          {connectErr && <div className="cal-connect-err">{connectErr}</div>}
        </div>
      )}

      {/* Disconnect link for connected user — armed confirm, no one-click unlink */}
      {data && data.status === "ok" && myConnected && myConnected.connected && (
        <div className="cal-disconnect-row">
          {!disconnectArmed ? (
            <button className="cal-disconnect-btn" onClick={() => setDisconnectArmed(true)} title="Unlink your calendar">Disconnect calendar</button>
          ) : (
            <span className="cal-disconnect-confirm">
              Removes your calendar from the team view.
              <button className="btn reject" style={{fontSize: 11, padding: "3px 10px"}} onClick={handleDisconnect}>Disconnect</button>
              <button className="btn" style={{fontSize: 11, padding: "3px 10px"}} onClick={() => setDisconnectArmed(false)}>Cancel</button>
            </span>
          )}
        </div>
      )}

      {loading && <div className="empty">Loading…</div>}
      {err && <div className="empty bad">Error: {err}</div>}

      {/* Week grid */}
      {data && data.status === "ok" && !loading && (
        <div className="cal-grid">
          {days.map((day, di) => {
            const isToday = day === today;
            const dayEvs = eventsOnDay(day);
            const allDay = dayEvs.filter((e) => e.all_day);
            const timed = dayEvs.filter((e) => !e.all_day);
            return (
              <div key={day} className={"cal-col" + (isToday ? " cal-col--today" : "")}>
                <div className="cal-col-hd">
                  <span className="cal-day-label">{DAY_LABELS[di]}</span>
                  <span className={"cal-day-num" + (isToday ? " cal-day-num--today" : "")}>{day.slice(8)}</span>
                </div>
                {/* All-day events pinned at top */}
                {allDay.map((ev, i) => (
                  <div key={i} className={"cal-ev cal-ev--allday" + (ev.private ? " cal-ev--private" : "")}>
                    {scope === "team" && <CalAvatar user={ev.user} size={14} />}
                    <span className="cal-ev-title">{ev.subject}</span>
                  </div>
                ))}
                {/* Timed events */}
                {timed.map((ev, i) => (
                  <div key={i} className={"cal-ev" + (ev.private ? " cal-ev--private" : "") + (ev.show_as === "free" ? " cal-ev--free" : "")}>
                    <div className="cal-ev-time">{fmtTime(ev.start)}</div>
                    <div className="cal-ev-body">
                      {scope === "team" && <CalAvatar user={ev.user} size={14} />}
                      <span className="cal-ev-title">{ev.subject}</span>
                      {ev.location && <span className="cal-ev-loc">{ev.location}</span>}
                      {ev.online_url && (
                        <a className="cal-ev-join" href={ev.online_url} target="_blank" rel="noreferrer">Join</a>
                      )}
                    </div>
                  </div>
                ))}
                {!dayEvs.length && <div className="cal-col-empty" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

window.CalendarView = CalendarView;
