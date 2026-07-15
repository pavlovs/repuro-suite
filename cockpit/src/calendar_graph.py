"""Microsoft Graph calendar integration for Cockpit Calendar module.

Env vars:
  COCKPIT_GRAPH_TENANT        Azure AD tenant ID
  COCKPIT_GRAPH_CLIENT_ID     App registration client ID
  COCKPIT_GRAPH_CLIENT_SECRET App registration client secret
  COCKPIT_CALENDAR_FAKE=1     Return deterministic demo events (dev/test)
"""

import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote  # noqa: F401 — used in Graph URL paths below; a formatter once stripped this as "unused" and broke every real Graph call

import httpx

# UPN = email-shaped, enforced before any Graph call (and quoted on top —
# a stored upn must never be able to redirect the request path).
UPN_RE = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# ---------------------------------------------------------------------------
# Token cache — module-level, keyed (tenant, client_id)
# GIL is sufficient for single-process FastAPI + thread pool usage.
# ---------------------------------------------------------------------------
_token_cache: dict[tuple[str, str], dict] = {}

_GRAPH_BASE = "https://graph.microsoft.com"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_CACHE_TTL = 300  # seconds
_EVENT_FIELDS = (
    "subject,start,end,location,showAs,sensitivity,isAllDay,onlineMeeting,organizer"
)
_TZ_HEADER = "W. Europe Standard Time"


