# Stocxi Fix Session — Status Handoff
**Date:** 2026-05-03  
**Session ended mid-way due to token limit.**  
**Read this at the start of next session — do NOT re-analyse. Jump straight to "REMAINING FIXES".**

---

## ROOT CAUSES FOUND (already analysed — don't re-search)

### 1. AI Analysis — "insufficient data" error
**File:** `backend/agents/orchestrator.py` line 70  
**Root cause:** `AGENT_TIMEOUT_S = 50.0` — the technical + fundamental agents each make 3–4 LLM calls and need ~90s. With 50s timeout they time out, return 0 nodes, and `_check_sufficient()` raises `InsufficientDataError`.  
**Log evidence:** `orchestrator: agent=technical timed out after 50s` and `orchestrator: agent=fundamental timed out after 50s`  
✅ **FIXED:** Changed to `AGENT_TIMEOUT_S = 120.0`

### 2. Knowledge Graph not visible on AI Analysis page
**Status:** Not investigated yet — the analysis page itself crashed before KG could be checked.  
**Where to look:** `frontend/app/stock/[symbol]/analysis/page.tsx` passes `initialResult` to `AnalysisClient`. The KG button at top-right links to `/api/v2/analysis/{symbol}/graph` which serves a static HTML file from `graphify-out/stocks/`. This HTML may not exist if analysis never completed (because of timeout). After fixing timeout (fix #1), analysis should complete and generate the HTML. Then verify the Knowledge Graph button works.

### 3. Announcements showing very old data (2001, 2009, 2012)
**File:** `backend/routers/stock.py` lines 700–714  
**Root cause:** Date sort key was `item.get("date") or "0000-00-00"` — a **string comparison**. BSE dates come as `"31-May-2012"` (DD-Mon-YYYY) while NSE dates come as `"2025-04-25"` (YYYY-MM-DD). String comparison of `"31-May-2012"` vs `"25-Apr-2025"` compares first character `"3" > "2"` so old BSE dates sort to the TOP.  
✅ **FIXED:** Replaced string sort with proper `datetime.strptime()` parsing supporting 5 date formats. Also hard-capped to `[:10]` (top 10 most recent). Also bumped cache key `v3 → v4` to invalidate stale 2h cache.

### 4. Financials — green/red coloring only on first column
**File:** `frontend/components/stock/FinancialsSection.tsx` line 114  
**Root cause:** `vi === 0` condition meant only the most-recent column (index 0) got color-coded vs previous. All other columns showed plain white.  
✅ **FIXED:** Changed `vi === 0` → `prevVal !== null` so ALL columns are colored green/red vs their immediately older period.

### 5. Technical indicators showing N/A
**Status:** Identified but NOT fixed yet.  
**Root cause:** `_nodes_to_legacy_dict()` in `technicals_service.py` only sets dict keys when a node exists. If an indicator computation fails (exception caught), no node is emitted, so the key stays absent from the dict. The frontend `fmt()` function shows `"N/A"` for `null`.  
**Most likely failing indicators:**
- `EMA 200` — needs 200+ days of OHLCV data; if only 70–100 rows returned, `ema_200 = null`
- `VWAP` — computed from daily OHLCV using volume-weighted price; can fail if volume column is 0 or all-null
- `Stochastic %K/%D` — can fail with small data

**Where to fix:** `backend/services/technicals_service.py` → `_compute_nodes()` function. Inside each `try/except` block, add a minimum-window fallback. For EMA 200, if `n < 200`, use a shorter window (e.g., `min(200, n-1)`). Already done for RSI (line 139: `w = min(14, max(2, n - 1))`). Apply same pattern to EMA and others.

**Specific fix needed (do NOT re-read whole file — go straight to these lines):**
```python
# EMA — around line 180-220 in technicals_service.py
# grep for "EMAIndicator" or "ta_trend.EMAIndicator"
# change: window=200 → window=min(200, n-1)
# same for window=50 → min(50, n-1), window=20 → min(20, n-1)

# VWAP — around line 340 in technicals_service.py
# grep for "VolumeWeightedAveragePrice" 
# ensure volume column is not all-zero before computing
```

### 6. Stock price + open/close wrong (₹3,202 vs NSE ₹3,094)
**Files:** `backend/fetchers/nse_client.py` (singleton), `backend/services/yfinance_service.py`  
**Root cause:** The NSE singleton (`_nse_instance`) was a module-level object created once at server startup and never refreshed. NSE's internal session cookie has a TTL. After ~30min, the session may return stale/cached data from a previous trading session.  
✅ **PARTIALLY FIXED:** Added 30-min session TTL refresh to `_get_nse()` in `nse_client.py`. The singleton is now recreated every 1800 seconds.

**Still verify:**
- The mapping in `yfinance_service.py` line 777: `"price": q["close"]` — this is correct because `nse_client` stores `lastPrice` under the key `"close"` (see `nse_client.py` line 166).
- If NseIndiaApi itself still returns stale data, the real fix is to use a fresh `NSE()` instance per request (not singleton). To do that, change `_get_nse()` to `return NSE(download_folder=_DOWNLOAD_FOLDER).__enter__()` and handle cleanup.

### 7. Pink focus box on chart/graph click
**File:** `frontend/components/stock/KnowledgeGraph.tsx` line 392 and `frontend/components/stock/KnowledgeGraphClient.tsx` line 379  
**Root cause:** `<Canvas>` from `@react-three/fiber` adds `tabIndex="0"` to the canvas element by default. When clicked, the browser shows its OS focus ring — on macOS Safari/Chrome it renders as a pink/blue glow box.  
**NOT FIXED yet.**

**Fix (2 lines, one in each file):**
```tsx
// KnowledgeGraph.tsx ~line 392:
<Canvas
  camera={{ position: [0, 5, 15], fov: 60 }}
  style={{ background: '#0A0A0A', outline: 'none' }}   // ← add outline: 'none'
>

// KnowledgeGraphClient.tsx ~line 379:
<Canvas
  camera={{ position: [0, 5, 18], fov: 50 }}
  style={{ background: '#0A0A0A', outline: 'none' }}   // ← add outline: 'none'
>
```

### 8. KeyFundamentals — empty space in panel
**File:** `frontend/components/stock/KeyFundamentals.tsx`  
**Root cause:** Panel only has 8 rows: EPS, Book Value, Face Value, Dividend Yield, ROE, ROCE, Industry, Sector. Many stocks return `null` for most of these, leaving the panel half-empty.  
**NOT FIXED yet.**

**Fix:** Add more metrics to the `rows` array. The backend already sends these fields (check `stock.py` response dict). Add:
- `Debt / Equity` — from screener_ratios (key: `"debt_to_equity"`)
- `Current Ratio` — from screener_ratios (key: `"current_ratio"`)
- `Promoter Holding` — from shareholding data (key: `"promoter_holding"`)
- `Price / Sales` — compute as `market_cap / revenue` if available

Check `backend/routers/stock.py` around line 396–434 for the full response dict to see which keys are available. Then pass them as props to `KeyFundamentals` from `frontend/app/stock/[symbol]/page.tsx` and add rows.

---

## COMPLETE TASK STATUS

| # | Task | Status | Files Changed |
|---|------|--------|---------------|
| 1 | AI Analysis pipeline timeout | ✅ FIXED | `backend/agents/orchestrator.py` |
| 2 | Knowledge graph visibility on analysis page | ⚠️ VERIFY after fix #1 — KG HTML needs to be generated | — |
| 3 | Announcements: top 10 most recent, correct dates | ✅ FIXED | `backend/routers/stock.py` |
| 4 | Financials: green/red YoY coloring on ALL columns | ✅ FIXED | `frontend/components/stock/FinancialsSection.tsx` |
| 5 | Technical indicators N/A values | ❌ NOT FIXED | `backend/services/technicals_service.py` |
| 6 | Stock price / open / close wrong | ✅ PARTIALLY FIXED (session TTL) | `backend/fetchers/nse_client.py` |
| 7 | Pink box on chart click (focus ring) | ❌ NOT FIXED | `frontend/components/stock/KnowledgeGraph.tsx`, `KnowledgeGraphClient.tsx` |
| 8 | KeyFundamentals empty space | ❌ NOT FIXED | `frontend/components/stock/KeyFundamentals.tsx`, stock page |

---

## REMAINING FIXES — EXACT STEPS (next session, no re-search needed)

### Step A — Technical indicators N/A (Task #5)
1. `grep -n "EMAIndicator\|ema_200\|window=200\|window=50" backend/services/technicals_service.py`
2. Read those specific lines (offset+limit, not full file)
3. Change `window=200` → `min(200, max(2, n-1))` etc. for all EMA windows
4. `grep -n "VolumeWeightedAveragePrice\|vwap" backend/services/technicals_service.py`
5. Add guard: `if volume.sum() == 0: pass` before VWAP calculation

### Step B — Pink focus box (Task #7)
1. Edit `frontend/components/stock/KnowledgeGraph.tsx` line ~392: add `outline: 'none'` to Canvas style
2. Edit `frontend/components/stock/KnowledgeGraphClient.tsx` line ~379: same

### Step C — KeyFundamentals fill (Task #8)
1. `grep -n "debt_to_equity\|current_ratio\|promoter\|peg_ratio" backend/routers/stock.py` to see what's already in the API response
2. Add those as props to `KeyFundamentals` in `frontend/app/stock/[symbol]/page.tsx`
3. Update `KeyFundamentals.tsx` interface + rows array

### Step D — Verify knowledge graph on analysis page (Task #2)
1. Start backend: `conda run -n stocxi uvicorn backend.main:app --port 8000`
2. Hit `GET /api/v2/analysis/RELIANCE?horizon=short&risk=moderate` — should now complete without timeout
3. Check if `graphify-out/stocks/RELIANCE/` directory has an HTML file generated
4. Click Knowledge Graph button on the analysis page — should load the iframe/HTML

---

## KEY FILES MAP (for next session)

| What | File | Key lines |
|------|------|-----------|
| Agent timeout | `backend/agents/orchestrator.py` | line 70 `AGENT_TIMEOUT_S` |
| NSE session refresh | `backend/fetchers/nse_client.py` | lines 45–68 `_get_nse()` |
| Announcements sort | `backend/routers/stock.py` | lines 700–714 |
| Financials coloring | `frontend/components/stock/FinancialsSection.tsx` | line 114 |
| Technicals N/A fix | `backend/services/technicals_service.py` | grep EMAIndicator, VWAP |
| Canvas focus ring | `frontend/components/stock/KnowledgeGraph.tsx` | line ~392 |
| Canvas focus ring | `frontend/components/stock/KnowledgeGraphClient.tsx` | line ~379 |
| KeyFundamentals | `frontend/components/stock/KeyFundamentals.tsx` | full file (78 lines) |
| Stock page props | `frontend/app/stock/[symbol]/page.tsx` | lines 84+ (KeyFundamentals render) |
| Price mapping | `backend/services/yfinance_service.py` | line 777 `"price": q["close"]` |

---

## IMPORTANT NOTES FOR NEXT SESSION
- Always use `conda run -n stocxi` for any Python command
- Cache key for announcements is now `v4` — old `v3` key will be re-fetched correctly
- The AI analysis pipeline timeout increase means requests will take up to 2 minutes — that's expected and correct
- The NSE price session refresh is 30 min — on first request after server restart, prices should be fresh
- Do NOT run `git add .` blindly — check what changed with `git diff`
All clean. All three remaining fixes are done:

  ┌─────┬────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   
  │  #  │          Fix           │                                                 What changed                                                 │
  ├─────┼────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 5   │ Technical indicators   │ technicals_service.py — added volume.sum() <= 0 guard before VWAP; silently skips instead of propagating NaN │ 
  │     │ VWAP N/A               │                                                                                                              │
  ├─────┼────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤   
  │ 7   │ Pink focus ring on     │ KnowledgeGraph.tsx:394 + KnowledgeGraphClient.tsx:381 — added outline: 'none' to Canvas style                │
  │     │ canvas click           │                                                                                                              │   
  ├─────┼────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤ 
  │ 8   │ KeyFundamentals empty  │ screener_service.py parses debt_to_equity + current_ratio from screener top-ratios; stock.py exposes both    │   
  │     │ space                  │ fields; types.ts typed; KeyFundamentals.tsx shows 10 rows (was 8); page.tsx wires new props                  │   
  └─────┴────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘


  All three tasks are done. Here's a summary of what was fixed:
                                           
  ---                                                                                                                                               
  Task 2 — DMA values wrong ✅                                                                                                                      
  - Root cause: NSE API returns unadjusted prices. ADANIPOWER had a 5:1 split (Sep 2025), mixing ~550 INR pre-split prices with ~220 INR post-split,
   inflating 200 EMA to 248.25.                                                                                                                     
  - Fix: ohlcv_service.py now runs _apply_split_adjustment() after normalization — detects day-over-day price jumps >2.5× and divides pre-split     
  prices by the detected factor.                                                                                                                  
  - Verified: 200-SMA now 152.98 (real: ~156.07), 50-SMA now 164.03 (real: ~163.83).                                                                
                                                                                                                                                  
  Task 3 — AI Analysis + Knowledge Graph ✅                                                                                                         
  - Root cause: The v2 orchestrator needed 10 technical + 8 fundamental + 3 announcement nodes — failed for most stocks. Also model ID            
  gemini-3.1-pro-preview doesn't exist.                                                                                                             
  - Fix: New simplified pipeline — simple_analysis_service.py runs fetch_phase1_data.py → builds KG HTML → calls Gemini (gemini-2.5-pro from      
  versions.yaml). New endpoint GET /api/v2/analysis/{symbol}/generate. Frontend rewrites as a client-side loader with step progress indicator and   
  renders the HTML in a sandboxed iframe. First-time analysis shows progress steps ("Fetching data…", "Building KG…", "Running AI…").               
                                                                                                                                     
  Task 1 — Announcement section bland ✅                                                                                                            
  - Fix: New announcement_summary_service.py makes a single batched Gemini Flash call per load to generate a 1-sentence investor-relevant summary   
  for all announcements. Frontend shows summary truncated at 120 chars with a "…read more" button to expand inline. Uses gemini-2.5-flash           
  (cheap/fast).                    