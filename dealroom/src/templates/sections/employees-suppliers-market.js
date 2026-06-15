// ─── Customers section ───────────────────────────────────────────────────────

function renderCustomers() {
  const cust = DATA.customers || {};
  const metrics = cust.metrics || {};
  const top10 = cust.top10 || {};
  const years = Object.keys(metrics).sort();

  if(years.length === 0) {
    return '<div class="stub"><h3>Customers</h3><p>No customer analysis data available.</p></div>';
  }

  const latest = years[years.length - 1];
  const m = metrics[latest] || {};
  const _fmt = v => v != null ? v : '—';
  const _eur = v => v != null ? '\u20ac'+(v>=1000000?(v/1000000).toFixed(2)+'M':(v/1000).toFixed(0)+'K') : '—';
  const _pct = v => v != null ? v.toFixed(1)+'%' : '—';

  let h = '';

  // ── KPI strip ──
  h += '<div style="display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap">';
  const kpis = [
    {l:'Total Customers', v:_fmt(m.total_customers), sub:latest},
    {l:'Recurring Share', v:_pct(m.recurring_rev_share), sub:latest, highlight: m.recurring_rev_share != null && m.recurring_rev_share >= 60},
    {l:'Top 10 Concentration', v:_pct(m.top10_share), sub:latest, warn: m.top10_share != null && m.top10_share > 60},
    {l:'Top 1 Share', v:_pct(m.top1_share), sub:latest},
    {l:'New Customers', v:_fmt(m.new_customers), sub:latest},
    {l:'Retained Customers', v:_fmt(m.retained_customers), sub:latest},
  ];
  kpis.forEach(k => {
    const bg = k.warn ? '#fff7ed' : k.highlight ? '#f0fdf4' : '#f8fafc';
    const border = k.warn ? '#fed7aa' : k.highlight ? '#86efac' : '#e2e8f0';
    const vColor = k.warn ? '#c2410c' : k.highlight ? '#15803d' : '#1e293b';
    h += '<div style="background:'+bg+';border:1px solid '+border+';border-radius:8px;padding:12px 16px;min-width:130px">';
    h += '<div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.3px;margin-bottom:4px">'+k.l+'</div>';
    h += '<div style="font-size:20px;font-weight:700;color:'+vColor+'">'+k.v+'</div>';
    h += '<div style="font-size:10px;color:#94a3b8;margin-top:2px">'+k.sub+'</div>';
    h += '</div>';
  });
  h += '</div>';

  // ── Charts row ──
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">';

  // Chart 1: Customer count trend (total vs retained vs new)
  h += '<div class="overview-card">';
  h += '<h3>Customer Count by Year</h3>';
  h += _custBarChart(years, metrics, ['total_customers','retained_customers','new_customers'],
    ['Total','Retained','New'], ['#1D7080','#38bdf8','#fb923c']);
  h += '</div>';

  // Chart 2: Revenue split — recurring vs new customer revenue
  h += '<div class="overview-card">';
  h += '<h3>Revenue Split (Recurring vs New)</h3>';
  h += _custStackedBar(years, metrics);
  h += '</div>';

  h += '</div>'; // end charts row

  // ── Year-selector for Top 10 ──
  h += '<div class="overview-card">';
  h += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
  h += '<h3 style="margin:0">Top 10 Customers</h3>';
  h += '<div style="display:flex;gap:6px">';
  years.forEach((yr, i) => {
    const active = yr === latest;
    h += '<button onclick="custShowYear(\''+yr+'\')" id="cust-yr-btn-'+yr+'" style="padding:4px 10px;border-radius:4px;border:1px solid '+(active?'#1D7080':'#e2e8f0')+';background:'+(active?'#1D7080':'#fff')+';color:'+(active?'#fff':'#64748b')+';font-size:11px;cursor:pointer;font-weight:600">'+yr+'</button>';
  });
  h += '</div></div>';

  years.forEach(yr => {
    const rows = top10[yr] || [];
    const hidden = yr !== latest ? 'display:none' : '';
    h += '<div id="cust-top10-'+yr+'" style="'+hidden+'">';
    if(rows.length === 0) {
      h += '<div style="color:#94a3b8;font-size:13px">No top-10 data for '+yr+'</div>';
    } else {
      h += '<table style="width:100%;border-collapse:collapse;font-size:13px">';
      h += '<thead><tr style="border-bottom:2px solid #e2e8f0">';
      h += '<th style="text-align:left;padding:6px 8px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">#</th>';
      h += '<th style="text-align:left;padding:6px 8px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">Customer</th>';
      h += '<th style="text-align:right;padding:6px 8px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">Revenue</th>';
      h += '<th style="text-align:right;padding:6px 8px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase">Share</th>';
      h += '<th style="text-align:left;padding:6px 16px;color:#64748b;font-weight:600;font-size:11px"></th>';
      h += '</tr></thead><tbody>';
      const maxRev = rows[0].revenue || 1;
      rows.forEach((r, i) => {
        const barW = Math.round((r.revenue / maxRev) * 100);
        const rowBg = i % 2 === 0 ? '#fff' : '#f8fafc';
        h += '<tr style="border-bottom:1px solid #f1f5f9;background:'+rowBg+'">';
        h += '<td style="padding:6px 8px;color:#94a3b8;font-weight:600;font-variant-numeric:tabular-nums">'+(r.rank||i+1)+'</td>';
        h += '<td style="padding:6px 8px;font-weight:500;color:#1e293b">'+r.name+'</td>';
        h += '<td style="padding:6px 8px;text-align:right;font-family:monospace;color:#334155">'+_eur(r.revenue)+'</td>';
        h += '<td style="padding:6px 8px;text-align:right;color:#64748b;font-weight:600">'+_pct(r.pct)+'</td>';
        h += '<td style="padding:6px 16px;min-width:100px"><div style="background:#e2e8f0;border-radius:3px;height:6px"><div style="background:#1D7080;border-radius:3px;height:6px;width:'+barW+'%"></div></div></td>';
        h += '</tr>';
      });
      h += '</tbody></table>';
    }
    h += '</div>';
  });
  h += '</div>'; // end top10 card

  return h;
}

