"""
knowledge_graph.py — Analysis knowledge graph builder + 3D HTML renderer.

Layer: graph/
Role: Converts a list of analysis Nodes + admin_view into an interactive
      3D force-directed graph using the same 3d-force-graph + Three.js stack
      as the graphify codebase visualiser.

Output: self-contained HTML file — open directly in any browser.

Node visual encoding:
  Community (colour group) = data category (technical / fundamental / news /
                              announcement / context / verdict)
  Node size (val)           = signal weight
  Node colour               = signal direction (bullish=green, bearish=red,
                              neutral/mixed=category accent)

Edge types:
  agreement     — green glow
  contradiction — red glow
  same_category — dim white (structural cohesion only)
  verdict_support — amber
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Community / category config ────────────────────────────────────────────────

_CATEGORIES: list[dict[str, Any]] = [
    {"id": 0, "key": "technical",    "name": "Technical",    "color": "#4FC3F7"},
    {"id": 1, "key": "fundamental",  "name": "Fundamental",  "color": "#81C784"},
    {"id": 2, "key": "news",         "name": "News",         "color": "#FFB74D"},
    {"id": 3, "key": "announcement", "name": "Announcement", "color": "#F06292"},
    {"id": 4, "key": "context",      "name": "Context",      "color": "#CE93D8"},
    {"id": 5, "key": "verdict",      "name": "Verdict",      "color": "#FF7043"},
]

_CAT_BY_KEY   = {c["key"]: c for c in _CATEGORIES}
_SIGNAL_COLOR = {
    "bullish":  "#00e676",
    "positive": "#00e676",
    "bearish":  "#ff5252",
    "negative": "#ff5252",
    "neutral":  None,   # falls back to category colour
    "mixed":    "#ffd740",
}
_EDGE_COLOR = {
    "agreement":      "rgba(0,230,118,0.7)",
    "contradiction":  "rgba(255,82,82,0.7)",
    "same_category":  "rgba(255,255,255,0.08)",
    "verdict_support":"rgba(255,171,64,0.7)",
}


# ── Public API ────────────────────────────────────────────────────────────────

def build_graph(
    nodes: list[Any],
    admin_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert analysis nodes → graph dict {nodes, links, communities, meta}.

    Args:
        nodes:      list[Node] from all data agents.
        admin_view: optional dict from formatter containing agreement /
                    contradiction / verdict lists.

    Returns:
        Plain dict ready to be JSON-serialised into the HTML template.
    """
    admin_view = admin_view or {}
    graph_nodes: list[dict] = []
    graph_links: list[dict] = []
    node_ids: set[str] = set()

    # ── Data nodes ────────────────────────────────────────────────────────────
    for node in nodes:
        nid  = node.node_id if hasattr(node, "node_id") else str(node.get("node_id", ""))
        cat  = str(node.category.value if hasattr(node.category, "value") else node.category)
        sig  = str(node.signal.value   if hasattr(node.signal,   "value") else node.signal) if hasattr(node, "signal") else "neutral"
        val  = str(getattr(node, "value", ""))
        wt   = float(getattr(node, "weight", 1.0))
        cat_cfg = _CAT_BY_KEY.get(cat, _CATEGORIES[0])
        color   = _SIGNAL_COLOR.get(sig) or cat_cfg["color"]
        label   = _short_label(nid)

        graph_nodes.append({
            "id":          nid,
            "label":       label,
            "community":   cat_cfg["id"],
            "signal":      sig,
            "value_text":  val[:120],
            "weight":      round(wt, 3),
            "color":       color,
            "val":         max(2, wt * 4),
            "degree":      0,   # updated below
            "source_file": f"{cat} · {sig}",
        })
        node_ids.add(nid)

    # ── Same-category links (structural cohesion) ─────────────────────────────
    by_cat: dict[int, list[str]] = {}
    for n in graph_nodes:
        by_cat.setdefault(n["community"], []).append(n["id"])

    for nids in by_cat.values():
        for i in range(len(nids)):
            for j in range(i + 1, min(i + 4, len(nids))):
                graph_links.append({
                    "source": nids[i],
                    "target": nids[j],
                    "type":   "same_category",
                    "color":  _EDGE_COLOR["same_category"],
                })

    # ── Agreement links ───────────────────────────────────────────────────────
    for link in admin_view.get("agreements", []):
        src, tgt = link.get("node_id_a"), link.get("node_id_b")
        if src in node_ids and tgt in node_ids:
            graph_links.append({"source": src, "target": tgt,
                                 "type": "agreement", "color": _EDGE_COLOR["agreement"]})

    # ── Contradiction links ───────────────────────────────────────────────────
    for link in admin_view.get("contradictions", []):
        src, tgt = link.get("node_id_positive"), link.get("node_id_negative")
        if src in node_ids and tgt in node_ids:
            graph_links.append({"source": src, "target": tgt,
                                 "type": "contradiction", "color": _EDGE_COLOR["contradiction"]})

    # ── Verdict nodes + support links ─────────────────────────────────────────
    # admin_view["verdicts"] is a dict keyed by category name (from formatter.py)
    verdicts_raw = admin_view.get("verdicts", {})
    verdicts_list = (
        [{"category": cat, **v} for cat, v in verdicts_raw.items()]
        if isinstance(verdicts_raw, dict)
        else verdicts_raw
    )
    for verdict in verdicts_list:
        cat_name = verdict.get("category", "unknown")
        vid  = f"verdict::{cat_name}"
        vsig = verdict.get("direction", verdict.get("signal", "neutral"))
        graph_nodes.append({
            "id":          vid,
            "label":       f"{cat_name.upper()} verdict",
            "community":   5,
            "signal":      vsig,
            "value_text":  vsig,
            "weight":      2.5,
            "color":       _SIGNAL_COLOR.get(vsig) or _CATEGORIES[5]["color"],
            "val":         10,
            "degree":      0,
            "source_file": f"verdict · {cat_name}",
        })
        node_ids.add(vid)
        for support_nid in verdict.get("supporting_node_ids", []):
            if support_nid in node_ids:
                graph_links.append({
                    "source": support_nid, "target": vid,
                    "type": "verdict_support", "color": _EDGE_COLOR["verdict_support"],
                })

    # ── Update degree counts ──────────────────────────────────────────────────
    degree: dict[str, int] = {n["id"]: 0 for n in graph_nodes}
    for lnk in graph_links:
        degree[lnk["source"]] = degree.get(lnk["source"], 0) + 1
        degree[lnk["target"]] = degree.get(lnk["target"], 0) + 1
    for n in graph_nodes:
        n["degree"] = degree.get(n["id"], 0)

    return {
        "nodes":       graph_nodes,
        "links":       graph_links,
        "communities": _CATEGORIES,
        "meta": {
            "node_count": len(graph_nodes),
            "edge_count": len(graph_links),
        },
    }


