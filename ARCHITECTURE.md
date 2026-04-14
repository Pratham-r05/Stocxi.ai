# Stocxi — Architecture

## System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  USER (Browser)                                             │
└───────────────────────────┬─────────────────────────────────┘
                            │ search stock
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND — Vercel                                          │
│  Next.js 15 (App Router)                                    │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / Cloudflare Tunnel
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  BACKEND — Ubuntu server                                    │
│  FastAPI │ routers/stock.py │ routers/analysis.py           │
│                                                             │
│  ┌──────────────────────────────────┐                       │
│  │  Upstash Redis — cache layer     │                       │
│  │  cache miss → fetch from sources │                       │
│  └──────────────────────────────────┘                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ parallel fetch (asyncio.gather)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  DATA SERVICES                                              │
│                                                             │
│  nsepython     Screener.in    jugaad-data     yfinance      │
│  price·52W·vol quarterly·BS·CF OHLCV history  news·PE       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  pandas-ta — RSI·MACD·ADX·ATR·BB·EMA(20/50/200)     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  Fallbacks:                                                 │
│  yfinance → jugaad-data if Yahoo 429                        │
│  Screener timeout → return null, frontend shows N/A         │
└───────────────────────────┬─────────────────────────────────┘
                            │ on "Analyse with AI" click
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  AI ANALYSIS — on-demand only                               │
│                                                             │
│  Prompt builder  →  OpenRouter  →  Claude Sonnet            │
│  (fund+tech+news+risk)                                      │
│                                                             │
│  Fundamentals    Technicals    News        Final verdict    │
│  Strong/Weak     Bullish/Bear  Pos/Neg     BUY/HOLD/AVOID   │
└─────────────────────────────────────────────────────────────┘

Cache TTLs:
  Price: 5 min  │  Technicals: 15 min  │  News: 2 hrs
  Fundamentals: 24 hrs  │  Financials (BS/CF): 7 days
  AI analysis: 6 hrs  │  Redis down → fetch direct (slower)

Phase 2 (later): Twitter / Reddit CLI sentiment layer
```

---

## Request Flow — Stock Page Load

```
1. User searches "RELIANCE"
2. Frontend calls GET /stock/RELIANCE
3. Backend checks Redis cache
   ├── HIT  → return cached data instantly (<100ms)
   └── MISS → fetch from sources in parallel
              ├── nsepython (price + 52W + volume)
              ├── Screener.in (fundamentals + financials)
              ├── jugaad-data → pandas-ta (technicals)
              └── yfinance (news + PE fallback)
              → merge all data
              → store in Redis
              → return to frontend (~3-5 sec first load)
4. Frontend renders progressively:
   ├── Price + header loads first
   ├── Tabs populate as data arrives
   └── "Analyse with AI" button appears last
```

---

## Request Flow — AI Analysis

```
1. User clicks "Analyse with AI"
2. Frontend calls POST /stock/RELIANCE/analyse
   Body: { risk_level: "medium" }
3. Backend:
   ├── Check Redis for cached analysis (TTL: 6hrs)
   ├── HIT  → return cached verdict
   └── MISS → build prompt from:
              ├── fundamentals data
              ├── technicals data
              ├── recent news headlines
              └── user's risk level
              → call OpenRouter → Claude Sonnet
              → parse structured JSON response
              → cache result
              → return to frontend
4. Frontend renders AI panel:
   ├── Fundamentals verdict (Strong/Weak/Neutral)
   ├── Technicals verdict (Bullish/Bearish/Mixed)
   ├── News sentiment (Positive/Negative/Neutral)
   └── Final verdict: BUY / HOLD / AVOID + plain English reason
```

---

## Backend Service Architecture

```
FastAPI App (main.py)
│
├── /routers
│   ├── stock.py
│   │   ├── GET /stock/{symbol}           → StockService.get_overview()
│   │   ├── GET /stock/{symbol}/financials → StockService.get_financials()
│   │   └── GET /stock/{symbol}/news       → NewsService.get_news()
│   └── analysis.py
│       └── POST /stock/{symbol}/analyse   → AIService.analyse()
│
├── /services
│   ├── yfinance_service.py        ← nsepython primary, yfinance fallback
│   │   └── get_price_and_fundamentals(symbol) → dict
│   ├── screener_service.py        ← BeautifulSoup scrape
│   │   └── get_financials(symbol) → dict
│   │       ├── quarterly_results
│   │       ├── balance_sheet
│   │       ├── cash_flow
│   │       ├── shareholding
│   │       ├── pe_ratio          ← from #top-ratios
│   │       ├── market_cap        ← from #top-ratios
│   │       └── sector            ← from company info
│   ├── technicals_service.py      ← jugaad-data OHLCV → pandas-ta
│   │   └── calculate_technicals(symbol) → dict
│   │       ├── RSI(14)
│   │       ├── MACD(12,26,9)
│   │       ├── ADX(14)
│   │       ├── ATR(14)
│   │       ├── Bollinger Bands(20,2)
│   │       ├── EMA(20), EMA(50), EMA(200)
│   │       └── Volume SMA(20)
│   ├── news_service.py            ← yfinance .news
│   │   └── get_news(symbol) → list[dict]
│   └── ai_service.py              ← OpenRouter → Claude Sonnet
│       └── analyse(symbol, fundamentals, technicals, news, risk_level) → dict
│
└── /cache
    └── redis_client.py
        ├── get(key)
        ├── set(key, value, ttl)
        └── invalidate(key)