function custShowYear(yr) {
  const cust = DATA.customers || {};
  const years = Object.keys((cust.metrics)||{}).sort();
  years.forEach(y => {
    const el = document.getElementById('cust-top10-'+y);
    if(el) el.style.display = y===yr ? '' : 'none';
    const btn = document.getElementById('cust-yr-btn-'+y);
    if(btn) {
      btn.style.background = y===yr ? '#1D7080' : '#fff';
      btn.style.color = y===yr ? '#fff' : '#64748b';
      btn.style.borderColor = y===yr ? '#1D7080' : '#e2e8f0';
    }
  });
}

function _custBarChart(years, metrics, keys, labels, colors) {
  // Simple grouped SVG bar chart
  const W=360, H=160, padL=48, padB=28, padT=10, padR=10;
  const chartW=W-padL-padR, chartH=H-padT-padB;
  const nYears=years.length, nKeys=keys.length;
  const groupW=chartW/nYears;
  const barW=Math.min(22, (groupW-8)/nKeys);

  // Find max value
  let maxV=0;
  years.forEach(yr => keys.forEach(k => { const v=metrics[yr]&&metrics[yr][k]; if(v!=null&&v>maxV) maxV=v; }));
  if(!maxV) return '<div style="color:#94a3b8;font-size:12px">No data</div>';

  let svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;max-height:'+H+'px;overflow:visible">';
  // Grid lines
  for(let i=0;i<=4;i++) {
    const y=padT+chartH*(1-i/4);
    const val=Math.round(maxV*i/4);
    svg+='<line x1="'+padL+'" y1="'+y.toFixed(1)+'" x2="'+(padL+chartW)+'" y2="'+y.toFixed(1)+'" stroke="#f1f5f9" stroke-width="1"/>';
    svg+='<text x="'+(padL-4)+'" y="'+(y+4).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8">'+val+'</text>';
  }

  // Bars
  years.forEach((yr,gi) => {
    const gx=padL+gi*groupW+(groupW-nKeys*barW-(nKeys-1)*2)/2;
    keys.forEach((k,ki) => {
      const v=(metrics[yr]&&metrics[yr][k])||0;
      const bh=v/maxV*chartH;
      const x=gx+ki*(barW+2);
      const y=padT+chartH-bh;
      svg+='<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+barW+'" height="'+bh.toFixed(1)+'" fill="'+colors[ki]+'" rx="2" opacity="0.85"/>';
      if(v>0&&bh>12) svg+='<text x="'+(x+barW/2).toFixed(1)+'" y="'+(y-3).toFixed(1)+'" text-anchor="middle" font-size="8" fill="'+colors[ki]+'">'+Math.round(v)+'</text>';
    });
    svg+='<text x="'+(padL+gi*groupW+groupW/2).toFixed(1)+'" y="'+(H-4)+'" text-anchor="middle" font-size="10" fill="#64748b">'+yr+'</text>';
  });

  // Legend
  let lx=padL;
  labels.forEach((l,i) => {
    svg+='<rect x="'+lx+'" y="2" width="10" height="8" fill="'+colors[i]+'" rx="1"/>';
    svg+='<text x="'+(lx+13)+'" y="9" font-size="9" fill="#64748b">'+l+'</text>';
    lx+=l.length*5.5+20;
  });

  svg+='</svg>';
  return svg;
}

