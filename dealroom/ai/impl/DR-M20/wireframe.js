// ─── DR-M20 Wireframe Render Functions ───────────────────────────────────────
// Sections: Business Model (6) + Investment Thesis & Fit (9)
// Pattern: returns HTML string, called from showSection() switch.
// Data: global DATA object (DATA.deal, DATA.financials, DATA.customers, DATA.commercial)
// All values K€, German number format where applicable.
// Placeholder values are clearly labelled [PLACEHOLDER].
//
// Integration into showSection():
//   case 'business_model':  area.innerHTML = bc + renderBusinessModel(); break;
//   case 'thesis':          area.innerHTML = bc + renderThesis(); break;
//
// Integration into renderSidebar() / sidebar items:
//   sidebarItem('business_model', 'Business Model', '6')
//   sidebarItem('thesis', 'Thesis & Fit', '9')

// ─── Section 6: Business Model ───────────────────────────────────────────────

function renderBusinessModel() {
  const d   = DATA.deal       || {};
  const com = DATA.commercial || {};

  // ── helpers ──────────────────────────────────────────────────────────────
  const ph = (text) => `<span style="color:#94a3b8;font-style:italic">${text}</span>`;

  // Section card wrapper
  function card(title, body, opts) {
    opts = opts || {};
    const mb    = opts.mb    != null ? opts.mb    : 20;
    const extra = opts.extra || '';
    return `
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:${mb}px;overflow:hidden${extra}">
  <div style="background:#0891B2;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">
    ${title}
  </div>
  <div style="padding:16px">
    ${body}
  </div>
</div>`;
  }

  // KPI card
  function kpiCard(label, value, sub, highlight) {
    const bg     = highlight ? '#f0fdf4' : '#f8fafc';
    const border = highlight ? '#86efac' : '#e2e8f0';
    const vColor = highlight ? '#15803d' : '#1e293b';
    return `
<div style="background:${bg};border:1px solid ${border};border-radius:8px;padding:12px 16px;min-width:140px;flex:1">
  <div style="font-size:10px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px">${label}</div>
  <div style="font-size:20px;font-weight:700;color:${vColor}">${value}</div>
  ${sub ? `<div style="font-size:10px;color:#94a3b8;margin-top:2px">${sub}</div>` : ''}
</div>`;
  }

  // Revenue model checkbox row
  function revenueCheckbox(label, checked, note) {
    const icon  = checked
      ? `<span style="color:#10b981;font-size:16px;margin-right:8px">&#9745;</span>`
      : `<span style="color:#cbd5e1;font-size:16px;margin-right:8px">&#9744;</span>`;
    const noteHtml = note
      ? `<span style="font-size:11px;color:#94a3b8;margin-left:8px">${note}</span>`
      : '';
    return `
<div style="display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #f1f5f9">
  ${icon}
  <span style="font-size:13px;color:#334155">${label}</span>
  ${noteHtml}
</div>`;
  }

  // ── 1. Company Description ────────────────────────────────────────────────
  const companyName = esc(d.company_name || d.code_name || '[Company Name]');
  const sector      = esc(com.sector || '[Sector]');
  const location    = esc(com.location || '[Location]');

  const descBody = `
<div style="font-size:13px;color:#334155;line-height:1.7;margin-bottom:12px">
  <strong>${companyName}</strong> is a ${sector} distributor based in ${location}.
  ${ph('[PLACEHOLDER — pull from DATA.commercial.description or draft from overview.description. Describe core business in 2–3 sentences: what they sell, who they serve, market position.]')}
</div>
<div style="background:#fefce8;border:1px solid #fef08a;border-radius:6px;padding:8px 12px;font-size:11px;color:#854d0e">
  Edit note: bind to <code>DATA.commercial.description</code> or <code>DATA.overview.description</code>.
  Editable via contenteditable in serve mode.
</div>`;

  // ── 2. Service Portfolio table ────────────────────────────────────────────
  // Placeholder rows — replace with DATA.commercial.service_lines when backend supplies it
  const serviceRows = [
    { line:'Medical Distribution', desc:'Core product distribution to hospitals and clinics', share:'65%', recurring:true  },
    { line:'Equipment Rental',     desc:'Short- and long-term device leasing',               share:'25%', recurring:true  },
    { line:'Service & Repair',     desc:'Maintenance contracts and on-call technicians',     share:'10%', recurring:false },
  ];

  let serviceTable = `
<table style="width:100%;border-collapse:collapse;font-size:13px">
  <thead>
    <tr style="border-bottom:2px solid #e2e8f0">
      <th style="text-align:left;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">Service Line</th>
      <th style="text-align:left;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">Description</th>
      <th style="text-align:center;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">Rev. Share</th>
      <th style="text-align:center;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">Recurring</th>
    </tr>
  </thead>
  <tbody>`;

  for (const row of serviceRows) {
    const recBadge = row.recurring
      ? `<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600">Yes</span>`
      : `<span style="background:#f3f4f6;color:#6b7280;padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600">No</span>`;
    serviceTable += `
    <tr style="border-bottom:1px solid #f1f5f9">
      <td style="padding:7px 10px;font-weight:600;color:#1e293b">${esc(row.line)}</td>
      <td style="padding:7px 10px;color:#475569">${ph('[PLACEHOLDER]')} ${esc(row.desc)}</td>
      <td style="padding:7px 10px;text-align:center;font-weight:700;color:#0891B2">${esc(row.share)}</td>
      <td style="padding:7px 10px;text-align:center">${recBadge}</td>
    </tr>`;
  }

  serviceTable += `
  </tbody>
</table>
<div style="margin-top:8px;font-size:11px;color:#94a3b8">
  ${ph('[PLACEHOLDER] — bind to DATA.commercial.service_lines [ {label, description, rev_share_pct, recurring} ]. Mock data shown.')}
</div>`;

  // ── 3. Key KPIs ──────────────────────────────────────────────────────────
  // Pull from DATA.customers.metrics (latest year) + DATA.commercial where available
  const cust    = DATA.customers || {};
  const metrics = cust.metrics   || {};
  const years   = Object.keys(metrics).sort();
  const latest  = years.length ? years[years.length - 1] : null;
  const m       = latest ? (metrics[latest] || {}) : {};

  const recurringPct  = m.recurring_rev_share != null
    ? (m.recurring_rev_share > 1 ? m.recurring_rev_share.toFixed(0) : (m.recurring_rev_share * 100).toFixed(0)) + '%'
    : ph('[PLACEHOLDER ~45%]');
  const totalCustomers = m.total_customers != null ? m.total_customers : ph('[PLACEHOLDER ~120]');
  const avgOrderVal    = com.avg_order_value_k != null ? com.avg_order_value_k + ' K€' : ph('[PLACEHOLDER ~12 K€]');
  const orderBacklog   = com.order_backlog_k   != null ? com.order_backlog_k   + ' K€' : ph('[PLACEHOLDER ~2.100 K€]');
  const contractBase   = m.total_customers    != null ? m.total_customers + ' active' : ph('[PLACEHOLDER 120 active]');

  const kpiBody = `
<div style="display:flex;gap:12px;flex-wrap:wrap">
  ${kpiCard('Recurring Revenue %', recurringPct, latest || 'latest year', m.recurring_rev_share != null && m.recurring_rev_share * 100 >= 40)}
  ${kpiCard('Avg. Order Value', avgOrderVal, ph('[PLACEHOLDER — DATA.commercial.avg_order_value_k]'))}
  ${kpiCard('Order Backlog', orderBacklog, ph('[PLACEHOLDER — DATA.commercial.order_backlog_k]'))}
  ${kpiCard('Active Contract Base', contractBase, ph('[PLACEHOLDER — DATA.customers.metrics.total_customers]'))}
</div>
<div style="margin-top:12px;font-size:11px;color:#94a3b8">
  ${ph('[PLACEHOLDER] Recurring % pulled from DATA.customers.metrics.recurring_rev_share. Backlog + order value require new fields in DATA.commercial.')}
</div>`;

  // ── 4. Revenue Model ─────────────────────────────────────────────────────
  const revModelBody = `
${revenueCheckbox('Product distribution', true,  ph('[PLACEHOLDER — dominant channel, ~65% of rev]'))}
${revenueCheckbox('Service contracts (recurring)', true,  ph('[PLACEHOLDER — rental + maintenance, ~35%]'))}
${revenueCheckbox('Project-based / one-off', false, ph('[PLACEHOLDER — not primary]'))}
${revenueCheckbox('Consumables / replenishment', false, ph('[PLACEHOLDER — evaluate from RFI data]'))}
<div style="margin-top:10px;font-size:11px;color:#94a3b8">
  ${ph('[PLACEHOLDER] Checkboxes are static wireframe. Backend: boolean flags in DATA.commercial.revenue_model { distribution, service_contracts, project_based, consumables }.')}
</div>`;

  // ── assemble ─────────────────────────────────────────────────────────────
  let h = '';
  h += card('Company Description',  descBody);
  h += card('Service Portfolio',    serviceTable);
  h += card('Key KPIs',             kpiBody);
  h += card('Revenue Model',        revModelBody, { mb: 0 });

  return h;
}

