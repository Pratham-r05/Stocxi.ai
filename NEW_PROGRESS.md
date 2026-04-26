# NEW_PROGRESS.md — Build Progress Tracker

> Tracks progress of the production rebuild (PLAN.md).
> Append only. Each entry: date, phase, what was done, files touched.



## Status

| Field | Value |
|---|---|
| Current Phase | Phase 4 COMPLETE + Newsdata.io pipeline added. Phase 5 is next. |
| Started | 2026-04-26 |
| Last Updated | 2026-04-26 |


---
Progress So Far

  Phase 4 — Agent Layer

  Wave 1 COMPLETE (5 specialist agents rewritten):

  ┌───────────────────────┬─────────┬───────────────────────────────────────────────────────────────────────────────────────────┐
  │         File          │ Status  │                                        Key change                                         │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ agent_technical.py    │ ✅ Done │ TechnicalAgent class, technical_agent singleton, 20s timeout, FetchFailure returns        │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ agent_fundamental.py  │ ✅ Done │ FundamentalAgent fans out to 3 services in parallel, handles partial failures             │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ agent_news.py         │ ✅ Done │ NewsAgent converts raw news dicts → Nodes, sanitizes, classifies signal                   │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ agent_announcement.py │ ✅ Done │ AnnouncementAgent thin wrapper over announcements_service                                 │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ agent_context.py      │ ✅ Done │ ContextAgent emits 4 nodes: Market_Regime, Sector_Trend, Peer_Snapshot, Data_Completeness │
  └───────────────────────┴─────────┴───────────────────────────────────────────────────────────────────────────────────────────┘

  Wave 2 NOT STARTED (4.6–4.9):
  - orchestrator.py — needs update
  - agent_analysis.py — needs rewrite
  - agent_verifier.py — needs rewrite
  - formatter.py — needs rewrite

  4.10 Tests — not started

  ---
  Known Issues to Fix Before Wave 2

  1. No run() aliases — orchestrator calls module.run(request) but Wave 1 agents only expose agent.fetch(request). Need to add to each
  agent:
  async def run(request: FetchRequest) -> list[Node] | FetchFailure:
      return await technical_agent.fetch(request)
  2. agent_news.py missing singleton — no news_agent = NewsAgent() line at end of file
  3. Orchestrator _run_agent_safe — doesn't handle FetchFailure returns (calls len(nodes) which breaks on a pydantic model)

  ---
  Exact Next Steps (resume here)

  1. Edit agent_technical.py   → add run() alias at bottom
  2. Edit agent_fundamental.py → add run() alias at bottom
  3. Edit agent_news.py        → add news_agent = NewsAgent() + add run() alias
  4. Edit agent_announcement.py → add run() alias at bottom
  5. Edit agent_context.py     → add run() alias at bottom
  6. Rewrite orchestrator.py   → fix _run_agent_safe to isinstance-check FetchFailure
  7. Rewrite agent_analysis.py → 10-step LLM protocol, temp=0, AnalysisDraft output
  8. Rewrite agent_verifier.py → node_id existence check, strip uncited claims
  9. Rewrite formatter.py      → de-anonymize, shape AnalysisResult
  10. Write tests               → backend/tests/unit/test_phase4_pipeline.py



## Data Source Decisions (Finalized 2026-04-26)

Verified via live testing across 10 stocks + 3 edge-case stocks (UNIECOM,
TMPV, QUESTCAP). Every coverage claim below is empirically tested.

| Component | Primary (L1) | Fallback (L2+) | Coverage |
|---|---|---|---|
| Price/Quote | NSE `equityQuote` | BSE `quote` → yfinance | 100% |
| OHLCV History | NSE `fetch_equity_historical_data` | yfinance .NS → .BO → alt | 100% |
| PE/PB/ROE/EPS/OPM/NPM | BSE `equityMetaInfo` | Screener top-ratios | 96% |
| Financial Statements | Screener.in (recency-picked) | BSE `resultsSnapshot` (3 periods) | 90% |
| Shareholding | NSE `shareholding` | Screener | 80% |
| Technical Indicators | ta library on OHLCV | — (computed, not fetched) | 100% |
| Announcements | NSE `boardMeetings` + `announcements` | BSE `actions` | 100% |
| 52W High/Low | BSE `quoteWeeklyHL` | NSE `quote.weekHighLow` | 100% |
| Market Cap | BSE `getScripTradingStats` | NSE `quote.tradeInfo` | 100% |
| Dividends/Splits | NSE `actions` + BSE `actions` | — | 100% |
| Result Calendar | BSE `resultCalendar` | — | 100% |
| News | Moneycontrol/ET/BS/Livemint RSS | Google News RSS | varies |