function _custStackedBar(years, metrics) {
  // Stacked bar: recurring_rev_eur (bottom) + new_customer_rev_eur (top)
  const W=360, H=160, padL=56, padB=28, padT=18, padR=10;
  const chartW=W-padL-padR, chartH=H-padT-padB;
  const barW=Math.min(50, chartW/years.length*0.55);

  let maxV=0;
  years.forEach(yr => {
    const m=metrics[yr]||{};
    const tot=(m.recurring_rev_eur||0)+(m.new_customer_rev_eur||0);
    if(tot>maxV) maxV=tot;
  });
  if(!maxV) return '<div style="color:#94a3b8;font-size:12px">No revenue data</div>';

  let svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;max-height:'+H+'px;overflow:visible">';
  // Grid lines + Y axis labels (€M)
  for(let i=0;i<=4;i++) {
    const y=padT+chartH*(1-i/4);
    const val=maxV*i/4;
    const label=val>=1000000?(val/1000000).toFixed(1)+'M':(val/1000).toFixed(0)+'K';
    svg+='<line x1="'+padL+'" y1="'+y.toFixed(1)+'" x2="'+(padL+chartW)+'" y2="'+y.toFixed(1)+'" stroke="#f1f5f9" stroke-width="1"/>';
    svg+='<text x="'+(padL-4)+'" y="'+(y+4).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8">'+label+'</text>';
  }

  years.forEach((yr,gi) => {
    const m=metrics[yr]||{};
    const recV=m.recurring_rev_eur||0;
    const newV=m.new_customer_rev_eur||0;
    const total=recV+newV;
    const recH=recV/maxV*chartH;
    const newH=newV/maxV*chartH;
    const x=padL+gi*(chartW/years.length)+(chartW/years.length-barW)/2;

    // Recurring (bottom, teal)
    svg+='<rect x="'+x.toFixed(1)+'" y="'+(padT+chartH-recH).toFixed(1)+'" width="'+barW+'" height="'+recH.toFixed(1)+'" fill="#1D7080" rx="2"/>';
    // New (top, orange)
    if(newH>0.5) svg+='<rect x="'+x.toFixed(1)+'" y="'+(padT+chartH-recH-newH).toFixed(1)+'" width="'+barW+'" height="'+newH.toFixed(1)+'" fill="#fb923c" rx="2" opacity="0.85"/>';
    // Total label above bar
    if(total>0) {
      const tLabel=total>=1000000?(total/1000000).toFixed(2)+'M':(total/1000).toFixed(0)+'K';
      svg+='<text x="'+(x+barW/2).toFixed(1)+'" y="'+(padT+chartH-recH-newH-4).toFixed(1)+'" text-anchor="middle" font-size="9" fill="#334155" font-weight="600">\u20ac'+tLabel+'</text>';
    }
    svg+='<text x="'+(x+barW/2).toFixed(1)+'" y="'+(H-4)+'" text-anchor="middle" font-size="10" fill="#64748b">'+yr+'</text>';
  });

  // Legend
  svg+='<rect x="'+padL+'" y="2" width="10" height="8" fill="#1D7080" rx="1"/>';
  svg+='<text x="'+(padL+13)+'" y="9" font-size="9" fill="#64748b">Recurring</text>';
  svg+='<rect x="'+(padL+70)+'" y="2" width="10" height="8" fill="#fb923c" rx="1" opacity="0.85"/>';
  svg+='<text x="'+(padL+83)+'" y="9" font-size="9" fill="#64748b">New</text>';

  svg+='</svg>';
  return svg;
}

