# Knowledge Graph Visualization Rebuild — Design Document

> **Status:** Draft  
> **Date:** 2026-04-30  
> **Author:** AI Agent  
> **Scope:** Phase 1 — Core architecture + 4 layouts + focus mode  

---

## 1. Problem Statement

The current knowledge graph visualization (`graphify-out/stocks/*/*.html`) has critical UX issues:

1. **No real hierarchy** — Nodes have `community` IDs but no explicit parent/child structure. Clicking a head node shows a flat highlight, not a tree.
2. **Broken layouts** — Force layout is chaotic; Radial and Tree are not implemented correctly (positions are random offsets, not computed layouts).
3. **No focus mode** — Cannot drill into a specific category (e.g., "show me only Financial nodes and their relationships").
4. **Focus mode is buggy** — When clicking a head node, child nodes don't maintain proper spatial relationships; background nodes clutter the view.
5. **No organizing principle** — Per Neo4j best practices, a knowledge graph needs a clear hierarchy: **Head → Group → Child → Verdict**.

---

## 2. Design Goals

| # | Goal | Success Metric |
|---|---|---|
| 1 | **Explicit hierarchy** | Every node has a clear parent; tree is traversable |
| 2 | **Crystal-clear layouts** | Each layout mode positions nodes deterministically |
| 3 | **Focus/drill-down** | Click any head → see only that subtree, background fades |
| 4 | **Multiple views** | 4 layout engines: Force, Radial, Tree, Orbit |
| 5 | **Professional aesthetic** | Bloomberg-terminal dark theme, no cartoonish effects |
| 6 | **Performance** | 60fps with 200+ nodes on modern laptops |

---

## 3. Architecture — Two-Layer Design

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER (Python)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Node Tree    │  │ Edge Index   │  │ Focus State  │      │
│  │ Builder      │  │ (adjacency)  │  │ Manager      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└──────────────────────────┬──────────────────────────────────┘
                           │ JSON export
┌──────────────────────────▼──────────────────────────────────┐
│                 LAYOUT LAYER (JavaScript)                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │ Force      │ │ Radial     │ │ Tree       │              │
│  │ Engine     │ │ Engine     │ │ Engine     │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│  ┌────────────┐                                             │
│  │ Orbit      │  ← All engines implement same interface     │
│  │ Engine     │     computeLayout(tree, focusNode) → positions│
│  └────────────┘                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ position arrays
┌──────────────────────────▼──────────────────────────────────┐
│                RENDER LAYER (Three.js)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Scene Graph  │  │ Node Meshes  │  │ Edge Lines   │      │
│  │ Camera       │  │ Materials    │  │ Particles    │      │
│  │ Controls     │  │ Labels       │  │ Animations   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** Layout and rendering are decoupled. We compute positions first, then render. This enables smooth transitions between layouts and focus modes.

---

## 4. Data Layer — Hierarchical Tree Builder

### 4.1 Node Hierarchy Schema

Every node belongs to a strict tree:

```
STOCK (root)
├── HEAD::technical
│   ├── GROUP::technical::Momentum
│   │   ├── RSI_14
│   │   ├── MACD
│   │   └── Stochastic_K
│   ├── GROUP::technical::Trend
│   │   ├── SMA_20
│   │   ├── SMA_50
│   │   └── EMA_12
│   └── GROUP::technical::Volatility
│       ├── Bollinger_Upper
│       └── ATR_14
├── HEAD::fundamental
│   ├── GROUP::fundamental::Valuation
│   │   ├── PE_Ratio
│   │   └── PB_Ratio
│   └── GROUP::fundamental::Profitability
│       ├── ROE
│       └── EPS
├── HEAD::financial
│   ├── GROUP::financial::Balance Sheet
│   │   ├── Total_Assets
│   │   └── Debt_To_Equity
│   ├── GROUP::financial::P&L
│   │   ├── Revenue_TTM
│   │   └── PAT_TTM
│   └── GROUP::financial::Cash Flow
│       ├── Operating_Cash_Flow
│       └── Free_Cashflow
├── HEAD::news
│   ├── News_Item_1
│   ├── News_Item_2
│   └── ...
├── HEAD::announcement
│   ├── Board_Meeting
│   ├── Dividend_Declared
│   └── ...
└── VERDICTS
    ├── VERDICT::technical
    ├── VERDICT::fundamental
    └── VERDICT::overall
```

