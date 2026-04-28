

# opencode-changes.md — Changes Made by OpenCode Sessions

> Append-only log of every code change made by OpenCode (Claude/opencode).
> Other LLMs read this to understand what was modified and why.
> Each entry: date, what changed, files touched, rationale.

---

## 2026-04-27 — LLM Summarization for Announcement Nodes

### What
Added Gemini 2.5 Pro batch summarization to the announcement pipeline. Each of the
10 fetched announcements now gets a 1-2 line AI-generated summary stored in `node.value`
instead of raw text truncation.

### Why
The old approach truncated raw purpose text to 150 chars. The analysis LLM needs
meaningful context about each announcement, not cut-off strings.

### Files changed

**`backend/services/announcements_service.py`**
- Added `import json` and `from backend.config import settings` to imports
- Added `_summarize_announcements(items, symbol)` function (~90 lines):
  - Builds compact prompt with all items (purpose + PDF text + classification)
  - Single batch Gemini 2.5 Pro call via OpenAI-compatible Vertex AI client
  - Parses JSON array response, handles markdown fences
  - Truncated JSON recovery via regex extraction of quoted strings
  - Attaches `llm_summary` to each item dict on success
  - Falls back to text truncation on any LLM failure (never crashes pipeline)
- Modified `get_announcements()`: added `await _summarize_announcements(enriched, symbol)` step
  after PDF enrichment, before `_build_nodes()`
- Modified `_item_to_node()`: prefers `item["llm_summary"]` over raw text truncation when available
- Added `llm_summary` field to `value_raw` dict for audit

### Pipeline order
```
Fetch (NSE+BSE parallel) → Dedup → Top 10 → PDF enrichment → LLM summarize → Build nodes
```

### Verified
- All 10 ASIANPAINT announcements have LLM summaries (10/10)
- All 257 tests pass (93 unit + 25 graph + 139 golden)

---

## 2026-04-27 — Knowledge Graph Rebuild (3D + Typed Edges)

### What
Updated the knowledge graph system to support typed edges from the builder module
and produce richer 3D visualizations.

### Files changed

**`backend/graph/builder.py`**
- Enriched `Edge` model: added `direction` (unidirectional/bidirectional) and `label` fields

**`backend/graph/knowledge_graph.py`**
- Added `serialize_for_llm(nodes, edges)` function — outputs structured text for LLM
  context window per rebuild doc §4.2
- Updated `build_graph()` to accept optional `edges` parameter from builder
  (typed edges: supports, contradicts, derived_from, correlates, caused_by, part_of)
- Updated 3D HTML edge legend to show all 6 edge types

**`backend/graph/__init__.py`**
- Added `serialize_for_llm` to exports

**`backend/agents/orchestrator.py`**
- Fixed line ~284: `G.number_of_nodes()` crashed on dict; changed to
  `G["meta"]["node_count"]` / `G["meta"]["edge_count"]`

**`generate_graph.py`**
- Fixed 6 occurrences of `node_a`/`node_b` → `node_id_a`/`node_id_b`
  and `node_id_positive`/`node_id_negative`

**`run_e2e_analysis.py`**
- Updated graph section to use `build_graph(nodes, admin, edges=kg_edges)`
  with `score_all` + `build_edges` + `serialize_for_llm`
- Set `SECTOR = "paints"` for Asian Paints

### Verified
- All 257 tests pass
- ASIANPAINT E2E run: 50 nodes, 253 edges (130 typed), graph renders in browser

---

## Key Context for Future LLMs

### Environment
- **Must use**: `conda run -n stocxi python ...` (not .venv312)
- Python 3.11 in `/Users/prathamraj/miniforge3/envs/stocxi/`
- Vertex AI ADC auth via `vertex_credentials.json`

### Architecture contracts
- Every agent returns `list[Node] | FetchFailure` — never raises for data issues
- Node `node_id` is deterministic: `{stock}|{category}|{name}|{as_of_date}`
- Node `value` is display string (max 150 chars); `value_raw` is dict for audit
- All external fetches go through `backend/fetchers/http_client.py`
- LLM calls use `google/gemini-2.5-pro` via Vertex AI OpenAI-compatible client
- Temperature 0 for production analysis, pinned model + prompt + weight versions

### Known issues (not bugs, just API limitations)
- `^NSEI` OHLCV data unavailable (Nifty index not in NSE library or yfinance) — context agent
  degrades gracefully
- newsdata.io returns HTTP 429 during heavy testing — rate limited, non-fatal
- NSE `announcements()` market-wide filter often returns empty for specific stocks —
  `announcements_service.py` uses `boardMeetings` + `actions` instead (reliable)

