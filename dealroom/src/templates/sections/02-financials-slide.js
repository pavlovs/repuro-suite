// DR-M24c — Financials Section: 3-Tab Slide System (GuV / Bilanz / Bewertung)
// Replaces single-slide view with top-level tabs above the teal slide header.
// Each tab has its own hero chart, 3 KPI powercards, and detail table.
// Dependencies: 00-slide-components.js, 01-kpi-registry.js, financials.js functions
//   (renderUnifiedGuV, renderBilanz, renderBewertungTab, _modelCtx, _fmtK, _fmtPct)

// ---------------------------------------------------------------------------
// CSS injection — tab bar sits between breadcrumb and slide-section
// ---------------------------------------------------------------------------
(function injectFinancialsSectionCSS() {
  if (document.getElementById('financials-section-css')) return;
  var css = [
    /* Tab bar row */
    '.fin-tab-bar {',
    '  display: flex;',
    '  gap: 4px;',
    '  margin-bottom: 6px;',
    '  flex-shrink: 0;',
    '}',

    '.fin-tab-btn {',
    '  padding: 5px 18px;',
    '  font-size: 13px;',
    '  font-family: Arial, sans-serif;',
    '  font-weight: 600;',
    '  border: 1px solid #cbd5e1;',
    '  border-radius: 5px 5px 0 0;',
    '  background: #f1f5f9;',
    '  color: #475569;',
    '  cursor: pointer;',
    '  border-bottom: none;',
    '  transition: background 0.15s;',
    '}',

    '.fin-tab-btn:hover {',
    '  background: #e0f2fe;',
    '  color: #0891B2;',
    '}',

    '.fin-tab-btn.active {',
    '  background: #0891B2;',
    '  color: #fff;',
    '  border-color: #0891B2;',
    '}',

    /* Hero chart */
    '.fin-hero-chart { width: 100%; font-family: Arial, sans-serif; }',
    '.fin-legend { display: flex; gap: 16px; margin-bottom: 12px; font-size: 11px; color: #475569; }',
    '.fin-legend-item { display: flex; align-items: center; gap: 5px; }',
    '.fin-legend-dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }',
    '.fin-bar-area { display: flex; align-items: flex-end; gap: 16px; height: 160px; }',
    '.fin-year-group { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }',
    '.fin-bars { display: flex; align-items: flex-end; gap: 4px; flex: 1; width: 100%; justify-content: center; }',
    '.fin-bar-col { display: flex; flex-direction: column; align-items: center; width: 32px; justify-content: flex-end; height: 100%; }',
    '.fin-bar { width: 28px; border-radius: 3px 3px 0 0; min-height: 2px; transition: opacity 0.2s; }',
    '.fin-bar:hover { opacity: 0.85; }',
    '.fin-bar-label { font-size: 10px; color: #334155; font-weight: 600; margin-bottom: 2px; white-space: nowrap; font-variant-numeric: tabular-nums; }',
    '.fin-year-label { font-size: 11px; color: #64748b; font-weight: 600; margin-top: 4px; border-top: 1px solid #e2e8f0; padding-top: 3px; width: 100%; text-align: center; }',

    /* Bilanz hero stacked bar */
    '.bil-hero { width: 100%; font-family: Arial, sans-serif; }',
    '.bil-stack-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }',
    '.bil-stack-label { font-size: 11px; color: #64748b; width: 60px; text-align: right; flex-shrink: 0; }',
    '.bil-stack-bar { display: flex; height: 22px; flex: 1; border-radius: 3px; overflow: hidden; position: relative; }',
    '.bil-stack-seg { height: 100%; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #fff; font-weight: 700; white-space: nowrap; overflow: hidden; min-width: 2px; }',
    '.bil-stack-seg:hover { opacity: 0.85; }',
    '.bil-legend { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; font-size: 10px; color: #475569; }',
    '.bil-legend-item { display: flex; align-items: center; gap: 4px; }',

    /* Bewertung hero table (read-only version of onepager Q2 table) */
    '.bew-hero-table { width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 11px; }',
    '.bew-hero-table th { background: #0891B2; color: #fff; padding: 4px 6px; text-align: right; white-space: nowrap; }',
    '.bew-hero-table th.lh { text-align: left; min-width: 130px; }',
    '.bew-hero-table td { padding: 3px 6px; text-align: right; border-bottom: 1px solid #f0f0f0; }',
    '.bew-hero-table td.lh { text-align: left; font-size: 11px; }',
    '.bew-hero-table tr.bold td { font-weight: 700; }',
    '.bew-hero-table tr.teal-row td { background: #0891B2; color: #fff; font-weight: 700; }',
    '.bew-hero-table tr.hl-row td { background: #e0f5fa; }',
    '.bew-hero-table tr.kpi-row td { font-style: italic; color: #94a3b8; font-size: 10px; }',
    '.bew-hero-sep { width: 8px; padding: 0; border: none; }',
  ].join('\n');
  var s = document.createElement('style');
  s.id = 'financials-section-css';
  s.textContent = css;
  document.head.appendChild(s);
})();

