/**
 * DR-M24a — Slide Section Components
 * Shared CSS and component helpers for the dealroom dashboard's
 * "slide section" pattern. Each analytical section becomes exportable
 * as a 16:9 slide with a hero chart (left) and 4 KPI powercards (right).
 *
 * Exported globals:
 *   formatKPI(value, format)         — format a KPI value by type
 *   renderKPIPowercards(kpis)        — render 2x2 powercard grid HTML
 *   renderSlideSection(...)          — assemble full slide section HTML
 *   exportSlide(sectionId)           — trigger print-export for a section
 *
 * No external libraries. String-concatenated HTML. No ES modules.
 */

// ---------------------------------------------------------------------------
// 1. CSS Injection (IIFE — idempotent)
// ---------------------------------------------------------------------------
(function injectSlideCSS() {
  if (document.getElementById('slide-section-css')) return;

  var css = [
    /* --- Slide shell — wraps breadcrumb + slide, fills .content --- */
    '.section-slide-shell {',
    '  display: flex;',
    '  flex-direction: column;',
    '  height: calc(100vh - 85px);',
    '  margin: -20px -24px;',
    '  padding: 12px 24px 0;',
    '}',

    '.section-slide-shell .breadcrumb {',
    '  flex-shrink: 0;',
    '  margin-bottom: 8px;',
    '}',

    /* --- Slide section outer wrapper --- */
    '.slide-section {',
    '  background: #fff;',
    '  border: 1px solid #e2e8f0;',
    '  border-radius: 8px;',
    '  overflow: hidden;',
    '  display: flex;',
    '  flex-direction: column;',
    '  flex: 1;',
    '  min-height: 0;',
    '}',

    /* --- Teal header bar --- */
    '.slide-header {',
    '  background: #0891B2;',
    '  color: #fff;',
    '  padding: 10px 16px;',
    '  font-size: 16px;',
    '  font-weight: 700;',
    '  font-family: Arial, sans-serif;',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: space-between;',
    '  flex-shrink: 0;',
    '}',

    '.slide-header .slide-title {',
    '  flex: 1;',
    '}',

    '.slide-header .slide-export-btn {',
    '  background: rgba(255,255,255,0.2);',
    '  border: 1px solid rgba(255,255,255,0.4);',
    '  color: #fff;',
    '  padding: 3px 10px;',
    '  border-radius: 3px;',
    '  font-size: 11px;',
    '  cursor: pointer;',
    '}',

    '.slide-header .slide-export-btn:hover {',
    '  background: rgba(255,255,255,0.35);',
    '}',

    /* --- Hero row: chart-first grid, KPI rail bounded --- */
    '.slide-hero-row {',
    '  display: grid;',
    '  grid-template-columns: minmax(0, 1fr) clamp(300px, 32%, 400px);',
    '  min-height: 180px;',
    '  border-bottom: 1px solid #e2e8f0;',
    '  flex-shrink: 0;',
    '}',

    '.slide-hero-chart {',
    '  min-width: 0;',
    '  padding: 16px 20px;',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  border-right: 1px solid #e2e8f0;',
    '}',

    '.slide-kpi-grid {',
    '  min-width: 0;',
    '  display: grid;',
    '  grid-template-columns: repeat(2, minmax(0, 1fr));',
    '  gap: 10px;',
    '  padding: 16px;',
    '  align-content: center;',
    '}',

    /* 3-card variant: top row 2 cards, bottom row 1 card spanning full width */
    '.slide-kpi-grid.kpi-count-3 .slide-kpi-card:last-child {',
    '  grid-column: 1 / -1;',
    '}',

    /* --- Individual KPI powercard --- */
    '.slide-kpi-card {',
    '  background: #f8fafc;',
    '  border: 1px solid #e2e8f0;',
    '  border-radius: 6px;',
    '  padding: 12px;',
    '}',

    '.slide-kpi-label {',
    '  font-size: 11px;',
    '  color: #64748b;',
    '  text-transform: uppercase;',
    '  letter-spacing: 0.5px;',
    '  margin-bottom: 4px;',
    '  font-family: Arial, sans-serif;',
    '}',

    '.slide-kpi-value {',
    '  font-size: 22px;',
    '  font-weight: 700;',
    '  color: #0f172a;',
    '  font-family: Arial, sans-serif;',
    '  font-variant-numeric: tabular-nums;',
    '  line-height: 1.2;',
    '}',

    '.slide-kpi-bullet {',
    '  font-size: 11px;',
    '  color: #475569;',
    '  margin-top: 4px;',
    '  line-height: 1.3;',
    '  font-family: Arial, sans-serif;',
    '}',

    /* --- Detail area below hero row — fills remaining height, scrolls internally --- */
    '.slide-detail {',
    '  padding: 12px 16px 16px;',
    '  flex: 1;',
    '  overflow-y: auto;',
    '  min-height: 0;',
    '}',

    '.slide-detail .subtabs {',
    '  position: sticky;',
    '  top: -12px;',
    '  z-index: 2;',
    '  background: #fff;',
    '  padding-top: 12px;',
    '  margin-bottom: 10px;',
    '}',

    /* --- Export mode: constrain to 16:9 at 960x540 --- */
    '.slide-section.slide-export {',
    '  width: 960px;',
    '  height: 540px;',
    '  overflow: hidden;',
    '}',

    '.slide-section.slide-export .slide-detail {',
    '  display: none;',
    '}',

    '.slide-section.slide-export .slide-hero-row,',
    '.slide-section.exporting .slide-hero-row {',
    '  flex: 1;',
    '  min-height: 0;',
    '  max-height: none;',
    '}',

    /* --- Print media query for export — hide all chrome, show only the slide --- */
    '@media print {',
    '  body > *:not(.wrapper), .wrapper > *:not(.main), .main > *:not(.content) {',
    '    display: none !important;',
    '  }',
    '  .sidebar, .top-bar, .breadcrumb, .fin-tab-bar {',
    '    display: none !important;',
    '  }',
    '  .content {',
    '    margin: 0 !important; padding: 0 !important;',
    '    overflow: visible !important;',
    '  }',
    '  .section-slide-shell {',
    '    height: auto !important; margin: 0 !important; padding: 0 !important;',
    '  }',
    '  .slide-section.exporting .slide-detail {',
    '    display: none;',
    '  }',
    '  .slide-section.exporting {',
    '    width: 960px;',
    '    height: 540px;',
    '    page-break-inside: avoid;',
    '    border: none;',
    '    box-shadow: none;',
    '  }',
    '}'
  ].join('\n');

  var style = document.createElement('style');
  style.id = 'slide-section-css';
  style.textContent = css;
  document.head.appendChild(style);
})();

