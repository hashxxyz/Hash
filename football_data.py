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


def get_matches_range(date, days):
    """Matches for Lagos dates `date` .. date+days-1 (one call). The window is padded by a day each side for the
    UTC/Lagos offset, and capped so it stays inside Football-Data.org's 10-day limit."""
    days = max(1, min(int(days), 7))
    d0 = datetime.strptime(date, "%Y-%m-%d")
    data = api_request("matches", {"dateFrom": (d0 - timedelta(days=1)).strftime("%Y-%m-%d"),
                                   "dateTo": (d0 + timedelta(days=days)).strftime("%Y-%m-%d")})
    return data.get("matches", [])


def get_finished_matches(competition):
    """Finished matches of the current season of one competition (one call)."""
    data = api_request(f"competitions/{competition}/matches", {"status": "FINISHED"})
    return data.get("matches", [])


# ---------------------------------------------------------------- API-Football (API-Sports), used in addition
# Same key as basketball. Env var names tried, in order: API_SPORTS_KEY, APISPORTS_KEY, API_FOOTBALL_KEY, API_BASKETBALL_KEY.
# Free plans only see yesterday/today/tomorrow and block this season's league statistics.
APS_URL = "https://v3.football.api-sports.io"


def aps_key():
    for name in ("API_SPORTS_KEY", "APISPORTS_KEY", "API_FOOTBALL_KEY", "API_BASKETBALL_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


def _aps(endpoint, params):
    import apisports
    apisports.acquire()
    r = requests.get(f"{APS_URL}/{endpoint}", headers={"x-apisports-key": aps_key()}, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    errs = data.get("errors")
    if errs:
        msg = "; ".join(str(v) for v in (errs.values() if isinstance(errs, dict) else errs))
        raise RuntimeError(msg[:200])
    return data.get("response") or []


def aps_fixtures(date, days=1):
    """Fixtures for Lagos dates date..date+days-1, one call per day. Raises only if every day failed."""
    d0 = datetime.strptime(date, "%Y-%m-%d")
    out, last_err, ok = [], "", 0
    for i in range(max(1, min(int(days), 7))):
        day = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            out.extend(_aps("fixtures", {"date": day, "timezone": "Africa/Lagos"}))
            ok += 1
        except Exception as e:
            last_err = str(e)[:160]
            print("API-FOOTBALL FIXTURES ERROR:", day, last_err)
    if not ok:
        raise RuntimeError(last_err or "no API-Football response")
    return out


def aps_prediction(fixture_id):
    return _aps("predictions", {"fixture": fixture_id})


def aps_odds(fixture_id):
    params = {"fixture": fixture_id}
    if os.environ.get("ODDS_BOOKMAKER"):
        params["bookmaker"] = os.environ["ODDS_BOOKMAKER"]
    return _aps("odds", params)
