/* ===== Overview — the Cockpit landing (merged with My Week content) ===== */
function delivStats(d) {
  const tasks = TASKS.filter((t) => t.d === d.id);
  const open = tasks.filter((t) => t.status !== "done");
  const done = tasks.length - open.length;
  let r = "green";
  for (const t of open) { const x = readiness(t); if (x === "red") r = "red"; else if (x === "amber" && r !== "red") r = "amber"; }
  return { total: tasks.length, done, open: open.length, readiness: open.length ? r : "green" };
}

/* Private per-user todo list — kind="personal", scoped server-side to the logged-in principal.
   Built from the SAME pieces as every other list section: card + wk-h + WeekRow + ghost "+ add"
   (which opens the standard QuickAdd in Personal mode). No bespoke widgets. */
function PersonalTodos({ mutate, openTask }) {
  const code = PRINCIPAL && PRINCIPAL.id === "ff" ? "FF" : "RD";
  const open = PERSONAL.filter((t) => t.status !== "done");
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="wk-h">My personal list<span className="wk-n">{open.length}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>private to {PEOPLE[code].name}</span>
      </div>
      {open.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} showDate={false} />)}
      {!open.length && <div className="empty">nothing private pending</div>}
      <button className="btn ghost" style={{ fontSize: 11, padding: "2px 8px", marginTop: 4 }}
        onClick={() => window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { type: "personal" } }))}>
        <Icon name="plus" size={11} /> add personal todo
      </button>
    </div>
  );
}

function OverviewView({ person, onJump, openTask, mutate }) {
  return (
    <div className="ov">
      {/* No in-view hero — the global topbar (title + date crumb) is the single, consistent
          header across every tab (Workstreams/Timeline/Agents already follow this). */}
      <WeekView person={person} mutate={mutate} openTask={openTask} embedded={true} />
      <PersonalTodos mutate={mutate} openTask={openTask} />
    </div>
  );
}
window.OverviewView = OverviewView;
window.delivStats = delivStats;
