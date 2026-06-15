/**
 * DR-M24f — Thesis & Fit (Section 9) Wireframe
 *
 * Hero chart: Scorecard Summary — horizontal traffic-light bar chart.
 * KPIs: Overall Score, Green Signals, Red Flags, Strategic Fit.
 * Detail: placeholder for existing renderThesis() output.
 *
 * Dependencies:
 *   DR-M24a  renderSlideSection(), formatKPI()
 *   DR-M24b  getKPIsBySection(), KPI_REGISTRY
 *   DATA     global deal data object
 *
 * No external libraries. String-concatenated HTML. No ES modules.
 */

// ---------------------------------------------------------------------------
// Mock data — used when DATA.scorecard.items is unavailable
// ---------------------------------------------------------------------------
var MOCK_SCORECARD = [
  { criterion: 'Revenue CAGR', score: 7.5, rating: 'green', weight: 1 },
  { criterion: 'EBITDA Margin', score: 6.0, rating: 'yellow', weight: 1 },
  { criterion: 'Recurring Revenue', score: 5.5, rating: 'yellow', weight: 1 },
  { criterion: 'Customer Concentration', score: 4.0, rating: 'red', weight: 1 },
  { criterion: 'Owner Dependency', score: 3.5, rating: 'red', weight: 1 },
  { criterion: 'Market Position', score: 7.0, rating: 'green', weight: 1 },
  { criterion: 'Growth Potential', score: 8.0, rating: 'green', weight: 1 },
  { criterion: 'Asset Quality', score: 6.5, rating: 'yellow', weight: 1 },
  { criterion: 'Management Team', score: 5.0, rating: 'yellow', weight: 1 },
  { criterion: 'Strategic Fit', score: 8.5, rating: 'green', weight: 1.5 },
  { criterion: 'Integration Risk', score: 6.0, rating: 'yellow', weight: 1 }
];

// ---------------------------------------------------------------------------
// CSS injection for scorecard-specific styles (idempotent)
// ---------------------------------------------------------------------------
(function injectScorecardCSS() {
  if (document.getElementById('scorecard-summary-css')) return;

  var css = [
    '.scorecard-summary {',
    '  width: 100%;',
    '  font-family: Arial, sans-serif;',
    '}',

    '.scorecard-row {',
    '  display: flex;',
    '  align-items: center;',
    '  margin-bottom: 6px;',
    '}',

    '.scorecard-label {',
    '  flex: 0 0 160px;',
    '  font-size: 12px;',
    '  color: #334155;',
    '  text-align: right;',
    '  padding-right: 12px;',
    '  white-space: nowrap;',
    '  overflow: hidden;',
    '  text-overflow: ellipsis;',
    '}',

    '.scorecard-bar-track {',
    '  flex: 1;',
    '  height: 16px;',
    '  background: #f1f5f9;',
    '  border-radius: 3px;',
    '  overflow: hidden;',
    '}',

    '.scorecard-bar-fill {',
    '  height: 100%;',
    '  border-radius: 3px;',
    '  transition: width 0.3s ease;',
    '}',

    '.scorecard-bar-fill.rating-green  { background: #10b981; }',
    '.scorecard-bar-fill.rating-yellow { background: #f59e0b; }',
    '.scorecard-bar-fill.rating-red    { background: #ef4444; }',
    '.scorecard-bar-fill.rating-open   { background: #e2e8f0; }',

    '.scorecard-score {',
    '  flex: 0 0 48px;',
    '  font-size: 12px;',
    '  font-weight: 600;',
    '  color: #0f172a;',
    '  text-align: right;',
    '  padding-left: 8px;',
    '  font-variant-numeric: tabular-nums;',
    '}'
  ].join('\n');

  var style = document.createElement('style');
  style.id = 'scorecard-summary-css';
  style.textContent = css;
  document.head.appendChild(style);
})();

// ---------------------------------------------------------------------------
// renderScorecardSummary()
// Renders a compact horizontal traffic-light bar chart from scorecard items.
// Each metric gets one row: label | colored bar proportional to score | value.
// ---------------------------------------------------------------------------
function renderScorecardSummary() {
  // Resolve scorecard items: DATA.scorecard.items > DATA.deal.scorecard_config > mock
  var items = null;
  if (typeof DATA !== 'undefined') {
    if (DATA.scorecard && Array.isArray(DATA.scorecard.items) && DATA.scorecard.items.length > 0) {
      items = DATA.scorecard.items;
    } else if (DATA.deal && Array.isArray(DATA.deal.scorecard_config) && DATA.deal.scorecard_config.length > 0) {
      items = DATA.deal.scorecard_config;
    }
  }
  if (!items) {
    items = MOCK_SCORECARD;
  }

  var maxScore = 10; // scorecard is out of 10
  var rows = [];

  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var label = item.criterion || item.label || ('Metric ' + (i + 1));
    var score = (item.score != null && isFinite(item.score)) ? item.score : 0;
    var rating = item.rating || 'open';
    var widthPct = Math.min(Math.max((score / maxScore) * 100, 0), 100);

    // Normalise rating to one of the known classes
    var ratingClass = 'rating-open';
    if (rating === 'green') ratingClass = 'rating-green';
    else if (rating === 'yellow' || rating === 'amber') ratingClass = 'rating-yellow';
    else if (rating === 'red') ratingClass = 'rating-red';

    var scoreDisplay = score.toLocaleString('de-DE', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    });

    rows.push(
      '<div class="scorecard-row">' +
        '<div class="scorecard-label" title="' + (typeof _slide_esc === 'function' ? _slide_esc(label) : label) + '">' + (typeof _slide_esc === 'function' ? _slide_esc(label) : label) + '</div>' +
        '<div class="scorecard-bar-track">' +
          '<div class="scorecard-bar-fill ' + ratingClass + '" style="width:' + widthPct.toFixed(1) + '%"></div>' +
        '</div>' +
        '<div class="scorecard-score">' + scoreDisplay + '</div>' +
      '</div>'
    );
  }

  return '<div class="scorecard-summary">' + rows.join('') + '</div>';
}

