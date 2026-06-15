// ─── DR-M22 — Deal History (wireframe) ─────────────────────────────────────
// Dependencies: DATA global (deal, notes)
// Exports: renderDealHistory() → HTML string

function _dhFmtDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function _dhDaysSince(iso) {
  if (!iso) return null;
  const now = new Date();
  const then = new Date(iso);
  return Math.floor((now - then) / 86400000);
}

function renderTimeline(currentStage, stages, daysInStage) {
  const currentIdx = stages.findIndex(s => s.key === currentStage);

  const dots = stages.map((stage, i) => {
    let dotClass, dotSymbol;
    if (i < currentIdx) {
      dotClass = "dh-dot-past";
      dotSymbol = "●";
    } else if (i === currentIdx) {
      dotClass = "dh-dot-active";
      dotSymbol = "●";
    } else {
      dotClass = "dh-dot-future";
      dotSymbol = "○";
    }

    const dateLabel = stage.date
      ? `<div class="dh-tl-date">${stage.date}</div>`
      : `<div class="dh-tl-date dh-tl-empty">—</div>`;

    const durationLabel = stage.duration
      ? `<div class="dh-tl-dur">${stage.duration}</div>`
      : `<div class="dh-tl-dur dh-tl-empty"></div>`;

    return `
      <div class="dh-tl-node">
        <div class="dh-tl-dot ${dotClass}">${dotSymbol}</div>
        <div class="dh-tl-label ${i === currentIdx ? "dh-tl-label-active" : ""}">${stage.label}</div>
        ${durationLabel}
        ${dateLabel}
      </div>
      ${i < stages.length - 1 ? `<div class="dh-tl-line ${i < currentIdx ? "dh-line-past" : "dh-line-future"}"></div>` : ""}
    `;
  }).join("");

  return `
    <div class="dh-section-block">
      <div class="dh-block-title">STAGE TIMELINE</div>
      <div class="dh-timeline-wrap">
        ${dots}
      </div>
      <div class="dh-tl-legend">
        <span class="dh-leg-item"><span style="color:#16a34a">●</span> Completed</span>
        <span class="dh-leg-item"><span style="color:#0891B2">●</span> Active (${daysInStage}d in stage)</span>
        <span class="dh-leg-item"><span style="color:#adb5bd">○</span> Upcoming</span>
      </div>
    </div>
  `;
}

