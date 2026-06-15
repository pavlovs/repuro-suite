/**
 * DR-M24g — Offer & Negotiation Wireframe (Section 5)
 *
 * Hero chart: Offer Progression Timeline — horizontal timeline showing
 * each offer round as a node with EV amount, date, and directional arrows.
 *
 * Dependencies:
 *   - DR-M24a: renderSlideSection(), renderKPIPowercards(), formatKPI()
 *   - DR-M24b: getKPIsBySection(), KPI_REGISTRY.offer
 *   - DATA object populated by dashboard loader
 *
 * Exported globals:
 *   renderOfferTimeline()   — hero chart SVG/HTML
 *   renderOfferSlide()      — full slide section assembly
 */

// ---------------------------------------------------------------------------
// Mock data — used when DATA.model_context.offer_history is unavailable
// ---------------------------------------------------------------------------
var MOCK_OFFER_HISTORY = [
  { round: 1, date: '2026-01-15', ev: 3800, sofortzahlung: 2600, earn_out: 400 },
  { round: 2, date: '2026-03-20', ev: 4200, sofortzahlung: 2900, earn_out: 500 },
  { round: 3, date: '2026-04-28', ev: 4500, sofortzahlung: 3100, earn_out: 600 }
];

// ---------------------------------------------------------------------------
// CSS Injection (IIFE — idempotent)
// ---------------------------------------------------------------------------
(function injectOfferTimelineCSS() {
  if (document.getElementById('offer-timeline-css')) return;

  var css = [
    '.offer-timeline {',
    '  width: 100%;',
    '  display: flex;',
    '  flex-direction: column;',
    '  align-items: center;',
    '  padding: 8px 0;',
    '  font-family: Arial, sans-serif;',
    '}',

    '.offer-timeline-track {',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  width: 100%;',
    '  position: relative;',
    '}',

    '.offer-timeline-node {',
    '  display: flex;',
    '  flex-direction: column;',
    '  align-items: center;',
    '  position: relative;',
    '  min-width: 80px;',
    '}',

    '.offer-timeline-date {',
    '  font-size: 10px;',
    '  color: #64748b;',
    '  margin-bottom: 6px;',
    '  white-space: nowrap;',
    '}',

    '.offer-timeline-circle {',
    '  width: 36px;',
    '  height: 36px;',
    '  border-radius: 50%;',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  font-size: 13px;',
    '  font-weight: 700;',
    '  border: 2px solid #94a3b8;',
    '  background: #e2e8f0;',
    '  color: #475569;',
    '  position: relative;',
    '  z-index: 2;',
    '}',

    '.offer-timeline-circle.current {',
    '  width: 44px;',
    '  height: 44px;',
    '  font-size: 15px;',
    '  border-color: #0891B2;',
    '  background: #0891B2;',
    '  color: #fff;',
    '  box-shadow: 0 0 0 4px rgba(8, 145, 178, 0.15);',
    '}',

    '.offer-timeline-ev {',
    '  font-size: 12px;',
    '  font-weight: 700;',
    '  color: #0f172a;',
    '  margin-top: 6px;',
    '  white-space: nowrap;',
    '}',

    '.offer-timeline-ev.current {',
    '  color: #0891B2;',
    '  font-size: 14px;',
    '}',

    /* Connector between nodes */
    '.offer-timeline-connector {',
    '  display: flex;',
    '  align-items: center;',
    '  justify-content: center;',
    '  position: relative;',
    '  min-width: 48px;',
    '  flex: 1;',
    '  max-width: 80px;',
    '}',

    '.offer-timeline-line {',
    '  height: 2px;',
    '  background: #cbd5e1;',
    '  flex: 1;',
    '}',

    '.offer-timeline-arrow {',
    '  position: absolute;',
    '  top: 50%;',
    '  left: 50%;',
    '  transform: translate(-50%, -50%);',
    '  font-size: 16px;',
    '  font-weight: 700;',
    '  z-index: 1;',
    '}',

    '.offer-timeline-arrow.up {',
    '  color: #16a34a;',
    '}',

    '.offer-timeline-arrow.down {',
    '  color: #dc2626;',
    '}',

    '.offer-timeline-label {',
    '  font-size: 10px;',
    '  color: #94a3b8;',
    '  margin-top: 12px;',
    '  text-align: center;',
    '}'
  ].join('\n');

  var style = document.createElement('style');
  style.id = 'offer-timeline-css';
  style.textContent = css;
  document.head.appendChild(style);
})();


