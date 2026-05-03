# AGENTS.md — Multi-Agent Orchestration Contract

> Every agent defined here is a Python module in `backend/agents/`.
> Agents communicate via typed pydantic messages, never raw dicts.
> Each agent has one job, one input type, one output type. No agent does two things.
> Data source methods referenced here are verified via live testing (2026-04-26).

---

## 1. Orchestrator Agent

**Module:** `backend/agents/orchestrator.py`
**Entry:** `async def run_analysis(stock: str, profile: UserProfile, as_of_date: date) -> AnalysisResult`

Responsibilities:

1. Validate request (stock exists in NSE/BSE, profile valid, `as_of_date` not future).
2. Compute `profile_bucket = (horizon, risk)` and check analysis cache.
   - Key: `analysis:v{prompt_v}:{weight_v}:{model_id}:{stock}:{profile_bucket}:{data_hash}`
   - If hit, return cached `AnalysisResult`.
3. On miss, fan out to data agents **in parallel** via `asyncio.gather`:
   - Technical Agent
   - Fundamental Agent
   - News Agent
   - Announcement Agent
   - Context Agent
4. Collect results. Failed agents return `FetchFailure` — orchestrator continues
   with partial data but records the gap in a `Data_Completeness` node.
5. Pass all nodes through:
   - **Normalizer** — raw payloads to Node schema
   - **Source Reconciler** — resolve conflicts via priority (L1 > L2 > L3), log winner and loser
   - **Sanitizer** — strip unsafe content before any LLM prompt
6. Check insufficient data thresholds (ARCHITECTURE Section 12). Abort with clean message if failed.
7. Build Knowledge Graph — nodes + typed edges (supports, contradicts, etc.).
8. **Anonymize** — STOCK_A, SECTOR_X, EXEC_A, PEER_1/2/3.
9. Hand anonymized node set + graph to Analysis Agent.
10. Hand Analysis Agent output to Verifier Agent.
11. Hand verified output to Output Formatter (de-anonymize, shape final JSON).
12. Write Audit Log row (append-only, immutable).
13. Write to Analysis Cache.
14. Return `AnalysisResult`.

**Timeouts:** Each data agent has a hard 20s budget. The full pipeline has a 60s budget.
On budget breach, return partial-data analysis rather than hanging.

---

## 2. Specialist Data Agents

All data agents implement the same protocol:

```python
class DataAgent(Protocol):
    domain: Literal["technical", "fundamental", "news", "announcement", "context"]

    async def fetch(self, stock: str, as_of_date: date) -> list[RawPayload] | FetchFailure: ...
    async def normalize(self, raw: list[RawPayload]) -> list[Node]: ...
    async def validate(self, nodes: list[Node]) -> list[Node]: ...   # drop bad, log dropped
```

Every fetch goes through `backend/fetchers/http_client.py` (rate-limited, retry-aware).
Every node gets `source_id`, `confidence`, `as_of_date` stamped at normalization.

---

### 2.1 Technical Agent

**Module:** `backend/agents/agent_technical.py`
**Domain:** `technical`

**Data flow:**
1. Fetch OHLCV via waterfall:
   - L1: `nse.fetch_equity_historical_data(sym, from_date, to_date)` — 247 rows/year,
     cols: `chOpeningPrice`, `chTradeHighPrice`, `chTradeLowPrice`, `chClosingPrice`, `chTotTradedQty`
   - L3: `yfinance.download("{sym}.NS")` → `.BO` → alt ticker fallback
2. Compute 17 indicators using `ta` Python library on the OHLCV DataFrame:
   - Trend: SMA_20, SMA_50, SMA_200, EMA_12, EMA_26, MACD, ADX
   - Momentum: RSI_14, Stochastic_K, Stochastic_D, Williams_%R, CCI
   - Volume: OBV, VWAP, Volume_SMA_20
   - Volatility: Bollinger_Upper, Bollinger_Lower
3. Emit one Node per indicator. Every calculation uses `as_of_date` — must not peek at future bars.
4. Apply NSE holiday calendar. Use split-adjusted prices.

**Output:** 17 indicator nodes + 1 Price node + 1 OHLCV_Summary node.

---

### 2.2 Fundamental Agent

**Module:** `backend/agents/agent_fundamental.py`
**Domain:** `fundamental`