### File locations
- Config: `config/versions.yaml`, `config/weights.yaml`, `config/profiles.yaml`, `config/sources.yaml`
- Schemas: `backend/schemas/node.py`, `backend/schemas/messages.py`
- Agents: `backend/agents/agent_*.py`
- Services: `backend/services/*.py`
- Fetchers: `backend/fetchers/*.py`
- Graph: `backend/graph/*.py`
- Tests: `backend/tests/unit/`, `backend/tests/golden/`
- Reports output: `reports/`
- Graph output: `graphify-out/stocks/<SYMBOL>/<date>.html`

---

## 2026-04-27 — Agent Timeout Fix + E2E Test Fix

### Problem Discovered
When all 5 data agents ran in parallel via `asyncio.gather`, each agent's internal 20s timeout was too tight due to shared resource contention (NSE/BSE HTTP connections, yfinance calls, Gemini API). Result: technical, fundamental, and context agents timed out → 0 nodes for those categories in the knowledge graph.

Evidence from parallel timing test:
```
technical      :  20.9s    0 nodes  [TIMEOUT]
fundamental    :  20.9s    0 nodes  [TIMEOUT]
news           :  20.9s    1 nodes  [TIMEOUT]
announcement   :  20.9s   10 nodes  [TIMEOUT]
context        :  20.9s    4 nodes  [TIMEOUT]
```
Same agents worked fine individually in ~5s each.

### Changes Made

#### 1. Increased agent internal timeouts (20s → 45s)
- **`backend/agents/agent_technical.py:23`** — `_FETCH_TIMEOUT_SECONDS: int = 45`
- **`backend/agents/agent_fundamental.py:28`** — `_AGENT_TIMEOUT: float = 45.0`
- **`backend/agents/agent_news.py:48`** — `_FETCH_TIMEOUT: float = 45.0` (was 25s, now 45s)
- **`backend/agents/agent_announcement.py:24`** — `_TIMEOUT_SECONDS: float = 45.0`
- **`backend/agents/agent_context.py:30`** — `_AGENT_TIMEOUT: float = 45.0`

#### 2. Increased orchestrator per-agent timeout (20s → 50s)
- **`backend/agents/orchestrator.py:71`** — `AGENT_TIMEOUT_S = 50.0`

The orchestrator timeout (50s) is now strictly greater than internal agent timeouts (45s), so the orchestrator is the outer safety net, not the bottleneck.

#### 3. Fixed E2E test announcement fetch
- **`backend/tests/e2e/analysis_runner.py:61`** — Replaced `from fetchers.nse_client import fetch_announcements` with `from services.announcements_service import get_announcements`
- **`backend/tests/e2e/analysis_runner.py:32`** — Added `date` to datetime import
- **`backend/tests/e2e/analysis_runner.py:62`** — Added `from schemas.messages import UserProfile`
- **`backend/tests/e2e/analysis_runner.py:99-104`** — Replaced `_nse_fetch_announcements(symbol, limit=8)` with `_svc_get_announcements(symbol, as_of_date, profile, request_id)`
- **`backend/tests/e2e/analysis_runner.py:119-131`** — Added Node→dict conversion (subject, category, date, source, llm_summary)

### Result
After fixes, parallel test shows all agents succeed:
```
technical      :  24.2s   17 nodes  [OK]
fundamental    :  24.1s   14 nodes  [OK]
news           :  24.1s    1 nodes  [OK]
announcement   :  24.1s   10 nodes  [OK]
context        :  25.0s    4 nodes  [OK]
Total parallel: 25.0s  |  Total nodes: 46
```

Full orchestrator run: **46 nodes, 50 graph nodes, 249 edges, 130 typed edges**
Knowledge graph now includes all 5 categories: Technical, Fundamental, News, Announcement, Context.

### Files Modified (this session)
- `backend/agents/agent_technical.py` — timeout 20→45
- `backend/agents/agent_fundamental.py` — timeout 20→45
- `backend/agents/agent_news.py` — timeout 25→45
- `backend/agents/agent_announcement.py` — timeout 20→45
- `backend/agents/agent_context.py` — timeout 20→45
- `backend/agents/orchestrator.py` — AGENT_TIMEOUT_S 20→50, docstring updates
- `backend/tests/e2e/analysis_runner.py` — announcement fetch fix (nse_client → announcements_service), Node→dict conversion

---

## 2026-04-27 — News LLM Summarization + Horizon-Aware Weights + Node Format

