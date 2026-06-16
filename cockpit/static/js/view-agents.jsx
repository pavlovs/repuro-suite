/* ===== Agents — each task is its own independent card ===== */
/* person → handover initials: RD = RC (Roman), FF = FC (Flo) */
var HANDOVER_INITIALS = { RD: "RC", FF: "FC" };

function AgentsView({ openTask, person }) {
  var agents = TASKS.filter(function(t) { return t.execution === "agent"; });
  var active = agents.filter(function(t) { return t.status !== "done"; });
  var recent = agents.filter(function(t) { return t.status === "done"; }).slice(-5).reverse();
  var showRecent = React.useState(false);
  var showRecentVal = showRecent[0], setShowRecent = showRecent[1];
  var showHowTo = React.useState(false);
  var showHowToVal = showHowTo[0], setShowHowTo = showHowTo[1];

  var review = agents.filter(function(t) { return t.status === "in_review"; });
  var running = agents.filter(function(t) { return t.status === "in_progress" && t.claimed_by; });
  var queued = agents.filter(function(t) { return t.status === "open"; });

  /* sort queued tasks by sort_order then by numeric id suffix (ids are "t-<n>") */
  var parseId = function(id) { return parseInt((id || "").replace("t-", ""), 10) || 0; };
  var queuedSorted = queued.slice().sort(function(a, b) {
    if (a.sortOrder !== b.sortOrder) return a.sortOrder - b.sortOrder;
    return parseId(a.id) - parseId(b.id);
  });
  var queuePosition = {};
  queuedSorted.forEach(function(t, i) { queuePosition[t.id] = i + 1; });

  /* render active cards: verdict first, then running, then queued (in queue order) */
  var statusPriority = function(t) {
    if (t.status === "in_review") return 0;
    if (t.status === "in_progress" && t.claimed_by) return 1;
    return 2 + (queuePosition[t.id] || 99);
  };
  var activeSorted = active.slice().sort(function(a, b) { return statusPriority(a) - statusPriority(b); });

  var wsFor = function(t) {
    var d = DELIVERABLES.find(function(d) { return d.id === t.d; });
    if (!d) return null;
    return WORKSTREAMS.find(function(w) { return w.id === d.ws; });
  };

  var stateOf = function(t) {
    if (t.status === "in_review") return { label: "Needs verdict", cls: "ag-verdict", icon: "alert" };
    if (t.status === "in_progress" && t.claimed_by) return { label: "Running", cls: "ag-running", icon: "bolt" };
    return { label: "Queued", cls: "ag-queued", icon: "table" };
  };

  var AgentCard = function(props) {
    var t = props.t;
    var ws = wsFor(t);
    var st = stateOf(t);
    var r = readiness(t);
    var qpos = (t.status === "open") ? queuePosition[t.id] : null;

    return (
      <div className={"ag-card " + st.cls}>
        <div className="ag-card-top">
          <span className={"ag-state-badge " + st.cls}><Icon name={st.icon} size={11} /> {st.label}</span>
          {qpos && <span className="ag-queue-pos">#{qpos}</span>}
          {ws && <span className="ag-card-ws">{ws.name}</span>}
        </div>
        <div className="ag-card-title tc-click" onClick={function() { openTask(t.id); }}>{t.text}</div>
        {t.ac && <div className="ag-card-ac"><b>Done when:</b> {t.ac}</div>}

        {t.status === "in_review" && t.evidence && <div className="ag-card-evidence">{t.evidence}</div>}
        {t.status === "in_review" && !t.evidence && <div className="ag-card-no-ev">No evidence posted</div>}
        {t.status === "in_review" && (
          <div className="ag-card-actions">
            <button className="btn approve" onClick={function() {
              var initials = HANDOVER_INITIALS[person] || person;
              api.save(t, { owners: [initials] }).then(function() { api.verdict(t, "approve"); });
            }}><Icon name="check" size={13} />Approve</button>
            <button className="btn reject" onClick={function() {
              showModal("Send back — what should the agent do differently?", [{placeholder: "feedback for the agent"}]).then(function(c) {
                api.verdict(t, "reject", c || "");
              });
            }}>Send back</button>
          </div>
        )}

        {t.status === "in_progress" && t.claimed_by && (
          <div className="ag-card-meta">Claimed by {t.claimed_by}</div>
        )}

        {t.status === "open" && r === "red" && t.need && <div className="ag-card-blocked">Blocked: {t.need}</div>}
        {t.status === "open" && r === "green" && <div className="ag-card-ready">Ready to pick up</div>}
      </div>
    );
  };

  return (
    <div className="agq">
      <div className="wk-hint">
        <span><Icon name="bolt" size={13} /> Agent tasks — worked by Claude, reviewed by you.</span>
        <span className="wk-hint-sp" />
        <span style={{fontSize:12,color:"var(--muted)"}}>
          {review.length} awaiting verdict · {running.length} running · {queued.length} queued
        </span>
      </div>

      <div className="ag-howto-panel">
        <button className="ag-howto-toggle" onClick={function() { setShowHowTo(!showHowToVal); }}>
          <span className={"caret" + (showHowToVal ? " open" : "")}><Icon name="chevron" size={12} /></span>
          How to use agent tasks
        </button>
        {showHowToVal && (
          <div className="ag-howto-body">
            <ul>
              <li><b>What:</b> Agent tasks are worked autonomously by Claude. It executes, posts evidence, and waits for your verdict.</li>
              <li><b>Queue:</b> Create or edit a task and set execution type to <b>Claude (agent)</b>. It lands here with a position number.</li>
              <li><b>Run:</b> Open Claude Code in <code>CLAUDE_REPURO</code> and type <code>/agent-loop</code>. Claude works the queue in order and reports back.</li>
              <li><b>States:</b> Queued (#1, #2…) → Running → Needs verdict. Approve to close; Send back with feedback to re-queue.</li>
              <li><b>Blocked tasks</b> (red border) have unmet dependencies — resolve before starting a loop or Claude will skip them.</li>
            </ul>
          </div>
        )}
      </div>

      <div className="ag-cards">
        {activeSorted.map(function(t) { return <AgentCard key={t.id} t={t} />; })}
      </div>

      {!active.length && (
        <div className="card" style={{padding:"24px 28px",fontSize:13,color:"var(--ink-2)",marginTop:12,textAlign:"center"}}>
          No agent tasks active. Create a task with execution type "Claude (agent)" to queue work.
        </div>
      )}

      {recent.length > 0 && (
        <div className="ag-recent" style={{marginTop:16}}>
          <button className="ag-recent-toggle" onClick={function() { setShowRecent(!showRecentVal); }}>
            <span className={"caret" + (showRecentVal ? " open" : "")}><Icon name="chevron" size={12} /></span>
            Recently completed ({recent.length})
          </button>
          {showRecentVal && (
            <div className="ag-cards" style={{marginTop:8}}>
              {recent.map(function(t) {
                return (
                  <div key={t.id} className="ag-card ag-done tc-click" onClick={function() { openTask(t.id); }}>
                    <div className="ag-card-top"><span className="ag-state-badge ag-done-badge"><Icon name="check" size={11} /> Done</span></div>
                    <div className="ag-card-title">{t.text}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
window.AgentsView = AgentsView;
