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

const NAV_ALL = [
  { id: "overview", module: "overview", label: "Cockpit", icon: "cockpit", crumb: "Intelligence overview" },
  { id: "week", module: "week", label: "Meeting", icon: "week", crumb: "Meeting focus" },
  { id: "calendar", module: "calendar", label: "Calendar", icon: "calendar", crumb: "Your and your team's meetings" },
  { id: "table", module: "workstreams", label: "Workstreams", icon: "table", crumb: "All work — table or board" },
  { id: "timeline", module: "timeline", label: "Timeline", icon: "timeline", crumb: "Milestones & windows" },
  { id: "agents", module: "agents", label: "Agents", icon: "bolt", crumb: "Claude works · you approve" },
];
const _ckModules = (window.COCKPIT && window.COCKPIT.modules) || NAV_ALL.map(n => n.module);
const NAV = NAV_ALL.filter(n => _ckModules.includes(n.module));

/* Workstreams tab: one dataset, two layouts (table / board), shared filters */
function WorkstreamsTab({ mutate, openTask, openDeliv, person, filtersOpen, setFiltersOpen, setFilterCount }) {
  const [layout, setLayout] = React.useState("table");
  const [grouping, setGrouping] = React.useState("workstream");
  const [filters, setFilters] = React.useState({ workstream: "", person: "", readiness: "", priority: "", showDone: false });

  const activeFilterCount = [filters.workstream, filters.person, filters.readiness].filter(f => f !== "").length
    + (layout === "table" && filters.priority !== "" ? 1 : 0)
    + (layout === "table" && filters.showDone ? 1 : 0);
  // Report active-filter count to the topbar Filter button. Every layout has at
  // least the workstream filter now, so the button shows in all of them.
  React.useEffect(() => { setFilterCount && setFilterCount(activeFilterCount); }, [activeFilterCount, layout]);

  return (
    <div>
      <div className="ws-toolbar">
        <div className="seg layout-seg">
          <button className={layout === "deliverables" ? "on" : ""} onClick={() => setLayout("deliverables")}><Icon name="deal" size={14} />Deliverables</button>
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
      </div>

      <FilterBar filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} activeCount={activeFilterCount} hideToggle>
        <label className="filter-ws">
          <span className="filter-ws-lbl">Workstream</span>
          <select value={filters.workstream} onChange={(e) => setFilters({ ...filters, workstream: e.target.value })}>
            <option value="">All workstreams</option>
            {SPACES.map((s) => {
              const list = (wsPerSpace[s.id] || []);
              if (!list.length) return null;
              return (
                <optgroup key={s.id} label={s.name}>
                  {list.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </optgroup>
              );
            })}
          </select>
        </label>
        {layout !== "deliverables" && (
          <label className="filter-ws">
            <span className="filter-ws-lbl">Person</span>
            <select value={filters.person} onChange={(e) => setFilters({ ...filters, person: e.target.value })}>
              <option value="">Everyone</option>
              {meFirst(Object.keys(PEOPLE)).map((p) => (
                <option key={p} value={p}>{PEOPLE[p].full || PEOPLE[p].name}</option>
              ))}
            </select>
          </label>
        )}
        {layout !== "deliverables" && (
          <div className="seg">
            {[["", "Any readiness"], ["red", "Blocked"], ["amber", "Prereqs running"], ["green", "Ready"]].map(([v, l]) => (
              <button key={v} className={filters.readiness === v ? "on" : ""} onClick={() => setFilters({ ...filters, readiness: v })}>
                {v && <span className="rdot" data-level={v} style={{ width: 8, height: 8, marginRight: 5 }} />}{l}
              </button>
            ))}
          </div>
        )}
        {layout === "table" && (
          <div className="seg">
            {[["", "Any priority"], ["high", "High"], ["med", "Medium"]].map(([v, l]) => (
              <button key={v} className={filters.priority === v ? "on" : ""} onClick={() => setFilters({ ...filters, priority: v })}>{l}</button>
            ))}
          </div>
        )}
        {layout === "table" && <label className="chk-lbl"><input type="checkbox" checked={filters.showDone} onChange={(e) => setFilters({ ...filters, showDone: e.target.checked })} /> show done</label>}
      </FilterBar>

      {layout === "deliverables"
        ? <DeliverableView mutate={mutate} openTask={openTask} openDeliv={openDeliv} filters={filters} />
        : layout === "table"
        ? <TableView mutate={mutate} openTask={openTask} openDeliv={openDeliv} filters={filters} />
        : <BoardView grouping={grouping} mutate={mutate} openTask={openTask} filters={filters} />}
    </div>
  );
}

