import json
from datetime import datetime
from zoneinfo import ZoneInfo

from agents import gemini, openrouter, groq
from football_data import (
    get_today_fixtures,
    get_predictions,
    get_odds,
    get_lagos_date,
)

MAX_CANDIDATES = 12
PREDICTION_CALLS = 12
ODDS_CALLS = 8

# Keep the first version focused on competitions that normally have
# enough data and liquidity. The AI still sees the competition name.
PRIORITY_LEAGUES = {
    "Premier League",
    "La Liga",
    "Serie A",
    "Bundesliga",
    "Ligue 1",
    "UEFA Champions League",
    "UEFA Europa League",
    "UEFA Europa Conference League",
    "Eredivisie",
    "Primeira Liga",
    "Süper Lig",
}


def _fixture_summary(f):
    fixture = f.get("fixture", {})
    league = f.get("league", {})
    teams = f.get("teams", {})

    return {
        "fixture_id": fixture.get("id"),
        "date": fixture.get("date"),
        "status": (fixture.get("status") or {}).get("short"),
        "venue": (fixture.get("venue") or {}).get("name"),
        "competition": league.get("name"),
        "country": league.get("country"),
        "home": (teams.get("home") or {}).get("name"),
        "away": (teams.get("away") or {}).get("name"),
    }


def _extract_prediction(raw):
    if not raw:
        return {}

    item = raw[0] if isinstance(raw, list) else raw
    prediction = item.get("predictions", item)

    return {
        "winner": prediction.get("winner"),
        "win_or_draw": prediction.get("win_or_draw"),
        "under_over": prediction.get("under_over"),
        "advice": prediction.get("advice"),
        "percent": prediction.get("percent"),
        "goals": prediction.get("goals"),
        "comparison": prediction.get("comparison"),
        "h2h": prediction.get("h2h"),
        "teams": prediction.get("teams"),
    }


def _extract_odds(raw):
    # Preserve only compact, verified bookmaker-market data.
    if not raw:
        return []

    output = []

    for item in raw[:3]:
        bookmaker = item.get("bookmaker", {})
        bookmaker_name = bookmaker.get("name")

        for bet in bookmaker.get("bets", [])[:12]:
            values = []
            for value in bet.get("values", [])[:20]:
                values.append({
                    "value": value.get("value"),
                    "odd": value.get("odd"),
                })

            output.append({
                "bookmaker": bookmaker_name,
                "market": bet.get("name"),
                "values": values,
            })

    return output


def collect_data():
    fixtures = get_today_fixtures()

    # Only future/not-started fixtures.
    usable = []
    for f in fixtures:
        summary = _fixture_summary(f)
        status = summary.get("status")
        if status in {"NS", "TBD", "PST"}:
            usable.append((f, summary))

    # Prefer major competitions, then fill remaining slots with other
    # fixtures so the bot is not completely blind on quieter days.
    usable.sort(
        key=lambda x: (
            x[1].get("competition") not in PRIORITY_LEAGUES,
            x[1].get("date") or "",
        )
    )
    usable = usable[:MAX_CANDIDATES]

    research = []

    for index, (fixture, summary) in enumerate(usable):
        record = {"fixture": summary}

        # Predictions are the most useful API-Football pre-match signal.
        if index < PREDICTION_CALLS:
            try:
                record["prediction"] = _extract_prediction(
                    get_predictions(summary["fixture_id"])
                )
            except Exception as e:
                record["prediction_error"] = str(e)

        # Odds are expensive in quota terms, so only request them for
        # the first few candidate fixtures.
        if index < ODDS_CALLS:
            try:
                record["odds"] = _extract_odds(
                    get_odds(summary["fixture_id"])
                )
            except Exception as e:
                record["odds_error"] = str(e)

        research.append(record)

    return research


def _mode_instruction(mode):
    modes = {
        "tips": "Find the strongest overall betting opportunities across sensible markets.",
        "safe": "Prioritize conservative markets such as double chance, draw-no-bet, team over 0.5, and over 1.5 goals. Reject volatile picks.",
        "goals": "Focus only on goals markets: Over/Under and team-goal markets. Prefer strong statistical evidence.",
        "btts": "Focus only on Both Teams To Score markets. Reject matches without sufficient evidence.",
        "acca": "Build a maximum 3-leg accumulator from the strongest low-to-medium risk selections. Do not force a leg if evidence is weak.",
    }
    return modes.get(mode, modes["tips"])


def run_pipeline(mode="tips"):
    date = get_lagos_date()
    data = collect_data()

    if not data:
        return (
            "⚠️ AI BETTING GURU\n\n"
            f"No suitable upcoming football fixtures were returned by "
            f"the football data provider for {date}.\n\n"
            "Try again later."
        )

    research_json = json.dumps(data, ensure_ascii=False, indent=2)

    research = gemini(
        f"""
You are the VERIFIED FOOTBALL DATA RESEARCH AGENT.

Today's date in Africa/Lagos is {date}.

The data below comes from API-Football. Treat it as the source of truth
for fixtures, prediction fields and any odds actually present.

TASK:
{_mode_instruction(mode)}

Rules:
- Analyze ONLY fixtures present in the supplied data.
- Never invent fixtures, odds, injuries, lineups, statistics, xG or form.
- If a required fact is missing, say it is missing and lower confidence.
- Do not call anything guaranteed or 100% certain.
- Prefer markets that can be supported by the supplied evidence.
- Reject matches where evidence is weak or contradictory.
- Do not force a number of picks.

Return structured research for the strongest candidates and a separate
avoid list.

DATA:
{research_json}
"""
    )

    analysis = openrouter(
        f"""
You are a disciplined professional football betting analyst.

Date: {date}
Requested mode: {mode}

{_mode_instruction(mode)}

Review the verified research below.

Scoring principles:
- Evidence quality matters more than flashy predictions.
- Agreement between independent signals increases confidence.
- Missing data decreases confidence.
- Avoid highly volatile markets unless evidence is unusually strong.
- Never manufacture bookmaker odds.
- Probability is an estimate, not a guarantee.
- A match should be rejected if the edge is unclear.

For each accepted pick provide:
MATCH
MARKET
ESTIMATED PROBABILITY
CONFIDENCE /10
RISK
REASON

For each rejected/avoided match provide:
MATCH
REASON

Do not add facts that are not in the research.

RESEARCH:
{research}
"""
    )

    final = groq(
        f"""
You are the FINAL TELEGRAM FOOTBALL BETTING REPORT EDITOR.

Create a clear, concise report for the user.

DATE: {date}
MODE: {mode}

Use ONLY the picks contained in the analyst output.
Do not add new bets, statistics, odds, injuries or claims.
Do not say "sure win", "banker", "guaranteed", "100%" or similar.
If there are fewer than 3 genuinely strong picks, show fewer.

Format:

🔥 AI BETTING GURU
📅 {date}

🏆 BEST PICKS

1️⃣ Match
Market:
Probability:
Confidence:
Risk:
Why:

2️⃣ Match
Market:
Probability:
Confidence:
Risk:
Why:

3️⃣ Match
Market:
Probability:
Confidence:
Risk:
Why:

🚫 AVOID
- Match — reason

⚠️ NOTE
Probability-based analysis, not guaranteed results. Bet responsibly.

ANALYST OUTPUT:
{analysis}
"""
    )

    return final