**Data flow (3 sub-pipelines):**

#### Key Ratios
| Level | Source | Method | Fields |
|---|---|---|---|
| L1 | BSE | `equityMetaInfo(code)` | PE, ConPE, EPS, ConEPS, ROE, ConROE, PB, OPM, NPM, Sector, Industry |
| L2 | Screener | top-ratios scraper | PE, ROE, ROCE, Book Value, EPS, Dividend Yield |

#### Financial Statements
| Level | Source | Method | Fields |
|---|---|---|---|
| L1 | Screener | quarterly P&L (recency-picked) | 12+ quarters: Sales, Expenses, Operating Profit, OPM, Net Profit, EPS |
| L1 | Screener | annual P&L (recency-picked) | 10+ years with TTM column |
| L1 | Screener | balance sheet | Equity, Debt, Total Assets, Reserves |
| L1 | Screener | cash flow | CFO, CFI, CFF, Net Change |
| L2 | BSE | `resultsSnapshot(code)` | Revenue, Net Profit, EPS, Cash EPS, OPM%, NPM% (latest 2Q + FY, standalone) |

**Screener recency rule:** Fetch BOTH consolidated and standalone URLs. Compare most
recent period header from `#quarters`. Use whichever has more recent data. (See
ARCHITECTURE Section 3.3 for rationale — QUESTCAP bug.)

#### Shareholding
| Level | Source | Method | Fields |
|---|---|---|---|
| L1 | NSE | `shareholding(sym)` | Promoter%, Public%, Employee Trust% (90 quarterly records) |
| L2 | Screener | `#shareholding` section | Promoter%, FII%, DII%, Public% (quarterly) |

#### Additional Fundamentals
| Level | Source | Method | Fields |
|---|---|---|---|
| L1 | BSE | `getScripTradingStats(code)` | Market Cap (full + free-float), Turnover, WAP |
| L1 | BSE | `quoteWeeklyHL(code)` | 52W/monthly/weekly H/L with dates |

**Output:** Ratio nodes + Financial statement nodes + Shareholding nodes + Market cap node.

Passes all outputs through Source Reconciler when BSE and Screener provide the same field.

---

### 2.3 News Agent

**Module:** `backend/agents/agent_news.py`
**Domain:** `news`

**Data flow:**
1. Crawl ONLY approved domains from `config/sources.yaml`:
   - Priority 1: moneycontrol.com, economictimes.indiatimes.com, business-standard.com, livemint.com (RSS)
   - Priority 2: reuters.com (India), bqprime.com (RSS)
   - Priority 3: news.google.com (RSS search fallback)
2. Filter:
   - **Fetch if:** stock name match, sector match with material impact, SEBI/RBI/govt policy, material event
   - **Drop if:** generic market commentary, duplicate, >30d old (short-term) / >90d old (long-term), opinion piece
3. Sanitize via `backend/util/sanitizer.py`:
   - Strip HTML, scripts, attribution links
   - Truncate body to 400 tokens
   - Remove imperative sentences targeting the reader ("buy now", "click here", "ignore previous...")
   - Wrap in `<<<NEWS_BODY_START>>> ... <<<NEWS_BODY_END>>>` delimiters
4. Set `sanitized: true` on emitted nodes. Unsanitized news nodes are rejected downstream.

**Forbidden sources:** Twitter/X, Reddit, YouTube, Telegram, WhatsApp, TradingView community,
Investopedia, any blog or influencer page, any domain not in `config/sources.yaml`.

**Output:** Up to 20 sanitized news nodes (weighted sampling by recency x signal weight).

---

### 2.4 Announcement Agent

**Module:** `backend/agents/agent_announcement.py`
**Domain:** `announcement`

**Data flow:**
| Level | Source | Method | What It Returns |
|---|---|---|---|
| L1 | NSE | `announcements()` | desc, attachment PDF/XBRL, timestamp (market-wide, filter by stock) |
| L1 | NSE | `boardMeetings(sym)` | date, purpose, result PDF/XBRL links |
| L1 | NSE | `actions(sym)` | dividends, bonus, splits with ex-date |
| L1 | BSE | `actions(code)` | dividends, splits with ex-date (33 records) |
| L1 | BSE | `resultCalendar(from, to)` | upcoming result dates (374 records) |

