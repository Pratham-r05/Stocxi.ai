# Stocxi — Social Sentiment Component
# Opus Agentic Workflow Prompt

> You are Claude Opus operating in autonomous agentic mode.
> Read ARCHITECTURE.md, AI_CONTEXT.md, and this file before touching any code.
> Every agent below has ONE job. Complete agents in order. Never skip ahead.

---

## STEP 0 — BEFORE ANYTHING ELSE

1. Read `ARCHITECTURE.md` — understand the full system
2. Read `AI_CONTEXT.md` — understand stack decisions, constraints, Pratham's preferences
3. Read `backend/main.py` — understand app structure
4. Read `backend/services/ai_service.py` — understand code style and docstring pattern
5. Read `backend/services/news_service.py` — understand fallback pattern and async style
6. Read `backend/requirements.txt` — know what's already installed

After reading, create `CLAUDE.md` in the project root (see Agent 1).

---

## AGENT WORKFLOW

Each agent does ONE task. After each agent completes:
- Update `PROGRESS.md` (created by Agent 1) — mark the agent done, note what changed
- Wait. Do not proceed to next agent automatically. Let Pratham confirm.

---

## AGENT 1 — SETUP: Create project documentation files

**Job:** Create two tracking files. No code yet.

### File 1: `CLAUDE.md` (project root)

Create this file with the following content — it is the living reference for all future AI work on this project:

```markdown
# CLAUDE.md — Stocxi AI Working Reference

> One-line description per function. Update after every session.
> This file is the memory layer for Claude Code across sessions.

---

## Project: Stocxi
AI-powered Indian stock analysis platform. NSE/BSE stocks → full data + Claude verdict.
Stack: FastAPI (Python 3.11) + Next.js 15 + Upstash Redis + OpenRouter → DeepSeek.

---

## Core Rules (never violate)
- Incremental only — one file at a time, never full rewrites
- Match existing code style in `backend/services/`
- All new deps → `requirements.txt`
- Every function must have a one-line docstring comment: `# what this does`
- No function should crash the app — always return fallback on exception
- Use existing `redis_client.py` for all caching — never create new cache layer
- Python 3.11 compatible only

---

## Function Registry

### backend/services/ai_service.py
| Function | What it does |
|---|---|
| `_build_user_prompt()` | Builds the structured text prompt sent to OpenRouter from fundamentals/technicals/news dicts |
| `_normalize_final_verdict()` | Maps raw model output to BUY/HOLD/AVOID with safe fallback |
| `_risk_adjusted_verdict()` | Applies deterministic score overlay to model verdict based on risk level |
| `_call_openrouter()` | Sync HTTP call to OpenRouter with 3x retry + backoff; strips JSON fences from response |
| `_validate_and_enrich()` | Fills missing keys with defaults, adds metadata (symbol, generated_at, disclaimer) |
| `analyse()` | Async public entry point — runs OpenRouter call in thread pool, never raises |

### backend/services/news_service.py
| Function | What it does |
|---|---|
| `_fetch_google_news()` | Fetches from Google News RSS; primary source, India-focused, no auth needed |
| `_fetch_yfinance_news()` | Fetches via yfinance .news property; fallback, may 429 |
| `_get_news_sync()` | Sync orchestrator — tries Google News, then yfinance, returns [] on both fail |
| `get_news()` | Async public entry point — runs sync fetch in thread pool |

### backend/services/screener_service.py
| Function | What it does |
|---|---|
| _(fill in after reading file)_ | |

### backend/services/technicals_service.py
| Function | What it does |
|---|---|
| _(fill in after reading file)_ | |

### backend/services/yfinance_service.py
| Function | What it does |
|---|---|
| _(fill in after reading file)_ | |

### backend/services/sentiment_service.py ← TO BE CREATED
| Function | What it does |
|---|---|
| _(populated by Agent 3)_ | |

---

## Cache Keys (full registry)
| Key pattern | TTL | Data |
|---|---|---|
| `stock:overview:{symbol}` | 300s | Price, fundamentals, technicals merged |
| `stock:financials:{symbol}` | 604800s | Quarterly P&L, BS, CF, shareholding |
| `stock:news:{symbol}` | 7200s | List of news headlines |
| `stock:analysis:{symbol}:{risk}` | 21600s | AI verdict JSON |
| `search:{query}` | 3600s | Autocomplete results |
| `stock:sentiment:reddit:{symbol}` | 3600s | Reddit posts + sentiment (TO BE ADDED) |
| `stock:sentiment:twitter:{symbol}` | 3600s | Twitter posts + sentiment (TO BE ADDED) |
| `stock:sentiment:chart:{symbol}` | 3600s | [{date, reddit_score, twitter_score}] (TO BE ADDED) |

---

## Sentiment Component Status
- [ ] Agent 1 — Setup files (CLAUDE.md + PROGRESS.md)
- [ ] Agent 2 — Tool selection + .env spec
- [ ] Agent 3 — sentiment_service.py
- [ ] Agent 4 — Router integration (routers/stock.py)
- [ ] Agent 5 — AI prompt extension (ai_service.py)
- [ ] Agent 6 — requirements.txt + smoke test
```

---

### File 2: `PROGRESS.md` (project root)

```markdown
# PROGRESS.md — Sentiment Component Build Tracker

