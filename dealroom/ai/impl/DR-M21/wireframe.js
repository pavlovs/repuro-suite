/**
 * DR-M21 — Wireframe render functions
 * Sections: Employees (8), Suppliers (subtab of 7), Market & Competition (10)
 *
 * All functions return HTML strings. Mock/placeholder data only.
 * Integration: drop renderEmployees(), renderSuppliers(), renderMarket()
 * into showSection() switch cases. Add the Suppliers subtab button to
 * renderCustomers() subtab row.
 *
 * CSS variables assumed present from dashboard.html:
 *   --text-muted:#6c757d  --accent:#0891B2 (teal)  --border:#e2e8f0
 * Class dependencies: .overview-card, .overview-card h3, .subtabs, .subtab,
 *   .subcontent, .subtab.active, .fin-table
 */

/* ─────────────────────────────────────────────────────────────────────────────
   Shared helpers (wireframe-local — safe to inline, no global collisions)
   ───────────────────────────────────────────────────────────────────────────── */

function _wf_kpiCard(label, value, sub, opts) {
  // opts: { warn, highlight, wide }
  opts = opts || {};
  var bg     = opts.warn ? '#fff7ed' : opts.highlight ? '#f0fdf4' : '#f8fafc';
  var border = opts.warn ? '#fed7aa' : opts.highlight ? '#86efac' : '#e2e8f0';
  var vColor = opts.warn ? '#c2410c' : opts.highlight ? '#15803d' : '#1e293b';
  var minW   = opts.wide ? '160px' : '130px';
  return '<div style="background:' + bg + ';border:1px solid ' + border + ';border-radius:8px;padding:12px 16px;min-width:' + minW + '">'
    + '<div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.3px;margin-bottom:4px">' + label + '</div>'
    + '<div style="font-size:20px;font-weight:700;color:' + vColor + '">' + value + '</div>'
    + '<div style="font-size:10px;color:#94a3b8;margin-top:2px">' + sub + '</div>'
    + '</div>';
}

function _wf_sectionLabel(text) {
  return '<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#0891B2;margin-bottom:8px;margin-top:4px">' + text + '</div>';
}

function _wf_wireframeBadge() {
  return '<span style="display:inline-block;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;'
    + 'background:#f1f5f9;color:#94a3b8;padding:2px 6px;border-radius:3px;border:1px solid #e2e8f0;vertical-align:middle;margin-left:8px">WIREFRAME</span>';
}

function _wf_tableHead(cols) {
  // cols: [{label, align}]
  var h = '<thead><tr style="border-bottom:2px solid #e2e8f0">';
  cols.forEach(function(c) {
    h += '<th style="text-align:' + (c.align || 'left') + ';padding:6px 8px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">' + c.label + '</th>';
  });
  h += '</tr></thead>';
  return h;
}

/* ─────────────────────────────────────────────────────────────────────────────
   Section 8 — EMPLOYEES
   IC memo chapter: Organisation — Personnel
   ───────────────────────────────────────────────────────────────────────────── */