// ---------------------------------------------------------------------------
// Utility: find latest ACTUAL year in onepager_chart.yearly
// "Actual" = year with non-zero revenue, and year <= current calendar year
// ---------------------------------------------------------------------------
function _finLatestActualYear() {
  var yearly = (DATA.onepager_chart && DATA.onepager_chart.yearly) || null;
  if (!yearly) return null;
  var currentYear = new Date().getFullYear();
  var yrs = Object.keys(yearly)
    .filter(function(k) { return /^\d{4}$/.test(k) && Number(k) < currentYear; })
    .sort();
  // Walk backwards — return first year with actual (non-zero) revenue
  var latestActual = null;
  for (var i = yrs.length - 1; i >= 0; i--) {
    var yr = yrs[i];
    var d = yearly[yr];
    if (d && d.revenue_k && d.revenue_k > 0) {
      latestActual = yr;
      break;
    }
  }
  return latestActual;
}

// ---------------------------------------------------------------------------
// TAB 1: GuV Hero — Revenue/EBITDA grouped bar chart (fixed baseline alignment)
// ---------------------------------------------------------------------------
function renderFinancialsHero() {
  var yearly = (DATA.onepager_chart && DATA.onepager_chart.yearly) || null;
  if (!yearly) {
    return '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:20px;">No financial chart data</div>';
  }
  var years = Object.keys(yearly).filter(function(k) { return /^\d{4}$/.test(k); }).sort();
  if (!years.length) {
    return '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:20px;">No financial chart data</div>';
  }

  var maxVal = 0;
  for (var i = 0; i < years.length; i++) {
    var yr = yearly[years[i]];
    // clamp negatives to 0 — negative EBITDA would corrupt baseline; shown as 0-height bar
    if ((yr.revenue_k || 0) > maxVal) maxVal = yr.revenue_k;
    if ((yr.ebitda_k || 0) > 0 && yr.ebitda_k > maxVal) maxVal = yr.ebitda_k;
  }
  if (maxVal === 0) maxVal = 1;
  var MAX_H = 120; // px — fits in slide hero at lower height

  var legend =
    '<div class="fin-legend">' +
      '<div class="fin-legend-item"><span class="fin-legend-dot" style="background:#67e8f9;"></span><span>Revenue</span></div>' +
      '<div class="fin-legend-item"><span class="fin-legend-dot" style="background:#0891B2;"></span><span>EBITDA</span></div>' +
    '</div>';

  var groups = '';
  for (var j = 0; j < years.length; j++) {
    var d = yearly[years[j]];
    var rev = d.revenue_k || 0;
    var ebi = d.ebitda_k || 0;
    // Heights: baseline-aligned — both bars grow upward from same baseline
    // Negative EBITDA renders as 0-height bar (don't corrupt scale)
    var rH = Math.max(Math.round((rev / maxVal) * MAX_H), 2);
    var eH = ebi > 0 ? Math.max(Math.round((ebi / maxVal) * MAX_H), 2) : 0;
    var rLabel = Math.round(rev).toLocaleString('de-DE');
    var eLabel = Math.round(ebi).toLocaleString('de-DE');

    groups +=
      '<div class="fin-year-group">' +
        '<div class="fin-bars">' +
          '<div class="fin-bar-col">' +
            '<div class="fin-bar-label">' + rLabel + '</div>' +
            '<div class="fin-bar" style="height:' + rH + 'px;background:#67e8f9;"></div>' +
          '</div>' +
          '<div class="fin-bar-col">' +
            '<div class="fin-bar-label">' + eLabel + '</div>' +
            '<div class="fin-bar" style="height:' + eH + 'px;background:#0891B2;"></div>' +
          '</div>' +
        '</div>' +
        '<div class="fin-year-label">' + years[j] + '</div>' +
      '</div>';
  }

  return '<div class="fin-hero-chart">' + legend + '<div class="fin-bar-area">' + groups + '</div></div>';
}

