"""
build_knowledge_graph.py — Parse data/{SYMBOL}_data.md and build an interactive
3D knowledge graph HTML.

Usage:
    python build_knowledge_graph.py RELIANCE            # build HTML
    python build_knowledge_graph.py RELIANCE --check    # print parsed nodes only
"""

from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── Section → (category, financial-group) ──────────────────────────────────────
SECTION_MAP: dict[str, tuple[str, str | None]] = {
    "Fundamentals":        ("fundamental",    None),
    "Technical Indicators":("technical",      None),
    "Balance Sheet":       ("financial",      "Balance Sheet"),
    "Profit and Loss":     ("financial",      "P&L"),
    "Cash Flow":           ("financial",      "Cash Flow"),
    "Quarterly Results":   ("financial",      "Quarterly Result"),
    "Shareholding Pattern":("financial",      "Share Holding"),
    "Announcements":       ("announcement",   None),
    "News":                ("news",           None),
    "Market Context":      ("market_context", None),
}

WEIGHT: dict[str, float] = {
    "fundamental":    1.5,
    "technical":      1.2,
    "financial":      0.8,
    "announcement":   0.6,
    "news":           0.5,
    "market_context": 1.0,
}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class ParsedNode:
    label:     str
    category:  str
    group:     str | None     # financial sub-group, else None
    signal:    str            # positive | negative | neutral | mixed
    value_text:str
    summary:   str
    context:   str            # Analysis / Trend (longer text)
    relates:   list[str]      # raw label strings from "relates to …"
    date:      str            # captured_at from frontmatter


# ── Parsing helpers ────────────────────────────────────────────────────────────

def _extract_signal(text: str) -> str:
    """Return 'positive' | 'negative' | 'neutral' | 'mixed' from sentiment text."""
    t = text.lower()
    if "📈" in text or "bullish" in t:
        return "positive"
    if "📉" in text or "bearish" in t:
        return "negative"
    if "mixed" in t:
        return "mixed"
    return "neutral"


def _field(content: str, *names: str) -> str:
    """Return first matching **Name:** field value from node content block."""
    for name in names:
        m = re.search(rf'\*\*{re.escape(name)}:\*\*\s*(.+?)(?=\n\*\*|\Z)', content, re.DOTALL)
        if m:
            return m.group(1).strip()
    return ""


def _extract_value(content: str) -> str:
    """Extract value_text — handles both single-value and multi-period formats."""
    # Multi-period: **Values:** Mar 2026: X | Mar 2025: Y ...
    mv = re.search(r'\*\*Values:\*\*\s*(.+?)(?=\n|$)', content)
    if mv:
        return mv.group(1).strip()

    # Sentiment is on the same line as Value: strip it
    sv = re.search(r'\*\*Value:\*\*\s*(.+?)(?:\s*\|\s*\*\*Sentiment)', content)
    if sv:
        return sv.group(1).strip()

    # Fallback: full Value line
    fv = re.search(r'\*\*Value:\*\*\s*(.+?)(?=\n|$)', content)
    if fv:
        return fv.group(1).strip()

    return ""


def _extract_relates(content: str) -> list[str]:
    """Return list of node labels from 'relates to X, Y, Z' clauses."""
    results: list[str] = []
    for m in re.finditer(r'relates?\s+to\s+([A-Za-z_0-9,\s]+?)(?=[.\n]|$)', content, re.IGNORECASE):
        raw = m.group(1)
        parts = re.split(r',\s*|\s+and\s+', raw)
        for p in parts:
            p = p.strip().rstrip(".")
            if p and re.match(r'^[A-Za-z_0-9]+$', p):
                results.append(p)
    return list(dict.fromkeys(results))  # deduplicate, preserve order


def _extract_sentiment_from_block(content: str) -> str:
    """Extract sentiment signal from a node content block."""
    sm = re.search(r'\*\*Sentiment:\*\*\s*([^\n|]+)', content)
    if sm:
        return _extract_signal(sm.group(1))
    return "neutral"


