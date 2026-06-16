/* ===== Overview — the Cockpit landing (merged with My Week content) ===== */
function delivStats(d) {
  const tasks = TASKS.filter((t) => t.d === d.id);
  const open = tasks.filter((t) => t.status !== "done");
  const done = tasks.length - open.length;
  let r = "green";
  for (const t of open) { const x = readiness(t); if (x === "red") r = "red"; else if (x === "amber" && r !== "red") r = "amber"; }
  return { total: tasks.length, done, open: open.length, readiness: open.length ? r : "green" };
}

function OverviewView({ person, onJump, openTask, mutate }) {
  const dateLine = todayDate.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })
    + " · week " + Math.ceil((((todayDate - new Date(todayDate.getFullYear(), 0, 1)) / 86400000) + new Date(todayDate.getFullYear(), 0, 1).getDay() + 1) / 7);

  return (
    <div className="ov">
      <div className="ov-hero">
        <div>
          <div className="ov-hello">{PEOPLE[person].name}</div>
          <div className="ov-date">{dateLine}</div>
        </div>
      </div>
      <WeekView person={person} mutate={mutate} openTask={openTask} embedded={true} />
    </div>
  );
}
window.OverviewView = OverviewView;
window.delivStats = delivStats;
