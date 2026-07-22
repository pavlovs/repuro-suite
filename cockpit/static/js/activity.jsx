/* ===== Activity log panel + per-task history section ===== */

/* Human-readable action label */
function fmtAction(action, entity, after) {
  var entityShort = entity && entity !== "bulk" ? entity : "";
  var name = (after && (after.text || after.name)) ? "‘" + (after.text || after.name) + "’" : (entityShort ? entityShort : "");
  var map = {
    task_create:        "created task "        + name,
    task_update:        "updated "             + (entityShort || "task") + (name && name !== entityShort ? " " + name : ""),
    task_delete:        "deleted task "        + name,
    task_approve:       "approved "            + (entityShort || "task"),
    task_reject:        "rejected "            + (entityShort || "task"),
    workstream_create:  "created workstream "  + name,
    workstream_update:  "updated workstream "  + (entityShort || ""),
    deliverable_create: "created deliverable " + name,
    deliverable_update: "updated deliverable " + (entityShort || ""),
    agent_claim:        "claimed "             + (entityShort || "task"),
    agent_result:       "submitted result for "+ (entityShort || "task"),
    agent_heartbeat:    "heartbeat on "        + (entityShort || "task"),
    lease_expired:      "lease expired on "    + (entityShort || "task"),
    tasks_reorder:      "reordered tasks",
    import_update:      "imported update to "  + (entityShort || "task"),
  };
  return map[action] || (action + (entityShort ? " " + entityShort : ""));
}

/* Actor display name — audit actors are user ids; map to initials via PEOPLE */
function actorLabel(actor) {
  if (!actor || actor === "system") return "System";
  for (var k in PEOPLE) {
    if (PEOPLE[k].userId === actor) return k;
  }
  return actor;
}

/* Relative time: "2 min ago", "3h ago", "Jan 5" */
function relTime(isoStr) {
  if (!isoStr) return "";
  var now = Date.now();
  var ts = new Date(isoStr).getTime();
  var diff = Math.floor((now - ts) / 1000);
  if (diff < 0) diff = 0;
  if (diff < 60) return diff + "s ago";
  if (diff < 3600) return Math.floor(diff / 60) + " min ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  var d = new Date(isoStr);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/* Date bucket label */
function dateBucket(isoStr) {
  if (!isoStr) return "Unknown";
  var d = new Date(isoStr);
  var dStr = d.toDateString();
  var today = new Date();
  today.setHours(0, 0, 0, 0);
  var yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (dStr === new Date().toDateString()) return "Today";
  if (dStr === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short" });
}

/* Single activity entry row */
function ActivityEntry({ entry }) {
  var actor = actorLabel(entry.actor);
  var label = fmtAction(entry.action, entry.entity, entry.after);
  var time = relTime(entry.timestamp);

  /* Highlight what changed for updates */
  var changeHint = null;
  if (entry.action === "task_update" && entry.before && entry.after) {
    var keys = Object.keys(entry.after).filter(function(k) {
      return k !== "updated_at" && k !== "last_touched_at" && entry.before[k] !== entry.after[k];
    });
    if (keys.length > 0 && keys.length <= 3) {
      changeHint = keys.map(function(k) {
        var v = entry.after[k];
        if (v === null) return k + " cleared";
        return k + " → " + String(v).slice(0, 30);
      }).join(", ");
    }
  }

  return (
    <div className="activity-entry">
      <div className="activity-entry-top">
        <span className="activity-actor">{actor}</span>
        <span className="activity-label">{label}</span>
        <span className="activity-time">{time}</span>
      </div>
      {changeHint && <div className="activity-hint">{changeHint}</div>}
    </div>
  );
}

/* Full activity slide-out panel */
function ActivityPanel({ open, onClose }) {
  var [entries, setEntries] = React.useState(null);
  var [error, setError] = React.useState(null);

  React.useEffect(function() {
    if (!open) return;
    setEntries(null);
    setError(null);
    var base = window.COCKPIT_BASE || "";
    var token = sessionStorage.getItem("cockpit_token") || "";
    var headers = token ? { Authorization: "Bearer " + token } : {};
    fetch(base + "/api/activity", { headers: headers })
      .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function(d) { setEntries(d.entries || []); })
      .catch(function(e) { setError("Failed to load: " + e.message); });
  }, [open]);

  React.useEffect(function() {
    if (!open) return;
    var onEsc = function(e) { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onEsc);
    return function() { window.removeEventListener("keydown", onEsc); };
  }, [open, onClose]);

  if (!open) return null;

  /* Group entries by date bucket */
  var groups = [];
  if (entries) {
    var seen = {};
    entries.forEach(function(e) {
      var bucket = dateBucket(e.timestamp);
      if (!seen[bucket]) { seen[bucket] = true; groups.push({ label: bucket, items: [] }); }
      groups[groups.length - 1].items.push(e);
    });
  }

  return (
    <>
      <div className="activity-scrim" onClick={onClose} />
      <aside className="activity-panel" onClick={function(e) { e.stopPropagation(); }}>
        <div className="activity-header">
          <span className="activity-title">Activity</span>
          <button className="activity-close" onClick={onClose} title="Close">×</button>
        </div>
        <div className="activity-body">
          {error && <div className="activity-error">{error}</div>}
          {!error && entries === null && <div className="activity-loading">Loading…</div>}
          {!error && entries && entries.length === 0 && <div className="activity-empty">No activity yet.</div>}
          {!error && groups.map(function(g) {
            return (
              <div key={g.label}>
                <div className="activity-date-group">{g.label}</div>
                {g.items.map(function(e) { return <ActivityEntry key={e.id} entry={e} />; })}
              </div>
            );
          })}
        </div>
      </aside>
    </>
  );
}
window.ActivityPanel = ActivityPanel;

/* Per-task history — rendered inside the task drawer */
function TaskHistory({ taskId }) {
  var [entries, setEntries] = React.useState(null);

  React.useEffect(function() {
    if (!taskId) { setEntries([]); return; }
    setEntries(null);
    var cancelled = false;
    var base = window.COCKPIT_BASE || "";
    var token = sessionStorage.getItem("cockpit_token") || "";
    var headers = token ? { Authorization: "Bearer " + token } : {};
    fetch(base + "/api/activity?entity=" + encodeURIComponent(taskId), { headers: headers })
      .then(function(r) { return r.ok ? r.json() : { entries: [] }; })
      .then(function(d) { if (!cancelled) setEntries((d.entries || []).slice(0, 5)); })
      .catch(function() { if (!cancelled) setEntries([]); });
    return function() { cancelled = true; };
  }, [taskId]);

  if (entries === null) return <div className="activity-loading" style={{ fontSize: 11 }}>Loading history…</div>;
  if (entries.length === 0) return <div className="empty">no changes recorded yet</div>;

  return (
    <div className="task-history-list">
      {entries.map(function(e) {
        var actor = actorLabel(e.actor);
        var label = fmtAction(e.action, e.entity, e.after);
        return (
          <div key={e.id} className="task-history-row">
            <span className="activity-actor">{actor}</span>
            <span className="task-history-label">{label}</span>
            <span className="activity-time">{relTime(e.timestamp)}</span>
          </div>
        );
      })}
    </div>
  );
}
window.TaskHistory = TaskHistory;
