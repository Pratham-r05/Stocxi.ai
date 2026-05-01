"""
knowledge_graph.py — Hierarchical knowledge graph builder + professional 3D renderer.

Layer: graph/
Role: Converts analysis Nodes + admin_view into a hierarchical 3-tier graph
      (head → child → verdict) rendered as an interactive 3D visualization.

Design: Bloomberg-terminal aesthetic. Deep black background, clear hierarchy,
         directional arrows for edges, signal-colored borders on child nodes.
         No cartoonish effects — no additive blending, no pulsating halos.

Output: self-contained HTML file — open in any browser.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Sequence

from backend.schemas.node import Node

logger = logging.getLogger(__name__)

# New hierarchical tree builder + renderer (Phase 1 rebuild)
from backend.graph.tree_builder import NodeTree
from backend.graph.kg_renderer import render_knowledge_graph

_FINANCIAL_NODE_GROUPS: dict[str, str] = {
    "Debt_To_Equity": "Balance Sheet",
    "Total_Assets": "Balance Sheet",
    "Total_Liabilities": "Balance Sheet",
    "Shareholders_Equity": "Balance Sheet",
    "Reserves": "Balance Sheet",
    "Borrowings": "Balance Sheet",
    "Revenue_TTM": "P&L",
    "PAT_TTM": "P&L",
    "EBITDA_TTM": "P&L",
    "EBITDA_Margin": "P&L",
    "Revenue_Growth_YoY": "P&L",
    "PAT_Growth_YoY": "P&L",
    "Interest_Coverage": "P&L",
    "Market_Cap": "P&L",
    "Operating_Cash_Flow": "Cash Flow",
    "Free_Cashflow": "Cash Flow",
    "Cash_From_Investing": "Cash Flow",
    "Cash_From_Financing": "Cash Flow",
    "Promoter_Holding": "Share Holding",
    "Public_Retail_Holding": "Share Holding",
    "FII_Holding": "Share Holding",
    "DII_Holding": "Share Holding",
    "Revenue_Quarterly": "Quarterly Result",
    "Net_Profit_Quarterly": "Quarterly Result",
    "Expenses_Quarterly": "Quarterly Result",
    "Operating_Profit_Quarterly": "Quarterly Result",
    "OPM_Quarterly": "Quarterly Result",
    "Revenue_Annual": "Annual Result",
    "Net_Profit_Annual": "Annual Result",
    "Expenses_Annual": "Annual Result",
    "Operating_Profit_Annual": "Annual Result",
    "OPM_Annual": "Annual Result",
    "EPS_Annual": "Annual Result",
}

_FINANCIAL_NODE_NAMES: frozenset[str] = frozenset(_FINANCIAL_NODE_GROUPS.keys())

_LINK_DISTANCE: dict[str, float] = {
    "belongs_to": 25,
    "informs": 60,
    "CONFIRMS": 100,
    "AMPLIFIES": 100,
    "TRIGGERS": 110,
    "CAUSES": 110,
    "CONTRADICTS": 120,
    "DAMPENS": 120,
    "CONTEXTUALIZES": 140,
    "CORRELATES": 160,
    "cross_category": 150,
}

_FINANCIAL_GROUP_INFO: dict[str, str] = {
    "Balance Sheet": "Assets, liabilities, and equity — leverage and solvency metrics",
    "P&L": "Profitability — revenue, margins, earnings, and growth trends",
    "Cash Flow": "Operating, investing, and free cash flow analysis",
    "Share Holding": "Promoter, institutional, and public ownership patterns",
    "Quarterly Result": "Quarterly revenue, profit, and margin trends",
    "Annual Result": "Annual financial performance and trajectory",
}

_HEAD_DESCRIPTIONS: dict[str, str] = {
    "technical": "Technical indicators analyzing price trends, momentum, volume, and volatility patterns",
    "fundamental": "Valuation ratios and company quality metrics measuring profitability and market positioning",
    "financial": "Financial statements — balance sheet, P&L, cash flow, shareholding, and results",
    "news": "Recent news coverage and sentiment from verified financial news sources",
    "announcement": "Exchange filings: quarterly results, board meetings, dividends, and corporate actions",
}

_SIGNAL_BORDER = {
    "bullish": "#00FF88",
    "positive": "#00FF88",
    "bearish": "#FF3355",
    "negative": "#FF3355",
    "neutral": "#B8C4D0",
    "mixed": "#FFB800",
}

_EDGE_STYLE = {
    "CONFIRMS":        {"color": "#00FF88", "w": 1.4, "opacity": 0.55, "dash": False, "flow": "slow"},
    "AMPLIFIES":       {"color": "#00FFCC", "w": 1.8, "opacity": 0.65, "dash": False, "flow": "fast"},
    "CONTRADICTS":     {"color": "#FF3355", "w": 1.4, "opacity": 0.55, "dash": True,  "flow": "medium"},
    "DAMPENS":         {"color": "#FF8844", "w": 1.0, "opacity": 0.45, "dash": True,  "flow": "slow"},
    "CAUSES":          {"color": "#4499FF", "w": 1.4, "opacity": 0.55, "dash": False, "flow": "medium"},
    "TRIGGERS":        {"color": "#AA55FF", "w": 1.8, "opacity": 0.65, "dash": False, "flow": "fast"},
    "CONTEXTUALIZES":  {"color": "#6688AA", "w": 0.6, "opacity": 0.30, "dash": False, "flow": "very_slow"},
    "CORRELATES":      {"color": "#556677", "w": 0.5, "opacity": 0.20, "dash": False, "flow": "static"},
    "belongs_to":      {"color": "rgba(255,255,255,0.22)", "w": 0.4, "opacity": 0.22, "dash": False, "flow": "static"},
    "informs":         {"color": "rgba(255,255,255,0.35)", "w": 0.7, "opacity": 0.35, "dash": False, "flow": "slow"},
    "cross_category":  {"color": "rgba(255,255,255,0.10)", "w": 0.25, "opacity": 0.10, "dash": True,  "flow": "static"},
}

_HORIZON_DISPLAY = {
    "short": "Short-term",
    "medium": "Medium-term",
    "long": "Long-term",
}

_EXCLUDED_CONTEXT_NODES: frozenset[str] = frozenset({
    "Market_Regime",
    "Sector_Trend",
    "Data_Completeness",
    "Peer_Snapshot",
})


def build_graph(
    nodes: list[Any],
    admin_view: dict[str, Any] | None = None,
    edges: list[Any] | None = None,
    effective_weights: dict[str, float] | None = None,
    horizon: str = "short",
) -> dict[str, Any]:
    """Convert analysis nodes into a hierarchical tree for knowledge graph visualization.

    Uses NodeTree to build explicit parent-child hierarchy:
      ROOT → HEADS → GROUPS (financial only) → CHILDREN
    """
    # Build hierarchical tree using new tree builder
    tree = NodeTree(nodes, edges)
    tree_json = tree.to_json()

    # Inject effective weights if provided
    if effective_weights:
        for node in tree_json["nodes"]:
            if node["id"] in effective_weights:
                node["effective_weight"] = effective_weights[node["id"]]

    # Add verdict nodes from admin_view if available
    admin_view = admin_view or {}
    verdicts_raw = admin_view.get("verdicts", {})
    if verdicts_raw and isinstance(verdicts_raw, dict):
        verdict_cats = {
            "technical": "HEAD::technical",
            "fundamental": "HEAD::fundamental",
            "announcement": "HEAD::announcement",
            "news": "HEAD::news",
            "financial": "HEAD::financial",
        }
        for cat_name, verdict in verdicts_raw.items():
            vid = f"VERDICT::{cat_name}"
            vsig = verdict.get("direction", verdict.get("signal", "neutral"))
            tree_json["nodes"].append({
                "id": vid,
                "label": f"Verdict: {cat_name.title()}",
                "node_type": "verdict",
                "parent_id": verdict_cats.get(cat_name),
                "children": [],
                "depth": 2,
                "value": vsig.upper(),
                "context": "",
                "impact": vsig,
                "summary": "",
                "category": cat_name,
                "signal": vsig,
                "weight": 2.5,
                "effective_weight": None,
                "confidence": 1.0,
                "color": "#a855f7",
            })
            # Link verdict to parent head
            parent_head = verdict_cats.get(cat_name)
            if parent_head:
                tree_json["edges"].append({
                    "source": parent_head,
                    "target": vid,
                    "type": "informs",
                    "weight": 0.8,
                })

    # Update meta
    tree_json["meta"]["node_count"] = len(tree_json["nodes"])
    tree_json["meta"]["edge_count"] = len(tree_json["edges"])

    return tree_json


def render_3d_html(
    graph_data: dict[str, Any],
    title: str = "Stocxi Knowledge Graph",
    stock_name: str = "",
    horizon: str = "",
    output_path: str | Path | None = None,
) -> str:
    """Render graph_data as self-contained professional 3D HTML.

    Delegates to the new hierarchical renderer (kg_renderer.py).
    """
    return render_knowledge_graph(
        tree_data=graph_data,
        title=title,
        stock_name=stock_name,
        horizon=horizon,
        output_path=output_path,
    )


def serialize_for_llm(
    nodes: list[Node],
    edges: Sequence[Any],
    horizon: str = "medium",
    ticker: str = "STOCK_A",
) -> str:
    """Serialize the knowledge graph as structured text for the LLM prompt."""
    if not nodes:
        return "(empty graph)"
    from backend.graph.stocxi_knowledge_graph import StocxiKnowledgeGraph
    kg = StocxiKnowledgeGraph(ticker=ticker, horizon=horizon)
    kg._nodes = list(nodes)
    kg._edges = list(edges) if edges else []
    kg.forward_propagate()
    return kg.serialize_for_llm()


def to_graphxr_data(graph_data: dict[str, Any]) -> dict[str, Any]:
    """Export graph data in GraphXR-compatible JSON format."""
    gx_nodes = []
    for n in graph_data.get("nodes", []):
        gx_nodes.append({
            "_id": n["id"],
            "_labels": [n.get("source_file", "Unknown").split("·")[0].strip()],
            "label": n.get("label", n["id"]),
            "signal": n.get("signal", "neutral"),
            "community": n.get("community", 0),
            "weight": n.get("weight", 0),
            "effective_weight": n.get("effective_weight"),
            "value_text": n.get("value_text", ""),
            "context": n.get("context", ""),
            "color": n.get("color", "#888888"),
            "node_type": n.get("node_type", "child"),
        })
    gx_edges = []
    for e in graph_data.get("links", []):
        src = e["source"]["id"] if isinstance(e["source"], dict) else e["source"]
        tgt = e["target"]["id"] if isinstance(e["target"], dict) else e["target"]
        gx_edges.append({
            "_from": src,
            "_to": tgt,
            "_label": e.get("type", "CONNECTS"),
            "edgeType": e.get("type", "CONNECTS"),
            "color": e.get("color", "#444444"),
        })
    return {"nodes": gx_nodes, "edges": gx_edges}


def _short_label(node_id: str) -> str:
    base = node_id.split("#")[0]
    if "|" in base:
        parts = base.split("|")
        name = parts[2] if len(parts) >= 3 else base
    elif "::" in base:
        parts = base.split("::")
        name = parts[1] if len(parts) >= 2 else base
    else:
        name = base
    return name.replace("_", " ")


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stocxi — __STOCK_NAME__</title>
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#050508;--surface:#111116;--surface-2:#1a1a22;--surface-hover:#252530;
  --border:rgba(255,255,255,0.08);--border-focus:rgba(139,92,246,0.6);
  --text:#FFFFFF;--text-sec:#C0C8D4;--text-muted:#6B7280;
  --accent:#8B5CF6;--accent2:#7C3AED;
  --positive:#00FF88;--negative:#FF3355;--neutral:#B0BEC5;--mixed:#FFB800;
  --confirms:#00FF88;--amplifies:#00FFCC;--contradicts:#FF3355;--dampens:#FF8844;
  --causes:#4499FF;--triggers:#AA55FF;--contextualizes:#6688AA;--correlates:#556677;
  --radius:8px;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:-apple-system,'SF Pro Text','SF Pro Display',BlinkMacSystemFont,system-ui,sans-serif;}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.15);border-radius:4px}
#graph{width:100vw;height:100vh;position:fixed;top:0;left:0;z-index:1}

#header{
  position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:100;
  padding:10px 22px;text-align:center;pointer-events:none;
  background:rgba(17,17,22,0.8);border:1px solid var(--border);border-radius:10px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
#header-title{font-size:15px;font-weight:700;color:var(--text);letter-spacing:-0.2px}
#header-sub{font-size:11px;color:var(--text-muted);margin-top:1px;letter-spacing:0.3px}

#panel{
  position:fixed;top:14px;left:14px;z-index:100;
  background:rgba(17,17,22,0.92);border:1px solid var(--border);border-radius:12px;
  padding:0;width:220px;max-height:calc(100vh - 28px);overflow-y:auto;
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
}
.p-section{padding:10px 12px;border-bottom:1px solid var(--border)}
.p-section:last-child{border-bottom:none}
.p-title{font-size:8px;text-transform:uppercase;letter-spacing:2.5px;color:#FFFFFF;
  margin-bottom:8px;font-weight:700;display:flex;align-items:center;gap:6px}
.p-title svg{width:10px;height:10px;opacity:0.5}
.p-row{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px;align-items:center}
.p-row:last-child{margin-bottom:0}
.p-row-center{justify-content:center}

.btn{
  background:rgba(255,255,255,0.05);border:1px solid var(--border);color:#FFFFFF;
  padding:5px 9px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;
  transition:all .15s;font-family:inherit;letter-spacing:0.2px;white-space:nowrap;
}
.btn:hover{background:rgba(139,92,246,0.12);border-color:rgba(139,92,246,0.4);color:#C4B5FD}
.btn.active{background:rgba(139,92,246,0.2);border-color:rgba(139,92,246,0.5);color:#A78BFA;
  box-shadow:0 0 8px rgba(139,92,246,0.15)}
.btn-icon{padding:5px 7px;display:flex;align-items:center;justify-content:center}

.sel{
  background:rgba(255,255,255,0.05);border:1px solid var(--border);color:#FFFFFF;
  padding:6px 8px;border-radius:6px;font-size:10px;font-family:inherit;cursor:pointer;
  width:100%;appearance:none;-webkit-appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%238B5CF6'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 8px center;padding-right:24px;
}
.sel option{background:#1a1a22;color:#FFFFFF}
.sel:focus{border-color:var(--border-focus);outline:none}

.slider-wrap{width:100%;display:flex;align-items:center;gap:8px;margin-bottom:4px}
.slider-wrap label{font-size:9px;color:var(--text-muted);min-width:60px;letter-spacing:0.3px;text-transform:uppercase}
.slider-wrap input[type=range]{flex:1;height:3px;-webkit-appearance:none;appearance:none;
  background:rgba(255,255,255,0.12);border-radius:2px;outline:none}
.slider-wrap input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:12px;height:12px;
  border-radius:50%;background:#8B5CF6;cursor:pointer;border:2px solid #1a1a22}
.slider-wrap .sv{font-size:9px;color:#A78BFA;min-width:24px;text-align:right;font-weight:600}

.edge-legend{display:flex;flex-wrap:wrap;gap:3px 8px}
.edge-legend-item{display:flex;align-items:center;gap:4px;font-size:8px;color:var(--text-muted);letter-spacing:0.3px}
.edge-legend-dot{width:10px;height:2px;border-radius:1px}

#tooltip{
  position:fixed;z-index:200;display:none;pointer-events:none;
  background:rgba(17,17,22,0.97);border:1px solid rgba(255,255,255,0.15);border-radius:10px;
  padding:14px 16px;max-width:340px;min-width:200px;
  backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);
  box-shadow:0 8px 40px rgba(0,0,0,0.6);
}
.tt-label{font-size:14px;font-weight:700;color:#FFFFFF;line-height:1.3;margin-bottom:2px}
.tt-cat{font-size:9px;text-transform:uppercase;letter-spacing:2px;color:#6B7280;
  margin-top:2px;margin-bottom:8px}
.tt-divider{height:1px;background:rgba(255,255,255,0.08);margin:8px 0}
.tt-section{margin-bottom:6px}
.tt-section-title{font-size:9px;text-transform:uppercase;letter-spacing:1.5px;color:#6B7280;margin-bottom:2px}
.tt-value{font-size:12px;color:#FFFFFF;line-height:1.5;font-weight:500}
.tt-children{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.tt-child-tag{font-size:9px;padding:2px 6px;border-radius:4px;
  background:rgba(255,255,255,0.06);color:#D1D5DB;border:1px solid rgba(255,255,255,0.08)}
.tt-row{display:flex;justify-content:space-between;font-size:11px;line-height:1.6;color:#6B7280}
.tt-row span:last-child{color:#FFFFFF;font-weight:600}
.tt-signal{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle}

#stats{
  position:fixed;bottom:14px;left:50%;transform:translateX(-50%);z-index:100;
  background:rgba(17,17,22,0.88);border:1px solid var(--border);border-radius:20px;
  padding:6px 18px;font-size:11px;color:var(--text-muted);
  display:flex;gap:10px;align-items:center;
  backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
}
#stats strong{color:#A78BFA;font-weight:700}

#shape-btn-wrap{position:relative}
.graph-tooltip{display:none!important}
#shape-dropdown{
  display:none;position:absolute;left:0;top:100%;margin-top:4px;z-index:120;
  background:rgba(26,26,34,0.98);border:1px solid var(--border);border-radius:8px;
  padding:4px;min-width:140px;
  backdrop-filter:blur(20px);box-shadow:0 4px 20px rgba(0,0,0,0.5);
}
#shape-dropdown.show{display:block}
.sd-item{
  display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:6px;
  cursor:pointer;font-size:10px;color:#C0C8D4;transition:all .12s;font-weight:500;
}
.sd-item:hover{background:rgba(139,92,246,0.15);color:#FFFFFF}
.sd-item.active{color:#A78BFA;font-weight:700}
.sd-shape{width:18px;height:18px;display:flex;align-items:center;justify-content:center}
</style>
</head>
<body>
<div id="graph"></div>

<div id="header">
  <div id="header-title">Knowledge Graph</div>
  <div id="header-sub">__STOCK_NAME__ · __HORIZON__</div>
</div>

<div id="panel">
  <div class="p-section">
    <div class="p-title">Layout</div>
    <div class="p-row">
      <button onclick="setLayout('force')" class="btn active" id="btn-force">Force</button>
      <button onclick="setLayout('radial')" class="btn" id="btn-radial">Radial</button>
      <button onclick="setLayout('hierarchy')" class="btn" id="btn-hierarchy">Tree</button>
    </div>
  </div>

  <div class="p-section">
    <div class="p-title">Node Shape</div>
    <div id="shape-btn-wrap">
      <button onclick="toggleShapeDropdown()" class="btn" id="btn-shape" style="width:100%">
        <span id="shape-label">Sphere</span> <span style="opacity:0.4">▼</span>
      </button>
      <div id="shape-dropdown">
        <div class="sd-item active" onclick="setShape('sphere', this)"><span class="sd-shape">●</span> Sphere</div>
        <div class="sd-item" onclick="setShape('box', this)"><span class="sd-shape">■</span> Box</div>
        <div class="sd-item" onclick="setShape('diamond', this)"><span class="sd-shape">◆</span> Diamond</div>
        <div class="sd-item" onclick="setShape('cone', this)"><span class="sd-shape">▲</span> Cone</div>
        <div class="sd-item" onclick="setShape('torus', this)"><span class="sd-shape">◎</span> Torus</div>
        <div class="sd-item" onclick="setShape('octahedron', this)"><span class="sd-shape">⬡</span> Octahedron</div>
      </div>
    </div>
  </div>

  <div class="p-section">
    <div class="p-title">Display</div>
    <div class="p-row">
      <button id="btn-edges" class="btn active" onclick="toggleEdges()">Edges</button>
      <button id="btn-labels" class="btn" onclick="toggleLabels()">Labels</button>
      <button id="btn-rotate" class="btn active" onclick="toggleRotation()">Spin</button>
    </div>
    <div class="p-row" style="margin-top:6px">
      <select onchange="filterCategory(this.value)" id="cat-filter" class="sel">
        <option value="all">All Categories</option>
        <option value="technical">Technical</option>
        <option value="fundamental">Fundamental</option>
        <option value="financial">Financial</option>
        <option value="news">News</option>
        <option value="announcement">Announcements</option>
      </select>
    </div>
    <div class="p-row" style="margin-top:6px">
      <select onchange="filterSignal(this.value)" id="sig-filter" class="sel">
        <option value="all">All Signals</option>
        <option value="bullish">Bullish</option>
        <option value="positive">Positive</option>
        <option value="bearish">Bearish</option>
        <option value="negative">Negative</option>
        <option value="neutral">Neutral</option>
        <option value="mixed">Mixed</option>
      </select>
    </div>
    <div class="p-row" style="margin-top:6px">
      <select onchange="filterNodeType(this.value)" id="type-filter" class="sel">
        <option value="all">All Node Types</option>
        <option value="head">Head</option>
        <option value="group">Group</option>
        <option value="child">Child</option>
        <option value="verdict">Verdict</option>
      </select>
    </div>
  </div>

  <div class="p-section">
    <div class="p-title">Physics</div>
    <div class="slider-wrap">
      <label>Charge</label>
      <input type="range" min="-600" max="-20" value="-250" id="sl-charge" oninput="setCharge(this.value)">
      <span class="sv" id="sv-charge">-250</span>
    </div>
    <div class="slider-wrap">
      <label>Dist</label>
      <input type="range" min="30" max="300" value="120" id="sl-dist" oninput="setLinkDist(this.value)">
      <span class="sv" id="sv-dist">120</span>
    </div>
    <div class="slider-wrap">
      <label>Curvature</label>
      <input type="range" min="0" max="50" value="8" id="sl-curve" oninput="setCurvature(this.value)">
      <span class="sv" id="sv-curve">0.08</span>
    </div>
  </div>

  <div class="p-section">
    <div class="p-title">Appearance</div>
    <div class="slider-wrap">
      <label>Opacity</label>
      <input type="range" min="10" max="100" value="100" id="sl-opacity" oninput="setGlobalOpacity(this.value)">
      <span class="sv" id="sv-opacity">100%</span>
    </div>
    <div class="slider-wrap">
      <label>Node Scale</label>
      <input type="range" min="50" max="200" value="100" id="sl-scale" oninput="setNodeScale(this.value)">
      <span class="sv" id="sv-scale">1.0x</span>
    </div>
    <div class="slider-wrap">
      <label>Edge Width</label>
      <input type="range" min="0" max="100" value="50" id="sl-ewidth" oninput="setEdgeWidthMult(this.value)">
      <span class="sv" id="sv-ewidth">1.0x</span>
    </div>
  </div>

  <div class="p-section">
    <div class="p-title">Edge Legend</div>
    <div class="edge-legend">
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#00FF88"></span>Confirms</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#00FFCC"></span>Amplifies</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#FF3355"></span>Contradicts</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#FF8844"></span>Dampens</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#4499FF"></span>Causes</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#AA55FF"></span>Triggers</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#6688AA"></span>Context</div>
      <div class="edge-legend-item"><span class="edge-legend-dot" style="background:#556677"></span>Correlates</div>
    </div>
    <div class="p-row" style="margin-top:6px">
      <select onchange="filterEdgeType(this.value)" id="edge-filter" class="sel">
        <option value="all">All Edge Types</option>
        <option value="CONFIRMS">Confirms</option>
        <option value="AMPLIFIES">Amplifies</option>
        <option value="CONTRADICTS">Contradicts</option>
        <option value="DAMPENS">Dampens</option>
        <option value="CAUSES">Causes</option>
        <option value="TRIGGERS">Triggers</option>
        <option value="CONTEXTUALIZES">Contextualizes</option>
        <option value="CORRELATES">Correlates</option>
      </select>
    </div>
  </div>

  <div class="p-section">
    <div class="p-title">Actions</div>
    <div class="p-row p-row-center">
      <button class="btn" onclick="resetCamera()">Reset View</button>
      <button class="btn" onclick="highlightNeighbors()">Neighbors</button>
      <button class="btn" onclick="clearHighlight()">Clear</button>
    </div>
  </div>
</div>

<div id="tooltip">
  <div class="tt-label" id="tt-label"></div>
  <div class="tt-cat" id="tt-cat"></div>
  <div class="tt-divider" id="tt-divider-1"></div>
  <div class="tt-section" id="tt-desc-section">
    <div class="tt-value" id="tt-desc"></div>
  </div>
  <div class="tt-divider" id="tt-divider-2"></div>
  <div class="tt-section" id="tt-val-section">
    <div class="tt-section-title">Value</div>
    <div class="tt-value" id="tt-val"></div>
  </div>
  <div class="tt-section" id="tt-sig-section">
    <div class="tt-section-title">Performance</div>
    <div class="tt-value" id="tt-sig"></div>
  </div>
  <div class="tt-section" id="tt-ctx-section">
    <div class="tt-section-title">Context</div>
    <div class="tt-value" id="tt-ctx"></div>
  </div>
  <div class="tt-children" id="tt-children"></div>
  <div class="tt-row" id="tt-wt-row" style="margin-top:4px"><span>Weight</span><span id="tt-wt"></span></div>
</div>

<div id="stats">
  <span><strong id="sn">0</strong> Nodes</span>
  <span>·</span>
  <span><strong id="se">0</strong> Edges</span>
  <span>·</span>
  <span><strong id="sc">0</strong> Groups</span>
</div>

<script src="https://unpkg.com/three@0.158.0/build/three.min.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.73.2/dist/3d-force-graph.min.js"></script>
<script>
const D=__GRAPH_DATA__;
let rotating=true, showLabels=false, edgesVisible=true, layoutMode='force';
let currentShape='sphere', globalOpacity=1.0, nodeScale=1.0, edgeWidthMult=1.0, linkCurvature=0.08;
let linkDistScale=1.0;
let focusMode=false;
let selectedHeadId=null;
let hoveredNode=null;
const hlNodes=new Set(), hlLinks=new Set();

const SIGNAL_COLORS={
  positive:'#00FF88',bullish:'#00FF88',negative:'#FF3355',bearish:'#FF3355',
  neutral:'#B0BEC5',mixed:'#FFB800'
};

const EDGE_COLORS={
  CONFIRMS:'#00FF88',AMPLIFIES:'#00FFCC',CONTRADICTS:'#FF3355',DAMPENS:'#FF8844',
  CAUSES:'#4499FF',TRIGGERS:'#AA55FF',CONTEXTUALIZES:'#6688AA',CORRELATES:'#556677',
  belongs_to:'rgba(255,255,255,0.22)',informs:'rgba(255,255,255,0.35)',
  cross_category:'rgba(255,255,255,0.10)'
};
const EDGE_CURVES={CONFIRMS:0.05,AMPLIFIES:0.08,CONTRADICTS:0.25,DAMPENS:0.15,
  CAUSES:0.1,TRIGGERS:0.12,CONTEXTUALIZES:0.02,CORRELATES:0.0,
  belongs_to:0.0,informs:0.03,cross_category:0.35};

const nodeMap={};
const childrenMap={};
D.nodes.forEach(n=>{
  nodeMap[n.id]=n;
  if(n.parent){
    if(!childrenMap[n.parent])childrenMap[n.parent]=[];
    childrenMap[n.parent].push(n);
  }
});

let Graph, canvas;

function makeGeom(r,shape){
  if(shape==='box') return new THREE.BoxGeometry(r*1.6,r*1.6,r*1.6);
  if(shape==='diamond') return new THREE.OctahedronGeometry(r);
  if(shape==='cone') return new THREE.ConeGeometry(r,r*2,16);
  if(shape==='torus') return new THREE.TorusGeometry(r,r*0.35,16,48);
  if(shape==='octahedron') return new THREE.OctahedronGeometry(r,0);
  return new THREE.SphereGeometry(r,24,16);
}

function makeNode(node){
  const g=new THREE.Group();
  const nt=node.node_type||'child';
  let r;
  if(nt==='head') r=12;
  else if(nt==='group') r=8;
  else if(nt==='verdict') r=10;
  else r=5.5;
  r*=nodeScale;

  if(nt==='head'){
    const core=new THREE.Mesh(makeGeom(r,currentShape),
      new THREE.MeshPhongMaterial({color:new THREE.Color('#FFFFFF'),shininess:90,specular:new THREE.Color('#666666')}));
    g.add(core);
    const ring=new THREE.Mesh(
      new THREE.TorusGeometry(r*1.4,0.3,16,64),
      new THREE.MeshPhongMaterial({color:new THREE.Color('#FFFFFF'),shininess:30,transparent:true,opacity:0.2})
    );
    ring.rotation.x=Math.PI/2;
    g.add(ring);
  } else if(nt==='group'){
    const fill=new THREE.Mesh(makeGeom(r,currentShape),
      new THREE.MeshPhongMaterial({color:new THREE.Color('#3B82F6'),shininess:70,specular:new THREE.Color('#4488EE')}));
    g.add(fill);
    const ring=new THREE.Mesh(
      new THREE.TorusGeometry(r*1.25,0.2,16,64),
      new THREE.MeshPhongMaterial({color:new THREE.Color('#60A5FA'),shininess:40,specular:new THREE.Color('#3366CC'),transparent:true,opacity:0.45})
    );
    ring.rotation.x=Math.PI/2;
    g.add(ring);
  } else if(nt==='verdict'){
    const shape=new THREE.Shape();
    const sides=6;
    for(let i=0;i<sides;i++){
      const a=(i/sides)*Math.PI*2-Math.PI/2;
      if(i===0)shape.moveTo(Math.cos(a)*r,Math.sin(a)*r);
      else shape.lineTo(Math.cos(a)*r,Math.sin(a)*r);
    }
    shape.closePath();
    const hexGeo=new THREE.ExtrudeGeometry(shape,{depth:1.5,bevelEnabled:false});
    const hexMat=new THREE.MeshPhongMaterial({color:new THREE.Color('#8B5CF6'),shininess:90,specular:new THREE.Color('#C4B5FD')});
    const hexMesh=new THREE.Mesh(hexGeo,hexMat);
    hexMesh.position.z=-0.75;
    g.add(hexMesh);
    const sigColor=SIGNAL_COLORS[node.signal]||SIGNAL_COLORS.neutral;
    const dot=new THREE.Mesh(new THREE.SphereGeometry(r*0.22,16,12),
      new THREE.MeshPhongMaterial({color:new THREE.Color(sigColor),shininess:60,specular:new THREE.Color('#888888')}));
    dot.position.set(0,-r*1.2,0);
    g.add(dot);
  } else {
    const sigColor=SIGNAL_COLORS[node.signal]||SIGNAL_COLORS[node.border_color]||SIGNAL_COLORS[node.color]||'#B0BEC5';
    const fill=new THREE.Mesh(makeGeom(r,currentShape),
      new THREE.MeshPhongMaterial({color:new THREE.Color('#374151'),shininess:50,specular:new THREE.Color('#666666')}));
    g.add(fill);
    const border=new THREE.Mesh(makeGeom(r*1.18,currentShape),
      new THREE.MeshPhongMaterial({color:new THREE.Color(sigColor),shininess:40,specular:new THREE.Color('#444444'),transparent:true,opacity:0.5}));
    g.add(border);
  }

  g.__nodeR=r;
  g.__nodeId=node.id;
  g.__nodeType=nt;
  return g;
}

function createLabelSprite(node){
  const c=document.createElement('canvas');
  const txt=node.label.length>22?node.label.slice(0,20)+'...':node.label;
  const fontSize=28;
  const font='bold '+fontSize+'px -apple-system,"SF Pro Text","SF Pro Display",BlinkMacSystemFont,system-ui,sans-serif';
  const ctx2d=c.getContext('2d');
  ctx2d.font=font;
  const tw=ctx2d.measureText(txt).width;
  c.width=Math.ceil(tw)+16;c.height=fontSize+8;
  ctx2d.font=font;
  ctx2d.textAlign='center';ctx2d.textBaseline='middle';
  ctx2d.fillStyle='#FFFFFF';
  ctx2d.fillText(txt,c.width/2,c.height/2);
  const tex=new THREE.CanvasTexture(c);
  const mat=new THREE.SpriteMaterial({map:tex,depthWrite:false,transparent:true,opacity:0.95});
  const sprite=new THREE.Sprite(mat);
  const r=node.__nodeR||5;
  const aspect=c.width/c.height;
  const lw=r*1.5*aspect;
  const lh=r*1.5;
  sprite.scale.set(lw,lh,1);
  sprite.position.set(0,r+lh/2+2,0);
  return sprite;
}

function nodeOpacity(n){
  if(!hlNodes.size)return globalOpacity;
  return hlNodes.has(n.id)?globalOpacity:0.01*globalOpacity;
}

function getEdgeType(l){
  return l.type||'';
}

function linkColor(l){
  if(!edgesVisible)return 'rgba(0,0,0,0)';
  const et=getEdgeType(l);
  const ec=EDGE_COLORS[et];
  if(hlLinks.size){
    return hlLinks.has(l)?(ec||'rgba(180,200,220,0.6)'):'rgba(0,0,0,0)';
  }
  return ec||'rgba(180,200,220,0.3)';
}

function linkWidth(l){
  if(!edgesVisible)return 0;
  const base=typeof l.w==='number'?l.w:0.7;
  if(!hlLinks.size)return Math.max(0.3,base*edgeWidthMult*0.7);
  return hlLinks.has(l)?Math.max(0.5,base*edgeWidthMult*1.8):0.08;
}

function linkCurvatureFn(l){
  const et=getEdgeType(l);
  const c=EDGE_CURVES[et];
  if(c!==undefined)return c;
  return linkCurvature;
}

function linkDirectionalParticles(l){
  if(!edgesVisible||!hlLinks.size)return 0;
  return hlLinks.has(l)?2:0;
}

function linkDirectionalParticleColor(l){
  const et=getEdgeType(l);
  const ec=EDGE_COLORS[et];
  return ec||'rgba(180,200,220,0.5)';
}

function showTooltip(node,x,y){
  const tt=document.getElementById('tooltip');
  const nt=node.node_type||'child';
  document.getElementById('tt-label').textContent=node.label||'';
  document.getElementById('tt-cat').textContent=(node.source_file||'').replace(' · ',', ');

  const descEl=document.getElementById('tt-desc-section');
  const descTextEl=document.getElementById('tt-desc');
  const valSection=document.getElementById('tt-val-section');
  const sigSection=document.getElementById('tt-sig-section');
  const ctxSection=document.getElementById('tt-ctx-section');
  const childrenEl=document.getElementById('tt-children');
  const wtRow=document.getElementById('tt-wt-row');
  const div1=document.getElementById('tt-divider-1');
  const div2=document.getElementById('tt-divider-2');

  valSection.style.display='none';sigSection.style.display='none';ctxSection.style.display='none';
  childrenEl.innerHTML='';childrenEl.style.display='none';wtRow.style.display='none';
  div1.style.display='block';div2.style.display='block';descEl.style.display='none';

  if(nt==='head'){
    const desc=node.context||'';
    descTextEl.textContent=desc;descEl.style.display='block';
    const kids=childrenMap[node.id]||[];
    if(kids.length>0){childrenEl.style.display='flex';kids.forEach(k=>{
      const tag=document.createElement('span');tag.className='tt-child-tag';tag.textContent=k.label;childrenEl.appendChild(tag);
    });}
    wtRow.style.display='flex';document.getElementById('tt-wt').textContent=kids.length+' items';
  } else if(nt==='group'){
    const desc=node.context||'';
    descTextEl.textContent=desc;descEl.style.display='block';
    const kids=childrenMap[node.id]||[];
    if(kids.length>0){childrenEl.style.display='flex';kids.forEach(k=>{
      const tag=document.createElement('span');tag.className='tt-child-tag';
      const sigDot=SIGNAL_COLORS[k.signal]||'#B0BEC5';
      tag.innerHTML='<span class="tt-signal" style="background:'+sigDot+';width:6px;height:6px;display:inline-block;border-radius:50%;margin-right:4px;vertical-align:middle"></span>'+k.label;
      childrenEl.appendChild(tag);
    });}
    wtRow.style.display='flex';document.getElementById('tt-wt').textContent=kids.length+' data points';
  } else if(nt==='verdict'){
    descEl.style.display='block';descTextEl.textContent=node.value_text||'';
    const sigColor=SIGNAL_COLORS[node.signal]||SIGNAL_COLORS.neutral;
    const sigLabel=(node.signal||'neutral').charAt(0).toUpperCase()+(node.signal||'neutral').slice(1);
    sigSection.style.display='block';
    document.getElementById('tt-sig').innerHTML='<span class="tt-signal" style="background:'+sigColor+'"></span>'+sigLabel;
    wtRow.style.display='flex';document.getElementById('tt-wt').textContent=node.weight?.toFixed(2)||'–';
  } else {
    const src=node.source_file||'';
    const isNewsOrAnn=src.startsWith('news')||src.startsWith('announcement');
    if(!isNewsOrAnn){valSection.style.display='block';document.getElementById('tt-val').textContent=node.value_text||'–';}
    sigSection.style.display='block';
    const sigColor=SIGNAL_COLORS[node.signal]||SIGNAL_COLORS.neutral;
    const sigLabel=(node.signal||'neutral').charAt(0).toUpperCase()+(node.signal||'neutral').slice(1);
    document.getElementById('tt-sig').innerHTML='<span class="tt-signal" style="background:'+sigColor+'"></span>'+sigLabel;
    ctxSection.style.display='block';
    const ctx=node.context||'';
    document.getElementById('tt-ctx').textContent=ctx.length>180?ctx.slice(0,177)+'...':ctx||'No context available';
    wtRow.style.display='flex';
    document.getElementById('tt-wt').textContent=node.effective_weight?(node.effective_weight*100).toFixed(1)+'%':node.weight?.toFixed(2)||'–';
  }

  tt.style.display='block';
  const maxW=340;let left=x+18;let top=y-12;
  if(left+maxW+20>window.innerWidth)left=x-maxW-18;
  if(top+280>window.innerHeight)top=window.innerHeight-290;
  if(top<10)top=10;
  tt.style.left=left+'px';tt.style.top=top+'px';
}
function hideTooltip(){document.getElementById('tooltip').style.display='none';}

function enterFocusMode(node){
  focusMode=true;
  selectedHeadId = (node.node_type==='head') ? node.id : null;
  const ctrls=Graph.controls();
  if(ctrls)ctrls.autoRotate=false;
  hlNodes.clear();hlLinks.clear();
  hlNodes.add(node.id);
  const nt=node.node_type||'child';

  // First pass: identify all highlighted nodes
  if(nt==='head'||nt==='group'){
    const dc=childrenMap[node.id]||[];
    dc.forEach(c=>{hlNodes.add(c.id);(childrenMap[c.id]||[]).forEach(gc=>hlNodes.add(gc.id));});
    if(node.parent){hlNodes.add(node.parent);(childrenMap[node.parent]||[]).forEach(s=>hlNodes.add(s.id));}
    D.links.forEach(l=>{
      const s=typeof l.source==='object'?l.source.id:l.source,t=typeof l.target==='object'?l.target.id:l.target;
      if(hlNodes.has(s)&&hlNodes.has(t))hlLinks.add(l);
    });
  } else {
    const neighborIds=new Set();
    neighborIds.add(node.id);
    D.links.forEach(l=>{
      const s=typeof l.source==='object'?l.source.id:l.source,t=typeof l.target==='object'?l.target.id:l.target;
      if(s===node.id){neighborIds.add(t);hlLinks.add(l);}
      if(t===node.id){neighborIds.add(s);hlLinks.add(l);}
    });
    if(node.parent)neighborIds.add(node.parent);
    if(childrenMap[node.id])childrenMap[node.id].forEach(c=>neighborIds.add(c.id));
    neighborIds.forEach(id=>hlNodes.add(id));
    D.links.forEach(l=>{
      const s=typeof l.source==='object'?l.source.id:l.source,t=typeof l.target==='object'?l.target.id:l.target;
      if(hlNodes.has(s)&&hlNodes.has(t))hlLinks.add(l);
    });
  }

  // Clear ALL fixed positions first to avoid conflicts
  D.nodes.forEach(n=>{delete n.fx;delete n.fy;delete n.fz;n.vx*=0.3;n.vy*=0.3;n.vz*=0.3;});

  // Set fixed positions only for focused node and its highlight group
  node.fx=0;node.fy=0;node.fz=0;

  if(nt==='head'||nt==='group'){
    const dc=childrenMap[node.id]||[];
    const total=dc.length;
    dc.forEach((c,i)=>{
      const angle=(i/Math.max(total,1))*Math.PI*2;
      const R=nt==='head'?130:100;
      c.fx=R*Math.cos(angle);c.fy=R*Math.sin(angle);c.fz=0;
      const gc=childrenMap[c.id]||[];
      gc.forEach((g,gi)=>{
        const ga=(gi/Math.max(gc.length,1))*Math.PI*2;
        g.fx=c.fx+55*Math.cos(ga);g.fy=c.fy+55*Math.sin(ga);g.fz=0;
      });
    });
    if(node.parent){
      const pD=D.nodes.find(n=>n.id===node.parent);
      if(pD){pD.fx=0;pD.fy=-160;pD.fz=0;}
    }

    // Push non-focused nodes deep behind focal cluster so they never sit in front.
    const backgroundNodes=D.nodes.filter(n=>!hlNodes.has(n.id));
    backgroundNodes.forEach((n,i)=>{
      const angle=(i/Math.max(backgroundNodes.length,1))*Math.PI*2;
      const R=520;
      n.fx=R*Math.cos(angle);
      n.fy=R*Math.sin(angle);
      n.fz=-1200;
    });
  } else {
    const neighborIds=new Set();
    neighborIds.add(node.id);
    D.links.forEach(l=>{
      const s=typeof l.source==='object'?l.source.id:l.source,t=typeof l.target==='object'?l.target.id:l.target;
      if(s===node.id)neighborIds.add(t);
      if(t===node.id)neighborIds.add(s);
    });
    if(node.parent)neighborIds.add(node.parent);
    if(childrenMap[node.id])childrenMap[node.id].forEach(c=>neighborIds.add(c.id));
    const neighbors=D.nodes.filter(n=>neighborIds.has(n.id)&&n.id!==node.id);
    neighbors.forEach((n,i)=>{
      const angle=(i/Math.max(neighbors.length,1))*Math.PI*2;
      const R=node.node_type==='verdict'?120:90;
      n.fx=R*Math.cos(angle);n.fy=R*Math.sin(angle);n.fz=0;
    });
  }

  // Gently reheat simulation instead of rebuilding graph
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
  Graph.d3Force('charge').strength(-250);
  Graph.reheat(800);
  setTimeout(()=>{Graph.cameraPosition({x:0,y:0,z:400},{x:0,y:0,z:0},900);},100);
}

function exitFocusMode(){
  focusMode=false;
  selectedHeadId=null;
  hlNodes.clear();hlLinks.clear();
  // Remove all fixed positions gently
  D.nodes.forEach(n=>{
    delete n.fx;delete n.fy;delete n.fz;
    n.vx*=0.5;n.vy*=0.5;n.vz*=0.5;
  });
  if(layoutMode==='force'){
    // For force layout, just let physics settle naturally
    Graph.reheat(600);
  } else {
    setLayout(layoutMode);
  }
  const ctrls=Graph.controls();
  if(ctrls)ctrls.autoRotate=rotating;
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
  hideTooltip();
}

function buildGraph(){
  Graph=ForceGraph3D()(document.getElementById('graph'))
    .graphData(D)
    .nodeId('id')
    .nodeLabel(node=>node.label||'')
    .nodeThreeObject(makeNode)
    .nodeThreeObjectExtend(false)
    .nodeOpacity(nodeOpacity)
    .linkSource('source')
    .linkTarget('target')
    .linkColor(linkColor)
    .linkWidth(linkWidth)
    .linkOpacity(0.8)
    .linkCurvature(linkCurvatureFn)
    .linkDirectionalParticles(linkDirectionalParticles)
    .linkDirectionalParticleSpeed(0.006)
    .linkDirectionalParticleWidth(2)
    .linkDirectionalParticleColor(linkDirectionalParticleColor)
    .linkDirectionalParticleResolution(4)
    .backgroundColor('#050508')
    .onNodeClick(node=>{
      if(!node)return;
      if(node.node_type==='head' && focusMode && selectedHeadId===node.id){
        exitFocusMode();
        return;
      }
      enterFocusMode(node);
    })
    .onNodeHover(node=>{
      canvas.style.cursor=node?'pointer':'default';
      if(node){hoveredNode=node;showTooltip(node,node.__screenX||0,node.__screenY||0);}
      else{hoveredNode=null;hideTooltip();}
    })
    .onBackgroundClick(()=>{
      if(focusMode){exitFocusMode();return;}
      hlNodes.clear();hlLinks.clear();
      Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
      hideTooltip();
    });

  const scene=Graph.scene();
  scene.add(new THREE.AmbientLight(0xffffff,0.65));
  const d1=new THREE.DirectionalLight(0xffffff,0.85);d1.position.set(200,300,400);scene.add(d1);
  const d2=new THREE.DirectionalLight(0xffffff,0.3);d2.position.set(-200,-100,-300);scene.add(d2);

  // Per-link distance AND strength: belongs_to pulls tight, cross_category stretches far
  const linkForce=Graph.d3Force('link');
  linkForce.distance(l=>{
    const t=l.type||'';
    if(t==='cross_category') return 150;
    const d=l.distance;
    if(d) return d;
    if(t==='belongs_to') return 25;
    if(t==='informs') return 60;
    if(t==='CONFIRMS'||t==='AMPLIFIES') return 100;
    if(t==='CONTRADICTS'||t==='DAMPENS') return 120;
    if(t==='TRIGGERS'||t==='CAUSES') return 110;
    return 100;
  });
  linkForce.strength(l=>{
    const t=l.type||'';
    if(t==='belongs_to') return 1.5;
    if(t==='informs') return 0.8;
    if(t==='cross_category') return 0.2;
    if(t==='CONFIRMS'||t==='AMPLIFIES') return 0.4;
    if(t==='CONTRADICTS'||t==='DAMPENS') return 0.3;
    if(t==='TRIGGERS'||t==='CAUSES') return 0.5;
    if(t==='CONTEXTUALIZES') return 0.2;
    if(t==='CORRELATES') return 0.1;
    return 0.3;
  });
  Graph.d3Force('charge').strength(-250);
  Graph.d3Force('headCenter',function(alpha){
    if(focusMode)return;
    D.nodes.filter(n=>n.node_type==='head').forEach(n=>{
      if(n.fx==null){n.vx-=(n.x||0)*0.06*alpha;n.vy-=(n.y||0)*0.06*alpha;n.vz-=(n.z||0)*0.06*alpha;}
    });
  });

  // Set initial positions so children start near parents
  const headNodes=D.nodes.filter(n=>n.node_type==='head');
  const headAngle=Math.PI*2/Math.max(headNodes.length,1);
  headNodes.forEach((h,i)=>{
    const a=i*headAngle;
    const R=150;h.x=R*Math.cos(a);h.y=R*Math.sin(a);h.z=0;
  });
  const gdNodes=D.nodes.filter(n=>n.node_type==='group');
  gdNodes.forEach(g=>{
    const p=D.nodes.find(n=>n.id===g.parent);
    if(p){g.x=(p.x||0)+(Math.random()-0.5)*60;g.y=(p.y||0)+(Math.random()-0.5)*60;g.z=(Math.random()-0.5)*40;}
  });
  const childNodes=D.nodes.filter(n=>n.node_type==='child');
  childNodes.forEach(c=>{
    const pid=c.parent;
    const p=D.nodes.find(n=>n.id===pid);
    if(p){c.x=(p.x||0)+(Math.random()-0.5)*30;c.y=(p.y||0)+(Math.random()-0.5)*30;c.z=(Math.random()-0.5)*20;}
    else{const R=150+Math.random()*100;const a=Math.random()*Math.PI*2;c.x=R*Math.cos(a);c.y=R*Math.sin(a);c.z=(Math.random()-0.5)*50;}
  });
  const vdNodes=D.nodes.filter(n=>n.node_type==='verdict');
  vdNodes.forEach((v,i)=>{
    const a=i*(Math.PI*2)/Math.max(vdNodes.length,1);const R=350;
    v.x=R*Math.cos(a);v.y=R*Math.sin(a);v.z=0;
  });
  Graph.graphData(D);

  canvas=document.querySelector('#graph canvas');
  if(showLabels)applyLabels();

  Graph.onEngineStop(()=>{const c=Graph.controls();if(c){c.autoRotate=rotating;c.autoRotateSpeed=0.5;}});
  setTimeout(()=>{const c=Graph.controls();if(c){c.autoRotate=rotating;c.autoRotateSpeed=0.5;c.enableDamping=true;c.dampingFactor=0.08;}},800);

  document.getElementById('sn').textContent=D.meta.node_count;
  document.getElementById('se').textContent=D.meta.edge_count;
  document.getElementById('sc').textContent=D.communities.filter(c=>D.nodes.some(n=>n.community===c.id)).length;
}

document.addEventListener('mousemove',function(e){
  if(hoveredNode)showTooltip(hoveredNode,e.clientX,e.clientY);
},{passive:false});

function applyLabels(){
  if(!Graph)return;
  if(showLabels){
    Graph.nodeThreeObjectExtend(true).nodeThreeObject(node=>{
      const group=makeNode(node);group.add(createLabelSprite(node));return group;
    });
  }else{
    Graph.nodeThreeObjectExtend(false).nodeThreeObject(makeNode);
  }
}

function rebuildGraph(){
  Graph.graphData(D);
}

function toggleLabels(){
  showLabels=!showLabels;
  document.getElementById('btn-labels').classList.toggle('active',showLabels);
  applyLabels();
}

function toggleRotation(){
  rotating=!rotating;
  document.getElementById('btn-rotate').classList.toggle('active',rotating);
  const c=Graph.controls();if(c)c.autoRotate=rotating;
}

function toggleEdges(){
  edgesVisible=!edgesVisible;
  document.getElementById('btn-edges').classList.toggle('active',edgesVisible);
  Graph.linkColor(linkColor).linkWidth(linkWidth).linkOpacity(edgesVisible?0.8:0);
}

function resetCamera(){
  Graph.cameraPosition({x:0,y:0,z:500},{x:0,y:0,z:0},900);
  hlNodes.clear();hlLinks.clear();
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
  hideTooltip();
}

function clearHighlight(){
  if(focusMode)exitFocusMode();
  hlNodes.clear();hlLinks.clear();
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
  hideTooltip();
  document.getElementById('cat-filter').value='all';
  document.getElementById('sig-filter').value='all';
  document.getElementById('type-filter').value='all';
  document.getElementById('edge-filter').value='all';
}

function highlightNeighbors(){
  if(!focusMode&&hlNodes.size===0)return;
  const first=hlNodes.values().next().value;
  if(!first)return;
  const node=D.nodes.find(n=>n.id===first);
  if(node)enterFocusMode(node);
}

function toggleShapeDropdown(){
  const dd=document.getElementById('shape-dropdown');
  dd.classList.toggle('show');
}

function setShape(shape, el){
  currentShape=shape;
  document.getElementById('shape-label').text=shape.charAt(0).toUpperCase()+shape.slice(1);
  document.getElementById('shape-label').textContent=shape.charAt(0).toUpperCase()+shape.slice(1);
  document.querySelectorAll('.sd-item').forEach(el=>el.classList.remove('active'));
  if(el){el.classList.add('active');}
  document.getElementById('shape-dropdown').classList.remove('show');
  Graph.nodeThreeObjectExtend(showLabels).nodeThreeObject(showLabels?node=>{const g=makeNode(node);g.add(createLabelSprite(node));return g;}:makeNode);
}

function setCharge(v){
  document.getElementById('sv-charge').textContent=v;
  Graph.d3Force('charge').strength(+v);
}

function setLinkDist(v){
  document.getElementById('sv-dist').textContent=v;
  linkDistScale=+v/120;
  Graph.d3Force('link').distance(l=>{
    const t=l.type||'';
    if(t==='cross_category') return 150*linkDistScale;
    const d=l.distance || (t==='belongs_to' ? 25 : 100);
    return d*linkDistScale;
  });
}

function setCurvature(v){
  linkCurvature=v/100;
  document.getElementById('sv-curve').textContent=(v/100).toFixed(2);
  Graph.linkCurvature(linkCurvatureFn);
}

function setGlobalOpacity(v){
  globalOpacity=v/100;
  document.getElementById('sv-opacity').textContent=v+'%';
  Graph.nodeOpacity(nodeOpacity);
}

function setNodeScale(v){
  nodeScale=v/100;
  document.getElementById('sv-scale').textContent=nodeScale.toFixed(1)+'x';
  Graph.nodeThreeObjectExtend(showLabels).nodeThreeObject(showLabels?node=>{const g=makeNode(node);g.add(createLabelSprite(node));return g;}:makeNode);
}

function setEdgeWidthMult(v){
  edgeWidthMult=v/50;
  document.getElementById('sv-ewidth').textContent=edgeWidthMult.toFixed(1)+'x';
  Graph.linkWidth(linkWidth);
}

function setLayout(mode){
  focusMode=false;
  layoutMode=mode;
  document.getElementById('btn-force').classList.toggle('active',mode==='force');
  document.getElementById('btn-radial').classList.toggle('active',mode==='radial');
  document.getElementById('btn-hierarchy').classList.toggle('active',mode==='hierarchy');

  if(mode==='radial'){
    D.nodes.forEach(n=>{delete n.fx;delete n.fy;delete n.fz;});
    const heads=D.nodes.filter(n=>n.node_type==='head');
    const angleStep=(2*Math.PI)/Math.max(heads.length,1);
    heads.forEach((h,i)=>{const a=i*angleStep,R=280;h.fx=R*Math.cos(a);h.fy=R*Math.sin(a);h.fz=0;});
    D.nodes.filter(n=>n.node_type==='verdict').forEach((v,vi)=>{
      const a=vi*(2*Math.PI)/Math.max(D.nodes.filter(n=>n.node_type==='verdict').length,1),R=400;
      v.fx=R*Math.cos(a);v.fy=R*Math.sin(a);v.fz=0;
    });
    D.nodes.filter(n=>n.node_type==='group').forEach(g=>{
      const p=D.nodes.find(n2=>n2.id===g.parent);
      if(p&&p.fx!=null){const oR=80+Math.random()*40,oA=Math.random()*2*Math.PI;
        g.fx=p.fx+oR*Math.cos(oA);g.fy=p.fy+oR*Math.sin(oA);g.fz=(Math.random()-0.5)*60;}
    });
    D.nodes.filter(n=>n.node_type==='child').forEach(c=>{
      const p=D.nodes.find(n2=>n2.id===c.parent);
      if(p&&p.fx!=null){const oR=40+Math.random()*60,oA=Math.random()*2*Math.PI;
        c.fx=p.fx+oR*Math.cos(oA);c.fy=p.fy+oR*Math.sin(oA);c.fz=(Math.random()-0.5)*80;}
      else{const oR=200+Math.random()*100,oA=Math.random()*2*Math.PI;
        c.fx=oR*Math.cos(oA);c.fy=oR*Math.sin(oA);c.fz=(Math.random()-0.5)*100;}
    });
    Graph.d3Force('charge').strength(-250);
    Graph.cameraPosition({x:0,y:0,z:800},{x:0,y:0,z:0},900);
  }else if(mode==='hierarchy'){
    D.nodes.forEach(n=>{delete n.fx;delete n.fy;delete n.fz;});
    const heads=D.nodes.filter(n=>n.node_type==='head');
    const headSpread=150;
    heads.forEach((h,i)=>{h.fx=(i-(heads.length-1)/2)*headSpread;h.fy=280;h.fz=0;});
    D.nodes.filter(n=>n.node_type==='verdict').forEach((v,i)=>{
      v.fx=(i-(D.nodes.filter(n2=>n2.node_type==='verdict').length-1)/2)*headSpread;v.fy=-300;v.fz=0;
    });
    D.nodes.filter(n=>n.node_type==='group').forEach(g=>{
      const p=D.nodes.find(n2=>n2.id===g.parent);
      if(p&&p.fx!=null){const sibs=D.nodes.filter(n2=>n2.parent===g.parent&&n2.node_type==='group');
        const idx=sibs.indexOf(g);g.fx=p.fx+(idx-(sibs.length-1)/2)*40;g.fy=p.fy-80;g.fz=0;}
    });
    const children=D.nodes.filter(n=>n.node_type==='child');
    const byParent={};children.forEach(c2=>{const p2=c2.parent||'orphan';if(!byParent[p2])byParent[p2]=[];byParent[p2].push(c2);});
    Object.keys(byParent).forEach(pid=>{
      const pp=D.nodes.find(n2=>n2.id===pid);const bx=pp?pp.fx:0,by=pp?pp.fy:0;
      byParent[pid].forEach((c2,ci)=>{c2.fx=bx+(ci-(byParent[pid].length-1)/2)*20;c2.fy=by-60-Math.random()*80;c2.fz=(Math.random()-0.5)*40;});
    });
    (byParent.orphan||[]).forEach((c2,i)=>{c2.fx=(i-((byParent.orphan||[]).length-1)/2)*30;c2.fy=0;c2.fz=(Math.random()-0.5)*100;});
    Graph.d3Force('charge').strength(-250);
    Graph.cameraPosition({x:0,y:0,z:900},{x:0,y:0,z:0},900);
  }else{
    // Force mode: clear all fixed positions, let physics settle
    D.nodes.forEach(n=>{delete n.fx;delete n.fy;delete n.fz;n.vx*=0.1;n.vy*=0.1;n.vz*=0.1;});
    Graph.d3Force('charge').strength(-250);
  }
  Graph.reheat(800);
}

function filterCategory(cat){
  hlNodes.clear();hlLinks.clear();
  if(cat==='all'){Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);hideTooltip();return;}
  const headId='HEAD::'+cat;
  D.nodes.forEach(n=>{
    if(n.id===headId||n.node_type==='verdict'||n.community===2)hlNodes.add(n.id);
    if(n.parent===headId)hlNodes.add(n.id);
    if(n.node_type==='child'&&n.source_file&&n.source_file.startsWith(cat))hlNodes.add(n.id);
    if(n.node_type==='group'&&n.id.startsWith('GROUP::'+cat))hlNodes.add(n.id);
    if(n.parent&&n.parent.startsWith('GROUP::'+cat))hlNodes.add(n.id);
  });
  D.links.forEach(l=>{
    const s=typeof l.source==='object'?l.source.id:l.source;
    const t=typeof l.target==='object'?l.target.id:l.target;
    if(hlNodes.has(s)&&hlNodes.has(t))hlLinks.add(l);
  });
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
}

function filterSignal(sig){
  hlNodes.clear();hlLinks.clear();
  if(sig==='all'){Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);return;}
  D.nodes.forEach(n=>{if(n.signal===sig||n.node_type==='head'||n.node_type==='verdict')hlNodes.add(n.id);});
  D.links.forEach(l=>{
    const s=typeof l.source==='object'?l.source.id:l.source;const t=typeof l.target==='object'?l.target.id:l.target;
    if(hlNodes.has(s)&&hlNodes.has(t))hlLinks.add(l);
  });
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
}

function filterNodeType(nt){
  hlNodes.clear();hlLinks.clear();
  if(nt==='all'){Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);return;}
  D.nodes.forEach(n=>{if(n.node_type===nt)hlNodes.add(n.id);});
  D.links.forEach(l=>{
    const s=typeof l.source==='object'?l.source.id:l.source;const t=typeof l.target==='object'?l.target.id:l.target;
    if(hlNodes.has(s)&&hlNodes.has(t))hlLinks.add(l);
  });
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
}

function filterEdgeType(et){
  hlNodes.clear();hlLinks.clear();
  if(et==='all'){Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);return;}
  D.links.forEach(l=>{if(l.type===et)hlLinks.add(l);});
  hlLinks.forEach(l=>{
    const s=typeof l.source==='object'?l.source.id:l.source;const t=typeof l.target==='object'?l.target.id:l.target;
    hlNodes.add(s);hlNodes.add(t);
  });
  Graph.nodeOpacity(nodeOpacity).linkColor(linkColor).linkWidth(linkWidth);
}

document.addEventListener('click',e=>{
  if(!e.target.closest('#shape-btn-wrap'))document.getElementById('shape-dropdown').classList.remove('show');
});

let touchCount=0;
document.addEventListener('touchstart',e=>{if(e.touches.length===3){e.preventDefault();return;}},{passive:false});
document.addEventListener('touchmove',e=>{
  if(e.touches.length===3){e.preventDefault();rotating=!rotating;const c=Graph.controls();if(c)c.autoRotate=rotating;}
},{passive:false});

buildGraph();
</script>
</body>
</html>"""