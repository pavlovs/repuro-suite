/* Boot loader: token login -> fetch /api/state -> map to COCKPIT_DATA shape ->
   compile the JSX bundle. Also owns window.api — ALL mutations write through to
   the FastAPI backend (version-checked; 409 => reload). Plain JS, no JSX here. */
(function () {
  "use strict";

  /* ---- toast notifications (replaces alert() for non-blocking feedback) ---- */
  var _toastEl;
  function ensureToast() {
    if (_toastEl) return _toastEl;
    _toastEl = document.createElement("div");
    _toastEl.className = "ck-toast";
    document.body.appendChild(_toastEl);
    return _toastEl;
  }
  window.showToast = function (msg, type, ms) {
    var t = ensureToast();
    t.textContent = msg;
    t.className = "ck-toast " + (type || "info");
    void t.offsetWidth;
    t.classList.add("show");
    clearTimeout(t._tid);
    t._tid = setTimeout(function () { t.classList.remove("show"); }, ms || 4000);
  };

  /* ---- mini-modal (replaces prompt() — returns a Promise) ---- */
  window.showModal = function (title, fields) {
    return new Promise(function (resolve) {
      var scrim = document.createElement("div");
      scrim.className = "ck-modal-scrim";
      var box = document.createElement("div");
      box.className = "ck-modal";
      var h = document.createElement("h3");
      h.textContent = title;
      box.appendChild(h);
      var inputs = [];
      fields.forEach(function (f) {
        if (f.label) {
          var lbl = document.createElement("label");
          lbl.textContent = f.label;
          lbl.style.cssText = "display:block;font-size:11px;font-weight:600;color:#475569;margin-bottom:2px";
          box.appendChild(lbl);
        }
        var inp;
        if (f.type === "select" && f.options) {
          inp = document.createElement("select");
          inp.style.cssText = "width:100%;padding:6px 8px;border:1px solid #cfd9de;border-radius:6px;font-size:14px;margin-bottom:8px";
          f.options.forEach(function (o) {
            var opt = document.createElement("option");
            opt.value = o.value;
            opt.textContent = o.label;
            if (f.value != null && o.value === f.value) opt.selected = true;
            inp.appendChild(opt);
          });
        } else {
          inp = document.createElement("input");
          inp.type = f.type || "text";
          inp.placeholder = f.placeholder || "";
          if (f.value != null) inp.value = f.value;
        }
        box.appendChild(inp);
        inputs.push(inp);
      });
      var acts = document.createElement("div");
      acts.className = "ck-modal-actions";
      var cancel = document.createElement("button");
      cancel.className = "ck-modal-cancel";
      cancel.textContent = "Cancel";
      var ok = document.createElement("button");
      ok.className = "ck-modal-ok";
      ok.textContent = "OK";
      acts.appendChild(cancel);
      acts.appendChild(ok);
      box.appendChild(acts);
      scrim.appendChild(box);
      document.body.appendChild(scrim);
      if (inputs[0]) inputs[0].focus();
      function close(val) { document.body.removeChild(scrim); resolve(val); }
      cancel.onclick = function () { close(null); };
      scrim.onclick = function (e) { if (e.target === scrim) close(null); };
      ok.onclick = function () {
        var vals = inputs.map(function (i) { return i.value; });
        close(vals.length === 1 ? vals[0] : vals);
      };
      if (inputs.length) inputs[inputs.length - 1].addEventListener("keydown", function (e) {
        if (e.key === "Enter") ok.click();
      });
    });
  };

  var JSX_FILES = [
    "tweaks-panel.jsx", "components.jsx", "task-drawer.jsx", "quick-add.jsx",
    "palette.jsx", "view-week.jsx", "view-overview.jsx", "view-board.jsx",
    "view-table.jsx", "view-timeline.jsx",
    "view-agents.jsx", "activity.jsx", "app.jsx",
  ];

  var WS_STYLE = [ // palette/icon assignment by order; name overrides below
    { color: "#0891B2", icon: "deal" }, { color: "#0E7490", icon: "deal" },
    { color: "#155E75", icon: "deal" }, { color: "#475569", icon: "ops" },
    { color: "#7C3AED", icon: "ops" }, { color: "#0369A1", icon: "deal" },
  ];

  function el(tag, attrs, parent) {
    var node = document.createElement(tag);
    Object.assign(node, attrs || {});
    (parent || document.body).appendChild(node);
    return node;
  }

  // visible error banner — a blank page is not an error message
  window.onerror = function (msg, srcUrl, line) {
    var b = document.getElementById("bootfail") || el("div", { id: "bootfail" });
    b.style.cssText = "position:fixed;top:0;left:0;right:0;background:#E11D48;color:#fff;" +
      "padding:10px 16px;font:13px Arial;z-index:9999";
    b.textContent = "Cockpit error: " + msg + " (" + (srcUrl || "").split("/").pop() + ":" + line + ") — tell RC.";
  };

  function getToken() {
    return sessionStorage.getItem("cockpit_token") || "";
  }

  function authedFetch(path, opts) {
    opts = opts || {};
    var token = getToken();
    if (token) {
      opts.headers = Object.assign({ Authorization: "Bearer " + token }, opts.headers || {});
    }
    var base = window.COCKPIT_BASE || '';
    if (base && typeof path === 'string' && path.startsWith('/')) path = base + path;
    return fetch(path, opts);
  }

  function showLogin(message) {
    return new Promise(function (resolve) {
      var ov = el("div", { id: "login-ov" });
      ov.style.cssText = "position:fixed;inset:0;background:#0f2832;display:flex;align-items:center;justify-content:center;font-family:Arial";
      ov.innerHTML =
        '<div style="background:#fff;border-radius:10px;padding:28px 30px;width:380px">' +
        '<div style="font-size:17px;font-weight:bold;color:#0891B2;margin-bottom:4px">Repuro Cockpit</div>' +
        '<div style="font-size:12px;color:#64748b;margin-bottom:14px">' + (message || "Enter your access token") + "</div>" +
        '<input id="login-token" type="password" style="width:100%;padding:9px;border:1px solid #cfd9de;border-radius:6px;font-size:14px" placeholder="token">' +
        '<button id="login-go" style="margin-top:12px;width:100%;padding:9px;background:#0891B2;color:#fff;border:none;border-radius:6px;font-size:14px;cursor:pointer">Enter</button></div>';
      function go() {
        sessionStorage.setItem("cockpit_token", document.getElementById("login-token").value.trim());
        ov.remove(); resolve();
      }
      document.getElementById("login-go").onclick = go;
      document.getElementById("login-token").onkeyup = function (e) { if (e.key === "Enter") go(); };
      document.getElementById("login-token").focus();
    });
  }

  /* ---------- server -> prototype mapping ---------- */
  function tokensOf(resp) {
    return (resp || "").split(/[,;\/\s]+/).filter(Boolean);
  }

  function mapState(state) {
    var PEOPLE = {
      RD: { id: "RD", name: "Roman", full: "Roman Dobriakov", color: "#0891B2", role: "Co-founder" },
      FF: { id: "FF", name: "Flo", full: "Florian Fischer", color: "#A855F7", role: "Co-founder" },
    };
    var stageOf = {};
    (state.deals || []).forEach(function (d) { stageOf[d.codename] = d.stage; });

    var SPACES = (state.spaces || []).map(function (s) {
      return { id: s.id, name: s.name, slug: s.slug, sortMode: s.sort_mode };
    });
    var WORKSTREAMS = [], DELIVERABLES = [], TASKS = [], EXT = {};
    var wsIdx = 0;
    (state.spaces || []).forEach(function (space) {
      var live = (space.workstreams || []).filter(function (w) { return w.status !== "parked"; });
      var wsNum = 0;
      live.forEach(function (w) {
        var style = WS_STYLE[wsIdx % WS_STYLE.length];
        wsIdx++;
        wsNum++;
        var name = w.name.toLowerCase();
        var delivNum = 0;
        WORKSTREAMS.push({
          id: w.id, name: w.name, space: w.space_id, version: w.version,
          deal: w.deal_codename || null, dealStage: w.deal_stage || null,
          visibility: w.visibility || null, sortOrder: w.sort_order || 0,
          displayNum: String(wsNum),
          color: w.color || (name.indexOf("fundrais") >= 0 ? "#0891B2" : style.color),
          icon: name.indexOf("fundrais") >= 0 ? "raise"
            : (name.indexOf("admin") >= 0 || name.indexOf("general") >= 0 || name.indexOf("ops") >= 0) ? "ops" : "deal",
        });
        (w.deliverables || []).forEach(function (d) {
          if (d.staging) return;
          delivNum++;
          var liveTasks = (d.tasks || []).filter(function (t) { return !t.staging; });
          var dealCode = d.deal || w.deal_codename ||
            (liveTasks.map(function (t) { return t.deal; }).filter(Boolean)[0] || null);
          DELIVERABLES.push({
            id: d.id, ws: w.id, name: d.name, target: d.target_date || null, version: d.version,
            displayNum: wsNum + "." + delivNum,
            deal: dealCode ? { codename: dealCode, stage: w.deal_stage || stageOf[dealCode] || "?" } : null,
          });
          liveTasks.forEach(function (t) { TASKS.push(mapTask(t, d.id)); });
        });
      });
    });
    (state.standalone_tasks || []).forEach(function (t) {
      if (!t.staging) TASKS.push(mapTask(t, null));
    });
    // expand d- prereq refs into that deliverable's open task ids
    var tasksByDeliv = {};
    TASKS.forEach(function (t) { (tasksByDeliv[t.d] = tasksByDeliv[t.d] || []).push(t); });
    TASKS.forEach(function (t) {
      var out = [];
      t.prereqs.forEach(function (ref) {
        if (ref[0] === "d") {
          (tasksByDeliv[ref] || []).forEach(function (p) { if (p.status !== "done" && p.id !== t.id) out.push(p.id); });
        } else out.push(ref);
      });
      t.prereqs = out;
    });
    TASKS.forEach(function (t) {
      if (t.waiting && t.waiting.party) EXT[t.waiting.party] = { kind: t.waiting.type || "counterparty" };
    });

    var STAGE_LABEL = {
      indicative_offer: "Indicative offer", loi_signed: "LOI signed", valuation_rfi: "Valuation / RFI",
      dd: "Due diligence", spa: "SPA", signing: "Signing", nda: "NDA",
      initial_contact: "Initial contact", screening: "Screening",
      on_hold: "On hold", dead: "Dead", "?": "—",
    };
    return {
      TODAY: state.meta.today, PEOPLE: PEOPLE, EXT: EXT,
      SPACES: SPACES, WORKSTREAMS: WORKSTREAMS, DELIVERABLES: DELIVERABLES,
      TASKS: TASKS, STAGE_LABEL: STAGE_LABEL,
    };
  }

  function mapTask(t, delivId) {
    var owners = tokensOf(t.responsible).filter(function (x) { return x === "RD" || x === "FF"; });
    return {
      id: t.id, d: delivId, text: t.text, detail: t.detail || null,
      owners: owners, ownersRaw: t.responsible || "",
      status: t.status === "blocked" ? "open" : t.status,
      due: t.deadline || t.computed.effective_deadline || null,
      ownDue: t.deadline || null,
      priority: t.priority || null,
      pinned: !!t.pinned_today,
      waiting: t.status === "waiting" ? {
        party: t.waiting_on_party || "—", type: t.waiting_on_type || "counterparty",
        chase: t.next_chase_date || null,
      } : null,
      prereqs: (t.prereqs || []).map(function (p) { return p.ref; }),
      prereqsRaw: t.prereqs || [],
      // server-computed truth — components.jsx readiness()/risks()/recommendation() read these
      computedReadiness: (t.computed && t.computed.readiness) || "green",
      computedRisks: ((t.computed && t.computed.risks) || []).map(function (x) { return x === "at_risk" ? "at-risk" : x; }),
      computedRec: (t.computed && t.computed.recommendation) || "later",
      expectedBack: t.expected_back_by || null,
      execution: (t.execution === "agent_supervised" || t.execution === "agent_auto") ? "agent" : t.execution,
      executionRaw: t.execution,
      ac: t.acceptance_criteria || null, evidence: t.evidence || null,
      claimed_by: t.claimed_by || null, claim_expires_at: t.claim_expires_at || null,
      doneAt: t.done_at || null,
      kind: t.kind, dealCode: t.deal || null, version: t.version,
      inputFrom: t.input_from || null, inputQuestion: t.input_question || null,
      sortOrder: t.sort_order != null ? t.sort_order : 99999,
    };
  }

  /* ---------- write-through API ---------- */
  function toServerFields(t, changes) {
    var out = {};
    Object.keys(changes).forEach(function (k) {
      var v = changes[k];
      if (k === "due") out.deadline = v;
      else if (k === "pinned") out.pinned_today = !!v;
      else if (k === "owners") out.responsible = v.join(", ");
      else if (k === "prereqs") {
        var hardnessOf = {};
        (t.prereqsRaw || []).forEach(function (p) { hardnessOf[p.ref] = p.hardness; });
        out.prereqs = v.map(function (ref) { // preserve existing soft edges
          return { ref: ref, hardness: hardnessOf[ref] || "hard" };
        });
      }
      else if (k === "waiting") {
        if (v) {
          out.waiting_on_party = v.party; out.waiting_on_type = v.type; out.next_chase_date = v.chase;
        }
      } else if (k === "status") out.status = v;
      else if (k === "priority") out.priority = v;
      else if (k === "text") out.text = v;
      else if (k === "detail") out.detail = v;
      else if (k === "execution") out.execution = v === "agent" ? "agent_supervised" : v;
      else if (k === "ac") out.acceptance_criteria = v;
      else if (k === "inputFrom") out.input_from = v;
      else if (k === "inputQuestion") out.input_question = v;
      else if (k === "d") out.deliverable_id = v || null;
      else out[k] = v;
    });
    return out;
  }

  /* Full in-place re-sync: one task's change moves OTHER tasks' computed
     readiness/recommendation server-side (dependents). The bundle's views hold
     direct references to these arrays/objects (const bindings + window) — so we
     mutate contents, never replace containers. */
  async function refreshFromServer() {
    var r = await authedFetch("/api/state");
    if (!r.ok) return;
    var fresh = mapState(await r.json());
    if (!window.TASKS) { window.COCKPIT_DATA = fresh; return; } // pre-bundle

    function syncArray(liveArr, freshArr, liveIdx) {
      var freshById = {};
      freshArr.forEach(function (x) { freshById[x.id] = x; });
      // Remove items that no longer exist on server
      for (var i = liveArr.length - 1; i >= 0; i--) {
        if (!freshById[liveArr[i].id]) { delete liveIdx[liveArr[i].id]; liveArr.splice(i, 1); }
      }
      // Update properties in place (preserves object identity for React refs)
      liveArr.forEach(function (x) { Object.assign(x, freshById[x.id]); delete freshById[x.id]; });
      // Append new items
      Object.keys(freshById).forEach(function (id) { liveArr.push(freshById[id]); liveIdx[id] = freshById[id]; });
      // Reorder live array to match server order (critical for drag-reorder to take effect)
      var liveByIdNow = {};
      liveArr.forEach(function (x) { liveByIdNow[x.id] = x; });
      var j = 0;
      freshArr.forEach(function (fresh) {
        if (liveByIdNow[fresh.id]) { liveArr[j] = liveByIdNow[fresh.id]; j++; }
      });
    }
    syncArray(window.TASKS, fresh.TASKS, window.byTask);
    syncArray(window.DELIVERABLES, fresh.DELIVERABLES, window.byDeliv);
    syncArray(window.WORKSTREAMS, fresh.WORKSTREAMS, window.byWs);
    if (window.SPACES && fresh.SPACES) {
      syncArray(window.SPACES, fresh.SPACES, {});
      window.SPACES.forEach(function (s) { window.wsPerSpace[s.id] = []; });
      window.WORKSTREAMS.forEach(function (w) { if (window.wsPerSpace[w.space]) window.wsPerSpace[w.space].push(w); });
    }
    Object.assign(window.EXT, fresh.EXT);
    Object.keys(window.DEPENDENTS).forEach(function (k) { delete window.DEPENDENTS[k]; });
    window.TASKS.forEach(function (t) { window.DEPENDENTS[t.id] = []; });
    window.TASKS.forEach(function (t) {
      (t.prereqs || []).forEach(function (ref) {
        if (window.DEPENDENTS[ref]) window.DEPENDENTS[ref].push(t.id);
      });
    });
    if (window.rerender) window.rerender();
  }

  function conflictReload(r) {
    if (r.status === 409) {
      showToast("This item changed elsewhere (Flo or an agent). Reloading…", "info");
      setTimeout(function(){ location.reload(); }, 1200);
      throw new Error("409");
    }
    return r;
  }

  /* ---- undo: every save/create records its inverse; the topbar button pops it ---- */
  var undoStack = [];
  function inverseOf(t, changes) {
    var inv = {};
    Object.keys(changes).forEach(function (k) {
      if (k === "due") inv.due = t.ownDue;
      else if (k === "pinned") inv.pinned = t.pinned;
      else if (k === "owners") inv.owners = (t.owners || []).slice();
      else if (k === "prereqs") inv.prereqs = (t.prereqs || []).slice();
      else if (k === "waiting") { // set/changed waiting -> restore old state
        if (t.status === "waiting" && t.waiting) inv.waiting = Object.assign({}, t.waiting);
        else inv.status = t.status;
      } else if (k === "status") {
        if (t.status === "waiting" && t.waiting) inv.waiting = Object.assign({}, t.waiting);
        else inv.status = t.status;
      } else inv[k] = t[k];
    });
    return inv;
  }

  window.api = {
    undoDepth: function () { return undoStack.length; },
    async undo() {
      var e = undoStack.pop();
      if (!e) return;
      if (e.type === "delete") {
        await authedFetch("/api/task/" + e.id, { method: "DELETE" });
        await refreshFromServer();
      } else {
        var t = window.byTask[e.taskId];
        if (t) await this._save(t, e.fields);
      }
    },
    async save(t, changes) {
      undoStack.push({ taskId: t.id, fields: inverseOf(t, changes) });
      if (undoStack.length > 25) undoStack.shift();
      return this._save(t, changes);
    },
    async _save(t, changes) {
      if (changes.waiting && !changes.status) changes.status = "waiting";
      var body = Object.assign({ version: t.version }, toServerFields(t, changes));
      // leaving "waiting" clears the waiting metadata — stale party/chase
      // fields otherwise linger in the DB and resurface on the next wait
      if (t.status === "waiting" && changes.status && changes.status !== "waiting") {
        body.waiting_on_party = null; body.waiting_on_type = null;
        body.next_chase_date = null; body.expected_back_by = null;
      }
      var r = await authedFetch("/api/task/" + t.id, {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      conflictReload(r);
      if (!r.ok) { showToast("Save failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer(); // dependents' computed fields move too
    },
    async create(fields) {
      var body = toServerFields({}, fields);
      if (fields.d) body.deliverable_id = fields.d;
      var r = await authedFetch("/api/task", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!r.ok) { showToast("Create failed: " + (await r.text()).slice(0, 200), "err"); return null; }
      var created = await r.json();
      undoStack.push({ type: "delete", id: created.id });
      await refreshFromServer();
      return window.byTask[created.id] || null;
    },
    async deleteTask(t) {
      if (!confirm('Delete "' + t.text + '"? Dependents lose this gate. No undo.')) return;
      var r = await authedFetch("/api/task/" + t.id, { method: "DELETE" });
      if (!r.ok) { showToast("Delete failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
      if (window.closeDrawer) window.closeDrawer();
    },
    async verdict(t, action, comment) { // approve | reject
      var r = await authedFetch("/api/task/" + t.id + "/" + action, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(action === "reject" ? { comment: comment || "" } : {}),
      });
      conflictReload(r);
      if (!r.ok) { showToast("Failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
    },
    /* Deal playbook: one deliverable + the standard arc, prereq-chained. */
    async spinupDeal(wsId, codename, steps, target) {
      var r = await authedFetch("/api/deliverable", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workstream_id: wsId, name: codename + " — Deal", target_date: target || null, source: "playbook" }),
      });
      if (!r.ok) { showToast("Playbook failed: " + (await r.text()).slice(0, 200), "err"); return; }
      var delivId = (await r.json()).id;
      var prev = null;
      for (var i = 0; i < steps.length; i++) {
        var body = { deliverable_id: delivId, text: steps[i], kind: "workplan", deal: codename, responsible: "RD" };
        if (prev) body.prereqs = [{ ref: prev, hardness: "hard" }];
        var tr = await authedFetch("/api/task", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        if (!tr.ok) { showToast("Playbook task failed: " + (await tr.text()).slice(0, 200), "err"); return; }
        prev = (await tr.json()).id;
      }
      location.reload(); // bulk change — clean resync beats incremental bookkeeping
    },
    async createDeliv(wsId, name, target) {
      var r = await authedFetch("/api/deliverable", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workstream_id: wsId, name: name, target_date: target || null }),
      });
      if (!r.ok) { showToast("Create failed: " + (await r.text()).slice(0, 200), "err"); return null; }
      var created = await r.json();
      await refreshFromServer();
      return created;
    },
    async saveDeliv(d, fields) { // {name?, target_date?}
      var r = await authedFetch("/api/deliverable/" + d.id, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ version: d.version }, fields)),
      });
      conflictReload(r);
      if (!r.ok) { showToast("Save failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
    },
    async deleteDeliv(d) {
      if (!confirm('Delete "' + d.name + '"? Tasks will become standalone. No undo.')) return;
      var r = await authedFetch("/api/deliverable/" + d.id, { method: "DELETE" });
      if (!r.ok) { showToast("Delete failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
      if (window.closeDrawer) window.closeDrawer();
    },
    async saveWs(w, fields) {
      var r = await authedFetch("/api/workstream/" + w.id, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ version: w.version }, fields)),
      });
      conflictReload(r);
      if (!r.ok) { showToast("Save failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
    },
    async saveDeal(codename, fields) {
      var r = await authedFetch("/api/deal/" + codename, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      });
      if (!r.ok) { showToast("Save failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
    },
    async reorderDelivs(delivIds) {
      var r = await authedFetch("/api/deliverables/reorder", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deliverable_ids: delivIds }),
      });
      if (!r.ok) { showToast("Reorder failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
    },
    async reorder(taskIds) {
      // taskIds: array of "t-N" strings in new display order
      var r = await authedFetch("/api/tasks/reorder", {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_ids: taskIds }),
      });
      if (!r.ok) { showToast("Reorder failed: " + (await r.text()).slice(0, 200), "err"); return; }
      await refreshFromServer();
    },
    reload: function () { location.reload(); },
  };

  /* ---------- boot ---------- */
  async function fetchState() {
    var r = await authedFetch("/api/state");
    if (r.status === 401) return null;
    if (!r.ok) throw new Error("state fetch failed: " + r.status);
    return r.json();
  }

  async function boot() {
    var state = null;
    var base = window.COCKPIT_BASE || '';
    // Caddy path: plain fetch — no Authorization header so browser sends cached Basic auth
    try {
      var r = await fetch((base || '') + '/api/state');
      if (r.ok) { state = await r.json(); sessionStorage.removeItem("cockpit_token"); }
    } catch (e) {}
    // Direct-access fallback: stored Bearer token
    if (!state && getToken()) state = await fetchState();
    while (!state) {
      await showLogin(state === null && getToken() ? "Invalid token — try again" : undefined);
      state = await fetchState();
    }
    window.COCKPIT_DATA = mapState(state);
    if (state.principal && state.principal.id && !sessionStorage.getItem("cockpit_person")) {
      var pMap = {rd: "RD", ff: "FF"};
      if (pMap[state.principal.id]) sessionStorage.setItem("cockpit_person", pMap[state.principal.id]);
    }

    var sources = await Promise.all(JSX_FILES.map(function (f) {
      return fetch((window.COCKPIT_BASE || '') + "/static/js/" + f, { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("missing " + f);
        return r.text();
      });
    }));
    var code = sources.map(function (s, i) { return "// ==== " + JSX_FILES[i] + "\n" + s; }).join("\n;\n");
    var compiled = Babel.transform(code, { presets: ["react"], sourceMaps: false }).code;
    (0, eval)(compiled); // single ordered bundle — no script-tag ordering races
  }

  boot().catch(function (e) { window.onerror(e.message || String(e), "boot.js", 0); });
})();
