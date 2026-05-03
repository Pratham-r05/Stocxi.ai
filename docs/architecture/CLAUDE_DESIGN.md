# CLAUDE_DESIGN.md — How Stocxi Works

> The definitive design reference for AI coding agents. Read this before touching any code.
> Cross-references: ARCHITECTURE.md (data contracts), AGENTS.md (agent protocol), SCALE.md (performance), PLAN.md (build phases).

---

## 1. The Idea

Stocxi is an AI-powered stock analysis platform for Indian retail investors who have **no finance background**. You search a stock name, and you get a transparent, evidence-backed analysis that tells you what the data suggests — not what to buy or sell.

**Core principle:** Never say "buy" or "sell." Describe what signals historically imply. Every claim must cite the data node it came from. This is SEBI-compliant (not registered advice).

The differentiator is the **knowledge graph** — a weighted, typed-edge graph that connects technical indicators, fundamental ratios, financial statements, news, and corporate announcements. The graph runs through an HFBP (Hebbian Forward-Backward Propagation) algorithm that learns which signals matter for which investment horizon, producing horizon-aware analysis.

---

## 2. System Architecture (End-to-End Flow)

```
User searches stock on frontend
        │
        ▼
Next.js frontend → FastAPI backend (/api/v2/analysis/{symbol})
        │
        ▼
Orchestrator Agent
        │
        ├── Cache check (Redis) ──── hit → return cached result
        │       miss
        │
        ▼
┌─────────────────── Parallel Fan-Out (asyncio.gather, 20s timeout each) ───────────────────┐
│                                                                                           │
│  Technical Agent ────── OHLCV data → ta library → 17 indicator nodes                      │
│  Fundamental Agent ─── BSE ratios + Screener financials + NSE shareholding → ~36 nodes   │
│  News Agent ────────── Newsdata.io L1 → Google News RSS L2 → sanitized news nodes       │
│  Announcement Agent ─── NSE + BSE filings → classified announcement nodes                │
│  Context Agent ──────── Market regime + sector trend + peer snapshot + data completeness   │
│                                                                                           │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
Normalizer → Source Reconciler → Sanitizer
        │
        ▼
Gemini Context Generation (batched, per-category)
  - Technical indicators get trend/momentum context
  - Fundamental ratios get vs-sector context
  - Financial statements get QoQ/YoY comparison context
  - News/announcements promote existing llm_summary → context
        │
        ▼
Knowledge Graph Builder (HFBP-typed edges)
        │
        ▼
HFBP Forward Propagation (horizon-aware weight activation)
        │
        ▼
Anonymization (STOCK_A, SECTOR_X, PEER_1/2/3, EXEC_A)
        │
        ▼
Analysis Agent (10-step protocol, temp=0, Gemini 2.5 Flash)
        │
        ▼
Verifier Agent (strip uncited claims, enforce fidelity)
        │
        ▼
Output Formatter (de-anonymize, shape AnalysisResult JSON)
        │
        ▼
HFBP Backward Propagation (learn edge weights from this analysis)
        │
        ▼
Audit Log Write + Redis Cache Write → Return to Frontend
        │
        ▼
3D Knowledge Graph HTML served at /api/v2/analysis/{symbol}/graph
```

---

## 3. Components and Their Responsibilities

### 3.1 Frontend (Next.js on Vercel)

```
frontend/
├── app/           ← Next.js App Router pages
├── components/    ← React components
├── lib/           ← API client, utilities
├── data/          ← Static data (stock lists, etc.)
└── src/           ← Additional source files
```

- Stock search with autocomplete
- Displays analysis results: signals for, signals against, data disclosure, disclaimer
- 3D knowledge graph visualization (when user visits graph endpoint)
- Calls `NEXT_PUBLIC_API_URL` for all backend requests

### 3.2 FastAPI Backend

