"""
builder.py — Knowledge graph edge builder for Stocxi analysis pipeline.

Consumes a list[Node] (output of all component services) and emits typed Edge
objects that form the knowledge graph used by the Analysis Agent.

Edge types (from ARCHITECTURE.md §5.1):
  supports      — same stock, cross-category, same signal direction
  contradicts   — same stock, cross-category, opposing signals
  derived_from  — one metric is computed from another (EPS from Net Profit, etc.)
  correlates    — statistical co-movement known a priori (sector + stock momentum)
  caused_by     — causal link (dividend announcement → price signal)
  part_of       — hierarchical membership (OPM is part_of P&L domain)
  same_domain   — structural cohesion within the same category

Rules:
  1. Edges are only built between nodes of the SAME stock.
  2. `contradicts` beats `supports` when both rules fire — contradiction wins.
  3. `same_domain` links within a category are sparse (sliding window, max-3).
  4. Strength ∈ [0, 1]: product of both nodes' relevance scores.
  5. No duplicate edges (deduped by (from_id, to_id, relation)).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from backend.schemas.node import Node, NodeCategory, NodeSignal

logger = logging.getLogger(__name__)

# ── Edge types ────────────────────────────────────────────────────────────────

EdgeRelation = Literal[
    "supports", "contradicts", "derived_from",
    "correlates", "caused_by", "part_of", "same_domain"
]


@dataclass(frozen=True)
class Edge:
    """
    Typed edge between two nodes in the knowledge graph.

    Attributes:
        from_id:  node_id of the source node.
        to_id:    node_id of the target node.
        relation: one of the seven EdgeRelation literals.
        strength: ∈ [0, 1] — product of both nodes' relevance scores.
        analysis_id: trace ID linking this edge to its analysis run.
    """
    from_id:     str
    to_id:       str
    relation:    EdgeRelation
    strength:    float
    analysis_id: str = ""


# ── Domain-level groupings for derived_from / part_of rules ──────────────────

# Nodes whose values are *computed from* another node in this map.
# Key = child (derived), Value = parent set (source)
_DERIVED_FROM: dict[str, set[str]] = {
    "EPS":             {"Net_Profit_Quarterly", "Net_Profit_Annual"},
    "Revenue_Growth":  {"Revenue_Quarterly", "Revenue_Annual"},
    "Profit_Growth":   {"Net_Profit_Quarterly", "Net_Profit_Annual"},
    "OPM_Quarterly":   {"Revenue_Quarterly"},
    "MACD":            {"EMA_12", "EMA_26"},
    "Bollinger_Upper": {"SMA_20"},
    "Bollinger_Lower": {"SMA_20"},
    "Stochastic_D":    {"Stochastic_K"},
    "52W_HL_Ratio":    {"OHLCV"},
    "Debt_To_Equity":  {"Revenue_Annual"},   # D/E uses balance sheet data
}

# Nodes that are *part of* a domain cluster.
# Key = member node name, Value = domain label (used as the to_id placeholder)
_PART_OF: dict[str, str] = {
    "RSI_14":          "momentum_cluster",
    "Stochastic_K":    "momentum_cluster",
    "Stochastic_D":    "momentum_cluster",
    "Williams_R":      "momentum_cluster",
    "CCI":             "momentum_cluster",
    "MACD":            "trend_cluster",
    "ADX_14":          "trend_cluster",
    "SMA_20":          "trend_cluster",
    "SMA_50":          "trend_cluster",
    "SMA_200":         "trend_cluster",
    "EMA_12":          "trend_cluster",
    "EMA_26":          "trend_cluster",
    "OBV":             "volume_cluster",
    "VWAP":            "volume_cluster",
    "Volume_SMA_20":   "volume_cluster",
    "Revenue_Quarterly": "pl_cluster",
    "Net_Profit_Quarterly": "pl_cluster",
    "Revenue_Annual":  "pl_cluster",
    "Net_Profit_Annual": "pl_cluster",
    "OPM_Quarterly":   "pl_cluster",
    "ROE":             "return_cluster",
    "ROCE":            "return_cluster",
    "NPM":             "return_cluster",
    "OPM":             "return_cluster",
}

# Known cross-category correlations (category_a_name, category_b_name) → relation
_CORRELATES: list[tuple[str, str]] = [
    ("Market_Regime",  "RSI_14"),
    ("Market_Regime",  "MACD"),
    ("Sector_Trend",   "PE_Ratio"),
    ("Sector_Trend",   "ROE"),
    ("Promoter_Holding", "Dividend_Declared"),
]

# Causal pairs: (cause_name, effect_name)
_CAUSED_BY: list[tuple[str, str]] = [
    ("Dividend_Declared", "Price"),
    ("Board_Meeting",     "Price"),
    ("Bonus_Split",       "Price"),
    ("Corporate_Action",  "Price"),
]

# News signal-class prefixes that get news→Price caused_by edges.
# Keyed by signal_class stored in value_raw["signal_class"].
# High-severity classes also create contradicts edges against opposing technicals.
_NEWS_HIGH_SEVERITY: frozenset[str] = frozenset([
    "regulatory_sebi_action",
    "fraud_allegation",
    "credit_rating_change",
    "leadership_change",
    "ma_event",
    "major_contract",
    "dividend_or_buyback",
])

# News signal classes that correlate with fundamental nodes
_NEWS_FUNDAMENTAL_CORRELATES: dict[str, list[str]] = {
    "major_contract":    ["Revenue_Quarterly", "Revenue_Annual"],
    "ma_event":          ["Net_Profit_Annual", "Revenue_Annual"],
    "dividend_or_buyback": ["EPS", "Net_Profit_Annual"],
    "credit_rating_change": ["Debt_To_Equity"],
}


# ── Public API ────────────────────────────────────────────────────────────────

def build_edges(
    nodes: list[Node],
    scores: dict[str, float],
    analysis_id: str = "",
) -> list[Edge]:
    """
    Build typed edges between nodes in the knowledge graph.

    Args:
        nodes:       All nodes for one analysis run (single stock).
        scores:      {node_id: relevance_score} from scorer.py.
        analysis_id: Trace ID for this analysis run.

    Returns:
        Deduplicated list of Edge objects.
    """
    if not nodes:
        return []

    # Index nodes by name and by (category, name) for fast lookup
    by_name: dict[str, list[Node]] = {}
    for node in nodes:
        by_name.setdefault(node.name, []).append(node)

    edges: list[Edge] = []
    seen:  set[tuple[str, str, str]] = set()

    def _add(from_id: str, to_id: str, relation: EdgeRelation, strength: float) -> None:
        """Add edge if not duplicate."""
        key = (from_id, to_id, relation)
        if key not in seen:
            seen.add(key)
            edges.append(Edge(from_id=from_id, to_id=to_id,
                              relation=relation, strength=round(strength, 4),
                              analysis_id=analysis_id))

    def _strength(n1: Node, n2: Node) -> float:
        s1 = scores.get(n1.node_id, 0.0)
        s2 = scores.get(n2.node_id, 0.0)
        return round(s1 * s2, 4)

    # ── 1. same_domain: within-category sliding window (max 3 neighbours) ────
    by_cat: dict[NodeCategory, list[Node]] = {}
    for node in nodes:
        by_cat.setdefault(node.category, []).append(node)

    for cat_nodes in by_cat.values():
        for i, n1 in enumerate(cat_nodes):
            for n2 in cat_nodes[i + 1: i + 4]:   # up to 3 neighbours
                _add(n1.node_id, n2.node_id, "same_domain", _strength(n1, n2))

    # ── 2. supports / contradicts: cross-category, same stock ─────────────────
    cat_list = list(by_cat.keys())
    for i, cat_a in enumerate(cat_list):
        for cat_b in cat_list[i + 1:]:
            if cat_a == cat_b:
                continue
            for na in by_cat[cat_a]:
                for nb in by_cat[cat_b]:
                    sig_a = na.signal
                    sig_b = nb.signal
                    # Skip neutral-neutral — no useful cross-signal
                    if sig_a == NodeSignal.neutral and sig_b == NodeSignal.neutral:
                        continue
                    strength = _strength(na, nb)
                    if strength < 0.01:
                        continue
                    if sig_a == sig_b and sig_a != NodeSignal.neutral:
                        _add(na.node_id, nb.node_id, "supports", strength)
                    elif (sig_a == NodeSignal.positive and sig_b == NodeSignal.negative) or \
                         (sig_a == NodeSignal.negative and sig_b == NodeSignal.positive):
                        _add(na.node_id, nb.node_id, "contradicts", strength)

    # ── 3. derived_from: child → parent within known derivation pairs ─────────
    for child_name, parent_names in _DERIVED_FROM.items():
        for child_node in by_name.get(child_name, []):
            for parent_name in parent_names:
                for parent_node in by_name.get(parent_name, []):
                    _add(parent_node.node_id, child_node.node_id, "derived_from",
                         _strength(child_node, parent_node))

    # ── 4. correlates: known cross-category statistical pairs ─────────────────
    for name_a, name_b in _CORRELATES:
        for na in by_name.get(name_a, []):
            for nb in by_name.get(name_b, []):
                _add(na.node_id, nb.node_id, "correlates", _strength(na, nb))

    # ── 5. caused_by: causal pairs ────────────────────────────────────────────
    for cause_name, effect_name in _CAUSED_BY:
        for cause in by_name.get(cause_name, []):
            for effect in by_name.get(effect_name, []):
                _add(cause.node_id, effect.node_id, "caused_by", _strength(cause, effect))

    # ── 6. part_of: member → cluster virtual node ─────────────────────────────
    # We add cluster virtual nodes only as edge targets (not real graph nodes).
    # The store layer ignores virtual-node to_ids when writing the nodes table.
    for node in nodes:
        cluster = _PART_OF.get(node.name)
        if cluster:
            virtual_id = f"{node.stock}|cluster|{cluster}"
            score = scores.get(node.node_id, 0.0)
            _add(node.node_id, virtual_id, "part_of", round(score, 4))

    # ── 7. news → price caused_by (all news nodes that name Price) ────────────��
    price_nodes  = by_name.get("Price", [])
    news_nodes   = by_cat.get(NodeCategory.news, [])

    for news_node in news_nodes:
        sig_class = (news_node.value_raw or {}).get("signal_class", "")
        for price_node in price_nodes:
            # All news events can cause price movement — add caused_by edge
            _add(news_node.node_id, price_node.node_id, "caused_by",
                 _strength(news_node, price_node))

        # High-severity news: also wire contradicts against opposing technical signals
        if sig_class in _NEWS_HIGH_SEVERITY:
            tech_nodes = by_cat.get(NodeCategory.technical, [])
            for tech in tech_nodes:
                if tech.signal == NodeSignal.neutral:
                    continue
                strength = _strength(news_node, tech)
                if strength < 0.01:
                    continue
                if news_node.signal == tech.signal:
                    _add(news_node.node_id, tech.node_id, "supports", strength)
                elif (news_node.signal != NodeSignal.neutral and
                      tech.signal   != NodeSignal.neutral):
                    _add(news_node.node_id, tech.node_id, "contradicts", strength)

    # ── 8. news → fundamental correlates (earnings/contract news) ─────────────
    for news_node in news_nodes:
        sig_class = (news_node.value_raw or {}).get("signal_class", "")
        corr_targets = _NEWS_FUNDAMENTAL_CORRELATES.get(sig_class, [])
        for target_name in corr_targets:
            for fund_node in by_name.get(target_name, []):
                _add(news_node.node_id, fund_node.node_id, "correlates",
                     _strength(news_node, fund_node))

    # ── 9. news impact cluster (virtual node grouping all news) ───────────────
    for news_node in news_nodes:
        virtual_id = f"{news_node.stock}|cluster|news_impact"
        score = scores.get(news_node.node_id, 0.0)
        _add(news_node.node_id, virtual_id, "part_of", round(score, 4))

    logger.debug(
        "build_edges: %d nodes → %d edges (analysis_id=%s)",
        len(nodes), len(edges), analysis_id,
    )
    return edges
