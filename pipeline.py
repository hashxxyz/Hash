import json
import os
import time
from datetime import datetime, timedelta
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import engine
import store
from agents import ask_json, scrub
from basketball_data import (get_today_games, get_games_range, get_finished_between, last_source, norm_team, get_odds as basketball_odds,
                             get_team_statistics, get_games_on)
from football_data import (get_today_matches, get_matches_range, get_finished_matches, get_lagos_date,
                           to_lagos_hhmm, aps_key, aps_fixtures, aps_prediction, aps_odds)
from render import render_report, MODE_SECTIONS


def _num_env(cast, name, default):
    try:
        return cast(os.environ.get(name, default))
    except ValueError:
        return default


def _int_env(name, default):
    return _num_env(int, name, default)


def _float_env(name, default):
    return _num_env(float, name, default)


# API-Sports free plan = 100 calls/day and about 10 calls/minute PER API. Defaults keep a football scan at
# 1 + 4 + 5 = 10 calls and a basketball scan at 1 + 4 + 5 = 10 calls. Odds, predictions and team statistics are
# cached, so repeated scans spend their calls on matches that are not covered yet.
MAX_FOOTBALL = _int_env("MAX_FOOTBALL", 30)
FOOTBALL_ODDS_CALLS = _int_env("FOOTBALL_ODDS_CALLS", 4)         # odds API calls per scan
ODDS_MAX_PAGES = _int_env("ODDS_MAX_PAGES", 2)                   # pages read per league
FOOTBALL_PREDICTION_CALLS = _int_env("FOOTBALL_PREDICTION_CALLS", 5)
MAX_BASKETBALL = _int_env("MAX_BASKETBALL", 12)
BASKETBALL_ODDS_CALLS = _int_env("BASKETBALL_ODDS_CALLS", 4)
BASKETBALL_STATS_CALLS = _int_env("BASKETBALL_STATS_CALLS", 5)
MIN_CONFIDENCE = _int_env("MIN_CONFIDENCE", 6)                   # "strong" = this or higher
MIN_PROB = _float_env("MIN_PROB", 60) / 100                      # football: minimum blended probability
MIN_BB_PROB = _float_env("MIN_BB_PROB", 56) / 100                # basketball: minimum blended probability
MIN_ODDS = _float_env("MIN_ODDS", 1.30)
MAX_ODDS = _float_env("MAX_ODDS", 3.0)
BB_MIN_GAP = _float_env("BB_MIN_GAP", 4.0)                       # points between model total and the line
MAX_PROBABILITY = 88                                              # never show 100%
CACHE_SECONDS = _int_env("CACHE_SECONDS", 30 * 60)
ODDS_CACHE_SECONDS = _int_env("ODDS_CACHE_SECONDS", 3600)        # longer = more matches covered over repeated scans
BB_HISTORY_DAYS = _int_env("BB_HISTORY_DAYS", 14)                # recent-results window for basketball form
PREDICTION_CACHE_SECONDS = _int_env("PREDICTION_CACHE_SECONDS", 6 * 3600)
STATS_CACHE_SECONDS = _int_env("STATS_CACHE_SECONDS", 12 * 3600)
TIME_BUDGET = _int_env("TIME_BUDGET", 55)
BUILD = "v7"                                                # shown in the /week basketball note: confirms which code Vercel is running
WEEK_DAYS = 7                                                    # /week looks this many days ahead (Football-Data caps a range at 10 days)
WEEK_MAX_FOOTBALL = _int_env("WEEK_MAX_FOOTBALL", 40)            # strongest football matches sent to the AI in /week
WEEK_MAX_BASKETBALL = _int_env("WEEK_MAX_BASKETBALL", 20)

# (league name, country), lower-case. Matching on the name alone also hit "Premier League" in Egypt, Russia, etc.
PRIORITY_LEAGUES = {(n.lower(), c.lower()) for n, c in [
    ("Premier League", "England"), ("La Liga", "Spain"), ("Serie A", "Italy"), ("Bundesliga", "Germany"),
    ("Ligue 1", "France"), ("UEFA Champions League", "World"), ("UEFA Europa League", "World"),
    ("UEFA Europa Conference League", "World"), ("Eredivisie", "Netherlands"), ("Primeira Liga", "Portugal"),
    ("Süper Lig", "Turkey"), ("Championship", "England"), ("Serie B", "Italy"), ("La Liga 2", "Spain"),
    ("2. Bundesliga", "Germany"), ("Ligue 2", "France"), ("Jupiler Pro League", "Belgium"),
    ("Scottish Premiership", "Scotland"), ("Major League Soccer", "USA")]}
PRIORITY_BASKETBALL = {"nba", "euroleague", "eurocup", "wnba", "liga acb", "acb", "nbl", "lnb", "bbl", "bsl",
                       "vtb united league", "lega a", "basketball champions league"}

