/* ===== Timeline v2 — workstream → deliverable gantt, all items expandable, reduced labels ===== */
function TimelineView({ openTask, openDeliv, mutate }) {
  const ZOOM_MIN = 160;
  const [range, setRange] = React.useState(3); // months from today
  const [open, setOpen] = React.useState({});
  const [filter, setFilter] = React.useState("dated"); // all | dated | undated
  const [filtersOpen, setFiltersOpen] = React.useState(true);
  const [showAllDeals, setShowAllDeals] = React.useState(false);
  const toggle = (id) => setOpen((o) => ({ ...o, [id]: !o[id] }));

  const activeFilterCount = filter !== "all" ? 1 : 0;
  const LABELW = 380, RH = 48, SUBH = 32;
  const scrollRef = React.useRef(null);
  const [containerW, setContainerW] = React.useState(0);
  React.useEffect(() => {
    if (!scrollRef.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((es) => { for (const e of es) setContainerW(e.contentRect.width); });
    ro.observe(scrollRef.current);
    return () => ro.disconnect();
  }, []);

  const allDelivs = DELIVERABLES.filter((d) => d.target || TASKS.some((t) => t.d === d.id));
  const hasDates = (d) => d.target || TASKS.some((t) => t.d === d.id && t.due);
  const filtered = filter === "dated" ? allDelivs.filter(hasDates) : filter === "undated" ? allDelivs.filter((d) => !hasDates(d)) : allDelivs;

  if (!allDelivs.length) {
    return (
      <div className="card" style={{ padding: "28px 32px", fontSize: 13, color: "#475569" }}>
        Nothing to show. Add tasks to deliverables in <b>Workstreams</b> to see them here.
      </div>
    );
  }

  // date range: from start of current month to today + range months
  let min = new Date(todayDate.getFullYear(), todayDate.getMonth(), 1);
  let max = new Date(todayDate.getFullYear(), todayDate.getMonth() + range + 1, 1);
  const months = [];
  for (let m = new Date(min); m < max; m.setMonth(m.getMonth() + 1)) months.push(new Date(m));
  const availW = containerW > 0 ? containerW - LABELW : 0;
  const MW = months.length > 0 ? Math.max(ZOOM_MIN, Math.floor(availW / months.length)) : ZOOM_MIN;
  const totalW = months.length * MW;
  const xPos = (d) => (((typeof d === "string" ? new Date(d + "T00:00:00") : d) - min) / (max - min)) * totalW;
  const xClamped = (d) => Math.min(totalW, Math.max(0, xPos(d)));
  const inWindow = (d) => { const x = xPos(d); return x >= -MW && x <= totalW + MW; };
  const RDOT = { green: "#16a34a", amber: "#eab308", red: "#e11d48", grey: "#c8d2d6" };
  const rank = { green: 0, amber: 1, red: 2 };
  const taskColor = (t) => t.status === "done" ? "#16a34a" : RDOT[readiness(t)];

  function cluster(tasks) {
    const pts = tasks.filter((t) => t.due).map((t) => ({ t, x: xPos(t.due) })).sort((a, b) => a.x - b.x);
    const THRESH = 15, out = [];
    for (const p of pts) {
      const last = out[out.length - 1];
      if (last && p.x - last.x <= THRESH) { last.items.push(p.t); last.x = (last.x * (last.items.length - 1) + p.x) / last.items.length; }
      else out.push({ x: p.x, items: [p.t] });
    }
    return out;
  }
  const worst = (items) => items.reduce((w, t) => { const r = t.status === "done" ? "green" : readiness(t); return rank[r] > rank[w] ? r : w; }, "green");

  const undatedCount = allDelivs.filter((d) => !hasDates(d)).length;

  return (
    <div>
      <div className="gantt-bar-top">
        <FilterBar filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} activeCount={activeFilterCount}>
          <div className="seg">
            <span className="seg-lbl">range</span>
            {[[1, "1 mo"], [2, "2 mo"], [3, "3 mo"], [6, "6 mo"]].map(([v, l]) => (
              <button key={v} className={range === v ? "on" : ""} onClick={() => setRange(v)}>{l}</button>
            ))}
          </div>
          <div className="seg">
            <span className="seg-lbl">show</span>
            <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>All</button>
            <button className={filter === "dated" ? "on" : ""} onClick={() => setFilter("dated")}>Dated</button>
            <button className={filter === "undated" ? "on" : ""} onClick={() => setFilter("undated")}>
              Undated{undatedCount > 0 && <span className="tl-filter-n">{undatedCount}</span>}
            </button>
          </div>
        </FilterBar>
      </div>

      <div className="gantt card">
        <div className="gantt-scroll" ref={scrollRef}>
          <div className="gantt-grid" style={{ width: LABELW + totalW }}>
            <div className="gantt-head" style={{ height: 36 }}>
              <div className="gantt-corner" style={{ width: LABELW }}>Deliverable</div>
              <div className="gantt-months" style={{ width: totalW }}>
                {months.map((m, i) => (
                  <div key={i} className="gantt-mo" style={{ left: i * MW, width: MW }}>
                    {m.toLocaleString("en", { month: "short" })} <span className="gantt-yr">'{String(m.getFullYear()).slice(2)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="gantt-body" style={{ position: "relative" }}>
              {months.map((m, i) => <div key={i} className="gantt-vline" style={{ left: LABELW + i * MW }} />)}
              <div className="gantt-today" style={{ left: LABELW + xClamped(todayDate) }}><span className="gantt-today-lbl">today</span></div>

              {SPACES.map((space) => {
                const allSpaceWs = (wsPerSpace[space.id] || []);
                const visibleWs = showAllDeals ? allSpaceWs : allSpaceWs.filter((w) => w.visibility !== "hidden");
                const hiddenCount = allSpaceWs.filter((w) => w.visibility === "hidden").length;
                const spaceWs = visibleWs;
                const hasDelivs = spaceWs.some((w) => filtered.some((d) => d.ws === w.id));
                if (!hasDelivs && !hiddenCount) return null;
                return (
                  <React.Fragment key={space.id}>
                    <div className="space-band" style={{ width: LABELW + totalW }}>
                      {space.name}
                      <span className="space-count">{spaceWs.length}</span>
                      {hiddenCount > 0 && (
                        <button className="space-band-toggle" onClick={() => setShowAllDeals((v) => !v)}>
                          {showAllDeals ? "hide inactive" : "+" + hiddenCount + " inactive"}
                        </button>
                      )}
                    </div>
                    {spaceWs.map((w) => {
                const delivs = filtered.filter((d) => d.ws === w.id);
                if (!delivs.length) return null;
                return (
                  <React.Fragment key={w.id}>
                    <div className="gantt-band" style={{ width: LABELW + totalW }}>
                      <span className="ws-ico sm" style={{ background: w.color }}><Icon name={w.icon} size={11} /></span>
                      {w.displayNum && <span className="num-prefix">{w.displayNum}</span>}
                      <span className="gantt-band-name">{w.name}</span>
                      <span className="gantt-band-count">{delivs.length}</span>
                    </div>
                    {delivs.sort((a, b) => (a.target || "9999").localeCompare(b.target || "9999")).map((d) => {
                      const s = delivStats(d);
                      const dTasks = TASKS.filter((t) => t.d === d.id);
                      const openTasks = dTasks.filter((t) => t.status !== "done" && t.due);
                      const dated = hasDates(d);
                      const du = d.target ? daysUntil(d.target) : null;
                      const isOpen = open[d.id];
                      const clusters = cluster(openTasks);
                      const pct = s.total > 0 ? Math.round((s.done / s.total) * 100) : 0;

                      return (
                        <React.Fragment key={d.id}>
                          <div className={"gantt-row" + (isOpen ? " expanded" : "") + (!dated ? " gantt-row-undated" : "")} style={{ height: RH }}>
                            <div className="gantt-label clickable" style={{ width: LABELW }} onClick={() => toggle(d.id)}>
                              <span className={"caret" + (isOpen ? " open" : "")}><Icon name="chevron" size={12} /></span>
                              <span className="rdot" data-level={s.readiness} style={{ width: 8, height: 8 }} />
                              {d.displayNum && <span className="num-prefix">{d.displayNum}</span>}
                              <span className="gantt-name">{d.name}</span>
                              {d.deal && <span className="gantt-deal">{d.deal.codename}</span>}
                              <button className="deliv-edit" title="edit deliverable"
                                onClick={(e) => { e.stopPropagation(); openDeliv && openDeliv(d.id); }}>✎</button>
                              <span className="gantt-prog-inline" title={s.done + " of " + s.total + " done"}>
                                <span className="gantt-prog-bar"><span style={{ width: pct + "%", background: RDOT[s.readiness] }} /></span>
                              </span>
                            </div>
                            <div className="gantt-track" style={{ width: totalW }}>
                              {dated && (() => {
                                const dueDates = dTasks.filter((t) => t.due).map((t) => t.due).concat(d.target ? [d.target] : []);
                                const start = dueDates.reduce((a, b) => (a < b ? a : b));
                                const end = dueDates.reduce((a, b) => (a > b ? a : b));
                                const x1 = xClamped(start), x2 = xClamped(d.target || end);
                                const barX = Math.min(x1, x2), barW = Math.max(18, Math.abs(x2 - x1));

                                // Explicit duration bar when start_date is set
                                const hasDurationBar = !!(d.startDate && d.target);
                                const hasOpenEndedBar = !!(d.startDate && !d.target);
                                const dbX1 = d.startDate ? xClamped(d.startDate) : null;
                                const dbX2 = d.target ? xClamped(d.target) : null;
                                // open-ended: extend 60px past the task spread or at least 60px wide
                                const openEndX = d.startDate ? Math.min(totalW, xPos(d.startDate) + Math.max(60, (xPos(end || d.startDate) - xPos(d.startDate)) + 20)) : null;

                                return (
                                  <React.Fragment>
                                    {/* task-spread background bar — only when no explicit startDate */}
                                    {!d.startDate && <div className="gantt-bar" style={{ left: barX, width: barW, background: w.color + "18", borderColor: w.color + "44" }} />}
                                    {/* explicit duration bar: start_date → target_date */}
                                    {hasDurationBar && (
                                      <div className="tl-bar" style={{ left: dbX1, width: Math.max(18, dbX2 - dbX1), background: w.color + "33", borderColor: w.color + "88" }}
                                        title={d.name + ": " + fdateShort(d.startDate) + " → " + fdateShort(d.target)} />
                                    )}
                                    {/* open-ended bar: start_date only, dashed right edge */}
                                    {hasOpenEndedBar && (
                                      <div className="tl-bar tl-bar-open" style={{ left: dbX1, width: Math.max(18, openEndX - dbX1), background: w.color + "22", borderColor: w.color + "66" }}
                                        title={d.name + ": from " + fdateShort(d.startDate) + " (no target set)"} />
                                    )}
                                    {clusters.filter((c) => inWindow(c.items[0].due)).map((c, i) => { const cx = Math.min(totalW, Math.max(0, c.x)); return c.items.length === 1 ? (
                                      <div key={i} className="gantt-tick" style={{ left: cx, background: taskColor(c.items[0]) }}
                                        title={c.items[0].text + " — due " + fdate(c.items[0].due)}
                                        onClick={(e) => { e.stopPropagation(); openTask(c.items[0].id); }} />
                                    ) : (
                                      <div key={i} className="gantt-cluster" style={{ left: cx, background: RDOT[worst(c.items)] }}
                                        title={c.items.length + " tasks due here:\n" + c.items.map((t) => "• " + t.text + " (" + fdate(t.due) + ")").join("\n")}
                                        onClick={(e) => { e.stopPropagation(); toggle(d.id); }}>{c.items.length}</div>
                                    ); })}
                                    {d.target && inWindow(d.target) && <div className="gantt-diamond" style={{ left: x2, background: RDOT[s.readiness] }}
                                      title={d.name + " target: " + fdateShort(d.target)} />}
                                    {d.target && inWindow(d.target) && <div className={"gantt-target-lbl" + (du < 0 ? " over" : du <= 7 ? " soon" : "")} style={{ left: Math.min(x2 + 12, totalW - 48) }}>
                                      {du < 0 ? Math.abs(du) + "d over" : du === 0 ? "today" : du <= 14 ? du + "d" : ""}
                                    </div>}
                                  </React.Fragment>
                                );
                              })()}
                              {!dated && (
                                <div className="gantt-undated-hint">
                                  <Icon name="clock" size={12} />
                                  <span>{s.open} task{s.open !== 1 ? "s" : ""} open — no dates set</span>
                                </div>
                              )}
                            </div>
                          </div>
                          {isOpen && dTasks.sort((a, b) => (a.due || "9").localeCompare(b.due || "9")).map((t) => (
                            <div key={t.id} className={"gantt-subrow" + (t.status === "done" ? " done" : "")} style={{ height: SUBH }}>
                              <div className="gantt-sublabel clickable" style={{ width: LABELW }} onClick={() => openTask(t.id)}>
                                <span className="rdot" data-level={t.status === "done" ? "green" : readiness(t)} style={{ width: 7, height: 7 }} />
                                <span className={"gantt-subname" + (t.status === "done" ? " done" : "")}>{t.text}</span>
                                <OwnerStack owners={t.owners} size={16} />
                              </div>
                              <div className="gantt-track" style={{ width: totalW }}>
                                {t.due && inWindow(t.due) && <div className="gantt-subdot" style={{ left: xClamped(t.due), background: taskColor(t) }} onClick={() => openTask(t.id)}
                                  title={t.text + " — " + fdateShort(t.due)} />}
                                {t.due && inWindow(t.due) && t.status === "waiting" && t.waiting && (
                                  <div className="gantt-sub-wait" style={{ left: Math.min(xClamped(t.due) + 12, totalW - 48) }}>@ {t.waiting.party}</div>
                                )}
                                {!t.due && (
                                  <div className="gantt-sub-nodate" onClick={() => openTask(t.id)}>
                                    <span className="gantt-set-date">set date →</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </React.Fragment>
                      );
                    })}
                  </React.Fragment>
                );
              })}
                  </React.Fragment>
                );
              })}
            </div>
          </div>
        </div>
        <div className="gantt-foot">
          <span><span className="diamond-key" /> Target date</span>
          <span><span className="tick-key" /> Task due</span>
          <span><span className="gantt-today-key" /> Today</span>
        </div>
      </div>
    </div>
  );
}
window.TimelineView = TimelineView;
