from agents import gemini, openrouter, groq


def run_pipeline(idea):

    # =========================================================
    # 1. RESEARCH AGENT
    # =========================================================

    research = gemini(
        f"""
You are the FOOTBALL FACT-CHECKING AGENT.

USER REQUEST:
{idea}

Your ONLY job is to identify the EXACT football event the user is referring to
and provide verified facts about that event.

IMPORTANT DATE / EVENT RULES:

1. If the user says "recent", "recently", "today", "yesterday",
   "two days ago", "latest", "last match", etc., find the most recent
   relevant football event.

2. If the user names two teams, such as "France vs Italy",
   identify the most recent match between those teams unless the user
   explicitly gives another date or competition.

3. NEVER substitute an older famous match just because it has more
   information available.

4. The date of the event MUST be included.

5. Verify the score, goals, scorers, cards and other important events
   before using them.

6. If you cannot confidently identify the exact event, say:
   "EVENT UNCERTAIN"
   and explain what information is missing.

7. NEVER invent facts.

8. Do NOT write a story.
9. Do NOT create comedy.
10. Do NOT suggest cartoon scenes.

RETURN ONLY THIS:

EVENT:
[exact match/event]

DATE:
[date]

COMPETITION:
[competition]

FINAL SCORE:
[score]

KEY FACTS:
- [fact]
- [fact]
- [fact]
- [fact]
- [fact]

IMPORTANT PLAYERS:
- [player]
- [player]

POTENTIAL COMEDY HOOKS:
- [short visual opportunity]
- [short visual opportunity]
- [short visual opportunity]

FACT CONFIDENCE:
[HIGH / MEDIUM / LOW]

FACTS MUST BE ACCURATE.
"""


    )

    # =========================================================
    # 2. COMEDY AGENT
    # =========================================================

    creative = openrouter(
        f"""
You are the COMEDY DIRECTOR for an original football cartoon channel.

Create ONE short football-cartoon concept from the VERIFIED RESEARCH below.

This is NOT a story-writing task.

The format is:

REAL FOOTBALL EVENT
→ FUNNY ANGLE
→ VISUAL GAG
→ ESCALATION
→ PUNCHLINE

STYLE:

- Fast
- Visual
- Physical comedy
- Easy to understand
- Exaggerated cartoon reactions
- Minimal dialogue
- One main joke
- 20–60 seconds
- Simple football environments
- Reusable characters and assets
- Current/recent football situation when provided

IMPORTANT FACT RULE:

The RESEARCH section is the FACT LOCK.

You MUST NOT change:

- match
- date
- competition
- score
- scorer
- player
- goal
- card
- result
- real match event

You MAY exaggerate the VERIFIED EVENT for cartoon comedy.

Example:

FACT:
A player scored.

ALLOWED:
The cartoon player celebrates ridiculously.

NOT ALLOWED:
Claiming another player scored when they did not.

Do not invent a different match.

Do not use historical information unless it is directly relevant
to the researched event.

Do not write narration.

Do not write a long explanation.

Do not create a multi-act story.

Do not introduce unnecessary characters.

RETURN EXACTLY:

🎯 COMEDY CONCEPT

TITLE:
[short title]

REAL EVENT:
[one sentence]

COMEDY PREMISE:
[one sentence]

CHARACTERS:
[only necessary characters]

VISUAL GAG:
[what we see]

ESCALATION:
[2–3 short escalating actions]

PUNCHLINE:
[final visual joke]

RUNTIME:
[20–60 seconds]

🎬 ACTION BEATS

1. [what we see]
2. [what we see]
3. [what we see]
4. [what we see]
5. [what we see]

Do not write anything outside this format.

VERIFIED RESEARCH:
{research}
"""
    )

    # =========================================================
    # 3. PRODUCTION AGENT
    # =========================================================

    production = groq(
        f"""
You are the PRODUCTION DIRECTOR for a Blender 5.2
Grease Pencil football-cartoon system.

Convert the comedy concept into a SHORT animation blueprint.

DO NOT rewrite the concept.

DO NOT add another joke.

DO NOT add another story.

DO NOT invent football facts.

Keep it practical for Blender.

Use reusable assets whenever possible.

RETURN EXACTLY:

🎬 PRODUCTION

RUNTIME:
[seconds]

CHARACTERS:
[list]

ENVIRONMENT:
[one short line]

REUSABLE ASSETS:
[list]

NEW ASSETS:
[list only if necessary]

🎥 SHOTS

SHOT 01
TIME:
CAMERA:
ACTION:
EXPRESSION:
AUDIO/SFX:

SHOT 02
TIME:
CAMERA:
ACTION:
EXPRESSION:
AUDIO/SFX:

SHOT 03
TIME:
CAMERA:
ACTION:
EXPRESSION:
AUDIO/SFX:

SHOT 04
TIME:
CAMERA:
ACTION:
EXPRESSION:
AUDIO/SFX:

SHOT 05
TIME:
CAMERA:
ACTION:
EXPRESSION:
AUDIO/SFX:

🎭 ANIMATION NEEDED:
[list exact actions]

😀 EXPRESSIONS:
[list]

⚠️ NOTES:
[only important Blender notes]

Keep this concise.

COMEDY CONCEPT:
{creative}

VERIFIED RESEARCH:
{research}
"""
    )

    # =========================================================
    # 4. FINAL TELEGRAM OUTPUT
    # =========================================================

    return f"""
⚽ FOOTBALL CARTOON PRODUCTION BRIEF

━━━━━━━━━━━━━━━━━━
🟠 COMEDY CONCEPT
━━━━━━━━━━━━━━━━━━

{creative}

━━━━━━━━━━━━━━━━━━
🔵 PRODUCTION
━━━━━━━━━━━━━━━━━━

{production}
"""
