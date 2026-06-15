// ─── One-pager ──────────────────────────────────────────────────────────────

function renderOnepager() {
  const op = DATA.onepager;
  const chart = DATA.onepager_chart;
  if (!op) return '';

  const d = DATA.deal;
  const sc = 'stage-' + d.deal_stage;
  const days = d.days_in_stage != null ? d.days_in_stage + 'd in stage' : '';
  const editable = SERVE_MODE && !INVESTOR_MODE;

  function bulletHtml(text, quadrant) {
    if (!text) return '<div class="empty-state">No content generated yet. Run draft-onepager to generate.</div>';
    const lines = text.split('\n').filter(l => l.trim());
    let ul = '<ul>';
    for (const line of lines) {
      ul += '<li>' + esc(line.replace(/^[-*] /, '')).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>') + '</li>';
    }
    ul += '</ul>';
    return ul;
  }

  function approvalBadge(quadrant, approved) {
    if (INVESTOR_MODE) return '';  // no DRAFT/APPROVED chrome for investors
    if (!editable) return approved ? '<span class="approved-badge">APPROVED</span>' : '<span class="draft-badge">DRAFT</span>';
    const badge = approved ? '<span class="approved-badge">APPROVED</span>' : '<span class="draft-badge">DRAFT</span>';
    const btnLabel = approved ? 'Revoke' : 'Approve';
    return badge + '<button class="op-approve-btn" data-quadrant="' + quadrant + '" data-approved="' + (approved?1:0) + '">' + btnLabel + '</button>';
  }

  let h = '<div class="onepager">';

  // Header
  h += '<div class="onepager-header">';
  const titleAttr = editable ? ' contenteditable="true" data-field="onepager_title"' : '';
  h += '<span class="op-title"' + titleAttr + '>' + esc(op.title || d.company_name || d.code_name) + '</span>';
  h += '<span class="op-stage ' + sc + '">' + (d.deal_stage||'').replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase()).replace(/\b(Loi|Rfi|Dd)\b/g, m => m.toUpperCase()) + '</span>';
  h += '<span class="op-days">' + days + '</span>';
  if (editable) h += '<span class="op-save-ind"></span>';
  h += '</div>';

  // Deal headline (italic subtitle below header)
  const hlAttr = editable ? ' contenteditable="true" data-field="onepager_headline"' : '';
  h += '<div class="op-headline"' + hlAttr + '>' + esc(op.headline || '') + '</div>';

  // 2x2 grid
  h += '<div class="onepager-grid">';

  // Q1: Executive Summary (top-left)
  h += '<div class="op-quadrant">';
  h += '<div class="op-quadrant-header"><span>Executive Summary</span>' + approvalBadge('q1', op.q1_approved) + '</div>';
  h += '<div class="op-quadrant-body"' + (editable ? ' contenteditable="true" data-field="onepager_q1"' : '') + '>' + bulletHtml(op.q1, 'q1') + '</div>';

  h += '</div>';

  // Q2: Financial Overview (top-right)
  h += '<div class="op-quadrant">';
  h += '<div class="op-quadrant-header"><span>Financials &amp; Valuation</span></div>';
  h += '<div class="op-quadrant-body">';
  h += renderQ2Chart(chart, editable);
  h += '</div>';

  h += '</div>';

  // Q3: Service Portfolio & Customer Structure (bottom-left)
  h += '<div class="op-quadrant">';
  h += '<div class="op-quadrant-header"><span>Service Portfolio</span>' + approvalBadge('q4', op.q4_approved) + '</div>';
  h += '<div class="op-quadrant-body op-serv-split">';
  h += '<div class="op-serv-chart-side">' + renderServicePortfolioChart() + '</div>';
  h += '<div class="op-serv-text-side"' + (editable ? ' contenteditable="true" data-field="onepager_q4"' : '') + '>' + bulletHtml(op.q4, 'q4') + '</div>';
  h += '</div>';

  h += '</div>';

  // Q4: Process & Status (bottom-right)
  h += '<div class="op-quadrant">';
  h += '<div class="op-quadrant-header"><span>Process &amp; Status</span>' + approvalBadge('q3', op.q3_approved) + '</div>';
  h += '<div class="op-quadrant-body"' + (editable ? ' contenteditable="true" data-field="onepager_q3"' : '') + '>' + bulletHtml(op.q3, 'q3') + '</div>';

  h += '</div>';

  h += '</div>'; // close grid

  // Footnote
  const fnAttr = editable ? ' contenteditable="true" data-field="onepager_footnote"' : '';
  h += '<div class="op-footnote"' + fnAttr + '>' + esc(op.footnote || '') + '</div>';

  h += '</div>'; // close onepager
  return h;
}

