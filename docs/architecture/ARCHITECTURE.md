# ARCHITECTURE.md — Stocxi System Architecture

> Law of the system. Every agent, every contributor follows this exactly.
> Changes require: entry in NEW_PROGRESS.md + version bump in config/versions.yaml.

---

## 1. What Stocxi Does

Stocxi analyzes Indian stocks for retail investors with no finance background.
User searches a stock. System fetches data from verified sources, builds a
knowledge graph, runs a strict 10-step analysis protocol through an LLM, and
returns a transparent, citation-backed report.

**Not a SEBI advisor.** Never says "buy" or "sell." Describes what signals
historically imply. Every claim cites the data node it came from.

---

## 2. System Flow

```
User (browser)
    │
    ▼
FastAPI Gateway (auth, rate limit)
    │
    ▼
Analysis Cache (Redis) ──── hit → return cached
    │ miss
    ▼
Orchestrator Agent
    ├── Technical Agent ──── NSE OHLCV → ta library → 17 indicator nodes
    ├── Fundamental Agent ── BSE ratios + Screener financials → ratio/statement nodes
    ├── News Agent ───────── RSS feeds → sanitized news nodes
    ├── Announcement Agent ─ NSE + BSE filings → announcement nodes
    └── Context Agent ────── Market regime + sector + peers + data completeness
            │
            ▼
    Normalizer (raw → Node schema)
    Source Reconciler (conflicts → priority winner, logged)
    Sanitizer (prompt safety)
            │
            ▼
    Knowledge Graph Builder (nodes + typed edges)
            │
            ▼
    Anonymizer (STOCK_A, SECTOR_X, EXEC_A)
            │
            ▼
    Analysis Agent (10-step protocol, temp=0, pinned model)
            │
            ▼
    Verifier Agent (strip uncited claims)
            │
            ▼
    Formatter (de-anonymize, shape output)
            │
            ▼
    Audit Log (immutable) + Cache Write → Response
```

---

## 3. Data Sources — Verified and Pinned

All sources defined in `config/sources.yaml`. Fetching from unlisted domains
raises `UnapprovedSourceError`.

### 3.1 Technical Data (Price + OHLCV)

| Source | Library/API | What It Returns | Priority |
|---|---|---|---|
| NSE `equityQuote(sym)` | BennyThadikaran/NseIndiaApi | open, high, low, close, volume, date | L1 |
| NSE `quote(sym)` | same | LTP, change%, VWAP, 52W H/L, sector PE, circuit limits, delivery% | L1 |
| NSE `fetch_equity_historical_data` | same | 247 rows/year OHLCV (exact cols: chOpeningPrice, chTradeHighPrice, chTradeLowPrice, chClosingPrice, chTotTradedQty) | L1 |
| BSE `quote(code)` | BennyThadikaran/BseIndiaApi | Open, High, Low, LTP, PrevClose | L2 |
| BSE `equityPriceVolumeT12M(code)` | same | 12-month daily price+volume chart data | L2 |
| yfinance `.NS` → `.BO` → alt ticker | yfinance library | OHLCV DataFrame | L3 |

### 3.2 Fundamental Ratios (Current Values)

| Source | Method | Fields | Priority |
|---|---|---|---|
| BSE `equityMetaInfo(code)` | BseIndiaApi | PE, ConPE, EPS, ConEPS, ROE, ConROE, PB, OPM, NPM, Sector, Industry | L1 |
| BSE `resultsSnapshot(code)` | BseIndiaApi | Revenue, Net Profit, EPS, Cash EPS, OPM%, NPM% (latest 2Q + FY, standalone) | L1 |
| BSE `getScripTradingStats(code)` | BseIndiaApi | Market Cap (full + free-float), Turnover, WAP | L1 |
| BSE `quoteWeeklyHL(code)` | BseIndiaApi | 52W/monthly/weekly H/L with dates | L1 |
| Screener.in top-ratios | scraper | PE, ROE, ROCE, Book Value, EPS, Dividend Yield | L2 |

### 3.3 Financial Statements (Historical)

| Source | Method | What It Returns | Priority |
|---|---|---|---|
| Screener.in quarterly P&L | scraper with recency-pick | 12+ quarters: Sales, Expenses, Operating Profit, OPM, Net Profit, EPS | L1 |
| Screener.in annual P&L | same | 10+ years with TTM column | L1 |
| Screener.in balance sheet | same | Equity, Debt, Total Assets, Reserves | L1 |
| Screener.in cash flow | same | CFO, CFI, CFF, Net Change | L1 |
| BSE `resultsSnapshot` | BseIndiaApi | Revenue + Net Profit for 2Q + FY (cross-validation only) | L2 |

