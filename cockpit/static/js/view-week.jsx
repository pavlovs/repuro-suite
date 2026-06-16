/* ===== My Week — computed daily/weekly recommendation + shared lane ===== */

/* --- Weekly Meeting prep view — agenda-structured, both people, decision-first --- */
function MeetingView({ mutate, openTask }) {
  const live = TASKS.filter((t) => t.status !== "done");

  // Deadlines — next upcoming milestone per active deal
  const activeStages = new Set(["loi_signed", "dd", "indicative_offer", "valuation_rfi"]);
  const hasOpenWork = (d) => TASKS.some((t) => t.d === d.id && t.status !== "done");
  const nextByDeal = {};
  DELIVERABLES
    .filter((d) => d.deal && d.target && daysUntil(d.target) >= 0 && activeStages.has(d.deal.stage) && hasOpenWork(d))
    .sort((a, b) => a.target.localeCompare(b.target))
    .forEach((d) => {
      const key = d.deal.codename.trim().toLowerCase();
      if (!nextByDeal[key]) nextByDeal[key] = d;
    });
  const loiDeals = Object.values(nextByDeal).sort((a, b) => a.target.localeCompare(b.target));

  function shortName(d) {
    if (!d.deal) return d.name;
    const cn = d.deal.codename;
    return d.name.toLowerCase().startsWith(cn.toLowerCase())
      ? d.name.slice(cn.length).replace(/^\s*[—–\-]+\s*/, "")
      : d.name;
  }

  // ---- Section 1: Completed since last Monday ----
  const lastMon = new Date(todayDate);
  const dow = lastMon.getDay();
  lastMon.setDate(lastMon.getDate() - (dow === 0 ? 6 : dow - 1));
  if (dow === 1) lastMon.setDate(lastMon.getDate() - 7);
  const lastMonISO = lastMon.toISOString().slice(0, 10);
  const recentDone = TASKS.filter((t) => t.status === "done" && t.doneAt && t.doneAt >= lastMonISO)
    .sort((a, b) => (b.doneAt || "").localeCompare(a.doneAt || ""));
  const rdDone = recentDone.filter((t) => (t.owners || []).includes("RD"));
  const ffDone = recentDone.filter((t) => (t.owners || []).includes("FF"));

  // ---- Section 2: Blockers & decisions (deduplicated — each task appears once) ----
  const seen = new Set();
  const claim = (list) => { const out = list.filter((t) => !seen.has(t.id)); out.forEach((t) => seen.add(t.id)); return out; };
  const blocked = claim(live.filter((t) => readiness(t) === "red"));
  const overdue = claim(live.filter((t) => t.due && daysUntil(t.due) < 0 && readiness(t) !== "red"));
  const waiting = claim(live.filter((t) => chaseDue(t)));

  // Cross-person dependencies
  const byId = Object.fromEntries(live.map((t) => [t.id, t]));
  const depsRaw = [];
  for (const t of live) {
    for (const ref of (t.prereqs || [])) {
      const pre = byId[ref];
      if (!pre) continue;
      const tO = (t.owners || []).join(), pO = (pre.owners || []).join();
      if (tO && pO && tO !== pO) depsRaw.push({ t, pre });
    }
  }
  const deps = depsRaw.filter(({ t }) => !seen.has(t.id));
  deps.forEach(({ t }) => seen.add(t.id));
  const together = claim(live.filter((t) => t.execution === "together"));
  const attentionN = blocked.length + overdue.length + waiting.length + deps.length + together.length;

  // ---- Section 3: This week per person (by deliverable) ----
  function personFocus(p) {
    const myLive = live.filter((t) => (t.owners || []).includes(p));
    const myActive = myLive.filter((t) =>
      t.status !== "waiting" &&
      (recommendation(t) === "today" || recommendation(t) === "this_week")
    );
    const delivIds = new Set(myActive.map((t) => t.d).filter(Boolean));
    const delivs = [];
    for (const dId of delivIds) {
      const d = byDeliv[dId];
      if (!d) continue;
      const allTasks = TASKS.filter((t) => t.d === dId);
      const doneCount = allTasks.filter((t) => t.status === "done").length;
      const myTasks = myActive.filter((t) => t.d === dId);
      delivs.push({ ...d, total: allTasks.length, done: doneCount, myTasks, wsObj: byWs[d.ws] });
    }
    const standalone = myActive.filter((t) => !t.d);
    return { delivs, standalone };
  }

  function groupByWs(delivs) {
    const map = {};
    delivs.forEach((d) => {
      const name = d.wsObj ? d.wsObj.name : "Other";
      (map[name] = map[name] || []).push(d);
    });
    return Object.entries(map);
  }

  const rd = personFocus("RD"), ff = personFocus("FF");

  async function mtgEditDeliv(d) {
    const name = await showModal("Deliverable name:", [{value: d.name}]);
    if (name === null) return;
    const target = await showModal("Target date (empty = none):", [{type: "date", value: d.target || ""}]);
    if (target === null) return;
    api.saveDeliv(d, { name: name.trim() || d.name, target_date: target.trim() || null });
  }

  // Week number
  const weekNum = Math.ceil((((todayDate - new Date(todayDate.getFullYear(), 0, 1)) / 86400000) + new Date(todayDate.getFullYear(), 0, 1).getDay() + 1) / 7);

  return (
    <div className="wk mtg">
      {/* Meeting header */}
      <div className="mtg-header card">
        <div className="mtg-header-top">
          <div>
            <div className="mtg-title">Weekly Meeting — Week {weekNum}</div>
            <div className="mtg-subtitle">{todayDate.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</div>
          </div>
          <div className="mtg-summary">
            {recentDone.length > 0 && <span className="mtg-stat done"><Icon name="check" size={12} /> {recentDone.length} completed</span>}
            {attentionN > 0 && <span className="mtg-stat attn">{attentionN} need attention</span>}
            {loiDeals.length > 0 && <span className="mtg-stat deals">{loiDeals.length} deal deadline{loiDeals.length !== 1 ? "s" : ""}</span>}
          </div>
        </div>
      </div>

      {/* Deadlines bar */}
      {loiDeals.length > 0 && (
        <div className="loi-bar">
          <div className="loi-label"><Icon name="clock" size={13} /> Upcoming deadlines</div>
          {loiDeals.map((d) => {
            const days = daysUntil(d.target);
            const cls = days <= 7 ? "urgent" : days <= 14 ? "soon" : "";
            return (
              <div key={d.id} className={"loi-item " + cls}>
                <span className="loi-code">{d.deal.codename}</span>
                <span className="loi-ms">{shortName(d)}</span>
                <span className="loi-days">{days}d</span>
                <span className="loi-date">{fdateShort(d.target)}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Section 1: This week's focus per person — editable */}
      <div className="mtg-sec-label"><Icon name="week" size={14} /> This week's focus</div>
      <div className="wk-cols wk-cols-2">
        {[["RD", rd], ["FF", ff]].map(([p, data]) => {
          const groups = groupByWs(data.delivs);
          const taskCount = data.delivs.reduce((n, d) => n + d.myTasks.length, 0) + data.standalone.length;
          return (
            <div key={p} className="card wk-col">
              <div className="wk-h"><Avatar id={p} size={18} /> {PEOPLE[p].name}<span className="wk-n">{taskCount}</span></div>
              {groups.map(([wsName, wsDelivs]) => (
                <React.Fragment key={wsName}>
                  <div className="wk-grp mtg-ws">{wsName}</div>
                  {wsDelivs.map((d) => {
                    const pct = d.total ? Math.round(d.done / d.total * 100) : 0;
                    const daysLeft = d.target ? daysUntil(d.target) : null;
                    const urgent = daysLeft !== null && daysLeft <= 14 && pct < 50;
                    return (
                      <div key={d.id} className="wk-deliv-block">
                        <div className={"wk-deliv-head" + (urgent ? " at-risk" : "")}>
                          <span className="wk-deliv-name tc-click" onClick={() => mtgEditDeliv(d)}>{shortName(d)}</span>
                          <button className="deliv-edit" title="edit deliverable" onClick={() => mtgEditDeliv(d)}>✎</button>
                          <button className="deliv-edit mtg-add-btn" title="add task to this deliverable"
                            onClick={() => window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } }))}>+</button>
                          <span className="wk-deliv-prog">
                            <span className="prog-bar" style={{width:60}}><span style={{ width: pct + "%", background: d.wsObj ? d.wsObj.color : "#94a3b8" }} /></span>
                          </span>
                          {d.target && <span className={"deliv-due" + (daysLeft < 0 ? " over" : daysLeft <= 7 ? " soon" : "")}>{fdate(d.target)}</span>}
                        </div>
                        {d.myTasks.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} />)}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
              {data.standalone.length > 0 && (
                <React.Fragment>
                  <div className="wk-grp mtg-ws">Other</div>
                  {data.standalone.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
                </React.Fragment>
              )}
              {!taskCount && <div className="empty">clear</div>}
            </div>
          );
        })}
      </div>

      {/* Section 2: Blockers & decisions */}
      {attentionN > 0 && (
        <div className="mtg-section mtg-attn-section card">
          <div className="mtg-sec-h attn">
            <Icon name="relations" size={14} />
            <span>Blockers & decisions</span>
            <span className="wk-n">{attentionN}</span>
          </div>
          {blocked.length > 0 && (
            <React.Fragment>
              <div className="wk-grp overdue"><Icon name="relations" size={11} /> Blocked — prerequisite not done</div>
              {blocked.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
            </React.Fragment>
          )}
          {overdue.length > 0 && (
            <React.Fragment>
              <div className="wk-grp overdue"><Icon name="clock" size={11} /> Overdue</div>
              {overdue.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
            </React.Fragment>
          )}
          {waiting.length > 0 && (
            <React.Fragment>
              <div className="wk-grp chase"><Icon name="clock" size={11} /> Chase — ball with others</div>
              {waiting.map((t) => (
                <div key={t.id} className="wkrow chase-row">
                  <button className="chk" data-on={false} onClick={() => api.save(t, { status: "open" })} title="mark resolved" />
                  <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}><span className="wkrow-main">{t.text}</span><span className="wkrow-sub">with {t.waiting.party}</span></div>
                  <button className="mini-btn" onClick={async () => {
                    const next = await showModal("Chased. Next chase date:", [{type: "date", value: addDays(t.waiting.chase || TODAY, 3)}]);
                    if (next) api.save(t, { waiting: { ...t.waiting, chase: next } });
                  }}>chased →</button>
                </div>
              ))}
            </React.Fragment>
          )}
          {deps.length > 0 && (
            <React.Fragment>
              <div className="wk-grp"><Icon name="relations" size={11} /> Cross-person dependencies</div>
              {deps.map(({ t, pre }, i) => (
                <div key={i} className="wkrow tc-click" onClick={() => openTask && openTask(t.id)}>
                  <div className="wkrow-txt">
                    <span className="wkrow-main">{t.text}</span>
                    {readiness(t) === "red" && <span className="tc-blocked">Blocked</span>}
                    <span className="dep-need"><OwnerStack owners={t.owners} size={14} /> waiting on <b>{pre.text}</b> <OwnerStack owners={pre.owners} size={14} /></span>
                  </div>
                </div>
              ))}
            </React.Fragment>
          )}
          {together.length > 0 && (
            <React.Fragment>
              <div className="wk-grp"><Icon name="board" size={11} /> Do together</div>
              {together.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
            </React.Fragment>
          )}
        </div>
      )}

      {/* Section 3: Completed since last meeting */}
      {recentDone.length > 0 && (
        <div className="mtg-section card">
          <div className="mtg-sec-h" style={{cursor:"pointer"}} onClick={() => {
            const el = document.getElementById("mtg-done-body");
            if (el) el.style.display = el.style.display === "none" ? "" : "none";
          }}>
            <Icon name="check" size={14} />
            <span>Completed since last meeting</span>
            <span className="wk-n">{recentDone.length}</span>
            <span style={{marginLeft:"auto",fontSize:11,color:"var(--muted)"}}>click to expand</span>
          </div>
          <div id="mtg-done-body" style={{display:"none"}}>
            <div className="mtg-done-cols">
              {[["RD", rdDone], ["FF", ffDone]].map(([p, items]) => items.length > 0 && (
                <div key={p} className="mtg-done-col">
                  <div className="mtg-done-person"><Avatar id={p} size={16} /> {PEOPLE[p].name}</div>
                  {items.map((t) => (
                    <div key={t.id} className="mtg-done-row tc-click" onClick={() => openTask && openTask(t.id)}>
                      <Icon name="check" size={11} />
                      <span className="mtg-done-txt">{t.text}</span>
                      {dealOf(t) && <span className="mtg-deal sm">{dealOf(t).codename}</span>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
window.MeetingView = MeetingView;

/* ---- DragList: generic reorderable list (HTML5 native, no library) ----
   items       – array of objects with .id
   onReorder   – async fn(reorderedItems) called optimistically then synced
   renderItem  – fn(item, dragHandlers) -> JSX
*/
function DragList({ items, onReorder, renderItem }) {
  const [dragIdx, setDragIdx] = React.useState(null);
  const [overIdx, setOverIdx] = React.useState(null);

  function handleDragStart(e, idx) {
    setDragIdx(idx);
    e.dataTransfer.effectAllowed = "move";
    // ghost image: let browser use the element itself
  }
  function handleDragOver(e, idx) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (idx !== overIdx) setOverIdx(idx);
  }
  function handleDragLeave() {
    // don't clear overIdx here — causes flicker when moving between child elements
  }
  function handleDrop(e, idx) {
    e.preventDefault();
    if (dragIdx === null || dragIdx === idx) {
      setDragIdx(null); setOverIdx(null); return;
    }
    const reordered = [...items];
    const [moved] = reordered.splice(dragIdx, 1);
    reordered.splice(idx, 0, moved);
    setDragIdx(null); setOverIdx(null);
    onReorder(reordered);
  }
  function handleDragEnd() {
    setDragIdx(null); setOverIdx(null);
  }

  return (
    <React.Fragment>
      {items.map((item, idx) => {
        const handlers = {
          draggable: true,
          onDragStart: (e) => handleDragStart(e, idx),
          onDragOver:  (e) => handleDragOver(e, idx),
          onDragLeave: handleDragLeave,
          onDrop:      (e) => handleDrop(e, idx),
          onDragEnd:   handleDragEnd,
          "data-dragging":  dragIdx === idx ? "true" : undefined,
          "data-drag-over": overIdx === idx && dragIdx !== idx ? "true" : undefined,
        };
        return renderItem(item, handlers, idx);
      })}
    </React.Fragment>
  );
}

function WeekRow({ t, mutate, openTask, showWs = true, showDate = true, dragHandlers = null }) {
  const ws = wsOf(t);
  const isOverdue = t.due && daysUntil(t.due) < 0;
  const dateVisible = showDate || isOverdue;
  // Bug 1 fix: optimistic local state so checkmark flips instantly (no waiting for server round-trip)
  const [optimisticDone, setOptimisticDone] = React.useState(null);
  const isDone = optimisticDone !== null ? optimisticDone : t.status === "done";
  async function handleCheck() {
    const newDone = !isDone;
    setOptimisticDone(newDone);
    // api.save always resolves undefined (success and failure both return nothing, 409 throws) — use try/catch
    try {
      await api.save(t, { status: newDone ? "done" : "open", ...(newDone ? { pinned: false } : {}) });
    } catch (_) {
      setOptimisticDone(null); // revert on any error (network, 409 conflict, etc.)
    }
  }
  // Reset optimistic state when server data arrives (t.status changed)
  React.useEffect(() => { setOptimisticDone(null); }, [t.status]);
  const dragging = dragHandlers && dragHandlers["data-dragging"] === "true";
  const dragOver = dragHandlers && dragHandlers["data-drag-over"] === "true";
  const extraClass = (dragging ? " dragging" : "") + (dragOver ? " drag-over" : "");
  return (
    <div className={"wkrow" + (isDone ? " done" : "") + extraClass} {...(dragHandlers || {})}>
      <button className="chk" data-on={isDone} onClick={handleCheck} title="mark done">
        {isDone && <Icon name="check" size={12} />}
      </button>
      <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}>
        <span className="wkrow-main">{t.text}</span>
        {readiness(t) === "red" && <span className="tc-blocked">Blocked</span>}
        {showWs && ws && <span className="wkrow-sub">{ws.name}</span>}
      </div>
      {t.inputFrom && !isDone && (
        <span className="input-needed-badge" title={t.inputQuestion || "Input needed"}>
          Waiting: {PEOPLE[t.inputFrom] ? PEOPLE[t.inputFrom].name : t.inputFrom}
        </span>
      )}
      {t.status === "waiting" ? <WaitingChip t={t} /> : (dateVisible && <DueChip t={t} />)}
    </div>
  );
}

/* ---- AgentQueue: 1-2 suggested agent tasks for My Week ---- */
function AgentQueue({ openTask }) {
  const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };
  const candidates = TASKS
    .filter((t) =>
      t.execution === "agent" &&
      t.status !== "done" &&
      readiness(t) !== "red"
    )
    .sort((a, b) => {
      const pa = PRIORITY_ORDER[a.priority] ?? 1;
      const pb = PRIORITY_ORDER[b.priority] ?? 1;
      if (pa !== pb) return pa - pb;
      if (a.due && b.due) return a.due.localeCompare(b.due);
      if (a.due) return -1;
      if (b.due) return 1;
      return 0;
    })
    .slice(0, 2);

  if (!candidates.length) return null;

  return (
    <div className="card" style={{marginTop:12}}>
      <div className="wk-h">
        <Icon name="bolt" size={14} /> Agent Queue<span className="wk-n">{candidates.length}</span>
      </div>
      {candidates.map((t) => {
        const ws = wsOf(t);
        const du = t.due ? daysUntil(t.due) : null;
        return (
          <div key={t.id} className="wkrow tc-click" onClick={() => openTask && openTask(t.id)}>
            <span className="rdot" data-level={readiness(t)} style={{width:8,height:8}} />
            <div className="wkrow-txt">
              <span className="wkrow-main">{t.text}</span>
              {ws && <span className="wkrow-sub">{ws.name}</span>}
            </div>
            {t.due && <DueChip t={t} />}
          </div>
        );
      })}
    </div>
  );
}

function WeekView({ person, mutate, openTask, embedded }) {

  const live = TASKS.filter((t) => t.status !== "done");
  const mine = live.filter((t) => (t.owners || []).includes(person));

  const [pinnedLocal, setPinnedLocal] = React.useState(null);
  const [dueTodayLocal, setDueTodayLocal] = React.useState(null);
  const [upNextLocal, setUpNextLocal] = React.useState(null);

  const pinnedBase = mine.filter((t) => t.pinned && t.status !== "waiting");
  // Bug 3 fix: no separate Overdue section — overdue tasks roll into Due Today (red badge signals them)
  const dueTodayBase = mine.filter((t) => t.status !== "waiting" && !t.pinned && t.due && daysUntil(t.due) <= 0)
    .sort((a, b) => a.due.localeCompare(b.due));
  const upNextBase = mine.filter((t) => t.status !== "waiting" && !t.pinned && t.due && daysUntil(t.due) === 1);

  // Reset local order when server data changes (new tasks, status changes)
  React.useEffect(() => { setPinnedLocal(null); }, [pinnedBase.map((t) => t.id).join()]);
  React.useEffect(() => { setDueTodayLocal(null); }, [dueTodayBase.map((t) => t.id).join()]);
  React.useEffect(() => { setUpNextLocal(null); }, [upNextBase.map((t) => t.id).join()]);

  const pinned = pinnedLocal || pinnedBase;
  const dueToday = dueTodayLocal || dueTodayBase;
  const upNext = upNextLocal || upNextBase;
  const todayN = pinned.length + dueToday.length;

  async function persistReorder(items) {
    await api.reorder(items.map((t) => t.id));
  }

  const dayLabel = todayDate.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

  const weekDelivs = DELIVERABLES
    .filter((d) => d.target && daysUntil(d.target) <= 10 && TASKS.some((t) => t.d === d.id && t.status !== "done"))
    .map((d) => ({ ...d, s: delivStats(d), ws: byWs[d.ws] }))
    .sort((a, b) => a.target.localeCompare(b.target));

  const byId = Object.fromEntries(live.map((t) => [t.id, t]));
  const deps = [];
  for (const t of live) {
    for (const ref of (t.prereqs || [])) {
      const pre = byId[ref];
      if (!pre) continue;
      const tO = (t.owners || []).join(), pO = (pre.owners || []).join();
      if (tO && pO && tO !== pO) deps.push({ t, pre });
    }
  }
  const together = live.filter((t) => t.execution === "together");
  const sharedN = deps.length + together.length;
  const [sharedOpen, setSharedOpen] = React.useState(false);
  const [delivOpen, setDelivOpen] = React.useState({});

  return (
    <div className="wk">
      <div className="wk-cols wk-cols-2">
        <div className="card wk-col">
          <div className="wk-h">Due Today <span style={{fontWeight:400,fontSize:12,color:"var(--muted)",marginLeft:2}}>{dayLabel}</span><span className="wk-n">{todayN}</span></div>

          {pinned.length > 0 && <div className="wk-grp"><Icon name="pin" size={11} /> Pinned</div>}
          <DragList items={pinned} onReorder={(items) => { setPinnedLocal(items); persistReorder(items); }}
            renderItem={(t, h) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showDate={false} dragHandlers={h} />} />

          {dueToday.length > 0 && <div className="wk-grp">Due today</div>}
          <DragList items={dueToday} onReorder={(items) => { setDueTodayLocal(items); persistReorder(items); }}
            renderItem={(t, h) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showDate={false} dragHandlers={h} />} />

          {!todayN && <div className="empty">clear — nothing due today</div>}
        </div>

        <div className="card wk-col">
          <div className="wk-h">Tomorrow<span className="wk-n">{upNext.length}</span></div>

          <DragList items={upNext} onReorder={(items) => { setUpNextLocal(items); persistReorder(items); }}
            renderItem={(t, h) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showDate={false} dragHandlers={h} />} />

          {!upNext.length && <div className="empty">nothing due tomorrow</div>}
        </div>
      </div>

      <div className="card" style={{marginTop:12}}>
          <div className="wk-h">Deliverables Due Next 10 Days<span className="wk-n">{weekDelivs.length}</span></div>

          {weekDelivs.map((d) => {
            const du = daysUntil(d.target);
            const isOpen = !!delivOpen[d.id];
            const openTasks = TASKS.filter((t) => t.d === d.id && t.status !== "done");
            return (
              <div key={d.id} className="wk-deliv-block">
                <div className="wk-deliv-head" style={{cursor:"pointer"}} onClick={() => setDelivOpen((o) => ({...o, [d.id]: !isOpen}))}>
                  <span className={"caret" + (isOpen ? " open" : "")}><Icon name="chevron" size={12} /></span>
                  <span className="wk-deliv-name">{d.name}</span>
                  <span className="wk-deliv-prog">
                    <span className="prog-bar" style={{width:50}}><span style={{ width: (d.s.total ? d.s.done / d.s.total * 100 : 0) + "%", background: d.ws ? d.ws.color : "var(--brand)" }} /></span>
                  </span>
                  <span className={"deliv-due" + (du < 0 ? " over" : du <= 7 ? " soon" : "")}>{fdate(d.target)}</span>
                </div>
                {isOpen && (
                  <div style={{marginTop:4}}>
                    <DragList items={openTasks} onReorder={(items) => persistReorder(items)}
                      renderItem={(t, h) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} dragHandlers={h} />} />
                    {!openTasks.length && <div className="empty">all tasks done</div>}
                    <div style={{display:"flex",gap:6,marginTop:4}}>
                      <button className="btn ghost" style={{fontSize:11,padding:"2px 8px"}}
                        onClick={() => window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } }))}>
                        <Icon name="plus" size={11} /> add task
                      </button>
                      <button className="btn ghost" style={{fontSize:11,padding:"2px 8px"}}
                        onClick={() => editDeliv(d)}>
                        ✎ edit deliverable
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {!weekDelivs.length && <div className="empty">no deliverable deadlines next 10 days</div>}
      </div>

      <AgentQueue openTask={openTask} />

      {sharedN > 0 && (
        <div className="wk-shared-section">
          <button className="wk-shared-toggle" onClick={() => setSharedOpen(!sharedOpen)}>
            <span className={"caret" + (sharedOpen ? " open" : "")}><Icon name="chevron" size={13} /></span>
            <span>Shared blockers</span>
            <span className="wk-n">{sharedN}</span>
          </button>
          {sharedOpen && (
            <div className="wk-shared-body">
              {deps.length > 0 && deps.map(({ t, pre }, i) => (
                <div key={i} className="dep-row tc-click" onClick={() => openTask && openTask(t.id)}>
                  <span className="rdot" data-level={readiness(t)} style={{ width: 9, height: 9 }} />
                  <div className="dep-txt">
                    <span className="wkrow-main">{t.text}</span>
                    <span className="dep-need">waiting on <b>{pre.text}</b> <Avatar id={(pre.owners || [])[0]} size={16} /></span>
                  </div>
                </div>
              ))}
              {together.length > 0 && (
                <React.Fragment>
                  <div className="wk-grp">Together</div>
                  {together.map((t) => (
                    <div key={t.id} className="wkrow">
                      <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}>
                        <span className="wkrow-main">{t.text}</span>
                        {readiness(t) === "red" && <span className="tc-blocked">Blocked</span>}
                        <span className="wkrow-sub">{(wsOf(t) || {}).name}</span>
                      </div>
                      <OwnerStack owners={t.owners} size={18} />
                    </div>
                  ))}
                </React.Fragment>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* addDays lives in components.jsx (single bundle scope — no redeclaration) */
window.WeekView = WeekView;
