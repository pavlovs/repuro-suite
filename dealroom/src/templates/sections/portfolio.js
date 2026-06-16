// ─── Portfolio ───────────────────────────────────────────────────────────────

// Harvey ball SVG: 0=empty, 1=quarter, 2=half, 3=three-quarter, 4=full (global — used by cycleFit too)
function harveyBall(v) {
  const r=9, cx=11, cy=11;
  const empty='#22D3EE', fill='#0891B2';
  const n = Math.max(0, Math.min(4, parseInt(v)||0));
  if (n===0) return `<svg width="22" height="22" style="vertical-align:middle"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${empty}" stroke-width="1.5"/></svg>`;
  if (n===4) return `<svg width="22" height="22" style="vertical-align:middle"><circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}"/></svg>`;
  const frac = n/4;
  const sa = -Math.PI/2;
  const ea = sa + frac*2*Math.PI;
  const x1 = (cx+r*Math.cos(sa)).toFixed(3), y1 = (cy+r*Math.sin(sa)).toFixed(3);
  const x2 = (cx+r*Math.cos(ea)).toFixed(3), y2 = (cy+r*Math.sin(ea)).toFixed(3);
  const la = frac>0.5?1:0;
  return `<svg width="22" height="22" style="vertical-align:middle"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${fill}" stroke-width="1.5"/><path d="M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${la} 1 ${x2} ${y2} Z" fill="${fill}"/></svg>`;
}