**Screener recency rule:** Fetch BOTH consolidated and standalone URLs. Compare
the most recent period header from `#quarters`. Use whichever has more recent
data. Rationale: small caps like QUESTCAP have stale consolidated pages while
standalone is current.

### 3.4 Shareholding

| Source | Method | Fields | Priority |
|---|---|---|---|
| NSE `shareholding(sym)` | NseIndiaApi | Promoter%, Public%, Employee Trust% (90 quarterly records) | L1 |
| Screener.in #shareholding | scraper | Promoter%, FII%, DII%, Public% (quarterly breakdown) | L2 |

### 3.5 Corporate Actions + Announcements

| Source | Method | What It Returns | Priority |
|---|---|---|---|
| NSE `announcements()` | NseIndiaApi | desc, attachment PDF/XBRL, timestamp (market-wide) | L1 |
| NSE `boardMeetings(sym)` | NseIndiaApi | date, purpose, result PDF/XBRL links | L1 |
| NSE `actions(sym)` | NseIndiaApi | dividends, bonus, splits with ex-date | L1 |
| BSE `actions(code)` | BseIndiaApi | dividends, splits with ex-date (33 records) | L1 |
| BSE `resultCalendar(from, to)` | BseIndiaApi | upcoming 374 result dates | L1 |

### 3.6 News (Approved Domains Only)

| Domain | Feed | Priority |
|---|---|---|
| moneycontrol.com | RSS | 1 |
| economictimes.indiatimes.com | RSS | 1 |
| business-standard.com | RSS | 1 |
| livemint.com | RSS | 1 |
| reuters.com (India) | RSS | 2 |
| bqprime.com | RSS | 2 |
| news.google.com | RSS search fallback | 3 |

### 3.7 Forbidden Sources

Twitter/X, Reddit, YouTube, Telegram, WhatsApp, TradingView community,
Investopedia, any blog or influencer page, any domain not in sources.yaml.

### 3.8 Future Paid Source (Post-MVP)

FinEdge API (XBRL-sourced financial statements, ₹2k/month quarterly billing).
Replaces Screener scraping with structured JSON when revenue justifies it.
Would become L1 for financial statements; Screener becomes L2.

---

## 4. Node Schema

Every piece of data stored as a Node. Pydantic model in `backend/schemas/node.py`.

```python
class Node(BaseModel):
    node_id: str          # deterministic: {stock}|{category}|{name}|{as_of_date}
    stock: str
    category: Literal["technical", "fundamental", "news", "announcement", "context"]
    name: str             # e.g. "RSI", "Revenue_Growth", "Dividend_Declared"
    value: str            # display string
    value_raw: dict       # original payload for audit
    date: date
    signal: Literal["positive", "negative", "neutral"]
    confidence: float     # 1.0 (L1) / 0.85 (L2) / 0.70 (L3) / 0.50 (L4)
    source: str           # source_id from sources.yaml
    source_url: str | None
    horizon_relevance: Literal["short", "long", "both"]
    weight: float         # from config/weights.yaml, stamped at normalization
    weight_version: str
    schema_version: int
    fetched_at_ist: datetime
    as_of_date: date      # point-in-time: what the world knew on this date
    sanitized: bool       # must be True before entering any LLM prompt
```

**Rules:**
- `node_id` is deterministic. Collisions overwrite (idempotent).
- `value_raw` preserves the original; `value` is the display string.
- `weight` is pulled from `config/weights.yaml` at normalization time.
- `sanitized: True` required before any node enters an LLM prompt.
- `as_of_date` is critical for backtest — no future data leakage.
- Malformed nodes are dropped at the normalizer and logged.

### 4.1 Node Data Formats by Category

Every node's `value` is a human-readable string. The `value_raw` dict preserves the
exact payload for audit and computation. Below is the **exact format** for each node type.

#### Technical Indicator Nodes