/* Hash-based routing: tab id ↔ URL hash */
const TAB_TO_HASH = { overview: "#cockpit", week: "#week", calendar: "#calendar", table: "#workstreams", timeline: "#timeline", agents: "#agents", admin: "#admin" };
const HASH_TO_TAB = { "#cockpit": "overview", "#week": "week", "#calendar": "calendar", "#workstreams": "table", "#timeline": "timeline", "#agents": "agents", "#admin": "admin" };
const VALID_TABS = new Set(Object.keys(TAB_TO_HASH));
/* Admin is not part of NAV (rendered as a separate button), so the hash
   validator must accept it explicitly for admins — otherwise setTab("admin")
   fires hashchange, tabFromHash rejects it, and the tab bounces straight back. */
const NAV_ADMIN = { id: "admin", label: "Admin", icon: "ops", crumb: "Users, teams & access" };
function _isValidTab(tab) {
  if (NAV.find((n) => n.id === tab)) return true;
  return tab === "admin" && !!(window.COCKPIT && window.COCKPIT.isAdmin);
}
function tabFromHash() {
  const tab = HASH_TO_TAB[window.location.hash];
  const first = NAV[0] ? NAV[0].id : "overview";
  const firstHash = TAB_TO_HASH[first] || "#cockpit";
  if (!tab || !_isValidTab(tab)) {
    history.replaceState(null, "", firstHash);
    return first;
  }
  return tab;
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTabState] = React.useState(tabFromHash);
  const [drawer, setDrawer] = React.useState(null);
  const [delivDrawer, setDelivDrawer] = React.useState(null);
  const [palette, setPalette] = React.useState(false);
  const [quickAdd, setQuickAdd] = React.useState(false);
  const [activityOpen, setActivityOpen] = React.useState(false);
  const [quickAddPrefill, setQuickAddPrefill] = React.useState(null);
  const [filtersOpen, setFiltersOpen] = React.useState(false);
  const [filterCount, setFilterCount] = React.useState(0);
  const [, setRev] = React.useState(0);
  const mutate = React.useCallback((fn) => { fn && fn(); setRev((r) => r + 1); }, []);
  const openTask = React.useCallback((id) => { setDelivDrawer(null); setDrawer(id); }, []);
  const openDeliv = React.useCallback((id) => { setDrawer(null); setDelivDrawer(id); }, []);

  /* Navigate to a tab: update state + URL hash */
  const setTab = React.useCallback((id) => {
    setTabState(id);
    setFiltersOpen(false); // close the filter panel when navigating between tabs
    setFilterCount(0);     // zero synchronously so the topbar never flashes the prior tab's count
    const hash = TAB_TO_HASH[id];
    if (hash && window.location.hash !== hash) window.location.hash = hash;
  }, []);

  // the write-through layer (boot.js api.*) re-renders after every successful save
  React.useEffect(() => {
    window.rerender = () => setRev((r) => r + 1);
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette(true); }
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); setQuickAdd(true); }
    };
    const onQuickAdd = (e) => { setQuickAddPrefill(e.detail || null); setQuickAdd(true); };
    const onJumpEvt = (e) => setTab(e.detail || "table");
    const onHashChange = () => { setTabState(tabFromHash()); setFiltersOpen(false); setFilterCount(0); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("cockpit:quickadd", onQuickAdd);
    window.addEventListener("cockpit:jump", onJumpEvt);
    window.addEventListener("hashchange", onHashChange);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("cockpit:quickadd", onQuickAdd);
      window.removeEventListener("cockpit:jump", onJumpEvt);
      window.removeEventListener("hashchange", onHashChange);
    };
  }, [setTab]);

  const live = TASKS.filter((x) => x.status !== "done");
  const chaseN = live.filter((x) => chaseDue(x)).length;
  const verdictN = TASKS.filter((x) => x.execution === "agent" && (x.status === "in_review" || x.statusRaw === "blocked")).length;
  const badge = { week: chaseN, agents: verdictN };

  const cur = NAV.find((n) => n.id === tab) || (tab === "admin" ? NAV_ADMIN : NAV[0]);
  /* Everyone — admins included — sees their OWN cockpit. The old person-switch
     ("view as") was a v1 relic; removed 2026-07-16 (Roman: no world needs it —
     teammate workload lives in Meeting columns + the Workstreams person filter). */
  const meKey = ME;

  const canWriteWorkstreams = window.COCKPIT && (window.COCKPIT.isAdmin || (window.COCKPIT.perms && window.COCKPIT.perms.workstreams === "rw"));

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
      {window.COCKPIT && window.COCKPIT.isAdmin && (
        <button className={"nav-item" + (tab === "admin" ? " active" : "")} onClick={() => setTab("admin")}>
          <Icon name="ops" size={18} />
          <span>Admin</span>
        </button>
      )}
    </>
  );

  return (
    <div className="app" data-direction={t.direction} data-density={t.density} data-nav={t.nav}>
      {(window.COCKPIT && window.COCKPIT.readOnly) && (
        <div className="read-only-banner">View-only access</div>
      )}
      <aside className="sidebar">
        <a href="/" className="brand" style={{textDecoration:'none',color:'inherit'}}>
          <RepuroMark size={34} />
          <div><div className="wm">Repuro</div><div className="sub">Cockpit</div></div>
        </a>
        <div className="suite-nav" style={{padding:'0 14px 6px'}}>
          <a href="/">Suite</a>
          <a href="/allex/">ALLEX</a>
          <a href="/deals/">Dealroom</a>
        </div>
        <nav className="side-nav"><NavList /></nav>
        <div className="side-foot">
          <div className="side-user">
            <Avatar id={meKey} size={30} />
            <div><div className="nm">{(PEOPLE[meKey] || {}).full || meKey}</div><div className="rl">{(PEOPLE[meKey] || {}).role || ""}</div></div>
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
            <Icon name="search" size={15} /><span className="search-ph">Search tasks, deals…</span><span className="pal-kbd">{navigator.platform.indexOf("Mac") >= 0 ? "⌘" : "Ctrl+"}K</span>
          </button>
          {(tab === "table" || tab === "timeline") && filterCount !== null && (
            <button className={"tb-filter tb-undo" + (filterCount > 0 ? " active" : "")} onClick={() => setFiltersOpen((o) => !o)} title="Filter">
              <Icon name="filter" size={14} /> Filter{filterCount > 0 ? " (" + filterCount + ")" : ""}
            </button>
          )}
          <button className="tb-undo" onClick={() => setActivityOpen(true)} title="Activity log">Activity</button>
          <button className="tb-undo" disabled={!api.undoDepth()} onClick={() => api.undo()}
            title={api.undoDepth() ? "undo last change (" + api.undoDepth() + ")" : "nothing to undo"}>↶ Undo</button>
          {canWriteWorkstreams && (
            <button className="btn primary" onClick={() => setQuickAdd(true)} title="Ctrl/⌘ Enter"><Icon name="plus" size={15} />New</button>
          )}
        </header>

        <main className="main">
          <div className={"view" + (tab === "timeline" || tab === "table" || tab === "week" ? " view-wide" : "")}>
            {tab === "overview" && <OverviewView person={ME} onJump={setTab} openTask={openTask} mutate={mutate} />}
            {tab === "week" && <MeetingView mutate={mutate} openTask={openTask} />}
            {tab === "calendar" && <CalendarView />}
            {tab === "table" && <WorkstreamsTab mutate={mutate} openTask={openTask} openDeliv={openDeliv} person={ME} filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} setFilterCount={setFilterCount} />}
            {tab === "timeline" && <TimelineView openTask={openTask} openDeliv={openDeliv} mutate={mutate} filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} setFilterCount={setFilterCount} />}
            {tab === "agents" && <AgentsView openTask={openTask} person={ME} />}
            {tab === "admin" && <AdminView />}
          </div>
        </main>
      </div>

      <TaskDrawer task={drawer ? byTask[drawer] : null} onClose={() => setDrawer(null)} mutate={mutate} openTask={openTask} />
      <DelivDrawer deliv={delivDrawer ? byDeliv[delivDrawer] : null} onClose={() => setDelivDrawer(null)} mutate={mutate} openTask={openTask} />
      <ActivityPanel open={activityOpen} onClose={() => setActivityOpen(false)} />
      <Palette open={palette} onClose={() => setPalette(false)} openTask={(id) => { setPalette(false); openTask(id); }} onJump={(v) => { setPalette(false); setTab(v); }} />
      <QuickAdd open={quickAdd} onClose={(id) => { setQuickAdd(false); setQuickAddPrefill(null); if (typeof id === "string") { id.startsWith("d-") ? openDeliv(id) : openTask(id); } }} prefill={quickAddPrefill} />

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
