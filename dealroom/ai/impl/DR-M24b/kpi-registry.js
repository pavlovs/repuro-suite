/**
 * DR-M24b — KPI Registry & Decision Layer
 *
 * Defines all KPIs per analytical section, computes values from the global
 * DATA object, and provides getTopKPIs() for onepager bubble-up selection.
 *
 * Dependencies: DATA object (populated by dashboard loader before this runs).
 * All functions are global (window scope). No ES modules.
 */

// ---------------------------------------------------------------------------
// Utility: get sorted year keys from an object, most recent last
// ---------------------------------------------------------------------------
function _kpi_sortedYears(obj) {
  if (!obj || typeof obj !== 'object') return [];
  return Object.keys(obj)
    .filter(function(k) { return /^\d{4}$/.test(k); })
    .sort();
}

// ---------------------------------------------------------------------------
// Utility: get the latest year key from an object
// ---------------------------------------------------------------------------
function _kpi_latestYear(obj) {
  var yrs = _kpi_sortedYears(obj);
  return yrs.length ? yrs[yrs.length - 1] : null;
}

// ---------------------------------------------------------------------------
// Utility: normalise percentage — handles both 0-1 and 0-100 storage
// ---------------------------------------------------------------------------
function _kpi_normPct(v) {
  if (v == null || isNaN(v)) return null;
  return v <= 1 && v > -1 ? v * 100 : v;
}

