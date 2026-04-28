# FIX_KNOWLEDGE_GRAPH.md — Knowledge Graph Redesign

> Created: 2026-04-28
> Status: READY FOR EXECUTION
> Priority: CRITICAL — knowledge graph is the core USP, current version is cartoonish and unreadable

---

## Problem Summary

The current knowledge graph visualization has these critical issues:

1. **Cartoonish design** — bright neon colors, additive-blending glow halos, pulsating animations. Looks like a game, not a professional stock analysis tool.
2. **No hierarchy** — all nodes are flat, same treatment. No head→child→verdict structure. User can't see what's important.
3. **Edges invisible** — particle trails too small/fast to show data flow direction. Can't read how data moves.
4. **Poor readability** — dark-on-dark labels, tiny text, excessive visual noise.
5. **Not stock-analysis-specific** — generic force-directed graph, not designed for financial data.

**Root cause:** The `_HTML_TEMPLATE` in `knowledge_graph.py` (lines 274-785) defines the entire visual design. `build_graph()` (lines 70-189) produces flat nodes with no hierarchy. Both need complete rewrite.

---

## Architecture (Unchanged)

- **Standalone HTML file** served from backend at `GET /api/v2/analysis/{symbol}/graph`
- `build_graph()` converts Nodes + admin_view + edges → graph dict
- `render_3d_html()` injects graph dict into HTML template
- 3D rendering uses `3d-force-graph@1.73.2` (Three.js-based, loaded from CDN)
- No frontend changes needed

---

## Design Decisions (Confirmed)

| Decision | Choice | Rationale |
|---|---|---|
| Architecture | Standalone HTML (keep same) | No frontend changes, works standalone |
| Verdict data source | From analysis result | LLM-computed verdicts are accurate |
| 3-finger gesture | Toggle auto-rotation | What 3d-force-graph natively supports |
| Background | Deep black `#0A0A0A` | Professional, Bloomberg-terminal aesthetic |
| Library | 3d-force-graph (keep) | Already in use, works well for this |

---

## Files to Modify

| File | Change | Priority |
|---|---|---|
| `backend/graph/knowledge_graph.py` | **Full rewrite** of `build_graph()` + `_HTML_TEMPLATE` | P0 |
| `backend/agents/orchestrator.py` | Update `build_graph()` call to pass verdict data from analysis result | P0 |
| `graphify-out/graph.html` | Delete old render | P1 |
| `graphify-out/graph3d.html` | Delete old render | P1 |
| `graphify-out/.graph3d_data.json` | Delete old data | P1 |

### Files NOT Modified (confirmed safe)

- `backend/graph/builder.py` — HFBP edge logic unchanged
- `backend/graph/stocxi_knowledge_graph.py` — lifecycle/serialization unchanged
- `backend/graph/hfbp.py` — propagation unchanged
- `backend/graph/scorer.py` — scoring unchanged
- `backend/schemas/node.py` — Node schema unchanged
- `backend/routers/v2_analysis.py` — endpoint unchanged
- Frontend — no changes needed (graph is standalone HTML)

---

## Task 1: Rewrite `build_graph()` — Hierarchical Node Structure

**File:** `backend/graph/knowledge_graph.py`, function `build_graph()` (lines 70-189)

### Current state
- All nodes are flat — same `community` ID per category, no parent/child relationship
- Verdicts injected from `admin_view["verdicts"]` as community=5
- No structural edges (belongs_to, informs) between head→child or head→verdict

### New node types

```
node_type: "head" | "child" | "verdict"
```

### 3 Tiers

| Tier | Type | Color | Shape | Size | Source |
|---|---|---|---|---|---|
| 1 | **Head** | White `#FFFFFF` | Circle with outer ring | Large (r=10-12) | 5 fixed category heads |
| 2 | **Child** | Gray `#6B7280` | Simple circle | Medium (r=4-7) | All data nodes |
| 3 | **Verdict** | Purple `#8B5CF6` | Hexagon | Large (r=8-10) | 5 verdicts from analysis result |

### 5 Head Nodes (always present)

| Head ID | Label | Category |
|---|---|---|
| `HEAD::technical` | Technical Indicators | technical |
| `HEAD::fundamental` | Fundamentals | fundamental |
| `HEAD::announcement` | Announcements | announcement |
| `HEAD::news` | News | news |
| `HEAD::financial` | Financial Statements | financial |

