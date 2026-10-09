import os
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

BASE_URL = "https://v3.football.api-sports.io"
LAGOS_TZ = ZoneInfo("Africa/Lagos")


def api_request(endpoint, params=None, paging=False):
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise RuntimeError("API_FOOTBALL_KEY is not configured.")
    r = requests.get(f"{BASE_URL}/{endpoint}", headers={"x-apisports-key": key, "Accept": "application/json"}, params=params or {}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    if paging:
        total = int((data.get("paging") or {}).get("total") or 1)
        return data.get("response", []), total
    return data.get("response", [])


def get_lagos_date():
    return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")


def get_today_fixtures():
    return api_request("fixtures", {"date": get_lagos_date(), "timezone": "Africa/Lagos"})


def get_predictions(fixture_id):
    return api_request("predictions", {"fixture": fixture_id})


def get_odds_by_league(league_id, season, page=1):
    """One call returns one page (about 10 fixtures) of a league's odds for today.
    Returns (items, total_pages). Each page is one API call."""
    params = {"league": league_id, "season": season, "date": get_lagos_date(), "timezone": "Africa/Lagos",
              "page": page}
    bookmaker = os.environ.get("ODDS_BOOKMAKER", "").strip()
    if bookmaker:
        params["bookmaker"] = bookmaker
    return api_request("odds", params, paging=True)