CATEGORIES = {"OVER", "UNDER", "1X2", "DOUBLE_CHANCE", "BTTS", "BB_OVER", "BB_UNDER", "BB_WINNER"}
RISK_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _cache_key(date, *parts):
    return ":".join(["guru", date, *map(str, parts)])


def _trim_totals(values, keep=3):
    """Keep only the most balanced lines (smallest over/under price gap), which is where the main line sits."""
    lines = {}
    for label, odd in values.items():
        d, ln = engine.parse_ou(label)
        if d:
            lines.setdefault(ln, {})[d] = odd
    gaps = sorted((abs(v["over"] - v["under"]), ln) for ln, v in lines.items() if "over" in v and "under" in v)
    if not gaps:
        return values
    best = {ln for _, ln in gaps[:keep]}
    return {k: o for k, o in values.items() if engine.parse_ou(k)[1] in best}


def parse_basketball_odds(items):
    out = {}
    for item in items or []:
        for bm in item.get("bookmakers") or []:
            for bet in bm.get("bets") or []:
                n = str(bet.get("name") or "").lower()
                key = "Home/Away" if n == "home/away" else "Total O/U" if n == "over/under" else None
                if not key or key in out:
                    continue
                values = {}
                for v in bet.get("values") or []:
                    try:
                        values[str(v.get("value"))] = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                if key == "Total O/U":
                    values = _trim_totals(values)
                if values:
                    out[key] = values
    return out


# ---------------------------------------------------------------- football collection (Football-Data.org)
# Free tier = 10 calls/minute and no odds. A scan costs 1 call for today's matches plus 1 call per competition
# that has a match today (results are cached for STATS_CACHE_SECONDS). Picks come from the goals model alone.
FD_MAX_COMPETITIONS = _int_env("FD_MAX_COMPETITIONS", 8)
FD_RESULTS_CACHE = _int_env("FD_RESULTS_CACHE_SECONDS", 12 * 3600)
ENABLE_BASKETBALL = os.environ.get("ENABLE_BASKETBALL", "true").strip().lower() not in {"0", "false", "no", "off"}


def _is_plan_error(msg):
    m = str(msg).lower()
    return "plan" in m or "subscription" in m or "not available" in m


def football_summary(m, date):
    comp, area = m.get("competition") or {}, m.get("area") or {}
    day, hhmm = to_lagos_hhmm(m.get("utcDate"))
    return {"id": m.get("id"), "day": day, "kickoff": hhmm, "status": m.get("status"),
            "league": comp.get("name"), "code": comp.get("code"), "country": area.get("name"),
            "home": (m.get("homeTeam") or {}).get("name"), "away": (m.get("awayTeam") or {}).get("name"),
            "home_id": (m.get("homeTeam") or {}).get("id"), "away_id": (m.get("awayTeam") or {}).get("id")}


def _window(date, days):
    d0 = datetime.strptime(date, "%Y-%m-%d").date()
    return {(d0 + timedelta(days=i)).isoformat() for i in range(days)}


def _when(day, hhmm, days):
    """Kickoff label: just the time for a single day, 'Sat 10 Oct 20:00' when scanning several days."""
    if days <= 1:
        return hhmm
    try:
        return datetime.strptime(day, "%Y-%m-%d").strftime("%a %d %b") + f" {hhmm}"
    except ValueError:
        return hhmm


def _football_fixtures(date, days=1):
    key = _cache_key(date, "fd", "fixtures") if days <= 1 else _cache_key(date, "fd", "fixtures", f"{days}d")
    usable = store.get_json(key)
    if usable is None:
        window = _window(date, days)
        matches = get_today_matches(date) if days <= 1 else get_matches_range(date, days)
        usable = [s for s in (football_summary(m, date) for m in matches)
                  if s["day"] in window and s["status"] in {"SCHEDULED", "TIMED"}
                  and s["home_id"] and s["away_id"] and s["id"]]
        store.set_json(key, usable, CACHE_SECONDS)
    return usable


def _competition_results(code):
    key = f"guru:fdresults:{code}"
    hit = store.get_json(key)
    if hit is None:
        hit = []
        for m in get_finished_matches(code):
            sc = m.get("score") or {}
            ft = sc.get("regularTime") or sc.get("fullTime") or {}  # 90 minutes, not extra time / penalties
            h, a = (m.get("homeTeam") or {}).get("id"), (m.get("awayTeam") or {}).get("id")
            if None not in (ft.get("home"), ft.get("away"), h, a):
                hit.append({"h": h, "a": a, "hs": ft["home"], "as": ft["away"], "d": (m.get("utcDate") or "")[:10]})
        hit.sort(key=lambda g: g["d"])
        store.set_json(key, hit, FD_RESULTS_CACHE)
    return hit


