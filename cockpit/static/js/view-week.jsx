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
                          {d.deal && <DealChip deal={d.deal} small />}
                          <span className="wk-deliv-name tc-click" onClick={() => mtgEditDeliv(d)}>{shortName(d)}</span>
                          <button className="deliv-edit" title="edit deliverable" onClick={() => mtgEditDeliv(d)}>✎</button>
                          <button className="deliv-edit mtg-add-btn" title="add task to this deliverable"
                            onClick={() => window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } }))}>+</button>
                          <span className="wk-deliv-prog">
                            <span className="prog-bar" style={{width:60}}><span style={{ width: pct + "%", background: d.wsObj ? d.wsObj.color : "#94a3b8" }} /></span>
                            <span style={{fontSize:11,color:"#64748b"}}>{d.done}/{d.total}</span>
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
                  <span className="rdot" data-level="grey" style={{ width: 9, height: 9 }} />
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
                  <ReadinessDot t={t} />
                  <div className="wkrow-txt">
                    <span className="wkrow-main">{t.text}</span>
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

function WeekRow({ t, mutate, openTask, showWs = true }) {
  const ws = wsOf(t), dl = delivOf(t);
  return (
    <div className={"wkrow" + (t.status === "done" ? " done" : "")}>
      <button className="chk" data-on={t.status === "done"} onClick={() => api.save(t, { status: t.status === "done" ? "open" : "done", ...(t.status !== "done" ? { pinned: false } : {}) })} title="mark done">
        {t.status === "done" && <Icon name="check" size={12} />}
      </button>
      {t.status === "waiting" ? <span className="rdot" data-level="grey" style={{ width: 9, height: 9 }} /> : <ReadinessDot t={t} />}
      <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}>
        <span className="wkrow-main">{t.text}</span>
        {showWs && <span className="wkrow-sub">{ws ? ws.name : ""}{dl ? " › " + dl.name : ""}{dealOf(t) ? " · " + dealOf(t).codename : ""}</span>}
      </div>
      {t.status === "waiting" ? <WaitingChip t={t} /> : <DueChip t={t} />}
    </div>
  );
}