function renderServicePortfolioChart() {
  const cust = DATA.customers || {};
  const top10 = cust.top10 || {};
  const metrics = cust.metrics || {};
  const chartYearly = (DATA.onepager_chart || {}).yearly || {};
  const svcData = cust.service_split || [];

  // --- Customer segments (Top 1 / Top 2-3 / Top 4-10 / Rest) ---
  const allYears = Object.keys(top10).sort();
  const latest = allYears.length ? allYears[allYears.length - 1] : null;
  const rows = latest ? (top10[latest] || []).slice().sort((a, b) => (a.rank || 99) - (b.rank || 99)) : [];
  const totalRevK = latest ? (chartYearly[latest] || {}).revenue_k : null;

  const withPct = rows.map(r => ({
    pct: r.pct != null ? r.pct : (r.revenue != null && totalRevK ? r.revenue / totalRevK * 100 : null)
  })).filter(r => r.pct != null);

  let top1, top2to3, top4to10;
  if (withPct.length >= 1) {
    top1     = withPct[0].pct;
    top2to3  = withPct.slice(1, 3).reduce((s, r) => s + r.pct, 0);
    top4to10 = withPct.slice(3, 10).reduce((s, r) => s + r.pct, 0);
  } else {
    const m = metrics[latest] || {};
    // Values may be stored as decimal (0-1) or percentage (0-100) — detect by magnitude
    const toPct = v => v == null ? 0 : (v > 1 ? v : v * 100);
    top1     = toPct(m.top1_share);
    top2to3  = Math.max(0, (toPct(m.top5_share) - top1) * 0.7);
    top4to10 = Math.max(0, toPct(m.top10_share) - top1 - top2to3);
  }
  const custRest = Math.max(0, 100 - top1 - top2to3 - top4to10);

  const custSegs = [
    {label: 'Top 1',   pct: top1,     fill: '#0891B2', tc: '#fff'},
    {label: 'Top 2-3', pct: top2to3,  fill: '#22C5E0', tc: '#fff'},
    {label: 'Top 4-10',pct: top4to10, fill: '#8DE8F6', tc: '#164e63'},
    {label: 'Rest',    pct: custRest, fill: '#e2e8f0', tc: '#64748b'},
  ].filter(s => s.pct > 0.3);

  // --- Service segments ---
  let svcSegs = null;
  if (svcData.length > 0) {
    const fills  = ['#0891B2', '#8DE8F6', '#e2e8f0', '#cbd5e1'];
    const tcs    = ['#fff', '#164e63', '#64748b', '#64748b'];
    svcSegs = svcData.map((s, i) => ({label: s.label, pct: s.pct, fill: fills[i] || '#e2e8f0', tc: tcs[i] || '#64748b'})).filter(s => s.pct > 0.3);
  } else {
    const m = metrics[latest] || {};
    const rec = (m.recurring_rev_share || 0) * 100;
    if (rec > 0) {
      svcSegs = [
        {label: 'Projects', pct: 100 - rec, fill: '#0891B2', tc: '#fff'},
        {label: 'Recurring', pct: rec,       fill: '#8DE8F6', tc: '#164e63'},
      ];
    }
  }

  const hasSvc  = svcSegs && svcSegs.length > 0 && latest != null;
  const hasCust = custSegs.length > 0 && latest != null;

  if (!hasSvc && !hasCust) return '';

  function drawCol(segs, title) {
    let bars = '';
    for (const seg of segs) {
      const w = Math.max(seg.pct, 4);
      bars += '<div class="svc-seg" style="flex:' + w.toFixed(1) + ';background:' + seg.fill + ';color:' + seg.tc + '" title="' + seg.label + ' ' + seg.pct.toFixed(0) + '%">';
      if (seg.pct < 10) {
        bars += '<span class="svc-seg-inline">' + seg.label + ' ' + seg.pct.toFixed(0) + '%</span>';
      } else {
        bars += '<span class="svc-seg-label">' + seg.label + '</span>';
        bars += '<span class="svc-seg-pct">' + seg.pct.toFixed(0) + '%</span>';
      }
      bars += '</div>';
    }
    return '<div class="svc-col"><div class="svc-col-title">' + title + '</div><div class="svc-col-bars">' + bars + '</div></div>';
  }

  let out = '<div class="svc-chart">';
  if (hasSvc)  out += drawCol(svcSegs,  'Service');
  if (hasCust) out += drawCol(custSegs, 'Customers');
  out += '</div>';
  const yr = latest ? '<div class="svc-yr">' + latest + '</div>' : '';
  return out + yr;
}

