import os
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

BASE_URL = "https://v1.basketball.api-sports.io"
LAGOS_TZ = ZoneInfo("Africa/Lagos")


def api_request(endpoint, params=None):
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise RuntimeError("API_FOOTBALL_KEY is not configured.")
    r = requests.get(f"{BASE_URL}/{endpoint}", headers={"x-apisports-key": key, "Accept": "application/json"}, params=params or {}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data.get("response", [])


def get_lagos_date():
    return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")


def get_today_games():
    return api_request("games", {"date": get_lagos_date(), "timezone": "Africa/Lagos"})


def get_odds(game_id):
    return api_request("odds", {"game": game_id})


def get_team_statistics(league_id, season, team_id):
    return api_request("statistics", {"league": league_id, "season": season, "team": team_id})
