"""
article_extractor.py — Deterministic key-sentence extractor for news articles.

Extracts the single most informative sentence from an article's text
(description + content combined). No LLM required — pure heuristic scoring.

Scoring algorithm per sentence:
  +3  sentence mentions the stock symbol or company name
  +2  per financial keyword hit (revenue, profit, growth, etc.), capped at +4
  +2  sentence contains a number or percentage (e.g. "up 18%", "₹500 crore")
  +1  sentence length is between 10 and 50 words (too short = noise, too long = summary)
  -1  sentence is a boilerplate disclaimer or navigation fragment

The extractor also derives a plain-English stock_impact string from the
signal_class and key_sentence — a one-liner explaining how this news typically
moves the stock, used to populate node.value_raw["stock_impact"].
"""

from __future__ import annotations

import re

# ── Financial keyword scoring ─────────────────────────────────────────────────

_FINANCIAL_KEYWORDS: frozenset[str] = frozenset([
    "revenue", "profit", "loss", "earnings", "ebitda", "margin", "growth",
    "decline", "quarter", "annual", "results", "guidance", "target",
    "acquisition", "merger", "demerger", "stake", "order", "contract",
    "dividend", "buyback", "bonus", "split", "rating", "downgrade", "upgrade",
    "sebi", "penalty", "fraud", "investigation", "ceo", "cfo", "appointed",
    "resigned", "debt", "cash", "capex", "expansion", "plant", "capacity",
    "export", "import", "market share", "ipo", "fpo", "qip", "rights issue",
    "npa", "provisioning", "loan", "credit", "interest rate", "rbi",
    "₹", "crore", "lakh", "billion", "million", "percent", "%",
])

_BOILERPLATE_FRAGMENTS: tuple[str, ...] = (
    "click here", "read more", "subscribe", "sign in", "log in",
    "privacy policy", "terms of use", "all rights reserved",
    "advertisement", "sponsored", "follow us", "share this",
    "next article", "previous article", "related stories",
    "also read", "check out", "find out more",
)

# ── Impact template map: signal_class → stock_impact string ──────────────────

_IMPACT_TEMPLATES: dict[str, str] = {
    "regulatory_sebi_action": (
        "SEBI action typically triggers sharp sell-off; sentiment turns sharply "
        "negative and institutional holders may reduce exposure."
    ),
    "fraud_allegation": (
        "Fraud allegations historically cause sustained multi-day declines; "
        "retail confidence erodes until independent audit confirms findings."
    ),
    "credit_rating_change_downgrade": (
        "Rating downgrade raises cost of borrowing; signals deteriorating "
        "financials — typically bearish for medium-term price."
    ),
    "credit_rating_change_upgrade": (
        "Rating upgrade lowers borrowing cost and signals improving balance "
        "sheet — positive for medium-term sentiment."
    ),
    "credit_rating_change": (
        "Rating action signals changing credit quality; direction depends on "
        "upgrade vs downgrade — watch for borrowing cost impact."
    ),
    "leadership_change": (
        "C-suite change introduces near-term uncertainty; market reaction "
        "depends on incoming leader's track record — typically neutral to negative."
    ),
    "ma_event": (
        "M&A events often cause short-term volatility; acquirer may dip on "
        "deal premium concerns while target typically rallies."
    ),
    "major_contract": (
        "Material contract win is a direct revenue visibility signal — "
        "positive for near-term order book and analyst upgrades."
    ),
    "dividend_or_buyback": (
        "Dividend or buyback signals management confidence in cash generation; "
        "typically short-term positive — stock often goes ex-date adjusted."
    ),
    "generic_positive": (
        "Positive news improves near-term sentiment; magnitude depends on "
        "proximity to earnings calendar and current market regime."
    ),
    "generic_negative": (
        "Negative headline increases short-term selling pressure; sustained "
        "impact depends on whether it alters fundamental outlook."
    ),
}


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_key_sentence(
    text: str,
    symbol: str,
    company_name: str = "",
) -> str:
    """
    Extract the most informative sentence from combined article text.

    Scores each sentence by financial keyword density, number/percentage
    presence, symbol/company mention, and length. Returns the
    highest-scoring sentence, or the first sentence if all score zero.

    Args:
        text:         Combined description + content string.
        symbol:       NSE ticker (e.g. "RELIANCE").
        company_name: Full company name for mention scoring.

    Returns:
        Single best sentence string (stripped, max 300 chars).
        Returns "" if text is empty.
    """
    if not text or not text.strip():
        return ""

    sentences = _split_sentences(text)
    if not sentences:
        return ""

    if len(sentences) == 1:
        return _truncate(sentences[0])

    sym_low   = symbol.lower().strip()
    name_low  = company_name.lower().strip() if company_name else ""
    # First two words of company name (most discriminative)
    name_first = " ".join(name_low.split()[:2]) if name_low else ""

    scored: list[tuple[float, str]] = []
    for sent in sentences:
        score = _score_sentence(sent, sym_low, name_first)
        scored.append((score, sent))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    return _truncate(best)