// ---------------------------------------------------------------------------
// TAB 1: GuV KPIs — EBITDA Margin, Revenue CAGR 3yr, EBIT Margin (latest actual)
// ---------------------------------------------------------------------------
function _getGuvKPIs() {
  var yearly = (DATA.onepager_chart && DATA.onepager_chart.yearly) || null;
  var yr = _finLatestActualYear();

  var ebitdaMargin = null;
  var ebitMargin = null;
  var revCagr = null;
  var latestLabel = yr ? yr : '—';

  if (yearly && yr) {
    var d = yearly[yr];
    if (d && d.revenue_k && d.revenue_k > 0) {
      if (d.ebitda_k != null) ebitdaMargin = d.ebitda_k / d.revenue_k * 100;
      if (d.margin_pct != null) ebitdaMargin = d.margin_pct; // prefer pre-computed
    }
    // EBIT margin: prefer unified_pnl (Excel-sourced), fall back to adj_pnl.summary
    var fin = DATA.financials || {};
    var upnl = fin.unified_pnl || {};
    var ebitRow = upnl['ebit_adj'] || upnl['ebit'];
    if (ebitRow && ebitRow[yr]) {
      var ebitCell = ebitRow[yr];
      var ebitVal = ebitCell.adjusted != null ? ebitCell.adjusted : ebitCell.raw;
      var revRow = upnl['revenue'];
      if (revRow && revRow[yr]) {
        var revCell = revRow[yr];
        var revVal = revCell.adjusted != null ? revCell.adjusted : revCell.raw;
        if (ebitVal != null && revVal && revVal > 0) {
          ebitMargin = ebitVal / revVal * 100;
        }
      }
    }
    if (ebitMargin == null) {
      var ctx = (typeof _modelCtx !== 'undefined' ? _modelCtx : null) || DATA.model_context || null;
      if (ctx && ctx.adj_pnl && ctx.adj_pnl.summary) {
        var sumYr = ctx.adj_pnl.summary[yr];
        if (sumYr && sumYr.ebit_adj != null && sumYr.total_sales && sumYr.total_sales > 0) {
          ebitMargin = sumYr.ebit_adj / sumYr.total_sales * 100;
        }
      }
    }
  }

  // Revenue CAGR 3yr
  if (yearly) {
    var cCurrentYear = new Date().getFullYear();
    var allYrs = Object.keys(yearly).filter(function(k) { return /^\d{4}$/.test(k) && Number(k) < cCurrentYear; }).sort();
    var actualYrs = allYrs.filter(function(k) { return yearly[k] && (yearly[k].revenue_k || 0) > 0; });
    if (actualYrs.length >= 3) {
      var firstYr = actualYrs[actualYrs.length - 3];
      var lastYr = actualYrs[actualYrs.length - 1];
      var firstRev = yearly[firstYr].revenue_k;
      var lastRev = yearly[lastYr].revenue_k;
      if (firstRev > 0 && lastRev > 0) {
        revCagr = (Math.pow(lastRev / firstRev, 1 / 2) - 1) * 100; // 3 years = 2 periods
      }
    } else if (actualYrs.length >= 2) {
      var f = actualYrs[0], l = actualYrs[actualYrs.length - 1];
      var n = actualYrs.length - 1;
      var fR = yearly[f].revenue_k, lR = yearly[l].revenue_k;
      if (fR > 0 && lR > 0 && n > 0) {
        revCagr = (Math.pow(lR / fR, 1 / n) - 1) * 100;
      }
    }
  }

  return [
    {
      label: 'EBITDA Margin',
      value: ebitdaMargin,
      format: 'pct',
      bullet: latestLabel + ' actual (adj.)'
    },
    {
      label: 'Revenue CAGR 3yr',
      value: revCagr,
      format: 'pct',
      bullet: 'Organic growth'
    },
    {
      label: 'EBIT Margin',
      value: ebitMargin,
      format: 'pct',
      bullet: latestLabel + ' adj.'
    }
  ];
}

