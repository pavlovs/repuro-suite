/* ===== Relations — interactive dependency map (the differentiator) =====
   Tasks laid out left→right by prerequisite depth. Edges = "must finish first".
   Click a node to trace its full upstream/downstream chain. */
function RelationsView({ openTask }) {
  const [sel, setSel] = React.useState(null);
  const [wsFilter, setWsFilter] = React.useState("");

  const { nodes, edges, width, height, ancestors, descendants, deps, dependents } = React.useMemo(() => {
    // connected = has prereqs OR is a prereq of something
    const isPre = new Set();
    TASKS.forEach((t) => (t.prereqs || []).forEach((r) => isPre.add(r)));
    let conn = TASKS.filter((t) => (t.prereqs && t.prereqs.length) || isPre.has(t.id));
    if (wsFilter) conn = conn.filter((t) => (wsOf(t) || {}).id === wsFilter);
    const connIds = new Set(conn.map((t) => t.id));

    const deps = {};       // id -> [prereq ids]
    const dependents = {}; // id -> [tasks that depend on it]
    conn.forEach((t) => { deps[t.id] = (t.prereqs || []).filter((r) => connIds.has(r)); dependents[t.id] = []; });
    conn.forEach((t) => deps[t.id].forEach((r) => dependents[r] && dependents[r].push(t.id)));

    // depth = longest prereq chain
    const depth = {};
    const calc = (id, seen = new Set()) => {
      if (depth[id] != null) return depth[id];
      if (seen.has(id)) return 0;
      seen.add(id);
      const ps = deps[id] || [];
      const d = ps.length ? Math.max(...ps.map((p) => calc(p, seen))) + 1 : 0;
      depth[id] = d; return d;
    };
    conn.forEach((t) => calc(t.id));

    const COL = 264, W = 208, H = 88, VGAP = 102, PADX = 26, PADY = 26;
    const cols = {};
    conn.forEach((t) => { (cols[depth[t.id]] = cols[depth[t.id]] || []).push(t); });
    Object.values(cols).forEach((arr) => arr.sort((a, b) => ((wsOf(a) || {}).id || "").localeCompare((wsOf(b) || {}).id || "") || a.id.localeCompare(b.id)));

    const pos = {};
    Object.entries(cols).forEach(([d, arr]) => arr.forEach((t, i) => { pos[t.id] = { x: PADX + d * COL, y: PADY + i * VGAP, w: W, h: H }; }));
    const maxRows = Math.max(...Object.values(cols).map((a) => a.length));
    const nodes = conn.map((t) => ({ t, ...pos[t.id] }));
    const edges = [];
    conn.forEach((t) => deps[t.id].forEach((r) => edges.push({ from: r, to: t.id })));

    // ancestor/descendant closures
    const closure = (start, map) => {
      const out = new Set(); const stack = [...(map[start] || [])];
      while (stack.length) { const x = stack.pop(); if (out.has(x)) continue; out.add(x); (map[x] || []).forEach((y) => stack.push(y)); }
      return out;
    };
    const ancestors = {}, descendants = {};
    conn.forEach((t) => { ancestors[t.id] = closure(t.id, deps); descendants[t.id] = closure(t.id, dependents); });

    const width = PADX * 2 + (Math.max(...Object.keys(cols).map(Number)) + 1) * COL;
    const height = PADY * 2 + maxRows * VGAP;
    return { nodes, edges, width, height, ancestors, descendants, deps, dependents };
  }, [wsFilter]);

  const chain = sel ? new Set([sel, ...ancestors[sel], ...descendants[sel]]) : null;
  const inChain = (id) => !chain || chain.has(id);
  const edgeActive = (e) => chain && chain.has(e.from) && chain.has(e.to);

  const selTask = sel ? byTask[sel] : null;

  return (
    <div className="rel">
      <div className="rel-bar">
        <div className="rel-legend">
          <span className="rel-flow"><Icon name="arrow" size={14} /> prerequisite flows into dependent</span>
          <span><span className="rdot" data-level="green" style={{ width: 9, height: 9 }} /> ready</span>
          <span><span className="rdot" data-level="amber" style={{ width: 9, height: 9 }} /> prereqs running</span>
          <span><span className="rdot" data-level="red" style={{ width: 9, height: 9 }} /> blocked</span>
        </div>
        <div className="seg">
          {[["", "All workstreams"], ...WORKSTREAMS.map((w) => [w.id, w.name])].map(([v, l]) => (
            <button key={v} className={wsFilter === v ? "on" : ""} onClick={() => { setWsFilter(v); setSel(null); }}>{l}</button>
          ))}
        </div>
      </div>

      <div className="rel-stage-wrap">
        <div className="rel-stage" style={{ width, height }} onClick={() => setSel(null)}>
          <svg className="rel-edges" width={width} height={height}>
            <defs>
              <marker id="arr" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                <path d="M1 1 L8 4.5 L1 8" fill="none" stroke="#b6c4ca" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </marker>
              <marker id="arrA" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                <path d="M1 1 L8 4.5 L1 8" fill="none" stroke="#0891b2" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </marker>
            </defs>
            {edges.map((e, i) => {
              const a = nodes.find((n) => n.t.id === e.from), b = nodes.find((n) => n.t.id === e.to);
              if (!a || !b) return null;
              const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
              const active = edgeActive(e);
              const dim = chain && !active;
              return <path key={i} d={`M ${x1} ${y1} C ${x1 + 46} ${y1}, ${x2 - 46} ${y2}, ${x2} ${y2}`}
                fill="none" stroke={active ? "#0891b2" : "#cfdade"} strokeWidth={active ? 2.4 : 1.4}
                opacity={dim ? 0.18 : 1} markerEnd={active ? "url(#arrA)" : "url(#arr)"} />;
            })}
          </svg>
          {nodes.map((n) => {
            const t = n.t, ws = wsOf(t), r = readiness(t);
            const active = sel === t.id;
            return (
              <div key={t.id} className={"rnode" + (active ? " sel" : "") + (chain && !inChain(t.id) ? " dim" : "")}
                style={{ left: n.x, top: n.y, width: n.w, height: n.h, "--ws": ws ? ws.color : "#888" }}
                onClick={(e) => { e.stopPropagation(); setSel(active ? null : t.id); }}>
                <div className="rnode-top">
                  <span className="rdot" data-level={r} style={{ width: 9, height: 9 }} />
                  <span className="rnode-ws">{ws ? ws.name : ""}</span>
                  {dealOf(t) && <span className="rnode-deal">{dealOf(t).codename}</span>}
                </div>
                <div className="rnode-txt">{t.text}</div>
                <div className="rnode-foot">
                  <OwnerStack owners={t.owners} size={17} />
                  {t.status === "waiting" ? <span className="rnode-wait">@ {t.waiting.party}</span> : <DueChip t={t} />}
                </div>
                {r === "red" && <span className="rnode-flag">blocked</span>}
              </div>
            );
          })}
        </div>
      </div>

      {selTask && (
        <div className="rel-panel">
          <button className="rel-panel-x" onClick={() => setSel(null)}>×</button>
          <div className="rel-panel-eyebrow">{(wsOf(selTask) || {}).name}{dealOf(selTask) ? " · " + dealOf(selTask).codename : ""}</div>
          <div className="rel-panel-title">{selTask.text}</div>
          <div className="rel-panel-meta"><StatusPill status={selTask.status} /><OwnerStack owners={selTask.owners} size={20} />{selTask.due && <DueChip t={selTask} />}</div>
          <button className="rel-panel-open" onClick={() => openTask && openTask(sel)}>Open full detail <Icon name="arrow" size={13} /></button>
          <div className="rel-panel-sec">Must finish first ({deps[sel].length})</div>
          {deps[sel].length ? deps[sel].map((r) => { const p = byTask[r]; return (
            <div key={r} className="rel-panel-row tc-click" onClick={() => openTask && openTask(r)}><span className="rdot" data-level={p.status === "done" ? "green" : readiness(p)} style={{ width: 8, height: 8 }} /><span>{p.text}</span><StatusPill status={p.status} /></div>
          ); }) : <div className="empty">nothing — this can start now</div>}
          <div className="rel-panel-sec">This unblocks ({dependents[sel].length})</div>
          {dependents[sel].length ? dependents[sel].map((r) => { const p = byTask[r]; return (
            <div key={r} className="rel-panel-row tc-click" onClick={() => openTask && openTask(r)}><span className="rdot" data-level={readiness(p)} style={{ width: 8, height: 8 }} /><span>{p.text}</span></div>
          ); }) : <div className="empty">no downstream tasks</div>}
        </div>
      )}
    </div>
  );
}
window.RelationsView = RelationsView;
