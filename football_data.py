import os
import requests
from datetime import datetime

BASE_URL = "https://v3.football.api-sports.io"


def api_request(endpoint, params=None):
    key = os.environ["API_FOOTBALL_KEY"]

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
        raise Exception(str(data["errors"]))

    return data.get("response", [])


def get_today_fixtures():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return api_request("fixtures", {"date": today})


def get_fixture_details(fixture_id):
    return api_request("fixtures", {"id": fixture_id})


def get_predictions(fixture_id):
    return api_request("predictions", {"fixture": fixture_id})


def get_odds(fixture_id):
    return api_request("odds", {"fixture": fixture_id})


def get_head_to_head(team_a, team_b):
    return api_request(
        "fixtures/headtohead",
        {"h2h": f"{team_a}-{team_b}", "last": 10},
    )