// ---------------------------------------------------------------------------
// TAB 2: Bilanz Hero — Horizontal stacked bar: LT Debt | ST Debt vs Cash
// ---------------------------------------------------------------------------
function renderBilanzHero() {
  var fin = DATA.financials || {};
  var balance = fin.balance || {};
  // Find latest year with balance data
  var balYrs = Object.keys(balance)
    .filter(function(k) { return /^\d{4}$/.test(k); })
    .sort();
  if (!balYrs.length) {
    return '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:20px;">No balance sheet data</div>';
  }
  var yr = balYrs[balYrs.length - 1];
  var b = balance[yr] || {};

  function safeVal(cell) {
    if (!cell) return null;
    return cell.value != null ? cell.value : null;
  }

  var cash = safeVal(b.cash) || 0;
  var debtLt = safeVal(b.debt_lt) || 0;
  var debtSt = safeVal(b.debt_st) || 0;
  var totalDebt = debtLt + debtSt;
  var totalBar = Math.max(cash, totalDebt);
  if (totalBar === 0) totalBar = 1;

  var fmtK = function(v) {
    if (v == null || v === 0) return '—';
    return Math.round(Math.abs(v)).toLocaleString('de-DE') + ' K€';
  };

  var barWidth = function(v) {
    return Math.max(Math.round((Math.abs(v) / totalBar) * 100), 2);
  };

  var legend =
    '<div class="bil-legend">' +
      '<div class="bil-legend-item"><span style="width:10px;height:10px;border-radius:2px;background:#dc2626;display:inline-block;"></span><span>LT Debt</span></div>' +
      '<div class="bil-legend-item"><span style="width:10px;height:10px;border-radius:2px;background:#f97316;display:inline-block;"></span><span>ST Debt</span></div>' +
      '<div class="bil-legend-item"><span style="width:10px;height:10px;border-radius:2px;background:#22c55e;display:inline-block;"></span><span>Cash</span></div>' +
    '</div>';

  // Debt bar
  var debtBar = '';
  if (totalDebt > 0) {
    var ltW = debtLt > 0 ? barWidth(debtLt) : 0;
    var stW = debtSt > 0 ? barWidth(debtSt) : 0;
    if (ltW > 0) {
      debtBar += '<div class="bil-stack-seg" style="width:' + ltW + '%;background:#dc2626;" title="LT Debt: ' + fmtK(debtLt) + '">' + (ltW > 15 ? fmtK(debtLt) : '') + '</div>';
    }
    if (stW > 0) {
      debtBar += '<div class="bil-stack-seg" style="width:' + stW + '%;background:#f97316;" title="ST Debt: ' + fmtK(debtSt) + '">' + (stW > 15 ? fmtK(debtSt) : '') + '</div>';
    }
  } else {
    debtBar = '<div class="bil-stack-seg" style="width:2%;background:#e2e8f0;"></div>';
  }

  // Cash bar
  var cashW = cash > 0 ? barWidth(cash) : 2;
  var cashBar = '<div class="bil-stack-seg" style="width:' + cashW + '%;background:#22c55e;" title="Cash: ' + fmtK(cash) + '">' + (cashW > 15 ? fmtK(cash) : '') + '</div>';

  var netDebt = safeVal(b.net_debt);
  var netDebtLabel = netDebt != null
    ? 'Net Debt: ' + Math.round(Math.abs(netDebt)).toLocaleString('de-DE') + ' K€'
    : '';

  var h =
    '<div class="bil-hero">' +
      '<div style="font-size:11px;color:#64748b;margin-bottom:6px;font-family:Arial,sans-serif;">' +
        'Balance Sheet — ' + yr + (netDebtLabel ? ' &nbsp;|&nbsp; ' + netDebtLabel : '') +
      '</div>' +
      legend +
      '<div class="bil-stack-row">' +
        '<div class="bil-stack-label">Debt</div>' +
        '<div class="bil-stack-bar">' + debtBar + '</div>' +
      '</div>' +
      '<div class="bil-stack-row">' +
        '<div class="bil-stack-label">Cash</div>' +
        '<div class="bil-stack-bar">' + cashBar + '</div>' +
      '</div>' +
    '</div>';

  return h;
}

