/**
 * DR-M24d — Business Model (Section 6) Slide Wireframe
 *
 * Hero chart: Revenue Mix horizontal stacked bar
 * KPIs: Recurring Revenue, Backlog, Avg. Order Value, Active Contracts
 * Detail: delegates to existing renderBusinessModel() if available
 *
 * Dependencies:
 *   - DR-M24a: renderSlideSection(), formatKPI()
 *   - DR-M24b: getKPIsBySection(), KPI_REGISTRY.business_model
 *   - DATA object (global, populated by dashboard loader)
 *
 * All functions global scope. String-concatenated HTML. No frameworks.
 */

// ---------------------------------------------------------------------------
// Palette for stacked bar segments
// ---------------------------------------------------------------------------
var REVENUE_MIX_COLORS = ['#0891B2', '#22D3EE', '#8DE8F6', '#e2e8f0'];

// ---------------------------------------------------------------------------
// Mock data — used when DATA.customers.service_split is unavailable
// ---------------------------------------------------------------------------
var MOCK_SERVICE_SPLIT = [
  { label: 'Medical Distribution', pct: 52 },
  { label: 'Service Contracts', pct: 28 },
  { label: 'Equipment Rental', pct: 12 },
  { label: 'Other', pct: 8 }
];

// ---------------------------------------------------------------------------
// CSS for revenue mix chart (IIFE — idempotent)
// ---------------------------------------------------------------------------
(function injectRevenueMixCSS() {
  if (document.getElementById('revenue-mix-css')) return;

  var css = [
    '.revenue-mix-wrapper {',
    '  width: 100%;',
    '  max-width: 480px;',
    '}',

    '.revenue-mix-title {',
    '  font-family: Arial, sans-serif;',
    '  font-size: 13px;',
    '  font-weight: 700;',
    '  color: #334155;',
    '  margin-bottom: 12px;',
    '  text-transform: uppercase;',
    '  letter-spacing: 0.5px;',
    '}',

    /* The stacked bar container */
    '.revenue-mix-bar {',
    '  display: flex;',
    '  width: 100%;',
    '  height: 32px;',
    '  border-radius: 4px;',
    '  overflow: hidden;',
    '}',

    /* Individual segment inside the bar */
    '.revenue-mix-segment {',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  height: 100%;',
    '  position: relative;',
    '  transition: opacity 0.15s;',
    '}',

    '.revenue-mix-segment:hover {',
    '  opacity: 0.85;',
    '}',

    /* Percentage label inside a segment (only shown for segments > 15%) */
    '.revenue-mix-segment-label {',
    '  font-family: Arial, sans-serif;',
    '  font-size: 11px;',
    '  font-weight: 700;',
    '  color: #fff;',
    '  white-space: nowrap;',
    '  text-shadow: 0 1px 2px rgba(0,0,0,0.3);',
    '}',

    /* Small-segment labels rendered below the bar */
    '.revenue-mix-below-labels {',
    '  display: flex;',
    '  gap: 0;',
    '  margin-top: 2px;',
    '  height: 16px;',
    '}',

    '.revenue-mix-below-label {',
    '  font-family: Arial, sans-serif;',
    '  font-size: 10px;',
    '  font-weight: 600;',
    '  color: #64748b;',
    '  text-align: center;',
    '  overflow: hidden;',
    '}',

    /* Legend below the bar */
    '.revenue-mix-legend {',
    '  display: flex;',
    '  flex-wrap: wrap;',
    '  gap: 12px;',
    '  margin-top: 14px;',
    '}',

    '.revenue-mix-legend-item {',
    '  display: flex;',
    '  align-items: center;',
    '  gap: 5px;',
    '}',

    '.revenue-mix-legend-dot {',
    '  width: 8px;',
    '  height: 8px;',
    '  border-radius: 50%;',
    '  flex-shrink: 0;',
    '}',

    '.revenue-mix-legend-text {',
    '  font-family: Arial, sans-serif;',
    '  font-size: 11px;',
    '  color: #475569;',
    '  line-height: 1.2;',
    '}'
  ].join('\n');

  var style = document.createElement('style');
  style.id = 'revenue-mix-css';
  style.textContent = css;
  document.head.appendChild(style);
})();