// ---------------------------------------------------------------------------
// Helper: format date string (YYYY-MM-DD) to German short format (DD.MM.YY)
// ---------------------------------------------------------------------------
function _offer_formatDate(dateStr) {
  if (!dateStr) return '';
  var parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  return parts[2] + '.' + parts[1] + '.' + parts[0].substring(2);
}

// ---------------------------------------------------------------------------
// Helper: format EV in T€ (German thousands format)
// ---------------------------------------------------------------------------
function _offer_formatEV(evK) {
  if (evK == null || isNaN(evK)) return '—';
  return Math.round(Number(evK)).toLocaleString('de-DE') + ' T€';
}

// ---------------------------------------------------------------------------
// Resolve offer history from DATA or fall back to mock
// ---------------------------------------------------------------------------
function _offer_getHistory() {
  if (typeof DATA !== 'undefined' &&
      DATA.model_context &&
      DATA.model_context.offer_history &&
      Array.isArray(DATA.model_context.offer_history) &&
      DATA.model_context.offer_history.length > 0) {
    return DATA.model_context.offer_history;
  }
  // Fallback: try to construct a single entry from bridge data
  if (typeof DATA !== 'undefined' &&
      DATA.onepager_chart &&
      DATA.onepager_chart.bridge &&
      DATA.onepager_chart.bridge.ev_at_closing != null) {
    var b = DATA.onepager_chart.bridge;
    return [{
      round: 1,
      date: '',
      ev: b.ev_at_closing,
      sofortzahlung: b.sofortzahlung || 0,
      earn_out: b.earn_out || 0
    }];
  }
  return MOCK_OFFER_HISTORY;
}

// ---------------------------------------------------------------------------
// renderOfferTimeline()
// Returns HTML string for the offer progression timeline hero chart.
// Displays up to 5 rounds, left-to-right, with directional arrows.
// ---------------------------------------------------------------------------
function renderOfferTimeline() {
  var history = _offer_getHistory();

  // Sort by date/round to ensure correct order
  history = history.slice().sort(function(a, b) {
    if (a.date && b.date) return a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
    return (a.round || 0) - (b.round || 0);
  });

  // Cap at 5 rounds — take the latest 5 if more
  if (history.length > 5) {
    history = history.slice(history.length - 5);
  }

  // Single-round case: just show the node, no connectors
  if (history.length === 0) {
    return '<div class="offer-timeline">' +
      '<div style="color:#94a3b8;font-size:12px;font-family:Arial,sans-serif;">' +
        'Keine Angebotsdaten verfügbar' +
      '</div>' +
    '</div>';
  }

  var parts = [];
  parts.push('<div class="offer-timeline">');
  parts.push('<div class="offer-timeline-track">');

  for (var i = 0; i < history.length; i++) {
    var entry = history[i];
    var isCurrent = (i === history.length - 1);
    var circleClass = 'offer-timeline-circle' + (isCurrent ? ' current' : '');
    var evClass = 'offer-timeline-ev' + (isCurrent ? ' current' : '');

    // Node
    parts.push('<div class="offer-timeline-node">');
    parts.push('  <div class="offer-timeline-date">' + _offer_formatDate(entry.date) + '</div>');
    parts.push('  <div class="' + circleClass + '">' + entry.round + '</div>');
    parts.push('  <div class="' + evClass + '">' + _offer_formatEV(entry.ev) + '</div>');
    parts.push('</div>');

    // Connector + arrow (not after the last node)
    if (i < history.length - 1) {
      var nextEV = history[i + 1].ev;
      var currEV = entry.ev;
      var arrowHtml = '';

      if (nextEV != null && currEV != null && currEV !== 0) {
        if (nextEV > currEV) {
          arrowHtml = '<div class="offer-timeline-arrow up">↑</div>';
        } else if (nextEV < currEV) {
          arrowHtml = '<div class="offer-timeline-arrow down">↓</div>';
        }
        // Equal = no arrow
      }

      parts.push('<div class="offer-timeline-connector">');
      parts.push('  <div class="offer-timeline-line"></div>');
      parts.push('  ' + arrowHtml);
      parts.push('</div>');
    }
  }

  parts.push('</div>'); // .offer-timeline-track

  // Bottom label
  var firstRound = history[0];
  var lastRound = history[history.length - 1];
  if (history.length > 1 && firstRound.ev && lastRound.ev && firstRound.ev !== 0) {
    var totalDelta = ((lastRound.ev - firstRound.ev) / firstRound.ev * 100);
    var sign = totalDelta >= 0 ? '+' : '';
    var deltaStr = sign + totalDelta.toLocaleString('de-DE', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    }) + '%';
    var deltaColor = totalDelta >= 0 ? '#16a34a' : '#dc2626';
    parts.push(
      '<div class="offer-timeline-label">' +
        'Gesamt: <span style="color:' + deltaColor + ';font-weight:700;">' + deltaStr + '</span>' +
        ' ü' + 'ber ' + history.length + ' Runden' +
      '</div>'
    );
  }

  parts.push('</div>'); // .offer-timeline
  return parts.join('\n');
}

