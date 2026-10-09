"""Football-Data.org v4 client (free tier: 12 competitions, 10 calls/minute, no odds)."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://api.football-data.org/v4"
LAGOS_TZ = ZoneInfo("Africa/Lagos")
UTC = ZoneInfo("UTC")


def api_request(endpoint, params=None):
    key = os.environ.get("FOOTBALL_DATA_KEY")
    if not key:
        raise RuntimeError("FOOTBALL_DATA_KEY is not configured.")
    r = requests.get(f"{BASE_URL}/{endpoint}", headers={"X-Auth-Token": key}, params=params or {}, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("Football-Data.org rate limit reached (10 calls/minute). Try again in a minute.")
    if r.status_code in (401, 403):
        raise RuntimeError(f"Football-Data.org refused the request ({r.status_code}): {r.text[:120]}")
    r.raise_for_status()
    return r.json()


def get_lagos_date():
    return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")


def to_lagos_hhmm(utc_date):
    """'2026-10-09T19:00:00Z' -> ('2026-10-09', '20:00') in Lagos time."""
    try:
        dt = datetime.strptime(utc_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).astimezone(LAGOS_TZ)
    except (TypeError, ValueError):
        return "", ""
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def get_today_matches(date):
    """Matches of the competitions on your plan, Lagos date `date` (one call)."""
    nxt = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    prev = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    data = api_request("matches", {"dateFrom": prev, "dateTo": nxt})
    return data.get("matches", [])


def get_finished_matches(competition):
    """Finished matches of the current season of one competition (one call)."""
    data = api_request(f"competitions/{competition}/matches", {"status": "FINISHED"})
    return data.get("matches", [])
