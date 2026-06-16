/* ===== Quick-add (the working "+ New task") + New-deal playbook modal ===== */
const PLAYBOOK_STEPS = [
  "NDA signed",
  "IM / financials received",
  "Financial model built",
  "Indicative offer sent",
  "LOI negotiated + signed",
  "DD kickoff (RFI + advisors)",
  "SPA draft negotiated",
  "Signing / notary",
];

function QuickAdd({ open, onClose, prefill }) {
  const initType = (prefill && prefill.type) || "task";
  const [mode, setMode] = React.useState(initType);
  const [f, setF] = React.useState({ text: "", d: "", ws: "", owners: ["RD"], due: TODAY, priority: "", execution: "me", ac: "", status: "open", target: "", inputFrom: "", inputQuestion: "" });
  React.useEffect(() => {
    if (open) {
      const t = (prefill && prefill.type) || "task";
      setMode(t);
      setF({
        text: "", d: (prefill && prefill.d) || "", ws: (prefill && prefill.ws) || "",
        owners: ["RD"], due: TODAY, priority: "", execution: "me", ac: "",
        status: (prefill && prefill.status) || "open", target: "",
        inputFrom: "", inputQuestion: "",
      });
    }
  }, [open]);
  if (!open) return null;

  const toggleOwner = (p) => setF((s) => ({ ...s, owners: s.owners.includes(p) ? s.owners.filter((x) => x !== p) : [...s.owners, p] }));

  const submitTask = async () => {
    if (!f.text.trim()) return showToast("Task text required", "err");
    if (f.execution === "agent" && !f.ac.trim()) return showToast("Agent tasks need 'done when…' (acceptance criteria)", "err");
    if (f.inputFrom && !f.inputQuestion.trim()) return showToast("Describe what input is needed", "err");
    const fields = { text: f.text.trim(), owners: f.owners, execution: f.execution, kind: f.execution === "agent" ? "agent_job" : "followup" };
    if (f.status && f.status !== "open") fields.status = f.status;
    if (f.d) fields.d = f.d;
    if (f.due) fields.due = f.due;
    if (f.priority) fields.priority = f.priority;
    if (f.ac) fields.ac = f.ac.trim();
    if (f.inputFrom) { fields.inputFrom = f.inputFrom; fields.inputQuestion = f.inputQuestion.trim(); }
    const t = await api.create(fields);
    if (t) onClose(t.id);
  };

  const submitDeliv = async () => {
    if (!f.text.trim()) return showToast("Deliverable name required", "err");
    const wsId = f.ws || (WORKSTREAMS[0] && WORKSTREAMS[0].id);
    if (!wsId) return showToast("No workstream available", "err");
    if (!f.target) {
      const ok = await showModal("No target date set", [
        {label: "This deliverable won't appear on the timeline. Click OK to continue anyway.", type: "select", options: [{value: "yes", label: "Continue without a target date"}], value: "yes"},
      ]);
      if (ok === null) return;
    }
    await api.createDeliv(wsId, f.text.trim(), f.target || null);
    onClose();
  };

  const submit = mode === "deliverable" ? submitDeliv : submitTask;

  return (
    <div className="qa-scrim" onClick={onClose}>
      <div className="qa-modal" onClick={(e) => e.stopPropagation()}>
        <div className="qa-type-toggle">
          <button className={mode === "task" ? "on" : ""} onClick={() => setMode("task")}><Icon name="check" size={13} />Task</button>
          <button className={mode === "deliverable" ? "on" : ""} onClick={() => setMode("deliverable")}><Icon name="timeline" size={13} />Deliverable</button>
        </div>
        {mode === "task" && (
          <React.Fragment>
            <input className="qa-input" autoFocus placeholder="What needs to happen?" value={f.text}
              onChange={(e) => setF({ ...f, text: e.target.value })} onKeyUp={(e) => e.key === "Enter" && submit()} />
            <div className="qa-row">
              <label>Deliverable
                <select value={f.d} onChange={(e) => setF({ ...f, d: e.target.value })}>
                  <option value="">(standalone)</option>
                  {WORKSTREAMS.map((w) => (
                    <optgroup key={w.id} label={w.name}>
                      {DELIVERABLES.filter((d) => d.ws === w.id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </optgroup>
                  ))}
                </select>
              </label>
              <label>Due
                <input type="date" value={f.due} onChange={(e) => setF({ ...f, due: e.target.value })} />
              </label>
            </div>
            <div className="qa-row">
              <label>Owner
                <span className="qa-owners">
                  {["RD", "FF"].map((p) => (
                    <button key={p} className={f.owners.includes(p) ? "on" : ""} onClick={() => toggleOwner(p)}>
                      <Avatar id={p} size={18} />{PEOPLE[p].name}
                    </button>
                  ))}
                </span>
              </label>
              <label>Priority
                <select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
                  <option value="">—</option><option value="high">High</option><option value="med">Medium</option><option value="low">Low</option>
                </select>
              </label>
              <label>Who works it
                <select value={f.execution} onChange={(e) => setF({ ...f, execution: e.target.value })}>
                  <option value="me">Me</option><option value="together">Together</option><option value="agent">Claude (agent)</option>
                </select>
              </label>
            </div>
            {f.execution === "agent" && (
              <label className="qa-ac">Done when… (the agent is judged against this)
                <input className="qa-input" placeholder="e.g. model standardized to EN, deltas listed" value={f.ac}
                  onChange={(e) => setF({ ...f, ac: e.target.value })} />
              </label>
            )}
            <div className="qa-input-required">
              <label className="qa-ir-toggle">
                <input type="checkbox" checked={!!f.inputFrom}
                  onChange={(e) => setF({ ...f, inputFrom: e.target.checked ? "FF" : "", inputQuestion: "" })} />
                <span>Needs input from someone?</span>
              </label>
              {f.inputFrom && (
                <div className="qa-row">
                  <label>Who
                    <select value={f.inputFrom} onChange={(e) => setF({ ...f, inputFrom: e.target.value })}>
                      {["RD", "FF"].map((p) => <option key={p} value={p}>{PEOPLE[p].name}</option>)}
                    </select>
                  </label>
                  <label style={{flex:2}}>What's needed
                    <input className="qa-input" placeholder="e.g. confirm budget, approve draft" value={f.inputQuestion}
                      onChange={(e) => setF({ ...f, inputQuestion: e.target.value })} />
                  </label>
                </div>
              )}
            </div>
          </React.Fragment>
        )}
        {mode === "deliverable" && (
          <React.Fragment>
            <input className="qa-input" autoFocus placeholder="Deliverable name (milestone)" value={f.text}
              onChange={(e) => setF({ ...f, text: e.target.value })} onKeyUp={(e) => e.key === "Enter" && submit()} />
            <div className="qa-row">
              <label>Workstream
                <select value={f.ws} onChange={(e) => setF({ ...f, ws: e.target.value })}>
                  {WORKSTREAMS.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
              </label>
              <label>Target date
                <input type="date" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} />
              </label>
            </div>
          </React.Fragment>
        )}
        <div className="qa-actions">
          <button className="btn" onClick={() => onClose()}>Cancel</button>
          <button className="btn primary" onClick={submit}><Icon name="plus" size={14} />Create {mode}</button>
        </div>
      </div>
    </div>
  );
}

function NewDeal({ open, onClose }) {
  const [f, setF] = React.useState({ codename: "", ws: "", target: "", steps: PLAYBOOK_STEPS.map(() => true) });
  React.useEffect(() => {
    if (open) {
      const ma = WORKSTREAMS.find((w) => /pipeline|m&a/i.test(w.name)) || WORKSTREAMS[0];
      setF({ codename: "", ws: ma.id, target: "", steps: PLAYBOOK_STEPS.map(() => true) });
    }
  }, [open]);
  if (!open) return null;

  const submit = () => {
    const code = f.codename.trim();
    if (!code) return showToast("Codename required (codenames only — no real company names here)", "err");
    const steps = PLAYBOOK_STEPS.filter((_, i) => f.steps[i]);
    if (!steps.length) return showToast("Pick at least one playbook step", "err");
    api.spinupDeal(f.ws, code, steps, f.target || null);
  };

  return (
    <div className="qa-scrim" onClick={onClose}>
      <div className="qa-modal" onClick={(e) => e.stopPropagation()}>
        <h2>New deal — standard playbook</h2>
        <p className="qa-sub">Spins up the deal with the standard arc, each step gated on the previous one. Codename only.</p>
        <div className="qa-row">
          <label>Codename
            <input className="qa-input" autoFocus placeholder="e.g. Heron" value={f.codename}
              onChange={(e) => setF({ ...f, codename: e.target.value })} />
          </label>
          <label>Workstream
            <select value={f.ws} onChange={(e) => setF({ ...f, ws: e.target.value })}>
              {WORKSTREAMS.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </label>
          <label>Target (signing)
            <input type="date" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} />
          </label>
        </div>
        <div className="qa-steps">
          {PLAYBOOK_STEPS.map((s, i) => (
            <label key={s} className="qa-step">
              <input type="checkbox" checked={f.steps[i]}
                onChange={() => setF({ ...f, steps: f.steps.map((v, j) => (j === i ? !v : v)) })} />
              <span className="qa-step-n">{i + 1}</span>{s}
            </label>
          ))}
        </div>
        <div className="qa-actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn primary" onClick={submit}><Icon name="deal" size={14} />Create deal</button>
        </div>
      </div>
    </div>
  );
}

window.QuickAdd = QuickAdd;
window.NewDeal = NewDeal;