// ---------------------------------------------------------------------------
// renderRevenueMixChart()
// Renders a horizontal stacked bar showing service/revenue line breakdown.
// Returns an HTML string.
// ---------------------------------------------------------------------------
function renderRevenueMixChart() {
  // 1. Resolve data source
  var splits = null;

  // Primary: DATA.customers.service_split
  if (typeof DATA !== 'undefined' && DATA.customers && Array.isArray(DATA.customers.service_split)) {
    splits = DATA.customers.service_split;
  }

  // Fallback: derive from DATA.customers.metrics latest year recurring_rev_share
  if (!splits && typeof DATA !== 'undefined' && DATA.customers && DATA.customers.metrics
      && typeof _kpi_latestYear === 'function') {
    var metrics = DATA.customers.metrics;
    var yr = _kpi_latestYear(metrics);
    if (yr && metrics[yr].recurring_rev_share != null) {
      var recurPct = (typeof _kpi_normPct === 'function') ? _kpi_normPct(metrics[yr].recurring_rev_share) : metrics[yr].recurring_rev_share;
      if (recurPct != null) {
        splits = [
          { label: 'Recurring', pct: Math.round(recurPct) },
          { label: 'Non-Recurring', pct: Math.round(100 - recurPct) }
        ];
      }
    }
  }

  // Last resort: mock data
  if (!splits || splits.length === 0) {
    splits = MOCK_SERVICE_SPLIT;
  }

  // 2. Normalise percentages to sum to 100
  var total = 0;
  for (var i = 0; i < splits.length; i++) {
    total += (splits[i].pct || 0);
  }
  if (total <= 0) total = 100;

  var segments = [];
  for (var j = 0; j < splits.length; j++) {
    var rawPct = splits[j].pct || 0;
    var normPct = (rawPct / total) * 100;
    segments.push({
      label: splits[j].label || 'Segment ' + (j + 1),
      pct: normPct,
      color: REVENUE_MIX_COLORS[j % REVENUE_MIX_COLORS.length]
    });
  }

  // 3. Build stacked bar HTML
  var barParts = [];
  var belowParts = [];
  var hasBelow = false;

  for (var s = 0; s < segments.length; s++) {
    var seg = segments[s];
    var widthStyle = 'width:' + seg.pct.toFixed(1) + '%;';
    var bgStyle = 'background:' + seg.color + ';';
    var pctDisplay = seg.pct.toLocaleString('de-DE', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }) + '%';

    if (seg.pct > 15) {
      // Label inside the segment
      barParts.push(
        '<div class="revenue-mix-segment" style="' + widthStyle + bgStyle + '" title="' + (typeof _slide_esc === 'function' ? _slide_esc(seg.label) : seg.label) + ': ' + pctDisplay + '">' +
          '<span class="revenue-mix-segment-label">' + pctDisplay + '</span>' +
        '</div>'
      );
      belowParts.push('<div class="revenue-mix-below-label" style="' + widthStyle + '"></div>');
    } else {
      // No label inside — render percentage below the bar
      hasBelow = true;
      barParts.push(
        '<div class="revenue-mix-segment" style="' + widthStyle + bgStyle + '" title="' + (typeof _slide_esc === 'function' ? _slide_esc(seg.label) : seg.label) + ': ' + pctDisplay + '"></div>'
      );
      belowParts.push(
        '<div class="revenue-mix-below-label" style="' + widthStyle + '">' + pctDisplay + '</div>'
      );
    }
  }

  var belowHtml = hasBelow
    ? '<div class="revenue-mix-below-labels">' + belowParts.join('') + '</div>'
    : '';

  // 4. Build legend
  var legendItems = [];
  for (var l = 0; l < segments.length; l++) {
    var item = segments[l];
    legendItems.push(
      '<div class="revenue-mix-legend-item">' +
        '<span class="revenue-mix-legend-dot" style="background:' + item.color + ';"></span>' +
        '<span class="revenue-mix-legend-text">' + item.label + '</span>' +
      '</div>'
    );
  }

  // 5. Assemble
  return (
    '<div class="revenue-mix-wrapper">' +
      '<div class="revenue-mix-title">Revenue Mix</div>' +
      '<div class="revenue-mix-bar">' + barParts.join('') + '</div>' +
      belowHtml +
      '<div class="revenue-mix-legend">' + legendItems.join('') + '</div>' +
    '</div>'
  );
}

