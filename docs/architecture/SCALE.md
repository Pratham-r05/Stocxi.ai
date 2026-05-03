# SCALE.md — Performance, Storage, Caching, and Cost Rules

> Every agent and contributor MUST obey these rules. One ignored timeout or one
> cache miss on a popular stock can break reliability and unit economics.

---

## 1. Database Strategy (PostgreSQL / Supabase)

### 1.1 Data Freshness Tiers

Not all data changes at the same rate. Store and refresh accordingly.

| Tier | Data | Refresh Rate | Storage | Why |
|---|---|---|---|---|
| **Static** | BSE scrip codes, NSE symbols, company names, sector mapping, industry classification | Weekly or on-demand | `stocks` table | Changes only on listing/delisting/name change. Fetch once, reuse forever. |
| **Slow** | Fundamentals (PE, PB, ROE, EPS, OPM, NPM), financial statements (quarterly/annual P&L, balance sheet, cash flow), shareholding pattern | Daily EOD for top 500, weekly for rest | `fundamental_cache` table | Changes quarterly (results) or rarely (ratios). No need to re-scrape Screener every request. |
| **Medium** | Technical indicators (RSI, MACD, SMA, etc.), OHLCV prices | Daily EOD for top 500, on-demand for rest | `technical_cache` table | Changes daily at market close. Pre-compute after 3:45 PM IST. |
| **Fast** | News, announcements, corporate filings, market regime | Hourly crawl | `nodes` table (append) | High signal, time-sensitive. Always fetch fresh, cache short. |
| **Computed** | Full analysis results, knowledge graph | On-demand, cached | Redis + `analyses` table | Expensive to compute, shared across users. |

### 1.2 Stock Master Table

```sql
CREATE TABLE stocks (
    symbol          VARCHAR(20) PRIMARY KEY,    -- NSE symbol (e.g., "RELIANCE")
    bse_code        VARCHAR(10),                -- BSE scrip code (e.g., "500325")
    company_name    VARCHAR(200) NOT NULL,
    sector          VARCHAR(100),
    industry        VARCHAR(100),
    yfinance_ticker VARCHAR(30),                -- .NS suffix or alt ticker from alt_tickers.yaml
    market_cap_tier VARCHAR(10),                -- "large", "mid", "small", "micro"
    is_active       BOOLEAN DEFAULT TRUE,
    last_verified   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_stocks_bse ON stocks (bse_code);
CREATE INDEX idx_stocks_sector ON stocks (sector);
CREATE INDEX idx_stocks_tier ON stocks (market_cap_tier);
```

**Population:** Seed from `config/bse_codes.yaml` + NSE symbol list. Refresh weekly
via cron that checks for new listings/delistings.

### 1.3 Fundamental Cache Table

Stores slow-changing fundamental data so we don't re-scrape Screener/BSE every request.

```sql
CREATE TABLE fundamental_cache (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL REFERENCES stocks(symbol),
    data_type       VARCHAR(50) NOT NULL,       -- "ratios", "quarterly_pl", "annual_pl", "balance_sheet", "cash_flow", "shareholding"
    source_id       VARCHAR(30) NOT NULL,       -- "bse_meta", "screener_consolidated", "nse_shareholding"
    source_type     VARCHAR(20),                -- "consolidated" or "standalone"
    confidence      FLOAT NOT NULL,
    data            JSONB NOT NULL,             -- full payload
    period_latest   VARCHAR(20),                -- "Dec 2024" or "Mar 2025" — most recent period in data
    fetched_at      TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,       -- fetched_at + TTL based on data_type
    UNIQUE(symbol, data_type, source_id)
);

CREATE INDEX idx_fund_cache_symbol ON fundamental_cache (symbol, data_type);
CREATE INDEX idx_fund_cache_expires ON fundamental_cache (expires_at);
```

