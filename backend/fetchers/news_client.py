"""
news_client.py — RSS news fetcher for approved Indian financial news domains.

Fetches news from approved RSS feeds defined in config/sources.yaml (news section).
All domains and URLs come from sources.yaml — no hardcoded URLs here.

Source priority (from sources.yaml):
  P1: moneycontrol, economic_times, business_standard, livemint
  P2: reuters_india, bq_prime
  P3: google_news_rss (fallback)

Each item is filtered to include only stories that mention the target stock
(symbol or company name in title/description). Items are returned newest-first.

HTTP calls use the central http_client.py for rate-limiting + circuit breaking.
RSS parsing uses feedparser. Raw HTML in descriptions is stripped before
returning — never passes raw HTML to callers (sanitizer handles any residual).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any

import feedparser  # type: ignore

from config import yaml_cfg
from fetchers.http_client import get as http_get

logger = logging.getLogger(__name__)


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_news(
    symbol: str,
    company_name: str = "",
    max_age_days: int = 30,
    max_items: int = 20,
) -> dict[str, Any]:
    """
    Fetch and filter recent news for a stock from all approved RSS feeds.

    Tries approved_domains in priority order (P1 → P2 → P3). Collects
    items from all feeds that mention the symbol or company name.
    Falls back to google_news_rss if no P1/P2 feeds yield relevant items.

    Args:
        symbol:       NSE ticker (e.g. "RELIANCE") — used for title filtering.
        company_name: Full company name for broader title matching.
        max_age_days: Only return items published within this many days.
        max_items:    Maximum total items to return across all feeds.

    Returns:
        Dict with "items" list of news dicts, "symbol", "feeds_tried" count.
        Never raises — returns {"items": [], ...} on total failure.
    """
    symbol = symbol.upper().strip()
    cfg = yaml_cfg.sources

    news_cfg: dict = cfg.get("news", {})
    approved: list[dict] = news_cfg.get("approved_domains", [])
    cutoff = _cutoff_date(max_age_days)

    all_items: list[dict] = []
    feeds_tried = 0

    # Sort by priority (lower number = higher priority)
    ordered = sorted(approved, key=lambda s: s.get("priority", 99))

    # P1 + P2 feeds first
    primary_feeds = [s for s in ordered if s.get("priority", 99) <= 2]
    fallback_feed = next((s for s in ordered if s.get("id") == "google_news_rss"), None)

    for src in primary_feeds:
        rss_url = src.get("rss_url", "")
        if not rss_url:
            continue
        feeds_tried += 1
        items = await _fetch_rss(rss_url, symbol, company_name, cutoff, src["id"])
        all_items.extend(items)

    # If primary feeds yielded nothing, try Google News RSS
    if not all_items and fallback_feed:
        fallback_url = _build_google_news_url(fallback_feed, symbol, company_name)
        if fallback_url:
            feeds_tried += 1
            items = await _fetch_rss(
                fallback_url, symbol, company_name, cutoff, "google_news_rss"
            )
            all_items.extend(items)

    # Deduplicate by title, sort newest first, cap at max_items
    seen: set[str] = set()
    unique: list[dict] = []
    for item in sorted(all_items, key=lambda x: x.get("published_iso", ""), reverse=True):
        key = item.get("title", "").lower()[:80]
        if key not in seen:
            seen.add(key)
            unique.append(item)
        if len(unique) >= max_items:
            break

    return {
        "symbol":      symbol,
        "items":       unique,
        "feeds_tried": feeds_tried,
        "total_found": len(unique),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_rss(
    url: str,
    symbol: str,
    company_name: str,
    cutoff: datetime,
    source_id: str,
) -> list[dict[str, Any]]:
    """
    Fetch a single RSS feed URL and return filtered news items.

    Args:
        url:          RSS feed URL (pre-validated against sources.yaml).
        symbol:       NSE ticker for title/desc matching.
        company_name: Optional company name for broader matching.
        cutoff:       Items older than this are excluded.
        source_id:    Source ID stamped on each returned item.

    Returns:
        List of news item dicts (may be empty if no matching items).
    """
    try:
        resp = await http_get(url, timeout=15)
        feed = feedparser.parse(resp.text)
    except Exception as exc:
        logger.debug("RSS fetch failed: url=%s source=%s error=%s", url, source_id, exc)
        return []

    items = []
    for entry in feed.get("entries", []):
        title = entry.get("title", "")
        summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))

        # Filter: must mention the symbol or company name
        if not _mentions(symbol, company_name, title, summary):
            continue

        pub_dt = _parse_pub_date(entry)
        if pub_dt and pub_dt < cutoff:
            continue   # too old

        items.append({
            "title":         _strip_html(title),
            "summary":       summary[:500] if summary else "",
            "url":           entry.get("link", ""),
            "source_id":     source_id,
            "published_iso": pub_dt.isoformat() if pub_dt else "",
            "symbol":        symbol,
        })

    return items


def _mentions(symbol: str, company_name: str, title: str, summary: str) -> bool:
    """
    Return True if title or summary mentions the stock symbol or company name.

    Matching is case-insensitive. Symbol must appear as a whole word to avoid
    false positives (e.g. "IT" matching unrelated headlines).
    """
    text = f"{title} {summary}".lower()
    sym_low = symbol.lower()
    # Whole-word match for ticker
    if re.search(r'\b' + re.escape(sym_low) + r'\b', text):
        return True
    # Partial match for company name (names are multi-word, less likely to false-positive)
    if company_name:
        name_low = company_name.lower()
        # Only use first two words of company name to avoid over-specific matching
        first_words = " ".join(name_low.split()[:2])
        if first_words and first_words in text:
            return True
    return False


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_pub_date(entry: dict) -> datetime | None:
    """
    Parse RSS entry publication date to a timezone-aware datetime.
    Returns None if unparseable.
    """
    # feedparser exposes parsed time as published_parsed (time.struct_time)
    t = entry.get("published_parsed")
    if t:
        try:
            return datetime(*t[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    # Fallback: try raw string
    raw = entry.get("published", "")
    if raw:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(raw)
        except Exception:
            pass
    return None


def _cutoff_date(max_age_days: int) -> datetime:
    """Return a UTC-aware datetime for max_age_days ago."""
    from datetime import timedelta
    return datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _build_google_news_url(fallback_cfg: dict, symbol: str, company_name: str) -> str:
    """
    Build a Google News RSS search URL for the stock.

    Format: https://news.google.com/rss/search?q=RELIANCE+NSE&hl=en-IN&gl=IN&ceid=IN:en
    """
    base = fallback_cfg.get("search_url", "")
    if not base:
        return ""
    # Use company name if available (broader match), else symbol
    query = company_name if company_name else symbol
    # Sanitize query — Google News doesn't like raw special chars
    query_clean = re.sub(r"[^\w\s]", " ", query).strip().replace(" ", "+")
    return f"{base}?q={query_clean}+India&hl=en-IN&gl=IN&ceid=IN:en"