| Node Name | `value` (display string) | `value_raw` (dict) | Signal Logic |
|---|---|---|---|
| `RSI_14` | `"RSI: 65.4"` | `{"rsi": 65.4}` | >70 negative (overbought), <30 positive (oversold), else neutral |
| `MACD` | `"MACD: 12.5, Signal: 10.2"` | `{"macd": 12.5, "signal": 10.2, "histogram": 2.3}` | macd > signal positive, else negative |
| `SMA_20` | `"SMA20: 1845.6, Price: 1920.3"` | `{"sma": 1845.6, "price": 1920.3, "position": "above"}` | price > sma positive, else negative |
| `SMA_50` | `"SMA50: 1780.2, Price: 1920.3"` | `{"sma": 1780.2, "price": 1920.3, "position": "above"}` | same as SMA_20 |
| `SMA_200` | `"SMA200: 1650.8, Price: 1920.3"` | `{"sma": 1650.8, "price": 1920.3, "position": "above"}` | same as SMA_20 |
| `EMA_12` | `"EMA12: 1890.1"` | `{"ema": 1890.1, "price": 1920.3}` | price > ema positive |
| `EMA_26` | `"EMA26: 1860.5"` | `{"ema": 1860.5, "price": 1920.3}` | price > ema positive |
| `ADX` | `"ADX: 28.3"` | `{"adx": 28.3, "plus_di": 25.1, "minus_di": 18.7}` | >25 = trending; plus_di > minus_di positive |
| `Stochastic_K` | `"Stoch %K: 78.2"` | `{"k": 78.2, "d": 72.1}` | >80 negative (overbought), <20 positive |
| `Stochastic_D` | `"Stoch %D: 72.1"` | `{"d": 72.1}` | same thresholds as %K |
| `Williams_%R` | `"Williams %R: -22.5"` | `{"wr": -22.5}` | >-20 negative, <-80 positive |
| `CCI` | `"CCI: 145.8"` | `{"cci": 145.8}` | >100 positive (trend), <-100 negative |
| `OBV` | `"OBV: 12.5M, Trend: rising"` | `{"obv": 12500000, "obv_sma": 11800000, "trend": "rising"}` | rising positive, falling negative |
| `VWAP` | `"VWAP: 1855.2, Price: 1920.3"` | `{"vwap": 1855.2, "price": 1920.3}` | price > vwap positive |
| `Volume_SMA_20` | `"Vol: 5.2M, Avg: 4.1M"` | `{"volume": 5200000, "sma_20": 4100000, "ratio": 1.27}` | ratio > 1.5 = high volume |
| `Bollinger_Upper` | `"BB Upper: 1980.5"` | `{"upper": 1980.5, "middle": 1850.0, "lower": 1719.5, "price": 1920.3}` | price near upper negative |
| `Bollinger_Lower` | `"BB Lower: 1719.5"` | `{"upper": 1980.5, "middle": 1850.0, "lower": 1719.5, "price": 1920.3}` | price near lower positive |

All numeric values are `float`. Volumes are raw integers (not abbreviated).

#### Fundamental Ratio Nodes

| Node Name | `value` | `value_raw` | Signal Logic |
|---|---|---|---|
| `PE_Ratio` | `"PE: 24.5"` | `{"pe": 24.5, "con_pe": 23.8, "sector_pe": 28.1}` | pe < sector_pe positive |
| `PB_Ratio` | `"PB: 3.2"` | `{"pb": 3.2}` | <1 positive, >5 negative (sector-dependent) |
| `ROE` | `"ROE: 18.5%"` | `{"roe": 18.5, "con_roe": 17.9}` | >15 positive, <10 negative |
| `EPS` | `"EPS: 42.3"` | `{"eps": 42.3, "con_eps": 41.8}` | growth-based signal |
| `OPM` | `"OPM: 22.1%"` | `{"opm": 22.1}` | >20 positive, declining negative |
| `NPM` | `"NPM: 15.3%"` | `{"npm": 15.3}` | >10 positive, declining negative |
| `ROCE` | `"ROCE: 21.4%"` | `{"roce": 21.4}` | >15 positive |
| `Dividend_Yield` | `"Div Yield: 1.8%"` | `{"yield": 1.8}` | >2 positive for income investors |
| `Book_Value` | `"Book Value: 520.3"` | `{"book_value": 520.3}` | informational |
| `Market_Cap` | `"Market Cap: 14.2L Cr"` | `{"market_cap_cr": 1420000, "free_float_cr": 850000}` | categorical (large/mid/small) |
| `52W_High_Low` | `"52W: 2100-1450, CMP: 1920"` | `{"high": 2100, "low": 1450, "price": 1920, "high_date": "2026-01-15", "low_date": "2025-08-22"}` | near high neutral, near low positive |