// ---------------------------------------------------------------------------
// renderThesisSlide()
// Assembles the full Section 9 slide using the shared slide-section pattern.
// ---------------------------------------------------------------------------
function renderThesisSlide() {
  // 1. Hero chart
  var heroHtml = renderScorecardSummary();

  // 2. KPIs from registry
  var kpis = [];
  if (typeof DATA !== 'undefined' && typeof getKPIsBySection === 'function') {
    var computed = getKPIsBySection(DATA, 'thesis');
    for (var i = 0; i < computed.length && kpis.length < 4; i++) {
      kpis.push({
        label: computed[i].label,
        value: computed[i].value,
        format: computed[i].format,
        bullet: computed[i].bullet
      });
    }
  }

  // Fallback: compute KPIs from mock if DATA unavailable
  if (kpis.length === 0) {
    var mockItems = MOCK_SCORECARD;
    // Overall Score — weighted average
    var totalWeight = 0;
    var totalScore = 0;
    var greenCount = 0;
    var redCount = 0;
    var fitScore = null;

    for (var j = 0; j < mockItems.length; j++) {
      var w = mockItems[j].weight != null ? mockItems[j].weight : 1;
      totalWeight += w;
      totalScore += (mockItems[j].score || 0) * w;
      if (mockItems[j].rating === 'green') greenCount++;
      if (mockItems[j].rating === 'red') redCount++;
      var crit = (mockItems[j].criterion || '').toLowerCase();
      if (crit.indexOf('strategic') !== -1 || crit.indexOf('fit') !== -1) {
        fitScore = mockItems[j].score;
      }
    }

    var overallScore = totalWeight > 0 ? totalScore / totalWeight : null;

    kpis = [
      { label: 'Scorecard Overall', value: overallScore, format: 'score', bullet: 'Composite investment attractiveness' },
      { label: 'Green Signals', value: greenCount, format: 'count', bullet: 'Number of strong-performing criteria' },
      { label: 'Red Flags', value: redCount, format: 'count', bullet: 'Material concerns requiring attention' },
      { label: 'Strategic Fit', value: fitScore, format: 'score', bullet: 'Alignment with Repuro buy-and-build thesis' }
    ];
  }

  // 3. Detail area — delegate to existing renderThesis() if available
  var detailHtml = '';
  if (typeof renderThesis === 'function') {
    try {
      detailHtml = renderThesis();
    } catch (e) {
      detailHtml = '<p style="color:#94a3b8;font-family:Arial,sans-serif;font-size:13px;">' +
        'Thesis detail unavailable — renderThesis() error: ' + e.message + '</p>';
    }
  } else {
    detailHtml = '<p style="color:#94a3b8;font-family:Arial,sans-serif;font-size:13px;">' +
      'Detail area: SWOT matrix, full scorecard table, and strategic rationale will render here.</p>';
  }

  // 4. Assemble via shared slide-section component
  if (typeof renderSlideSection === 'function') {
    return renderSlideSection('thesis', 'Investment Thesis & Strategic Fit', heroHtml, kpis, detailHtml);
  }

  // Fallback: inline assembly if DR-M24a not loaded
  var kpiCardsHtml = '';
  for (var k = 0; k < kpis.length && k < 4; k++) {
    var fmtVal = (typeof formatKPI === 'function')
      ? formatKPI(kpis[k].value, kpis[k].format)
      : String(kpis[k].value != null ? kpis[k].value : '—');
    var bulletHtml = kpis[k].bullet
      ? '<div style="font-size:11px;color:#475569;margin-top:4px;">' + kpis[k].bullet + '</div>'
      : '';
    kpiCardsHtml +=
      '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px;">' +
        '<div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">' + kpis[k].label + '</div>' +
        '<div style="font-size:22px;font-weight:700;color:#0f172a;font-variant-numeric:tabular-nums;">' + fmtVal + '</div>' +
        bulletHtml +
      '</div>';
  }

  return (
    '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;margin-bottom:24px;">' +
      '<div style="background:#0891B2;color:#fff;padding:10px 16px;font-size:16px;font-weight:700;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:space-between;">' +
        '<span>Investment Thesis &amp; Strategic Fit</span>' +
        '<button style="background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.4);color:#fff;padding:3px 10px;border-radius:3px;font-size:11px;cursor:pointer;" onclick="exportSlide(\'thesis\')">Export</button>' +
      '</div>' +
      '<div style="display:flex;min-height:200px;border-bottom:1px solid #e2e8f0;">' +
        '<div style="flex:0 0 55%;padding:16px;display:flex;align-items:center;justify-content:center;border-right:1px solid #e2e8f0;">' + heroHtml + '</div>' +
        '<div style="flex:0 0 45%;display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:16px;align-content:center;">' + kpiCardsHtml + '</div>' +
      '</div>' +
      '<div style="padding:20px;">' + detailHtml + '</div>' +
    '</div>'
  );
}
