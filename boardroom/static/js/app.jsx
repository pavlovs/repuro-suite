/* Investor Room — React/Babel in-browser, no build step. */
const { useState, useEffect } = React;

// ---------------------------------------------------------------------------
// Dev-auth: in production Caddy injects X-Remote-User. Locally there is no Caddy,
// so when the server runs with --dev we let the browser send the header itself and
// expose a role switcher (review as Strada vs admin). No effect in production —
// Caddy overwrites X-Remote-User regardless.
let DEV = false;
function devRole() { return localStorage.getItem('inv_dev_role') || 'roman'; }
function setDevRole(r) { localStorage.setItem('inv_dev_role', r); location.reload(); }
function _devHeaders() { return DEV ? { 'X-Remote-User': devRole() } : {}; }

// ---------------------------------------------------------------------------
// API helpers — relative URLs so it works at localhost:8084/ AND /investor/

function apiFetch(path) {
  return fetch(path, { headers: _devHeaders() }).then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });
}

// ---------------------------------------------------------------------------
// Updates tab — weekly_update

function PipelineFunnel({ items }) {
  if (!items || !items.length) return <p className="empty-state">No pipeline data.</p>;
  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Codename</th><th>Stage</th><th>Sector</th><th>Region</th>
            <th>Size band</th><th>Strategic fit</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r, i) => (
            <tr key={i}>
              <td><strong>{r.codename}</strong></td>
              <td>{r.stage}</td>
              <td>{r.sector}</td>
              <td>{r.region}</td>
              <td>{r.size_band}</td>
              <td>{r.strategic_fit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BatchStats({ rows }) {
  if (!rows || !rows.length) return <p className="empty-state">No batch data.</p>;
  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Batch</th><th>Sent</th><th>Replies</th><th>Meetings</th><th>Conv %</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.batch}</td>
              <td>{r.sent}</td>
              <td>{r.replies}</td>
              <td>{r.meetings}</td>
              <td>{r.conv_pct != null ? `${r.conv_pct}%` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LiveDealCard({ deal }) {
  const fmt = v => v != null ? `€${v}M` : '—';
  return (
    <div className="deal-card">
      <div className="deal-card-header">
        <span className="deal-name">{deal.name}</span>
        <span className="deal-stage">{deal.stage}</span>
      </div>
      <div className="deal-metrics">
        <div className="metric"><span className="metric-label">Revenue</span><span className="metric-value">{fmt(deal.rev_m)}</span></div>
        <div className="metric"><span className="metric-label">EBITDA</span><span className="metric-value">{fmt(deal.ebitda_m)}</span></div>
        <div className="metric"><span className="metric-label">EV</span><span className="metric-value">{fmt(deal.ev_m)}</span></div>
        <div className="metric"><span className="metric-label">Multiple</span><span className="metric-value">{deal.multiple != null ? `${deal.multiple}x` : '—'}</span></div>
        <div className="metric"><span className="metric-label">Close target</span><span className="metric-value">{deal.close_target || '—'}</span></div>
      </div>
      {deal.earnout && <div className="deal-commentary"><strong>Earn-out:</strong> {deal.earnout}</div>}
      {deal.dd_status && <div className="deal-commentary"><strong>DD:</strong> {deal.dd_status}</div>}
      {deal.commentary && <div className="deal-commentary">{deal.commentary}</div>}
    </div>
  );
}

function SourcesUsesTable({ rows }) {
  if (!rows || !rows.length) return null;
  return (
    <div className="tbl-wrap">
      <table>
        <thead><tr><th>Item</th><th>Amount (€M)</th><th>Note</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.item}</td>
              <td>{r.amount_m != null ? `€${r.amount_m}M` : '—'}</td>
              <td style={{color:'#6b7280'}}>{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Stage tokens — mirror dealroom (_STAGE_STATUS + stage colors from dashboard.html)
const STAGE_LABEL = {
  meeting_concluded: 'Meeting', valuation_rfi: 'Valuation & RFI', indicative_offer: 'NBO Sent',
  loi_signed: 'LOI signed', due_diligence: 'Due Diligence', contract_negotiation: 'Contract Neg.',
  closed: 'Closed', on_hold: 'On hold', dead: 'Dead',
};
const STAGE_COLOR = {
  meeting_concluded: '#eab308', valuation_rfi: '#3b82f6', indicative_offer: '#6366f1',
  loi_signed: '#a855f7', due_diligence: '#059669', contract_negotiation: '#0d9488',
  closed: '#065f46', on_hold: '#6b7280', dead: '#e11d48',
};
const STAGE_ORDER = ['meeting_concluded', 'valuation_rfi', 'indicative_offer', 'loi_signed', 'due_diligence', 'contract_negotiation', 'closed'];
const POST_LOI = ['loi_signed', 'due_diligence', 'contract_negotiation', 'closed'];
const BAND_MID = { '<€1M': 0.5, '€1–3M': 2, '€3–5M': 4, '€5M+': 6 };
const fmtM = v => (v == null ? '—' : `€${(+v).toFixed(1)}M`);

// Answer-first hero: aggregate EBITDA (M€) by current stage. Post-LOI exact; pre-LOI from
// size-band midpoint (indicative). Bars deep-link in-room to the live pipeline (sandbox-safe).
function Hero({ funnel, liveDeals, onStageClick }) {
  const agg = {};
  liveDeals.forEach(d => {
    const s = d.stage; if (!s) return;
    agg[s] = agg[s] || { ebitda: 0, count: 0, indicative: false };
    agg[s].ebitda += (+d.ebitda_m || 0); agg[s].count++;
  });
  funnel.forEach(d => {
    const s = d.stage; if (!s) return;
    agg[s] = agg[s] || { ebitda: 0, count: 0, indicative: true };
    agg[s].ebitda += (BAND_MID[d.size_band] || 0); agg[s].count++;
  });
  const stages = STAGE_ORDER.filter(s => agg[s]);
  if (!stages.length) return null;
  const max = Math.max(...stages.map(s => agg[s].ebitda), 0.1);
  const total = stages.reduce((t, s) => t + agg[s].ebitda, 0);

  return (
    <div className="hero">
      <div className="hero-head">
        <div className="hero-title">Pipeline by stage <span>— adj. EBITDA (€M)</span></div>
        <div className="hero-total"><strong>{fmtM(total)}</strong> across {stages.reduce((t, s) => t + agg[s].count, 0)} targets</div>
      </div>
      <div className="hero-chart">
        {stages.map(s => {
          const a = agg[s];
          const clickable = POST_LOI.includes(s);
          return (
            <div key={s} className="hero-col" data-clickable={clickable ? 1 : 0}
                 onClick={clickable ? () => onStageClick(s) : undefined}
                 title={clickable ? 'Open in live pipeline' : 'Pre-LOI — anonymized'}>
              <div className="hero-bar-val">{fmtM(a.ebitda)}</div>
              <div className={`hero-bar${a.indicative ? ' indicative' : ''}`}
                   style={{ height: `${Math.max(3, (a.ebitda / max) * 100)}%`, background: STAGE_COLOR[s] }} />
              <div className="hero-x">
                <div className="hero-x-stage">{STAGE_LABEL[s] || s}</div>
                <div className="hero-x-meta">{a.count} {a.count === 1 ? 'deal' : 'deals'}</div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="hero-foot">
        <span><span className="sw" style={{ background: '#a855f7' }} />Post-LOI — exact EBITDA, click to open</span>
        <span><span className="sw ind" />Pre-LOI — indicative (size band)</span>
      </div>
    </div>
  );
}

// Live pipeline — Dealroom .portfolio-table format (post-LOI deals, real names).
function PipelineTable({ deals }) {
  if (!deals.length) return <p className="empty-state">No live deals yet.</p>;
  const sum = k => deals.reduce((t, d) => t + (+d[k] || 0), 0);
  const pct = d => (d.rev_m && d.ebitda_m != null ? `${Math.round((d.ebitda_m / d.rev_m) * 100)}%` : '—');
  return (
    <div className="portfolio-wrap">
      <table className="portfolio-table">
        <colgroup>
          <col className="c-code" /><col className="c-name" /><col className="c-rev" /><col className="c-ebitda" />
          <col className="c-pct" /><col className="c-ev" /><col className="c-mul" /><col className="c-stage" /><col className="c-comment" />
        </colgroup>
        <thead><tr>
          <th className="c">Code</th><th>Company</th><th className="r">Rev (M)</th><th className="r">EBITDA (M)</th>
          <th className="r">%</th><th className="r">EV (M)</th><th className="r">Mult</th><th>Stage</th><th>Update</th>
        </tr></thead>
        <tbody>
          {deals.map((d, i) => (
            <tr key={i}>
              <td className="code-cell">{d.codename}</td>
              <td className="text-cell">{d.name}</td>
              <td className="r">{d.rev_m != null ? (+d.rev_m).toFixed(1) : '—'}</td>
              <td className="r">{d.ebitda_m != null ? (+d.ebitda_m).toFixed(1) : '—'}</td>
              <td className="r">{pct(d)}</td>
              <td className="r">{d.ev_m != null ? (+d.ev_m).toFixed(1) : '—'}</td>
              <td className="r">{d.multiple != null ? `${(+d.multiple).toFixed(1)}x` : '—'}</td>
              <td><span className={`stage-badge stage-${d.stage}`}>{STAGE_LABEL[d.stage] || d.stage}</span></td>
              <td className="text-cell">{d.commentary || d.dd_status || '—'}</td>
            </tr>
          ))}
        </tbody>
        <tfoot><tr>
          <td>TOTAL</td><td></td>
          <td className="r">{sum('rev_m').toFixed(1)}</td>
          <td className="r">{sum('ebitda_m').toFixed(1)}</td>
          <td></td>
          <td className="r">{sum('ev_m').toFixed(1)}</td>
          <td></td><td></td><td></td>
        </tr></tfoot>
      </table>
    </div>
  );
}

function UpdatesTab({ body }) {
  if (!body) return <p className="empty-state">No published update yet.</p>;
  const funnel = ((body.pipeline || {}).funnel || {}).items || [];
  const liveDeals = body.live_deals || [];
  const scrollToPipeline = () => {
    const el = document.getElementById('live-pipeline');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div>
      <Hero funnel={funnel} liveDeals={liveDeals} onStageClick={scrollToPipeline} />
      <div className="section" id="live-pipeline">
        <div className="section-title">Live pipeline — post-LOI</div>
        <PipelineTable deals={liveDeals} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Board tab — board_pack

function BoardTab({ body }) {
  if (!body) return <p className="empty-state">No published board pack yet.</p>;

  const meeting = body.meeting || {};
  const agenda = body.agenda || [];
  const kpis = body.kpis || [];
  const decisions = body.decisions || [];
  const preRead = body.pre_read || [];
  const minutes = body.minutes;

  return (
    <div>
      <div className="meeting-header">
        <div className="meeting-date">Board meeting — {meeting.date || '—'}</div>
        <div className="meeting-meta">
          {meeting.location && <span>{meeting.location}</span>}
          {meeting.attendees && meeting.attendees.length > 0 && (
            <span> &middot; {meeting.attendees.join(', ')}</span>
          )}
        </div>
      </div>

      {kpis.length > 0 && (
        <div className="section">
          <div className="section-title">KPIs</div>
          <div className="kpi-grid">
            {kpis.map((k, i) => (
              <div key={i} className="kpi-card">
                <div className="kpi-metric">{k.metric}</div>
                <div className="kpi-value">{k.value}</div>
                {k.prior && <div className="kpi-prior">Prior: {k.prior}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {agenda.length > 0 && (
        <div className="section">
          <div className="section-title">Agenda</div>
          <ul className="agenda-list">
            {agenda.map((a, i) => (
              <li key={i} className="agenda-item">
                <div className="agenda-item-title">{a.item}</div>
                {a.owner && <div className="agenda-item-owner">Owner: {a.owner}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {decisions.length > 0 && (
        <div className="section">
          <div className="section-title">Decisions &amp; resolutions</div>
          <ul className="decision-list">
            {decisions.map((d, i) => (
              <li key={i} className="decision-item">
                <div className="decision-topic">
                  {d.topic}
                  {d.resolution && (
                    <span className="resolution-badge">{d.resolution}</span>
                  )}
                </div>
                <div className="decision-meta">
                  {d.proposal && <span>{d.proposal}</span>}
                  {d.vote && <span> &middot; Vote: {d.vote}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {preRead.length > 0 && (
        <div className="section">
          <div className="section-title">Pre-read materials</div>
          <ul className="preread-list">
            {preRead.map((p, i) => (
              <li key={i} className="preread-item">
                <strong>{p.title}</strong>
                {p.note && <span style={{color:'#6b7280'}}> — {p.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {minutes !== undefined && (
        <div className="section">
          <div className="section-title">Minutes</div>
          <div className="minutes-block">
            {minutes || 'Minutes not yet available.'}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin curation helpers

function apiPost(path, body) {
  return fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', ..._devHeaders()},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(r => r.json().then(d => ({ ok: r.ok, status: r.status, data: d })));
}

function apiPatch(path, body) {
  return fetch(path, {
    method: 'PATCH',
    headers: {'Content-Type': 'application/json', ..._devHeaders()},
    body: JSON.stringify(body),
  }).then(r => r.json().then(d => ({ ok: r.ok, status: r.status, data: d })));
}

// ---------------------------------------------------------------------------
// Curate tab — admin only

function CurateTab() {
  const [pubs, setPubs] = useState([]);
  const [selected, setSelected] = useState(null);   // full pub row
  const [editBody, setEditBody] = useState('');      // textarea JSON
  const [diff, setDiff] = useState(null);
  const [msg, setMsg] = useState('');
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [checklist, setChecklist] = useState({
    no_pre_loi_names: false,
    no_other_investors: false,
    figures_stamped: false,
  });

  const loadList = () => {
    apiFetch('api/publications')
      .then(d => setPubs((d.publications || []).filter(p => p.status === 'draft' || p.status === 'approved')))
      .catch(e => setMsg('Error loading: ' + e.message));
  };

  useEffect(() => { loadList(); }, []);

  const openPub = (id) => {
    apiFetch(`api/publication/${id}`)
      .then(p => {
        setSelected(p);
        setEditBody(JSON.stringify(p.body, null, 2));
        setDiff(null);
        setMsg('');
      })
      .catch(e => setMsg('Error: ' + e.message));
  };

  const save = () => {
    let parsed;
    try { parsed = JSON.parse(editBody); } catch(e) { setMsg('JSON parse error: ' + e.message); return; }
    apiPatch(`api/publication/${selected.id}`, { body: parsed })
      .then(({ ok, data }) => {
        if (ok) { setSelected(data); setMsg('Saved (version ' + data.version + ')'); loadList(); }
        else setMsg('Save failed: ' + JSON.stringify(data.detail));
      });
  };

  const showDiff = () => {
    apiFetch(`api/publication/${selected.id}/diff`)
      .then(d => { setDiff(d); setMsg(''); })
      .catch(e => setMsg('Diff error: ' + e.message));
  };

  const doApprove = (force) => {
    apiPost(`api/publication/${selected.id}/approve${force ? '?force=1' : ''}`, { checklist })
      .then(({ ok, data }) => {
        setShowApproveModal(false);
        if (ok) {
          setMsg('Approved ✓');
          setSelected(s => ({...s, status: 'approved'}));
          loadList();
        } else {
          const detail = data.detail || {};
          if (detail.missing_acks) setMsg('Missing acks: ' + detail.missing_acks.join(', '));
          else if (detail.hard_violations) {
            // HARD gate (other-investor / pre-LOI name / non-contract key) — NOT overridable.
            setMsg('BLOCKED (hard gate, cannot be forced):\n' + detail.hard_violations.slice(0, 6).join('\n'));
          } else if (detail.soft_violations) {
            // SOFT gate (unstamped figure) — force allowed with explicit confirm.
            const vtext = detail.soft_violations.slice(0, 5).join('\n');
            if (window.confirm('Completeness warning (soft):\n' + vtext + '\n\nForce approve anyway?')) doApprove(true);
            else setMsg('Approval blocked — fix the figures or force.');
          } else setMsg('Approve failed: ' + JSON.stringify(detail));
        }
      });
  };

  const doPublish = () => {
    apiPost(`api/publication/${selected.id}/publish`)
      .then(({ ok, data }) => {
        if (ok) { setMsg('Published ✓'); setSelected(s => ({...s, status: 'published'})); loadList(); }
        else setMsg('Publish failed: ' + JSON.stringify(data.detail));
      });
  };

  const isDraft = selected && selected.status === 'draft';
  const isApproved = selected && selected.status === 'approved';

  return (
    <div style={{display:'flex', gap:'1.5rem', alignItems:'flex-start'}}>
      {/* Left: draft/approved list */}
      <div style={{minWidth:'220px', maxWidth:'260px'}}>
        <div style={{fontWeight:600, marginBottom:'0.5rem', fontSize:'0.85rem', color:'#6b7280', textTransform:'uppercase', letterSpacing:'0.05em'}}>Drafts &amp; Approved</div>
        {pubs.length === 0 && <div style={{color:'#9ca3af', fontSize:'0.85rem'}}>No drafts.</div>}
        {pubs.map(p => (
          <div
            key={p.id}
            onClick={() => openPub(p.id)}
            style={{
              padding:'0.5rem 0.75rem', marginBottom:'0.35rem', borderRadius:'6px', cursor:'pointer',
              background: selected && selected.id === p.id ? '#eff6ff' : '#f9fafb',
              border: selected && selected.id === p.id ? '1px solid #93c5fd' : '1px solid #e5e7eb',
              fontSize:'0.85rem',
            }}
          >
            <div style={{fontWeight:500}}>{p.title || `#${p.id}`}</div>
            <div style={{color:'#6b7280', fontSize:'0.75rem'}}>{p.kind} · <span style={{color: p.status==='approved' ? '#059669' : '#d97706'}}>{p.status}</span></div>
          </div>
        ))}
        <button onClick={loadList} style={{marginTop:'0.5rem', fontSize:'0.8rem', color:'#6b7280', background:'none', border:'none', cursor:'pointer'}}>↻ Refresh</button>
      </div>

      {/* Right: editor */}
      {selected ? (
        <div style={{flex:1}}>
          <div style={{display:'flex', alignItems:'center', gap:'1rem', marginBottom:'0.75rem'}}>
            <div style={{fontWeight:600}}>{selected.title}</div>
            <span style={{
              fontSize:'0.75rem', padding:'2px 8px', borderRadius:'999px', fontWeight:500,
              background: isApproved ? '#d1fae5' : '#fef3c7',
              color: isApproved ? '#065f46' : '#92400e',
            }}>{selected.status}</span>
            <span style={{fontSize:'0.75rem', color:'#9ca3af'}}>v{selected.version}</span>
          </div>

          {msg && <div style={{marginBottom:'0.5rem', padding:'0.4rem 0.75rem', borderRadius:'6px', background:'#f3f4f6', fontSize:'0.85rem', whiteSpace:'pre-wrap'}}>{msg}</div>}

          <textarea
            value={editBody}
            onChange={e => setEditBody(e.target.value)}
            disabled={!isDraft}
            rows={22}
            style={{
              width:'100%', fontFamily:'monospace', fontSize:'0.8rem', padding:'0.75rem',
              border:'1px solid #d1d5db', borderRadius:'6px', resize:'vertical',
              background: isDraft ? '#fff' : '#f9fafb', color: isDraft ? '#111' : '#6b7280',
              boxSizing:'border-box',
            }}
          />

          <div style={{display:'flex', gap:'0.5rem', marginTop:'0.75rem', flexWrap:'wrap'}}>
            {isDraft && (
              <button onClick={save} style={{padding:'0.4rem 1rem', borderRadius:'6px', background:'#2563eb', color:'#fff', border:'none', cursor:'pointer', fontSize:'0.85rem'}}>
                Save
              </button>
            )}
            <button onClick={showDiff} style={{padding:'0.4rem 1rem', borderRadius:'6px', background:'#f3f4f6', color:'#374151', border:'1px solid #d1d5db', cursor:'pointer', fontSize:'0.85rem'}}>
              Diff
            </button>
            {isDraft && (
              <button onClick={() => { setShowApproveModal(true); setMsg(''); }} style={{padding:'0.4rem 1rem', borderRadius:'6px', background:'#059669', color:'#fff', border:'none', cursor:'pointer', fontSize:'0.85rem'}}>
                Approve…
              </button>
            )}
            {isApproved && (
              <button onClick={doPublish} style={{padding:'0.4rem 1rem', borderRadius:'6px', background:'#7c3aed', color:'#fff', border:'none', cursor:'pointer', fontSize:'0.85rem'}}>
                Publish
              </button>
            )}
          </div>

          {/* Diff output */}
          {diff && (
            <div style={{marginTop:'1rem', fontSize:'0.8rem', fontFamily:'monospace', background:'#f8fafc', border:'1px solid #e2e8f0', borderRadius:'6px', padding:'0.75rem', maxHeight:'280px', overflow:'auto'}}>
              <div style={{fontWeight:600, marginBottom:'0.4rem', color:'#475569'}}>Diff vs published baseline</div>
              {diff.added.length > 0 && <div style={{color:'#15803d'}}>+ Added: {diff.added.slice(0,10).join(', ')}{diff.added.length > 10 ? ` …+${diff.added.length-10}` : ''}</div>}
              {diff.removed.length > 0 && <div style={{color:'#dc2626'}}>− Removed: {diff.removed.slice(0,10).join(', ')}{diff.removed.length > 10 ? ` …+${diff.removed.length-10}` : ''}</div>}
              {diff.changed.map((c, i) => (
                <div key={i} style={{color:'#92400e'}}>~ {c.path}: <span style={{color:'#dc2626'}}>{String(c.from).slice(0,40)}</span> → <span style={{color:'#15803d'}}>{String(c.to).slice(0,40)}</span></div>
              ))}
              {diff.added.length === 0 && diff.removed.length === 0 && diff.changed.length === 0 && <div style={{color:'#6b7280'}}>No differences.</div>}
            </div>
          )}
        </div>
      ) : (
        <div style={{flex:1, color:'#9ca3af', paddingTop:'2rem'}}>Select a draft to open.</div>
      )}

      {/* Approve modal */}
      {showApproveModal && (
        <div style={{position:'fixed', inset:0, background:'rgba(0,0,0,0.4)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:100}}>
          <div style={{background:'#fff', borderRadius:'10px', padding:'1.5rem', width:'400px', boxShadow:'0 20px 60px rgba(0,0,0,0.2)'}}>
            <div style={{fontWeight:600, marginBottom:'1rem'}}>Approval checklist</div>
            {Object.keys(checklist).map(k => (
              <label key={k} style={{display:'block', marginBottom:'0.6rem', cursor:'pointer', fontSize:'0.9rem'}}>
                <input
                  type="checkbox"
                  checked={checklist[k]}
                  onChange={e => setChecklist(c => ({...c, [k]: e.target.checked}))}
                  style={{marginRight:'0.5rem'}}
                />
                {k === 'no_pre_loi_names' && 'No pre-LOI real company names in funnel'}
                {k === 'no_other_investors' && 'No other-investor references (ASF / Aurica / Arbor)'}
                {k === 'figures_stamped' && 'All figures stamped with source + as-of date'}
              </label>
            ))}
            <div style={{display:'flex', gap:'0.5rem', marginTop:'1.25rem'}}>
              <button
                onClick={() => doApprove(false)}
                disabled={!Object.values(checklist).every(Boolean)}
                style={{flex:1, padding:'0.5rem', borderRadius:'6px', background: Object.values(checklist).every(Boolean) ? '#059669' : '#d1d5db', color:'#fff', border:'none', cursor: Object.values(checklist).every(Boolean) ? 'pointer' : 'not-allowed', fontWeight:500}}
              >
                Approve
              </button>
              <button
                onClick={() => setShowApproveModal(false)}
                style={{padding:'0.5rem 1rem', borderRadius:'6px', background:'#f3f4f6', color:'#374151', border:'1px solid #d1d5db', cursor:'pointer'}}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root app

function App() {
  const [tab, setTab] = useState('updates');
  const [weekly, setWeekly] = useState(null);
  const [board, setBoard] = useState(null);
  const [role, setRole] = useState(null);   // null=loading, 'admin'|'investor'
  const [error, setError] = useState(null);

  useEffect(() => {
    // Resolve role via whoami
    apiFetch('api/whoami')
      .then(d => setRole(d.role))
      .catch(() => setRole('investor'));  // fallback: investor-mode (403 = not admin)

    apiFetch('api/published?kind=weekly_update')
      .then(d => setWeekly(d.empty ? null : d))
      .catch(e => setError(e.message));

    apiFetch('api/published?kind=board_pack')
      .then(d => setBoard(d.empty ? null : d))
      .catch(e => setError(e.message));
  }, []);

  const isAdmin = role === 'admin';

  return (
    <div className="layout">
      <nav className="nav">
        <div className="nav-logo-wrap">
          <img className="nav-logo-img" src="static/img/logo-color.png" alt="Repuro" />
          <div className="nav-logo-sub">Investor Room{isAdmin && <span className="badge-admin">admin</span>}</div>
        </div>
        <button className={`nav-item${tab === 'updates' ? ' active' : ''}`} onClick={() => setTab('updates')}>Updates</button>
        <button className={`nav-item${tab === 'board' ? ' active' : ''}`} onClick={() => setTab('board')}>Board</button>
        {isAdmin && (
          <button className={`nav-item${tab === 'curate' ? ' active' : ''}`} onClick={() => setTab('curate')}>Curate</button>
        )}
        {DEV && (
          <div className="dev-switch">
            <div className="dev-switch-label">DEV — view as</div>
            <button className={`dev-btn${devRole() === 'investor' ? ' on' : ''}`} onClick={() => setDevRole('investor')}>Strada (investor)</button>
            <button className={`dev-btn${devRole() === 'roman' ? ' on' : ''}`} onClick={() => setDevRole('roman')}>Admin (Roman)</button>
          </div>
        )}
        <div className="nav-footer">Repuro &copy; 2026</div>
      </nav>
      <main className="main">
        {error && <div className="error-box">{error}</div>}
        {tab === 'updates' && (
          <>
            <div className="page-title">Weekly Update</div>
            <div className="page-sub">{weekly ? weekly.title : 'No published update yet.'}</div>
            <UpdatesTab body={weekly ? weekly.body : null} />
          </>
        )}
        {tab === 'board' && (
          <>
            <div className="page-title">Board</div>
            <div className="page-sub">{board ? board.title : 'No published board pack yet.'}</div>
            <BoardTab body={board ? board.body : null} />
          </>
        )}
        {tab === 'curate' && isAdmin && (
          <>
            <div className="page-title">Curate</div>
            <div className="page-sub">Edit drafts, review diffs, approve and publish.</div>
            <CurateTab />
          </>
        )}
      </main>
    </div>
  );
}

// Resolve dev-mode (unauthenticated) before mounting so apiFetch sends the right header.
apiFetch('api/config')
  .then(c => { DEV = !!(c && c.dev_mode); })
  .catch(() => { DEV = false; })
  .finally(() => {
    ReactDOM.createRoot(document.getElementById('root')).render(<App />);
  });
