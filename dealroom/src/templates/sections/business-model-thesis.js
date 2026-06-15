// ─── DR-M20 — Business Model + Thesis ──────────────────────────────────────
// Dependencies: DATA global, _slide_esc(), _afDDCard(), _afHarvey(), _afSectionConfidence(),
//               _afColor(), renderAnswerFirstBar(), _afCddSignals()
// Exports: renderBusinessModel(), renderThesis(), _attachDDEditableHandlers()

function _attachDDEditableHandlers() {
  if (typeof SERVE_MODE === 'undefined' || !SERVE_MODE) return;
  document.querySelectorAll('[contenteditable="true"][data-field]').forEach(function(el) {
    if (el._ddBlurBound) return;
    el._ddBlurBound = true;
    el.addEventListener('blur', function() {
      var field = el.dataset.field;
      if (!field) return;
      var value = el.innerText.trim();
      var code = DATA.deal.code_name;
      fetch('/api/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code_name: code, field: field, value: value})
      }).then(function(r) {
        el.style.borderColor = r.ok ? '#86efac' : '#fecaca';
        setTimeout(function() { el.style.borderColor = '#e2e8f0'; }, 1500);
      }).catch(function() {
        el.style.borderColor = '#fecaca';
        setTimeout(function() { el.style.borderColor = '#e2e8f0'; }, 1500);
      });
    });
  });
}