function renderEmployees() {
  var h = '';

  // ── Page title ──
  h += '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:20px">';
  h += '<h2 style="margin:0;font-size:18px;color:#1e293b">Employees</h2>';
  h += _wf_wireframeBadge();
  h += '</div>';

  // ── HEADCOUNT SUMMARY — KPI strip ──
  h += '<div class="overview-card" style="margin-bottom:16px">';
  h += _wf_sectionLabel('Headcount Summary');
  h += '<div style="display:flex;gap:12px;flex-wrap:wrap">';
  h += _wf_kpiCard('Total HC',      '45',    'Headcount');
  h += _wf_kpiCard('FTE',           '42,5',  'Full-time equivalent');
  h += _wf_kpiCard('Avg. Tenure',   '6,2 J', 'Years');
  h += _wf_kpiCard('Avg. Age',      '41',    'Years');
  h += _wf_kpiCard('Turnover Rate', '8 %',   'p.a.', {warn: true});
  h += '</div>';
  h += '</div>';

  // ── PERSONNEL BY DEPARTMENT ──
  h += '<div class="overview-card" style="margin-bottom:16px">';
  h += _wf_sectionLabel('Personal nach Abteilung');

  var depts = [
    { name:'Vertrieb',        hc:12, fte:'12,0', comp:'48' },
    { name:'Lager / Logistik',hc:15, fte:'14,5', comp:'36' },
    { name:'Verwaltung',      hc:8,  fte:'7,5',  comp:'52' },
    { name:'Service / Tech.', hc:6,  fte:'5,5',  comp:'42' },
    { name:'GF',              hc:2,  fte:'2,0',  comp:'180', highlight:true },
    { name:'Azubis',          hc:2,  fte:'2,0',  comp:'18'  },
  ];

  h += '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  h += _wf_tableHead([
    {label:'Abteilung'},
    {label:'HC',   align:'right'},
    {label:'FTE',  align:'right'},
    {label:'Ø Vergütung K€', align:'right'},
    {label:'',     align:'right'}, // bar column
  ]);
  h += '<tbody>';
  var maxComp = 180;
  depts.forEach(function(d, i) {
    var rowBg = i % 2 === 0 ? '#fff' : '#f8fafc';
    var nameColor = d.highlight ? '#0891B2' : '#1e293b';
    var barW = Math.round((parseInt(d.comp) / maxComp) * 100);
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:' + rowBg + '">';
    h += '<td style="padding:6px 8px;font-weight:500;color:' + nameColor + '">' + d.name + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-variant-numeric:tabular-nums">' + d.hc + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-variant-numeric:tabular-nums;color:#64748b">' + d.fte + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-family:monospace">' + d.comp + '</td>';
    h += '<td style="padding:6px 16px;min-width:80px"><div style="background:#e2e8f0;border-radius:3px;height:6px"><div style="background:#0891B2;border-radius:3px;height:6px;width:' + barW + '%"></div></div></td>';
    h += '</tr>';
  });
  // Total row
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700">';
  h += '<td style="padding:6px 8px">GESAMT</td>';
  h += '<td style="padding:6px 8px;text-align:right">45</td>';
  h += '<td style="padding:6px 8px;text-align:right;color:#64748b">42,5</td>';
  h += '<td style="padding:6px 8px;text-align:right;color:#94a3b8">—</td>';
  h += '<td></td>';
  h += '</tr>';
  h += '</tbody></table>';
  h += '</div>';

  // ── KEY PERSON RISK ──
  h += '<div class="overview-card">';
  h += _wf_sectionLabel('Key Person Risk');

  var risks = [
    {
      title: 'GF (58 J., alleiniger Geschäftsführer)',
      detail: 'Kein Prokura-Vertreter. Ausfall blockiert Vertragsabschlüsse und Bankvollmacht.',
      level: 'high',
    },
    {
      title: 'Head of Sales (15 J. Betriebszugehörigkeit, Schlüsselkunden)',
      detail: 'Persönliche Kundenbeziehungen zu Top-3-Kunden. Kein schriftlicher Übergabeplan.',
      level: 'high',
    },
    {
      title: 'Lagerist (einzige Fachkraft für Gefahrgut-Handling)',
      detail: 'ADR-Zertifikat läuft 2025 aus. Nachfolger nicht identifiziert.',
      level: 'medium',
    },
  ];

  h += '<div style="display:flex;flex-direction:column;gap:10px">';
  risks.forEach(function(r) {
    var bg     = r.level === 'high' ? '#fff7ed' : '#fffbeb';
    var border = r.level === 'high' ? '#fed7aa' : '#fde68a';
    var icon   = r.level === 'high' ? '&#9888;' : '&#9888;';
    var iconC  = r.level === 'high' ? '#c2410c' : '#b45309';
    h += '<div style="background:' + bg + ';border:1px solid ' + border + ';border-radius:6px;padding:10px 14px;display:flex;gap:10px;align-items:flex-start">';
    h += '<span style="font-size:16px;color:' + iconC + ';flex-shrink:0;margin-top:1px">' + icon + '</span>';
    h += '<div>';
    h += '<div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:2px">' + r.title + '</div>';
    h += '<div style="font-size:12px;color:#6c757d;line-height:1.5">' + r.detail + '</div>';
    h += '</div>';
    h += '</div>';
  });
  h += '</div>';

  h += '<div style="margin-top:12px;font-size:11px;color:#94a3b8;font-style:italic">Platzhalter-Daten — nach RFI-Rücklauf zu befüllen.</div>';
  h += '</div>'; // end key person risk card

  return h;
}

