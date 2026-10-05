# AI Football + Basketball Betting Guru

Telegram bot on Vercel. Football + basketball data from API-Sports, analysed by Gemini
(automatic fallback to Groq, then OpenRouter). Picks come back as structured data and are
formatted by the code (render.py), so the Telegram layout is always clean.

## Commands
/tips (everything), /football, /basketball, /over, /under, /corners, /1x2, /dc, /firsthalf,
/goals, /btts, /safe, /acca (max 3 legs), /help

Analysis is cached 30 min, so running /over then /corners then /dc costs one scan, not three.

## Vercel environment variables
Required: TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY, API_FOOTBALL_KEY

Optional:
- ALLOWED_CHAT_IDS — comma-separated chat IDs allowed to use the bot (empty = anyone)
- GEMINI_MODELS, OPENROUTER_MODEL, GROQ_MODEL — override model names
- ODDS_BOOKMAKER — API-Sports bookmaker id to use for odds (empty = any available)
- MIN_CONFIDENCE (default 6) — "strong pick" threshold
- FOOTBALL_ODDS_CALLS (6), FOOTBALL_PREDICTION_CALLS (2), MAX_FOOTBALL (30),
  BASKETBALL_ODDS_CALLS (6), MAX_BASKETBALL (12), CACHE_SECONDS (1800)

## API-Sports limits
Free plan = 100 calls/day and roughly 10 calls/minute per API. One football scan = 1 fixtures call
+ up to 6 odds calls (one per league, covering all that league's matches) + 2 prediction calls = 9.
On a paid plan, raise the numbers above to cover more leagues.

## Notes
- Corners and 1st-half picks are based on bookmaker odds only (no corner statistics are supplied),
  so corner confidence is capped at 7/10.
- Probability is capped at 88% and odds are checked against the real odds data (invented odds are dropped).
- vercel.json sets maxDuration to 60s.
- legacy/ holds the old football-cartoon /newvideo bot files; not used by this bot.