### 4.2 Python Tree Builder

```python
# backend/graph/tree_builder.py

@dataclass
class TreeNode:
    id: str
    label: str
    node_type: Literal["root", "head", "group", "child", "verdict"]
    parent_id: str | None
    children: list[str]           # child node IDs
    depth: int                    # 0=root, 1=head, 2=group, 3=child
    data: dict[str, Any]          # original node properties
    
class NodeTree:
    """Hierarchical tree for knowledge graph visualization."""
    
    def __init__(self, nodes: list[Node], edges: list[Edge]):
        self._nodes: dict[str, TreeNode] = {}
        self._root_id = "ROOT"
        self._build_tree(nodes, edges)
    
    def _build_tree(self, nodes, edges):
        # 1. Create root
        # 2. Create 5 head nodes
        # 3. Group children by category + subgroup
        # 4. Build adjacency index for edges
        pass
    
    def get_subtree(self, node_id: str) -> list[str]:
        """Return node_id + all descendants."""
        pass
    
    def get_focus_positions(self, focus_id: str) -> dict[str, tuple[float, float, float]]:
        """Compute positions for focus mode. Focus node at center, descendants in concentric rings."""
        pass
```

### 4.3 Edge Types in Tree Context

| Edge Type | Connects | Visual Treatment |
|---|---|---|
| `belongs_to` | child → parent/group | Thin, white, 20% opacity |
| `informs` | child/head → verdict | Medium, gold, dashed |
| `CONFIRMS` | peer → peer | Green, animated particles |
| `AMPLIFIES` | peer → peer | Bright green, thick, fast particles |
| `CONTRADICTS` | peer → peer | Red, dashed, animated |
| `DAMPENS` | peer → peer | Orange, thin, dashed |
| `CAUSES` | news/ann → child | Blue, medium |
| `TRIGGERS` | news/ann → child | Purple, thick, fast |
| `CONTEXTUALIZES` | context → child | Gray, very thin |
| `cross_category` | head ↔ head | Almost invisible, structural only |

---

## 5. Layout Engines

All engines implement:

```typescript
interface LayoutEngine {
  name: string;
  computeLayout(tree: NodeTree, focusNodeId?: string): NodePositions;
}

type NodePositions = Map<string, {x: number, y: number, z: number}>;
```

### 5.1 Force Engine

**Purpose:** Organic exploration mode  
**Algorithm:** D3-force-3d with custom forces:

- `charge`: -300 (repulsion)
- `link`: distance varies by edge type (belongs_to=30, CONFIRMS=80, cross_category=200)
- `center`: pulls root to origin
- `collision`: radius = node.val * 2.5
- `y-force`: pulls heads to y=+150, groups to y=0, children to y=-100 (subtle vertical stratification)

**Focus mode:** Freeze focus node at origin. Descendants in sphere(r=120). Background nodes pushed to z=-800.

### 5.2 Radial Engine

**Purpose:** See all categories at a glance  
**Algorithm:**

- Root at center
- Heads on inner ring (R=150)
- Groups on middle ring (R=280)
- Children on outer ring (R=420)
- Verdicts below (y=-200, R=300)

Angular distribution:
- Divide 360° by number of heads
- Each head gets a sector
- Within sector: groups evenly spaced, children evenly spaced within group arcs

**Focus mode:** Selected head moves to center. Its groups in inner ring (R=100). Its children in outer ring (R=220). Other heads fade to 5% and move to R=600.

### 5.3 Tree Engine

**Purpose:** Clear hierarchy reading  
**Algorithm:** Reingold-Tilford tree layout (D3-hierarchy):

- Root at top center
- Heads on level 1 (y = +180)
- Groups on level 2 (y = 0)
- Children on level 3 (y = -160)
- Verdicts on level 4 (y = -320)

Horizontal spacing:
- Each level's nodes evenly distributed across viewport width
- Sibling subtrees don't overlap

**Focus mode:** Selected head becomes the new "root". Its subtree expands to fill viewport. Other nodes collapsed to a single "..." ghost node at the side.

### 5.4 Orbit Engine

**Purpose:** Dynamic, engaging view  
**Algorithm:**