```
backend/
├── main.py              ← FastAPI app entry, CORS, lifespan
├── config.py             ← YamlConfig: loads all 9 YAML config files + .env
│
├── routers/              ← API route handlers
│   ├── analysis.py       ← v1 analysis endpoints (legacy)
│   ├── v2_analysis.py    ← v2 analysis + graph endpoints (current)
│   ├── search.py          ← symbol autocomplete
│   └── stock.py           ← stock overview, financials, news, etc.
│
├── agents/               ← Specialist agents (see AGENTS.md)
│   ├── orchestrator.py        ← Fan-out, collect, build graph, call analysis
│   ├── agent_technical.py     ← 17 technical indicators from OHLCV
│   ├── agent_fundamental.py   ← Ratios + financials + shareholding (~36 nodes)
│   ├── agent_news.py          ← Newsdata.io + RSS → sanitized news nodes
│   ├── agent_announcement.py  ← NSE/BSE filings → classified nodes
│   ├── agent_context.py       ← 4 context nodes (market, sector, peers, completeness)
│   ├── agent_analysis.py      ← 10-step LLM protocol (Gemini, temp=0)
│   ├── agent_verifier.py      ← Strip uncited claims, fidelity gate
│   ├── agent_report.py        ← PDF report generation (future)
│   └── formatter.py            ← De-anonymize, shape final JSON
│
├── services/              ← Business logic, one per data domain
│   ├── ohlcv_service.py       ← OHLCV waterfall (NSE → yfinance)
│   ├── price_service.py       ← Price/quote waterfall
│   ├── ratios_service.py      ← Key ratios (BSE → Screener)
│   ├── financials_service.py  ← Financial statements (Screener → BSE)
│   ├── shareholding_service.py← Shareholding (NSE → Screener)
│   ├── technicals_service.py  ← 17 indicators via ta library
│   ├── announcements_service.py← NSE+BSE corporate filings
│   ├── news_service.py        ← Newsdata.io L1 → Google News RSS L2
│   ├── context_generator.py   ← Gemini-batched context per node category
│   ├── ai_service.py          ← LLM client (Gemini via OpenAI SDK)
│   ├── screener_service.py    ← Screener.in HTML scraper with recency-pick
│   ├── search_service.py      ← Symbol search
│   ├── sentiment_service.py   ← Social sentiment (Reddit/X)
│   ├── yfinance_service.py   ← yfinance wrapper
│   └── report_service.py      ← Report generation
│
├── fetchers/              ← One client per data source, returns raw payload
│   ├── base.py                 ← FetchResult, WaterfallRunner (L1→L2→L3→L4)
│   ├── nse_client.py           ← NSE India API (NseIndiaApi library)
│   ├── bse_client.py           ← BSE India API (BseIndiaApi library)
│   ├── screener_client.py      ← Screener.in scraper
│   ├── yfinance_client.py      ← yfinance .NS/.BO/alt ticker fallback
│   ├── news_client.py          ← RSS feed fetcher (approved domains)
│   ├── newsdata_client.py      ← Newsdata.io REST API
│   ├── http_client.py          ← Rate-limited, retry-aware HTTP client
│   └── groww_client.py         ← Groww (deprecated, not used)
│
├── graph/                 ← Knowledge graph system
│   ├── builder.py              ← HFBP-typed edge creation rules
│   ├── hfbp.py                 ← Hebbian Forward-Backward Propagation algorithm
│   ├── stocxi_knowledge_graph.py  ← Full KG lifecycle (build→propagate→serialize)
│   ├── knowledge_graph.py      ← 3D HTML visualization (Three.js + 3D-Force-Graph)
│   ├── scorer.py               ← Node relevance scoring (weight×confidence×recency)
│   └── store.py                ← Postgres read/write for nodes and edges
│
├── analysis/              ← LLM analysis pipeline
│   └── prompt_template.jinja  ← Jinja2 template for 10-step analysis protocol
│
├── schemas/               ← Pydantic models (the contract)
│   ├── node.py                 ← Node model (see ARCHITECTURE Section 4)
│   └── messages.py             ← FetchRequest, FetchResult, RawPayload, AnalysisDraft, etc.
│
├── cache/                 ← Redis caching layer
├── audit/                 ← Immutable audit log per analysis
├── db/                    ← Database migrations (Supabase/Postgres)
├── backtest/              ← Point-in-time replay
├── calibration/           ← Weight refit + confidence calibration
├── util/                  ← Sanitizer, holiday calendar, IST helpers
└── tests/                 ← Unit + integration tests
```