**Classification:** Each filing is tagged by type:
- Quarterly result, board meeting outcome, dividend declaration
- M&A activity, promoter trade, SEBI action
- Insider trade, leadership change, rights/bonus/split
- Credit rating action

Highest signal quality — direct from exchanges, no web scraping, no parsing ambiguity.

**Output:** Classified announcement nodes with attachment URLs preserved in `value_raw`.

---

### 2.5 Context Agent

**Module:** `backend/agents/agent_context.py`
**Domain:** `context`

Emits 4 nodes (shared across all analyses for the same day):

| Node | Source | Logic |
|---|---|---|
| `Market_Regime` | NSE Nifty 50 OHLCV | 50d/200d SMA trend + India VIX level → bull/bear/sideways/high-vol |
| `Sector_Trend` | NSE sector index OHLCV | Sector-specific momentum and relative strength |
| `Peer_Snapshot` | BSE `equityMetaInfo` for top 3 peers | PE, ROE, market cap comparison |
| `Data_Completeness` | Internal | Count of nodes per category, missing sources flagged |

**Output:** 4 context nodes. Cached 24h (one fetch per day, reused by every analysis).

---

## 3. Analysis Agent

**Module:** `backend/agents/agent_analysis.py`
**Input:** Validated, sanitized, **anonymized** list of nodes + knowledge graph edges + user profile.
**Output:** `AnalysisDraft` — structured JSON, every claim tagged with `node_id`.

**10-Step Protocol (ARCHITECTURE Section 6):**

```
Steps 1-9: Zero deviation (80% of output)
  1. VALIDATE     — Load nodes, drop schema mismatches, verify minimums
  2. ANONYMIZE    — STOCK_A, SECTOR_X, EXEC_A, PEER_1/2/3 (done by orchestrator)
  3. TECHNICAL    — Read indicator nodes → verdict with citations
  4. FUNDAMENTAL  — Read ratio + financial nodes → verdict with citations
  5. NEWS         — Read sanitized news nodes → verdict with citations
  6. ANNOUNCEMENT — Read filing nodes → verdict with citations
  7. WEIGHTS      — Apply profile weights (horizon x risk → category mix)
  8. AGREEMENTS   — List cross-category agreements with node_id pairs
  9. CONTRADICTIONS — List conflicts, resolve via hierarchy

Step 10: Free reasoning (20%)
  — Non-obvious cross-category connections
  — Divergences (price up + OBV down = distribution)
  — Constrained to supplied node_ids only
```

**Constraints:**
- `temperature = 0`, pinned model id, pinned prompt version, pinned seed
- Prompt assembled from `backend/analysis/prompt_template.jinja` (version pinned in `config/versions.yaml`)
- Structured output via JSON schema (Gemini / Anthropic native function calling)
- Every sentence-level claim must carry a `node_id` field
- Never sees real stock name during reasoning — only anonymized tokens
- Never does de-anonymization itself

**On schema violation:** Retry once. On second failure, return "system error". Never
repair by prompt-engineering at runtime — that breaks determinism.

---

## 4. Verifier Agent

**Module:** `backend/agents/agent_verifier.py`
**Input:** `AnalysisDraft` + original node list.
**Output:** `VerifiedAnalysis` — same shape, uncited claims stripped.

**Logic:**
1. For every claim in the draft, check that each referenced `node_id` exists in the supplied node list.
2. Strip claims where `node_id` is missing or invalid.
3. Set `stripped_claims: int` count on output.
4. If `stripped_claims > 2`: flag `low_fidelity`, return to orchestrator for retry with tighter prompt.
5. Max 1 retry. On second failure, return analysis with `low_fidelity` badge visible to user.

**Implementation:** Prefer pure-Python verification (cheaper, deterministic). Use a small
LLM call only when claims are too unstructured for pattern matching.

This agent is the anti-hallucination gate. It is never skipped.

---

## 5. Output Formatter

**Module:** `backend/agents/formatter.py`
**Input:** `VerifiedAnalysis` + original stock/sector/peers (not anonymized tokens).

De-anonymizes by token substitution:
- `STOCK_A` → actual stock name
- `SECTOR_X` → actual sector
- `PEER_1/2/3` → actual peer names

Produces final `AnalysisResult` shaped for the API and PDF builder.

