# PLAN.md — Production System Build Plan

> Single source of truth for what needs to be built, in what order, and why.
> Every agent reads this before starting any work. Check off items as completed.

---

## Current State (2026-04-26)

**What exists:** MVP frontend on Vercel + FastAPI backend with services layer
(yfinance, screener, news, sentiment, technicals, announcements). Milestone 0-7
tests pass. Services work but are monolithic, tightly coupled, and use hardcoded
URLs.

**What's wrong:** Services bypass the agent architecture. Data fetching is
scattered across services with no waterfall, no source stamping, no confidence
scoring. No knowledge graph is wired. Analysis calls LLM directly without the
10-step protocol.

**What we decided (this session):** NSE + BSE libraries are 100% accurate for
price, OHLCV, ratios, shareholding. Screener.in is accurate for financial
statements (fixed standalone/consolidated bug). No paid APIs at MVP stage.

---

## Phase 0 — Config + Schemas (Foundation)

> Everything reads from config. Nothing is hardcoded. Schemas are the contract.

- [x] **0.1** Audit and finalize `config/sources.yaml` — remove Groww, ensure NSE
      is P1 for technicals, BSE is P1 for fundamentals, Screener P1 for financials
- [x] **0.2** Create `config/versions.yaml` — pin model ID, prompt version,
      weight version, schema version, architecture version
- [x] **0.3** Finalize `backend/schemas/node.py` — Node pydantic model matching
      ARCHITECTURE.md section 3 exactly
- [x] **0.4** Finalize `backend/schemas/messages.py` — FetchRequest, FetchResult,
      FetchFailure, RawPayload, AnalysisDraft, VerifiedAnalysis, AnalysisResult
- [x] **0.5** Validate all config files load cleanly via `backend/config.py`

**Exit criteria:** `python -c "from backend.schemas.node import Node; from
backend.schemas.messages import FetchResult"` works. All config files parse.

---

## Phase 1 — Data Fetcher Layer (Waterfall)

> One client per source. One waterfall runner. Every fetch returns FetchResult.

- [x] **1.1** `backend/fetchers/base.py` — FetchResult dataclass, FetchLevel
      protocol, WaterfallRunner (loop levels, log result, return first OK)
- [x] **1.2** `backend/fetchers/nse_client.py` — wraps `nse` library:
      equityQuote, quote, fetch_equity_historical_data, shareholding,
      announcements, boardMeetings, actions, annual_reports
- [x] **1.3** `backend/fetchers/bse_client.py` — wraps `bse` library:
      quote, equityMetaInfo, resultsSnapshot, quoteWeeklyHL,
      getScripTradingStats, resultCalendar, actions, getScripCode
- [x] **1.4** `backend/fetchers/screener_client.py` — slug resolver +
      consolidated/standalone recency picker + table parser (quarterly P&L,
      annual P&L, balance sheet, cash flow, top ratios)
- [x] **1.5** `backend/fetchers/yfinance_client.py` — .NS → .BO → alt ticker
      fallback for OHLCV only (not fundamentals)
- [x] **1.6** `backend/fetchers/news_client.py` — RSS feeds from approved
      domains in sources.yaml + Google News RSS fallback
- [x] **1.7** `backend/fetchers/http_client.py` — centralized rate-limited
      HTTP client (reads limits from sources.yaml, not hardcoded)
- [x] **1.8** Tests: one integration test per client against 3 stocks
      (RELIANCE, IRCTC, QUESTCAP)

**Exit criteria:** Each client fetches live data. WaterfallRunner returns
FetchResult with correct source_id and confidence.

---

## Phase 2 — Component Waterfalls (7 Pipelines)

> Each component defines its waterfall chain. Normalizer converts raw → Node.

| # | Component | Waterfall (L1 → L4) | Output Nodes |
|---|---|---|---|
| 2.1 | Price/Quote | NSE equityQuote → BSE quote → yfinance | Price, Change%, VWAP |
| 2.2 | OHLCV | NSE historical → yfinance .NS → .BO → alt | OHLCV DataFrame |
| 2.3 | Key Ratios | BSE equityMetaInfo → Screener top-ratios → yfinance | PE, PB, ROE, EPS, OPM, NPM |
| 2.4 | Financial Statements | Screener (recency-picked) → BSE resultsSnapshot | Revenue, PAT, OPM, BS, CF |
| 2.5 | Shareholding | NSE shareholding → Screener | Promoter%, Public%, FII%, DII% |
| 2.6 | Technical Indicators | ta library on OHLCV (Phase 2.2 output) | 17 indicator nodes |
| 2.7 | Announcements | NSE announcements + boardMeetings + BSE actions | Filing nodes |

- [x] **2.1** Build `backend/services/price_service.py`
- [x] **2.2** Build `backend/services/ohlcv_service.py`
- [x] **2.3** Build `backend/services/ratios_service.py`
- [x] **2.4** Build `backend/services/financials_service.py`
- [x] **2.5** Build `backend/services/shareholding_service.py`
- [x] **2.6** Rewrite `backend/services/technicals_service.py` (use OHLCV service)
- [x] **2.7** Rewrite `backend/services/announcements_service.py` (use NSE+BSE)
- [x] **2.8** Tests: waterfall test per component — verify fallback triggers

