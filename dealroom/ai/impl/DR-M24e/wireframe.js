/**
 * DR-M24e — Customers & Suppliers Slide (Section 7)
 *
 * Hero chart: horizontal stacked bar showing customer concentration segments.
 * KPIs: Top-1 Share, Top-3 Share, Total Customers, Retention Rate.
 * Detail area: placeholder for existing renderCustomers() output.
 *
 * Dependencies:
 *   - DR-M24a: renderSlideSection(), formatKPI()
 *   - DR-M24b: getKPIsBySection(), KPI_REGISTRY.customers
 *   - Global DATA object populated by dashboard loader
 *
 * No external libraries. String-concatenated HTML. No ES modules.
 */

// ---------------------------------------------------------------------------
// Mock data — used when DATA.customers.top10 is absent
// ---------------------------------------------------------------------------
var MOCK_TOP10 = {
  '2025': [
    { rank: 1, name: 'Klinikum Südstadt', revenue: 890, pct: 15.3 },
    { rank: 2, name: 'MVZ Berlin', revenue: 720, pct: 12.4 },
    { rank: 3, name: 'Praxis Dr. Weber', revenue: 580, pct: 10.0 },
    { rank: 4, name: 'Medizinzentrum Nord', revenue: 420, pct: 7.2 },
    { rank: 5, name: 'KH Charité', revenue: 380, pct: 6.5 },
    { rank: 6, name: 'Rehaklinik Ost', revenue: 310, pct: 5.3 },
    { rank: 7, name: 'Praxis Schmidt', revenue: 250, pct: 4.3 },
    { rank: 8, name: 'MVZ Steglitz', revenue: 200, pct: 3.4 },
    { rank: 9, name: 'Tagesklinik West', revenue: 180, pct: 3.1 },
    { rank: 10, name: 'Dr. Fischer GmbH', revenue: 150, pct: 2.6 }
  ]
};

// ---------------------------------------------------------------------------
// CSS injection for concentration chart (IIFE — idempotent)
// ---------------------------------------------------------------------------
(function injectConcentrationCSS() {
  if (document.getElementById('concentration-chart-css')) return;

  var css = [
    '.conc-chart-wrap {',
    '  width: 100%;',
    '  font-family: Arial, sans-serif;',
    '}',

    '.conc-bar {',
    '  display: flex;',
    '  height: 40px;',
    '  border-radius: 4px;',
    '  overflow: hidden;',
    '  width: 100%;',
    '}',

    '.conc-seg {',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  font-size: 12px;',
    '  font-weight: 600;',
    '  color: #fff;',
    '  white-space: nowrap;',
    '  min-width: 0;',
    '  overflow: hidden;',
    '  text-overflow: ellipsis;',
    '  padding: 0 6px;',
    '}',

    '.conc-seg--rest {',
    '  color: #475569;',
    '}',

    '.conc-legend {',
    '  display: flex;',
    '  flex-wrap: wrap;',
    '  gap: 12px;',
    '  margin-top: 10px;',
    '}',

    '.conc-legend-item {',
    '  display: flex;',
    '  align-items: center;',
    '  gap: 5px;',
    '  font-size: 11px;',
    '  color: #475569;',
    '}',

    '.conc-legend-dot {',
    '  width: 10px;',
    '  height: 10px;',
    '  border-radius: 2px;',
    '  flex-shrink: 0;',
    '}',

    '.conc-annotation {',
    '  margin-top: 8px;',
    '  font-size: 11px;',
    '  color: #94a3b8;',
    '  font-family: Arial, sans-serif;',
    '}'
  ].join('\n');

  var style = document.createElement('style');
  style.id = 'concentration-chart-css';
  style.textContent = css;
  document.head.appendChild(style);
})();

// ---------------------------------------------------------------------------
// _conc_getSegments(data)
// Compute concentration segments from top10 data or metrics fallback.
// Returns { top1, top2to3, top4to10, rest, year, count }
// ---------------------------------------------------------------------------
function _conc_getSegments(data) {
  var customers = data && data.customers;
  if (!customers) return null;

  var top10 = customers.top10;
  var metrics = customers.metrics;
  var year = null;
  var count = null;
  var top1 = null;
  var top2to3 = null;
  var top4to10 = null;

  // Primary path: compute from top10 array
  if (top10) {
    var years = Object.keys(top10)
      .filter(function(k) { return /^\d{4}$/.test(k); })
      .sort();
    if (years.length) {
      year = years[years.length - 1];
      var entries = top10[year];
      if (Array.isArray(entries) && entries.length > 0) {
        var sorted = entries.slice().sort(function(a, b) { return a.rank - b.rank; });
        top1 = sorted[0] ? sorted[0].pct : 0;
        top2to3 = 0;
        for (var i = 1; i < 3 && i < sorted.length; i++) {
          top2to3 += (sorted[i].pct || 0);
        }
        top4to10 = 0;
        for (var j = 3; j < 10 && j < sorted.length; j++) {
          top4to10 += (sorted[j].pct || 0);
        }
        count = sorted.length;
      }
    }
  }

  // Fallback: use metrics aggregates
  if (top1 === null && metrics) {
    var mYears = Object.keys(metrics)
      .filter(function(k) { return /^\d{4}$/.test(k); })
      .sort();
    if (mYears.length) {
      year = mYears[mYears.length - 1];
      var m = metrics[year];
      top1 = m.top1_share != null ? (m.top1_share <= 1 ? m.top1_share * 100 : m.top1_share) : 0;
      var top5 = m.top5_share != null ? (m.top5_share <= 1 ? m.top5_share * 100 : m.top5_share) : null;
      var top10s = m.top10_share != null ? (m.top10_share <= 1 ? m.top10_share * 100 : m.top10_share) : null;

      // Estimate segments from available aggregate shares
      if (top5 != null) {
        top2to3 = Math.max(0, top5 - top1) * 0.6;  // rough split: 60% to 2-3, 40% to 4-5
        var top4to5 = Math.max(0, top5 - top1) * 0.4;
        top4to10 = top10s != null ? Math.max(0, top10s - top5) + top4to5 : top4to5;
      } else {
        top2to3 = 0;
        top4to10 = top10s != null ? Math.max(0, top10s - top1) : 0;
      }

      count = m.customer_count || null;
    }
  }

  if (top1 === null) return null;

  var rest = Math.max(0, 100 - top1 - top2to3 - top4to10);

  return {
    top1: top1,
    top2to3: top2to3,
    top4to10: top4to10,
    rest: rest,
    year: year,
    count: count
  };
}

