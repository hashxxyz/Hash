import json
from agents import gemini, openrouter, groq
from football_data import get_today_fixtures, get_predictions, get_odds as football_odds, get_lagos_date
from basketball_data import get_today_games, get_odds as basketball_odds

MAX_FOOTBALL = 10
MAX_BASKETBALL = 10
FOOTBALL_ODDS_CALLS = 6
BASKETBALL_ODDS_CALLS = 6
PRIORITY_LEAGUES = {"Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League", "Eredivisie", "Primeira Liga", "Süper Lig"}


def football_summary(f):
    x, l, t = f.get("fixture", {}), f.get("league", {}), f.get("teams", {})
    return {"id": x.get("id"), "date": x.get("date"), "status": (x.get("status") or {}).get("short"), "competition": l.get("name"), "country": l.get("country"), "home": (t.get("home") or {}).get("name"), "away": (t.get("away") or {}).get("name")}


def basketball_summary(g):
    teams = g.get("teams", {})
    league = g.get("league", {})
    status = g.get("status", {})
    return {"id": g.get("id"), "date": g.get("date"), "status": status.get("short") or status.get("long"), "competition": league.get("name"), "country": league.get("country"), "home": (teams.get("home") or {}).get("name"), "away": (teams.get("away") or {}).get("name")}


def parse_odds(raw, sport):
    out = []
    for item in (raw or [])[:3]:
        bookmaker = item.get("bookmaker") or {}
        for bet in (bookmaker.get("bets") or [])[:15]:
            vals = []
            for v in (bet.get("values") or [])[:20]:
                vals.append({"value": v.get("value"), "odd": v.get("odd"), "handicap": v.get("handicap")})
            out.append({"sport": sport, "bookmaker": bookmaker.get("name"), "market": bet.get("name"), "values": vals})
    return out


def collect_football():
    fixtures = get_today_fixtures()
    usable = []
    for f in fixtures:
        s = football_summary(f)
        if s["status"] in {"NS", "TBD", "PST"} and s["home"] and s["away"]:
            usable.append(s)
    usable.sort(key=lambda s: (s["competition"] not in PRIORITY_LEAGUES, s["date"] or ""))
    usable = usable[:MAX_FOOTBALL]
    research = []
    for i, s in enumerate(usable):
        r = {"fixture": s, "sport": "football"}
        try:
            r["prediction"] = (get_predictions(s["id"]) or [{}])[0].get("predictions", {})
        except Exception as e:
            r["prediction_error"] = str(e)
        if i < FOOTBALL_ODDS_CALLS:
            try: r["odds"] = parse_odds(football_odds(s["id"]), "football")
            except Exception as e: r["odds_error"] = str(e)
        research.append(r)
    return research


def collect_basketball():
    games = get_today_games()
    usable = []
    for g in games:
        s = basketball_summary(g)
        if s["home"] and s["away"] and s["id"]:
            status = str(s["status"] or "").lower()
            if "cancel" not in status and "finish" not in status and "final" not in status:
                usable.append(s)
    usable.sort(key=lambda s: s["date"] or "")
    usable = usable[:MAX_BASKETBALL]
    research = []
    for i, s in enumerate(usable):
        r = {"fixture": s, "sport": "basketball"}
        if i < BASKETBALL_ODDS_CALLS:
            try: r["odds"] = parse_odds(basketball_odds(s["id"]), "basketball")
            except Exception as e: r["odds_error"] = str(e)
        research.append(r)
    return research


def mode_instruction(mode):
    return {
        "tips": "Find the strongest overall opportunities across football and basketball.",
        "football": "Analyze football only and find the strongest opportunities.",
        "basketball": "Analyze basketball only and find the strongest opportunities.",
        "safe": "Prioritize conservative markets and reject volatile selections.",
        "goals": "Football goals markets only; reject weak evidence.",
        "btts": "Football BTTS only; reject weak evidence.",
        "acca": "Build a maximum 3-leg accumulator from the strongest selections across both sports. Do not force a leg.",
    }.get(mode, "Find the strongest overall opportunities across football and basketball.")


def run_pipeline(mode="tips"):
    date = get_lagos_date()
    data = []
    errors = []
    if mode in {"tips", "football", "safe", "goals", "btts", "acca"}:
        try: data.extend(collect_football())
        except Exception as e: errors.append(f"Football data error: {e}")
    if mode in {"tips", "basketball", "acca"}:
        try: data.extend(collect_basketball())
        except Exception as e: errors.append(f"Basketball data error: {e}")
    if not data:
        return "⚠️ AI BETTING GURU\n\nNo usable fixtures were returned today.\n\n" + ("\n".join(errors) if errors else "Try again later.")

    research = gemini(f"""
You are the VERIFIED SPORTS DATA RESEARCH AGENT.
Date in Africa/Lagos: {date}
Requested mode: {mode}
TASK: {mode_instruction(mode)}

Use ONLY the supplied API data. Never invent odds, injuries, form, xG, lineups, player news, statistics or fixtures. Missing data must reduce confidence. Do not call any bet guaranteed or 100% certain. For basketball, do not invent spread/total evidence if odds are missing. Separate strong candidates from avoid candidates.

DATA:
{json.dumps(data, ensure_ascii=False, indent=2)}
""")

    analysis = openrouter(f"""
You are a disciplined professional football and basketball betting analyst.
Date: {date}. Mode: {mode}. {mode_instruction(mode)}

Evaluate only the verified research below. Evidence quality beats quantity. Agreement between signals increases confidence; missing or conflicting data lowers confidence. Never manufacture bookmaker odds or statistics. Probability is an estimate, not a guarantee.

For each accepted pick give: SPORT, MATCH, MARKET, ESTIMATED PROBABILITY, CONFIDENCE /10, RISK, REASON.
For rejected matches give MATCH and REASON.
Do not force picks.

RESEARCH:
{research}
""")

    return groq(f"""
You are the FINAL TELEGRAM AI BETTING GURU editor.
Create a concise combined report. Use ONLY picks in the analyst output. Do not add facts, odds or bets. If fewer than 3 strong picks exist, show fewer.

🔥 AI BETTING GURU
📅 {date}

⚽ FOOTBALL
...

🏀 BASKETBALL
...

🏆 BEST OVERALL PICKS
...

🚫 AVOID
...

⚠️ NOTE
Probability-based analysis, not guaranteed results. Bet responsibly.

ANALYST OUTPUT:
{analysis}
""")