def collect_football(date, days=1):
    notes, usable = [], _football_fixtures(date, days)
    counts = Counter(s["code"] for s in usable)

    def rank(s):  # top competitions first, then the ones with the most matches in the window
        return (-counts[s["code"]], s["code"] or "", s["day"], s["kickoff"])

    usable.sort(key=rank)
    codes = []
    for s in usable:
        if s["code"] and s["code"] not in codes:
            codes.append(s["code"])
    results, failed, last_err = {}, 0, ""
    for code in codes[:FD_MAX_COMPETITIONS]:
        try:
            results[code] = _competition_results(code)
        except Exception as e:
            failed += 1
            last_err = scrub(e)[:160]
            print("RESULTS ERROR:", last_err)
    if failed:
        notes.append(f"Results were unavailable for {failed} competition(s): {last_err}")
    if len(codes) > FD_MAX_COMPETITIONS:
        notes.append(f"Only the {FD_MAX_COMPETITIONS} busiest competitions were analysed today.")

    research = []
    for s in (usable if days > 1 else usable[:MAX_FOOTBALL]):
        games = results.get(s["code"])
        if not games:
            continue
        model = engine.football_model_from_results(s["home_id"], s["away_id"], games)
        if not model:
            continue
        cands = [c for c in engine.football_candidates_model(model, s["home"], s["away"], MIN_PROB)
                 if c["n"] >= MIN_CONFIDENCE]
        if cands:
            research.append({"id": f"f{s['id']}", "sport": "football", "match": f"{s['home']} vs {s['away']}",
                             "league": f"{s['league']} ({s['country']})" if s["country"] else s["league"],
                             "kickoff": _when(s["day"], s["kickoff"], days), "cands": cands,
                             "ctx": {"exp_goals": model["exp"], "home_xg": model["lh"], "away_xg": model["la"],
                                     "games_used": model["n"]}})
    if days > 1 and len(research) > WEEK_MAX_FOOTBALL:  # keep the strongest matches so the AI prompt stays small
        research.sort(key=lambda r: max((c["n"], c["p"]) for c in r["cands"]), reverse=True)
        research = research[:WEEK_MAX_FOOTBALL]
        notes.append(f"Only the {WEEK_MAX_FOOTBALL} strongest football matches of the week were reviewed.")
    if usable and not results:
        notes.append("No competition results could be loaded, so no match could be modelled.")
    notes.append("Football picks come from a goals model on this season's results. No bookmaker odds are used.")
    return research, notes


# ---------------------------------------------------------------- football via API-Football (API-Sports), in addition
def parse_football_odds(items):
    names = {"match winner": "1X2", "goals over/under": "Goals O/U", "both teams score": "BTTS", "double chance": "Double Chance"}
    out = {}
    for item in items or []:
        for bm in item.get("bookmakers") or []:
            for bet in bm.get("bets") or []:
                key = names.get(str(bet.get("name") or "").lower())
                if not key or key in out:
                    continue
                values = {}
                for v in bet.get("values") or []:
                    try:
                        values[str(v.get("value"))] = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                if key == "Goals O/U":
                    values = _trim_totals(values)
                if values:
                    out[key] = values
    return out


_SKIP_WORDS = {"fc", "cf", "ac", "as", "sc", "afc", "us", "ss", "sv", "fk", "club", "de", "the", "calcio", "and", "e"}


def _team_key(name):
    """Longest meaningful word of a team name, to match the same club across two data sources."""
    words = [w for w in "".join(ch if ch.isalpha() else " " for ch in str(name or "").lower()).split() if w not in _SKIP_WORDS]
    return max(words, key=len) if words else ""


def _match_key(day, home, away):
    return (day, _team_key(home), _team_key(away))


