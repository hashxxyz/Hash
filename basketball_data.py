"""Basketball data from ESPN's public scoreboard feed (no key, covers the current season).

Exposes the same functions the pipeline already used, returning data shaped like the old API-Sports responses,
so pipeline.py and engine.py do not need to change. Leagues come from BB_LEAGUES (default: nba,wnba).
Odds are whatever ESPN lists for the game (total line, moneyline); when a price is not listed, -110 is assumed.
"""
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball"
LAGOS_TZ = ZoneInfo("Africa/Lagos")
LEAGUE_NAMES = {"nba": "NBA", "wnba": "WNBA", "mens-college-basketball": "NCAA Men",
                "womens-college-basketball": "NCAA Women"}
DEFAULT_DECIMAL = 1.91  # -110


def _leagues():
    raw = os.environ.get("BB_LEAGUES", "nba,wnba")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def get_lagos_date():
    return datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")


def _scoreboard(league, start, end):
    """ESPN events for the date range start..end (US dates, YYYYMMDD)."""
    dates = start if start == end else f"{start}-{end}"
    r = requests.get(f"{BASE_URL}/{league}/scoreboard", params={"dates": dates, "limit": 300}, timeout=20)
    r.raise_for_status()
    return r.json().get("events") or []


def _lagos_day_events(league, day):
    """Events whose start time falls on the given Lagos calendar day. Evening US games are the next day in Lagos,
    so the feed is asked for the day before as well."""
    d = datetime.strptime(day, "%Y-%m-%d")
    events = _scoreboard(league, (d - timedelta(days=1)).strftime("%Y%m%d"), d.strftime("%Y%m%d"))
    out = []
    for e in events:
        dt = _to_lagos(e.get("date"))
        if dt and dt.strftime("%Y-%m-%d") == day:
            out.append((e, dt))
    return out


def _to_lagos(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LAGOS_TZ)


def _sides(event):
    comp = (event.get("competitions") or [{}])[0]
    home = away = None
    for c in comp.get("competitors") or []:
        if c.get("homeAway") == "home":
            home = c
        elif c.get("homeAway") == "away":
            away = c
    return comp, home, away


def _team(c):
    t = (c or {}).get("team") or {}
    return {"id": str(t.get("id")) if t.get("id") is not None else None,
            "name": t.get("displayName") or t.get("name")}


def _status_short(event):
    st = ((event.get("status") or {}).get("type")) or {}
    state, name = st.get("state"), str(st.get("name") or "")
    if state == "pre" and "POSTPONED" not in name and "CANCELED" not in name:
        return "NS"
    if state == "post" and st.get("completed") and "FINAL" in name:
        return "AOT" if "OT" in name else "FT"
    return "OTHER"


def get_today_games():
    day = get_lagos_date()
    out = []
    for league in _leagues():
        try:
            events = _lagos_day_events(league, day)
        except requests.RequestException as e:
            print("BASKETBALL FEED ERROR:", league, e)
            continue
        for e, dt in events:
            comp, home, away = _sides(e)
            h, a = _team(home), _team(away)
            if not e.get("id"):
                continue
            out.append({"id": f"{league}:{e['id']}", "date": dt.isoformat(),
                        "status": {"short": _status_short(e)}, "teams": {"home": h, "away": a},
                        "league": {"name": LEAGUE_NAMES.get(league, league.upper()), "id": league,
                                   "season": ((e.get("season") or {}).get("year"))},
                        "country": {"name": "USA"}})
    return out


# ---------------------------------------------------------------- odds
def _american_to_decimal(v):
    try:
        s = str(v).strip().replace("+", "")
        if s.upper() in {"", "EVEN", "EV", "PK"}:
            return 2.0 if s.upper() in {"EVEN", "EV"} else None
        n = float(s)
    except (TypeError, ValueError):
        return None
    if n == 0:
        return None
    return round(1 + (n / 100 if n > 0 else 100 / -n), 3)


def _first(*vals):
    for v in vals:
        if v not in (None, ""):
            return v
    return None


def _moneyline(o, side):
    ml = (o.get("moneyline") or {}).get(side) or {}
    team = o.get(f"{side}TeamOdds") or {}
    return _american_to_decimal(_first((ml.get("close") or {}).get("odds"), (ml.get("open") or {}).get("odds"),
                                       team.get("moneyLine")))


def _odds_item(event):
    comp = (event.get("competitions") or [{}])[0]
    for o in comp.get("odds") or []:
        bets = []
        try:
            line = float(o.get("overUnder"))
        except (TypeError, ValueError):
            line = None
        if line:
            over = _american_to_decimal(o.get("overOdds")) or DEFAULT_DECIMAL
            under = _american_to_decimal(o.get("underOdds")) or DEFAULT_DECIMAL
            bets.append({"name": "Over/Under", "values": [{"value": f"Over {line:g}", "odd": over},
                                                           {"value": f"Under {line:g}", "odd": under}]})
        h, a = _moneyline(o, "home"), _moneyline(o, "away")
        if h and a:
            bets.append({"name": "Home/Away", "values": [{"value": "Home", "odd": h}, {"value": "Away", "odd": a}]})
        if bets:
            return {"bookmakers": [{"bets": bets}]}
    return None


def get_odds(game_id):
    league, _, eid = str(game_id).partition(":")
    day = get_lagos_date()
    for e, _dt in _lagos_day_events(league, day):
        if str(e.get("id")) == eid:
            item = _odds_item(e)
            return [item] if item else []
    return []


# ---------------------------------------------------------------- form
def get_team_statistics(league_id, season, team_id):
    # No season-statistics endpoint here: the pipeline falls back to recent results when it sees this error.
    raise RuntimeError("plan: season statistics are not available from this data source")


def get_games_on(day):
    """Finished games on one Lagos date, shaped like the old API-Sports 'games' response."""
    out = []
    for league in _leagues():
        for e, _dt in _lagos_day_events(league, day):
            short = _status_short(e)
            if short not in {"FT", "AOT"}:
                continue
            comp, home, away = _sides(e)
            try:
                hs, aws = int(float(home.get("score"))), int(float(away.get("score")))
            except (TypeError, ValueError, AttributeError):
                continue
            out.append({"status": {"short": short}, "teams": {"home": _team(home), "away": _team(away)},
                        "scores": {"home": {"total": hs}, "away": {"total": aws}}})
    return out
