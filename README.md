# Football AI Orchestrator — V1

Minimal multi-agent Telegram bot for the Football Cartoon Animation System.

## Agent roles

- Gemini: football research / fact structuring
- OpenRouter free model: creative direction
- Groq free model: Blender production + final review

## Shared project brain

The `knowledge/` folder contains project-wide guidance that every agent receives.

Current files:
- `HAMID_FORMAT.md` — original analysis of the format we want to learn from
- `PROJECT_RULES.md` — our production rules and agent boundaries

Add or edit Markdown files there as the project grows.

## Setup

1. Copy `.env.example` to `.env`.
2. Add API keys.
3. Install requirements:
   `pip install -r requirements.txt`
4. Run:
   `python bot.py`

## Vercel

Environment variables can be added in Vercel instead of `.env`.

This V1 intentionally avoids databases, Redis, Upstash, Notion dependencies, dashboards, and Blender automation. Those can be added after the core pipeline works.

## Important

The Hamid reference is a format study, not a source for copying scripts, artwork, characters, jokes, music, or scenes.
