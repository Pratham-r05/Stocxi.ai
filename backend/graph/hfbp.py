"""
hfbp.py — Horizon-Aware Forward-Backward Propagation (HFBP) algorithm.

This is the intelligence core of the Stocxi knowledge graph.

Algorithm overview:
  INITIALIZATION
    Every node starts with effective_weight = 0.0.

  FORWARD PASS
    Step 1 — Seed activation: each node gets a raw_activation from its signal_strength,
             normalized value, or mood_score (category-dependent).
    Step 2 — Edge propagation: activations flow through edges, modified by edge type
             (CONFIRMS ×1.0, AMPLIFIES ×1.2, CONTRADICTS ×-1.0, etc.)
    Step 3 — Horizon lens: multiply each node's activation by its horizon_sensitivity
             coefficient (news matters more for SHORT; fundamentals for LONG).
    Step 4 — Normalize: effective_weights clipped and rescaled to [0, 1].

  GEMINI REASONING PASS (in stocxi_knowledge_graph.py)
    Step 5 — Serialize top-weight nodes for LLM.
    Step 6 — Send to Gemini with instructions to assign per-node relevance scores.

  BACKWARD PASS
    Step 7 — Receive Gemini's per-node relevance scores.
    Step 8 — Update edge weights using gradient signal:
             w = w + lr × (gemini_relevance[T] - T.effective_weight) × S.raw_activation
    Step 9 — Clamp all weights to [0, 1].

  PERSISTENCE
    Updated edge weights saved to JSON per-ticker.
    Next analysis loads them, bypassing priors — graph converges over ~5 runs.

References: Stocxi Knowledge Graph Rebuild V2 spec §3.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from backend.graph.builder import Edge, EDGE_MODIFIERS, EDGE_WEIGHT_PRIORS, _weight_key
from backend.schemas.node import Node, NodeCategory, NodeSignal

logger = logging.getLogger(__name__)

# ── Horizon sensitivity table ─────────────────────────────────────────────────
# Controls how much each node category contributes for each horizon.
# Based on spec §3.2 — "apply horizon lens".

_HORIZON_SENSITIVITY: dict[str, dict[str, float]] = {
    "short": {
        "news":          1.00,
        "announcement":  0.95,
        "momentum_tech": 0.95,
        "trend_tech":    0.80,
        "volume_tech":   0.85,
        "volatility_tech": 0.90,
        "fundamental":   0.15,
        "financial":     0.10,
        "context":       0.60,
    },
    "medium": {
        "news":          0.45,
        "announcement":  0.65,
        "momentum_tech": 0.55,
        "trend_tech":    0.70,
        "volume_tech":   0.60,
        "volatility_tech": 0.65,
        "fundamental":   0.75,
        "financial":     0.80,
        "context":       0.70,
    },
    "long": {
        "news":          0.10,
        "announcement":  0.30,
        "momentum_tech": 0.10,
        "trend_tech":    0.25,
        "volume_tech":   0.15,
        "volatility_tech": 0.20,
        "fundamental":   0.95,
        "financial":     0.98,
        "context":       0.50,
    },
}

# Technical node name → subcategory for horizon sensitivity lookup
_MOMENTUM_TECH: frozenset[str] = frozenset([
    "RSI_14", "Stochastic_K", "Stochastic_D", "Williams_R", "CCI", "ROC",
])
_TREND_TECH: frozenset[str] = frozenset([
    "MACD", "ADX_14", "SMA_20", "SMA_50", "SMA_200", "EMA_12", "EMA_26",
    "Ichimoku", "Parabolic_SAR",
])
_VOLUME_TECH: frozenset[str] = frozenset([
    "OBV", "VWAP", "Volume_SMA_20", "CMF", "MFI",
])
_VOLATILITY_TECH: frozenset[str] = frozenset([
    "Bollinger_Upper", "Bollinger_Lower", "Bollinger_Bands", "ATR_14", "52W_HL_Ratio",
])

# Financial statement node names (vs ratio nodes)
_FINANCIAL_NODE_NAMES: frozenset[str] = frozenset([
    "Revenue_Quarterly", "Net_Profit_Quarterly", "OPM_Quarterly",
    "EPS_Quarterly", "Revenue_Annual", "Net_Profit_Annual",
    "Balance_Sheet", "Cash_Flow", "Revenue_Growth", "Profit_Growth",
    "Debt_To_Equity", "Operating_Cash_Flow",
])

# HFBP learning rate — conservative; we trust Gemini but not blindly
_LEARNING_RATE: float = 0.1

# Weight persistence directory
_WEIGHTS_DIR: Path = Path(__file__).parents[2] / "graph_weights"


# ── Public API ─────────────────────────────────────────────────────────────────

class HFBPGraph:
    """
    Horizon-Aware Forward-Backward Propagation graph.

    Wraps a list of nodes + edges and runs the HFBP algorithm to produce
    effective_weights for every node, then updates edge weights from Gemini's
    relevance feedback.

    Usage:
        graph = HFBPGraph(nodes, edges, horizon="short")
        effective_weights = graph.forward_propagate()
        # ... send serialized graph to Gemini, get relevance_scores ...
        updated_weights = graph.backward_propagate(relevance_scores)
        HFBPGraph.save_weights(ticker, updated_weights)
    """

    def __init__(
        self,
        nodes: list[Node],
        edges: list[Edge],
        horizon: str = "medium",
    ) -> None:
        """
        Initialize HFBP graph.

        Args:
            nodes:   All nodes for a single stock analysis run.
            edges:   Typed edges from builder.build_edges().
            horizon: "short", "medium", or "long".
        """
        self.nodes   = nodes
        self.edges   = edges
        self.horizon = horizon.lower()

        # Build internal lookup structures
        self._node_map: dict[str, Node] = {n.node_id: n for n in nodes}
        self._out_edges: dict[str, list[Edge]] = {}
        for edge in edges:
            self._out_edges.setdefault(edge.from_id, []).append(edge)

        # State populated by forward_propagate()
        self.raw_activations:  dict[str, float] = {}
        self.effective_weights: dict[str, float] = {}

    # ── Forward pass ───────────────────────────────────────────────────────────

    def forward_propagate(self) -> dict[str, float]:
        """
        Run forward pass: seed activations → propagate through edges → apply
        horizon lens → normalize to [0, 1].

        Returns:
            Dict mapping node_id → effective_weight ∈ [0, 1].
        """
        sens = _HORIZON_SENSITIVITY.get(self.horizon, _HORIZON_SENSITIVITY["medium"])

        # Step 1: Seed raw activations
        raw: dict[str, float] = {}
        for node in self.nodes:
            raw[node.node_id] = _seed_activation(node)
        self.raw_activations = raw

        # Step 2: Propagate activations through edges (single pass, topological-ish)
        activated: dict[str, float] = dict(raw)

        for edge in self.edges:
            if edge.from_id not in self._node_map:
                continue  # virtual cluster nodes — skip

            src_act = raw.get(edge.from_id, 0.0)
            contribution = src_act * edge.weight
            modifier = EDGE_MODIFIERS.get(edge.relation, 1.0)

            if edge.to_id not in activated:
                activated[edge.to_id] = 0.0

            if edge.relation == "TRIGGERS":
                # TRIGGERS: max not additive
                activated[edge.to_id] = max(
                    activated[edge.to_id],
                    contribution * modifier,
                )
            else:
                activated[edge.to_id] = activated[edge.to_id] + contribution * modifier

        # Step 3: Apply horizon lens
        weighted: dict[str, float] = {}
        for node_id, act in activated.items():
            node = self._node_map.get(node_id)
            if node is None:
                continue
            h_sens = _horizon_sensitivity_for(node, sens)
            weighted[node_id] = act * h_sens

        # Step 4: Normalize to [0, 1]
        if weighted:
            max_w = max(abs(v) for v in weighted.values()) or 1.0
            normalized = {nid: max(0.0, min(1.0, v / max_w)) for nid, v in weighted.items()}
        else:
            normalized = {}

        self.effective_weights = normalized
        return normalized

    # ── Backward pass ──────────────────────────────────────────────────────────

    def backward_propagate(
        self,
        gemini_relevance: dict[str, float],
    ) -> dict[str, float]:
        """
        Update edge weights based on Gemini's per-node relevance scores.

        For each edge S → T:
            error = gemini_relevance[T] - T.effective_weight
            new_weight = old_weight + lr × error × S.raw_activation

        Args:
            gemini_relevance: {node_id: score 0-1} from Gemini's analysis output.

        Returns:
            Dict of updated edge weights keyed by _weight_key(from, to, relation).
            Store these via save_weights().
        """
        if not self.effective_weights:
            logger.warning("hfbp: backward_propagate called before forward_propagate")
            self.forward_propagate()

        updated: dict[str, float] = {}

        for edge in self.edges:
            if edge.from_id not in self._node_map:
                continue

            tgt_ew  = self.effective_weights.get(edge.to_id, 0.0)
            tgt_rel = gemini_relevance.get(edge.to_id, tgt_ew)  # fallback to effective_weight
            src_raw = self.raw_activations.get(edge.from_id, 0.0)

            error = tgt_rel - tgt_ew
            new_weight = edge.weight + (_LEARNING_RATE * error * src_raw)
            new_weight = max(0.0, min(1.0, new_weight))   # clamp to [0, 1]

            wk = _weight_key(edge.from_id, edge.to_id, edge.relation)
            updated[wk] = round(new_weight, 6)

        logger.debug(
            "hfbp: backward_propagate — %d edge weights updated (horizon=%s)",
            len(updated), self.horizon,
        )
        return updated

    # ── Summary for serialization ──────────────────────────────────────────────

    def top_nodes(self, n: int = 20, min_weight: float = 0.30) -> list[tuple[str, float]]:
        """Return top-N nodes sorted by effective_weight, filtered by min_weight.

        Args:
            n:          Max number of nodes to return.
            min_weight: Minimum effective_weight threshold.

        Returns:
            List of (node_id, effective_weight) tuples, sorted descending.
        """
        items = [
            (nid, w)
            for nid, w in self.effective_weights.items()
            if w >= min_weight and nid in self._node_map
        ]
        items.sort(key=lambda x: x[1], reverse=True)
        return items[:n]

    def low_weight_nodes(self, max_weight: float = 0.30) -> list[tuple[str, float]]:
        """Return nodes below the weight threshold (excluded from primary analysis).

        Args:
            max_weight: Threshold below which nodes are considered low-weight.

        Returns:
            List of (node_id, effective_weight) tuples, sorted descending.
        """
        items = [
            (nid, w)
            for nid, w in self.effective_weights.items()
            if w < max_weight and nid in self._node_map
        ]
        items.sort(key=lambda x: x[1], reverse=True)
        return items

    # ── Weight persistence ─────────────────────────────────────────────────────

    @staticmethod
    def save_weights(ticker: str, weights: dict[str, float]) -> None:
        """Persist updated edge weights for a ticker to disk.

        Weights are stored at graph_weights/{ticker}.json and loaded on the
        next analysis run to bypass cold-start priors.

        Args:
            ticker:  NSE ticker symbol (used as filename).
            weights: Dict from backward_propagate() — {weight_key: float}.
        """
        _WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        path = _WEIGHTS_DIR / f"{ticker.upper()}.json"

        # Merge with existing weights (new values override old)
        existing: dict[str, float] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}

        existing.update(weights)

        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        logger.info("hfbp: saved %d weights for %s → %s", len(weights), ticker, path)

    @staticmethod
    def load_weights(ticker: str) -> dict[str, float]:
        """Load previously learned edge weights for a ticker.

        Args:
            ticker: NSE ticker symbol.

        Returns:
            Dict {weight_key: float}. Empty dict if no persisted weights exist.
        """
        path = _WEIGHTS_DIR / f"{ticker.upper()}.json"
        if not path.exists():
            logger.debug("hfbp: no persisted weights for %s — using priors", ticker)
            return {}

        try:
            weights = json.loads(path.read_text(encoding="utf-8"))
            logger.debug(
                "hfbp: loaded %d persisted weights for %s", len(weights), ticker
            )
            return weights
        except Exception as exc:
            logger.warning("hfbp: failed to load weights for %s: %s", ticker, exc)
            return {}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _seed_activation(node: Node) -> float:
    """Compute raw_activation for a node from its signal data.

    Priority:
      - signal_strength in value_raw → direct 0-1 value
      - mood_score in value_raw (news/announcement) → direct 0-1
      - signal enum → positive=0.8, negative=0.8, neutral=0.3
      - weight from weights.yaml → fallback normalize

    Returns:
        Float ∈ [0, 1].
    """
    vr = node.value_raw or {}

    # 1. signal_strength (technical indicators from agent_technical)
    ss = vr.get("signal_strength") or vr.get("strength")
    if ss is not None:
        try:
            return float(max(0.0, min(1.0, ss)))
        except (TypeError, ValueError):
            pass

    # 2. mood_score / relevance (news)
    ms = vr.get("mood_score") or vr.get("llm_relevance") or vr.get("relevance_score")
    if ms is not None:
        try:
            return float(max(0.0, min(1.0, ms)))
        except (TypeError, ValueError):
            pass

    # 3. Signal enum → fixed activation
    if node.signal == NodeSignal.positive:
        return 0.75
    if node.signal == NodeSignal.negative:
        return 0.75
    if node.signal == NodeSignal.neutral:
        return 0.30

    # 4. Fallback: normalized weight (already in [0,1] but often small)
    return float(min(1.0, max(0.0, node.weight)))


def _horizon_sensitivity_for(node: Node, sens: dict[str, float]) -> float:
    """Return the horizon sensitivity coefficient for a given node.

    Maps node category + name to one of the horizon sensitivity keys.

    Args:
        node: The node to look up.
        sens: Sensitivity dict for the chosen horizon.

    Returns:
        Float sensitivity coefficient.
    """
    cat = node.category

    if cat == NodeCategory.news:
        return sens.get("news", 0.5)

    if cat == NodeCategory.announcement:
        return sens.get("announcement", 0.5)

    if cat == NodeCategory.context:
        return sens.get("context", 0.5)

    if cat == NodeCategory.technical:
        if node.name in _MOMENTUM_TECH:
            return sens.get("momentum_tech", 0.5)
        if node.name in _TREND_TECH:
            return sens.get("trend_tech", 0.5)
        if node.name in _VOLUME_TECH:
            return sens.get("volume_tech", 0.5)
        if node.name in _VOLATILITY_TECH:
            return sens.get("volatility_tech", 0.5)
        return sens.get("trend_tech", 0.5)  # default for unknown technical

    if cat == NodeCategory.fundamental:
        if node.name in _FINANCIAL_NODE_NAMES:
            return sens.get("financial", 0.5)
        return sens.get("fundamental", 0.5)

    return 0.5  # safe default
