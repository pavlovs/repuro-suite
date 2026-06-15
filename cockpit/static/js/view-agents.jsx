/* ===== Agents — Claude works these tasks, you approve with evidence ===== */
function AgentsView({ openTask }) {
  const agents = TASKS.filter((t) => t.execution === "agent");
  const queued = agents.filter((t) => t.status === "open");
  const running = agents.filter((t) => t.status === "in_progress" && t.claimed_by);
  const review = agents.filter((t) => t.status === "in_review");
  const recent = agents.filter((t) => t.status === "done").slice(-5).reverse();

  const Card = ({ t, children }) => (
    <div className="agq-card">
      <div className="agq-top tc-click" onClick={() => openTask(t.id)}>
        <span className="agent-tag"><Icon name="bolt" size={11} /></span>
        <b>{t.text}</b>
        {dealOf(t) && <DealChip deal={dealOf(t)} small />}
      </div>
      {t.ac && <div className="agq-ac"><b>Done when:</b> {t.ac}</div>}
      {children}
    </div>
  );

  return (
    <div className="agq">
      <div className="wk-hint">
        <span><Icon name="bolt" size={13} /> Agent tasks — worked by Claude, reviewed by you.</span>
      </div>
      <div className="agq-cols">
        <div className="card agq-col">
          <div className="wk-h">Queued<span className="wk-n">{queued.length}</span></div>
          {queued.map((t) => <Card key={t.id} t={t} />)}
          {!queued.length && <div className="empty">nothing queued — create a task with "Claude (agent)"</div>}
        </div>
        <div className="card agq-col">
          <div className="wk-h">Running<span className="wk-n">{running.length}</span></div>
          {running.map((t) => (
            <Card key={t.id} t={t}>
              <div className="agq-meta">claimed by {t.claimed_by} · lease until {(t.claim_expires_at || "?").replace("T", " ").slice(0, 16)}</div>
            </Card>
          ))}
          {!running.length && <div className="empty">nothing running</div>}
        </div>
        <div className="card agq-col verdict">
          <div className="wk-h">Needs your verdict<span className="wk-n">{review.length}</span></div>
          {review.map((t) => (
            <Card key={t.id} t={t}>
              <div className="agq-evidence">{t.evidence || "no evidence posted"}</div>
              <div className="agq-actions">
                <button className="btn approve" onClick={() => api.verdict(t, "approve")}><Icon name="check" size={13} />Approve</button>
                <button className="btn reject" onClick={() => {
                  showModal("Send back — what should the agent do differently?", [{placeholder: "feedback for the agent"}]).then((c) => {
                    api.verdict(t, "reject", c || "");
                  });
                }}>Send back</button>
              </div>
            </Card>
          ))}
          {!review.length && <div className="empty">nothing awaiting you</div>}
          {recent.length > 0 && <><div className="wk-grp">Recently approved</div>
            {recent.map((t) => <div key={t.id} className="agq-done tc-click" onClick={() => openTask(t.id)}><Icon name="check" size={12} /> {t.text}</div>)}</>}
        </div>
      </div>
    </div>
  );
}
window.AgentsView = AgentsView;
