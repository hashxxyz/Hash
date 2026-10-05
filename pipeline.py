import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from agents import ask_json, scrub
from football_data import get_today_fixtures, get_predictions, get_odds_by_league, get_lagos_date
from basketball_data import get_today_games, get_odds as basketball_odds
from render import render_report, MODE_SECTIONS


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# API-Sports free plan = 100 calls/day and about 10 calls/minute PER API, so these defaults keep one
# football run at 1 + 6 + 2 = 9 calls. On a paid plan raise them in Vercel env vars.
MAX_FOOTBALL = _int_env("MAX_FOOTBALL", 30)
FOOTBALL_ODDS_CALLS = _int_env("FOOTBALL_ODDS_CALLS", 6)        # one call = all of a league's matches today
FOOTBALL_PREDICTION_CALLS = _int_env("FOOTBALL_PREDICTION_CALLS", 2)
MAX_BASKETBALL = _int_env("MAX_BASKETBALL", 12)
BASKETBALL_ODDS_CALLS = _int_env("BASKETBALL_ODDS_CALLS", 6)
MIN_CONFIDENCE = _int_env("MIN_CONFIDENCE", 6)                   # "strong" = this or higher
MAX_PROBABILITY = 88                                              # never show 100%
CACHE_SECONDS = _int_env("CACHE_SECONDS", 30 * 60)
TIME_BUDGET = _int_env("TIME_BUDGET", 55)

PRIORITY_LEAGUES = {"Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "UEFA Champions League",
                    "UEFA Europa League", "UEFA Europa Conference League", "Eredivisie", "Primeira Liga",
                    "Süper Lig", "Championship", "Serie B", "La Liga 2", "2. Bundesliga", "Ligue 2",
                    "Jupiler Pro League", "Scottish Premiership", "Major League Soccer"}

CATEGORIES = {"OVER", "UNDER", "CORNERS", "1X2", "DOUBLE_CHANCE", "FIRST_HALF", "BTTS", "BASKETBALL"}

_CACHE = {}  # scope -> (time, picks, avoid, notes)


# ---------------------------------------------------------------- odds parsing
def _line(value):
    try:
        return float(str(value).split()[-1])
    except (ValueError, IndexError):
        return None


LINE_BOUNDS = {"Goals O/U": (0.5, 4.5), "1H Goals O/U": (0.5, 2.5), "Corners O/U": (6.5, 13.5)}


def _football_market(name):
    n = str(name or "").lower().strip()
    team_specific = n.startswith(("home", "away", "1st", "2nd", "second", "team"))
    if n == "match winner":
        return "1X2"
    if n == "double chance":
        return "Double Chance"
    if n == "both teams score":
        return "BTTS"
    if n == "first half winner":
        return "1H 1X2"
    if "corner" in n and "over" in n and not team_specific and "first" not in n:
        return "Corners O/U"
    if "over/under" in n and "goals" in n and "first half" in n and not team_specific:
        return "1H Goals O/U"
    if n == "goals over/under":
        return "Goals O/U"
    return None


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
                    ln = _line(v.get("value"))
                    lo, hi = LINE_BOUNDS[key]
                    if ln is None or not lo <= ln <= hi:
                        continue
                values[str(v.get("value"))] = odd
            if values:
                out[key] = values
    return out


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
                for v in (bet.get("values") or [])[:12]:
                    try:
                        values[str(v.get("value"))] = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                if values:
                    out[key] = values
    return out


def _all_odds(odds):
    return {round(o, 2) for market in (odds or {}).values() for o in market.values()}


# ---------------------------------------------------------------- data collection
def football_summary(f):
    x, l, t = f.get("fixture", {}), f.get("league", {}), f.get("teams", {})
    date = x.get("date") or ""
    return {"id": x.get("id"), "kickoff": date[11:16], "status": (x.get("status") or {}).get("short"),
            "league": l.get("name"), "country": l.get("country"), "league_id": l.get("id"),
            "season": l.get("season"), "home": (t.get("home") or {}).get("name"),
            "away": (t.get("away") or {}).get("name")}


