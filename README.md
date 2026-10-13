# AI Betting Guru — Football + Basketball Telegram Bot

A Telegram bot that scans today's football and basketball fixtures and sends back the strongest **over/under** picks, plus match result, double chance, BTTS and basketball winner picks.

Every pick is priced by a statistical model first, compared against bookmaker odds, and only then reviewed by an AI model. The AI chooses and ranks; it never writes the numbers.

Runs serverlessly on **Vercel** (Python) and talks to Telegram through a webhook.

> **Disclaimer:** Picks are model estimates, not guaranteed results. Probabilities come from a simple statistical model blended with bookmaker odds, and have not been back-tested. Betting involves real financial risk. Only bet what you can afford to lose, follow the laws where you live, and do not use this bot if you are under 18.

---

## What it does

- **Football over/under** priced with a Poisson goals model (team scoring/conceding averages, recent form, head-to-head)
- **Basketball over/under and winner** priced from team scoring averages, with the bookmaker's main total line
- **BTTS, 1X2 and double chance** from the same football model
- **Model vs market check:** a pick is kept only if the model agrees with (or is more bullish than) the bookmaker's no-margin probability, and the odds are in a sensible range
- **Only real lines:** lines and odds come from the bookmaker data, never from the AI
- **AI review with fallback:** Gemini, then Groq, then OpenRouter. If all fail, the bot still answers with the model's own ranking
- **Quota-friendly:** results are cached; repeated scans spend API calls on matches not yet covered

## Commands

| Command | What you get |
|---|---|
| `/tips` | Everything: football and basketball, all sections |
| `/totals` | All over/under picks (football + basketball) |
| `/over` | Football over goals |
| `/under` | Football under goals |
| `/goals` | Football over + under |
| `/bbover` | Basketball over (total points) |
| `/bbunder` | Basketball under (total points) |
| `/football` | Football picks only |
| `/basketball` | Basketball picks only |
| `/1x2` | Match result |
| `/dc` | Double chance |
| `/btts` | Both teams to score |
| `/safe` | Conservative picks only (low risk, confidence 7+) |
| `/acca` | Best 3-leg accumulator (max 3 legs, one per match) |
| `/help` | List of commands |

Each pick shows the match, league, kickoff (Lagos time), selection, odds, probability, confidence out of 10, risk, and the model vs market probability.

## How it works

```
Telegram ──► Vercel function (api/index.py)
                  │
                  ▼
             pipeline.py
                  ├─► API-Sports: fixtures, odds, predictions / team statistics   (cached)
                  ├─► engine.py: prices each bet (Poisson / scoring model) and compares with the market
                  ├─► AI (Gemini → Groq → OpenRouter): picks from the priced candidates only
                  └─► render.py: formatted Telegram message
```

1. **Collect:** today's fixtures, then odds league by league and match statistics, within a per-scan API call budget.
2. **Price:** `engine.py` turns statistics into probabilities for each bet and keeps only candidates where model and market agree.
3. **Review:** the AI picks from those candidates and can raise risk labels. Anything it returns that isn't a real candidate is discarded.
4. **Render:** picks are grouped by category and sent to Telegram.

Probability = 60% model + 40% market for football (50/50 for basketball). Confidence is derived from that probability, with a penalty when the model is far more bullish than the market.

## Project structure

```
api/index.py         Telegram webhook handler (Vercel entry point)
pipeline.py          Data collection, caching, AI review, validation
engine.py            Pricing models (football Poisson, basketball scoring) and candidate bets
store.py             Cache and duplicate-update guard (Redis if configured, else in-memory)
agents.py            Gemini / Groq / OpenRouter clients, fallback, key scrubbing
football_data.py     Football-Data.org client (fixtures + season results)
basketball_data.py   ESPN basketball feed (no key)
render.py            Telegram message formatting
vercel.json          Function settings (60 s max duration)
```

## Setup

### 1. Get your keys

