"""City → (region, region_prep) lookup from bundled JSON (extracted from Excel once)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_MAPPING_FILE = Path(__file__).parent.parent / "data" / "region_mapping.json"


@lru_cache(maxsize=1)
def load_region_mapping() -> dict[str, tuple[str, str]]:
    """Return {city_lower: (region, region_prep)}. Cached — reads JSON once per process."""
    if not _MAPPING_FILE.exists():
        return {}
    raw = json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))
    return {k: tuple(v) for k, v in raw.items()}


def lookup_region(city: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (region, region_prep) or (None, None) if city not in mapping."""
    if not city:
        return None, None
    entry = load_region_mapping().get(city.strip().lower())
    return entry if entry else (None, None)
