"""
test_identity_leakage.py — Red-team anonymization CI test (ARCHITECTURE §6.1 Layer D).

Verifies that the sanitization pipeline removes all identifying tokens
(stock names, promoter names, brand names) from node values before they
reach the LLM prompt. Pure-Python — no LLM call, no network I/O.

Coverage: RELIANCE, TCS, HDFCBANK, INFY, ITC.
"""

from datetime import date, datetime, timezone

import pytest

from schemas.node import HorizonRelevance, Node, NodeCategory, NodeSignal
from util.sanitizer import AnonMap, build_anon_map, restore_text, scrub_text

_TODAY = date.today()
_NOW   = datetime.now(timezone.utc)


def _sanitize_nodes(nodes: list[Node], anon_map: AnonMap) -> list[Node]:
    """Local copy of orchestrator._sanitize_nodes — avoids importing redis at test time."""
    out: list[Node] = []
    for n in nodes:
        if n.sanitized:
            out.append(n)
        else:
            out.append(n.model_copy(update={"value": scrub_text(n.value, anon_map), "sanitized": True}))
    return out


# ── Test corpus ────────────────────────────────────────────────────────────────

_CASES = [
    {
        "stock":          "RELIANCE",
        "sector":         "Energy & Oil",
        "promoter_names": ["Mukesh Ambani"],
        "brand_names":    ["Jio", "Reliance Industries"],
        "peer_names":     ["ONGC", "BPCL"],
        "text": (
            "RELIANCE Q4 profit beats. Jio adds 8M users. "
            "Mukesh Ambani bullish on Reliance Industries expansion."
        ),
        "forbidden": ["RELIANCE", "Jio", "Mukesh Ambani", "Reliance Industries"],
    },
    {
        "stock":          "TCS",
        "sector":         "IT Services",
        "promoter_names": ["N Chandrasekaran"],
        "brand_names":    ["Tata Consultancy Services"],
        "peer_names":     ["INFY", "WIPRO"],
        "text": (
            "TCS Q3 PAT up 11%. Tata Consultancy Services wins $1B deal. "
            "N Chandrasekaran optimistic on FY26 outlook."
        ),
        "forbidden": ["TCS", "Tata Consultancy Services", "N Chandrasekaran"],
    },
    {
        "stock":          "HDFCBANK",
        "sector":         "Banking & Finance",
        "promoter_names": ["Sashidhar Jagdishan"],
        "brand_names":    ["HDFC Bank"],
        "peer_names":     ["ICICIBANK", "KOTAKBANK"],
        "text": (
            "HDFCBANK NIM stable at 3.4%. HDFC Bank loan growth 17%. "
            "Sashidhar Jagdishan guides for cautious H2."
        ),
        "forbidden": ["HDFCBANK", "HDFC Bank", "Sashidhar Jagdishan"],
    },
    {
        "stock":          "INFY",
        "sector":         "IT Services",
        "promoter_names": ["Narayana Murthy", "Nandan Nilekani"],
        "brand_names":    ["Infosys"],
        "peer_names":     ["TCS", "WIPRO"],
        "text": (
            "INFY raises FY26 guidance to 4.5-7%. Infosys wins AI deal. "
            "Narayana Murthy and Nandan Nilekani attend investor day."
        ),
        "forbidden": ["INFY", "Infosys", "Narayana Murthy", "Nandan Nilekani"],
    },
    {
        "stock":          "ITC",
        "sector":         "FMCG",
        "promoter_names": ["Sanjiv Puri"],
        "brand_names":    ["ITC Limited", "Wills"],
        "peer_names":     ["HINDUNILVR", "NESTLEIND"],
        "text": (
            "ITC Q4 cigarette volumes flat. ITC Limited expands agri business. "
            "Sanjiv Puri confident on Wills diversification."
        ),
        "forbidden": ["ITC", "ITC Limited", "Sanjiv Puri", "Wills"],
    },
]