### 3.3 Configuration Files

```
config/
├── versions.yaml         ← Pinned model ID, prompt version, weight version, schema version
├── sources.yaml           ← Approved data source URLs, priorities, rate limits
├── weights.yaml           ← Signal weight table (node type → weight)
├── profiles.yaml          ← User profile → category-weight map (horizon × risk)
├── bse_codes.yaml         ← NSE symbol → BSE scrip code mapping
├── alt_tickers.yaml       ← yfinance alternative tickers (ZOMATO→ETERNAL, etc.)
├── screener_slugs.yaml    ← Static NSE→Screener slug overrides
└── calibration.yaml      ← Backtest calibration parameters
```

### 3.4 Database (PostgreSQL / Supabase)

6 tables, each with a clear purpose:

| Table | Purpose | Refresh |
|---|---|---|
| `stocks` | NSE symbols, BSE codes, company names, sector, market cap tier | Weekly |
| `fundamental_cache` | PE, PB, ROE, financial statements, shareholding (JSONB) | 24h (ratios), 7-14d (statements) |
| `technical_cache` | Pre-computed 17 indicators per stock per day | Daily EOD |
| `nodes` | Analysis nodes (partitioned monthly by as_of_date) | Per analysis |
| `node_edges` | Knowledge graph edges per analysis_id | Per analysis |
| `analyses` | Full audit log (partitioned monthly) | Append-only |

---

## 4. The Knowledge Graph (The Core Differentiator)

### 4.1 What It Is

Every analysis builds a typed-edge graph connecting all data nodes. This is not just data collection — it's **relational reasoning**:

- **Technical indicator RSI_14 at 35** → contradicts or confirms **Revenue declining in last 2 quarters**
- **Promoter pledging increase** → triggers (causes) signal regardless of what RSI says
- **News about SEBI action** → amplifies fundamental deterioration, dampens bullish technical signals

### 4.2 HFBP Edge Types (8 types)

| Type | Meaning | Color (3D graph) | Example |
|---|---|---|---|
| `CONFIRMS` | Same direction, reinforces | Green `#00FF88` | RSI bullish confirms MACD bullish |
| `AMPLIFIES` | Intensifies a signal | Cyan-green `#00FFCC` | Strong volume amplifies breakout |
| `CONTRADICTS` | Opposite direction, conflict | Red `#FF3355` | Declining revenue contradicts rising RSI |
| `DAMPENS` | Weakens a signal | Orange `#FF8844` | High VIX dampens breakout signals |
| `CAUSES` | Direct causal link | Blue `#4499FF` | Dividend declaration causes price jump |
| `TRIGGERS` | Indirect trigger | Purple `#AA55FF` | SEBI action triggers fundamental review |
| `CONTEXTUALIZES` | Provides background context | Steel blue `#6688AA` | Sector trend contextualizes stock movement |
| `CORRELATES` | Statistical co-movement | Dark steel `#556677` | Sector PE correlates with stock PE |

### 4.3 HFBP Algorithm

1. **Build** — Create nodes and typed edges with prior weights
2. **Forward Propagate** — Seed nodes get activation 1.0. Propagate through edges. Horizon lens: short-term boosts news/momentum, long-term boosts fundamentals.
3. **Serialize for LLM** — Top activated nodes (W≥0.3) with context strings and edge relationships are injected into the Gemini analysis prompt
4. **Backward Propagate** — After analysis, update edge weights based on Gemini's assessment of relevance vs computed weight. Save per-ticker JSON for future analyses.

### 4.4 4-Tier Node Hierarchy (3D Graph)

```
HEAD (stock name, white, r=12)
  └── GROUP nodes (category: Technical/Fundamental/News/etc., blue #3B82F6, r=8)
        └── CHILD nodes (individual data points, dark grey #374151, r=5.5)
              └── Signal border: green=positive, red=negative, grey=neutral
VERDICT nodes (analysis verdict, purple #8B5CF6 hex, r=10)
```

---

## 5. The Analysis Protocol (10 Steps)

Steps 1-9 are strict (zero deviation). Step 10 is free reasoning (20%).

