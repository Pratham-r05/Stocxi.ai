"""
news_service.py — Recent news headlines for a stock symbol.

AI_CONTEXT.md spec: "News | yfinance .news property | Good enough for phase 1"

Reality: yfinance .news also hits crumb-gated endpoints and 429s with our IP.

Fix: Primary source = Google News RSS
  URL: https://news.google.com/rss/search?q={symbol}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en
  - Completely free, no auth, no API key, no rate limits
  - Returns real financial news in English, India-focused
  - Parse with stdlib xml.etree (no extra deps)

Fallback: yfinance .news (works when Yahoo isn't throttling)
Fallback 2: Empty list (never crash)

Cache TTL: 7200s (2 hrs) — set in redis_client.py TTL_NEWS
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
_TIMEOUT = 10
_MAX_NEWS = 10
_NEWS_MAX_AGE_DAYS = 7  # only show news from last 7 days


def _is_recent_news(published_iso: str) -> bool:
    """Return True if article was published within _NEWS_MAX_AGE_DAYS."""
    if not published_iso:
        return True  # keep if date unknown
    try:
        # Handle ISO with or without trailing Z
        dt_str = published_iso.rstrip("Z")
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=_NEWS_MAX_AGE_DAYS)
        return dt >= cutoff
    except Exception:
        return True  # keep on parse failure


# ── Source 1: Google News RSS ─────────────────────────────────────────────────
def _fetch_google_news(symbol: str, company_name: str | None = None) -> list[dict]:
    """
    Google News RSS — completely free, India-focused, in English.
    Query: "<symbol> NSE stock" OR "<company_name> stock" if available.
    """
    # Build query — include company name if available for better relevance
    after_date = (datetime.now(timezone.utc) - timedelta(days=_NEWS_MAX_AGE_DAYS)).strftime("%Y-%m-%d")
    query_parts = [f"{symbol} NSE stock after:{after_date}"]
    if company_name and company_name != symbol:
        query_parts.append(f"{company_name} stock India after:{after_date}")
    query = " OR ".join(query_parts)

    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = []

        for item in root.findall(".//item")[:_MAX_NEWS]:
            title     = item.findtext("title", "").strip()
            link      = item.findtext("link", "").strip()
            pub_date  = item.findtext("pubDate", "").strip()
            source_el = item.find("source")
            source    = source_el.text.strip() if source_el is not None else "Google News"

            if not title:
                continue

            # Parse pubDate → ISO format ("Mon, 14 Apr 2025 03:00:00 GMT")
            published_iso = pub_date
            try:
                dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
                published_iso = dt.isoformat() + "Z"
            except Exception:
                pass

            items.append({
                "title":     title,
                "link":      link,
                "published": published_iso,
                "source":    source,
            })

        # Post-filter: drop anything older than cutoff (Google `after:` is fuzzy)
        items = [a for a in items if _is_recent_news(a["published"])]
        logger.info(f"Google News RSS: {len(items)} recent articles for {symbol}")
        return items

    except Exception as e:
        logger.warning(f"Google News RSS failed for {symbol}: {e}")
        return []


# ── Source 2: yfinance .news (fallback, works when Yahoo not throttled) ────────
def _fetch_yfinance_news(symbol: str) -> list[dict]:
    """
    yfinance .news property — may 429, use only as fallback.
    Uses browser session to reduce rate limiting.
    """
    import requests as req
    import yfinance as yf

    session = req.Session()
    session.headers.update({"User-Agent": _HEADERS["User-Agent"]})

    items = []
    for suffix in [".NS", ".BO"]:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}", session=session)
            news   = ticker.news or []
            if not news:
                continue
            cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=_NEWS_MAX_AGE_DAYS)).timestamp()
            for n in news[:_MAX_NEWS]:
                pub_ts = n.get("providerPublishTime", 0)
                if pub_ts and float(pub_ts) < cutoff_ts:
                    continue  # skip old articles
                pub_iso = ""
                if pub_ts:
                    try:
                        pub_iso = datetime.fromtimestamp(float(pub_ts), tz=timezone.utc).isoformat() + "Z"
                    except Exception:
                        pub_iso = str(pub_ts)
                items.append({
                    "title":     n.get("title", "").strip(),
                    "link":      n.get("link", ""),
                    "published": pub_iso,
                    "source":    n.get("publisher", "Yahoo Finance"),
                })
            logger.info(f"yfinance news: {len(items)} recent articles for {symbol}{suffix}")
            return items
        except Exception as e:
            logger.debug(f"yfinance news failed for {symbol}{suffix}: {e}")
    return []


# ── Main function ─────────────────────────────────────────────────────────────
def _get_news_sync(symbol: str, company_name: str | None = None) -> list[dict]:
    """
    Sync — runs in thread pool.
    1. Try Google News RSS (primary — reliable)
    2. Try yfinance .news (fallback)
    3. Return [] — never raises
    """
    symbol = symbol.upper().strip()

    articles = _fetch_google_news(symbol, company_name)
    if articles:
        return articles

    logger.warning(f"Google News empty for {symbol}, trying yfinance...")
    articles = _fetch_yfinance_news(symbol)
    if articles:
        return articles

    logger.warning(f"No news found for {symbol} from any source")
    return []


async def get_news(symbol: str, company_name: str | None = None) -> list[dict]:
    """
    Async entry point.
    Returns list of news dicts: [{title, link, published, source}, ...]
    Never raises — returns [] on complete failure.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_news_sync, symbol, company_name)
