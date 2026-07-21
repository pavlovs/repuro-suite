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

async function editWs(w) {
  const name = await showModal("Workstream name:", [{value: w.name}]);
  if (name === null || !name.trim() || name.trim() === w.name) return;
  api.saveWs(w, { name: name.trim() });
}

const DEAL_STAGES = [
  { value: "initial_contact", label: "Initial contact" },
  { value: "screening", label: "Screening" },
  { value: "nda", label: "NDA" },
  { value: "valuation_rfi", label: "Valuation / RFI" },
  { value: "indicative_offer", label: "Indicative offer" },
  { value: "loi_signed", label: "LOI signed" },
  { value: "dd", label: "Due diligence" },
  { value: "spa", label: "SPA" },
  { value: "signing", label: "Signing" },
  { value: "on_hold", label: "On hold" },
  { value: "dead", label: "Dead" },
];

async function editDealStage(w) {
  const result = await showModal("Deal: " + (w.deal || w.name), [
    {label: "Stage", type: "select", value: w.dealStage || "",
      options: DEAL_STAGES},
  ]);
  if (result === null) return;
  const [stage] = result;
  if (stage && stage !== w.dealStage) {
    api.saveDeal(w.deal, { stage });
  }
}

async function editDeliv(d) {
  const result = await showModal("Edit deliverable", [
    {label: "Name", value: d.name},
    {label: "Target date", type: "date", value: d.target || ""},
    {label: "Workstream", type: "select", value: d.ws,
      options: WORKSTREAMS.map((w) => ({ value: w.id, label: w.name }))},
  ]);
  if (result === null) return;
  const [name, target, wsId] = result;
  const changes = { name: name.trim() || d.name, target_date: target.trim() || null };
  if (wsId && wsId !== d.ws) changes.workstream_id = wsId;
  api.saveDeliv(d, changes);
}

async function editTask(t) {
  const deliv = byDeliv[t.d];
  const ws = deliv ? byWs[deliv.ws] : null;
  const context = ws && deliv ? ws.name + " › " + deliv.name : deliv ? deliv.name : null;
  const result = await showModal(context ? "Edit task — " + context : "Edit task", [
    {label: "Task", value: t.text},
    {label: "Due date", type: "date", value: t.ownDue || ""},
  ]);
  if (result === null) return;
  const [text, due] = result;
  const changes = {};
  if (text.trim() && text.trim() !== t.text) changes.text = text.trim();
  if (due !== (t.ownDue || "")) changes.due = due || null;
  if (Object.keys(changes).length) api.save(t, changes);
}