All percentages stored as plain numbers (18.5 not 0.185). All currency in INR.
Market cap in crores (Cr). Dates as ISO strings in `value_raw`.

#### Financial Statement Nodes

| Node Name | `value` | `value_raw` | Notes |
|---|---|---|---|
| `Revenue_Quarterly` | `"Q3 FY25 Revenue: 2,64,905 Cr"` | `{"periods": [{"period": "Dec 2024", "value_cr": 264905}, ...], "source_type": "consolidated", "num_quarters": 12}` | Array of period objects, newest first |
| `Net_Profit_Quarterly` | `"Q3 FY25 PAT: 21,804 Cr"` | `{"periods": [{"period": "Dec 2024", "value_cr": 21804}, ...]}` | Same structure |
| `OPM_Quarterly` | `"Q3 FY25 OPM: 15.2%"` | `{"periods": [{"period": "Dec 2024", "value_pct": 15.2}, ...]}` | Percentage array |
| `EPS_Quarterly` | `"Q3 FY25 EPS: 16.1"` | `{"periods": [{"period": "Dec 2024", "value": 16.1}, ...]}` | Per-share value |
| `Revenue_Annual` | `"FY24 Revenue: 9,73,508 Cr"` | `{"periods": [{"period": "Mar 2024", "value_cr": 973508}, ...], "has_ttm": true, "ttm_value_cr": 1005000}` | 10+ years + TTM |
| `Balance_Sheet` | `"Total Assets: 15.2L Cr"` | `{"equity_cr": 520000, "debt_cr": 340000, "total_assets_cr": 1520000, "reserves_cr": 480000, "period": "Mar 2024"}` | Latest period snapshot |
| `Cash_Flow` | `"CFO: 1,12,500 Cr"` | `{"cfo_cr": 112500, "cfi_cr": -85000, "cff_cr": -22000, "net_change_cr": 5500, "period": "Mar 2024"}` | Latest period |
| `Revenue_Growth` | `"Revenue Growth: 12.5% YoY"` | `{"yoy_pct": 12.5, "qoq_pct": 3.2, "cagr_3y_pct": 15.1}` | Computed from statement data |
| `Profit_Growth` | `"PAT Growth: 8.2% YoY"` | `{"yoy_pct": 8.2, "qoq_pct": -2.1, "cagr_3y_pct": 11.8}` | Computed |

Financial periods stored as `"Mon YYYY"` strings (e.g., `"Dec 2024"`, `"Mar 2025"`).
All monetary values in crores (Cr) as integers or floats — never lakhs or abbreviated.
`source_type` is always `"consolidated"` or `"standalone"` — never ambiguous.

#### Shareholding Nodes

| Node Name | `value` | `value_raw` |
|---|---|---|
| `Promoter_Holding` | `"Promoter: 50.3%"` | `{"current_pct": 50.3, "prev_quarter_pct": 50.1, "change_pct": 0.2, "quarters": [{"period": "Dec 2024", "pct": 50.3}, ...]}` |
| `FII_Holding` | `"FII: 22.1%"` | `{"current_pct": 22.1, "prev_quarter_pct": 23.5, "change_pct": -1.4, "quarters": [...]}` |
| `DII_Holding` | `"DII: 18.5%"` | `{"current_pct": 18.5, "prev_quarter_pct": 17.8, "change_pct": 0.7, "quarters": [...]}` |
| `Public_Holding` | `"Public: 9.1%"` | `{"current_pct": 9.1, "quarters": [...]}` |
| `Promoter_Pledge` | `"Pledge: 2.1%"` | `{"pledge_pct": 2.1, "prev_pct": 1.8}` |

Percentages as plain numbers. `quarters` array has 4-8 periods for trend analysis.

#### News Nodes

| Node Name | `value` | `value_raw` |
|---|---|---|
| `News_Item` | `"Reliance Q3 profit rises 12%"` (sanitized headline, max 100 chars) | `{"headline": "...", "body_truncated": "..." (max 400 tokens), "source_domain": "moneycontrol.com", "published_at": "2026-04-25T14:30:00+05:30", "url": "https://...", "sentiment": "positive", "relevance_score": 0.85}` |

Body is sanitized (HTML stripped, imperatives removed). `sentiment` is computed,
not from the source. `url` preserved for citation but never sent to LLM.

#### Announcement Nodes