function renderBusinessModel() {
  var d   = DATA.deal       || {};
  var cdd = DATA.cdd;
  var fin = DATA.financials || {};
  var editable = typeof SERVE_MODE !== 'undefined' && SERVE_MODE && !(typeof INVESTOR_MODE !== 'undefined' && INVESTOR_MODE);

  // ── No CDD data at all → wireframe stub ──
  var hasSegments = cdd && cdd.segments && cdd.segments.rows && cdd.segments.rows.length;
  var hasCustomers = cdd && ((cdd.concentration && cdd.concentration.tiers) || (cdd.retention && cdd.retention.length) || cdd.new_existing);
  if (!hasSegments && !hasCustomers) {
    return _bmWireframe(d, editable);
  }

  var seg = (cdd && cdd.segments) || {};
  var rows = seg.rows || [];
  var years = seg.years || [];
  var fullYears = seg.full_years || [];
  var latest = seg.latest_full_year;
  var latestStr = latest ? String(latest) : '';
  var totals = seg.totals || {};

  // ── Compute section confidence ──
  var conf = _afSectionConfidence([
    {present: rows.length > 0, weight: 3},
    {present: fullYears.length >= 2, weight: 2},
    {present: !!(cdd.concentration && cdd.concentration.tiers), weight: 2},
    {present: !!(cdd.retention && cdd.retention.length), weight: 2},
    {present: !!(cdd.churn && cdd.churn.bridge && cdd.churn.bridge.length), weight: 1},
  ]);

  var h = '';

  // ── Signal bar ──
  if (typeof renderAnswerFirstBar === 'function') {
    h += renderAnswerFirstBar(_afCddSignals(cdd), {title: 'Commercial Signals'});
  }

  // ── Card 1: Revenue segments (only if segment data exists) ──
  if (!rows.length) {
    // Skip segment + margin cards when only customer-level data available
  } else {
  var topSeg = rows[0];
  var topShare = topSeg.share_latest ? topSeg.share_latest.toFixed(0) + '%' : '—';
  var totalRev = totals[latestStr];
  var totalRevFmt = totalRev ? (totalRev >= 1000 ? (totalRev / 1000).toFixed(1) + ' M€' : Math.round(totalRev) + ' K€') : '—';

  var cagrVal = null;
  if (fullYears.length >= 2) {
    var t0 = totals[String(fullYears[0])];
    var tN = totals[String(fullYears[fullYears.length - 1])];
    var nY = fullYears.length - 1;
    if (t0 && t0 > 0 && tN && tN > 0 && nY > 0) {
      cagrVal = (Math.pow(tN / t0, 1 / nY) - 1) * 100;
    }
  }

  var segHeadline = rows.length + ' revenue segments totaling ' + totalRevFmt + ' in ' + latestStr;
  if (cagrVal != null) segHeadline += ' (' + (cagrVal >= 0 ? '+' : '') + cagrVal.toFixed(1) + '% CAGR)';

  var segVerdict = cagrVal == null ? 'grey' : cagrVal >= 5 ? 'green' : cagrVal >= 0 ? 'yellow' : 'red';
  var segConf = rows.length >= 3 && fullYears.length >= 2 ? 4 : rows.length >= 2 ? 3 : 2;

  var segBody = _bmSegmentTable(rows, years, fullYears, latestStr, totals);
  segBody += _bmSegmentChart(rows, latestStr);

  // Editable commentary
  segBody += _bmEditableBox('bm_segments_comment',
    'Revenue is distributed across ' + rows.length + ' reporting lines. '
    + _slide_esc(topSeg.name) + ' is the largest at ' + topShare + ' of ' + latestStr + ' revenue.'
    + (cagrVal != null ? ' Overall CAGR of ' + cagrVal.toFixed(1) + '% driven by ' + (rows.filter(function(r){return r.cagr && r.cagr > 5;}).length) + ' growing segments.' : ''),
    editable);

  h += _afDDCard(segHeadline, segVerdict, segConf, segBody, {editable: false, id: 'bm-seg'});

  // ── Card 2: Gross margin architecture ──
  var gpRows = rows.filter(function(r) { return r.gm_pct && r.gm_pct[latestStr] != null; });
  if (gpRows.length > 0) {
    var wRevSum = 0, wGpSum = 0;
    gpRows.forEach(function(r) {
      var rv = r.rev[latestStr] || 0;
      wRevSum += rv;
      wGpSum += rv * (r.gm_pct[latestStr] || 0) / 100;
    });
    var blendedGm = wRevSum > 0 ? (wGpSum / wRevSum * 100) : null;

    var gmVerdict = blendedGm == null ? 'grey' : blendedGm >= 35 ? 'green' : blendedGm >= 20 ? 'yellow' : 'red';
    var gmHeadline = 'Blended gross margin is ' + (blendedGm != null ? blendedGm.toFixed(1) + '%' : 'n/a') + ' in ' + latestStr + ' (materials-only)';
    var gmConf = gpRows.length >= rows.length * 0.8 ? 3 : 2;

    var gmBody = _bmMarginTable(gpRows, fullYears, latestStr);
    gmBody += _bmEditableBox('bm_margin_comment',
      'Gross margins are materials-only (Rohertrag). Labor is not allocated to segments. '
      + 'Margin dispersion across segments: '
      + gpRows.map(function(r) { return _slide_esc(r.name) + ' ' + (r.gm_pct[latestStr] || 0).toFixed(0) + '%'; }).join(', ')
      + '.',
      editable);

    h += _afDDCard(gmHeadline, gmVerdict, gmConf, gmBody, {
      caveat: 'Materials-only margin — labor allocation and rebate impact not captured.',
      id: 'bm-gm'
    });
  }
  } // end segments guard

  // ── Card 3: Revenue quality (new vs existing) ──
  if (cdd.new_existing) {
    var neData = cdd.new_existing[latestStr];
    if (neData) {
      var existPct = neData.existing.pct;
      var neVerdict = existPct == null ? 'grey' : existPct >= 80 ? 'green' : existPct >= 60 ? 'yellow' : 'red';
      var neHeadline = (existPct != null ? existPct.toFixed(0) + '%' : '—') + ' of ' + latestStr + ' revenue from existing customers';
      var neConf = cdd.retention && cdd.retention.length >= 2 ? 4 : cdd.retention && cdd.retention.length ? 3 : 2;

      var neBody = '<div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap">';
      neBody += _bmKpi('Existing', (neData.existing.rev || 0).toFixed(0) + ' K€', neData.existing.n + ' customers', existPct >= 80);
      neBody += _bmKpi('New', (neData.new.rev || 0).toFixed(0) + ' K€', neData.new.n + ' customers', false);
      neBody += '</div>';

      neBody += _bmEditableBox('bm_revquality_comment',
        'Existing-customer base generates the dominant share of revenue. '
        + 'New customer acquisition contributed ' + (neData.new.rev || 0).toFixed(0) + ' K€ from ' + neData.new.n + ' accounts.',
        editable);

      h += _afDDCard(neHeadline, neVerdict, neConf, neBody, {id: 'bm-revquality'});
    }
  }

  // ── Card 4: Revenue tie-out (invoice vs P&L) ──
  var pnl = fin.pnl || {};
  var unified = fin.unified_pnl || {};
  var tieoutCards = [];
  fullYears.forEach(function(y) {
    var ys = String(y);
    var invoiceRev = totals[ys];
    var pnlRev = null;
    // Try unified_pnl first, then pnl
    if (unified && unified[ys]) {
      var uRow = unified[ys];
      if (uRow.revenue != null) pnlRev = uRow.revenue;
      else if (uRow.Umsatzerloese != null) pnlRev = uRow.Umsatzerloese;
    }
    if (pnlRev == null && pnl[ys]) {
      var pEntry = pnl[ys];
      if (pEntry.revenue && pEntry.revenue.primary) pnlRev = pEntry.revenue.primary.value;
      if (pnlRev == null && pEntry.Umsatzerloese && pEntry.Umsatzerloese.primary) pnlRev = pEntry.Umsatzerloese.primary.value;
    }
    if (invoiceRev != null && pnlRev != null && pnlRev > 0) {
      var coverage = invoiceRev / pnlRev * 100;
      tieoutCards.push({year: ys, invoice: invoiceRev, pnl: pnlRev, coverage: coverage});
    }
  });

  if (tieoutCards.length > 0) {
    var latestTie = tieoutCards[tieoutCards.length - 1];
    var tieVerdict = latestTie.coverage >= 90 ? 'green' : latestTie.coverage >= 75 ? 'yellow' : 'red';
    var tieHeadline = 'Invoice data covers ' + latestTie.coverage.toFixed(0) + '% of reported P&L revenue in ' + latestTie.year;
    var tieConf = tieoutCards.length >= 2 ? 3 : 2;

    var tieBody = '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px">';
    tieBody += '<thead><tr style="border-bottom:2px solid #e2e8f0">';
    tieBody += '<th style="text-align:left;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">Year</th>';
    tieBody += '<th style="text-align:right;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">Invoice Rev.</th>';
    tieBody += '<th style="text-align:right;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">P&L Rev.</th>';
    tieBody += '<th style="text-align:right;padding:6px 10px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">Coverage</th>';
    tieBody += '</tr></thead><tbody>';
    tieoutCards.forEach(function(t) {
      var covColor = t.coverage >= 90 ? '#15803d' : t.coverage >= 75 ? '#b45309' : '#b91c1c';
      tieBody += '<tr style="border-bottom:1px solid #f1f5f9">';
      tieBody += '<td style="padding:6px 10px;font-weight:500">' + t.year + '</td>';
      tieBody += '<td style="padding:6px 10px;text-align:right;font-variant-numeric:tabular-nums">' + Math.round(t.invoice) + ' K€</td>';
      tieBody += '<td style="padding:6px 10px;text-align:right;font-variant-numeric:tabular-nums">' + Math.round(t.pnl) + ' K€</td>';
      tieBody += '<td style="padding:6px 10px;text-align:right;font-weight:700;color:' + covColor + '">' + t.coverage.toFixed(1) + '%</td>';
      tieBody += '</tr>';
    });
    tieBody += '</tbody></table>';

    tieBody += _bmEditableBox('bm_tieout_comment',
      'Revenue tie-out compares invoice-derived totals to P&L. '
      + (latestTie.coverage >= 90 ? 'High coverage — invoice data is reliable basis for analysis.' :
         latestTie.coverage >= 75 ? 'Partial coverage — some revenue streams may not be in the invoice extract.' :
         'Low coverage — conclusions from invoice analysis should be treated as directional.'),
      editable);

    h += _afDDCard(tieHeadline, tieVerdict, tieConf, tieBody, {
      caveat: latestTie.coverage < 90 ? 'Invoice extract does not cover full P&L revenue — analysis is based on a subset.' : null,
      id: 'bm-tieout'
    });
  }

  return h;
}

