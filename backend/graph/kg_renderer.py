"""
kg_renderer.py — Knowledge graph HTML renderer with hierarchical layouts.

Generates self-contained HTML files with:
  - Hierarchical tree data structure
  - 4 layout engines: Force, Radial, Tree, Orbit
  - Focus/drill-down mode
  - Clean Three.js rendering (no 3d-force-graph wrapper)
  - Bloomberg-terminal aesthetic

Usage:
    from graph.kg_renderer import render_knowledge_graph
    html = render_knowledge_graph(tree_data, title="RELIANCE", horizon="short")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def render_knowledge_graph(
    tree_data: dict[str, Any],
    title: str = "Knowledge Graph",
    stock_name: str = "",
    horizon: str = "",
    output_path: str | Path | None = None,
) -> str:
    """Render tree_data as a self-contained interactive HTML file."""
    data_json = json.dumps(tree_data, ensure_ascii=False)

    html = _HTML_TEMPLATE.replace("__GRAPH_DATA__", data_json)
    html = html.replace("__STOCK_NAME__", stock_name or title)
    html = html.replace("__HORIZON__", horizon.upper())
    html = html.replace("__TITLE__", title)

    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        logger.info("kg_renderer: saved -> %s (%d nodes)", p, tree_data["meta"]["node_count"])

    return html


_HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#050508;--surface:#0a0a10;--surface-hover:#12121a;--border:rgba(255,255,255,0.06);
  --text:#e8e8f0;--text-secondary:#7a7a8a;--text-muted:#4a4a5a;
  --accent:#6366f1;--accent-hover:#818cf8;
  --technical:#3b82f6;--fundamental:#10b981;--financial:#f59e0b;
  --news:#ec4899;--announcement:#8b5cf6;--verdict:#a855f7;
  --positive:#00e676;--negative:#ff5252;--neutral:#78909c;--mixed:#ffab40;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:-apple-system,'SF Pro Text','SF Pro Display',BlinkMacSystemFont,system-ui,sans-serif;}
#canvas-container{width:100vw;height:100vh;position:fixed;top:0;left:0;z-index:1}

#sidebar{
  position:fixed;top:0;right:0;height:100vh;width:260px;z-index:100;
  background:rgba(10,10,16,0.95);border-left:1px solid var(--border);
  backdrop-filter:blur(32px) saturate(180%);
  display:flex;flex-direction:column;padding:0;overflow:hidden;
}
#debug{
  position:fixed;top:10px;left:10px;z-index:200;
  background:rgba(0,0,0,0.85);border:1px solid rgba(255,255,255,0.1);
  border-radius:8px;padding:10px 14px;font-size:11px;color:#aaa;
  font-family:monospace;max-width:280px;pointer-events:none;
}
.sb-section{padding:10px 12px;border-bottom:1px solid var(--border)}
.sb-section:last-child{border-bottom:none;flex:1;overflow-y:auto;min-height:0}
#hdr{display:flex;flex-direction:column;gap:2px}
#hdr-sup{font-size:9px;letter-spacing:3px;text-transform:uppercase;color:var(--accent);font-weight:700;opacity:0.7}
#hdr-title{font-size:14px;font-weight:800;color:#f8fafc;letter-spacing:-0.3px;line-height:1.3}

#search{width:100%;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:10px;
  color:var(--text);padding:8px 12px 8px 32px;font-size:11px;outline:none;
  transition:border .2s,box-shadow .2s;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' fill='%2364748b' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85zm-5.242.156a5 5 0 1 1 0-10 5 5 0 0 1 0 10z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:10px center}
#search:focus{border-color:rgba(99,102,241,0.5);box-shadow:0 0 0 3px rgba(99,102,241,0.08)}
#search::placeholder{color:#334155}

.ctrl-row{display:flex;gap:5px;flex-wrap:wrap}
button{background:rgba(255,255,255,0.03);border:1px solid var(--border);color:#475569;
  padding:7px 12px;border-radius:8px;font-size:10.5px;font-weight:600;cursor:pointer;
  transition:all .18s;letter-spacing:0.3px;font-family:inherit}
button:hover{background:rgba(99,102,241,0.06);border-color:rgba(99,102,241,0.3);color:#818cf8}
button.active{background:rgba(99,102,241,0.10);border-color:rgba(99,102,241,0.4);color:#818cf8;
  box-shadow:0 0 16px rgba(99,102,241,0.08)}

.layout-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.layout-btn{text-align:center;padding:8px 4px}
.layout-btn.active{background:rgba(99,102,241,0.15);border-color:rgba(99,102,241,0.5);color:#a78bfa}

.focus-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px}
.focus-btn{font-size:9.5px;padding:6px 4px}
.focus-btn.active{background:rgba(99,102,241,0.15);border-color:rgba(99,102,241,0.5);color:#a78bfa}

#node-info{background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;min-height:80px;transition:all .25s}
#node-info:hover{border-color:rgba(99,102,241,0.2)}
.ni-placeholder{color:#334155;font-size:12px;font-style:italic;padding:12px 0;text-align:center}
.ni-label{font-size:15px;font-weight:800;margin-bottom:3px;line-height:1.2}
.ni-cat{font-size:9px;text-transform:uppercase;letter-spacing:2.5px;opacity:0.45;margin-bottom:8px}
.ni-val{font-size:11.5px;color:#94a3b8;line-height:1.65;
  font-family:'JetBrains Mono','SF Mono','Fira Code',monospace;
  background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;word-break:break-word;margin-bottom:6px}
.ni-ctx{font-size:11px;color:#475569;line-height:1.5;font-style:italic;
  border-top:1px solid rgba(255,255,255,0.04);padding-top:6px;margin-top:4px}
.ni-summary{font-size:11px;color:#64748b;line-height:1.5;background:rgba(99,102,241,0.05);
  border-radius:8px;padding:8px 10px;margin-top:6px;border-left:2px solid var(--accent)}
.ni-meta{font-size:10px;color:#334155;margin-top:8px;display:flex;gap:8px;align-items:center}
.sig-badge{display:inline-block;padding:2px 10px;border-radius:20px;
  font-size:8.5px;font-weight:800;text-transform:uppercase;letter-spacing:1.5px}
.sb-pos{background:rgba(16,185,129,0.12);color:#34d399;border:1px solid rgba(16,185,129,0.25)}
.sb-neg{background:rgba(239,68,68,0.12);color:#f87171;border:1px solid rgba(239,68,68,0.25)}
.sb-neu{background:rgba(148,163,184,0.08);color:#94a3b8;border:1px solid rgba(148,163,184,0.18)}
.sb-mix{background:rgba(251,191,36,0.10);color:#fbbf24;border:1px solid rgba(251,191,36,0.22)}

#leg-title{font-size:9px;text-transform:uppercase;letter-spacing:3px;color:#334155;margin-bottom:6px;font-weight:800}
#legend{overflow-y:auto;flex:1;min-height:0}
#legend::-webkit-scrollbar{width:3px}
#legend::-webkit-scrollbar-thumb{background:rgba(99,102,241,0.2);border-radius:2px}
.leg-item{display:flex;align-items:center;gap:9px;padding:6px 8px;font-size:11px;
  cursor:pointer;border-radius:8px;transition:all .18s;margin-bottom:1px;color:#475569}
.leg-item:hover{background:rgba(255,255,255,0.03);color:#94a3b8;transform:translateX(2px)}
.leg-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;box-shadow:0 0 6px var(--dot-color,#4FC3F7)}
.leg-cnt{margin-left:auto;background:rgba(255,255,255,0.03);padding:1px 7px;border-radius:9px;font-size:9px;color:#334155;font-weight:600}

#stats-bar{display:flex;gap:2px;padding-top:10px;border-top:1px solid var(--border);margin-top:auto}
.stat{flex:1;text-align:center}
.stat-v{font-size:18px;font-weight:800;color:var(--accent);line-height:1}
.stat-l{font-size:8px;color:#334155;margin-top:2px;text-transform:uppercase;letter-spacing:2px;font-weight:600}

#tooltip{
  position:fixed;z-index:200;display:none;pointer-events:none;
  background:rgba(10,10,16,0.97);border:1px solid rgba(255,255,255,0.1);border-radius:10px;
  padding:12px 14px;max-width:300px;min-width:180px;
  backdrop-filter:blur(24px);box-shadow:0 8px 40px rgba(0,0,0,0.6);
}
.tt-label{font-size:13px;font-weight:700;color:#fff;line-height:1.3;margin-bottom:2px}
.tt-cat{font-size:8px;text-transform:uppercase;letter-spacing:2px;color:#4a4a5a;margin-bottom:6px}
.tt-row{font-size:10px;color:#4a4a5a;line-height:1.5}
.tt-row span{color:#7a7a8a}

.edge-tooltip{max-width:280px}
.edge-tt-type{font-size:10px;color:var(--accent);font-weight:700;margin-bottom:4px}
.edge-tt-desc{font-size:10px;color:#7a7a8a;line-height:1.4}
</style>
</head>
<body>
<div id="canvas-container"></div>

<div id="debug">
  <div>Nodes parsed: <span id="dbg-nodes">0</span></div>
  <div>Meshes: <span id="dbg-meshes">0</span></div>
  <div>Edges: <span id="dbg-edges">0</span></div>
  <div>Layout: <span id="dbg-layout">force</span></div>
  <div>Camera: <span id="dbg-cam">-</span></div>
  <div style="color:#ff5252;margin-top:4px" id="dbg-error"></div>
</div>

<div id="sidebar">
  <div class="sb-section" id="hdr">
    <div id="hdr-sup">Stocxi Knowledge Graph</div>
    <div id="hdr-title">__STOCK_NAME__ — __HORIZON__</div>
  </div>
  
  <div class="sb-section">
    <input id="search" placeholder="Search nodes..." type="text">
  </div>
  
  <div class="sb-section">
    <div id="leg-title">Layout</div>
    <div class="layout-grid">
      <button class="layout-btn active" data-layout="force">Force</button>
      <button class="layout-btn" data-layout="radial">Radial</button>
      <button class="layout-btn" data-layout="tree">Tree</button>
      <button class="layout-btn" data-layout="orbit">Orbit</button>
    </div>
  </div>
  
  <div class="sb-section">
    <div id="leg-title">Focus</div>
    <div class="focus-grid">
      <button class="focus-btn active" data-focus="all">All</button>
      <button class="focus-btn" data-focus="HEAD::technical">Technical</button>
      <button class="focus-btn" data-focus="HEAD::fundamental">Fundamental</button>
      <button class="focus-btn" data-focus="HEAD::financial">Financial</button>
      <button class="focus-btn" data-focus="HEAD::news">News</button>
      <button class="focus-btn" data-focus="HEAD::announcement">Announce</button>
    </div>
  </div>
  
  <div class="sb-section">
    <div id="node-info">
      <div class="ni-placeholder">Click any node to inspect</div>
    </div>
  </div>
  
  <div class="sb-section">
    <div class="ctrl-row">
      <button id="btn-labels" onclick="toggleLabels()">Labels</button>
      <button id="btn-edges" class="active" onclick="toggleEdges()">Edges</button>
      <button id="btn-rotate" class="active" onclick="toggleRotate()">Rotate</button>
      <button onclick="resetView()">Reset</button>
    </div>
  </div>
  
  <div class="sb-section" style="flex:1;overflow-y:auto;display:flex;flex-direction:column">
    <div id="leg-title">Categories</div>
    <div id="legend"></div>
  </div>
  
  <div class="sb-section" id="stats-bar">
    <div class="stat"><div class="stat-v" id="sn">0</div><div class="stat-l">Nodes</div></div>
    <div class="stat"><div class="stat-v" id="se">0</div><div class="stat-l">Edges</div></div>
    <div class="stat"><div class="stat-v" id="sg">0</div><div class="stat-l">Groups</div></div>
  </div>
</div>

<div id="tooltip">
  <div class="tt-label" id="tt-label"></div>
  <div class="tt-cat" id="tt-cat"></div>
  <div class="tt-row" id="tt-content"></div>
</div>

<script type="importmap">
{
  "imports": {
    "three": "https://unpkg.com/three@0.158.0/build/three.module.js",
    "three/addons/": "https://unpkg.com/three@0.158.0/examples/jsm/"
  }
}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
// ═══════════════════════════════════════════════════════════════════════════════
// KNOWLEDGE GRAPH RENDERER — Hierarchical 3D Visualization
// ═══════════════════════════════════════════════════════════════════════════════

const DATA = __GRAPH_DATA__;
const nodesById = new Map();
const treeNodes = new Map();
let currentLayout = 'force';
let focusNodeId = null;
let showLabels = false;
let showEdges = true;
let autoRotate = true;
let scene, camera, renderer, controls;
let nodeMeshes = new Map();
let edgeLines = new Map();
let labelSprites = new Map();
let animationId;
let orbitAngles = new Map(); // For orbit layout

// ═══════════════════════════════════════════════════════════════════════════════
// DATA PREPARATION
// ═══════════════════════════════════════════════════════════════════════════════

function prepareData() {
  // Build node lookup
  DATA.nodes.forEach(n => {
    nodesById.set(n.id, n);
    treeNodes.set(n.id, n);
  });
  
  // Build parent-child relationships
  DATA.nodes.forEach(n => {
    if (n.parent_id) {
      const parent = nodesById.get(n.parent_id);
      if (parent) {
        if (!parent.children) parent.children = [];
        if (!parent.children.includes(n.id)) {
          parent.children.push(n.id);
        }
      }
    }
  });
  
  // Initialize orbit angles
  DATA.nodes.forEach(n => {
    orbitAngles.set(n.id, Math.random() * Math.PI * 2);
  });
  
  // Update debug panel
  document.getElementById('dbg-nodes').textContent = DATA.nodes.length;
}

function getSubtree(nodeId) {
  const result = new Set([nodeId]);
  const node = nodesById.get(nodeId);
  if (!node) return result;
  
  function addChildren(nid) {
    const n = nodesById.get(nid);
    if (!n || !n.children) return;
    n.children.forEach(cid => {
      result.add(cid);
      addChildren(cid);
    });
  }
  
  addChildren(nodeId);
  return result;
}

function getFocusSet() {
  if (!focusNodeId || focusNodeId === 'all') {
    return new Set(DATA.nodes.map(n => n.id));
  }
  return getSubtree(focusNodeId);
}

// ═══════════════════════════════════════════════════════════════════════════════
// LAYOUT ENGINES
// ═══════════════════════════════════════════════════════════════════════════════

const LayoutEngines = {
  force: computeForceLayout,
  radial: computeRadialLayout,
  tree: computeTreeLayout,
  orbit: computeOrbitLayout,
};

function normalizePositions(positions) {
  // Compute bounding box
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;
  let minZ = Infinity, maxZ = -Infinity;
  
  positions.forEach(pos => {
    minX = Math.min(minX, pos.x); maxX = Math.max(maxX, pos.x);
    minY = Math.min(minY, pos.y); maxY = Math.max(maxY, pos.y);
    minZ = Math.min(minZ, pos.z); maxZ = Math.max(maxZ, pos.z);
  });
  
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const cz = (minZ + maxZ) / 2;
  
  const size = Math.max(maxX - minX, maxY - minY, maxZ - minZ, 1);
  const targetSize = 500; // Fit graph within 500 units
  const scale = targetSize / size;
  
  const normalized = new Map();
  positions.forEach((pos, id) => {
    normalized.set(id, {
      x: (pos.x - cx) * scale,
      y: (pos.y - cy) * scale,
      z: (pos.z - cz) * scale * 0.5, // Less z-depth to keep visible
    });
  });
  
  return normalized;
}

function computeForceLayout() {
  const positions = new Map();
  const totalNodes = DATA.nodes.length;
  const scaleFactor = Math.max(1, Math.sqrt(totalNodes) / 3);
  
  // Place nodes in a simple 3D grid based on hierarchy depth
  const byDepth = [[], [], [], []];
  DATA.nodes.forEach(n => {
    const d = n.depth || 0;
    if (!byDepth[d]) byDepth[d] = [];
    byDepth[d].push(n);
  });
  
  // Root at center
  byDepth[0].forEach((n, i) => {
    positions.set(n.id, {x: 0, y: 0, z: 0});
  });
  
  // Heads in a circle at y=100
  const headRadius = 180 * scaleFactor;
  byDepth[1].forEach((n, i) => {
    const angle = (i / Math.max(byDepth[1].length, 1)) * Math.PI * 2;
    positions.set(n.id, {
      x: Math.cos(angle) * headRadius,
      y: 100,
      z: Math.sin(angle) * headRadius,
    });
  });
  
  // Groups near their parents
  const groupRadius = 70 * scaleFactor;
  byDepth[2].forEach((n, i) => {
    const parent = positions.get(n.parent_id);
    if (parent) {
      const angle = (i * 1.5) + (n.id.charCodeAt(0) % 10); // deterministic
      positions.set(n.id, {
        x: parent.x + Math.cos(angle) * groupRadius,
        y: (i % 2 === 0 ? 1 : -1) * 30, // slight y variation
        z: parent.z + Math.sin(angle) * groupRadius,
      });
    } else {
      positions.set(n.id, {x: (Math.random()-0.5)*300*scaleFactor, y: 0, z: (Math.random()-0.5)*300*scaleFactor});
    }
  });
  
  // Children near their parents
  const childRadius = 45 * scaleFactor;
  byDepth[3].forEach((n, i) => {
    const parent = positions.get(n.parent_id);
    if (parent) {
      const angle = (i * 0.8) + (n.id.charCodeAt(0) % 10);
      positions.set(n.id, {
        x: parent.x + Math.cos(angle) * childRadius,
        y: -80,
        z: parent.z + Math.sin(angle) * childRadius,
      });
    } else {
      positions.set(n.id, {x: (Math.random()-0.5)*300*scaleFactor, y: -80, z: (Math.random()-0.5)*300*scaleFactor});
    }
  });
  
  return positions;
}

function computeRadialLayout() {
  const positions = new Map();
  const totalNodes = DATA.nodes.length;
  const scaleFactor = Math.max(1, Math.sqrt(totalNodes) / 3);
  
  // Root at center
  const root = DATA.nodes.find(n => n.node_type === 'root');
  if (root) {
    positions.set(root.id, {x: 0, y: 0, z: 0});
  }
  
  // Heads on inner ring with z variation
  const heads = DATA.nodes.filter(n => n.node_type === 'head');
  const headAngle = (Math.PI * 2) / Math.max(heads.length, 1);
  const headRadius = 120 * scaleFactor;
  heads.forEach((h, i) => {
    const angle = i * headAngle;
    const zOffset = Math.sin(i * 1.7) * 40; // deterministic z variation
    positions.set(h.id, {
      x: Math.cos(angle) * headRadius,
      y: Math.sin(angle) * headRadius,
      z: zOffset,
    });
  });
  
  // Groups on middle ring
  const groups = DATA.nodes.filter(n => n.node_type === 'group');
  const groupRadius = 80 * scaleFactor;
  groups.forEach(g => {
    const parent = positions.get(g.parent_id);
    const parentNode = nodesById.get(g.parent_id);
    if (parent && parentNode) {
      const siblingGroups = parentNode.children || [];
      const idx = siblingGroups.indexOf(g.id);
      const total = siblingGroups.length;
      
      const baseAngle = Math.atan2(parent.y, parent.x);
      const sectorSize = Math.PI / 2.5;
      const angle = baseAngle - sectorSize/2 + (idx / Math.max(total-1, 1)) * sectorSize;
      const zOffset = Math.cos(idx * 2.3) * 50; // deterministic z variation
      
      positions.set(g.id, {
        x: parent.x + Math.cos(angle) * groupRadius,
        y: parent.y + Math.sin(angle) * groupRadius,
        z: parent.z + zOffset,
      });
    }
  });
  
  // Children on outer ring
  const childRadius = 55 * scaleFactor;
  DATA.nodes.filter(n => n.node_type === 'child').forEach(c => {
    const parent = positions.get(c.parent_id);
    const parentNode = nodesById.get(c.parent_id);
    if (parent && parentNode) {
      const siblings = parentNode.children || [];
      const idx = siblings.indexOf(c.id);
      const total = siblings.length;
      
      const baseAngle = Math.atan2(parent.y, parent.x);
      const spread = Math.PI / 2;
      const angle = baseAngle - spread/2 + (idx / Math.max(total-1, 1)) * spread;
      const zOffset = Math.sin(idx * 1.9) * 35;
      
      positions.set(c.id, {
        x: parent.x + Math.cos(angle) * childRadius,
        y: parent.y + Math.sin(angle) * childRadius,
        z: parent.z + zOffset,
      });
    }
  });
  
  return positions;
}

function computeTreeLayout() {
  const positions = new Map();
  const totalNodes = DATA.nodes.length;
  const scaleFactor = Math.max(1, Math.sqrt(totalNodes) / 4);
  
  // Level 0: Root at top
  const root = DATA.nodes.find(n => n.node_type === 'root');
  if (root) positions.set(root.id, {x: 0, y: 180 * scaleFactor, z: 0});
  
  // Level 1: Heads
  const heads = DATA.nodes.filter(n => n.node_type === 'head');
  const headSpacing = Math.min(160 * scaleFactor, 300);
  heads.forEach((h, i) => {
    positions.set(h.id, {
      x: (i - (heads.length - 1) / 2) * headSpacing,
      y: 80 * scaleFactor,
      z: Math.sin(i * 1.3) * 30, // slight z variation
    });
  });
  
  // Level 2: Groups
  const groups = DATA.nodes.filter(n => n.node_type === 'group');
  groups.forEach(g => {
    const parent = positions.get(g.parent_id);
    const parentNode = nodesById.get(g.parent_id);
    if (parent && parentNode) {
      const siblings = parentNode.children || [];
      const idx = siblings.indexOf(g.id);
      const total = siblings.length;
      const spacing = Math.min(70 * scaleFactor, 140);
      
      positions.set(g.id, {
        x: parent.x + (idx - (total - 1) / 2) * spacing,
        y: -20 * scaleFactor,
        z: Math.cos(idx * 1.7) * 25,
      });
    }
  });
  
  // Level 3: Children
  DATA.nodes.filter(n => n.node_type === 'child').forEach(c => {
    const parent = positions.get(c.parent_id);
    const parentNode = nodesById.get(c.parent_id);
    if (parent && parentNode) {
      const siblings = parentNode.children || [];
      const idx = siblings.indexOf(c.id);
      const total = siblings.length;
      const spacing = Math.min(45 * scaleFactor, 90);
      
      positions.set(c.id, {
        x: parent.x + (idx - (total - 1) / 2) * spacing,
        y: -120 * scaleFactor,
        z: Math.sin(idx * 2.1) * 20,
      });
    }
  });
  
  return positions;
}

function computeOrbitLayout() {
  const positions = new Map();
  const totalNodes = DATA.nodes.length;
  const scaleFactor = Math.max(1, Math.sqrt(totalNodes) / 4);
  const time = Date.now() * 0.0001;
  
  // Root at center
  const root = DATA.nodes.find(n => n.node_type === 'root');
  if (root) positions.set(root.id, {x: 0, y: 0, z: 0});
  
  // Heads orbit at different radii and speeds
  const heads = DATA.nodes.filter(n => n.node_type === 'head');
  const baseHeadRadius = 100 * scaleFactor;
  heads.forEach((h, i) => {
    const angle = time * (0.5 + i * 0.1) + i * Math.PI * 2 / Math.max(heads.length, 1);
    const r = baseHeadRadius + i * 20;
    positions.set(h.id, {
      x: Math.cos(angle) * r,
      y: Math.sin(angle) * r,
      z: Math.sin(angle * 0.5) * 40,
    });
  });
  
  // Groups orbit around their parent head
  const groups = DATA.nodes.filter(n => n.node_type === 'group');
  const groupRadius = 50 * scaleFactor;
  groups.forEach(g => {
    const parent = positions.get(g.parent_id);
    if (parent) {
      const angle = time * 0.8 + orbitAngles.get(g.id);
      positions.set(g.id, {
        x: parent.x + Math.cos(angle) * groupRadius,
        y: parent.y + Math.sin(angle) * groupRadius,
        z: parent.z + Math.sin(angle * 0.7) * 25,
      });
    }
  });
  
  // Children orbit around their parent
  const childRadius = 30 * scaleFactor;
  DATA.nodes.filter(n => n.node_type === 'child').forEach(c => {
    const parent = positions.get(c.parent_id);
    if (parent) {
      const angle = time * 1.2 + orbitAngles.get(c.id);
      positions.set(c.id, {
        x: parent.x + Math.cos(angle) * childRadius,
        y: parent.y + Math.sin(angle) * childRadius,
        z: parent.z + Math.cos(angle * 0.9) * 15,
      });
    }
  });
  
  return positions;
}

// ═══════════════════════════════════════════════════════════════════════════════
// THREE.JS SETUP
// ═══════════════════════════════════════════════════════════════════════════════

function initScene() {
  const container = document.getElementById('canvas-container');
  
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x050508);
  
  camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 10000);
  camera.position.set(0, 0, 500);
  
  renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);
  
  // Controls
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.5;
  
  // Lights
  const ambient = new THREE.AmbientLight(0xffffff, 0.6);
  scene.add(ambient);
  
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(200, 300, 400);
  scene.add(dirLight);
  
  const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
  dirLight2.position.set(-200, -100, -300);
  scene.add(dirLight2);
  
  // Event listeners
  window.addEventListener('resize', onWindowResize);
  renderer.domElement.addEventListener('click', onCanvasClick);
  renderer.domElement.addEventListener('mousemove', onCanvasMouseMove);
  
  animate();
}

function onWindowResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

// ═══════════════════════════════════════════════════════════════════════════════
// NODE RENDERING
// ═══════════════════════════════════════════════════════════════════════════════

function getNodeColor(node) {
  if (node.node_type === 'head') return 0xffffff;
  if (node.node_type === 'group') return 0x3b82f6;
  if (node.impact === 'positive') return 0x00e676;
  if (node.impact === 'negative') return 0xff5252;
  if (node.impact === 'mixed') return 0xffab40;
  return 0x78909c;
}

function getNodeSize(node) {
  if (node.node_type === 'head') return 20;
  if (node.node_type === 'group') return 14;
  if (node.node_type === 'root') return 6;
  return Math.max(8, Math.min(14, (node.weight || 0.5) * 20));
}

function createNodeMesh(node) {
  const size = getNodeSize(node);
  const color = getNodeColor(node);
  
  const geometry = new THREE.SphereGeometry(size, 32, 16);
  const material = new THREE.MeshPhysicalMaterial({
    color: color,
    metalness: 0.2,
    roughness: 0.6,
    emissive: color,
    emissiveIntensity: 0.1,
  });
  
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData = {nodeId: node.id, nodeType: node.node_type};
  
  // Add border for non-head nodes
  if (node.node_type !== 'head' && node.node_type !== 'root') {
    const borderGeometry = new THREE.SphereGeometry(size * 1.2, 16, 8);
    const borderMaterial = new THREE.MeshBasicMaterial({
      color: color,
      transparent: true,
      opacity: 0.2,
      wireframe: true,
    });
    const border = new THREE.Mesh(borderGeometry, borderMaterial);
    mesh.add(border);
  }
  
  return mesh;
}

function createEdgeLine(edge, positions) {
  const src = positions.get(edge.source);
  const tgt = positions.get(edge.target);
  if (!src || !tgt) return null;
  
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(src.x, src.y, src.z),
    new THREE.Vector3(tgt.x, tgt.y, tgt.z),
  ]);
  
  const color = getEdgeColor(edge.type);
  const material = new THREE.LineBasicMaterial({
    color: color,
    transparent: true,
    opacity: getEdgeOpacity(edge.type),
  });
  
  return new THREE.Line(geometry, material);
}

function getEdgeColor(type) {
  const colors = {
    CONFIRMS: 0x00e676,
    AMPLIFIES: 0x00e676,
    CONTRADICTS: 0xff5252,
    DAMPENS: 0xffab40,
    CAUSES: 0x3b82f6,
    TRIGGERS: 0x8b5cf6,
    CONTEXTUALIZES: 0x78909c,
    CORRELATES: 0x4a4a5a,
    belongs_to: 0x333333,
    informs: 0x444444,
  };
  return colors[type] || 0x4a4a5a;
}

function getEdgeOpacity(type) {
  if (type === 'belongs_to') return 0.15;
  if (type === 'CONFIRMS' || type === 'AMPLIFIES') return 0.7;
  if (type === 'CONTRADICTS') return 0.7;
  return 0.4;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCENE UPDATES
// ═══════════════════════════════════════════════════════════════════════════════

function updateScene() {
  console.log('updateScene called, layout:', currentLayout, 'nodes:', DATA.nodes.length);
  
  // Clear existing
  nodeMeshes.forEach(mesh => scene.remove(mesh));
  edgeLines.forEach(line => scene.remove(line));
  labelSprites.forEach(sprite => scene.remove(sprite));
  nodeMeshes.clear();
  edgeLines.clear();
  labelSprites.clear();
  
  // Compute positions
  const computeLayout = LayoutEngines[currentLayout] || LayoutEngines.force;
  let positions = computeLayout();
  positions = normalizePositions(positions);
  console.log('Positions computed:', positions.size);
  
  const focusSet = getFocusSet();
  console.log('Focus set size:', focusSet.size);
  
  // Create node meshes
  DATA.nodes.forEach(node => {
    const pos = positions.get(node.id);
    if (!pos) return;
    
    const mesh = createNodeMesh(node);
    mesh.position.set(pos.x, pos.y, pos.z);
    
    // Focus mode: dim background nodes
    const isFocused = focusSet.has(node.id);
    if (focusNodeId && focusNodeId !== 'all') {
      if (!isFocused) {
        mesh.material.opacity = 0.08;
        mesh.material.transparent = true;
        mesh.position.z -= 300; // Push back slightly
      } else {
        mesh.material.emissiveIntensity = 0.3;
      }
    }
    
    scene.add(mesh);
    nodeMeshes.set(node.id, mesh);
  });
  
  // Create edge lines
  if (showEdges) {
    DATA.edges.forEach(edge => {
      const srcInFocus = focusSet.has(edge.source);
      const tgtInFocus = focusSet.has(edge.target);
      
      // Only show edges within focus set
      if (focusNodeId && focusNodeId !== 'all' && (!srcInFocus || !tgtInFocus)) {
        return;
      }
      
      const line = createEdgeLine(edge, positions);
      if (line) {
        scene.add(line);
        edgeLines.set(`${edge.source}-${edge.target}`, line);
      }
    });
  }
  
  // Create labels if enabled
  if (showLabels) {
    DATA.nodes.forEach(node => {
      if (!focusSet.has(node.id)) return;
      const pos = positions.get(node.id);
      if (!pos) return;
      
      const sprite = createLabelSprite(node.label, node.node_type === 'head' ? 16 : 12);
      sprite.position.set(pos.x, pos.y + getNodeSize(node) + 10, pos.z);
      scene.add(sprite);
      labelSprites.set(node.id, sprite);
    });
  }
}

function createLabelSprite(text, size) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 256;
  canvas.height = 64;
  
  ctx.fillStyle = 'rgba(5, 5, 8, 0.85)';
  ctx.beginPath();
  ctx.roundRect(4, 8, 248, 48, 8);
  ctx.fill();
  
  ctx.strokeStyle = 'rgba(99, 102, 241, 0.3)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.roundRect(4, 8, 248, 48, 8);
  ctx.stroke();
  
  ctx.font = `bold ${size}px -apple-system, system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#e8e8f0';
  ctx.fillText(text.length > 20 ? text.slice(0, 18) + '...' : text, 128, 32);
  
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({map: texture, transparent: true});
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(40, 10, 1);
  
  return sprite;
}

// ═══════════════════════════════════════════════════════════════════════════════
// INTERACTION
// ═══════════════════════════════════════════════════════════════════════════════

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

function onCanvasClick(event) {
  mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
  
  raycaster.setFromCamera(mouse, camera);
  const intersects = raycaster.intersectObjects(Array.from(nodeMeshes.values()));
  
  if (intersects.length > 0) {
    const nodeId = intersects[0].object.userData.nodeId;
    selectNode(nodeId);
  } else {
    // Click background: reset focus
    focusNodeId = 'all';
    updateFocusButtons();
    updateScene();
    showNodeInfo(null);
  }
}

function onCanvasMouseMove(event) {
  mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
  mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
  
  raycaster.setFromCamera(mouse, camera);
  const intersects = raycaster.intersectObjects(Array.from(nodeMeshes.values()));
  
  const tooltip = document.getElementById('tooltip');
  
  if (intersects.length > 0) {
    const nodeId = intersects[0].object.userData.nodeId;
    const node = nodesById.get(nodeId);
    if (node) {
      showTooltip(node, event.clientX, event.clientY);
      document.body.style.cursor = 'pointer';
    }
  } else {
    tooltip.style.display = 'none';
    document.body.style.cursor = 'default';
  }
}

function selectNode(nodeId) {
  const node = nodesById.get(nodeId);
  if (!node) return;
  
  if (node.node_type === 'head') {
    focusNodeId = nodeId;
    updateFocusButtons();
    updateScene();
  }
  
  showNodeInfo(node);
  
  // Camera focus
  const mesh = nodeMeshes.get(nodeId);
  if (mesh) {
    const target = mesh.position.clone();
    const dist = Math.max(120, getNodeSize(node) * 4);
    const offset = new THREE.Vector3(0.6, 0.4, 1).normalize().multiplyScalar(dist);
    const newPos = target.clone().add(offset);
    
    // Smooth camera transition
    animateCamera(newPos, target);
  }
}

function animateCamera(targetPos, lookAt) {
  const startPos = camera.position.clone();
  const startTarget = controls.target.clone();
  const duration = 800;
  const start = Date.now();
  
  function step() {
    const elapsed = Date.now() - start;
    const t = Math.min(elapsed / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3); // ease-out cubic
    
    camera.position.lerpVectors(startPos, targetPos, ease);
    controls.target.lerpVectors(startTarget, lookAt, ease);
    controls.update();
    
    if (t < 1) requestAnimationFrame(step);
  }
  
  step();
}

function fitCameraToGraph(positions) {
  if (!positions || positions.size === 0) return;
  
  let maxDist = 0;
  positions.forEach(pos => {
    const d = Math.sqrt(pos.x * pos.x + pos.y * pos.y + pos.z * pos.z);
    maxDist = Math.max(maxDist, d);
  });
  
  // Position camera to see entire graph
  const dist = Math.max(maxDist * 2.2, 300);
  const targetPos = new THREE.Vector3(dist * 0.6, dist * 0.4, dist);
  const lookAt = new THREE.Vector3(0, 0, 0);
  
  camera.position.copy(targetPos);
  controls.target.copy(lookAt);
  controls.update();
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI UPDATES
// ═══════════════════════════════════════════════════════════════════════════════

function showNodeInfo(node) {
  const info = document.getElementById('node-info');
  
  if (!node) {
    info.innerHTML = '<div class="ni-placeholder">Click any node to inspect</div>';
    return;
  }
  
  const impactClass = node.impact === 'positive' ? 'sb-pos' :
                      node.impact === 'negative' ? 'sb-neg' :
                      node.impact === 'mixed' ? 'sb-mix' : 'sb-neu';
  
  let html = `
    <div class="ni-label" style="color:${node.color || '#fff'}">${node.label}</div>
    <div class="ni-cat">${node.node_type}${node.category ? ' · ' + node.category : ''}</div>
  `;
  
  if (node.value) {
    html += `<div class="ni-val">${node.value}</div>`;
  }
  
  if (node.summary) {
    html += `<div class="ni-summary">${node.summary}</div>`;
  }
  
  if (node.context) {
    html += `<div class="ni-ctx">${node.context}</div>`;
  }
  
  html += `
    <div class="ni-meta">
      <span class="sig-badge ${impactClass}">${node.impact || 'neutral'}</span>
      <span>wt ${(node.weight || 0).toFixed(2)}</span>
      ${node.effective_weight != null ? `<span>ew ${(node.effective_weight * 100).toFixed(0)}%</span>` : ''}
    </div>
  `;
  
  info.innerHTML = html;
}

function showTooltip(node, x, y) {
  const tooltip = document.getElementById('tooltip');
  const label = document.getElementById('tt-label');
  const cat = document.getElementById('tt-cat');
  const content = document.getElementById('tt-content');
  
  label.textContent = node.label || 'Unnamed';
  cat.textContent = `${node.node_type || 'node'}${node.category ? ' · ' + node.category : ''}`;
  
  let text = '';
  if (node.value != null) text += `Value: ${node.value}`;
  if (node.impact) text += (text ? ' | ' : '') + `Impact: ${node.impact}`;
  if (node.weight != null) text += (text ? ' | ' : '') + `Weight: ${node.weight.toFixed(2)}`;
  if (!text) text = 'Click to inspect details';
  
  content.innerHTML = text;
  
  tooltip.style.display = 'block';
  
  // Viewport-aware positioning
  const sidebarWidth = 260;
  const padding = 12;
  const ttWidth = Math.min(300, tooltip.offsetWidth || 200);
  const ttHeight = tooltip.offsetHeight || 80;
  
  let left = x + 18;
  let top = y - 15;
  
  // Prevent going under sidebar
  if (left + ttWidth > window.innerWidth - sidebarWidth - padding) {
    left = x - ttWidth - 18;
  }
  // Prevent going off top/bottom
  if (top < padding) top = y + 20;
  if (top + ttHeight > window.innerHeight - padding) {
    top = window.innerHeight - ttHeight - padding;
  }
  // Prevent going off left
  if (left < padding) left = padding;
  
  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
}

function updateFocusButtons() {
  document.querySelectorAll('.focus-btn').forEach(btn => {
    const fid = btn.dataset.focus;
    btn.classList.toggle('active', fid === focusNodeId);
  });
}

function updateStats() {
  const focusSet = getFocusSet();
  const visibleNodes = DATA.nodes.filter(n => focusSet.has(n.id));
  
  document.getElementById('sn').textContent = visibleNodes.length;
  document.getElementById('se').textContent = DATA.edges.filter(e => 
    focusSet.has(e.source) && focusSet.has(e.target)
  ).length;
  document.getElementById('sg').textContent = visibleNodes.filter(n => n.node_type === 'group').length;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONTROLS
// ═══════════════════════════════════════════════════════════════════════════════

function toggleLabels() {
  showLabels = !showLabels;
  document.getElementById('btn-labels').classList.toggle('active', showLabels);
  updateScene();
}

function toggleEdges() {
  showEdges = !showEdges;
  document.getElementById('btn-edges').classList.toggle('active', showEdges);
  updateScene();
}

function toggleRotate() {
  autoRotate = !autoRotate;
  controls.autoRotate = autoRotate;
  document.getElementById('btn-rotate').classList.toggle('active', autoRotate);
}

function resetView() {
  focusNodeId = 'all';
  updateFocusButtons();
  updateScene();
  showNodeInfo(null);
  // Re-fit camera to show full graph
  const computeLayout = LayoutEngines[currentLayout] || LayoutEngines.force;
  let positions = computeLayout();
  positions = normalizePositions(positions);
  fitCameraToGraph(positions);
}

// Layout buttons
document.querySelectorAll('.layout-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.layout-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentLayout = btn.dataset.layout;
    updateScene();
  });
});

// Focus buttons
document.querySelectorAll('.focus-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    focusNodeId = btn.dataset.focus;
    updateFocusButtons();
    updateScene();
  });
});

// Search
document.getElementById('search').addEventListener('input', (e) => {
  const q = e.target.value.toLowerCase().trim();
  if (!q) {
    focusNodeId = 'all';
    updateFocusButtons();
    updateScene();
    return;
  }
  
  const matched = DATA.nodes.filter(n => 
    n.label.toLowerCase().includes(q) ||
    (n.value || '').toLowerCase().includes(q) ||
    (n.context || '').toLowerCase().includes(q)
  );
  
  if (matched.length === 1) {
    selectNode(matched[0].id);
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
// ANIMATION LOOP
// ═══════════════════════════════════════════════════════════════════════════════

function animate() {
  animationId = requestAnimationFrame(animate);
  
  // Update orbit layout continuously without rebuilding scene
  if (currentLayout === 'orbit') {
    updateOrbitPositions();
  }
  
  controls.update();
  renderer.render(scene, camera);
  
  // Update debug panel
  if(camera){
    document.getElementById('dbg-cam').textContent = 
      `x=${camera.position.x.toFixed(0)} y=${camera.position.y.toFixed(0)} z=${camera.position.z.toFixed(0)}`;
  }
  document.getElementById('dbg-meshes').textContent = nodeMeshes.size;
  document.getElementById('dbg-edges').textContent = edgeLines.size;
  document.getElementById('dbg-layout').textContent = currentLayout;
}

function updateOrbitPositions() {
  const time = Date.now() * 0.0001;
  const positions = new Map();
  const totalNodes = DATA.nodes.length;
  const scaleFactor = Math.max(1, Math.sqrt(totalNodes) / 4);
  
  // Update head positions
  const heads = DATA.nodes.filter(n => n.node_type === 'head');
  const baseHeadRadius = 100 * scaleFactor;
  heads.forEach((h, i) => {
    const angle = time * (0.5 + i * 0.1) + i * Math.PI * 2 / Math.max(heads.length, 1);
    const r = baseHeadRadius + i * 20;
    positions.set(h.id, {
      x: Math.cos(angle) * r,
      y: Math.sin(angle) * r,
      z: Math.sin(angle * 0.5) * 40,
    });
  });
  
  // Update group positions
  const groups = DATA.nodes.filter(n => n.node_type === 'group');
  const groupRadius = 50 * scaleFactor;
  groups.forEach(g => {
    const parent = positions.get(g.parent_id);
    if (parent) {
      const angle = time * 0.8 + orbitAngles.get(g.id);
      positions.set(g.id, {
        x: parent.x + Math.cos(angle) * groupRadius,
        y: parent.y + Math.sin(angle) * groupRadius,
        z: parent.z + Math.sin(angle * 0.7) * 25,
      });
    }
  });
  
  // Update child positions
  const childRadius = 30 * scaleFactor;
  DATA.nodes.filter(n => n.node_type === 'child').forEach(c => {
    const parent = positions.get(c.parent_id);
    if (parent) {
      const angle = time * 1.2 + orbitAngles.get(c.id);
      positions.set(c.id, {
        x: parent.x + Math.cos(angle) * childRadius,
        y: parent.y + Math.sin(angle) * childRadius,
        z: parent.z + Math.cos(angle * 0.9) * 15,
      });
    }
  });
  
  // Apply positions to meshes
  positions.forEach((pos, nodeId) => {
    const mesh = nodeMeshes.get(nodeId);
    if (mesh) {
      mesh.position.set(pos.x, pos.y, pos.z);
    }
  });
  
  // Update edge lines
  DATA.edges.forEach(edge => {
    const line = edgeLines.get(`${edge.source}-${edge.target}`);
    if (line) {
      const src = positions.get(edge.source);
      const tgt = positions.get(edge.target);
      if (src && tgt) {
        const positions_attr = line.geometry.attributes.position;
        positions_attr.setXYZ(0, src.x, src.y, src.z);
        positions_attr.setXYZ(1, tgt.x, tgt.y, tgt.z);
        positions_attr.needsUpdate = true;
      }
    }
  });
  
  // Update labels
  labelSprites.forEach((sprite, nodeId) => {
    const pos = positions.get(nodeId);
    if (pos) {
      sprite.position.set(pos.x, pos.y + 15, pos.z);
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// LEGEND
// ═══════════════════════════════════════════════════════════════════════════════

function buildLegend() {
  const legend = document.getElementById('legend');
  const categories = [
    {name: 'Technical', color: '#3b82f6', type: 'HEAD::technical'},
    {name: 'Fundamental', color: '#10b981', type: 'HEAD::fundamental'},
    {name: 'Financial', color: '#f59e0b', type: 'HEAD::financial'},
    {name: 'News', color: '#ec4899', type: 'HEAD::news'},
    {name: 'Announcements', color: '#8b5cf6', type: 'HEAD::announcement'},
  ];
  
  categories.forEach(cat => {
    const count = DATA.nodes.filter(n => n.category === cat.type.replace('HEAD::', '')).length;
    if (count === 0) return;
    
    const div = document.createElement('div');
    div.className = 'leg-item';
    div.innerHTML = `
      <div class="leg-dot" style="background:${cat.color};--dot-color:${cat.color}"></div>
      <span>${cat.name}</span>
      <span class="leg-cnt">${count}</span>
    `;
    div.onclick = () => {
      focusNodeId = cat.type;
      updateFocusButtons();
      updateScene();
    };
    legend.appendChild(div);
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════════════

// Initialize immediately (OrbitControls loaded via script tag in <head>)
try {
  prepareData();
  initScene();
  updateScene();
  // Fit camera to show entire graph on load
  const computeLayout = LayoutEngines[currentLayout] || LayoutEngines.force;
  let positions = computeLayout();
  positions = normalizePositions(positions);
  fitCameraToGraph(positions);
  buildLegend();
  updateStats();
} catch(e) {
  console.error('Init error:', e);
  document.getElementById('dbg-error').textContent = 'ERROR: ' + e.message;
}

// Catch all errors
window.addEventListener('error', (e) => {
  console.error('Global error:', e.error);
  document.getElementById('dbg-error').textContent = 'JS ERROR: ' + e.error.message;
});
</script>
</body>
</html>'''