Note: "Financial" is a subset of "fundamental" category in the data model (financials_service nodes), but gets its own head node in the graph for visual clarity.

### Child Nodes

- Every existing data node gets `node_type: "child"` and `parent: "HEAD::{category}"`
- If category is `fundamental` and node name is in financials set (Revenue_Quarterly, Net_Profit_Quarterly, etc.), parent is `HEAD::financial`
- Signal color overlay on child nodes:
  - Positive/bullish → green border `#22C55E`
  - Negative/bearish → red border `#EF4444`
  - Neutral → default gray `#6B7280`
  - Mixed → amber border `#F59E0B`

### 5 Verdict Nodes

| Verdict ID | Label | Color |
|---|---|---|
| `VERDICT::technical` | Verdict: Technical | Purple `#8B5CF6` |
| `VERDICT::fundamental` | Verdict: Fundamental | Purple `#8B5CF6` |
| `VERDICT::announcement` | Verdict: Announcement | Purple `#8B5CF6` |
| `VERDICT::news` | Verdict: News | Purple `#8B5CF6` |
| `VERDICT::financial` | Verdict: Financial | Purple `#8B5CF6` |

Verdict signal text (bullish/bearish/neutral/mixed) and supporting_node_ids come from `admin_view["verdicts"]`.

### New Edge Types (visual only, added by build_graph)

| Relation | From → To | Color | Style | Meaning |
|---|---|---|---|---|
| `belongs_to` | Child → Head | `rgba(255,255,255,0.15)` | thin, solid | "This data point belongs to this category" |
| `informs` | Head → Verdict | `rgba(139,92,246,0.4)` | medium, solid | "This category informs this verdict" |
| `cross_category` | Head → Head | `rgba(255,255,255,0.08)` | thin, dashed | Cross-category relationship |

### HFBP Edge Types (already in builder.py, visual style change only)

| Relation | Arrow Color | Style |
|---|---|---|
| CONFIRMS | `#22C55E` (green) | solid, medium |
| AMPLIFIES | `#84CC16` (lime) | solid, thick, fast arrow |
| CONTRADICTS | `#EF4444` (red) | dashed, medium |
| DAMPENS | `#F97316` (orange) | thin dashed |
| CAUSES | `#EAB308` (gold) | solid, medium |
| TRIGGERS | `#FBBF24` (amber) | solid, thick, fast arrow |
| CONTEXTUALIZES | `#60A5FA` (blue) | thin, slow |
| CORRELATES | `#94A3B8` (gray) | faint, thin |

### communities array (replaces current 6 categories)

```javascript
[
  {"id": 0, "key": "head",       "name": "Head Nodes",        "color": "#FFFFFF"},
  {"id": 1, "key": "child",      "name": "Data Points",       "color": "#6B7280"},
  {"id": 2, "key": "verdict",    "name": "Verdicts",           "color": "#8B5CF6"},
]
```

### Mapping fundamentals → financial split

```python
_FINANCIAL_NODE_NAMES = frozenset([
    "Revenue_Quarterly", "Net_Profit_Quarterly", "Revenue_Annual",
    "Net_Profit_Annual", "Debt_To_Equity", "Operating_Cash_Flow",
    "EPS_Quarterly", "OPM_Quarterly", "Revenue_Growth", "Profit_Growth",
    "Cash_Flow", "Balance_Sheet",
])
```

Nodes with name in `_FINANCIAL_NODE_NAMES` get parent `HEAD::financial`. All other `fundamental` category nodes get parent `HEAD::fundamental`.

---

## Task 2: Rewrite `_HTML_TEMPLATE` — Professional Minimal Design

**File:** `backend/graph/knowledge_graph.py`, lines 274-785 (the entire `_HTML_TEMPLATE` string)

### Design Principles

- **Deep black background** (`#0A0A0A`)
- **Professional, minimal** — Bloomberg terminal / Refinitiv Eikon aesthetic
- **Clear visual hierarchy** — head nodes dominant, child nodes subordinate, verdicts distinct
- **Readable edges** — directional arrows with clear flow indication
- **No cartoonish effects** — no additive blending, no pulsating halos, no scan line, no glow rings

### Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ ┌─────────────┐                        ┌──────────────────────┐   │
│ │  Control     │                        │  Knowledge Graph    │   │
│ │  Panel       │       3D GRAPH         │                     │   │
│ │  (top-left)  │       AREA             │  RELIANCE · Short   │   │
│ │              │                        └──────────────────────┘   │
│ │ [Force]      │                                                  │
│ │ [Radial]     │                                                  │
│ │ [Hierarch.]  │                                                  │
│ │ [Edges]      │                                                  │
│ │ [Labels]     │                                                  │
│ │ [Reset]      │                                                  │
│ │ [Category ▾] │                                                  │
│ └─────────────┘                                                   │
│                                                                    │
│  ┌─ Hover Tooltip ──────────────┐                                 │
│  │ RSI_14                        │                                 │
│  │ Technical · Momentum          │                                 │
│  │───────────────────────────────│                                 │
│  │ Value:    72.4                │                                 │
│  │ Signal:   ● Positive         │                                 │
│  │ Context:  Overbought...      │                                 │
│  └───────────────────────────────┘                                 │
│                                                                    │
│  ┌─ Statistics ───────────────────────────────────────────────┐   │
│  │  42 Nodes  ·  167 Edges  ·  3 Groups                      │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### CSS Variables

```css
:root {
  --bg: #0A0A0A;
  --surface: #111827;
  --surface-hover: #1F2937;
  --border: rgba(255, 255, 255, 0.06);
  --border-focus: rgba(139, 92, 246, 0.4);
  --text: #E5E7EB;
  --text-secondary: #6B7280;
  --text-muted: #374151;
  --accent: #8B5CF6;
  --accent-hover: #7C3AED;
  --head-color: #FFFFFF;
  --child-color: #6B7280;
  --verdict-color: #8B5CF6;
  --positive: #22C55E;
  --negative: #EF4444;
  --neutral: #6B7280;
  --mixed: #F59E0B;
}
```

### Node Rendering (Three.js)

**Head node:**
```javascript
// Circle + outer ring, always show label
// Fill: white (#FFFFFF), Border: 2px white
// Size: r=10-12
// Outer ring: r*1.4, thin white border, no fill
// Label: always visible, white text, 11px Inter Medium, below node
```

**Child node:**
```javascript
// Simple circle, label on hover only
// Fill: #374151 (dark gray), Border: colored by signal
//   positive → #22C55E, negative → #EF4444, neutral → #4B5563, mixed → #F59E0B
// Size: r=4-7 (scaled by effective_weight)
// Label: hidden by default, shown on hover
```

**Verdict node:**
```javascript
// Hexagon shape, always show label
// Fill: #8B5CF6 (purple), Border: 2px #7C3AED
// Size: r=8-10
// Label: always visible, white text, 11px Inter Bold
// Signal badge: small colored dot below (green/red/gray/amber)
```

### Edge Rendering

Replace particle animations with **directional arrows**:

```javascript
// Arrow: thin line + small arrowhead at target
// Color: by relation type (see table above)
// Opacity: default 0.25, hover highlights connected edges to 0.7
// Flow direction: animated dash pattern moving source → target for:
//   CAUSES, TRIGGERS, AMPLIFIES (fast dash, 0.02s)
//   CONFIRMS, CONTEXTUALIZES (slow dash, 0.005s)
//   CONTRADICTS, DAMPENS (pulsing opacity, no dash)
//   belongs_to, informs, cross_category (static, very low opacity)
```

### Control Panel (top-left)

```html
<div id="controls" class="control-panel">
  <div class="control-title">Controls</div>
  <div class="control-group">
    <button onclick="setLayout('force')" class="active">Force</button>
    <button onclick="setLayout('radial')">Radial</button>
    <button onclick="setLayout('hierarchy')">Hierarchy</button>
  </div>
  <div class="control-group">
    <button onclick="toggleEdges()">Edges</button>
    <button onclick="toggleLabels()">Labels</button>
    <button onclick="resetCamera()">Reset</button>
  </div>
  <div class="control-group">
    <select onchange="filterCategory(this.value)">
      <option value="all">All Categories</option>
      <option value="technical">Technical</option>
      <option value="fundamental">Fundamental</option>
      <option value="financial">Financial</option>
      <option value="news">News</option>
      <option value="announcement">Announcements</option>
    </select>
  </div>
  <div class="control-group">
    <button onclick="takeScreenshot()">📸 Screenshot</button>
  </div>
</div>
```

### Header (top-center, above graph)