// ── Segment revenue table ──
function _bmSegmentTable(rows, years, fullYears, latestStr, totals) {
  var h = '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px">';
  h += '<thead><tr style="border-bottom:2px solid #e2e8f0">';
  h += '<th style="text-align:left;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase">Segment</th>';
  years.forEach(function(y) {
    h += '<th style="text-align:right;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px">' + y + '</th>';
  });
  h += '<th style="text-align:right;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px">Share</th>';
  h += '<th style="text-align:right;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px">CAGR</th>';
  h += '<th style="text-align:right;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px">GM%</th>';
  h += '</tr></thead><tbody>';

  rows.forEach(function(r, i) {
    var bg = i % 2 === 0 ? '#fff' : '#f8fafc';
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:' + bg + '">';
    h += '<td style="padding:5px 8px;font-weight:500;color:#1e293b;white-space:nowrap">' + _slide_esc(r.name) + '</td>';
    years.forEach(function(y) {
      var v = r.rev[String(y)];
      h += '<td style="padding:5px 8px;text-align:right;font-variant-numeric:tabular-nums;color:#334155">' + (v != null ? Math.round(v) : '—') + '</td>';
    });
    h += '<td style="padding:5px 8px;text-align:right;font-weight:600;color:#0891B2">' + (r.share_latest != null ? r.share_latest.toFixed(0) + '%' : '—') + '</td>';
    h += '<td style="padding:5px 8px;text-align:right;color:' + (r.cagr != null && r.cagr >= 0 ? '#15803d' : '#b91c1c') + '">' + (r.cagr != null ? (r.cagr >= 0 ? '+' : '') + r.cagr.toFixed(1) + '%' : '—') + '</td>';
    var gm = r.gm_pct ? r.gm_pct[latestStr] : null;
    h += '<td style="padding:5px 8px;text-align:right;color:#64748b">' + (gm != null ? gm.toFixed(0) + '%' : '—') + '</td>';
    h += '</tr>';
  });

  // Totals row
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700">';
  h += '<td style="padding:5px 8px">Total</td>';
  years.forEach(function(y) {
    var v = totals[String(y)];
    h += '<td style="padding:5px 8px;text-align:right;font-variant-numeric:tabular-nums">' + (v != null ? Math.round(v) : '—') + '</td>';
  });
  h += '<td style="padding:5px 8px;text-align:right">100%</td>';
  h += '<td></td><td></td></tr>';
  h += '</tbody></table>';
  h += '<div style="font-size:10px;color:#94a3b8;margin-bottom:8px">Revenue in K€. GM% = materials-only gross margin (' + latestStr + ').</div>';
  return h;
}