// ---------------------------------------------------------------------------
// renderConcentrationChart()
// Returns HTML string for the horizontal stacked bar chart.
// Reads from global DATA; falls back to MOCK_TOP10 if no customer data.
// ---------------------------------------------------------------------------
function renderConcentrationChart() {
  var sourceData = (typeof DATA !== 'undefined' && DATA && DATA.customers)
    ? DATA
    : { customers: { top10: MOCK_TOP10 } };

  var seg = _conc_getSegments(sourceData);
  if (!seg) {
    return '<div style="color:#94a3b8;font-size:13px;font-family:Arial,sans-serif;">No customer concentration data available</div>';
  }

  var segments = [
    { label: 'Top 1',    pct: seg.top1,     color: '#0891B2' },
    { label: 'Top 2–3',  pct: seg.top2to3,  color: '#22D3EE' },
    { label: 'Top 4–10', pct: seg.top4to10, color: '#8DE8F6' },
    { label: 'Rest',     pct: seg.rest,      color: '#e2e8f0' }
  ];

  // Build bar segments
  var barHtml = '';
  for (var i = 0; i < segments.length; i++) {
    var s = segments[i];
    if (s.pct <= 0) continue;
    var isRest = s.label === 'Rest';
    var pctLabel = s.pct.toLocaleString('de-DE', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    }) + '%';
    // Only show label if segment is wide enough (>6%)
    var displayLabel = s.pct >= 6 ? pctLabel : '';
    barHtml +=
      '<div class="conc-seg' + (isRest ? ' conc-seg--rest' : '') + '" ' +
      'style="width:' + s.pct.toFixed(1) + '%;background:' + s.color + ';" ' +
      'title="' + s.label + ': ' + pctLabel + '">' +
        displayLabel +
      '</div>';
  }

  // Build legend
  var legendHtml = '';
  for (var j = 0; j < segments.length; j++) {
    var seg_j = segments[j];
    if (seg_j.pct <= 0) continue;
    var pctStr = seg_j.pct.toLocaleString('de-DE', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    }) + '%';
    legendHtml +=
      '<div class="conc-legend-item">' +
        '<div class="conc-legend-dot" style="background:' + seg_j.color + ';"></div>' +
        seg_j.label + ': ' + pctStr +
      '</div>';
  }

  // Annotation
  var annotationParts = [];
  if (seg.year) annotationParts.push('Year: ' + seg.year);
  if (seg.count) annotationParts.push(seg.count.toLocaleString('de-DE') + ' customers');
  var annotationHtml = annotationParts.length
    ? '<div class="conc-annotation">' + annotationParts.join(' | ') + '</div>'
    : '';

  return (
    '<div class="conc-chart-wrap">' +
      '<div class="conc-bar">' + barHtml + '</div>' +
      '<div class="conc-legend">' + legendHtml + '</div>' +
      annotationHtml +
    '</div>'
  );
}

// ---------------------------------------------------------------------------
// renderCustomersSlide()
// Assembles the full Section 7 slide using renderSlideSection from DR-M24a.
// ---------------------------------------------------------------------------
function renderCustomersSlide() {
  var heroHtml = renderConcentrationChart();

  // Compute KPIs via registry
  var sourceData = (typeof DATA !== 'undefined' && DATA) ? DATA : null;
  var kpis = [];

  if (sourceData && typeof getKPIsBySection === 'function') {
    var computed = getKPIsBySection(sourceData, 'customers');
    for (var i = 0; i < computed.length; i++) {
      kpis.push({
        label: computed[i].label,
        value: computed[i].value,
        format: computed[i].format,
        bullet: computed[i].bullet
      });
    }
  }

  // If no live data, populate from mock for preview
  if (kpis.length === 0) {
    kpis = [
      { label: 'Top-1 Customer Share', value: 15.3, format: 'pct', bullet: 'Single-customer dependency risk' },
      { label: 'Top-3 Customer Share', value: 37.7, format: 'pct', bullet: 'Revenue concentration in top accounts' },
      { label: 'Total Customers', value: 142, format: 'count', bullet: 'Breadth of customer base' },
      { label: 'Retention Rate', value: 91.2, format: 'pct', bullet: 'Customer stickiness — churn inverse' }
    ];
  }

  // Detail area — delegate to existing render functions if available
  var detailHtml = '';
  if (typeof renderCustomersWithSuppliers === 'function') {
    detailHtml = renderCustomersWithSuppliers();
  } else if (typeof renderCustomers === 'function') {
    detailHtml = renderCustomers();
  } else {
    detailHtml =
      '<div style="color:#94a3b8;font-size:13px;font-family:Arial,sans-serif;padding:12px 0;">' +
        'Customer &amp; supplier detail tables will render here.' +
      '</div>';
  }

  return renderSlideSection('customers', 'Customers & Suppliers', heroHtml, kpis, detailHtml);
}