```html
<div id="header">
  <div class="header-title">Knowledge Graph</div>
  <div class="header-subtitle">__STOCK_NAME__ · __HORIZON__</div>
</div>
```

### Hover Tooltip (follows mouse)

```html
<div id="tooltip" class="tooltip hidden">
  <div class="tooltip-label">__NODE_LABEL__</div>
  <div class="tooltip-category">__CATEGORY__ · __SUBCATEGORY__</div>
  <div class="tooltip-divider"></div>
  <div class="tooltip-row"><span>Value</span><span>__VALUE__</span></div>
  <div class="tooltip-row"><span>Signal</span><span class="tooltip-signal __SIGNAL_CLASS__">__SIGNAL__</span></div>
  <div class="tooltip-row"><span>Context</span><span>__CONTEXT__</span></div>
  <div class="tooltip-row"><span>Weight</span><span>__WEIGHT__</span></div>
</div>
```

CSS for tooltip: `position: fixed`, glassmorphic background `rgba(17,24,39,0.95)`, backdrop-filter blur, border `rgba(255,255,255,0.06)`, max-width 280px.

### Touch/Gesture Support

- **2-finger pinch**: Zoom (native browser/CSS `touch-action: pan-x pan-y`, handled by Three.js OrbitControls)
- **3-finger**: Toggle `autoRotate` on/off. On toggle:
  - If autoRotate was OFF → turn ON with speed 0.5, smooth transition
  - If autoRotate was ON → turn OFF
- **Single tap**: Highlight node + connected edges, center camera, show tooltip
- **Click background**: Clear highlight, hide tooltip

JavaScript for 3-finger detection:
```javascript
let touchCount = 0;
canvas.addEventListener('touchstart', (e) => { touchCount = e.touches.length; });
canvas.addEventListener('touchend', () => { touchCount = 0; });
canvas.addEventListener('touchmove', (e) => {
  if (e.touches.length === 3) {
    e.preventDefault();
    rotating = !rotating;
    Graph.controls().autoRotate = rotating;
  }
});
```

### Layout Modes

**Force (default):** Standard 3d-force-graph force-directed layout. Heads cluster naturally.

**Radial:** Heads in a ring (5 heads at 72° intervals). Children orbit their head. Verdicts outside the ring, connected to their respective heads.

**Hierarchy:** Heads at top (y=200). Children below their head (y=0 to -100, spread along x). Verdicts at bottom (y=-300). Clear top→bottom flow.

```javascript
function setLayout(mode) {
  layoutMode = mode;
  if (mode === 'radial') { /* position heads in ring, children orbit */ }
  else if (mode === 'hierarchy') { /* heads top, children middle, verdicts bottom */ }
  else { /* force: delete fx/fy/fz */ }
  Graph.graphData(D);
}
```

### Statistics Bar (bottom-center)

```html
<div id="stats">
  <span><strong id="sn">0</strong> Nodes</span>
  <span>·</span>
  <span><strong id="se">0</strong> Edges</span>
  <span>·</span>
  <span><strong id="sc">0</strong> Groups</span>
</div>
```

---

## Task 3: Update `render_3d_html()` Signature

**File:** `backend/graph/knowledge_graph.py`, function `render_3d_html()` (lines 192-207)

### Current signature
```python
def render_3d_html(
    graph_data: dict[str, Any],
    title: str = "Stocxi Knowledge Graph",
    output_path: str | Path | None = None,
) -> str:
```

### New signature
```python
def render_3d_html(
    graph_data: dict[str, Any],
    title: str = "Stocxi Knowledge Graph",
    stock_name: str = "",
    horizon: str = "",
    output_path: str | Path | None = None,
) -> str:
```

The `stock_name` and `horizon` parameters are needed for the header subtitle ("RELIANCE · Short-term").

In the HTML template, replace `__TITLE__` with separate `__STOCK_NAME__` and `__HORIZAN__` placeholders:
```python
html = (
    _HTML_TEMPLATE
    .replace("__GRAPH_DATA__", data_json)
    .replace("__STOCK_NAME__", stock_name)
    .replace("__HORIZAN__", horizon_display)
)
```

Where `horizon_display` maps:
```python
_HORIZON_DISPLAY = {"short": "Short-term", "medium": "Medium-term", "long": "Long-term"}
```

---

## Task 4: Update Orchestrator to Pass Verdict Data

**File:** `backend/agents/orchestrator.py`, around line 300

