from agents import gemini, openrouter, groq


def run_pipeline(idea):

    research = gemini(
        f"""
You are the FOOTBALL RESEARCH & TREND AGENT.

Analyze this football topic:

{idea}

Your job is NOT to write a cartoon story.

Find the most useful REAL football situation behind the topic.

OUTPUT:

EVENT
- What actually happened?

KEY PEOPLE
- Which real players, coaches, teams or officials are involved?

FACTS
- 3-6 concise verified facts.

CURRENT CONTEXT
- Why is this relevant or funny right now?

POSSIBLE SITUATIONS
Give 3 different real situations that could become a short
football cartoon.

For each situation:
- Situation
- People involved
- What makes it visually funny
- What part is fact
- What part would be fictional exaggeration

IMPORTANT:
Do not invent events.
Do not turn the answer into a documentary.
Do not force historical information if the topic has a more
interesting current situation.
"""
        .strip()
    )

    creative = openrouter(
        f"""
You are the CREATIVE DIRECTOR of an ORIGINAL football cartoon channel.

Your task is to create a short football cartoon concept inspired by
the HIGH-LEVEL FORMAT of short football situation cartoons.

DO NOT copy Hamid Sahari's characters, drawings, scripts, jokes,
specific scenes, animation style, music or trademarks.

Instead use the following storytelling characteristics:

- A recognizable real football situation
- One simple comedic premise
- Real football personalities as characters when relevant
- Exaggerated physical reactions
- Visual storytelling
- Very little dialogue
- Fast escalation
- A clear visual payoff
- Usually 20-60 seconds
- The situation should be understandable immediately

IMPORTANT:

Do NOT create:
- fantasy kingdoms
- random chefs
- ghosts
- statues
- generic national stereotypes
- long historical documentaries
- complicated multi-act stories

unless the specific football joke genuinely requires them.

The characters should behave like exaggerated cartoon versions
of the real football situation.

The comedy should come from WHAT THE PLAYER IS DOING,
not from inventing an unrelated personality.

STRUCTURE:

1. PREMISE
One sentence describing the funny situation.

2. HOOK
What the viewer sees in the first 1-3 seconds.

3. SETUP
Establish the real football situation.

4. ESCALATION
The situation becomes increasingly ridiculous.

5. PAYOFF
One strong visual/comedic ending.

6. OPTIONAL DIALOGUE
Only if genuinely necessary.

7. VISUAL GAGS
List the physical/cartoon actions that make the joke work.

8. CHARACTERS
Only the characters actually needed.

9. ENVIRONMENT
Keep it simple and reusable.

10. RUNTIME
Prefer 20-60 seconds.

Then produce:

SHOT-BY-SHOT BLUEPRINT

For every shot:

SHOT
TIME
WHAT WE SEE
CHARACTER ACTION
FACIAL EXPRESSION
CAMERA
DIALOGUE
SFX
COMEDIC PURPOSE

Keep the number of shots practical.

Separate clearly:

REAL FOOTBALL FACT
COMEDIC EXAGGERATION
FICTIONAL ACTION

RESEARCH:

{research}
"""
        .strip()
    )

    production = groq(
        f"""
You are the PRODUCTION DIRECTOR for a reusable
Blender 5.2 Grease Pencil football-cartoon system.

Convert the creative concept into a production-ready blueprint.

DO NOT rewrite the joke.
DO NOT create a different story.

Preserve the exact comedic premise.

TARGET:
20-60 seconds.

For every shot provide:

SHOT ID
START
END
DURATION
CAMERA
ENVIRONMENT
CHARACTERS
ACTION
EXPRESSION
PROP
ANIMATION
DIALOGUE/SFX

CAMERA PRESETS:

CAM_WIDE
CAM_MED
CAM_CLOSE
CAM_TIGHT
CAM_TWO_SHOT
CAM_TRACK
CAM_PUSH
CAM_REACTION

Prioritize reusable assets.

Separate:

REUSABLE CHARACTERS
REUSABLE ACTIONS
REUSABLE EXPRESSIONS
REUSABLE ENVIRONMENTS
REUSABLE PROPS

NEW ASSETS REQUIRED

ANIMATION LIBRARY GAPS

PRODUCTION RISKS

BLENDER IMPLEMENTATION

The production should be achievable by a small creator using
2D Grease Pencil characters.

Avoid unnecessary new assets.

CREATIVE CONCEPT:

{creative}
"""
        .strip()
    )

    return f"""
⚽ FOOTBALL CARTOON PRODUCTION BRIEF

━━━━━━━━━━━━━━━━━━
🟢 RESEARCH / REAL EVENT
━━━━━━━━━━━━━━━━━━

{research}

━━━━━━━━━━━━━━━━━━
🟠 CREATIVE / COMEDIC PREMISE
━━━━━━━━━━━━━━━━━━

{creative}

━━━━━━━━━━━━━━━━━━
🔵 BLENDER / PRODUCTION
━━━━━━━━━━━━━━━━━━

{production}
"""
