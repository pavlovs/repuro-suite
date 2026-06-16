/* ===== Workstreams — Monday-style grouped table.
   One sticky header for the whole table; single-deliverable groups flatten
   (the middle layer only appears when it separates real milestones). ===== */
function StatusCell({ t, mutate }) {
  const next = { open: "in_progress", in_progress: "in_review", in_review: "done", done: "open", waiting: "open" };
  const bg = { open: "#9aa9b0", in_progress: "#22b8d6", waiting: "#a855f7", in_review: "#eab308", done: "#16a34a" }[t.status];
  return (
    <button className="status-cell" style={{ background: bg }}
      onClick={() => api.save(t, { status: next[t.status], ...(next[t.status] === "done" ? { pinned: false } : {}) })}
      title="click to advance status">
      {STATUS_LABEL[t.status]}
    </button>
  );
}

async function editDeliv(d) {
  const name = await showModal("Deliverable name:", [{value: d.name}]);
  if (name === null) return;
  const target = await showModal("Target date (empty = none):", [{type: "date", value: d.target || ""}]);
  if (target === null) return;
  api.saveDeliv(d, { name: name.trim() || d.name, target_date: target.trim() || null });
}

function TableView({ mutate, openTask, filters }) {
  const [open, setOpen] = React.useState(() => {
    const init = {};
    DELIVERABLES.forEach((d) => {
      const tasks = TASKS.filter((t) => t.d === d.id && t.status !== "done");
      const needsAttention = tasks.some((t) => readiness(t) === "red" || (t.due && daysUntil(t.due) < 0));
      init[d.id] = needsAttention;
    });
    return init;
  });
  const [wsOpen, setWsOpen] = React.useState(() => Object.fromEntries(WORKSTREAMS.map((w) => [w.id, true])));
  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }));
  const toggleWs = (id) => setWsOpen((o) => ({ ...o, [id]: !o[id] }));
  const allExpanded = Object.values(wsOpen).every(Boolean);
  const toggleAll = () => {
    const next = !allExpanded;
    setWsOpen(Object.fromEntries(WORKSTREAMS.map((w) => [w.id, next])));
    setOpen(Object.fromEntries(DELIVERABLES.map((d) => [d.id, next])));
  };

  const visible = (t) => {
    if (!filters.showDone && t.status === "done") return false;
    if (filters.person && !(t.owners || []).includes(filters.person)) return false;
    if (filters.readiness && readiness(t) !== filters.readiness) return false;
    return true;
  };

  const TRow = ({ t }) => (
    <div className={"trow" + (t.status === "done" ? " done" : "")}>
      <span className="tc-r"><ReadinessDot t={t} /></span>
      <span className="tc-txt tc-click" onClick={() => openTask(t.id)} title="open & edit">
        <PriorityFlag p={t.priority} />
        <span className="tc-main">{t.text}</span>
        {t.status === "waiting" && <WaitingChip t={t} />}
        {(t.prereqs && t.prereqs.length) ? <span className="tc-pre" title={"needs: " + blockingPrereqs(t).map((p) => p.text).join(", ")}><Icon name="link" size={11} /> {t.prereqs.length}</span> : null}
      </span>
      <span><StatusCell t={t} mutate={mutate} /></span>
      <span><OwnerStack owners={t.owners} size={22} /></span>
      <span><DueChip t={t} /></span>
      <span className="tc-pin">
        <button className={"pin-btn" + (t.pinned ? " on" : "")} title={t.pinned ? "unpin" : "pin to today"} onClick={() => api.save(t, { pinned: !t.pinned })}><Icon name="pin" size={13} /></button>
      </span>
    </div>
  );

  const standalone = TASKS.filter((t) => !t.d && visible(t));

  return (
    <div className="tbl">
      <div className="trow thead tbl-sticky">
        <span></span><span>Task</span><span>Status</span><span>Owner</span><span>Due</span>
        <span><button className="pin-btn" title={allExpanded ? "collapse all" : "expand all"} onClick={toggleAll} style={{fontSize:11,opacity:.6}}>{allExpanded ? "▾" : "▸"}</button></span>
      </div>
      {WORKSTREAMS.map((w) => {
        const delivs = DELIVERABLES.filter((d) => d.ws === w.id);
        const flat = delivs.length === 1; // middle layer earns its place only with >1 milestone
        return (
          <div key={w.id} className="ws-group" style={{ "--ws": w.color }}>
            <div className="ws-band" onClick={() => toggleWs(w.id)} style={{cursor:"pointer"}}>
              <span className={"caret" + (wsOpen[w.id] ? " open" : "")} style={{marginRight:4}}><Icon name="chevron" size={14} /></span>
              <span className="ws-ico" style={{ background: w.color }}><Icon name={w.icon} size={14} /></span>
              <span className="ws-name">{w.name}</span>
              {flat && delivs[0] && (
                <button className="ws-band-target" title="deliverable target — click to edit"
                  onClick={(e) => { e.stopPropagation(); editDeliv(delivs[0]); }}>
                  {delivs[0].target ? "target " + fdate(delivs[0].target) : "set target"} ✎
                </button>
              )}
              {!flat && <span className="ws-count">{delivs.length} deliverables</span>}
              <button className="ws-band-target" style={{ marginLeft: "auto", border: "1px dashed var(--line)", color: "var(--muted)" }}
                title="add a deliverable (milestone) to this workstream"
                onClick={(e) => {
                  e.stopPropagation();
                  window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { type: "deliverable", ws: w.id } }));
                }}>+ deliverable</button>
            </div>
            {wsOpen[w.id] && (flat
              ? (delivs[0] ? TASKS.filter((t) => t.d === delivs[0].id && visible(t)).map((t) => <TRow key={t.id} t={t} />) : null)
              : delivs.map((d) => {
                const tasks = TASKS.filter((t) => t.d === d.id && visible(t));
                if (filters.person || filters.readiness || !filters.showDone) { if (!tasks.length) return null; }
                const s = delivStats(d);
                const du = daysUntil(d.target);
                return (
                  <div key={d.id} className="deliv">
                    <div className="deliv-h" onClick={() => toggle(d.id)}>
                      <span className={"caret" + (open[d.id] ? " open" : "")}><Icon name="chevron" size={14} /></span>
                      <span className="deliv-name">{d.name}</span>
                      <button className="deliv-edit" title="rename / set target date"
                        onClick={(e) => { e.stopPropagation(); editDeliv(d); }}>✎</button>
                      {d.deal && <DealChip deal={d.deal} small />}
                      <span className="deliv-prog">
                        <span className="prog-bar"><span style={{ width: (s.total ? s.done / s.total * 100 : 0) + "%", background: w.color }} /></span>
                        {s.done}/{s.total}
                      </span>
                      {d.target && <span className={"deliv-due" + (du < 0 ? " over" : du <= 7 ? " soon" : "")}>{du < 0 ? "overdue " : "due "}{fdate(d.target)}</span>}
                    </div>
                    {open[d.id] && (
                      <div className="deliv-body">
                        {tasks.map((t) => <TRow key={t.id} t={t} />)}
                        {!tasks.length && <div className="trow"><span></span><span className="empty">no matching tasks</span></div>}
                      </div>
                    )}
                  </div>
                );
              }))}
          </div>
        );
      })}
      {standalone.length > 0 && (
        <div className="ws-group" style={{ "--ws": "#64748b" }}>
          <div className="ws-band">
            <span className="ws-ico" style={{ background: "#64748b" }}><Icon name="ops" size={14} /></span>
            <span className="ws-name">Standalone</span>
            <span className="ws-count">not assigned to a workstream</span>
          </div>
          {standalone.map((t) => <TRow key={t.id} t={t} />)}
        </div>
      )}
    </div>
  );
}
window.TableView = TableView;