### Key Bugs Fixed During Testing

1. **Screener standalone vs consolidated** — Code blindly fetched consolidated
   first. QUESTCAP's consolidated had Dec 2020 data; standalone had Mar 2025.
   Fix: fetch both, compare most recent period header, use fresher page.
   File: `backend/services/screener_service.py`

2. **NSE price key mismatch** — `equityQuote()` returns flat `{close}` not
   nested `{priceInfo.lastPrice}`. Fix: use `q.get("close")`.

3. **ta library duplicate columns** — NSE OHLCV has `ch52WeekHighPrice` which
   substring-matched "high", creating duplicate columns. Fix: exact column
   name dict, no substring matching.

4. **Screener slug returning "consolidated"** — URL parser took last segment
   which was structural. Fix: skip `{company, consolidated, standalone}`,
   take first remaining segment.

---

## Session Log

### 2026-04-26 — Architecture Reset + Plan Creation

**What was done:**
- Exhaustive live testing of NSE library (20 methods), BSE library (15 methods)
- Mapped every data point available from NSE + BSE with exact method names
- Tested Screener.in accuracy: verified QUESTCAP TTM matches (Sales=53Cr,
  Net Profit=40Cr, EPS=40.09)
- Fixed screener_service.py consolidated/standalone selection
- Evaluated FinEdge API (XBRL-sourced, ₹2k/month) — deferred to post-MVP
- Evaluated LiveMint/Refinitiv data (Tata Steel JSON) — broken shareholding,
  unclear standalone/consolidated, not Indian-taxonomy — rejected
- Created PLAN.md with 7-phase production build plan
- Created this file (NEW_PROGRESS.md)
- Rewrote ARCHITECTURE.md, AGENTS.md, CLAUDE.md, SCALE.md

**Files created/modified:**
- `PLAN.md` (new)
- `NEW_PROGRESS.md` (new)
- `ARCHITECTURE.md` (rewritten)
- `AGENTS.md` (rewritten)
- `CLAUDE.md` (updated)
- `backend/services/screener_service.py` (standalone/consolidated fix)
- `backend/tests/research/test_target_stocks.py` (same fix)

**Next:** Begin Phase 0 — finalize config files and pydantic schemas.

---

### 2026-04-26 — Documentation Finalization + DB Storage Strategy

**What was done:**
- Rewrote AGENTS.md with verified NSE/BSE library methods, exact waterfall chains per agent,
  pipeline execution diagram, complete communication protocol with pydantic models
- Updated CLAUDE.md: added data source hierarchy, corrected folder structure (config files,
  services vs fetchers), updated references to NEW_PROGRESS.md instead of PROGRESS.md
- Added comprehensive node data format specification to ARCHITECTURE.md Section 4.1:
  exact `value` and `value_raw` formats for all node types (17 technical indicators,
  11 fundamental ratios, 7 financial statement types, 5 shareholding nodes, news,
  announcements, context nodes) with data format rules (numbers as native types,
  percentages as plain numbers, currency in crores, dates as ISO, arrays newest-first)
- Rewrote SCALE.md with DB storage strategy: `stocks` master table, `fundamental_cache`
  (7-day TTL for statements, 24h for ratios), `technical_cache` (pre-computed EOD),
  request flow showing what gets fetched vs cached from Postgres, reducing HTTP calls
  by ~70% on analysis cache misses
- Deleted obsolete files: BUGS.md (all fixed), DATA_LAYER.md (superseded), PROGRESS.md
  (replaced by NEW_PROGRESS.md)

**Files modified:**
- `AGENTS.md` (rewritten)
- `CLAUDE.md` (rewritten)
- `ARCHITECTURE.md` (added Section 4.1 node data formats + Section 4.2 format rules)
- `SCALE.md` (rewritten with DB caching strategy + SQL schemas)

**Files deleted:**
- `BUGS.md` (obsolete — all 7 bugs were fixed 2026-04-24)
- `DATA_LAYER.md` (superseded by ARCHITECTURE.md + PLAN.md)
- `PROGRESS.md` (replaced by NEW_PROGRESS.md)

