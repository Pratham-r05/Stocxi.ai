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

from schemas.messages import FetchDomain, FetchFailure, FetchRequest
from schemas.node import HorizonRelevance, Node, NodeCategory, NodeSignal
from services.context_generator import apply_news_context
from services.news_service import get_news
from util.ist_calendar import now_ist
from util.sanitizer import strip_html, strip_imperative_sentences

logger = logging.getLogger(__name__)

# ── Config load ────────────────────────────────────────────────────────────────

_CONFIG_DIR = next((p / "config" for p in Path(__file__).parents if (p / "config").exists()), Path("config").resolve())
_WEIGHTS_RAW   = yaml.safe_load((_CONFIG_DIR / "weights.yaml").read_text())
_NEWS_CLASSES  = _WEIGHTS_RAW["news_signal_classes"]
_PROFILES      = yaml.safe_load((_CONFIG_DIR / "profiles.yaml").read_text())
_WEIGHT_VER    = yaml.safe_load((_CONFIG_DIR / "versions.yaml").read_text())["weight_version"]

_NEWS_ITEM_BASE_WEIGHT: float = 0.10  # fallback; overridden per profile horizon
_MAX_ARTICLES: int = 10               # top 10 most crucial articles only
_FETCH_TIMEOUT: float = 45.0          # newsdata.io + enrichment needs a bit more time

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
    ("earnings_result", [
        "quarterly results", "q4 results", "q3 results", "q2 results", "q1 results",
        "fy26", "fy25", "fy24", "annual results", "net profit", "pat rises",
        "pat falls", "revenue rises", "revenue falls", "earnings",
        "quarterly profit", "annual profit",
    ]),
    ("leadership_change", [
        "ceo", "chief executive", "cfo", "chief financial", "managing director",
        "chairman", "resignation", "quits", "appoints", "board change",
    ]),
    ("analyst_action", [
        "analyst", "target price", "brokerage", "upgrades", "downgrades",
        "buy rating", "sell rating", "hold rating", "price target",
        "recommendation",
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
    "gnews":             0.65,   # Google News via gnews lib, free, no API key
    "newsdata_io":       0.80,   # structured REST API, verified publishers
    "moneycontrol":      0.70,
    "economic_times":    0.70,
    "business_standard": 0.70,
    "livemint":          0.70,
    "google_news_rss":   0.50,
}

_SOURCE_SLUG_MAP: list[tuple[str, str]] = [
    ("gnews",             "gnews"),           # gnews Python library (Google News)
    ("newsdata_io",       "newsdata_io"),      # newsdata.io REST API
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
            if cls == "earnings_result":
                # Direction depends on whether results are positive or negative
                neg_words = {"falls", "falls", "drop", "decline", "miss", "weak", "dip", "slips"}
                pos_words = {"rises", "beats", "jump", "surge", "strong", "growth", "record"}
                words = set(re.findall(r"\b\w+\b", low))
                if words & neg_words:
                    return cls, NodeSignal.negative
                if words & pos_words:
                    return cls, NodeSignal.positive
                return cls, NodeSignal.neutral
            if cls == "leadership_change":
                return cls, NodeSignal.neutral
            if cls == "analyst_action":
                sig = (NodeSignal.positive if any(w in low for w in ["upgrade", "buy", "outperform"])
                       else NodeSignal.negative if any(w in low for w in ["downgrade", "sell", "underperform"])
                       else NodeSignal.neutral)
                return cls, sig
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


def _news_weight(
    signal_class: str,
    horizon: str,
    relevance_score: float = 0.5,
    article_horizon: str = "both",
) -> float:
    """
    Compute per-node weight incorporating category budget, signal class,
    LLM relevance score, and horizon alignment.

    Formula:
        weight = (category_budget / max_articles) × class_multiplier × relevance × horizon_match

    horizon_match:
        1.0 if article_horizon == "both" or matches user horizon
        0.6 if article_horizon != user horizon (less relevant for this investor)

    Args:
        signal_class:     Key into news_signal_classes in weights.yaml.
        horizon:          User's investor horizon ("short" or "long").
        relevance_score:  LLM-assessed relevance 0.0-1.0 (default 0.5).
        article_horizon:  LLM-assessed horizon relevance ("short", "long", "both").

    Returns:
        Rounded float weight for this node.
    """
    base = _PROFILES["category_mix"].get(horizon, {}).get("news", _NEWS_ITEM_BASE_WEIGHT)
    mult = _NEWS_CLASSES.get(signal_class, {}).get("weight_multiplier", 0.8)

    # Horizon alignment: boost if article matches user's horizon, reduce if not
    if article_horizon == "both" or article_horizon == horizon:
        horizon_match = 1.0
    else:
        horizon_match = 0.6  # still include, but lower weight

    weight = (base / _MAX_ARTICLES) * mult * relevance_score * horizon_match
    return round(max(weight, 0.001), 4)


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

    Prefers LLM-generated summary + classification when available,
    falls back to heuristic key_sentence + signal classifier.

    Args:
        article:    Raw article dict from news_service.get_news.
                    May contain llm_summary, llm_relevance, llm_signal_class, llm_horizon.
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

    # LLM fields (may be absent if LLM enrichment failed)
    llm_summary      = article.get("llm_summary") or ""
    llm_relevance    = article.get("llm_relevance", None)
    llm_signal_class = article.get("llm_signal_class") or ""
    llm_horizon      = article.get("llm_horizon") or "both"

    title   = strip_imperative_sentences(strip_html(raw_title)).strip()[:300]
    snippet = strip_imperative_sentences(strip_html(raw_summary)).strip()[:200]
    key_s   = strip_html(key_sentence).strip()[:250]

    if not title:
        return None

    # ── Signal classification: prefer LLM, fallback to heuristic ─────────
    signal_class_to_use: str
    sig: NodeSignal

    if llm_signal_class:
        signal_class_to_use = llm_signal_class
        # Derive signal direction from LLM class + title keywords
        _, sig = _classify(title)
    else:
        signal_class_to_use, sig = _classify(title)

    # ── Compute relevance + horizon before building value ──────────────
    relevance_score = llm_relevance if llm_relevance is not None else 0.5
    article_horizon = llm_horizon if llm_horizon in ("short", "long", "both") else "both"

    # ── Node value: structured format for model + user readability ─────────
    # Format: [class] headline — analysis: summary | Impact: dir | Relevance: X/1.0 | For: horizon
    if llm_summary:
        # Clean headline: strip source suffix like " - Business Standard"
        clean_title = re.sub(r'\s*[-–—|]\s*(The |Business Standard|Moneycontrol|Economic Times|Mint|CNBC|Reuters|Times of India|Markets Mojo|MarketWatch|Investing\.com).*$',
                            '', title, flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = title[:120]

        # Impact direction from signal
        if sig == NodeSignal.positive:
            impact_dir = "Positive"
        elif sig == NodeSignal.negative:
            impact_dir = "Negative"
        else:
            impact_dir = "Neutral"

        # Format summary: ensure it fits within 500 total chars
        # Budget: ~120 title + ~50 class/format + ~50 metadata = ~220 overhead
        # Remaining for summary: ~280 chars
        summary_parts = llm_summary.replace('\n', ' ').strip()
        summary_capped = summary_parts[:400]

        value = (
            f"[{signal_class_to_use}] {clean_title[:120]}\n"
            f"Analysis: {summary_capped}\n"
            f"Impact: {impact_dir} | Relevance: {relevance_score}/1.0 | For: {article_horizon}-term"
        )
    elif key_s and key_s.lower() not in title.lower():
        # Clean title for fallback too
        clean_title = re.sub(r'\s*[-–—|]\s*(The |Business Standard|Moneycontrol|Economic Times|Mint|CNBC|Reuters|Times of India|Markets Mojo|MarketWatch|Investing\.com).*$',
                            '', title, flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = title[:120]
        value = f"[{signal_class_to_use}] {clean_title[:120]}\nKey insight: {key_s[:250]}"
    elif snippet:
        clean_title = re.sub(r'\s*[-–—|]\s*(The |Business Standard|Moneycontrol|Economic Times|Mint|CNBC|Reuters|Times of India|Markets Mojo|MarketWatch|Investing\.com).*$',
                            '', title, flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = title[:120]
        value = f"[{signal_class_to_use}] {clean_title[:120]}\n{snippet[:250]}"
    else:
        clean_title = re.sub(r'\s*[-–—|]\s*(The |Business Standard|Moneycontrol|Economic Times|Mint|CNBC|Reuters|Times of India|Markets Mojo|MarketWatch|Investing\.com).*$',
                            '', title, flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = title[:150]
        value = f"[{signal_class_to_use}] {clean_title}"

    # Cap value at 800 chars (structured format with LLM summary needs more space)
    value = value[:800]

    # ── Weight: horizon-aware with LLM relevance ─────────────────────────
    source_slug, conf = _resolve_source(str(article.get("source", "")))
    weight = _news_weight(
        signal_class_to_use,
        horizon,
        relevance_score=relevance_score,
        article_horizon=article_horizon,
    )
    as_of = _parse_as_of_date(
        str(article.get("published", "")), request.as_of_date
    )

    # ── Horizon relevance for the node ───────────────────────────────────
    if article_horizon == "both":
        node_horizon = HorizonRelevance.both
    elif article_horizon == "short":
        node_horizon = HorizonRelevance.short
    elif article_horizon == "long":
        node_horizon = HorizonRelevance.long
    else:
        node_horizon = HorizonRelevance.both

    return Node(
        stock=request.stock.upper(),
        category=NodeCategory.news,
        name=f"News_Item_{index}",
        value=value,
        value_raw={
            "title":            raw_title,
            "description":      raw_summary,
            "key_sentence":     key_sentence,
            "stock_impact":     stock_impact,
            "llm_summary":      llm_summary,
            "llm_relevance":    relevance_score,
            "llm_signal_class": llm_signal_class,
            "llm_horizon":      llm_horizon,
            "link":             article.get("link", ""),
            "published":        article.get("published", ""),
            "source":           article.get("source", ""),
            "source_name":      article.get("source_name", ""),
            "signal_class":     signal_class_to_use,
        },
        signal=sig,
        confidence=conf,
        source=source_slug,
        source_url=article.get("link", ""),
        as_of_date=as_of,
        fetched_at_ist=fetched_at,
        horizon_relevance=node_horizon,
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

        # Promote llm_summary from value_raw into node.context (no extra LLM call)
        nodes = apply_news_context(nodes)

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