- Heads are "planets" orbiting the sun (root) at different radii and speeds
- Groups are "moons" orbiting their parent head
- Children are "satellites" orbiting their group
- Each orbit plane is slightly tilted (random seed per stock for determinism)

Animation:
- Continuous slow rotation (0.1-0.3 rad/s)
- Nodes on same orbit have same angular velocity
- Focus mode: selected head becomes the sun, its moons/satellites orbit it; other planets pushed to outer orbits (R=800)

---

## 6. Focus / Drill-Down System

### 6.1 Focus States

| State | Behavior |
|---|---|
| `GLOBAL` | Full graph, all nodes visible |
| `HEAD_FOCUS` | Selected head + descendants highlighted. Background at 3% opacity, pushed to z=-1000 |
| `GROUP_FOCUS` | Selected group + children highlighted. Parent head visible but dimmed |
| `NODE_FOCUS` | Selected node + direct neighbors highlighted |

### 6.2 Focus Transition Animation

```
1. User clicks a head node
2. Compute new positions for focus mode (via active layout engine)
3. Animate all nodes to new positions over 600ms (easing: cubic-out)
4. Simultaneously: background nodes fade to 3% opacity
5. Camera smoothly zooms to focus on selected subtree
6. Focus node gets a pulsing glow ring
```

### 6.3 Background Node Treatment in Focus Mode

- **Opacity:** 3% (nearly invisible but still present for context)
- **Position:** Pushed to z = -1200 (behind the focus cluster)
- **Edges:** Only edges within the focus subtree are visible; cross-edges to background nodes are hidden
- **Labels:** Hidden

---

## 7. Render Layer (Three.js)

### 7.1 Scene Setup

```
Scene
├── AmbientLight (0.4 intensity)
├── DirectionalLight (0.6, from top-right)
├── Node Group
│   ├── Head Nodes (large icosahedrons, white)
│   ├── Group Nodes (medium spheres, category-colored)
│   ├── Child Nodes (small spheres, signal-colored border)
│   └── Verdict Nodes (hexagonal prisms, purple)
├── Edge Group
│   ├── belongs_to lines (thin, white, low opacity)
│   ├── CONFIRMS/AMPLIFIES (green, animated particles)
│   ├── CONTRADICTS/DAMPENS (red/orange, dashed)
│   └── CAUSES/TRIGGERS (blue/purple, animated)
└── Label Group (CanvasTextures as Sprites, shown on hover/click)
```

### 7.2 Node Materials

| Type | Geometry | Material | Size |
|---|---|---|---|
| Root | None (invisible anchor) | — | — |
| Head | Icosahedron (detail=2) | MeshPhysicalMaterial, white, metalness=0.3 | radius=14 |
| Group | Sphere (32 segments) | MeshPhysicalMaterial, category color, metalness=0.2 | radius=9 |
| Child | Sphere (24 segments) | MeshPhysicalMaterial, gray fill + signal-colored emissive border | radius=5-7 (by weight) |
| Verdict | Extruded hexagon | MeshPhysicalMaterial, purple, emissive=0.2 | radius=11 |

### 7.3 Edge Rendering

- **Straight lines** for `belongs_to` and `informs`
- **Curved arcs** (Bezier) for cross-node relationships
- **Animated particles** traveling along edges for CONFIRMS/AMPLIFIES/TRIGGERS
- **Dashed lines** for CONTRADICTS/DAMPENS (via shader or texture)

### 7.4 Label System

- **Default:** No labels (too cluttered)
- **Hover:** Show tooltip with node details (rich HTML overlay)
- **Click:** Show persistent label on focus node + direct neighbors
- **Toggle:** "Labels" button shows all labels for current focus set

---

## 8. UI/UX Design

### 8.1 Sidebar Layout (Right Side)