function renderQ2Chart(chart, editable) {
  if (!chart || !chart.yearly) return '<div class="empty-state">No financial data available</div>';

  const allYears = Object.keys(chart.yearly).sort();
  if (allYears.length === 0) return '<div class="empty-state">No financial data available</div>';

  // Actuals only (exclude 2026+ projections — those get own columns)
  const years = allYears.filter(y => parseInt(y) <= 2025).slice(-3);
  if (years.length === 0) return '<div class="empty-state">No financial data available</div>';
  const g = yr => chart.yearly[yr] || {};
  const br = chart.bridge || {};
  const bp = chart.bp_2026 || {};
  const maxeo = chart.maxeo_2026 || {};

  const fmtK = v => {
    if (v == null) return '—';
    const neg = v < 0;
    const abs = Math.abs(v);
    const s = Math.round(abs).toLocaleString('de-DE');
    return neg ? '('+s+')' : s;
  };
  const fmtPct = v => v != null ? v.toFixed(1)+'%' : '—';
  const spc = '<th class="op-fin-sep"></th>';
  const spcTd = '<td class="op-fin-sep"></td>';

  // Avg last-two-years (always 2024+2025 from actuals)
  const avg2 = key => {
    if (years.length < 2) return null;
    const a = g(years[years.length-2])[key], b = g(years[years.length-1])[key];
    return (a != null && b != null) ? (a + b) / 2 : null;
  };
  const avgEbitda = avg2('ebitda_k');
  const avgRev = avg2('revenue_k');

  // Multiples: EV / EBITDA basis for each scenario
  const evClose = br.ev_at_closing;
  const evAntic = br.ev_anticipated_earnout;
  const evTotal = br.ev_total;
  const bpEbitda = bp.ebitda_k;
  const maxeoEbitda = maxeo.ebitda_k;
  const mult = (ev, basis) => (ev && basis && basis > 0) ? (ev / basis).toFixed(1)+'x' : '—';

  const bpCell = (val, field) => {
    const content = fmtK(val);
    const attr = editable ? ' contenteditable="true" data-field="' + field + '"' : '';
    return '<td class="op-fin-bp-cell"' + attr + '>' + content + '</td>';
  };

  const nCols = years.length + 7;
  let h = '<table class="op-fin-table">';

  // Header
  h += '<thead><tr><th class="op-fin-label">P&amp;L (in K€)</th>';
  for (const yr of years) h += '<th>' + yr + '</th>';
  h += spc;
  const avgLabel = years.length >= 2 ? 'Avg. ' + years[years.length-2].slice(-2) + '-' + years[years.length-1].slice(-2) : 'Avg.';
  h += '<th class="op-fin-ct">' + avgLabel + '</th>';
  h += '<th class="op-fin-bp">2026 BP</th>';
  h += '<th class="op-fin-bp">Max EO</th>';
  h += spc;
  h += '<th class="op-fin-cagr">Valuation</th>';
  h += '</tr></thead><tbody>';

  // Revenue
  h += '<tr class="op-fin-bold"><td>Revenue</td>';
  for (const yr of years) h += '<td>' + fmtK(g(yr).revenue_k) + '</td>';
  h += spcTd + '<td>' + fmtK(avgRev) + '</td>';
  h += bpCell(bp.revenue_k, 'bp_2026_rev_k');
  h += '<td class="op-fin-bp-cell"></td>';
  h += spcTd + '<td></td></tr>';

  // Adj. EBITDA
  h += '<tr class="op-fin-bold"><td>Adj. EBITDA</td>';
  for (const yr of years) h += '<td>' + fmtK(g(yr).ebitda_k) + '</td>';
  h += spcTd + '<td>' + fmtK(avgEbitda) + '</td>';
  h += bpCell(bpEbitda, 'bp_2026_ebitda_k');
  h += bpCell(maxeoEbitda, 'maxeo_2026_ebitda_k');
  h += spcTd + '<td></td></tr>';

  // Revenue growth
  h += '<tr class="op-fin-kpi"><td><em>Revenue growth</em></td>';
  for (const yr of years) h += '<td>' + fmtPct(g(yr).topline_growth_pct) + '</td>';
  h += spcTd + '<td></td><td></td><td></td>' + spcTd + '<td></td></tr>';

  // EBITDA margin
  h += '<tr class="op-fin-kpi"><td><em>EBITDA margin</em></td>';
  for (const yr of years) h += '<td>' + fmtPct(g(yr).margin_pct) + '</td>';
  h += spcTd + '<td>' + (avgEbitda && avgRev ? fmtPct(avgEbitda / avgRev * 100) : '—') + '</td>';
  h += '<td>' + (bpEbitda && bp.revenue_k ? fmtPct(bpEbitda / bp.revenue_k * 100) : '—') + '</td>';
  h += '<td></td>' + spcTd + '<td></td></tr>';

  // Current Trading (LTM / YTD) — only shown if data exists
  const ct = chart.current_trading || {};
  if (ct.revenue_ltm_k != null || ct.revenue_ytd_k != null) {
    const ltmPeriod = ct.revenue_ltm_period ? ' (' + ct.revenue_ltm_period + ')' : '';
    const ytdPeriod = ct.revenue_ytd_period ? ' (' + ct.revenue_ytd_period + ')' : '';
    const ltmMargin = (ct.ebitda_ltm_k != null && ct.revenue_ltm_k) ? ' / ' + fmtPct(ct.ebitda_ltm_k / ct.revenue_ltm_k * 100) : '';
    const ytdMargin = (ct.ebitda_ytd_k != null && ct.revenue_ytd_k) ? ' / ' + fmtPct(ct.ebitda_ytd_k / ct.revenue_ytd_k * 100) : '';
    h += '<tr class="op-fin-ct"><td><em>Current Trading</em></td>';
    for (const yr of years) h += '<td></td>';
    h += spcTd;
    h += '<td title="LTM' + ltmPeriod + '">' + (ct.revenue_ltm_k != null ? fmtK(ct.revenue_ltm_k) + ltmMargin : '—') + '</td>';
    h += '<td class="op-fin-bp-cell" title="YTD' + ytdPeriod + '">' + (ct.revenue_ytd_k != null ? fmtK(ct.revenue_ytd_k) + ytdMargin : '—') + '</td>';
    h += '<td></td>' + spcTd + '<td></td></tr>';
  }

  // Separator
  h += '<tr class="op-fin-spacer"><td colspan="'+nCols+'"></td></tr>';

  // EV rows — multiples in last year (2025) column only
  const lastYrEbitda = g(years[years.length - 1]).ebitda_k;
  h += '<tr class="op-fin-highlight"><td>EV at closing</td>';
  for (const yr of years) h += '<td>' + (yr === years[years.length - 1] ? mult(evClose, lastYrEbitda) : '') + '</td>';
  h += spcTd + '<td>' + mult(evClose, avgEbitda) + '</td>';
  h += '<td class="op-fin-bp-cell"></td>';
  h += '<td class="op-fin-bp-cell"></td>';
  h += spcTd + '<td>' + fmtK(evClose) + '</td></tr>';

  // EV anticipated Earn-Out
  h += '<tr class="op-fin-highlight"><td>EV anticipated Earn-Out</td>';
  for (const yr of years) h += '<td>' + (yr === years[years.length - 1] ? mult(evAntic, lastYrEbitda) : '') + '</td>';
  h += spcTd + '<td></td>';
  h += '<td class="op-fin-bp-cell">' + mult(evAntic, bpEbitda) + '</td>';
  h += '<td class="op-fin-bp-cell"></td>';
  h += spcTd + '<td>' + fmtK(evAntic) + '</td></tr>';

  // Total EV incl. Super-Earn-Out
  h += '<tr class="op-fin-bold op-fin-highlight"><td>Total EV incl. Super-EO</td>';
  for (const yr of years) h += '<td>' + (yr === years[years.length - 1] ? mult(evTotal, lastYrEbitda) : '') + '</td>';
  h += spcTd + '<td></td>';
  h += '<td class="op-fin-bp-cell"></td>';
  h += '<td class="op-fin-bp-cell">' + mult(evTotal, maxeoEbitda) + '</td>';
  h += spcTd + '<td>' + fmtK(evTotal) + '</td></tr>';

  // Net Cash / Debt
  h += '<tr><td>+/- Net Cash | (Net Debt)</td>';
  for (const yr of years) h += '<td></td>';
  h += spcTd + '<td></td><td></td><td></td>' + spcTd;
  h += '<td>' + (br.net_cash_debt != null ? fmtK(br.net_cash_debt) : '—') + '</td></tr>';

  // Permitted Leakage
  h += '<tr><td>- Permitted Leakage</td>';
  for (const yr of years) h += '<td></td>';
  h += spcTd + '<td></td><td></td><td></td>' + spcTd;
  h += '<td>' + (br.permitted_leakage != null ? '('+fmtK(Math.abs(br.permitted_leakage))+')' : '—') + '</td></tr>';

  // Equity Value
  h += '<tr class="op-fin-bold"><td>Equity Value</td>';
  for (const yr of years) h += '<td></td>';
  h += spcTd + '<td></td><td></td><td></td>' + spcTd;
  h += '<td>' + (br.equity_value != null ? fmtK(br.equity_value) : '—') + '</td></tr>';

  h += '</tbody></table>';
  return h;
}