# ── Main parser ────────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> dict[str, str]:
    """Parse YAML frontmatter block from top of file."""
    m = re.match(r'^---\n(.+?)\n---\n', content, re.DOTALL)
    if not m:
        return {}
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            meta[k.strip()] = v.strip()
    return meta


def parse_section(sec_name: str, sec_content: str, date: str) -> list[ParsedNode]:
    """Parse all ### nodes from one ## section block."""
    if sec_name not in SECTION_MAP:
        return []

    cat, group = SECTION_MAP[sec_name]
    nodes: list[ParsedNode] = []

    # Split on ### node headers
    parts = re.split(r'^### (.+)$', sec_content, flags=re.MULTILINE)
    # parts[0] = section intro text; then alternating [name, content, name, content …]
    i = 1
    while i < len(parts) - 1:
        label   = parts[i].strip()
        content = parts[i + 1]
        i += 2

        signal    = _extract_sentiment_from_block(content)
        value_txt = _extract_value(content)
        summary   = _field(content, "Summary")
        context   = _field(content, "Analysis", "Trend", "Performance")
        relates   = _extract_relates(content)

        nodes.append(ParsedNode(
            label=label, category=cat, group=group,
            signal=signal, value_text=value_txt,
            summary=summary, context=context,
            relates=relates, date=date,
        ))

    return nodes


def parse_md(md_path: Path) -> tuple[dict[str, str], list[ParsedNode]]:
    """
    Parse a _data.md file.

    Returns:
        meta:  frontmatter dict (symbol, horizon, sector, captured_at, …)
        nodes: list of ParsedNode (one per ### block)
    """
    content = md_path.read_text(encoding="utf-8")
    meta    = parse_frontmatter(content)
    date    = meta.get("captured_at", "unknown")

    # Split file into ## sections
    parts = re.split(r'^## (.+)$', content, flags=re.MULTILINE)
    # parts[0] = frontmatter + intro; then alternating [section_name, section_content …]

    all_nodes: list[ParsedNode] = []
    i = 1
    while i < len(parts) - 1:
        sec_name    = parts[i].strip()
        sec_content = parts[i + 1]
        i += 2
        all_nodes.extend(parse_section(sec_name, sec_content, date))

    return meta, all_nodes


# ── Check / print mode ─────────────────────────────────────────────────────────

def print_check(meta: dict[str, str], nodes: list[ParsedNode]) -> None:
    """Print a human-readable summary for user verification."""
    symbol  = meta.get("symbol", "?")
    horizon = meta.get("horizon", "?")
    sector  = meta.get("sector", "?")
    date    = meta.get("captured_at", "?")

    print(f"\n{'='*70}")
    print(f"  KNOWLEDGE FILE: {symbol}  |  {horizon}  |  {sector}  |  {date}")
    print(f"{'='*70}")

    # Group by category for display
    by_cat: dict[str, list[ParsedNode]] = {}
    for n in nodes:
        by_cat.setdefault(n.category, []).append(n)

    SIGNALS = {"positive": "📈", "negative": "📉", "neutral": "➡️ ", "mixed": "⚡"}
    total = 0

    for cat, cat_nodes in by_cat.items():
        print(f"\n  [{cat.upper()}]  ({len(cat_nodes)} nodes)")
        print(f"  {'─'*66}")
        for n in cat_nodes:
            icon = SIGNALS.get(n.signal, "?")
            val  = (n.value_text[:45] + "…") if len(n.value_text) > 45 else n.value_text
            summ = (n.summary[:60] + "…")    if len(n.summary)     > 60 else n.summary
            rel  = ", ".join(n.relates[:3]) + ("…" if len(n.relates) > 3 else "")
            print(f"  {icon} {n.label:<35} val: {val}")
            if summ:
                print(f"     summary: {summ}")
            if rel:
                print(f"     relates: {rel}")
            total += 1

    pos  = sum(1 for n in nodes if n.signal == "positive")
    neg  = sum(1 for n in nodes if n.signal == "negative")
    neut = sum(1 for n in nodes if n.signal == "neutral")
    mix  = sum(1 for n in nodes if n.signal == "mixed")
    edge_count = sum(len(n.relates) for n in nodes)

    print(f"\n{'='*70}")
    print(f"  TOTAL: {total} nodes  |  📈{pos} bullish  📉{neg} bearish  ➡️ {neut} neutral  ⚡{mix} mixed")
    print(f"  EDGES (relates-to): {edge_count} references parsed")
    print(f"{'='*70}\n")