**TTLs by data_type:**
| data_type | TTL | Rationale |
|---|---|---|
| `ratios` | 24 hours | PE/PB change daily with price, but ratios from BSE update EOD |
| `quarterly_pl` | 7 days | Only changes when new quarterly results announced |
| `annual_pl` | 14 days | Annual results once a year |
| `balance_sheet` | 14 days | Same as annual |
| `cash_flow` | 14 days | Same as annual |
| `shareholding` | 7 days | SEBI requires quarterly disclosure |

**Fetch flow:**
1. Request comes in for RELIANCE fundamentals
2. Check `fundamental_cache` WHERE symbol='RELIANCE' AND data_type='quarterly_pl' AND expires_at > NOW()
3. If hit → return `data` JSONB directly (no HTTP call, no scraping)
4. If miss → fetch from source waterfall (BSE/Screener), store in cache, return
5. Background refresh: cron runs daily at 4 PM IST for top 500 stocks

### 1.4 Technical Cache Table

```sql
CREATE TABLE technical_cache (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(20) NOT NULL REFERENCES stocks(symbol),
    indicator       VARCHAR(30) NOT NULL,       -- "RSI_14", "MACD", "SMA_200", etc.
    value_raw       JSONB NOT NULL,
    signal          VARCHAR(10) NOT NULL,       -- "positive", "negative", "neutral"
    as_of_date      DATE NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL,
    UNIQUE(symbol, indicator, as_of_date)
);

CREATE INDEX idx_tech_cache_symbol_date ON technical_cache (symbol, as_of_date DESC);
```

**Pre-computation:** EOD cron at 4:00 PM IST fetches OHLCV and computes all 17
indicators for top 500 stocks. Stored in `technical_cache`. On-demand stocks computed
and cached for 24h.

### 1.5 Node Table (Analysis Nodes)

```sql
CREATE TABLE nodes (
    node_id         VARCHAR(200) PRIMARY KEY,   -- {stock}|{category}|{name}|{as_of_date}
    stock           VARCHAR(20) NOT NULL,
    category        VARCHAR(20) NOT NULL,
    name            VARCHAR(50) NOT NULL,
    value           VARCHAR(200) NOT NULL,       -- display string
    value_raw       JSONB NOT NULL,
    date            DATE NOT NULL,
    signal          VARCHAR(10) NOT NULL,
    confidence      FLOAT NOT NULL,
    source_id       VARCHAR(30) NOT NULL,
    source_url      VARCHAR(500),
    horizon_relevance VARCHAR(10) NOT NULL,
    weight          FLOAT NOT NULL,
    weight_version  VARCHAR(20) NOT NULL,
    schema_version  INT NOT NULL,
    fetched_at_ist  TIMESTAMPTZ NOT NULL,
    as_of_date      DATE NOT NULL,
    sanitized       BOOLEAN NOT NULL DEFAULT FALSE
) PARTITION BY RANGE (as_of_date);

-- Monthly partitions
CREATE TABLE nodes_2026_04 PARTITION OF nodes FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE nodes_2026_05 PARTITION OF nodes FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE INDEX idx_nodes_stock_date ON nodes (stock, as_of_date DESC);
CREATE INDEX idx_nodes_stock_cat_date ON nodes (stock, category, as_of_date DESC);
CREATE INDEX idx_nodes_fetched ON nodes (fetched_at_ist);
```

### 1.6 Edge Table

```sql
CREATE TABLE node_edges (
    id              BIGSERIAL PRIMARY KEY,
    from_id         VARCHAR(200) NOT NULL REFERENCES nodes(node_id),
    to_id           VARCHAR(200) NOT NULL REFERENCES nodes(node_id),
    relation        VARCHAR(20) NOT NULL,       -- supports, contradicts, derived_from, etc.
    strength        FLOAT NOT NULL,
    analysis_id     UUID NOT NULL,
    built_at        TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_edges_analysis ON node_edges (analysis_id);
CREATE INDEX idx_edges_from ON node_edges (from_id);
```