// ---------------------------------------------------------------------------
// TAB 2: Bilanz KPIs
// ---------------------------------------------------------------------------
function _getBilanzKPIs() {
  var fin = DATA.financials || {};
  var balance = fin.balance || {};
  var balYrs = Object.keys(balance)
    .filter(function(k) { return /^\d{4}$/.test(k); })
    .sort();

  var latestBalYr = balYrs.length ? balYrs[balYrs.length - 1] : null;
  var b = latestBalYr ? (balance[latestBalYr] || {}) : {};

  function safeVal(cell) {
    if (!cell) return null;
    return cell.value != null ? cell.value : null;
  }

  var netDebt = safeVal(b.net_debt);
  var cash = safeVal(b.cash);
  var debtLt = safeVal(b.debt_lt) || 0;
  var debtSt = safeVal(b.debt_st) || 0;
  var receivables = safeVal(b.receivables);

  // NWC % of Sales — receivables / revenue from latest actual year
  var nwcPct = null;
  var latestActYr = _finLatestActualYear();
  var yearly = (DATA.onepager_chart && DATA.onepager_chart.yearly) || null;
  if (receivables != null && yearly && latestActYr) {
    var rev = yearly[latestActYr] && yearly[latestActYr].revenue_k;
    if (rev && rev > 0) {
      nwcPct = (receivables / rev) * 100;
    }
  }

  // Debt/EBITDA ratio
  var debtEbitda = null;
  var totalDebt = Math.abs(debtLt) + Math.abs(debtSt);
  if (yearly && latestActYr) {
    var ebitda = yearly[latestActYr] && yearly[latestActYr].ebitda_k;
    if (ebitda && ebitda > 0 && totalDebt > 0) {
      debtEbitda = totalDebt / ebitda;
    }
  }

  var netDebtLabel = 'Net Debt';
  var netDebtBullet = latestBalYr || '—';
  var netDebtDisplay = null;
  if (netDebt != null) {
    if (netDebt < 0) {
      netDebtLabel = 'Net Cash';
      netDebtDisplay = Math.abs(netDebt);
    } else {
      netDebtDisplay = netDebt;
    }
  }

  return [
    {
      label: 'Receivables % of Sales',
      value: nwcPct,
      format: 'pct',
      bullet: 'Forderungen / Revenue'
    },
    {
      label: netDebtLabel,
      value: netDebtDisplay,
      format: 'eur_k',
      bullet: netDebtBullet
    },
    {
      label: 'Debt / EBITDA',
      value: debtEbitda,
      format: 'mult',
      bullet: 'Leverage ratio'
    }
  ];
}