function TableView({ mutate, openTask, openDeliv, filters }) {
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
  const [showAllDeals, setShowAllDeals] = React.useState(false);
  const [delivDragId, setDelivDragId] = React.useState(null);
  const [delivOverId, setDelivOverId] = React.useState(null);
  const readOnly = !(window.COCKPIT && (window.COCKPIT.isAdmin || (window.COCKPIT.perms && window.COCKPIT.perms.workstreams === "rw")));
  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }));
  const toggleWs = (id) => setWsOpen((o) => ({ ...o, [id]: !o[id] }));
  const allExpanded = Object.values(wsOpen).every(Boolean);
  const toggleAll = () => {
    const next = !allExpanded;
    setWsOpen(Object.fromEntries(WORKSTREAMS.map((w) => [w.id, next])));
    setOpen(Object.fromEntries(DELIVERABLES.map((d) => [d.id, next])));
  };

  const visible = (t) => {
    if (t.execution === "agent") return false;
    if (!filters.showDone && t.status === "done") return false;
    if (filters.person && !(t.owners || []).includes(filters.person)) return false;
    if (filters.readiness && readiness(t) !== filters.readiness) return false;
    if (filters.priority && (t.priority || "") !== filters.priority) return false;
    return true;
  };

  const isDelivDrag = (e) => e.dataTransfer.types.includes("text/deliv-id");

  const TRow = ({ t, dragHandlers }) => {
    const dragging = dragHandlers && dragHandlers["data-dragging"] === "true";
    const dragOver = dragHandlers && dragHandlers["data-drag-over"] === "true";
    const extraClass = (dragging ? " dragging" : "") + (dragOver ? " drag-over" : "");
    const blocked = readiness(t) === "red";
    const prereqs = blocked ? blockingPrereqs(t) : [];
    return (
      <div className="trow-hovergroup">
        <div className={"trow" + (t.status === "done" ? " done" : "") + extraClass} {...(dragHandlers || {})}>
          <span className="tc-txt tc-click" onClick={() => openTask(t.id)} title="open task">
            <span className="tc-main">{t.text}</span>
            {blocked && <span className="tc-blocked">Blocked</span>}
            <button className="rep-act rep-act--edit tc-edit" title="edit task name / due date"
              onClick={(e) => { e.stopPropagation(); editTask(t); }} />
          </span>
          <span><OwnerStack owners={t.owners} size={22} /></span>
          <span><DueChip t={t} /></span>
        </div>
        {prereqs.map((p) => (
          <div key={p.id} className="trow prereq-row">
            <span className="tc-txt prereq-txt" onClick={() => openTask(p.id)} title="open blocking task">
              <span className="prereq-connector">&#x21B3;</span>
              <span className="prereq-label">blocked by:</span>
              <span className="prereq-name">{p.text}</span>
            </span>
            <span></span>
            <span></span>
          </div>
        ))}
      </div>
    );
  };

  // standalone tasks have no workstream — a workstream filter excludes them
  const standalone = filters.workstream ? [] : TASKS.filter((t) => !t.d && visible(t))
    .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));

  return (
    <div className="tbl">
      <div className="trow thead tbl-sticky">
        <span>Task</span><span>Owner</span><span>Due</span>
      </div>
      {SPACES.map((space) => {
        let allSpaceWs = (wsPerSpace[space.id] || []);
        if (filters.workstream) allSpaceWs = allSpaceWs.filter((w) => w.id === filters.workstream);
        const hiddenCount = allSpaceWs.filter((w) => w.visibility === "hidden").length;
        const spaceWs = showAllDeals ? allSpaceWs : allSpaceWs.filter((w) => w.visibility !== "hidden");
        if (!spaceWs.length && !hiddenCount) return null;
        return (
          <div key={space.id} className="space-group">
            <div className="space-band">
              {space.name}
              <span className="space-count">{spaceWs.length}</span>
              {hiddenCount > 0 && (
                <button className="space-band-toggle" onClick={() => setShowAllDeals((v) => !v)}>
                  {showAllDeals ? "hide inactive" : "+" + hiddenCount + " inactive"}
                </button>
              )}
            </div>
            {spaceWs.map((w) => {
              const delivs = DELIVERABLES.filter((d) => d.ws === w.id);
              const flat = delivs.length === 1;
              return (
                <div key={w.id} className="ws-group" style={{ "--ws": w.color }}>
                  <div className="ws-band" onClick={() => toggleWs(w.id)} style={{cursor:"pointer"}}>
                    <span className={"caret" + (wsOpen[w.id] ? " open" : "")} style={{marginRight:4}}><Icon name="chevron" size={14} /></span>
                    <span className="ws-ico" style={{ background: w.color }}><Icon name={w.icon} size={14} /></span>
                    {w.displayNum && <span className="num-prefix">{w.displayNum}</span>}
                    <span className="ws-name">{w.name}</span>
                    <button className="rep-act rep-act--edit" title="Rename workstream" onClick={(e) => { e.stopPropagation(); editWs(w); }} />
                    {!readOnly && <button className="rep-act rep-act--add" title="add a deliverable (milestone) to this workstream"
                      onClick={(e) => {
                        e.stopPropagation();
                        window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { type: "deliverable", ws: w.id } }));
                      }} />}
                    <span className="deliv-sp" />
                    {w.deal && w.dealStage && (
                      <span className="ws-stage" data-active={w.visibility === "expanded" ? "true" : "false"}
                        title={"Deal stage — click to change"}
                        style={{cursor:"pointer"}}
                        onClick={(e) => { e.stopPropagation(); editDealStage(w); }}>
                        {STAGE_LABEL[w.dealStage] || w.dealStage}
                      </span>
                    )}
                    {flat && delivs[0] && (
                      <button className="ws-band-target" title="deliverable target — click to edit"
                        onClick={(e) => { e.stopPropagation(); openDeliv && openDeliv(delivs[0].id); }}>
                        {delivs[0].target ? "target " + fdate(delivs[0].target) : "set target"} ✎
                      </button>
                    )}
                  </div>
                  {wsOpen[w.id] && (flat
                    ? (delivs[0] ? (() => {
                        const flatTasks = TASKS.filter((t) => t.d === delivs[0].id && visible(t))
                          .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));
                        return (
                          <DragList items={flatTasks} onReorder={(items) => api.reorder(items.map((t) => t.id))}
                            renderItem={(t, h) => <TRow key={t.id} t={t} dragHandlers={h} />} />
                        );
                      })() : null)
                    : delivs.map((d) => {
                      const allDelivTasks = TASKS.filter((t) => t.d === d.id);
                      const delivDone = d.status === "done" || d.status === "dropped" ||
                        (allDelivTasks.length > 0 && allDelivTasks.every((t) => t.status === "done"));
                      const tasks = TASKS.filter((t) => t.d === d.id && visible(t))
                        .sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0));
                      // Hide non-done deliverables whose tasks all filter out; keep done ones
                      // visible (greyed) so Roman can find and archive them.
                      if (!delivDone && allDelivTasks.length > 0 && (filters.person || filters.readiness || !filters.showDone)) { if (!tasks.length) return null; }
                      const du = daysUntil(d.target);
                      return (
                        <div key={d.id} className={"deliv" + (delivDone ? " done" : "")}
                          data-deliv-dragging={delivDragId === d.id ? "true" : undefined}
                          data-deliv-over={delivOverId === d.id && delivDragId !== d.id ? "true" : undefined}
                          onDragOver={(e) => { if (!isDelivDrag(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "move"; if (delivOverId !== d.id) setDelivOverId(d.id); }}
                          onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDelivOverId(null); }}
                          onDrop={(e) => {
                            if (!isDelivDrag(e)) return;
                            e.preventDefault(); setDelivOverId(null); setDelivDragId(null);
                            const srcId = e.dataTransfer.getData("text/deliv-id");
                            if (srcId === d.id) return;
                            const wsDelivs = DELIVERABLES.filter((x) => x.ws === d.ws);
                            const ids = wsDelivs.map((x) => x.id);
                            const srcIdx = ids.indexOf(srcId);
                            const tgtIdx = ids.indexOf(d.id);
                            if (srcIdx < 0) return;
                            ids.splice(srcIdx, 1);
                            ids.splice(tgtIdx, 0, srcId);
                            api.reorderDelivs(ids);
                          }}>
                          <div className="deliv-h" draggable={true}
                            onDragStart={(e) => { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/deliv-id", d.id); setDelivDragId(d.id); e.stopPropagation(); }}
                            onDragEnd={() => { setDelivDragId(null); setDelivOverId(null); }}
                            onClick={() => toggle(d.id)}>
                            <span className={"caret" + (open[d.id] ? " open" : "")}><Icon name="chevron" size={14} /></span>
                            {d.displayNum && <span className="num-prefix">{d.displayNum}</span>}
                            <span className="deliv-name">{d.name}</span>
                            <button className="rep-act rep-act--edit" title="rename / set target date"
                              onClick={(e) => { e.stopPropagation(); openDeliv && openDeliv(d.id); }} />
                            {!readOnly && <button className="rep-act rep-act--add" title="add task"
                              onClick={(e) => { e.stopPropagation(); window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } })); }} />}
                            <span className="deliv-sp" />
                            {d.target && <span className={"deliv-due" + (d.hardDeadline ? " hard-deadline-due" : "") + (du < 0 ? " over" : du <= 7 ? " soon" : "")}>{du < 0 ? "overdue " : "due "}{fdate(d.target)}</span>}
                          </div>
                          {(open[d.id] !== false) && (
                            <div className="deliv-body">
                              <DragList items={tasks} onReorder={(items) => api.reorder(items.map((t) => t.id))}
                                renderItem={(t, h) => <TRow key={t.id} t={t} dragHandlers={h} />} />
                              {!tasks.length && <div className="trow"><span className="tc-txt empty">no matching tasks</span><span></span><span></span></div>}
                            </div>
                          )}
                        </div>
                      );
                    }))}
                </div>
              );
            })}
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

