"""Path resolution for foreign read-only DBs (dealroom, pipeline, cockpit).

Each function checks the relevant env var first; falls back to the sibling-repo
default relative to this file's location (i.e. CLAUDE_REPURO/<sub>/data/<db>.db).
"""

import os
from pathlib import Path

# boardroom/src/sources.py  →  CLAUDE_REPURO = parent.parent.parent
_REPO = Path(__file__).resolve().parent.parent.parent


def dealroom_db() -> Path:
    env = os.environ.get("INVESTOR_DEALROOM_DB")
    if env:
        return Path(env)
    return _REPO / "dealroom" / "data" / "dealroom.db"


def pipeline_db() -> Path:
    env = os.environ.get("INVESTOR_PIPELINE_DB")
    if env:
        return Path(env)
    return _REPO / "lead-pipeline" / "data" / "pipeline.db"


def cockpit_db() -> Path:
    env = os.environ.get("INVESTOR_COCKPIT_DB")
    if env:
        return Path(env)
    return _REPO / "cockpit" / "data" / "cockpit.db"