/* ─────────────────────────────────────────────────────────────────────────────
   Section 7 subtab — SUPPLIERS
   Add as subtab inside renderCustomers() alongside "Kunden".
   Call renderSuppliers() for the sub-content panel.
   ───────────────────────────────────────────────────────────────────────────── */
function renderSuppliers() {
  var h = '';

  // ── SUPPLIER CONCENTRATION TABLE ──
  h += '<div class="overview-card" style="margin-bottom:16px">';
  h += _wf_sectionLabel('Lieferanten-Konzentration');

  var suppliers = [
    { rank:1, name:'Medline',       vol:'1.200', share:'22%', excl:'Nein', shareNum:22 },
    { rank:2, name:'B. Braun',      vol:'890',   share:'16%', excl:'Ja',   shareNum:16, exclusive:true },
    { rank:3, name:'Paul Hartmann', vol:'650',   share:'12%', excl:'Nein', shareNum:12 },
    { rank:4, name:'Cardinal',      vol:'420',   share:'8%',  excl:'Nein', shareNum:8  },
    { rank:5, name:'Sonstige (23)', vol:'2.340', share:'42%', excl:'—',    shareNum:42, other:true },
  ];

  h += '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  h += _wf_tableHead([
    {label:'#',            align:'right'},
    {label:'Name'},
    {label:'Vol. K€',      align:'right'},
    {label:'Anteil',       align:'right'},
    {label:'Exklusiv',     align:'center'},
    {label:'',             align:'right'}, // bar
  ]);
  h += '<tbody>';
  suppliers.forEach(function(s, i) {
    var rowBg   = i % 2 === 0 ? '#fff' : '#f8fafc';
    var nameFw  = s.other ? '400' : '500';
    var nameC   = s.other ? '#94a3b8' : '#1e293b';
    var exclEl  = s.exclusive
      ? '<span style="color:#b45309;font-weight:600;font-size:11px">Ja</span>'
      : (s.excl === 'Nein'
        ? '<span style="color:#64748b;font-size:11px">Nein</span>'
        : '<span style="color:#94a3b8;font-size:11px">—</span>');
    var barW = Math.round(s.shareNum * 1.8); // scale: 100% → 180px cap
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:' + rowBg + '">';
    h += '<td style="padding:6px 8px;text-align:right;color:#94a3b8;font-weight:600">' + s.rank + '</td>';
    h += '<td style="padding:6px 8px;font-weight:' + nameFw + ';color:' + nameC + '">' + s.name + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-family:monospace">' + s.vol + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-weight:600;color:#1e293b">' + s.share + '</td>';
    h += '<td style="padding:6px 8px;text-align:center">' + exclEl + '</td>';
    h += '<td style="padding:6px 16px;min-width:80px"><div style="background:#e2e8f0;border-radius:3px;height:6px"><div style="background:#0891B2;border-radius:3px;height:6px;width:' + barW + 'px"></div></div></td>';
    h += '</tr>';
  });
  // Total row
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700">';
  h += '<td colspan="2" style="padding:6px 8px">GESAMT</td>';
  h += '<td style="padding:6px 8px;text-align:right;font-family:monospace">5.500</td>';
  h += '<td style="padding:6px 8px;text-align:right">100 %</td>';
  h += '<td colspan="2"></td>';
  h += '</tr>';
  h += '</tbody></table>';
  h += '</div>';

  // ── DEPENDENCY RISK ──
  h += '<div class="overview-card">';
  h += _wf_sectionLabel('Abhängigkeitsrisiko');

  h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">';
  h += _wf_kpiCard('Top-1-Anteil',   '22 %', 'Medline',       {});
  h += _wf_kpiCard('Top-3-Anteil',   '50 %', 'Medline + 2',   {warn: true});
  h += _wf_kpiCard('Exklusivverträge','1',   'B. Braun',      {warn: true});
  h += _wf_kpiCard('Ø Laufzeit',     '2 J.', 'Rahmenverträge',{});
  h += '</div>';

  // Risk indicator bar
  var risks2 = [
    { label:'Top-1 < 20 %',   status:'warn',  text:'22 % — knapp über Schwelle' },
    { label:'Top-3 < 50 %',   status:'bad',   text:'50 % — an Grenze' },
    { label:'Kein Exklusiv',  status:'bad',   text:'1 Exklusivvertrag (B. Braun)' },
    { label:'Alternativen OK',status:'ok',    text:'23 weitere Lieferanten' },
  ];
  h += '<div style="display:flex;flex-direction:column;gap:6px">';
  risks2.forEach(function(r) {
    var dot   = r.status === 'ok' ? '#22c55e' : r.status === 'warn' ? '#f59e0b' : '#ef4444';
    var textC = r.status === 'ok' ? '#15803d' : r.status === 'warn' ? '#b45309'  : '#b91c1c';
    h += '<div style="display:flex;align-items:center;gap:8px;font-size:12px">';
    h += '<span style="width:8px;height:8px;border-radius:50%;background:' + dot + ';flex-shrink:0;display:inline-block"></span>';
    h += '<span style="font-weight:600;color:#334155;min-width:140px">' + r.label + '</span>';
    h += '<span style="color:' + textC + '">' + r.text + '</span>';
    h += '</div>';
  });
  h += '</div>';

  h += '<div style="margin-top:12px;font-size:11px;color:#94a3b8;font-style:italic">Platzhalter-Daten — nach Lieferanten-RFI zu befüllen.</div>';
  h += '</div>'; // end dependency card

  return h;
}

