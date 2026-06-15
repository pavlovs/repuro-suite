/**
 * DR-M18 Wireframe — Bilanz & Bewertung Dashboard Sections
 * =========================================================
 *
 * INTEGRATION NOTES FOR DASHBOARD.HTML
 * ─────────────────────────────────────
 *
 * SIDEBAR (renderSidebar, ~line 1253):
 *   No new top-level sidebar items needed.
 *   - Bilanz is already a subtab under 'financials' (sub-bilanz)
 *   - Bewertung is also already a subtab under 'financials' (sub-bewertung)
 *   If Bewertung is promoted to its own top-level section in future:
 *     h += sidebarItem('bewertung', 'Bewertung', null);
 *
 * SWITCH CASE (showSection, ~line 1290):
 *   If Bewertung is promoted:
 *     case 'bewertung': area.innerHTML = bc + renderBewertungWireframe(); break;
 *
 * CURRENT INTEGRATION POINT:
 *   In renderInformation() (~line 1785), replace or supplement existing subtab bodies:
 *     h += '<div id="sub-bilanz" class="subcontent">' + renderBilanzWireframe() + '</div>';
 *     h += '<div id="sub-bewertung" class="subcontent">' + renderBewertungWireframe() + '</div>';
 *
 * MOCK DATA FLAG:
 *   Both functions check DATA.financials.balance / DATA.valuations first.
 *   If real data is absent, mock data is used and a "[mock data]" label is shown.
 *
 * CSS VARS USED:
 *   --accent: #4361ee
 *   --text-muted: #6c757d
 *   Teal headers: #0891B2
 *   fin-table class (existing)
 */

// ─────────────────────────────────────────────────────────────────────────────
// BILANZ WIREFRAME
// Target layout:
//   Subtabs: [Aktiva] [Passiva]
//   Financial table with 3 years, bold subtotals
//   Key Ratios strip below
// ─────────────────────────────────────────────────────────────────────────────