def collect_football_aps(date, days=1, skip=frozenset()):
    """Football-Data.org covers 12 competitions; this adds every other league the API-Sports key can see.
    Matches already handled by the other source (same day + clubs) are skipped."""
    notes = []
    key = _cache_key(date, "aps", "fixtures", f"{days}d")
    fixtures = store.get_json(key)
    if fixtures is None:
        window, fixtures = _window(date, days), []
        for f in aps_fixtures(date, days):
            fx, lg, tm = f.get("fixture") or {}, f.get("league") or {}, f.get("teams") or {}
            day, hhmm = (fx.get("date") or "")[:10], (fx.get("date") or "")[11:16]
            if day in window and str((fx.get("status") or {}).get("short") or "").upper() == "NS" and fx.get("id"):
                fixtures.append({"id": fx["id"], "day": day, "kickoff": hhmm, "league": lg.get("name"), "country": lg.get("country"),
                                 "home": (tm.get("home") or {}).get("name"), "away": (tm.get("away") or {}).get("name")})
        store.set_json(key, fixtures, CACHE_SECONDS)
    fixtures = [f for f in fixtures if f["home"] and f["away"] and _match_key(f["day"], f["home"], f["away"]) not in skip]
    fixtures.sort(key=lambda f: ((str(f["league"]).lower(), str(f["country"]).lower()) not in PRIORITY_LEAGUES, f["day"], f["kickoff"]))

    pred_left, odds_left, failed, last_err, research = FOOTBALL_PREDICTION_CALLS, FOOTBALL_ODDS_CALLS, 0, "", []
    for f in fixtures:
        pk = _cache_key(date, "aps", "pred", f["id"])
        pred = store.get_json(pk)
        if pred is None:
            if pred_left <= 0:
                continue
            pred_left -= 1
            try:
                pred = aps_prediction(f["id"]) or []
            except Exception as e:
                failed += 1
                last_err = scrub(e)[:160]
                print("API-FOOTBALL PREDICTION ERROR:", last_err)
                continue
            store.set_json(pk, pred, PREDICTION_CACHE_SECONDS)
        model = engine.football_model(pred)
        if not model:
            continue
        ok = _cache_key(date, "aps", "odds", f["id"])
        odds = store.get_json(ok)
        if odds is None and odds_left > 0:
            odds_left -= 1
            try:
                odds = parse_football_odds(aps_odds(f["id"]))
                store.set_json(ok, odds, ODDS_CACHE_SECONDS)
            except Exception as e:
                last_err = scrub(e)[:160]
                print("API-FOOTBALL ODDS ERROR:", last_err)
        if odds:
            cands = engine.football_candidates(odds, model, f["home"], f["away"], MIN_ODDS, MAX_ODDS, MIN_PROB)
        else:
            cands = engine.football_candidates_model(model, f["home"], f["away"], MIN_PROB)
        cands = [c for c in cands if c["n"] >= MIN_CONFIDENCE]
        if cands:
            research.append({"id": f"a{f['id']}", "sport": "football", "match": f"{f['home']} vs {f['away']}",
                             "league": f"{f['league']} ({f['country']})" if f["country"] else f["league"],
                             "kickoff": _when(f["day"], f["kickoff"], days), "cands": cands,
                             "ctx": {"exp_goals": model["exp"], "home_xg": model["lh"], "away_xg": model["la"],
                                     "h2h_avg": model["h2h_avg"]}})
    if failed:
        notes.append(f"API-Football data failed for {failed} match(es): {last_err}")
    notes.append(f"API-Football added {len(research)} extra match(es) from other leagues"
                 " (each scan covers a few more, results are cached).")
    return research, notes


def collect_football_all(date, days=1):
    """Football-Data.org first; API-Football (same key as basketball) adds the leagues it does not cover."""
    research, notes, errors = [], [], []
    try:
        research, notes = collect_football(date, days)
    except Exception as e:
        errors.append(scrub(e)[:160])
        print("FOOTBALL-DATA ERROR:", errors[-1])
    if aps_key():
        try:
            try:
                skip = {_match_key(s["day"], s["home"], s["away"]) for s in _football_fixtures(date, days)}
            except Exception:
                skip = set()
            extra, n = collect_football_aps(date, days, skip)
            research = research + extra
            notes = notes + n
        except Exception as e:
            errors.append(scrub(e)[:160])
            print("API-FOOTBALL ERROR:", errors[-1])
    if errors and not research and len(errors) >= (2 if aps_key() else 1):
        raise RuntimeError("; ".join(errors))
    if errors:
        notes.append("Some football data failed: " + "; ".join(errors))
    if days > 1 and len(research) > WEEK_MAX_FOOTBALL:
        research.sort(key=lambda r: max((c["n"], c["p"]) for c in r["cands"]), reverse=True)
        research = research[:WEEK_MAX_FOOTBALL]
    return research, notes


# ---------------------------------------------------------------- basketball collection
def _basketball_games(date, days=1):
    key = _cache_key(date, "bb", "games") if days <= 1 else _cache_key(date, "bb", "games", f"{days}d")
    usable = store.get_json(key)
    if usable is None:
        usable = []
        for g in (get_today_games() if days <= 1 else get_games_range(date, days)):
            status, teams = g.get("status") or {}, g.get("teams") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            lg = g.get("league") or {}
            if g.get("id") and home.get("name") and away.get("name") and str(status.get("short") or "").upper() == "NS":
                usable.append({"id": g["id"], "day": (g.get("date") or "")[:10], "odds_item": g.get("odds_item"),
                               "kickoff": (g.get("date") or "")[11:16], "home": home["name"],
                               "away": away["name"], "home_id": home.get("id"), "away_id": away.get("id"),
                               "league": lg.get("name"), "league_id": lg.get("id"), "season": lg.get("season"),
                               "country": (g.get("country") or {}).get("name")})
        store.set_json(key, usable, CACHE_SECONDS)
    return usable


def _basketball_profile(game, team_id):
    return store.get_json(f"guru:bbstats:{game['league_id']}:{game['season']}:{team_id}")