// ---------------------------------------------------------------------------
// renderBusinessModelSlide()
// Assembles the full Business Model slide section using shared components.
// ---------------------------------------------------------------------------
function renderBusinessModelSlide() {
  var D = (typeof DATA !== 'undefined') ? DATA : {};

  var kpis = (typeof getKPIsBySection === 'function')
    ? getKPIsBySection(D, 'business_model')
    : [];

  // Mock KPI fallback for standalone preview
  if (!kpis.length) {
    kpis = [
      { label: 'Recurring Revenue', value: 45, formatted: '45,0 %', format: 'pct', bullet: 'Revenue quality — higher = more predictable' },
      { label: 'Backlog', value: 2.1, formatted: '2,1 M€', format: 'eur_m', bullet: 'Contracted future revenue' },
      { label: 'Avg. Order Value', value: 12, formatted: '12 K€', format: 'eur_k', bullet: 'Ticket size per transaction' },
      { label: 'Active Contracts', value: 38, formatted: '38', format: 'count', bullet: 'Number of running service agreements' }
    ];
  }

  var heroHtml = renderRevenueMixChart();
  var detailHtml = typeof renderBusinessModel === 'function'
    ? renderBusinessModel()
    : '<div class="slide-detail-placeholder" style="color:#94a3b8;font-size:13px;padding:20px;text-align:center;border:1px dashed #e2e8f0;border-radius:6px;">Business model detail renders here (renderBusinessModel)</div>';

  if (typeof renderSlideSection === 'function') {
    return renderSlideSection('business_model', 'Business Model', heroHtml, kpis, detailHtml);
  }

  // Fallback: inline assembly if DR-M24a not loaded
  var kpiCards = '';
  for (var i = 0; i < kpis.length && i < 4; i++) {
    var kpi = kpis[i];
    var fmtVal = kpi.formatted || String(kpi.value);
    kpiCards +=
      '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;">' +
        '<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">' + kpi.label + '</div>' +
        '<div style="font-size:22px;font-weight:700;color:#0f172a;font-variant-numeric:tabular-nums;">' + fmtVal + '</div>' +
        (kpi.bullet ? '<div style="font-size:11px;color:#475569;margin-top:4px;">' + kpi.bullet + '</div>' : '') +
      '</div>';
  }

  return (
    '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:24px;">' +
      '<div style="background:#0891B2;color:#fff;padding:10px 16px;font-size:16px;font-weight:700;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:space-between;">' +
        '<span>Business Model</span>' +
        '<button style="background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);color:#fff;padding:3px 10px;border-radius:3px;font-size:11px;cursor:pointer;">Export</button>' +
      '</div>' +
      '<div style="display:flex;min-height:200px;border-bottom:1px solid #e2e8f0;">' +
        '<div style="flex:0 0 55%;padding:16px;display:flex;align-items:center;justify-content:center;border-right:1px solid #e2e8f0;">' + heroHtml + '</div>' +
        '<div style="flex:0 0 45%;display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:16px;align-content:center;">' + kpiCards + '</div>' +
      '</div>' +
      '<div style="padding:20px;">' + detailHtml + '</div>' +
    '</div>'
  );
}
