"""
builder.py — HFBP-aware knowledge graph edge builder for Stocxi.

Produces typed Edge objects using the 8 edge types defined in the
Horizon-Aware Forward-Backward Propagation (HFBP) algorithm:

  CONFIRMS      — same-direction signal reinforcement (modifier ×1.0)
  AMPLIFIES     — strong same-direction confirmation (modifier ×1.2)
  CONTRADICTS   — opposing signals conflict (modifier ×-1.0)
  DAMPENS       — weakens a signal without full contradiction (modifier ×-0.8)
  CAUSES        — causal link from one node to another (modifier ×1.1)
  TRIGGERS      — event that forces re-evaluation; max not additive (modifier ×1.3)
  CONTEXTUALIZES — soft background influence (modifier ×0.5)
  CORRELATES    — weakest, statistical co-movement (modifier ×0.4)

Edge construction is conditional:
  - RSI confirms Bollinger only when RSI > 70 AND price at upper band (or < 30 + lower).
  - ADX amplifies trend indicators when ADX > 25; dampens when ADX < 20.
  - Announcement TRIGGERS fundamental nodes, not just CONFIRMS.
  - News materiality HIGH → CAUSES sentiment; medium → CONTEXTUALIZES.

Edge weight initialization uses HFBP priors. After each analysis run, weights
are updated via backward propagation (see hfbp.py).

Rules:
  1. All edges require both endpoint node_ids to exist in the current graph.
  2. CONTRADICTS overrides CONFIRMS when both conditions fire.
  3. Strength = source_score × target_score (from scorer.py relevance scores).
  4. No duplicate (from_id, to_id, relation) triples.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from backend.schemas.node import Node, NodeCategory, NodeSignal

logger = logging.getLogger(__name__)

# ── Edge type definition ───────────────────────────────────────────────────────

HFBPRelation = Literal[
    "CONFIRMS", "AMPLIFIES", "CONTRADICTS", "DAMPENS",
    "CAUSES", "TRIGGERS", "CONTEXTUALIZES", "CORRELATES",
]

# Forward-pass modifier for each edge type (applied to source activation)
EDGE_MODIFIERS: dict[str, float] = {
    "CONFIRMS":       1.0,
    "AMPLIFIES":      1.2,
    "CONTRADICTS":   -1.0,
    "DAMPENS":       -0.8,
    "CAUSES":         1.1,
    "TRIGGERS":       1.3,   # applied as max(current, contribution × 1.3)
    "CONTEXTUALIZES": 0.5,
    "CORRELATES":     0.4,
}

# Initial edge weights (priors) — used on first analysis of a stock.
# After each run, backward pass updates these per (ticker, relation, from_id, to_id).
EDGE_WEIGHT_PRIORS: dict[str, float] = {
    "CONFIRMS":       0.60,
    "AMPLIFIES":      0.65,
    "CONTRADICTS":    0.60,
    "DAMPENS":        0.55,
    "CAUSES":         0.70,
    "TRIGGERS":       0.75,
    "CONTEXTUALIZES": 0.45,
    "CORRELATES":     0.35,
}


@dataclass(frozen=True)
class Edge:
    """
    A typed, weighted directed edge in the Stocxi knowledge graph.

    Attributes:
        from_id:    node_id of the source node.
        to_id:      node_id of the target node.
        relation:   One of the 8 HFBPRelation literals.
        weight:     ∈ [0, 1] — initialized from EDGE_WEIGHT_PRIORS, updated by HFBP.
        strength:   ∈ [0, 1] — product of source × target relevance scores.
        direction:  "unidirectional" or "bidirectional".
        label:      Human-readable description of the relationship.
        analysis_id: Trace ID linking this edge to its analysis run.
    """
    from_id:     str
    to_id:       str
    relation:    HFBPRelation
    weight:      float          # HFBP prior or learned weight
    strength:    float          # score_a × score_b
    direction:   str = "unidirectional"
    label:       str = ""
    analysis_id: str = ""


# ── Technical subcategory sets ─────────────────────────────────────────────────
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

# Announcement types that TRIGGER fundamental re-evaluation
_ANNOUNCEMENT_TRIGGERS: frozenset[str] = frozenset([
    "Board_Meeting", "Result_Announced", "Corporate_Action",
])
# Announcement types that AMPLIFY sentiment
_ANNOUNCEMENT_AMPLIFIES: frozenset[str] = frozenset([
    "Dividend_Declared", "Bonus_Split",
])
# Announcement types that DAMPEN sentiment (risk events)
_ANNOUNCEMENT_DAMPENS: frozenset[str] = frozenset([
    "SEBI_Action", "Promoter_Trade",
])

# Financial nodes that earnings announcements TRIGGER
_EARNINGS_TRIGGER_TARGETS: frozenset[str] = frozenset([
    "Revenue_Growth", "Profit_Growth", "Net_Profit_Quarterly",
    "Revenue_Quarterly", "OPM_Quarterly", "EPS_Quarterly",
])

# High-severity news signal classes
_NEWS_HIGH_SEVERITY: frozenset[str] = frozenset([
    "regulatory_sebi_action", "fraud_allegation", "credit_rating_change",
    "leadership_change", "ma_event", "major_contract", "dividend_or_buyback",
    "earnings_result",
])

# News classes that TRIGGER fundamental nodes
_NEWS_FUNDAMENTAL_TRIGGERS: dict[str, list[str]] = {
    "earnings_result":    ["Revenue_Growth", "Profit_Growth", "EPS_Quarterly"],
    "major_contract":     ["Revenue_Quarterly", "Revenue_Annual"],
    "ma_event":           ["Net_Profit_Annual", "Revenue_Annual"],
    "dividend_or_buyback": ["EPS", "Net_Profit_Annual"],
    "credit_rating_change": ["Debt_To_Equity"],
}

# ADX thresholds for AMPLIFIES / DAMPENS of trend nodes
_ADX_STRONG_TREND = 25.0
_ADX_WEAK_TREND   = 20.0

# RSI thresholds for conditional edge type selection
_RSI_OVERBOUGHT = 70.0
_RSI_OVERSOLD   = 30.0


# ── Public API ─────────────────────────────────────────────────────────────────

def build_edges(
    nodes: list[Node],
    scores: dict[str, float],
    persisted_weights: dict[str, float] | None = None,
    analysis_id: str = "",
) -> list[Edge]:
    """Build HFBP-typed edges between nodes for one analysis run.

    Args:
        nodes:             All nodes for a single stock / single analysis run.
        scores:            {node_id: relevance_score} from scorer.py.
        persisted_weights: Learned edge weights from previous runs (keyed by
                           _weight_key()). If None, EDGE_WEIGHT_PRIORS are used.
        analysis_id:       Trace ID for this analysis run.

    Returns:
        Deduplicated list of Edge objects with HFBP types and weights.
    """
    if not nodes:
        return []

    pw = persisted_weights or {}

    # Index nodes for fast lookup
    by_name: dict[str, list[Node]] = {}
    by_cat:  dict[NodeCategory, list[Node]] = {}
    for node in nodes:
        by_name.setdefault(node.name, []).append(node)
        by_cat.setdefault(node.category, []).append(node)

    edges: list[Edge] = []
    seen:  set[tuple[str, str, str]] = set()

    def _add(
        from_id: str,
        to_id:   str,
        relation: HFBPRelation,
        *,
        bidirectional: bool = False,
    ) -> None:
        """Add edge if not already seen. Compute weight and strength."""
        key = (from_id, to_id, relation)
        if key in seen:
            return
        seen.add(key)

        # Edge weight: use learned value if available, else prior
        wk = _weight_key(from_id, to_id, relation)
        weight = pw.get(wk, EDGE_WEIGHT_PRIORS[relation])

        # Strength = score product
        s_from = scores.get(from_id, 0.0)
        s_to   = scores.get(to_id,   0.0)
        strength = round(s_from * s_to, 4)

        direction = "bidirectional" if bidirectional else "unidirectional"
        label     = _EDGE_LABELS.get(relation, relation)

        edges.append(Edge(
            from_id=from_id, to_id=to_id,
            relation=relation, weight=round(weight, 4),
            strength=strength, direction=direction,
            label=label, analysis_id=analysis_id,
        ))

    # ── 1. TECHNICAL INTERNAL EDGES (conditional) ─────────────────────────────
    _build_technical_edges(by_name, by_cat, scores, _add)

    # ── 2. NEWS + ANNOUNCEMENT EDGES ──────────────────────────────────────────
    _build_news_edges(by_name, by_cat, scores, _add)
    _build_announcement_edges(by_name, by_cat, scores, _add)

    # ── 3. FUNDAMENTAL ↔ FINANCIAL EDGES ──────────────────────────────────────
    _build_fundamental_edges(by_name, scores, _add)

    # ── 4. CROSS-LAYER: FII/DII → Price + Momentum ────────────────────────────
    _build_cross_layer_edges(by_name, by_cat, scores, _add)

    # ── 5. CONTEXTUALIZES: within-category structural cohesion ─────────────────
    _build_structural_edges(by_cat, scores, _add)

    logger.debug(
        "build_edges: %d nodes → %d edges (analysis_id=%s)",
        len(nodes), len(edges), analysis_id,
    )
    return edges


def _weight_key(from_id: str, to_id: str, relation: str) -> str:
    """Deterministic key for edge weight lookup/storage."""
    return f"{from_id}::{to_id}::{relation}"


# ── Edge label lookup ──────────────────────────────────────────────────────────
_EDGE_LABELS: dict[str, str] = {
    "CONFIRMS":       "confirms signal alignment",
    "AMPLIFIES":      "strongly amplifies — same direction high conviction",
    "CONTRADICTS":    "contradicts — opposing signals",
    "DAMPENS":        "dampens — weakens signal reliability",
    "CAUSES":         "causal link — this drives that",
    "TRIGGERS":       "triggers re-evaluation",
    "CONTEXTUALIZES": "provides soft background context",
    "CORRELATES":     "statistically co-moves (weak)",
}


# ── Section builders ───────────────────────────────────────────────────────────

def _build_technical_edges(
    by_name: dict[str, list[Node]],
    by_cat: dict[NodeCategory, list[Node]],
    scores: dict[str, float],
    _add,
) -> None:
    """Build all technical-internal edges using conditional HFBP logic."""

    tech_nodes = by_cat.get(NodeCategory.technical, [])
    if not tech_nodes:
        return

    # Helper: get numeric value from node.value_raw safely
    def _num(node: Node, key: str, default: float = 0.0) -> float:
        return float((node.value_raw or {}).get(key, default))

    # ── RSI → Bollinger (conditional) ─────────────────────────────────────────
    for rsi in by_name.get("RSI_14", []):
        rsi_val = _num(rsi, "rsi")
        bb_upper = by_name.get("Bollinger_Upper", [])
        bb_lower = by_name.get("Bollinger_Lower", [])
        bb_mid   = by_name.get("Bollinger_Bands", [])

        for bb in bb_upper:
            price_pos = (bb.value_raw or {}).get("position", "")
            if rsi_val > _RSI_OVERBOUGHT and price_pos == "near_upper":
                _add(rsi.node_id, bb.node_id, "CONFIRMS")
            elif rsi_val > _RSI_OVERBOUGHT:
                _add(rsi.node_id, bb.node_id, "CONTEXTUALIZES")
            else:
                _add(rsi.node_id, bb.node_id, "CORRELATES")

        for bb in bb_lower:
            price_pos = (bb.value_raw or {}).get("position", "")
            if rsi_val < _RSI_OVERSOLD and price_pos == "near_lower":
                _add(rsi.node_id, bb.node_id, "CONFIRMS")
            else:
                _add(rsi.node_id, bb.node_id, "CORRELATES")

        for bb in bb_mid:
            _add(rsi.node_id, bb.node_id, "CONTEXTUALIZES")

    # ── RSI → OBV (divergence check) ──────────────────────────────────────────
    for rsi in by_name.get("RSI_14", []):
        for obv in by_name.get("OBV", []):
            rsi_sig = rsi.signal
            obv_sig = obv.signal
            if rsi_sig == obv_sig:
                _add(rsi.node_id, obv.node_id, "CONFIRMS")
            elif rsi_sig != NodeSignal.neutral and obv_sig != NodeSignal.neutral:
                _add(rsi.node_id, obv.node_id, "CONTRADICTS")
            else:
                _add(rsi.node_id, obv.node_id, "CONTEXTUALIZES")

    # ── MACD → EMA crossover (CONFIRMS when same direction) ───────────────────
    for macd in by_name.get("MACD", []):
        for ema12 in by_name.get("EMA_12", []):
            if macd.signal == ema12.signal and macd.signal != NodeSignal.neutral:
                _add(macd.node_id, ema12.node_id, "CONFIRMS")
            else:
                _add(macd.node_id, ema12.node_id, "CONTEXTUALIZES")

    # ── ADX → Trend nodes (AMPLIFIES strong, DAMPENS weak) ────────────────────
    for adx in by_name.get("ADX_14", []):
        adx_val = _num(adx, "adx")
        trend_node_names = ["MACD", "SMA_20", "SMA_50", "SMA_200", "EMA_12", "EMA_26"]
        for name in trend_node_names:
            for trend_node in by_name.get(name, []):
                if adx_val > _ADX_STRONG_TREND:
                    _add(adx.node_id, trend_node.node_id, "AMPLIFIES")
                elif adx_val < _ADX_WEAK_TREND:
                    _add(adx.node_id, trend_node.node_id, "DAMPENS")
                else:
                    _add(adx.node_id, trend_node.node_id, "CONTEXTUALIZES")

    # ── ADX → RSI (DAMPENS oscillator when ADX < 20 — no strong trend) ────────
    for adx in by_name.get("ADX_14", []):
        adx_val = _num(adx, "adx")
        for rsi in by_name.get("RSI_14", []):
            if adx_val < _ADX_WEAK_TREND:
                _add(adx.node_id, rsi.node_id, "DAMPENS")
            else:
                _add(adx.node_id, rsi.node_id, "CONTEXTUALIZES")

    # ── VWAP → Price (CONTEXTUALIZES always) ──────────────────────────────────
    for vwap in by_name.get("VWAP", []):
        for price in by_name.get("Price", []):
            _add(vwap.node_id, price.node_id, "CONTEXTUALIZES")

    # ── OBV → Price (AMPLIFIES when same direction, CONTRADICTS on divergence) ─
    for obv in by_name.get("OBV", []):
        for price in by_name.get("Price", []):
            if obv.signal == price.signal and obv.signal != NodeSignal.neutral:
                _add(obv.node_id, price.node_id, "AMPLIFIES")
            elif obv.signal != NodeSignal.neutral and price.signal != NodeSignal.neutral:
                _add(obv.node_id, price.node_id, "CONTRADICTS")
            else:
                _add(obv.node_id, price.node_id, "CONTEXTUALIZES")

    # ── Bollinger squeeze + RSI → AMPLIFIES (high conviction) ─────────────────
    for bb_upper in by_name.get("Bollinger_Upper", []):
        for rsi in by_name.get("RSI_14", []):
            bb_squeeze = (bb_upper.value_raw or {}).get("squeeze", False)
            if bb_squeeze:
                _add(bb_upper.node_id, rsi.node_id, "AMPLIFIES")

    # ── MFI → OBV (money flow alignment) ──────────────────────────────────────
    for mfi in by_name.get("MFI", []):
        for obv in by_name.get("OBV", []):
            if mfi.signal == obv.signal and mfi.signal != NodeSignal.neutral:
                _add(mfi.node_id, obv.node_id, "CONFIRMS")
            else:
                _add(mfi.node_id, obv.node_id, "CONTEXTUALIZES")

    # ── MACD → RSI (CONTRADICTS on divergence) ────────────────────────────────
    for macd in by_name.get("MACD", []):
        for rsi in by_name.get("RSI_14", []):
            if macd.signal != rsi.signal and NodeSignal.neutral not in (macd.signal, rsi.signal):
                _add(macd.node_id, rsi.node_id, "CONTRADICTS")
            elif macd.signal == rsi.signal and macd.signal != NodeSignal.neutral:
                _add(macd.node_id, rsi.node_id, "CONFIRMS")

    # ── ATR → Support/Resistance (CONTEXTUALIZES) ─────────────────────────────
    for atr in by_name.get("ATR_14", []):
        for bb in by_name.get("Bollinger_Bands", by_name.get("Bollinger_Upper", [])):
            _add(atr.node_id, bb.node_id, "CONTEXTUALIZES")

    # ── 52W High/Low → Price (CONTEXTUALIZES) ─────────────────────────────────
    for hl in by_name.get("52W_HL_Ratio", []):
        for price in by_name.get("Price", []):
            _add(hl.node_id, price.node_id, "CONTEXTUALIZES")


def _build_news_edges(
    by_name: dict[str, list[Node]],
    by_cat: dict[NodeCategory, list[Node]],
    scores: dict[str, float],
    _add,
) -> None:
    """Build all news → price/technical/fundamental edges."""
    news_nodes = by_cat.get(NodeCategory.news, [])
    if not news_nodes:
        return

    price_nodes = by_name.get("Price", [])

    for news in news_nodes:
        sig_class   = (news.value_raw or {}).get("signal_class", "")
        materiality = (news.value_raw or {}).get("materiality", "medium")
        mood        = str((news.value_raw or {}).get("mood", "NEUTRAL")).upper()

        # All news → Price: CAUSES
        for price in price_nodes:
            _add(news.node_id, price.node_id, "CAUSES")

        # High-severity news ↔ technical nodes
        if sig_class in _NEWS_HIGH_SEVERITY:
            for tech in by_cat.get(NodeCategory.technical, []):
                if tech.signal == NodeSignal.neutral:
                    continue
                if (mood == "POSITIVE" and tech.signal == NodeSignal.positive) or \
                   (mood == "NEGATIVE" and tech.signal == NodeSignal.negative):
                    _add(news.node_id, tech.node_id, "AMPLIFIES")
                elif mood != "NEUTRAL" and tech.signal != NodeSignal.neutral:
                    _add(news.node_id, tech.node_id, "CONTRADICTS")

        # Materiality-based → fundamental/financial
        trigger_targets = _NEWS_FUNDAMENTAL_TRIGGERS.get(sig_class, [])
        for target_name in trigger_targets:
            for fund in by_name.get(target_name, []):
                _add(news.node_id, fund.node_id, "TRIGGERS")

        # Remaining news → sentiment node (if it exists)
        for sent in by_name.get("Sentiment", []):
            if materiality == "HIGH":
                _add(news.node_id, sent.node_id, "CAUSES")
            else:
                _add(news.node_id, sent.node_id, "CONTEXTUALIZES")


def _build_announcement_edges(
    by_name: dict[str, list[Node]],
    by_cat: dict[NodeCategory, list[Node]],
    scores: dict[str, float],
    _add,
) -> None:
    """Build announcement → fundamental/price/sentiment edges."""
    ann_nodes = by_cat.get(NodeCategory.announcement, [])
    if not ann_nodes:
        return

    price_nodes = by_name.get("Price", [])

    for ann in ann_nodes:
        # TRIGGERS: earnings/results announcements → financial nodes
        if ann.name in _ANNOUNCEMENT_TRIGGERS:
            for target_name in _EARNINGS_TRIGGER_TARGETS:
                for fund in by_name.get(target_name, []):
                    _add(ann.node_id, fund.node_id, "TRIGGERS")

        # AMPLIFIES: dividends/buybacks → price + sentiment
        if ann.name in _ANNOUNCEMENT_AMPLIFIES:
            for price in price_nodes:
                _add(ann.node_id, price.node_id, "AMPLIFIES")
            for sent in by_name.get("Sentiment", []):
                _add(ann.node_id, sent.node_id, "AMPLIFIES")

        # DAMPENS: SEBI actions, promoter sells → sentiment
        if ann.name in _ANNOUNCEMENT_DAMPENS:
            for sent in by_name.get("Sentiment", []):
                _add(ann.node_id, sent.node_id, "DAMPENS")

        # CONTEXTUALIZES: capex/board meetings → debt/balance sheet
        if ann.name == "Board_Meeting":
            for bs in by_name.get("Balance_Sheet", []):
                _add(ann.node_id, bs.node_id, "CONTEXTUALIZES")
            for dte in by_name.get("Debt_To_Equity", []):
                _add(ann.node_id, dte.node_id, "CONTEXTUALIZES")


def _build_fundamental_edges(
    by_name: dict[str, list[Node]],
    scores: dict[str, float],
    _add,
) -> None:
    """Build fundamental ↔ financial cross-node edges."""

    # PAT Growth → PE (CONFIRMS growth justifies premium; CONTRADICTS if PE high but growth slowing)
    for pat in by_name.get("Profit_Growth", []):
        for pe in by_name.get("PE_Ratio", []):
            if pat.signal == NodeSignal.positive and pe.signal == NodeSignal.negative:
                # Growth accelerating while PE looks expensive → CONFIRMS premium justified
                _add(pat.node_id, pe.node_id, "CONFIRMS")
            elif pat.signal == NodeSignal.negative and pe.signal == NodeSignal.negative:
                # Growth slowing + expensive PE → CONTRADICTS (double warning)
                _add(pat.node_id, pe.node_id, "CONTRADICTS")
            else:
                _add(pat.node_id, pe.node_id, "CONTEXTUALIZES")

    # Revenue Growth → PAT Growth (operating leverage check)
    for rev in by_name.get("Revenue_Growth", []):
        for pat in by_name.get("Profit_Growth", []):
            if rev.signal == pat.signal and rev.signal != NodeSignal.neutral:
                _add(rev.node_id, pat.node_id, "CONFIRMS")
            elif rev.signal != pat.signal and NodeSignal.neutral not in (rev.signal, pat.signal):
                _add(rev.node_id, pat.node_id, "CONTRADICTS")
            else:
                _add(rev.node_id, pat.node_id, "CONTEXTUALIZES")

    # ROE → PE (CONTEXTUALIZES: quality of earnings justifies multiple)
    for roe in by_name.get("ROE", []):
        for pe in by_name.get("PE_Ratio", []):
            _add(roe.node_id, pe.node_id, "CONTEXTUALIZES")

    # Debt/Equity → Cash Flow (DAMPENS FCF quality when high debt)
    for dte in by_name.get("Debt_To_Equity", []):
        for cf in by_name.get("Operating_Cash_Flow", by_name.get("Cash_Flow", [])):
            if dte.signal == NodeSignal.negative:
                _add(dte.node_id, cf.node_id, "DAMPENS")
            else:
                _add(dte.node_id, cf.node_id, "CONTEXTUALIZES")

    # Cash Flow → ROE (AMPLIFIES when cash-backed returns)
    for cf in by_name.get("Operating_Cash_Flow", by_name.get("Cash_Flow", [])):
        for roe in by_name.get("ROE", []):
            if cf.signal == NodeSignal.positive and roe.signal == NodeSignal.positive:
                _add(cf.node_id, roe.node_id, "AMPLIFIES")
            else:
                _add(cf.node_id, roe.node_id, "CONTEXTUALIZES")

    # Promoter Holding → Sentiment (AMPLIFIES confidence)
    for ph in by_name.get("Promoter_Holding", []):
        for sent in by_name.get("Sentiment", []):
            if ph.signal == NodeSignal.positive:
                _add(ph.node_id, sent.node_id, "AMPLIFIES")
            elif ph.signal == NodeSignal.negative:
                _add(ph.node_id, sent.node_id, "DAMPENS")

    # Promoter Pledge → Sentiment (DAMPENS: pledge = risk signal)
    for pp in by_name.get("Promoter_Pledge", []):
        for sent in by_name.get("Sentiment", []):
            _add(pp.node_id, sent.node_id, "DAMPENS")

    # Balance Sheet → Debt/Equity (CONTEXTUALIZES)
    for bs in by_name.get("Balance_Sheet", []):
        for dte in by_name.get("Debt_To_Equity", []):
            _add(bs.node_id, dte.node_id, "CONTEXTUALIZES")

    # Sector PE → Stock PE (CONTEXTUALIZES benchmark)
    for sector_ctx in by_name.get("Sector_Trend", []):
        for pe in by_name.get("PE_Ratio", []):
            _add(sector_ctx.node_id, pe.node_id, "CONTEXTUALIZES")


def _build_cross_layer_edges(
    by_name: dict[str, list[Node]],
    by_cat: dict[NodeCategory, list[Node]],
    scores: dict[str, float],
    _add,
) -> None:
    """Cross-layer edges: FII/DII, market regime, sentiment overlay."""

    # FII/DII → Price: AMPLIFIES short-term
    fii_nodes = by_name.get("FII_Holding", [])
    dii_nodes = by_name.get("DII_Holding", [])
    price_nodes = by_name.get("Price", [])

    for fii in fii_nodes:
        for price in price_nodes:
            _add(fii.node_id, price.node_id, "AMPLIFIES")
        for mom in by_cat.get(NodeCategory.technical, []):
            if mom.name in _MOMENTUM_TECH:
                _add(fii.node_id, mom.node_id, "CORRELATES")

    for dii in dii_nodes:
        for price in price_nodes:
            _add(dii.node_id, price.node_id, "CORRELATES")

    # Market Regime → all technical nodes: AMPLIFIES in bull, DAMPENS in bear
    for regime in by_name.get("Market_Regime", []):
        for tech in by_cat.get(NodeCategory.technical, []):
            if regime.signal == NodeSignal.positive:
                _add(regime.node_id, tech.node_id, "AMPLIFIES")
            elif regime.signal == NodeSignal.negative:
                _add(regime.node_id, tech.node_id, "DAMPENS")
            else:
                _add(regime.node_id, tech.node_id, "CONTEXTUALIZES")

    # Sentiment → all technical nodes: overlay
    for sent in by_name.get("Sentiment", []):
        for tech in by_cat.get(NodeCategory.technical, []):
            if sent.signal == tech.signal and sent.signal != NodeSignal.neutral:
                _add(sent.node_id, tech.node_id, "AMPLIFIES")
            elif sent.signal != NodeSignal.neutral and tech.signal != NodeSignal.neutral:
                _add(sent.node_id, tech.node_id, "CONTRADICTS")


def _build_structural_edges(
    by_cat: dict[NodeCategory, list[Node]],
    scores: dict[str, float],
    _add,
) -> None:
    """CONTEXTUALIZES edges within each category (sparse sliding window, max 3)."""
    for cat_nodes in by_cat.values():
        for i, n1 in enumerate(cat_nodes):
            for n2 in cat_nodes[i + 1: i + 4]:
                _add(n1.node_id, n2.node_id, "CORRELATES", bidirectional=True)
