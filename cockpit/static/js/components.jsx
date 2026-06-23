/* Shared model helpers + UI atoms. Exported to window for the view scripts. */
const { TODAY, PEOPLE, EXT, SPACES, WORKSTREAMS, DELIVERABLES, TASKS, STAGE_LABEL } = window.COCKPIT_DATA;

const todayDate = new Date(TODAY + "T00:00:00");
const byTask = Object.fromEntries(TASKS.map((t) => [t.id, t]));
const byDeliv = Object.fromEntries(DELIVERABLES.map((d) => [d.id, d]));
const byWs = Object.fromEntries(WORKSTREAMS.map((w) => [w.id, w]));

// dependents: id -> [tasks that list it as a prereq]
const DEPENDENTS = {};
TASKS.forEach((t) => { DEPENDENTS[t.id] = []; });
TASKS.forEach((t) => (t.prereqs || []).forEach((r) => { if (DEPENDENTS[r]) DEPENDENTS[r].push(t.id); }));

function daysUntil(iso) {
  if (!iso) return null;
  return Math.round((new Date(iso + "T00:00:00") - todayDate) / 86400000);
}
function addDays(iso, n) {
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function fdate(iso) {
  if (!iso) return "";
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}
function fdateShort(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.`;
}

// Readiness / risks / recommendation come from the SERVER (compute.py is the
// only truth — hard/soft prereqs, waiting semantics). The UI never recomputes;
// boot.js re-syncs all computed fields after every save.
function readiness(t) {
  return t.computedReadiness || "green";
}
function blockingPrereqs(t) {
  return (t.prereqs || []).map((r) => byTask[r]).filter((p) => p && p.status !== "done");
}
function risks(t) {
  return t.computedRisks || [];
}
function chaseDue(t) {
  return t.status === "waiting" && t.waiting && (!t.waiting.chase || daysUntil(t.waiting.chase) <= 0);
}
function recommendation(t) {
  if (t.status === "done") return "done";
  if (t.pinned) return "today"; // pin is instant; server agrees on next sync
  return t.computedRec || "later";
}

function delivOf(t) { return byDeliv[t.d]; }
function wsOf(t) { const d = byDeliv[t.d]; return d ? byWs[d.ws] : null; }
function dealOf(t) { const d = byDeliv[t.d]; return d ? d.deal : null; }

const STATUS_LABEL = { open: "To do", in_progress: "In progress", waiting: "Waiting", in_review: "In review", done: "Done" };
const STATUS_ORDER = ["open", "in_progress", "waiting", "in_review", "done"];

/* ---------------- UI atoms ---------------- */

function Dot({ level, size = 9, title }) {
  return <span className="rdot" data-level={level} title={title} style={{ width: size, height: size }} />;
}

function ReadinessDot({ t }) {
  const r = readiness(t);
  if (r !== "red") return null;
  return <span className="blocked-label" title={"Needs: " + blockingPrereqs(t).map((p) => p.text).join(", ")}>blocked</span>;
}

function StatusPill({ status }) {
  return <span className="pill" data-status={status}>{STATUS_LABEL[status] || status}</span>;
}

function PriorityFlag({ p }) {
  if (!p || p === "low") return null;
  return <span className="prio" data-prio={p} title={p + " priority"} />;
}

function Avatar({ id, size = 22 }) {
  const p = PEOPLE[id];
  if (p) return <span className="avatar" title={p.full + " · " + p.role} style={{ width: size, height: size, background: p.color, fontSize: size * 0.42 }}>{id}</span>;
  // external
  const meta = EXT[id];
  return <span className="avatar ext" title={id + (meta ? " · " + meta.kind : "")} style={{ width: size, height: size, fontSize: size * 0.34 }}>{id.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>;
}

function OwnerStack({ owners, size = 22 }) {
  if (!owners || !owners.length) return <span className="owner-none">—</span>;
  return (
    <span className="owner-stack">
      {owners.map((o) => <Avatar key={o} id={o} size={size} />)}
    </span>
  );
}

function DealChip({ deal, small }) {
  if (!deal) return null;
  return (
    <span className={"deal-chip" + (small ? " sm" : "")} title={"Stage: " + (STAGE_LABEL[deal.stage] || deal.stage) + " · codename"}>
      <span className="deal-name">{deal.codename}</span>
      <span className="deal-stage">{STAGE_LABEL[deal.stage] || deal.stage}</span>
    </span>
  );
}

function DueChip({ t, plain }) {
  if (!t.due) return <span className="due-chip none">—</span>;
  const du = daysUntil(t.due);
  const over = t.status !== "done" && du < 0;
  const soon = t.status !== "done" && du >= 0 && du <= 7;
  const cls = over ? "overdue" : soon ? "soon" : "";
  return <span className={"due-chip " + cls + (plain ? " plain" : "")}>{fdate(t.due)}</span>;
}

function WaitingChip({ t }) {
  if (t.status !== "waiting" || !t.waiting) return null;
  const noDate = !t.waiting.chase;
  const overdue = !noDate && daysUntil(t.waiting.chase) <= 0;
  return (
    <span className={"wait-flat" + (overdue || noDate ? " due" : "")} title={"Ball with " + t.waiting.party + (noDate ? " · no chase date set" : " · chase " + fdate(t.waiting.chase))}>
      {t.waiting.party}{noDate ? "" : " · " + fdate(t.waiting.chase)}
    </span>
  );
}

/* ---------------- FilterBar — shared collapsible filter UI ---------------- */
// Usage: <FilterBar filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} activeCount={n}>
//          <div className="seg">...</div>
//        </FilterBar>
function FilterBar({ filtersOpen, setFiltersOpen, activeCount, children, hideToggle }) {
  // hideToggle: the toggle lives in the global topbar (next to Activity); render only the body here.
  if (hideToggle) return filtersOpen ? <div className="filter-bar"><div className="filter-bar-body">{children}</div></div> : null;
  return (
    <div className="filter-bar">
      <button
        className={"filter-bar-toggle" + (activeCount > 0 ? " active" : "")}
        onClick={() => setFiltersOpen(f => !f)}
      >
        <Icon name="filter" size={13} />
        Filter
        {activeCount > 0 && <span className="filter-bar-badge">{activeCount}</span>}
        <span className="filter-bar-chevron">{filtersOpen ? "▾" : "▸"}</span>
      </button>
      {filtersOpen && <div className="filter-bar-body">{children}</div>}
    </div>
  );
}

/* Minimal stroke icon set */
function Icon({ name, size = 16 }) {
  const p = {
    cockpit: "M3 12a9 9 0 0 1 18 0M12 12l4-2M12 12v0M12 3v2M21 12h-2M5 12H3M12 12a1 1 0 1 0 .01 0",
    board: "M4 4h5v16H4zM10.5 4h5v10h-5zM17 4h3v7h-3z",
    week: "M4 5h16v15H4zM4 9h16M9 3v4M15 3v4M8 13h3M8 16h3",
    table: "M4 5h16v14H4zM4 10h16M4 14.5h16M9.5 5v14",
    relations: "M6 6a2 2 0 1 0 .01 0M18 6a2 2 0 1 0 .01 0M12 18a2 2 0 1 0 .01 0M7.5 7.5l3 8M16.5 7.5l-3 8M8 6h8",
    timeline: "M4 6h9M4 11h13M4 16h6M16 4v16",
    clock: "M12 7v5l3 2M12 3a9 9 0 1 0 .01 0",
    search: "M11 4a7 7 0 1 0 .01 0M20 20l-4-4",
    plus: "M12 5v14M5 12h14",
    bolt: "M13 3 5 13h5l-1 8 8-10h-5z",
    check: "M5 12l4 4 10-11",
    chevron: "M9 6l6 6-6 6",
    filter: "M4 5h16l-6 8v5l-4 2v-7z",
    bell: "M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6M10 21h4",
    arrow: "M5 12h14M13 6l6 6-6 6",
    raise: "M4 18l5-5 3 3 8-8M16 7h4v4",
    deal: "M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8",
    ops: "M12 9a3 3 0 1 0 .01 0M19 12l1.5-1-1.5-2.6-1.8.6a6 6 0 0 0-1.7-1l-.3-1.9h-3l-.3 1.9a6 6 0 0 0-1.7 1l-1.8-.6L5 9l1.5 1a6 6 0 0 0 0 2L5 13l1.5 2.6 1.8-.6a6 6 0 0 0 1.7 1l.3 1.9h3l.3-1.9a6 6 0 0 0 1.7-1l1.8.6L19 13l-1.5-1a6 6 0 0 0 0-2z",
    pin: "M9 4h6l-1 6 3 3H7l3-3z M12 16v4",
    link: "M9 15l6-6M10 7l1-1a4 4 0 0 1 6 6l-1 1M14 17l-1 1a4 4 0 0 1-6-6l1-1",
  }[name] || "";
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {p.split("M").filter(Boolean).map((seg, i) => <path key={i} d={"M" + seg} />)}
    </svg>
  );
}

const bySpace = Object.fromEntries(SPACES.map((s) => [s.id, s]));
const wsPerSpace = {};
SPACES.forEach((s) => { wsPerSpace[s.id] = []; });
WORKSTREAMS.forEach((w) => { if (wsPerSpace[w.space]) wsPerSpace[w.space].push(w); });

Object.assign(window, {
  TODAY, PEOPLE, EXT, SPACES, WORKSTREAMS, DELIVERABLES, TASKS, STAGE_LABEL,
  todayDate, byTask, byDeliv, byWs, bySpace, wsPerSpace,
  daysUntil, addDays, fdate, fdateShort, readiness, blockingPrereqs, risks, recommendation, chaseDue,
  delivOf, wsOf, dealOf, STATUS_LABEL, STATUS_ORDER, DEPENDENTS,
  Dot, ReadinessDot, StatusPill, PriorityFlag, Avatar, OwnerStack, DealChip, DueChip, WaitingChip, Icon,
  FilterBar,
});
