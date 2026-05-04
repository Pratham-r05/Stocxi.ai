"""
test_graph_phase3.py — Unit tests for Phase 3 knowledge graph (no network, no DB).

Tests:
  - scorer.recency_factor: all four bands
  - scorer.score_node: formula verification
  - scorer.top_nodes: correct ranking and slicing
  - builder.build_edges: same_domain, supports, contradicts, derived_from,
                          part_of, edge deduplication, empty-input safety
"""

from __future__ import annotations

import pytest
from datetime import date, datetime, timezone

from schemas.node import Node, NodeCategory, NodeSignal, HorizonRelevance
from graph.scorer import recency_factor, score_node, score_all, top_nodes
from graph.builder import build_edges, Edge


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_node(
    name: str,
    category: NodeCategory = NodeCategory.technical,
    signal: NodeSignal = NodeSignal.positive,
    weight: float = 0.5,
    confidence: float = 1.0,
    as_of_date: date = date(2026, 4, 25),
    stock: str = "RELIANCE",
) -> Node:
    """Create a minimal test Node."""
    return Node(
        stock=stock,
        category=category,
        name=name,
        value=f"{name} test value",
        signal=signal,
        confidence=confidence,
        source="nse_library",
        as_of_date=as_of_date,
        fetched_at_ist=datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc),
        weight=weight,
        horizon_relevance=HorizonRelevance.both,
    )


ANALYSIS_DATE = date(2026, 4, 26)


# ── scorer tests ──────────────────────────────────────────────────────────────

class TestRecencyFactor:
    def test_band_under_7(self):
        """Age < 7 days → 1.0"""
        as_of = date(2026, 4, 24)   # 2 days ago
        assert recency_factor(as_of, ANALYSIS_DATE) == 1.0

    def test_band_7_to_30(self):
        """Age 7–29 days → 0.8"""
        as_of = date(2026, 4, 6)    # 20 days ago
        assert recency_factor(as_of, ANALYSIS_DATE) == 0.8

    def test_band_30_to_90(self):
        """Age 30–89 days → 0.5"""
        as_of = date(2026, 2, 5)    # 80 days ago
        assert recency_factor(as_of, ANALYSIS_DATE) == 0.5

    def test_band_over_90(self):
        """Age ≥ 90 days → 0.2"""
        as_of = date(2025, 12, 1)   # ~147 days ago
        assert recency_factor(as_of, ANALYSIS_DATE) == 0.2

    def test_future_date_clamps_to_1(self):
        """Future as_of_date should not crash — clamp to 1.0."""
        future = date(2026, 5, 1)
        assert recency_factor(future, ANALYSIS_DATE) == 1.0

    def test_exact_7_day_boundary(self):
        """Exactly 7 days → second band (0.8)."""
        as_of = date(2026, 4, 19)   # 7 days ago
        assert recency_factor(as_of, ANALYSIS_DATE) == 0.8

    def test_exact_30_day_boundary(self):
        """Exactly 30 days → third band (0.5)."""
        as_of = date(2026, 3, 27)   # 30 days ago
        assert recency_factor(as_of, ANALYSIS_DATE) == 0.5


class TestScoreNode:
    def test_formula_fresh_node(self):
        """score = weight × confidence × recency (1.0 for fresh)"""
        node = _make_node("RSI_14", weight=0.6, confidence=1.0,
                          as_of_date=date(2026, 4, 25))
        score = score_node(node, ANALYSIS_DATE)
        assert abs(score - 0.6) < 1e-5

    def test_formula_stale_node(self):
        """Stale (>90d) node gets 0.2 recency factor."""
        node = _make_node("RSI_14", weight=0.6, confidence=1.0,
                          as_of_date=date(2025, 12, 1))
        score = score_node(node, ANALYSIS_DATE)
        assert abs(score - 0.6 * 1.0 * 0.2) < 1e-5

    def test_low_confidence_reduces_score(self):
        """L3 source (confidence=0.70) lowers score."""
        node = _make_node("RSI_14", weight=0.5, confidence=0.7,
                          as_of_date=date(2026, 4, 25))
        score = score_node(node, ANALYSIS_DATE)
        assert abs(score - 0.5 * 0.7 * 1.0) < 1e-5

    def test_score_clamped_above_1(self):
        """Weight > 1 should not push score above 1."""
        node = _make_node("RSI_14", weight=5.0, confidence=1.0,
                          as_of_date=date(2026, 4, 25))
        score = score_node(node, ANALYSIS_DATE)
        assert score <= 1.0

    def test_zero_weight_zero_score(self):
        node = _make_node("RSI_14", weight=0.0, confidence=1.0)
        assert score_node(node, ANALYSIS_DATE) == 0.0


class TestTopNodes:
    def test_top_returns_highest_scored(self):
        nodes = [
            _make_node("A", weight=0.1),
            _make_node("B", weight=0.9),
            _make_node("C", weight=0.5),
        ]
        scores = score_all(nodes, ANALYSIS_DATE)
        ranked = top_nodes(nodes, scores, n=2)
        assert len(ranked) == 2
        assert ranked[0].name == "B"
        assert ranked[1].name == "C"

    def test_top_n_larger_than_nodes(self):
        nodes = [_make_node("X", weight=0.3)]
        scores = score_all(nodes, ANALYSIS_DATE)
        result = top_nodes(nodes, scores, n=100)
        assert len(result) == 1


# ── builder tests ─────────────────────────────────────────────────────────────

