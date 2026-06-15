// ─── RFI / Fragen ────────────────────────────────────────────────────────────

function renderRFI() {
  const qdata=DATA.questions||{};
  const counts=qdata.counts||{};
  const bySection=qdata.by_section||{};
  const total=counts.total||0;
  const code=DATA.deal?DATA.deal.code_name:'';

  if(total===0){
    return '<div class="empty">Keine Fragen vorhanden.<br>'
      +'<code>python DEALROOM.py draft-rfi --deal '+esc(code)+'</code></div>';
  }

  // Flatten all sections into one list, preserving order: financial → commercial → general
  const allRows=[];
  for(const sec of ['financial','commercial','general']){
    for(const q of (bySection[sec]||[])) allRows.push(q);
  }

  function srcClass(src){
    if(!src||src==='rfi_generator') return 'src-template';
    if(src==='rfi_generator:conflict') return 'src-conflict';
    if(src.startsWith('rfi_generator:account:')) return 'src-account';
    if(src==='manual') return 'src-manual';
    return 'src-template';
  }
  function stClass(st){ return 'st-'+(st||'draft'); }
  function catLabel(c){ return c==='financial'?'Finanzen':c==='commercial'?'Kommerziell':'Allgemein'; }

  // Toolbar with filter dropdowns
  const statuses=['','draft','sent','answered','waived'];
  const categories=['','financial','commercial','general'];
  const importances=['','high','medium'];

  let h='<div class="rfi-toolbar">';
  h+='<select id="rfi-f-status" onchange="rfiFilter()">';
  for(const s of statuses) h+='<option value="'+s+'">'+(s?s.charAt(0).toUpperCase()+s.slice(1):'Alle Status')+'</option>';
  h+='</select>';
  h+='<select id="rfi-f-cat" onchange="rfiFilter()">';
  for(const c of categories) h+='<option value="'+c+'">'+(c?catLabel(c):'Alle Kategorien')+'</option>';
  h+='</select>';
  h+='<select id="rfi-f-imp" onchange="rfiFilter()">';
  for(const i of importances) h+='<option value="'+i+'">'+(i?i.charAt(0).toUpperCase()+i.slice(1):'Alle Prioritäten')+'</option>';
  h+='</select>';
  h+='<span class="rfi-stats" id="rfi-visible-count">'+total+' Fragen</span>';
  h+='</div>';

  // Table
  h+='<table class="rfi-table" id="rfi-table">';
  h+='<thead><tr>';
  h+='<th style="width:28px">#</th>';
  h+='<th>Frage</th>';
  h+='<th style="width:90px">Kategorie</th>';
  h+='<th style="width:60px">Prio</th>';
  h+='<th style="width:80px">Quelle</th>';
  h+='<th style="width:72px">Status</th>';
  h+='<th>Antwort</th>';
  h+='<th style="width:100px">Antwort-Quelle</th>';
  h+='</tr></thead><tbody>';

  allRows.forEach((q,i)=>{
    const imp=q.importance||'medium';
    const st=q.status||'draft';
    const slabel=q.source_label||'TEMPLATE';
    const hasAnswer=!!q.answer;

    h+='<tr class="rfi-row" data-status="'+st+'" data-cat="'+esc(q.category)+'" data-imp="'+imp+'">';
    h+='<td style="color:var(--text-muted);font-size:11px">'+(i+1)+'</td>';
    h+='<td class="imp-cell-'+imp+'"><div class="q-text">'+esc(q.question)+'</div></td>';
    h+='<td><span style="font-size:11px">'+catLabel(q.category||'general')+'</span>'
      +(q.subcategory?'<br><span style="font-size:10px;color:var(--text-muted)">'+esc(q.subcategory)+'</span>':'')+'</td>';
    h+='<td>'+(imp==='high'?'<span class="badge imp-high">HOCH</span>':'<span class="badge imp-medium">MED</span>')+'</td>';
    h+='<td><span class="badge '+srcClass(q.source)+'">'+esc(slabel)+'</span></td>';
    h+='<td><span class="badge '+stClass(st)+'">'+st.toUpperCase()+'</span></td>';
    h+='<td>'+(hasAnswer
      ?'<div style="font-size:12px;color:var(--text);line-height:1.4">'+esc(q.answer)+'</div>'
      :'<span style="color:var(--text-muted);font-size:11px">—</span>')+'</td>';
    h+='<td><span style="font-size:11px;color:var(--text-muted)">'+(q.answer_source?esc(q.answer_source):'—')+'</span></td>';
    h+='</tr>';
  });

  h+='</tbody></table>';
  h+='<div class="rfi-footer">Regenerieren: <code>python DEALROOM.py draft-rfi --deal '+esc(code)+'</code>'
    +' &nbsp;|&nbsp; Als gesendet markieren: <code>python DEALROOM.py rfi --deal '+esc(code)+' --mark-sent</code></div>';
  return h;
}

function rfiFilter(){
  const fStatus=document.getElementById('rfi-f-status').value;
  const fCat=document.getElementById('rfi-f-cat').value;
  const fImp=document.getElementById('rfi-f-imp').value;
  const rows=document.querySelectorAll('#rfi-table .rfi-row');
  let visible=0;
  rows.forEach(tr=>{
    const match=(!fStatus||tr.dataset.status===fStatus)
      &&(!fCat||tr.dataset.cat===fCat)
      &&(!fImp||tr.dataset.imp===fImp);
    tr.classList.toggle('hidden',!match);
    if(match) visible++;
  });
  const el=document.getElementById('rfi-visible-count');
  if(el) el.textContent=visible+' Fragen';
}

