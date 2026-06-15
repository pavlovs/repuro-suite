// ALLEX v2 — single app file, two views with sub-tabs

(function(){
const D = window.D;
let activeIdx = 0;
let queueSort = 'ready';
let funnelStyle = 'bar';
let mode = 'review';
let sub = { review: 'list', analyze: 'funnel' };
let activityFilter = 'all'; // all | claude | roman

// ===== ROUTING =====
const TITLES = {
  review:  ['Review', 'Was fehlt, damit Records exportbereit sind'],
  analyze: ['Analyze', 'Performance der Pipeline und Briefaktionen'],
};
const SUBNAV = {
  review: [
    { id: 'list',     label: 'Lead-Liste',     hint: 'Queue & Editor' },
    { id: 'dropoff',  label: 'Drop-off',       hint: 'Wo Records herausfallen' },
    { id: 'activity', label: 'Activity Log',   hint: 'Wer hat was geändert' },
  ],
  analyze: [
    { id: 'funnel',     label: 'Funnel',        hint: 'Ingest → Export' },
    { id: 'cohorts',    label: 'Cohorts',       hint: 'Sent → Reply → Deal' },
    { id: 'classes',    label: 'Klassen',       hint: 'A/B/C/D/E Verteilung' },
    { id: 'bottlenecks',label: 'Bottlenecks',   hint: 'Aktuelle Blocker' },
  ],
};

const titleEl = document.getElementById('top-title');
const subEl   = document.getElementById('top-sub');
const subnavEl= document.getElementById('subnav');
const modes   = document.querySelectorAll('.side-mode');

function showMode(m){
  mode = m;
  modes.forEach(x => x.classList.toggle('active', x.dataset.mode === m));
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + m).classList.add('active');
  titleEl.textContent = TITLES[m][0];
  subEl.textContent   = TITLES[m][1];
  renderSubnav();
  renderCurrent();
}
modes.forEach(m => m.addEventListener('click', () => showMode(m.dataset.mode)));

function renderSubnav(){
  const items = SUBNAV[mode];
  const cur = sub[mode];
  subnavEl.innerHTML = items.map(it => `
    <button class="subnav-item ${it.id === cur ? 'active' : ''}" data-sub="${it.id}">
      <span class="subnav-label">${it.label}</span>
      <span class="subnav-hint">${it.hint}</span>
    </button>
  `).join('');
  subnavEl.querySelectorAll('.subnav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      sub[mode] = btn.dataset.sub;
      renderSubnav();
      renderCurrent();
    });
  });
}

function renderCurrent(){
  if (mode === 'review') {
    if (sub.review === 'list')     renderReviewList();
    if (sub.review === 'dropoff')  renderReviewDropoff();
    if (sub.review === 'activity') renderReviewActivity();
  } else {
    if (sub.analyze === 'funnel')      renderAnalyzeFunnel();
    if (sub.analyze === 'cohorts')     renderAnalyzeCohorts();
    if (sub.analyze === 'classes')     renderAnalyzeClasses();
    if (sub.analyze === 'bottlenecks') renderAnalyzeBottlenecks();
  }
}

