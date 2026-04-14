# Stocxi — AI Context File

> This file is the single source of truth for any AI assistant continuing work on this project.
> Read this FIRST before touching any code. Update it after every session.

---

## What Is Stocxi?

AI-powered Indian stock analysis platform for beginners. Users search any NSE/BSE stock, see full data (fundamentals + technicals + financials), and click "Analyse with AI" to get a plain English Buy/Hold/Avoid verdict broken down by fundamentals, technicals, and news — personalized to their risk level.

---

## Owner

- Name: Pratham
- GitHub: `Pratham-r05` / `QWERTYH35`
- Machine: MacBook Air M-series (dev), Ubuntu Server at `100.96.125.11` (backend)
- Repo: `stocxi` on GitHub

---

## Stack Decisions & Why

| Decision | Choice | Reason |
|---|---|---|
| Price + basic fundamentals | yfinance | Free, no API key, covers NSE/BSE via .NS/.BO suffix |
| Quarterly, BS, CF, Shareholding | Screener.in scrape | Most reliable Indian fundamental data, public, no auth needed |
| Technicals | pandas-ta | Pure Python calculation on yfinance OHLCV, never fails |
| News | yfinance `.news` property | Good enough for phase 1 |
| AI | OpenRouter → Claude Sonnet | Pratham has OpenRouter key, cheaper than direct Anthropic |
| Cache | Upstash Redis | Managed Redis, free tier, works from any server |
| Frontend | Next.js 15 App Router | Latest stable, Vercel native |
| Backend | FastAPI Python 3.11 | Pratham knows FastAPI well |
| Deployment | Vercel (FE) + Cloudflare Tunnel (BE) | ACT fiber blocks incoming ports, tunnel solves this |

---

## What Was Deliberately NOT Built (and why)

| Skipped | Reason |
|---|---|
| indianapi.in | Free tier only 500 req/month, private endpoints require ₹799/month |
| Zerodha Kite / Upstox API | Broker APIs, don't provide fundamentals like quarterly P&L |
| GraphRAG / KuzuDB | Overkill from StockSense v1, killed that project |
| Celery task queue | Not needed, Redis caching handles the load |
| Auth / Watchlist | Phase 2 feature |
| Twitter/Reddit sentiment | Phase 2, CLI scraper to be integrated later |

---

## Critical Implementation Notes

### yfinance Symbol Format
```python
# NSE: append .NS
ticker = yf.Ticker("RELIANCE.NS")

# BSE fallback: append .BO
ticker = yf.Ticker("RELIANCE.BO")

# Always try .NS first, fallback to .BO if info is empty
```

### Screener.in Scraping
```python
# URL pattern
url = f"https://www.screener.in/company/{symbol}/consolidated/"
# Fallback if consolidated not available:
url = f"https://www.screener.in/company/{symbol}/"

# Tables to extract:
# id="quarters"       → quarterly P&L
# id="balance-sheet"  → balance sheet
# id="cash-flow"      → cash flow
# id="shareholding"   → shareholding pattern

# IMPORTANT: Add headers to avoid 403
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
}
```

### Redis Cache Keys
```python
f"stock:overview:{symbol}"          # TTL: 300s (5 min)
f"stock:financials:{symbol}"        # TTL: 604800s (7 days)
f"stock:news:{symbol}"              # TTL: 7200s (2 hrs)
f"stock:analysis:{symbol}:{risk}"   # TTL: 21600s (6 hrs)
f"search:{query}"                   # TTL: 3600s (1 hr)
```

### OpenRouter Model
```python
model = "anthropic/claude-sonnet-4-5"
# Fallback if cost is issue:
# model = "anthropic/claude-haiku-4-5"

# API base URL for OpenRouter:
base_url = "https://openrouter.ai/api/v1"
# Use with standard OpenAI-compatible format
```

### AI Prompt Structure
```
System: You are a SEBI-aware stock analyst assistant. 
        Always add disclaimer. Never give guaranteed returns.
        Respond in structured JSON only.

User: Analyse {symbol} for a {risk_level} risk investor.

      FUNDAMENTALS:
      {fundamentals_data}

      TECHNICALS:
      {technicals_data}

      RECENT NEWS:
      {news_headlines}

      Respond with JSON:
      {
        "fundamentals": { "verdict": "Strong|Weak|Neutral", "summary": "..." },
        "technicals": { "verdict": "Bullish|Bearish|Mixed", "summary": "..." },
        "news": { "verdict": "Positive|Negative|Neutral", "summary": "..." },
        "final_verdict": "BUY|HOLD|AVOID",
        "plain_english": "...",
        "risk_match": true|false
      }
```

---

## Current Project State

**Last updated:** 2026-04-14
**Phase:** Documentation complete, ready to start coding

**Next step:** Build backend first
1. Scaffold FastAPI project
2. Implement yfinance_service.py
3. Implement screener_service.py
4. Implement technicals_service.py
5. Wire up Redis caching
6. Build AI analysis endpoint
7. Test all endpoints with RELIANCE, TCS, INFY

---

## Common Errors & Fixes

| Error | Fix |
|---|---|
| yfinance returns empty dict | Symbol not found, try .BO suffix |
| Screener.in 403 | Add User-Agent header |
| Screener.in timeout | Set timeout=10, return empty dict, frontend shows "unavailable" |
| pandas-ta returns NaN | Not enough historical data, need min 200 candles for EMA200 |
| OpenRouter rate limit | Add retry with exponential backoff |

---

## Pratham's Preferences

- Incremental changes only — never full rewrites
- One file at a time
- Short, compressed explanations
- Code comments should explain WHY not WHAT
- No unnecessary complexity
