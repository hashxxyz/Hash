import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://v3.football.api-sports.io"
LAGOS_TZ = ZoneInfo("Africa/Lagos")


def api_request(endpoint, params=None):
    key = os.environ.get("API_FOOTBALL_KEY")
    if not key:
        raise RuntimeError("API_FOOTBALL_KEY is not configured.")

    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        headers={
            "x-apisports-key": key,
            "Accept": "application/json",
        },
        params=params or {},
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))

    return data.get("response", [])


def get_lagos_date():
    return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")


def get_today_fixtures():
    return api_request("fixtures", {"date": get_lagos_date()})


def get_predictions(fixture_id):
    return api_request("predictions", {"fixture": fixture_id})


def get_odds(fixture_id, bookmaker=None):
    params = {"fixture": fixture_id}
    if bookmaker:
        params["bookmaker"] = bookmaker
    return api_request("odds", params)


def get_head_to_head(team_a, team_b, last=5):
    return api_request(
        "fixtures/headtohead",
        {"h2h": f"{team_a}-{team_b}", "last": last},
    )