**Exit criteria:** Each service returns list[Node] with source_id, confidence,
and correct schema. Waterfall tested on large cap + small cap + BSE-only stock.

---

## Phase 3 — Knowledge Graph

> Nodes connect via typed edges. Graph is built per analysis run.

- [x] **3.1** Define edge types: supports, contradicts, derived_from,
      correlates, caused_by, part_of, same_domain
- [x] **3.2** Build `backend/graph/builder.py` — takes list[Node], emits edges
      based on rules (same stock + overlapping date + opposing signals =
      contradicts; same domain + same direction = supports)
- [x] **3.3** Build `backend/graph/scorer.py` — relevance_score =
      weight × confidence × recency_factor
- [x] **3.4** Build `backend/graph/store.py` — Postgres write, read by
      analysis_id, recursive CTE traversal
- [x] **3.5** Tests: build graph for RELIANCE, verify edge count and types

**Exit criteria:** Given 40+ nodes for a stock, graph builder produces typed
edges with scores. Stored in Postgres.

---

## Phase 4 — Agent Layer (Orchestration)

> Agents own domains. Orchestrator fans out. Verifier gates output.

- [x] **4.1** Rewrite `backend/agents/agent_technical.py` — calls OHLCV +
      technicals service, emits Node list
- [x] **4.2** Rewrite `backend/agents/agent_fundamental.py` — calls ratios +
      financials + shareholding services, emits Node list
- [x] **4.3** Rewrite `backend/agents/agent_news.py` — calls news service,
      sanitizes, emits Node list
- [x] **4.4** Rewrite `backend/agents/agent_announcement.py` — calls
      announcements service, classifies, emits Node list
- [x] **4.5** Rewrite `backend/agents/agent_context.py` — market regime,
      sector trend, peer snapshot, data completeness
- [x] **4.6** Rewrite `backend/agents/orchestrator.py` — parallel fan-out,
      collect nodes, build graph, anonymize, call analysis agent
- [x] **4.7** Rewrite `backend/agents/agent_analysis.py` — 10-step protocol,
      temp=0, pinned model, structured JSON output
- [x] **4.8** Rewrite `backend/agents/agent_verifier.py` — strip uncited
      claims, check node_id existence
- [x] **4.9** Rewrite `backend/agents/formatter.py` — de-anonymize, shape
      final AnalysisResult
- [x] **4.10** Tests: full pipeline test — 25 unit tests in `test_phase4_pipeline.py`
- [x] **4.11** Newsdata.io news pipeline: `newsdata_client.py`, `article_extractor.py`,
      rewritten `news_service.py`, updated `agent_news.py` (key_sentence + stock_impact
      per node), 3 new graph edge rules (news→Price caused_by, news↔technical
      supports/contradicts, news→fundamental correlates). 43 unit tests, all pass.

**Exit criteria:** `orchestrator.run_analysis("RELIANCE", profile, date)` returns
a verified AnalysisResult with node citations.

---

## Phase 5 — API + Frontend Wiring

> Connect the new agent pipeline to the existing FastAPI routes.

- [ ] **5.1** New router `backend/routers/v3_analysis.py` — calls orchestrator
- [ ] **5.2** Update frontend `lib/api.ts` — point to v3 endpoint
- [ ] **5.3** Cache layer — Redis analysis cache with key format from SCALE.md
- [ ] **5.4** Error responses — clean user messages for all failure modes
- [ ] **5.5** Admin view — `/admin/analysis/{id}` with reasoning trace

**Exit criteria:** End-to-end flow: user searches stock → frontend calls v3 →
orchestrator runs → cached analysis returned.

---

## Phase 6 — Audit + Determinism

> Every analysis is reproducible and logged.

- [ ] **6.1** Audit log writer — append-only row per analysis
- [ ] **6.2** Determinism checks — same input nodes → same output
- [ ] **6.3** Golden file tests — snapshot analyses for 5 canary stocks
- [ ] **6.4** Identity leakage test — anonymized prompts must not leak names

**Exit criteria:** `pytest backend/tests/golden/` passes. Audit rows written.

---

## Phase 7 — PDF Reports + Polish

- [ ] **7.1** Report agent — charts (price, indicators, financials, holdings)
- [ ] **7.2** PDF generation via WeasyPrint
- [ ] **7.3** Disclaimer injection
- [ ] **7.4** Frontend display polish

---

## Rules For Every Phase

1. No hardcoded URLs, timeouts, thresholds — all from `config/`
2. Every public function has a docstring
3. Every external call goes through `fetchers/http_client.py`
4. Every node has source_id and confidence
5. Every service returns pydantic models, not raw dicts
6. Tests written alongside code, not after
7. Update `NEW_PROGRESS.md` after completing each numbered item

---

*Maintained by: current agent. Review with Pratham before starting each phase.*