function renderKeyDates(deal) {
  const lastContactDays = _dhDaysSince(deal.last_contact_at);
  const ndaDays = _dhDaysSince("2025-12-04");

  const rows = [
    ["First contact",    "20.11.2025",                      ""],
    ["NDA signed",       "04.12.2025",                      ""],
    ["Financials recv.", "15.02.2026",                      ""],
    ["First NBO sent",   "03.04.2026",                      ""],
    ["Last contact",     _dhFmtDate(deal.last_contact_at), `<span class="dh-badge-warn">${lastContactDays}d ago</span>`],
    ["Days since NDA",   `${ndaDays}d`,                     ""],
  ];

  const rowsHtml = rows.map(([label, value, badge]) => `
    <tr>
      <td class="dh-kd-label">${label}</td>
      <td class="dh-kd-value">${value} ${badge}</td>
    </tr>
  `).join("");

  return `
    <div class="dh-section-block">
      <div class="dh-block-title">KEY DATES</div>
      <table class="dh-kd-table">
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

function renderActivityFeed(notes) {
  const TYPE_META = {
    email:   { icon: "✉",  label: "Email",   cls: "dh-type-email"   },
    meeting: { icon: "📞", label: "Meeting", cls: "dh-type-meeting" },
    note:    { icon: "📝", label: "Note",    cls: "dh-type-note"    },
    stage:   { icon: "▶",  label: "Stage",   cls: "dh-type-stage"   },
  };

  const rowsHtml = notes.map(n => {
    const meta = TYPE_META[n.type] || { icon: "•", label: n.type, cls: "" };
    return `
      <tr class="dh-feed-row">
        <td class="dh-feed-date">${_dhFmtDate(n.date)}</td>
        <td class="dh-feed-type"><span class="dh-type-badge ${meta.cls}">${meta.icon} ${meta.label}</span></td>
        <td class="dh-feed-summary">${n.summary}</td>
      </tr>
    `;
  }).join("");

  return `
    <div class="dh-section-block">
      <div class="dh-block-title">RECENT ACTIVITY</div>
      <table class="dh-feed-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Summary</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

function renderOpenActions() {
  const actions = [
    { priority: "High",   text: "Respond to salary counter-proposal",  owner: "Roman",  due: "20.05.2026", overdue: true  },
    { priority: "High",   text: "Request updated BWA Q1/2026",          owner: "Seller", due: "25.05.2026", overdue: false },
    { priority: "Medium", text: "Schedule on-site visit",               owner: "Roman",  due: "30.05.2026", overdue: false },
    { priority: "Low",    text: "Draft LOI heads of terms",             owner: "Roman",  due: "15.06.2026", overdue: false },
  ];

  const PRIO_CLS = { High: "dh-prio-high", Medium: "dh-prio-medium", Low: "dh-prio-low" };

  const rowsHtml = actions.map(a => `
    <tr class="dh-action-row">
      <td><span class="dh-prio-badge ${PRIO_CLS[a.priority]}">${a.priority}</span></td>
      <td class="dh-action-text">${a.text}</td>
      <td class="dh-action-owner">${a.owner}</td>
      <td class="dh-action-due ${a.overdue ? "dh-overdue" : ""}">${a.due}${a.overdue ? " ⚠" : ""}</td>
    </tr>
  `).join("");

  return `
    <div class="dh-section-block">
      <div class="dh-block-title">OPEN ACTIONS / BLOCKERS</div>
      <table class="dh-action-table">
        <thead>
          <tr>
            <th>Priority</th>
            <th>Action</th>
            <th>Owner</th>
            <th>Due</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

function renderContactLog() {
  const channels = [
    { channel: "Email",   count: 12, last: "14.05.2026", next: "—"          },
    { channel: "Meeting", count: 4,  last: "10.05.2026", next: "22.05.2026" },
    { channel: "Phone",   count: 3,  last: "05.05.2026", next: "—"          },
  ];

  const rowsHtml = channels.map(c => `
    <tr>
      <td class="dh-cl-channel">${c.channel}</td>
      <td class="dh-cl-count">${c.count}</td>
      <td class="dh-cl-last">${c.last}</td>
      <td class="dh-cl-next ${c.next !== "—" ? "dh-cl-next-set" : ""}">${c.next}</td>
    </tr>
  `).join("");

  return `
    <div class="dh-section-block">
      <div class="dh-block-title">CONTACT LOG</div>
      <table class="dh-cl-table">
        <thead>
          <tr>
            <th>Channel</th>
            <th>Count</th>
            <th>Last</th>
            <th>Next planned</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;
}

function renderDealHistory() {
  const MOCK = {
    deal: {
      name: "HWV GmbH",
      deal_stage: "offer_negotiation",
      stage_entered_at: "2026-04-28",
      last_contact_at: "2026-05-14",
      days_in_stage: 24,
    },
    notes: [
      { date: "2026-05-14", type: "email",   summary: "Follow-up on counter-offer" },
      { date: "2026-05-10", type: "meeting", summary: "Management call — discussed earn-out structure" },
      { date: "2026-05-02", type: "note",    summary: "Seller flexible on trigger metric (EBIT vs. Umsatz)" },
      { date: "2026-04-28", type: "stage",   summary: "Moved to offer_negotiation" },
      { date: "2026-04-18", type: "email",   summary: "Received counter-proposal from seller" },
      { date: "2026-04-03", type: "stage",   summary: "First NBO sent" },
      { date: "2026-03-20", type: "meeting", summary: "Intro call with GF — good chemistry, open on timing" },
      { date: "2026-03-10", type: "email",   summary: "Sent teaser + NDA request" },
      { date: "2026-02-27", type: "stage",   summary: "Moved to valuation" },
      { date: "2026-02-15", type: "note",    summary: "Financials received (BWA 2023–2025 + SuSa)" },
      { date: "2026-01-12", type: "meeting", summary: "Advisor call — aligned on process timeline" },
      { date: "2025-12-04", type: "stage",   summary: "NDA signed" },
      { date: "2025-11-20", type: "email",   summary: "Initial outreach via cold email" },
      { date: "2025-11-20", type: "stage",   summary: "Deal created — stage: sourcing" },
    ],
  };

  const STAGES = [
    { key: "sourcing",           label: "Sourcing",    date: "20.11.2025", duration: "14d" },
    { key: "nda",                label: "NDA",         date: "04.12.2025", duration: "85d" },
    { key: "valuation",          label: "Valuation",   date: "27.02.2026", duration: "35d" },
    { key: "offer_negotiation",  label: "Offer",       date: "03.04.2026", duration: "24d+" },
    { key: "loi",                label: "LOI",         date: null,         duration: null   },
    { key: "due_diligence",      label: "DD",          date: null,         duration: null   },
    { key: "closing",            label: "Closing",     date: null,         duration: null   },
  ];

  const deal  = (typeof DATA !== "undefined" && DATA && DATA.deal)  ? DATA.deal  : MOCK.deal;
  const notes = (typeof DATA !== "undefined" && DATA && DATA.notes) ? DATA.notes : MOCK.notes;

  const css = `
    <style>
      .dh-wrap {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
        color: #1e293b;
        background: #f8fafc;
        padding: 16px;
        border-radius: 6px;
        max-width: 900px;
      }

      /* Section header */
      .dh-header {
        background: #0891B2;
        color: #fff;
        padding: 10px 16px;
        border-radius: 4px 4px 0 0;
        font-size: 14px;
        font-weight: 700;
        letter-spacing: 0.04em;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .dh-header .dh-wf-label {
        font-size: 10px;
        font-weight: 400;
        opacity: 0.75;
        background: rgba(255,255,255,0.15);
        padding: 2px 7px;
        border-radius: 3px;
      }

      /* Section blocks */
      .dh-section-block {
        background: #fff;
        border: 1px solid #e2e8f0;
        border-top: none;
        padding: 14px 16px;
      }
      .dh-section-block + .dh-section-block {
        border-top: none;
      }
      .dh-section-block:last-child {
        border-radius: 0 0 4px 4px;
      }

      .dh-block-title {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.08em;
        color: #6c757d;
        text-transform: uppercase;
        margin-bottom: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid #f1f5f9;
      }

      /* ---- TIMELINE ---- */
      .dh-timeline-wrap {
        display: flex;
        align-items: center;
        gap: 0;
        overflow-x: auto;
        padding: 8px 0 4px;
      }
      .dh-tl-node {
        display: flex;
        flex-direction: column;
        align-items: center;
        min-width: 80px;
        flex-shrink: 0;
      }
      .dh-tl-dot {
        font-size: 20px;
        line-height: 1;
      }
      .dh-dot-past   { color: #16a34a; }
      .dh-dot-future { color: #adb5bd; }
      .dh-dot-active {
        color: #0891B2;
        animation: dh-pulse 1.8s infinite;
        display: inline-block;
      }
      @keyframes dh-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.6; transform: scale(1.2); }
      }
      .dh-tl-label {
        font-size: 11px;
        font-weight: 600;
        color: #64748b;
        margin-top: 4px;
        text-align: center;
      }
      .dh-tl-label-active {
        color: #0891B2;
        font-weight: 700;
      }
      .dh-tl-dur {
        font-size: 10px;
        color: #94a3b8;
        margin-top: 2px;
      }
      .dh-tl-date {
        font-size: 10px;
        color: #adb5bd;
        margin-top: 1px;
      }
      .dh-tl-empty { visibility: hidden; }
      .dh-tl-line {
        flex: 1;
        height: 2px;
        min-width: 20px;
        margin-top: -26px;
        align-self: flex-start;
        margin-top: 9px;
      }
      .dh-line-past   { background: #16a34a; }
      .dh-line-future { background: #e2e8f0; }

      .dh-tl-legend {
        display: flex;
        gap: 16px;
        margin-top: 10px;
        font-size: 11px;
        color: #6c757d;
      }
      .dh-leg-item { display: flex; align-items: center; gap: 4px; }

      /* ---- KEY DATES ---- */
      .dh-kd-table { width: 100%; border-collapse: collapse; }
      .dh-kd-label {
        color: #6c757d;
        padding: 4px 0;
        width: 160px;
        font-size: 12px;
      }
      .dh-kd-value {
        font-weight: 600;
        font-size: 12px;
        padding: 4px 0;
      }
      .dh-badge-warn {
        background: #fef3c7;
        color: #92400e;
        border-radius: 3px;
        padding: 1px 6px;
        font-size: 10px;
        font-weight: 600;
        margin-left: 6px;
      }

      /* ---- ACTIVITY FEED ---- */
      .dh-feed-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .dh-feed-table th {
        text-align: left;
        color: #6c757d;
        font-weight: 600;
        font-size: 11px;
        padding: 4px 8px 6px 0;
        border-bottom: 1px solid #f1f5f9;
      }
      .dh-feed-row td {
        padding: 5px 8px 5px 0;
        border-bottom: 1px solid #f8fafc;
        vertical-align: top;
      }
      .dh-feed-row:hover td { background: #f8fafc; }
      .dh-feed-date { color: #64748b; white-space: nowrap; width: 90px; }
      .dh-feed-type { width: 100px; }
      .dh-feed-summary { color: #1e293b; }

      .dh-type-badge {
        display: inline-block;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 3px;
      }
      .dh-type-email   { background: #eff6ff; color: #1d4ed8; }
      .dh-type-meeting { background: #f0fdf4; color: #166534; }
      .dh-type-note    { background: #fefce8; color: #713f12; }
      .dh-type-stage   { background: #f5f3ff; color: #5b21b6; }

      /* ---- OPEN ACTIONS ---- */
      .dh-action-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .dh-action-table th {
        text-align: left;
        color: #6c757d;
        font-weight: 600;
        font-size: 11px;
        padding: 4px 8px 6px 0;
        border-bottom: 1px solid #f1f5f9;
      }
      .dh-action-row td {
        padding: 5px 8px 5px 0;
        border-bottom: 1px solid #f8fafc;
        vertical-align: middle;
      }
      .dh-action-row:hover td { background: #f8fafc; }
      .dh-action-text  { color: #1e293b; }
      .dh-action-owner { color: #64748b; white-space: nowrap; }
      .dh-action-due   { color: #64748b; white-space: nowrap; }
      .dh-action-due.dh-overdue { color: #dc2626; font-weight: 600; }

      .dh-prio-badge {
        display: inline-block;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 3px;
        white-space: nowrap;
      }
      .dh-prio-high   { background: #fee2e2; color: #991b1b; }
      .dh-prio-medium { background: #fef3c7; color: #92400e; }
      .dh-prio-low    { background: #f1f5f9; color: #475569; }

      /* ---- CONTACT LOG ---- */
      .dh-cl-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
      }
      .dh-cl-table th {
        text-align: left;
        color: #6c757d;
        font-weight: 600;
        font-size: 11px;
        padding: 4px 8px 6px 0;
        border-bottom: 1px solid #f1f5f9;
      }
      .dh-cl-table td {
        padding: 5px 8px 5px 0;
        border-bottom: 1px solid #f8fafc;
      }
      .dh-cl-channel { font-weight: 600; color: #1e293b; }
      .dh-cl-count   { color: #0891B2; font-weight: 700; }
      .dh-cl-last    { color: #64748b; }
      .dh-cl-next    { color: #adb5bd; }
      .dh-cl-next-set { color: #0891B2; font-weight: 600; }
    </style>
  `;

  const header = `
    <div class="dh-header">
      DEAL HISTORY — ${deal.name || "HWV GmbH"}
      <span class="dh-wf-label">[Wireframe — mock data]</span>
    </div>
  `;

  const body = [
    renderTimeline(deal.deal_stage, STAGES, deal.days_in_stage),
    renderKeyDates(deal),
    renderActivityFeed(notes),
    renderOpenActions(),
    renderContactLog(),
  ].join("");

  return `<div class="dh-wrap">${css}${header}${body}</div>`;
}