// ─── DR-M21 — Employees, Suppliers, Market (wireframe) ─────────────────────
// Dependencies: DATA global, renderCustomers() (from main dashboard), showSubtab()
// Exports: renderEmployees(), renderSuppliers(), renderCustomersWithSuppliers(), renderMarket()

function _wf_kpiCard(label, value, sub, opts) {
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
  var h = '<thead><tr style="border-bottom:2px solid #e2e8f0">';
  cols.forEach(function(c) {
    h += '<th style="text-align:' + (c.align || 'left') + ';padding:6px 8px;color:#64748b;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.3px">' + c.label + '</th>';
  });
  h += '</tr></thead>';
  return h;
}

function renderEmployees() {
  var h = '';

  h += '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:20px">';
  h += '<h2 style="margin:0;font-size:18px;color:#1e293b">Employees</h2>';
  h += _wf_wireframeBadge();
  h += '</div>';

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
    {label:'',     align:'right'},
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
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700">';
  h += '<td style="padding:6px 8px">GESAMT</td>';
  h += '<td style="padding:6px 8px;text-align:right">45</td>';
  h += '<td style="padding:6px 8px;text-align:right;color:#64748b">42,5</td>';
  h += '<td style="padding:6px 8px;text-align:right;color:#94a3b8">—</td>';
  h += '<td></td>';
  h += '</tr>';
  h += '</tbody></table>';
  h += '</div>';

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
  h += '</div>';

  return h;
}

function renderSuppliers() {
  var h = '';

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
    {label:'',             align:'right'},
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
    var barW = Math.round(s.shareNum * 1.8);
    h += '<tr style="border-bottom:1px solid #f1f5f9;background:' + rowBg + '">';
    h += '<td style="padding:6px 8px;text-align:right;color:#94a3b8;font-weight:600">' + s.rank + '</td>';
    h += '<td style="padding:6px 8px;font-weight:' + nameFw + ';color:' + nameC + '">' + s.name + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-family:monospace">' + s.vol + '</td>';
    h += '<td style="padding:6px 8px;text-align:right;font-weight:600;color:#1e293b">' + s.share + '</td>';
    h += '<td style="padding:6px 8px;text-align:center">' + exclEl + '</td>';
    h += '<td style="padding:6px 16px;min-width:80px"><div style="background:#e2e8f0;border-radius:3px;height:6px"><div style="background:#0891B2;border-radius:3px;height:6px;width:' + barW + 'px"></div></div></td>';
    h += '</tr>';
  });
  h += '<tr style="border-top:2px solid #e2e8f0;background:#f8fafc;font-weight:700">';
  h += '<td colspan="2" style="padding:6px 8px">GESAMT</td>';
  h += '<td style="padding:6px 8px;text-align:right;font-family:monospace">5.500</td>';
  h += '<td style="padding:6px 8px;text-align:right">100 %</td>';
  h += '<td colspan="2"></td>';
  h += '</tr>';
  h += '</tbody></table>';
  h += '</div>';

  h += '<div class="overview-card">';
  h += _wf_sectionLabel('Abhängigkeitsrisiko');

  h += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">';
  h += _wf_kpiCard('Top-1-Anteil',   '22 %', 'Medline',       {});
  h += _wf_kpiCard('Top-3-Anteil',   '50 %', 'Medline + 2',   {warn: true});
  h += _wf_kpiCard('Exklusivverträge','1',   'B. Braun',      {warn: true});
  h += _wf_kpiCard('Ø Laufzeit',     '2 J.', 'Rahmenverträge',{});
  h += '</div>';

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
  h += '</div>';

  return h;
}