# ── Signal / node style constants ─────────────────────────────────────────────

SIGNAL_STYLE: dict[str, dict] = {
    "positive": {"community": 1, "color": "#1c3a2a", "border_color": "#00FF88"},
    "negative": {"community": 2, "color": "#3a1c1c", "border_color": "#FF3355"},
    "neutral":  {"community": 0, "color": "#1e2230", "border_color": "#6B7280"},
    "mixed":    {"community": 3, "color": "#2e2a10", "border_color": "#FFB800"},
}

HEAD_STYLE  = {"community": 4, "color": "#0a0e18", "border_color": "#4A90E2", "val": 20}
GROUP_STYLE = {"community": 5, "color": "#0d1520", "border_color": "#5B8DEF", "val": 12}


# ── Graph data builder ─────────────────────────────────────────────────────────

def build_graph_data(symbol: str, meta: dict[str, str], nodes: list[ParsedNode]) -> dict:
    """
    Convert parsed nodes into a 3d-force-graph compatible {nodes, links} dict.

    Node hierarchy: HEAD → GROUP (financial only) → child
    Edge types: belongs_to (structural), relates_to (semantic cross-links)
    """
    date = meta.get("captured_at", "unknown")

    graph_nodes: list[dict] = []
    graph_links: list[dict] = []

    # Collect categories and financial sub-groups present in data
    categories  = dict.fromkeys(n.category for n in nodes)   # ordered, deduplicated
    fin_groups  = dict.fromkeys(n.group for n in nodes if n.group)

    # HEAD nodes
    head_id: dict[str, str] = {}
    for cat in categories:
        hid = f"HEAD::{cat}"
        head_id[cat] = hid
        graph_nodes.append({
            "id": hid,
            "label": cat.replace("_", " ").title(),
            "community": HEAD_STYLE["community"],
            "signal": "neutral",
            "value_text": "",
            "context": "",
            "weight": 2.0,
            "color": HEAD_STYLE["color"],
            "border_color": HEAD_STYLE["border_color"],
            "val": HEAD_STYLE["val"],
            "degree": 0,
            "node_type": "head",
            "parent": None,
        })

    # GROUP nodes (financial sub-groups only)
    group_id: dict[str, str] = {}
    fin_head = head_id.get("financial")
    for grp in fin_groups:
        gid = f"GROUP::financial::{grp}"
        group_id[grp] = gid
        graph_nodes.append({
            "id": gid,
            "label": grp,
            "community": GROUP_STYLE["community"],
            "signal": "neutral",
            "value_text": "",
            "context": "",
            "weight": 1.0,
            "color": GROUP_STYLE["color"],
            "border_color": GROUP_STYLE["border_color"],
            "val": GROUP_STYLE["val"],
            "degree": 0,
            "node_type": "group",
            "parent": fin_head,
        })
        if fin_head:
            graph_links.append({"source": gid, "target": fin_head, "type": "belongs_to"})

    child_id: dict[str, str] = {}
    used_ids: set[str] = set()

    for n in nodes:
        base = f"{symbol}|{n.category}|{n.group or ''}|{n.label}|{date}"
        cid = base
        suffix = 1
        while cid in used_ids:
            cid = f"{base}_{suffix}"
            suffix += 1
        used_ids.add(cid)
        label_key = (n.label, n.category, n.group or "")
        child_id[label_key] = cid

    label_to_keys: dict[str, list[tuple[str, str, str]]] = {}
    for label_key in child_id:
        lbl = label_key[0]
        label_to_keys.setdefault(lbl, []).append(label_key)

    for n in nodes:
        label_key = (n.label, n.category, n.group or "")
        cid    = child_id[label_key]
        style  = SIGNAL_STYLE.get(n.signal, SIGNAL_STYLE["neutral"])
        parent = group_id.get(n.group) if n.group else None
        parent = parent or head_id.get(n.category, "")

        graph_nodes.append({
            "id": cid,
            "label": n.label,
            "community": style["community"],
            "signal": n.signal,
            "value_text": n.value_text,
            "context": n.context or n.summary,
            "weight": WEIGHT.get(n.category, 1.0),
            "color": style["color"],
            "border_color": style["border_color"],
            "val": max(4, 4 + min(len(n.relates), 4)),
            "degree": len(n.relates),
            "node_type": "child",
            "parent": parent,
        })

        if parent:
            graph_links.append({"source": cid, "target": parent, "type": "belongs_to"})

    for n in nodes:
        src_key = (n.label, n.category, n.group or "")
        src = child_id[src_key]
        for rel in n.relates:
            keys = label_to_keys.get(rel)
            if not keys:
                continue
            tgt = child_id[keys[0]]
            if tgt != src:
                graph_links.append({"source": src, "target": tgt, "type": "relates_to"})

    return {"nodes": graph_nodes, "links": graph_links}


