import json
import os
import time
from datetime import datetime, timedelta
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import engine
import store
from agents import ask_json, scrub
from basketball_data import get_today_games, get_odds as basketball_odds, get_team_statistics, get_games_on
from football_data import get_today_matches, get_finished_matches, get_lagos_date, to_lagos_hhmm
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
ENABLE_BASKETBALL = os.environ.get("ENABLE_BASKETBALL", "").strip().lower() in {"1", "true", "yes"}


def football_summary(m, date):
    comp, area = m.get("competition") or {}, m.get("area") or {}
    day, hhmm = to_lagos_hhmm(m.get("utcDate"))
    return {"id": m.get("id"), "day": day, "kickoff": hhmm, "status": m.get("status"),
            "league": comp.get("name"), "code": comp.get("code"), "country": area.get("name"),
            "home": (m.get("homeTeam") or {}).get("name"), "away": (m.get("awayTeam") or {}).get("name"),
            "home_id": (m.get("homeTeam") or {}).get("id"), "away_id": (m.get("awayTeam") or {}).get("id")}


def _football_fixtures(date):
    key = _cache_key(date, "fd", "fixtures")
    usable = store.get_json(key)
    if usable is None:
        usable = [s for s in (football_summary(m, date) for m in get_today_matches(date))
                  if s["day"] == date and s["status"] in {"SCHEDULED", "TIMED"}
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


def collect_football(date):
    notes, usable = [], _football_fixtures(date)
    counts = Counter(s["code"] for s in usable)

    def rank(s):  # top competitions first, then the ones with the most matches today
        return (-counts[s["code"]], s["code"] or "", s["kickoff"])

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
    for s in usable[:MAX_FOOTBALL]:
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
                             "kickoff": s["kickoff"], "cands": cands,
                             "ctx": {"exp_goals": model["exp"], "home_xg": model["lh"], "away_xg": model["la"],
                                     "games_used": model["n"]}})
    if usable and not results:
        notes.append("No competition results could be loaded, so no match could be modelled.")
    notes.append("Football picks come from a goals model on this season's results. No bookmaker odds are used.")
    return research, notes


# ---------------------------------------------------------------- basketball collection
def _basketball_games(date):
    key = _cache_key(date, "bb", "games")
    usable = store.get_json(key)
    if usable is None:
        usable = []
        for g in get_today_games():
            status, teams = g.get("status") or {}, g.get("teams") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            lg = g.get("league") or {}
            if g.get("id") and home.get("name") and away.get("name") and str(status.get("short") or "").upper() == "NS":
                usable.append({"id": g["id"], "kickoff": (g.get("date") or "")[11:16], "home": home["name"],
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


def _bb_history(date, budget):
    """Finished games of the last BB_HISTORY_DAYS days. Each past day is cached for a week, so the window
    fills in over the first few scans (free-plan substitute for season statistics)."""
    games, failed, last_err = [], 0, ""
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
    return games, budget, failed, last_err


def collect_basketball(date):
    notes = []
    usable = _basketball_games(date)
    usable.sort(key=lambda s: ((s["league"] or "").lower() not in PRIORITY_BASKETBALL, s["kickoff"]))
    usable = usable[:MAX_BASKETBALL]

    priced, odds_left, odds_failed, odds_err = [], BASKETBALL_ODDS_CALLS, 0, ""
    for s in usable:
        ok = _cache_key(date, "bb", "odds", s["id"])
        odds = store.get_json(ok)
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
                continue
            store.set_json(ok, odds, ODDS_CACHE_SECONDS)
        if odds and s["home_id"] and s["away_id"]:
            priced.append((s, odds))

    mode_key = _cache_key(date, "bb_stats_mode")
    window = store.get_json(mode_key) == "window"
    stats_left, stats_failed, stats_err, history = BASKETBALL_STATS_CALLS, 0, "", None
    research = []
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
        if window:
            if history is None:
                history, stats_left, f, err = _bb_history(date, stats_left)
                stats_failed += f
                stats_err = err or stats_err
            profiles = {tid: engine.basketball_profile_from_games(tid, history)
                        for tid in (s["home_id"], s["away_id"])}
        model = engine.basketball_model(profiles.get(s["home_id"]), profiles.get(s["away_id"]))
        if not model:
            continue
        cands = engine.basketball_candidates(odds, model, s["home"], s["away"], MIN_ODDS, MAX_ODDS,
                                             MIN_BB_PROB, BB_MIN_GAP)
        cands = [c for c in cands if c["n"] >= MIN_CONFIDENCE]
        if cands:
            research.append({"id": f"b{s['id']}", "sport": "basketball", "match": f"{s['home']} vs {s['away']}",
                             "league": s["league"], "kickoff": s["kickoff"], "cands": cands,
                             "ctx": {"model_total": model["total"], "model_home": model["eh"],
                                     "model_away": model["ea"]}})
    if window:
        notes.append("Free API plan: basketball form comes from the last "
                     f"{BB_HISTORY_DAYS} days of results, which fills in over the first few scans.")
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


def _analyse(scope, date):
    deadline = time.time() + TIME_BUDGET
    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        if scope in {"both", "football"}:
            jobs["football"] = pool.submit(collect_football, date)
        if scope in {"both", "basketball"}:
            jobs["basketball"] = pool.submit(collect_basketball, date)
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
        picks, avoid = clean(ask_json(build_prompt(date, scope, data), ["gemini", "groq", "openrouter"],
                                      deadline=deadline), index)
    except Exception as e:
        print("AI ERROR:", scrub(e))
    if not picks:
        picks, avoid = engine_picks(index), avoid or []
        notes.append("AI review unavailable or empty; showing model-ranked picks.")
    return picks, avoid, notes


def _cached(scope, date):
    for s in ([scope, "both"] if scope != "both" else ["both"]):
        hit = store.get_json(_cache_key(date, "pipe", s))
        if hit:
            return hit
    return None


def run_pipeline(mode="tips"):
    date = get_lagos_date()
    scope = ("basketball" if mode in {"basketball", "bbover", "bbunder"}
             else "both" if mode in {"tips", "acca", "safe", "totals"} else "football")
    if not ENABLE_BASKETBALL:  # basketball still needs an API-Sports plan that covers the current season
        if scope == "basketball":
            return ("🏀 Basketball is switched off. Football-Data.org covers football only. "
                    "Set ENABLE_BASKETBALL=true to use the API-Sports basketball scan.")
        scope = "football"
    hit = _cached(scope, date)
    if hit:
        picks, avoid, notes = hit["picks"], hit["avoid"], hit["notes"]
    else:
        picks, avoid, notes = _analyse(scope, date)
        if picks is None:
            return "⚠️ <b>AI BETTING GURU</b>\n\nNo usable fixtures were returned today.\n" + "\n".join(notes)
        store.set_json(_cache_key(date, "pipe", scope), {"picks": picks, "avoid": avoid, "notes": notes}, CACHE_SECONDS)

    wanted = MODE_SECTIONS.get(mode, MODE_SECTIONS["tips"])
    picks = [p for p in picks if p["category"] in wanted]
    if mode == "safe":
        picks = [p for p in picks if p["risk"] == "Low" and p["confidence"] >= 7]
    return render_report(picks, avoid, mode, date, notes)
