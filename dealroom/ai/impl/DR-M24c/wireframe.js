/**
 * DR-M24c — Financials Slide Wireframe (Section 4: Valuation & Financials)
 *
 * Renders a slide section with:
 *   - Teal header bar with title + export button (from DR-M24a)
 *   - Hero row: grouped Revenue/EBITDA bar chart (left 55%)
 *                + 4 KPI powercards (right 45%) from DR-M24b
 *   - Detail area: P&L table via renderUnifiedGuV()
 *
 * Dependencies:
 *   - renderSlideSection()       from DR-M24a (slide-components.js)
 *   - getKPIsBySection()         from DR-M24b (kpi-registry.js)
 *   - formatKPI()                from DR-M24a
 *   - DATA global object         populated by dashboard loader
 *   - renderUnifiedGuV()         optional — existing P&L renderer
 *
 * No external libraries. String-concatenated HTML. No ES modules.
 */

// ---------------------------------------------------------------------------
// Mock data for standalone preview
// ---------------------------------------------------------------------------
var MOCK_FINANCIALS_CHART = {
  '2022': { revenue_k: 4200, ebitda_k: 520, margin_pct: 12.4, topline_growth_pct: null },
  '2023': { revenue_k: 4800, ebitda_k: 620, margin_pct: 12.9, topline_growth_pct: 14.3 },
  '2024': { revenue_k: 5400, ebitda_k: 740, margin_pct: 13.7, topline_growth_pct: 12.5 },
  '2025': { revenue_k: 5900, ebitda_k: 830, margin_pct: 14.1, topline_growth_pct: 9.3 }
};

// ---------------------------------------------------------------------------
// CSS injection for financials hero chart (IIFE — idempotent)
// ---------------------------------------------------------------------------
(function injectFinancialsCSS() {
  if (document.getElementById('financials-hero-css')) return;

  var css = [
    '.fin-hero-chart {',
    '  width: 100%;',
    '  font-family: Arial, sans-serif;',
    '}',

    '.fin-legend {',
    '  display: flex;',
    '  gap: 16px;',
    '  margin-bottom: 12px;',
    '  font-size: 11px;',
    '  color: #475569;',
    '}',

    '.fin-legend-item {',
    '  display: flex;',
    '  align-items: center;',
    '  gap: 5px;',
    '}',

    '.fin-legend-dot {',
    '  width: 10px;',
    '  height: 10px;',
    '  border-radius: 2px;',
    '  display: inline-block;',
    '}',

    '.fin-bar-area {',
    '  display: flex;',
    '  align-items: flex-end;',
    '  gap: 16px;',
    '  height: 180px;',
    '  padding-bottom: 0;',
    '}',

    '.fin-year-group {',
    '  flex: 1;',
    '  display: flex;',
    '  flex-direction: column;',
    '  align-items: center;',
    '  height: 100%;',
    '}',

    '.fin-bars {',
    '  display: flex;',
    '  align-items: flex-end;',
    '  gap: 4px;',
    '  flex: 1;',
    '  width: 100%;',
    '  justify-content: center;',
    '}',

    '.fin-bar-col {',
    '  display: flex;',
    '  flex-direction: column;',
    '  align-items: center;',
    '  width: 32px;',
    '  justify-content: flex-end;',
    '  height: 100%;',
    '}',

    '.fin-bar {',
    '  width: 28px;',
    '  border-radius: 3px 3px 0 0;',
    '  min-height: 2px;',
    '  transition: opacity 0.2s;',
    '}',

    '.fin-bar:hover {',
    '  opacity: 0.85;',
    '}',

    '.fin-bar-label {',
    '  font-size: 11px;',
    '  color: #334155;',
    '  font-weight: 600;',
    '  margin-bottom: 3px;',
    '  white-space: nowrap;',
    '  font-variant-numeric: tabular-nums;',
    '}',

    '.fin-year-label {',
    '  font-size: 12px;',
    '  color: #64748b;',
    '  font-weight: 600;',
    '  margin-top: 6px;',
    '  border-top: 1px solid #e2e8f0;',
    '  padding-top: 4px;',
    '  width: 100%;',
    '  text-align: center;',
    '}'
  ].join('\n');

  var style = document.createElement('style');
  style.id = 'financials-hero-css';
  style.textContent = css;
  document.head.appendChild(style);
})();