// ---------------------------------------------------------------------------
// 1b. _slide_esc(str) — escape HTML special chars to prevent XSS
// ---------------------------------------------------------------------------
function _slide_esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// 2. formatKPI(value, format)
//    Formats a KPI value based on its type. Returns a display string.
//    German locale (de-DE): dot thousands, comma decimals.
// ---------------------------------------------------------------------------
function formatKPI(value, format) {
  if (value === null || value === undefined) return '—'; // em dash

  switch (format) {
    case 'pct':
      return Number(value).toLocaleString('de-DE', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }) + '%';

    case 'mult':
      return Number(value).toLocaleString('de-DE', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }) + 'x';

    case 'eur_k':
      return Math.round(Number(value)).toLocaleString('de-DE') + ' K€';

    case 'eur_m':
      return Number(value).toLocaleString('de-DE', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }) + ' M€';

    case 'ratio':
      // Expects {sofort, eo} object
      if (typeof value === 'object' && value.sofort !== undefined && value.eo !== undefined) {
        return Math.round(Number(value.sofort)) + ' / ' + Math.round(Number(value.eo));
      }
      return String(value);

    case 'count':
      return Math.round(Number(value)).toLocaleString('de-DE');

    case 'score':
      return Number(value).toLocaleString('de-DE', {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1
      }) + ' / 10';

    default:
      return String(value);
  }
}

// ---------------------------------------------------------------------------
// 3. renderKPIPowercards(kpis)
//    Takes an array of KPI objects (max 4):
//      [{label, value, format, bullet}]
//    Returns HTML string for the 2x2 powercard grid.
// ---------------------------------------------------------------------------
function renderKPIPowercards(kpis) {
  if (!kpis || !kpis.length) return '';

  var cards = [];
  var limit = Math.min(kpis.length, 4);

  for (var i = 0; i < limit; i++) {
    var kpi = kpis[i];
    var formattedValue = formatKPI(kpi.value, kpi.format);
    var bulletHtml = kpi.bullet
      ? '<div class="slide-kpi-bullet">' + kpi.bullet + '</div>'
      : '';

    cards.push(
      '<div class="slide-kpi-card">' +
        '<div class="slide-kpi-label">' + (kpi.label || '') + '</div>' +
        '<div class="slide-kpi-value">' + formattedValue + '</div>' +
        bulletHtml +
      '</div>'
    );
  }

  return cards.join('\n');
}

// ---------------------------------------------------------------------------
// 4. renderSlideSection(sectionId, title, heroChartHtml, kpis, detailHtml)
//    Assembles the full slide section HTML.
// ---------------------------------------------------------------------------
function renderSlideSection(sectionId, title, heroChartHtml, kpis, detailHtml) {
  var kpiGridHtml = renderKPIPowercards(kpis);
  var kpiCount = kpis ? Math.min(kpis.length, 4) : 0;
  var kpiGridClass = 'slide-kpi-grid' + (kpiCount ? ' kpi-count-' + kpiCount : '');
  var detailBlock = detailHtml
    ? '<div class="slide-detail">' + detailHtml + '</div>'
    : '';

  return (
    '<div class="slide-section" data-section="' + sectionId + '">' +
      '<div class="slide-header">' +
        '<span class="slide-title">' + title + '</span>' +
        '<button class="slide-export-btn" onclick="exportSlide(\'' + sectionId + '\')">Export</button>' +
      '</div>' +
      '<div class="slide-hero-row">' +
        '<div class="slide-hero-chart">' + (heroChartHtml || '') + '</div>' +
        '<div class="' + kpiGridClass + '">' + kpiGridHtml + '</div>' +
      '</div>' +
      detailBlock +
    '</div>'
  );
}

// ---------------------------------------------------------------------------
// 5. exportSlide(sectionId)
//    Triggers print-export for a specific slide section.
//    Adds .slide-export class, prints, then removes the class.
// ---------------------------------------------------------------------------
function exportSlide(sectionId) {
  var section = document.querySelector('.slide-section[data-section="' + sectionId + '"]');
  if (!section) {
    console.warn('exportSlide: section "' + sectionId + '" not found');
    return;
  }

  section.classList.add('slide-export');
  section.classList.add('exporting');

  // Use requestAnimationFrame to ensure the class is applied before printing
  requestAnimationFrame(function () {
    window.print();

    // Clean up after print dialog closes
    // window.print() is synchronous in most browsers — it blocks until the
    // dialog is dismissed, so we can remove the classes immediately after.
    section.classList.remove('slide-export');
    section.classList.remove('exporting');
  });
}