### Problem Discovered
The news pipeline had 4 critical issues:
1. **No LLM summarization** — used heuristic `article_extractor.py` (keyword scoring) which produced empty key_sentences for RSS articles (no body text available from Google News RSS)
2. **Wrong signal classification** — heuristic classified "Net profit falls 12.5%" as `generic_positive` (positive/negative word intersection failed)
3. **Uniform weights** — all news articles got the same weight regardless of actual relevance or investor horizon fit
4. **Ugly node values** — raw headline concatenation with no structure, unreadable for both model and user

### What Was Built

Full news pipeline now:
```
newsdata.io (L1) → Google RSS (L2) → normalise → heuristic enrichment
→ Gemini 2.5 Pro batch summarization → structured nodes with horizon-aware weights
```

### Files Changed

**`backend/services/news_service.py`** — major changes:
- Added `_summarize_articles(articles, symbol)` — **sync** function (not async, runs in thread pool executor from `get_news`):
  - Sends all 10 articles as one batch to Gemini 2.5 Pro via Vertex AI
  - Each article gets: `llm_summary` (5-line), `llm_relevance` (0.0-1.0), `llm_signal_class`, `llm_horizon` (short/long/both)
  - Prompt asks for JSON array with 4 fields per article
  - Truncated JSON recovery via regex `re.findall(r'\{[^{}]+\}', raw)`
  - Falls back gracefully on any failure — articles returned unchanged
- Updated `_get_news_sync()` to call `_summarize_articles()` after `_enrich()`
- Added `json`, `yaml` imports
- **Important**: `_summarize_articles` is sync, NOT async — because it runs inside `_get_news_sync` which is already in a thread pool executor. Using `asyncio.run()` here caused event loop errors.

**`backend/agents/agent_news.py`** — major changes:
- Updated `_news_weight()` — new formula:
  ```
  weight = (category_budget / max_articles) × class_multiplier × relevance × horizon_match
  ```
  - `relevance_score`: LLM-assessed 0.0-1.0 (default 0.5 if LLM fails)
  - `horizon_match`: 1.0 if article horizon matches user, 0.6 if not
  - Added `relevance_score` and `article_horizon` parameters
- Updated `_article_to_node()`:
  - Moved `relevance_score` and `article_horizon` computation BEFORE value construction (was causing `UnboundLocalError`)
  - Node value format changed from `"{title} | {llm_summary}"` to structured:
    ```
    [signal_class] clean_headline
    Analysis: <LLM summary>
    Impact: Positive/Negative/Neutral | Relevance: X/1.0 | For: horizon-term
    ```
  - Headline cleaning: regex strips source suffixes like " - Business Standard"
  - Value cap increased from 500 to 800 chars
  - `value_raw` now includes: `llm_summary`, `llm_relevance`, `llm_signal_class`, `llm_horizon`
  - `horizon_relevance` field set from LLM horizon (short/long/both) instead of always `both`
- Updated `_classify()` — added 2 new signal classes:
  - `earnings_result`: detects quarterly results, PAT, revenue keywords; signal direction from neg/pos words in headline
  - `analyst_action`: detects analyst, target price, brokerage keywords; signal from upgrade/buy vs downgrade/sell
- Added `_CLASS_KEYWORDS` entries for `earnings_result` and `analyst_action`

**`config/weights.yaml`** — added 3 new news signal classes:
```yaml
earnings_result:
  weight_multiplier: 1.4
  description: "Quarterly/annual earnings results"
analyst_action:
  weight_multiplier: 1.2
  description: "Analyst upgrade/downgrade, target price change"
sector_policy:
  weight_multiplier: 0.9
  description: "Sector-level policy change, regulation"
```

### Verified Results

**RELIANCE (short horizon):**
| Article | LLM Class | Relevance | Weight |
|---|---|---|---|
| Q4 profit slips 8.9% YoY | earnings_result | 0.9 | 0.0378 |
| Stock to Watch (routine) | generic_positive | 0.1 | 0.0024 |

**MARUTI (short vs long horizon):**
| Article | Class | Relevance | Short W | Long W | Ratio |
|---|---|---|---|---|---|
| Record 2.34M production | generic_positive | 0.8 | 0.0192 | 0.0043 | 4.5x |
| PAT +14.7% forecast | analyst_action | 0.6 | 0.0216 | 0.0014 | 15.4x |
| CCI hearing adjourned | regulatory_sebi_action | 0.5 | 0.0300 | 0.0042 | 7.1x |

LLM correctly classified articles that heuristic got wrong (earnings_result vs generic_positive).

### Known Issues
- newsdata.io free tier (200 req/day) exhausted during testing — pipeline falls back to Google News RSS correctly
- Heuristic classifier still has false positives — but LLM overrides when available
- Duplicate RSS articles not deduplicated (same headline from different sources)

---

*Last updated: 2026-04-27 by OpenCode*