// ---------------------------------------------------------------------------
// TAB 3: Bewertung Hero — Read-only P&L + Valuation table (onepager Q2 style)
// ---------------------------------------------------------------------------
function renderBewertungHero() {
  var chart = DATA.onepager_chart;
  if (!chart || !chart.yearly) {
    return '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:20px;">No valuation data</div>';
  }

  var currentYear = new Date().getFullYear();
  var allYears = Object.keys(chart.yearly)
    .filter(function(k) { return /^\d{4}$/.test(k) && Number(k) < currentYear; })
    .sort();
  // Actuals only (≤ current year with positive revenue), last 3
  var years = allYears.filter(function(y) { return (chart.yearly[y].revenue_k || 0) > 0; }).slice(-3);
  if (!years.length) {
    return '<div style="color:#94a3b8;font-size:13px;text-align:center;padding:20px;">No financial data</div>';
  }

  var br = chart.bridge || {};
  var bp = chart.bp_2026 || {};
  var maxeo = chart.maxeo_2026 || {};

  var g = function(yr) { return chart.yearly[yr] || {}; };

  var fmtK = function(v) {
    if (v == null) return '—';
    var neg = v < 0;
    var s = Math.round(Math.abs(v)).toLocaleString('de-DE');
    return neg ? '(' + s + ')' : s;
  };
  var fmtPct = function(v) {
    return v != null
      ? Number(v).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%'
      : '—';
  };
  var mult = function(ev, basis) {
    return (ev && basis && basis > 0)
      ? Number(ev / basis).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'x'
      : '—';
  };

  var lastYrEbitda = g(years[years.length - 1]).ebitda_k;

  // Avg of last 2 actual years
  var avgEbitda = null, avgRev = null;
  if (years.length >= 2) {
    var aE = g(years[years.length - 2]).ebitda_k;
    var bE = g(years[years.length - 1]).ebitda_k;
    if (aE != null && bE != null) avgEbitda = (aE + bE) / 2;
    var aR = g(years[years.length - 2]).revenue_k;
    var bR = g(years[years.length - 1]).revenue_k;
    if (aR != null && bR != null) avgRev = (aR + bR) / 2;
  }

  var avgLabel = years.length >= 2
    ? 'Avg ' + years[years.length - 2].slice(-2) + '-' + years[years.length - 1].slice(-2)
    : 'Avg';

  var evClose = br.ev_at_closing;
  var evAntic = br.ev_anticipated_earnout;
  var evTotal = br.ev_total;

  var h = '<table class="bew-hero-table">';

  // Header — year keys are already /^\d{4}$/-filtered but escape for safety
  h += '<thead><tr><th class="lh">P&amp;L (K€)</th>';
  for (var i = 0; i < years.length; i++) {
    h += '<th>' + _slide_esc(years[i]) + '</th>';
  }
  h += '<th class="bew-hero-sep"></th>';
  h += '<th>' + avgLabel + '</th>';
  if (bp.ebitda_k != null) h += '<th>BP</th>';
  h += '<th class="bew-hero-sep"></th>';
  h += '<th>Valuation</th>';
  h += '</tr></thead><tbody>';

  // Revenue
  h += '<tr class="bold"><td class="lh">Revenue</td>';
  for (var ri = 0; ri < years.length; ri++) h += '<td>' + fmtK(g(years[ri]).revenue_k) + '</td>';
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + fmtK(avgRev) + '</td>';
  if (bp.ebitda_k != null) h += '<td>' + fmtK(bp.revenue_k) + '</td>';
  h += '<td class="bew-hero-sep"></td><td></td></tr>';

  // Adj. EBITDA
  h += '<tr class="bold"><td class="lh">Adj. EBITDA</td>';
  for (var ei = 0; ei < years.length; ei++) h += '<td>' + fmtK(g(years[ei]).ebitda_k) + '</td>';
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + fmtK(avgEbitda) + '</td>';
  if (bp.ebitda_k != null) h += '<td>' + fmtK(bp.ebitda_k) + '</td>';
  h += '<td class="bew-hero-sep"></td><td></td></tr>';

  // EBITDA margin (kpi row)
  h += '<tr class="kpi-row"><td class="lh"><em>EBITDA margin</em></td>';
  for (var mi = 0; mi < years.length; mi++) h += '<td>' + fmtPct(g(years[mi]).margin_pct) + '</td>';
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + (avgEbitda != null && avgRev != null && avgRev > 0 ? fmtPct(avgEbitda / avgRev * 100) : '—') + '</td>';
  if (bp.ebitda_k != null) h += '<td>' + (bp.ebitda_k != null && bp.revenue_k != null && bp.revenue_k > 0 ? fmtPct(bp.ebitda_k / bp.revenue_k * 100) : '—') + '</td>';
  h += '<td class="bew-hero-sep"></td><td></td></tr>';

  // Spacer — hasBpCol derived from null-check to match column rendering logic
  var hasBpCol = bp.ebitda_k != null;
  h += '<tr><td colspan="' + (years.length + 4 + (hasBpCol ? 1 : 0)) + '" style="padding:3px;border:none;"></td></tr>';

  // EV at closing
  h += '<tr class="hl-row bold"><td class="lh">EV at closing</td>';
  for (var ci = 0; ci < years.length; ci++) {
    h += '<td>' + (ci === years.length - 1 ? mult(evClose, lastYrEbitda) : '') + '</td>';
  }
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + mult(evClose, avgEbitda) + '</td>';
  if (bp.ebitda_k != null) h += '<td></td>';
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + fmtK(evClose) + '</td></tr>';

  // EV anticipated
  if (evAntic) {
    h += '<tr class="hl-row"><td class="lh">EV ant. Earn-Out</td>';
    for (var ai = 0; ai < years.length; ai++) {
      h += '<td>' + (ai === years.length - 1 ? mult(evAntic, lastYrEbitda) : '') + '</td>';
    }
    h += '<td class="bew-hero-sep"></td><td></td>';
    if (bp.ebitda_k != null) h += '<td></td>';
    h += '<td class="bew-hero-sep"></td>';
    h += '<td>' + fmtK(evAntic) + '</td></tr>';
  }

  // Total EV
  if (evTotal) {
    h += '<tr class="teal-row"><td class="lh">Total EV incl. Super-EO</td>';
    for (var ti = 0; ti < years.length; ti++) {
      h += '<td>' + (ti === years.length - 1 ? mult(evTotal, lastYrEbitda) : '') + '</td>';
    }
    h += '<td class="bew-hero-sep"></td><td></td>';
    if (bp.ebitda_k != null) h += '<td></td>';
    h += '<td class="bew-hero-sep"></td>';
    h += '<td>' + fmtK(evTotal) + '</td></tr>';
  }

  // Net debt + equity value
  var ndVal = br.net_cash_debt != null ? br.net_cash_debt : null;
  var eqVal = br.equity_value != null ? br.equity_value : null;
  h += '<tr><td class="lh">+/- Net Cash | (Net Debt)</td>';
  for (var ni = 0; ni < years.length; ni++) h += '<td></td>';
  h += '<td class="bew-hero-sep"></td><td></td>';
  if (bp.ebitda_k != null) h += '<td></td>';
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + (ndVal != null ? fmtK(ndVal) : '—') + '</td></tr>';

  h += '<tr class="bold"><td class="lh">Equity Value</td>';
  for (var qi = 0; qi < years.length; qi++) h += '<td></td>';
  h += '<td class="bew-hero-sep"></td><td></td>';
  if (bp.ebitda_k != null) h += '<td></td>';
  h += '<td class="bew-hero-sep"></td>';
  h += '<td>' + (eqVal != null ? fmtK(eqVal) : '—') + '</td></tr>';

  h += '</tbody></table>';
  return h;
}