```
┌──────────────────────────────────┐
│  Stocxi                          │
│  RELIANCE — Long-term Analysis   │
├──────────────────────────────────┤
│  [Search nodes...]               │
├──────────────────────────────────┤
│  LAYOUT: [Force ▼]               │
│  ┌────────┬────────┬────────┐    │
│  │ Force  │ Radial │ Tree   │    │
│  │        │        │        │    │
│  └────────┴────────┴────────┘    │
│  [Orbit]                         │
├──────────────────────────────────┤
│  FOCUS:                          │
│  [All] [Technical] [Fundamental] │
│  [Financial] [News] [Announ...]  │
├──────────────────────────────────┤
│  NODE INFO                       │
│  ─────────────────────────────   │
│  RSI_14                          │
│  Technical · Neutral             │
│  RSI: 52.3                       │
│  Balanced momentum...            │
│  Weight: 0.08 | 10 links         │
├──────────────────────────────────┤
│  DISPLAY:                        │
│  [Labels] [Edges] [Particles]    │
│  [Rotate]                        │
├──────────────────────────────────
│  LEGEND                          │
│  ● Technical (23)                │
│  ● Fundamental (15)              │
│  ● Financial (12)                │
│  ● News (8)                      │
│  ● Announcements (5)             │
├──────────────────────────────────┤
│  63 Nodes · 142 Edges · 5 Groups │
└──────────────────────────────────┘
```

### 8.2 Color Scheme

```css
:root {
  --bg: #050508;
  --surface: #0a0a10;
  --surface-hover: #12121a;
  --border: rgba(255,255,255,0.06);
  --text: #e8e8f0;
  --text-secondary: #7a7a8a;
  --text-muted: #4a4a5a;
  
  --accent: #6366f1;           /* indigo */
  --accent-hover: #818cf8;
  
  /* Category colors */
  --technical: #3b82f6;        /* blue */
  --fundamental: #10b981;      /* emerald */
  --financial: #f59e0b;        /* amber */
  --news: #ec4899;             /* pink */
  --announcement: #8b5cf6;     /* violet */
  --verdict: #a855f7;          /* purple */
  
  /* Signal colors */
  --positive: #00e676;
  --negative: #ff5252;
  --neutral: #78909c;
  --mixed: #ffab40;
}
```

### 8.3 Interaction Model

| Action | Response |
|---|---|
| Click head node | Enter HEAD_FOCUS mode for that category |
| Click group node | Enter GROUP_FOCUS mode |
| Click child node | Enter NODE_FOCUS mode (highlights neighbors) |
| Click background | Exit focus mode → GLOBAL |
| Hover any node | Show tooltip with details |
| Drag | Rotate camera |
| Scroll | Zoom in/out |
| Right-click drag | Pan camera |
| Layout button | Animate transition to new layout |
| Focus button | Animate transition to focus view |

---

## 9. Implementation Plan

### Phase 1A: Data Layer (Day 1)

1. `backend/graph/tree_builder.py` — Build hierarchical tree from nodes + edges
2. `backend/graph/layout_data.py` — Export tree + positions as JSON
3. Update `backend/graph/knowledge_graph.py` — Use new tree structure

### Phase 1B: JavaScript Architecture (Day 2)

1. `frontend/public/kg-renderer/` (or inline in HTML template):
   - `tree.js` — Node tree data structure
   - `layouts/force.js` — Force layout engine
   - `layouts/radial.js` — Radial layout engine
   - `layouts/tree.js` — Tree layout engine
   - `layouts/orbit.js` — Orbit layout engine
   - `renderer.js` — Three.js scene manager
   - `focus.js` — Focus state manager
   - `ui.js` — Sidebar UI controller
   - `main.js` — Entry point

### Phase 1C: Integration (Day 3)

1. Update `render_3d_html()` in `knowledge_graph.py` to output new template
2. Wire focus mode into click handlers
3. Add layout transition animations
4. Test with BAJAJ-AUTO data

### Phase 1D: Polish (Day 4)

1. Edge particle animations
2. Hover tooltip improvements
3. Mobile responsiveness (hide sidebar on small screens)
4. Performance optimization (LOD for distant nodes)

---

## 9.5 Node Data Schema (Per Type)

Each node stores data fields based on its category. This schema is used for both visualization (tooltip, sidebar) and LLM analysis (Gemini prompt).

### 9.5.1 Financial Ratio Child Nodes

| Field | Type | Description |
|---|---|---|
| `value` | string | Raw metric value (e.g., "PE: 24.5") |
| `context` | string | Summary of what this value means for THIS specific stock |
| `impact` | enum | `positive` / `negative` / `neutral` — interpreted impact on stock outlook |

