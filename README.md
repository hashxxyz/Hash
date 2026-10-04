# AI Football + Basketball Betting Guru

## Replace/add in the existing Hash repo
- pipeline.py
- football_data.py
- basketball_data.py (NEW)
- api/index.py
- requirements.txt

Keep agents.py and the existing Vercel setup.

## Vercel environment variables
Existing:
- TELEGRAM_BOT_TOKEN
- GEMINI_API_KEY
- OPENROUTER_API_KEY
- GROQ_API_KEY
- API_FOOTBALL_KEY

Add:
- API_BASKETBALL_KEY

API-Sports provides a free plan with 100 requests/day for each API. The bot intentionally limits per-run calls.

## Commands
/tips — football + basketball
/football — football only
/basketball — basketball only
/safe — conservative picks
/goals — football goals
/btts — football BTTS
/acca — strongest combined selections (max 3)
/help

No guaranteed-win language. Missing data lowers confidence rather than being invented.
