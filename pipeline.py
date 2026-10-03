from agents import gemini, openrouter, groq


def run_pipeline(idea):

    research = gemini(
        f"""
You are the FOOTBALL EVENT RESEARCH AGENT.

Analyze this football topic:

{idea}

Your job is to find the usable football situation, NOT write a story.

Return ONLY:

EVENT
What actually happened?

PEOPLE
Which real players/teams/coaches are involved?

KEY FACTS
Only the facts needed to understand the situation.

FUNNY OPPORTUNITIES
List 3-5 things about this situation that could become visual comedy.

IMPORTANT:
Do not write a script.
Do not write narration.
Do not create fantasy characters.
Do not give a long historical explanation.
Do not invent facts.

Keep it concise.
"""
    )

    creative = openrouter(
        f"""
You are the COMEDY DIRECTOR for an original football cartoon channel.

Use the football research below.

Your job is NOT to write a story.

Create ONE strong short-form football comedy concept.

The format should be:

REAL FOOTBALL SITUATION
→ SIMPLE FUNNY IDEA
→ PHYSICAL/ VISUAL COMEDY
→ ESCALATION
→ PUNCHLINE

The concept should feel like a short football cartoon situation:
fast, visual, exaggerated and easy to understand.

Do NOT copy Hamid Sahari's actual jokes, scripts, scenes,
characters or artwork. We are building our own original channel.

IMPORTANT:

- One main situation.
- One main joke.
- Real football players when relevant.
- Exaggerated cartoon actions.
- Minimal dialogue.
- Visual comedy first.
- No long story.
- No narration-heavy explanation.
- No fantasy worlds.
- No unnecessary characters.
- No generic national stereotypes.
- Prefer reusable football assets.
- Target 20-60 seconds.

OUTPUT EXACTLY:

🎯 COMEDY CONCEPT

TITLE:
Short title.

REAL SITUATION:
One or two sentences.

COMEDY PREMISE:
One sentence explaining the joke.

CHARACTERS:
Only characters needed.

VISUAL GAG:
What the viewer actually sees.

ESCALATION:
How the joke gets increasingly ridiculous.

PUNCHLINE:
The final visual/comedic payoff.

RUNTIME:
Estimated seconds.

🎬 ACTION SEQUENCE

1.
2.
3.
4.
5.
6.

Each action should describe WHAT WE SEE and WHAT THE
CHARACTER DOES.

Do not write paragraphs of story.

RESEARCH:
{research}
"""
    )

    production = groq(
        f"""
You are the PRODUCTION DIRECTOR for a reusable
Blender 5.2 Grease Pencil football-cartoon system.

Convert the comedy concept into an animation blueprint.

DO NOT rewrite the joke.
DO NOT add a new story.
DO NOT add unnecessary characters.

Your job is to tell the animator exactly what needs to be built
and animated.

OUTPUT:

🎬 PRODUCTION BLUEPRINT

RUNTIME:

CHARACTERS:
List characters required.

REUSABLE ASSETS:
Characters, actions, expressions, props and environments
that can come from the existing library.

NEW ASSETS:
Only things that must be created specifically for this video.

ENVIRONMENT:

PROPS:

🎥 SHOT LIST

For every shot:

SHOT:
TIME:
CAMERA:
CHARACTER:
ACTION:
EXPRESSION:
PROP:
DIALOGUE/SFX:
PURPOSE:

Use these camera presets when useful:

CAM_WIDE
CAM_MED
CAM_CLOSE
CAM_TIGHT
CAM_TWO_SHOT
CAM_TRACK
CAM_PUSH
CAM_REACTION

🎭 ANIMATION REQUIREMENTS

List the exact actions needed.

😀 EXPRESSIONS

List the expressions needed.

🔊 AUDIO

List dialogue/SFX/music cues only.

⚠️ PRODUCTION NOTES

Mention anything difficult, reusable or important for Blender.

Keep the answer practical.
This is a production blueprint, NOT a story.

COMEDY CONCEPT:

{creative}
"""
    )

    return f"""
⚽ FOOTBALL CARTOON PRODUCTION BRIEF

━━━━━━━━━━━━━━━━━━
🟠 COMEDY CONCEPT
━━━━━━━━━━━━━━━━━━

{creative}

━━━━━━━━━━━━━━━━━━
🔵 PRODUCTION BLUEPRINT
━━━━━━━━━━━━━━━━━━

{production}
"""