def _mock_node(stock: str, text: str, sanitized: bool = False) -> Node:
    return Node(
        stock=stock,
        category=NodeCategory.news,
        name="headline",
        value=text,
        signal=NodeSignal.neutral,
        confidence=0.6,
        weight=0.5,
        horizon_relevance=HorizonRelevance.both,
        source="test_corpus",
        source_id="test_corpus",
        as_of_date=_TODAY,
        fetched_at_ist=_NOW,
        weight_version="test",
        sanitized=sanitized,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", _CASES, ids=[c["stock"] for c in _CASES])
def test_scrub_removes_forbidden_tokens(case):
    """scrub_text must replace every forbidden token with a placeholder."""
    anon_map = build_anon_map(
        stock=case["stock"],
        sector=case["sector"],
        promoter_names=case["promoter_names"],
        brand_names=case["brand_names"],
        peer_names=case["peer_names"],
    )
    scrubbed = scrub_text(case["text"], anon_map)

    for token in case["forbidden"]:
        assert token.lower() not in scrubbed.lower(), (
            f"[{case['stock']}] Identity leak: '{token}' still present after scrub.\n"
            f"  original: {case['text']!r}\n"
            f"  scrubbed: {scrubbed!r}"
        )
    assert "STOCK_A" in scrubbed, (
        f"[{case['stock']}] STOCK_A placeholder missing — stock ticker not replaced."
    )


@pytest.mark.parametrize("case", _CASES, ids=[c["stock"] for c in _CASES])
def test_orchestrator_sanitize_nodes(case):
    """_sanitize_nodes must flip sanitized=False→True and remove forbidden tokens."""
    anon_map = build_anon_map(
        stock=case["stock"],
        sector=case["sector"],
        promoter_names=case["promoter_names"],
        brand_names=case["brand_names"],
        peer_names=case["peer_names"],
    )
    node = _mock_node(case["stock"], case["text"])
    assert not node.sanitized

    cleaned = _sanitize_nodes([node], anon_map)
    assert len(cleaned) == 1
    clean = cleaned[0]

    assert clean.sanitized is True, "sanitized flag must be True after orchestrator scrub"
    for token in case["forbidden"]:
        assert token.lower() not in clean.value.lower(), (
            f"[{case['stock']}] Node value still contains '{token}' after _sanitize_nodes."
        )


def test_already_sanitized_nodes_pass_through():
    """Nodes with sanitized=True must not be re-scrubbed or mutated."""
    anon_map = build_anon_map(stock="RELIANCE")
    node = Node(
        stock="RELIANCE",
        category=NodeCategory.technical,
        name="RSI_14",
        value="68.5 — overbought",
        signal=NodeSignal.negative,
        confidence=0.75,
        weight=0.6,
        horizon_relevance=HorizonRelevance.short,
        source="yfinance",
        source_id="yfinance",
        as_of_date=_TODAY,
        fetched_at_ist=_NOW,
        weight_version="2026.04",
        sanitized=True,
    )
    cleaned = _sanitize_nodes([node], anon_map)
    assert cleaned[0] is node, "Already-sanitized node should be returned as-is (no copy)"


def test_round_trip_restore():
    """scrub_text → restore_text must recover the original text."""
    anon_map = build_anon_map(
        stock="RELIANCE",
        sector="Energy",
        promoter_names=["Mukesh Ambani"],
        brand_names=["Jio"],
    )
    original = "RELIANCE Q4: Jio adds 8M users under Mukesh Ambani leadership."
    scrubbed = scrub_text(original, anon_map)
    restored = restore_text(scrubbed, anon_map)

    assert "RELIANCE" in restored
    assert "Jio"      in restored
    assert "Mukesh Ambani" in restored
    assert "STOCK_A" not in restored
    assert "BRAND_A" not in restored
    assert "PROMOTER_A" not in restored


def test_no_double_replacement():
    """Longer tokens must be replaced before shorter ones to avoid partial matches."""
    anon_map = build_anon_map(
        stock="ITC",
        brand_names=["ITC Limited"],   # longer than "ITC"
    )
    text = "ITC Limited reports; ITC standalone PAT up."
    scrubbed = scrub_text(text, anon_map)

    assert "ITC" not in scrubbed, f"'ITC' still present: {scrubbed!r}"
    assert "ITC Limited" not in scrubbed, f"'ITC Limited' still present: {scrubbed!r}"