Last updated: [timestamp when you create this]

---

## Status

| Agent | Task | Status | Files Changed |
|---|---|---|---|
| 1 | Setup files | ✅ Done | CLAUDE.md, PROGRESS.md (created) |
| 2 | Tool selection + .env spec | ⏳ Pending | — |
| 3 | sentiment_service.py | ⏳ Pending | — |
| 4 | Router integration | ⏳ Pending | — |
| 5 | AI prompt extension | ⏳ Pending | — |
| 6 | Requirements + smoke test | ⏳ Pending | — |

---

## Decisions Log
_(agents append here as they make decisions)_

---

## Known Issues
_(agents append here when they hit problems)_
```

After creating both files:
- Update PROGRESS.md: mark Agent 1 ✅ Done
- Stop. Wait for Pratham to confirm before Agent 2.

---

## AGENT 2 — PLAN: Tool selection + .env spec

**Job:** Research and decide which CLI tools to use. Write the plan. No code yet.

Output a decision doc appended to `PROGRESS.md` under `## Decisions Log` covering:

### 2a. Reddit tool decision
Evaluate these options:
- `praw` — official Reddit Python API (requires app credentials, free, reliable)
- `asyncpraw` — async version of praw
- `reddit-scraper` — no-auth scrape (may break, less reliable)

Pick one. State: name, pip install command, whether it needs .env credentials, why you chose it.

### 2b. X/Twitter tool decision
Evaluate these options:
- `twscrape` — async scraper using Twitter's guest API, no official key needed
- `snscrape` — older scraper, may be broken post-API changes
- `ntscraper` — newer wrapper around nitter instances

Pick one. State: name, pip install command, auth requirements, why you chose it.

### 2c. Sentiment tool decision
Use `vaderSentiment` — confirmed working, pip-installable, no API key.
State the pip install command.

### 2d. .env additions required
List the exact env var names that need to be added to `backend/.env` and `backend/.env.example`.
Format:
```
# Reddit (via praw)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=stocxi/1.0

# Twitter/X (via twscrape or chosen tool)
TWITTER_USERNAME=
TWITTER_PASSWORD=
TWITTER_EMAIL=
```

### 2e. Risk table
| Risk | Mitigation |
|---|---|
| Reddit auth fails | Return fallback dict, log warning, never raise |
| X/Twitter scraper breaks | Return fallback dict, log warning, never raise |
| Rate limited | Catch exception, return cached data if available, else fallback |
| Company name lookup fails | Use symbol only in query, never fail |
| vaderSentiment returns NaN | Default score to 0.0 |

After writing plan:
- Update PROGRESS.md: mark Agent 2 ✅ Done, list decisions
- Stop. Wait for Pratham to confirm before Agent 3.

---

## AGENT 3 — BUILD: sentiment_service.py

**Job:** Create `backend/services/sentiment_service.py`.

### Rules
- Match docstring style from `ai_service.py` — module-level docstring explaining purpose + spec reference
- Every function gets a one-line `# what this does` comment above it
- Every function returns fallback on exception — NEVER raises
- Use `asyncio.get_event_loop().run_in_executor()` pattern (match `news_service.py`)
- Import guard: wrap tool imports in try/except; if tool not installed, set a module-level flag and return fallback

### Required structure

```python
"""
sentiment_service.py — Reddit + X/Twitter social sentiment for a stock symbol.

Sources: Reddit (via praw) + X/Twitter (via [chosen tool])
Window: Last 7 days only
Sentiment: vaderSentiment — compound score aggregated across posts
Signal: score > 0.15 → BUY | score < -0.15 → AVOID | else → HOLD

MUST NEVER FAIL: every public function returns a valid dict even on total error.
Cache keys:
  stock:sentiment:reddit:{symbol}    TTL: 3600s
  stock:sentiment:twitter:{symbol}   TTL: 3600s
  stock:sentiment:chart:{symbol}     TTL: 3600s
"""
```

### Required functions (in order)

```
_get_company_name(symbol)      # resolves symbol → company name via yfinance, returns symbol on fail
_score_posts(posts)            # runs vaderSentiment on list of post texts, returns aggregate score
_score_to_signal(score)        # maps float score to BUY/HOLD/AVOID string
_score_to_label(score)         # maps float score to Positive/Negative/Neutral string
_build_summary(posts, signal)  # builds 1-2 sentence plain English summary from post texts + signal
_fallback_source(source)       # returns valid empty fallback dict for "reddit" or "twitter"
_fetch_reddit(symbol)          # fetches last 7 days posts from r/IndiaInvestments etc, returns unified list
_fetch_twitter(symbol)         # fetches last 7 days posts from X, returns unified list
_process_source(raw_posts, source, symbol)  # scores + summarizes a list of posts into the unified schema
get_sentiment(symbol)          # async public entry — fetches both sources in parallel, returns combined dict
```

