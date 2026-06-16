/* ===== Shared task drawer — the single editing surface, everything inline ===== */
function FieldInput({ value, onSave, type = "text", placeholder, className, big }) {
  // uncontrolled + save-on-blur/Enter: no per-keystroke writes, no stale closures
  return (
    <input type={type} className={className} key={value || "empty"} defaultValue={value || ""}
      placeholder={placeholder}
      onKeyUp={(e) => { if (e.key === "Enter") e.target.blur(); }}
      onBlur={(e) => { if (e.target.value !== (value || "")) onSave(e.target.value || null); }} />
  );
}

function TaskDrawer({ task, onClose, mutate, openTask }) {
  const [addingPre, setAddingPre] = React.useState(false);
  const [preQ, setPreQ] = React.useState("");
  React.useEffect(() => { setAddingPre(false); setPreQ(""); window.closeDrawer = onClose; }, [task && task.id]);
  React.useEffect(() => {
    if (!task) return;
    const onEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [task && task.id]);
  if (!task) return null;

  const ws = wsOf(task), deal = dealOf(task), deliv = delivOf(task);
  const pre = (task.prereqs || []).map((r) => byTask[r]).filter(Boolean);
  const deps = (DEPENDENTS[task.id] || []).map((r) => byTask[r]).filter(Boolean);
  const r = readiness(task);

  const setStatus = (s) => {
    if (s === "waiting") {
      api.save(task, { waiting: { party: (task.waiting || {}).party || "—", type: (task.waiting || {}).type || "counterparty", chase: (task.waiting || {}).chase || addDays(TODAY, 3) } });
    } else {
      api.save(task, { status: s, ...(s === "done" ? { pinned: false } : {}) });
    }
  };

  const preHits = addingPre && preQ.trim()
    ? TASKS.filter((p) => p.id !== task.id && p.status !== "done"
        && !(task.prereqs || []).includes(p.id)
        && p.text.toLowerCase().includes(preQ.trim().toLowerCase())).slice(0, 6)
    : [];

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="drawer-x" onClick={onClose} title="Close">×</button>
        <div className="drawer-eyebrow">
          <span className="ws-ico sm" style={{ background: ws ? ws.color : "#888" }}><Icon name={ws ? ws.icon : "ops"} size={11} /></span>
          <button className="drawer-jump" title="show in Workstreams"
            onClick={() => { window.dispatchEvent(new CustomEvent("cockpit:jump", { detail: "table" })); onClose(); }}>
            {ws ? ws.name : "Standalone"}{deliv ? " › " + deliv.name : ""}
          </button>
          {deal && <span className="drawer-stage">{deal.codename} · {STAGE_LABEL[deal.stage] || deal.stage} <span className="muted">(stage from dealroom)</span></span>}
        </div>

        <FieldInput big className="drawer-title-input" value={task.text}
          onSave={(v) => v && api.save(task, { text: v })} placeholder="task" />

        <textarea className="drawer-note" key={"n" + task.id} defaultValue={task.detail || ""}
          placeholder="add a note — context, links, next step…"
          onBlur={(e) => { if (e.target.value !== (task.detail || "")) api.save(task, { detail: e.target.value || null }); }} />

        {task.ac && <p className="drawer-detail"><b>Done when:</b> {task.ac}</p>}
        {task.evidence && <p className="drawer-detail drawer-evidence">{task.evidence}</p>}

        {r === "red" && (
          <div className="drawer-block">
            <span className="rdot" data-level="red" style={{ width: 8, height: 8 }} /> Blocked — must finish first: <b>{pre.filter((p) => p.status !== "done").map((p) => p.text).join(", ")}</b>
          </div>
        )}

        <div className="drawer-sec-lbl">Status</div>
        <div className="drawer-status">
          {STATUS_ORDER.map((s) => (
            <button key={s} className={task.status === s ? "on" : ""} data-status={s} onClick={() => setStatus(s)}>{STATUS_LABEL[s]}</button>
          ))}
        </div>

        {task.status === "waiting" && task.waiting && (
          <div className="drawer-wait editable">
            <Icon name="clock" size={13} /> with
            <FieldInput className="dw-party" value={task.waiting.party}
              onSave={(v) => api.save(task, { waiting: { ...task.waiting, party: v || "—" } })} />
            <select className="dm-select" value={task.waiting.type || "counterparty"}
              onChange={(e) => api.save(task, { waiting: { ...task.waiting, type: e.target.value } })}>
              <option>counterparty</option><option>advisor</option><option>investor</option><option>internal</option>
            </select>
            chase
            <FieldInput type="date" className="dm-date" value={task.waiting.chase}
              onSave={(v) => api.save(task, { waiting: { ...task.waiting, chase: v } })} />
          </div>
        )}

        <div className="drawer-meta">
          <div><span className="dm-k">Owner</span><span className="dm-v dm-edit">
            {["RD", "FF"].map((p) => (
              <button key={p} className={"own-toggle" + ((task.owners || []).includes(p) ? " on" : "")}
                title={(task.owners || []).includes(p) ? "remove " + PEOPLE[p].name : "add " + PEOPLE[p].name}
                onClick={() => {
                  const owners = (task.owners || []).includes(p)
                    ? task.owners.filter((x) => x !== p) : [...(task.owners || []), p];
                  api.save(task, { owners });
                }}><Avatar id={p} size={20} /></button>
            ))}
            {task.ownersRaw && !["RD", "FF"].some((p) => (task.ownersRaw || "").includes(p)) &&
              <span className="dm-ext" title={task.ownersRaw}>{task.ownersRaw}</span>}
          </span></div>
          <div><span className="dm-k">Due</span><span className="dm-v">
            <FieldInput type="date" className="dm-date" value={task.ownDue}
              onSave={(v) => api.save(task, { due: v })} />
          </span></div>
          <div><span className="dm-k">Priority</span><span className="dm-v">
            <select className="dm-select" value={task.priority || ""}
              onChange={(e) => api.save(task, { priority: e.target.value || null })}>
              <option value="">—</option><option value="high">High</option><option value="med">Medium</option><option value="low">Low</option>
            </select>
          </span></div>
          <div><span className="dm-k">Kind</span><span className="dm-v">
            <select className="dm-select" value={task.kind || "workplan"}
              onChange={(e) => api.save(task, { kind: e.target.value })}>
              <option value="workplan">Workplan</option><option value="followup">Follow-up</option>
              <option value="approval">Approval</option><option value="agent_job">Agent job</option>
              <option value="personal">Personal</option>
            </select>
          </span></div>
          <div><span className="dm-k">Worked by</span><span className="dm-v">
            <select className="dm-select" value={task.execution || "me"}
              onChange={(e) => {
                const v = e.target.value;
                if (v === "agent" && !task.ac) {
                  showModal("Done when… (the agent is judged against this):", [{placeholder: "e.g. model standardized, deltas listed"}]).then((ac) => {
                    if (!ac) return;
                    api.save(task, { execution: "agent", ac: ac.trim() });
                  });
                } else api.save(task, { execution: v });
              }}>
              <option value="me">Me</option><option value="together">Together</option><option value="agent">Claude (agent)</option>
            </select>
          </span></div>
          <div><span className="dm-k">Readiness</span><span className="dm-v"><span className="rdot" data-level={r} style={{ width: 9, height: 9, marginRight: 6 }} />{{ green: "Ready", amber: "Prereqs running", red: "Blocked" }[r]}
            <button className={"pin-btn" + (task.pinned ? " on" : "")} style={{ marginLeft: 10 }} title={task.pinned ? "unpin" : "pin to today"} onClick={() => api.save(task, { pinned: !task.pinned })}><Icon name="pin" size={13} /></button>
          </span></div>
          <div><span className="dm-k">Input from</span><span className="dm-v dm-edit">
            <select className="dm-select" value={task.inputFrom || ""}
              onChange={(e) => {
                const v = e.target.value || null;
                if (v && !task.inputQuestion) {
                  showModal("What input is needed?", [{ placeholder: "e.g. confirm budget, approve draft" }]).then((q) => {
                    if (q === null) return;
                    api.save(task, { inputFrom: v, inputQuestion: q.trim() || null });
                  });
                } else {
                  api.save(task, { inputFrom: v, inputQuestion: v ? task.inputQuestion : null });
                }
              }}>
              <option value="">— none —</option>
              {["RD", "FF"].map((p) => <option key={p} value={p}>{PEOPLE[p].name}</option>)}
            </select>
          </span></div>
          {task.inputFrom && (
            <div><span className="dm-k">Question</span><span className="dm-v">
              <FieldInput className="dm-date" style={{width:"100%"}} value={task.inputQuestion}
                placeholder="what's needed from them"
                onSave={(v) => api.save(task, { inputQuestion: v })} />
            </span></div>
          )}
        </div>

        <div className="drawer-sec-lbl">Dependencies — must finish first <span className="dm-n">{pre.length}</span>
          <button className="mini-btn dm-add" onClick={() => setAddingPre(!addingPre)}>{addingPre ? "close" : "+ add dependency"}</button>
        </div>
        {addingPre && (
          <div className="dm-pre-add">
            <input autoFocus placeholder="search a task this one must wait for…" value={preQ} onChange={(e) => setPreQ(e.target.value)} />
            {preHits.map((p) => (
              <button key={p.id} className="drawer-link-row" onClick={() => {
                api.save(task, { prereqs: [...(task.prereqs || []), p.id] });
                setAddingPre(false); setPreQ("");
              }}>
                <Icon name="plus" size={11} /><span className="dlr-txt">{p.text}</span><StatusPill status={p.status} />
              </button>
            ))}
            {preQ.trim() && !preHits.length && (
              <button className="drawer-link-row dm-pre-create" onClick={async () => {
                const created = await api.create({ text: preQ.trim(), owners: task.owners || ["RD"], d: task.d || "" });
                if (created) {
                  api.save(task, { prereqs: [...(task.prereqs || []), created.id] });
                  setAddingPre(false); setPreQ("");
                }
              }}>
                <Icon name="plus" size={11} /><span className="dlr-txt">Create "<b>{preQ.trim()}</b>" and add as dependency</span>
              </button>
            )}
          </div>
        )}
        {pre.length ? pre.map((p) => (
          <div key={p.id} className="drawer-link-row as-row">
            <button className="dlr-go" onClick={() => openTask(p.id)}>
              <span className="rdot" data-level={p.status === "done" ? "green" : readiness(p)} style={{ width: 8, height: 8 }} />
              <span className="dlr-txt">{p.text}</span>
              <StatusPill status={p.status} />
            </button>
            <button className="dlr-rm" title="remove dependency"
              onClick={() => api.save(task, { prereqs: (task.prereqs || []).filter((x) => x !== p.id) })}>×</button>
          </div>
        )) : <div className="empty">none — this can start any time</div>}

        <div className="drawer-sec-lbl">This unblocks <span className="dm-n">{deps.length}</span></div>
        {deps.length ? deps.map((p) => (
          <button key={p.id} className="drawer-link-row" onClick={() => openTask(p.id)}>
            <span className="rdot" data-level={readiness(p)} style={{ width: 8, height: 8 }} />
            <span className="dlr-txt">{p.text}</span>
            <Avatar id={(p.owners || [])[0]} size={18} />
          </button>
        )) : <div className="empty">no downstream tasks</div>}

        <div className="drawer-sec-lbl">History</div>
        <TaskHistory taskId={task.id} />

        <div className="drawer-foot">
          <button className="drawer-delete" onClick={() => api.deleteTask(task)}>Delete task</button>
        </div>
      </aside>
    </>
  );
}
window.TaskDrawer = TaskDrawer;