**Next:** Begin Phase 0 — finalize config files and pydantic schemas.

---

### 2026-04-26 — Phase 0 Complete: Config + Schemas + DB Schema

**What was done:**
- Audited and rewrote `config/sources.yaml` (0.1):
  - Removed duplicate `screener_in` entry (had two conflicting priority fields inside one YAML mapping)
  - Removed stale `bse_api`, `nse_api` raw HTTP entries (covered by `bse_library`/`nse_library`)
  - Removed `tickertape` (not in plan)
  - Corrected `fundamental_field_priority` to use library source IDs
  - Corrected announcement sources to `type: library` (they use NSE/BSE Python libs, not raw HTTP)
  - Added file-header comment summarising waterfall chain per domain
- Added full YAML config loader to `backend/config.py` (0.5):
  - New `YamlConfig` class with lazy-loaded properties for all 6 config files
  - `validate_all()` method — called at startup, fails fast on missing keys or corrupt YAML
  - Convenience helpers: `active_model_id()`, `prompt_version()`, `weight_version()`, `category_mix(horizon)`, `risk_adjustments(risk)`
  - Module-level singleton `yaml_cfg` — import as `from backend.config import yaml_cfg`
  - All 6 files validated live: sources, versions, weights, profiles, bse_codes, alt_tickers
- Created DB migration (DB layer):
  - New directory `backend/db/` + `backend/db/migrations/`
  - `001_initial_schema.sql` — all 6 tables: `stocks`, `fundamental_cache`, `technical_cache`, `nodes` (partitioned), `node_edges`, `analyses` (partitioned)
  - Includes indexes, constraints, `updated_at` trigger, initial monthly partitions (Apr–Jun 2026), partition maintenance template
- Schemas already correct (0.2, 0.3, 0.4 — pre-existing):
  - `config/versions.yaml`: all fields present, model pinned
  - `backend/schemas/node.py`: Node with auto node_id builder, all enums
  - `backend/schemas/messages.py`: all 9 types present

**Files modified/created:**
- `config/sources.yaml` (rewritten — removed duplicates, stale entries)
- `backend/config.py` (rewritten — added YamlConfig + yaml_cfg singleton)
- `backend/db/__init__.py` (new)
- `backend/db/migrations/001_initial_schema.sql` (new — 6 tables, full Supabase schema)
- `PLAN.md` (Phase 0 all 5 items ticked ✓)

**Validation:** `yaml_cfg.validate_all()` PASSES — all 6 YAML files load, all critical keys present.

**Next:** Phase 1 — Data Fetcher Layer. Start with `backend/fetchers/base.py` (FetchResult, WaterfallRunner), then nse_client, bse_client, screener_client.

---

### 2026-04-26 — Phase 1 Complete: Data Fetcher Layer

**What was done:**
- Built all 6 fetcher modules in `backend/fetchers/`:
  - `base.py` — `FetchResult` dataclass (`.success()` / `.failure()` factories), `WaterfallFailure` exception, `WaterfallRunner.run()`, module-level `waterfall` singleton
  - `nse_client.py` — async wrapper for NSE library: `fetch_quote`, `fetch_ohlcv`, `fetch_shareholding`, `fetch_announcements`, `fetch_board_meetings`, `fetch_actions`, `fetch_annual_reports`. Lazy singleton, thread-pool executor for sync calls.
  - `bse_client.py` — async wrapper for BSE library: `resolve_scrip_code` (live API + bse_codes.yaml fallback + per-process cache), `fetch_quote`, `fetch_meta_info`, `fetch_results_snapshot`, `fetch_weekly_hl`, `fetch_trading_stats`, `fetch_result_calendar`, `fetch_actions`. Lazy singleton, thread-pool executor.
  - `screener_client.py` — thin wrapper around `screener_service.get_financials()`, promotes empty-result to `ValueError` so WaterfallRunner can fall through. Source ID `screener_in`, confidence 0.85.
  - `yfinance_client.py` — OHLCV fallback only: `.NS → .BO → alt_tickers.yaml` waterfall, `fetch_ohlcv` + `fetch_quote`. NaN-safe float coercion. Multi-level column flattening for yfinance MultiIndex.
  - `news_client.py` — RSS fetcher from all approved domains in sources.yaml (P1→P2→P3 Google News fallback). Uses `http_client.py` for rate-limiting. HTML stripping, date filtering, symbol/company-name matching, deduplication.