def render_3d_html(
    graph_data: dict[str, Any],
    title: str = "Stocxi Knowledge Graph",
    output_path: str | Path | None = None,
) -> str:
    """Render graph_data as a self-contained interactive 3D HTML file.

    Uses 3d-force-graph + Three.js — same stack as graphify output.

    Args:
        graph_data:  dict from build_graph().
        title:       Page title shown in the UI header.
        output_path: If given, saves HTML here.

    Returns:
        Full HTML string.
    """
    data_json = json.dumps(graph_data, ensure_ascii=False)
    html = _HTML_TEMPLATE.replace("__GRAPH_DATA__", data_json).replace("__TITLE__", title)

    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        logger.info("knowledge_graph: saved → %s (%d nodes, %d edges)",
                    p, graph_data["meta"]["node_count"], graph_data["meta"]["edge_count"])

    return html


# ── Helper ─────────────────────────────────────────────────────────────────────

def _short_label(node_id: str) -> str:
    """'technical::RSI_14::bullish' → 'RSI_14'"""
    parts = node_id.split("::")
    return parts[1] if len(parts) >= 2 else node_id


# ── HTML template ─────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; overflow: hidden; }
  #graph { width: 100vw; height: 100vh; }
  #ui {
    position: fixed; top: 16px; right: 16px; z-index: 100;
    background: rgba(13,17,23,0.96); border: 1px solid #30363d;
    border-radius: 12px; padding: 16px 18px; min-width: 260px; max-width: 300px;
    backdrop-filter: blur(16px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  #title-bar {
    font-size: 12px; color: #f0f6fc; margin-bottom: 12px;
    letter-spacing: .8px; text-transform: uppercase; font-weight: 700;
    border-bottom: 1px solid #30363d; padding-bottom: 8px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  #search {
    width: 100%; background: #0d1117; border: 2px solid #30363d;
    border-radius: 8px; color: #e6edf3; padding: 8px 12px;
    font-size: 13px; outline: none; margin-bottom: 10px; transition: all .2s;
  }
  #search:focus { border-color: #00e676; box-shadow: 0 0 0 3px rgba(0,230,118,.12); background: #161b22; }
  #node-info {
    font-size: 12px; color: #8b949e; min-height: 60px; margin-bottom: 10px;
    padding: 10px; background: rgba(255,255,255,.03);
    border-radius: 8px; border: 1px solid rgba(48,54,61,.6); line-height: 1.5;
  }
  #node-info strong { color: #e6edf3; display: block; margin-bottom: 4px; font-size: 13px; }
  #controls { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 10px; }
  button {
    background: #21262d; border: 1px solid #30363d; color: #e6edf3;
    padding: 5px 10px; border-radius: 6px; font-size: 11px; cursor: pointer;
    transition: all .15s; font-weight: 500;
  }
  button:hover { background: #30363d; border-color: #484f58; }
  button.active { background: #1f6feb; border-color: #388bfd; color: #fff; }
  #legend { max-height: 220px; overflow-y: auto; }
  #legend::-webkit-scrollbar { width: 3px; }
  #legend::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }
  .legend-item {
    display: flex; align-items: center; gap: 8px; padding: 7px 6px;
    font-size: 12px; cursor: pointer; border-radius: 6px;
    transition: all .2s; margin-bottom: 2px;
  }
  .legend-item:hover { background: rgba(255,255,255,.08); transform: translateX(2px); }
  .legend-dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; border: 2px solid rgba(255,255,255,.15); }
  .legend-count { margin-left: auto; color: #484f58; font-size: 11px; }
  #stats { font-size: 11px; color: #6e7681; margin-top: 10px; padding-top: 8px; border-top: 1px solid #21262d; }
  #edge-legend { margin-top: 8px; display: flex; flex-direction: column; gap: 4px; }
  .edge-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #8b949e; }
  .edge-line { width: 22px; height: 2px; border-radius: 2px; flex-shrink: 0; }
</style>
</head>
<body>
<div id="graph"></div>
<div id="ui">
  <div id="title-bar">__TITLE__</div>
  <input id="search" placeholder="&#128269; Search indicators..." type="text">
  <div id="node-info">Click any node to inspect</div>
  <div id="controls">
    <button id="btn-rotate" class="active" onclick="toggleRotate()">&#9654; Rotate</button>
    <button onclick="resetCamera()">Reset</button>
    <button id="btn-labels" onclick="toggleLabels()">Labels</button>
    <button id="btn-layout" onclick="cycleLayout()">Layout: 3D</button>
    <button id="btn-edges" class="active" onclick="toggleEdges()">Edges</button>
  </div>
  <div id="legend"></div>
  <div id="edge-legend">
    <div class="edge-item"><div class="edge-line" style="background:#00e676"></div> Agreement</div>
    <div class="edge-item"><div class="edge-line" style="background:#ff5252"></div> Contradiction</div>
    <div class="edge-item"><div class="edge-line" style="background:#ffab40"></div> Verdict support</div>
  </div>
  <div id="stats"></div>
</div>

<script src="https://unpkg.com/three@0.158.0/build/three.min.js"></script>
<script src="https://unpkg.com/3d-force-graph@1.73.2/dist/3d-force-graph.min.js"></script>
<script>
const GRAPH_DATA = __GRAPH_DATA__;

let rotating    = true;
let showLabels  = false;
let edgesVisible= true;
let layoutMode  = 0;
const layouts   = ['3D Force', 'Sphere', 'Clusters'];

const highlightNodes = new Set();
const highlightLinks = new Set();

// ── Colour helpers ─────────────────────────────────────────────────────────
function nodeColor(node) {
  if (!highlightNodes.size) return node.color;
  return highlightNodes.has(node.id) ? node.color : node.color + '18';
}
function linkColor(link) {
  if (!highlightLinks.size) return edgesVisible ? (link.color || 'rgba(255,255,255,0.12)') : 'rgba(255,255,255,0)';
  return highlightLinks.has(link)
    ? (link.color || 'rgba(100,200,255,0.8)')
    : 'rgba(255,255,255,0.03)';
}
function linkWidth(link) {
  if (!edgesVisible) return 0;
  if (highlightLinks.has(link)) return 2.5;
  if (link.type === 'same_category') return 0.3;
  return 1.0;
}

// ── Build graph ────────────────────────────────────────────────────────────
const Graph = ForceGraph3D()(document.getElementById('graph'))
  .graphData(GRAPH_DATA)
  .nodeId('id')
  .nodeLabel(n => `<div style="background:rgba(13,17,23,.92);border:1px solid #30363d;border-radius:8px;padding:8px 12px;font-size:12px;color:#e6edf3;max-width:260px">
    <strong style="color:${n.color}">${n.label}</strong><br>
    <span style="color:#8b949e">${n.source_file}</span><br>
    <span style="font-size:11px;color:#6e7681">${n.value_text}</span>
  </div>`)
  .nodeColor(nodeColor)
  .nodeVal('val')
  .nodeOpacity(0.92)
  .linkSource('source')
  .linkTarget('target')
  .linkColor(linkColor)
  .linkWidth(linkWidth)
  .linkOpacity(0.85)
  .linkDirectionalParticles(l => (l.type === 'agreement' || l.type === 'contradiction') ? 2 : 0)
  .linkDirectionalParticleSpeed(0.004)
  .linkDirectionalParticleColor(l => l.color || '#fff')
  .backgroundColor('#0d1117')
  .onNodeClick(node => {
    highlightNodes.clear(); highlightLinks.clear();
    if (node) {
      highlightNodes.add(node.id);
      GRAPH_DATA.links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        if (s === node.id || t === node.id) {
          highlightLinks.add(l); highlightNodes.add(s); highlightNodes.add(t);
        }
      });
    }
    Graph.nodeColor(nodeColor).linkColor(linkColor).linkWidth(linkWidth);
    if (node) {
      const comm = GRAPH_DATA.communities.find(c => c.id === node.community);
      document.getElementById('node-info').innerHTML = `
        <strong style="color:${node.color}">${node.label}</strong>
        <span style="color:#58a6ff">${node.source_file}</span><br>
        <span style="color:#8b949e;font-size:11px">${node.value_text || ''}</span><br>
        <span style="color:#484f58;font-size:11px">Weight: ${node.weight} &nbsp;|&nbsp; ${highlightNodes.size - 1} connections</span>
      `;
      const dist = 100;
      const r = 1 + dist / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
      Graph.cameraPosition({x: node.x*r, y: node.y*r, z: node.z*r}, node, 800);
    }
  })
  .onBackgroundClick(() => {
    highlightNodes.clear(); highlightLinks.clear();
    Graph.nodeColor(nodeColor).linkColor(linkColor).linkWidth(linkWidth);
    document.getElementById('node-info').textContent = 'Click any node to inspect';
  });

