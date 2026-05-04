"""
tree_builder.py — Hierarchical tree builder for knowledge graph visualization.

Builds a strict tree from flat analysis nodes:
  ROOT → HEADS → GROUPS → CHILDREN → VERDICTS

Financial statements have 3 levels:
  HEAD::financial → GROUP::Balance Sheet (summary) → CHILD::Total_Assets (value+context+impact)

All other categories have 2 levels:
  HEAD::technical → CHILD::RSI_14 (value+context+impact)

Used by layout engines to compute positions and by focus system to extract subtrees.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from schemas.node import Node

logger = logging.getLogger(__name__)

NodeType = Literal["root", "head", "group", "child", "verdict"]


# ── Financial statement group mapping ──────────────────────────────────────────

_FINANCIAL_GROUPS: dict[str, str] = {
    # Balance Sheet
    "Debt_To_Equity": "Balance Sheet",
    "Total_Assets": "Balance Sheet",
    "Total_Liabilities": "Balance Sheet",
    "Shareholders_Equity": "Balance Sheet",
    "Reserves": "Balance Sheet",
    "Borrowings": "Balance Sheet",
    # P&L
    "Revenue_TTM": "P&L",
    "PAT_TTM": "P&L",
    "EBITDA_TTM": "P&L",
    "EBITDA_Margin": "P&L",
    "Revenue_Growth_YoY": "P&L",
    "PAT_Growth_YoY": "P&L",
    "Interest_Coverage": "P&L",
    "Market_Cap": "P&L",
    # Cash Flow
    "Operating_Cash_Flow": "Cash Flow",
    "Free_Cashflow": "Cash Flow",
    "Cash_From_Investing": "Cash Flow",
    "Cash_From_Financing": "Cash Flow",
    # Shareholding
    "Promoter_Holding": "Shareholding",
    "Public_Retail_Holding": "Shareholding",
    "FII_Holding": "Shareholding",
    "DII_Holding": "Shareholding",
    # Quarterly Result
    "Revenue_Quarterly": "Quarterly Result",
    "Net_Profit_Quarterly": "Quarterly Result",
    "Expenses_Quarterly": "Quarterly Result",
    "Operating_Profit_Quarterly": "Quarterly Result",
    "OPM_Quarterly": "Quarterly Result",
    # Annual Result
    "Revenue_Annual": "Annual Result",
    "Net_Profit_Annual": "Annual Result",
    "Expenses_Annual": "Annual Result",
    "Operating_Profit_Annual": "Annual Result",
    "OPM_Annual": "Annual Result",
    "EPS_Annual": "Annual Result",
}

_GROUP_ORDER: list[str] = [
    "Balance Sheet", "P&L", "Cash Flow",
    "Shareholding", "Quarterly Result", "Annual Result",
]

# Nodes that should NOT appear as children (context nodes)
_EXCLUDED_CONTEXT_NODES: frozenset[str] = frozenset({
    "Market_Regime", "Sector_Trend", "Data_Completeness", "Peer_Snapshot",
})


@dataclass
class TreeNode:
    """A node in the hierarchical knowledge graph tree."""
    id: str
    label: str
    node_type: NodeType
    parent_id: str | None
    children: list[str] = field(default_factory=list)
    depth: int = 0
    # Data fields per category
    value: str = ""
    context: str = ""
    impact: str = "neutral"  # positive / negative / neutral / mixed
    summary: str = ""        # For financial statement groups only
    # Visual properties (inherited from original node or computed)
    category: str = ""
    signal: str = "neutral"
    weight: float = 1.0
    effective_weight: float | None = None
    confidence: float = 1.0
    source: str = ""
    color: str = "#888888"
    # Original node reference (for advanced use)
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)


class NodeTree:
    """
    Hierarchical tree for knowledge graph visualization.

    Usage:
        tree = NodeTree(nodes, edges)
        subtree_ids = tree.get_subtree("HEAD::financial")
        positions = tree.compute_focus_positions("HEAD::financial", layout="radial")
    """

    def __init__(self, nodes: list[Node], edges: list[Any] | None = None) -> None:
        self._nodes: dict[str, TreeNode] = {}
        self._root_id = "ROOT"
        self._edges: list[dict[str, Any]] = []
        self._adjacency: dict[str, list[str]] = {}  # node_id -> list of neighbor ids

        self._build_tree(nodes)
        if edges:
            self._index_edges(edges)

    # ── Tree construction ──────────────────────────────────────────────────────

    def _build_tree(self, nodes: list[Node]) -> None:
        """Build hierarchical tree from flat node list."""
        logger.info("NodeTree._build_tree: received %d nodes", len(nodes))
        
        # Log categories of input nodes
        cat_counts = {}
        for node in nodes:
            cat = self._get_category(node)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        logger.info("NodeTree input categories: %s", cat_counts)
        
        # 1. Create root
        self._nodes[self._root_id] = TreeNode(
            id=self._root_id,
            label="Stock Analysis",
            node_type="root",
            parent_id=None,
            depth=0,
            color="#FFFFFF",
        )

        # 2. Create heads
        head_defs = [
            ("HEAD::technical", "Technical Indicators", "technical", "#3b82f6"),
            ("HEAD::fundamental", "Fundamentals", "fundamental", "#10b981"),
            ("HEAD::financial", "Financial Statements", "financial", "#f59e0b"),
            ("HEAD::news", "News", "news", "#ec4899"),
            ("HEAD::announcement", "Announcements", "announcement", "#8b5cf6"),
        ]
        for hid, hlabel, hcat, hcolor in head_defs:
            self._nodes[hid] = TreeNode(
                id=hid,
                label=hlabel,
                node_type="head",
                parent_id=self._root_id,
                depth=1,
                category=hcat,
                color=hcolor,
            )
            self._nodes[self._root_id].children.append(hid)

        # 3. Index original nodes by name for grouping
        by_name: dict[str, list[Node]] = {}
        for node in nodes:
            by_name.setdefault(node.name, []).append(node)

        # 4. Build groups and children per category
        for node in nodes:
            cat = self._get_category(node)
            name = node.name

            # Skip excluded context nodes
            if cat == "context" and name in _EXCLUDED_CONTEXT_NODES:
                continue

            head_id = f"HEAD::{cat}"
            if head_id not in self._nodes:
                continue  # Skip unknown categories

            # Financial statements: create group nodes
            if cat == "financial" and name in _FINANCIAL_GROUPS:
                group_name = _FINANCIAL_GROUPS[name]
                group_id = f"GROUP::financial::{group_name}"

                # Create group if not exists
                if group_id not in self._nodes:
                    self._nodes[group_id] = TreeNode(
                        id=group_id,
                        label=group_name,
                        node_type="group",
                        parent_id=head_id,
                        depth=2,
                        category=cat,
                        color="#60a5fa",
                        summary="",  # Will be populated later if available
                    )
                    self._nodes[head_id].children.append(group_id)

                # Create child under group
                child = self._node_to_tree_node(node, parent_id=group_id, depth=3)
                self._nodes[child.id] = child
                self._nodes[group_id].children.append(child.id)

            elif cat == "fundamental" and name in _FINANCIAL_GROUPS:
                # Fundamental nodes that map to financial groups go under financial head
                group_name = _FINANCIAL_GROUPS[name]
                group_id = f"GROUP::financial::{group_name}"

                if group_id not in self._nodes:
                    self._nodes[group_id] = TreeNode(
                        id=group_id,
                        label=group_name,
                        node_type="group",
                        parent_id="HEAD::financial",
                        depth=2,
                        category="financial",
                        color="#60a5fa",
                        summary="",
                    )
                    self._nodes["HEAD::financial"].children.append(group_id)

                child = self._node_to_tree_node(node, parent_id=group_id, depth=3)
                self._nodes[child.id] = child
                self._nodes[group_id].children.append(child.id)

            else:
                # Direct child under head (no group)
                child = self._node_to_tree_node(node, parent_id=head_id, depth=2)
                self._nodes[child.id] = child
                self._nodes[head_id].children.append(child.id)

        # 5. Sort financial groups by predefined order
        financial_head = self._nodes.get("HEAD::financial")
        if financial_head:
            financial_head.children.sort(
                key=lambda gid: _GROUP_ORDER.index(self._nodes[gid].label)
                if self._nodes[gid].label in _GROUP_ORDER else 99
            )
        
        # Log final tree structure
        final_cats = {}
        for node in self._nodes.values():
            cat = node.node_type
            final_cats[cat] = final_cats.get(cat, 0) + 1
        logger.info("NodeTree built: %d total nodes (%s)", len(self._nodes), final_cats)

    def _node_to_tree_node(
        self, node: Node, parent_id: str, depth: int
    ) -> TreeNode:
        """Convert a Node schema object to a TreeNode."""
        cat = self._get_category(node)
        sig = self._get_signal(node)

        # Determine impact from signal
        impact = self._signal_to_impact(sig)

        # Extract value and context from node
        value = str(node.value) if hasattr(node, "value") else ""
        context = str(node.context) if hasattr(node, "context") else ""

        # If node has llm_summary, use it as context
        if hasattr(node, "llm_summary") and node.llm_summary:
            context = str(node.llm_summary)

        return TreeNode(
            id=node.node_id,
            label=self._short_label(node.node_id),
            node_type="child",
            parent_id=parent_id,
            depth=depth,
            value=value,
            context=context,
            impact=impact,
            category=cat,
            signal=sig,
            weight=float(node.weight) if hasattr(node, "weight") else 1.0,
            effective_weight=float(node.effective_weight)
            if hasattr(node, "effective_weight") and node.effective_weight is not None
            else None,
            confidence=float(node.confidence) if hasattr(node, "confidence") else 1.0,
            source=node.source if hasattr(node, "source") else "",
            color=self._category_color(cat),
            _raw=node.model_dump() if hasattr(node, "model_dump") else {},
        )

    def _index_edges(self, edges: list[Any]) -> None:
        """Build adjacency index from edge list."""
        for edge in edges:
            src = edge.from_id if hasattr(edge, "from_id") else edge.get("from_id", "")
            tgt = edge.to_id if hasattr(edge, "to_id") else edge.get("to_id", "")
            rel = edge.relation if hasattr(edge, "relation") else edge.get("relation", "")
            weight = float(edge.weight) if hasattr(edge, "weight") else 1.0

            if src and tgt:
                self._edges.append({
                    "source": src,
                    "target": tgt,
                    "type": rel,
                    "weight": weight,
                })
                self._adjacency.setdefault(src, []).append(tgt)
                self._adjacency.setdefault(tgt, []).append(src)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_subtree(self, node_id: str) -> list[str]:
        """Return node_id + all descendant node_ids."""
        result = [node_id]
        node = self._nodes.get(node_id)
        if not node:
            return result
        for child_id in node.children:
            result.extend(self.get_subtree(child_id))
        return result

    def get_focus_nodes(self, focus_id: str) -> tuple[set[str], set[str]]:
        """
        Return (highlighted_ids, background_ids) for focus mode.

        Highlighted = focus node + all descendants + direct neighbors via edges.
        Background = everything else.
        """
        highlighted = set(self.get_subtree(focus_id))

        # Also include direct neighbors connected by edges
        for nid in list(highlighted):
            for neighbor in self._adjacency.get(nid, []):
                highlighted.add(neighbor)

        # Always include verdicts but dimmed
        all_ids = set(self._nodes.keys())
        background = all_ids - highlighted

        return highlighted, background

    def to_json(self) -> dict[str, Any]:
        """Export tree as JSON for frontend rendering."""
        nodes_json = []
        for node in self._nodes.values():
            nodes_json.append({
                "id": node.id,
                "label": node.label,
                "node_type": node.node_type,
                "parent_id": node.parent_id,
                "children": node.children,
                "depth": node.depth,
                "value": node.value,
                "context": node.context,
                "impact": node.impact,
                "summary": node.summary,
                "category": node.category,
                "signal": node.signal,
                "weight": node.weight,
                "effective_weight": node.effective_weight,
                "confidence": node.confidence,
                "color": node.color,
            })

        return {
            "root_id": self._root_id,
            "nodes": nodes_json,
            "edges": self._edges,
            "meta": {
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
            },
        }

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_category(node: Node) -> str:
        """Extract category string from node."""
        cat = getattr(node, "category", None)
        if cat is None:
            return ""
        return str(cat.value if hasattr(cat, "value") else cat)

    @staticmethod
    def _get_signal(node: Node) -> str:
        """Extract signal string from node."""
        sig = getattr(node, "signal", None)
        if sig is None:
            return "neutral"
        return str(sig.value if hasattr(sig, "value") else sig)

    @staticmethod
    def _signal_to_impact(signal: str) -> str:
        """Map signal to impact."""
        sig = signal.lower()
        if sig in ("positive", "bullish"):
            return "positive"
        if sig in ("negative", "bearish"):
            return "negative"
        if sig == "mixed":
            return "mixed"
        return "neutral"

    @staticmethod
    def _category_color(category: str) -> str:
        """Return color for a category."""
        colors = {
            "technical": "#3b82f6",
            "fundamental": "#10b981",
            "financial": "#f59e0b",
            "news": "#ec4899",
            "announcement": "#8b5cf6",
            "context": "#64748b",
        }
        return colors.get(category, "#888888")

    @staticmethod
    def _short_label(node_id: str) -> str:
        """Extract readable label from node_id."""
        base = node_id.split("#")[0]
        if "|" in base:
            parts = base.split("|")
            name = parts[2] if len(parts) >= 3 else base
        elif "::" in base:
            parts = base.split("::")
            name = parts[-1] if len(parts) >= 2 else base
        else:
            name = base
        return name.replace("_", " ")


# ── Quick test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simple sanity test
    print("tree_builder.py loaded successfully")
    print(f"Financial groups defined: {len(_FINANCIAL_GROUPS)}")
    print(f"Group order: {_GROUP_ORDER}")