### 1.7 Analyses Table (Audit Log)

```sql
CREATE TABLE analyses (
    analysis_id     UUID PRIMARY KEY,
    stock           VARCHAR(20) NOT NULL,
    profile_hash    VARCHAR(64) NOT NULL,
    as_of_date      DATE NOT NULL,
    data_hash       VARCHAR(64) NOT NULL,       -- sha256(sorted node_ids)
    prompt_version  VARCHAR(20) NOT NULL,
    weight_version  VARCHAR(20) NOT NULL,
    model_id        VARCHAR(100) NOT NULL,
    input_nodes     JSONB NOT NULL,             -- list of node_ids used
    full_prompt     TEXT NOT NULL,
    raw_output      TEXT NOT NULL,
    final_output    JSONB NOT NULL,
    conflicts_resolved JSONB,
    stripped_claims  INT DEFAULT 0,
    low_fidelity    BOOLEAN DEFAULT FALSE,
    cache_key       VARCHAR(300),
    latency_ms      INT,
    tokens_in       INT,
    tokens_out      INT,
    created_at_ist  TIMESTAMPTZ NOT NULL
) PARTITION BY RANGE (created_at_ist);

CREATE INDEX idx_analyses_stock ON analyses (stock, created_at_ist DESC);
CREATE INDEX idx_analyses_cache ON analyses (cache_key);
```

### 1.8 Partitioning & Retention

- `nodes`: monthly partitions by `as_of_date`. Drop partitions >3 years old (except stocks in active backtests).
- `analyses`: monthly partitions. Hot partition in RAM; cold archived after 90 days, still queryable.
- `fundamental_cache`: no partitioning needed (UPSERT on unique constraint keeps it small).
- `technical_cache`: no partitioning. Delete rows where `as_of_date < NOW() - 90 days`.

---

## 2. Caching Rules (Redis)

Three distinct caches, different TTLs.

### 2.1 Raw-fetch cache

Prevents redundant HTTP calls during a single analysis run.

Keys: `raw:{source_id}:{symbol}:{date}`

| Source | TTL | Why |
|---|---|---|
| NSE OHLCV | 24h | Daily EOD refresh |
| BSE equityMetaInfo | 24h | Ratios change daily with price |
| BSE resultsSnapshot | 7 days | Only updates on quarterly results |
| Screener statements | 7 days | Same as above |
| NSE shareholding | 7 days | Quarterly SEBI disclosure |
| News RSS feeds | 4h | Time-sensitive |
| NSE announcements | 1h | High signal, frequent |
| Context (market regime) | 24h | Shared, one per day |

### 2.2 Node cache (per-stock snapshot)

Key: `nodes:{symbol}:{as_of_date}`
TTL: shortest upstream TTL for that stock (news 4h dominates).
Used by orchestrator on analysis cache miss to avoid re-normalization.

### 2.3 Analysis cache (the big lever)

Key: `analysis:v{prompt_v}:{weight_v}:{model_id}:{symbol}:{profile_bucket}:{data_hash}`
- `profile_bucket = (horizon, risk)`
- `data_hash = sha256(sorted(node_ids))`
- TTL: until node cache invalidates (or 24h, whichever first)
- Invalidated on: prompt version bump, weight version bump, model id bump, admin flush

Target hit rate: **>= 80%** steady state.

### 2.4 What does NOT get cached

- Authentication tokens
- Failure responses — fail-open retry safer than stale errors
- Partial analyses — cache only complete results
- Live prices with TTL < 15 minutes

---

## 3. Shared Analysis Cache — the Cost Lever

Naive cost at 100 analyses/day = 100 LLM calls. At 10,000/day = 10,000 calls.

