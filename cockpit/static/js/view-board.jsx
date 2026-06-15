/* ===== Board — Trello-style kanban, drag cards across status columns ===== */
function TaskCard({ t, draggable, onDragStart, dragging, openTask }) {
  const r = readiness(t);
  const rk = risks(t);
  const deal = dealOf(t);
  const ws = wsOf(t);
  return (
    <div className={"tcard" + (dragging ? " dragging" : "") + (r === "red" ? " is-blocked" : "")}
      draggable={draggable} onDragStart={onDragStart} onClick={() => openTask && openTask(t.id)} data-ws={ws ? ws.id : ""}>
      {r === "red" && <div className="tcard-block"><Icon name="relations" size={11} /> Blocked</div>}
      <div className="tcard-top">
        <span className="tcard-tags">
          <PriorityFlag p={t.priority} />
          <ReadinessDot t={t} />
          {t.execution === "agent" && <span className="agent-tag" title="agent task"><Icon name="bolt" size={10} /></span>}
        </span>
        {deal && <DealChip deal={deal} small />}
      </div>
      <div className="tcard-txt">{t.text}</div>
      {r === "red" && <div className="tcard-need">needs · {blockingPrereqs(t).map((p) => p.text).join(", ")}</div>}
      {t.status === "waiting" && <div className="tcard-wait"><WaitingChip t={t} /></div>}
      <div className="tcard-foot">
        <span className="tcard-ws" style={{ color: ws ? ws.color : "#888" }}>{ws ? ws.name : ""}</span>
        <span className="tcard-foot-r">
          {(t.prereqs && t.prereqs.length) ? <span className="link-mark" title={t.prereqs.length + " prerequisite(s)"}><Icon name="link" size={12} /></span> : null}
          {t.status !== "waiting" && <DueChip t={t} />}
          <OwnerStack owners={t.owners} size={20} />
        </span>
      </div>
    </div>
  );
}

function BoardView({ grouping, mutate, openTask, filters }) {
  const [drag, setDrag] = React.useState(null);
  const [over, setOver] = React.useState(null);
  filters = filters || {};

  let pool = TASKS;
  if (filters.person) pool = pool.filter((t) => (t.owners || []).includes(filters.person));
  if (filters.readiness) pool = pool.filter((t) => readiness(t) === filters.readiness);

  const columns = grouping === "workstream"
    ? WORKSTREAMS.map((w) => ({ id: w.id, label: w.name, color: w.color, tasks: pool.filter((t) => (wsOf(t) || {}).id === w.id) }))
    : STATUS_ORDER.map((s) => ({ id: s, label: STATUS_LABEL[s], tasks: pool.filter((t) => t.status === s) }));

  const canDrag = grouping === "status";

  function onDrop(colId) {
    if (!canDrag || !drag) return;
    const t = byTask[drag];
    if (t && t.status !== colId) {
      if (colId === "waiting") {
        showModal("Who has the ball?", [{placeholder: "seller / advisor / investor name"}]).then((party) => {
          if (party) api.save(t, { waiting: { party, type: "counterparty", chase: addDays(TODAY, 3) } });
        });
      } else {
        api.save(t, { status: colId, ...(colId === "done" ? { pinned: false } : {}) });
      }
    }
    setDrag(null); setOver(null);
  }

  const colAccent = (c) => grouping === "workstream" ? c.color : {
    open: "#9aa9b0", in_progress: "#22d3ee", waiting: "#a855f7", in_review: "#eab308", done: "#16a34a",
  }[c.id];

  return (
    <div>
      <div className="board-hint">
        {canDrag
          ? <><Icon name="board" size={13} /> Drag a card between columns to change its status. Red cards are <b>blocked</b> by an unfinished prerequisite.</>
          : <><Icon name="board" size={13} /> Grouped by workstream. Switch grouping to <b>Status</b> in Tweaks to drag cards.</>}
      </div>
      <div className="board">
        {columns.map((c) => (
          <div key={c.id} className={"bcol" + (over === c.id ? " over" : "")}
            onDragOver={(e) => { if (canDrag) { e.preventDefault(); setOver(c.id); } }}
            onDragLeave={() => setOver(null)}
            onDrop={() => onDrop(c.id)}>
            <div className="bcol-h">
              <span className="bcol-accent" style={{ background: colAccent(c) }} />
              <span className="bcol-name">{c.label}</span>
              <span className="bcol-n">{c.tasks.length}</span>
            </div>
            <div className="bcol-body">
              {c.tasks.map((t) => (
                <TaskCard key={t.id} t={t} draggable={canDrag} openTask={openTask}
                  dragging={drag === t.id}
                  onDragStart={(e) => { setDrag(t.id); e.dataTransfer.effectAllowed = "move"; }} />
              ))}
              {!c.tasks.length && <div className="bcol-empty">—</div>}
              {canDrag && <button className="btn ghost bcol-add" onClick={() => window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { status: c.id } }))}><Icon name="plus" size={13} />New task</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
window.BoardView = BoardView;