def _bb_day_results(day):
    out = []
    for g in get_games_on(day):
        if str((g.get("status") or {}).get("short") or "").upper() not in {"FT", "AOT"}:
            continue
        t, sc = g.get("teams") or {}, g.get("scores") or {}
        hs, aws = (sc.get("home") or {}).get("total"), (sc.get("away") or {}).get("total")
        h, a = (t.get("home") or {}).get("id"), (t.get("away") or {}).get("id")
        if None not in (hs, aws, h, a):
            out.append({"h": h, "a": a, "hs": hs, "as": aws})
    return out


def _bb_history_range(date):
    """The whole recent-results window in ONE call, cached 6 hours (works even when the cache is not persistent)."""
    key = f"guru:bbhist:{date}:{last_source()[0]}"
    hit = store.get_json(key)
    if hit is None:
        today = datetime.strptime(date, "%Y-%m-%d").date()
        hit = get_finished_between((today - timedelta(days=BB_HISTORY_DAYS)).isoformat(),
                                   (today - timedelta(days=1)).isoformat())
        if not hit:
            raise RuntimeError("no finished games returned")
        store.set_json(key, hit, 6 * 3600)
    return hit


def _bb_history(date, budget):
    """Finished games of the last BB_HISTORY_DAYS days. Each past day is cached for a week, so the window
    fills in over the first few scans (free-plan substitute for season statistics)."""
    games, failed, last_err = [], 0, ""
    range_err = ""
    try:
        return _bb_history_range(date), budget, 0, ""
    except Exception as e:  # fall back to the slower day-by-day window
        range_err = "ESPN history: " + scrub(e)[:120]
        print("BASKETBALL HISTORY RANGE ERROR:", range_err)
    today = datetime.strptime(date, "%Y-%m-%d").date()
    for d in range(1, BB_HISTORY_DAYS + 1):
        day = (today - timedelta(days=d)).isoformat()
        ck = f"guru:bbday:{day}"
        hit = store.get_json(ck)
        if hit is None:
            if budget <= 0:
                continue
            budget -= 1
            try:
                hit = _bb_day_results(day)
            except Exception as e:
                failed += 1
                last_err = scrub(e)[:160]
                print("BASKETBALL HISTORY ERROR:", last_err)
                continue
            store.set_json(ck, hit, 7 * 24 * 3600)
        games.extend(hit)
    if range_err:
        last_err = f"{range_err} | {last_err}"
    return games, budget, failed, last_err