| Step | What | deviation allowed? |
|---|---|---|
| 1. VALIDATE | Load nodes, drop bad schemas, verify minimums | No |
| 2. ANONYMIZE | Replace real names with STOCK_A, SECTOR_X, etc. | No |
| 3. TECHNICAL | Read 17 indicator nodes → verdict with citations | No |
| 4. FUNDAMENTAL | Read ratio + financial nodes → verdict with citations | No |
| 5. NEWS | Read sanitized news nodes → verdict with citations | No |
| 6. ANNOUNCEMENT | Read filing nodes → verdict with citations | No |
| 7. WEIGHTS | Apply profile weights (horizon × risk → category mix) | No |
| 8. AGREEMENTS | List cross-category agreements with node_id pairs | No |
| 9. CONTRADICTIONS | List conflicts, resolve via hierarchy | No |
| 10. FREE REASONING | Non-obvious cross-category connections, divergences | Yes (20%) |

**Contradiction Hierarchy (highest wins):**
1. Regulatory/SEBI/legal
2. Promoter pledging increase or promoter selling
3. Fundamental deterioration
4. Leadership change/audit qualifier/credit downgrade
5. Technical divergence
6. News sentiment (lowest standalone weight)

---

## 6. Data Pipeline: Waterfall Pattern

Every data fetch follows a **waterfall** — try L1 first, fall to L2 on failure, etc.

| Component | L1 (exchange) | L2 (verified scraper) | L3 (aggregator) | L4 (fallback) |
|---|---|---|---|---|
| Price/Quote | NSE `equityQuote` | BSE `quote` | yfinance | — |
| OHLCV | NSE historical | — | yfinance `.NS→.BO→alt` | — |
| Key Ratios | BSE `equityMetaInfo` | Screener top-ratios | yfinance | — |
| Financials | Screener (recency-picked) | BSE `resultsSnapshot` | — | — |
| Shareholding | NSE `shareholding` | Screener | — | — |
| Technicals | ta library (computed) | — | — | — |
| Announcements | NSE + BSE | — | — | — |
| News | Newsdata.io | Google News RSS | — | — |

Each result is stamped with `source_id` and `confidence` (1.00 for L1, 0.85 for L2, 0.70 for L3, 0.50 for L4).

---

## 7. The Node System

Every piece of data flowing through the system is a **Node** — a pydantic model with:

- `node_id`: deterministic key (`{stock}|{category}|{name}|{as_of_date}`)
- `value`: human-readable display string (max 150 chars)
- `value_raw`: machine-readable dict (full data for audit)
- `signal`: positive / negative / neutral
- `confidence`: 1.0 (L1) → 0.50 (L4)
- `source`: where it came from
- `context`: Gemini-generated, horizon-aware explanation
- `weight`: from config/weights.yaml
- `sanitized`: must be True before entering any LLM prompt

**Key rule:** No node without `source_id`. No node without `confidence`. No node entering an LLM prompt without `sanitized=True`.

---

## 8. Anti-Hallucination Pipeline

Three layers of defense:

1. **Anonymization** — The LLM never sees the real stock name during reasoning. Only tokens like STOCK_A, SECTOR_X, PEER_1/2/3. De-anonymization happens after, mechanically, with no LLM.

2. **Citation Firewall** — Every claim in the analysis must reference a `node_id`. The Verifier Agent strips any claim that references a node_id not in the supplied node list. If >2 claims are stripped, the analysis is flagged `low_fidelity`.

3. **Sanitizer** — All news HTML is stripped before entering the prompt. No imperative sentences. Body truncated to 400 tokens. Only approved domains in `config/sources.yaml`.

---

## 9. Caching Strategy

Three cache layers, different TTLs:

| Layer | Key Pattern | TTL | Purpose |
|---|---|---|---|
| Raw-fetch (Redis) | `raw:{source_id}:{symbol}:{date}` | 1h–7d per source | Avoid redundant HTTP calls |
| Node (Redis) | `nodes:{symbol}:{as_of_date}` | Shortest upstream TTL | Avoid re-normalization |
| Analysis (Redis) | `analysis:v{prompt}:{weight}:{model}:{symbol}:{profile}:{data_hash}` | 24h | The big lever — collapses repeated LLM calls |

