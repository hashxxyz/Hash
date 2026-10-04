# AI Football Betting Guru

## Environment variables

Required in Vercel:

- TELEGRAM_BOT_TOKEN
- GEMINI_API_KEY
- OPENROUTER_API_KEY
- GROQ_API_KEY
- API_FOOTBALL_KEY

## Commands

- /tips
- /safe
- /goals
- /btts
- /acca
- /help

The bot automatically retrieves today's fixtures from API-Football,
uses available pre-match prediction/odds data, and sends the strongest
probability-based opportunities.

## Important

The first version intentionally does not pretend to scrape Forebet,
FreeSuperTips, Sofascore, FotMob, Flashscore, FBref, Understat or
FootyStats when no reliable API/feed has been connected. Those sources
can be added as secondary evidence later.

The bot must never present a bet as guaranteed.