// ===== HELPERS =====
function fmt(n){ return n.toLocaleString('de-DE').replace(',', '.'); }
function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ===== REVIEW › LIST =====
function renderReviewList(){
  const root = document.getElementById('view-review');
  root.innerHTML = `
    <div class="kpi-bar">
      <div class="kpi" data-kpi="block">
        <div class="kpi-num block num">${D.kpis.stalled}</div>
        <div class="kpi-meta">
          <div class="kpi-label">Blockiert</div>
          <div class="kpi-sub">Mehrere fehlende Felder · benötigt Aufmerksamkeit</div>
        </div>
        <div class="kpi-cta">→</div>
      </div>
      <div class="kpi" data-kpi="warn">
        <div class="kpi-num warn num">${D.kpis.blocked}</div>
        <div class="kpi-meta">
          <div class="kpi-label">In Bearbeitung</div>
          <div class="kpi-sub">Fast fertig · 1–3 Felder fehlen</div>
        </div>
        <div class="kpi-cta">→</div>
      </div>
      <div class="kpi" data-kpi="ok">
        <div class="kpi-num ok num">${D.kpis.ready}</div>
        <div class="kpi-meta">
          <div class="kpi-label">Bereit zum Export</div>
          <div class="kpi-sub">Alle Felder · freigegeben</div>
        </div>
        <div class="kpi-cta">Export →</div>
      </div>
    </div>

    <div class="review">
      <div class="queue">
        <div class="queue-head">
          <div class="queue-title">
            <strong>BA #7 — Niederrhein</strong>
            <span class="num">${D.rows.length}</span>
          </div>
          <div class="queue-search">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
            <input type="text" placeholder="Suchen…" id="qsearch"/>
          </div>
        </div>
        <div class="queue-sort">
          <span class="qs-chip ${queueSort==='ready'?'active':''}" data-sort="ready">Fast fertig</span>
          <span class="qs-chip ${queueSort==='block'?'active':''}" data-sort="block">Am stärksten blockiert</span>
          <span class="qs-spacer"></span>
        </div>
        <div class="queue-list" id="qlist"></div>
      </div>

      <div class="record" id="record"></div>
    </div>
  `;
  bindKpis();
  renderQueue();
  renderRecord();
}

function bindKpis(){
  document.querySelectorAll('.qs-chip').forEach(c => {
    c.addEventListener('click', () => {
      queueSort = c.dataset.sort;
      document.querySelectorAll('.qs-chip').forEach(x => x.classList.toggle('active', x.dataset.sort === queueSort));
      renderQueue();
    });
  });
}

function sortedRows(){
  const rs = D.rows.map((r, i) => ({ ...r, _idx: i, _missing: D.missingFor(r).filter(m => m.severity !== 'done').length }));
  if (queueSort === 'ready') {
    return rs.sort((a, b) => a._missing - b._missing || b.ready - a.ready);
  } else {
    return rs.sort((a, b) => b._missing - a._missing || a.ready - b.ready);
  }
}

function renderQueue(){
  const list = document.getElementById('qlist');
  if (!list) return;
  const rs = sortedRows();
  list.innerHTML = rs.map(r => {
    const miss = r._missing;
    let sev = 'warn', stat = `${miss} fehlen`;
    if (miss === 0) { sev = 'ok'; stat = 'Bereit'; }
    else if (miss >= 4) { sev = 'block'; stat = `${miss} fehlen`; }
    return `
      <div class="qitem ${r._idx === activeIdx ? 'active' : ''}" data-idx="${r._idx}">
        <div class="qitem-name">${escapeHtml(r.name)}</div>
        <div class="qitem-stat ${sev} num">${stat}</div>
        <div class="qitem-domain">${escapeHtml(r.domain)}</div>
        <div class="qitem-cls">${r.klass}</div>
      </div>
    `;
  }).join('');
  list.querySelectorAll('.qitem').forEach(el => {
    el.addEventListener('click', () => {
      activeIdx = parseInt(el.dataset.idx, 10);
      renderQueue();
      renderRecord();
    });
  });
}