function renderPortfolio() {
  document.getElementById('portfolioView').style.display='block';
  document.getElementById('dealView').style.display='none';
  document.getElementById('cockpit').style.display='none';
  document.getElementById('sidebar').style.display='none';

  const deals = DATA.deals || [];
  const editable = SERVE_MODE && !INVESTOR_MODE;

  function numCell(v) {
    const disp = v!=null ? Number(v).toFixed(1) : null;
    return `<td style="text-align:center;font-weight:700">${disp!=null ? disp : '—'}</td>`;
  }
  function mulCell(v) {
    const disp = v!=null ? Number(v).toFixed(1)+'x' : null;
    return `<td style="text-align:center;font-weight:700">${disp!=null ? disp : '—'}</td>`;
  }
  // Stage dropdown color map (background colors from .stage-* classes)
  const STAGE_COLORS = {
    meeting_concluded:{bg:'#f59e0b',color:'#000'},valuation_rfi:{bg:'#3b82f6',color:'#fff'},
    indicative_offer:{bg:'#6366f1',color:'#fff'},loi_signed:{bg:'#8b5cf6',color:'#fff'},
    due_diligence:{bg:'#059669',color:'#fff'},contract_negotiation:{bg:'#0d9488',color:'#fff'},
    closed:{bg:'#065f46',color:'#fff'},on_hold:{bg:'#6b7280',color:'#fff'},dead:{bg:'#ef4444',color:'#fff'}
  };
  function stageDropdownCell(currentStage, code) {
    const sc = STAGE_COLORS[currentStage]||{bg:'#e2e8f0',color:'#000'};
    const label = STAGE_LABELS[currentStage]||currentStage||'—';
    const dotHtml = `<span class="stage-dot" style="background:${sc.bg}"></span>`;
    if (!editable) {
      return `<td class="stage-cell" style="text-align:center"><span style="display:inline-flex;align-items:center;gap:5px;color:#334155">${dotHtml}${label}</span></td>`;
    }
    return `<td class="stage-cell" style="text-align:center"><div class="stage-dropdown-wrap" data-code="${code}"><span class="stage-dropdown-trigger" data-stage="${currentStage}" style="display:inline-flex;align-items:center;gap:5px;color:#334155;background:none">${dotHtml}${label}</span><div class="stage-dropdown-menu">${ALL_STAGES.map(s=>{const c=STAGE_COLORS[s]||{bg:'#e2e8f0',color:'#000'};return `<div class="stage-dropdown-option" data-value="${s}"><span class="stage-dot" style="background:${c.bg}"></span>${STAGE_LABELS[s]}</div>`;}).join('')}</div></div></td>`;
  }
  function commentCell(text, code) {
    const lines = (text||'').split('\n').filter(l=>l.trim());
    let inner = '';
    if (lines.length > 0) {
      inner = '<ul class="comment-bullets">' + lines.map(l=>'<li>'+esc(l)+'</li>').join('') + '</ul>';
    }
    if (editable) {
      return `<td class="text-cell"><div class="comment-cell-wrap" data-field="status_override" data-code="${code}" tabindex="0">${inner}</div></td>`;
    }
    return `<td class="text-cell">${inner || '<span style="color:#94a3b8;font-style:italic">—</span>'}</td>`;
  }

  // Stage filter constants
  const ACTIVE_STAGES = ['meeting_concluded','valuation_rfi','indicative_offer','loi_signed','due_diligence','contract_negotiation'];
  const ALL_STAGES = ['meeting_concluded','valuation_rfi','indicative_offer','loi_signed','due_diligence','contract_negotiation','closed','on_hold','dead'];
  const STAGE_LABELS = {
    meeting_concluded:'Meeting Concluded',valuation_rfi:'Valuation & RFI',indicative_offer:'NBO Sent',
    loi_signed:'LOI Signed',due_diligence:'Due Diligence',contract_negotiation:'Contract Negotiation',
    closed:'Closed',on_hold:'On Hold',dead:'Dead'
  };

  // Read filter from URL hash
  let selectedStages = new Set(ACTIVE_STAGES);
  const hashMatch = location.hash.match(/stage=([^&]+)/);
  if (hashMatch) {
    const fromHash = hashMatch[1].split(',').filter(s => ALL_STAGES.includes(s));
    if (fromHash.length > 0) selectedStages = new Set(fromHash);
  }

  let h = '<div class="portfolio-section-title">Live Deal Portfolio';
  if (editable) h += ' <span class="save-indicator" id="saveInd"></span>';
  h += '</div>';

  // Stage filter bar
  h += '<div class="stage-filter"><label>Stage:</label>';
  const allActiveOn = ACTIVE_STAGES.every(s => selectedStages.has(s)) && !['closed','on_hold','dead'].some(s => selectedStages.has(s));
  h += `<span class="filter-btn${allActiveOn?' active':''}" data-filter="all-active">All Active</span>`;
  const allOn = ALL_STAGES.every(s => selectedStages.has(s));
  h += `<span class="filter-btn${allOn?' active':''}" data-filter="all">All</span>`;
  for (const s of ALL_STAGES) {
    h += `<span class="filter-btn${selectedStages.has(s)?' active':''}" data-filter="${s}">${STAGE_LABELS[s]}</span>`;
  }
  h += '</div>';

  h += '<div class="portfolio-wrap"><table class="portfolio-table"><colgroup>';
  h += '<col class="c-code"><col class="c-rev"><col class="c-ebitda"><col class="c-pct"><col class="c-emp"><col class="c-desc"><col class="c-ev"><col class="c-mul"><col class="c-stage"><col class="c-comment">';
  h += '</colgroup><thead><tr>';
  h += '<th class="c">Deal</th><th class="c">Rev.</th><th class="c">EBITDA</th>';
  h += '<th class="c">EBITDA<br>margin</th><th class="c"># empl.</th>';
  h += '<th style="text-align:left">Description</th>';
  h += '<th class="c">EV<sup>1</sup></th><th class="c">Multiple<sup>2</sup></th><th class="c">Stage</th><th style="text-align:left">Comment</th>';
  h += '</tr></thead><tbody>';

  let sumRev=0, sumEbitda=0, sumEmp=0, nRev=0, nEbitda=0, nEmp=0;

  for (const d of deals) {
    const code = d.code_name;
    const pctDisp = d.ebitda_pct!=null ? Number(d.ebitda_pct).toFixed(0)+'%' : '—';
    const empDisp = d.employees!=null ? d.employees : '—';

    if (selectedStages.has(d.deal_stage)) {
      if (d.rev_m!=null){sumRev+=Number(d.rev_m);nRev++;}
      if (d.ebitda_m!=null){sumEbitda+=Number(d.ebitda_m);nEbitda++;}
      if (d.employees!=null){sumEmp+=Number(d.employees);nEmp++;}
    }

    h += `<tr data-stage="${d.deal_stage}"${selectedStages.has(d.deal_stage)?'':' style="display:none"'}>`;
    h += `<td class="code-cell" onclick="loadDeal('${code}')">${code}</td>`;
    h += numCell(d.rev_m, null);
    h += numCell(d.ebitda_m, null);
    h += `<td style="text-align:center">${pctDisp}</td>`;
    h += `<td style="text-align:center">${empDisp}</td>`;
    h += `<td class="text-cell"><div class="clamp3">${esc(d.description||'')}</div></td>`;
    h += numCell(d.ev_m, d.ev_m_note);
    h += mulCell(d.multiple, d.multiple_note);
    h += stageDropdownCell(d.deal_stage, code);
    h += commentCell(d.status_text, code);
    h += '</tr>';
  }

  const sumRevDisp = nRev>0 ? sumRev.toFixed(1) : '—';
  const sumEbitdaDisp = nEbitda>0 ? sumEbitda.toFixed(1) : '—';
  h += '</tbody><tfoot><tr>';
  h += `<td style="text-align:center">SUM</td><td style="text-align:center">${sumRevDisp}</td><td style="text-align:center">${sumEbitdaDisp}</td>`;
  h += `<td style="text-align:center">—</td><td style="text-align:center">${nEmp>0?sumEmp:'—'}</td>`;
  h += '<td></td><td style="text-align:center">—</td><td style="text-align:center">—</td><td></td><td></td>';
  h += '</tr></tfoot></table>';
  h += '<div style="font-size:11px;color:#6b7280;padding:4px 8px;line-height:1.6">';
  h += 'All financial figures in M€. All numbers are preliminary.&nbsp;&nbsp;|&nbsp;&nbsp;<sup>1</sup> EV = Enterprise Value incl. anticipated earn-out, based on latest model where available.&nbsp;&nbsp;|&nbsp;&nbsp;<sup>2</sup> EV / adj. EBITDA 2025tje.';
  h += '</div></div>';

  // Other pipeline comments (new section)
  const pipLines = (DATA.portfolio_pipeline_comments||'').split('\n').filter(l=>l.trim());
  let pipInner = '';
  if (pipLines.length > 0) {
    pipInner = '<ul class="comment-bullets">' + pipLines.map(l=>'<li>'+esc(l)+'</li>').join('') + '</ul>';
  }
  h += '<div class="op-quadrant" style="margin-top:20px">';
  h += '<div class="op-quadrant-header">Other pipeline comments</div>';
  if (editable) {
    h += '<div class="op-quadrant-body" id="portfolioPipelineComments" contenteditable="true" style="min-height:80px">' + (pipInner || '') + '</div>';
  } else {
    h += '<div class="op-quadrant-body" id="portfolioPipelineComments" style="min-height:80px">' + (pipInner || '<span style="color:#94a3b8;font-style:italic">No pipeline comments.</span>') + '</div>';
  }
  h += '</div>';

  // Other updates (renamed from Other Comments)
  const pcLines = (DATA.portfolio_comments||'').split('\n').filter(l=>l.trim());
  let pcInner = '';
  if (pcLines.length > 0) {
    pcInner = '<ul class="comment-bullets">' + pcLines.map(l=>'<li>'+esc(l)+'</li>').join('') + '</ul>';
  }
  h += '<div class="op-quadrant" style="margin-top:12px">';
  h += '<div class="op-quadrant-header">Other updates</div>';
  if (editable) {
    h += '<div class="op-quadrant-body" id="portfolioComments" contenteditable="true" style="min-height:80px">' + (pcInner || '') + '</div>';
  } else {
    h += '<div class="op-quadrant-body" id="portfolioComments" style="min-height:80px">' + (pcInner || '<span style="color:#94a3b8;font-style:italic">No portfolio update notes.</span>') + '</div>';
  }
  h += '</div>';

  document.getElementById('portfolioView').innerHTML = h;

  // Add placeholder behavior for portfolioComments
  if (editable) {
    const pcEl = document.getElementById('portfolioComments');
    if (pcEl && !pcEl.textContent.trim()) {
      pcEl.innerHTML = '<span style="color:#94a3b8;font-style:italic">Click to add portfolio update notes…</span>';
    }
    if (pcEl) {
      pcEl.addEventListener('focus', () => {
        if (pcEl.querySelector('span[style]') && !pcEl.textContent.replace('Click to add portfolio update notes…','').trim()) {
          pcEl.innerHTML = '';
        }
      });
      pcEl.addEventListener('blur', () => {
        const text = pcEl.innerText.trim();
        if (!text) {
          pcEl.innerHTML = '<span style="color:#94a3b8;font-style:italic">Click to add portfolio update notes…</span>';
        }
        const ind = document.getElementById('saveInd');
        if (ind) { ind.textContent='Saving…'; ind.className='save-indicator saving'; }
        fetch('api/portfolio-comments',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({value:text})})
        .then(r=>{
          if(ind){
            if(r.ok){ind.textContent='Saved ✓';ind.className='save-indicator saved';}
            else{ind.textContent='Error';ind.className='save-indicator error';}
            setTimeout(()=>{ind.className='save-indicator';},2500);
          }
        }).catch(()=>{if(ind){ind.textContent='Error';ind.className='save-indicator error';}});
      });
    }
  }

  // Pipeline comments blur handler
  const pipEl = document.getElementById('portfolioPipelineComments');
  if (pipEl && pipEl.contentEditable === 'true') {
    pipEl.addEventListener('blur', function() {
      const lines = [];
      pipEl.querySelectorAll('li').forEach(li => { const t=li.textContent.trim(); if(t) lines.push(t); });
      if (lines.length === 0) { const raw = pipEl.innerText.trim(); if (raw) lines.push(...raw.split('\n').filter(l=>l.trim())); }
      const text = lines.join('\n');
      fetch('api/portfolio-comments', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({key:'portfolio_pipeline_comments', value:text})
      });
      if (lines.length > 0) {
        pipEl.innerHTML = '<ul class="comment-bullets">' + lines.map(l => '<li>'+esc(l)+'</li>').join('') + '</ul>';
      }
    });
  }

  if (editable) {
    const ind = document.getElementById('saveInd');

    // Comment cell (bullet) handlers
    document.querySelectorAll('#portfolioView .comment-cell-wrap').forEach(wrap => {
      wrap.addEventListener('focus', () => {
        // Convert bullets to editable text lines
        const lis = wrap.querySelectorAll('li');
        if (lis.length > 0) {
          const lines = Array.from(lis).map(li => li.textContent);
          wrap.innerHTML = '';
          wrap.setAttribute('contenteditable','true');
          // Use div lines for editing
          lines.forEach(line => {
            const div = document.createElement('div');
            div.textContent = line;
            wrap.appendChild(div);
          });
        } else {
          wrap.setAttribute('contenteditable','true');
          if (!wrap.textContent.trim()) wrap.innerHTML = '';
        }
      });
      wrap.addEventListener('blur', () => {
        const field = wrap.dataset.field, code = wrap.dataset.code;
        // Collect text from child divs or raw text
        let lines;
        const divs = wrap.querySelectorAll('div');
        if (divs.length > 0) {
          lines = Array.from(divs).map(d => d.textContent.trim()).filter(l => l);
        } else {
          lines = wrap.innerText.split('\n').map(l => l.trim()).filter(l => l);
        }
        const value = lines.join('\n');
        // Re-render as bullets
        if (lines.length > 0) {
          wrap.innerHTML = '<ul class="comment-bullets">' + lines.map(l => '<li>'+esc(l)+'</li>').join('') + '</ul>';
        } else {
          wrap.innerHTML = '';
        }
        wrap.removeAttribute('contenteditable');
        if (!field || !code) return;
        ind.textContent='Saving…'; ind.className='save-indicator saving';
        fetch('api/update',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({code_name:code,field,value})})
        .then(r=>{
          if(r.ok){ind.textContent='Saved ✓';ind.className='save-indicator saved';}
          else{ind.textContent='Error';ind.className='save-indicator error';}
          setTimeout(()=>{ind.className='save-indicator';},2500);
        }).catch(()=>{ind.textContent='Error';ind.className='save-indicator error';});
      });
      wrap.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();wrap.blur();}});
    });

    // Custom stage dropdown handlers
    document.querySelectorAll('#portfolioView .stage-dropdown-trigger').forEach(trigger => {
      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        // Close all other open menus
        document.querySelectorAll('.stage-dropdown-menu.open').forEach(m => m.classList.remove('open'));
        const menu = trigger.nextElementSibling;
        menu.classList.toggle('open');
      });
    });
    document.querySelectorAll('#portfolioView .stage-dropdown-option').forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        const wrap = opt.closest('.stage-dropdown-wrap');
        const code = wrap.dataset.code;
        const value = opt.dataset.value;
        const trigger = wrap.querySelector('.stage-dropdown-trigger');
        const sc = STAGE_COLORS[value]||{bg:'#e2e8f0',color:'#000'};
        trigger.innerHTML = `<span class="stage-dot" style="background:${sc.bg}"></span>${STAGE_LABELS[value]||value}`;
        trigger.dataset.stage = value;
        opt.closest('.stage-dropdown-menu').classList.remove('open');
        // Update the row's data-stage for filtering
        wrap.closest('tr').dataset.stage = value;
        ind.textContent='Saving…'; ind.className='save-indicator saving';
        fetch('api/update',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({code_name:code,field:'deal_stage',value})})
        .then(r=>{
          if(r.ok){ind.textContent='Saved ✓';ind.className='save-indicator saved';}
          else{ind.textContent='Error';ind.className='save-indicator error';}
          setTimeout(()=>{ind.className='save-indicator';},2500);
        }).catch(()=>{ind.textContent='Error';ind.className='save-indicator error';});
      });
    });
    // Close dropdown when clicking outside
    document.addEventListener('click', () => {
      document.querySelectorAll('.stage-dropdown-menu.open').forEach(m => m.classList.remove('open'));
    });
  }

  // Stage filter click handlers
  document.querySelectorAll('#portfolioView .filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const f = btn.dataset.filter;
      if (f === 'all-active') {
        selectedStages = new Set(ACTIVE_STAGES);
      } else if (f === 'all') {
        selectedStages = new Set(ALL_STAGES);
      } else {
        if (selectedStages.has(f)) selectedStages.delete(f);
        else selectedStages.add(f);
      }
      // Persist to URL hash
      location.hash = 'stage=' + [...selectedStages].join(',');
      // Re-render with updated filter
      renderPortfolio();
    });
  });
}