function _attachOnepagerHandlers() {
  if (!SERVE_MODE) return;

  // Save indicator
  let saveTimer;
  function showSaved(el, ok) {
    const indicator = document.querySelector('.onepager .op-save-ind');
    if (indicator) {
      indicator.textContent = ok ? 'Saved ✓' : 'Error';
      indicator.className = 'op-save-ind ' + (ok ? 'saved' : 'error');
      clearTimeout(saveTimer);
      saveTimer = setTimeout(function() { indicator.className = 'op-save-ind'; }, 2500);
    }
  }

  // Contenteditable fields: title, q1, q3, q4, footnote
  // Text quadrant fields: capture innerHTML and convert <strong>/<b> to **text** so bold survives saves
  const TEXT_FIELDS = new Set(['onepager_q1', 'onepager_q3', 'onepager_q4']);
  document.querySelectorAll('.onepager [contenteditable="true"]').forEach(function(el) {
    el.addEventListener('blur', function() {
      const field = el.dataset.field;
      if (!field) return;
      let value;
      if (TEXT_FIELDS.has(field)) {
        value = el.innerHTML
          .replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, '**$1**')
          .replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, '**$1**')
          .replace(/<\/li>/gi, '\n')
          .replace(/<\/?(div|p)[^>]*>/gi, '\n')
          .replace(/<br\s*\/?>/gi, '\n')
          .replace(/<[^>]+>/g, '')
          .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
          .replace(/\n{3,}/g, '\n\n').trim();
      } else {
        value = el.innerText.trim();
      }
      const code = DATA.deal.code_name;

      fetch('/api/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code_name: code, field: field, value: value})
      }).then(function(r) { showSaved(el, r.ok); }).catch(function() { showSaved(el, false); });
    });
  });

  // Approval buttons
  document.querySelectorAll('.op-approve-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      const q = btn.dataset.quadrant;
      const currentlyApproved = btn.dataset.approved === '1';
      const newVal = currentlyApproved ? 0 : 1;
      const code = DATA.deal.code_name;
      const field = 'onepager_' + q + '_approved';

      fetch('/api/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code_name: code, field: field, value: newVal})
      }).then(function(r) {
        if (r.ok) {
          DATA.onepager[q + '_approved'] = !currentlyApproved;
          showSection('onepager');
        }
      });
    });
  });
}