function DeliverableView({ mutate, openTask, openDeliv, filters }) {
  filters = filters || {};
  const [expanded, setExpanded] = React.useState({});
  const toggle = (id) => setExpanded((o) => ({ ...o, [id]: !o[id] }));
  const readOnly = !(window.COCKPIT && (window.COCKPIT.isAdmin || (window.COCKPIT.perms && window.COCKPIT.perms.workstreams === "rw")));

  function personGroups(person) {
    const out = [];
    for (const ws of WORKSTREAMS) {
      if (filters.workstream && ws.id !== filters.workstream) continue;
      const matching = [];
      for (const d of DELIVERABLES.filter((d) => d.ws === ws.id)) {
        const allTasks = TASKS.filter((t) => t.d === d.id);
        const personTasks = allTasks.filter((t) => (t.owners || []).includes(person));
        if (!personTasks.length) continue;
        const openTasks = personTasks.filter((t) => t.status !== "done");
        if (!openTasks.length) continue;  // skip deliverables where all person tasks are done
        const s = delivStats(d);
        matching.push({ d, personTasks: openTasks, openTasks, s });
      }
      if (matching.length) out.push({ ws, delivs: matching });
    }
    return out;
  }

  const colPeople = meFirst(Object.keys(PEOPLE));

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
                    <button className="rep-act rep-act--edit" title="rename / set target date"
                      onClick={(e) => { e.stopPropagation(); openDeliv && openDeliv(d.id); }} />
                    {!readOnly && <button className="rep-act rep-act--add" title="add task to this deliverable"
                      onClick={(e) => { e.stopPropagation(); window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } })); }} />}
                    {d.target && <span className={"deliv-due" + (d.hardDeadline ? " hard-deadline-due" : "") + (du < 0 ? " over" : du <= 7 ? " soon" : "")} style={{ fontSize: 11 }}>{fdate(d.target)}</span>}
                  </div>
                  {isOpen && (
                    <div style={{ marginTop: 4 }}>
                      {personTasks.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} />)}
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
    <div className={"wk-cols wk-cols-" + Math.min(colPeople.length, 3)} style={{ marginTop: 12 }}>
      {colPeople.map((p) => <PersonCol key={p} id={p} groups={personGroups(p)} />)}
    </div>
  );
}
window.DeliverableView = DeliverableView;
