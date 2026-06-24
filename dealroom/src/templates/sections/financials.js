// ─── Unified GuV (DR-M9) ─────────────────────────────────────────────────────

function renderUnifiedGuV() {
  const fin = DATA.financials || {};
  const unified = fin.unified_pnl || {};
  const subaccounts = fin.subaccounts || {};
  const years = fin.years || [];
  const hasAdj = fin.has_adjusted || false;
  const ctData = fin.ct_data || {};
  const ctCurrent = fin.ct_current || {};
  const ctPrior = fin.ct_prior || {};
  const ctHeader = fin.ct_header || 'CT';
  const ctHeaderCur = fin.ct_header_current || 'CT';
  const ctHeaderPri = fin.ct_header_prior || 'CT (PY)';
  const cagrData = fin.cagr || {};
  const cagrLabel = fin.cagr_label || 'CAGR';
  const proj2026 = fin.proj_2026 || null;
  const entities = fin.entities || ['consolidated'];
  const currentEntity = fin.current_entity || 'consolidated';
  const pnlComments = fin.pnl_row_comments || {};

  if (!years.length) {
    return '<div class="empty">No P&L data extracted yet.<br><code>python DEALROOM.py extract --deal '+DATA.deal.code_name+'</code></div>';
  }

  // Helper: extract best value from a cell object (adjusted preferred over raw)
  function getVal(cell) {
    if (!cell) return null;
    return cell.adjusted != null ? cell.adjusted : cell.raw;
  }

  // Helper: get cell from unified_pnl — structure is key -> year -> cell
  function getCell(key, yr) {
    const byKey = unified[key];
    if (!byKey) return null;
    return byKey[yr] || null;
  }

  const TEAL = '#0891B2';
  const TEAL_BG = '#e0f5fa';
  const ADJ_BG = '#fef3c7';

  const thS = 'background:'+TEAL+';color:#fff;padding:5px 8px;text-align:right;font-size:12px;white-space:nowrap;';
  const thL = thS + 'text-align:left;';
  const tdR = 'text-align:right;padding:5px 10px;font-size:13px;';
  const tdL = 'text-align:left;padding:5px 12px;font-size:13px;';
  const spS = 'width:16px;padding:0;border:none;';
  // border-left applied to first cell after each spacer for visual section dividers
  const secBorderL = 'border-left:2px solid #e2e8f0;';

  // Display years: up to 5 most recent + any 2026 actuals
  const dispYears = years.slice(-5);
  const show2026proj = proj2026 && !dispYears.includes('2026');
  // Spacer between actuals (≤2025) and budget (≥2026) within dispYears
  const budgetStartIdx = dispYears.findIndex(yr => parseInt(yr) >= 2026);
  const hasBudgetInDisp = budgetStartIdx > 0;

  // Total column count for colspan calculations
  function totalCols() {
    let n = 2 + dispYears.length; // label + years + first spacer
    if (hasBudgetInDisp) n++;     // actuals/budget spacer
    if (show2026proj) n += 2;     // 2026B col + spacer
    n += 3;                       // CT prior + CT current + spacer
    n += 3;                       // CAGR + DeltaCT + spacer
    n += 1;                       // comment
    return n;
  }

  // Pre-compute gross margin (revenue + cogs; cogs stored as negative so addition = subtraction)
  function computeGrossMargin(yr) {
    const rev = getVal(getCell('revenue', yr));
    const cogs = getVal(getCell('cogs_adj', yr));
    if (rev == null || cogs == null) return null;
    return rev + cogs;
  }

  // ── Entity dropdown ──────────────────────────────────────────────────────────
  let entityDropdown = '';
  if (entities.length > 1) {
    entityDropdown = '<div style="margin-bottom:6px;"><label style="font-size:11px;color:#555;margin-right:6px;">Entity:</label><select style="font-size:12px;padding:2px 6px;border:1px solid #ccc;border-radius:3px;" onchange="(function(sel){var ent=sel.value;fetch(\'api/financials?deal=\'+encodeURIComponent(DATA.deal.code_name)+\'&entity=\'+encodeURIComponent(ent)).then(function(r){return r.json();}).then(function(d){Object.assign(DATA.financials,d);document.getElementById(\'sub-guv\').innerHTML=renderUnifiedGuV();document.querySelectorAll(\'#sub-guv .expandable\').forEach(function(tr){tr.addEventListener(\'click\',function(){toggleExpandGuV(this);});});});return false;})(this)">';
    for (const ent of entities) {
      const label = ent === 'consolidated' ? 'Consolidated' : ent;
      const sel = ent === currentEntity ? ' selected' : '';
      entityDropdown += '<option value="'+esc(ent)+'"'+sel+'>'+esc(label)+'</option>';
    }
    entityDropdown += '</select></div>';
  }

  // ── Row definitions ──────────────────────────────────────────────────────────
  const ROWS = [
    {key:'revenue',         label:'Total Sales',          bold:false, teal:false, ebitBg:false, sign:1,  drillable:true},
    {key:'cogs_adj',        label:'Cost of Sales (adj.)', bold:false, teal:false, ebitBg:false, sign:-1, drillable:true, indent:true},
    {type:'computed',       ckey:'gross_margin',          label:'Gross Margin',   bold:true},
    {key:'personnel_adj',   label:'Personnel (adj.)',     bold:false, teal:false, ebitBg:false, sign:-1, drillable:true, indent:true},
    {key:'opex_net_adj',    label:'OPEX (adj.)',           bold:false, teal:false, ebitBg:false, sign:-1, drillable:true, indent:true},
    {type:'divider'},
    {key:'ebitda_adj',      label:'EBITDA (adj.)',         bold:true,  teal:true,  ebitBg:true,  sign:1},
    {type:'divider'},
    {key:'da_adj',          label:'D&A (adj.)',            bold:false, teal:false, ebitBg:false, sign:-1, indent:true},
    {key:'ebit_adj',        label:'EBIT (adj.)',           bold:true,  teal:true,  ebitBg:false,  sign:1},
  ];

  // Keys that have 2026 projection values
  const PROJ_KEYS = new Set(['revenue','cogs_adj','ebitda_adj']);

  // ── Header ───────────────────────────────────────────────────────────────────
  let h = '';
  if (!hasAdj) {
    h += '<div style="margin-bottom:8px;padding:4px 10px;background:#fef3c7;border:1px solid #f59e0b;border-radius:4px;font-size:11px;color:#92400e;display:inline-block">Raw data only — no model extracted</div>';
  }
  h += entityDropdown;

  h += '<div style="overflow-x:auto"><table id="guv-main-table" style="border-collapse:collapse;width:auto"><thead><tr>';
  h += '<th style="'+thL+'min-width:220px;">P&amp;L in €K</th>';
  for (let yi = 0; yi < dispYears.length; yi++) {
    if (yi === budgetStartIdx && hasBudgetInDisp) h += '<th style="'+spS+'background:'+TEAL+'"></th>';
    const suffix = parseInt(dispYears[yi]) >= 2026 ? 'B' : 'A';
    h += '<th style="'+thS+'min-width:75px;">'+dispYears[yi]+suffix+'</th>';
  }
  h += '<th style="'+spS+'background:'+TEAL+'"></th>';
  if (show2026proj) {
    h += '<th style="'+thS+'min-width:75px;'+secBorderL+'">2026B</th>';
    h += '<th style="'+spS+'background:'+TEAL+'"></th>';
  }
  h += '<th style="'+thS+'min-width:75px;'+secBorderL+'">'+esc(ctHeaderPri)+'</th>';
  h += '<th style="'+thS+'min-width:75px;">'+esc(ctHeaderCur)+'</th>';
  h += '<th style="'+spS+'background:'+TEAL+'"></th>';
  h += '<th style="'+thS+'min-width:75px;'+secBorderL+'">'+esc(cagrLabel)+'</th>';
  h += '<th style="'+thS+'min-width:65px;">Δ CT</th>';
  h += '<th style="'+spS+'background:'+TEAL+'"></th>';
  h += '<th style="'+thL+'min-width:220px;'+secBorderL+'">Notes</th>';
  h += '</tr></thead><tbody>';

  // ── Rows ─────────────────────────────────────────────────────────────────────
  let rowIdx = 0;
  const nc = totalCols();

  for (const item of ROWS) {
    // Divider
    if (item.type === 'divider') {
      h += '<tr><td colspan="'+nc+'" style="padding:3px;border:none;"></td></tr>';
      continue;
    }

    // Computed: Gross Margin
    if (item.type === 'computed' && item.ckey === 'gross_margin') {
      h += '<tr style="border-top:1px solid #333;">';
      h += '<td style="'+tdL+'font-weight:700;">'+item.label+'</td>';
      for (let yi = 0; yi < dispYears.length; yi++) {
        if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
        h += '<td style="'+tdR+'font-weight:700;">'+_fmtK(computeGrossMargin(dispYears[yi]))+'</td>';
      }
      h += '<td style="'+spS+'"></td>';
      if (show2026proj) {
        const pRev = proj2026['revenue'] != null ? proj2026['revenue'] : null;
        const pCogs = proj2026['cogs_adj'] != null ? proj2026['cogs_adj'] : null;
        const pGm = (pRev != null && pCogs != null) ? pRev + pCogs : null;
        h += '<td style="'+tdR+'font-weight:700;'+secBorderL+'">'+_fmtK(pGm)+'</td>';
        h += '<td style="'+spS+'"></td>';
      }
      const ctPriRev = ctPrior['revenue'] != null ? ctPrior['revenue'] : null;
      const ctPriCogs = ctPrior['cogs_adj'] != null ? ctPrior['cogs_adj'] : null;
      const ctPriGm = (ctPriRev != null && ctPriCogs != null) ? ctPriRev + ctPriCogs : null;
      h += '<td style="'+tdR+'font-weight:700;'+secBorderL+'">'+_fmtK(ctPriGm)+'</td>';
      const ctCurRev = ctCurrent['revenue'] != null ? ctCurrent['revenue'] : null;
      const ctCurCogs = ctCurrent['cogs_adj'] != null ? ctCurrent['cogs_adj'] : null;
      const ctCurGm = (ctCurRev != null && ctCurCogs != null) ? ctCurRev + ctCurCogs : null;
      h += '<td style="'+tdR+'font-weight:700;">'+_fmtK(ctCurGm)+'</td>';
      h += '<td style="'+spS+'"></td>';
      h += '<td style="'+tdR+'font-size:11px;color:#aaa;'+secBorderL+'">—</td>';
      const ctGmDelta = (ctCurGm != null && ctPriGm != null && ctPriGm !== 0) ? ((ctCurGm - ctPriGm) / Math.abs(ctPriGm) * 100).toFixed(1)+'%' : '—';
      h += '<td style="'+tdR+'font-size:11px;color:#555;">'+ctGmDelta+'</td>';
      h += '<td style="'+spS+'"></td>';
      h += '<td style="'+tdL+'font-size:11px;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'+secBorderL+'"></td>';
      h += '</tr>';
      continue;
    }

    // Normal data row
    const fw = item.bold ? 'font-weight:700;' : '';
    const tc = item.teal ? 'color:'+TEAL+';' : '';
    const bg = item.ebitBg ? 'background:'+TEAL_BG+';' : '';
    const topBorder = item.bold ? 'border-top:1px solid #333;' : '';
    const indentPad = item.indent ? 'padding-left:24px;' : '';
    const rid = 'ug-' + rowIdx++;
    const canDrill = item.drillable && currentEntity !== 'consolidated';
    const drillCls = canDrill ? 'expandable' : '';
    const drillCursor = canDrill ? 'cursor:pointer;' : '';
    const chevron = canDrill
      ? '<span class="guv-chevron" data-rid="'+rid+'" style="display:inline-block;width:14px;color:#aaa;font-size:10px;">▸</span>'
      : '';

    h += '<tr class="'+drillCls+'" data-rid="'+rid+'" data-guv="1" style="'+bg+topBorder+drillCursor+'">';
    h += '<td style="'+tdL+fw+tc+indentPad+'">'+chevron+item.label+'</td>';

    for (let yi = 0; yi < dispYears.length; yi++) {
      if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
      const yr = dispYears[yi];
      const cell = getCell(item.key, yr);
      const dispVal = getVal(cell);
      const v = dispVal != null ? (item.sign === -1 ? -Math.abs(dispVal) : dispVal) : null;
      const srcTip = cell ? (cell.source_adj || cell.source_raw || '') : '';
      h += '<td style="'+tdR+fw+tc+bg+'" title="'+esc(srcTip)+'">'+_fmtK(v)+'</td>';
    }
    h += '<td style="'+spS+'"></td>';

    if (show2026proj) {
      if (PROJ_KEYS.has(item.key)) {
        const pv = proj2026[item.key] != null ? proj2026[item.key] : null;
        const pDisp = pv != null ? (item.sign === -1 ? -Math.abs(pv) : pv) : null;
        h += '<td style="'+tdR+fw+tc+secBorderL+'">'+_fmtK(pDisp)+'</td>';
      } else {
        h += '<td style="'+tdR+'font-size:11px;color:#aaa;'+secBorderL+'">—</td>';
      }
      h += '<td style="'+spS+'"></td>';
    }

    const ctPriV = ctPrior[item.key] != null ? ctPrior[item.key] : null;
    const ctPriDisp = ctPriV != null ? (item.sign === -1 ? -Math.abs(ctPriV) : ctPriV) : null;
    h += '<td style="'+tdR+fw+tc+secBorderL+'">'+_fmtK(ctPriDisp)+'</td>';
    const ctCurV = ctCurrent[item.key] != null ? ctCurrent[item.key] : null;
    const ctCurDisp = ctCurV != null ? (item.sign === -1 ? -Math.abs(ctCurV) : ctCurV) : null;
    h += '<td style="'+tdR+fw+tc+'">'+_fmtK(ctCurDisp)+'</td>';
    h += '<td style="'+spS+'"></td>';

    const cagrHasKey = item.key in cagrData;
    const cagrV = cagrHasKey ? cagrData[item.key] : undefined;
    const cagrDisp = !cagrHasKey ? '—' : (cagrV != null ? (cagrV * 100).toFixed(1)+'%' : '—');
    h += '<td style="'+tdR+'font-size:11px;color:#555;'+secBorderL+'">'+cagrDisp+'</td>';
    const ctDeltaV = (ctCurV != null && ctPriV != null && ctPriV !== 0) ? ((ctCurV - ctPriV) / Math.abs(ctPriV) * 100).toFixed(1)+'%' : '—';
    h += '<td style="'+tdR+'font-size:11px;color:#555;">'+ctDeltaV+'</td>';
    h += '<td style="'+spS+'"></td>';

    const commentVal = pnlComments[item.key] || '';
    if (SERVE_MODE) {
      h += '<td style="'+tdL+'font-size:11px;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'+secBorderL+'" contenteditable="true" data-pnl-key="'+esc(item.key)+'" onblur="(function(el){var k=el.dataset.pnlKey;var v=el.innerText.trim();var allC={};document.querySelectorAll(\'[data-pnl-key]\').forEach(function(e){allC[e.dataset.pnlKey]=e.innerText.trim();});allC[k]=v;if(typeof _debouncedSave===\'function\'){_debouncedSave(\'pnl|\'+k,\'api/update\',{code_name:DATA.deal.code_name,field:\'pnl_row_comments\',value:JSON.stringify(allC)});}return false;})(this)">'+esc(commentVal)+'</td>';
    } else {
      h += '<td style="'+tdL+'font-size:11px;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#555;'+secBorderL+'">'+esc(commentVal)+'</td>';
    }
    h += '</tr>';

    // Drill-down rows (hidden) — only for non-consolidated entity views
    if (canDrill && subaccounts[item.key]) {
      const sub = subaccounts[item.key];
      // Group kontos by 2-digit prefix
      const prefixMap = {};
      for (const yr of dispYears) {
        if (!sub[yr]) continue;
        for (const s of sub[yr]) {
          const prefix = String(s.konto_nr).substring(0, 2);
          if (!prefixMap[prefix]) prefixMap[prefix] = {kontos: [], data: {}};
          if (!prefixMap[prefix].kontos.includes(s.konto_nr)) prefixMap[prefix].kontos.push(s.konto_nr);
          if (!prefixMap[prefix].data[yr]) prefixMap[prefix].data[yr] = {};
          prefixMap[prefix].data[yr][s.konto_nr] = s.value_k;
        }
      }
      for (const prefix of Object.keys(prefixMap).sort()) {
        const pdata = prefixMap[prefix];
        const pgid = rid + '-p' + prefix;
        const remCols = nc - 1 - dispYears.length - (hasBudgetInDisp ? 2 : 1); // after label + year cols + spacers

        // Layer 2: prefix group row
        h += '<tr class="detail-row guv-drill-l2" data-parent="'+rid+'" data-gid="'+pgid+'" style="cursor:pointer;" onclick="(function(tr){var gid=tr.dataset.gid;var kids=document.querySelectorAll(\'.guv-drill-l3[data-gparent=\\\'\'+gid+\'\\\']\');var exp=tr.classList.contains(\'expanded\');tr.classList.toggle(\'expanded\');kids.forEach(function(k){k.classList.toggle(\'visible\');});var ch=tr.querySelector(\'.guv-l2-chev\');if(ch)ch.textContent=exp?\'▸\':\'▾\';})(this)">';
        h += '<td style="'+tdL+'padding-left:24px;font-size:11px;color:#444;"><span class="guv-l2-chev" style="display:inline-block;width:14px;color:#aaa;font-size:10px;">▸</span>'+esc(prefix)+'xx</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const yr = dispYears[yi];
          let sum = null;
          if (pdata.data[yr]) {
            for (const k of pdata.kontos) {
              if (pdata.data[yr][k] != null) sum = (sum || 0) + pdata.data[yr][k];
            }
          }
          h += '<td style="'+tdR+'font-size:11px;color:#444;">'+_fmtK(sum)+'</td>';
        }
        for (let ci = 0; ci < remCols; ci++) h += '<td style="padding:0;font-size:11px;color:#aaa;">—</td>';
        h += '</tr>';

        // Layer 3: individual konto rows
        for (const konto of pdata.kontos.slice().sort()) {
          h += '<tr class="detail-row guv-drill-l3" data-parent="'+rid+'" data-gparent="'+pgid+'">';
          h += '<td style="'+tdL+'padding-left:48px;font-size:11px;color:#666;">'+esc(konto)+'</td>';
          for (let yi = 0; yi < dispYears.length; yi++) {
            if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
            const yr = dispYears[yi];
            const v = pdata.data[yr] && pdata.data[yr][konto] != null ? pdata.data[yr][konto] : null;
            h += '<td style="'+tdR+'font-size:11px;color:#666;">'+_fmtK(v)+'</td>';
          }
          for (let ci = 0; ci < remCols; ci++) h += '<td style="padding:0;font-size:11px;color:#aaa;">—</td>';
          h += '</tr>';
        }
      }
    }
  }

  // ── KPI rows (Fix 2+5): inside main tbody, same columns, 13px italic muted ─────
  const kpiStyle = 'font-style:italic;color:#888;font-size:13px;';
  const kpiTdR = 'text-align:right;padding:5px 10px;'+kpiStyle;
  const kpiTdL = 'text-align:left;padding:5px 12px;min-width:200px;'+kpiStyle;

  // Format KPI percent — parentheses for negatives
  function fmtPct(v) {
    if (v == null) return '-';
    const abs = Math.abs(v).toFixed(1) + '%';
    return v < 0 ? '('+abs+')' : abs;
  }

  const kpiRows = [
    {label:'Topline growth', fn: function(i) {
      if (i === 0) return null;
      const rev = getVal(getCell('revenue', dispYears[i]));
      const revP = getVal(getCell('revenue', dispYears[i-1]));
      return (rev != null && revP != null && revP !== 0) ? (rev - revP) / Math.abs(revP) * 100 : null;
    }},
    {label:'Gross margin %', fn: function(i) {
      const yr = dispYears[i];
      const gm = computeGrossMargin(yr);
      const rev = getVal(getCell('revenue', yr));
      return (gm != null && rev && rev !== 0) ? gm / rev * 100 : null;
    }},
    {label:'PEX %', fn: function(i) {
      const yr = dispYears[i];
      const pex = getVal(getCell('personnel_adj', yr));
      const rev = getVal(getCell('revenue', yr));
      return (pex != null && rev && rev !== 0) ? Math.abs(pex) / rev * 100 : null;
    }},
    {label:'OPEX %', fn: function(i) {
      const yr = dispYears[i];
      const opex = getVal(getCell('opex_net_adj', yr));
      const rev = getVal(getCell('revenue', yr));
      return (opex != null && rev && rev !== 0) ? Math.abs(opex) / rev * 100 : null;
    }},
    {label:'EBITDA margin', fn: function(i) {
      const yr = dispYears[i];
      const ebitda = getVal(getCell('ebitda_adj', yr));
      const rev = getVal(getCell('revenue', yr));
      return (ebitda != null && rev && rev !== 0) ? ebitda / rev * 100 : null;
    }},
    {label:'EBIT margin', fn: function(i) {
      const yr = dispYears[i];
      const ebit = getVal(getCell('ebit_adj', yr));
      const rev = getVal(getCell('revenue', yr));
      return (ebit != null && rev && rev !== 0) ? ebit / rev * 100 : null;
    }},
  ];

  // Divider before KPI rows
  h += '<tr><td colspan="'+nc+'" style="padding:3px;border:none;border-top:1px solid #e0e0e0;"></td></tr>';

  for (const kr of kpiRows) {
    h += '<tr>';
    h += '<td style="'+kpiTdL+'">'+kr.label+'</td>';
    for (let i = 0; i < dispYears.length; i++) {
      if (i === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
      const v = kr.fn(i);
      h += '<td style="'+kpiTdR+'">'+fmtPct(v)+'</td>';
    }
    h += '<td style="'+spS+'"></td>';
    if (show2026proj) {
      h += '<td style="'+kpiTdR+secBorderL+'">—</td>';
      h += '<td style="'+spS+'"></td>';
    }
    h += '<td style="'+kpiTdR+secBorderL+'">—</td>';
    h += '<td style="'+kpiTdR+'">—</td>';
    h += '<td style="'+spS+'"></td>';
    h += '<td style="'+kpiTdR+secBorderL+'">—</td>';
    h += '<td style="'+kpiTdR+'">—</td>';
    h += '<td style="'+spS+'"></td>';
    h += '<td style="'+kpiTdR+secBorderL+'"></td>';
    h += '</tr>';
  }

  // ── Adjustment Bridge (Fix 3+5): inline rows in main table, same columns ──────
  const bridgeRows = ROWS.filter(r => r.key && !r.type && dispYears.some(yr => {
    const cell = getCell(r.key, yr);
    return cell && cell.adjusted != null && cell.raw != null && cell.adjusted !== cell.raw;
  }));

  if (bridgeRows.length && hasAdj) {
    const bridgeRowId = 'guv-bridge-rows';
    // Toggle row (colspan full width)
    h += '<tr>';
    h += '<td colspan="'+nc+'" style="padding:0;border:none;">';
    h += '<div style="cursor:pointer;user-select:none;font-size:12px;font-weight:600;color:'+TEAL+';padding:6px 8px 2px;" onclick="(function(el){var rows=document.querySelectorAll(\'.guv-adj-row\');var isHid=rows.length&&rows[0].style.display===\'none\';rows.forEach(function(r){r.style.display=isHid?\'\':\' none\';});el.querySelector(\'.bridge-chev\').textContent=isHid?\'▾\':\'▸\';})(this)"><span class="bridge-chev">▸</span> Adjustments in €K</div>';
    h += '</td>';
    h += '</tr>';

    for (const row of bridgeRows) {
      const isOpex = row.key === 'opex_net_adj';
      const remColsAfterYears = nc - 1 - dispYears.length - 1; // label + year cols + first spacer accounted

      // Helper to build trailing empty cells after year columns (spacer + rest)
      function adjTrailing() {
        let t = '<td style="'+spS+'"></td>';
        if (show2026proj) { t += '<td style="text-align:right;padding:4px 8px;font-size:12px;color:#aaa;'+secBorderL+'">—</td><td style="'+spS+'"></td>'; }
        t += '<td style="text-align:right;padding:4px 8px;font-size:12px;color:#aaa;'+secBorderL+'">—</td>';
        t += '<td style="text-align:right;padding:4px 8px;font-size:12px;color:#aaa;">—</td>';
        t += '<td style="'+spS+'"></td>';
        t += '<td style="text-align:right;padding:4px 8px;font-size:12px;color:#aaa;'+secBorderL+'">—</td>';
        t += '<td style="text-align:right;padding:4px 8px;font-size:12px;color:#aaa;">—</td>';
        t += '<td style="'+spS+'"></td>';
        t += '<td style="'+secBorderL+'"></td>';
        return t;
      }

      if (isOpex) {
        h += '<tr class="guv-adj-row" style="display:none;">';
        h += '<td style="'+tdL+'font-size:12px;padding-left:20px;">Other OPEX (raw)</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const cell = getCell('other_opex_adj', dispYears[yi]);
          h += '<td style="'+tdR+'font-size:12px;">'+_fmtK(cell && cell.raw != null ? -Math.abs(cell.raw) : null)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';

        h += '<tr class="guv-adj-row" style="display:none;">';
        h += '<td style="'+tdL+'font-size:12px;padding-left:20px;">Other Income (raw)</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const cell = getCell('other_income_adj', dispYears[yi]);
          h += '<td style="'+tdR+'font-size:12px;">'+_fmtK(cell ? cell.raw : null)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';

        h += '<tr class="guv-adj-row" style="display:none;background:'+ADJ_BG+'">';
        h += '<td style="'+tdL+'font-size:12px;padding-left:20px;">Net adjustment</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const opC = getCell('other_opex_adj', dispYears[yi]);
          const opI = getCell('other_income_adj', dispYears[yi]);
          let delta = null;
          if (opC && opI) {
            const netAdj = (opC.adjusted != null ? opC.adjusted : opC.raw) - (opI.adjusted != null ? opI.adjusted : opI.raw);
            const netRaw = (opC.raw != null ? opC.raw : 0) - (opI.raw != null ? opI.raw : 0);
            delta = netAdj - netRaw;
          }
          const dS = delta != null ? (delta >= 0 ? 'color:#059669;' : 'color:#dc2626;') : '';
          h += '<td style="'+tdR+'font-size:12px;'+dS+'">'+_fmtK(delta)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';

        h += '<tr class="guv-adj-row" style="display:none;">';
        h += '<td style="'+tdL+'font-size:12px;font-weight:700;padding-left:20px;">OPEX (adj.)</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const cell = getCell(row.key, dispYears[yi]);
          const av = cell ? getVal(cell) : null;
          h += '<td style="'+tdR+'font-size:12px;font-weight:700;">'+_fmtK(av != null ? -Math.abs(av) : null)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';
      } else {
        h += '<tr class="guv-adj-row" style="display:none;">';
        h += '<td style="'+tdL+'font-size:12px;padding-left:20px;">'+esc(row.label)+' — Reported (raw)</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const cell = getCell(row.key, dispYears[yi]);
          const rv = cell && cell.raw != null ? (row.sign === -1 ? -Math.abs(cell.raw) : cell.raw) : null;
          h += '<td style="'+tdR+'font-size:12px;">'+_fmtK(rv)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';

        h += '<tr class="guv-adj-row" style="display:none;background:'+ADJ_BG+'">';
        h += '<td style="'+tdL+'font-size:12px;padding-left:20px;">Adjustment</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const cell = getCell(row.key, dispYears[yi]);
          let delta = null;
          if (cell && cell.adjusted != null && cell.raw != null) delta = cell.adjusted - cell.raw;
          const dS = delta != null ? (delta >= 0 ? 'color:#059669;' : 'color:#dc2626;') : '';
          h += '<td style="'+tdR+'font-size:12px;'+dS+'">'+_fmtK(delta)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';

        h += '<tr class="guv-adj-row" style="display:none;">';
        h += '<td style="'+tdL+'font-size:12px;font-weight:700;padding-left:20px;">'+esc(row.label)+' (adj.)</td>';
        for (let yi = 0; yi < dispYears.length; yi++) {
          if (yi === budgetStartIdx && hasBudgetInDisp) h += '<td style="'+spS+'"></td>';
          const cell = getCell(row.key, dispYears[yi]);
          const av = cell ? getVal(cell) : null;
          const disp = av != null ? (row.sign === -1 ? -Math.abs(av) : av) : null;
          h += '<td style="'+tdR+'font-size:12px;font-weight:700;">'+_fmtK(disp)+'</td>';
        }
        h += adjTrailing();
        h += '</tr>';
      }
      // Spacer between bridge items
      h += '<tr class="guv-adj-row" style="display:none;"><td colspan="'+nc+'" style="padding:3px;border:none;"></td></tr>';
    }
  }

  h += '</tbody></table></div>';

  return h;
}