```

---

## Data Sources (actual, tested)

| Data | Primary Source | Fallback | Status |
|---|---|---|---|
| Price, 52W, Volume | `nsepython` (NSE direct) | yfinance Yahoo chart | ✅ Working |
| PE, Market Cap, Sector | `Screener.in #top-ratios` | yfinance `.info` | 🔄 In progress |
| Quarterly P&L | `Screener.in #quarters` | — | ✅ Working |
| Balance Sheet | `Screener.in #balance-sheet` | — | ✅ Working |
| Cash Flow | `Screener.in #cash-flow` | — | ✅ Working |
| Shareholding | `Screener.in #shareholding` | — | ✅ Working |
| OHLCV (for technicals) | `jugaad-data` NSE historical | yfinance | ✅ Working |
| Technicals | `pandas-ta` on OHLCV | — | ✅ Working |
| News | `yfinance .news` | — | ✅ Working |
| AI Analysis | OpenRouter → Claude Sonnet | Claude Haiku (cheaper) | ✅ Working |

---

## Frontend Architecture

```
Next.js 15 App Router
│
├── app/
│   ├── page.tsx                  ← Home: search bar + trending stocks
│   └── stock/[symbol]/page.tsx   ← Stock detail page
│
├── components/
│   ├── SearchBar.tsx             ← Autocomplete search
│   ├── StockHeader.tsx           ← Price, change, key stats
│   ├── TabNav.tsx                ← Tab switcher
│   ├── tabs/
│   │   ├── OverviewTab.tsx       ← Key fundamentals cards
│   │   ├── FinancialsTab.tsx     ← Quarterly P&L table
│   │   ├── TechnicalsTab.tsx     ← Indicator cards with signals
│   │   └── NewsTab.tsx           ← News list with sentiment
│   └── AIAnalysis.tsx            ← Trigger button + verdict panel
│
└── lib/
    └── api.ts                    ← All fetch calls to FastAPI
```

---

## Data Models

### Stock Overview Response
```json
{
  "symbol": "RELIANCE",
  "company_name": "Reliance Industries Ltd",
  "exchange": "NSE",
  "price": 1314.0,
  "change": -36.2,
  "change_percent": -2.68,
  "market_cap": null,
  "pe_ratio": null,
  "pb_ratio": null,
  "eps": null,
  "dividend_yield": null,
  "week_52_high": 1611.8,
  "week_52_low": 1195.15,
  "volume": null,
  "sector": null,
  "technicals": {
    "rsi": 39.97,
    "rsi_signal": "Neutral",
    "macd": -22.14,
    "macd_signal": "Bearish",
    "adx": 28.38,
    "adx_signal": "Trend",
    "atr": 34.85,
    "bb_upper": 1440.89,
    "bb_lower": 1296.08,
    "ema_20": 1360.26,
    "ema_50": 1394.49,
    "ema_200": 1419.20,
    "overall_signal": "Bearish"
  }
}
```

### AI Analysis Response
```json
{
  "symbol": "RELIANCE",
  "risk_level": "medium",
  "fundamentals": {
    "verdict": "Strong",
    "summary": "Revenue growing steadily, debt manageable, PE in fair range"
  },
  "technicals": {
    "verdict": "Bearish",
    "summary": "RSI neutral, MACD bearish, price below all EMAs"
  },
  "news": {
    "verdict": "Neutral",
    "summary": "No major negative news, routine business announcements"
  },
  "final_verdict": "HOLD",
  "plain_english": "Reliance is a solid company fundamentally but momentum is bearish right now. All EMAs point down. Medium risk investor should wait for stabilisation above ₹1350 before entering.",
  "risk_match": true,
  "generated_at": "2026-04-14T02:30:00Z"
}
```

---

## Caching Keys Pattern

```
stock:overview:{symbol}        TTL: 300s   (5 min)
stock:financials:{symbol}      TTL: 604800s (7 days)
stock:news:{symbol}            TTL: 7200s  (2 hours)
stock:analysis:{symbol}:{risk} TTL: 21600s (6 hours)
search:autocomplete:{query}    TTL: 3600s  (1 hour)
```

---

## Screener.in Scraping Strategy

URL pattern:
```
https://www.screener.in/company/{SYMBOL}/consolidated/
# fallback:
https://www.screener.in/company/{SYMBOL}/
```

Data extracted via BeautifulSoup:
- `#top-ratios` → PE ratio, Market Cap, Book Value, Dividend Yield, ROE, ROCE
- `#quarters` table → quarterly P&L
- `#balance-sheet` table → balance sheet
- `#cash-flow` table → cash flow
- `#shareholding` table → shareholding pattern

Headers required (avoid 403):
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}
```

Cache aggressively (7 days TTL) — Screener data updates quarterly.

---

## Deployment

```
Frontend  → Vercel (automatic deploys from GitHub)
Backend   → Local Ubuntu Server (100.96.125.11)
            └── Cloudflare Tunnel → public HTTPS URL
                └── set as NEXT_PUBLIC_API_URL in Vercel env
```
