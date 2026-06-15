/* ===== App shell: nav, topbar, palette, quick-add, shared drawer ===== */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "direction": "command",
  "density": "roomy",
  "nav": "sidebar"
}/*EDITMODE-END*/;

function RepuroMark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" className="mark">
      <defs>
        <linearGradient id="rg" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0" stopColor="#22D3EE" /><stop offset="1" stopColor="#0891B2" />
        </linearGradient>
      </defs>
      <rect x="0.5" y="0.5" width="31" height="31" rx="9" fill="url(#rg)" />
      <rect x="7" y="17.5" width="7.5" height="7.5" rx="2" fill="#fff" opacity="0.95" />
      <rect x="12.25" y="12.25" width="7.5" height="7.5" rx="2" fill="#fff" opacity="0.78" />
      <rect x="17.5" y="7" width="7.5" height="7.5" rx="2" fill="#fff" />
    </svg>
  );
}

const NAV = [
  { id: "overview", label: "Cockpit", icon: "cockpit", crumb: "Intelligence overview" },
  { id: "week", label: "My Week", icon: "week", crumb: "Daily & weekly focus" },
  { id: "table", label: "Workstreams", icon: "table", crumb: "All work — table or board" },
  { id: "relations", label: "Relations", icon: "relations", crumb: "Dependency map" },
  { id: "timeline", label: "Timeline", icon: "timeline", crumb: "Milestones & windows" },
  { id: "agents", label: "Agents", icon: "bolt", crumb: "Claude works · you approve" },
];