def collect_basketball(date, days=1):
    notes = []
    usable = _basketball_games(date, days)
    usable.sort(key=lambda s: ((s["league"] or "").lower() not in PRIORITY_BASKETBALL, s.get("day") or "", s["kickoff"]))
    usable = usable[:MAX_BASKETBALL] if days <= 1 else usable[:WEEK_MAX_BASKETBALL]

    priced, odds_left, odds_failed, odds_err = [], BASKETBALL_ODDS_CALLS, 0, ""
    for s in usable:
        if days > 1 and ":" in str(s["id"]):  # ESPN week feed already carries each game's odds: no extra call per game
            odds = parse_basketball_odds([s["odds_item"]]) if s.get("odds_item") else {}
            if s["home_id"] and s["away_id"]:
                priced.append((s, odds))  # odds may be empty: those games get a model-only winner pick
            continue
        ok = _cache_key(date, "bb", "odds", s["id"])
        odds = store.get_json(ok)
        if odds is None and days > 1 and odds_left <= 0:  # week: out of odds calls, keep the game for a model-only pick
            if s["home_id"] and s["away_id"]:
                priced.append((s, {}))
            continue
        if odds is None:
            if odds_left <= 0:
                continue
            odds_left -= 1
            try:
                odds = parse_basketball_odds(basketball_odds(s["id"]))
            except Exception as e:
                odds_failed += 1
                odds_err = scrub(e)[:160]
                print("BASKETBALL ODDS ERROR:", odds_err)
                if days > 1 and s["home_id"] and s["away_id"]:
                    priced.append((s, {}))
                continue
            store.set_json(ok, odds, ODDS_CACHE_SECONDS)
        if (odds or days > 1) and s["home_id"] and s["away_id"]:
            priced.append((s, odds or {}))

    mode_key = _cache_key(date, "bb_stats_mode")
    window = store.get_json(mode_key) == "window"
    stats_left, stats_failed, stats_err, history = BASKETBALL_STATS_CALLS, 0, "", None
    research, modelled, hist_n, hist_err = [], 0, None, ""
    for s, odds in priced:
        profiles = {}
        if not window and s["league_id"] and s["season"]:
            missing = []
            for tid in (s["home_id"], s["away_id"]):
                p = _basketball_profile(s, tid)
                if p is None:
                    missing.append(tid)
                else:
                    profiles[tid] = p
            if missing and len(missing) <= stats_left:
                for tid in missing:
                    stats_left -= 1
                    try:
                        p = engine.basketball_profile(get_team_statistics(s["league_id"], s["season"], tid))
                    except Exception as e:
                        stats_err = scrub(e)[:160]
                        print("BASKETBALL STATS ERROR:", stats_err)
                        if _is_plan_error(stats_err):  # plan can't read season statistics: use recent results
                            window = True
                            store.set_json(mode_key, "window", 24 * 3600)
                            stats_err = ""
                        else:
                            stats_failed += 1
                        break
                    store.set_json(f"guru:bbstats:{s['league_id']}:{s['season']}:{tid}", p, STATS_CACHE_SECONDS)
                    profiles[tid] = p
        if window or not (s["league_id"] and s["season"]):  # no season statistics available: use recent results
            if history is None:
                history, stats_left, f, err = _bb_history(date, stats_left)
                hist_n, hist_err = len(history), err
                stats_failed += f
                stats_err = err or stats_err
            if last_source()[0] == "apisports":  # history comes from ESPN: match the teams by name
                profiles = {tid: engine.basketball_profile_from_games(norm_team(name), history)
                            for tid, name in ((s["home_id"], s["home"]), (s["away_id"], s["away"]))}
            else:
                profiles = {tid: engine.basketball_profile_from_games(tid, history)
                            for tid in (s["home_id"], s["away_id"])}
        model = engine.basketball_model(profiles.get(s["home_id"]), profiles.get(s["away_id"]))
        if not model:
            continue
        modelled += 1
        if odds:
            cands = engine.basketball_candidates(odds, model, s["home"], s["away"], MIN_ODDS, MAX_ODDS,
                                                 MIN_BB_PROB, BB_MIN_GAP)
        else:
            cands = engine.basketball_candidates_model(model, s["home"], s["away"], MIN_BB_PROB)
        cands = [c for c in cands if c["n"] >= MIN_CONFIDENCE]
        if cands:
            research.append({"id": f"b{s['id']}", "sport": "basketball", "match": f"{s['home']} vs {s['away']}",
                             "league": s["league"], "kickoff": _when(s.get("day"), s["kickoff"], days), "cands": cands,
                             "ctx": {"model_total": model["total"], "model_home": model["eh"],
                                     "model_away": model["ea"]}})
    if window:
        notes.append("Basketball form comes from the last "
                     f"{BB_HISTORY_DAYS} days of results.")
    with_odds = sum(1 for _, o in priced if o)
    src, src_err = last_source()
    notes.append(f"Basketball [{BUILD}] ({src}{', ' + src_err if src_err else ''}): "
                 f"{len(usable)} games found, {with_odds} with bookmaker odds, {modelled} modelled"
                 + (f", {hist_n} past games used for form" if hist_n is not None else "") + ". "
                 + ("Games without odds only get a model-based winner pick; over/under appears once a total line is listed."
                    if days > 1 else ""))
    if hist_err and not stats_failed:
        notes.append(f"Form data problem: {hist_err}")
    if odds_failed:
        notes.append(f"Basketball odds failed for {odds_failed} game(s): {odds_err}")
    if stats_failed:
        notes.append(f"Basketball form data failed for {stats_failed} request(s): {stats_err}")
    return research, notes


# ---------------------------------------------------------------- analysis
def build_prompt(date, scope, data):
    slim = [{"id": r["id"], "match": r["match"], "league": r["league"], "ctx": r["ctx"],
             "cands": [{k: c[k] for k in ("k", "c", "s", "o", "p", "pm", "pk", "n", "r")} for c in r["cands"]]}
            for r in data]
    return f"""You are a disciplined sports betting analyst reviewing pre-computed candidate bets.
Date (Africa/Lagos): {date}. Scope: {scope}.

Each match in DATA has "cands": bets already priced by a statistical model (Poisson goals model for football,
scoring-average model for basketball). Football candidates have no bookmaker odds (o and pk are null); basketball
ones are compared with bookmaker odds. Fields: k = key, c = category,
s = selection, o = odds, p = probability %, pm = model %, pk = bookmaker no-margin % (or null),
n = confidence 1-10, r = base risk. "ctx" holds supporting numbers (expected goals / points, head-to-head).

TASK: choose the strongest bets from the candidates.
- Pick ONLY from the supplied cands, using the exact id and k. Never invent or change a selection, odds or number.
- At most one pick per category per match and at most 3 per match.
- Prefer picks where p is high and n is high (and pm and pk are close when pk exists). Skip anything that looks thin, contradicted by ctx,
  or volatile. Do not pad: fewer strong picks beat many weak ones.
- risk: Low, Medium or High. You may raise the base risk r, never lower it.
- avoid: up to 4 matches that look too volatile (id only).

Return ONLY this JSON, nothing else:
{{"picks":[{{"id":"f123","key":"OVER:2.5","risk":"Medium"}}],"avoid":[{{"id":"f456"}}]}}

DATA:
{json.dumps(slim, ensure_ascii=False, separators=(",", ":"))}
"""