function renderRecord(){
  const root = document.getElementById('record');
  if (!root) return;
  const r = D.rows[activeIdx];
  const missing = D.missingFor(r);
  const blockingCount = missing.filter(m => m.severity !== 'done').length;
  const allDone = blockingCount === 0;

  root.innerHTML = `
    <div class="record-head">
      <div class="record-cls">${r.klass}</div>
      <div class="record-meta">
        <div class="record-name">${escapeHtml(r.name)}</div>
        <div class="record-domain">${escapeHtml(r.domain)} · ${escapeHtml(r.region)}</div>
      </div>
      <div class="record-spacer"></div>
      <div class="record-counter num">${activeIdx + 1} / ${D.rows.length}</div>
      <div class="record-nav">
        <button id="rec-prev" title="Vorheriger Record">
          <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>
        </button>
        <button id="rec-next" title="Nächster Record">
          <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
        </button>
      </div>
    </div>

    <div class="record-body">
      <div class="record-left">

        ${allDone ? `
          <div class="missing">
            <div class="missing-title">Status</div>
            <div class="miss-ready">
              <div class="miss-ready-icon">
                <svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-12"/></svg>
              </div>
              <div>
                <div style="font-weight:600;font-size:14px">Bereit zum Export</div>
                <div class="muted" style="font-size:12px;margin-top:2px">Alle Felder gefüllt · final freigegeben</div>
              </div>
            </div>
          </div>
        ` : `
          <div class="missing">
            <div class="missing-title">
              <span>Was fehlt</span>
              <span class="muted num" style="margin-left:auto;font-weight:500">${blockingCount} offen</span>
            </div>
            <div class="missing-list">
              ${missing.map(m => `
                <div class="miss-row ${m.severity}">
                  <div class="miss-icon">
                    ${m.severity === 'done'
                      ? '<svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-12"/></svg>'
                      : m.severity === 'block'
                        ? '<svg viewBox="0 0 24 24"><path d="M12 8v5M12 17v.01"/></svg>'
                        : ''}
                  </div>
                  <div class="miss-body">
                    <div class="miss-label">${m.label}</div>
                    <div class="miss-hint">${m.hint}</div>
                  </div>
                  ${m.severity === 'done'
                    ? '<div class="miss-action muted">erledigt</div>'
                    : '<div class="miss-action">Bearbeiten <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg></div>'}
                </div>
              `).join('')}
            </div>
          </div>
        `}

        <div class="fields-section">
          <div class="section-title">Stammdaten</div>
          <div class="field">
            <div class="field-label">Firma <span class="src">· Impressum</span></div>
            <input type="text" value="${escapeHtml(r.name)}"/>
          </div>
          <div class="field-grid">
            <div class="field">
              <div class="field-label">Klasse</div>
              <select>
                <option ${r.klass==='A'?'selected':''}>A — Platform</option>
                <option ${r.klass==='B'?'selected':''}>B — Add-on</option>
                <option>C — Unklar</option>
                <option>D — No-fit</option>
                <option>E — Special</option>
              </select>
            </div>
            <div class="field">
              <div class="field-label">Region</div>
              <input type="text" value="${escapeHtml(r.region)}"/>
            </div>
          </div>
          <div class="field-grid">
            <div class="field">
              <div class="field-label">Anrede</div>
              <select><option>Frau</option><option>Herr</option></select>
            </div>
            <div class="field">
              <div class="field-label">Geschäftsführer</div>
              <input type="text" value="Jana Rennecke"/>
            </div>
          </div>
        </div>

        <div class="fields-section">
          <div class="section-title">Postadresse ${missing.find(m=>m.key==='address' && m.severity!=='done') ? '<span class="muted" style="margin-left:6px;color:var(--block)">— fehlt</span>' : ''}</div>
          <div class="field">
            <div class="field-label">Straße</div>
            <input type="text" placeholder="—" class="${missing.find(m=>m.key==='address' && m.severity!=='done') ? 'bad' : ''}"/>
          </div>
          <div class="field-grid">
            <div class="field">
              <div class="field-label">PLZ</div>
              <input type="text" placeholder="—" class="${missing.find(m=>m.key==='address' && m.severity!=='done') ? 'bad' : ''}"/>
            </div>
            <div class="field">
              <div class="field-label">Stadt</div>
              <input type="text" placeholder="—" class="${missing.find(m=>m.key==='address' && m.severity!=='done') ? 'bad' : ''}"/>
            </div>
          </div>
        </div>

        <div class="fields-section">
          <div class="section-title">Brief-Inhalt</div>
          <div class="field">
            <div class="field-label">Persönliches Kompliment <span class="src">· AI-generiert</span></div>
            <textarea rows="3">besonders beeindruckt hat uns die breite Sortimentstiefe von über 600 Artikeln für Notfall und Praxis — Ausdruck einer tiefen Verankerung im ambulanten Versorgungsbereich.</textarea>
          </div>
          <div class="field">
            <div class="field-label">GF E-Mail <span class="src">· optional</span></div>
            <input type="email" value="info@${escapeHtml(r.domain)}"/>
          </div>
        </div>
      </div>

      <div class="record-right">
        <div class="preview-tabs">
          <div class="preview-tab active" data-tab="letter">Brief-Vorschau</div>
          <div class="preview-tab" data-tab="site">Website</div>
        </div>
        <div class="preview-body" id="preview-body">${letterHtml(r, missing)}</div>
      </div>
    </div>

    <div class="actions">
      <button class="btn">Save <span class="kbd">⌘S</span></button>
      <button class="btn">Skip <span class="kbd">→</span></button>
      <div style="flex:1"></div>
      ${allDone
        ? '<button class="btn primary">Bereit · Zum Export hinzufügen <svg viewBox="0 0 24 24"><path d="M5 12h14M13 5l7 7-7 7"/></svg></button>'
        : `<button class="btn warn">${blockingCount} offene Felder bearbeiten</button>`
      }
    </div>
  `;

  document.getElementById('rec-prev').addEventListener('click', () => {
    activeIdx = (activeIdx - 1 + D.rows.length) % D.rows.length;
    renderQueue(); renderRecord();
  });
  document.getElementById('rec-next').addEventListener('click', () => {
    activeIdx = (activeIdx + 1) % D.rows.length;
    renderQueue(); renderRecord();
  });
  document.querySelectorAll('.preview-tab').forEach(t => {
    t.addEventListener('click', () => {
      document.querySelectorAll('.preview-tab').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      const body = document.getElementById('preview-body');
      body.innerHTML = t.dataset.tab === 'letter' ? letterHtml(r, missing) : siteHtml(r);
    });
  });
}