// ---------------------------------------------------------------------------
// TAB 3: Bewertung KPIs
// ---------------------------------------------------------------------------
function _getBewertungKPIs() {
  var wf = (DATA.model_context && DATA.model_context.waterfall) || {};
  var br = (DATA.onepager_chart && DATA.onepager_chart.bridge) || {};

  // Cash at Closing %
  var cashPct = null;
  if (wf.cash_pct != null) {
    cashPct = wf.cash_pct > 1 ? wf.cash_pct : wf.cash_pct * 100;
  } else if (wf.ev_at_closing && wf.equity_value) {
    // derive from params if available
    var params = (DATA.model_context && DATA.model_context.params) || {};
    if (params.cash_at_closing != null && wf.equity_value > 0) {
      cashPct = (params.cash_at_closing / wf.equity_value) * 100;
    }
  }

  // Earn-Out % of EV Total — always compute from amounts, not pre-stored pct
  var eoEv = null;
  if (wf.earnout_anticipated != null && wf.ev_total && wf.ev_total > 0) {
    eoEv = (wf.earnout_anticipated / wf.ev_total) * 100;
  } else {
    var params2 = (DATA.model_context && DATA.model_context.params) || {};
    if (params2.earnout_anticipated != null && wf.ev_total && wf.ev_total > 0) {
      eoEv = (params2.earnout_anticipated / wf.ev_total) * 100;
    }
  }
  if (eoEv == null && br.ev_total && br.ev_anticipated_earnout) {
    eoEv = (br.ev_anticipated_earnout / br.ev_total) * 100;
  }

  // Net Debt / EBITDA — preserve sign (negative = net cash)
  var ndEbitda = null;
  var bewNdLabel = 'Net Debt / EBITDA';
  var latestActYr = _finLatestActualYear();
  var yearly = (DATA.onepager_chart && DATA.onepager_chart.yearly) || null;
  if (yearly && latestActYr) {
    var ebitda = yearly[latestActYr] && yearly[latestActYr].ebitda_k;
    var nd = null;
    if (wf.net_debt != null) {
      nd = wf.net_debt;
    } else {
      var params3 = (DATA.model_context && DATA.model_context.params) || {};
      if (params3.net_debt != null) nd = params3.net_debt;
    }
    if (nd != null && ebitda && ebitda > 0) {
      ndEbitda = Math.abs(nd) / ebitda;
      if (nd < 0) bewNdLabel = 'Net Cash / EBITDA';
    }
  }

  return [
    {
      label: 'Cash at Closing',
      value: cashPct,
      format: 'pct',
      bullet: '% of equity value'
    },
    {
      label: 'Earn-Out % of EV',
      value: eoEv,
      format: 'pct',
      bullet: 'Deferred component'
    },
    {
      label: bewNdLabel,
      value: ndEbitda,
      format: 'mult',
      bullet: 'Leverage at closing'
    }
  ];
}

// ---------------------------------------------------------------------------
// Tab slide content renderers — hero + KPIs + detail for each tab
// ---------------------------------------------------------------------------
function renderGuvTabSlide() {
  // Ensure model context is initialized so renderBewertungTab / renderUnifiedGuV work
  if (typeof _modelCtx !== 'undefined' && _modelCtx === null) {
    _modelCtx = DATA.model_context || null;
  }
  var heroHtml = renderFinancialsHero();
  var kpis = _getGuvKPIs();
  // Detail: GuV table — call renderUnifiedGuV directly (already exists in financials.js)
  var detailHtml = (typeof renderUnifiedGuV === 'function') ? renderUnifiedGuV() : renderInformation();
  return renderSlideSection('financials-guv', 'Financials — GuV', heroHtml, kpis, detailHtml);
}

function renderBilanzTabSlide() {
  if (typeof _modelCtx !== 'undefined' && _modelCtx === null) {
    _modelCtx = DATA.model_context || null;
  }
  var heroHtml = renderBilanzHero();
  var kpis = _getBilanzKPIs();
  var fin = DATA.financials || {};
  var balance = fin.balance || {};
  var detailHtml = (typeof renderBilanz === 'function') ? renderBilanz(balance) : '<div style="color:#94a3b8">Balance sheet not available</div>';
  return renderSlideSection('financials-bilanz', 'Financials — Bilanz', heroHtml, kpis, detailHtml);
}

