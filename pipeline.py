from agents import gemini, openrouter, groq


def run_pipeline(idea):

    research = gemini(
        f"""
You are the football research agent.

Analyze this football video idea:

{idea}

Give:
1. Verified football facts
2. What is uncertain
3. Useful visual/comedy hooks

Keep it concise.
"""
    )

    creative = openrouter(
        f"""
You are the creative director for an original football cartoon channel.

Turn this research into a short, funny, event-first football cartoon.

Separate:
FACTS
COMEDIC INTERPRETATION
FICTIONAL ACTION

Include:
- Hook
- 2-4 beats
- Visual gag
- Escalation
- Punchline
- Characters
- Environment
- Approximate runtime

RESEARCH:

{research}
"""
    )

    production = groq(
        f"""
You are the production director.

Turn this concept into a practical Blender/Grease Pencil production brief.

Include:
- Characters
- Actions
- Expressions
- Props
- Environment
- Camera shots
- Timing
- Reusable assets
- New assets
- Production risks

Do not rewrite the comedy.

CONCEPT:

{creative}
"""
    )

    return f"""
⚽ FINAL FOOTBALL CARTOON BRIEF

━━━━━━━━━━━━━━
🟢 RESEARCH
━━━━━━━━━━━━━━

{research}

━━━━━━━━━━━━━━
🟠 CREATIVE
━━━━━━━━━━━━━━

{creative}

━━━━━━━━━━━━━━
🔵 PRODUCTION
━━━━━━━━━━━━━━

{production}
"""
