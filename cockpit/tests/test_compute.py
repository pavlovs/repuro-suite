"""Table-driven tests for src/compute.py — the product's core logic."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.compute import (
    AMBER,
    GREEN,
    RED,
    deliverable_rollup,
    effective_deadline,
    readiness,
    recommendation,
    schedule_risk,
)

TODAY = date(2026, 6, 11)


def H(ref):  # hard prereq
    return {"ref": ref, "hardness": "hard"}


def S(ref):  # soft prereq
    return {"ref": ref, "hardness": "soft"}


# ---- readiness ----------------------------------------------------------
READINESS_CASES = [
    # (prereqs, status_map, expected)
    ([], {}, GREEN),
    ([H("t-1")], {"t-1": "done"}, GREEN),
    ([H("t-1"), H("t-2")], {"t-1": "done", "t-2": "done"}, GREEN),
    ([H("t-1")], {"t-1": "in_progress"}, AMBER),
    ([H("t-1")], {"t-1": "in_review"}, AMBER),
    ([H("t-1")], {"t-1": "open"}, RED),
    ([H("t-1")], {"t-1": "blocked"}, RED),
    ([H("t-1")], {"t-1": "waiting"}, RED),
    ([H("t-1")], {}, RED),  # dangling hard ref -> red
    ([S("t-1")], {"t-1": "open"}, AMBER),  # soft never red
    ([S("t-1")], {"t-1": "blocked"}, AMBER),
    ([S("t-1")], {"t-1": "in_progress"}, AMBER),  # soft not done blocks green
    ([S("t-1")], {"t-1": "done"}, GREEN),
    ([S("t-1")], {}, AMBER),  # dangling soft -> amber
    ([H("t-1"), S("t-2")], {"t-1": "done", "t-2": "open"}, AMBER),
    ([H("t-1"), S("t-2")], {"t-1": "open", "t-2": "done"}, RED),
    ([H("d-1")], {"d-1": "done"}, GREEN),  # deliverable refs work the same
    ([H("d-1")], {"d-1": "open"}, RED),
    ([H("t-1"), H("t-2")], {"t-1": "in_progress", "t-2": "open"}, RED),  # red wins
]


@pytest.mark.parametrize("prereqs,smap,expected", READINESS_CASES)
def test_readiness(prereqs, smap, expected):
    assert readiness(prereqs, smap.get) == expected


# ---- effective deadline -------------------------------------------------
def test_effective_deadline():
    assert effective_deadline("2026-06-20", "2026-06-30") == "2026-06-20"
    assert effective_deadline(None, "2026-06-30") == "2026-06-30"
    assert effective_deadline(None, None) is None


# ---- schedule risk ------------------------------------------------------
RISK_CASES = [
    # (deadline, readiness, status, chase, expected)
    ("2026-06-10", GREEN, "open", None, ["overdue"]),  # past deadline
    ("2026-06-10", AMBER, "open", None, ["overdue", "at_risk"]),
    ("2026-06-15", AMBER, "open", None, ["at_risk"]),  # within 7d, not green
    ("2026-06-15", GREEN, "open", None, []),  # within 7d but green
    ("2026-06-30", RED, "open", None, []),  # far out
    (None, RED, "open", None, []),  # no deadline
    (None, GREEN, "waiting", "2026-06-11", ["chase"]),  # chase due today
    (None, GREEN, "waiting", "2026-06-01", ["chase"]),  # chase overdue
    (None, GREEN, "waiting", "2026-06-20", []),  # chase in future
    (None, GREEN, "open", "2026-06-01", []),  # chase only when waiting
]


@pytest.mark.parametrize("dl,rd,st,chase,expected", RISK_CASES)
def test_schedule_risk(dl, rd, st, chase, expected):
    assert schedule_risk(dl, rd, st, chase, TODAY) == expected


# ---- recommendation -----------------------------------------------------
REC_CASES = [
    # (status, deadline, pinned, chase, back_by, prereq_soon, expected)
    ("open", "2026-06-10", False, None, None, False, "today"),  # overdue
    ("open", "2026-06-11", False, None, None, False, "today"),  # due today
    ("open", "2026-06-12", False, None, None, False, "today"),  # due tomorrow
    ("open", "2026-06-15", False, None, None, False, "this_week"),
    ("open", "2026-06-18", False, None, None, False, "this_week"),  # exactly +7
    ("open", "2026-06-19", False, None, None, False, "later"),
    ("open", None, False, None, None, False, "later"),
    ("open", None, True, None, None, False, "today"),  # pinned
    ("open", None, False, None, None, True, "this_week"),  # prereq of due-soon
    # waiting: own deadline must NOT surface it
    ("waiting", "2026-06-10", False, None, None, False, "later"),
    ("waiting", "2026-06-10", False, "2026-06-11", None, False, "today"),  # chase due
    (
        "waiting",
        None,
        False,
        "2026-06-20",
        "2026-06-15",
        False,
        "this_week",
    ),  # back soon
    ("waiting", None, False, "2026-06-20", "2026-06-25", False, "later"),
]


@pytest.mark.parametrize("st,dl,pin,chase,back,soon,expected", REC_CASES)
def test_recommendation(st, dl, pin, chase, back, soon, expected):
    assert recommendation(st, dl, pin, chase, back, soon, TODAY) == expected


# ---- deliverable roll-up ------------------------------------------------
def test_rollup_worst_of():
    assert deliverable_rollup([GREEN, AMBER, GREEN], "2026-07-01", TODAY) == (AMBER, [])
    assert deliverable_rollup([GREEN, RED, AMBER], "2026-07-01", TODAY) == (RED, [])
    assert deliverable_rollup([GREEN, GREEN], "2026-07-01", TODAY) == (GREEN, [])
    assert deliverable_rollup([], "2026-07-01", TODAY) == (GREEN, [])


def test_rollup_overdue_forces_risk():
    assert deliverable_rollup([GREEN], "2026-06-01", TODAY) == (GREEN, ["overdue"])
    assert deliverable_rollup([AMBER], "2026-06-15", TODAY) == (AMBER, ["at_risk"])
    assert deliverable_rollup([GREEN], "2026-06-15", TODAY) == (GREEN, [])
