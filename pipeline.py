from agents import research_agent, creative_agent, production_agent, review_agent
from knowledge import load_knowledge

def run_pipeline(user_request: str) -> str:
    knowledge = load_knowledge()

    research = research_agent(user_request, knowledge)
    creative = creative_agent(research, knowledge)
    production = production_agent(research, creative, knowledge)
    final = review_agent(research, creative, production, knowledge)

    return (
        "⚽ FINAL VIDEO RECOMMENDATION\n\n"
        + final
    )
