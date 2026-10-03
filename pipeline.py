from agents import call_gemini, call_openrouter, call_groq

def run_pipeline(idea):
    research=call_gemini("You are the football research agent. Analyze this event/idea. Return verified facts, uncertainty, and visual hooks. Keep it concise.\n\n"+idea)
    creative=call_openrouter("You are the football comedy creative director. Turn the research below into a short event-first football cartoon concept. Separate facts from comedic fiction. Include hook, 2-4 beats, visual gag, punchline, cast, environment, and approximate runtime.\n\nRESEARCH:\n"+research)
    production=call_groq("You are the Blender production director. Convert this concept into a practical Blender/Grease Pencil production brief. Specify reusable/new assets, characters, actions, expressions, environment, props, camera shots, timing, and production risks. Do not rewrite the joke.\n\n"+creative)
    return "⚽ FINAL PRODUCTION BRIEF\n\nRESEARCH:\n"+research[:2500]+"\n\nCREATIVE:\n"+creative[:5000]+"\n\nPRODUCTION:\n"+production[:6000]
