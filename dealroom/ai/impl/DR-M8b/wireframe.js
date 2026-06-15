/**
 * DR-M8b — Offer & Negotiation Section Wireframe
 *
 * Drop-in replacement for renderOfferStub() in dashboard.html.
 * Function name: renderOfferNegotiation()
 *
 * Integration:
 *   1. Add to showSection() switch: case 'offer': area.innerHTML=bc+renderOfferNegotiation(); break;
 *   2. DATA shape expected: DATA.deal, DATA.valuations (offer rounds array)
 *
 * ALL DATA IS MOCK — labelled clearly. Replace with real DATA bindings in DR-M8b implementation.
 */

function renderOfferNegotiation() {
  const TEAL = '#0891B2';
  const TEAL_BG = '#e0f5fa';
  const TEAL_BORDER = '#b0dff0';

  // ── Style helpers ────────────────────────────────────────────────────────────
  const thStyle = 'background:' + TEAL + ';color:#fff;padding:5px 10px;font-size:11px;'
    + 'font-weight:700;text-align:right;white-space:nowrap;font-family:Arial,sans-serif';
  const thStyleL = thStyle + ';text-align:left';
  const tdR = 'padding:5px 10px;font-size:12px;text-align:right;font-family:Arial,sans-serif;'
    + 'border-bottom:1px solid #e9ecef';
  const tdL = 'padding:5px 10px;font-size:12px;text-align:left;font-family:Arial,sans-serif;'
    + 'border-bottom:1px solid #e9ecef';

  // ── Mock data ─────────────────────────────────────────────────────────────────
  // In production: derive from DATA.deal, DATA.valuations, DATA.deal.negotiations
  const mock = {
    current_ev_m:    6.6,
    scenario:        'Mid',
    seller_ask_m:    7.5,
    gap_m:           0.9,
    gap_pct:         12,
    status:          'NBO sent',
    status_date:     '14.05.2026',
    open_issues:     3,

    rounds: [
      { rnd: 1, date: '03.04.26', ev:  5800, sofort: 4000, rb_pct: 15, eo:  900, multiple: 4.8, status: 'Sent' },
      { rnd: 2, date: '18.04.26', ev:  6200, sofort: 4300, rb_pct: 15, eo: 1000, multiple: 5.2, status: 'Countered' },
      { rnd: 3, date: '02.05.26', ev:  6600, sofort: 4600, rb_pct: 15, eo: 1100, multiple: 5.5, status: 'Sent' },
    ],

    issues: [
      { n: 1, label: 'GF salary adj.',     buyer: '120K',    seller: '150K',    status: 'Open',     prio: 'High' },
      { n: 2, label: 'Earn-out trigger',   buyer: 'EBITDA',  seller: 'Revenue', status: 'Open',     prio: 'High' },
      { n: 3, label: 'Exclusivity period', buyer: '8 weeks', seller: '4 weeks', status: 'Resolved', prio: 'Med'  },
      { n: 4, label: 'Net debt cutoff',    buyer: 'Closing', seller: 'Signing', status: 'Open',     prio: 'Med'  },
      { n: 5, label: 'Non-compete scope',  buyer: '3yr/50km',seller: '2yr/30km',status: 'Open',     prio: 'Low'  },
    ],

    counter_notes: [
      { date: '02.05.26', text: 'Seller indicated flexibility on earn-out trigger (EBITDA vs. Revenue); firm on GF salary at 150K.' },
      { date: '18.04.26', text: 'Initial counter at 7,5M€ EV. Seller wants revenue-based earn-out metric. Exclusivity period under discussion.' },
    ],
  };

  // ── German number format helpers ─────────────────────────────────────────────
  function fmtK(v)    { return v == null ? '-' : v.toLocaleString('de-DE', { maximumFractionDigits: 0 }); }
  function fmtM(v)    { return v == null ? '-' : v.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'M€'; }
  function fmtPct(v)  { return v == null ? '-' : v.toFixed(0) + '%'; }
  function fmtMult(v) { return v == null ? '-' : v.toFixed(1) + 'x'; }

  // ── Badge renderers ───────────────────────────────────────────────────────────
  function statusBadge(s) {
    const map = {
      'Sent':      'background:#dbeafe;color:#1d4ed8',
      'Countered': 'background:#fef3c7;color:#92400e',
      'Resolved':  'background:#d1fae5;color:#065f46',
      'Open':      'background:#dbeafe;color:#1d4ed8',
      'Withdrawn': 'background:#f3f4f6;color:#6b7280',
    };
    const style = map[s] || 'background:#f3f4f6;color:#6b7280';
    return '<span style="' + style + ';padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;">' + s + '</span>';
  }

  function prioBadge(p) {
    const map = {
      'High': 'background:#fee2e2;color:#b91c1c',
      'Med':  'background:#fef3c7;color:#92400e',
      'Low':  'background:#f3f4f6;color:#6b7280',
    };
    const style = map[p] || 'background:#f3f4f6;color:#6b7280';
    return '<span style="' + style + ';padding:1px 7px;border-radius:10px;font-size:10px;font-weight:700;">' + p + '</span>';
  }

  // ─────────────────────────────────────────────────────────────────────────────
  let h = '';

  // Wireframe banner
  h += '<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:4px;padding:6px 12px;'
    + 'margin-bottom:16px;font-size:11px;color:#92400e;font-weight:600;">'
    + '[Wireframe — mock data] DR-M8b / Offer &amp; Negotiation — replace stub with this function'
    + '</div>';

  // ── Section header ────────────────────────────────────────────────────────────
  h += '<div style="font-size:13px;font-weight:700;color:' + TEAL + ';text-transform:uppercase;'
    + 'letter-spacing:.6px;border-bottom:2px solid ' + TEAL + ';padding-bottom:6px;margin-bottom:16px;">'
    + 'Offer &amp; Negotiation</div>';

  // ─────────────────────────────────────────────────────────────────────────────
  // 1. OFFER SUMMARY CARD
  // ─────────────────────────────────────────────────────────────────────────────
  h += '<div style="background:' + TEAL_BG + ';border:1px solid ' + TEAL_BORDER + ';border-radius:6px;'
    + 'padding:14px 18px;margin-bottom:20px;">';

  h += '<div style="font-size:11px;font-weight:700;color:' + TEAL + ';text-transform:uppercase;'
    + 'letter-spacing:.5px;margin-bottom:10px;">Offer Summary</div>';

  h += '<div style="display:flex;gap:32px;flex-wrap:wrap;align-items:flex-start">';

  // EV block
  h += '<div>';
  h += '<div style="font-size:11px;color:#6c757d;margin-bottom:2px;">Current EV (' + mock.scenario + ' scenario)</div>';
  h += '<div style="font-size:22px;font-weight:700;color:' + TEAL + ';font-family:Arial,sans-serif;">'
    + fmtM(mock.current_ev_m) + '</div>';
  h += '</div>';

  // Seller ask + gap
  h += '<div>';
  h += '<div style="font-size:11px;color:#6c757d;margin-bottom:2px;">Seller Ask</div>';
  h += '<div style="font-size:22px;font-weight:700;color:#374151;font-family:Arial,sans-serif;">'
    + fmtM(mock.seller_ask_m) + '</div>';
  h += '</div>';

  h += '<div>';
  h += '<div style="font-size:11px;color:#6c757d;margin-bottom:2px;">Gap</div>';
  h += '<div style="font-size:22px;font-weight:700;color:#b91c1c;font-family:Arial,sans-serif;">'
    + fmtM(mock.gap_m)
    + ' <span style="font-size:14px;font-weight:600;color:#b91c1c;">(' + fmtPct(mock.gap_pct) + ')</span></div>';
  h += '</div>';

  // Status block
  h += '<div>';
  h += '<div style="font-size:11px;color:#6c757d;margin-bottom:2px;">Status</div>';
  h += '<div style="font-size:14px;font-weight:700;color:#374151;font-family:Arial,sans-serif;">'
    + mock.status
    + ' <span style="font-size:12px;font-weight:400;color:#6c757d;">' + mock.status_date + '</span></div>';
  h += '<div style="font-size:12px;margin-top:4px;color:#374151;">'
    + '<span style="background:#fee2e2;color:#b91c1c;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700;">'
    + mock.open_issues + ' open issues</span></div>';
  h += '</div>';

  h += '</div>'; // flex row
  h += '</div>'; // summary card

  // ─────────────────────────────────────────────────────────────────────────────
  // 2. OFFER ROUND LEDGER
  // ─────────────────────────────────────────────────────────────────────────────
  h += '<div style="font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;'
    + 'letter-spacing:.5px;margin-bottom:8px;">Offer Round Ledger</div>';

  h += '<div style="overflow-x:auto;margin-bottom:20px;">';
  h += '<table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;">';
  h += '<thead><tr>';
  h += '<th style="' + thStyleL + ';min-width:40px">Rnd</th>';
  h += '<th style="' + thStyleL + ';min-width:80px">Date</th>';
  h += '<th style="' + thStyle  + ';min-width:70px">EV (K€)</th>';
  h += '<th style="' + thStyle  + ';min-width:80px">Sofort (K€)</th>';
  h += '<th style="' + thStyle  + ';min-width:50px">RB%</th>';
  h += '<th style="' + thStyle  + ';min-width:70px">EO (K€)</th>';
  h += '<th style="' + thStyle  + ';min-width:70px">Multiple</th>';
  h += '<th style="' + thStyleL + ';min-width:90px">Status</th>';
  h += '</tr></thead><tbody>';

  for (const r of mock.rounds) {
    const isLatest = r.rnd === mock.rounds.length;
    const rowBg = isLatest ? 'background:#f0f9ff;font-weight:600;' : '';
    h += '<tr style="' + rowBg + '">';
    h += '<td style="' + tdL + (isLatest?'font-weight:700;':'') + '">' + r.rnd + '</td>';
    h += '<td style="' + tdL + '">' + r.date + '</td>';
    h += '<td style="' + tdR + (isLatest?'font-weight:700;color:'+TEAL+';':'') + '">' + fmtK(r.ev) + '</td>';
    h += '<td style="' + tdR + '">' + fmtK(r.sofort) + '</td>';
    h += '<td style="' + tdR + '">' + fmtPct(r.rb_pct) + '</td>';
    h += '<td style="' + tdR + '">' + fmtK(r.eo) + '</td>';
    h += '<td style="' + tdR + '">' + fmtMult(r.multiple) + '</td>';
    h += '<td style="' + tdL + '">' + statusBadge(r.status) + '</td>';
    h += '</tr>';
  }

  h += '</tbody></table>';
  h += '</div>'; // overflow wrapper

  // ─────────────────────────────────────────────────────────────────────────────
  // 3. NEGOTIATION ISSUE LIST
  // ─────────────────────────────────────────────────────────────────────────────
  h += '<div style="font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;'
    + 'letter-spacing:.5px;margin-bottom:8px;">Negotiation Issue List</div>';

  h += '<div style="overflow-x:auto;margin-bottom:20px;">';
  h += '<table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;">';
  h += '<thead><tr>';
  h += '<th style="' + thStyleL + ';min-width:30px">#</th>';
  h += '<th style="' + thStyleL + ';min-width:160px">Issue</th>';
  h += '<th style="' + thStyleL + ';min-width:100px">Buyer</th>';
  h += '<th style="' + thStyleL + ';min-width:100px">Seller</th>';
  h += '<th style="' + thStyleL + ';min-width:80px">Status</th>';
  h += '<th style="' + thStyleL + ';min-width:60px">Prio</th>';
  h += '</tr></thead><tbody>';

  for (const iss of mock.issues) {
    const resolved = iss.status === 'Resolved';
    const rowStyle = resolved ? 'opacity:0.6;' : '';
    h += '<tr style="' + rowStyle + '">';
    h += '<td style="' + tdL + 'color:#6c757d;">' + iss.n + '</td>';
    h += '<td style="' + tdL + (resolved ? 'text-decoration:line-through;color:#6c757d;' : '') + '">'
      + iss.label + '</td>';
    h += '<td style="' + tdL + '">' + iss.buyer + '</td>';
    h += '<td style="' + tdL + '">' + iss.seller + '</td>';
    h += '<td style="' + tdL + '">' + statusBadge(iss.status) + '</td>';
    h += '<td style="' + tdL + '">' + prioBadge(iss.prio) + '</td>';
    h += '</tr>';
  }

  h += '</tbody></table>';
  h += '</div>'; // overflow wrapper

  // ─────────────────────────────────────────────────────────────────────────────
  // 4. SELLER COUNTER-POSITIONS
  // ─────────────────────────────────────────────────────────────────────────────
  h += '<div style="font-size:11px;font-weight:700;color:#374151;text-transform:uppercase;'
    + 'letter-spacing:.5px;margin-bottom:8px;">Seller Counter-Positions</div>';

  h += '<div style="border:1px solid #e9ecef;border-radius:4px;overflow:hidden;margin-bottom:20px;">';

  for (let i = 0; i < mock.counter_notes.length; i++) {
    const n = mock.counter_notes[i];
    const borderTop = i > 0 ? 'border-top:1px solid #e9ecef;' : '';
    h += '<div style="' + borderTop + 'padding:10px 14px;">';
    h += '<div style="font-size:11px;font-weight:700;color:' + TEAL + ';margin-bottom:4px;">' + n.date + '</div>';
    h += '<div style="font-size:12px;color:#374151;line-height:1.5;">' + n.text + '</div>';
    h += '</div>';
  }

  // Placeholder note for Granola integration
  h += '<div style="border-top:1px solid #e9ecef;padding:10px 14px;background:#fafbfc;">';
  h += '<div style="font-size:11px;color:#6c757d;font-style:italic;">'
    + '[Placeholder — Granola meeting transcripts will populate this section via DR-M8b integration]'
    + '</div>';
  h += '</div>';

  h += '</div>'; // counter-positions block

  return h;
}