/**
 * renderCustomersWithSuppliers() — drop-in replacement for renderCustomers()
 * Wraps the existing renderCustomers() content + adds Suppliers subtab.
 * Call this from showSection('customers') instead of the old renderCustomers().
 *
 * INTEGRATION NOTE: Replace the case 'customers' in showSection():
 *   case 'customers': area.innerHTML = bc + renderCustomersWithSuppliers(); break;
 */
function renderCustomersWithSuppliers() {
  var h = '';
  h += '<div class="subtabs">';
  h += '<button class="subtab active" onclick="showSubtab(this,\'sub-kunden\')">Kunden</button>';
  h += '<button class="subtab" onclick="showSubtab(this,\'sub-lieferanten\')">' + _wf_wireframeBadge().replace('margin-left:8px','margin-left:0') + ' Lieferanten</button>';
  h += '</div>';

  // Kunden tab (existing content)
  h += '<div id="sub-kunden" class="subcontent active">';
  if (typeof renderCustomers === 'function') {
    h += renderCustomers();
  } else {
    h += '<div style="color:#94a3b8;font-size:13px">renderCustomers() not found — integrate after loading dashboard.html.</div>';
  }
  h += '</div>';

  // Lieferanten tab (new wireframe)
  h += '<div id="sub-lieferanten" class="subcontent">';
  h += renderSuppliers();
  h += '</div>';

  return h;
}

/* ─────────────────────────────────────────────────────────────────────────────
   Section 10 — MARKET & COMPETITION
   IC memo chapter: Markt
   ───────────────────────────────────────────────────────────────────────────── */
