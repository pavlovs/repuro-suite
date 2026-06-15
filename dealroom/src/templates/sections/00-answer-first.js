// ─── Answer-First utilities (DR-Redesign) ─────────────────────────────────────
// Provides: renderAnswerFirstBar(), _afCddSignals(), _afFinancialSignals(),
//           _afColor(), _afChip(), _afDealVerdictChips()
// Load order: this file sorts first (00-) so all section files can use it.

function _afColor(verdict) {
  var C = {
    green:  { bg:'#f0fdf4', border:'#86efac', text:'#166534', dot:'#22c55e' },
    yellow: { bg:'#fffbeb', border:'#fde68a', text:'#92400e', dot:'#f59e0b' },
    red:    { bg:'#fef2f2', border:'#fecaca', text:'#991b1b', dot:'#ef4444' },
    grey:   { bg:'#f8fafc', border:'#e2e8f0', text:'#475569', dot:'#94a3b8' },
  };
  return C[verdict] || C.grey;
}

function _afChip(label, value, verdict, detail) {
  var c = _afColor(verdict || 'grey');
  var safe = function(s) { return String(s).replace(/[<>&"]/g, function(m){return({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'})[m];}); };
  var tip = detail ? ' title="' + safe(detail) + '"' : '';
  return '<div' + tip + ' style="'
    + 'display:flex;flex-direction:column;gap:2px;cursor:default;'
    + 'background:' + c.bg + ';border:1px solid ' + c.border + ';border-radius:8px;'
    + 'padding:9px 13px;min-width:110px;flex:1;max-width:220px'
    + '">'
    + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:' + c.text + '">'
    + '<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:' + c.dot + ';margin-right:5px;vertical-align:middle"></span>'
    + safe(label)
    + '</div>'
    + '<div style="font-size:16px;font-weight:700;color:#1e293b;line-height:1.2">' + value + '</div>'
    + (detail ? '<div style="font-size:10px;color:' + c.text + ';margin-top:2px;line-height:1.35;opacity:.85">' + safe(String(detail)) + '</div>' : '')
    + '</div>';
}

function renderAnswerFirstBar(items, opts) {
  opts = opts || {};
  var valid = (items || []).filter(Boolean);
  if (!valid.length) return '';
  var h = '<div style="'
    + 'display:flex;align-items:stretch;gap:10px;flex-wrap:wrap;'
    + 'margin-bottom:18px;padding:12px 14px;'
    + 'background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px'
    + '">';
  if (opts.title) {
    h += '<div style="width:100%;margin-bottom:6px;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.6px">'
      + String(opts.title).replace(/[<>&]/g, function(m){return({'<':'&lt;','>':'&gt;','&':'&amp;'})[m];})
      + '</div>';
  }
  valid.forEach(function(it) { h += _afChip(it.label, it.value || '—', it.verdict || 'grey', it.detail || null); });
  h += '</div>';
  return h;
}

// ── CDD signals ───────────────────────────────────────────────────────────────
function _afCddSignals(cdd) {
  var out = [];
  if (!cdd) return out;

  var seg = cdd.segments;
  if (seg && seg.rows && seg.rows.length && seg.years && seg.years.length > 1) {
    var allYrs = seg.years.map(String);
    var ytdStr = cdd.meta && cdd.meta.ytd_year ? String(cdd.meta.ytd_year) : null;
    var fullYrs = ytdStr ? allYrs.filter(function(y) { return y !== ytdStr; }) : allYrs;
    var y0 = fullYrs[0], y1 = fullYrs.length > 1 ? fullYrs[fullYrs.length - 1] : y0;
    var t0 = seg.totals[y0], t1 = seg.totals[y1];
    var cagrN = fullYrs.length > 1 ? fullYrs.length - 1 : 1;
    var cagr = (t0 && t1 && cagrN > 0) ? (Math.pow(t1 / t0, 1 / cagrN) - 1) * 100 : null;
    out.push({
      label: 'Rev. CAGR',
      value: cagr != null ? (cagr >= 0 ? '+' : '') + cagr.toFixed(0) + '%' : '—',
      verdict: cagr == null ? 'grey' : cagr >= 5 ? 'green' : cagr >= 0 ? 'yellow' : 'red',
      detail: y0 + '–' + y1 + ' revenue CAGR (full years only)',
    });
    var latest = String(seg.latest_full_year);
    var gpSum = 0, rvSum = 0;
    seg.rows.forEach(function(s) {
      var rv = s.rev[latest], gm = s.gm_pct[latest];
      if (rv != null && gm != null) { rvSum += rv; gpSum += rv * gm / 100; }
    });
    var gm = rvSum > 0 ? gpSum / rvSum * 100 : null;
    out.push({
      label: 'Gross Margin',
      value: gm != null ? gm.toFixed(0) + '%' : '—',
      verdict: gm == null ? 'grey' : gm >= 35 ? 'green' : gm >= 20 ? 'yellow' : 'red',
      detail: 'Materials-only gross margin in ' + latest,
    });
  }

  var conc = cdd.concentration;
  if (conc && conc.tiers && conc.tiers.length) {
    var best = conc.tiers.reduce(function(b, t) {
      return (!b || (t.n <= 3 && t.n > (b.n || 0))) ? t : b;
    }, null);
    if (best && best.pct != null) {
      out.push({
        label: 'Top-' + (best.n || 3) + ' Conc.',
        value: best.pct.toFixed(0) + '%',
        verdict: best.pct <= 25 ? 'green' : best.pct <= 45 ? 'yellow' : 'red',
        detail: 'Top ' + best.n + ' customers share of ' + (conc.year || '') + ' revenue',
      });
    }
  }

  var ret = cdd.retention;
  if (ret && ret.length) {
    var lr = ret[ret.length - 1];
    if (lr) {
      if (lr.logo_pct != null) {
        out.push({
          label: 'Logo Ret.',
          value: lr.logo_pct.toFixed(0) + '%',
          verdict: lr.logo_pct >= 80 ? 'green' : lr.logo_pct >= 65 ? 'yellow' : 'red',
          detail: 'Logo retention in ' + (lr.period || ''),
        });
      }
      if (lr.nrr_pct != null) {
        out.push({
          label: 'NRR',
          value: lr.nrr_pct.toFixed(0) + '%',
          verdict: lr.nrr_pct >= 90 ? 'green' : lr.nrr_pct >= 70 ? 'yellow' : 'red',
          detail: 'Net revenue retention in ' + (lr.period || ''),
        });
      }
    }
  }

  var f = cdd.findings;
  if (f && f.red_flags) {
    var flags = f.red_flags || [];
    var high = flags.filter(function(r) { return r.severity === 'HIGH'; }).length;
    out.push({
      label: 'Red Flags',
      value: flags.length === 0 ? 'None' : flags.length + (high ? ' · ' + high + ' HIGH' : ''),
      verdict: flags.length === 0 ? 'green' : high > 0 ? 'red' : 'yellow',
      detail: flags.length + ' findings (' + high + ' HIGH, ' + (flags.length - high) + ' MEDIUM)',
    });
  }

  return out;
}

// ── Financial (valuation) signals ─────────────────────────────────────────────
function _afFinancialSignals(mc) {
  var out = [];
  if (!mc) return out;
  var p = mc.params || {}, w = mc.waterfall || {};

  var mult = p.multiple;
  out.push({
    label: 'EV / EBITDA',
    value: mult != null ? mult.toFixed(1) + 'x' : '—',
    verdict: mult == null ? 'grey' : mult <= 5 ? 'green' : mult <= 6.5 ? 'yellow' : 'red',
    detail: 'Closing EBITDA multiple (excl. earn-out)',
  });

  var ebitda = p.ebitda_basis_override != null ? p.ebitda_basis_override : mc.ebitda_basis;
  out.push({
    label: 'Adj. EBITDA',
    value: ebitda != null ? (ebitda >= 1000 ? '€' + (ebitda / 1000).toFixed(1) + 'M' : '€' + Math.round(ebitda) + 'K') : '—',
    verdict: 'grey',
    detail: 'Adjusted EBITDA basis used for valuation',
  });

  var evT = w.ev_total, evC = w.ev_at_closing;
  if (evT != null && evC != null && evT > 0) {
    var eoPct = (evT - evC) / evT * 100;
    out.push({
      label: 'Earn-Out %',
      value: eoPct.toFixed(0) + '%',
      verdict: eoPct <= 10 ? 'green' : eoPct <= 25 ? 'yellow' : 'red',
      detail: 'Contingent earn-out as share of total EV',
    });
  }

  var eq = w.equity_value;
  if (eq != null) {
    out.push({
      label: 'Equity Value',
      value: Math.abs(eq) >= 1000 ? '€' + (eq / 1000).toFixed(1) + 'M' : '€' + Math.round(eq) + 'K',
      verdict: 'grey',
      detail: 'Net of cash/debt and permitted leakage',
    });
  }

  return out;
}

// ── Deal-level verdict chips (for cockpit) ────────────────────────────────────
function _afDealVerdictChips() {
  var chips = [];
  var cdd = DATA.cdd;
  var mc = DATA.model_context;

  if (cdd && cdd.segments && cdd.segments.years && cdd.segments.years.length > 1) {
    var _allY = cdd.segments.years.map(String);
    var _ytd = cdd.meta && cdd.meta.ytd_year ? String(cdd.meta.ytd_year) : null;
    var _fy = _ytd ? _allY.filter(function(y){return y!==_ytd;}) : _allY;
    var _y0 = _fy[0], _y1 = _fy.length > 1 ? _fy[_fy.length-1] : _y0;
    var t0 = cdd.segments.totals[_y0], t1 = cdd.segments.totals[_y1];
    var _n = _fy.length > 1 ? _fy.length - 1 : 1;
    var cagr = (t0 && t1 && _n > 0) ? (Math.pow(t1 / t0, 1 / _n) - 1) * 100 : null;
    chips.push({
      label: 'Revenue',
      val: cagr != null ? (cagr >= 0 ? '+' : '') + cagr.toFixed(0) + '% CAGR' : 'No data',
      verdict: cagr == null ? 'grey' : cagr >= 5 ? 'green' : cagr >= 0 ? 'yellow' : 'red',
    });
  }

  if (cdd && cdd.concentration && cdd.concentration.tiers && cdd.concentration.tiers.length) {
    var best = cdd.concentration.tiers.reduce(function(b, t) {
      return (!b || (t.n <= 3 && t.n > (b.n || 0))) ? t : b;
    }, null);
    if (best && best.pct != null) {
      chips.push({
        label: 'Customers',
        val: 'Top-' + best.n + ' = ' + best.pct.toFixed(0) + '%',
        verdict: best.pct <= 25 ? 'green' : best.pct <= 45 ? 'yellow' : 'red',
      });
    }
  }

  if (mc && mc.params && mc.params.multiple != null) {
    var m = mc.params.multiple;
    chips.push({
      label: 'Valuation',
      val: m.toFixed(1) + 'x EBITDA',
      verdict: m <= 5 ? 'green' : m <= 6.5 ? 'yellow' : 'red',
    });
  }

  if (cdd && cdd.findings && cdd.findings.red_flags) {
    var flags = cdd.findings.red_flags;
    var high = flags.filter(function(r) { return r.severity === 'HIGH'; }).length;
    chips.push({
      label: 'Risks',
      val: flags.length === 0 ? 'No flags' : flags.length + ' flag' + (flags.length > 1 ? 's' : '') + (high ? ' (' + high + ' HIGH)' : ''),
      verdict: flags.length === 0 ? 'green' : high > 0 ? 'red' : 'yellow',
    });
  }

  return chips;
}

// ── Harvey Ball (1-4 quarters filled, colored) ───────────────────────────────
function _afHarvey(level, verdict) {
  // level: 1=low confidence, 2=partial, 3=good, 4=full confidence
  // verdict: 'green','yellow','red','grey'
  var c = _afColor(verdict || 'grey');
  var fill = c.dot;
  var bg = '#e2e8f0';
  var r = 9;
  var svg = '<svg width="20" height="20" viewBox="0 0 20 20" style="vertical-align:middle">';
  svg += '<circle cx="10" cy="10" r="' + r + '" fill="' + bg + '" stroke="' + c.border + '" stroke-width="1"/>';
  if (level >= 4) {
    svg += '<circle cx="10" cy="10" r="' + r + '" fill="' + fill + '"/>';
  } else if (level === 3) {
    svg += '<path d="M10 1 A9 9 0 1 0 10 19 A9 9 0 0 1 10 1 Z" fill="' + fill + '"/>';
    svg += '<path d="M10 1 A9 9 0 0 1 19 10 L10 10 Z" fill="' + fill + '"/>';
  } else if (level === 2) {
    svg += '<path d="M10 1 A9 9 0 0 0 10 19 L10 10 Z" fill="' + fill + '"/>';
  } else if (level === 1) {
    svg += '<path d="M10 1 A9 9 0 0 0 1 10 L10 10 Z" fill="' + fill + '"/>';
  }
  svg += '</svg>';
  return svg;
}

// ── Confidence-gated DD card ─────────────────────────────────────────────────
// headline: the answer-first insight (string)
// verdict: 'green','yellow','red'
// confidence: 1-4 (Harvey ball fill level)
// bodyHtml: chart + bullets HTML
// opts: { editable, field, caveat, id }
function _afDDCard(headline, verdict, confidence, bodyHtml, opts) {
  opts = opts || {};
  var c = _afColor(verdict);
  var safe = function(s) { return String(s||'').replace(/[<>&"]/g, function(m){return({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'})[m];}); };
  var editAttr = (opts.editable && opts.field) ? ' contenteditable="true" data-field="' + opts.field + '"' : '';
  var idAttr = opts.id ? ' id="' + opts.id + '"' : '';

  var h = '<div class="af-dd-card"' + idAttr + ' style="'
    + 'background:#fff;border:1px solid ' + c.border + ';border-radius:8px;margin-bottom:16px;overflow:hidden'
    + '">';

  // Header bar with verdict dot + headline + Harvey ball
  h += '<div style="'
    + 'display:flex;align-items:center;gap:10px;padding:10px 16px;'
    + 'background:' + c.bg + ';border-bottom:1px solid ' + c.border
    + '">';
  h += '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c.dot + ';flex-shrink:0"></span>';
  h += '<span style="flex:1;font-size:14px;font-weight:700;color:#1e293b">' + safe(headline) + '</span>';
  h += '<span title="Confidence: ' + confidence + '/4">' + _afHarvey(confidence, verdict) + '</span>';
  h += '</div>';

  // Caveat (amber/red auto-caveat)
  if (opts.caveat) {
    h += '<div style="padding:6px 16px;font-size:11px;color:' + c.text + ';background:' + c.bg + ';border-bottom:1px solid ' + c.border + '">'
      + safe(opts.caveat) + '</div>';
  }

  // Body: chart + bullets (editable)
  h += '<div style="padding:16px"' + editAttr + '>' + bodyHtml + '</div>';

  h += '</div>';
  return h;
}

// ── Auto-compute section confidence from data availability ───────────────────
function _afSectionConfidence(checks) {
  // checks: [{present: bool, weight: 1|2|3}]
  // Returns {level: 1-4, verdict: 'green'|'yellow'|'red'}
  var total = 0, score = 0;
  for (var i = 0; i < checks.length; i++) {
    total += (checks[i].weight || 1);
    if (checks[i].present) score += (checks[i].weight || 1);
  }
  if (total === 0) return {level: 1, verdict: 'grey'};
  var pct = score / total;
  var level = pct >= 0.9 ? 4 : pct >= 0.65 ? 3 : pct >= 0.35 ? 2 : 1;
  var verdict = pct >= 0.75 ? 'green' : pct >= 0.4 ? 'yellow' : 'red';
  return {level: level, verdict: verdict};
}
