import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import engine
import store
from agents import ask_json, scrub
from basketball_data import get_today_games, get_odds as basketball_odds, get_team_statistics
from football_data import get_today_fixtures, get_predictions, get_odds_by_league, get_lagos_date
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
# 1 + 3 + 6 = 10 calls and a basketball scan at 1 + 4 + 5 = 10 calls. Odds, predictions and team statistics are
# cached, so repeated scans spend their calls on matches that are not covered yet.
MAX_FOOTBALL = _int_env("MAX_FOOTBALL", 30)
FOOTBALL_ODDS_CALLS = _int_env("FOOTBALL_ODDS_CALLS", 3)         # odds API calls (one page = about 10 matches)
ODDS_MAX_PAGES = _int_env("ODDS_MAX_PAGES", 2)                   # pages read per league
FOOTBALL_PREDICTION_CALLS = _int_env("FOOTBALL_PREDICTION_CALLS", 6)
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


# ---------------------------------------------------------------- odds parsing
LINE_BOUNDS = {"Goals O/U": (0.5, 4.5)}


def _football_market(name):
    n = str(name or "").lower().strip()
    return {"match winner": "1X2", "double chance": "Double Chance", "both teams score": "BTTS",
            "goals over/under": "Goals O/U"}.get(n)


def parse_football_odds(item):
    out = {}
    for bm in item.get("bookmakers") or []:
        for bet in bm.get("bets") or []:
            key = _football_market(bet.get("name"))
            if not key or key in out:
                continue
            values = {}
            for v in bet.get("values") or []:
                try:
                    odd = float(v.get("odd"))
                except (TypeError, ValueError):
                    continue
                if key in LINE_BOUNDS:
                    _, ln = engine.parse_ou(v.get("value"))
                    lo, hi = LINE_BOUNDS[key]
                    if ln is None or not lo <= ln <= hi:
                        continue
                values[str(v.get("value"))] = odd
            if values:
                out[key] = values
    return out


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


# ---------------------------------------------------------------- football collection
def football_summary(f):
    x, l, t = f.get("fixture", {}), f.get("league", {}), f.get("teams", {})
    date = x.get("date") or ""
    return {"id": x.get("id"), "kickoff": date[11:16], "status": (x.get("status") or {}).get("short"),
            "league": l.get("name"), "country": l.get("country"), "league_id": l.get("id"),
            "season": l.get("season"), "home": (t.get("home") or {}).get("name"),
            "away": (t.get("away") or {}).get("name")}


def _football_fixtures(date):
    key = _cache_key(date, "fixtures")
    usable = store.get_json(key)
    if usable is None:
        usable = [s for s in map(football_summary, get_today_fixtures())
                  if s["status"] in {"NS", "TBD"} and s["home"] and s["away"] and s["id"]]
        store.set_json(key, usable, CACHE_SECONDS)
    return usable


def _football_odds(date, league_order, notes):
    """Read odds league by league (and page by page) until the call budget is spent."""
    odds, tried, failed, calls_left = {}, [], 0, FOOTBALL_ODDS_CALLS
    for league_id, season in league_order:
        if calls_left <= 0:
            break
        tried.append((league_id, season))
        page = 1
        while True:
            ck = _cache_key(date, "odds", league_id, season, page)
            hit = store.get_json(ck)
            if hit is None:
                if calls_left <= 0:
                    break
                calls_left -= 1
                try:
                    items, total = get_odds_by_league(league_id, season, page)
                except Exception as e:
                    failed += 1
                    print("ODDS ERROR:", scrub(e))
                    break
                parsed = {}
                for item in items:
                    fid = (item.get("fixture") or {}).get("id")
                    p = parse_football_odds(item)
                    if fid and p:
                        parsed[str(fid)] = p
                hit = {"odds": parsed, "total": total}
                store.set_json(ck, hit, CACHE_SECONDS)
            odds.update(hit["odds"])
            if page >= hit["total"] or page >= ODDS_MAX_PAGES:
                break
            page += 1
    if failed:
        notes.append(f"Odds were unavailable for {failed} request(s).")
    return odds, tried


def _football_model(date, fixture_id, budget):
    """Cached goals model for one fixture. Returns (model or {}, calls_used)."""
    ck = _cache_key(date, "pred", fixture_id)
    hit = store.get_json(ck)
    if hit is not None:
        return hit, 0
    if budget <= 0:
        return None, 0
    try:
        model = engine.football_model(get_predictions(fixture_id)) or {}
    except Exception as e:
        print("PREDICTION ERROR:", scrub(e))
        return None, 1
    store.set_json(ck, model, PREDICTION_CACHE_SECONDS)
    return model, 1