function cycleFit(td, code) {
  const cur = parseInt(td.dataset.fit) || 0;
  const next = (cur + 1) % 5;
  td.dataset.fit = next;
  td.innerHTML = harveyBall(next);
  if (!SERVE_MODE) return;
  const ind = document.getElementById('saveInd');
  if (ind) { ind.textContent='Saving…'; ind.className='save-indicator saving'; }
  fetch('api/update', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({code_name: code, field: 'strategic_fit', value: String(next)})})
  .then(r => {
    if (!ind) return;
    if (r.ok) { ind.textContent='Saved ✓'; ind.className='save-indicator saved'; }
    else { ind.textContent='Error'; ind.className='save-indicator error'; }
    setTimeout(() => { ind.className='save-indicator'; }, 2500);
  }).catch(() => { if (ind) { ind.textContent='Error'; ind.className='save-indicator error'; } });
}

function loadDeal(c){if(SERVE_MODE)window.location.href=(window.BASE_PATH||'')+'/?deal='+c;else alert('Static mode — to browse deals interactively, restart with:\n\npython DEALROOM.py dashboard --serve')}
function showPortfolio(){if(SERVE_MODE)window.location.href=(window.BASE_PATH||'')+'/'}

// ─── Next step logic ─────────────────────────────────────────────────────────