/* Workstreams tab: one dataset, two layouts (table / board), shared filters */
function WorkstreamsTab({ mutate, openTask, person, onNewDeal }) {
  const [layout, setLayout] = React.useState("table");
  const [grouping, setGrouping] = React.useState("status");
  const [filters, setFilters] = React.useState({ person: "", readiness: "", showDone: false });

  return (
    <div>
      <div className="ws-toolbar">
        <div className="seg layout-seg">
          <button className={layout === "table" ? "on" : ""} onClick={() => setLayout("table")}><Icon name="table" size={14} />Table</button>
          <button className={layout === "board" ? "on" : ""} onClick={() => setLayout("board")}><Icon name="board" size={14} />Board</button>
        </div>
        {layout === "board" && (
          <div className="seg">
            <span className="seg-lbl">group by</span>
            <button className={grouping === "status" ? "on" : ""} onClick={() => setGrouping("status")}>Status</button>
            <button className={grouping === "workstream" ? "on" : ""} onClick={() => setGrouping("workstream")}>Workstream</button>
          </div>
        )}
        <div className="ws-toolbar-sp" />
        <button className="btn ghost" onClick={onNewDeal}><Icon name="deal" size={14} />New deal (playbook)</button>
      </div>

      <div className="tbl-filters">
        <div className="seg">
          {[["", "Everyone"], ["RD", "Roman"], ["FF", "Flo"]].map(([v, l]) => (
            <button key={v} className={filters.person === v ? "on" : ""} onClick={() => setFilters({ ...filters, person: v })}>{l}</button>
          ))}
        </div>
        <div className="seg">
          {[["", "Any readiness"], ["red", "Blocked"], ["amber", "Prereqs running"], ["green", "Ready"]].map(([v, l]) => (
            <button key={v} className={filters.readiness === v ? "on" : ""} onClick={() => setFilters({ ...filters, readiness: v })}>
              {v && <span className="rdot" data-level={v} style={{ width: 8, height: 8, marginRight: 5 }} />}{l}
            </button>
          ))}
        </div>
        {layout === "table" && <label className="chk-lbl"><input type="checkbox" checked={filters.showDone} onChange={(e) => setFilters({ ...filters, showDone: e.target.checked })} /> show done</label>}
      </div>

      {layout === "table"
        ? <TableView mutate={mutate} openTask={openTask} filters={filters} />
        : <BoardView grouping={grouping} mutate={mutate} openTask={openTask} filters={filters} />}
    </div>
  );
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = React.useState("overview");
  const [person, setPerson] = React.useState(sessionStorage.getItem("cockpit_person") || "RD");
  const [drawer, setDrawer] = React.useState(null);
  const [palette, setPalette] = React.useState(false);
  const [quickAdd, setQuickAdd] = React.useState(false);
  const [quickAddPrefill, setQuickAddPrefill] = React.useState(null);
  const [newDeal, setNewDeal] = React.useState(false);
  const [meetingMode, setMeeting] = React.useState(false);
  const [, setRev] = React.useState(0);
  const mutate = React.useCallback((fn) => { fn && fn(); setRev((r) => r + 1); }, []);
  const openTask = React.useCallback((id) => setDrawer(id), []);

  // the write-through layer (boot.js api.*) re-renders after every successful save
  React.useEffect(() => {
    window.rerender = () => setRev((r) => r + 1);
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(true); }
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); setQuickAdd(true); }
    };
    const onQuickAdd = (e) => { setQuickAddPrefill(e.detail || null); setQuickAdd(true); };
    const onJumpEvt = (e) => setTab(e.detail || "table");
    window.addEventListener("keydown", onKey);
    window.addEventListener("cockpit:quickadd", onQuickAdd);
    window.addEventListener("cockpit:jump", onJumpEvt);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("cockpit:quickadd", onQuickAdd);
      window.removeEventListener("cockpit:jump", onJumpEvt);
    };
  }, []);
  const pickPerson = (p) => { sessionStorage.setItem("cockpit_person", p); setPerson(p); };

  const live = TASKS.filter((x) => x.status !== "done");
  const blockedN = live.filter((x) => readiness(x) === "red").length;
  const chaseN = live.filter((x) => chaseDue(x)).length;
  const verdictN = TASKS.filter((x) => x.execution === "agent" && x.status === "in_review").length;
  const badge = { relations: blockedN, week: chaseN, agents: verdictN };

  const cur = NAV.find((n) => n.id === tab) || NAV[0];
  const showPerson = tab === "overview" || tab === "week";
  const mtgActive = meetingMode && tab === "week";

  const NavList = ({ inTop }) => (
    <>
      {!inTop && <div className="nav-lbl">Navigate</div>}
      {NAV.map((n) => (
        <button key={n.id} className={"nav-item" + (tab === n.id ? " active" : "")} onClick={() => setTab(n.id)}>
          <Icon name={n.icon} size={18} />
          <span>{n.label}</span>
          {badge[n.id] ? <span className="nav-badge">{badge[n.id]}</span> : null}
        </button>
      ))}
    </>
  );

  return (
    <div className="app" data-direction={t.direction} data-density={t.density} data-nav={t.nav}>
      <aside className="sidebar">
        <a href="/" className="brand" style={{textDecoration:'none',color:'inherit'}}>
          <RepuroMark size={34} />
          <div><div className="wm">Repuro</div><div className="sub">Cockpit</div></div>
        </a>
        <div className="suite-nav" style={{padding:'0 14px 6px'}}>
          <a href="/">Suite</a>
          <a href="/allex/">ALLEX</a>
          <a href="/deals/">DEALRoom</a>
        </div>
        <nav className="side-nav"><NavList /></nav>
        <div className="side-foot">
          <div className="side-user">
            <Avatar id={person} size={30} />
            <div><div className="nm">{PEOPLE[person].full}</div><div className="rl">{PEOPLE[person].role}</div></div>
          </div>
        </div>
      </aside>

      <div className="workarea">
        <header className="topbar">
          <div className="tb-brand"><RepuroMark size={28} /><div className="wm" style={{ fontSize: 15 }}>Repuro</div></div>
          <nav className="tb-nav"><NavList inTop /></nav>
          <div className="tb-title">
            <h1>{cur.label}</h1>
            <div className="crumb">{cur.id === "overview" ? todayDate.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : cur.crumb}</div>
          </div>
          <div className="tb-spacer" />
          <button className="search as-btn" onClick={() => setPalette(true)} title="Search (Ctrl/⌘ K)">
            <Icon name="search" size={15} /><span className="search-ph">Search tasks, deals…</span><span className="pal-kbd">⌘K</span>
          </button>
          {showPerson && (
            <div className="person-switch">
              {["RD", "FF"].map((p) => (
                <button key={p} className={!mtgActive && person === p ? "on" : ""} onClick={() => { pickPerson(p); setMeeting(false); }}>
                  <Avatar id={p} size={18} />{PEOPLE[p].name}
                </button>
              ))}
              {tab === "week" && (
                <button className={mtgActive ? "on" : ""} onClick={() => setMeeting(!meetingMode)}>
                  <Icon name="week" size={15} />Weekly Meeting
                </button>
              )}
            </div>
          )}
          <button className="tb-undo" disabled={!api.undoDepth()} onClick={() => api.undo()}
            title={api.undoDepth() ? "undo last change (" + api.undoDepth() + ")" : "nothing to undo"}>↶ Undo</button>
          <button className="btn primary" onClick={() => setQuickAdd(true)} title="Ctrl/⌘ Enter"><Icon name="plus" size={15} />New</button>
        </header>

        <main className="main">
          <div className={"view" + (tab === "relations" || tab === "timeline" || tab === "table" ? " view-wide" : "")}>
            {tab === "overview" && <OverviewView person={person} onJump={setTab} openTask={openTask} />}
            {tab === "week" && <WeekView person={person} mutate={mutate} openTask={openTask} meetingMode={mtgActive} />}
            {tab === "table" && <WorkstreamsTab mutate={mutate} openTask={openTask} person={person} onNewDeal={() => setNewDeal(true)} />}
            {tab === "relations" && <RelationsView openTask={openTask} />}
            {tab === "timeline" && <TimelineView openTask={openTask} />}
            {tab === "agents" && <AgentsView openTask={openTask} />}
          </div>
        </main>
      </div>

      <TaskDrawer task={drawer ? byTask[drawer] : null} onClose={() => setDrawer(null)} mutate={mutate} openTask={openTask} />
      <Palette open={palette} onClose={() => setPalette(false)} openTask={(id) => { setPalette(false); openTask(id); }} onJump={(v) => { setPalette(false); setTab(v); }} />
      <QuickAdd open={quickAdd} onClose={(id) => { setQuickAdd(false); setQuickAddPrefill(null); if (id) openTask(id); }} prefill={quickAddPrefill} />
      <NewDeal open={newDeal} onClose={() => setNewDeal(false)} />

      <TweaksPanel>
        <TweakSection label="Direction" />
        <TweakRadio label="Look & feel" value={t.direction} options={[{ value: "command", label: "Command" }, { value: "calm", label: "Calm" }]} onChange={(v) => setTweak("direction", v)} />
        <TweakSection label="Layout" />
        <TweakRadio label="Density" value={t.density} options={["compact", "cozy", "roomy"]} onChange={(v) => setTweak("density", v)} />
        <TweakRadio label="Navigation" value={t.nav} options={[{ value: "sidebar", label: "Sidebar" }, { value: "top", label: "Top bar" }]} onChange={(v) => setTweak("nav", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
