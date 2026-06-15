// ─── Interactive DD Analysis Engine ──────────────────────────────────────────
// Cross-dimensional insight layer with global filter state, cross-filtering,
// drill-through, and what-if scenario modeling.
// Depends on: 00-answer-first.js (chip utils), DATA global, _CDD_PALETTE (cdd.js)

// ═══════════════════════════════════════════════════════════════════════════════
// GLOBAL FILTER STATE — all panels react to changes
// ═══════════════════════════════════════════════════════════════════════════════
var _IA = {
  segFilter: null,
  yearRange: null,
  scenarioMult: null,
  scenarioEbitda: null,
  expandedPanel: null,
  drillTarget: null,
};

function _iaEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function _iaSetFilter(key, val) {
  _IA[key] = val;
  _iaRerender();
}

function _iaToggleSegFilter(name) {
  _IA.segFilter = (_IA.segFilter === name) ? null : name;
  _iaRerender();
}

function _iaRerender() {
  var el = document.getElementById('ia-root');
  if (!el) return;
  el.innerHTML = _iaRenderInner();
  _iaBindScenarioSliders();
}

// ═══════════════════════════════════════════════════════════════════════════════
// FILTER BAR — segment chips + year range
// ═══════════════════════════════════════════════════════════════════════════════
function _iaFilterBar(cdd) {
  var seg = cdd.segments;
  if (!seg || !seg.rows) return '';
  var h = '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;background:#f1f5f9;border-radius:8px">';
  h += '<span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#64748b;margin-right:4px">Filter</span>';

  // Segment chips
  seg.rows.forEach(function(s, i) {
    var active = _IA.segFilter === s.name;
    var c = _CDD_PALETTE[i % _CDD_PALETTE.length];
    h += '<button onclick="_iaToggleSegFilter(\'' + _iaEsc(s.name).replace(/'/g,"\\'") + '\')" style="'
      + 'border:1.5px solid ' + c + ';background:' + (active ? c : '#fff') + ';color:' + (active ? '#fff' : c) + ';'
      + 'border-radius:14px;padding:3px 10px;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s">'
      + _iaEsc(s.name) + '</button>';
  });

  if (_IA.segFilter) {
    h += '<button onclick="_iaSetFilter(\'segFilter\',null)" style="border:none;background:none;cursor:pointer;font-size:12px;color:#94a3b8;margin-left:4px" title="Clear filter">&times; clear</button>';
  }

  h += '<span style="margin-left:auto"></span>';

  // Year range buttons
  var allYrs = seg.years.map(String);
  var ytd = cdd.meta && cdd.meta.ytd_year ? String(cdd.meta.ytd_year) : null;
  var fy = ytd ? allYrs.filter(function(y){return y!==ytd;}) : allYrs;
  fy.forEach(function(y) {
    var inRange = !_IA.yearRange || (y >= _IA.yearRange[0] && y <= _IA.yearRange[1]);
    h += '<button onclick="_iaToggleYear(\'' + y + '\')" style="'
      + 'border:1px solid ' + (inRange ? '#0891B2' : '#e2e8f0') + ';background:' + (inRange ? '#ecfeff' : '#fff') + ';color:' + (inRange ? '#0891B2' : '#94a3b8') + ';'
      + 'border-radius:4px;padding:2px 8px;font-size:10px;font-weight:600;cursor:pointer;min-width:40px">'
      + y + '</button>';
  });
  if (_IA.yearRange) {
    h += '<button onclick="_iaSetFilter(\'yearRange\',null)" style="border:none;background:none;cursor:pointer;font-size:11px;color:#94a3b8">&times;</button>';
  }

  h += '</div>';
  return h;
}

function _iaToggleYear(y) {
  if (!_IA.yearRange) { _IA.yearRange = [y, y]; }
  else if (_IA.yearRange[0] === y && _IA.yearRange[1] === y) { _IA.yearRange = null; }
  else if (y < _IA.yearRange[0]) { _IA.yearRange[0] = y; }
  else if (y > _IA.yearRange[1]) { _IA.yearRange[1] = y; }
  else { _IA.yearRange = [y, y]; }
  _iaRerender();
}

function _iaFilteredYears(cdd) {
  var allYrs = cdd.segments.years.map(String);
  var ytd = cdd.meta && cdd.meta.ytd_year ? String(cdd.meta.ytd_year) : null;
  var fy = ytd ? allYrs.filter(function(y){return y!==ytd;}) : allYrs;
  if (!_IA.yearRange) return fy;
  return fy.filter(function(y) { return y >= _IA.yearRange[0] && y <= _IA.yearRange[1]; });
}

// ═══════════════════════════════════════════════════════════════════════════════
// REVENUE NARRATIVE — auto-generated, filter-aware
// ═══════════════════════════════════════════════════════════════════════════════
function _insightNarrative(cdd, mc, fin) {
  if (!cdd || !cdd.segments) return '';
  var seg = cdd.segments, bridge = (cdd.churn || {}).bridge || [];
  var ret = cdd.retention || [];
  var flags = (cdd.findings || {}).red_flags || [];
  var conc = cdd.concentration || {};

  var fy = _iaFilteredYears(cdd);
  if (fy.length < 1) return '<div style="color:#94a3b8;font-size:12px">Select at least one year.</div>';
  var y0 = fy[0], y1 = fy[fy.length-1];

  // If segment-filtered, scope to that segment
  var filteredRows = seg.rows;
  if (_IA.segFilter) {
    filteredRows = seg.rows.filter(function(s){return s.name === _IA.segFilter;});
    if (!filteredRows.length) return '<div style="color:#94a3b8;font-size:12px">Segment "'+_IA.segFilter+'" not found.</div>';
  }

  var t0 = 0, t1 = 0;
  filteredRows.forEach(function(s) {
    if (s.rev[y0] != null) t0 += s.rev[y0];
    if (s.rev[y1] != null) t1 += s.rev[y1];
  });
  var n = fy.length > 1 ? fy.length - 1 : 1;
  var cagr = (t0 && t1 && n > 0) ? (Math.pow(t1/t0, 1/n) - 1) * 100 : null;

  var avgLogo = 0, avgNrr = 0, retN = 0;
  ret.forEach(function(r) { if (!r.partial) { avgLogo += r.logo_pct; avgNrr += r.nrr_pct; retN++; } });
  if (retN) { avgLogo /= retN; avgNrr /= retN; }

  var totalNew = 0, totalEnd = 0;
  bridge.forEach(function(b) { totalNew += b.new; totalEnd += b.end; });
  var newPct = totalEnd > 0 ? totalNew / totalEnd * 100 : null;

  var highFlags = flags.filter(function(f){return f.severity==='HIGH';}).length;

  var top3 = null;
  if (conc.tiers) {
    var t = conc.tiers.reduce(function(b,t){return(!b||(t.n<=3&&t.n>(b.n||0)))?t:b;},null);
    if (t) top3 = t.pct;
  }

  var avgGm = 0, gmRevSum = 0;
  filteredRows.forEach(function(s) {
    var rv = s.rev[String(seg.latest_full_year)], gm = s.gm_pct[String(seg.latest_full_year)];
    if (rv != null && gm != null) { avgGm += rv * gm / 100; gmRevSum += rv; }
  });
  avgGm = gmRevSum > 0 ? avgGm / gmRevSum * 100 : null;

  var lines = [];
  var scope = _IA.segFilter ? ' (segment: ' + _IA.segFilter + ')' : '';
  lines.push('<div style="font-size:13px;line-height:1.75;color:#334155">');

  var growthVerdict = cagr == null ? 'Insufficient data' : cagr >= 10 ? 'Strong' : cagr >= 5 ? 'Moderate' : cagr >= 0 ? 'Weak' : 'Declining';
  if (cagr != null) {
    lines.push('<p><strong>Revenue Growth: ' + growthVerdict + scope + '.</strong> ');
    lines.push('Topline grew ' + (cagr>=0?'+':'') + cagr.toFixed(1) + '% CAGR (' + y0 + '–' + y1 + ', €' + Math.round(t0) + 'K → €' + Math.round(t1) + 'K)');
    if (!_IA.segFilter && avgNrr && avgNrr < 90) {
      lines.push(', but net revenue retention averages only ' + avgNrr.toFixed(0) + '% — ');
      if (newPct != null && newPct > 15) {
        lines.push('<span style="color:#b91c1c;font-weight:600">growth is ' + newPct.toFixed(0) + '% new-customer-driven</span>, more expensive and less predictable than organic expansion.');
      } else {
        lines.push('indicating revenue churn among existing customers.');
      }
    } else if (!_IA.segFilter && avgNrr >= 100) {
      lines.push(' with strong net expansion (NRR ' + avgNrr.toFixed(0) + '%).');
    } else {
      lines.push('.');
    }
    lines.push('</p>');
  }

  if (!_IA.segFilter && (avgLogo || top3 != null)) {
    var custVerdict = avgLogo >= 80 ? 'Stable' : avgLogo >= 65 ? 'Moderate churn' : 'High churn';
    lines.push('<p><strong>Customer Base: ' + custVerdict + '.</strong> ');
    if (avgLogo) {
      lines.push('Average logo retention ' + avgLogo.toFixed(0) + '% (');
      lines.push(avgLogo >= 80 ? 'healthy' : avgLogo >= 65 ? 'below target' : '<span style="color:#b91c1c;font-weight:600">material risk</span>');
      lines.push('). ');
    }
    if (top3 != null) {
      lines.push('Top-3 concentration ' + top3.toFixed(0) + '% — ' + (top3 <= 25 ? 'diversified' : top3 <= 45 ? 'monitor' : '<span style="color:#b91c1c;font-weight:600">concentrated</span>') + '.');
    }
    lines.push('</p>');
  }

  if (avgGm != null) {
    lines.push('<p><strong>Margin' + scope + ':</strong> Blended GM ' + avgGm.toFixed(0) + '% ');
    lines.push(avgGm >= 35 ? '(healthy)' : avgGm >= 20 ? '(moderate — distribution typical)' : '(<span style="color:#b91c1c">thin</span>)');
    lines.push('.</p>');
  }

  if (!_IA.segFilter && flags.length) {
    lines.push('<p><strong>Risk: ' + (highFlags > 0 ? '<span style="color:#b91c1c">Elevated</span>' : 'Moderate') + '.</strong> ');
    lines.push(flags.length + ' findings (' + highFlags + ' HIGH). ');
    if (highFlags > 0) {
      var topFlag = flags.filter(function(f){return f.severity==='HIGH';})[0];
      lines.push('"' + (topFlag.finding||'').substring(0,80) + '"');
    }
    lines.push('</p>');
  }

  if (!_IA.segFilter && mc) {
    var p = mc.params || {}, w = mc.waterfall || {};
    var mult = _IA.scenarioMult != null ? _IA.scenarioMult : p.multiple;
    var ebitda = _IA.scenarioEbitda != null ? _IA.scenarioEbitda : (p.ebitda_basis_override != null ? p.ebitda_basis_override : mc.ebitda_basis);
    if (mult != null && ebitda != null) {
      var ev = mult * ebitda;
      lines.push('<p><strong>Valuation: ' + (mult <= 5 ? 'Attractive' : mult <= 6.5 ? 'Fair' : 'Premium') + '.</strong> ');
      lines.push(mult.toFixed(1) + 'x on €' + Math.round(ebitda) + 'K adj. EBITDA = €' + (ev/1000).toFixed(1) + 'M EV');
      if (_IA.scenarioMult != null || _IA.scenarioEbitda != null) {
        lines.push(' <span style="background:#dbeafe;color:#1d4ed8;font-size:10px;padding:1px 6px;border-radius:4px;font-weight:600">SCENARIO</span>');
      }
      lines.push('.</p>');
    }
  }

  lines.push('</div>');
  return lines.join('');
}

// ═══════════════════════════════════════════════════════════════════════════════
// REVENUE BRIDGE WATERFALL — filter-aware
// ═══════════════════════════════════════════════════════════════════════════════
function _insightWaterfall(bridge) {
  if (!bridge || !bridge.length) return '';
  var filtered = bridge;
  if (_IA.yearRange) {
    filtered = bridge.filter(function(b) {
      var yrs = (b.period||'').match(/\d{4}/g);
      if (!yrs) return true;
      return yrs.some(function(y){ return y >= _IA.yearRange[0] && y <= _IA.yearRange[1]; });
    });
  }
  if (!filtered.length) return '<div style="color:#94a3b8;font-size:12px">No bridge data for selected years.</div>';

  var W = 860, H = 280, padL = 64, padR = 20, padT = 30, padB = 50;
  var chartW = W - padL - padR, chartH = H - padT - padB;
  var allVals = [];
  filtered.forEach(function(b) { allVals.push(b.start, b.end, Math.abs(b.churned), Math.abs(b.net_retained), Math.abs(b.new)); });
  var maxVal = Math.max.apply(null, allVals) * 1.15;
  var groupW = chartW / filtered.length;

  var svg = '<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;max-height:'+H+'px;overflow:visible">';
  for (var g = 0; g <= 4; g++) {
    var gy = padT + chartH * (1 - g/4);
    var lbl = Math.round(maxVal * g / 4);
    lbl = lbl >= 1000 ? (lbl/1000).toFixed(1)+'M' : lbl+'K';
    svg += '<line x1="'+padL+'" y1="'+gy.toFixed(1)+'" x2="'+(padL+chartW)+'" y2="'+gy.toFixed(1)+'" stroke="#f1f5f9"/>';
    svg += '<text x="'+(padL-6)+'" y="'+(gy+3.5).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8">'+lbl+'</text>';
  }

  filtered.forEach(function(b, pi) {
    var gx = padL + pi * groupW;
    var barW = Math.min(36, groupW / 6);
    var gap = 3;
    var bars = [
      {label:'Start', val:b.start, color:'#94a3b8', base:0},
      {label:'Churned', val:Math.abs(b.churned), color:'#ef4444', base:b.start - Math.abs(b.churned)},
      {label:'Retained', val:Math.abs(b.net_retained), color: b.net_retained >= 0 ? '#22c55e' : '#f97316', base: b.net_retained >= 0 ? b.start - Math.abs(b.churned) : b.start - Math.abs(b.churned) - Math.abs(b.net_retained)},
      {label:'New', val:b.new, color:'#3b82f6', base: b.end - b.new},
      {label:'End', val:b.end, color:'#475569', base:0},
    ];
    var totalBarsW = bars.length * barW + (bars.length - 1) * gap;
    var startX = gx + (groupW - totalBarsW) / 2;

    bars.forEach(function(bar, bi) {
      var x = startX + bi * (barW + gap);
      var bh = bar.val / maxVal * chartH;
      var y = padT + chartH - bar.base / maxVal * chartH - bh;
      var highlight = '';
      if (bi === 1) highlight = ' onclick="_iaDrill(\'churn\',\''+b.period+'\')" style="cursor:pointer"';
      if (bi === 3) highlight = ' onclick="_iaDrill(\'newcust\',\''+b.period+'\')" style="cursor:pointer"';
      svg += '<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+barW+'" height="'+Math.max(1,bh).toFixed(1)+'" fill="'+bar.color+'" rx="2" opacity="0.85"'+highlight+'>';
      svg += '<title>'+bar.label+': €'+Math.round(bar.val)+'K</title></rect>';
      if (bi === 0 || bi === 4) {
        var valLbl = bar.val >= 1000 ? (bar.val/1000).toFixed(2)+'M' : Math.round(bar.val)+'K';
        svg += '<text x="'+(x+barW/2).toFixed(1)+'" y="'+(y-4).toFixed(1)+'" text-anchor="middle" font-size="8.5" fill="'+bar.color+'" font-weight="600">€'+valLbl+'</text>';
      }
    });

    svg += '<text x="'+(gx+groupW/2).toFixed(1)+'" y="'+(H-28)+'" text-anchor="middle" font-size="10" fill="#334155" font-weight="600">'+b.period+'</text>';
    var deltaK = b.end - b.start;
    var deltaPct = b.start > 0 ? (deltaK / b.start * 100) : 0;
    var dColor = deltaK >= 0 ? '#15803d' : '#b91c1c';
    svg += '<text x="'+(gx+groupW/2).toFixed(1)+'" y="'+(H-14)+'" text-anchor="middle" font-size="9" fill="'+dColor+'" font-weight="700">'+(deltaK>=0?'+':'')+(deltaK>=1000?(deltaK/1000).toFixed(1)+'M':Math.round(deltaK)+'K')+' ('+(deltaPct>=0?'+':'')+deltaPct.toFixed(0)+'%)</text>';
  });

  svg += '</svg>';
  var legend = '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:6px;font-size:10px;color:#64748b">';
  [{c:'#94a3b8',l:'Start/End'},{c:'#ef4444',l:'Churned (click to drill)'},{c:'#22c55e',l:'Retained exp.'},{c:'#f97316',l:'Retained contr.'},{c:'#3b82f6',l:'New (click to drill)'}].forEach(function(i) {
    legend += '<span style="display:flex;align-items:center;gap:4px"><span style="width:9px;height:9px;border-radius:2px;background:'+i.c+';display:inline-block"></span>'+i.l+'</span>';
  });
  legend += '</div>';
  return svg + legend;
}

// ═══════════════════════════════════════════════════════════════════════════════
// DRILL-THROUGH PANEL — expands below any chart
// ═══════════════════════════════════════════════════════════════════════════════
function _iaDrill(type, context) {
  var el = document.getElementById('ia-drill');
  if (!el) return;
  if (_IA.drillTarget === type + ':' + context) { el.innerHTML = ''; _IA.drillTarget = null; return; }
  _IA.drillTarget = type + ':' + context;

  var cdd = DATA.cdd || {};
  var h = '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:14px 16px;margin-top:12px;animation:fadeIn .3s">';
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">';
  h += '<span style="font-size:12px;font-weight:700;color:#0369a1;text-transform:uppercase;letter-spacing:.4px">';

  if (type === 'churn') {
    h += 'Churn Analysis — ' + context + '</span>';
    h += '<button onclick="document.getElementById(\'ia-drill\').innerHTML=\'\';_IA.drillTarget=null" style="border:none;background:none;cursor:pointer;color:#94a3b8;font-size:14px">&times;</button></div>';
    var bridge = (cdd.churn || {}).bridge || [];
    var b = bridge.filter(function(x){return x.period === context;})[0];
    if (b) {
      var churnRate = b.start > 0 ? (Math.abs(b.churned) / b.start * 100) : 0;
      h += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">';
      h += _afChip('Churned Revenue', '€' + Math.round(Math.abs(b.churned)) + 'K', churnRate > 20 ? 'red' : churnRate > 10 ? 'yellow' : 'green', churnRate.toFixed(1) + '% of start-of-period revenue');
      h += _afChip('Start Revenue', '€' + Math.round(b.start) + 'K', 'grey');
      h += _afChip('Churn Rate', churnRate.toFixed(1) + '%', churnRate > 20 ? 'red' : churnRate > 10 ? 'yellow' : 'green');
      h += '</div>';
      h += '<div style="font-size:12px;color:#334155;line-height:1.6">';
      h += '<strong>Investor implication:</strong> ';
      if (churnRate > 20) h += 'Churn above 20% is a structural concern. The customer base is not sticky — new revenue must replace a large outflow each period. Due diligence should focus on contract terms, switching costs, and competitive alternatives.';
      else if (churnRate > 10) h += 'Moderate churn indicates some customer turnover. Check whether churn concentrates in specific segments or is evenly distributed.';
      else h += 'Low churn suggests a sticky customer base with good retention dynamics.';
      h += '</div>';
    }
    var cohorts = cdd.cohorts || [];
    if (cohorts.length) {
      h += '<div style="margin-top:10px;font-size:11px;font-weight:700;color:#0369a1;margin-bottom:4px">COHORT DETAIL</div>';
      h += '<div style="overflow-x:auto"><table style="font-size:11px;border-collapse:collapse;width:100%">';
      h += '<tr style="background:#e0f2fe"><th style="padding:4px 8px;text-align:left;border-bottom:1px solid #bae6fd">Cohort</th><th style="padding:4px 8px;text-align:right;border-bottom:1px solid #bae6fd">Start</th><th style="padding:4px 8px;text-align:right;border-bottom:1px solid #bae6fd">Retained</th><th style="padding:4px 8px;text-align:right;border-bottom:1px solid #bae6fd">Rate</th></tr>';
      cohorts.forEach(function(c) {
        var rate = c.start_count > 0 ? (c.retained_count / c.start_count * 100) : 0;
        h += '<tr><td style="padding:3px 8px;border-bottom:1px solid #f1f5f9">' + (c.cohort||c.period||'') + '</td>';
        h += '<td style="padding:3px 8px;text-align:right;border-bottom:1px solid #f1f5f9">' + (c.start_count||0) + '</td>';
        h += '<td style="padding:3px 8px;text-align:right;border-bottom:1px solid #f1f5f9">' + (c.retained_count||0) + '</td>';
        h += '<td style="padding:3px 8px;text-align:right;border-bottom:1px solid #f1f5f9;color:' + (rate >= 80 ? '#15803d' : rate >= 65 ? '#b45309' : '#b91c1c') + ';font-weight:600">' + rate.toFixed(0) + '%</td></tr>';
      });
      h += '</table></div>';
    }
    h += '<div style="margin-top:8px"><button onclick="showSection(\'customers\')" style="border:none;background:#0891B2;color:#fff;border-radius:6px;padding:4px 12px;font-size:11px;font-weight:600;cursor:pointer">Full Customer Analysis →</button></div>';

  } else if (type === 'newcust') {
    h += 'New Customer Acquisition — ' + context + '</span>';
    h += '<button onclick="document.getElementById(\'ia-drill\').innerHTML=\'\';_IA.drillTarget=null" style="border:none;background:none;cursor:pointer;color:#94a3b8;font-size:14px">&times;</button></div>';
    var bridge2 = (cdd.churn || {}).bridge || [];
    var b2 = bridge2.filter(function(x){return x.period === context;})[0];
    if (b2) {
      var newShare = b2.end > 0 ? (b2.new / b2.end * 100) : 0;
      h += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">';
      h += _afChip('New Revenue', '€' + Math.round(b2.new) + 'K', 'grey');
      h += _afChip('New as % of End', newShare.toFixed(0) + '%', newShare > 30 ? 'yellow' : 'green', 'High % = growth depends on new acquisition');
      h += _afChip('Net Growth', '€' + Math.round(b2.end - b2.start) + 'K', b2.end >= b2.start ? 'green' : 'red');
      h += '</div>';
      h += '<div style="font-size:12px;color:#334155;line-height:1.6">';
      h += '<strong>Growth quality:</strong> ';
      if (newShare > 40) h += 'Over 40% of period-end revenue comes from new customers. This is acquisition-heavy growth — more expensive (CAC) and less predictable. The business must continuously acquire to maintain revenue.';
      else if (newShare > 20) h += 'Balanced mix of retained and new revenue. Growth is healthy if retention stays stable.';
      else h += 'Strong retained base with new customers adding incremental growth. This is the healthiest pattern.';
      h += '</div>';
    }
    var typeSplit = cdd.type_split || {};
    if (typeSplit.years && typeSplit.new_rev) {
      h += '<div style="margin-top:10px;font-size:11px;font-weight:700;color:#0369a1;margin-bottom:4px">NEW vs EXISTING REVENUE TREND</div>';
      h += '<div style="display:flex;gap:6px;flex-wrap:wrap">';
      (typeSplit.years||[]).forEach(function(y) {
        var nv = (typeSplit.new_rev||{})[y] || 0;
        var ev = (typeSplit.existing_rev||{})[y] || 0;
        var tot = nv + ev;
        var newPct = tot > 0 ? (nv/tot*100) : 0;
        h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;min-width:80px;text-align:center">';
        h += '<div style="font-size:10px;font-weight:600;color:#64748b">' + y + '</div>';
        h += '<div style="font-size:14px;font-weight:700;color:#1e293b">' + newPct.toFixed(0) + '%</div>';
        h += '<div style="font-size:9px;color:#94a3b8">new</div>';
        h += '</div>';
      });
      h += '</div>';
    }

  } else if (type === 'segment') {
    h += 'Segment Deep-Dive — ' + context + '</span>';
    h += '<button onclick="document.getElementById(\'ia-drill\').innerHTML=\'\';_IA.drillTarget=null" style="border:none;background:none;cursor:pointer;color:#94a3b8;font-size:14px">&times;</button></div>';
    var seg = cdd.segments ? cdd.segments.rows.filter(function(s){return s.name===context;})[0] : null;
    if (seg) {
      var latest = String(cdd.segments.latest_full_year);
      var gm = seg.gm_pct[latest], rv = seg.rev[latest];
      h += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">';
      h += _afChip('Revenue '+latest, rv != null ? '€'+Math.round(rv)+'K' : '—', 'grey');
      h += _afChip('GM%', gm != null ? gm.toFixed(0)+'%' : '—', gm==null?'grey':gm>=35?'green':gm>=20?'yellow':'red');
      h += _afChip('CAGR', seg.cagr != null ? (seg.cagr>0?'+':'')+seg.cagr.toFixed(1)+'%' : '—', seg.cagr==null?'grey':seg.cagr>=5?'green':seg.cagr>=0?'yellow':'red');
      h += _afChip('Share', (seg.share_latest||0).toFixed(0)+'%', 'grey');
      h += '</div>';

      // Revenue time series for this segment
      h += '<div style="font-size:11px;font-weight:700;color:#0369a1;margin-bottom:4px">REVENUE TRAJECTORY</div>';
      h += '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">';
      cdd.segments.years.forEach(function(y) {
        var val = seg.rev[String(y)];
        var prevY = cdd.segments.years[cdd.segments.years.indexOf(y)-1];
        var prevVal = prevY ? seg.rev[String(prevY)] : null;
        var yoyPct = (prevVal && val != null) ? ((val - prevVal) / prevVal * 100) : null;
        h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;min-width:70px;text-align:center">';
        h += '<div style="font-size:10px;font-weight:600;color:#64748b">' + y + '</div>';
        h += '<div style="font-size:13px;font-weight:700;color:#1e293b">' + (val != null ? '€'+Math.round(val)+'K' : '—') + '</div>';
        if (yoyPct != null) h += '<div style="font-size:9px;color:' + (yoyPct >= 0 ? '#15803d' : '#b91c1c') + ';font-weight:600">' + (yoyPct>=0?'+':'') + yoyPct.toFixed(0) + '%</div>';
        h += '</div>';
      });
      h += '</div>';

      var flags = (cdd.findings || {}).red_flags || [];
      var related = flags.filter(function(f) { return f.finding && f.finding.toLowerCase().indexOf(context.toLowerCase()) >= 0; });
      if (related.length) {
        h += '<div style="font-size:11px;font-weight:700;color:#b91c1c;margin-bottom:4px">RELATED RED FLAGS</div>';
        related.forEach(function(f) {
          h += '<div style="font-size:12px;color:#334155;padding:3px 0">- ' + f.finding + (f.severity === 'HIGH' ? ' <span style="color:#b91c1c;font-weight:600">[HIGH]</span>' : '') + '</div>';
        });
      }
      h += '<div style="margin-top:8px;display:flex;gap:8px">';
      h += '<button onclick="_iaToggleSegFilter(\''+_iaEsc(context).replace(/'/g,"\\'")+'\')" style="border:none;background:#0891B2;color:#fff;border-radius:6px;padding:4px 12px;font-size:11px;font-weight:600;cursor:pointer">Filter All Charts to '+_iaEsc(context)+' →</button>';
      h += '<button onclick="showSection(\'business_model\')" style="border:1px solid #0891B2;background:#fff;color:#0891B2;border-radius:6px;padding:4px 12px;font-size:11px;font-weight:600;cursor:pointer">Business Model →</button>';
      h += '</div>';
    }
  }

  h += '</div>';
  el.innerHTML = h;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SEGMENT RISK MATRIX — clickable bubbles → drill panel
// ═══════════════════════════════════════════════════════════════════════════════
function _insightSegMatrix(segments) {
  if (!segments || !segments.rows || !segments.rows.length) return '';
  var latest = String(segments.latest_full_year);
  var W = 500, H = 320, padL = 50, padR = 30, padT = 20, padB = 40;
  var chartW = W - padL - padR, chartH = H - padT - padB;

  var data = segments.rows.map(function(s, i) {
    var gm = s.gm_pct[latest];
    var cagr = s.cagr;
    var share = s.share_latest || 0;
    return {name: s.name, cagr: cagr, gm: gm, share: share, color: _CDD_PALETTE[i % _CDD_PALETTE.length]};
  }).filter(function(d) { return d.cagr != null && d.gm != null; });

  if (!data.length) return '';

  var minCagr = Infinity, maxCagr = -Infinity, minGm = Infinity, maxGm = -Infinity;
  data.forEach(function(d) {
    if (d.cagr < minCagr) minCagr = d.cagr;
    if (d.cagr > maxCagr) maxCagr = d.cagr;
    if (d.gm < minGm) minGm = d.gm;
    if (d.gm > maxGm) maxGm = d.gm;
  });
  var xMin = Math.min(minCagr - 5, -10), xMax = Math.max(maxCagr + 5, 20);
  var yMin = Math.min(minGm - 5, 0), yMax = Math.max(maxGm + 5, 100);

  var svg = '<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;max-height:'+H+'px;overflow:visible">';
  var x0line = padL + (0 - xMin) / (xMax - xMin) * chartW;
  var yAvgGm = padT + chartH - (50 - yMin) / (yMax - yMin) * chartH;
  svg += '<rect x="'+x0line.toFixed(1)+'" y="'+padT+'" width="'+(padL+chartW-x0line).toFixed(1)+'" height="'+(yAvgGm-padT).toFixed(1)+'" fill="#f0fdf4" opacity="0.4"/>';
  svg += '<text x="'+(padL+chartW-4)+'" y="'+(padT+12)+'" text-anchor="end" font-size="8" fill="#86efac" font-weight="600">STARS</text>';
  svg += '<rect x="'+padL+'" y="'+padT+'" width="'+(x0line-padL).toFixed(1)+'" height="'+(yAvgGm-padT).toFixed(1)+'" fill="#fffbeb" opacity="0.3"/>';
  svg += '<text x="'+(padL+4)+'" y="'+(padT+12)+'" font-size="8" fill="#fde68a" font-weight="600">MARGIN ONLY</text>';
  svg += '<rect x="'+padL+'" y="'+yAvgGm.toFixed(1)+'" width="'+(x0line-padL).toFixed(1)+'" height="'+(padT+chartH-yAvgGm).toFixed(1)+'" fill="#fef2f2" opacity="0.3"/>';
  svg += '<text x="'+(padL+4)+'" y="'+(padT+chartH-4)+'" font-size="8" fill="#fecaca" font-weight="600">DOGS</text>';
  svg += '<rect x="'+x0line.toFixed(1)+'" y="'+yAvgGm.toFixed(1)+'" width="'+(padL+chartW-x0line).toFixed(1)+'" height="'+(padT+chartH-yAvgGm).toFixed(1)+'" fill="#dbeafe" opacity="0.3"/>';
  svg += '<text x="'+(padL+chartW-4)+'" y="'+(padT+chartH-4)+'" text-anchor="end" font-size="8" fill="#93c5fd" font-weight="600">GROWTH ONLY</text>';
  svg += '<line x1="'+padL+'" y1="'+(padT+chartH)+'" x2="'+(padL+chartW)+'" y2="'+(padT+chartH)+'" stroke="#e2e8f0"/>';
  svg += '<line x1="'+padL+'" y1="'+padT+'" x2="'+padL+'" y2="'+(padT+chartH)+'" stroke="#e2e8f0"/>';
  svg += '<line x1="'+x0line.toFixed(1)+'" y1="'+padT+'" x2="'+x0line.toFixed(1)+'" y2="'+(padT+chartH)+'" stroke="#cbd5e1" stroke-dasharray="4,3"/>';
  svg += '<line x1="'+padL+'" y1="'+yAvgGm.toFixed(1)+'" x2="'+(padL+chartW)+'" y2="'+yAvgGm.toFixed(1)+'" stroke="#cbd5e1" stroke-dasharray="4,3"/>';
  svg += '<text x="'+(padL+chartW/2)+'" y="'+(H-4)+'" text-anchor="middle" font-size="10" fill="#64748b">Revenue CAGR (%)</text>';
  svg += '<text x="12" y="'+(padT+chartH/2)+'" text-anchor="middle" font-size="10" fill="#64748b" transform="rotate(-90 12 '+(padT+chartH/2)+')">Gross Margin (%, '+latest+')</text>';
  for (var xt = Math.ceil(xMin/10)*10; xt <= xMax; xt += 10) {
    var xx = padL + (xt - xMin) / (xMax - xMin) * chartW;
    svg += '<text x="'+xx.toFixed(1)+'" y="'+(padT+chartH+14)+'" text-anchor="middle" font-size="9" fill="#94a3b8">'+(xt>0?'+':'')+xt+'%</text>';
  }
  for (var yt = Math.ceil(yMin/20)*20; yt <= yMax; yt += 20) {
    var yy = padT + chartH - (yt - yMin) / (yMax - yMin) * chartH;
    svg += '<text x="'+(padL-6)+'" y="'+(yy+3.5).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8">'+yt+'%</text>';
  }

  data.forEach(function(d) {
    var cx = padL + (d.cagr - xMin) / (xMax - xMin) * chartW;
    var cy = padT + chartH - (d.gm - yMin) / (yMax - yMin) * chartH;
    var r = Math.max(8, Math.min(28, Math.sqrt(d.share) * 7));
    var isActive = !_IA.segFilter || _IA.segFilter === d.name;
    var opacity = isActive ? '0.8' : '0.2';
    svg += '<circle cx="'+cx.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r="'+r.toFixed(1)+'" fill="'+d.color+'" opacity="'+opacity+'" stroke="'+d.color+'" stroke-width="'+(isActive?'2':'0.5')+'" style="cursor:pointer;transition:opacity .2s" '
      + 'onclick="_iaDrill(\'segment\',\''+_iaEsc(d.name).replace(/'/g,"\\'")+'\')">'
      + '<title>'+_iaEsc(d.name)+'\nCAGR: '+(d.cagr>0?'+':'')+d.cagr.toFixed(0)+'%\nGM: '+d.gm.toFixed(0)+'%\nShare: '+d.share.toFixed(0)+'%</title></circle>';
    if (r >= 10 && isActive) {
      var shortName = d.name.length > 12 ? d.name.substring(0,10)+'..' : d.name;
      svg += '<text x="'+cx.toFixed(1)+'" y="'+(cy+3).toFixed(1)+'" text-anchor="middle" font-size="8" fill="#fff" font-weight="600" pointer-events="none">'+_iaEsc(shortName)+'</text>';
    }
  });
  svg += '</svg>';
  return svg;
}

// ═══════════════════════════════════════════════════════════════════════════════
// GROWTH DECOMPOSITION — filter-aware cards
// ═══════════════════════════════════════════════════════════════════════════════
function _insightGrowthDecomp(bridge, retention) {
  if (!bridge || !bridge.length) return '';
  var filtered = bridge;
  if (_IA.yearRange) {
    filtered = bridge.filter(function(b) {
      var yrs = (b.period||'').match(/\d{4}/g);
      if (!yrs) return true;
      return yrs.some(function(y){ return y >= _IA.yearRange[0] && y <= _IA.yearRange[1]; });
    });
  }
  if (!filtered.length) return '';
  var h = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">';
  filtered.forEach(function(b) {
    var delta = b.end - b.start;
    var newPct = b.end > 0 ? (b.new / b.end * 100) : 0;
    var growthSource = delta > 0 ? (b.new > Math.abs(b.net_retained) && b.new > Math.abs(b.churned) ? 'New-customer driven' : b.net_retained > b.new ? 'Expansion-driven' : 'Mixed') : 'Contracting';
    var verdict = delta > 0 ? (newPct > 30 ? 'yellow' : 'green') : 'red';

    h += '<div style="background:'+_afColor(verdict).bg+';border:1px solid '+_afColor(verdict).border+';border-radius:8px;padding:12px 14px;flex:1;min-width:200px;cursor:pointer;transition:all .15s" onclick="_iaDrill(\'newcust\',\''+b.period+'\')" onmouseover="this.style.transform=\'translateY(-2px)\';this.style.boxShadow=\'0 4px 12px rgba(0,0,0,0.08)\'" onmouseout="this.style.transform=\'\';this.style.boxShadow=\'\'">';
    h += '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:'+_afColor(verdict).text+'">'+b.period+'</div>';
    h += '<div style="font-size:18px;font-weight:700;color:#1e293b;margin:4px 0">'+(delta>=0?'+':'')+'€'+Math.round(Math.abs(delta))+'K</div>';
    h += '<div style="font-size:11px;color:#64748b;line-height:1.5">'+growthSource+'<br>';
    h += '<span style="color:#ef4444">−€'+Math.round(Math.abs(b.churned))+'K</span>';
    h += ' · <span style="color:'+(b.net_retained>=0?'#22c55e':'#f97316')+'">'+(b.net_retained>=0?'+':'')+'€'+Math.round(Math.abs(b.net_retained))+'K</span>';
    h += ' · <span style="color:#3b82f6">+€'+Math.round(b.new)+'K</span>';
    h += '</div></div>';
  });
  h += '</div>';
  return h;
}

// ═══════════════════════════════════════════════════════════════════════════════
// EBITDA BRIDGE — with bar chart visualization
// ═══════════════════════════════════════════════════════════════════════════════
function _insightEbitdaBridge(fin) {
  if (!fin || !fin.ebitda_bridge) return '';
  var eb = fin.ebitda_bridge;
  var years = Object.keys(eb).sort();
  if (_IA.yearRange) years = years.filter(function(y){ return y >= _IA.yearRange[0] && y <= _IA.yearRange[1]; });
  if (years.length < 1) return '';

  var maxVal = 0;
  years.forEach(function(y) { var d = eb[y]; if (d && d.adjusted > maxVal) maxVal = d.adjusted; if (d && d.raw > maxVal) maxVal = d.raw; });

  var h = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">';
  years.forEach(function(y) {
    var d = eb[y];
    if (!d) return;
    var raw = d.raw, adj = d.adjusted, delta = d.delta;
    var hasAdj = adj != null && adj !== 'None';
    var hasRaw = raw != null && raw !== 'None';
    var hasDelta = delta != null && delta !== 'None';
    if (!hasAdj) return;

    var barH = maxVal > 0 ? (adj / maxVal * 60) : 20;
    var rawBarH = (hasRaw && maxVal > 0) ? (raw / maxVal * 60) : 0;

    h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;min-width:120px;flex:1;max-width:160px">';
    h += '<div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px">' + y + '</div>';
    h += '<div style="display:flex;gap:4px;align-items:flex-end;height:65px;margin-bottom:4px">';
    if (hasRaw) h += '<div style="width:20px;background:#e2e8f0;border-radius:2px 2px 0 0;height:'+Math.max(2,rawBarH)+'px" title="Raw: €'+Math.round(raw)+'K"></div>';
    h += '<div style="width:20px;background:#0891B2;border-radius:2px 2px 0 0;height:'+Math.max(2,barH)+'px" title="Adjusted: €'+Math.round(adj)+'K"></div>';
    h += '</div>';
    h += '<div style="font-size:14px;font-weight:700;color:#1e293b">€'+Math.round(adj)+'K</div>';
    if (hasRaw && hasDelta) {
      var c = delta >= 0 ? '#15803d' : '#b91c1c';
      h += '<div style="font-size:10px;color:'+c+'">'+(delta>=0?'+':'')+'€'+Math.round(delta)+'K adj.</div>';
    }
    h += '</div>';
  });
  h += '</div>';

  var legend = '<div style="display:flex;gap:12px;font-size:10px;color:#64748b">';
  legend += '<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;background:#e2e8f0;border-radius:2px;display:inline-block"></span>Raw EBITDA</span>';
  legend += '<span style="display:flex;align-items:center;gap:4px"><span style="width:10px;height:10px;background:#0891B2;border-radius:2px;display:inline-block"></span>Adjusted EBITDA</span>';
  legend += '</div>';
  return h + legend;
}

// ═══════════════════════════════════════════════════════════════════════════════
// VALUATION SCENARIO PANEL — interactive sliders
// ═══════════════════════════════════════════════════════════════════════════════
function _insightScenario(mc) {
  if (!mc || !mc.params) return '';
  var p = mc.params, w = mc.waterfall || {};
  var baseMult = p.multiple || 5;
  var baseEbitda = p.ebitda_basis_override != null ? p.ebitda_basis_override : mc.ebitda_basis;
  if (baseEbitda == null) return '';

  var curMult = _IA.scenarioMult != null ? _IA.scenarioMult : baseMult;
  var curEbitda = _IA.scenarioEbitda != null ? _IA.scenarioEbitda : baseEbitda;
  var ev = curMult * curEbitda;
  var baseEv = baseMult * baseEbitda;
  var evDelta = ev - baseEv;
  var netDebt = (w.net_debt || 0);
  var equity = ev - netDebt;
  var baseEquity = baseEv - netDebt;
  var eqDelta = equity - baseEquity;
  var isScenario = _IA.scenarioMult != null || _IA.scenarioEbitda != null;

  var h = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">';

  // Sliders column
  h += '<div>';
  h += '<div style="margin-bottom:14px">';
  h += '<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px"><span style="color:#64748b;font-weight:600">EV/EBITDA Multiple</span><span style="color:#1e293b;font-weight:700" id="ia-mult-val">' + curMult.toFixed(1) + 'x</span></div>';
  h += '<input type="range" id="ia-mult-slider" min="2" max="10" step="0.1" value="' + curMult.toFixed(1) + '" style="width:100%;accent-color:#0891B2">';
  h += '<div style="display:flex;justify-content:space-between;font-size:9px;color:#94a3b8"><span>2.0x</span><span style="color:#0891B2;font-weight:600">Base: ' + baseMult.toFixed(1) + 'x</span><span>10.0x</span></div>';
  h += '</div>';

  h += '<div style="margin-bottom:14px">';
  h += '<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px"><span style="color:#64748b;font-weight:600">Adj. EBITDA Basis (€K)</span><span style="color:#1e293b;font-weight:700" id="ia-ebitda-val">€' + Math.round(curEbitda) + 'K</span></div>';
  var eMin = Math.round(baseEbitda * 0.5), eMax = Math.round(baseEbitda * 1.5);
  h += '<input type="range" id="ia-ebitda-slider" min="' + eMin + '" max="' + eMax + '" step="5" value="' + Math.round(curEbitda) + '" style="width:100%;accent-color:#0891B2">';
  h += '<div style="display:flex;justify-content:space-between;font-size:9px;color:#94a3b8"><span>€' + eMin + 'K</span><span style="color:#0891B2;font-weight:600">Base: €' + Math.round(baseEbitda) + 'K</span><span>€' + eMax + 'K</span></div>';
  h += '</div>';

  if (isScenario) {
    h += '<button onclick="_IA.scenarioMult=null;_IA.scenarioEbitda=null;_iaRerender()" style="border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:4px 12px;font-size:11px;font-weight:600;color:#64748b;cursor:pointer">Reset to Base Case</button>';
  }
  h += '</div>';

  // Results column
  h += '<div id="ia-scenario-results" style="display:flex;flex-direction:column;gap:8px">';
  h += '<div style="background:' + (isScenario ? '#dbeafe' : '#f8fafc') + ';border:1px solid ' + (isScenario ? '#93c5fd' : '#e2e8f0') + ';border-radius:8px;padding:12px 16px">';
  h += '<div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.4px">Enterprise Value</div>';
  h += '<div class="ia-ev-val" style="font-size:22px;font-weight:700;color:#1e293b">€' + (ev/1000).toFixed(1) + 'M</div>';
  if (isScenario) {
    h += '<div style="font-size:11px;color:' + (evDelta >= 0 ? '#15803d' : '#b91c1c') + ';font-weight:600">' + (evDelta>=0?'+':'') + '€' + Math.round(evDelta) + 'K vs base</div>';
  }
  h += '</div>';
  h += '<div style="background:' + (isScenario ? '#dbeafe' : '#f8fafc') + ';border:1px solid ' + (isScenario ? '#93c5fd' : '#e2e8f0') + ';border-radius:8px;padding:12px 16px">';
  h += '<div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.4px">Equity Value</div>';
  h += '<div class="ia-eq-val" style="font-size:22px;font-weight:700;color:#1e293b">€' + (equity/1000).toFixed(1) + 'M</div>';
  if (isScenario && netDebt) {
    h += '<div style="font-size:11px;color:' + (eqDelta >= 0 ? '#15803d' : '#b91c1c') + ';font-weight:600">' + (eqDelta>=0?'+':'') + '€' + Math.round(eqDelta) + 'K vs base</div>';
    h += '<div style="font-size:10px;color:#94a3b8;margin-top:2px">Net debt: €' + Math.round(netDebt) + 'K</div>';
  }
  h += '</div>';
  if (isScenario) {
    h += '<div style="background:#fffbeb;border:1px solid #fef08a;border-radius:6px;padding:8px 12px;font-size:11px;color:#92400e;line-height:1.5">';
    h += '<strong>Scenario mode</strong> — narrative and snapshot update in real-time. ';
    var multChg = ((curMult - baseMult) / baseMult * 100);
    var ebitdaChg = ((curEbitda - baseEbitda) / baseEbitda * 100);
    if (Math.abs(multChg) > 0.5) h += 'Multiple ' + (multChg > 0 ? '+' : '') + multChg.toFixed(0) + '% vs base. ';
    if (Math.abs(ebitdaChg) > 0.5) h += 'EBITDA ' + (ebitdaChg > 0 ? '+' : '') + ebitdaChg.toFixed(0) + '% vs base.';
    h += '</div>';
  }
  h += '</div>';
  h += '</div>';
  return h;
}

function _iaBindScenarioSliders() {
  var multSlider = document.getElementById('ia-mult-slider');
  var ebitdaSlider = document.getElementById('ia-ebitda-slider');
  var mc = (DATA || {}).model_context || {};
  var p = mc.params || {};
  var baseMult = p.multiple || 5;
  var baseEbitda = p.ebitda_basis_override != null ? p.ebitda_basis_override : mc.ebitda_basis;

  if (multSlider) {
    multSlider.oninput = function() {
      var v = parseFloat(this.value);
      document.getElementById('ia-mult-val').textContent = v.toFixed(1) + 'x';
      _IA.scenarioMult = Math.abs(v - baseMult) < 0.05 ? null : v;
      _iaUpdateScenarioResults();
    };
  }
  if (ebitdaSlider) {
    ebitdaSlider.oninput = function() {
      var v = parseFloat(this.value);
      document.getElementById('ia-ebitda-val').textContent = '€' + Math.round(v) + 'K';
      _IA.scenarioEbitda = Math.abs(v - baseEbitda) < 3 ? null : v;
      _iaUpdateScenarioResults();
    };
  }
}

function _iaUpdateScenarioResults() {
  var mc = (DATA || {}).model_context || {};
  var p = mc.params || {}, w = mc.waterfall || {};
  var baseMult = p.multiple || 5;
  var baseEbitda = p.ebitda_basis_override != null ? p.ebitda_basis_override : mc.ebitda_basis;
  var curMult = _IA.scenarioMult != null ? _IA.scenarioMult : baseMult;
  var curEbitda = _IA.scenarioEbitda != null ? _IA.scenarioEbitda : baseEbitda;
  var ev = curMult * curEbitda;

  // Update the scenario results without full rerender (for smooth slider UX)
  var el = document.getElementById('ia-scenario-results');
  if (el) {
    var netDebt = w.net_debt || 0;
    var equity = ev - netDebt;
    el.querySelector('.ia-ev-val').textContent = '€' + (ev/1000).toFixed(1) + 'M';
    el.querySelector('.ia-eq-val').textContent = '€' + (equity/1000).toFixed(1) + 'M';
  }
  // Also live-update the Deal Snapshot bar
  var snapEl = document.getElementById('ia-snapshot-ev');
  if (snapEl) snapEl.textContent = curMult.toFixed(1) + 'x';
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN RENDERER — assembles all panels
// ═══════════════════════════════════════════════════════════════════════════════
function renderAnalysis() {
  var cdd = DATA.cdd;
  var mc = DATA.model_context || null;
  var fin = DATA.financials || {};

  if (!cdd || !cdd.segments) {
    return '<div class="stub"><h3>Investment Analysis</h3><p>No CDD data loaded.</p></div>';
  }

  var h = '<div id="ia-root">';
  h += _iaRenderInner();
  h += '</div>';

  return h;
}

function _iaRenderInner() {
  var cdd = DATA.cdd;
  var mc = DATA.model_context || null;
  var fin = DATA.financials || {};
  var h = '';

  // Header
  h += '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">';
  h += '<h2 style="margin:0;font-size:18px;color:#1e293b">Investment Analysis</h2>';
  h += '<span style="font-size:11px;color:#94a3b8">'+((cdd.meta||{}).invoice_count||0).toLocaleString('en-US')+' invoices / '+(cdd.meta.customer_count||0)+' customers / '+Object.keys(fin.pnl||{}).length+' years</span>';
  if (_IA.yearRange) {
    h += '<span style="background:#dbeafe;color:#1d4ed8;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600">YEAR FILTER</span>';
  }
  if (_IA.segFilter) {
    h += '<span style="background:#e0e7ff;color:#4338ca;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600">SEGMENT: '+_iaEsc(_IA.segFilter)+'</span>';
  }
  if (_IA.scenarioMult != null || _IA.scenarioEbitda != null) {
    h += '<span style="background:#fef3c7;color:#92400e;font-size:10px;padding:2px 8px;border-radius:4px;font-weight:600">SCENARIO</span>';
  }
  h += '</div>';

  // Filter bar
  h += _iaFilterBar(cdd);

  // Deal Snapshot (answer-first chips)
  if (typeof renderAnswerFirstBar === 'function') {
    var signals = _afCddSignals(cdd).concat(_afFinancialSignals(mc));
    h += renderAnswerFirstBar(signals, {title: 'Deal Snapshot'});
  }

  // Investment Narrative
  h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:20px;overflow:hidden">';
  h += '<div style="background:#1e293b;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">Investment Narrative' + (_IA.segFilter ? ' — ' + _IA.segFilter : '') + '</div>';
  h += '<div style="padding:16px">' + _insightNarrative(cdd, mc, fin) + '</div>';
  h += '</div>';

  // Revenue Bridge
  h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:20px;overflow:hidden">';
  h += '<div style="background:#0891B2;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;display:flex;align-items:center;gap:8px">Revenue Bridge — Where Growth Comes From';
  if (_IA.segFilter) h += '<span style="font-size:9px;font-weight:400;opacity:.7">(all segments — bridge data is pre-aggregated)</span>';
  h += '</div>';
  h += '<div style="padding:16px">';
  h += _insightGrowthDecomp((cdd.churn||{}).bridge, cdd.retention);
  h += '<div style="margin-top:12px">' + _insightWaterfall((cdd.churn||{}).bridge) + '</div>';
  h += '<div id="ia-drill"></div>';
  h += '</div></div>';

  // Two-column: Segment Matrix + Valuation Scenario
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">';

  // Segment Matrix
  h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">';
  h += '<div style="background:#0891B2;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">Segment Risk Matrix</div>';
  h += '<div style="padding:16px">';
  h += _insightSegMatrix(cdd.segments);
  h += '<div style="font-size:10px;color:#94a3b8;margin-top:6px">Click bubble to drill down. Segment filter scopes narrative + matrix; year filter scopes all panels.</div>';
  h += '</div></div>';

  // Valuation Scenario or EBITDA Bridge
  if (mc && mc.params && mc.params.multiple != null) {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">';
    h += '<div style="background:#1e293b;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">Valuation Scenario</div>';
    h += '<div style="padding:16px">' + _insightScenario(mc) + '</div>';
    h += '</div>';
  } else {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">';
    h += '<div style="background:#0891B2;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">EBITDA Bridge</div>';
    h += '<div style="padding:16px">' + _insightEbitdaBridge(fin) + '</div>';
    h += '</div>';
  }
  h += '</div>';

  // EBITDA Bridge (always show, below if valuation scenario is above)
  if (mc && mc.params && mc.params.multiple != null) {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:20px;overflow:hidden">';
    h += '<div style="background:#0891B2;color:#fff;padding:8px 16px;font-size:13px;font-weight:700;letter-spacing:.4px;text-transform:uppercase">EBITDA Bridge — Raw vs Adjusted</div>';
    h += '<div style="padding:16px">';
    h += _insightEbitdaBridge(fin);
    var eb = fin.ebitda_bridge || {};
    var adjYears = Object.keys(eb).filter(function(y) { return eb[y] && eb[y].delta != null && eb[y].delta !== 'None'; });
    if (adjYears.length) {
      var totalDelta = 0;
      adjYears.forEach(function(y) { totalDelta += eb[y].delta; });
      var avgDelta = totalDelta / adjYears.length;
      h += '<div style="margin-top:10px;font-size:12px;color:#475569;line-height:1.6">';
      h += 'Average annual adjustment: <strong>'+(avgDelta>=0?'+':'')+'€'+Math.round(avgDelta)+'K</strong>';
      if (Math.abs(avgDelta) > 100) h += ' — <span style="color:#b91c1c;font-weight:600">material</span>, verify each line';
      else if (Math.abs(avgDelta) > 30) h += ' — moderate, typical for owner-managed';
      else h += ' — minimal';
      h += '.</div>';
    }
    h += '</div></div>';
  }

  // Data quality warnings
  var gaps = ((cdd.findings||{}).gaps||[]);
  if (gaps.length) {
    h += '<div style="background:#fffbeb;border:1px solid #fef08a;border-radius:8px;padding:12px 16px;margin-bottom:20px">';
    h += '<div style="font-size:10px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Data Quality Warnings</div>';
    h += '<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#78350f">';
    gaps.forEach(function(g) { h += '<span>' + (g.severity==='HIGH'?'!':'*') + ' '+g.item+': '+(g.description||'').substring(0,60)+'</span>'; });
    h += '</div></div>';
  }

  // Navigation
  h += '<div style="display:flex;gap:10px;flex-wrap:wrap">';
  [{s:'business_model',l:'Business Model'},{s:'customers',l:'Customers & Suppliers'},{s:'financials',l:'Valuation & Financials'},{s:'dd',l:'Due Diligence'},{s:'thesis',l:'Thesis & Fit'}].forEach(function(nav) {
    h += '<button onclick="showSection(\''+nav.s+'\')" style="border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:6px 14px;font-size:12px;font-weight:600;color:#0891B2;cursor:pointer;transition:all .15s" '
      + 'onmouseover="this.style.background=\'#f0f9ff\'" onmouseout="this.style.background=\'#fff\'">'
      + nav.l+' →</button>';
  });
  h += '</div>';

  return h;
}