Example:
```json
{
  "value": "PE: 24.5",
  "context": "PE of 24.5 is below sector average of 28.1, suggesting potential undervaluation relative to peers",
  "impact": "positive"
}
```

### 9.5.2 Technical Indicator Child Nodes

| Field | Type | Description |
|---|---|---|
| `value` | string | Raw indicator reading (e.g., "RSI: 72.3") |
| `context` | string | Summary of what this reading means for THIS specific stock's price action |
| `impact` | enum | `positive` / `negative` / `neutral` — signal direction |

Example:
```json
{
  "value": "RSI: 72.3",
  "context": "RSI above 70 indicates overbought conditions; combined with price at upper Bollinger Band, suggests short-term pullback risk",
  "impact": "negative"
}
```

### 9.5.3 Announcement Child Nodes

| Field | Type | Description |
|---|---|---|
| `context` | string | What happened in this announcement (event summary) |
| `impact` | enum | `positive` / `negative` / `neutral` |

**Note:** No `value` field — announcements are event-driven, not metric-driven.

Example:
```json
{
  "context": "Q3 FY26 board meeting declared interim dividend of Rs 12 per share; revenue grew 8% YoY beating estimates",
  "impact": "positive"
}
```

### 9.5.4 News Child Nodes

| Field | Type | Description |
|---|---|---|
| `context` | string | Summary of entire news article, highlighting main point and stock relevance |
| `impact` | enum | `positive` / `negative` / `neutral` |

**Note:** No `value` field — news is qualitative.

Example:
```json
{
  "context": "Reliance announces new green energy JV with European partner; 5GW capacity addition planned over 3 years; market sees this as diversifying revenue beyond petrochemicals",
  "impact": "positive"
}
```

### 9.5.5 Financial Statement Nodes (Three-Level Hierarchy)

Financial statements have a **strict three-level hierarchy**:

**Level 1 — Financial Head:**
- `HEAD::financial` — "Financial Statements" (no data, just category anchor)

**Level 2 — Statement Group:**
- `GROUP::financial::Balance Sheet`
- `GROUP::financial::P&L` (Profit & Loss)
- `GROUP::financial::Cash Flow`
- `GROUP::financial::Shareholding`
- `GROUP::financial::Quarterly Result`
- `GROUP::financial::Annual Result`

**Data stored by Statement Group:**
| Field | Type | Description |
|---|---|---|
| `summary` | string | Summary of all its children — overall assessment of this statement |

**No `value`, `context`, or `impact` at this level.**

Example:
```json
{
  "summary": "Balance Sheet shows healthy asset growth (12% YoY) but debt-funded expansion raises leverage concerns; current ratio stable at 1.4x"
}
```

**Level 3 — Metric Children (sub-children):**

These are the actual data-bearing nodes under each Statement Group.

| Field | Type | Description |
|---|---|---|
| `value` | string | Current period metric (e.g., "Total Assets: 15.2L Cr") |
| `context` | string | Comparison summary from past year(s) available data — trend analysis |
| `impact` | enum | `positive` / `negative` / `neutral` — trend direction |

Example (Balance Sheet metric child):
```json
{
  "value": "Total Assets: 15.2L Cr",
  "context": "Assets grew 12% YoY from 13.6L Cr (FY25); driven by capacity expansion and inventory buildup; debt-funded growth warrants monitoring",
  "impact": "mixed"
}
```

Example (Quarterly Result metric child):
```json
{
  "value": "Q3 FY26 Revenue: 2,64,905 Cr",
  "context": "Revenue up 8.2% YoY from 2,44,800 Cr (Q3 FY25); 4-quarter CAGR at 9.5% showing consistent top-line momentum",
  "impact": "positive"
}
```

**Hierarchy visualization:**
```
HEAD::financial (Financial Statements)
└── GROUP::financial::Balance Sheet
│   └── summary: "Healthy asset growth but rising leverage..."
│   ├── CHILD::Total_Assets
│   │   ├── value: "15.2L Cr"
│   │   ├── context: "Assets grew 12% YoY..."
│   │   └── impact: "mixed"
│   ├── CHILD::Debt_To_Equity
│   │   ├── value: "0.42"
│   │   ├── context: "D/E improved from 0.48 last year..."
│   │   └── impact: "positive"
│   └── ...
└── GROUP::financial::P&L
│   └── summary: "Strong revenue growth with margin expansion..."
│   ├── CHILD::Revenue_TTM
│   │   ├── value: "9,73,508 Cr"
│   │   ├── context: "Revenue grew 15% YoY..."
│   │   └── impact: "positive"
│   └── ...
```