// ── Segment share bar chart (horizontal) ──
function _bmSegmentChart(rows, latestStr) {
  var sorted = rows.slice().sort(function(a,b) { return (b.share_latest || 0) - (a.share_latest || 0); });
  var colors = ['#0891B2','#22C5E0','#67D6E8','#8DE8F6','#B0F0FA','#D3F8FD','#E8FBFE','#F0FDFF','#F8FFFE'];
  var h = '<div style="display:flex;height:28px;border-radius:6px;overflow:hidden;margin-bottom:12px">';
  sorted.forEach(function(r, i) {
    var w = r.share_latest || 0;
    if (w < 0.5) return;
    var fill = colors[i % colors.length];
    var tc = i < 3 ? '#fff' : '#164e63';
    h += '<div style="flex:' + w.toFixed(1) + ';background:' + fill + ';display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:600;color:' + tc + ';min-width:0;overflow:hidden;white-space:nowrap;padding:0 4px" title="' + _slide_esc(r.name) + ': ' + w.toFixed(1) + '%">';
    if (w >= 8) h += _slide_esc(r.name) + ' ' + w.toFixed(0) + '%';
    h += '</div>';
  });
  h += '</div>';
  return h;
}

// ── Margin table by segment ──
function _bmMarginTable(gpRows, fullYears, latestStr) {
  var h = '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px">';
  h += '<thead><tr style="border-bottom:2px solid #e2e8f0">';
  h += '<th style="text-align:left;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase">Segment</th>';
  fullYears.forEach(function(y) {
    h += '<th style="text-align:right;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px">GM% ' + y + '</th>';
  });
  h += '<th style="text-align:right;padding:5px 8px;color:#64748b;font-weight:600;font-size:10px">Δ</th>';
  h += '</tr></thead><tbody>';

  gpRows.forEach(function(r, i) {
    var bg = i % 2 === 0 ? '#fff' : '#f8fafc';
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:' + bg + '">';
    h += '<td style="padding:5px 8px;font-weight:500;color:#1e293b">' + _slide_esc(r.name) + '</td>';
    fullYears.forEach(function(y) {
      var gm = r.gm_pct ? r.gm_pct[String(y)] : null;
      h += '<td style="padding:5px 8px;text-align:right;font-variant-numeric:tabular-nums">' + (gm != null ? gm.toFixed(1) + '%' : '—') + '</td>';
    });
    // Delta first vs last full year
    var first = r.gm_pct ? r.gm_pct[String(fullYears[0])] : null;
    var last = r.gm_pct ? r.gm_pct[String(fullYears[fullYears.length - 1])] : null;
    if (first != null && last != null) {
      var delta = last - first;
      var dColor = delta >= 0 ? '#15803d' : '#b91c1c';
      h += '<td style="padding:5px 8px;text-align:right;font-weight:600;color:' + dColor + '">' + (delta >= 0 ? '+' : '') + delta.toFixed(1) + 'pp</td>';
    } else {
      h += '<td style="padding:5px 8px;text-align:right;color:#94a3b8">—</td>';
    }
    h += '</tr>';
  });
  h += '</tbody></table>';
  return h;
}