// ── Auto-rotate ────────────────────────────────────────────────────────────
Graph.onEngineStop(() => {
  const c = Graph.controls();
  if (c) { c.autoRotate = rotating; c.autoRotateSpeed = 1.2; }
});
setTimeout(() => {
  const c = Graph.controls();
  if (c) { c.autoRotate = true; c.autoRotateSpeed = 1.2; }
}, 600);

// ── Legend ─────────────────────────────────────────────────────────────────
const legendEl = document.getElementById('legend');
const nodeCounts = {};
GRAPH_DATA.nodes.forEach(n => { nodeCounts[n.community] = (nodeCounts[n.community] || 0) + 1; });

GRAPH_DATA.communities.forEach(comm => {
  if (!nodeCounts[comm.id]) return;
  const div = document.createElement('div');
  div.className = 'legend-item';
  div.innerHTML = `<div class="legend-dot" style="background:${comm.color}"></div>
    <span>${comm.name}</span><span class="legend-count">${nodeCounts[comm.id]}</span>`;
  div.onclick = () => filterCommunity(comm.id);
  legendEl.appendChild(div);
});

// ── Stats ──────────────────────────────────────────────────────────────────
document.getElementById('stats').innerHTML =
  `${GRAPH_DATA.meta.node_count} nodes &nbsp;|&nbsp; ${GRAPH_DATA.meta.edge_count} edges`;