- Added `feedparser==6.0.12`, `nse==2.1.3`, `bse==3.2.0` to `backend/requirements.txt`
- Installed all three in `.venv312` (not globally)
- Built integration test suite: `backend/tests/integration/test_fetcher_clients.py`
  - `TestWaterfallRunner` (5 unit tests) — all 5 PASS (no network required)
  - `TestNseClient`, `TestBseClient`, `TestScreenerClient`, `TestYfinanceClient`, `TestNewsClient` — 18 integration tests (run with `STOCXI_INTEGRATION=1`)

**Files created/modified:**
- `backend/fetchers/base.py` (new)
- `backend/fetchers/nse_client.py` (new)
- `backend/fetchers/bse_client.py` (new)
- `backend/fetchers/screener_client.py` (new)
- `backend/fetchers/yfinance_client.py` (new)
- `backend/fetchers/news_client.py` (new)
- `backend/tests/integration/__init__.py` (new)
- `backend/tests/integration/test_fetcher_clients.py` (new)
- `backend/requirements.txt` (added nse, bse, feedparser)
- `NEW_PROGRESS.md` (this update)

**Validation:** `python -m pytest backend/tests/integration/test_fetcher_clients.py::TestWaterfallRunner -v --asyncio-mode=auto` → 5/5 PASS

**Next:** Phase 2 — Component Waterfalls (7 pipelines). Start with `backend/components/price_component.py` using `WaterfallRunner` over nse_client → bse_client → yfinance_client.

---

### 2026-04-26 — Phase 2 Complete: Component Waterfalls (7 Services)

**What was done:**
- Built all 7 component services in `backend/services/`:
  - `ohlcv_service.py` — OHLCV waterfall (NSE library → yfinance). Returns `pd.DataFrame [Open,High,Low,Close,Volume]` with DatetimeIndex. Used by technicals.
  - `price_service.py` — Price waterfall (NSE equityQuote → BSE quote → yfinance). Emits Price, Change_Pct, VWAP nodes.
  - `ratios_service.py` — Ratios waterfall (BSE equityMetaInfo → Screener top-ratios). Emits PE_Ratio, PB_Ratio, ROE, ROCE, EPS, OPM, NPM, Dividend_Yield nodes. Signals for PE vs sector, ROE/ROCE >15% vs <8%, OPM/NPM thresholds.
  - `financials_service.py` — Financials waterfall (Screener recency-picked → BSE resultsSnapshot). Emits Revenue_Quarterly, Net_Profit_Quarterly, Revenue_Annual, Net_Profit_Annual, Debt_To_Equity, Operating_Cash_Flow. Growth signals: >15% → positive, negative → negative.
  - `shareholding_service.py` — Shareholding waterfall (NSE → Screener). Emits Promoter_Holding, FII_Holding, DII_Holding, Public_Retail_Holding. QoQ change signals.
  - `technicals_service.py` — Full rewrite. Now delegates OHLCV to `ohlcv_service`. Emits 17 indicator nodes (RSI_14, MACD, ADX_14, ATR_14, Bollinger_Bands, EMA, SMA, Ichimoku, Parabolic_SAR, Stochastic, Williams_R, ROC, OBV, VWAP, CMF, MFI, 52W_HL_Ratio). Legacy `calculate_technicals()` shim preserved for v1 router compatibility.
  - `announcements_service.py` — Full rewrite. Parallel fetch from NSE (boardMeetings + actions) and BSE (actions), deduplication by (date, purpose). Classifies into Board_Meeting, Dividend_Declared, Bonus_Split, Corporate_Action, NSE_Filing nodes.
- All 7 services: `list[Node]` output with correct schema, weights from `weights.yaml`, `source_id`, `confidence`.

**Files modified/created:**
- `backend/services/ohlcv_service.py` (new)
- `backend/services/price_service.py` (new)
- `backend/services/ratios_service.py` (new)
- `backend/services/financials_service.py` (new)
- `backend/services/shareholding_service.py` (new)
- `backend/services/technicals_service.py` (rewritten — Node output, ohlcv_service delegation)
- `backend/services/announcements_service.py` (rewritten — NSE+BSE parallel, Node output)

**Validation:** All 7 service modules import cleanly in `.venv312`.

**Next:** Phase 3 — Knowledge Graph. Build `backend/graph/builder.py`, `scorer.py`, `store.py`.