**User-facing output (ARCHITECTURE Section 11):**
- What the Data Suggests (plain English, no node IDs)
- Signals In Favor (bullet list with reasons)
- Signals Against (never hidden)
- Data Disclosure ("Analysis based on 17 technical indicators, 11 ratios...")
- Disclaimer (mandatory, every output)

De-anonymization is mechanical and deterministic — no LLM call.

---

## 6. Report Agent (PDF)

**Module:** `backend/agents/agent_report.py`

Triggered for Pro users or on-demand. Takes `AnalysisResult` + raw price/financial series.

Generates:
- Price chart (horizon-appropriate window)
- Technical indicator charts with signal annotations at referenced dates
- Fundamental trend charts (revenue, profit, debt)
- FII/DII/Promoter holding trend chart
- Knowledge graph visualization (networkx + plotly force-directed)
- News sentiment trend chart
- Cover page + disclaimers

Output: branded PDF via WeasyPrint. Cached alongside analysis (same key + `:pdf` suffix).

---

## 7. Communication Protocol

All inter-agent messages are pydantic models in `backend/schemas/messages.py`:

```python
class FetchRequest(BaseModel):
    stock: str
    as_of_date: date
    request_id: str   # for tracing

class RawPayload(BaseModel):
    domain: Literal["technical", "fundamental", "news", "announcement", "context"]
    source_id: str         # from config/sources.yaml
    source_url: str
    confidence: float      # 1.0 (L1), 0.85 (L2), 0.70 (L3), 0.50 (L4)
    fetched_at_ist: datetime
    payload: dict          # source-specific, kept raw for audit

class FetchFailure(BaseModel):
    domain: str
    source_id: str
    reason: Literal["timeout", "blocked", "parse_error", "unapproved_source", "empty"]
    error: str
    request_id: str

class AnalysisDraft(BaseModel):
    claims: list[Claim]              # each Claim has text + node_ids: list[str]
    verdicts: dict[str, Verdict]     # one per category
    agreements: list[AgreementLink]
    contradictions: list[ContradictionLink]
    model_id: str
    prompt_version: str
    weight_version: str

class VerifiedAnalysis(BaseModel):
    # same as AnalysisDraft + verification metadata
    stripped_claims: int
    low_fidelity: bool

class AnalysisResult(BaseModel):
    # de-anonymized, user-facing final output
    summary: str
    signals_favor: list[Signal]
    signals_against: list[Signal]
    data_disclosure: str
    disclaimer: str
    metadata: AnalysisMetadata
```

Never pass raw dicts between agents. Fail fast on schema mismatch.

---

## 8. Agent Rules (absolute)

| # | Rule |
|---|---|
| 1 | One agent = one domain. Don't have the News Agent fetch announcements "because it's similar". |
| 2 | Every agent validates its own output. Invalid nodes are dropped + logged; they never reach the orchestrator. |
| 3 | Every agent respects `as_of_date`. Future data leakage = bug. |
| 4 | No agent fetches from a source not in `config/sources.yaml`. Violation raises `UnapprovedSourceError`. |
| 5 | No agent invents or fills missing fields. Missing = missing. |
| 6 | No agent retries forever. Every external call: timeout + max 3 retries with exponential backoff + jitter. |
| 7 | On failure, an agent returns `FetchFailure`, not an exception. Exceptions are for bugs, not missing data. |
| 8 | Analysis Agent sees only anonymized node data. Never the real stock name during reasoning. |
| 9 | Analysis Agent uses pinned model + temp=0 + pinned prompt version. No runtime prompt mutation. |
| 10 | Verifier Agent is always run. Never skipped for "performance". |
| 11 | Output Formatter is pure Python, no LLM. |
| 12 | Every agent logs to the same structured logger with `request_id` for tracing. |
| 13 | All fetches go through `backend/fetchers/http_client.py`. No raw `requests.get()` in agent code. |
| 14 | Every node emitted has `source_id` and `confidence` stamped. No anonymous data. |

---

## 9. Failure Modes & Graceful Degradation

