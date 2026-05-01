# Knowledge Graph Rebuild — Session Notes (2026-05-01)

## Current State

| Item | Status |
|---|---|
| Project root | ✅ Cleaned — all old graph files deleted |
| `data/` folder | ✅ Only `.md` files kept |
| BSE PE ratio bug | ✅ Fixed — now uses consolidated PE |
| `.md` format | ✅ Fixed — no truncated Summary field |
| `.md` parser | ✅ Done — `build_knowledge_graph.py --check` |
| HTML graph | ⏳ Next task |

---

## Bug Fixed: BSE PE Ratio

**File:** `backend/fetchers/bse_client.py`

**Problem:** RELIANCE PE was 44.2 (standalone) instead of 20.2 (consolidated).
BSE returns both `ConPE=20.22` and `PE=44.16`. The staleness guard only checked
`ConROE`/`ConPB` — both null for RELIANCE — so it fell through to standalone.

**Fix:** Added `ConPE` to the staleness guard:
```python
use_consolidated = (con_pe is not None) or (con_roe is not None) or (con_pb is not None)
```

**Verified:** RELIANCE now: PE=20.2, EPS=₹70.76 (consolidated).

---

## `.md` Format Fix

**File:** `fetch_phase1_data.py`

Removed `**Summary:**` line from fundamental and technical node blocks.
Old format had a truncated summary (split on decimal points like `20.2`).
New format matches reference files (`NAVA_data.md`, `NLCINDIA_data.md` etc.):

```markdown
### PE_Ratio
**Value:** PE: 20.2 | **Sentiment:** ➡️ neutral
**Analysis:** The PE ratio of 20.2 suggests a reasonable valuation... PE_Ratio relates to EPS, Revenue_Growth_YoY, Market_Cap.
```

---

## Parser: `build_knowledge_graph.py`

Reads `data/{SYMBOL}_data.md` and extracts all nodes.

**Usage:**
```bash
conda run -n stocxi python build_knowledge_graph.py RELIANCE --check
# prints all 120 nodes with value, sentiment, relates-to edges

conda run -n stocxi python build_knowledge_graph.py RELIANCE
# (HTML generation — Task 2, not yet built)
```

**RELIANCE output (verified):**
- 120 nodes total
- 📈 20 bullish · 📉 12 bearish · ➡️ 88 neutral
- 62 relates-to edge references
- All 10 sections populated

---

## Next Task: Build HTML Knowledge Graph

Extend `build_knowledge_graph.py` to generate `graphify-out/stocks/{SYMBOL}/{DATE}.html`.

### Node hierarchy to build:
```
HEAD::fundamental       ← category head node (1 per category)
HEAD::technical
HEAD::financial
HEAD::announcement
HEAD::news
HEAD::market_context
  └── GROUP::financial::Balance Sheet   ← sub-group (financial only)
  └── GROUP::financial::P&L
  └── GROUP::financial::Cash Flow
  └── GROUP::financial::Quarterly Result
  └── GROUP::financial::Share Holding
       └── RELIANCE|fundamental|PE_Ratio|2026-05-01   ← child node (one per ###)
```

### Node schema:
```json
{
  "id": "RELIANCE|fundamental|PE_Ratio|2026-05-01",
  "label": "PE_Ratio",
  "community": 0,
  "signal": "neutral",
  "value_text": "PE: 20.2",
  "context": "full analysis text",
  "weight": 1.5,
  "color": "#1e2230",
  "border_color": "#6B7280",
  "val": 6,
  "degree": 3,
  "node_type": "child",
  "parent": "HEAD::fundamental"
}
```

### Signal → color mapping:
| Signal | community | node bg | border |
|---|---|---|---|
| positive (📈) | 1 | `#1c3a2a` | `#00FF88` |
| negative (📉) | 2 | `#3a1c1c` | `#FF3355` |
| neutral (➡️) | 0 | `#1e2230` | `#6B7280` |
| mixed | 3 | `#2e2a10` | `#FFB800` |

### Edge types:
- `belongs_to` — child → HEAD (or GROUP → HEAD)
- `relates_to` — child → child (from "relates to X, Y" in Analysis text)

### Output path:
```
graphify-out/stocks/RELIANCE/2026-05-01.html
```

---

## Data Available in `data/`

| File | Status |
|---|---|
| `RELIANCE_data.md` | ✅ Fresh — re-fetched 2026-05-01, all values correct |
| `NAVA_data.md` | Old — needs re-fetch before building KG |
| `NLCINDIA_data.md` | Old — needs re-fetch |
| `ADANIENSOL_data.md` | Old — needs re-fetch |
| `ICICIAMC_data.md` | Old — needs re-fetch |
| `RPOWER_data.md` | Old — needs re-fetch |

Re-fetch any stock:
```bash
conda run -n stocxi python fetch_phase1_data.py NAVA long
```

---

## Files Modified This Session

| File | Change |
|---|---|
| `backend/fetchers/bse_client.py` | Fixed consolidated PE logic |
| `fetch_phase1_data.py` | Removed truncated Summary from fundamental/technical blocks |
| `build_knowledge_graph.py` | NEW — .md parser with --check mode |
| `data/RELIANCE_data.md` | Regenerated with correct values |
| `NEW_PROGRESS.md` | Updated with session log + next steps |