// GuV rows: standard 15-line DATEV structure — labels resolved via L()
function getGuvStructure() { return [
  {key:'revenue', bold:false, sign:1},
  {key:'other_income', sign:1},
  {type:'divider'},
  {key:'cogs', sign:-1},
  {key:'personnel', sign:-1},
  {key:'da', sign:-1},
  {key:'other_opex', sign:-1},
  {type:'divider'},
  {key:'ebitda', bold:true, sign:1, summary:true},
  {key:'ebitda_margin', margin:true},
  {type:'divider'},
  {key:'ebit', bold:true, sign:1, summary:true},
  {key:'interest_income', sign:1},
  {key:'interest_expense', sign:-1},
  {key:'ebt', bold:true, sign:1, summary:true},
  {key:'tax', sign:-1},
  {type:'divider'},
  {key:'net_income', bold:true, sign:1, summary:true},
]; }

function getP(pnl,yr,key) { return pnl[yr]&&pnl[yr][key]?pnl[yr][key]:null; }
function getV(pnl,yr,key) { const e=getP(pnl,yr,key); return e?e.primary.value:null; }

function fmt(v) {
  if(v==null)return'-';
  const n=parseFloat(v);if(isNaN(n))return'-';
  const sign=n<0?'-':'';
  const abs=Math.abs(n);
  const parts=abs.toFixed(1).split('.');
  parts[0]=parts[0].replace(/\B(?=(\d{3})+(?!\d))/g,',');
  return sign+parts.join('.');
}

