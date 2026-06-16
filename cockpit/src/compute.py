"""Pure computed logic: readiness, schedule risk, recommendation, roll-ups.
No DB access — callers supply resolver callables. Dates are ISO 'YYYY-MM-DD' strings.

Rules locked in ai/PLAN-M1.md (Locked decisions / Computed logic). The one
interpretation note: a dangling prereq ref (points at nothing) is AMBER, never
green — fail visible, not fail blocking.
"""

from datetime import date, timedelta

GREEN, AMBER, RED = "green", "amber", "red"
_RED_STATUSES = {"open", "blocked", "waiting"}  # a hard prereq in these = cannot start

STAGE_WEIGHTS = {
    "signing": 100,
    "spa": 90,
    "dd": 80,
    "loi_signed": 70,
    "indicative_offer": 60,
    "valuation_rfi": 50,
    "nda": 40,
    "initial_contact": 30,
    "screening": 20,
    "on_hold": 10,
    "dead": 5,
}
_LOI_PLUS = {"loi_signed", "dd", "spa", "signing"}
_HIDDEN_STAGES = {"on_hold", "dead"}


def stage_weight(stage):
    return STAGE_WEIGHTS.get(stage, 0)


def deal_visibility(deal_codename, stage):
    if not deal_codename:
        return "expanded"
    if stage in _LOI_PLUS:
        return "expanded"
    if stage in _HIDDEN_STAGES:
        return "hidden"
    return "collapsed"


def _d(iso):
    return date.fromisoformat(iso) if iso else None


def effective_deadline(task_deadline, deliverable_target):
    return task_deadline or deliverable_target or None


def readiness(prereqs, status_of):
    """prereqs: [{'ref': 't-3'|'d-2', 'hardness': 'hard'|'soft'}].
    status_of(ref) -> status string, or None for a dangling ref.
    green: all hard done AND no soft (or dangling) in a not-started state
    red:   any hard prereq open/blocked/waiting (or hard dangling)
    amber: everything else (hard in_progress/in_review, soft not done, dangling soft)
    """
    if not prereqs:
        return GREEN
    color = GREEN
    for p in prereqs:
        st = status_of(p["ref"])
        hard = p.get("hardness", "hard") == "hard"
        if st == "done":
            continue
        if hard and (st is None or st in _RED_STATUSES):
            return RED
        color = AMBER  # hard progressing, or soft not done, or soft dangling
    return color


def schedule_risk(eff_deadline, task_readiness, status, next_chase_date, today):
    """Returns a list (possibly empty) of 'overdue' | 'at_risk' | 'chase'."""
    risks = []
    dl = _d(eff_deadline)
    if dl and dl < today:
        risks.append("overdue")
    if dl and dl <= today + timedelta(days=7) and task_readiness != GREEN:
        risks.append("at_risk")
    if status == "waiting" and next_chase_date and _d(next_chase_date) <= today:
        risks.append("chase")
    return risks


def recommendation(
    status,
    eff_deadline,
    pinned_today,
    next_chase_date,
    expected_back_by,
    prereq_of_due_soon,
    today,
):
    """'today' | 'this_week' | 'later'. Done tasks are the caller's concern.
    waiting tasks never surface via their own deadline — only chase/expected_back.
    """
    dl = _d(eff_deadline)
    if status == "waiting":
        if next_chase_date and _d(next_chase_date) <= today:
            return "today"
        if expected_back_by and _d(expected_back_by) <= today + timedelta(days=7):
            return "this_week"
        return "later"
    if pinned_today:
        return "today"
    if dl and dl <= today + timedelta(days=1):  # overdue or due today/tomorrow
        return "today"
    if dl and dl <= today + timedelta(days=7):
        return "this_week"
    if prereq_of_due_soon:
        return "this_week"
    return "later"


def deliverable_rollup(open_task_readiness, target_date, today):
    """(readiness, risks) for a deliverable. Worst readiness among open tasks;
    overdue target forces 'overdue' risk."""
    worst = GREEN
    for r in open_task_readiness:
        if r == RED:
            worst = RED
            break
        if r == AMBER:
            worst = AMBER
    risks = []
    td = _d(target_date)
    if td and td < today:
        risks.append("overdue")
    elif td and td <= today + timedelta(days=7) and worst != GREEN:
        risks.append("at_risk")
    return worst, risks