| Node Name | `value` | `value_raw` |
|---|---|---|
| `Board_Meeting` | `"Board meeting: Q3 results on 2026-01-15"` | `{"purpose": "Financial Results", "date": "2026-01-15", "attachment_url": "https://...", "filing_type": "board_meeting"}` |
| `Dividend_Declared` | `"Dividend: Rs 8.5 per share, ex-date 2026-02-01"` | `{"amount": 8.5, "ex_date": "2026-02-01", "record_date": "2026-02-03", "type": "interim"}` |
| `Bonus_Split` | `"Bonus 1:1 declared"` | `{"ratio": "1:1", "type": "bonus", "ex_date": "2026-03-15"}` |
| `Result_Announced` | `"Q3 FY25 results: PAT up 12%"` | `{"quarter": "Q3 FY25", "summary": "...", "attachment_url": "https://..."}` |
| `SEBI_Action` | `"SEBI warning for insider trading"` | `{"action_type": "warning", "details": "...", "date": "2026-04-20"}` |
| `Promoter_Trade` | `"Promoter sold 0.5% stake"` | `{"trade_type": "sell", "pct": 0.5, "shares": 500000, "date": "2026-04-18"}` |

Dates as ISO strings. Amounts in INR. Attachment URLs preserved for reference only.

#### Context Nodes

| Node Name | `value` | `value_raw` |
|---|---|---|
| `Market_Regime` | `"Market: Bullish (Nifty above 200 SMA)"` | `{"regime": "bullish", "nifty_50d_sma": 22500, "nifty_200d_sma": 21800, "vix": 14.2, "nifty_ltp": 23100}` |
| `Sector_Trend` | `"IT sector: Sideways"` | `{"sector": "Information Technology", "trend": "sideways", "sector_pe": 28.5, "3m_return_pct": 2.1}` |
| `Peer_Snapshot` | `"Peers: TCS (PE 28), INFY (PE 25), WIPRO (PE 22)"` | `{"peers": [{"name": "TCS", "pe": 28, "roe": 45, "market_cap_cr": 1200000}, ...]}` |
| `Data_Completeness` | `"17 tech, 11 fundamental, 5 news, 3 announcements"` | `{"technical": 17, "fundamental": 11, "news": 5, "announcement": 3, "context": 4, "missing_sources": ["screener_timeout"]}` |

### 4.2 Data Format Rules

1. **All numbers are native types** — `float` for decimals, `int` for counts/volumes. Never strings like `"12.5"`.
2. **Percentages as plain numbers** — `18.5` not `0.185` or `"18.5%"`.
3. **Currency in INR crores** — `264905` (crores) not `26490500` (lakhs). Field suffix `_cr` for clarity.
4. **Dates as ISO strings** — `"2026-04-25"` for dates, `"2026-04-25T14:30:00+05:30"` for timestamps.
5. **Period labels as "Mon YYYY"** — `"Dec 2024"`, `"Mar 2025"`. Consistent across all statement data.
6. **Arrays newest-first** — Time series in `value_raw` are ordered most recent period first.
7. **No nulls in required fields** — Missing data = node not emitted. Never `{"pe": null}`.
8. **`value` is always a human-readable string** — short, for display. Max 150 chars.
9. **`value_raw` is always a dict** — machine-readable, complete data for computation and audit.

---

## 5. Knowledge Graph

### 5.1 Edge Types

| Type | Meaning | Example |
|---|---|---|
| `supports` | Same direction, reinforces | RSI bullish + MACD bullish |
| `contradicts` | Opposite direction, conflict | RSI bullish + Revenue declining |
| `derived_from` | One computed from another | EPS derived from Net Profit |
| `correlates` | Statistical co-movement | Sector trend + stock momentum |
| `caused_by` | Causal link (rare, justified) | Dividend announced → price jump |
| `part_of` | Hierarchical grouping | OPM is part of P&L analysis |
| `same_domain` | Same category relationship | RSI and MACD are both momentum |

### 5.2 Relevance Scoring

```
relevance = weight × confidence × recency_factor

recency_factor:
  age < 7 days  → 1.0
  age < 30 days → 0.8
  age < 90 days → 0.5
  age > 90 days → 0.2
```

### 5.3 Storage

Postgres tables: `nodes` (partitioned by as_of_date monthly) + `node_edges`
(from_id, to_id, relation, strength, analysis_id). Recursive CTEs for
traversal. Neo4j is not adopted at this scale.

---

## 6. Analysis Protocol — 10-Step Strict