With shared cache keyed on `(symbol, profile_bucket, data_hash)`:
- Popular stocks (RELIANCE, TCS, INFY, HDFC — top ~100 names) requested many times/day.
- Within a trading day, `data_hash` is stable until news/announcements arrive.
- 10,000 user requests collapse to ~200-500 actual LLM calls.

**This is the single biggest unit-economics win.** Rules:
- Never mix user-specific data into cached analysis (watchlist, portfolio).
- User-specific layers applied post-cache as a separate rendering step.

---

## 4. Rate Limiting (per-source)

Centralized client: `backend/fetchers/http_client.py`. ALL external HTTP goes through it.

### 4.1 Limits

| Source | Max req/min | Concurrent | Backoff |
|---|---|---|---|
| NSE API (NseIndiaApi) | 20 | 2 | exp 5s -> 60s, jitter 0.5x |
| BSE API (BseIndiaApi) | 30 | 3 | exp 2s -> 60s |
| Screener.in | 10 | 2 | exp 5s -> 120s, jitter 0.5x |
| yfinance | 30 | 4 | exp 2s -> 64s, jitter 0.5x |
| Moneycontrol / ET / BS / Livemint | 15/domain | 2/domain | exp 3s -> 90s |
| Google News RSS | 20 | 3 | exp 2s -> 60s |

### 4.2 Block handling

- HTTP 429 or 403: pause source for 15 minutes, degrade to next waterfall level.
- 3 consecutive 5xx: circuit-break for 5 minutes.
- Never retry within backoff window.

### 4.3 Respect

- `robots.txt` checked at fetcher startup; disallowed paths never fetched.
- Off-hours batch jobs where source allows (NSE/BSE documented windows).

### 4.4 Dead-letter queue

Parse failures (HTML changed, unexpected shape) go to Redis DLQ. Daily alert if DLQ > 10.

### 4.5 Daily canary

08:00 IST: fetch 5 stocks (RELIANCE, TCS, HDFCBANK, ITC, INFY), compare key fields
against known-good snapshot. Mismatch = alert. Catches silent scraper breakage early.

---

## 5. Request Flow — What Gets Fetched vs Cached

```
User requests analysis for RELIANCE
    |
    v
[1] Check analysis cache (Redis)
    | miss
    v
[2] Check fundamental_cache (Postgres) -- ratios, financials, shareholding
    | hit for ratios (fetched 2h ago, TTL 24h) -- NO HTTP call
    | miss for quarterly_pl (expired) -- fetch from Screener, store in cache
    v
[3] Check technical_cache (Postgres) -- pre-computed EOD indicators
    | hit (computed at 4 PM today) -- NO HTTP call, NO ta computation
    v
[4] Fetch fresh: news (RSS, always fresh), announcements (NSE, 1h cache)
    v
[5] Normalize all data -> Nodes
    v
[6] Build graph -> Anonymize -> LLM analysis -> Verify -> Format
    v
[7] Store in analysis cache + audit log -> Return
```

**Result:** For a popular stock with pre-computed data, only news + announcements
require live HTTP calls. Everything else comes from Postgres cache. This drops
analysis latency from ~8s (all fresh fetches) to ~2s (mostly cached).

---

## 6. Async / Concurrency Rules

- All data fetching is `async`. No blocking `requests` calls in agent code.
- Orchestrator fans out via `asyncio.gather` with per-task timeouts.
- DB writes batched: normalizer emits list, `bulk_upsert()` in one transaction.
- Celery handles scheduled jobs (EOD technicals, hourly news, weekly fundamentals).
- No agent spawns threads. Parallelism = more `asyncio`.
- Never `asyncio.run` from inside request code — propagate the loop.

---

## 7. LLM Cost Management

### 7.1 Token budget per analysis

Max: **12,000 input + 2,500 output tokens**.
If exceeded, drop oldest news nodes (keep latest N by recency x weight).
Never drop announcements or fundamentals.

### 7.2 Model selection