def collect_football():
    notes, fixtures = [], get_today_fixtures()
    usable = [s for s in map(football_summary, fixtures)
              if s["status"] in {"NS", "TBD"} and s["home"] and s["away"] and s["id"]]
    counts = Counter(s["league_id"] for s in usable)

    def rank(s):  # top leagues first, then leagues with the most matches today
        return (s["league"] not in PRIORITY_LEAGUES, -counts[s["league_id"]], s["league_id"] or 0, s["kickoff"])

    usable.sort(key=rank)

    leagues = []
    for s in usable:
        k = (s["league_id"], s["season"])
        if s["league_id"] and k not in leagues:
            leagues.append(k)
        if len(leagues) >= FOOTBALL_ODDS_CALLS:
            break

    odds, failed = {}, 0
    for league_id, season in leagues:
        try:
            for item in get_odds_by_league(league_id, season):
                fid = (item.get("fixture") or {}).get("id")
                parsed = parse_football_odds(item)
                if fid and parsed:
                    odds[fid] = parsed
        except Exception as e:
            failed += 1
            print("ODDS ERROR:", scrub(e))
    if failed:
        notes.append(f"Odds were unavailable for {failed} league(s).")

    chosen = [s for s in usable if (s["league_id"], s["season"]) in leagues]
    chosen.sort(key=lambda s: (s["id"] not in odds,) + rank(s))
    chosen = chosen[:MAX_FOOTBALL] or usable[:MAX_FOOTBALL]

    research = []
    for i, s in enumerate(chosen):
        r = {"id": s["id"], "sport": "football", "match": f"{s['home']} vs {s['away']}",
             "league": f"{s['league']} ({s['country']})" if s["country"] else s["league"],
             "kickoff": s["kickoff"], "odds": odds.get(s["id"])}
        if i < FOOTBALL_PREDICTION_CALLS:
            try:
                r["prediction"] = (get_predictions(s["id"]) or [{}])[0].get("predictions", {})
            except Exception as e:
                print("PREDICTION ERROR:", scrub(e))
        research.append(r)
    return research, notes


def collect_basketball():
    notes, games = [], get_today_games()
    usable = []
    for g in games:
        status = g.get("status") or {}
        teams = g.get("teams") or {}
        home, away = (teams.get("home") or {}).get("name"), (teams.get("away") or {}).get("name")
        if g.get("id") and home and away and str(status.get("short") or "").upper() == "NS":
            date = g.get("date") or ""
            lg = g.get("league") or {}
            usable.append({"id": g["id"], "kickoff": date[11:16], "home": home, "away": away,
                           "league": lg.get("name"), "country": (g.get("country") or {}).get("name")})
    usable.sort(key=lambda s: s["kickoff"])
    usable = usable[:MAX_BASKETBALL]

    research, failed = [], 0
    for i, s in enumerate(usable):
        r = {"id": s["id"], "sport": "basketball", "match": f"{s['home']} vs {s['away']}",
             "league": s["league"], "kickoff": s["kickoff"], "odds": None}
        if i < BASKETBALL_ODDS_CALLS:
            try:
                r["odds"] = parse_basketball_odds(basketball_odds(s["id"])) or None
            except Exception as e:
                failed += 1
                print("BASKETBALL ODDS ERROR:", scrub(e))
        research.append(r)
    if failed:
        notes.append(f"Basketball odds failed for {failed} game(s).")
    return research, notes


# ---------------------------------------------------------------- analysis
def build_prompt(date, scope, data):
    return f"""You are a disciplined sports betting analyst.
Date (Africa/Lagos): {date}. Scope: {scope}.

TASK: From DATA below choose ONLY the strong picks, spread across these categories:
- OVER: goals over a line (selection like "Over 2.5 Goals")
- UNDER: goals under a line
- CORNERS: corners over/under (only odds are supplied, no corner statistics, so confidence max 7)
- 1X2: match result (Home / Draw / Away)
- DOUBLE_CHANCE: 1X, X2 or 12
- FIRST_HALF: 1st-half goals line or 1st-half result
- BTTS: both teams to score Yes/No
- BASKETBALL: basketball winner or total points (sport = basketball only)

RULES:
- Use ONLY the supplied data. Never invent odds, form, injuries, lineups, xG or statistics.
- "id" must be copied exactly from DATA. "odds" must be an odd that exists in that match's odds, else null.
- Estimate probability from agreement between prediction percentages (if present) and bookmaker implied
  probability (1/odd, normalised for the market margin). Max {MAX_PROBABILITY}. Never 100.
- Confidence is 1-10. Only include picks you rate {MIN_CONFIDENCE} or higher. Missing data lowers confidence.
- Cover as many matches and categories as the evidence supports (roughly 10-30 picks when data allows);
  do not pad with weak picks. At most 3 picks per match, one per category.
- risk: Low, Medium or High. Do not include reasons or explanations.
- avoid: up to 4 matches that look too volatile or lack data.

Return ONLY this JSON, nothing else:
{{"picks":[{{"id":123,"category":"OVER","selection":"Over 2.5 Goals","odds":1.85,"probability":71,"confidence":7,"risk":"Medium"}}],
 "avoid":[{{"id":456}}]}}

DATA:
{json.dumps(data, ensure_ascii=False, separators=(",", ":"))}
"""