def _env() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (tenant, client_id, client_secret) from env, or (None,None,None)."""
    return (
        os.environ.get("COCKPIT_GRAPH_TENANT"),
        os.environ.get("COCKPIT_GRAPH_CLIENT_ID"),
        os.environ.get("COCKPIT_GRAPH_CLIENT_SECRET"),
    )


def _get_token() -> Optional[str]:
    """Return a valid access token, refreshing when within 60 s of expiry."""
    tenant, client_id, client_secret = _env()
    if not (tenant and client_id and client_secret):
        return None

    key = (tenant, client_id)
    cached = _token_cache.get(key)
    if cached and cached["expires_at"] - time.monotonic() > 60:
        return cached["access_token"]

    url = _TOKEN_URL.format(tenant=tenant)
    try:
        resp = httpx.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        # wrong secret / tenant typo / network down — callers treat None as
        # not_configured instead of a 500 bubbling to the browser
        return None
    payload = resp.json()
    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _token_cache[key] = {
        "access_token": token,
        "expires_at": time.monotonic() + expires_in,
    }
    return token


# ---------------------------------------------------------------------------
# In-memory event cache keyed (upn, start_iso, end_iso)
# ---------------------------------------------------------------------------
_event_cache: dict[tuple[str, str, str], dict] = {}  # key → {events, expires_at}


def _cache_get(key: tuple) -> Optional[list]:
    entry = _event_cache.get(key)
    if entry and entry["expires_at"] > time.monotonic():
        return entry["events"]
    return None


def _cache_set(key: tuple, events: list) -> None:
    # bounded: prune expired on write; hard-reset if still oversized (long-running
    # Fly process + week navigation would otherwise grow the dict forever)
    if len(_event_cache) >= 512:
        now = time.monotonic()
        for k in [k for k, v in _event_cache.items() if v["expires_at"] <= now]:
            del _event_cache[k]
        if len(_event_cache) >= 512:
            _event_cache.clear()
    _event_cache[key] = {
        "events": events,
        "expires_at": time.monotonic() + _CACHE_TTL,
    }


# ---------------------------------------------------------------------------
# Event normalisation
# ---------------------------------------------------------------------------
def _normalise(event: dict, upn: str) -> dict:
    all_day = event.get("isAllDay", False)
    start_block = event.get("start", {})
    end_block = event.get("end", {})
    # Graph returns start/end as {dateTime, timeZone} for EVERY event — including
    # all-day ones (dateTime = local midnight, isAllDay=true). It does NOT send a
    # `date` field here, so reading .date dropped every all-day event to an empty
    # start and made it vanish from the grid. Prefer date when present (defensive)
    # but fall back to dateTime, which is what the live API actually sends.
    if all_day:
        start = start_block.get("date") or start_block.get("dateTime", "")
        end = end_block.get("date") or end_block.get("dateTime", "")
    else:
        start = start_block.get("dateTime", "")
        end = end_block.get("dateTime", "")

    online = event.get("onlineMeeting")
    online_url = online.get("joinUrl") if online else None

    return {
        "upn": upn,
        "subject": event.get("subject", ""),
        "start": start,
        "end": end,
        "all_day": all_day,
        "location": event.get("location", {}).get("displayName", ""),
        "show_as": event.get("showAs", "busy"),
        "private": event.get("sensitivity") in ("private", "personal"),
        "online_url": online_url,
    }


def _fetch_upn_events(upn: str, start_iso: str, end_iso: str, token: str) -> list[dict]:
    cache_key = (upn, start_iso, end_iso)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = (
        f"{_GRAPH_BASE}/v1.0/users/{quote(upn, safe='@')}/calendarView"
        f"?startDateTime={start_iso}&endDateTime={end_iso}"
        f"&$select={_EVENT_FIELDS}"
        f"&$orderby=start/dateTime"
        f"&$top=50"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": f'outlook.timezone="{_TZ_HEADER}"',
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
    except httpx.HTTPError:  # ConnectError, Timeout, protocol errors — all of it
        return []

    if resp.status_code != 200:
        return []

    raw_events = resp.json().get("value", [])
    events = [_normalise(e, upn) for e in raw_events]
    _cache_set(cache_key, events)
    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_events(upns: list[str], start_iso: str, end_iso: str) -> list[dict]:
    """Fetch calendar events for all upns in [start_iso, end_iso].

    Returns a flat list of normalised event dicts sorted by start ascending.
    Returns empty list on timeout or auth failure — callers should not raise.
    """
    if os.environ.get("COCKPIT_CALENDAR_FAKE"):
        return _fake_events(upns, start_iso, end_iso)

    token = _get_token()
    if not token:
        return []

    all_events: list[dict] = []
    for upn in upns:
        all_events.extend(_fetch_upn_events(upn, start_iso, end_iso, token))

    all_events.sort(key=lambda e: e["start"])
    return all_events


def probe_upn(upn: str) -> tuple[bool, str]:
    """Check whether Graph access to upn's calendar is working.

    Returns (True, "ok") on success, (False, reason) on failure.
    reason values: "not_configured", "consent_missing", "unknown_upn", "error_<status>"
    """
    if os.environ.get("COCKPIT_CALENDAR_FAKE"):
        return (True, "ok")

    tenant, client_id, client_secret = _env()
    if not (tenant and client_id and client_secret):
        return (False, "not_configured")

    token = _get_token()
    if not token:
        return (False, "not_configured")

    if not UPN_RE.match(upn):
        return (False, "unknown_upn")

    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    url = (
        f"{_GRAPH_BASE}/v1.0/users/{quote(upn, safe='@')}/calendarView"
        f"?startDateTime={today}T00:00:00&endDateTime={tomorrow}T00:00:00&$top=1"
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
    except httpx.HTTPError:
        return (False, "error_network")

    if resp.status_code == 200:
        return (True, "ok")
    if resp.status_code == 403:
        return (False, "consent_missing")
    if resp.status_code == 404:
        return (False, "unknown_upn")
    return (False, f"error_{resp.status_code}")


# ---------------------------------------------------------------------------
# FAKE mode — deterministic demo events for whatever UPNs are connected.
# Two alternating profiles keyed by sorted-upn position, so any pair of
# connected users gets distinguishable, stable demo data.
# ---------------------------------------------------------------------------
def _fake_events(upns: list[str], start_iso: str, end_iso: str) -> list[dict]:
    """Return a stable set of demo events filtered to the requested upns/range."""
    today = datetime.now(timezone.utc).date()

    def _dt(delta_days: int, hour: int = 9, minute: int = 0) -> str:
        d = today + timedelta(days=delta_days)
        return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"

    # (subject, day_delta, start_h, end_h, location, private, online_url) — None hours = all-day
    _PROFILES = [
        [
            (
                "Team Standup",
                0,
                9,
                9.5,
                "Teams",
                False,
                "https://teams.microsoft.com/l/meetup-join/fake-standup",
            ),
            ("Private Appointment", 1, 11, 12, "", True, None),
            (
                "Investor Call — Strada",
                3,
                14,
                15,
                "Zoom",
                False,
                "https://zoom.us/j/fake-investor-call",
            ),
        ],
        [
            ("Board Sync", 0, 10, 11, "Berlin HQ", False, None),
            ("Out of Office", 2, None, None, "", False, None),
        ],
    ]

    filtered: list[dict] = []
    for upn in sorted(upns):
        # profile keyed by upn content, not set position — a user must see the
        # same demo events whether queried alone (scope=me) or in a team set
        profile = _PROFILES[sum(map(ord, upn)) % 2]
        for subject, delta, h_start, h_end, location, private, online_url in profile:
            all_day = h_start is None
            if all_day:
                start = (today + timedelta(days=delta)).isoformat()
                end = (today + timedelta(days=delta + 1)).isoformat()
            else:
                start = _dt(delta, int(h_start), int((h_start % 1) * 60))
                end = _dt(delta, int(h_end), int((h_end % 1) * 60))
            filtered.append(
                {
                    "upn": upn,
                    "subject": subject,
                    "start": start,
                    "end": end,
                    "all_day": all_day,
                    "location": location,
                    "show_as": "oof" if all_day else "busy",
                    "private": private,
                    "online_url": online_url,
                }
            )

    # Filter to requested time range (string comparison works for ISO dates)
    start_key = start_iso[:19]  # trim to comparable length
    end_key = end_iso[:19]
    filtered = [
        e
        for e in filtered
        if e["start"][:19] >= start_key and e["start"][:19] < end_key
    ]

    filtered.sort(key=lambda e: e["start"])
    return filtered
