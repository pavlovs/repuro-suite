/* ===== Overview — the Cockpit landing (merged with My Week content) ===== */
function delivStats(d) {
  const tasks = TASKS.filter((t) => t.d === d.id);
  const open = tasks.filter((t) => t.status !== "done");
  const done = tasks.length - open.length;
  let r = "green";
  for (const t of open) { const x = readiness(t); if (x === "red") r = "red"; else if (x === "amber" && r !== "red") r = "amber"; }
  return { total: tasks.length, done, open: open.length, readiness: open.length ? r : "green" };
}

/* Private per-user todo list — kind="personal", scoped server-side to the logged-in
   principal (the other person never receives them). Lives only on the Cockpit landing. */
function PersonalTodos() {
  const code = PRINCIPAL && PRINCIPAL.id === "ff" ? "FF" : "RD";
  const open = PERSONAL.filter((t) => t.status !== "done");
  const done = PERSONAL.filter((t) => t.status === "done");
  const [text, setText] = React.useState("");
  const add = async () => {
    const v = text.trim();
    if (!v) return;
    setText("");
    await api.create({ text: v, kind: "personal", owners: [code], execution: "me" });
  };
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="wk-h">
        <Icon name="check" size={14} /> My personal list<span className="wk-n">{open.length}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>private to {PEOPLE[code].name}</span>
      </div>
      <div style={{ display: "flex", gap: 6, margin: "8px 0" }}>
        <input className="qa-input" style={{ flex: 1 }} placeholder="Add a private todo…" value={text}
          onChange={(e) => setText(e.target.value)} onKeyUp={(e) => e.key === "Enter" && add()} />
        <button className="btn primary" onClick={add}><Icon name="plus" size={13} /> Add</button>
      </div>
      {open.map((t) => (
        <div key={t.id} className="wkrow">
          <button className="chk" data-on={false} onClick={() => api.save(t, { status: "done" })} title="mark done" />
          <div className="wkrow-txt"><span className="wkrow-main">{t.text}</span></div>
          <button className="dlr-rm" title="delete" onClick={() => api.deleteTask(t)}>×</button>
        </div>
      ))}
      {!open.length && <div className="empty">nothing private pending</div>}
      {done.length > 0 && (
        <React.Fragment>
          <div className="wk-grp">Done<span className="dm-n">{done.length}</span></div>
          {done.map((t) => (
            <div key={t.id} className="wkrow done">
              <button className="chk" data-on={true} onClick={() => api.save(t, { status: "open" })} title="reopen"><Icon name="check" size={12} /></button>
              <div className="wkrow-txt"><span className="wkrow-main" style={{ textDecoration: "line-through", opacity: 0.6 }}>{t.text}</span></div>
              <button className="dlr-rm" title="delete" onClick={() => api.deleteTask(t)}>×</button>
            </div>
          ))}
        </React.Fragment>
      )}
    </div>
  );
}

function OverviewView({ person, onJump, openTask, mutate }) {
  return (
    <div className="ov">
      {/* No in-view hero — the global topbar (title + date crumb) is the single, consistent
          header across every tab (Workstreams/Timeline/Agents already follow this). */}
      <WeekView person={person} mutate={mutate} openTask={openTask} embedded={true} />
      <PersonalTodos />
    </div>
  );
}
window.OverviewView = OverviewView;
window.delivStats = delivStats;
