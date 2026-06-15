// ─── DR-M25 — Commercial DD (computed from deal_invoices + deal_customers) ──
// Dependencies: DATA global, showSubtab(), _wf_kpiCard(), _wf_sectionLabel(), _wf_tableHead()
// Exports: renderCDD()

var _CDD_PALETTE = ['#1D7080','#38bdf8','#fb923c','#a78bfa','#34d399','#f472b6','#facc15','#94a3b8','#f87171','#60a5fa'];

function _cddK(v) {
  if (v == null) return '—';
  var neg = v < 0;
  var a = Math.abs(v);
  var s = a >= 1000 ? (a/1000).toFixed(2) + 'M' : Math.round(a).toLocaleString('en-US') + 'K';
  return (neg ? '(' : '') + '€' + s + (neg ? ')' : '');
}

function _cddPct(v) { return v != null ? v.toFixed(1) + '%' : '—'; }

function _cddSevBadge(sev) {
  var s = (sev || '').toUpperCase();
  var bg = s === 'HIGH' ? '#fef2f2' : s === 'MEDIUM' ? '#fffbeb' : '#f0fdf4';
  var c  = s === 'HIGH' ? '#b91c1c' : s === 'MEDIUM' ? '#b45309' : '#15803d';
  return '<span style="background:'+bg+';color:'+c+';font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">'+(s||'—')+'</span>';
}

function _cddConfBadge(conf) {
  var s = (conf || '').toUpperCase();
  var high = s.indexOf('HIGH') === 0, low = s.indexOf('LOW') === 0;
  var bg = high ? '#f0fdf4' : low ? '#fef2f2' : '#fffbeb';
  var c  = high ? '#15803d' : low ? '#b91c1c' : '#b45309';
  return '<span style="background:'+bg+';color:'+c+';font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">'+(s||'—')+'</span>';
}

// Generic stacked bar chart. series = [{label, values:{yearStr:val}, color}]
function _cddStackChart(years, series, opts) {
  opts = opts || {};
  var W = opts.w || 420, H = opts.h || 200, padL = 56, padB = 26, padT = 20, padR = 10;
  var chartW = W - padL - padR, chartH = H - padT - padB;
  var barW = Math.min(56, chartW / years.length * 0.6);

  var maxV = 0;
  years.forEach(function(y) {
    var tot = 0;
    series.forEach(function(s) { var v = s.values[y]; if (v != null && v > 0) tot += v; });
    if (tot > maxV) maxV = tot;
  });
  if (!maxV) return '<div style="color:#94a3b8;font-size:12px">No data</div>';

  var svg = '<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;max-height:'+H+'px;overflow:visible">';
  for (var i = 0; i <= 4; i++) {
    var gy = padT + chartH * (1 - i/4);
    var val = maxV * i / 4;
    var lbl = val >= 1000 ? (val/1000).toFixed(1)+'M' : Math.round(val)+'K';
    svg += '<line x1="'+padL+'" y1="'+gy.toFixed(1)+'" x2="'+(padL+chartW)+'" y2="'+gy.toFixed(1)+'" stroke="#f1f5f9"/>';
    svg += '<text x="'+(padL-4)+'" y="'+(gy+3.5).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8">'+lbl+'</text>';
  }
  years.forEach(function(y, gi) {
    var x = padL + gi * (chartW / years.length) + (chartW / years.length - barW) / 2;
    var acc = 0, tot = 0;
    series.forEach(function(s) {
      var v = s.values[y];
      if (v == null || v <= 0) return;
      var bh = v / maxV * chartH;
      var by = padT + chartH - (acc + v) / maxV * chartH;
      svg += '<rect x="'+x.toFixed(1)+'" y="'+by.toFixed(1)+'" width="'+barW+'" height="'+bh.toFixed(1)+'" fill="'+s.color+'" rx="1.5"><title>'+s.label+' '+y+': '+_cddK(v)+'</title></rect>';
      acc += v; tot += v;
    });
    if (tot > 0) {
      var tl = tot >= 1000 ? (tot/1000).toFixed(2)+'M' : Math.round(tot)+'K';
      svg += '<text x="'+(x+barW/2).toFixed(1)+'" y="'+(padT+chartH-acc/maxV*chartH-4).toFixed(1)+'" text-anchor="middle" font-size="9" fill="#334155" font-weight="600">'+tl+'</text>';
    }
    svg += '<text x="'+(x+barW/2).toFixed(1)+'" y="'+(H-4)+'" text-anchor="middle" font-size="10" fill="#64748b">'+y+(opts.ytd === y ? ' YTD' : '')+'</text>';
  });
  svg += '</svg>';

  var legend = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:6px">';
  series.forEach(function(s) {
    legend += '<span style="display:flex;align-items:center;gap:4px;font-size:10px;color:#64748b">'
      + '<span style="width:9px;height:9px;border-radius:2px;background:'+s.color+';display:inline-block"></span>'+s.label+'</span>';
  });
  legend += '</div>';
  return svg + legend;
}