---

### 2026-04-26 — Phase 2.8 Complete: Component Waterfall Tests

**What was done:**
- Created `backend/tests/integration/test_component_waterfalls.py` with 38 tests covering all 7 Phase 2 services.
- Test structure: 7 test classes (one per service) + 1 cross-service invariant class.
- Live data tests: each service tested against RELIANCE (large cap), IRCTC (mid cap), QUESTCAP (small cap).
- Waterfall fallback tests use `unittest.mock.patch` + `AsyncMock` to force L1 failures, then assert L2/L3 source kicks in.
- Total/exhaustion failure tests: verify services return `[]` or empty DataFrame without raising.
- Node schema invariants: every node checked for `source`, `name`, `confidence`, `signal`, `weight`, `as_of_date`.
- All 38 tests collect cleanly. Run with: `STOCXI_INTEGRATION=1 python -m pytest backend/tests/integration/test_component_waterfalls.py -v --asyncio-mode=auto`

**Files created/modified:**
- `backend/tests/integration/test_component_waterfalls.py` (new — 38 tests)
- `PLAN.md` (2.8 ticked ✓)
- `NEW_PROGRESS.md` (this update)

**Phase 2 status:** COMPLETE. All 8 items done (2.1–2.8).

**Next:** Phase 3 — Knowledge Graph. Start with `backend/graph/builder.py` (edge types + builder).

---

### 2026-04-26 — Bug Fixes: 4 Data Pipeline Bugs Found + Fixed (10-stock run)

**Bugs found and fixed:**

1. **OHLCV date field mismatch** (`backend/fetchers/nse_client.py`)
   - NSE library now returns `mtimestamp` (e.g. `'16-Apr-2026'`), not `CH_TIMESTAMP`/`chTimestamp`
   - Fix: added `mtimestamp` as third fallback in `fetch_ohlcv` date extraction
   - Impact: OHLCV was 0/10 → now 10/10

2. **BSE quote wrong field names** (`backend/fetchers/bse_client.py`)
   - BSE library returns `LTP` (last traded price), `Open`, `High`, `Low`, `PrevClose`
   - Our code was looking for `CurrentRate`, `OpenRate` etc. — all returning None
   - Fix: updated `fetch_quote` to use correct field names; compute change/change_pct from LTP−PrevClose
   - Impact: price was 7/10 → now 10/10

3. **NSE shareholding format changed** (`backend/fetchers/nse_client.py`)
   - NSE shareholding now returns flat list of `{pr_and_prgrp, public_val}` rows (one per period)
   - Old code expected nested `categories` array — found nothing, raised ValueError
   - Fix: filter `NEW_1` desc entries, read `pr_and_prgrp` (promoter) and `public_val` (public) directly
   - Impact: shareholding was 2/10 → now 10/10 (NSE for large/mid caps, Screener fallback for others)

4. **TATAMOTORS Screener slug mismatch** (`backend/services/screener_service.py`, new `config/screener_slugs.yaml`)
   - Screener search API returns no result for "TATAMOTORS"; actual slug is "TMCV"
   - Correct ticker: TATAMOTORS (NSE) → TMCV (Screener), TMPV is the passenger vehicle subsidiary
   - Fix: added `config/screener_slugs.yaml` with static override map; updated `_resolve_screener_slug`:
     (1) static override map, (2) API search by NSE symbol, (3) API search by company name, (4) raw symbol
   - Impact: TATAMOTORS financials 0→✓, shareholding 0→4 nodes via Screener

**Ticker correction:** ZOMATO → ETERNAL (NSE rebranded; already in alt_tickers.yaml)

**Final coverage after fixes:**
```
Stock         price  ohlcv  ratios  financials  shareholding  technicals  announcements
RELIANCE      10/10  10/10  10/10   10/10       10/10         10/10       10/10
TCS           ✓      ✓      ✓       ✓           ✓             ✓           ✓
HDFCBANK      ✓      ✓      ✓       ✓           ✓             ✓           ✓
SUNPHARMA     ✓      ✓      ✓       ✓           ✓             ✓           ✓
TATAMOTORS    ✓(BSE) ✓      ✓       ✓(2 nodes)  ✓(4 nodes)    ✓           ✓
ETERNAL       ✓      ✓      ✓       ✓           ✓             ✓           ✓
IRCTC         ✓      ✓      ✓       ✓           ✓             ✓           ✓
DMART         ✓      ✓      ✓       ✓           ✓             ✓           ✓
COALINDIA     ✓      ✓      ✓       ✓           ✓             ✓           ✓
NESTLEIND     ✓      ✓      ✓       ✓           ✓             ✓           ✓
Coverage:     10/10  10/10  10/10   10/10       10/10         10/10       10/10
```