// ---------------------------------------------------------------------------
// renderOfferSlide()
// Assembles the full Section 5 slide using shared components from DR-M24a/b.
// Returns HTML string ready for DOM insertion.
// ---------------------------------------------------------------------------
function renderOfferSlide() {
  // 1. Hero chart
  var heroHtml = renderOfferTimeline();

  // 2. KPIs from registry
  var kpis = [];
  if (typeof getKPIsBySection === 'function' && typeof DATA !== 'undefined') {
    kpis = getKPIsBySection(DATA, 'offer');
  }

  // Fallback: build KPIs from mock data if registry returned nothing useful
  if (!kpis.length || kpis.every(function(k) { return k.value == null; })) {
    var history = _offer_getHistory();
    var latest = history[history.length - 1];
    var prev = history.length >= 2 ? history[history.length - 2] : null;

    var evDelta = null;
    if (prev && prev.ev && prev.ev !== 0 && latest.ev != null) {
      evDelta = ((latest.ev - prev.ev) / prev.ev * 100);
    }

    var splitSofort = null;
    var totalEV = latest.ev || 0;
    if (totalEV > 0 && latest.sofortzahlung != null) {
      var sofortPct = (latest.sofortzahlung / totalEV) * 100;
      splitSofort = { sofort: sofortPct, eo: 100 - sofortPct };
    }

    kpis = [
      {
        label: 'Current EV',
        value: latest.ev != null ? latest.ev / 1000 : null,
        format: 'eur_m',
        bullet: 'Enterprise value in current round'
      },
      {
        label: 'EV Delta',
        value: evDelta,
        format: 'pct',
        bullet: 'Price movement between rounds'
      },
      {
        label: 'Payment Split',
        value: splitSofort,
        format: 'ratio',
        bullet: 'Closing payment vs. deferred'
      },
      {
        label: 'Implied Multiple',
        value: null,
        format: 'mult',
        bullet: 'Price-to-earnings at current offer'
      }
    ];
  }

  // 3. Detail area — placeholder for existing offer section content
  var detailHtml =
    '<div style="color:#94a3b8;font-size:12px;font-family:Arial,sans-serif;' +
    'text-align:center;padding:24px;">' +
      'Offer round ledger &amp; negotiation points rendered here' +
    '</div>';

  // 4. Assemble via shared component
  if (typeof renderSlideSection === 'function') {
    return renderSlideSection('offer', 'Offer & Negotiation', heroHtml, kpis, detailHtml);
  }

  // Inline fallback if DR-M24a is not loaded (defensive)
  var kpiCards = '';
  if (typeof renderKPIPowercards === 'function') {
    kpiCards = renderKPIPowercards(kpis);
  }

  return (
    '<div class="slide-section" data-section="offer">' +
      '<div class="slide-header">' +
        '<span class="slide-title">Offer &amp; Negotiation</span>' +
        '<button class="slide-export-btn" onclick="exportSlide(\'offer\')">Export</button>' +
      '</div>' +
      '<div class="slide-hero-row">' +
        '<div class="slide-hero-chart">' + heroHtml + '</div>' +
        '<div class="slide-kpi-grid">' + kpiCards + '</div>' +
      '</div>' +
      '<div class="slide-detail">' + detailHtml + '</div>' +
    '</div>'
  );
}