def derive_stock_impact(signal_class: str, key_sentence: str = "") -> str:
    """
    Return a plain-English explanation of how this news class typically
    affects the stock price.

    Picks from _IMPACT_TEMPLATES; falls back to a generic template.
    For credit_rating_change, refines to upgrade/downgrade if keyword found.

    Args:
        signal_class: Signal class key from _CLASS_KEYWORDS in agent_news.py.
        key_sentence: Best sentence (used for downgrade/upgrade disambiguation).

    Returns:
        Non-empty impact string.
    """
    if signal_class == "credit_rating_change" and key_sentence:
        low = key_sentence.lower()
        if "downgrade" in low:
            return _IMPACT_TEMPLATES["credit_rating_change_downgrade"]
        if "upgrade" in low:
            return _IMPACT_TEMPLATES["credit_rating_change_upgrade"]

    return _IMPACT_TEMPLATES.get(signal_class, _IMPACT_TEMPLATES["generic_positive"])


# ── Internal helpers ───────────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using punctuation boundaries.

    Handles common abbreviations and decimal numbers to avoid false splits.

    Args:
        text: Raw article text.

    Returns:
        List of non-empty sentence strings.
    """
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Split on sentence-ending punctuation followed by space + capital letter
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\'])", text)
    cleaned: list[str] = []
    for s in raw:
        s = s.strip()
        if len(s) > 20:   # discard very short fragments
            cleaned.append(s)
    return cleaned


def _score_sentence(sentence: str, sym_low: str, name_first: str) -> float:
    """
    Heuristic relevance score for a single sentence.

    Args:
        sentence:   Raw sentence string.
        sym_low:    Lowercase stock symbol.
        name_first: First two words of company name (lowercase).

    Returns:
        Float score (higher = more informative).
    """
    score = 0.0
    low   = sentence.lower()

    # Boilerplate penalty
    if any(frag in low for frag in _BOILERPLATE_FRAGMENTS):
        return -1.0

    # Stock mention bonus
    if sym_low and re.search(r"\b" + re.escape(sym_low) + r"\b", low):
        score += 3.0
    elif name_first and name_first in low:
        score += 3.0

    # Financial keyword hits (cap at 4 × 0.5 = +2.0)
    kw_hits = sum(1 for kw in _FINANCIAL_KEYWORDS if kw in low)
    score += min(kw_hits * 0.5, 2.0)

    # Number / percentage presence
    if re.search(r"\d", sentence):
        score += 2.0

    # Length bonus: 10–50 words ideal
    word_count = len(sentence.split())
    if 10 <= word_count <= 50:
        score += 1.0
    elif word_count < 6:
        score -= 1.0

    return score


def _truncate(sentence: str, max_len: int = 300) -> str:
    """Truncate sentence to max_len characters, preserving word boundaries."""
    sentence = sentence.strip()
    if len(sentence) <= max_len:
        return sentence
    truncated = sentence[:max_len].rsplit(" ", 1)[0]
    return truncated + "…"
