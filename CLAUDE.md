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

### backend/services/sentiment_service.py
| Function | What it does |
|---|---|
| `_get_company_name()` | Resolves symbol → company name via yfinance; returns symbol on fail |
| `_score_posts()` | Runs vaderSentiment on list of post texts; returns aggregate compound score |
| `_score_to_signal()` | Maps float score to BUY/HOLD/AVOID string (thresholds: ±0.15) |
| `_score_to_label()` | Maps float score to Positive/Negative/Neutral string |
| `_build_summary()` | Builds 1-2 sentence plain English summary from post texts + signal |
| `_fallback_source()` | Returns valid empty fallback dict for "reddit" or "twitter" |
| `_fetch_reddit()` | Fetches last 7 days posts from r/IndiaInvestments + r/IndianStockMarket via praw |
| `_fetch_twitter()` | Fetches last 7 days posts from X via twscrape; returns unified post list |
| `_process_source()` | Scores + summarizes a list of posts into the unified schema dict |
| `get_sentiment()` | Async public entry — fetches both sources in parallel, returns combined dict |

---

## Cache Keys (full registry)
| Key pattern | TTL | Data |
|---|---|---|
| `stock:overview:{symbol}` | 300s | Price, fundamentals, technicals merged |
| `stock:financials:{symbol}` | 604800s | Quarterly P&L, BS, CF, shareholding |
| `stock:news:{symbol}` | 7200s | List of news headlines |
| `stock:analysis:{symbol}:{risk}` | 21600s | AI verdict JSON |
| `search:{query}` | 3600s | Autocomplete results |
| `stock:sentiment:reddit:{symbol}` | 3600s | Reddit posts + sentiment |
| `stock:sentiment:twitter:{symbol}` | 3600s | Twitter posts + sentiment |
| `stock:sentiment:chart:{symbol}` | 3600s | [{date, reddit_score, twitter_score}] |

---

## Sentiment Component Status
- [x] Agent 1 — Setup files (CLAUDE.md + PROGRESS.md)
- [x] Agent 2 — Tool selection + .env spec
- [x] Agent 3 — sentiment_service.py
- [x] Agent 4 — Router integration (routers/stock.py)
- [x] Agent 5 — AI prompt extension (ai_service.py)
- [x] Agent 6 — requirements.txt + smoke test