**The unit-economics win:** Popular stocks (RELIANCE, TCS, HDFCBANK) get many requests/day. With shared cache keyed on `(symbol, profile_bucket, data_hash)`, 10,000 requests collapse to ~200-500 actual LLM calls.

---

## 10. Determinism Rules

These are **non-negotiable**:

- `temperature = 0` for all production LLM calls
- Pinned model ID in `config/versions.yaml`
- Pinned prompt version
- Pinned weight version
- Same input nodes + same config = identical output
- Random tie-breakers use `hash(node_ids)`, not RNG

---

## 11. User Profiles and Weight System

Analysis depth depends on investment horizon and risk tolerance:

| Category | Short-term (intraday–weeks) | Long-term (months–years) |
|---|---|---|
| Technical | 0.50 | 0.20 |
| News | 0.30 | 0.10 |
| Fundamental | 0.15 | 0.50 |
| Announcement | 0.05 | 0.20 |

Risk adjustments:
- **Conservative:** negative signals ×1.3, volatility ×1.2
- **Modererate:** unchanged
- **Aggressive:** positive momentum ×1.2, volatility ×0.9

---

## 12. What Gets Built Next (Phase Status)

| Phase | Status | What |
|---|---|---|
| 0 — Config + Schemas | ✅ Complete | YAML configs, pydantic models, DB schema |
| 1 — Data Fetcher Layer | ✅ Complete | Waterfall clients for all 6 sources |
| 2 — Component Waterfalls | ✅ Complete | 7 services producing Node lists |
| 3 — Knowledge Graph | ✅ Complete | HFBP edges, scorer, store |
| 4 — Agent Layer | ✅ Complete | 5 specialist agents + orchestrator + analysis + verifier + formatter |
| 5 — API + Frontend Wiring | 🔲 Next | v3 router, Redis cache, error responses |
| 6 — Audit + Determinism | 🔲 Pending | Audit log, golden tests, identity leakage test |
| 7 — PDF + Polish | 🔲 Pending | Reports, charts, disclaimer injection |

---

## 13. Key Files to Know

| If you're working on... | Start here |
|---|---|
| Adding a new data source | `backend/fetchers/` + `config/sources.yaml` |
| Adding a new agent | `backend/agents/` + `AGENTS.md` |
| Changing how analysis works | `backend/agents/agent_analysis.py` + `backend/analysis/prompt_template.jinja` |
| Changing node schema | `backend/schemas/node.py` + `ARCHITECTURE.md Section 4` |
| Changing weights or profiles | `config/weights.yaml` + `config/profiles.yaml` |
| Changing KG visualization | `backend/graph/knowledge_graph.py` |
| Changing HFBP algorithm | `backend/graph/hfbp.py` + `backend/graph/stocxi_knowledge_graph.py` |
| Changing edge rules | `backend/graph/builder.py` |
| Adding a new API endpoint | `backend/routers/` + `backend/main.py` |
| Changing LLM model | `config/versions.yaml` |
| Changing caching | `backend/cache/` + `SCALE.md` |
| Frontend changes | `frontend/app/` + `frontend/components/` |
| Running the server | `conda run -n stocxi uvicorn backend.main:app --reload --port 8000` |

---

## 14. Rules That Must Never Be Broken

1. **No unapproved sources.** Every fetch goes through sources in `config/sources.yaml`. Violation raises `UnapprovedSourceError`.
2. **No real stock names in LLM reasoning.** Anonymization is mandatory.
3. **No claims without node_id citations.** Verifier strips uncited claims.
4. **No temperature > 0 in production.** Determinism is law.
5. **No raw news HTML in prompts.** Sanitizer must run.
6. **No "BUY" / "SELL" / "RECOMMEND" in output.** SEBI compliance.
7. **No hardcoded values.** Everything from config or .env.
8. **No skipping the audit log.** Every analysis gets logged.
9. **Python env is `stocxi` conda.** Never use `.venv312` or system Python.
10. **Every node has source_id and confidence.** Never anonymous data.

---

*Comprehensive design reference. Read ARCHITECTURE.md for exact data contracts, AGENTS.md for agent protocol details, SCALE.md for performance/caching rules, PLAN.md for build phases.*