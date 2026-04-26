"""
scorer.py — Relevance scoring for knowledge graph nodes.

Formula (from ARCHITECTURE.md §5.2):
    relevance = weight × confidence × recency_factor

    recency_factor:
      age < 7 days  → 1.0
      age < 30 days → 0.8
      age < 90 days → 0.5
      age ≥ 90 days → 0.2

Scores are used by builder.py to weight edges (strength = score_a × score_b)
and by the Analysis Agent to rank nodes for prompt inclusion.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.schemas.node import Node

logger = logging.getLogger(__name__)

# ── Recency bands (days → factor) ─────────────────────────────────────────────
_RECENCY_BANDS: list[tuple[int, float]] = [
    (7,   1.0),
    (30,  0.8),
    (90,  0.5),
]
_RECENCY_FLOOR = 0.2


def recency_factor(as_of_date: date, analysis_date: date) -> float:
    """
    Compute the recency decay factor for a node.

    Args:
        as_of_date:    Date the data was valid as of.
        analysis_date: Today's analysis date.

    Returns:
        Float ∈ [_RECENCY_FLOOR, 1.0].
    """
    age_days = (analysis_date - as_of_date).days
    if age_days < 0:
        # Future data — should not happen, clamp to fresh
        logger.warning("scorer: negative age %d days (as_of=%s, analysis=%s)",
                       age_days, as_of_date, analysis_date)
        return 1.0
    for threshold, factor in _RECENCY_BANDS:
        if age_days < threshold:
            return factor
    return _RECENCY_FLOOR


def score_node(node: Node, analysis_date: date) -> float:
    """
    Compute relevance score for a single node.

    Args:
        node:          Node to score.
        analysis_date: Date of the analysis run.

    Returns:
        Float ∈ [0, 1] — higher is more relevant.
    """
    rf = recency_factor(node.as_of_date, analysis_date)
    score = node.weight * node.confidence * rf
    # Clamp to [0, 1] — weights > 1 would push score above 1
    return min(max(round(score, 6), 0.0), 1.0)


def score_all(nodes: list[Node], analysis_date: date) -> dict[str, float]:
    """
    Score every node in a batch and return a lookup dict.

    Args:
        nodes:         All nodes for the analysis run.
        analysis_date: Date of the analysis run.

    Returns:
        Dict mapping node_id → relevance_score.
    """
    scores: dict[str, float] = {}
    for node in nodes:
        scores[node.node_id] = score_node(node, analysis_date)
    return scores


def top_nodes(
    nodes: list[Node],
    scores: dict[str, float],
    n: int = 40,
) -> list[Node]:
    """
    Return the top-N nodes sorted by relevance score (descending).

    Used by the Analysis Agent to trim the node set to the prompt budget.

    Args:
        nodes:  All nodes.
        scores: {node_id: score} from score_all().
        n:      Maximum number of nodes to return.

    Returns:
        Up to n Node objects, highest-scored first.
    """
    ranked = sorted(nodes, key=lambda nd: scores.get(nd.node_id, 0.0), reverse=True)
    return ranked[:n]
