"""DEALROOM v2 — shared UI constants + helpers (used by ui.py and ui_workspace.py)."""

import html
import os

BASE = os.environ.get("DEALROOM_BASE_PATH", "")

SEV_CHIP = {"alert": "chip--alert", "warn": "chip--warn", "info": "chip--info"}
SEV_FLAG = {"alert": "flag--alert", "warn": "flag--warn", "info": "flag--info"}

TERM_STATUS_BADGE = {
    "locked": "badge--brand",
    "agreed": "badge--brand",
    "countered": "badge--alert",
    "proposed": "badge--muted",
    "superseded": "badge--muted",
}

LANE_BADGE = {
    "CDD": "badge--brand",
    "FDD": "badge--muted",
    "QA": "badge--muted",
    "TDD": "badge--muted",
}

CONF_CHIP = {
    "HIGH": "chip--info",
    "MED": "chip",
    "LOW": "chip--warn",
    "UNSCORED": "chip",
}


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""