def _pick(r, c, risk=None):
    risk = max([c["r"], risk or c["r"]], key=lambda x: RISK_ORDER.get(x, 1))
    return {"match_id": r["id"], "match": r["match"], "league": r["league"], "kickoff": r["kickoff"],
            "category": c["c"], "selection": c["s"], "odds": c["o"],
            "probability": min(MAX_PROBABILITY, c["p"]), "confidence": c["n"], "risk": risk,
            "model": c["pm"], "market": c["pk"]}


def clean(raw, index):
    """Map the AI's choices back onto engine candidates. All numbers come from the engine, never from the AI."""
    picks, avoid, seen, per_match = [], [], set(), Counter()
    if not isinstance(raw, dict):
        return picks, avoid
    chosen = raw.get("picks") if isinstance(raw.get("picks"), list) else []
    for p in chosen:
        if not isinstance(p, dict):
            continue
        r = index.get(str(p.get("id")))
        c = next((c for c in r["cands"] if c["k"] == str(p.get("key"))), None) if r else None
        if not c or c["c"] not in CATEGORIES or (r["id"], c["c"]) in seen or per_match[r["id"]] >= 3:
            continue
        risk = str(p.get("risk", "")).strip().capitalize()
        seen.add((r["id"], c["c"]))
        per_match[r["id"]] += 1
        picks.append(_pick(r, c, risk if risk in RISK_ORDER else None))
    for a in raw.get("avoid") if isinstance(raw.get("avoid"), list) else []:
        r = index.get(str(a.get("id"))) if isinstance(a, dict) else None
        if r:
            avoid.append({"match": r["match"]})
    return picks, avoid


def engine_picks(index):
    """Fallback when no AI provider answers: use the engine's own ranking."""
    picks = []
    for r in index.values():
        picks.extend(_pick(r, c) for c in r["cands"][:3])
    return picks


def _analyse(scope, date, days=1):
    deadline = time.time() + TIME_BUDGET
    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        if scope in {"both", "football"}:
            jobs["football"] = pool.submit(collect_football_all, date, days)
        if scope in {"both", "basketball"}:
            jobs["basketball"] = pool.submit(collect_basketball, date, days)
    data, notes, failed = [], [], 0
    for sport, job in jobs.items():
        try:
            rows, n = job.result()
            data.extend(rows)
            notes.extend(n)
        except Exception as e:
            failed += 1
            print(f"{sport.upper()} DATA ERROR:", scrub(e))
            notes.append(f"{sport.capitalize()} data was unavailable: {scrub(e)[:160]}")
    if not data:
        if failed == len(jobs):
            return None, None, notes
        notes.append("No match had enough data for a strong pick.")
        return [], [], notes

    index = {r["id"]: r for r in data}
    picks = avoid = None
    try:
        picks, avoid = clean(ask_json(build_prompt(date, scope + (f", next {days} days" if days > 1 else ""), data), ["gemini", "groq", "openrouter"],
                                      deadline=deadline), index)
    except Exception as e:
        print("AI ERROR:", scrub(e))
    if not picks:
        picks, avoid = engine_picks(index), avoid or []
        notes.append("AI review unavailable or empty; showing model-ranked picks.")
    return picks, avoid, notes


CATEGORY_PRIORITY = {"OVER": 0, "UNDER": 0, "BB_OVER": 0, "BB_UNDER": 0, "BTTS": 1, "1X2": 2, "BB_WINNER": 2, "DOUBLE_CHANCE": 3}


def one_per_match(picks):
    """Keep only the strongest pick of each match (confidence, then probability, then over/under before the rest)."""
    best = {}
    for p in picks:
        key = (-p["confidence"], -p["probability"], CATEGORY_PRIORITY.get(p["category"], 9))
        cur = best.get(p["match_id"])
        if cur is None or key < cur[0]:
            best[p["match_id"]] = (key, p)
    return [p for _, p in best.values()]


def _pipe_key(date, scope, days=1):
    return _cache_key(date, "pipe", scope) if days <= 1 else _cache_key(date, "pipe", f"{days}d", scope)


def _cached(scope, date, days=1):
    for s in ([scope, "both"] if scope != "both" else ["both"]):
        hit = store.get_json(_pipe_key(date, s, days))
        if hit:
            return hit
    return None


