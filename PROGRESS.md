# Stocxi — Progress Tracker

> AI must update this file after every implementation session.
> Mark ✅ when done, 🔄 when in progress, ❌ when blocked.

---

## Phase 1 — Backend

### Setup
- ✅ FastAPI project scaffold (`main.py` + `config.py`)
- ✅ `.env` file configured (Upstash Redis + OpenRouter key)
- ✅ Redis client connected (Upstash) — `cache/redis_client.py`
- ✅ CORS configured (wildcard dev, configurable for prod)
- ✅ Health check endpoint `/health` (includes Redis connection status)
- ✅ `requirements.txt` — all deps installed in `stocxi` conda env (Python 3.11)
- ✅ `backend/.gitignore` — `.env` excluded from git

### Data Services
- ✅ `yfinance_service.py` — price + fundamentals (NSE via nsepython, BSE fallback via httpx chart API)
- ✅ `screener_service.py` — quarterly P&L, annual P&L, balance sheet, cashflow, shareholding + top-ratios (PE, market cap, book value, ROCE, ROE)
- ✅ `screener_service.py` — MF holdings extraction via Screener investor API (`domestic_institutions` drilldown, MF-filtered)
- ✅ `technicals_service.py` — RSI, MACD, ADX, ATR, BB, EMA via `ta` library; OHLCV: yfinance → jugaad-data → empty (3-tier)
- ✅ `news_service.py` — Google News RSS primary, yfinance fallback; returns 10 articles
- ✅ `ai_service.py` — OpenRouter (nvidia/nemotron free), structured JSON verdict, SEBI disclaimer, retry + malformed-JSON retry + risk-aware verdict normalization

### Caching
- ✅ Redis caching wrapper implemented (`cache_get`, `cache_set`, `cache_delete`)
- ✅ TTLs set per data type (300s price / 604800s financials / 7200s news / 21600s analysis / 3600s search)
- ✅ Cache invalidation (`cache_delete`)

### API Endpoints (Routers)
- ✅ `GET /api/v1/stock/{symbol}` — overview: price + fundamentals + technicals (merged, cached 5m)
- ✅ `GET /api/v1/stock/{symbol}/financials` — quarterly + annual P&L, BS, CF, shareholding, MF holdings + MF source status fields (cached 7d)
- ✅ `GET /api/v1/stock/{symbol}/news` — headlines with `?limit=` param (cached 2h)
- ✅ `GET /api/v1/stock/{symbol}/announcements` — NSE corporate announcements (primary), BSE fallback (cached 2h)
- ✅ `GET /api/v1/analysis/{symbol}` — AI verdict with `?risk_level=low|medium|high` (cached 6h)
- ✅ `GET /api/v1/search?q={query}` — autocomplete (nsepython prefix match, fallback top-50 list)
- ✅ Wire routers into `main.py` (router prefix bug fixed)

### Testing (Smoke Tests — `test_services.py`)
- ✅ `yfinance_service` — RELIANCE: ₹1314, 52W ✅, invalid symbol raises ValueError ✅
- ✅ `screener_service` — 12 quarterly rows, 10 BS rows, PE: 23.2, Market Cap: 1779655 Cr ✅
- ✅ `technicals_service` — RSI: 39.97 Neutral, MACD: Bearish, EMA: Bearish (jugaad-data) ✅
- ✅ `news_service` — 10 articles from Google News RSS ✅
- ✅ `ai_service` — Verdict: HOLD, Fundamentals: Neutral, plain English response ✅
- ✅ End-to-end API test via `uvicorn` + curl — all 5 endpoints responding ✅
- ✅ All endpoints tested with RELIANCE + TCS — correct data returned ✅
- ✅ Edge case: invalid symbol returns 404 with `detail`
- ✅ Edge case: Screener timeout chaos test returns graceful 404 (no 500 crash)
- ✅ Financials endpoint verified for quarterly/annual/balance sheet/cash flow/shareholding across RELIANCE/TCS/INFY/HDFCBANK
- ✅ MF holdings verified populated for RELIANCE/INFY and explicitly unavailable for symbols without source rows (e.g. TCS/HDFCBANK)

---

## Phase 2 — Frontend

### Setup
- [ ] Next.js 15 project scaffold
- [ ] Tailwind CSS configured
- [ ] API lib (`lib/api.ts`) set up
- [ ] Environment variables set

### Pages
- [ ] Home page (`app/page.tsx`) — search + trending
- [ ] Stock detail page (`app/stock/[symbol]/page.tsx`)

### Components
- [ ] `SearchBar.tsx` — autocomplete search
- [ ] `StockHeader.tsx` — price, change, key stats
- [ ] `TabNav.tsx` — tab switcher
- [ ] `OverviewTab.tsx` — fundamentals cards
- [ ] `FinancialsTab.tsx` — quarterly P&L table
- [ ] `TechnicalsTab.tsx` — indicator cards
- [ ] `NewsTab.tsx` — news list
- [ ] `AIAnalysis.tsx` — trigger + verdict panel

### UX
- [ ] Progressive loading (skeleton screens)
- [ ] Error states handled
- [ ] Mobile responsive
- [ ] Risk level selector working

---

## Phase 3 — Deployment

