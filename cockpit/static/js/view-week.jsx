/* ===== My Week — computed daily/weekly recommendation + shared lane ===== */

/* --- Weekly Meeting prep view — agenda-structured, both people, decision-first --- */
function MeetingView({ mutate, openTask }) {
  const [mode, setMode] = React.useState("daily");
  const readOnly = !(window.COCKPIT && (window.COCKPIT.isAdmin || (window.COCKPIT.perms && window.COCKPIT.perms.workstreams === "rw")));
  const live = TASKS.filter((t) => t.status !== "done" && t.execution !== "agent");
  /* One column per person, me first — the meeting agenda covers everyone in the
     viewer's scope (server already filters workstreams by team visibility). */
  const MTG_PEOPLE = meFirst(Object.keys(PEOPLE));
  const mtgColsCls = "wk-cols wk-cols-" + Math.min(MTG_PEOPLE.length, 3);

  // Deadlines — next upcoming milestone per active deal
  const activeStages = new Set(["loi_signed", "dd", "indicative_offer", "valuation_rfi"]);
  const hasOpenWork = (d) => TASKS.some((t) => t.d === d.id && t.status !== "done" && t.execution !== "agent");
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
  const lastMonISO = localISO(lastMon); // NOT toISOString — UTC shift breaks local dates east of UTC
  const recentDone = TASKS.filter((t) => t.status === "done" && t.execution !== "agent" && t.doneAt && t.doneAt >= lastMonISO)
    .sort((a, b) => (b.doneAt || "").localeCompare(a.doneAt || ""));
  const doneBy = {};
  MTG_PEOPLE.forEach((p) => { doneBy[p] = recentDone.filter((t) => (t.owners || []).includes(p)); });

  // ---- Section 2: Decisions & waiting — only what needs a person to act (issue 30) ----
  // Roman's rule: show Decisions needed + Waiting on external ONLY. NOT plain overdue,
  // NOT tasks blocked by the other person / a prerequisite (that's just sequencing).
  const seen = new Set();
  const claim = (list) => { const out = list.filter((t) => !seen.has(t.id)); out.forEach((t) => seen.add(t.id)); return out; };
  // Decisions needed: ONLY a real decision (approval gate) or a task explicitly requesting someone's input.
  // NOT execution==="together" — that's just collaborative work and dumped the whole todo list here.
  const decisions = claim(live.filter((t) => t.inputFrom || t.kind === "approval").sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; }));
  // Waiting on external: the ball is with a counterparty / advisor / investor
  const waiting = claim(live.filter((t) => t.status === "waiting").sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; }));
  const attentionN = decisions.length + waiting.length;

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
      const myTasks = myActive.filter((t) => t.d === dId).sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; });
      // Issue 27: in the weekly view only surface deliverables that have a subtask due within the coming 7 days
      if (!myTasks.some((t) => t.due && daysUntil(t.due) <= 7)) continue;
      const allTasks = TASKS.filter((t) => t.d === dId);
      const doneCount = allTasks.filter((t) => t.status === "done").length;
      delivs.push({ ...d, total: allTasks.length, done: doneCount, myTasks, wsObj: byWs[d.ws] });
    }
    const standalone = myActive.filter((t) => !t.d).sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; });
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

  const focusBy = {};
  MTG_PEOPLE.forEach((p) => { focusBy[p] = personFocus(p); });

  // Daily mode data
  const dueTodayBy = {};
  MTG_PEOPLE.forEach((p) => {
    dueTodayBy[p] = live.filter((t) => (t.owners || []).includes(p) && t.due && daysUntil(t.due) <= 0 && t.status !== "waiting").sort((a, b) => a.due.localeCompare(b.due));
  });
  const delivsDueToday = DELIVERABLES
    .filter((d) => d.target && daysUntil(d.target) <= 0 && TASKS.some((t) => t.d === d.id && t.status !== "done" && t.execution !== "agent"))
    .map((d) => ({ ...d, s: delivStats(d), wsObj: byWs[d.ws] }))
    .sort((a, b) => a.target.localeCompare(b.target));

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
      {/* Consistent slim toolbar — title comes from the global topbar, matching Workstreams/Timeline */}
      <div className="ws-toolbar">
        <div className="seg">
          <button className={mode === "daily" ? "on" : ""} onClick={() => setMode("daily")}>Daily</button>
          <button className={mode === "weekly" ? "on" : ""} onClick={() => setMode("weekly")}>Weekly</button>
        </div>
        <div className="ws-toolbar-sp" />
        <span className="ws-toolbar-note">{mode === "weekly" ? "Week " + weekNum + " · " : ""}{todayDate.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}</span>
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

      {/* DAILY: Due Today per person + deliverables due today */}
      {mode === "daily" && (
        <React.Fragment>
          <div className="mtg-sec-label"><Icon name="week" size={14} /> Due Today</div>
          <div className={mtgColsCls}>
            {MTG_PEOPLE.map((p) => [p, dueTodayBy[p]]).map(([p, tasks]) => (
              <div key={p} className="card wk-col">
                <div className="wk-h"><Avatar id={p} size={18} /> {PEOPLE[p].name}<span className="wk-n">{tasks.length}</span></div>
                {tasks.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
                {!tasks.length && <div className="empty">clear — nothing due</div>}
              </div>
            ))}
          </div>
          {delivsDueToday.length > 0 && (
            <div className="card" style={{marginTop:12}}>
              <div className="wk-h">Deliverables Due Today<span className="wk-n">{delivsDueToday.length}</span></div>
              {delivsDueToday.map((d) => {
                const pct = d.s.total ? Math.round(d.s.done / d.s.total * 100) : 0;
                return (
                  <div key={d.id} className="wk-deliv-block">
                    <div className="wk-deliv-head">
                      <span className="wk-deliv-name">{d.name}</span>
                      <span className="wk-deliv-prog">
                        <span className="prog-bar" style={{width:60}}><span style={{ width: pct + "%", background: d.wsObj ? d.wsObj.color : "#94a3b8" }} /></span>
                      </span>
                      <span className="deliv-due over">{fdate(d.target)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </React.Fragment>
      )}

      {/* WEEKLY: This week's focus per person — editable */}
      {mode === "weekly" && (
        <React.Fragment>
          <div className="mtg-sec-label"><Icon name="week" size={14} /> This week's focus</div>
          <div className={mtgColsCls}>
            {MTG_PEOPLE.map((p) => [p, focusBy[p]]).map(([p, data]) => {
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
                              {d.displayNum && <span className="num-prefix">{d.displayNum}</span>}
                              <span className="wk-deliv-name tc-click" onClick={() => mtgEditDeliv(d)}>{shortName(d)}</span>
                              <button className="rep-act rep-act--edit" title="edit deliverable" onClick={(e) => { e.stopPropagation(); mtgEditDeliv(d); }} />
                              {!readOnly && <button className="rep-act rep-act--add" title="add task to this deliverable"
                                onClick={(e) => { e.stopPropagation(); window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } })); }} />}
                              <span className="deliv-sp" />
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
        </React.Fragment>
      )}

      {/* Section 2: Decisions & waiting — only what needs a person to act */}
      {attentionN > 0 && (
        <div className="mtg-section mtg-attn-section card">
          <div className="mtg-sec-h attn">
            <Icon name="relations" size={14} />
            <span>Decisions &amp; waiting</span>
            <span className="wk-n">{attentionN}</span>
          </div>
          {decisions.length > 0 && (
            <React.Fragment>
              <div className="wk-grp"><Icon name="relations" size={11} /> Decisions needed</div>
              {decisions.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
            </React.Fragment>
          )}
          {waiting.length > 0 && (
            <React.Fragment>
              <div className="wk-grp chase"><Icon name="clock" size={11} /> Waiting on external</div>
              {waiting.map((t) => (
                <div key={t.id} className="wkrow chase-row">
                  <button className="chk" data-on={false} onClick={() => api.save(t, { status: "open" })} title="mark resolved" />
                  <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}><span className="wkrow-main">{t.text}</span><span className="wkrow-sub">with {(t.waiting && t.waiting.party) || "—"}</span></div>
                  <button className="mini-btn" onClick={async () => {
                    const next = await showModal("Chased. Next chase date:", [{type: "date", value: addDays((t.waiting && t.waiting.chase) || TODAY, 3)}]);
                    if (next) api.save(t, { waiting: { ...(t.waiting || {}), chase: next } });
                  }}>chased →</button>
                </div>
              ))}
            </React.Fragment>
          )}
        </div>
      )}

      {/* Section 3: Completed since last meeting (weekly only) */}
      {mode === "weekly" && recentDone.length > 0 && (
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
              {MTG_PEOPLE.map((p) => [p, doneBy[p]]).map(([p, items]) => items.length > 0 && (
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
  // optimistic due so +1d updates the row instantly; bumpRef guards against double-bump while the save+refetch settles
  const [optimisticDue, setOptimisticDue] = React.useState(null);
  const effDue = optimisticDue !== null ? optimisticDue : t.due;
  const dueTask = optimisticDue !== null ? { ...t, due: optimisticDue } : t;
  const bumpRef = React.useRef(false);
  const isOverdue = effDue && daysUntil(effDue) < 0;
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
  // Clear the optimistic due once the server round-trip lands the new value
  React.useEffect(() => { setOptimisticDue(null); }, [t.due]);
  async function bumpTomorrow(e) {
    e.stopPropagation();
    if (bumpRef.current) return;
    bumpRef.current = true;
    const next = addDays(effDue, 1);
    setOptimisticDue(next);
    try {
      const ok = await api.bumpDue(t, next);
      if (ok === false) setOptimisticDue(null);
    } catch (_) { setOptimisticDue(null); }
    finally { bumpRef.current = false; }
  }
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
        {(() => {
          // Issue 26: flag a task whose due date falls after its deliverable's target date
          const dv = t.d ? byDeliv[t.d] : null;
          return dv && dv.target && t.due && t.due > dv.target
            ? <span className="tc-blocked" style={{ background: "#fffbeb", color: "#b45309", borderColor: "#fde68a" }}
                title={"Due " + fdate(t.due) + " — after deliverable target " + fdate(dv.target)}>⚠ after target</span>
            : null;
        })()}
        {showWs && ws && <span className="wkrow-sub">{ws.name}</span>}
      </div>
      {t.inputFrom && !isDone && (
        <span className="input-needed-badge" title={t.inputQuestion || "Input needed"}>
          Waiting: {PEOPLE[t.inputFrom] ? PEOPLE[t.inputFrom].name : t.inputFrom}
        </span>
      )}
      {!isDone && effDue && t.status !== "waiting" && (
        <button className="bump-btn" title="Move due date to tomorrow"
          onClick={bumpTomorrow}>+1d</button>
      )}
      {t.status === "waiting" ? <WaitingChip t={t} /> : (dateVisible && <DueChip t={dueTask} />)}
    </div>
  );
}

/* ---- AgentQueue: agent tasks waiting on the viewer — in_review or blocked with a question.
   TASKS is already scoped server-side: non-admins only ever receive their own
   agent workflows here. Hidden entirely without the agents module. ---- */
function AgentQueue({ openTask }) {
  const hasAgents = window.COCKPIT && (window.COCKPIT.modules || []).includes("agents");
  const needsMe = TASKS
    .filter((t) =>
      t.execution === "agent" &&
      (t.status === "in_review" || t.statusRaw === "blocked")
    )
    .slice(0, 5);

  if (!hasAgents || !needsMe.length) return null;

  return (
    <div className="card" style={{marginTop:12}}>
      <div className="wk-h">
        <Icon name="bolt" size={14} /> Agents — waiting on you<span className="wk-n">{needsMe.length}</span>
      </div>
      {needsMe.map((t) => {
        const isBlocked = t.statusRaw === "blocked";
        return (
          <div key={t.id} className="wkrow tc-click" onClick={() => openTask && openTask(t.id)}>
            <span className="rdot" data-level={isBlocked ? "amber" : "red"} style={{width:8,height:8}} />
            <div className="wkrow-txt">
              <span className="wkrow-main">{t.text}</span>
              <span className="wkrow-sub">{isBlocked ? "Waiting on your answer" : "Needs review"}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function WeekView({ person, mutate, openTask, embedded }) {
  const readOnly = !(window.COCKPIT && (window.COCKPIT.isAdmin || (window.COCKPIT.perms && window.COCKPIT.perms.workstreams === "rw")));
  const live = TASKS.filter((t) => t.status !== "done" && t.execution !== "agent");
  const mine = live.filter((t) => (t.owners || []).includes(person));

  const [pinnedLocal, setPinnedLocal] = React.useState(null);
  const [dueTodayLocal, setDueTodayLocal] = React.useState(null);
  const [upNextLocal, setUpNextLocal] = React.useState(null);

  const pinnedBase = mine.filter((t) => t.pinned && t.status !== "waiting").sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; });
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
    .filter((d) => d.target && daysUntil(d.target) <= 10 && TASKS.some((t) => t.d === d.id && t.status !== "done" && t.execution !== "agent"))
    .map((d) => ({ ...d, s: delivStats(d), ws: byWs[d.ws] }))
    .sort((a, b) => a.target.localeCompare(b.target));

  // Decisions & waiting (issue 30): decisions needed + items waiting on someone external.
  // NOT tasks blocked by the other person / a prerequisite — that's just sequencing.
  // ONLY a real decision (approval gate) or a task explicitly requesting input — NOT execution==="together".
  const decisions = live.filter((t) => t.inputFrom || t.kind === "approval").sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; });
  const waitingShared = live.filter((t) => t.status === "waiting" && !decisions.includes(t)).sort((a, b) => { if (a.due && b.due) return a.due.localeCompare(b.due); if (a.due) return -1; if (b.due) return 1; return 0; }); // dedup: a task shows under one group only
  const sharedN = decisions.length + waitingShared.length;
  // Switchable right column (Roman's request): only ever 2 boxes side by side — Due Today | one of Tomorrow/Personal/Blocked
  const personalOpen = (typeof PERSONAL !== "undefined" ? PERSONAL : []).filter((t) => t.status !== "done");
  const [rightTab, setRightTab] = React.useState("tomorrow");
  const [delivOpen, setDelivOpen] = React.useState({});
  const [calBadge, setCalBadge] = React.useState(0);
  const [calAgenda, setCalAgenda] = React.useState(null);
  const calFetched = React.useRef(false);
  React.useEffect(() => {
    if (rightTab !== "calendar" || calFetched.current) return;
    calFetched.current = true;
    var today = localISO(todayDate);
    api.calendarEvents("team", today, 2)
      .then(function(d) {
        if (d && d.events) {
          // keep only the two days the agenda groups render — badge must match the list;
          // all-day spans count on every covered day (Graph end date is exclusive)
          var tomorrow = addDays(today, 1);
          var covers = function(e, day) {
            var s = (e.start || "").slice(0, 10);
            if (!e.all_day) return s === day;
            var en = (e.end || "").slice(0, 10);
            return en > s ? (day >= s && day < en) : day === s;
          };
          var evs = d.events.filter(function(e) { return covers(e, today) || covers(e, tomorrow); });
          setCalBadge(evs.length);
          setCalAgenda(evs);
        }
      })
      .catch(function() { calFetched.current = false; }); // retry on next tab visit instead of loading forever
  }, [rightTab]);

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
          <div className="wk-h wk-h--seg">
            <div className="seg wk-rseg">
              {[["tomorrow", "Tomorrow", upNext.length], ["personal", "Personal", personalOpen.length], ["blocked", "Blocked", sharedN], ["calendar", "Calendar", calBadge]].map((opt) => (
                <button key={opt[0]} className={rightTab === opt[0] ? "on" : ""} onClick={() => setRightTab(opt[0])}>
                  {opt[1]}{opt[2] > 0 && <span className="wk-n">{opt[2]}</span>}
                </button>
              ))}
            </div>
          </div>

          {rightTab === "tomorrow" && (
            <React.Fragment>
              <DragList items={upNext} onReorder={(items) => { setUpNextLocal(items); persistReorder(items); }}
                renderItem={(t, h) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showDate={false} dragHandlers={h} />} />
              {!upNext.length && <div className="empty">nothing due tomorrow</div>}
            </React.Fragment>
          )}

          {rightTab === "personal" && <PersonalTodos bare mutate={mutate} openTask={openTask} />}

          {rightTab === "blocked" && (
            <React.Fragment>
              {decisions.length > 0 && <div className="wk-grp">Decisions needed</div>}
              {decisions.map((t) => (
                <div key={t.id} className="wkrow">
                  <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}>
                    <span className="wkrow-main">{t.text}</span>
                    {t.inputFrom && <span className="wkrow-sub">input from {PEOPLE[t.inputFrom] ? PEOPLE[t.inputFrom].name : t.inputFrom}</span>}
                  </div>
                  <OwnerStack owners={t.owners} size={18} />
                </div>
              ))}
              {waitingShared.length > 0 && <div className="wk-grp">Waiting on external</div>}
              {waitingShared.map((t) => (
                <div key={t.id} className="wkrow">
                  <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}>
                    <span className="wkrow-main">{t.text}</span>
                    <span className="wkrow-sub">with {(t.waiting && t.waiting.party) || "—"}</span>
                  </div>
                  <OwnerStack owners={t.owners} size={18} />
                </div>
              ))}
              {!sharedN && <div className="empty">nothing blocked — no decisions or waits</div>}
            </React.Fragment>
          )}

          {rightTab === "calendar" && (
            <React.Fragment>
              {!calAgenda && <div className="empty">Loading…</div>}
              {calAgenda && calAgenda.length === 0 && <div className="empty">No meetings today or tomorrow</div>}
              {calAgenda && (() => {
                var today = localISO(todayDate);
                var tomorrow = addDays(today, 1);
                var groups = [[today, "Today"], [tomorrow, "Tomorrow"]];
                return groups.map(function(g) {
                  var evs = calAgenda.filter(function(e) { return (e.start || "").startsWith(g[0]); });
                  if (!evs.length) return null;
                  return (
                    <React.Fragment key={g[0]}>
                      <div className="wk-grp">{g[1]}</div>
                      {evs.map(function(ev, i) {
                        var time = (ev.start || "").match(/T(\d{2}:\d{2})/);
                        return (
                          <div key={i} className="wkrow cal-agenda-row">
                            <span className="cal-agenda-time">{time ? time[1] : "—"}</span>
                            <span className="wkrow-main" style={{flex:1}}>{ev.subject}</span>
                            {ev.user && <span className="avatar" style={{width:18,height:18,fontSize:7.5,background:"#0891B2",flexShrink:0}}>{ev.user.initials}</span>}
                          </div>
                        );
                      })}
                    </React.Fragment>
                  );
                });
              })()}
            </React.Fragment>
          )}
        </div>
      </div>

      <div className="card" style={{marginTop:12}}>
          <div className="wk-h">Deliverables Due Next 10 Days<span className="wk-n">{weekDelivs.length}</span></div>

          {weekDelivs.map((d) => {
            const du = daysUntil(d.target);
            const isOpen = !!delivOpen[d.id];
            const openTasks = TASKS.filter((t) => t.d === d.id && t.status !== "done" && t.execution !== "agent");
            return (
              <div key={d.id} className="wk-deliv-block">
                <div className="wk-deliv-head" style={{cursor:"pointer"}} onClick={() => setDelivOpen((o) => ({...o, [d.id]: !isOpen}))}>
                  <span className={"caret" + (isOpen ? " open" : "")}><Icon name="chevron" size={12} /></span>
                  <span className="wk-deliv-name">{d.name}</span>
                  <button className="rep-act rep-act--edit" title="edit deliverable"
                    onClick={(e) => { e.stopPropagation(); editDeliv(d); }} />
                  {!readOnly && <button className="rep-act rep-act--add" title="add task to this deliverable"
                    onClick={(e) => { e.stopPropagation(); window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } })); }} />}
                  <span className="deliv-sp" />
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
                  </div>
                )}
              </div>
            );
          })}

          {!weekDelivs.length && <div className="empty">no deliverable deadlines next 10 days</div>}
      </div>

      <AgentQueue openTask={openTask} />
    </div>
  );
}

/* addDays lives in components.jsx (single bundle scope — no redeclaration) */
window.WeekView = WeekView;
