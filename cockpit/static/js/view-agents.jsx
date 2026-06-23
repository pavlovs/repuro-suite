/* ===== Agents — review-first: "Needs your review" up top, then Running, Queue, FAQ ===== */
/* person → handover initials: RD = RC (Roman), FF = FC (Flo) */
var HANDOVER_INITIALS = { RD: "RC", FF: "FC" };

/* Render evidence text with clickable links — [label](url) and bare URLs become
   anchors so the produced .md / artifacts are one click away; newlines preserved. */
function renderEvidence(text) {
  if (!text) return null;
  var out = [], re = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s]+)/g;
  var last = 0, m, k = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    var label = m[2] ? m[1] : m[3], href = m[2] || m[3];
    out.push(<a key={k++} href={href} target="_blank" rel="noreferrer">{label}</a>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function AgentsView({ openTask, person }) {
  var allAgents = TASKS.filter(function(t) { return t.execution === "agent"; });
  var lane = React.useState("all");
  var laneVal = lane[0], setLane = lane[1];
  var agents = laneVal === "all" ? allAgents : allAgents.filter(function(t) { return t.lane === laneVal; });
  var recent = agents.filter(function(t) { return t.status === "done"; }).slice(-5).reverse();
  var showRecent = React.useState(false);
  var showRecentVal = showRecent[0], setShowRecent = showRecent[1];
  var showFaq = React.useState(false);
  var showFaqVal = showFaq[0], setShowFaq = showFaq[1];

  /* lane filter — RC (Roman) / FC (Flo); counts = active tasks, ignore current filter */
  var laneN = function(l) {
    return allAgents.filter(function(t) { return t.status !== "done" && (l === "all" || t.lane === l); }).length;
  };
  var LANES = [["all", "All"], ["RC", "RC"], ["FC", "FC"]];

  var review = agents.filter(function(t) { return t.status === "in_review"; });
  var running = agents.filter(function(t) { return t.status === "in_progress" && t.claimed_by; });
  var queued = agents.filter(function(t) { return t.status === "open"; });

  var parseId = function(id) { return parseInt((id || "").replace("t-", ""), 10) || 0; };
  var queuedSorted = queued.slice().sort(function(a, b) {
    if (a.sortOrder !== b.sortOrder) return a.sortOrder - b.sortOrder;
    return parseId(a.id) - parseId(b.id);
  });
  var queuePosition = {};
  queuedSorted.forEach(function(t, i) { queuePosition[t.id] = i + 1; });

  var wsFor = function(t) {
    var d = DELIVERABLES.find(function(d) { return d.id === t.d; });
    if (!d) return null;
    return WORKSTREAMS.find(function(w) { return w.id === d.ws; });
  };

  /* ---- prominent verdict card (the surface Roman/Flo live in) ---- */
  var ReviewCard = function(props) {
    var t = props.t, ws = wsFor(t);
    return (
      <div className="ag-rev-card">
        <div className="ag-rev-head">
          {t.lane && <span className={"ag-lane-chip ag-lane-" + t.lane}>{t.lane}</span>}
          {t.dealCode && <span className="ag-rev-deal">{t.dealCode}</span>}
          {ws && <span className="ag-rev-ws">{ws.name}</span>}
          <span className="ag-rev-id">{t.id}</span>
        </div>
        <div className="ag-rev-title" onClick={function() { openTask(t.id); }}>{t.text}</div>
        {t.ac && <div className="ag-rev-ac"><b>Done when:</b> {t.ac}</div>}
        <div className="ag-rev-evlabel">Result / evidence</div>
        {t.evidence
          ? <div className="ag-rev-ev">{renderEvidence(t.evidence)}</div>
          : <div className="ag-rev-noev">No evidence posted yet.</div>}
        <div className="ag-rev-actions">
          <button className="btn approve" onClick={function() {
            var initials = HANDOVER_INITIALS[person] || person;
            api.save(t, { owners: [initials] }).then(function() { api.verdict(t, "approve"); });
          }}><Icon name="check" size={14} /> Approve</button>
          <button className="btn reject" onClick={function() {
            showModal("Send back — what should the agent do differently?", [{placeholder: "feedback for the agent"}]).then(function(c) {
              api.verdict(t, "reject", c || "");
            });
          }}>Send back</button>
        </div>
      </div>
    );
  };

  /* ---- compact card for running / queued ---- */
  var AgentCard = function(props) {
    var t = props.t, ws = wsFor(t), r = readiness(t);
    var qpos = (t.status === "open") ? queuePosition[t.id] : null;
    var st = (t.status === "in_progress")
      ? { label: "Running", cls: "ag-running", icon: "bolt" }
      : { label: "Queued", cls: "ag-queued", icon: "table" };
    return (
      <div className={"ag-card " + st.cls}>
        <div className="ag-card-top">
          <span className={"ag-state-badge " + st.cls}><Icon name={st.icon} size={11} /> {st.label}</span>
          {qpos && <span className="ag-queue-pos">#{qpos}</span>}
          {t.lane && <span className={"ag-lane-chip ag-lane-" + t.lane}>{t.lane}</span>}
          {ws && <span className="ag-card-ws">{ws.name}</span>}
        </div>
        <div className="ag-card-title tc-click" onClick={function() { openTask(t.id); }}>{t.text}</div>
        {t.ac && <div className="ag-card-ac"><b>Done when:</b> {t.ac}</div>}
        {t.status === "in_progress" && t.claimed_by && <div className="ag-card-meta">Claimed by {t.claimed_by}</div>}
        {t.status === "open" && r === "red" && t.need && <div className="ag-card-blocked">Blocked: {t.need}</div>}
        {t.status === "open" && r === "green" && <div className="ag-card-ready">Ready to pick up</div>}
      </div>
    );
  };

  return (
    <div className="agq">
      {/* ---- Lane filter (RC / FC) ---- */}
      <div className="ag-lanebar">
        <span className="ag-lanebar-label">Lane</span>
        <div className="ag-seg">
          {LANES.map(function(l) {
            return (
              <button key={l[0]} className={"ag-seg-btn" + (laneVal === l[0] ? " on" : "")}
                onClick={function() { setLane(l[0]); }}>
                {l[1]} <span className="ag-seg-n">{laneN(l[0])}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ---- Needs your review (primary) ---- */}
      <section className="ag-sec">
        <h2 className="ag-sec-h">
          Needs your review
          {review.length > 0 && <span className="ag-sec-count ag-count-attn">{review.length}</span>}
        </h2>
        {review.length > 0
          ? review.map(function(t) { return <ReviewCard key={t.id} t={t} />; })
          : <div className="ag-sec-empty">Nothing waiting on you. Finished agent tasks land here for approval.</div>}
      </section>

      {/* ---- Running ---- */}
      {running.length > 0 && (
        <section className="ag-sec">
          <h2 className="ag-sec-h">Running <span className="ag-sec-count">{running.length}</span></h2>
          <div className="ag-cards">{running.map(function(t) { return <AgentCard key={t.id} t={t} />; })}</div>
        </section>
      )}

      {/* ---- Queue ---- */}
      <section className="ag-sec">
        <h2 className="ag-sec-h">Queue <span className="ag-sec-count">{queued.length}</span></h2>
        {queuedSorted.length > 0
          ? <div className="ag-cards">{queuedSorted.map(function(t) { return <AgentCard key={t.id} t={t} />; })}</div>
          : <div className="ag-sec-empty">Queue empty. Add a task with execution <b>Claude (agent)</b>, or run <code>/repuro:queue</code>.</div>}
      </section>

      {/* ---- Recently completed ---- */}
      {recent.length > 0 && (
        <section className="ag-sec">
          <button className="ag-faq-toggle" onClick={function() { setShowRecent(!showRecentVal); }}>
            <span className={"caret" + (showRecentVal ? " open" : "")}><Icon name="chevron" size={13} /></span>
            Recently completed ({recent.length})
          </button>
          {showRecentVal && (
            <div className="ag-cards" style={{marginTop:10}}>
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
        </section>
      )}

      {/* ---- FAQ (numbered, collapsed) ---- */}
      <div className="ag-faq">
        <button className="ag-faq-toggle" onClick={function() { setShowFaq(!showFaqVal); }}>
          <span className={"caret" + (showFaqVal ? " open" : "")}><Icon name="chevron" size={13} /></span>
          How to set up &amp; run <code>/repuro</code>
        </button>
        {showFaqVal && (
          <ol className="ag-faq-body">
            <li><b>What it is.</b> Agent tasks are run by Claude via the <code>/repuro</code> plugin — it executes the task and posts the result above for your verdict. Nothing auto-closes.</li>
            <li><b>Set up once</b> (in Claude Code): <code>/plugin marketplace add pavlovs/repuro-cockpit-skills</code> → <code>/plugin install repuro</code> → <code>/repuro:setup &lt;your-token&gt;</code>. No clone, no scripts — ask Roman for your token; it sets your lane (RC / FC) automatically.</li>
            <li><b>Run it.</b> <code>/repuro:queue</code> lists your lane; <code>/repuro:run &lt;id | #position | words&gt;</code> claims and runs one task. Add <code>--all</code> to work across both lanes.</li>
            <li><b>Review.</b> Results appear under <b>Needs your review</b> above — <b>Approve</b> to close, or <b>Send back</b> with feedback to re-queue.</li>
            <li><b>Repo</b> (auto-updates): <a href="https://github.com/pavlovs/repuro-cockpit-skills" target="_blank" rel="noreferrer">github.com/pavlovs/repuro-cockpit-skills</a></li>
          </ol>
        )}
      </div>
    </div>
  );
}
window.AgentsView = AgentsView;
