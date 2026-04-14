# Stocxi — Data Flow

## Every Data Point: Source → Cache → Frontend

### Price & Basic Fundamentals
| Field | Source | Cache TTL | Notes |
|---|---|---|---|
| Current Price | yfinance `.info["currentPrice"]` | 5 min | |
| Change % | yfinance `.info["regularMarketChangePercent"]` | 5 min | |
| Market Cap | yfinance `.info["marketCap"]` | 5 min | |
| PE Ratio | yfinance `.info["trailingPE"]` | 24 hrs | |
| PB Ratio | yfinance `.info["priceToBook"]` | 24 hrs | |
| EPS | yfinance `.info["trailingEps"]` | 24 hrs | |
| Dividend Yield | yfinance `.info["dividendYield"]` | 24 hrs | |
| 52W High | yfinance `.info["fiftyTwoWeekHigh"]` | 24 hrs | |
| 52W Low | yfinance `.info["fiftyTwoWeekLow"]` | 24 hrs | |
| Volume | yfinance `.info["volume"]` | 5 min | |
| Sector | yfinance `.info["sector"]` | 7 days | |
| Industry | yfinance `.info["industry"]` | 7 days | |
| Book Value | yfinance `.info["bookValue"]` | 24 hrs | |
| Debt to Equity | yfinance `.info["debtToEquity"]` | 24 hrs | |
| ROE | yfinance `.info["returnOnEquity"]` | 24 hrs | |

---

### Technicals (calculated from yfinance OHLCV)
| Indicator | Calculation | Cache TTL | Signal Logic |
|---|---|---|---|
| RSI(14) | pandas-ta `ta.rsi(close, 14)` | 15 min | >70=Overbought, <30=Oversold, else Neutral |
| MACD(12,26,9) | pandas-ta `ta.macd(close)` | 15 min | MACD>Signal=Bullish, else Bearish |
| ADX(14) | pandas-ta `ta.adx(h,l,c,14)` | 15 min | >25=Strong Trend, <20=Weak Trend |
| ATR(14) | pandas-ta `ta.atr(h,l,c,14)` | 15 min | Volatility measure, no signal |
| BB(20,2) | pandas-ta `ta.bbands(close)` | 15 min | Price>Upper=Overbought, <Lower=Oversold |
| EMA(20) | pandas-ta `ta.ema(close, 20)` | 15 min | Price>EMA=Bullish |
| EMA(50) | pandas-ta `ta.ema(close, 50)` | 15 min | Price>EMA=Bullish |
| EMA(200) | pandas-ta `ta.ema(close, 200)` | 15 min | Price>EMA=Long term Bullish |
| Volume SMA(20) | pandas-ta `ta.sma(volume, 20)` | 15 min | Vol>SMA=High Activity |

**OHLCV data source:** `yf.Ticker(symbol).history(period="1y", interval="1d")`
**Minimum candles needed:** 200 (for EMA200), use `period="2y"` to be safe.

---

### Financials (from Screener.in)
| Data | Screener Selector | Cache TTL | Notes |
|---|---|---|---|
| Quarterly P&L | `#quarters table` | 7 days | Revenue, Expenses, EBITDA, Net Profit, EPS |
| Annual P&L | `#profit-loss table` | 7 days | Same fields, annual view |
| Balance Sheet | `#balance-sheet table` | 7 days | Assets, Liabilities, Equity |
| Cash Flow | `#cash-flow table` | 7 days | Operating, Investing, Financing |
| Shareholding | `#shareholding table` | 7 days | Promoter, FII, DII, Public % |

---

### News
| Field | Source | Cache TTL |
|---|---|---|
| Headlines | `yf.Ticker(symbol).news` | 2 hrs |
| Publisher | `.news[i]["publisher"]` | 2 hrs |
| Link | `.news[i]["link"]` | 2 hrs |
| Publish Time | `.news[i]["providerPublishTime"]` | 2 hrs |

---

### AI Analysis (on-demand)
| Input | Source |
|---|---|
| Fundamentals summary | From cached overview data |
| Technicals summary | From cached technicals data |
| News headlines | From cached news data (top 5) |
| Risk level | From user input (low/medium/high) |

**Output cached at:** `stock:analysis:{symbol}:{risk_level}` TTL: 6 hrs

---

## Parallel Fetching Strategy

On cache MISS, fetch all data in parallel using `asyncio.gather`:

```python
overview, financials, news = await asyncio.gather(
    yfinance_service.get_overview(symbol),
    screener_service.get_financials(symbol),
    news_service.get_news(symbol)
)
```

This reduces total fetch time from ~9 sec sequential to ~4 sec parallel.

---

## Fallback Strategy

| Failure | Fallback |
|---|---|
| yfinance returns empty | Return error: "Symbol not found" |
| Screener.in timeout | Return `financials: null`, show "Financial data temporarily unavailable" |
| Screener.in 403 | Rotate User-Agent header, retry once |
| OpenRouter timeout | Return error: "AI analysis unavailable, try again" |
| Redis down | Skip cache, fetch directly (slower but works) |

---

## Data Freshness Guarantees

| Data | How Fresh |
|---|---|
| Price | Max 5 min old |
| Technicals | Max 15 min old |
| News | Max 2 hrs old |
| Fundamentals | Max 24 hrs old |
| Financials (quarterly) | Max 7 days old (acceptable, data updates quarterly) |
| AI Analysis | Max 6 hrs old |