function renderGuV(pnl) {
  const years=Object.keys(pnl).filter(y=>y!=='unknown').sort();
  if(years.length===0) return '<div class="empty">No P&L data extracted yet.<br><code>python DEALROOM.py extract --deal '+DATA.deal.code_name+'</code></div>';

  const GUV=getGuvStructure();
  let h='<table class="fin-table"><thead><tr><th style="min-width:260px">'+L('guv_header')+'</th>';
  for(const yr of years) h+='<th>'+yr+'</th>';
  h+='</tr></thead><tbody>';

  let rowIdx=0;
  for(const item of GUV) {
    if(item.type==='divider') { h+='<tr><td colspan="'+(years.length+1)+'" style="padding:2px;border:none"></td></tr>'; continue; }
    if(item.margin) {
      h+='<tr class="margin-row"><td>'+L(item.key)+'</td>';
      for(const yr of years) {
        const rev=getV(pnl,yr,'revenue'); const eb=getV(pnl,yr,'ebitda');
        h+='<td>'+(eb!=null&&rev?((eb/rev*100).toFixed(1)+'%'):'-')+'</td>';
      }
      h+='</tr>'; continue;
    }

    const cls=[];
    if(item.summary)cls.push('summary-row');
    cls.push('expandable');
    const rid='guv-'+rowIdx++;
    h+='<tr class="'+cls.join(' ')+'" data-rid="'+rid+'">';
    const style=item.bold?'font-weight:700':'';
    h+='<td style="'+style+'">'+L(item.key)+'</td>';

    for(const yr of years) {
      const cell=getP(pnl,yr,item.key);
      if(cell) {
        const v=item.sign===-1?-Math.abs(cell.primary.value):cell.primary.value;
        const conflict=cell.primary.conflict;
        const tdCls=conflict?' class="conflict-cell"':'';
        const src=cell.primary.source||'';
        const ttip=conflict&&cell.primary.conflict_note
          ?' title="CONFLICT: '+esc(cell.primary.conflict_note)+'\nSource: '+esc(src)+'"'
          :' title="'+esc(src)+'"';
        h+='<td'+tdCls+ttip+'>'+fmt(v)+'</td>';
      } else { h+='<td>-</td>'; }
    }
    h+='</tr>';

    // Detail rows (sources) — hidden by default
    const allSources=[];
    for(const yr of years) {
      const cell=getP(pnl,yr,item.key);
      if(cell) for(const s of cell.sources) if(!allSources.includes(s.source)) allSources.push(s.source);
    }
    if(allSources.length>1) {
      for(const src of allSources) {
        h+='<tr class="detail-row" data-parent="'+rid+'">';
        h+='<td>'+esc(src)+'</td>';
        for(const yr of years) {
          const cell=getP(pnl,yr,item.key);
          if(cell) {
            const match=cell.sources.find(s=>s.source===src);
            h+='<td>'+(match?fmt(item.sign===-1?-Math.abs(match.value):match.value):'-')+'</td>';
          } else { h+='<td>-</td>'; }
        }
        h+='</tr>';
      }
    }
  }
  h+='</tbody></table>';
  return h;
}

