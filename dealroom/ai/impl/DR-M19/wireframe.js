/**
 * DR-M19 — Sidebar Restructuring Wireframe
 * Drop-in replacement for renderSidebar() + showSection() + CSS injection.
 * Copy the CSS block into <style>, and replace the two functions in dashboard.html.
 *
 * Backward compatibility: all existing section IDs are preserved unchanged.
 * New section IDs: deal_history, business_model, employees, thesis, market
 */

/* ─────────────────────────────────────────────────────────────────────────────
   CSS — add inside <style> tag in dashboard.html
   ───────────────────────────────────────────────────────────────────────────── */
const DR_M19_CSS = `
.sidebar-block-header {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #64748b;
  padding: 8px 16px 4px;
  font-weight: 600;
  user-select: none;
  pointer-events: none;
}
`;

// Inject CSS once on load
(function injectDRM19CSS() {
  if (document.getElementById('dr-m19-styles')) return;
  const style = document.createElement('style');
  style.id = 'dr-m19-styles';
  style.textContent = DR_M19_CSS;
  document.head.appendChild(style);
})();

/* ─────────────────────────────────────────────────────────────────────────────
   renderSidebar() — replacement
   ───────────────────────────────────────────────────────────────────────────── */
function renderSidebar() {
  let h = '';

  // ── BLOCK A — Deal Economics ──────────────────────────────────────────────
  h += '<div class="sidebar-block-header">Deal Economics</div>';
  h += sidebarItem('onepager',    'One-Pager',             null);
  h += sidebarItem('overview',    'Overview',              null);
  h += sidebarItem('deal_history','Deal History',          'stub');
  h += sidebarItem('financials',  'Valuation & Financials',null);
  h += sidebarItem('offer',       'Offer & Negotiation',   'stub');

  h += '<div class="sidebar-divider"></div>';

  // ── BLOCK B — Business Fundamentals ──────────────────────────────────────
  h += '<div class="sidebar-block-header">Business Fundamentals</div>';
  h += sidebarItem('business_model','Business Model',       'stub');
  h += sidebarItem('customers',    'Customers & Suppliers', null);
  h += sidebarItem('employees',    'Employees',             'stub');
  h += sidebarItem('thesis',       'Thesis & Fit',          'stub');
  h += sidebarItem('market',       'Market & Competition',  'stub');

  h += '<div class="sidebar-divider"></div>';

  // ── BLOCK C — Process Artifacts ───────────────────────────────────────────
  h += '<div class="sidebar-block-header">Process Artifacts</div>';
  h += sidebarItem('rfi',       'RFI',           qOpen > 0 ? qOpen : null);
  h += sidebarItem('dd',        'Due Diligence', 'stub');
  h += sidebarItem('documents', 'Documents',     docCount);
  h += sidebarItem('notes',     'Notes',         noteCount);
  if (flagCount > 0) h += sidebarItem('flags', 'Risk Flags', flagCount);

  document.getElementById('sidebar').innerHTML = h;
}

/* ─────────────────────────────────────────────────────────────────────────────
   showSection(id) — replacement
   Handles all 14 section IDs. [SOON] sections route to stubSection().
   ───────────────────────────────────────────────────────────────────────────── */
function showSection(id) {
  currentSection = id;
  renderSidebar();

  switch (id) {
    // ── Block A — existing sections ────────────────────────────────────────
    case 'onepager':
      showOnepager();
      break;
    case 'overview':
      showOverview();
      break;
    case 'financials':
      showFinancials();
      break;

    // ── Block A — [SOON] ──────────────────────────────────────────────────
    case 'deal_history':
      stubSection('Deal History', 'Timeline of LOIs, term sheets, price changes, and key negotiation milestones.');
      break;
    case 'offer':
      stubSection('Offer & Negotiation', 'Structured offer tracker: Sofortzahlung, earn-out, conditions, counterparty responses.');
      break;

    // ── Block B — existing sections ────────────────────────────────────────
    case 'customers':
      showCustomers();
      break;

    // ── Block B — [SOON] ──────────────────────────────────────────────────
    case 'business_model':
      stubSection('Business Model', 'Revenue streams, margin structure, key dependencies, and operational model summary.');
      break;
    case 'employees':
      stubSection('Employees', 'Headcount by role, key-person risk, retention flags, and org chart.');
      break;
    case 'thesis':
      stubSection('Thesis & Fit', 'Strategic rationale, Repuro platform fit score, synergy hypothesis, and red lines.');
      break;
    case 'market':
      stubSection('Market & Competition', 'Addressable market, competitive landscape, positioning, and regulatory exposure.');
      break;

    // ── Block C — existing sections ────────────────────────────────────────
    case 'rfi':
      showRFI();
      break;
    case 'documents':
      showDocuments();
      break;
    case 'notes':
      showNotes();
      break;
    case 'flags':
      showFlags();
      break;

    // ── Block C — [SOON] ──────────────────────────────────────────────────
    case 'dd':
      stubSection('Due Diligence', 'Legal, financial, and operational DD tracker with open items and sign-off status.');
      break;

    default:
      console.warn('showSection: unknown id', id);
      stubSection(id, 'Section not yet implemented.');
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
   stubSection(title, description) — renders a placeholder for [SOON] sections
   Uses existing #main-content area. Adapt selector to match dashboard.html.
   ───────────────────────────────────────────────────────────────────────────── */
function stubSection(title, description) {
  const container = document.getElementById('main-content') || document.getElementById('content');
  if (!container) return;
  container.innerHTML = `
    <div style="
      display:flex; flex-direction:column; align-items:center; justify-content:center;
      height:60vh; color:#94a3b8; text-align:center; gap:12px;
    ">
      <div style="font-size:32px; opacity:0.4;">⬜</div>
      <div style="font-size:18px; font-weight:600; color:#64748b;">${title}</div>
      <div style="font-size:13px; max-width:360px; line-height:1.6;">${description}</div>
      <div style="
        margin-top:8px; font-size:11px; text-transform:uppercase; letter-spacing:1px;
        background:#1e293b; color:#64748b; padding:4px 12px; border-radius:4px;
      ">Coming soon</div>
    </div>
  `;
}