class TestBuildEdges:
    def test_empty_nodes_returns_empty(self):
        assert build_edges([], {}, "test") == []

    def test_same_domain_within_category(self):
        """Two technical nodes should get a same_domain edge."""
        n1 = _make_node("RSI_14", weight=0.5)
        n2 = _make_node("MACD",   weight=0.5)
        scores = score_all([n1, n2], ANALYSIS_DATE)
        edges = build_edges([n1, n2], scores, "test")
        rels = {e.relation for e in edges}
        assert "same_domain" in rels

    def test_supports_cross_category_same_signal(self):
        """Positive technical + positive fundamental → supports edge."""
        n_tech = _make_node("RSI_14", category=NodeCategory.technical,
                             signal=NodeSignal.positive, weight=0.5)
        n_fund = _make_node("PE_Ratio", category=NodeCategory.fundamental,
                             signal=NodeSignal.positive, weight=0.4)
        scores = score_all([n_tech, n_fund], ANALYSIS_DATE)
        edges = build_edges([n_tech, n_fund], scores, "test")
        rels = {e.relation for e in edges}
        assert "supports" in rels

    def test_contradicts_cross_category_opposite_signal(self):
        """Positive technical + negative fundamental → contradicts edge."""
        n_tech = _make_node("RSI_14", category=NodeCategory.technical,
                             signal=NodeSignal.positive, weight=0.5)
        n_fund = _make_node("Revenue_Quarterly", category=NodeCategory.fundamental,
                             signal=NodeSignal.negative, weight=0.4)
        scores = score_all([n_tech, n_fund], ANALYSIS_DATE)
        edges = build_edges([n_tech, n_fund], scores, "test")
        rels = {e.relation for e in edges}
        assert "contradicts" in rels

    def test_no_supports_for_neutral_neutral(self):
        """Neutral × Neutral should not generate supports."""
        n1 = _make_node("RSI_14",   category=NodeCategory.technical,
                         signal=NodeSignal.neutral, weight=0.5)
        n2 = _make_node("PE_Ratio", category=NodeCategory.fundamental,
                         signal=NodeSignal.neutral, weight=0.4)
        scores = score_all([n1, n2], ANALYSIS_DATE)
        edges = build_edges([n1, n2], scores, "test")
        rels = {e.relation for e in edges}
        assert "supports" not in rels

    def test_derived_from_eps_net_profit(self):
        """EPS node should get derived_from edge from Net_Profit_Quarterly."""
        n_profit = _make_node("Net_Profit_Quarterly", category=NodeCategory.fundamental,
                               weight=0.5)
        n_eps    = _make_node("EPS", category=NodeCategory.fundamental, weight=0.3)
        scores   = score_all([n_profit, n_eps], ANALYSIS_DATE)
        edges    = build_edges([n_profit, n_eps], scores, "test")
        derived  = [e for e in edges if e.relation == "derived_from"]
        assert len(derived) >= 1
        assert any(e.from_id == n_profit.node_id and e.to_id == n_eps.node_id
                   for e in derived)

    def test_part_of_cluster(self):
        """RSI_14 should get a part_of edge to momentum_cluster."""
        n_rsi = _make_node("RSI_14", category=NodeCategory.technical, weight=0.5)
        scores = score_all([n_rsi], ANALYSIS_DATE)
        edges  = build_edges([n_rsi], scores, "test")
        part_of = [e for e in edges if e.relation == "part_of"]
        assert len(part_of) >= 1
        assert any("momentum_cluster" in e.to_id for e in part_of)

    def test_no_duplicate_edges(self):
        """Same (from_id, to_id, relation) must not appear twice."""
        n1 = _make_node("RSI_14", category=NodeCategory.technical,
                         signal=NodeSignal.positive, weight=0.5)
        n2 = _make_node("MACD",   category=NodeCategory.technical,
                         signal=NodeSignal.positive, weight=0.5)
        scores = score_all([n1, n2], ANALYSIS_DATE)
        edges  = build_edges([n1, n2, n1, n2], scores, "test")  # duplicated input
        seen: set[tuple] = set()
        for e in edges:
            key = (e.from_id, e.to_id, e.relation)
            assert key not in seen, f"Duplicate edge: {key}"
            seen.add(key)

    def test_edge_strength_is_product_of_scores(self):
        """strength should be score_a × score_b."""
        n1 = _make_node("RSI_14",   category=NodeCategory.technical,
                         signal=NodeSignal.positive, weight=0.5, confidence=1.0)
        n2 = _make_node("PE_Ratio", category=NodeCategory.fundamental,
                         signal=NodeSignal.positive, weight=0.4, confidence=1.0)
        scores = score_all([n1, n2], ANALYSIS_DATE)
        edges  = build_edges([n1, n2], scores, "test")
        supports = [e for e in edges if e.relation == "supports"]
        assert len(supports) >= 1
        expected = round(scores[n1.node_id] * scores[n2.node_id], 4)
        assert any(abs(e.strength - expected) < 1e-4 for e in supports)

    def test_single_node_no_crash(self):
        """Single node → only part_of edges (if applicable), no cross-node edges."""
        n = _make_node("RSI_14", weight=0.5)
        scores = score_all([n], ANALYSIS_DATE)
        edges  = build_edges([n], scores, "test")
        cross  = [e for e in edges if e.relation in ("supports", "contradicts")]
        assert len(cross) == 0

    def test_analysis_id_stamped(self):
        """All edges should carry the analysis_id."""
        n1 = _make_node("RSI_14", weight=0.5)
        n2 = _make_node("MACD",   weight=0.5)
        scores = score_all([n1, n2], ANALYSIS_DATE)
        edges  = build_edges([n1, n2], scores, "run-42")
        assert all(e.analysis_id == "run-42" for e in edges)