function getNextStep(deal, data) {
  const fin=data.financials||{};
  const pnl=fin.pnl||{};
  const docs=data.documents||[];
  const flags=fin.risk_flags||[];
  const hasPnl=Object.keys(pnl).length>0;
  const hasBalance=Object.keys(fin.balance||{}).length>0;
  const hasDocs=docs.length>0;
  const hasConflicts=deal.conflict_count>0;

  switch(deal.deal_stage) {
    case 'meeting_concluded':
      return 'NDA exchange — first contact through data room handover';
    case 'valuation_rfi':
      if(!hasDocs) return 'Run ingest-docs to register financial documents';
      if(!hasPnl) return 'Run extract to parse financial data from documents';
      if(hasConflicts) return 'Resolve '+deal.conflict_count+' data conflicts before proceeding';
      return 'Financial analysis, RFI, thesis building — prepare for IC go';
    case 'indicative_offer':
      if(hasConflicts) return 'Resolve '+deal.conflict_count+' conflicts before offer';
      return 'Indicative offer drafting & negotiation';
    case 'loi_signed':
      return 'LOI drafting through signature';
    case 'due_diligence':
      return 'Active DD — track open items';
    case 'closed':
      return 'SPA negotiation through funds flow';
    case 'on_hold':
      return 'Deal on hold — review when ready to resume';
    case 'dead':
      return 'Deal dead — post-mortem available';
    default:
      return null;
  }
}
