import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_workplan import seed


def make_fixture_xlsx(path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Workplan"
    ws.append([])  # row 1 empty (matches real layout: data starts col B, header row 2)
    rows = [
        [
            None,
            "Workstream",
            "Deliverable",
            "Activity",
            "Deadline",
            "Responsible",
            "Priority",
            "Comment",
        ],
        [
            None,
            "Fundraising",
            "Term-sheet",
            "Negotiate final offer",
            "2026-03-20",
            "FF, RD",
            "High",
            "Decision needed",
        ],
        [None, "Fundraising", "Term-sheet", "Sign term sheet", None, None, None, None],
        [
            None,
            "Octopus",
            "Legal DD",
            "Review contracts",
            "2026-06-05",
            "External Legal",
            "Medium",
            None,
        ],
        [
            None,
            "Pipeline",
            None,
            None,
            None,
            None,
            None,
            None,
        ],  # empty activity -> skipped
        [
            None,
            "Admin",
            None,
            "Hire allrounder",
            None,
            None,
            None,
            None,
        ],  # no deliverable
    ]
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_seed_maps_and_is_idempotent(cockpit_db, tmp_path, monkeypatch):
    xlsx = tmp_path / "workplan.xlsx"
    make_fixture_xlsx(xlsx)
    monkeypatch.setenv("COCKPIT_WORKPLAN_XLSX", str(xlsx))

    counts = seed(cockpit_db)
    # Pipeline has no activities but IS a workstream (created empty, filled at curation)
    assert counts == {"workstreams": 4, "deliverables": 3, "tasks": 4, "skipped": 1}

    conn = cockpit_db
    assert conn.execute("SELECT COUNT(*) FROM tasks WHERE staging=1").fetchone()[0] == 4
    assert (
        conn.execute("SELECT COUNT(*) FROM tasks WHERE source='seed-v1'").fetchone()[0]
        == 4
    )
    # priority normalized, deadline ISO
    row = conn.execute(
        "SELECT * FROM tasks WHERE text='Negotiate final offer'"
    ).fetchone()
    assert row["priority"] == "high" and row["deadline"] == "2026-03-20"
    # task without deliverable lands under "(general)"
    row = conn.execute(
        "SELECT d.name FROM tasks t JOIN deliverables d ON t.deliverable_id=d.id "
        "WHERE t.text='Hire allrounder'"
    ).fetchone()
    assert row["name"] == "(general)"

    # re-run: same end state, no duplicates
    counts2 = seed(cockpit_db)
    assert counts2["tasks"] == 4
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM workstreams").fetchone()[0] == 4
