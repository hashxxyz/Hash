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


def _espn_today_games():
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


def _espn_finished_between(start_day, end_day):
    """Finished games from Lagos date start_day to end_day inclusive, ONE feed call per league (not one per day)."""
    d0, d1 = datetime.strptime(start_day, "%Y-%m-%d"), datetime.strptime(end_day, "%Y-%m-%d")
    out = []
    for league in _leagues():
        events = _scoreboard(league, (d0 - timedelta(days=1)).strftime("%Y%m%d"), d1.strftime("%Y%m%d"))
        for e in events:
            if _status_short(e) not in {"FT", "AOT"}:
                continue
            comp, home, away = _sides(e)
            try:
                hs, aws = int(float(home.get("score"))), int(float(away.get("score")))
            except (TypeError, ValueError, AttributeError):
                continue
            h, a = _team(home), _team(away)
            if h["id"] and a["id"]:
                out.append({"h": h["id"], "a": a["id"], "hs": hs, "as": aws})
    return out


def _espn_games_range(date, days):
    """Upcoming games for Lagos dates `date` .. date+days-1, one feed call per league. Each game carries the odds
    ESPN already lists for it (key "odds_item"), so no extra call is needed per game."""
    days = max(1, min(int(days), 7))
    d0 = datetime.strptime(date, "%Y-%m-%d")
    days_set = {(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)}
    start = (d0 - timedelta(days=1)).strftime("%Y%m%d")
    end = (d0 + timedelta(days=days - 1)).strftime("%Y%m%d")
    out = []
    for league in _leagues():
        try:
            events = _scoreboard(league, start, end)
        except requests.RequestException as e:
            print("BASKETBALL FEED ERROR:", league, e)
            continue
        for e in events:
            dt = _to_lagos(e.get("date"))
            if not dt or dt.strftime("%Y-%m-%d") not in days_set or not e.get("id"):
                continue
            comp, home, away = _sides(e)
            h, a = _team(home), _team(away)
            out.append({"id": f"{league}:{e['id']}", "date": dt.isoformat(),
                        "status": {"short": _status_short(e)}, "teams": {"home": h, "away": a},
                        "league": {"name": LEAGUE_NAMES.get(league, league.upper()), "id": league,
                                   "season": ((e.get("season") or {}).get("year"))},
                        "country": {"name": "USA"}, "odds_item": _odds_item(e)})
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


def _espn_odds(game_id):
    league, _, eid = str(game_id).partition(":")
    day = get_lagos_date()
    for e, _dt in _lagos_day_events(league, day):
        if str(e.get("id")) == eid:
            item = _odds_item(e)
            return [item] if item else []
    return []


# ---------------------------------------------------------------- form
def _espn_team_statistics(league_id, season, team_id):
    # No season-statistics endpoint here: the pipeline falls back to recent results when it sees this error.
    raise RuntimeError("plan: season statistics are not available from this data source")


def _espn_games_on(day):
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


# ================================================================ API-Sports (used first when a key is set)
# Same key as the old setup. Env var names tried, in order: API_SPORTS_KEY, APISPORTS_KEY, API_BASKETBALL_KEY, API_FOOTBALL_KEY.
# Free plans only see yesterday/today/tomorrow and no season statistics: errors fall back to ESPN automatically.
APS_URL = "https://v1.basketball.api-sports.io"
_STATE = {"source": "espn", "error": ""}


def _aps_key():
    for name in ("API_SPORTS_KEY", "APISPORTS_KEY", "API_BASKETBALL_KEY", "API_FOOTBALL_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


def last_source():
    """('apisports' | 'espn', last API-Sports error text) for the diagnostic note."""
    return _STATE["source"], _STATE["error"]


def _aps(endpoint, params):
    r = requests.get(f"{APS_URL}/{endpoint}", headers={"x-apisports-key": _aps_key()}, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    errs = data.get("errors")
    if errs:
        msg = "; ".join(str(v) for v in (errs.values() if isinstance(errs, dict) else errs))
        raise RuntimeError(msg[:200])
    return data.get("response") or []


def _aps_games_on(day):
    return _aps("games", {"date": day, "timezone": "Africa/Lagos"})


def _aps_games(date, days):
    d0 = datetime.strptime(date, "%Y-%m-%d")
    out, last_err, ok = [], "", 0
    for i in range(max(1, min(int(days), 7))):
        day = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            out.extend(_aps_games_on(day))
            ok += 1
        except Exception as e:  # e.g. free plan: day outside the allowed window
            last_err = str(e)[:160]
            print("API-SPORTS BASKETBALL GAMES ERROR:", day, last_err)
    if not ok:
        raise RuntimeError(last_err or "no API-Sports response")
    return out


def _use_aps_first(fetch):
    if _aps_key():
        try:
            games = fetch()
            if games:
                _STATE.update(source="apisports", error="")
                return games
            _STATE["error"] = "API-Sports returned no games"
        except Exception as e:
            _STATE["error"] = str(e)[:160]
            print("API-SPORTS BASKETBALL FALLBACK:", _STATE["error"])
    _STATE["source"] = "espn"
    return None


def get_today_games():
    games = _use_aps_first(lambda: _aps_games(get_lagos_date(), 1))
    return games if games is not None else _espn_today_games()


def get_games_range(date, days):
    games = _use_aps_first(lambda: _aps_games(date, days))
    return games if games is not None else _espn_games_range(date, days)


def _is_espn_id(game_id):
    return ":" in str(game_id)


def get_odds(game_id):
    if _is_espn_id(game_id):
        return _espn_odds(game_id)
    return _aps("odds", {"game": game_id})


def get_team_statistics(league_id, season, team_id):
    if _STATE["source"] == "apisports":
        return _aps("statistics", {"league": league_id, "season": season, "team": team_id})
    return _espn_team_statistics(league_id, season, team_id)


def get_games_on(day):
    if _STATE["source"] == "apisports":
        return _aps_games_on(day)
    return _espn_games_on(day)


def get_finished_between(start_day, end_day):
    if _STATE["source"] == "apisports":  # one call per day on API-Sports: let the pipeline use its budgeted day-by-day path
        raise RuntimeError("API-Sports history is read day by day")
    return _espn_finished_between(start_day, end_day)