// ---------------------------------------------------------------------------
// renderFinancialsHero()
// Renders a grouped bar chart (Revenue + EBITDA) using pure CSS divs.
// Returns HTML string.
// ---------------------------------------------------------------------------
function renderFinancialsHero() {
  // Resolve data source: live DATA or mock fallback
  var yearly = null;
  if (typeof DATA !== 'undefined' && DATA.onepager_chart && DATA.onepager_chart.yearly) {
    yearly = DATA.onepager_chart.yearly;
  } else {
    yearly = MOCK_FINANCIALS_CHART;
  }

  // Extract year keys sorted ascending
  var years = Object.keys(yearly)
    .filter(function(k) { return /^\d{4}$/.test(k); })
    .sort();

  if (!years.length) {
    return '<div style="color:#94a3b8;font-size:13px;text-align:center;">No financial data available</div>';
  }

  // Determine max value for scaling (across both revenue and ebitda)
  var maxVal = 0;
  for (var i = 0; i < years.length; i++) {
    var yr = yearly[years[i]];
    if (yr.revenue_k > maxVal) maxVal = yr.revenue_k;
    if (yr.ebitda_k > maxVal) maxVal = yr.ebitda_k;
  }
  if (maxVal === 0) maxVal = 1; // prevent division by zero

  var MAX_BAR_HEIGHT = 160; // px

  // Format helper: K€ with German locale
  function fmtK(val) {
    return Math.round(val).toLocaleString('de-DE');
  }

  // Legend
  var legend =
    '<div class="fin-legend">' +
      '<div class="fin-legend-item">' +
        '<span class="fin-legend-dot" style="background:#67e8f9;"></span>' +
        '<span>Revenue</span>' +
      '</div>' +
      '<div class="fin-legend-item">' +
        '<span class="fin-legend-dot" style="background:#0891B2;"></span>' +
        '<span>EBITDA</span>' +
      '</div>' +
    '</div>';

  // Bar groups
  var groups = '';
  for (var j = 0; j < years.length; j++) {
    var year = years[j];
    var data = yearly[year];
    var revHeight = Math.round((data.revenue_k / maxVal) * MAX_BAR_HEIGHT);
    var ebitdaHeight = Math.round((data.ebitda_k / maxVal) * MAX_BAR_HEIGHT);

    // Enforce minimum visible height
    if (revHeight < 2) revHeight = 2;
    if (ebitdaHeight < 2) ebitdaHeight = 2;

    groups +=
      '<div class="fin-year-group">' +
        '<div class="fin-bars">' +
          // Revenue bar
          '<div class="fin-bar-col">' +
            '<div class="fin-bar-label">' + fmtK(data.revenue_k) + '</div>' +
            '<div class="fin-bar" style="height:' + revHeight + 'px;background:#67e8f9;"></div>' +
          '</div>' +
          // EBITDA bar
          '<div class="fin-bar-col">' +
            '<div class="fin-bar-label">' + fmtK(data.ebitda_k) + '</div>' +
            '<div class="fin-bar" style="height:' + ebitdaHeight + 'px;background:#0891B2;"></div>' +
          '</div>' +
        '</div>' +
        '<div class="fin-year-label">' + year + '</div>' +
      '</div>';
  }

  return (
    '<div class="fin-hero-chart">' +
      legend +
      '<div class="fin-bar-area">' +
        groups +
      '</div>' +
    '</div>'
  );
}

// ---------------------------------------------------------------------------
// renderFinancialsSlide()
// Assembles the full Valuation & Financials slide section.
// Returns HTML string.
// ---------------------------------------------------------------------------
function renderFinancialsSlide() {
  // Resolve DATA — use empty object for KPI computation if unavailable
  var D = (typeof DATA !== 'undefined') ? DATA : {};

  // Get KPIs from registry (DR-M24b)
  var kpis = (typeof getKPIsBySection === 'function')
    ? getKPIsBySection(D, 'financials')
    : [];

  // Hero chart
  var heroHtml = renderFinancialsHero();

  // Detail area: existing P&L table or placeholder
  var detailHtml = (typeof renderUnifiedGuV === 'function')
    ? renderUnifiedGuV()
    : '<div class="slide-detail-placeholder" style="color:#94a3b8;font-size:13px;padding:20px;text-align:center;border:1px dashed #e2e8f0;border-radius:6px;">' +
        '<!-- renderUnifiedGuV() renders the full P&L table here -->' +
        'P&L table renders here (renderUnifiedGuV)' +
      '</div>';

  // Assemble via shared slide component (DR-M24a)
  if (typeof renderSlideSection === 'function') {
    return renderSlideSection('financials', 'Valuation & Financials', heroHtml, kpis, detailHtml);
  }

  // Fallback: inline assembly if DR-M24a not loaded (standalone preview)
  var kpiCards = '';
  for (var i = 0; i < kpis.length && i < 4; i++) {
    var kpi = kpis[i];
    var fmtVal = kpi.formatted || (typeof formatKPI === 'function' ? formatKPI(kpi.value, kpi.format) : String(kpi.value));
    var bulletHtml = kpi.bullet
      ? '<div style="font-size:11px;color:#475569;margin-top:4px;">' + kpi.bullet + '</div>'
      : '';
    kpiCards +=
      '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;">' +
        '<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">' + kpi.label + '</div>' +
        '<div style="font-size:22px;font-weight:700;color:#0f172a;font-variant-numeric:tabular-nums;">' + fmtVal + '</div>' +
        bulletHtml +
      '</div>';
  }

  return (
    '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:24px;">' +
      '<div style="background:#0891B2;color:#fff;padding:10px 16px;font-size:16px;font-weight:700;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:space-between;">' +
        '<span>Valuation &amp; Financials</span>' +
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
