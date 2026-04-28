"""
stocxi_knowledge_graph.py — Full StocxiKnowledgeGraph class.

This is the orchestrating object that wires together:
  - Node ingestion (from all data agents)
  - Edge construction (builder.py, HFBP types)
  - Relevance scoring (scorer.py)
  - Forward propagation (hfbp.py)
  - LLM serialization (for Gemini reasoning pass)
  - Backward propagation (hfbp.py, weight updates)
  - Weight persistence (hfbp.py save/load)
  - JSON export (for frontend 3D renderer)

Lifecycle per analysis run:
  1. graph = StocxiKnowledgeGraph(ticker, horizon)
  2. graph.build(nodes)           — adds nodes, builds edges, runs scorer
  3. graph.forward_propagate()    — computes effective_weight per node
  4. prompt = graph.serialize_for_llm()  — structured string for Gemini
  5. Send prompt → Gemini → receive analysis + per_node_relevance
  6. graph.backward_propagate(per_node_relevance)  — update edge weights
  7. graph.save_weights()         — persist for next run
  8. graph_json = graph.to_json() — send to frontend renderer

References: Stocxi Knowledge Graph Rebuild V2 spec §7.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from backend.graph.builder import Edge, build_edges
from backend.graph.hfbp import HFBPGraph
from backend.graph.scorer import score_all
from backend.schemas.node import Node, NodeCategory, NodeSignal

logger = logging.getLogger(__name__)

# Effective weight threshold below which nodes are considered "low weight"
# for the current horizon (excluded from primary analysis but still shown)
_LOW_WEIGHT_THRESHOLD: float = 0.30


class StocxiKnowledgeGraph:
    """
    Full knowledge graph for a single stock analysis run.

    Manages the full HFBP lifecycle from node ingestion to frontend export.
    One instance per analysis request — not shared across requests.

    Attributes:
        ticker:  NSE symbol (e.g. "RELIANCE").
        horizon: Investment horizon: "short", "medium", or "long".
    """

    def __init__(self, ticker: str, horizon: str = "medium") -> None:
        """
        Initialize an empty knowledge graph for a stock.

        Args:
            ticker:  NSE ticker, e.g. "RELIANCE".
            horizon: "short", "medium", or "long". Affects HFBP sensitivity.
        """
        self.ticker  = ticker.upper()
        self.horizon = horizon.lower()

        self._nodes:    list[Node]          = []
        self._edges:    list[Edge]          = []
        self._scores:   dict[str, float]    = {}
        self._hfbp:     HFBPGraph | None    = None
        self._effective_weights: dict[str, float] = {}
        self._updated_weights:   dict[str, float] = {}
        self._analysis_id: str = ""

    # ── Build phase ────────────────────────────────────────────────────────────

    def build(self, nodes: list[Node], analysis_id: str = "") -> None:
        """
        Ingest nodes, build edges, and run relevance scoring.

        Uses existing node creation logic from agents — this method only
        builds the graph structure on top of populated nodes.

        Args:
            nodes:       list[Node] from all data agents (pre-populated, sanitized).
            analysis_id: Trace ID for this analysis run.
        """
        self._nodes      = nodes
        self._analysis_id = analysis_id

        if not nodes:
            logger.warning("StocxiKG.build: no nodes for %s — empty graph", self.ticker)
            return

        # Compute relevance scores for all nodes
        self._scores = score_all(nodes, date.today())

        # Load persisted edge weights (empty dict = use priors on first run)
        persisted = HFBPGraph.load_weights(self.ticker)

        # Build HFBP-typed edges
        self._edges = build_edges(
            nodes,
            self._scores,
            persisted_weights=persisted,
            analysis_id=analysis_id,
        )

        logger.info(
            "StocxiKG.build: %s — %d nodes, %d edges (horizon=%s)",
            self.ticker, len(self._nodes), len(self._edges), self.horizon,
        )

    # ── Forward propagation ────────────────────────────────────────────────────

    def forward_propagate(self) -> dict[str, float]:
        """
        Run HFBP forward pass to compute effective_weight for every node.

        Must be called after build(). Effective weights determine:
          - Which nodes appear prominently in the LLM serialization.
          - Node size in the 3D graph renderer.
          - Which nodes the backward pass updates.

        Returns:
            Dict {node_id: effective_weight ∈ [0, 1]}.
        """
        self._hfbp = HFBPGraph(self._nodes, self._edges, horizon=self.horizon)
        self._effective_weights = self._hfbp.forward_propagate()

        logger.debug(
            "StocxiKG.forward_propagate: %s — top node weight=%.3f (horizon=%s)",
            self.ticker,
            max(self._effective_weights.values(), default=0.0),
            self.horizon,
        )
        return self._effective_weights

    # ── LLM serialization ─────────────────────────────────────────────────────

    def serialize_for_llm(self) -> str:
        """
        Serialize the activated graph as structured text for the Gemini prompt.

        Format (spec §5):
          ═════════════════════════════════════
          STOCXI KNOWLEDGE GRAPH — [TICKER] — [HORIZON] ANALYSIS
          ...
          TOP ACTIVATED NODES (effective_weight ≥ 0.30):
          [W:0.94] RSI_14 | TECHNICAL_MOMENTUM | signal: OVERBOUGHT | value: 72.4
            context: "..."
            → CONFIRMS (w:0.6) → BB_UPPER [W:0.88]
          ...
          LOW-WEIGHT NODES (excluded for [HORIZON] horizon):
          ...
          ═════════════════════════════════════
          ANALYSIS INSTRUCTIONS FOR MODEL:
          ...

        Returns:
            Full serialization string — inject directly into Gemini prompt.
        """
        if not self._effective_weights:
            logger.warning(
                "StocxiKG.serialize_for_llm: forward_propagate() not run yet — "
                "calling it now"
            )
            self.forward_propagate()

        node_map: dict[str, Node] = {n.node_id: n for n in self._nodes}
        ew = self._effective_weights

        # Build edge index by source
        out_edges: dict[str, list[Edge]] = {}
        for edge in self._edges:
            out_edges.setdefault(edge.from_id, []).append(edge)

        horizon_label = {
            "short":  "SHORT TERM (1–2 weeks)",
            "medium": "MEDIUM TERM (1–3 months)",
            "long":   "LONG TERM (1–3 years)",
        }.get(self.horizon, self.horizon.upper())

        horizon_goal = {
            "short":  "Identify short-term price direction, momentum, and key risk events",
            "medium": "Identify medium-term trend, fundamental inflection, and event risk",
            "long":   "Identify long-term value creation, compounding quality, and structural risks",
        }.get(self.horizon, "Analyze the stock for this horizon")

        # Sort nodes by effective_weight descending
        sorted_nodes = sorted(
            [(nid, w) for nid, w in ew.items() if nid in node_map],
            key=lambda x: x[1],
            reverse=True,
        )

        top_nodes = [(nid, w) for nid, w in sorted_nodes if w >= _LOW_WEIGHT_THRESHOLD]
        low_nodes = [(nid, w) for nid, w in sorted_nodes if w < _LOW_WEIGHT_THRESHOLD]

        lines: list[str] = []

        # Header
        lines.append("═" * 60)
        lines.append(f"STOCXI KNOWLEDGE GRAPH — {self.ticker} — {horizon_label}")
        lines.append(
            f"Nodes: {len(self._nodes)} | Edges: {len(self._edges)} | "
            f"Active: {len(top_nodes)}"
        )
        lines.append("═" * 60)
        lines.append("")
        lines.append(f"HORIZON: {horizon_label}")
        lines.append(f"INVESTOR GOAL: {horizon_goal}")
        lines.append("")

        # Top activated nodes
        lines.append(
            f"TOP ACTIVATED NODES (effective_weight ≥ {_LOW_WEIGHT_THRESHOLD}, "
            f"sorted by weight):"
        )
        lines.append("")

        for node_id, weight in top_nodes:
            node    = node_map[node_id]
            sig     = node.signal.value.upper() if hasattr(node.signal, "value") else str(node.signal).upper()
            cat_tag = _category_tag(node)

            lines.append(
                f"[W:{weight:.2f}] {node.name} | {cat_tag} | "
                f"signal: {sig} | value: {node.value}"
            )
            if node.context:
                lines.append(f'  context: "{node.context}"')

            # Outgoing edges to other top nodes
            for edge in sorted(
                out_edges.get(node_id, []),
                key=lambda e: ew.get(e.to_id, 0.0),
                reverse=True,
            )[:5]:
                tgt_w   = ew.get(edge.to_id, 0.0)
                tgt_node = node_map.get(edge.to_id)
                tgt_label = tgt_node.name if tgt_node else edge.to_id.split("|")[-1]
                if tgt_w >= _LOW_WEIGHT_THRESHOLD or edge.to_id in node_map:
                    lines.append(
                        f"  → {edge.relation} (w:{edge.weight:.2f}) "
                        f"→ {tgt_label} [W:{tgt_w:.2f}]"
                    )

            lines.append("")

        # Low-weight nodes (excluded section)
        if low_nodes:
            lines.append("")
            lines.append(
                f"LOW-WEIGHT NODES (excluded from primary analysis for "
                f"{self.horizon.upper()} horizon):"
            )
            for node_id, weight in low_nodes[:10]:
                node = node_map[node_id]
                reason = _low_weight_reason(node, self.horizon)
                lines.append(
                    f"  {node.name} [W:{weight:.2f}] — {reason}"
                )

        # Analysis instructions
        lines.append("")
        lines.append("═" * 60)
        lines.append("ANALYSIS INSTRUCTIONS FOR MODEL:")
        lines.append(f"1. Walk every node with W ≥ {_LOW_WEIGHT_THRESHOLD} — "
                     f"understand its signal in isolation")
        lines.append("2. Walk every edge between high-weight nodes — "
                     "understand confirmations and contradictions")
        lines.append("3. Assign your own RELEVANCE_SCORE (0–1) to each node "
                     "based on your understanding")
        lines.append("4. Note where your RELEVANCE_SCORE differs significantly "
                     "from the computed W score — explain why")
        lines.append(f"5. Build a coherent {self.horizon.upper()} TERM analysis "
                     "from this traversal")
        lines.append("6. Return:")
        lines.append("   - analysis paragraph (min 200 words)")
        lines.append("   - bullish_signals: list of supporting node names")
        lines.append("   - bearish_signals: list of contradicting node names")
        lines.append("   - key_risk: single biggest risk node or edge")
        lines.append("   - confidence_score: 0–1")
        lines.append("   - per_node_relevance: {node_name: score} for ALL nodes shown above")
        lines.append("═" * 60)

        return "\n".join(lines)

    # ── Backward propagation ───────────────────────────────────────────────────

    def backward_propagate(
        self,
        gemini_relevance: dict[str, float],
    ) -> dict[str, float]:
        """
        Update edge weights based on Gemini's per-node relevance scores.

        Call this after receiving Gemini's analysis output with per_node_relevance.

        Args:
            gemini_relevance: {node_name: score 0-1} or {node_id: score 0-1}.
                              Node names are resolved to node_ids automatically.

        Returns:
            Dict of updated edge weights. Store with save_weights().
        """
        if self._hfbp is None:
            logger.warning(
                "StocxiKG.backward_propagate: HFBP not initialized — "
                "running forward pass first"
            )
            self.forward_propagate()

        # Resolve node names → node_ids (Gemini returns names, not full IDs)
        name_to_id: dict[str, str] = {n.name: n.node_id for n in self._nodes}
        resolved: dict[str, float] = {}
        for key, score in gemini_relevance.items():
            if key in name_to_id:
                resolved[name_to_id[key]] = float(score)
            else:
                # Might already be a node_id
                resolved[key] = float(score)

        self._updated_weights = self._hfbp.backward_propagate(resolved)

        logger.info(
            "StocxiKG.backward_propagate: %s — %d weights updated",
            self.ticker, len(self._updated_weights),
        )
        return self._updated_weights

    # ── Persistence ────────────────────────────────────────────────────────────

    def save_weights(self) -> None:
        """Persist updated edge weights for this ticker to disk.

        Must be called after backward_propagate(). Weights are merged with
        existing persisted weights — new values override old for the same keys.
        """
        if not self._updated_weights:
            logger.debug(
                "StocxiKG.save_weights: no updated weights to save for %s",
                self.ticker,
            )
            return
        HFBPGraph.save_weights(self.ticker, self._updated_weights)

    def load_weights(self) -> dict[str, float]:
        """Load previously learned edge weights for this ticker.

        Returns:
            Dict {weight_key: float}. Empty dict if no persisted weights exist.
        """
        return HFBPGraph.load_weights(self.ticker)

    # ── JSON export for frontend ───────────────────────────────────────────────

    def to_json(self) -> dict[str, Any]:
        """
        Serialize the full graph as JSON for the frontend 3D renderer.

        Includes effective_weights so the renderer can size and color nodes
        by their HFBP-computed importance for the current horizon.

        Returns:
            Dict with keys: nodes, edges, meta.
        """
        ew = self._effective_weights

        serialized_nodes = []
        for node in self._nodes:
            n_ew = ew.get(node.node_id, 0.0)
            sig  = node.signal.value if hasattr(node.signal, "value") else str(node.signal)
            cat  = node.category.value if hasattr(node.category, "value") else str(node.category)
            serialized_nodes.append({
                "node_id":         node.node_id,
                "name":            node.name,
                "category":        cat,
                "value":           node.value,
                "signal":          sig,
                "context":         node.context,
                "effective_weight": round(n_ew, 4),
                "weight":          round(node.weight, 4),
                "confidence":      round(node.confidence, 4),
                "horizon_relevance": node.horizon_relevance.value
                                    if hasattr(node.horizon_relevance, "value")
                                    else str(node.horizon_relevance),
                "source":          node.source,
                "as_of_date":      node.as_of_date.isoformat(),
            })

        serialized_edges = []
        for edge in self._edges:
            serialized_edges.append({
                "from_id":   edge.from_id,
                "to_id":     edge.to_id,
                "relation":  edge.relation,
                "weight":    round(edge.weight, 4),
                "strength":  round(edge.strength, 4),
                "direction": edge.direction,
                "label":     edge.label,
            })

        return {
            "ticker":  self.ticker,
            "horizon": self.horizon,
            "nodes":   serialized_nodes,
            "edges":   serialized_edges,
            "meta": {
                "node_count":         len(self._nodes),
                "edge_count":         len(self._edges),
                "analysis_id":        self._analysis_id,
                "top_node_weight":    round(max(ew.values(), default=0.0), 4),
                "active_node_count":  sum(
                    1 for w in ew.values() if w >= _LOW_WEIGHT_THRESHOLD
                ),
            },
        }

    # ── Accessors ──────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Node | None:
        """Return a node by its node_id, or None if not found."""
        for node in self._nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_edges_from(self, node_id: str) -> list[Edge]:
        """Return all edges whose source is node_id."""
        return [e for e in self._edges if e.from_id == node_id]

    def get_edges_to(self, node_id: str) -> list[Edge]:
        """Return all edges whose target is node_id."""
        return [e for e in self._edges if e.to_id == node_id]

    def get_subgraph(self, node_ids: list[str]) -> dict[str, Any]:
        """Return the subgraph containing only the specified nodes and edges between them.

        Args:
            node_ids: List of node_ids to include in the subgraph.

        Returns:
            Dict with 'nodes' and 'edges' lists.
        """
        id_set = set(node_ids)
        sub_nodes = [n for n in self._nodes if n.node_id in id_set]
        sub_edges = [
            e for e in self._edges
            if e.from_id in id_set and e.to_id in id_set
        ]
        return {"nodes": sub_nodes, "edges": sub_edges}

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return len(self._edges)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _category_tag(node: Node) -> str:
    """Return a display tag for the node category (e.g. TECHNICAL_MOMENTUM)."""
    cat = node.category.value if hasattr(node.category, "value") else str(node.category)
    cat = cat.upper()

    if cat == "TECHNICAL":
        from backend.graph.hfbp import (
            _MOMENTUM_TECH, _TREND_TECH, _VOLUME_TECH, _VOLATILITY_TECH,
        )
        if node.name in _MOMENTUM_TECH:
            return "TECHNICAL_MOMENTUM"
        if node.name in _TREND_TECH:
            return "TECHNICAL_TREND"
        if node.name in _VOLUME_TECH:
            return "TECHNICAL_VOLUME"
        if node.name in _VOLATILITY_TECH:
            return "TECHNICAL_VOLATILITY"
        return "TECHNICAL"

    if cat == "FUNDAMENTAL":
        from backend.graph.hfbp import _FINANCIAL_NODE_NAMES
        if node.name in _FINANCIAL_NODE_NAMES:
            return "FINANCIAL_STATEMENT"
        return "FUNDAMENTAL_RATIO"

    return cat


def _low_weight_reason(node: Node, horizon: str) -> str:
    """Return a brief reason why a node has low weight for the given horizon."""
    cat = node.category.value if hasattr(node.category, "value") else str(node.category)

    if cat == "fundamental" and horizon == "short":
        return f"high {horizon}-term relevance suppressed — structural metric, not short-term"
    if cat == "news" and horizon == "long":
        return f"news cycle irrelevant for {horizon}-term outlook"
    if cat == "technical" and horizon == "long":
        return f"short-term momentum signal — minimal {horizon}-term impact"
    if cat == "announcement" and horizon == "long":
        return f"event-driven signal — context matters more than recency for {horizon}-term"
    return f"low activation for {horizon} horizon"