// Quarterly revenue bars + GM% line overlay
function _cddQuarterlyChart(quarters) {
  if (!quarters || !quarters.length) return '<div style="color:#94a3b8;font-size:12px">No invoice data</div>';
  var W = 860, H = 210, padL = 56, padB = 30, padT = 20, padR = 44;
  var chartW = W - padL - padR, chartH = H - padT - padB;
  var n = quarters.length;
  var slot = chartW / n, barW = Math.min(34, slot * 0.62);

  var maxV = 0;
  quarters.forEach(function(q) { if (q.rev > maxV) maxV = q.rev; });
  if (!maxV) return '<div style="color:#94a3b8;font-size:12px">No data</div>';

  var svg = '<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;max-height:'+H+'px;overflow:visible">';
  for (var i = 0; i <= 4; i++) {
    var gy = padT + chartH * (1 - i/4);
    svg += '<line x1="'+padL+'" y1="'+gy.toFixed(1)+'" x2="'+(padL+chartW)+'" y2="'+gy.toFixed(1)+'" stroke="#f1f5f9"/>';
    svg += '<text x="'+(padL-4)+'" y="'+(gy+3.5).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8">'+Math.round(maxV*i/4)+'K</text>';
  }
  // bars
  quarters.forEach(function(q, gi) {
    var x = padL + gi * slot + (slot - barW) / 2;
    var bh = Math.max(0, q.rev / maxV * chartH); // negative quarters: no bar, label only
    var y = padT + chartH - bh;
    svg += '<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+barW+'" height="'+bh.toFixed(1)+'" fill="#1D7080" rx="2" opacity="0.85"><title>'+q.label+': '+_cddK(q.rev)+' / GM '+_cddPct(q.gm_pct)+'</title></rect>';
    svg += '<text x="'+(x+barW/2).toFixed(1)+'" y="'+(H-16)+'" text-anchor="middle" font-size="8.5" fill="#64748b">'+q.label.replace('-',' ')+'</text>';
  });
  // GM% line (right axis 0-100%)
  var pts = [];
  quarters.forEach(function(q, gi) {
    if (q.gm_pct == null) return;
    var x = padL + gi * slot + slot / 2;
    var y = padT + chartH * (1 - Math.min(q.gm_pct, 100) / 100);
    pts.push([x, y]);
  });
  if (pts.length > 1) {
    var d = pts.map(function(p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join('');
    svg += '<path d="'+d+'" fill="none" stroke="#fb923c" stroke-width="2"/>';
    pts.forEach(function(p) { svg += '<circle cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="2.5" fill="#fb923c"/>'; });
  }
  for (var j = 0; j <= 2; j++) {
    var ry = padT + chartH * (1 - j/2);
    svg += '<text x="'+(padL+chartW+6)+'" y="'+(ry+3.5).toFixed(1)+'" font-size="9" fill="#fb923c">'+(j*50)+'%</text>';
  }
  svg += '</svg>';
  svg += '<div style="display:flex;gap:14px;margin-top:4px;font-size:10px;color:#64748b">'
    + '<span style="display:flex;align-items:center;gap:4px"><span style="width:9px;height:9px;border-radius:2px;background:#1D7080;display:inline-block"></span>Revenue (EUR k)</span>'
    + '<span style="display:flex;align-items:center;gap:4px"><span style="width:9px;height:3px;background:#fb923c;display:inline-block"></span>GM%</span></div>';
  return svg;
}

// ── Year filter state (per-section) ──────────────────────────────────────────
var _cddYearsBySection = {}; // key=wrapperId, value=null|Set<string>

function _cddYrSel(wrapperId) { return _cddYearsBySection[wrapperId] || null; }

function _cddYrBar(allYrs, wrapperId) {
  var sel = _cddYrSel(wrapperId);
  var isAll = !sel;
  var h = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;align-items:center">';
  h += '<span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.4px;margin-right:2px">Year:</span>';
  h += '<button onclick="_cddSetYrs(null,\'' + wrapperId + '\')" style="padding:2px 9px;border-radius:12px;border:1px solid ' + (isAll ? '#0891B2' : '#cbd5e1') + ';background:' + (isAll ? '#0891B2' : '#fff') + ';color:' + (isAll ? '#fff' : '#475569') + ';font-size:11px;font-weight:600;cursor:pointer">All</button>';
  allYrs.forEach(function(y) {
    var act = sel && sel.has(String(y));
    h += '<button onclick="_cddTogYr(\'' + String(y) + '\',\'' + wrapperId + '\')" style="padding:2px 9px;border-radius:12px;border:1px solid ' + (act ? '#0891B2' : '#cbd5e1') + ';background:' + (act ? '#0891B2' : '#fff') + ';color:' + (act ? '#fff' : '#475569') + ';font-size:11px;font-weight:600;cursor:pointer">' + String(y) + '</button>';
  });
  h += '</div>';
  return h;
}

function _cddSetYrs(sel, elId) { _cddYearsBySection[elId] = sel; _cddRerender(elId); }

function _cddTogYr(y, elId) {
  var cur = _cddYrSel(elId);
  if (!cur) { _cddYearsBySection[elId] = new Set([String(y)]); }
  else { var s = new Set(cur); s.has(String(y)) ? s.delete(String(y)) : s.add(String(y)); _cddYearsBySection[elId] = s.size ? s : null; }
  _cddRerender(elId);
}

function _cddRerender(elId) {
  var el = document.getElementById(elId);
  if (!el || !DATA.cdd) return;
  var cdd = DATA.cdd;
  if (elId === 'bm-cdd-seg') el.innerHTML = _cddSourceNote(cdd) + _cddRenderSegments(cdd);
  else if (elId === 'sub-kunden') el.innerHTML = _cddSourceNote(cdd) + _cddRenderCustomers(cdd);
  else if (elId === 'sub-cohorts') el.innerHTML = _cddSourceNote(cdd) + _cddRenderCohorts(cdd);
  else if (elId === 'sub-churn') el.innerHTML = _cddSourceNote(cdd) + _cddRenderChurn(cdd);
}

function _cddGetYears(years, wrapperId) {
  var sel = wrapperId ? _cddYrSel(wrapperId) : null;
  if (!sel || !sel.size) return years;
  return years.filter(function(y) { return sel.has(String(y)); });
}

function _cddYearHeader(years, ytd) {
  return years.map(function(y) { return {label: String(y) + (String(ytd) === String(y) ? ' YTD' : ''), align: 'right'}; });
}

// ── Subtab: Revenue & Segments ──────────────────────────────────────────────
function _cddRenderSegments(cdd) {
  var seg = cdd.segments;
  var h = '';
  if (!seg || !seg.rows || !seg.rows.length) {
    return '<div class="stub"><p>No invoice data loaded — run <code>DEALROOM.py ingest-databook</code>.</p></div>';
  }
  var allYears = seg.years.map(String);
  var years = _cddGetYears(allYears, 'bm-cdd-seg');
  var latest = String(seg.latest_full_year);

  h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">';
  h += _wf_kpiCard('Revenue ' + latest, _cddK(seg.totals[latest]), 'from ' + (cdd.meta.invoice_count||0).toLocaleString('en-US') + ' invoice lines');
  var topSeg = seg.rows[0];
  h += _wf_kpiCard('Top Segment', topSeg.name, _cddPct(topSeg.share_latest) + ' of ' + latest + ' revenue');
  var gmLatest = null, gpSum = 0, revSum = 0;
  seg.rows.forEach(function(s) {
    var rv = s.rev[latest], gm = s.gm_pct[latest];
    if (rv != null && gm != null) { revSum += rv; gpSum += rv * gm / 100; }
  });
  if (revSum > 0) gmLatest = gpSum / revSum * 100;
  h += _wf_kpiCard('Gross Margin ' + latest, _cddPct(gmLatest), 'materials-only (Rohertrag)');
  if (cdd.meta.ytd_year) {
    var ytdStr = String(cdd.meta.ytd_year);
    h += _wf_kpiCard('Revenue ' + ytdStr + ' YTD', _cddK(seg.totals[ytdStr]), 'partial year');
  }
  h += '</div>';
  if (typeof renderAnswerFirstBar === 'function') h += renderAnswerFirstBar(_afCddSignals(cdd), {title: 'Revenue Signals'});
  h += _cddYrBar(allYears, 'bm-cdd-seg');

  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">';
  h += '<div class="overview-card"><h3>Revenue by Service Segment</h3>';
  var series = seg.rows.map(function(s, i) { return {label: s.name, values: s.rev, color: _CDD_PALETTE[i % _CDD_PALETTE.length]}; });
  h += _cddStackChart(years, series, {ytd: String(cdd.meta.ytd_year || '')});
  h += '</div>';
  h += '<div class="overview-card"><h3>Gross Margin by Segment ('+latest+')</h3>';
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
  h += _wf_tableHead([{label:'Segment'},{label:'Rev '+latest,align:'right'},{label:'GM% '+latest,align:'right'},{label:'',align:'left'}]);
  h += '<tbody>';
  seg.rows.forEach(function(s, i) {
    var gm = s.gm_pct[latest];
    var barW = gm != null ? Math.max(2, Math.min(100, gm)) : 0;
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
    h += '<td style="padding:5px 8px;font-weight:500">'+s.name+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+_cddK(s.rev[latest])+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600">'+_cddPct(gm)+'</td>';
    h += '<td style="padding:5px 10px;min-width:90px"><div style="background:#e2e8f0;border-radius:3px;height:6px"><div style="background:#0891B2;border-radius:3px;height:6px;width:'+barW+'%"></div></div></td>';
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  h += '</div>';

  // Segment matrix table
  h += '<div class="overview-card" style="margin-bottom:20px">';
  h += '<h3>Revenue by Segment by Year (EUR k)</h3>';
  var cols = [{label:'Segment'}].concat(_cddYearHeader(years, cdd.meta.ytd_year));
  Object.keys(seg.rows[0].yoy || {}).forEach(function(k) { cols.push({label:'YoY '+k.replace('20','’').replace('-20','-’'), align:'right'}); });
  cols.push({label:'CAGR', align:'right'});
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">' + _wf_tableHead(cols) + '<tbody>';
  seg.rows.forEach(function(s, i) {
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
    h += '<td style="padding:5px 8px;font-weight:500">'+s.name+'</td>';
    years.forEach(function(y) {
      var v = s.rev[String(y)];
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+(v!=null?Math.round(v).toLocaleString('en-US'):'—')+'</td>';
    });
    Object.keys(seg.rows[0].yoy || {}).forEach(function(k) {
      var v = s.yoy ? s.yoy[k] : null;
      var c = v == null ? '#94a3b8' : v < 0 ? '#b91c1c' : '#15803d';
      h += '<td style="padding:5px 8px;text-align:right;color:'+c+';font-weight:600">'+(v!=null?(v>0?'+':'')+v.toFixed(0)+'%':'—')+'</td>';
    });
    var cg = s.cagr;
    h += '<td style="padding:5px 8px;text-align:right;color:'+(cg==null?'#94a3b8':cg<0?'#b91c1c':'#15803d')+';font-weight:600">'+(cg!=null?(cg>0?'+':'')+cg.toFixed(0)+'%':'—')+'</td>';
    h += '</tr>';
  });
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700"><td style="padding:5px 8px">TOTAL</td>';
  years.forEach(function(y) {
    var v = seg.totals[String(y)];
    h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+(v!=null?Math.round(v).toLocaleString('en-US'):'—')+'</td>';
  });
  Object.keys(seg.rows[0].yoy || {}).forEach(function() { h += '<td></td>'; });
  h += '<td></td></tr>';
  h += '</tbody></table></div>';

  // Quarterly
  h += '<div class="overview-card"><h3>Quarterly Revenue & Gross Margin</h3>';
  h += _cddQuarterlyChart(cdd.quarterly);
  h += '</div>';
  return h;
}

// ── Subtab: Customers ───────────────────────────────────────────────────────
function _cddRenderCustomers(cdd) {
  var h = '';
  var conc = cdd.concentration;
  if (!conc) return '<div class="stub"><p>No customer data loaded.</p></div>';
  var yr = conc.year;
  var _allCYrs = (cdd.meta.customer_years || []).map(String);
  h += _cddYrBar(_allCYrs, 'sub-kunden');

  h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">';
  h += _wf_kpiCard('Active Customers', conc.active.n, String(yr));
  conc.tiers.forEach(function(t) {
    h += _wf_kpiCard(t.label, _cddPct(t.pct), _cddK(t.rev) + ' · ' + yr, {warn: t.n <= 10 && t.pct != null && t.pct > 50});
  });
  h += '</div>';

  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">';

  // Revenue by customer type (stacked by year)
  h += '<div class="overview-card"><h3>Revenue by Customer Type (EUR k)</h3>';
  var allYears = _cddGetYears(_allCYrs, 'sub-kunden');
  var series = (cdd.type_split || []).map(function(t, i) { return {label: t.type + ' ('+t.n+')', values: t.rev, color: _CDD_PALETTE[i % _CDD_PALETTE.length]}; });
  h += _cddStackChart(allYears, series, {ytd: String(cdd.meta.ytd_year || '')});
  h += '</div>';

  // Buckets
  h += '<div class="overview-card"><h3>Customers by Revenue Bucket (total, all years)</h3>';
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
  h += _wf_tableHead([{label:'Bucket'},{label:'# Cust',align:'right'},{label:'Revenue',align:'right'},{label:'Share',align:'right'},{label:''}]);
  h += '<tbody>';
  (cdd.buckets || []).forEach(function(b, i) {
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
    h += '<td style="padding:5px 8px;font-weight:500">'+b.label+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+b.n+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+_cddK(b.rev)+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600">'+_cddPct(b.pct)+'</td>';
    h += '<td style="padding:5px 10px;min-width:80px"><div style="background:#e2e8f0;border-radius:3px;height:6px"><div style="background:#1D7080;border-radius:3px;height:6px;width:'+Math.min(100,(b.pct||0)*1.4)+'%"></div></div></td>';
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  h += '</div>';

  // New vs existing
  var ne = cdd.new_existing || {};
  var neYears = Object.keys(ne).sort();
  if (neYears.length) {
    h += '<div class="overview-card" style="margin-bottom:20px"><h3>New vs Existing Customers</h3>';
    h += '<div style="display:flex;gap:24px;flex-wrap:wrap">';
    neYears.forEach(function(y) {
      var d = ne[y];
      h += '<div style="flex:1;min-width:260px">';
      h += '<div style="font-size:11px;font-weight:700;color:#0891B2;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">'+y+(String(cdd.meta.ytd_year)===y?' YTD':'')+'</div>';
      h += '<div style="display:flex;gap:10px">';
      h += _wf_kpiCard('Existing', _cddPct(d.existing.pct), d.existing.n + ' cust · ' + _cddK(d.existing.rev), {highlight: d.existing.pct != null && d.existing.pct >= 90});
      h += _wf_kpiCard('New ('+y+' cohort)', _cddPct(d.new.pct), d.new.n + ' cust · ' + _cddK(d.new.rev));
      h += '</div></div>';
    });
    h += '</div></div>';
  }

  // Top 20 table
  var top20 = cdd.top20 || [];
  if (top20.length) {
    var years = (cdd.meta.customer_years || []);
    h += '<div class="overview-card"><h3>Top 20 Customers by '+yr+' Revenue (EUR k)</h3>';
    var cols = [{label:'#',align:'right'},{label:'Kunde'},{label:'Type'},{label:'Cohort',align:'right'}].concat(_cddYearHeader(years, cdd.meta.ytd_year)).concat([{label:'Total',align:'right'}]);
    h += '<table style="width:100%;border-collapse:collapse;font-size:12px">' + _wf_tableHead(cols) + '<tbody>';
    top20.forEach(function(c, i) {
      h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
      h += '<td style="padding:4px 8px;text-align:right;color:#94a3b8;font-weight:600">'+c.rank+'</td>';
      h += '<td style="padding:4px 8px;font-weight:500">'+c.name+'</td>';
      h += '<td style="padding:4px 8px;color:#64748b">'+(c.type||'—')+'</td>';
      h += '<td style="padding:4px 8px;text-align:right;color:#64748b">'+(c.cohort||'—')+'</td>';
      years.forEach(function(y) {
        var v = c.rev[String(y)];
        h += '<td style="padding:4px 8px;text-align:right;font-family:monospace">'+(v!=null?Math.round(v).toLocaleString('en-US'):'·')+'</td>';
      });
      h += '<td style="padding:4px 8px;text-align:right;font-family:monospace;font-weight:600">'+Math.round(c.total).toLocaleString('en-US')+'</td>';
      h += '</tr>';
    });
    h += '</tbody></table>';
    h += '<div style="margin-top:6px;font-size:10.5px;color:#94a3b8">Customers anonymised in source databook (Kunde # = seller customer number).</div>';
    h += '</div>';
  }
  return h;
}

// ── Subtab: Cohorts & Retention ─────────────────────────────────────────────
function _cddRenderCohorts(cdd) {
  var h = '';
  var co = cdd.cohorts;
  if (!co || !co.rows || !co.rows.length) return '<div class="stub"><p>No customer data loaded.</p></div>';
  var years = co.years.map(String);

  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">';
  h += '<div class="overview-card"><h3>Revenue by First-Revenue Cohort (EUR k)</h3>';
  var series = co.rows.map(function(c, i) { return {label: c.cohort + ' ('+c.n+')', values: c.rev, color: _CDD_PALETTE[i % _CDD_PALETTE.length]}; });
  h += _cddStackChart(years, series, {ytd: String(cdd.meta.ytd_year || '')});
  h += '</div>';

  // Retention table
  h += '<div class="overview-card"><h3>Year-over-Year Retention</h3>';
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
  h += _wf_tableHead([{label:'Period'},{label:'Active',align:'right'},{label:'Retained',align:'right'},{label:'Logo Ret.',align:'right'},{label:'NRR',align:'right'}]);
  h += '<tbody>';
  (cdd.retention || []).forEach(function(r, i) {
    var dim = r.partial ? 'opacity:.55;' : '';
    var nrrC = r.nrr_pct == null ? '#94a3b8' : r.nrr_pct >= 100 ? '#15803d' : r.nrr_pct >= 90 ? '#b45309' : '#b91c1c';
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+';'+dim+'">';
    h += '<td style="padding:5px 8px;font-weight:500">'+r.period+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+r.active_start+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+r.retained+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600">'+_cddPct(r.logo_pct)+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:700;color:'+nrrC+'">'+_cddPct(r.nrr_pct)+'</td>';
    h += '</tr>';
  });
  h += '</tbody></table>';
  h += '<div style="margin-top:6px;font-size:10.5px;color:#94a3b8">Logo retention = active customers invoiced again next year. NRR = next-year revenue of the start-year base.</div>';
  h += '</div>';
  h += '</div>';

  // Cohort matrix
  h += '<div class="overview-card"><h3>Cohort Matrix (EUR k)</h3>';
  var cols = [{label:'Cohort'},{label:'# Cust',align:'right'}].concat(_cddYearHeader(co.years, cdd.meta.ytd_year)).concat([{label:'CAGR',align:'right'}]);
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">' + _wf_tableHead(cols) + '<tbody>';
  co.rows.forEach(function(c, i) {
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
    h += '<td style="padding:5px 8px;font-weight:600;color:#0891B2">'+c.cohort+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+c.n+'</td>';
    co.years.forEach(function(y, yi) {
      var v = c.rev[String(y)];
      var isDiag = String(c.cohort) === String(y);
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace;'+(isDiag?'background:#f0f9ff;font-weight:600':'')+'">'+(v!=null&&Math.abs(v)>0.005?Math.round(v).toLocaleString('en-US'):'·')+'</td>';
    });
    var cg = c.cagr;
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600;color:'+(cg==null?'#94a3b8':cg<0?'#b91c1c':'#15803d')+'">'+(cg!=null?(cg>0?'+':'')+cg.toFixed(0)+'%':'—')+'</td>';
    h += '</tr>';
  });
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700">';
  h += '<td style="padding:5px 8px">TOTAL</td><td style="padding:5px 8px;text-align:right">'+co.total.n+'</td>';
  co.years.forEach(function(y) {
    var v = co.total.rev[String(y)];
    h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+(v!=null?Math.round(v).toLocaleString('en-US'):'—')+'</td>';
  });
  h += '<td></td></tr>';
  h += '</tbody></table>';
  h += '<div style="margin-top:6px;font-size:10.5px;color:#94a3b8">Cohort = first calendar year with revenue inside the data window. Pre-window customers sit in the earliest cohort.</div>';
  h += '</div>';
  return h;
}

// ── Subtab: Churn ───────────────────────────────────────────────────────────
function _cddRenderChurn(cdd) {
  var h = '';
  var ch = cdd.churn;
  if (!ch || !ch.by_year || !ch.by_year.length) return '<div class="stub"><p>No customer data loaded.</p></div>';

  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">';
  h += '<div class="overview-card"><h3>Churn by Year (EUR k)</h3>';
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
  h += _wf_tableHead([{label:'Period'},{label:'Active',align:'right'},{label:'Churned',align:'right'},{label:'Logo Churn',align:'right'},{label:'Churned Rev',align:'right'},{label:'Rev Churn',align:'right'}]);
  h += '<tbody>';
  ch.by_year.forEach(function(r, i) {
    var dim = r.partial ? 'opacity:.55;' : '';
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+';'+dim+'">';
    h += '<td style="padding:5px 8px;font-weight:500">'+r.period+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+r.active_start+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600;color:#b91c1c">'+r.churned+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+_cddPct(r.logo_churn_pct)+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+_cddK(r.churned_rev)+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600">'+_cddPct(r.rev_churn_pct)+'</td>';
    h += '</tr>';
  });
  h += '</tbody></table>';
  h += '<div style="margin-top:6px;font-size:10.5px;color:#94a3b8">Invoicing-based churn — a customer without invoices in the next year counts as churned, even if the relationship survives.</div>';
  h += '</div>';

  // Churn by type
  h += '<div class="overview-card"><h3>Churn by Customer Type'+(ch.by_type_period?' ('+ch.by_type_period+')':'')+'</h3>';
  h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
  h += _wf_tableHead([{label:'Type'},{label:'Active',align:'right'},{label:'Churned',align:'right'},{label:'Logo Churn',align:'right'},{label:'Churned Rev',align:'right'}]);
  h += '<tbody>';
  (ch.by_type || []).forEach(function(r, i) {
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
    h += '<td style="padding:5px 8px;font-weight:500">'+r.type+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+r.active+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600;color:#b91c1c">'+r.churned+'</td>';
    h += '<td style="padding:5px 8px;text-align:right">'+_cddPct(r.logo_churn_pct)+'</td>';
    h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+_cddK(r.churned_rev)+'</td>';
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  h += '</div>';

  // Revenue bridge
  if (ch.bridge && ch.bridge.length) {
    h += '<div class="overview-card"><h3>Revenue Bridge (EUR k)</h3>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
    h += _wf_tableHead([{label:'Period'},{label:'Start',align:'right'},{label:'− Churned',align:'right'},{label:'± Net Retained',align:'right'},{label:'+ New/React.',align:'right'},{label:'= End',align:'right'}]);
    h += '<tbody>';
    ch.bridge.forEach(function(r, i) {
      var nrC = r.net_retained == null ? '#94a3b8' : r.net_retained < 0 ? '#b91c1c' : '#15803d';
      h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
      h += '<td style="padding:5px 8px;font-weight:500">'+r.period+'</td>';
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace">'+Math.round(r.start).toLocaleString('en-US')+'</td>';
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace;color:#b91c1c">'+Math.round(r.churned).toLocaleString('en-US')+'</td>';
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace;color:'+nrC+'">'+(r.net_retained>0?'+':'')+Math.round(r.net_retained).toLocaleString('en-US')+'</td>';
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace;color:#15803d">+'+Math.round(r.new).toLocaleString('en-US')+'</td>';
      h += '<td style="padding:5px 8px;text-align:right;font-family:monospace;font-weight:700">'+Math.round(r.end).toLocaleString('en-US')+'</td>';
      h += '</tr>';
    });
    h += '</tbody></table></div>';
  }
  return h;
}

// ── Subtab: Findings ────────────────────────────────────────────────────────
function _cddRenderFindings(cdd) {
  var f = cdd.findings || {};
  var h = '';
  if (!(f.red_flags||[]).length && !(f.gaps||[]).length && !(f.confidence||[]).length) {
    return '<div class="stub"><p>No findings loaded from the databook.</p></div>';
  }

  if ((f.red_flags||[]).length) {
    h += '<div class="overview-card" style="margin-bottom:16px"><h3>Red Flags / Watch Items</h3>';
    h += '<div style="display:flex;flex-direction:column;gap:8px">';
    f.red_flags.forEach(function(r) {
      var high = (r.severity||'') === 'HIGH';
      h += '<div style="background:'+(high?'#fef2f2':'#fffbeb')+';border:1px solid '+(high?'#fecaca':'#fde68a')+';border-radius:6px;padding:10px 14px">';
      h += '<div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">';
      h += '<div style="font-weight:600;font-size:13px;color:#1e293b">'+r.finding+'</div>';
      h += '<div style="flex-shrink:0">'+_cddSevBadge(r.severity)+'</div>';
      h += '</div>';
      if (r.so_what) h += '<div style="font-size:12px;color:#6c757d;margin-top:4px;line-height:1.5"><strong style="color:#475569">So what:</strong> '+r.so_what+'</div>';
      h += '</div>';
    });
    h += '</div></div>';
  }

  if ((f.gaps||[]).length) {
    h += '<div class="overview-card" style="margin-bottom:16px"><h3>Data Gaps</h3>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
    h += _wf_tableHead([{label:'Item'},{label:'Description'},{label:'Severity',align:'center'}]);
    h += '<tbody>';
    f.gaps.forEach(function(g, i) {
      h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
      h += '<td style="padding:6px 8px;font-weight:500;min-width:160px">'+(g.item||'—')+'</td>';
      h += '<td style="padding:6px 8px;color:#475569;line-height:1.45">'+(g.description||'')+'</td>';
      h += '<td style="padding:6px 8px;text-align:center">'+_cddSevBadge(g.severity)+'</td>';
      h += '</tr>';
    });
    h += '</tbody></table></div>';
  }

  if ((f.confidence||[]).length) {
    h += '<div class="overview-card"><h3>Confidence by Analysis</h3>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:12.5px">';
    h += _wf_tableHead([{label:'Analysis'},{label:'Notes'},{label:'Confidence',align:'center'}]);
    h += '<tbody>';
    f.confidence.forEach(function(c, i) {
      h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+(i%2?'#f8fafc':'#fff')+'">';
      h += '<td style="padding:6px 8px;font-weight:500;min-width:180px">'+(c.analysis||'—')+'</td>';
      h += '<td style="padding:6px 8px;color:#475569;line-height:1.45">'+(c.notes||'')+'</td>';
      h += '<td style="padding:6px 8px;text-align:center">'+_cddConfBadge(c.confidence)+'</td>';
      h += '</tr>';
    });
    h += '</tbody></table></div>';
  }
  return h;
}

// ── Source note + DD section entry ──────────────────────────────────────────
// No standalone CDD tab: each analysis lives in its IC-memo section —
// segments → Business Model, customers/cohorts/churn → Customers & Suppliers,
// findings → Due Diligence. The sidebar sections ARE the presentation.

function _cddSourceNote(cdd) {
  return '<div style="font-size:11px;color:#94a3b8;margin-bottom:12px">Commercial DD — computed live from '
    + (cdd.meta.invoice_count||0).toLocaleString('en-US') + ' invoice lines · '
    + (cdd.meta.customer_count||0) + ' customers (databook-verified, 106-check tie-out)</div>';
}

function renderDDSection() {
  var cdd = DATA.cdd;
  var f = cdd && cdd.findings || {};
  var hasFindings = (f.red_flags||[]).length || (f.gaps||[]).length || (f.confidence||[]).length;
  if (!hasFindings) {
    return stubSection('Due Diligence','DD request lists, received documents, gap analysis','DR-M14 (DD Package)');
  }
  var h = '';
  h += '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:14px">';
  h += '<h2 style="margin:0;font-size:18px;color:#1e293b">Due Diligence — CDD Findings</h2>';
  h += '</div>';
  h += _cddSourceNote(cdd);
  if (typeof renderAnswerFirstBar === 'function') {
    var _dFlags = f.red_flags || [];
    var _dHigh = _dFlags.filter(function(r){return r.severity==='HIGH';}).length;
    var _dGaps = f.gaps || [];
    var _dGHigh = _dGaps.filter(function(g){return g.severity==='HIGH';}).length;
    h += renderAnswerFirstBar([
      {label:'Red Flags',value:_dFlags.length===0?'None':_dFlags.length+(_dHigh?' · '+_dHigh+' HIGH':''),verdict:_dFlags.length===0?'green':_dHigh>0?'red':'yellow',detail:_dFlags.length+' total ('+_dHigh+' HIGH)'},
      {label:'Data Gaps',value:_dGaps.length===0?'None':_dGHigh+' HIGH / '+_dGaps.length+' total',verdict:_dGaps.length===0?'green':_dGHigh>0?'red':_dGaps.length>0?'yellow':'green',detail:'Data gaps identified in CDD'},
    ], {title: 'DD Quality Signals'});
  }
  h += _cddRenderFindings(cdd);
  return h;
}