Example (Quarterly Result child):
```json
{
  "value": "Q3 FY26 Revenue: 2,64,905 Cr",
  "context": "Revenue up 8.2% YoY vs Q3 FY25 (2,44,800 Cr) and up 3.1% QoQ; 4-quarter CAGR at 9.5% showing consistent top-line momentum",
  "impact": "positive"
}
```

### 9.5.6 Impact Display Rules

| Impact | Node Border Color | Edge Particle Color | Tooltip Badge |
|---|---|---|---|
| `positive` | `#00FF88` (green) | Green particles flowing OUT | 🟢 Positive |
| `negative` | `#FF3355` (red) | Red particles flowing OUT | 🔴 Negative |
| `neutral` | `#B0BEC5` (gray) | No particles | ⚪ Neutral |
| `mixed` | `#FFB800` (amber) | Amber particles | 🟡 Mixed |

**Visual encoding:**
- Node fill color = category color (consistent across all nodes in category)
- Node border color = impact color (dynamic per node)
- Border thickness = `weight` × 2px (heavier nodes get thicker borders)
- Animated ring around high-impact nodes (impact != neutral AND weight > 0.5)

---

## 10. Edge Representation & Impact Flow

Edges must clearly show **HOW nodes attach and impact each other and the stock**.

### 10.1 Edge Data Schema

Every edge carries:

| Field | Type | Description |
|---|---|---|
| `source` | string | Source node ID |
| `target` | string | Target node ID |
| `type` | enum | Relationship type (see §4.3) |
| `weight` | float | 0.0–1.0 — strength of relationship |
| `impact_flow` | enum | `amplifies` / `dampens` / `neutral` — how source affects target |
| `context` | string | 1-sentence explanation of WHY this relationship exists |

Example:
```json
{
  "source": "RELIANCE|technical|RSI_14|2026-04-28",
  "target": "RELIANCE|technical|Bollinger_Upper|2026-04-28",
  "type": "CONFIRMS",
  "weight": 0.85,
  "impact_flow": "amplifies",
  "context": "RSI overbought (>70) + price at upper Bollinger Band together confirm overbought conditions, amplifying the sell signal"
}
```

### 10.2 Impact Flow Visualization

| impact_flow | Visual Treatment |
|---|---|
| `amplifies` | Bright color, thick line, fast particles flowing source→target |
| `dampens` | Muted color, dashed line, slow particles or no particles |
| `neutral` | Thin line, no particles, low opacity |

### 10.3 Edge Label on Hover

When hovering an edge, show:
```
RSI_14 ──[CONFIRMS]──► Bollinger_Upper
Weight: 0.85 | Impact: amplifies
"RSI overbought + price at upper band together 
confirm overbought conditions"
```

---

## 11. LLM Readability (Gemini Analysis)

The knowledge graph must be **easily readable by Gemini** for stock analysis.

### 11.1 Text Serialization Format

When serializing the graph for the LLM prompt, use this structured format:

```
══════════════════════════════════════════════════════════
KNOWLEDGE GRAPH: RELIANCE — Short-term Analysis
══════════════════════════════════════════════════════════

[NODE] RSI_14 | Technical — Momentum
  Value: RSI: 72.3
  Context: RSI above 70 indicates overbought conditions; combined with price at 
           upper Bollinger Band, suggests short-term pullback risk
  Impact: negative
  Weight: 0.08 | Confidence: 1.0

[NODE] Bollinger_Upper | Technical — Volatility
  Value: BB Upper: 1980.5
  Context: Price near upper band suggests resistance level; multiple tests here 
           historically led to 3-5% corrections
  Impact: negative
  Weight: 0.06 | Confidence: 1.0

[EDGE] RSI_14 ──CONFIRMS──► Bollinger_Upper
  Weight: 0.85 | Impact Flow: amplifies
  Explanation: Both indicators independently signal overbought conditions; 
                together they strongly amplify the bearish short-term signal

[NODE] Revenue_Quarterly | Financial — P&L
  Value: Q3 FY26 Revenue: 2,64,905 Cr
  Context: Revenue up 8.2% YoY from 2,44,800 Cr (Q3 FY25); 4-quarter CAGR at 9.5%
  Impact: positive
  Weight: 0.12 | Confidence: 0.85

[EDGE] Revenue_Quarterly ──CORRELATES──► PE_Ratio
  Weight: 0.40 | Impact Flow: neutral
  Explanation: Revenue growth provides fundamental support for valuation, but 
                PE expansion depends on margin sustainability

... (all active nodes and edges)
══════════════════════════════════════════════════════════
```

