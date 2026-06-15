"""Enum constants and ID helpers. IDs are exposed as t-<n>/d-<n>/w-<n> at the API
boundary and stored as integer PKs."""

STATUSES = ("open", "in_progress", "waiting", "blocked", "in_review", "done")
EXECUTIONS = ("me", "together", "agent_supervised", "agent_auto")
AGENT_EXECUTIONS = ("agent_supervised", "agent_auto")
KINDS = ("workplan", "followup", "approval", "agent_job", "personal")
HARDNESS = ("hard", "soft")
WAITING_TYPES = ("counterparty", "advisor", "investor", "internal")
PRIORITIES = ("high", "med", "low")
RUNNERS = ("local", "cma", "any")
WS_STATUSES = ("active", "parked", "done")
DELIV_STATUSES = ("open", "done", "dropped")


def task_id(n: int) -> str:
    return f"t-{n}"


def deliv_id(n: int) -> str:
    return f"d-{n}"


def ws_id(n: int) -> str:
    return f"w-{n}"


def parse_ref(ref: str):
    """'t-41' -> ('t', 41). Raises ValueError on anything else."""
    prefix, _, num = ref.partition("-")
    if prefix not in ("t", "d", "w") or not num.isdigit():
        raise ValueError(f"bad ref: {ref!r}")
    return prefix, int(num)