| Failure | Handler | User-visible result |
|---|---|---|
| One data source down | Orchestrator continues with remaining; `Data_Completeness` node reflects gap | Analysis runs with disclosure: "news data partial today" |
| All news sources down | Proceed with 0 news nodes; profile weight on news redistributed to other categories | Analysis runs with "no news data available" flag |
| Fundamentals totally missing | Abort — insufficient data (ARCHITECTURE Section 12) | "We don't have enough public data on this stock to produce a reliable analysis." |
| LLM provider down | Return cached response if any; else clean error | "Analysis temporarily unavailable. Please try again shortly." |
| Verifier strips >2 claims | One retry with tighter prompt; on second failure, return with `low_fidelity` badge | User sees badge; transparency preserved |
| Unapproved source attempted | Hard raise `UnapprovedSourceError`, log, alert | Never reaches user |
| NSE/BSE rate limited (429) | Pause source 15min, degrade to next waterfall level | Transparent — lower confidence noted |
| Screener HTML changed | Parse failure → DLQ, alert; use BSE `resultsSnapshot` as fallback | Partial fundamentals with disclosure |

No failure condition ever returns invented data to the user.

---

## 10. Pipeline Execution Order

```
Request arrives
    │
    ▼
Orchestrator validates → Cache check
    │ miss
    ▼
┌───────────────────────────────────────────────────┐
│  asyncio.gather (parallel, 20s timeout each)      │
│                                                   │
│  Technical Agent ──→ OHLCV + 17 indicators        │
│  Fundamental Agent ──→ Ratios + Financials + SH   │
│  News Agent ──→ Sanitized news (max 20)           │
│  Announcement Agent ──→ Classified filings        │
│  Context Agent ──→ Market regime + sector + peers  │
└───────────────────────────────────────────────────┘
    │
    ▼
Normalizer → Reconciler → Sanitizer
    │
    ▼
Insufficient Data Check (abort if below thresholds)
    │
    ▼
Knowledge Graph Builder (nodes + typed edges)
    │
    ▼
Anonymizer (STOCK_A, SECTOR_X, PEER_1/2/3)
    │
    ▼
Analysis Agent (10-step protocol, temp=0)
    │
    ▼
Verifier Agent (strip uncited claims)
    │
    ▼
Output Formatter (de-anonymize, shape response)
    │
    ▼
Audit Log Write → Cache Write → Return AnalysisResult
```

---

*Contract of the agent layer. Edits require updating orchestrator tests.*


<claude-mem-context>
# Memory Context

# [stocxi] recent context, 2026-05-04 3:27am GMT+5:30

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (20,598t read) | 1,194,452t work | 98% savings