function WeekView({ person, mutate, openTask, meetingMode }) {
  if (meetingMode) return <MeetingView mutate={mutate} openTask={openTask} />;

  const live = TASKS.filter((t) => t.status !== "done");
  const mine = live.filter((t) => (t.owners || []).includes(person));

  const pinned = mine.filter((t) => t.pinned && t.status !== "waiting");
  const overdue = mine.filter((t) => t.status !== "waiting" && !t.pinned && t.due && daysUntil(t.due) < 0)
    .sort((a, b) => a.due.localeCompare(b.due));
  const today = mine.filter((t) => t.status !== "waiting" && !t.pinned && !(t.due && daysUntil(t.due) < 0) && recommendation(t) === "today");
  const chase = mine.filter((t) => chaseDue(t))
    .sort((a, b) => ((a.waiting && a.waiting.chase) || "9999").localeCompare((b.waiting && b.waiting.chase) || "9999"));
  const week = mine.filter((t) => t.status !== "waiting" && recommendation(t) === "this_week");

  // shared lane
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

  const done = TASKS.filter((t) => (t.owners || []).includes(person) && t.status === "done");
  const [doneOpen, setDoneOpen] = React.useState(false);

  const todayN = pinned.length + overdue.length + today.length;
  const dayLabel = todayDate.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

  return (
    <div className="wk">
      <div className="wk-cols wk-cols-2">
        <div className="card wk-col">
          <div className="wk-h">Today <span style={{fontWeight:400,fontSize:12,color:"var(--muted)",marginLeft:2}}>{dayLabel}</span><span className="wk-n">{todayN}</span></div>
          {overdue.length > 0 && <div className="wk-grp overdue"><Icon name="clock" size={11} /> Overdue</div>}
          {overdue.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
          {pinned.length > 0 && <div className="wk-grp"><Icon name="pin" size={11} /> Pinned</div>}
          {pinned.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
          {today.length > 0 && (overdue.length > 0 || pinned.length > 0) && <div className="wk-grp">Up next</div>}
          {today.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
          {!pinned.length && !overdue.length && !today.length && <div className="empty">clear — nothing due today</div>}
          {chase.length > 0 && <div className="wk-grp chase"><Icon name="clock" size={11} /> Chase</div>}
          {chase.map((t) => (
            <div key={t.id} className="wkrow chase-row">
              <span className="rdot" data-level="grey" style={{ width: 9, height: 9 }} />
              <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}><span className="wkrow-main">{t.text}</span><span className="wkrow-sub">with {t.waiting.party}</span></div>
              <button className="mini-btn" onClick={async () => {
                const next = await showModal("Chased. Next chase date:", [{type: "date", value: addDays(t.waiting.chase || TODAY, 3)}]);
                if (next) api.save(t, { waiting: { ...t.waiting, chase: next } });
              }}>chased →</button>
            </div>
          ))}
        </div>

        <div className="card wk-col wk-focus">
          <div className="wk-h">This week<span className="wk-n">{week.length}</span>
            <button className="mini-btn" style={{marginLeft:"auto"}} onClick={() => {
              window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { type: "deliverable" } }));
            }}>+ deliverable</button>
          </div>
          {(() => {
            const myActive = mine.filter((t) => t.status !== "waiting" && (recommendation(t) === "today" || recommendation(t) === "this_week"));
            const delivIds = new Set(myActive.map((t) => t.d).filter(Boolean));
            const focusDelivs = [];
            for (const dId of delivIds) {
              const d = byDeliv[dId];
              if (!d) continue;
              const allT = TASKS.filter((t) => t.d === dId);
              const doneN = allT.filter((t) => t.status === "done").length;
              const myT = myActive.filter((t) => t.d === dId);
              focusDelivs.push({ ...d, total: allT.length, done: doneN, myTasks: myT, wsObj: byWs[d.ws] });
            }
            const standalone = myActive.filter((t) => !t.d);
            const wsGroups = {};
            focusDelivs.forEach((d) => {
              const name = d.wsObj ? d.wsObj.name : "Other";
              (wsGroups[name] = wsGroups[name] || []).push(d);
            });
            const groups = Object.entries(wsGroups);
            return (
              <React.Fragment>
                {groups.map(([wsName, wsDelivs]) => (
                  <React.Fragment key={wsName}>
                    <div className="wk-grp wk-ws-grp">{wsName}</div>
                    {wsDelivs.map((d) => {
                      const pct = d.total ? Math.round(d.done / d.total * 100) : 0;
                      const du = d.target ? daysUntil(d.target) : null;
                      return (
                        <div key={d.id} className="wk-deliv-block">
                          <div className="wk-deliv-head">
                            <span className="wk-deliv-name">{d.name}</span>
                            <button className="deliv-edit" title="rename / set target"
                              onClick={() => editDeliv(d)}>✎</button>
                            {d.deal && <DealChip deal={d.deal} small />}
                            <span className="wk-deliv-prog">
                              <span className="prog-bar" style={{width:60}}><span style={{ width: pct + "%", background: d.wsObj ? d.wsObj.color : "#94a3b8" }} /></span>
                              <span style={{fontSize:11,color:"#64748b"}}>{d.done}/{d.total}</span>
                            </span>
                            {d.target && <span className={"deliv-due" + (du < 0 ? " over" : du <= 7 ? " soon" : "")} style={{fontSize:11}}>{fdate(d.target)}</span>}
                          </div>
                          {d.myTasks.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} showWs={false} />)}
                          <button className="wk-add-task" onClick={() => {
                            window.dispatchEvent(new CustomEvent("cockpit:quickadd", { detail: { d: d.id } }));
                          }}>+ add task</button>
                        </div>
                      );
                    })}
                  </React.Fragment>
                ))}
                {standalone.length > 0 && (
                  <React.Fragment>
                    <div className="wk-grp wk-ws-grp">Standalone</div>
                    {standalone.map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
                  </React.Fragment>
                )}
                {!groups.length && !standalone.length && <div className="empty">clear — pin tasks or set due dates to populate</div>}
              </React.Fragment>
            );
          })()}
          {done.length > 0 && (
            <React.Fragment>
              <div className="wk-grp" style={{cursor:"pointer"}} onClick={() => setDoneOpen(!doneOpen)}>
                <span className={"caret" + (doneOpen ? " open" : "")}><Icon name="chevron" size={10} /></span>
                Done recently <span style={{fontWeight:600,color:"var(--muted)"}}>{done.length}</span>
              </div>
              {doneOpen && done.slice(0, 6).map((t) => <WeekRow key={t.id} t={t} mutate={mutate} openTask={openTask} />)}
            </React.Fragment>
          )}
        </div>
      </div>

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
                      <ReadinessDot t={t} />
                      <div className="wkrow-txt tc-click" onClick={() => openTask && openTask(t.id)}><span className="wkrow-main">{t.text}</span><span className="wkrow-sub">{(wsOf(t) || {}).name}</span></div>
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