### Steps 1-9: Zero deviation (80%)

```
1. VALIDATE     Load nodes. Drop schema_version mismatch or sanitized=false.
                Verify all context nodes. Abort if below minimum thresholds.
2. ANONYMIZE    STOCK_A, SECTOR_X, EXEC_A, BRAND_A, PEER_1/2/3, LOCATION_A.
                Numeric bucketing for market cap. Relative % preserved.
3. TECHNICAL    Read 17 indicator nodes → verdict with node_id citations.
4. FUNDAMENTAL  Read ratio + financial nodes → verdict with node_id citations.
5. NEWS         Read sanitized news nodes → verdict with node_id citations.
6. ANNOUNCEMENT Read filing nodes → verdict with node_id citations.
7. WEIGHTS      Apply profile weights (horizon × risk → category mix).
8. AGREEMENTS   List cross-category agreements, each backed by node_id pairs.
9. CONTRADICTIONS  List conflicts. Resolve via contradiction hierarchy.
```

### Step 10: Free reasoning (20%)

Model may surface non-obvious cross-category connections, spot divergences
(price up + OBV down = distribution), apply contextual judgment. Constrained
to supplied node_ids only.

### Contradiction Hierarchy (highest wins)

1. Regulatory / SEBI / legal action
2. Promoter pledging increase or promoter selling
3. Fundamental deterioration (declining revenue, rising debt)
4. Leadership change / audit qualifier / credit downgrade
5. Technical divergence
6. News sentiment (lowest standalone weight)

---

## 7. Anonymization Layers

| Layer | Defense |
|---|---|
| A — Identity scrub | Replace stock/sector/promoter/exec/brand names with tokens |
| B — Numeric bucketing | Market cap → category; absolute ₹ → order of magnitude |
| C — Citation firewall | Every output claim must carry a node_id. Verifier strips uncited. |
| D — Red-team CI test | Anonymized RELIANCE/TCS/HDFCBANK prompts must not leak real names. |

---

## 8. Signal Weight Table

Defined in `config/weights.yaml`. v1 is hand-picked bootstrap.
From v2 onward, weights are refit quarterly from backtest (logistic regression
per horizon × sector). Hand-editing after v1 is forbidden.

All weights within a category × horizon normalize to sum 1.0 at load time.

---

## 9. User Profile System

Profile = (horizon, risk). Sector preference affects peer selection only,
not weights.

| Category | Short-term | Long-term |
|---|---|---|
| Technical | 0.50 | 0.20 |
| News | 0.30 | 0.10 |
| Fundamental | 0.15 | 0.50 |
| Announcement | 0.05 | 0.20 |

Risk adjustments applied after category mix:
- Conservative: negative signals ×1.3, volatility ×1.2
- Moderate: unchanged
- Aggressive: positive momentum ×1.2, volatility ×0.9

---

## 10. Determinism + Audit

Every production analysis:
- `temperature = 0`, pinned model id, pinned prompt version, pinned weight version
- Deterministic seed where provider supports it
- Random tie-breakers use hash of node_ids, not RNG

Audit row per analysis (append-only, 7-year retention):
```
analysis_id, stock, profile_hash, as_of_date, data_hash,
prompt_version, weight_version, model_id,
input_nodes_json, full_prompt, raw_output, final_output,
conflicts_resolved, created_at_ist
```

---

## 11. Output Format

### User-facing
- What the Data Suggests (plain English, no node IDs)
- Signals In Favor (bullet list with reasons)
- Signals Against (never hidden)
- Data Disclosure ("Analysis based on 17 technical indicators, 11 ratios...")
- Disclaimer (mandatory, every output)

### Admin view (Pratham only)
- Reasoning trace (10 steps with node_ids)
- Verifier diff (stripped claims)
- Source reconciliation log
- Knowledge graph visualization
- Run metadata (model, prompt version, latency, tokens)

---

## 12. Insufficient Data Policy

- < 17 technical nodes → degrade gracefully, mark incomplete
- 0 fundamental or 0 announcement nodes → refuse analysis entirely
- Return clear message: "We don't have enough public data on this stock."
- Low-confidence output is worse than no output.

---

## 13. Disclaimer (mandatory, every output)

"This analysis is AI-generated from publicly available data as a pattern
description for educational use. Stocxi is not a SEBI-registered investment
advisor. Historical signal patterns are not predictions. Consult a qualified
advisor before investing."

---

*Authoritative architecture. Law of the system.*
