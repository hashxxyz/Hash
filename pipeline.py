from agents import gemini, openrouter, groq


def run_pipeline():

    research = gemini(
        """
You are the FOOTBALL BETTING RESEARCH AGENT.

Identify today's football matches and determine which are worth deeper betting analysis.

Rules:
- Focus on matches being played today.
- Do not invent fixtures, odds, injuries, lineups or statistics.
- Do not give betting tips yet.
- Do not write stories.

For each potentially interesting match collect:
MATCH
DATE
COMPETITION
RECENT FORM
HOME/AWAY FORM
GOALS
BTTS
OVER/UNDER TRENDS
H2H
INJURIES
SUSPENSIONS
EXPECTED LINEUPS
IMPORTANT NEWS
AVAILABLE ODDS IF VERIFIED

Also identify matches that should be avoided.

Return concise research data only.
"""
    )

    analysis = openrouter(
        f"""
You are an expert football betting analyst.

Analyze the football research below and identify the strongest
betting opportunities.

Consider:
- Recent form
- Home/away performance
- Goals
- BTTS
- Over/under trends
- xG when available
- Injuries
- Suspensions
- Expected lineups
- H2H
- Match importance
- Fixture congestion
- Statistical consistency
- Prediction-source agreement
- Available odds when verified

Possible markets:
1X2
Double Chance
Draw No Bet
Over/Under Goals
BTTS
Team Goals
Corners
Cards

Do not invent missing information.
If evidence is weak, reject the match.
Give probability estimates, not guarantees.

Return ONLY:

BEST BETTING OPPORTUNITIES

1.
MATCH:
MARKET:
ESTIMATED PROBABILITY:
CONFIDENCE:
RISK:
REASON:

2.
MATCH:
MARKET:
ESTIMATED PROBABILITY:
CONFIDENCE:
RISK:
REASON:

3.
MATCH:
MARKET:
ESTIMATED PROBABILITY:
CONFIDENCE:
RISK:
REASON:

MATCHES TO AVOID
- match + reason

RESEARCH:
{research}
"""
    )

    final = groq(
        f"""
You are the FINAL BETTING REPORT AGENT.

Turn the analysis into a concise Telegram betting report.

Do NOT add new bets.
Do NOT invent statistics or odds.
Do NOT claim any bet is guaranteed.
Use probability and risk clearly.

Return exactly:

AI BETTING GURU
TODAY

BEST PICKS

1. MATCH
Market:
Probability:
Confidence:
Risk:
Why:

2. MATCH
Market:
Probability:
Confidence:
Risk:
Why:

3. MATCH
Market:
Probability:
Confidence:
Risk:
Why:

AVOID
[list rejected matches and short reasons]

NOTE:
These are probability-based analyses, not guaranteed results.

ANALYSIS:
{analysis}
"""
    )

    return final
