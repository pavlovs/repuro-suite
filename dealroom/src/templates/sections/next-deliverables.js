// ─── Next Deliverables (from Cockpit) ────────────────────────────────────────
// Dependencies: DATA global (deal.code_name), esc() helper
// Exports: renderNextDeliverables() → HTML string (async self-loading)

function renderNextDeliverables() {
  const containerId = 'nd-root';
  setTimeout(() => _ndLoad(containerId), 0);
  return _ndStyles() + '<div id="' + containerId + '"><div class="nd-loading">Loading from Cockpit…</div></div>';
}

async function _ndLoad(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const dealCode = ((DATA.deal && DATA.deal.code_name) || '').toLowerCase();

  let state;
  try {
    const resp = await fetch('/cockpit/api/state', { credentials: 'include' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    state = await resp.json();
  } catch (e) {
    // Static HTML export has no same-origin Cockpit API — degrade to a quiet
    // note instead of an error state (mirrors the api/data fetch fallback).
    el.innerHTML = '<div class="nd-loading">Cockpit data is only available in the live suite (' + esc(String(e && e.message || e)) + ')</div>';
    return;
  }

  // Collect deliverables across workstreams matching this deal
  const matched = [];
  for (const space of (state.spaces || [])) {
    for (const ws of (space.workstreams || [])) {
      const wsCode = (ws.deal_codename || '').toLowerCase();
      for (const d of (ws.deliverables || [])) {
        const dCode = (d.deal || '').toLowerCase();
        if (wsCode === dealCode || dCode === dealCode) {
          matched.push({ ws: ws, d: d });
        }
      }
    }
  }

  if (matched.length === 0) {
    el.innerHTML = '<div class="nd-empty">No Cockpit deliverables linked to '
      + esc(DATA.deal.code_name)
      + '.<br><span class="nd-hint">Link a Cockpit workstream to this deal codename to see deliverables here.</span></div>';
    return;
  }

  const today = (state.meta && state.meta.today) || '';

  // Sort: open first ordered by target_date, then done/dropped
  matched.sort(function(a, b) {
    const done = function(s) { return s === 'done' || s === 'dropped' ? 1 : 0; };
    var da = done(a.d.status), db = done(b.d.status);
    if (da !== db) return da - db;
    var ta = a.d.target_date || 'zzzz', tb = b.d.target_date || 'zzzz';
    return ta < tb ? -1 : ta > tb ? 1 : 0;
  });

  const open = matched.filter(function(x) { return x.d.status !== 'done' && x.d.status !== 'dropped'; });
  const done = matched.filter(function(x) { return x.d.status === 'done' || x.d.status === 'dropped'; });

  var h = '<div class="nd-section-header"><span>Cockpit Deliverables</span><span class="nd-deal-tag">' + esc(DATA.deal.code_name) + '</span></div>';

  function renderCard(item) {
    var d = item.d, ws = item.ws;
    var prog = (d.computed && d.computed.progress) || { done: 0, total: 0 };
    var pct = prog.total > 0 ? Math.round(prog.done / prog.total * 100) : 0;
    var isDone = d.status === 'done' || d.status === 'dropped';
    var dateStr = '';
    var isOverdue = false;
    if (d.target_date) {
      var dt = new Date(d.target_date + 'T00:00:00');
      dateStr = dt.toLocaleDateString('de-DE', { day: '2-digit', month: 'short' });
      isOverdue = !isDone && today && d.target_date < today;
    }

    var openTasks = (d.tasks || []).filter(function(t) { return t.status !== 'done'; });
    var taskHtml = '';
    if (openTasks.length > 0) {
      taskHtml = '<ul class="nd-tasks">';
      var shown = openTasks.slice(0, 4);
      for (var i = 0; i < shown.length; i++) {
        var t = shown[i];
        var tDate = (t.computed && t.computed.effective_deadline) || '';
        var tDateStr = tDate ? ' <span class="nd-task-date">' + new Date(tDate + 'T00:00:00').toLocaleDateString('de-DE', { day: '2-digit', month: 'short' }) + '</span>' : '';
        taskHtml += '<li class="nd-task">' + esc(t.text) + tDateStr + '</li>';
      }
      if (openTasks.length > 4) taskHtml += '<li class="nd-task nd-task-more">+' + (openTasks.length - 4) + ' more open</li>';
      taskHtml += '</ul>';
    }

    return '<div class="nd-card' + (isDone ? ' nd-card-done' : '') + '">'
      + '<div class="nd-card-top">'
      + '<span class="nd-name">' + esc(d.name) + '</span>'
      + (dateStr ? '<span class="nd-date' + (isOverdue ? ' nd-overdue' : '') + '">' + dateStr + '</span>' : '')
      + '</div>'
      + '<div class="nd-meta">' + esc(ws.name)
      + (prog.total > 0 ? ' &middot; ' + prog.done + '/' + prog.total + ' tasks' : '')
      + '</div>'
      + (prog.total > 0 ? '<div class="nd-bar"><div class="nd-bar-fill" style="width:' + pct + '%"></div></div>' : '')
      + taskHtml
      + '</div>';
  }

  if (open.length > 0) {
    h += '<div class="nd-group">Open (' + open.length + ')</div>';
    for (var i = 0; i < open.length; i++) h += renderCard(open[i]);
  }
  if (done.length > 0) {
    h += '<div class="nd-group nd-group-done">Done (' + done.length + ')</div>';
    for (var j = 0; j < done.length; j++) h += renderCard(done[j]);
  }

  el.innerHTML = h;
}

function _ndStyles() {
  return '<style>'
    + '.nd-loading{padding:20px;color:#6b7280;font-size:13px}'
    + '.nd-error{padding:12px 16px;background:#fff1f4;border:1px solid #fecdd3;border-radius:6px;color:#e11d48;font-size:12px}'
    + '.nd-empty{padding:20px;color:#6b7280;font-size:13px;line-height:1.6}'
    + '.nd-hint{font-size:11px;color:#94a3b8}'
    + '.nd-section-header{background:#0891B2;color:#fff;padding:10px 16px;border-radius:4px 4px 0 0;font-size:13px;font-weight:700;letter-spacing:.04em;display:flex;justify-content:space-between;align-items:center;margin-bottom:0}'
    + '.nd-deal-tag{font-size:10px;font-weight:600;background:rgba(255,255,255,.18);padding:2px 8px;border-radius:3px}'
    + '.nd-group{font-size:10px;text-transform:uppercase;letter-spacing:.06em;font-weight:700;color:#6b7280;padding:10px 16px 4px;background:#fff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb}'
    + '.nd-group-done{color:#94a3b8}'
    + '.nd-card{background:#fff;border:1px solid #e5e7eb;border-top:none;padding:12px 16px}'
    + '.nd-card:last-child{border-radius:0 0 4px 4px}'
    + '.nd-card-done .nd-name{opacity:.55;text-decoration:line-through}'
    + '.nd-card-done .nd-date{opacity:.5}'
    + '.nd-card-top{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:3px}'
    + '.nd-name{font-size:13px;font-weight:600;color:#111827}'
    + '.nd-date{font-size:11px;color:#6b7280;white-space:nowrap}'
    + '.nd-overdue{color:#e11d48;font-weight:600}'
    + '.nd-meta{font-size:11px;color:#9ca3af;margin-bottom:6px}'
    + '.nd-bar{height:3px;background:#f3f4f6;border-radius:2px;margin-bottom:8px}'
    + '.nd-bar-fill{height:3px;background:#0891B2;border-radius:2px;transition:width .3s}'
    + '.nd-tasks{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px}'
    + '.nd-task{font-size:12px;color:#374151;display:flex;align-items:baseline;justify-content:space-between;gap:8px;padding:2px 0;border-bottom:1px solid #f3f4f6}'
    + '.nd-task:last-child{border-bottom:none}'
    + '.nd-task-date{font-size:11px;color:#9ca3af;white-space:nowrap;flex-shrink:0}'
    + '.nd-task-more{font-size:11px;color:#9ca3af;font-style:italic}'
    + '</style>';
}
