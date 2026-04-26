"""
agent_news.py — News Data Agent (Phase 4 Agent Layer).

Fetches raw news articles via news_service.get_news, applies basic HTML
sanitization and imperative-sentence stripping, classifies each headline
into a signal class drawn from weights.yaml, and converts each article into
a typed Node object ready for the knowledge graph.

Sanitized=True after this agent — basic scrubbing only (strip_html +
strip_imperative_sentences). The Orchestrator applies full identity scrub
(company-name anonymization) before nodes enter the Analysis Agent.

Contract:
  Input:  FetchRequest
  Output: list[Node] | FetchFailure
  Errors: returned as FetchFailure, never raised
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from backend.schemas.messages import FetchDomain, FetchFailure, FetchRequest
from backend.schemas.node import HorizonRelevance, Node, NodeCategory, NodeSignal
from backend.services.news_service import get_news
from backend.util.ist_calendar import now_ist
from backend.util.sanitizer import strip_html, strip_imperative_sentences

logger = logging.getLogger(__name__)

# ── Config load ────────────────────────────────────────────────────────────────

_CONFIG_DIR    = Path(__file__).parents[2] / "config"
_WEIGHTS_RAW   = yaml.safe_load((_CONFIG_DIR / "weights.yaml").read_text())
_NEWS_CLASSES  = _WEIGHTS_RAW["news_signal_classes"]
_PROFILES      = yaml.safe_load((_CONFIG_DIR / "profiles.yaml").read_text())
_WEIGHT_VER    = yaml.safe_load((_CONFIG_DIR / "versions.yaml").read_text())["weight_version"]

_NEWS_ITEM_BASE_WEIGHT: float = 0.10  # fallback; overridden per profile horizon
_MAX_ARTICLES: int = 10               # top 10 most crucial articles only
_FETCH_TIMEOUT: float = 25.0          # newsdata.io + enrichment needs a bit more time

# ── Signal classification helpers ─────────────────────────────────────────────
# Ordered by priority — first match wins.

_CLASS_KEYWORDS: list[tuple[str, list[str]]] = [
    ("regulatory_sebi_action", [
        "sebi", "penalty", "investigation", "ban", "enforcement",
        "adjudication", "insider trading", "show cause",
    ]),
    ("fraud_allegation", [
        "fraud", "scam", "irregularity", "misappropriation",
        "embezzlement", "manipulation", "siphon",
    ]),
    ("credit_rating_change", [
        "downgrade", "upgrade", "crisil", "icra", "care ratings",
        "fitch", "moody", "credit rating", "rating action",
    ]),
    ("leadership_change", [
        "ceo", "chief executive", "cfo", "chief financial", "managing director",
        "chairman", "resignation", "quits", "appoints", "board change",
    ]),
    ("ma_event", [
        "merger", "acquisition", "takeover", "demerger",
        "amalgamation", "joint venture", "strategic alliance",
    ]),
    ("major_contract", [
        "bags order", "wins contract", "secures deal",
        "order win", "major contract", "new order",
    ]),
    ("dividend_or_buyback", [
        "dividend", "buyback", "buy-back", "bonus share",
        "special dividend", "interim dividend",
    ]),
]

_POSITIVE_WORDS = frozenset([
    "profit", "growth", "record", "strong", "beat", "beats",
    "surge", "surges", "rally", "rise", "gain", "increase",
    "win", "wins", "expansion", "milestone", "outperform",
    "recovery", "upgrade", "positive",
])

_NEGATIVE_WORDS = frozenset([
    "loss", "decline", "fall", "weak", "miss", "misses", "concern",
    "worry", "decrease", "drop", "cut", "slowdown", "layoff",
    "penalty", "fraud", "downgrade", "negative", "risk",
    "warning", "plunge", "crash",
])

# ── Source → confidence map ────────────────────────────────────────────────────

_SOURCE_CONFIDENCE: dict[str, float] = {
    "newsdata_io":       0.80,   # structured REST API, verified publishers
    "moneycontrol":      0.70,
    "economic_times":    0.70,
    "business_standard": 0.70,
    "livemint":          0.70,
    "google_news_rss":   0.50,
}

_SOURCE_SLUG_MAP: list[tuple[str, str]] = [
    ("newsdata_io",       "newsdata_io"),    # newsdata.io REST API
    ("newsdata",          "newsdata_io"),
    ("moneycontrol",      "moneycontrol"),
    ("economic times",    "economic_times"),
    ("et markets",        "economic_times"),
    ("business standard", "business_standard"),
    ("mint",              "livemint"),
    ("livemint",          "livemint"),
]


def _classify(title: str) -> tuple[str, NodeSignal]:
    """
    Classify a news headline into a signal class and NodeSignal.

    Checks structured keyword classes first (ordered by severity), then falls
    back to generic positive/negative based on word-set intersection.

    Args:
        title: Sanitized (HTML-stripped) news headline.

    Returns:
        Tuple of (signal_class_key, NodeSignal).
    """
    low = title.lower()

    for cls, keywords in _CLASS_KEYWORDS:
        if any(kw in low for kw in keywords):
            if cls == "regulatory_sebi_action":
                return cls, NodeSignal.negative
            if cls == "fraud_allegation":
                return cls, NodeSignal.negative
            if cls == "credit_rating_change":
                sig = (NodeSignal.negative if "downgrade" in low
                       else NodeSignal.positive if "upgrade" in low
                       else NodeSignal.neutral)
                return cls, sig
            if cls == "leadership_change":
                return cls, NodeSignal.neutral
            if cls == "ma_event":
                return cls, NodeSignal.neutral
            if cls == "major_contract":
                return cls, NodeSignal.positive
            if cls == "dividend_or_buyback":
                return cls, NodeSignal.positive

    words = set(re.findall(r"\b\w+\b", low))
    pos_hits = len(words & _POSITIVE_WORDS)
    neg_hits = len(words & _NEGATIVE_WORDS)

    if pos_hits > neg_hits:
        return "generic_positive", NodeSignal.positive
    if neg_hits > pos_hits:
        return "generic_negative", NodeSignal.negative
    return "generic_positive", NodeSignal.neutral


def _news_weight(signal_class: str, horizon: str) -> float:
    """
    Compute per-node weight as (category_budget / max_articles) × class_multiplier.

    Args:
        signal_class: Key into news_signal_classes in weights.yaml.
        horizon:      Investor horizon string ("short" or "long").

    Returns:
        Rounded float weight for this node.
    """
    base = _PROFILES["category_mix"].get(horizon, {}).get("news", _NEWS_ITEM_BASE_WEIGHT)
    mult = _NEWS_CLASSES.get(signal_class, {}).get("weight_multiplier", 0.8)
    return round((base / _MAX_ARTICLES) * mult, 4)


def _resolve_source(raw_source: str) -> tuple[str, float]:
    """
    Map a raw source name from the article dict to an approved source slug and
    its corresponding confidence score.

    Args:
        raw_source: Raw source string from article metadata.

    Returns:
        Tuple of (source_slug, confidence).
    """
    low = raw_source.lower()
    for fragment, slug in _SOURCE_SLUG_MAP:
        if fragment in low:
            return slug, _SOURCE_CONFIDENCE.get(slug, 0.70)
    return "google_news_rss", 0.50


def _parse_as_of_date(published: str, fallback: date) -> date:
    """
    Extract a date from the article's "published" string (expects YYYY-MM-DD prefix).

    Args:
        published: Raw published timestamp string from the article dict.
        fallback:  Date to use when parsing fails.

    Returns:
        Parsed date or fallback.
    """
    try:
        return date.fromisoformat(published[:10])
    except Exception:
        return fallback


def _article_to_node(
    article: dict[str, Any],
    index: int,
    request: FetchRequest,
    horizon: str,
    fetched_at: Any,
) -> Node | None:
    """
    Convert a single raw article dict to a Node.

    Applies strip_html + strip_imperative_sentences to title and summary,
    classifies signal, resolves source slug, and builds the Node.

    Args:
        article:    Raw article dict from news_service.get_news.
        index:      Zero-based article index (used for node name).
        request:    Original FetchRequest.
        horizon:    Investor horizon ("short" or "long").
        fetched_at: IST datetime when the batch fetch occurred.

    Returns:
        Constructed Node, or None if title is empty after sanitization.
    """
    raw_title    = article.get("title") or ""
    raw_summary  = article.get("description") or article.get("summary") or ""
    key_sentence = article.get("key_sentence") or ""
    stock_impact = article.get("stock_impact") or ""
    signal_class = article.get("signal_class") or ""

    title   = strip_imperative_sentences(strip_html(raw_title)).strip()[:300]
    snippet = strip_imperative_sentences(strip_html(raw_summary)).strip()[:200]
    key_s   = strip_html(key_sentence).strip()[:250]

    if not title:
        return None

    # Derive signal class from pre-computed field or fall back to classifier
    if signal_class:
        _, sig = _classify(title)  # signal direction from title keywords
    else:
        signal_class, sig = _classify(title)

    # Node value: headline + key insight sentence (most informative for LLM)
    if key_s and key_s.lower() not in title.lower():
        value = f"{title} | Key insight: {key_s}"
    elif snippet:
        value = f"{title} — {snippet}"
    else:
        value = title

    source_slug, conf = _resolve_source(str(article.get("source", "")))
    weight            = _news_weight(signal_class, horizon)
    as_of             = _parse_as_of_date(
        str(article.get("published", "")), request.as_of_date
    )

    return Node(
        stock=request.stock.upper(),
        category=NodeCategory.news,
        name=f"News_Item_{index}",
        value=value,
        value_raw={
            "title":        raw_title,
            "description":  raw_summary,
            "key_sentence": key_sentence,
            "stock_impact": stock_impact,
            "link":         article.get("link", ""),
            "published":    article.get("published", ""),
            "source":       article.get("source", ""),
            "source_name":  article.get("source_name", ""),
            "signal_class": signal_class,
        },
        signal=sig,
        confidence=conf,
        source=source_slug,
        source_url=article.get("link", ""),
        as_of_date=as_of,
        fetched_at_ist=fetched_at,
        horizon_relevance=HorizonRelevance.both,
        weight=weight,
        weight_version=_WEIGHT_VER,
        schema_version=1,
        sanitized=True,
    )


class NewsAgent:
    """
    Phase 4 Agent: fetches and converts news articles into Node objects.

    Calls news_service.get_news (approved sources only), caps at 20 articles,
    sanitizes each headline, classifies signal, and emits typed Nodes.
    Returns FetchFailure on empty feed or unhandled error — never raises.
    """

    domain = FetchDomain.news

    async def fetch(self, request: FetchRequest) -> list[Node] | FetchFailure:
        """
        Fetch news articles and convert them to Nodes (max 20).

        Args:
            request: FetchRequest carrying stock symbol, date, and user profile.

        Returns:
            list[Node] on success, FetchFailure if no articles or on error.
        """
        try:
            articles = await asyncio.wait_for(
                get_news(request.stock.upper(), company_name=None),
                timeout=_FETCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("agent_news: timeout fetching news for %s", request.stock)
            return FetchFailure(
                domain=self.domain,
                source="news_rss",
                reason="timeout",
                error=f"get_news timed out after {_FETCH_TIMEOUT}s",
                request_id=request.request_id,
            )
        except Exception as exc:
            logger.error("agent_news: fetch error for %s — %s", request.stock, exc)
            return FetchFailure(
                domain=self.domain,
                source="news_rss",
                reason="parse_error",
                error=str(exc),
                request_id=request.request_id,
            )

        if not articles:
            logger.info("agent_news: no articles for %s", request.stock)
            return FetchFailure(
                domain=self.domain,
                source="news_rss",
                reason="empty",
                error="get_news returned empty list",
                request_id=request.request_id,
            )

        fetched_at = now_ist()
        horizon    = request.profile.horizon.value
        nodes: list[Node] = []

        for i, art in enumerate(articles[:_MAX_ARTICLES]):
            try:
                node = _article_to_node(art, i, request, horizon, fetched_at)
                if node is not None:
                    nodes.append(node)
            except Exception as exc:
                logger.warning(
                    "agent_news: skipping article %d for %s — %s", i, request.stock, exc
                )

        logger.info("agent_news: %s — %d nodes built from %d articles",
                    request.stock, len(nodes), len(articles[:_MAX_ARTICLES]))
        return nodes

    async def validate(self, nodes: list[Node]) -> list[Node]:
        """
        Drop nodes that failed sanitization or have an empty value.

        Args:
            nodes: Raw list of Nodes produced by fetch().

        Returns:
            Filtered list containing only valid, sanitized nodes.
        """
        valid = [n for n in nodes if n.sanitized and n.value.strip()]
        dropped = len(nodes) - len(valid)
        if dropped:
            logger.info("agent_news: validate dropped %d invalid nodes", dropped)
        return valid


# Module-level singleton.
news_agent = NewsAgent()


async def run(request: FetchRequest) -> list[Node] | FetchFailure:
    """Module-level entry point — delegates to news_agent singleton."""
    return await news_agent.fetch(request)