### Current code
```python
if kg is not None:
    G = build_graph(all_nodes, admin_view, edges=kg._edges)
```

### New code
```python
if kg is not None:
    G = build_graph(
        all_nodes,
        admin_view,
        edges=kg._edges,
        effective_weights=kg._effective_weights,
        horizon=horizon,
    )
```

And update the `render_3d_html` call:
```python
render_3d_html(
    G,
    title=f"Stocxi — {request.stock}",
    stock_name=request.stock,
    horizon=horizon,
    output_path=graph_path,
)
```

---

## Task 5: Clean Up Old Graph Files

Delete these files (they're old renders that could confuse the LLM):
- `graphify-out/graph.html`
- `graphify-out/graph3d.html`
- `graphify-out/.graph3d_data.json`
- `graphify-out/.graphify_chunk_01.json`
- `graphify-out/.graphify_ast.json`
- `graphify-out/.graphify_cached.json`
- `graphify-out/.graphify_detect.json`
- `graphify-out/.graphify_uncached.txt`

Also check and clean worktree copies under `.claude/worktrees/*/graphify-out/`.

---

## Task 6: Update `build_graph()` Function Signature

**File:** `backend/graph/knowledge_graph.py`, function `build_graph()` (lines 70-189)

### Current signature
```python
def build_graph(
    nodes: list[Any],
    admin_view: dict[str, Any] | None = None,
    edges: list[Any] | None = None,
    effective_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
```

### New signature
```python
def build_graph(
    nodes: list[Any],
    admin_view: dict[str, Any] | None = None,
    edges: list[Any] | None = None,
    effective_weights: dict[str, float] | None = None,
    horizon: str = "short",
) -> dict[str, Any]:
```

### Implementation Pseudocode

```python
def build_graph(nodes, admin_view, edges, effective_weights, horizon):
    admin_view = admin_view or {}
    ew = effective_weights or {}

    graph_nodes = []
    graph_links = []
    node_ids = set()

    # ── 1. Create 5 HEAD nodes ──────────────────────────────
    head_ids = {}
    for head_id, head_label, head_category in [
        ("HEAD::technical", "Technical Indicators", "technical"),
        ("HEAD::fundamental", "Fundamentals", "fundamental"),
        ("HEAD::announcement", "Announcements", "announcement"),
        ("HEAD::news", "News", "news"),
        ("HEAD::financial", "Financial Statements", "financial"),
    ]:
        graph_nodes.append({
            "id": head_id,
            "label": head_label,
            "community": 0,  # head community
            "signal": "neutral",
            "value_text": "",
            "context": "",
            "weight": 3.0,
            "effective_weight": None,
            "color": "#FFFFFF",
            "val": 12,  # large
            "degree": 0,
            "source_file": f"{head_category} · head",
            "node_type": "head",
        })
        node_ids.add(head_id)
        head_ids[head_category] = head_id

    # ── 2. Create CHILD nodes ───────────────────────────────
    for node in nodes:
        nid = node.node_id
        cat = str(node.category.value if hasattr(node.category, "value") else node.category)
        sig = str(node.signal.value if hasattr(node.signal, "value") else node.signal) if hasattr(node, "signal") else "neutral"
        val = str(getattr(node, "value", ""))
        ctx = str(getattr(node, "context", "") or "")
        wt = float(getattr(node, "weight", 1.0))

        # Determine parent head
        if cat == "fundamental" and node.name in _FINANCIAL_NODE_NAMES:
            parent = "HEAD::financial"
        elif cat == "context":
            parent = None  # context nodes float free
        else:
            parent = head_ids.get(cat, head_ids.get("fundamental"))

        # Signal color for child node border
        sig_color = _SIGNAL_BORDER.get(sig, "#4B5563")

        ew_val = ew.get(nid, 0)
        visual_val = max(4, min(8, (ew_val * 6 + 4) if ew_val > 0 else (math.log1p(wt * 80) * 3)))

        graph_nodes.append({
            "id": nid,
            "label": _short_label(nid),
            "community": 1,  # child community
            "signal": sig,
            "value_text": val[:200],
            "context": ctx[:350],
            "weight": round(wt, 3),
            "effective_weight": round(ew_val, 4) if ew_val else None,
            "color": "#374151",  # dark gray fill
            "border_color": sig_color,  # signal-colored border
            "val": round(visual_val, 2),
            "degree": 0,
            "source_file": f"{cat} · {sig}",
            "node_type": "child",
            "parent": parent,
        })
        node_ids.add(nid)

        # belongs_to edge: child → head
        if parent:
            graph_links.append({
                "source": nid,
                "target": parent,
                "type": "belongs_to",
                "color": "rgba(255,255,255,0.10)",
            })

    # ── 3. Create VERDICT nodes ─────────────────────────────
    verdicts_raw = admin_view.get("verdicts", {})
    verdicts_list = (
        [{"category": cat, **v} for cat, v in verdicts_raw.items()]
        if isinstance(verdicts_raw, dict) else verdicts_raw
    )
    verdict_cats = {
        "technical": "HEAD::technical",
        "fundamental": "HEAD::fundamental",
        "announcement": "HEAD::announcement",
        "news": "HEAD::news",
        "financial": "HEAD::financial",
    }

    for verdict in verdicts_list:
        cat_name = verdict.get("category", "unknown")
        vid = f"VERDICT::{cat_name}"
        vsig = verdict.get("direction", verdict.get("signal", "neutral"))

        graph_nodes.append({
            "id": vid,
            "label": f"Verdict: {cat_name.title()}",
            "community": 2,  # verdict community
            "signal": vsig,
            "value_text": vsig.upper(),
            "context": "",
            "weight": 2.5,
            "effective_weight": None,
            "color": "#8B5CF6",
            "val": 10,
            "degree": 0,
            "source_file": f"verdict · {cat_name}",
            "node_type": "verdict",
        })
        node_ids.add(vid)

        # informs edge: head → verdict
        parent_head = verdict_cats.get(cat_name, head_ids.get(cat_name))
        if parent_head and parent_head in node_ids:
            graph_links.append({
                "source": parent_head,
                "target": vid,
                "type": "informs",
                "color": "rgba(139,92,246,0.4)",
            })

        # supporting_node_ids → verdict edges
        for support_nid in verdict.get("supporting_node_ids", []):
            if support_nid in node_ids:
                graph_links.append({
                    "source": support_nid,
                    "target": vid,
                    "type": "informs",
                    "color": "rgba(139,92,246,0.25)",
                })

    # ── 4. Add HFBP edges ───────────────────────────────────
    if edges:
        for edge in edges:
            src = edge.from_id if hasattr(edge, "from_id") else str(edge.get("from_id", ""))
            tgt = edge.to_id if hasattr(edge, "to_id") else str(edge.get("to_id", ""))
            rel = edge.relation if hasattr(edge, "relation") else str(edge.get("relation", "same_domain"))
            if src in node_ids and tgt in node_ids:
                style = _EDGE_STYLE.get(rel, _EDGE_STYLE.get("CORRELATES"))
                graph_links.append({
                    "source": src,
                    "target": tgt,
                    "type": rel,
                    "color": style["color"],
                    "eweight": float(getattr(edge, "weight", 1.0)),
                })

    # ── 5. Head → Head cross_category edges ─────────────────
    head_list = list(head_ids.values())
    for i, h1 in enumerate(head_list):
        for h2 in head_list[i+1:]:
            graph_links.append({
                "source": h1,
                "target": h2,
                "type": "cross_category",
                "color": "rgba(255,255,255,0.06)",
            })

    # ── 6. Verdict → other Verdict edges ────────────────────
    verdict_ids = [n["id"] for n in graph_nodes if n["node_type"] == "verdict"]
    for i, v1 in enumerate(verdict_ids):
        for v2 in verdict_ids[i+1:]:
            graph_links.append({
                "source": v1,
                "target": v2,
                "type": "cross_category",
                "color": "rgba(139,92,246,0.15)",
            })

    # ── 7. Compute degrees ──────────────────────────────────
    degree = {n["id"]: 0 for n in graph_nodes}
    for lnk in graph_links:
        degree[lnk["source"]] = degree.get(lnk["source"], 0) + 1
        degree[lnk["target"]] = degree.get(lnk["target"], 0) + 1
    for n in graph_nodes:
        n["degree"] = degree.get(n["id"], 0)

    return {
        "nodes": graph_nodes,
        "links": graph_links,
        "communities": [
            {"id": 0, "key": "head", "name": "Head Nodes", "color": "#FFFFFF"},
            {"id": 1, "key": "child", "name": "Data Points", "color": "#6B7280"},
            {"id": 2, "key": "verdict", "name": "Verdicts", "color": "#8B5CF6"},
        ],
        "meta": {"node_count": len(graph_nodes), "edge_count": len(graph_links)},
    }
```

### Signal border color map

```python
_SIGNAL_BORDER = {
    "bullish": "#22C55E",
    "positive": "#22C55E",
    "bearish": "#EF4444",
    "negative": "#EF4444",
    "neutral": "#4B5563",
    "mixed": "#F59E0B",
}
```

---

## Task 7: End-to-End Test

After all changes, run:

```bash
conda run -n stocxi python -c "
import asyncio
from datetime import date
from backend.agents.orchestrator import run
from backend.schemas.messages import FetchRequest, UserProfile, Horizon, Risk

async def test():
    req = FetchRequest(
        stock='BAJAJ-AUTO',
        as_of_date=date.today(),
        profile=UserProfile(horizon=Horizon('short'), risk=Risk('moderate'), sector=''),
        request_id='kg-test-001',
    )
    result, admin = await run(req)
    print(f'Signal: {result.overall_signal}')
    print(f'Confidence: {result.calibrated_confidence}')
    print(f'KG nodes: {admin.get(\"graph_node_count\", \"N/A\")}')
    print(f'KG edges: {admin.get(\"graph_edge_count\", \"N/A\")}')
    print(f'Graph path: {admin.get(\"knowledge_graph_path\", \"N/A\")}')
    print('E2E pipeline works')

asyncio.run(test())
"
```

Then verify:
```bash
conda run -n stocxi uvicorn backend.main:app --reload --port 8000
# Browser: http://localhost:8000/api/v2/analysis/BAJAJ-AUTO/graph
```

Check:
- [ ] Head nodes appear (white, large)
- [ ] Child nodes cluster under heads (gray, smaller)
- [ ] Verdict nodes appear (purple hexagons)
- [ ] Edges show data flow direction with arrows
- [ ] Hover tooltip shows value, context, signal
- [ ] Deep black background
- [ ] Header shows "Knowledge Graph" + stock name
- [ ] Control panel works (layout, edges, labels, reset, category filter)
- [ ] 2-finger zoom works
- [ ] 3-finger toggles rotation
- [ ] Category filter isolates one head + its children + verdict

---

## Execution Order

1. Rewrite `build_graph()` in `knowledge_graph.py` (Task 6)
2. Rewrite `_HTML_TEMPLATE` in `knowledge_graph.py` (Task 2)
3. Update `render_3d_html()` signature (Task 3)
4. Update orchestrator call (Task 4)
5. Delete old graph files (Task 5)
6. E2E test (Task 7)

Tasks 1-3 are all in the same file, should be done together.
Task 4 is a small change in orchestrator.
Task 5 is just file deletion.
Task 6 is the main implementation work — the `build_graph()` rewrite + HTML template rewrite.

---

## Key Context for New Session

1. **The knowledge graph is the CORE product USP** — this is not a cosmetic tweak, it's a fundamental redesign.

2. **The HTML template is 785 lines of embedded JS/CSS** in `knowledge_graph.py` — it must be completely rewritten, not patched.

3. **`build_graph()` produces the data that feeds the template** — it must be rewritten to produce hierarchical nodes (head/child/verdict) instead of flat nodes.

4. **The orchestrator** (lines 294-326) calls `build_graph()` and `render_3d_html()` — these call signatures need minor updates to pass `horizon` and `stock_name`.

5. **The backend serves the graph at** `GET /api/v2/analysis/{symbol}/graph` — this endpoint is unchanged.

6. **The current 3d-force-graph library works** — keep it, just change how we use it (node rendering, edge rendering, layout).

7. **Verdict data comes from `admin_view["verdicts"]`** — a dict keyed by category with `direction` and `supporting_node_ids` fields.

8. **Node signal data already exists** — every Node has `signal` (positive/negative/neutral) and `value` and `context` fields.

9. **HFBP edge types (CONFIRMS, AMPLIFIES, etc.)** are already built by `builder.py` — we just need to style them differently in the template.

10. **The `_HTML_TEMPLATE` uses CDN-loaded dependencies:**
    - `three@0.158.0` from unpkg CDN
    - `3d-force-graph@1.73.2` from unpkg CDN
    - These should be kept for simplicity.

---

*This file is the single source of truth for the knowledge graph redesign. Update NEW_PROGRESS.md after completion.*