### 11.2 What Gemini Sees

- Every node with its **value**, **context**, and **impact**
- Every edge with its **relationship type**, **weight**, and **impact_flow**
- Clear hierarchy: which nodes belong to which category
- Cross-category connections: how technical signals relate to fundamentals

### 11.3 What Gemini Returns

After analyzing the graph, Gemini returns:

```json
{
  "per_node_relevance": {
    "RSI_14": 0.92,
    "Bollinger_Upper": 0.88,
    "Revenue_Quarterly": 0.75,
    "...": "..."
  },
  "contradictions": [
    {
      "nodes": ["RSI_14", "Revenue_Quarterly"],
      "explanation": "Technical overbought signal contradicts fundamental revenue strength"
    }
  ],
  "agreements": [
    {
      "nodes": ["RSI_14", "Bollinger_Upper"],
      "explanation": "Both technical indicators confirm overbought conditions"
    }
  ],
  "key_risk": "RSI_14",
  "confidence_score": 0.78
}
```

This feedback drives the **backward propagation** (edge weight updates).

---

## 12. File Changes

### New Files
- `backend/graph/tree_builder.py`
- `backend/graph/layout_data.py`
- `backend/graph/kg_template.html` (new HTML template)
- `backend/graph/js/tree.js`
- `backend/graph/js/layouts/*.js`
- `backend/graph/js/renderer.js`
- `backend/graph/js/focus.js`
- `backend/graph/js/ui.js`

### Modified Files
- `backend/graph/knowledge_graph.py` — Replace `_HTML_TEMPLATE` + `build_graph()`
- `backend/graph/stocxi_knowledge_graph.py` — Use tree builder
- `backend/agents/orchestrator.py` — Update graph render call

---

## 13. Acceptance Criteria

### Visual & Interaction
- [ ] Click "Financial" head → only Financial subtree visible, others fade to 3%
- [ ] Click "Balance Sheet" group → Balance Sheet metric children visible, others dimmed
- [ ] Switch layout → smooth 600ms animation to new positions
- [ ] All 4 layouts produce deterministic, non-overlapping positions
- [ ] 200 nodes render at 60fps on M1 MacBook Air
- [ ] Focus mode works correctly in all 4 layouts
- [ ] Background nodes in focus mode are visible but unobtrusive (3% opacity)
- [ ] Verdict nodes always visible but de-emphasized in focus mode

### Data Schema
- [ ] Financial ratio nodes store: `value`, `context`, `impact`
- [ ] Technical indicator nodes store: `value`, `context`, `impact`
- [ ] Announcement nodes store: `context`, `impact` (no `value`)
- [ ] News nodes store: `context`, `impact` (no `value`)
- [ ] Financial statement **groups** store: `summary` only (no `value`, `context`, `impact`)
- [ ] Financial statement **metric children** store: `value`, `context`, `impact`
- [ ] Edge hover shows: relationship type, weight, impact_flow, and 1-sentence explanation

### LLM Readability
- [ ] Text serialization includes all node values, contexts, impacts
- [ ] Text serialization includes all edges with explanations
- [ ] Gemini can clearly read the graph structure and relationships
- [ ] Gemini's per-node relevance feedback drives backward propagation

### Control & Visualization
- [ ] User can switch between 4 layouts (Force, Radial, Tree, Orbit)
- [ ] User can focus on any head, group, or child node
- [ ] User can filter by category, signal, edge type
- [ ] User can toggle labels, edges, particles, rotation
- [ ] Search finds nodes by label, source, value, or context

---

*Design document complete. Awaiting approval before implementation.*