function toggleExpand(tr) {
  const rid=tr.dataset.rid;
  if(!rid)return;
  const details=document.querySelectorAll('.detail-row[data-parent="'+rid+'"]');
  tr.classList.toggle('expanded');
  details.forEach(d=>d.classList.toggle('visible'));
}

// Unified GuV drill-down: Layer 1 → Layer 2 (prefix groups); Layer 3 opened by group row inline handler
function toggleExpandGuV(tr) {
  const rid = tr.dataset.rid;
  if (!rid) return;
  const isExpanded = tr.classList.contains('expanded');
  tr.classList.toggle('expanded');
  // Update chevron
  const chev = tr.querySelector('.guv-chevron');
  if (chev) chev.textContent = isExpanded ? '▸' : '▾';
  // Show/hide Layer 2 prefix-group rows (not L3 — those are toggled by L2 row handler)
  const l2rows = document.querySelectorAll('.guv-drill-l2[data-parent="'+rid+'"]');
  l2rows.forEach(function(l2) {
    l2.classList.toggle('visible', !isExpanded);
    if (isExpanded) {
      // Collapse open L2 groups when collapsing L1
      l2.classList.remove('expanded');
      const gid = l2.dataset.gid;
      if (gid) document.querySelectorAll('.guv-drill-l3[data-gparent="'+gid+'"]').forEach(function(l3){ l3.classList.remove('visible'); });
      const l2ch = l2.querySelector('.guv-l2-chev');
      if (l2ch) l2ch.textContent = '▸';
    }
  });
}

// ─── Bilanz ──────────────────────────────────────────────────────────────────

function renderBilanz(balance) {
  const years=Object.keys(balance).filter(y=>y!=='unknown').sort();
  if(years.length===0) return '<div class="empty">No balance sheet data extracted yet.</div>';

  // Net-debt relevant positions marked for future flagging
  const items=[
    {key:'total_assets',bold:true},
    {key:'fixed_assets'},
    {key:'current_assets'},
    {key:'cash', netDebtRelevant:true},
    {key:'receivables'},
    {type:'divider'},
    {key:'equity',bold:true},
    {key:'provisions'},
    {key:'debt_lt', netDebtRelevant:true},
    {key:'debt_st', netDebtRelevant:true},
    {key:'net_debt',bold:true, netDebtRelevant:true},
  ];

  let h='<table class="fin-table"><thead><tr><th style="min-width:280px">'+L('bilanz_header')+'</th>';
  for(const yr of years) h+='<th>'+yr+'</th>';
  h+='</tr></thead><tbody>';

  let rowIdx=0;
  for(const item of items) {
    if(item.type==='divider'){h+='<tr><td colspan="'+(years.length+1)+'" style="padding:2px;border:none"></td></tr>';continue;}
    const cls=[];
    if(item.bold)cls.push('summary-row');
    cls.push('expandable');
    const rid='bal-'+rowIdx++;
    h+='<tr class="'+cls.join(' ')+'" data-rid="'+rid+'">';
    const ndTag=item.netDebtRelevant?' <span style="color:var(--info);font-size:9px" title="Net debt relevant">ND</span>':'';
    h+='<td style="'+(item.bold?'font-weight:700':'')+'">'+L(item.key)+ndTag+'</td>';
    for(const yr of years) {
      const cell=balance[yr]&&balance[yr][item.key]?balance[yr][item.key]:null;
      if(cell) {
        const tdCls=cell.conflict?' class="conflict-cell"':'';
        h+='<td'+tdCls+' title="'+esc(cell.source||'')+'">'+fmt(cell.value)+'</td>';
      } else { h+='<td>-</td>'; }
    }
    h+='</tr>';

    // Detail rows for balance — show source per value (same as P&L expand)
    const allSources=[];
    for(const yr of years) {
      const cell=balance[yr]&&balance[yr][item.key];
      if(cell&&cell.source&&!allSources.includes(cell.source)) allSources.push(cell.source);
    }
    if(allSources.length>1) {
      for(const src of allSources) {
        h+='<tr class="detail-row" data-parent="'+rid+'"><td>'+esc(src)+'</td>';
        for(const yr of years) {
          const cell=balance[yr]&&balance[yr][item.key];
          h+='<td>'+(cell&&cell.source===src?fmt(cell.value):'-')+'</td>';
        }
        h+='</tr>';
      }
    }
  }
  h+='</tbody></table>';
  return h;
}