function letterHtml(r, missing){
  const addrMissing = missing.find(m => m.key === 'address' && m.severity !== 'done');
  const compMissing = missing.find(m => m.key === 'compliment' && m.severity !== 'done');
  return `
  <div class="letter">
    <div class="lhead">
      <div>${escapeHtml(r.name)}</div>
      <div>Frau Jana Rennecke</div>
      ${addrMissing
        ? '<span class="hl-miss">[Straße fehlt]</span><br><span class="hl-miss">[PLZ Stadt fehlt]</span>'
        : '<span class="hl-fill">Hauptstraße 47</span><br><span class="hl-fill">63867 Niedernberg</span>'}
    </div>
    <div class="ldate">Berlin, 27.04.2026</div>
    <div class="lsubject">${escapeHtml(r.name)} — gemeinsam mit der Repuro Gruppe den nächsten Schritt gehen</div>
    <p>Sehr geehrte Frau Rennecke,</p>
    <p>bei meiner Recherche zu erfolgreichen <b>Medizinprodukt-Händlern</b> in der Region ${escapeHtml(r.region)} sind wir auf <b>${escapeHtml(r.name)}</b> aufmerksam geworden. ${compMissing ? '<span class="hl-miss">[Persönliches Kompliment generieren]</span>' : '<span class="hl-fill">Besonders beeindruckt hat uns die breite Sortimentstiefe von über 600 Artikeln für Notfall und Praxis — Ausdruck einer tiefen Verankerung im ambulanten Versorgungsbereich.</span>'}</p>
    <p>Mein Name ist Florian Fischer — ich bin Gründer und Geschäftsführer der Repuro Gruppe. Als inhabergeführte Unternehmergruppe beteiligen wir uns ausschließlich an Medizinprodukt-Händlern in Deutschland.</p>
    <p>Gerne würden wir mit Ihnen über eine Unternehmensnachfolge sprechen und bieten als Gesellschafter eine maßgeschneiderte Lösung — von der Sicherung Ihres Lebenswerks bis hin zur strategischen Partnerschaft.</p>
    <p>Wir freuen uns, von Ihnen zu hören.</p>
    <p>Mit freundlichen Grüßen</p>
    <div class="lsig">
      <div><b>Florian Fischer</b><br>Geschäftsführer</div>
      <div><b>Roman Dobrolov</b><br>Geschäftsführer</div>
    </div>
  </div>`;
}