// ─── Section 9: Investment Thesis & Fit ──────────────────────────────────────
// IC memo: SWOT (ch.1) + Kriterienkatalog (ch.2) + Rationale (ch.9)

function renderThesis() {
  const d   = DATA.deal       || {};
  const com = DATA.commercial || {};

  // ── helpers ──────────────────────────────────────────────────────────────
  const ph = (text) => `<span style="color:#94a3b8;font-style:italic">${text}</span>`;

  function card(title, body, opts) {
    opts = opts || {};
    const mb = opts.mb != null ? opts.mb : 20;
    return `
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:${mb}px;overflow:hidden">
  <div style="background:#0891B2;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">
    ${title}
  </div>
  <div style="padding:16px">
    ${body}
  </div>
</div>`;
  }

  // Coloured dot for scorecard
  function scoreDot(color) {
    const hex = { green:'#10b981', yellow:'#f59e0b', red:'#ef4444' }[color] || '#e2e8f0';
    return `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${hex};box-shadow:0 0 0 2px ${hex}33"></span>`;
  }

  // Trend arrow
  function trend(direction) {
    const map = { up:'&#8593;', flat:'&#8594;', down:'&#8595;' };
    const col = { up:'#10b981', flat:'#6b7280', down:'#ef4444' };
    return `<span style="color:${col[direction]||'#6b7280'};font-weight:700">${map[direction]||'&#8594;'}</span>`;
  }

  // ── 1. SWOT Matrix ───────────────────────────────────────────────────────
  // SWOT is stored as a JSON column on the deals table, served as DATA.deal.swot_json.
  // NOT under DATA.commercial — do not read from com.swot.
  const swot = (d.swot_json) ? d.swot_json : null;

  function swotQuadrant(label, color, bullets, bgColor) {
    const items = bullets.map(b => `<li style="margin-bottom:4px">${b}</li>`).join('');
    return `
<div style="background:${bgColor};border-radius:6px;padding:12px 14px;min-height:120px">
  <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:${color};margin-bottom:8px">${label}</div>
  <ul style="margin:0;padding-left:16px;font-size:13px;color:#334155;line-height:1.6">
    ${items}
  </ul>
</div>`;
  }

  const swotStrengths    = swot ? swot.strengths    : ['High recurring revenue base', 'Regional market leader', 'Strong EBITDA margins'];
  const swotWeaknesses   = swot ? swot.weaknesses   : ['Owner-manager dependency', 'Single location', 'Key man concentration risk'];
  const swotOpportunities = swot ? swot.opportunities : ['Cross-sell / upsell potential', 'Digitisation of logistics', 'Add-on M&A platform'];
  const swotThreats      = swot ? swot.threats      : ['Reimbursement rate cuts', 'Amazon / e-commerce threat', 'Margin pressure from suppliers'];

  // Mark placeholder bullets visually if from mock
  function maybePh(arr, isPlaceholder) {
    if (!isPlaceholder) return arr;
    return arr.map(s => `${s} <em style="font-size:10px;color:#94a3b8">[PLACEHOLDER]</em>`);
  }
  const isPlaceholder = !swot;

  const swotBody = `
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
  ${swotQuadrant('Strengths',     '#15803d', maybePh(swotStrengths,     isPlaceholder), '#dcfce7')}
  ${swotQuadrant('Weaknesses',    '#92400e', maybePh(swotWeaknesses,    isPlaceholder), '#fef3c7')}
  ${swotQuadrant('Opportunities', '#1e40af', maybePh(swotOpportunities, isPlaceholder), '#dbeafe')}
  ${swotQuadrant('Threats',       '#991b1b', maybePh(swotThreats,       isPlaceholder), '#fee2e2')}
</div>
${isPlaceholder ? `<div style="margin-top:10px;font-size:11px;color:#94a3b8">${ph('[PLACEHOLDER] Bind to DATA.deal.swot_json { strengths[], weaknesses[], opportunities[], threats[] } — JSON column on deals table. Mock data shown.')}</div>` : ''}`;

  // ── 2. Scorecard ─────────────────────────────────────────────────────────
  // Pull live values where available; fall back to placeholder
  const fin     = DATA.financials || {};
  const pnl     = fin.pnl || {};
  const custM   = (DATA.customers || {}).metrics || {};
  const lyears  = Object.keys(custM).sort();
  const ly      = lyears.length ? lyears[lyears.length - 1] : null;
  const lm      = ly ? (custM[ly] || {}) : {};

  // Revenue CAGR — compute from financials if available, else placeholder
  let cagr = null;
  if (fin.cagr_pct != null) cagr = fin.cagr_pct.toFixed(1) + '%';
  else if (com.revenue_cagr_pct != null) cagr = com.revenue_cagr_pct.toFixed(1) + '%';

  // EBITDA margin — latest year
  let ebitdaMargin = null;
  const pnlYears = Object.keys(pnl).sort();
  if (pnlYears.length) {
    const lpnl = pnl[pnlYears[pnlYears.length - 1]] || {};
    if (lpnl.ebitda_margin_pct != null) ebitdaMargin = lpnl.ebitda_margin_pct.toFixed(1) + '%';
  }

  // Recurring %
  let recurringPct = null;
  if (lm.recurring_rev_share != null) {
    recurringPct = lm.recurring_rev_share > 1
      ? lm.recurring_rev_share.toFixed(0) + '%'
      : (lm.recurring_rev_share * 100).toFixed(0) + '%';
  }

  // Top-3 customer concentration
  let custConc = null;
  if (lm.top3_share != null) {
    custConc = lm.top3_share > 1
      ? lm.top3_share.toFixed(0) + '%'
      : (lm.top3_share * 100).toFixed(0) + '%';
  }

  // Helper: return value or placeholder string
  const val = (v, fallback) => v != null ? v : ph(fallback);

  // Scorecard rows: [ criterion, displayValue, dotColor, trendDir, notes ]
  const rows = [
    { criterion:'Revenue CAGR (3yr)',      value: val(cagr,        '[PLACEHOLDER ~8.2%]'), dot:'green',  trendDir:'up',   note:'DATA.financials.cagr_pct or DATA.commercial.revenue_cagr_pct'  },
    { criterion:'EBITDA Margin (latest)',  value: val(ebitdaMargin,'[PLACEHOLDER ~14.1%]'),dot:'green',  trendDir:'flat', note:'DATA.financials.pnl[year].ebitda_margin_pct'                   },
    { criterion:'Recurring Revenue %',     value: val(recurringPct,'[PLACEHOLDER ~45%]'),  dot:'yellow', trendDir:'up',   note:'DATA.customers.metrics[year].recurring_rev_share'              },
    { criterion:'Cust. Conc. (Top 3)',     value: val(custConc,    '[PLACEHOLDER ~38%]'),  dot:'yellow', trendDir:'flat', note:'DATA.customers.metrics[year].top3_share'                       },
    { criterion:'Owner Dependency',        value: ph('[PLACEHOLDER Med]'),                  dot:'yellow', trendDir:'flat', note:'Qualitative — requires RFI answer'                             },
    { criterion:'Market Position',         value: ph('[PLACEHOLDER #2 regional]'),          dot:'green',  trendDir:'up',   note:'Qualitative — requires commercial analysis'                    },
  ];

  // Legend
  const dotLegend = `
<div style="display:flex;gap:16px;font-size:11px;color:#64748b;margin-bottom:10px">
  <span>${scoreDot('green')}  Green = strong / above threshold</span>
  <span>${scoreDot('yellow')} Yellow = acceptable / watch</span>
  <span>${scoreDot('red')}    Red = risk / below threshold</span>
</div>`;

  let scoreTable = `
<table style="width:100%;border-collapse:collapse;font-size:13px">
  <thead>
    <tr style="border-bottom:2px solid #e2e8f0">
      <th style="text-align:left;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px;width:35%">Criterion</th>
      <th style="text-align:center;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px;width:18%">Value</th>
      <th style="text-align:center;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px;width:10%">Rating</th>
      <th style="text-align:center;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px;width:10%">Trend</th>
      <th style="text-align:left;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">Data Source</th>
    </tr>
  </thead>
  <tbody>`;

  for (const row of rows) {
    scoreTable += `
    <tr style="border-bottom:1px solid #f1f5f9">
      <td style="padding:8px 10px;font-weight:500;color:#1e293b">${esc(row.criterion)}</td>
      <td style="padding:8px 10px;text-align:center;font-weight:700;color:#0891B2">${row.value}</td>
      <td style="padding:8px 10px;text-align:center">${scoreDot(row.dot)}</td>
      <td style="padding:8px 10px;text-align:center">${trend(row.trendDir)}</td>
      <td style="padding:8px 10px;font-size:11px;color:#94a3b8">${ph(row.note)}</td>
    </tr>`;
  }

  scoreTable += `
  </tbody>
</table>
<div style="margin-top:8px;font-size:11px;color:#94a3b8">
  ${ph('[PLACEHOLDER] Dot ratings should be computed from thresholds. NOTE: DATA.commercial.scorecard_thresholds path needs backend confirmation — per spec, thresholds come from the deal_scorecard_config table, likely served as DATA.scorecard_config (not DATA.commercial). Trend direction from YoY delta. Qualitative fields need RFI data.')}
</div>`;

  const scorecardBody = dotLegend + scoreTable;

  // ── 3. Strategic Rationale ───────────────────────────────────────────────
  const companyName = esc(d.company_name || d.code_name || '[Company]');
  const rationale   = com.strategic_rationale || null;

  const rationaleBody = `
<div style="font-size:13px;color:#334155;line-height:1.7;min-height:80px;padding:12px;background:#f8fafc;border-radius:6px;border:1px solid #e2e8f0">
  ${rationale
    ? esc(rationale)
    : ph(`[PLACEHOLDER] Acquisition of ${companyName} supports Repuro's buy-and-build strategy in ambulatory healthcare distribution.
The target provides [geographic / product] coverage complementary to the existing portfolio,
with an estimated platform synergy of [X K€] EBITDA. Entry valuation at [Y]x EV/EBITDA aligns
with Repuro's return threshold of [Z]x MOIC over [N]-year hold.`)}
</div>
<div style="margin-top:10px;font-size:11px;color:#94a3b8">
  ${ph('[PLACEHOLDER] Bind to DATA.commercial.strategic_rationale (string). Editable via contenteditable in serve mode. Auto-draft from IC memo chapter 9 via LLM helper (planned DR-M20 backend).')}
</div>`;

  // ── assemble ─────────────────────────────────────────────────────────────
  let h = '';
  h += card('SWOT Matrix',          swotBody);
  h += card('Scorecard',            scorecardBody);
  h += card('Strategic Rationale',  rationaleBody, { mb: 0 });

  return h;
}