// ─── Model section (DR-M7: Interactive Valuation Model) ─────────────────────

let _modelCtx = null;  // cached model context from server
let _modelDebounce = null;
const TEAL = '#1D7080';

function renderModel() {
  _modelCtx = DATA.model_context || null;
  if(!_modelCtx || (!_modelCtx.years.length && !_modelCtx.waterfall)) {
    return '<div class="empty">No model data available.<br><code>python DEALROOM.py extract --deal '+DATA.deal.code_name+'</code></div>';
  }

  let h='<div class="subtabs">';
  h+='<button class="subtab active" onclick="showSubtab(this,\'sub-guv\')">Adj. GuV</button>';
  h+='<button class="subtab" onclick="showSubtab(this,\'sub-netdebt\')">Net Debt</button>';
  h+='<button class="subtab" onclick="showSubtab(this,\'sub-bewertung\')">Bewertung</button>';
  h+='</div>';

  h+='<div id="sub-guv" class="subcontent active">'+renderAdjGuV()+'</div>';
  h+='<div id="sub-netdebt" class="subcontent">'+renderNetDebt()+'</div>';
  h+='<div id="sub-bewertung" class="subcontent">'+renderBewertungTab()+'</div>';
  return h;
}

function _fmtK(v) {
  if(v==null) return '-';
  if(v<0) return '('+Math.abs(v).toLocaleString('de-DE',{maximumFractionDigits:0})+')';
  return v.toLocaleString('de-DE',{maximumFractionDigits:0});
}

function _fmtPct(v) {
  if(v==null) return '-';
  return v.toFixed(1)+'%';
}

function _fmtMult(v) {
  if(!v) return '-';
  return v.toFixed(1)+'x';
}

function _modelInput(name, val, width, onChange) {
  if(!SERVE_MODE) return '<span>'+_fmtK(val)+'</span>';
  const v = val!=null ? val : '';
  return '<input type="number" step="any" style="width:'+width+'px;text-align:right;background:#e8f5e9;border:1px solid #ccc;padding:2px 4px" value="'+v+'" oninput="'+onChange+'">';
}

function _postModelUpdate(params) {
  if(!SERVE_MODE || !_modelCtx) return;
  clearTimeout(_modelDebounce);
  _modelDebounce = setTimeout(()=>{
    const domain = _modelCtx.params.domain || '';
    const scenario = _modelCtx.params.scenario_name || 'base';
    // Merge into current params
    const merged = Object.assign({}, _modelCtx.params, params);
    fetch('api/model-params', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({domain, scenario, params: merged})
    }).then(r=>r.json()).then(ctx=>{
      _modelCtx = ctx;
      DATA.model_context = ctx;
      // Re-render active sub-tab
      const guv = document.getElementById('sub-guv');
      const nd = document.getElementById('sub-netdebt');
      const bew = document.getElementById('sub-bewertung');
      if(guv && guv.classList.contains('active')) guv.innerHTML = renderAdjGuV();
      if(nd && nd.classList.contains('active')) nd.innerHTML = renderNetDebt();
      if(bew && bew.classList.contains('active')) bew.innerHTML = renderBewertungTab();
    }).catch(e=>console.error('Model update failed:', e));
  }, 300);
}

// ─── Adj. GuV sub-tab ────────────────────────────────────────────────────────

function renderAdjGuV() {
  const ctx = _modelCtx;
  if(!ctx) return '';
  const adj = ctx.adj_pnl || {};
  const summary = adj.summary || {};
  const kpis = adj.kpis || {};
  const cagr = adj.cagr || {};
  const years = ctx.years || [];
  if(!years.length) return '<div class="empty">No P&L data available.</div>';

  // Column count: label + years + CAGR + Comment
  const nCols = years.length + 3;
  const thStyle = 'background:'+TEAL+';color:#fff;padding:5px 8px;text-align:right;font-size:11px;white-space:nowrap';
  const tdR = 'text-align:right;padding:3px 8px;font-size:12px;';
  const tdL = 'text-align:left;padding:3px 8px;font-size:12px;';

  let h='<table style="border-collapse:collapse;width:100%"><thead><tr>';
  h+='<th style="'+thStyle+';text-align:left;min-width:200px">P&L in \u20acK</th>';
  for(const y of years) h+='<th style="'+thStyle+';min-width:70px">'+y+'</th>';
  h+='<th style="'+thStyle+';min-width:60px">CAGR</th>';
  h+='<th style="'+thStyle+';text-align:left;min-width:120px">Comment</th>';
  h+='</tr></thead><tbody>';

  const rows = [
    {key:'total_sales', label:'Total Sales', bold:true},
    {key:'cogs_adj', label:'Cost of sales (adj.)'},
    {key:'gross_margin', label:'Gross margin', bold:true},
    {key:'pex_adj', label:'Personnel Expenses (adj.)'},
    {key:'opex_adj', label:'OPEX (adj.)'},
    {key:'opin_adj', label:'OPIN (adj.)'},
    {key:'ebitda_adj', label:'EBITDA (adj.)', bold:true, teal:true},
    {key:'da', label:'D&A'},
    {key:'ebit_adj', label:'EBIT (adj.)', bold:true, teal:true},
  ];

  for(const r of rows) {
    const fw = r.bold ? 'font-weight:700;' : '';
    const tc = r.teal ? 'color:'+TEAL+';' : '';
    h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+';'+fw+tc+'">'+r.label+'</td>';
    for(const y of years) {
      const v = summary[y] ? summary[y][r.key] : null;
      h+='<td style="'+tdR+';'+fw+tc+'">'+_fmtK(v)+'</td>';
    }
    const c = cagr[r.key];
    h+='<td style="'+tdR+';">'+(c!=null?_fmtPct(c*100):'-')+'</td>';
    h+='<td style="'+tdL+';color:#888;font-size:11px"></td>';
    h+='</tr>';
  }

  // KPI rows — italic, muted
  h+='<tr><td colspan="'+nCols+'" style="padding:2px;border:none"></td></tr>';
  const kpiRows = [
    {key:'topline_growth', label:'Topline growth'},
    {key:'gross_margin_pct', label:'Gross margin %'},
    {key:'pex_pct', label:'PEX %'},
    {key:'opex_pct', label:'OPEX %'},
    {key:'ebitda_margin_pct', label:'EBITDA margin'},
    {key:'ebit_margin_pct', label:'EBIT margin'},
  ];
  for(const r of kpiRows) {
    h+='<tr style="font-style:italic;color:#888"><td style="'+tdL+';font-style:italic;color:#888">'+r.label+'</td>';
    for(const y of years) {
      const v = kpis[y] ? kpis[y][r.key] : null;
      h+='<td style="'+tdR+';font-style:italic;color:#888">'+_fmtPct(v)+'</td>';
    }
    h+='<td></td><td></td></tr>';
  }

  h+='</tbody></table>';

  // GF Salary panel
  const p = ctx.params || {};
  h+='<div style="margin-top:16px;padding:10px;background:#f5f5f5;border-radius:4px;font-size:12px">';
  h+='<div style="font-weight:700;margin-bottom:6px;">GF-Gehalt Anpassung</div>';
  h+='<div style="display:flex;gap:14px;flex-wrap:wrap">';
  h+='<label>Aktuelles Gehalt/Monat (\u20acK): '+_modelInput('gf_old',p.gf_old_salary_monthly_k,60,"_postModelUpdate({gf_old_salary_monthly_k:+this.value})")+'</label>';
  h+='<label>Faktor: '+_modelInput('gf_bf',p.gf_benefit_factor,50,"_postModelUpdate({gf_benefit_factor:+this.value})")+'</label>';
  h+='<label>Neues Gehalt GF (\u20acK/J): '+_modelInput('gf_new',p.gf_new_base_k,60,"_postModelUpdate({gf_new_base_k:+this.value})")+'</label>';
  h+='<label>Tantieme: '+_modelInput('gf_t',p.gf_tantieme_k,60,"_postModelUpdate({gf_tantieme_k:+this.value})")+'</label>';
  h+='<label>Sozialabg.: '+_modelInput('gf_s',p.gf_sozialabgaben_pct!=null?p.gf_sozialabgaben_pct*100:18,50,"_postModelUpdate({gf_sozialabgaben_pct:+this.value/100})")+'%</label>';
  h+='</div></div>';

  // Adjustment detail — delegated to standalone helper
  h += renderAdjDetail(adj, summary, years, thStyle, tdR, tdL);

  return h;
}