# ── HTML renderer ──────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{symbol} · Knowledge Graph · {date}</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #0f0f1a; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }}
#graph {{ flex: 1; }}
#sidebar {{ width: 300px; background: #1a1a2e; border-left: 1px solid #2a2a4e; display: flex; flex-direction: column; overflow: hidden; }}
#search-wrap {{ padding: 12px; border-bottom: 1px solid #2a2a4e; }}
#search {{ width: 100%; background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0; padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }}
#search:focus {{ border-color: #4E79A7; }}
#search-results {{ max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid #2a2a4e; display: none; }}
.search-item {{ padding: 4px 8px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.search-item:hover {{ background: #2a2a4e; }}
#info-panel {{ padding: 14px; border-bottom: 1px solid #2a2a4e; min-height: 160px; max-height: 340px; overflow-y: auto; }}
#info-panel h3 {{ font-size: 11px; color: #666; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em; }}
#info-content {{ font-size: 13px; color: #ccc; line-height: 1.6; }}
#info-content .field {{ margin-bottom: 5px; }}
#info-content .field b {{ color: #e0e0e0; }}
#info-content .empty {{ color: #444; font-style: italic; }}
.neighbor-link {{ display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid #333; }}
.neighbor-link:hover {{ background: #2a2a4e; }}
#neighbors-list {{ max-height: 160px; overflow-y: auto; margin-top: 4px; }}
#legend-wrap {{ flex: 1; overflow-y: auto; padding: 12px; }}
#legend-wrap h3 {{ font-size: 11px; color: #666; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em; }}
.legend-item {{ display: flex; align-items: center; gap: 8px; padding: 5px 4px; cursor: pointer; border-radius: 4px; font-size: 12px; }}
.legend-item:hover {{ background: #2a2a4e; }}
.legend-item.dimmed {{ opacity: 0.3; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
.legend-label {{ flex: 1; }}
.legend-count {{ color: #555; font-size: 11px; }}
#legend-controls {{ display: flex; gap: 6px; margin-bottom: 10px; }}
#legend-controls button {{ flex: 1; background: #0f0f1a; border: 1px solid #3a3a5e; color: #888; padding: 4px 0; border-radius: 4px; font-size: 11px; cursor: pointer; }}
#legend-controls button:hover {{ border-color: #4E79A7; color: #e0e0e0; }}
#stats {{ padding: 10px 14px; border-top: 1px solid #2a2a4e; font-size: 11px; color: #444; }}
.sig-pos {{ color: #00FF88; }} .sig-neg {{ color: #FF3355; }} .sig-neu {{ color: #6B7280; }} .sig-mix {{ color: #FFB800; }}
.sig-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }}
.badge-pos {{ background: rgba(0,255,136,0.12); color: #00FF88; border: 1px solid rgba(0,255,136,0.25); }}
.badge-neg {{ background: rgba(255,51,85,0.12); color: #FF3355; border: 1px solid rgba(255,51,85,0.25); }}
.badge-neu {{ background: rgba(107,114,128,0.15); color: #9CA3AF; border: 1px solid rgba(107,114,128,0.25); }}
.badge-mix {{ background: rgba(255,184,0,0.12); color: #FFB800; border: 1px solid rgba(255,184,0,0.25); }}
.metric-row {{ display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }}
.metric {{ background: rgba(255,255,255,0.03); border: 1px solid #2a2a4e; border-radius: 6px; padding: 5px 10px; font-size: 10px; color: #6B7280; text-align: center; flex: 1; min-width: 60px; }}
.metric b {{ display: block; font-size: 13px; color: #e0e0e0; font-weight: 700; margin-bottom: 1px; }}
.section-divider {{ border: none; border-top: 1px solid #2a2a4e; margin: 10px 0; }}
.edge-stat {{ display: inline-flex; align-items: center; gap: 4px; font-size: 10px; color: #475569; margin-right: 8px; }}
.edge-dot {{ width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }}
#neighbors-section h4 {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: #475569; margin-bottom: 6px; }}
.news-full {{ font-size: 11px; color: #94a3b8; line-height: 1.5; margin-top: 6px; word-break: break-word; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes…" autocomplete="off"/>
  </div>
  <div id="search-results"></div>
  <div id="info-panel">
    <h3>{symbol} &nbsp;·&nbsp; {sector} &nbsp;·&nbsp; {date}</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Legend</h3>
    <div id="legend-controls">
      <button onclick="toggleAllCommunities(false)">Show All</button>
      <button onclick="toggleAllCommunities(true)">Hide All</button>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">nodes: {n_nodes} &nbsp;·&nbsp; links: {n_links}</div>
</div>
<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND    = {legend_json};

function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

const nodesDS = new vis.DataSet(RAW_NODES.map(n => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  _signal: n.signal, _value: n.value_text, _context: n.context,
  _type: n.node_type, _degree: n.degree, _community: n.community,
  _full_label: n.full_label,
}})));

const edgesDS = new vis.DataSet(RAW_EDGES.map((e, i) => ({{
  id: i, from: e.from, to: e.to,
  dashes: e.dashes, width: e.width, color: e.color,
  title: e.title, _type: e.edge_type,
  arrows: {{ to: {{ enabled: true, scaleFactor: 0.4 }} }},
}})));

const container = document.getElementById('graph');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  physics: {{
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.02,
      springLength: 100,
      springConstant: 0.12,
      damping: 0.4,
      avoidOverlap: 0.8,
    }},
    stabilization: {{ iterations: 300, fit: true }},
  }},
  interaction: {{
    hover: true,
    tooltipDelay: 200,
    hideEdgesOnDrag: true,
    navigationButtons: false,
    keyboard: false,
  }},
  nodes: {{
    shape: 'dot',
    borderWidth: 1.5,
    scaling: {{
      label: {{
        enabled: true,
        min: 8,
        max: 20,
        maxVisible: 30,
        drawThreshold: 3,
      }},
    }},
  }},
  edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }}, selectionWidth: 3 }},
}});

network.once('stabilizationIterationsDone', () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
  network.fit();
}});

const SIG_CLASS = {{ positive:'sig-pos', negative:'sig-neg', neutral:'sig-neu', mixed:'sig-mix' }};
const SIG_BADGE = {{ positive:'badge-pos', negative:'badge-neg', neutral:'badge-neu', mixed:'badge-mix' }};
const SIG_LABEL = {{ positive:'Bullish', negative:'Bearish', neutral:'Neutral', mixed:'Mixed' }};
const TYPE_COLOR = {{ belongs_to: '#3b82f6', relates_to: '#a855f7' }};

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;

  const connectedEdges = network.getConnectedEdges(nodeId);
  const neighborIds = network.getConnectedNodes(nodeId);

  // Count edge types
  let belongsCount = 0, relatesCount = 0;
  connectedEdges.forEach(eid => {{
    const e = edgesDS.get(eid);
    if (e && e._type === 'belongs_to') belongsCount++;
    else if (e && e._type === 'relates_to') relatesCount++;
  }});

  // Build neighbor list with edge type indicator
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodesDS.get(nid);
    const c  = nb ? nb.color.background : '#555';
    const edgesTo = connectedEdges.filter(eid => {{
      const e = edgesDS.get(eid);
      return e && (e.from === nid || e.to === nid);
    }});
    const eType = edgesTo.length > 0 ? (edgesDS.get(edgesTo[0])._type || '') : '';
    const eDot = eType === 'relates_to'
      ? `<span class="edge-dot" style="background:#a855f7;margin-right:4px"></span>`
      : `<span class="edge-dot" style="background:#3b82f6;margin-right:4px"></span>`;
    return `<span class="neighbor-link" style="border-left-color:${{esc(c)}}" onclick="focusNode(${{JSON.stringify(nid)}})">${{eDot}}${{esc(nb ? nb.label : nid)}}</span>`;
  }}).join('');

  const sigBadge = SIG_BADGE[n._signal] || 'badge-neu';
  const sigLbl   = SIG_LABEL[n._signal] || (n._signal || 'Neutral');
  const typeLabel = n._type === 'head' ? 'Category Hub' : n._type === 'group' ? 'Sub-Group' : 'Data Node';

  // Full headline for news nodes
  const fullLabel = n._full_label && n._full_label !== n.label
    ? `<div class="news-full">${{esc(n._full_label)}}</div>` : '';

  const metricsHtml = `
    <div class="metric-row">
      <div class="metric"><b>${{n._degree || 0}}</b>connections</div>
      ${{belongsCount ? `<div class="metric"><b>${{belongsCount}}</b>structural</div>` : ''}}
      ${{relatesCount ? `<div class="metric"><b style="color:#a855f7">${{relatesCount}}</b>semantic</div>` : ''}}
    </div>`;

  const edgeStatsHtml = (belongsCount || relatesCount) ? `
    <div style="margin-top:8px">
      ${{belongsCount ? `<span class="edge-stat"><span class="edge-dot" style="background:#3b82f6"></span>${{belongsCount}} structural</span>` : ''}}
      ${{relatesCount ? `<span class="edge-stat"><span class="edge-dot" style="background:#a855f7"></span>${{relatesCount}} semantic</span>` : ''}}
    </div>` : '';

  document.getElementById('info-content').innerHTML = `
    <div class="field" style="display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap">
      <b style="font-size:14px">${{esc(n.label)}}</b>
      <span class="sig-badge ${{sigBadge}}">${{sigLbl}}</span>
    </div>
    <div style="color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:0.06em;margin:3px 0 6px">${{typeLabel}}</div>
    ${{fullLabel}}
    ${{n._value ? `<hr class="section-divider"><div style="color:#94a3b8;font-size:12px">${{esc(n._value)}}</div>` : ''}}
    ${{n._context ? `<hr class="section-divider"><div style="color:#c9d1d9;font-size:11px;line-height:1.6">${{esc(n._context)}}</div>` : ''}}
    ${{metricsHtml}}
    ${{edgeStatsHtml}}
    ${{neighborIds.length ? `<hr class="section-divider"><div id="neighbors-section"><h4>Connected (${{neighborIds.length}})</h4><div id="neighbors-list">${{neighborItems}}</div></div>` : ''}}
  `;
}}

window.focusNode = function(nodeId) {{
  network.focus(nodeId, {{ scale: 1.4, animation: true }});
  network.selectNodes([nodeId]);
  showInfo(nodeId);
}};

let hoveredNodeId = null;
network.on('hoverNode', p => {{ hoveredNodeId = p.node; container.style.cursor = 'pointer'; }});
network.on('blurNode',  () => {{ hoveredNodeId = null;  container.style.cursor = 'default'; }});
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    showInfo(params.nodes[0]);
  }} else if (hoveredNodeId === null) {{
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }}
}});
container.addEventListener('click', () => {{
  if (hoveredNodeId !== null) {{
    showInfo(hoveredNodeId);
    network.selectNodes([hoveredNodeId]);
  }}
}});

const searchInput   = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n =>
    (n.label || '').toLowerCase().includes(q) ||
    (n.full_label || '').toLowerCase().includes(q)
  ).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.full_label || n.label;
    el.style.borderLeft = `3px solid ${{n.color.background}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      network.focus(n.id, {{ scale: 1.5, animation: true }});
      network.selectNodes([n.id]);
      showInfo(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

const hiddenCommunities = new Set();
function toggleAllCommunities(hide) {{
  document.querySelectorAll('.legend-item').forEach(el => hide ? el.classList.add('dimmed') : el.classList.remove('dimmed'));
  LEGEND.forEach(c => {{ if (hide) hiddenCommunities.add(c.cid); else hiddenCommunities.delete(c.cid); }});
  nodesDS.update(RAW_NODES.map(n => ({{ id: n.id, hidden: hide }})));
}}

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {{
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.innerHTML = `<div class="legend-dot" style="background:${{c.color}}"></div>
    <span class="legend-label">${{esc(c.label)}}</span>
    <span class="legend-count">${{c.count}}</span>`;
  item.onclick = () => {{
    if (hiddenCommunities.has(c.cid)) {{
      hiddenCommunities.delete(c.cid);
      item.classList.remove('dimmed');
    }} else {{
      hiddenCommunities.add(c.cid);
      item.classList.add('dimmed');
    }}
    nodesDS.update(RAW_NODES
      .filter(n => n.community === c.cid)
      .map(n => ({{ id: n.id, hidden: hiddenCommunities.has(c.cid) }})));
  }};
  legendEl.appendChild(item);
}});
</script>
</body>
</html>
"""


def render_html(symbol: str, meta: dict[str, str], graph_data: dict) -> str:
    """Render graph_data into a standalone HTML using vis.js 2D force layout."""
    raw_nodes = graph_data["nodes"]
    raw_links = graph_data["links"]

    # Compute degree from links so node size reflects connectivity
    deg: dict[str, int] = {}
    for lnk in raw_links:
        deg[lnk["source"]] = deg.get(lnk["source"], 0) + 1
        deg[lnk["target"]] = deg.get(lnk["target"], 0) + 1
    max_deg = max(deg.values(), default=1) or 1

    vis_nodes = []
    for n in raw_nodes:
        nt  = n.get("node_type", "child")
        d   = deg.get(n["id"], 1)
        clr = n.get("border_color", "#6B7280")   # bright signal/type color

        if nt == "head":
            size, font_size = 30, 14
        elif nt == "group":
            size, font_size = 18, 12
        else:
            size      = round(10 + 20 * (d / max_deg), 1)
            font_size = 12 if d >= max_deg * 0.15 else 11

        full_label = n["label"].replace("_", " ")
        val_txt    = (n.get("value_text") or "")
        ctx_txt    = (n.get("context")    or "")

        # Plain-text tooltip (newer vis-network treats title strings as text, not HTML)
        cat = n.get("node_type", "child")
        tooltip_parts = [full_label]
        if val_txt:
            tooltip_parts.append(val_txt[:120])
        if ctx_txt:
            tooltip_parts.append(ctx_txt[:200])
        tooltip = "\n".join(tooltip_parts)

        # Truncate labels so they don't overflow nodes in the canvas
        # News/announcement headlines are always shortened — full text is in the side panel
        display_label = full_label
        parent_id = n.get("parent") or ""
        if "news" in parent_id.lower() or "announcement" in parent_id.lower():
            display_label = full_label[:25] + "…" if len(full_label) > 25 else full_label
        elif len(display_label) > 35:
            display_label = display_label[:33] + "…"

        vis_nodes.append({
            "id":         n["id"],
            "label":      display_label,
            "full_label": full_label,
            "color": {
                "background": clr,
                "border":     clr,
                "highlight":  {"background": "#ffffff", "border": clr},
                "hover":      {"background": "#eeeeee", "border": clr},
            },
            "size":       size,
            "font":       {"size": font_size, "color": "#e0e0e0" if d >= max_deg * 0.15 else "rgba(255,255,255,0.55)"},
            "title":      tooltip,
            "community":  n.get("community", 0),
            "signal":     n.get("signal", "neutral"),
            "value_text": val_txt[:200],
            "context":    ctx_txt[:400],
            "node_type":  nt,
            "degree":     d,
        })

    vis_edges = []
    for lnk in raw_links:
        ltype = lnk.get("type", "relates_to")
        is_structural = ltype == "belongs_to"
        vis_edges.append({
            "from":      lnk["source"],
            "to":        lnk["target"],
            "edge_type": ltype,
            "dashes":    not is_structural,
            "width":     2 if is_structural else 2,
            "color": {
                "color":   "#3b82f6" if is_structural else "#a855f7",
                "opacity": 0.5 if is_structural else 0.55,
                "highlight": "#ffffff",
                "hover":     "#ffffff",
            },
            "title": "structural (belongs to)" if is_structural else "semantic (relates to)",
        })

    legend = [
        {"cid": 0, "color": "#6B7280", "label": "Neutral",      "count": sum(1 for n in raw_nodes if n.get("signal") == "neutral")},
        {"cid": 1, "color": "#00FF88", "label": "Bullish",       "count": sum(1 for n in raw_nodes if n.get("signal") == "positive")},
        {"cid": 2, "color": "#FF3355", "label": "Bearish",       "count": sum(1 for n in raw_nodes if n.get("signal") == "negative")},
        {"cid": 3, "color": "#FFB800", "label": "Mixed",         "count": sum(1 for n in raw_nodes if n.get("signal") == "mixed")},
        {"cid": 4, "color": "#4A90E2", "label": "Category Hub",  "count": sum(1 for n in raw_nodes if n.get("node_type") == "head")},
        {"cid": 5, "color": "#5B8DEF", "label": "Sub-Group",     "count": sum(1 for n in raw_nodes if n.get("node_type") == "group")},
    ]
    legend = [l for l in legend if l["count"] > 0]

    return _HTML_TEMPLATE.format(
        symbol      = symbol,
        date        = meta.get("captured_at", "unknown"),
        sector      = meta.get("sector", "—"),
        n_nodes     = len(raw_nodes),
        n_links     = len(raw_links),
        nodes_json  = json.dumps(vis_nodes, ensure_ascii=False, separators=(",", ":")),
        edges_json  = json.dumps(vis_edges, ensure_ascii=False, separators=(",", ":")),
        legend_json = json.dumps(legend,    ensure_ascii=False, separators=(",", ":")),
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Build knowledge graph from _data.md")
    ap.add_argument("symbol", help="NSE stock symbol, e.g. RELIANCE")
    ap.add_argument("--check", action="store_true",
                    help="Print parsed nodes only — no HTML output")
    args = ap.parse_args()

    symbol   = args.symbol.upper()
    data_dir = Path(__file__).parent / "data"
    md_path  = data_dir / f"{symbol}_data.md"

    if not md_path.exists():
        print(f"[ERROR] {md_path} not found. Run fetch_phase1_data.py {symbol} first.")
        sys.exit(1)

    print(f"[1/3] Parsing {md_path.name} …")
    meta, nodes = parse_md(md_path)
    print(f"[1/3] Done — {len(nodes)} nodes extracted.")

    print_check(meta, nodes)

    if args.check:
        return

    print(f"[2/3] Building graph data …")
    graph_data = build_graph_data(symbol, meta, nodes)
    n_nodes = len(graph_data["nodes"])
    n_links = len(graph_data["links"])
    print(f"[2/3] Done — {n_nodes} graph nodes, {n_links} links.")

    print(f"[3/3] Rendering HTML …")
    out_dir = Path(__file__).parent / "graphify-out" / "stocks" / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    date    = meta.get("captured_at", "unknown")
    out_path = out_dir / f"{date}.html"
    out_path.write_text(render_html(symbol, meta, graph_data), encoding="utf-8")
    print(f"[3/3] Done — {out_path}")
    print(f"\n  Open in browser:  file://{out_path.resolve()}\n")


if __name__ == "__main__":
    main()
