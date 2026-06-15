/* ===== Overview — the intelligence cockpit landing ===== */
function delivStats(d) {
  const tasks = TASKS.filter((t) => t.d === d.id);
  const open = tasks.filter((t) => t.status !== "done");
  const done = tasks.length - open.length;
  let r = "green";
  for (const t of open) { const x = readiness(t); if (x === "red") r = "red"; else if (x === "amber" && r !== "red") r = "amber"; }
  return { total: tasks.length, done, open: open.length, readiness: open.length ? r : "green" };
}

function OverviewView({ person, onJump, openTask }) {
  const mine = (t) => (t.owners || []).includes(person);
  const live = TASKS.filter((t) => t.status !== "done");
  const myLive = live.filter(mine);
  const blocked = myLive.filter((t) => readiness(t) === "red");
  const waiting = myLive.filter((t) => t.status === "waiting")
    .sort((a, b) => ((a.waiting && a.waiting.chase) || "9999").localeCompare((b.waiting && b.waiting.chase) || "9999"));
  const toChase = waiting.filter((t) => chaseDue(t));
  const overdue = myLive.filter((t) => t.status !== "waiting" && t.due && daysUntil(t.due) < 0);
  const dueWeek = myLive.filter((t) => t.status !== "waiting" && t.due && daysUntil(t.due) >= 0 && daysUntil(t.due) <= 7);
  // ONE card per deal (a deal can span several deliverables) — stage comes from
  // the dealroom mirror; progress/readiness roll up across all its deliverables
  const dealMap = {};
  DELIVERABLES.filter((d) => d.deal).forEach((d) => {
    const k = (d.deal.codename || "").trim().toLowerCase(); // case/space drift must not split a deal
    (dealMap[k] = dealMap[k] || { codename: d.deal.codename.trim(), stage: d.deal.stage, delivs: [] }).delivs.push(d);
  });
  const rank = { green: 0, amber: 1, red: 2 };
  const deals = Object.values(dealMap).map((g) => {
    const tasks = TASKS.filter((t) => g.delivs.some((d) => d.id === t.d));
    const open = tasks.filter((t) => t.status !== "done");
    let r = "green";
    open.forEach((t) => { if (rank[readiness(t)] > rank[r]) r = readiness(t); });
    const next = open.filter((t) => t.due).sort((a, b) => a.due.localeCompare(b.due))[0];
    // the milestone that matters: the next deliverable with open work
    const nextDeliv = g.delivs
      .filter((d) => tasks.some((t) => t.d === d.id && t.status !== "done"))
      .sort((a, b) => (a.target || "9999").localeCompare(b.target || "9999"))[0];
    const nd = nextDeliv ? {
      name: nextDeliv.name, target: nextDeliv.target,
      done: tasks.filter((t) => t.d === nextDeliv.id && t.status === "done").length,
      total: tasks.filter((t) => t.d === nextDeliv.id).length,
    } : null;
    return { ...g, total: tasks.length, done: tasks.length - open.length, open: open.length, readiness: r, next, nd };
  }).filter((g) => g.open > 0);
  const focus = live.filter((t) => (t.owners || []).includes(person) && (t.pinned || (t.due && daysUntil(t.due) <= 1) || chaseDue(t)))
    .sort((a, b) => (a.due || "9").localeCompare(b.due || "9"));

  const dateLine = todayDate.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })
    + " · week " + Math.ceil((((todayDate - new Date(todayDate.getFullYear(), 0, 1)) / 86400000) + new Date(todayDate.getFullYear(), 0, 1).getDay() + 1) / 7);
  const kpis = [
    { k: "Deals", v: deals.length, sub: "with open work", icon: "deal", tone: "brand", to: "table" },
    { k: "Tasks", v: myLive.length, sub: dueWeek.length + " due this week", icon: "board", tone: "ink", to: "table" },
    { k: "Blocked", v: blocked.length, sub: blocked.length ? "need unblocking" : "none", icon: "relations", tone: "red", to: "relations" },
    { k: "Chase", v: toChase.length, sub: waiting.length + " with others", icon: "clock", tone: "purple", to: "week" },
  ];

  return (
    <div className="ov">
      <div className="ov-hero">
        <div>
          <div className="ov-hello">{PEOPLE[person].name}</div>
          <div className="ov-date">{dateLine}</div>
        </div>
      </div>

      <div className="kpi-row">
        {kpis.map((c) => (
          <button key={c.k} className="kpi" data-tone={c.tone} onClick={() => onJump(c.to)}>
            <div className="kpi-ico"><Icon name={c.icon} size={15} /></div>
            <div className="kpi-v">{c.v}</div>
            <div className="kpi-k">{c.k}</div>
            <div className="kpi-sub">{c.sub}</div>
            <span className="kpi-arrow"><Icon name="arrow" size={14} /></span>
          </button>
        ))}
      </div>

      {focus.length > 0 && (
        <div className="card" style={{marginBottom:"var(--gap)"}}>
          <div className="card-h"><h3>Focus today</h3><span className="card-h-sub">{focus.length} items</span></div>
          <div className="ov-deliv-list">
            {focus.slice(0, 5).map((t) => (
              <div key={t.id} className="ov-deliv-row tc-click" onClick={() => openTask && openTask(t.id)}>
                <ReadinessDot t={t} />
                <span className="ov-deliv-name">{t.text}</span>
                {dealOf(t) && <DealChip deal={dealOf(t)} small />}
                {t.status === "waiting" ? <WaitingChip t={t} /> : <DueChip t={t} />}
              </div>
            ))}
            {focus.length > 5 && <button className="ov-deliv-more" onClick={() => onJump("week")}>{focus.length - 5} more in My Week →</button>}
          </div>
        </div>
      )}

      {(() => {
        const rk = { red: 0, amber: 1, green: 2 };
        const allActive = DELIVERABLES
          .filter((d) => TASKS.some((t) => t.d === d.id && t.status !== "done"))
          .map((d) => { const s = delivStats(d); return { ...d, s, ws: byWs[d.ws], du: d.target ? daysUntil(d.target) : null }; });
        const attn = allActive
          .filter((d) => d.s.readiness === "red" || d.s.readiness === "amber" || (d.du !== null && d.du <= 14))
          .sort((a, b) => {
            if (rk[a.s.readiness] !== rk[b.s.readiness]) return rk[a.s.readiness] - rk[b.s.readiness];
            if (a.du !== null && b.du !== null) return a.du - b.du;
            if (a.du !== null) return -1;
            if (b.du !== null) return 1;
            return 0;
          });
        const blockedD = attn.filter((d) => d.s.readiness === "red").length;
        const quiet = allActive.length - attn.length;
        return (
          <div className="card attn attn-hero">
            <div className="card-h">
              <h3>Deliverables</h3>
              <span className="card-h-sub">{attn.length} need attention{quiet ? " · " + quiet + " on track" : ""}</span>
            </div>
            <div className="ov-deliv-list">
              {attn.map((d) => (
                <div key={d.id} className="ov-deliv-row tc-click" onClick={() => onJump("table")}>
                  <span className="rdot" data-level={d.s.readiness} style={{ width: 9, height: 9 }} />
                  <span className="ov-deliv-name">{d.name}</span>
                  {d.deal && <DealChip deal={d.deal} small />}
                  <span className="deliv-prog">
                    <span className="prog-bar"><span style={{ width: (d.s.total ? d.s.done / d.s.total * 100 : 0) + "%", background: d.ws ? d.ws.color : "var(--brand)" }} /></span>
                    {d.s.done}/{d.s.total}
                  </span>
                  {d.target && <span className={"ov-deliv-due" + (d.du < 0 ? " over" : d.du <= 7 ? " soon" : "")}>{fdate(d.target)}</span>}
                  {!d.target && <span className="ov-deliv-due none">—</span>}
                </div>
              ))}
              {!attn.length && <div className="empty">all deliverables on track</div>}
              {quiet > 0 && <button className="ov-deliv-more" onClick={() => onJump("table")}>{quiet} more on track in Workstreams →</button>}
            </div>
          </div>
        );
      })()}

      <div className="ov-dealroom-link">
        <a className="dealroom-btn" href={window.DEALROOM_URL || "#"} target="_blank" rel="noopener"
          onClick={(e) => { if (!window.DEALROOM_URL) { e.preventDefault(); onJump("table"); } }}>
          <Icon name="deal" size={16} />
          <span>Open Dealroom</span>
          <span className="dealroom-count">{deals.length} deals in flight</span>
          <Icon name="arrow" size={14} />
        </a>
      </div>
    </div>
  );
}
window.OverviewView = OverviewView;
window.delivStats = delivStats;