// ---------------------------------------------------------------------------
// Utility: safe number — returns null for non-finite values
// ---------------------------------------------------------------------------
function _kpi_num(v) {
  if (v == null || !isFinite(v)) return null;
  return v;
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------
var KPI_FORMATTERS = {
  pct: function(v) {
    if (v == null) return '—';
    return v.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' %';
  },
  mult: function(v) {
    if (v == null) return '—';
    return v.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'x';
  },
  eur_k: function(v) {
    if (v == null) return '—';
    return v.toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ' K€';
  },
  eur_m: function(v) {
    if (v == null) return '—';
    return v.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' M€';
  },
  count: function(v) {
    if (v == null) return '—';
    return Math.round(v).toLocaleString('de-DE');
  },
  score: function(v) {
    if (v == null) return '—';
    return v.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' / 10';
  },
  ratio: function(v) {
    if (v == null || typeof v !== 'object') return '—';
    var s = (v.sofort != null ? v.sofort.toFixed(0) : '?');
    var e = (v.eo != null ? v.eo.toFixed(0) : '?');
    return s + ' / ' + e;
  }
};

function kpiFormat(format, value) {
  if (typeof formatKPI === 'function') return formatKPI(value, format);
  var fn = KPI_FORMATTERS[format];
  return fn ? fn(value) : String(value != null ? value : '—');
}

// ===========================================================================
// KPI REGISTRY — keyed by section
// ===========================================================================

var KPI_REGISTRY = {

  // ─── Section 4: Valuation & Financials ──────────────────────────────────
  financials: [
    {
      id: 'ebitda_margin',
      label: 'EBITDA Margin',
      importance: 9,
      format: 'pct',
      bullet: 'Profitability benchmark for medtech distribution',
      compute: function(D) {
        var yearly = D.onepager_chart && D.onepager_chart.yearly;
        if (!yearly) return null;
        var yr = _kpi_latestYear(yearly);
        if (!yr) return null;
        return _kpi_num(yearly[yr].margin_pct);
      }
    },
    {
      id: 'revenue_cagr',
      label: 'Revenue CAGR',
      importance: 8,
      format: 'pct',
      bullet: 'Organic growth trajectory',
      compute: function(D) {
        var yearly = D.onepager_chart && D.onepager_chart.yearly;
        if (!yearly) return null;
        var yrs = _kpi_sortedYears(yearly);
        if (yrs.length < 3) return null;
        var first = yearly[yrs[0]].revenue_k;
        var last  = yearly[yrs[yrs.length - 1]].revenue_k;
        if (!first || first <= 0 || !last || last <= 0) return null;
        var n = yrs.length - 1;
        return _kpi_num((Math.pow(last / first, 1 / n) - 1) * 100);
      }
    },
    {
      id: 'ev_ebitda_mult',
      label: 'EV / EBITDA',
      importance: 9,
      format: 'mult',
      bullet: 'Implied valuation at closing',
      compute: function(D) {
        var bridge = D.onepager_chart && D.onepager_chart.bridge;
        var yearly = D.onepager_chart && D.onepager_chart.yearly;
        if (!bridge || !yearly) return null;
        var ev = bridge.ev_at_closing;
        var yr = _kpi_latestYear(yearly);
        if (!yr) return null;
        var ebitda = yearly[yr].ebitda_k;
        if (!ev || !ebitda || ebitda === 0) return null;
        return _kpi_num(ev / ebitda);
      }
    },
    {
      id: 'adj_ebitda',
      label: 'Adj. EBITDA',
      importance: 7,
      format: 'eur_k',
      bullet: 'Earnings basis for valuation',
      compute: function(D) {
        var yearly = D.onepager_chart && D.onepager_chart.yearly;
        if (!yearly) return null;
        var yr = _kpi_latestYear(yearly);
        if (!yr) return null;
        return _kpi_num(yearly[yr].ebitda_k);
      }
    }
  ],

  // ─── Section 5: Offer & Negotiation ─────────────────────────────────────
  offer: [
    {
      id: 'current_ev',
      label: 'Current EV',
      importance: 8,
      format: 'eur_m',
      bullet: 'Enterprise value in current round',
      compute: function(D) {
        var bridge = D.onepager_chart && D.onepager_chart.bridge;
        if (!bridge || bridge.ev_at_closing == null) return null;
        return _kpi_num(bridge.ev_at_closing / 1000);
      }
    },
    {
      id: 'ev_delta',
      label: 'EV Delta',
      importance: 6,
      format: 'pct',
      bullet: 'Price movement between rounds',
      compute: function(D) {
        var hist = D.model_context && D.model_context.offer_history;
        if (!hist || !Array.isArray(hist) || hist.length < 2) return null;
        var prev = hist[hist.length - 2];
        var curr = hist[hist.length - 1];
        if (!prev.ev || prev.ev === 0 || !curr.ev) return null;
        return _kpi_num((curr.ev - prev.ev) / prev.ev * 100);
      }
    },
    {
      id: 'structure_split',
      label: 'Payment Split',
      importance: 7,
      format: 'ratio',
      bullet: 'Closing payment vs. deferred',
      compute: function(D) {
        var bridge = D.onepager_chart && D.onepager_chart.bridge;
        if (!bridge) return null;
        var sofort = bridge.sofortzahlung;
        var ev = bridge.ev_at_closing;
        if (sofort == null || !ev || ev === 0) return null;
        var sofortPct = (sofort / ev) * 100;
        return { sofort: sofortPct, eo: 100 - sofortPct };
      }
    },
    {
      id: 'implied_multiple',
      label: 'Implied Multiple',
      importance: 7,
      format: 'mult',
      bullet: 'Price-to-earnings at current offer',
      compute: function(D) {
        var bridge = D.onepager_chart && D.onepager_chart.bridge;
        var yearly = D.onepager_chart && D.onepager_chart.yearly;
        if (!bridge || !yearly) return null;
        var ev = bridge.ev_at_closing;
        var yr = _kpi_latestYear(yearly);
        if (!yr) return null;
        var ebitda = yearly[yr].ebitda_k;
        if (!ev || !ebitda || ebitda === 0) return null;
        return _kpi_num(ev / ebitda);
      }
    }
  ],

  // ─── Section 6: Business Model ──────────────────────────────────────────
  business_model: [
    {
      id: 'recurring_pct',
      label: 'Recurring Revenue',
      importance: 9,
      format: 'pct',
      bullet: 'Revenue quality — higher = more predictable',
      compute: function(D) {
        var metrics = D.customers && D.customers.metrics;
        if (!metrics) return null;
        var yr = _kpi_latestYear(metrics);
        if (!yr || metrics[yr].recurring_rev_share == null) return null;
        return _kpi_normPct(metrics[yr].recurring_rev_share);
      }
    },
    {
      id: 'backlog',
      label: 'Backlog',
      importance: 7,
      format: 'eur_m',
      bullet: 'Contracted future revenue',
      compute: function(D) {
        var comm = D.commercial;
        if (!comm) return null;
        // commercial may be an array of { category, metric, value } objects
        if (Array.isArray(comm)) {
          var total = 0;
          var found = false;
          for (var i = 0; i < comm.length; i++) {
            if (comm[i].metric === 'backlog_value_k' || comm[i].metric === 'backlog') {
              total += (comm[i].value || 0);
              found = true;
            }
          }
          return found ? _kpi_num(total / 1000) : null;
        }
        // or a keyed object
        if (comm.backlog_value_k != null) return _kpi_num(comm.backlog_value_k / 1000);
        if (comm.backlog != null) return _kpi_num(comm.backlog / 1000);
        return null;
      }
    },
    {
      id: 'avg_order_value',
      label: 'Avg. Order Value',
      importance: 5,
      format: 'eur_k',
      bullet: 'Ticket size per transaction',
      compute: function(D) {
        var comm = D.commercial;
        if (!comm) return null;
        if (Array.isArray(comm)) {
          for (var i = 0; i < comm.length; i++) {
            if (comm[i].metric === 'avg_order_value' || comm[i].metric === 'avg_order_value_k') {
              return _kpi_num(comm[i].value);
            }
          }
          return null;
        }
        if (comm.avg_order_value != null) return _kpi_num(comm.avg_order_value);
        if (comm.avg_order_value_k != null) return _kpi_num(comm.avg_order_value_k);
        return null;
      }
    },
    {
      id: 'active_contracts',
      label: 'Active Contracts',
      importance: 5,
      format: 'count',
      bullet: 'Number of running service agreements',
      compute: function(D) {
        var comm = D.commercial;
        if (!comm) return null;
        if (Array.isArray(comm)) {
          for (var i = 0; i < comm.length; i++) {
            if (comm[i].metric === 'active_contracts') {
              return _kpi_num(comm[i].value);
            }
          }
          return null;
        }
        return _kpi_num(comm.active_contracts);
      }
    }
  ],

  // ─── Section 7: Customers & Suppliers ───────────────────────────────────
  customers: [
    {
      id: 'top1_share',
      label: 'Top-1 Customer Share',
      importance: 8,
      format: 'pct',
      bullet: 'Single-customer dependency risk',
      compute: function(D) {
        var metrics = D.customers && D.customers.metrics;
        if (!metrics) return null;
        var yr = _kpi_latestYear(metrics);
        if (!yr || metrics[yr].top1_share == null) return null;
        return _kpi_normPct(metrics[yr].top1_share);
      }
    },
    {
      id: 'top3_share',
      label: 'Top-3 Customer Share',
      importance: 7,
      format: 'pct',
      bullet: 'Revenue concentration in top accounts',
      compute: function(D) {
        var customers = D.customers;
        if (!customers) return null;
        // Try top10 array first — sum the first 3 pct values
        var top10 = customers.top10;
        if (top10) {
          var yr = _kpi_latestYear(top10);
          if (yr && Array.isArray(top10[yr]) && top10[yr].length >= 3) {
            var sorted = top10[yr].slice().sort(function(a, b) { return a.rank - b.rank; });
            var sum = 0;
            for (var i = 0; i < 3 && i < sorted.length; i++) {
              sum += (sorted[i].pct || 0);
            }
            return _kpi_normPct(sum);
          }
        }
        return null;
      }
    },
    {
      id: 'total_customers',
      label: 'Total Customers',
      importance: 5,
      format: 'count',
      bullet: 'Breadth of customer base',
      compute: function(D) {
        var metrics = D.customers && D.customers.metrics;
        if (!metrics) return null;
        var yr = _kpi_latestYear(metrics);
        if (!yr) return null;
        var val = metrics[yr].total_customers != null ? metrics[yr].total_customers
                : metrics[yr].customer_count != null ? metrics[yr].customer_count
                : null;
        if (val == null) return null;
        return _kpi_num(val);
      }
    },
    {
      id: 'retention',
      label: 'Retention Rate',
      importance: 8,
      format: 'pct',
      bullet: 'Customer stickiness — churn inverse',
      compute: function(D) {
        var metrics = D.customers && D.customers.metrics;
        if (!metrics) return null;
        var yr = _kpi_latestYear(metrics);
        if (!yr) return null;
        var val = metrics[yr].retention_rate != null ? metrics[yr].retention_rate
                : metrics[yr].retention != null ? metrics[yr].retention
                : null;
        if (val == null) return null;
        return _kpi_normPct(val);
      }
    }
  ],

  // ─── Section 9: Thesis & Fit ────────────────────────────────────────────
  thesis: [
    {
      id: 'scorecard_overall',
      label: 'Scorecard Overall',
      importance: 9,
      format: 'score',
      bullet: 'Composite investment attractiveness',
      compute: function(D) {
        var items = D.scorecard && D.scorecard.items;
        if (!items || !Array.isArray(items) || items.length === 0) return null;
        var totalWeight = 0;
        var totalScore = 0;
        for (var i = 0; i < items.length; i++) {
          var w = items[i].weight != null ? items[i].weight : 1;
          var s = items[i].score;
          if (s == null) continue;
          totalWeight += w;
          totalScore += s * w;
        }
        if (totalWeight === 0) return null;
        return _kpi_num(totalScore / totalWeight);
      }
    },
    {
      id: 'green_count',
      label: 'Green Flags',
      importance: 6,
      format: 'count',
      bullet: 'Number of strong-performing criteria',
      compute: function(D) {
        var items = D.scorecard && D.scorecard.items;
        if (!items || !Array.isArray(items)) return null;
        var count = 0;
        for (var i = 0; i < items.length; i++) {
          if (items[i].rating === 'green') count++;
        }
        return count;
      }
    },
    {
      id: 'red_count',
      label: 'Red Flags',
      importance: 8,
      format: 'count',
      bullet: 'Material concerns requiring attention',
      compute: function(D) {
        var items = D.scorecard && D.scorecard.items;
        if (!items || !Array.isArray(items)) return null;
        var count = 0;
        for (var i = 0; i < items.length; i++) {
          if (items[i].rating === 'red') count++;
        }
        return count;
      }
    },
    {
      id: 'strategic_fit',
      label: 'Strategic Fit',
      importance: 9,
      format: 'score',
      bullet: 'Alignment with Repuro buy-and-build thesis',
      compute: function(D) {
        // Try direct deal field first
        if (D.deal && D.deal.strategic_fit_score != null) {
          return _kpi_num(D.deal.strategic_fit_score);
        }
        // Fallback: find in scorecard items
        var items = D.scorecard && D.scorecard.items;
        if (!items || !Array.isArray(items)) return null;
        for (var i = 0; i < items.length; i++) {
          var label = (items[i].label || items[i].criterion || '').toLowerCase();
          if (label.indexOf('strategic') !== -1 || label.indexOf('fit') !== -1) {
            return _kpi_num(items[i].score);
          }
        }
        return null;
      }
    }
  ]
};

// ===========================================================================
// getTopKPIs — bubble-up selection for onepager
// ===========================================================================

/**
 * Evaluate all KPIs, return the top N with section diversity.
 *
 * @param {Object} D    - The global DATA object
 * @param {number} [n]  - Number of KPIs to return (default 4)
 * @returns {Array<{id, label, section, value, formatted, format, bullet, importance}>}
 */
function getTopKPIs(D, n) {
  n = n || 4;
  if (!D) return [];

  // 1. Collect all KPIs where compute returns non-null
  var candidates = [];
  var sections = Object.keys(KPI_REGISTRY);
  for (var s = 0; s < sections.length; s++) {
    var section = sections[s];
    var kpis = KPI_REGISTRY[section];
    for (var k = 0; k < kpis.length; k++) {
      var kpi = kpis[k];
      var value = null;
      try {
        value = kpi.compute(D);
      } catch (e) {
        // compute failed — skip this KPI
        continue;
      }
      if (value == null) continue;
      candidates.push({
        id: kpi.id,
        label: kpi.label,
        section: section,
        value: value,
        formatted: kpiFormat(kpi.format, value),
        format: kpi.format,
        bullet: kpi.bullet,
        importance: kpi.importance
      });
    }
  }

  // 2. Sort by importance descending, then by section order for stability
  candidates.sort(function(a, b) {
    if (b.importance !== a.importance) return b.importance - a.importance;
    // Tie-break: prefer sections earlier in registry order
    var ai = sections.indexOf(a.section);
    var bi = sections.indexOf(b.section);
    return ai - bi;
  });

  // 3. Apply section diversity — prefer no two from the same section
  var result = [];
  var usedSections = {};

  // First pass: pick highest-importance from each unique section
  for (var i = 0; i < candidates.length && result.length < n; i++) {
    if (!usedSections[candidates[i].section]) {
      result.push(candidates[i]);
      usedSections[candidates[i].section] = true;
    }
  }

  // Second pass: if we still need more, fill from remaining by importance
  if (result.length < n) {
    var picked = {};
    for (var j = 0; j < result.length; j++) {
      picked[result[j].id] = true;
    }
    for (var m = 0; m < candidates.length && result.length < n; m++) {
      if (!picked[candidates[m].id]) {
        result.push(candidates[m]);
        picked[candidates[m].id] = true;
      }
    }
  }

  return result;
}

// ===========================================================================
// getKPIsBySection — retrieve all computed KPIs for a specific section
// ===========================================================================

/**
 * @param {Object} D        - The global DATA object
 * @param {string} section  - Section key (financials, offer, business_model, customers, thesis)
 * @returns {Array<{id, label, value, formatted, format, bullet, importance}>}
 */
function getKPIsBySection(D, section) {
  if (!D || !KPI_REGISTRY[section]) return [];
  var kpis = KPI_REGISTRY[section];
  var results = [];
  for (var i = 0; i < kpis.length; i++) {
    var kpi = kpis[i];
    var value = null;
    try {
      value = kpi.compute(D);
    } catch (e) {
      continue;
    }
    results.push({
      id: kpi.id,
      label: kpi.label,
      value: value,
      formatted: kpiFormat(kpi.format, value),
      format: kpi.format,
      bullet: kpi.bullet,
      importance: kpi.importance
    });
  }
  return results;
}