function renderCustomersWithSuppliers() {
  // DR-M25: with CDD data the full customer analysis set (concentration,
  // cohorts/retention, churn) lives here — IC-memo mapping, no separate tab.
  var cdd = DATA.cdd;
  var hasCdd = !!(cdd && cdd.concentration);
  var h = '';

  if (hasCdd && typeof renderAnswerFirstBar === 'function') {
    h += renderAnswerFirstBar(_afCddSignals(cdd), {title: 'Customer & Market Signals'});
  }

  h += '<div class="subtabs">';
  h += '<button class="subtab active" onclick="showSubtab(this,\'sub-kunden\')">Kunden</button>';
  if (hasCdd) {
    h += '<button class="subtab" onclick="showSubtab(this,\'sub-cohorts\')">Cohorts &amp; Retention</button>';
    h += '<button class="subtab" onclick="showSubtab(this,\'sub-churn\')">Churn</button>';
  }
  h += '<button class="subtab" onclick="showSubtab(this,\'sub-lieferanten\')">' + _wf_wireframeBadge().replace('margin-left:8px','margin-left:0') + ' Lieferanten</button>';
  h += '</div>';

  h += '<div id="sub-kunden" class="subcontent active">';
  if (hasCdd) {
    h += _cddSourceNote(cdd);
    h += _cddRenderCustomers(cdd);
  } else if (typeof renderCustomers === 'function') {
    h += renderCustomers();
  } else {
    h += '<div style="color:#94a3b8;font-size:13px">renderCustomers() not found.</div>';
  }
  h += '</div>';

  if (hasCdd) {
    h += '<div id="sub-cohorts" class="subcontent">' + _cddSourceNote(cdd) + _cddRenderCohorts(cdd) + '</div>';
    h += '<div id="sub-churn" class="subcontent">' + _cddSourceNote(cdd) + _cddRenderChurn(cdd) + '</div>';
  }

  h += '<div id="sub-lieferanten" class="subcontent">';
  h += renderSuppliers();
  h += '</div>';

  return h;
}

function renderMarket() {
  var h = '';

  h += '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:20px">';
  h += '<h2 style="margin:0;font-size:18px;color:#1e293b">Market &amp; Competition</h2>';
  h += _wf_wireframeBadge();
  h += '</div>';

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

  h += '<div class="overview-card" style="margin-bottom:16px">';
  h += _wf_sectionLabel('Marktpositionierung');

  var W = 320, H = 240;
  var cx = W / 2, cy = H / 2;
  var tx = cx + 40, ty = cy + 30;

  var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;max-width:' + W + 'px;display:block;margin:0 auto">';

  svg += '<rect x="0" y="0" width="' + cx + '" height="' + cy + '" fill="#fafbff" rx="0"/>';
  svg += '<rect x="' + cx + '" y="0" width="' + cx + '" height="' + cy + '" fill="#f0fdf4" rx="0"/>';
  svg += '<rect x="0" y="' + cy + '" width="' + cx + '" height="' + cy + '" fill="#fff7ed" rx="0"/>';
  svg += '<rect x="' + cx + '" y="' + cy + '" width="' + cx + '" height="' + cy + '" fill="#fef2f2" rx="0"/>';

  svg += '<line x1="' + cx + '" y1="10" x2="' + cx + '" y2="' + (H - 10) + '" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="4,3"/>';
  svg += '<line x1="10" y1="' + cy + '" x2="' + (W - 10) + '" y2="' + cy + '" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="4,3"/>';

  svg += '<text x="' + cx + '" y="8" text-anchor="middle" font-size="10" font-weight="600" fill="#64748b">Spezialist</text>';
  svg += '<text x="' + cx + '" y="' + (H - 2) + '" text-anchor="middle" font-size="10" font-weight="600" fill="#64748b">Generalist</text>';
  svg += '<text x="14" y="' + (cy + 1) + '" text-anchor="start" font-size="10" font-weight="600" fill="#64748b">Nische</text>';
  svg += '<text x="' + (W - 14) + '" y="' + (cy + 1) + '" text-anchor="end" font-size="10" font-weight="600" fill="#64748b">Scale</text>';

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

  svg += '<circle cx="' + tx + '" cy="' + ty + '" r="10" fill="#0891B2" opacity=".9"/>';
  svg += '<text x="' + (tx + 14) + '" y="' + (ty - 8) + '" font-size="10" font-weight="700" fill="#0891B2">Zielunternehmen</text>';
  svg += '<text x="' + (tx + 14) + '" y="' + (ty + 4) + '" font-size="9" fill="#64748b">(Platzhalter)</text>';

  svg += '</svg>';

  h += svg;
  h += '<div style="margin-top:8px;font-size:11px;color:#94a3b8;text-align:center;font-style:italic">Achsen-Einordnung nach RFI / Interviews zu kalibrieren.</div>';
  h += '</div>';

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
  h += '</div>';

  return h;
}
