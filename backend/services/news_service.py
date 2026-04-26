"""
news_service.py — Top-10 stock news with key sentence extraction.

Waterfall (L1 → L2):
  L1: newsdata.io REST API  (NEWSDATA_API_KEY required; confidence=0.80)
  L2: Google News RSS        (free; confidence=0.50)

For each article the service:
  1. Calls article_extractor.extract_key_sentence on description+content.
  2. Produces a one-line stock_impact via article_extractor.derive_stock_impact.
  3. Returns a normalised dict with fields: title, description, content,
     key_sentence, stock_impact, link, published, source, source_name.

Max 10 articles returned, sorted newest-first.
Never raises — returns [] on complete failure.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

from backend.fetchers.newsdata_client import fetch_stock_news
from backend.util.article_extractor import derive_stock_impact, extract_key_sentence

logger = logging.getLogger(__name__)

_MAX_NEWS       = 10
_MAX_AGE_DAYS   = 7
_TIMEOUT        = 10
_HEADERS        = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Signal-class keywords (mirrors agent_news._CLASS_KEYWORDS for impact lookup)
_CLASS_KEYWORDS: list[tuple[str, list[str]]] = [
    ("regulatory_sebi_action", ["sebi", "penalty", "investigation", "ban", "enforcement",
                                 "adjudication", "insider trading", "show cause"]),
    ("fraud_allegation",       ["fraud", "scam", "irregularity", "misappropriation",
                                 "embezzlement", "manipulation", "siphon"]),
    ("credit_rating_change",   ["downgrade", "upgrade", "crisil", "icra", "care ratings",
                                 "fitch", "moody", "credit rating", "rating action"]),
    ("leadership_change",      ["ceo", "chief executive", "cfo", "chief financial",
                                 "managing director", "chairman", "resignation",
                                 "quits", "appoints", "board change"]),
    ("ma_event",               ["merger", "acquisition", "takeover", "demerger",
                                 "amalgamation", "joint venture", "strategic alliance"]),
    ("major_contract",         ["bags order", "wins contract", "secures deal",
                                 "order win", "major contract", "new order"]),
    ("dividend_or_buyback",    ["dividend", "buyback", "buy-back", "bonus share",
                                 "special dividend", "interim dividend"]),
]


# ── Public async entry point ─────────────────────────────────��────────────────

async def get_news(symbol: str, company_name: str | None = None) -> list[dict[str, Any]]:
    """
    Fetch and enrich top-10 news articles for a stock, async entry point.

    Runs the waterfall (newsdata.io → Google News RSS) in a thread pool,
    then extracts key_sentence + stock_impact for each article.

    Args:
        symbol:       NSE ticker (e.g. "RELIANCE").
        company_name: Full company name for broader matching.

    Returns:
        list[dict] with fields: title, description, content, key_sentence,
        stock_impact, link, published, source, source_name, signal_class.
        Empty list on complete failure.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _get_news_sync, symbol, company_name or ""
    )


# ── Sync pipeline ───────────────────────────────────────────────────────────��─

def _get_news_sync(symbol: str, company_name: str) -> list[dict[str, Any]]:
    """
    Sync waterfall: newsdata.io → Google News RSS.

    Args:
        symbol:       NSE ticker.
        company_name: Full company name (may be empty string).

    Returns:
        Enriched article list (max 10).
    """
    symbol = symbol.upper().strip()

    # L1: newsdata.io
    result = fetch_stock_news(symbol, company_name)
    if result.ok:
        raw_articles = _normalise_newsdata(result.payload, symbol, company_name)
        if raw_articles:
            logger.info("news_service: newsdata.io → %d articles for %s", len(raw_articles), symbol)
            return _enrich(raw_articles, symbol, company_name)

    # L2: Google News RSS
    logger.info("news_service: newsdata.io empty/missing for %s, trying Google News RSS", symbol)
    raw_articles = _fetch_google_news_rss(symbol, company_name)
    if raw_articles:
        logger.info("news_service: Google News RSS → %d articles for %s", len(raw_articles), symbol)
        return _enrich(raw_articles, symbol, company_name)

    logger.warning("news_service: no news from any source for %s", symbol)
    return []


# ── Normalisers ────────────────────────────────��──────────────────────────────

def _normalise_newsdata(
    raw: list[dict[str, Any]],
    symbol: str,
    company_name: str,
) -> list[dict[str, Any]]:
    """
    Convert newsdata.io article dicts to the canonical intermediate format.

    Args:
        raw:          List of article dicts from newsdata_client.fetch_stock_news.
        symbol:       NSE ticker for relevance filtering.
        company_name: Company name for relevance filtering.

    Returns:
        Filtered, normalised list (newest-first, max 10).
    """
    articles: list[dict[str, Any]] = []
    for item in raw:
        title = item.get("title", "").strip()
        if not title:
            continue
        if not _is_relevant(title, symbol, company_name):
            continue

        pub_dt: datetime | None = item.get("pub_dt")
        published_iso = pub_dt.isoformat() if pub_dt else item.get("pubDate", "")

        articles.append({
            "title":       title,
            "description": item.get("description", ""),
            "content":     item.get("content", ""),
            "link":        item.get("link", ""),
            "published":   published_iso,
            "source":      item.get("source_id", "newsdata_io"),
            "source_name": item.get("source_name", ""),
            "sentiment":   item.get("sentiment", ""),   # may be empty on free tier
        })

    return articles[:_MAX_NEWS]