function renderBilanzWireframe() {
  // ── Helpers ──
  function _wfFmtK(v) {
    if (v == null) return '-';
    if (v < 0) return '(' + Math.abs(v).toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ')';
    return v.toLocaleString('de-DE', { maximumFractionDigits: 0 });
  }
  function _wfFmtM(v) {
    if (v == null) return '-';
    return (v / 1000).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' M€';
  }
  function _wfFmtPct(v) {
    if (v == null) return '-';
    return v.toFixed(0) + '%';
  }

  // Try real data first; fall back to mock
  const fin = (typeof DATA !== 'undefined' && DATA.financials) || {};
  const balance = fin.balance || null;
  const isMock = !balance || Object.keys(balance).filter(y => y !== 'unknown').length === 0;

  // Mock data structure — mirrors real schema: { year: { key: { value, source } } }
  const MOCK_BALANCE = {
    '2022': {
      anlagevermoegen:    { value: 890 },
      sachanlagen:        { value: 650 },
      immat_vermoegen:    { value: 240 },
      umlaufvermoegen:    { value: 1230 },
      vorrraete:          { value: 450 },
      forderungen:        { value: 680 },
      kasse:              { value: 100 },
      bilanzsumme:        { value: 2120 },
      eigenkapital:       { value: 678 },
      rueckstellungen:    { value: 210 },
      verbindlichkeiten_lt: { value: 680 },
      verbindlichkeiten_st: { value: 552 },
      bilanzsumme_passiva:  { value: 2120 },
    },
    '2023': {
      anlagevermoegen:    { value: 920 },
      sachanlagen:        { value: 670 },
      immat_vermoegen:    { value: 250 },
      umlaufvermoegen:    { value: 1180 },
      vorrraete:          { value: 480 },
      forderungen:        { value: 600 },
      kasse:              { value: 100 },
      bilanzsumme:        { value: 2100 },
      eigenkapital:       { value: 693 },
      rueckstellungen:    { value: 225 },
      verbindlichkeiten_lt: { value: 620 },
      verbindlichkeiten_st: { value: 562 },
      bilanzsumme_passiva:  { value: 2100 },
    },
    '2024': {
      anlagevermoegen:    { value: 1050 },
      sachanlagen:        { value: 780 },
      immat_vermoegen:    { value: 270 },
      umlaufvermoegen:    { value: 1340 },
      vorrraete:          { value: 520 },
      forderungen:        { value: 710 },
      kasse:              { value: 110 },
      bilanzsumme:        { value: 2390 },
      eigenkapital:       { value: 765 },
      rueckstellungen:    { value: 240 },
      verbindlichkeiten_lt: { value: 730 },
      verbindlichkeiten_st: { value: 655 },
      bilanzsumme_passiva:  { value: 2390 },
    },
  };

  const data = isMock ? MOCK_BALANCE : balance;
  const years = Object.keys(data).filter(y => y !== 'unknown').sort();
  const latestYear = years[years.length - 1];
  const lat = data[latestYear] || {};

  // ── Key ratio calculations (from latest year) ──
  const ekQuote = lat.eigenkapital && lat.bilanzsumme
    ? Math.round((lat.eigenkapital.value / lat.bilanzsumme.value) * 100)
    : null;
  const workingCapital = lat.umlaufvermoegen && lat.verbindlichkeiten_st
    ? lat.umlaufvermoegen.value - lat.verbindlichkeiten_st.value
    : null;
  const netDebt = lat.verbindlichkeiten_lt && lat.verbindlichkeiten_st && lat.kasse
    ? (lat.verbindlichkeiten_lt.value + lat.verbindlichkeiten_st.value) - lat.kasse.value
    : null;
  const currentRatio = lat.umlaufvermoegen && lat.verbindlichkeiten_st && lat.verbindlichkeiten_st.value > 0
    ? (lat.umlaufvermoegen.value / lat.verbindlichkeiten_st.value).toFixed(1)
    : null;

  // ── Aktiva rows ──
  const aktivaRows = [
    { label: 'Anlagevermögen (Fixed Assets)', key: 'anlagevermoegen', bold: true, indent: 0 },
    { label: 'Sachanlagen', key: 'sachanlagen', bold: false, indent: 1 },
    { label: 'Immat. Vermögen', key: 'immat_vermoegen', bold: false, indent: 1 },
    { type: 'spacer' },
    { label: 'Umlaufvermögen (Current Assets)', key: 'umlaufvermoegen', bold: true, indent: 0 },
    { label: 'Vorräte', key: 'vorrraete', bold: false, indent: 1 },
    { label: 'Forderungen', key: 'forderungen', bold: false, indent: 1 },
    { label: 'Kasse / Bank', key: 'kasse', bold: false, indent: 1 },
    { type: 'spacer' },
    { label: 'BILANZSUMME', key: 'bilanzsumme', bold: true, total: true, indent: 0 },
  ];

  // ── Passiva rows ──
  const passivaRows = [
    { label: 'Eigenkapital (Equity)', key: 'eigenkapital', bold: true, indent: 0 },
    { type: 'spacer' },
    { label: 'Rückstellungen (Provisions)', key: 'rueckstellungen', bold: false, indent: 0 },
    { type: 'spacer' },
    { label: 'Verbindlichkeiten langfristig', key: 'verbindlichkeiten_lt', bold: false, indent: 0 },
    { label: 'Verbindlichkeiten kurzfristig', key: 'verbindlichkeiten_st', bold: false, indent: 0 },
    { type: 'spacer' },
    { label: 'BILANZSUMME', key: 'bilanzsumme_passiva', bold: true, total: true, indent: 0 },
  ];

  function buildTable(rows) {
    let t = '<table class="fin-table" style="border-collapse:collapse;width:100%;max-width:640px">';
    t += '<thead><tr>';
    t += '<th style="background:#0891B2;color:#fff;padding:5px 8px;text-align:left;font-size:11px;min-width:260px">Position</th>';
    for (const yr of years) {
      t += '<th style="background:#0891B2;color:#fff;padding:5px 8px;text-align:right;font-size:11px;min-width:72px">' + yr + '</th>';
    }
    t += '</tr></thead><tbody>';

    for (const row of rows) {
      if (row.type === 'spacer') {
        t += '<tr><td colspan="' + (years.length + 1) + '" style="padding:2px;border:none"></td></tr>';
        continue;
      }
      const fw = row.bold ? 'font-weight:700;' : '';
      const bg = row.total ? 'background:#f0f4ff;' : '';
      const pl = row.indent ? 'padding-left:' + (8 + row.indent * 14) + 'px;' : 'padding-left:8px;';
      t += '<tr style="border-bottom:1px solid #e8e8e8;' + bg + '">';
      t += '<td style="' + pl + fw + 'font-size:12px;padding-top:4px;padding-bottom:4px">' + row.label + '</td>';
      for (const yr of years) {
        const cell = data[yr] && data[yr][row.key] ? data[yr][row.key] : null;
        t += '<td style="text-align:right;' + fw + 'font-size:12px;padding:4px 8px">'
          + (cell ? _wfFmtK(cell.value) : '-') + '</td>';
      }
      t += '</tr>';
    }
    t += '</tbody></table>';
    return t;
  }

  // ── Assemble ──
  let h = '';

  if (isMock) {
    h += '<div style="background:#fff8e1;border:1px solid #f0c040;border-radius:4px;padding:4px 10px;'
      + 'font-size:11px;color:#856404;margin-bottom:10px;display:inline-block">'
      + '&#9888; [mock data] — real balance data not yet extracted</div>';
  }

  // Subtabs: Aktiva / Passiva
  h += '<div class="subtabs" style="margin-bottom:12px">';
  h += '<button class="subtab active" onclick="showSubtab(this,\'wf-sub-aktiva\')">Aktiva</button>';
  h += '<button class="subtab" onclick="showSubtab(this,\'wf-sub-passiva\')">Passiva</button>';
  h += '</div>';

  // Aktiva tab
  h += '<div id="wf-sub-aktiva" class="subcontent active">';
  h += '<div style="font-size:11px;color:#0891B2;font-weight:700;margin-bottom:6px;letter-spacing:0.03em">AKTIVA (in K€)</div>';
  h += buildTable(aktivaRows);
  h += '</div>';

  // Passiva tab
  h += '<div id="wf-sub-passiva" class="subcontent">';
  h += '<div style="font-size:11px;color:#0891B2;font-weight:700;margin-bottom:6px;letter-spacing:0.03em">PASSIVA (in K€)</div>';
  h += buildTable(passivaRows);
  h += '</div>';

  // ── Key Ratios strip ──
  h += '<div style="margin-top:16px;padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;'
    + 'border-radius:6px;display:flex;gap:24px;flex-wrap:wrap;max-width:640px">';
  h += '<div style="font-size:11px;color:#0891B2;font-weight:700;width:100%;margin-bottom:4px">KEY RATIOS — ' + latestYear + '</div>';

  function ratioChip(label, val) {
    return '<div style="min-width:130px">'
      + '<div style="font-size:10px;color:#6c757d">' + label + '</div>'
      + '<div style="font-size:13px;font-weight:700;color:#1e293b">' + (val != null ? val : '—') + '</div>'
      + '</div>';
  }

  h += ratioChip('EK-Quote', ekQuote != null ? _wfFmtPct(ekQuote) : null);
  h += ratioChip('Working Capital', workingCapital != null ? _wfFmtK(workingCapital) + ' K' : null);
  h += ratioChip('Net Debt', netDebt != null ? _wfFmtK(netDebt) + ' K' : null);
  h += ratioChip('Current Ratio', currentRatio != null ? currentRatio + 'x' : null);
  h += '</div>';

  return h;
}