### Return schema (unified, both sources)

```python
{
  "posts": [{"text": str, "score": int, "date": str, "url": str, "source": str}],
  "summary": str,
  "sentiment": "Positive" | "Negative" | "Neutral",
  "sentiment_score": float,   # -1.0 to 1.0
  "signal": "BUY" | "HOLD" | "AVOID",
  "source": "reddit" | "twitter",
  "fetched_at": str           # ISO timestamp
}
```

### Combined return from `get_sentiment()`

```python
{
  "reddit": { ...unified schema... },
  "twitter": { ...unified schema... },
  "combined_signal": "BUY" | "HOLD" | "AVOID",
  "combined_sentiment_score": float,
  "chart_data": [{"date": str, "reddit_score": float, "twitter_score": float}]
}
```

After creating file:
- Add all new functions to CLAUDE.md function registry under `sentiment_service.py`
- Update PROGRESS.md: mark Agent 3 ✅ Done, list files changed
- Stop. Wait for Pratham to confirm before Agent 4.

---

## AGENT 4 — INTEGRATE: routers/stock.py

**Job:** Add sentiment endpoint and wire it into existing overview fetch.

### Rules
- Read `backend/routers/stock.py` fully before touching it
- Incremental only — do NOT rewrite existing endpoints
- Add ONE new endpoint: `GET /stock/{symbol}/sentiment`
- Wire `get_sentiment()` into `asyncio.gather()` inside existing overview handler

### Changes to make

1. Import `sentiment_service` at top of file
2. Add endpoint:
```python
@router.get("/{symbol}/sentiment")
async def get_stock_sentiment(symbol: str):
    # returns Reddit + Twitter sentiment for symbol
```
3. In existing overview handler, add `sentiment_service.get_sentiment(symbol)` to the `asyncio.gather()` call
4. Add `"sentiment"` key to the overview response dict — set to `None` if sentiment fetch fails (never block overview)

After changes:
- Update PROGRESS.md: mark Agent 4 ✅ Done, list exactly what lines changed
- Stop. Wait for Pratham to confirm before Agent 5.

---

## AGENT 5 — EXTEND: ai_service.py

**Job:** Pull sentiment data into the AI prompt.

### Rules
- Read `backend/services/ai_service.py` fully before touching it
- Incremental only — only modify `_build_user_prompt()` and `_validate_and_enrich()`

### Changes to make

1. Add `social_sentiment: dict | None = None` parameter to `analyse()` and `_build_user_prompt()`
2. In `_build_user_prompt()`, append this block if sentiment data available:
```
SOCIAL SENTIMENT (last 7 days):
Reddit: {reddit.sentiment} ({reddit.signal}) — {reddit.summary}
Twitter/X: {twitter.sentiment} ({twitter.signal}) — {twitter.summary}
```
3. In the AI JSON response schema inside the prompt, add:
```json
"social": { "verdict": "Positive|Negative|Neutral", "summary": "1-2 sentences" }
```
4. In `_validate_and_enrich()`, handle the new `"social"` key with fallback:
```python
"social": raw.get("social", {"verdict": "Neutral", "summary": "No social data available."})
```

After changes:
- Update PROGRESS.md: mark Agent 5 ✅ Done, list exactly what changed
- Stop. Wait for Pratham to confirm before Agent 6.

---

## AGENT 6 — FINALIZE: requirements.txt + smoke test

**Job:** Add deps and verify the component works end-to-end.

### Changes to requirements.txt
Append:
```
# ── Sentiment ──────────────────────────────────────────────────────────────────
praw==7.8.1                # Reddit API client — get_sentiment() Reddit source
vaderSentiment==3.3.2      # Offline sentiment scoring — no API key needed
[chosen-twitter-tool]      # X/Twitter scraper — determined by Agent 2
```

### Smoke test
Run these and confirm output:
```bash
cd backend
python -c "
import asyncio
from services.sentiment_service import get_sentiment
result = asyncio.run(get_sentiment('RELIANCE'))
print('reddit signal:', result['reddit']['signal'])
print('twitter signal:', result['twitter']['signal'])
print('combined:', result['combined_signal'])
print('chart data points:', len(result['chart_data']))
"
```

Expected: no crash, valid signals printed, fallback values acceptable if no auth yet.

Also run:
```bash
curl http://localhost:8000/stock/RELIANCE/sentiment
```
Expected: valid JSON response, no 500 error.

After completing:
- Update PROGRESS.md: mark Agent 6 ✅ Done
- Update CLAUDE.md: fill in any missing function entries
- Final summary: paste test output into PROGRESS.md under Known Issues or Decisions Log

---

## COMPONENT CONSTRAINTS (applies to all agents)

- Incremental only — never rewrite existing files
- One file per agent, one agent at a time
- All Redis keys go through existing `cache/redis_client.py`
- Python 3.11 only
- No paid API keys — only free-tier or no-auth tools
- Pratham's preference: short explanations, no rewrites, wait for confirmation
