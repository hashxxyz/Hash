import os
import requests

def call_openai_compatible(base_url, api_key, model, system, user):
    response = requests.post(
        base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def gemini(prompt):
    key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    response = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def research_agent(request, knowledge):
    return gemini(
        f"""You are the FOOTBALL RESEARCH AGENT.
Your job: identify and structure relevant football facts and useful visual opportunities.
Do not write the comedy script.

PROJECT KNOWLEDGE:
{knowledge}

USER REQUEST:
{request}

Return:
FACTS
SOURCES/VERIFICATION NEEDED
UNCERTAINTIES
VISUAL OPPORTUNITIES
RECOMMENDATION
"""
    )

def creative_agent(research, knowledge):
    key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    return call_openai_compatible(
        "https://openrouter.ai/api/v1/chat/completions",
        key,
        model,
        """You are the CREATIVE DIRECTOR.
Turn verified football research into an original short football-comedy concept.
Use the project's format principles without copying any creator's scripts, artwork, characters, jokes, or scenes.
Separate real facts from comedic interpretation and fictional action.""",
        f"PROJECT KNOWLEDGE:\n{knowledge}\n\nRESEARCH:\n{research}"
    )

def production_agent(research, creative, knowledge):
    key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    return call_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        key,
        model,
        """You are the PRODUCTION/TECHNICAL DIRECTOR.
Convert the concept into a practical Blender 5.2 Grease Pencil production plan.
Specify reusable characters, actions, expressions, props, environment, camera shots, timing, and new assets.
Prefer reuse over unnecessary new work.""",
        f"PROJECT KNOWLEDGE:\n{knowledge}\n\nRESEARCH:\n{research}\n\nCREATIVE CONCEPT:\n{creative}"
    )

def review_agent(research, creative, production, knowledge):
    key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    return call_openai_compatible(
        "https://api.groq.com/openai/v1/chat/completions",
        key,
        model,
        """You are the FINAL REVIEW AGENT.
Check factual separation, originality, comedy clarity, production feasibility, runtime, and asset reuse.
Do not silently invent missing facts. Flag uncertainty.
Return a concise final recommendation with:
APPROVAL STATUS
CONCEPT
SHOT PLAN
ASSETS
ISSUES TO VERIFY""",
        f"KNOWLEDGE:\n{knowledge}\n\nRESEARCH:\n{research}\n\nCREATIVE:\n{creative}\n\nPRODUCTION:\n{production}"
    )