// ── KPI card (small, for inline use) ──
function _bmKpi(label, value, sub, highlight) {
  var bg = highlight ? '#f0fdf4' : '#f8fafc';
  var border = highlight ? '#86efac' : '#e2e8f0';
  var vColor = highlight ? '#15803d' : '#1e293b';
  return '<div style="background:' + bg + ';border:1px solid ' + border + ';border-radius:8px;padding:10px 14px;min-width:120px;flex:1">'
    + '<div style="font-size:10px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px">' + label + '</div>'
    + '<div style="font-size:18px;font-weight:700;color:' + vColor + '">' + value + '</div>'
    + (sub ? '<div style="font-size:10px;color:#94a3b8;margin-top:2px">' + sub + '</div>' : '')
    + '</div>';
}

// ── Editable commentary box ──
function _bmEditableBox(field, defaultText, editable) {
  var saved = DATA.dd_commentary && DATA.dd_commentary[field];
  var raw = saved || defaultText;
  var text = _slide_esc(raw).replace(/\n/g, '<br>');
  var editAttr = editable ? ' contenteditable="true" data-field="' + field + '"' : '';
  return '<div style="margin-top:10px;padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;'
    + 'font-size:12px;color:#475569;line-height:1.6;min-height:40px"' + editAttr + '>'
    + text
    + '</div>';
}