function renderBewertungTabSlide() {
  // Must set _modelCtx before calling renderBewertungTab
  if (typeof _modelCtx !== 'undefined') {
    _modelCtx = DATA.model_context || null;
  }
  var heroHtml = renderBewertungHero();
  var kpis = _getBewertungKPIs();
  var detailHtml = (typeof renderBewertungTab === 'function') ? renderBewertungTab() : '<div style="color:#94a3b8">Valuation model not available</div>';
  return renderSlideSection('financials-bewertung', 'Financials — Bewertung', heroHtml, kpis, detailHtml);
}

// ---------------------------------------------------------------------------
// Master function: renderFinancialsSection()
// Returns full HTML for the financials section: tab bar + active slide.
// Called from dashboard.html showSection() case 'financials'.
// After setting innerHTML, call _initFinancialsSection() to wire tab handlers.
// ---------------------------------------------------------------------------
function renderFinancialsSection(activeTab) {
  activeTab = activeTab || 'guv';

  var tabs = [
    { id: 'guv',       label: 'GuV' },
    { id: 'bilanz',    label: 'Bilanz' },
    { id: 'bewertung', label: 'Bewertung' }
  ];

  var afBar = '';
  if (typeof renderAnswerFirstBar === 'function' && typeof _afFinancialSignals === 'function') {
    var mc = (typeof _modelCtx !== 'undefined' && _modelCtx) ? _modelCtx : (DATA.model_context || null);
    afBar = renderAnswerFirstBar(_afFinancialSignals(mc), {title: 'Financial Signals'});
  }

  // Tab bar
  var tabBar = '<div class="fin-tab-bar" id="fin-tab-bar">';
  for (var i = 0; i < tabs.length; i++) {
    var t = tabs[i];
    var activeCls = (t.id === activeTab) ? ' active' : '';
    tabBar +=
      '<button class="fin-tab-btn' + activeCls + '" ' +
        'data-tab="' + t.id + '" ' +
        'onclick="_switchFinTab(\'' + t.id + '\')">' +
        t.label +
      '</button>';
  }
  tabBar += '</div>';

  // Active slide content
  var slideHtml = '';
  if (activeTab === 'guv') {
    slideHtml = renderGuvTabSlide();
  } else if (activeTab === 'bilanz') {
    slideHtml = renderBilanzTabSlide();
  } else if (activeTab === 'bewertung') {
    slideHtml = renderBewertungTabSlide();
  } else {
    slideHtml = renderGuvTabSlide();
  }

  return (
    '<div id="financials-section-shell" style="display:flex;flex-direction:column;flex:1;min-height:0;">' +
      afBar + tabBar + slideHtml +
    '</div>'
  );
}

// ---------------------------------------------------------------------------
// Tab switch handler — called by onclick on tab buttons
// ---------------------------------------------------------------------------
function _switchFinTab(tabId) {
  // Re-render just the slide content area (preserve shell + breadcrumb)
  var shell = document.getElementById('financials-section-shell');
  if (!shell) return;

  // Update active button state
  var btns = shell.querySelectorAll('.fin-tab-btn');
  for (var i = 0; i < btns.length; i++) {
    if (btns[i].getAttribute('data-tab') === tabId) {
      btns[i].classList.add('active');
    } else {
      btns[i].classList.remove('active');
    }
  }

  // Re-render slide content — replace everything after the tab bar
  var tabBar = shell.querySelector('#fin-tab-bar');
  if (!tabBar) return;

  // Remove all siblings after tab bar (that's the old slide)
  var next = tabBar.nextSibling;
  while (next) {
    var tmp = next.nextSibling;
    shell.removeChild(next);
    next = tmp;
  }

  // Render and insert new slide HTML
  var newSlideHtml = '';
  if (tabId === 'guv') {
    newSlideHtml = renderGuvTabSlide();
  } else if (tabId === 'bilanz') {
    newSlideHtml = renderBilanzTabSlide();
  } else if (tabId === 'bewertung') {
    newSlideHtml = renderBewertungTabSlide();
  }

  var tmp2 = document.createElement('div');
  tmp2.innerHTML = newSlideHtml;
  while (tmp2.firstChild) {
    shell.appendChild(tmp2.firstChild);
  }

  // Re-wire all expand handlers after tab swap
  // GuV rows use toggleExpandGuV (data-guv attr), all others use toggleExpand
  var allExpandables = shell.querySelectorAll('.expandable');
  for (var j = 0; j < allExpandables.length; j++) {
    (function(el) {
      if (el.dataset.guv) {
        if (typeof toggleExpandGuV === 'function') {
          el.addEventListener('click', function() { toggleExpandGuV(el); });
        }
      } else {
        if (typeof toggleExpand === 'function') {
          el.addEventListener('click', function() { toggleExpand(el); });
        }
      }
    })(allExpandables[j]);
  }
}