def clean(raw, index):
    picks, seen = [], set()
    for p in raw.get("picks") or []:
        info = index.get(str(p.get("id")))
        cat = str(p.get("category", "")).upper().replace(" ", "_").replace("-", "_")
        if not info or cat not in CATEGORIES:
            continue
        if (cat == "BASKETBALL") != (info["sport"] == "basketball"):
            continue
        selection = str(p.get("selection", "")).strip()[:60]
        if not selection or (info["id"], cat) in seen:
            continue
        try:
            prob = max(1, min(MAX_PROBABILITY, int(float(str(p.get("probability")).strip("% ")))))
            conf = max(1, min(10, int(float(p.get("confidence")))))
        except (TypeError, ValueError):
            continue
        if cat == "CORNERS":
            conf = min(conf, 7)
        if conf < MIN_CONFIDENCE:
            continue
        odds = None
        try:
            o = round(float(p.get("odds")), 2)
            odds = o if o in info["odds_set"] else None  # drop invented odds
        except (TypeError, ValueError):
            pass
        risk = str(p.get("risk", "Medium")).strip().capitalize()
        risk = risk if risk in {"Low", "Medium", "High"} else "Medium"
        seen.add((info["id"], cat))
        picks.append({"match_id": info["id"], "match": info["match"], "league": info["league"],
                      "kickoff": info["kickoff"], "category": cat, "selection": selection, "odds": odds,
                      "probability": prob, "confidence": conf, "risk": risk})
    avoid = []
    for a in raw.get("avoid") or []:
        info = index.get(str(a.get("id")))
        if info:
            avoid.append({"match": info["match"]})
    return picks, avoid


def _analyse(scope, date):
    deadline = time.time() + TIME_BUDGET
    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        if scope in {"both", "football"}:
            jobs["football"] = pool.submit(collect_football)
        if scope in {"both", "basketball"}:
            jobs["basketball"] = pool.submit(collect_basketball)
    data, notes = [], []
    for sport, job in jobs.items():
        try:
            rows, n = job.result()
            data.extend(rows)
            notes.extend(n)
        except Exception as e:
            print(f"{sport.upper()} DATA ERROR:", scrub(e))
            notes.append(f"{sport.capitalize()} data was unavailable.")
    if not data:
        return None, None, notes

    index = {str(r["id"]): {**r, "odds_set": _all_odds(r.get("odds"))} for r in data}
    raw = ask_json(build_prompt(date, scope, data), ["gemini", "groq", "openrouter"], deadline=deadline)
    picks, avoid = clean(raw, index)
    return picks, avoid, notes


def _cached(scope):
    for key in ([scope, "both"] if scope != "both" else ["both"]):
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit
    return None


def run_pipeline(mode="tips"):
    date = get_lagos_date()
    scope = ("basketball" if mode == "basketball" else "both" if mode in {"tips", "acca"} else "football")
    hit = _cached(scope)
    if hit:
        _, picks, avoid, notes = hit
    else:
        picks, avoid, notes = _analyse(scope, date)
        if picks is None:
            return "⚠️ <b>AI BETTING GURU</b>\n\nNo usable fixtures were returned today.\n" + "\n".join(notes)
        _CACHE[scope] = (time.time(), picks, avoid, notes)

    wanted = MODE_SECTIONS.get(mode, MODE_SECTIONS["tips"])
    picks = [p for p in picks if p["category"] in wanted]
    if mode == "safe":
        picks = [p for p in picks if p["risk"] == "Low" and p["confidence"] >= 7]
    return render_report(picks, avoid, mode, date, notes)