def collect_football(date):
    notes, usable = [], _football_fixtures(date)
    counts = Counter(s["league_id"] for s in usable)

    def rank(s):  # top leagues first, then leagues with the most matches today
        top = ((s["league"] or "").lower(), (s["country"] or "").lower()) in PRIORITY_LEAGUES
        return (not top, -counts[s["league_id"]], s["league_id"] or 0, s["kickoff"])

    usable.sort(key=rank)
    league_order = []
    for s in usable:
        k = (s["league_id"], s["season"])
        if s["league_id"] and k not in league_order:
            league_order.append(k)

    odds, tried = _football_odds(date, league_order, notes)
    chosen = [s for s in usable if (s["league_id"], s["season"]) in tried and str(s["id"]) in odds]
    chosen.sort(key=rank)
    chosen = chosen[:MAX_FOOTBALL]

    research, budget, skipped = [], FOOTBALL_PREDICTION_CALLS, 0
    for s in chosen:
        model, used = _football_model(date, s["id"], budget)
        budget -= used
        if model is None:
            skipped += 1
        if not model:
            continue
        cands = engine.football_candidates(odds[str(s["id"])], model, s["home"], s["away"],
                                           MIN_ODDS, MAX_ODDS, MIN_PROB)
        cands = [c for c in cands if c["n"] >= MIN_CONFIDENCE]
        if cands:
            research.append({"id": f"f{s['id']}", "sport": "football", "match": f"{s['home']} vs {s['away']}",
                             "league": f"{s['league']} ({s['country']})" if s["country"] else s["league"],
                             "kickoff": s["kickoff"], "cands": cands,
                             "ctx": {"exp_goals": model["exp"], "h2h_avg_goals": model["h2h_avg"],
                                     "h2h_n": model["h2h_n"], "api_advice": model["advice"]}})
    if usable and not chosen:
        notes.append("No odds were returned for today's leagues.")
    elif skipped:
        notes.append(f"{skipped} match(es) were not analysed yet (API call budget). Run again later to cover more.")
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


def _basketball_profile(date, game, team_id):
    ck = f"guru:bbstats:{game['league_id']}:{game['season']}:{team_id}"
    return store.get_json(ck)


def collect_basketball(date):
    notes = []
    usable = _basketball_games(date)
    usable.sort(key=lambda s: ((s["league"] or "").lower() not in PRIORITY_BASKETBALL, s["kickoff"]))
    usable = usable[:MAX_BASKETBALL]

    research, odds_left, stats_left, odds_failed, stats_failed = [], BASKETBALL_ODDS_CALLS, BASKETBALL_STATS_CALLS, 0, 0
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
                print("BASKETBALL ODDS ERROR:", scrub(e))
                continue
            store.set_json(ok, odds, CACHE_SECONDS)
        if not odds or not s["home_id"] or not s["away_id"] or not s["league_id"] or not s["season"]:
            continue

        profiles, missing = {}, []
        for tid in (s["home_id"], s["away_id"]):
            p = _basketball_profile(date, s, tid)
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
                    stats_failed += 1
                    print("BASKETBALL STATS ERROR:", scrub(e))
                    continue
                store.set_json(f"guru:bbstats:{s['league_id']}:{s['season']}:{tid}", p, STATS_CACHE_SECONDS)
                profiles[tid] = p
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
    if odds_failed:
        notes.append(f"Basketball odds failed for {odds_failed} game(s).")
    if stats_failed:
        notes.append(f"Basketball team statistics failed for {stats_failed} request(s).")
    return research, notes


# ---------------------------------------------------------------- analysis
def build_prompt(date, scope, data):
    slim = [{"id": r["id"], "match": r["match"], "league": r["league"], "ctx": r["ctx"],
             "cands": [{k: c[k] for k in ("k", "c", "s", "o", "p", "pm", "pk", "n", "r")} for c in r["cands"]]}
            for r in data]
    return f"""You are a disciplined sports betting analyst reviewing pre-computed candidate bets.
Date (Africa/Lagos): {date}. Scope: {scope}.

Each match in DATA has "cands": bets already priced by a statistical model (Poisson goals model for football,
scoring-average model for basketball) and compared with bookmaker odds. Fields: k = key, c = category,
s = selection, o = odds, p = blended probability %, pm = model %, pk = bookmaker no-margin %,
n = confidence 1-10, r = base risk. "ctx" holds supporting numbers (expected goals / points, head-to-head).

TASK: choose the strongest bets from the candidates.
- Pick ONLY from the supplied cands, using the exact id and k. Never invent or change a selection, odds or number.
- At most one pick per category per match and at most 3 per match.
- Prefer picks where pm and pk are close, p is high and n is high. Skip anything that looks thin, contradicted by ctx,
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
            notes.append(f"{sport.capitalize()} data was unavailable.")
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