| Path | Model | Rationale |
|---|---|---|
| Dev / testing | Gemini 2.5 Flash (free tier) | 1500 req/day covers dev |
| Production | Gemini 2.5 Flash (paid, pinned) | Cheap, fast, sufficient for strict-prompt |
| Backtest at scale | Gemini 2.5 Flash | Determinism + cost |
| Deep reasoning (future) | Claude Sonnet API | Only when revenue supports it |
| Verifier Agent | Pure Python OR small Gemini prompt | Must be cheaper than main call |

Model choice is config, not code. Pinned in `config/versions.yaml`.

### 7.3 Prompt-size reduction

- Node `value_raw` is NOT included in LLM prompt — only `value` (display string).
- News bodies truncated to 400 tokens; max 20 news nodes per analysis.
- Financial series capped to last 8 quarters.
- Compact tabular format for indicator nodes, not verbose JSON.

---

## 8. Error Handling Rules

- Every external call: typed client with timeout + retry.
- Every caught exception logged with: `request_id`, `stock`, `source`, `stage`, `error_type`.
- Agents return `FetchFailure` for known failures. Raise only for bugs.
- User NEVER sees raw exceptions. They see: successful analysis, partial analysis with disclosure, insufficient-data refusal, or "temporarily unavailable".
- No `except Exception: pass`. Minimum: log and return `FetchFailure`.

---

## 9. Observability

### 9.1 Structured logging

JSON lines. Every record: `timestamp_ist`, `request_id`, `stock`, `stage`, `agent`, `level`, `duration_ms`.

### 9.2 Key metrics (Prometheus / Grafana)

- `stocxi_analysis_latency_ms` (histogram: cached yes/no)
- `stocxi_cache_hit_ratio` (gauge: by layer — redis/postgres/analysis)
- `stocxi_fetch_success_ratio` (gauge: by source)
- `stocxi_nodes_per_analysis` (histogram: by category)
- `stocxi_llm_tokens_in`, `stocxi_llm_tokens_out` (histograms)
- `stocxi_llm_cost_inr` (counter: by model_id)
- `stocxi_verifier_stripped_claims` (histogram)
- `stocxi_db_cache_hit_ratio` (gauge: fundamental_cache / technical_cache)

### 9.3 Performance targets (SLOs)

| Scenario | Target |
|---|---|
| Analysis cache hit (Redis) | p50 < 200ms, p95 < 500ms |
| Analysis with DB-cached fundamentals + technicals | p50 < 2s, p95 < 5s |
| Full fresh fetch (all sources) | p50 < 5s, p95 < 12s |
| EOD technicals for top 500 | complete within 30 min |
| Hourly news crawl | complete within 15 min |
| Daily canary | < 2 min |

---

## 10. Capacity Planning

| Tier | DAU | Analyses/day | LLM calls (post-cache) | LLM cost/day |
|---|---|---|---|---|
| Early MVP | 100 | 300 | ~120 (60% hit) | ~INR 60 |
| Growth | 1,000 | 5,000 | ~1,000 (80% hit) | ~INR 500 |
| Scale | 10,000 | 50,000 | ~7,500 (85% hit) | ~INR 3,750 |

With DB caching, HTTP calls drop ~70% even on cache misses (fundamentals + technicals served from Postgres).

---

## 11. Anti-Patterns (do NOT do)

- Do not parallelize scrapers without central rate limiting.
- Do not cache anything with "live price" beyond 15 minutes.
- Do not cache failure responses.
- Do not call LLM twice to "double check" — Verifier is the only second call.
- Do not build per-user analysis caches. Cache is shared by (symbol, profile_bucket, data_hash).
- Do not add a data source without adding to `config/sources.yaml` AND writing a canary.
- Do not fetch fundamentals on every request — check `fundamental_cache` first.
- Do not re-compute technicals during market hours — use pre-computed EOD values.

---

*Performance + cost + reliability discipline. Ignore at the project's peril.*