function DeliverableView({ mutate, openTask }) {
  const [expanded, setExpanded] = React.useState({});
  const toggle = (id) => setExpanded((o) => ({ ...o, [id]: !o[id] }));

  function personGroups(person) {
    const out = [];
    for (const ws of WORKSTREAMS) {
      const matching = [];
      for (const d of DELIVERABLES.filter((d) => d.ws === ws.id)) {
        const allTasks = TASKS.filter((t) => t.d === d.id);
        const personTasks = allTasks.filter((t) => (t.owners || []).includes(person));
        if (!personTasks.length) continue;
        const openTasks = personTasks.filter((t) => t.status !== "done");
        const s = delivStats(d);
        matching.push({ d, personTasks, openTasks, s });
      }
      if (matching.length) out.push({ ws, delivs: matching });
    }
    return out;
  }

  const rdGroups = personGroups("RD");
  const ffGroups = personGroups("FF");

  const PersonCol = ({ id, groups }) => {
    const totalDelivs = groups.reduce((n, g) => n + g.delivs.length, 0);
    return (
      <div className="card wk-col">
        <div className="wk-h"><Avatar id={id} size={18} /> {PEOPLE[id].name}<span className="wk-n">{totalDelivs}</span></div>
        {groups.map(({ ws, delivs }) => (
          <React.Fragment key={ws.id}>
            <div className="wk-grp wk-ws-grp" style={{ color: ws.color }}>
              <span className="ws-ico" style={{ background: ws.color, width: 16, height: 16, borderRadius: 4, display: "inline-flex", alignItems: "center", justifyContent: "center", marginRight: 6 }}>
                <Icon name={ws.icon} size={10} />
              </span>
              {ws.name}
            </div>
            {delivs.map(({ d, personTasks, openTasks, s }) => {
              const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
              const du = d.target ? daysUntil(d.target) : null;
              const needsAttention = openTasks.some((t) => readiness(t) === "red" || (t.due && daysUntil(t.due) < 0));
              const isOpen = expanded[d.id + "-" + id] !== undefined ? expanded[d.id + "-" + id] : needsAttention;
              return (
                <div key={d.id} className="wk-deliv-block">
                  <div className="wk-deliv-head" style={{ cursor: "pointer" }} onClick={() => toggle(d.id + "-" + id)}>
                    <span className={"caret" + (isOpen ? " open" : "")}><Icon name="chevron" size={12} /></span>
                    <span className="wk-deliv-name">{d.name}</span>
                    {d.deal && <DealChip deal={d.deal} small />}
                    <span className="wk-deliv-prog">
                      <span className="prog-bar" style={{ width: 60 }}><span style={{ width: pct + "%", background: ws.color }} /></span>
                      <span style={{ fontSize: 11, color: "#64748b" }}>{s.done}/{s.total}</span>
                    </span>
                    {d.target && <span className={"deliv-due" + (du < 0 ? " over" : du <= 7 ? " soon" : "")} style={{ fontSize: 11 }}>{fdate(d.target)}</span>}
                    <button className="deliv-edit" title="rename / set target date" style={{marginLeft:4}}
                      onClick={(e) => { e.stopPropagation(); editDeliv(d); }}>✎</button>
                  </div>
                  {isOpen && (
                    <div style={{ marginTop: 4 }}>
                      {personTasks.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} />)}
                      <button className="btn ghost" style={{ fontSize: 11, padding: "2px 8px", marginTop: 2 }}
                        onClick={() => window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } }))}>
                        <Icon name="plus" size={11} /> add task
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </React.Fragment>
        ))}
        {!groups.length && <div className="empty">no deliverables</div>}
      </div>
    );
  };

  return (
    <div className="wk-cols wk-cols-2" style={{ marginTop: 12 }}>
      <PersonCol id="RD" groups={rdGroups} />
      <PersonCol id="FF" groups={ffGroups} />
    </div>
  );
}
window.DeliverableView = DeliverableView;