- [ ] Backend running on Ubuntu server
- [ ] Cloudflare Tunnel configured
- [ ] Frontend deployed to Vercel
- [ ] `NEXT_PUBLIC_API_URL` set in Vercel env
- [ ] End-to-end test on production URL
- [ ] SEBI disclaimer visible on all stock pages

---

## Phase 4 — Sentiment Layer (Later)

- [ ] CLI scraper repo integrated
- [ ] Twitter sentiment endpoint
- [ ] Reddit sentiment endpoint
- [ ] Sentiment added to AI analysis prompt
- [ ] Cached with 2hr TTL

---

## Known Issues / Blockers

| Issue | Status | Notes |
|---|---|---|
| `pandas-ta` repo deleted from GitHub | ✅ Fixed | Switched to `ta==0.11.0` from PyPI |
| yfinance 429 from Yahoo crumb endpoint | ✅ Fixed | Switched to nsepython (NSE direct) + httpx chart API (BSE fallback) |
| yfinance 429 also on `yf.download()` (OHLCV) | ✅ Fixed | Added jugaad-data as priority 2 OHLCV source (NSE direct) |
| OpenRouter model `deepseek-chat-v3-0324:free` 404 | ✅ Fixed | Switched to `nvidia/nemotron-3-super-120b-a12b:free` |
| Screener market cap "1,77,604 Cr." couldn't parse | ✅ Fixed | Regex-based number extraction strips non-numeric suffixes |
| nsepython returns `company_name` as symbol ticker | ✅ Mitigated | Added fallback name extraction and screener-enriched output where available |
| Sector always `None` | 🔄 Known | Screener doesn't expose sector in a reliable HTML element; will use NSE industry field |
| `mf_holdings` empty for some symbols | 🔄 Known data variance | Source investor API may not expose MF rows for every stock (status field added in API) |

---

## Data Source Map (Current)

| Data | Source | Fallback |
|---|---|---|
| Price, 52W, Change | nsepython (NSE direct) | httpx Yahoo chart API |
| PE, Market Cap, Book Value, ROCE, ROE | Screener.in `#top-ratios` | None (shown as null) |
| Quarterly P&L, Balance Sheet, Cash Flow | Screener.in tables | None (404 if empty) |
| Shareholding pattern | Screener.in | None |
| Mutual fund holdings | Screener investor API (`/api/3/{companyId}/investors/domestic_institutions/quarterly/`) | Empty with `mf_holdings_source_status=not_available` |
| OHLCV (technicals base) | yfinance `download()` | jugaad-data (NSE) |
| Technical indicators | `ta` library on OHLCV | Empty dict (never crash) |
| News headlines | Google News RSS | yfinance `.news` |
| Corporate announcements | NSE corporate announcements API (via nsepython) | BSE public API |
| AI analysis | OpenRouter nvidia/nemotron free | Error dict (graceful) |

---

## Changes Log

| Date | What Changed | Why |
|---|---|---|
| 2026-04-14 | Project initialized | First setup |
| 2026-04-14 | `requirements.txt` created, all deps installed in conda env `stocxi` | Phase 1 backend scaffold |
| 2026-04-14 | `main.py`, `config.py`, `.env`, `.gitignore` created | FastAPI app + config |
| 2026-04-14 | `cache/redis_client.py` created | Async Redis wrapper with TTL constants |
| 2026-04-14 | `services/yfinance_service.py` created → switched to nsepython | Yahoo Finance 429 IP block |
| 2026-04-14 | `services/screener_service.py` created + `#top-ratios` scraping added | PE, market cap, book value |
| 2026-04-14 | `services/technicals_service.py` created with jugaad-data fallback | Yahoo `yf.download()` also blocked |
| 2026-04-14 | `services/news_service.py` created (Google News RSS) | yfinance `.news` also 429-prone |
| 2026-04-14 | `services/ai_service.py` created (OpenRouter, nemotron free) | Structured AI verdict + SEBI disclaimer |
| 2026-04-14 | `routers/stock.py` + `routers/analysis.py` created | API layer wiring all services |
| 2026-04-14 | All 5 services smoke-tested with RELIANCE | 4/4 test_services.py passing |
| 2026-04-14 | `main.py` router prefix bug fixed (removed duplicate `prefix=/stock`) | Routers self-declare /api/v1/... prefix |
| 2026-04-14 | `services/search_service.py` + `routers/search.py` created | GET /api/v1/search?q= autocomplete |
| 2026-04-14 | All 3 routers wired into `main.py` | Phase 1 API complete |
| 2026-04-14 | `/health` now includes Redis status | Align health response with runtime readiness checks |
| 2026-04-14 | `services/announcements_service.py` switched to NSE corporate announcements primary + BSE fallback | BSE endpoint returned HTML/empty in runtime; NSE is reliable |
| 2026-04-14 | `services/ai_service.py` improved with risk-aware verdict normalization and malformed-JSON retries | Reduce unstable responses and improve risk-level behavior |
| 2026-04-14 | `services/screener_service.py` MF holdings extraction added via investor API drilldown | Populate previously empty `mf_holdings` where source data exists |
| 2026-04-14 | `routers/stock.py` financial cache key versioned (`v2`→`v3`) | Invalidate stale cached financial payloads after schema/parser updates |
| 2026-04-14 | `GET /api/v1/stock/{symbol}/financials` now returns `mf_holdings_source_status` + `mf_holdings_note` | Frontend can show explicit availability state instead of blank table |