def _fetch_google_news_rss(symbol: str, company_name: str) -> list[dict[str, Any]]:
    """
    Fetch news from Google News RSS as L2 fallback.

    Args:
        symbol:       NSE ticker.
        company_name: Company name for query building.

    Returns:
        Normalised article list (max 10).
    """
    query_term = company_name if company_name else f"{symbol} NSE"
    after_date = (datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    query = f"{query_term} stock when:{_MAX_AGE_DAYS}d after:{after_date}"
    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:
        logger.warning("news_service: Google News RSS failed for %s — %s", symbol, exc)
        return []

    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item")[:_MAX_NEWS * 2]:
        title    = (item.findtext("title") or "").strip()
        link     = (item.findtext("link")  or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        src_el   = item.find("source")
        source   = src_el.text.strip() if src_el is not None else "Google News"

        if not title or not _is_relevant(title, symbol, company_name):
            continue

        pub_dt       = _parse_rfc_date(pub_date)
        published_iso = pub_dt.isoformat() if pub_dt else pub_date

        if pub_dt and pub_dt < datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS):
            continue

        articles.append({
            "title":       title,
            "description": "",
            "content":     "",
            "link":        link,
            "published":   published_iso,
            "source":      "google_news_rss",
            "source_name": source,
            "sentiment":   "",
        })

    return _sort_by_date(articles)[:_MAX_NEWS]


# ── Enrichment ───────────────────────────────────��──────────────────────────���─

def _enrich(
    articles: list[dict[str, Any]],
    symbol: str,
    company_name: str,
) -> list[dict[str, Any]]:
    """
    Add key_sentence, stock_impact, and signal_class to each article dict.

    Args:
        articles:     List of normalised article dicts.
        symbol:       NSE ticker for key sentence scoring.
        company_name: Company name for key sentence scoring.

    Returns:
        Same list with key_sentence, stock_impact, signal_class added in-place.
    """
    for art in articles:
        combined_text = " ".join(filter(None, [
            art.get("description", ""),
            art.get("content", ""),
        ]))

        key_sentence = extract_key_sentence(combined_text, symbol, company_name)
        signal_class = _classify_signal_class(art.get("title", ""))
        stock_impact = derive_stock_impact(signal_class, key_sentence)

        art["key_sentence"]  = key_sentence
        art["stock_impact"]  = stock_impact
        art["signal_class"]  = signal_class

    return articles


# ── Helpers ──────────────────────────────────────────────────────��────────────

def _classify_signal_class(title: str) -> str:
    """
    Classify a headline into one of the signal class keys.

    Args:
        title: News headline string.

    Returns:
        Signal class key string (e.g. "major_contract", "generic_positive").
    """
    low = title.lower()
    for cls, keywords in _CLASS_KEYWORDS:
        if any(kw in low for kw in keywords):
            return cls

    pos_words = frozenset(["profit", "growth", "record", "strong", "beat", "surge",
                            "rally", "rise", "gain", "win", "expansion", "upgrade"])
    neg_words = frozenset(["loss", "decline", "fall", "miss", "concern", "drop",
                            "cut", "penalty", "fraud", "downgrade", "plunge"])
    words = set(re.findall(r"\b\w+\b", low))
    if len(words & pos_words) > len(words & neg_words):
        return "generic_positive"
    if len(words & neg_words) > len(words & pos_words):
        return "generic_negative"
    return "generic_positive"


_NAME_STOPWORDS: frozenset[str] = frozenset([
    "limited", "ltd", "india", "group", "co", "company", "plc",
    "bank", "finance", "financial", "services", "technologies", "tech",
    "industries", "industry", "enterprises", "holdings", "ventures",
    "corp", "corporation", "international", "global",
])


def _is_relevant(title: str, symbol: str, company_name: str) -> bool:
    """
    Return True if the headline is clearly about the target stock.

    Matching rules (in order):
    1. Exact whole-word ticker match (e.g. "RELIANCE" in title)
    2. Company's distinctive core words (≥4 chars, non-generic) appear in title

    Args:
        title:        News headline.
        symbol:       NSE ticker.
        company_name: Full company name.

    Returns:
        True if title mentions the stock.
    """
    low = title.lower()
    sym = symbol.lower()

    if re.search(r"\b" + re.escape(sym) + r"\b", low):
        return True

    if company_name:
        # Keep only distinctive words: ≥4 chars, not in stopword list
        core_words = [
            w for w in company_name.lower().split()
            if len(w) >= 4 and w not in _NAME_STOPWORDS
        ]
        if not core_words:
            return False
        # All core words (up to 2) must appear — avoids "bank" matching ICICI for HDFC
        check = core_words[:2]
        return all(re.search(r"\b" + re.escape(w) + r"\b", low) for w in check)

    return False


def _parse_rfc_date(raw: str) -> datetime | None:
    """Parse RFC-2822 date string (RSS pubDate) to UTC datetime."""
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _sort_by_date(articles: list[dict]) -> list[dict]:
    """Sort articles newest-first by 'published' ISO string."""
    def _key(a: dict) -> datetime:
        raw = a.get("published", "")
        try:
            s = raw
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    return sorted(articles, key=_key, reverse=True)