function siteHtml(r){
  return `
  <div class="site">
    <div class="site-bar">
      <span style="color:var(--ink-3)">https://</span><span style="color:var(--ink);font-weight:500">${escapeHtml(r.domain)}</span>
      <div style="flex:1"></div>
      <button class="btn sm ghost" onclick="window.open('https://${escapeHtml(r.domain)}','_blank')">Neu öffnen ↗</button>
    </div>
    <div class="site-frame">
      <div style="padding:32px 36px;font-family:var(--sans)">
        <div style="display:flex;align-items:center;gap:12px;padding-bottom:18px;border-bottom:1px solid #eee">
          <div style="width:38px;height:38px;background:#1f3a5f;border-radius:5px;display:grid;place-items:center;color:white;font-weight:700;font-size:14px">${escapeHtml(r.name).split(' ').map(w=>w[0]).slice(0,2).join('')}</div>
          <div>
            <div style="font-weight:700;font-size:15px;color:var(--ink)">${escapeHtml(r.name)}</div>
            <div style="font-size:11px;color:var(--ink-3)">Medizinprodukte · Handel · Service</div>
          </div>
        </div>
        <div style="padding:28px 0">
          <div style="font-size:24px;font-weight:600;color:var(--ink);line-height:1.2;margin-bottom:12px;letter-spacing:-0.015em">Ihr Partner für Medizintechnik in ${escapeHtml(r.region)}</div>
          <div style="font-size:13px;color:var(--ink-2);line-height:1.6">Seit über 30 Jahren beliefern wir Arztpraxen, Krankenhäuser und Pflegeeinrichtungen mit zertifizierten Medizinprodukten.</div>
        </div>
      </div>
    </div>
  </div>`;
}