function renderMarket() {
  var h = '';

  // ── Page title ──
  h += '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:20px">';
  h += '<h2 style="margin:0;font-size:18px;color:#1e293b">Market &amp; Competition</h2>';
  h += _wf_wireframeBadge();
  h += '</div>';

  // ── COMPETITIVE LANDSCAPE ──
  h += '<div class="overview-card" style="margin-bottom:16px">';
  h += _wf_sectionLabel('Competitive Landscape');

  var competitors = [
    { name:'Wettbewerber A',  rev:'~45',  scope:'National',    overlap:'Hoch',     overlapLevel:'high' },
    { name:'Wettbewerber B',  rev:'~12',  scope:'Regional',    overlap:'Hoch',     overlapLevel:'high' },
    { name:'Wettbewerber C',  rev:'~28',  scope:'Spezialist',  overlap:'Gering',   overlapLevel:'low'  },
    { name:'Wettbewerber D',  rev:'~8',   scope:'Regional',    overlap:'Mittel',   overlapLevel:'mid'  },
  ];

  h += '<table style="width:100%;border-collapse:collapse;font-size:13px">';
  h += _wf_tableHead([
    {label:'Unternehmen'},
    {label:'Umsatz M€',     align:'right'},
    {label:'Segment'},
    {label:'Produktüberlappung', align:'center'},
  ]);
  h += '<tbody>';
  competitors.forEach(function(c, i) {
    var rowBg  = i % 2 === 0 ? '#fff' : '#f8fafc';
    var olBg   = c.overlapLevel === 'high' ? '#fff7ed' : c.overlapLevel === 'mid' ? '#fffbeb' : '#f0fdf4';
    var olC    = c.overlapLevel === 'high' ? '#c2410c' : c.overlapLevel === 'mid' ? '#b45309' : '#15803d';
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:' + rowBg + '">';
    h += '<td style="padding:6px 8px;font-weight:500;color:#1e293b">' + c.name + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-family:monospace;color:#334155">' + c.rev + '</td>';
    h += '<td style="padding:6px 8px;color:#64748b">' + c.scope + '</td>';
    h += '<td style="padding:6px 8px;text-align:center"><span style="background:' + olBg + ';color:' + olC + ';font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px">' + c.overlap + '</span></td>';
    h += '</tr>';
  });
  h += '</tbody></table>';
  h += '<div style="margin-top:8px;font-size:11px;color:#94a3b8;font-style:italic">Namen anonymisiert — durch echte Wettbewerber ersetzen.</div>';
  h += '</div>';

  // ── MARKET POSITIONING — 2x2 Grid ──
  h += '<div class="overview-card" style="margin-bottom:16px">';
  h += _wf_sectionLabel('Marktpositionierung');

  var W = 320, H = 240;
  var cx = W / 2, cy = H / 2;
  // Target company dot: slightly right of center, below center (scale > specialist)
  var tx = cx + 40, ty = cy + 30;

  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;max-width:' + W + 'px;display:block;margin:0 auto">';

  // Background quadrants
  svg += '<rect x="0" y="0" width="' + cx + '" height="' + cy + '" fill="#fafbff" rx="0"/>';
  svg += '<rect x="' + cx + '" y="0" width="' + cx + '" height="' + cy + '" fill="#f0fdf4" rx="0"/>';
  svg += '<rect x="0" y="' + cy + '" width="' + cx + '" height="' + cy + '" fill="#fff7ed" rx="0"/>';
  svg += '<rect x="' + cx + '" y="' + cy + '" width="' + cx + '" height="' + cy + '" fill="#fef2f2" rx="0"/>';

  // Axes
  svg += '<line x1="' + cx + '" y1="10" x2="' + cx + '" y2="' + (H - 10) + '" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="4,3"/>';
  svg += '<line x1="10" y1="' + cy + '" x2="' + (W - 10) + '" y2="' + cy + '" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="4,3"/>';

  // Axis labels
  svg += '<text x="' + cx + '" y="8" text-anchor="middle" font-size="10" font-weight="600" fill="#64748b">Spezialist</text>';
  svg += '<text x="' + cx + '" y="' + (H - 2) + '" text-anchor="middle" font-size="10" font-weight="600" fill="#64748b">Generalist</text>';
  svg += '<text x="14" y="' + (cy + 1) + '" text-anchor="start" font-size="10" font-weight="600" fill="#64748b">Nische</text>';
  svg += '<text x="' + (W - 14) + '" y="' + (cy + 1) + '" text-anchor="end" font-size="10" font-weight="600" fill="#64748b">Scale</text>';

  // Competitor dots
  var compDots = [
    { x: cx - 20, y: cy - 50, label:'A' },
    { x: cx + 30, y: cy - 60, label:'B' },
    { x: cx - 50, y: cy + 40, label:'C' },
    { x: cx + 60, y: cy + 25, label:'D' },
  ];
  compDots.forEach(function(d) {
    svg += '<circle cx="' + d.x + '" cy="' + d.y + '" r="7" fill="#94a3b8" opacity=".7"/>';
    svg += '<text x="' + d.x + '" y="' + (d.y + 3.5) + '" text-anchor="middle" font-size="8" font-weight="700" fill="#fff">' + d.label + '</text>';
  });

  // Target company dot
  svg += '<circle cx="' + tx + '" cy="' + ty + '" r="10" fill="#0891B2" opacity=".9"/>';
  svg += '<text x="' + (tx + 14) + '" y="' + (ty - 8) + '" font-size="10" font-weight="700" fill="#0891B2">Zielunternehmen</text>';
  svg += '<text x="' + (tx + 14) + '" y="' + (ty + 4) + '" font-size="9" fill="#64748b">(Platzhalter)</text>';

  svg += '</svg>';

  h += svg;
  h += '<div style="margin-top:8px;font-size:11px;color:#94a3b8;text-align:center;font-style:italic">Achsen-Einordnung nach RFI / Interviews zu kalibrieren.</div>';
  h += '</div>';

  // ── MARKET CONTEXT ──
  h += '<div class="overview-card">';
  h += _wf_sectionLabel('Marktkontext');

  var contextRows = [
    { label:'TAM (DE)',          value:'~2,5 Mrd. € — ambulante Medizinproduktversorgung Deutschland' },
    { label:'SAM (Regional)',    value:'~800 Mio. € — regionale Distribution / spezialisierte Segmente' },
    { label:'Wachstum',         value:'~3–4 % p.a. — demografisch getrieben, strukturell stabil' },
    { label:'Regulierung',      value:'MDR-Compliance laufend; DSGVO-konforme Patientendaten' },
    { label:'Key Trends',       value:'Konsolidierung, Digitalisierung, vertikale Integration' },
    { label:'Wettbewerbsdruck', value:'National: 3–4 Spieler mit > 30 M€; regional sehr fragmentiert' },
  ];

  h += '<div style="display:flex;flex-direction:column;gap:0">';
  contextRows.forEach(function(r, i) {
    var rowBg = i % 2 === 0 ? '#fff' : '#f8fafc';
    h += '<div style="display:flex;gap:16px;padding:7px 4px;border-bottom:1px solid #f1f5f9;background:' + rowBg + '">';
    h += '<span style="min-width:160px;font-size:12px;font-weight:600;color:#64748b;flex-shrink:0">' + r.label + '</span>';
    h += '<span style="font-size:13px;color:#334155;line-height:1.4">' + r.value + '</span>';
    h += '</div>';
  });
  h += '</div>';

  h += '<div style="margin-top:12px;font-size:11px;color:#94a3b8;font-style:italic">Platzhalter — durch dealspezifische Marktdaten zu ersetzen.</div>';
  h += '</div>'; // end market context card

  return h;
}

/* ─────────────────────────────────────────────────────────────────────────────
   INTEGRATION GUIDE
   ─────────────────────────────────────────────────────────────────────────────
   In showSection() switch (dashboard.html):

     case 'employees':
       area.innerHTML = bc + renderEmployees();
       break;

     case 'customers':
       area.innerHTML = bc + renderCustomersWithSuppliers();
       break;

     case 'market':
       area.innerHTML = bc + renderMarket();
       break;

   showSubtab() is already defined in dashboard.html — no change needed.

   Remove 'stub' labels from DR-M19 renderSidebar() for these three items once wired.
   ───────────────────────────────────────────────────────────────────────────── */