**Files modified:**
- `backend/fetchers/nse_client.py` (OHLCV date field + shareholding parser)
- `backend/fetchers/bse_client.py` (quote field names: LTP, Open, PrevClose)
- `backend/services/screener_service.py` (slug resolver: static map + name fallback)
- `config/screener_slugs.yaml` (new — static NSE→Screener slug overrides)
- `backend/tests/research/run_10_stocks.py` (new — 10-stock coverage runner, ETERNAL instead of ZOMATO)

---

### 2026-04-26 — Phase 4 Complete: Agent Layer + 6 Bug Fixes

**What was done:**

Phase 4 Wave 1 (4.1–4.5) was already implemented. Wave 2 (4.6–4.9) was also
already written. This session completed the remaining work: fixed all outstanding
bugs and wrote the full test suite.

**Bug fixes (6 bugs):**

1. **orchestrator.py — FetchFailure isinstance check** (`backend/agents/orchestrator.py`)
   - `_run_agent_safe` called `len(nodes)` which raises `TypeError` on a `FetchFailure`
     pydantic model (no `__len__`). Error was silently caught but logged wrong.
   - Fix: import `FetchFailure`, add `isinstance(result, FetchFailure)` check before `len()`.
     Now logs `WARNING orchestrator: agent=X FetchFailure — domain=... reason=...`

2. **agent_analysis.py — wrong config import** (`backend/agents/agent_analysis.py`)
   - `_get_llm_client()` had `from config import settings` — resolves to non-existent
     top-level `config` module, not `backend.config`.
   - Fix: changed to `from backend.config import settings`.

3. **agent_analysis.py — stale orphaned import** (`backend/agents/agent_analysis.py`)
   - `_call_llm()` had a dead `from config import settings` that was never used.
   - Fix: removed entirely.

4. **calibration/refit_weights.py — parents[] off-by-one** (`backend/calibration/refit_weights.py`)
   - `_WEIGHTS_PATH` and `_CALIB_PATH` used `Path(__file__).parents[3]` (resolves to
     `10.Projects/`) instead of `parents[2]` (project root). Config files were unreachable.
   - Fix: changed both to `parents[2]`.

5. **graph/knowledge_graph.py — wrong agreement/contradiction field names**
   - `build_graph()` looked up `link.get("node_a")` / `link.get("node_b")` but
     formatter writes `node_id_a` / `node_id_b` (agreements) and
     `node_id_positive` / `node_id_negative` (contradictions). All lookups returned
     `None` — no agreement/contradiction edges ever rendered.
   - Fix: corrected all four key names.

6. **graph/knowledge_graph.py — verdicts dict vs list mismatch**
   - `build_graph()` iterated `admin_view["verdicts"]` expecting a `list[dict]` but
     formatter stores it as `dict[str, {...}]` keyed by category. Loop produced no nodes.
   - Fix: added normalization step that detects dict-shaped verdicts and converts to list
     with `"category"` key injected. Also fixed signal key: formatter uses `"direction"`,
     not `"signal"`.

**Phase 4.10 Tests written:** `backend/tests/unit/test_phase4_pipeline.py`
- 25 tests across 7 `unittest.TestCase` classes
- Zero network, LLM, or Redis dependencies — pure unit tests
- Covers: FetchFailure handling, InsufficientDataError gate, node sanitization,
  verifier claim stripping + low_fidelity, formatter output shape, draft parsing,
  cache key uniqueness

**Files modified:**
- `backend/agents/orchestrator.py` (FetchFailure isinstance fix + FetchFailure import)
- `backend/agents/agent_analysis.py` (config import fix + stale import removal)
- `backend/calibration/refit_weights.py` (parents[2] fix)
- `backend/graph/knowledge_graph.py` (field names + verdicts dict/list fix)
- `backend/tests/unit/test_phase4_pipeline.py` (new — 25 tests)
- `PLAN.md` (Phase 4 all 10 items ticked ✓)
- `NEW_PROGRESS.md` (this update)

