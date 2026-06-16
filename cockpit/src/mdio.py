"""MD import parsing + export rendering (§6.2 of DESIGN-SPEC).
Import is fail-closed and all-or-nothing: any error rejects the whole push.
Only two block types exist: task-update (id required) and new-task.
No deal-status block — deal stage enters only via the dealroom.db mirror."""

import re
from datetime import date

from . import models

UPDATE_KEYS = {
    "id",
    "version",
    "status",
    "evidence",
    "deadline",
    "priority",
    "text",
    "detail",
    "responsible",
    "waiting_on_party",
    "waiting_on_type",
    "next_chase_date",
    "expected_back_by",
    "pinned_today",
    "deal",
}
NEW_KEYS = {
    "space",
    "workstream",
    "deliverable",
    "text",
    "deadline",
    "responsible",
    "prereq",
    "execution",
    "priority",
    "kind",
    "detail",
    "deal",
    "acceptance_criteria",
    "runner",
}
_DATE_KEYS = {"deadline", "next_chase_date", "expected_back_by"}
_ENUMS = {
    "status": models.STATUSES,
    "priority": models.PRIORITIES,
    "execution": models.EXECUTIONS,
    "kind": models.KINDS,
    "waiting_on_type": models.WAITING_TYPES,
    "runner": models.RUNNERS,
}
_PREREQ_RE = re.compile(r"^([td]-\d+)(?:\((hard|soft)\))?$")


def _validate_value(key, value, lineno, errors):
    if key in _DATE_KEYS:
        try:
            date.fromisoformat(value)
        except ValueError:
            errors.append(f"line {lineno}: {key} not YYYY-MM-DD: {value!r}")
    elif key in _ENUMS and value not in _ENUMS[key]:
        errors.append(
            f"line {lineno}: invalid {key} {value!r} (allowed: {', '.join(_ENUMS[key])})"
        )
    elif key == "pinned_today" and value not in ("true", "false"):
        errors.append(f"line {lineno}: pinned_today must be true/false")
    elif key == "id":
        try:
            prefix, _ = models.parse_ref(value)
            if prefix != "t":
                raise ValueError
        except ValueError:
            errors.append(f"line {lineno}: id must be t-<n>, got {value!r}")
    elif key == "version" and not value.lstrip("v").isdigit():
        errors.append(f"line {lineno}: version must be an integer (got {value!r})")


def _parse_prereqs(value, lineno, errors):
    prereqs = []
    for part in [p.strip() for p in value.split(",") if p.strip()]:
        m = _PREREQ_RE.match(part)
        if not m:
            errors.append(f"line {lineno}: bad prereq {part!r} (want t-<n>(hard|soft))")
            continue
        ref, hardness = m.group(1), m.group(2) or "hard"
        # normalize zero-padded numbers: t-031 -> t-31
        prefix, num = models.parse_ref(ref)
        prereqs.append({"ref": f"{prefix}-{num}", "hardness": hardness})
    return prereqs


def parse_push(md_text):
    """Returns (updates, creates, errors). updates/creates are lists of dicts.
    Any entry in errors means the caller must reject the entire push."""
    updates, creates, errors = [], [], []
    section = None
    items = []  # (lineno, joined_text, section)
    for lineno, raw in enumerate(md_text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("# cockpit-push"):
            continue
        if line.startswith("## "):
            name = line[3:].strip().lower()
            if name not in ("task-update", "new-task"):
                errors.append(f"line {lineno}: unknown block {name!r}")
                section = None
            else:
                section = name
        elif line.startswith("- "):
            if section is None:
                errors.append(f"line {lineno}: item outside a known block")
            else:
                items.append([lineno, line[2:], section])
        elif line.startswith((" ", "\t")) and line.strip().startswith("|") and items:
            items[-1][1] += (
                " " + line.strip().lstrip("|").strip()
                and (" | " + line.strip().lstrip("|").strip())
                or ""
            )
        else:
            errors.append(f"line {lineno}: unparseable line {line!r}")

    for lineno, text, section in items:
        fields = {}
        for pair in text.split("|"):
            pair = pair.strip()
            if not pair:
                continue
            key, sep, value = pair.partition(":")
            key, value = key.strip(), value.strip()
            if not sep or not value:
                errors.append(f"line {lineno}: malformed pair {pair!r}")
                continue
            allowed = UPDATE_KEYS if section == "task-update" else NEW_KEYS
            if key not in allowed:
                errors.append(f"line {lineno}: unknown key {key!r} for {section}")
                continue
            if key == "prereq":
                fields["prereqs"] = _parse_prereqs(value, lineno, errors)
            else:
                _validate_value(key, value, lineno, errors)
                fields[key] = value if key != "pinned_today" else (value == "true")
        if section == "task-update":
            for req in (
                "id",
                "version",
            ):  # version: stale pushes must conflict, not overwrite
                if req not in fields:
                    errors.append(f"line {lineno}: task-update requires {req}")
            if "id" in fields and "version" in fields:
                fields["version"] = int(str(fields["version"]).lstrip("v"))
                fields["_line"] = lineno
                updates.append(fields)
        else:
            for req in ("workstream", "text"):
                if req not in fields:
                    errors.append(f"line {lineno}: new-task requires {req}")
            fields["_line"] = lineno
            creates.append(fields)
    return updates, creates, errors


def render_export(state, scope):
    """Deterministic markdown from an assembled state dict (api.assemble_state)."""
    out = [
        f"# cockpit-export | scope: {scope} | synced: {state['meta'].get('mirror_synced_at')}"
    ]

    def task_line(t):
        box = "x" if t["status"] == "done" else " "
        prereqs = ",".join(f"{p['ref']}({p['hardness']})" for p in t["prereqs"]) or "-"
        risks = ",".join(t["computed"]["risks"]) or "-"
        return (
            f"- [{box}] {t['id']} | {t['text']} | {t['computed']['effective_deadline'] or '-'}"
            f" | {t['responsible'] or '-'} | {t['status']} | {t['computed']['readiness']}"
            f" | {risks} | {prereqs} | v{t['version']}"
        )

    for space in state["spaces"]:
        if not space["workstreams"]:
            continue
        out.append(f"\n## {space['name']}")
        for ws in space["workstreams"]:
            deal = (
                f" | deal: {ws['deal']['codename']} ({ws['deal']['stage']})"
                if ws.get("deal")
                else ""
            )
            out.append(f"\n### {ws['name']} ({ws['id']}){deal}")
            for d in ws["deliverables"]:
                out.append(
                    f"\n#### {d['name']} ({d['id']}) | target: {d['target_date'] or '-'}"
                    f" | {d['computed']['readiness']}"
                    + (" | staging" if d["staging"] else "")
                )
                for t in d["tasks"]:
                    out.append(task_line(t))
    if state["standalone_tasks"]:
        out.append("\n## (standalone)")
        for t in state["standalone_tasks"]:
            out.append(task_line(t))
    return "\n".join(out) + "\n"