// ─── EBIT Adjustment Detail — standalone helper ───────────────────────────────
// Renders adjustment positions + commentary table.
// Called from renderAdjGuV() and the Financials GuV tab slide.
// adj      = ctx.adj_pnl  (contains adjustments_detail + adjustments_total)
// summary  = adj.summary  (per-year adjusted P&L for subtotal rows)
// years    = ctx.years
// thStyle/tdR/tdL — optional style overrides; defaults applied when omitted.

function renderAdjDetail(adj, summary, years, thStyle, tdR, tdL) {
  const _TEAL = '#1D7080';
  thStyle = thStyle || ('background:'+_TEAL+';color:#fff;padding:5px 8px;font-size:11px;');
  tdR = tdR || 'text-align:right;padding:3px 8px;font-size:12px;';
  tdL = tdL || 'text-align:left;padding:3px 8px;font-size:12px;';

  const adjDetail = (adj && adj.adjustments_detail) || {};
  const adjTotal  = (adj && adj.adjustments_total)  || {};
  summary = summary || {};
  years   = years   || [];
  if(!Object.keys(adjDetail).length) return '';

  // Human-readable label per category key — covers English (backend) + German (legacy)
  const CAT_LABEL = {
    revenue:'Revenue',      umsatz:'Umsatz',
    cogs:'Cost of Sales',   materialkosten:'Materialkosten',
    personnel:'Personnel',  personalkosten:'Personalkosten',
    opex:'OPEX',
    opin:'OPIN',
  };
  // Map category key -> adj_pnl summary sub-key for the adjusted subtotal row
  const CAT_TO_SUMMARY = {
    revenue:'total_sales',    umsatz:'total_sales',
    cogs:'cogs_adj',          materialkosten:'cogs_adj',
    personnel:'pex_adj',      personalkosten:'pex_adj',
    opex:'opex_adj',
    opin:'opin_adj',
  };

  // Preferred display order (English keys first, then German aliases for legacy data)
  const catOrder = ['revenue','umsatz','cogs','materialkosten','personnel','personalkosten','opex','opin'];
  const catKeys = catOrder.filter(c=>adjDetail[c])
    .concat(Object.keys(adjDetail).filter(c=>!catOrder.includes(c)));

  let h='<div style="margin-top:16px">';
  h+='<table style="border-collapse:collapse;width:100%"><thead><tr>';
  h+='<th style="'+thStyle+';text-align:left;min-width:200px">Adjustments in €K</th>';
  for(const y of years) h+='<th style="'+thStyle+';min-width:70px">'+y+'</th>';
  h+='<th style="'+thStyle+';text-align:left;min-width:120px">Comment</th>';
  h+='</tr></thead><tbody>';

  for(const cat of catKeys) {
    const items = adjDetail[cat];
    if(!items || !items.length) continue;
    const catLabel = CAT_LABEL[cat] || (cat.charAt(0).toUpperCase()+cat.slice(1));

    // Category header row
    h+='<tr style="background:#f5f5f5;border-bottom:1px solid #ddd">';
    h+='<td style="'+tdL+';font-weight:700">'+catLabel+'</td>';
    for(const y of years) {
      const total = items.reduce((s,it)=>s+((it.amounts_by_year&&it.amounts_by_year[y])||0),0);
      h+='<td style="'+tdR+';font-weight:700">'+_fmtK(total!=null?total:null)+'</td>';
    }
    h+='<td style="'+tdL+'"></td></tr>';

    // Individual adjustment items — indented, description + comment
    for(const item of items) {
      h+='<tr style="border-bottom:1px solid #f0f0f0">';
      h+='<td style="'+tdL+';padding-left:20px;font-size:11px;color:#555">'+esc(item.description||'')+'</td>';
      for(const y of years) {
        const v = item.amounts_by_year ? item.amounts_by_year[y] : null;
        h+='<td style="'+tdR+';font-size:11px;color:#555">'+_fmtK(v!=null?v:null)+'</td>';
      }
      h+='<td style="'+tdL+';color:#888;font-size:11px">'+esc(item.comment||'')+'</td></tr>';
    }

    // Adjusted subtotal row
    const summaryKey = CAT_TO_SUMMARY[cat] || null;
    const adjCatLabel = catLabel + ' (adj.)';
    h+='<tr style="border-bottom:1px solid #ccc">';
    h+='<td style="'+tdL+';font-weight:700">'+adjCatLabel+'</td>';
    for(const y of years) {
      const v = summaryKey && summary[y] ? summary[y][summaryKey] : null;
      h+='<td style="'+tdR+';font-weight:700">'+_fmtK(v)+'</td>';
    }
    h+='<td style="'+tdL+'"></td></tr>';
  }

  // Adjustments total footer
  h+='<tr><td colspan="'+(years.length+2)+'" style="padding:2px;border:none"></td></tr>';
  h+='<tr style="border-top:2px solid #333">';
  h+='<td style="'+tdL+';font-weight:700;font-style:italic">Adjustments total</td>';
  for(const y of years) {
    const t = adjTotal[y] ? adjTotal[y].total : 0;
    h+='<td style="'+tdR+';font-weight:700">'+_fmtK(t)+'</td>';
  }
  h+='<td></td></tr>';

  h+='</tbody></table></div>';
  return h;
}

// ─── Net Debt sub-tab ────────────────────────────────────────────────────────

function renderNetDebt() {
  const ctx = _modelCtx;
  if(!ctx) return '';
  const items = (ctx.params||{}).net_debt_items_json || [];
  const nd = (ctx.params||{}).net_debt || 0;
  const thStyle = 'background:'+TEAL+';color:#fff;padding:5px 8px;font-size:11px;';
  const tdR = 'text-align:right;padding:3px 8px;font-size:12px;';
  const tdL = 'text-align:left;padding:3px 8px;font-size:12px;';
  const tdKonto = 'text-align:right;padding:3px 8px;font-size:12px;color:#555;min-width:48px';

  // Figure out date label from items or fallback
  const dateLabel = (items.length && items[0].date) ? items[0].date : '';

  let h='<table style="border-collapse:collapse;width:100%"><thead><tr>';
  h+='<th style="'+thStyle+';text-align:right;min-width:48px"></th>';
  h+='<th style="'+thStyle+';text-align:left;min-width:260px">Net Cash Berechnung</th>';
  h+='<th style="'+thStyle+';text-align:right;min-width:90px">'+esc(dateLabel)+'</th>';
  h+='<th style="'+thStyle+';text-align:left;min-width:160px">Kommentar</th>';
  h+='</tr></thead><tbody>';

  if(!items || items.length === 0) {
    h+='<tr><td colspan="4" style="padding:12px;color:var(--text-muted)">No net debt items defined. ';
    if(SERVE_MODE) h+='Use the inputs below to add items.';
    else h+='Start the dashboard in --serve mode to add items.';
    h+='</td></tr>';
  } else {
    let cashTotal = 0, debtTotal = 0;
    const cashItems = items.filter(i=>i.type==='cash');
    const debtItems = items.filter(i=>i.type==='debt');

    // Cash items — no section header, just list them
    for(const it of cashItems) {
      const amt = it.amount||0;
      cashTotal += amt;
      const isBetrieb = it.betriebsnotwendig === true;
      const rowStyle = isBetrieb ? 'background:#ffffcc' : '';
      h+='<tr style="border-bottom:1px solid #f0f0f0;'+rowStyle+'">';
      h+='<td style="'+tdKonto+'">'+esc(it.konto||'')+'</td>';
      h+='<td style="'+tdL+'">'+esc(it.name||'')+'</td>';
      h+='<td style="'+tdR+'">'+_fmtK(amt)+'</td>';
      h+='<td style="'+tdL+';color:#888;font-size:11px">'+esc(it.comment||'')+'</td>';
      h+='</tr>';
    }
    // Cash subtotal
    h+='<tr style="border-bottom:1px solid #aaa">';
    h+='<td></td>';
    h+='<td style="'+tdL+';font-weight:700">Liquide Mittel</td>';
    h+='<td style="'+tdR+';font-weight:700">'+_fmtK(cashTotal)+'</td>';
    h+='<td></td></tr>';

    // Gap row
    h+='<tr><td colspan="4" style="padding:3px;border:none"></td></tr>';

    // Debt items — no section header, just list them
    for(const it of debtItems) {
      const amt = it.amount||0;
      debtTotal += amt;
      h+='<tr style="border-bottom:1px solid #f0f0f0">';
      h+='<td style="'+tdKonto+'">'+esc(it.konto||'')+'</td>';
      h+='<td style="'+tdL+'">'+esc(it.name||'')+'</td>';
      h+='<td style="'+tdR+'">'+_fmtK(amt)+'</td>';
      h+='<td style="'+tdL+';color:#888;font-size:11px">'+esc(it.comment||'')+'</td>';
      h+='</tr>';
    }
    // Debt subtotal
    h+='<tr style="border-bottom:1px solid #aaa">';
    h+='<td></td>';
    h+='<td style="'+tdL+';font-weight:700">Finanzverbindlichkeiten</td>';
    h+='<td style="'+tdR+';font-weight:700">'+_fmtK(debtTotal)+'</td>';
    h+='<td></td></tr>';

    // Net Cash total
    h+='<tr style="border-top:2px solid #555">';
    h+='<td></td>';
    h+='<td style="'+tdL+';font-weight:700">Net Cash (Debt)</td>';
    h+='<td style="'+tdR+';font-weight:700">'+_fmtK(cashTotal+debtTotal)+'</td>';
    h+='<td></td></tr>';
  }

  h+='</tbody></table>';

  // Net debt override
  h+='<div style="margin-top:12px;font-size:12px">';
  h+='<label>Net Debt Override (\u20acK): '+_modelInput('nd',nd,80,"_postModelUpdate({net_debt:+this.value})")+'</label>';
  h+='<span style="color:var(--text-muted);margin-left:8px">(positive = net cash, negative = net debt)</span>';
  h+='</div>';

  return h;
}

