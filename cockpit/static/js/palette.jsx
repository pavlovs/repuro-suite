/* ===== {navigator.platform.indexOf("Mac") >= 0 ? "⌘" : "Ctrl+"}K command palette + live search — jump to any task or deal ===== */
function Palette({ open, onClose, openTask, onJump }) {
  const [q, setQ] = React.useState("");
  React.useEffect(() => { if (open) setQ(""); }, [open]);
  if (!open) return null;

  const needle = q.trim().toLowerCase();
  const hit = (s) => s && s.toLowerCase().indexOf(needle) >= 0;

  const taskHits = needle ? TASKS.filter((t) =>
    hit(t.text) || hit(t.dealCode) || hit((dealOf(t) || {}).codename) || hit(t.ownersRaw) || hit((t.waiting || {}).party) || hit(t.detail)
  ).slice(0, 9) : [];
  const dealHits = needle ? DELIVERABLES.filter((d) =>
    d.deal ? (hit(d.deal.codename) || hit(d.name)) : hit(d.name)
  ).slice(0, 5) : [];
  const views = [["overview", "Cockpit"], ["week", "Weekly Meeting"], ["table", "Workstreams"],
    ["timeline", "Timeline"], ["agents", "Agents"]]
    .filter(([, l]) => !needle || hit(l));

  const pick = (fn) => { fn(); onClose(); };

  return (
    <div className="pal-scrim" onClick={onClose}>
      <div className="pal" onClick={(e) => e.stopPropagation()}>
        <div className="pal-input">
          <Icon name="search" size={16} />
          <input autoFocus placeholder="Search tasks, deals, views…  (Esc to close)" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyUp={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "Enter" && taskHits.length) pick(() => openTask(taskHits[0].id));
            }} />
          <span className="pal-kbd">{navigator.platform.indexOf("Mac") >= 0 ? "⌘" : "Ctrl+"}K</span>
        </div>
        {needle && (
          <div className="pal-results">
            {taskHits.length > 0 && <div className="pal-grp">Tasks</div>}
            {taskHits.map((t) => (
              <button key={t.id} className="pal-row" onClick={() => pick(() => openTask(t.id))}>
                <span className="pal-txt">{t.text}</span>
                <ReadinessDot t={t} />
                <span className="pal-sub">{(wsOf(t) || {}).name}{t.dealCode ? " · " + t.dealCode : ""}</span>
                <StatusPill status={t.status} />
              </button>
            ))}
            {dealHits.length > 0 && <div className="pal-grp">Deals & deliverables</div>}
            {dealHits.map((d) => {
              const next = TASKS.filter((t) => t.d === d.id && t.status !== "done")
                .sort((a, b) => (a.due || "9").localeCompare(b.due || "9"))[0];
              return (
                <button key={d.id} className="pal-row"
                  title={next ? "opens next task: " + next.text : "opens Workstreams"}
                  onClick={() => pick(() => (next ? openTask(next.id) : onJump("table")))}>
                  <span className="ws-ico sm" style={{ background: (byWs[d.ws] || {}).color }}><Icon name="deal" size={11} /></span>
                  <span className="pal-txt">{d.name}</span>
                  {next && <span className="pal-sub">next: {next.text}</span>}
                  {d.deal && <DealChip deal={d.deal} small />}
                </button>
              );
            })}
            {views.length > 0 && <div className="pal-grp">Views</div>}
            {views.map(([id, l]) => (
              <button key={id} className="pal-row" onClick={() => pick(() => onJump(id))}>
                <Icon name={NAV_ICONS[id] || "table"} size={14} /><span className="pal-txt">{l}</span>
              </button>
            ))}
            {!taskHits.length && !dealHits.length && !views.length && <div className="pal-empty">no matches</div>}
          </div>
        )}
      </div>
    </div>
  );
}
const NAV_ICONS = { overview: "cockpit", week: "week", table: "table", timeline: "timeline", agents: "bolt" };
window.Palette = Palette;