def run_pipeline(mode="tips", days=1, fresh=False):
    date = get_lagos_date()
    scope = ("basketball" if mode in {"basketball", "bbover", "bbunder"}
             else "both" if mode in {"tips", "acca", "safe", "totals"} else "football")
    if not ENABLE_BASKETBALL:  # on by default; set ENABLE_BASKETBALL=false to turn it off
        if scope == "basketball":
            return "🏀 Basketball is switched off (ENABLE_BASKETBALL=false)."
        scope = "football"
    hit = None if fresh else _cached(scope, date, days)
    if hit:
        picks, avoid, notes = hit["picks"], hit["avoid"], hit["notes"]
    else:
        picks, avoid, notes = _analyse(scope, date, days)
        if picks is None:
            return ("⚠️ <b>AI BETTING GURU</b>\n\nNo usable fixtures were returned for "
                    + ("today" if days <= 1 else f"the next {days} days") + ".\n" + "\n".join(notes))
        if picks:  # never keep an empty result: it would repeat the same "no picks" message for hours
            store.set_json(_pipe_key(date, scope, days), {"picks": picks, "avoid": avoid, "notes": notes},
                           CACHE_SECONDS if days <= 1 else 3 * 3600)

    wanted = MODE_SECTIONS.get(mode, MODE_SECTIONS["tips"])
    picks = [p for p in picks if p["category"] in wanted]
    if mode == "safe":
        picks = [p for p in picks if p["risk"] == "Low" and p["confidence"] >= 7]
    picks = one_per_match(picks)  # a match appears once, with its strongest pick
    return render_report(picks, avoid, mode, date, notes, days)


# ---------------------------------------------------------------- /longshot
def _numbered_picks(date):
    """Today's picks in a fixed order, so the numbers in /longshot stay the same between messages."""
    hit = _cached("football", date)
    if hit:
        picks = hit["picks"]
    else:
        picks, _, notes = _analyse("football", date)
        if picks is None:
            return None
        store.set_json(_cache_key(date, "pipe", "football"), {"picks": picks, "avoid": [], "notes": notes}, CACHE_SECONDS)
    picks = [p for p in picks if p["category"] in {"OVER", "UNDER", "BTTS", "1X2", "DOUBLE_CHANCE"}]
    picks = one_per_match(picks)
    picks.sort(key=lambda p: (-p["confidence"], -p["probability"], p["match_id"], p["category"]))
    return picks[:12]


def run_longshot(args):
    date = get_lagos_date()
    picks = _numbered_picks(date)
    if picks is None:
        return "⚠️ No usable fixtures were returned today."
    if not args:
        if not picks:
            return "No picks today, so there is nothing to build a longshot from."
        lines = ["🎰 <b>LONGSHOT BUILDER</b>", "Today's legs (model probability):", ""]
        for i, p in enumerate(picks, 1):
            lines.append(f"{i}. {_h(p['match'])} — <b>{_h(p['selection'])}</b> ({p['probability']}%)")
        lines += ["", "Check the real odds on your bookmaker, then send them with the leg numbers:",
                  "<code>/longshot 1:1.25 3:1.40 4:1.18</code>", "",
                  "Plain odds also work: <code>/longshot 1.8 2.1 1.5</code>"]
        return "\n".join(lines)

    legs, bad = [], []
    for tok in args[:15]:
        num, _, odd = tok.rpartition(":")
        try:
            o = float(odd.replace(",", "."))
            n = int(num) if num else None
        except ValueError:
            bad.append(tok)
            continue
        if o <= 1.0:
            bad.append(tok)
            continue
        pick = picks[n - 1] if n and 1 <= n <= len(picks) else None
        if n and not pick:
            bad.append(tok)
            continue
        legs.append((o, pick))
    if bad or not legs:
        return "❌ I could not read: " + _h(" ".join(bad or args)) + "\nUse <code>/longshot 1:1.25 3:1.40</code> or <code>/longshot 1.8 2.1</code>."

    combined = 1.0
    for o, _ in legs:
        combined *= o
    out = ["🎰 <b>LONGSHOT</b>", f"Legs: {len(legs)}", f"💰 Combined odds ≈ <b>{combined:.2f}</b>",
           f"🏦 Bookmaker's implied chance ≈ {100 / combined:.1f}% (about 1 in {round(combined)}, before their margin)"]
    modelled = [p for _, p in legs if p]
    if len(modelled) == len(legs):
        chance = 1.0
        for p in modelled:
            chance *= p["probability"] / 100
        out.append(f"🧮 Model's chance ≈ {chance * 100:.1f}% (legs treated as independent)")
        ids = [p["match_id"] for p in modelled]
        if len(set(ids)) < len(ids):
            out.append("⚠️ Two legs are from the same match, so they are not independent. The real chance is different.")
        fair = 1 / chance if chance else 0
        verdict = ("the bookmaker is paying less than the model's own fair price, so this is poor value"
                   if combined < fair else "the bookmaker pays more than the model's fair price")
        out.append(f"📉 Model's fair odds ≈ {fair:.1f}, so {verdict}. The model is untested; do not trust this number much.")
    out.append("\nMost longshots lose. Stake only what you would happily lose, and keep it apart from your normal bets.")
    return "\n".join(out)


def _h(x):
    import html
    return html.escape(str(x), quote=False)