| Service | Used for | Where |
|---|---|---|
| Telegram bot token | Receiving and sending messages | [@BotFather](https://t.me/BotFather) → `/newbot` |
| Football-Data.org key | Football fixtures and results (free tier) | [football-data.org](https://www.football-data.org/client/register) |
| API-Sports key (optional) | Basketball only, needs a plan covering the current season | [api-sports.io](https://api-sports.io) |
| Gemini key | Main AI provider | [Google AI Studio](https://aistudio.google.com) |
| Groq key | First fallback | [console.groq.com](https://console.groq.com) |
| OpenRouter key | Second fallback | [openrouter.ai](https://openrouter.ai) |
| Upstash Redis (recommended) | Cache that survives Vercel restarts | Vercel Marketplace → Upstash Redis, or [upstash.com](https://upstash.com) |

You need **at least one** AI key. The same API-Sports key is used for both sports; enable the Basketball API on your account too.

### 2. Deploy to Vercel

1. Clone the repo: `git clone https://github.com/hashxxyz/Hash.git`
2. Import it as a new project in [Vercel](https://vercel.com).
3. Add the environment variables below (Settings → Environment Variables).
4. Deploy.

Opening `https://<your-project>.vercel.app/api` in a browser should show: *AI Betting Guru is LIVE*.

### 3. Connect Telegram

Open this URL in a browser with your own values (the secret can be any string of letters, numbers, `_` or `-`):

```
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<your-project>.vercel.app/api&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

You should see `"ok": true`. Then message your bot `/start`.

## Environment variables

**Required**

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `FOOTBALL_DATA_KEY` | Football-Data.org API token (football) |
| `ENABLE_BASKETBALL` | Optional. On by default; set `false` to turn basketball off |
| `BB_LEAGUES` | Optional. ESPN leagues to scan, default `nba,wnba` |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` | At least one required; all three recommended |

**Strongly recommended**

| Variable | Description |
|---|---|
| `ALLOWED_CHAT_IDS` | Comma-separated Telegram chat IDs allowed to use the bot. If empty, anyone can use it and drain your API quota. Find your ID with [@userinfobot](https://t.me/userinfobot) |
| `TELEGRAM_WEBHOOK_SECRET` | Same value as `secret_token` in `setWebhook`. Requests without it are rejected |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | Persistent cache (Vercel KV's `KV_REST_API_URL` / `KV_REST_API_TOKEN` also work) |

**Tuning (optional)**

| Variable | Default | Description |
|---|---|---|
| `MIN_CONFIDENCE` | `6` | Minimum confidence (1–10) for a pick |
| `MIN_PROB` | `60` | Football: minimum blended probability (%) |
| `MIN_BB_PROB` | `56` | Basketball: minimum blended probability (%) |
| `MIN_ODDS` / `MAX_ODDS` | `1.30` / `3.0` | Odds range considered |
| `BB_MIN_GAP` | `4` | Basketball: minimum points between model total and the line |
| `CACHE_SECONDS` | `1800` | How long a scan is reused |
| `PREDICTION_CACHE_SECONDS` | `21600` | How long match statistics are reused |
| `STATS_CACHE_SECONDS` | `43200` | How long basketball team statistics are reused |
| `MAX_FOOTBALL` / `MAX_BASKETBALL` | `30` / `12` | Max matches considered |
| `FOOTBALL_ODDS_CALLS` | `4` | Football odds API calls per scan (one page ≈ 10 matches) |
| `ODDS_MAX_PAGES` | `2` | Odds pages read per league |
| `ODDS_CACHE_SECONDS` | `3600` | How long odds are reused (longer = more matches covered over repeated scans) |
| `BB_HISTORY_DAYS` | `14` | Free plan: days of past basketball results used for team form |
| `FOOTBALL_PREDICTION_CALLS` | `5` | Football statistics calls per scan |
| `BASKETBALL_ODDS_CALLS` / `BASKETBALL_STATS_CALLS` | `4` / `5` | Basketball calls per scan |
| `ODDS_BOOKMAKER` | any | API-Sports bookmaker ID to use |
| `GEMINI_MODELS` | see `agents.py` | Comma-separated Gemini models, tried in order |
| `GROQ_MODEL` / `OPENROUTER_MODEL` | `openai/gpt-oss-120b` / `openrouter/free` | Fallback models |
| `LLM_TIMEOUT` / `TIME_BUDGET` | `40` / `55` | Seconds per AI request / per scan |

## Limits and good-to-know

- **Football-Data.org free tier:** 12 competitions (Premier League, Championship, Bundesliga, Serie A, La Liga, Ligue 1, Eredivisie, Primeira Liga, Champions League, Brazilian Serie A, World Cup, Euros), 10 calls/minute, and **no odds**. Football picks are model-only: a Poisson goals model built from this season's results. There is no market check, so treat the probabilities as rough. `FD_MAX_COMPETITIONS` (8) caps calls per scan; results are cached 12 hours.

- **API-Sports free plan:** the free plan blocks the current season on league odds and team statistics ("Free plans do not have access to this season"). The bot detects this and switches automatically: football odds are read match by match, and basketball form is built from the last 14 days of results. Coverage starts small and grows over the first few scans. A paid plan removes this limit and covers every match in one scan.

- **API-Sports free plan:** 100 calls/day and about 10/minute per API. Defaults keep a scan at about 10 calls per sport. Statistics are cached, so each new scan covers matches the previous one missed. On a paid plan, raise the `*_CALLS` variables.
- **Cache:** without Redis the cache lives in memory and resets whenever Vercel starts a fresh instance, so repeated commands may cost extra API calls. Set up Redis to avoid this.
- **60-second limit:** `vercel.json` caps the function at 60 seconds; scans are budgeted to fit.
- **Some matches get skipped** when the call budget runs out; the message says so. Run again later to cover more.
- **Only matches that haven't started** are analysed. Times are Lagos time (WAT).
- **The models are simple.** Poisson goals and scoring averages ignore injuries, lineups, motivation and pace. Treat picks as one input, not a guarantee.

## Security notes

- Never commit API keys or the Telegram token; keep them in Vercel environment variables.
- Keys and bot tokens are scrubbed from logs and error messages.
- Set `ALLOWED_CHAT_IDS` and `TELEGRAM_WEBHOOK_SECRET` so only you (and Telegram) can use the endpoint.