// ── Controls ───────────────────────────────────────────────────────────────
function toggleRotate() {
  rotating = !rotating;
  document.getElementById('btn-rotate').classList.toggle('active', rotating);
  const c = Graph.controls(); if (c) c.autoRotate = rotating;
}
function resetCamera() {
  Graph.cameraPosition({x:0, y:0, z:600}, {x:0,y:0,z:0}, 800);
  highlightNodes.clear(); highlightLinks.clear();
  Graph.nodeColor(nodeColor).linkColor(linkColor).linkWidth(linkWidth);
  document.getElementById('node-info').textContent = 'Click any node to inspect';
}
function toggleLabels() {
  showLabels = !showLabels;
  document.getElementById('btn-labels').classList.toggle('active', showLabels);
  if (showLabels) {
    Graph.nodeThreeObjectExtend(true).nodeThreeObject(node => {
      const canvas = document.createElement('canvas');
      canvas.width = 512; canvas.height = 72;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = 'rgba(13,17,23,0.88)';
      ctx.beginPath(); ctx.roundRect(4, 8, 504, 56, 8); ctx.fill();
      ctx.strokeStyle = node.color; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(4, 8, 504, 56, 8); ctx.stroke();
      const txt = node.label.length > 24 ? node.label.slice(0,22)+'…' : node.label;
      ctx.font = 'bold 26px sans-serif'; ctx.textAlign = 'center';
      ctx.textBaseline = 'middle'; ctx.fillStyle = node.color;
      ctx.fillText(txt, 256, 36);
      const tex = new THREE.CanvasTexture(canvas);
      const mat = new THREE.SpriteMaterial({map:tex, depthWrite:false, transparent:true});
      const sprite = new THREE.Sprite(mat);
      sprite.scale.set(42, 8, 1); sprite.position.set(0, 9, 0);
      return sprite;
    });
  } else {
    Graph.nodeThreeObjectExtend(false).nodeThreeObject(null);
  }
}
function toggleEdges() {
  edgesVisible = !edgesVisible;
  document.getElementById('btn-edges').classList.toggle('active', edgesVisible);
  Graph.linkColor(linkColor).linkWidth(linkWidth).linkOpacity(edgesVisible ? 0.85 : 0);
}
function cycleLayout() {
  layoutMode = (layoutMode + 1) % 3;
  document.getElementById('btn-layout').textContent = 'Layout: ' + layouts[layoutMode];
  if (layoutMode === 1) {
    const N = GRAPH_DATA.nodes.length;
    GRAPH_DATA.nodes.forEach((n, i) => {
      const phi = Math.acos(-1 + (2*i)/N), theta = Math.sqrt(N*Math.PI)*phi, R = 220;
      n.fx = R*Math.cos(theta)*Math.sin(phi); n.fy = R*Math.sin(theta)*Math.sin(phi); n.fz = R*Math.cos(phi);
    });
    Graph.cameraPosition({x:0,y:0,z:600},{x:0,y:0,z:0},800);
  } else if (layoutMode === 2) {
    const comms = {};
    GRAPH_DATA.nodes.forEach(n => { (comms[n.community] = comms[n.community]||[]).push(n); });
    Object.keys(comms).forEach((cid, ci, keys) => {
      const theta = (ci/keys.length)*2*Math.PI, R=280;
      comms[cid].forEach((n,ni) => {
        const r=60, a=(ni/comms[cid].length)*2*Math.PI;
        n.fx = R*Math.cos(theta)+r*Math.cos(a); n.fy = R*Math.sin(theta)+r*Math.sin(a); n.fz=(Math.random()-.5)*80;
      });
    });
  } else {
    GRAPH_DATA.nodes.forEach(n => { delete n.fx; delete n.fy; delete n.fz; });
    Graph.cameraPosition({x:0,y:0,z:600},{x:0,y:0,z:0},800);
  }
  Graph.graphData(GRAPH_DATA);
}
function filterCommunity(cid) {
  highlightNodes.clear(); highlightLinks.clear();
  const comm = GRAPH_DATA.communities.find(c => c.id === cid);
  GRAPH_DATA.nodes.forEach(n => { if (n.community === cid) highlightNodes.add(n.id); });
  GRAPH_DATA.links.forEach(l => {
    const s = typeof l.source==='object'?l.source.id:l.source;
    const t = typeof l.target==='object'?l.target.id:l.target;
    if (highlightNodes.has(s) && highlightNodes.has(t)) highlightLinks.add(l);
  });
  Graph.nodeColor(node => highlightNodes.has(node.id) ? node.color : node.color+'18')
       .linkColor(link => highlightLinks.has(link) ? (link.color||'rgba(100,200,255,0.7)') : 'rgba(255,255,255,0.02)')
       .linkWidth(link => highlightLinks.has(link) ? 2.0 : 0.1);
  document.getElementById('node-info').innerHTML =
    `<strong style="color:${comm.color}">${comm.name}</strong><br>
     <span style="color:#8b949e">${highlightNodes.size} nodes &nbsp;|&nbsp; ${highlightLinks.size} connections</span>`;
}