### Apr 30, 2026
9 1:22a 🔵 yfinance ^NSEI Ticker Broken — JSONDecodeError on Download
10 " 🔵 yfinance Entirely Non-Functional in stocxi Environment — All Tickers Fail
11 " 🔵 NSE equityQuote API Returns Different Schema for Index Tickers
13 1:24a 🔵 NSE Library Has fetch_historical_index_data — Synchronous, Not Wrapped in nse_client.py
14 " 🔵 NSE fetch_historical_index_data Returns 70 Rows of Valid Nifty 50 OHLCV Data
15 " 🔵 nse_client.py fetch_ohlcv Implementation Pattern for Index OHLCV Fix
17 " 🔵 screener_service.py _most_recent_period — Page Selection Logic Confirmed Working
16 1:25a 🔵 ohlcv_service.py Full Waterfall Architecture — HISTORY_DAYS=400, No Index Special-Case
18 1:27a 🔵 screener_service Candidate Page Selection — TTM Header Always Wins Over Dated Quarters
19 " 🔵 Critical Bug: _most_recent_period Reads Oldest Quarter — Screener Headers Are Oldest-First
20 " 🔴 screener_service _most_recent_period Iterates Headers Forward — Bug Confirmed, Fix Identified
21 " 🔵 knowledge_graph.py Node Community Assignments — 4 Community Types for 3D Visualization
22 1:28a 🔴 screener_service._most_recent_period Fixed — Now Returns Max Period Across All Headers
23 " 🟣 fetch_index_ohlcv Added to nse_client.py — Enables Nifty 50 OHLCV via NSE Library
24 " ⚖️ Index vs Equity Detection in ohlcv_service — Space in Symbol Name as Discriminator
25 " 🔴 ohlcv_service.py Index Branching Implemented — But agent_context.py Still Passes "^NSEI" Not "NIFTY 50"
26 " 🔴 agent_context.py _market_regime_node Confirmed Using "^NSEI" — Change to "NIFTY 50" Required
27 1:29a 🔴 agent_context.py Fixed — Market_Regime Now Calls get_ohlcv("NIFTY 50") Not "^NSEI"
S1 Fix all bugs in stocxi Indian stock analytics backend — verify all data components work, fix NYKAA no-data issue, fix knowledge graph bugs (Apr 30 at 1:29 AM)
28 3:56a 🔵 Stocxi Project Debug Session Initiated via Handoff XML
29 " 🔵 Stocxi 3D Knowledge Graph Renders 0 Meshes in Browser Despite Valid Data Pipeline
30 " 🔵 Stocxi Knowledge Graph Architecture: Three-Layer Python-to-Three.js Pipeline
31 3:57a 🔵 kg_renderer.py Initialization Runs Immediately Without DOMContentLoaded Guard
32 " 🔵 Root Node Size=0 Causes SphereGeometry(0, 32, 16) in Three.js — Potential Loop Crash
33 " 🔵 Data Injection Uses json.dumps with ensure_ascii=False — Risk of Unicode Line Terminators in Injected JSON
34 3:58a 🔵 Root Node Mesh Creation Confirmed: SphereGeometry(0) Called for Root, Camera at z=500 Looking at Origin
35 " 🔵 tree_builder.py Serializes children Array Into JSON — JS prepareData() Has Redundant Children-Build Logic
36 3:59a 🔵 OrbitControls CDN Path Likely Invalid for Three.js 0.158.0 — examples/js/ Removed in Favor of examples/jsm/
37 " 🔵 Debug Panel Mesh/Edge Counts Updated Inside Animation Loop, Not updateScene() — Critical for Diagnosing Blank Graph
38 4:00a 🔵 Generated HTML Data Confirmed Clean: 63 Nodes, 210 Edges, No NaN/Infinity, All Positions Computed
39 " 🔵 animate() Called as Last Line of initScene() — Confirms OrbitControls Failure Blocks Entire Render Loop
40 " 🔵 Script Injection Attack Vector Eliminated: No &lt;/script&gt; Tag in 72KB DATA JSON
41 " 🔵 All Four Layout Functions Are Hoisted Declarations — No Temporal Dead Zone Issues
42 4:01a 🔵 Browser Screenshot Captured for Visual Inspection of Knowledge Graph State
S2 Fix blank 3D knowledge graph canvas in Stocxi — Three.js nodes not rendering (0 meshes shown despite 63+ nodes parsed) (Apr 30 at 4:02 AM)
43 4:16a ⚖️ Knowledge Graph UI Bug Fix Task — Todo List Defined
44 " 🔵 Visual Bug Evidence Loaded — Knowledge Graph Screenshots Analyzed
### May 3, 2026
45 11:11p 🔵 Three Active Bugs Identified in Stock Analysis Web App
46 " 🔵 Visual Evidence of AI Analysis Box Format Bug Captured
47 11:12p 🔵 Three Active Bugs Identified in Stock Analysis Web App
48 " 🔵 Announcement Summary: Frontend Renders Correctly, Service Generates Field Properly
49 " 🔵 Knowledge Graph Router References Broken Service Import
50 11:13p 🔵 Announcement Summary Pipeline Is Correctly Wired in Stock Router
51 " 🔵 Knowledge Graph Router Uses JSON-Based Service, Not HTML File Generation Script
52 " 🔵 Two Competing Knowledge Graph Implementations — v2_analysis Serves HTML Files, knowledge_graph Router Returns JSON
53 " 🔵 Knowledge Graph Endpoint Confirmed: Requires Pre-Generated HTML File, Returns 404 If Missing
54 11:14p 🔵 Knowledge Graph HTML Files Stored at Project Root `graphify-out/stocks/`
55 " 🔵 Pre-Generated Knowledge Graph Files Exist for 7 Stocks But May Be Stale
56 " 🔵 Critical Date Mismatch: Script Names HTML by MD File's `captured_at`, Router Looks for Today's Date
57 11:15p 🔵 Frontend Knowledge Graph Uses React Three Fiber 3D Renderer, NOT an HTML Iframe
58 " 🔵 Knowledge Graph Page Uses Iframe to `/api/v2/analysis/{symbol}/graph` — HTML File Approach Is Correct
59 " 🔵 Announcement Type and `fetchAnnouncements` Missing from `lib/types.ts` and `lib/api.ts`

Access 1194k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>