// ===== REVIEW › DROP-OFF =====
function renderReviewDropoff(){
  const root = document.getElementById('view-review');
  const d = D.dropoff;
  const total = d.total;
  const finalPassed = d.stages[d.stages.length - 1].passed;
  const totalDropped = total - finalPassed;

  root.innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h2>Drop-off · BA #7 Niederrhein</h2>
          <p class="lead">Wo fielen die ${fmt(total)} ingestierten Targets im Pipeline-Verlauf heraus?</p>
        </div>
        <div class="page-stats">
          <div class="ps">
            <div class="ps-num num">${fmt(total)}</div>
            <div class="ps-lbl">Ingestiert</div>
          </div>
          <div class="ps">
            <div class="ps-num num warn">${fmt(totalDropped)}</div>
            <div class="ps-lbl">Herausgefallen</div>
          </div>
          <div class="ps">
            <div class="ps-num num ok">${fmt(finalPassed)}</div>
            <div class="ps-lbl">Approved</div>
          </div>
        </div>
      </div>

      <div class="dropflow">
        ${d.stages.map((s, i) => {
          const prev = i === 0 ? total : d.stages[i-1].passed;
          const passPct = prev > 0 ? Math.round((s.passed / prev) * 100) : 100;
          const dropPct = prev > 0 ? Math.round((s.dropped / prev) * 100) : 0;
          const widthPass = (s.passed / total) * 100;
          return `
            <div class="dfstage">
              <div class="dfstage-head">
                <div class="dfstage-meta">
                  <div class="dfstage-step num">${String(i+1).padStart(2,'0')}</div>
                  <div>
                    <div class="dfstage-title">${s.stage}</div>
                    <div class="dfstage-sub">${s.sub}</div>
                  </div>
                </div>
                <div class="dfstage-counts">
                  <div class="dfc-pass">
                    <span class="num">${fmt(s.passed)}</span>
                    <span class="dfc-lbl">passieren · ${passPct}%</span>
                  </div>
                  ${s.dropped > 0 ? `
                    <div class="dfc-drop">
                      <span class="num">−${fmt(s.dropped)}</span>
                      <span class="dfc-lbl">${dropPct}% drop</span>
                    </div>
                  ` : '<div class="dfc-drop muted">keine Verluste</div>'}
                </div>
              </div>
              <div class="dfflow">
                <div class="dfflow-pass" style="width:${widthPass}%"></div>
              </div>
              ${s.reasons.length ? `
                <div class="dfreasons">
                  ${s.reasons.map(r => `
                    <div class="dfreason">
                      <span class="dfr-dot ${r.kind}"></span>
                      <span class="dfr-label">${escapeHtml(r.label)}</span>
                      <span class="dfr-bar"><span style="width:${(r.n / s.dropped) * 100}%"></span></span>
                      <span class="dfr-n num">${fmt(r.n)}</span>
                    </div>
                  `).join('')}
                </div>
              ` : ''}
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

// ===== REVIEW › ACTIVITY =====
function renderReviewActivity(){
  const root = document.getElementById('view-review');
  const all = D.activity;
  const claudeCount = all.filter(a => a.actor === 'claude').length;
  const romanCount  = all.filter(a => a.actor === 'roman').length;
  const filtered = activityFilter === 'all' ? all : all.filter(a => a.actor === activityFilter);

  root.innerHTML = `
    <div class="page">
      <div class="page-head">
        <div>
          <h2>Activity Log</h2>
          <p class="lead">Welche Felder wurden geändert — von Claude oder manuell? Letzte Änderungen zuerst.</p>
        </div>
        <div class="page-stats">
          <div class="ps">
            <div class="ps-num num">${all.length}</div>
            <div class="ps-lbl">Änderungen heute</div>
          </div>
          <div class="ps">
            <div class="ps-num num"><span class="actor-dot claude"></span>${claudeCount}</div>
            <div class="ps-lbl">Claude</div>
          </div>
          <div class="ps">
            <div class="ps-num num"><span class="actor-dot roman"></span>${romanCount}</div>
            <div class="ps-lbl">Manuell (Roman)</div>
          </div>
        </div>
      </div>

      <div class="actfilter">
        <span class="qs-chip ${activityFilter==='all'?'active':''}"    data-f="all">Alle</span>
        <span class="qs-chip ${activityFilter==='claude'?'active':''}" data-f="claude">Nur Claude</span>
        <span class="qs-chip ${activityFilter==='roman'?'active':''}"  data-f="roman">Nur manuell</span>
      </div>

      <div class="actlog">
        ${filtered.map(a => `
          <div class="actrow">
            <div class="actcol-time num">${a.ts}</div>
            <div class="actcol-actor">
              <span class="actor-dot ${a.actor}"></span>
              <span class="actor-name">${a.actor === 'claude' ? 'Claude' : 'Roman'}</span>
              <span class="act-kind ${a.kind}">${kindLabel(a.kind)}</span>
            </div>
            <div class="actcol-company">${escapeHtml(a.company)}</div>
            <div class="actcol-field">
              <code>${escapeHtml(a.field)}</code>
            </div>
            <div class="actcol-diff">
              <span class="diff-old">${escapeHtml(a.old)}</span>
              <svg viewBox="0 0 24 24" class="diff-arrow"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
              <span class="diff-new">${escapeHtml(a.neu)}</span>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
  root.querySelectorAll('.qs-chip').forEach(c => {
    c.addEventListener('click', () => {
      activityFilter = c.dataset.f;
      renderReviewActivity();
    });
  });
}

function kindLabel(k){
  return ({
    gen:    'AI generiert',
    regen:  'AI re-generiert',
    enrich: 'Enrichment',
    edit:   'Manuell',
    approve:'Freigabe',
    system: 'System',
  })[k] || k;
}

// ===== ANALYZE › FUNNEL =====
function renderAnalyzeFunnel(){
  const root = document.getElementById('view-analyze');
  const totalIn = D.funnel[0].n;
  root.innerHTML = `
    <div class="analyze">
      <h2>Pipeline-Funnel · Alle Briefaktionen</h2>
      <p class="lead">Wo stehen die ${fmt(totalIn)} Records aktuell — und wo geht der Trichter verloren?</p>

      <div class="an-section">
        <div class="fnl">
          ${D.funnel.map((f, i) => `
            <div class="fnl-row">
              <div>
                <div class="fnl-stage">${f.stage}</div>
                <div class="fnl-stage-sub">${f.sub}</div>
              </div>
              <div class="fnl-track">
                <div class="fnl-bar" style="width:${Math.max(0.2, f.pct)}%;animation-delay:${i*70}ms"></div>
              </div>
              <div class="fnl-n num">${fmt(f.n)}</div>
              <div class="fnl-pct num">${f.pct < 1 ? f.pct.toFixed(1) : f.pct.toFixed(0)}%</div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}

// ===== ANALYZE › COHORTS =====
function renderAnalyzeCohorts(){
  const root = document.getElementById('view-analyze');
  root.innerHTML = `
    <div class="analyze">
      <h2>Cohort Performance</h2>
      <p class="lead">Sent → Reply → Meeting → Deal pro Briefaktion.</p>
      <div class="an-section">
        <table class="cohort">
          <thead>
            <tr>
              <th>Briefaktion</th>
              <th class="r">Sent</th>
              <th class="r">Reply</th>
              <th class="r">Meeting</th>
              <th class="r">Deal</th>
            </tr>
          </thead>
          <tbody>
            ${D.cohorts.map(c => `
              <tr>
                <td class="name">${escapeHtml(c.name)}</td>
                <td class="r num">${c.sent}</td>
                <td class="r num">${c.reply}<span class="pct">${Math.round(c.reply/c.sent*100)}%</span></td>
                <td class="r num">${c.meeting}<span class="pct">${Math.round(c.meeting/c.sent*100)}%</span></td>
                <td class="r num">${c.deal}<span class="pct">${Math.round(c.deal/c.sent*100)}%</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ===== ANALYZE › CLASSES =====
function renderAnalyzeClasses(){
  const root = document.getElementById('view-analyze');
  const total = D.classes.reduce((s, c) => s + c.n, 0);
  root.innerHTML = `
    <div class="analyze">
      <h2>Klassen-Verteilung</h2>
      <p class="lead">${fmt(total)} klassifizierte Records über alle Briefaktionen.</p>
      <div class="an-section">
        <div class="cls-sum">
          ${D.classes.map(c => `
            <div class="cls-cell">
              <div class="cls-letter">${c.k}</div>
              <div class="cls-num num">${fmt(c.n)}</div>
              <div class="cls-desc">${c.desc}</div>
              <div class="cls-bar"><span style="width:${(c.n/total)*100}%"></span></div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}

// ===== ANALYZE › BOTTLENECKS =====
function renderAnalyzeBottlenecks(){
  const root = document.getElementById('view-analyze');
  root.innerHTML = `
    <div class="analyze">
      <h2>Aktuelle Bottlenecks</h2>
      <p class="lead">Wo der Operator gerade Hand anlegen muss.</p>
      <div class="an-section">
        <div class="bottle">
          ${D.bottlenecks.map(b => `
            <div class="bottle-card">
              <div class="bottle-card-label">${b.label}</div>
              <div class="bottle-card-num ${b.sev || ''} num">${fmt(b.n)}</div>
              <div class="bottle-card-action">${b.action} →</div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}

// ===== TWEAKS =====
const tweaks = document.getElementById('tweaks');
document.getElementById('toggle-tweaks').addEventListener('click', () => tweaks.classList.toggle('open'));
tweaks.querySelectorAll('.seg').forEach(seg => {
  seg.addEventListener('click', e => {
    const btn = e.target.closest('button[data-v]');
    if (!btn) return;
    seg.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (seg.dataset.tweak === 'sort') {
      queueSort = btn.dataset.v;
      renderQueue();
    }
  });
});

// Init
renderSubnav();
renderReviewList();
})();