// ── Wireframe fallback (no CDD data) ──
function _bmWireframe(d, editable) {
  var companyName = _slide_esc((d.company_name || d.code_name || '[Company]'));
  var h = '';
  h += _afDDCard('No invoice or customer data loaded', 'red', 1,
    '<div style="font-size:13px;color:#64748b;line-height:1.6">'
    + '<p><strong>' + companyName + '</strong> — business model analysis requires invoice-level or customer matrix data.</p>'
    + '<p>Load data via: <code>python DEALROOM.py ingest --deal ' + _slide_esc(d.code_name || '') + ' --type invoices</code></p>'
    + '</div>'
    + _bmEditableBox('bm_description', 'Add business description here...', editable),
    {caveat: 'No structured commercial data available. Load invoice or customer data to populate this section.', id: 'bm-stub'});
  return h;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Thesis / Scorecard
// ═══════════════════════════════════════════════════════════════════════════════

function renderThesis() {
  var d   = DATA.deal       || {};
  var cdd = DATA.cdd;
  var fin = DATA.financials || {};
  var mc  = DATA.model_context;
  var editable = typeof SERVE_MODE !== 'undefined' && SERVE_MODE && !(typeof INVESTOR_MODE !== 'undefined' && INVESTOR_MODE);

  var h = '';

  // ── Signal bar ──
  if (typeof renderAnswerFirstBar === 'function') {
    var signals = _afCddSignals(cdd).concat(_afFinancialSignals(mc));
    h += renderAnswerFirstBar(signals, {title: 'Investment Thesis Signals'});
  }

  // ── Card 1: Scorecard (auto-computed) ──
  h += _thesisScorecard(cdd, fin, mc, editable);

  // ── Card 2: SWOT ──
  h += _thesisSwot(d, editable);

  // ── Card 3: Strategic rationale ──
  var savedRat = DATA.dd_commentary && DATA.dd_commentary.thesis_rationale;
  var rationale = savedRat || d.investment_thesis || null;
  var companyName = _slide_esc(d.company_name || d.code_name || '[Company]');
  var ratBody = '<div style="font-size:13px;color:#334155;line-height:1.7;min-height:60px">'
    + (rationale ? _slide_esc(rationale) : '<span style="color:#94a3b8;font-style:italic">Add strategic rationale...</span>')
    + '</div>';

  h += _afDDCard('Strategic rationale', 'grey', rationale ? 3 : 1, ratBody, {
    editable: editable, field: 'thesis_rationale', id: 'thesis-rationale'
  });

  return h;
}

function _thesisScorecard(cdd, fin, mc, editable) {
  var seg = cdd && cdd.segments || {};
  var fullYears = seg.full_years || [];
  var latestStr = seg.latest_full_year ? String(seg.latest_full_year) : null;
  var totals = seg.totals || {};

  function scoreDot(verdict) {
    var c = _afColor(verdict);
    return '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c.dot + '"></span>';
  }

  function trendArrow(dir) {
    var map = {up: '↑', flat: '→', down: '↓'};
    var col = {up: '#10b981', flat: '#6b7280', down: '#ef4444'};
    return '<span style="color:' + (col[dir] || '#6b7280') + ';font-weight:700">' + (map[dir] || '→') + '</span>';
  }

  // ── Auto-compute scorecard rows ──
  var rows = [];

  // 1. Revenue CAGR
  var cagr = null, cagrVerdict = 'grey', cagrConf = 1, cagrTrend = 'flat';
  if (fullYears.length >= 2) {
    var t0 = totals[String(fullYears[0])];
    var tN = totals[String(fullYears[fullYears.length - 1])];
    var nY = fullYears.length - 1;
    if (t0 && t0 > 0 && tN && tN > 0 && nY > 0) {
      cagr = (Math.pow(tN / t0, 1 / nY) - 1) * 100;
      cagrVerdict = cagr >= 5 ? 'green' : cagr >= 0 ? 'yellow' : 'red';
      cagrConf = fullYears.length >= 3 ? 4 : 3;
      cagrTrend = cagr > 2 ? 'up' : cagr < -2 ? 'down' : 'flat';
    }
  }
  rows.push({
    criterion: 'Revenue CAGR',
    value: cagr != null ? (cagr >= 0 ? '+' : '') + cagr.toFixed(1) + '%' : '—',
    verdict: cagrVerdict, confidence: cagrConf, trend: cagrTrend,
    source: cagr != null ? 'Invoice data ' + fullYears[0] + '–' + fullYears[fullYears.length - 1] : 'No multi-year data'
  });

  // 2. EBITDA Margin
  var ebitdaMargin = null, emVerdict = 'grey', emConf = 1, emTrend = 'flat';
  var pnl = fin.pnl || {};
  var pnlYears = Object.keys(pnl).filter(function(k){return /^\d{4}$/.test(k);}).sort();
  if (pnlYears.length) {
    var lpnl = pnl[pnlYears[pnlYears.length - 1]] || {};
    if (lpnl.ebitda_margin_pct != null) {
      ebitdaMargin = lpnl.ebitda_margin_pct;
    } else {
      var ebitdaEntry = lpnl.ebitda || lpnl.EBITDA;
      var revEntry = lpnl.revenue || lpnl.Umsatzerloese;
      if (ebitdaEntry && revEntry && ebitdaEntry.primary && revEntry.primary) {
        var eV = ebitdaEntry.primary.value;
        var rV = revEntry.primary.value;
        if (rV && rV > 0) ebitdaMargin = eV / rV * 100;
      }
    }
    if (ebitdaMargin != null) {
      emVerdict = ebitdaMargin >= 12 ? 'green' : ebitdaMargin >= 6 ? 'yellow' : 'red';
      emConf = pnlYears.length >= 2 ? 3 : 2;
      if (pnlYears.length >= 2) {
        var prevPnl = pnl[pnlYears[pnlYears.length - 2]] || {};
        var prevMarg = prevPnl.ebitda_margin_pct;
        if (prevMarg != null) {
          emTrend = ebitdaMargin > prevMarg + 1 ? 'up' : ebitdaMargin < prevMarg - 1 ? 'down' : 'flat';
        }
      }
    }
  }
  rows.push({
    criterion: 'EBITDA Margin',
    value: ebitdaMargin != null ? ebitdaMargin.toFixed(1) + '%' : '—',
    verdict: emVerdict, confidence: emConf, trend: emTrend,
    source: ebitdaMargin != null ? 'P&L ' + pnlYears[pnlYears.length - 1] : 'No P&L data'
  });

  // 3. Gross Margin
  var gm = null, gmVerdict = 'grey', gmConf = 1;
  if (cdd && cdd.segments && cdd.segments.rows) {
    var segRows = cdd.segments.rows;
    var wR = 0, wG = 0;
    segRows.forEach(function(r) {
      if (latestStr && r.rev[latestStr] && r.gm_pct && r.gm_pct[latestStr] != null) {
        var rv = r.rev[latestStr];
        wR += rv; wG += rv * r.gm_pct[latestStr] / 100;
      }
    });
    if (wR > 0) {
      gm = wG / wR * 100;
      gmVerdict = gm >= 35 ? 'green' : gm >= 20 ? 'yellow' : 'red';
      gmConf = 3;
    }
  }
  rows.push({
    criterion: 'Gross Margin',
    value: gm != null ? gm.toFixed(1) + '%' : '—',
    verdict: gmVerdict, confidence: gmConf, trend: 'flat',
    source: gm != null ? 'Invoice data (materials-only) ' + (latestStr || '') : 'No segment GM data'
  });

  // 4. Customer concentration (Top 3)
  var conc = cdd && cdd.concentration;
  var top3pct = null, concVerdict = 'grey', concConf = 1;
  if (conc && conc.tiers) {
    var t3 = conc.tiers.find(function(t) { return t.n === 3; });
    if (t3 && t3.pct != null) {
      top3pct = t3.pct;
      concVerdict = top3pct <= 25 ? 'green' : top3pct <= 45 ? 'yellow' : 'red';
      concConf = 4;
    }
  }
  rows.push({
    criterion: 'Cust. Conc. (Top 3)',
    value: top3pct != null ? top3pct.toFixed(0) + '%' : '—',
    verdict: concVerdict, confidence: concConf, trend: 'flat',
    source: top3pct != null ? 'Customer matrix ' + (conc.year || '') : 'No customer data'
  });

  // 5. Logo Retention
  var logoRet = null, lrVerdict = 'grey', lrConf = 1, lrTrend = 'flat';
  var ret = cdd && cdd.retention;
  if (ret && ret.length) {
    var fullRet = ret.filter(function(r) { return !r.partial; });
    var lr = fullRet.length ? fullRet[fullRet.length - 1] : ret[ret.length - 1];
    if (lr && lr.logo_pct != null) {
      logoRet = lr.logo_pct;
      lrVerdict = logoRet >= 80 ? 'green' : logoRet >= 65 ? 'yellow' : 'red';
      lrConf = lr.partial ? 2 : (fullRet.length >= 2 ? 4 : 3);
    }
  }
  rows.push({
    criterion: 'Logo Retention',
    value: logoRet != null ? logoRet.toFixed(0) + '%' : '—',
    verdict: lrVerdict, confidence: lrConf, trend: lrTrend,
    source: logoRet != null ? 'Customer matrix (full-year pairs)' : 'No retention data'
  });

  // 6. NRR
  var nrr = null, nrrVerdict = 'grey', nrrConf = 1;
  if (ret && ret.length) {
    var fullRet2 = ret.filter(function(r) { return !r.partial; });
    var lr2 = fullRet2.length ? fullRet2[fullRet2.length - 1] : ret[ret.length - 1];
    if (lr2 && lr2.nrr_pct != null) {
      nrr = lr2.nrr_pct;
      nrrVerdict = nrr >= 100 ? 'green' : nrr >= 85 ? 'yellow' : 'red';
      nrrConf = lr2.partial ? 2 : 3;
    }
  }
  rows.push({
    criterion: 'Net Rev. Retention',
    value: nrr != null ? nrr.toFixed(0) + '%' : '—',
    verdict: nrrVerdict, confidence: nrrConf, trend: 'flat',
    source: nrr != null ? 'Customer matrix' : 'No retention data'
  });

  // 7. EV/EBITDA multiple
  var mult = null, multVerdict = 'grey', multConf = 1;
  if (mc && mc.params && mc.params.multiple != null) {
    mult = mc.params.multiple;
    multVerdict = mult <= 5 ? 'green' : mult <= 6.5 ? 'yellow' : 'red';
    multConf = 4;
  }
  rows.push({
    criterion: 'EV / EBITDA',
    value: mult != null ? mult.toFixed(1) + 'x' : '—',
    verdict: multVerdict, confidence: multConf, trend: 'flat',
    source: mult != null ? 'Model parameters' : 'No valuation model'
  });

  // 8. Red flags
  var flags = cdd && cdd.findings && cdd.findings.red_flags || [];
  var high = flags.filter(function(f) { return f.severity === 'HIGH'; }).length;
  rows.push({
    criterion: 'Red Flags',
    value: flags.length === 0 ? 'None' : flags.length + (high ? ' (' + high + ' HIGH)' : ''),
    verdict: flags.length === 0 ? 'green' : high > 0 ? 'red' : 'yellow',
    confidence: flags.length > 0 ? 3 : 2,
    trend: 'flat',
    source: flags.length > 0 ? 'CDD findings' : 'No structured DD items'
  });

  // ── Overall scorecard confidence ──
  var dataRows = rows.filter(function(r) { return r.value !== '—'; });
  var overallConf = _afSectionConfidence(rows.map(function(r) {
    return {present: r.value !== '—', weight: 1};
  }));

  var greenCount = rows.filter(function(r){return r.verdict==='green';}).length;
  var redCount = rows.filter(function(r){return r.verdict==='red';}).length;
  var overallVerdict = redCount >= 2 ? 'red' : redCount >= 1 ? 'yellow' : greenCount >= rows.length * 0.6 ? 'green' : 'yellow';
  var headline = dataRows.length + '/' + rows.length + ' scorecard criteria populated — '
    + greenCount + ' green, ' + (rows.length - greenCount - redCount) + ' yellow/grey, ' + redCount + ' red';

  // ── Legend ──
  var legend = '<div style="display:flex;gap:16px;font-size:10px;color:#64748b;margin-bottom:8px;flex-wrap:wrap">';
  legend += '<span>' + scoreDot('green') + ' Strong</span>';
  legend += '<span>' + scoreDot('yellow') + ' Watch</span>';
  legend += '<span>' + scoreDot('red') + ' Risk</span>';
  legend += '<span>' + _afHarvey(4, 'grey') + ' Full evidence</span>';
  legend += '<span>' + _afHarvey(2, 'grey') + ' Partial</span>';
  legend += '<span>' + _afHarvey(1, 'grey') + ' Low</span>';
  legend += '</div>';

  // ── Table ──
  var table = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  table += '<thead><tr style="border-bottom:2px solid #e2e8f0">';
  table += '<th style="text-align:left;padding:6px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase;width:30%">Criterion</th>';
  table += '<th style="text-align:center;padding:6px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase;width:18%">Value</th>';
  table += '<th style="text-align:center;padding:6px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase;width:8%">Rating</th>';
  table += '<th style="text-align:center;padding:6px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase;width:8%">Conf.</th>';
  table += '<th style="text-align:center;padding:6px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase;width:6%">Trend</th>';
  table += '<th style="text-align:left;padding:6px 8px;color:#64748b;font-weight:600;font-size:10px;text-transform:uppercase">Source</th>';
  table += '</tr></thead><tbody>';

  rows.forEach(function(r, i) {
    var bg = i % 2 === 0 ? '#fff' : '#f8fafc';
    table += '<tr style="border-bottom:1px solid #f1f5f9;background:' + bg + '">';
    table += '<td style="padding:7px 8px;font-weight:500;color:#1e293b">' + r.criterion + '</td>';
    table += '<td style="padding:7px 8px;text-align:center;font-weight:700;color:#0891B2">' + r.value + '</td>';
    table += '<td style="padding:7px 8px;text-align:center">' + scoreDot(r.verdict) + '</td>';
    table += '<td style="padding:7px 8px;text-align:center">' + _afHarvey(r.confidence, r.verdict) + '</td>';
    table += '<td style="padding:7px 8px;text-align:center">' + trendArrow(r.trend) + '</td>';
    table += '<td style="padding:7px 8px;font-size:11px;color:#94a3b8">' + r.source + '</td>';
    table += '</tr>';
  });
  table += '</tbody></table>';

  var body = legend + table;
  body += _bmEditableBox('thesis_scorecard_comment',
    'Scorecard auto-populated from available data. Criteria without values need data loading or management input.',
    editable);

  return _afDDCard(headline, overallVerdict, overallConf.level, body, {id: 'thesis-scorecard'});
}

function _thesisSwot(d, editable) {
  var swot = d.swot_json || null;
  var isPlaceholder = !swot;

  function quadrant(label, color, bg, bullets) {
    var h = '<div style="background:' + bg + ';border-radius:6px;padding:10px 12px;min-height:90px">';
    h += '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:' + color + ';margin-bottom:6px">' + label + '</div>';
    h += '<ul style="margin:0;padding-left:14px;font-size:12px;color:#334155;line-height:1.5">';
    bullets.forEach(function(b) {
      h += '<li style="margin-bottom:3px">' + b + '</li>';
    });
    h += '</ul></div>';
    return h;
  }

  var ph = function(s) { return '<em style="font-size:10px;color:#94a3b8"> [placeholder]</em>'; };
  var strengths     = swot ? swot.strengths     : ['High repeat customer base', 'Specialized market position', 'Strong EBITDA margins'];
  var weaknesses    = swot ? swot.weaknesses    : ['Owner-manager dependency', 'Single location', 'Key man concentration'];
  var opportunities = swot ? swot.opportunities : ['Cross-sell / upsell potential', 'Digitisation', 'Add-on M&A platform'];
  var threats       = swot ? swot.threats       : ['Reimbursement cuts', 'Online competition', 'Margin pressure from suppliers'];

  if (isPlaceholder) {
    strengths = strengths.map(function(s) { return s + ph(); });
    weaknesses = weaknesses.map(function(s) { return s + ph(); });
    opportunities = opportunities.map(function(s) { return s + ph(); });
    threats = threats.map(function(s) { return s + ph(); });
  }

  var body = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
  body += quadrant('Strengths', '#15803d', '#dcfce7', strengths);
  body += quadrant('Weaknesses', '#92400e', '#fef3c7', weaknesses);
  body += quadrant('Opportunities', '#1e40af', '#dbeafe', opportunities);
  body += quadrant('Threats', '#991b1b', '#fee2e2', threats);
  body += '</div>';

  body += _bmEditableBox('thesis_swot_comment', 'SWOT analysis — update with deal-specific findings from DD.', editable);

  return _afDDCard('SWOT Assessment', isPlaceholder ? 'yellow' : 'green', isPlaceholder ? 2 : 3, body, {
    caveat: isPlaceholder ? 'Placeholder data — populate from deal analysis and RFI responses.' : null,
    id: 'thesis-swot'
  });
}