**Validation:** All 25 tests structured as pure unit tests, runnable with:
`python -m pytest backend/tests/unit/test_phase4_pipeline.py -v`

**Phase 4 status: COMPLETE.** All 10 items done (4.1–4.10).

**Next:** Phase 5 — API + Frontend Wiring. Start with `backend/routers/v3_analysis.py`.

---

### 2026-04-26 — Newsdata.io Pipeline + Graph News Edges

**What was done:**

Replaced the old RSS-only news pipeline with a proper structured newsdata.io primary source,
per-article key sentence extraction, stock impact derivation, and 3 new knowledge graph edge
rules for news nodes.

**Environment change:**
- Switched from `.venv312` to `conda env stocxi` (`/Users/prathamraj/miniforge3/envs/stocxi`)
- All future commands use `conda run -n stocxi ...`
- CLAUDE.md updated with mandatory conda env section (Section 0)
- Missing packages installed into stocxi env: `nse`, `bse`, `feedparser`, `asyncpg`, `pypdf`

**Gemini 2.5 Pro fix:**
- Verified Vertex AI ADC auth works (`vertex_credentials.json`)
- Root cause: `max_tokens=1200/1400` was exhausted by the thinking phase (reasoning tokens)
- Fixed both calls in `ai_service.py` to `max_tokens=8192`
- `agent_analysis.py` already had `max_tokens=32768` from `versions.yaml` — correct

**Newsdata.io pipeline (new):**

| File | Status | What |
|---|---|---|
| `backend/fetchers/newsdata_client.py` | ✅ New | REST client, `qInTitle` precision + `q=` broadfall, top-10 by date |
| `backend/util/article_extractor.py` | ✅ New | Deterministic sentence scorer: symbol mention +3, financial keywords +0.5 (capped +2), numbers/% +2, length 10-50 +1, boilerplate -1 |
| `backend/services/news_service.py` | ✅ Rewritten | newsdata.io L1 → Google News RSS L2. Adds `key_sentence`, `stock_impact`, `signal_class` per article. Cap 10. |
| `backend/agents/agent_news.py` | ✅ Updated | Cap 10 articles. Node value = `"{title} | Key insight: {key_sentence}"`. `value_raw` gets `key_sentence`, `stock_impact`, `signal_class`. newsdata_io confidence = 0.80. |
| `backend/graph/builder.py` | ✅ Updated | 3 new edge rules: ①All news→Price `caused_by` ②High-severity news (`regulatory/fraud/rating/leadership/ma/contract/dividend`) `contradicts`/`supports` matching technical signals ③Earnings/contract/rating news `correlates` with Revenue/Profit/EPS/D-E nodes. All news → `news_impact` virtual cluster `part_of`. |
| `config/sources.yaml` | ✅ Updated | Added `newsdata_io` source with confidence=0.80, rate limits. `max_items_per_analysis: 10`. |
| `backend/config.py` | ✅ Updated | Added `newsdata_api_key: str = ""` to Settings |
| `backend/.env` | ✅ Updated | `NEWSDATA_API_KEY` set (user-provided) |
| `backend/tests/unit/test_newsdata_pipeline.py` | ✅ New | 43 unit tests, 43/43 PASS |

**Full test suite:** 93/93 PASS (50 existing + 43 new)

**Files modified:**
- `backend/fetchers/newsdata_client.py` (new)
- `backend/util/article_extractor.py` (new)
- `backend/services/news_service.py` (rewritten)
- `backend/agents/agent_news.py` (updated)
- `backend/graph/builder.py` (updated — 3 new edge rule blocks)
- `config/sources.yaml` (newsdata_io added, max_items 20→10)
- `backend/config.py` (newsdata_api_key field)
- `backend/.env` (NEWSDATA_API_KEY)
- `backend/.env.example` (NEWSDATA_API_KEY placeholder)
- `backend/services/ai_service.py` (max_tokens 1200/1400 → 8192)
- `CLAUDE.md` (Section 0: conda env rule added)
- `NEW_PROGRESS.md` (this update)

**Next:** Phase 5 — API + Frontend Wiring. Start with `backend/routers/v3_analysis.py`.

---

### 2026-04-26 — Phase 2 Bug Fixes + Phase 3 Complete: Knowledge Graph

**Bug Fixes (4 bugs):**