// ─────────────────────────────────────────────────────────────────────────────
// BEWERTUNG WIREFRAME
// Target layout:
//   1. EBITDA BASIS block
//   2. EV SCENARIOS table (3 scenarios, multiple / EV / structure)
//   3. DEAL STRUCTURE block
//   4. EV WATERFALL — horizontal bar
//   5. Source attribution
// ─────────────────────────────────────────────────────────────────────────────

function renderBewertungWireframe() {
  // ── Helpers ──
  function _wfFmtK(v) {
    if (v == null) return '-';
    if (v < 0) return '(' + Math.abs(v).toLocaleString('de-DE', { maximumFractionDigits: 0 }) + ')';
    return v.toLocaleString('de-DE', { maximumFractionDigits: 0 });
  }
  function _wfFmtM(v) {
    if (v == null) return '-';
    return (v / 1000).toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' M€';
  }

  // Try real model_context / valuations data first; fall back to mock
  const hasReal = typeof DATA !== 'undefined'
    && DATA.model_context
    && DATA.model_context.waterfall
    && DATA.model_context.waterfall.ev_total;

  const isMock = !hasReal;

  // Mock valuations data
  const MOCK = {
    ebitda_adj:      1200,   // K€
    ebitda_year:     '2025 (adj.)',
    adjustments: [
      { label: 'GF-Gehaltsbereinigung', value: 120 },
      { label: 'Einmalige Kosten', value: 0 },
    ],
    scenarios: [
      { name: 'Low',  multiple: 5.0, ev_k: 6000,  sofort_k: 4200, rb_k: 1800, rb_pct: 0 },
      { name: 'Mid',  multiple: 5.5, ev_k: 6600,  sofort_k: 4600, rb_k: 2000, rb_pct: 0 },
      { name: 'High', multiple: 6.0, ev_k: 7200,  sofort_k: 5000, rb_k: 2200, rb_pct: 0 },
    ],
    base_scenario: 1,  // index into scenarios (Mid)
    deal: {
      sofort_k:      4600,
      rueckbeteil_pct: 15,
      rueckbeteil_k: 690,
      earnout_max_k: 2000,
      earnout_trigger: 'EBITDA-Schwelle 1.150K',
    },
    source: '260505_Model_v7.xlsx',
    source_date: '05.05.2026',
  };

  const d = isMock ? MOCK : (() => {
    const ctx = DATA.model_context;
    const wf = ctx.waterfall || {};
    const p = ctx.params || {};
    return {
      ebitda_adj: ctx.ebitda_basis,
      ebitda_year: (ctx.years || []).slice(-1)[0] + ' (adj.)',
      adjustments: [],
      scenarios: [
        { name: 'Low',  multiple: (p.multiple || 5.5) - 0.5, ev_k: Math.round(ctx.ebitda_basis * ((p.multiple || 5.5) - 0.5)), sofort_k: wf.cash_at_closing, rb_k: 0 },
        { name: 'Mid',  multiple: p.multiple || 5.5,           ev_k: wf.ev_at_closing, sofort_k: wf.cash_at_closing, rb_k: wf.vendor_loan },
        { name: 'High', multiple: (p.multiple || 5.5) + 0.5, ev_k: Math.round(ctx.ebitda_basis * ((p.multiple || 5.5) + 0.5)), sofort_k: wf.cash_at_closing, rb_k: 0 },
      ],
      base_scenario: 1,
      deal: {
        sofort_k: wf.cash_at_closing,
        rueckbeteil_pct: wf.vendor_loan_pct,
        rueckbeteil_k: wf.vendor_loan,
        earnout_max_k: wf.earnout_max,
        earnout_trigger: 'per Modell',
      },
      source: null,
      source_date: null,
    };
  })();

  const TEAL_H = '#0891B2';
  const thStyle = 'background:' + TEAL_H + ';color:#fff;padding:5px 10px;font-size:11px;text-align:right;white-space:nowrap';
  const thStyleL = 'background:' + TEAL_H + ';color:#fff;padding:5px 10px;font-size:11px;text-align:left;white-space:nowrap';
  const tdStyle = 'padding:4px 10px;font-size:12px;text-align:right;border-bottom:1px solid #e8e8e8';
  const tdStyleL = 'padding:4px 10px;font-size:12px;text-align:left;border-bottom:1px solid #e8e8e8';
  const sectionHead = 'font-size:11px;color:' + TEAL_H + ';font-weight:700;letter-spacing:0.04em;margin:0 0 6px 0';

  let h = '<div style="max-width:680px">';

  if (isMock) {
    h += '<div style="background:#fff8e1;border:1px solid #f0c040;border-radius:4px;padding:4px 10px;'
      + 'font-size:11px;color:#856404;margin-bottom:12px;display:inline-block">'
      + '&#9888; [mock data] — run model extraction to populate real values</div>';
  }

  // ── 1. EBITDA BASIS ──────────────────────────────────────────────────────
  h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px;margin-bottom:14px">';
  h += '<p style="' + sectionHead + '">EBITDA BASIS</p>';
  h += '<div style="display:flex;gap:24px;flex-wrap:wrap">';
  h += '<div><div style="font-size:10px;color:#6c757d">Adj. EBITDA ' + d.ebitda_year + '</div>'
    + '<div style="font-size:16px;font-weight:700;color:#1e293b">' + _wfFmtK(d.ebitda_adj) + ' K</div></div>';

  if (d.adjustments && d.adjustments.length > 0) {
    const adjSum = d.adjustments.reduce((s, a) => s + (a.value || 0), 0);
    h += '<div><div style="font-size:10px;color:#6c757d">Adjustments</div>'
      + '<div style="font-size:13px;font-weight:600;color:#1e293b">'
      + (adjSum >= 0 ? '+' : '') + _wfFmtK(adjSum) + ' K</div>'
      + '<div style="font-size:10px;color:#6c757d">'
      + d.adjustments.filter(a => a.value).map(a => a.label + ' (' + (a.value > 0 ? '+' : '') + _wfFmtK(a.value) + ')').join(', ')
      + '</div></div>';
  }

  h += '</div></div>';

  // ── 2. EV SCENARIOS ──────────────────────────────────────────────────────
  h += '<p style="' + sectionHead + '">EV SCENARIOS</p>';
  h += '<table style="border-collapse:collapse;width:100%;margin-bottom:14px">';
  h += '<thead><tr>';
  h += '<th style="' + thStyleL + '">Szenario</th>';
  h += '<th style="' + thStyle + '">Multiple</th>';
  h += '<th style="' + thStyle + '">EV (M€)</th>';
  h += '<th style="' + thStyle + '">Sofort + Nachzahlung</th>';
  h += '</tr></thead><tbody>';

  for (let i = 0; i < d.scenarios.length; i++) {
    const sc = d.scenarios[i];
    const isBase = i === d.base_scenario;
    const bg = isBase ? 'background:#eef6ff;' : '';
    const fw = isBase ? 'font-weight:700;' : '';
    const tag = isBase ? ' <span style="font-size:9px;background:#4361ee;color:#fff;border-radius:3px;padding:1px 4px;vertical-align:middle">base</span>' : '';
    h += '<tr style="border-bottom:1px solid #e8e8e8;' + bg + '">';
    h += '<td style="' + tdStyleL + fw + '">' + sc.name + tag + '</td>';
    h += '<td style="' + tdStyle + fw + '">' + sc.multiple.toFixed(1) + 'x</td>';
    h += '<td style="' + tdStyle + fw + '">' + _wfFmtM(sc.ev_k * 1000) + '</td>';
    const struct = sc.sofort_k != null && sc.rb_k != null
      ? _wfFmtM(sc.sofort_k * 1000) + ' + ' + _wfFmtM(sc.rb_k * 1000)
      : '-';
    h += '<td style="' + tdStyle + fw + '">' + struct + '</td>';
    h += '</tr>';
  }

  h += '</tbody></table>';

  // ── 3. DEAL STRUCTURE ────────────────────────────────────────────────────
  h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px;margin-bottom:14px">';
  h += '<p style="' + sectionHead + '">DEAL STRUCTURE</p>';

  const dl = d.deal;
  function dealLine(label, val, sub) {
    return '<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #eee">'
      + '<div style="font-size:12px;color:#334155">' + label + '</div>'
      + '<div style="font-size:12px;font-weight:600;color:#1e293b">' + val
      + (sub ? '<span style="font-size:10px;color:#6c757d;margin-left:6px">' + sub + '</span>' : '')
      + '</div></div>';
  }

  h += dealLine('Sofortzahlung', dl.sofort_k != null ? _wfFmtM(dl.sofort_k * 1000) : '-');
  if (dl.rueckbeteil_pct != null) {
    h += dealLine('Rückbeteiligung',
      dl.rueckbeteil_pct + '%',
      dl.rueckbeteil_k != null ? '(' + _wfFmtK(dl.rueckbeteil_k) + ' K)' : '');
  }
  h += dealLine('Earn-Out max.',
    dl.earnout_max_k != null ? _wfFmtM(dl.earnout_max_k * 1000) : '-',
    dl.earnout_trigger || '');

  h += '</div>';

  // ── 4. EV WATERFALL (horizontal stacked bar) ─────────────────────────────
  h += '<p style="' + sectionHead + '">EV WATERFALL</p>';

  const base = d.scenarios[d.base_scenario] || d.scenarios[0];
  const totalK = base ? base.ev_k : null;
  const sofortK = dl.sofort_k || 0;
  const rbK = dl.rueckbeteil_k || 0;
  const eoK = dl.earnout_max_k || 0;
  const totalBar = sofortK + rbK + eoK;

  if (totalBar > 0) {
    const sofortPct = Math.round((sofortK / totalBar) * 100);
    const rbPct = Math.round((rbK / totalBar) * 100);
    const eoPct = 100 - sofortPct - rbPct;

    h += '<div style="margin-bottom:6px">';
    h += '<div style="display:flex;height:28px;border-radius:4px;overflow:hidden;border:1px solid #cbd5e1">';
    h += '<div style="width:' + sofortPct + '%;background:#4361ee;display:flex;align-items:center;'
      + 'justify-content:center;font-size:10px;color:#fff;font-weight:600;white-space:nowrap;overflow:hidden">'
      + 'Sofort ' + _wfFmtM(sofortK * 1000) + '</div>';
    if (rbPct > 0) {
      h += '<div style="width:' + rbPct + '%;background:#0891B2;display:flex;align-items:center;'
        + 'justify-content:center;font-size:10px;color:#fff;font-weight:600;white-space:nowrap;overflow:hidden">'
        + 'RB ' + _wfFmtM(rbK * 1000) + '</div>';
    }
    if (eoPct > 0) {
      h += '<div style="width:' + eoPct + '%;background:#7c3aed;display:flex;align-items:center;'
        + 'justify-content:center;font-size:10px;color:#fff;font-weight:600;white-space:nowrap;overflow:hidden">'
        + 'Earn-Out max. ' + _wfFmtM(eoK * 1000) + '</div>';
    }
    h += '</div>';

    // Legend
    h += '<div style="display:flex;gap:16px;margin-top:5px;flex-wrap:wrap">';
    function legendDot(color, label) {
      return '<div style="display:flex;align-items:center;gap:4px;font-size:10px;color:#6c757d">'
        + '<div style="width:10px;height:10px;border-radius:50%;background:' + color + '"></div>'
        + label + '</div>';
    }
    h += legendDot('#4361ee', 'Sofortzahlung');
    if (rbPct > 0) h += legendDot('#0891B2', 'Rückbeteiligung');
    if (eoPct > 0) h += legendDot('#7c3aed', 'Earn-Out (max.)');
    h += '<div style="margin-left:auto;font-size:10px;color:#6c757d">= ' + _wfFmtM(totalBar * 1000) + ' Total</div>';
    h += '</div>';
    h += '</div>';
  } else {
    h += '<div style="font-size:11px;color:#6c757d;padding:6px 0">No structure data available.</div>';
  }

  // ── 5. Source attribution ────────────────────────────────────────────────
  if (d.source) {
    h += '<div style="margin-top:12px;font-size:10px;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:6px">';
    h += 'Quelle: ' + d.source;
    if (d.source_date) h += ' (' + d.source_date + ')';
    h += '</div>';
  }

  h += '</div>'; // max-width wrapper
  return h;
}