// ─── Bewertung sub-tab ───────────────────────────────────────────────────────

function renderBewertungTab() {
  const ctx = _modelCtx;
  if(!ctx) return '';
  const wf = ctx.waterfall || {};
  const p = ctx.params || {};
  const em = ctx.earnout_matrix || [];
  const years = ctx.years || [];
  const summary = (ctx.adj_pnl||{}).summary || {};
  const offers = ctx.offer_history || [];
  const thStyle = 'background:'+TEAL+';color:#fff;padding:5px 8px;font-size:11px;white-space:nowrap';
  const tdR = 'text-align:right;padding:3px 8px;font-size:12px;';
  const tdL = 'text-align:left;padding:3px 8px;font-size:12px;';

  let h = '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">';

  // ── LEFT: Unternehmensbewertung ──
  h+='<div style="flex:0 0 auto;min-width:340px">';
  h+='<table style="border-collapse:collapse;font-size:12px;width:100%">';
  h+='<thead><tr>';
  h+='<th style="'+thStyle+';text-align:left;min-width:180px">Unternehmensbewertung</th>';
  for(const y of years) h+='<th style="'+thStyle+';min-width:60px">'+y+'</th>';
  h+='<th style="'+thStyle+';min-width:70px">Valuation</th>';
  h+='</tr></thead><tbody>';

  // Adj. Gesamtleistung
  h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+'">Adj. Gesamtleistung</td>';
  for(const y of years) h+='<td style="'+tdR+';color:'+TEAL+'">'+_fmtK(summary[y]?summary[y].total_sales:null)+'</td>';
  h+='<td style="'+tdR+'">'+_fmtK(ctx.ebitda_basis)+'</td></tr>';

  // Adj. EBIT
  h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+'">Adj. EBIT</td>';
  for(const y of years) h+='<td style="'+tdR+';color:'+TEAL+'">'+_fmtK(summary[y]?summary[y].ebit_adj:null)+'</td>';
  h+='<td style="'+tdR+'">'+_fmtK(ctx.ebit_basis)+'</td></tr>';

  // Adj. EBITDA
  h+='<tr style="border-bottom:1px solid #e0e0e0;font-weight:700"><td style="'+tdL+'">Adj. EBITDA</td>';
  for(const y of years) h+='<td style="'+tdR+';color:'+TEAL+'">'+_fmtK(summary[y]?summary[y].ebitda_adj:null)+'</td>';
  h+='<td style="'+tdR+'">'+_fmtK(ctx.ebitda_basis)+'</td></tr>';

  // % growth row (italic, EBITDA YoY growth)
  h+='<tr style="border-bottom:1px solid #e0e0e0;font-style:italic;color:#888"><td style="'+tdL+';font-style:italic;color:#888">% growth</td>';
  for(let i=0;i<years.length;i++) {
    const y=years[i], yPrev=years[i-1];
    const cur=summary[y]?summary[y].ebitda_adj:null;
    const prev=yPrev&&summary[yPrev]?summary[yPrev].ebitda_adj:null;
    const pct=(cur!=null&&prev!=null&&prev!==0)?((cur-prev)/Math.abs(prev)*100):null;
    h+='<td style="'+tdR+';font-style:italic;color:#888">'+(pct!=null?_fmtPct(pct):'-')+'</td>';
  }
  h+='<td style="'+tdR+';font-style:italic;color:#888">'+_fmtPct(wf.ebitda_growth_pct!=null?wf.ebitda_growth_pct:null)+'</td></tr>';

  // Rep. EBIT
  h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+'">Rep. EBIT</td>';
  for(const y of years) h+='<td style="'+tdR+'">'+_fmtK(summary[y]?summary[y].ebit_adj:null)+'</td>';
  h+='<td style="'+tdR+'">'+_fmtK(ctx.ebit_basis)+'</td></tr>';

  h+='<tr><td colspan="'+(years.length+2)+'" style="padding:3px;border:none"></td></tr>';

  // EV Waterfall rows — label spans year cols, then value, then multiple
  const ySpan = years.length;
  function wfRow(label, val, mult, bold, tealBg) {
    const fw = bold ? 'font-weight:700;' : '';
    const bg = tealBg ? 'background:'+TEAL+';color:#fff;' : '';
    return '<tr style="border-bottom:1px solid #e0e0e0;'+bg+'">'
      +'<td style="'+tdL+';'+fw+bg+'" colspan="1">'+label+'</td>'
      +(years.length > 0 ? '<td colspan="'+ySpan+'" style="'+tdR+'"></td>' : '')
      +'<td style="'+tdR+';'+fw+bg+'">'+_fmtK(val)+'</td>'
      +'</tr>';
  }

  h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+';font-weight:700">EV at closing</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+';font-weight:700">'+_fmtK(wf.ev_at_closing)+'</td></tr>';

  h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+'">EV anticipated Earn-Out</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_fmtK(wf.ev_anticipated)+'</td></tr>';

  h+='<tr style="border-bottom:1px solid #e0e0e0;background:'+TEAL+';color:#fff"><td style="'+tdL+';font-weight:700;color:#fff">Total EV incl. Super-Earn-Out</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+';font-weight:700;color:#fff">'+_fmtK(wf.ev_total)+'</td></tr>';

  h+='<tr style="border-bottom:1px solid #e0e0e0"><td style="'+tdL+'">+/- Net Cash | (Net Debt)</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_modelInput('nd2',p.net_debt,65,"_postModelUpdate({net_debt:+this.value})")+'</td></tr>';

  h+='<tr style="border-bottom:2px solid #333;font-weight:700"><td style="'+tdL+';font-weight:700">Equity Value</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+';font-weight:700">'+_fmtK(wf.equity_value)+'</td></tr>';

  // Structure breakdown
  h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';padding-left:18px">At Closing ('+_fmtPct(wf.cash_pct)+')</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_modelInput('cash',p.cash_at_closing,65,"_postModelUpdate({cash_at_closing:+this.value})")+'</td></tr>';

  h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';padding-left:18px">Vendor Loan ('+_fmtPct(wf.vendor_loan_pct)+')</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_modelInput('vl',p.vendor_loan,65,"_postModelUpdate({vendor_loan:+this.value})")+'</td></tr>';

  h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';padding-left:18px">Earn-Out ant. ('+_fmtPct(wf.earnout_pct)+')</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_modelInput('eo',p.earnout_anticipated,65,"_postModelUpdate({earnout_anticipated:+this.value})")+'</td></tr>';

  h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';padding-left:18px">Super Earn-Out</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_fmtK(wf.super_earnout)+'</td></tr>';

  // EBITDA basis + Multiple input row
  h+='<tr style="background:#e8f5e9"><td style="'+tdL+';font-size:11px">EBITDA Basis (\u20acK)</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_modelInput('eb',p.ebitda_basis_override||ctx.ebitda_basis,65,"_postModelUpdate({ebitda_basis_override:+this.value})")+'</td></tr>';
  h+='<tr style="background:#e8f5e9"><td style="'+tdL+';font-size:11px">Multiple</td>';
  h+=(years.length>0?'<td colspan="'+ySpan+'" style="'+tdR+'"></td>':'');
  h+='<td style="'+tdR+'">'+_modelInput('mult',p.multiple,65,"_postModelUpdate({multiple:+this.value})")+'</td></tr>';

  h+='</tbody></table></div>';

  // ── CENTER: Offer History ──
  if(offers.length > 0) {
    h+='<div style="flex:0 0 auto;min-width:200px">';
    h+='<table style="border-collapse:collapse;font-size:12px">';
    h+='<thead><tr>';
    h+='<th style="'+thStyle+';text-align:left;min-width:90px">Offer History</th>';
    h+='<th style="'+thStyle+';min-width:60px">Multiple</th>';
    h+='<th style="'+thStyle+';min-width:70px">EV</th>';
    h+='</tr></thead><tbody>';
    for(const o of offers) {
      const isAsk = (o.type||'').toLowerCase().includes('ask') || (o.type||'').toLowerCase().includes('seller');
      const rowStyle = isAsk ? 'background:#fff3cd' : '';
      h+='<tr style="border-bottom:1px solid #e0e0e0;'+rowStyle+'">';
      h+='<td style="'+tdL+'">'+(o.label||o.type||'')+'</td>';
      h+='<td style="'+tdR+'">'+_fmtMult(o.multiple)+'</td>';
      h+='<td style="'+tdR+'">'+_fmtK(o.ev)+'</td>';
      h+='</tr>';
    }
    h+='</tbody></table></div>';
  }

  // ── RIGHT: Earn-Out Scenario Matrix ──
  h+='<div style="flex:1;min-width:360px">';
  const basisYr = years.length ? years[years.length-1] : '';
  h+='<div style="margin-bottom:6px;font-size:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">';
  h+='<label style="font-size:11px">EBIT Anchor: '+_modelInput('ea',p.earnout_ebit_anchor||ctx.ebit_basis,58,"_postModelUpdate({earnout_ebit_anchor:+this.value})")+'</label>';
  h+='<label style="font-size:11px">Step: '+_modelInput('es',p.earnout_step||25,48,"_postModelUpdate({earnout_step:+this.value})")+'</label>';
  if(SERVE_MODE) {
    h+='<button onclick="_addTier()" style="padding:2px 6px;font-size:11px;cursor:pointer">+ Tier</button>';
    h+='<button onclick="_removeTier()" style="padding:2px 6px;font-size:11px;cursor:pointer">- Tier</button>';
  }
  h+='</div>';

  if(em.length > 0) {
    const nScen = em.length;
    h+='<table style="border-collapse:collapse;font-size:11px;width:100%"><thead><tr>';
    h+='<th style="'+thStyle+';text-align:left;min-width:140px">Szenarioanalyse Earn-out'+(basisYr?' '+basisYr:'')+'</th>';
    for(const s of em) h+='<th style="'+thStyle+';text-align:right;min-width:55px">'+_fmtK(s.ebit)+'</th>';
    h+='</tr></thead><tbody>';

    // Adj. EBIT
    h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';font-size:11px">Adj. EBIT</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px">'+_fmtK(s.ebit)+'</td>';
    h+='</tr>';

    // Adj. EBITDA
    h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';font-size:11px">Adj. EBITDA</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px">'+_fmtK(s.ebitda)+'</td>';
    h+='</tr>';

    // % vs base EBITDA — italic, highlight if available
    h+='<tr style="border-bottom:1px solid #e8e8e8;font-style:italic;color:#888"><td style="'+tdL+';font-size:11px;font-style:italic;color:#888">% vs. '+(basisYr||'base')+' EBITDA</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px;font-style:italic;color:#888">'+_fmtPct(s.vs_base_pct)+'</td>';
    h+='</tr>';

    h+='<tr><td colspan="'+(nScen+1)+'" style="padding:2px;border:none"></td></tr>';

    // Multiple
    h+='<tr style="border-bottom:1px solid #e8e8e8;font-weight:700"><td style="'+tdL+';font-size:11px">Multiple</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px">'+_fmtMult(s.multiple)+'</td>';
    h+='</tr>';

    // Kaufpreis
    h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';font-size:11px">Kaufpreis</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px">'+_fmtK(s.kaufpreis)+'</td>';
    h+='</tr>';

    // Enterprise Value
    h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';font-size:11px">Enterprise Value</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px">'+_fmtK(s.ev)+'</td>';
    h+='</tr>';

    // Net debt
    h+='<tr style="border-bottom:1px solid #e8e8e8;color:#888"><td style="'+tdL+';font-size:11px;color:#888">+/- Net Cash | (Net Debt)</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px;color:#888">'+_fmtK(p.net_debt||0)+'</td>';
    h+='</tr>';

    h+='<tr><td colspan="'+(nScen+1)+'" style="padding:2px;border:none"></td></tr>';

    // Fixed payment
    h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';font-size:11px">Fixed Payment</td>';
    for(const s of em) h+='<td style="'+tdR+';font-size:11px">'+_fmtK(s.fixed_payment)+'</td>';
    h+='</tr>';

    // Earn-out (editable — green bg)
    const tiers = (p.earnout_tiers_json || []);
    h+='<tr style="border-bottom:1px solid #e8e8e8;background:#e8f5e9;font-weight:700"><td style="'+tdL+';font-size:11px">Earn-Out</td>';
    for(let i=0;i<em.length;i++) {
      if(SERVE_MODE) {
        h+='<td style="'+tdR+';font-size:11px;background:#e8f5e9"><input type="number" step="any" style="width:52px;text-align:right;background:#e8f5e9;border:1px solid #aaa;padding:1px 3px;font-size:11px" value="'+(tiers[i]||0)+'" oninput="_updateTier('+i+',+this.value)"></td>';
      } else {
        h+='<td style="'+tdR+';font-size:11px;background:#e8f5e9">'+_fmtK(em[i].earnout)+'</td>';
      }
    }
    h+='</tr>';

    // Bottom total row: Earn-Out dargestellt im Angebot (+ Verkäuferdarlehen)
    const vl = p.vendor_loan || 0;
    h+='<tr style="border-top:2px solid #555"><td colspan="'+(nScen+1)+'" style="padding:3px 8px;font-size:10px;color:#888;font-style:italic">Earn-Out dargestellt im Angebot (+ Verk\u00e4uferdarlehen)</td></tr>';
    h+='<tr style="border-bottom:1px solid #e8e8e8"><td style="'+tdL+';font-size:11px;font-weight:700">EO + VL Total</td>';
    for(let i=0;i<em.length;i++) {
      const earnout = em[i].earnout || 0;
      h+='<td style="'+tdR+';font-size:11px;font-weight:700">'+_fmtK(earnout+vl)+'</td>';
    }
    h+='</tr>';

    h+='</tbody></table>';
  } else {
    h+='<div class="empty" style="padding:12px">No earn-out tiers defined.</div>';
  }
  h+='</div>'; // close right panel

  h+='</div>';  // close top flex container

  // ── Pro-Forma EBIT Bridge (full width below) ──
  const pf = ctx.proforma || [];
  if(pf.length > 0 && pf.some(r=>r.ebit)) {
    h+='<div style="margin-top:20px;width:100%">';
    h+='<table style="border-collapse:collapse;font-size:12px;max-width:480px"><thead><tr>';
    h+='<th style="'+thStyle+';text-align:left;min-width:220px">Nebenrechnung f\u00fcr EBIT-Bestimmung</th>';
    for(const r of pf) h+='<th style="'+thStyle+';min-width:70px">'+r.year+'</th>';
    h+='</tr></thead><tbody>';

    const pfRows = [
      {key:'ergebnis_nach_steuern', label:'Ergebnis nach Steuern'},
      {key:'steuern', label:'+ Steuern'},
      {key:'zinsaufwand', label:'+ Zinsaufwand'},
      {key:'zinsertraege', label:'- Zinsertr\u00e4ge'},
      {key:'sonst_neutral_ertrag', label:'+ Sonstiger neutraler Ertrag'},
      {key:'sonst_neutral_aufwand', label:'- Sonstiger Neutraler Aufwand'},
      {key:'ebit', label:'EBIT', bold:true},
      {type:'gap'},
      {key:'gf_salary', label:'- Neues Gehalt M\u00fchlan'},
      {key:'nebenkosten', label:'- Nebenkosten (17%)'},
      {key:'ebit_proforma', label:'EBIT Pro-Forma', bold:true},
    ];

    for(const pr of pfRows) {
      if(pr.type==='gap'){h+='<tr><td colspan="'+(pf.length+1)+'" style="padding:2px;border:none"></td></tr>';continue;}
      const fw = pr.bold ? 'font-weight:700;' : '';
      const bb = pr.bold ? 'border-top:1px solid #555;' : 'border-bottom:1px solid #e8e8e8;';
      h+='<tr style="'+bb+'"><td style="'+tdL+';'+fw+'">'+pr.label+'</td>';
      for(const r of pf) {
        const v = r[pr.key];
        h+='<td style="'+tdR+';'+fw+'">'+_fmtK(v)+'</td>';
      }
      h+='</tr>';
    }

    // GF salary inputs
    h+='<tr><td style="padding:6px 8px" colspan="'+(pf.length+1)+'">';
    h+='<label style="font-size:11px">Neues Gehalt GF (\u20acK/J): '+_modelInput('pf_gf',p.proforma_gf_salary_k,70,"_postModelUpdate({proforma_gf_salary_k:+this.value})")+'</label>';
    h+=' <label style="font-size:11px;margin-left:12px">NK %: '+_modelInput('pf_nk',p.proforma_nebenkosten_pct!=null?p.proforma_nebenkosten_pct*100:17,50,"_postModelUpdate({proforma_nebenkosten_pct:+this.value/100})")+'</label>';
    h+='</td></tr>';

    h+='</tbody></table></div>';
  }

  return h;
}

function _addTier() {
  if(!SERVE_MODE || !_modelCtx) return;
  const domain = _modelCtx.params.domain || '';
  const scenario = _modelCtx.params.scenario_name || 'base';
  fetch('api/model-add-tier',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({domain,scenario})
  }).then(r=>r.json()).then(ctx=>{
    _modelCtx=ctx; DATA.model_context=ctx;
    document.getElementById('sub-bewertung').innerHTML=renderBewertungTab();
  });
}

function _removeTier() {
  if(!SERVE_MODE || !_modelCtx) return;
  const domain = _modelCtx.params.domain || '';
  const scenario = _modelCtx.params.scenario_name || 'base';
  fetch('api/model-remove-tier',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({domain,scenario})
  }).then(r=>r.json()).then(ctx=>{
    _modelCtx=ctx; DATA.model_context=ctx;
    document.getElementById('sub-bewertung').innerHTML=renderBewertungTab();
  });
}

function _updateTier(index, value) {
  if(!SERVE_MODE || !_modelCtx) return;
  const tiers = [...(_modelCtx.params.earnout_tiers_json || [])];
  tiers[index] = value;
  _postModelUpdate({earnout_tiers_json: tiers});
}