// ── Search ────────────────────────────────────────────────────────────────
document.getElementById('search').addEventListener('input', e => {
  const q = e.target.value.toLowerCase().trim();
  if (!q) {
    highlightNodes.clear(); highlightLinks.clear();
    Graph.nodeColor(nodeColor).linkColor(linkColor).linkWidth(linkWidth);
    document.getElementById('node-info').textContent = 'Click any node to inspect';
    return;
  }
  highlightNodes.clear(); highlightLinks.clear();
  const matched = GRAPH_DATA.nodes.filter(n =>
    n.label.toLowerCase().includes(q) || n.source_file.toLowerCase().includes(q) || n.value_text.toLowerCase().includes(q)
  );
  matched.forEach(n => highlightNodes.add(n.id));
  GRAPH_DATA.links.forEach(l => {
    const s = typeof l.source==='object'?l.source.id:l.source;
    const t = typeof l.target==='object'?l.target.id:l.target;
    if (highlightNodes.has(s)||highlightNodes.has(t)) {
      highlightLinks.add(l); highlightNodes.add(s); highlightNodes.add(t);
    }
  });
  const G = '#00e676';
  Graph.nodeColor(n => matched.some(m=>m.id===n.id) ? G : highlightNodes.has(n.id) ? G+'66' : n.color+'10')
       .linkColor(l => highlightLinks.has(l) ? 'rgba(0,230,118,0.7)' : 'rgba(255,255,255,0.02)')
       .linkWidth(l => highlightLinks.has(l) ? 3.0 : 0.05);
  document.getElementById('node-info').innerHTML = matched.length === 1
    ? `<strong style="color:${G}">${matched[0].label}</strong><br>
       <span style="color:#8b949e">${matched[0].source_file}</span><br>
       <span style="font-size:11px;color:#6e7681">${matched[0].value_text}</span>`
    : `<strong style="color:${G}">${matched.length} matches found</strong><br>
       <span style="color:#8b949e">${highlightNodes.size - matched.length} connected nodes</span>`;
});
</script>
</body>
</html>"""
