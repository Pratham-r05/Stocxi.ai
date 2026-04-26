"""
newsdata_client.py — Newsdata.io REST API client for stock news.

Primary news source (L1). Uses NEWSDATA_API_KEY from backend settings.
Fetches up to 10 India-focused business news articles for a stock,
ranked by publication date (newest first).

API docs: https://newsdata.io/documentation
Free tier: 200 requests/day, description field available, content may be
           truncated. Falls through gracefully when key is absent.

Returns FetchResult with payload list[dict], each dict containing:
  title, description, content, link, pubDate, source_id, source_name,
  sentiment (if available), category

Confidence: 0.80 — structured REST API, India-filtered, verified publishers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from backend.config import settings
from backend.fetchers.base import FetchResult

logger = logging.getLogger(__name__)

_BASE_URL      = "https://newsdata.io/api/1/news"
_CONFIDENCE    = 0.80
_SOURCE_ID     = "newsdata_io"
_TIMEOUT       = 12          # seconds
_MAX_ARTICLES  = 10
_MAX_AGE_DAYS  = 7           # only articles from the past week


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_stock_news(
    symbol: str,
    company_name: str = "",
) -> FetchResult:
    """
    Fetch top-10 recent India business news articles for a stock from newsdata.io.

    Uses qInTitle for higher precision (only articles that mention the company/
    symbol in their headline). Falls back to q= (full-text search) if qInTitle
    yields fewer than 3 results.

    Args:
        symbol:       NSE ticker (e.g. "RELIANCE").
        company_name: Full company name for broader headline matching.

    Returns:
        FetchResult with source_id="newsdata_io", confidence=0.80, and
        payload=list[dict] on success; FetchResult.failure() on any error
        or missing API key.
    """
    api_key = settings.newsdata_api_key.strip()
    if not api_key:
        logger.debug("newsdata_client: NEWSDATA_API_KEY not set — skipping")
        return FetchResult.failure(_SOURCE_ID, _CONFIDENCE, "api_key_missing")

    # Prefer company name in headline (higher precision)
    title_query = company_name if company_name else symbol
    articles = _query(api_key, title_query, use_title_field=True)

    # If fewer than 3 results with qInTitle, retry with q= (broader)
    if len(articles) < 3:
        symbol_articles = _query(api_key, symbol, use_title_field=False)
        # Merge, dedup by link
        seen = {a["link"] for a in articles}
        for art in symbol_articles:
            if art["link"] not in seen:
                articles.append(art)
                seen.add(art["link"])

    if not articles:
        logger.info("newsdata_client: no articles returned for %s", symbol)
        return FetchResult.failure(_SOURCE_ID, _CONFIDENCE, "empty_response")

    articles = _sort_by_date(articles)[:_MAX_ARTICLES]
    logger.info("newsdata_client: %d articles for %s", len(articles), symbol)
    return FetchResult.success(_SOURCE_ID, _CONFIDENCE, articles)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _query(api_key: str, query: str, use_title_field: bool) -> list[dict[str, Any]]:
    """
    Execute one newsdata.io API call.

    Args:
        api_key:         Newsdata.io API key.
        query:           Search query string.
        use_title_field: If True, use qInTitle (headline-only match).
                         If False, use q (full-text match).

    Returns:
        List of article dicts (may be empty on error or no results).
    """
    field_name = "qInTitle" if use_title_field else "q"
    params: dict[str, str] = {
        "apikey":   api_key,
        field_name: query,
        "language": "en",
        "country":  "in",
        "category": "business",
    }

    try:
        resp = requests.get(_BASE_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        logger.warning("newsdata_client: timeout for query=%s", query)
        return []
    except requests.exceptions.HTTPError as exc:
        logger.warning("newsdata_client: HTTP %s for query=%s", exc.response.status_code, query)
        return []
    except Exception as exc:
        logger.warning("newsdata_client: request failed for query=%s — %s", query, exc)
        return []

    if data.get("status") != "success":
        logger.warning(
            "newsdata_client: non-success status=%s for query=%s",
            data.get("status"), query,
        )
        return []

    articles: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=_MAX_AGE_DAYS)

    for item in data.get("results", []):
        title = str(item.get("title") or "").strip()
        link  = str(item.get("link")  or "").strip()
        if not title or not link:
            continue

        pub_str = str(item.get("pubDate") or "").strip()
        pub_dt  = _parse_date(pub_str)
        if pub_dt and pub_dt < cutoff:
            continue    # skip stale articles

        articles.append({
            "title":        title,
            "description":  str(item.get("description") or "").strip(),
            "content":      str(item.get("content")     or "").strip(),
            "link":         link,
            "pubDate":      pub_str,
            "pub_dt":       pub_dt,
            "source_id":    str(item.get("source_id")   or "newsdata_io").strip(),
            "source_name":  str(item.get("source_name") or "").strip(),
            "sentiment":    str(item.get("sentiment")   or "").strip(),  # paid tier only
            "category":     item.get("category") or [],
        })

    return articles


def _parse_date(raw: str) -> datetime | None:
    """
    Parse newsdata.io pubDate string to UTC-aware datetime.

    Args:
        raw: pubDate string, typically "YYYY-MM-DD HH:MM:SS".

    Returns:
        UTC datetime, or None if unparseable.
    """
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _sort_by_date(articles: list[dict]) -> list[dict]:
    """Sort articles newest-first. Articles with unknown dates go last."""
    return sorted(
        articles,
        key=lambda a: a.get("pub_dt") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
