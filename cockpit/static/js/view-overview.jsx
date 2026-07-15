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
   Add happens inline here only — personal kind is NOT available in the top QuickAdd modal. */
function PersonalTodos({ mutate, openTask, bare }) {
  const code = ME;
  const open = PERSONAL.filter((t) => t.status !== "done");
  const [adding, setAdding] = React.useState(false);
  const [text, setText] = React.useState("");
  const busyRef = React.useRef(false);

  const submitPersonal = async () => {
    if (busyRef.current) return;
    if (!text.trim()) return;
    busyRef.current = true;
    try {
      await api.create({ text: text.trim(), kind: "personal", owners: [code], execution: "me" });
      setText("");
      setAdding(false);
    } catch (_) {}
    busyRef.current = false;
  };

  const body = (
    <>
      {open.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} showDate={false} />)}
      {!open.length && !adding && <div className="empty">nothing private pending</div>}
      {adding ? (
        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          <input className="qa-input" autoFocus style={{ flex: 1, fontSize: 12, padding: "3px 7px" }}
            placeholder="Private todo…" value={text} onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submitPersonal(); } if (e.key === "Escape") { setAdding(false); setText(""); } }} />
          <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={submitPersonal}>Add</button>
          <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => { setAdding(false); setText(""); }}>✕</button>
        </div>
      ) : (
        <button className="btn ghost" style={{ fontSize: 11, padding: "2px 8px", marginTop: 4 }}
          onClick={() => setAdding(true)}>
          <Icon name="plus" size={11} /> add personal todo
        </button>
      )}
    </>
  );

  // bare = render rows + add only (used inside the switchable right column, which supplies its own header/card)
  if (bare) return body;

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="wk-h">My personal list<span className="wk-n">{open.length}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>private to {(PEOPLE[code] || {}).name || code}</span>
      </div>
      {body}
    </div>
  );
}

function OverviewView({ person, onJump, openTask, mutate }) {
  return (
    <div className="ov">
      {/* No in-view hero — the global topbar (title + date crumb) is the single, consistent
          header across every tab (Workstreams/Timeline/Agents already follow this). */}
      <WeekView person={person} mutate={mutate} openTask={openTask} embedded={true} />
    </div>
  );
}
window.OverviewView = OverviewView;
window.delivStats = delivStats;