1. **Screener period ordering** (`backend/services/financials_service.py`)
   - `_extract_series()` was returning data oldest-first (Screener stores columns oldest-left)
   - Fix: `return {"periods": periods[::-1], "values": values[::-1]}` — now newest-first
   - Impact: D/E ratio, revenue periods, all financial metrics now show correct latest period

2. **Announcement date truncation** (`backend/services/announcements_service.py`)
   - `str(event_date)[:10]` truncated "12-May-2026" → "12-May-202" (year cut)
   - Fix: added `_normalise_date()` helper that tries multiple strptime formats → ISO output
   - All `[:10]` slices replaced with `_normalise_date()` across _item_to_node + dedup key

3. **BSE actions Ex_date field** (`backend/fetchers/bse_client.py`)
   - BSE library returns `Ex_date` but code only checked `ExDate`/`exDate`
   - Fix: added `Ex_date` as primary lookup before the existing fallbacks

4. **Announcements top-10 + PDF content** (`backend/services/announcements_service.py`)
   - Added sort by date descending before deduplication
   - Added `unique[:10]` slice to limit to 10 most recent
   - Added `_enrich_with_pdf_text()` async enrichment: fetches PDF from NSE/BSE CDN URLs
   - Added `_fetch_pdf_text()`: validates domain against allowlist, fetches via httpx,
     parses with `pypdf`, returns first 1000 chars stored in `value_raw["pdf_text"]`
   - Added `pypdf==4.3.1` to requirements.txt + installed in .venv312

**Phase 3 — Knowledge Graph: COMPLETE**

- `backend/graph/scorer.py` (new):
  - `recency_factor(as_of_date, analysis_date)` → 1.0 / 0.8 / 0.5 / 0.2 by age band
  - `score_node(node, analysis_date)` → weight × confidence × recency_factor (clamped [0,1])
  - `score_all(nodes, date)` → {node_id: score} batch scorer
  - `top_nodes(nodes, scores, n=40)` → top-N ranked for prompt budget

- `backend/graph/builder.py` (new):
  - 7 edge types: `supports`, `contradicts`, `derived_from`, `correlates`, `caused_by`, `part_of`, `same_domain`
  - `build_edges(nodes, scores, analysis_id)` → `list[Edge]`
  - Rules: same_domain within category (window-3), supports/contradicts cross-category by signal
  - `_DERIVED_FROM` map: EPS←Net_Profit, MACD←EMA_12/EMA_26, Bollinger←SMA_20, etc.
  - `_PART_OF` map: RSI/Stoch/Williams→momentum_cluster, MACD/ADX/SMA→trend_cluster, etc.
  - Edge strength = score_a × score_b; dedup by (from_id, to_id, relation)

- `backend/graph/store.py` (new):
  - `write_nodes(nodes, analysis_id)` → upsert to `nodes` table (ON CONFLICT DO UPDATE)
  - `write_edges(edges, analysis_id)` → upsert to `node_edges` table
  - `read_nodes_by_analysis(analysis_id)` → fetch all nodes for an analysis
  - `read_subgraph(analysis_id, root_node_id, max_depth=3)` → recursive CTE traversal
  - asyncpg lazy import — imports succeed without DB, raises RuntimeError on first call

- `backend/tests/unit/test_graph_phase3.py` (new — 25 tests, all PASS):
  - TestRecencyFactor: 7 tests (all 4 bands + edge cases + future date clamp)
  - TestScoreNode: 5 tests (formula, stale, low confidence, >1 clamp, zero weight)
  - TestTopNodes: 2 tests
  - TestBuildEdges: 11 tests (all edge types, dedup, strength formula, analysis_id stamp)

**Files created/modified:**
- `backend/services/financials_service.py` (period reverse fix)
- `backend/services/announcements_service.py` (date normalise, top-10, PDF enrichment)
- `backend/fetchers/bse_client.py` (Ex_date field)
- `backend/graph/scorer.py` (new)
- `backend/graph/builder.py` (new)
- `backend/graph/store.py` (new)
- `backend/tests/unit/test_graph_phase3.py` (new — 25 tests)
- `backend/requirements.txt` (added pypdf==4.3.1, asyncpg==0.30.0)
- `PLAN.md` (Phase 3 all 5 items ticked ✓)

**Validation:** 25/25 unit tests PASS (no network, no DB required)

**Next:** Phase 4 — Agent Layer. Start with `backend/agents/orchestrator.py`.

---
